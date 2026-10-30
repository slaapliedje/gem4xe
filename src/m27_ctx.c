/* m27_ctx.c -- the context switch on its own, before anything depends on it.
 *
 * src/sys/ctx.c parks a context by copying its extent of the one engine
 * stack into far memory and copying it back at the same addresses when
 * the context runs again.  Two things have to be true for that to be
 * worth building on, and neither of them is visible from the outside of
 * a working desktop:
 *
 *   THE TURNS HAPPEN IN THE ORDER THEY WERE ASKED FOR.  The runner
 *   records who ran, in sequence, in a plain array the host reads by
 *   symbol.  A switch that silently did nothing, or that came back to
 *   the wrong context, shows up as a different sequence and not as a
 *   crash.
 *
 *   A FRAME SURVIVES A SWITCH FROM UNDERNEATH IT.  A context that
 *   switches at the bottom of a recursion has to find its locals intact
 *   on the way back out, at every level.  So one of the two contexts
 *   recurses, writes a value derived from the depth into a local and
 *   into an array, switches away from the deepest frame, and checks each
 *   local against the array as the recursion unwinds.  That is the whole
 *   claim the design rests on -- the extent goes back to the SAME
 *   addresses, so a pointer into a frame is still the address it was --
 *   and a copy that were off by one byte, or short, would fail it.
 *
 * The runner also leaves the measured park sizes where the gate can
 * print them: what a switch actually costs is a number this project
 * would rather measure than argue about.
 */
#include "portab.h"
#include <stdint.h>
#include "sys/ctx.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"

#define STATUS ((volatile unsigned char *) 0x0600)

/* The call gate's own words.  A context carries them (src/sys/ctx.c) and
 * src/sys/abi.s reaches for them, so linking app_run -- which is how a
 * context enters its program -- means defining them.  The engine behind
 * them is not here and does not need to be: this runner executes no COP,
 * and gem_entry is the proof that it does not.  Reaching it is a failure
 * the gate can see, not a crash. */
uint32_t gem_pb;
uint8_t  gem_which;
uint16_t gem_api_sp;
uint8_t  gem_depth;
uint16_t gem_calls;
uint16_t gem_bad;
uint8_t  gem_cop_pass;      /* abi.s reads it for a COP that is not gem4xe's */
uint8_t  gem_term;          /* ...and this after every call it serves */
uint16_t gem_caller_sp;     /* ...and this on the way in (the stack check) */
uint16_t gem_reached;

void gem_entry(void)
{
    gem_reached++;
}

#define ROUNDS  5           /* turns each of the two contexts takes */
#define DEEP    6           /* frames the recursing context builds */

/* Who ran, in order: 1 and 2 are the two contexts, 0 is the root. */
uint16_t seq[32];
uint16_t nseq;

/* The recursion's evidence: what each level wrote, and what it still
 * held after the switch. */
uint16_t deep_put[DEEP];
uint16_t deep_got[DEEP];
uint16_t deep_bad;          /* levels whose local did not survive */

uint16_t ctx_done;          /* the runner reached the end */
uint16_t rounds_a, rounds_b;

CTX c_root, c_a, c_b;

static void note(uint16_t who)
{
    if (nseq < 32)
        seq[nseq++] = who;
}

/* Down DEEP frames, switch away from the bottom, and check every level
 * on the way back up.  The local is deliberately kept live across the
 * call so the compiler cannot spill it somewhere that is not the stack. */
static void recurse(uint16_t level)
{
    uint16_t mine = (uint16_t)(0xC000 + level * 7);

    deep_put[level] = mine;
    if (level + 1 < DEEP)
        recurse((uint16_t)(level + 1));
    else
        ctx_switch(&c_b);           /* the deepest frame yields */
    deep_got[level] = mine;
    if (mine != (uint16_t)(0xC000 + level * 7))
        deep_bad++;
}

static int16_t proc_a(void)
{
    uint16_t i;

    for (i = 0; i < ROUNDS; i++) {
        note(1);
        rounds_a++;
        ctx_switch(&c_b);
    }
    recurse(0);
    note(0x11);
    return 0;                       /* done: ctx_boot hands back to the root */
}

static int16_t proc_b(void)
{
    for (;;) {
        note(2);
        rounds_b++;
        ctx_switch(&c_a);
    }
}

TASK void main(void)
{
    STATUS[0] = 'C';
    STATUS[1] = 'X';
    STATUS[2] = 0;

    farmem_probe();
    if (farmem.kind == FARMEM_NONE) {
        STATUS[2] = 0xFF;
        for (;;)
            ;
    }

    /* The root gets a save area like any other context: without one its
     * parked stack goes to far address 0, which is bank $00's zero page.
     * This gate did not notice for three runs, because a runner that
     * spins in a loop afterwards never asks the OS for anything. */
    if (!ctx_make(&c_root, 0)) {
        STATUS[2] = 0xFE;
        for (;;)
            ;
    }
    ctx_init(&c_root);
    if (!ctx_make(&c_a, (uint32_t)proc_a) ||
        !ctx_make(&c_b, (uint32_t)proc_b)) {
        STATUS[2] = 0xFE;
        for (;;)
            ;
    }

    note(0);
    ctx_switch(&c_a);               /* comes back when proc_a returns */
    note(0);
    ctx_done = 1;
    STATUS[2] = 1;
    for (;;)
        ;
}
