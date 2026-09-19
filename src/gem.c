/* gem.c -- GEM.COM, the product entry point.
 *
 * The same bring-up as the conformance runner (src/m3_vdi.c) with no host
 * in the loop: DOS loads it, it takes the machine over, hands the screen
 * to the shell loop (src/aes/shel.c: DESKTOP.G4A, then whatever the
 * desktop asks for, until the desktop asks to shut down), and gives the
 * machine back exactly as it found it.  Nothing here is poked from the
 * bridge, so the runner's STATUS block, its script buffers and its test
 * stage do not exist in this link: the application pool has the whole of
 * $4000-$7FFF (src/gem4xe.scm, the `layout` function's second argument).
 *
 * ONE BINARY, TWO SCREENS.  Both VDI devices are linked (src/vdi/vdidev.h)
 * and this file is where the choice is made -- the only place it is made,
 * which is why `vdev` is set here and not by the VDI finding out for
 * itself.  A machine with a VBXE gets 640x240 in sixteen colours; one
 * without gets ANTIC mode F, 320x168 in two, on Atari's condensed face.
 * GEM4XE.CFG overrides either way (src/sys/config.h): VIDEO=ANTIC is the
 * safe mode for a monitor that will not lock to the VBXE's output, and
 * it is a plain text file precisely because that machine has no screen
 * to put a dialog on.
 *
 * WHAT IS STILL REQUIRED EITHER WAY is the accelerator: this program's
 * code lives in bank $01 and a 6502 cannot reach it (src/farload.s
 * refuses the machine before its first store).  The ANTIC device is the
 * answer to "no VBXE", not to "no Rapidus".
 *
 * BEFORE EITHER SCREEN there is the boot screen (src/sys/bootinfo.h): on
 * the OS's text screen, a line for each thing the start-up settled, in
 * the order it settled them, held for three seconds the way EmuTOS
 * holds its.  That is why the far-memory probe and the reading of
 * LANG.RSC come before the screen is chosen rather than after the AES
 * is up, where they used to be: the screen is written in LANG.RSC's
 * words, and LANG.RSC lives in far memory.  Both are safe that early --
 * the probe touches no bank the program is in, and the strings need
 * nothing of the VDI.  The FONT half of a translation, SYSTEM.FNT,
 * still waits for the device it is loaded into (lang_font).
 *
 * The one message it can print is a refusal, and _sys_exit says it on the
 * way out (src/crt_atari.s, _exit_msg) -- after DOS's own screen is back,
 * so the line is not cleared with the reopen of E:.
 */
#include "portab.h"
#include <stdint.h>
#include "vdi/vdi.h"
#include "vdi/vdidev.h"             /* the seam: which device, and both */
#include "vdi/pointer.h"
#include "vdi/font.h"
#include "aes/aes.h"
#include "aes/proc.h"
#include "sys/farmem.h"
#include "sys/rapidus.h"
#include "sys/abi.h"
#include "sys/irq.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/config.h"
#include "sys/bootinfo.h"
#include "sys/clock.h"
#include "vdi/print.h"
#include "sys/gemdos.h"
#include "vbxe/vbxe.h"
#include "lang_rsc.h"              /* LS_*, LANG_MAXLEN */
#include "antic/antic.h"
#ifdef GEM_DIAG
#include "sys/diag.h"
/* GEMDIAG.COM: a mark before each step, and two steps it can leave out.
 * GEM.COM compiles the same file with the marks empty. */
#define MARK(n)       diag_mark(n)
#define UNLESS(bit)   if (!(diag_keys & (bit)))
#define DIAG(call)    call
#else
#define MARK(n)
#define UNLESS(bit)
#define DIAG(call)
#endif

extern void _sys_exit(void);
extern uint16_t _exit_msg;           /* src/crt_atari.s: a line for the way out */

/* The pointing device.  An ST mouse on the joystick port is what a GEM
 * machine has; the quadrature is counted from the timer interrupt
 * irq_install sets up (src/sys/irq.h), so it needs nothing polled.
 * MOUSE= in GEM4XE.CFG names another. */
#define GEM_POINTER PTR_ST_MOUSE

/* Mode F's two colours: a set bit takes COLPF1's LUMINANCE over COLPF2's
 * hue, so this is GEM's white paper and black ink and there is no third
 * choice to make (src/antic/antic.h). */
#define AN_INK    0x00
#define AN_PAPER  0x0E

static const char no_vbxe[] =
    "gem4xe: VIDEO=VBXE, and no VBXE in this machine\x9b";

/* A refusal in LANG.RSC's words: the line, EOL-terminated, in bank $00
 * where _sys_exit can reach it after the far memory is nobody's. */
static char exit_line[LANG_MAXLEN + 2];

static void exit_say(WORD n)
{
    const char *s = lang_str(n);
    WORD i;

    for (i = 0; s[i]; i++)
        exit_line[i] = s[i];
    exit_line[i] = (char)0x9B;
    exit_line[i + 1] = '\0';
    _exit_msg = (uint16_t)exit_line;
}

TASK void main(void)
{
    WORD video, pointer;

#ifdef GEM_DIAG
    diag_init();
#endif
    MARK(0);  dos_ident();
    MARK(1);  UNLESS(DIAG_SKIP_SPEEDUP) rapidus_speedup();
    DIAG(diag_rapidus());       /* the signature and the windows, as found */
    MARK(2);  UNLESS(DIAG_SKIP_IRQ) irq_install();
              abi_probe_os();   /* whose COP a foreign one is (src/sys/abi.s);
                                   a CIO call, so after the vectors, as
                                   config_read is */
    MARK(3);  config_read();    /* before the screen: it says which one */
    MARK(4);  farmem_probe();   /* LANG.RSC goes in far memory ... */
    MARK(5);  lang_init();      /* ... and the boot screen is in its words */
    MARK(6);  boot_begin();     /* version, CPU, memory, DOS, the two files */

    /* WHICH SCREEN.  AUTO takes the VBXE when the machine has one, which
     * is the only case that needs no file.  VBXE asked for and not found
     * is the one refusal: the alternative is to quietly give somebody
     * half the pixels they asked for and let them wonder. */
    video = config.video;
    if (video == CFG_VIDEO_AUTO)
        video = vbxe_detect() ? CFG_VIDEO_VBXE : CFG_VIDEO_ANTIC;
    else if (video == CFG_VIDEO_VBXE && !vbxe_detect()) {
        irq_remove();
        rapidus_restore();
        _exit_msg = (uint16_t)no_vbxe;
        _sys_exit();
    }
    boot_video(video);
    clock_how = (uint8_t)config.clock;  /* where to look, before the first look */
    boot_clock();
    pointer = config.mouse == CFG_MOUSE_AUTO ? GEM_POINTER : (WORD)config.mouse;
    boot_pointer(pointer);
    boot_printer();
    boot_end();                 /* three seconds, or a key */

    /* NO VECTORS, NO DESKTOP.  Every application, the desktop first,
     * calls in through COP (src/sys/abi.s), and the native-mode COP
     * vector is one of the vectors irq_install() places -- so the
     * polled regime, which can draw and read the mouse, cannot run a
     * program: the first call jumps through whatever the OS ROM holds
     * at $FFE4.  Say so and go back.  Going on instead clears the
     * screen and hangs at that first call, which is a white screen and
     * nothing after it -- what the first real Rapidus this met showed. */
    if (irq.how == IRQ_OFF) {
        rapidus_restore();
        exit_say(irq.fail == IRQ_FAIL_COPY ? LS_EXIT_NOCOPY
               : irq.fail == IRQ_FAIL_VEC  ? LS_EXIT_NOVEC
                                           : LS_EXIT_NOIRQ);
        _sys_exit();
    }

    MARK(7);
    if (video == CFG_VIDEO_VBXE) {
        /* How many of the 240 lines to show.  A tube that cuts the top
         * or bottom off is given fewer; the buffer is 240 either way, so
         * only the XDL and what the seam reports change. */
        vdev = config.screenh == 200 ? &vdev_vbxe_200
             : config.screenh == 224 ? &vdev_vbxe_224
                                     : &vdev_vbxe;
        /* A blit list started in uninitialised VRAM ($FF) never stops,
         * because the "next" bit is always set.  Clear the control
         * region first. */
        vram_fill(VR_XDL, 0x00, 0x1000);
        vbxe_xdl_hr(VR_SCREEN0, (uint16_t)vdev->h, (uint8_t)config.topmargin,
                    OVATT_WIDTH_NORMAL);
        antic_suspend();            /* its DMA off the bus: antic.h */
    } else {
        vdev = &vdev_antic;
        antic_init(AN_INK, AN_PAPER);       /* builds the list and clears */
    }

    MARK(8);  vdi_font_default();   /* the device's own face, into the device */
    MARK(9);  vdi_init();
    MARK(10); ptr_init(pointer, SCR_W / 2, SCR_H / 2);
    /* The printer, which is a destination and a language and nothing
     * else until a program opens the workstation. */
    pr_kind = config.printer;
    pr_dest = config.printto;
    /* The processes, and the mark the context switch measures from.
     * ctx_init() MUST be called from here and not from inside
     * proc_init(): the mark it takes is its own caller's S, and no
     * context may ever park above it -- src/sys/ctx.h has the argument
     * and test-m27 caught it being got wrong.  main() is the shallowest
     * place in gem4xe that can ever change hands. */
    if (!ctx_regs_ok() || !proc_init(pool_alloc(PROC_STORE, 2))
        || !ctx_make(&proc_app->p_ctx, 0))
        _sys_exit();
    ctx_init(&proc_app->p_ctx);
    gemdos_init();              /* its far state below any application's */
    MARK(11); dev_clear_screen();   /* whichever screen it is */

    MARK(12); gsx_start();
    ev_init();
    wm_init();
    mn_init();
    mn_start();     /* the registry: once, before any accessory */
    sh_init();                  /* far buffers: before any app_load */
    sc_init();                  /* the scrap directory, the same way */
    MARK(13); lang_font();      /* SYSTEM.FNT, now there is a device for it */
    fs_start();
    MARK(14); sh_main();

    /* The way back, in the reverse of the way in: interrupts off and the
     * ROM in, the screen off, the accelerator's windows written back and
     * slow, then the CPU and the stack as DOS had them. */
    irq_remove();
    if (video == CFG_VIDEO_VBXE) {
        vbxe_off();
        antic_resume();
    } else
        antic_off();
    rapidus_restore();
    _sys_exit();
}
