# The Rapidus's 4 KB cache, and what no gate here can tell us

Asked because `src/sys/blkmove.s` writes an MVN instruction into RAM and
then executes it, and a cache that held a stale copy of those four bytes
would run the previous move's banks.  The answer turned out to be
reassuring about that and **worrying about something larger**.

---

## 1. What the cache is

The Rapidus's register file in bank `$FF` carries, at `$FF0082`, the
**SDRAM Control Register**.  Its D7 is *"SDRAM 4K cache (1 = disabled,
0 = enabled)"*.

The word that matters is **SDRAM**.  The board has two kinds of memory
and they are not treated alike:

| | banks | cached |
|---|---|---|
| windowed SRAM over the Atari's own space | `$00` | no |
| SRAM | `$01`-`$07` (512 KB card) or `$01`-`$0F` (1 MB) | no |
| SDRAM | `$08`-`$EF` -- `$080000`-`$EFFFFF` | **yes** |

`src/sys/farmem.h` already carried that map; what is new here is that
only the bottom of it is uncached.

**Source and its weight:** this is read out of Altirra's Rapidus
emulation, which is the best description of the board available -- no
public Rapidus register documentation exists.  It is second-hand and
should be treated as such.

## 2. No gate here can answer a cache question

`source/rapidus.cpp` mentions the cache **once**, in the comment quoted
above.  Writing `$FF0082` stores the value and updates the banking
window; there is no cache, no line, no invalidation.

So a test run under AltirraSDL passes whether the hardware is coherent
or not.  **A green gate would mean nothing at all** -- which is this
project's oldest failure shape wearing a new hat, and the reason this is
a document rather than a test.

## 3. The stub is fine

`blk_stub` lives in `zdata`, which the small data model puts in bank
`$00`: the windowed SRAM, not behind the SDRAM cache.  The hazard that
prompted the question **does not arise as the code is written**.

It would arise if the stub ever moved into far memory above bank `$07`,
so that is worth not doing quietly.

## 4. The larger thing

**gem4xe writes a program's relocated code into the far heap and then
jumps to it.**  That is write-then-execute, it happens on every launch,
and it is not confined to SRAM:

    far brk with the desktop up          $074DB8
    SDRAM begins                         $080000
    SRAM headroom                        45,640 bytes

Any application whose far image is larger than that has its code
**above the boundary, in cached memory**.  GACS's engine is about
111,000 bytes; `test-m31`'s fixture is 101,536.  Both cross it.

Whether that matters depends on questions nobody here has answered:

- Is the cache an instruction cache, a data cache, or unified?
- Does a write invalidate the line, or is it write-around?
- Is it flushed on a long jump, an interrupt, a bank change -- or never?

**gem4xe has run on real hardware** since 2026-09-13, so it is not
broken in any obvious way; but what has been launched there is the
desktop and small programs, all of which fit under `$080000`.  The
crossing case has been exercised only under an emulator that models no
cache.

`test-boot` now prints the headroom on every run, so the day the product
crosses the line, the line says so.

## 5. Two experiments, both needing the real board

**(a) Does write-then-execute work above `$080000`?**  Write a small
routine into SDRAM, call it, check its answer; overwrite the same
address with a routine that answers differently, call it again, check.
Repeat tightly.  A stale cache gives the first answer twice.  Run it
with D7 of `$FF0082` clear and again with it set -- if the two disagree,
the cache is the difference and the bit is the mitigation.

**(b) Where does SRAM actually end on this board?**  Altirra hardcodes
the 512 KB layout (`$01`-`$07`), but the comment beside it says a 1 MB
card reaches `$0F`.  On a **1 MB card the boundary is `$100000`** and
everything above is half a megabyte further away -- gem4xe would be
comfortably inside SRAM and most of section 4 evaporates.

The emulator cannot find the boundary by timing: it models both as
fast-bus with no difference.  **Real hardware may well show a step**, so
timing a read loop across banks `$06`-`$0A` on the board would both size
the SRAM and locate the cache.

## 6. What to do meanwhile

- **Keep the far heap under `$080000`** where it is free to do so, which
  is the standing "stay in the first 1 MB" preference anyway -- now with
  a second reason that is not about speed.
- **Do not move `blk_stub`** out of bank `$00`.
- Treat `$FF0082` D7 as the escape hatch: if write-then-execute turns
  out to be unsafe in SDRAM, disabling the cache costs speed and nothing
  else.
- And do not write a gate that appears to test any of this.  It would be
  green on the only machine that can run it.
