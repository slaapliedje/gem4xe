/* v6_vdi.c -- step 1 of docs/6502.md: the VDI, banked, on a stock 6502.
 *
 * The same src/vdi/vdi.c and src/vdi/dev_antic.c the 65C816 build ships,
 * compiled by cc6502 into banks of the PORTB window (vdi.c in two, the
 * device in a third), with this program resident and every call into a
 * bank going through a veneer (src/sys6502/bank6502.s).  It draws what
 * test-m25 draws on the 65C816 before the AES comes in, through the VDI's
 * own interface -- contrl, intin, ptsin and a call to vdi() -- and the
 * gate holds every pixel to tools/vdiref.py on tools/devref.py's ANTIC:
 *
 *   a filled rectangle, the same again in XOR, a line of text,
 *   text the clip cuts through a glyph at each end,
 *   vro_cpyfm's S XOR D and S AND D on the screen,
 *   and vqt_name's face, which names this screen's cell.
 *
 * and text at twice its size, which goes through a buffer in far memory
 * (step 3b): src/sys/farmem.c's allocator in a bank of its own, the far
 * heap in the PORTB banks after the code's (src/sys6502/farmem6502.c).
 *
 * Then the object library on top (step 3c), as test-m25 has it: the
 * AES's gsx_start (src/aes/graf.c) and ob_draw (src/aes/objc.c) of
 * test-m25's dialog -- with the tree and its strings in FAR memory, where
 * rsrc_load puts a resource's, every field read through OB_GET -- and
 * objc_find on its OK button.
 *
 * Not yet: the rest of the AES (step 4).
 *
 * STATUS at $0600: 'A' 'V' as it starts, 'K' at $0602 when it is done;
 * vqt_name's bytes at $0630; the banks it found at $0608, the far banks
 * the heap made of them at $0609; the tree's far address at $0650 (four
 * bytes), what objc_find answered at the OK button's middle at $0654, and
 * how many of the four objects far_get reads back as written at $0655.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "sys/farmem.h"
#include "aes/aes.h"

void v6_tree(void);                     /* src/v6_tree.c, bank 6 */
#include "sys/hiprobe.h"           /* farmem_probe */

#define STATUS ((volatile unsigned char *)0x0600)

extern unsigned char b6_count;

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

int main(void)
{
    STATUS[0] = 'A';
    STATUS[1] = 'V';
    STATUS[2] = 0;
    STATUS[8] = b6_count;

    farmem_probe();                     /* the far heap, before the VDI */
    STATUS[9] = (unsigned char)farmem.banks;
    vdev = &vdev_antic;
    STATUS[3] = '1';                    /* how far it got, at $0603 */
    vdi_font_default();
    STATUS[3] = '2';
    vdi_init();
    STATUS[3] = '3';

    set1(VSF_COLOR, 1);
    set1(VSF_INTERIOR, FIS_SOLID);
    set1(VSWR_MODE, MD_REPLACE);
    rect(VR_RECFL, 20, 20, 200, 60);
    set1(VSWR_MODE, MD_XOR);
    rect(VR_RECFL, 60, 30, 160, 50);
    set1(VSWR_MODE, MD_REPLACE);
    STATUS[3] = '4';
    set1(VST_COLOR, 1);
    text(20, 80, "GEM ON A 6502");

    STATUS[3] = '5';
    ptsin[0] = 213; ptsin[1] = 140; ptsin[2] = 244; ptsin[3] = 160;
    intin[0] = 1;
    call(VS_CLIP, 2, 1);
    text(210, 150, "CLIPPED");
    intin[0] = 0;
    call(VS_CLIP, 0, 1);

    STATUS[3] = '6';
    {
        static const WORD mode[2] = { 6, 1 };
        static const WORD dy[2] = { 75, 115 };
        WORD k;

        for (k = 0; k < 2; k++) {
            ptsin[0] = 21;  ptsin[1] = 21;  ptsin[2] = 120; ptsin[3] = 58;
            ptsin[4] = 203; ptsin[5] = dy[k];
            ptsin[6] = 302; ptsin[7] = (WORD)(dy[k] + 37);
            intin[0] = mode[k];
            contrl[7] = 0; contrl[8] = 0;
            contrl[9] = 0; contrl[10] = 0;
            call(VRO_CPYFM, 4, 1);
        }
    }

    /* the face at twice its size: 6x6 doubled, by vst_height 8 (phase
     * 149) -- its raster built in the VDI's far buffer -- and back */
    STATUS[3] = '7';
    ptsin[0] = 0; ptsin[1] = 8;
    call(VST_HEIGHT, 1, 0);
    text(230, 180, "BIG");
    ptsin[0] = 0; ptsin[1] = 0;
    call(VST_HEIGHT, 1, 0);

    {
        volatile unsigned char *nm = (volatile unsigned char *)0x0630;
        WORD k;

        set1(VQT_NAME, 1);
        for (k = 0; k < 20; k++)
            nm[k] = (unsigned char)intout[k + 1];
    }

    /* -- the object library: test-m25's dialog, from far memory
     * (src/v6_tree.c, banked: resident room is all taken) */
    STATUS[3] = '8';
    gsx_start();
    v6_tree();

    STATUS[2] = 'K';
    for (;;)
        ;
}
