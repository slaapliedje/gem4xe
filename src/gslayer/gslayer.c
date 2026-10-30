/* gslayer.c -- GSlayer's main: take bank $E1, load the program, run it.
 *
 * GSlayer: a GS LAYER, not an emulator.  A IIGS program is 65816 code,
 * as gem4xe is, so it runs as it is; what it needs from the machine is
 * the Toolbox and GS/OS, and no Apple ROM is involved in answering them.
 * The Toolbox it answers is written here, from Apple's published
 * references, and serves only the calls written so far -- a call that is
 * not stops the program and says which (gs_tool), so what runs, runs as
 * the reference says.
 *
 * GSLAYER.PRG NAME.S16 runs NAME.S16; with no name it runs HELLO.S16.
 */
#include "gs.h"

uint16_t gs_x, gs_pop, gs_why, gs_what;
uint32_t gs_go;
uint16_t gs_prog_d, gs_prog_s, gs_userid, gs_my_d;
uint16_t gsi_save_s, gsi_csp, gsi_err;      /* gsabi.s's own */

/* The harness's marks (tests/emu/gs1_hello.py): 'GS' when the run has
 * ended, and why in gs_result. */
uint16_t gs_done, gs_result, gs_stage;

/* Bank $00 for the program: its 4 KB of direct page and stack -- what
 * GS/OS gives a program with no direct-page/stack segment of its own --
 * QuickDraw II's three pages, and what else the Memory Manager is asked
 * for there.  It is in GSlayer's own near memory, so gem4xe sees one
 * program whose stack is its own. */
#define B0_SIZE     0x1600
static uint8_t b0_raw[B0_SIZE + 0x100];
uint8_t *gs_b0;
uint16_t gs_b0_size;

uint16_t gs_get_d(void);            /* gsabi.s: GSlayer's D */

void gs_putw(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

void gs_putl(uint8_t *p, uint32_t v)
{
    gs_putw(p, (uint16_t)v);
    gs_putw(p + 2, (uint16_t)(v >> 16));
}

static void put_jml(uint32_t at, uint32_t to)
{
    uint8_t FAR *p = (uint8_t FAR *)at;

    p[0] = 0x5C;                        /* jml long */
    p[1] = (uint8_t)to;
    p[2] = (uint8_t)(to >> 8);
    p[3] = (uint8_t)(to >> 16);
}

/* gs_tool: the call in gs_x, its inputs at p.  A set that is not here, or
 * a function in one that is not served, ends the run. */
uint16_t gs_tool(uint8_t *p)
{
    uint16_t ts = gs_x & 0xFF;          /* words: a chain of tests on a */
    uint8_t fn = (uint8_t)(gs_x >> 8);  /* byte is B23's shape */
    uint16_t e = GS_NOTYET;

    if (ts == 0x01)
        e = gs_tl(fn, p);
    else if (ts == 0x02)
        e = gs_mm(fn, p);
    else if (ts == 0x03)
        e = gs_mt(fn, p);
    else if (ts == 0x04)
        e = gs_qd(fn, p);
    else if (ts == 0x0A)
        e = gs_sane(fn, p);
    if (e == GS_NOTYET) {
        gs_what = gs_x;
        gs_abort(GS_UNTOOL);
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
static const char gs_home[] = ":D1:";

/* The last pathname a GS/OS call was given, for the harness's report,
 * and the parameter block it came in. */
char gs_path[40];
uint32_t gs_pb;

static void note_path(uint32_t str)
{
    uint16_t n = rdw(str), i;

    if (n > sizeof gs_path - 1)
        n = sizeof gs_path - 1;
    for (i = 0; i < n; i++)
        gs_path[i] = (char)rd8(str + 2 + i);
    gs_path[n] = 0;
}

/* gs_gsos: `jsl $E100A8`, then the call number and the parameter block's
 * address in the six bytes after it; `ret` is where the return address is.
 * A served call moves the return address past those six bytes and returns
 * its error (GS/OS Reference, chapter 7).  Quit ($2029, or ProDOS 16's
 * $0029) ends the run; a call not served stops it. */
uint16_t gs_gsos(uint8_t *ret)
{
    uint32_t at = (uint32_t)ret[0] | (uint32_t)ret[1] << 8
                  | (uint32_t)ret[2] << 16;
    uint16_t call = (uint16_t)(rd8(at + 1) | rd8(at + 2) << 8);
    uint32_t pb = (uint32_t)rd8(at + 3) | (uint32_t)rd8(at + 4) << 8
                  | (uint32_t)rd8(at + 5) << 16;
    uint16_t e;

    gs_what = call;
    if (call == 0x2029 || call == 0x0029)
        gs_abort(GS_QUIT);
    switch (call) {
    case 0x200A:                        /* GetPrefix(pCount, prefixNum, prefix) */
        e = rdw(pb + 2);
        e = out_string(rdl(pb + 4), (e == 8 || e == 9) ? gs_home : "");
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
        gs_pb = pb;                     /* path -- ORCA/C's stdio opening a */
        note_path(rdl(pb + 4));         /* null prefix 10-12 -- is badly */
        if (gs_path[0]) {               /* formed whatever the files */
            gs_abort(GS_UNGSOS);
            return 0;
        }
        e = 0x0040;                     /* badPathSyntax */
        break;
    default:
        gs_abort(GS_UNGSOS);
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
    gs_stage = 1;
    cmd[0] = 0;
    tail[0] = 0;
    shel_read(cmd, tail);
    if (tail[0] > 0 && tail[0] < 127) {
        tail[(uint8_t)tail[0] + 1] = 0;
        name = tail + 1;
        while (*name == ' ')
            name++;
    }
    gs_my_d = gs_get_d();

    if (Mclaim((LONG)GS_E1, (LONG)(GS_SHR_END - GS_E1)) < 0) {
        say("[3][GSlayer needs bank $E1,|and it is not free memory.][ OK ]");
        appl_exit();
        return 2;
    }
    for (a = GS_E1; a < GS_SHR_END; a++)
        *(uint8_t FAR *)a = 0;
    put_jml(GS_TOOLS, (uint32_t)gs_entry);
    put_jml(GS_TOOLS2, (uint32_t)gs_entry2);
    put_jml(GS_GSOS, (uint32_t)gs_gsos_entry);

    gs_b0 = (uint8_t *)(((uint16_t)b0_raw + 0xFF) & 0xFF00);
    gs_b0_size = B0_SIZE;
    gs_userid = 0x1001;
    gs_stage = 2;
    if (gs_load(name) < 0) {
        say("[3][GSlayer could not load|the program.][ OK ]");
        appl_exit();
        return 3;
    }
    gs_stage = 3;
    dp = gs_alloc(0x1000, 0xC015, 0);   /* locked, fixed, bank $00, page */
    if (!dp) {
        appl_exit();
        return 4;
    }
    gs_handle(dp, 0x1000, gs_userid);
    gs_prog_d = (uint16_t)dp;
    gs_prog_s = (uint16_t)(dp + 0x0FFF);
    gs_qd_reset();

    gs_stage = 4;
    why = gs_run();
    gs_result = why;
    gs_done = 0x5347;                   /* "GS" */
    if (why != GS_QUIT && why != GS_RTL)
        say("[1][GSlayer stopped the program:|a call it does not serve yet.][ OK ]");
    appl_exit();
    return (int)why;
}
