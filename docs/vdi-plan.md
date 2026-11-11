# The VDI after NVDI: what is wrong, slow or missing

Status: **step 1 built** -- [phase 142](phase142.md): `vro_cpyfm`'s
sixteen modes on every device, `v_opnbm` refused and the face's name;
[phase 143](phase143.md): `vrt_cpyfm` into forms, `vr_trnfm`,
`v_bez_on`, and the page's erase colour.  Then [phase 144](phase144.md),
found while preparing step 2: the VDI's lazily taken far buffers were
the first caller's and went with it, and a contour fill on the page
never worked.  Step 2 built: [phase 145](phase145.md), text on the VBXE a
run at a time; [phase 146](phase146.md), ANTIC's text in assembler;
[phase 147](phase147.md), the logic modes by the blitter.  Step 3
under way: [phase 148](phase148.md), offscreen bitmaps on the VBXE;
[phase 149](phase149.md), the face at twice its size; [phase
150](phase150.md), the cookie jar.  Text effects and proportional faces
are left for later (2026-11-11); step 4 is next.  Planned 2026-11-10.  The question (2026-11-09): "We know that
NVDI sped up a lot of the VDI calls, but since we don't/won't have NVDI
to load for or emuTOS port.  What optimizations and capabilities are we
missing that we should implement?"  The answer was given then; this is
the plan to build it, in the order agreed -- "go through them in order":
what draws the wrong thing first, then speed, then what is not there.

gem4xe's VDI answers every one of the 71 opcode slots DRI's driver had
(docs/api.md), but 66 have real handlers, and several of those do less
than the call asks -- quietly, which is worse than not at all, because
a program cannot tell.  NVDI's lesson is that the VDI is the floor
every GEM program stands on: a correct, fast VDI makes every program
better at once.

## Where it stands (surveyed 2026-11-10)

| | today | NVDI / EmuTOS |
|---|---|---|
| `vro_cpyfm` (109) | modes 3 (replace) and 7 (OR, VBXE from memory only); the other 14 copy as replace; ANTIC and the printer ignore OR | all 16 logic modes, every device |
| `vrt_cpyfm` (121) | the destination MFDB is not read: always the screen; ANTIC and the printer see two colours | any destination, both colours |
| `vr_trnfm` (110) | an empty function | standard <-> device format |
| `v_opnbm` / `v_clsbm` | not refused: opens an ordinary workstation on the screen | offscreen bitmaps (NVDI, EmuTOS) |
| Bezier (`v_bez`, `v_bez_fill`, `v_bez_on`) | the control points drawn as a polyline | flattened curves (GDOS/NVDI) |
| `v_escape` (5) | empty for every escape | the cursor escapes, at least the queries |
| fonts | the built-in face and one loaded SYSTEM.FNT, monospace, one size; "8x8" named on ANTIC's 6x6 | many faces and sizes, `vqt_ext_name` |
| `vst_effects` | bold and underline; light, italic, outline, shadow dropped | all six |
| text on the VBXE | a fill, then one blit (or two) per character | a string at a time |
| text on ANTIC | `antic_text` in C, a row at a time | assembler |
| cookie jar | none: `Getcookie` always says not found | `_VDO`, `_CPU`, `NVDI`... |

## The steps

Each is a phase with its gate, and each gate is seen to fail first.

1. **What draws the wrong thing.**
   - `vro_cpyfm`: all 16 modes, on every device.  *Built in phase 142
     on the CPU, a row at a time on the VBXE and a pixel at a time on
     ANTIC and the printer, for every pair of forms.*  The VBXE
     blitter's AND, OR and XOR modes -- NOT S from its XOR mask, NOT D a
     complementing pass, 0 and 15 as fills -- moved to step 2, as speed.
   - `vrt_cpyfm`: its destination MFDB honoured; both colours on ANTIC.
   - `vr_trnfm`: standard format (planes, one after another) to the
     device's (4-bit chunky on the VBXE, one plane on ANTIC) and back.
   - `v_opnbm`: refused cleanly -- handle 0 -- until step 3 builds it, so
     a program that asks can fall back as it would on TOS.
   - Bezier: `v_bez_on` answers 0, "not available", so a program draws
     its own.  *Phase 143 kept `v_bez`'s polyline of points: TOS without
     a GDOS draws the same, its `v_pline` ignoring the sub-function.*
   - The font's name says what it is on each screen.
   *Gate*: a conformance program -- like test-m3's, which already runs
   258 cases over three screen widths -- draws each mode and each call
   and the picture is compared with a model written from the TOS VDI's
   definitions (tools/vdiref.py), on ANTIC and the VBXE.

2. **Speed.**
   - Text on the VBXE a string at a time: the string's glyphs drawn into
     one 1-bit buffer and that buffer put on the screen as one masked
     raster, where today a character is a blit or two.
   - ANTIC's `antic_text` and `an_pack6` in assembler.
   - The VBXE blitter for `vro_cpyfm`'s logic modes between screen
     rectangles, one or two passes each, where phase 142 goes a row at a
     time on the CPU.
   *Gate*: `make g4bench` and docs/bench.md's text rows, before and
   after, with the conformance gate's pictures unchanged.

3. **What is not there.**
   - Offscreen bitmaps: `v_opnbm` / `v_clsbm` -- a workstation that draws
     into far memory -- which is what a paint program and smooth redraw
     both want (g4paint draws its own).
   - Font sizes: the built-in faces at twice their size, `vst_height`
     and `vst_point` choosing, `vqt_ext_name`.
   - Text effects: light, italic (skew), outline, shadow.
   - Proportional widths, from a GDOS font's offset table.
   - A cookie jar the kit's `Getcookie` reads: `_VDO`, `_CPU`, `_MCH`,
     and gem4xe's own, and never an `NVDI` it is not.
   *Gate*: each in the conformance program; a cookie test beside m58's.

4. **The two documents that went stale.**  docs/differences.md says
   gem4xe is single-tasking (phase 129 made it switch programs), that a
   module's header is inside it (phase 133 moved it), that no face can
   be loaded, and counts the VDI's handlers wrongly; docs/bench.md's
   tables are from September, before the odd-x path, the one-block
   glyph and the shift-and-add row address.  Both brought back to what
   the code does, with the numbers measured again.

## Decisions

- **The conformance model is written from the TOS VDI's definitions,
  not from gem4xe's code**, as tools/vdiref.py already is: a model
  written from the target agrees with the target when both are wrong.
- **Step 1 before step 2.**  A faster wrong answer is still wrong, and
  the conformance gate step 1 builds is what step 2's speed-ups are
  checked against.
- **No NVDI emulation.**  gem4xe answers what it does and never claims a
  cookie for software it is not.

## Risks

- Bank $00: the VDI's tables live there, and LoRAM is at its floor.  New
  state goes far, as the control panel's did.
- The VBXE blitter's NOT D pass doubles the cost of the modes that need
  it -- rare ones (2, 8-11, 14) -- and the common ones stay one pass.
- Offscreen bitmaps cost far memory per workstation; on a machine with
  three banks that is the boot's room (phase 139).
