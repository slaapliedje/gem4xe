/* menu.c -- the AES menu library (EmuTOS aes/gemmnlib.c, without the
 * submenu extension).
 *
 * A menu tree is the shape the RCS builds and the AES trusts: the root
 * has two children, the bar (THEBAR) and the box of drop-downs; the bar
 * holds THEACTIVE, whose children are the titles in order; the drop-down
 * box's children are the drop-downs in the same order, the first the
 * Desk menu (THEDESK is its title), whose children the AES rebuilds to
 * fit the accessories -- none here, so it keeps the one "About" item
 * and its separator goes.  A title's drop-down is found by walking as
 * many siblings as the title is titles in (menu_sub): the titles must
 * be contiguous in the array, the items may be anywhere.
 *
 * mn_do is the state machine that runs a drop-down: it is entered by
 * the control manager when the pointer comes into the active bar with
 * the buttons up (event.c's ct_poll), takes the mouse (ct_mouse), and
 * pulls each menu down as the pointer crosses its title, saving what is
 * under it with bb_save and putting it back with bb_restore.  It leaves
 * on a button transition off the title, reporting the item if one is
 * under the pointer and enabled; the control manager sends MN_SELECTED.
 * The bar and the drop-downs are drawn with the clip off (gl_rzero) as
 * the donor draws them: they are outside every window.
 *
 * WHAT IS NOT HERE: accessories (menu_register returns -1), the Atari
 * corpus's later hierarchical menus, and the ROM's 25-column save
 * buffer with its overflow on a wide drop-down -- the VDI's save buffer
 * is a whole screen (vdi_save_form).  The other corpus landmine stands:
 * the save rectangle is the drop-down grown by MENU_THICKNESS and NOT
 * clipped by the donor, so a drop-down off an edge of the screen is the
 * RCS's fix_menu_bar's job to prevent; here the VDI clips the copy to
 * the screen (vro_cpyfm, source-clipped), so the cost is a stripe left
 * unrestored, not a crash.
 */
#include <string.h>
#include "portab.h"
#include "aes.h"
#include "proc.h"
#include "sys/farmem.h"

#define MENU_THICKNESS  1       /* the frame bb_save keeps around a drop-down */

/* The accessories' names and who registered them, by slot; gl_dafirst is
 * where the first of them lands in the tree, which is what makes a click
 * on one into a menu id.  Registrations outlive every application: the
 * donor's mn_init runs once at AES start-up, before the accessories are
 * loaded, and never again. */
const char *gl_acctitle[NUM_ACCS];
PROC       *gl_accown[NUM_ACCS];
WORD        gl_accreg;
WORD        gl_dafirst;

/* mn_do's states: where the pointer is */
#define START_STATE     1       /* in the bar, off the titles */
#define INTITLE_STATE   2       /* on a title */
#define INITEM_STATE    3       /* on an item */
#define OUTSIDE_STATE   4       /* off the bar and the items, menu down */

OBJECT FAR *gl_mntree;              /* the menu bar showing, or 0 */
MOBLK   gl_ctwait;              /* the rectangle that wakes the menu: the
                                 * active bar while there is one, else
                                 * gl_rmenu (which nothing enters, as a
                                 * press there goes to the control
                                 * manager before the menu could) */

/* The drop-down for a title: the titles and the drop-downs are children
 * of THEACTIVE and of the box after the bar, in the same order. */
static WORD menu_sub(OBJECT FAR *tree, WORD ititle)
{
    WORD themenus, imenu, i;

    themenus = tree[THESCREEN].ob_tail;
    imenu = tree[themenus].ob_head;
    for (i = ititle - THEACTIVE; i > 1; i--)
        imenu = tree[imenu].ob_next;
    return imenu;
}

/* Rebuild the Desk drop-down's chain for the accessories that have
 * registered a name: the application's "About" item, then -- if there
 * are any -- the separator and one item per name, in slot order.  The
 * items are the RCS's own, at dabox+1..dabox+8, and the chain is
 * destroyed and rebuilt BY INDEX, which is why the resource must carry
 * exactly eight children of the Desk box whether they are used or not
 * (tools/deskrsc.py; the invariant is the donor's, and one child short
 * makes the sixth accessory's ob_add walk into the File drop-down).
 *
 * The height is recomputed and the WIDTH IS NOT, which is the donor's
 * behaviour and not an omission: a title too long for the box the
 * resource drew is clipped, and the resource is where its width is
 * decided.  gl_dafirst is the object index the first name landed on,
 * which is what turns a click into a menu id (ctrl.c). */
static void menu_fixup(void)
{
    OBJECT FAR *tree = gl_mntree;
    WORD themenus, dabox, cnt, i, slot, ob, height;

    if (tree == 0)
        return;
    themenus = tree[THESCREEN].ob_tail;
    dabox = tree[themenus].ob_head;
    tree[dabox].ob_head = tree[dabox].ob_tail = NIL;
    gl_dafirst = dabox + 3;

    cnt = gl_accreg ? (WORD)(2 + gl_accreg) : 1;
    slot = 0;
    height = 0;
    for (i = 1; i <= cnt; i++) {
        ob = dabox + i;
        ob_add(tree, dabox, ob);
        if (i > 2) {                    /* the names, after the separator */
            while (slot < NUM_ACCS && !gl_acctitle[slot])
                slot++;
            if (slot >= NUM_ACCS)
                break;
            tree[ob].ob_spec = (int32_t)(uint16_t)gl_acctitle[slot];
            slot++;
        }
        height += gl_hchar;
    }
    tree[dabox].ob_height = height;
}

/* A mouse rectangle wait on an object: leave it if x, else enter it. */
static void rect_change(OBJECT FAR *tree, MOBLK *prmob, WORD iob, WORD x)
{
    ob_actxywh(tree, iob, &prmob->m_gr);
    prmob->m_out = x;
}

/* Set or clear a state bit on an object, redrawing it with the clip off
 * if dodraw; FALSE, and nothing done, when chkdisabled and the object is
 * disabled.  The menu_icheck/ienable/tnormal calls come here directly. */
WORD do_chg(OBJECT FAR *tree, WORD iitem, UWORD chgvalue, WORD dochg,
            WORD dodraw, WORD chkdisabled)
{
    UWORD curr_state;

    curr_state = tree[iitem].ob_state;
    if (chkdisabled && (curr_state & DISABLED))
        return FALSE;
    if (dochg)
        curr_state |= chgvalue;
    else
        curr_state &= ~chgvalue;
    if (dodraw)
        gsx_sclip(&gl_rzero);
    ob_change(tree, iitem, curr_state, dodraw);
    return TRUE;
}

static WORD item_changed(WORD last_item, WORD cur_item)
{
    if (last_item == NIL)
        return FALSE;
    if (last_item == cur_item)
        return FALSE;
    return TRUE;
}

/* Select or deselect last_item, if it is something and not cur_item.
 * Called with the two swapped to select the new one: then it is "the new
 * one, if it is something and not the old one". */
static WORD menu_select(OBJECT FAR *tree, WORD last_item, WORD cur_item,
                        WORD setit)
{
    if (item_changed(last_item, cur_item))
        return do_chg(tree, last_item, SELECTED, setit, TRUE, TRUE);
    return FALSE;
}

/* Save or restore what is under a drop-down, one pixel of frame
 * included on the left, right and bottom. */
static void menu_sr(WORD saveit, OBJECT FAR *tree, WORD imenu)
{
    GRECT t;

    gsx_sclip(&gl_rzero);
    ob_actxywh(tree, imenu, &t);
    t.g_x -= MENU_THICKNESS;
    t.g_w += 2 * MENU_THICKNESS;
    t.g_h += 2 * MENU_THICKNESS;
    if (saveit)
        bb_save(&t);
    else
        bb_restore(&t);
}

/* Pull a title's menu down: the title selected, the screen under the
 * drop-down saved, the drop-down drawn.  A disabled title gets none of
 * it.  Returns the drop-down's object. */
static WORD menu_down(OBJECT FAR *tree, WORD ititle)
{
    WORD imenu;

    imenu = menu_sub(tree, ititle);
    if (do_chg(tree, ititle, SELECTED, TRUE, TRUE, TRUE)) {
        menu_sr(TRUE, tree, imenu);
        ob_draw(tree, imenu, MAX_DEPTH);
    }
    return imenu;
}

/* Run the menu bar from the pointer's arrival in it until a button
 * transition ends it or the pointer leaves with nothing down.  TRUE with
 * the title and item when an enabled item was chosen.  The button's
 * state is left as it is: the control manager holds the mouse until it
 * is up (event.c). */
WORD mn_do(WORD *ptitle, WORD *pitem)
{
    /* FAR, because gl_mntree is: a menu tree can live in far memory now
     * (docs/far-trees.md), and a near slot here truncated it to sixteen
     * bits SILENTLY.  Every tree in this tree's own world is in the
     * bank-$00 pool, where the truncation loses nothing, so it went
     * unseen through step 1 and forty gates; QED is the first program
     * whose resource -- and so whose menu bar -- is in far memory, and
     * its menu would not drop: the bar drew (objc_draw takes FAR), then
     * ob_find and rect_change here were handed a bank-$00 address that
     * was never a tree.  Everything this passes tree to already takes
     * OBJECT FAR *. */
    OBJECT FAR *tree;
    uint32_t buparm;
    WORD    mnu_flags, done, main_rect;
    WORD    cur_menu, cur_item, last_item;
    WORD    cur_title, last_title;
    UWORD   ev_which;
    MOBLK   p1mor, p2mor;
    WORD    menu_state, leave_flag;
    WORD    rets[6];

    menu_state = START_STATE;
    done = FALSE;
    buparm = 0x00010101UL;              /* a press */
    cur_title = cur_menu = cur_item = NIL;
    tree = gl_mntree;

    ct_mouse(TRUE);

    while (!done) {
        mnu_flags = MU_BUTTON | MU_M1;

        switch (menu_state) {
        case START_STATE:
            /* the pointer into the titles, or out of the bar */
            mnu_flags |= MU_M2;
            rect_change(tree, &p2mor, THEBAR, TRUE);
            main_rect = THEACTIVE;
            leave_flag = FALSE;
            break;
        case OUTSIDE_STATE:
            /* the pointer into the titles, or into the drop-down */
            mnu_flags |= MU_M2;
            rect_change(tree, &p2mor, cur_menu, FALSE);
            main_rect = THEACTIVE;
            leave_flag = FALSE;
            break;
        case INITEM_STATE:
            /* the pointer off the item; the button the other way */
            main_rect = cur_item;
            buparm = (button & 0x0001) ? 0x00010100UL : 0x00010101UL;
            leave_flag = TRUE;
            break;
        default:                        /* INTITLE_STATE */
            main_rect = cur_title;
            leave_flag = TRUE;
            break;
        }
        rect_change(tree, &p1mor, main_rect, leave_flag);

        ev_which = ev_multi(mnu_flags, &p1mor, &p2mor, 0UL, buparm, 0, rets);

        /* A button: in the bar off the titles it is nothing.  On a title
         * it flips the state waited for and the menu goes on.  Anywhere
         * else it ends the menu. */
        if (ev_which & MU_BUTTON) {
            if (menu_state == START_STATE)
                continue;
            if (menu_state != INTITLE_STATE)
                break;
            buparm ^= 0x00000001UL;
        }

        last_title = cur_title;
        last_item = cur_item;

        /* where the pointer is now */
        cur_title = ob_find(tree, THEACTIVE, 1, rets[0], rets[1]);
        if (cur_title != NIL && cur_title != THEACTIVE) {
            menu_state = INTITLE_STATE;
            cur_item = NIL;
        } else {
            cur_title = last_title;
            if (cur_menu == NIL)        /* no menu ever shown: nothing */
                cur_title = NIL;
            if (cur_title == NIL) {
                done = TRUE;
            } else {
                cur_item = ob_find(tree, cur_menu, 1, rets[0], rets[1]);
                if (cur_item != NIL) {
                    menu_state = INITEM_STATE;
                } else if (tree[cur_title].ob_state & DISABLED) {
                    cur_title = NIL;
                    done = TRUE;
                } else {
                    menu_state = OUTSIDE_STATE;
                }
            }
        }

        /* the old item off; the old title off and its menu up; the new
         * title on and its menu down; the new item on */
        menu_select(tree, last_item, cur_item, FALSE);
        if (menu_select(tree, last_title, cur_title, FALSE))
            menu_sr(FALSE, tree, cur_menu);
        if (menu_select(tree, cur_title, last_title, TRUE))
            cur_menu = menu_down(tree, cur_title);
        menu_select(tree, cur_item, last_item, TRUE);
    }

    /* Clean up: the menu up, and the item reported only if it is one
     * and enabled -- then the title stays selected for the application
     * to menu_tnormal, else it is deselected here. */
    done = FALSE;
    if (cur_title != NIL) {
        menu_sr(FALSE, tree, cur_menu);
        if (cur_item != NIL
            && do_chg(tree, cur_item, SELECTED, FALSE, FALSE, TRUE)) {
            *ptitle = cur_title;
            *pitem = cur_item;
            done = TRUE;
        } else {
            do_chg(tree, cur_title, SELECTED, FALSE, TRUE, TRUE);
        }
    }

    ct_mouse(FALSE);
    return done;
}

/* menu_bar: show the bar -- the tree fixed up for the accessories, the
 * bar object stretched to the right edge, drawn with the clip off, and
 * the line under it drawn black in replace mode whatever the tree says
 * -- or hide it, which is only to forget it: the application redraws. */
void mn_bar(OBJECT FAR *tree, WORD showit)
{
    if (showit) {
        gl_mntree = tree;
        menu_fixup();
        tree[THEBAR].ob_width = gl_width - tree[THEBAR].ob_x;
        ob_actxywh(tree, THEACTIVE, &gl_ctwait.m_gr);
        gsx_sclip(&gl_rzero);
        ob_draw(tree, THEBAR, MAX_DEPTH);
        gsx_attr(FALSE, MD_REPLACE, BLACK);
        gsx_cline(0, gl_hbox - 1, gl_width - 1, gl_hbox - 1);
    } else {
        gl_mntree = 0;
        gl_ctwait.m_gr = gl_rmenu;
    }
}

/* menu_text: a new string for an item, copied over the old one, which
 * the caller made long enough.
 *
 * THE DESTINATION IS FAR, because the tree is: ob_spec is a 32-bit GEM
 * address and a menu whose resource went to far memory has a real
 * 24-bit one there (docs/far-trees.md).  `(char *)(uint16_t)ob_spec`
 * kept the offset and threw the BANK away, and since far_alloc hands out
 * whole banks the offset is the string's offset in the .RSC file -- so
 * the copy landed in bank $00 at that address, on top of whatever is
 * there.  Under SpartaDOS X that is the DOS: QED's "  Makefile..." (file
 * offset $08C4) overwrote $0008C4, four bytes into the stub SDX calls to
 * read a DIRECTORY, whose `jsr` then ran into a BRK.  The symptom was a
 * file selector that drew and then hung the machine -- three removes from
 * the menu call that did it, and nowhere near the selector.
 *
 * far_strput rather than a walked pointer: far pointer arithmetic is
 * 16 bits on this compiler and does not carry into the bank byte
 * (tools/ccbug), so a string near the top of a bank would wrap. */
void mn_text(OBJECT FAR *tree, WORD item, const char *text)
{
    uint32_t d = (uint32_t)tree[item].ob_spec;

    far_strput(d, text, (uint16_t)(strlen(text) + 1));
}

/* menu_register: a name in the Desk menu, and the menu id that will come
 * back in the AC_OPEN when it is chosen.  -1 when the slots are full,
 * which is also what a caller that is not a process gets.
 *
 * THE STRING IS NOT COPIED.  The pointer is kept and goes straight into
 * an object's ob_spec, which is what the donor does and says so ("save
 * pointer, like Atari TOS"): an accessory's title has to be in memory
 * that lives as long as the accessory, and an accessory that frees it
 * has put a dangling pointer in the menu.  Since an accessory takes all
 * its bank $00 memory before the first program is loaded (src/aes/shel.c)
 * and never gives it back, that is a rule it cannot easily break here.
 *
 * The id is the SLOT, found by looking for a free one rather than by
 * counting registrations, so that six ids stay six ids however they were
 * handed out.  The owner recorded is the CALLER, not the pid it names --
 * again the donor's: pid is a sanity check and nothing more, since the
 * only process that can ask is the one running. */
WORD mn_register(WORD pid, const char *pstr)
{
    WORD slot;

    if (pid < 0 || gl_accreg >= NUM_ACCS)
        return -1;
    for (slot = 0; slot < NUM_ACCS; slot++)
        if (!gl_acctitle[slot])
            break;
    if (slot >= NUM_ACCS)
        return -1;
    gl_acctitle[slot] = pstr;
    gl_accown[slot] = rlr;
    gl_accreg++;
    menu_fixup();
    return slot;
}

/* AC_CLOSE to every registered accessory, whether it has anything open
 * or not -- the donor's mn_cleanup, and it goes to all of them for the
 * reason the donor's does: the message does not mean "the user closed
 * you".  It means the application that was running has terminated and
 * its memory is about to be reclaimed, so anything the accessory took
 * while that application was alive has to go back now.
 *
 * The accessory must NOT close its own windows.  The AES does that --
 * here in the shell loop's wm_init(), which destroys every window
 * whoever owns it, exactly as the donor's wm_new does -- and a handle
 * kept across an AC_CLOSE is a handle to a window that no longer
 * exists.  The Compendium says the same in one line: "Do not close any
 * windows your accessory had open, the system will do this for you."
 *
 * msg[3] is the MENU ID, where AC_OPEN puts it in msg[4].  The asymmetry
 * is the donor's and both sources agree on it. */
void mn_cleanup(void)
{
    WORD i;

    for (i = 0; i < NUM_ACCS; i++)
        if (gl_accown[i])
            ap_sendmsg(gl_accown[i], AC_CLOSE, i, 0, 0, 0, 0);
}

/* The process that registered slot `id`, and 0 for a slot nobody has. */
PROC *mn_owner(WORD id)
{
    if (id < 0 || id >= NUM_ACCS)
        return 0;
    return gl_accown[id];
}

/* Once per AES start-up, before any accessory is loaded: the Desk menu's
 * registrations, forgotten.
 *
 * This is a SPLIT the donor does not need and gem4xe does.  There,
 * mn_init() is called once, from geminit, and the registry is simply
 * part of it; here mn_init() is called again by the shell loop between
 * every two programs (src/aes/shel.c), because the window and menu state
 * of the program that has just gone has to go with it.  An accessory's
 * name must NOT go with it -- the accessory is still there -- so the
 * registry moved to the half that happens once.  The gate said so before
 * the reasoning did: test-m9 runs four cases against one live AES, and
 * the target kept case 0's registration into case 1 while the model,
 * built fresh per case, did not. */
void mn_start(void)
{
    WORD i;

    for (i = 0; i < NUM_ACCS; i++) {
        gl_acctitle[i] = 0;
        gl_accown[i] = 0;
    }
    gl_accreg = 0;
    gl_dafirst = 0;
}

/* No bar; the wake rectangle is the menu bar's row, after gsx_start has
 * measured it. */
void mn_init(void)
{
    gl_mntree = 0;
    gl_ctwait.m_out = FALSE;
    gl_ctwait.m_gr = gl_rmenu;
}
