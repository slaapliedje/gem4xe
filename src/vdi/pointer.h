/* pointer.h -- the pointing-device seam.
 *
 * Everything above this produces and consumes ONE thing: an absolute screen
 * position plus button state.  Below it sit devices that disagree
 * fundamentally about how position works:
 *
 *   ST mouse, Amiga mouse, CX80 trak-ball   RELATIVE -- quadrature on the
 *                                           joystick direction lines, read
 *                                           through PORTA, deltas integrated
 *   Touch tablet (CX77), KoalaPad           ABSOLUTE -- the port's two pot
 *                                           lines, one position per POKEY
 *                                           pot scan; buttons on its
 *                                           direction lines
 *   mouSTer (USB adapter) in XEM1 mode      RELATIVE, but COUNTED BY THE
 *                                           DEVICE -- 7-bit position
 *                                           counters on the POT lines, so
 *                                           one pot scan per frame is enough
 *
 * GEM's own design already assumes this seam: `vex_motv` hands the AES an
 * absolute position and `v_locator` is a device-independent locator, so
 * nothing above here ever learns which device is fitted.
 *
 * A relative device needs frequent sampling or it loses quadrature counts
 * -- the classic Atari 8-bit mouse complaint -- which means an interrupt.
 * Since Phase 9 there is one: src/sys/irq.h shadows the OS ROM into RAM,
 * fills the 65816's native-mode vectors, and runs a POKEY timer at ~4 kHz
 * that samples PORTA and decodes both axes through tables THIS file fills
 * in per device (ptr_pair, lines_select).  The relative back ends take the
 * counters' difference each poll.  If the interrupt regime could not be
 * installed (irq.how == IRQ_OFF) they fall back to decoding the one
 * sample a poll gives, through the same tables, and lose counts as before.
 * The absolute back ends never needed it: one POT read per frame is
 * enough.  Nor does XEM1, where the adapter does the counting: the host
 * reads a position, not a phase, and a frame's movement is a difference
 * of two readings.  Its one demand is a POTGO at a steady cadence (the
 * sample driver says within ~100 cycles, every frame), which the polling
 * loop only approximates; moving it into the VBI is still to do.
 *
 * XEM1 is decoded from the mouSTer firmware's own sample driver
 * (Mad-Pascal samples/a8/mouSTer/vbl.asm), not from its prose, which calls
 * the readings "relative coordinate changes": the code subtracts the
 * previous reading, so they are counters.  Altirra does not emulate the
 * adapter; the decode is checked against tools/vdiref.py in the compiler's
 * simulator (tests/host/test_pointer.py) and has NOT met the hardware.
 */
#ifndef GEM4XE_POINTER_H
#define GEM4XE_POINTER_H

#include <stdint.h>
#include "vdi.h"

typedef enum {
    PTR_NONE = 0,
    PTR_ST_MOUSE,       /* Atari ST mouse via a joystick-port adapter */
    PTR_AMIGA_MOUSE,    /* same idea, different pin order */
    PTR_TRAKBALL,       /* Atari CX80 trak-ball, in trak-ball mode */
    PTR_CX77,           /* Atari CX77 Touch Tablet, absolute */
    PTR_XEM1,           /* mouSTer, XEM1 mode: probes both ports for it   */
    PTR_KOALA           /* KoalaPad: the CX77's shape, its own readings */
} ptr_kind;

typedef struct {
    WORD x, y;          /* absolute, always clamped to the screen */
    WORD buttons;       /* bit 0 = left, bit 1 = right, bit 2 = middle */
    WORD kind;
    WORD wheel;         /* notches, accumulated; XEM1 only, sign unverified */
} PTR_STATE;

/* ptr_state is the device's record and ptr_seen the copy everything above
 * the seam reads.  They differ because the record can change under a
 * reader: today the test harness rewrites it between frames, later a VBI
 * will, and either can land between a reader's fetch of x and its fetch of
 * y.  The AES then sees a position that never existed -- old x, new y --
 * and answers a rectangle it was never in.  ptr_sample() takes the copy in
 * one piece, so a pass of the input loop sees one instant. */
extern PTR_STATE ptr_state;
extern PTR_STATE ptr_seen;

/* WHICH JOYSTICK PORT the relative devices are on.  Port 2 is the
 * standard: the Atari community wires a mouse there, and port 1 is
 * reported to interfere with the keyboard.  A quadrature device occupies
 * ONE port completely -- its four direction lines are the two axes, its
 * trigger is the left button, and its first paddle line is the right
 * button (0 pressed, ~229 released), which is how the ST-mouse adapter
 * is built and how Altirra models it.  So the port decides every read,
 * not just the direction nibble. */
#define PTR_PORT_1  0
#define PTR_PORT_2  1
/* ONE byte, and the 4 kHz sampler in src/sys/irq.s reads this very
 * variable rather than a copy: two that had to agree would be one too
 * many, and bank $00 has no room for the spare. */
extern uint8_t ptr_port;        /* PTR_PORT_1 or PTR_PORT_2 */
void ptr_setport(WORD port);    /* before ptr_init; the sampler follows */

void ptr_init(ptr_kind kind, WORD x, WORD y);
void ptr_poll(void);            /* refresh ptr_state from the hardware */
void ptr_sample(void);          /* ptr_seen = ptr_state, torn reads retried */
/* The buttons, had the triggers been `trig` (bit 0 TRIG0, bit 1 TRIG1,
 * 1 = pressed) and every other line as it is now; -1 for a device whose
 * buttons are not on the triggers.  What vdi_input_poll replays the
 * vertical blank's trigger ring through (src/sys/irq.h, irq_tq). */
WORD ptr_buttons_at(uint8_t trig);
void ptr_warp(WORD x, WORD y);  /* force a position (vq_mouse / tests)  */

/* Exposed for the device-layer tests, which drive synthetic quadrature rather
 * than relying on the emulator's input system: the two transition tables
 * (Gray-code quadrature; the CX80's direction-and-pulse) and the per-device
 * choice of which two PORTA lines make an axis's pair (axis 0 = x). */
WORD ptr_decode_quad(uint8_t prev, uint8_t now);
WORD ptr_decode_tb(uint8_t prev, uint8_t now);
WORD ptr_pair(WORD kind, uint8_t nibble, WORD axis);

/* THE TWO TABLETS, as Altirra models them (inputcontroller.cpp,
 * ATTabletController; inputmanager.cpp makes the CX77 with (228, invertY)
 * and the KoalaPad with (0, no invert)):
 *
 *   - the position is the port's pot pair, x then y, 0..228;
 *   - with the stylus lifted BOTH read a fixed value -- 228 on the CX77,
 *     0 on the KoalaPad -- which is not a place: the pointer stays where
 *     the stylus left it;
 *   - the CX77's y runs the other way: 228 at the top;
 *   - the buttons are the port's DIRECTION lines, active low, not its
 *     trigger: the stylus button the up line, the pad's left button the
 *     left line, its right button the right line.
 *
 * ptr_decode_tablet: TRUE with *x, *y the screen position when the
 * stylus is down, FALSE (and nothing written) when it is up.
 * ptr_tablet_buttons: the button word from the port's direction nibble.
 * Exposed for the device-layer tests (tests/host/test_pointer.py), which
 * hold them to a model of that controller. */
WORD ptr_decode_tablet(WORD kind, uint8_t px, uint8_t py, WORD *x, WORD *y);
WORD ptr_tablet_buttons(uint8_t nibble);

/* XEM1: a reading is a 7-bit counter sent as 64..191; the movement between
 * two readings is their difference modulo 128, halved (the low bit is
 * noise).  Both exposed for the same reason. */
WORD ptr_xem1_valid(uint8_t pot);
WORD ptr_decode_xem1(uint8_t ref, uint8_t now);

#endif /* GEM4XE_POINTER_H */
