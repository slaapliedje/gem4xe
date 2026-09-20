/* clock.c -- a clock for gem4xe, whole.
 *
 * The other half of the pair calc.c belongs to, and deliberately not
 * written the same way.  A calculator can sit in form_do and wait; a
 * clock cannot, because form_do does not come back until something is
 * pressed and a clock has to say something every second.  So this one
 * runs the loop a GEM program normally runs: evnt_multi with a timer
 * and the button, objc_find for what was under the pointer, and its own
 * redraw of the fields that changed.  Between them the two programs
 * cover both shapes an application takes.
 *
 * WHERE THE TIME COMES FROM.  GEMDOS answers Tgettime and Tgetdate, and
 * on this machine that is the Ultimate 1MB's DS1305 (src/sys/clock.c).
 * A machine without one answers the ST's dead-clock epoch -- midnight
 * on 1 January 1980 -- and answers it again a second later, so a clock
 * that only asked GEMDOS would never move.  This one asks once, then
 * counts its own seconds off the AES's timer and asks again every
 * minute to correct the drift: it shows the right time on a machine
 * that knows it, and a stopwatch from midnight on one that does not.
 *
 * The two fields are filled through their TEMPLATES (tools/clockrsc.py):
 * the runs of underscores take the numbers in the order the resource
 * puts them, so a translation may write the date the other way round
 * and nothing here changes.  It is the desktop's text-view rule
 * (docs/phase27.md) in a smaller place.
 */
#include "gem.h"
#include "clockrsc.h"

#define TICK_MS   1000                      /* what the timer is asked for */
#define RESYNC    60                        /* ticks between GEMDOS reads */

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];

static OBJECT *tree;
static WORD hour, minute, second;
static WORD day, month, year;               /* year is the century's two */

static char *field(WORD obj)
{
    TEDINFO *ted = (TEDINFO *)(uint32_t)tree[obj].ob_spec.index;

    return (char *)(uint32_t)ted->te_ptext;
}

/* Three numbers into the runs of underscores of a field's template, in
 * the template's order: the resource decides the separators and the
 * order, this decides only what the numbers are. */
static void fill(WORD obj, WORD a, WORD b, WORD c)
{
    TEDINFO *ted = (TEDINFO *)(uint32_t)tree[obj].ob_spec.index;
    const char *t = (const char *)(uint32_t)ted->te_ptmplt;
    char *d = field(obj);
    WORD v[3], n = 0, i = 0;

    v[0] = a;
    v[1] = b;
    v[2] = c;
    while (t[i]) {
        if (t[i] != '_') {
            d[i] = t[i];
            i++;
            continue;
        }
        {                                   /* the run, and the number in it */
            WORD run = 0, k;

            while (t[i + run] == '_')
                run++;
            for (k = run; k > 0; k--) {
                d[i + k - 1] = (char)('0' + (n < 3 ? v[n] % 10 : 0));
                if (n < 3)
                    v[n] /= 10;
            }
            n++;
            i += run;
        }
    }
    d[i] = 0;
}

/* What GEMDOS says, into the six numbers. */
static void ask_gemdos(void)
{
    WORD t = Tgettime(), d = Tgetdate();

    hour = (WORD)((t >> 11) & 0x1F);
    minute = (WORD)((t >> 5) & 0x3F);
    second = (WORD)((t & 0x1F) * 2);
    day = (WORD)(d & 0x1F);
    month = (WORD)((d >> 5) & 0x0F);
    year = (WORD)((((d >> 9) & 0x7F) + 80) % 100);
}

/* ...and one second later.  A day that rolls over is the only carry
 * worth doing here: the date comes back from GEMDOS at the next resync
 * and this keeps the fields sane until then. */
static void tick(void)
{
    if (++second < 60)
        return;
    second = 0;
    if (++minute < 60)
        return;
    minute = 0;
    if (++hour < 24)
        return;
    hour = 0;
}

/* The resource, once.  It is a separate call from the panel because the
 * two happen at different times in an accessory: src/apps/clockacc.c
 * takes the resource while the AES is starting up -- before the first
 * program, which is the only time an accessory may take anything from
 * bank $00 -- and opens the panel later, whenever somebody chooses it
 * from the Desk menu. */
WORD clock_start(void)
{
    if (!rsrc_load("CLOCK.RSC"))
        return FALSE;
    rsrc_gaddr(R_TREE, ADCLOCK, (void **)&tree);
    return TRUE;
}

/* A workstation of its own.  The caller decides how long to keep it: the
 * program opens one around its single panel, the accessory opens one at
 * start-up and holds it for the life of the machine, which it can do
 * because a virtual workstation belongs to the process that opened it and
 * a program ending closes only its own (src/vdi/vdi.c). */
WORD clock_ws(void)
{
    WORD handle, wchar, hchar, wbox, hbox;

    handle = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &handle, work_out);
    return handle;
}

/* The panel, and the loop it runs until a key or Quit, on a workstation
 * the caller has already opened.  Returns when the clock has been put
 * away and the screen given back. */
void clock_panel(WORD handle)
{
    WORD done = FALSE, ticks = 0;
    WORD x, y, w, h, ev, mx, my, mb, ks, kr, br, msg[8];

    (void)handle;
    ask_gemdos();

    form_center(tree, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_GROW, 0, 0, 0, 0, x, y, w, h);
    fill(KTIME, hour, minute, second);
    fill(KDATE, day, month, year);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, w, h);

    while (!done) {
        ev = evnt_multi_moblk((UWORD)(MU_TIMER | MU_BUTTON | MU_KEYBD),
                        1, 1, 1, 0, 0, msg, TICK_MS, 0,
                        &mx, &my, &mb, &ks, &kr, &br);
        if (ev & MU_TIMER) {
            tick();
            if (++ticks >= RESYNC) {        /* the clock is the authority */
                ticks = 0;
                ask_gemdos();
                fill(KDATE, day, month, year);
                objc_draw(tree, KDATE, 0, x, y, w, h);
            }
            fill(KTIME, hour, minute, second);
            objc_draw(tree, KTIME, 0, x, y, w, h);
        }
        if (ev & MU_KEYBD)
            done = TRUE;                    /* any key */
        if ((ev & MU_BUTTON)
            && objc_find(tree, ROOT, MAX_DEPTH, mx, my) == KQUIT)
            done = TRUE;
    }

    form_dial(FMD_SHRINK, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}
