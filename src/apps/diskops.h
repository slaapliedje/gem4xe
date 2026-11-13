/* diskops.h -- what DISKUTIL and DUP both do to whole disks: format one
 * with a file system, copy one, make one boot G4DOS (docs/disk-plan.md,
 * part two step 1).  Through phase 155's Dgeom, Dformat and Drwsec and
 * phase 156's mkfs.c.  The program says what is happening and asks for a
 * disk to be swapped through the hooks: DISKUTIL with its status line and
 * alerts, DUP with lines of text.
 */
#ifndef GEM4XE_DISKOPS_H
#define GEM4XE_DISKOPS_H

#include "gem.h"

/* What the hooks are told. */
#define DK_FORMAT   0       /* stage: formatting `drive` */
#define DK_LAY      1       /* ...laying its file system */
#define DK_SYSTEM   2       /* ...putting G4DOS on it */
#define DK_READ     3       /* ...reading the source */
#define DK_WRITE    4       /* ...writing the destination */
#define DK_SOURCE   0       /* swap: the source disk wanted in `drive` */
#define DK_DEST     1       /* ...the destination disk */

typedef struct {
    void (*stage)(WORD what, WORD drive);
    void (*step)(UWORD done, UWORD total);  /* sectors, for a bar */
    WORD (*swap)(WORD which, WORD drive);   /* FALSE stops the copy */
} DK_HOOKS;

/* The errors of its own, beside GEMDOS's, the BIOS's and mkfs.h's. */
#define DK_ESHAPE   (-80L)  /* the source has no floppy's shape */
#define DK_ESTOP    (-81L)  /* the person stopped a copy at a swap */

/* The density a disk of this shape is, DF_SD to DF_DSDD; 0 for none. */
WORD dk_density(UWORD secsize, UWORD sectors);

/* A drive in `map` (bit 0 D1:), not `not`, with G4DOS.SYS and SHELL.SYS
 * in its root, to make a disk bootable from: 0 when there is none. */
WORD dk_system(UWORD map, WORD not);

/* The disk in `d` formatted at `dens` (DF_ASIS to DF_DSDD), DOS 2's file
 * system on it if `dos2`, else SDFS called `label`, and G4DOS put on it
 * from drive `boot` unless that is 0.  The free bytes into *free; 0, or
 * the error. */
LONG dk_format(const DK_HOOKS *h, WORD d, WORD dens, WORD dos2,
               const char *label, WORD boot, uint32_t *free);

/* G4DOS put on the SDFS disk already in `d`, from drive `boot`: DUP's
 * Write DOS files.  0, EUNDEV when the disk is not SDFS, or the error. */
LONG dk_bootable(WORD d, WORD boot);

/* The disk in `src` asked its shape, for the caller to say before it
 * copies: 0 with *secsize and *sectors, DK_ESHAPE for none a floppy has,
 * or the error. */
LONG dk_shape(WORD src, UWORD *secsize, UWORD *sectors);

/* The disk in `src` copied onto the one in `dst` -- `dst` formatted to
 * the source's shape first when it has another -- through as much far
 * memory as there is; on one drive, asking through h->swap for each disk
 * in turn.  0, or the error. */
LONG dk_copy(const DK_HOOKS *h, WORD src, WORD dst);

#endif
