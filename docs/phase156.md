# Phase 156 -- the file systems DISKUTIL lays

Step 2 of `docs/disk-plan.md`.  Phase 155's `Dformat` leaves a disk
formatted and empty: sectors, and no file system.  `src/apps/mkfs.c`
lays one, two kinds:

| asked for | on | is |
|---|---|---|
| `mkfs_sdfs` | 128-, 256- or 512-byte sectors, any count | SpartaDOS's file system: G4DOS's and SpartaDOS X's, with folders |
| `mkfs_dos2` | 720 x 128 | DOS 2.0S, sector 720 unusable: what every DOS 2 reads |
| | 1040 x 128 | DOS 2.5's enhanced density, the upper half's bits in VTOC2 at 1024 |
| | 720 x 256, 1440 x 256, anything else from 720 | MyDOS: its VTOC grows down from 360 as the disk grows, and its code says how far |

The layouts are Altirra's disk explorer's (`diskfssdx2.cpp`,
`diskfsdos2.cpp`, InitNew and Flush), which reads and writes real disks.
Portable C, as GemARC's engine is.  The program links it, and the host
builds it with gcc for the test.  A sector goes out through a callback,
so on the Atari it is `Drwsec` and on the host a line of hex.

## What it writes, and in what order

Only what is not zeros.  A disk the drive has just formatted is zeros
already, and writing a 1440-sector disk whole would take minutes; the
double-sided SDFS is six sectors, the MyDOS one twelve.

The sector that makes a disk a disk goes last: SDFS's sector 1, DOS 2's
VTOC.  A format cut short (the drive refusing, a disk pulled out)
leaves something no DOS takes for a file system, rather than one whose
bitmap or directory never arrived.

Boot sectors:
- **SDFS**: Altirra's stub. The code is one RTS, and sectors 2-3 flag the
  boot failed.
- **DOS 2**: gem4xe's own, eight bytes. One sector loads, DOSINI points at
  an RTS, and the boot's code is SEC, RTS. The carry is the OS's word for a
  failed boot, so booting a data disk says BOOT ERROR instead of running
  zeros.

SpartaDOS X tells one disk from another by superblock bytes 38-39, the
volume's serial number and random ID.  The caller gives them; the next
step's program will make them from the clock and the name, as Altirra
does.

**A drive's bad sectors refuse both.** DOS 2's own FORMAT refuses such a
disk ("error 173, bad sectors at format time"), and a file system mapped
around a failing disk is not one to keep anything on.

## Three witnesses

`make test-mkfs`.  A writer and a model of it can agree and both be
wrong, so there are three:

1. **tools/atr.py's formatters, byte for byte**, wherever it has one:
   - SDFS on seven geometries, from 720 x 128 to 65,535 x 128;
   - DOS 2.0S;
   - DOS 2.5, by `atr.enhance`;
   - MyDOS on 720 x 256.
2. **A disk real MyDOS 4.50 formatted**, double-sided: its VTOC code 3,
   its 1,428 sectors to use, and every sector this keeps for itself kept
   there too.
3. **Altirra's InitNew read a third time**, in the test, for the MyDOS
   volumes atr.py cannot write: 943 sectors (code 2, one VTOC sector),
   944 (code 3, two), 2000 and 8192 of 128, 4000 of 256.

Each image is also read back with `Sdfs.check()` or `Dos2.free_count()`,
the free count agrees with what the call answered, and the last sector
written is the right one.

**The first run disagreed** in one sector of every SDFS: the root's
header named "MAIN" followed by three NULs where the C wrote spaces.
Altirra writes "MAIN" and seven spaces, and so does a real SpartaDOS 3.2
disk, the fixture.  `atr.py` was the one wrong: a blank entry's extension
is NULs, and its formatter never cleared it.  Fixed there, which changes
three bytes of every SDFS image the build makes.

| broken on purpose | result |
|---|---|
| the VTOC placed one sector high | DOS 2.0S and MyDOS's VTOC differ from atr.py's, the free count one more |
| the bitmap starting at the root's own sector | SDFS's bitmap differs, `Sdfs.check()` finds the root marked free |

Calypsi compiles it clean and `make qscan` reads it.  `make mscan`'s
checks reach it when step 3's program links it into the build.
