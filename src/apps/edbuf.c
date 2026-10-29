/* EDIT's text: a gap buffer and the file's own line ends (edbuf.h). */
#include "edbuf.h"

#define EOL_ATARI 0x9B

void ed_init(EDBUF *e, uint8_t FAR *buf, uint16_t cap)
{
    e->b = buf;
    e->cap = cap;
    e->gs = 0;
    e->ge = cap;
    e->lines = 1;
    e->eol = ED_ATARI;
    e->dirty = 0;
}

uint16_t ed_len(const EDBUF *e)
{
    uint16_t gap = (uint16_t)(e->ge - e->gs);

    return (uint16_t)(e->cap - gap);
}

uint16_t ed_room(const EDBUF *e)
{
    return (uint16_t)(e->ge - e->gs);
}

uint8_t ed_at(const EDBUF *e, uint16_t p)
{
    uint16_t gs = e->gs;

    if (p < gs)
        return e->b[p];
    return e->b[(uint16_t)(p + (uint16_t)(e->ge - gs))];
}

void ed_span(const EDBUF *e, uint16_t *n1, uint8_t FAR **p2, uint16_t *n2)
{
    uint16_t ge = e->ge;

    *n1 = e->gs;
    *p2 = e->b + ge;
    *n2 = (uint16_t)(e->cap - ge);
}

uint16_t ed_eol_at(const EDBUF *e, uint16_t p)
{
    uint16_t len = ed_len(e);
    uint8_t c, kind = e->eol;

    if (p >= len)
        return 0;
    c = ed_at(e, p);
    if (kind == ED_ATARI)
        return (uint16_t)(c == EOL_ATARI);
    if (kind == ED_LF)
        return (uint16_t)(c == '\n');
    if (kind == ED_CR)
        return (uint16_t)(c == '\r');
    if (c != '\r' || (uint16_t)(p + 1) >= len)
        return 0;
    return (uint16_t)(ed_at(e, (uint16_t)(p + 1)) == '\n' ? 2 : 0);
}

uint16_t ed_eol_before(const EDBUF *e, uint16_t p)
{
    if (p == 0)
        return 0;
    if (e->eol == ED_CRLF) {
        if (p < 2)
            return 0;
        return ed_eol_at(e, (uint16_t)(p - 2));
    }
    return ed_eol_at(e, (uint16_t)(p - 1));
}

uint16_t ed_bol(const EDBUF *e, uint16_t p)
{
    while (p > 0 && !ed_eol_before(e, p))
        p--;
    return p;
}

uint16_t ed_eolpos(const EDBUF *e, uint16_t p)
{
    uint16_t len = ed_len(e);

    while (p < len && !ed_eol_at(e, p))
        p++;
    return p;
}

uint16_t ed_next(const EDBUF *e, uint16_t p)
{
    uint16_t q = ed_eolpos(e, p);

    return (uint16_t)(q + ed_eol_at(e, q));
}

uint16_t ed_prev(const EDBUF *e, uint16_t p)
{
    uint16_t b = ed_bol(e, p), k;

    if (b == 0)
        return 0;
    k = ed_eol_before(e, b);
    return ed_bol(e, (uint16_t)(b - k));
}

uint16_t ed_left(const EDBUF *e, uint16_t p)
{
    uint16_t k;

    if (p == 0)
        return 0;
    k = ed_eol_before(e, p);
    return (uint16_t)(p - (k ? k : 1));
}

uint16_t ed_right(const EDBUF *e, uint16_t p)
{
    uint16_t k;

    if (p >= ed_len(e))
        return p;
    k = ed_eol_at(e, p);
    return (uint16_t)(p + (k ? k : 1));
}

uint16_t ed_width(const EDBUF *e, uint8_t c, uint16_t col)
{
    if (c == '\t' && e->eol != ED_ATARI)
        return (uint16_t)(ED_TAB - col % ED_TAB);
    return 1;
}

uint16_t ed_col(const EDBUF *e, uint16_t bol, uint16_t p)
{
    uint16_t c = 0;

    while (bol < p) {
        c = (uint16_t)(c + ed_width(e, ed_at(e, bol), c));
        bol++;
    }
    return c;
}

uint16_t ed_atcol(const EDBUF *e, uint16_t bol, uint16_t col)
{
    uint16_t len = ed_len(e), c = 0, w;

    while (bol < len && !ed_eol_at(e, bol)) {
        w = ed_width(e, ed_at(e, bol), c);
        if ((uint16_t)(c + w) > col)
            break;
        c = (uint16_t)(c + w);
        bol++;
    }
    return bol;
}

uint16_t ed_up(const EDBUF *e, uint16_t p, uint16_t goal)
{
    if (ed_bol(e, p) == 0)
        return p;
    return ed_atcol(e, ed_prev(e, p), goal);
}

uint16_t ed_down(const EDBUF *e, uint16_t p, uint16_t goal)
{
    uint16_t q = ed_eolpos(e, p), k = ed_eol_at(e, q);

    if (!k)
        return p;
    return ed_atcol(e, (uint16_t)(q + k), goal);
}

/* Line ends that START from a to z (z itself excluded). */
static uint16_t count(const EDBUF *e, uint16_t a, uint16_t z)
{
    uint16_t n = 0, k;

    while (a < z) {
        k = ed_eol_at(e, a);
        if (k) {
            n++;
            a = (uint16_t)(a + k);
        } else {
            a++;
        }
    }
    return n;
}

/* The gap moved to p. */
static void gap_to(EDBUF *e, uint16_t p)
{
    uint8_t FAR *b = e->b;
    uint16_t gs = e->gs, ge = e->ge;

    while (p < gs) {                    /* text before the gap goes after */
        gs--;
        ge--;
        b[ge] = b[gs];
    }
    while (p > gs) {                    /* text after it comes before */
        b[gs] = b[ge];
        gs++;
        ge++;
    }
    e->gs = gs;
    e->ge = ge;
}

static uint16_t lo_of(uint16_t p)
{
    return (uint16_t)(p ? p - 1 : 0);
}

static uint16_t hi_of(const EDBUF *e, uint16_t p)
{
    uint16_t len = ed_len(e);

    return (uint16_t)(p < len ? p + 1 : len);
}

/* A change at p can make or break a line end only at p's neighbours: a
 * CR LF split by an insert, or joined by a delete.  So the line ends are
 * counted in that window before and after, not in the whole text. */
int ed_insert(EDBUF *e, uint16_t p, const uint8_t *s, uint16_t n)
{
    uint16_t lo = lo_of(p), before, after, i, lines;

    if (n > ed_room(e))
        return 0;
    before = count(e, lo, hi_of(e, p));
    gap_to(e, p);
    for (i = 0; i < n; i++)
        e->b[(uint16_t)(p + i)] = s[i];
    e->gs = (uint16_t)(p + n);
    after = count(e, lo, hi_of(e, (uint16_t)(p + n)));
    lines = e->lines;
    e->lines = (uint16_t)(lines + after - before);
    e->dirty = 1;
    return 1;
}

int ed_newline(EDBUF *e, uint16_t p)
{
    uint8_t s[2];
    uint16_t n = 1;

    switch (e->eol) {
    case ED_CRLF: s[0] = '\r'; s[1] = '\n'; n = 2; break;
    case ED_LF:   s[0] = '\n'; break;
    case ED_CR:   s[0] = '\r'; break;
    default:      s[0] = EOL_ATARI; break;
    }
    return ed_insert(e, p, s, n);
}

void ed_delete(EDBUF *e, uint16_t p, uint16_t n)
{
    uint16_t lo = lo_of(p), before, after, len = ed_len(e), lines, ge;

    if (p >= len)
        return;
    if (n > (uint16_t)(len - p))
        n = (uint16_t)(len - p);
    before = count(e, lo, hi_of(e, (uint16_t)(p + n)));
    gap_to(e, p);
    ge = e->ge;
    e->ge = (uint16_t)(ge + n);
    after = count(e, lo, hi_of(e, p));
    lines = e->lines;
    e->lines = (uint16_t)(lines + after - before);
    e->dirty = 1;
}

uint16_t ed_del_right(EDBUF *e, uint16_t p)
{
    uint16_t k;

    if (p >= ed_len(e))
        return p;
    k = ed_eol_at(e, p);
    ed_delete(e, p, k ? k : 1);
    return p;
}

uint16_t ed_del_left(EDBUF *e, uint16_t p)
{
    uint16_t k, n;

    if (p == 0)
        return 0;
    k = ed_eol_before(e, p);
    n = k ? k : 1;
    ed_delete(e, (uint16_t)(p - n), n);
    return (uint16_t)(p - n);
}

void ed_loaded(EDBUF *e, uint16_t n)
{
    uint16_t i;
    uint8_t c, kind = ED_ATARI;

    e->gs = n;
    e->ge = e->cap;
    for (i = 0; i < n; i++) {
        c = e->b[i];
        if (c == EOL_ATARI)
            break;
        if (c == '\n') {
            kind = ED_LF;
            break;
        }
        if (c == '\r') {
            kind = (uint8_t)((uint16_t)(i + 1) < n && e->b[(uint16_t)(i + 1)] == '\n'
                             ? ED_CRLF : ED_CR);
            break;
        }
    }
    e->eol = kind;
    e->lines = (uint16_t)(count(e, 0, n) + 1);
    e->dirty = 0;
}
