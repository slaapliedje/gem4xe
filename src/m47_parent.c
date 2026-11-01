/* test-m47's parent (tests/emu/m47_stack.py), run as the desktop: it
 * runs CHILD.PRG (src/m47_child.c), whose stack runs away, and then makes
 * twenty calls of its own.
 *
 * m47_result: 1 if Pexec came back with the child STOPPED (GEM_STOPPED,
 * -9, src/sys/abi.h), and 2 more if all twenty calls after it came back
 * -- the parent's own floor put back after its child's (src/sys/app.c,
 * app_exec), not the child's left to stop the parent too.  m47_done is
 * the mark that m47_result is written, a value memory does not hold by
 * chance.  It stays running so that its memory is there to read. */
#include "gem.h"

volatile WORD m47_result;
volatile WORD m47_done;
volatile LONG m47_pexec;
volatile LONG m47_big, m47_small;   /* phase 121: a stack asked for */

int main(void)
{
    WORD i, w, h, bw, bh, calls = 0, r = 0;

    appl_init();
    m47_pexec = Pexec(0, "CHILD.PRG", "\0", 0);
    if (m47_pexec == -9)
        r |= 1;
    m47_big = Pexec(0, "BIG.PRG", "\0", 0);       /* 7: it ran to its end */
    m47_small = Pexec(0, "SMALL.PRG", "\0", 0);   /* -9: stopped */
    for (i = 0; i < 20; i++) {
        graf_handle(&w, &h, &bw, &bh);
        calls++;
    }
    if (calls == 20)
        r |= 2;
    m47_result = r;
    m47_done = 0x4D47;                  /* "GM" */
    for (;;)
        evnt_timer(1000, 0);
}
