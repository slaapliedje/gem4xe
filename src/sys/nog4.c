/* nog4.c -- G4DOS's half of GEMDOS, left out: GEM.COM for a disk that
 * boots a DOS 2 (build/gem-dos2.xex, the Makefile's GEM_DOS2_OBJS).
 *
 * WHY.  The SDFS engine (sdfs.c), CIO's D: over it (sdcio.c) and the
 * DOS's commands (doscmd.c) are some 32 KB of far code that runs only
 * where the DOS is G4DOS -- and a DOS 2 floppy is 720 sectors, which
 * GEM.COM with all of it no longer left room on for the desktop's files
 * and a DESKTOP.INF (2026-11-03, when the commands came in).  A DOS 2
 * floppy never has G4DOS on it, so its GEM.COM is the product with this
 * file in place of those three: sdc_init leaves the engine off, as it
 * does on every DOS but G4DOS, and the rest is never reached.
 *
 * Should this GEM.COM find itself on G4DOS after all, it is what gem4xe
 * was before G4DOS's folders: G4DOS's own flat D: through the OS, and no
 * DOS command.
 */
#include "portab.h"
#include "sdcio.h"
#include "gemdos.h"

void sdc_init(void)
{
}

uint8_t sdc_claims(const char *name)
{
    (void)name;
    return 0;
}

/* Never called: cio.c asks sdc_claims first, and an IOCB is only ever
 * marked SDC_ICHID by sdc_open. */
int16_t sdc_open(int16_t iocb, const char *name, uint8_t aux1, uint8_t aux2)
{
    (void)iocb;
    (void)name;
    (void)aux1;
    (void)aux2;
    return 0x92;                        /* CIO: not something this DOS does */
}

uint8_t sdc_close(int16_t iocb)
{
    (void)iocb;
    return 0x92;
}

uint8_t sdc_xfer(int16_t iocb, uint8_t cmd, void *buf, uint16_t len,
                 uint16_t *got)
{
    (void)iocb;
    (void)cmd;
    (void)buf;
    (void)len;
    *got = 0;
    return 0x92;
}

/* No engine, no folder to name: the AES leaves the name bare (phase 141). */
uint8_t sdc_folder(const char *bare, char *cio)
{
    (void)bare;
    (void)cio;
    return 0;
}

uint8_t sdc_xio(uint8_t cmd, const char *name)
{
    (void)cmd;
    (void)name;
    return 0x92;
}

int32_t sdc_command(uint32_t line, uint32_t out, uint32_t max)
{
    (void)line;
    (void)out;
    (void)max;
    return GD_EINVFN;
}
