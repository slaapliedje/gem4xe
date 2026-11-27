/* MINES: the mine game, in a window on the desktop.
 *
 * The field and its rules are src/apps/minefld.c, which
 * tests/host/test_mines.py runs on the host against a model of its own;
 * this file is the GEM program round it -- the window, the menu, the
 * clicks and the drawing.  Every word a player reads is in MINES.RSC
 * (tools/minesrsc.py).
 *
 * A click opens a square, and a click on an open number whose flags are
 * all up opens the rest round it.  The right button, or Shift with the
 * one a trak-ball or a joystick has, puts a flag up or takes it down.
 * The first square opened is never a mine (minefld.c lays the mines
 * then).  The window is the field's size, so it has a closer and a mover
 * and nothing that would change that; the three sizes are on the Game
 * menu, and one that the screen cannot hold is greyed there.
 *
 * DRAWN TO SUIT THE SCREEN.  A square is a character cell and a pixel
 * either way, so the field is as legible as the system's own text: 8x8
 * on ANTIC's 6x6 face, larger on the VBXE, and wider than it is tall
 * where the pixels are tall (the workstation says how tall, in
 * microns).  With sixteen colours the squares are raised grey tiles and
 * each number has its colour; with two, a closed square is a light
 * dither and an open one white, and the numbers are black.
 */
#include "gem.h"
#include "time.h"
#include "minefld.h"
#include "minesrsc.h"

#define KIND      (NAME | INFO | CLOSER | MOVER)
#define EDGE      3                     /* pixels round the field */
#define LEVELS    3
#define TICK_MS   250                   /* the clock's look, while it runs */
#define CTRL_N    0x0E
#define CTRL_Q    0x11

static const uint8_t  lv_w[LEVELS] = { 9, 16, 30 };
static const uint8_t  lv_h[LEVELS] = { 9, 16, 16 };
static const uint16_t lv_m[LEVELS] = { 10, 40, 99 };
static const WORD     lv_item[LEVELS] = { BEGITEM, INTITEM, EXPITEM };

/* The colour of each number with sixteen pens: the VDI's own palette
 * (gem.h), blue for one round to dark grey for eight. */
static const WORD num_pen[9] = { 1, 4, 11, 2, 12, 10, 13, 1, 9 };

/* Globals, not statics, where a gate reads them by name
 * (tests/emu/mines.py): the field's corner, a square's size, the window,
 * the menu tree, the level and whether there is colour. */
WORD fx, fy, cw, chh;
WORD level, wh = -1, colour;
OBJECT *menu;
static WORD vh, wchar, hchar;
static WORD wx, wy, ww, whh;            /* the window's work area */
static WORD dx, dy, dw, dh;             /* the desk's */
static clock_t t0;
WORD secs;                              /* the time shown */
static char info[64], msg[160];

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];

/* -- words ------------------------------------------------------------------ */

static char *str(WORD i)
{
    char *s = 0;

    rsrc_gaddr(R_STRING, i, (void **)&s);
    return s;
}

/* A resource string with each '#' the next of nums, signed. */
static void fill(char *d, uint16_t max, WORD which, const LONG *nums)
{
    const char *s = str(which);
    uint16_t k = 0, n;
    char c, t[12];

    while ((c = *s++) != 0 && k < max - 13) {
        if (c != '#') {
            d[k++] = c;
            continue;
        }
        {
            LONG v = *nums++;
            uint32_t u;

            if (v < 0) {
                d[k++] = '-';
                u = (uint32_t)(-v);
            } else {
                u = (uint32_t)v;
            }
            n = 0;
            do {
                t[n++] = (char)('0' + (uint16_t)(u % 10));
                u /= 10;
            } while (u);
            while (n)
                d[k++] = t[--n];
        }
    }
    d[k] = 0;
}

static void set_info(void)
{
    LONG n[2];

    n[0] = (LONG)mf_mines - (LONG)mf_flags;
    n[1] = secs;
    fill(info, sizeof info, ST_INFO, n);
    wind_set_str(wh, WF_INFO, info);
}

/* -- geometry --------------------------------------------------------------- */

/* A square's size: a character cell and a pixel each way, made wider
 * where a pixel is taller than it is wide, so the squares look square. */
static void square_size(void)
{
    cw = (WORD)(wchar + 2);
    chh = (WORD)(hchar + 2);
    if (work_out[3] > 0 && work_out[4] > work_out[3]) {
        LONG sq = (LONG)chh * work_out[4] / work_out[3];

        if (sq > cw && sq < 3L * chh)
            cw = (WORD)sq;
    }
}

/* The information line at its longest -- three digits each, and a sign
 * -- in pixels: the window is never narrower, or the small field would
 * cut the time off (the field sits in the middle of a wider one). */
static WORD info_w;

static void measure_info(void)
{
    LONG n[2];
    uint16_t k = 0;

    n[0] = -999;
    n[1] = 999;
    fill(msg, sizeof msg, ST_INFO, n);
    while (msg[k])
        k++;
    info_w = (WORD)((k + 2) * wchar);
}

static WORD field_w(WORD lv)
{
    WORD fw = (WORD)(lv_w[lv] * cw + 2 * EDGE);

    if (fw < info_w)
        fw = info_w;
    return fw;
}

static WORD field_h(WORD lv) { return (WORD)(lv_h[lv] * chh + 2 * EDGE); }

static void outer(WORD lv, WORD *ow, WORD *oh)
{
    WORD x, y;

    wind_calc(WC_BORDER, KIND, 0, 0, field_w(lv), field_h(lv), &x, &y, ow, oh);
}

static WORD fits(WORD lv)
{
    WORD ow, oh;

    outer(lv, &ow, &oh);
    return (WORD)(ow <= dw && oh <= dh);
}

static void work_area(void)
{
    WORD w;

    wind_get(wh, WF_WORKXYWH, &wx, &wy, &ww, &whh);
    w = (WORD)(mf_w * cw);
    fx = (WORD)(wx + EDGE);
    if (ww > w + 2 * EDGE)
        fx = (WORD)(wx + (UWORD)(ww - w) / 2);
    fy = (WORD)(wy + EDGE);
}

/* -- drawing ---------------------------------------------------------------- */

static void box(WORD x, WORD y, WORD w, WORD h, WORD pen, WORD style)
{
    WORD p[4];

    vsf_color(vh, pen);
    if (style) {
        vsf_interior(vh, FIS_PATTERN);
        vsf_style(vh, style);
    } else {
        vsf_interior(vh, FIS_SOLID);
    }
    p[0] = x;
    p[1] = y;
    p[2] = (WORD)(x + w - 1);
    p[3] = (WORD)(y + h - 1);
    vr_recfl(vh, p);
}

static void line(WORD x0, WORD y0, WORD x1, WORD y1, WORD pen)
{
    WORD p[4];

    vsl_color(vh, pen);
    p[0] = x0;
    p[1] = y0;
    p[2] = x1;
    p[3] = y1;
    v_pline(vh, 2, p);
}

/* A flag on its pole, in the square at x y. */
static void flag(WORD x, WORD y)
{
    WORD p[6], px = (WORD)(x + (UWORD)cw / 2), top = (WORD)(y + 2);
    WORD foot = (WORD)(y + chh - 3), mid = (WORD)(y + (UWORD)chh / 2);
    WORD pen = G_BLACK;

    if (colour)
        pen = G_RED;
    vsf_color(vh, pen);
    vsf_interior(vh, FIS_SOLID);
    p[0] = px;
    p[1] = top;
    p[2] = px;
    p[3] = mid;
    p[4] = (WORD)(x + 2);
    p[5] = (WORD)(top + (UWORD)(mid - top) / 2);
    v_fillarea(vh, 3, p);
    line(px, top, px, foot, G_BLACK);
    line((WORD)(px - 2), foot, (WORD)(px + 2), foot, G_BLACK);
}

/* A mine: a disc and its spikes, in pen. */
static void mine(WORD x, WORD y, WORD pen)
{
    WORD cx = (WORD)(x + (UWORD)cw / 2), cy = (WORD)(y + (UWORD)chh / 2);
    WORD r = (WORD)((UWORD)((cw < chh ? cw : chh) - 4) / 2);

    if (r < 1)
        r = 1;
    vsf_color(vh, pen);
    vsf_interior(vh, FIS_SOLID);
    v_circle(vh, cx, cy, r);
    line((WORD)(cx - r - 1), cy, (WORD)(cx + r + 1), cy, pen);
    line(cx, (WORD)(cy - r - 1), cx, (WORD)(cy + r + 1), pen);
}

/* A flag that was wrong, at the end: crossed out. */
static void crossed(WORD x, WORD y)
{
    WORD pen = G_BLACK;

    if (colour)
        pen = G_RED;
    line((WORD)(x + 1), (WORD)(y + 1), (WORD)(x + cw - 2), (WORD)(y + chh - 2), pen);
    line((WORD)(x + cw - 2), (WORD)(y + 1), (WORD)(x + 1), (WORD)(y + chh - 2), pen);
}

/* Square i, as it is now. */
static void square(uint16_t i)
{
    uint8_t v = mf_cell[i];
    WORD x = (WORD)(fx + (WORD)(i % mf_w) * cw);
    WORD y = (WORD)(fy + (WORD)(i / mf_w) * chh);
    WORD x1 = (WORD)(x + cw - 1), y1 = (WORD)(y + chh - 1);
    WORD n = (WORD)(v & MF_COUNT), boom = (WORD)(i == mf_boom);

    if (!(v & MF_OPEN)) {
        if (colour) {
            box(x, y, cw, chh, G_LWHITE, 0);
            line(x, y, x1, y, G_WHITE);
            line(x, y, x, y1, G_WHITE);
            line(x1, y, x1, y1, G_LBLACK);
            line(x, y1, x1, y1, G_LBLACK);
        } else {
            box(x, y, cw, chh, G_WHITE, 0);
            box((WORD)(x + 1), (WORD)(y + 1), (WORD)(cw - 2), (WORD)(chh - 2), G_BLACK, 2);
            line(x1, y, x1, y1, G_BLACK);
            line(x, y1, x1, y1, G_BLACK);
        }
        if (v & MF_FLAG) {
            flag(x, y);
            if (mf_state == MF_LOST && !(v & MF_MINE))
                crossed(x, y);
        }
        return;
    }
    if (colour) {
        WORD pen = G_LWHITE;

        if (boom)
            pen = G_RED;
        box(x, y, cw, chh, pen, 0);
        line(x, y, x1, y, G_LBLACK);
        line(x, y, x, y1, G_LBLACK);
    } else {
        WORD pen = G_WHITE;

        if (boom)
            pen = G_BLACK;
        box(x, y, cw, chh, pen, 0);
        line(x, y, x1, y, G_BLACK);
        line(x, y, x, y1, G_BLACK);
    }
    if (v & MF_MINE) {
        WORD pen = G_BLACK;

        if (boom && !colour)
            pen = G_WHITE;
        mine(x, y, pen);
        return;
    }
    if (n) {
        char s[2];
        WORD pen = G_BLACK;

        if (colour)
            pen = num_pen[n];
        s[0] = (char)('0' + n);
        s[1] = 0;
        vst_color(vh, pen);
        v_gtext(vh, (WORD)(x + (UWORD)(cw - wchar) / 2),
                (WORD)(y + (UWORD)(chh - hchar) / 2), s);
    }
}

/* The ground round the field, and the line that sinks it. */
static void ground(void)
{
    WORD pen = G_WHITE, edge = G_BLACK;
    WORD w = (WORD)(mf_w * cw), h = (WORD)(mf_h * chh);

    if (colour) {
        pen = G_LWHITE;
        edge = G_LBLACK;
    }
    box(wx, wy, ww, (WORD)(fy - wy), pen, 0);
    box(wx, (WORD)(fy + h), ww, (WORD)(wy + whh - fy - h), pen, 0);
    box(wx, fy, (WORD)(fx - wx), h, pen, 0);
    box((WORD)(fx + w), fy, (WORD)(wx + ww - fx - w), h, pen, 0);
    line((WORD)(fx - 1), (WORD)(fy - 1), (WORD)(fx + w), (WORD)(fy - 1), edge);
    line((WORD)(fx - 1), (WORD)(fy - 1), (WORD)(fx - 1), (WORD)(fy + h), edge);
}

/* What lies in x y w h, through the window's rectangle list: the ground
 * if asked, and every square that meets it -- or, with only the dirty
 * list, those alone. */
static void paint(WORD x, WORD y, WORD w, WORD h, WORD all)
{
    WORD rx, ry, rw, rh, p[4];

    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    vswr_mode(vh, MD_TRANS);
    vsf_perimeter(vh, 0);
    vsl_width(vh, 1);
    wind_get(wh, WF_FIRSTXYWH, &rx, &ry, &rw, &rh);
    while (rw && rh) {
        WORD ax = rx > x ? rx : x, ay = ry > y ? ry : y;
        WORD bx = (rx + rw < x + w) ? rx + rw : x + w;
        WORD by = (ry + rh < y + h) ? ry + rh : y + h;

        if (bx > ax && by > ay) {
            p[0] = ax;
            p[1] = ay;
            p[2] = (WORD)(bx - 1);
            p[3] = (WORD)(by - 1);
            vs_clip(vh, 1, p);
            if (all) {
                WORD c0 = 0, r0 = 0, c1, r1, c, r;

                ground();
                if (ax > fx)
                    c0 = (WORD)((UWORD)(ax - fx) / (UWORD)cw);
                if (ay > fy)
                    r0 = (WORD)((UWORD)(ay - fy) / (UWORD)chh);
                c1 = mf_w;
                r1 = mf_h;
                if (bx < fx + mf_w * cw)
                    c1 = (WORD)((UWORD)(bx - fx + cw - 1) / (UWORD)cw);
                if (by < fy + mf_h * chh)
                    r1 = (WORD)((UWORD)(by - fy + chh - 1) / (UWORD)chh);
                for (r = r0; r < r1; r++)
                    for (c = c0; c < c1; c++)
                        square((uint16_t)((uint16_t)r * mf_w + (uint16_t)c));
            } else {
                uint16_t k;

                for (k = 0; k < mf_ndirty; k++)
                    square(mf_dirty[k]);
            }
        }
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    vs_clip(vh, 0, p);
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

static void paint_all(void)
{
    paint(wx, wy, ww, whh, TRUE);
}

/* The squares the last move changed, inside the box they make. */
static void paint_dirty(void)
{
    WORD c0 = 32767, r0 = 32767, c1 = 0, r1 = 0;
    uint16_t k;

    if (!mf_ndirty)
        return;
    for (k = 0; k < mf_ndirty; k++) {
        uint16_t i = mf_dirty[k];
        WORD c = (WORD)(i % mf_w), r = (WORD)(i / mf_w);

        if (c < c0)
            c0 = c;
        if (r < r0)
            r0 = r;
        if (c >= c1)
            c1 = (WORD)(c + 1);
        if (r >= r1)
            r1 = (WORD)(r + 1);
    }
    paint((WORD)(fx + c0 * cw), (WORD)(fy + r0 * chh), (WORD)((c1 - c0) * cw),
          (WORD)((r1 - r0) * chh), FALSE);
}

/* -- the game --------------------------------------------------------------- */

static void new_game(void)
{
    mf_new(lv_w[level], lv_h[level], lv_m[level]);
    secs = 0;
    if (wh < 0)
        return;
    set_info();
    paint_all();
}

/* The size changed: the window to suit, where it was if the desk lets it. */
static void new_level(WORD lv)
{
    WORD x, y, w, h, ow, oh;

    if (lv == level || !fits(lv))
        return;
    menu_icheck(menu, lv_item[level], 0);
    level = lv;
    menu_icheck(menu, lv_item[level], 1);
    mf_new(lv_w[level], lv_h[level], lv_m[level]);
    secs = 0;
    outer(lv, &ow, &oh);
    wind_get(wh, WF_CURRXYWH, &x, &y, &w, &h);
    if (x + ow > dx + dw)
        x = (WORD)(dx + dw - ow);
    if (y + oh > dy + dh)
        y = (WORD)(dy + dh - oh);
    if (x < dx)
        x = dx;
    if (y < dy)
        y = dy;
    x = (WORD)(x & ~1);
    wind_set(wh, WF_CURRXYWH, x, y, ow, oh);
    work_area();
    set_info();
    paint_all();
}

static void tick(void)
{
    clock_t now;
    LONG s;

    if (mf_state != MF_PLAYING)
        return;
    now = clock();
    s = (LONG)((now - t0) / CLOCKS_PER_SEC);
    if (s > 999)
        s = 999;
    if ((WORD)s != secs) {
        secs = (WORD)s;
        set_info();
    }
}

/* The end of a game: what the player is told, and a new one if asked. */
static void ended(void)
{
    LONG n[1];
    WORD b;

    if (mf_state == MF_WON) {
        n[0] = secs;
        fill(msg, sizeof msg, ST_WON, n);
        b = form_alert(1, msg);
    } else if (mf_state == MF_LOST) {
        b = form_alert(1, str(ST_LOST));
    } else {
        return;
    }
    if (b == 1)
        new_game();
}

static WORD on_top(void)
{
    WORD t, d;

    wind_get(wh, WF_TOP, &t, &d, &d, &d);
    return (WORD)(t == wh);
}

/* A click at mx my with the buttons mb and the shift keys ks. */
static void click(WORD mx, WORD my, WORD mb, WORD ks)
{
    WORD c, r, was = mf_state;
    uint8_t v;

    if (mx < fx || my < fy || mx >= fx + mf_w * cw || my >= fy + mf_h * chh)
        return;
    c = (WORD)((UWORD)(mx - fx) / (UWORD)cw);
    r = (WORD)((UWORD)(my - fy) / (UWORD)chh);
    v = mf_cell[(uint16_t)r * mf_w + (uint16_t)c];
    if ((mb & 2) || (ks & (K_LSHIFT | K_RSHIFT)))
        mf_flag((uint8_t)c, (uint8_t)r);
    else if (v & MF_OPEN)
        mf_chord((uint8_t)c, (uint8_t)r);
    else
        mf_open((uint8_t)c, (uint8_t)r);
    if (was == MF_FRESH && mf_state != MF_FRESH)
        t0 = clock();
    paint_dirty();
    tick();
    set_info();
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
    WORD quit = FALSE, lv;

    switch (item) {
    case ABOUITEM:
        about();
        break;
    case NEWITEM:
        new_game();
        break;
    case QUITITEM:
        quit = TRUE;
        break;
    default:
        for (lv = 0; lv < LEVELS; lv++)
            if (item == lv_item[lv])
                new_level(lv);
        break;
    }
    if (title_obj)
        menu_tnormal(menu, title_obj, 1);
    return quit;
}

int main(void)
{
    WORD wbox, hbox, a, b, lv, ow, oh, x, y;
    WORD msgb[8], mx, my, mb, ks, kr, br, ev, done = FALSE;
    uint32_t seed;

    appl_init();
    shel_write(SWM_NEWMSG, NM_APTERM, 0, 0, 0);    /* AP_TERM: below */
    if (!rsrc_load("MINES.RSC")) {
        appl_exit();
        return 1;
    }
    vh = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &vh, work_out);
    colour = (WORD)(work_out[13] >= 16);
    vst_alignment(vh, 0, 5, &a, &b);    /* text hangs from its top */
    rsrc_gaddr(R_TREE, ADMENU, (void **)&menu);
    wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
    square_size();
    measure_info();

    /* the sizes the screen cannot hold, greyed; the first it can, chosen */
    level = -1;
    for (lv = 0; lv < LEVELS; lv++) {
        if (!fits(lv))
            menu_ienable(menu, lv_item[lv], 0);
        else if (level < 0)
            level = lv;
    }
    if (level < 0) {                    /* not even the smallest */
        v_clsvwk(vh);
        rsrc_free();
        appl_exit();
        return 1;
    }
    menu_icheck(menu, lv_item[level], 1);
    menu_bar(menu, 1);

    seed = (uint32_t)clock() ^ ((uint32_t)(UWORD)Tgettime() << 16)
           ^ (uint32_t)(UWORD)Tgetdate();
    mf_seed(seed);
    mf_new(lv_w[level], lv_h[level], lv_m[level]);

    outer(level, &ow, &oh);
    x = (WORD)((dx + (UWORD)(dw - ow) / 2) & ~1);
    y = (WORD)(dy + (UWORD)(dh - oh) / 2);
    wh = wind_create(KIND, dx, dy, dw, dh);
    if (wh < 0) {
        done = TRUE;
    } else {
        wind_set_str(wh, WF_NAME, str(ST_TITLE));
        set_info();
        wind_open(wh, x, y, ow, oh);
        work_area();
    }

    while (!done) {
        UWORD flags = MU_MESAG | MU_KEYBD | MU_BUTTON;

        if (mf_state == MF_PLAYING)
            flags |= MU_TIMER;
        /* 0x101: the clicks' high byte asks to LEAVE the state -- all
         * buttons up -- so either button wakes it (src/aes/event.c) */
        ev = evnt_multi_moblk(flags, 0x101, 3, 0, 0, 0, msgb, TICK_MS, 0,
                              &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_MESAG) {
            switch (msgb[0]) {
            case MN_SELECTED:
                done = do_menu(msgb[3], msgb[4]);
                break;
            case WM_REDRAW:
                if (msgb[3] == wh)
                    paint(msgb[4], msgb[5], msgb[6], msgb[7], TRUE);
                break;
            case WM_TOPPED:
                if (msgb[3] == wh)
                    wind_set(wh, WF_TOP, 0, 0, 0, 0);
                break;
            case WM_CLOSED:
            case AP_TERM:
                done = TRUE;
                break;
            case WM_MOVED:
                if (msgb[3] == wh) {
                    WORD nx = (WORD)(msgb[4] & ~1), ny = msgb[5];

                    if (ny < dy)
                        ny = dy;
                    wind_set(wh, WF_CURRXYWH, nx, ny, msgb[6], msgb[7]);
                    work_area();
                }
                break;
            default:
                break;
            }
        }
        if ((ev & MU_KEYBD) && !done) {
            WORD c = (WORD)(kr & 0xFF);

            if (c == CTRL_N)
                new_game();
            else if (c == CTRL_Q)
                done = TRUE;
        }
        if ((ev & MU_BUTTON) && !done) {
            if (wind_find(mx, my) == wh && on_top()) {
                click(mx, my, mb, ks);
                evnt_button(1, 3, 0, &mx, &my, &mb, &ks);   /* let go first */
                ended();
            } else {
                evnt_button(1, 3, 0, &mx, &my, &mb, &ks);
            }
        }
        if ((ev & MU_TIMER) && !done)
            tick();
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
