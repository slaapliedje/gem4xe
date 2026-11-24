/* i6_irq.c -- step 4d of docs/6502.md: the interrupt handlers on a stock
 * 6502 (src/sys6502/irq6502.s, irq6502.c), on their own.  test-m10's
 * checks (tests/emu/m10_irq.py), less the ROM copy a 6502 does not need.
 *
 * The runner measures how fast its own loop turns in a frame with the OS's
 * interrupts only, installs gem4xe's, selects the CX80 trak-ball through
 * the VDI's own pointer layer (src/vdi/pointer.c, banked), measures again,
 * and busy-waits polling nothing: what the gate sees counted, the handlers
 * counted.  Asked to (1 at $0604), it removes them and says so ('X' at
 * $0605), and the gate checks the OS has its vectors and its keyboard back.
 *
 * STATUS at $0600: 'I' '6' as it starts, 'R' at $0602 once installed and
 * measured.  The rest the gate reads by symbol (build/i6.map).
 */
#include "portab.h"
#include <stdint.h>
#include "sys/irq.h"
#include "vdi/vdidev.h"
#include "vdi/pointer.h"

#define STATUS  ((volatile unsigned char *)0x0600)
#define RTCLOK2 (*(volatile uint8_t *)0x0014)   /* the OS's frame count, low */

/* pointer.c clamps to the screen's size, off `vdev`; this is the size and
 * nothing else (no device is opened here). */
static const VDIDEV i6_dev = { .w = 320, .h = 192 };
const VDIDEV FAR_816 *vdev = &i6_dev;

uint16_t turns_os, turns_gem;   /* loop turns in a frame, before and after */

/* Turns of a small loop over `frames` frames of the OS's own clock, per
 * frame.  RTCLOK is read into a word: spinning on a byte is B16's shape on
 * the 65C816 and costs nothing to avoid here. */
static uint16_t turns(uint8_t frames)
{
    uint16_t n = 0;
    uint16_t t0, t;

    t0 = RTCLOK2;
    do {
        t = RTCLOK2;
    } while (t == t0);              /* to a frame's start */
    t0 = t;
    do {
        n++;
        t = RTCLOK2;
    } while ((uint8_t)(t - t0) < frames);
    return (uint16_t)(n / frames);
}

int main(void)
{
    STATUS[0] = 'I';
    STATUS[1] = '6';
    STATUS[2] = 0;
    STATUS[4] = 0;
    STATUS[5] = 0;

    turns_os = turns(50);
    irq_install();
    ptr_init(PTR_TRAKBALL, 100, 100);
    turns_gem = turns(50);
    STATUS[2] = 'R';

    for (;;) {
        if (STATUS[4] == 1) {
            STATUS[4] = 0;
            irq_remove();
            STATUS[5] = 'X';
        }
        if (STATUS[4] == 2) {           /* an Amiga mouse: its x pair is */
            STATUS[4] = 0;              /* right and down, which a stick's */
            ptr_init(PTR_AMIGA_MOUSE, 100, 100);    /* nine states reach */
            STATUS[5] = 'M';
        }
    }
}
