/* lang.c -- LANG.RSC: everything the system says, kept in far memory --
 * and, since a translation is no use in a character set that cannot
 * spell it, the SYSTEM.FNT beside it (src/vdi/font.c).  They are the
 * two files a translation ships, and two calls read them: lang_init()
 * the strings, which needs only far memory and so can run before there
 * is a GEM screen -- the boot screen (src/sys/bootinfo.c) is written in
 * them -- and lang_font() the face, which goes into the device and so
 * has to wait for one.
 *
 * The rule the project set itself is that no string a person reads is in
 * the C (docs/shipping.md, section 5).  The desktop's went into its own
 * resource in Phase 14; the SYSTEM's -- form_error's alerts, the shell's
 * two failures -- are here, as free strings of a resource that
 * tools/langrsc.py builds and a translator replaces.
 *
 * Far, and copied a string at a time.  The application pool is 14 KB and
 * an application's resource has to fit in it beside the desktop's, so a
 * kilobyte of alert text cannot live there; the resource sits in far
 * memory as the file's own bytes, unfixed (there are no trees in it to
 * fix), and lang_str() copies the one string being used into a near
 * buffer, which is what fm_alert wants.  ONE buffer: an alert is modal,
 * so no two of these are alive at once, and a caller that wants to keep
 * one past the next call must copy it.
 *
 * The file is optional.  A disk without LANG.RSC gets the same English
 * from build/lang_rsc.c -- the identical bytes, linked into the far
 * image -- because a system that cannot say "this application cannot be
 * found" because its language file is missing is worse than one that
 * says it in English.  So the file OVERRIDES; it is not required.
 *
 * What it will not do is fix up trees.  The file selector's dialog is
 * still built into the far image (tools/fselrsc.py) for the pool reason
 * in tools/langrsc.py's header, so a translation cannot widen it yet.
 */
#include "portab.h"
#include <string.h>
#include "aes/aes.h"
#include "sys/cio.h"
#include "sys/farmem.h"
#include "sys/app.h"                    /* far_read_file */
#include "vdi/font.h"
#include "lang_rsc.h"

/* The .RSC header, by offset rather than by struct: every word in the
 * file is big-endian, so it is read a byte at a time anyway, and this
 * file has no business knowing the rest of the layout.  (aes.h's RSHDR
 * is the same fields in the 65816's order, for a resource already
 * loaded and swapped.) */
#define RSH_VRSN     0          /* UWORD: 4 set means the colour format */
#define RSH_FRSTR   10          /* UWORD: offset of the free-string table */
#define RSH_NSTRING 30          /* WORD:  how many strings are in it      */
#define RSH_RSSIZE  34          /* UWORD: the whole file                  */
#define RSH_SIZE    36

#define LANG_CHUNK 256          /* the near bounce buffer for the read */

static uint32_t lang_base;      /* far address of the resource image */
static uint16_t lang_frstr;     /* the free-string table, from its start */
static WORD     lang_n;         /* strings in it */

static uint16_t be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

/* The English in the far image, which is where every run starts. */
static void lang_builtin(void)
{
    uint8_t hdr[RSH_SIZE];

    lang_base = (uint32_t)(const uint8_t FAR *)lang_rsc;
    far_get(hdr, lang_base, RSH_SIZE);
    lang_frstr = be16(&hdr[RSH_FRSTR]);
    lang_n = (WORD)be16(&hdr[RSH_NSTRING]);
}

/* Read `size` bytes of an open file into far memory through a near
 * buffer, the header already read and handed back in.  0 unless all of
 * it arrived. */
static WORD lang_read(int16_t fd, uint32_t dst, const uint8_t *hdr, uint16_t size)
{
    uint16_t left = (uint16_t)(size - RSH_SIZE), got;
    uint8_t buf[LANG_CHUNK], st;

    far_put(dst, hdr, RSH_SIZE);
    dst += RSH_SIZE;
    while (left) {
        uint16_t want = left > LANG_CHUNK ? LANG_CHUNK : left;
        st = cio_read(fd, buf, want, &got);
        if ((st != CIO_OK && st != CIO_OK_EOF) || got != want)
            return 0;
        far_put(dst, buf, got);
        dst += got;
        left = (uint16_t)(left - got);
    }
    return 1;
}

extern int16_t g4z_unpack(uint32_t src, uint32_t dst, uint32_t count);

/* A SQUEEZED LANG.RSC (phase 163): "G4A" 6, the unpacked length, one G4Z
 * stream -- what tools/squeeze.py makes of a file, as it makes DESKTOP.RSC
 * for the floppy that boots a DOS 2 (src/aes/rsrc.c, rc_unsqueeze).  That
 * floppy is the tight one, and LANG.RSC goes on it in 5 sectors where it
 * was 10.  A resource cannot begin so: its first word is a version, 0 to
 * 3, high byte first.  The file as it was before it was squeezed, in far
 * memory of its own, with its header copied back into `hdr`; or 0.  The
 * whole file is read first (far_read_file), after the memory it unpacks
 * to is taken, so the read's block is the one that goes again. */
static uint32_t lang_unsqueeze(const char *cio, uint8_t *hdr)
{
    uint32_t n, mem, blob = 0, len = 0;

    n = (uint32_t)hdr[4] | ((uint32_t)hdr[5] << 8) | ((uint32_t)hdr[6] << 16)
        | ((uint32_t)hdr[7] << 24);
    if (n < RSH_SIZE || n > 0xFFFFUL)
        return 0;
    mem = far_alloc(n);
    if (!mem)
        return 0;
    if (far_read_file(cio, &blob, &len) != APP_OK)
        return 0;                       /* mem stays taken: never given back */
    if (len <= 8 || g4z_unpack(blob + 8, mem, n) != 0) {
        far_free(blob);
        return 0;
    }
    far_free(blob);
    far_get(hdr, mem, RSH_SIZE);
    return mem;
}

/* The other half of a translation: the character set.  LANG.RSC in Polish
 * is unreadable in the Atari ST's set, so a translation ships SYSTEM.FNT
 * beside it and the system takes it if it is there (src/vdi/font.c).  The
 * VDI is told where to look either way, so vst_load_fonts can go back for
 * it later. */
void lang_font(void)
{
    static WORD done;           /* once a run, like the strings */
    char cio[CIO_NAME_MAX + 1];

    if (done)
        return;
    done = 1;
    sh_cioname(FONT_FILE, cio);
    vdi_font_where(cio);
    vdi_font_load();
}

static WORD lang_file;          /* 1: LANG.RSC is what is in use */

void lang_init(void)
{
    static WORD done;           /* the file is read once a run */
    uint8_t hdr[RSH_SIZE];
    char cio[CIO_NAME_MAX + 1];
    uint16_t size, got;
    uint32_t mem = 0;
    int16_t fd;
    WORD squeezed;

    if (done)
        return;
    done = 1;
    lang_builtin();
    sh_cioname(LANG_FILE, cio);
    fd = cio_open(cio, CIO_A_READ, 0);
    if (fd < 0)
        return;
    if (cio_read(fd, hdr, RSH_SIZE, &got) != CIO_OK || got != RSH_SIZE) {
        cio_close(fd);
        return;
    }
    squeezed = (WORD)(hdr[0] == 'G' && hdr[1] == '4' && hdr[2] == 'A' && hdr[3] == 6);
    if (squeezed) {                     /* read whole and unpacked, below */
        cio_close(fd);
        mem = lang_unsqueeze(cio, hdr);
        if (!mem)
            return;
    }
    size = be16(&hdr[RSH_RSSIZE]);
    /* Refuse what cannot be read rather than half-read it: the colour
     * format, a file that does not hold its own header, and one with
     * fewer strings than the system asks for by index. */
    if ((be16(&hdr[RSH_VRSN]) & NEW_FORMAT_RSC) || size < RSH_SIZE
        || (WORD)be16(&hdr[RSH_NSTRING]) < LANG_NSTRING) {
        if (!squeezed)
            cio_close(fd);
        return;
    }
    if (squeezed) {
        lang_base = mem;
        lang_frstr = be16(&hdr[RSH_FRSTR]);
        lang_n = (WORD)be16(&hdr[RSH_NSTRING]);
        lang_file = 1;
        return;
    }
    mem = far_alloc(size);
    if (!mem) {
        cio_close(fd);
        return;
    }
    if (lang_read(fd, mem, hdr, size)) {
        lang_base = mem;
        lang_frstr = be16(&hdr[RSH_FRSTR]);
        lang_n = (WORD)be16(&hdr[RSH_NSTRING]);
        lang_file = 1;
    }
    cio_close(fd);
    /* A read that failed leaves the far memory taken and the built-in in
     * use, which is the safe way round: far_alloc never gives it back. */
}

WORD lang_loaded(void)
{
    return lang_file;
}

const char *lang_str(WORD n)
{
    /* named for the gates, which read what an alert is showing out of it
     * (tests/emu/m57_short.py): `buf` is another file's name too */
    static char lang_buf[LANG_MAXLEN + 1];
    uint8_t off[4];

    if (n < 0 || n >= lang_n) {         /* a string this build does not have */
        lang_buf[0] = '\0';
        return lang_buf;
    }
    far_get(off, lang_base + lang_frstr + (uint32_t)((uint16_t)n << 2), 4);
    far_strget(lang_buf, lang_base + (((uint32_t)off[0] << 24) | ((uint32_t)off[1] << 16)
                                      | ((uint32_t)off[2] << 8) | off[3]),
               sizeof lang_buf);
    return lang_buf;
}
