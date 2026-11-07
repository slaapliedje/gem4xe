/* m50_acc.c -- the phase 123 gate accessory: a shutdown, asked for.
 *
 * AES 4's shel_write(SWM_SHUTDOWN) from the side that ASKS (src/aes/
 * shel.c, sh_shutdown).  An accessory is the one process that can ask a
 * running program to end -- the program is process 0 and the desktop is
 * not running beside it -- which is also where a task switcher would sit.
 *
 * THE GATE DRIVES IT through acc_req: it writes SD_PARTIAL or SD_COMPLETE
 * to ask for a shutdown, or ACC_ABORT to abort one, and on its next tick
 * the accessory makes that call, counts it and keeps the answer.  Every
 * SHUT_COMPLETED that comes back is counted and kept word for word, as
 * every AC_CLOSE is counted.  Everything the gate reads is a global here,
 * found by symbol (tests/emu/m50_shutdown.py).
 */
#include "gem.h"

WORD acc_id;                    /* appl_init's answer */
WORD acc_menu;                  /* menu_register's */
WORD acc_ticks;                 /* timer waits: it is alive */
WORD acc_req;                   /* the gate writes: SD_*, or ACC_ABORT */
WORD acc_asked;                 /* shel_write(SWM_SHUTDOWN) calls made */
WORD acc_ret;                   /* ...and what the last one answered */
WORD acc_shut;                  /* SHUT_COMPLETED received */
WORD acc_shutmsg[8];            /* ...the last one, word for word */
WORD acc_closes;                /* AC_CLOSE received */
WORD acc_g2;                    /* global[2] after appl_init: its own id
                                 * since phase 124 (test-m51 reads it) */
WORD acc_wh = -1;               /* ACC_OPEN's window (test-m52, phase 125) */
WORD acc_opens;                 /* AC_OPEN received (test-m55, phase 130)... */
WORD acc_openid;                /* ...and its menu id, msg[4] */
WORD acc_rsc;                   /* ACC_RSRC's rsrc_load answered */

/* SD_ABORT is 0, which is also "nothing asked": the gate writes this. */
#define ACC_ABORT 3
/* ...and test-m52's two (phase 125): a window of the accessory's own
 * opened over the program's, and closed again -- so the program's comes
 * back to the top without the program doing it, which is WM_ONTOP. */
#define ACC_OPEN  10
#define ACC_CLOSE 11
/* ...and test-m57's (phase 132): a resource loaded at run time, into the
 * pool -- where a program put aside was -- and freed again. */
#define ACC_RSRC  12
#define ACC_UNRSRC 13

static char acc_title[] = "  Shutdown gate";

int main(void)
{
    WORD msg[8], mx, my, mb, ks, kr, br, i;

    acc_id = appl_init();
    acc_g2 = global[2];
    acc_menu = menu_register(acc_id, acc_title);
    for (;;) {
        WORD what = evnt_multi_moblk((UWORD)(MU_MESAG | MU_TIMER), 1, 1, 1,
                                     0, 0, msg, 100, 0,
                                     &mx, &my, &mb, &ks, &kr, &br);
        if (what & MU_TIMER) {
            acc_ticks++;
            if (acc_req == ACC_OPEN && acc_wh < 0) {
                acc_req = 0;
                acc_wh = wind_create(NAME, 300, 120, 200, 80);
                if (acc_wh >= 0)
                    wind_open(acc_wh, 300, 120, 200, 80);
                acc_asked++;
            } else if (acc_req == ACC_RSRC) {
                acc_req = 0;
                acc_rsc = rsrc_load("M50.RSC");
                acc_asked++;
            } else if (acc_req == ACC_UNRSRC) {
                acc_req = 0;
                if (acc_rsc)
                    rsrc_free();
                acc_rsc = 0;
                acc_asked++;
            } else if (acc_req == ACC_CLOSE && acc_wh >= 0) {
                acc_req = 0;
                wind_close(acc_wh);
                wind_delete(acc_wh);
                acc_wh = -1;
                acc_asked++;
            } else if (acc_req) {
                WORD how = acc_req;
                acc_req = 0;
                acc_ret = shel_write(SWM_SHUTDOWN,
                                     how == ACC_ABORT ? SD_ABORT : how,
                                     0, 0, 0);
                acc_asked++;
            }
        }
        if (!(what & MU_MESAG))
            continue;
        if (msg[0] == SHUT_COMPLETED) {
            acc_shut++;
            for (i = 0; i < 8; i++)
                acc_shutmsg[i] = msg[i];
        } else if (msg[0] == AC_CLOSE) {
            acc_closes++;
        } else if (msg[0] == AC_OPEN) {
            acc_openid = msg[4];
            acc_opens++;
        }
    }
}
