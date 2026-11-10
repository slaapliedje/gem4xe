/* cpanel.c -- the control panel: a WINDOW listing the extensions, XControl's
 * shape (phase 135, docs/cpanel-plan.md step 2).
 *
 * A strip along the top with the time and the date; under it the list,
 * one slot per extension -- its icon, the icon's text, its title, all out
 * of the header in front of the module's file (phase 133) -- and a
 * scroll bar when there are more than fit.  Double-click a slot, or pick
 * one with the arrow keys and press Return, and the module opens.  The
 * closer or Escape shuts the panel.
 *
 * A WINDOW, NOT A DIALOG.  Until phase 135 the panel was a form_do inside
 * wind_update(BEG_UPDATE): it held the screen, and nothing else could be
 * clicked or redrawn until it was put away.  Now the desktop and its
 * windows go on working beside it, and the panel takes the keys and the
 * presses only while its window is on top -- the AES's rule since phase
 * 134, which is what made a window like this possible.
 *
 * WHAT A MODULE GETS.  The window's whole work area, as XControl gives:
 * an EVENT CPX draws into it and is driven from here, one event at a
 * time, with the window's redraws, moves and closer handled around it.
 * A FORM CPX still runs its own dialog (General and Color, until phase
 * 136 gives them Xform_do and the window).
 *
 * NO WORKSTATION.  Everything here is objects the AES draws.
 */
#include "gem.h"
#include "cpx.h"
#include "mint/cookie.h"
#include "cpanelrsc.h"

static OBJECT *tree;

/* WHICH BANK THE RESOURCE LANDED IN, for a gate to read: 0 is the pool,
 * anything else is far memory.  Without this the claim that a large-data
 * accessory's resource costs bank $00 nothing is only a claim -- rs_load
 * would fall back to the pool in silence, tools/memreport.py would go on
 * reporting the far arrangement, and both would agree while being wrong
 * (the trap docs/phase*.md keeps recording). */
WORD acc_far;

/* Modules boot-initialised, for a gate to read. */
WORD cp_boots;

/* THE WINDOW AS A GATE SEES IT.  A gate finds these the way test-m45
 * finds an accessory's variables: by the address the AES holds of the
 * accessory's title, less its link offset (tests/emu/shots.py,
 * Tour.panel) -- so the places it clicks are the ones this file chose,
 * not a copy of the layout in Python. */
WORD  cp_wh = -1;               /* the window, -1 for none */
GRECT cp_work;                  /* its work area, as last placed */
WORD  cp_rows;                  /* extensions listed */
WORD  cp_top;                   /* the row in the first slot */
WORD  cp_sel = -1;              /* the selected row, -1 for none */
WORD  cp_opens;                 /* modules opened from the window */
WORD  cp_slotr[N_VIS][4];       /* each slot on the screen: x, y, w, h */
uint32_t cp_form;               /* the form Xform_do last ran: a module's */

#define CP_KIND     (NAME | CLOSER | MOVER)
#define CP_COLS     32          /* XControl's 256 pixels of 8 */
#define CP_ICONW    32          /* a CPX icon is 32 x 24 (cpx.h) */
#define CP_ICONH    24
#define CP_ICOLS    11          /* the icon's column, its text under it */
#define CP_TCOLS    17          /* a title: title_txt less its NUL */

#define KEY_UP      0x4800      /* the ST's key words (src/desk/desktop.c) */
#define KEY_DOWN    0x5000
#define KEY_LEFT    0x4B00
#define KEY_RIGHT   0x4D00
#define KEY_ESC     0x011B
#define KEY_RETURN  0x1C0D

static WORD wchar, hchar;

/* ---- the extensions ---------------------------------------------------
 *
 * The AES reads every module's header off the front of its file into its
 * table, loads at boot the ones that ask, and frees the ones that are not
 * CPX_RESIDENT after this panel has boot-initialised them (src/aes/shel.c,
 * sh_cpx); this panel asks what is there, lists it, and has the one the
 * user picks loaded for as long as it is open (cp_opencpx).  That split
 * is the whole shape of a CPX: the HOST owns the window and the event
 * loop, the MODULE owns the dialog.
 *
 * A ROW IS NOT A SLOT.  A CPX_SETONLY module acts at boot and has nothing
 * to open, so it is not listed -- XControl drops it too -- and the rows
 * map to the table through cpx_row.
 *
 * THE WORDS ARE COPIED, not pointed at: an object's ob_spec has to be an
 * address the VDI can read at every redraw, and a copy is simpler to
 * reason about than a lifetime shared with the shell.  The ICON is
 * pointed at, in the AES's table -- 96 bytes a module, kept for as long
 * as the machine is up. */
#define CP_MAXROWS 16           /* src/aes/shel.c CPX_MAX */

static uint32_t cpx_table;
static WORD     cpx_stride;
static WORD     cpx_total;              /* slots in the AES's table */
static WORD     cpx_row[CP_MAXROWS];    /* row -> slot */
static char     cpx_titles[CP_MAXROWS][CP_TCOLS + 1];
static char     cpx_itext[CP_MAXROWS][14];

/* A CPX icon has no mask (cpx.h), so every slot shares one that is all
 * set: the icon's 32 x 24 goes down white and the picture black over it,
 * and SELECTED swaps the two, as for any G_ICON (src/aes/objc.c). */
static UWORD cp_mask[CP_ICONW / 16 * CP_ICONH];

static void cp_findcpx(void)
{
    WORD i, j;

    cpx_total = cpx_count(&cpx_table, &cpx_stride);
    cp_rows = 0;
    for (i = 0; i < cpx_total && cp_rows < CP_MAXROWS; i++) {
        CPXSLOT FAR *sl = cpx_slot(cpx_table, cpx_stride, i);
        WORD r;

        if (sl->hdr.flags & CPX_SETONLY)
            continue;
        r = cp_rows;
        cpx_row[r] = i;
        for (j = 0; j < CP_TCOLS && sl->hdr.title_txt[j]; j++)
            cpx_titles[r][j] = sl->hdr.title_txt[j];
        cpx_titles[r][j] = 0;
        for (j = 0; j < 13 && sl->hdr.i_text[j]; j++)
            cpx_itext[r][j] = sl->hdr.i_text[j];
        cpx_itext[r][j] = 0;
        cp_rows = (WORD)(r + 1);
    }
    if (cp_sel >= cp_rows)
        cp_sel = -1;
}

/* ---- the objects ------------------------------------------------------
 *
 * EVERY PLACE IS SET HERE, from the character cell: a slot is as tall as
 * an icon and a line of text, which is pixels and characters at once, and
 * an icon block's offsets are pixels rsrc_obfix never touches.  The tree
 * in CPANEL.RSC gives the structure and the words (tools/cpanelrsc.py). */
static void cp_set(WORD ob, WORD x, WORD y, WORD w, WORD h)
{
    tree[ob].ob_x = x;
    tree[ob].ob_y = y;
    tree[ob].ob_width = w;
    tree[ob].ob_height = h;
}

/* Hidden or shown.  Read-modify-write through a temporary: the compiler
 * has a fault in `p->a = p->a OP e` (tools/ccbug, B15). */
static void cp_hide(WORD ob, WORD hide)
{
    UWORD f = tree[ob].ob_flags;

    if (hide)
        f |= HIDETREE;
    else
        f &= (UWORD)~HIDETREE;
    tree[ob].ob_flags = f;
}

static ICONBLK FAR *cp_iconblk(WORD ob)
{
    return (ICONBLK FAR *)(uint32_t)tree[ob].ob_spec.index;
}

static void cp_layout(void)
{
    WORD w = CP_COLS * wchar;
    WORD hs = hchar + 4;                        /* the strip */
    WORD sh = CP_ICONH + hchar + 4;             /* a slot */
    WORD lw = w - 4, lh = N_VIS * sh + 2;       /* the list, framed */
    WORD sb = 2 * wchar, ah = hchar + 2;        /* the scroll bar, an arrow */
    WORD iw = CP_ICOLS * wchar;
    WORD k;

    cp_set(CPROOT, 0, 0, w, hs + lh + 2);
    cp_set(CPTIME, wchar, 2, 6 * wchar, hchar);
    cp_set(CPDATE, w - 9 * wchar, 2, 8 * wchar, hchar);
    cp_set(CPOPTS, 11 * wchar, 2, 9 * wchar, hchar);
    cp_set(CPLIST, 2, hs, lw, lh);
    for (k = 0; k < N_VIS; k++) {
        WORD box = CPSLOT0 + k * SLOT_OBS;
        ICONBLK FAR *ib = cp_iconblk(box + 1);

        cp_set(box, 1, 1 + k * sh, lw - 2 - sb, sh);
        cp_set(box + 1, 2, 2, iw, CP_ICONH + hchar);
        ib->ib_xicon = (WORD)((UWORD)(iw - CP_ICONW) / 2);
        ib->ib_yicon = 0;
        ib->ib_wicon = CP_ICONW;
        ib->ib_hicon = CP_ICONH;
        ib->ib_xtext = 0;
        ib->ib_ytext = CP_ICONH;
        ib->ib_wtext = iw;
        ib->ib_htext = hchar;
        ib->ib_pmask = (LONG)(uint32_t)(UWORD FAR *)cp_mask;
        cp_set(box + 2, iw + 2 + wchar, (WORD)((UWORD)(sh - hchar) / 2),
               CP_TCOLS * wchar, hchar);
    }
    cp_set(CPSBAR, lw - 1 - sb, 1, sb, lh - 2);
    cp_set(CPUP, 0, 0, sb, ah);
    cp_set(CPTRACK, 0, ah, sb, lh - 2 - 2 * ah);
    cp_set(CPDOWN, 0, lh - 2 - ah, sb, ah);
    cp_set(CPEMPTY, 2 * wchar, 2 * hchar, 27 * wchar, hchar);
}

/* The rows into the slots, and the scroll bar to match. */
static void cp_fill(void)
{
    WORD k, most = cp_rows > N_VIS ? (WORD)(cp_rows - N_VIS) : 0;

    if (cp_top > most)
        cp_top = most;
    if (cp_top < 0)
        cp_top = 0;
    for (k = 0; k < N_VIS; k++) {
        WORD box = CPSLOT0 + k * SLOT_OBS, row = cp_top + k;
        UWORD st = NORMAL;

        if (row >= cp_rows) {
            cp_hide(box, 1);
            continue;
        }
        {
            CPXSLOT FAR *sl = cpx_slot(cpx_table, cpx_stride, cpx_row[row]);
            ICONBLK FAR *ib = cp_iconblk(box + 1);
            UWORD ic = sl->hdr.i_info;

            ib->ib_pdata = (LONG)(uint32_t)(UWORD FAR *)sl->hdr.icon;
            ib->ib_ptext = (LONG)(uint32_t)(char FAR *)cpx_itext[row];
            if (!ic)
                ic = 0x1000;            /* black on white */
            ib->ib_char = (WORD)ic;
        }
        /* ALL 24 BITS.  This panel is --data-model=large, so its own
         * strings are far; a 16-bit ob_spec here would name bank $00 and
         * draw whatever is at the same offset (tools/nearcast.py). */
        tree[box + 2].ob_spec.index =
            (int32_t)(uint32_t)(char FAR *)cpx_titles[row];
        {
            /* as wide as its words, so that SELECTED inverts the title
             * and not a bar of blanks after it */
            WORD n = 0;
            while (n < CP_TCOLS && cpx_titles[row][n])
                n++;
            tree[box + 2].ob_width = (WORD)(n * wchar);
        }
        if (row == cp_sel)
            st = SELECTED;
        tree[box + 1].ob_state = st;
        tree[box + 2].ob_state = st;
        cp_hide(box, 0);
    }
    cp_hide(CPSBAR, cp_rows <= N_VIS);
    if (cp_rows > N_VIS) {
        WORD th = tree[CPTRACK].ob_height;
        WORD sh = (WORD)((LONG)th * N_VIS / cp_rows);
        WORD y;

        if (sh < hchar)
            sh = hchar;
        y = (WORD)((LONG)(th - sh) * cp_top / most);
        cp_set(CPSLIDER, 0, y, tree[CPTRACK].ob_width, sh);
    }
    cp_hide(CPEMPTY, cp_rows != 0);
}

/* Where each slot is on the screen, for a gate (cp_slotr). */
static void cp_gatexy(void)
{
    WORD k, x, y;

    for (k = 0; k < N_VIS; k++) {
        WORD box = CPSLOT0 + k * SLOT_OBS;

        objc_offset(tree, box, &x, &y);
        cp_slotr[k][0] = x;
        cp_slotr[k][1] = y;
        cp_slotr[k][2] = tree[box].ob_width;
        cp_slotr[k][3] = tree[box].ob_height;
    }
}

/* ---- the clock strip ----------------------------------------------------
 * The time and the date, refreshed when the minute turns: a timer asks
 * every second, and only a change is drawn.  DD/MM/YY, General's order
 * (src/apps/general.c); twelve-hour time is step 4's. */
static char cp_time[7], cp_date[9];

/* THE CLOCK'S WAY (phase 140): 0 for 24-hour, 1 for 12 -- XControl's
 * Setup choice, kept in CONTROL.INF where the modules' settings are kept
 * (cp_readinf) and read by a gate here. */
WORD cp_hour12;

static void cp_two(char *p, UWORD v)
{
    p[0] = (char)('0' + (v / 10) % 10);
    p[1] = (char)('0' + v % 10);
}

static WORD cp_clock(void)
{
    UWORD t = (UWORD)Tgettime(), d = (UWORD)Tgetdate();
    UWORD h = t >> 11;
    char tm[7], dt[9];
    WORD i, changed = 0;

    if (cp_hour12) {                    /* " 1:05p", "12:30a" */
        UWORD h12 = h % 12;

        if (!h12)
            h12 = 12;
        tm[0] = ' ';
        if (h12 >= 10)
            tm[0] = '1';
        tm[1] = (char)('0' + h12 % 10);
        tm[5] = 'a';
        if (h >= 12)
            tm[5] = 'p';
    } else {
        cp_two(tm, h);
        tm[5] = ' ';
    }
    tm[2] = ':';
    cp_two(tm + 3, (t >> 5) & 63);
    tm[6] = 0;
    cp_two(dt, d & 31);
    dt[2] = '/';
    cp_two(dt + 3, (d >> 5) & 15);
    dt[5] = '/';
    cp_two(dt + 6, ((d >> 9) + 80) % 100);
    dt[8] = 0;
    for (i = 0; i < 7; i++)
        if (cp_time[i] != tm[i]) {
            cp_time[i] = tm[i];
            changed = 1;
        }
    for (i = 0; i < 9; i++)
        if (cp_date[i] != dt[i]) {
            cp_date[i] = dt[i];
            changed = 1;
        }
    return changed;
}

/* ---- drawing ------------------------------------------------------------
 * Through the window's rectangle list, inside the screen lock: the window
 * may be partly covered, and another process may be drawing. */
static void cp_draw(WORD ob, WORD depth, const GRECT *area)
{
    GRECT r;

    if (cp_wh < 0)
        return;
    wind_update(BEG_UPDATE);
    wind_get(cp_wh, WF_FIRSTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    while (r.g_w && r.g_h) {
        if (rc_intersect(area, &r))
            objc_draw(tree, ob, depth, r.g_x, r.g_y, r.g_w, r.g_h);
        wind_get(cp_wh, WF_NEXTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    }
    wind_update(END_UPDATE);
}

static void cp_drawlist(void)
{
    GRECT r;

    objc_offset(tree, CPLIST, &r.g_x, &r.g_y);
    r.g_w = tree[CPLIST].ob_width;
    r.g_h = tree[CPLIST].ob_height;
    cp_draw(CPLIST, MAX_DEPTH, &r);
}

/* A slot drawn again from the list's ground up: deselecting must put the
 * white back under a title, which the title alone does not draw. */
static void cp_drawslot(WORD k)
{
    GRECT r;

    if (k < 0 || k >= N_VIS)
        return;
    objc_offset(tree, CPSLOT0 + k * SLOT_OBS, &r.g_x, &r.g_y);
    r.g_w = tree[CPSLOT0 + k * SLOT_OBS].ob_width;
    r.g_h = tree[CPSLOT0 + k * SLOT_OBS].ob_height;
    cp_draw(CPLIST, MAX_DEPTH, &r);
}

static void cp_drawstrip(void)
{
    GRECT r = cp_work;

    r.g_h = (WORD)(hchar + 4);
    cp_draw(CPROOT, MAX_DEPTH, &r);
}

/* The window's work area again -- it opened, or moved -- and the tree
 * placed in it. */
static void cp_place(void)
{
    if (cp_wh < 0)
        return;
    wind_get(cp_wh, WF_WORKXYWH, &cp_work.g_x, &cp_work.g_y,
             &cp_work.g_w, &cp_work.g_h);
    tree[CPROOT].ob_x = cp_work.g_x;
    tree[CPROOT].ob_y = cp_work.g_y;
    cp_gatexy();
}

/* ---- selecting and scrolling -------------------------------------------- */

static void cp_scrollto(WORD top)
{
    WORD most = cp_rows > N_VIS ? (WORD)(cp_rows - N_VIS) : 0;

    if (top > most)
        top = most;
    if (top < 0)
        top = 0;
    if (top == cp_top)
        return;
    cp_top = top;
    cp_fill();
    cp_gatexy();
    cp_drawlist();
}

static void cp_select(WORD row)
{
    WORD old = cp_sel, top = cp_top;

    if (row < 0 || row >= cp_rows || row == old)
        return;
    cp_sel = row;
    if (row < top)
        top = row;
    else if (row >= top + N_VIS)
        top = (WORD)(row - N_VIS + 1);
    if (top != cp_top) {
        cp_top = top;
        cp_fill();
        cp_gatexy();
        cp_drawlist();
        return;
    }
    cp_fill();
    if (old >= 0)
        cp_drawslot((WORD)(old - cp_top));
    cp_drawslot((WORD)(row - cp_top));
}

/* ---- what the panel hands a module -------------------------------------
 *
 * The XCPB, and its two working callbacks.  These run INSIDE THIS PANEL
 * and are called BY a module, so they are the same cross-link call as a
 * CPXINFO entry in the other direction and obey the same rules: SAVEDS,
 * and one uint32_t argument, which is the block's own address
 * (src/app/cpx.h says why).  A callback reads what it needs out of the
 * block and writes its answer back into it.
 */
static XCPB cp_xcpb;

/* CPX_Save: the module's 64 bytes, to a file named after the MODULE and
 * not after anything it chose.  The panel knows the file name because
 * the AES's table carries it (src/aes/shel.c, CPXE_FILE) -- a module
 * never learns its own name and never has to, which is what stops two
 * modules from arguing over one settings file.
 *
 * The ST writes these bytes back into the .CPX itself.  Here they go
 * beside it, so a module is never written to while it is loaded and one
 * that will not save cannot corrupt itself trying. */
static SAVEDS void cp_cpx_save(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    CPXSLOT FAR *sl;
    char name[20];
    uint8_t buf[64];
    LONG h;
    WORD i, j;

    pb->ok = 0;
    if (pb->which < 0 || pb->which >= cpx_total || !cpx_table)
        return;
    sl = cpx_slot(cpx_table, cpx_stride, pb->which);
    for (i = 0; i < 13 && sl->file[i] && sl->file[i] != '.'; i++)
        name[i] = sl->file[i];
    name[i++] = '.';
    name[i++] = 'C'; name[i++] = 'F'; name[i++] = 'G';
    name[i] = 0;
    for (j = 0; j < 64; j++)
        buf[j] = (uint8_t)sl->hdr.buffer[j];
    h = Fcreate(name, 0);
    if (h < 0)
        return;
    pb->ok = (WORD)(Fwrite((WORD)h, 64L, buf) == 64L);
    Fclose((WORD)h);
}

/* XGen_Alert: one of the canned alerts, drawn in the panel's voice.
 *
 * THE WHOLE POINT IS THAT THE WORDS ARE NOT THE MODULE'S.  Every module
 * that cannot read its file says the same sentence, and a translator
 * translates it once, in CPANEL.RSC, where free strings are how the
 * desktop says everything too (src/desk/deskfun.c, fun_alert).  A
 * sentence compiled into a module could not be reached from outside it
 * at all.
 *
 * The id indexes the free strings directly -- Atari's numbers are 0..3
 * and CPXAL0 is where this resource puts the first of them, so the two
 * stay together if a string is ever added in front (tools/cpanelrsc.py).
 *
 * AN ID THAT IS NOT ONE OF THE FOUR draws nothing and answers 0.  There
 * is no sentence for a number nobody defined, and answering 1 would be
 * reporting a decision the person was never asked to make.
 *
 * THE ANSWER IS ATARI'S TOO: alert 0 asks, and 1 means its first button;
 * alerts 1-3 have one button and always answer 1, which is what the
 * Compendium promises a module that tests ok after one of them. */
/* TWO PLACES COUNT THESE ALERTS: cpx.h's XAL_NALERT, which is what a
 * module compiles against, and the resource's N_XALERT, which is how
 * many strings are really in the file.  A module asking for the fourth
 * when the resource has three would index past the end and draw
 * whatever a stale free string held.  So the build fails instead --
 * the same shape as the slot-layout check in cpx.h, and for the same
 * reason: anything restated in a second place drifts. */
typedef char cp_xalert_count_holds[(N_XALERT == XAL_NALERT) ? 1 : -1];

static SAVEDS void cp_gen_alert(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    char *str;

    pb->ok = 0;
    if (pb->alert < 0 || pb->alert >= N_XALERT)
        return;
    str = 0;
    rsrc_gaddr(R_STRING, CPXAL0 + pb->alert, (void **)&str);
    if (!str)
        return;
    pb->ok = (WORD)(form_alert(1, str) == 1);
}

/* ---- Xform_do: a module's form, in the window (phase 136) ---------------
 *
 * form_do's loop (src/aes/form.c fm_do), run by the panel over the
 * module's tree in the window's work area -- XControl's Xform_do.  The
 * difference from form_do is everything around the form: it does NOT
 * take the screen (no fm_own, no BEG_UPDATE while it waits), so the
 * desktop and its windows go on working, and the window's own messages
 * come here between a person's clicks:
 *
 *   WM_REDRAW   the form drawn again through the rectangle list;
 *   WM_TOPPED   the window to the top;
 *   WM_MOVED    the window moved, and the tree's root with it, so the
 *               module finds its place in tree[ROOT];
 *   WM_SIZED    the look changed (cp_fit), the work area kept;
 *   WM_CLOSED, AC_CLOSE   answered as -1 with the message: the module
 *               keeps or puts back what it set, and returns.
 *
 * Presses and keys reach it only while the window is on top (phase 134),
 * so form_button, form_keybd and objc_edit draw on a window nothing
 * covers; each is done inside the screen lock, as GEM's own drawing is.
 */
static void cp_fit(void);

/* The first EDITABLE field, as form_do's fm_inifld finds it. */
static WORD cp_firstedit(OBJECT *t)
{
    WORD i = 0;

    for (;;) {
        UWORD f = t[i].ob_flags;

        if ((f & EDITABLE) && !(f & HIDETREE))
            return i;
        if (f & LASTOB)
            return 0;
        i++;
    }
}

static void cp_formdraw(OBJECT *t, const GRECT *area)
{
    GRECT r;

    if (cp_wh < 0)
        return;
    wind_update(BEG_UPDATE);
    wind_get(cp_wh, WF_FIRSTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    while (r.g_w && r.g_h) {
        if (rc_intersect(area, &r))
            objc_draw(t, ROOT, MAX_DEPTH, r.g_x, r.g_y, r.g_w, r.g_h);
        wind_get(cp_wh, WF_NEXTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    }
    wind_update(END_UPDATE);
}

/* the field's cursor, on or off, inside the screen lock */
static void cp_cursor(OBJECT *t, WORD edit, WORD *idx, WORD kind)
{
    if (!edit)
        return;
    wind_update(BEG_UPDATE);
    objc_edit(t, edit, 0, idx, kind);
    wind_update(END_UPDATE);
}

static SAVEDS void cp_xform_do(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    OBJECT *t = (OBJECT *)pb->xf_tree;
    WORD edit = 0, next, idx = 0, cont = 1, i;
    WORD msg[8], mx, my, mb, ks, kr, nc, nk, nb;

    /* NEXT'S ADDRESS IS NEVER TAKEN: form_keybd and form_button answer
     * into nk and nb.  Any join given to a variable whose address is
     * taken is wrong at every -O (B9, tools/ccbug), and an inlined
     * function's two returns are a join -- cp_firstedit, inlined here,
     * left its answer in one slot and `next` was copied from another
     * nothing had written: the cursor went on object 32443 of 41 and
     * the AES walked off the tree for ever (phase 138). */
    next = pb->xf_edit;
    if (!next)
        next = cp_firstedit(t);
    for (i = 0; i < 8; i++)
        pb->xf_msg[i] = 0;
    cp_form = pb->xf_tree;
    while (cont) {
        WORD ev;

        if (next != 0 && edit != next) {
            edit = next;
            next = 0;
            cp_cursor(t, edit, &idx, ED_INIT);
        }
        ev = evnt_multi(MU_KEYBD | MU_BUTTON | MU_MESAG, 2, 1, 1,
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                        msg, 0, 0, &mx, &my, &mb, &ks, &kr, &nc);
        if (ev & MU_MESAG) {
            WORD gone = 0;

            if (msg[0] == AC_CLOSE) {
                cp_wh = -1;             /* the AES took the window */
                gone = 1;
            } else if (msg[0] == AC_OPEN && cp_wh >= 0) {
                wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
            } else if (cp_wh >= 0 && msg[3] == cp_wh) {
                if (msg[0] == WM_REDRAW) {
                    GRECT a;

                    a.g_x = msg[4]; a.g_y = msg[5];
                    a.g_w = msg[6]; a.g_h = msg[7];
                    cp_cursor(t, edit, &idx, ED_END);
                    cp_formdraw(t, &a);
                    cp_cursor(t, edit, &idx, ED_INIT);
                } else if (msg[0] == WM_TOPPED) {
                    wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
                } else if (msg[0] == WM_MOVED) {
                    WORD ox = cp_work.g_x, oy = cp_work.g_y, v;

                    wind_set(cp_wh, WF_CURRXYWH, msg[4], msg[5], msg[6], msg[7]);
                    cp_place();
                    /* through temporaries: B15, `p->a = p->a OP e` */
                    v = (WORD)(t[ROOT].ob_x + cp_work.g_x - ox);
                    t[ROOT].ob_x = v;
                    v = (WORD)(t[ROOT].ob_y + cp_work.g_y - oy);
                    t[ROOT].ob_y = v;
                } else if (msg[0] == WM_SIZED) {
                    cp_fit();
                } else if (msg[0] == WM_CLOSED) {
                    gone = 1;
                }
            }
            if (gone) {
                if (cp_wh >= 0)
                    cp_cursor(t, edit, &idx, ED_END);
                for (i = 0; i < 8; i++)
                    pb->xf_msg[i] = msg[i];
                pb->xf_ret = -1;
                return;
            }
        }
        /* A KEY WITH NO CHARACTER -- a function key, Help, Undo -- is the
         * module's to read, as XControl's CT_KEY: -1, and the key word in
         * msg[3].  The four arrows move between fields and stay here. */
        if ((ev & MU_KEYBD) && !(kr & 0xFF) && (UWORD)kr != KEY_UP
            && (UWORD)kr != KEY_DOWN && (UWORD)kr != KEY_LEFT
            && (UWORD)kr != KEY_RIGHT) {
            cp_cursor(t, edit, &idx, ED_END);
            for (i = 0; i < 8; i++)
                pb->xf_msg[i] = 0;
            pb->xf_msg[0] = CT_KEY;
            pb->xf_msg[3] = kr;
            pb->xf_ret = -1;
            return;
        }
        if (ev & MU_KEYBD) {
            wind_update(BEG_UPDATE);
            cont = form_keybd(t, edit, next, kr, &nk, &kr);
            next = nk;
            if (kr && edit)
                objc_edit(t, edit, kr, &idx, ED_CHAR);
            wind_update(END_UPDATE);
        }
        if ((ev & MU_BUTTON) && cont) {
            next = objc_find(t, ROOT, MAX_DEPTH, mx, my);
            if (next == NIL)
                next = 0;
            else {
                wind_update(BEG_UPDATE);
                cont = form_button(t, next, nc, &nb);
                next = nb;
                wind_update(END_UPDATE);
            }
        }
        /* leaving the field: take the cursor away */
        if (!cont || (next != 0 && next != edit))
            cp_cursor(t, edit, &idx, ED_END);
    }
    pb->xf_ret = next;
}

/* ---- the rest of the toolkit (phase 137) -------------------------------
 *
 * Set_Evnt_Mask, GetFirstRect / GetNextRect, getcookie and MFsave, each
 * a one-block callback as cpx.h's ABI requires (src/app/cpx.h says what
 * each is for, and where it parts from XControl's).
 */
#define CPX_TIME  30000L                /* XControl's timer, until asked */

static WORD  cp_emask;                  /* Set_Evnt_Mask: MU_M1 | MU_M2 */
static MOBLK cp_em1, cp_em2;
static LONG  cp_etime = CPX_TIME;

static SAVEDS void cp_set_evnt_mask(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    cp_emask = (WORD)(pb->em_mask & (MU_M1 | MU_M2));
    /* field by field: a MOBLK is ten bytes, and a near <-> far struct
     * copy over eight is an internal compiler error (B11) */
    cp_em1.m_out = pb->em_m1.m_out;
    cp_em1.m_x = pb->em_m1.m_x;
    cp_em1.m_y = pb->em_m1.m_y;
    cp_em1.m_w = pb->em_m1.m_w;
    cp_em1.m_h = pb->em_m1.m_h;
    cp_em2.m_out = pb->em_m2.m_out;
    cp_em2.m_x = pb->em_m2.m_x;
    cp_em2.m_y = pb->em_m2.m_y;
    cp_em2.m_w = pb->em_m2.m_w;
    cp_em2.m_h = pb->em_m2.m_h;
    if (pb->em_time != -1L)
        cp_etime = pb->em_time;
}

/* The window's list, each piece cut to the area: the walk goes on through
 * the AES's own cursor (WF_NEXTXYWH), so a GetFirstRect starts it again. */
static GRECT cp_rlarea;

static void cp_rlwalk(XCPB FAR *pb, WORD field)
{
    GRECT r;

    pb->ok = 0;
    if (cp_wh < 0)
        return;
    for (;;) {
        wind_get(cp_wh, field, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
        if (!r.g_w || !r.g_h)
            return;                     /* the end of the list */
        field = WF_NEXTXYWH;
        if (rc_intersect(&cp_rlarea, &r)) {
            pb->rl_rect = r;
            pb->ok = 1;
            return;
        }
    }
}

static SAVEDS void cp_first_rect(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    cp_rlarea = pb->rl_rect;
    cp_rlwalk(pb, WF_FIRSTXYWH);
}

static SAVEDS void cp_next_rect(uint32_t xcpb)
{
    cp_rlwalk((XCPB FAR *)xcpb, WF_NEXTXYWH);
}

/* No jar on this machine: every cookie is not found, and said so. */
static SAVEDS void cp_getcookie(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    long v = 0;

    pb->ok = 0;
    if (Getcookie(pb->ck_id, &v) == C_FOUND) {
        pb->ck_value = v;
        pb->ok = 1;
    }
}

static SAVEDS void cp_mfsave(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    if (pb->mf_save)
        graf_mouse(M_SAVE, (const WORD *)0);
    else
        graf_mouse(M_RESTORE, (const WORD *)0);
}

/* ---- the widgets (phase 138) ---------------------------------------------
 *
 * XControl's sliders and pop-up, behaving as its code does (src/app/cpx.h
 * says where they part from it).  They draw straight onto the screen,
 * clipped to what changed, inside the screen lock: they run while a
 * person is pressing inside the window, which the AES gives this process
 * only while the window is on top (phase 134), so nothing covers it.
 */

/* An object's rectangle on the screen, and a margin round it. */
static void cp_obrect(OBJECT *t, WORD ob, WORD m, GRECT *r)
{
    objc_offset(t, ob, &r->g_x, &r->g_y);
    r->g_x = (WORD)(r->g_x - m);
    r->g_y = (WORD)(r->g_y - m);
    r->g_w = (WORD)(t[ob].ob_width + 2 * m);
    r->g_h = (WORD)(t[ob].ob_height + 2 * m);
}

static void cp_drawclip(OBJECT *t, WORD ob, const GRECT *r)
{
    wind_update(BEG_UPDATE);
    objc_draw(t, ob, MAX_DEPTH, r->g_x, r->g_y, r->g_w, r->g_h);
    wind_update(END_UPDATE);
}

static SAVEDS void cp_sl_size(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    OBJECT *t = (OBJECT *)pb->sl_tree;
    LONG ratio = 1000L, len;
    WORD base = pb->sl_base, sl = pb->sl_slider;

    if (pb->sl_items > 0 && pb->sl_visible > 0) {
        ratio = (LONG)pb->sl_visible * 1000L / pb->sl_items;
        if (ratio > 1000L)
            ratio = 1000L;
    }
    if (pb->sl_dir == SL_HORIZONTAL) {
        len = ratio * t[base].ob_width / 1000L;
        if (len < pb->sl_minsize)
            len = pb->sl_minsize;
        t[sl].ob_width = (WORD)len;
    } else {
        len = ratio * t[base].ob_height / 1000L;
        if (len < pb->sl_minsize)
            len = pb->sl_minsize;
        t[sl].ob_height = (WORD)len;
    }
}

/* The thumb for a value: Sl_x's minimum at the left, Sl_y's at the
 * bottom (XControl's).  Then the module's foo, every time. */
static void cp_slplace(XCPB FAR *pb, WORD dir, WORD value)
{
    OBJECT *t = (OBJECT *)pb->sl_tree;
    WORD base = pb->sl_base, sl = pb->sl_slider;
    WORD min = pb->sl_min, max = pb->sl_max;
    LONG room, at = 0;

    if (dir == SL_HORIZONTAL) {
        room = (LONG)t[base].ob_width - t[sl].ob_width;
        if (value == max)
            at = room;
        else if (max != min)
            at = (LONG)(value - min) * room / (LONG)(max - min);
        t[sl].ob_x = (WORD)at;
    } else {
        room = (LONG)t[base].ob_height - t[sl].ob_height;
        if (value == min)
            at = room;
        else if (max != min)
            at = (LONG)(value - max) * room / (LONG)(min - max);
        t[sl].ob_y = (WORD)at;
    }
    if (pb->sl_foo)
        pb->sl_foo((uint32_t)pb);
}

static SAVEDS void cp_sl_x(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    cp_slplace(pb, SL_HORIZONTAL, pb->sl_value);
}

static SAVEDS void cp_sl_y(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    cp_slplace(pb, SL_VERTICAL, pb->sl_value);
}

/* The track drawn again where the thumb was and is, from the track up --
 * the old thumb rubbed out by its background. */
static void cp_slredraw(XCPB FAR *pb, const GRECT *old)
{
    OBJECT *t = (OBJECT *)pb->sl_tree;
    GRECT now, both;

    cp_obrect(t, pb->sl_slider, 3, &now);
    both = *old;
    rc_union(&now, &both);
    cp_drawclip(t, pb->sl_base, &both);
}

/* *sl_var stepped toward sl_inc, inside sl_min..sl_max either way round */
static WORD cp_slclamp(XCPB FAR *pb, WORD v)
{
    WORD lo = pb->sl_min, hi = pb->sl_max;

    if (lo > hi) {
        lo = pb->sl_max;
        hi = pb->sl_min;
    }
    if (v < lo)
        v = lo;
    if (v > hi)
        v = hi;
    return v;
}

static WORD cp_button_down(void)
{
    WORD x, y, b, k;

    graf_mkstate(&x, &y, &b, &k);
    return (WORD)(b & 1);
}

static SAVEDS void cp_sl_arrow(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    OBJECT *t = (OBJECT *)pb->sl_tree;
    WORD FAR *var = (WORD FAR *)pb->sl_var;
    WORD obj = pb->sl_obj, first = 1;
    GRECT old, ob;

    if (obj > 0) {
        t[obj].ob_state = SELECTED;
        cp_obrect(t, obj, 2, &ob);
        cp_drawclip(t, ROOT, &ob);
    }
    do {
        WORD v = cp_slclamp(pb, (WORD)(*var + pb->sl_inc));

        if (v != *var) {
            cp_obrect(t, pb->sl_slider, 3, &old);
            *var = v;
            cp_slplace(pb, pb->sl_dir, v);
            cp_slredraw(pb, &old);
        }
        /* a quarter of a second before the first repeat, 60 ms after:
         * XControl repeats with no delay, and one click here was eleven
         * steps */
        evnt_timer(first ? 250 : 60, 0);
        first = 0;
    } while (cp_button_down());
    if (obj > 0) {
        t[obj].ob_state = NORMAL;
        cp_drawclip(t, ROOT, &ob);
    }
}

/* The thumb follows the pointer while the button is down; the value from
 * where its middle is, rounded to the nearest step. */
static void cp_sldrag(XCPB FAR *pb, WORD dir)
{
    OBJECT *t = (OBJECT *)pb->sl_tree;
    WORD FAR *var = (WORD FAR *)pb->sl_var;
    WORD base = pb->sl_base, sl = pb->sl_slider;
    WORD min = pb->sl_min, max = pb->sl_max;
    WORD mx, my, mb, ks, bx, by, sx, sy, grab, last = (WORD)(min - 1);
    GRECT old;

    graf_mkstate(&mx, &my, &mb, &ks);
    objc_offset(t, base, &bx, &by);
    objc_offset(t, sl, &sx, &sy);
    if (dir == SL_HORIZONTAL)
        grab = (WORD)(mx - sx);
    else
        grab = (WORD)(my - sy);
    while (mb & 1) {
        LONG room, pos, v;

        if (dir == SL_HORIZONTAL) {
            room = (LONG)t[base].ob_width - t[sl].ob_width;
            pos = (LONG)(mx - grab) - bx;
        } else {
            room = (LONG)t[base].ob_height - t[sl].ob_height;
            pos = (LONG)(my - grab) - by;
        }
        if (pos < 0)
            pos = 0;
        if (pos > room)
            pos = room;
        if (room <= 0)
            v = min;
        else if (dir == SL_HORIZONTAL)
            v = min + ((LONG)(max - min) * pos * 2 + room) / (room * 2);
        else
            v = max + ((LONG)(min - max) * pos * 2 + room) / (room * 2);
        if ((WORD)v != last) {
            last = (WORD)v;
            cp_obrect(t, sl, 3, &old);
            *var = (WORD)v;
            cp_slplace(pb, dir, (WORD)v);
            cp_slredraw(pb, &old);
        }
        graf_mkstate(&mx, &my, &mb, &ks);
    }
}

static SAVEDS void cp_sl_dragx(uint32_t xcpb)
{
    cp_sldrag((XCPB FAR *)xcpb, SL_HORIZONTAL);
}

static SAVEDS void cp_sl_dragy(uint32_t xcpb)
{
    cp_sldrag((XCPB FAR *)xcpb, SL_VERTICAL);
}

/* Popup: XControl's shape -- five slots, and past five items an up arrow,
 * three items and a down arrow -- in a tree of the panel's own, drawn
 * over whatever is there inside the screen and mouse locks, and put away
 * with FMD_FINISH, which has the windows under it redraw themselves, as
 * a dialog is put away. */
#define PU_SLOTS   5
static OBJECT cp_pu[1 + PU_SLOTS];
static const char cp_upa[] = "\001", cp_dna[] = "\002";

/* What slot i shows, and its state, from the offset and the slot under
 * the pointer; then the whole menu drawn. */
static void cp_pudraw(char **items, WORD n, WORD dflt, WORD k, WORD off,
                      WORD hot, const GRECT *box)
{
    WORD i, scroll = n > PU_SLOTS;

    for (i = 1; i <= k; i++) {
        WORD item = (WORD)(i - 1);
        UWORD st = NORMAL;

        if (scroll)
            item = (WORD)(off + i - 2);
        if (scroll && i == 1)
            cp_pu[i].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)cp_upa;
        else if (scroll && i == k)
            cp_pu[i].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)cp_dna;
        else {
            cp_pu[i].ob_spec.index = (int32_t)(uint32_t)items[item];
            if (item == dflt)
                st = CHECKED;
        }
        if (i == hot)
            st |= SELECTED;
        cp_pu[i].ob_state = st;
    }
    objc_draw(cp_pu, ROOT, MAX_DEPTH, box->g_x, box->g_y, box->g_w, box->g_h);
}

static SAVEDS void cp_popup(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;
    char **items = (char **)pb->pu_items;   /* far, as every pointer here */
    WORD n = pb->pu_n, dflt = pb->pu_default, scroll, off = 0;
    WORD w = 0, sh = (WORD)(hchar + 4), x, y, h, i, k, hot = -1;
    WORD mx, my, mb, ks, kr, nc, held, down, pick = -1, msg[8];
    WORD start = -2, moved = 0;
    GRECT box;

    pb->pu_ret = -1;
    if (n <= 0 || !items)
        return;
    scroll = n > PU_SLOTS;
    if (scroll && dflt > 0) {
        off = (WORD)(dflt - 1);
        if (off > n - 3)
            off = (WORD)(n - 3);
    }
    for (i = 0; i < n; i++) {
        WORD len = 0;
        const char FAR *s = items[i];

        while (s[len])
            len++;
        if ((WORD)((len + 1) * wchar) > w)
            w = (WORD)((len + 1) * wchar);
    }
    if (w < pb->pu_button.g_w + 3)
        w = (WORD)(pb->pu_button.g_w + 3);
    k = n;
    if (scroll)
        k = PU_SLOTS;
    h = (WORD)(k * sh);
    /* at the button's corner; up or left so as to stay in the world */
    x = pb->pu_button.g_x;
    y = pb->pu_button.g_y;
    if (y + h >= pb->pu_world.g_y + pb->pu_world.g_h)
        y = (WORD)(pb->pu_button.g_y + pb->pu_button.g_h + 3 - h);
    if (x + w >= pb->pu_world.g_x + pb->pu_world.g_w)
        x = (WORD)(pb->pu_button.g_x + pb->pu_button.g_w + 3 - w);
    x = (WORD)(x - 1);
    y = (WORD)(y - 1);

    cp_pu[0].ob_next = NIL;
    cp_pu[0].ob_head = 1;
    cp_pu[0].ob_tail = k;
    cp_pu[0].ob_type = G_BOX;
    cp_pu[0].ob_flags = NONE;
    cp_pu[0].ob_state = SHADOWED;
    cp_pu[0].ob_spec.index = 0x00FF1100L;      /* a one-pixel frame */
    cp_pu[0].ob_x = x;
    cp_pu[0].ob_y = y;
    cp_pu[0].ob_width = w;
    cp_pu[0].ob_height = h;
    for (i = 1; i <= k; i++) {
        cp_pu[i].ob_next = 0;
        if (i < k)
            cp_pu[i].ob_next = (WORD)(i + 1);
        cp_pu[i].ob_head = NIL;
        cp_pu[i].ob_tail = NIL;
        cp_pu[i].ob_type = G_STRING;
        cp_pu[i].ob_flags = NONE;
        if (i == k)
            cp_pu[i].ob_flags = LASTOB;
        cp_pu[i].ob_x = 0;
        cp_pu[i].ob_y = (WORD)((i - 1) * sh + 2);
        cp_pu[i].ob_width = w;
        cp_pu[i].ob_height = hchar;
    }

    box.g_x = (WORD)(x - 1);
    box.g_y = (WORD)(y - 1);
    box.g_w = (WORD)(w + 2 + 2);                /* the frame and the shadow */
    box.g_h = (WORD)(h + 2 + 2);
    wind_update(BEG_UPDATE);
    wind_update(BEG_MCTRL);
    graf_mkstate(&mx, &my, &mb, &ks);
    held = (WORD)(mb & 1);
    down = held;
    cp_pudraw(items, n, dflt, k, off, hot, &box);

    /* EVENTS, NOT POLLING: a press shorter than one turn of a polling loop
     * was never seen.  The slot under the pointer is worked out from where
     * it is (the slots tile the menu, sh apart); then the wait is for the
     * button to change, the pointer to leave that slot (or, off the menu,
     * to come onto it), or -- an arrow held -- 125 ms, one item a turn.
     * Held when the menu came up, the choice is made on the release;
     * otherwise on the next press.  Off the menu, either is Cancel.
     *
     * NOT XCONTROL'S: a release on the slot the menu came up under, the
     * pointer never off it, picks nothing and the menu stays for a press.
     * The menu opens over its button, so XControl took a slow click on
     * the button for its first item. */
    for (;;) {
        WORD now = -1, ev, arrow, want, mflag;
        GRECT r;

        if (mx >= x && mx < x + w && my >= y && my < y + h)
            now = (WORD)((my - y) / sh + 1);
        if (start == -2)
            start = now;
        if (now != start)
            moved = 1;
        if (now != hot) {
            hot = now;
            cp_pudraw(items, n, dflt, k, off, hot, &box);
        }
        arrow = 0;
        if (scroll && (hot == 1 || hot == k))
            arrow = 1;
        if (arrow && down) {
            if (hot == 1 && off > 0) {
                off--;
                cp_pudraw(items, n, dflt, k, off, hot, &box);
            } else if (hot == k && off < n - 3) {
                off++;
                cp_pudraw(items, n, dflt, k, off, hot, &box);
            }
        }
        r.g_x = x;
        r.g_w = w;
        if (hot > 0) {
            r.g_y = (WORD)(y + (hot - 1) * sh);
            r.g_h = sh;
            mflag = 1;                  /* wait to leave the slot */
        } else {
            r.g_y = y;
            r.g_h = h;
            mflag = 0;                  /* ...or to come onto the menu */
        }
        want = 1;
        if (down)
            want = 0;
        ev = evnt_multi((WORD)(MU_BUTTON | MU_M1
                               | (arrow && down ? MU_TIMER : 0)),
                        1, 1, want, mflag, r.g_x, r.g_y, r.g_w, r.g_h,
                        0, 0, 0, 0, 0, msg, 125, 0,
                        &mx, &my, &mb, &ks, &kr, &nc);
        if (!(ev & MU_BUTTON))
            continue;                   /* moved, or the arrow's repeat */
        down = (WORD)(mb & 1);
        if (mx >= x && mx < x + w && my >= y && my < y + h)
            now = (WORD)((my - y) / sh + 1);
        else
            now = -1;
        arrow = 0;
        if (scroll && (now == 1 || now == k))
            arrow = 1;
        if (arrow) {
            held = 0;                   /* an arrow picks nothing: go on,
                                         * choosing with a press now */
            continue;
        }
        if (down && held)
            continue;
        if (held && !moved) {
            held = 0;                   /* the slow click: see above */
            continue;
        }
        if (now > 0) {
            pick = (WORD)(now - 1);
            if (scroll)
                pick = (WORD)(off + now - 2);
        }
        break;
    }
    /* the button up before anything else sees a click */
    if (down)
        evnt_button(1, 1, 0, &mx, &my, &mb, &ks);
    wind_update(END_MCTRL);
    wind_update(END_UPDATE);
    form_dial(FMD_FINISH, 0, 0, 0, 0, box.g_x, box.g_y, box.g_w, box.g_h);
    pb->pu_ret = pick;
}

static SAVEDS void cp_rsh_obfix(uint32_t xcpb)
{
    XCPB FAR *pb = (XCPB FAR *)xcpb;

    rsrc_obfix((OBJECT *)pb->ob_tree, pb->ob_obj);
}

/* ONE PARAMETER BLOCK, reused for every call, and it is the PANEL's --
 * a module is handed its address and reads it there (src/app/cpx.h says
 * why every entry takes one uint32_t rather than arguments). */
static CPXPB cp_pb;

static void cp_xcpb_init(void)
{
    cp_xcpb.handle = 0;                 /* this panel opens no workstation */
    cp_xcpb.booting = 0;
    cp_xcpb.country = 0;
    cp_xcpb.CPX_Save = cp_cpx_save;
    cp_xcpb.XGen_Alert = cp_gen_alert;
    cp_xcpb.alert = 0;
    cp_xcpb.ok = 0;
    cp_xcpb.Xform_do = cp_xform_do;
    cp_xcpb.Set_Evnt_Mask = cp_set_evnt_mask;
    cp_xcpb.GetFirstRect = cp_first_rect;
    cp_xcpb.GetNextRect = cp_next_rect;
    cp_xcpb.getcookie = cp_getcookie;
    cp_xcpb.MFsave = cp_mfsave;
    cp_xcpb.Popup = cp_popup;
    cp_xcpb.Sl_size = cp_sl_size;
    cp_xcpb.Sl_x = cp_sl_x;
    cp_xcpb.Sl_y = cp_sl_y;
    cp_xcpb.Sl_arrow = cp_sl_arrow;
    cp_xcpb.Sl_dragx = cp_sl_dragx;
    cp_xcpb.Sl_dragy = cp_sl_dragy;
    cp_xcpb.rsh_obfix = cp_rsh_obfix;
}

/* BOOT-TIME INIT.  A module whose header says CPX_BOOTINIT -- or
 * CPX_SETONLY, which has nothing else to do -- is opened once at
 * start-up with xcpb->booting set, so it can put back what it saved --
 * the double-click rate, a screen setting -- before anybody sees the
 * machine.  It draws nothing: `booting` is how it knows, and cpx.h tells
 * a module to act and return without a dialog.
 *
 * This is the PANEL's job and not the AES's.  The AES loads the modules
 * and could call them, but it would have to learn the shape of CPXPB and
 * XCPB to do it -- a second place for two layouts that already exist in
 * src/app/cpx.h, and a second place for them to drift.  The shell loads
 * modules BEFORE accessories so that this can happen here instead
 * (src/aes/shel.c says so where the order is set). */
void cp_bootinit(void)
{
    WORD i;

    cp_findcpx();
    cp_xcpb_init();
    if (!cpx_total)
        return;
    cp_xcpb.booting = 1;
    for (i = 0; i < cpx_total; i++) {
        CPXSLOT FAR *sl = cpx_slot(cpx_table, cpx_stride, i);
        CPXINFO FAR *info;

        if (!sl->info || !(sl->hdr.flags & (CPX_BOOTINIT | CPX_SETONLY)))
            continue;
        info = (CPXINFO FAR *)sl->info;
        if (!info->cpx_call)
            continue;
        cp_xcpb.which = i;
        cp_xcpb.buffer = (uint32_t)(char FAR *)sl->hdr.buffer;
        cp_pb.xcpb = (uint32_t)(XCPB FAR *)&cp_xcpb;
        cp_pb.rect.g_x = cp_pb.rect.g_y = 0;
        cp_pb.rect.g_w = cp_pb.rect.g_h = 0;
        cp_pb.quit = 0;
        cp_pb.ret = 0;
        info->cpx_call((uint32_t)(CPXPB FAR *)&cp_pb);
        cp_boots++;
    }
    cp_xcpb.booting = 0;
}

/* ---- driving an event CPX, in the window --------------------------------
 *
 * The module has drawn itself into the work area and asked to be driven,
 * so from here the PANEL owns the loop and the module owns what is in the
 * window.  That is the whole reason a CPX is worth the machinery: a
 * module that never blocks its host can show the effect of a control
 * while the control is being moved.
 *
 * XCONTROL'S ORDER (phase 137; src/app/cpx.h, CPXINFO): cpx_hook first,
 * and the event goes no further if it takes it; then the timer, the key
 * and the press -- those two only reach this process while the window is
 * on top, the AES's rule since phase 134 -- then the mouse rectangles a
 * module asked for with Set_Evnt_Mask, then the window's messages.  A
 * redraw is done a rectangle at a time, each the module's clip; a move
 * is cpx_wmove, or a redraw of the work area for a module with none.
 * XControl takes the update lock around the lot and a hook that takes
 * the event leaves it held; this takes it only to draw.
 *
 * Each entry is given a `quit` zeroed first, and the loop ends the moment
 * one comes back non-zero -- so a module says "I am done" once and is not
 * asked again.  AN ENTRY MAY BE 0, and most of a simple module's are.
 *
 * cpx_close COMES WHEN THE WINDOW GOES, with pb->keep: 1 for its closer,
 * 0 for AC_CLOSE -- and not when the module ends itself, as XControl's.
 * Until phase 137 it came every time, with nothing to say which.
 *
 * THE TIMER is XControl's 30 seconds until a module asks for another
 * period; the mouse rectangles only if it asks.  What it asked for lasts
 * until it shuts, and the next module starts from nothing.
 */
/* The work area cleared, then the module asked to draw: each rectangle of
 * the window's list that meets `area`. */
static void cp_cpxdraw(CPXINFO FAR *info, const GRECT *area)
{
    GRECT r;

    if (cp_wh < 0)
        return;
    wind_update(BEG_UPDATE);
    wind_get(cp_wh, WF_FIRSTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    while (r.g_w && r.g_h) {
        if (rc_intersect(area, &r)) {
            objc_draw(tree, CPROOT, 0, r.g_x, r.g_y, r.g_w, r.g_h);
            if (info->cpx_draw) {
                cp_pb.rect = r;
                cp_pb.quit = 0;
                info->cpx_draw((uint32_t)(CPXPB FAR *)&cp_pb);
            }
        }
        wind_get(cp_wh, WF_NEXTXYWH, &r.g_x, &r.g_y, &r.g_w, &r.g_h);
    }
    wind_update(END_UPDATE);
}

static void cp_close(void);

static void cp_drivecpx(CPXINFO FAR *info)
{
    WORD msg[8], mx, my, mb, ks, kr, nc, gone = 0, i;
    uint32_t pb = (uint32_t)(CPXPB FAR *)&cp_pb;

    for (;;) {
        WORD ev = evnt_multi(MU_KEYBD | MU_BUTTON | MU_TIMER | MU_MESAG
                             | (cp_emask & (MU_M1 | MU_M2)),
                             2, 1, 1,
                             cp_em1.m_out, cp_em1.m_x, cp_em1.m_y,
                             cp_em1.m_w, cp_em1.m_h,
                             cp_em2.m_out, cp_em2.m_x, cp_em2.m_y,
                             cp_em2.m_w, cp_em2.m_h,
                             msg,
                             (WORD)(cp_etime & 0xFFFFL),
                             (WORD)((uint32_t)cp_etime >> 16),
                             &mx, &my, &mb, &ks, &kr, &nc);
        cp_pb.mouse.x = mx;
        cp_pb.mouse.y = my;
        cp_pb.mouse.buttons = mb;
        cp_pb.mouse.kstate = ks;
        cp_pb.kstate = ks;
        cp_pb.key = kr;
        cp_pb.nclicks = nc;
        cp_pb.event = ev;
        /* plain ifs, not ?: or a comparison's value: cp_pb's address is
         * taken, and a join into an address-taken variable is wrong at
         * every -O (B9, tools/ccbug) */
        for (i = 0; i < 8; i++) {
            cp_pb.msg[i] = 0;
            if (ev & MU_MESAG)
                cp_pb.msg[i] = msg[i];
        }
        cp_pb.quit = 0;

        if (info->cpx_hook) {
            cp_pb.ret = 0;
            info->cpx_hook(pb);
            if (cp_pb.ret) {            /* it took the event */
                if (cp_pb.quit)
                    break;
                continue;
            }
        }
        if ((ev & MU_TIMER) && info->cpx_timer)
            info->cpx_timer(pb);
        if ((ev & MU_KEYBD) && info->cpx_key)
            info->cpx_key(pb);
        if ((ev & MU_BUTTON) && info->cpx_button)
            info->cpx_button(pb);
        if ((ev & MU_M1) && info->cpx_m1)
            info->cpx_m1(pb);
        if ((ev & MU_M2) && info->cpx_m2)
            info->cpx_m2(pb);
        if (ev & MU_MESAG) {
            if (msg[0] == AC_CLOSE)
                gone = 2;               /* the AES took the window */
            else if (msg[0] == AC_OPEN && cp_wh >= 0)
                wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
            else if (msg[3] == cp_wh && cp_wh >= 0) {
                if (msg[0] == WM_REDRAW) {
                    GRECT a;
                    a.g_x = msg[4]; a.g_y = msg[5];
                    a.g_w = msg[6]; a.g_h = msg[7];
                    cp_cpxdraw(info, &a);
                } else if (msg[0] == WM_TOPPED) {
                    wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
                } else if (msg[0] == WM_MOVED) {
                    wind_set(cp_wh, WF_CURRXYWH, msg[4], msg[5], msg[6], msg[7]);
                    cp_place();
                    cp_pb.rect = cp_work;
                    if (info->cpx_wmove)
                        info->cpx_wmove(pb);
                    else
                        cp_cpxdraw(info, &cp_work);
                } else if (msg[0] == WM_SIZED) {
                    cp_fit();
                } else if (msg[0] == WM_CLOSED) {
                    gone = 1;
                }
            }
        }
        /* A key the module did not take closes it, so a module with no
         * cpx_key is not a window nobody can get out of. */
        if ((ev & MU_KEYBD) && !info->cpx_key)
            cp_pb.quit = 1;
        if (cp_pb.quit || gone)
            break;
    }
    if (gone && info->cpx_close) {
        cp_pb.keep = 0;
        if (gone == 1)
            cp_pb.keep = 1;
        info->cpx_close(pb);
    }
    if (gone == 1)
        cp_close();
    else if (gone == 2)
        cp_wh = -1;
}

/* Open slot i's module: its cpx_call, through the vtable it published
 * when it loaded.  A separately linked module reached by a runtime
 * long-indirect call -- which is safe because every entry in a CPXINFO is
 * `saveds` and sets up its own direct page and data bank
 * (src/app/cpx.h).
 *
 * LOADED FOR THE OPEN, FREED AFTER IT.  The AES frees every module that
 * is not CPX_RESIDENT once this panel has boot-initialised it, so a
 * slot's vtable is 0 until Cpxload runs the module again (src/aes/shel.c
 * sh_cpxload) -- the ST's rule, and what lets a closed module cost bank
 * $00 nothing.  A module that will not load says so with the canned
 * memory alert, which is what it nearly always is.
 *
 * THE BLOCK GOES TO cpx_init (phase 137): its address in the first four
 * reserved bytes of the slot's header before the load, which the kit's
 * glue reads (src/app/cpxmain.c) -- so a module has the toolkit at init,
 * as XControl's has. */
static void cp_opencpx(WORD i)
{
    CPXSLOT FAR *sl;
    CPXINFO FAR *info;

    if (i < 0 || i >= cpx_total || !cpx_table)
        return;
    sl = cpx_slot(cpx_table, cpx_stride, i);
    cp_xcpb_init();
    cp_xcpb.which = i;                  /* who is about to call back */
    cp_xcpb.buffer = (uint32_t)(char FAR *)sl->hdr.buffer;
    cp_emask = 0;                       /* nothing asked for yet */
    cp_etime = CPX_TIME;
    *(uint32_t FAR *)sl->hdr.reserved = (uint32_t)(XCPB FAR *)&cp_xcpb;
    if (!sl->info && Cpxload(i, 1) != 0) {
        cp_xcpb.alert = XAL_MEM_ERR;
        cp_gen_alert((uint32_t)(XCPB FAR *)&cp_xcpb);
        return;
    }
    info = (CPXINFO FAR *)sl->info;
    if (info && info->cpx_call) {
        cp_pb.xcpb = (uint32_t)(XCPB FAR *)&cp_xcpb;
        cp_pb.rect = cp_work;
        cp_pb.quit = 0;
        cp_pb.ret = 0;
        cp_pb.keep = 0;
        /* the module draws into the whole work area: clear it first */
        cp_draw(CPROOT, 0, &cp_work);
        info->cpx_call((uint32_t)(CPXPB FAR *)&cp_pb);
        if (cp_pb.ret)
            cp_drivecpx(info);          /* an EVENT CPX: it wants events */
    }
    cp_emask = 0;
    cp_etime = CPX_TIME;
    Cpxload(i, 0);                      /* kept only if CPX_RESIDENT */
}

static void cp_openrow(WORD row)
{
    if (row < 0 || row >= cp_rows)
        return;
    cp_opens++;
    cp_opencpx(cpx_row[row]);
    if (cp_wh >= 0) {                   /* the list back, unless it went */
        cp_findcpx();
        cp_fill();
        cp_place();
        cp_draw(CPROOT, MAX_DEPTH, &cp_work);
    }
}

/* ---- the window --------------------------------------------------------- */

static char *cp_title;                  /* CPANEL.RSC's: WF_NAME keeps it */

/* ---- the options' state (phase 140; the options themselves are below) */
#define CP_NWORDS   (CPNO - CPOPABOUT + 1)
#define CP_WORD(i)  cp_words[(i) - CPOPABOUT]
#define CP_CLOSER   (-1)                /* a form ended by the closer: OK */
#define CP_GONE     (-2)                /* ...by AC_CLOSE: Cancel */
#define CP_INF      "CONTROL.INF"       /* a bare name, as NAME.CFG: where
                                         * the modules' settings go */

static OBJECT *cp_infot, *cp_setupt;
static char *cp_words[CP_NWORDS];
WORD cp_optpick = -1;                   /* the last option picked: a gate's */
static char cp_ifile[14], cp_iver[6], cp_iid[5];

/* CONTROL.INF: a line, "CLOCK 12" or "CLOCK 24".  Missing or not
 * understood, the clock is 24-hour. */
static void cp_readinf(void)
{
    char buf[32];
    LONG h = Fopen(CP_INF, 0), n;
    WORD i;

    if (h < 0)
        return;
    n = Fread((WORD)h, (LONG)sizeof buf - 1, buf);
    Fclose((WORD)h);
    for (i = 0; i + 8 <= (WORD)n; i++)
        if (buf[i] == 'C' && buf[i + 1] == 'L' && buf[i + 2] == 'O'
            && buf[i + 3] == 'C' && buf[i + 4] == 'K' && buf[i + 5] == ' ') {
            cp_hour12 = 0;
            if (buf[i + 6] == '1' && buf[i + 7] == '2')
                cp_hour12 = 1;
        }
}

static WORD cp_writeinf(WORD h12)
{
    static const char l12[] = "CLOCK 12\x9b", l24[] = "CLOCK 24\x9b";
    const char *s = l24;
    LONG h;
    WORD ok;

    if (h12)
        s = l12;
    h = Fcreate(CP_INF, 0);
    if (h < 0)
        return 0;
    ok = (WORD)(Fwrite((WORD)h, 9L, s) == 9L);
    Fclose((WORD)h);
    return ok;
}

/* The resource, once.  Separate from the window because the two happen
 * at different times in an accessory: the shell takes this while the AES
 * is starting up -- before the first program, the only time an accessory
 * may take anything from bank $00 -- and opens the window whenever
 * somebody chooses it from the Desk menu (src/apps/cpanelacc.c). */
WORD cp_start(void)
{
    WORD wb, hb, i;

    if (!rsrc_load("CPANEL.RSC"))
        return FALSE;
    rsrc_gaddr(R_TREE, ADCPANEL, (void **)&tree);
    rsrc_gaddr(R_STRING, CPWTITLE, (void **)&cp_title);
    if (!tree || !cp_title)
        return FALSE;
    acc_far = (WORD)(((uint32_t)tree) >> 16);
    graf_handle(&wchar, &hchar, &wb, &hb);
    for (i = 0; i < (WORD)(sizeof cp_mask / sizeof cp_mask[0]); i++)
        cp_mask[i] = 0xFFFF;
    tree[CPTIME].ob_spec.index = (int32_t)(uint32_t)(char FAR *)cp_time;
    tree[CPDATE].ob_spec.index = (int32_t)(uint32_t)(char FAR *)cp_date;
    cp_layout();
    /* the options' forms and words, now: taken later, in a module's
     * time, the words could be looked up in the wrong resource */
    rsrc_gaddr(R_TREE, ADCPINFO, (void **)&cp_infot);
    rsrc_gaddr(R_TREE, ADCPSETUP, (void **)&cp_setupt);
    for (i = 0; i < CP_NWORDS; i++)
        rsrc_gaddr(R_STRING, CPOPABOUT + i, (void **)&cp_words[i]);
    cp_readinf();
    return TRUE;
}

/* Desk -> Control Panel: the window, opened -- or brought to the top if
 * it is open already. */
void cp_open(void)
{
    WORD dx, dy, dw, dh, bx, by, w, h, x, y;

    if (cp_wh >= 0) {
        wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
        return;
    }
    cp_findcpx();
    cp_xcpb_init();
    cp_clock();
    cp_fill();
    wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
    wind_calc(WC_BORDER, CP_KIND, 0, 0, tree[CPROOT].ob_width,
              tree[CPROOT].ob_height, &bx, &by, &w, &h);
    /* Centred on the desk.  NOT `x = dw > w ? ... : dx` -- x was handed
     * to wind_calc by address, and a ?: joined into an address-taken
     * variable is wrong at every -O (B9, tools/ccbug): the window opened
     * at x = $5C01, off the screen.  So x and y are not the variables
     * wind_calc writes, and they are set by plain ifs. */
    x = dx;
    if (dw > w)
        x = (WORD)(dx + (WORD)((UWORD)(dw - w) / 2));
    y = dy;
    if (dh > h)
        y = (WORD)(dy + (WORD)((UWORD)(dh - h) / 2));
    cp_wh = wind_create(CP_KIND, x, y, w, h);
    if (cp_wh < 0) {
        cp_xcpb.alert = XAL_MEM_ERR;    /* no window left */
        cp_gen_alert((uint32_t)(XCPB FAR *)&cp_xcpb);
        return;
    }
    wind_set_str(cp_wh, WF_NAME, cp_title);
    wind_open(cp_wh, x, y, w, h);
    cp_place();
}

/* WM_SIZED: the window has no sizer, so the AES sends this when the LOOK
 * changes (src/aes/wind.c) -- the 3D frame is thicker, and the same frame
 * leaves a smaller work area.  The window is made the size the tree needs
 * again, at the same place, rather than the list losing its bottom edge
 * (General's Look -> 3D, with the panel open, took 4 pixels off it). */
static void cp_fit(void)
{
    WORD x, y, w, h, bx, by;

    if (cp_wh < 0)
        return;
    wind_get(cp_wh, WF_WORKXYWH, &x, &y, &w, &h);
    wind_calc(WC_BORDER, CP_KIND, x, y, tree[CPROOT].ob_width,
              tree[CPROOT].ob_height, &bx, &by, &w, &h);
    wind_set(cp_wh, WF_CURRXYWH, bx, by, w, h);
    cp_place();
}

static void cp_close(void)
{
    if (cp_wh < 0)
        return;
    wind_close(cp_wh);
    wind_delete(cp_wh);
    cp_wh = -1;
}

/* AC_CLOSE: the AES has destroyed the window already (src/aes/menu.c). */
void cp_acclose(void)
{
    cp_wh = -1;
}

/* ---- the options (phase 140, docs/cpanel-plan.md step 4) ---------------
 *
 * XControl's: an Options button in the strip, and its pop-up -- About and
 * Setup always, Open CPX and CPX Info with a module picked -- and two
 * forms of the panel's own, run in the window as a module's form is run.
 * Reload, Unload, Activate and Deactivate are step 4's second half.
 */
/* One of the panel's own forms, in the window: its root over the work
 * area, drawn; then each end of it, as the object, or CP_CLOSER for the
 * window's closer (OK, XControl's rule) or CP_GONE for AC_CLOSE (Cancel).
 * Through the panel's Xform_do, as a module's form. */
static void cp_formopen(OBJECT *ft)
{
    ft[ROOT].ob_x = cp_work.g_x;
    ft[ROOT].ob_y = cp_work.g_y;
    ft[ROOT].ob_width = cp_work.g_w;
    ft[ROOT].ob_height = cp_work.g_h;
    cp_formdraw(ft, &cp_work);
}

static WORD cp_formnext(OBJECT *ft)
{
    WORD msg[8], r;

    for (;;) {
        r = cpx_xform_do((XCPB FAR *)&cp_xcpb, ft, 0, msg);
        if (r != -1)
            return (WORD)(r & 0x7FFF);
        if (msg[0] == WM_CLOSED)
            return CP_CLOSER;
        if (msg[0] == AC_CLOSE)
            return CP_GONE;
    }
}

/* ...and the list back, unless the window went */
static void cp_formdone(void)
{
    if (cp_wh < 0)
        return;
    cp_fill();
    cp_place();
    cp_draw(CPROOT, MAX_DEPTH, &cp_work);
}

static void cp_obgrect(OBJECT *t, WORD ob, GRECT *r)
{
    objc_offset(t, ob, &r->g_x, &r->g_y);
    r->g_w = t[ob].ob_width;
    r->g_h = t[ob].ob_height;
}

/* one object of a form again, with the margin a button's frame takes */
static void cp_redrawob(OBJECT *t, WORD ob)
{
    GRECT b;

    cp_obgrect(t, ob, &b);
    b.g_x = (WORD)(b.g_x - 2);
    b.g_y = (WORD)(b.g_y - 2);
    b.g_w = (WORD)(b.g_w + 4);
    b.g_h = (WORD)(b.g_h + 4);
    cp_formdraw(t, &b);
}

/* the panel's own pop-up, as a module's: through its block */
static WORD cp_pick(char **items, WORD n, WORD dflt, OBJECT *t, WORD ob)
{
    cp_xcpb.pu_items = (uint32_t)items;
    cp_xcpb.pu_n = n;
    cp_xcpb.pu_default = dflt;
    cp_xcpb.pu_font = 3;
    cp_obgrect(t, ob, &cp_xcpb.pu_button);
    cp_xcpb.pu_world = cp_work;
    /* through the block's pointer, as a module calls it: called by name,
     * the compiler inlined all 1,900 bytes of cp_popup here -- a second
     * copy of it in an accessory that has to fit three banks */
    cp_xcpb.Popup((uint32_t)(XCPB FAR *)&cp_xcpb);
    return cp_xcpb.pu_ret;
}

static void cp_spec(OBJECT *t, WORD ob, const char *s)
{
    t[ob].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)s;
}

/* CPX INFO: what the picked module's header says -- its file, version,
 * id, whether it stays and whether it is loaded at boot -- XControl's
 * four and one more. */
static void cp_info(void)
{
    CPXSLOT FAR *sl;
    UWORD v, f;
    uint32_t id;
    WORD i;

    if (cp_sel < 0 || !cp_infot)
        return;
    sl = cpx_slot(cpx_table, cpx_stride, cpx_row[cp_sel]);
    for (i = 0; i < 13 && sl->file[i]; i++)
        cp_ifile[i] = sl->file[i];
    cp_ifile[i] = 0;
    v = sl->hdr.cpx_version;            /* BCD, as XControl prints it */
    cp_iver[0] = (char)('0' + ((v >> 12) & 15));
    cp_iver[1] = (char)('0' + ((v >> 8) & 15));
    cp_iver[2] = '.';
    cp_iver[3] = (char)('0' + ((v >> 4) & 15));
    cp_iver[4] = (char)('0' + (v & 15));
    cp_iver[5] = 0;
    id = (uint32_t)sl->hdr.cpx_id;
    for (i = 0; i < 4; i++) {
        char c = (char)((id >> (24 - 8 * i)) & 0xFF);

        if (c < ' ' || c > '~')
            c = '.';
        cp_iid[i] = c;
    }
    cp_iid[4] = 0;
    f = sl->hdr.flags;
    cp_spec(cp_infot, CIFILE, cp_ifile);
    cp_spec(cp_infot, CIVER, cp_iver);
    cp_spec(cp_infot, CIID, cp_iid);
    cp_spec(cp_infot, CIRES, CP_WORD(CPNO));
    if (f & CPX_RESIDENT)
        cp_spec(cp_infot, CIRES, CP_WORD(CPYES));
    cp_spec(cp_infot, CIBOOT, CP_WORD(CPNO));
    if (f & (CPX_BOOTINIT | CPX_SETONLY))
        cp_spec(cp_infot, CIBOOT, CP_WORD(CPYES));
    cp_formopen(cp_infot);
    (void)cp_formnext(cp_infot);        /* OK, the closer or AC_CLOSE */
    cp_infot[CIOK].ob_state = NORMAL;
    cp_formdone();
}

/* SETUP: the clock's way, a pop-up; Save writes it to CONTROL.INF; OK
 * (or the closer) uses it, Cancel (or AC_CLOSE) does not. */
static void cp_setup(void)
{
    char *ways[2];
    WORD h12 = cp_hour12, r;

    if (!cp_setupt)
        return;
    ways[0] = CP_WORD(CPH24);
    ways[1] = CP_WORD(CPH12);
    cp_spec(cp_setupt, CSCLOCK, ways[h12]);
    cp_formopen(cp_setupt);
    for (;;) {
        r = cp_formnext(cp_setupt);
        if (r == CSCLOCK) {
            WORD k = cp_pick(ways, 2, h12, cp_setupt, CSCLOCK);

            if (k >= 0)
                h12 = k;
            cp_spec(cp_setupt, CSCLOCK, ways[h12]);
            cp_setupt[CSCLOCK].ob_state = NORMAL;
            cp_redrawob(cp_setupt, CSCLOCK);
            continue;
        }
        if (r == CSSAVE) {
            if (!cp_writeinf(h12)) {
                cp_xcpb.alert = XAL_FILE_ERR;
                cp_gen_alert((uint32_t)(XCPB FAR *)&cp_xcpb);
            }
            cp_setupt[CSSAVE].ob_state = NORMAL;
            cp_redrawob(cp_setupt, CSSAVE);
            continue;
        }
        if (r == CSOK || r == CP_CLOSER)
            cp_hour12 = h12;
        break;
    }
    cp_setupt[CSOK].ob_state = NORMAL;
    cp_setupt[CSCANCEL].ob_state = NORMAL;
    cp_clock();
    cp_formdone();
}

/* THE OPTIONS BUTTON: its pop-up, and what was picked */
static void cp_options(void)
{
    char *items[4];
    WORD n = 2, k;

    items[0] = CP_WORD(CPOPABOUT);
    items[1] = CP_WORD(CPOPSETUP);
    if (cp_sel >= 0) {
        items[2] = CP_WORD(CPOPOPEN);
        items[3] = CP_WORD(CPOPINFO);
        n = 4;
    }
    k = cp_pick(items, n, -1, tree, CPOPTS);
    cp_optpick = k;
    tree[CPOPTS].ob_state = NORMAL;
    if (k == 0)
        (void)form_alert(1, CP_WORD(CPABOUT));
    else if (k == 1)
        cp_setup();
    else if (k == 2)
        cp_openrow(cp_sel);
    else if (k == 3)
        cp_info();
}

/* A press in the work area: a slot picked (twice, opened), or the scroll
 * bar.  Then the button up, so one press is one press. */
static void cp_button(WORD mx, WORD my, WORD nc)
{
    WORD ob = objc_find(tree, CPROOT, MAX_DEPTH, mx, my);
    WORD x, y, mb, ks;

    if (ob >= CPSLOT0 && ob < CPSBAR) {
        WORD row = (WORD)(cp_top + (WORD)((UWORD)(ob - CPSLOT0) / SLOT_OBS));
        if (row < cp_rows) {
            cp_select(row);
            if (nc >= 2)
                cp_openrow(row);
        }
    } else if (ob == CPUP) {
        cp_scrollto((WORD)(cp_top - 1));
    } else if (ob == CPDOWN) {
        cp_scrollto((WORD)(cp_top + 1));
    } else if (ob == CPSLIDER && cp_rows > N_VIS) {
        LONG pos = graf_slidebox(tree, CPTRACK, CPSLIDER, 1);
        cp_scrollto((WORD)((pos * (cp_rows - N_VIS) + 500L) / 1000L));
    } else if (ob == CPTRACK) {
        objc_offset(tree, CPSLIDER, &x, &y);
        cp_scrollto((WORD)(my < y ? cp_top - N_VIS : cp_top + N_VIS));
    } else if (ob == CPOPTS) {
        cp_options();
    }
    graf_mkstate(&x, &y, &mb, &ks);
    if (mb & 1)
        evnt_button(1, 1, 0, &x, &y, &mb, &ks);
}

static void cp_key(WORD key)
{
    switch ((UWORD)key) {
    case KEY_UP:
        cp_select(cp_sel > 0 ? (WORD)(cp_sel - 1) : 0);
        break;
    case KEY_DOWN:
        cp_select(cp_sel < 0 ? 0 : (WORD)(cp_sel + 1));
        break;
    case KEY_RETURN:
        if (cp_sel >= 0)
            cp_openrow(cp_sel);
        break;
    case KEY_ESC:
        cp_close();
        break;
    default:
        break;
    }
}

/* A message about the window. */
void cp_message(const WORD *msg)
{
    GRECT a;

    if (cp_wh < 0 || msg[3] != cp_wh)
        return;
    switch (msg[0]) {
    case WM_REDRAW:
        a.g_x = msg[4]; a.g_y = msg[5];
        a.g_w = msg[6]; a.g_h = msg[7];
        cp_draw(CPROOT, MAX_DEPTH, &a);
        break;
    case WM_TOPPED:
        wind_set(cp_wh, WF_TOP, 0, 0, 0, 0);
        break;
    case WM_MOVED:
        wind_set(cp_wh, WF_CURRXYWH, msg[4], msg[5], msg[6], msg[7]);
        cp_place();
        break;
    case WM_SIZED:
        cp_fit();
        break;
    case WM_CLOSED:
        cp_close();
        break;
    default:
        break;
    }
}

/* One turn of the accessory's loop: a message only while the window is
 * shut, and while it is open the presses and keys this window owns too,
 * and the clock's second.  Answers what happened; a message is the
 * caller's to dispatch. */
WORD cp_wait(WORD *msg)
{
    WORD ev, mx, my, mb, ks, kr, nc;

    if (cp_wh < 0) {
        evnt_mesag(msg);
        return MU_MESAG;
    }
    ev = evnt_multi(MU_MESAG | MU_BUTTON | MU_KEYBD | MU_TIMER, 2, 1, 1,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    msg, 1000, 0, &mx, &my, &mb, &ks, &kr, &nc);
    if (ev & MU_BUTTON)
        cp_button(mx, my, nc);
    if ((ev & MU_KEYBD) && cp_wh >= 0)
        cp_key(kr);
    if ((ev & MU_TIMER) && cp_wh >= 0 && cp_clock())
        cp_drawstrip();
    return ev;
}
