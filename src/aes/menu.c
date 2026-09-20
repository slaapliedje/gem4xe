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
/* THE FULL 24 BITS, not a near pointer.  The AES keeps this address for
 * the life of the machine and reads the string again at every redraw, so
 * it may not be bounced through abi.c's near scratch: str_used winds back
 * to 0 on the next call and the Desk menu would draw whatever landed
 * there.  A large-data accessory's title IS far -- in that model every
 * string literal is -- and this is the first thing to register one.
 * objc_draw already reads a G_STRING's spec through a far pointer
 * (expand_string, SPEC_PTR), which is what makes keeping it free. */
uint32_t gl_acctitle[MAX_ACCS];
PROC       *gl_accown[MAX_ACCS];
WORD        gl_accreg;
WORD        gl_dafirst;

/* mn_do's states: where the pointer is */
#define START_STATE     1       /* in the bar, off the titles */
#define INTITLE_STATE   2       /* on a title */
#define INITEM_STATE    3       /* on an item */
#define OUTSIDE_STATE   4       /* off the bar and the items, menu down */
#define SUBMENU_STATE   5       /* on an item of an open submenu */

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
            while (slot < MAX_ACCS && !gl_acctitle[slot])
                slot++;
            if (slot >= MAX_ACCS)
                break;
            tree[ob].ob_spec = (int32_t)gl_acctitle[slot];
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

/* ---- menu_popup -------------------------------------------------------
 *
 * A menu box put up wherever the application says, tracked, and taken
 * away again.  It is the menu bar's drop-down machinery above with the
 * bar taken out: the same menu_sr to save what it covers, the same
 * ob_draw, the same menu_select to move the highlight.
 *
 * WHAT IT IS NOT is a submenu.  The ROM's mn_popup and its submenus run
 * one shared loop (MN_EVENT.C's EvntSubMenu) and a popup can open
 * another popup from an item, up to MAX_LEVEL of them; this one cannot,
 * for the reason EmuTOS gives for its own restriction and one more of
 * gem4xe's.  bb_save is a SINGLE screen-sized shadow (graf.c) and a
 * second save over the first one's rectangle would capture the pixels
 * the first one drew, so only one of these can be open at a time.
 * appl_getinfo(AES_MENU) answers 0 for sub-menus, which is what a
 * program that cares reads.
 */

/* The box on the screen: the donor's clamp_ypos, and the same for x.
 *
 * THE ROM CLAMPS NEITHER, and that is not a contract to keep.  Its
 * AdjustMenuPosition takes a Horizontal_Flag, and the submenu path passes
 * TRUE -- flop to the other side of the item, then step right a character
 * at a time -- while mn_popup alone passes FALSE and writes ObX = xpos
 * verbatim.  A popup off the right edge is then drawn cut off and cannot
 * be used, which reads as an omission in the one caller rather than a
 * decision.  Clamping can only move a box that would have been unusable,
 * so no program that places one properly sees a difference. */
static void popup_place(OBJECT FAR *tree, WORD imenu, WORD istart,
                        WORD x, WORD y)
{
    WORD w = tree[imenu].ob_width, h = tree[imenu].ob_height;
    WORD ox, oy, bx, by;

    /* WHERE THE BOX'S PARENT BEGINS, so that everything below is in
     * SCREEN coordinates.  Both donors write ob_x and ob_y straight from
     * xpos and ypos and then clamp them against the screen, which is
     * right only while the box hangs off the root at the origin -- true
     * of a popup tree of its own, which is the usual thing, and not true
     * of a box borrowed out of a menu tree, where the drop-downs hang
     * off an IBOX below the bar.  Subtracting the parent's origin costs
     * one call and is right either way. */
    ob_offset(tree, imenu, &ox, &oy);
    ox = (WORD)(ox - tree[imenu].ob_x);
    oy = (WORD)(oy - tree[imenu].ob_y);

    /* x and y name where the START ITEM goes, not the box: the item's own
     * offset within the box comes off first (both donors do this). */
    bx = x;
    by = (WORD)(y - tree[istart].ob_y);
    while (bx + w + MENU_THICKNESS > gl_width)
        bx = (WORD)(bx - gl_wchar);
    while (bx < MENU_THICKNESS)
        bx = (WORD)(bx + gl_wchar);
    while (by > (WORD)(gl_height - h))
        by = (WORD)(by - gl_hchar);
    while (by < gl_rfull.g_y)
        by = (WORD)(by + gl_hchar);
    tree[imenu].ob_x = (WORD)(bx - ox);
    tree[imenu].ob_y = (WORD)(by - oy);
}

/* Track the box until a press: the item under the pointer, or NIL.  The
 * wait is mn_do's, one rectangle: leave the item the pointer is on, or
 * enter the box when it is outside. */
static WORD popup_track(OBJECT FAR *tree, WORD imenu, WORD istart)
{
    MOBLK m;
    WORD  rets[6];
    WORD  cur = NIL, last;
    UWORD which;

    /* The start item comes up selected, as the donor does it, so that a
     * press with no movement chooses it. */
    if (!(tree[istart].ob_state & DISABLED))
        cur = istart;
    if (cur != NIL)
        do_chg(tree, cur, SELECTED, TRUE, FALSE, TRUE);
    gsx_sclip(&gl_rzero);
    ob_draw(tree, imenu, MAX_DEPTH);

    for (;;) {
        if (cur != NIL)
            rect_change(tree, &m, cur, TRUE);       /* wait to leave it */
        else
            rect_change(tree, &m, imenu, FALSE);    /* wait to enter the box */
        which = (UWORD)ev_multi(MU_BUTTON | MU_M1, &m, 0, 0UL,
                                0x0001FF01UL, 0, rets);
        last = cur;
        cur = ob_find(tree, imenu, 1, rets[0], rets[1]);
        if (cur == imenu)               /* in the box, on no item */
            cur = NIL;
        menu_select(tree, last, cur, FALSE);
        menu_select(tree, cur, last, TRUE);
        if (which & MU_BUTTON)
            break;
    }
    /* The highlight comes off before the box does, so that the item is
     * left as the application handed it over -- a popup is put up again
     * and again out of the same tree. */
    if (cur != NIL)
        do_chg(tree, cur, SELECTED, FALSE, FALSE, FALSE);
    return cur;
}

WORD mn_popup(OBJECT FAR *tree, WORD imenu, WORD istart, WORD x, WORD y,
              WORD *pkeystate)
{
    WORD rets[6], chosen;

    /* The keystate is written whatever happens: "TOS always sets
     * mn_keystate" (EmuTOS), and the ROM says so in as many words --
     * "Always return the keystate - regardless" (MN_POPUP.C). */
    *pkeystate = 0;
    if (!tree || imenu <= 0)
        return NIL;
    if (istart < 0)
        istart = tree[imenu].ob_head;
    if (istart <= 0)
        return NIL;

    wm_update(BEG_MCTRL);
    /* The button that opened the popup is usually still down, and a press
     * is what chooses an item -- so the one that got here must be let go
     * of first, or it chooses immediately. */
    ev_button(1, 0x00FF, 0x0000, rets);

    popup_place(tree, imenu, istart, x, y);
    menu_sr(TRUE, tree, imenu);
    chosen = popup_track(tree, imenu, istart);
    menu_sr(FALSE, tree, imenu);

    *pkeystate = kstate;
    ev_button(1, 0x00FF, 0x0000, rets);
    wm_update(END_MCTRL);
    return chosen;
}

/* ---- sub-menus: menu_attach and menu_istart ---------------------------
 *
 * A menu item may carry a whole menu of its own, which opens beside it
 * while the pointer rests on it.  The AES keeps the attachment, not the
 * application: menu_attach records a (tree, box) pair against the item
 * and marks the item, and mn_do opens it.
 *
 * THE MARK IS THE ROM'S, exactly, because a resource editor and a ported
 * program both know it: a RIGHT-ARROW character written into the item's
 * own string two bytes from its end, the SUBMENU flag set in ob_flags,
 * and the slot number in the HIGH BYTE of ob_type -- which is free
 * because objc.c has always read the type as `ob_type & 0xFF`.  The ROM
 * numbers its slots from 128 and so does this, so an item marked here
 * reads the same way to anything that inspects the tree.
 *
 * WHICH MEANS IT WRITES INTO THE APPLICATION'S STRING.  The ROM does the
 * same and never checks; the landmine is that the string must be at
 * least two characters long and must be writable, and a one-character
 * item would have its NUL or the byte in front of it overwritten.  This
 * one checks the length and refuses, because the check is two lines and
 * the alternative is a corruption in somebody else's memory.
 *
 * THE LIMITS, all of them gem4xe's rather than the donor's:
 *
 *   One level.  A submenu's items cannot carry submenus of their own,
 *   and neither can a popup's.  That is EmuTOS's restriction too, and
 *   the reason here is the screen save: bb_save is one screen-sized
 *   shadow (graf.c), so two saved rectangles may not overlap, and the
 *   drop-down and its submenu are kept apart by SM_GAP for exactly that
 *   reason.  A third would have nowhere to go.
 *
 *   No scrolling.  mn_scroll is carried and ignored, as it is in
 *   menu_popup, and appl_getinfo(AES_MENU) answers 0 for it.
 */
#define SMI_BASE    128     /* ob_type's high byte: the ROM's numbering */
#define NUM_SMI     8       /* pairs one program may have attached */
#define SM_ARROW    0x03    /* the character the ROM marks an item with */
#define SM_ARROWOFF 2       /* ...written that many bytes from the end */
#define SM_GAP      (2 * MENU_THICKNESS)  /* between two saved rectangles */

/* The tree is an ADDRESS and not a pointer here.  Every other far
 * pointer in this AES is a local or a bare global; this is the one that
 * would live in a struct, and the one time a far pointer was put in a
 * struct field the value that came back out had the right offset and the
 * wrong bank, with no reduced case to explain it (src/sys/abi.c).  An
 * address costs a cast at each use and cannot go wrong that way. */
typedef struct {
    uint32_t s_tree;        /* 0 = the slot is free */
    WORD     s_menu;        /* the submenu's box object in that tree */
    WORD     s_start;       /* the item to put beside the parent item */
    WORD     s_count;       /* items pointing at this pair */
} SMI;

static SMI gl_smi[NUM_SMI];

static SMI *smi_at(WORD n)
{
    if (n < SMI_BASE || n >= SMI_BASE + NUM_SMI)
        return 0;
    return gl_smi[n - SMI_BASE].s_tree ? &gl_smi[n - SMI_BASE] : 0;
}

/* The slot an item names, out of ob_type's high byte. */
static SMI *smi_of(OBJECT FAR *tree, WORD item)
{
    if (!(tree[item].ob_flags & SUBMENU))
        return 0;
    return smi_at((WORD)((tree[item].ob_type >> 8) & 0xFF));
}

static WORD smi_slot(SMI *s)
{
    return (WORD)(SMI_BASE + (s - gl_smi));
}

/* The slot for a (tree, box) pair, or a free one, or 0. */
static SMI *smi_find(uint32_t tree, WORD imenu)
{
    WORD i;

    for (i = 0; i < NUM_SMI; i++)
        if (gl_smi[i].s_tree == tree && gl_smi[i].s_menu == imenu)
            return &gl_smi[i];
    return 0;
}

static SMI *smi_new(void)
{
    WORD i;

    for (i = 0; i < NUM_SMI; i++)
        if (!gl_smi[i].s_tree)
            return &gl_smi[i];
    return 0;
}

/* Put the arrow on the item, or a blank to take it off.
 *
 * THE STRING IS MEASURED HERE and not in a helper of its own, which is
 * what this was.  Spelled as mn_attach -> sm_mark -> sm_str, with the
 * far `tree` handed down both levels, the mark silently did not happen:
 * sm_str returned the right length and sm_mark behaved as though it had
 * not.  Any read of tree[item].ob_spec in mn_attach before the call --
 * even one whose result was thrown away -- made it work, which is the
 * signature of something going wrong in the far pointer's passage and
 * not of a bug in the arithmetic.  One level down it is right.  No
 * reduced case was made, so nothing is being claimed about the
 * compiler; what is recorded is the shape that works.
 *
 * A far string is measured WHERE IT LIES: only the two bytes at the end
 * are touched, and bringing forty characters down to count them would
 * be the expensive way to find that out.  The byte goes into a WORD
 * before it is tested, which is tools/ccbug's B16 rule. */
static WORD sm_mark(OBJECT FAR *tree, WORD item, WORD ch)
{
    uint32_t p = tree[item].ob_spec;
    WORD n;

    if (tree[item].ob_flags & INDIRECT)
        p = *(const uint32_t FAR *)(uint32_t)p;
    if (!p)
        return FALSE;
    for (n = 0; n < MAX_LEN; n++) {
        WORD c = (WORD)far_read8(p + (uint32_t)n);
        if (!c)
            break;
    }
    if (n < SM_ARROWOFF)
        return FALSE;
    far_write8(p + (uint32_t)(n - SM_ARROWOFF), (uint8_t)ch);
    return TRUE;
}

static void sm_detach(OBJECT FAR *tree, WORD item)
{
    SMI *s = smi_of(tree, item);

    sm_mark(tree, item, ' ');        /* a SPACE, as the ROM leaves it */
    tree[item].ob_type &= 0x00FF;
    tree[item].ob_flags &= ~SUBMENU;
    if (s && --s->s_count <= 0)
        s->s_tree = 0;
}

/* menu_attach.  The three flags are the ROM's bare integers, which
 * EmuTOS names ME_INQUIRE, ME_ATTACH and ME_REMOVE.  On an inquiry the
 * four words are the pair attached; on an attach they are what to
 * attach, and mn_item is clamped into the box as the ROM clamps it. */
WORD mn_attach(WORD flag, OBJECT FAR *tree, WORD item,
               uint32_t *ptree, WORD *pmenu, WORD *pitem, WORD *pscroll)
{
    SMI *s;

    if (!tree || item <= 0)
        return FALSE;
    /* A G_STRING, and only one.  The ROM tests this before anything else
     * and so does EmuTOS: the mark is a character IN THE ITEM'S TEXT,
     * and a type that does not have text has nowhere to put it. */
    if ((tree[item].ob_type & 0x00FF) != G_STRING)
        return FALSE;

    if (flag == ME_INQUIRE) {
        s = smi_of(tree, item);
        if (!s)
            return FALSE;
        *ptree = s->s_tree;
        *pmenu = s->s_menu;
        *pitem = s->s_start;
        *pscroll = 0;               /* never scrolled: see the head */
        return TRUE;
    }
    if (flag != ME_ATTACH && flag != ME_REMOVE)
        return FALSE;

    if (tree[item].ob_flags & SUBMENU)
        sm_detach(tree, item);      /* one attachment at a time */
    if (flag == ME_REMOVE)
        return TRUE;
    if (!*ptree || *pmenu <= 0)
        return FALSE;

    s = smi_find(*ptree, *pmenu);
    if (!s) {
        s = smi_new();
        if (!s)
            return FALSE;
        s->s_tree = *ptree;
        s->s_menu = *pmenu;
        s->s_count = 0;
    }
    /* The MARK LAST, so a refusal leaves the item untouched: the string
     * is the application's and a half-done attach would leave an arrow
     * on an item that carries nothing. */
    if (!sm_mark(tree, item, SM_ARROW)) {
        if (s->s_count <= 0)
            s->s_tree = 0;
        return FALSE;
    }
    {
        OBJECT FAR *st = (OBJECT FAR *)s->s_tree;
        WORD start = *pitem;
        if (start < st[s->s_menu].ob_head)
            start = st[s->s_menu].ob_head;
        if (start > st[s->s_menu].ob_tail)
            start = st[s->s_menu].ob_tail;
        s->s_start = start;
        *pitem = start;             /* the ROM writes the clamp back */
    }
    s->s_count++;
    tree[item].ob_type = (UWORD)((tree[item].ob_type & 0x00FF)
                                 | (smi_slot(s) << 8));
    tree[item].ob_flags |= SUBMENU;
    return TRUE;
}

/* menu_istart: which item of an attached submenu sits beside its parent.
 * The ROM answers the item and not a truth value, and 0 for an error --
 * which is ambiguous there and here, and harmless because object 0 is a
 * tree's root and never a menu item. */
WORD mn_istart(WORD flag, uint32_t tree, WORD imenu, WORD item)
{
    OBJECT FAR *t = (OBJECT FAR *)tree;
    SMI *s;

    if (!tree || imenu <= 0)
        return 0;
    s = smi_find(tree, imenu);
    if (!s)
        return 0;
    if (flag == MIS_INQUIRE)
        return s->s_start;
    if (flag != MIS_SET)
        return 0;
    if (item < t[imenu].ob_head)
        item = t[imenu].ob_head;
    if (item > t[imenu].ob_tail)
        item = t[imenu].ob_tail;
    s->s_start = item;
    return item;
}

/* ---- menu_settings ----------------------------------------------------
 *
 * Five numbers the AES runs its sub-menus by.  ONE OF THEM IS LIVE here
 * and four are kept and handed back, which is the whole of what this
 * machine can honestly promise -- and the live one is why the call is
 * served at all.  Before it, the submenu opened the moment the pointer
 * reached its item, EmuTOS's behaviour, and the comment here said a
 * delay nobody could change was only in the way.  menu_settings is the
 * way to change it, so the ROM's delay is back and Display sets it.
 *
 * Drag is the diagonal grace period for a pointer heading towards an
 * open submenu; there is no such tracking here.  Delay and Speed are
 * the scroll arrows' repeat, and Height where a menu starts scrolling;
 * nothing scrolls here and appl_getinfo(AES_MENU) answers 0 for it.
 * They are still STORED and still clamped as the ROM clamps them, so
 * that a program that sets one and reads it back is told the truth
 * rather than the default.
 *
 * The ROM's numbers, from MN_TOOLS.H: 200 ms, 10000 ms, 250 ms, 0 ms,
 * 16 items.  MultiTOS ships 999 for the height, meaning "never scroll",
 * and clamps it down to the screen; the Falcon's 16 is the one taken
 * here because the Falcon ROM is this project's authority. */
#define MN_INIT_DISPLAY 200L
#define MN_INIT_DRAG    10000L
#define MN_INIT_DELAY   250L
#define MN_INIT_SPEED   0L
#define MN_INIT_HEIGHT  16
#define MN_MIN_HEIGHT   5

static uint32_t mn_display, mn_drag, mn_delay, mn_speed;
static WORD     mn_height;

/* SetMaxHeight (MN_MENU.C), order and all: a height at or below the
 * minimum is raised to it, and one at or above what the screen holds is
 * cut to that -- and the second test wins when both apply, which is the
 * ROM's order and not an accident worth fixing. */
static WORD mn_clampheight(WORD h)
{
    WORD max = (WORD)((gl_rfull.g_h - gl_hchar / 2 - 1) / gl_hchar);

    if (h <= MN_MIN_HEIGHT)
        h = MN_MIN_HEIGHT;
    if (h >= max)
        h = max;
    return h;
}

void mn_defaults(void)
{
    mn_display = MN_INIT_DISPLAY;
    mn_drag    = MN_INIT_DRAG;
    mn_delay   = MN_INIT_DELAY;
    mn_speed   = MN_INIT_SPEED;
    mn_height  = MN_INIT_HEIGHT;
}

/* `set` is nine words: four LONGs low word first, then the height.  A
 * SET applies a field only when it is not negative, which is the ROM's
 * per-field "leave this one alone" and is why the block is signed. */
void mn_settings(WORD flag, WORD *set)
{
    if (flag == MNS_GET) {
        set[0] = (WORD)(UWORD)mn_display;
        set[1] = (WORD)(UWORD)(mn_display >> 16);
        set[2] = (WORD)(UWORD)mn_drag;
        set[3] = (WORD)(UWORD)(mn_drag >> 16);
        set[4] = (WORD)(UWORD)mn_delay;
        set[5] = (WORD)(UWORD)(mn_delay >> 16);
        set[6] = (WORD)(UWORD)mn_speed;
        set[7] = (WORD)(UWORD)(mn_speed >> 16);
        set[8] = mn_clampheight(mn_height);
        return;
    }
    if (flag != MNS_SET)
        return;
    if (set[1] >= 0)
        mn_display = ((uint32_t)(UWORD)set[1] << 16) | (UWORD)set[0];
    if (set[3] >= 0)
        mn_drag = ((uint32_t)(UWORD)set[3] << 16) | (UWORD)set[2];
    if (set[5] >= 0)
        mn_delay = ((uint32_t)(UWORD)set[5] << 16) | (UWORD)set[4];
    if (set[7] >= 0)
        mn_speed = ((uint32_t)(UWORD)set[7] << 16) | (UWORD)set[6];
    if (set[8] >= 0)
        mn_height = mn_clampheight(set[8]);
}

/* Open the submenu attached to `item`, beside it; its tree's address, or
 * 0 if there is nowhere to put it.  *psmroot gets its box.
 *
 * TO THE RIGHT, WITH A GAP, flopped to the left when there is no room.
 * The ROM tucks the box UNDER the item by a character so the two touch
 * (MN_MENU.C's ShowSubMenu, and EmuTOS copies it); here they must not
 * touch at all, because bb_save is ONE screen-sized shadow (graf.c) and
 * a second saved rectangle overlapping the first captures the pixels the
 * first one drew -- restoring the drop-down would then paint the
 * submenu's own border back onto the screen.  SM_GAP is the two pixels
 * menu_sr adds to each box, and the cost is a submenu two pixels further
 * out than an ST's.  Where neither side has room the submenu does not
 * open, which is a refusal and not a corruption.
 *
 * NO GATE CAN FALSIFY THAT, and it was tried: with SM_GAP set to 0 on
 * BOTH sides test-m9 stays green, because tools/aesref.py models the
 * same single shadow at the same coordinates and loses the same pixels.
 * A comparison cannot see a fault both sides have.  What would see it is
 * an invariant rather than a comparison -- the screen after the menu
 * equals the screen before it -- and m9 does not check that.  So the
 * reason for the gap is read out of graf.c and is not gated; setting it
 * to 0 changes only where the box lands, which IS gated. */
static uint32_t sm_show(OBJECT FAR *tree, WORD item, WORD *psmroot)
{
    SMI *s = smi_of(tree, item);
    OBJECT FAR *st;
    GRECT r;
    WORD w, h, ox, oy, bx, by;

    if (!s)
        return 0;
    st = (OBJECT FAR *)s->s_tree;
    ob_actxywh(tree, item, &r);
    w = st[s->s_menu].ob_width;
    h = st[s->s_menu].ob_height;
    ob_offset(st, s->s_menu, &ox, &oy);
    ox = (WORD)(ox - st[s->s_menu].ob_x);
    oy = (WORD)(oy - st[s->s_menu].ob_y);

    bx = (WORD)(r.g_x + r.g_w + SM_GAP);
    if (bx + w + MENU_THICKNESS > gl_width)
        bx = (WORD)(r.g_x - w - SM_GAP);    /* flop to the other side */
    if (bx < MENU_THICKNESS)
        return 0;                           /* and no room there either */
    by = (WORD)(r.g_y - st[s->s_start].ob_y);
    while (by > (WORD)(gl_height - h))
        by = (WORD)(by - gl_hchar);
    while (by < gl_rfull.g_y)
        by = (WORD)(by + gl_hchar);
    st[s->s_menu].ob_x = (WORD)(bx - ox);
    st[s->s_menu].ob_y = (WORD)(by - oy);

    menu_sr(TRUE, st, s->s_menu);
    gsx_sclip(&gl_rzero);
    ob_draw(st, s->s_menu, MAX_DEPTH);
    *psmroot = s->s_menu;
    return s->s_tree;
}

static void sm_hide(OBJECT FAR *tree, WORD item)
{
    SMI *s = smi_of(tree, item);

    if (s)
        menu_sr(FALSE, (OBJECT FAR *)s->s_tree, s->s_menu);
}

/* Does this item open one?  Enabled, marked, and with a slot behind the
 * mark -- an item whose slot was freed is still marked and must not. */
static WORD sm_opens(OBJECT FAR *tree, WORD item)
{
    if (item == NIL || (tree[item].ob_state & DISABLED))
        return FALSE;
    return smi_of(tree, item) != 0;
}

/* Run the menu bar from the pointer's arrival in it until a button
 * transition ends it or the pointer leaves with nothing down.  TRUE with
 * the title and item when an enabled item was chosen.  The button's
 * state is left as it is: the control manager holds the mouse until it
 * is up (event.c). */
WORD mn_do(WORD *ptitle, WORD *pitem, uint32_t *ptree, WORD *pmenu)
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
    OBJECT FAR *tree, *p1tree;
    uint32_t buparm, smtree = 0;
    WORD    mnu_flags, done, main_rect;
    WORD    cur_menu, cur_item, last_item;
    WORD    cur_title, last_title;
    WORD    cur_sub, last_sub, smparent, smroot, smnoroom;
    uint32_t tmout;
    UWORD   ev_which;
    MOBLK   p1mor, p2mor;
    WORD    menu_state, leave_flag;
    WORD    rets[6];

    menu_state = START_STATE;
    done = FALSE;
    buparm = 0x00010101UL;              /* a press */
    cur_title = cur_menu = cur_item = NIL;
    cur_sub = smparent = smnoroom = NIL;
    smroot = 0;
    tree = gl_mntree;

    ct_mouse(TRUE);

    while (!done) {
        p1tree = tree;                  /* the submenu's state overrides it */
        mnu_flags = MU_BUTTON | MU_M1;
        tmout = 0;

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
            /* AND THE DISPLAY DELAY, if this item has a menu of its own
             * that is not up yet: the ROM waits SUBMENU_DELAY before
             * opening one (MN_EVENT.C), so that running the pointer down
             * a drop-down does not flash every submenu on the way past.
             * menu_settings is what changes it. */
            if (!smtree && cur_item != smnoroom && sm_opens(tree, cur_item)) {
                mnu_flags |= MU_TIMER;
                tmout = mn_display;
            }
            main_rect = cur_item;
            buparm = (button & 0x0001) ? 0x00010100UL : 0x00010101UL;
            leave_flag = TRUE;
            break;
        case SUBMENU_STATE:
            /* the pointer off the SUBMENU's item, in the submenu's tree */
            p1tree = (OBJECT FAR *)smtree;
            main_rect = cur_sub;
            buparm = (button & 0x0001) ? 0x00010100UL : 0x00010101UL;
            leave_flag = TRUE;
            break;
        default:                        /* INTITLE_STATE */
            main_rect = cur_title;
            leave_flag = TRUE;
            break;
        }
        rect_change(p1tree, &p1mor, main_rect, leave_flag);

        /* TWO RECTANGLES AND NOT THREE.  EmuTOS's menu loop arms a
         * third for "the pointer enters the submenu", because its
         * submenu overlaps the parent item by a character and the
         * pointer can therefore be in both.  Here they are SM_GAP apart
         * -- the save buffer requires it -- so entering the submenu
         * always means leaving the item, and leaving the item is what
         * MU_M1 already watches for.  A third was built, and taking it
         * out again changed nothing this gate can see, which is what
         * says it was not reached. */
        ev_which = ev_multi(mnu_flags, &p1mor, &p2mor, tmout, buparm, 0, rets);

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
        last_sub = cur_sub;

        /* where the pointer is now */
        cur_title = ob_find(tree, THEACTIVE, 1, rets[0], rets[1]);
        if (cur_title != NIL && cur_title != THEACTIVE) {
            menu_state = INTITLE_STATE;
            cur_item = NIL;
            cur_sub = NIL;
        } else {
            cur_title = last_title;
            if (cur_menu == NIL)        /* no menu ever shown: nothing */
                cur_title = NIL;
            if (cur_title == NIL) {
                done = TRUE;
            } else {
                /* THE SUBMENU IS ASKED FIRST, and cur_item is left alone
                 * when the pointer is in it: the parent item has to stay
                 * selected while its own menu is open, and it is also
                 * what says which submenu is showing. */
                cur_sub = smtree ? ob_find((OBJECT FAR *)smtree, smroot, 1,
                                           rets[0], rets[1]) : NIL;
                if (cur_sub == smroot)
                    cur_sub = NIL;      /* in the box, on no item */
                if (cur_sub != NIL) {
                    menu_state = SUBMENU_STATE;
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
        }

        /* The order is inside out: the submenu's highlight, then the
         * submenu itself, then the item, then the title and its menu --
         * so that a box is never taken off the screen while something
         * drawn on top of it is still there. */
        if (smtree)
            menu_select((OBJECT FAR *)smtree, last_sub, cur_sub, FALSE);
        if (smtree && cur_item != smparent) {
            sm_hide(tree, smparent);
            smtree = 0;
            smparent = NIL;
            cur_sub = last_sub = NIL;
        }
        menu_select(tree, last_item, cur_item, FALSE);
        if (menu_select(tree, last_title, cur_title, FALSE))
            menu_sr(FALSE, tree, cur_menu);
        if (menu_select(tree, cur_title, last_title, TRUE))
            cur_menu = menu_down(tree, cur_title);
        menu_select(tree, cur_item, last_item, TRUE);
        /* The submenu opens AT ONCE and not after a delay.  The ROM arms
         * a timer with SUBMENU_DELAY (200 ms, menu_settings); EmuTOS
         * opens it straight away and so does this, because nothing here
         * serves menu_settings and a delay nobody can change is a delay
         * that is only in the way. */
        /* ...AND ONLY WHEN THE DELAY HAS RUN OUT.  MU_TIMER is armed in
         * INITEM_STATE above and nowhere else, so this opens on the tick
         * and not on the move that arrived first.  An item whose submenu
         * has nowhere to go is remembered, or the timer would re-arm on
         * it for as long as the pointer stayed there. */
        if ((ev_which & MU_TIMER) && !smtree && sm_opens(tree, cur_item)) {
            smtree = sm_show(tree, cur_item, &smroot);
            if (smtree)
                smparent = cur_item;
            else
                smnoroom = cur_item;
        }
        if (smtree)
            menu_select((OBJECT FAR *)smtree, cur_sub, last_sub, TRUE);
    }

    /* Clean up: the menu up, and the item reported only if it is one
     * and enabled -- then the title stays selected for the application
     * to menu_tnormal, else it is deselected here. */
    done = FALSE;
    *ptree = (uint32_t)tree;
    *pmenu = cur_menu;
    if (cur_title != NIL) {
        if (smtree) {
            sm_hide(tree, smparent);
            if (cur_sub != NIL)
                do_chg((OBJECT FAR *)smtree, cur_sub, SELECTED, FALSE,
                       FALSE, FALSE);
        }
        menu_sr(FALSE, tree, cur_menu);
        /* THE ITEM MAY BE IN THE SUBMENU'S TREE, which is why mn_do says
         * which tree at all: with sub-menus an object number on its own
         * no longer names one thing, and the caller would look it up in
         * the menu bar's tree and find something else.  Those are
         * MN_SELECTED's words 5, 6 and 7 (ctrl.c). */
        if (smtree && cur_sub != NIL
            && do_chg((OBJECT FAR *)smtree, cur_sub, SELECTED, FALSE,
                      FALSE, TRUE)) {
            *ptitle = cur_title;
            *pitem = cur_sub;
            *ptree = smtree;
            *pmenu = smroot;
            done = TRUE;
        } else if (!smtree && cur_item != NIL
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
WORD mn_register(WORD pid, uint32_t pstr)
{
    WORD slot;

    if (pid < 0 || gl_accreg >= MAX_ACCS)
        return -1;
    for (slot = 0; slot < MAX_ACCS; slot++)
        if (!gl_acctitle[slot])
            break;
    if (slot >= MAX_ACCS)
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

    for (i = 0; i < MAX_ACCS; i++)
        if (gl_accown[i])
            ap_sendmsg(gl_accown[i], AC_CLOSE, i, 0, 0, 0, 0);
}

/* The process that registered slot `id`, and 0 for a slot nobody has. */
PROC *mn_owner(WORD id)
{
    if (id < 0 || id >= MAX_ACCS)
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

    for (i = 0; i < MAX_ACCS; i++) {
        gl_acctitle[i] = 0;
        gl_accown[i] = 0;
    }
    gl_accreg = 0;
    gl_dafirst = 0;
    mn_defaults();
}

/* No bar; the wake rectangle is the menu bar's row, after gsx_start has
 * measured it. */
void mn_init(void)
{
    gl_mntree = 0;
    gl_ctwait.m_out = FALSE;
    gl_ctwait.m_gr = gl_rmenu;
}
