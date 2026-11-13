/* mkfs.h -- a blank file system laid on a disk DISKUTIL has just
 * formatted (docs/disk-plan.md, step 2).
 *
 * Portable C, as GemARC's engine is: DISKUTIL links it, and
 * tests/host/test_mkfs.py builds it with gcc (tests/host/mkfs_host.c) and
 * holds what it writes against tools/atr.py's formatters and a disk that
 * real MyDOS formatted.  The layouts are Altirra's disk explorer's
 * (src/ATIO/source/diskfssdx2.cpp and diskfsdos2.cpp, InitNew), which
 * reads and writes real disks.
 *
 * Only what is not zeros is written: a disk the drive has just formatted
 * is zeros, and a 1440-sector disk written whole would take minutes.  The
 * sector that says what the disk is -- SDFS's sector 1, DOS 2's VTOC --
 * is written last, so a format cut short is not taken for a disk.
 */
#ifndef GEM4XE_MKFS_H
#define GEM4XE_MKFS_H

#include <stdint.h>

/* Where a sector goes: `len` bytes of `buf` to sector `sec`, from 1.  0,
 * or a negative error, which ends the format with it. */
typedef int32_t (*MKFS_PUT)(void *ctx, uint16_t sec, const uint8_t *buf,
                            uint16_t len);

typedef struct {
    uint16_t secsize;       /* 128, 256 or 512 */
    uint16_t sectors;       /* how many the disk has */
    const uint8_t *bad;     /* the drive's bad sectors, as Dformat gives
                               them: words, low byte first, ending at
                               $FFFF; or 0 for none */
    const char *label;      /* SDFS: the volume's name, to 8; 0 for NEWDISK */
    uint16_t stamp;         /* SDFS: its serial number (low) and random ID
                               (high), by which SpartaDOS X tells one disk
                               from another */
    uint8_t *buf;           /* room for one sector, secsize bytes */
    MKFS_PUT put;
    void *ctx;
} MKFS;

#define MKFS_EGEOM  (-64)   /* no such file system on that geometry */
#define MKFS_EBAD   (-65)   /* a sector the file system's own is bad */

/* SpartaDOS's file system, G4DOS's and SpartaDOS X's, with folders: the
 * free sectors it leaves, or an error. */
int32_t mkfs_sdfs(const MKFS *m);

/* DOS 2's, chosen by the geometry as the DOSes divide it: DOS 2.0S on 720
 * sectors of 128 (720 itself unusable), DOS 2.5 on 1040 of 128 (a second
 * VTOC at 1024 for the upper half), MyDOS on anything else from 720 up
 * (more VTOC sectors, and extended links over 1023 sectors).  The free
 * sectors, or an error. */
int32_t mkfs_dos2(const MKFS *m);

#endif
