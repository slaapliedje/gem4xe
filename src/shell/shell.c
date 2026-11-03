/* shell.c -- G4DOS's shell: the DOS's commands at a prompt, with no GEM
 * (docs/g4dos-plan.md, step 4).
 *
 * WHAT IT IS.  The file SHELL.SYS beside G4DOS.SYS.  G4DOS's loader runs it
 * when a disk has nothing else to boot -- no GEM.COM, no AUTORUN.SYS -- and
 * through DOSVEC whenever a program is done, as DOS 2's DOS.SYS ran
 * DUP.SYS.  It is a prompt and the commands of src/sys/doscmd.c, the same
 * commands gem4xe's File -> DOS command runs, over the same SDFS engine
 * (src/sys/sdfs.c): folders to any depth, 128-, 256- and 512-byte sectors.
 *
 * BELOW THE ENGINE, what the platform gives it, as in src/sys/sdcio.c: a
 * sector through G4DOS's sector entry ($070B) -- which keeps G4DOS's own
 * buffers true to what is written -- and a 512-byte one through the OS's
 * SIO, which G4DOS's buffers are too small for and which G4DOS cannot read
 * anyway.  Everything here is in bank $00 (src/shell/shell.scm), so a FAR
 * pointer's low word is its address.
 *
 * ITS PLACE OUTLASTS A PROGRAM: the drive and its folder go into the
 * cassette buffer ($0400-$047F, the OS's only for a cassette) after every
 * line, with a mark and a sum, and the shell that DOSVEC loads after a
 * program is done -- or after a RESET -- starts there -- unless the program used the page,
 * which the sum notices, or the folder has gone, when it is the root.
 *
 * A PROGRAM is run by G4DOS's loader, which is the one that can load over
 * the shell: the shell names the file and is gone (shstart.s, sh_exec).
 * G4DOS finds a name in the root or in a folder one level down -- the root
 * first, then the folders in order -- so a program is run only if that
 * search finds the very file the shell means; anything deeper waits for
 * G4DOS's handler to follow paths (the plan's step 9).
 */
#include "portab.h"
#include "sdfs.h"
#include "doscmd.h"

/* shstart.s */
SIMPLE_CALL uint16_t sh_call(uint16_t addr);
SIMPLE_CALL void sh_exec(uint16_t name);
SIMPLE_CALL void sh_cold(uint16_t unused);
extern uint8_t sh_a, sh_x, sh_y;

#define PEEK(a)       (*(volatile uint8_t *)(a))
#define PEEKW(a)      (*(volatile uint16_t *)(a))
#define LMARGN        0x52
#define RMARGN        0x53
#define CIOV          0xE456
#define SIOV          0xE459
#define IOCB(n, f)    PEEK(0x0340 + (n) * 16 + (f))
#define IOCBW(n, f)   PEEKW(0x0340 + (n) * 16 + (f))
#define IC_COM        2
#define IC_STA        3
#define IC_BAL        4
#define IC_BLL        8
#define IC_AX1        10
#define IC_AX2        11
#define CIO_OPEN      3
#define CIO_GETREC    5
#define CIO_GETCHR    7
#define CIO_PUTCHR    11
#define CIO_CLOSE     12
#define KBD           7               /* the IOCB K: is open on, for more */

/* The OS's SIO, by its device control block. */
#define DDEVIC        0x0300
#define DUNIT         0x0301
#define DCOMND        0x0302
#define DSTATS        0x0303
#define DBUF          0x0304
#define DTIMLO        0x0306
#define DBYT          0x0308
#define DAUX          0x030A

/* G4DOS's sector entry (src/fdos.s, fd_xsec). */
#define G4_UNIT       PEEK(0x0708)
#define G4_MODE       PEEK(0x0709)
#define G4_SECT       PEEKW(0x070E)
#define G4_ENTRY      0x070B
#define G4_WRITE      0x01
#define G4_ASK        0x40
#define G4_SHORT      0x80

static SDFS fs;
static DC_STATE dc;
static char line[DC_LINE];
static char run[20];                  /* "Dn:NAME.EXT" and an EOL */
static uint16_t g4buf;                /* G4DOS's data buffer: where it is */
static uint16_t devsec[SD_UNITS];     /* each drive's sector size: 0 not
                                         asked, $FFFF it could not say */
static uint8_t key;

#define KEEP          ((volatile uint8_t *)0x0400)   /* the cassette buffer */
#define KEEP_LEN      (3 + DC_PATH + 1)              /* 'G' '4', the drive,
                                                        the folder, a sum */

static const char banner[] = "\x9bG4DOS shell -- help lists commands\x9b";
static const char kname[] = "K:\x9b";
static const char FAR m_deep[] = "more than one folder down";
static const char FAR m_hidden[] = "G4DOS finds another first";

/* ---- the OS ------------------------------------------------------------ */

static uint16_t cio(uint16_t iocb)
{
    sh_x = (uint8_t)(iocb << 4);
    return (uint16_t)(sh_call(CIOV) & 0x80 ? IOCB(iocb, IC_STA) : 1);
}

static void put(const char *s, uint16_t n)
{
    IOCB(0, IC_COM) = CIO_PUTCHR;
    IOCBW(0, IC_BAL) = (uint16_t)s;
    IOCBW(0, IC_BLL) = n;
    cio(0);
}

/* The OS's SIO: the command `cmd` for sector `sec` of unit `unit`, `len`
 * bytes at `buf`, `dir` $40 in or $80 out.  SIO's status. */
static uint8_t sio(uint8_t unit, uint8_t cmd, uint8_t dir, uint16_t sec,
                   uint16_t buf, uint16_t len)
{
    PEEK(DDEVIC) = 0x31;
    PEEK(DUNIT) = unit;
    PEEK(DCOMND) = cmd;
    PEEK(DSTATS) = dir;
    PEEKW(DBUF) = buf;
    PEEK(DTIMLO) = 7;
    PEEKW(DBYT) = len;
    PEEKW(DAUX) = sec;
    sh_call(SIOV);
    return PEEK(DSTATS);
}

/* ---- below the engine -------------------------------------------------- */

static int16_t sio_err(uint8_t unit, uint8_t st, uint8_t write)
{
    if (st == 0x8A || st == 0x8B) {     /* nothing answered */
        devsec[unit - 1] = 0;
        return SD_EDRIVE;
    }
    if (write && st == 0x90)
        return SD_EWRPRO;
    return SD_EERROR;
}

uint16_t sd_devsec(SDFS FAR *s, uint8_t unit)
{
    uint8_t pc[12];
    uint16_t v;

    (void)s;
    if (unit < 1 || unit > SD_UNITS)
        return 0;
    v = devsec[unit - 1];
    if (!v) {
        v = 0xFFFF;
        if (sio(unit, 0x4E, 0x40, 0, (uint16_t)pc, 12) == 1)
            v = (uint16_t)(((uint16_t)pc[6] << 8) | pc[7]);
        devsec[unit - 1] = v;
    }
    return v == 0xFFFF ? 0 : v;
}

int16_t sd_dev(SDFS FAR *s, uint8_t unit, uint16_t sec, uint8_t FAR *buf,
               uint16_t len, uint8_t write)
{
    uint8_t *b;
    uint16_t i;
    uint8_t st;

    (void)s;
    if (len > 256) {                    /* straight to and from the cache */
        st = sio(unit, (uint8_t)(write ? 0x50 : 0x52),
                 (uint8_t)(write ? 0x80 : 0x40), sec,
                 (uint16_t)(uint32_t)buf, len);
        return st == 1 ? 0 : sio_err(unit, st, write);
    }
    if (!g4buf) {
        G4_MODE = G4_ASK;
        sh_call(G4_ENTRY);
        g4buf = (uint16_t)(sh_a | ((uint16_t)sh_x << 8));
    }
    b = (uint8_t *)g4buf;
    if (write)
        for (i = 0; i < len; i++)
            b[i] = buf[i];
    G4_UNIT = unit;
    G4_SECT = sec;
    G4_MODE = (uint8_t)((write ? G4_WRITE : 0) | (len == 128 ? G4_SHORT : 0));
    if (sh_call(G4_ENTRY) & 1)
        return sio_err(unit, PEEK(DSTATS), write);
    if (!write)
        for (i = 0; i < len; i++)
            buf[i] = b[i];
    return 0;
}

/* No clock is read here yet (the plan's step 6): what is written is
 * stamped 1 January 1980, as gem4xe stamps it without one. */
void sd_now(uint8_t FAR *stamp)
{
    stamp[0] = 1;
    stamp[1] = 1;
    stamp[2] = 80;
    stamp[3] = 0;
    stamp[4] = 0;
    stamp[5] = 0;
}

/* ---- what the commands want --------------------------------------------- */

void dc_out(DC_STATE FAR *h, const char FAR *s, uint16_t n)
{
    (void)h;
    put((const char *)(uint16_t)(uint32_t)s, n);
}

int16_t dc_key(DC_STATE FAR *h)
{
    (void)h;
    IOCB(KBD, IC_COM) = CIO_GETCHR;
    IOCBW(KBD, IC_BAL) = (uint16_t)&key;
    IOCBW(KBD, IC_BLL) = 1;
    return cio(KBD) < 0x80 ? key : -1;
}

/* The drive and its folder, kept for the next shell (above). */
static uint8_t keep_sum(void)
{
    uint16_t i;
    uint8_t s = 0x5A;

    for (i = 0; i < KEEP_LEN - 1; i++)
        s = (uint8_t)((s << 1 | s >> 7) ^ KEEP[i]);
    return s;
}

static void keep(void)
{
    uint16_t i;

    KEEP[0] = 'G';
    KEEP[1] = '4';
    KEEP[2] = dc.drive;
    for (i = 0; i < DC_PATH; i++)
        KEEP[3 + i] = (uint8_t)dc.cwd[dc.drive - 1][i];
    KEEP[KEEP_LEN - 1] = keep_sum();
}

static void restore(void)
{
    uint16_t i, d = KEEP[2];

    if (KEEP[0] != 'G' || KEEP[1] != '4' || d < 1 || d > SD_UNITS
        || KEEP[KEEP_LEN - 1] != keep_sum())
        return;
    for (i = 0; i < DC_PATH; i++)
        dc.cwd[d - 1][i] = (char)KEEP[3 + i];
    dc.cwd[d - 1][DC_PATH - 1] = 0;
    dc.drive = (uint8_t)d;
    if (sd_stat(&fs, (uint8_t)d, dc.cwd[d - 1], &dc.info2) != 0
        || !(dc.info2.status & SD_SUBDIR)) {
        dc.drive = 1;                   /* the disk has changed: the root */
        dc.cwd[d - 1][0] = 0;
    }
}

/* Everything the engine holds, written; where the shell is, kept; and the
 * IOCB it keeps for more closed, as a program expects to find it. */
static void leave(void)
{
    uint16_t u;

    for (u = 1; u <= SD_UNITS; u++)
        if (fs.units[u - 1].mounted)
            sd_sync(&fs, (uint8_t)u);
    keep();
    IOCB(KBD, IC_COM) = CIO_CLOSE;
    cio(KBD);
}

int16_t dc_exec(DC_STATE FAR *h, uint8_t unit, const char FAR *path)
{
    uint16_t i, k, at = 0, depth = 0;
    int16_t d;

    for (i = 0; path[i]; i++)
        if (path[i] == '\\') {
            depth++;
            at = i + 1;
        }
    if (depth > 2) {
        dc_say(h, 0, m_deep);
        return SD_EPTHNF;
    }
    if (depth == 2) {                   /* \DIR\NAME: is it the one G4DOS
                                         * would find? */
        dc.c[0] = '\\';
        for (k = 0; path[at + k]; k++)
            dc.c[1 + k] = path[at + k];
        dc.c[1 + k] = 0;
        if (sd_stat(&fs, unit, dc.c, &dc.info2) == 0) {
            dc_say(h, 0, m_hidden);
            return SD_EACCDN;
        }
        d = sd_opendir(&fs, unit, "");
        while (d >= 0 && sd_readdir(&fs, d, &dc.info2) >= 0) {
            if (!(dc.info2.status & SD_SUBDIR))
                continue;
            dc.c[0] = '\\';
            for (k = 0; dc.info2.name[k]; k++)
                dc.c[1 + k] = dc.info2.name[k];
            dc.c[1 + k] = 0;
            for (i = 0; i + 1 < at && path[i] == dc.c[i]; i++)
                ;
            if (i + 1 == at && !dc.c[i])
                break;                  /* its own folder: it is first */
            dc.c[1 + k] = '\\';
            for (i = 0; path[at + i]; i++)
                dc.c[2 + k + i] = path[at + i];
            dc.c[2 + k + i] = 0;
            if (sd_stat(&fs, unit, dc.c, &dc.info) == 0) {
                sd_closedir(&fs, d);
                dc_say(h, 0, m_hidden);
                return SD_EACCDN;
            }
        }
        if (d >= 0)
            sd_closedir(&fs, d);
    }
    run[0] = 'D';
    run[1] = (char)('0' + unit);
    run[2] = ':';
    for (i = 0; path[at + i] && i < 12; i++)
        run[3 + i] = path[at + i];
    run[3 + i] = (char)DC_EOL;
    leave();
    sh_exec((uint16_t)run);
    return 0;                           /* not reached */
}

int16_t dc_reboot(DC_STATE FAR *h)
{
    (void)h;
    leave();
    sh_cold(0);
    return 0;
}

/* ---- the prompt ------------------------------------------------------------ */

int main(void)
{
    uint16_t cols = (uint16_t)(PEEK(RMARGN) - PEEK(LMARGN) + 1);

    sd_init(&fs);
    dc_init(&dc, &fs, (uint8_t)cols, 24);
    IOCB(KBD, IC_COM) = CIO_CLOSE;      /* whatever a program left there */
    cio(KBD);
    IOCB(KBD, IC_COM) = CIO_OPEN;
    IOCBW(KBD, IC_BAL) = (uint16_t)kname;
    IOCB(KBD, IC_AX1) = 4;
    IOCB(KBD, IC_AX2) = 0;
    cio(KBD);
    put(banner, sizeof banner - 1);
    restore();
    for (;;) {
        dc_prompt(&dc);
        IOCB(0, IC_COM) = CIO_GETREC;
        IOCBW(0, IC_BAL) = (uint16_t)line;
        IOCBW(0, IC_BLL) = DC_LINE - 1;
        if (cio(0) >= 0x80) {           /* BREAK, or the line too long */
            put(banner, 1);
            continue;
        }
        dc_run(&dc, line);
        keep();
    }
}
