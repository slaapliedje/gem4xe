/* cpanel6.c -- the control panel as a 6502 program (docs/6502.md, step
 * 5f): src/apps/cpanel.c's panel with General and Color built in, opened
 * at once and run until its window closes, when the program ends and the
 * desktop comes back (src/a6_evt.c, the shell).  On the 65C816 the panel
 * is a desk accessory beside the desktop (src/apps/cpanelacc.c); the 6502
 * has no disk-loaded accessories, and a program of several banks runs
 * alone. */
#include "gem.h"

WORD cp_start(void);
void cp_bootinit(void);
void cp_open(void);
void cp_message(const WORD *msg);
WORD cp_wait(WORD *msg);
extern WORD cp_wh;

WORD cp6_runs;                  /* panels shown, for a gate to read */

int main(void)
{
    WORD msg[8];

    appl_init();
    if (cp_start()) {
        cp_bootinit();
        cp_open();
        if (cp_wh >= 0)
            cp6_runs++;
        while (cp_wh >= 0)
            if (cp_wait(msg) & MU_MESAG)
                cp_message(msg);
    }
    appl_exit();
    return 0;
}
