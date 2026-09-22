# Phase 48 -- the AUTO folder, and a control panel with things in it

Phase 47 ended with a control panel that had two settings in it, and the
obvious complaint: an ST's control panel is not a dialog, it is a *host*.
You drop a `.CPX` into the system folder and the panel grows a page.
That is XCONTROL's shape, and it is the shape this phase builds, because
"applications ported from the ST work here" is the whole point of the
project and a CPX is an application shape like any other.

Getting there needed something underneath it that did not exist: a way
for a program to run at start-up and **stay**.

## Ptermres, and why it is all or nothing here

The ST's `Ptermres` keeps a byte count and frees the rest.  gem4xe keeps
the whole region or none of it, and that is not a simplification -- it
is what the allocators allow.

Both the pool and the far heap are **bump allocators**: a pointer that
moves up and winds back to a mark.  There is no free list, so there is
no way to give back the tail of a region and have the space be usable;
a partial release would leave a hole that neither allocator can ever
hand out again, and the honest version of that is to not offer it.  So
`Ptermres` here means *this program is now part of the floor*, and a
program that wants to be small at rest has to be small when it loads.

`src/sys/gemdos.h` said the opposite for six phases -- *"Nothing stays
resident after `Ptermres`; there is nothing on this machine for a TSR to
hook"* -- which was true when it was written and is the first thing this
phase falsified.  `docs/phase42.md` carries the same sentence and now
carries a note pointing here.

## \GEM\AUTO\, and where the mark goes

The AES runs `\GEM\AUTO\` in name order, before the accessories, before
the CPX modules, and before it sets the keep mark.  That ordering is the
whole mechanism: `pool_keep_mark()` and `far_keep_mark()` record where
the permanent floor is, and everything loaded above that line is wound
back when a program exits.  An AUTO program that ends with `Ptermres`
lands *below* the mark and outlives every program the desktop ever runs;
one that returns normally is freed like anything else, and the next one
loads over it.

An AUTO program gets **no process record and no turn**.  It is not a
task; it runs once, installs whatever it installs -- a vector, a device,
a service another program will look for -- and the machine goes on
without it in the event loop.  That is also why it is the dependency for
a task lister later: something has to be resident before there is
anything to list.

### The frame that nearly ate the stack

`test-m17` went red with the engine's stack **within 216 bytes of the
bottom** the first time an AUTO program ran.  The cause was not the AUTO
program: `sh_ldauto` was running it from inside the directory scan's own
stack frame, so the scan's locals were still live underneath the whole
of the program's execution.

Split into a non-inlined `sh_autoscan()` that collects the names and
returns, and a loop that runs them afterwards, so the scan's frame is
dead before any program starts.  `sh_cpxscan()` is the same shape for
the same reason, and both are deliberately marked not-inlined: the
compiler merging them back would silently restore the bug.

## The CPX contract

A CPX is a `.g4a` like any other, with one extra entry point:

```c
CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr);
```

It fills in the header -- title, id, version, flags -- and returns a
vtable of ten entries.  The host owns the window and the event loop; the
module owns its dialog.  Two kinds, distinguished by what `cpx_call`
leaves in `pb->ret`:

- **a form CPX** returns 0.  It ran its own `form_do` and is finished.
  `GENERAL.CPX` is one.
- **an event CPX** returns 1.  It drew itself and is now driven by the
  panel one event at a time -- `cpx_key`, `cpx_button`, `cpx_timer`,
  `cpx_draw` -- until it sets `pb->quit`.  `src/m35_cpx.c` is the
  worked example and the gate for it.

The module runs through **its own crt**, which matters more than it
sounds: the crt is what walks `data_init_table` and installs initialised
data.  A module entered around its crt has garbage globals and no
diagnostic, so `m35_sig` is an initialised word that every single entry
reads back and records -- a module entered wrongly reports a wrong
signature instead of working by luck until it doesn't.

### One uint32_t per entry, because the compiler says so

Every vtable entry takes exactly one `uint32_t` and casts it inside:

```c
static SAVEDS void m35_cpx_key(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
```

That is not a style choice.  Calling a separately linked module means the
callee must establish its own direct page and data bank, which is what
`__attribute__((saveds))` does -- and a `saveds` function on this
compiler emits its `tcd` **before** the body reads an argument that the
caller left in the *caller's* direct page.  Measured across five
signatures on 5.18.2: one `short` is safe, one `unsigned long` is safe,
and **a second argument of any kind, or a first argument that is a
pointer, arrives as garbage** with nothing refused and nothing warned.

Which is GEM's own ABI shape anyway -- `contrl`/`intin`/`ptsin` is one
parameter block reached by address -- so the contract is not distorted
by the constraint, only pinned down by it.

**Found by a screenshot.** The module drew its box in the wrong corner,
so it was made to print the rectangle it had been handed: `x=01E1
y=0000 w=3006 h=0000` where `00A0 0016 0140 00CD` was expected.  No gate
was red.  Nothing had been refused.

## XCPB, and the panel as a host

`XCPB` is what the panel hands *down*: the workstation handle, the
country, a scratch buffer, and callbacks -- `CPX_Save` for a module to
persist its own settings, `XGen_Alert` for a message in the host's
voice.  `appl_getinfo(AES_CPX)` is how the panel finds the modules at
all; it is the sixteenth subject the call answers, and it exists so the
panel needs no private channel into the AES.

`CPX_Save` is a `SAVEDS` callback with one argument, for the reason
above.  `XGen_Alert` is still 0 -- the alert strings belong in
`CPANEL.RSC` and no reader-visible string belongs in the C.

## Settings that survive a reboot

This is the claim a control panel exists for, and the one that cannot be
checked by looking at a running machine.

`GENERAL.CPX` writes a mark byte, the double-click rate and the sub-menu
delay into a file of its own.  The AES reads `<name>.CFG` back after the
module has initialised, laying the saved bytes over the defaults the
module just wrote.  Then the panel opens every module whose header has
`CPX_BOOTINIT` set, once, with `booting` true, so it can put its
settings back before anybody sees the desk.

The panel does that, not the AES -- the AES would have to learn the
shape of `CPXPB` and `XCPB`, which is a second place for two layouts to
drift.  Which is exactly the trouble that came next.

### Two faults, and both silent

Persistence did nothing at all.  Three stages of bisecting, by writing
three *distinct* rates at three points in start-up and reading back the
one that survived:

1. **The shell's load order had not changed.**  The edit that was
   supposed to move `sh_cpx()` above `sh_accs()` had not matched the
   file, and left a mangled line behind.  A replace that finds nothing
   looks exactly like a replace that worked.

2. **`char file[14]` was padded to 16.**  The slot is laid out by hand
   in the AES -- small-data, it cannot include the application header --
   and as a struct in `src/app/cpx.h`.  The compiler pads a `char[14]`
   between a `uint32_t` and an inner struct up to 16, so `hdr` sat at
   offset **20** in the struct and **18** in the AES.  Both sides built
   clean.  The AES wrote each module's header two bytes below where the
   panel read it, so every module's flags came back as whatever was in
   the gap.

The field is sixteen bytes now, and the layout is checked by the
compiler rather than by a comment:

```c
#define CPX_SLOT_HDR 20
typedef char cpx_slot_layout_holds[
    (offsetof(CPXSLOT, hdr) == CPX_SLOT_HDR) ? 1 : -1];
```

A negative array bound is a build error.  **Any struct that a second
piece of code restates by hand wants one of these.**

## The desktop gaps this phase closed on the way

Three things an ST does that gem4xe did not, all of them in the same
sentence a user would say about double-clicking:

- **`.APP`, `.TOS`, `.TTP`** are programs now, beside `.PRG` and `.G4A`.
  `.TTP` asks for a command line first, which is the only one of the
  five that changes what `do_open` does.  `.TOS` means something real
  here rather than being accepted for the look of it: GEMDOS has a VT-52
  console on GEM's screen (`docs/phase42.md`).
- **Show | Print | Cancel** on a document, reusing the text window the
  DOS-command output already had.
- **The installed name is `.PRG`**, not `.G4A`.  Somebody arriving from
  an ST cannot tell a program from a control panel extension if
  everything has the same extension.  `.G4A` is still accepted -- it is
  the container's name and it is what 0.5 shipped.

### A model that had been agreeing by never being asked

`tools/deskref.py` went on recognising two extensions after the target
recognised five, and stayed green, because no gate disk carried a
`.APP`, a `.TOS` or a `.TTP`.  The model was never asked the question it
would have got wrong.

`test-m17`'s disk carries one file per extension now.  They are text,
deliberately: the extension is the role and it is all the desktop reads
to pick an icon, while the format is the loader's business and it checks
the file's magic.  So `SAMPLE.TOS` draws as a program and would be
refused if it were opened -- which is the split the two layers are meant
to have.  With the files on the disk and the model unchanged, `test-m17`
reported twelve problems; the model then re-written from the ST's
vocabulary rather than transcribed from `deskwin.c`, because a model
copied off the target proves only that the copy was faithful.

## The numbers

| | |
|---|---|
| a CPX module's near region | 1,536 bytes, off the permanent floor |
| `appl_getinfo` subjects | 15 -> **16** (`AI_CPX`) |
| executable extensions the desktop knows | 2 -> **5** |
| host suite | **262** tests |
| new on the product media | `GENERAL.CPX`, `GENERAL.RSC` |

The 104-byte resident-name table went to far memory when LoRAM came in
at 213 free against its floor of 256 -- bank `$00` is still the scarce
thing and every phase pays it something.

## Gates

`test-m34` (the AUTO folder), `test-m35` (both halves of the CPX
contract), `test-m36` (settings across a reboot, **with the control**:
the same system booted without the saved file must come up at the AES's
own defaults, or "it was restored" and "nothing happened" are the same
picture).  Plus `m1`-`m36`, `test-boot`, `test-install`, `test-sdx816`,
the host suite (262), `tools/memreport.py`, `tools/nearcast.py` and
`tools/opcodes.py`.

Four of this phase's bugs were found by **looking at a picture**, not by
an assertion: the module in the wrong corner, the panel drawing "Test
CPX" twice, the tour's clicks missing because `publish()` doubles rows,
and a boot-init that did nothing.  `make shots` is a gate.
