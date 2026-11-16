/* irq6502.c -- the interrupt regime on a stock 6502 (docs/6502.md, step
 * 4d): src/sys/irq.c's job, without its problem.
 *
 * The 65C816 needs native-mode vectors the OS ROM never filled, and copies
 * the ROM under itself to get them (src/sys/irq.h).  A 6502 takes the ROM's
 * own vectors, and the OS stays: CIO and the DOS run beside GEM.  So the
 * handlers (src/sys6502/irq6502.s) go into the OS's RAM vectors -- the
 * immediate VBI's through SETVBV, as the OS asks; the IRQ's with
 * interrupts held -- and hand on what is not theirs.  irq.how says so:
 * IRQ_OS_CHAINED, and the VDI's consumers ask only that it is not
 * IRQ_OFF.
 *
 * THE SAMPLER'S RATE.  The 65C816 at 20 MHz samples the pointer ~4,000
 * times a second (TIMER_DIV 15); src/sys/irq.c's own measurement says a
 * 1.79 MHz CPU cannot pay that, and grows the divisor in proportion: to
 * 127 for that CPU.  A stock 6502 is it, so the divisor is fixed at 127,
 * ~500 Hz.  Measured (tests/emu/i6_irq.py): at 63, ~1 kHz, the handler's
 * ~200 cycles a time took 17.6% of the machine, ANTIC's DMA and all.  The
 * handler also skips the decode when the port's lines are as they were,
 * which is every sample while the pointer is still.
 *
 * THE KEYBOARD is GEM's while this is installed: the handler takes every
 * key before the OS's dispatch sees it, so CH never fills and E: would
 * wait for ever.  Nothing of GEM's reads E: (and irq_remove gives the
 * keyboard back before a program that would).  The OS's attract mode
 * counts from its last key, which it never sees: the VBI handler holds
 * ATRACT at zero.
 *
 * The handlers' state is defined here, with src/sys/irq.h's names.  Not
 * yet: irq_clock, which nothing on the 6502 calls before GEMDOS does.
 */
#include "portab.h"
#include "sys/irq.h"

IRQ_INFO irq;
volatile uint16_t irq_frames;
volatile uint32_t irq_timer;
volatile uint16_t irq_qlo, irq_qhi;
volatile uint8_t  irq_kb[8];
volatile uint8_t  irq_kb_head, irq_kb_tail, irq_kb_count;
volatile uint8_t  irq_tq[4], irq_tq_head, irq_tq_tail;
volatile uint8_t  irq_fault;
uint8_t  irq_ptr_on;
uint8_t  irq_plo[16], irq_phi[16];
signed char irq_qtab[16];
uint8_t  irq_prev_lo, irq_prev_hi;
uint8_t  irq_pend;
uint8_t  irq_tmp[2];                /* [0] the IRQ handler's, [1] the VBI's */
uint8_t  irq6_last = 0xFF;          /* the port's lines at the last sample */
uint8_t  irq_cio_swap;              /* nothing to swap around CIO here */

/* src/sys6502/irq6502.s */
void irq6_hook(void);
void irq6_unhook(void);

#define POKMSK  (*(volatile uint8_t *)0x0010)
#define IRQEN   (*(volatile uint8_t *)0xD20E)
#define AUDF1   (*(volatile uint8_t *)0xD200)
#define AUDC1   (*(volatile uint8_t *)0xD201)
#define AUDCTL  (*(volatile uint8_t *)0xD208)
#define STIMER  (*(volatile uint8_t *)0xD209)
#define PAL     (*(volatile uint8_t *)0xD014)

#define IRQ_TIMER1  0x01
#define TIMER_DIV6  127

uint8_t irq_install(void)
{
    if (irq.how != IRQ_OFF)
        return 1;
    irq.fail = IRQ_FAIL_NONE;
    irq.pal = (uint8_t)((PAL & 0x0E) == 0);
    irq.timer_div = TIMER_DIV6;
    irq.speed = 0;
    irq_kb_head = irq_kb_tail = 0;
    irq_tq_head = irq_tq_tail = 0;

    /* timer 1 from POKEY's 64 kHz clock, silent; the serial channels (3
     * and 4) and their AUDCTL bits are SIO's, which sets its own around
     * every transfer and leaves 64 kHz and channel 1 alone */
    AUDCTL = 0;
    AUDC1 = 0;
    AUDF1 = irq.timer_div;
    irq6_hook();                    /* the vectors, then the timer's latch:
                                     * irq6_hook arms POKMSK and IRQEN */
    STIMER = 0;
    irq.how = IRQ_OS_CHAINED;
    return 1;
}

void irq_remove(void)
{
    if (irq.how == IRQ_OFF)
        return;
    irq6_unhook();                  /* timer 1 off, the vectors put back */
    irq.how = IRQ_OFF;
}
