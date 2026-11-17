/* abistub6502.c -- what src/sys/abi.c reaches for that the 6502 has not
 * got yet (docs/6502.md, step 5a), in bank abi beside it.
 *
 * The shell, resources, the file selector, the scrap directory and the
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

/* resources (src/aes/rsrc.c) */
WORD     rs_free(void) { return refused(); }
WORD     rs_gaddr(UWORD rtype, UWORD rindex, uint32_t *paddr) { (void)rtype; (void)rindex; *paddr = 0; return refused(); }
void     rs_header(RSHDR *h) { uint16_t i; for (i = 0; i < sizeof *h; i++) ((uint8_t *)h)[i] = 0; }
WORD     rs_load(const char *name, WORD wants_far) { (void)name; (void)wants_far; return refused(); }
uint32_t rs_loaded(void) { return 0; }
void     rs_obfix(OBTREE tree, WORD obj) { (void)tree; (void)obj; refused(); }
WORD     rs_rcfix(uint32_t base) { (void)base; return refused(); }
WORD     rs_saddr(UWORD rtype, UWORD rindex, uint32_t addr) { (void)rtype; (void)rindex; (void)addr; return refused(); }

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
