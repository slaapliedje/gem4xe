/* test-m47's child (tests/emu/m47_stack.py): a program that runs its
 * stack out of its own memory and keeps calling GEM while it does.
 *
 * Each level of the recursion holds 200 bytes and makes one AES call.
 * Linked with a 384-byte stack, the third or fourth level is below the
 * floor gem4xe keeps for it (src/sys/ctx.h) -- $40 into its direct
 * page, past the compiler's registers -- and the call made from there
 * must stop it (src/sys/abi.c)
 * before a further level writes past the direct page into memory that is
 * not its own.  If it is not stopped it returns 7, which its parent
 * reports as a failure.
 *
 * BIG.PRG and SMALL.PRG are this file again (phase 121), built with
 * M47_LEVELS 12 and 3 and their stacks LAST, asking for 4096 bytes and
 * for 256 (the Makefile, test-m47): the first must run to its end and
 * return 7, the second must be stopped by the floor of the stack it
 * asked for, though the 1024 it was linked with would have held it. */
#include "gem.h"

#ifndef M47_LEVELS
#define M47_LEVELS 40
#endif

/* Its own data, checked at the end: a stack that ran out of its room
 * without being stopped writes through it -- with the stack last, this is
 * what is below the stack -- and the program returns 5 instead of 7. */
static volatile char m47_mine[48] = "the child's own data, as the crt laid it down";

static WORD deep(WORD n)
{
    volatile char buf[200];
    WORD w, h, bw, bh;

    buf[0] = (char)n;
    buf[199] = (char)n;
    graf_handle(&w, &h, &bw, &bh);
    if (n > 0)
        return (WORD)(deep((WORD)(n - 1)) + buf[0] + buf[199]);
    return buf[0];
}

int main(void)
{
    appl_init();
    deep(M47_LEVELS);
    appl_exit();
    {
        static const char want[48] = "the child's own data, as the crt laid it down";
        WORD i;
        for (i = 0; i < 48; i++)
            if (m47_mine[i] != want[i])
                return 5;
    }
    return 7;
}
