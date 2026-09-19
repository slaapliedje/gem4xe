/* ctrl.c -- the AES control manager (EmuTOS aes/gemctrl.c): what a press
 * on a window's frame does.
 *
 * GEM runs this as its own process, woken by every press that is not the
 * application's (see event.c).  Here it is a call, hctl_button, made from
 * the poll that saw the press: it finds the window, and on the top window
 * the gadget, and does the gadget's work -- tracks the button over the
 * closer or fuller, drags the mover's outline, rubbers the sizer's, drags
 * an elevator -- then sends the application one message saying what to
 * do about it.  Nothing here moves a window: WM_MOVED carries the new
 * position and the application's wind_set does the moving, and likewise
 * for the rest.  A press on a window that is not on top sends WM_TOPPED
 * and nothing else, as the ROM has it.
 *
 * The arrows and the slide bars are the one gadget that repeats: the
 * first WM_ARROWED goes at the press, and once the double-click time has
 * passed with the button still down, one more with every poll -- the
 * queue holds one WM_ARROWED at a time, so an application that is slow
 * to scroll is not buried.  ct_arrow_repeat is that, called from
 * event.c's ct_poll while the window manager holds the mouse.
 *
 * As in the non-3D build of the donor, only the closer and the fuller
 * are drawn selected while the button is down.
 */
#include "aes.h"
#include "proc.h"

WORD gl_ctmown;                 /* the menu has taken the mouse (ct_mouse) */
static WORD ct_tmpmoff;         /* the hide count the menu found, to put back */


/* The WM_ARROWED action for each gadget from W_UPARROW up: the slide
 * bars page, the arrows line, and W_HBAR is not a gadget at all. */
static const WORD gl_wa[] = {
    WA_UPLINE, WA_DNLINE, WA_UPPAGE, WA_DNPAGE, 0,
    WA_LFLINE, WA_RTLINE, WA_LFPAGE, WA_RTPAGE
};

/* the arrow being held */
static WORD     ct_held;
static WORD     ct_wh, ct_action;
static uint32_t ct_tick;        /* when the first WM_ARROWED went */

static void ct_msgup(PROC *to, WORD message, WORD wh, WORD m1, WORD m2,
                     WORD m3, WORD m4)
{
    if (message)
        ap_sendmsg(to, message, wh, m1, m2, m3, m4);
}

/* An arrow or slide bar pressed: the first WM_ARROWED now, the rest from
 * ct_arrow_repeat.  The update lock is dropped for the duration, as the
 * donor drops it, so the application may redraw as it scrolls. */
static void handle_arrow_msg(WORD wh, WORD gadget)
{
    wm_update(END_UPDATE);
    ct_action = gl_wa[gadget - W_UPARROW];
    ap_sendmsg(proc_app, WM_ARROWED, wh, ct_action, 0, 0, 0);
    ct_held = TRUE;
    ct_wh = wh;
    ct_tick = gl_ticks;
    wm_update(BEG_UPDATE);
}

void ct_arrow_repeat(void)
{
    if (!ct_held)
        return;
    if (!(button & 1)) {
        ct_held = FALSE;
        return;
    }
    if ((gl_ticks - ct_tick) < (uint32_t)gl_dclick)
        return;
    ap_sendmsg(proc_app, WM_ARROWED, ct_wh, ct_action, 0, 0, 0);
}

void ct_arrow_stop(void)
{
    ct_held = FALSE;
}

/* A press at (mx,my) on window wh's frame. */
static void hctl_window(WORD wh, WORD mx, WORD my)
{
    GRECT   t, f;
    WINDOW *pwin = &gl_win[wh];
    WORD    x, y, w, h;
    WORD    wm, hm;
    WORD    elev_x, elev_y;
    WORD    kind;
    WORD    cpt, message;
    WORD    gadget;
    WORD    need_normal = FALSE;

    if (wh != gl_wtop) {
        /* went down on an inactive window: tell the owner to top it */
        ct_msgup(proc_app, WM_TOPPED, wh, 0, 0, 0, 0);
        return;
    }

    message = 0;

    /* went down on the active window: handle the control points */
    w_bldactive(wh);
    gadget = cpt = ob_find(gl_awind, W_BOX, MAX_DEPTH, mx, my);
    w_getsize(WS_CURR, wh, &t);
    x = t.g_x;
    y = t.g_y;
    w = t.g_w;
    h = t.g_h;
    kind = (WORD)pwin->w_kind;

    switch (cpt) {
    case W_CLOSER:
    case W_FULLER:
        if (gr_watchbox(gl_awind, gadget, SELECTED, NORMAL)) {
            message = (cpt == W_CLOSER) ? WM_CLOSED : WM_FULLED;
            need_normal = TRUE;
        }
        break;
    case W_NAME:
        if (kind & MOVER) {
            /* the window may go off the right and the bottom, but not
             * so far that its title is out of reach */
            r_set(&f, 0, gl_hbox, gl_rscreen.g_w + w - gl_wbox - 6,
                  MAX_COORDINATE);
            gr_dragbox(w, h, x, y, &f, &x, &y);
            message = WM_MOVED;
        }
        break;
    case W_SIZER:
        if (kind & SIZER) {
            /* the second rubber box is the work area, as an offset from
             * the frame; the minimum keeps every gadget drawable */
            w_getsize(WS_WORK, wh, &t);
            t.g_x -= x;
            t.g_y -= y;
            t.g_w -= w;
            t.g_h -= h;
            wm = gl_wchar;
            hm = gl_hchar;
            if (kind & (TGADGETS | HGADGETS))
                wm = gl_wbox * 4;
            if (kind & VGADGETS)
                hm = gl_hbox * 6;
            gr_rubwind(x, y, wm, hm, &t, &w, &h);
            message = WM_SIZED;
        }
        break;
    case W_HSLIDE:
    case W_VSLIDE:
        /* W_ACTIVE is arranged so that cpt+1 is the bar's elevator:
         * before it pages one way, past it the other */
        ob_offset(gl_awind, cpt + 1, &elev_x, &elev_y);
        if (cpt == W_HSLIDE) {
            if (!(mx < elev_x))
                cpt += 1;
        } else {
            if (!(my < elev_y))
                cpt += 1;
        }
        /* fall through */
    case W_UPARROW:
    case W_DNARROW:
    case W_LFARROW:
    case W_RTARROW:
        handle_arrow_msg(wh, cpt);
        return;
    case W_HELEV:
    case W_VELEV:
        message = (cpt == W_HELEV) ? WM_HSLID : WM_VSLID;
        /* and cpt-1 is the elevator's bar */
        x = gr_slidebox(gl_awind, cpt - 1, cpt, (cpt == W_VELEV));
        break;
    }

    if (need_normal)
        ob_change(gl_awind, gadget, NORMAL, TRUE);

    ct_msgup(proc_app, message, wh, x, y, w, h);
}

/* The window manager's press at (mx,my).  The desktop's presses are the
 * application's and never come here; the menu bar's are swallowed -- a
 * menu is entered by the pointer's arrival, not by a press (hctl_rect). */
void hctl_button(WORD mx, WORD my)
{
    WORD wh;

    wh = wm_find(mx, my);
    if (wh > 0)
        hctl_window(wh, mx, my);
}

/* The pointer has come into the active menu bar with the buttons up: run
 * the menu, and tell whoever it belongs to what was chosen.
 *
 * TWO MESSAGES COME OUT OF ONE GESTURE.  An item in the Desk drop-down
 * at or below gl_dafirst is an ACCESSORY's, and it gets AC_OPEN with the
 * menu id menu_register handed out; everything else is the
 * application's MN_SELECTED.  The word layouts are not the same shape
 * and the difference is worth writing down, because two pages of the
 * Compendium get it wrong: AC_OPEN's msg[3] is the DESK TITLE's object
 * index -- 3 in every tree the RCS builds -- and the menu id is in
 * msg[4], where MN_SELECTED puts the item.
 *
 * The title is left selected for the application's menu_tnormal, except
 * for an accessory: nobody would ever call it, so the AES puts the
 * title back itself, which is what the donor does here too.
 *
 * And the mouse goes with it.  An accessory that has just been asked to
 * open is about to put something on the screen and wait for a click, so
 * it becomes the input owner (src/aes/proc.h); the application gets the
 * mouse back when the accessory has nothing on the screen any more. */
void hctl_rect(void)
{
    WORD title, item, menu;
    uint32_t mtree;

    if (!gl_mntree || !mn_do(&title, &item, &mtree, &menu))
        return;
    if (title == THEDESK && gl_accreg && item >= gl_dafirst) {
        WORD  id = (WORD)(item - gl_dafirst);
        PROC *to = mn_owner(id);

        do_chg(gl_mntree, title, SELECTED, FALSE, TRUE, TRUE);
        if (to) {
            proc_input = to;
            ct_msgup(to, AC_OPEN, title, id, 0, 0, 0);
        }
        return;
    }
    /* WORDS 5, 6 AND 7 ARE FILLED IN NOW, and they used to be zeros.
     * They are AES 4's: the tree the item came from, high word first,
     * then the box it is a child of (MULTITOS GEMCTRL.C's hctl_rect
     * splits the pointer exactly this way).  With sub-menus the item may
     * be in a tree that is not the menu bar's, and then the number on
     * its own names nothing -- so the words are not an extension here,
     * they are what makes menu_attach usable.  A program with one tree
     * and no sub-menus reads msg[4] as it always did and these are
     * simply true; appl_getinfo(AES_MENU) says they are valid. */
    ct_msgup(proc_app, MN_SELECTED, title, item,
             (WORD)(UWORD)(mtree >> 16), (WORD)(UWORD)mtree, menu);
}

/* The menu taking the mouse (grabit) and giving it back.  While it has
 * it, presses do not change the owner (event.c's bchange), and the
 * pointer is shown whatever the application's hide count -- an
 * application that hid it to draw must not have the menu run unseen --
 * and the count is put back afterwards.  The donor also swaps the
 * pointer's form for the arrow while it has it and puts the
 * application's back; not done -- no program yet reaches a menu with
 * anything but the arrow set. */
void ct_mouse(WORD grabit)
{
    if (grabit) {
        gl_ctmown = TRUE;
        ct_tmpmoff = gsx_mforce();
    } else {
        gsx_munforce(ct_tmpmoff);
        gl_ctmown = FALSE;
    }
}
