/* deskcmd.c -- File -> DOS command: the window on what the command
 * printed.  The dialog that asks for the line is deskfun.c's
 * fun_command, beside the desktop's other dialogs; this file runs the
 * line and shows the result.
 *
 * The ST's desktop has no such item.  EmuTOS's has "Execute EmuCON"
 * where this one sits in the File menu (deskmain.c CLIITEM), and a
 * SpartaDOS X machine has a command processor already, with an entry a
 * program may hand a whole line to (Programming Guide 4.50, 18.9.2,
 * XCOMLI).  GEMDOS's Psystem (src/sys/dos.c dos_command) is that entry:
 * the line goes in, the command runs with GEM's screen left as it is --
 * the DOS's own console is under the overlay -- and every byte it prints
 * lands in a far buffer the desktop lends it, Malloc'd once.
 *
 * The buffer is shown in a window of its own kind: lines of it, the
 * DOS's EOL ending each, drawn a row at a time through one G_STRING of a
 * two-object tree -- the AES's own text drawing, as the text view's
 * lines are -- rather than built as items in the screen tree, because a
 * DIR is longer than the tree has items for (NUM_ITEMS) and nothing in
 * it is ever selected or dragged.  It scrolls by the arrows and the
 * slider as a folder window does, and hndl_msg hands it its messages
 * before the folder windows get to look (desktop.c).
 *
 * NEAR MEMORY.  The desktop's is spoken for: its bss shares a page-
 * rounded region with a 640-byte stack, and a page more of it is a
 * page less of the pool for the accessory beside it (test-m28).  So
 * this file keeps nothing there: its seven scalars are direct-page,
 * the tree and the line it draws through live on the stack for the
 * one objc_draw that reads them, and
 * the window's title is the far buffer's first bytes -- the AES draws
 * a far title now (src/aes/wind.c w_ptext), to forty characters.
 *
 * The command runs to completion before the window opens.  The DOS's
 * console is not the keyboard the AES reads, so a command that asks a
 * question has nobody to answer it; the item is for the ones that do
 * not -- DIR, COPY, DEL, MKDIR, CHKDSK, VER.  What they run in is what
 * the desktop is not using of bank $00, ten KB or so (dos.c says how).
 */
#include "portab.h"
#include "desk.h"

#define CMD_BUF     16384L              /* the far buffer: title, then text */
#define CMD_TEXT    (LEN_ZCMD + 4)      /* where the text starts in it */
#define CMD_COLS    80                  /* a line is shown to this width */
#define CMD_ROWS    12                  /* the window opens this many high */
#define CMD_STYLE   (NAME | CLOSER | FULLER | MOVER | SIZER | \
                     UPARROW | DNARROW | VSLIDE)
#define EOL         0x9B                /* ATASCII end of line */
#define CMD_LINE    1                   /* the tree's string, under its box */

/* The window's state: seven scalars in the desktop's direct page, which
 * has the room, where its bss has not (a direct-page scalar or pointer
 * is fine, a direct-page ARRAY is not: tools/ccbug, rule 6).  Globals,
 * not statics, so a gate finds them by name (tests/emu/sdx816.py). */
TINY WORD  cmd_id;         /* the AES's handle; 0 = closed */
TINY UWORD cmd_len;        /* how much the command printed */
TINY WORD  cmd_lines;      /* the EOLs in it, plus a last
                                             * line the DOS never ended */
TINY WORD  cmd_top;        /* the first line shown ... */
TINY UWORD cmd_top_off;    /* ... and where in the text it is */
TINY WORD  cmd_rows;       /* lines the work area holds */
char FAR * TINY cmd_buf;       /* the title, then the text */

static WORD mul_div(WORD m1, WORD m2, WORD d1)
{
    return (WORD)((LONG)m1 * m2 / d1);
}

static const uint8_t FAR *cmd_textp(void)
{
    return (const uint8_t FAR *)cmd_buf + CMD_TEXT;
}

/* Where line n starts: walked from the top line shown when n is at or
 * past it, from the start otherwise. */
static UWORD cmd_seek(WORD n)
{
    const uint8_t FAR *p = cmd_textp();
    UWORD off = 0;
    WORD i = 0;

    if (n >= cmd_top) {
        off = cmd_top_off;
        i = cmd_top;
    }
    while (i < n && off < cmd_len) {
        if (p[off] == EOL)
            i++;
        off++;
    }
    return off;
}

/* The lines in the text, counted once the command has run. */
static void cmd_count(void)
{
    const uint8_t FAR *p = cmd_textp();
    UWORD off, len = cmd_len;
    WORD n = 0;

    for (off = 0; off < len; off++)
        if (p[off] == EOL)
            n++;
    if (len) {
        len--;
        if (p[len] != EOL)
            n++;
    }
    cmd_lines = n;
    cmd_top = 0;
    cmd_top_off = 0;
}

/* One line from off into d (CMD_COLS + 1): printable ATASCII as it is,
 * inverse video as the character, anything else as a space, cut at the
 * width.  Answers the offset after its EOL, or the end. */
static UWORD cmd_line(UWORD off, char *d)
{
    const uint8_t FAR *p = cmd_textp();
    WORD n = 0, c;

    while (off < cmd_len) {
        c = p[off];
        off++;
        if (c == EOL)
            break;
        c &= 0x7F;
        if (c < 0x20 || c == 0x7F)
            c = ' ';
        if (n < CMD_COLS)
            d[n++] = (char)c;
    }
    d[n] = 0;
    return off;
}

/* The slider: its size the window's share of the lines, its place the
 * top line's. */
static void cmd_slider(void)
{
    WORD over = 0;

    if (cmd_lines > cmd_rows)
        over = (WORD)(cmd_lines - cmd_rows);
    wind_set(cmd_id, WF_VSLSIZ,
             (WORD)(over ? mul_div(cmd_rows, 1000, cmd_lines) : 1000), 0, 0, 0);
    wind_set(cmd_id, WF_VSLIDE,
             (WORD)(over ? mul_div(cmd_top, 1000, over) : 0), 0, 0, 0);
}

/* Draw the rows that meet *pc: the work area's box, white, cleared over
 * the rectangle, then each row's line through the one string of the
 * tree, moved down the box a row at a time. */
static void cmd_paint(const GRECT *work, const GRECT *pc)
{
    OBJECT tree[2];
    char line[CMD_COLS + 1];
    WORD first, last, i;
    UWORD off;

    tree[ROOT].ob_next = NIL;
    tree[ROOT].ob_head = CMD_LINE;
    tree[ROOT].ob_tail = CMD_LINE;
    tree[ROOT].ob_type = G_BOX;
    tree[ROOT].ob_flags = NONE;
    tree[ROOT].ob_state = NORMAL;
    tree[ROOT].ob_spec.index = WINDOW_SPEC;
    tree[ROOT].ob_x = work->g_x;
    tree[ROOT].ob_y = work->g_y;
    tree[ROOT].ob_width = work->g_w;
    tree[ROOT].ob_height = work->g_h;
    tree[CMD_LINE].ob_next = ROOT;
    tree[CMD_LINE].ob_head = NIL;
    tree[CMD_LINE].ob_tail = NIL;
    tree[CMD_LINE].ob_type = G_STRING;
    tree[CMD_LINE].ob_flags = LASTOB;
    tree[CMD_LINE].ob_state = NORMAL;
    tree[CMD_LINE].ob_spec.index = (LONG)(uint32_t)line;
    tree[CMD_LINE].ob_x = 1;
    tree[CMD_LINE].ob_y = 0;
    tree[CMD_LINE].ob_width = (WORD)(G.g_wchar * CMD_COLS);
    tree[CMD_LINE].ob_height = G.g_hchar;
    objc_draw(tree, ROOT, 0, pc->g_x, pc->g_y, pc->g_w, pc->g_h);

    first = (WORD)((pc->g_y - work->g_y) / G.g_hchar);
    last = (WORD)((pc->g_y + pc->g_h - 1 - work->g_y) / G.g_hchar);
    if (last > cmd_rows - 1)
        last = (WORD)(cmd_rows - 1);
    off = cmd_seek((WORD)(cmd_top + first));
    for (i = first; i <= last; i++) {
        if (cmd_top + i >= cmd_lines)
            break;
        off = cmd_line(off, line);
        tree[CMD_LINE].ob_y = (WORD)(i * G.g_hchar);
        objc_draw(tree, CMD_LINE, 0, pc->g_x, pc->g_y, pc->g_w, pc->g_h);
    }
}

/* Draw what of *pc is visible: once per rectangle of the window's list. */
static void cmd_redraw(const GRECT *pc)
{
    GRECT work, t;

    wind_get_grect(cmd_id, WF_WORKXYWH, &work);
    graf_mouse(M_OFF, 0);
    wind_get_grect(cmd_id, WF_FIRSTXYWH, &t);
    while (t.g_w && t.g_h) {
        if (rc_intersect(pc, &t))
            cmd_paint(&work, &t);
        wind_get_grect(cmd_id, WF_NEXTXYWH, &t);
    }
    graf_mouse(M_ON, 0);
}

/* The rows the work area holds, and the top line kept within them. */
static void cmd_size(void)
{
    GRECT work;
    WORD over = 0;

    wind_get_grect(cmd_id, WF_WORKXYWH, &work);
    cmd_rows = (WORD)(work.g_h / G.g_hchar);
    if (cmd_rows < 1)
        cmd_rows = 1;
    if (cmd_lines > cmd_rows)
        over = (WORD)(cmd_lines - cmd_rows);
    if (cmd_top > over) {
        cmd_top_off = cmd_seek(over);           /* before top moves: the
                                                 * walk starts from it */
        cmd_top = over;
    }
    cmd_slider();
}

/* Show the view from line newtop, if that is a change. */
static void cmd_scroll(WORD newtop)
{
    GRECT t;
    WORD over = 0, lo, want;

    if (cmd_lines > cmd_rows)
        over = (WORD)(cmd_lines - cmd_rows);
    lo = newtop < 0 ? 0 : newtop;               /* fresh locals, not the
                                                 * parameter clamped in
                                                 * place: tools/ccbug B10 */
    want = lo > over ? over : lo;
    if (want == cmd_top)
        return;
    cmd_top_off = cmd_seek(want);
    cmd_top = want;
    cmd_slider();
    wind_get_grect(cmd_id, WF_WORKXYWH, &t);
    cmd_redraw(&t);
}

static void cmd_close(void)
{
    wind_close(cmd_id);
    wind_delete(cmd_id);
    cmd_id = 0;
}

/* The title: " the line ", at the head of the far buffer, which the AES
 * reads at every draw of it. */
static void cmd_title(const char *line)
{
    char FAR *t = cmd_buf;
    WORD i;

    t[0] = ' ';
    for (i = 0; i < LEN_ZCMD - 1 && line[i]; i++)
        t[i + 1] = line[i];
    t[i + 1] = ' ';
    t[i + 2] = 0;
    wind_set(cmd_id, WF_NAME, (WORD)((uint32_t)cmd_buf >> 16),
             (WORD)(uint32_t)cmd_buf, 0, 0);
}

/* The window: opened on the first command, its title the line that
 * ran, and shown from the top on every one after. */
static WORD cmd_show(const char *line)
{
    GRECT work, r;

    if (!cmd_id) {
        work.g_x = (WORD)(G.g_desk.g_x + G.g_wchar * 2);
        work.g_y = (WORD)(G.g_desk.g_y + G.g_hchar * 2);
        work.g_w = (WORD)(G.g_wchar * (CMD_COLS - 12));
        work.g_h = (WORD)(G.g_hchar * CMD_ROWS);
        wind_calc_grect(WC_BORDER, CMD_STYLE, &work, &r);
        cmd_id = wind_create_grect(CMD_STYLE, &G.g_desk);
        if (cmd_id <= 0) {
            cmd_id = 0;
            return FALSE;
        }
        cmd_title(line);
        cmd_rows = CMD_ROWS;
        cmd_slider();
        wind_open_grect(cmd_id, &r);            /* the AES asks for the draw */
        cmd_size();
        return TRUE;
    }
    cmd_title(line);
    wind_set(cmd_id, WF_TOP, 0, 0, 0, 0);
    cmd_size();
    wind_get_grect(cmd_id, WF_WORKXYWH, &work);
    cmd_redraw(&work);
    return TRUE;
}

/* Whether the DOS has a command processor to hand a line to, asked once
 * at start: the item is greyed when it has not. */
void cmd_init(void)
{
    if (Psystem(0, 0, 0L) < 0)
        menu_ienable(G.a_menu, CMDITEM, 0);
}

/* Run the line and show what it printed. */
void cmd_run(const char *line)
{
    LONG n;

    if (!cmd_buf) {
        LONG a = Malloc(CMD_BUF);
        if (a <= 0) {
            fun_alert(1, STCMDMEM);
            return;
        }
        cmd_buf = (char FAR *)a;
    }
    desk_busy(TRUE);
    n = Psystem(line, cmd_buf + CMD_TEXT, CMD_BUF - CMD_TEXT);
    desk_busy(FALSE);
    if (n < 0)
        n = 0;                                  /* the item was enabled;
                                                 * shown empty rather than
                                                 * refused */
    cmd_len = (UWORD)n;
    cmd_count();
    if (!cmd_show(line))
        fun_alert(1, STNOWIND);
}

/* The window's messages; FALSE for anybody else's. */
WORD cmd_msg(const WORD *msg)
{
    GRECT t;
    WORD x, y;

    if (!cmd_id || msg[3] != cmd_id)
        return FALSE;
    switch (msg[0]) {
    case WM_REDRAW:
        t.g_x = msg[4];
        t.g_y = msg[5];
        t.g_w = msg[6];
        t.g_h = msg[7];
        cmd_redraw(&t);
        break;
    case WM_TOPPED:
        wind_set(cmd_id, WF_TOP, 0, 0, 0, 0);
        break;
    case WM_CLOSED:
        cmd_close();
        break;
    case WM_FULLED:
        do_wfull(cmd_id);
        cmd_size();
        break;
    case WM_ARROWED:
        switch (msg[4]) {
        case WA_UPPAGE:
            cmd_scroll((WORD)(cmd_top - cmd_rows));
            break;
        case WA_DNPAGE:
            cmd_scroll((WORD)(cmd_top + cmd_rows));
            break;
        case WA_UPLINE:
            cmd_scroll((WORD)(cmd_top - 1));
            break;
        case WA_DNLINE:
            cmd_scroll((WORD)(cmd_top + 1));
            break;
        default:
            break;
        }
        break;
    case WM_VSLID:
        x = 0;
        if (cmd_lines > cmd_rows)
            x = (WORD)(cmd_lines - cmd_rows);
        cmd_scroll(mul_div(msg[4], x, 1000));
        break;
    case WM_SIZED:
    case WM_MOVED:
        x = (WORD)((msg[4] + 8) & 0xFFF0);      /* deskwin.c do_xyfix: even
                                                 * x, so a move is one blit,
                                                 * and never over the menu */
        y = msg[5];
        if (y < G.g_desk.g_y)
            y = G.g_desk.g_y;
        t.g_x = x;
        t.g_y = y;
        t.g_w = msg[6];
        t.g_h = msg[7];
        wind_set_grect(cmd_id, WF_CURRXYWH, &t);
        if (msg[0] == WM_SIZED) {
            y = cmd_top;
            cmd_size();
            if (cmd_top != y) {                 /* the view moved: all of it */
                wind_get_grect(cmd_id, WF_WORKXYWH, &t);
                cmd_redraw(&t);
            }
        }
        break;
    default:
        break;
    }
    return TRUE;
}

/* The desktop is leaving: the window goes, the buffer with its far memory. */
void cmd_exit(void)
{
    if (cmd_id)
        cmd_close();
}
