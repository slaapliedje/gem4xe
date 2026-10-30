/* gsomf.c -- load a GS/OS load file (OMF version 2) for GSlayer.
 *
 * Object Module Format is the GS/OS Reference's appendix F.  A load file
 * is a run of segments, each a header and a body of records: data
 * (LCONST, DS, CONST) and the relocations that fix it to where it was put
 * (RELOC, INTERSEG and their compressed forms cRELOC, cINTERSEG and
 * SUPER).  This loads every static segment into memory from gem4xe, two
 * passes -- place them all, then fill and fix them, since a record in one
 * may point into another -- and leaves the first code segment's entry in
 * gs_go.
 *
 * Not yet, and refused rather than guessed: dynamic code segments (they
 * need the jump table, loaded on first call), references into other load
 * files (SUPER INTERSEG2-12, INTERSEG with a file number other than 1),
 * and a file over 64 KB.  The ~ExpressLoad segment ORCA's linker writes
 * first is a speed-up for GS/OS's loader only and is skipped.
 */
#include "gs.h"

#define SEG_MAX     32

extern uint16_t gs_stage;           /* gslayer.c: the harness reads it */

static uint32_t buf;                /* the file, read whole */
static uint32_t seg_at[SEG_MAX];    /* where segment n went (0: not loaded) */

static uint8_t rd8(uint32_t a) { return *(uint8_t FAR *)a; }
static void wr8(uint32_t a, uint8_t v) { *(uint8_t FAR *)a = v; }

static uint16_t rdw(uint32_t a)
{
    return (uint16_t)(rd8(a) | rd8(a + 1) << 8);
}

static uint32_t rdl(uint32_t a)
{
    return (uint32_t)rdw(a) | (uint32_t)rdw(a + 2) << 16;
}

/* Write the low `n` bytes of v at a. */
static void put(uint32_t a, uint32_t v, uint8_t n)
{
    while (n--) {
        wr8(a++, (uint8_t)v);
        v >>= 8;
    }
}

static uint32_t get(uint32_t a, uint8_t n)
{
    uint32_t v = 0;

    while (n--)
        v = v << 8 | rd8(a + n);
    return v;
}

static uint32_t shift(uint32_t v, uint8_t s)
{
    if (s & 0x80)
        return v >> (uint8_t)(0x100 - s);  /* negative: right */
    return v << s;
}

/* A segment's header, the parts of it used here (appendix F, "Segment
 * header"). */
typedef struct {
    uint32_t bytecnt, resspc, length, align, entry;
    uint16_t kind, segnum, dispname, dispdata;
    uint16_t numsex, version;           /* bytes in the file; words here,
                                         * so the struct is all one width
                                         * (Calypsi B7: a byte beside words
                                         * is sized two ways) */
} SegHdr;

static SegHdr h;                    /* not on the stack, for the same reason */

static void header(uint32_t at, SegHdr *h)
{
    h->bytecnt = rdl(at);
    h->resspc = rdl(at + 4);
    h->length = rdl(at + 8);
    h->version = rd8(at + 15);
    h->kind = rdw(at + 20);
    h->align = rdl(at + 28);
    h->numsex = rd8(at + 32);
    h->segnum = rdw(at + 34);
    h->entry = rdl(at + 36);
    h->dispname = rdw(at + 40);
    h->dispdata = rdw(at + 42);
}

/* Is this the ~ExpressLoad segment?  Its name is the segment name field,
 * after the 10-byte load name; a length byte first (LABLEN 0). */
static int16_t express(uint32_t at, SegHdr *h)
{
    static const char x[] = "~ExpressLoad";
    uint32_t n = at + h->dispname + 10;
    uint16_t i;

    if (rd8(n) != 12)
        return 0;
    for (i = 0; i < 12; i++)
        if (rd8(n + 1 + i) != (uint8_t)x[i])
            return 0;
    return 1;
}

/* One SUPER record's subrecords, `len` bytes from `at`, for segment base
 * `base`.  `type` is 0 RELOC2, 1 RELOC3, or 2-37 INTERSEG1-INTERSEG36 --
 * INTERSEGn is type n + 1.  The patched location holds the rest of what
 * it needs (appendix F, "SUPER"). */
static int16_t super(uint32_t at, uint32_t len, uint16_t type, uint32_t base)
{
    uint32_t end = at + len, p;
    uint16_t page = 0, n, off;
    /* Words, not bytes: with `c` a byte, cc65816 -O2 tested its bit 7 in
     * the high half of a stack word and then took `c + 1` from the LOW
     * half -- a stray byte -- so every count was wrong and the patches
     * went astray (B23's family, docs/gslayer.md). */
    uint16_t c, seg, is = (uint16_t)(type - 1);  /* INTERSEG number */

    if (type >= 2 && is >= 2 && is <= 12)
        return -1;                      /* another load file: not yet */
    while (at < end) {
        c = rd8(at++);
        if (c & 0x80) {
            page = (uint16_t)(page + (c & 0x7F));
            continue;
        }
        for (n = (uint16_t)(c + 1); n; n--) {
            off = (uint16_t)(page << 8 | rd8(at++));
            p = base + off;
            if (type == 0) {            /* RELOC2 */
                put(p, base + rdw(p), 2);
                continue;
            }
            if (type == 1) {            /* RELOC3 */
                put(p, base + get(p, 3), 3);
                continue;
            }
            if (is == 1)                /* the segment in the third byte */
                seg = rd8(p + 2);
            else if (is <= 24)          /* 13-24: segment is - 12 */
                seg = (uint16_t)(is - 12);
            else                        /* 25-36: segment is - 24 */
                seg = (uint16_t)(is - 24);
            if (seg >= SEG_MAX || !seg_at[seg])
                return -1;
            if (is == 1)
                put(p, seg_at[seg] + rdw(p), 3);
            else if (is <= 24)
                put(p, seg_at[seg] + rdw(p), 2);
            else                        /* shifted right 16: the bank */
                put(p, (seg_at[seg] + rdw(p)) >> 16, 2);
        }
        page++;
    }
    return 0;
}

/* The body of a segment loaded at `base`: data and relocations. */
static int16_t body(uint32_t at, uint32_t base)
{
    uint32_t pc = 0, n, i, patch, ref;
    uint16_t op, seg;                   /* words: see super() */
    uint8_t cnt, sh;

    for (;;) {
        op = rd8(at++);
        if (op == 0x00)                 /* END */
            return 0;
        if (op <= 0xDF) {               /* CONST: op bytes */
            for (i = 0; i < op; i++)
                wr8(base + pc++, rd8(at++));
            continue;
        }
        switch (op) {
        case 0xF2:                      /* LCONST */
            n = rdl(at);
            at += 4;
            for (i = 0; i < n; i++)
                wr8(base + pc++, rd8(at++));
            break;
        case 0xF1:                      /* DS: zeros */
            n = rdl(at);
            at += 4;
            for (i = 0; i < n; i++)
                wr8(base + pc++, 0);
            break;
        case 0xE2:                      /* RELOC */
            cnt = rd8(at);
            sh = rd8(at + 1);
            patch = rdl(at + 2);
            ref = rdl(at + 6);
            at += 10;
            put(base + patch, shift(base + ref, sh), cnt);
            break;
        case 0xE3:                      /* INTERSEG */
            cnt = rd8(at);
            sh = rd8(at + 1);
            patch = rdl(at + 2);
            if (rdw(at + 6) != 1)       /* another load file */
                return -1;
            seg = rdw(at + 8);
            ref = rdl(at + 10);
            at += 14;
            if (seg >= SEG_MAX || !seg_at[seg])
                return -1;
            put(base + patch, shift(seg_at[seg] + ref, sh), cnt);
            break;
        case 0xF5:                      /* cRELOC */
            cnt = rd8(at);
            sh = rd8(at + 1);
            patch = rdw(at + 2);
            ref = rdw(at + 4);
            at += 6;
            put(base + patch, shift(base + ref, sh), cnt);
            break;
        case 0xF6:                      /* cINTERSEG */
            cnt = rd8(at);
            sh = rd8(at + 1);
            patch = rdw(at + 2);
            seg = rd8(at + 4);
            ref = rdw(at + 5);
            at += 7;
            if (seg >= SEG_MAX || !seg_at[seg])
                return -1;
            put(base + patch, shift(seg_at[seg] + ref, sh), cnt);
            break;
        case 0xF7:                      /* SUPER */
            n = rdl(at);
            if (super(at + 5, n - 1, rd8(at + 4), base) < 0)
                return -1;
            at += 4 + n;
            break;
        default:
            return -1;                  /* not a record a load file has */
        }
    }
}

int16_t gs_load(const char *path)
{
    LONG fd, size;
    uint32_t at, end, base;
    uint16_t pass, attr;
    int16_t first = 1;

    fd = Fopen(path, 0);
    if (fd < 0)
        return -1;
    gs_stage = 0x20;
    size = Fseek(0, (WORD)fd, 2);
    gs_stage = 0x21;
    Fseek(0, (WORD)fd, 0);
    gs_stage = 0x22;
    if (size <= 0 || size > 0xFF00L) {
        Fclose((WORD)fd);
        return -1;
    }
    buf = (uint32_t)Malloc(size);
    gs_stage = 0x23;
    if (!buf || Fread((WORD)fd, size, (void FAR *)buf) != size) {
        Fclose((WORD)fd);
        return -1;
    }
    Fclose((WORD)fd);
    gs_stage = 0x24;

    end = buf + (uint32_t)size;
    for (pass = 0; pass < 2; pass++) {
        gs_stage = (uint16_t)(0x30 + pass);
        for (at = buf; at < end; at += h.bytecnt) {
            header(at, &h);
            if (h.bytecnt == 0 || h.version != 2 || h.numsex != 0)
                return -1;
            if (h.segnum >= SEG_MAX)
                return -1;
            if (express(at, &h))
                continue;
            if ((h.kind & 0x1F) == 0x12)
                continue;               /* direct page/stack: gs_alloc'd by main */
            if ((h.kind & 0x8000) && (h.kind & 0x1F) == 0x00)
                return -1;              /* a dynamic code segment: not yet */
            if (pass == 0) {
                attr = (h.align > 1) ? 0x0004 : 0;
                base = gs_alloc(h.length + h.resspc, attr, 0);
                if (!base)
                    return -1;
                seg_at[h.segnum] = base;
                gs_handle(base, h.length + h.resspc, gs_userid);
                if (first && (h.kind & 0x1F) == 0x00) {
                    gs_go = base + h.entry;
                    first = 0;
                }
            } else if (body(at + h.dispdata, seg_at[h.segnum]) < 0) {
                return -1;
            }
        }
    }
    Mfree((void FAR *)buf);
    return first ? -1 : 0;
}
