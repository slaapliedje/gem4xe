/* ctx.c -- the bookkeeping half of the context switch.  See ctx.h for why
 * the contexts share one stack instead of having one each.
 *
 * Everything that can be C is C: the assembly (src/sys/ctx.s) does only
 * what C cannot, which is to read S, to write S, and to return through a
 * stack that arrived after it started.  So no offset into CTX is ever
 * written down twice, and the two halves cannot drift apart.
 *
 * THE ORDER MATTERS, and it is the whole trick:
 *
 *   ctx_park()   runs on the OUTGOING context's stack and copies the
 *                extent [sp+1 .. base] out.  Its own frame is below sp,
 *                so it is not copying itself, and an interrupt taken
 *                while it works pushes below sp as well.
 *   ctx_unpark() runs with S ALREADY MOVED to the incoming context's,
 *                and copies [sp+1 .. base] back.  Its own frame is below
 *                that too, so it is not overwriting itself either.
 *
 * Between the two, the stack the routine started on no longer exists.
 * That is why the middle of a switch is three instructions of assembly
 * and not a function call.
 */
#include "sys/ctx.h"
#include "sys/abi.h"
#include "sys/farmem.h"

/* The whole engine stack: what one context can want at the very most.
 * src/gem4xe.scm gives the stack 2 KB and the gates measure 1,239 bytes
 * of it in use at the deepest, so a park can never exceed this -- but a
 * park is measured, not assumed, and ctx_park refuses one that would. */
#define CTX_MAX     0x0800

CTX      *ctx_cur;
uint16_t  ctx_base;
CTX      *ctx_root;             /* context 0: where a finished one returns */
uint16_t  ctx_over;             /* parks refused for want of room: a bug counter */

extern uint16_t ctx_sp_in;      /* src/sys/ctx.s: S at the switch */

/* The compiler's register file, from the linker (src/sys/ctx.s), and how
 * much of the direct page a switch actually carries.  The two are checked
 * against each other once, at start-up, rather than trusted: a register
 * file that grew past what travels would corrupt the other context in a
 * way nothing else here would notice. */
extern const uint16_t ctx_reg_lo, ctx_reg_hi;
#define CTX_REGS    32          /* must match src/sys/ctx.s */

uint16_t ctx_regs_want;         /* what the linker says: for the gate */

/* The C half of ctx_init(); src/sys/ctx.s has already marked ctx_base
 * with ITS caller's S, which is the shallowest point that can ever
 * switch.  Everything above that mark belongs to no context and is never
 * copied. */
int16_t ctx_regs_ok(void)
{
    ctx_regs_want = (uint16_t)(ctx_reg_hi - ctx_reg_lo);
    return ctx_regs_want <= CTX_REGS;
}

void ctx_start0(CTX *first)
{
    /* Everything but the mark is ctx_make()'s: context 0 is a context
     * like any other and needs somewhere to be parked just as much as
     * the ones it starts.  It did not have one for the first three runs
     * of test-m28, and far_put() to address 0 is bank $00's zero page --
     * the machine survived it in test-m27, which asks the OS for
     * nothing afterwards, and did not survive it in the shell. */
    ctx_cur = ctx_root = first;
    first->sp = ctx_base;
    first->len = 0;
    first->live = CTX_LIVE;
}

int16_t ctx_make(CTX *c, uint32_t entry)
{
    uint32_t save = far_alloc(CTX_MAX);

    if (!save)
        return 0;
    c->sp = 0;
    c->save = save;
    c->len = c->deep = 0;
    c->entry = entry;
    c->live = CTX_NEW;
    c->pb = 0;
    c->api_sp = 0;
    c->which = 0;
    c->depth = 0;
    return 1;
}

/* Called from ctx_switch, which has left the outgoing S in ctx_sp_in.
 * Parks the running context, makes `to` the running one, and answers the
 * S to resume it at -- 0 for "never run: start it at the top", $FFFF for
 * "refused: put nothing back". */
uint16_t ctx_park(CTX *to)
{
    CTX *from = ctx_cur;
    uint16_t sp = ctx_sp_in;
    uint16_t len = (uint16_t)(ctx_base - sp);

    if (from != to) {
        if (!from->save || len > CTX_MAX) {
            /* Neither can happen from ev_poll, and either would corrupt
             * something quietly: a context with nowhere to be parked
             * would write its stack over bank $00's zero page, and one
             * too deep would write over the other context's.  Refuse and
             * stay put; ctx_over is the count nobody should ever see. */
            ctx_over++;
            return 0xFFFF;
        }
        from->sp = sp;
        from->len = len;
        if (len > from->deep)
            from->deep = len;
        if (len)
            far_put(from->save, (const uint8_t *)(sp + 1), len);

        from->pb = gem_pb;
        from->api_sp = gem_api_sp;
        from->which = gem_which;
        from->depth = gem_depth;

        ctx_cur = to;
        far_owner = (uint8_t)to->owner;
        gem_pb = to->pb;
        gem_api_sp = to->api_sp;
        gem_which = (uint8_t)to->which;
        gem_depth = (uint8_t)to->depth;
    }
    return (to->live == CTX_NEW) ? 0 : to->sp;
}

/* Called from ctx_switch with S already the incoming context's. */
void ctx_unpark(void)
{
    CTX *c = ctx_cur;

    if (c->len)
        far_get((uint8_t *)(c->sp + 1), c->save, c->len);
}

/* Called from ctx_switch on a context's first turn, at the top of the
 * stack.  Runs its program; if that ever returns, the context is done
 * and context 0 gets the processor back. */
void ctx_boot(void)
{
    CTX *c = ctx_cur;

    c->live = CTX_LIVE;
    (void)app_run(c->entry);
    c->live = CTX_DONE;
    for (;;)
        ctx_switch(ctx_root);
}
