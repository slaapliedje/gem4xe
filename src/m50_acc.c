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

/* SD_ABORT is 0, which is also "nothing asked": the gate writes this. */
#define ACC_ABORT 3

static char acc_title[] = "  Shutdown gate";

int main(void)
{
    WORD msg[8], mx, my, mb, ks, kr, br, i;

    acc_id = appl_init();
    acc_menu = menu_register(acc_id, acc_title);
    for (;;) {
        WORD what = evnt_multi_moblk((UWORD)(MU_MESAG | MU_TIMER), 1, 1, 1,
                                     0, 0, msg, 100, 0,
                                     &mx, &my, &mb, &ks, &kr, &br);
        if (what & MU_TIMER) {
            acc_ticks++;
            if (acc_req) {
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
        }
    }
}
