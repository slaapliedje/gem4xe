/* g4bench.c -- G4BENCH: what drawing, text, blits, the AES and the CPU
 * cost on this machine, measured by an ordinary GEM program.
 *
 * GEMBench's idea, gem4xe's tests (docs/roadmap-0.9.md).  The numbers it
 * gives are the ones a program sees, through the same calls and the same
 * AES a program uses -- not the test runner's, which calls the VDI from
 * inside the system (tests/emu/bench_gem.py).  So it runs as it is on
 * real hardware, and a result from a real machine can be set beside one
 * from the emulator.
 *
 * It opens one window, uses the window's work area as its canvas, and
 * runs each test a fixed number of times, timed by Tgettimeofday -- the
 * system's ~4 kHz timer, exact to a quarter of a millisecond.  Then it
 * lists the results in the window and writes them to G4BENCH.TXT beside
 * itself.  Every test is sized to the canvas, so the same program runs on
 * the VBXE's 640 pixels and the ANTIC screen's 320.
 *
 * FOR THE GATE: g4b_done and g4b_us[] are what tests/emu/g4bench.py reads
 * by symbol, the way test-m22 reads the clock's seconds -- the program is
 * the same one a person runs, with no mode of its own for being tested.
 */
#include "gem.h"

#define NTESTS 18

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];
static WORD ext_out[57];

static WORD vh;                     /* our workstation */
static WORD wh;                     /* our window */
static WORD cx, cy, cw, ch;         /* the canvas: the window's work area */
static WORD ncol;                   /* pens the screen has */
static WORD planes;

/* READ BY THE GATE: 1 once every result is in, and each test's time in
 * microseconds, in the table's order. */
WORD g4b_done;
LONG g4b_us[NTESTS];

static char title[] = " G4BENCH ";

/* ---- timing ------------------------------------------------------------ */

static struct timeval t0;

static void start(void)
{
    Tgettimeofday((struct timeval FAR *)&t0, 0);
}

static LONG stop(void)
{
    struct timeval t1;

    Tgettimeofday((struct timeval FAR *)&t1, 0);
    return (t1.tv_sec - t0.tv_sec) * 1000000L + (t1.tv_usec - t0.tv_usec);
}

/* ---- the canvas -------------------------------------------------------- */

static void canvas_clip(void)
{
    WORD pxy[4];

    pxy[0] = cx;
    pxy[1] = cy;
    pxy[2] = (WORD)(cx + cw - 1);
    pxy[3] = (WORD)(cy + ch - 1);
    vs_clip(vh, 1, pxy);
}

static void canvas_clear(void)
{
    WORD pxy[4];

    vswr_mode(vh, MD_REPLACE);
    vsf_interior(vh, FIS_SOLID);
    vsf_color(vh, 0);
    pxy[0] = cx;
    pxy[1] = cy;
    pxy[2] = (WORD)(cx + cw - 1);
    pxy[3] = (WORD)(cy + ch - 1);
    vr_recfl(vh, pxy);
}

static WORD pen(WORD i)             /* a pen that is not the background */
{
    return (WORD)(ncol > 2 ? 1 + i % (ncol - 1) : 1);
}

static WORD min(WORD a, WORD b)
{
    return a < b ? a : b;
}

/* ---- graphics ------------------------------------------------------------ */

static void t_hlines(WORD n)
{
    WORD i, pxy[4];

    for (i = 0; i < n; i++) {
        vsl_color(vh, pen(i));
        pxy[0] = (WORD)(cx + 4);
        pxy[2] = (WORD)(cx + cw - 5);
        pxy[1] = pxy[3] = (WORD)(cy + 2 + i % (ch - 4));
        v_pline(vh, 2, pxy);
    }
}

static void t_vlines(WORD n)
{
    WORD i, pxy[4];

    for (i = 0; i < n; i++) {
        vsl_color(vh, pen(i));
        pxy[1] = (WORD)(cy + 2);
        pxy[3] = (WORD)(cy + ch - 3);
        pxy[0] = pxy[2] = (WORD)(cx + 2 + i % (cw - 4));
        v_pline(vh, 2, pxy);
    }
}

static void t_dlines(WORD n)
{
    WORD i, pxy[4], s = min((WORD)(cw - 8), (WORD)(ch - 8));

    for (i = 0; i < n; i++) {
        vsl_color(vh, pen(i));
        pxy[0] = (WORD)(cx + 4 + i % 16);
        pxy[1] = (WORD)(cy + 4);
        pxy[2] = (WORD)(pxy[0] + s - 16);
        pxy[3] = (WORD)(cy + 4 + s - 1);
        v_pline(vh, 2, pxy);
    }
}

static void boxes(WORD n, WORD interior)
{
    WORD i, pxy[4], w = min(100, (WORD)(cw / 2)), h = min(50, (WORD)(ch / 2));

    vsf_interior(vh, interior);
    vsf_style(vh, 4);
    for (i = 0; i < n; i++) {
        vsf_color(vh, pen(i));
        pxy[0] = (WORD)(cx + (i * 7) % (cw - w));
        pxy[1] = (WORD)(cy + (i * 5) % (ch - h));
        pxy[2] = (WORD)(pxy[0] + w - 1);
        pxy[3] = (WORD)(pxy[1] + h - 1);
        vr_recfl(vh, pxy);
    }
}

static void t_solid(WORD n)   { boxes(n, FIS_SOLID); }
static void t_pattern(WORD n) { boxes(n, FIS_PATTERN); }

static void t_circles(WORD n)
{
    WORD i, r = min(40, (WORD)(ch / 3));

    vsf_interior(vh, FIS_SOLID);
    for (i = 0; i < n; i++) {
        vsf_color(vh, pen(i));
        v_circle(vh, (WORD)(cx + r + (i * 13) % (cw - 2 * r)),
                 (WORD)(cy + r + (i * 7) % (ch - 2 * r)), r);
    }
}

static void t_ellipses(WORD n)
{
    WORD i, rx = min(60, (WORD)(cw / 4)), ry = min(30, (WORD)(ch / 4));

    vsf_interior(vh, FIS_SOLID);
    for (i = 0; i < n; i++) {
        vsf_color(vh, pen(i));
        v_ellipse(vh, (WORD)(cx + rx + (i * 11) % (cw - 2 * rx)),
                  (WORD)(cy + ry + (i * 5) % (ch - 2 * ry)), rx, ry);
    }
}

static void t_polygons(WORD n)
{
    WORD i, k, pxy[12], s = min(60, (WORD)(ch / 2));
    static const WORD hexagon[12] = { 2, 0, 4, 0, 6, 2, 4, 4, 2, 4, 0, 2 };

    vsf_interior(vh, FIS_SOLID);
    for (i = 0; i < n; i++) {
        WORD ox = (WORD)(cx + (i * 17) % (cw - s)), oy = (WORD)(cy + (i * 9) % (ch - s));

        vsf_color(vh, pen(i));
        for (k = 0; k < 12; k += 2) {
            pxy[k] = (WORD)(ox + hexagon[k] * s / 6);
            pxy[k + 1] = (WORD)(oy + hexagon[k + 1] * s / 4);
        }
        v_fillarea(vh, 6, pxy);
    }
}

static void t_rboxes(WORD n)
{
    WORD i, pxy[4], w = min(80, (WORD)(cw / 3)), h = min(40, (WORD)(ch / 3));

    vsf_interior(vh, FIS_SOLID);
    for (i = 0; i < n; i++) {
        vsf_color(vh, pen(i));
        pxy[0] = (WORD)(cx + (i * 11) % (cw - w));
        pxy[1] = (WORD)(cy + (i * 7) % (ch - h));
        pxy[2] = (WORD)(pxy[0] + w - 1);
        pxy[3] = (WORD)(pxy[1] + h - 1);
        v_rfbox(vh, pxy);
    }
}

/* ---- text ---------------------------------------------------------------- */

static const char line40[] = "The quick brown fox jumps over the lazy";

static void text(WORD n, WORD effects, WORD heights)
{
    WORD i, cwd, cht, bw, bh, hstep = 0, y;
    static const WORD hs[4] = { 4, 6, 8, 13 };

    vswr_mode(vh, MD_TRANS);
    vst_effects(vh, effects);
    vst_height(vh, 6, &cwd, &cht, &bw, &bh);
    y = (WORD)(cy + bh);
    for (i = 0; i < n; i++) {
        if (heights) {
            vst_height(vh, hs[hstep], &cwd, &cht, &bw, &bh);
            hstep = (WORD)((hstep + 1) & 3);
        }
        vst_color(vh, pen(i));
        v_gtext(vh, (WORD)(cx + 2), y, line40);
        y = (WORD)(y + bh);
        if (y > cy + ch - 1)
            y = (WORD)(cy + bh);
    }
    vst_effects(vh, 0);
    vswr_mode(vh, MD_REPLACE);
}

static void t_text(WORD n)    { text(n, 0, 0); }
static void t_effects(WORD n) { text(n, 1 | 8, 0); }   /* bold, underlined */
static void t_heights(WORD n) { text(n, 0, 1); }

/* ---- blits --------------------------------------------------------------- */

#define FORM_W 64
#define FORM_H 32
/* 4 planes is the most either screen has; a form must be in bank $00,
 * which a static is. */
static uint8_t form_bits[FORM_W / 8 * FORM_H * 4];

static void t_copy(WORD n)
{
    MFDB scr;
    WORD i, pxy[8], w = min(96, (WORD)(cw / 3)), h = min(48, (WORD)(ch / 3));

    scr.fd_addr = 0;
    for (i = 0; i < n; i++) {
        pxy[0] = cx;
        pxy[1] = cy;
        pxy[2] = (WORD)(cx + w - 1);
        pxy[3] = (WORD)(cy + h - 1);
        pxy[4] = (WORD)(cx + w + (i * 6) % (cw - 2 * w));
        pxy[5] = (WORD)(cy + h + (i * 3) % (ch - 2 * h));
        pxy[6] = (WORD)(pxy[4] + w - 1);
        pxy[7] = (WORD)(pxy[5] + h - 1);
        vro_cpyfm(vh, S_ONLY, pxy, &scr, &scr);
    }
}

static void t_memcopy(WORD n)
{
    MFDB scr, mem;
    WORD i, pxy[8];

    scr.fd_addr = 0;
    mem.fd_addr = (uint32_t)form_bits;
    mem.fd_w = FORM_W;
    mem.fd_h = FORM_H;
    mem.fd_wdwidth = FORM_W / 16;
    mem.fd_stand = 0;
    mem.fd_nplanes = planes;
    mem.fd_r1 = mem.fd_r2 = mem.fd_r3 = 0;
    for (i = 0; i < n; i++) {
        pxy[0] = cx;                            /* out to memory... */
        pxy[1] = cy;
        pxy[2] = (WORD)(cx + FORM_W - 1);
        pxy[3] = (WORD)(cy + FORM_H - 1);
        pxy[4] = 0;
        pxy[5] = 0;
        pxy[6] = FORM_W - 1;
        pxy[7] = FORM_H - 1;
        vro_cpyfm(vh, S_ONLY, pxy, &scr, &mem);
        pxy[0] = 0;                             /* ...and back elsewhere */
        pxy[1] = 0;
        pxy[2] = FORM_W - 1;
        pxy[3] = FORM_H - 1;
        pxy[4] = (WORD)(cx + FORM_W + (i * 8) % (cw - 2 * FORM_W));
        pxy[5] = (WORD)(cy + FORM_H + (i * 4) % (ch - 2 * FORM_H));
        pxy[6] = (WORD)(pxy[4] + FORM_W - 1);
        pxy[7] = (WORD)(pxy[5] + FORM_H - 1);
        vro_cpyfm(vh, S_ONLY, pxy, &mem, &scr);
    }
}

/* A 32x32 one-plane icon: a ring. */
static uint16_t icon_bits[64];

static void make_icon(void)
{
    WORD y, x;

    for (y = 0; y < 32; y++) {
        uint32_t row = 0;

        for (x = 0; x < 32; x++) {
            WORD dx = (WORD)(x - 16), dy = (WORD)(y - 16), d = (WORD)(dx * dx + dy * dy);

            if (d < 225 && d > 100)
                row |= 0x80000000UL >> x;
        }
        icon_bits[y * 2] = (uint16_t)(row >> 16);
        icon_bits[y * 2 + 1] = (uint16_t)row;
    }
}

static void t_icons(WORD n)
{
    MFDB scr, ic;
    WORD i, pxy[8], col[2];

    scr.fd_addr = 0;
    ic.fd_addr = (uint32_t)icon_bits;
    ic.fd_w = 32;
    ic.fd_h = 32;
    ic.fd_wdwidth = 2;
    ic.fd_stand = 0;
    ic.fd_nplanes = 1;
    ic.fd_r1 = ic.fd_r2 = ic.fd_r3 = 0;
    for (i = 0; i < n; i++) {
        col[0] = pen(i);
        col[1] = 0;
        pxy[0] = 0;
        pxy[1] = 0;
        pxy[2] = 31;
        pxy[3] = 31;
        pxy[4] = (WORD)(cx + (i * 37) % (cw - 32));
        pxy[5] = (WORD)(cy + (i * 11) % (ch - 32));
        pxy[6] = (WORD)(pxy[4] + 31);
        pxy[7] = (WORD)(pxy[5] + 31);
        vrt_cpyfm(vh, MD_TRANS, pxy, &ic, &scr, col);
    }
}

/* ---- the AES ------------------------------------------------------------- */

static char s_ok[] = "OK", s_cancel[] = "Cancel", s_line[] = "A dialog box";
static OBJECT dialog[5];

static void make_dialog(void)
{
    WORD k;

    for (k = 0; k < 5; k++) {
        dialog[k].ob_next = (WORD)(k + 1);
        dialog[k].ob_head = dialog[k].ob_tail = -1;
        dialog[k].ob_flags = 0;
        dialog[k].ob_state = 0;
    }
    dialog[0].ob_next = -1;
    dialog[0].ob_head = 1;
    dialog[0].ob_tail = 4;
    dialog[0].ob_type = G_BOX;
    dialog[0].ob_state = 0x10;                  /* OUTLINED */
    dialog[0].ob_spec.index = 0x00021100L;      /* border 2, black frame */
    dialog[0].ob_x = 0;
    dialog[0].ob_y = 0;
    dialog[0].ob_width = 176;
    dialog[0].ob_height = 64;
    dialog[4].ob_next = 0;
    dialog[4].ob_flags = LASTOB;

    dialog[1].ob_type = G_STRING;
    dialog[1].ob_spec.index = (LONG)(uint32_t)s_line;
    dialog[1].ob_x = 16;
    dialog[1].ob_y = 8;
    dialog[1].ob_width = 96;
    dialog[1].ob_height = 8;
    dialog[2].ob_type = G_BOX;
    dialog[2].ob_spec.index = 0x00011172L;
    dialog[2].ob_x = 136;
    dialog[2].ob_y = 8;
    dialog[2].ob_width = 24;
    dialog[2].ob_height = 16;
    for (k = 3; k < 5; k++) {
        dialog[k].ob_type = G_BUTTON;
        dialog[k].ob_flags |= 0x0001 | 0x0004;  /* SELECTABLE | EXIT */
        dialog[k].ob_x = (WORD)(16 + (k - 3) * 80);
        dialog[k].ob_y = 40;
        dialog[k].ob_width = 64;
        dialog[k].ob_height = 16;
    }
    dialog[3].ob_flags |= 0x0002;               /* DEFAULT */
    dialog[3].ob_spec.index = (LONG)(uint32_t)s_ok;
    dialog[4].ob_spec.index = (LONG)(uint32_t)s_cancel;
}

static void t_dialog(WORD n)
{
    WORD i;

    for (i = 0; i < n; i++) {
        dialog[0].ob_x = (WORD)(cx + (i * 13) % (cw - 176));
        dialog[0].ob_y = (WORD)(cy + (i * 7) % (ch - 64));
        objc_draw(dialog, 0, 8, cx, cy, cw, ch);
    }
}

static char w2name[] = " a window ";

static void drain(void)
{
    WORD msg[8], mx, my, mb, ks, kr, br;

    while (evnt_multi_moblk(MU_MESAG | MU_TIMER, 0, 0, 0, 0, 0, msg, 0, 0,
                            &mx, &my, &mb, &ks, &kr, &br) & MU_MESAG)
        ;
}

static void t_windows(WORD n)
{
    WORD i, w;

    for (i = 0; i < n; i++) {
        w = wind_create(NAME | CLOSER | MOVER, cx, cy, cw, ch);
        if (w < 0)
            return;
        wind_set_str(w, 2 /* WF_NAME */, w2name);
        wind_open(w, (WORD)(cx + cw / 4), (WORD)(cy + ch / 4),
                  (WORD)(cw / 2), (WORD)(ch / 2));
        wind_close(w);
        wind_delete(w);
    }
}

/* ---- the CPU: a Mandelbrot ---------------------------------------------- */

/* Fixed point with 12 bits after the point, in 16-bit words, and a 32-bit
 * product for each multiply -- which on this CPU is the run-time library's
 * multiply, and that is part of what is being measured.  Each row is
 * drawn as it is worked out, one line per run of equal colour. */
#define FIX 12
#define MAXIT 32

static void t_mandel(WORD n)
{
    /* 64x40: at 160x100 it took four minutes, three quarters of that in
     * the run-time library's _Mul32 (docs/roadmap-0.9.md) -- a number to
     * beat, and a size that keeps a whole run to a minute or two. */
    WORD fw = min(64, (WORD)(cw - 8)), fh = min(40, (WORD)(ch - 8));
    WORD px, py, it, rep, run, runcol, pxy[4];
    WORD x0, y0, dx, dy;

    dx = (WORD)((3L << FIX) / fw);              /* -2.0 .. 1.0 across */
    dy = (WORD)((2L << FIX) / fh);              /* -1.0 .. 1.0 down   */
    for (rep = 0; rep < n; rep++) {
        y0 = (WORD)(-(1 << FIX));
        for (py = 0; py < fh; py++, y0 = (WORD)(y0 + dy)) {
            x0 = (WORD)(-(2 << FIX));
            run = 0;
            runcol = -1;
            for (px = 0; px <= fw; px++, x0 = (WORD)(x0 + dx)) {
                WORD col = -2;

                if (px < fw) {
                    WORD x = 0, y = 0, xx, yy;

                    for (it = 0; it < MAXIT; it++) {
                        LONG x2 = ((LONG)x * x) >> FIX, y2 = ((LONG)y * y) >> FIX;

                        if (x2 + y2 > (4L << FIX))
                            break;
                        yy = (WORD)(((((LONG)x * y) >> FIX) << 1) + y0);
                        xx = (WORD)(x2 - y2 + x0);
                        x = xx;
                        y = yy;
                    }
                    col = (WORD)(it == MAXIT ? 0 : (ncol > 2 ? 1 + it % (ncol - 1) : (it & 1)));
                }
                if (col != runcol) {
                    if (run && runcol > 0) {
                        vsl_color(vh, runcol);
                        pxy[0] = (WORD)(cx + 4 + px - run);
                        pxy[1] = pxy[3] = (WORD)(cy + 4 + py);
                        pxy[2] = (WORD)(cx + 4 + px - 1);
                        v_pline(vh, 2, pxy);
                    }
                    runcol = col;
                    run = 0;
                }
                run++;
            }
        }
    }
}

/* ---- the table ------------------------------------------------------------ */

typedef struct {
    const char *group;
    const char *name;
    void (*fn)(WORD);
    WORD n;
} TEST;

static const TEST tests[NTESTS] = {
    { "Graphics", "horizontal lines",       t_hlines,   200 },
    { "",         "vertical lines",         t_vlines,   200 },
    { "",         "diagonal lines",         t_dlines,   100 },
    { "",         "filled boxes, solid",    t_solid,     50 },
    { "",         "filled boxes, pattern",  t_pattern,   50 },
    { "",         "filled circles",         t_circles,   20 },
    { "",         "filled ellipses",        t_ellipses,  20 },
    { "",         "polygons",               t_polygons,  20 },
    { "",         "rounded boxes",          t_rboxes,    20 },
    { "Text",     "40 characters",          t_text,      50 },
    { "",         "bold and underlined",    t_effects,   50 },
    { "",         "four heights",           t_heights,   50 },
    { "Blits",    "screen to screen",       t_copy,      50 },
    { "",         "screen to memory, back", t_memcopy,   50 },
    { "",         "icons",                  t_icons,    100 },
    { "AES",      "draw a dialog",          t_dialog,    20 },
    { "",         "open and close a window", t_windows,  10 },
    { "CPU",      "Mandelbrot",             t_mandel,     1 },
};

/* ---- the report --------------------------------------------------------- */

static char line[64];

/* n as decimal into line at p, right-aligned in `width`, with a point
 * `dec` digits from the right if dec. */
static WORD put_num(WORD p, LONG n, WORD width, WORD dec)
{
    char d[12];
    WORD k = 0, i;

    do {
        if (dec && k == dec)
            d[k++] = '.';
        d[k++] = (char)('0' + (WORD)(n % 10));
        n /= 10;
    } while (n || (dec && k <= dec));
    for (i = k; i < width; i++)
        line[p++] = ' ';
    while (k)
        line[p++] = d[--k];
    return p;
}

static WORD put_str(WORD p, const char *s, WORD width)
{
    WORD i = 0;

    while (s[i] && i < width)
        line[p++] = s[i++];
    for (; i < width; i++)
        line[p++] = ' ';
    return p;
}

/* Test k's line: group, name, milliseconds per call to three places. */
static void format(WORD k)
{
    WORD p = 0;
    LONG per = g4b_us[k] / tests[k].n;

    p = put_str(p, tests[k].group, 9);
    p = put_str(p, tests[k].name, 24);
    p = put_num(p, per, 9, 3);
    p = put_str(p, " ms", 3);
    line[p] = 0;
}

static WORD total_line(void)
{
    WORD p = 0, k;
    LONG sum = 0;

    for (k = 0; k < NTESTS; k++)
        sum += g4b_us[k] / 1000;
    p = put_str(p, "", 9);
    p = put_str(p, "all of it, once", 24);
    p = put_num(p, sum, 9, 0);
    p = put_str(p, " ms", 3);
    line[p] = 0;
    return p;
}

static void report_draw(void)
{
    WORD k, y, cwd, cht, bw, bh;

    canvas_clear();
    vst_effects(vh, 0);
    vst_height(vh, 6, &cwd, &cht, &bw, &bh);
    vst_color(vh, 1);
    vswr_mode(vh, MD_TRANS);
    y = (WORD)(cy + bh);
    if (bh < 8)
        bh++;                       /* the 6x6 face has no gap of its own */
    for (k = 0; k < NTESTS && y < cy + ch; k++, y = (WORD)(y + bh)) {
        format(k);
        v_gtext(vh, (WORD)(cx + 4), y, line);
    }
    if (y < cy + ch) {
        total_line();
        v_gtext(vh, (WORD)(cx + 4), y, line);
    }
    vswr_mode(vh, MD_REPLACE);
}

static void report_file(void)
{
    LONG f = Fcreate("G4BENCH.TXT", 0);
    WORD k, n;

    if (f < 0)
        return;
    for (k = 0; k < NTESTS; k++) {
        format(k);
        for (n = 0; line[n]; n++)
            ;
        line[n++] = '\r';
        line[n++] = '\n';
        Fwrite((WORD)f, n, (const void FAR *)line);
    }
    n = total_line();
    line[n++] = '\r';
    line[n++] = '\n';
    Fwrite((WORD)f, n, (const void FAR *)line);
    Fclose((WORD)f);
}

/* A WM_REDRAW: the report again, through each visible rectangle. */
static void redraw(WORD x, WORD y, WORD w, WORD h)
{
    WORD rx, ry, rw, rh, pxy[4];

    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    wind_get(wh, WF_FIRSTXYWH, &rx, &ry, &rw, &rh);
    while (rw && rh) {
        WORD ax = rx > x ? rx : x, ay = ry > y ? ry : y;
        WORD bx = (rx + rw < x + w) ? rx + rw : x + w;
        WORD by = (ry + rh < y + h) ? ry + rh : y + h;

        if (bx > ax && by > ay) {
            pxy[0] = ax;
            pxy[1] = ay;
            pxy[2] = (WORD)(bx - 1);
            pxy[3] = (WORD)(by - 1);
            vs_clip(vh, 1, pxy);
            report_draw();
        }
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

int main(void)
{
    WORD wchar, hchar, wbox, hbox, dx, dy, dw, dh, k;
    WORD msg[8], mx, my, mb, ks, kr, br, ev, done = FALSE;

    appl_init();
    vh = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &vh, work_out);
    vq_extnd(vh, 1, ext_out);
    ncol = work_out[13];
    planes = ext_out[4];
    make_icon();
    make_dialog();

    wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
    wh = wind_create(NAME | CLOSER, dx, dy, dw, dh);
    if (wh < 0) {
        v_clsvwk(vh);
        appl_exit();
        return 1;
    }
    wind_set_str(wh, 2 /* WF_NAME */, title);
    wind_open(wh, dx, dy, dw, dh);
    wind_get(wh, WF_WORKXYWH, &cx, &cy, &cw, &ch);
    drain();                                    /* the window's first redraw */

    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    canvas_clip();
    for (k = 0; k < NTESTS; k++) {
        canvas_clear();
        if (tests[k].fn == t_windows) {         /* the AES must run it */
            wind_update(END_UPDATE);
            start();
            tests[k].fn(tests[k].n);
            drain();
            g4b_us[k] = stop();
            wind_update(BEG_UPDATE);
            canvas_clip();
            continue;
        }
        start();
        tests[k].fn(tests[k].n);
        g4b_us[k] = stop();
    }
    canvas_clip();
    report_draw();
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
    report_file();
    g4b_done = 1;

    while (!done) {
        ev = evnt_multi_moblk(MU_MESAG | MU_KEYBD, 0, 0, 0, 0, 0, msg, 0, 0,
                              &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_KEYBD)
            done = TRUE;
        if (ev & MU_MESAG) {
            if (msg[0] == WM_REDRAW && msg[3] == wh)
                redraw(msg[4], msg[5], msg[6], msg[7]);
            else if (msg[0] == WM_CLOSED && msg[3] == wh)
                done = TRUE;
        }
    }
    wind_close(wh);
    wind_delete(wh);
    v_clsvwk(vh);
    appl_exit();
    return 0;
}
