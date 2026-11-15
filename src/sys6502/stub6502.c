/* stub6502.c -- what the 6502 VDI links against before it exists here.
 *
 * Step 1 of docs/6502.md is the VDI and its ANTIC device, banked, drawing
 * on a stock 6502.  The VDI also reaches for things the steps after it
 * bring: far memory (step 3), CIO for a loaded face, the interrupt
 * handler's keyboard queue, the printer device, the process context.
 * (Far memory is real since step 3b: src/sys6502/farmem6502.c.)  Each
 * is answered here the way the VDI already copes with its absence: no
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
#include "aes/aes.h"
#include "sys/gemdos.h"

/* ---- GEMDOS, for the object library (step 3c) ------------------------
 * objc.c's desktop-icon call keeps a GEMDOS block; it is not here, so the
 * keep fails and objc.c gives the icon back, as it does when GEMDOS
 * refuses it.  (wind.c's w_look and gl_rzero, which a program without
 * the window manager needs: src/sys6502/v6stub.c.) */
int16_t gd_keep(int32_t a)  { (void)a; return 0; }
void    gd_unkeep(int32_t a) { (void)a; }

/* A stub that must not be reached: its letter at $0604, and stop -- the
 * gate names it rather than chasing what ran after. */
static void b6_unreached(char what)
{
    *(volatile char *)0x0604 = what;
    for (;;)
        ;
}

/* ---- the context switch: step 4d (src/sys/ctx.s on the 65C816) --------
 * Step 4c runs one process and never parks it, so a context is made and
 * marked running, and a switch is never asked for. */
int16_t ctx_make(CTX *c, uint32_t entry) { (void)c; (void)entry; return 1; }
void    ctx_init(CTX *first) { ctx_cur = first; }
void    ctx_switch(CTX *to) { (void)to; b6_unreached('S'); }

/* ---- the shell (src/aes/shel.c): not on the 6502 yet ------------------
 * The Desk menu's list of programs and the switch key: one program, and
 * nothing to switch to.  A request to switch must not come. */
void     sh_hotkey(void) {}
WORD     sh_nprogs(void) { return 0; }
uint32_t sh_prog(WORD i, char *text) { (void)i; text[0] = 0; return 0; }
void     sh_request(uint32_t e) { (void)e; b6_unreached('R'); }

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
const VDIDEV FAR_816 vdev_print = { 0 };     /* initialised: with the code, not in RAM */

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
