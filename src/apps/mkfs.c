/* mkfs.c -- blank file systems for DISKUTIL: see mkfs.h.
 *
 * A disk whose drive found bad sectors gets neither: DOS 2's own FORMAT
 * refuses one (error 173, "bad sectors at format time"), and a file
 * system mapped around a failing disk is not one to keep anything on.
 */
#include <string.h>
#include "mkfs.h"

/* A byte's bits from the left, as every bitmap here counts them: a
 * table, because `0x80 >> n` is a signed shift by a variable, which
 * cc65816 gets wrong (B12, tools/ccbug/README.md). */
static const uint8_t bit_of[8] = { 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01 };

static int32_t put(const MKFS *m, uint16_t sec, uint16_t len)
{
    return m->put(m->ctx, sec, m->buf, len);
}

static void put16(uint8_t *b, uint16_t at, uint16_t v)
{
    b[at] = (uint8_t)v;
    b[at + 1] = (uint8_t)(v >> 8);
}

/* Whether the drive found any bad sector: the list's first word is not
 * the $FFFF that ends it. */
static int has_bad(const MKFS *m)
{
    const uint8_t *p = m->bad;
    uint16_t lo, hi;

    if (!p)
        return 0;
    lo = p[0];
    hi = p[1];
    return !(lo == 0xFF && hi == 0xFF);
}

static void set_bit(uint8_t *b, uint16_t k)
{
    b[k >> 3] |= bit_of[k & 7];
}

/* ---- SDFS ---------------------------------------------------------------
 * Altirra's InitNew (diskfssdx2.cpp): the boot sectors, the bitmap, then
 * the root directory -- a map sector pointing at one data sector, which
 * holds the directory's header.  The bitmap's bit SET is a FREE sector,
 * sector 0's bit is never free, and every sector after the root's is.
 * A 512-byte volume, which a hard disk's partition is, has one boot
 * sector where a floppy has three, its size byte is 1 rather than the
 * size, and its boot header loads at $0400 and starts at $07E0, which
 * CLX 1.9 checks for (Altirra's code says $0400; its comment, $0440). */

#define SD_ENTRY 23         /* a directory entry */

int32_t mkfs_sdfs(const MKFS *m)
{
    uint8_t *b = m->buf;
    uint16_t ss = m->secsize, total = m->sectors;
    uint16_t shift, bmc, boot, bms, rmap, rdata, i, s, lo, n, len;
    uint32_t base, span, top;
    const char *l;
    int32_t e;
    char c;

    if (has_bad(m))
        return MKFS_EBAD;
    if (ss == 128)
        shift = 7;
    else if (ss == 256)
        shift = 8;
    else if (ss == 512)
        shift = 9;
    else
        return MKFS_EGEOM;
    bmc = (uint16_t)((total >> (shift + 3)) + 1);
    boot = ss >= 512 ? 1 : 3;
    bms = (uint16_t)(boot + 1);
    rmap = (uint16_t)(bms + bmc);
    rdata = (uint16_t)(rmap + 1);
    if (rdata >= total)
        return MKFS_EGEOM;

    /* the bitmap: bitmap sector i holds the bits of sectors i * ss * 8 on */
    span = (uint32_t)ss << 3;
    for (i = 0; i < bmc; i++) {
        memset(b, 0, ss);
        base = span * i;
        top = base + span - 1;
        if (top > total)
            top = total;
        lo = rdata + 1;
        if (base > lo)
            lo = (uint16_t)base;
        for (s = lo; (uint32_t)s <= top && s >= lo; s++)
            set_bit(b, (uint16_t)(s - base));
        e = put(m, (uint16_t)(bms + i), ss);
        if (e < 0)
            return e;
    }
    n = (uint16_t)(total - rdata);          /* the free sectors */

    /* the root: its map, and its one data sector with the header in it */
    memset(b, 0, ss);
    put16(b, 4, rdata);
    e = put(m, rmap, ss);
    if (e < 0)
        return e;
    memset(b, 0, ss);
    b[0] = 0x28;                            /* in use, a directory */
    b[3] = SD_ENTRY;                        /* its length: the header */
    memcpy(b + 6, "MAIN       ", 11);       /* name and extension */
    e = put(m, rdata, ss);
    if (e < 0)
        return e;

    /* the second and third boot sectors: flag the boot failed, return */
    if (boot == 3) {
        memset(b, 0, 128);
        b[0] = 0xA9;                        /* lda #$60 */
        b[1] = 0x60;
        b[2] = 0x8D;                        /* sta $0740 */
        b[3] = 0x40;
        b[4] = 0x07;
        b[5] = 0x38;                        /* sec */
        b[6] = 0x60;                        /* rts */
        e = put(m, 2, 128);
        if (e < 0)
            return e;
        memset(b, 0, 128);
        e = put(m, 3, 128);
        if (e < 0)
            return e;
    }

    /* sector 1, last: what makes it a disk */
    len = ss >= 512 ? 512 : 128;
    memset(b, 0, len);
    b[1] = (uint8_t)boot;
    if (ss >= 512) {
        b[3] = 0x04;                        /* load at $0400 ... */
        b[4] = 0xE0;                        /* ... start at $07E0 */
        b[5] = 0x07;
        b[6] = 0x4C;                        /* launch: jmp $0440 */
        b[7] = 0x40;
        b[8] = 0x04;
    } else {
        b[3] = 0x30;                        /* load at $3000 ... */
        b[4] = 0x40;                        /* ... start at $0740 */
        b[5] = 0x07;
        b[6] = 0x4C;                        /* launch: jmp $3080 */
        b[7] = 0x80;
        b[8] = 0x30;
    }
    put16(b, 9, rmap);
    put16(b, 11, total);
    put16(b, 13, n);
    b[15] = (uint8_t)bmc;
    put16(b, 16, bms);
    put16(b, 18, (uint16_t)(rdata + 1));    /* where to look for room */
    put16(b, 20, (uint16_t)(rdata + 1));
    memset(b + 22, ' ', 8);
    l = m->label;
    for (i = 0; l && *l && i < 8; l++) {    /* Altirra's rule for the name */
        c = *l;
        if (c >= 'a' && c <= 'z')
            c = (char)(c - 32);
        if (c == '.')
            break;
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))
            b[22 + i++] = (uint8_t)c;
    }
    if (b[22] == ' ')
        memcpy(b + 22, "NEWDISK", 7);
    b[30] = 1;                              /* tracks: 1, as SpartaDOS writes */
    b[31] = (uint8_t)(ss >= 512 ? 1 : ss);  /* the size: $80, $00, or 1 */
    b[32] = 0x21;                           /* the format: SpartaDOS 2.1 */
    put16(b, 33, ss);
    put16(b, 35, (uint16_t)((ss - 4) >> 1));    /* entries in a map sector */
    b[37] = 1;                              /* physical sectors a logical */
    put16(b, 38, m->stamp);                 /* serial number, random ID */
    b[64] = 0x60;                           /* the boot's code: rts */
    e = put(m, 1, len);
    if (e < 0)
        return e;
    return n;
}

/* ---- DOS 2 --------------------------------------------------------------
 * Altirra's InitNew and Flush (diskfsdos2.cpp).  The boot sectors, the
 * directory (361-368), the VTOC at 360: a code, the sectors there are to
 * use, the free ones, and from byte 10 a bit a sector from 0 up, SET
 * free.  Taken: 0, the boot sectors 1-3, the directory and the VTOC, and
 * 720 except on MyDOS.
 *
 * DOS 2.5's enhanced disk keeps VTOC1's 90 bytes of bits (sectors 0-719)
 * and puts the bits of 48-1023 in VTOC2 at sector 1024, with the upper
 * half's free count after them.  MyDOS's VTOC grows down from 360 as the
 * disk grows -- in pairs of 128-byte sectors over 943 sectors, a 256-byte
 * one at a time from 1024 -- and its code says how many. */

static uint16_t d_total, d_vlo;
static uint8_t d_mydos, d_dos25;

static int d2_free(uint16_t s)
{
    if (s < 4 || s > d_total)
        return 0;
    if (s >= 361 && s <= 368)
        return 0;
    if (s >= d_vlo && s <= 360)
        return 0;
    if (!d_mydos && s == 720)
        return 0;
    return 1;
}

static uint16_t d2_count(uint16_t lo, uint16_t hi)
{
    uint16_t s, n = 0;

    for (s = lo; s <= hi; s++)
        if (d2_free(s))
            n++;
    return n;
}

int32_t mkfs_dos2(const MKFS *m)
{
    uint8_t *b = m->buf;
    uint16_t ss = m->secsize, total = m->sectors;
    uint16_t count = 1, code = 2, i, s, lo, hi, last, n1, n2 = 0, avail;
    uint32_t big, first, end;
    int32_t e;

    if (has_bad(m))
        return MKFS_EBAD;
    if ((ss != 128 && ss != 256) || total < 720)
        return MKFS_EGEOM;
    d_total = total;
    d_dos25 = (uint8_t)(ss == 128 && total == 1040);
    d_mydos = (uint8_t)(!d_dos25 && !(ss == 128 && total == 720));
    if (d_mydos) {
        big = (uint32_t)total + 1 + 80 + 2047;
        if (ss == 128 && total > 943) {
            count = (uint16_t)((big >> 11) << 1);
            code = (uint16_t)((count >> 1) + 2);
        } else if (ss == 256 && total >= 1024) {
            count = (uint16_t)(big >> 11);
            code = (uint16_t)(count + 2);
        }
    }
    d_vlo = (uint16_t)(361 - count);        /* the VTOC: d_vlo to 360 */

    /* the boot sectors: a disk with no DOS on it, which says BOOT ERROR --
     * one sector loaded at $0700, DOSINI at its RTS, and the boot's code
     * a SEC and an RTS: the carry is the OS's word for a failed boot */
    memset(b, 0, 128);
    b[1] = 1;
    b[3] = 0x07;
    b[4] = 0x07;
    b[5] = 0x07;
    b[6] = 0x38;
    b[7] = 0x60;
    e = put(m, 1, 128);
    if (e < 0)
        return e;
    memset(b, 0, 128);
    for (s = 2; s <= 3; s++) {
        e = put(m, s, 128);
        if (e < 0)
            return e;
    }

    /* the directory: empty */
    memset(b, 0, ss);
    for (s = 361; s <= 368; s++) {
        e = put(m, s, ss);
        if (e < 0)
            return e;
    }

    /* DOS 2.5's VTOC2: the bits of 48-1023, then 720-1023's free count */
    if (d_dos25) {
        memset(b, 0, 128);
        for (s = 48; s < 1024; s++)
            if (d2_free(s))
                set_bit(b, (uint16_t)(s - 48));
        n2 = d2_count(720, 1023);
        put16(b, 122, n2);
        e = put(m, 1024, 128);
        if (e < 0)
            return e;
    }

    /* the VTOC, last: sector 360 - i holds bytes i * ss on of it, the
     * bits from byte 10; DOS 2.5's VTOC1 only those of 0-719 */
    last = d_dos25 ? 719 : total;
    n1 = d2_count(1, last);
    if (d_dos25)
        avail = 707;
    else
        avail = (uint16_t)(total - count - 11 - (d_mydos ? 0 : 1));
    for (i = 0; i < count; i++) {
        memset(b, 0, ss);
        /* the sectors whose bits fall in this one: from bit
         * (i * ss - 10) * 8 to bit ((i + 1) * ss - 10) * 8 - 1 */
        first = (uint32_t)ss * i;
        first = first > 10 ? (first - 10) << 3 : 0;
        end = (((uint32_t)ss * (i + 1) - 10) << 3) - 1;
        if (end > last)
            end = last;
        lo = (uint16_t)first;
        hi = (uint16_t)end;
        for (s = lo; s <= hi && s >= lo && first <= end; s++)
            if (d2_free(s))
                set_bit(b, (uint16_t)(((uint32_t)s + 80) - ((uint32_t)ss * i << 3)));
        if (i == 0) {
            b[0] = (uint8_t)code;
            put16(b, 1, avail);
            put16(b, 3, n1);
        }
        e = put(m, (uint16_t)(360 - i), ss);
        if (e < 0)
            return e;
    }
    return (int32_t)n1 + n2;
}
