/* m35_cpx.c -- the gate's control panel extension: an EVENT CPX, and,
 * under a second header, a FORM CPX (test-m35, test-m44, test-m58).
 *
 * The worked example of the harder half of the contract, and the gate
 * for it.  GENERAL.CPX is a form CPX: it runs its form through the
 * panel's Xform_do and is finished when cpx_call returns.  This one, as
 * TEST.CPX, draws itself, returns 1, and is then driven by the panel one
 * event at a time until it says stop (src/app/cpx.h; the panel's loop is
 * cp_drivecpx in src/apps/cpanel.c).  As FORM.CPX -- its header's buffer
 * starting 'F', src/m35_form.cpxh -- it runs a small form instead.
 *
 * WHAT IT PROVES, and each of these would otherwise fail silently:
 *
 *   ITS DATA IS REAL.  m35_sig is INITIALISED data, installed by this
 *   module's own crt walking data_init_table -- it is not in the image.
 *   Every entry below reads it and records what it saw, so a module
 *   entered without its crt, or one whose `saveds` prologue went
 *   missing, reports a wrong signature rather than working by luck.
 *
 *   THE HOST REACHES EVERY ENTRY.  A count per entry, so a forwarding
 *   loop that quietly drops timers -- or calls cpx_key for a button --
 *   is a number that did not move rather than a dialog that feels odd.
 *
 *   AND `quit` IS HONOURED.  It closes on a key, and the panel must stop
 *   asking: m35_after_quit counts anything that arrives afterwards and
 *   must stay 0.
 *
 *   THE TOOLKIT (phase 137, test-m58).  The XCPB at cpx_init; the hook,
 *   which takes the key 'h' so that cpx_key never sees it; Set_Evnt_Mask,
 *   a rectangle over its box and a 50 ms timer; GetFirstRect /
 *   GetNextRect, which it draws its box through; getcookie, which must
 *   say there is no 'NVDI'; MFsave; cpx_close and its `keep`; and, as a
 *   form, Xform_do's CT_KEY for Help and the way the form ended.
 *
 *   THE WIDGETS (phase 138, test-m58).  As a form it has a Popup of
 *   seven items -- past five, so it scrolls -- and a vertical slider, a
 *   list's: ten rows, three showing, Sl_size and Sl_y with the first row
 *   at the top, its arrows Sl_arrow and its thumb Sl_dragy, foo counted.
 *
 * WHERE THE TOOLKIT'S COUNTS GO: the module's own 64 settings bytes, the
 * buffer in the AES's table (XCPB's buffer) -- which outlives the module,
 * freed as it is when it shuts, so a gate reads them there afterwards
 * without finding where the module was loaded.  K_* below are the bytes.
 * Nothing saves them to the disk: CPX_Save is never called.
 *
 * It draws a real box rather than nothing, because a module that draws
 * nothing cannot be told from one that was never called.  The trees are
 * built here: this module has no resource and no workstation of its own
 * -- a CPX draws through the AES's, which objc_draw uses.
 */
#include "cpx.h"

#define M35_SIG   0x3535

/* The record in the buffer (see above).  K_MODE is the header's. */
#define K_MODE    0     /* 'F': a form CPX; anything else, an event CPX */
#define K_INITX   1     /* cpx_init calls that came with an XCPB */
#define K_HOOK    2     /* cpx_hook calls */
#define K_TAKEN   3     /* ...events it took: the key 'h' */
#define K_KEY     4     /* cpx_key calls */
#define K_M1      5     /* the pointer onto the box (cpx_m1, entering) */
#define K_TIMER   6     /* cpx_timer calls, to 255 */
#define K_CLOSE   7     /* cpx_close calls */
#define K_KEEP    8     /* ...the last one's keep */
#define K_RECTS   9     /* pieces GetFirstRect/GetNextRect gave the box */
#define K_COOKIE  10    /* getcookie('NVDI')'s answer: 0, there is no jar */
#define K_CTKEY   11    /* CT_KEY answers from Xform_do (a form) */
#define K_FORMX   12    /* how the form ended: 1 its button, 2 the closer,
                         * 3 AC_CLOSE */
#define K_MFSAVE  13    /* MFsave calls */
#define K_CALL    14    /* cpx_call calls, not booting */
#define K_POPUP   15    /* the Popup's pick, plus 1; 0 for none yet */
#define K_SLVAL   16    /* the slider's value after it last moved */
#define K_FOO     17    /* calls of the slider's foo, to 255 */

/* Where the box and the form's button are, from the work area's corner:
 * test-m58 points at them by these numbers. */
#define BOX_X     24
#define BOX_Y     96
#define BOX_H     24
#define DONE_X    96
#define DONE_Y    120
#define DONE_W    64
#define DONE_H    12
#define POP_X     24            /* the Popup's button */
#define POP_Y     20
#define POP_W     80
#define POP_H     12
#define SL_X      200           /* the slider: its up arrow, the track, */
#define SL_Y      20            /* its down arrow, one under the other */
#define SL_W      16
#define SL_AH     12            /* an arrow's height */
#define SL_TH     64            /* the track's */
#define SL_ROWS   10            /* a list of ten rows, three showing */
#define SL_SHOW   3

/* INITIALISED, deliberately: see above. */
static WORD m35_sig = M35_SIG;

/* What the gates read. */
WORD m35_inits;           /* cpx_init calls: once a load */
WORD m35_n_call;          /* ...and each entry the panel reached */
WORD m35_n_key;
WORD m35_n_button;
WORD m35_n_timer;
WORD m35_n_draw;
WORD m35_n_close;
WORD m35_after_quit;      /* anything at all after quit was set: must be 0 */
WORD m35_sig_seen;        /* m35_sig, read from inside a forwarded call */
WORD m35_alert_asked;     /* the host handed out XGen_Alert at all */
WORD m35_alert_ok;        /* ...and what it answered: 1, for alerts 1-3 */
WORD m35_got_x, m35_got_y, m35_got_w, m35_got_h;   /* the GRECT as read */

static WORD m35_quit;     /* our own copy, to notice a host that ignores it */
static XCPB FAR *m35_x;   /* the panel's block, from cpx_init or cpx_call */
static MOBLK m35_m1;      /* the rectangle asked for: the box */

static OBJECT m35_tree[8];
static const char m35_msg[] = " Event CPX -- press a key ";
static const char m35_fmsg[] = " Form CPX -- press Help ";
static const char m35_done[] = "Done";
static char m35_i0[] = "One", m35_i1[] = "Two", m35_i2[] = "Three",
            m35_i3[] = "Four", m35_i4[] = "Five", m35_i5[] = "Six",
            m35_i6[] = "Seven";
static char *m35_items[7] = { m35_i0, m35_i1, m35_i2, m35_i3, m35_i4,
                              m35_i5, m35_i6 };
static WORD m35_pick;                   /* the Popup's item in force */
static WORD m35_row;                    /* the slider's: the first row shown */

static void m35_note(void)
{
    if (m35_quit)
        m35_after_quit++;
    m35_sig_seen = m35_sig;
}

/* A byte of the record, read and written through locals: a far byte
 * changed in place is where this compiler has hung (B18, tools/ccbug). */
static uint8_t m35_get(WORD at)
{
    uint8_t FAR *b;

    if (!m35_x || !m35_x->buffer)
        return 0;
    b = (uint8_t FAR *)m35_x->buffer;
    return b[at];
}

static void m35_put(WORD at, WORD v)
{
    uint8_t FAR *b;

    if (!m35_x || !m35_x->buffer)
        return;
    b = (uint8_t FAR *)m35_x->buffer;
    b[at] = (uint8_t)v;
}

static void m35_count(WORD at)
{
    WORD v = m35_get(at);

    if (v < 255)
        m35_put(at, (WORD)(v + 1));
}

static void m35_obj(WORD i, WORD next, WORD head, WORD tail, UWORD type,
                    UWORD flags, UWORD state, int32_t spec,
                    WORD x, WORD y, WORD w, WORD h)
{
    m35_tree[i].ob_next = next;
    m35_tree[i].ob_head = head;
    m35_tree[i].ob_tail = tail;
    m35_tree[i].ob_type = type;
    m35_tree[i].ob_flags = flags;
    m35_tree[i].ob_state = state;
    m35_tree[i].ob_spec.index = spec;
    m35_tree[i].ob_x = x;
    m35_tree[i].ob_y = y;
    m35_tree[i].ob_width = w;
    m35_tree[i].ob_height = h;
}

/* The slider's foo: called by the panel after every move. */
static SAVEDS void m35_foo(uint32_t xcpb)
{
    (void)xcpb;
    m35_count(K_FOO);
}

/* AS A FORM: a line, a Done button, the Popup's button and a slider over
 * the whole work area, run through Xform_do until Done, the closer or
 * AC_CLOSE.  CT_KEY -- Help -- is counted and the form goes on. */
static void m35_form(CPXPB FAR *pb)
{
    WORD msg[8], r, x, y;
    GRECT bt, world;

    m35_obj(0, NIL, 1, 7, G_BOX, NONE, NORMAL, 0x00001100L,
            pb->rect.g_x, pb->rect.g_y, pb->rect.g_w, pb->rect.g_h);
    m35_obj(1, 2, NIL, NIL, G_STRING, NONE, NORMAL,
            (int32_t)(uint32_t)(const char FAR *)m35_fmsg,
            BOX_X, BOX_Y, (WORD)((sizeof m35_fmsg - 1) * 8), 8);
    m35_obj(2, 3, NIL, NIL, G_BUTTON, SELECTABLE | EXIT, NORMAL,
            (int32_t)(uint32_t)(const char FAR *)m35_done,
            DONE_X, DONE_Y, DONE_W, DONE_H);
    /* TOUCHEXIT alone: a selectable button is tracked until its release
     * (form_button's gr_watchbox), and the menu must come up on the press */
    m35_obj(3, 4, NIL, NIL, G_BUTTON, TOUCHEXIT, NORMAL,
            (int32_t)(uint32_t)m35_items[m35_pick],
            POP_X, POP_Y, POP_W, POP_H);
    m35_obj(4, 6, 5, 5, G_BOX, TOUCHEXIT, NORMAL, 0x00011111L,
            SL_X, SL_Y + SL_AH, SL_W, SL_TH);
    m35_obj(5, 4, NIL, NIL, G_BOX, TOUCHEXIT, NORMAL, 0x00011170L,
            0, 0, SL_W, 8);
    m35_obj(6, 7, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL,
            (int32_t)((uint32_t)0x01 << 24) | 0x00011100L,
            SL_X, SL_Y, SL_W, SL_AH);
    m35_obj(7, 0, NIL, NIL, G_BOXCHAR, TOUCHEXIT | LASTOB, NORMAL,
            (int32_t)((uint32_t)0x02 << 24) | 0x00011100L,
            SL_X, SL_Y + SL_AH + SL_TH, SL_W, SL_AH);
    /* a list's slider: SL_ROWS rows, SL_SHOW showing, the first row at the
     * top -- Sl_y's minimum is at the bottom, so min is the last first
     * row and max 0 (XControl's own list does the same) */
    m35_row = 0;
    cpx_sl_size(m35_x, m35_tree, 4, 5, SL_ROWS, SL_SHOW, SL_VERTICAL, 8);
    cpx_sl_xy(m35_x, m35_tree, 4, 5, m35_row, SL_ROWS - SL_SHOW, 0,
              SL_VERTICAL, (void (*)(uint32_t))0);
    objc_draw(m35_tree, ROOT, MAX_DEPTH, pb->rect.g_x, pb->rect.g_y,
              pb->rect.g_w, pb->rect.g_h);
    for (;;) {
        r = cpx_xform_do(m35_x, m35_tree, 0, msg);
        if (r == 3) {                   /* the Popup's button */
            objc_offset(m35_tree, 3, &x, &y);
            bt.g_x = x;
            bt.g_y = y;
            bt.g_w = POP_W;
            bt.g_h = POP_H;
            world.g_x = m35_tree[0].ob_x;
            world.g_y = m35_tree[0].ob_y;
            world.g_w = m35_tree[0].ob_width;
            world.g_h = m35_tree[0].ob_height;
            r = cpx_popup(m35_x, m35_items, 7, m35_pick, 3, &bt, &world);
            if (r >= 0) {
                m35_pick = r;
                m35_put(K_POPUP, (WORD)(r + 1));
                m35_tree[3].ob_spec.index = (int32_t)(uint32_t)m35_items[r];
            }
            m35_tree[3].ob_state = NORMAL;
            objc_draw(m35_tree, ROOT, MAX_DEPTH, x - 2, y - 2,
                      POP_W + 4, POP_H + 4);
            continue;
        }
        if (r == 5) {                   /* the thumb */
            cpx_sl_drag(m35_x, m35_tree, 4, 5, SL_ROWS - SL_SHOW, 0,
                        &m35_row, SL_VERTICAL, m35_foo);
            m35_put(K_SLVAL, m35_row);
            continue;
        }
        if (r == 6 || r == 7) {         /* an arrow: up is toward row 0 */
            WORD inc = 1;

            if (r == 6)
                inc = -1;
            cpx_sl_arrow(m35_x, m35_tree, 4, 5, r, inc, SL_ROWS - SL_SHOW,
                         0, &m35_row, SL_VERTICAL, m35_foo);
            m35_put(K_SLVAL, m35_row);
            continue;
        }
        if (r == 4)                     /* the track: nothing here */
            continue;
        if (r != -1) {
            m35_put(K_FORMX, 1);
            break;
        }
        if (msg[0] == CT_KEY)
            m35_count(K_CTKEY);
        else if (msg[0] == WM_CLOSED) {
            m35_put(K_FORMX, 2);
            break;
        } else if (msg[0] == AC_CLOSE) {
            m35_put(K_FORMX, 3);
            break;
        }
    }
    m35_tree[2].ob_state = NORMAL;
    pb->ret = 0;                        /* a FORM CPX: finished */
}

static SAVEDS void m35_cpx_call(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
    GRECT box, r;
    LONG v = 0;
    WORD n = 0;

    m35_n_call++;
    m35_note();
    m35_x = (XCPB FAR *)pb->xcpb;
    if (m35_x && m35_x->booting)
        return;
    m35_count(K_CALL);
    m35_put(K_COOKIE, cpx_getcookie(m35_x, 0x4E564449L, &v));  /* 'NVDI' */
    cpx_mfsave(m35_x, 1);
    if (m35_x && m35_x->MFsave)
        m35_count(K_MFSAVE);
    m35_got_x = pb->rect.g_x; m35_got_y = pb->rect.g_y;
    m35_got_w = pb->rect.g_w; m35_got_h = pb->rect.g_h;
    if (m35_get(K_MODE) == 'F') {
        m35_form(pb);
        return;
    }

    m35_obj(0, NIL, 1, 1, G_BOX, NONE, OUTLINED, 0x00021100L,
            (WORD)(pb->rect.g_x + BOX_X), (WORD)(pb->rect.g_y + BOX_Y),
            (WORD)(sizeof m35_msg * 8), BOX_H);
    m35_obj(1, 0, NIL, NIL, G_STRING, LASTOB, NORMAL,
            (int32_t)(uint32_t)(const char FAR *)m35_msg,
            4, 8, (WORD)((sizeof m35_msg - 1) * 8), 8);
    box.g_x = m35_tree[0].ob_x;
    box.g_y = m35_tree[0].ob_y;
    box.g_w = m35_tree[0].ob_width;
    box.g_h = m35_tree[0].ob_height;

    /* drawn a piece at a time through the window's list, as XControl's
     * modules draw; straight onto the screen with no GetFirstRect */
    if (cpx_first_rect(m35_x, &box, &r)) {
        do {
            objc_draw(m35_tree, ROOT, MAX_DEPTH, r.g_x, r.g_y, r.g_w, r.g_h);
            n++;
        } while (cpx_next_rect(m35_x, &r));
    } else if (!m35_x || !m35_x->GetFirstRect)
        objc_draw(m35_tree, ROOT, MAX_DEPTH, box.g_x, box.g_y,
                  box.g_w, box.g_h);
    m35_put(K_RECTS, n);

    /* the pointer onto the box, and a timer twenty times a second */
    m35_m1.m_out = 0;
    m35_m1.m_x = box.g_x;
    m35_m1.m_y = box.g_y;
    m35_m1.m_w = box.g_w;
    m35_m1.m_h = box.g_h;
    cpx_set_evnt_mask(m35_x, MU_M1, &m35_m1, (const MOBLK *)0, 50L);
    pb->ret = 1;                        /* an EVENT CPX: drive me */
}

/* First, with everything: 'h' is taken here and goes no further. */
static SAVEDS void m35_cpx_hook(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_count(K_HOOK);
    if ((pb->event & MU_KEYBD) && (pb->key & 0xFF) == 'h') {
        m35_count(K_TAKEN);
        pb->ret = 1;
    }
}

/* The pointer onto the box -- and then off it, so that one visit is one
 * count: an "entering" rectangle is satisfied for as long as the pointer
 * is inside it. */
static SAVEDS void m35_cpx_m1(uint32_t pbaddr)
{
    (void)pbaddr;
    /* plain ifs: a ! joined into m35_m1, whose address is handed on, is
     * wrong at every -O (B9, tools/ccbug) */
    if (m35_m1.m_out)
        m35_m1.m_out = 0;
    else {
        m35_count(K_M1);
        m35_m1.m_out = 1;
    }
    cpx_set_evnt_mask(m35_x, MU_M1, &m35_m1, (const MOBLK *)0, -1L);
}

static SAVEDS void m35_cpx_key(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
    XCPB FAR *x;

    m35_n_key++;
    m35_note();
    m35_count(K_KEY);

    /* ONE CANNED ALERT ON THE WAY OUT, which is the other half of the
     * XCPB and the half a module cannot fake.  The words are the
     * PANEL'S, in CPANEL.RSC -- this module names the alert by number
     * and carries no sentence at all, which is the whole point: every
     * module says "that file was not found" in the same words, and a
     * translator translates it once.
     *
     * GUARDED, because cpx.h says every callback may be 0 and a module
     * that assumes otherwise crashes on a host that hands out fewer
     * than this one does.  It was 0 for the whole of 0.6's development.
     *
     * FILE_NOT_FOUND is one of the three that always answer TRUE (the
     * Compendium), so m35_alert_ok is 1 or the panel is not obeying
     * Atari's rule about which alerts can say no. */
    x = (XCPB FAR *)pb->xcpb;
    if (x && x->XGen_Alert) {
        m35_alert_asked = 1;
        x->alert = XAL_FILE_NOT_FOUND;
        x->XGen_Alert(pb->xcpb);
        m35_alert_ok = x->ok;
    }

    m35_quit = 1;
    pb->quit = 1;                       /* any key closes it */
}

static SAVEDS void m35_cpx_button(uint32_t pbaddr)
{
    (void)pbaddr;
    m35_n_button++;
    m35_note();
}

static SAVEDS void m35_cpx_timer(uint32_t pbaddr)
{
    (void)pbaddr;
    m35_n_timer++;
    m35_note();
    m35_count(K_TIMER);
}

static SAVEDS void m35_cpx_draw(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_n_draw++;
    m35_note();
    objc_draw(m35_tree, ROOT, MAX_DEPTH, pb->rect.g_x, pb->rect.g_y,
              pb->rect.g_w, pb->rect.g_h);
}

/* The window went: its closer (keep 1) or AC_CLOSE (0). */
static SAVEDS void m35_cpx_close(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_n_close++;
    m35_sig_seen = m35_sig;             /* not m35_note: close IS after quit */
    m35_count(K_CLOSE);
    m35_put(K_KEEP, pb->keep);
}

static CPXINFO m35_info = {
    m35_cpx_call, m35_cpx_draw, 0, m35_cpx_timer, m35_cpx_key,
    m35_cpx_button, m35_cpx_m1, 0, m35_cpx_hook, m35_cpx_close
};

/* The header is src/m35_cpx.cpxh (and src/m35_boot.cpxh and
 * src/m35_form.cpxh: one module, three files), in front of this module
 * (tools/mkcpx.py).  The XCPB comes with the call when the panel loads
 * the module to open it (phase 137), and is counted then. */
CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb)
{
    m35_inits++;
    if (pb) {
        m35_x = pb;
        m35_count(K_INITX);
    }
    return &m35_info;
}
