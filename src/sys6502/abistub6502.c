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
