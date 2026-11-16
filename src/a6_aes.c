/* a6_aes.c -- step 4c of docs/6502.md: the AES started on a stock 6502,
 * on one process, and its window manager and menu bar drawn.
 *
 * The VDI and its ANTIC device start as in src/v6_vdi.c.  Then the AES as
 * src/gem.c starts it, less what a single process with no input needs:
 * the process records (src/aes/proc.c, a static store here, as test-m25's
 * runner has them), gsx_start, ev_init, wm_init, mn_init.  The context
 * is made and marked as src/gem.c does (src/sys6502/ctx6502.c, step 4d),
 * and never switched away from: there is one process.  Then
 * src/a6_tree.c (banked) makes the calls the gate holds to the model.
 *
 * main is only what must be resident: the context made in the frame
 * every later switch parks from below (ctx_init takes the caller's
 * stack), and the wait.  The rest of the start is in a6_tree.c's bank,
 * because resident memory had not the room for cc6502's corrected
 * multiply (src/sys6502/mul6502.s, step 4e).
 *
 * STATUS at $0600: 'A' '6' as it starts, 'K' at $0602 when done, how far
 * it got at $0603; the banks found at $0608, the far banks at $0609;
 * a6_tree's at $065C-$0661 (src/a6_tree.c).  1 at $0606 starts the
 * event loop (src/a6_evt.c, step 4e), which says so at $0607.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"           /* farmem_probe */
#include "aes/aes.h"
#include "aes/proc.h"

void a6_boot(void);                     /* src/a6_tree.c, banked: */
void a6_aes_up(void);                   /* ...the start, in two halves */
void a6_events(void);                   /* src/a6_evt.c, banked */

#define STATUS ((volatile unsigned char *)0x0600)

extern unsigned char b6_count;

int main(void)
{
    a6_boot();                          /* the VDI up, the records made */
    ctx_init(&proc_app->p_ctx);
    a6_aes_up();                        /* the AES started, its screen drawn */

    STATUS[2] = 'K';
    /* test-a6 compares the screen as it is now; test-e6 says go, and
     * the handlers, the pointer and the event loop start (step 4e) */
    while (STATUS[6] != 1)
        ;
    a6_events();                        /* never returns */
    for (;;)
        ;
}
