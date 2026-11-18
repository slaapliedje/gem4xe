/* abistub6502.c -- what src/sys/abi.c reaches for that the 6502 has not
 * got yet (docs/6502.md, step 5a), in bank abi beside it.
 *
 * The shell, the file selector, the scrap directory and the
 * language file all need GEMDOS's file calls, which are step 5b; alerts
 * need the AES's pool, a near arena the 65C816 carves from its bank-$00
 * application pool and the 6502 has nowhere to put yet.  So each call
 * here is REFUSED, not pretended: it counts in gem_bad, as an opcode that
 * does not exist does -- which also makes abi.c record the opcode in
 * gem_badop -- and answers what the AES answers when the thing is not
 * there: no resource loaded, no program found, nothing chosen.
 */
#include "portab.h"
#include "aes/aes.h"
#include "sys/abi.h"
#include "sys/pool.h"
#include "sys/cio.h"
#include "sys/sdcio.h"
#include "sys/gemdos.h"
#include "sys/farmem.h"

static WORD refused(void)
{
    gem_bad++;
    return 0;
}

/* form_error (src/aes/alert.c): its texts are LANG.RSC's, which the
 * 6502 does not load yet.  form_alert itself is served (step 5b-5). */
WORD fm_error(WORD n) { (void)n; return refused(); }

/* the file selector (src/aes/fsel.c) */
WORD fs_input(char *pipath, char *pisel, WORD *pbutton, const char *pilabel)
{
    (void)pipath; (void)pisel; (void)pilabel;
    *pbutton = 0;
    return refused();
}

/* the language file (src/aes/lang.c): the built-in strings */
WORD lang_loaded(void) { return 0; }

/* THE POOL, a call's scratch (docs/6502.md, 5b-4).  On the 65C816 the
 * pool is bank $00's application pool (src/sys/pool.c), with a table of
 * blocks and owners; GEMDOS takes its path work and its transfer slices
 * from it and gives them back before the call returns.  That is all the
 * 6502 asks of it, so here it is a stack -- pool_alloc at the top,
 * pool_release back to a mark -- over the bytes of the load-time code,
 * section b6init (src/sys6502/bank6502.s), which runs from INITAD before
 * main and never again: 494 bytes of resident memory that nothing else
 * could have.  It must be NEAR and outside the window: far_get and
 * far_put map the far side into $4000-$7FFF, and CIO's buffer cannot be
 * in a bank a DOS might switch.  Nothing may keep a block past its call:
 * rsrc.c's colour icons, which would, are refused on the 6502. */
extern const uint16_t b6init_lo, b6init_hi;
#define POOL6_LO b6init_lo
#define POOL6_HI b6init_hi
static uint16_t pool6_top;              /* 0: not started (main has run) */
uint16_t pool6_peak;                    /* the highest it went: the gate's */
uint16_t pool6_refused;

void *pool_alloc(uint16_t size, uint16_t align)
{
    uint16_t at;

    if (!pool6_top)
        pool6_top = pool6_peak = POOL6_LO;
    at = pool6_top;

    if (align > 1)
        at = (uint16_t)((at + align - 1) & ~(align - 1));
    if (size > POOL6_HI - at) {
        pool6_refused++;
        return 0;
    }
    pool6_top = (uint16_t)(at + size);
    if (pool6_top > pool6_peak)
        pool6_peak = pool6_top;
    return (void *)at;
}
uint16_t pool_mark(void)
{
    if (!pool6_top)
        pool6_top = pool6_peak = POOL6_LO;
    return pool6_top;
}
void     pool_release(uint16_t mark)
{
    if (mark >= POOL6_LO && mark <= pool6_top)
        pool6_top = mark;
}

/* A resource's name (src/aes/rsrc.c), as the 65C816's shell makes it:
 * through GEMDOS, which knows each drive's directory and the DOS's
 * separator (src/sys/gemdos.c). */
void sh_cioname(const char *gem, char *cio) { gd_cioname(gem, cio); }

uint16_t pool_room(void) { return (uint16_t)(POOL6_HI - pool_mark()); }

/* the scrap directory (src/aes/scrap.c) */
WORD sc_clear(void) { return refused(); }
WORD sc_read(char *pscrap) { pscrap[0] = 0; return refused(); }
WORD sc_write(const char *pscrap) { (void)pscrap; return refused(); }

/* the shell (src/aes/shel.c): one program, no desktop, no control panel */
WORD     sh_ncpx;
WORD     sh_aesmsg(const WORD *msg) { (void)msg; return refused(); }
WORD     sh_broadcast(const WORD *msg) { (void)msg; return refused(); }
WORD     sh_cpxstride(void) { return 0; }
uint32_t sh_cpxtable(void) { return 0; }
WORD     sh_desk_running(void) { return 0; }
WORD     sh_environ(WORD how, WORD len, uint32_t buf) { (void)how; (void)len; (void)buf; return refused(); }
void     sh_envrn(const char **ppath, const char *psrch) { (void)psrch; *ppath = 0; refused(); }
WORD     sh_find(char *pspec) { (void)pspec; return refused(); }
/* the program shel_write(SHW_EXEC) names, for A6's shell (src/a6_evt.c) */
#define G6_RUNLEN 32
extern char g6_run[G6_RUNLEN];

/* THE SHELL BUFFER (step 5c-3): where the desktop keeps its DESKTOP.INF
 * text between programs, as src/aes/shel.c's sh_get and sh_put serve it --
 * here the far heap's, taken at the first call and kept as the system's
 * (far_keep: a block taken during a program's call is that program's). */
#define SH6_BUFLEN 4192                 /* the ST's SIZE_SHELBUF, gem.h's */
BANK_DATA("abi") static uint32_t sh6_buf;

static uint32_t sh6(void)
{
    if (!sh6_buf) {
        sh6_buf = far_alloc(SH6_BUFLEN);
        if (sh6_buf) {
            far_keep(sh6_buf);
            far_fill(sh6_buf, 0, SH6_BUFLEN);
        }
    }
    return sh6_buf;
}

void sh_get(uint32_t pbuffer, WORD len)
{
    uint32_t b = sh6();

    if (!b || len <= 0)
        return;
    if (len > SH6_BUFLEN)
        len = SH6_BUFLEN;
    far_copy(pbuffer, b, (uint16_t)len);
}

void sh_put(uint32_t pdata, WORD len)
{
    uint32_t b = sh6();

    if (!b || len <= 0)
        return;
    if (len > SH6_BUFLEN)
        len = SH6_BUFLEN;
    far_copy(b, pdata, (uint16_t)len);
}
void     sh_rdef(char *lpcmd, char *lpdir) { lpcmd[0] = 0; lpdir[0] = 0; refused(); }
void     sh_read(char *pcmd, char *ptail) { pcmd[0] = 0; ptail[0] = 0; refused(); }
void     sh_wdef(const char *lpcmd, const char *lpdir) { (void)lpcmd; (void)lpdir; refused(); }
WORD     sh_write(WORD doex, WORD isgem, WORD isover, const char *pcmd, const char *ptail)
{
    (void)isgem; (void)isover; (void)ptail;
    if (doex == 9)                      /* SWM_NEWMSG: what messages it takes;
                                         * A6 sends none of them (5c-3) */
        return 1;
    if (doex == 1 && pcmd) {            /* SHW_EXEC: the program, for A6's
                                         * shell (src/a6_evt.c, step 5d), as
                                         * CIO names it; it runs when the
                                         * caller's main returns */
        uint16_t mark = pool_mark();
        char *cio = pool_alloc(CIO_NAME_MAX + 1, 1);
        uint8_t i;

        if (!cio) {
            pool_release(mark);
            return refused();
        }
        gd_cioname(pcmd, cio);
        for (i = 0; i < G6_RUNLEN - 1 && cio[i]; i++)
            g6_run[i] = cio[i];
        if (cio[i])
            i = 0;                      /* too long for the slot: none */
        g6_run[i] = 0;
        pool_release(mark);
        return (WORD)(i != 0);
    }
    return refused();
}

/* G4DOS's own file system (src/sys/sdcio.c), which src/sys/cio.c asks
 * first: not on the 6502, so it claims no name and every file goes to
 * the DOS's D: (step 5b).  An IOCB never has SDC_ICHID here, so the rest
 * is not reached; each refuses if it is. */
uint8_t sdc_claims(const char *name) { (void)name; return 0; }
int16_t sdc_open(int16_t iocb, const char *name, uint8_t aux1, uint8_t aux2)
{
    (void)iocb; (void)name; (void)aux1; (void)aux2;
    refused();
    return -(int16_t)CIO_E_NODEV;
}
uint8_t sdc_close(int16_t iocb) { (void)iocb; refused(); return CIO_E_NOTOPEN; }
uint8_t sdc_xfer(int16_t iocb, uint8_t cmd, void *buf, uint16_t len, uint16_t *got)
{
    (void)iocb; (void)cmd; (void)buf; (void)len;
    if (got)
        *got = 0;
    refused();
    return CIO_E_NOTOPEN;
}
uint8_t sdc_xio(uint8_t cmd, const char *name) { (void)cmd; (void)name; refused(); return CIO_E_NODEV; }
/* SpartaDOS X's kernel (src/sys/cio.h): src/sys/clock.c asks it the time
 * on an SDX machine only, and SDX is a cartridge where the 6502 build
 * keeps resident code ($A000-$BFFF): not there.  Bit 0 set is its "no". */
uint16_t dos_call(uint16_t fn) { (void)fn; return 1; }

/* src/crt_atari.s's on the 65C816, how the program leaves for DOS, which
 * src/sys/dos.c sets from the DOS it found; A6 never leaves. */
uint8_t _exit_dosvec;

/* ...and what GEMDOS asks of it (src/sys/gemdos.c): Frename's move in
 * place, which a name it never claims never reaches, and the drive's
 * folder cache, which there is none of */
void    sdc_init(void) { }
void    sdc_forget(uint8_t drv) { (void)drv; }
uint8_t sdc_move(const char *from, const char *to) { (void)from; (void)to; refused(); return CIO_E_NODEV; }
