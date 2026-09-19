/* m2_vbxe.c -- Phase 1 milestone: bring up the VBXE surface and draw a test
 * pattern the host can verify pixel for pixel.
 *
 * Everything is drawn by the BLITTER, not the CPU.  That is the whole point of
 * the exercise: on this machine VBXE sits on the 1.79 MHz chip bus no matter
 * how fast the 65816 runs, so the VDI has to be a blit-list compiler.  This is
 * the first proof that the blit-list path works end to end.
 */
#include "portab.h"
#include "vbxe/vbxe.h"

#define STATUS ((volatile unsigned char *) 0x0600)

/* 16 palette entries.  Deliberately not a smooth ramp -- distinct values in
 * all three channels catch a channel swap, and odd values catch the DAC's
 * 7-bit truncation (a written $96 reads back as $97). */
static const unsigned char pal16[16 * 3] = {
    0x00, 0x00, 0x00,   /*  0 black        */
    0xFF, 0xFF, 0xFF,   /*  1 white        */
    0xC0, 0x00, 0x00,   /*  2 red          */
    0x00, 0xC0, 0x00,   /*  3 green        */
    0x00, 0x00, 0xC0,   /*  4 blue         */
    0xC0, 0xC0, 0x00,   /*  5 yellow       */
    0xC0, 0x00, 0xC0,   /*  6 magenta      */
    0x00, 0xC0, 0xC0,   /*  7 cyan         */
    0x60, 0x60, 0x60,   /*  8 grey         */
    0x96, 0x96, 0x96,   /*  9 odd grey -- exercises the DAC bit duplication */
    0xFF, 0x80, 0x00,   /* 10 orange       */
    0x80, 0x00, 0xFF,   /* 11 violet       */
    0x00, 0xFF, 0x80,   /* 12 spring       */
    0x40, 0x20, 0x10,   /* 13 brown        */
    0x10, 0x20, 0x40,   /* 14 navy         */
    0x7F, 0x01, 0x7F    /* 15 odd purple   */
};

TASK void main(void)
{
    unsigned int i;

    STATUS[0] = 'V';
    STATUS[1] = 'B';
    STATUS[2] = 0;                      /* progress marker */

    if (!vbxe_detect()) {
        STATUS[2] = 0xEE;               /* no VBXE -- nothing else is valid  */
        for (;;)
            ;
    }
    STATUS[3] = vbxe_major();
    STATUS[4] = vbxe_minor_bcd();
    STATUS[5] = (unsigned char)(vbxe_base >> 8);
    STATUS[2] = 1;

    /* Clear the whole XDL/BCB scratch page first.  A blit list started in
     * uninitialised VRAM ($FF) runs forever, because the "Next" bit is always
     * set -- so never leave that region undefined. */
    vram_fill(VR_XDL, 0x00, 0x1000);
    STATUS[2] = 2;

    vbxe_palette(1, 0, pal16, 16);
    STATUS[2] = 3;

    vbxe_xdl_hr(VR_SCREEN0, VB_H, 0, OVATT_WIDTH_NORMAL);
    STATUS[2] = 4;

    /* --- the pattern -------------------------------------------------- */
    /* 1. clear the screen to colour 0.  76,800 bytes is more than the
     *    blitter's 9-bit width allows in one row, so this is rows: 320
     *    bytes x 240, exactly the screen's own shape. */
    blit_reset();
    blit_fill(VR_SCREEN0, VB_STRIDE, VB_STRIDE, VB_H, 0x00);
    blit_run();
    STATUS[2] = 5;

    /* 2. sixteen vertical bars, 40 px = 20 bytes each, colours 0..15.
     *    Both nibbles of the fill byte carry the colour, so each bar is a
     *    solid block and the byte boundary is exact. */
    blit_reset();
    for (i = 0; i < 16; i++) {
        unsigned char c = (unsigned char)((i << 4) | i);
        blit_fill(VR_SCREEN0 + (unsigned long)(i * 20), VB_STRIDE,
                  20, 120, c);
        if (i == 11) {                  /* MAX_BCB is 12 -- flush and go on */
            blit_run();
            blit_reset();
        }
    }
    blit_run();
    STATUS[2] = 6;

    /* 3. copy the top-left 160x60 block down to (0,180), which exercises the
     *    real read-modify path (AND mask $FF) and a differing source and
     *    destination stride offset. */
    blit_reset();
    blit_copy(VR_SCREEN0, VB_STRIDE,
              VR_SCREEN0 + (unsigned long)VB_STRIDE * 180, VB_STRIDE,
              80, 60);
    blit_run();
    STATUS[2] = 7;

    /* 4. a single-colour band across the bottom, to prove a fill whose width
     *    is the full 320-byte stride still works (width field is 9 bits, and
     *    320-1 = 319 needs that ninth bit). */
    blit_reset();
    blit_fill(VR_SCREEN0 + (unsigned long)VB_STRIDE * 150, VB_STRIDE,
              VB_STRIDE, 20, 0x99);
    blit_run();

    /* --- 5. measure the blitter ---------------------------------------
     * The architecture rests on the claim that the blitter can sustain about
     * one full-screen copy per frame, which is what makes dirty rectangles
     * mandatory rather than merely nice.  Measure it rather than trust it.
     * A PAL frame is 156 VCOUNT ticks. */
    /* Order matters: the COPY is timed first because it doubles as the
     * backup of the pattern, which the FILL then destroys and the final
     * untimed copy restores.  The screen must end up exactly as the pixel
     * comparison expects. */
    blit_reset();
    blit_copy(VR_SCREEN0, VB_STRIDE, VR_SCREEN1, VB_STRIDE, VB_STRIDE, VB_H);
    i = blit_time();                    /* full-screen COPY (2 cycles/byte) */
    STATUS[10] = (unsigned char)i;
    STATUS[11] = (unsigned char)(i >> 8);

    blit_reset();
    blit_fill(VR_SCREEN0, VB_STRIDE, VB_STRIDE, VB_H, 0x11);
    i = blit_time();                    /* full-screen FILL (1 cycle/byte)  */
    STATUS[8] = (unsigned char)i;
    STATUS[9] = (unsigned char)(i >> 8);

    blit_reset();                       /* restore the pattern, untimed */
    blit_copy(VR_SCREEN1, VB_STRIDE, VR_SCREEN0, VB_STRIDE, VB_STRIDE, VB_H);
    blit_run();

    STATUS[2] = 0xA5;                   /* done */
    for (;;)
        ;
}
