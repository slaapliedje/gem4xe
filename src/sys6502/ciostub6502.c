/* ciostub6502.c -- CIO refused, for the 6502 links that have none: V6
 * and C6, whose VDI reaches for a face loaded from a file.  A6 links the
 * real src/sys/cio.c (docs/6502.md, step 5b) and not this. */
#include "portab.h"
#include "sys/cio.h"

/* ---- CIO: a face loaded from a file is refused ------------------------ */
int16_t  cio_open(const char *name, uint8_t aux1, uint8_t aux2)
{
    (void)name; (void)aux1; (void)aux2;
    return -1;
}
uint8_t  cio_read(int16_t iocb, void *buf, uint16_t len, uint16_t *got)
{
    (void)iocb; (void)buf; (void)len;
    *got = 0;
    return 136;                         /* end of file */
}
uint8_t  cio_close(int16_t iocb) { (void)iocb; return 1; }
