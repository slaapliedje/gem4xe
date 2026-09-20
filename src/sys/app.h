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
 * both regions back: the pool and the far heap are bump allocators, so an
 * application is released by winding them back to where they were --
 * which is also why applications are released in the reverse order of
 * their loading, or all together.
 *
 * The pool is also the AES's own bank-$00 allocator, for what it must
 * address near and cannot give a static home in a 7.9 KB bank $00: a
 * resource file's objects (src/aes/rsrc.c), the file selector's tree and
 * its work while it is up (src/aes/fsel.c).  Same bump discipline:
 * pool_mark(), take, pool_release() to the mark.
 *
 * WHY A BUMP ALLOCATOR AND NOT A HEAP, since the question is a fair one.
 * Of the nineteen places that take from the pool, thirteen release in the
 * same call they took in -- GEMDOS's slices and directory cache, the
 * selector's working set, an alert's tree -- which is a stack, not a
 * heap.  The other six are lifetimes: a program's near region and its
 * resource, an accessory's, the process records.  With one program
 * running at a time those nest, so a free list would put a header on
 * every one of the nineteen and add fragmentation to serve a case that
 * does not arise.  What DID arise is lifetimes going wrong quietly, and
 * that is what the floor is for:
 *
 *   pool_keep_mark()   everything taken so far is permanent
 *   pool_release(m)    refused, and counted, if m is below that
 *
 * with far_keep_mark() and far_release() the same for the far heap.  The
 * shell sets both once, after the accessories have started and before the
 * first program (src/aes/shel.c).  If gem4xe ever runs two programs at
 * once, THAT is when a real allocator earns its header -- and the seam to
 * put it behind is these four calls.
 */
#ifndef GEM4XE_APP_H
#define GEM4XE_APP_H

#include "portab.h"
#include <stdint.h>

#define APP_OK        0
#define APP_E_MAGIC  -1     /* not a G4A, or a version this loader lacks */
#define APP_E_SHORT  -2     /* the blob ends before the header says */
#define APP_E_POOL   -3     /* no room in the bank-$00 pool */
#define APP_E_FAR    -4     /* no far bank */
#define APP_E_FIXUP  -5     /* a fixup offset outside its part */
#define APP_E_FILE   -6     /* the file would not open (app_load_file) */
#define APP_E_READ   -7     /* it opened, then a read failed partway */
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
    uint16_t pool_mark;     /* what app_free() winds back to */
    uint32_t far_mark;
} APP;

uint16_t pool_mark(void);                          /* the cursor         */
void    *pool_alloc(uint16_t size, uint16_t align); /* 0 when it will not fit */
void     pool_release(uint16_t mark);
uint16_t pool_room(void);

/* Everything taken so far is permanent: no later pool_release() may go
 * below it.  The accessories call it once they have started and taken
 * what they need (src/aes/shel.c), which is what turns "an accessory is
 * loaded before the first program" from an arrangement into a rule the
 * machine keeps.  pool_refused counts the releases turned away -- a
 * number nobody should ever see. */
void     pool_keep_mark(void);
uint16_t pool_floor(void);
extern uint16_t pool_refused;

/* Where the last program app_load() placed its near region.  Only a
 * diagnostic -- nothing in the engine reads it -- but the gates need it
 * now that an accessory is loaded before the first program. */
extern uint16_t app_near;                          /* bytes left          */
extern uint32_t app_far;           /* its far image: large-data globals   */

int16_t app_load(const uint8_t FAR *blob, uint32_t len, APP *app);
int16_t app_exec(const APP *app);
void    app_free(const APP *app);

/* A whole file, by its CIO name, into far memory: where it starts, with
 * its length in *len, or 0 when it would not open or read to its end --
 * and then nothing is kept.  It is taken from the far heap, so what
 * app_free() winds back to decides who owns it.  The file is read
 * through a slice of the pool, which is given back before returning. */
/* APP_OK with *addr and *len set; or APP_E_FILE (it would not open),
 * APP_E_READ (a read failed partway), APP_E_FAR (far memory ran out)
 * or APP_E_SHORT (it was empty), keeping nothing -- but *len still says
 * how far it got. */
int16_t far_read_file(const char *cioname, uint32_t *addr, uint32_t *len);

/* app_load() on a file: the GEM name (X:\DIR\NAME.G4A, or a bare name on
 * the default drive) through the DOS seam, read whole, then loaded.  The
 * file's bytes are left in far memory below the application's and go
 * back with them at app_free(). */
int16_t app_load_file(const char *gemname, APP *app);

#endif /* GEM4XE_APP_H */
