/* app.h -- loading and running a gem4xe application.
 *
 * An application arrives as a .g4a (tools/mkg4a.py): a near part that
 * wants a page-aligned place in bank $00 -- its direct page, stack and
 * data -- a far part that wants whole banks -- its code -- and four lists
 * of the bytes to patch once both places are known.  app_load() takes the
 * near part from the pool src/gem4xe.scm sets aside (apppool; the bounds
 * come from the linker through src/sys/apppool.s) and the far part from
 * the far heap, copies, patches, and records where everything went.
 * app_exec() calls the application's entry as a far subroutine
 * (src/sys/abi.s) and returns what its main() returned.  app_free() gives
 * both regions back, by the program's owner, in any order: the far heap
 * since phase 79 (src/sys/farmem.c), the pool since phase 117
 * (src/sys/pool.h, which is also where the pool's rules are).
 */
#ifndef GEM4XE_APP_H
#define GEM4XE_APP_H

#include "portab.h"
#include <stdint.h>
#include "sys/pool.h"

#define APP_OK        0
#define APP_E_MAGIC  -1     /* not a G4A, or a version this loader lacks */
#define APP_E_SHORT  -2     /* the blob ends before the header says */
#define APP_E_POOL   -3     /* no room in the bank-$00 pool */
#define APP_E_FAR    -4     /* no far bank */
#define APP_E_FIXUP  -5     /* a fixup offset outside its part */
#define APP_E_FILE   -6     /* the file would not open (app_load_file) */
#define APP_E_READ   -7     /* it opened, then a read failed partway */
#define APP_E_STACK  -9     /* it ran, and was stopped: its stack left its
                               own memory (src/sys/abi.c) -- the shell's
                               report, not a load status */
#define APP_E_OLDSDK -8     /* a G4A of format 1 or 2, built for the old COP
                               signatures (src/sys/abi.h): rebuild it */

typedef struct {
    uint16_t near_base;     /* where the near part landed, page aligned */
    uint16_t near_size;
    uint32_t far_addr;      /* where the far part landed */
    uint32_t far_size;
    uint32_t entry;         /* __program_start, relocated */
    uint16_t link_near;     /* the link-time bases, so a symbol from the */
    uint8_t  link_bank;     /* link's map translates: addr - link + base */
    uint16_t fixups;        /* patched bytes, all four lists */
    uint16_t pool_mark;     /* the pool's top before the load: a
                             * failure part-way releases to it */
    uint32_t vars_addr;     /* a packed program's far variables (format 5), */
    uint8_t  vars_link;     /* and the bank they were linked in; 0 if none */
    uint16_t owner;         /* whose its far blocks are: app_free frees them
                             * (src/sys/farmem.c, phase 79) */
} APP;


/* Where the last program app_load() placed its near region.  Only a
 * diagnostic -- nothing in the engine reads it -- but the gates need it
 * now that an accessory is loaded before the first program. */
extern uint16_t app_near;                          /* bytes left          */
extern uint32_t app_far;           /* its far image: large-data globals   */
extern uint32_t app_vars;          /* ...a packed one's far variables (v5) */
extern uint8_t  app_vlink;         /* ...and the bank they were linked in  */

/* The kind of program the next app_load or app_load_file loads, OWN_* in
 * src/sys/farmem.h; read once and put back to 0, which is OWN_APP. */
extern uint8_t app_kind;

int16_t app_load(const uint8_t FAR *blob, uint32_t len, APP *app);
int16_t app_exec(const APP *app);
void    app_free(const APP *app);

/* A whole file, by its CIO name, into far memory: where it starts, with
 * its length in *len, or 0 when it would not open or read to its end --
 * and then nothing is kept.  It is taken from the far heap as far_owner,
 * so the owner decides when it goes.  The file is read
 * through a slice of the pool, which is given back before returning. */
/* APP_OK with *addr and *len set; or APP_E_FILE (it would not open),
 * APP_E_READ (a read failed partway), APP_E_FAR (far memory ran out)
 * or APP_E_SHORT (it was empty), keeping nothing -- but *len still says
 * how far it got. */
int16_t far_read_file(const char *cioname, uint32_t *addr, uint32_t *len);

/* app_load() on a file: the GEM name (X:\DIR\NAME.PRG, or a bare name on
 * the default drive) through the DOS seam, read whole, then loaded.  The
 * file's bytes are left in far memory below the application's and go
 * back with them at app_free(). */
int16_t app_load_file(const char *gemname, APP *app);

/* ...and on a CIO name, for a caller that has made it itself -- the
 * shell, for a file in the system's own directory whatever the default
 * one is now (src/aes/shel.c sh_cpxload). */
int16_t app_load_cio(const char *cioname, APP *app);

#endif /* GEM4XE_APP_H */
