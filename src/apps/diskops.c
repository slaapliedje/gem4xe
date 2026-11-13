/* diskops.c -- whole disks formatted, copied and made bootable, for
 * DISKUTIL and DUP: see diskops.h.  Taken out of diskutil.c (phases
 * 157-159) when DUP came to want the same (docs/disk-plan.md, part two).
 *
 * Large-data, as both programs are: these buffers are far, and a far
 * buffer is addressed as a 32-bit number, never by pointer arithmetic,
 * which cc65816 does in sixteen bits (tools/ccbug).
 */
#include <string.h>
#include "diskops.h"
#include "mkfs.h"

static uint8_t geo[DG_LEN];
static uint8_t secbuf[512];
static uint8_t bad[DF_BADLEN];
static uint8_t donor[768];          /* a system disk's sectors 1-3 */
static UWORD cur_ss;                /* the sector size being written */
static WORD cur_d;                  /* ...and the drive */

static UWORD geo16(WORD at)
{
    UWORD lo = geo[at], hi = geo[at + 1];

    return (UWORD)(lo | (hi << 8));
}

WORD dk_density(UWORD ss, UWORD n)
{
    if (ss == 128 && n == 720)
        return DF_SD;
    if (ss == 128 && n == 1040)
        return DF_ED;
    if (ss == 256 && n == 720)
        return DF_DD;
    if (ss == 256 && n == 1440)
        return DF_DSDD;
    return 0;
}

static void stage(const DK_HOOKS *h, WORD what, WORD d)
{
    if (h && h->stage)
        h->stage(what, d);
}

static void step(const DK_HOOKS *h, UWORD done, UWORD total)
{
    if (h && h->step)
        h->step(done, total);
}

/* ---- G4DOS on a disk (phase 159) -----------------------------------------
 * Its two files, G4DOS.SYS and SHELL.SYS, copied from a G4DOS disk in
 * another drive, and that disk's boot -- the header in sector 1's bytes
 * 0-8, its code from byte 48, and sectors 2 and 3 (tools/atr.py
 * boot_gem4xe) -- laid on the new disk's sector 1 around ITS OWN
 * file-system fields, with bytes 40-41 naming the new G4DOS.SYS's map,
 * which the boot loads by. */

static void path_of(char *p, WORD d, const char *name)
{
    WORD k = 0;

    p[0] = (char)('A' + d - 1);
    p[1] = ':';
    p[2] = '\\';
    while (name[k] && k < 12) {
        p[3 + k] = name[k];
        k++;
    }
    p[3 + k] = 0;
}

static WORD has_file(WORD d, const char *name)
{
    char p[16];
    LONG h;

    path_of(p, d, name);
    h = Fopen(p, 0);
    if (h < 0)
        return FALSE;
    Fclose((WORD)h);
    return TRUE;
}

WORD dk_system(UWORD map, WORD not)
{
    WORD d;

    for (d = 1; d <= 8; d++)
        if (d != not && (map & (1U << (d - 1)))
            && has_file(d, "G4DOS.SYS") && has_file(d, "SHELL.SYS"))
            return d;
    return 0;
}

/* `name` from drive a's root to drive b's, through the far buffer at
 * `buf` of `room` bytes: 0, or the error. */
static LONG copy_file(WORD a, WORD b, const char *name, uint32_t buf, LONG room)
{
    char p[16];
    LONG in, out, n, w, r = 0;

    path_of(p, a, name);
    in = Fopen(p, 0);
    if (in < 0)
        return in;
    path_of(p, b, name);
    out = Fcreate(p, 0);
    if (out < 0) {
        Fclose((WORD)in);
        return out;
    }
    for (;;) {
        n = Fread((WORD)in, room, (void FAR *)buf);
        if (n <= 0) {
            r = n;
            break;
        }
        w = Fwrite((WORD)out, n, (const void FAR *)buf);
        if (w != n) {
            r = EWRITF;
            if (w < 0)
                r = w;
            break;
        }
    }
    Fclose((WORD)in);
    if (Fclose((WORD)out) < 0 && r == 0)
        r = EWRITF;
    return r;
}

/* The map sector of G4DOS.SYS in the root of the disk in `d`, whose
 * sectors are cur_ss bytes: 0 when it is not there. */
static UWORD sys_map(WORD d)
{
    UWORD lo, hi, s, i;
    uint8_t *e;

    if (Drwsec(d, 0, 1, 1, cur_ss, secbuf) != 0)
        return 0;
    lo = secbuf[9];
    hi = secbuf[10];
    s = (UWORD)(lo | (hi << 8));            /* the root's map */
    if (!s || Drwsec(d, 0, s, 1, cur_ss, secbuf) != 0)
        return 0;
    lo = secbuf[4];
    hi = secbuf[5];
    s = (UWORD)(lo | (hi << 8));            /* its first data sector */
    if (!s || Drwsec(d, 0, s, 1, cur_ss, secbuf) != 0)
        return 0;
    for (i = 23; i + 23 <= cur_ss; i = (UWORD)(i + 23)) {
        e = secbuf + i;
        if (!e[0])
            break;                          /* the end of the directory */
        if ((e[0] & 0x08) && !memcmp(e + 6, "G4DOS   SYS", 11)) {
            lo = e[1];
            hi = e[2];
            return (UWORD)(lo | (hi << 8));
        }
    }
    return 0;
}

static LONG make_bootable(WORD src, WORD d)
{
    UWORD ss, m, i;
    uint8_t ours[128];
    LONG r, base, room;

    r = Dgeom(src, geo);
    if (r != 0)
        return r;
    ss = geo16(0);
    if (ss > 256)
        return EUNDEV;                      /* a floppy's boot, not a partition's */
    r = Drwsec(src, 0, 1, 3, ss, donor);
    if (r != 0)
        return r;
    room = Malloc(-1L) - 8192L;
    if (room > 32768L)
        room = 32768L;
    if (room < 1024L)
        return ENSMEM;
    base = Malloc(room);
    if (base <= 0)
        return ENSMEM;
    r = copy_file(src, d, "G4DOS.SYS", (uint32_t)base, room);
    if (r == 0)
        r = copy_file(src, d, "SHELL.SYS", (uint32_t)base, room);
    Mfree((void FAR *)(uint32_t)base);
    if (r != 0)
        return r;
    m = sys_map(d);
    if (!m)
        return EWRITF;
    r = Drwsec(d, 0, 1, 1, cur_ss, secbuf);
    if (r != 0)
        return r;
    for (i = 0; i < 128; i++)
        ours[i] = secbuf[i];
    for (i = 0; i <= 8; i++)                /* the boot's header */
        ours[i] = donor[i];
    for (i = 48; i < 128; i++)              /* ...and its code */
        ours[i] = donor[i];
    ours[40] = (uint8_t)m;                  /* the file it loads */
    ours[41] = (uint8_t)(m >> 8);
    for (i = 0; i < 128; i++)
        secbuf[i] = ours[i];
    r = Drwsec(d, 1, 1, 1, cur_ss, secbuf);
    if (r == 0)
        r = Drwsec(d, 1, 2, 1, cur_ss, (void FAR *)((uint32_t)donor + ss));
    if (r == 0)
        r = Drwsec(d, 1, 3, 1, cur_ss, (void FAR *)((uint32_t)donor + 2 * (uint32_t)ss));
    return r;
}

LONG dk_bootable(WORD d, WORD boot)
{
    LONG r = Dgeom(d, geo);

    if (r != 0)
        return r;
    cur_ss = geo16(0);
    if (cur_ss > 256)
        return EUNDEV;
    r = Drwsec(d, 0, 1, 1, cur_ss, secbuf);
    if (r != 0)
        return r;
    if (secbuf[7] != 0x80)
        return EUNDEV;                      /* not a floppy's SDFS */
    return make_bootable(boot, d);
}

/* ---- Format ----------------------------------------------------------------- */

static int32_t put_sec(void *ctx, uint16_t sec, const uint8_t *buf, uint16_t len)
{
    (void)ctx;
    (void)len;
    return Drwsec(cur_d, 1, sec, 1, cur_ss, (void FAR *)buf);
}

/* The serial number and random ID SpartaDOS X tells disks apart by, from
 * the clock and the name, as Altirra makes them. */
static uint16_t stamp(const char *l)
{
    uint16_t h = (uint16_t)Tgettime();
    uint16_t d = (uint16_t)Tgetdate();

    h = (uint16_t)(h ^ (uint16_t)(d << 5));
    while (l && *l)
        h = (uint16_t)(h * 31 + (uint8_t)*l++);
    return h;
}

LONG dk_format(const DK_HOOKS *h, WORD d, WORD dens, WORD dos2,
               const char *label, WORD boot, uint32_t *free)
{
    DISKINFO di;
    MKFS m;
    int32_t n;
    UWORD each;
    LONG r;

    *free = 0;
    stage(h, DK_FORMAT, d);
    step(h, 0, 1);
    r = Dformat(d, dens, bad);
    if (r != 0)
        return r;
    r = Dgeom(d, geo);
    if (r != 0)
        return r;
    stage(h, DK_LAY, d);
    cur_d = d;
    cur_ss = geo16(0);
    memset(&m, 0, sizeof m);
    m.secsize = cur_ss;
    m.sectors = geo16(2);
    m.bad = bad;
    m.label = label;
    m.stamp = stamp(label);
    m.buf = secbuf;
    m.put = put_sec;
    if (dos2)
        n = mkfs_dos2(&m);
    else
        n = mkfs_sdfs(&m);
    if (n < 0)
        return n;
    if (boot) {
        stage(h, DK_SYSTEM, d);
        r = make_bootable(boot, d);
        if (r != 0)
            return r;
        if (Dfree(&di, d) == 0)
            n = di.b_free;
    }
    each = cur_ss;                          /* a DOS 2 sector's link is 3 bytes */
    if (dos2)
        each = (UWORD)(each - 3);
    *free = (uint32_t)n * each;
    step(h, 1, 1);
    return 0;
}

/* ---- Copy --------------------------------------------------------------------- */

#define CHUNK 16                    /* sectors a Drwsec, between the bar's steps */

LONG dk_shape(WORD src, UWORD *ss, UWORD *n)
{
    LONG r = Dgeom(src, geo);

    if (r != 0)
        return r;
    *ss = geo16(0);
    *n = geo16(2);
    if (!(geo16(4) & DG_FLOPPY) || !dk_density(*ss, *n))
        return DK_ESHAPE;
    return 0;
}

/* `count` sectors from `first` between the drive and the buffer at the far
 * address `base`, CHUNK at a time, the bar stepping: 0, or the error. */
static LONG transfer(const DK_HOOKS *h, WORD d, WORD rw, UWORD first, UWORD count,
                     UWORD ss, uint32_t base, UWORD *done, UWORD total)
{
    UWORD k, c;
    LONG r;

    for (k = 0; k < count; k += c) {
        c = (UWORD)(count - k);
        if (c > CHUNK)
            c = CHUNK;
        r = Drwsec(d, rw, (UWORD)(first + k), c, ss,
                   (void FAR *)(base + (uint32_t)k * ss));
        if (r != 0)
            return r;
        *done = (UWORD)(*done + c);
        step(h, *done, total);
    }
    return 0;
}

static WORD swap(const DK_HOOKS *h, WORD which, WORD d)
{
    return h && h->swap ? h->swap(which, d) : TRUE;
}

LONG dk_copy(const DK_HOOKS *h, WORD src, WORD dst)
{
    UWORD ss, n, per, first, cnt, done = 0, total, ss2, n2;
    WORD dens, single = src == dst;
    LONG r, room;
    uint32_t base;

    r = dk_shape(src, &ss, &n);
    if (r != 0)
        return r;
    dens = dk_density(ss, n);
    /* as much of the disk as memory holds, less a little for others; a
     * one-drive copy asks for a swap of disks each time it fills */
    room = Malloc(-1L) - 8192L;
    if (room > (LONG)ss * n)
        room = (LONG)ss * n;
    per = 0;
    if (room > 0)
        per = (UWORD)(room / ss);
    if (per < CHUNK)
        return ENSMEM;
    r = Malloc((LONG)per * ss);
    if (r <= 0)
        return ENSMEM;
    base = (uint32_t)r;
    total = (UWORD)(n * 2);
    step(h, 0, total);
    for (first = 1, r = 0; first <= n && r == 0; first = (UWORD)(first + per)) {
        cnt = (UWORD)(n - first + 1);
        if (cnt > per)
            cnt = per;
        if (single && first > 1 && !swap(h, DK_SOURCE, src)) {
            r = DK_ESTOP;
            break;
        }
        stage(h, DK_READ, src);
        r = transfer(h, src, 0, first, cnt, ss, base, &done, total);
        if (r != 0)
            break;
        if (single && !swap(h, DK_DEST, dst)) {
            r = DK_ESTOP;
            break;
        }
        if (first == 1) {
            /* the destination's disk: another shape is formatted to this
             * one first, and one the drive cannot make is refused */
            r = Dgeom(dst, geo);
            if (r != 0)
                break;
            ss2 = geo16(0);
            n2 = geo16(2);
            if (!(geo16(4) & DG_FLOPPY)) {
                r = EUNDEV;
                break;
            }
            if (ss2 != ss || n2 != n) {
                stage(h, DK_FORMAT, dst);
                r = Dformat(dst, dens, bad);
                if (r != 0)
                    break;
            }
        }
        stage(h, DK_WRITE, dst);
        r = transfer(h, dst, 1, first, cnt, ss, base, &done, total);
    }
    Mfree((void FAR *)(uint32_t)base);
    return r;
}
