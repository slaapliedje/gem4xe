/* hello_app.c -- HELLO.PRG, the desktop's hello-world.
 *
 * The smallest thing that is a real GEM PROGRAM rather than a gate: it
 * opens one titled window with a closer and a mover, draws a line of
 * text in it, and runs the message loop a program runs -- redraw when
 * the AES asks, follow the window when it is dragged, and end when the
 * closer is clicked -- then puts the window away and returns to the
 * desktop.  It is what M11.PRG never was: a program you can leave open
 * and then close, instead of one that flashes for two-thirds of a second
 * and exits (docs, and the note in tools/mkdist.py).
 *
 * It reaches the AES and the VDI through the two COP entries only
 * (src/app/gemapp.scm, src/app/gem.h) -- linked against nothing of
 * gem4xe's -- so it is also, incidentally, a worked example for anyone
 * writing a gem4xe application.  The window idiom is the desktop's own
 * (src/desk/deskwin.c, hndl_wmsg / do_wredraw), reduced to one window
 * whose contents are two lines of text rather than an object tree.
 */
#include "portab.h"
#include "gem.h"

/* The AES keeps the POINTER to a window's title, not a copy (src/aes/wind.c,
 * WF_NAME), so the string has to outlive the wind_set -- static, in bank $00
 * where a near address reaches it. */
static char s_title[] = " Hello ";
static const char s_line1[] = "Hello, world!";
static const char s_line2[] = "A GEM program on the Atari, built with gem4xe.";

static WORD work_in[11];
static WORD work_out[57];

/* Draw the window's contents over one rectangle of its list: clear it to
 * the window background and put the two lines in the work area, clipped
 * to the piece.  The AES has already told us which pieces show; text
 * that falls outside the clip is simply not drawn. */
static void draw_piece(WORD handle, const GRECT *work, const GRECT *piece)
{
    WORD pxy[4];

    pxy[0] = piece->g_x;
    pxy[1] = piece->g_y;
    pxy[2] = (WORD)(piece->g_x + piece->g_w - 1);
    pxy[3] = (WORD)(piece->g_y + piece->g_h - 1);
    vs_clip(handle, 1, pxy);

    vsf_interior(handle, 1);            /* solid */
    vsf_color(handle, 0);               /* the window ground: white */
    vr_recfl(handle, pxy);

    vst_color(handle, 1);               /* ink: black */
    v_gtext(handle, (WORD)(work->g_x + 12), (WORD)(work->g_y + 16), s_line1);
    v_gtext(handle, (WORD)(work->g_x + 12), (WORD)(work->g_y + 32), s_line2);
}

/* WM_REDRAW: walk the window's rectangle list and draw each piece that
 * meets the dirty rectangle, with the mouse hidden across the drawing
 * and the screen locked, exactly as the desktop's do_wredraw does. */
static void redraw(WORD handle, WORD wh, const GRECT *dirty)
{
    GRECT work, t;

    wind_get_grect(wh, WF_WORKXYWH, &work);
    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    wind_get_grect(wh, WF_FIRSTXYWH, &t);
    while (t.g_w && t.g_h) {
        if (rc_intersect(dirty, &t))
            draw_piece(handle, &work, &t);
        wind_get_grect(wh, WF_NEXTXYWH, &t);
    }
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

int main(void)
{
    WORD handle, wchar, hchar, wbox, hbox;
    WORD wh, done = FALSE;
    WORD msg[8];
    WORD k;
    GRECT r;

    appl_init();
    handle = graf_handle(&wchar, &hchar, &wbox, &hbox);
    for (k = 0; k < 10; k++)
        work_in[k] = 1;
    work_in[10] = 2;
    v_opnvwk(work_in, &handle, work_out);
    if (!handle) {
        appl_exit();
        return 1;
    }

    /* One window, no bigger than the desk below the menu bar. */
    wh = wind_create(NAME | CLOSER | MOVER, 0, hbox, 640, (WORD)(240 - hbox));
    if (wh < 0) {
        v_clsvwk(handle);
        appl_exit();
        return 1;
    }
    wind_set_str(wh, WF_NAME, s_title);
    /* Opened centred-ish; x even so a move is one blit, not a shift
     * (the blitter has no shifter -- docs/phase2b.md, the window manager). */
    wind_open(wh, 160, 70, 320, 104);

    while (!done) {
        evnt_mesag(msg);
        wh = msg[3];
        switch (msg[0]) {
        case WM_REDRAW:
            r.g_x = msg[4];
            r.g_y = msg[5];
            r.g_w = msg[6];
            r.g_h = msg[7];
            redraw(handle, wh, &r);
            break;
        case WM_TOPPED:
            wind_set(wh, WF_TOP, 0, 0, 0, 0);
            break;
        case WM_MOVED:
            r.g_x = (WORD)(msg[4] & ~1);        /* even x: one blit */
            r.g_y = msg[5];
            r.g_w = msg[6];
            r.g_h = msg[7];
            wind_set(wh, WF_CURRXYWH, r.g_x, r.g_y, r.g_w, r.g_h);
            break;
        case WM_CLOSED:
            done = TRUE;
            break;
        default:
            break;
        }
    }

    wind_close(wh);
    wind_delete(wh);
    v_clsvwk(handle);
    appl_exit();
    return 0;
}
