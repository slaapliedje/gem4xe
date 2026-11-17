/* con.c -- GEMDOS's console, a VT-52 on GEM's screen.  See con.h.
 *
 * Everything is drawn through the AES's waist (src/aes/graf.c): a cell's
 * background is a solid fill in the paper colour, the characters on it a
 * transparent text run in the ink, a scroll one screen-to-screen blit.
 * Printable characters are gathered into a run and drawn together, so a
 * line of text is two VDI calls rather than two per character.  The
 * pointer is hidden and the clip opened to the whole screen for as long
 * as one write draws, and both are put back after it.
 */
#include "portab.h"
#include <string.h>
#include "con.h"
#include "farmem.h"
#include "../vdi/vdi.h"

#define CON_COLS    80          /* the most a row can hold: 640 / 8 */

/* The record, as con_write works on it: read from far memory at the start
 * of a call and written back at the end. */
typedef struct {
    uint8_t col, row;           /* the cursor; col == cols is "past the edge" */
    uint8_t ink, paper;         /* ESC b, ESC c: VDI colour indices */
    uint8_t flags;              /* CF_* */
    uint8_t esc;                /* how far into an escape sequence: ES_* */
    uint8_t yrow;               /* ESC Y's row, while its column is awaited */
    uint8_t scol, srow;         /* ESC j's saved position */
    uint8_t spare;
    WORD    key;                /* a key con_ready took and nobody has read */
} CONREC;

#define CF_WRAP     0x01        /* ESC v */
#define CF_REV      0x02        /* ESC p */
#define CF_CURSOR   0x04        /* ESC e */

#define ES_NONE     0
#define ES_ESC      1           /* ESC, and the code is next */
#define ES_YROW     2           /* ESC Y: the row next */
#define ES_YCOL     3           /* ...and then the column */
#define ES_INK      4           /* ESC b: the colour next */
#define ES_PAPER    5           /* ESC c */

#define C_BEL       0x07
#define C_BS        0x08
#define C_TAB       0x09
#define C_LF        0x0A
#define C_VT        0x0B
#define C_FF        0x0C
#define C_CR        0x0D
#define C_ESC       0x1B

/* The screen in cells, and whether this call has started drawing. */
typedef struct {
    WORD cw, ch;                /* a cell */
    WORD cols, rows;
    WORD drawing;
    GRECT clip;                 /* the AES's, to put back */
    WORD rn, rcol;              /* the run waiting to be drawn */
    uint8_t run[CON_COLS];
} CONDRAW;

static void geometry(CONDRAW *d)
{
    d->cw = gl_wchar;
    d->ch = gl_hchar;
    d->cols = (WORD)(gl_width / d->cw);
    if (d->cols > CON_COLS)
        d->cols = CON_COLS;
    d->rows = (WORD)(gl_height / d->ch);
    d->drawing = 0;
    d->rn = 0;
}

static void begin(CONDRAW *d)
{
    GRECT all;

    if (d->drawing)
        return;
    d->drawing = 1;
    gsx_moff();
    gsx_gclip(&d->clip);
    r_set(&all, 0, 0, gl_width, gl_height);
    gsx_sclip(&all);
}

static void end(CONDRAW *d)
{
    if (!d->drawing)
        return;
    gsx_sclip(&d->clip);
    gsx_mon();
}

/* ncols x nrows cells from (col, row), to the paper colour. */
static void erase(CONDRAW *d, const CONREC *c, WORD col, WORD row,
                  WORD ncols, WORD nrows)
{
    if (ncols <= 0 || nrows <= 0)
        return;
    begin(d);
    gsx_fcolor(c->paper);
    bb_fill(MD_REPLACE, FIS_SOLID, 0, (WORD)(col * d->cw), (WORD)(row * d->ch),
            (WORD)(ncols * d->cw), (WORD)(nrows * d->ch));
}

/* The rows below `top` up one, and the last row blank. */
static void scroll_up(CONDRAW *d, const CONREC *c, WORD top)
{
    WORD last = (WORD)(d->rows - 1);

    if (top < last) {
        begin(d);
        bb_screen(0, (WORD)((top + 1) * d->ch), 0, (WORD)(top * d->ch),
                  (WORD)(d->cols * d->cw), (WORD)((last - top) * d->ch));
    }
    erase(d, c, 0, last, d->cols, 1);
}

/* The rows from `top` down one, the last falling off, and `top` blank. */
static void scroll_down(CONDRAW *d, const CONREC *c, WORD top)
{
    WORD last = (WORD)(d->rows - 1);

    if (top < last) {
        begin(d);
        bb_screen(0, (WORD)(top * d->ch), 0, (WORD)((top + 1) * d->ch),
                  (WORD)(d->cols * d->cw), (WORD)((last - top) * d->ch));
    }
    erase(d, c, 0, top, d->cols, 1);
}

/* The run gathered so far, drawn where it began: the cells in the paper,
 * then the characters in the ink -- the two swapped under ESC p. */
static void flush(CONDRAW *d, const CONREC *c)
{
    WORD i, ink = c->ink, paper = c->paper, x, y;

    if (!d->rn)
        return;
    if (c->flags & CF_REV) {
        ink = c->paper;
        paper = c->ink;
    }
    x = (WORD)(d->rcol * d->cw);
    y = (WORD)(c->row * d->ch);
    begin(d);
    gsx_fcolor(paper);
    bb_fill(MD_REPLACE, FIS_SOLID, 0, x, y, (WORD)(d->rn * d->cw), d->ch);
    gsx_attr(1, MD_TRANS, ink);
    for (i = 0; i < d->rn; i++)         /* after the attributes: they use intin[0] */
        intin[i] = d->run[i];
    gsx_tblt(0, x, y, d->rn);
    d->rn = 0;
}

static void newline(CONDRAW *d, CONREC *c)
{
    if (c->row + 1 < d->rows)
        c->row++;
    else
        scroll_up(d, c, 0);
}

/* One printable character at the cursor.  At the right edge it waits
 * there, and the character after it wraps to the next line or, with wrap
 * off, overwrites the last cell -- the VT-52's two behaviours. */
static void put(CONDRAW *d, CONREC *c, uint8_t ch)
{
    if (c->col >= d->cols) {
        flush(d, c);
        if (c->flags & CF_WRAP) {
            c->col = 0;
            newline(d, c);
        } else
            c->col = (uint8_t)(d->cols - 1);
    }
    if (!d->rn)
        d->rcol = c->col;
    d->run[d->rn++] = ch;
    c->col++;
}

/* The last column the cursor may be addressed at. */
static void clampcol(CONDRAW *d, CONREC *c)
{
    if (c->col >= d->cols)
        c->col = (uint8_t)(d->cols - 1);
}

/* A byte of an escape sequence. */
static void escape(CONDRAW *d, CONREC *c, uint8_t ch)
{
    WORD col, row, last = (WORD)(d->rows - 1);

    switch (c->esc) {
    case ES_YROW:
        c->yrow = ch;
        c->esc = ES_YCOL;
        return;
    case ES_YCOL:
        c->esc = ES_NONE;
        row = (WORD)(c->yrow - 32);
        col = (WORD)(ch - 32);
        if (row < 0)
            row = 0;
        if (row > last)
            row = last;
        if (col < 0)
            col = 0;
        if (col >= d->cols)
            col = (WORD)(d->cols - 1);
        c->row = (uint8_t)row;
        c->col = (uint8_t)col;
        return;
    case ES_INK:
        c->ink = (uint8_t)(ch & 0x0F);
        c->esc = ES_NONE;
        return;
    case ES_PAPER:
        c->paper = (uint8_t)(ch & 0x0F);
        c->esc = ES_NONE;
        return;
    }
    c->esc = ES_NONE;
    clampcol(d, c);
    col = c->col;
    row = c->row;
    switch (ch) {
    case 'A':
        if (row > 0)
            c->row--;
        break;
    case 'B':
        if (row < last)
            c->row++;
        break;
    case 'C':
        if (col < d->cols - 1)
            c->col++;
        break;
    case 'D':
        if (col > 0)
            c->col--;
        break;
    case 'E':
        erase(d, c, 0, 0, d->cols, d->rows);
        c->col = c->row = 0;
        break;
    case 'H':
        c->col = c->row = 0;
        break;
    case 'I':
        if (row > 0)
            c->row--;
        else
            scroll_down(d, c, 0);
        break;
    case 'J':
        erase(d, c, col, row, (WORD)(d->cols - col), 1);
        erase(d, c, 0, (WORD)(row + 1), d->cols, (WORD)(last - row));
        break;
    case 'K':
        erase(d, c, col, row, (WORD)(d->cols - col), 1);
        break;
    case 'L':
        scroll_down(d, c, row);
        c->col = 0;
        break;
    case 'M':
        scroll_up(d, c, row);
        c->col = 0;
        break;
    case 'Y':
        c->esc = ES_YROW;
        break;
    case 'b':
        c->esc = ES_INK;
        break;
    case 'c':
        c->esc = ES_PAPER;
        break;
    case 'd':
        erase(d, c, 0, 0, d->cols, row);
        erase(d, c, 0, row, (WORD)(col + 1), 1);
        break;
    case 'e':
        c->flags |= CF_CURSOR;
        break;
    case 'f':
        c->flags = (uint8_t)(c->flags & ~CF_CURSOR);
        break;
    case 'j':
        c->scol = (uint8_t)col;
        c->srow = (uint8_t)row;
        break;
    case 'k':
        c->col = c->scol;
        c->row = c->srow;
        break;
    case 'l':
        erase(d, c, 0, row, d->cols, 1);
        c->col = 0;
        break;
    case 'o':
        erase(d, c, 0, row, (WORD)(col + 1), 1);
        break;
    case 'p':
        c->flags |= CF_REV;
        break;
    case 'q':
        c->flags = (uint8_t)(c->flags & ~CF_REV);
        break;
    case 'v':
        c->flags |= CF_WRAP;
        break;
    case 'w':
        c->flags = (uint8_t)(c->flags & ~CF_WRAP);
        break;
    default:                            /* not a VT-52 escape: both go */
        break;
    }
}

void con_reset(uint32_t rec)
{
    CONREC c;

    memset(&c, 0, sizeof c);
    c.ink = 1;
    c.flags = CF_CURSOR;
    far_put(rec, (const uint8_t *)&c, sizeof c);
}

void con_write(uint32_t rec, const uint8_t *s, uint16_t n)
{
    CONREC c;
    CONDRAW d;
    uint16_t i;

    far_get((uint8_t *)&c, rec, sizeof c);
    geometry(&d);
    for (i = 0; i < n; i++) {
        uint8_t ch = s[i];

        if (c.esc != ES_NONE) {
            flush(&d, &c);
            escape(&d, &c, ch);
            continue;
        }
        if (ch >= ' ') {
            put(&d, &c, ch);
            continue;
        }
        flush(&d, &c);
        switch (ch) {
        case C_BS:
            if (c.col >= d.cols)
                c.col = (uint8_t)(d.cols - 1);
            if (c.col > 0)
                c.col--;
            break;
        case C_TAB:                     /* spaces to the next stop, as
                                         * GEMDOS's output does (EmuTOS
                                         * bdos/console.c, tabout) */
            do
                put(&d, &c, ' ');
            while ((c.col & 7) && c.col < d.cols);
            flush(&d, &c);
            break;
        case C_LF:
        case C_VT:
        case C_FF:
            newline(&d, &c);
            break;
        case C_CR:
            c.col = 0;
            break;
        case C_ESC:
            c.esc = ES_ESC;
            break;
        default:                        /* BEL and the rest: nothing */
            break;
        }
    }
    flush(&d, &c);
    end(&d);
    far_put(rec, (const uint8_t *)&c, sizeof c);
}

/* The cursor block, XORed on and off at a cell.  The column is clamped
 * into a local of its own, not into the parameter: a parameter changed on
 * one path of a conditional in an inlined static is B10 (tools/ccbug). */
static void cursor(WORD col, WORD row)
{
    CONDRAW d;
    WORD x;

    geometry(&d);
    x = col;
    if (x >= d.cols)
        x = (WORD)(d.cols - 1);
    begin(&d);
    gsx_fcolor(1);
    bb_fill(MD_XOR, FIS_SOLID, 0, (WORD)(x * d.cw), (WORD)(row * d.ch), d.cw, d.ch);
    end(&d);
}

WORD con_key(uint32_t rec, WORD wait)
{
    CONREC c;
    WORD k, col, row, shown;

    far_get((uint8_t *)&c, rec, sizeof c);
    if (c.key) {
        k = c.key;
        c.key = 0;
        far_put(rec, (const uint8_t *)&c, sizeof c);
        return k;
    }
    if (!wait) {
        if (!ev_keyq(&k))
            return 0;
        return k;
    }
    /* The position is kept here, not read back: an accessory may write to
     * the console while this waits, and the block has to come off where
     * it went on. */
    col = c.col;
    row = c.row;
    shown = (c.flags & CF_CURSOR) != 0;
    if (shown)
        cursor(col, row);
    k = ev_keybd();
    if (shown)
        cursor(col, row);
    return k;
}

WORD con_ready(uint32_t rec)
{
    CONREC c;
    WORD k;

    far_get((uint8_t *)&c, rec, sizeof c);
    if (c.key)
        return 1;
    if (!ev_keyq(&k))
        return 0;
    far_get((uint8_t *)&c, rec, sizeof c);  /* the poll gave others a turn */
    c.key = k;
    far_put(rec, (const uint8_t *)&c, sizeof c);
    return 1;
}

WORD con_col(uint32_t rec)
{
    return far_read8(rec);              /* CONREC's first byte */
}
