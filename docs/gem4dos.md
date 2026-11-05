# gem4dos: gem4xe on FreeDOS -- the scope

Status: **scoped 2026-11-04, nothing built.**  This records what was
measured, what carries over, what is new, the order to build it in, and the
decisions that are the project's to make.

## Why

RetroWP wants a GUI on DOS.  Today its DOS build is text mode (80x25,
Open Watcom, 16-bit large model, 8086).  Its GEM backend -- RetroWP's
`platform/atari/app_shell.c` and retroplat's `dialog_`, `draw_` and
`metrics_atari.c` -- already serves two machines: the ST, and gem4xe, where
the same three files are shared unchanged and only the file, memory,
clipboard, transport and timer files are swapped.  A GEM on DOS makes DOS
the third: the GEM backend recompiled with Open Watcom against a DOS
`gem.h`, the pattern the gem4xe build already follows.

Windows 3.1 is not wanted.  FreeGEM/OpenGEM was ruled out earlier as too
old, and RetroWP's GEM backend is written against the Atari AES that gem4xe
implements (79 of 79 AES and 71 of 71 VDI opcodes, docs/api.md), not
PC GEM/3's.

## What was measured

**gem4xe's C compiles with Open Watcom almost as it is.**  Every system C
file (78, 47,912 lines, the same set `tools/bsp6502/survey.sh` compiles on
the 6502 branch) through `wcc -za99 -mm -0 -bt=dos`, with an Open Watcom
block in `portab.h`:

| | files clean | errors |
|---|---|---|
| as it is | 67 of 78 | 110 |
| variables named `near` and `far` renamed, `SAVEDS` after the return type | **72 of 78** | 14 |

`near` and `far` are keywords in Watcom C, and gem4xe has variables called
both (`gemdos.c`, `app.c`, `shel.c`, `rsrc.c`); the renames are harmless to
Calypsi and belong on master.  The six left are the control-panel module
interface (`CPXINFO` declared twice, in `cpxmain.c`, `color.c`,
`general.c`), Calypsi's own C-library glue in the kit (`gemstub.c`,
`gemstat.c`, which a DOS kit replaces anyway), and one array bound in
`vdi.c:1417` that Watcom does not accept as a constant.

**Watcom names 32 places where a far pointer is cut to a near one** (W112):
object trees in `alert.c`, `fsel.c`, `menu.c`; rectangle lists in
`wind.c`; resource words in `rsrc.c`; and parameters.  Calypsi accepts all
of them silently.  On the 65C816 each is right only if the object is in
bank $00; on DOS only if it is in the data segment.  So a Watcom build is
also a check of gem4xe's own far/near discipline, the defect class of
`far-address-in-a-near-slot`.

**gcc-ia16 is stricter, and its errors are mostly that check.**  The same
78 files through `ia16-elf-gcc -mcmodel=medium -march=i8086 -Os`, with no
`portab.h` block yet: 51 compile clean, 54 errors, 39 warnings.  Three
groups and a stray:

| errors | files | what |
|---|---|---|
| 21 | 21 | newlib's `<sys/reent.h>` breaks on something gem4xe's headers define before `<string.h>`: one cause, and a freestanding build includes no newlib at all |
| 21 | `alert.c`, `rsrc.c`, `color.c`, `edit.c`, `gemarc.c`, `general.c` | **a far pointer passed where a near one is declared** -- object trees to `objc_draw`, `form_do`, `form_center`, `objc_offset`; strings to `form_alert`, `fsel_exinput`, `scpy` -- an ERROR in gcc-ia16 (its `__far` is a named address space), a warning in Watcom, nothing in Calypsi |
| 11 | `gemlib.c` | a far address in a static initialiser, which a medium-model segment cannot be until load time |
| 1 | the kit | `calypsi/stubs.h`, Calypsi's own |

So the two compilers find the truncations differently -- Watcom in the
system, gcc-ia16 in the applications and the kit's bindings -- and
between them they cover more than either.

**The machines agree where it matters.**  Calypsi and 16-bit Watcom both
have a 16-bit `int`, both are little-endian, and both have near and far
data: Watcom's medium model (far code, near data in one 64 KB group,
`__far` for the rest) is gem4xe's `--code-model=large --data-model=small`.
`SAVEDS` is Watcom's `__loadds`.  A far pointer's arithmetic is 16 bits on
both, so `farmem.c`'s rule -- no block crosses a bank -- becomes the same
rule for a segment.  A 32-bit DOS extender would agree on none of this, and
RetroWP's DOS build is 16-bit already.

**No AES or VDI code has met a second compiler before.**  The host builds
are `sdfs.c`, `doscmd.c`, `edbuf.c` and the ARC codec; the rest is tested
under Calypsi, in its simulator or on the machine.

## What carries over and what is new

gem4xe is 54,000 lines of C and 8,322 of 65C816 assembly.

| Layer | gem4xe | gem4dos |
|---|---|---|
| AES, `src/aes` (11,900) | | **as it is**, but for the five files that call CIO directly (`fsel`, `lang`, `rsrc`, `scrap`, `shel`) |
| VDI above the device seam (`vdi.c`, fonts, fill patterns) | | **as it is**; `font.c` and `emit.c` also call CIO |
| Display | `dev_vbxe.c`, `dev_antic.c` behind `vdidev.h`'s `VDIDEV` table | **new `dev_vga.c`**: mode 12h, 640x480, 16 colours, planar, through the VGA's write modes; the ANTIC and printer devices, all software, are the shape to follow |
| Printer | `dev_print.c` + `emit.c` (PCL, PostScript) | as it is, writing to a file or `PRN` |
| Desktop, apps | ordinary programs against the kit | rebuilt against a DOS kit |
| Pointer | `pointer.c`: quadrature, tablets | INT 33h (CuteMouse on FreeDOS) |
| Keyboard | `vdi.c` ~2307-2560: POKEY to ST scan codes | INT 16h: PC scan codes are the ST's, nearly (RetroWP's dos-platform.md) |
| Timer | VBI frame count, POKEY timer 1 at ~4 kHz | INT 08h, the PIT sped up and the BIOS's 18.2 Hz chained |
| GEMDOS (`gemdos.c` 2,872, on CIO) | | **mostly not needed**: programs call DOS (INT 21h) themselves, as PC GEM programs did; the system's own files go through a small file seam (below) on INT 21h |
| Far heap | `farmem.c` over Rapidus banks | the same allocator over DOS memory blocks (INT 21h 48h) |
| System call | `COP $41/$56/$44`, X:C = parameter block | **INT EFh, DS:DX = parameter block, CX = 200 (AES) / 473 (VDI)**: PC GEM's own convention, with `abi.c`'s copy-in/copy-out as it is |
| Loader | `.G4A`, `app.c` | DOS EXEC (INT 21h 4Bh); programs are `.EXE` |
| Accessories | `ctx.c`, one stack | later |
| Boot | `crt_atari.s`, `farload.s`, G4DOS | `GEM.EXE` under FreeDOS |
| 65C816 assembly | 8,322 lines | **none of it**; new x86 is the interrupt hooks, the INT EFh entry and the start-up -- a few hundred lines -- and fast blits later |

New code, roughly: the VGA device ~1,500 lines (about `dev_vbxe.c`'s size),
input and timer ~400, the file seam and DOS layer ~600, the entry and
loader ~500, x86 assembly ~400, and the kit adapted.  Against ~45,000
lines reused.

**The file seam** is the one refactor gem4xe itself gains from: today the
AES and VDI reach CIO in seven files.  Routing them through `sys_open`,
`sys_read`, `sys_close`, `sys_search` (or what the code already calls them)
on master, implemented on CIO there and on INT 21h here, leaves one place
per machine that knows how files are read.

## Decisions (recommendations; the project's to make)

1. **The machine.** VGA mode 12h on any x86: the 8086 instruction set,
   real mode, 640 KB, a mouse driver -- the floor RetroWP's DOS build
   already has, with VGA in place of text mode.  EGA 640x350x16 is the same
   planar code with fewer lines, a cheap second device; CGA and Hercules
   are 1-bit devices of `dev_antic.c`'s shape, later if wanted; VESA
   256-colour, later if wanted.
2. **Where it lives.** A `dos` branch of gem4xe in its own worktree, as
   the 6502 port is (`6502`, `~/dev/gem4xe-6502`); what is good for both --
   the renames, the file seam, the truncation audit -- goes to master.
3. **PC GEM/3 programs.** Use PC GEM's INT EFh convention so that running
   them stays possible (GEM Paint, GEM Write, Ventura); do not build it.
   That is FreeGEM's job, and its AES differs from the Atari one.
4. **Licence.** Open Watcom's C library is under the Sybase Open Watcom
   Public License, which is not GPL-compatible.  Build the system the way
   the FreeDOS kernel is built with Watcom: freestanding, with its own
   start-up and gem4xe's own small C library, as gem4xe already does on the
   Atari to keep NuttX's Apache-2.0 library out.  (RetroWP's DOS build links
   Watcom's library today: a question for RetroWP, not for gem4dos.)
5. **Compilers: both, not one.**  Open Watcom and gcc-ia16 (GPL; medium
   model, `__far` pointers and far variables; built from tkchia's
   `build-ia16` into `~/dev/toolchains/build-ia16/prefix`) each build the
   tree, through their own blocks in `portab.h`, and each one's warnings
   are findings for master -- a second compiler is how bad code is found
   (Watcom's 32 truncations above).  Which one builds the releases is
   decided when both run.

## The steps

Each says how it is tested; as everywhere in gem4xe, a check is believed
only once it has been seen to fail.

0. **The survey, made real.**  Blocks in `portab.h` for Open Watcom and
   gcc-ia16, `tools/bspdos/survey.sh` beside the 6502 one running both, the
   `near`/`far` renames on master, `CPXINFO` and `vdi.c:1417` fixed.
   *Gate*: 78 of 78 compile with each; every warning either compiler gives
   (Watcom's 32 truncations and gcc-ia16's 21 first) fixed or shown to
   point into bank $00 / the data segment.
1. **The file seam, on master.**  *Gate*: gem4xe's own suite, unchanged.
2. **GEM.EXE draws.**  Freestanding, medium model, mode 12h, `dev_vga.c`,
   the VDI with no AES.  *Gate*: the VDI conformance cases `make test-m3`
   runs on the VBXE (258 of them), run under QEMU with FreeDOS and held to
   `tools/vdiref.py` -- QEMU's monitor takes a `screendump` by script.
3. **Input and the AES.**  Mouse, keyboard, timer; the desktop linked in.
   *Gate*: the desktop's gates against `tools/aesref.py` and
   `deskref.py`, driven through QEMU's `sendkey`, `mouse_move` and
   `mouse_button`.  Measure memory here (risks, below).
4. **Programs.**  The INT EFh entry, EXEC, and a DOS kit: `gem.h`,
   `gemlib.c` with an INT stub in place of `COP`, start-up, large model.
   *Gate*: EDIT and CALC from `src/apps`, run from the desktop.
5. **RetroWP in GEM.**  A third branch in its `gemcompat.h`, the DOS
   `gem.h`, `file_`, `mem_` and `transport_dos.c` as they are, a timer on
   `evnt_timer` (`timer_dos.c` busy-waits), the clipboard through the
   scrap, and its planar image blit ported.  *Gate*: RetroWP's DOSBox CI,
   now in GEM.
6. **Later:** accessories; EGA, CGA, Hercules, VESA devices; the printer;
   real hardware; PC GEM/3 programs.

## Risks

- **640 KB.**  gem4xe's far code is ~146 KB on the 65C816, its near data
  64 KB; RetroWP's DOS `.EXE` is 213 KB today.  FreeDOS loaded high leaves
  about 600 KB.  It should fit with the desktop unloaded while a program
  runs, as gem4xe does; measured at step 3, with overlays and EMS/XMS for
  the far heap as the fallbacks.
- **A second compiler's defects.**  Watcom will have its own; gem4xe's
  Calypsi workarounds (tools/ccbug) are harmless under it.
- **Speed.**  Planar VGA drawn a pixel at a time is slow on a 286.  GEM/3
  ran on an 8088 with an EGA because its drivers used the card's write
  modes and latches, so `dev_vga.c` must too.

## References

- **PC GEM/3's source, GPL-2**: `ref/gemworld/gemfull/GEM/MRS/GEM3X/`
  (`license.txt`; `ref/` is not in git).  `SCREENDR` has EGA 16-colour,
  EGA mono, CGA and Hercules drivers in 8086 assembly -- mode 12h is EGA's
  planar layout with 480 lines, so `EGA16CLR` is the model for
  `dev_vga.c`.  GPL-2 like gem4xe, so it may be used, not only read.
- XM/GEM, GPL-2: `ref/gemworld/xmgem` (`docs/multitasking.md`).
- RetroWP: `docs/dos-platform.md`, `docs/gem4xe-port.md` (the AES rules a
  gem4dos must honour, learned on the ST); retroplat `backends/atari/`.
- Tools: Open Watcom 2.0 (`~/dev/toolchains/watcom`), QEMU, DOSBox,
  DOSBox-X; a FreeDOS 1.3 image to fetch.
