/* GemARC's archives (src/apps/arcfile.h): the members listed, taken out
 * and put in, over the platform's pf_ functions.  Portable C; the
 * Atari's int is 16 bits, so sizes are uint32_t throughout. */
#include "arcfile.h"

/* -- the streams the codecs read and write --------------------------------- */

static uint8_t FAR *ibuf;
static uint8_t FAR *obuf;
static uint16_t bsize;

void arc_buffers(uint8_t FAR *in, uint8_t FAR *out, uint16_t size)
{
    ibuf = in;
    obuf = out;
    bsize = size;
}

static int ih;
static uint32_t iremain;
static uint8_t ilimited, ieof;
static uint16_t ipos, ilen;

/* Input from handle h: `limit` bytes of it, or to its end if 0 == limited. */
static void in_start(int h, uint32_t limit, uint8_t limited)
{
    ih = h;
    iremain = limit;
    ilimited = limited;
    ieof = 0;
    ipos = ilen = 0;
}

int arc_in(void)
{
    uint8_t c;
    long n;
    uint32_t ask;

    if (ilimited && iremain == 0)
        return -1;
    if (ipos >= ilen) {
        if (ieof)
            return -1;
        ask = bsize;
        if (ilimited && iremain < ask)
            ask = iremain;
        n = pf_read(ih, ibuf, (long)ask);
        if (n <= 0) {
            ieof = 1;
            return -1;
        }
        ilen = (uint16_t)n;
        ipos = 0;
    }
    if (ilimited)
        iremain--;
    c = ibuf[ipos];
    ipos++;
    return c;
}

static int oh;
static uint16_t opos;
static uint8_t ofail;
static uint32_t ocount;

static void out_start(int h)
{
    oh = h;
    opos = 0;
    ofail = 0;
    ocount = 0;
}

static void out_flush(void)
{
    if (opos && !ofail && pf_write(oh, obuf, (long)opos) != (long)opos)
        ofail = 1;
    opos = 0;
}

void arc_out(uint8_t c)
{
    obuf[opos] = c;
    opos++;
    ocount++;
    if (opos == bsize)
        out_flush();
}

int arc_out_failed(void)
{
    return ofail;
}

static void out16(uint16_t v)
{
    arc_out((uint8_t)v);
    arc_out((uint8_t)(v >> 8));
}

static void out32(uint32_t v)
{
    out16((uint16_t)v);
    out16((uint16_t)(v >> 16));
}

/* -- names -------------------------------------------------------------------- */

static char upper(char c)
{
    return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
}

void arc_member_name(const char FAR *from, char *to)
{
    uint16_t k = 0, n = 0, ext = 0;
    char c;

    for (; (c = from[k]) != 0 && n < ARC_NAMELEN - 1; k++) {
        if (c == '.') {
            if (ext)
                continue;
            ext = 1;
            to[n++] = '.';
            continue;
        }
        if (!ext && n >= 8)
            continue;
        if (ext && n >= ARC_NAMELEN - 1)
            break;
        to[n++] = upper(c);
    }
    to[n] = 0;
}

/* Two member names compared as ARC orders them: by their letters, case
 * not counted. */
static int name_cmp(const char FAR *a, const char FAR *b)
{
    uint16_t k;
    char x, y;

    for (k = 0; k < ARC_NAMELEN; k++) {
        x = upper(a[k]);
        y = upper(b[k]);
        if (x != y)
            return (x < y) ? -1 : 1;
        if (!x)
            break;
    }
    return 0;
}

/* -- the list ----------------------------------------------------------------- */

static uint16_t le16(const uint8_t *p)
{
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)le16(p) | ((uint32_t)le16(p + 2) << 16);
}

/* One header at `pos`: 1 and *e filled, 0 at the end mark (or a file
 * that just stops), -1 for something that is not a header. */
static int header_at(int h, uint32_t pos, ARC_ENTRY *e, uint16_t *len)
{
    uint8_t hb[ARC_HDR];
    long got;
    uint16_t k, hl;
    uint8_t m;

    if (pf_seek(h, (long)pos) < 0)
        return 0;
    got = pf_read(h, hb, (long)ARC_HDR);
    if (got <= 0)
        return 0;
    if (hb[0] != ARC_MARK)
        return -1;
    if (got < 2)
        return 0;
    m = hb[1];
    if (m == 0)
        return 0;
    hl = (m == ARC_STORED1) ? ARC_HDR_OLD : ARC_HDR;
    if (got < (long)hl)
        return -1;
    for (k = 0; k < ARC_NAMELEN - 1; k++)
        e->name[k] = (char)hb[2 + k];
    e->name[ARC_NAMELEN - 1] = 0;
    e->method = m;
    e->sel = 0;
    e->csize = le32(hb + 15);
    e->date = le16(hb + 19);
    e->time = le16(hb + 21);
    e->crc = le16(hb + 23);
    e->osize = (m == ARC_STORED1) ? e->csize : le32(hb + 25);
    e->data = pos + hl;
    *len = hl;
    return 1;
}

static void entry_put(ARC_ENTRY FAR *to, const ARC_ENTRY *e)
{
    uint16_t k;
    char c;

    for (k = 0; k < ARC_NAMELEN; k++) {
        c = e->name[k];
        to->name[k] = c;
    }
    to->method = e->method;
    to->sel = 0;
    to->date = e->date;
    to->time = e->time;
    to->crc = e->crc;
    to->csize = e->csize;
    to->osize = e->osize;
    to->data = e->data;
}

static int list_open(int h, ARC_ENTRY FAR *list, uint16_t max, uint16_t *n)
{
    ARC_ENTRY e;
    uint32_t pos = 0;
    uint16_t hl, count = 0;
    int r;

    for (;;) {
        r = header_at(h, pos, &e, &hl);
        if (r < 0) {
            if (count == 0)
                return ARC_E_NOTARC;
            break;                      /* what follows is not ours */
        }
        if (r == 0)
            break;
        if (count < max)
            entry_put(&list[count], &e);
        count++;
        pos = e.data + e.csize;
    }
    if (count == 0) {                   /* the end mark alone, or nothing */
        uint8_t two[2];
        if (pf_seek(h, 0) < 0 || pf_read(h, two, 2) != 2 || two[0] != ARC_MARK)
            return ARC_E_NOTARC;
    }
    *n = (count < max) ? count : max;
    return (count > max) ? ARC_E_FULL : ARC_OK;
}

int arc_list(const char FAR *path, ARC_ENTRY FAR *list, uint16_t max,
             uint16_t *n)
{
    int h, r;

    *n = 0;
    h = pf_open(path);
    if (h < 0)
        return ARC_E_OPEN;
    r = list_open(h, list, max, n);
    pf_close(h);
    return r;
}

/* -- taking out ----------------------------------------------------------- */

int arc_extract(const char FAR *archive, const ARC_ENTRY FAR *e,
                const char FAR *out)
{
    int h, o, r;
    uint16_t crc;
    uint32_t data = e->data, csize = e->csize, osize = e->osize;
    uint16_t want = e->crc, date = e->date, time = e->time;
    uint8_t method = e->method;

    arc_progress(e->name);
    h = pf_open(archive);
    if (h < 0)
        return ARC_E_OPEN;
    if (pf_seek(h, (long)data) < 0) {
        pf_close(h);
        return ARC_E_NOTARC;
    }
    o = pf_create(out);
    if (o < 0) {
        pf_close(h);
        return ARC_E_CREATE;
    }
    in_start(h, csize, 1);
    out_start(o);
    r = arc_decode(method, &crc);
    out_flush();
    if (r == ARC_OK && ofail)
        r = ARC_E_WRITE;
    if (r == ARC_OK && (crc != want || ocount != osize))
        r = ARC_E_CRC;
    if (r == ARC_OK)
        pf_setstamp(o, date, time);
    pf_close(o);
    pf_close(h);
    if (r != ARC_OK)
        pf_delete(out);                 /* nothing half made is left */
    return r;
}

/* -- putting in ------------------------------------------------------------ */

/* An old member, header and data, byte for byte into the output. */
static int copy_member(int a, const ARC_ENTRY FAR *e)
{
    uint8_t m = e->method;
    uint32_t hl = (m == ARC_STORED1) ? ARC_HDR_OLD : ARC_HDR;
    int c;

    if (pf_seek(a, (long)(e->data - hl)) < 0)
        return ARC_E_NOTARC;
    in_start(a, hl + e->csize, 1);
    while ((c = arc_in()) >= 0)
        arc_out((uint8_t)c);
    return ofail ? ARC_E_WRITE : ARC_OK;
}

static char path[160];                  /* not on the Atari's small stack */

static int add_file(const char FAR *dir, const char FAR *name)
{
    char mname[ARC_NAMELEN];
    uint16_t k = 0, j, date = 0, time = 0;
    int s;
    char c;
    ARC_SIZES sz;
    uint32_t csize, start;
    uint8_t m;

    while ((c = dir[k]) != 0 && k < sizeof path - ARC_NAMELEN - 1)
        path[k++] = c;
    for (j = 0; (c = name[j]) != 0 && j < ARC_NAMELEN - 1; j++)
        path[k++] = c;
    path[k] = 0;
    arc_member_name(name, mname);
    s = pf_open(path);
    if (s < 0)
        return ARC_E_SOURCE;
    arc_progress(mname);
    in_start(s, 0, 0);
    arc_measure(&sz);
    m = arc_choose(&sz, &csize);
    pf_stamp(path, &date, &time);

    arc_out(ARC_MARK);
    arc_out(m);
    for (k = 0, j = 0; k < ARC_NAMELEN; k++) {
        c = j ? 0 : mname[k];          /* the name, then NULs to 13 */
        if (!c)
            j = 1;
        arc_out((uint8_t)c);
    }
    out32(csize);
    out16(date);
    out16(time);
    out16(sz.crc);
    out32(sz.size);

    start = ocount;
    if (pf_seek(s, 0) < 0) {
        pf_close(s);
        return ARC_E_SOURCE;
    }
    in_start(s, 0, 0);
    arc_encode(m);
    pf_close(s);
    if (ofail)
        return ARC_E_WRITE;
    if (ocount - start != csize)
        return ARC_E_DATA;              /* the two passes disagree */
    return ARC_OK;
}

int arc_add(const char FAR *archive, const char FAR *temp,
            const char FAR *dir, char FAR (*names)[ARC_NAMELEN],
            uint16_t count, ARC_ENTRY FAR *list, uint16_t max)
{
    uint16_t n = 0, i = 0, j = 0, a1, b1;
    uint16_t order[ARC_ADD_MAX];
    int a = -1, t, r;
    char FAR *x;
    char FAR *y;

    if (count > ARC_ADD_MAX)
        return ARC_E_FULL;
    r = arc_list(archive, list, max, &n);
    if (r == ARC_E_NOTARC || r == ARC_E_FULL)
        return r;
    if (r == ARC_OK) {
        a = pf_open(archive);
        if (a < 0)
            return ARC_E_OPEN;
    } else {
        n = 0;                          /* a new archive */
    }
    /* the new names in order: a few, so an insertion sort */
    for (i = 0; i < count; i++) {
        for (j = i; j > 0; j--) {
            a1 = order[j - 1];
            x = names[a1];
            y = names[i];
            if (name_cmp(x, y) <= 0)
                break;
            order[j] = a1;
        }
        order[j] = i;
    }
    t = pf_create(temp);
    if (t < 0) {
        if (a >= 0)
            pf_close(a);
        return ARC_E_CREATE;
    }
    out_start(t);
    r = ARC_OK;
    i = j = 0;
    while (r == ARC_OK && (i < n || j < count)) {
        if (j < count) {
            b1 = order[j];
            y = names[b1];
            if (i >= n || name_cmp(y, list[i].name) <= 0) {
                char mname[ARC_NAMELEN];
                arc_member_name(y, mname);
                if (i < n && name_cmp(mname, list[i].name) == 0)
                    i++;                /* replaced */
                r = add_file(dir, y);
                j++;
                continue;
            }
        }
        r = copy_member(a, &list[i]);
        i++;
    }
    if (r == ARC_OK) {
        arc_out(ARC_MARK);
        arc_out(0);
    }
    out_flush();
    if (r == ARC_OK && ofail)
        r = ARC_E_WRITE;
    pf_close(t);
    if (a >= 0)
        pf_close(a);
    if (r != ARC_OK) {
        pf_delete(temp);
        return r;
    }
    pf_delete(archive);
    if (pf_rename(temp, archive) < 0)
        return ARC_E_CREATE;
    return ARC_OK;
}
