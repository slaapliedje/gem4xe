/* c6_ctx.c -- step 4d of docs/6502.md: the context switch on a stock 6502,
 * on its own, before the AES depends on it.  test-m27's runner
 * (src/m27_ctx.c), on the 6502's two stacks and its banks.
 *
 * Two contexts take turns with the root.  Their programs are in banks of
 * their own (src/c6_procs.c: proc_a in `cxa`, proc_b in `cxb`), so every
 * switch leaves one bank and must come back to another, and a context
 * resumed in the wrong one would run the middle of the other's code.
 * The claims, as test-m27's:
 *
 *   THE TURNS HAPPEN IN THE ORDER ASKED FOR: who ran, and the bank mapped
 *   when it did (b6_cur), in arrays the gate reads.
 *
 *   A FRAME SURVIVES A SWITCH FROM UNDERNEATH IT: proc_a recurses six
 *   frames -- its locals in the compiler's registers, which each call
 *   saves on the C stack -- yields from the deepest, and checks every
 *   level on the way out.  A copy short by a byte, of either stack, or
 *   a register file not carried, fails it.
 *
 * STATUS at $0600: 'C' '6' as it starts, 'K' at $0602 when done, an error
 * there instead ($FF no far memory, $FE no park buffer, $FD the register
 * file outgrew what a switch carries); $0603 how far it got.  The rest
 * the gate reads by symbol (build/c6.map).
 */
#include "portab.h"
#include <stdint.h>
#include "sys/ctx.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"

#define STATUS ((volatile unsigned char *)0x0600)

#define ROUNDS  5
#define DEEP    6

extern uint8_t b6_cur, b6_count;
uint16_t ctx_s_now(void);      /* src/sys6502/ctx6502.s: page-1 S */

int16_t proc_a(void);           /* src/c6_procs.c, bank cxa */
int16_t proc_b(void);           /* src/c6_procs.c, bank cxb */

uint16_t seq[32];               /* who ran: 1 and 2 the contexts, 0 the root */
uint8_t  seqbank[32];           /* ...and the bank mapped when it did */
uint16_t nseq;
uint16_t deep_put[DEEP], deep_got[DEEP];
uint16_t deep_bad;
uint16_t rounds_a, rounds_b;
uint8_t  min_s = 0xFF;          /* the lowest page-1 S a note saw */

CTX c_root, c_a, c_b;

/* Resident: called from both banks. */
void note(uint16_t who)
{
    uint8_t s = (uint8_t)ctx_s_now();

    if (s < min_s)
        min_s = s;
    if (nseq < 32) {
        seqbank[nseq] = b6_cur;
        seq[nseq++] = who;
    }
}

int main(void)
{
    STATUS[0] = 'C';
    STATUS[1] = '6';
    STATUS[2] = 0;
    STATUS[8] = b6_count;

    farmem_probe();
    STATUS[9] = (unsigned char)farmem.banks;
    if (farmem.kind == FARMEM_NONE) {
        STATUS[2] = 0xFF;
        for (;;)
            ;
    }
    if (!ctx_regs_ok()) {
        STATUS[2] = 0xFD;
        for (;;)
            ;
    }
    STATUS[3] = '1';
    if (!ctx_make(&c_root, 0)) {
        STATUS[2] = 0xFE;
        for (;;)
            ;
    }
    ctx_init(&c_root);
    if (!ctx_make(&c_a, (uint32_t)(uint16_t)proc_a) ||
        !ctx_make(&c_b, (uint32_t)(uint16_t)proc_b)) {
        STATUS[2] = 0xFE;
        for (;;)
            ;
    }
    STATUS[3] = '2';
    note(0);
    ctx_switch(&c_a);       /* back when proc_a returns */
    note(0);
    STATUS[3] = '3';
    STATUS[2] = 'K';
    for (;;)
        ;
}
