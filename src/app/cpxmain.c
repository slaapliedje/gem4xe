/* cpxmain.c -- the glue that makes a CPX module a program.
 *
 * A module author writes cpx_init and nothing else (src/app/cpx.h).
 * This file is main(): it finds the slot the shell gave it, calls
 * cpx_init, publishes what comes back, and stays resident.  It is part
 * of the kit, so a module links it and never sees any of this.
 *
 * WHY A MODULE IS A PROGRAM AT ALL, since XCONTROL's is not.  A
 * program's initialised data is installed by its crt, walking
 * data_init_table -- it is NOT in the image.  So a module entered
 * anywhere but its crt has globals full of whatever was there before,
 * with nothing failing at the time.  Running it as a program is what
 * guarantees cpx_init sees its own data, and the AES keeps it afterwards
 * exactly as it keeps an AUTO folder program that ends with Ptermres
 * (src/aes/shel.c).
 *
 * THE SLOT'S ADDRESS ARRIVES IN THE COMMAND TAIL, three bytes after the
 * ST's length byte.  A tail is how a program has always been told what
 * to do, so nothing new was invented to carry it.
 */
#include "cpx.h"

/* The module's own, which it must define. */
extern CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr);

/* CPXSLOT is src/app/cpx.h's -- the same layout the panel reads through
 * cpx_slot().  The AES lays it out again by hand (src/aes/shel.c's
 * CPXE_INFO and CPXE_HDR) because it cannot include this header, and
 * tests/host/test_cpx.py is the third writing that holds the two to it. */
int main(void)
{
    char cmd[128], tail[128];
    CPXSLOT FAR *slot;
    CPXINFO FAR *info;
    uint32_t addr;

    shel_read(cmd, tail);
    if ((unsigned char)tail[0] < 3)
        return 1;                       /* not run by the shell's loader */
    addr = (uint32_t)(unsigned char)tail[1]
         | ((uint32_t)(unsigned char)tail[2] << 8)
         | ((uint32_t)(unsigned char)tail[3] << 16);
    if (!addr)
        return 1;
    slot = (CPXSLOT FAR *)addr;

    /* The panel's parameter block is the shell's, far, and lives as long
     * as this module does.  cpx.h promises a module that every callback
     * may be 0, which is what lets this grow without breaking a module
     * built against an older one. */
    info = cpx_init((XCPB FAR *)0, &slot->hdr);
    if (!info)
        return 1;                       /* it declined: the shell frees it */

    slot->info = (uint32_t)(CPXINFO FAR *)info;
    /* STAY.  Without this the shell releases the module and the vtable
     * just published points into memory the next program will take. */
    Ptermres(0, 0);
    return 0;                           /* not reached */
}
