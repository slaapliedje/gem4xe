/* EDIT: a small text editor, opened from the desktop's Show (docs/edit.md).
 *
 * One window on one file.  The text and its line ends are
 * src/apps/edbuf.c, which tests/host/test_edit.py runs on the host; this
 * file is the GEM program around it: the window, the keys, and the file
 * read and written through GEMDOS.
 *
 * AN ATARI FILE IS DRAWN IN THE ATARI'S CHARACTERS.  The system font is
 * the ST's, which has the ASCII the two share and its own glyphs for the
 * rest; ATASCII's graphics ($00-$1F, $60, $7B and $7D-$7F) would come
 * out as the wrong pictures and inverse video (bit 7) as accented
 * letters.  So the OS's character set is read out of the machine at
 * start-up -- never shipped: it is Atari's -- into a one-plane form, and
 * a graphic is copied from it with vrt_cpyfm.  Everything else is the
 * system font through v_gtext, a run at a time, with inverse video drawn
 * as white on a black bar.  An ST or PC file is drawn in the system
 * font, byte for byte, as QED draws it.
 *
 * Built --data-model=large: the text and the glyphs come from Malloc,
 * the resource goes far, and what must be in bank $00 is on the stack --
 * the file selector's two buffers and the MFDBs vrt_cpyfm is handed
 * (src/app/gem.h).  Every word a person reads is in EDIT.RSC
 * (tools/editrsc.py). */
#include "gem.h"
#include "edbuf.h"
#include "editrsc.h"

#define ED_MAX    32768L            /* the largest file EDIT opens */
#define ED_CAP    40960U            /* the buffer: that, and 8 KB to type */
#define PATHLEN   GEM_PATH_MAX
#define MAXCOLS   100               /* a row of the window, at most */
#define MARGIN    4                 /* pixels left of the text: even, so a
                                     * glyph copy stays on the fast path */
#define KEY_UP    0x4800
#define KEY_DOWN  0x5000
#define KEY_LEFT  0x4B00
#define KEY_RIGHT 0x4D00
#define KEY_RET   0x1C0D
#define KEY_BS    0x0E08
#define KEY_DEL   0x537F
#define KEY_TAB   0x0F09
#define KEY_ESC   0x011B
#define ATASCII_TAB 0x7F

/* Globals, not statics, where a gate reads them by name
 * (tests/emu/edit.py): the work area, the cursor and the glyphs. */
static WORD vh, wh = -1, wchar, hchar;
WORD wx, wy;                        /* the window's work area ... */
static WORD ww, whh;                /* ... and its size */
static WORD rows, cols;             /* text cells it holds */
static OBJECT *menu;

static EDBUF ed;
uint16_t cur;                       /* the cursor */
static uint16_t goal;               /* the column up and
                                     * down aim for */
uint16_t curline;                   /* the cursor's line, from 0 */
static uint16_t top, topline;       /* the first row's line: where, which */
static uint16_t left;               /* the first column shown */
uint8_t FAR *glyphs;                /* the Atari's characters, 0 if none */

static char path[PATHLEN];          /* the file's, "" for none */
static char lastdir[PATHLEN];
static char title[PATHLEN + 6];
static char info[100];
static char msg[300];
static char run[MAXCOLS + 1];       /* a run of one row, for v_gtext */

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];

/* -- small things ------------------------------------------------------------ */

static char FAR *str(WORD i)
{
    char FAR *s = 0;

    rsrc_gaddr(R_STRING, i, (void **)&s);
    return s;
}

static uint16_t slen(const char FAR *s)
{
    uint16_t n = 0;

    while (s[n])
        n++;
    return n;
}

static void scpy(char *d, const char FAR *s, uint16_t max)
{
    uint16_t k;
    char c;

    for (k = 0; k < max - 1 && (c = s[k]) != 0; k++)
        d[k] = c;
    d[k] = 0;
}

static uint16_t udec(char *d, uint32_t v)
{
    char t[12];
    uint16_t n = 0, k = 0;

    do {
        t[n++] = (char)('0' + (uint16_t)(v % 10));
        v /= 10;
    } while (v);
    while (n)
        d[k++] = t[--n];
    d[k] = 0;
    return k;
}

/* A resource string with each '#' the next of `nums` and '@' `name`. */
static void fill(char *d, uint16_t max, WORD which, const uint32_t *nums,
                 const char FAR *name)
{
    const char FAR *s = str(which);
    uint16_t k = 0, j;
    char c, t[12];

    while ((c = *s++) != 0 && k < max - 12) {
        if (c == '#' && nums) {
            udec(t, *nums++);
            for (j = 0; t[j]; j++)
                d[k++] = t[j];
        } else if (c == '@' && name) {
            for (j = 0; name[j] && k < max - 1; j++)
                d[k++] = name[j];
        } else {
            d[k++] = c;
        }
    }
    d[k] = 0;
}

/* The name part of a path. */
static const char *name_of(const char *p)
{
    uint16_t k, cut = 0;

    for (k = 0; p[k]; k++)
        if (p[k] == '\\' || p[k] == ':')
            cut = (uint16_t)(k + 1);
    return p + cut;
}

static WORD alert(WORD which, uint32_t n)
{
    fill(msg, sizeof msg, which, &n, name_of(path));
    return form_alert(1, msg);
}

static void dir_of(const char *p, char *dir)
{
    uint16_t k, cut = (uint16_t)(name_of(p) - p);

    for (k = 0; k < cut; k++)
        dir[k] = p[k];
    dir[cut] = 0;
}

/* -- the Atari's characters --------------------------------------------------- */

/* The OS's set, read where every XL OS keeps it -- found, not assumed: a
 * space must be blank and an A must not be, or there is no set to read
 * (a machine whose $E000 is something else draws graphics as text).
 * Copied into a form 1024 pixels wide, ATASCII order: character c's row r
 * at byte r * 128 + c.  The OS keeps them in its internal order, which
 * puts $20-$5F first, then $00-$1F, then $60-$7F. */
#define OS_CHARSET 0xE000UL

static void glyphs_read(void)
{
    const uint8_t FAR *rom = (const uint8_t FAR *)OS_CHARSET;
    uint16_t c, r, in, blank = 0, ink = 0;
    LONG a;

    if (wchar != 8 || hchar < 8)
        return;                         /* cells the glyphs do not fill */
    for (r = 0; r < 8; r++) {
        blank |= rom[r];                /* internal 0, the space */
        ink |= rom[0x21 * 8 + r];       /* internal $21, the A */
    }
    if (blank || !ink)
        return;
    a = Malloc(1024L);
    if (a <= 0)
        return;
    glyphs = (uint8_t FAR *)(uint32_t)a;
    for (c = 0; c < 128; c++) {
        if (c < 0x20)
            in = (uint16_t)(c + 0x40);
        else if (c < 0x60)
            in = (uint16_t)(c - 0x20);
        else
            in = c;
        for (r = 0; r < 8; r++)
            glyphs[(uint16_t)(r * 128 + c)] = rom[(uint16_t)(in * 8 + r)];
    }
}

/* Is ATASCII c (bit 7 off) a picture the system font has no glyph for? */
static WORD graphic(uint16_t c)
{
    return (WORD)(c < 0x20 || c == 0x60 || c == 0x7B || c >= 0x7D);
}

static void glyph_draw(uint16_t c, WORD x, WORD y, WORD inverse)
{
    MFDB src, scr;
    WORD pxy[8], col[2];

    src.fd_addr = (uint32_t)glyphs;
    src.fd_w = 1024;
    src.fd_h = 8;
    src.fd_wdwidth = 64;
    src.fd_stand = 0;
    src.fd_nplanes = 1;
    src.fd_r1 = src.fd_r2 = src.fd_r3 = 0;
    scr.fd_addr = 0;
    pxy[0] = (WORD)(c * 8);
    pxy[1] = 0;
    pxy[2] = (WORD)(c * 8 + 7);
    pxy[3] = 7;
    pxy[4] = x;
    pxy[5] = y;
    pxy[6] = (WORD)(x + 7);
    pxy[7] = (WORD)(y + 7);
    col[0] = inverse ? 0 : 1;
    col[1] = inverse ? 1 : 0;
    vrt_cpyfm(vh, MD_REPLACE, pxy, &src, &scr, col);
}

/* -- drawing ------------------------------------------------------------------ */

static void bar(WORD x, WORD y, WORD w, WORD color)
{
    WORD pxy[4];

    vsf_color(vh, color);
    pxy[0] = x;
    pxy[1] = y;
    pxy[2] = (WORD)(x + w - 1);
    pxy[3] = (WORD)(y + hchar - 1);
    vr_recfl(vh, pxy);
}

/* The run so far, from column `at`, n cells. */
static void flush(WORD at, uint16_t n, WORD inverse, WORD y)
{
    WORD x = (WORD)(wx + MARGIN + at * wchar);

    if (!n)
        return;
    run[n] = 0;
    if (inverse) {
        bar(x, y, (WORD)(n * wchar), 1);
        vst_color(vh, 0);
    }
    v_gtext(vh, x, y, run);
    if (inverse)
        vst_color(vh, 1);
}

/* Row r of the window, its line starting at p -- or past the text's last
 * line, when `p` is 0xFFFF, a blank row. */
static void draw_row(WORD r, uint16_t p)
{
    WORD y = (WORD)(wy + r * hchar), inv = 0, cinv, at = 0;
    WORD atari = ed.eol == ED_ATARI;
    uint16_t col = 0, n = 0, len = ed_len(&ed), w, c, shown;

    bar(wx, y, ww, 0);
    if (p == 0xFFFF)
        return;
    for (;;) {
        WORD end = p >= len || ed_eol_at(&ed, p);
        WORD here = p == cur;

        if (end)
            c = ' ';
        else
            c = ed_at(&ed, p);
        w = end ? 1 : ed_width(&ed, (uint8_t)c, col);
        cinv = 0;
        if (atari) {
            cinv = (WORD)((c & 0x80) != 0);
            c &= 0x7F;
        } else if (c < 0x20) {
            c = ' ';                    /* a tab is spaces, a control too */
        }
        if (here)
            cinv = !cinv;
        while (w--) {
            if (col >= left && col < (uint16_t)(left + cols)) {
                shown = (uint16_t)(col - left);
                if (atari && graphic(c) && glyphs) {
                    flush(at, n, inv, y);
                    n = 0;
                    glyph_draw(c, (WORD)(wx + MARGIN + shown * wchar), y, cinv);
                    at = (WORD)(shown + 1);
                } else {
                    if (n && cinv != inv) {
                        flush(at, n, inv, y);
                        n = 0;
                    }
                    if (!n) {
                        at = (WORD)shown;
                        inv = cinv;
                    }
                    /* no glyphs: the ASCII a graphic shares a code
                     * with, and a blank for a control character */
                    run[n++] = (char)(atari && c < 0x20 ? ' ' : c);
                }
            }
            col++;
            c = ' ';                    /* a tab's other columns */
            if (here)
                cinv = 0, here = 0;
        }
        if (end || col >= (uint16_t)(left + cols))
            break;
        p++;
    }
    flush(at, n, inv, y);
}

/* The line starting at p, k lines further down: its start, or 0xFFFF. */
static uint16_t lines_down(uint16_t p, uint16_t k)
{
    uint16_t q;

    while (k--) {
        q = ed_eolpos(&ed, p);
        if (!ed_eol_at(&ed, q))
            return 0xFFFF;
        p = (uint16_t)(q + ed_eol_at(&ed, q));
    }
    return p;
}

static void draw_rows(WORD from, WORD to)
{
    uint16_t p = lines_down(top, (uint16_t)from);
    WORD r;

    for (r = from; r < to; r++) {
        draw_row(r, p);
        if (p != 0xFFFF)
            p = lines_down(p, 1);
    }
}

/* Rows from..to (excluded) drawn, through the window's rectangle list. */
static void redraw_rows(WORD from, WORD to, WORD x, WORD y, WORD w, WORD h)
{
    WORD rx, ry, rw, rh, pxy[4];

    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    vswr_mode(vh, MD_TRANS);
    vsf_interior(vh, FIS_SOLID);
    vst_color(vh, 1);
    wind_get(wh, WF_FIRSTXYWH, &rx, &ry, &rw, &rh);
    while (rw && rh) {
        WORD ax = rx > x ? rx : x, ay = ry > y ? ry : y;
        WORD bx = (rx + rw < x + w) ? rx + rw : x + w;
        WORD by = (ry + rh < y + h) ? ry + rh : y + h;

        if (bx > ax && by > ay) {
            WORD f = (WORD)((ay - wy) / hchar), t = (WORD)((by - wy + hchar - 1) / hchar);

            if (f < from)
                f = from;
            if (t > to)
                t = to;
            pxy[0] = ax;
            pxy[1] = ay;
            pxy[2] = (WORD)(bx - 1);
            pxy[3] = (WORD)(by - 1);
            vs_clip(vh, 1, pxy);
            bar(wx, (WORD)(wy + rows * hchar), ww, 0);  /* below the last row */
            if (f < t)
                draw_rows(f, t);
        }
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    vs_clip(vh, 0, pxy);
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

static void redraw(WORD x, WORD y, WORD w, WORD h)
{
    redraw_rows(0, rows, x, y, w, h);
}

static void redraw_all(void)
{
    redraw(wx, wy, ww, whh);
}

static void set_slider(void)
{
    uint16_t n = ed.lines;
    WORD size = 1000, pos = 0;

    if (n > (uint16_t)rows) {
        size = (WORD)((uint32_t)rows * 1000UL / n);
        pos = (WORD)((uint32_t)topline * 1000UL / (n - rows));
    }
    wind_set(wh, WF_VSLSIZ, size, 0, 0, 0);
    wind_set(wh, WF_VSLIDE, pos, 0, 0, 0);
}

static void set_title(void)
{
    uint16_t k;
    const char FAR *s = path[0] ? (const char FAR *)path : str(ST_TITLE);

    title[0] = ' ';
    scpy(title + 1, s, PATHLEN);
    k = slen(title);
    if (ed.dirty) {
        title[k++] = ' ';
        title[k++] = '*';
    }
    title[k++] = ' ';
    title[k] = 0;
    wind_set_str(wh, WF_NAME, title);
}

static void set_info(void)
{
    uint32_t n[2];

    n[0] = (uint32_t)curline + 1;
    n[1] = (uint32_t)ed_col(&ed, ed_bol(&ed, cur), cur) + 1;
    fill(info, sizeof info, ST_INFO, n, str((WORD)(ST_EATARI + ed.eol)));
    wind_set_str(wh, WF_INFO, info);
}

static void work_area(void)
{
    wind_get(wh, WF_WORKXYWH, &wx, &wy, &ww, &whh);
    rows = (WORD)(whh / hchar);
    cols = (WORD)((ww - MARGIN) / wchar);
    if (rows < 1)
        rows = 1;
    if (cols < 1)
        cols = 1;
    if (cols > MAXCOLS)
        cols = MAXCOLS;
}

/* -- the cursor and the view -------------------------------------------------- */

/* The cursor's row on screen, or -1 when it is off it. */
static WORD cur_row(void)
{
    if (curline < topline || curline >= (uint16_t)(topline + rows))
        return -1;
    return (WORD)(curline - topline);
}

/* Bring the cursor into view; TRUE if the view moved. */
static WORD follow(void)
{
    uint16_t c = ed_col(&ed, ed_bol(&ed, cur), cur);
    WORD moved = FALSE;

    if (curline < topline) {
        top = ed_bol(&ed, cur);
        topline = curline;
        moved = TRUE;
    } else if (curline >= (uint16_t)(topline + rows)) {
        uint16_t k = (uint16_t)(curline - topline - rows + 1);
        top = lines_down(top, k);
        topline = (uint16_t)(topline + k);
        moved = TRUE;
    }
    if (c < left) {
        left = (uint16_t)(c - c % 8);
        moved = TRUE;
    } else if (c >= (uint16_t)(left + cols)) {
        left = (uint16_t)((c - cols + 8) & ~7U);
        moved = TRUE;
    }
    return moved;
}

/* The view from line n, and the cursor kept in it. */
static void view_from(long n)
{
    long most = (long)ed.lines - rows;
    uint16_t t;

    if (n > most)
        n = most;
    if (n < 0)
        n = 0;
    t = (uint16_t)n;
    if (t == topline)
        return;
    top = lines_down(0, t);
    topline = t;
    if (curline < topline) {
        cur = ed_atcol(&ed, top, goal);
        curline = topline;
    } else if (curline >= (uint16_t)(topline + rows)) {
        uint16_t last = (uint16_t)(topline + rows - 1);
        cur = ed_atcol(&ed, lines_down(top, (uint16_t)(last - topline)), goal);
        curline = last;
    }
    set_slider();
    set_info();
    redraw_all();
}

/* -- the file ----------------------------------------------------------------- */

static void reset_view(void)
{
    cur = goal = curline = top = topline = left = 0;
}

/* Read `p` into the buffer; FALSE (and an alert) if it is not taken.  A
 * name that is not there is a new, empty file. */
static WORD load(const char *p)
{
    LONG h, n;

    scpy(path, p, PATHLEN);
    ed_init(&ed, ed.b, ED_CAP);
    reset_view();
    h = Fopen(path, 0);
    if (h == EFILNF) {
        ed_loaded(&ed, 0);
        return TRUE;
    }
    if (h < 0) {
        alert(ST_NOOPEN, 0);
        path[0] = 0;
        return FALSE;
    }
    graf_mouse(BUSYBEE, 0);
    n = Fread((WORD)h, ED_MAX + 1, ed.b);
    Fclose((WORD)h);
    graf_mouse(ARROW, 0);
    if (n > ED_MAX) {
        alert(ST_TOOBIG, (uint32_t)(ED_MAX / 1024));
        path[0] = 0;
        ed_loaded(&ed, 0);
        return FALSE;
    }
    if (n < 0) {
        alert(ST_NOOPEN, 0);
        path[0] = 0;
        ed_loaded(&ed, 0);
        return FALSE;
    }
    ed_loaded(&ed, (uint16_t)n);
    return TRUE;
}

/* The text written to `name`; FALSE if any of it was not. */
static WORD write_to(const char *name)
{
    uint16_t n1, n2;
    uint8_t FAR *p2;
    LONG h, a, b = 0;

    h = Fcreate(name, 0);
    if (h < 0)
        return FALSE;
    ed_span(&ed, &n1, &p2, &n2);
    a = n1 ? Fwrite((WORD)h, (LONG)n1, ed.b) : 0;
    if (a == (LONG)n1 && n2)
        b = Fwrite((WORD)h, (LONG)n2, p2);
    Fclose((WORD)h);
    return (WORD)(a == (LONG)n1 && b == (LONG)n2);
}

/* Save: written beside the file as EDIT.TMP, and only then put in its
 * place, so a full disk leaves the file as it was.  A DOS that cannot
 * rename (SpartaDOS X 4.49e, docs/edit.md) has the text written over the
 * file instead -- the copy in EDIT.TMP is already safe -- and the copy is
 * kept only if that fails too. */
static WORD save(void)
{
    char temp[PATHLEN];
    uint16_t k;
    const char FAR *t = str(ST_TEMP);

    dir_of(path, temp);
    k = slen(temp);
    while (*t && k < PATHLEN - 1)
        temp[k++] = *t++;
    temp[k] = 0;
    graf_mouse(BUSYBEE, 0);
    if (!write_to(temp)) {
        Fdelete(temp);
        graf_mouse(ARROW, 0);
        alert(ST_NOSAVE, 0);
        return FALSE;
    }
    Fdelete(path);
    if (Frename(temp, path) < 0) {
        if (!write_to(path)) {
            graf_mouse(ARROW, 0);
            alert(ST_INTEMP, 0);
            return FALSE;
        }
        Fdelete(temp);
    }
    graf_mouse(ARROW, 0);
    ed.dirty = 0;
    set_title();
    return TRUE;
}

/* Changed: ask.  TRUE when it is all right to let the text go. */
static WORD let_go(void)
{
    if (!ed.dirty || !path[0])
        return TRUE;
    switch (alert(ST_CHANGED, 0)) {
    case 1:  return save();
    case 2:  return TRUE;
    default: return FALSE;
    }
}

/* The file selector, in lastdir: the path chosen, or FALSE. */
static WORD fsel_ask(char *out)
{
    char p[PATHLEN], s[16];
    WORD button = 0;
    uint16_t k, j;

    scpy(p, lastdir, PATHLEN - 4);
    k = slen(p);
    p[k++] = '*';
    p[k++] = '.';
    p[k++] = '*';
    p[k] = 0;
    s[0] = 0;
    fsel_exinput(p, s, &button, str(ST_TOPEN));
    if (button != 1 || !s[0])
        return FALSE;
    dir_of(p, lastdir);
    scpy(out, lastdir, PATHLEN);
    k = slen(out);
    for (j = 0; s[j] && k < PATHLEN - 1; j++)
        out[k++] = s[j];
    out[k] = 0;
    return TRUE;
}

static void opened(void)
{
    set_title();
    set_info();
    set_slider();
    redraw_all();
}

static void do_open(void)
{
    char p[PATHLEN];

    if (!let_go() || !fsel_ask(p))
        return;
    load(p);
    opened();
}

/* -- keys --------------------------------------------------------------------- */

/* The cursor moved or the text changed: draw what that touched.  `row`
 * is the cursor's row before, `lines` the text's line count. */
static void touched(WORD row, uint16_t lines)
{
    WORD now;

    if (follow()) {
        set_slider();
        redraw_all();
    } else if (lines != ed.lines) {
        now = cur_row();
        if (row < 0 || (now >= 0 && now < row))
            row = now;
        if (row < 0)
            row = 0;
        set_slider();
        redraw_rows(row, rows, wx, wy, ww, whh);
    } else {
        now = cur_row();
        if (row >= 0)
            redraw_rows(row, (WORD)(row + 1), wx, wy, ww, whh);
        if (now >= 0 && now != row)
            redraw_rows(now, (WORD)(now + 1), wx, wy, ww, whh);
    }
    set_info();
}

static void typed(uint8_t c)
{
    WORD was = ed.dirty;

    if (!path[0])
        return;
    if (!ed_insert(&ed, cur, &c, 1)) {
        alert(ST_FULL, 0);
        return;
    }
    cur++;
    goal = ed_col(&ed, ed_bol(&ed, cur), cur);
    if (!was)
        set_title();
}

static void up(WORD n)
{
    while (n-- && ed_bol(&ed, cur) != 0) {
        cur = ed_up(&ed, cur, goal);
        curline--;
    }
}

static void down(WORD n)
{
    uint16_t q;

    while (n--) {
        q = ed_down(&ed, cur, goal);
        if (q == cur && !ed_eol_at(&ed, ed_eolpos(&ed, cur)))
            break;
        cur = q;
        curline++;
    }
}

static WORD do_menu(WORD title_obj, WORD item);

/* A key; TRUE to quit. */
static WORD do_key(WORD ks, WORD kr)
{
    WORD row = cur_row(), page = (WORD)((ks & (K_LSHIFT | K_RSHIFT)) != 0);
    WORD keep = FALSE, was = ed.dirty;
    uint16_t lines = ed.lines, c = (uint16_t)(kr & 0xFF), k;

    switch ((UWORD)kr) {
    case KEY_UP:
        up(page ? rows : 1);
        keep = TRUE;
        break;
    case KEY_DOWN:
        down(page ? rows : 1);
        keep = TRUE;
        break;
    case KEY_LEFT:
        if (page) {
            cur = ed_bol(&ed, cur);
        } else if (cur) {
            k = ed_eol_before(&ed, cur);
            if (k)
                curline--;
            cur = ed_left(&ed, cur);
        }
        break;
    case KEY_RIGHT:
        if (page) {
            cur = ed_eolpos(&ed, cur);
        } else {
            if (ed_eol_at(&ed, cur))
                curline++;
            cur = ed_right(&ed, cur);
        }
        break;
    case KEY_RET:
        if (!path[0])
            return FALSE;
        if (!ed_newline(&ed, cur)) {
            alert(ST_FULL, 0);
            return FALSE;
        }
        cur = ed_right(&ed, cur);
        curline++;
        break;
    case KEY_BS:
        if (!path[0] || !cur)
            return FALSE;
        if (ed_eol_before(&ed, cur))
            curline--;
        cur = ed_del_left(&ed, cur);
        break;
    case KEY_DEL:
        if (!path[0])
            return FALSE;
        cur = ed_del_right(&ed, cur);
        break;
    case KEY_TAB:
        typed((uint8_t)(ed.eol == ED_ATARI ? ATASCII_TAB : '\t'));
        break;
    case KEY_ESC:
        return do_menu(0, QUITITEM);
    default:
        if ((ks & K_CTRL) && c >= 1 && c <= 26) {
            switch (c + 'A' - 1) {
            case 'O': return do_menu(0, OPENITEM);
            case 'S': return do_menu(0, SAVEITEM);
            case 'Q': return do_menu(0, QUITITEM);
            default:  return FALSE;
            }
        }
        if (c < 0x20 || c == 0x7F)
            return FALSE;
        typed((uint8_t)c);
        break;
    }
    if (!keep)
        goal = ed_col(&ed, ed_bol(&ed, cur), cur);
    if (ed.dirty != was)
        set_title();
    touched(row, lines);
    return FALSE;
}

/* A click in the text: the cursor there. */
static void click(WORD mx, WORD my)
{
    WORD row = cur_row(), r;
    uint16_t lines = ed.lines, p, col;

    if (mx < wx || mx >= wx + ww || my < wy || my >= wy + whh)
        return;
    r = (WORD)((my - wy) / hchar);
    p = lines_down(top, (uint16_t)r);
    if (p == 0xFFFF)
        return;
    col = (uint16_t)(left + (mx - wx - MARGIN < 0 ? 0 : (mx - wx - MARGIN) / wchar));
    cur = ed_atcol(&ed, p, col);
    curline = (uint16_t)(topline + r);
    goal = ed_col(&ed, p, cur);
    touched(row, lines);
}

static void about(void)
{
    OBJECT *t;
    WORD x, y, w, h;

    rsrc_gaddr(R_TREE, ADABOUT, (void **)&t);
    form_center(t, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    objc_draw(t, 0, 8, x, y, w, h);
    form_do(t, 0);
    t[ABOK].ob_state = NORMAL;
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}

/* A menu item; TRUE to quit. */
static WORD do_menu(WORD title_obj, WORD item)
{
    WORD quit = FALSE;

    switch (item) {
    case ABOUITEM: about(); break;
    case OPENITEM: do_open(); break;
    case SAVEITEM: if (path[0]) save(); break;
    case QUITITEM: quit = let_go(); break;
    default: break;
    }
    if (title_obj)
        menu_tnormal(menu, title_obj, 1);
    return quit;
}

static void arrowed(WORD how)
{
    switch (how) {
    case WA_UPPAGE: view_from((long)topline - rows); break;
    case WA_DNPAGE: view_from((long)topline + rows); break;
    case WA_UPLINE: view_from((long)topline - 1); break;
    case WA_DNLINE: view_from((long)topline + 1); break;
    default: break;
    }
}

/* The window put at x y w h: x even, so a move is one blit (as the
 * desktop's do_xyfix keeps its own), and never over the menu bar. */
static void place(WORD x, WORD y, WORD w, WORD h, WORD dy)
{
    x = (WORD)((x + 1) & ~1);
    if (y < dy)
        y = dy;
    wind_set(wh, WF_CURRXYWH, x, y, w, h);
    work_area();
}

int main(void)
{
    char cmd[130], tail[132], p[PATHLEN];
    WORD wbox, hbox, dx, dy, dw, dh, a, b;
    WORD msgb[8], mx, my, mb, ks, kr, br, ev, done = FALSE, n;
    LONG m;

    cmd[0] = 0;
    tail[0] = 0;
    appl_init();
    shel_read(cmd, tail);
    if (!rsrc_load("EDIT.RSC")) {
        appl_exit();
        return 1;
    }
    m = Malloc((LONG)ED_CAP);
    if (m <= 0) {
        form_alert(1, str(ST_NOMEM));
        rsrc_free();
        appl_exit();
        return 1;
    }
    ed_init(&ed, (uint8_t FAR *)(uint32_t)m, ED_CAP);
    ed_loaded(&ed, 0);

    vh = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &vh, work_out);
    vst_alignment(vh, 0, 5, &a, &b);    /* text hangs from its top */
    glyphs_read();
    rsrc_gaddr(R_TREE, ADMENU, (void **)&menu);
    menu_bar(menu, 1);

    Dgetpath(lastdir + 2, 0);
    lastdir[0] = (char)('A' + Dgetdrv());
    lastdir[1] = ':';
    n = (WORD)slen(lastdir);
    if (n < 3 || lastdir[n - 1] != '\\') {
        lastdir[n++] = '\\';
        lastdir[n] = 0;
    }

    /* The file: handed over in the command tail -- from the desktop's
     * Show, a drop on EDIT.PRG, or a type installed for it -- or asked
     * for.  One that will not open ends EDIT, back where it came from. */
    p[0] = 0;
    n = (WORD)(uint8_t)tail[0];
    if (n > 0 && n < 128) {
        WORD i = 1, k = 0;
        while (i <= n && tail[i] == ' ')
            i++;
        while (i <= n && tail[i] && tail[i] != ' ' && tail[i] != '\r'
               && k < PATHLEN - 1)
            p[k++] = tail[i++];
        p[k] = 0;
    }
    if (!p[0] && !fsel_ask(p))
        done = TRUE;
    if (!done && !load(p))
        done = TRUE;
    if (!done) {
        dir_of(path, lastdir);
        wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
        wh = wind_create(NAME | INFO | CLOSER | MOVER | FULLER | SIZER
                         | UPARROW | DNARROW | VSLIDE, dx, dy, dw, dh);
        if (wh < 0) {
            done = TRUE;
        } else {
            set_title();
            wind_open(wh, dx, dy, dw, dh);
            work_area();
            set_info();
            set_slider();
        }
    }

    while (!done) {
        ev = evnt_multi_moblk(MU_MESAG | MU_KEYBD | MU_BUTTON, 1, 1, 1, 0, 0,
                              msgb, 0, 0, &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_MESAG) {
            switch (msgb[0]) {
            case MN_SELECTED:
                done = do_menu(msgb[3], msgb[4]);
                break;
            case WM_REDRAW:
                if (msgb[3] == wh)
                    redraw(msgb[4], msgb[5], msgb[6], msgb[7]);
                break;
            case WM_TOPPED:
                if (msgb[3] == wh)
                    wind_set(wh, WF_TOP, 0, 0, 0, 0);
                break;
            case WM_CLOSED:
                if (msgb[3] == wh)
                    done = let_go();
                break;
            case WM_MOVED:
            case WM_SIZED:
                if (msgb[3] == wh) {
                    WORD was = rows, wasc = cols;
                    place(msgb[4], msgb[5], msgb[6], msgb[7], dy);
                    if (follow() || rows != was || cols != wasc)
                        redraw_all();
                    set_slider();
                }
                break;
            case WM_FULLED:
                if (msgb[3] == wh) {
                    WORD cx, cy, cw, ch;
                    wind_get(wh, WF_CURRXYWH, &cx, &cy, &cw, &ch);
                    if (cx == dx && cy == dy && cw == dw && ch == dh)
                        wind_get(wh, WF_PREVXYWH, &cx, &cy, &cw, &ch);
                    else
                        cx = dx, cy = dy, cw = dw, ch = dh;
                    place(cx, cy, cw, ch, dy);
                    follow();
                    set_slider();
                    redraw_all();
                }
                break;
            case WM_ARROWED:
                if (msgb[3] == wh)
                    arrowed(msgb[4]);
                break;
            case WM_VSLID:
                if (msgb[3] == wh && ed.lines > (uint16_t)rows)
                    view_from((long)msgb[4] * (long)(ed.lines - rows) / 1000L);
                break;
            default:
                break;
            }
        }
        if ((ev & MU_KEYBD) && !done)
            done = do_key(ks, kr);
        if ((ev & MU_BUTTON) && !done && wind_find(mx, my) == wh)
            click(mx, my);
    }
    if (wh >= 0) {
        wind_close(wh);
        wind_delete(wh);
    }
    menu_bar(menu, 0);
    v_clsvwk(vh);
    rsrc_free();
    appl_exit();
    return 0;
}
