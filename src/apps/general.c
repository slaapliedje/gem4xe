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
 * A FORM CPX, WHICH IS THE SIMPLE HALF OF THE CONTRACT.  XCONTROL has
 * two kinds: a form CPX whose dialog the host runs, and an event CPX
 * that is handed events one at a time.  cpx_call here runs its own
 * form_do and returns when the dialog closes, so the host's loop is
 * simply blocked for the duration.  That is honest for a settings
 * dialog and needs nothing the AES does not already do; an event CPX
 * wants the panel to forward cpx_key and its kind, which is the next
 * piece of work and is why those entries exist in CPXINFO already.
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

static SAVEDS WORD gn_cpx_call(const GRECT *r)
{
    WORD x, y, w, h, ret, ob, i, j;

    (void)r;
    if (!tree)
        return 0;

    dc0 = evnt_dclick(0, 0);
    {
        MN_SET set;
        menu_settings(MNS_GET, &set);
        ms0 = set.mn_display;
    }
    for (i = 0; i < N_DC; i++)
        tree[GNDC0 + i].ob_state = (UWORD)(i == dc0 ? SELECTED : NORMAL);
    j = gn_index(ms0);
    for (i = 0; i < N_MN; i++)
        tree[GNMN0 + i].ob_state = (UWORD)(i == j ? SELECTED : NORMAL);
    tree[GNOK].ob_state = NORMAL;
    tree[GNCNCL].ob_state = NORMAL;
    gn_show();

    form_center(tree, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_GROW, 0, 0, 0, 0, x, y, w, h);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, w, h);

    for (;;) {
        ret = form_do(tree, GNDATE);
        ob = (WORD)(ret & 0x7FFF);
        if (ob == GNOK || ob == GNCNCL)
            break;
        if (ob >= GNDC0 && ob < GNDC0 + N_DC)
            evnt_dclick((WORD)(ob - GNDC0), 1);
        else if (ob >= GNMN0 && ob < GNMN0 + N_MN)
            gn_setdelay(gn_ms[ob - GNMN0]);
    }

    if (ob == GNOK)
        gn_apply_clock();
    else {                              /* exactly what was there */
        evnt_dclick(dc0, 1);
        gn_setdelay(ms0);
    }

    tree[GNOK].ob_state = NORMAL;
    tree[GNCNCL].ob_state = NORMAL;
    form_dial(FMD_SHRINK, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
    return 1;
}

static SAVEDS void gn_cpx_close(WORD flag)
{
    (void)flag;
}

CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr)
{
    static const char title[] = "General";
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

    hdr->magic = CPX_MAGIC;
    hdr->flags = 0;
    hdr->cpx_id = 0x47454E4CL;          /* 'GENL' */
    hdr->cpx_version = 1;
    for (i = 0; title[i] && i < 17; i++)
        hdr->title_txt[i] = title[i];
    hdr->title_txt[i] = 0;
    for (i = 0; title[i] && i < 13; i++)
        hdr->i_text[i] = title[i];
    hdr->i_text[i] = 0;

    ginfo.cpx_call = gn_cpx_call;
    ginfo.cpx_close = gn_cpx_close;
    return &ginfo;
}
