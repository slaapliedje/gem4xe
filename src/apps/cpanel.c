/* cpanel.c -- the control panel: the settings the AES already honours at
 * run time, and that nothing could reach until now.
 *
 * TWO SETTINGS, BOTH LIVE.  The double-click rate (evnt_dclick) and how
 * long the pointer must rest on an item before its sub-menu opens
 * (menu_settings' mn_display).  menu_settings carries five numbers and
 * the other four are kept and handed back rather than obeyed -- there is
 * no drag tracking and nothing scrolls, which appl_getinfo(AES_MENU)
 * says out loud -- so they are not offered.  A control that moves and
 * changes nothing teaches a wrong model of the machine, and the person
 * finds out by being surprised later.
 *
 * EVERY PICK APPLIES IMMEDIATELY, not on OK.  That is what makes the test
 * box worth having: "can I double-click this fast?" is the only question
 * a number from 1 to 5 raises, and the box can only answer it about the
 * rate the AES is using right now.  The cost is that Cancel has real work
 * to do, so the entry values are kept and put back -- the delay as the
 * LONG it was, not as the button that was nearest it.
 *
 * NO WORKSTATION.  Unlike the clock, this panel draws nothing itself: the
 * AES draws the tree and form_do runs it.  So there is no v_opnvwk here
 * and nothing to hold across an AC_CLOSE.
 *
 * NOTHING IS PERSISTED, and that is a gap rather than a decision.  The
 * desktop owns DESKTOP.INF and nothing at all writes GEM4XE.CFG, so these
 * settings last as long as the machine is up.  A writer for the config is
 * the next piece of work, and it is shared with the resolution picker.
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

/* The delays offered, in milliseconds, against mn_display.  200 is the
 * AES's own initial value (src/aes/menu.c MN_INIT_DISPLAY), so "Normal"
 * is the machine as it starts. */
static const LONG cp_ms[N_MN] = { 0L, 100L, 200L, 400L };

/* ---- the extensions -----------------------------------------------------
 *
 * The AES loads a module at boot and keeps it (src/aes/shel.c, sh_cpx);
 * this panel asks what is there, shows the titles, and calls the one the
 * user picks.  That split is the whole shape of a CPX: the HOST owns the
 * window and the event loop, the MODULE owns the dialog.
 *
 * THE TITLES ARE COPIED, not pointed at.  A row's ob_spec has to be an
 * address the VDI can read at every redraw, and the AES's table is far
 * memory this panel does not own -- copying eighteen bytes once is
 * cheaper to reason about than a lifetime shared with the shell. */
static uint32_t cpx_table;
static WORD     cpx_stride;
static WORD     cpx_n;
static char     cpx_titles[N_CPX][19];

static void cp_findcpx(void)
{
    WORD i, j;

    cpx_n = cpx_count(&cpx_table, &cpx_stride);
    if (cpx_n > N_CPX)
        cpx_n = N_CPX;
    for (i = 0; i < N_CPX; i++) {
        OBJECT *row = &tree[CPX0 + i];
        if (i < cpx_n) {
            CPXSLOT FAR *sl = cpx_slot(cpx_table, cpx_stride, i);
            for (j = 0; j < 18 && sl->hdr.title_txt[j]; j++)
                cpx_titles[i][j] = sl->hdr.title_txt[j];
            cpx_titles[i][j] = 0;
            /* ALL 24 BITS.  This panel is --data-model=large, so its own
             * strings are far; a 16-bit ob_spec here would name bank $00
             * and draw whatever is at the same offset (tools/nearcast.py). */
            row->ob_spec.index = (int32_t)(uint32_t)(char FAR *)cpx_titles[i];
            row->ob_flags = SELECTABLE | RBUTTON | TOUCHEXIT;
        } else {
            row->ob_flags = SELECTABLE | RBUTTON | TOUCHEXIT | HIDETREE;
        }
        row->ob_state = NORMAL;
    }
}

/* Open the selected module: its cpx_call, through the vtable it
 * published when it loaded.  A separately linked module reached by a
 * runtime long-indirect call -- which is safe because every entry in a
 * CPXINFO is `saveds` and sets up its own direct page and data bank
 * (src/app/cpx.h).  0 from cpx_call means it declined to open. */
static WORD cp_opencpx(WORD i, WORD x, WORD y, WORD w, WORD h)
{
    CPXSLOT FAR *sl;
    CPXINFO FAR *info;
    GRECT r;

    if (i < 0 || i >= cpx_n || !cpx_table)
        return 0;
    sl = cpx_slot(cpx_table, cpx_stride, i);
    if (!sl->info)
        return 0;
    info = (CPXINFO FAR *)sl->info;
    if (!info->cpx_call)
        return 0;
    r.g_x = x; r.g_y = y; r.g_w = w; r.g_h = h;
    return info->cpx_call(&r);
}

/* Which button a live value lights.  NEAREST rather than exact: another
 * program may have set a number this panel does not offer, and a panel
 * with nothing selected would say the machine has no setting at all. */
static WORD cp_index(LONG ms)
{
    WORD i, best = 0;
    LONG d, bestd;

    bestd = cp_ms[0] - ms;
    if (bestd < 0)
        bestd = -bestd;
    for (i = 1; i < N_MN; i++) {
        d = cp_ms[i] - ms;
        if (d < 0)
            d = -d;
        if (d < bestd) {
            bestd = d;
            best = i;
        }
    }
    return best;
}

/* A sub-menu delay and nothing else: a SET applies a field only when it
 * is not negative, so -1 leaves the four that are not live alone. */
static void cp_setdelay(LONG ms)
{
    MN_SET set;

    set.mn_display = ms;
    set.mn_drag = -1L;
    set.mn_delay = -1L;
    set.mn_speed = -1L;
    set.mn_height = -1;
    menu_settings(MNS_SET, &set);
}

/* The resource, once.  Separate from the panel because the two happen at
 * different times in an accessory: the shell takes this while the AES is
 * starting up -- before the first program, the only time an accessory may
 * take anything from bank $00 -- and opens the panel whenever somebody
 * chooses it from the Desk menu (src/apps/cpanelacc.c). */
WORD cp_start(void)
{
    if (!rsrc_load("CPANEL.RSC"))
        return FALSE;
    rsrc_gaddr(R_TREE, ADCPANEL, (void **)&tree);
    acc_far = (WORD)(((uint32_t)tree) >> 16);
    return TRUE;
}

void cp_panel(void)
{
    WORD x, y, w, h, ret, ob = CPCNCL, i, j, dc0;
    UWORD st;
    LONG ms0;
    MN_SET set;

    /* What the AES is doing NOW, which is what the panel must show: a
     * program may have changed either of these since it was last open. */
    dc0 = evnt_dclick(0, 0);
    menu_settings(MNS_GET, &set);
    ms0 = set.mn_display;

    for (i = 0; i < N_DC; i++)
        tree[CPDC0 + i].ob_state = (UWORD)(i == dc0 ? SELECTED : NORMAL);
    j = cp_index(ms0);
    for (i = 0; i < N_MN; i++)
        tree[CPMN0 + i].ob_state = (UWORD)(i == j ? SELECTED : NORMAL);
    cp_findcpx();
    tree[CPXOPEN].ob_state = NORMAL;
    tree[CPTEST].ob_state = NORMAL;
    tree[CPOK].ob_state = NORMAL;
    tree[CPCNCL].ob_state = NORMAL;

    form_center(tree, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_GROW, 0, 0, 0, 0, x, y, w, h);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, w, h);

    for (;;) {
        ret = form_do(tree, 0);
        ob = (WORD)(ret & 0x7FFF);
        if (ob == CPOK || ob == CPCNCL)
            break;
        if (ob >= CPDC0 && ob < CPDC0 + N_DC) {
            evnt_dclick((WORD)(ob - CPDC0), 1);
        } else if (ob >= CPMN0 && ob < CPMN0 + N_MN) {
            cp_setdelay(cp_ms[ob - CPMN0]);
        } else if (ob == CPXOPEN) {
            /* Whichever row is lit; none means nothing to open. */
            WORD k, pick = -1;
            for (k = 0; k < cpx_n; k++)
                if (tree[CPX0 + k].ob_state & SELECTED)
                    pick = k;
            tree[CPXOPEN].ob_state = NORMAL;
            objc_draw(tree, CPXOPEN, 0, x, y, w, h);
            if (pick >= 0) {
                cp_opencpx(pick, x, y, w, h);
                objc_draw(tree, ROOT, MAX_DEPTH, x, y, w, h);
            }
        } else if (ob >= CPX0 && ob < CPX0 + N_CPX) {
            /* the radio group does the lighting; nothing else to do */
        } else if (ob == CPTEST) {
            /* form_do sets bit 15 when the second click arrived inside
             * the time the rate above allows.  A single click is the
             * answer "not that fast" and must change nothing -- but
             * form_do has already drawn the box SELECTED, so undo that
             * either way.  Read-modify-write through a temporary: the
             * compiler has a fault in `p->a = p->a OP e` (tools/ccbug). */
            st = tree[CPTEST].ob_state;
            if (ret & 0x8000)
                st ^= CHECKED;
            st &= (UWORD)~SELECTED;
            tree[CPTEST].ob_state = st;
            objc_draw(tree, CPTEST, 0, x, y, w, h);
        }
    }

    if (ob == CPCNCL) {                 /* put back exactly what was there */
        evnt_dclick(dc0, 1);
        cp_setdelay(ms0);
    }

    tree[CPOK].ob_state = NORMAL;
    tree[CPCNCL].ob_state = NORMAL;
    form_dial(FMD_SHRINK, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}
