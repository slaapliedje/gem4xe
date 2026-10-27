/* GemARC's codecs -- what each ARC method is, written from the format
 * (src/apps/arccodec.h says which).  No file of its own: arc_in() and
 * arc_out() are the platform's (src/apps/arcfile.c), the tables the
 * caller's (arc_tables).
 *
 * The compiler is cc65816, whose int is 16 bits: every shift that can
 * pass bit 15 is done on a uint32_t, and a byte read through a far table
 * is read into a local before it is used (tools/ccbug's B18, B22). */
#include "arccodec.h"

#define DLE        0x90             /* RLE90's escape */
#define LZW_CLEAR  256
#define LZW_FIRST  257
#define LZW_BITS   12               /* what ARC's crunching writes */
#define SQ_EOF     256              /* squeeze's end of the member */
#define HASH_EMPTY 0xFFFFFFFFUL

static uint16_t FAR *tprefix;
static uint8_t FAR *tsuffix;
static uint8_t FAR *tstack;
static uint32_t FAR *htab;
static uint16_t FAR *codetab;

void arc_tables(uint16_t FAR *prefix, uint8_t FAR *suffix, uint8_t FAR *stack,
                uint32_t FAR *hash, uint16_t FAR *codes)
{
    tprefix = prefix;
    tsuffix = suffix;
    tstack = stack;
    htab = hash;
    codetab = codes;
}

/* -- the CRC: ARC's CRC-16, $A001 reflected, from 0 ------------------------ */

static uint16_t crctab[256];
static uint8_t crc_ready;

uint16_t arc_crc(uint16_t crc, uint8_t c)
{
    uint16_t i, k, v;

    if (!crc_ready) {
        for (i = 0; i < 256; i++) {
            v = i;
            for (k = 0; k < 8; k++)
                v = (v & 1) ? (uint16_t)((v >> 1) ^ 0xA001) : (uint16_t)(v >> 1);
            crctab[i] = v;
        }
        crc_ready = 1;
    }
    v = crctab[(crc ^ c) & 0xFF];
    return (uint16_t)((crc >> 8) ^ v);
}

/* -- decoding ----------------------------------------------------------------- */

static uint16_t dcrc;               /* of what has come out */

static void put(uint8_t c)
{
    dcrc = arc_crc(dcrc, c);
    arc_out(c);
}

/* RLE90 undone, a byte at a time: $90 n is the last byte n-1 more times,
 * $90 0 a $90 -- which is not "the last byte" for a run after it. */
static uint8_t rle_state, rle_last;

static void unrle(uint8_t c)
{
    uint16_t n;

    if (rle_state == 0) {
        if (c == DLE) {
            rle_state = 1;
        } else {
            rle_last = c;
            put(c);
        }
        return;
    }
    rle_state = 0;
    if (c == 0) {
        put(DLE);
        return;
    }
    for (n = c; n > 1; n--)
        put(rle_last);
}

static uint8_t lzw_rle;             /* the LZW's output goes through RLE90 */

static void emit(uint8_t c)
{
    if (lzw_rle)
        unrle(c);
    else
        put(c);
}

/* LZW's codes in Unix compress's bit groups: a group is nbits BYTES, so
 * eight codes, and the codes are read low bit first.  When the code size
 * grows, or a clear comes, the rest of the group is thrown away -- the
 * writer padded it out, and every compress and ARC reads it so. */
static uint8_t gbuf[16];
static uint16_t goff, gsize, maxcode, maxmaxcode, free_ent;
static uint8_t nbits, maxbits, clear_flg;

static int getcode(void)
{
    uint16_t k, r;
    uint32_t v;
    int c;

    if (clear_flg || goff >= gsize || free_ent > maxcode) {
        if (free_ent > maxcode) {
            nbits++;
            maxcode = (nbits == maxbits) ? maxmaxcode
                                         : (uint16_t)((1UL << nbits) - 1);
        }
        if (clear_flg) {
            nbits = 9;
            maxcode = 511;
            clear_flg = 0;
        }
        for (k = 0; k < nbits; k++) {
            c = arc_in();
            if (c < 0)
                break;
            gbuf[k] = (uint8_t)c;
        }
        if (k == 0)
            return -1;
        for (r = k; r < sizeof gbuf; r++)
            gbuf[r] = 0;
        goff = 0;
        gsize = (uint16_t)((k << 3) - (nbits - 1));
    }
    r = goff >> 3;
    v = (uint32_t)gbuf[r] | ((uint32_t)gbuf[r + 1] << 8)
        | ((uint32_t)gbuf[r + 2] << 16);
    v >>= (goff & 7);
    goff = (uint16_t)(goff + nbits);
    return (int)(v & ((1UL << nbits) - 1));
}

static int unlzw(void)
{
    int code, incode, oldcode;
    uint16_t sp, k, fe;
    uint8_t finchar, s;

    nbits = 9;
    maxcode = 511;
    maxmaxcode = (uint16_t)(1UL << maxbits);
    free_ent = LZW_FIRST;
    clear_flg = 0;
    goff = gsize = 0;
    for (k = 0; k < 256; k++) {
        tprefix[k] = 0;
        tsuffix[k] = (uint8_t)k;
    }
    oldcode = getcode();
    if (oldcode < 0)
        return ARC_OK;                  /* an empty member */
    if (oldcode > 255)
        return ARC_E_DATA;
    finchar = (uint8_t)oldcode;
    emit(finchar);
    while ((code = getcode()) >= 0) {
        if (code == LZW_CLEAR) {
            clear_flg = 1;
            free_ent = LZW_FIRST - 1;   /* compress's: the next adds at 256 */
            code = getcode();
            if (code < 0)
                break;
        }
        incode = code;
        sp = 0;
        fe = free_ent;
        if ((uint16_t)code >= fe) {     /* the string being defined (KwKwK) */
            if ((uint16_t)code > fe)
                return ARC_E_DATA;
            tstack[sp++] = finchar;
            code = oldcode;
        }
        while (code >= 256) {
            s = tsuffix[code];
            tstack[sp++] = s;
            code = (int)tprefix[code];
            if (sp >= ARC_LZW_ENTRIES)
                return ARC_E_DATA;
        }
        finchar = tsuffix[code];
        emit(finchar);
        while (sp) {
            s = tstack[--sp];
            emit(s);
        }
        if (fe < maxmaxcode) {
            tprefix[fe] = (uint16_t)oldcode;
            tsuffix[fe] = finchar;
            free_ent = (uint16_t)(fe + 1);
        }
        oldcode = incode;
    }
    return ARC_OK;
}

/* Squeezed: RLE90 through a Huffman tree the member carries -- a count,
 * then that many nodes of two signed words, a child each way; a child
 * below 0 is the byte -(child+1), and 256 of those ends the member.  The
 * bits are read low first.  The nodes are kept in tprefix. */
static int unsqueeze(void)
{
    int lo, hi, n, i, b;
    uint16_t k, v;
    uint8_t cur = 0, left = 0;

    lo = arc_in();
    hi = arc_in();
    if (hi < 0)
        return ARC_E_DATA;
    n = (int)(int16_t)(uint16_t)(lo | (hi << 8));
    if (n < 0 || n > 256)
        return ARC_E_DATA;
    for (k = 0; k < (uint16_t)(2 * n); k++) {
        lo = arc_in();
        hi = arc_in();
        if (hi < 0)
            return ARC_E_DATA;
        tprefix[k] = (uint16_t)(lo | (hi << 8));
    }
    if (n == 0)
        return ARC_OK;
    for (;;) {
        i = 0;
        do {
            if (left == 0) {
                b = arc_in();
                if (b < 0)
                    return ARC_OK;      /* no end mark: the CRC will say */
                cur = (uint8_t)b;
                left = 8;
            }
            b = cur & 1;
            cur >>= 1;
            left--;
            v = tprefix[2 * i + b];
            i = (int)(int16_t)v;
            if (i >= n)
                return ARC_E_DATA;
        } while (i >= 0);
        i = -(i + 1);
        if (i == SQ_EOF)
            return ARC_OK;
        if (i > SQ_EOF)
            return ARC_E_DATA;
        unrle((uint8_t)i);
    }
}

int arc_decode(uint8_t method, uint16_t *crc)
{
    int c, r = ARC_OK;

    dcrc = 0;
    rle_state = 0;
    rle_last = 0;
    switch (method) {
    case ARC_STORED1:
    case ARC_STORED:
        while ((c = arc_in()) >= 0)
            put((uint8_t)c);
        break;
    case ARC_PACKED:
        while ((c = arc_in()) >= 0)
            unrle((uint8_t)c);
        break;
    case ARC_SQUEEZED:
        r = unsqueeze();
        break;
    case ARC_CRUNCHED:
        c = arc_in();
        if (c < 9 || c > 13) {
            r = ARC_E_DATA;
            break;
        }
        maxbits = (uint8_t)c;
        lzw_rle = 1;
        r = unlzw();
        break;
    case ARC_SQUASHED:
        maxbits = 13;
        lzw_rle = 0;
        r = unlzw();
        break;
    default:
        r = ARC_E_METHOD;
        break;
    }
    while (arc_in() >= 0)               /* what the decoder did not want */
        ;
    *crc = dcrc;
    if (r == ARC_OK && arc_out_failed())
        r = ARC_E_WRITE;
    return r;
}

/* -- encoding ----------------------------------------------------------------- */

/* Where a stage's bytes go.  Measuring counts both packings at once, the
 * RLE90 bytes as they are and through the LZW; writing sends one of them
 * out. */
#define TO_MEASURE 0
#define TO_OUT     1
#define TO_LZW     2
static uint8_t rle_to, lzw_counting;
static uint32_t n_packed, n_crunched;

static void lzw_in(uint8_t c);

static void rle_emit(uint8_t c)
{
    if (rle_to == TO_OUT) {
        arc_out(c);
    } else if (rle_to == TO_LZW) {
        lzw_in(c);
    } else {
        n_packed++;
        lzw_in(c);
    }
}

/* RLE90, gem4xe's way of writing it -- every reader takes it: a run of
 * three or more is the byte, $90 and the count (to 255); a $90 is always
 * $90 0, never part of a run, because readers disagree on what a run
 * after one repeats. */
static uint8_t r_last, r_have;
static uint16_t r_run;

static void rle_flush(void)
{
    uint16_t k;

    if (!r_have)
        return;
    if (r_last == DLE) {
        for (k = 0; k < r_run; k++) {
            rle_emit(DLE);
            rle_emit(0);
        }
    } else if (r_run >= 3) {
        rle_emit(r_last);
        rle_emit(DLE);
        rle_emit((uint8_t)r_run);
    } else {
        for (k = 0; k < r_run; k++)
            rle_emit(r_last);
    }
    r_have = 0;
}

static void rle_in(uint8_t c)
{
    if (r_have && c == r_last && r_run < 255) {
        r_run++;
        return;
    }
    rle_flush();
    r_last = c;
    r_have = 1;
    r_run = 1;
}

/* LZW to 12 bits, written as Unix compress writes it: the same groups,
 * the code size growing one code later than a reader would guess -- the
 * reader's check comes before its read and the writer's after its write,
 * and the two agree -- and a clear when the table is full.  (compress
 * clears only once the ratio falls; a reader cannot tell the
 * difference.) */
static uint16_t ent;
static uint8_t ent_valid;

static void lzw_byte(uint8_t b)
{
    if (lzw_counting)
        n_crunched++;
    else
        arc_out(b);
}

static void group_out(uint16_t n)
{
    uint16_t k;

    for (k = 0; k < n; k++)
        lzw_byte(gbuf[k]);
    for (k = 0; k < sizeof gbuf; k++)
        gbuf[k] = 0;
    goff = 0;
}

static void output(int code)
{
    uint16_t r;
    uint32_t v;

    if (code < 0) {
        if (goff)
            group_out((uint16_t)((goff + 7) >> 3));
        return;
    }
    r = goff >> 3;
    v = (uint32_t)(uint16_t)code << (goff & 7);
    gbuf[r] |= (uint8_t)v;
    gbuf[r + 1] |= (uint8_t)(v >> 8);
    gbuf[r + 2] |= (uint8_t)(v >> 16);
    goff = (uint16_t)(goff + nbits);
    if (goff == (uint16_t)(nbits << 3))
        group_out(nbits);
    if (free_ent > maxcode || clear_flg) {
        if (goff)
            group_out(nbits);           /* the whole group, padding and all */
        if (clear_flg) {
            nbits = 9;
            maxcode = 511;
            clear_flg = 0;
        } else {
            nbits++;
            maxcode = (nbits == LZW_BITS) ? maxmaxcode
                                          : (uint16_t)((1UL << nbits) - 1);
        }
    }
}

static void hash_clear(void)
{
    uint16_t k;

    for (k = 0; k < ARC_HASH; k++)
        htab[k] = HASH_EMPTY;
}

static void lzw_start(uint8_t counting)
{
    lzw_counting = counting;
    nbits = 9;
    maxcode = 511;
    maxmaxcode = 1U << LZW_BITS;
    free_ent = LZW_FIRST;
    clear_flg = 0;
    goff = 0;
    for (ent = 0; ent < sizeof gbuf; ent++)
        gbuf[ent] = 0;
    ent = 0;
    ent_valid = 0;
    hash_clear();
}

static void lzw_in(uint8_t c)
{
    uint32_t fcode, h;
    int i, disp;

    if (!ent_valid) {
        ent = c;
        ent_valid = 1;
        return;
    }
    fcode = ((uint32_t)c << LZW_BITS) + ent;
    i = (int)(((uint16_t)c << 4) ^ ent);
    h = htab[i];
    if (h == fcode) {
        ent = codetab[i];
        return;
    }
    if (h != HASH_EMPTY) {
        disp = (i == 0) ? 1 : ARC_HASH - i;
        for (;;) {
            i -= disp;
            if (i < 0)
                i += ARC_HASH;
            h = htab[i];
            if (h == fcode) {
                ent = codetab[i];
                return;
            }
            if (h == HASH_EMPTY)
                break;
        }
    }
    output((int)ent);
    ent = c;
    if (free_ent < maxmaxcode) {
        codetab[i] = free_ent;
        free_ent++;
        htab[i] = fcode;
    } else {
        hash_clear();
        free_ent = LZW_FIRST;
        clear_flg = 1;
        output(LZW_CLEAR);
    }
}

static void lzw_end(void)
{
    if (ent_valid)
        output((int)ent);
    output(-1);
}

void arc_measure(ARC_SIZES *s)
{
    int c;
    uint32_t size = 0;
    uint16_t crc = 0;

    n_packed = 0;
    n_crunched = 1;                     /* the bit count */
    rle_to = TO_MEASURE;
    r_have = 0;
    lzw_start(1);
    while ((c = arc_in()) >= 0) {
        size++;
        crc = arc_crc(crc, (uint8_t)c);
        rle_in((uint8_t)c);
    }
    rle_flush();
    lzw_end();
    s->size = size;
    s->packed = n_packed;
    s->crunched = n_crunched;
    s->crc = crc;
}

uint8_t arc_choose(const ARC_SIZES *s, uint32_t *csize)
{
    uint32_t best = s->size;
    uint8_t m = ARC_STORED;

    if (s->packed < best) {
        best = s->packed;
        m = ARC_PACKED;
    }
    if (s->crunched < best) {
        best = s->crunched;
        m = ARC_CRUNCHED;
    }
    *csize = best;
    return m;
}

void arc_encode(uint8_t method)
{
    int c;

    r_have = 0;
    if (method == ARC_STORED) {
        while ((c = arc_in()) >= 0)
            arc_out((uint8_t)c);
        return;
    }
    if (method == ARC_PACKED) {
        rle_to = TO_OUT;
        while ((c = arc_in()) >= 0)
            rle_in((uint8_t)c);
        rle_flush();
        return;
    }
    arc_out(LZW_BITS);                  /* ARC_CRUNCHED */
    rle_to = TO_LZW;
    lzw_start(0);
    while ((c = arc_in()) >= 0)
        rle_in((uint8_t)c);
    rle_flush();
    lzw_end();
}
