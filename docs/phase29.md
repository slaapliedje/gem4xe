# Phase 29 -- an accessory opened from a folder, and used

Two bugs a person found in ten minutes that eight gates had not, both on
the same path: **open a folder, launch the program in it, use it.**  The
first (phase 28's tail, `gd_cioname`) was that the program could not find
its own resource.  This one is what it did once it could.

## The report

> Calculator loads, but gives an hourglass and I can't click on anything.

## What the hourglass was

`desk_busy(TRUE)` -- `graf_mouse(HOURGLASS, 0)` -- is the last thing the
desktop does before `shel_write`, and it deliberately never puts the
pointer back.  That is correct **in the donor**, and the reason is worth
writing down because it is the shape of most of what is left to go wrong
here:

> In the ROM AES the mouse form belongs to a **process**.  `set_mown`
> gives the mouse's new owner its own form back (`geminput.c`), so the
> desktop's hourglass dies with the desktop's turn at the mouse, and the
> program that starts next brings the arrow it was born with.

gem4xe runs **one process**.  The form is one global in `graf.c`, so
nothing in the donor's design is there to put it right, and the
hourglass stayed over the calculator for as long as the calculator ran.

The fix is one line in `sh_main`'s loop, beside the `ratinit()` the donor
already has there, with the reasoning above in the comment:

    ratinit();              /* the pointer on, as the donor */
    gr_mouse(ARROW, 0);     /* ...and the ARROW, which the donor does
                             * not have to do: a form belongs to a
                             * PROCESS there.  One process here. */

**The model had the same hole**, which is why no gate saw it: `deskref`
sets the hourglass in `desk_busy` exactly as the C does, and the six
places that model `sh_main`'s loop called `ratinit()` and stopped.  Both
sides were faithfully wrong together, and the pixel comparison passed.
The lesson is the one phase 28 ended on, from the other direction: *a
model catches what a program gets wrong, not what a description gets
wrong* -- so a gate needs at least one check that is not a comparison
against the model.  Here it is `mouse_form()`, which reads the VDI's own
`cur_data`/`cur_xhot` out of the target and names the form it finds
against `tools/gemdata.py`.  It does not ask the model anything.

## The gate: test-m23

`tests/emu/m23_deskapp.py`, on a disk (`build/m23-boot.atr`) that is
test-m17's with the two accessories in `\APPS\` as the product media
carries them -- the user's own layout.  The real desktop, at the mouse:

    double-click drive A      ->  a window on A:\*.*
    the fuller                ->  it grows to the desk
    double-click APPS         ->  do_fopen: the same window, deeper
    double-click CALC.PRG     ->  do_aopen: shel_write, and the shell
                                  loads the calculator
    a key on the panel        ->  the calculator answers it
    Quit                      ->  the desktop again

**No gate had opened a folder before.**  test-m18 launches a program
from a window, but from the root, and the program it launches (M11.PRG)
makes its calls and returns without ever reading the mouse.  test-m22
uses the accessories, but launches them from a stand-in desktop by a
KEYPRESS.  Neither crosses the seam that broke: what the AES's input
state and the pointer's form are left holding when one program stops
mid-gesture and the next one starts and asks for a click.

The click is checked by waiting FOR it, not by waiting it out: the
calculator's own `shown` is polled until it reads what the pressed key
means, so a click that never arrives is reported as a dead click and not
as a picture that differs somewhere.

## What is still open

The other half of the report -- *"I can't click on anything"* -- **does
not reproduce**, and the gate above is the reason that is worth saying
plainly: with synthetic input the whole path is sound, end to end.

The gates drive the pointer by poking `ptr_state` (`src/m3_vdi.c` opens
with `ptr_init(PTR_NONE, ...)` for exactly that reason).  So everything
ABOVE `ptr_state` is now covered on target and everything BELOW it --
the ST mouse's quadrature off PORTA, the timer interrupt that counts it,
the triggers -- has never run under a gate on the emulator at all.  It
is host-tested only.  That is where the remaining symptom has to live,
and it is the same layer as the other standing complaint, that the
pointer is slow.

Two facts read out of the shipping build booted on the reporter's own
machine configuration:

    irq.how = 1 (ROM_COPIED), irq.fail = 0     the interrupt regime IS up
    irq_ptr_on = 1                            the pointer sampler IS on

so the quadrature is being counted ~4000 times a second as designed, and
a dead sampler is not the explanation for either symptom.

**The bridge cannot drive an ST mouse.**  `JOY port direction [fire]`
offers the nine joystick positions, and ST quadrature needs PORTA
nibbles a joystick cannot make (x walks the pair 00-01-11-10, and 11 is
up and down at once).  Gating this layer needs a `MOUSE` verb added to
AltirraSDL's bridge -- a fourth patch on `tools/altirra/`, alongside the
three that are upstream PRs #88 and #90.

## A regression found on the way: test-m19

Running the gates the pointer-form fix touched turned up a failure that
**predates it** -- proved by backing the fix out and running test-m19
again, which fails identically.  It is phase 28's, and phase 28 never
re-ran this gate.

    FAIL: driving the desktop: op 162 did not complete on its plan
    it is inside a AES call, opcode 52          (form_alert)
    exists: 169 px differ from the model

The desktop puts up `STFOFAIL` -- *"You cannot create a folder with that
name."* -- and never comes out of it.  What is known:

  * the alert's box, icon and both message lines draw correctly;
  * **the button's " OK " is not painted**, and neither is the pointer
    over it, which is what the 169 pixels are;
  * RETURN does not take the default button, so the alert cannot be
    dismissed and the gate stalls there for good.

Everything the drawing reads was dumped out of the target at the stall
and is **correct**:

    the alert's string arena at $7042
      line0: 'You cannot create a folder\0'
      line1: 'with that name.\0'
      but0:  ' OK \0'
    the alert tree at $6F52
      [7] type 26 (G_BUTTON) flags $0027 (SELECTABLE|DEFAULT|EXIT|LASTOB)
          spec $710F  ( = arena + 205, exactly ' OK ')  xywh 112,48,40,8

So the tree is right, the string is right, the DEFAULT flag is set, and
the button is where the model has it -- the label is simply not drawn
and the key is not answered.  `test-m13` puts up six alerts with three
icons and takes their default buttons with RETURN, and **passes**, so
the alert library works in isolation; whatever this is, it is about the
state the desktop is in when it raises one.

### What the target's own cursor state says

Read out of the machine at the stall, with the alert on screen:

    gl_moff=0   cur_hide=0   cur_drawn=1
    sv_bx=134 (= pixel 268)  sv_y=141  sv_nb=8  sv_nr=16
    ptr_seen=268  xrat=268  yrat=141
    ct_owns=0 ct_inside=0 gl_ctmown=0 button=0 gl_bdely=0 gl_moff=0
    gl_ticks advancing, nothing changing over 40 further frames

So the AES's hide count and the VDI's agree that the pointer is SHOWN,
and `cur_drawn` says it is PAINTED, with a save block at exactly where
the pointer is -- and it is not on the screen.  That pins one half:

> `vdi_v_show_c` repaints only `if (cur_hide == 0 && !cur_drawn)`.  A
> draw that paints over a pointer the VDI still believes is drawn leaves
> `cur_drawn` set, and every later show is then a no-op: the pointer is
> gone for good, and the counts all read healthy.

`ob_draw` does bracket its work with `gsx_moff()`/`gsx_mon()`, so the
question is who had the AES's count already off zero when the alert was
drawn -- `gsx_moff()` only reaches the VDI on the 0->1 edge.

The button's " OK " is a second, separate absence: the message lines
above it drew, the glyph path flushes the blitter per character
(`draw_char`), and the label is the LAST thing the alert draws.  Whether
the two share a cause is not yet known.

Worth knowing while looking: **the blit chain holds 12 blocks**
(`MAX_BCB` in src/vbxe/vbxe.c) and `bcb_new()` returns 0 past that, which
every caller turns into a silent `return`.  Nothing reports a dropped
blit.

**A fix for the pointer half was tried and backed out.**  Making a forced
`v_show_c` throw the saved block away and repaint does bring a
painted-over pointer back -- but `gsx_mforce()` also forces a show, for
the menu, where the block is usually VALID and nothing redraws the
screen afterwards; discarding it there saves the cursor's own pixels and
the next hide stamps a cursor permanently onto the screen.  It changed
no gate either way, so it was not worth shipping a speculative fix with
a smear in it.  **The defect to find is whoever paints over the pointer
without hiding it**, not the show that cannot undo the damage.

Not yet chased further.  It is the one thing standing between the tree
and a green `make test`, and the pointer half of it -- a pointer that
can be painted over and never comes back -- is the kind of thing a
person meets as "I can't click on anything".

## A gate gap closed on the way

`test-m22` and `test-m23` replay an accessory's CALLS on the model but
not its INPUT, so the model never learned where `press()` had put the
pointer -- and the cursor is painted into the picture the two sides are
compared on.  It went unnoticed while the models did not repaint the
arrow between programs, because then neither side drew a cursor there at
all: **two omissions cancelling**.  Adding the arrow uncovered it.  Both
gates now move the model's pointer with the target's, and a failing
comparison writes the model's own picture out beside the screenshot
(`vbxeref.save_rgb`), because a count of differing pixels says nothing
about what differs -- that is what turned "169 px" into "the OK and the
pointer are missing" here.

## The third bug on the same path, found taking pictures

Open a folder, launch the program in it, use it -- and **quit it**.  The
desktop came back saying

> DESKTOP.RSC is not on the boot disk.

with a Quit button and nothing else, on the tester's disk and on the
shipped one alike.  Found on the day after 0.1 went out, by
`tests/emu/shots.py`, whose only job is to photograph the product being
used, and which could not get past the calculator's Quit to photograph
the accessory.

The cause is the fix before it.  Phase 28's tail made a bare resource
name resolve through GEMDOS's current directory so that a program could
find its own resource in the folder the desktop had `Dsetpath`ed into
before running it.  The desktop's own `DESKTOP.RSC` is a bare name too,
and when the shell ran the desktop again it ran it in the program's
folder.  The donor is explicit about this: `sh_chdef` changes drive and
directory back to the desktop's (`sh_cdir`, the boot drive's root) before
every run of the desktop.  `gemdos_home()` (`src/sys/gemdos.c`) is that
step here -- drive A, every drive's directory unset, so a bare name goes
to CIO as it did at boot -- and `sh_ldapp` calls it before it loads the
desktop.

Why eight gates missed the third bug on a path two of them walk:
`test-m23` checked that the desktop *ran* again after Quit -- `sh_runs`
reaching 3 -- and the shell counts the run before the desktop's `main()`,
where the load that fails is not a load status but an alert.  The gate
now waits for `gl_mntree`, the menu bar the desktop installs once its
resource is in; without the fix it reports "the desktop's menu bar never
came back", with it the bar is up 70 frames after the run is counted.
