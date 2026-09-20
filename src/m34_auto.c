/* m34_auto.c -- the AUTO folder's two cases, from one source.
 *
 * Built twice (the Makefile):
 *
 *   M34RES.PRG   ends with Ptermres, so the shell must KEEP it
 *   M34GO.PRG    ends with a plain return, so the shell must RELEASE it
 *
 * Both run before the accessories and before the keep mark
 * (src/aes/shel.c, sh_auto), and neither opens a workstation or talks to
 * the AES at all -- an AUTO program on an ST runs before the AES exists,
 * and one here should not need it either.  What they do instead is leave
 * a mark the gate can read afterwards.
 *
 * THE MARK IS IN FAR MEMORY, taken with Malloc, and that is the point of
 * the whole test rather than an incidental: a resident program's Malloc
 * must SURVIVE, because the far heap is a bump allocator and releasing
 * this program would wind it back over the very bytes written here.  So
 * the gate reads the signature back after the desktop is up -- through
 * the address this program recorded -- and if the shell released a
 * resident program the bytes are gone or overwritten by the desktop.
 *
 * Nothing near is used for the mark, because a program's near region is
 * the shell's again the instant a NON-resident program exits, and the
 * gate must be able to tell those two apart.
 */
#include "gem.h"

/* Where the gate looks.  These are this program's own variables, and the
 * gate finds them the way it finds any program's: through the .g4a's
 * recorded near base (tests/emu use app_near).  A resident program's
 * near region is never reclaimed, so for M34RES they stay readable. */
WORD  m34_ran;            /* 1 once main() has run */
WORD  m34_res;            /* 1 if this build asks to stay */
LONG  m34_addr;           /* what Malloc gave it */
WORD  m34_wrote;          /* 1 once the signature is in far memory */

#define M34_SIG   0x5A34          /* 'Z4': what the gate looks for */
#define M34_LEN   16

int main(void)
{
    LONG a;

    m34_ran = 1;
#ifdef M34_RESIDENT
    m34_res = 1;
#endif
    /* Far memory, and written through a far pointer: this is the byte
     * the shell must not wind back over. */
    a = Malloc(M34_LEN);
    m34_addr = a;
    if (a > 0) {
        UWORD FAR *p = (UWORD FAR *)a;
        *p = M34_SIG;
        m34_wrote = 1;
    }
#ifdef M34_RESIDENT
    /* TERMINATE AND STAY RESIDENT.  The `keep` argument is the ST's and
     * cannot mean here what it means there -- a gem4xe program is two
     * whole regions out of two bump allocators, so there is nothing to
     * cut and it is read and ignored (src/sys/gemdos.c).  Passing the
     * length anyway says what was intended. */
    Ptermres(M34_LEN, 0);
#endif
    return 0;
}
