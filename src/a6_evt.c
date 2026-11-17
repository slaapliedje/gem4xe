/* a6_evt.c -- step 4e of docs/6502.md: the input poll and the event loop
 * on a stock 6502, on one process.  Called by src/a6_aes.c once the
 * screen step 4c draws is up and the gate says go; banked.
 *
 * The interrupt handlers are in (src/sys6502/irq6502.s and .c, step 4d;
 * src/a6_tree.c's a6_aes_up installs them before ev_init), the pointer is the CX80 trak-ball through the VDI's pointer layer, and
 * then an application's loop: evnt_multi for a key, a click and a
 * message, every event it answers filed in a6_log, and the two messages
 * an application must act on acted on -- MN_SELECTED (the title put back,
 * menu_tnormal's call) and WM_CLOSED (the window closed).  Everything
 * between -- the poll, the control manager dropping a menu and tracking
 * it, the close box, the double-click count, the turn proc_yield offers
 * and nobody takes -- is the AES's own code, as on the 65C816.
 *
 * And what every application does that the AES does not: the pointer on
 * and an arrow, as src/aes/shel.c's sh_main gives each program (there is
 * no shell here); and WM_REDRAW answered -- the AES draws a window's frame
 * and the application its inside, here a white one, a piece of the
 * window's rectangle list at a time.  Without it a window's inside keeps
 * whatever was on the screen before: what a closed window left over it.
 *
 * a6_log: A6_LOG records of A6_REC words, the n-th at n % A6_LOG, n in
 * a6_nlog (build/a6.map): what ev_multi answered, the pointer, its
 * buttons and the shift state, the key, the clicks, and the message's
 * words 0, 3 and 4.  $0607 is 'L' once the loop runs; $060A is 1 while
 * it closes a window and 2 when it has.
 *
 * AND A SECOND PROCESS (step 4f): a6_acc, an accessory built in, with a
 * process record, a queue and a context of its own (src/sys6502/
 * ctx6502.c), started as src/aes/shel.c's sh_ldacc starts one -- the
 * first turn runs it until it parks in its first evnt_multi.  It waits on
 * a message and a timer: every tick it counts (a6_acc_ticks), so turns
 * are reaching it while the application sits in its own wait; a key P to
 * the application sends it A6_PING, and it answers A6_PONG with the ping's
 * number and the pid the AES says is running (rlr) -- 1, its own.  $060B
 * is 'P' once it has parked.
 *
 * AND A PROGRAM IN A BANK OF ITS OWN (step 5a), when $060C is 1 at the
 * go: read from the disk (step 5b), D1:P6PROG.G6A, into the first
 * program slot -- far bank 1, piece 0 (src/sys6502/farmem6502.c) -- and,
 * if its header says it is one (src/app/crt6502.s), started as a process
 * as a6_acc is, its entry the resident veneer gate6502.s keeps for it.
 * It calls the system only through the gate.  $060C is 'R' once its
 * first turn is over, 'H' if the slot held no program; $060D is the
 * read's CIO status (1: all of it) and $060E-F how many bytes came.
 */
#include "portab.h"
#include "aes/aes.h"
#include "sys/irq.h"
#include "vdi/pointer.h"
#include "aes/proc.h"
#include "sys/farmem.h"
#include "sys/cio.h"

#define STATUS ((volatile unsigned char *)0x0600)

#define A6_LOG  8
#define A6_REC  10
WORD     a6_log[A6_LOG][A6_REC];        /* resident: the gate reads it */
uint16_t a6_nlog;

#define A6_PING 0x4136                  /* the application to a6_acc */
#define A6_PONG 0x4137                  /* ...and its answer */
#define A6_TICK 100                     /* a6_acc's timer, ms */
#define KEY_P   0x70                    /* the application's 'p' */
uint16_t a6_acc_ticks, a6_acc_pings;    /* resident: the gate reads them */
WORD     a6_acc_got[4];                 /* the last ping: 0, 1, 3, its pid */
static SECTION("zwin") WORD acc_queue[ACC_MSGS * 8];
static WORD a6_pings;                   /* pings the application sent */
static WORD prog_queue[ACC_MSGS * 8];   /* the program's (step 5a) */
extern uint8_t p6_ven[];                /* src/sys6502/gate6502.s */
extern const uint8_t b6_prog_bank;      /* src/sys6502/farmem6502.c */

/* The message, with msg[1] the sender's pid as appl_write fills it. */
static void send(PROC *to, WORD type, WORD w3, WORD w4)
{
    WORD m[8];

    m[0] = type;
    m[1] = proc_pid(rlr);
    m[2] = 0;
    m[3] = w3;
    m[4] = w4;
    m[5] = m[6] = m[7] = 0;
    mq_put(to, m);
}

/* The second process: its whole life is this loop.  Its address is taken,
 * so bankasm.py gives it a resident veneer, which is what ctx_make's
 * entry must be: the first switch jumps there with any bank in. */
static int16_t a6_acc(void)
{
    static const MOBLK none = { 0, 0, 0, 0, 0 };
    WORD msg[8], rets[6], which;

    for (;;) {
        which = ev_multi(MU_MESAG | MU_TIMER, &none, &none, A6_TICK, 0, msg, rets);
        if (which & MU_TIMER)
            a6_acc_ticks++;
        if ((which & MU_MESAG) && msg[0] == A6_PING) {
            a6_acc_pings++;
            a6_acc_got[0] = msg[0];
            a6_acc_got[1] = msg[1];
            a6_acc_got[2] = msg[3];
            a6_acc_got[3] = proc_pid(rlr);
            send(proc_of(msg[1]), A6_PONG, msg[3], proc_pid(rlr));
        }
    }
}

/* sh_ldacc's start, less the file: a record, a context, the first turn. */
static void acc_start(void)
{
    PROC *p = proc_new(acc_queue, ACC_MSGS);

    if (!p)
        return;
    if (!ctx_make(&p->p_ctx, (uint32_t)(uint16_t)a6_acc)) {
        proc_drop(p);
        return;
    }
    proc_name(p, "A6ACC");
    ctx_switch(&p->p_ctx);              /* runs until it parks */
    p->p_stat = P_LIVE;
    STATUS[11] = 'P';
}

/* The program read into the first slot: a .G6A is the bank's bytes from
 * $4000, header first (tools/bsp6502/mkxex6502.py --g6a), a piece at a
 * time through a buffer outside the window -- where CIO and a DOS that
 * banks may write it (src/sys6502/cio6502.s) -- and on into the slot.
 * CIO_OK when the whole file came and fitted. */
#define P6_SLOT 0x10000UL               /* far bank 1, piece 0 */
#define P6_FILE "D1:P6PROG.G6A"
#define P6_MAX  0x4000u                 /* one bank */
static SECTION("bounce") uint8_t p6_buf[256];

static uint8_t prog_load(void)
{
    int16_t io = cio_open(P6_FILE, CIO_A_READ, 0);
    uint16_t at = 0, got;
    uint8_t st;

    if (io < 0) {
        io = -io;
        st = (uint8_t)io;
        return st;
    }
    do {
        got = 0;
        st = cio_read(io, p6_buf, sizeof p6_buf, &got);
        if (got > P6_MAX - at) {
            st = CIO_E_TRUNC;           /* more than a bank */
            break;
        }
        far_put(P6_SLOT + at, p6_buf, got);
        at += got;
    } while (st == CIO_OK);
    cio_close(io);
    STATUS[14] = (unsigned char)at;
    STATUS[15] = (unsigned char)(at >> 8);
    return st == CIO_E_EOF ? CIO_OK : st;
}

/* The program in the first slot, if there is one: a process of its own,
 * whose first turn runs it to its first wait. */
static void prog_start(void)
{
    PROC *p;
    uint8_t st = prog_load();

    STATUS[13] = st;
    if (st != CIO_OK || far_rd16(P6_SLOT) != 0x3647 || far_read8(P6_SLOT + 2) != 1) {
        STATUS[12] = 'H';               /* "G6", format 1: none */
        return;
    }
    p6_ven[5] = b6_prog_bank;           /* its veneer's bank byte */
    p = proc_new(prog_queue, ACC_MSGS);
    if (!p)
        return;
    if (!ctx_make(&p->p_ctx, (uint32_t)(uint16_t)p6_ven)) {
        proc_drop(p);
        return;
    }
    proc_name(p, "P6PROG");
    ctx_switch(&p->p_ctx);
    p->p_stat = P_LIVE;
    STATUS[12] = 'R';
}

/* The inside of window wh, white, where it shows inside *area. */
static void redraw(WORD wh, const GRECT *area)
{
    WORD w[4];
    GRECT r;

    gsx_moff();
    wm_get(wh, WF_FIRSTXYWH, w, 0);
    while (w[2] && w[3]) {
        r.g_x = w[0];
        r.g_y = w[1];
        r.g_w = w[2];
        r.g_h = w[3];
        if (rc_intersect(area, &r)) {
            gsx_sclip(&r);
            gr_rect(WHITE, IP_HOLLOW, &r);
        }
        wm_get(wh, WF_NEXTXYWH, w, 0);
    }
    gsx_sclip(&gl_rscreen);
    gsx_mon();
}

void a6_events(void)
{
    static const MOBLK none = { 0, 0, 0, 0, 0 };
    WORD msg[8], rets[6];
    WORD which, *r, i;
    GRECT area;

    ptr_init(PTR_TRAKBALL, 160, 96);    /* the handlers are in: a6_aes_up */
    ratinit();                          /* the pointer on, and an arrow */
    gr_mouse(ARROW, 0);
    acc_start();
    if (STATUS[12] == 1)
        prog_start();
    STATUS[7] = 'L';
    for (;;) {
        for (i = 0; i < 8; i++)
            msg[i] = 0;
        rets[4] = rets[5] = 0;
        /* a left press, up to two clicks; any key; any message */
        which = ev_multi(MU_KEYBD | MU_BUTTON | MU_MESAG, &none, &none, 0,
                         combine_cms(2, 1, 1), msg, rets);
        r = a6_log[a6_nlog % A6_LOG];
        r[0] = which;
        for (i = 0; i < 6; i++)
            r[1 + i] = rets[i];
        r[7] = msg[0];
        r[8] = msg[3];
        r[9] = msg[4];
        a6_nlog++;
        if ((which & MU_KEYBD) && (rets[4] & 0xFF) == KEY_P && proc_of(1))
            send(proc_of(1), A6_PING, ++a6_pings, 0);
        if (which & MU_MESAG) {
            if (msg[0] == MN_SELECTED && gl_mntree)
                do_chg(gl_mntree, msg[3], SELECTED, FALSE, TRUE, TRUE);
            else if (msg[0] == WM_REDRAW) {
                area.g_x = msg[4];
                area.g_y = msg[5];
                area.g_w = msg[6];
                area.g_h = msg[7];
                redraw(msg[3], &area);
            } else if (msg[0] == WM_CLOSED)
            {
                STATUS[10] = 1;             /* a close redraws: seconds */
                wm_close(msg[3]);
                STATUS[10] = 2;
            }
        }
    }
}
