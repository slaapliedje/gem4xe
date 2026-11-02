/* sdcio.h -- CIO's D:, served by gem4xe's own SDFS engine where the DOS is
 * G4DOS (docs/sdfs-plan.md, steps 2 and 3).
 *
 * G4DOS (src/fdos.s) reads and writes SDFS but has no room for folders:
 * it shows the root and one level down as a single flat drive.  So once
 * GEMDOS is up (gemdos_init), gem4xe stops handing D: to it: every name
 * src/sys/cio.c is given for a disk -- GEMDOS's, the file selector's, the
 * shell's, the program loader's -- goes to the engine (src/sys/sdfs.c),
 * which reads and writes sectors through G4DOS's sector entry and does
 * the folders itself.  Everything above cio.c is unchanged: it sees a DOS
 * with directories, as it does under SpartaDOS (src/sys/dos.h), and the
 * names it builds are SpartaDOS's.
 *
 * WHAT A NAME MEANS.  "Dn:>DIR>NAME.EXT" is from the root, and so is a
 * name with a '>' anywhere in it.  A BARE name -- "Dn:NAME.EXT", no '>'
 * at all -- keeps G4DOS's meaning, because it is how gem4xe finds its own
 * files (src/sys/gemdos.c, gd_cioname): the root first, then each folder
 * of the root.  A bare name to be created goes in the root, as G4DOS
 * writes one, and a bare listing is G4DOS's flat one: the root's files
 * and its folders' files, the folders themselves left out.
 *
 * AN IOCB THE ENGINE HAS is claimed as CIO would claim it -- its ICHID is
 * not $FF, so nothing else takes it -- but with SDC_ICHID, no handler's
 * index, and cio.c sends every later call on it here.  Nothing gem4xe
 * runs reaches the OS's CIO on such an IOCB.
 *
 * Statuses are CIO's, as cio.h describes them: the engine's GEMDOS errors
 * are turned into the numbers a SpartaDOS would have answered, which
 * src/sys/gemdos.c turns back (gd_err).
 */
#ifndef GEM4XE_SDCIO_H
#define GEM4XE_SDCIO_H

#include <stdint.h>

#define SDC_ICHID    0x7E        /* an IOCB the engine has */

/* gemdos_init: off, and where the DOS is G4DOS on -- the engine's state
 * in far memory, and the DOS described as having folders.  Without far
 * memory it stays off and G4DOS's flat view is what there is. */
void     sdc_init(void);

/* Is `name` a D: name the engine serves?  Never before sdc_init. */
uint8_t  sdc_claims(const char *name);

/* cio.c's calls, for a name sdc_claims took or an IOCB with SDC_ICHID. */
int16_t  sdc_open(int16_t iocb, const char *name, uint8_t aux1, uint8_t aux2);
uint8_t  sdc_close(int16_t iocb);
uint8_t  sdc_xfer(int16_t iocb, uint8_t cmd, void *buf, uint16_t len,
                 uint16_t *got);
uint8_t  sdc_xio(uint8_t cmd, const char *name);

#endif
