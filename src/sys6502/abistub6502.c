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

static WORD refused(void)
{
    gem_bad++;
    return 0;
}

/* alerts (src/aes/alert.c): the pool */
WORD fm_alert(WORD defbut, const char *palstr) { (void)defbut; (void)palstr; return refused(); }
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

/* the pool (src/sys/pool.c) */
void    *pool_alloc(uint16_t size, uint16_t align) { (void)size; (void)align; refused(); return 0; }
uint16_t pool_mark(void) { return 0; }
void     pool_release(uint16_t mark) { (void)mark; }

/* what src/aes/rsrc.c reaches for (step 5b-3), resources being real now:
 *
 * A NAME, without GEMDOS.  On the 65C816 sh_cioname goes through GEMDOS
 * (src/sys/gemdos.c, gd_cioname), which knows the current directory and
 * the DOS's separator; the 6502 has neither yet.  So this is the flat
 * DOS's rule from src/sys/dos.c, dos_cioname with no separator: a drive
 * letter A-H becomes D1:-D8:, only the last component is kept, and it is
 * upper-cased.  "A:\X.RSC" and "X.RSC" both open D1:X.RSC (a bare name is
 * CIO's default drive).  GEMDOS replaces it. */
void sh_cioname(const char *gem, char *cio)
{
    const char *p = gem, *q;
    uint8_t k = 0;

    if (gem[0] && gem[1] == ':') {
        int d = (uint8_t)gem[0] | 0x20;     /* not a byte: B8, tools/ccbug */
        if (d >= 'a' && d <= 'h') {
            cio[k++] = 'D';
            cio[k++] = (char)('1' + (d - 'a'));
            cio[k++] = ':';
        }
        p = gem + 2;
    }
    for (q = p; *q; q++)
        if (*q == '\\')
            p = q + 1;
    if (!k) {
        cio[k++] = 'D';
        cio[k++] = ':';
    }
    for (; *p && k < CIO_NAME_MAX; p++) {
        int c = (uint8_t)*p;
        if (c >= 'a' && c <= 'z')
            c -= 0x20;
        cio[k++] = (char)c;
    }
    cio[k] = 0;
}

/* The pool has nothing above its top: there is no pool. */
uint16_t pool_room(void) { return 0; }

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
void     sh_get(uint32_t pbuffer, WORD len) { (void)pbuffer; (void)len; refused(); }
void     sh_put(uint32_t pdata, WORD len) { (void)pdata; (void)len; refused(); }
void     sh_rdef(char *lpcmd, char *lpdir) { lpcmd[0] = 0; lpdir[0] = 0; refused(); }
void     sh_read(char *pcmd, char *ptail) { pcmd[0] = 0; ptail[0] = 0; refused(); }
void     sh_wdef(const char *lpcmd, const char *lpdir) { (void)lpcmd; (void)lpdir; refused(); }
WORD     sh_write(WORD doex, WORD isgem, WORD isover, const char *pcmd, const char *ptail)
{
    (void)doex; (void)isgem; (void)isover; (void)pcmd; (void)ptail;
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
