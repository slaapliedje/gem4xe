/* calcacc.c -- the calculator as a DESK ACCESSORY.
 *
 * The ST shipped one and it is the reason the Desk menu exists: a thing
 * you want WHILE you are using something else, not instead of it.  The
 * same src/apps/calc.c the program is built from, with the accessory's
 * main() and none of its own -- which is the point of having split it.
 *
 * COMPILED --data-model=large, so CALC.RSC goes to far memory rather than
 * the pool (src/aes/rsrc.c prefers far for a caller that can hold a
 * 32-bit pointer).  An accessory is charged to bank $00 for as long as
 * the machine is on, so 650 bytes it does not have to spend there is 650
 * bytes another accessory can have.
 *
 * NO WORKSTATION, unlike the program.  The panel is a form the AES draws
 * and form_do runs; the handle the program opens is never used for
 * anything but closing (src/apps/calc.c, calc_ws).  So there is nothing
 * to hold across an AC_CLOSE either.
 *
 * Everything else is src/apps/clockacc.c's shape, for its reasons: the
 * resource is taken at start-up and never freed, because an accessory is
 * loaded before the first program and both allocators are bump allocators
 * that a program's exit winds back (src/aes/shel.c's pool_keep_mark); and
 * the title is a static because menu_register keeps the POINTER, not a
 * copy -- which since 2026-09-19 it keeps whole, all 24 bits of it, so a
 * large-data accessory's far title survives (src/aes/menu.c).
 */
#include "gem.h"

WORD calc_start(void);
void calc_panel(void);

static char acc_title[] = "  Calculator";

/* What a person driving the machine cannot see, for a gate to read. */
WORD acc_id;                    /* appl_init's answer */
WORD acc_menu;                  /* menu_register's: the slot */
WORD acc_opens;                 /* panels opened */
WORD acc_closes;                /* AC_CLOSE seen */

int main(void)
{
    WORD msg[8];

    acc_id = appl_init();
    if (!calc_start())
        acc_menu = -1;
    else
        acc_menu = menu_register(acc_id, acc_title);

    for (;;) {
        evnt_mesag(msg);
        if (msg[0] == AC_OPEN && msg[4] == acc_menu) {
            acc_opens++;
            calc_panel();
        } else if (msg[0] == AC_CLOSE) {
            acc_closes++;
        }
    }
}
