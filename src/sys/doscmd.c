/* doscmd.c -- the DOS's commands (doscmd.h says what and why;
 * docs/g4dos-plan.md, step 4).
 *
 * A LINE is words between spaces.  The first is a command -- looked up in
 * dc_names without regard to case -- or a drive, "D2:", which is `cd D2:`,
 * or else a program, which is looked for as the shell would find it: the
 * path as typed, with .COM, .XEX or .EXE after it if it has no extension
 * of its own, and for a bare name the root and then every folder in the
 * root, which is how G4DOS finds a bare name.  The platform runs it.
 *
 * A PATH becomes a unit and the engine's path from that unit's root
 * (resolve): "Dn:" or "D:" first, then parts between any of '/', '>' and
 * '\'.  Without a separator first it starts from the unit's own folder;
 * "." stays and ".." goes up.  Names are put in capitals, as SpartaDOS
 * keeps them, so two paths are the same file when their strings are.
 *
 * WILDCARDS, '*' and '?', in a path's last part, are each()'s: the folder
 * listed and the command run for every name that matches.  "*.*" matches
 * every name, with a dot or without, as a DOS user means it.
 *
 * THE MESSAGES are Linux's shape, "rm: NAME: locked", in the strings
 * below and nowhere else.  The engine has one error, SD_EACCDN, for
 * locked, exists, not empty and full; each command says the one it means,
 * looking first where looking can tell.
 *
 * FOR THE ATARI, as sdfs.c is written: every pointer into the state FAR,
 * byte work in words (tools/ccbug B8, B23), index loops rather than *p++
 * through a far pointer (B18), and every string a FAR array -- a literal
 * would be bank $00's, which gem4xe has none of to spare.
 */
#include "doscmd.h"

#define C_LS      1
#define C_DIR     2
#define C_CD      3
#define C_PWD     4
#define C_CP      5
#define C_MV      6
#define C_RM      7
#define C_MKDIR   8
#define C_RMDIR   9
#define C_CAT     10
#define C_MORE    11
#define C_DF      12
#define C_HELP    13
#define C_REBOOT  14

#define DC_LSW    14            /* ls: a name's column */

/* The commands, and the old names, each a word ended by a zero. */
static const char FAR dc_names[] =
    "LS\0" "DIR\0" "CD\0" "CWD\0" "PWD\0" "CP\0" "COPY\0" "MV\0" "MOVE\0"
    "REN\0" "RENAME\0" "RM\0" "DEL\0" "ERASE\0" "MKDIR\0" "MD\0" "RMDIR\0"
    "RD\0" "CAT\0" "TYPE\0" "MORE\0" "DF\0" "CHKDSK\0" "HELP\0" "REBOOT\0"
    "COLD\0";
static const uint8_t FAR dc_codes[] = {
    C_LS, C_DIR, C_CD, C_CD, C_PWD, C_CP, C_CP, C_MV, C_MV,
    C_MV, C_MV, C_RM, C_RM, C_RM, C_MKDIR, C_MKDIR, C_RMDIR,
    C_RMDIR, C_CAT, C_CAT, C_MORE, C_DF, C_DF, C_HELP, C_REBOOT,
    C_REBOOT
};

/* A program's extensions, tried in order, each three letters. */
static const char FAR dc_exts[] = "COM\0" "XEX\0" "EXE\0";

static const char FAR m_nofile[]   = "no such file";
static const char FAR m_nodir[]    = "no such folder";
static const char FAR m_denied[]   = "access denied";
static const char FAR m_wrpro[]    = "write-protected";
static const char FAR m_nodrive[]  = "no disk it can read";
static const char FAR m_toomany[]  = "too many files open";
static const char FAR m_error[]    = "disk error";
static const char FAR m_locked[]   = "locked";
static const char FAR m_exists[]   = "exists";
static const char FAR m_notempty[] = "not empty";
static const char FAR m_full[]     = "disk full";
static const char FAR m_isdir[]    = "is a folder";
static const char FAR m_notdir[]   = "not a folder";
static const char FAR m_same[]     = "same file";
static const char FAR m_across[]   = "a folder stays on its drive";
static const char FAR m_into[]     = "not into itself";
static const char FAR m_notfound[] = "command not found";
static const char FAR m_operand[]  = "missing operand";
static const char FAR m_more[]     = "-- more --";
static const char FAR m_delline[]  = { 0x9C };      /* ATASCII: delete line */
static const char FAR m_prompt[]   = "$ ";
static const char FAR m_none[]     = "";
static const char FAR m_root[]     = "/";
static const char FAR m_dfhead[]   = "Drive Sectors   Free  Bytes free\n";
static const char FAR m_help[] =
    "ls [-l] [PATH]   list\n"
    "cd [PATH]        change folder\n"
    "pwd              where you are\n"
    "cp FROM... TO    copy\n"
    "mv FROM... TO    move, rename\n"
    "rm FILE...       delete\n"
    "mkdir, rmdir     make, remove folders\n"
    "cat, more FILE   show a file\n"
    "df [Dn:]         free space\n"
    "Dn:              change drive\n"
    "reboot           start again\n"
    "DIR COPY REN DEL TYPE work too.\n"
    "Paths: D1:/GEM/NAME.EXT, and * and ?\n"
    "match.  A program runs by its name.\n";

typedef int16_t (*DC_FN)(DC_STATE FAR *h, int16_t u, char FAR *path);

#define ARG(h, i)  (&(h)->line[(h)->argv[i]])

/* ---- small things ----------------------------------------------------- */

static int16_t up(int16_t c)
{
    return (c >= 'a' && c <= 'z') ? (int16_t)(c - 0x20) : c;
}

static int16_t is_sep(int16_t c)
{
    return c == '/' || c == '\\' || c == '>';
}

static uint16_t f_len(const char FAR *s)
{
    uint16_t n = 0;

    while (s[n])
        n++;
    return n;
}

static void f_cpy(char FAR *d, const char FAR *s)
{
    uint16_t i = 0;

    while (s[i]) {
        d[i] = s[i];
        i++;
    }
    d[i] = 0;
}

static uint16_t f_same(const char FAR *a, const char FAR *b)
{
    uint16_t i = 0;

    while (a[i] && a[i] == b[i])
        i++;
    return a[i] == b[i];
}

static uint16_t is_dir(const SD_INFO FAR *in)
{
    uint16_t st = in->status;

    return (st & SD_SUBDIR) != 0;
}

/* `p` is inside the folder `dir`: dir's path, then a '\'. */
static uint16_t within(const char FAR *p, const char FAR *dir)
{
    uint16_t i = 0;

    while (dir[i] && p[i] == dir[i])
        i++;
    return !dir[i] && p[i] == '\\';
}

/* Where a path's last part starts: after its last '\'. */
static uint16_t last_part(const char FAR *p)
{
    uint16_t i, at = 0;

    for (i = 0; p[i]; i++)
        if (p[i] == '\\')
            at = i + 1;
    return at;
}

static uint16_t has_wild(const char FAR *s)
{
    uint16_t i;

    for (i = 0; s[i]; i++)
        if (s[i] == '*' || s[i] == '?')
            return 1;
    return 0;
}

static uint16_t has_dot(const char FAR *s)
{
    uint16_t i;

    for (i = 0; s[i]; i++)
        if (s[i] == '.')
            return 1;
    return 0;
}

/* `name` against the pattern `p`, both in capitals: '?' one character,
 * '*' any run of them -- and "*.*" everything. */
static uint16_t match(const char FAR *p, const char FAR *name)
{
    uint16_t pi = 0, si = 0, star = 0xFFFF, mark = 0;

    if (p[0] == '*' && p[1] == '.' && p[2] == '*' && !p[3])
        return 1;
    while (name[si]) {
        if (p[pi] == '?' || (p[pi] && p[pi] != '*' && p[pi] == name[si])) {
            pi++;
            si++;
        } else if (p[pi] == '*') {
            star = pi++;
            mark = si;
        } else if (star != 0xFFFF) {
            pi = star + 1;
            si = ++mark;
        } else
            return 0;
    }
    while (p[pi] == '*')
        pi++;
    return !p[pi];
}

/* ---- output ----------------------------------------------------------- */

void dc_flush(DC_STATE FAR *h)
{
    uint16_t n = h->on;

    if (n) {
        h->on = 0;
        dc_out(h, h->out, n);
    }
}

/* more's pause: the prompt, a key, the prompt taken away again. */
static void o_wait(DC_STATE FAR *h)
{
    int16_t k;

    dc_flush(h);
    dc_out(h, m_more, f_len(m_more));
    k = dc_key(h);
    dc_out(h, m_delline, 1);
    h->row = 0;
    h->col = 0;
    if (k == 'q' || k == 'Q' || k == 0x1B)
        h->quit = 1;
}

/* A line has gone up the screen: more waits when a screenful has. */
static void o_row(DC_STATE FAR *h)
{
    uint16_t r;

    if (!h->paging || !h->rows)
        return;
    r = (uint16_t)(h->row + 1);
    h->row = (uint8_t)r;
    if (r + 1 >= h->rows)
        o_wait(h);
}

static void o_c(DC_STATE FAR *h, int16_t c)
{
    uint16_t n;

    if (h->quit)
        return;
    n = h->on;
    h->out[n] = (char)c;
    h->on = (uint8_t)(n + 1);
    if (c == DC_EOL) {
        h->col = 0;
        dc_flush(h);
        o_row(h);
        return;
    }
    n = (uint16_t)(h->col + 1);
    if (n >= h->cols) {                 /* the screen carries it on below */
        h->col = 0;
        dc_flush(h);
        o_row(h);
        return;
    }
    h->col = (uint8_t)n;
    if (h->on >= DC_OUT)
        dc_flush(h);
}

static void o_s(DC_STATE FAR *h, const char FAR *s)
{
    uint16_t i;
    int16_t c;

    for (i = 0; s[i]; i++) {
        c = (uint8_t)s[i];
        o_c(h, c == '\n' ? DC_EOL : c);
    }
}

static void o_num(DC_STATE FAR *h, uint32_t v, uint16_t width)
{
    char d[10];
    uint16_t n = 0;

    do {
        d[n] = (char)('0' + (uint16_t)(v % 10));
        n++;
        v /= 10;
    } while (v && n < 10);
    while (width > n) {
        o_c(h, ' ');
        width--;
    }
    while (n) {
        n--;
        o_c(h, (uint8_t)d[n]);
    }
}

static void o_two(DC_STATE FAR *h, uint16_t v)
{
    o_c(h, '0' + (v / 10) % 10);
    o_c(h, '0' + v % 10);
}

/* A path of the engine's as the user sees it: D1:/GEM/NAME. */
static void o_where(DC_STATE FAR *h, uint16_t u, const char FAR *p)
{
    uint16_t i;
    int16_t c;

    o_c(h, 'D');
    o_c(h, '0' + u);
    o_c(h, ':');
    if (!p[0])
        o_c(h, '/');
    for (i = 0; p[i]; i++) {
        c = (uint8_t)p[i];
        o_c(h, c == '\\' ? '/' : c);
    }
}

void dc_say(DC_STATE FAR *h, const char FAR *what, const char FAR *msg)
{
    if (h->argc)
        o_s(h, ARG(h, 0));
    o_c(h, ':');
    o_c(h, ' ');
    if (what && what[0]) {
        o_s(h, what);
        o_c(h, ':');
        o_c(h, ' ');
    }
    o_s(h, msg);
    o_c(h, DC_EOL);
}

/* A message, and the command's error. */
static int16_t refuse(DC_STATE FAR *h, const char FAR *what,
                      const char FAR *msg, int16_t e)
{
    dc_say(h, what, msg);
    h->err = e;
    return e;
}

/* The engine's error `e`, said; `acc` is what SD_EACCDN means here. */
static int16_t fail(DC_STATE FAR *h, const char FAR *what, int16_t e,
                    const char FAR *acc)
{
    const char FAR *m;

    switch (e) {
    case SD_EFILNF: m = m_nofile;   break;
    case SD_EPTHNF: m = m_nodir;    break;
    case SD_EACCDN: m = acc ? acc : m_denied;  break;
    case SD_EWRPRO: m = m_wrpro;    break;
    case SD_EDRIVE: m = m_nodrive;  break;
    case SD_ENHNDL: m = m_toomany;  break;
    default:        m = m_error;    break;
    }
    return refuse(h, what, m, e);
}

/* ---- the line and its paths ---------------------------------------------- */

static void split(DC_STATE FAR *h)
{
    uint16_t i = 0, n = 0;

    for (;;) {
        while (h->line[i] == ' ')
            i++;
        if (!h->line[i])
            break;
        if (n < DC_ARGS) {
            h->argv[n] = i;
            n++;
        }
        while (h->line[i] && h->line[i] != ' ')
            i++;
        if (h->line[i]) {
            h->line[i] = 0;
            i++;
        }
    }
    h->argc = (uint8_t)n;
}

static uint16_t lookup(const char FAR *w)
{
    uint16_t i = 0, k, n = 0;

    while (dc_names[i]) {
        for (k = 0; dc_names[i + k] && up((uint8_t)w[k]) == dc_names[i + k]; k++)
            ;
        if (!dc_names[i + k] && !w[k])
            return dc_codes[n];
        while (dc_names[i])
            i++;
        i++;
        n++;
    }
    return 0;
}

/* "D2:" or "D:", by itself: a drive. */
static uint16_t is_drive(const char FAR *w)
{
    if (up((uint8_t)w[0]) != 'D')
        return 0;
    if (w[1] == ':')
        return !w[2];
    return w[1] >= '1' && w[1] <= '8' && w[2] == ':' && !w[3];
}

/* `arg` as a unit -- returned, or a negative error -- and its path from
 * that unit's root into `out`. */
static int16_t resolve(DC_STATE FAR *h, const char FAR *arg, char FAR *out)
{
    uint16_t i = 0, k = 0, n, j;
    int16_t u = h->drive;

    if (up((uint8_t)arg[0]) == 'D') {
        if (arg[1] == ':')
            i = 2;
        else if (arg[1] >= '1' && arg[1] <= '8' && arg[2] == ':') {
            u = arg[1] - '0';
            i = 3;
        }
    }
    if (!is_sep((uint8_t)arg[i])) {
        f_cpy(out, h->cwd[u - 1]);
        k = f_len(out);
    }
    out[k] = 0;
    for (;;) {
        while (is_sep((uint8_t)arg[i]))
            i++;
        if (!arg[i])
            break;
        for (n = 0; arg[i + n] && !is_sep((uint8_t)arg[i + n]); n++)
            ;
        if (n == 1 && arg[i] == '.')
            ;
        else if (n == 2 && arg[i] == '.' && arg[i + 1] == '.') {
            while (k && out[k - 1] != '\\')
                k--;
            if (k)
                k--;
            out[k] = 0;
        } else {
            if (k + 1 + n >= DC_PATH)
                return SD_EPTHNF;
            out[k] = '\\';
            k++;
            for (j = 0; j < n; j++) {
                out[k] = (char)up((uint8_t)arg[i + j]);
                k++;
            }
            out[k] = 0;
        }
        i += n;
    }
    return u;
}

/* The command `fn` for `arg`: for the one thing it names, looked up into
 * h->info first, or with a wildcard for every name in its folder that
 * matches -- folders too when `dirs` says so.  h->a is the path fn gets. */
static int16_t each(DC_STATE FAR *h, const char FAR *arg, DC_FN fn,
                    uint16_t dirs)
{
    int16_t u, d, e, r = 0;
    uint16_t at, k, n, any = 0;

    u = resolve(h, arg, h->a);
    if (u < 0)
        return fail(h, arg, u, 0);
    at = last_part(h->a);
    if (!has_wild(h->a + at)) {
        e = sd_stat(h->fs, (uint8_t)u, h->a, &h->info);
        if (e < 0)
            return fail(h, arg, e, 0);
        return fn(h, u, h->a);
    }
    for (k = 0; h->a[at + k] && k < 13; k++)
        h->pat[k] = h->a[at + k];
    h->pat[k] = 0;
    n = at ? at - 1 : 0;                /* the folder, without its '\' */
    for (k = 0; k < n; k++)
        h->c[k] = h->a[k];
    h->c[n] = 0;
    d = sd_opendir(h->fs, (uint8_t)u, h->c);
    if (d < 0)
        return fail(h, arg, d, 0);
    while (!h->quit && sd_readdir(h->fs, d, &h->info) >= 0) {
        if (!dirs && is_dir(&h->info))
            continue;
        if (!match(h->pat, h->info.name))
            continue;
        f_cpy(h->a, h->c);
        k = f_len(h->a);
        h->a[k] = '\\';
        f_cpy(h->a + k + 1, h->info.name);
        any = 1;
        e = fn(h, u, h->a);
        if (e < 0)
            r = e;
    }
    sd_closedir(h->fs, d);
    if (!any && !r)
        return fail(h, arg, SD_EFILNF, 0);
    return r;
}

/* ---- ls ----------------------------------------------------------------- */

/* h->info, as a column of names or, long, a line of its own:
 *     NAME.EXT       1234 2026-11-02 14:05      (folders NAME/) */
static void ls_entry(DC_STATE FAR *h)
{
    uint16_t n = f_len(h->info.name), w, y;

    if (h->lng) {
        o_s(h, h->info.name);
        if (is_dir(&h->info)) {
            o_c(h, '/');
            n++;
        }
        while (n < 13) {
            o_c(h, ' ');
            n++;
        }
        o_num(h, h->info.size, 7);
        o_c(h, ' ');
        y = h->info.stamp[2];
        o_num(h, y < 80 ? 2000 + y : 1900 + y, 4);
        o_c(h, '-');
        o_two(h, h->info.stamp[1]);
        o_c(h, '-');
        o_two(h, h->info.stamp[0]);
        o_c(h, ' ');
        o_two(h, h->info.stamp[3]);
        o_c(h, ':');
        o_two(h, h->info.stamp[4]);
        o_c(h, DC_EOL);
        return;
    }
    w = h->cols / DC_LSW;
    if (!w)
        w = 1;
    if (h->lscol >= w) {
        o_c(h, DC_EOL);
        h->lscol = 0;
    } else
        for (y = h->lsgap; h->lscol && y; y--)
            o_c(h, ' ');
    o_s(h, h->info.name);
    if (is_dir(&h->info)) {
        o_c(h, '/');
        n++;
    }
    h->lsgap = (uint8_t)(n < DC_LSW ? DC_LSW - n : 1);
    h->lscol = (uint8_t)(h->lscol + 1);
}

static int16_t ls_one(DC_STATE FAR *h, int16_t u, char FAR *path)
{
    int16_t d;

    if (h->wild || !is_dir(&h->info)) {
        ls_entry(h);
        return 0;
    }
    d = sd_opendir(h->fs, (uint8_t)u, path);
    if (d < 0)
        return fail(h, path, d, 0);
    while (!h->quit && sd_readdir(h->fs, d, &h->info) >= 0)
        ls_entry(h);
    sd_closedir(h->fs, d);
    return 0;
}

static void c_ls(DC_STATE FAR *h, uint16_t lng)
{
    uint16_t i, k, any = 0;
    const char FAR *a;

    for (i = 1; i < h->argc; i++) {
        a = ARG(h, i);
        if (a[0] == '-')
            for (k = 1; a[k]; k++)
                if (up((uint8_t)a[k]) == 'L')
                    lng = 1;
    }
    h->lng = (uint8_t)lng;
    h->lscol = 0;
    for (i = 1; i < h->argc; i++) {
        a = ARG(h, i);
        if (a[0] == '-')
            continue;
        any = 1;
        h->wild = (uint8_t)has_wild(a);
        each(h, a, ls_one, 1);
    }
    if (!any) {
        h->wild = 0;
        each(h, m_none, ls_one, 1);
    }
    if (h->lscol)
        o_c(h, DC_EOL);
}

/* ---- cd, pwd, df -------------------------------------------------------- */

static void c_cd(DC_STATE FAR *h, const char FAR *arg)
{
    int16_t u, e;

    u = resolve(h, arg, h->a);
    if (u < 0) {
        fail(h, arg, u, 0);
        return;
    }
    e = sd_stat(h->fs, (uint8_t)u, h->a, &h->info2);
    if (e < 0) {
        fail(h, arg, e == SD_EFILNF ? SD_EPTHNF : e, 0);
        return;
    }
    if (!is_dir(&h->info2)) {
        refuse(h, arg, m_notdir, SD_EPTHNF);
        return;
    }
    f_cpy(h->cwd[u - 1], h->a);
    h->drive = (uint8_t)u;
}

static void df_one(DC_STATE FAR *h, const char FAR *arg)
{
    uint16_t fr, tot;
    int16_t u, e;

    u = resolve(h, arg, h->a);
    if (u < 0) {
        fail(h, arg, u, 0);
        return;
    }
    e = sd_space(h->fs, (uint8_t)u, &fr, &tot);
    if (e < 0) {
        fail(h, arg, e, 0);
        return;
    }
    o_c(h, 'D');
    o_c(h, '0' + u);
    o_c(h, ':');
    o_num(h, tot, 10);
    o_num(h, fr, 7);
    o_num(h, (uint32_t)fr << h->fs->units[u - 1].shift, 12);
    o_c(h, DC_EOL);
}

static void c_df(DC_STATE FAR *h)
{
    uint16_t i;

    o_s(h, m_dfhead);
    if (h->argc < 2)
        df_one(h, m_none);
    for (i = 1; i < h->argc; i++)
        df_one(h, ARG(h, i));
}

/* ---- rm, mkdir, rmdir --------------------------------------------------- */

static int16_t rm_one(DC_STATE FAR *h, int16_t u, char FAR *path)
{
    const char FAR *name = path + last_part(path);
    int16_t e;

    if (is_dir(&h->info))
        return refuse(h, name, m_isdir, SD_EACCDN);
    e = sd_delete(h->fs, (uint8_t)u, path);
    return e < 0 ? fail(h, name, e, m_locked) : 0;
}

static void c_mkdir(DC_STATE FAR *h)
{
    uint16_t i;
    int16_t u, e;
    const char FAR *a;

    for (i = 1; i < h->argc; i++) {
        a = ARG(h, i);
        u = resolve(h, a, h->a);
        if (u < 0) {
            fail(h, a, u, 0);
            continue;
        }
        if (sd_stat(h->fs, (uint8_t)u, h->a, &h->info2) == 0) {
            refuse(h, a, m_exists, SD_EACCDN);
            continue;
        }
        e = sd_mkdir(h->fs, (uint8_t)u, h->a);
        if (e < 0)
            fail(h, a, e, m_full);
    }
}

static void c_rmdir(DC_STATE FAR *h)
{
    uint16_t i;
    int16_t u, e;
    const char FAR *a;

    for (i = 1; i < h->argc; i++) {
        a = ARG(h, i);
        u = resolve(h, a, h->a);
        if (u < 0) {
            fail(h, a, u, 0);
            continue;
        }
        e = sd_stat(h->fs, (uint8_t)u, h->a, &h->info2);
        if (e == 0 && !is_dir(&h->info2)) {
            refuse(h, a, m_notdir, SD_EPTHNF);
            continue;
        }
        if (e == 0)
            e = sd_rmdir(h->fs, (uint8_t)u, h->a);
        if (e < 0)
            fail(h, a, e, (h->info2.status & SD_LOCKED) ? m_locked : m_notempty);
    }
}

/* ---- cp, mv ------------------------------------------------------------- */

/* The last word, where to: h->d, on unit h->du, a folder (h->dfold) if it
 * is one -- and it must be one when `many` things are going there, or
 * when it ends in a separator. */
static int16_t dest(DC_STATE FAR *h, uint16_t many)
{
    const char FAR *arg = ARG(h, h->argc - 1);
    uint16_t n = f_len(arg), trail;
    int16_t u, e;

    u = resolve(h, arg, h->d);
    if (u < 0)
        return fail(h, arg, u, 0);
    h->du = (uint8_t)u;
    trail = (uint16_t)((n && is_sep((uint8_t)arg[n - 1])) || is_drive(arg));
    e = sd_stat(h->fs, (uint8_t)u, h->d, &h->info2);
    if (e == 0 && is_dir(&h->info2)) {
        h->dfold = 1;
        return 0;
    }
    if (e < 0 && e != SD_EFILNF)
        return fail(h, arg, e, 0);
    if (trail)
        return fail(h, arg, SD_EPTHNF, 0);
    if (many)
        return refuse(h, arg, m_notdir, SD_EPTHNF);
    h->dfold = 0;
    return 0;
}

/* Where `src` goes: h->b. */
static int16_t dest_for(DC_STATE FAR *h, const char FAR *src)
{
    uint16_t k, at;

    f_cpy(h->b, h->d);
    if (!h->dfold)
        return 0;
    at = last_part(src);
    k = f_len(h->b);
    if (k + 1 + f_len(src + at) >= DC_PATH)
        return SD_EPTHNF;
    h->b[k] = '\\';
    f_cpy(h->b + k + 1, src + at);
    return 0;
}

static int16_t cp_one(DC_STATE FAR *h, int16_t u, char FAR *src)
{
    const char FAR *name = src + last_part(src);
    int16_t in, out, e;
    int32_t n, w;

    if (is_dir(&h->info))
        return refuse(h, name, m_isdir, SD_EACCDN);
    e = dest_for(h, src);
    if (e < 0)
        return fail(h, name, e, 0);
    if (h->du == u && f_same(h->b, src))
        return refuse(h, name, m_same, SD_EACCDN);
    in = sd_open(h->fs, (uint8_t)u, src, SD_READ);
    if (in < 0)
        return fail(h, name, in, 0);
    out = sd_open(h->fs, h->du, h->b, SD_CREATE);
    if (out < 0) {
        sd_close(h->fs, in);
        return fail(h, name, out, 0);
    }
    for (;;) {
        n = sd_read(h->fs, in, h->buf, DC_BUF);
        if (n <= 0)
            break;
        w = sd_write(h->fs, out, h->buf, (uint32_t)n);
        if (w != n) {
            n = w < 0 ? w : SD_EACCDN;
            break;
        }
    }
    sd_close(h->fs, in);
    if (h->keep)                        /* mv: the file's own time goes too */
        sd_fstamp(h->fs, out, h->info.stamp, 1);
    e = sd_close(h->fs, out);
    if (n < 0)
        return fail(h, name, (int16_t)n, m_full);
    if (e < 0)
        return fail(h, name, e, m_full);
    return 0;
}

static int16_t mv_one(DC_STATE FAR *h, int16_t u, char FAR *src)
{
    const char FAR *name = src + last_part(src);
    int16_t e;

    if (h->du != u) {
        if (is_dir(&h->info))
            return refuse(h, name, m_across, SD_ENSAME);
        h->keep = 1;
        e = cp_one(h, u, src);
        h->keep = 0;
        if (e < 0)
            return e;
        e = sd_delete(h->fs, (uint8_t)u, src);
        return e < 0 ? fail(h, name, e, m_locked) : 0;
    }
    e = dest_for(h, src);
    if (e < 0)
        return fail(h, name, e, 0);
    if (f_same(h->b, src))
        return 0;
    if (sd_stat(h->fs, (uint8_t)u, h->b, &h->info2) == 0)
        return refuse(h, name, m_exists, SD_EACCDN);
    if (is_dir(&h->info) && within(h->b, src))
        return refuse(h, name, m_into, SD_EACCDN);
    e = sd_rename(h->fs, (uint8_t)u, src, h->b);
    return e < 0 ? fail(h, name, e, 0) : 0;
}

static void c_cpmv(DC_STATE FAR *h, DC_FN fn)
{
    uint16_t i, many;

    if (h->argc < 3) {
        refuse(h, 0, m_operand, SD_EFILNF);
        return;
    }
    many = h->argc > 3;
    for (i = 1; i + 1 < h->argc; i++)
        if (has_wild(ARG(h, i)))
            many = 1;
    if (dest(h, many) < 0)
        return;
    for (i = 1; i + 1 < h->argc && !h->quit; i++)
        each(h, ARG(h, i), fn, 0);
}

/* ---- cat, more ---------------------------------------------------------- */

/* A file's bytes to the screen, its line ends -- CR LF, LF or CR, the
 * ST's and Linux's -- made the Atari's, and a tab a space. */
static int16_t cat_one(DC_STATE FAR *h, int16_t u, char FAR *path)
{
    const char FAR *name = path + last_part(path);
    int16_t f, c;
    int32_t n = 0;
    uint16_t i;

    if (is_dir(&h->info))
        return refuse(h, name, m_isdir, SD_EACCDN);
    f = sd_open(h->fs, (uint8_t)u, path, SD_READ);
    if (f < 0)
        return fail(h, name, f, 0);
    h->cr = 0;
    while (!h->quit && (n = sd_read(h->fs, f, h->buf, DC_BUF)) > 0)
        for (i = 0; i < (uint16_t)n && !h->quit; i++) {
            c = h->buf[i];
            if (c == 0x0D) {
                o_c(h, DC_EOL);
                h->cr = 1;
                continue;
            }
            if (c == 0x0A) {
                if (!h->cr)
                    o_c(h, DC_EOL);
                h->cr = 0;
                continue;
            }
            h->cr = 0;
            o_c(h, c == 0x09 ? ' ' : c);
        }
    sd_close(h->fs, f);
    if (h->col)
        o_c(h, DC_EOL);
    return n < 0 ? fail(h, name, (int16_t)n, 0) : 0;
}

static void c_cat(DC_STATE FAR *h, uint16_t page)
{
    uint16_t i;

    if (h->argc < 2) {
        refuse(h, 0, m_operand, SD_EFILNF);
        return;
    }
    h->paging = (uint8_t)page;
    h->row = 0;
    for (i = 1; i < h->argc && !h->quit; i++)
        each(h, ARG(h, i), cat_one, 0);
    h->paging = 0;
}

static void c_each(DC_STATE FAR *h, DC_FN fn)
{
    uint16_t i;

    if (h->argc < 2) {
        refuse(h, 0, m_operand, SD_EFILNF);
        return;
    }
    for (i = 1; i < h->argc; i++)
        each(h, ARG(h, i), fn, 0);
}

/* ---- programs ----------------------------------------------------------- */

/* h->a a file, looked up into h->info2. */
static uint16_t a_file(DC_STATE FAR *h, int16_t u)
{
    return sd_stat(h->fs, (uint8_t)u, h->a, &h->info2) == 0
           && !is_dir(&h->info2);
}

/* h->a as a program: itself if its last part (from `at`) has a dot, or
 * else with each extension after it.  1, and h->a the one found. */
static uint16_t find_prog(DC_STATE FAR *h, int16_t u, uint16_t at)
{
    uint16_t k = f_len(h->a), i, j;

    if (has_dot(h->a + at))
        return a_file(h, u);
    if (k + 4 >= DC_PATH)
        return 0;
    for (i = 0; dc_exts[i]; i += 4) {
        h->a[k] = '.';
        for (j = 0; j < 3; j++)
            h->a[k + 1 + j] = dc_exts[i + j];
        h->a[k + 4] = 0;
        if (a_file(h, u))
            return 1;
    }
    h->a[k] = 0;
    return 0;
}

static void c_run(DC_STATE FAR *h)
{
    const char FAR *arg = ARG(h, 0);
    int16_t u, d;
    uint16_t at, k, bare = 1;

    for (k = 0; arg[k]; k++)
        if (is_sep((uint8_t)arg[k]) || arg[k] == ':')
            bare = 0;
    u = resolve(h, arg, h->a);
    if (u < 0) {
        fail(h, arg, u, 0);
        return;
    }
    at = last_part(h->a);
    if (find_prog(h, u, at)) {
        dc_flush(h);
        dc_exec(h, (uint8_t)u, h->a);
        return;
    }
    if (bare) {                         /* the root, then its folders */
        for (k = 0; arg[k] && k < 12; k++)
            h->pat[k] = (char)up((uint8_t)arg[k]);
        h->pat[k] = 0;
        h->a[0] = '\\';
        f_cpy(h->a + 1, h->pat);
        if (find_prog(h, u, 1)) {
            dc_flush(h);
            dc_exec(h, (uint8_t)u, h->a);
            return;
        }
        d = sd_opendir(h->fs, (uint8_t)u, m_none);
        while (d >= 0 && sd_readdir(h->fs, d, &h->info) >= 0) {
            if (!is_dir(&h->info))
                continue;
            h->a[0] = '\\';
            f_cpy(h->a + 1, h->info.name);
            k = f_len(h->a);
            if (k + 14 >= DC_PATH)
                continue;
            h->a[k] = '\\';
            f_cpy(h->a + k + 1, h->pat);
            if (find_prog(h, u, k + 1)) {
                sd_closedir(h->fs, d);
                dc_flush(h);
                dc_exec(h, (uint8_t)u, h->a);
                return;
            }
        }
        if (d >= 0)
            sd_closedir(h->fs, d);
    }
    refuse(h, 0, m_notfound, SD_EFILNF);
}

/* ---- the line ----------------------------------------------------------- */

void dc_init(DC_STATE FAR *h, SDFS FAR *fs, uint8_t cols, uint8_t rows)
{
    uint16_t i;

    h->fs = fs;
    h->drive = 1;
    h->cols = cols;
    h->rows = rows;
    h->col = 0;
    h->on = 0;
    h->argc = 0;
    h->quit = 0;
    h->paging = 0;
    for (i = 0; i < SD_UNITS; i++)
        h->cwd[i][0] = 0;
}

void dc_prompt(DC_STATE FAR *h)
{
    h->quit = 0;
    o_where(h, h->drive, h->cwd[h->drive - 1]);
    o_s(h, m_prompt);
    dc_flush(h);
}

int16_t dc_run(DC_STATE FAR *h, const char FAR *line)
{
    uint16_t i;

    for (i = 0; i < DC_LINE - 1 && line[i] && (uint8_t)line[i] != DC_EOL; i++)
        h->line[i] = line[i];
    h->line[i] = 0;
    h->err = 0;
    h->quit = 0;
    h->paging = 0;
    h->keep = 0;
    h->col = 0;
    for (i = 1; i <= SD_UNITS; i++)     /* a disk may have been changed */
        sd_recheck(h->fs, (uint8_t)i);
    split(h);
    if (!h->argc)
        return 0;
    if (is_drive(ARG(h, 0)))
        c_cd(h, ARG(h, 0));
    else
        switch (lookup(ARG(h, 0))) {
        case C_LS:     c_ls(h, 0);                 break;
        case C_DIR:    c_ls(h, 1);                 break;
        case C_CD:     if (h->argc > 1)    /* not a ?: of the two: one is
                                            * const, and cc65816 makes that
                                            * near (tools/ccbug B27) */
                           c_cd(h, ARG(h, 1));
                       else
                           c_cd(h, m_root);
                       break;
        case C_PWD:    o_where(h, h->drive, h->cwd[h->drive - 1]);
                       o_c(h, DC_EOL);
                       break;
        case C_CP:     c_cpmv(h, cp_one);          break;
        case C_MV:     c_cpmv(h, mv_one);          break;
        case C_RM:     c_each(h, rm_one);          break;
        case C_MKDIR:  c_mkdir(h);                 break;
        case C_RMDIR:  c_rmdir(h);                 break;
        case C_CAT:    c_cat(h, 0);                break;
        case C_MORE:   c_cat(h, 1);                break;
        case C_DF:     c_df(h);                    break;
        case C_HELP:   o_s(h, m_help);             break;
        case C_REBOOT: dc_flush(h);
                       h->err = dc_reboot(h);
                       break;
        default:       c_run(h);                   break;
        }
    dc_flush(h);
    return h->err;
}
