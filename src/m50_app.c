/* m50_app.c -- the phase 123 gate program: a shutdown, answered.
 *
 * One program, four ways of answering AP_TERM, chosen by the letter its
 * file is named with -- the gate puts the same .G4A on the disk four
 * times (tests/emu/m50_shutdown.py):
 *
 *   M50U.PRG   never registers: a shutdown must be REFUSED while it runs,
 *              and nothing sent to it -- it might be holding work
 *   M50F.PRG   registers, and answers the first AP_TERM with AP_TFAIL,
 *              code 77; ends on the second
 *   M50T.PRG   registers, and ends on AP_TERM
 *   M50S.PRG   registers, and never answers: what the one asking can
 *              then do is abort
 *
 * It also keeps appl_getinfo's answers on the shell and on messages, the
 * two subjects phase 123 changed, for the gate to read.  Everything the
 * gate reads is a global here, found by symbol; app_quit is the gate's
 * way of ending it otherwise.
 */
#include "gem.h"

WORD app_mode;                  /* 'U', 'F', 'T' or 'S' */
WORD app_reg;                   /* shel_write(SWM_NEWMSG)'s answer, or -1 */
WORD app_ticks;                 /* timer waits: it is running */
WORD app_terms;                 /* AP_TERM received */
WORD app_last[8];               /* ...the last one, word for word */
WORD app_fail;                  /* shel_write(SWM_AESMSG)'s answer */
WORD app_quit;                  /* the gate writes 1: end */
WORD app_shell[4];              /* appl_getinfo(AES_SHELL) */
WORD app_mesg[4];               /* appl_getinfo(AES_MESSAGE) */

#define AES_SHELL   10
#define AES_MESSAGE 12

int main(void)
{
    char cmd[130], tail[130];
    WORD msg[8], mx, my, mb, ks, kr, br, i, dot = -1;

    appl_init();
    cmd[0] = 0;
    shel_read(cmd, tail);
    for (i = 0; cmd[i]; i++)
        if (cmd[i] == '.')
            dot = i;
    app_mode = (dot > 0) ? cmd[dot - 1] : '?';
    appl_getinfo(AES_SHELL, &app_shell[0], &app_shell[1], &app_shell[2],
                 &app_shell[3]);
    appl_getinfo(AES_MESSAGE, &app_mesg[0], &app_mesg[1], &app_mesg[2],
                 &app_mesg[3]);
    app_reg = -1;
    if (app_mode != 'U')
        app_reg = shel_write(SWM_NEWMSG, NM_APTERM, 0, 0, 0);

    while (!app_quit) {
        WORD what = evnt_multi_moblk((UWORD)(MU_MESAG | MU_TIMER), 1, 1, 1,
                                     0, 0, msg, 100, 0,
                                     &mx, &my, &mb, &ks, &kr, &br);
        if (what & MU_TIMER)
            app_ticks++;
        if (!(what & MU_MESAG) || msg[0] != AP_TERM)
            continue;
        app_terms++;
        for (i = 0; i < 8; i++)
            app_last[i] = msg[i];
        if (app_mode == 'T')
            break;
        if (app_mode == 'F') {
            if (app_terms > 1)
                break;
            {
                WORD f[8] = { AP_TFAIL, 77, 0, 0, 0, 0, 0, 0 };
                app_fail = shel_write(SWM_AESMSG, 0, 0, (const char *)f, 0);
            }
        }
        /* 'S' says nothing, and 'U' was never sent one */
    }
    appl_exit();
    return 0;
}
