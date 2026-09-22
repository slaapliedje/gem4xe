# Phase 45 -- auditing what the engine serves, and the window order it was getting wrong

A name in a header is a promise, and an opcode in a dispatcher is what
keeps it.  This phase built the tool that checks the second against the
first, and then spent itself on what the tool found.

## The tool: read the dispatchers, not the headers

`tools/surface.py` already answered "which names does `gem.h` declare
that gemlib does" -- a real question, and not this one.
`tools/opcodes.py` reads the **dispatchers**: what actually has a case
in `crysbind`, and what answers `-1`.

    AES: 63 of 79 opcodes served      VDI: 66 of 71

The AES number is a real gap and Phase 46 closed it.  **The VDI's five
were never a gap at all**, and the tool has since been taught to say so:
they dispatch to `v_nop` on purpose -- `v_clswk`, because nothing closes
the physical workstation on this machine; `cellarray`, `vq_cellarray`
and `valuator`, because DRI's own GEM/3.1 screen driver nops those too;
and 34, which is not an opcode.  It reads 71 of 71 now, with the five
listed as decisions.  Nothing was implemented to make that happen, which
is exactly why reporting a settled decision as a miss was worth fixing:
it sent somebody looking to close them before a release.

The two audits disagreed in both directions, which is the point of
having the second one.  `WF_SCREEN` (17) and `WF_OWNER` (20) were
**served and not declared** -- so a port had to `#define` them itself,
and QED did.  `WF_BOTTOM` (25) was **declared and not served**, which is
the worse direction: a program that trusts the header gets `-1` at run
time.

Settling those three turned up a fourth thing, and it is the real
content of this phase.

## WF_OWNER was answering the wrong question, and the gate agreed with it

The Compendium (p.455) asks `wind_get(WF_OWNER)` for the handle of the
window directly **above** the one named, and the one directly **below**
it.  gem4xe handed back `gl_wtop` and the root's first child -- the
**top** and the **bottom** of the whole list.

With one window open the two readings agree.  That is why four phases of
gates did not notice: `m8` compares the target against
`tools/aesref.py`, **and the model was wrong in the same way**, so both
sides agreed and the gate passed.

This is the failure mode this tree has a memory for
(`model-and-target-agreeing-wrongly`), and the answer is always the
same: write the contract a **third** time, from the specification rather
than from either implementation.  `tests/host/test_wind_order.py` is
that third writing, and the case that tells the two readings apart is
the middle of three windows, whose neighbours are neither the top nor
the bottom.

Both directions were then checked by breaking them: restoring the old
answer in the model fails five of its eight tests, and restoring it in
the engine fails three of `m8`'s twelve cases.  A check nobody has seen
fail is not yet a check.

`WF_OWNER`'s first word is the owner's `ap_id`, so `WINDOW` gained
`w_owner`, set from the process that called `wind_create`.  An accessory
has a process of its own here and could own a window, so that is not a
constant even though the application is the only thing in the tree that
asks today.  Eight windows' worth of it took LoRAM under its margin and
`memreport` failed the build -- which is what it is for -- and the
LoRAM/Near boundary moved 16 bytes to `$3760`, the third time and the
only boundary in bank `$00` that can move safely.

`WF_BOTTOM` is served for `wind_get`: the first of the root's children,
the desk not counted, and the desk itself when there is no window.
`wind_set(WF_BOTTOM)` stays unserved and `gem.h` now says which half is
which.  Both it and `WF_OWNER` are AES 4.0's and gated there on
`appl_getinfo` -- which, at the time, gem4xe did not serve.  `wind_get`
answers them anyway: **a port that asks unguarded is better served with
the truth than with a refusal.**

## Closing the gaps, and the answers that are not the donor's

**`objc_sysvar` (48)** had the most measured callers of anything
missing: cflib asks it in `obgframe.c` and lays objects out by the
answer, MControl asks it, QED's port had to stub it.

The value matters more than the call.  `AD3DVALUE` asks how many extra
pixels an indicator or activator needs on each side to make room for its
3D border.  EmuTOS answers 2, because it really does draw a two-pixel
border.  **gem4xe draws none, so the answer is 0** -- copying EmuTOS's 2
would have every dialog in every ported program reserve space for
something that is never painted.  Zero is the true answer here, and the
truthful answer is the useful one.

**`appl_find` (13)** had nothing to search: gem4xe's processes had no
names.  `PROC` gained the donor's field -- eight characters,
blank-padded and deliberately **not** terminated, because eight is the
width the Compendium tells the caller to pad to and therefore the width
the compare has to be.  Blanks and not zeroes, for a specific reason: a
record of zeroes compares equal to the empty string over its whole
width, so `appl_find("")` would have been answered with a pid.

**`appl_getinfo` (130)** -- fifteen subjects and fifteen true answers.
(Sixteen since phase 48, which added `AI_CPX`: the control panel asks it
for the modules the AES loaded.)
Five real callers in cflib, the library QED links: `appinit.c` asks
subject 0 for the font metric it lays every dialog out with,
`sendchan.c` asks 10 before it will speak the AV protocol, and
`ppmenu.c` asks 9 about popups.  A truthful 0 is the whole point of the
call: a program told "no popup menus" draws its own, while one told
"yes" calls an opcode and gets `-1`.

**The Compendium has the return value backwards** (p.368: *"returns 1 if
an error occurred or 0 otherwise"*).  The ROM sets `ret = TRUE` and only
the default case clears it, and gemlib documents the opposite of the
Compendium.  The ROM wins.

**`appl_yield` (17)** is not in the Compendium at all -- its opcode
table leaves 17 blank -- so the contract is gemlib's binding and
EmuTOS's body, a bare `dsptch()`.  It matters more here than on the
machine it came from: `src/aes/proc.h` is a round robin with **no
pre-emption**, so a program that works for a long time between `evnt_`
calls stops every accessory beside it dead.

**`graf_mbox` (72) and `graf_slidebox` (76)** were already written and
had no door to them.  `gr_movebox` has had `graf_mbox`'s exact signature
since the graphics library was built, and `gr_slidebox` has had
`graf_slidebox`'s, because the window manager slides its own elevators
with it.  Neither had a case in the dispatch, so the opcodes answered
`-1`.  `gr_movebox` stopped being static; nothing else in the AES
changed.

**`wind_new` (109)** closes and deletes all of an application's
windows and resets the `wind_update` and pointer-hide counts -- what a
parent process calls to make sure a poorly written child has cleaned up.
`gsx_mreset` forces the pointer visible with one `V_SHOW_C` at
`intin[0] == 0` rather than a `gsx_mon` loop, so the AES's count and the
VDI's end up agreeing instead of drifting.

## The three widths the overlay actually has

gem4xe drew at 640x240 because that is the VBXE's normal overlay, and
had no way to say otherwise.  The hardware has three: the overlay
occupies 128, 160 or 168 colour clocks and HR puts four pixels in each,
so the screen is **512, 640 or 672** pixels.  `GEM4XE.CFG`'s `SCREENW`
picks one and the AES lays the desktop out to it.

Measured, not inferred.  The narrow overlay lands in columns 80..591 of
a 672-wide capture with the playfield showing through either side; the
wide one shows no playfield anywhere, so it covers all 672.  The crop
the comparator takes is `(672 - width) / 2` -- 80, 16, 0 -- which are
the three measured positions and not an assumption about centring.

The model had the width bound at import time in three module constants,
so every gate could only compare at 640.  It travels through
**construction** now -- `devref.Vbxe(width=...)` into the `Surface`,
which carries its own `w`/`h`/`stride` -- and the module constants stay
as the default.  Nothing rebinds anything, so a stray
`from vbxeref import SCR_W` cannot silently keep 640 while the model
draws 672.  `tools/modelsnap.py` proves the refactor moved nothing: the
digest is `69e954213736b66d` before and after.

`test-m3` is **258 cases** now, 86 at each width, and the whole run is
under two minutes.

**It found two bugs, and neither was visible at 640.**

*The XDL's `OVSTEP` was always `VB_STRIDE`.*  The display stepped 320
bytes per row whatever the overlay was showing.  At 672 it read 336
bytes from a 320-byte step, so the last 16 pixels of every row were the
next row's first 16 -- and at 512, once the rasteriser was fixed to step
256, the whole picture sheared.  `OVSTEP` is the screen's own stride
now.

*The device file's geometry was compile-time.*  Inside `dev_vbxe.c`,
`SCR_W` and `SCR_STRIDE` were `VB_W` and `VB_STRIDE` -- the normal
screen -- regardless of what had been opened.

Both are the same shape of bug, and both are the argument for running a
conformance suite at more than one configuration.

## And one from a user

Change the desktop's colour and it was gone at the next boot.
Confirmed, and it was exactly that: *Set preferences...* wrote the
chosen pattern and colour straight into `G.g_screen` and nothing wrote
them down, so the choice lived until the machine did.

The donor's `#Q` line carries it, and this is that line with gem4xe's
pairs rather than its three -- a desk byte and a window byte **per
screen**, because this binary drives two of them.
