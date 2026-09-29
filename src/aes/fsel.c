/* fsel.c -- the file selector: fsel_input and fsel_exinput.  EmuTOS
 * aes/gemfslib.c, with its string helpers from util/optimize.c and
 * util/miscutil.c, on the file layer gem4xe has.
 *
 * THE TREE.  The donor's selector lives in the AES's own resource, fixed
 * up once at start-up; gem4xe has no resident resource and no bank-$00
 * room to keep a 35-object tree in, so the tree travels as a .RSC file's
 * bytes in the far image (tools/fselrsc.py -> fs_rsc) and is loaded into
 * the application pool each time the selector opens -- copied down, fixed
 * up by rs_fixit() exactly as an application's resource is, used, and
 * released with the rest of the selector's memory when it closes.  The
 * indices come from the same script, through build/fsel_rsc.h.  What the
 * donor's fs_start() does to the tree's widths is done to every fresh
 * copy, since none of them lives to be done twice.  The pool is the
 * budget: 1516 bytes of tree (FS_RSC_SIZE), 272 of work area, and an
 * application that holds a resource of more than the remainder gets
 * FALSE, nothing drawn, the pool as it was (docs/phase11.md).
 *
 * THE NAMES.  The names of the directory being shown are the one thing
 * the donor keeps in the memory it takes per call that will not fit the
 * pool, so they sit in a far buffer taken once at AES start-up
 * (fs_start(), like sh_init's) and read through far_strget: 64 slots of
 * a flag byte, the name, and its NUL, which is what the donor's
 * ad_fsnames holds at the offsets g_fslist counts; the slots being of one
 * size, the list holds slot numbers and the sort swaps those.  The flag
 * is the donor's -- 0x07 for a folder, ' ' for a file.  On DOS 2 it is
 * always ' ', there being no folders, and the selector's FCLSBOX does
 * what the donor does at the root, nothing; on a SpartaDOS a folder
 * clicked goes into the path and FCLSBOX comes back out of it, the
 * donor's own code, which never knew the DOS underneath had changed.
 *
 * THE DIRECTORY.  The donor's dos_sfirst/dos_snext is CIO's directory
 * read here: the path's file part replaced by *.* and mapped through
 * sh_cioname (X:\DIR\*.* -> Dn:*.* or Dn:>DIR>*.*, the DOS seam's rule,
 * src/sys/dos.h), opened with aux1 = 6 and read a record at a time.  A
 * record is DOS 2's 17-character line -- a lock mark, a space, the name
 * in 8, the extension in 3, a space, and the sector count in 3 -- which
 * a SpartaDOS prints too, marking a subdirectory its own way: 3.2 in the
 * extension field, X in the flag column (dos_folder_line knows both).
 * fs_entry() takes only the lines shaped so with a
 * name of DOS 2's characters, which passes over the deleted entries, the
 * FREE SECTORS line, and what a RAM disk with nothing on it says (an
 * unformatted D8: answers with 34 lines of noise).  The mask is applied
 * here with the donor's wildcmp, never by the DOS, so that *.C and A?.*
 * mean what they mean on the ST.  A drive that does not answer costs
 * CIO's timeout, about 1.2 seconds, and then follows the donor's own
 * error path: the path put back and the last directory read again.
 *
 * gl_drvbits says which drive buttons are live.  DOS 2 keeps no drive
 * map worth reading (docs/phase11.md), so all eight are, and a click on
 * a drive with nothing there takes the timeout and comes back.
 */
#include "portab.h"
#include <string.h>
#include "aes/aes.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/farmem.h"
#include "fsel_rsc.h"

#define NM_NAMES    FS_NM_NAMES
#define NM_DRIVES   FS_NM_DRIVES
#define NAME_OFFSET FS_F1NAME
#define DRIVE_OFFSET FS_FS1STDRV

#define LEN_FSNAME  (FS_LEN_NAME + 1)   /* flag, NAME.EXT, NUL: the donor's 14 */
#define LEN_FSPATH  (FS_LEN_DIRECT + 9) /* X:\ and a mask the field's width */
#define MAX_FILES   64                  /* the donor's nm_files, fixed */
#define LEN_FSWORK  (4 * LEN_FSPATH + MAX_FILES * 2)   /* ...and the typed line */

#define PATHSEP     '\\'
#define DRIVESEP    ':'
#define DIRLINE     17                  /* DOS 2's directory record, less its EOL */
#define FS_FILE     ' '                 /* the flag: the donor's */
#define FS_FOLDER   0x07

WORD gl_drvbits = 0x00FF;               /* drives A..H: buttons enabled */

static uint32_t fs_names_far;           /* MAX_FILES * LEN_FSNAME, 0 until fs_start */
static WORD *g_fslist;                  /* slot numbers, sorted: the donor's offsets */

void fs_start(void)
{
    if (!fs_names_far)
        fs_names_far = far_alloc((uint32_t)MAX_FILES * LEN_FSNAME);
}

/* ---- the donor's string helpers (util/optimize.c, util/miscutil.c) ---- */

/* 'SAMPLE.PRG' -> 'SAMPLE  PRG', 'TEST' -> 'TEST': the shape a
 * ________.___ template takes.  outstr holds 12. */
static void fmt_str(const char *instr, char *outstr)
{
    const char *p;
    char *q;

    for (p = instr, q = outstr; *p; p++) {
        if (*p == '.') {
            p++;
            break;
        }
        if (q - outstr < 8)
            *q++ = *p;
    }
    if (*p) {
        while (q - outstr < 8)
            *q++ = ' ';
        while (q - outstr < 11 && *p)
            *q++ = *p++;
    }
    *q = 0;
}

/* The reverse: 'SAMPLE  PRG' -> 'SAMPLE.PRG'. */
static void unfmt_str(const char *instr, char *outstr)
{
    const char *pstr = instr;

    while (*pstr && pstr - instr < 8) {
        WORD c = (uint8_t)*pstr++;      /* a WORD: B8, tools/ccbug */
        if (c != ' ')
            *outstr++ = (char)c;
    }
    if (*pstr) {
        *outstr++ = '.';
        while (*pstr)
            *outstr++ = *pstr++;
    }
    *outstr = 0;
}

static TEDINFO FAR *ted_of(OBJECT FAR *tree, WORD obj)
{
    return (TEDINFO FAR *)(uint16_t)tree[obj].ob_spec;
}

/* The string into the object's text, cut to the TEDINFO's length. */
static void inf_sset(OBJECT FAR *tree, WORD obj, const char *pstr)
{
    TEDINFO FAR *ted = ted_of(tree, obj);
    char *text = (char *)(uint16_t)ted->te_ptext;
    WORD len = ted->te_txtlen;      /* a scalar first: B5, tools/ccbug */
    WORD n = (WORD)(len - 1);

    while (n > 0 && *pstr) {
        *text++ = *pstr++;
        n--;
    }
    *text = 0;
}

static void inf_sget(OBJECT FAR *tree, WORD obj, char *pstr)
{
    strcpy(pstr, (const char *)(uint16_t)ted_of(tree, obj)->te_ptext);
}

/* 1 if `ok` is SELECTED, 0 if the object after it is, -1 if neither; the
 * one that was is put back to NORMAL. */
static WORD inf_what(OBJECT FAR *tree, WORD ok)
{
    WORD field;

    for (field = 0; field < 2; field++)
        if (tree[ok + field].ob_state & SELECTED) {
            tree[ok + field].ob_state = NORMAL;
            return field == 0;
        }
    return -1;
}

/* 0..7 for A..H at the front of the path, else -1. */
static WORD extract_drive_number(const char *path)
{
    if (path[0] && path[1] == DRIVESEP) {
        WORD c = (uint8_t)path[0];
        if (c >= 'a' && c <= 'z')
            c -= 0x20;
        if (c >= 'A' && c < 'A' + NM_DRIVES)
            return c - 'A';
    }
    return -1;
}

/* The default drive: A, which is D1:, where PATH= points (shel.c). */
static WORD dos_gdrv(void)
{
    return 0;
}

/* The donor's ins_char (gemobed.c), for fs_back's separator. */
static void ins_char(char *str, WORD pos, char chr, WORD tot_len)
{
    WORD ii, len = (WORD)strlen(str);

    for (ii = len; ii > pos; ii--)
        str[ii] = str[ii - 1];
    str[ii] = chr;
    if (len + 1 < tot_len)
        str[len + 1] = 0;
    else
        str[tot_len - 1] = 0;
}

/* ---- gemfslib.c ------------------------------------------------------ */

static void centre_title(OBJECT FAR *tree, WORD objnum)
{
    OBJECT FAR *str = tree + objnum;

    str->ob_x = (tree->ob_width
                 - (WORD)strlen((const char *)(uint16_t)str->ob_spec) * gl_wchar) / 2;
}

/* Back from the end of the path to the last separator, or the colon of
 * X: (a separator put in after it), or the start. */
static char *fs_back(char *pstr, char *pend)
{
    char *p;

    if (!pend)
        pend = pstr + strlen(pstr);
    for (p = pend; p != pstr; p--) {
        if (*p == PATHSEP)
            break;
        if (*p == DRIVESEP && p == pstr + 1) {
            ins_char(++p, 0, PATHSEP, LEN_FSPATH - 3);
            break;
        }
    }
    return p;
}

/* The file part of the path: after the last separator. */
static char *fs_pspec(char *pstr, char *pend)
{
    pend = fs_back(pstr, pend);
    if (*pend == PATHSEP)
        pend++;
    return pend;
}

/* The far slot a list position names. */
static uint32_t fs_slot(WORD pos)
{
    return fs_names_far + (uint32_t)g_fslist[pos] * LEN_FSNAME;
}

static WORD fs_comp(WORD i, WORD j)
{
    char a[LEN_FSNAME], b[LEN_FSNAME];

    far_strget(a, fs_slot(i), LEN_FSNAME);
    far_strget(b, fs_slot(j), LEN_FSNAME);
    return (WORD)strcmp(a, b);
}

static void fs_add(WORD thefile, char flag, const char *fname)
{
    uint32_t slot;

    g_fslist[thefile] = thefile;
    slot = fs_slot(thefile);
    far_write8(slot, (uint8_t)flag);
    far_strput(slot + 1, fname, LEN_FSNAME - 1);
}

/* A DOS 2 directory line into NAME.EXT and its flag -- FS_FILE, or
 * FS_FOLDER for a subdirectory where the DOS has them -- or 0 for a
 * line that is not one.  The parsing is the DOS seam's (dos_dirline),
 * shared with Fsfirst so that the selector and GEMDOS list alike. */
static char fs_entry(const char *line, WORD got, char *fname)
{
    uint8_t e = dos_dirline(line, got, fname, 0) & DOS_ENT_KIND;

    return e == DOS_ENT_DIR ? FS_FOLDER : e ? FS_FILE : 0;
}

/* Read the directory the path names into the far slots, those matching
 * pspec, sorted; *pcount how many.  FALSE when the drive does not answer. */
static WORD fs_active(char *ppath, const char *pspec, WORD *pcount)
{
    char allpath[LEN_FSPATH], name[CIO_NAME_MAX + 1];
    char line[DIRLINE + 8], entry[LEN_FSNAME], flag;
    char *fname;
    WORD thefile = 0, i, j, gap;
    int16_t fd;
    uint8_t st;

    strcpy(allpath, ppath);
    fname = fs_pspec(allpath, 0);
    strcpy(fname, "*.*");
    sh_cioname(allpath, name);
    fd = cio_open(name, CIO_A_DIR, 0);
    if (fd < 0) {
        *pcount = 0;
        return FALSE;
    }
    while (thefile < MAX_FILES) {
        uint16_t got = 0;
        st = cio_getrec(fd, line, sizeof line, &got);
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        flag = fs_entry(line, (WORD)got, entry);
        if (flag == FS_FOLDER || (flag && dos_wildcmp(pspec, entry)))
            fs_add(thefile++, flag, entry);
        if (st == CIO_OK_EOF)
            break;
    }
    cio_close(fd);
    *pcount = thefile;

    /* the donor's shell sort, K&R page 108 */
    for (gap = thefile / 2; gap > 0; gap /= 2)
        for (i = gap; i < thefile; i++)
            for (j = i - gap; j >= 0; j -= gap) {
                WORD temp;
                if (fs_comp(j, j + gap) <= 0)
                    break;
                temp = g_fslist[j];
                g_fslist[j] = g_fslist[j + gap];
                g_fslist[j + gap] = temp;
            }
    return TRUE;
}

static WORD fs_1scroll(WORD curr, WORD count, WORD touchob)
{
    WORD newcurr = (touchob == FS_FUPAROW) ? curr - 1 : curr + 1;

    if (newcurr < 0)
        newcurr++;
    if (count - newcurr < NM_NAMES)
        newcurr--;
    return (count > NM_NAMES) ? newcurr : curr;
}

/* The nine name lines from the list at currtop, and the elevator. */
static void fs_format(OBJECT FAR *tree, WORD currtop, WORD count)
{
    WORD i, cnt, y, h, th;
    char name[LEN_FSNAME], raw[LEN_FSNAME];
    OBJECT FAR *obj;

    cnt = count - currtop;
    if (cnt > NM_NAMES)
        cnt = NM_NAMES;
    for (i = 0, obj = tree + NAME_OFFSET; i < NM_NAMES; i++, obj++) {
        if (i < cnt) {
            far_strget(raw, fs_slot(currtop + i), LEN_FSNAME);
            fmt_str(raw + 1, name + 1);
            name[0] = raw[0];
        } else {
            name[0] = ' ';
            name[1] = 0;
        }
        inf_sset(tree, NAME_OFFSET + i, name);
        obj->ob_type = G_FBOXTEXT;
        obj->ob_state = NORMAL;
    }

    y = 0;
    obj = tree + FS_FSVSLID;
    th = h = obj->ob_height;
    if (count > NM_NAMES) {
        h = mul_div_round(NM_NAMES, h, count);
        if (h < gl_hbox)
            h = gl_hbox;
        y = mul_div_round(currtop, th - h, count - NM_NAMES);
    }
    obj = tree + FS_FSVELEV;
    obj->ob_y = y;
    obj->ob_height = h;
}

static void fs_sel(OBJECT FAR *tree, WORD sel, WORD state)
{
    if (sel)
        ob_change(tree, FS_F1NAME + sel - 1, state, TRUE);
}

/* Scroll the list n names the arrow's way: the rows that stay are
 * blitted, the rest redrawn. */
static WORD fs_nscroll(OBJECT FAR *tree, WORD *psel, WORD curr, WORD count,
                       WORD touchob, WORD n)
{
    WORD i, newcurr, diffcurr, sy, dy, neg;
    GRECT r[2];

    newcurr = curr;
    for (i = 0; i < n; i++)
        newcurr = fs_1scroll(newcurr, count, touchob);

    diffcurr = newcurr - curr;
    if (diffcurr) {
        curr = newcurr;
        fs_sel(tree, *psel, NORMAL);
        *psel = 0;
        fs_format(tree, curr, count);
        gsx_gclip(&r[1]);
        ob_actxywh(tree, FS_F1NAME, &r[0]);

        neg = diffcurr < 0;
        if (neg)
            diffcurr = -diffcurr;

        if (diffcurr < NM_NAMES) {
            sy = r[0].g_y + r[0].g_h * diffcurr;
            dy = r[0].g_y;
            if (neg) {
                dy = sy;
                sy = r[0].g_y;
            }
            bb_screen(r[0].g_x, sy, r[0].g_x, dy, r[0].g_w,
                      r[0].g_h * (NM_NAMES - diffcurr));
            if (!neg)
                r[0].g_y += r[0].g_h * (NM_NAMES - diffcurr);
        } else {
            diffcurr = NM_NAMES;
        }
        r[0].g_h *= diffcurr;

        for (i = 0; i < 2; i++) {
            gsx_sclip(&r[i]);
            ob_draw(tree, i ? FS_FSVSLID : FS_FILEBOX, MAX_DEPTH);
        }
    }
    return curr;
}

/* A new directory: read it, show it.  FALSE when it could not be read. */
static WORD fs_newdir(char *fpath, char *pspec, OBJECT FAR *tree, WORD *pcount)
{
    static const WORD gl_fsobj[3] = {FS_FTITLE, FS_FILEBOX, FS_SCRLBAR};
    WORD i;

    ob_draw(tree, FS_FSDIRECT, MAX_DEPTH);
    if (!fs_active(fpath, pspec, pcount))
        return FALSE;
    fs_format(tree, 0, *pcount);
    ted_of(tree, FS_FTITLE)->te_ptext = (uint16_t)pspec;
    for (i = 0; i < 3; i++)
        ob_draw(tree, gl_fsobj[i], MAX_DEPTH);
    return TRUE;
}

/* The mask from the path's file part, *.* added to the path when it has
 * none. */
static void set_mask(char *mask, char *path)
{
    char *pend = fs_pspec(path, 0);
    WORD n = LEN_FSPATH - 1;

    if (!*pend)
        strcpy(pend, "*.*");
    while (n > 0 && *pend) {
        *mask++ = *pend++;
        n--;
    }
    *mask = 0;
}

static void select_drive(OBJECT FAR *tree, WORD drive, WORD redraw)
{
    WORD i, olddrive = -1;
    OBJECT FAR *obj, *start = tree + DRIVE_OFFSET;

    if (drive < 0 || drive >= NM_DRIVES)
        return;
    for (i = 0, obj = start; i < NM_DRIVES; i++, obj++)
        if (obj->ob_state & SELECTED) {
            obj->ob_state &= ~SELECTED;
            olddrive = i;
        }
    (start + drive)->ob_state |= SELECTED;
    if (redraw && drive != olddrive) {
        if (olddrive >= 0)
            ob_draw(tree, olddrive + DRIVE_OFFSET, MAX_DEPTH);
        ob_draw(tree, drive + DRIVE_OFFSET, MAX_DEPTH);
    }
}

/* THE DIRECTORY LINE SAYS D1:, and the path under it says A:.  A person
 * reads the Atari's names -- D1: to D8:, as the desktop's icons and
 * windows do (phase 73) -- and the program that asked gets its path back
 * in GEMDOS's, which is what every ST program passes and expects.  So the
 * line is translated as it is filled and as it is read, and nowhere else:
 * the path is A:\ from end to end. */
static WORD shown_drive(const char *path)
{
    return (WORD)(path[0] >= 'A' && path[0] < 'A' + NM_DRIVES
                  && path[1] == DRIVESEP);
}

/* The path into the directory line, as it is shown. */
static void dir_sset(OBJECT FAR *tree, const char *path)
{
    TEDINFO FAR *ted = ted_of(tree, FS_FSDIRECT);
    char *d = (char *)(uint16_t)ted->te_ptext;
    char *end = d + ted->te_txtlen - 1;

    if (shown_drive(path) && end - d > 3) {
        *d++ = 'D';
        *d++ = (char)('1' + path[0] - 'A');
        path++;
    }
    while (*path && d < end)
        *d++ = *path++;
    *d = 0;
}

/* What was typed on the directory line, as a path: "D1:" (or "1:") is
 * A:, a letter is itself, and the rest is copied. */
static void dir_sget(char *path, const char *line)
{
    const char *s = line;
    WORD n = 0;

    if ((s[0] == 'D' || s[0] == 'd') && s[1] >= '1' && s[1] <= '8'
        && s[2] == DRIVESEP) {
        path[n++] = (char)('A' + s[1] - '1');
        s += 2;
    } else if (s[0] >= '1' && s[0] <= '8' && s[1] == DRIVESEP) {
        path[n++] = (char)('A' + s[0] - '1');
        s += 1;
    }
    while (*s && n < LEN_FSPATH - 1)
        path[n++] = *s++;
    path[n] = 0;
}

/* Does the path differ from what the directory field shows? */
static WORD path_changed(OBJECT FAR *tree, const char *path)
{
    TEDINFO FAR *ted = ted_of(tree, FS_FSDIRECT);
    const char *line = (const char *)(uint16_t)ted->te_ptext;
    WORD n = (WORD)(ted->te_txtlen - 1);

    if (shown_drive(path)) {
        if (line[0] != 'D' || line[1] != (char)('1' + path[0] - 'A'))
            return TRUE;
        line += 2;
        path++;
        n -= 2;
    }
    return strncmp(path, line, (size_t)n) != 0;
}

static WORD get_drive(const char *path)
{
    WORD drive = extract_drive_number(path);

    return drive >= 0 ? drive : dos_gdrv();
}

/* X:\ and the mask into the path. */
static void drive_path(char *locstr, WORD drive, const char *mask)
{
    locstr[0] = (char)('A' + drive);
    locstr[1] = DRIVESEP;
    locstr[2] = PATHSEP;
    strcpy(locstr + 3, mask);
}

/* The selector: the tree made in the pool, the dialog run, the path and
 * the name given back, the pool released.  pilabel of 0 is fsel_input's
 * default title. */
WORD fs_input(char *pipath, char *pisel, WORD *pbutton, const char *pilabel)
{
    WORD cont, newlist, newsel, newdrive;
    WORD drive, dclkret, error;
    WORD touchob, value, fnum;
    WORD curr, count, sel;
    WORD mx, my;
    OBJECT FAR *tree, *obj;
    RSHDR *h;
    UWORD bitmask;
    char *ad_fpath, *ad_fname, *pstr;
    char *locstr, *locold, *mask;
    char selname[LEN_FSNAME];
    GRECT pt, rfs;
    uint16_t mark;
    WORD diff;

    curr = count = 0;
    if (!pipath || !fs_names_far)
        return FALSE;
    if (!*pipath) {
        strcpy(pipath, "A:\\*.*");
        *pipath += dos_gdrv();
    }

    /* the tree and the work area, from the pool: neither, and nothing
     * has happened */
    mark = pool_mark();
    h = pool_alloc(FS_RSC_SIZE, 2);
    g_fslist = pool_alloc(LEN_FSWORK, 2);
    if (!h || !g_fslist) {
        pool_release(mark);
        return FALSE;
    }
    locstr = (char *)(g_fslist + MAX_FILES);
    locold = locstr + LEN_FSPATH;
    mask = locold + LEN_FSPATH;

    far_get((uint8_t *)h, (uint32_t)(const uint8_t FAR *)fs_rsc, FS_RSC_SIZE);
    rs_fixit((uint32_t)(uint16_t)h);   /* a bank-zero base: the pool */
    tree = (OBJECT FAR *)(uint16_t)*(uint32_t *)((uint8_t *)h + h->rsh_trindex);

    /* the donor's fs_start: centred, and the scroll bar the width of a
     * box in this resolution, the title (which overhangs it) narrowed
     * to match */
    ob_center(tree, &rfs);
    diff = tree[FS_SCRLBAR].ob_width - gl_wbox;
    tree[FS_FTITLE].ob_width -= diff;
    tree[FS_SCRLBAR].ob_width = gl_wbox;
    tree[FS_FUPAROW].ob_width = gl_wbox;
    tree[FS_FDNAROW].ob_width = gl_wbox;
    tree[FS_FSVSLID].ob_width = gl_wbox;
    tree[FS_FSVELEV].ob_width = gl_wbox;

    /* the caller's path, cut to what the work area holds -- the donor
     * copies it whole, docs/phase11.md */
    for (diff = 0; diff < LEN_FSPATH - 1 && pipath[diff]; diff++)
        locstr[diff] = pipath[diff];
    locstr[diff] = 0;
    strcpy(locold, locstr);

    /* the strings in the form */
    set_mask(mask, locstr);
    ted_of(tree, FS_FTITLE)->te_ptext = (uint16_t)mask;

    ad_fpath = (char *)(uint16_t)ted_of(tree, FS_FSDIRECT)->te_ptext;
    dir_sset(tree, locstr);

    ad_fname = (char *)(uint16_t)ted_of(tree, FS_FSSELECT)->te_ptext;
    fmt_str(pisel, selname);
    inf_sset(tree, FS_FSSELECT, selname);

    if (pilabel)
        tree[FS_FSTITLE].ob_spec = (uint16_t)pilabel;
    centre_title(tree, FS_FSTITLE);

    obj = tree + DRIVE_OFFSET;
    for (drive = 0, bitmask = 1; drive < NM_DRIVES; drive++, bitmask <<= 1, obj++) {
        if (gl_drvbits & bitmask)
            obj->ob_state &= ~DISABLED;
        else
            obj->ob_state |= DISABLED;
    }
    select_drive(tree, get_drive(locstr), 0);

    gsx_sclip(&rfs);
    fm_dial(FMD_START, &gl_rcenter, &rfs);
    ob_draw(tree, ROOT, 2);

    sel = 0;
    newsel = newdrive = FALSE;
    cont = newlist = TRUE;
    error = 0;
    while (cont) {
        touchob = newlist ? 0 : fm_do(tree, FS_FSSELECT);
        gsx_mouse(&mx, &my);

        if (newlist) {
            fs_sel(tree, sel, NORMAL);
            dir_sset(tree, locstr);
            pstr = fs_pspec(locstr, 0);
            strcpy(pstr, mask);
            curr = 0;
            sel = 0;
            newlist = FALSE;
            if (fs_newdir(locstr, mask, tree, &count))
                error = 0;
            else
                ++error;
            if (error == 1) {           /* one retry: the old path, or the root */
                newlist = TRUE;
                if (strcmp(locstr, locold) != 0)
                    strcpy(locstr, locold);
                else
                    drive_path(locstr, dos_gdrv(), mask);
                select_drive(tree, get_drive(locstr), TRUE);
            }
            strcpy(locold, locstr);
        }

        value = 0;
        dclkret = (touchob & 0x8000) != 0;
        switch (touchob &= 0x7FFF) {
        case FS_FSOK:
            if (path_changed(tree, locstr)) {   /* an edited mask: OK lists, */
                ob_change(tree, FS_FSOK, NORMAL, TRUE); /* it does not exit */
                break;
            }
            /* FALLTHROUGH */
        case FS_FSCANCEL:
            cont = FALSE;
            break;
        case FS_FUPAROW:
        case FS_FDNAROW:
            value = 1;
            break;
        case FS_FSVSLID:
            ob_actxywh(tree, FS_FSVELEV, &pt);
            if (!inside(mx, my, &pt)) {
                touchob = (my <= pt.g_y) ? FS_FUPAROW : FS_FDNAROW;
                value = NM_NAMES;
                break;
            }
            /* FALLTHROUGH */
        case FS_FSVELEV:
            fm_own(TRUE);
            value = gr_slidebox(tree, FS_FSVSLID, FS_FSVELEV, TRUE);
            fm_own(FALSE);
            value = curr - mul_div_round(value, count - NM_NAMES, 1000);
            if (value >= 0) {
                touchob = FS_FUPAROW;
            } else {
                touchob = FS_FDNAROW;
                value = -value;
            }
            break;
        case FS_FCLSBOX:
            pstr = fs_back(locstr, 0);
            if (pstr == locstr)         /* a path like *.*: nothing, as TOS */
                break;
            if (*--pstr == DRIVESEP)    /* the root: nothing above it */
                break;
            pstr = fs_pspec(locstr, pstr);
            strcpy(pstr, mask);
            newlist = TRUE;
            break;
        default:
            if (touchob >= FS_F1NAME && touchob <= FS_F9NAME) {
                fnum = touchob - FS_F1NAME + 1;
                if (fnum > count)
                    break;
                if (sel && sel != fnum)
                    fs_sel(tree, sel, NORMAL);
                if (sel != fnum) {
                    sel = fnum;
                    fs_sel(tree, sel, SELECTED);
                }
                inf_sget(tree, touchob, selname);
                if (selname[0] == ' ') {        /* a file: the selection */
                    newsel = TRUE;
                    if (dclkret)
                        cont = FALSE;
                } else {                        /* a folder: into the path */
                    pstr = fs_pspec(locstr, 0);
                    unfmt_str(selname + 1, pstr);
                    pstr += strlen(pstr);
                    *pstr++ = PATHSEP;
                    strcpy(pstr, mask);
                    newlist = TRUE;
                }
                break;
            }
            drive = touchob - DRIVE_OFFSET;
            if (drive < 0 || drive >= NM_DRIVES)
                break;
            if (drive == get_drive(locstr))
                break;
            if (path_changed(tree, locstr))     /* an edited mask: no drive change */
                break;
            if (tree[touchob].ob_state & DISABLED)
                break;
            drive_path(locstr, drive, mask);
            newdrive = TRUE;
            break;
        }

        if (touchob == FS_FSCANCEL)
            break;

        if (!newlist && !newdrive && path_changed(tree, locstr)) {
            char *typed = mask + LEN_FSPATH;    /* the work area's fourth */

            dir_sget(typed, ad_fpath);
            if (get_drive(typed) != get_drive(locstr))
                newdrive = TRUE;
            else
                newlist = TRUE;
            strcpy(locstr, typed);
        }

        if (newdrive) {
            select_drive(tree, touchob - DRIVE_OFFSET, 1);
            newdrive = FALSE;
            newlist = TRUE;
        }

        if (newlist) {
            dir_sset(tree, locstr);
            set_mask(mask, locstr);
            if (!error) {
                selname[1] = 0;
                newsel = TRUE;
            }
        }

        if (newsel) {
            strcpy(ad_fname, selname + 1);
            ob_draw(tree, FS_FSSELECT, MAX_DEPTH);
            if (!cont)
                ob_change(tree, FS_FSOK, SELECTED, TRUE);
            newsel = FALSE;
        }

        if (value)
            curr = fs_nscroll(tree, &sel, curr, count, touchob, value);
    }

    strcpy(pipath, locstr);
    unfmt_str(ad_fname, selname);
    strcpy(pisel, selname);

    fm_dial(FMD_FINISH, &gl_rcenter, &rfs);

    *pbutton = inf_what(tree, FS_FSOK);
    pool_release(mark);
    return TRUE;
}
