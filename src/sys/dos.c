/* dos.c -- which DOS is behind CIO.  See dos.h. */
#include "portab.h"
#include <string.h>
#include "dos.h"
#include "cio.h"
#include "app.h"
#include "farmem.h"
#include "gemdos.h"
#include "vbxe/vbxe.h"

DOS_INFO dos;

#define DOSVEC   (*(uint8_t **)0x000A)
#define DOSBASE  ((const uint8_t *)0x0700)
#define MEMTOP   (*(uint16_t *)0x02E5)
#define MEMLO    (*(uint16_t *)0x02E7)

extern uint8_t _exit_dosvec;        /* src/crt_atari.s */

void dos_ident(void)
{
    const uint8_t *comtab = DOSVEC;

    dos.kind = DOS_2;
    dos.caps = 0;
    dos.dirsep = 0;
    dos.memlo = MEMLO;
    dos.memtop = MEMTOP;

    if (DOSBASE[0] == 'S' && comtab[3] == 0x4C) {
        /* The X is a cartridge: its RAMTOP is the cartridge's bottom,
         * where a disk SpartaDOS leaves the screen at DOS 2's height.
         * MEMTOP is that less the screen, so $A000 tells them apart
         * without reading either DOS's own tables. */
        dos.kind = (dos.memtop < 0xA000) ? DOS_SDX : DOS_SPARTA;
        dos.caps = DOS_CAP_DIRS | DOS_CAP_RAWDIR | DOS_CAP_STAMPS;
        dos.dirsep = '>';
    }
    /* How to leave (src/crt_atari.s).  A SpartaDOS keeps its command
     * processor resident and is waiting for its loader to return, so a
     * return is what it wants.  An Atari DOS 2 may keep its in DUP.SYS,
     * at $1D00-$3306 -- memory gem4xe runs in -- so it is asked to come
     * back through DOSVEC, which reloads it. */
    _exit_dosvec = (uint8_t)(dos.kind == DOS_2);
}

/* SpartaDOS X: ':' in the second flag column (Programming Guide 4.50,
 * 10.2, the short format's mode $08).  SpartaDOS 3.2: "DIR" with the
 * high bits set in the extension field -- inverse video on the screen
 * the line was made for. */
uint8_t dos_folder_line(const char *line)
{
    const char *ext = line + 10;

    if (!(dos.caps & DOS_CAP_DIRS))
        return DOS_MARK_NONE;
    if (line[1] == ':')
        return DOS_MARK_FLAG;
    if ((uint8_t)ext[0] == ('D' | 0x80) && (uint8_t)ext[1] == ('I' | 0x80)
        && (uint8_t)ext[2] == ('R' | 0x80))
        return DOS_MARK_EXT;
    return DOS_MARK_NONE;
}

void dos_cioname(const char *gem, char *cio)
{
    const char *p = gem, *q;
    uint8_t k = 0;

    if (gem[0] && gem[1] == ':' && gem[2] == '\\') {
        char d = (char)(gem[0] | 0x20);
        if (d >= 'a' && d <= 'h') {
            cio[k++] = 'D';
            cio[k++] = (char)('1' + (d - 'a'));
            cio[k++] = ':';
        }
        p = gem + 3;
        if (dos.dirsep)
            cio[k++] = dos.dirsep;      /* from the root */
    }
    if (!dos.dirsep)                    /* a flat DOS: the last component */
        for (q = p; *q; q++)
            if (*q == '\\')
                p = q + 1;
    for (; *p && k < CIO_NAME_MAX; p++) {
        int c = (uint8_t)*p;            /* not a byte: B8, tools/ccbug */
        if (c == '\\')
            c = (uint8_t)dos.dirsep;
        else if (c >= 'a' && c <= 'z')
            c -= 0x20;
        cio[k++] = (char)c;
    }
    cio[k] = 0;
}

#define DIRLINE 17          /* DOS 2's directory record, less its EOL */

/* A directory field -- the name's 8 columns or the extension's 3 -- less
 * its trailing spaces: its length, or -1 when a character in it is not
 * one DOS 2 puts in a name. */
static int16_t dir_field(const char *p, int16_t n, char *out)
{
    int16_t k;

    while (n > 0 && p[n - 1] == ' ')
        n--;
    for (k = 0; k < n; k++) {
        int c = (uint8_t)p[k];          /* not a byte: B8, tools/ccbug */
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
              || c == '_' || c == '@'))
            return -1;
        out[k] = (char)c;
    }
    out[n] = 0;
    return n;
}

uint8_t dos_dirline(const char *line, uint16_t got, char *fname,
                    uint16_t *sectors)
{
    char ext[4];
    int16_t n, e;
    uint8_t mark, kind;

    if (got < DIRLINE || line[13] != ' ')
        return DOS_ENT_NONE;
    mark = dos_folder_line(line);
    if (mark == DOS_MARK_NONE && line[1] != ' ')
        return DOS_ENT_NONE;
    n = dir_field(line + 2, 8, fname);
    if (n <= 0 || !(fname[0] >= 'A' && fname[0] <= 'Z'))
        return DOS_ENT_NONE;
    if (sectors) {
        uint16_t v = 0;
        for (e = 14; e < DIRLINE; e++) {
            int c = (uint8_t)line[e];
            if (c >= '0' && c <= '9')
                v = v * 10 + (c - '0');
        }
        *sectors = v;
    }
    kind = (line[0] == '*') ? DOS_ENT_LOCKED : 0;
    if (mark == DOS_MARK_EXT)
        return kind | DOS_ENT_DIR;
    e = dir_field(line + 10, 3, ext);
    if (e < 0)
        return DOS_ENT_NONE;
    if (e) {
        fname[n] = '.';
        strcpy(fname + n + 1, ext);
    }
    return kind | (mark ? DOS_ENT_DIR : DOS_ENT_FILE);
}

uint16_t dos_wildcmp(const char *pattern, const char *filename)
{
    int16_t i;

    for (i = 0; i < 2; i++) {
        for (; *filename && *filename != '.'; filename++) {
            if (*pattern == '*')
                continue;
            if (*pattern == '?' || *pattern == *filename) {
                pattern++;
                continue;
            }
            return 0;
        }
        while (*pattern == '*' || *pattern == '?')
            pattern++;
        if (*pattern == '.')
            pattern++;
        if (*filename == '.')
            filename++;
    }
    return *pattern == *filename;
}

/* ---- the DOS's command processor ------------------------------------ */
/* SpartaDOS X will run a whole command line for a program: XCOMLI,
 * "eXecute COMmand LIne" (Programming Guide 4.50, 18.9.2).  The line
 * goes in LBUF (COMTAB+63, 64 bytes, EOL-ended), BUFOFF (COMTAB+10) is
 * zeroed, and one JSR does what the prompt would -- an internal command,
 * a CAR: command, a program, >> redirection; only batch files are out.
 * What it prints can be caught in memory (18.9.5.2): with the console's
 * handle at COMTAB+6 set to 100 the library's FPUTC jumps through PUT_V
 * for every byte, and src/sys/cio.s sdx_put stores each through a long
 * address into a far buffer of the caller's.
 *
 * FINDING THE ENTRIES.  Both are symbols, which the DOS's loader
 * resolves for its own relocatable binaries and not for a .xex.  The
 * fixed entry jfsymbol at $07EB (16.1, as of 4.40) looks one up by its
 * space-padded name -- AX in, AX out, Z for none -- and is asked once,
 * on the first call, and only on a SpartaDOS X of 4.4 or later ($0701
 * holds the version, User Guide 6.8) whose $07EB is the JMP it should
 * be.  A program started with X.COM has no symbol list; jfsymbol's Z
 * says so and the item stays grey.
 *
 * THE ROOM.  XCOMLI loads COMMAND.COM (~3.6 KB) at MEMLO and a program
 * above it, so for the call MEMLO is raised to the pool's cursor and
 * the MEMAC window is closed: from there to the DOS's screen at $9C00
 * -- the pool's free top, the window's 4 KB and the idle $9000-$9BFF --
 * is the command's, ten KB or so with the product resident
 * (tools/memreport.py).  MEMLO goes back afterwards, so a program that
 * stays resident from here does not; it would sit where the next
 * application loads.  A DOS 2 has no command processor: EINVFN.
 */
#define SDX_VERSION  (*(volatile uint8_t *)0x0701)  /* $44 = 4.4 */
#define SDX_JFSYMBOL 0x07EB
#define SDX_STDOUT   6                  /* COMTAB+6: the console's handle */
#define SDX_BUFOFF   10
#define SDX_LBUF     63                 /* 64 bytes */
#define SDX_LBUF_LEN 64
#define SDX_EOL      0x9B
#define SDX_PUTV_H   100                /* the handle that goes through PUT_V */

static uint16_t sdx_xcomli, sdx_putv;   /* the two entries; 0 = none */
static uint8_t  sdx_asked;              /* jfsymbol has been asked */

/* One symbol's address, by its eight-character name in bank $00. */
static uint16_t sdx_symbol(const char *name)
{
    uint16_t p;

    sdx_vec = SDX_JFSYMBOL;
    sdx_ax = (uint16_t)name;
    p = sdx_call(0);
    return (uint16_t)((p & 0x02) ? 0 : sdx_ax);    /* Z: no such symbol */
}

/* THE NAMES GO BELOW $4000, and that is the whole of this buffer's
 * reason for existing.  They used to be pool_alloc'd, which puts them at
 * $4800 or above -- INSIDE THE WINDOW SPARTADOS X BANKS ITS OWN RAM INTO
 * while it works (src/gem4xe.scm, "THE BANKED WINDOW").  The window is
 * safe for a CIO buffer because a DOS reaches a caller's memory through
 * its memory-index mechanism and runs the transfer loop below $4000 for
 * exactly that reason (SDX Programming Guide 4.50, 3.7 and 22.4.3).
 * jfsymbol is NOT CIO: it is a JSR into the cartridge with a raw pointer
 * in the registers, so the name has to be somewhere that is still there
 * after the bank comes in.
 *
 * It presented as a SIZE problem, which is why it took a bisect and then
 * a probe to name: pool_alloc hands out the pool's cursor, the cursor
 * moves as the desktop and its resource grow, and whether the seventeen
 * bytes landed somewhere fatal depended on how big GEM.COM was.  Four
 * hundred bytes of dummy far code on a good commit reproduced it
 * exactly.  The desktop hung at cmd_init with the hourglass up and
 * sometimes a BRK; skipping the cartridge call took it from call 18 to
 * call 44 and named the subject.
 *
 * ONE NAME AT A TIME, and nine bytes rather than seventeen, because
 * LoRAM is what pays for this: the pair in one buffer took it to 251
 * free against a budget of 256, and src/gem4xe.scm had just said the
 * next table would have to find room rather than move that boundary a
 * fifth time.  jfsymbol takes eight characters and no terminator -- the
 * old buffer held both names with the NUL only after the second -- so
 * the ninth byte here is for C's sake, not the cartridge's. */
static char sdx_name[9];                /* LoRAM: below $4000, always there */

static uint16_t sdx_find(const char FAR *name)
{
    far_strget(sdx_name, (uint32_t)name, sizeof sdx_name);
    return sdx_symbol(sdx_name);
}

static void sdx_lookup(void)
{
    static const char FAR xcomli[] = "XCOMLI  ";
    static const char FAR put_v[]  = "PUT_V   ";

    if (dos.kind != DOS_SDX || SDX_VERSION < 0x44
     || *(volatile uint8_t *)SDX_JFSYMBOL != 0x4C) {
        sdx_asked = 1;
        return;
    }
    sdx_xcomli = sdx_find(xcomli);
    sdx_putv = sdx_find(put_v);
    sdx_asked = 1;
}

int32_t dos_command(uint32_t line, uint32_t out, uint32_t max)
{
    uint8_t *comtab = DOSVEC;
    uint8_t *lbuf = comtab + SDX_LBUF;
    uint16_t *putv;
    uint16_t memlo, was, i;
    uint8_t handle;

    if (!sdx_asked)
        sdx_lookup();
    if (!sdx_xcomli || !sdx_putv)
        return GD_EINVFN;
    if (!line)
        return 0;                       /* the probe: there is one */
    if (max > 0xFFFFUL)
        max = 0xFFFFUL;

    /* the line, ended as the prompt would leave it */
    far_strget((char *)lbuf, line, SDX_LBUF_LEN);
    for (i = 0; i < SDX_LBUF_LEN - 1 && lbuf[i]; i++)
        ;
    lbuf[i] = SDX_EOL;
    comtab[SDX_BUFOFF] = 0;

    /* what it prints, into the caller's buffer */
    sdx_put_ptr[0] = (uint8_t)out;
    sdx_put_ptr[1] = (uint8_t)(out >> 8);
    sdx_put_ptr[2] = (uint8_t)(out >> 16);
    sdx_put_left = (uint16_t)max;
    putv = (uint16_t *)sdx_putv;
    was = *putv;
    *putv = (uint16_t)sdx_put;
    handle = comtab[SDX_STDOUT];
    comtab[SDX_STDOUT] = SDX_PUTV_H;

    /* the room, then the run */
    memlo = MEMLO;
    MEMLO = pool_mark();
    vram_unmap();
    sdx_vec = sdx_xcomli;
    sdx_call(0);

    MEMLO = memlo;
    comtab[SDX_STDOUT] = handle;
    *putv = was;
    return (int32_t)(max - sdx_put_left);
}
