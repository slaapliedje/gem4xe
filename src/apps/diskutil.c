/* diskutil.c -- DISKUTIL: a disk formatted, or copied whole.
 *
 * Step 3 of docs/disk-plan.md, the window-based DUP: DUP.SYS's Format
 * disk and Duplicate disk, which the desktop lacked, as TOS's desktop does
 * them -- one dialog for both (the Falcon's DESKDISK.C, read as a
 * specification only).  It is a program of its own and not part of the
 * desktop, whose code must fit one place in a 512 KB machine's three
 * banks with about 4 KB to spare.  The desktop runs it with a tail: "F 2"
 * formats D2:, "C 1 2" copies D1: to D2:.  Run bare, it opens on Format.
 *
 * Underneath: Dgeom, Dformat and Drwsec (phase 155) to reach the drive,
 * and src/apps/mkfs.c (phase 156) to lay a file system on what Dformat
 * leaves.  The dialog is DISKUTIL.RSC (tools/diskrsc.py), and every word
 * a person reads is there.
 *
 * Large-data, so the copy's buffer, the resource and these statics are
 * far; a far buffer is addressed as a 32-bit number and never by pointer
 * arithmetic, which cc65816 does in sixteen bits (tools/ccbug).
 */
#include <string.h>
#include "gem.h"
#include "diskrsc.h"
#include "mkfs.h"

static OBJECT *tree;
static WORD dx, dy, dw, dh;
static WORD op;                     /* 0 Format, 1 Copy */
static WORD src = 1, dst = 1;       /* D1: .. D8: */
static UWORD map;                   /* the drives the DOS has, bit 0 D1: */
static uint8_t geo[DG_LEN];
static uint8_t secbuf[512];
static uint8_t bad[DF_BADLEN];
static char msg[160];
static UWORD cur_ss;                /* the sector size mkfs writes in */

/* ---- strings ------------------------------------------------------------ */

static char *str(WORD i)
{
    char *s;

    rsrc_gaddr(R_STRING, i, (void **)&s);
    return s;
}

/* Free string i into msg with `#` made drive d's number: held in a WORD
 * and narrowed once, at the store (B8, tools/ccbug). */
static char *with_drive(WORD i, WORD d)
{
    char *s = str(i);
    WORD k = 0, v;

    while (k < (WORD)sizeof msg - 1) {
        v = (uint8_t)s[k];
        if (!v)
            break;
        if (v == '#')
            v = '0' + d;
        msg[k++] = (char)v;
    }
    msg[k] = 0;
    return msg;
}

static WORD alert(WORD def, WORD i, WORD d)
{
    return form_alert(def, with_drive(i, d));
}

static WORD put_str(char *to, WORD at, const char *s)
{
    while (*s && at < DK_STATUS_W)
        to[at++] = *s++;
    return at;
}

static WORD put_num(char *to, WORD at, uint32_t n)
{
    char d[11];
    WORD k = 0;

    do {
        d[k++] = (char)('0' + (WORD)(n % 10));
        n /= 10;
    } while (n && k < 10);
    while (k > 0 && at < DK_STATUS_W)
        to[at++] = d[--k];
    return at;
}

/* ---- the dialog ----------------------------------------------------------- */

static void draw(WORD obj)
{
    objc_draw(tree, obj, MAX_DEPTH, dx, dy, dw, dh);
}

static void state(WORD obj, UWORD bit, WORD on)
{
    UWORD s = tree[obj].ob_state;

    if (on)
        s = (UWORD)(s | bit);
    else
        s = (UWORD)(s & ~bit);
    tree[obj].ob_state = s;
}

static WORD is_sel(WORD obj)
{
    UWORD s = tree[obj].ob_state;

    return (s & SELECTED) != 0;
}

/* The status line: the TEDINFO's own text, which the AES leaves alone and
 * objc_draw reads where it stands -- all 24 bits of both addresses, the
 * resource being far (src/apps/calc.c says what taking 16 cost). */
static char *status_text(void)
{
    TEDINFO *t = (TEDINFO *)(uint32_t)tree[DKSTATUS].ob_spec.index;

    return (char *)(uint32_t)t->te_ptext;
}

static void status_end(WORD at)
{
    char *t = status_text();

    while (at < DK_STATUS_W)
        t[at++] = ' ';
    t[DK_STATUS_W] = 0;
    draw(DKSTATUS);
}

static void status(WORD i, WORD d)
{
    status_end(put_str(status_text(), 0, with_drive(i, d)));
}

static void progress(UWORD done, UWORD total)
{
    WORD w = tree[DKBAR].ob_width;
    LONG f = total ? (LONG)w * done / total : 0;

    tree[DKFILL].ob_width = (WORD)f;
    draw(DKBAR);
}

static UWORD geo16(WORD at)
{
    UWORD lo = geo[at], hi = geo[at + 1];

    return (UWORD)(lo | (hi << 8));
}

/* The density a disk of this shape is, DF_SD to DF_DSDD; 0 for none. */
static WORD density_of(UWORD ss, UWORD n)
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

/* The destination asked what it is: its densities offered, the one its
 * disk has chosen, and what it is on the status line. */
static void probe(void)
{
    UWORD flags = 0, formats = 0, ss, n, i;
    WORD cur = 0, pick = 0, at;
    char *t;
    LONG r;

    graf_mouse(BUSYBEE, 0);
    r = Dgeom(dst, geo);
    graf_mouse(ARROW, 0);
    if (r == 0) {
        flags = geo16(4);
        formats = geo16(6);
        if (!(flags & DG_FLOPPY))
            formats = 0;
        cur = density_of(geo16(0), geo16(2));
    }
    for (i = 0; i < 4; i++) {
        WORD d = (WORD)(i + 1);
        WORD can = (formats & (1U << d)) != 0;

        state((WORD)(DKSD + i), DISABLED, op == 1 || !can);
        if (can && (d == cur || !pick))
            pick = d;
    }
    for (i = 0; i < 4; i++)
        state((WORD)(DKSD + i), SELECTED, (WORD)(i + 1) == pick);
    if (r != 0) {
        status(S_NODISK, dst);
    } else if (!(flags & DG_FLOPPY)) {
        status(S_NOTFLOPPY, dst);
    } else {
        ss = geo16(0);
        n = geo16(2);
        t = status_text();
        at = put_str(t, 0, with_drive(S_DRIVE, dst));
        at = put_num(t, at, n);
        at = put_str(t, at, str(S_SECTORS));
        at = put_num(t, at, ss);
        status_end(at);
    }
}

/* What the mode allows: the source row for a copy; the density, the file
 * system and the label for a format; the action button's word. */
static void setup(void)
{
    WORD i;

    /* Every drive is offered, and asked when it is chosen: the DOS's map
     * says D1: and D2: until somebody runs Dprobe, which costs a second
     * for each drive that is not there -- an absent one chosen says so
     * on the status line instead. */
    for (i = 0; i < 8; i++) {
        state((WORD)(DKFROM1 + i), DISABLED, op == 0);
        state((WORD)(DKFROM1 + i), SELECTED, i + 1 == src);
        state((WORD)(DKTO1 + i), SELECTED, i + 1 == dst);
    }
    state(DKFORMAT, SELECTED, op == 0);
    state(DKCOPY, SELECTED, op == 1);
    state(DKSDFS, DISABLED, op == 1);
    state(DKDOS2, DISABLED, op == 1);
    state(DKLABEL, DISABLED, op == 1);
    i = S_FORMAT;
    if (op)
        i = S_COPY;
    tree[DKGO].ob_spec.index = (LONG)(uint32_t)str(i);
    tree[DKFILL].ob_width = 0;
}

/* A failure as the alert that says it. */
static void fail(LONG r, WORD d)
{
    WORD a = A_FAILED;

    if (r == EDRVNR || r == EDRIVE)
        a = A_NODRIVE;
    else if (r == EWRPRO)
        a = A_WPROT;
    else if (r == EUNDEV)
        a = A_NOTFLOPPY;
    else if (r == EUNCMD)
        a = A_DENSITY;
    else if (r == ENSMEM)
        a = A_NOMEM;
    else if (r == MKFS_EBAD || r > 0)
        a = A_BAD;
    graf_mouse(ARROW, 0);
    alert(1, a, d);
}

/* ---- Format --------------------------------------------------------------- */

static int32_t put_sec(void *ctx, uint16_t sec, const uint8_t *buf, uint16_t len)
{
    (void)ctx;
    (void)len;
    return Drwsec(dst, 1, sec, 1, cur_ss, (void FAR *)buf);
}

/* The serial number and random ID SpartaDOS X tells disks apart by, from
 * the clock and the name, as Altirra makes them. */
static uint16_t stamp(const char *l)
{
    uint16_t h = (uint16_t)Tgettime();
    uint16_t d = (uint16_t)Tgetdate();

    h = (uint16_t)(h ^ (uint16_t)(d << 5));
    while (*l)
        h = (uint16_t)(h * 31 + (uint8_t)*l++);
    return h;
}

static void do_format(void)
{
    TEDINFO *lt = (TEDINFO *)(uint32_t)tree[DKLABEL].ob_spec.index;
    char *label = (char *)(uint32_t)lt->te_ptext;
    WORD dens = 0, i, at;
    UWORD each;
    MKFS m;
    int32_t n;
    LONG r;
    char *t;

    for (i = 0; i < 4; i++)
        if (is_sel((WORD)(DKSD + i)))
            dens = (WORD)(i + 1);
    if (!dens)
        return;                         /* nothing it can make */
    if (alert(2, A_ERASE, dst) != 1)
        return;
    graf_mouse(BUSYBEE, 0);
    progress(0, 1);
    status(S_FORMATTING, dst);
    r = Dformat(dst, dens, bad);
    if (r != 0) {
        fail(r, dst);
        return;
    }
    r = Dgeom(dst, geo);
    if (r != 0) {
        fail(r, dst);
        return;
    }
    status(S_WRITING, dst);
    cur_ss = geo16(0);
    memset(&m, 0, sizeof m);
    m.secsize = cur_ss;
    m.sectors = geo16(2);
    m.bad = bad;
    m.label = label;
    m.stamp = stamp(label);
    m.buf = secbuf;
    m.put = put_sec;
    n = is_sel(DKDOS2) ? mkfs_dos2(&m) : mkfs_sdfs(&m);
    if (n < 0) {
        fail(n, dst);
        return;
    }
    progress(1, 1);
    graf_mouse(ARROW, 0);
    each = cur_ss;                      /* a DOS 2 sector's link is 3 bytes */
    if (is_sel(DKDOS2))
        each = (UWORD)(each - 3);
    t = status_text();
    at = put_str(t, 0, with_drive(S_FORMATTED, dst));
    at = put_num(t, at, (uint32_t)n * each);
    at = put_str(t, at, str(S_FREE));
    status_end(at);
}

/* ---- Copy ------------------------------------------------------------------ */

#define CHUNK 16                    /* sectors a Drwsec, between the bar's steps */

/* `count` sectors from `first` between the drive and the buffer at the far
 * address `base`, CHUNK at a time, the bar stepping: 0, or the error. */
static LONG transfer(WORD d, WORD rw, UWORD first, UWORD count, UWORD ss,
                     uint32_t base, UWORD *done, UWORD total)
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
        progress(*done, total);
    }
    return 0;
}

static void do_copy(void)
{
    UWORD ss, n, per, first, cnt, done = 0, total, ss2, n2, flags2;
    WORD dens, single = src == dst, at;
    LONG r, room;
    uint32_t base;
    char *t;

    graf_mouse(BUSYBEE, 0);
    r = Dgeom(src, geo);
    graf_mouse(ARROW, 0);
    if (r != 0) {
        fail(r, src);
        return;
    }
    ss = geo16(0);
    n = geo16(2);
    dens = density_of(ss, n);
    if (!(geo16(4) & DG_FLOPPY) || !dens) {
        alert(1, A_CANTCOPY, src);
        return;
    }
    if (alert(2, A_REPLACE, dst) != 1)
        return;
    /* as much of the disk as memory holds, less a little for others; a
     * one-drive copy asks for a swap of disks each time it fills */
    room = Malloc(-1L) - 8192L;
    if (room > (LONG)ss * n)
        room = (LONG)ss * n;
    per = 0;
    if (room > 0)
        per = (UWORD)(room / ss);
    if (per < CHUNK) {
        alert(1, A_NOMEM, src);
        return;
    }
    r = Malloc((LONG)per * ss);
    if (r <= 0) {
        alert(1, A_NOMEM, src);
        return;
    }
    base = (uint32_t)r;
    total = (UWORD)(n * 2);
    progress(0, total);
    for (first = 1; first <= n; first = (UWORD)(first + per)) {
        cnt = (UWORD)(n - first + 1);
        if (cnt > per)
            cnt = per;
        if (single && first > 1 && alert(1, A_SOURCE, src) != 1)
            break;
        graf_mouse(BUSYBEE, 0);
        status(S_READING, src);
        r = transfer(src, 0, first, cnt, ss, base, &done, total);
        if (r != 0) {
            fail(r, src);
            break;
        }
        graf_mouse(ARROW, 0);
        if (single && alert(1, A_DEST, dst) != 1)
            break;
        graf_mouse(BUSYBEE, 0);
        if (first == 1) {
            /* the destination's disk: another shape is formatted to this
             * one first, and one the drive cannot make is refused */
            r = Dgeom(dst, geo);
            if (r != 0) {
                fail(r, dst);
                break;
            }
            ss2 = geo16(0);
            n2 = geo16(2);
            flags2 = geo16(4);
            if (!(flags2 & DG_FLOPPY)) {
                fail(EUNDEV, dst);
                break;
            }
            if (ss2 != ss || n2 != n) {
                status(S_FORMATTING, dst);
                r = Dformat(dst, dens, bad);
                if (r != 0) {
                    fail(r, dst);
                    break;
                }
            }
        }
        status(S_COPYING, dst);
        r = transfer(dst, 1, first, cnt, ss, base, &done, total);
        if (r != 0) {
            fail(r, dst);
            break;
        }
    }
    Mfree((void FAR *)(uint32_t)base);
    graf_mouse(ARROW, 0);
    if (done == total) {
        t = status_text();
        at = put_str(t, 0, str(S_COPIED));
        at = put_num(t, at, n);
        at = put_str(t, at, str(S_SECTORS));
        at = put_num(t, at, ss);
        status_end(at);
    }
}

/* ---- main ------------------------------------------------------------------ */

/* The tail the desktop gives: "F 2" or "C 1 2" -- a letter, then the
 * drives, for a copy the source first.  Anything missing keeps its
 * default. */
static void read_tail(const char *tail)
{
    WORD n = (WORD)(uint8_t)tail[0], i, v, got = 0;

    for (i = 1; i <= n && i < 128; i++) {
        v = (uint8_t)tail[i];
        if (v == 'C' || v == 'c')
            op = 1;
        else if (v == 'F' || v == 'f')
            op = 0;
        else if (v >= '1' && v <= '8') {
            v = (WORD)(v - '0');
            if (op == 1 && got == 0)
                src = v;
            else
                dst = v;
            got++;
        }
    }
    if (op == 1 && got == 1)
        dst = src;
}

int main(void)
{
    char cmd[130], tail[132];
    WORD obj, done = FALSE, i, start, cur;

    cmd[0] = 0;
    tail[0] = 0;
    appl_init();
    shel_read(cmd, tail);
    if (!rsrc_load("DISKUTIL.RSC")) {
        appl_exit();
        return 1;
    }
    rsrc_gaddr(R_TREE, ADDISK, (void **)&tree);
    /* the first drive there, and as the destination the first that is
     * not the one this was run from -- a formatter's default should not
     * be its own disk; the current one only when it is the only one */
    cur = Dgetdrv();
    map = (UWORD)Dsetdrv(cur);
    for (i = 0; i < 8 && !(map & (1U << i)); i++)
        ;
    if (i < 8)
        src = dst = (WORD)(i + 1);
    for (i = 0; i < 8; i++)
        if ((map & (1U << i)) && i != cur) {
            dst = (WORD)(i + 1);
            break;
        }
    read_tail(tail);
    state(DKSDFS, SELECTED, 1);         /* G4DOS's, with folders, unless asked */
    {
        /* the label's default, into a field whose room is the resource's
         * eight characters (tools/diskrsc.py says why) */
        TEDINFO *lt = (TEDINFO *)(uint32_t)tree[DKLABEL].ob_spec.index;
        char *l = (char *)(uint32_t)lt->te_ptext, *d = str(S_LABEL);

        for (i = 0; i < 8 && d[i]; i++)
            l[i] = d[i];
        l[i] = 0;
    }
    graf_mouse(ARROW, 0);
    form_center(tree, &dx, &dy, &dw, &dh);
    form_dial(FMD_START, 0, 0, 0, 0, dx, dy, dw, dh);
    setup();
    probe();
    draw(ROOT);
    while (!done) {
        start = 0;
        if (op == 0)
            start = DKLABEL;
        obj = form_do(tree, start) & 0x7FFF;
        if (obj >= DKTO1 && obj <= DKTO8) {
            dst = (WORD)(obj - DKTO1 + 1);
            probe();
            draw(DKDENBOX);
        } else if (obj >= DKFROM1 && obj <= DKFROM8) {
            src = (WORD)(obj - DKFROM1 + 1);
        } else if (obj == DKFORMAT || obj == DKCOPY) {
            op = obj == DKCOPY;
            setup();
            probe();
            draw(ROOT);
        } else if (obj == DKEXIT) {
            done = TRUE;
        } else if (obj == DKGO) {
            state(DKGO, SELECTED, 0);
            draw(DKGO);
            if (op)
                do_copy();
            else
                do_format();
        }
    }
    form_dial(FMD_FINISH, 0, 0, 0, 0, dx, dy, dw, dh);
    rsrc_free();
    appl_exit();
    return 0;
}
