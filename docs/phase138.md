# Phase 138 -- the CPX toolkit: widgets

Step 3 of [cpanel-plan.md](cpanel-plan.md), its second half, after the
events of [phase 137](phase137.md): XControl's pop-up menu and its six
slider calls, and `rsh_obfix`.  Color's channels are sliders now, and
General's sub-menu delay a pop-up.  On the way, a compiler bug hung the
machine the moment Color opened, and the scan that should have caught
it turned out never to have read the applications.

| | was | now |
|---|---|---|
| `Popup` | -- | a menu of strings at a button: five showing, or past five an up arrow, three items and a down arrow |
| `Sl_size`, `Sl_x`, `Sl_y` | -- | the thumb sized and placed for a value |
| `Sl_arrow` | -- | step by `sl_inc` while the button is held, the thumb moving |
| `Sl_dragx`, `Sl_dragy` | -- | the thumb follows the pointer, the value with it |
| `rsh_obfix` | -- | one object from characters to pixels |
| Color's red, green, blue | a button either side and a bar | a slider each: drag the thumb, press the track or a button either side |
| General's sub-menu delay | four radio buttons, "None" | a pop-up, "Instant" again |

## The calls

Each is a one-block callback, as cpx.h's ABI requires, with an inline in
cpx.h that reads like XControl's call: `cpx_popup`, `cpx_sl_size`,
`cpx_sl_xy` (Sl_x or Sl_y by direction), `cpx_sl_arrow`, `cpx_sl_drag`
(Sl_dragx or Sl_dragy), `cpx_rsh_obfix`.  The slider's `foo` is the
module's own function, called by the panel after every move, so it is a
vtable entry in all but name: SAVEDS and one uint32_t.  Color's is what
changes the pen while the thumb moves, which is the point of a slider.

The widgets draw straight onto the screen, clipped to what changed,
inside the screen lock.  They run only while someone is pressing in the
window, which the AES hands to this process only while the window is on
top (phase 134), so nothing covers it.

## Where they part from XControl

- **`Popup` draws CHECKED** for the default, where XControl writes a
  check into the string's first character and puts a space back after.
  The strings are left alone.  `pu_font` is ignored: one face a screen.
- **A slow click on a pop-up's button picks nothing.**  The menu opens
  over its button (which should be TOUCHEXIT and not SELECTABLE, so the
  menu comes up on the press).  If the button is still down when it appears, the
  choice is made on the release, as in XControl -- but not when the
  pointer never left the slot it came up under.  XControl took a slow
  click for the first item.
- **`Sl_arrow` waits a quarter of a second before it repeats**, then
  steps every 60 ms.  XControl repeats with no delay, and one ordinary
  click was eleven steps.
- **`Sl_y`'s minimum is at the bottom**, as XControl's: a list that
  starts at the top passes min = the last first row and max = 0.
- **`rsh_obfix` uses this screen's cell**, where XControl's is always
  8 x 16.  There is no `rsh_fix`: a module here loads its resource with
  `rsrc_load`.

## The pop-up waits for events

The first pop-up polled the button with `graf_mkstate` and a 20 ms
timer, and a six-frame press on an item fell between two turns of the
loop: the menu stayed up.  It now works out the slot under the pointer
from where the pointer is (the slots tile the menu), and waits in
`evnt_multi` for the button to change, for the pointer to leave that
slot (or, off the menu, to come onto it), or -- an arrow held -- for
125 ms, one item a turn.  The AES queues a press, so none is lost.

## The bug: an inlined function's returns are a join

With the widgets in, opening Color hung the machine: the pointer froze
and the CPU went round the AES's `ob_get_par` for ever.  The history
trace and the stack showed `objc_edit` called on Color's form, from the
panel's `Xform_do`, for object 32443 of 41:

    next = pb->xf_edit;
    if (!next)
        next = cp_firstedit(t);     /* return i; ... return 0; */
    ... form_button(t, next, nc, &next);

-O2 inlined `cp_firstedit`.  Both its returns stored to one stack slot,
and `next` was then copied from another that nothing had written.
`next` has its address taken, and this is B9 -- a join given to an
address-taken variable is wrong at every -O -- reached through a call
instead of a `?:`.  It worked in phase 137 only because that slot held
0; phase 138's code left something else there.  `next` no longer has
its address taken: `form_keybd` and `form_button` answer into variables
of their own.  [tools/ccbug/README.md](../tools/ccbug/README.md) has
the entry.

## The scan was blind

`make qscan` refuses B9's shapes, and said 0 for the whole tree.  It
could not have seen this one -- the source has no join -- so it now
counts a call to a function defined in the same file as a join when that
function has two returns with values, or a return with a join in it.
Then it still said 0 for cpanel.c.  Its clang was run without
`-I src/app`, so every application's `gem.h` was missing.  Every
function in `src/apps` was an invalid declaration with no body, so the
scan found nothing there and reported "0 not parsed".

It now passes every directory the Makefile does, `-m32` so the headers'
layout checks hold, fakes for Calypsi's `stubs.h` and the host's
`timeval` and `fpos_t`, and each device file's own `-D`s.  Any clang
error but the two the far model causes counts as "not parsed", which
fails the scan.  Its first real run found:

- the panel's `next`, the bug above;
- a B27 in `src/apps/edit.c`'s window title: a `?:` of `const char FAR *`
  and `char FAR *`, which cc65816 makes near.  Now an if;
- `src/aes/objc.c`'s two `xor_color` calls, whose three returns go into
  colours whose addresses are taken.  The kernel does not inline them
  today (a `jsl` and a store of A), but they now go through a local.

## Three banks: an open bug, found here

`test-m37` measured the boot on a 960K 65C816 and held it to three banks
from $05.  The panel's 5 KB moved the settled layout into a fourth: the
desktop's last block no longer fitted the top of bank 6 or of bank 7.

That check was read as "the boot fits three banks", and a machine with
exactly three -- a 65C816 with 512 KB, $05-$07 -- does not boot, at
phase 137 as now: gem4xe says the desktop needs more memory.  Cut to
three banks, the one request refused is the desktop's code, 49,048 bytes
that must end below $D500 in their bank, with bank 7 empty a moment
later.  The desktop file is squeezed (format 6), and `app_load_v6`
unpacks it into a block from the TOP of the heap, "out of the program's
way" -- which on three banks is bank 7, where the code has to go.  At its
peak the load wants the squeezed file (28 KB, the shell's cached copy),
its unpacked copy (about 55 KB) and the code and variables (53 KB) at
once: about 200 KB of 192.  On a bigger machine the top of the heap is a
spare bank and nothing shows.

So `test-m37` now says what is true: the settled boot fits four banks.
And it boots with the heap cut to three (`m37three`) as a known open
bug: while the desktop is refused it says so and passes, and the day the
desktop runs there it fails, so that it is made a real check.  The fix --
unpacking the desktop straight into its code and variable blocks, with no
55 KB copy -- is the next phase, before step 4.

## Gates

- **`test-m58`** grows: the gate module's form has a pop-up of seven
  items and a list's vertical slider, ten rows with three showing.  Held
  on the down arrow until it scrolls no further, the pop-up's last item
  shown is picked: the seventh.  The slider's thumb dragged to the foot
  is row 7, with `foo` called; its up arrow, once, is row 6.
- **`test-m42`**: Red's thumb dragged to level 7 makes the swatch
  (118, 0, 0) while it moves -- 467 thousandths, 59 in the VBXE's seven
  bits -- and Cancel puts it back.  The four steps down are `Sl_arrow`
  now.
- **`test-m44`**: General opened again, its delay button says
  "Normal"; a slow click on it leaves the delay, a click on "Instant"
  sets it to 0 and the button says so, and Cancel puts back 200 ms.  The
  button's text is read out of General's own tree, which the panel now
  keeps in `cp_form` for a gate (`Tour.panel()`'s `form`).

`make shots` found what the gates had not: General's button read
"...not be read or written.][ OK ]".  General looked its four names up
with `rsrc_gaddr` when the pop-up first ran, inside the panel's process,
and got the panel's own alert strings.  It takes them at `cpx_init` now,
beside its tree, and m44 reads the label.

Each check was run against a build without the thing it checks, and
failed: without `Popup`, `Sl_dragx` and `Sl_dragy`, the pop-up, the
list slider's drag and Color's drag; without `Sl_arrow`, the list's up
arrow and Color's four steps; without the slow-click rule, General's
slow click.  That last check first passed without its rule twice --
once because the gate's click lets go before the menu looks at the
button, and once because the button was SELECTABLE, which
`form_button` tracks until the release, so the menu never saw it held.
A pop-up's button is TOUCHEXIT alone now, in General and in the gate
module, as cpx.h says it should be; the gate holds the button for a
second.
