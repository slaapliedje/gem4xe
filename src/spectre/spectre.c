/* spectre.c -- Spectre GS's main: take bank $E1, load the program, run it.
 *
 * The name is a nod to David Small's Spectre, which ran Macintosh
 * software on the Atari ST.  This runs Apple IIGS software on gem4xe, and
 * it does it the other way round from Spectre: no Apple ROM is involved.
 * The Toolbox it answers is written here, from Apple's published
 * references, and serves only the calls written so far -- a call that is
 * not stops the program and says which (sg_tool), so what runs, runs as
 * the reference says.
 *
 * SPECTRE.PRG NAME.S16 runs NAME.S16; with no name it runs HELLO.S16.
 */
#include "sg.h"

uint16_t sg_x, sg_pop, sg_why, sg_what;
uint32_t sg_go;
uint16_t sg_prog_d, sg_prog_s, sg_userid, sg_my_d;
uint16_t sgi_save_s, sgi_csp, sgi_err;      /* sgabi.s's own */

/* The harness's marks (tests/emu/sg1_hello.py): 'SG' when the run has
 * ended, and why in sg_result. */
uint16_t sg_done, sg_result, sg_stage;

/* Bank $00 for the program: its 4 KB of direct page and stack -- what
 * GS/OS gives a program with no direct-page/stack segment of its own --
 * QuickDraw II's three pages, and what else the Memory Manager is asked
 * for there.  It is in Spectre's own near memory, so gem4xe sees one
 * program whose stack is its own. */
#define B0_SIZE     0x1600
static uint8_t b0_raw[B0_SIZE + 0x100];
uint8_t *sg_b0;
uint16_t sg_b0_size;

uint16_t sg_get_d(void);            /* sgabi.s: Spectre's D */

void sg_putw(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

void sg_putl(uint8_t *p, uint32_t v)
{
    sg_putw(p, (uint16_t)v);
    sg_putw(p + 2, (uint16_t)(v >> 16));
}

static void put_jml(uint32_t at, uint32_t to)
{
    uint8_t FAR *p = (uint8_t FAR *)at;

    p[0] = 0x5C;                        /* jml long */
    p[1] = (uint8_t)to;
    p[2] = (uint8_t)(to >> 8);
    p[3] = (uint8_t)(to >> 16);
}

/* sg_tool: the call in sg_x, its inputs at p.  A set that is not here, or
 * a function in one that is not served, ends the run. */
uint16_t sg_tool(uint8_t *p)
{
    uint16_t ts = sg_x & 0xFF;          /* words: a chain of tests on a */
    uint8_t fn = (uint8_t)(sg_x >> 8);  /* byte is B23's shape */
    uint16_t e = SG_NOTYET;

    if (ts == 0x01)
        e = sg_tl(fn, p);
    else if (ts == 0x02)
        e = sg_mm(fn, p);
    else if (ts == 0x03)
        e = sg_mt(fn, p);
    else if (ts == 0x04)
        e = sg_qd(fn, p);
    else if (ts == 0x0A)
        e = sg_sane(fn, p);
    if (e == SG_NOTYET) {
        sg_what = sg_x;
        sg_abort(SG_UNTOOL);
    }
    return e;
}

static uint8_t rd8(uint32_t a)
{
    return *(uint8_t FAR *)a;
}

static void wr8(uint32_t a, uint8_t v)
{
    *(uint8_t FAR *)a = v;
}

static uint16_t rdw(uint32_t a)
{
    return (uint16_t)(rd8(a) | rd8(a + 1) << 8);
}

static uint32_t rdl(uint32_t a)
{
    return (uint32_t)rdw(a) | (uint32_t)rdw(a + 2) << 16;
}

static void wrw(uint32_t a, uint16_t v)
{
    wr8(a, (uint8_t)v);
    wr8(a + 1, (uint8_t)(v >> 8));
}

/* A GS/OS output string into the result buffer at `buf` (GS/OS Reference,
 * "GS/OS result buffer"): its size word first, then the string's length
 * word and its characters -- or, if they do not fit, the length alone and
 * error $4F, so the caller can grow the buffer and ask again. */
static uint16_t out_string(uint32_t buf, const char *s)
{
    uint16_t n = 0, i;

    while (s[n])
        n++;
    wrw(buf + 2, n);
    if (rdw(buf) < (uint16_t)(n + 4))
        return 0x004F;                  /* buffTooSmall */
    for (i = 0; i < n; i++)
        wr8(buf + 4 + i, (uint8_t)s[i]);
    return 0;
}

/* Where the program came from, as GS/OS would name it: its drive as a
 * volume.  Prefixes 8 (the default) and 9 (the program's own) are it;
 * the others are null until a program sets them, which it cannot yet. */
static const char sg_home[] = ":D1:";

/* The last pathname a GS/OS call was given, for the harness's report,
 * and the parameter block it came in. */
char sg_path[40];
uint32_t sg_pb;

static void note_path(uint32_t str)
{
    uint16_t n = rdw(str), i;

    if (n > sizeof sg_path - 1)
        n = sizeof sg_path - 1;
    for (i = 0; i < n; i++)
        sg_path[i] = (char)rd8(str + 2 + i);
    sg_path[n] = 0;
}

/* sg_gsos: `jsl $E100A8`, then the call number and the parameter block's
 * address in the six bytes after it; `ret` is where the return address is.
 * A served call moves the return address past those six bytes and returns
 * its error (GS/OS Reference, chapter 7).  Quit ($2029, or ProDOS 16's
 * $0029) ends the run; a call not served stops it. */
uint16_t sg_gsos(uint8_t *ret)
{
    uint32_t at = (uint32_t)ret[0] | (uint32_t)ret[1] << 8
                  | (uint32_t)ret[2] << 16;
    uint16_t call = (uint16_t)(rd8(at + 1) | rd8(at + 2) << 8);
    uint32_t pb = (uint32_t)rd8(at + 3) | (uint32_t)rd8(at + 4) << 8
                  | (uint32_t)rd8(at + 5) << 16;
    uint16_t e;

    sg_what = call;
    if (call == 0x2029 || call == 0x0029)
        sg_abort(SG_QUIT);
    switch (call) {
    case 0x200A:                        /* GetPrefix(pCount, prefixNum, prefix) */
        e = rdw(pb + 2);
        e = out_string(rdl(pb + 4), (e == 8 || e == 9) ? sg_home : "");
        break;
    case 0x2038:                        /* GetRefNum(pathname...): nothing is */
        if (rdw(pb) >= 2)               /* open, so no file matches */
            wrw(pb + 6, 0);             /* refNum */
        if (rdw(pb) >= 3)
            wrw(pb + 8, 0);             /* access */
        e = 0x0060;                     /* dataUnavail */
        break;
    case 0x2039:                        /* GetRefInfo(refNum...): no file */
        e = 0x0043;                     /* is open: invalidRefNum */
        break;
    case 0x2037:                        /* GetStdRefNum: nothing is open */
        *(uint8_t FAR *)(pb + 4) = 0;   /* refNum, for a program that */
        *(uint8_t FAR *)(pb + 5) = 0;   /* reads it anyway */
        e = 0x0060;                     /* dataUnavail */
        break;
    case 0x2010:                        /* Open: no files yet, but an EMPTY */
        sg_pb = pb;                     /* path -- ORCA/C's stdio opening a */
        note_path(rdl(pb + 4));         /* null prefix 10-12 -- is badly */
        if (sg_path[0]) {               /* formed whatever the files */
            sg_abort(SG_UNGSOS);
            return 0;
        }
        e = 0x0040;                     /* badPathSyntax */
        break;
    default:
        sg_abort(SG_UNGSOS);
        return 0;
    }
    at += 6;
    ret[0] = (uint8_t)at;
    ret[1] = (uint8_t)(at >> 8);
    ret[2] = (uint8_t)(at >> 16);
    return e;
}

static void say(const char *s)
{
    form_alert(1, s);
}

/* Not on the stack: it is 1 KB, and the loader's frames sit under main's. */
static char cmd[128], tail[128];

int main(void)
{
    const char *name = "HELLO.S16";
    uint32_t a, dp;
    uint16_t why;

    appl_init();
    sg_stage = 1;
    cmd[0] = 0;
    tail[0] = 0;
    shel_read(cmd, tail);
    if (tail[0] > 0 && tail[0] < 127) {
        tail[(uint8_t)tail[0] + 1] = 0;
        name = tail + 1;
        while (*name == ' ')
            name++;
    }
    sg_my_d = sg_get_d();

    if (Mclaim((LONG)SG_E1, (LONG)(SG_SHR_END - SG_E1)) < 0) {
        say("[3][Spectre GS needs bank $E1,|and it is not free memory.][ OK ]");
        appl_exit();
        return 2;
    }
    for (a = SG_E1; a < SG_SHR_END; a++)
        *(uint8_t FAR *)a = 0;
    put_jml(SG_TOOLS, (uint32_t)sg_entry);
    put_jml(SG_TOOLS2, (uint32_t)sg_entry2);
    put_jml(SG_GSOS, (uint32_t)sg_gsos_entry);

    sg_b0 = (uint8_t *)(((uint16_t)b0_raw + 0xFF) & 0xFF00);
    sg_b0_size = B0_SIZE;
    sg_userid = 0x1001;
    sg_stage = 2;
    if (sg_load(name) < 0) {
        say("[3][Spectre GS could not load|the program.][ OK ]");
        appl_exit();
        return 3;
    }
    sg_stage = 3;
    dp = sg_alloc(0x1000, 0xC015, 0);   /* locked, fixed, bank $00, page */
    if (!dp) {
        appl_exit();
        return 4;
    }
    sg_handle(dp, 0x1000, sg_userid);
    sg_prog_d = (uint16_t)dp;
    sg_prog_s = (uint16_t)(dp + 0x0FFF);
    sg_qd_reset();

    sg_stage = 4;
    why = sg_run();
    sg_result = why;
    sg_done = 0x4753;                   /* "SG" */
    if (why != SG_QUIT && why != SG_RTL)
        say("[1][Spectre GS stopped the program:|a call it does not serve yet.][ OK ]");
    appl_exit();
    return (int)why;
}
