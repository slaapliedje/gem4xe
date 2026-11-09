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

#define CP_KIND     (NAME | CLOSER | MOVER)
#define CP_COLS     32          /* XControl's 256 pixels of 8 */
#define CP_ICONW    32          /* a CPX icon is 32 x 24 (cpx.h) */
#define CP_ICONH    24
#define CP_ICOLS    11          /* the icon's column, its text under it */
#define CP_TCOLS    17          /* a title: title_txt less its NUL */

#define KEY_UP      0x4800      /* the ST's key words (src/desk/desktop.c) */
#define KEY_DOWN    0x5000
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
    cp_set(CPTIME, wchar, 2, 5 * wchar, hchar);
    cp_set(CPDATE, w - 9 * wchar, 2, 8 * wchar, hchar);
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
static char cp_time[6], cp_date[9];

static void cp_two(char *p, UWORD v)
{
    p[0] = (char)('0' + (v / 10) % 10);
    p[1] = (char)('0' + v % 10);
}

static WORD cp_clock(void)
{
    UWORD t = (UWORD)Tgettime(), d = (UWORD)Tgetdate();
    char tm[6], dt[9];
    WORD i, changed = 0;

    cp_two(tm, t >> 11);
    tm[2] = ':';
    cp_two(tm + 3, (t >> 5) & 63);
    tm[5] = 0;
    cp_two(dt, d & 31);
    dt[2] = '/';
    cp_two(dt + 3, (d >> 5) & 15);
    dt[5] = '/';
    cp_two(dt + 6, ((d >> 9) + 80) % 100);
    dt[8] = 0;
    for (i = 0; i < 6; i++)
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
 * WHAT IS FORWARDED is a key, a button and a timer tick -- the keys and
 * the presses only reach this process while the window is on top (the
 * AES's rule, phase 134) -- and a redraw, rectangle by rectangle, as
 * XControl's cpx_draw is called: the module draws with the rectangle as
 * its clip.  The window's own business is done here around it: topped,
 * moved (cpx_wmove when the module has one; a redraw of the whole work
 * area when it has not), closed, or taken away by AC_CLOSE.
 *
 * Each entry is given a `quit` zeroed first, and the loop ends the moment
 * one comes back non-zero -- so a module says "I am done" once and is not
 * asked again.  AN ENTRY MAY BE 0, and most of a simple module's are.
 *
 * THE TIMER IS ALWAYS ASKED FOR, at a rate the panel chooses rather than
 * the module: Set_Evnt_Mask is how XCONTROL lets a module say what it
 * wants, and that is step 3's.  100 ms is a rate a clock or a sound can
 * work with and costs a module that ignores cpx_timer nothing.
 */
#define CPX_TICK  100L

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
    WORD msg[8], mx, my, mb, ks, kr, nc, gone = 0;
    uint32_t pb = (uint32_t)(CPXPB FAR *)&cp_pb;

    for (;;) {
        WORD ev = evnt_multi(MU_KEYBD | MU_BUTTON | MU_TIMER | MU_MESAG,
                             2, 1, 1,
                             0, 0, 0, 0, 0,
                             0, 0, 0, 0, 0,
                             msg,
                             (WORD)(CPX_TICK & 0xFFFFL),
                             (WORD)(CPX_TICK >> 16),
                             &mx, &my, &mb, &ks, &kr, &nc);
        cp_pb.mouse.x = mx;
        cp_pb.mouse.y = my;
        cp_pb.mouse.buttons = mb;
        cp_pb.mouse.kstate = ks;
        cp_pb.quit = 0;

        if ((ev & MU_KEYBD) && info->cpx_key) {
            cp_pb.kstate = ks;
            cp_pb.key = kr;
            info->cpx_key(pb);
        }
        if ((ev & MU_BUTTON) && info->cpx_button) {
            cp_pb.nclicks = nc;
            info->cpx_button(pb);
        }
        if ((ev & MU_TIMER) && info->cpx_timer)
            info->cpx_timer(pb);
        if (ev & MU_MESAG) {
            WORD i;
            for (i = 0; i < 8; i++)
                cp_pb.msg[i] = msg[i];
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
    if (info->cpx_close)
        info->cpx_close(pb);
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
 * memory alert, which is what it nearly always is. */
static void cp_opencpx(WORD i)
{
    CPXSLOT FAR *sl;
    CPXINFO FAR *info;

    if (i < 0 || i >= cpx_total || !cpx_table)
        return;
    sl = cpx_slot(cpx_table, cpx_stride, i);
    if (!sl->info && Cpxload(i, 1) != 0) {
        cp_xcpb.alert = XAL_MEM_ERR;
        cp_gen_alert((uint32_t)(XCPB FAR *)&cp_xcpb);
        return;
    }
    info = (CPXINFO FAR *)sl->info;
    if (info && info->cpx_call) {
        cp_xcpb_init();
        cp_xcpb.which = i;              /* who is about to call back */
        cp_xcpb.buffer = (uint32_t)(char FAR *)sl->hdr.buffer;
        cp_pb.xcpb = (uint32_t)(XCPB FAR *)&cp_xcpb;
        cp_pb.rect = cp_work;
        cp_pb.quit = 0;
        cp_pb.ret = 0;
        /* the module draws into the whole work area: clear it first */
        cp_draw(CPROOT, 0, &cp_work);
        info->cpx_call((uint32_t)(CPXPB FAR *)&cp_pb);
        if (cp_pb.ret)
            cp_drivecpx(info);          /* an EVENT CPX: it wants events */
    }
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
