/* event.c -- the AES event layer: mouse, buttons, keyboard, timer
 * (EmuTOS aes/gemevlib.c + geminput.c, single-tasking).
 *
 * Underneath GEM's AES is a small multitasking kernel: the interrupt
 * handlers post to a fork queue, a dispatcher runs the posts, and a process
 * waiting in evnt_multi sleeps until one of its events completes.  gem4xe
 * runs one application and polls, so the same state machine is driven from
 * vdi_input_poll() through the VDI's three input vectors -- motion, button,
 * timer -- and ev_multi() loops on the poll until something it asked for
 * has happened.  What is kept exactly is the button logic: the transition
 * pair (button/pr_button, so a press-and-release that arrived before anyone
 * asked still reports the press), the double-click delay that turns rapid
 * presses into a click count, and downorup()'s mask/state/flag test that
 * every waiter is phrased in.  form_do and the window manager are written
 * against precisely that behaviour.
 *
 * One departure from EmuTOS, taken from the ROM AES instead: cancelling a
 * pending multi-click button wait releases the pending-clicks semaphore.
 * EmuTOS leaks it, so after the first keystroke in a form every later click
 * is reported through the double-click delay.
 *
 * OWNERSHIP.  GEM's control manager is a second process that owns the
 * mouse whenever a press lands outside the application's control
 * rectangle -- the top window's work area, or the whole screen while
 * form_do runs -- and the application's waits see nothing of the button,
 * the keyboard or the pointer until the button is up and the mouse is
 * handed back (geminput.c's chkown/set_mown).  Here the control manager
 * is a call, ct_run, made from the poll that saw the press: it runs the
 * gadget to completion, nesting its own waits inside the application's,
 * and any message it sends is in the queue when the application's wait
 * looks again.  The ownership rules are kept as they are: the press
 * decides the owner, the application's checks are gated while it is not
 * the owner, the hand-back posts the button state to a waiter as
 * set_mown does.  Where EmuTOS and the ROM differ -- the ROM's control
 * manager keeps the mouse until the button is up and never sends
 * WM_UNTOPPED -- the ROM is followed.  The menu is the control manager's
 * other entry: the pointer arriving in the menu bar with the buttons up
 * runs it the same way (ct_poll), and while it runs presses do not
 * change the owner (gl_ctmown).
 */
#include "aes.h"
#include "proc.h"
#include "../sys/farmem.h"
#include "../sys/zwin.h"

/* ---- the pointer as the AES sees it ------------------------------------ */

WORD button, xrat, yrat, kstate, mclick, mtrans;
WORD pr_button, pr_xrat, pr_yrat, pr_mclick;

WORD gl_ticktime;               /* ms per tick, from the VDI */
WORD gl_dclick;                 /* double-click window in ticks */
WORD gl_dcindex;

/* The double-click machine (geminput.c).  gl_btrue is what the hardware
 * says right now; gl_bdesired/gl_bclick/gl_bdely accumulate presses while
 * a multi-click waiter exists (gl_bpend). */
static WORD gl_btrue, gl_bdesired, gl_bclick, gl_bdely, gl_bpend;

/* Double-click rates in ms, index 0..4, the slowest first. */
static const WORD gl_dcrates[5] = { 450, 330, 275, 220, 165 };

uint32_t gl_ticks;              /* timer ticks seen since ev_init */

/* The one button wait a process can have outstanding: whoever is inside
 * ev_multi.  bchange() completes it, ev_multi cancels it.
 *
 * These were file statics until the desk accessories, and the comment
 * said "the one button wait that can be outstanding" because there was
 * one process to have one.  Two processes can be inside ev_multi at once
 * now (src/aes/proc.h), so the slot belongs to whoever is running and
 * the rest of this file does not have to know that it moved. */
#define bw_active   (rlr->p_bwactive)
#define bw_parm     (rlr->p_bwparm)
#define bw_want     (rlr->p_bwwant)
#define bw_done     (rlr->p_bwdone)
#define bw_clicks   (rlr->p_bwclicks)

/* ---- ownership (geminput.c) --------------------------------------------
 * ctrl is the application's rectangle.  ct_owns: the last press went to
 * the control manager, which keeps the mouse until the button is up.
 * ct_inside: the control manager is running, its waits nested inside the
 * application's, and sees everything.  ct_click: a press it has yet to
 * take, seen in the poll before ct_poll gets its turn. */
static GRECT    ctrl;
static WORD     ct_owns, ct_inside, ct_click;
static WORD     ct_x, ct_y;     /* where that press was */

/* TRUE when the application's waits may look at the input. */
#define ct_mine()   (ct_inside || !ct_owns)

/* ---- the message pipe (gemqueue.c) --------------------------------------
 * GEM gives each process a 256-byte queue of 16-byte messages, which the
 * window manager, the menu and appl_write post into and evnt_mesag /
 * evnt_multi(MU_MESAG) read from, oldest first.  One process here, so one
 * queue.  Two messages coalesce on the way in: a WM_REDRAW for a handle
 * that already has one waiting is unioned into it (the ROM AES's rule),
 * and a WM_ARROWED replaces a WM_ARROWED already waiting (EmuTOS's, so a
 * held arrow does not stack up scrolls the application cannot catch up
 * with).  A full queue drops the message: GEM would block the sender,
 * and here the sender is the process that would have to drain it. */
ZWIN static WORD gl_queue[NUM_MSGS][8];

/* The application keeps the queue it always had -- sixteen messages in
 * the banked window -- and only an accessory pays the pool for one
 * (src/aes/proc.c).  The COUNT is the process's, not this file's. */
WORD *gl_appqueue(WORD *max)
{
    *max = NUM_MSGS;
    return &gl_queue[0][0];
}

/* ---- the button-state test every waiter is phrased in ------------------
 * buparm: bit 24 flag (0 = wait to ENTER the state, 1 = to LEAVE it),
 * bits 23..16 clicks wanted, bits 15..8 the mask, bits 7..0 the state. */
static WORD downorup(WORD new, uint32_t buparm)
{
    uint32_t t;
    WORD flag, mask, val;

    t = buparm >> 24;
    flag = (WORD)t & 0xFF;
    t = buparm >> 8;
    mask = (WORD)t & 0xFF;
    val = (WORD)buparm & 0xFF;
    return ((mask & (val ^ new)) == 0) != flag;
}

uint32_t combine_cms(WORD clicks, UWORD mask, UWORD state)
{
    uint32_t r = (uint32_t)(clicks & 0xFFFF) << 16;
    r |= (uint32_t)(mask & 0xFF) << 8;
    r |= (uint32_t)(state & 0xFF);
    return r;
}

/* TRUE when the pointer is where pmo wants it: inside m_gr, or outside
 * it if m_out. */
static WORD in_mrect(const MOBLK *pmo)
{
    WORD in = inside(xrat, yrat, &pmo->m_gr);
    return (pmo->m_out != in);
}

/* ---- the tape: appl_trecord and appl_tplay -----------------------------
 *
 * The AES's own input, written into the caller's array and played back
 * out of it.  The ROM does this through its fork queue -- ap_trecd sets
 * gl_recd and the forker files every post, ap_tplay pushes them back in
 * and dispatches between each (GEMAPLIB.C) -- and gem4xe has no fork
 * queue, so the three places input actually ARRIVES do the filing: the
 * VDI's motion, button and timer vectors below, and the one call that
 * takes a key.
 *
 * THE FORMAT IS THE COMPENDIUM'S EVNTREC (p.372), six bytes: a WORD
 * saying which kind, then a LONG whose halves depend on it.  It is the
 * caller's memory and may be far, so records go in and out a record at a
 * time rather than through a pointer.
 *
 * RECORDING BLOCKS UNTIL THE ARRAY IS FULL, which is the ROM's contract
 * and reads like a hang until you see why it is not: a timer record is
 * filed every TP_SAMPLE whether anything else happened or not, so a
 * quiet machine fills the array with the passage of time and the call
 * comes back.  The ROM samples at the same 100 ms.
 *
 * WHAT IS NOT RECORDED: a key nobody asks for.  The ROM files a kchange
 * when the key ARRIVES; here it is filed when the AES takes it out of
 * the VDI's queue, because that is the only place the AES sees one.  A
 * key pressed while no wait wants it is recorded when a wait finally
 * does, with the time of that moment rather than of the press.
 *
 * WHAT THE GATE COVERS: the pointer, the buttons and the gaps between
 * them, both ways round -- a tape the host wrote, and a tape this code
 * took and then played back, compared byte for byte (test-m7 case 0).
 * THE KEYBOARD IS NOT IN IT.  ev_getkey below is written and is not
 * exercised by any case, which is worth knowing before trusting it. */
#define TP_OFF      0
#define TP_RECORD   1
#define TP_PLAY     2
#define TP_RECBYTES 6           /* EVNTREC: a WORD and a LONG */
#define TP_SAMPLE   100         /* ms between timer records, as the ROM */

#define APPEVNT_TIMER    0
#define APPEVNT_BUTTON   1
#define APPEVNT_MOUSE    2
#define APPEVNT_KEYBOARD 3

static uint32_t tp_buf;         /* the caller's array, or 0 */
static WORD     tp_max, tp_n;   /* its room, and what is in it */
static WORD     tp_mode = TP_OFF;
static uint32_t tp_mark;        /* gl_ticks when the last record went in */
/* A key the tape has put back, or 0 for none.  0 is safe as "none"
 * because a GEM key word is the scan code in the high byte and the
 * ASCII in the low one, and 0 would be neither. */
static WORD     tp_key;

static void tp_rec(WORD ev, uint32_t val)
{
    uint8_t r[TP_RECBYTES];

    if (tp_mode != TP_RECORD || tp_n >= tp_max)
        return;
    /* Little-endian, both fields, because the caller's EVNTREC is this
     * compiler's: a WORD then a LONG is six bytes with the LONG at
     * offset two, which was read out of the generated code and not
     * assumed -- Calypsi pads some structs to four (tools/ccbug B7). */
    r[0] = (uint8_t)ev;
    r[1] = (uint8_t)(ev >> 8);
    r[2] = (uint8_t)val;
    r[3] = (uint8_t)(val >> 8);
    r[4] = (uint8_t)(val >> 16);
    r[5] = (uint8_t)(val >> 24);
    far_put(tp_buf + (uint32_t)tp_n * TP_RECBYTES, r, TP_RECBYTES);
    tp_n++;
    tp_mark = gl_ticks;
    if (tp_n >= tp_max)
        tp_mode = TP_OFF;       /* full: ap_trecord stops waiting */
}

/* The gap before an event, so that a playback can keep its timing.  The
 * ROM files a TCHNG of its own for this and so does gem4xe. */
static void tp_gap(void)
{
    uint32_t dt;

    if (tp_mode != TP_RECORD)
        return;
    dt = (gl_ticks - tp_mark) * (uint32_t)gl_ticktime;
    if (dt)
        tp_rec(APPEVNT_TIMER, dt);
}

/* ---- transitions -------------------------------------------------------- */

/* Who a press at (mx,my) goes to (chk_ctrl): 1 the application, inside
 * its rectangle; -1 the control manager, on the menu bar or any window
 * but the desktop; 0 the desktop's owner, which is the application. */
static WORD ct_chkown(WORD mx, WORD my)
{
    if (inside(mx, my, &ctrl))
        return 1;
    if (inside(mx, my, &gl_rmenu))
        return -1;
    if (wm_find(mx, my))
        return -1;
    return 0;
}

/* A button transition, `clicks` presses' worth.  A left press with the
 * buttons up decides who owns the mouse, unless the menu has it.  Remember
 * the previous transition so that ev_rets can report a press that was
 * released again before the caller looked; then satisfy the button waiter
 * if this is what it asked for (post_button) -- and if it may see it. */
static void bchange(WORD new, WORD clicks)
{
    if (!gl_ctmown && new == 1 && button == 0 && !ct_inside) {
        ct_owns = (ct_chkown(xrat, yrat) < 0);
        if (ct_owns) {
            ct_click = TRUE;
            ct_x = xrat;
            ct_y = yrat;
        }
    }
    mtrans++;
    pr_button = button;
    pr_mclick = mclick;
    pr_xrat   = xrat;
    pr_yrat   = yrat;
    button = new;
    mclick = clicks;

    if (bw_active && ct_mine() && downorup(new, bw_parm)) {
        if (bw_want > 1)
            gl_bpend--;
        if (clicks > bw_want)
            bw_clicks = bw_want;
        else
            bw_clicks = clicks;
        bw_done = TRUE;
        bw_active = FALSE;
    }
}

/* Whenever the buttons change (the button interrupt in GEM).  If someone
 * wants multiple clicks, a press starts a delay in which further presses
 * are counted instead of reported. */
static void b_click(WORD state)
{
    if (state == gl_btrue)
        return;
    if (gl_bdely) {
        if (state == gl_bdesired) {
            gl_bclick++;
            gl_bdely = (WORD)(gl_bdely + 3);
        }
    } else {
        if (gl_bpend && state) {
            gl_bclick = 1;
            gl_bdesired = state;
            gl_bdely = gl_dclick;
        } else {
            bchange(state, 1);
        }
    }
    gl_btrue = state;
}

/* The tick's share of the double-click delay.  When it runs out the
 * counted presses are reported, and the release too if the button has
 * already come up. */
static void b_delay(WORD amnt)
{
    if (!gl_bdely)
        return;
    gl_bdely = (WORD)(gl_bdely - amnt);
    if (gl_bdely < 0)
        gl_bdely = 0;
    if (gl_bdely == 0) {
        bchange(gl_bdesired, gl_bclick);
        if (gl_bdesired != gl_btrue)
            bchange(gl_btrue, 1);
    }
}

/* The pointer moved.  A move of more than two pixels ends a double-click
 * wait early: a drag is not a double click. */
static void mchange(WORD x, WORD y)
{
    WORD dx = (WORD)(xrat - x), dy = (WORD)(yrat - y);

    if (gl_bdely && (dx > 2 || dx < -2 || dy > 2 || dy < -2))
        b_delay(gl_bdely);
    xrat = x;
    yrat = y;
}

/* ---- the VDI vectors ---------------------------------------------------
 * Called from vdi_input_poll(): motion every pass, button on a change,
 * timer once per tick.  The AES reads the pointer back through vq_mouse,
 * as the ROM does, rather than reaching into the driver. */
static void ev_motv(void)
{
    WORD x, y;

    if (tp_mode == TP_PLAY)     /* the tape is driving, not the mouse */
        return;
    gsx_mouse(&x, &y);
    if (x != xrat || y != yrat) {
        mchange(x, y);
        tp_gap();
        tp_rec(APPEVNT_MOUSE, (uint32_t)(UWORD)x
                              | ((uint32_t)(UWORD)y << 16));
    }
}

static void ev_butv(void)
{
    WORD x, y, b;

    if (tp_mode == TP_PLAY)
        return;
    b = gsx_mouse(&x, &y);
    b_click(b);
    tp_gap();
    tp_rec(APPEVNT_BUTTON, (uint32_t)(UWORD)b
                           | ((uint32_t)(UWORD)mclick << 16));
}

static void ev_timv(void)
{
    gl_ticks++;
    b_delay(1);
    /* The sample: a record of the time passing, so that recording on a
     * quiet machine still fills the array and comes back. */
    if (tp_mode == TP_RECORD
        && (gl_ticks - tp_mark) * (uint32_t)gl_ticktime >= TP_SAMPLE)
        tp_rec(APPEVNT_TIMER,
               (gl_ticks - tp_mark) * (uint32_t)gl_ticktime);
}

/* ---- ownership ---------------------------------------------------------- */

void set_ctrl(const GRECT *pt)
{
    ctrl = *pt;
}

void get_ctrl(GRECT *pt)
{
    *pt = ctrl;
}

/* The mouse back to the application (set_mown): the button's state is
 * posted to a waiter, in case that is what it was waiting for. */
static void ct_release(void)
{
    ct_owns = FALSE;
    ct_arrow_stop();
    if (bw_active && downorup(button, bw_parm)) {
        if (bw_want > 1)
            gl_bpend--;
        bw_clicks = 1;
        bw_done = TRUE;
        bw_active = FALSE;
    }
}

/* A new control rectangle, and the mouse to its owner -- only with the
 * buttons up, as GEM insists: a press being handled runs to its end. */
void ct_chgown(const GRECT *pr)
{
    ctrl = *pr;
    if (!gl_ctmown && button == 0)
        ct_release();
}

/* The control manager's turn at a press.  The application's button wait,
 * if one is registered, is put aside so that the gadget's own waits can
 * use the one slot, and restored untouched afterwards; mtrans is the
 * control manager's to reset, as its ev_multi would have. */
static void ct_run(WORD menu)
{
    WORD     s_active = bw_active, s_want = bw_want, s_done = bw_done;
    WORD     s_clicks = bw_clicks;
    uint32_t s_parm = bw_parm;

    bw_active = FALSE;
    ct_inside = TRUE;
    mtrans = 0;
    wm_update(BEG_UPDATE);
    if (menu)
        hctl_rect();
    else
        hctl_button(ct_x, ct_y);
    wm_update(END_UPDATE);
    ct_inside = FALSE;
    bw_active = s_active;
    bw_want = s_want;
    bw_done = s_done;
    bw_clicks = s_clicks;
    bw_parm = s_parm;
}

/* After every poll: a press for the control manager is run; the
 * pointer's arrival in the menu bar with the buttons up, and the mouse
 * the application's, runs the menu (mchange's tail in the donor); while
 * the control manager holds the mouse the keys are its to drop and a
 * held arrow repeats; and the button coming up hands the mouse back.
 *
 * The menu returns with the button as the transition that ended it
 * left it.  Down, the mouse is held here until it is up: the donor's
 * control manager instead waits again at once and, the button being
 * down, dispatches it as a fresh press -- WM_TOPPED to a window under
 * the item, or a gadget's drag started with the button already held.
 * That is not done. */
void ct_poll(void)
{
    WORD k;

    if (ct_inside)
        return;
    if (ct_click) {
        ct_click = FALSE;
        ct_run(FALSE);
    }
    if (!ct_owns && !gl_ctmown && button == 0 && gl_mntree
        && in_mrect(&gl_ctwait)) {
        ct_owns = TRUE;
        ct_run(TRUE);
    }
    if (!ct_owns)
        return;
    if (button) {
        while (gsx_getkey(&k))
            ;
        ct_arrow_repeat();
        return;
    }
    ct_release();
}

/* TRUE when nothing is mid-gesture, so a turn may change hands here.
 * The rule is GEM's: the mouse belongs to whoever took the press until
 * the button comes up (set_mown refuses to transfer with a button down),
 * and the control manager's own state is the AES's rather than the
 * process's, so it must be allowed to finish. */
WORD ct_idle(void)
{
    return !ct_inside && !ct_owns && !ct_click && button == 0;
}

/* One poll of the devices, the control manager's turn, and then somebody
 * else's turn if anybody else can go: every wait loop here spins on
 * this, which makes it the one place in gem4xe where a context switch
 * can happen (src/aes/proc.h). */
void ev_poll(void)
{
    vdi_input_poll();
    ct_poll();
    proc_yield();
}

/* ---- set-up ------------------------------------------------------------- */

WORD ev_dclick(WORD rate, WORD setit)
{
    if (setit) {
        WORD ms;
        if (rate < 0) rate = 0;
        if (rate > 4) rate = 4;
        gl_dcindex = rate;
        ms = gl_dcrates[rate];
        gl_dclick = (WORD)(ms / gl_ticktime);
    }
    return gl_dcindex;
}

/* Hook the vectors and take the pointer's current state as the starting
 * point.  The tick length comes from the VDI; the double-click window is
 * derived from it, as geminit does. */
void ev_init(void)
{
    WORD x, y, b, t;

    mtrans = 0;
    mclick = pr_mclick = 0;
    gl_bdely = gl_bpend = gl_bclick = 0;
    bw_active = bw_done = FALSE;
    gl_ticks = 0;
    rlr->p_qcount = 0;  /* the test runner re-inits: no stale messages */
    rlr->p_evwait = 0;
    ct_owns = ct_inside = ct_click = FALSE;
    r_set(&ctrl, 0, 0, 0, 0);
    gl_ctmown = FALSE;
    ct_arrow_stop();

    t = gsx_vex(VEX_TIMV, ev_timv);
    if (t < 1)
        t = 1;
    gl_ticktime = t;
    gsx_vex(VEX_BUTV, ev_butv);
    gsx_vex(VEX_MOTV, ev_motv);

    b = gsx_mouse(&x, &y);
    xrat = pr_xrat = x;
    yrat = pr_yrat = y;
    button = pr_button = b;
    gl_btrue = gl_bdesired = b;
    kstate = gsx_kstate();

    ev_dclick(3, TRUE);
}

/* Post a message to `to`; see the coalescing rules above.  A message to
 * a process that is not there is dropped, which is what GEM does with
 * one addressed to a pid that has gone. */
void mq_put(PROC *to, const WORD *msg)
{
    WORD i, j;
    WORD *q;

    if (!to)
        return;
    q = to->p_queue;
    if (msg[0] == WM_REDRAW || msg[0] == WM_ARROWED) {
        for (i = 0; i < to->p_qcount; i++) {
            WORD *om = q + i * 8;
            if (om[0] != msg[0])
                continue;
            if (msg[0] == WM_REDRAW) {
                if (om[3] != msg[3])
                    continue;
                rc_union((const GRECT *)&msg[4], (GRECT *)&om[4]);
                return;
            }
            for (j = 0; j < 8; j++)
                om[j] = msg[j];
            return;
        }
    }
    if (to->p_qcount >= to->p_qmax)
        return;
    q += to->p_qcount * 8;
    for (j = 0; j < 8; j++)
        q[j] = msg[j];
    to->p_qcount++;
}

/* Take the running process's oldest message; FALSE if there is none. */
WORD mq_get(WORD *msg)
{
    WORD i, j;
    WORD *q = rlr->p_queue;

    if (rlr->p_qcount == 0)
        return FALSE;
    for (j = 0; j < 8; j++)
        msg[j] = q[j];
    rlr->p_qcount--;
    for (i = 0; i < rlr->p_qcount; i++)
        for (j = 0; j < 8; j++)
            q[i * 8 + j] = q[(i + 1) * 8 + j];
    return TRUE;
}

WORD mq_count(void)
{
    return rlr->p_qcount;
}

/* The window manager's message: type, sender, no extra length, then five
 * words of argument.
 *
 * THE SENDER IS 0, and that is a real difference from the donor rather
 * than an omission.  There the control manager is a PROCESS, SCRENMGR,
 * and its pid goes in word 1 of every MN_SELECTED and AC_OPEN it sends;
 * here it is a call nested in the application's wait (docs/phase8.md), so
 * there is no process to name and the AES's own messages say 0.  Nothing
 * documented reads word 1 of these -- an accessory is told which item it
 * was by words 3 and 4 -- and appl_write, which is the one place a real
 * sender exists, fills it in itself. */
void ap_sendmsg(PROC *to, WORD type, WORD w3, WORD w4,
                WORD w5, WORD w6, WORD w7)
{
    /* ONE buffer, not one per caller.  It is filled and handed to
     * mq_put, which copies it into the destination's queue before this
     * returns, so it is scratch and never state -- which is why the
     * donor has a single appl_msg for the whole AES.  Three of these
     * were three eight-word statics in three files until bank $00 ran
     * out of room, which is a tidier reason to fix it than tidiness. */
    static WORD ap_msg[8];

    ap_msg[0] = type;
    ap_msg[1] = 0;
    ap_msg[2] = 0;
    ap_msg[3] = w3;
    ap_msg[4] = w4;
    ap_msg[5] = w5;
    ap_msg[6] = w6;
    ap_msg[7] = w7;
    mq_put(to, ap_msg);
}

/* evnt_mesag: the oldest message, waiting for one if the queue is empty.
 * Nothing but this process posts, so an empty queue is waited on the way
 * every other event is -- polling -- and a wait with nothing pending
 * never returns, exactly as GEM's would. */
void ev_mesag(WORD *mebuff)
{
    WORD     s_evwait = rlr->p_evwait;      /* see ev_wait: it may be nested */
    uint32_t s_tdead = rlr->p_tdead;

    rlr->p_evwait = MU_MESAG;
    if (rlr == proc_input && rlr != proc_app)
        proc_input = proc_app;      /* see ev_wait: nothing on the screen */
    while (!mq_get(mebuff))
        ev_poll();
    rlr->p_evwait = s_evwait;
    rlr->p_tdead = s_tdead;
}

/* Drain the keyboard queue (gemfmlib.c fq). */
void ev_fq(void)
{
    WORD k;
    while (gsx_getkey(&k))
        ;
}

/* THE ONE PLACE THE AES TAKES A KEY, so the one place the tape can file
 * one or put one back.  ev_fq's drain still calls gsx_getkey directly:
 * throwing keys away is not an event worth recording, and a playback
 * that had to survive a drain would be recording its own replay. */
static WORD ev_getkey(WORD *pkey)
{
    if (tp_mode == TP_PLAY) {
        if (!tp_key)
            return FALSE;
        *pkey = tp_key;
        tp_key = 0;
        return TRUE;
    }
    if (!gsx_getkey(pkey))
        return FALSE;
    tp_gap();
    tp_rec(APPEVNT_KEYBOARD, (uint32_t)(UWORD)*pkey
                             | ((uint32_t)(UWORD)kstate << 16));
    return TRUE;
}

/* ---- the tape's two calls ----------------------------------------------
 *
 * Both live here rather than in appl.c, where the other application
 * manager calls are, because both ARE the input layer: one files what
 * the vectors above see and the other hands the vectors' work to
 * mchange and b_click itself. */

/* appl_trecord: fill the caller's array and say how many went in.  It
 * BLOCKS until the array is full, which is the ROM's contract
 * (GEMAPLIB.C's `while (gl_recd) ev_timer(100L);`) and terminates for
 * the ROM's reason: time itself is recorded. */
WORD ap_trecord(uint32_t buf, WORD num)
{
    if (!buf || num <= 0 || tp_mode != TP_OFF)
        return 0;
    tp_buf = buf;
    tp_max = num;
    tp_n = 0;
    tp_mark = gl_ticks;
    tp_mode = TP_RECORD;
    while (tp_mode == TP_RECORD)
        ev_timer(TP_SAMPLE);
    tp_buf = 0;
    return tp_n;
}

/* appl_tplay: the array back through the input layer, `scale` per cent
 * of the speed it was taken at -- 100 as recorded, 200 twice as fast.
 *
 * THE POINTER IS LEFT WHERE THE TAPE PUT IT.  The ROM saves xrat and
 * yrat at the top and the code that would put them back is inside an
 * `#if UNLINKED` that is off, with a note at the head of the file
 * saying the fix was "so after it finished, it stay where it is".  The
 * next real movement of the mouse takes it back, on that machine and on
 * this one, because the hardware never knew. */
WORD ap_tplay(uint32_t buf, WORD num, WORD scale)
{
    uint8_t  r[TP_RECBYTES];
    uint32_t val;
    WORD     i, ev;

    if (!buf || num <= 0 || tp_mode != TP_OFF)
        return 0;
    if (scale <= 0)
        scale = 100;            /* the Compendium's 1..10000; 0 would divide */
    tp_mode = TP_PLAY;
    tp_key = 0;
    for (i = 0; i < num; i++) {
        far_get(r, buf + (uint32_t)i * TP_RECBYTES, TP_RECBYTES);
        ev = (WORD)(r[0] | (r[1] << 8));
        val = (uint32_t)r[2] | ((uint32_t)r[3] << 8)
            | ((uint32_t)r[4] << 16) | ((uint32_t)r[5] << 24);
        switch (ev) {
        case APPEVNT_TIMER:
            ev_timer(val * 100UL / (uint32_t)scale);
            break;
        case APPEVNT_MOUSE:
            mchange((WORD)(UWORD)val, (WORD)(UWORD)(val >> 16));
            break;
        case APPEVNT_BUTTON:
            b_click((WORD)(UWORD)val);
            break;
        case APPEVNT_KEYBOARD:
            tp_key = (WORD)(UWORD)val;
            kstate = (WORD)(UWORD)(val >> 16);
            break;
        default:
            break;
        }
        /* and let whoever is waiting hear it, which is the dsptch() the
         * ROM makes between every event it plays */
        ev_poll();
    }
    tp_mode = TP_OFF;
    return TRUE;
}

/* ---- the wait ----------------------------------------------------------- */

/* Mouse x, y, button and shift state for the caller; the previous
 * transition's if two arrived before anyone asked. */
static void ev_rets(WORD *rets)
{
    if (mtrans > 1) {
        rets[0] = pr_xrat;
        rets[1] = pr_yrat;
        rets[2] = pr_button;
    } else {
        rets[0] = xrat;
        rets[1] = yrat;
        rets[2] = button;
    }
    kstate = gsx_kstate();
    rets[3] = kstate;
    mtrans = 0;
}

/* Register the button wait.  Nothing happens immediately: ev_multi has
 * already checked the current state (abutton's "already satisfied" case is
 * ev_multi's quick check here, and ev_block's is in ev_button). */
static void bw_register(uint32_t buparm)
{
    uint32_t t = buparm >> 16;

    bw_parm = buparm;
    bw_want = (WORD)t & 0xFF;
    bw_done = FALSE;
    bw_active = TRUE;
    if (bw_want > 1)
        gl_bpend++;
}

/* Cancel it if it is still outstanding (acancel), releasing the
 * multi-click semaphore as the ROM AES does. */
static void bw_cancel(void)
{
    if (bw_active) {
        bw_active = FALSE;
        if (bw_want > 1 && gl_bpend)
            gl_bpend--;
    }
}

/* Wait for any of `flags`:
 *   MU_KEYBD   a key                      prets[4] = the key
 *   MU_BUTTON  the buttons reach buparm   prets[5] = clicks
 *   MU_M1/M2   the pointer enters/leaves pmo1/pmo2
 *   MU_TIMER   tmcount ms have passed
 *   MU_MESAG   a message is in the queue; it is copied to mebuff
 * Returns the flags of what happened.  ev_multi adds the pointer and
 * shift state in prets[0..3]; ev_block's callers do their own ev_rets, and
 * must see mtrans as the wait left it. */
static WORD ev_wait(WORD flags, const MOBLK *pmo1, const MOBLK *pmo2,
                    uint32_t tmcount, uint32_t buparm, WORD *mebuff,
                    WORD *prets)
{
    WORD what = 0, which = 0;
    WORD k;
    uint32_t t0 = 0, twant = 0;
    /* What this process was already parked on, because THIS WAIT MAY BE
     * NESTED INSIDE IT.  The control manager runs as a call inside the
     * application's wait (docs/phase8.md) and the menu and the gadgets
     * wait again in there, on the same process; a nested wait that ZEROED
     * p_evwait on its way out would leave the outer wait invisible to
     * proc_ready, and the scheduler would never give anybody else a turn
     * again.  It is the same save-and-restore ct_run already does around
     * the one button-wait slot, for the same reason, and test-m28 found
     * it the same way: an accessory stopped being scheduled the moment
     * the Desk menu had been pulled down once. */
    WORD     s_evwait = rlr->p_evwait;
    uint32_t s_tdead = rlr->p_tdead;

    /* bring the state up to date (chkkbd + forker) */
    ev_poll();

    /* quick checks: anything already there?  The input ones only for the
     * mouse's owner. */
    if (ct_mine()) {
        if ((flags & MU_KEYBD) && ev_getkey(&k)) {
            prets[4] = k;
            what |= MU_KEYBD;
        }
        if (flags & MU_BUTTON) {
            if (mtrans > 1 && downorup(pr_button, buparm)) {
                what |= MU_BUTTON;
                prets[5] = pr_mclick;
            } else if (downorup(button, buparm)) {
                what |= MU_BUTTON;
                prets[5] = mclick;
            }
        }
        if ((flags & MU_M1) && in_mrect(pmo1))
            what |= MU_M1;
        if ((flags & MU_M2) && in_mrect(pmo2))
            what |= MU_M2;
    }
    if ((flags & MU_TIMER) && tmcount == 0)
        what |= MU_TIMER;
    if ((flags & MU_MESAG) && mq_get(mebuff))
        what |= MU_MESAG;

    if (what == 0) {
        /* nothing yet: register and wait */
        if (flags & MU_BUTTON)
            bw_register(buparm);
        if (flags & MU_TIMER) {
            if (tmcount < (uint32_t)gl_ticktime)
                twant = 1;
            else
                twant = tmcount / (uint32_t)gl_ticktime;
            t0 = gl_ticks;
        }
        /* What this process is parked on, for proc_ready() to test from
         * another one's poll (src/aes/proc.c).  Only the two conditions
         * that do not depend on who owns the mouse are recorded: a
         * message, and a deadline. */
        rlr->p_evwait = flags;
        rlr->p_tdead = t0 + twant;
        /* THE MOUSE GOES BACK when an accessory stops asking for it: a
         * wait with none of the input events in it is an accessory with
         * nothing on the screen, which is the point at which the donor's
         * ownership -- recomputed from the window under the pointer --
         * would have handed it back anyway.  The full rule needs a window
         * to have an owner, which is a later milestone; this is the half
         * of it that an accessory without a window needs, and without it
         * an accessory that finishes a dialog keeps the mouse for ever. */
        if (rlr == proc_input && rlr != proc_app
            && !(flags & (MU_KEYBD | MU_BUTTON | MU_M1 | MU_M2)))
            proc_input = proc_app;
        for (;;) {
            ev_poll();
            if (ct_mine()) {
                if ((flags & MU_KEYBD) && ev_getkey(&k)) {
                    prets[4] = k;
                    which |= MU_KEYBD;
                }
                if ((flags & MU_BUTTON) && bw_done) {
                    prets[5] = bw_clicks;
                    which |= MU_BUTTON;
                }
                if ((flags & MU_M1) && in_mrect(pmo1))
                    which |= MU_M1;
                if ((flags & MU_M2) && in_mrect(pmo2))
                    which |= MU_M2;
            }
            if ((flags & MU_TIMER) && (gl_ticks - t0) >= twant)
                which |= MU_TIMER;
            if ((flags & MU_MESAG) && mq_get(mebuff))
                which |= MU_MESAG;
            if (which)
                break;
        }
        bw_cancel();
        what = which;
    }
    rlr->p_evwait = s_evwait;
    rlr->p_tdead = s_tdead;
    return what;
}

WORD ev_multi(WORD flags, const MOBLK *pmo1, const MOBLK *pmo2,
              uint32_t tmcount, uint32_t buparm, WORD *mebuff, WORD *prets)
{
    WORD what;

    what = ev_wait(flags, pmo1, pmo2, tmcount, buparm, mebuff, prets);
    ev_rets(prets);
    return what;
}

/* Sleep for `ticks` ticks; none means one (adelay).  Unlike ev_multi's
 * timer, which answers at once for a count of zero, a plain evnt_timer(0)
 * always gives the machine one tick.
 *
 * The count starts at the call, as ev_wait's does: the poll comes first,
 * so the ticks the VDI has been keeping since the last poll -- frames the
 * application spent drawing, or idle, before it asked -- are delivered to
 * the delays that want real time (b_delay) and not to this wait.  Under
 * the interrupt regime that backlog is every frame since the last poll,
 * where the polled regime could hand over at most one. */
static void ev_wait_ticks(uint32_t ticks)
{
    uint32_t t0, s_tdead;
    WORD     s_evwait;

    ev_poll();
    t0 = gl_ticks;
    if (ticks == 0)
        ticks = 1;
    s_evwait = rlr->p_evwait;               /* see ev_wait: it may be nested */
    s_tdead = rlr->p_tdead;
    rlr->p_evwait = MU_TIMER;
    rlr->p_tdead = t0 + ticks;
    do
        ev_poll();
    while ((gl_ticks - t0) < ticks);
    rlr->p_evwait = s_evwait;
    rlr->p_tdead = s_tdead;
}

/* One event, the way ev_block does it: the immediate cases differ a little
 * from ev_multi's (abutton answers 1 for an already-satisfied wait, amouse
 * 0), and evnt_timer/evnt_button/evnt_mouse are specified in those terms. */
WORD ev_block(WORD code, uint32_t lvalue)
{
    WORD rets[6];
    WORD r;

    switch (code) {
    case MU_KEYBD:
        ev_poll();
        for (;;) {
            if (ct_mine() && ev_getkey(&r))
                return r;
            ev_poll();
        }
    case MU_BUTTON:
        ev_poll();
        if (ct_mine() && downorup(button, lvalue))
            return 1;
        bw_register(lvalue);
        do
            ev_poll();
        while (!bw_done);
        return bw_clicks;
    case MU_M1:
    case MU_M2:
        ev_wait(code, (const MOBLK *)(uint16_t)lvalue,
                (const MOBLK *)(uint16_t)lvalue, 0, 0, 0, rets);
        return 0;
    case MU_TIMER:
        ev_wait_ticks(lvalue);      /* already in ticks */
        return 0;
    default:
        return 0;
    }
}

WORD ev_keybd(void)
{
    return ev_block(MU_KEYBD, 0);
}

/* A key without waiting for one: a poll, then the two checks ev_wait
 * makes -- the input is the running process's to see, and a key is
 * there -- with no wait registered.  GEMDOS's console asks this for
 * Cconis and Crawio (src/sys/con.c). */
WORD ev_keyq(WORD *pkey)
{
    ev_poll();
    return (WORD)(ct_mine() && ev_getkey(pkey));
}

WORD ev_button(WORD clicks, UWORD mask, UWORD state, WORD *rets)
{
    WORD ret = ev_block(MU_BUTTON, combine_cms(clicks, mask, state));
    ev_rets(rets);
    return ret;
}

WORD ev_mouse(const MOBLK *pmo, WORD *rets)
{
    ev_block(MU_M1, (uint32_t)(uint16_t)pmo);
    ev_rets(rets);
    rets[2] = button;               /* always the current button state */
    return TRUE;
}

WORD ev_timer(uint32_t count)
{
    uint32_t ticks;

    if (count < (uint32_t)gl_ticktime)
        ticks = 0;
    else
        ticks = count / (uint32_t)gl_ticktime;
    ev_wait_ticks(ticks);
    return TRUE;
}
