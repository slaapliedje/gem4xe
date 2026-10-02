# Phase 104 -- a dialog and a window, in fewer blits

Item 5 of `roadmap-0.12.md`: G4BENCH's "draw a dialog" (38 ms on the
VBXE, 45 on ANTIC) and "open and close a window" (74, 85), and the 3D
frame's cost on a window.

## Where the time went

The emulator's profiler, over exactly the 20 dialogs and then the 10
windows, counts machine cycles, so it measures time.

- **The dialog** is one `objc_draw` of five objects, and 60% of it was
  the VBXE's blit machinery: `vram_write`, writing each blit's control
  block into VRAM over the slow bus, then `bcb_common` and the RMW, fill
  and mask blits.  The cost is the number of blits.  A host trace of the
  VDI calls the model makes for that tree, which the AES makes too,
  found 13 rectangle outlines among 47 calls: 52 line blits out of about
  96.  A border `th` thick is `th` nested one-pixel outlines, four blits
  each, and a default button's is four outlines.
- **The window** made about 113 blit lists and 200 control blocks a
  round, and the AES's own CPU time was about a fifth of it.  9% of the
  total was the compiler's run-time `_Mul16`.  Counting the `jsl`s by
  their place in the profile found 150 calls a round from `&gl_win[h]`
  (the record is 54 bytes), 112 from `vwk_select` (once a VDI call, a
  `Vwk` index) and 32 from `just_draw`'s `-3 * th`.

## What changed

- **A thick border is four bars** (`gr_box`, `src/aes/graf.c`): the
  same pixels in four `vr_recfl`s, where it took four outlines a pixel
  of thickness.  This is used only in replace mode, where a pixel drawn
  twice is drawn once, and only when the innermost outline is a real
  box, because only then is the outlines' union the frame between the
  outer box and its hole.  The fill colour is left as the line colour.
  Everything after that sets its own, and XOR, the one fill that does
  not, ignores the pen.
- **The 2D title bar draws nothing when the window has a name**
  (`w_bldactive`).  Closer, name and fuller tile it, each drawing every
  pixel of its own box, so its outline and white fill were always
  painted over.  In 3D it stays, as the ground in the gaps.
- **No `_Mul16` on the hot paths.**
  - `w_win(h)` stands for `&gl_win[h]`, via `MUL_BY`, a shift-and-add
    expansion of `sizeof`.  It uses the sizeof the code sees, which is
    the stride.  A compile-time check on `sizeof(WINDOW)` failed: in a
    constant expression it is the padded size, B7 again, so the macro
    takes the size from the code and has no check.
  - `vwk_select` answers from the live workstation when the call names
    the current one, which is nearly every call.
  - `just_draw` adds `th` three times.
- **The pointer is hidden once a `draw_change`.**  The old top's frame
  was drawn rectangle by rectangle outside `w_update`'s own hide, each
  `ob_draw` hiding and showing the pointer, and saving the pixels under
  it, again: five times for one window opened, one now.

None of it changes a pixel, so `tools/aesref.py` is unchanged.

## Figures

G4BENCH, ms a call, against the 0.11 reference:

| | VBXE before | after | ANTIC before | after |
|---|---|---|---|---|
| draw a dialog | 37.5 | **26.0** (-31%) | 45.4 | **32.4** (-29%) |
| open and close a window | 73.8 | **61.5** (-17%) | 85.1 | **72.2** (-15%) |
| the same in 3D: a dialog | 37.4 | 26.1 | 45.4 | 32.3 |
| ...a window | 90.5 | **82.6** (-9%) | 106.3 | **98.7** (-7%) |

The 3D rows were measured with `gl_3d` poked on after boot.  G4BENCH
itself runs in 2D.  Every other G4BENCH test is the same or up to 5%
faster, from the `vwk_select` change.

`make bench-desk` counts whole frames, 20 ms each.  Unfull on the VBXE
went from 440 to 400 ms.  The rest is unchanged at that grain: open DISK
A takes 360 ms on the VBXE and 280 on ANTIC.

## What is left, and is not the AES's

In 3D a window round makes about 161 blit lists and 142 RMW control
blocks, against about 100 and 86 in 2D.  The extra is the one-pixel
bevel lines.  On the VBXE, a vertical one-pixel line, or the odd end of a
horizontal one, is an AND blit and an OR blit, because the blitter
writes bytes and a pixel is a nibble.  The VDI's line code is where the
3D frame's remaining cost lives.

## Proof

- `make test-m4` 17/17, `test-m7` 13/13, `test-m8` 17/17 (the 3D frame
  cases included), `test-m9` 7/7, `test-m17` PASS.
- **m4 speaks.**  With the side bars one pixel narrow, six of its cases
  fail.
- `make g4bench` passes against the reference.
- `make memcheck` ok.  GEM.COM is 166 bytes larger; the DOS 2 floppies
  have 111 and 99 sectors free.
