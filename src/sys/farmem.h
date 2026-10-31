/* farmem.h -- linear memory above bank $00: FARMEM, the allocator, and the
 * helpers that reach it.
 *
 * Which banks are RAM, and ours, is found by the probe -- src/sys/hiprobe.c
 * and hiprobe.h, the Atari's part -- which fills FARMEM and starts the
 * allocator.  Nothing here knows the machine.
 */
#ifndef GEM4XE_FARMEM_H
#define GEM4XE_FARMEM_H

#include <stdint.h>
#include "portab.h"

#define FARMEM_NONE     0   /* no linear RAM -- gem4xe cannot run */
#define FARMEM_RAPIDUS  1
#define FARMEM_UNKNOWN  2   /* linear RAM found, board not identified */

typedef struct {
    uint8_t  kind;
    uint8_t  first_bank;    /* lowest usable bank */
    uint8_t  last_bank;     /* highest usable bank, inclusive */
    uint8_t  banks;         /* count of usable banks */
    uint32_t bytes;         /* banks * 64K */
    uint8_t  taken;         /* banks the OS's allocator says are in use */
} FARMEM;

extern FARMEM farmem;

/* The allocator (farmem.c, "THE ALLOCATOR"): blocks in a table, each with
 * an owner, freed singly or by owner in any order.  0 on failure. */
extern uint8_t  far_owner;              /* whose the next block is; 0 system */
/* ...and its TAG (phase 119): what kind of owner, and which of its
 * sub-pools -- GS/OS's user ID without the main part, which is far_owner.
 * A block carries both; far_free_owner frees an owner whatever the tag,
 * far_free_sub one sub-pool of it.  src/sys/ctx.c keeps both right. */
extern uint8_t  far_tag;
#define OWN_SYSTEM  0                   /* the kinds, in the tag's top nibble */
#define OWN_APP     1                   /* a program, the desktop's children */
#define OWN_ACC     2                   /* a desk accessory */
#define OWN_CPX     3                   /* a control panel module */
#define OWN_DESK    4                   /* the desktop */
#define OWN_AUTO    5                   /* an AUTO folder program */
#define OWN_TAG(kind, sub)  ((uint8_t)(((kind) << 4) | ((sub) & 0x0F)))
#define OWN_KIND(tag)       ((uint8_t)((tag) >> 4))
#define OWN_SUB(tag)        ((uint8_t)((tag) & 0x0F))
extern uint16_t far_blocks;             /* the table's length, and where */
extern uint32_t far_table;              /* it is -- for the gates */
void     far_heap_clear(void);          /* no heap yet: the probe's start */
void     far_heap_init(void);           /* farmem_probe calls it */
uint32_t far_alloc(uint32_t bytes);     /* never crosses a bank */
/* ...and one that MAY cross, for a file read in whole (far_read_file).
 * A FAR POINTER'S ARITHMETIC IS 16 BITS on this compiler, so what lives
 * in a span must be reached by recomputing the address -- far_read8,
 * far_write8, far_put_span, far_copy_span -- and never by walking a
 * pointer over the boundary.  The reasoning is in farmem.c. */
uint32_t far_alloc_span(uint32_t bytes);
/* ...the same at the top of the highest gap it fits: a moment's block. */
uint32_t far_alloc_top(uint32_t bytes);
/* Page-aligned, and ending at or below `limit` within its bank. */
uint32_t far_alloc_page(uint32_t bytes, uint32_t limit);
/* Exactly at..at+bytes, all of it free heap, or 0: Mclaim's. */
uint32_t far_claim(uint32_t at, uint32_t bytes);
uint16_t far_alloc_banks(uint16_t n);   /* n whole banks, the lowest free
                                         * run: the first bank's number, 0 on
                                         * failure */
uint16_t far_free(uint32_t addr);       /* 1 if addr was a block */
uint16_t far_keep(uint32_t addr);       /* ...and the system's from now on */
void     far_free_owner(uint8_t owner); /* every block of one owner */
void     far_free_sub(uint8_t owner, uint8_t sub); /* ...of one sub-pool, 1-15 */
uint16_t far_shrink(uint32_t addr, uint32_t bytes);  /* smaller, in place */
/* PURGE LEVELS (phase 120): 0 never, 1-3 given up when a request would
 * otherwise fail -- level 3 first, then 2, then 1, each tried again after
 * -- and named to far_purge_hook as they go, so a cache forgets them.  A
 * block in use is set to 0 first and back after. */
uint16_t far_set_purge(uint32_t addr, uint16_t level);   /* 1 if a block */
extern void (*far_purge_hook)(uint32_t addr);
extern uint16_t far_purged;             /* blocks purged, for the gates */
uint32_t far_size(uint32_t addr);       /* a block's length, 0 if none */
uint32_t far_largest(uint16_t span);    /* the biggest request that fits */
uint8_t  far_new_owner(void);           /* an owner with no blocks yet */

void     far_write8(uint32_t addr, uint8_t v);
uint8_t  far_read8(uint32_t addr);
void     far_put(uint32_t dst, const uint8_t *src, uint16_t len);
void     far_get(uint8_t *dst, uint32_t src, uint16_t len);
void     far_copy(uint32_t dst, uint32_t src, uint16_t len);
/* The same two for a far_alloc_span block, which may cross a bank. */
void     far_put_span(uint32_t dst, const uint8_t *src, uint16_t len);
void     far_copy_span(uint32_t dst, uint32_t src, uint32_t len);
void     far_fill(uint32_t dst, uint8_t v, uint16_t len);
void     far_strget(char *dst, uint32_t src, uint16_t max);   /* bounded strcpy, */
void     far_strput(uint32_t dst, const char *src, uint16_t max); /* NUL always */

#endif /* GEM4XE_FARMEM_H */
