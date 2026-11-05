/* m52_app.c -- the phase 125 gate program: the top changes hands.
 *
 * Two windows of its own, A and B, and a log of every window message it
 * is sent -- type and handle -- for tests/emu/m52_winmsg.py to read by
 * symbol.  It answers WM_TOPPED and WM_BOTTOMED as an AES 4 program does,
 * with wind_set(WF_TOP) and wind_set(WF_BOTTOM), and does one thing on its
 * own when the gate writes `step`: 1 tops A itself.  The rest is done to
 * it -- by the gate accessory (M50.ACC) opening and closing a window over
 * it, and by the gate clicking, with and without Shift.
 *
 * It also sets the desk's tree to a one-object tree of its own and reads
 * it back with wind_get(WF_NEWDESK), then puts the default back.
 */
#include "gem.h"

WORD r_wh[2];                   /* A and B */
WORD r_rect[2][4];              /* their outer rectangles */
WORD r_log[48][2];              /* window messages: type, handle */
WORD r_nlog;
WORD r_mesg[5], r_win[5];       /* appl_getinfo 12 and 11 */
WORD r_newdesk[3];              /* wind_get(WF_NEWDESK) after setting it */
WORD r_ready;
WORD step;                      /* the gate writes: 1 top A */
WORD app_quit;

OBJECT r_desk[1] = {
    { -1, -1, -1, G_BOX, LASTOB, NORMAL, { 0x00001143L }, 0, 0, 640, 240 }
};

static void logmsg(const WORD *m)
{
    if (r_nlog < 48) {
        r_log[r_nlog][0] = m[0];
        r_log[r_nlog][1] = m[3];
        r_nlog++;
    }
}

int main(void)
{
    WORD msg[8], mx, my, mb, ks, kr, br, i;
    uint32_t a = (uint32_t)(OBJECT FAR *)r_desk;

    appl_init();
    appl_getinfo(AES_MESSAGE, &r_mesg[1], &r_mesg[2], &r_mesg[3], &r_mesg[4]);
    appl_getinfo(AES_WINDOW, &r_win[1], &r_win[2], &r_win[3], &r_win[4]);

    wind_set(0, WF_NEWDESK, (WORD)(a >> 16), (WORD)(a & 0xFFFF), 0, 0);
    wind_get(0, WF_NEWDESK, &r_newdesk[0], &r_newdesk[1], &r_newdesk[2], &i);
    wind_set(0, WF_NEWDESK, 0, 0, 0, 0);

    r_wh[0] = wind_create(NAME | MOVER, 20, 30, 260, 120);
    r_wh[1] = wind_create(NAME | MOVER, 120, 60, 260, 120);
    wind_set_str(r_wh[0], WF_NAME, " A ");
    wind_set_str(r_wh[1], WF_NAME, " B ");
    wind_open(r_wh[0], 20, 30, 260, 120);
    wind_open(r_wh[1], 120, 60, 260, 120);
    for (i = 0; i < 2; i++)
        wind_get(r_wh[i], WF_CURRXYWH, &r_rect[i][0], &r_rect[i][1],
                 &r_rect[i][2], &r_rect[i][3]);
    r_nlog = 0;                         /* what opening them said is not
                                         * what is being tested */
    r_ready = 1;

    while (!app_quit) {
        WORD what = evnt_multi_moblk((UWORD)(MU_MESAG | MU_TIMER), 1, 1, 1,
                                     0, 0, msg, 100, 0,
                                     &mx, &my, &mb, &ks, &kr, &br);
        if (step == 1) {
            step = 0;
            wind_set(r_wh[0], WF_TOP, 0, 0, 0, 0);
        }
        if (!(what & MU_MESAG))
            continue;
        switch (msg[0]) {
        case WM_TOPPED:
            logmsg(msg);
            wind_set(msg[3], WF_TOP, 0, 0, 0, 0);
            break;
        case WM_BOTTOMED:
            logmsg(msg);
            wind_set(msg[3], WF_BOTTOM, 0, 0, 0, 0);
            break;
        case WM_UNTOPPED:
        case WM_ONTOP:
            logmsg(msg);
            break;
        default:                        /* redraws: the frames are the
                                         * AES's, the insides are blank */
            break;
        }
    }
    for (i = 1; i >= 0; i--) {
        wind_close(r_wh[i]);
        wind_delete(r_wh[i]);
    }
    appl_exit();
    return 0;
}
