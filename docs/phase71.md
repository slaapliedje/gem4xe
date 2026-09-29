# Phase 71 -- GRAPHICS 8's full 192 lines, and a DOS command kept off the screen

## 192 lines

The ANTIC screen was 320x168, and the limit was memory, never ANTIC
(`src/antic/antic.h`).  GRAPHICS 8's full height needs 7,680 bytes; from
$8100 that ends at $9EFF, 768 bytes past the $9BFF the tree reserved.
Those 768 bytes are the OS's text screen under a cartridge (SDX, or
gem4xe's own; MEMTOP $9C1F), or plain RAM with none, the screen then
sitting under $C000.  Nothing writes to the OS's screen while GEM runs
-- GEM draws on its own display list, and a DOS command's output is
captured -- and when GEM quits it reopens E:, so the OS builds its screen
again.  The display list grows to 202 bytes and still fits $8000-$80FF;
the 4 KB boundary still falls between lines 95 and 96, and the screen
ends before the next one.  On a Rapidus the 16 KB block from $8000 was
already kept on the slow bus for ANTIC.

`AN_H` in `src/antic/antic.h` and `tools/anticref.py` is the change; all
three ANTIC gates follow it (m25 compares 61,440 pixels).  G4BENCH's
ANTIC vertical and diagonal lines are 13-16% longer on the taller
window, and the reference was rewritten for that alone.

## A DOS command's memory stops below the display list on ANTIC

File -> DOS command gives a SpartaDOS X command the memory from the
pool's cursor to MEMTOP, $9C1F -- written for the VBXE machine, where
$8000-$9BFF is free once the MEMAC window is closed (`src/sys/dos.c`).
On an ANTIC machine that is the display list and the framebuffer ANTIC
is showing.  A 0.9 tester's ANTIC machine went to a black screen and
stopped on a DOS command, which is what an overwritten display list
looks like.  MEMTOP is now held below $8000 for the command when the
screen is ours (the OS's list shadow, $0230, says so).

**Not reproduced**: VER, DIR and CHKDSK ran on the emulated Rapidus's
ANTIC screen before the change and after, the list untouched -- they
fit in what the pool has free.  So this closes a door that was open
rather than being proven to be the one the tester's machine went
through; their setup (an Antonia 2, SDX from U1MB, accessories loaded)
is what would tell.
