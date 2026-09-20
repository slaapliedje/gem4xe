/* cpanelacc.c -- the control panel as a DESK ACCESSORY.
 *
 * AN ACCESSORY IS THE POINT, not a convenience.  A control panel exists
 * to be reached from inside the program you are using -- the moment you
 * want the double-click rate changed is the moment one did not register
 * -- and the Desk menu is the only door that is open then.  It matters
 * more here than it does on an ST: gem4xe runs one program at a time, so
 * while a program is up the Desk menu is the only door to a setting at
 * all.  (It used to matter more still -- a program as large as qed had to
 * be installed AS the desktop, and there was no Desk menu on that machine
 * at all.  Since qed's near region came down to 6,144 bytes it launches
 * FROM the desktop like anything else: docs/phase47.md.)
 *
 * Everything else is src/apps/clockacc.c's shape, for its reasons: the
 * resource is taken at start-up and never freed, because an accessory is
 * loaded before the first program and both allocators are bump allocators
 * that a program's exit winds back (src/aes/shel.c's pool_keep_mark); and
 * the title is a static because menu_register keeps the POINTER, not a
 * copy.  The two leading spaces are the donor's convention, lining the
 * name up under the desktop's own "About".
 *
 * THERE IS NO WORKSTATION to open or keep: the panel is a form the AES
 * draws, not a picture this program paints (src/apps/cpanel.c).  And
 * AC_CLOSE has nothing to do, because nothing here was taken from the
 * program that is going away.
 */
#include "gem.h"

WORD cp_start(void);
void cp_panel(void);

static char acc_title[] = "  Control Panel";

/* What a person driving the machine cannot see, for a gate to read. */
WORD acc_id;                    /* appl_init's answer */
WORD acc_menu;                  /* menu_register's: the slot */
WORD acc_opens;                 /* panels opened */
WORD acc_closes;                /* AC_CLOSE seen */

int main(void)
{
    WORD msg[8];

    acc_id = appl_init();
    if (!cp_start())
        acc_menu = -1;
    else
        acc_menu = menu_register(acc_id, acc_title);

    for (;;) {
        evnt_mesag(msg);
        if (msg[0] == AC_OPEN && msg[4] == acc_menu) {
            acc_opens++;
            cp_panel();
        } else if (msg[0] == AC_CLOSE) {
            acc_closes++;
        }
    }
}
