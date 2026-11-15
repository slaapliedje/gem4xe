/* stub6502.c -- what the 6502 VDI links against before it exists here.
 *
 * Step 1 of docs/6502.md is the VDI and its ANTIC device, banked, drawing
 * on a stock 6502.  The VDI also reaches for things the steps after it
 * bring: far memory (step 3), CIO for a loaded face, the interrupt
 * handler's keyboard queue, the printer device, the process context.
 * Each is answered here the way the VDI already copes with its absence:
 * no far memory is a failed allocation, which every caller checks; no
 * keyboard is an empty queue; no printer is a workstation that will not
 * open.  Nothing here pretends to work.
 */
#include "portab.h"
#include "sys/farmem.h"
#include "sys/cio.h"
#include "sys/irq.h"
#include "sys/ctx.h"
#include "vdi/vdi.h"
#include "vdi/vdidev.h"
#include "vdi/print.h"

/* ---- far memory: none yet (step 3) ------------------------------------ */
uint32_t far_alloc(uint32_t bytes)     { (void)bytes; return 0; }
uint32_t far_alloc_top(uint32_t bytes) { (void)bytes; return 0; }
uint16_t far_free(uint32_t addr)       { (void)addr; return 0; }
uint16_t far_keep(uint32_t addr)       { (void)addr; return 0; }
uint32_t far_size(uint32_t addr)       { (void)addr; return 0; }
uint8_t  far_read8(uint32_t addr)      { (void)addr; return 0; }
void     far_write8(uint32_t addr, uint8_t v) { (void)addr; (void)v; }
void     far_get(uint8_t *dst, uint32_t src, uint16_t len) { (void)dst; (void)src; (void)len; }
void     far_put(uint32_t dst, const uint8_t *src, uint16_t len) { (void)dst; (void)src; (void)len; }
void     far_copy(uint32_t dst, uint32_t src, uint16_t len) { (void)dst; (void)src; (void)len; }

/* ---- CIO: a face loaded from a file is refused ------------------------ */
int16_t  cio_open(const char *name, uint8_t aux1, uint8_t aux2)
{
    (void)name; (void)aux1; (void)aux2;
    return -1;
}
uint8_t  cio_read(int16_t iocb, void *buf, uint16_t len, uint16_t *got)
{
    (void)iocb; (void)buf; (void)len;
    *got = 0;
    return 136;                         /* end of file */
}
uint8_t  cio_close(int16_t iocb) { (void)iocb; return 1; }

/* ---- the interrupt handler's state: quiet ----------------------------- */
IRQ_INFO irq;
volatile uint8_t irq_kb_head, irq_kb_tail, irq_kb_count;
CTX *ctx_cur;

/* ---- the printer: none ------------------------------------------------ */
uint8_t FAR *pr_page;
int16_t pr_page_open(void) { return 0; }
void    pr_page_close(void) {}
WORD pr_emit(void) { return 0; }
volatile uint8_t irq_kb[8];

/* The printer's table: a printer workstation is never opened here, and
 * vdi.c only compares against this one's address before it would be. */
const VDIDEV FAR vdev_print;

/* ...and the rest of the handler's variables, which the VDI's timer and
 * pointer code read and pointer.c's tables fill: there, unread, until the
 * 6502 has an interrupt handler of its own. */
volatile uint16_t irq_frames;
volatile uint16_t irq_qlo, irq_qhi;
volatile uint8_t irq_tq[4], irq_tq_head, irq_tq_tail;
uint8_t irq_ptr_on;
uint8_t irq_plo[16], irq_phi[16];
signed char irq_qtab[16];
uint8_t irq_prev_lo, irq_prev_hi;
