/* ctx6502.c -- the bookkeeping half of the 6502's context switch.
 *
 * src/sys/ctx.c is the 65C816's; the shape is the same (src/sys/ctx.h),
 * with two stacks to park instead of one: the 6502's page 1 and Calypsi's
 * C stack under _Vsp (src/sys6502/ctx6502.s).  Both extents go into the
 * context's one far buffer, page 1's first.
 *
 *   ctx_park()   runs on the OUTGOING stacks and copies [S+1 .. hbase]
 *                and [_Vsp .. vbase) out; its own frames are below both.
 *   ctx_unpark() runs with both pointers ALREADY the incoming context's
 *                and copies its extents back; its frames are below those.
 *
 * What does not travel here, yet: the call gate's per-call words, which
 * a 6502 program does not have until step 5 decides how it calls the
 * system.  Whose far blocks a program takes does (far_owner, far_tag).
 *
 * In a bank of its own program's choosing (A6: `evt`; tools/bsp6502/
 * rules.mk): 1 KB that resident memory has not got.  ctx6502.s says why
 * that is safe.
 */
#define GEM4XE_CTX6502                  /* the 6502's CTX, on a host too */
#include "sys/ctx.h"
#include "sys/farmem.h"

/* ctx_cur is src/sys6502/stub6502.c's, where the VDI's link finds it. */
CTX      *ctx_root;
uint16_t  ctx_base;             /* the C stack's top, for the gate */
uint16_t  ctx_over;             /* parks refused: a bug counter */
uint16_t  ctx_regs_want;

/* src/sys6502/ctx6502.s */
extern uint8_t  ctx_sp_in, ctx_sp_out, ctx_hbase;
extern uint16_t ctx_vsp_in, ctx_vsp_out, ctx_vbase;
extern const uint16_t ctx_reg_lo, ctx_reg_hi;
#define CTX_REGS    54          /* must match ctx6502.s */

int16_t ctx_regs_ok(void)
{
    ctx_regs_want = (uint16_t)(ctx_reg_hi - ctx_reg_lo);
    return ctx_regs_want <= CTX_REGS;
}

void ctx_start0(CTX *first)
{
    ctx_cur = ctx_root = first;
    ctx_base = ctx_vbase;
    first->sp = ctx_hbase;
    first->vsp = ctx_vbase;
    first->len = 0;
    first->vlen = 0;
    first->live = CTX_LIVE;
}

int16_t ctx_make(CTX *c, uint32_t entry)
{
    uint32_t save = far_alloc(CTX_MAX);

    if (!save)
        return 0;
    c->save = save;
    c->deep = 0;
    ctx_reset(c, entry);
    return 1;
}

void ctx_reset(CTX *c, uint32_t entry)
{
    c->sp = 0;
    c->len = 0;
    c->vsp = 0;
    c->vlen = 0;
    c->entry = entry;
    c->live = CTX_NEW;
    c->pb = 0;
    c->api_sp = 0;
    c->which = 0;
    c->depth = 0;
    c->floor = 0;
}

/* From ctx_switch, with the outgoing pointers in ctx_sp_in / ctx_vsp_in.
 * 0: `to` never ran; 1: resume it at ctx_sp_out / ctx_vsp_out; 2: refused,
 * nothing moved. */
uint16_t ctx_park(CTX *to)
{
    CTX *from = ctx_cur;
    uint16_t sp = ctx_sp_in;            /* bytes widened unsigned: exact */
    uint16_t hb = ctx_hbase;
    uint16_t len = (uint16_t)(hb - sp);
    uint16_t vsp = ctx_vsp_in;
    uint16_t vlen = (uint16_t)(ctx_vbase - vsp);

    if (!from->save || sp > hb || vsp > ctx_vbase ||
        (uint16_t)(len + vlen) > CTX_MAX) {
        /* nowhere to park it, or a switch from above the marks: either
         * would write over something.  Stay put, and count it. */
        ctx_over++;
        return 2;
    }
    from->sp = sp;
    from->len = len;
    from->vsp = vsp;
    from->vlen = vlen;
    if ((uint16_t)(len + vlen) > from->deep)
        from->deep = (uint16_t)(len + vlen);
    if (len)
        far_put(from->save, (const uint8_t *)(0x0101 + sp), len);
    if (vlen)
        far_put(from->save + len, (const uint8_t *)vsp, vlen);

    ctx_cur = to;
    far_owner = (uint8_t)to->owner;
    far_tag = (uint8_t)(to->owner >> 8);
    if (to->live == CTX_NEW)
        return 0;
    ctx_sp_out = (uint8_t)to->sp;
    ctx_vsp_out = to->vsp;
    return 1;
}

/* From ctx_switch, both pointers already the incoming context's. */
void ctx_unpark(void)
{
    CTX *c = ctx_cur;

    if (c->len)
        far_get((uint8_t *)(0x0101 + c->sp), c->save, c->len);
    if (c->vlen)
        far_get((uint8_t *)c->vsp, c->save + c->len, c->vlen);
}

/* A context's first turn, at the top of both stacks.  Its entry is a
 * function's address -- a resident one, which a banked function's is
 * (its veneer: tools/bsp6502/bankasm.py).  If the program returns, the
 * context is done, what it returned is kept in `entry`, and the root
 * gets the processor back. */
void ctx_boot(void)
{
    CTX *c = ctx_cur;
    int16_t (*run)(void) = (int16_t (*)(void))(uint16_t)c->entry;

    c->live = CTX_LIVE;
    c->entry = (uint32_t)(uint16_t)run();
    c->live = CTX_DONE;
    for (;;)
        ctx_switch(ctx_root);
}
