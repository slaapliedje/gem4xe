/* clockacc.c -- the clock as a DESK ACCESSORY.
 *
 * The same src/apps/clock.c that CLOCK.PRG is built from, with the shape
 * the donor's own accessory skeleton has: take what you need while the
 * AES is starting up, register a name in the Desk menu, then an
 * indefinite message loop that never exits.
 *
 * THE RESOURCE IS TAKEN HERE, at start-up, and never freed.  That is not
 * tidiness, it is the rule: an accessory is loaded before the first
 * program, and both of gem4xe's allocators are bump allocators that
 * app_free winds back to where app_load found them.  Anything an
 * accessory takes AFTER a program has loaded is freed underneath it the
 * first time that program exits.  So everything comes first, and nothing
 * goes back.
 *
 * THE TITLE IS A STATIC for a related reason: menu_register keeps the
 * POINTER, not a copy -- the AES puts it straight into the Desk box's
 * object -- so a title in a local, or in memory the accessory might
 * release, is a dangling pointer in the menu.  The two leading spaces are
 * the donor's convention: they line the name up under the desktop's own
 * "About" item.
 *
 * THE WORKSTATION IS OPENED ONCE and kept, which is the thing an
 * accessory could not do until a virtual workstation had an owner: the
 * AES used to close every one of them when any program ended, so this
 * file opened and closed one around each panel instead.  Now a program
 * ending closes only its own (src/vdi/vdi.c), and the same is true of
 * open files and searches (src/sys/gemdos.c), so an accessory can hold
 * what it needs.
 *
 * AC_CLOSE has nothing to do here.  It means "the program you were
 * sitting under has gone and its memory is about to be reclaimed", and
 * this accessory took nothing from that program -- its resource and its
 * workstation are its own, from before the program existed.  It must not
 * close its own window either: the AES does that, and a handle kept
 * across an AC_CLOSE is a handle to a window that no longer exists.
 */
#include "gem.h"

WORD clock_start(void);
WORD clock_ws(void);
void clock_panel(WORD handle);

static char acc_title[] = "  Clock";

/* What a person driving the machine cannot see, for a gate to read. */
WORD acc_id;                    /* appl_init's answer */
WORD acc_menu;                  /* menu_register's: the slot */
WORD acc_opens;                 /* panels opened */
WORD acc_closes;                /* AC_CLOSE seen */
WORD acc_ws;                    /* its workstation, held for the duration */

int main(void)
{
    WORD msg[8];

    acc_id = appl_init();
    if (!clock_start()) {
        acc_menu = -1;
    } else {
        acc_ws = clock_ws();            /* once, and kept */
        acc_menu = menu_register(acc_id, acc_title);
    }

    for (;;) {
        evnt_mesag(msg);
        if (msg[0] == AC_OPEN && msg[4] == acc_menu) {
            acc_opens++;
            clock_panel(acc_ws);
        } else if (msg[0] == AC_CLOSE) {
            acc_closes++;
        }
    }
}
