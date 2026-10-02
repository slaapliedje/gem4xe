# Phase 93 -- the polygon filler's scan line

Item 2 of `roadmap-0.12.md`: filled circles, ellipses, polygons and
rounded boxes.  They all end in the same place, `clc_flit` in
`src/vdi/vdi.c`, which fills a polygon a scan line at a time: for each
line, every edge is tested, each one the line crosses gives an x, and
the xs are sorted and filled in pairs.

## Where a circle went

`tests/emu/bench_vdi.py --by-function circle` (a filled circle of radius
60 on VBXE, machine cycles a call, from the 0.11 build):

| | cycles | |
|---|---|---|
| `_UDivMod32` | 54,000 | the crossing's divide |
| `polygon` | 43,000 | the edge test, inlined |
| `_Mul32` | 39,000 | the crossing's multiply |
| `vram_write` + `vbd_line_diag` | 49,000 | the outline |

A third of a filled circle was one 32-bit multiply and one 32-bit divide
per crossing.  The donor computes the crossing as `(int32)t * dx / dy`,
and the compiler calls its general routines for both.

## The small case

When every point of the polygon is within +-16383, which is every
polygon the AES and the desktop draw and any a program draws on the
screen, nothing in that arithmetic can overflow:

- the edge test, whose sign trick is there for overflow, is just
  y1 <= y < y2 (or y2 <= y < y1);
- on an edge the line crosses, |t| <= |dy|, so t * dx / dy is at most
  |dx| <= 65532: a 16-bit quotient of a 32-bit product of two 16-bit
  numbers;
- and it is never negative.  It is measured from the end with the
  smaller x, whichever way the edge runs.

`clc_flit` checks the points once.  For a small polygon it calls
`flit_scan` in `src/sys/muldiv.s` for each line.  That routine is the
edge test and the crossing in assembly: a shift-and-add multiply and a
sixteen-step divide in place of the library's calls.  It also does the
edge test with plain compares, where the compiler kept every variable on
the stack and fixed up every signed compare for an overflow that cannot
happen.  Anything larger takes the donor's code as it was.  The
crossings are the same numbers in the same order, so the `MAX_INTERSECT`
cut-off falls in the same place.

## Proof

- `make test-m3`: all 273 VDI cases, the polygons and curves among them,
  pixel for pixel against `tools/vdiref.py`.  Dropping one term of the
  first version's sign arithmetic turned 24 of them red.
- `tests/host/test_muldiv.py`, in the vendor's simulator:
  - `umuldiv` against Python on 3,280 quotients;
  - `flit_scan` against `flit_ref`, the C loop it replaced, on 1,458
    scan lines of random polygons (some points far off the screen);
  - a zigzag that crosses one line 70 times, where `MAX_INTERSECT`
    keeps 32.

  Letting one crossing too many through, or dropping the `+ 1` before
  the halving, fails it.  It also holds the assembly's copy of
  `MAX_INTERSECT` to `vdi.c`'s.

## On the way

- **The vendor's simulator decodes `BRL` with an 8-bit displacement.**
  The assembler's bytes are right (`--list-file` shows them).  The long
  branches in `muldiv.s` are `jmp .kbank`, which is what the compiler
  emits and a cycle cheaper.
- `bench_vdi.py` waited a fixed 200 frames for its runner, which had
  outgrown them.  It now polls for the ready stage, as m3 does.  It has
  circle, ellipse and rounded-box cases.
- It costs GEM.COM one sector of the DOS 2 floppy (14 free; the gate's
  ANTIC floppy has 2).

## What it bought

G4BENCH, ms a call:

| | VBXE | ANTIC |
|---|---|---|
| filled circles | 106.4 -> 69.3 (-35%) | 86.8 -> 48.8 (-44%) |
| filled ellipses | 84.1 -> 56.5 (-33%) | 72.1 -> 43.8 (-39%) |
| polygons | 67.9 -> 43.7 (-36%) | 52.5 -> 27.8 (-47%) |
| rounded boxes | 54.2 -> 36.8 (-32%) | 39.9 -> 22.6 (-43%) |

## What is left

The bench's circle is now 97.5 ms, and the scan is still 37,500 cycles
of it.  About half is the multiply and divide for each crossing, and
half is testing every edge on every line, which a circle's 60-odd edges
make 7,000 tests.  Going through each edge once instead -- every line it
crosses, its x stepped by a quotient and a remainder rather than divided
-- would remove most of both.  It needs somewhere to keep each line's
crossings, and bank $00 has no room for that.  The outline (49,000) is
pixels through the slow bus, and is the other half of what remains.
