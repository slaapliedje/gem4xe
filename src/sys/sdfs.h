/* sdfs.h -- SDFS, the SpartaDOS file system, in C: GEMDOS's own file system
 * where the DOS is G4DOS (docs/sdfs-plan.md).
 *
 * Portable: the same sdfs.c runs on the Atari, inside GEM.COM, and on the
 * host, where tests/host/test_sdfs.py holds it to tools/atr.py.  It knows
 * nothing of GEMDOS or of CIO.  Below it, two functions the platform
 * gives it: a sector read or written (sd_dev) and the time (sd_now).
 *
 * ALL ITS STATE IS ONE BLOCK, an SDFS, that the caller allocates and hands
 * to every call: on the Atari a far block (bank $00 has nothing to spare,
 * src/gem4xe.scm), on the host anything.  Nothing in sdfs.c is static.
 *
 * PATHS are from the root of a unit, components between backslashes, the
 * way GEMDOS composes them: "" or "\" is the root, "\GEM\DESKTOP.INF" a
 * file in a folder.  A name is up to eight characters, a dot, up to three
 * -- letters, digits and the underscore, as SpartaDOS takes them --
 * matched without regard to case and stored in capitals.
 *
 * ERRORS are GEMDOS's numbers, negative; 0 or a count is success.
 *
 * WHAT IS WRITTEN is SDFS as tools/atr.py and G4DOS write it, and in the
 * same order, so that a RESET part way through leaves a disk SpartaDOS
 * will read: a file's first map page and its entry go down when it is
 * created; its data, then the map pages that name the data, then its
 * length, then the bitmap and the free count, when it is closed.  The
 * cache keeps that order when it has to write a sector early (sdfs.c).
 */
#ifndef GEM4XE_SDFS_H
#define GEM4XE_SDFS_H

#include <stdint.h>

#ifdef SDFS_HOST
#define FAR                     /* the host build: one flat memory */
#else
#include "portab.h"             /* the Atari: FAR is a long pointer */
#endif

#define SD_UNITS    8           /* D1: .. D8: -- unit n at [n - 1] */
#define SD_CACHE    8           /* sectors held */
#define SD_FILES    8           /* files open at once */
#define SD_DIRS     8           /* directories being listed at once */
#define SD_SECMAX   512         /* the biggest sector: a hard disk partition's */
#define SD_ENT      23          /* a directory entry */

/* GEMDOS's error numbers, the ones the engine has a use for. */
#define SD_EERROR   (-1)
#define SD_EWRPRO   (-13)       /* the disk is write-protected */
#define SD_EFILNF   (-33)
#define SD_EPTHNF   (-34)
#define SD_ENHNDL   (-35)       /* no file record free */
#define SD_EACCDN   (-36)       /* locked, a folder, exists, not empty, full */
#define SD_EIHNDL   (-37)
#define SD_EDRIVE   (-46)       /* no such unit, or not SDFS */
#define SD_ENSAME   (-48)       /* a rename between two units */
#define SD_ENMFIL   (-49)       /* no more entries */
#define SD_ERANGE   (-64)       /* a seek past the end */

/* An entry's status byte, SpartaDOS's. */
#define SD_LOCKED   0x01
#define SD_HIDDEN   0x02
#define SD_ARCHIVED 0x04
#define SD_INUSE    0x08
#define SD_DELETED  0x10
#define SD_SUBDIR   0x20

/* What a listing or a lookup gives back. */
typedef struct {
    uint8_t  status;            /* SD_* above */
    uint32_t size;              /* bytes; a folder's is its directory's */
    char     name[13];          /* NAME.EXT, a terminating zero */
    uint8_t  stamp[6];          /* day, month, year (0-79 is 2000-2079,
                                   80-99 1980-1999), hour, minute, second */
} SD_INFO;

/* Open modes, GEMDOS's Fopen and Fcreate. */
#define SD_READ     0
#define SD_WRITE    1           /* Fopen(1): an existing file, from its start */
#define SD_RW       2
#define SD_CREATE   3           /* Fcreate: emptied, or made */

/* ---- the state ---------------------------------------------------------
 * Fields are the engine's; the sizes are what a caller allocates.  No
 * sizeof() of anything with an array in it is used in a constant
 * expression (Calypsi's B7: the two answers differ). */
typedef struct {
    uint8_t  mounted;
    uint8_t  shift;             /* 7 for 128-byte sectors, 8 for 256 */
    uint8_t  bm_count;
    uint8_t  fresh;             /* sector 1 read since sd_recheck */
    uint16_t root;              /* the root directory's first map page */
    uint16_t total;             /* sectors on the disk */
    uint16_t bm_start;          /* the bitmap's first sector */
    uint16_t hint;              /* where the next allocation looks first */
    int16_t  fdelta;            /* free sectors gained, not yet in sector 1 */
} SD_UNIT;

typedef struct {
    uint8_t  unit;              /* 1..8, 0 for an empty slot */
    uint8_t  kind;              /* SK_* in sdfs.c: what writes it first */
    uint8_t  dirty;
    uint8_t  age;
    uint16_t sec;
} SD_SLOT;

typedef struct {
    uint8_t  used;
    uint8_t  unit;
    uint8_t  mode;
    uint8_t  grown;             /* written to: the entry's length is due */
    uint16_t dmap;              /* its directory's first map page */
    uint16_t doff;              /* its entry's offset in that directory */
    uint16_t first;             /* its own first map page */
    uint16_t mpage;             /* a map page of its chain, kept ... */
    uint16_t mpn;               /* ... with its place in the chain, or $FFFF */
    uint16_t pad;
    uint32_t size;
    uint32_t pos;
} SD_FILE;

typedef struct {
    uint8_t  used;
    uint8_t  unit;
    uint16_t dmap;
    uint16_t off;               /* the next entry's offset */
    uint16_t size;              /* the directory's length */
} SD_DIR;

/* A lookup: a name in a directory (sdfs.c, d_find). */
typedef struct {
    uint16_t dmap;              /* the directory */
    uint16_t off;               /* the entry, if found */
    uint16_t freeoff;           /* the first free slot, or the end */
    uint16_t dsize;             /* the directory's length */
    uint8_t  ent[SD_ENT];       /* the entry, if found */
    uint8_t  want[11];          /* the name looked for */
} SD_FIND;

typedef struct {
    SD_UNIT  units[SD_UNITS];
    SD_SLOT  slots[SD_CACHE];
    SD_FILE  files[SD_FILES];
    SD_DIR   dirs[SD_DIRS];
    uint8_t  age;
    uint8_t  pad;
    uint16_t dev;               /* the platform's own: sd_dev may keep a
                                   word here (the Atari's, G4DOS's buffer) */
    /* scratch for the call in progress -- here and not on the stack,
     * which on the Atari is bank $00's and an application's (sdfs.c) */
    SD_FIND  f, g, w;
    uint8_t  ent[SD_ENT];
    uint8_t  buf[SD_CACHE][SD_SECMAX];
} SDFS;

/* ---- what the platform gives -------------------------------------------
 * sd_dev: sector `sec` of unit `unit` (1..8), `len` bytes (128 or 256),
 * for the engine `s` (whose `dev` word is the platform's to keep),
 * read into `buf` or written from it.  0, or a negative GEMDOS error
 * (SD_EWRPRO for a write-protected disk, SD_EDRIVE when nothing answers). */
int16_t sd_dev(SDFS FAR *s, uint8_t unit, uint16_t sec, uint8_t FAR *buf,
               uint16_t len, uint8_t write);
/* sd_now: the time, as an entry keeps it (SD_INFO.stamp). */
void sd_now(uint8_t FAR *stamp);
/* sd_devsec: the size of the sectors the drive in `unit` reads -- 128,
 * 256 or 512 -- or 0 when it cannot say.  Asked before a unit's sector 1
 * is read, because that sector is 512 bytes on a 512-byte disk and 128
 * on every other: the engine reads it as 512 only when told 512. */
uint16_t sd_devsec(SDFS FAR *s, uint8_t unit);

/* ---- the engine ------------------------------------------------------- */
void    sd_init(SDFS FAR *s);
/* the disk in unit `unit` may have changed: forget what is cached of it */
void    sd_forget(SDFS FAR *s, uint8_t unit);
/* ...or it may have: the next call that names a path reads sector 1 again
 * and forgets the rest if it is another disk.  Until this is called, a
 * mounted unit is taken to hold the disk it held -- so a platform calls it
 * once an operation, and a lookup that is several calls costs one read. */
void    sd_recheck(SDFS FAR *s, uint8_t unit);

int16_t sd_stat(SDFS FAR *s, uint8_t unit, const char FAR *path,
                SD_INFO FAR *info);
int16_t sd_open(SDFS FAR *s, uint8_t unit, const char FAR *path,
                uint8_t mode);                  /* a file number, or < 0 */
int32_t sd_read(SDFS FAR *s, int16_t f, uint8_t FAR *buf, uint32_t n);
int32_t sd_write(SDFS FAR *s, int16_t f, const uint8_t FAR *buf, uint32_t n);
int32_t sd_seek(SDFS FAR *s, int16_t f, uint32_t pos);
int32_t sd_tell(SDFS FAR *s, int16_t f);
int32_t sd_length(SDFS FAR *s, int16_t f);
int16_t sd_close(SDFS FAR *s, int16_t f);
/* a file's stamp, read (set = 0) or written: open files only */
int16_t sd_fstamp(SDFS FAR *s, int16_t f, uint8_t FAR *stamp, uint8_t set);

int16_t sd_opendir(SDFS FAR *s, uint8_t unit, const char FAR *path);
int16_t sd_readdir(SDFS FAR *s, int16_t d, SD_INFO FAR *info);  /* SD_ENMFIL at the end */
void    sd_closedir(SDFS FAR *s, int16_t d);

int16_t sd_delete(SDFS FAR *s, uint8_t unit, const char FAR *path);
int16_t sd_rename(SDFS FAR *s, uint8_t unit, const char FAR *from,
                  const char FAR *to);
int16_t sd_mkdir(SDFS FAR *s, uint8_t unit, const char FAR *path);
int16_t sd_rmdir(SDFS FAR *s, uint8_t unit, const char FAR *path);
/* the status bits LOCKED, HIDDEN and ARCHIVED, read, or set to `bits` */
int16_t sd_attrib(SDFS FAR *s, uint8_t unit, const char FAR *path,
                  uint8_t set, uint8_t bits);
int16_t sd_space(SDFS FAR *s, uint8_t unit, uint16_t FAR *free,
                 uint16_t FAR *total);
/* everything written that is still cached, written: the order above */
int16_t sd_sync(SDFS FAR *s, uint8_t unit);

#endif
