/* font.c -- loading a GEM .FNT, and the face the VDI draws with.  See font.h.
 *
 * THE FORMAT is DRI's, the one every GEM font file has: an 88-byte header
 * (EmuTOS's `Fonthead`, big-endian), then the offset table, then the strip --
 * `form_width` bytes a row, `form_height` rows, character N's byte on row r
 * at r*form_width + N.  For a monospaced 8-wide font of 256 characters that
 * strip IS the layout vdi_font_expand() reads, so loading one is a read into
 * far memory and an expansion, not a conversion.
 *
 * WHAT IS REFUSED, and why each: a form that is not 256x8 (the cell is fixed
 * -- font.h says why), a first/last character range that is not 0..255 (the
 * strip would have to be placed rather than copied), a `top` that is not the
 * linked font's (the AES asks for the cell once, at start-up, and lays the
 * desktop out with the answer), and the colour or word-swapped variants of
 * the format.  A refusal leaves the face that was in use, and says so by
 * returning 0; nothing here can leave the VDI with half a font.
 *
 * CIO has no seek, so the strip is reached by reading the file to it and
 * dropping what is passed -- 514 bytes of offset table for a 256-glyph font.
 */
#include <string.h>
#include "font.h"
#include "vdidev.h"

/* The face the running DEVICE carries -- 8x8 where there are 80 columns
 * to spend and Atari's condensed 6x6 where there are not (vdidev.h).  It
 * is read off `vdev` rather than chosen here, because both faces are in
 * the image and which screen came up is not decided until the program
 * starts. */
#define vdi_face (vdev->font_face)
#include "sys/cio.h"
#include "sys/farmem.h"

/* The header, by offset: every word in the file is big-endian, so it is read
 * a byte at a time anyway. */
#define FH_FONT_ID     0
#define FH_POINT       2
#define FH_NAME        4        /* 32 bytes */
#define FH_FIRST_ADE  36
#define FH_LAST_ADE   38
#define FH_TOP        40
#define FH_MAX_CELL   52
#define FH_FLAGS      66
#define FH_DAT_TABLE  76        /* a LONG: where the strip starts */
#define FH_FORM_W     80
#define FH_FORM_H     82
#define FH_SIZE       88

#define FF_HORZ_OFF  0x02       /* a horizontal offset table: not carried */
#define FF_STDFORM   0x04       /* big-endian bit order: required */
#define FF_MONOSPACE 0x08       /* required: the cell is fixed */

#define FONT_CHUNK 128          /* the near bounce buffer */
#define FONT_BYTES ((uint16_t)FONT_STRIDE * FONT_H)

uint32_t vdi_font;

static uint32_t font_ram;                   /* the loaded strip, 0 until one is */
static char     font_cio[CIO_NAME_MAX + 1]; /* where the system looks */
static char     font_named[FONT_NAME_MAX];  /* the loaded face's name */
static WORD     font_loaded_id;
static WORD     font_have;                  /* a font is loaded */

static uint16_t be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
           | ((uint32_t)p[2] << 8) | p[3];
}

void vdi_font_where(const char *cioname)
{
    uint16_t i;
    for (i = 0; i < CIO_NAME_MAX && cioname[i]; i++)
        font_cio[i] = cioname[i];
    font_cio[i] = '\0';
}

void vdi_font_default(void)
{
    vdi_font = (uint32_t)vdi_face;
    dev_font_changed();
}

/* The header says whether this file is one we can take. */
static WORD font_ok(const uint8_t *h)
{
    uint16_t flags = be16(&h[FH_FLAGS]);

    return be16(&h[FH_FORM_W]) == FONT_STRIDE
        && be16(&h[FH_FORM_H]) == FONT_H
        && be16(&h[FH_FIRST_ADE]) == 0
        && be16(&h[FH_LAST_ADE]) == 255
        && be16(&h[FH_TOP]) == FONT_TOP
        && be16(&h[FH_MAX_CELL]) == FONT_W
        && (flags & (FF_STDFORM | FF_MONOSPACE)) == (FF_STDFORM | FF_MONOSPACE)
        && !(flags & FF_HORZ_OFF)
        && be32(&h[FH_DAT_TABLE]) >= FH_SIZE;
}

/* Read forward to `to`, dropping what is passed. */
static WORD font_skip(int16_t fd, uint32_t from, uint32_t to)
{
    uint8_t buf[FONT_CHUNK];
    uint16_t got;

    while (from < to) {
        uint16_t want = (uint16_t)(to - from > FONT_CHUNK ? FONT_CHUNK : to - from);
        uint8_t st = cio_read(fd, buf, want, &got);
        if ((st != CIO_OK && st != CIO_OK_EOF) || got != want)
            return 0;
        from += got;
    }
    return 1;
}

WORD vdi_font_load(void)
{
    uint8_t hdr[FH_SIZE], buf[FONT_CHUNK];
    uint16_t left = FONT_BYTES, got;
    uint32_t dst;
    int16_t fd;

    if (!font_cio[0])
        return 0;
    fd = cio_open(font_cio, CIO_A_READ, 0);
    if (fd < 0)
        return 0;
    if (cio_read(fd, hdr, FH_SIZE, &got) != CIO_OK || got != FH_SIZE
        || !font_ok(hdr) || !font_skip(fd, FH_SIZE, be32(&hdr[FH_DAT_TABLE]))) {
        cio_close(fd);
        return 0;
    }
    /* One strip's worth of far memory, taken once however often a font is
     * loaded: far_alloc never gives any back. */
    if (!font_ram) {
        font_ram = far_alloc(FONT_BYTES);
        if (!font_ram) {
            cio_close(fd);
            return 0;
        }
    }
    dst = font_ram;
    while (left) {
        uint16_t want = left > FONT_CHUNK ? FONT_CHUNK : left;
        uint8_t st = cio_read(fd, buf, want, &got);
        if ((st != CIO_OK && st != CIO_OK_EOF) || got != want) {
            cio_close(fd);
            /* Half a strip is not a font: leave the face as it was.  The
             * memory stays taken, and the next load reuses it. */
            return 0;
        }
        far_put(dst, buf, got);
        dst += got;
        left = (uint16_t)(left - got);
    }
    cio_close(fd);
    memcpy(font_named, &hdr[FH_NAME], FONT_NAME_MAX - 1);
    font_named[FONT_NAME_MAX - 1] = '\0';
    font_loaded_id = (WORD)be16(&hdr[FH_FONT_ID]);
    font_have = 1;
    vdi_font = font_ram;
    dev_font_changed();
    return 1;
}

WORD vdi_font_faces(void)
{
    return (WORD)(font_have ? 2 : 1);
}

WORD vdi_font_id(WORD face)
{
    return (WORD)(face == FONT_LOADED && font_have ? font_loaded_id : FONT_ID_SYS);
}

/* vqt_name's 32 words: a face's name, one character to a word and zeros
 * after it.  The system face's carries its cell, which is the device's:
 * 8x8 on the VBXE and the page, 6x6 on ANTIC -- until phase 142 it said
 * 8x8 on both.  A digit each, because a cell is 6 or 8 (font.h), and put
 * in the words rather than the string, which stays constant: LoRAM has no
 * room for a writable copy. */
void vdi_font_name(WORD face, WORD *out)
{
    static const char sysname[] = "gem4xe system 8x8";
    const char *nm = sysname;
    WORD i, end = 0;

    if (face == FONT_LOADED && font_have)
        nm = font_named;
    for (i = 0; i < 32; i++) {
        if (!end && !nm[i])
            end = 1;
        out[i] = (WORD)(end ? 0 : (uint8_t)nm[i]);
    }
    if (nm == sysname) {
        out[14] = (WORD)('0' + FONT_W);
        out[16] = (WORD)('0' + FONT_H);
    }
}

/* vst_font's answer: the face now drawn with.  An id this driver does not
 * have is the system font, which is what the VDI contract asks for -- the
 * caller must use what comes back. */
WORD vdi_font_select(WORD id)
{
    uint32_t want = (uint32_t)(font_have && id == font_loaded_id && id != FONT_ID_SYS
                               ? font_ram : (uint32_t)vdi_face);
    WORD now = (WORD)(want == font_ram && font_have ? font_loaded_id : FONT_ID_SYS);

    if (want != vdi_font) {
        vdi_font = want;
        dev_font_changed();
    }
    return now;
}
