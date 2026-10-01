/* desktop.c -- DESKTOP.PRG, the GEM Desktop.
 *
 * A gem4xe application like any other (src/app/gem.h): the shell loop
 * in src/aes/shel.c loads it first, runs whatever it asks for with
 * shel_write, and loads it again when that returns, until it asks to
 * shut down.  The shape is the donor's deskmain.c: take the desk over
 * with a screen tree of drive icons and the trash, put the menu bar
 * up, and answer evnt_multi until Quit.
 *
 * Milestone 4 of docs/phase14.md was the bar, the icons, the About
 * dialog, Quit, and an icon that selects when clicked; milestone 5 the
 * folder windows (deskwin.c) a double-click on a drive icon opens;
 * milestone 6 a program run from its icon -- the desktop exits with
 * its windows' places in the shell buffer, and opens them again when
 * the shell loads it back; milestone 7 New folder and Delete
 * (deskfun.c), the first things the desktop does TO a disk; then the
 * drag that copies or moves, and Show info, which is also the rename.
 * The items of later milestones are in the menu, disabled, until the
 * milestone that brings them (NOT_YET_ITEMS, build/deskrsc.h).
 */
#include "desk.h"

GLOBES G;

/* -- dialogs ----------------------------------------------------------- */

static GRECT dlg;

static void start_dialog(OBJECT *tree)
{
    form_center(tree, &dlg.g_x, &dlg.g_y, &dlg.g_w, &dlg.g_h);
    form_dial(FMD_START, 0, 0, 0, 0, dlg.g_x, dlg.g_y, dlg.g_w, dlg.g_h);
    objc_draw(tree, ROOT, MAX_DEPTH, dlg.g_x, dlg.g_y, dlg.g_w, dlg.g_h);
}

static void end_dialog(void)
{
    form_dial(FMD_FINISH, 0, 0, 0, 0, dlg.g_x, dlg.g_y, dlg.g_w, dlg.g_h);
}

void desk_busy(WORD on)
{
    wind_update(BEG_UPDATE);
    graf_mouse(on ? HOURGLASS : ARROW, 0);
    wind_update(END_UPDATE);
}

/* -- the desk ---------------------------------------------------------- */

/* The donor's snap_icon: grid position (gx, gy) as a pixel position,
 * the spare pixels shared out between the columns and the rows. */
static void snap_icon(WORD gx, WORD gy, WORD *px, WORD *py)
{
    WORD columns = G.g_desk.g_w / G.g_icw;
    WORD rows = G.g_desk.g_h / G.g_ich;
    WORD spare;
    /* Clamped into fresh locals, not back into the parameters: cc65816
     * 5.18 at -O2 inlines this into desk_icon and, with the parameters
     * reassigned, reads both of them back from a stack slot it never
     * wrote (tools/ccbug/bugs.c, B10).  The first icon came out right only
     * because that slot happened to hold zero. */
    WORD cx = gx > columns - 1 ? (WORD)(columns - 1) : gx;
    WORD cy = gy > rows - 1 ? (WORD)(rows - 1) : gy;

    spare = (WORD)(G.g_desk.g_w - columns * G.g_icw);
    *px = (WORD)(cx * G.g_icw + spare / columns);
    spare = (WORD)(G.g_desk.g_h - rows * G.g_ich);
    *py = (WORD)(cy * G.g_ich + spare / rows + G.g_desk.g_y);
}

/* An icon on the desk at grid (gx, gy). */
static WORD desk_icon(WORD gx, WORD gy, WORD which, const char *label, WORD letter)
{
    WORD x, y;

    snap_icon(gx, gy, &x, &y);
    return obj_icon(DROOT, x, y, which, label, letter);
}

/* The desk: a disk icon per drive in GEMDOS's map, floppies for the
 * first two, across the top from the left; the trash bottom-left, or
 * bottom-right when the disks reach that row (the donor's build_inf). */
static void desk_build(void)
{
    WORD xcnt, ycnt, drive, n, gx, gy;
    char label[LABEL_LEN];
    char *disk, *trash;
    UWORD map;

    G.g_wicon = (WORD)(MAX_ICONTEXT_WIDTH * G.g_wchar + 2 * G.a_iblist[0].ib_xtext);
    G.g_hicon = (WORD)(G.a_iblist[0].ib_hicon + G.g_hchar + 2);
    xcnt = G.g_desk.g_w / (G.g_wicon + MIN_WINT);
    G.g_icw = G.g_desk.g_w / xcnt;
    ycnt = G.g_desk.g_h / (G.g_hicon + MIN_HINT);
    G.g_ich = G.g_desk.g_h / ycnt;

    obj_wfree(DROOT, 0, 0, (WORD)(G.g_desk.g_x + G.g_desk.g_w),
              (WORD)(G.g_desk.g_y + G.g_desk.g_h));
    G.g_screen[DROOT].ob_spec.index = DESK_SPEC;

    rsrc_gaddr(R_STRING, STDISK, (void **)&disk);
    rsrc_gaddr(R_STRING, STTRASH, (void **)&trash);

    map = (UWORD)Dsetdrv(Dgetdrv());
    gx = gy = 0;
    for (drive = 0, n = 0; drive < MAX_DRIVES; drive++) {
        const char *own = drv_own_set() ? drv_icon_label(drive) : 0;

        if (drv_own_set() ? !own : !(map & (1U << drive)))
            continue;
        if (own) {                              /* Install icon's (phase 74) */
            desk_icon((WORD)(n % xcnt), (WORD)(n / xcnt),
                      drive > 1 ? IB_HARD : IB_FLOPPY, own, (WORD)('A' + drive));
            gy = (WORD)(n / xcnt);
            n++;
            continue;
        }
        gx = (WORD)(n % xcnt);
        gy = (WORD)(n / xcnt);
        {
            char *d = label;
            const char *s = disk;
            while (*s && d < label + LABEL_LEN - 5)
                *d++ = *s++;
            *d++ = ' ';                         /* "DISK D1:", as SDX */
            *d++ = 'D';                         /* and a person say it */
            *d++ = (char)('1' + drive);
            *d++ = ':';
            *d = 0;
        }
        desk_icon(gx, gy, drive > 1 ? IB_HARD : IB_FLOPPY, label, (WORD)('A' + drive));
        n++;
    }
    gx = 0;
    gy = (WORD)(ycnt - 1);
    if (n && (WORD)((n - 1) / xcnt) >= gy)
        gx = (WORD)(xcnt - 1);
    desk_icon(gx, gy, IB_TRASH, trash, 0);
}

/* The desk again, from nothing: after Install icon, or an INF whose "#M"
 * lines chose the drive icons.  The windows are the AES's and stay. */
void desk_rebuild(void)
{
    desk_build();
    do_wredraw(DESKWH, &G.g_desk);
}

/* The selected item under root, or 0. */
static WORD sel_item(WORD root)
{
    WORD i;

    for (i = G.g_screen[root].ob_head; i >= WOBS_START; i = G.g_screen[i].ob_next)
        if (G.g_screen[i].ob_state & SELECTED)
            return i;
    return 0;
}

/* -- preferences -------------------------------------------------------- */



/* The two fields of a colour word the chooser touches (the donor's
 * FILLPAT_MASK and FILLCOL_MASK): the fill pattern and the fill colour. */
#define FILLPAT_MASK    0x0070L
#define FILLCOL_MASK    0x000FL

/* Put `spec` on the dialog: its pattern and colour selected in the two
 * rows, and the sample drawn in both.  A colour the screen cannot show is
 * left DISABLED and never selected. */
static void pref_show(OBJECT *tree, LONG spec)
{
    WORD i, pat = (WORD)((spec & FILLPAT_MASK) >> 4);
    WORD col = (WORD)(spec & FILLCOL_MASK);

    for (i = 0; i < N_PAT; i++)
        tree[PRPAT0 + i].ob_state = (UWORD)(i == pat ? SELECTED : NORMAL);
    for (i = 0; i < N_COL; i++)
        if (!(tree[PRCOL0 + i].ob_state & DISABLED))
            tree[PRCOL0 + i].ob_state = (UWORD)(i == col ? SELECTED : NORMAL);
    tree[PRSAMPLE].ob_spec.index = spec;
}

/* The background chooser: EmuTOS's inf_backgrounds in gem4xe's one
 * "Set preferences..." item.  The desk's pattern and colour, or a
 * window's, chosen from the eight VDI patterns and the colours the screen
 * can show -- which is why the desktop's own background is a setting and
 * not a decision made here: a 50% stipple is the GEM default at every
 * depth (EmuTOS desk/deskapp.c) and it artifacts into colour on a
 * composite Atari, so the answer is to let somebody choose. */
static void do_prefs(void)
{
    OBJECT *tree;

    /* THE CHOOSER LIVES IN A RESOURCE OF ITS OWN, loaded over ours while
     * it is up and freed again (src/aes/rsrc.c nests one).  Keeping it in
     * DESKTOP.RSC cost ~970 bytes of the pool for the whole run, which an
     * accessory beside the desktop has not got (test-m28).  This costs it
     * nothing until somebody opens the dialog. */
    if (!rsrc_load("PREFS.RSC")) {
        fun_alert(1, STNOPREF);
        return;
    }
    rsrc_gaddr(R_TREE, ADPREF, (void **)&tree);
    LONG curdesk = G.g_screen[DROOT].ob_spec.index;
    LONG curwin = G.g_screen[DROOT + 1].ob_spec.index;
    LONG spec;
    WORD ret, i, ncol, desk = TRUE;

    /* the colours this screen has, from what appl_init was told */
    ncol = (WORD)(1 << global[10]);
    if (ncol > N_COL)
        ncol = N_COL;
    for (i = 0; i < N_COL; i++)
        tree[PRCOL0 + i].ob_state = (UWORD)(i < ncol ? NORMAL : DISABLED);

    tree[PRDESK].ob_state = SELECTED;
    tree[PRWIND].ob_state = NORMAL;
    spec = curdesk;
    pref_show(tree, spec);
    tree[PRCNFDEL].ob_state = (UWORD)(desk_asks(CNF_DELETE) ? SELECTED : NORMAL);
    tree[PRCNFCPY].ob_state = (UWORD)(desk_asks(CNF_COPY) ? SELECTED : NORMAL);
    tree[PRCNFOVW].ob_state = (UWORD)(desk_asks(CNF_OVERWRITE) ? SELECTED : NORMAL);
    start_dialog(tree);

    for (;;) {
        ret = (WORD)(form_do(tree, 0) & 0x7FFF);
        if (ret == PROK || ret == PRCNCL)
            break;
        if (ret == PRDESK) {
            desk = TRUE;
            spec = curdesk;
        } else if (ret == PRWIND) {
            desk = FALSE;
            spec = curwin;
        } else if (ret >= PRPAT0 && ret < PRPAT0 + N_PAT) {
            spec = (spec & ~FILLPAT_MASK) | ((LONG)(ret - PRPAT0) << 4);
        } else if (ret >= PRCOL0 && ret < PRCOL0 + N_COL) {
            spec = (spec & ~FILLCOL_MASK) | (LONG)(ret - PRCOL0);
        }
        if (desk)
            curdesk = spec;
        else
            curwin = spec;
        pref_show(tree, spec);
        objc_draw(tree, ROOT, MAX_DEPTH, dlg.g_x, dlg.g_y, dlg.g_w, dlg.g_h);
    }

    tree[PROK].ob_state = NORMAL;
    tree[PRCNCL].ob_state = NORMAL;
    end_dialog();
    if (ret == PROK)                /* the toggles, before the file goes */
        desk_setasks((WORD)(((tree[PRCNFDEL].ob_state & SELECTED) ? CNF_DELETE : 0)
                            | ((tree[PRCNFCPY].ob_state & SELECTED) ? CNF_COPY : 0)
                            | ((tree[PRCNFOVW].ob_state & SELECTED) ? CNF_OVERWRITE : 0)));

    rsrc_free();                    /* the nested one: ours is untouched */

    if (ret == PROK) {
        /* Through desk_patcol, which REMEMBERS it: the choice belongs to
         * this screen and goes out on the INF's "#Q" line, so that Save
         * desktop keeps it and the next boot brings it back.  Setting
         * G.g_screen here directly was the bug -- the desk changed and
         * nothing wrote it down. */
        desk_patcol((UWORD)(curdesk & PATCOL_MASK),
                    (UWORD)(curwin & PATCOL_MASK));
        do_wredraw(DESKWH, &G.g_desk);
    }
}
/* -- the menu ---------------------------------------------------------- */

static WORD do_deskmenu(WORD item)
{
    OBJECT *tree = G.a_info;

    if (item == ABOUITEM) {
        start_dialog(tree);
        form_do(tree, 0);
        tree[DEOK].ob_state = NORMAL;
        end_dialog();
    }
    return FALSE;
}

static WORD do_filemenu(WORD item)
{
    WNODE *pw = win_ontop();
    WORD obj;

    switch (item) {
    case OPENITEM:                              /* the top window's selection,
                                                 * else the desk's */
        obj = pw ? sel_item(pw->w_root) : 0;
        if (obj)
            return do_open(pw->w_id, obj);
        if ((obj = sel_item(DROOT)) != 0)
            return do_open(DESKWH, obj);
        break;
    case SHOWITEM:                              /* what the selection is,
                                                 * and its name to change --
                                                 * or a drive on the desk */
        if (pw && sel_item(pw->w_root))
            fun_info(pw);
        else if ((obj = sel_item(DROOT)) != 0)
            fun_dinfo(obj);
        else if (pw)
            fun_info(pw);
        break;
    case NFOLITEM:                              /* a folder in the top
                                                 * window's directory */
        if (pw)
            fun_mkdir(pw);
        break;
    case DELTITEM:                              /* what is selected there */
        if (pw)
            fun_del(pw);
        break;
    case CLOSITEM:
        if (pw)
            win_close(pw, FALSE);
        break;
    case CLSWITEM:
        if (pw)
            win_close(pw, TRUE);
        break;
    case CYCLITEM:                              /* the bottom window up */
        win_cycle();
        break;
    case SALLITEM:                              /* everything the top
                                                 * window lists */
        if (pw)
            act_selall(pw);
        break;
    case MASKITEM:                              /* which files it lists */
        fun_mask(pw);
        break;
    case CMDITEM:                               /* a line for the DOS, and a
                                                 * window on what it printed */
        fun_command();
        break;
    case QUITITEM:
        shel_write(SHW_SHUTDOWN, 0, 0, "", "\0");
        return TRUE;
    default:
        break;
    }
    return FALSE;
}

/* Options -> Read .INF file / Save desktop: the layout the shell buffer
 * carries between programs, kept on the boot drive so that it outlives
 * the machine being switched off (deskwin.c).  Neither ends the
 * desktop's loop -- only a program run from an icon does. */
/* The view the desktop is in: the menu's checkmark moves with it and
 * the item metrics are worked out again.  The View menu sets it, and so
 * does the INF's environment line (deskwin.c inf_parse), which is why
 * it is here rather than inside the menu's handler. */
void desk_view(WORD view)
{
    if (view != G.g_iview) {
        menu_icheck(G.a_menu, (WORD)(ICONITEM + G.g_iview), 0);
        menu_icheck(G.a_menu, (WORD)(ICONITEM + view), 1);
        G.g_iview = view;
    }
    win_view();
}

/* ...and the order its listings are in.  The item and the order are the
 * same number less NAMEITEM, which is how the donor's deskfpd.h defines
 * them. */
void desk_sort(WORD sort)
{
    if (sort != G.g_isort) {
        menu_icheck(G.a_menu, (WORD)(NAMEITEM + G.g_isort), 0);
        menu_icheck(G.a_menu, (WORD)(NAMEITEM + sort), 1);
        G.g_isort = sort;
    }
}

/* Size to fit, or not: the columns follow the window, or the screen.
 * Like the view and the sort, the INF's environment line sets it too. */
void desk_fit(WORD fit)
{
    G.g_ifit = fit ? TRUE : FALSE;
    menu_icheck(G.a_menu, FITITEM, G.g_ifit);
    /* ...and nothing else: g_icols follows the VIEW, which has not
     * changed, so win_view has nothing to say here.  The donor's
     * FITITEM does the same two things and no more. */
}

/* View: which of the two views the windows are in, and which order
 * their listings are in.  A change sorts every open window, then
 * builds every one of them, and only then draws any -- the donor's
 * desk_all, in that sequence. */
static WORD do_viewmenu(WORD item)
{
    WORD sorted = FALSE, viewed = FALSE;

    switch (item) {
    case ICONITEM:
    case TEXTITEM:
        if ((WORD)(item - ICONITEM) == G.g_iview)
            break;
        desk_view((WORD)(item - ICONITEM));
        viewed = TRUE;
        break;
    case NAMEITEM:
    case TYPEITEM:
    case SIZEITEM:
    case DATEITEM:
    case NSRTITEM:
        if ((WORD)(item - NAMEITEM) == G.g_isort)
            break;
        desk_sort((WORD)(item - NAMEITEM));
        sorted = TRUE;
        break;
    case FITITEM:
        desk_fit(!G.g_ifit);
        viewed = TRUE;              /* the same rebuild a view change wants */
        break;
    default:
        break;
    }
    if (sorted || viewed) {
        desk_busy(TRUE);
        if (sorted)
            win_srtall();
        win_bdall();
        win_shwall();
        desk_busy(FALSE);
    }
    return FALSE;
}

static WORD do_optnmenu(WORD item)
{
    switch (item) {
    case SAVEITEM:
        if (!inf_save())
            fun_alert(1, STSVINF);
        break;
    case READITEM: {
        WORD own = drv_own_set();

        if (!inf_read())
            fun_alert(1, STRDINF);
        else if (own || drv_own_set())
            desk_rebuild();                     /* "#M" before or after it:
                                                 * a desk nobody changed is
                                                 * left exactly as it was */
        break;
    }
    case PREFITEM:
        do_prefs();
        break;
    case IAPPITEM:
        fun_install(win_ontop());
        break;
    case IICNITEM:
        fun_icon(sel_item(DROOT));    /* a drive icon, or 0 */
        break;
    default:
        break;
    }
    return FALSE;
}

static WORD hndl_menu(WORD title, WORD item)
{
    WORD done = FALSE;

    switch (title) {
    case DESKMENU:
        done = do_deskmenu(item);
        break;
    case FILEMENU:
        done = do_filemenu(item);
        break;
    case VIEWMENU:
        done = do_viewmenu(item);
        break;
    case OPTNMENU:
        done = do_optnmenu(item);
        break;
    default:
        break;
    }
    menu_tnormal(G.a_menu, title, 1);
    return done;
}

/* -- events ------------------------------------------------------------ */

/* An item taken out of a window and let go somewhere.  The AES drags
 * the outline and answers where the button came up; where the POINTER
 * came up is what says which window and which icon, so the state is
 * asked for again afterwards -- the box is snapped to the grid the item
 * came from and is not where the hand is.
 *
 * Dropped in its own window on nothing, or on itself, it is the click
 * it started as.  Anywhere else the file layer takes over: another
 * window or a folder in one is a copy, a copy with SHIFT held is a
 * move, and the trash is a delete. */
/* TRUE when the press turned out to be a drag and was acted on -- 2
 * when that drag ran a program, which ends the desktop; FALSE
 * when the button had already come up, which makes it a click and the
 * caller's business (hndl_button). */
static WORD hndl_drag(WNODE *pw, WORD obj, WORD wh, WORD root)
{
    OBJECT *pob = &G.g_screen[obj];
    WORD x, y, mstate, kstate, dwh, dobj, bx, by;
    GRECT d;

    graf_mkstate(&x, &y, &mstate, &kstate);
    if (!(mstate & 1))                          /* already let go: a click */
        return FALSE;
    /* What is dragged is the SELECTION, and an item pressed on that was
     * not part of it becomes the whole of it -- so dragging one of
     * several carries all of them, and dragging one of none carries
     * that one. */
    if (!(G.g_screen[obj].ob_state & SELECTED))
        act_select(wh, root, obj);
    objc_offset(G.g_screen, obj, &bx, &by);
    wind_get(0, WF_WORKXYWH, &d.g_x, &d.g_y, &d.g_w, &d.g_h);
    graf_dragbox(pob->ob_width, pob->ob_height, bx, by,
                 d.g_x, d.g_y, d.g_w, d.g_h, &x, &y);
    graf_mkstate(&x, &y, &mstate, &kstate);

    dwh = wind_find(x, y);
    if (dwh == DESKWH) {
        dobj = objc_find(G.g_screen, DROOT, MAX_DEPTH, x, y);
        if (dobj < WOBS_START)
            return TRUE;                        /* the bare desk */
    } else {
        WNODE *pd = win_find(dwh);
        if (!pd)
            return TRUE;
        dobj = objc_find(G.g_screen, pd->w_root, MAX_DEPTH, x, y);
        if (dobj < WOBS_START)
            dobj = 0;                           /* the window itself */
        if (dwh == wh && (dobj == 0 || dobj == obj))
            return TRUE;                        /* where it already is */
        /* ON A PROGRAM: that program run with the file, the TOS
         * desktop's other way of opening a document (docs/phase61.md) */
        if (dobj && do_dropopen(pw, pd, dobj))
            return 2;
    }
    fun_file2any(pw, dwh, dobj, kstate);
    return TRUE;
}

/* A press on the desk or in a window's work area (the control manager
 * keeps the gadgets and the windows under the top one): select the
 * item under it and no other there; two clicks open it, and opening
 * a program is what ends the desktop's loop.  One click on an item in
 * a window, with the button still down, is a drag. */
/* A press on a window's background, held: the AES draws the box while
 * the button is down and says how big it got, and everything the box
 * touches is the new selection.  It only grows right and down -- the
 * anchor stays where the press was (src/aes/grlib.c gr_rubwind), which
 * is the ST's behaviour and the donor's.
 *
 * FALSE when the button had already come up, which makes the press a
 * click on nothing, and that clears the selection instead. */
static WORD hndl_rubber(WORD wh, WORD root, WORD mx, WORD my)
{
    WORD x, y, mstate, kstate;
    GRECT box;

    graf_mkstate(&x, &y, &mstate, &kstate);
    if (!(mstate & 1))
        return FALSE;
    graf_rubbox(mx, my, 1, 1, &box.g_w, &box.g_h);
    box.g_x = mx;
    box.g_y = my;
    act_allselect(wh, root, &box);
    return TRUE;
}

/* A press: a double-click opens what is under it, a press held and
 * moved drags the selection, and anything else is a click, whose effect
 * on the selection act_bsclick decides.  The order matters -- the drag
 * has to be recognised before the click semantics are applied, because
 * SHIFT means "move" to a drag and "add to the selection" to a click,
 * and the same press cannot be both. */
static WORD hndl_button(WORD clicks, WORD mx, WORD my, WORD kstate)
{
    WORD wh, root, obj;
    WNODE *pw = 0;

    wh = wind_find(mx, my);
    if (wh == DESKWH) {
        root = DROOT;
    } else {
        pw = win_find(wh);
        if (!pw)
            return FALSE;
        root = pw->w_root;
    }
    obj = objc_find(G.g_screen, root, MAX_DEPTH, mx, my);
    if (obj < WOBS_START)
        obj = 0;
    if (obj && clicks == 2) {
        act_select(wh, root, obj);              /* just the one is opened */
        return do_open(wh, obj);
    }
    if (obj && pw) {
        WORD d = hndl_drag(pw, obj, wh, root);  /* 2: a program ran */

        if (d)
            return (WORD)(d == 2);
    }
    if (!obj && pw && hndl_rubber(wh, root, mx, my))
        return FALSE;
    act_bsclick(wh, root, obj, kstate);
    return FALSE;
}

/* -- the keyboard ------------------------------------------------------- */

/* The menu's shortcuts, the TOS desktop's own letters.  A Control+letter
 * arrives as its control code in the low byte and the letter's scan code
 * in the high one -- ^O is 0x180F (src/vdi/vdi.c, kb_translate) -- so ^I
 * is not TAB and ^M is not RETURN, whose scan codes are their own.  The
 * item text says the shortcut (tools/deskrsc.py MENU). */
static const struct {
    WORD code, title, item;
} menu_keys[] = {
    { 'O' - '@', FILEMENU, OPENITEM },
    { 'I' - '@', FILEMENU, SHOWITEM },
    { 'N' - '@', FILEMENU, NFOLITEM },
    { 'H' - '@', FILEMENU, CLOSITEM },
    { 'U' - '@', FILEMENU, CLSWITEM },
    { 'W' - '@', FILEMENU, CYCLITEM },
    { 'A' - '@', FILEMENU, SALLITEM },
    { 'D' - '@', FILEMENU, DELTITEM },
    { 'Z' - '@', FILEMENU, CMDITEM },
    { 'Q' - '@', FILEMENU, QUITITEM },
    { 'S' - '@', OPTNMENU, SAVEITEM },
};
#define N_MENU_KEYS (WORD)(sizeof menu_keys / sizeof menu_keys[0])

#define KEY_UP     0x4800
#define KEY_DOWN   0x5000
#define KEY_LEFT   0x4B00
#define KEY_RIGHT  0x4D00
#define KEY_ESC    0x011B
#define KEY_DELETE 0x537F
/* The three keys whose characters are also Control-letters' ($0D is
 * Ctrl-M, $09 Ctrl-I, $08 Ctrl-H): their scan codes tell them apart. */
#define KEY_RETURN 0x1C0D
#define KEY_TAB    0x0F09
#define KEY_BACKSP 0x0E08

/* One item of the menu, as if it had been chosen: the title shown
 * selected while it runs, as a mouse choice leaves it, and nothing at
 * all for an item that is greyed out. */
static WORD key_menu(WORD title, WORD item)
{
    if (G.a_menu[item].ob_state & DISABLED)
        return FALSE;
    menu_tnormal(G.a_menu, title, 0);
    return hndl_menu(title, item);
}

/* A scroll of the top window, as its arrows would send it. */
static void key_arrow(WORD action)
{
    WNODE *pw = win_ontop();
    WORD msg[8];

    if (!pw)
        return;
    msg[0] = WM_ARROWED;
    msg[1] = 0;
    msg[2] = 0;
    msg[3] = pw->w_id;
    msg[4] = action;
    hndl_wmsg(msg);
}

/* TRUE when the key ended the desktop (Quit).
 *
 * THE DRIVES ARE THE DIGITS.  TOS opens a drive with Alt and its letter;
 * this keyboard has no Alt, and the icons are labelled D1:, D2: -- so
 * 1 to 9 open them, and the letters are left alone.  THE ARROWS are
 * CONTROL and - = + * on this keyboard, so SHIFT with them is SHIFT and
 * CONTROL at once; with SHIFT a page, without it a line.  ESC reads the
 * top window's directory again; DELETE is File -> Delete. */
static WORD hndl_kbd(WORD key, WORD kstate)
{
    WORD low = (WORD)(key & 0xFF), i, obj;
    WORD page = (WORD)((kstate & 3) != 0);
    WNODE *pw;

    /* A Control-letter is its control character with the LETTER's scan
     * code, as on the ST, since keys carry the ST's (phase 84); only
     * RETURN, TAB and BACKSPACE share a character with one. */
    if (low >= 1 && low <= 26 && (UWORD)key != KEY_RETURN
        && (UWORD)key != KEY_TAB && (UWORD)key != KEY_BACKSP) {
        for (i = 0; i < N_MENU_KEYS; i++)
            if (menu_keys[i].code == low)
                return key_menu(menu_keys[i].title, menu_keys[i].item);
        return FALSE;
    }
    if (low >= '1' && low <= '9') {
        obj = obj_get_obid((WORD)('A' + low - '1'));
        if (obj) {
            act_select(DESKWH, DROOT, obj);
            return do_open(DESKWH, obj);
        }
        return FALSE;
    }
    switch ((UWORD)key) {
    case KEY_UP:    key_arrow(page ? WA_UPPAGE : WA_UPLINE); break;
    case KEY_DOWN:  key_arrow(page ? WA_DNPAGE : WA_DNLINE); break;
    case KEY_LEFT:  key_arrow(page ? WA_LFPAGE : WA_LFLINE); break;
    case KEY_RIGHT: key_arrow(page ? WA_RTPAGE : WA_RTLINE); break;
    case KEY_DELETE:
        return key_menu(FILEMENU, DELTITEM);
    case KEY_ESC:
        if ((pw = win_ontop()) != 0)
            win_rebld(pw);
        break;
    default:
        break;
    }
    return FALSE;
}

static WORD hndl_msg(void)
{
    WORD *msg = G.g_rmsg;

    switch (msg[0]) {
    case MN_SELECTED:
        return hndl_menu(msg[3], msg[4]);
    case WM_REDRAW:
    case WM_TOPPED:
    case WM_CLOSED:
    case WM_FULLED:
    case WM_ARROWED:
    case WM_HSLID:
    case WM_VSLID:
    case WM_SIZED:
    case WM_MOVED:
    case WM_NEWTOP:
        if (!cmd_msg(msg))                      /* the DOS command's window
                                                 * is not a folder's */
            hndl_wmsg(msg);
        return FALSE;
    default:
        return FALSE;
    }
}

/* ---- colour icons --------------------------------------------------------
 *
 * DESKICON.RSC, the Falcon desktop's icon file, beside DESKTOP.RSC: one
 * tree of G_CICONs, each named by its label.  Where it is there, the
 * desktop draws its six kinds of icon in colour (phase 87) -- and where
 * it is not, as it always has.
 *
 * TAKEN, NOT KEPT.  The AES gives a program two resource slots, and the
 * desktop needs the second for PREFS.RSC (Set preferences and the rest,
 * deskfun.c), so the file is loaded, the icons the desktop uses are copied
 * into one far block of its own, and the slot is given back.  rsrc_load
 * has turned their images chunky already (src/aes/rsrc.c, rs_chunky).
 *
 * BY NAME, not by place: "HARD DISK", "  trash can", "text    file" --
 * the Falcon's labels, spaces and case aside, the first of each kind
 * wins.  A NEWDESK.INF names its icons by number instead; reading one is
 * for later. */
static const char *const ci_names[N_IB] = {
    "HARDDISK", "FLOPPYDISK", "TRASHCAN", "FOLDER", "PROGRAMFILE", "TEXTFILE"
};

#define CI_BYTES 128                    /* one plane of a 32 x 32 form */
#define CI_SIZE  (sizeof(DCICON) + 2 * CI_BYTES + 2 * 5 * CI_BYTES)

/* What `a` names, spaces dropped and letters upper case, against `want`.
 * Every character a WORD: as a char, the path that folds the case reached
 * the compare with an 8-bit accumulator and every lower-case label missed
 * (B21, tools/ccbug). */
static WORD ci_named(const char FAR *a, const char *want)
{
    WORD i, j = 0, c;

    for (i = 0; i < 32; i++) {
        c = (WORD)(uint8_t)a[i];
        if (!c)
            break;
        if (c == ' ')
            continue;
        if (c >= 'a' && c <= 'z')
            c -= 32;
        if (c != (WORD)(uint8_t)want[j])
            return 0;
        j++;
    }
    return (WORD)(want[j] == 0);
}

/* n bytes, far to far, a byte through a local each time (B18). */
static void ci_copy(uint8_t FAR *d, const uint8_t FAR *s, WORD n)
{
    WORD i;
    uint8_t v;

    for (i = 0; i < n; i++) {
        v = s[i];
        d[i] = v;
    }
}

static void desk_cicons(void)
{
    OBJECT *t = 0;
    WORD k, o;
    LONG a;
    uint8_t FAR *p;

    G.g_cicon = 0;
    if (!rsrc_load("DESKICON.RSC"))
        return;
    rsrc_gaddr(R_TREE, 0, (void **)&t);
    a = t ? Malloc((LONG)(N_IB * CI_SIZE)) : 0;
    if (a > 0) {
        G.g_cicon = (DCICON FAR *)a;
        p = (uint8_t FAR *)(a + N_IB * (LONG)sizeof(DCICON));
        for (k = 0; k < N_IB; k++)
            G.g_cicon[k].col4 = 0;
        for (k = 0; k < N_IB; k++) {
            for (o = t[0].ob_head; o > 0; o = t[o].ob_next) {
                DCICON FAR *src = (DCICON FAR *)t[o].ob_spec.index;
                DCICON FAR *d = &G.g_cicon[k];
                if ((t[o].ob_type & 0xFF) != G_CICON || !src->col4
                    || src->ib.ib_wicon != 32 || src->ib.ib_hicon != 32
                    || !ci_named((const char FAR *)src->ib.ib_ptext, ci_names[k]))
                    continue;
                ci_copy((uint8_t FAR *)d, (const uint8_t FAR *)src, (WORD)sizeof(DCICON));
                ci_copy(p, (const uint8_t FAR *)src->ib.ib_pdata, CI_BYTES);
                d->ib.ib_pdata = (LONG)p;
                p += CI_BYTES;
                ci_copy(p, (const uint8_t FAR *)src->ib.ib_pmask, CI_BYTES);
                d->ib.ib_pmask = (LONG)p;
                p += CI_BYTES;
                ci_copy(p, (const uint8_t FAR *)src->col4, 5 * CI_BYTES);
                d->col4 = (LONG)p;
                p += 5 * CI_BYTES;
                d->sel4 = 0;
                if (src->sel4) {
                    ci_copy(p, (const uint8_t FAR *)src->sel4, 5 * CI_BYTES);
                    d->sel4 = (LONG)p;
                    p += 5 * CI_BYTES;
                }
                break;
            }
        }
    }
    rsrc_free();                        /* the nested one: PREFS.RSC's slot */
}

/* The AES's version, from global[0] as the ST has it (0x0140 is 1.40),
 * written over the resource's "0.00". */
static void set_version(void)
{
    char *v = (char *)(uint32_t)G.a_info[DEVERSN].ob_spec.index;
    UWORD g = (UWORD)global[0];
    static const char hex[] = "0123456789ABCDEF";

    v[0] = hex[(g >> 8) & 0x0F];
    v[2] = hex[(g >> 4) & 0x0F];
    v[3] = hex[g & 0x0F];
}

int main(void)
{
    static const WORD not_yet[N_NOT_YET] = NOT_YET_ITEMS;
    WORD ev_which, mx, my, button, kstate, kret, bret;
    WORD i, done;

    appl_init();
    G.g_handle = graf_handle(&G.g_wchar, &G.g_hchar, &G.g_wbox, &G.g_hbox);
    wind_get(DESKWH, WF_WORKXYWH, &G.g_desk.g_x, &G.g_desk.g_y,
             &G.g_desk.g_w, &G.g_desk.g_h);
    desk_busy(TRUE);

    if (!rsrc_load("DESKTOP.RSC")) {
        desk_busy(FALSE);
        /* the one string that cannot come from the resource */
        form_alert(1, "[3][DESKTOP.RSC is not on|the boot disk.][ Quit ]");
        shel_write(SHW_SHUTDOWN, 0, 0, "", "\0");
        appl_exit();
        return 1;
    }
    rsrc_gaddr(R_TREE, ADMENU, (void **)&G.a_menu);
    rsrc_gaddr(R_TREE, ADDINFO, (void **)&G.a_info);
    rsrc_gaddr(R_TREE, ADMKDBOX, (void **)&G.a_mkdir);
    rsrc_gaddr(R_TREE, ADDELDIA, (void **)&G.a_delete);
    rsrc_gaddr(R_TREE, ADFINFO, (void **)&G.a_finfo);
    rsrc_gaddr(R_ICONBLK, 0, (void **)&G.a_iblist);
    rsrc_gaddr(R_STRING, STFLINE, (void **)&G.g_fline);
    rsrc_gaddr(R_STRING, STFMARK, (void **)&G.g_fmark);
    desk_cicons();
    set_version();
    for (i = 0; i < N_NOT_YET; i++)
        menu_ienable(G.a_menu, not_yet[i], 0);
    cmd_init();

    obj_init();
    desk_build();
    G.g_ifit = TRUE;                            /* the donor's win_start */
    win_view();                                 /* V_ICON, until the INF */
    if (!win_start()) {
        desk_busy(FALSE);
        fun_alert(1, STNOMEM);
        rsrc_free();
        shel_write(SHW_SHUTDOWN, 0, 0, "", "\0");
        appl_exit();
        return 1;
    }
    app_start();
    if (drv_own_set())
        desk_build();                           /* the INF chose the drives */
    wind_newdesk(G.g_screen, DROOT);
    wind_update(BEG_UPDATE);
    do_wredraw(DESKWH, &G.g_desk);
    cnx_get();
    menu_bar(G.a_menu, 1);
    wind_update(END_UPDATE);
    desk_busy(FALSE);

    done = FALSE;
    while (!done) {
        ev_which = evnt_multi_moblk(MU_BUTTON | MU_MESAG | MU_KEYBD, 0x02, 0x01, 0x01,
                              0, 0, G.g_rmsg, 0, 0,
                              &mx, &my, &button, &kstate, &kret, &bret);
        wind_update(BEG_UPDATE);
        if (ev_which & MU_BUTTON)
            if (hndl_button(bret, mx, my, kstate))
                done = TRUE;
        if ((ev_which & MU_KEYBD) && !done)
            if (hndl_kbd(kret, kstate))
                done = TRUE;
        while ((ev_which & MU_MESAG) && !done) {
            if (hndl_msg())
                done = TRUE;
            ev_which = evnt_multi_moblk(MU_MESAG | MU_TIMER, 0x02, 0x01, 0x01,
                                  0, 0, G.g_rmsg, 0, 0,
                                  &mx, &my, &button, &kstate, &kret, &bret);
        }
        wind_update(END_UPDATE);
    }

    /* The windows stay open, as the donor leaves them: the shell's
     * reinitialisation takes the screen back, and their places are in
     * the shell buffer for the next desktop. */
    cmd_exit();
    cnx_put();
    app_save();
    menu_bar(G.a_menu, 0);
    wind_newdesk(0, ROOT);
    rsrc_free();
    appl_exit();
    return 0;
}
