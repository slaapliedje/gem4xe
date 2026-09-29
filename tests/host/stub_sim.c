/* stub_sim.c -- what `printf` actually asks the system for.
 *
 * src/app/gemstub.c answers the routines Calypsi's C library asks the
 * board for, and the whole of its correctness is a mapping: a file
 * descriptor is a GEMDOS handle unchanged, so stdout is handle 1 and the
 * bytes go out through Fwrite.  Nothing about that shows at link time --
 * a wrong handle, or a count and a buffer the wrong way round, links
 * perfectly and writes somewhere else.
 *
 * So the GEMDOS gate is replaced by a recorder, as tests/host/bind_sim.c
 * does for the bindings, and the program runs in the compiler's own
 * simulator.  What it records is the function number, the handle, the
 * byte count and the bytes themselves; tests/host/test_stub.py compares
 * them with what the program printed.
 */
#include "portab.h"
#include "gem.h"
#include <stdio.h>
#include <string.h>
#include <calypsi/stubs.h>

#define STUB_MAX 64

WORD stub_calls;                /* GEMDOS calls of any kind */
WORD stub_fn;                   /* the last one's function number */
WORD stub_handle;               /* ...and, for a write, its handle */
WORD stub_writes;               /* how many Fwrites the line took */
WORD stub_len;                  /* bytes over all of them */
WORD stub_text[STUB_MAX];       /* and the bytes themselves, one per word
                                 * so the simulator can print them */

/* The three gates.  Only GEMDOS is interesting here. */
SIMPLE_CALL void vdi_call(VDIPB FAR *pb) { (void)pb; }
SIMPLE_CALL void aes_call(AESPB FAR *pb) { (void)pb; }

SIMPLE_CALL void dos_call(GDPB FAR *pb)
{
    /* Pterm and Pterm0 do not come back, on the machine or here: the
     * kit's exit() is Pterm (src/app/gemstub.c), and this hands the end to
     * the simulator's own, where --exit-breakpoint stops.  Not counted --
     * the program's last CALL is still the write the test looks for. */
    if (pb->fn == 0x4C || pb->fn == 0x00)
        _Stub_exit(pb->fn == 0x4C ? pb->arg[0] : 0);
    stub_calls++;
    stub_fn = pb->fn;
    if (pb->fn == 0x40) {               /* Fwrite(handle, count, buf) */
        LONG count = (LONG)(UWORD)pb->arg[1] | ((LONG)pb->arg[2] << 16);
        LONG addr  = (LONG)(UWORD)pb->arg[3] | ((LONG)pb->arg[4] << 16);
        const char *p = (const char *)(UWORD)addr;
        WORD i, n = (WORD)(count > STUB_MAX ? STUB_MAX : count);

        stub_handle = pb->arg[0];
        stub_writes++;
        /* APPENDED, not replaced: stdout is unbuffered here, so a line
         * arrives one call per character unless the program gives stdio
         * a buffer of its own. */
        for (i = 0; i < n && stub_len < STUB_MAX; i++)
            stub_text[stub_len++] = (WORD)(unsigned char)p[i];
        pb->ret = count;                /* all of it went */
        return;
    }
    pb->ret = 0;
}

int main(void)
{
    printf("gem4xe %d\n", 43);
    fflush(stdout);
    return 0;
}
