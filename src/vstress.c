/* vstress.c -- the VBXE path on its own, for a machine that freezes.
 *
 * gem4xe's own Rapidus, interrupt, VBXE and pointer code, brought up the
 * way GEM.COM brings it up (src/gem.c), and then nothing else: no AES, no
 * desktop, no DOS call after start-up.  It loops, and says on the top line
 * how many times and for how long, so a freeze is a number that stops.
 *
 * Built once per mode (VS_MODE_x from the Makefile), each its own floppy;
 * docs/vstress.md has what the user's machine did with each:
 *   'P'  the pointer only: an ST mouse in port 1, the 4 kHz sampler, the
 *        pointer drawn and moved on the VBXE.  Nothing else is drawn.
 *   'D'  the pointer, and random filled bars drawn under it all the
 *        time, the cursor hidden around each as the AES hides it.
 *   'N'  the bars and no pointer at all: PTR_NONE, so the sampler reads
 *        no port and nothing is drawn where the mouse is.
 *   'B'  the blitter alone: one filled rectangle a list, started and
 *        waited for, no VDI between -- the bars without the VDI.
 *   'C'  the CPU alone: the rectangles written into VRAM through the
 *        MEMAC window a row at a time, and the blitter never started
 *        after start-up.  No status line either: that is drawn by blits.
 *   'I'  B, with the VBXE's interrupt switched off and acknowledged at
 *        start-up (IRQ_CONTROL = 0).  gem4xe never writes that register,
 *        and its IRQ handler returns from any interrupt that is not
 *        POKEY's without clearing it: a blitter-done interrupt left enabled
 *        by whatever ran before would hold the CPU in the handler for good.
 *   'W'  B without the busy-wait: the list is started and the loop waits
 *        a frame by the vertical blank's counter, in fast RAM, before the
 *        next -- so no VBXE register is read while the blitter runs.
 *   'F'  W at B's rate: the blit is waited out by a count in fast RAM
 *        rather than a frame, then BUSY is read once, when it is done.
 *   'L'  the blitter worked hard with the CPU kept off it: four full-
 *        screen fills in one list, then three frames counted in fast RAM
 *        before the next -- the blitter busy most of the time, the CPU
 *        touching the VBXE once a batch.  The colour changes each second.
 *   'S'  F's rate with nothing but the start register: one block uploaded
 *        at start-up, then BLITTER_START written again and again, the
 *        list waited out in fast RAM.  No window writes, no BUSY reads.
 *   'M'  F without the BUSY read: the block uploaded through the window
 *        and started, the list waited out in fast RAM.
 *   'G'  F, and 'H' S, with ten times the wait: a list given about 5 ms
 *        rather than 0.5 before the VBXE is touched again.
 *   'R'  no blits at all: the blitter's busy register read in a loop,
 *        over the slow bus, as the busy-wait reads it.
 * A machine that freezes in N has a problem gem4xe's pointer is not part
 * of; B against C says blitter or CPU writes; the rest take B apart.
 *
 * WHAT A FROZEN SCREEN STILL SAYS.  Every second, while the vertical blank
 * runs and the loop goes round, a short quiet beep.  A blit list that has
 * not finished two seconds after it was started sounds a steady tone
 * instead (blit_stuck, from src/vbxe/vbxe.c built with BLIT_WATCHDOG):
 * high when only BCB_LOAD is set, middle for BUSY, low for both.  Silence
 * with the beeps stopped is the CPU, or the vertical blank, gone.          */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/pointer.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "aes/aes.h"           /* gsx_mfform: the AES's arrow */
#include "sys/rapidus.h"
#include "sys/irq.h"
#include "sys/abi.h"
#include "sys/dos.h"
#include "vbxe/vbxe.h"
#include "antic/antic.h"

/* The Makefile says which with -D VS_MODE_P, _D or _N: a quoted
 * character does not survive tools/ccdep.sh's quoting. */
#if defined(VS_MODE_P)
#define VS_MODE 'P'
#elif defined(VS_MODE_B)
#define VS_MODE 'B'
#elif defined(VS_MODE_I)
#define VS_MODE 'I'
#elif defined(VS_MODE_W)
#define VS_MODE 'W'
#elif defined(VS_MODE_R)
#define VS_MODE 'R'
#elif defined(VS_MODE_F)
#define VS_MODE 'F'
#elif defined(VS_MODE_L)
#define VS_MODE 'L'
#elif defined(VS_MODE_S)
#define VS_MODE 'S'
#elif defined(VS_MODE_M)
#define VS_MODE 'M'
#elif defined(VS_MODE_G)
#define VS_MODE 'G'
#define VS_MODE_F 1                     /* F, waiting ten times as long */
#elif defined(VS_MODE_H)
#define VS_MODE 'H'
#define VS_MODE_S 1                     /* S, waiting ten times as long */
#elif defined(VS_MODE_C)
#define VS_MODE 'C'
#elif defined(VS_MODE_N)
#define VS_MODE 'N'
#else
#define VS_MODE 'D'
#endif

extern void _sys_exit(void);
#if defined(VS_MODE_G) || defined(VS_MODE_H)
#define VS_SPIN 10000u
#else
#define VS_SPIN 1000u
#endif
extern void blit_start_nowait(void);  /* vbxe.c, BLIT_WATCHDOG builds */

/* Pointer and drawing, per mode -- decided by the PREPROCESSOR, as 0 or 1.
 * cc65816 5.18.2 gets a branch on constant comparisons joined by || or &&
 * backwards: `if ('N' == 'P' || 'N' == 'D')` is taken, and the first build
 * of this file had its N mode drawing like C with the pointer on.  A
 * literal 0 or 1 under || is folded correctly. */
#if defined(VS_MODE_P) || defined(VS_MODE_D)
#define VS_PTR   1
#else
#define VS_PTR   0
#endif
#if defined(VS_MODE_D) || defined(VS_MODE_N)
#define VS_BARS  1
#else
#define VS_BARS  0
#endif
#if defined(VS_MODE_B) || defined(VS_MODE_C) || defined(VS_MODE_I) \
    || defined(VS_MODE_W) || defined(VS_MODE_F) || defined(VS_MODE_M)
#define VS_RAW   1
#else
#define VS_RAW   0
#endif
#if defined(VS_MODE_C) || defined(VS_MODE_W) || defined(VS_MODE_R) \
    || defined(VS_MODE_F) || defined(VS_MODE_L) || defined(VS_MODE_S) \
    || defined(VS_MODE_M)
#define VS_TEXT  0                  /* the status line is blits */
#else
#define VS_TEXT  1
#endif
#ifdef VS_MODE_W
#define VS_WAIT  1
#else
#define VS_WAIT  0
#endif
#ifdef VS_MODE_F
#define VS_FAST  1
#else
#define VS_FAST  0
#endif
#ifdef VS_MODE_S
#define VS_RESTART 1
#else
#define VS_RESTART 0
#endif
#ifdef VS_MODE_M
#define VS_NOPOLL 1
#else
#define VS_NOPOLL 0
#endif
#ifdef VS_MODE_L
#define VS_LOAD  1
#else
#define VS_LOAD  0
#endif
#ifdef VS_MODE_R
#define VS_READS 1
#else
#define VS_READS 0
#endif
#if defined(VS_MODE_B) || defined(VS_MODE_I)
#define VS_BLIT  1
#else
#define VS_BLIT  0
#endif

#define AUDF3 (*(volatile uint8_t *)0xD204)
#define AUDC3 (*(volatile uint8_t *)0xD205)
#define AUDF4 (*(volatile uint8_t *)0xD206)
#define AUDC4 (*(volatile uint8_t *)0xD207)

/* The watchdog's report (src/vbxe/vbxe.c): a tone that stays. */
void blit_stuck(uint16_t busy)
{
    AUDC4 = 0;
    AUDF3 = (uint8_t)(busy == 1 ? 0x20 : busy == 2 ? 0x40 : 0x80);
    AUDC3 = 0xA8;
    for (;;)
        ;
}

static uint16_t seed = 0x2F6B;

static uint16_t rnd(uint16_t n)
{
    seed = (uint16_t)(seed * 25173u + 13849u);
    return (uint16_t)((seed >> 4) % n);
}

static void call(WORD op, WORD npts, WORD nint, WORD sub)
{
    contrl[0] = op;
    contrl[1] = npts;
    contrl[3] = nint;
    contrl[5] = sub;
    vdi();
}

static void show_c(WORD reset) { intin[0] = reset; call(122, 0, 1, 0); }
static void hide_c(void)       { call(123, 0, 0, 0); }

/* "P loops 0001234 time 001:02:03" at the top left. */
static void status(uint32_t loops, uint32_t secs)
{
    static const char pre[] = " loops ";
    static const char mid[] = " time ";
    char s[40];
    WORD n = 0, i;
    uint32_t v;
    uint32_t div;

    s[n++] = VS_MODE;
    for (i = 0; pre[i]; i++)
        s[n++] = pre[i];
    for (div = 1000000UL, v = loops % 10000000UL; div; div /= 10)
        s[n++] = (char)('0' + (v / div) % 10);
    for (i = 0; mid[i]; i++)
        s[n++] = mid[i];
    v = secs / 3600;
    s[n++] = (char)('0' + (v / 100) % 10);
    s[n++] = (char)('0' + (v / 10) % 10);
    s[n++] = (char)('0' + v % 10);
    s[n++] = ':';
    v = (secs / 60) % 60;
    s[n++] = (char)('0' + v / 10);
    s[n++] = (char)('0' + v % 10);
    s[n++] = ':';
    v = secs % 60;
    s[n++] = (char)('0' + v / 10);
    s[n++] = (char)('0' + v % 10);

    for (i = 0; i < n; i++)
        intin[i] = (WORD)(uint8_t)s[i];
    ptsin[0] = 8;
    ptsin[1] = 12;
    call(8, 1, n, 0);                   /* v_gtext */
}

static void bar(void)
{
    WORD x = (WORD)rnd((uint16_t)(SCR_W - 40));
    WORD y = (WORD)(24 + rnd((uint16_t)(SCR_H - 64)));

    intin[0] = (WORD)rnd(16);
    call(25, 0, 1, 0);                  /* vsf_color */
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = (WORD)(x + 8 + rnd(32));
    ptsin[3] = (WORD)(y + 8 + rnd(32));
    call(11, 2, 0, 1);                  /* v_bar */
}

/* A rectangle of one colour, both nibbles, straight into the screen:
 * by one blit list (B) or by the CPU through the window (C). */
static void raw_rect(void)
{
    uint16_t stride = (uint16_t)SCR_STRIDE;
    uint16_t x = rnd((uint16_t)(stride - 24));
    uint16_t y = (uint16_t)(24 + rnd((uint16_t)(VB_H - 64)));
    uint16_t w = (uint16_t)(4 + rnd(16)), h = (uint16_t)(8 + rnd(32)), r;
    uint8_t  c = (uint8_t)rnd(16);
    uint32_t a = VR_SCREEN0 + (uint32_t)y * stride + x;

    c = (uint8_t)(c | (c << 4));
    if (VS_BLIT) {
        blit_fill(a, stride, w, h, c);
        blit_run();
    } else if (VS_NOPOLL) {
        volatile uint16_t spin;

        blit_fill(a, stride, w, h, c);
        blit_start_nowait();
        for (spin = 0; spin < VS_SPIN; spin++)
            ;
    } else if (VS_FAST) {
        volatile uint16_t spin;

        /* B's rate without B's busy-wait: the blit is left to finish while
         * the CPU counts in fast RAM, long enough for the largest block
         * this makes (20 x 40 bytes, well under a millisecond), and only
         * then does blit_start's own wait read BUSY -- once, finished. */
        blit_fill(a, stride, w, h, c);
        blit_start();
        for (spin = 0; spin < VS_SPIN; spin++)
            ;
    } else if (VS_WAIT) {
        uint16_t f;

        blit_fill(a, stride, w, h, c);
        blit_start();                   /* and NOT waited on, by polling */
        f = irq_frames;
        while ((uint16_t)(irq_frames - f) < 2)
            ;                           /* a frame and a bit, in fast RAM */
    } else {
        for (r = 0; r < h; r++, a += stride)
            vram_fill(a, c, w);
    }
}

TASK void main(void)
{
    WORD i;
    uint32_t loops = 0, secs = 0;
    uint16_t last;
    uint8_t ticks = 0, beep = 0;

    dos_ident();
    rapidus_speedup();
    irq_install();
    abi_probe_os();
    if (irq.how == IRQ_OFF || !vbxe_detect()) {
        rapidus_restore();
        _sys_exit();
    }

    /* 640 x 240, GEM.COM's default; the index IS the OVATT width code. */
#ifdef VS_MODE_I
    *(volatile uint8_t *)(vbxe_base + FX_IRQ_CONTROL) = 0;  /* off, and acked */
#endif
    vdev = &vdev_vbxe_tab[OVATT_WIDTH_NORMAL][0];
    vram_fill(VR_XDL, 0x00, 0x1000);
    vbxe_xdl_hr(VR_SCREEN0, (uint16_t)vdev->h, 0, OVATT_WIDTH_NORMAL);
    antic_suspend();
    vdi_font_default();
    vdi_init();
    blit_fill(VR_SCREEN0, VB_STRIDE, VB_STRIDE, VB_H, 0x00);   /* white */
    blit_run();
    ptr_setport(PTR_PORT_1);
    ptr_init(VS_PTR ? PTR_ST_MOUSE : PTR_NONE, SCR_W / 2, SCR_H / 2);

    /* The workstation, as v_opnwk with every default. */
    for (i = 0; i < 10; i++)
        intin[i] = 1;
    intin[10] = 2;
    call(1, 0, 11, 0);
    intin[0] = 1;
    call(23, 0, 1, 0);                  /* vsf_interior: solid */
    if (VS_PTR) {
        /* The arrow, as graf_mouse(ARROW) sets it: without an AES nothing
         * else gives the pointer a shape, and an empty one draws nothing. */
        gsx_mfform(ARROW, intin);
        call(111, 0, 37, 0);            /* vsc_form */
        show_c(0);
    } else
        hide_c();                       /* a VDI starts with it shown */

#ifdef VS_MODE_S
    /* The one block S restarts: a 40 x 40 square in the middle, uploaded
     * to VR_BCB and BL_ADR pointed at it by the run itself. */
    blit_fill(VR_SCREEN0 + 100UL * SCR_STRIDE + 140, (uint16_t)SCR_STRIDE,
              20, 40, 0x22);
#endif
    blit_run();                         /* start-up's blits finished */
    if (VS_TEXT)
        status(0, 0);
    last = irq_frames;
    for (;;) {
        uint16_t now = irq_frames;

        if (VS_BARS) {
            if (VS_PTR)
                hide_c();
            bar();
            if (VS_PTR)
                show_c(1);
        } else if (VS_RAW)
            raw_rect();
        else if (VS_RESTART) {
            volatile uint16_t spin;

            *(volatile uint8_t *)(vbxe_base + FX_BLITTER_START) = 1;
            for (spin = 0; spin < VS_SPIN; spin++)
                ;
        }
        else if (VS_LOAD) {
            uint8_t k, c = (uint8_t)(secs & 15);
            uint16_t f;

            c = (uint8_t)(c | (c << 4));
            for (k = 0; k < 4; k++)
                blit_fill(VR_SCREEN0, (uint16_t)SCR_STRIDE,
                          (uint16_t)SCR_STRIDE, VB_H, c);
            blit_start();               /* four screens' worth, not waited on */
            f = irq_frames;
            while ((uint16_t)(irq_frames - f) < 3)
                ;
        }
        else if (VS_READS) {
            uint8_t k;

            for (k = 0; k < 64; k++)
                (void)blit_busy();      /* BLITTER_BUSY, over the slow bus */
        }
        if (VS_PTR)
            vdi_input_poll();           /* the mouse read, the pointer drawn */
        loops++;

        /* A second is 50 frames on PAL and 60 on NTSC; near enough for
         * a clock whose only job is to stop. */
        while ((uint16_t)(now - last) >= 1) {
            last++;
            if (beep && !--beep)
                AUDC4 = 0;
            if (++ticks >= (irq.pal ? 50 : 60)) {
                ticks = 0;
                secs++;
                AUDF4 = 0x50;           /* the heartbeat: a quiet beep */
                AUDC4 = 0xA3;
                beep = 4;
                if (VS_TEXT) {
                    if (VS_PTR)
                        hide_c();
                    status(loops, secs);
                    if (VS_PTR)
                        show_c(1);
                }
            }
        }
    }
}
