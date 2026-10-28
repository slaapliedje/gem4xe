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
 * reports as a failure. */
#include "gem.h"

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
    deep(40);
    appl_exit();
    return 7;
}
