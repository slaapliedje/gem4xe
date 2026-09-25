/* bench_antic.c -- the VDI on the ANTIC screen, timed by the host.
 *
 * GEMBench's text rows (tests/emu/bench_gem.py) run on the VBXE runner;
 * the desktop tour (bench_desk.py) has almost no text in it, because its
 * disk holds five files.  So this is the ANTIC device's own bench: the
 * product's vdi.o on vdev_antic, as test-m25 runs it, drawing a case the
 * host names as many times as it asks, while the host counts frames.
 *
 * The protocol, in page 6: the host writes the case to STATUS[3] and 1 to
 * STATUS[4]; this clears STATUS[4], draws, and writes $A5 to STATUS[5].
 * STATUS[0..2] is "AB" and then 'K' once the workstation is up;
 * STATUS[6] is the MCR after rapidus_speedup(), which the host checks --
 * the first version of this bench forgot the call and timed a machine
 * running everything at 1.79 MHz.
 * tests/emu/bench_antic.py is the other half.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "sys/rapidus.h"

#define STATUS ((volatile unsigned char *) 0x0600)
#define REPS   16                       /* each case, this many times over */

static void call(WORD op, WORD npts, WORD nint)
{
    contrl[0] = op;
    contrl[1] = npts;
    contrl[3] = nint;
    contrl[6] = VDI_PHYS_HANDLE;
    vdi();
}

static void set1(WORD op, WORD v)
{
    intin[0] = v;
    call(op, 0, 1);
}

/* A byte read as a WORD: never spin on a byte (tools/ccbug rule 16). */
static uint16_t status(uint16_t i)
{
    return STATUS[i];
}

/* A screen of text: every row the 6x6 face has room for, 53 characters
 * each, in the given mode, starting at x. */
static void text_screen(WORD mode, WORD x)
{
    WORD r, i;

    set1(VSWR_MODE, mode);
    for (i = 0; i < 53; i++)
        intin[i] = (WORD)('A' + (i % 26));
    for (r = 0; r < 26; r++) {
        ptsin[0] = x;
        ptsin[1] = (WORD)(8 + r * 6);
        call(V_GTEXT, 1, (WORD)(53 - (x > 0)));
    }
}

static void rect(WORD x1, WORD y1, WORD x2, WORD y2)
{
    ptsin[0] = x1;  ptsin[1] = y1;  ptsin[2] = x2;  ptsin[3] = y2;
    call(VR_RECFL, 2, 0);
}

/* A rectangle, solid or in a pattern, in a mode. */
static void big_rect(WORD interior, WORD index, WORD mode)
{
    set1(VSF_INTERIOR, interior);
    set1(VSF_STYLE, index);
    set1(VSWR_MODE, mode);
    rect(9, 9, 308, 158);
}

/* The desk's own: its patterned background, the whole screen. */
static void desk_pattern(void)
{
    set1(VSF_INTERIOR, FIS_PATTERN);
    set1(VSF_STYLE, 4);
    set1(VSWR_MODE, MD_REPLACE);
    rect(0, 0, 319, 167);
}

/* Many small ones -- buttons, gadgets, the backgrounds of menu items --
 * where what a call costs to set up is most of it. */
static void small_rects(void)
{
    WORD i;

    set1(VSF_INTERIOR, FIS_SOLID);
    set1(VSWR_MODE, MD_REPLACE);
    for (i = 0; i < 200; i++) {
        WORD x = (WORD)(3 + (i % 12) * 26), y = (WORD)(2 + (i / 12) * 9);

        rect(x, y, (WORD)(x + 23), (WORD)(y + 7));
    }
}

TASK void main(void)
{
    WORD rep;

    STATUS[0] = 'A';
    STATUS[1] = 'B';
    STATUS[2] = 0;
    STATUS[4] = 0;
    STATUS[5] = 0;

    rapidus_speedup();
    STATUS[6] = rapidus.mcr_after;
    vdev = &vdev_antic;
    vdi_font_default();
    vdi_init();
    set1(VST_COLOR, 1);
    set1(VSF_COLOR, 1);
    STATUS[2] = 'K';

    for (;;) {
        while (!status(4))
            ;
        STATUS[4] = 0;
        for (rep = 0; rep < REPS; rep++) {
            switch (status(3)) {
            case 0: text_screen(MD_REPLACE, 0); break;
            case 1: text_screen(MD_TRANS, 0);   break;
            case 2: text_screen(MD_REPLACE, 3); break;
            case 3: big_rect(FIS_SOLID, 1, MD_REPLACE); break;
            case 4: desk_pattern();             break;
            case 5: small_rects();              break;
            default: big_rect(FIS_SOLID, 1, MD_XOR); break;
            }
        }
        STATUS[5] = 0xA5;
    }
}
