/* p6_prog.c -- step 5a of docs/6502.md: a program in a bank of its own.
 *
 * Built with the kit alone -- src/app/gem.h and lib/gemlib.c, the 6502's
 * gates (src/app/gemabi6502.s) and start-up (src/app/crt6502.s), linked
 * whole into one 16 KB bank (src/app/gemapp6502.scm) -- and loaded by
 * A6 into the first program slot (src/a6_evt.c), it knows no address of
 * the system's but the gate's.  Everything it passes is in its own bank
 * or on the shared C stack: its arrays, its parameter blocks, the
 * window's title, the text it draws, the message buffers.
 *
 * What it does, and what it leaves at $0640 for tests/emu/p6_prog.py:
 *
 *   $0640  'p' once main runs, 'W' waiting for its redraw, 'D' drawn,
 *          'E' about to return
 *   $0641  ap_id from appl_init; $0642-3 global[0] (the AES version)
 *   $0644  the workstation handle from v_opnvwk; $0645 the window's
 *   $0646  the character height graf_handle answered
 *   $0647  the first message's type; $0648 the window it names
 *   $0649-$0650  the window's work area: x, y, w, h (two bytes each)
 *   $0651  the rectangles its redraw painted
 *
 * Its redraw is what a GEM program owes its window: the AES draws the
 * frame and nothing inside it, so on WM_REDRAW the program walks the
 * window's rectangle list (WF_FIRSTXYWH, WF_NEXTXYWH) inside a
 * wind_update and paints each piece the redraw asks for -- white, and
 * its text -- clipped to it.  Without it the inside of the window shows
 * whatever was on the screen under it: window 2's title bar, here.
 *
 * and after its text it sends process 0 -- A6's application, which logs
 * every message it gets -- P6_HELLO with its ap_id and its window. */
#include "portab.h"
#include "gem.h"

#define STATUS   ((volatile unsigned char *)0x0600)
#define P6_HELLO 0x4138

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];
static const char title[] = " BANKED ";
static const char text[] = "FROM A BANK";

/* *a cut to what it shares with *b; 0 if nothing */
static WORD meet(WORD *a, const WORD *b)
{
    WORD x2 = a[0] + a[2], y2 = a[1] + a[3];
    WORD bx2 = b[0] + b[2], by2 = b[1] + b[3];

    if (b[0] > a[0]) a[0] = b[0];
    if (b[1] > a[1]) a[1] = b[1];
    if (bx2 < x2) x2 = bx2;
    if (by2 < y2) y2 = by2;
    a[2] = (WORD)(x2 - a[0]);
    a[3] = (WORD)(y2 - a[1]);
    return a[2] > 0 && a[3] > 0;
}

static void put16(uint8_t at, WORD v)
{
    STATUS[at] = (unsigned char)v;
    STATUS[at + 1] = (unsigned char)((UWORD)v >> 8);
}

int main(void)
{
    WORD ap, vh, wh, wc, hc, wb, hb, x, y, w, h;
    WORD msg[8], r[4], pxy[4];
    uint8_t pieces = 0;

    STATUS[0x40] = 'p';
    ap = appl_init();
    STATUS[0x41] = (unsigned char)ap;
    put16(0x42, global[0]);
    vh = graf_handle(&wc, &hc, &wb, &hb);
    STATUS[0x46] = (unsigned char)hc;
    v_opnvwk(work_in, &vh, work_out);
    STATUS[0x44] = (unsigned char)vh;

    wh = wind_create(NAME, 30, 40, 180, 60);
    STATUS[0x45] = (unsigned char)wh;
    wind_set_str(wh, WF_NAME, title);
    wind_open(wh, 30, 40, 180, 60);

    STATUS[0x40] = 'W';
    do {
        evnt_mesag(msg);
    } while (msg[0] != WM_REDRAW);
    STATUS[0x47] = (unsigned char)msg[0];
    STATUS[0x48] = (unsigned char)msg[3];
    wind_get(wh, WF_WORKXYWH, &x, &y, &w, &h);
    put16(0x49, x);
    put16(0x4B, y);
    put16(0x4D, w);
    put16(0x4F, h);
    vswr_mode(vh, 1);
    vsf_interior(vh, FIS_SOLID);
    vsf_color(vh, 0);
    wind_update(BEG_UPDATE);
    graf_mouse(M_OFF, 0);
    wind_get(wh, WF_FIRSTXYWH, &r[0], &r[1], &r[2], &r[3]);
    while (r[2] && r[3]) {
        if (meet(r, &msg[4])) {
            pxy[0] = r[0];
            pxy[1] = r[1];
            pxy[2] = (WORD)(r[0] + r[2] - 1);
            pxy[3] = (WORD)(r[1] + r[3] - 1);
            vs_clip(vh, 1, pxy);
            vr_recfl(vh, pxy);
            v_gtext(vh, (WORD)(x + 4), (WORD)(y + 12), text);
            pieces++;
        }
        wind_get(wh, WF_NEXTXYWH, &r[0], &r[1], &r[2], &r[3]);
    }
    vs_clip(vh, 0, pxy);
    graf_mouse(M_ON, 0);
    wind_update(END_UPDATE);
    STATUS[0x51] = pieces;
    STATUS[0x40] = 'D';

    msg[0] = P6_HELLO;
    msg[1] = ap;
    msg[2] = 0;
    msg[3] = ap;
    msg[4] = wh;
    msg[5] = msg[6] = msg[7] = 0;
    appl_write(0, 16, msg);

    STATUS[0x40] = 'E';
    return 0x1234;
}
