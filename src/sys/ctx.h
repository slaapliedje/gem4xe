/* ctx.h -- one engine stack, shared by turns.
 *
 * A desk accessory is a second program resident beside the first, and
 * GEM's own answer to "how does it get the processor" is a process with
 * its own stack that blocks inside evnt_multi while the dispatcher runs
 * somebody else (EmuTOS aes/gemdisp.c, aes/gemasm.S).  gem4xe cannot
 * copy that shape directly, and the reason is measured rather than
 * argued: the engine's stack is 2 KB and the gates find most of it used
 * at the low-water mark -- 1,660 bytes on 2026-09-22 (test-m17 prints
 * the number, so read it there rather than trusting this line) -- with
 * a few hundred bytes free in LoRAM, and 1,024 of what looks spare is
 * reserved anyway for a child's calls under a Pexec (GD_PEXEC_STACK,
 * src/sys/gemdos.c).  There is no room in bank $00 for a second one.
 *
 * Nor may a second one live anywhere else.  An application's OWN stack
 * is in the pool at $4800 and that is safe, because of an invariant the
 * map relies on without ever having had to say it: whenever a DOS may
 * have banked its own RAM over $4000-$7FFF, S is in $2000-$3FFF, since
 * the call gate moved it there on the way in (src/sys/abi.s).  An
 * engine stack in the pool would break that the first time an accessory
 * asked GEMDOS for anything.
 *
 * So the contexts SHARE the one stack and take turns on it.  A context
 * that is not running has its extent of that stack parked in far
 * memory; resuming it copies the extent back to the same addresses,
 * which is what makes it safe -- every pointer into a stack frame is
 * still the address it was.  The cost is proportional to the depth AT
 * THE MOMENT OF THE SWITCH, not to the 2 KB: a switch happens at one
 * place only, ev_poll(), where the engine is a handful of frames deep,
 * and the gate prints what it measured.
 *
 * WHAT A CONTEXT IS.  Everything from `base` down: base is S at
 * ctx_init(), so the shell's own loop and everything it calls belongs to
 * the context that ran it, and whatever called ctx_init belongs to
 * nobody and is never copied.  Nothing may switch contexts above base.
 *
 * WHAT TRAVELS WITH IT.  The stack, and the call gate's per-call words
 * (src/sys/abi.c): a switch happens INSIDE a COP -- ev_poll is reached
 * through evnt_multi -- so the block being served, which call it is, how
 * deep the gate is and where the gate resumes are all per context.
 * Nothing else here: the AES's own per-process state is the AES's
 * business (src/aes/proc.c).
 */
#ifndef GEM4XE_CTX_H
#define GEM4XE_CTX_H

#include "portab.h"
#include <stdint.h>

#define CTX_NEW     0       /* made, never entered */
#define CTX_LIVE    1       /* running, or parked with a stack to come back to */
#define CTX_DONE    2       /* its program returned */

typedef struct {
    uint16_t sp;        /* engine S while parked; meaningless while running */
    uint32_t save;      /* far: where the parked extent lives */
    uint16_t len;       /* bytes parked -- what the last switch cost */
    uint16_t deep;      /* the most it has ever parked: for the gate to print */
    uint32_t entry;     /* the program, entered the first time it is resumed */
    uint16_t live;      /* CTX_NEW / CTX_LIVE / CTX_DONE */
    /* the call gate's per-call words, which a park interrupts */
    uint32_t pb;
    uint16_t api_sp;
    uint16_t which;     /* a word, not a byte: the assembly never sees this */
    uint16_t depth;
} CTX;

extern CTX      *ctx_cur;       /* the running one; never 0 after ctx_init */
extern CTX      *ctx_root;      /* context 0: where a finished one returns */
extern uint16_t  ctx_base;      /* the top of the shared extent */
/* ...and the bottom of the stack it is in, from the linker (ctx.s): what
 * Pexec measures its child's room against (src/sys/gemdos.c). */
extern const uint16_t ctx_stack_lo;
extern uint16_t  ctx_over;      /* parks refused for want of room -- a bug */

/* The caller becomes context 0.  `first` is its record, which must
 * outlive every switch; the shell's records come from the pool.
 *
 * CALL IT FROM THE SHALLOWEST PLACE THAT WILL EVER SWITCH.  The mark it
 * takes is its own caller's S, and no context may ever park above that
 * mark -- src/sys/ctx.s says what happens if one tries. */
SIMPLE_CALL void ctx_init(CTX *first);

/* FALSE when the compiler's register file has outgrown what a switch
 * carries -- see src/sys/ctx.s.  Ask before ctx_init and refuse to run;
 * ctx_regs_want is what the linker says it is. */
int16_t ctx_regs_ok(void);
extern uint16_t ctx_regs_want;

/* Room in far memory for one context's extent, and the record zeroed.
 * FALSE if the far heap has none.  `entry` is the program it runs the
 * first time it is resumed; it is expected never to return. */
int16_t ctx_make(CTX *c, uint32_t entry);

/* Park the running context and resume `to`.  Returns -- in `to` -- from
 * the ctx_switch() that parked IT, or, the first time, by entering its
 * program.  A context whose program returns is marked done and the
 * caller of ctx_switch is resumed instead. */
SIMPLE_CALL void ctx_switch(CTX *to);

#endif /* GEM4XE_CTX_H */
