/* dos.h -- which DOS is behind CIO, and what its file system can do.
 *
 * GEM on the ST sits on GEMDOS; gem4xe sits on whatever DOS booted the
 * machine, through CIO (src/sys/cio.h), and the DOSes differ in exactly
 * two things the AES can see: the shape of a path, and what a directory
 * listing says.  Everything the file layer has to decide by DOS is
 * decided here, once, at start-up, and read from `dos` afterwards --
 * the selector (src/aes/fsel.c) and the path mapping (src/aes/shel.c)
 * ask this header, never the DOS.
 *
 * THE DOSES.  Atari DOS 2 (2.0S, 2.5, and the lookalikes that keep its
 * boot record) has one flat directory per disk, names of 8.3, and a
 * directory read -- OPEN with aux1 = 6 -- that prints one 17-character
 * line per entry.  SpartaDOS (3.x from disk, X from a cartridge) has a
 * hierarchical file system, SDFS, with a path syntax of its own:
 *
 *     D1:>DIR>SUB>NAME.EXT       from the root of D1:
 *     D1:DIR>NAME.EXT            from the current directory of D1:
 *
 * and its CIO directory read prints DOS 2's line for DOS 2's sake, with
 * one addition for the thing DOS 2 does not have, made differently by
 * the two:
 *
 *     3.2g   "  SUB     DIR 002"   the extension field is "DIR" in
 *                                  inverse video (high bits set); the
 *                                  "sectors" are the directory's own
 *     X 4.50 " :SUB         001"   a ':' before the name, the directory's
 *                                  own extension where a file's would be
 *
 * The first was measured from SpartaDOS 3.2g through CIO; the second is
 * what the SpartaDOS X Programming Guide 4.50 (10.2) says the short
 * format's mode $08 does, and measured the same from 4.50.  Both marks
 * are looked for on either DOS -- neither can occur in a DOS 2 line.
 * gem4xe keeps the GEM shape -- A:\DIR\SUB\NAME.EXT -- and maps it
 * here, so an application never sees a '>'.
 *
 * IDENTIFYING THEM.  A SpartaDOS keeps an 'S' at $0700, the first byte
 * of its resident part, and DOSVEC points at its command table, whose
 * fourth byte is a JMP -- the ZCRNAME entry, "common to all SpartaDOS
 * and DOS XL versions" (SpartaDOS X Programming Guide 4.50, chapter 5).
 * DOS 2's $0700 is the boot record's flag byte, zero.  Both are asked,
 * and a DOS that answers neither is taken for DOS 2, which is the DOS
 * gem4xe grew up on and the safer guess: it costs subdirectories, not
 * correctness.
 */
#ifndef GEM4XE_DOS_H
#define GEM4XE_DOS_H

#include <stdint.h>

#define DOS_2        0          /* Atari DOS 2.x or a lookalike */
#define DOS_SPARTA   1          /* SpartaDOS 3.x, from disk */
#define DOS_SDX      2          /* SpartaDOS X, from a cartridge */

/* Capabilities: what the file layer may rely on. */
#define DOS_CAP_DIRS 0x01       /* subdirectories: paths carry them and
                                   listings mark them */
#define DOS_CAP_RAWDIR 0x02     /* a directory opens as its own entries
                                   (CIO_A_RAWDIR): 23 bytes each -- status,
                                   map sector, size in bytes, name, ext,
                                   date, time -- the whole directory in
                                   one read, where the line listing costs
                                   a call a record.  Both SpartaDOSes do
                                   it (SDX Programming Guide 4.50, 8.1.1;
                                   3.2g measured).  src/sys/gemdos.c */
#define DOS_CAP_STAMPS 0x04     /* the entries carry a date and a time */
#define DOS_CAP_DRVBYT 0x08     /* $070A is DOS 2's DRVBYT, a bitmap of the
                                   drives it will talk to, and Drvmap may
                                   return it.  Every DOS_2 but MyDOS: its
                                   boot flag at $0700 is 'M' and its $070A
                                   is $08 on a one-drive machine, which as a
                                   bitmap is drive D (docs/phase50.md) */

typedef struct {
    uint8_t  kind;              /* DOS_2 .. DOS_SDX */
    uint8_t  caps;              /* DOS_CAP_* */
    char     dirsep;            /* the DOS's path separator, 0 for none:
                                   directories are dropped from a path */
    uint16_t memlo, memtop;     /* the DOS's, as booted: what is free */
} DOS_INFO;

extern DOS_INFO dos;

/* Look at the machine once; fills `dos`.  Before anything opens a file. */
void dos_ident(void);

/* The DOS's command processor given a line -- SpartaDOS X's XCOMLI --
 * with what it prints caught in the far buffer at `out`, `max` bytes of
 * it (src/sys/cio.s sdx_put).  The bytes caught; GD_EINVFN on a DOS
 * with no such entry.  A null `line` asks only whether there is one. */
int32_t dos_command(uint32_t line, uint32_t out, uint32_t max);

/* Does this 17-character directory line carry the DOS's mark for a
 * subdirectory?  DOS_MARK_NONE for a file (or on a flat DOS, always);
 * DOS_MARK_FLAG when the mark is in the flag column and the extension
 * field is the directory's own; DOS_MARK_EXT when the extension field
 * IS the mark, so the directory has none. */
#define DOS_MARK_NONE 0
#define DOS_MARK_FLAG 1
#define DOS_MARK_EXT  2
uint8_t dos_folder_line(const char *line);

/* A GEM path -- X:\DIR\NAME.EXT, or a bare NAME.EXT -- into the name
 * CIO opens on this DOS, uppercased: Dn:>DIR>NAME.EXT where the DOS has
 * directories, Dn:NAME.EXT where it has not (the directories dropped).
 * `cio` holds CIO_NAME_MAX + 1; a longer path is cut there. */
void dos_cioname(const char *gem, char *cio);

/* A directory line -- DOS 2's 17 characters, less the EOL, as the
 * directory read with CIO_A_DIR yields them on every DOS -- into
 * NAME.EXT (fname holds 13) and its kind: DOS_ENT_FILE, DOS_ENT_DIR
 * for a subdirectory where the DOS has them, or DOS_ENT_NONE for a
 * line that is not an entry: the deleted entry's dashes, the FREE
 * SECTORS trailer, noise.  DOS_ENT_LOCKED is or'ed in for the '*' in
 * the flag column.  *sectors, when asked for, is the line's count --
 * the file's size in sectors, which is all a DOS 2 directory knows. */
#define DOS_ENT_NONE   0
#define DOS_ENT_FILE   1
#define DOS_ENT_DIR    2
#define DOS_ENT_KIND   0x0F
#define DOS_ENT_LOCKED 0x80
uint8_t dos_dirline(const char *line, uint16_t got, char *fname,
                    uint16_t *sectors);

/* NAME.EXT against a pattern, name and extension in turn, '*' and '?'
 * as on the ST: the donor's wildcmp, shared by the selector and by
 * Fsfirst so that both agree on what *.C means. */
uint16_t dos_wildcmp(const char *pattern, const char *filename);

#endif
