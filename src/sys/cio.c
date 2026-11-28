/* cio.c -- IOCBs filled in and CIO called.  See cio.h. */
#include "sys/cio.h"
#include "sys/irq.h"
#include "sys/sdcio.h"

uint16_t cio_calls;
uint8_t  cio_last;

/* The name CIO reads, in bank $00: "D:" + name + EOL at most. */
static char cio_name[CIO_NAME_MAX + 4];

#ifdef __CALYPSI_TARGET_6502__
/* THE SAMPLER IS SILENT FOR THE CALL, as src/sys/cio.s keeps it on the
 * 65C816: timer 1 out of POKMSK and IRQEN before CIO or SIO has POKEY,
 * back in POKMSK after, and armed by irq_pokey_resync only once it has
 * reprogrammed the timer.  Left running, it stopped the desktop's load on
 * MiSTer's Atari800 core every time -- the machine hung inside SIO and
 * the core's drive was left with half a command frame -- where Altirra,
 * with real serial timing or without, never minded.  The pointer stands
 * still while the disk turns, as it does on the 65C816. */
#define POKMSK (*(volatile uint8_t *)0x0010)
#define IRQEN  (*(volatile uint8_t *)0xD20E)
static void sampler_off(void)
{
    if (irq.how != IRQ_OFF) {
        POKMSK &= (uint8_t)~1u;
        IRQEN = POKMSK;
    }
}
static void sampler_on(void)
{
    if (irq.how != IRQ_OFF)
        POKMSK |= 1u;                   /* armed by irq_pokey_resync */
}
#else
#define sampler_off()
#define sampler_on()
#endif

static uint8_t call(int16_t iocb)
{
    uint8_t st;
    cio_calls++;
    sampler_off();
    st = (uint8_t)cio_call((uint16_t)iocb);
    sampler_on();
    irq_pokey_resync();             /* SIO had POKEY; the sampler wants it back */
    cio_last = st;
    return st;
}

static uint8_t is_digit(char c) { return (uint8_t)(c >= '0' && c <= '9'); }

/* A device spec is "X:" or "Xn:" -- a letter, an optional digit, a colon. */
static uint8_t has_device(const char *name)
{
    if (!name[0])
        return 0;
    if (name[1] == ':')
        return 1;
    return (uint8_t)(is_digit(name[1]) && name[2] == ':');
}

/* The name into cio_name, "D:" prefixed when it names no device. */
static void put_name(const char *name)
{
    uint8_t i = 0;
    if (!has_device(name)) {
        cio_name[i++] = 'D';
        cio_name[i++] = ':';
    }
    while (*name && i < CIO_NAME_MAX)
        cio_name[i++] = *name++;
    cio_name[i] = (char)CIO_EOL;
}

/* A free IOCB, or -1. */
static int16_t free_iocb(void)
{
    int16_t n;
    for (n = 1; n < CIO_IOCBS; n++)
        if (CIO_IOCB[n].ichid == 0xFF)
            return n;
    return -1;
}

/* Open on the IOCB the caller names, rather than the first free one.
 * GEMDOS's handles ARE its IOCBs (src/sys/gemdos.c: handle = iocb +
 * GD_HANDLE_BASE), so a file that has to be reopened -- which is how a
 * seek backwards is done on a DOS with no byte-addressable POINT -- must
 * come back on the IOCB it went out on, or the handle would change under
 * the application. */
static int16_t open_on(int16_t n, const char *name, uint8_t aux1, uint8_t aux2)
{
    volatile IOCB *io;

    if (n < 1 || n >= CIO_IOCBS)
        return -(int16_t)CIO_E_INUSE;
    if (sdc_claims(name))            /* G4DOS's disks: src/sys/sdcio.h */
        return sdc_open(n, name, aux1, aux2);
    put_name(name);
    io = &CIO_IOCB[n];
    io->iccom = CIO_OPEN;
    io->icbal = (uint16_t)cio_name;
    io->icbll = 0;
    io->icax1 = aux1;
    io->icax2 = aux2;
    {
        uint8_t st = call(n);
        if (st != CIO_OK) {
            /* A failed open leaves the IOCB claimed -- ICHID is the
             * handler's, not $FF -- until it is closed (seen: the next
             * open would have taken the next IOCB). */
            cio_close(n);
            return -(int16_t)st;
        }
    }
    return n;
}

int16_t cio_open(const char *name, uint8_t aux1, uint8_t aux2)
{
    int16_t n = free_iocb();

    if (n < 0)
        return -(int16_t)CIO_E_INUSE;
    return open_on(n, name, aux1, aux2);
}

/* The same file on the same IOCB, from the beginning: close and open.
 * A close of an IOCB that is already free is a status, not a fault. */
int16_t cio_reopen(int16_t iocb, const char *name, uint8_t aux1, uint8_t aux2)
{
    cio_close(iocb);
    return open_on(iocb, name, aux1, aux2);
}


uint8_t cio_close(int16_t iocb)
{
    if (CIO_IOCB[iocb].ichid == SDC_ICHID)
        return sdc_close(iocb);
    CIO_IOCB[iocb].iccom = CIO_CLOSE;
    return call(iocb);
}

static uint8_t xfer(int16_t iocb, uint8_t cmd, const void *buf, uint16_t len,
                    uint16_t *got)
{
    volatile IOCB *io = &CIO_IOCB[iocb];
    uint8_t st;
    if (io->ichid == SDC_ICHID)
        return sdc_xfer(iocb, cmd, (void *)buf, len, got);
    io->iccom = cmd;
    io->icbal = (uint16_t)buf;
    io->icbll = len;
    st = call(iocb);
    if (got)
        *got = io->icbll;
    return st;
}

uint8_t cio_read(int16_t iocb, void *buf, uint16_t len, uint16_t *got)
{
    return xfer(iocb, CIO_GETCHR, buf, len, got);
}

uint8_t cio_getrec(int16_t iocb, void *buf, uint16_t len, uint16_t *got)
{
    return xfer(iocb, CIO_GETREC, buf, len, got);
}

uint8_t cio_write(int16_t iocb, const void *buf, uint16_t len)
{
    return xfer(iocb, CIO_PUTCHR, buf, len, 0);
}

uint8_t cio_status(int16_t iocb)
{
    if (CIO_IOCB[iocb].ichid == SDC_ICHID)
        return CIO_OK;
    CIO_IOCB[iocb].iccom = CIO_STATUS;
    return call(iocb);
}

uint8_t cio_xio(uint8_t cmd, const char *name, uint8_t aux1, uint8_t aux2)
{
    volatile IOCB *io;
    int16_t n;
    uint8_t st;

    if (sdc_claims(name))
        return sdc_xio(cmd, name);
    n = free_iocb();
    if (n < 0)
        return CIO_E_INUSE;
    put_name(name);
    io = &CIO_IOCB[n];
    io->iccom = cmd;
    io->icbal = (uint16_t)cio_name;
    io->icbll = 0;
    io->icax1 = aux1;
    io->icax2 = aux2;
    st = call(n);
    /* CIO serves a special command on a closed IOCB by opening it to the
     * device for the call; whether it is left claimed afterwards is the
     * handler's business, so it is closed here regardless -- closing a
     * free IOCB is a status, not a fault. */
    if (io->ichid != 0xFF)
        cio_close(n);
    return st;
}

/* ---- the disk, under the file system ----------------------------------
 * The DCB in page 3, then SIOV.  Filling it here rather than in the
 * assembly keeps the round trip (src/sys/cio.s) the one thing that knows
 * how to become the machine DOS was running on.
 *
 * DTIMLO is the OS's own for a disk read; DSTATS $40 says the drive
 * sends.  The unit is 1-based, as D1: is.  */
#define DCB_DDEVIC 0x0300
#define DCB_DUNIT  0x0301
#define DCB_DCOMND 0x0302
#define DCB_DSTATS 0x0303
#define DCB_DBUFLO 0x0304
#define DCB_DTIMLO 0x0306
#define DCB_DBYTLO 0x0308
#define DCB_DAUX1  0x030A

#define SIO_DISK   0x31         /* DDEVIC for D1: .. D8: */
#define SIO_READ   0x52         /* 'R' */
#define SIO_PERCOM 0x4E         /* 'N': the drive's own geometry */
#define SIO_STATUS 0x53         /* 'S': four bytes, from any drive there */
#define SIO_FROM   0x40         /* DSTATS: the drive sends */
#define SIO_TO     0x80         /* ...or is sent to */
#define SIO_PUT    0x50         /* 'P': a write without the drive's verify */
#define SIO_PERCOM_W 0x4F       /* 'O': the drive told the geometry to format */
#define SIO_TIME   0x0F         /* DTIMLO, as the OS uses for a disk */
#define SIO_CLOCK  0x45         /* DDEVIC of an APETime clock: a FujiNet's */
#define SIO_FUJI   0x70         /* DDEVIC of the FujiNet itself */
#define SIO_GETTIME 0x93        /* its date and time */
#define SIO_GETAUX 0xA0EE       /* DAUX as APETime's callers send it */

/* ...with `tim` for DTIMLO: a format takes minutes, not the seconds a
 * sector does. */
static uint8_t sio_devt(uint8_t dev, uint8_t unit, uint8_t cmd, uint8_t dir,
                        uint16_t aux, void *buf, uint16_t len, uint8_t tim)
{
    uint8_t st;
    volatile uint8_t *d = (volatile uint8_t *)DCB_DDEVIC;
    volatile uint16_t *w;

    d[DCB_DDEVIC - DCB_DDEVIC] = dev;
    d[DCB_DUNIT - DCB_DDEVIC] = unit;
    d[DCB_DCOMND - DCB_DDEVIC] = cmd;
    d[DCB_DSTATS - DCB_DDEVIC] = dir;
    w = (volatile uint16_t *)DCB_DBUFLO;
    *w = (uint16_t)buf;
    d[DCB_DTIMLO - DCB_DDEVIC] = tim;
    w = (volatile uint16_t *)DCB_DBYTLO;
    *w = len;
    w = (volatile uint16_t *)DCB_DAUX1;
    *w = aux;
    cio_calls++;
    sampler_off();
    st = (uint8_t)dsk_call(0);
    sampler_on();
    irq_pokey_resync();             /* and arms timer 1 again (cio.s) */
    return st;
}

static uint8_t sio_dev(uint8_t dev, uint8_t unit, uint8_t cmd, uint8_t dir,
                       uint16_t aux, void *buf, uint16_t len)
{
    return sio_devt(dev, unit, cmd, dir, aux, buf, len, SIO_TIME);
}

static uint8_t sio_dir(uint8_t unit, uint8_t cmd, uint8_t dir, uint16_t aux,
                       void *buf, uint16_t len)
{
    return sio_dev(SIO_DISK, unit, cmd, dir, aux, buf, len);
}

static uint8_t sio(uint8_t unit, uint8_t cmd, uint16_t aux, void *buf,
                   uint16_t len)
{
    return sio_dir(unit, cmd, SIO_FROM, aux, buf, len);
}

uint8_t dsk_read(uint8_t unit, uint16_t sector, void *buf, uint16_t len)
{
    return sio(unit, SIO_READ, sector, buf, len);
}

uint8_t dsk_write(uint8_t unit, uint16_t sector, void *buf, uint16_t len)
{
    return sio_dir(unit, SIO_PUT, SIO_TO, sector, buf, len);
}

/* The drive's own geometry: tracks, sectors a track, sides and the sector
 * size, the words big-endian.  What the caller wants it for is the sector
 * size (bytes 6-7) and how many sectors there are, which decides whether a
 * DOS 2 disk has a second VTOC (src/sys/gemdos.c). */
uint8_t dsk_percom(uint8_t unit, void *buf)
{
    return sio(unit, SIO_PERCOM, 0, buf, SIO_PERCOM_LEN);
}

uint8_t dsk_status(uint8_t unit)
{
    uint8_t st[4];

    return sio(unit, SIO_STATUS, 0, st, sizeof st);
}

uint8_t dsk_status4(uint8_t unit, void *buf)
{
    return sio(unit, SIO_STATUS, 0, buf, 4);
}

uint8_t dsk_setpercom(uint8_t unit, void *buf)
{
    return sio_dir(unit, SIO_PERCOM_W, SIO_TO, 0, buf, SIO_PERCOM_LEN);
}

uint8_t dsk_format(uint8_t unit, uint8_t cmd, void *buf, uint16_t len,
                   uint8_t secs)
{
    return sio_devt(SIO_DISK, unit, cmd, SIO_FROM, 0, buf, len, secs);
}

uint8_t sio_fuji(uint8_t cmd, uint8_t dstats, uint16_t aux, void *buf,
                 uint16_t len)
{
    return sio_dev(SIO_FUJI, 1, cmd, dstats, aux, buf, len);
}

uint8_t sio_gettime(void *buf)
{
    return sio_dev(SIO_CLOCK, 1, SIO_GETTIME, SIO_FROM, SIO_GETAUX, buf,
                   SIO_GETTIME_LEN);
}
