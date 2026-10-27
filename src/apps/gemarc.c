/* GemARC: ARC archives on gem4xe -- opened, listed, taken out and made.
 *
 * A window lists the archive's members; a click selects one, Extract
 * takes the selected ones out to a folder the file selector names, and
 * Add files puts files in, replacing members of the same name.  The work
 * is src/apps/arcfile.c and arccodec.c, which tests/host/test_gemarc.py
 * runs on the host against real archives and The Unarchiver; this file
 * is the GEM program around them and the GEMDOS they read and write
 * through.
 *
 * Built --data-model=large: the tables (55 KB) and the member list come
 * from Malloc, the resource goes far, and the only things in bank $00
 * are the file selector's two buffers, which must be (src/app/gem.h) --
 * they are on the stack, in fsel_ask.  Every word a person reads is in
 * GEMARC.RSC (tools/gemarcrsc.py). */
#include "gem.h"
#include "arcfile.h"
#include "gemarcrsc.h"

#define MAXLIST   512               /* members listed */
#define BUFSIZE   2048
#define PATHLEN   GEM_PATH_MAX

static WORD vh, wh = -1, wchar, hchar;
static WORD wx, wy, ww, whh;        /* the window's work area */
static OBJECT *menu;

static ARC_ENTRY FAR *list;
static uint16_t nlist, top;         /* members, and the first one shown */
static char FAR (*names)[ARC_NAMELEN];

static char archive[PATHLEN];       /* the open archive's path, "" for none */
static char lastdir[PATHLEN];       /* where the file selector starts */
static char title[PATHLEN + 4];
static char info[100];
static char line[100];
static char msg[300];
static DTA dta;
/* Paths being built.  FAR, not on the stack: the stack is bank $00's and
 * small, and nothing these are handed to wants bank $00 -- GEMDOS takes
 * far names.  Only fsel_ask's and main's own buffers must be near. */
static char xpath[PATHLEN], xdir[PATHLEN], xspec[PATHLEN], xtemp[PATHLEN];

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];

/* -- small things ------------------------------------------------------------ */

static char FAR *str(WORD i)
{
    char FAR *s = 0;

    rsrc_gaddr(R_STRING, i, (void **)&s);
    return s;
}

static uint16_t slen(const char FAR *s)
{
    uint16_t n = 0;

    while (s[n])
        n++;
    return n;
}

static void scpy(char *d, const char FAR *s, uint16_t max)
{
    uint16_t k;
    char c;

    for (k = 0; k < max - 1 && (c = s[k]) != 0; k++)
        d[k] = c;
    d[k] = 0;
}

/* A number in decimal, right-aligned in `w` places (0 for as it comes). */
static uint16_t udec(char *d, uint32_t v, uint16_t w)
{
    char t[12];
    uint16_t n = 0, k = 0;

    do {
        t[n++] = (char)('0' + (uint16_t)(v % 10));
        v /= 10;
    } while (v);
    while (k + n < w)
        d[k++] = ' ';
    while (n)
        d[k++] = t[--n];
    d[k] = 0;
    return k;
}

/* A resource string with each '#' the next of `nums` and '@' `name`. */
static void fill(char *d, uint16_t max, WORD which, const uint32_t *nums,
                 const char FAR *name)
{
    const char FAR *s = str(which);
    uint16_t k = 0, j;
    char c, t[12];

    while ((c = *s++) != 0 && k < max - 12) {
        if (c == '#' && nums) {
            udec(t, *nums++, 0);
            for (j = 0; t[j]; j++)
                d[k++] = t[j];
        } else if (c == '@' && name) {
            for (j = 0; name[j] && k < max - 1; j++)
                d[k++] = name[j];
        } else {
            d[k++] = c;
        }
    }
    d[k] = 0;
}

static WORD alert(WORD which, uint32_t n)
{
    fill(msg, sizeof msg, which, &n, 0);
    return form_alert(1, msg);
}

/* The folder part of a path: everything to its last '\', which stays. */
static void dir_of(const char *path, char *dir)
{
    uint16_t k, cut = 0;

    for (k = 0; path[k]; k++)
        if (path[k] == '\\' || path[k] == ':')
            cut = (uint16_t)(k + 1);
    for (k = 0; k < cut; k++)
        dir[k] = path[k];
    dir[cut] = 0;
}

/* -- the platform under arcfile.c: GEMDOS ----------------------------------- */

int pf_open(const char FAR *name)
{
    LONG h = Fopen(name, 0);
    return h < 0 ? -1 : (int)h;
}

int pf_create(const char FAR *name)
{
    LONG h = Fcreate(name, 0);
    return h < 0 ? -1 : (int)h;
}

long pf_read(int h, uint8_t FAR *buf, long n)
{
    return Fread((WORD)h, n, buf);
}

long pf_write(int h, const uint8_t FAR *buf, long n)
{
    return Fwrite((WORD)h, n, buf);
}

long pf_seek(int h, long offset)
{
    return Fseek(offset, (WORD)h, 0);
}

void pf_close(int h)
{
    Fclose((WORD)h);
}

int pf_delete(const char FAR *name)
{
    return Fdelete(name) < 0 ? -1 : 0;
}

int pf_rename(const char FAR *from, const char FAR *to)
{
    return Frename(from, to) < 0 ? -1 : 0;
}

void pf_stamp(const char FAR *name, uint16_t *date, uint16_t *time)
{
    Fsetdta(&dta);
    if (Fsfirst(name, 0) == 0) {
        *date = dta.d_date;
        *time = dta.d_time;
    } else {
        *date = (uint16_t)Tgetdate();
        *time = (uint16_t)Tgettime();
    }
}

void pf_setstamp(int h, uint16_t date, uint16_t time)
{
    WORD t[2];

    if (!date)
        return;
    t[0] = (WORD)time;
    t[1] = (WORD)date;
    Fdatime(t, (WORD)h, 1);             /* a DOS that cannot, cannot */
}

static WORD progress_text;

void arc_progress(const char FAR *name)
{
    fill(info, sizeof info, progress_text, 0, name);
    if (wh >= 0)
        wind_set_str(wh, WF_INFO, info);
}

/* -- the window --------------------------------------------------------------- */

static uint16_t rows(void)
{
    WORD r = (WORD)(whh / hchar) - 1;   /* the heading takes one */
    return r > 0 ? (uint16_t)r : 1;
}

static void set_info(void)
{
    uint32_t n[3], o = 0, c = 0;
    uint16_t i;

    if (!archive[0]) {
        scpy(info, str(ST_NONE), sizeof info);
    } else {
        for (i = 0; i < nlist; i++) {
            o += list[i].osize;
            c += list[i].csize;
        }
        n[0] = nlist;
        n[1] = o;
        n[2] = o ? (c * 100UL + o / 2) / o : 100;
        fill(info, sizeof info, ST_INFO, n, 0);
    }
    wind_set_str(wh, WF_INFO, info);
}

static void set_slider(void)
{
    uint16_t r = rows();
    WORD size = 1000, pos = 0;

    if (nlist > r) {
        size = (WORD)((uint32_t)r * 1000UL / nlist);
        pos = (WORD)((uint32_t)top * 1000UL / (nlist - r));
    }
    wind_set(wh, WF_VSLSIZ, size, 0, 0, 0);
    wind_set(wh, WF_VSLIDE, pos, 0, 0, 0);
}

/* One member as a line of the list. */
static void member_line(uint16_t i)
{
    ARC_ENTRY FAR *e = &list[i];
    uint16_t k = 0, j, d;
    uint8_t m = e->method;
    uint32_t n = m;
    const char FAR *mn;
    char c;

    for (j = 0; j < ARC_NAMELEN - 1 && (c = e->name[j]) != 0; j++)
        line[k++] = c;
    while (k < 12)
        line[k++] = ' ';
    k += udec(line + k, e->osize, 9);
    k += udec(line + k, e->csize, 9);
    line[k++] = ' ';
    line[k++] = ' ';
    if (m >= 1 && m <= 9) {
        mn = str((WORD)(ST_M1 + m - 1));
        for (j = 0; mn[j]; j++)
            line[k++] = mn[j];
    } else {
        fill(line + k, 20, ST_MX, &n, 0);
        k += slen(line + k);
    }
    while (k < 42)
        line[k++] = ' ';
    d = e->date;                         /* DD-MM-YY */
    j = (uint16_t)(d & 31);
    line[k++] = (char)('0' + j / 10);
    line[k++] = (char)('0' + j % 10);
    line[k++] = '-';
    j = (uint16_t)((d >> 5) & 15);
    line[k++] = (char)('0' + j / 10);
    line[k++] = (char)('0' + j % 10);
    line[k++] = '-';
    j = (uint16_t)(((d >> 9) + 80) % 100);
    line[k++] = (char)('0' + j / 10);
    line[k++] = (char)('0' + j % 10);
    line[k] = 0;
}

static void draw_list(void)
{
    WORD pxy[4], y;
    uint16_t i, r = rows();

    vswr_mode(vh, MD_REPLACE);
    vsf_interior(vh, FIS_SOLID);
    vsf_color(vh, 0);
    pxy[0] = wx;
    pxy[1] = wy;
    pxy[2] = (WORD)(wx + ww - 1);
    pxy[3] = (WORD)(wy + whh - 1);
    vr_recfl(vh, pxy);
    vst_color(vh, 1);
    if (!archive[0])
        return;
    scpy(line, str(ST_HEAD), sizeof line);
    v_gtext(vh, (WORD)(wx + 4), wy, line);
    pxy[0] = wx;
    pxy[2] = (WORD)(wx + ww - 1);
    pxy[1] = pxy[3] = (WORD)(wy + hchar - 1);
    v_pline(vh, 2, pxy);
    y = (WORD)(wy + hchar);
    for (i = top; i < nlist && i < top + r; i++, y = (WORD)(y + hchar)) {
        member_line(i);
        if (list[i].sel) {
            vsf_color(vh, 1);
            pxy[0] = wx;
            pxy[1] = y;
            pxy[2] = (WORD)(wx + ww - 1);
            pxy[3] = (WORD)(y + hchar - 1);
            vr_recfl(vh, pxy);
            vst_color(vh, 0);
            v_gtext(vh, (WORD)(wx + 4), y, line);
            vst_color(vh, 1);
            vsf_color(vh, 0);
        } else {
            v_gtext(vh, (WORD)(wx + 4), y, line);
        }
    }
}

static void redraw(WORD x, WORD y, WORD w, WORD h)
{
    WORD rx, ry, rw, rh, pxy[4];

    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    wind_get(wh, WF_FIRSTXYWH, &rx, &ry, &rw, &rh);
    while (rw && rh) {
        WORD ax = rx > x ? rx : x, ay = ry > y ? ry : y;
        WORD bx = (rx + rw < x + w) ? rx + rw : x + w;
        WORD by = (ry + rh < y + h) ? ry + rh : y + h;

        if (bx > ax && by > ay) {
            pxy[0] = ax;
            pxy[1] = ay;
            pxy[2] = (WORD)(bx - 1);
            pxy[3] = (WORD)(by - 1);
            vs_clip(vh, 1, pxy);
            draw_list();
        }
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    vs_clip(vh, 0, pxy);
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

static void refresh(void)
{
    set_slider();
    redraw(wx, wy, ww, whh);
}

static void scroll_to(long t)
{
    uint16_t r = rows();
    long most = (nlist > r) ? (long)(nlist - r) : 0;

    if (t > most)
        t = most;
    if (t < 0)
        t = 0;
    if ((uint16_t)t != top) {
        top = (uint16_t)t;
        refresh();
    }
}

static void menu_state(void)
{
    WORD on = archive[0] != 0;

    menu_ienable(menu, CLOSITEM, on);
    menu_ienable(menu, XSELITEM, on);
    menu_ienable(menu, XALLITEM, on);
    menu_ienable(menu, SALLITEM, on);
    menu_ienable(menu, ADDITEM, on);
}

/* -- the file selector ------------------------------------------------------ */

/* Ask for a file in `lastdir`, under `label`.  The path chosen goes to
 * `path` (folder and name) and the folder to lastdir; FALSE if cancelled.
 * `mask` is the selector's, *.ARC or *.*.  The buffers are on the stack:
 * fsel wants bank $00. */
static WORD fsel_ask(WORD label, const char *mask, char *path, char *sel_out)
{
    char p[PATHLEN], s[16];
    WORD button = 0;
    uint16_t k, j;

    scpy(p, lastdir, PATHLEN - 16);
    k = slen(p);
    for (j = 0; mask[j]; j++)
        p[k++] = mask[j];
    p[k] = 0;
    s[0] = 0;
    fsel_exinput(p, s, &button, str(label));
    if (button != 1)
        return FALSE;
    dir_of(p, lastdir);
    scpy(path, lastdir, PATHLEN);
    k = slen(path);
    for (j = 0; s[j] && k < PATHLEN - 1; j++)
        path[k++] = s[j];
    path[k] = 0;
    if (sel_out)
        scpy(sel_out, s, 16);
    return TRUE;
}

/* -- the archive -------------------------------------------------------------- */

static WORD wild(const char *s)
{
    uint16_t k;

    if (!s[0])
        return TRUE;
    for (k = 0; s[k]; k++)
        if (s[k] == '*' || s[k] == '?')
            return TRUE;
    return FALSE;
}

static void load(void)
{
    int r;

    nlist = 0;
    top = 0;
    graf_mouse(BUSYBEE, 0);
    r = arc_list(archive, list, MAXLIST, &nlist);
    graf_mouse(ARROW, 0);
    if (r == ARC_E_FULL) {
        alert(ST_FULL, MAXLIST);
    } else if (r != ARC_OK) {
        alert(r == ARC_E_OPEN ? ST_NOOPEN : ST_NOTARC, 0);
        archive[0] = 0;
        nlist = 0;
    }
    scpy(title, archive[0] ? archive : str(ST_TITLE), sizeof title);
    wind_set_str(wh, WF_NAME, title);
    set_info();
    menu_state();
    refresh();
}

static void open_archive(const char *path)
{
    scpy(archive, path, PATHLEN);
    dir_of(archive, lastdir);
    load();
}

static void do_open(void)
{
    if (fsel_ask(ST_TOPEN, "*.ARC", xpath, 0))
        open_archive(xpath);
}

static void do_new(void)
{
    char *path = xpath, sel[16];
    WORD h;
    uint8_t end[2];

    if (!fsel_ask(ST_TNEW, "*.ARC", path, sel) || !sel[0] || wild(sel))
        return;
    h = (WORD)Fcreate(path, 0);
    if (h < 0) {
        alert(ST_NOOPEN, 0);
        return;
    }
    end[0] = ARC_MARK;
    end[1] = 0;
    Fwrite(h, 2L, end);
    Fclose(h);
    open_archive(path);
}

static void do_close(void)
{
    archive[0] = 0;
    nlist = 0;
    top = 0;
    scpy(title, str(ST_TITLE), sizeof title);
    wind_set_str(wh, WF_NAME, title);
    set_info();
    menu_state();
    refresh();
}

/* The member's name as a file here: upper case, letters, digits and '_'
 * -- an archive made elsewhere can carry a space ("ZMAG.40 ") or worse. */
static void file_name(const char FAR *member, char *to)
{
    uint16_t k, n = 0;
    char c;

    for (k = 0; k < ARC_NAMELEN - 1 && (c = member[k]) != 0; k++) {
        if (c >= 'a' && c <= 'z')
            c = (char)(c - 32);
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'
            || c == '.')
            to[n++] = c;
    }
    to[n] = 0;
}

static void do_extract(WORD all)
{
    char *path = xpath, *dir = xdir, fname[ARC_NAMELEN];
    uint16_t i, k, j, want = 0;
    uint32_t ok = 0, bad = 0;
    WORD replace = 0;                   /* 0 not asked, 1 replace, 2 skip */
    int r;

    for (i = 0; i < nlist; i++)
        if (all || list[i].sel)
            want++;
    if (!want) {
        alert(ST_NOSEL, 0);
        return;
    }
    if (!fsel_ask(ST_TOUT, "*.*", path, 0))
        return;
    dir_of(path, dir);
    for (i = 0; i < nlist; i++)
        if ((all || list[i].sel) && list[i].method <= ARC_SQUASHED) {
            file_name(list[i].name, fname);
            scpy(path, dir, PATHLEN);
            k = slen(path);
            for (j = 0; fname[j]; j++)
                path[k++] = fname[j];
            path[k] = 0;
            Fsetdta(&dta);
            if (Fsfirst(path, 0) == 0) {
                WORD b = form_alert(1, str(ST_EXISTS));
                if (b == 3)
                    return;                 /* Cancel: nothing taken out */
                replace = b;
                break;                      /* asked once, for all of them */
            }
        }
    progress_text = ST_OUTING;
    graf_mouse(BUSYBEE, 0);
    for (i = 0; i < nlist; i++) {
        if (!all && !list[i].sel)
            continue;
        file_name(list[i].name, fname);
        scpy(path, dir, PATHLEN);
        k = slen(path);
        for (j = 0; fname[j]; j++)
            path[k++] = fname[j];
        path[k] = 0;
        if (replace == 2) {
            Fsetdta(&dta);
            if (Fsfirst(path, 0) == 0)
                continue;
        }
        r = arc_extract(archive, &list[i], path);
        if (r == ARC_OK)
            ok++;
        else
            bad++;
    }
    graf_mouse(ARROW, 0);
    set_info();
    if (bad)
        alert(ST_BAD, bad);
    alert(ST_DONE, ok);
}

static WORD same_name(const char FAR *a, const char FAR *b)
{
    uint16_t k;
    char x, y;

    for (k = 0;; k++) {
        x = a[k];
        y = b[k];
        if (x >= 'a' && x <= 'z')
            x = (char)(x - 32);
        if (y >= 'a' && y <= 'z')
            y = (char)(y - 32);
        if (x != y)
            return FALSE;
        if (!x)
            return TRUE;
    }
}

static void do_add(void)
{
    char *path = xpath, *dir = xdir, *spec = xspec, *temp = xtemp;
    char sel[16], arcname[ARC_NAMELEN];
    uint16_t n = 0, k, j;
    LONG e;
    int r;
    const char FAR *t;

    if (!fsel_ask(ST_TADD, "*.*", path, sel))
        return;
    dir_of(path, dir);
    dir_of(archive, temp);              /* the archive's own name, to skip */
    file_name(archive + slen(temp), arcname);
    scpy(spec, dir, PATHLEN);
    k = slen(spec);
    if (wild(sel)) {
        const char *m = sel[0] ? sel : "*.*";
        for (j = 0; m[j]; j++)
            spec[k++] = m[j];
        spec[k] = 0;
        Fsetdta(&dta);
        for (e = Fsfirst(spec, 0); e == 0; e = Fsnext()) {
            if (dta.d_attrib & (FA_SUBDIR | FA_VOLUME))
                continue;
            if (same_name(dta.d_fname, arcname)
                || same_name(dta.d_fname, str(ST_TEMP)))
                continue;
            if (n == ARC_ADD_MAX) {
                alert(ST_TOOMANY, ARC_ADD_MAX);
                return;
            }
            scpy(names[n], dta.d_fname, ARC_NAMELEN);
            n++;
        }
    } else {
        scpy(names[n], sel, ARC_NAMELEN);
        n++;
    }
    if (!n) {
        alert(ST_NOFILES, 0);
        return;
    }
    dir_of(archive, temp);
    k = slen(temp);
    t = str(ST_TEMP);
    for (j = 0; t[j]; j++)
        temp[k++] = t[j];
    temp[k] = 0;
    progress_text = ST_ADDING;
    graf_mouse(BUSYBEE, 0);
    r = arc_add(archive, temp, dir, names, n, list, MAXLIST);
    graf_mouse(ARROW, 0);
    if (r != ARC_OK)
        alert(ST_ADDFAIL, 0);
    load();
    if (r == ARC_OK)
        alert(ST_ADDED, n);
}

static void select_all(void)
{
    uint16_t i;
    WORD any = FALSE;

    for (i = 0; i < nlist; i++)
        if (!list[i].sel)
            any = TRUE;
    for (i = 0; i < nlist; i++)
        list[i].sel = (uint8_t)any;
    refresh();
}

static void click(WORD mx, WORD my)
{
    WORD row;
    uint16_t i;

    if (mx < wx || mx >= wx + ww || my < wy + hchar || my >= wy + whh)
        return;
    row = (WORD)((my - wy - hchar) / hchar);
    i = (uint16_t)(top + row);
    if (i >= nlist)
        return;
    list[i].sel = (uint8_t)!list[i].sel;
    redraw(wx, (WORD)(wy + hchar + row * hchar), ww, hchar);
}

static void about(void)
{
    OBJECT *t;
    WORD x, y, w, h;

    rsrc_gaddr(R_TREE, ADABOUT, (void **)&t);
    form_center(t, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    objc_draw(t, 0, 8, x, y, w, h);
    form_do(t, 0);
    t[ABOK].ob_state = NORMAL;
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}

/* A menu item; TRUE to quit. */
static WORD do_menu(WORD title_obj, WORD item)
{
    WORD quit = FALSE;

    switch (item) {
    case ABOUITEM: about(); break;
    case OPENITEM: do_open(); break;
    case NEWITEM:  do_new(); break;
    case CLOSITEM: do_close(); break;
    case QUITITEM: quit = TRUE; break;
    case XSELITEM: do_extract(FALSE); break;
    case XALLITEM: do_extract(TRUE); break;
    case SALLITEM: select_all(); break;
    case ADDITEM:  do_add(); break;
    default: break;
    }
    if (title_obj)
        menu_tnormal(menu, title_obj, 1);
    return quit;
}

/* A key: CONTROL and a letter is a menu item's, the arrows scroll. */
static WORD do_key(WORD ks, WORD kr)
{
    WORD c = (WORD)(kr & 0xFF), scan = (WORD)((kr >> 8) & 0xFF);
    WORD on = archive[0] != 0;

    if (ks & K_CTRL) {
        if (c >= 1 && c <= 26)
            c = (WORD)(c + 'A' - 1);
        if (c >= 'a' && c <= 'z')
            c = (WORD)(c - 32);
        switch (c) {
        case 'O': return do_menu(0, OPENITEM);
        case 'N': return do_menu(0, NEWITEM);
        case 'Q': return do_menu(0, QUITITEM);
        case 'U': if (on) do_menu(0, CLOSITEM); break;
        case 'E': if (on) do_menu(0, XSELITEM); break;
        case 'A': if (on) do_menu(0, SALLITEM); break;
        case 'I': if (on) do_menu(0, ADDITEM); break;
        default: break;
        }
        return FALSE;
    }
    if (scan == 0x48)
        scroll_to((long)top - 1);
    else if (scan == 0x50)
        scroll_to((long)top + 1);
    return FALSE;
}

static void arrowed(WORD how)
{
    long r = rows();

    switch (how) {
    case WA_UPPAGE: scroll_to((long)top - r); break;
    case WA_DNPAGE: scroll_to((long)top + r); break;
    case WA_UPLINE: scroll_to((long)top - 1); break;
    case WA_DNLINE: scroll_to((long)top + 1); break;
    default: break;
    }
}

static void *get(LONG n)
{
    LONG a = Malloc(n);
    return a > 0 ? (void *)(uint32_t)a : 0;
}

int main(void)
{
    char cmd[130], tail[132];
    WORD wbox, hbox, dx, dy, dw, dh, a, b;
    WORD msgb[8], mx, my, mb, ks, kr, br, ev, done = FALSE, n;
    uint16_t FAR *prefix;
    uint8_t FAR *suffix, *stack, *ib, *ob;
    uint32_t FAR *hash;
    uint16_t FAR *codes;

    cmd[0] = 0;
    tail[0] = 0;
    appl_init();
    shel_read(cmd, tail);
    if (!rsrc_load("GEMARC.RSC")) {
        appl_exit();
        return 1;
    }
    prefix = (uint16_t FAR *)get(2L * ARC_LZW_ENTRIES);
    suffix = (uint8_t FAR *)get(ARC_LZW_ENTRIES);
    stack = (uint8_t FAR *)get(ARC_LZW_ENTRIES);
    hash = (uint32_t FAR *)get(4L * ARC_HASH);
    codes = (uint16_t FAR *)get(2L * ARC_HASH);
    ib = (uint8_t FAR *)get(BUFSIZE);
    ob = (uint8_t FAR *)get(BUFSIZE);
    list = (ARC_ENTRY FAR *)get((LONG)sizeof(ARC_ENTRY) * MAXLIST);
    names = (char FAR (*)[ARC_NAMELEN])get((LONG)ARC_NAMELEN * ARC_ADD_MAX);
    if (!prefix || !suffix || !stack || !hash || !codes || !ib || !ob
        || !list || !names) {
        form_alert(1, str(ST_NOMEM));
        rsrc_free();
        appl_exit();
        return 1;
    }
    arc_tables(prefix, suffix, stack, hash, codes);
    arc_buffers(ib, ob, BUFSIZE);

    vh = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &vh, work_out);
    vst_alignment(vh, 0, 5, &a, &b);    /* text hangs from its top */
    rsrc_gaddr(R_TREE, ADMENU, (void **)&menu);
    menu_bar(menu, 1);

    wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
    wh = wind_create(NAME | INFO | CLOSER | MOVER | UPARROW | DNARROW | VSLIDE,
                     dx, dy, dw, dh);
    if (wh < 0) {
        menu_bar(menu, 0);
        v_clsvwk(vh);
        rsrc_free();
        appl_exit();
        return 1;
    }
    scpy(title, str(ST_TITLE), sizeof title);
    wind_set_str(wh, WF_NAME, title);
    wind_open(wh, dx, dy, dw, dh);
    wind_get(wh, WF_WORKXYWH, &wx, &wy, &ww, &whh);
    Dgetpath(lastdir + 2, 0);
    lastdir[0] = (char)('A' + Dgetdrv());
    lastdir[1] = ':';
    n = (WORD)slen(lastdir);
    if (n < 3 || lastdir[n - 1] != '\\') {
        lastdir[n++] = '\\';
        lastdir[n] = 0;
    }
    set_info();
    menu_state();

    /* A file handed over in the command tail -- dropped on GEMARC.PRG, or
     * an .ARC opened from the desktop. */
    n = (WORD)(uint8_t)tail[0];
    if (n > 0 && n < 128) {
        WORD i = 1, k = 0;
        while (i <= n && tail[i] == ' ')
            i++;
        while (i <= n && tail[i] && tail[i] != ' ' && tail[i] != '\r'
               && k < PATHLEN - 1)
            xpath[k++] = tail[i++];
        xpath[k] = 0;
        if (k)
            open_archive(xpath);
    }

    while (!done) {
        ev = evnt_multi_moblk(MU_MESAG | MU_KEYBD | MU_BUTTON, 1, 1, 1, 0, 0,
                              msgb, 0, 0, &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_MESAG) {
            switch (msgb[0]) {
            case MN_SELECTED:
                done = do_menu(msgb[3], msgb[4]);
                break;
            case WM_REDRAW:
                if (msgb[3] == wh)
                    redraw(msgb[4], msgb[5], msgb[6], msgb[7]);
                break;
            case WM_TOPPED:
                if (msgb[3] == wh)
                    wind_set(wh, WF_TOP, 0, 0, 0, 0);
                break;
            case WM_CLOSED:
                if (msgb[3] == wh) {
                    if (archive[0])
                        do_close();
                    else
                        done = TRUE;
                }
                break;
            case WM_MOVED:
                if (msgb[3] == wh) {
                    wind_set(wh, WF_CURRXYWH, msgb[4], msgb[5], msgb[6], msgb[7]);
                    wind_get(wh, WF_WORKXYWH, &wx, &wy, &ww, &whh);
                }
                break;
            case WM_ARROWED:
                if (msgb[3] == wh)
                    arrowed(msgb[4]);
                break;
            case WM_VSLID:
                if (msgb[3] == wh && nlist > rows())
                    scroll_to((long)msgb[4] * (long)(nlist - rows()) / 1000L);
                break;
            default:
                break;
            }
        }
        if ((ev & MU_KEYBD) && !done)
            done = do_key(ks, kr);
        if ((ev & MU_BUTTON) && !done && wind_find(mx, my) == wh)
            click(mx, my);
    }
    wind_close(wh);
    wind_delete(wh);
    menu_bar(menu, 0);
    v_clsvwk(vh);
    rsrc_free();
    appl_exit();
    return 0;
}
