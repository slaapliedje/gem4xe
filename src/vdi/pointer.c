/* pointer.c -- pointing-device back ends behind the seam in pointer.h. */
#include "pointer.h"
#include "vdidev.h"          /* the screen's size, from whichever device */
#include "../sys/irq.h"

PTR_STATE ptr_state;
PTR_STATE ptr_seen;

#define PORTA  (*(volatile uint8_t *)0xD300)   /* PIA: joystick 0 in low nibble */
#define TRIG0  (*(volatile uint8_t *)0xD010)   /* GTIA: 0 = pressed             */
#define TRIG1  (*(volatile uint8_t *)0xD011)
#define POT0   (*(volatile uint8_t *)0xD200)
#define POT1   (*(volatile uint8_t *)0xD201)
#define POT(n) (*(volatile uint8_t *)(0xD200 + (n)))
#define TRIG(n) (*(volatile uint8_t *)(0xD010 + (n)))
#define ALLPOT (*(volatile uint8_t *)0xD208)
#define POTGO  (*(volatile uint8_t *)0xD20B)

#define POT_MAX 228     /* POKEY's pot counter tops out here on a real Atari */
/* A quadrature mouse's right button grounds its paddle line: the counter
 * reads ~0 held and ~229 free, so anything low is a press. */
#define PTR_RMB_MAX 64

static uint8_t last_x, last_y;      /* previous line pair per axis (polled) */
static uint16_t last_qlo, last_qhi; /* the IRQ's counters as last consumed  */
static WORD    pot_pending;
/* THE RIGHT BUTTON IS NOT BELIEVED UNTIL ITS LINE HAS BEEN SEEN FREE.  An
 * ST mouse leaves the paddle line open when the button is up, and it
 * counts to ~229.  A switchable ST/Amiga mouse drives it low in either
 * mode, and the line reads "held" from power-on: every menu then waits
 * for a release that never comes (the menu bar takes over only with ALL
 * buttons up, src/aes/menu.c) and a double-click never matches -- a
 * 0.9 tester's report.  A button that has never been up is not a press;
 * the first time it reads free, it is trusted from then on. */
static uint8_t rmb_seen_free;

static uint8_t xem_port;            /* XEM1: joystick port it answered on */

/* Port 2 by default: it is what the Atari world wires a mouse to, and
 * port 1 is reported to interfere with the keyboard.  The 4 kHz sampler
 * (src/sys/irq.s) reads this byte to pick PORTA's nibble. */
uint8_t ptr_port = PTR_PORT_2;

void ptr_setport(WORD port)
{
    ptr_port = (uint8_t)((port == PTR_PORT_1) ? PTR_PORT_1 : PTR_PORT_2);
}
static uint8_t xem_found;
static uint8_t xem_rx, xem_ry;      /* the readings the movement is from */
static uint8_t xem_wheel;           /* previous wheel phase */

/* Classic 2-bit Gray-code quadrature table, indexed by (prev << 2) | now.
 * The four "impossible" entries (a two-step jump, i.e. a missed sample) are 0
 * rather than a guess: on a missed count it is better to drop motion than to
 * invent it in the wrong direction. */
static const signed char qdec[16] = {
     0, +1, -1,  0,
    -1,  0,  0, +1,
    +1,  0,  0, -1,
     0, -1, +1,  0
};

/* Direction-and-pulse, same index, for the CX80 trak-ball: the pair is
 * (direction << 1) | pulse, a count is a pulse edge, and the direction line
 * AS SAMPLED WITH THE EDGE says which way -- high is +, as PORTA reads it.
 * No entry is impossible: a missed pulse is a missed count, not a wrong
 * one. */
static const signed char tbdec[16] = {
     0, -1,  0, +1,
    -1,  0, +1,  0,
     0, -1,  0, +1,
    -1,  0, +1,  0
};

WORD ptr_decode_quad(uint8_t prev, uint8_t now)
{
    return qdec[((prev & 3) << 2) | (now & 3)];
}

WORD ptr_decode_tb(uint8_t prev, uint8_t now)
{
    return tbdec[((prev & 3) << 2) | (now & 3)];
}

/* Which two of PORTA's four lines make each axis's pair, per device, and
 * which table a pair transition goes through.  Written as tables the
 * interrupt handler can index by the raw nibble (src/sys/irq.s), and used
 * by the polled path the same way, so both regimes decode identically.
 *
 * The pair is ordered so that the sequence Altirra's device models emit
 * for +x / +y walks 0, 1, 3, 2 -- i.e. +1 through qdec -- with the port's
 * active-low inversion taken into account (it does not change a
 * quadrature direction; it does flip a direction line):
 *
 *   ST     x: lines 1 (XA) and 0 (XB), pair = b0 << 1 | b1
 *          y: lines 3 (YA) and 2 (YB), pair = b2 << 1 | b3
 *   Amiga  x: lines 3 and 1,           pair = b3 << 1 | b1
 *          y: lines 2 and 0,           pair = b2 << 1 | b0
 *   CX80   x: line 0 direction, line 1 pulse,   pair = b0 << 1 | b1
 *          y: line 2 direction, line 3 pulse,   pair = b2 << 1 | b3
 *
 * That is Altirra's inputcontroller.cpp (kSTTabX/Y, kAMTabX/Y, and the
 * trak-ball's dirBits), not a datasheet; the earlier version of this file
 * had the Amiga axes on the wrong pins and the ST sign inverted against
 * the same model, and called the CX80 quadrature.  The signs have not met
 * hardware; if a real mouse runs backwards, this is the table to flip. */
#define BIT(v, n) (((v) >> (n)) & 1)

WORD ptr_pair(WORD kind, uint8_t nibble, WORD axis)
{
    uint8_t p = (uint8_t)(nibble & 0x0F);
    if (kind == PTR_AMIGA_MOUSE)
        return axis ? (WORD)((BIT(p, 2) << 1) | BIT(p, 0))
                    : (WORD)((BIT(p, 3) << 1) | BIT(p, 1));
    return axis ? (WORD)((BIT(p, 2) << 1) | BIT(p, 3))
                : (WORD)((BIT(p, 0) << 1) | BIT(p, 1));
}

static void lines_select(ptr_kind kind)
{
    uint8_t n;
    const signed char *tab = (kind == PTR_TRAKBALL) ? tbdec : qdec;

    irq_ptr_on = 0;                 /* the handler must not see a half-built table */
    for (n = 0; n < 16; n++) {
        irq_plo[n] = (uint8_t)ptr_pair((WORD)kind, n, 0);
        irq_phi[n] = (uint8_t)ptr_pair((WORD)kind, n, 1);
    }
    for (n = 0; n < 16; n++)
        irq_qtab[n] = tab[n];
    /* Start from the lines as they are now, so the first sample is not
     * counted as a transition from zero. */
    n = (uint8_t)((ptr_port ? (PORTA >> 4) : PORTA) & 0x0F);
    last_x = irq_plo[n];
    last_y = irq_phi[n];
    irq_prev_lo = (uint8_t)(last_x << 2);
    irq_prev_hi = (uint8_t)(last_y << 2);
    last_qlo = irq_qlo;
    last_qhi = irq_qhi;
    if (kind == PTR_ST_MOUSE || kind == PTR_AMIGA_MOUSE || kind == PTR_TRAKBALL)
        irq_ptr_on = 1;
}

static void clamp(void)
{
    if (ptr_state.x < 0) ptr_state.x = 0;
    if (ptr_state.y < 0) ptr_state.y = 0;
    if (ptr_state.x > SCR_W - 1) ptr_state.x = SCR_W - 1;
    if (ptr_state.y > SCR_H - 1) ptr_state.y = SCR_H - 1;
}

/* Copy the record, and copy it again if it moved while being copied.  A
 * writer that lands between two of the reads leaves at least one field
 * changed by the time it is re-read, unless it changed nothing that was
 * read before it -- in which case the copy is the new state anyway. */
void ptr_sample(void)
{
    do {
        ptr_seen.x = ptr_state.x;
        ptr_seen.y = ptr_state.y;
        ptr_seen.buttons = ptr_state.buttons;
        ptr_seen.wheel = ptr_state.wheel;
    } while (ptr_seen.x != ptr_state.x || ptr_seen.y != ptr_state.y
             || ptr_seen.buttons != ptr_state.buttons
             || ptr_seen.wheel != ptr_state.wheel);
    ptr_seen.kind = ptr_state.kind;
}

void ptr_warp(WORD x, WORD y)
{
    ptr_state.x = x;
    ptr_state.y = y;
    clamp();
    ptr_sample();
}

void ptr_init(ptr_kind kind, WORD x, WORD y)
{
    ptr_state.kind = (WORD)kind;
    ptr_state.buttons = 0;
    ptr_state.wheel = 0;
    ptr_warp(x, y);
    lines_select(kind);
    pot_pending = 0;
    rmb_seen_free = 0;
    xem_found = 0;
    xem_wheel = 0;
    if (kind == PTR_TABLET || kind == PTR_XEM1
            || kind == PTR_ST_MOUSE || kind == PTR_AMIGA_MOUSE
            || kind == PTR_TRAKBALL) {
        POTGO = 0;                  /* the absolute devices' position, and
                                     * a quadrature mouse's right button */
        pot_pending = 1;
    }
}

/* Relative devices.  With the interrupt regime up (src/sys/irq.h) the
 * timer handler has been sampling PORTA ~4000 times a second and adding
 * to two counters; this takes the difference since the last poll.  Without
 * it, the one sample a poll gives is decoded here through the same tables
 * -- and loses every transition that happened between polls, which is the
 * classic Atari mouse complaint and why the interrupt exists. */
static void poll_relative(void)
{
    if (irq.how != IRQ_OFF) {
        uint16_t q;
        q = irq_qlo;
        ptr_state.x = (WORD)(ptr_state.x + (WORD)(q - last_qlo));
        last_qlo = q;
        q = irq_qhi;
        ptr_state.y = (WORD)(ptr_state.y + (WORD)(q - last_qhi));
        last_qhi = q;
    } else {
        uint8_t p = (uint8_t)((ptr_port ? (PORTA >> 4) : PORTA) & 0x0F);
        uint8_t qx = irq_plo[p], qy = irq_phi[p];
        ptr_state.x = (WORD)(ptr_state.x + irq_qtab[(last_x << 2) | qx]);
        ptr_state.y = (WORD)(ptr_state.y + irq_qtab[(last_y << 2) | qy]);
        last_x = qx;
        last_y = qy;
    }
    clamp();
    /* Both buttons are this port's.  Left is its trigger; right is its
     * FIRST PADDLE LINE -- POT0 for port 1, POT2 for port 2 -- which the
     * adapter pulls to 0 and leaves near 229 otherwise.  It is not the
     * other port's trigger, which is what this read used to be and which
     * answered a joystick plugged in beside the mouse. */
    /* Bit 1 of the button word IS the cache: the right button keeps its
     * last answer while the paddle scan runs, and bank $00 pays for no
     * variable to hold it. */
    ptr_state.buttons = (WORD)(((TRIG(ptr_port) & 1) ? 0 : 1)
                               | (ptr_state.buttons & 2));
    /* The paddle counts UP through a scan, so reading it mid-scan reads
     * low -- which is indistinguishable from a held button.  Sample it
     * only when the scan has finished, keep the answer until the next
     * one, and start the next immediately.  (Reading it every poll is
     * what made the right button stick down and the desktop unusable.) */
    if (pot_pending && (ALLPOT & (1 << (ptr_port * 2))) != 0)
        return;                     /* still counting: last answer stands */
    {
        WORD held = (WORD)(POT(ptr_port * 2) < PTR_RMB_MAX);
        if (!held)
            rmb_seen_free = 1;
        ptr_state.buttons = (WORD)((ptr_state.buttons & ~2)
                                   | ((held && rmb_seen_free) ? 2 : 0));
    }
    POTGO = 0;
    pot_pending = 1;
}

/* Absolute devices.  POKEY's pot scan takes a full frame in normal mode, so
 * this reads the previous scan's result and immediately starts the next --
 * one position per frame, which is all a GUI pointer needs.
 *
 * The counter tops out around 228, against a 640x240 screen: roughly 2.8
 * screen pixels per step horizontally and about 1:1 vertically.  Good enough
 * to hit a menu item, coarse for drawing.  Callers wanting smooth motion
 * should filter, not scale harder. */
static void poll_absolute(void)
{
    uint16_t px, py;
    if (pot_pending && (ALLPOT & 3) != 0)
        return;                     /* scan still running; keep the old value */
    px = POT0;
    py = POT1;
    if (px > POT_MAX) px = POT_MAX;
    if (py > POT_MAX) py = POT_MAX;
    ptr_state.x = (WORD)(((uint32_t)px * (SCR_W - 1)) / POT_MAX);
    ptr_state.y = (WORD)(((uint32_t)py * (SCR_H - 1)) / POT_MAX);
    clamp();
    ptr_state.buttons = (WORD)(((TRIG0 & 1) ? 0 : 1) | ((TRIG1 & 1) ? 0 : 2));
    POTGO = 0;                      /* start the next scan */
    pot_pending = 1;
}

/* mouSTer in XEM1 mode.  The adapter keeps a 7-bit position counter per
 * axis and presents it on the port's two POT lines, sent as 64..191 so that
 * exactly one of bits 6 and 7 is set: an empty port (the counter runs to
 * 228) or a paddle at either end fails that, which is how the device is
 * found -- both ports are tried until a pair validates.  The left button
 * is the trigger, right and middle are the port's upper two direction
 * lines, and its lower two carry the wheel as plain quadrature.
 *
 * Per the sample driver: a reading is used only if both axes validate; the
 * difference from the last USED reading is taken modulo 128 and halved
 * (the low bit is noise), and a reading that halves to nothing is not
 * taken as the new reference, so a slow drag of one count a frame is not
 * lost but arrives every other frame. */
WORD ptr_xem1_valid(uint8_t pot)
{
    return (WORD)((((pot >> 1) ^ pot) & 0x40) != 0);
}

WORD ptr_decode_xem1(uint8_t ref, uint8_t now)
{
    WORD d = (WORD)((now - ref) & 0x7F);
    if (d & 0x40)
        d -= 128;
    return (WORD)((d < 0) ? -((-d) >> 1) : (d >> 1));
}

static void poll_xem1(void)
{
    uint8_t px, py, pa, q;
    WORD    d;

    if (pot_pending && (ALLPOT & 0x0F) != 0)
        return;                     /* scan still running; keep the old value */
    if (!xem_found) {
        for (q = 0; q < 2; q++) {
            px = POT(q * 2);
            py = POT(q * 2 + 1);
            if (ptr_xem1_valid(px) && ptr_xem1_valid(py)) {
                xem_port = q;
                xem_rx = px;
                xem_ry = py;
                xem_found = 1;
                break;
            }
        }
    } else {
        px = POT(xem_port * 2);
        py = POT(xem_port * 2 + 1);
        if (ptr_xem1_valid(px) && ptr_xem1_valid(py)) {
            d = ptr_decode_xem1(xem_rx, px);
            if (d) {
                ptr_state.x = (WORD)(ptr_state.x + d);
                xem_rx = px;
            }
            d = ptr_decode_xem1(xem_ry, py);
            if (d) {
                ptr_state.y = (WORD)(ptr_state.y + d);
                xem_ry = py;
            }
            clamp();
        }
    }
    if (xem_found) {
        pa = (uint8_t)(PORTA >> (xem_port * 4));
        ptr_state.buttons = (WORD)(((TRIG(xem_port) & 1) ? 0 : 1)
                                   | ((pa & 4) ? 0 : 2)
                                   | ((pa & 8) ? 0 : 4));
        q = (uint8_t)(pa & 3);
        ptr_state.wheel = (WORD)(ptr_state.wheel + ptr_decode_quad(xem_wheel, q));
        xem_wheel = q;
    }
    POTGO = 0;                      /* start the next scan */
    pot_pending = 1;
}

void ptr_poll(void)
{
    switch (ptr_state.kind) {
    case PTR_ST_MOUSE:
    case PTR_AMIGA_MOUSE:
    case PTR_TRAKBALL:
        poll_relative();
        break;
    case PTR_TABLET:
        poll_absolute();
        break;
    case PTR_XEM1:
        poll_xem1();
        break;
    default:
        break;
    }
}
