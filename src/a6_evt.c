/* a6_evt.c -- step 4e of docs/6502.md: the input poll and the event loop
 * on a stock 6502, on one process.  Called by src/a6_aes.c once the
 * screen step 4c draws is up and the gate says go; banked.
 *
 * The interrupt handlers go in (src/sys6502/irq6502.s and .c, step 4d),
 * the pointer is the CX80 trak-ball through the VDI's pointer layer, and
 * then an application's loop: evnt_multi for a key, a click and a
 * message, every event it answers filed in a6_log, and the two messages
 * an application must act on acted on -- MN_SELECTED (the title put back,
 * menu_tnormal's call) and WM_CLOSED (the window closed).  Everything
 * between -- the poll, the control manager dropping a menu and tracking
 * it, the close box, the double-click count, the turn proc_yield offers
 * and nobody takes -- is the AES's own code, as on the 65C816.
 *
 * And what every application does that the AES does not: the pointer on
 * and an arrow, as src/aes/shel.c's sh_main gives each program (there is
 * no shell here); and WM_REDRAW answered -- the AES draws a window's frame
 * and the application its inside, here a white one, a piece of the
 * window's rectangle list at a time.  Without it a window's inside keeps
 * whatever was on the screen before: what a closed window left over it.
 *
 * a6_log: A6_LOG records of A6_REC words, the n-th at n % A6_LOG, n in
 * a6_nlog (build/a6.map): what ev_multi answered, the pointer, its
 * buttons and the shift state, the key, the clicks, and the message's
 * words 0, 3 and 4.  $0607 is 'L' once the loop runs; $060A is 1 while
 * it closes a window and 2 when it has.
 */
#include "portab.h"
#include "aes/aes.h"
#include "sys/irq.h"
#include "vdi/pointer.h"

#define STATUS ((volatile unsigned char *)0x0600)

#define A6_LOG  8
#define A6_REC  10
WORD     a6_log[A6_LOG][A6_REC];        /* resident: the gate reads it */
uint16_t a6_nlog;

/* The inside of window wh, white, where it shows inside *area. */
static void redraw(WORD wh, const GRECT *area)
{
    WORD w[4];
    GRECT r;

    gsx_moff();
    wm_get(wh, WF_FIRSTXYWH, w, 0);
    while (w[2] && w[3]) {
        r.g_x = w[0];
        r.g_y = w[1];
        r.g_w = w[2];
        r.g_h = w[3];
        if (rc_intersect(area, &r)) {
            gsx_sclip(&r);
            gr_rect(WHITE, IP_HOLLOW, &r);
        }
        wm_get(wh, WF_NEXTXYWH, w, 0);
    }
    gsx_sclip(&gl_rscreen);
    gsx_mon();
}

void a6_events(void)
{
    static const MOBLK none = { 0, 0, 0, 0, 0 };
    WORD msg[8], rets[6];
    WORD which, *r, i;
    GRECT area;

    irq_install();
    ptr_init(PTR_TRAKBALL, 160, 96);
    ratinit();                          /* the pointer on, and an arrow */
    gr_mouse(ARROW, 0);
    STATUS[7] = 'L';
    for (;;) {
        for (i = 0; i < 8; i++)
            msg[i] = 0;
        rets[4] = rets[5] = 0;
        /* a left press, up to two clicks; any key; any message */
        which = ev_multi(MU_KEYBD | MU_BUTTON | MU_MESAG, &none, &none, 0,
                         combine_cms(2, 1, 1), msg, rets);
        r = a6_log[a6_nlog % A6_LOG];
        r[0] = which;
        for (i = 0; i < 6; i++)
            r[1 + i] = rets[i];
        r[7] = msg[0];
        r[8] = msg[3];
        r[9] = msg[4];
        a6_nlog++;
        if (which & MU_MESAG) {
            if (msg[0] == MN_SELECTED && gl_mntree)
                do_chg(gl_mntree, msg[3], SELECTED, FALSE, TRUE, TRUE);
            else if (msg[0] == WM_REDRAW) {
                area.g_x = msg[4];
                area.g_y = msg[5];
                area.g_w = msg[6];
                area.g_h = msg[7];
                redraw(msg[3], &area);
            } else if (msg[0] == WM_CLOSED)
            {
                STATUS[10] = 1;             /* a close redraws: seconds */
                wm_close(msg[3]);
                STATUS[10] = 2;
            }
        }
    }
}
