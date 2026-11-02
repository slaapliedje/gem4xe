/* sdfs.c -- SDFS in C (sdfs.h says what and why; docs/sdfs-plan.md).
 *
 * THE DISK.  Sector 1, 128 bytes even on a 256-byte disk, is the
 * superblock: +9 the root directory's first map page, +11 the sectors on
 * the disk, +13 how many are free, +15 how many sectors the bitmap takes,
 * +16 where it starts, +31 the sector size ($80 for 128, 0 for 256).  The
 * bitmap has a bit a sector, SET when FREE: sector s at byte s/8, bit
 * $80 >> (s mod 8).  A file is a chain of MAP PAGES -- +0 the next page,
 * +2 the previous, then the data sectors in order, two bytes each, 126 to
 * a page of 256 and 62 to one of 128 -- and a directory is a file of
 * 23-byte entries: status, first map page, length (three bytes), name
 * (eight), extension (three), day, month, year, hour, minute, second.
 * Entry 0 is the directory's header: its length is the directory's, its
 * map is the PARENT's, and its name is its own.  A zero status ends a
 * directory; one without SD_INUSE is a free slot.
 *
 * THE CACHE holds SD_CACHE sectors, each tagged with its unit, its
 * number, whether it has changed, and its KIND: file data, map page,
 * directory, bitmap, superblock.  A changed sector is written when the
 * caller syncs, or when its slot is wanted for another -- and then every
 * changed sector of a lower kind on that unit is written FIRST, so the
 * disk is always written in the order sdfs.h promises: data before the
 * map pages that name it, those before the directory that names them,
 * all of it before the bitmap that says what is used.
 *
 * NOTHING HERE IS STATIC, and every pointer is FAR: the state is the
 * caller's block (sdfs.h), and on the Atari that is far memory -- a near
 * pointer to anything in it would be truncated without a word
 * (Calypsi, docs: far-address-in-a-near-slot).
 */
#include "sdfs.h"

#define SK_DATA   0
#define SK_MAP    1
#define SK_DIR    2
#define SK_BMAP   3
#define SK_SUPER  4

#define E_STATUS  0
#define E_MAP     1
#define E_SIZE    3
#define E_NAME    6
#define E_STAMP   17

/* ---- small things ----------------------------------------------------- */

static void fcopy(uint8_t FAR *d, const uint8_t FAR *s, uint16_t n)
{
    while (n--)
        *d++ = *s++;
}

static void fzero(uint8_t FAR *d, uint16_t n)
{
    while (n--)
        *d++ = 0;
}

static uint16_t get16(const uint8_t FAR *p)
{
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static void put16(uint8_t FAR *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static SD_UNIT FAR *unit_of(SDFS FAR *s, uint8_t u)
{
    return &s->units[u - 1];
}

static uint16_t secsize(SDFS FAR *s, uint8_t u)
{
    return (uint16_t)1 << unit_of(s, u)->shift;
}

/* sectors 1-3 are the boot sectors, 128 bytes on every floppy */
static uint16_t seclen(SDFS FAR *s, uint8_t u, uint16_t sec)
{
    return sec <= 3 ? 128 : secsize(s, u);
}

/* data sectors a map page names: 126 for 256-byte sectors, 62 for 128 */
static uint16_t perm(SDFS FAR *s, uint8_t u)
{
    return (uint16_t)((secsize(s, u) - 4) >> 1);
}

/* ---- the cache -------------------------------------------------------- */

static int16_t c_write(SDFS FAR *s, int16_t i)
{
    SD_SLOT FAR *sl = &s->slots[i];
    int16_t e;

    if (!sl->dirty)
        return 0;
    e = sd_dev(s, sl->unit, sl->sec, s->buf[i], seclen(s, sl->unit, sl->sec), 1);
    if (e < 0)
        return e;
    sl->dirty = 0;
    return 0;
}

/* Every changed sector of unit u whose kind is `upto` or lower, lowest
 * kind first. */
static int16_t c_flush(SDFS FAR *s, uint8_t u, uint8_t upto)
{
    uint8_t k;
    int16_t i, e;

    for (k = 0; k <= upto; k++)
        for (i = 0; i < SD_CACHE; i++)
            if (s->slots[i].unit == u && s->slots[i].kind == k
                && s->slots[i].dirty) {
                e = c_write(s, i);
                if (e < 0)
                    return e;
            }
    return 0;
}

/* The slot holding sector `sec` of unit u, read from the disk -- or, with
 * `fresh`, a sector of zeros the caller is about to fill.  A slot wanted
 * for it that holds a changed sector is written first, after everything
 * of a lower kind on its unit.  A slot index, or a negative error. */
static int16_t c_get(SDFS FAR *s, uint8_t u, uint16_t sec, uint8_t kind,
                     uint8_t fresh)
{
    SD_SLOT FAR *sl;
    int16_t i, v = -1;
    uint8_t oldest = 0, a;

    s->age++;
    for (i = 0; i < SD_CACHE; i++) {
        sl = &s->slots[i];
        if (sl->unit == u && sl->sec == sec) {
            sl->age = s->age;
            sl->kind = kind;
            if (fresh)
                fzero(s->buf[i], SD_SECMAX);
            return i;
        }
    }
    for (i = 0; i < SD_CACHE; i++) {
        sl = &s->slots[i];
        if (!sl->unit) {
            v = i;
            break;
        }
        a = (uint8_t)(s->age - sl->age);
        if (v < 0 || a > oldest) {
            v = i;
            oldest = a;
        }
    }
    sl = &s->slots[v];
    if (sl->unit && sl->dirty) {
        int16_t r;
        if (sl->kind > 0) {
            r = c_flush(s, sl->unit, (uint8_t)(sl->kind - 1));
            if (r < 0)
                return r;
        }
        r = c_write(s, v);
        if (r < 0)
            return r;
    }
    sl->unit = 0;
    if (fresh)
        fzero(s->buf[v], SD_SECMAX);
    else {
        int16_t r = sd_dev(s, u, sec, s->buf[v], seclen(s, u, sec), 0);
        if (r < 0)
            return r;
    }
    sl->unit = u;
    sl->sec = sec;
    sl->kind = kind;
    sl->dirty = 0;
    sl->age = s->age;
    return v;
}

static void c_dirty(SDFS FAR *s, int16_t i)
{
    s->slots[i].dirty = 1;
}

/* Forget a unit's sectors, changed or not: the disk is not that disk. */
void sd_forget(SDFS FAR *s, uint8_t u)
{
    int16_t i;

    if (u < 1 || u > SD_UNITS)
        return;
    for (i = 0; i < SD_CACHE; i++)
        if (s->slots[i].unit == u) {
            s->slots[i].unit = 0;
            s->slots[i].dirty = 0;
        }
    for (i = 0; i < SD_FILES; i++)
        if (s->files[i].used && s->files[i].unit == u)
            s->files[i].used = 0;
    for (i = 0; i < SD_DIRS; i++)
        if (s->dirs[i].used && s->dirs[i].unit == u)
            s->dirs[i].used = 0;
    unit_of(s, u)->mounted = 0;
    unit_of(s, u)->fdelta = 0;
}

void sd_recheck(SDFS FAR *s, uint8_t u)
{
    if (u >= 1 && u <= SD_UNITS)
        unit_of(s, u)->fresh = 0;
}

void sd_init(SDFS FAR *s)
{
    fzero((uint8_t FAR *)s, (uint16_t)((uint8_t FAR *)&s->buf[0][0]
                                       - (uint8_t FAR *)s));
}

/* ---- mounting --------------------------------------------------------- */

/* Unit u's superblock, read again when sd_recheck says the disk may have
 * been changed since the last call; one that has is forgotten before
 * anything is written to it.  Every call that names a path starts here. */
static int16_t mount(SDFS FAR *s, uint8_t u)
{
    SD_UNIT FAR *un;
    uint8_t FAR *b;
    int16_t i, e;
    uint16_t root, total, bms;
    uint8_t shift, bmc;

    if (u < 1 || u > SD_UNITS)
        return SD_EDRIVE;
    un = unit_of(s, u);
    if (un->mounted && un->fresh)
        return 0;
    /* sector 1 again from the disk, unless it has changes of ours */
    for (i = 0; i < SD_CACHE; i++)
        if (s->slots[i].unit == u && s->slots[i].sec == 1
            && !s->slots[i].dirty)
            s->slots[i].unit = 0;
    if (!un->mounted)
        un->shift = 7;              /* sector 1 is 128 bytes regardless */
    i = c_get(s, u, 1, SK_SUPER, 0);
    if (i < 0) {
        sd_forget(s, u);
        return i;
    }
    b = s->buf[i];
    if (b[7] != 0x80 && b[7] != 0x40) {
        sd_forget(s, u);
        return SD_EDRIVE;           /* not SDFS */
    }
    shift = b[31] == 0x80 ? 7 : (b[31] == 0 ? 8 : 0);
    root = get16(b + 9);
    total = get16(b + 11);
    bmc = b[15];
    bms = get16(b + 16);
    if (!shift || !root || !total) {
        sd_forget(s, u);
        return SD_EDRIVE;
    }
    if (un->mounted && (un->shift != shift || un->root != root
                        || un->total != total || un->bm_start != bms)) {
        sd_forget(s, u);            /* another disk */
        e = mount(s, u);
        return e;
    }
    if (!un->mounted) {
        un->shift = shift;
        un->root = root;
        un->total = total;
        un->bm_count = bmc;
        un->bm_start = bms;
        un->hint = 1;
        un->fdelta = 0;
        un->mounted = 1;
    }
    un->fresh = 1;
    return 0;
}

/* ---- the bitmap ------------------------------------------------------- */

/* sector `sec`'s bit: its slot's buffer offset in *off, the mask in *mask */
static int16_t bm_at(SDFS FAR *s, uint8_t u, uint16_t sec, uint16_t *off,
                     uint8_t *mask)
{
    SD_UNIT FAR *un = unit_of(s, u);
    uint16_t byte = sec >> 3;
    int16_t i;

    i = c_get(s, u, (uint16_t)(un->bm_start + (byte >> un->shift)), SK_BMAP, 0);
    if (i < 0)
        return i;
    *off = byte & (uint16_t)(secsize(s, u) - 1);
    *mask = (uint8_t)(0x80 >> (sec & 7));
    return i;
}

/* A free sector, taken: the first at or after the hint, round once. */
static int32_t alloc_sec(SDFS FAR *s, uint8_t u)
{
    SD_UNIT FAR *un = unit_of(s, u);
    uint16_t sec = un->hint, n, off;
    uint8_t mask;
    int16_t i;

    if (sec < 1 || sec > un->total)
        sec = 1;
    for (n = 0; n < un->total; n++) {
        i = bm_at(s, u, sec, &off, &mask);
        if (i < 0)
            return i;
        if (s->buf[i][off] & mask) {
            s->buf[i][off] &= (uint8_t)~mask;
            c_dirty(s, i);
            un->fdelta--;
            un->hint = (uint16_t)(sec + 1);
            return sec;
        }
        sec++;
        if (sec > un->total)
            sec = 1;
    }
    return SD_EACCDN;               /* full */
}

static int16_t free_sec(SDFS FAR *s, uint8_t u, uint16_t sec)
{
    uint16_t off;
    uint8_t mask;
    int16_t i = bm_at(s, u, sec, &off, &mask);

    if (i < 0)
        return i;
    if (!(s->buf[i][off] & mask)) {
        s->buf[i][off] |= mask;
        c_dirty(s, i);
        unit_of(s, u)->fdelta++;
    }
    return 0;
}

/* ---- chains ----------------------------------------------------------- */

/* The k-th data sector of the chain whose first map page is `first`: 0
 * where there is none -- or, with `grow`, one made there, a sector of
 * zeros of kind `kind`, with the map pages it needs, linked both ways.
 * *mp and *mpn are a page of the chain and its place in it, kept between
 * calls by an open file so that reading on does not walk from the start
 * every time; mpn $FFFF means none. */
static int32_t ch_sec(SDFS FAR *s, uint8_t u, uint16_t first, uint16_t k,
                      uint8_t grow, uint8_t kind, uint16_t *mp, uint16_t *mpn)
{
    uint16_t pm = perm(s, u), page = k / pm, idx = k % pm;
    uint16_t p, pn, nx, d;
    int16_t i;
    int32_t a;

    if (*mpn != 0xFFFF && *mpn <= page) {
        p = *mp;
        pn = *mpn;
    } else {
        p = first;
        pn = 0;
    }
    while (pn < page) {
        i = c_get(s, u, p, SK_MAP, 0);
        if (i < 0)
            return i;
        nx = get16(s->buf[i]);
        if (!nx) {
            if (!grow)
                return 0;
            a = alloc_sec(s, u);
            if (a < 0)
                return a;
            i = c_get(s, u, (uint16_t)a, SK_MAP, 1);   /* the new page */
            if (i < 0)
                return i;
            put16(s->buf[i] + 2, p);
            c_dirty(s, i);
            i = c_get(s, u, p, SK_MAP, 0);             /* linked from this */
            if (i < 0)
                return i;
            put16(s->buf[i], (uint16_t)a);
            c_dirty(s, i);
            nx = (uint16_t)a;
        }
        p = nx;
        pn++;
    }
    *mp = p;
    *mpn = pn;
    i = c_get(s, u, p, SK_MAP, 0);
    if (i < 0)
        return i;
    d = get16(s->buf[i] + 4 + 2 * idx);
    if (d || !grow)
        return d;
    a = alloc_sec(s, u);
    if (a < 0)
        return a;
    i = c_get(s, u, (uint16_t)a, kind, 1);
    if (i < 0)
        return i;
    c_dirty(s, i);                  /* zeros, on the disk at the next sync */
    i = c_get(s, u, p, SK_MAP, 0);
    if (i < 0)
        return i;
    put16(s->buf[i] + 4 + 2 * idx, (uint16_t)a);
    c_dirty(s, i);
    return a;
}

/* n bytes at offset `off` of a chain, read or written; written past the
 * chain's last sector, it grows.  The bytes moved -- fewer than n when the
 * disk filled or the chain ended part way -- or, if nothing moved, a
 * negative error.  Part of a write is what is kept: the sectors it took
 * are exactly the ones the bytes moved are in (and at most an empty map
 * page past them), so a file's length can say so. */
static int32_t ch_io(SDFS FAR *s, uint8_t u, uint16_t first, uint32_t off,
                     uint8_t FAR *buf, uint32_t n, uint8_t write, uint8_t kind,
                     uint16_t *mp, uint16_t *mpn)
{
    uint16_t sz = secsize(s, u), in, chunk;
    uint8_t sh = unit_of(s, u)->shift;
    uint32_t done = 0;
    int32_t d;
    int16_t i;

    while (done < n) {
        in = (uint16_t)(off & (sz - 1));
        chunk = (uint16_t)(sz - in);
        if ((uint32_t)chunk > n - done)
            chunk = (uint16_t)(n - done);
        d = ch_sec(s, u, first, (uint16_t)(off >> sh), write, kind, mp, mpn);
        if (d < 0)
            return done ? (int32_t)done : d;
        if (!d)
            break;                  /* read past the chain */
        /* a whole sector written needs nothing read first */
        i = c_get(s, u, (uint16_t)d, kind, (uint8_t)(write && chunk == sz));
        if (i < 0)
            return done ? (int32_t)done : i;
        if (write) {
            fcopy(s->buf[i] + in, buf + done, chunk);
            c_dirty(s, i);
        } else
            fcopy(buf + done, s->buf[i] + in, chunk);
        done += chunk;
        off += chunk;
    }
    return (int32_t)done;
}

/* Every sector of a chain, given back. */
static int16_t ch_free(SDFS FAR *s, uint8_t u, uint16_t first)
{
    uint16_t p = first, pm = perm(s, u), j, d, nx;
    int16_t i, e;

    while (p) {
        for (j = 0; j < pm; j++) {
            i = c_get(s, u, p, SK_MAP, 0);
            if (i < 0)
                return i;
            d = get16(s->buf[i] + 4 + 2 * j);
            if (d) {
                e = free_sec(s, u, d);
                if (e < 0)
                    return e;
            }
        }
        i = c_get(s, u, p, SK_MAP, 0);
        if (i < 0)
            return i;
        nx = get16(s->buf[i]);
        e = free_sec(s, u, p);
        if (e < 0)
            return e;
        p = nx;
    }
    return 0;
}

/* A new chain: one map page, empty.  Its sector, or a negative error. */
static int32_t ch_new(SDFS FAR *s, uint8_t u)
{
    int32_t a = alloc_sec(s, u);
    int16_t i;

    if (a < 0)
        return a;
    i = c_get(s, u, (uint16_t)a, SK_MAP, 1);
    if (i < 0)
        return i;
    c_dirty(s, i);
    return a;
}

/* ---- names ------------------------------------------------------------ */

/* One component, n characters, into an entry's eleven: NAME, padded,
 * then EXT, padded.  0, or SD_EFILNF for what SpartaDOS cannot name. */
static int16_t name11(const char FAR *p, uint16_t n, uint8_t FAR *out)
{
    uint16_t k, at = 0, lim = 8;
    uint8_t c;

    for (k = 0; k < 11; k++)
        out[k] = ' ';
    if (!n)
        return SD_EFILNF;
    for (k = 0; k < n; k++) {
        c = (uint8_t)p[k];
        if (c == '.') {
            if (lim == 11 || at == 0)
                return SD_EFILNF;   /* a second dot, or no name */
            at = 8;
            lim = 11;
            continue;
        }
        if (c >= 'a' && c <= 'z')
            c = (uint8_t)(c - 0x20);
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'))
            return SD_EFILNF;
        if (at >= lim)
            return SD_EFILNF;       /* too long */
        out[at++] = c;
    }
    return 0;
}

static uint8_t same11(const uint8_t FAR *a, const uint8_t FAR *b)
{
    uint8_t k;

    for (k = 0; k < 11; k++)
        if (a[k] != b[k])
            return 0;
    return 1;
}

static void info_of(const uint8_t FAR *ent, SD_INFO FAR *info)
{
    uint8_t k, n = 0;

    info->status = ent[E_STATUS];
    info->size = (uint32_t)ent[E_SIZE] | ((uint32_t)ent[E_SIZE + 1] << 8)
                 | ((uint32_t)ent[E_SIZE + 2] << 16);
    for (k = 0; k < 8 && ent[E_NAME + k] != ' '; k++)
        info->name[n++] = (char)ent[E_NAME + k];
    if (ent[E_NAME + 8] != ' ') {
        info->name[n++] = '.';
        for (k = 8; k < 11 && ent[E_NAME + k] != ' '; k++)
            info->name[n++] = (char)ent[E_NAME + k];
    }
    info->name[n] = 0;
    for (k = 0; k < 6; k++)
        info->stamp[k] = ent[E_STAMP + k];
}

/* ---- directories ------------------------------------------------------ */

/* A directory's bytes, read or written: a chain of kind SK_DIR. */
static int32_t d_io(SDFS FAR *s, uint8_t u, uint16_t dmap, uint16_t off,
                    uint8_t FAR *buf, uint16_t n, uint8_t write)
{
    uint16_t mp = 0, mpn = 0xFFFF;

    return ch_io(s, u, dmap, off, buf, n, write, SK_DIR, &mp, &mpn);
}

/* What a search of one directory found: where, and what. */

/* `f->want` in directory f->dmap: 0 with f->off and f->ent, or SD_EFILNF
 * with f->freeoff; or another negative error. */
static int16_t d_find(SDFS FAR *s, uint8_t u, SD_FIND FAR *f)
{
    uint8_t FAR *e = f->ent;
    uint16_t off;
    int32_t r;
    uint8_t havefree = 0;

    r = d_io(s, u, f->dmap, 0, e, SD_ENT, 0);
    if (r < 0)
        return (int16_t)r;
    if (r < SD_ENT)
        return SD_EPTHNF;
    f->dsize = get16(e + E_SIZE);
    f->freeoff = f->dsize;
    for (off = SD_ENT; (uint32_t)off + SD_ENT <= f->dsize; off += SD_ENT) {
        r = d_io(s, u, f->dmap, off, e, SD_ENT, 0);
        if (r < 0)
            return (int16_t)r;
        if (r < SD_ENT || !e[E_STATUS])
            break;
        if (!(e[E_STATUS] & SD_INUSE)) {
            if (!havefree) {
                f->freeoff = off;
                havefree = 1;
            }
            continue;
        }
        if (same11(e + E_NAME, f->want)) {
            f->off = off;
            return 0;
        }
    }
    return SD_EFILNF;
}

/* A path's directory and last name: f->dmap is the directory the last
 * component is in, f->want that component.  *root is set for the root
 * itself ("" or "\"), which has no last component.  The folders on the
 * way must be there: SD_EPTHNF otherwise. */
static int16_t resolve(SDFS FAR *s, uint8_t u, const char FAR *path,
                       SD_FIND FAR *f, uint8_t *root)
{
    const char FAR *p = path;
    const char FAR *q;
    uint16_t n;
    int16_t e;

    *root = 0;
    f->dmap = unit_of(s, u)->root;
    while (*p == '\\')
        p++;
    if (!*p) {
        *root = 1;
        return 0;
    }
    for (;;) {
        for (q = p; *q && *q != '\\'; q++)
            ;
        n = (uint16_t)(q - p);
        e = name11(p, n, f->want);
        if (!*q || (q[0] == '\\' && !q[1]))
            return e < 0 ? e : 0;           /* the last component */
        if (e < 0)
            return SD_EPTHNF;
        e = d_find(s, u, f);
        if (e == SD_EFILNF || (e == 0 && !(f->ent[E_STATUS] & SD_SUBDIR)))
            return SD_EPTHNF;
        if (e < 0)
            return e;
        f->dmap = get16(f->ent + E_MAP);
        p = q + 1;
    }
}

/* An entry, written at f->freeoff; a slot past the end makes the
 * directory one entry longer, in its header. */
static int16_t d_add(SDFS FAR *s, uint8_t u, SD_FIND FAR *f,
                     const uint8_t FAR *ent)
{
    int32_t r;
    uint8_t len[3];

    r = d_io(s, u, f->dmap, f->freeoff, (uint8_t FAR *)ent, SD_ENT, 1);
    if (r < 0)
        return (int16_t)r;
    f->off = f->freeoff;
    if (f->freeoff == f->dsize) {
        f->dsize = (uint16_t)(f->dsize + SD_ENT);
        len[0] = (uint8_t)f->dsize;
        len[1] = (uint8_t)(f->dsize >> 8);
        len[2] = 0;
        r = d_io(s, u, f->dmap, E_SIZE, len, 3, 1);
        if (r < 0)
            return (int16_t)r;
    }
    return 0;
}

/* ---- syncing ---------------------------------------------------------- */

int16_t sd_sync(SDFS FAR *s, uint8_t u)
{
    SD_UNIT FAR *un;
    int16_t i, e;
    uint16_t fr;

    if (u < 1 || u > SD_UNITS || !unit_of(s, u)->mounted)
        return 0;
    un = unit_of(s, u);
    e = c_flush(s, u, SK_BMAP);
    if (e < 0)
        return e;
    if (un->fdelta) {
        i = c_get(s, u, 1, SK_SUPER, 0);
        if (i < 0)
            return i;
        fr = (uint16_t)(get16(s->buf[i] + 13) + un->fdelta);
        put16(s->buf[i] + 13, fr);
        c_dirty(s, i);
        e = c_write(s, i);
        if (e < 0)
            return e;
        un->fdelta = 0;
    }
    return 0;
}

/* ---- the calls -------------------------------------------------------- */

int16_t sd_stat(SDFS FAR *s, uint8_t u, const char FAR *path,
                SD_INFO FAR *info)
{
    SD_FIND FAR *f = &s->f;
    uint8_t root;
    int16_t e = mount(s, u);

    if (e < 0)
        return e;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root) {
        info->status = SD_INUSE | SD_SUBDIR;
        info->size = 0;
        info->name[0] = 0;
        fzero(info->stamp, 6);
        return 0;
    }
    e = d_find(s, u, f);
    if (e < 0)
        return e;
    info_of(f->ent, info);
    return 0;
}

static int16_t is_open(SDFS FAR *s, uint8_t u, uint16_t dmap, uint16_t off)
{
    int16_t i;

    for (i = 0; i < SD_FILES; i++)
        if (s->files[i].used && s->files[i].unit == u
            && s->files[i].dmap == dmap && s->files[i].doff == off)
            return 1;
    return 0;
}

int16_t sd_open(SDFS FAR *s, uint8_t u, const char FAR *path, uint8_t mode)
{
    SD_FIND FAR *f = &s->f;
    SD_FILE FAR *fl;
    uint8_t root, k;
    int16_t e, h;
    int32_t a;

    e = mount(s, u);
    if (e < 0)
        return e;
    for (h = 0; h < SD_FILES && s->files[h].used; h++)
        ;
    if (h == SD_FILES)
        return SD_ENHNDL;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, f);
    if (e < 0 && e != SD_EFILNF)
        return e;
    if (e == 0 && (f->ent[E_STATUS] & SD_SUBDIR))
        return SD_EACCDN;
    if (mode != SD_CREATE) {
        if (e < 0)
            return e;
        if (mode != SD_READ && (f->ent[E_STATUS] & SD_LOCKED))
            return SD_EACCDN;
    } else {
        /* emptied, or made */
        if (e == 0) {
            if (f->ent[E_STATUS] & SD_LOCKED)
                return SD_EACCDN;
            if (is_open(s, u, f->dmap, f->off))
                return SD_EACCDN;
            e = ch_free(s, u, get16(f->ent + E_MAP));
            if (e < 0)
                return e;
        } else {
            fzero(f->ent, SD_ENT);
            for (k = 0; k < 11; k++)
                f->ent[E_NAME + k] = f->want[k];
        }
        a = ch_new(s, u);
        if (a < 0)
            return (int16_t)a;
        f->ent[E_STATUS] = SD_INUSE;
        put16(f->ent + E_MAP, (uint16_t)a);
        f->ent[E_SIZE] = f->ent[E_SIZE + 1] = f->ent[E_SIZE + 2] = 0;
        sd_now(f->ent + E_STAMP);
        if (e == 0) {               /* where it was */
            int32_t r = d_io(s, u, f->dmap, f->off, f->ent, SD_ENT, 1);
            if (r < 0)
                return (int16_t)r;
        } else {
            e = d_add(s, u, f, f->ent);
            if (e < 0)
                return e;
        }
        e = sd_sync(s, u);          /* the map page, the entry, the bitmap */
        if (e < 0)
            return e;
    }
    fl = &s->files[h];
    fl->used = 1;
    fl->unit = u;
    fl->mode = mode;
    fl->grown = 0;
    fl->dmap = f->dmap;
    fl->doff = f->off;
    fl->first = get16(f->ent + E_MAP);
    fl->mpage = 0;
    fl->mpn = 0xFFFF;
    fl->size = (uint32_t)f->ent[E_SIZE] | ((uint32_t)f->ent[E_SIZE + 1] << 8)
               | ((uint32_t)f->ent[E_SIZE + 2] << 16);
    fl->pos = 0;
    return h;
}

static SD_FILE FAR *file_of(SDFS FAR *s, int16_t h)
{
    if (h < 0 || h >= SD_FILES || !s->files[h].used)
        return 0;
    return &s->files[h];
}

int32_t sd_read(SDFS FAR *s, int16_t h, uint8_t FAR *buf, uint32_t n)
{
    SD_FILE FAR *fl = file_of(s, h);
    uint16_t mp, mpn;
    int32_t r;

    if (!fl)
        return SD_EIHNDL;
    if (fl->mode == SD_WRITE)
        return SD_EACCDN;
    if (fl->pos >= fl->size)
        return 0;
    if (n > fl->size - fl->pos)
        n = fl->size - fl->pos;
    mp = fl->mpage;
    mpn = fl->mpn;
    r = ch_io(s, fl->unit, fl->first, fl->pos, buf, n, 0, SK_DATA, &mp, &mpn);
    fl->mpage = mp;
    fl->mpn = mpn;
    if (r > 0)
        fl->pos += (uint32_t)r;
    return r;
}

int32_t sd_write(SDFS FAR *s, int16_t h, const uint8_t FAR *buf, uint32_t n)
{
    SD_FILE FAR *fl = file_of(s, h);
    uint16_t mp, mpn;
    int32_t r;

    if (!fl)
        return SD_EIHNDL;
    if (fl->mode == SD_READ)
        return SD_EACCDN;
    if (!n)
        return 0;
    mp = fl->mpage;
    mpn = fl->mpn;
    r = ch_io(s, fl->unit, fl->first, fl->pos, (uint8_t FAR *)buf, n, 1,
              SK_DATA, &mp, &mpn);
    fl->mpage = mp;
    fl->mpn = mpn;
    if (r > 0) {
        fl->pos += (uint32_t)r;
        if (fl->pos > fl->size)
            fl->size = fl->pos;
        fl->grown = 1;
    }
    return r;
}

int32_t sd_seek(SDFS FAR *s, int16_t h, uint32_t pos)
{
    SD_FILE FAR *fl = file_of(s, h);

    if (!fl)
        return SD_EIHNDL;
    if (pos > fl->size)
        return SD_ERANGE;
    fl->pos = pos;
    return (int32_t)pos;
}

int32_t sd_tell(SDFS FAR *s, int16_t h)
{
    SD_FILE FAR *fl = file_of(s, h);

    return fl ? (int32_t)fl->pos : SD_EIHNDL;
}

int32_t sd_length(SDFS FAR *s, int16_t h)
{
    SD_FILE FAR *fl = file_of(s, h);

    return fl ? (int32_t)fl->size : SD_EIHNDL;
}

int16_t sd_close(SDFS FAR *s, int16_t h)
{
    SD_FILE FAR *fl = file_of(s, h);
    uint8_t ent[9];
    int32_t r;
    int16_t e = 0;

    if (!fl)
        return SD_EIHNDL;
    if (fl->grown) {
        /* its length and the time, then all of it in order */
        ent[0] = (uint8_t)fl->size;
        ent[1] = (uint8_t)(fl->size >> 8);
        ent[2] = (uint8_t)(fl->size >> 16);
        r = d_io(s, fl->unit, fl->dmap, (uint16_t)(fl->doff + E_SIZE), ent, 3, 1);
        if (r < 0)
            e = (int16_t)r;
        else {
            sd_now(ent + 3);
            r = d_io(s, fl->unit, fl->dmap, (uint16_t)(fl->doff + E_STAMP),
                     ent + 3, 6, 1);
            if (r < 0)
                e = (int16_t)r;
        }
        if (e == 0)
            e = sd_sync(s, fl->unit);
    }
    fl->used = 0;
    return e;
}

int16_t sd_fstamp(SDFS FAR *s, int16_t h, uint8_t FAR *stamp, uint8_t set)
{
    SD_FILE FAR *fl = file_of(s, h);
    int32_t r;

    if (!fl)
        return SD_EIHNDL;
    r = d_io(s, fl->unit, fl->dmap, (uint16_t)(fl->doff + E_STAMP), stamp, 6,
             set);
    if (r < 0)
        return (int16_t)r;
    return set ? sd_sync(s, fl->unit) : 0;
}

/* ---- listing ---------------------------------------------------------- */

int16_t sd_opendir(SDFS FAR *s, uint8_t u, const char FAR *path)
{
    SD_FIND FAR *f = &s->f;
    SD_DIR FAR *d;
    uint8_t root;
    uint8_t FAR *hdr = s->ent;
    int16_t e, h;
    int32_t r;
    uint16_t dmap;

    e = mount(s, u);
    if (e < 0)
        return e;
    for (h = 0; h < SD_DIRS && s->dirs[h].used; h++)
        ;
    if (h == SD_DIRS)
        return SD_ENHNDL;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e == SD_EFILNF ? SD_EPTHNF : e;
    if (root)
        dmap = f->dmap;
    else {
        e = d_find(s, u, f);
        if (e == SD_EFILNF || (e == 0 && !(f->ent[E_STATUS] & SD_SUBDIR)))
            return SD_EPTHNF;
        if (e < 0)
            return e;
        dmap = get16(f->ent + E_MAP);
    }
    r = d_io(s, u, dmap, 0, hdr, SD_ENT, 0);
    if (r < 0)
        return (int16_t)r;
    if (r < SD_ENT)
        return SD_EPTHNF;
    d = &s->dirs[h];
    d->used = 1;
    d->unit = u;
    d->dmap = dmap;
    d->off = SD_ENT;
    d->size = get16(hdr + E_SIZE);
    return h;
}

int16_t sd_readdir(SDFS FAR *s, int16_t h, SD_INFO FAR *info)
{
    SD_DIR FAR *d;
    uint8_t FAR *ent = s->ent;
    int32_t r;

    if (h < 0 || h >= SD_DIRS || !s->dirs[h].used)
        return SD_EIHNDL;
    d = &s->dirs[h];
    while ((uint32_t)d->off + SD_ENT <= d->size) {
        r = d_io(s, d->unit, d->dmap, d->off, ent, SD_ENT, 0);
        if (r < 0)
            return (int16_t)r;
        d->off = (uint16_t)(d->off + SD_ENT);
        if (r < SD_ENT || !ent[E_STATUS])
            break;
        if (ent[E_STATUS] & SD_INUSE) {
            info_of(ent, info);
            return 0;
        }
    }
    d->off = d->size;
    return SD_ENMFIL;
}

void sd_closedir(SDFS FAR *s, int16_t h)
{
    if (h >= 0 && h < SD_DIRS)
        s->dirs[h].used = 0;
}

/* ---- changes ---------------------------------------------------------- */

/* The entry at f->off marked deleted: one byte. */
static int16_t d_unlink(SDFS FAR *s, uint8_t u, SD_FIND FAR *f)
{
    uint8_t st = (uint8_t)((f->ent[E_STATUS] & ~SD_INUSE) | SD_DELETED);
    int32_t r = d_io(s, u, f->dmap, f->off, &st, 1, 1);

    return r < 0 ? (int16_t)r : 0;
}

int16_t sd_delete(SDFS FAR *s, uint8_t u, const char FAR *path)
{
    SD_FIND FAR *f = &s->f;
    uint8_t root;
    int16_t e = mount(s, u);

    if (e < 0)
        return e;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, f);
    if (e < 0)
        return e;
    if (f->ent[E_STATUS] & (SD_SUBDIR | SD_LOCKED))
        return SD_EACCDN;
    if (is_open(s, u, f->dmap, f->off))
        return SD_EACCDN;
    e = ch_free(s, u, get16(f->ent + E_MAP));
    if (e < 0)
        return e;
    e = d_unlink(s, u, f);
    if (e < 0)
        return e;
    return sd_sync(s, u);
}

int16_t sd_mkdir(SDFS FAR *s, uint8_t u, const char FAR *path)
{
    SD_FIND FAR *f = &s->f;
    uint8_t root, k;
    uint8_t FAR *head = s->ent;
    uint16_t mp = 0, mpn = 0xFFFF;
    int16_t e = mount(s, u);
    int32_t a, r;

    if (e < 0)
        return e;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, f);
    if (e == 0)
        return SD_EACCDN;           /* there already */
    if (e != SD_EFILNF)
        return e;
    a = ch_new(s, u);
    if (a < 0)
        return (int16_t)a;
    /* its header: in use and a directory, the parent's map, one entry
     * long, its own name */
    fzero(head, SD_ENT);
    head[E_STATUS] = SD_INUSE | SD_SUBDIR;
    put16(head + E_MAP, f->dmap);
    head[E_SIZE] = SD_ENT;
    for (k = 0; k < 11; k++)
        head[E_NAME + k] = f->want[k];
    sd_now(head + E_STAMP);
    r = ch_io(s, u, (uint16_t)a, 0, head, SD_ENT, 1, SK_DIR, &mp, &mpn);
    if (r < 0)
        return (int16_t)r;
    /* and its entry in the parent */
    put16(head + E_MAP, (uint16_t)a);
    e = d_add(s, u, f, head);
    if (e < 0)
        return e;
    return sd_sync(s, u);
}

int16_t sd_rmdir(SDFS FAR *s, uint8_t u, const char FAR *path)
{
    SD_FIND FAR *f = &s->f;
    uint8_t root;
    uint8_t FAR *ent = s->ent;
    uint16_t dmap, size, off;
    int16_t e = mount(s, u);
    int32_t r;

    if (e < 0)
        return e;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, f);
    if (e == SD_EFILNF)
        return SD_EPTHNF;
    if (e < 0)
        return e;
    if (!(f->ent[E_STATUS] & SD_SUBDIR))
        return SD_EPTHNF;
    if (f->ent[E_STATUS] & SD_LOCKED)
        return SD_EACCDN;
    dmap = get16(f->ent + E_MAP);
    r = d_io(s, u, dmap, 0, ent, SD_ENT, 0);
    if (r < 0)
        return (int16_t)r;
    size = get16(ent + E_SIZE);
    for (off = SD_ENT; (uint32_t)off + SD_ENT <= size; off += SD_ENT) {
        r = d_io(s, u, dmap, off, ent, SD_ENT, 0);
        if (r < 0)
            return (int16_t)r;
        if (r < SD_ENT || !ent[E_STATUS])
            break;
        if (ent[E_STATUS] & SD_INUSE)
            return SD_EACCDN;       /* not empty */
    }
    for (off = 0; off < SD_DIRS; off++)
        if (s->dirs[off].used && s->dirs[off].unit == u
            && s->dirs[off].dmap == dmap)
            s->dirs[off].used = 0;
    e = ch_free(s, u, dmap);
    if (e < 0)
        return e;
    e = d_unlink(s, u, f);
    if (e < 0)
        return e;
    return sd_sync(s, u);
}

int16_t sd_rename(SDFS FAR *s, uint8_t u, const char FAR *from,
                  const char FAR *to)
{
    SD_FIND FAR *f = &s->f;
    SD_FIND FAR *g = &s->g;
    uint8_t root;
    int16_t k;                      /* a word: no byte of this frame is
                                       sign-tested wide (B23, mscan) */
    uint8_t FAR *ent = s->ent;
    int16_t e = mount(s, u);
    int32_t r;

    if (e < 0)
        return e;
    e = resolve(s, u, from, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, f);
    if (e < 0)
        return e;
    if (f->ent[E_STATUS] & SD_LOCKED)
        return SD_EACCDN;
    e = resolve(s, u, to, g, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_EACCDN;
    e = d_find(s, u, g);
    if (e == 0)
        return SD_EACCDN;           /* the new name is taken */
    if (e != SD_EFILNF)
        return e;
    if (g->dmap == f->dmap) {         /* the same folder: the name alone */
        r = d_io(s, u, f->dmap, (uint16_t)(f->off + E_NAME), g->want, 11, 1);
        if (r < 0)
            return (int16_t)r;
        return sd_sync(s, u);
    }
    /* to another folder: a new entry there, the old one deleted -- and a
     * folder moved says so in its header, whose map is its parent's */
    for (k = 0; k < SD_ENT; k++)
        ent[k] = f->ent[k];
    for (k = 0; k < 11; k++)
        ent[E_NAME + k] = g->want[k];
    if (ent[E_STATUS] & SD_SUBDIR) {
        uint16_t sub = get16(ent + E_MAP), hops;
        SD_FIND FAR *w = &s->w;
        /* not into itself, nor anything inside it */
        w->dmap = g->dmap;
        for (hops = 0; hops < 64; hops++) {
            if (w->dmap == sub)
                return SD_EACCDN;
            if (w->dmap == unit_of(s, u)->root)
                break;
            r = d_io(s, u, w->dmap, 0, w->ent, SD_ENT, 0);
            if (r < SD_ENT)
                return r < 0 ? (int16_t)r : SD_EPTHNF;
            w->dmap = get16(w->ent + E_MAP);
        }
        put16(w->ent, g->dmap);     /* the walk is done with its buffer */
        r = d_io(s, u, sub, E_MAP, w->ent, 2, 1);
        if (r < 0)
            return (int16_t)r;
    }
    e = d_add(s, u, g, ent);
    if (e < 0)
        return e;
    e = d_unlink(s, u, f);
    if (e < 0)
        return e;
    for (k = 0; k < SD_FILES; k++)  /* an open file goes with it */
        if (s->files[k].used && s->files[k].unit == u
            && s->files[k].dmap == f->dmap && s->files[k].doff == f->off) {
            s->files[k].dmap = g->dmap;
            s->files[k].doff = g->off;
        }
    return sd_sync(s, u);
}

int16_t sd_attrib(SDFS FAR *s, uint8_t u, const char FAR *path, uint8_t set,
                  uint8_t bits)
{
    SD_FIND FAR *f = &s->f;
    uint8_t root, st;
    int16_t e = mount(s, u);
    int32_t r;

    if (e < 0)
        return e;
    e = resolve(s, u, path, f, &root);
    if (e < 0)
        return e;
    if (root)
        return SD_INUSE | SD_SUBDIR;
    e = d_find(s, u, f);
    if (e < 0)
        return e;
    st = f->ent[E_STATUS];
    if (!set)
        return st;
    st = (uint8_t)((st & ~(SD_LOCKED | SD_HIDDEN | SD_ARCHIVED))
                   | (bits & (SD_LOCKED | SD_HIDDEN | SD_ARCHIVED)));
    r = d_io(s, u, f->dmap, f->off, &st, 1, 1);
    if (r < 0)
        return (int16_t)r;
    e = sd_sync(s, u);
    return e < 0 ? e : st;
}

int16_t sd_space(SDFS FAR *s, uint8_t u, uint16_t FAR *free,
                 uint16_t FAR *total)
{
    int16_t i, e = mount(s, u);
    SD_UNIT FAR *un;

    if (e < 0)
        return e;
    un = unit_of(s, u);
    i = c_get(s, u, 1, SK_SUPER, 0);
    if (i < 0)
        return i;
    *free = (uint16_t)(get16(s->buf[i] + 13) + un->fdelta);
    *total = un->total;
    return 0;
}
