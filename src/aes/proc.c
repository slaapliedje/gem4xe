/* proc.c -- who runs next.  See proc.h for the shape and src/sys/ctx.h
 * for the stack half.
 *
 * This is deliberately the smallest scheduler that is still GEM's: a
 * round robin over the processes that can go, entered from one place,
 * with no pre-emption and no timer.  The donor's is the same round robin
 * with the queues and event blocks broken out into lists; the lists earn
 * their keep at a dozen processes and cost more than they save at four.
 */
#include <string.h>
#include "aes/proc.h"

PROC *proc_tab;
PROC *proc_input;
WORD  proc_n;
WORD  proc_turns;   /* turns handed over: a measurement, not a gate */

/* event.c's, so that the application keeps the queue it always had --
 * sixteen messages in the banked window -- and only an accessory pays
 * the pool for one. */
extern WORD *gl_appqueue(WORD *max);

WORD proc_init(void *store)
{
    WORD i, max;

    proc_tab = (PROC *)store;
    if (!proc_tab)
        return FALSE;
    for (i = 0; i < NUM_PROCS; i++) {
        PROC *p = &proc_tab[i];
        /* EVERY field, not the ones this loop names.  The record comes
         * from memory nobody cleared, and a field left out is whatever was
         * there before: p_rsc and p_rsc2 were, so a process could start
         * with two resources it never loaded, and rs_load refuses a third.
         * Under SpartaDOS X that memory is zero until 65816.SYS loads, and
         * then holds bytes of the driver -- and the desktop said
         * DESKTOP.RSC was not on the boot disk (docs/phase41.md). */
        memset(p, 0, sizeof *p);
        /* ...and the name is BLANKS, which zero is not.  A record full of
         * zeroes compares equal to the empty string over its whole width,
         * so appl_find("") would answer 0 -- a pid, and a wrong one. */
        memset(p->p_name, ' ', AP_NAMELEN);
        p->p_stat = P_FREE;
        p->p_evwait = 0;
        p->p_tdead = 0;
        p->p_queue = 0;
        p->p_qmax = p->p_qcount = 0;
        p->p_bwactive = p->p_bwwant = p->p_bwdone = p->p_bwclicks = 0;
        p->p_bwparm = 0;
    }
    proc_tab[0].p_stat = P_LIVE;
    proc_tab[0].p_queue = gl_appqueue(&max);
    proc_tab[0].p_qmax = max;
    proc_n = 1;
    proc_input = proc_tab;
    return TRUE;
}

WORD proc_pid(const PROC *p)
{
    return (WORD)(p - proc_tab);
}

PROC *proc_of(WORD pid)
{
    if (pid < 0 || pid >= proc_n || proc_tab[pid].p_stat == P_FREE)
        return 0;
    return &proc_tab[pid];
}

PROC *proc_new(WORD *queue, WORD qmax)
{
    PROC *p;
    WORD *q = queue;

    if (proc_n >= NUM_PROCS || !q)
        return 0;
    p = &proc_tab[proc_n];
    p->p_queue = q;
    p->p_qmax = qmax;
    p->p_qcount = 0;
    p->p_rsc = p->p_rsc2 = 0;          /* a new process has no resource yet */
    p->p_rscmark = p->p_rscmark2 = 0;
    memset(p->p_name, ' ', AP_NAMELEN);   /* not the last tenant's */
    p->p_stat = P_NEW;
    proc_n++;
    return p;
}

/* The donor's sh_name() and p_nameit() in one (gemshlib.c, gempd.c):
 * the last component of the path, its first eight characters, stopping
 * at the extension and padded out with blanks.  One function rather than
 * two because gem4xe has no other caller for either half -- and because
 * two cannot then be called in the wrong order. */
void proc_name(PROC *p, const char *path)
{
    const char *name = path, *s;
    WORD i;

    for (s = path; *s; s++)
        if (*s == '\\' || *s == '/' || *s == ':')
            name = s + 1;
    for (i = 0; i < AP_NAMELEN && name[i] && name[i] != '.'; i++)
        p->p_name[i] = name[i];
    for (; i < AP_NAMELEN; i++)
        p->p_name[i] = ' ';
}

/* The donor's fpdnm(pname, 0), over the records in use -- and P_FREE is
 * skipped inside that range too.  proc_drop() only ever gives back the
 * LAST record and winds proc_n back with it, so there should be no free
 * record below proc_n; the test costs a compare and means a name can
 * never be answered for a record nobody is running. */
PROC *proc_byname(const char *name)
{
    WORD i;

    for (i = 0; i < proc_n; i++)
        if (proc_tab[i].p_stat != P_FREE
            && strncmp(name, proc_tab[i].p_name, AP_NAMELEN) == 0)
            return &proc_tab[i];
    return 0;
}

/* Give back the record proc_new() just handed out, when the load it was
 * for did not happen.  Only the last one: the table is filled in order
 * and nothing has a pointer to this record yet. */
void proc_drop(PROC *p)
{
    if (p == &proc_tab[proc_n - 1] && proc_n > 1) {
        p->p_stat = P_FREE;
        p->p_queue = 0;
        p->p_qmax = p->p_qcount = 0;
        proc_n--;
    }
}

WORD proc_ready(const PROC *p)
{
    if (p->p_stat == P_NEW)
        return TRUE;                /* it has never had its first turn */
    if (p->p_stat != P_LIVE)
        return FALSE;
    if (p == proc_input)
        return TRUE;                /* it can always look at the input */
    if (p->p_evwait == 0)
        return TRUE;                /* parked outside a wait: not waiting */
    if ((p->p_evwait & MU_MESAG) && p->p_qcount)
        return TRUE;
    if ((p->p_evwait & MU_TIMER) && gl_ticks >= p->p_tdead)
        return TRUE;
    return FALSE;
}

/* Give every other process a turn until none of them has a message left
 * unread, or until `rounds` turns have gone by -- the donor's
 * wait_for_accs, which blocks appl_exit until every accessory has taken
 * its AC_CLOSE out of the queue.
 *
 * The bound is what stops an accessory that has stopped reading from
 * hanging the machine: the donor gives up after 500 dispatcher rounds
 * and abandons it.  A round here is a context switch and a stack copy
 * rather than a register swap, so the number is smaller and the reason
 * is the same. */
void proc_drain(WORD rounds)
{
    WORD i;

    while (rounds-- > 0) {
        PROC *busy = 0;

        for (i = 1; i < proc_n; i++)
            if (proc_tab[i].p_stat == P_LIVE && proc_tab[i].p_qcount) {
                busy = &proc_tab[i];
                break;
            }
        if (!busy)
            return;
        proc_turns++;
        ctx_switch(&busy->p_ctx);
    }
}

void proc_yield(void)
{
    PROC *p;
    WORD i, here;

    if (proc_n < 2)
        return;
    if (!rlr->p_evwait)
        return;                     /* not parked on anything: keep going.
                                     * Without this a process between waits
                                     * would hand over and be handed back
                                     * on every poll, and pay two stack
                                     * copies each time for nothing. */
    if (!ct_idle())
        return;                     /* a gesture is in flight: see proc.h */

    /* Round robin from the one after the running process, so that a
     * process that is always ready cannot starve the one behind it. */
    here = proc_pid(rlr);
    for (i = 1; i < proc_n; i++) {
        p = &proc_tab[(here + i) % proc_n];
        if (p != rlr && proc_ready(p)) {
            proc_turns++;
            ctx_switch(&p->p_ctx);
            return;
        }
    }
}
