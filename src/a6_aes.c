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
 * STATUS at $0600: 'A' '6' as it starts, 'K' at $0602 when done, how far
 * it got at $0603; the banks found at $0608, the far banks at $0609;
 * a6_tree's at $065C-$0661 (src/a6_tree.c).
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"           /* farmem_probe */
#include "aes/aes.h"
#include "aes/proc.h"

void a6_tree(void);                     /* src/a6_tree.c, banked */

#define STATUS ((volatile unsigned char *)0x0600)

extern unsigned char b6_count;

int main(void)
{
    /* the records with the AES's other window-safe state (zwin, LowRam
     * in tools/bsp6502/a6.scm): HiRam has not the room */
    static SECTION("zwin") char proc_store[PROC_STORE];

    STATUS[0] = 'A';
    STATUS[1] = '6';
    STATUS[2] = 0;
    STATUS[8] = b6_count;

    farmem_probe();
    STATUS[9] = (unsigned char)farmem.banks;
    vdev = &vdev_antic;
    STATUS[3] = '1';
    vdi_font_default();
    vdi_init();
    STATUS[3] = '2';

    proc_init(proc_store);
    ctx_make(&proc_app->p_ctx, 0);
    ctx_init(&proc_app->p_ctx);
    STATUS[3] = '3';
    gsx_start();
    STATUS[3] = '4';
    ev_init();
    STATUS[3] = '5';
    wm_init();
    STATUS[3] = '6';
    mn_init();
    STATUS[3] = '7';
    a6_tree();

    STATUS[2] = 'K';
    for (;;)
        ;
}
