# Where gem4xe differs from an Atari ST and from EmuTOS

gem4xe's AES and VDI are EmuTOS's -- the Caldera-GPL Digital Research
sources -- carried onto a 65C816, so most of GEM behaves as it does on an
ST.  This page is the rest: what a person or a program coming from an ST,
or from EmuTOS, meets here.  Each entry names where the difference is
made, so it can be read rather than taken on trust;
`tests/host/test_docs.py` fails when a file or folder named here is gone.

What the system answers, call by call, is [`api.md`](api.md).  Porting a
program is the application kit's ["Porting from the
ST"](../tools/sdk/README.md#porting-from-the-st).

## The machine

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| CPU | 68000 | 65C816, native mode, 24-bit addresses.  **An ST program does not run**: it must be recompiled with the kit, and the loader refuses a 68000 `.PRG` | `src/sys/app.c` |
| Screen | ST low, medium, high; TT and Falcon modes | 640 x 240 in 16 colours on a VBXE (512 or 672 wide, 200 or 224 tall, by `GEM4XE.CFG`), or 320 x 192 in 2 on ANTIC.  Pixels are about twice as tall as they are wide.  `appl_getinfo(AES_SYSTEM)` answers -1 for the resolution number: there is no `Getrez` value for these | `src/vdi/dev_vbxe.c`, `src/vdi/dev_antic.c`, `src/aes/appl.c` |
| Screen memory | a program may write it | **not reachable**: the VBXE's memory is not in the CPU's map.  Drawing is through the VDI only, and a device-specific form is 4-bit **chunky**, not interleaved planes | `src/vdi/vdi.c` |
| BIOS, XBIOS, line-A | there | **none**: a program reaches the machine through the VDI, the AES and GEMDOS only.  No cookie jar (`Getcookie` answers not found), no system variables, no `_hz_200` | `src/sys/abi.c` |
| Supervisor mode | `Super` switches to it | there is no user mode to leave: `Super(1L)` answers -1, as TOS answers a supervisor, and nothing else changes | `src/sys/gemdos.c` |
| Pointer | the ST mouse | an ST or Amiga mouse on a joystick-port adapter, a CX80 trak-ball, a CX77 or KoalaPad tablet, or a mouSTer; `MOUSE=` in `GEM4XE.CFG` | `src/vdi/pointer.h` |
| Keyboard | the ST's | the Atari's, sending **the ST's scan codes** for every key the two share, with the SHIFT and CONTROL it was pressed with.  HELP, or a 1200XL's F1, is the ST's Help; a 1200XL's F2 its Undo | `src/vdi/vdi.c` |

## Memory

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| A block | as large as free memory | **never crosses a 64 KB bank**, so `Malloc(-1)`, the largest block, is never more than 65,532 bytes however much is free.  A program that sizes its memory by `Malloc(-1)` needs telling (QED did) | `src/sys/gemdos.c`, `src/sys/farmem.c` |
| `Mxalloc` | ST RAM or TT RAM | one kind of memory: the mode is accepted and makes no difference | `src/sys/gemdos.c` |
| A program's own memory | its TPA | code in far banks of its own; a near region of a few KB taken from a **14 KB pool in bank `$00` shared by everything resident** -- the desktop, the accessories, the control panel modules.  Large data belongs in `Malloc`'d far memory | `src/sys/app.c`, [kit: "Your memory"](../tools/sdk/README.md#your-memory) |
| `malloc` | the C library's heap | refused at link time: use `Malloc` | `tools/sdk/README.md` |

## Programs and processes

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| Multitasking | single-tasking TOS; MultiTOS and MagiC multitask | single-tasking, as TOS: the desktop, one program, and the desk accessories | `src/aes/shel.c` |
| `Pexec` | load and go, load, go, create a basepage | mode 0, load and go, only; the environment is not passed | `src/sys/gemdos.c` |
| Desk accessories | `*.ACC` in the boot drive's root | `*.ACC` in the system's folder (`\GEM\`), loaded once at boot, as many as the pool has room for, up to the Desk menu's six | `src/aes/shel.c` |
| The AUTO folder | `\AUTO\` | `\GEM\AUTO\`.  `Ptermres` keeps all of a program or none of it, and a `.TTP` is not run from there | `src/aes/shel.c`, `tools/sdk/README.md` |
| Control panel modules | Atari's XCONTROL `.CPX` | gem4xe's own control panel and module interface, in the same shape; a module is built with the kit | `src/apps/cpanel.c`, `tools/sdk/cpx.c` |
| A DOS prompt | -- | `Psystem`, GEMDOS `0x1F0`, gem4xe's own: a command line run by SpartaDOS X, its output captured | `src/sys/gemdos.c` |

## Files and drives

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| Drive names | `A:` to `P:` | `A:` to `H:` to a program, which are **`D1:` to `D8:`** to a person: the desktop and the file selector show `D1:`, and `DESKINF=` takes either spelling | `src/sys/dos.c`, `src/desk/desktop.c` |
| The file system | FAT | the DOS's: SpartaDOS X, SpartaDOS 3.2 and MyDOS have folders; **DOS 2 has none**, and a path on it is its last component | `src/sys/dos.c` |
| Names | 8.3 | 8.3, upper case, by the DOS's own rules for which characters it takes | `src/sys/dos.c` |
| A folder's name | can be changed | **cannot**: the DOSes refuse to rename a directory, so Show info greys it | `src/desk/deskfun.c` |
| `Fattrib` | reads and sets | **sets** read-only (the DOS's lock) and **refuses a read**: a search answers what a read would | `src/sys/gemdos.c` |
| `Dfree` | the cluster count | what the DOS's directory listing says, at most 999 sectors; the disk's total is unknown | `src/sys/gemdos.c` |
| A name with no path | the current directory | the same -- and until a program has set one, the **DOS's own** current directory, where `GEM.COM` was started (phase 90) | `src/sys/gemdos.c` |
| `DESKTOP.INF` | the boot drive's root | beside `GEM4XE.CFG` (`\GEM\` on the product media), or where `DESKINF=` in `GEM4XE.CFG` says.  Its lines are the donor's with gem4xe's own (`#Q` is a pair per screen, `#M` a drive icon); `NEWDESK.INF` is not read | `src/desk/deskwin.c` |

## The AES

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| Version | 1.40 (TOS 1.04) to 4.x | **1.40** in `global[0]`, and all 79 opcodes of AES 4's set served, `menu_popup`, `menu_attach` and `appl_getinfo` among them -- ask with `appl_getinfo`, not the version | [`api.md`](api.md) |
| Window fields | the ST's | no `WF_COLOR` or `WF_DCOLOR`; `wind_get` does not answer `WF_KIND`, `WF_NAME` or `WF_INFO` | [`api.md`](api.md), `src/aes/wind.c` |
| Window position | any pixel | **x snaps to even**, because the blitter has no shifter: `wind_set(WF_CURRXYWH)` takes the snapped rectangle, and that is what `wind_get` answers | `src/aes/wind.c` |
| The 3D look | TOS 4 always; EmuTOS when built so | **off by default**, on in the control panel's General module.  With it on, dialogs and window frames are raised on **grey** grounds where TOS 4's default gadgets are white, and a text a dialog prints on its ground gets no edge.  `objc_sysvar` answers for the look in force | `src/aes/objc.c`, `src/aes/wind.c` |
| Colour icons | TOS 4 | drawn on the 16-colour screen, 4-plane forms up to 32 x 32; the mono form everywhere else | `src/aes/objc.c`, `src/aes/rsrc.c` |
| Flying dialogs | MagiC, some AES 4 | none: `form_do` takes the whole screen | `src/aes/appl.c` |
| `objc_sysvar` | AES 3.40's settings | the same, and `G4_3DLOOK` (100) and `G4_DESKICON` (101), gem4xe's own | `src/aes/objc.c` |
| `appl_getinfo` | subjects 0 to 14 | the same, and `AI_CPX` (64), gem4xe's own | `src/aes/appl.c` |

## The VDI

| | ST / EmuTOS | gem4xe | Where |
|---|---|---|---|
| Fonts | the system faces, GDOS faces | **one face**, the 8 x 8 system font (Atari's condensed 6 x 6 on ANTIC).  No GDOS: no face can be loaded, and a TEDINFO cannot name another.  A port's GDOS check should come out "none" -- the kit has no `vq_vgdos` | `src/vdi/vdi.c`, `src/vdi/dev_antic.c` |
| Raster copy | sixteen modes | `vro_cpyfm` does replace (3) and OR (7); every other mode copies as replace | `src/vdi/vdi.c` |
| Opcodes | -- | 71 served; five dispatch to nothing on purpose, as DRI's own driver did | [`api.md`](api.md) |
| The printer | GDOS's driver | a 640 x 800 graphics device writing PCL 5 or PostScript where `PRINTTO=` says (`PRINTER=` in `GEM4XE.CFG`); the desktop's Print sends a text file to `PRN:` as it is | `src/vdi/dev_print.c` |

## From EmuTOS in particular

gem4xe follows EmuTOS file by file -- each file's header names its donor
-- and departs from it where the machine or the purpose asks:

- **The desktop** is EmuTOS's in shape, with what it does on this
  machine: drives named `D1:` to `D8:`, a DOS command item, colour icons
  from `DESKICON.RSC`, and its layout file in its own folder.  Format is
  greyed.
- **The window manager** keeps EmuTOS's rectangle lists and frame, and
  blits a window that moves rather than redrawing it (`src/aes/wind.c`).
- **The 3D look** is EmuTOS's `CONF_WITH_3D_OBJECTS`, switched at run
  time rather than chosen at build time, on grey grounds.
- **The resource loader** reads the same files, and can put one in far
  memory, colour icons and all (`src/aes/rsrc.c`).
- **GEMDOS** is gem4xe's own, over the Atari DOSes, not EmuTOS's FAT
  file system (`src/sys/gemdos.c`).
