/* acc.c -- a desk accessory, whole and commented.
 *
 *     make KIND=acc APP=example/acc.c        ->  acc.g4a
 *
 * ...which you install as ACC.ACC beside GEM.COM, and it appears in the
 * Desk menu next to the clock and the calculator.
 *
 * AN ACCESSORY IS A PROGRAM, with the same crt, the same call gates and
 * the same budget as hello.c.  Four things make it one, and each is a
 * rule rather than a convention:
 *
 * 1. IT NEVER RETURNS.  A program's main() ends and the AES frees it; an
 *    accessory parks in evnt_mesag() forever.  Returning from here would
 *    hand your memory back while the Desk menu still has your name in it.
 *
 * 2. IT REGISTERS A NAME.  menu_register() puts you in the Desk menu and
 *    answers the slot number that AC_OPEN will carry.  There are six
 *    slots on this machine, TOS's number.
 *
 * 3. IT KEEPS THE POINTER, NOT A COPY.  menu_register stores the ADDRESS
 *    of the title you give it, so that string must outlive the call --
 *    `static`, or a global, never a local.  A local works until the
 *    stack is reused and then the Desk menu draws rubbish.
 *
 * 4. IT TAKES WHAT IT NEEDS AT START-UP AND NEVER GIVES IT BACK.  An
 *    accessory is loaded before the first program, and both of gem4xe's
 *    allocators are bump allocators that a program's exit winds back to
 *    a mark.  Anything you allocate AFTER a program has loaded is freed
 *    underneath you when that program ends.  So load your resource here,
 *    at start-up, and keep it: an accessory does not rsrc_free().
 *
 * THE TWO MESSAGES.  AC_OPEN (msg[4] is your slot) means somebody picked
 * your name; do your thing and come back.  AC_CLOSE means the program
 * you were open over is going away and anything of ITS you were holding
 * is gone -- close your windows, forget its handles.  Nothing here holds
 * anything of another program's, so AC_CLOSE only counts.
 *
 * WHERE IT GOES.  \GEM\, the directory GEM.COM was started from, never
 * \APPS\: the AES scans its own directory for *.ACC at start-up and
 * nowhere else.  Its resource, if it has one, goes beside it.
 */
#include "gem.h"

/* Rule 3: static, because menu_register keeps the pointer.  The two
 * leading spaces are the donor's convention -- they line the name up
 * under the desktop's own "About" in the drop-down. */
static char acc_title[] = "  Example";

static WORD acc_id;             /* appl_init's answer: our AES id */
static WORD acc_slot;           /* menu_register's: which line we are */

/* The alert is a literal here because this file is an example and a
 * literal reads better in one.  In a program you mean to translate it
 * would be a free string of your .RSC, fetched with rsrc_gaddr(R_STRING,
 * n, &p) -- gem4xe keeps no reader-visible string in its own C, for
 * exactly that reason. */
static const char acc_hello[] =
    "[1][An accessory, open over|whatever was running.][ OK ]";

int main(void)
{
    WORD msg[8];

    acc_id = appl_init();
    acc_slot = menu_register(acc_id, acc_title);
    /* A negative slot means there was no room -- six accessories are
     * already registered.  Park anyway rather than returning: see rule 1.
     * Nothing will ever send us AC_OPEN, which is the correct outcome. */

    for (;;) {
        evnt_mesag(msg);
        if (msg[0] == AC_OPEN && msg[4] == acc_slot)
            form_alert(1, acc_hello);
        /* else if (msg[0] == AC_CLOSE) -- let go of the departing
         * program's things here.  We hold none. */
    }
}
