/* calc.c -- a calculator for gem4xe, whole.
 *
 * The second program written to gem4xe's application ABI and the first
 * that is not a test: it links against nothing of the system's, reaches
 * the AES, the VDI and GEMDOS through the three call gates, and is
 * launched from the desktop like any other .g4a.
 *
 * The whole of it is a form_do loop.  Every key of the panel is a
 * SELECTABLE|EXIT button, so form_do returns the object that was
 * pressed; this program works out what that means, writes the display
 * and goes back in.  The panel is CALC.RSC (tools/calcrsc.py) and every
 * word a person reads is in there, none of it here.
 *
 * IT COUNTS IN WHOLE NUMBERS, on purpose.  There is no floating point
 * anywhere in gem4xe -- no FPU on this machine and no libc linked into
 * an application -- so a division truncates towards zero and says so by
 * showing the remainder in place of the quotient when a key is pressed
 * after it.  A calculator that quietly rounded would be worse than one
 * that is honest about being exact.
 *
 * The accumulator is a LONG.  Ten places hold 2,147,483,647, so entry
 * stops at ten digits and an operation that would pass it leaves the
 * display alone rather than wrapping.
 */
#include "gem.h"
#include "calcrsc.h"

#define MAXVAL  2147483647L                 /* what a LONG holds */

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];                   /* 45 words and 12 of points */

static OBJECT *tree;
static LONG    acc;                         /* what has been entered so far */
static LONG    shown;                       /* ...and what the display says */
static WORD    pending;                     /* the operator waiting, an index */
static WORD    fresh;                       /* the next digit starts a number */

/* The display's buffer, which the AES leaves alone: the resource's
 * TEDINFO points at it and objc_draw reads it where it stands.
 *
 * ALL 24 BITS OF BOTH.  ob_spec and te_ptext are LONGs holding addresses,
 * and this took the low sixteen of each -- correct while a resource was
 * always in bank $00, and silently wrong from the moment one was not.
 * Built as an accessory this file is --data-model=large, so rs_load puts
 * CALC.RSC in FAR memory (src/aes/rsrc.c) and the truncated pointers sent
 * show() to write the display over whatever sits at the same offset in
 * bank $00: the desktop came up to an hourglass and a blank desk, hung
 * inside a GEMDOS call, with no bad-call count and no BRK to say why.
 * The program build is small-data and its resource IS near, so uint32_t
 * changes nothing there.  Fourteenth of its kind today -- see the
 * (uint16_t) casts fixed in src/desk/ the same afternoon. */
static char *disp_text(void)
{
    TEDINFO *ted = (TEDINFO *)(uint32_t)tree[CDISP].ob_spec.index;

    return (char *)(uint32_t)ted->te_ptext;
}

/* A signed LONG into the display, right-aligned in its places -- the
 * desktop's inf_numset, with room for the sign. */
static void show(LONG value)
{
    char *text = disp_text();
    LONG v = value < 0 ? -value : value;
    WORD i = DISP_PLACES;

    shown = value;
    text[i] = 0;
    do {
        text[--i] = (char)('0' + (WORD)(v % 10));
        v /= 10;
    } while (v && i > 0);
    if (value < 0 && i > 0)
        text[--i] = '-';
    while (i > 0)
        text[--i] = ' ';
}

/* Which digit a key is.  The resource's order is the panel's reading
 * order, not 0-9, so this is a switch rather than arithmetic: the two
 * would agree today and stop agreeing the moment a translation moves a
 * key. */
static WORD key_digit(WORD obj)
{
    switch (obj) {
    case C1: return 1;
    case C2: return 2;
    case C3: return 3;
    case C4: return 4;
    case C5: return 5;
    case C6: return 6;
    case C7: return 7;
    case C8: return 8;
    case C9: return 9;
    default: return 0;
    }
}

/* The two the panel does that are not arithmetic. */
static void clear(void)
{
    acc = 0;
    pending = 0;
    fresh = TRUE;
    show(0);
}

static void digit(WORD d)
{
    LONG v = fresh ? 0 : shown;
    LONG neg = (!fresh && shown < 0);

    if (neg)
        v = -v;
    if (v > (MAXVAL - d) / 10)              /* ten places is the ceiling */
        return;
    v = v * 10 + d;
    fresh = FALSE;
    show(neg ? -v : v);
}

/* The pending operation, applied to what is on the display.  A division
 * by nothing leaves the display alone -- the donor's calculators put a
 * word there, and a word is a string, and a string would have to come
 * from the resource for one case that a person will read once. */
static void apply(void)
{
    LONG b = shown;

    switch (pending) {
    case CADD:
        if ((b > 0 && acc > MAXVAL - b) || (b < 0 && acc < -MAXVAL - b))
            return;
        acc += b;
        break;
    case CSUB:
        if ((b < 0 && acc > MAXVAL + b) || (b > 0 && acc < -MAXVAL + b))
            return;
        acc -= b;
        break;
    case CMUL:
        if (b && (acc > MAXVAL / (b < 0 ? -b : b)
                  || acc < -(MAXVAL / (b < 0 ? -b : b))))
            return;
        acc *= b;
        break;
    case CDIV:
        if (!b)
            return;
        acc /= b;                           /* towards zero, and exact */
        break;
    default:
        acc = b;
        break;
    }
    show(acc);
}

/* The resource, once.  Separate from the panel because the two happen at
 * different times in an accessory: the shell takes this while the AES is
 * starting up -- before the first program, the only time an accessory may
 * take anything from bank $00 -- and opens the panel whenever somebody
 * chooses it from the Desk menu (src/apps/calcacc.c). */
WORD calc_start(void)
{
    if (!rsrc_load("CALC.RSC"))
        return FALSE;
    rsrc_gaddr(R_TREE, ADCALC, (void **)&tree);
    clear();
    return TRUE;
}

/* A workstation of its own, for the PROGRAM.  The panel does not need one
 * -- the AES draws the form and form_do runs it, which is why the
 * accessory opens none (src/apps/calcacc.c, and src/apps/cpanel.c for the
 * same reasoning) -- but the standalone calculator has always opened one
 * and its gate counts the calls it makes (test-m22). */
WORD calc_ws(void)
{
    WORD handle, wchar, hchar, wbox, hbox;

    handle = graf_handle(&wchar, &hchar, &wbox, &hbox);
    if (!handle)
        return 0;
    v_opnvwk(work_in, &handle, work_out);
    return handle;
}

/* The panel, and the form_do loop that is the whole of this program.
 * Returns when Quit is pressed and the screen has been given back. */
void calc_panel(void)
{
    WORD x, y, w, h, obj, done = FALSE;

    form_center(tree, &x, &y, &w, &h);
    form_dial(FMD_START, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_GROW, 0, 0, 0, 0, x, y, w, h);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, w, h);

    while (!done) {
        obj = form_do(tree, 0);
        tree[obj].ob_state = (UWORD)(tree[obj].ob_state & ~SELECTED);
        objc_draw(tree, obj, 1, x, y, w, h);
        switch (obj) {
        case CQUIT:
            done = TRUE;
            break;
        case CCLR:
            clear();
            break;
        case CSIGN:
            show(-shown);
            fresh = FALSE;
            break;
        case CADD:
        case CSUB:
        case CMUL:
        case CDIV:
            apply();
            pending = obj;
            fresh = TRUE;
            break;
        case CEQ:
            apply();
            pending = 0;
            fresh = TRUE;
            break;
        default:
            digit(key_digit(obj));
            break;
        }
        objc_draw(tree, CDISP, 0, x, y, w, h);
    }

    form_dial(FMD_SHRINK, 0, 0, 0, 0, x, y, w, h);
    form_dial(FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}
