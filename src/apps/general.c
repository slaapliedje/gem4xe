/* general.c -- GENERAL.CPX, the first real control panel extension.
 *
 * The ST's General panel is the everyday settings and the clock, and
 * this is that: the two settings this AES actually honours, and the
 * date and time.  It is a MODULE -- the panel finds it, lists it and
 * opens it, and owns none of what is below (src/app/cpx.h).
 *
 * WHY THIS ONE FIRST.  The panel's own settings were the panel's until
 * now, which made CONTROL.ACC a dialog that could never grow.  Moving
 * them into a module is what proves the split is real rather than
 * decorative: the same two controls, the same live behaviour, in a file
 * the panel has never heard of and can be shipped without.
 *
 * A FORM CPX, AND IT SAYS SO BY RETURNING 0.  XCONTROL has two kinds:
 * a form CPX that runs its own form and is finished when cpx_call
 * returns, and an event CPX that draws itself, returns 1, and is then
 * handed events one at a time by the host.  This is the first, which is
 * the honest shape for a page of radio buttons and two fields.  Since
 * phase 136 the form is in the PANEL'S WINDOW, through the panel's
 * Xform_do (src/app/cpx.h), as XControl's are: the desktop goes on
 * working beside it, and the panel answers the window's redraws and
 * moves while the form is up.
 *
 * The other kind is worth having for a module whose control has to show
 * its own effect while it is being moved -- a mouse speed, a sound --
 * and src/m35_cpx.c is the worked example of it.
 *
 * EVERY PICK APPLIES IMMEDIATELY, as the panel's did, and for the same
 * reason: the only question a double-click number raises is "can I
 * double-click this fast?", which can only be answered about the rate
 * in force now.  Cancel therefore has real work and puts back the
 * values the dialog was entered with -- the delay as the LONG it was,
 * not as the button nearest it.
 *
 * THE CLOCK IS SET ONLY IF IT WAS TYPED IN.  Tsetdate/Tsettime reach
 * the Ultimate 1MB's DS1305 where there is one, and writing the same
 * second back to it on every OK would be a needless write to a battery
 * clock -- so the fields are compared with what they were shown as, and
 * an untouched field is left alone.
 */
#include "cpx.h"
#include "generalrsc.h"

static OBJECT FAR *tree;
static CPXINFO ginfo;

/* Shown, so that OK can tell a typed field from an untouched one. */
static char shown_date[16];
static char shown_time[16];

static const LONG gn_ms[N_MN] = { 0L, 100L, 200L, 400L };

/* Entry values, for Cancel. */
static WORD dc0;
static LONG ms0;
static WORD look0;

static WORD gn_index(LONG ms)
{
    WORD i, best = 0;
    LONG d, bd = 0x7FFFFFFFL;

    for (i = 0; i < N_MN; i++) {
        d = ms - gn_ms[i];
        if (d < 0)
            d = -d;
        if (d < bd) {
            bd = d;
            best = i;
        }
    }
    return best;
}

static LONG ms_now(void)
{
    MN_SET set;

    menu_settings(MNS_GET, &set);
    return set.mn_display;
}

static void gn_setdelay(LONG ms)
{
    MN_SET set;

    menu_settings(MNS_GET, &set);
    set.mn_display = ms;
    menu_settings(MNS_SET, &set);
}

/* ---- the fields -------------------------------------------------------
 * A G_FTEXT's te_ptext is the characters the person typed, with the
 * template's punctuation NOT in it -- the AES keeps only the places the
 * underscores marked.  So "25/12/26" is six digits here, and both
 * directions below work on those six.
 */
static char FAR *gn_text(WORD ob)
{
    TEDINFO FAR *ted = (TEDINFO FAR *)(uint32_t)tree[ob].ob_spec.index;
    return (char FAR *)(uint32_t)ted->te_ptext;
}

static void gn_put2(char FAR *p, WORD v)
{
    p[0] = (char)('0' + (v / 10) % 10);
    p[1] = (char)('0' + v % 10);
}

static WORD gn_get2(const char FAR *p)
{
    WORD a = p[0] - '0', b = p[1] - '0';

    if (a < 0 || a > 9 || b < 0 || b > 9)
        return -1;
    return (WORD)(a * 10 + b);
}

static void gn_same(char *dst, const char FAR *src, WORD n)
{
    WORD i;

    for (i = 0; i < n; i++)
        dst[i] = src[i];
    dst[n] = 0;
}

static WORD gn_differs(const char *was, const char FAR *now, WORD n)
{
    WORD i;

    for (i = 0; i < n; i++)
        if (was[i] != now[i])
            return 1;
    return 0;
}

/* GEMDOS packs a date as year-1980 in bits 15..9, month in 8..5 and day
 * in 4..0, and a time as hour in 15..11, minute in 10..5 and the second
 * HALVED in 4..0 -- which is why the seconds field is not offered: it
 * cannot represent an odd one and a control that silently rounds is
 * worse than no control. */
static void gn_show(void)
{
    UWORD d = (UWORD)Tgetdate(), t = (UWORD)Tgettime();
    char FAR *p = gn_text(GNDATE);

    gn_put2(p + 0, (WORD)(d & 0x1F));               /* day */
    gn_put2(p + 2, (WORD)((d >> 5) & 0x0F));        /* month */
    gn_put2(p + 4, (WORD)((1980 + (d >> 9)) % 100));
    p[6] = 0;
    gn_same(shown_date, p, 6);

    p = gn_text(GNTIME);
    gn_put2(p + 0, (WORD)((t >> 11) & 0x1F));       /* hour */
    gn_put2(p + 2, (WORD)((t >> 5) & 0x3F));        /* minute */
    p[4] = 0;
    gn_same(shown_time, p, 4);
}

/* Both halves are checked before either is written, so a bad time does
 * not leave a good date half-applied. */
static void gn_apply_clock(void)
{
    const char FAR *d = gn_text(GNDATE);
    const char FAR *t = gn_text(GNTIME);
    WORD day, mon, yr, hh, mm;

    if (gn_differs(shown_date, d, 6)) {
        day = gn_get2(d + 0);
        mon = gn_get2(d + 2);
        yr  = gn_get2(d + 4);
        if (day >= 1 && day <= 31 && mon >= 1 && mon <= 12 && yr >= 0)
            Tsetdate((UWORD)((((yr + 2000 - 1980) & 0x7F) << 9)
                             | ((mon & 0x0F) << 5) | (day & 0x1F)));
    }
    if (gn_differs(shown_time, t, 4)) {
        hh = gn_get2(t + 0);
        mm = gn_get2(t + 2);
        if (hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59)
            Tsettime((UWORD)(((hh & 0x1F) << 11) | ((mm & 0x3F) << 5)));
    }
}

/* ---- the contract -----------------------------------------------------*/

/* ---- remembering ------------------------------------------------------
 *
 * The 64 bytes in this module's own header, which the panel reaches
 * through XCPB and writes to a file beside the module (src/app/cpx.h).
 * Four bytes are used:
 *
 *   [0]  a mark, so an unsaved buffer of zeroes is not read as "rate 0"
 *   [1]  the double-click rate
 *   [2]  which sub-menu delay
 *   [3]  the look: 0 flat, 1 3D (src/aes/objc.c) -- 0 in a buffer saved
 *        before there was a choice, which is the flat look it had
 *
 * A MARK RATHER THAN A LENGTH, because a buffer that has never been
 * saved is all zeroes and every field in it is a legal value.  Without
 * something that cannot occur by accident, a machine that had never
 * saved would come up claiming the fastest double-click and no delay --
 * which is a setting nobody chose, arriving silently. */
#define GN_MARK   0x47                  /* 'G' */

/* The look, which the AES keeps: G4_3DLOOK is gem4xe's own objc_sysvar. */
static WORD gn_look(void)
{
    WORD on = 0, d;

    objc_sysvar(SV_INQUIRE, G4_3DLOOK, 0, 0, &on, &d);
    return on;
}

static void gn_setlook(WORD on)
{
    WORD d;

    objc_sysvar(SV_SET, G4_3DLOOK, on, 0, &d, &d);
}

static XCPB FAR *gn_xcpb;

static void gn_restore(void)
{
    const char FAR *b;
    WORD dc, mn;

    if (!gn_xcpb || !gn_xcpb->buffer)
        return;
    b = (const char FAR *)gn_xcpb->buffer;
    if ((b[0] & 0xFF) != GN_MARK)
        return;                         /* nothing has been saved yet */
    dc = b[1] & 0xFF;
    mn = b[2] & 0xFF;
    if (dc >= 0 && dc < N_DC)
        evnt_dclick(dc, 1);
    if (mn >= 0 && mn < N_MN)
        gn_setdelay(gn_ms[mn]);
    gn_setlook((WORD)(b[3] == 1));
}

static void gn_remember(WORD dc, WORD mn, WORD look)
{
    char FAR *b;

    if (!gn_xcpb || !gn_xcpb->buffer || !gn_xcpb->CPX_Save)
        return;
    b = (char FAR *)gn_xcpb->buffer;
    b[0] = (char)GN_MARK;
    b[1] = (char)dc;
    b[2] = (char)mn;
    b[3] = (char)look;
    gn_xcpb->CPX_Save((uint32_t)gn_xcpb);
}

/* THE SUB-MENU DELAY'S POP-UP (phase 138, the panel's Popup): its four
 * names are GENERAL.RSC's free strings, the button's text is pointed at
 * the one in force, and the pick applies at once, as every pick here
 * does.  The names are taken at cpx_init, beside the tree: at cpx_call
 * this runs in the panel's process, and rsrc_gaddr answered from the
 * PANEL's resource -- the button read "...not be read or written". */
static char *gn_mnname[N_MN];

static void gn_mnshow(WORD j)
{
    if (j >= 0 && j < N_MN && gn_mnname[j])
        tree[GNMNBTN].ob_spec.index = (int32_t)(uint32_t)gn_mnname[j];
}

static void gn_mnpick(void)
{
    GRECT bt, world;
    WORD x, y, r;

    objc_offset(tree, GNMNBTN, &x, &y);
    bt.g_x = x;
    bt.g_y = y;
    bt.g_w = tree[GNMNBTN].ob_width;
    bt.g_h = tree[GNMNBTN].ob_height;
    world.g_x = tree[ROOT].ob_x;
    world.g_y = tree[ROOT].ob_y;
    world.g_w = tree[ROOT].ob_width;
    world.g_h = tree[ROOT].ob_height;
    r = cpx_popup(gn_xcpb, gn_mnname, N_MN, gn_index(ms_now()), 3, &bt,
                  &world);
    tree[GNMNBTN].ob_state = NORMAL;
    if (r >= 0 && r < N_MN) {
        gn_setdelay(gn_ms[r]);
        gn_mnshow(r);
    }
    objc_draw(tree, ROOT, MAX_DEPTH, bt.g_x - 2, bt.g_y - 2,
              bt.g_w + 4, bt.g_h + 4);
}

static SAVEDS void gn_cpx_call(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
    WORD ret, ob = GNCNCL, i, j, gone = 0;
    WORD msg[8];

    pb->ret = 0;                        /* a FORM CPX: see the end */
    if (!tree)
        return;
    /* The panel's block arrives here rather than at cpx_init, because
     * the AES loads a module at boot and the panel is not in that
     * conversation.  Kept, and what was saved last time is applied
     * BEFORE the dialog is filled in from the live values -- so the
     * dialog shows what the machine is actually doing either way. */
    gn_xcpb = (XCPB FAR *)pb->xcpb;
    gn_restore();
    /* BOOTING: act and return, with no dialog.  The panel opens a
     * CPX_BOOTINIT module once at start-up purely so it can do the line
     * above; there is nobody to show anything to yet (src/app/cpx.h). */
    if (gn_xcpb && gn_xcpb->booting)
        return;
    /* IN THE PANEL'S WINDOW (phase 136), through its Xform_do: a panel
     * without one has no window to put this form in, and the module has
     * nothing to show there. */
    if (!gn_xcpb || !gn_xcpb->Xform_do)
        return;

    dc0 = evnt_dclick(0, 0);
    {
        MN_SET set;
        menu_settings(MNS_GET, &set);
        ms0 = set.mn_display;
    }
    for (i = 0; i < N_DC; i++)
        tree[GNDC0 + i].ob_state = (UWORD)(i == dc0 ? SELECTED : NORMAL);
    j = gn_index(ms0);
    gn_mnshow(j);
    look0 = gn_look();
    for (i = 0; i < N_LOOK; i++)
        tree[GN3D0 + i].ob_state = (UWORD)(i == look0 ? SELECTED : NORMAL);
    tree[GNOK].ob_state = NORMAL;
    tree[GNCNCL].ob_state = NORMAL;
    gn_show();

    /* the whole work area, the panel's window being the frame: the panel
     * has cleared it, and moves tree[ROOT] with the window from here */
    tree[ROOT].ob_x = pb->rect.g_x;
    tree[ROOT].ob_y = pb->rect.g_y;
    tree[ROOT].ob_width = pb->rect.g_w;
    tree[ROOT].ob_height = pb->rect.g_h;
    objc_draw(tree, ROOT, MAX_DEPTH, pb->rect.g_x, pb->rect.g_y,
              pb->rect.g_w, pb->rect.g_h);

    for (;;) {
        ret = cpx_xform_do(gn_xcpb, tree, GNDATE, msg);
        if (ret == -1) {
            /* XControl's rule: the closer keeps what was set, as OK;
             * AC_CLOSE -- the window gone -- puts it back, as Cancel.
             * Anything else -- CT_KEY, a key with no character -- is
             * not this form's, and it goes on. */
            if (msg[0] == WM_CLOSED)
                gone = 1;
            else if (msg[0] == AC_CLOSE)
                gone = 2;
            else
                continue;
            break;
        }
        ob = (WORD)(ret & 0x7FFF);
        if (ob == GNOK || ob == GNCNCL)
            break;
        if (ob >= GNDC0 && ob < GNDC0 + N_DC)
            evnt_dclick((WORD)(ob - GNDC0), 1);
        else if (ob == GNMNBTN)
            gn_mnpick();
        else if (ob >= GN3D0 && ob < GN3D0 + N_LOOK
                 && (WORD)(ob - GN3D0) != gn_look()) {
            /* the look, at once, and this form in it to show it -- where
             * the window has it now, which a move may have changed */
            gn_setlook((WORD)(ob - GN3D0));
            objc_draw(tree, ROOT, MAX_DEPTH, tree[ROOT].ob_x,
                      tree[ROOT].ob_y, tree[ROOT].ob_width,
                      tree[ROOT].ob_height);
        }
    }

    if (ob == GNOK || gone == 1) {
        gn_apply_clock();
        gn_remember(evnt_dclick(0, 0), gn_index(ms_now()), gn_look());
    }
    else {                              /* exactly what was there */
        evnt_dclick(dc0, 1);
        gn_setdelay(ms0);
        gn_setlook(look0);
    }

    tree[GNOK].ob_state = NORMAL;
    tree[GNCNCL].ob_state = NORMAL;
    if (gn_look() != look0) {
        /* everything on the screen was drawn in the other look: the
         * whole desktop is redrawn, every window with it */
        WORD dx, dy, dw, dh;
        wind_get(0, WF_CURRXYWH, &dx, &dy, &dw, &dh);
        form_dial(FMD_FINISH, 0, 0, 0, 0, dx, dy, dw, dh);
    }
    /* pb->ret stays 0: A FORM CPX, and finished.  Its form ran in the
     * panel's window, and the panel draws its list back over it -- a 1
     * here would leave the panel forwarding events to a module with no
     * form left to put them in (src/app/cpx.h). */
}

static SAVEDS void gn_cpx_close(uint32_t pbaddr)
{
    (void)pbaddr;
}

/* The header -- title, icon, CPX_BOOTINIT -- is src/apps/general.cpxh,
 * in front of this module in the file (tools/mkcpx.py). */
CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb)
{
    WORD i;

    (void)pb;
    /* THE RESOURCE IS TAKEN ONCE AND NEVER FREED, which is right rather
     * than lazy: a module is loaded before the keep mark and kept for
     * the life of the machine (src/aes/shel.c), so its resource is as
     * permanent as an accessory's and freeing it would be freeing
     * something nothing can take back. */
    if (!rsrc_load("GENERAL.RSC"))
        return (CPXINFO FAR *)0;        /* no dialog: decline to appear */
    rsrc_gaddr(R_TREE, ADGENRL, (void **)&tree);
    if (!tree)
        return (CPXINFO FAR *)0;
    for (i = 0; i < N_MN; i++)
        rsrc_gaddr(R_STRING, GNMNSTR0 + i, (void **)&gn_mnname[i]);

    ginfo.cpx_call = gn_cpx_call;
    ginfo.cpx_close = gn_cpx_close;
    return &ginfo;
}
