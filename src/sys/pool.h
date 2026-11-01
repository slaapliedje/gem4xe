/* pool.h -- bank $00's application pool: owned blocks, freed in any order.
 *
 * The pool is the bank-$00 memory src/gem4xe.scm sets aside (apppool; the
 * bounds come from the linker through src/sys/apppool.s): a program's
 * near region -- its direct page, stack and data -- and what the AES must
 * address near and cannot give a static home: a resource file's objects
 * (src/aes/rsrc.c), the file selector's work (src/aes/fsel.c), an alert's
 * tree, GEMDOS's read slices, the process records.
 *
 * TWO KINDS OF REQUEST, because the pool has two kinds of user.  Of the
 * nineteen places that take from it, thirteen give back in the same call
 * they took in -- a stack -- and six hold memory for a lifetime: a
 * program's near region and its resource, an accessory's, its queue, the
 * process records.  Until phase 117 both were one bump cursor, wound
 * back to a mark, which is why accessories had to load before the first
 * program and nothing could be freed out of order.
 *
 *   pool_alloc(n, a)   at the TOP, always: the stack's kind.  What it
 *                      gives is above pool_mark(), so pool_release(mark)
 *                      gives it back.
 *   pool_take(n, a)    the LOWEST place it fits, a hole a freed block
 *                      left included: the lifetime's kind.  Given back by
 *                      pool_free() or pool_free_owner(), not by a mark.
 *
 * EVERY BLOCK HAS AN OWNER, far_owner's at the time it was taken, and
 * far_tag's kind and sub-pool with it (phase 119) -- the
 * far heap's owners (src/sys/farmem.c), so a program's blocks in both
 * allocators are one owner's, and src/sys/ctx.c keeps far_owner right at
 * every switch.  pool_release(mark) gives back only the CURRENT owner's
 * blocks above the mark, and cuts one of them that straddles it short:
 * an accessory that took a block while a program's file selector was up
 * keeps it when the selector's work goes.  app_free() frees a program by
 * its owner.
 *
 * pool_mark() is an ADDRESS, the top of the highest block, as the cursor
 * was: the gates place their models' trees at it (tools/aesref.py), and
 * the DOS command's MEMLO is it (src/sys/dos.c).  With no block freed out
 * of order -- which is every flow before phase 117 -- every block lands
 * where the cursor put it, byte for byte.
 *
 * THE FLOOR stays: pool_keep_mark() says everything below the top now is
 * permanent, and a pool_release() to a mark under it is refused and
 * counted in pool_refused, a number nobody should ever see (test-boot
 * reads it).  The shell sets it once, after the accessories have started
 * and before the first program (src/aes/shel.c).
 *
 * The table is POOL_MAX entries in zwin (src/sys/zwin.h), not in the pool
 * itself, so the pool's addresses are the ones they always were;
 * tools/poolref.py is the same rules in Python, held to this file by
 * tests/host/test_pool.py.
 */
#ifndef GEM4XE_POOL_H
#define GEM4XE_POOL_H

#include "portab.h"
#include <stdint.h>

#define POOL_MAX 32                 /* blocks: docs/phase117.md has the counts */

uint16_t pool_mark(void);           /* the top of the highest block */
void    *pool_alloc(uint16_t size, uint16_t align); /* 0 when it will not fit */
void    *pool_take(uint16_t size, uint16_t align);  /* ...nor in any hole */
void     pool_release(uint16_t mark);
void    *pool_claim(uint16_t at, uint16_t size);    /* exactly there, or 0 */
uint16_t pool_free(void *block);    /* 1 if it was a block, 0 if not */
void     pool_free_owner(uint8_t owner);            /* 0, the system: no-op */
void     pool_free_sub(uint8_t owner, uint8_t sub); /* one sub-pool, 1-15 */
uint16_t pool_room(void);           /* above the top: what pool_alloc has */

void     pool_keep_mark(void);
uint16_t pool_floor(void);
extern uint16_t pool_refused;
extern uint16_t pool_full;          /* takes refused for a full table */
extern uint16_t pool_blocks;

#endif /* GEM4XE_POOL_H */
