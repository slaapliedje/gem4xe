/* dup.c -- DUP: DOS 2's disk menu in a GEM window, done by gem4xe.
 *
 * Part two of docs/disk-plan.md.  Not DUP.SYS but its lettered menu: a
 * 40-column window of text, the menu in it, a letter typed, DUP's question
 * asked, the answer typed, what came of it printed, and SELECT ITEM OR
 * RETURN FOR MENU again.  A person who knows DUP finds the same letters
 * asking the same things -- on any DOS, through GEMDOS, and for the whole
 * disks (format, duplicate, write DOS) through src/apps/diskops.c, which
 * DISKUTIL shares.
 *
 * It formats the way of the DOS it runs on: where the drive has folders
 * (G4DOS, SpartaDOS X; Dcaps) an SDFS, and H puts G4DOS on one; under
 * DOS 2 or MyDOS a DOS 2 disk, and H says that DOS's own DUP writes its
 * files.  L and B (phase 166) ask the AES to run a plain Atari program or
 * the cartridge, as the desktop's icons do: GEM ends, the program or the
 * cartridge runs, and GEM comes back -- so DUP quits once it has asked.
 * K, M and N -- binary save, run at an address, MEM.SAV -- need memory
 * GEM holds while it runs; each says so.
 *
 * Every line it prints is DUP.RSC's (tools/duprsc.py).  Errors are DUP's
 * numbers -- 170 for a file not found, 167 locked, 144 the disk refusing,
 * 138 no answer -- because a DUP user knows those.
 *
 * Large-data, as DISKUTIL is: far buffers are addressed as 32-bit numbers.
 */
#include <string.h>
#include "gem.h"
#include "duprsc.h"
#include "diskops.h"
#include "mkfs.h"

#define COLS      40
#define MAXROWS   24
#define MARGIN    4
#define LINEMAX   60
#define PATHMAX   80
#define MAXNAMES  64
#define KEY_RET   0x1C0D
#define KEY_BS    0x0E08
#define KEY_ESC   0x011B

/* What a key means now. */
#define M_SELECT  0                 /* a letter, or Return for the menu */
#define M_LINE    1                 /* an answer, ended by Return */
#define M_DEL     2                 /* Y or N, for each file D deletes */

static WORD vh, wh = -1, wchar, hchar, wx, wy, ww, whh, rows;
static OBJECT *menu;
static char scr[MAXROWS][COLS + 1];
static WORD row, col;
static char line[LINEMAX + 1];
static WORD llen;
static WORD mode, item;             /* item: the letter asking, lower case
                                     * for its second question */
static WORD arg_d, arg_e;           /* a drive the first answer named */
static UWORD map;
static char msg[200];
static char names[MAXNAMES][14];    /* a search's files, its folder in dir */
static LONG sizes[MAXNAMES];
static uint8_t attrs[MAXNAMES];
static char dir[PATHMAX];
static WORD n_names, at_name;
static WORD leaving;                /* L or B asked: DUP quits */
static DTA dta;
static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];

/* ---- strings ---------------------------------------------------------- */

static char *str(WORD i)
{
    char *s;

    rsrc_gaddr(R_STRING, i, (void **)&s);
    return s;
}

static WORD udec(char *d, uint32_t v, WORD width)
{
    char t[11];
    WORD k = 0, n = 0;

    do {
        t[k++] = (char)('0' + (WORD)(v % 10));
        v /= 10;
    } while (v && k < 10);
    while (k < width && k < 10)
        t[k++] = '0';
    while (k > 0)
        d[n++] = t[--k];
    d[n] = 0;
    return n;
}

/* Free string i into msg: `#` the number, `@` the name.  Characters go
 * through a WORD and are narrowed once, at the store (B8, tools/ccbug). */
static char *fill(WORD i, uint32_t num, const char *name)
{
    char *s = str(i);
    WORD k = 0, o = 0, v;

    while ((v = (uint8_t)s[k++]) != 0 && o < (WORD)sizeof msg - 12) {
        if (v == '#') {
            o = (WORD)(o + udec(msg + o, num, 1));
        } else if (v == '@' && name) {
            while (*name && o < (WORD)sizeof msg - 2)
                msg[o++] = *name++;
        } else {
            msg[o++] = (char)v;
        }
    }
    msg[o] = 0;
    return msg;
}

/* ---- the window ----------------------------------------------------------- */

static void bar(WORD x, WORD y, WORD w, WORD h, WORD color)
{
    WORD pxy[4];

    vsf_color(vh, color);
    pxy[0] = x;
    pxy[1] = y;
    pxy[2] = (WORD)(x + w - 1);
    pxy[3] = (WORD)(y + h - 1);
    vr_recfl(vh, pxy);
}

/* The work area through the window's rectangle list: white, the rows of
 * text, and the cursor where a key will go. */
static void redraw(WORD x, WORD y, WORD w, WORD h)
{
    WORD rx, ry, rw, rh, r, pxy[4];

    if (wh < 0)
        return;
    graf_mouse(M_OFF, 0);
    wind_update(BEG_UPDATE);
    vswr_mode(vh, MD_TRANS);
    vsf_interior(vh, FIS_SOLID);
    vst_color(vh, 1);
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
            bar(wx, wy, ww, whh, 0);
            for (r = 0; r < rows; r++)
                if (scr[r][0])
                    v_gtext(vh, (WORD)(wx + MARGIN), (WORD)(wy + r * hchar), scr[r]);
            bar((WORD)(wx + MARGIN + col * wchar), (WORD)(wy + row * hchar),
                wchar, hchar, 1);
        }
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    vs_clip(vh, 0, pxy);
    wind_update(END_UPDATE);
    graf_mouse(M_ON, 0);
}

static void redraw_all(void)
{
    redraw(wx, wy, ww, whh);
}

static void work_area(void)
{
    wind_get(wh, WF_WORKXYWH, &wx, &wy, &ww, &whh);
    rows = (WORD)(whh / hchar);
    if (rows > MAXROWS)
        rows = MAXROWS;
    if (rows < 2)
        rows = 2;
}

/* ---- printing ----------------------------------------------------------- */

static void newline(void)
{
    WORD r;

    col = 0;
    if (++row < rows)
        return;
    for (r = 0; r + 1 < rows; r++)
        memcpy(scr[r], scr[r + 1], COLS + 1);
    memset(scr[rows - 1], 0, COLS + 1);
    row = (WORD)(rows - 1);
}

static void put(WORD c)
{
    if (c == '|') {
        newline();
        return;
    }
    if (col >= COLS)
        newline();
    scr[row][col++] = (char)c;
    scr[row][col] = 0;
}

/* `s` printed at the cursor, `|` ending a line, and the window drawn. */
static void out(const char *s)
{
    WORD v;

    while ((v = (uint8_t)*s++) != 0)
        put(v);
    redraw_all();
}

static void say(WORD i)
{
    out(str(i));
}

/* A GEMDOS or BIOS error as DUP's number. */
static void error(LONG r)
{
    WORD n = 255;

    if (r == EFILNF || r == EPTHNF || r == ENMFIL)
        n = 170;                        /* file not found */
    else if (r == EACCDN)
        n = 167;                        /* locked, or no room */
    else if (r == EWRPRO || r == EWRITF || r == EREADF)
        n = 144;                        /* the drive would not */
    else if (r == EDRVNR)
        n = 138;                        /* nothing answered */
    else if (r == EDRIVE || r == EUNDEV || r == DK_ESHAPE)
        n = 160;                        /* no such drive, for that */
    else if (r == EUNCMD)
        n = 139;                        /* the drive refused it */
    else if (r == MKFS_EBAD)
        n = 173;                        /* bad sectors at format time */
    else if (r == ENSMEM)
        n = 158;
    out(fill(R_ERROR, (uint32_t)n, 0));
}

/* ---- names ---------------------------------------------------------------- */

/* A DUP file spec as a GEMDOS path: "D2:NAME.EXT", "D:NAME" or "NAME"
 * (D1:), folders between `>` or `/`.  `out` gets "B:\NAME.EXT"; *d the
 * drive, 1 for D1:.  An empty name is left empty. */
static void gempath(const char *s, char *o, WORD *d)
{
    WORD n = 1, k = 3, v;

    while (*s == ' ')
        s++;
    if ((s[0] == 'D' || s[0] == 'd') && s[1] >= '1' && s[1] <= '8' && s[2] == ':') {
        n = (WORD)(s[1] - '0');
        s += 3;
    } else if ((s[0] == 'D' || s[0] == 'd') && s[1] == ':') {
        s += 2;
    }
    o[0] = (char)('A' + n - 1);
    o[1] = ':';
    o[2] = '\\';
    if (*s == '>' || *s == '/' || *s == '\\')
        s++;
    while ((v = (uint8_t)*s++) != 0 && v != ' ' && k < PATHMAX - 1) {
        if (v == '>' || v == '/')
            v = '\\';
        if (v >= 'a' && v <= 'z')
            v -= 32;
        o[k++] = (char)v;
    }
    o[k] = 0;
    *d = n;
}

/* A GEMDOS path as DUP writes a name: "B:\DOCS\A.TXT" is "D2:DOCS>A.TXT". */
static char shown[PATHMAX];

static char *dupname(const char *p)
{
    WORD k = 3, o = 3, v;

    shown[0] = 'D';
    shown[1] = (char)('1' + p[0] - 'A');
    shown[2] = ':';
    while ((v = (uint8_t)p[k++]) != 0 && o < PATHMAX - 1) {
        if (v == '\\')
            v = '>';
        shown[o++] = (char)v;
    }
    shown[o] = 0;
    return shown;
}

/* The folder part of a path, up to and with its last `\`. */
static WORD dir_len(const char *p)
{
    WORD k, last = 0;

    for (k = 0; p[k]; k++)
        if (p[k] == '\\')
            last = (WORD)(k + 1);
    return last;
}

static WORD wild(const char *p)
{
    for (; *p; p++)
        if (*p == '*' || *p == '?')
            return TRUE;
    return FALSE;
}

/* The answer split at its comma: the part after it into `two`. */
static void split(char *one, char *two)
{
    WORD k = 0, o = 0;

    while (one[k] && one[k] != ',')
        k++;
    if (one[k] == ',') {
        one[k++] = 0;
        while (one[k])
            two[o++] = one[k++];
    }
    two[o] = 0;
}

/* The files matching `spec` (a GEMDOS path), folder into dir, names into
 * names[]: how many. */
static WORD matches(const char *spec, WORD folders)
{
    WORD k = dir_len(spec), n = 0;

    memcpy(dir, spec, (size_t)k);
    dir[k] = 0;
    Fsetdta(&dta);
    if (Fsfirst(spec, (WORD)(FA_RDONLY | (folders ? FA_SUBDIR : 0))) != 0)
        return 0;
    do {
        if (!(dta.d_attrib & FA_SUBDIR) || folders) {
            strcpy(names[n], dta.d_fname);
            sizes[n] = dta.d_length;
            attrs[n] = (uint8_t)dta.d_attrib;
            n++;
        }
    } while (n < MAXNAMES && Fsnext() == 0);
    return n;
}

static void full(char *p, WORD i)
{
    strcpy(p, dir);
    strcat(p, names[i]);
}

/* ---- the items -------------------------------------------------------------- */

static void select_again(void)
{
    say(S_SELECT);
    mode = M_SELECT;
}

/* A: the directory, DUP's way -- `*` for a locked file, the name in
 * columns 1-8, its extension in 9-11, its sectors from 13 (a folder says
 * DIR there), and the free sectors last. */
static void item_a(char *a)
{
    char spec[PATHMAX], t[COLS + 1];
    WORD d, k, n, j, o, folders;
    DISKINFO di;
    UWORD per = 125;
    uint32_t s;
    const char *nm;

    if (!a[0])
        strcpy(a, "D1:*.*");
    gempath(a, spec, &d);
    if (!spec[dir_len(spec)])
        strcat(spec, "*.*");
    folders = (Dcaps(d) & DC_FOLDERS) != 0;
    if (Dfree(&di, d) == 0 && di.b_secsiz > 3) {
        per = (UWORD)di.b_secsiz;
        if (!folders)
            per = (UWORD)(per - 3);     /* a DOS 2 sector's link */
    }
    n = matches(spec, TRUE);
    for (k = 0; k < n; k++) {
        nm = names[k];
        memset(t, ' ', COLS);
        t[COLS] = 0;
        if (attrs[k] & FA_RDONLY)
            t[0] = '*';
        for (j = 0, o = 1; nm[j] && nm[j] != '.' && o < 9; )
            t[o++] = nm[j++];
        while (nm[j] && nm[j] != '.')
            j++;
        if (nm[j] == '.')
            for (j++, o = 9; nm[j] && o < 12; )
                t[o++] = nm[j++];
        if (attrs[k] & FA_SUBDIR) {
            strcpy(t + 12, str(R_DIR));
        } else {
            s = (uint32_t)sizes[k];
            s = (s + per - 1) / per;
            if (!s)
                s = 1;
            udec(t + 13, s, 3);
        }
        out(t);
        out("|");
    }
    if (Dfree(&di, d) == 0)
        out(fill(R_FREE, (uint32_t)di.b_free, 0));
}

/* One file, `from` to `to`, through a far buffer. */
static LONG copy_one(const char *from, const char *to)
{
    LONG in, outh, n, w, r = 0, room, buf;

    room = Malloc(-1L) - 8192L;
    if (room > 32768L)
        room = 32768L;
    if (room < 512L)
        return ENSMEM;
    buf = Malloc(room);
    if (buf <= 0)
        return ENSMEM;
    in = Fopen(from, 0);
    if (in < 0) {
        Mfree((void FAR *)(uint32_t)buf);
        return in;
    }
    outh = Fcreate(to, 0);
    if (outh < 0) {
        Fclose((WORD)in);
        Mfree((void FAR *)(uint32_t)buf);
        return outh;
    }
    for (;;) {
        n = Fread((WORD)in, room, (void FAR *)(uint32_t)buf);
        if (n <= 0) {
            r = n;
            break;
        }
        w = Fwrite((WORD)outh, n, (const void FAR *)(uint32_t)buf);
        if (w != n) {
            r = EACCDN;
            if (w < 0)
                r = w;
            break;
        }
    }
    Fclose((WORD)in);
    if (Fclose((WORD)outh) < 0 && r == 0)
        r = EWRITF;
    Mfree((void FAR *)(uint32_t)buf);
    return r;
}

/* C: from, to -- a file, or a spec of them onto a drive or folder. */
static void item_c(char *a)
{
    char two[LINEMAX + 1], from[PATHMAX], to[PATHMAX], p[PATHMAX], q[PATHMAX];
    WORD d, e, k, n, tl;
    LONG r;

    split(a, two);
    gempath(a, from, &d);
    gempath(two, to, &e);
    n = matches(from, FALSE);
    if (!n) {
        error(EFILNF);
        return;
    }
    tl = dir_len(to);
    for (k = 0; k < n; k++) {
        full(p, k);
        strcpy(q, to);
        if (!to[tl] || wild(to + tl)) {
            q[tl] = 0;
            strcat(q, names[k]);
        }
        if (!strcmp(p, q)) {
            error(EACCDN);
            return;
        }
        out(fill(R_COPYING, 0, dupname(p)));
        r = copy_one(p, q);
        if (r != 0) {
            error(r);
            return;
        }
    }
}

/* D: its files, each asked about unless the spec ends /N. */
static WORD item_d(char *a)
{
    char spec[PATHMAX], p[PATHMAX];
    WORD d, k, quiet = FALSE;
    LONG r;

    for (k = 0; a[k]; k++)
        if (a[k] == '/' && (a[k + 1] == 'N' || a[k + 1] == 'n')) {
            a[k] = 0;
            quiet = TRUE;
            break;
        }
    gempath(a, spec, &d);
    n_names = matches(spec, FALSE);
    if (!n_names) {
        error(EFILNF);
        return FALSE;
    }
    if (quiet) {
        for (k = 0; k < n_names; k++) {
            full(p, k);
            r = Fdelete(p);
            if (r != 0) {
                error(r);
                return FALSE;
            }
        }
        return FALSE;
    }
    at_name = 0;
    full(p, 0);
    out(fill(Q_DCONF, 0, dupname(p)));
    return TRUE;                        /* M_DEL: a Y or an N each */
}

static void item_e(char *a)
{
    char two[LINEMAX + 1], old[PATHMAX], nw[PATHMAX], tmp[PATHMAX];
    WORD d, k;
    LONG r;

    split(a, two);
    gempath(a, old, &d);
    gempath(two, tmp, &d);
    k = dir_len(old);
    memcpy(nw, old, (size_t)k);
    strcpy(nw + k, tmp + 3);            /* the new name, in the old folder */
    r = Frename(old, nw);
    if (r != 0)
        error(r);
}

/* F and G: the read-only bit set or cleared -- which is all gem4xe's
 * Fattrib does, and it refuses a read (docs/differences.md). */
static void item_lock(char *a, WORD on)
{
    char spec[PATHMAX], p[PATHMAX];
    WORD d, k, n, at = 0;
    LONG r;

    gempath(a, spec, &d);
    n = matches(spec, FALSE);
    if (!n) {
        error(EFILNF);
        return;
    }
    if (on)
        at = FA_RDONLY;
    for (k = 0; k < n; k++) {
        full(p, k);
        r = Fattrib(p, 1, at);
        if (r < 0) {
            error(r);
            return;
        }
    }
}

/* A drive number from an answer: "2", "D2", "D2:"; 0 for none. */
static WORD drive_of(const char *a)
{
    WORD v;

    while (*a == ' ' || *a == 'D' || *a == 'd')
        a++;
    v = (uint8_t)*a;
    if (v >= '1' && v <= '8')
        return (WORD)(v - '0');
    return 0;
}

/* Wait for Return (TRUE) or Esc (FALSE), the window kept drawn. */
static WORD wait_return(void)
{
    WORD msgb[8], mx, my, mb, ks, kr, br, ev;

    for (;;) {
        ev = evnt_multi_moblk(MU_MESAG | MU_KEYBD, 1, 1, 1, 0, 0,
                              msgb, 0, 0, &mx, &my, &mb, &ks, &kr, &br);
        if ((ev & MU_MESAG) && msgb[0] == WM_REDRAW && msgb[3] == wh)
            redraw(msgb[4], msgb[5], msgb[6], msgb[7]);
        if (ev & MU_KEYBD) {
            if ((UWORD)kr == KEY_RET)
                return TRUE;
            if ((UWORD)kr == KEY_ESC)
                return FALSE;
        }
    }
}

static void on_stage(WORD what, WORD d)
{
    if (what == DK_FORMAT)
        out(fill(R_WORKING, (uint32_t)d, 0));
}

static WORD on_swap(WORD which, WORD d)
{
    (void)d;
    say(which == DK_SOURCE ? Q_SRC : Q_DST);
    return wait_return();
}

static const DK_HOOKS hooks = { on_stage, 0, on_swap };

/* H, I and P, Y given: G4DOS on the disk, or the disk formatted. */
static void item_disk(WORD which, WORD d)
{
    WORD sdfs = (Dcaps(d) & DC_FOLDERS) != 0, boot;
    uint32_t free;
    LONG r;

    if (which == 'H') {
        if (!sdfs) {
            say(R_NODOS);
            return;
        }
        boot = dk_system(map, d);
        if (!boot) {
            say(R_NOSYS);
            return;
        }
        out(fill(R_WORKING, (uint32_t)d, 0));
        r = dk_bootable(d, boot);
        if (r != 0)
            error(r);
        return;
    }
    r = dk_format(&hooks, d, which == 'P' ? DF_SD : DF_ASIS, !sdfs,
                  str(S_LABEL), 0, &free);
    if (r != 0) {
        error(r);
        return;
    }
    {
        DISKINFO di;

        if (Dfree(&di, d) == 0)
            out(fill(R_FREE, (uint32_t)di.b_free, 0));
    }
}

/* O: one file, read whole, the other disk put in, written. */
static void item_o(char *a)
{
    char p[PATHMAX];
    WORD d;
    LONG h, n, w, buf, room;

    gempath(a, p, &d);
    room = Malloc(-1L) - 8192L;
    if (room < 512L) {
        error(ENSMEM);
        return;
    }
    buf = Malloc(room);
    if (buf <= 0) {
        error(ENSMEM);
        return;
    }
    h = Fopen(p, 0);
    if (h < 0) {
        Mfree((void FAR *)(uint32_t)buf);
        error(h);
        return;
    }
    n = Fread((WORD)h, room, (void FAR *)(uint32_t)buf);
    Fclose((WORD)h);
    if (n < 0 || n == room) {           /* an error, or more than memory */
        Mfree((void FAR *)(uint32_t)buf);
        error(n < 0 ? n : ENSMEM);
        return;
    }
    say(Q_DST);
    if (wait_return()) {
        h = Fcreate(p, 0);
        if (h < 0) {
            error(h);
        } else {
            w = Fwrite((WORD)h, n, (const void FAR *)(uint32_t)buf);
            if (Fclose((WORD)h) < 0 || w != n)
                error(w < 0 ? w : EWRITF);
        }
    }
    Mfree((void FAR *)(uint32_t)buf);
}

/* L and B: the AES asked to run it once DUP has quit, as a desktop icon
 * would (src/aes/shel.c, sh_plain).  The tail is pro_run's: none. */
static void run_after(const char *p)
{
    char cmd[PATHMAX], tail[4];
    WORD i;

    for (i = 0; p[i] && i < PATHMAX - 1; i++)  /* a buffer of this frame */
        cmd[i] = p[i];
    cmd[i] = 0;
    tail[0] = 0;
    tail[1] = 0x0D;
    tail[2] = 0;
    if (shel_write(SHW_EXEC, 0, 0, cmd, tail))
        leaving = TRUE;
    else
        out(fill(R_ERROR, 255, 0));
}

/* L: a binary file -- $FF $FF first, or SpartaDOS X's $FA $FF -- of a
 * kind the AES runs, by its extension. */
static void item_l(char *a)
{
    static const char ext[] = "COMXEXEXEOBJ";
    char p[PATHMAX];
    uint8_t two[2];
    WORD d, i, e = -1, ok;
    LONG h, n;

    gempath(a, p, &d);
    h = Fopen(p, 0);
    if (h < 0) {
        error(h);
        return;
    }
    n = Fread((WORD)h, 2L, (void FAR *)two);
    Fclose((WORD)h);
    if (n != 2 || two[1] != 0xFF || (two[0] != 0xFF && two[0] != 0xFA)) {
        out(fill(R_ERROR, 180, 0));     /* DOS 2's: not a binary file */
        return;
    }
    for (i = 0; p[i]; i++)
        if (p[i] == '.')
            e = i + 1;
        else if (p[i] == '\\')
            e = -1;
    ok = FALSE;
    if (e > 0 && i - e == 3)
        for (i = 0; ext[i]; i += 3)
            if (p[e] == ext[i] && p[e + 1] == ext[i + 1] && p[e + 2] == ext[i + 2])
                ok = TRUE;
    if (!ok) {
        say(R_NOTPLAIN);
        return;
    }
    run_after(p);
}

/* B: the cartridge, or the XL/XE's own BASIC, as the AES found it. */
static void item_b(void)
{
    static const char car[] = SH_CARTRIDGE;
    LONG c = Ssystem(S_GETCOOKIE, G4CT_COOKIE, 0L);

    if (c != G4CT_BASIC && c != G4CT_CART) {
        say(R_NOCART);
        return;
    }
    run_after(car);
}

/* An answer ended by Return. */
static void answered(void)
{
    WORD again = FALSE, d;

    line[llen] = 0;
    newline();
    switch (item) {
    case 'A': item_a(line); break;
    case 'C': item_c(line); break;
    case 'D':
        if (item_d(line)) {
            mode = M_DEL;
            redraw_all();
            return;
        }
        break;
    case 'E': item_e(line); break;
    case 'F': item_lock(line, TRUE); break;
    case 'G': item_lock(line, FALSE); break;
    case 'H':
    case 'I':
    case 'P':
        d = drive_of(line);
        if (!d) {
            error(EDRIVE);
            break;
        }
        arg_d = d;
        out(fill(item == 'H' ? Q_HCONF : Q_ICONF, (uint32_t)d, 0));
        item = item + ('a' - 'A');      /* the second question */
        again = TRUE;
        break;
    case 'h':
    case 'i':
    case 'p':
        if (line[0] == 'Y' || line[0] == 'y')
            item_disk((WORD)(item - ('a' - 'A')), arg_d);
        break;
    case 'J':
        d = drive_of(line);
        {
            char two[LINEMAX + 1];

            split(line, two);
            arg_e = drive_of(two);
        }
        if (!d || !arg_e) {
            error(EDRIVE);
            break;
        }
        arg_d = d;
        say(d == arg_e ? Q_SRC : Q_JBOTH);
        item = 'j';
        again = TRUE;
        break;
    case 'j':
        {
            LONG r = dk_copy(&hooks, arg_d, arg_e);

            if (r != 0 && r != DK_ESTOP)
                error(r);
        }
        break;
    case 'O': item_o(line); break;
    case 'L': item_l(line); break;
    default: break;
    }
    llen = 0;
    if (leaving)
        return;
    if (again) {
        mode = M_LINE;
        redraw_all();
    } else {
        select_again();
    }
}

static const WORD questions[16] = {
    Q_A, 0, Q_C, Q_D, Q_E, Q_F, Q_G, Q_H, Q_I, Q_J, 0, Q_L, 0, 0, Q_O, Q_I
};

/* A key; TRUE to quit. */
static WORD do_key(WORD kr)
{
    WORD c = (WORD)(kr & 0xFF), q;
    char p[PATHMAX];

    if (mode == M_DEL) {
        if (c == 'Y' || c == 'y' || c == 'N' || c == 'n') {
            put(c);
            newline();
            if (c == 'Y' || c == 'y') {
                LONG r;

                full(p, at_name);
                r = Fdelete(p);
                if (r != 0) {
                    error(r);
                    select_again();
                    return FALSE;
                }
            }
            if (++at_name < n_names) {
                full(p, at_name);
                out(fill(Q_DCONF, 0, dupname(p)));
            } else {
                select_again();
            }
        }
        return FALSE;
    }
    if (mode == M_SELECT) {
        if ((UWORD)kr == KEY_RET) {
            newline();
            say(S_MENU);
            say(S_SELECT);
            return FALSE;
        }
        if (c >= 'a' && c <= 'z')
            c -= 32;
        if (c < 'A' || c > 'P')
            return FALSE;
        put(c);
        newline();
        if (c == 'B') {
            item_b();
            if (leaving)
                return TRUE;
            select_again();
            return FALSE;
        }
        q = questions[c - 'A'];
        if (!q) {                       /* K, M, N */
            say(R_NOTGEM);
            select_again();
            return FALSE;
        }
        item = c;
        llen = 0;
        say(q);
        mode = M_LINE;
        return FALSE;
    }
    /* M_LINE: an answer */
    if ((UWORD)kr == KEY_RET) {
        answered();
        if (leaving)
            return TRUE;
    } else if ((UWORD)kr == KEY_BS) {
        if (llen > 0 && col > 0) {
            llen--;
            scr[row][--col] = 0;
            redraw_all();
        }
    } else if ((UWORD)kr == KEY_ESC) {
        newline();
        select_again();
    } else if (c >= ' ' && c < 127 && llen < LINEMAX) {
        if (c >= 'a' && c <= 'z')
            c -= 32;
        line[llen++] = (char)c;
        put(c);
        redraw_all();
    }
    return FALSE;
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

int main(void)
{
    WORD msgb[8], mx, my, mb, ks, kr, br, ev, done = FALSE;
    WORD dx, dy, dw, dh, x, y, w, h, wbox, hbox;

    appl_init();
    if (!rsrc_load("DUP.RSC")) {
        appl_exit();
        return 1;
    }
    vh = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &vh, work_out);
    vst_alignment(vh, 0, 5, &x, &y);    /* text hangs from its top */
    rsrc_gaddr(R_TREE, ADMENU, (void **)&menu);
    menu_bar(menu, 1);
    map = (UWORD)Dsetdrv(Dgetdrv());

    /* 40 columns, and as many rows as the desk holds */
    wind_get(0, WF_WORKXYWH, &dx, &dy, &dw, &dh);
    wind_calc(WC_BORDER, NAME | CLOSER | MOVER, dx, dy,
              (WORD)(COLS * wchar + 2 * MARGIN), dh, &x, &y, &w, &h);
    if (w > dw)
        w = dw;
    h = dh;
    wh = wind_create(NAME | CLOSER | MOVER, dx, dy, dw, dh);
    if (wh >= 0) {
        wind_set_str(wh, WF_NAME, str(S_TITLE));
        wind_open(wh, (WORD)(dx + (dw - w) / 2), dy, w, h);
        work_area();
        say(S_BANNER);
        say(S_MENU);
        say(S_SELECT);
    } else {
        done = TRUE;
    }
    while (!done) {
        ev = evnt_multi_moblk(MU_MESAG | MU_KEYBD, 1, 1, 1, 0, 0,
                              msgb, 0, 0, &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_MESAG) {
            switch (msgb[0]) {
            case MN_SELECTED:
                if (msgb[4] == ABOUITEM)
                    about();
                else if (msgb[4] == QUITITEM)
                    done = TRUE;
                menu_tnormal(menu, msgb[3], 1);
                break;
            case WM_REDRAW:
                if (msgb[3] == wh)
                    redraw(msgb[4], msgb[5], msgb[6], msgb[7]);
                break;
            case WM_TOPPED:
                if (msgb[3] == wh)
                    wind_set(wh, WF_TOP, 0, 0, 0, 0);
                break;
            case WM_MOVED:
                if (msgb[3] == wh) {
                    wind_set(wh, WF_CURRXYWH, msgb[4], msgb[5], msgb[6], msgb[7]);
                    work_area();
                }
                break;
            case WM_CLOSED:
            case AP_TERM:
                done = TRUE;
                break;
            default:
                break;
            }
        }
        if ((ev & MU_KEYBD) && !done) {
            if ((kr & 0xFF) == 'Q' - '@')    /* ^Q, its control code low */
                done = TRUE;
            else
                done = do_key(kr);
        }
    }
    if (wh >= 0) {
        wind_close(wh);
        wind_delete(wh);
    }
    menu_bar(menu, 0);
    v_clsvwk(vh);
    rsrc_free();
    appl_exit();
    return 0;
}
