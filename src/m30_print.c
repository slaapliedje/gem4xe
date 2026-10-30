/* m30_print.c -- the VDI on the printer, and the page off the machine.
 *
 * The THIRD device through src/vdi/vdidev.h's seam, and the first that
 * is not a screen: 640 x 800 dots at one bit, in far memory, drawn by
 * the same src/vdi/vdi.c that draws the other two and then written out
 * by src/vdi/emit.c as PCL 5 and as PostScript.
 *
 * There is nothing to photograph, so this milestone is checked from the
 * FILES IT WRITES.  PCL is lossless -- tools/emitref.py decodes it back
 * to a page -- and PostScript is checked by giving it to Ghostscript,
 * which is the only honest way to check a program in a language that has
 * an interpreter.  Both are compared against tools/vdiref.py driving
 * tools/devref.py's Printer, the same models that answer for the VBXE in
 * test-m3 and for ANTIC in test-m25, with one argument changed.
 *
 * WHY IT WRITES TWICE.  pr_kind and pr_dest are what src/gem.c sets out
 * of GEM4XE.CFG, and setting them here rather than reading a config file
 * is the point: the VDI does not know what a config file is, and a gate
 * that had to reboot the machine to try the second language would be
 * testing DOS.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "vdi/print.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"
#include "sys/dos.h"
#include "sys/irq.h"
#include "sys/rapidus.h"

#define STATUS ((volatile unsigned char *) 0x0600)

/* STATUS[4] says how far this got, so a gate that finds the machine
 * stopped can say where rather than "it did not finish".  A page is
 * 512,000 dots drawn a byte at a time and 129 KB of PostScript written
 * through CIO, and either could be slow rather than wrong. */
#define MARK(c)  (STATUS[4] = (unsigned char)(c))

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

static void rect(WORD op, WORD x1, WORD y1, WORD x2, WORD y2)
{
    ptsin[0] = x1; ptsin[1] = y1; ptsin[2] = x2; ptsin[3] = y2;
    call(op, 2, 0);
}

static void text(WORD x, WORD y, const char *s)
{
    WORD i;

    for (i = 0; s[i]; i++)
        intin[i] = (WORD)(unsigned char)s[i];
    ptsin[0] = x;
    ptsin[1] = y;
    call(V_GTEXT, 1, i);
}

TASK void main(void)
{
    STATUS[0] = 'A';
    STATUS[1] = 'V';
    STATUS[2] = 0;
    STATUS[3] = 0;
    MARK('.');

    /* THE SAME THREE CALLS src/gem.c OPENS WITH, and for the same
     * reason the product needs them: this milestone WRITES, and a write
     * is SIO, and SIO is interrupts.  In native mode the 65816 fetches
     * its vectors from $FFEA/$FFEE, which the Atari's ROM does not fill
     * -- so without irq_install() the first VBI inside the first
     * cio_write derails the machine, which is exactly how it presented:
     * the page drawn, the file never written, and nothing on the screen
     * to say so.  The other two VDI milestones get away without these
     * because they never call the OS. */
    dos_ident();
    rapidus_speedup();
    irq_install();

    farmem_probe();
    MARK('f');
    if (!pr_page_open()) {
        STATUS[1] = '!';                /* no far heap: nothing to draw on */
        for (;;)
            ;
    }

    MARK('p');
    vdev = &vdev_print;
    vdi_font_default();
    vdi_init();
    MARK('w');

    /* A page with something at each of the places a 1bpp raster goes
     * wrong: both ends of a byte, the last row, a span that is not a
     * whole number of bytes, and text at an odd x. */
    set1(VSF_COLOR, 1);
    set1(VSF_INTERIOR, FIS_SOLID);
    set1(VSWR_MODE, MD_REPLACE);

    /* The two full-width rules cover the first and last byte of a row
     * and the last row of the page; the two short marks cover both
     * edges again somewhere the rules are not.  What is deliberately
     * NOT here is a border down the sides -- it would put ink in every
     * one of the 800 rows and leave the blank-row skip untested, which
     * is the one thing about the PCL that could quietly stop working
     * and still print. */
    rect(VR_RECFL, 0, 0, PR_W - 1, 2);              /* a rule across the top */
    rect(VR_RECFL, 0, PR_H - 3, PR_W - 1, PR_H - 1);        /* and the foot */
    rect(VR_RECFL, 0, 400, 2, 420);                  /* a mark at the left */
    rect(VR_RECFL, PR_W - 3, 400, PR_W - 1, 420);           /* and the right */

    rect(VR_RECFL, 37, 60, 122, 140);           /* neither end byte-aligned */
    set1(VSWR_MODE, MD_XOR);
    rect(VR_RECFL, 60, 80, 100, 120);                    /* a hole in it */
    set1(VSWR_MODE, MD_REPLACE);

    MARK('r');
    set1(VST_COLOR, 1);
    text(24, 200, "GEM4XE -- 640 x 800 DOTS AT 100 DPI");
    text(25, 216, "...AND THE SAME LINE AT AN ODD X.");

    /* A diagonal, which is the one primitive the blitter never helped
     * with on either screen and which here has no blitter at all. */
    MARK('t');
    set1(VSL_COLOR, 1);
    ptsin[0] = 300; ptsin[1] = 300;
    ptsin[2] = 420; ptsin[3] = 340;
    call(V_PLINE, 2, 0);

    /* -- off the machine, twice ---------------------------------------
     * Through v_updwk both times, because the wiring from the VDI's
     * opcode 4 to pr_emit() is part of what this gate is for.
     *
     * D: is the disk the milestone was loaded from, which is what a real
     * PRINTTO= names when there is no printer on the other end of P: --
     * the file is carried to a machine with a printer.  The gate reads
     * the two files back out of the image afterwards (tools/atr.py). */
    MARK('l');
    pr_kind = PR_PCL;
    pr_dest = "D:PAGE.PCL";
    call(V_UPDWK, 0, 0);
    STATUS[3] = '1';
    MARK('P');

    pr_kind = PR_PS;
    pr_dest = "D:PAGE.PS";
    call(V_UPDWK, 0, 0);

    MARK('S');
    STATUS[2] = 'K';
    for (;;)
        ;
}
