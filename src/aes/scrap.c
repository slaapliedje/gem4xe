/* scrap.c -- the scrap manager: scrp_read and scrp_write, which are the
 * AES's record of WHERE the clipboard is.  EmuTOS aes/gemsclib.c.
 *
 * The AES keeps a directory path and nothing else.  The scrap itself is
 * files called SCRAP.* in that directory, written and read by the
 * applications themselves, so what the AES arbitrates is a place rather
 * than a format -- which is why two programs that have never heard of
 * each other can still cut and paste.
 *
 * Neither call validates the path.  TOS stopped doing that and the donor
 * follows it, with the reason in its comment: an application that asks
 * for the scrap directory before anybody has set one wants an answer it
 * can act on, not a refusal.  So sc_read hands back whatever is there,
 * empty string included, and answers TRUE either way.
 *
 * It lives in far memory for the same reason shel.c's buffers do: it is
 * state the AES holds on the applications' behalf, across their
 * lifetimes, and far_alloc is a bump allocator that app_free winds back
 * to where app_load found it.  So it is taken ONCE, at start-up, before
 * any application is loaded -- anything taken after one would go with it.
 */
#include "portab.h"
#include <string.h>
#include "aes/aes.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/farmem.h"

/* SH_CMDLEN's number and SH_CMDLEN's reason: a scrap directory is a path
 * like any other, and the donor's sc_clear appends SCRAP.* to this same
 * buffer to search it, so a full path AND a filename have to fit. */
#define SC_PATHLEN  128

static uint32_t sc_path_far;            /* 0 until sc_init */

void sc_init(void)
{
    if (sc_path_far)                    /* the AES starts up once per script */
        return;
    sc_path_far = far_alloc(SC_PATHLEN);
    if (sc_path_far)
        far_write8(sc_path_far, 0);     /* no scrap directory yet */
}

WORD sc_read(char *pscrap)
{
    if (!sc_path_far)
        return 0;
    far_strget(pscrap, sc_path_far, SC_PATHLEN);
    return 1;
}

WORD sc_write(const char *pscrap)
{
    if (!sc_path_far)
        return 0;
    far_strput(sc_path_far, pscrap, SC_PATHLEN);
    return 1;
}

/* THE SCRAP ITSELF, which is the one thing the two calls above do not
 * touch: every SCRAP.* in the scrap directory, deleted.
 *
 * NO ATARI AES HAS THIS.  The Falcon ROM's CRYSBIND.H declares SCRP_READ
 * 80 and SCRP_WRITE 81 and stops -- there is no SCRP_CLEAR in it, and
 * the Compendium documents the same two and gives opcode 82 no reference
 * page.  It is PC-GEM's; EmuTOS names it in include/aesdefs.h and serves
 * it only under CONF_WITH_PCGEM.
 *
 * So a program ported from an ST will not call this, and must not have
 * to: the Compendium's own cut-and-copy recipe (p.352, step 3) tells the
 * APPLICATION to "search and delete files in the current clipboard
 * directory with the mask SCRAP.*", because on an ST there is nothing
 * else it could do.  That still works here.  What this adds is the same
 * walk done once, in the AES, for a program that asks for it -- and for
 * gem4xe's own desktop, which will want to clear the scrap without
 * opening the file selector's machinery to do it.
 */
#define SC_MASK     "SCRAP.*"
#define SC_NAMELEN  13                  /* NAME.EXT and its NUL: dos_dirline's */
#define SC_DIRLINE  17                  /* DOS 2's record, less its EOL */

/* The first SCRAP.* in the directory `path` names, written where `fname`
 * points -- which is `path`'s own NUL, so on TRUE `path` has become the
 * full name of that file.  FALSE when there is none, or when the drive
 * does not answer, which read the same on purpose: a scrap directory on
 * a drive with no disk in it has no scrap in it either. */
static WORD sc_first(char *path, char *fname)
{
    char     cio[CIO_NAME_MAX + 1], line[SC_DIRLINE + 8], entry[SC_NAMELEN];
    int16_t  fd;
    WORD     found = FALSE;

    /* "*.*" and not SC_MASK: the directory is read whole and matched
     * here, because what a DOS does with a pattern of its own is the
     * DOS's business and dos_wildcmp is what agrees with the ST. */
    strcpy(fname, "*.*");
    sh_cioname(path, cio);
    *fname = '\0';
    fd = cio_open(cio, CIO_A_DIR, 0);
    if (fd < 0)
        return FALSE;
    for (;;) {
        uint16_t got = 0;
        uint8_t  st = cio_getrec(fd, line, sizeof line, &got);

        /* 1 for a record and 3 for the last one, not 0 (fs_active). */
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        if ((dos_dirline(line, got, entry, 0) & DOS_ENT_KIND) == DOS_ENT_FILE
            && dos_wildcmp(SC_MASK, entry)) {
            strcpy(fname, entry);
            found = TRUE;
            break;
        }
        if (st == CIO_OK_EOF)
            break;
    }
    cio_close(fd);
    return found;
}

WORD sc_clear(void)
{
    char  path[SC_PATHLEN];
    char *fname;

    if (!sc_path_far)
        return FALSE;
    far_strget(path, sc_path_far, SC_PATHLEN);
    if (!path[0])                       /* nobody has set a scrap directory */
        return FALSE;                   /* -- the donor's refusal, and its
                                         * only one */
    fname = path + strlen(path);
    if ((WORD)(fname - path) + SC_NAMELEN > SC_PATHLEN)
        return FALSE;                   /* no room to name a file in it */

    /* ONE FILE PER PASS, and the directory closed before any delete.
     * The donor deletes inside its own Fsfirst/Fsnext walk, which a
     * GEMDOS tolerates; here the walk is a CIO directory channel open on
     * the drive being deleted from, and sh_accs already keeps those two
     * apart for the weaker reason that loading an accessory reads files
     * (src/aes/shel.c).  Re-reading the directory per file is a few
     * hundred bytes of I/O against a clipboard that holds a handful of
     * files -- SCRAP.TXT, SCRAP.IMG and their kind -- and it costs no
     * stack, which is the scarcer thing here.
     *
     * IT TERMINATES BECAUSE A FAILED DELETE STOPS IT.  Every pass starts
     * the directory again, so a file that would not go -- locked, or on
     * a write-protected disk -- would be found again forever.  The loop
     * ends on the first refusal and answers FALSE, which is also the
     * truthful answer: the scrap is not clear. */
    while (sc_first(path, fname)) {
        char cio[CIO_NAME_MAX + 1];

        sh_cioname(path, cio);
        if (cio_xio(CIO_X_DELETE, cio, 0, 0) != CIO_OK) {
            *fname = '\0';
            return FALSE;
        }
        *fname = '\0';
    }
    return TRUE;
}
