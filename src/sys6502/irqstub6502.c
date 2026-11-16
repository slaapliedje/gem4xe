/* irqstub6502.c -- the interrupt handlers' state, quiet, for a 6502
 * program that does not install them (V6).  The VDI reads it and
 * src/vdi/pointer.c's tables fill it; with irq.how IRQ_OFF the VDI polls
 * instead and nothing here moves.  A program with the handlers links
 * src/sys6502/irq6502.c, which defines the same names, instead.
 */
#include "portab.h"
#include "sys/irq.h"

IRQ_INFO irq;
volatile uint8_t irq_kb_head, irq_kb_tail, irq_kb_count;
volatile uint8_t irq_kb[8];
volatile uint16_t irq_frames;
volatile uint16_t irq_qlo, irq_qhi;
volatile uint8_t irq_tq[4], irq_tq_head, irq_tq_tail;
uint8_t irq_ptr_on;
uint8_t irq_plo[16], irq_phi[16];
signed char irq_qtab[16];
uint8_t irq_prev_lo, irq_prev_hi;
