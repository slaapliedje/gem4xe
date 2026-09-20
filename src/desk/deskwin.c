/* deskwin.c -- folder windows.
 *
 * The donor's deskwin.c and deskfpd.c, with the window half of its
 * desksupp.c and deskact.c, for the one view this desktop has (icons)
 * and the one order (folders first, then by name).  A window is a
 * WNODE (desk.h): the AES window, its box in the screen tree, the rows
 * of the item grid in view, and the PNODE -- the directory it lists,
 * read through Fsfirst/Fsnext into FNODEs in far memory.
 *
 * Opening a drive icon or a folder lists the directory, names the
 * window after the search spec, puts the total on the information
 * line, and builds the window's items -- a G_ICON per entry in the rows
 * shown -- under its box in the screen tree for the AES to draw when it
 * asks (WM_REDRAW).  Scrolling moves the view a row of the grid and
 * builds the items again; the AES's own rectangle list clips every
 * redraw, so a window under another draws only what shows.
 */
#include "portab.h"
#include "desk.h"

/* The far arena, Malloc'd once: the DTA the listing reads into, then
 * every window's FNODEs, then the windows' saved places (CSAVE), the
 * desktop's copy of the shell buffer, and a DTA per level of a delete's
 * walk (deskfun.c). */
#define ARENA_SIZE  (sizeof(DTA) + (LONG)NUM_WNODES * NUM_FNODES * sizeof(FNODE) \
                     + sizeof(CSAVE) + SIZE_SHELBUF \
                     + (LONG)MAX_DELLEVEL * sizeof(DTA) + COPY_BUF)

/* The INF file's default windows (the donor's desk_inf_data1, "#W"):
 * in character cells, x 2 wide 38 high 12, each one lower. */
#define WIN_XCELL   2
#define WIN_WCELL   38
#define WIN_HCELL   12
static const WORD win_ycell[NUM_WNODES] = { 6, 8, 10, 13 };

/* -- strings and rectangles -------------------------------------------- */

static char *put_str(char *d, const char FAR *s)
{
    while (*s)
        *d++ = *s++;
    *d = 0;
    return d;
}

/* n in decimal at d; the sizes and counts are never negative. */
static char *put_num(char *d, LONG n)
{
    char digits[10];
    WORD i = 0;

    do {
        digits[i++] = (char)('0' + (WORD)(n % 10));
        n /= 10;
    } while (n);
    while (i)
        *d++ = digits[--i];
    *d = 0;
    return d;
}

/* rc_intersect, wind_get_grect and wind_set_grect used to be three more
 * statics here.  They are in the application library now (src/app/gemlib.c),
 * where the desktop having written them itself was the argument for putting
 * them: every GEM program wants the same three, and an ST program arrives
 * already written against gemlib's spelling of them. */
static WORD far_strcmp(const char FAR *a, const char FAR *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (WORD)((unsigned char)*a - (unsigned char)*b);
}

static WORD mul_div(WORD m1, WORD m2, WORD d1)
{
    return (WORD)((LONG)m1 * m2 / d1);
}

/* -- the windows ------------------------------------------------------- */

/* Before the first window: the arena, and every WNODE free. */
WORD win_start(void)
{
    LONG arena;
    WORD i;

    G.g_wcnt = 0;
    arena = Malloc((LONG)ARENA_SIZE);
    if (arena <= 0)
        return FALSE;
    G.g_dta = (DTA FAR *)arena;
    Fsetdta(G.g_dta);
    for (i = 0; i < NUM_WNODES; i++) {
        WNODE *pw = &G.g_wlist[i];
        pw->w_id = 0;
        pw->w_root = (WORD)(DROOT + 1 + i);
        pw->w_path.p_flist =
            (FNODE FAR *)(arena + (LONG)sizeof(DTA) + (LONG)i * (NUM_FNODES * sizeof(FNODE)));
    }
    G.g_cnxsave = (CSAVE FAR *)(arena + (LONG)sizeof(DTA)
                                  + (LONG)NUM_WNODES * (NUM_FNODES * sizeof(FNODE)));
    G.g_shelbuf = (char FAR *)G.g_cnxsave + sizeof(CSAVE);
    G.g_opdta = (DTA FAR *)(G.g_shelbuf + SIZE_SHELBUF);
    G.g_copybuf = (char FAR *)(G.g_opdta + MAX_DELLEVEL);
    {                                           /* the donor's is zeroed */
        char FAR *p = (char FAR *)G.g_cnxsave;
        WORD n;
        for (n = 0; n < sizeof(CSAVE); n++)
            *p++ = 0;
    }
    return TRUE;
}

WNODE *win_find(WORD wh)
{
    WORD i;

    for (i = 0; i < NUM_WNODES; i++)
        if (G.g_wlist[i].w_id == wh)
            return &G.g_wlist[i];
    return NULL;
}

/* The window on top: the last of ROOT's children, if it is open. */
WNODE *win_ontop(void)
{
    WORD wob = G.g_screen[ROOT].ob_tail;

    if (G.g_screen[wob].ob_width && G.g_screen[wob].ob_height)
        return &G.g_wlist[wob - (DROOT + 1)];
    return NULL;
}

static void win_top(WNODE *pw)
{
    objc_order(G.g_screen, pw->w_root, NIL);
}

/* Give the window up: the AES's handle, and its box, which goes to the
 * bottom of the stack, right after the desk. */
static void win_free(WNODE *pw)
{
    if (pw->w_id != -1)
        wind_delete(pw->w_id);
    G.g_wcnt--;
    pw->w_id = 0;
    objc_order(G.g_screen, pw->w_root, 1);
    obj_wfree(pw->w_root, 0, 0, 0, 0);
}

/* A window in the place the next saved slot has (the INF file's
 * defaults, or where a window was when the desktop last exited), its
 * box sized to it, created but not yet open; NULL when all NUM_WNODES
 * are out. */
static WNODE *win_alloc(void)
{
    WSAVE FAR *pws;
    WNODE *pw;
    WORD wob;
    GRECT r;

    if (G.g_wcnt == NUM_WNODES)
        return NULL;
    pws = &G.g_cnxsave->cs_wnode[G.g_wcnt];
    r.g_x = pws->x_save;
    r.g_y = pws->y_save;
    r.g_w = pws->w_save;
    r.g_h = pws->h_save;
    wob = obj_walloc(r.g_x, r.g_y, r.g_w, r.g_h);
    if (!wob)
        return NULL;
    G.g_wcnt++;
    pw = &G.g_wlist[wob - (DROOT + 1)];
    pw->w_root = wob;
    pw->w_cvrow = pw->w_cvcol = 0;
    pw->w_pncol = (WORD)((r.g_w - G.g_wchar) / (G.g_wicon + MIN_WINT));
    pw->w_pnrow = (WORD)((r.g_h - G.g_hchar) / (G.g_hicon + MIN_HINT));
    pw->w_vnrow = pw->w_vncol = 0;
    pw->w_id = wind_create(WINDOW_STYLE, G.g_desk.g_x, G.g_desk.g_y,
                           G.g_desk.g_w, G.g_desk.g_h);
    if (pw->w_id != -1)
        return pw;
    win_free(pw);
    return NULL;
}

/* -- the listing ------------------------------------------------------- */

/* The window's FNODE behind item obj, or NULL. */
FNODE FAR *win_fnode(WNODE *pw, WORD obj)
{
    FNODE FAR *pf = pw->w_path.p_flist;
    WORD i;

    for (i = 0; i < pw->w_path.p_count; i++, pf++)
        if (pf->f_obid == obj)
            return pf;
    return NULL;
}

/* The field the current order compares, the donor's pn_fcomp: date and
 * size run the other way round -- newest and biggest first -- because
 * that is what a person looking for either of them wants at the top.
 * Every order falls back to the name, which is the whole of S_NAME and
 * the tie-break for the rest, so the listing never depends on the order
 * the directory happened to be in.  Except S_NSRT, which is that
 * order. */
static WORD pn_fcomp(const FNODE *a, const FNODE FAR *b)
{
    const char FAR *ea;
    const char *ta;
    LONG chk = 0;

    switch (G.g_isort) {
    case S_DATE:
        chk = (LONG)b->f_date - (LONG)a->f_date;
        if (!chk)
            chk = (LONG)b->f_time - (LONG)a->f_time;
        break;
    case S_SIZE:
        chk = b->f_size - a->f_size;
        break;
    case S_TYPE:
        for (ta = a->f_name; *ta && *ta != '.'; ta++)
            ;
        for (ea = b->f_name; *ea && *ea != '.'; ea++)
            ;
        chk = far_strcmp(ta, ea);
        break;
    case S_NSRT:
        chk = (LONG)a->f_seq - (LONG)b->f_seq;
        break;
    default:
        break;
    }
    if (chk)
        return chk < 0 ? -1 : 1;
    return far_strcmp(a->f_name, b->f_name);
}

/* Folders first -- unless nothing is being sorted, when the directory's
 * own order is the whole of it -- and then the field: the donor's
 * pn_comp. */
static WORD pn_comp(const FNODE *a, const FNODE FAR *b)
{
    if (G.g_isort != S_NSRT && ((a->f_attr ^ b->f_attr) & FA_SUBDIR))
        return (a->f_attr & FA_SUBDIR) ? -1 : 1;
    return pn_fcomp(a, b);
}

/* Take the search spec; FALSE if it does not fit. */
static WORD pn_open(PNODE *pn, const char *spec)
{
    WORD n = 0;

    while (spec[n])
        n++;
    if (n >= LEN_ZPATH)
        return FALSE;
    put_str(pn->p_spec, spec);
    pn->p_count = 0;
    pn->p_size = 0;
    return TRUE;
}

/* A near FNODE into a far one, byte by byte: cc65816 5.18 cannot
 * compile a struct assignment between near and far objects over 8 bytes
 * at all (tools/ccbug/README.md, B11); far to far it can. */
static void fn_copy(FNODE FAR *d, const FNODE *s)
{
    char FAR *pd = (char FAR *)d;
    const char *ps = (const char *)s;
    WORD n;

    for (n = 0; n < sizeof(FNODE); n++)
        *pd++ = *ps++;
}

/* ...and a far one into a near one, for the same reason. */
static void fn_read(FNODE *d, const FNODE FAR *s)
{
    char *pd = (char *)d;
    const char FAR *ps = (const char FAR *)s;
    WORD n;

    for (n = 0; n < sizeof(FNODE); n++)
        *pd++ = *ps++;
}

/* Read the directory through the DTA into the FNODEs, each one into its
 * place in the order: the count and the bytes together.  An error from
 * Fsfirst lists nothing. */
static void pn_active(PNODE *pn)
{
    DTA FAR *dta = G.g_dta;
    FNODE FAR *pf;
    FNODE fn;
    LONG ret;
    WORD count = 0, i;

    pn->p_size = 0;                             /* read again after a delete */
    pn->p_count = 0;
    ret = Fsfirst(pn->p_spec, DISPATTR);
    while (ret == E_OK && count < NUM_FNODES) {
        if (dta->d_fname[0] != '.') {
            fn.f_obid = 0;
            fn.f_flags = 0;
            fn.f_seq = count;               /* where the directory had it */
            fn.f_attr = (WORD)(unsigned char)dta->d_attrib;
            fn.f_time = dta->d_time;
            fn.f_date = dta->d_date;
            fn.f_size = dta->d_length;
            for (i = 0; i < LEN_ZFNAME - 1 && dta->d_fname[i]; i++)
                fn.f_name[i] = dta->d_fname[i];
            for (; i < LEN_ZFNAME; i++)
                fn.f_name[i] = 0;
            /* insertion: slide the ones after it up one */
            i = count;
            pf = pn->p_flist + count;
            while (i > 0 && pn_comp(&fn, pf - 1) < 0) {
                *pf = *(pf - 1);
                pf--;
                i--;
            }
            fn_copy(pf, &fn);
            count++;
            pn->p_size += fn.f_size;
        }
        ret = Fsnext();
    }
    pn->p_count = count;
}

/* The listing put into the current order where it stands: the same
 * insertion sort pn_active runs as it reads, over what is already
 * there (the donor's pn_sort).  A change of order costs no directory
 * read, which is the whole reason an FNODE carries f_seq. */
static void pn_sort(PNODE *pn)
{
    FNODE FAR *pf;
    FNODE fn;
    WORD i, j;

    for (i = 1; i < pn->p_count; i++) {
        pf = pn->p_flist + i;
        fn_read(&fn, pf);
        j = i;
        while (j > 0 && pn_comp(&fn, pf - 1) < 0) {
            *pf = *(pf - 1);
            pf--;
            j--;
        }
        fn_copy(pf, &fn);
    }
}

/* Every open window's listing sorted again: the donor's win_srtall,
 * which runs before the views are built (desktop.c do_viewmenu). */
void win_srtall(void)
{
    WORD i;

    for (i = 0; i < NUM_WNODES; i++)
        if (G.g_wlist[i].w_id)
            pn_sort(&G.g_wlist[i].w_path);
}

/* -- the name and information lines ------------------------------------ */

static void win_sname(WNODE *pw)
{
    char *d = put_str(pw->w_name, " ");

    d = put_str(d, pw->w_path.p_spec);
    put_str(d, " ");
}

/* " 12345 bytes used in 6 items." (the donor's STINFOST). */
static void win_sinfo(WNODE *pw)
{
    char *d = put_str(pw->w_info, " ");

    d = put_num(d, pw->w_path.p_size);
    d = put_str(d, " bytes used in ");
    d = put_num(d, pw->w_path.p_count);
    put_str(d, " items.");
    /* BOTH WORDS, high first.  The high one was written 0 while this was
     * a small-data program and every string was in bank $00; the window's
     * name and information line live in G, and G went to far memory when
     * the desktop's resource did (2026-09-19).  A truncated address here
     * draws whatever is at the same offset in bank $00. */
    wind_set(pw->w_id, WF_INFO,
             (WORD)((uint32_t)pw->w_info >> 16),
             (WORD)(uint32_t)pw->w_info, 0, 0);
}

/* -- the view ---------------------------------------------------------- */

/* Which icon an entry gets: a folder, a program, or a document.  A
 * program is .G4A -- gem4xe's own executable -- or .PRG, the Atari
 * world's name for one, for anyone who would rather use that extension;
 * either way the loader reads the file's format, not its name, and
 * refuses a file that is not gem4xe's (src/sys/app.c, APP_E_MAGIC), so a
 * 68000 .PRG off a real Atari is turned away rather than run. */
static WORD win_which(const FNODE FAR *pf)
{
    const char FAR *s = pf->f_name;

    if (pf->f_attr & FA_SUBDIR)
        return IB_FOLDER;
    while (*s && *s != '.')
        s++;
    if (s[0] == '.' && !s[4]
        && ((s[1] == 'G' && s[2] == '4' && s[3] == 'A')
         || (s[1] == 'P' && s[2] == 'R' && s[3] == 'G')))
        return IB_APPL;
    return IB_DOCU;
}

/* What an item of the current view fills, and the space in front of it
 * (the donor's win_view).  ONE DEPARTURE: the donor makes a text line's
 * left margin `2*gl_wchar - 1`, an odd number, to land the text on a
 * byte boundary and reach the ST's fast text output.  Here the
 * arithmetic inverts -- 4bpp packs two pixels to a byte, so an ODD x is
 * the pre-shifted strip and the slow path (docs/phase2b.md) -- so the
 * margin is even. */
void win_view(void)
{
    GRECT t;

    if (G.g_iview == V_TEXT) {
        G.g_iwext = (WORD)(LEN_FNODE * G.g_wchar);
        G.g_ihext = G.g_hchar;
        G.g_iwint = (WORD)(2 * G.g_wchar);
        G.g_ihint = 2;
    } else {
        G.g_iwext = G.g_wicon;
        G.g_ihext = G.g_hicon;
        G.g_iwint = MIN_WINT;
        G.g_ihint = MIN_HINT;
    }
    /* ...and the grid a window that does NOT size to fit is laid out on:
     * the columns the widest window this screen can show would hold.  It
     * belongs here because it is a property of the view and the screen
     * and of nothing else, so it is settled once per view change rather
     * than per window (the donor's win_view). */
    wind_calc(WC_WORK, WINDOW_STYLE, G.g_desk.g_x, G.g_desk.g_y,
              G.g_desk.g_w, G.g_desk.g_h, &t.g_x, &t.g_y, &t.g_w, &t.g_h);
    G.g_icols = (WORD)(t.g_w / (G.g_iwext + G.g_iwint));
    if (G.g_icols < 1)
        G.g_icols = 1;
}

/* A number into n places, right-aligned, padded with `pad`; the places
 * are filled from the right, so a value too long for them loses its
 * high digits rather than the field's shape. */
static void win_num(char *d, WORD n, LONG value, char pad)
{
    WORD i = n;

    while (i > 0) {
        d[--i] = (char)('0' + (WORD)(value % 10));
        value /= 10;
        if (!value)
            break;
    }
    while (i > 0)
        d[--i] = pad;
}

/* One line of the text view, from the template the resource carries
 * (tools/deskrsc.py, STFLINE).  Each RUN of a placeholder letter takes
 * one field, in the template's own order and width: a translation may
 * move the columns, change the separators or leave a field out, and
 * none of that is written here.  A run shorter than its field truncates
 * it, a longer one pads it.  Anything that is not a placeholder is
 * copied as it stands. */
static void win_line(char *d, const FNODE FAR *pf)
{
    const char *t = G.g_fline;
    const char FAR *s;
    char *end = d + LEN_FNODE - 1;
    WORD n, i;
    char c;

    while (*t && d < end) {
        c = *t;
        for (n = 1; t[n] == c; n++)
            ;
        if (n > (WORD)(end - d))
            n = (WORD)(end - d);
        switch (c) {
        case 'f':                               /* the mark, one of three */
            for (i = 0; i < n; i++)
                d[i] = G.g_fmark[(pf->f_attr & FA_SUBDIR) ? 0
                                 : (pf->f_attr & FA_RDONLY) ? 1 : 2];
            break;
        case 'n':                               /* the name up to the dot */
        case 'e':                               /* ...and what follows it */
            s = pf->f_name;
            if (c == 'e') {
                while (*s && *s != '.')
                    s++;
                if (*s)
                    s++;
            }
            for (i = 0; i < n; i++)
                d[i] = (*s && *s != '.') ? *s++ : ' ';
            break;
        case 's':                               /* a folder's size is what it
                                                 * holds, and Show info is
                                                 * where the walk for that is */
            if (pf->f_attr & FA_SUBDIR)
                for (i = 0; i < n; i++)
                    d[i] = ' ';
            else
                win_num(d, n, pf->f_size, ' ');
            break;
        case 'd':
            win_num(d, n, (LONG)(pf->f_date & 0x1F), '0');
            break;
        case 'm':
            win_num(d, n, (LONG)((pf->f_date >> 5) & 0x0F), '0');
            break;
        case 'y':
            win_num(d, n, (LONG)(((pf->f_date >> 9) + 80) % 100), '0');
            break;
        case 'H':
            win_num(d, n, (LONG)((pf->f_time >> 11) & 0x1F), '0');
            break;
        case 'M':
            win_num(d, n, (LONG)((pf->f_time >> 5) & 0x3F), '0');
            break;
        default:
            for (i = 0; i < n; i++)
                d[i] = c;
            break;
        }
        d += n;
        t += n;
    }
    *d = 0;
}

/* The window's items for the view over work area *r: the grid that
 * fits (the donor's win_ocalc), then an item per entry in the rows
 * shown, and the sliders to match. */
static void win_bldview(WNODE *pw, const GRECT *r)
{
    WORD iwspc = (WORD)(G.g_iwext + G.g_iwint);
    WORD ihspc = (WORD)(G.g_ihext + G.g_ihint);
    FNODE FAR *pf;
    WORD wfit, hfit, i, n, row, col, obid, which;

    obj_wfree(pw->w_root, r->g_x, r->g_y, r->g_w, r->g_h);

    wfit = r->g_w / iwspc;
    if (wfit < 1)
        wfit = 1;
    hfit = r->g_h / ihspc;
    if (hfit < 1)
        hfit = 1;
    pf = pw->w_path.p_flist;
    for (i = 0; i < pw->w_path.p_count; i++, pf++)
        pf->f_obid = 0;
    /* THE GRID THE LISTING IS LAID ON.  With size to fit the columns are
     * the window's own, so the items reflow as it is resized and nothing
     * ever scrolls sideways; without it they are laid out for the widest
     * window this screen can show (g_icols) and the window scrolls over
     * that, which is what keeps an item under the same finger while the
     * window is resized.  The donor's win_ocalc. */
    if (G.g_ifit) {
        pw->w_vncol = wfit;
        pw->w_vnrow = (WORD)((pw->w_path.p_count + wfit - 1) / wfit);
    } else {
        WORD cols = G.g_icols;
        pw->w_vncol = pw->w_path.p_count < cols ? pw->w_path.p_count : cols;
        pw->w_vnrow = (WORD)((pw->w_path.p_count + cols - 1) / cols);
    }
    if (pw->w_vncol < 1)
        pw->w_vncol = 1;
    if (pw->w_vnrow < 1)
        pw->w_vnrow = 1;
    pw->w_pncol = wfit;
    pw->w_pnrow = hfit < pw->w_vnrow ? hfit : pw->w_vnrow;
    /* a window that grew shows earlier rows and columns rather than blank */
    n = wfit < pw->w_vncol ? wfit : pw->w_vncol;
    while (pw->w_vncol - pw->w_cvcol < n)
        pw->w_cvcol--;
    while (pw->w_vnrow - pw->w_cvrow < pw->w_pnrow)
        pw->w_cvrow--;

    hfit = (WORD)(pw->w_vnrow - pw->w_cvrow);
    if (hfit > pw->w_pnrow + 1)
        hfit = (WORD)(pw->w_pnrow + 1);         /* a row may show in part */
    for (row = 0; row < hfit; row++) {
        for (col = 0; col < pw->w_pncol; col++) {
            WORD vcol = (WORD)(pw->w_cvcol + col);

            if (vcol >= pw->w_vncol)
                break;                          /* past the last column */
            i = (WORD)((pw->w_cvrow + row) * pw->w_vncol + vcol);
            if (i >= pw->w_path.p_count)
                break;                          /* past the last entry */
            pf = pw->w_path.p_flist + i;
            if (G.g_iview == V_TEXT) {
                obid = obj_text(pw->w_root, (WORD)(col * iwspc + G.g_iwint),
                                (WORD)(row * ihspc + G.g_ihint),
                                G.g_iwext, G.g_ihext);
                if (obid)
                    win_line(obj_info(obid)->line, pf);
            } else {
                which = win_which(pf);
                obid = obj_icon(pw->w_root, (WORD)(col * iwspc + G.g_iwint),
                                (WORD)(row * ihspc + G.g_ihint), which,
                                pf->f_name, 0);
            }
            if (!obid) {
                row = hfit;                     /* no items left: stop */
                break;
            }
            pf->f_obid = obid;
            G.g_screen[obid].ob_state =
                (UWORD)(WHITEBAK | ((pf->f_flags & F_SELECTED) ? SELECTED : 0));
            G.g_screen[obid].ob_flags = NONE;
        }
    }

    wind_set(pw->w_id, WF_HSLSIZ,
             pw->w_vncol > pw->w_pncol
                 ? mul_div(pw->w_pncol, 1000, pw->w_vncol) : 1000, 0, 0, 0);
    wind_set(pw->w_id, WF_HSLIDE,
             pw->w_vncol > pw->w_pncol
                 ? mul_div(pw->w_cvcol, 1000, (WORD)(pw->w_vncol - pw->w_pncol))
                 : 0, 0, 0, 0);
    wind_set(pw->w_id, WF_VSLSIZ, mul_div(pw->w_pnrow, 1000, pw->w_vnrow), 0, 0, 0);
    wind_set(pw->w_id, WF_VSLIDE,
             pw->w_vnrow > pw->w_pnrow
                 ? mul_div(pw->w_cvrow, 1000, (WORD)(pw->w_vnrow - pw->w_pnrow)) : 0,
             0, 0, 0);
}

/* Build the window's items again over its work area. */
static void desk_verify(WORD wh)
{
    WNODE *pw = win_find(wh);
    GRECT t;

    if (pw) {
        wind_get_grect(wh, WF_WORKXYWH, &t);
        win_bldview(pw, &t);
    }
}

/* Draw wh's tree -- the desk's, or the window's box and items -- once
 * per rectangle of its list that meets *pc. */
void do_wredraw(WORD wh, const GRECT *pc)
{
    WORD root = DROOT;
    GRECT t;

    if (wh != DESKWH) {
        WNODE *pw = win_find(wh);
        if (!pw)
            return;
        root = pw->w_root;
    }
    graf_mouse(M_OFF, 0);
    wind_get_grect(wh, WF_FIRSTXYWH, &t);
    while (t.g_w && t.g_h) {
        if (rc_intersect(pc, &t))
            objc_draw(G.g_screen, root, MAX_DEPTH, t.g_x, t.g_y, t.g_w, t.g_h);
        wind_get_grect(wh, WF_NEXTXYWH, &t);
    }
    graf_mouse(M_ON, 0);
}

/* Show the view from row newcv, if that is a change. */
static void win_scroll(WNODE *pw, WORD newcv)
{
    GRECT t;

    if (newcv > pw->w_vnrow - pw->w_pnrow)
        newcv = (WORD)(pw->w_vnrow - pw->w_pnrow);
    if (newcv < 0)
        newcv = 0;
    if (newcv == pw->w_cvrow)
        return;
    pw->w_cvrow = newcv;
    wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
    win_bldview(pw, &t);
    do_wredraw(pw->w_id, &t);
}

/* Sideways, the same way: only a window that is not sizing to fit has
 * anywhere to go, because with size to fit w_vncol IS w_pncol. */
static void win_hscroll(WNODE *pw, WORD newcv)
{
    GRECT t;

    if (newcv > pw->w_vncol - pw->w_pncol)
        newcv = (WORD)(pw->w_vncol - pw->w_pncol);
    if (newcv < 0)
        newcv = 0;
    if (newcv == pw->w_cvcol)
        return;
    pw->w_cvcol = newcv;
    wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
    win_bldview(pw, &t);
    do_wredraw(pw->w_id, &t);
}

static void win_arrow(WNODE *pw, WORD arrow)
{
    switch (arrow) {
    case WA_UPPAGE:
        win_scroll(pw, (WORD)(pw->w_cvrow - pw->w_pnrow));
        break;
    case WA_DNPAGE:
        win_scroll(pw, (WORD)(pw->w_cvrow + pw->w_pnrow));
        break;
    case WA_UPLINE:
        win_scroll(pw, (WORD)(pw->w_cvrow - 1));
        break;
    case WA_DNLINE:
        win_scroll(pw, (WORD)(pw->w_cvrow + 1));
        break;
    case WA_LFPAGE:
        win_hscroll(pw, (WORD)(pw->w_cvcol - pw->w_pncol));
        break;
    case WA_RTPAGE:
        win_hscroll(pw, (WORD)(pw->w_cvcol + pw->w_pncol));
        break;
    case WA_LFLINE:
        win_hscroll(pw, (WORD)(pw->w_cvcol - 1));
        break;
    case WA_RTLINE:
        win_hscroll(pw, (WORD)(pw->w_cvcol + 1));
        break;
    default:
        break;
    }
}

static void win_slide(WNODE *pw, WORD permille)
{
    win_scroll(pw, mul_div(permille, (WORD)(pw->w_vnrow - pw->w_pnrow), 1000));
}

static void win_hslide(WNODE *pw, WORD permille)
{
    win_hscroll(pw, mul_div(permille, (WORD)(pw->w_vncol - pw->w_pncol), 1000));
}

/* -- selection --------------------------------------------------------- */

/* Select item obj, or deselect it, and redraw it if asked. */
void act_chg(WORD wh, WORD root, WORD obj, WORD set, WORD dodraw)
{
    OBJECT *pob = &G.g_screen[obj];
    UWORD state = pob->ob_state;
    GRECT t;

    state = set ? (UWORD)(state | SELECTED) : (UWORD)(state & ~SELECTED);
    if (state == pob->ob_state)
        return;
    pob->ob_state = state;
    if (root != DROOT) {
        FNODE FAR *pf = win_fnode(&G.g_wlist[root - (DROOT + 1)], obj);
        if (pf)
            pf->f_flags = set ? (WORD)(pf->f_flags | F_SELECTED)
                              : (WORD)(pf->f_flags & ~F_SELECTED);
    }
    if (dodraw) {
        objc_offset(G.g_screen, obj, &t.g_x, &t.g_y);
        t.g_w = pob->ob_width;
        t.g_h = pob->ob_height;
        do_wredraw(wh, &t);
    }
}

/* Select item obj under root and no other there; obj 0 selects none. */
void act_select(WORD wh, WORD root, WORD obj)
{
    WORD i;

    for (i = G.g_screen[root].ob_head; i >= WOBS_START; i = G.g_screen[i].ob_next)
        act_chg(wh, root, i, i == obj, TRUE);
}

/* What a CLICK does to the selection -- the donor's act_bsclick
 * (deskact.c), reached only once a press has turned out not to be a
 * drag (desktop.c hndl_button).
 *
 * SHIFT adds an item to the selection or takes it out again, which is
 * the only modifier this machine can be asked about while the button is
 * down (docs/phase18.md); without it the item clicked becomes the whole
 * selection, and a click on nothing clears it.  An item that is already
 * selected is left alone, so that clicking one of several and dragging
 * carries all of them. */
void act_bsclick(WORD wh, WORD root, WORD obj, WORD kstate)
{
    if (kstate & (MODE_LSHIFT | MODE_RSHIFT)) {
        if (obj)
            act_chg(wh, root, obj,
                    (WORD)!(G.g_screen[obj].ob_state & SELECTED), TRUE);
        return;
    }
    if (!obj || !(G.g_screen[obj].ob_state & SELECTED))
        act_select(wh, root, obj);
}

/* Everything of a window's whose cell the rectangle touches, selected;
 * everything it does not touch, deselected.  What a rubber band leaves
 * behind (the donor's act_allselect, deskact.c) -- and on this machine
 * the only way to select several things at once that a test harness can
 * drive, because SHIFT cannot be held down through one (docs/phase26.md). */
void act_allselect(WORD wh, WORD root, const GRECT *box)
{
    WORD i;

    for (i = G.g_screen[root].ob_head; i >= WOBS_START; i = G.g_screen[i].ob_next) {
        GRECT t;

        objc_offset(G.g_screen, i, &t.g_x, &t.g_y);
        t.g_w = G.g_screen[i].ob_width;
        t.g_h = G.g_screen[i].ob_height;
        act_chg(wh, root, i, rc_intersect(box, &t), TRUE);
    }
}

/* How many of a window's items are selected, and the first of them
 * (0 when none): what the File menu asks before it does anything. */
WORD act_count(WORD root, WORD *pfirst)
{
    WORD i, n = 0;

    *pfirst = 0;
    for (i = G.g_screen[root].ob_head; i >= WOBS_START; i = G.g_screen[i].ob_next)
        if (G.g_screen[i].ob_state & SELECTED) {
            if (!n)
                *pfirst = i;
            n++;
        }
    return n;
}

/* The window, and the window handle, an item is in. */
static WORD obj_parent(WORD obj)
{
    while (obj >= WOBS_START)
        obj = G.g_screen[obj].ob_next;
    return obj;
}

static WORD obj_wh(WORD parent)
{
    return parent == DROOT ? DESKWH : G.g_wlist[parent - (DROOT + 1)].w_id;
}

/* -- opening ----------------------------------------------------------- */

/* Where a window may go: x on a 16-pixel boundary, below the menu bar. */
static void do_xyfix(WORD *px, WORD *py)
{
    *px = (WORD)((*px + 8) & 0xFFF0);
    if (*py < G.g_desk.g_y)
        *py = G.g_desk.g_y;
}

/* Open the window at *pt, growing from the icon curr (which is
 * deselected) when there is one; a window already open moves nothing. */
static void do_wopen(WORD new_win, WORD wh, WORD curr, const GRECT *pt)
{
    GRECT t = *pt, c;

    do_xyfix(&t.g_x, &t.g_y);
    if (curr > 0) {
        WORD croot = obj_parent(curr);
        objc_offset(G.g_screen, curr, &c.g_x, &c.g_y);
        c.g_w = G.g_screen[curr].ob_width;
        c.g_h = G.g_screen[curr].ob_height;
        graf_growbox(c.g_x, c.g_y, c.g_w, c.g_h, t.g_x, t.g_y, t.g_w, t.g_h);
        act_chg(obj_wh(croot), croot, curr, FALSE, new_win);
    }
    if (new_win)
        wind_open(wh, t.g_x, t.g_y, t.g_w, t.g_h);
}

/* The window between its full size and the size before that. */
void do_wfull(WORD wh)
{
    GRECT curr, prev, full;

    wind_get_grect(wh, WF_CURRXYWH, &curr);
    wind_get_grect(wh, WF_PREVXYWH, &prev);
    wind_get_grect(wh, WF_FULLXYWH, &full);
    if (curr.g_x == full.g_x && curr.g_y == full.g_y
     && curr.g_w == full.g_w && curr.g_h == full.g_h) {
        wind_set_grect(wh, WF_CURRXYWH, &prev);
        graf_shrinkbox(prev.g_x, prev.g_y, prev.g_w, prev.g_h,
                       full.g_x, full.g_y, full.g_w, full.g_h);
    } else {
        graf_growbox(curr.g_x, curr.g_y, curr.g_w, curr.g_h,
                     full.g_x, full.g_y, full.g_w, full.g_h);
        wind_set_grect(wh, WF_CURRXYWH, &full);
    }
}

/* List path in the window and show it: a new window opens at *pt, an
 * open one is redrawn where it is. */
static WORD do_diropen(WNODE *pw, WORD new_win, WORD curr, const char *path,
                       const GRECT *pt, WORD redraw)
{
    GRECT t;

    desk_busy(TRUE);
    if (!pn_open(&pw->w_path, path)) {
        desk_busy(FALSE);
        return FALSE;
    }
    pn_active(&pw->w_path);
    win_sname(pw);
    win_sinfo(pw);
    wind_set(pw->w_id, WF_NAME,
             (WORD)((uint32_t)pw->w_name >> 16),
             (WORD)(uint32_t)pw->w_name, 0, 0);
    do_wopen(new_win, pw->w_id, curr, pt);
    if (new_win)
        win_top(pw);
    desk_verify(pw->w_id);
    if (redraw && !new_win) {
        wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
        do_wredraw(pw->w_id, &t);
    }
    desk_busy(FALSE);
    return TRUE;
}

/* Every open window's items built again over its work area, and then
 * every one of them drawn: the donor's win_bdall and win_shwall, which
 * a change of view needs one after the other -- all the building
 * first, so that no window is drawn in the new view beside one still
 * standing in the old. */
void win_bdall(void)
{
    WORD i;

    for (i = 0; i < NUM_WNODES; i++)
        if (G.g_wlist[i].w_id)
            desk_verify(G.g_wlist[i].w_id);
}

void win_shwall(void)
{
    GRECT t;
    WORD i;

    for (i = 0; i < NUM_WNODES; i++)
        if (G.g_wlist[i].w_id) {
            wind_get_grect(G.g_wlist[i].w_id, WF_WORKXYWH, &t);
            do_wredraw(G.g_wlist[i].w_id, &t);
        }
}

/* The window's directory listed again, after something on the disk
 * changed it: the same place, the same view, the items rebuilt.  The
 * listing's DTA is put back first -- a delete's walk leaves its own
 * (deskfun.c). */
void win_rebld(WNODE *pw)
{
    GRECT t;

    desk_busy(TRUE);
    Fsetdta(G.g_dta);
    pn_active(&pw->w_path);
    win_sname(pw);
    win_sinfo(pw);
    wind_set(pw->w_id, WF_NAME,
             (WORD)((uint32_t)pw->w_name >> 16),
             (WORD)(uint32_t)pw->w_name, 0, 0);
    desk_verify(pw->w_id);
    wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
    do_wredraw(pw->w_id, &t);
    desk_busy(FALSE);
}

/* A drive icon: its root in a new window. */
static WORD do_dopen(WORD curr)
{
    WNODE *pw;
    char path[8];

    pw = win_alloc();
    if (!pw) {
        fun_alert(1, STNOWIND);
        act_chg(DESKWH, DROOT, curr, FALSE, TRUE);
        return FALSE;
    }
    path[0] = (char)(obj_info(curr)->i.blk.ib_char & 0xFF);
    path[1] = ':';
    path[2] = '\\';
    path[3] = '*';
    path[4] = '.';
    path[5] = '*';
    path[6] = 0;
    if (!do_diropen(pw, TRUE, curr, path, (const GRECT *)&G.g_screen[pw->w_root].ob_x, TRUE)) {
        win_free(pw);
        act_chg(DESKWH, DROOT, curr, FALSE, TRUE);
        return FALSE;
    }
    return TRUE;
}

/* A folder in a window: its listing in the same window. */
static WORD do_fopen(WNODE *pw, WORD curr, const char FAR *name)
{
    char path[LEN_ZPATH];
    const char *spec = pw->w_path.p_spec;
    GRECT t;
    WORD n = 0, i;

    wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
    while (spec[n])                             /* "A:\SUB\*.*" less the "*.*" */
        n++;
    n -= 3;
    for (i = 0; i < n; i++)
        path[i] = spec[i];
    while (*name && i < LEN_ZPATH - 5)
        path[i++] = *name++;
    if (*name)
        return FALSE;
    path[i++] = '\\';
    path[i++] = '*';
    path[i++] = '.';
    path[i++] = '*';
    path[i] = 0;
    return do_diropen(pw, FALSE, curr, path, &t, TRUE);
}

/* A program in a window: its folder becomes the default directory and
 * the program the shell's next command (the donor's do_aopen, pro_run
 * and pro_exec).  TRUE when the shell took it -- the desktop's main
 * loop is then done, and the shell runs the program once the desktop
 * has exited.  The icon shrinks to the desk on the way out, deselected
 * but not redrawn, as the donor has it.
 *
 * Not static: the compiler inlines a static function with one call
 * site, and this one's path and tail (176 bytes) would then sit in
 * do_open's frame under every window it opens -- the desktop's deepest
 * stack, 164 bytes deeper (milestone 6).  External, it keeps its own
 * frame, paid only on the way out to a program. */
WORD do_aopen(WNODE *pw, WORD curr, const char FAR *name)
{
    char app_path[LEN_ZPATH];
    char tail[SH_TAILLEN];
    const char *spec = pw->w_path.p_spec;
    WORD n = 0, k = 0, i, ret;

    while (spec[n])                             /* "A:\SUB\*.*" less the "*.*" */
        n++;
    n -= 3;
    while (name[k])
        k++;
    if (n + k >= LEN_ZPATH)                     /* the full path must fit */
        return FALSE;
    for (i = 0; i < n; i++)
        app_path[i] = spec[i];
    app_path[i] = 0;
    desk_busy(TRUE);                            /* set_default_path: disk i/o */
    Dsetdrv((WORD)(app_path[0] - 'A'));
    if (Dsetpath(app_path) < 0) {
        desk_busy(FALSE);
        fun_alert(1, STDEFDIR);
        return FALSE;
    }
    desk_busy(FALSE);
    for (k = 0; name[k]; k++)                   /* the full path */
        app_path[i++] = name[k];
    app_path[i] = 0;
    for (i = 0; i < SH_TAILLEN; i++)            /* pro_run: no arguments, */
        tail[i] = 0;                            /* the CR after the NUL */
    tail[2] = 0x0D;
    desk_busy(TRUE);                            /* pro_exec */
    ret = shel_write(SHW_EXEC, 1, 1, app_path, tail);
    if (!ret)
        desk_busy(FALSE);
    do_wopen(FALSE, pw->w_id, curr, &G.g_desk);
    return ret;
}

/* Open item obj of window wh (DESKWH: the desk): a drive icon in a new
 * window, a folder in its own, a program through the shell.  TRUE only
 * when a program ran, as the donor's do_open answers: the desktop is
 * done then. */
WORD do_open(WORD wh, WORD obj)
{
    WNODE *pw;
    FNODE FAR *pf;

    if (wh == DESKWH) {
        if (obj_info(obj)->i.blk.ib_char & 0xFF)
            do_dopen(obj);
        return FALSE;                           /* else the trash */
    }
    pw = win_find(wh);
    if (!pw)
        return FALSE;
    pf = win_fnode(pw, obj);
    if (!pf)
        return FALSE;
    if (pf->f_attr & FA_SUBDIR) {
        do_fopen(pw, obj, pf->f_name);
        return FALSE;
    }
    if (win_which(pf) == IB_APPL)
        return do_aopen(pw, obj, pf->f_name);
    return FALSE;                               /* a document */
}

/* Close the window, or -- close_window FALSE -- the folder it shows,
 * which lists the folder above it, or closes the window at the root. */
void win_close(WNODE *pw, WORD close_window)
{
    char path[LEN_ZPATH];
    const char *spec = pw->w_path.p_spec;
    GRECT t;
    WORD n = 0, last = 0, i;

    if (!close_window) {
        while (spec[n]) {                       /* the '\' before the "*.*" */
            if (spec[n] == '\\')
                last = n;
            n++;
        }
        for (i = last; i > 0 && spec[i - 1] != '\\'; i--)
            ;
        if (i > 0) {                            /* "A:\SUB\*.*" -> "A:\*.*" */
            for (n = 0; n < i; n++)
                path[n] = spec[n];
            path[n++] = '*';
            path[n++] = '.';
            path[n++] = '*';
            path[n] = 0;
            wind_get_grect(pw->w_id, WF_WORKXYWH, &t);
            do_diropen(pw, FALSE, 0, path, &t, TRUE);
            return;
        }
    }
    wind_close(pw->w_id);
    win_free(pw);
}

/* -- the windows between programs -------------------------------------- */

/* The desktop's DESKTOP.INF lives in the AES's shell buffer, after
 * CPDATA_LEN bytes: "#R 02" and a "#W" line per window slot -- the
 * view, the place in character cells, and the path, "@" ending it
 * (the donor's deskapp.c; the lines for the icons and the preferences
 * are later milestones).  app_save writes it from the slots when the
 * desktop exits to run a program, app_start reads it back into them
 * when the shell loads the desktop again, and cnx_put/cnx_get carry
 * the windows themselves to and from the slots (the donor's
 * deskmain.c).  The slots also give a new window its place. */

/* -- the background, and which screen it belongs to --------------------- */

/* Sixteen colours or two: what appl_init reported, which is the one
 * place the desktop learns the depth (src/sys/abi.c fills global[10]). */
WORD desk_screen(void)
{
    return (global[10] > 1) ? SCR_COLOUR : SCR_MONO;
}

/* The remembered pair onto the desk and every window's box.  The high
 * bytes are left as the resource built them -- they are the border and
 * text colours, which the chooser does not offer. */
void desk_patcol_apply(void)
{
    UWORD *pc = G.g_patcol[desk_screen()];
    WORD i;

    G.g_screen[DROOT].ob_spec.index =
        (G.g_screen[DROOT].ob_spec.index & ~PATCOL_MASK) | (LONG)pc[0];
    for (i = 1; i <= NUM_WNODES; i++)
        G.g_screen[DROOT + i].ob_spec.index =
            (G.g_screen[DROOT + i].ob_spec.index & ~PATCOL_MASK) | (LONG)pc[1];
}

void desk_patcol(UWORD deskpc, UWORD winpc)
{
    UWORD *pc = G.g_patcol[desk_screen()];

    pc[0] = deskpc;
    pc[1] = winpc;
    desk_patcol_apply();
}

static WORD hex_dig(char c)
{
    if (c >= 'A')
        c = (char)(c + 9);
    return (WORD)(c & 0x0F);
}

/* The donor's scan_2: past the spaces, two hex digits (0xFF is -1) or
 * nothing at a CR. */
static WORD scan_2(const char FAR **pp)
{
    const char FAR *p = *pp;
    WORD v = 0;

    while (*p == ' ')
        p++;
    if (*p != '\r') {
        v = (WORD)(hex_dig(*p++) << 4);
        v |= hex_dig(*p++);
        if (v == 0xFF)
            v = -1;
    }
    *pp = p;
    return v;
}

static char FAR *put_hex2(char FAR *d, WORD v)
{
    static const char hex[] = "0123456789ABCDEF";

    *d++ = ' ';
    *d++ = hex[(v >> 4) & 0x0F];
    *d++ = hex[v & 0x0F];
    return d;
}

static char FAR *put_far(char FAR *d, const char FAR *s)
{
    while (*s)
        *d++ = *s++;
    return d;
}

/* The file the layout lives in, on the drive the desktop was started
 * from -- the donor's INF_FILE_NAME with the boot drive's letter put
 * into it (deskapp.c read_inf_file).  An absolute path, so that a
 * desktop which has been walking around a disk still writes it where
 * it will be found at the next boot. */
static void inf_name(char *name)
{
    name[0] = (char)('A' + Dgetdrv());
    name[1] = ':';
    name[2] = '\\';
    put_str(name + 3, INF_NAME);
}

/* The INF text from the slots; its length with the NUL. */
static WORD inf_write(void)
{
    char FAR *p = G.g_shelbuf + CPDATA_LEN;
    WSAVE FAR *pws = G.g_cnxsave->cs_wnode;
    WORD i;

    p = put_far(p, "#R");
    p = put_hex2(p, INF_REV_LEVEL);
    p = put_far(p, "\r\n");
    /* the environment, in the donor's first byte: bit 7 is the text
     * view, bits 6-5 the sort (deskapp.c INF_E1_VIEWTEXT).  The second
     * byte is the donor's date and clock formats, which are the
     * resource's here (deskrsc.py STFLINE), so it goes out as zero and
     * is not read back. */
    p = put_far(p, "#E");
    p = put_hex2(p, (WORD)((G.g_iview == V_TEXT ? INF_E1_VIEWTEXT : 0)
                           | ((G.g_isort == S_NSRT ? 0 : G.g_isort) << 5)));
    p = put_hex2(p, 0);
    p = put_hex2(p, 0);
    p = put_hex2(p, 0);
    p = put_hex2(p, (WORD)((G.g_isort == S_NSRT ? INF_E5_NOSORT : 0)
                           | (G.g_ifit ? 0 : INF_E5_NOSIZE)));
    p = put_far(p, "\r\n");
    /* The backgrounds, the donor's "#Q" line (EmuTOS deskapp.c) with
     * gem4xe's pairs rather than its three: a desk byte and a window
     * byte per screen, the colour one first.  Written for BOTH screens
     * and not only the one that is up, so that a machine booted on the
     * ANTIC fallback and saved does not throw away what was chosen in
     * sixteen colours. */
    p = put_far(p, "#Q");
    for (i = 0; i < N_SCREENS; i++) {
        p = put_hex2(p, G.g_patcol[i][0]);
        p = put_hex2(p, G.g_patcol[i][1]);
    }
    p = put_far(p, "\r\n");
    for (i = 0; i < NUM_WNODES; i++, pws++) {
        p = put_far(p, "#W");
        p = put_hex2(p, pws->hsl_save);
        p = put_hex2(p, pws->vsl_save);
        p = put_hex2(p, (WORD)(pws->x_save / G.g_wchar));
        p = put_hex2(p, (WORD)(pws->y_save / G.g_hchar));
        p = put_hex2(p, (WORD)(pws->w_save / G.g_wchar));
        p = put_hex2(p, (WORD)(pws->h_save / G.g_hchar));
        p = put_hex2(p, 0);
        *p++ = ' ';
        p = put_far(p, pws->pth_save);
        p = put_far(p, "@\r\n");
    }
    *p = 0;
    return (WORD)((uint32_t)p - (uint32_t)G.g_shelbuf + 1);
}

/* The text after CPDATA_LEN, and how long it is without the NUL. */
static WORD inf_len(WORD len)
{
    return (WORD)(len - CPDATA_LEN - 1);
}

/* The file into the shell buffer, FALSE when there is none to read or
 * what is there is not INF text. */
static WORD inf_load(void)
{
    char name[LEN_ZFNAME + 4];
    char FAR *buf = G.g_shelbuf + CPDATA_LEN;
    LONG fd, got;

    inf_name(name);
    fd = Fopen(name, 0);
    if (fd < 0)
        return FALSE;
    got = Fread((WORD)fd, (LONG)(SIZE_SHELBUF - CPDATA_LEN - 1), buf);
    Fclose((WORD)fd);
    if (got < 0)
        got = 0;
    buf[got] = 0;
    return (WORD)(buf[0] == '#');
}

/* ...and the buffer out to it.  `len` is inf_write's, so the NUL and
 * the copy/paste bytes in front of the text are not written: what goes
 * on the disk is the text a person could read. */
static WORD inf_store(WORD len)
{
    char name[LEN_ZFNAME + 4];
    LONG fd, put, n = (LONG)inf_len(len);

    inf_name(name);
    fd = Fcreate(name, 0);
    if (fd < 0)
        return FALSE;
    put = Fwrite((WORD)fd, n, G.g_shelbuf + CPDATA_LEN);
    Fclose((WORD)fd);
    return (WORD)(put == n);
}

/* No INF text yet: the donor's desk_inf_data1 windows, each lower
 * than the one before, as text for app_start to read like any other. */
static void build_inf(void)
{
    WSAVE FAR *pws = G.g_cnxsave->cs_wnode;
    WORD i;

    for (i = 0; i < NUM_WNODES; i++, pws++) {
        pws->x_save = (WORD)(WIN_XCELL * G.g_wchar);
        pws->y_save = (WORD)(win_ycell[i] * G.g_hchar);
        pws->w_save = (WORD)(WIN_WCELL * G.g_wchar);
        pws->h_save = (WORD)(WIN_HCELL * G.g_hchar);
        pws->hsl_save = 0;
        pws->vsl_save = 0;
        pws->pth_save[0] = 0;
    }
    inf_write();
}

/* The slots from the "#W" lines of INF text. */
static void inf_parse(const char FAR *pcurr)
{
    WSAVE FAR *pws;
    WORD wincnt = 0, rev, i;

    while (*pcurr) {
        if (*pcurr++ != '#')
            continue;
        switch (*pcurr) {
        case 'R':
            pcurr++;
            rev = scan_2(&pcurr);
            (void)rev;
            break;
        case 'E': {
            WORD e1, e5;

            pcurr++;
            e1 = scan_2(&pcurr);
            scan_2(&pcurr);                     /* the donor's date and clock */
            scan_2(&pcurr);                     /* formats, and its video     */
            scan_2(&pcurr);                     /* words: the resource's here */
            e5 = scan_2(&pcurr);
            desk_view((WORD)((e1 & INF_E1_VIEWTEXT) ? V_TEXT : V_ICON));
            desk_sort((WORD)((e5 & INF_E5_NOSORT) ? S_NSRT
                             : (e1 & INF_E1_SORTMASK) >> 5));
            desk_fit(!(e5 & INF_E5_NOSIZE));
            break;
        }
        case 'Q':                       /* the backgrounds: see inf_write */
            pcurr++;
            for (i = 0; i < N_SCREENS; i++) {
                G.g_patcol[i][0] = (UWORD)scan_2(&pcurr);
                G.g_patcol[i][1] = (UWORD)scan_2(&pcurr);
            }
            desk_patcol_apply();
            break;
        case 'W':
            pcurr++;
            if (wincnt < NUM_WNODES) {
                pws = &G.g_cnxsave->cs_wnode[wincnt];
                pws->hsl_save = scan_2(&pcurr);
                pws->vsl_save = scan_2(&pcurr);
                pws->x_save = (WORD)(scan_2(&pcurr) * G.g_wchar);
                pws->y_save = (WORD)(scan_2(&pcurr) * G.g_hchar);
                pws->w_save = (WORD)(scan_2(&pcurr) * G.g_wchar);
                pws->h_save = (WORD)(scan_2(&pcurr) * G.g_hchar);
                pcurr += 4;                     /* " 00 ", then the path */
                for (i = 0; *pcurr != '@' && i < LEN_ZPATH - 1; i++)
                    pws->pth_save[i] = *pcurr++;
                pws->pth_save[i] = 0;
                wincnt++;
            }
            break;
        default:
            break;
        }
    }
}

/* Where the desktop's layout comes from at start-up, in the order the
 * donor looks: what the shell buffer holds -- which is how a desktop
 * that has just run a program gets its windows back -- then the file,
 * which is how it gets them back after the machine has been off, and
 * then the built-in default. */
void app_start(void)
{
    WORD i;

    /* The defaults FIRST, for both screens, so that an INF written
     * before there was a "#Q" line -- or none at all -- leaves the desk
     * the green it has always been rather than pattern 0 in colour 0.
     * A "#Q" in the text overwrites them a moment later; without this
     * the next Save desktop would write the zeros out as if they were
     * somebody's choice. */
    for (i = 0; i < N_SCREENS; i++) {
        G.g_patcol[i][0] = (UWORD)(DESK_SPEC & PATCOL_MASK);
        G.g_patcol[i][1] = (UWORD)(WINDOW_SPEC & PATCOL_MASK);
    }
    shel_get(G.g_shelbuf, SIZE_SHELBUF);
    if (G.g_shelbuf[CPDATA_LEN] != '#' && !inf_load())
        build_inf();
    inf_parse(G.g_shelbuf + CPDATA_LEN);
}

/* Options -> Save desktop: the windows as they are now, into the slots,
 * into the text, onto the disk. */
WORD inf_save(void)
{
    cnx_put();
    return inf_store(inf_write());
}

/* Options -> Read .INF file: the file back, and the windows with it --
 * what is open is closed first, so that what comes up is what was
 * saved and not what was saved on top of what is there. */
WORD inf_read(void)
{
    WORD i;

    if (!inf_load())
        return FALSE;
    inf_parse(G.g_shelbuf + CPDATA_LEN);
    for (i = 0; i < NUM_WNODES; i++)
        if (G.g_wlist[i].w_id > 0)
            win_close(&G.g_wlist[i], TRUE);
    cnx_get();
    return TRUE;
}

/* The slots into the shell buffer, for the next desktop. */
void app_save(void)
{
    WORD len = inf_write();

    shel_put(G.g_shelbuf, len);
}

/* The open windows into the slots, bottom-most first (ROOT's children
 * are in stacking order), the rest cleared: the order cnx_get opens
 * them in puts them back as they were. */
void cnx_put(void)
{
    WSAVE FAR *pws = G.g_cnxsave->cs_wnode;
    WORD wob, n = 0, i;
    GRECT r;

    for (wob = G.g_screen[ROOT].ob_head; wob > ROOT; wob = G.g_screen[wob].ob_next) {
        WNODE *pw;
        if (wob == DROOT)
            continue;
        pw = &G.g_wlist[wob - (DROOT + 1)];
        if (pw->w_id <= 0)
            continue;
        wind_get_grect(pw->w_id, WF_CURRXYWH, &r);
        do_xyfix(&r.g_x, &r.g_y);
        pws->x_save = r.g_x;
        pws->y_save = r.g_y;
        pws->w_save = r.g_w;
        pws->h_save = r.g_h;
        pws->hsl_save = 0;
        pws->vsl_save = pw->w_cvrow;
        for (i = 0; pw->w_path.p_spec[i]; i++)
            pws->pth_save[i] = pw->w_path.p_spec[i];
        pws->pth_save[i] = 0;
        pws++;
        n++;
    }
    for (; n < NUM_WNODES; n++, pws++)
        pws->pth_save[0] = 0;
}

/* The windows back from the slots, each in its place -- on the desk,
 * at least -- and its view, growing from its drive's icon. */
void cnx_get(void)
{
    WSAVE FAR *pws = G.g_cnxsave->cs_wnode;
    WNODE *pw;
    WORD nw, obid, i;
    char path[LEN_ZPATH];
    GRECT r;

    for (nw = 0; nw < NUM_WNODES; nw++, pws++) {
        if (pws->x_save >= G.g_desk.g_w)
            pws->x_save = (WORD)(G.g_desk.g_w / 2);
        if (pws->y_save >= G.g_desk.g_h)
            pws->y_save = (WORD)(G.g_desk.g_h / 2);
        if (pws->w_save <= 0 || pws->w_save > G.g_desk.g_w)
            pws->w_save = G.g_desk.g_w;
        if (pws->h_save <= 0 || pws->h_save > G.g_desk.g_h)
            pws->h_save = G.g_desk.g_h;
        if (!pws->pth_save[0])
            continue;
        obid = obj_get_obid(pws->pth_save[0]);
        pw = win_alloc();
        if (!pw)
            continue;
        pw->w_cvrow = pws->vsl_save;
        r.g_x = pws->x_save;
        r.g_y = pws->y_save;
        do_xyfix(&r.g_x, &r.g_y);
        pws->x_save = r.g_x;
        pws->y_save = r.g_y;
        r.g_w = pws->w_save;
        r.g_h = pws->h_save;
        for (i = 0; pws->pth_save[i]; i++)
            path[i] = pws->pth_save[i];
        path[i] = 0;
        if (!do_diropen(pw, TRUE, obid, path, &r, TRUE))
            win_free(pw);
    }
}

/* -- the window manager's messages ------------------------------------- */

void hndl_wmsg(const WORD *msg)
{
    WORD wh = msg[3];
    WNODE *pw = win_find(wh);
    GRECT t;

    switch (msg[0]) {
    case WM_REDRAW:
        t.g_x = msg[4];
        t.g_y = msg[5];
        t.g_w = msg[6];
        t.g_h = msg[7];
        do_wredraw(wh, &t);
        break;
    case WM_TOPPED:
        wind_set(wh, WF_TOP, 0, 0, 0, 0);
        /* falls through */
    case WM_NEWTOP:
        if (pw)
            win_top(pw);
        break;
    case WM_CLOSED:                             /* the closer is File -> Close:
                                                 * out of the folder, and the
                                                 * window at the root closes */
        if (pw)
            win_close(pw, FALSE);
        break;
    case WM_FULLED:
        do_wfull(wh);
        desk_verify(wh);
        break;
    case WM_ARROWED:
        if (pw)
            win_arrow(pw, msg[4]);
        break;
    case WM_VSLID:
        if (pw)
            win_slide(pw, msg[4]);
        break;
    case WM_HSLID:
        if (pw)
            win_hslide(pw, msg[4]);
        break;
    case WM_SIZED:
    case WM_MOVED:
        if (!pw)
            break;
        t.g_x = msg[4];
        t.g_y = msg[5];
        t.g_w = msg[6];
        t.g_h = msg[7];
        do_xyfix(&t.g_x, &t.g_y);
        wind_set_grect(wh, WF_CURRXYWH, &t);
        if (msg[0] == WM_SIZED) {
            WORD cols = pw->w_pncol;
            desk_verify(wh);
            if (pw->w_pncol != cols) {          /* the items moved: the AES
                                                 * redraws only what it uncovered */
                wind_get_grect(wh, WF_WORKXYWH, &t);
                do_wredraw(wh, &t);
            }
        } else {                                /* the items keep their places
                                                 * in the box: move the box */
            wind_get_grect(wh, WF_WORKXYWH, &t);
            obj_wfree(pw->w_root, t.g_x, t.g_y, t.g_w, t.g_h);
            desk_verify(wh);
        }
        break;
    default:
        break;
    }
}
