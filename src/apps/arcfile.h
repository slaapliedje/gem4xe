/* GemARC's archives: the members listed, taken out and put in.
 *
 * Portable like src/apps/arccodec.c.  The files are the platform's --
 * GEMDOS in src/apps/gemarc.c, stdio in tests/host/arc_host.c -- through
 * the pf_ functions below. */
#ifndef GEMARC_FILE_H
#define GEMARC_FILE_H

#include "arccodec.h"

typedef struct {
    char     name[ARC_NAMELEN];     /* as the archive spells it, NUL ended */
    uint8_t  method;
    uint8_t  sel;                   /* the program's: chosen in the list */
    uint16_t date, time;            /* MS-DOS's, as GEMDOS's */
    uint16_t crc;
    uint32_t csize, osize;
    uint32_t data;                  /* where its data starts in the file */
} ARC_ENTRY;

/* What went wrong with an archive as a whole, beside arccodec.h's. */
#define ARC_E_OPEN    10            /* the archive would not open */
#define ARC_E_NOTARC  11            /* it is not an ARC archive */
#define ARC_E_SOURCE  12            /* a file to add would not open */
#define ARC_E_CREATE  13            /* a file to write would not be made */
#define ARC_E_MEMORY  14
#define ARC_E_FULL    15            /* more members than the list holds */

/* -- the platform's ----------------------------------------------------- */
int  pf_open(const char FAR *name);         /* a handle, or <0 */
int  pf_create(const char FAR *name);
long pf_read(int h, uint8_t FAR *buf, long n);
long pf_write(int h, const uint8_t FAR *buf, long n);
long pf_seek(int h, long offset);           /* from the start */
void pf_close(int h);
int  pf_delete(const char FAR *name);
int  pf_rename(const char FAR *from, const char FAR *to);
/* A file's date and time, MS-DOS's words, for a member made of it; and
 * set on a file being written, if the DOS can (0s are left alone). */
void pf_stamp(const char FAR *name, uint16_t *date, uint16_t *time);
void pf_setstamp(int h, uint16_t date, uint16_t time);
/* Told each member's name as it is taken out or put in. */
void arc_progress(const char FAR *name);

/* The two buffers the files are read and written through, each `size`
 * bytes, and the codec's tables (arccodec.h arc_tables) -- the caller's
 * memory, all of it. */
void arc_buffers(uint8_t FAR *in, uint8_t FAR *out, uint16_t size);

/* The members of `path`, up to `max` of them, into `list`; *n how many.
 * ARC_OK, or ARC_E_OPEN / ARC_E_NOTARC / ARC_E_FULL (the first `max` are
 * there all the same). */
int arc_list(const char FAR *path, ARC_ENTRY FAR *list, uint16_t max,
             uint16_t *n);

/* One member out of `archive` into the file `out`. */
int arc_extract(const char FAR *archive, const ARC_ENTRY FAR *e,
                const char FAR *out);

/* An archive made, or made again, with the files in `dir` named in
 * `names` (`count` of them, each "NAME.EXT") put in: a member of the same
 * name is replaced, the rest kept, the members in name order as ARC keeps
 * them.  Written to `temp` and renamed over `archive` when it is whole,
 * so a failure leaves the old one as it was.  `archive` need not exist. */
int arc_add(const char FAR *archive, const char FAR *temp,
            const char FAR *dir, char FAR (*names)[ARC_NAMELEN],
            uint16_t count, ARC_ENTRY FAR *list, uint16_t max);
#define ARC_ADD_MAX 64                  /* files in one arc_add */

/* "FILE.EXT" as a member is named: upper case, eight and three. */
void arc_member_name(const char FAR *from, char *to);

#endif
