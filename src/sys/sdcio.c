/* sdcio.c -- CIO's D: from gem4xe's own SDFS engine, where the DOS is
 * G4DOS.  sdcio.h says what and why; docs/sdfs-plan.md the plan.
 *
 * Two halves.  BELOW the engine, what the platform gives it (sdfs.h): a
 * sector, through G4DOS's sector entry, and the time, from the clock.
 * ABOVE it, the IOCB calls src/sys/cio.c hands over: open, close, the
 * transfers and XIO, in CIO's terms.
 *
 * ALL OF IT IS FAR, but the one pointer to it: the engine's block and a
 * record an IOCB, allocated by sdc_init.  Every pointer into it is FAR, and
 * nothing in it is handed to a function that takes a plain pointer
 * (docs: far-address-in-a-near-slot) -- a pattern or a name is copied
 * into a local first.
 */
#include "portab.h"
#include <string.h>
#include "sdfs.h"
#include "doscmd.h"
#include "sdcio.h"
#include "cio.h"
#include "dos.h"
#include "clock.h"
#include "farmem.h"
#include "irq.h"
#include "pool.h"
#include "zwin.h"
#include "gemdos.h"

/* ---- G4DOS's sector entry (src/fdos.s, fd_xsec) ------------------------ */
#define G4_UNIT   (*(volatile uint8_t *)0x0708)
#define G4_MODE   (*(volatile uint8_t *)0x0709)
#define G4_SECT   (*(volatile uint16_t *)0x070E)
#define G4_ENTRY  0x070B
#define G4_WRITE  0x01
#define G4_ASK    0x40              /* only: where is your buffer? */
#define G4_SHORT  0x80              /* a 128-byte sector */
#define DSTATS    (*(volatile uint8_t *)0x0303)

/* What an IOCB the engine has is doing. */
#define SDC_FILE   1
#define SDC_LINES  2                 /* a directory, as DOS 2's lines */
#define SDC_RAW    3                 /* a directory, as its own entries */

#define SDC_COLS   80                 /* the command window's width (deskcmd.c) */
#define SDC_PATH   (CIO_NAME_MAX + 16)   /* a path, with a folder put before it */
#define SDC_PAT    14

typedef struct {
    uint8_t  kind;                  /* SC_*, 0 for none */
    uint8_t  unit;
    uint8_t  flat;                  /* a listing of a bare name: G4DOS's */
    uint8_t  len;                   /* the entry being handed out: its size */
    uint8_t  at;                    /* ...and how much of it has gone */
    uint8_t  pad;
    int16_t  h;                     /* the engine's file or directory */
    int16_t  sub;                   /* flat: the folder being listed, or -1 */
    char     pat[SDC_PAT];           /* a listing's pattern */
    uint8_t  buf[24];               /* the entry being handed out */
} SDC_IO;

typedef struct {
    SDC_IO   io[CIO_IOCBS];
    /* a call's scratch, here and not on the stack: a GEMDOS call from an
     * application runs on that application's bank-$00 stack, and these
     * were 370 bytes of it more than the same call costs on SpartaDOS */
    char     path[SDC_PATH];
    char     to[SDC_PATH];
    char     sub[SDC_PATH];
    SD_INFO  info;
    uint16_t devsec[SD_UNITS];      /* what each drive said its sectors are:
                                       0 not asked, $FFFF it could not say */
    uint32_t cout;                  /* sdc_command: where its output goes */
    uint16_t cleft;                 /* ...and how much more there is room for */
    DC_STATE dc;                    /* the DOS's commands, between calls: their
                                       drive and folders persist, as a DOS's
                                       prompt keeps them */
    SDFS     fs;
} SDC_STATE;

/* In the window (zwin.h): only gem4xe's own calls read it, and before
 * they call a DOS, not during -- and LoRAM has no four bytes to spare. */
ZWIN static SDC_STATE FAR *sc;      /* 0: the engine is off */

#define FS (&sc->fs)

/* ---- below the engine -------------------------------------------------- */

/* G4DOS's entry with `mode`: the P it came back with (carry: it failed).
 * The round trip is sdx_call's (src/sys/cio.s), which ends at a JSR to
 * the address in sdx_vec; POKEY is given back to gem4xe after, as after
 * any SIO (src/sys/cio.c). */
static uint16_t g4_call(uint8_t mode)
{
    uint16_t p;

    G4_MODE = mode;
    sdx_vec = G4_ENTRY;
    cio_calls++;                    /* a round trip, as cio.c counts them */
    p = sdx_call(0);
    irq_pokey_resync();
    return p;
}

/* A failed SIO's status as the engine's error.  A drive that did not
 * answer is asked its geometry again next time: it may be another drive. */
static int16_t sdc_sio_err(uint8_t unit, uint8_t st, uint8_t write)
{
    if (st == 0x8A || st == 0x8B) {     /* timeout, NAK: nothing there */
        sc->devsec[unit - 1] = 0;
        return SD_EDRIVE;
    }
    if (write && st == 0x90)            /* the drive would not write */
        return SD_EWRPRO;
    return SD_EERROR;
}

/* The drive's sector size, from its PERCOM block (bytes 6-7, high first),
 * asked once a unit.  A drive with no PERCOM -- an 810 -- cannot say, and
 * its sector 1 is 128 bytes as every floppy's is. */
uint16_t sd_devsec(SDFS FAR *s, uint8_t unit)
{
    uint8_t pc[SIO_PERCOM_LEN];
    uint16_t v;

    (void)s;
    if (unit < 1 || unit > SD_UNITS)
        return 0;
    v = sc->devsec[unit - 1];
    if (!v) {
        v = 0xFFFF;
        if (dsk_percom(unit, pc) == SIO_OK)
            v = (uint16_t)(((uint16_t)pc[6] << 8) | pc[7]);
        sc->devsec[unit - 1] = v;
    }
    return v == 0xFFFF ? 0 : v;
}

/* A sector, through G4DOS's own data buffer in bank $00 -- whose address
 * G4DOS gives once and the engine's block keeps (s->dev) -- copied to or
 * from the engine's cache, which is far.  A 512-byte sector does not fit
 * that buffer: it goes through a slice of the pool and the OS's SIO
 * directly, as GEMDOS's own transfers do (gemdos.c, gd_xfer) -- nothing
 * else under GEM uses G4DOS's caches, so going round them is safe. */
int16_t sd_dev(SDFS FAR *s, uint8_t unit, uint16_t sec, uint8_t FAR *buf,
               uint16_t len, uint8_t write)
{
    uint8_t FAR *b;
    uint8_t st;

    if (len > 256) {
        uint16_t mark = pool_mark();
        uint8_t *p = (uint8_t *)pool_alloc(len, 2);
        if (!p)
            return SD_EERROR;
        if (write)
            memcpy_far((uint8_t FAR *)p, buf, len);
        st = write ? dsk_write(unit, sec, p, len) : dsk_read(unit, sec, p, len);
        if (st == SIO_OK && !write)
            memcpy_far(buf, (uint8_t FAR *)p, len);
        pool_release(mark);
        return st == SIO_OK ? 0 : sdc_sio_err(unit, st, write);
    }
    if (!s->dev) {
        g4_call(G4_ASK);
        s->dev = sdx_ax;            /* A low, X high */
    }
    b = (uint8_t FAR *)(uint32_t)s->dev;
    if (write)
        memcpy_far(b, buf, len);
    G4_UNIT = unit;
    G4_SECT = sec;
    if (g4_call((uint8_t)((write ? G4_WRITE : 0) | (len == 128 ? G4_SHORT : 0)))
        & 1)
        return sdc_sio_err(unit, DSTATS, write);
    if (!write)
        memcpy_far(buf, b, len);
    return 0;
}

/* The time as an entry keeps it: day, month, the year in two digits
 * (80-99 are 1980-1999, 0-79 2000-2079), hour, minute, second.  With no
 * clock, clock_read leaves 1 January 1980. */
void sd_now(uint8_t FAR *stamp)
{
    CLOCK c;

    clock_read(&c);
    stamp[0] = c.day;
    stamp[1] = c.month;
    stamp[2] = (uint8_t)(c.year >= 2000 ? c.year - 2000 : c.year - 1900);
    stamp[3] = c.hour;
    stamp[4] = c.minute;
    stamp[5] = c.second;
}

/* ---- names ------------------------------------------------------------- */

void sdc_init(void)
{
    int16_t i;

    sc = 0;
    if (dos.kind != DOS_G4DOS)
        return;
    sc = (SDC_STATE FAR *)far_alloc(sizeof(SDC_STATE));
    if (!sc)
        return;
    sd_init(FS);
    for (i = 0; i < CIO_IOCBS; i++)
        sc->io[i].kind = 0;
    for (i = 0; i < SD_UNITS; i++)
        sc->devsec[i] = 0;
    dc_init(&sc->dc, FS, SDC_COLS, 0);
    dos.caps |= DOS_CAP_DIRS | DOS_CAP_RAWDIR | DOS_CAP_STAMPS;
    /* ...and no drive map.  G4DOS's DRVBYT says D1: and D2: for what reads
     * it before GEM, but the engine reaches any unit, so Dprobe asks all
     * eight and Options -> Install devices can find a D3: (gemdos.c,
     * gd_dprobe).  Dsetdrv still answers D1: and D2: without asking. */
    dos.caps &= (uint8_t)~DOS_CAP_DRVBYT;
    dos.dirsep = '>';
}

/* The unit a D: name is for and where its path starts, or 0 for a name
 * that is not D:'s.  A name with no device is D1:'s, as cio.c's put_name
 * makes it. */
static const char *sdc_dev(const char *name, uint8_t *unit)
{
    char c = name[0];

    *unit = 1;
    if (c && name[1] == ':')
        return (c | 0x20) == 'd' ? name + 2 : 0;
    if (c && name[1] >= '0' && name[1] <= '9' && name[2] == ':') {
        *unit = (uint8_t)(name[1] - '0');
        return (c | 0x20) == 'd' ? name + 3 : 0;
    }
    return name;
}

static uint16_t sdc_len(const char FAR *s)
{
    uint16_t n = 0;

    while (s[n])
        n++;
    return n;
}

uint8_t sdc_claims(const char *name)
{
    uint8_t u;

    return (uint8_t)(sc && sdc_dev(name, &u));
}

/* What follows the device, as the engine takes a path: from the root,
 * '\' between the parts, in capitals, ending at a ',' (a rename's new
 * name follows one).  1 when it names no folder: a BARE name. */
static uint8_t sdc_path(const char *p, char FAR *out)
{
    uint8_t k = 0, bare = 1;

    out[k++] = '\\';
    for (; *p && *p != ',' && k < SDC_PATH - 14; p++) {
        int c = (uint8_t)*p;        /* not a byte: B8, tools/ccbug */
        if (c == '>') {
            if (k == 1 && bare) {   /* the root's own '>' */
                bare = 0;
                continue;
            }
            c = '\\';
            bare = 0;
        } else if (c >= 'a' && c <= 'z')
            c -= 0x20;
        out[k++] = (char)c;
    }
    out[k] = 0;
    return bare;
}

/* A bare name found where G4DOS finds one: the root, then each folder of
 * the root in turn.  sc->path ("\NAME.EXT") becomes the path of the one
 * found.  0, or the root's answer. */
static int16_t sdc_find(uint8_t u)
{
    SD_INFO FAR *in = &sc->info;
    char FAR *path = sc->path;
    char FAR *sub = sc->sub;
    uint16_t n, m, k;
    int16_t e, d;

    e = sd_stat(FS, u, path, in);
    if (e != SD_EFILNF)
        return e;
    d = sd_opendir(FS, u, "");
    if (d < 0)
        return e;
    m = sdc_len(path);
    while (sd_readdir(FS, d, in) == 0) {
        if (!(in->status & SD_SUBDIR))
            continue;
        sub[0] = '\\';
        for (n = 0; in->name[n]; n++)
            sub[n + 1] = in->name[n];
        n++;
        if (n + m >= SDC_PATH)
            continue;
        for (k = 0; k <= m; k++)    /* the path's '\' and its NUL too */
            sub[n + k] = path[k];
        if (sd_stat(FS, u, sub, in) == 0) {
            sd_closedir(FS, d);
            for (k = 0; k <= n + m; k++)
                path[k] = sub[k];
            return 0;
        }
    }
    sd_closedir(FS, d);
    return e;
}

/* The engine's errors as the status a SpartaDOS answers with -- which
 * src/sys/gemdos.c's gd_err turns back into GEMDOS's. */
static uint8_t sdc_st(int16_t e)
{
    switch (e) {
    case SD_EFILNF: return CIO_E_NOTFOUND;
    case SD_EPTHNF: return 0x96;            /* no such directory */
    case SD_EDRIVE: return 0xA0;            /* drive number */
    case SD_ENHNDL: return 0xA1;            /* too many files open */
    case SD_EIHNDL: return CIO_E_NOTOPEN;
    case SD_ENMFIL: return CIO_E_EOF;
    case SD_EWRPRO:
    case SD_EERROR: return 0x90;            /* the drive's own error */
    default:        return 0xA7;            /* refused: locked, there, full */
    }
}

/* ---- opening and closing ----------------------------------------------- */

int16_t sdc_open(int16_t n, const char *name, uint8_t aux1, uint8_t aux2)
{
    SDC_IO FAR *io = &sc->io[n];
    volatile IOCB *cb = &CIO_IOCB[n];
    char FAR *path = sc->path;
    uint8_t u, bare;
    int16_t mode, kind;                /* not bytes: B8, tools/ccbug */
    int16_t h, k, e;

    bare = sdc_path(sdc_dev(name, &u), path);
    sd_recheck(FS, u);
    io->sub = -1;
    io->len = io->at = 0;
    io->unit = u;
    io->flat = 0;
    if (aux1 == CIO_A_DIR || aux1 == CIO_A_RAWDIR) {
        /* the last part is the pattern, what is before it the folder */
        k = (int16_t)sdc_len(path);
        while (k > 0 && path[k - 1] != '\\')
            k--;
        if (sdc_len(path + k) >= SDC_PAT)
            return -(int16_t)CIO_E_NOTFOUND;
        for (h = 0; h < SDC_PAT; h++)
            io->pat[h] = path[k + h];
        if (!path[k])
            for (h = 0; h < 4; h++)
                io->pat[h] = "*.*"[h];
        path[k] = 0;
        h = sd_opendir(FS, u, path);
        if (h < 0)
            return -(int16_t)sdc_st(h);
        io->flat = bare;
        kind = aux1 == CIO_A_RAWDIR ? SDC_RAW : SDC_LINES;
    } else {
        switch (aux1 & 0x0C) {
        case CIO_A_READ:   mode = SD_READ; break;
        case CIO_A_WRITE:  mode = (aux1 & 1) ? SD_RW : SD_CREATE; break;
        case CIO_A_UPDATE: mode = SD_RW; break;
        default:           return -(int16_t)0x84;   /* no such mode */
        }
        if (bare && mode != SD_CREATE) {
            e = sdc_find(u);
            if (e < 0)
                return -(int16_t)sdc_st(e);
        }
        h = sd_open(FS, u, path, (uint8_t)mode);
        if (h < 0)
            return -(int16_t)sdc_st(h);
        if (aux1 == CIO_A_APPEND)
            sd_seek(FS, h, (uint32_t)sd_length(FS, h));
        kind = SDC_FILE;
    }
    io->h = h;
    io->kind = (uint8_t)kind;
    cb->ichid = SDC_ICHID;
    cb->icdno = u;
    cb->icax1 = aux1;
    cb->icax2 = aux2;
    cb->icsta = CIO_OK;
    return n;
}

uint8_t sdc_close(int16_t n)
{
    SDC_IO FAR *io = &sc->io[n];
    int16_t e = 0;

    if (io->kind == SDC_FILE)
        e = sd_close(FS, io->h);
    else if (io->kind) {
        sd_closedir(FS, io->h);
        if (io->sub >= 0)
            sd_closedir(FS, io->sub);
    }
    io->kind = 0;
    CIO_IOCB[n].ichid = 0xFF;
    return e < 0 ? sdc_st(e) : CIO_OK;
}

/* ---- listings ---------------------------------------------------------- */

/* An entry into io->buf in the form the listing was opened for: SDFS's
 * own 23 bytes (SDC_RAW), or the line a SpartaDOS X prints in its short
 * form -- a '*' for locked, a ':' for a folder, the name and extension in
 * columns 2-12, the size in sectors from column 14, and the EOL. */
static void sdc_form(SDC_IO FAR *io, const SD_INFO FAR *in, const char *s)
{
    uint8_t b[24], k, shift;
    int16_t n;                         /* not a byte: B8 */
    uint16_t secs;

    memset(b, ' ', sizeof b);
    if (io->kind == SDC_RAW) {
        b[0] = in->status;
        b[1] = b[2] = 0;            /* the map: nobody above asks */
        b[3] = (uint8_t)in->size;
        b[4] = (uint8_t)(in->size >> 8);
        b[5] = (uint8_t)(in->size >> 16);
        for (k = 0; k < 6; k++)
            b[17 + k] = in->stamp[k];
        n = 6;                      /* where the name goes */
    } else {
        b[0] = (uint8_t)((in->status & SD_LOCKED) ? '*' : ' ');
        b[1] = (uint8_t)((in->status & SD_SUBDIR) ? ':' : ' ');
        shift = sc->fs.units[io->unit - 1].shift;
        secs = (uint16_t)((in->size + ((1UL << shift) - 1)) >> shift);
        if (secs > 999)
            secs = 999;
        b[14] = (uint8_t)('0' + secs / 100);
        b[15] = (uint8_t)('0' + secs / 10 % 10);
        b[16] = (uint8_t)('0' + secs % 10);
        b[17] = CIO_EOL;
        n = 2;
    }
    for (k = 0; k < 8 && *s && *s != '.'; k++)
        b[n + k] = (uint8_t)*s++;      /* the name ... */
    while (*s && *s != '.')
        s++;
    if (*s == '.')
        s++;
    for (k = 0; k < 3 && *s; k++)
        b[n + 8 + k] = (uint8_t)*s++;
    n = io->kind == SDC_RAW ? 23 : 18;
    for (k = 0; k < n; k++)
        io->buf[k] = b[k];
    io->len = (uint8_t)n;
    io->at = 0;
}

/* The listing's next entry, into io->buf: 0, or SD_ENMFIL at the end.  A
 * flat listing walks each folder of the root as it meets it, files only;
 * a line listing leaves out what is hidden, as SpartaDOS's does.  The
 * pattern and the name are copied near for dos_wildcmp, whose pointers
 * are plain (docs: far-address-in-a-near-slot). */
static int16_t sdc_next(SDC_IO FAR *io)
{
    SD_INFO FAR *in = &sc->info;
    char pat[SDC_PAT], name[13];
    int16_t e, k;

    for (k = 0; k < SDC_PAT; k++)
        pat[k] = io->pat[k];
    for (;;) {
        if (io->sub >= 0) {
            e = sd_readdir(FS, io->sub, in);
            if (e == SD_ENMFIL) {
                sd_closedir(FS, io->sub);
                io->sub = -1;
                continue;
            }
            if (e < 0)
                return e;
            if (in->status & SD_SUBDIR)
                continue;           /* one level down, and no further */
        } else {
            e = sd_readdir(FS, io->h, in);
            if (e < 0)
                return e;
            if (io->flat && (in->status & SD_SUBDIR)) {
                sc->sub[0] = '\\';
                for (k = 0; k < 13; k++)
                    sc->sub[k + 1] = in->name[k];
                e = sd_opendir(FS, io->unit, sc->sub);
                io->sub = e < 0 ? -1 : e;
                continue;
            }
        }
        if (io->kind == SDC_LINES && (in->status & SD_HIDDEN))
            continue;
        for (k = 0; k < 13; k++)
            name[k] = in->name[k];
        if (!dos_wildcmp(pat, name))
            continue;
        sdc_form(io, in, name);
        return 0;
    }
}

/* ---- transfers --------------------------------------------------------- */

/* A record from a file: up to the EOL, which is kept; a longer one is cut
 * at `len` and the rest read away (CIO_E_TRUNC), as CIO does. */
static uint8_t sdc_getrec(int16_t h, uint8_t *p, uint16_t len, uint16_t *got)
{
    uint8_t c;
    int32_t r, at = sd_tell(FS, h);
    uint16_t i;

    r = sd_read(FS, h, p, len);
    if (r < 0)
        return sdc_st((int16_t)r);
    for (i = 0; i < (uint16_t)r; i++)
        if (p[i] == CIO_EOL) {
            sd_seek(FS, h, (uint32_t)(at + i + 1));
            *got = (uint16_t)(i + 1);
            return CIO_OK;
        }
    *got = (uint16_t)r;
    if ((uint16_t)r < len)
        return CIO_E_EOF;           /* the end, and no EOL before it */
    do
        r = sd_read(FS, h, &c, 1);
    while (r == 1 && c != CIO_EOL);
    return CIO_E_TRUNC;
}

uint8_t sdc_xfer(int16_t n, uint8_t cmd, void *buf, uint16_t len,
                uint16_t *got)
{
    SDC_IO FAR *io = &sc->io[n];
    uint8_t *p = (uint8_t *)buf;
    int16_t st = CIO_OK;               /* not a byte: B8 */
    uint16_t done = 0, m;
    int32_t r;
    int16_t e;

    if (io->kind == SDC_FILE) {
        switch (cmd) {
        case CIO_GETCHR:
            r = sd_read(FS, io->h, p, len);
            if (r < 0)
                st = sdc_st((int16_t)r);
            else if ((done = (uint16_t)r) < len)
                st = CIO_E_EOF;
            break;
        case CIO_GETREC:
            st = sdc_getrec(io->h, p, len, &done);
            break;
        case CIO_PUTREC:
            for (m = 0; m < len && p[m] != CIO_EOL; m++)
                ;
            if (m < len)
                len = (uint16_t)(m + 1);
            /* and on, as a block of that length */
        case CIO_PUTCHR:
            r = sd_write(FS, io->h, p, len);
            if (r < 0)
                st = sdc_st((int16_t)r);
            else if ((done = (uint16_t)r) < len)
                st = 0xA2;          /* the disk is full */
            break;
        default:
            st = 0x84;              /* not a command for a file */
        }
    } else if (cmd == CIO_GETCHR || cmd == CIO_GETREC) {
        while (done < len) {
            if (io->at >= io->len) {
                e = sdc_next(io);
                if (e < 0) {
                    st = sdc_st(e);
                    break;
                }
            }
            m = (uint16_t)(io->len - io->at);
            if (cmd == CIO_GETREC && m > len) {
                m = len;
                st = CIO_E_TRUNC;
            } else if (m > len - done)
                m = (uint16_t)(len - done);
            memcpy_far((uint8_t FAR *)(p + done), &io->buf[io->at], m);
            done = (uint16_t)(done + m);
            io->at = (uint8_t)(io->at + m);
            if (cmd == CIO_GETREC) {
                io->at = io->len;   /* a record is the whole entry */
                break;
            }
        }
    } else
        st = 0x87;                  /* a listing is read, not written */
    if (got)
        *got = done;
    CIO_IOCB[n].icbll = done;
    CIO_IOCB[n].icsta = (uint8_t)st;
    return (uint8_t)st;
}

/* ---- XIO --------------------------------------------------------------- */

uint8_t sdc_xio(uint8_t cmd, const char *name)
{
    char FAR *path = sc->path;
    char FAR *to = sc->to;
    const char *p, *comma;
    uint8_t u, bare;
    int16_t e = 0, k;

    p = sdc_dev(name, &u);
    bare = sdc_path(p, path);
    sd_recheck(FS, u);
    if (bare && cmd != CIO_X_MKDIR)
        e = sdc_find(u);
    if (e < 0)
        return sdc_st(e);
    switch (cmd) {
    case CIO_X_RENAME:
        /* "OLD,NEW": NEW is a name in OLD's folder */
        comma = strchr(p, ',');
        if (!comma)
            return 0xA5;            /* a name the DOS cannot read */
        k = (int16_t)sdc_len(path);
        while (k > 0 && path[k - 1] != '\\')
            k--;
        if (k + strlen(comma + 1) + 2 > SDC_PATH - 14)
            return 0xA5;
        memcpy_far(to, path, (size_t)k);
        sdc_path(comma + 1, to + k - 1);
        e = sd_rename(FS, u, path, to);
        break;
    case CIO_X_DELETE:
        e = sd_delete(FS, u, path);
        break;
    case CIO_X_LOCK:
    case CIO_X_UNLOCK:
        e = sd_attrib(FS, u, path, 0, 0);
        if (e >= 0)
            e = sd_attrib(FS, u, path, 1, (uint8_t)(cmd == CIO_X_LOCK
                                                    ? e | SD_LOCKED
                                                    : e & ~SD_LOCKED));
        break;
    case CIO_X_MKDIR:
        e = sd_mkdir(FS, u, path);
        break;
    case CIO_X_RMDIR:
        e = sd_rmdir(FS, u, path);
        break;
    case CIO_X_CHDIR:
        e = sd_opendir(FS, u, path);
        if (e >= 0) {
            sd_closedir(FS, e);
            e = 0;
        }
        break;
    default:
        return 0x92;                /* not something this DOS does */
    }
    return e < 0 ? sdc_st(e) : CIO_OK;
}

/* ---- the DOS's commands ---------------------------------------------------
 * File -> DOS command and Psystem, as SpartaDOS X's XCOMLI serves them
 * elsewhere (src/sys/dos.c): the same commands G4DOS's own shell runs at
 * its prompt, printing into the caller's far buffer.  The window shows
 * eighty columns (src/desk/deskcmd.c) and scrolls, so more never waits.
 * What they cannot do under GEM is run a DOS program, which would take
 * the machine, or start it again. */
static const char FAR m_quitgem[] = "quit GEM to run it";
static const char FAR m_noreboot[] = "quit GEM first";

void dc_out(DC_STATE FAR *h, const char FAR *s, uint16_t n)
{
    uint32_t at = sc->cout;
    uint16_t i;

    (void)h;
    if (n > sc->cleft)
        n = sc->cleft;
    for (i = 0; i < n; i++) {           /* by address: the buffer may
                                         * cross a bank (farmem.h) */
        *(uint8_t FAR *)at = (uint8_t)s[i];
        at++;
    }
    sc->cout = at;
    sc->cleft -= n;
}

int16_t dc_key(DC_STATE FAR *h)
{
    (void)h;
    return -1;
}

int16_t dc_exec(DC_STATE FAR *h, uint8_t unit, const char FAR *path)
{
    (void)unit;
    (void)path;
    dc_say(h, 0, m_quitgem);
    return SD_EACCDN;
}

int16_t dc_reboot(DC_STATE FAR *h)
{
    dc_say(h, 0, m_noreboot);
    return SD_EACCDN;
}

int32_t sdc_command(uint32_t line, uint32_t out, uint32_t max)
{
    uint16_t room;

    if (!sc)
        return GD_EINVFN;
    if (!line)
        return 0;
    room = max > 0xFFFFUL ? 0xFFFF : (uint16_t)max;
    sc->cout = out;
    sc->cleft = room;
    dc_run(&sc->dc, (const char FAR *)line);
    return (int32_t)(room - sc->cleft);
}
