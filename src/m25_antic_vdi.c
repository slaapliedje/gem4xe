/* m25_antic_vdi.c -- the VDI itself, running on the ANTIC device.
 *
 * The same src/vdi/vdi.c the VBXE build uses, compiled with
 * GEM4XE_DEV_ANTIC and linked against src/vdi/dev_antic.c instead of
 * dev_vbxe.c.  Nothing in the VDI was changed to make this happen; that
 * is what the seam was for.
 *
 * Everything here goes through the VDI's own interface -- the contrl,
 * intin and ptsin arrays and a call to vdi() -- so what is being tested
 * is the dispatcher, the workstation state, the clipping and the
 * attributes on top of a device they were not written for.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "aes/aes.h"
#include "aes/proc.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"    /* which device this program is about */
#include "sys/farmem.h"

#define STATUS ((volatile unsigned char *) 0x0600)

static void call(WORD op, WORD npts, WORD nint)
{
    contrl[0] = op;
    contrl[1] = npts;
    contrl[3] = nint;
    contrl[6] = VDI_PHYS_HANDLE;
    vdi();
}

/* the attribute setters this milestone uses */
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

TASK void main(void)
{
    STATUS[0] = 'A';
    STATUS[1] = 'V';
    STATUS[2] = 0;

    /* The face first, as src/gem.c and src/m3_vdi.c do: vdi_init opens
     * the workstation but the FONT is the program's to choose, and a
     * vdi_font of zero is a glyph blit reading address zero. */
    vdev = &vdev_antic;      /* this milestone is about the other
                              * device; nothing else in the file
                              * names it again */
    vdi_font_default();
    vdi_init();                         /* opens the workstation: the
                                         * device's palette call is what
                                         * brings ANTIC up */

    /* a filled rectangle in pen 1 */
    set1(VSF_COLOR, 1);
    set1(VSF_INTERIOR, FIS_SOLID);
    set1(VSWR_MODE, MD_REPLACE);
    rect(VR_RECFL, 20, 20, 200, 60);

    /* the same rectangle again in XOR: a hole in the middle of it */
    set1(VSWR_MODE, MD_XOR);
    rect(VR_RECFL, 60, 30, 160, 50);

    /* text */
    set1(VSWR_MODE, MD_REPLACE);
    set1(VST_COLOR, 1);
    {
        static const char s[] = "GEM ON ANTIC";
        WORD i;
        for (i = 0; s[i]; i++)
            intin[i] = (WORD)(unsigned char)s[i];
        ptsin[0] = 20;
        ptsin[1] = 80;
        call(V_GTEXT, 1, (WORD)i);
    }

    /* -- and the AES on top of it ------------------------------------
     * gsx_start is where the AES learns what device it is on: it asks
     * the VDI for the extent, the depth and the system font's cell, and
     * everything it lays out afterwards -- the menu bar's height, the
     * middle of the screen, a dialog's box -- comes off those numbers.
     * It is the whole reason a GEM ports to a second screen at all, so
     * the gate reads them back rather than trusting them. */
    /* The AES's processes, and the context switch's mark.  This runner
     * has one process and never switches, but event.c reaches for the
     * running one and there has to BE one (src/aes/proc.h).  The records
     * are a static here rather than the pool's, because a VDI milestone
     * has no loader: that is the whole reason proc.c allocates nothing
     * itself. */
    {
        static char proc_store[PROC_STORE];
        proc_init(proc_store);
    }
    ctx_make(&proc_app->p_ctx, 0);      /* somewhere to be parked, if ever */
    ctx_init(&proc_app->p_ctx);

    gsx_start();
    {
        volatile WORD *g = (volatile WORD *)0x0610;
        g[0] = gl_width;      g[1] = gl_height;
        g[2] = gl_nplanes;    g[3] = gl_wchar;
        g[4] = gl_hchar;      g[5] = gl_wbox;
        g[6] = gl_hbox;       g[7] = gl_rmenu.g_w;
        g[8] = gl_rmenu.g_h;  g[9] = gl_rfull.g_h;
    }

    /* -- an AES object tree, drawn by the object library --------------
     * A dialog's shape: an outlined box with a border, a title, and a
     * button with the DEFAULT ring round it.  ob_draw walks it and
     * reaches the screen through the VDI and then the device, so what
     * this shows is the whole stack on a screen none of it was written
     * for -- and whether GEM's colour conventions survive a device with
     * two colours, since a box's colour word names a pen and a pattern
     * and this one has neither to spare. */
    {
        static char title[] = "A GEM dialog";
        static char okstr[] = "  OK  ";
        static OBJECT tree[4];

        tree[0].ob_next = -1; tree[0].ob_head = 1; tree[0].ob_tail = 3;
        tree[0].ob_type = G_BOX; tree[0].ob_flags = NONE;
        tree[0].ob_state = OUTLINED;
        tree[0].ob_spec = 0x00021100UL;   /* no char, 2px border, white on
                                           * black -- the donor's DIALERT */
        tree[0].ob_x = 30; tree[0].ob_y = 100;
        tree[0].ob_width = 160; tree[0].ob_height = 46;

        tree[1].ob_next = 2; tree[1].ob_head = -1; tree[1].ob_tail = -1;
        tree[1].ob_type = G_STRING; tree[1].ob_flags = NONE;
        tree[1].ob_state = NORMAL;
        tree[1].ob_spec = (uint32_t)(uint16_t)title;
        tree[1].ob_x = 8; tree[1].ob_y = 6;
        tree[1].ob_width = 12 * 6; tree[1].ob_height = 6;

        tree[2].ob_next = 3; tree[2].ob_head = -1; tree[2].ob_tail = -1;
        tree[2].ob_type = G_BOX; tree[2].ob_flags = NONE;
        tree[2].ob_state = NORMAL;
        tree[2].ob_spec = 0x00011100UL;   /* one pixel of border */
        tree[2].ob_x = 8; tree[2].ob_y = 16;
        tree[2].ob_width = 144; tree[2].ob_height = 8;

        tree[3].ob_next = 0; tree[3].ob_head = -1; tree[3].ob_tail = -1;
        tree[3].ob_type = G_BUTTON;
        tree[3].ob_flags = (UWORD)(SELECTABLE | EXIT | DEFAULT | LASTOB);
        tree[3].ob_state = NORMAL;
        tree[3].ob_spec = (uint32_t)(uint16_t)okstr;
        tree[3].ob_x = 56; tree[3].ob_y = 30;
        tree[3].ob_width = 6 * 6; tree[3].ob_height = 10;

        ob_draw(tree, 0, MAX_DEPTH);
    }


    /* -- vro_cpyfm through memory ------------------------------------
     * The text, from the screen into a form in bank $00, from there into
     * the far save form the AES keeps menus in, and back onto the screen
     * somewhere empty -- at a different bit position every step, so the
     * row copy's shifts and edge masks both ways are all in the picture
     * (phase 66: this path took five seconds a drop-down in 0.8.1). */
    farmem_probe();
    {
        static uint8_t near_buf[20 * 16];      /* 160 x 16, one plane */
        static MFDB scr, mem, far;
        static const WORD hops[3][8] = {
            { 19, 78, 118, 87,    3,  2, 102, 11 },
            {  3,  2, 102, 11,   37, 50, 136, 59 },
            { 37, 50, 136, 59,  211, 85, 310, 94 },
        };
        MFDB *from[3], *to[3];
        WORD k, i;

        mem.fd_addr = (uint32_t)(uint16_t)near_buf;
        mem.fd_w = 160; mem.fd_h = 16; mem.fd_wdwidth = 10;
        mem.fd_nplanes = 1;
        vdi_save_form(&far);
        STATUS[3] = far.fd_addr >= 0x10000UL ? 'F' : 'N';
        from[0] = &scr; to[0] = &mem;
        from[1] = &mem; to[1] = &far;
        from[2] = &far; to[2] = &scr;
        set1(VSWR_MODE, MD_REPLACE);
        for (k = 0; k < 3; k++) {
            for (i = 0; i < 8; i++)
                ptsin[i] = hops[k][i];
            contrl[7] = (WORD)(uint16_t)from[k]; contrl[8] = 0;
            contrl[9] = (WORD)(uint16_t)to[k];   contrl[10] = 0;
            intin[0] = S_ONLY;
            call(VRO_CPYFM, 4, 1);
        }
    }

    STATUS[2] = 'K';
    for (;;)
        ;
}
