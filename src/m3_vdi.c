/* m3_vdi.c -- VDI conformance runner.
 *
 * Brings up the VBXE surface and a VDI workstation, then executes scripts of
 * VDI calls that the host pokes into vdi_script[] over the Altirra bridge.
 * The host runs the identical script through tools/vdiref.py and the two
 * framebuffers are compared pixel for pixel.
 *
 * Poking scripts rather than compiling them in is what makes the suite worth
 * having: a new case costs a line of Python, not a rebuild and a reflash.
 * This is the pattern vbxetxtadv's conformance_test.py established, and the
 * plan calls it the single most valuable thing in that rig.
 *
 * Script format, all 16-bit little-endian:
 *     WORD opcode        (0 ends the script)
 *     WORD n_pts         number of POINTS in ptsin (so 2*n words follow)
 *     WORD n_int         number of words in intin
 *     WORD contrl[7..10] four words: the two MFDB pointers, 0 when unused
 *     WORD sub           contrl[5], the sub-opcode (v_gdp's GDP), else 0
 *     WORD ptsin[2*n_pts]
 *     WORD intin[n_int]
 *
 * An opcode of 1000+n is an AES call rather than a VDI one, using GEM's own
 * AES function numbers (objc_draw = 42, objc_find = 43).  The object tree
 * address travels in the contrl[7] slot, the same place an MFDB does.
 *
 * vdi_scratch[] is where the host stages MFDBs and their bitmaps, so a case
 * can pass a real source form without anything being compiled in.
 *
 * An opcode of 2000+n is a benchmark op (tests/emu/bench_gem.py): the CPU
 * and the memory it can reach, which no VDI or AES call exercises on its
 * own.  intin[0] is the iteration count and the op returns a checksum in
 * intout[0].  The host times a script from the VCOUNT the runner stamps at
 * ST_VC_GO and ST_VC_DONE, against the emulator's cycle counter.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/pointer.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"    /* which device this program is about */
#include "aes/aes.h"
#include "aes/proc.h"
#include "sys/farmem.h"
#include "sys/rapidus.h"
#include "sys/irq.h"
#include "sys/abi.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/gemdos.h"
#include "vbxe/vbxe.h"
#include "antic/antic.h"   /* the other chip's DMA, off under the overlay */

#define STATUS ((volatile unsigned char *) 0x0600)

/* STATUS[0..1] 'V','D'   STATUS[2] stage   STATUS[3] go   STATUS[4] done
 * The host writes STATUS[3]; the runner answers on STATUS[4].
 * STATUS[5..6] are VCOUNT when GO was seen and just before DONE was set,
 * STATUS[7] the number of VCOUNT values in a frame, measured at start-up:
 * VCOUNT is what the target stamps a script's start and end with, finer
 * than the frame counter the VBI keeps.  The host reads the emulator's
 * cycle counter at the frame boundaries around a script and takes the
 * idle tail off with the stamps (tests/emu/bench_gem.py).
 * STATUS[8..13] the DOS (src/sys/dos.h): kind, caps, dirsep, and MEMTOP
 * as a little-endian word, then the CIO name limit.
 * STATUS[30..39] the interrupt regime (src/sys/irq.h): how, fail, fast,
 * timer_div, rom_sum, ram_sum -- the sums as two little-endian words --
 * then via and bad_byte.                                                */
#define ST_STAGE     2
#define ST_GO        3
#define ST_DONE      4
#define ST_VC_GO     5
#define ST_VC_DONE   6
#define ST_VC_PERIOD 7
#define VCOUNT (*(volatile uint8_t *)0xD40B)
#define NMIEN  (*(volatile uint8_t *)0xD40E)
#define PORTB  (*(volatile uint8_t *)0xD301)

/* Both buffers are host-poked staging, so they go in the `teststage` section,
 * which src/gem4xe.scm gives a memory of its own.  Naming the section means
 * nothing else can end up in the region the host pokes, and it keeps the
 * runner's map identical to the driver's everywhere else. */
/* From src/farload.s -- reports the bank the far code is running in. */
extern unsigned int _fl_running_bank(void);
/* From src/crt_atari.s -- back to DOS; never returns. */
extern void _sys_exit(void);

/* The three staging buffers are the gate rig's, not the driver's, and
 * they share the banked window with the application pool: what they do
 * not take, a loaded application and its resource can have.  The
 * conformance gates need them full size; the desktop gates need a few
 * calls' worth and a pool the size of GEM.COM's, so build/m3desk.xex is
 * this same runner compiled with the three sizes cut and linked with
 * the pool ending where its staging begins (the Makefile). */
#ifndef SCRIPT_WORDS
#define SCRIPT_WORDS 1024
#endif
SECTION("teststage")
volatile WORD vdi_script[SCRIPT_WORDS];

#ifndef SCRATCH_BYTES
#define SCRATCH_BYTES 2048
#endif
SECTION("teststage")
volatile unsigned char vdi_scratch[SCRATCH_BYTES];

/* Per-call output record, so the harness can check what an opcode RETURNS and
 * not only what it draws.  Without this the input and inquiry opcodes -- most
 * of what is left for the AES -- would be untestable.
 *   [0] contrl[2]  [1] contrl[4]  [2..16] intout[0..14]  [17..19] ptsout[0..2]
 * Fifteen intout words because evnt_multi returns seven and then the
 * eight-word message a MU_MESAG delivered (tools/vdiref.py RESULT_WORDS). */
#define RESULT_WORDS 20
#define RESULT_INTOUT 15
#ifndef MAX_RESULTS
#define MAX_RESULTS  48
#endif
SECTION("teststage")
volatile WORD vdi_results[MAX_RESULTS * RESULT_WORDS];
/* The count is the one word the host polls WHILE a call runs, so it
 * stays in ordinary data, out of $4000-$7FFF: SpartaDOS X banks its
 * own RAM in there for the length of a CIO call, and the bridge reads
 * what the CPU sees (tests/emu/m14_sparta.py).  The buffers above are
 * only touched between calls. */
volatile WORD vdi_result_count;


/* How many values VCOUNT takes in a frame -- 156 on PAL, 131 on NTSC --
 * read off the hardware rather than assumed: the largest value seen
 * between two wraps, plus one.  Costs a frame or two, once. */
static uint8_t vcount_period(void)
{
    uint8_t last = VCOUNT, max = 0, wraps = 0;
    while (wraps < 2) {
        uint8_t v = VCOUNT;
        if (v < last)
            wraps++;
        if (v > max)
            max = v;
        last = v;
    }
    return (uint8_t)(max + 1);
}


/* ---- benchmark ops -------------------------------------------------------
 * 2000+n.  The memory ops read, write or copy BENCH_BYTES at a time, n
 * times, through a far pointer whatever the space, so the loop is the same
 * and the spaces differ only in the bus behind them:
 *   space 0  the 24-bit address in the next two intin words
 *   space 1  VRAM at that address, mapped through the MEMAC window
 *   space 2  a buffer on the runner's stack: bank $00, the fast SRAM
 *   space 3  a second such buffer, for a bank-$00 to bank-$00 copy
 * The divide ops go through _Div16 (the override, tools/ccbug B2) and the
 * library's 32-bit divide; the float op is whatever the library does. */
#define BENCH_BYTES 256

/* The memory loops move words, counting down, with the counter and the
 * sum in the direct page (Phase 8c): as byte loops with stack locals they
 * cost 24 instructions a byte, which buried the bus behind the loop.
 * Scalars only -- an indexed direct-page array is compiler bug B6. */
static TINY UWORD bench_j;
static TINY UWORD bench_sum;

static uint8_t FAR *bench_place(WORD lo, WORD hi, WORD space, uint8_t *buf)
{
    uint32_t a = ((uint32_t)(UWORD)hi << 16) | (UWORD)lo;
    switch (space) {
    case 1:  return (uint8_t FAR *)vram_win(a);
    case 2:  return (uint8_t FAR *)buf;
    case 3:  return (uint8_t FAR *)(buf + BENCH_BYTES);
    default: return (uint8_t FAR *)a;
    }
}

static UWORD bench_op(WORD which)
{
    WORD n = intin[0], k;
    UWORD sum = 0;
    uint8_t buf[2 * BENCH_BYTES];
    switch (which) {
    case 1: {                                   /* 16-bit divide */
        WORD a = 32767, b = 1;
        for (k = 0; k < n; k++) {
            sum += (UWORD)(a / b);
            a -= 7;
            b = (b & 15) + 1;
        }
        break;
    }
    case 2: {                                   /* 32-bit divide */
        int32_t a = 0x7FFFFFFFL, b = 1;
        for (k = 0; k < n; k++) {
            sum += (UWORD)(a / b);
            a -= 70001L;
            b = (b & 15) + 1;
        }
        break;
    }
    case 3: {                                   /* float: mul, add, div */
        float a = 1.5f;
        for (k = 0; k < n; k++) {
            a = a * 1.0001f + 0.5f;
            a = a / 1.0002f;
        }
        sum = (UWORD)a;
        break;
    }
    case 4:                                     /* read */
        bench_sum = 0;
        for (k = 0; k < n; k++) {
            const UWORD FAR *p = (const UWORD FAR *)
                bench_place(intin[1], intin[2], intin[3], buf);
            bench_j = BENCH_BYTES / 2;
            do bench_sum += *p++; while (--bench_j);
        }
        sum = bench_sum;
        break;
    case 5:                                     /* write */
        for (k = 0; k < n; k++) {
            UWORD FAR *p = (UWORD FAR *)
                bench_place(intin[1], intin[2], intin[3], buf);
            bench_j = BENCH_BYTES / 2;
            do *p++ = bench_j; while (--bench_j);
        }
        sum = (UWORD)n;
        break;
    case 6:                                     /* copy: src, then dst */
        for (k = 0; k < n; k++) {
            const UWORD FAR *s = (const UWORD FAR *)
                bench_place(intin[1], intin[2], intin[3], buf);
            UWORD FAR *d = (UWORD FAR *)
                bench_place(intin[4], intin[5], intin[6], buf);
            bench_j = BENCH_BYTES / 2;
            do *d++ = *s++; while (--bench_j);
        }
        sum = (UWORD)n;
        break;
    case 7: {                                   /* vram_write: the driver's upload */
        uint32_t a = ((uint32_t)(UWORD)intin[2] << 16) | (UWORD)intin[1];
        for (k = 0; k < n; k++)
            vram_write(a, buf, BENCH_BYTES);
        sum = (UWORD)n;
        break;
    }
    default:
        break;
    }
    return sum;
}


/* System ops, 3000 and up: what a script needs from outside the VDI and
 * the AES.  3000 selects a pointing device (kind, x, y) -- the interrupt
 * handler starts sampling PORTA for a relative one; 3001 asks for the
 * return to DOS once the script is done and reported; 3002 runs the
 * target for intin[0] frames WITHOUT polling anything, which is what
 * proves the handler counts without help; 3003 is one pass of the input
 * machinery (vdi_input_poll), as an AES wait would make, so what the
 * handler counted reaches ptr_seen and vq_mouse; 3004 loads and runs the
 * gate application (below); 3005-3009 are CIO (src/sys/cio.h): open
 * (name address, aux1, aux2), close (iocb), read / write / getrec (iocb,
 * buffer address, length), the name and the buffer staged by the host in
 * vdi_scratch, and 3014 is XIO (command, name address, aux1, aux2).
 * Those add [6] the status -- or, for open, the IOCB number -- [7] the
 * bytes moved and [8] the round trips made so far.  3012 is one GEMDOS
 * call on the block at intin[0] (src/sys/gemdos.h), adding [6] the
 * round trips so far, [7] the GEMDOS calls made and [8] the ones
 * refused; 3013 is gemdos_release(), the application's exit.
 * intout[0..5] report the handler's state after each: frames, timer,
 * the two axes, keys, fault. */
static uint8_t exit_req;

/* The Phase 10 gate application, packed into the image by tools/mkg4a.py
 * (build/app_blob.c).  Sys op 4 loads it, runs it and frees it, and adds
 * to the record: [6] the loader's status, [7] the near base it chose,
 * [8] the far bank, [9] what the application's main() returned, [10] the
 * COP calls the ABI took and [11] the ones it refused. */
extern const uint8_t FAR app_blob[];
extern const uint32_t app_blob_len;

static void sys_op(WORD op)
{
    WORD c4 = 6;
    switch (op) {
    case 0:
        ptr_init((ptr_kind)intin[0], intin[1], intin[2]);
        break;
    case 1:
        exit_req = 1;
        break;
    case 2: {
        WORD n = intin[0];
        if (irq.how != IRQ_OFF) {
            uint16_t f = irq_frames;
            while ((uint16_t)(irq_frames - f) < (uint16_t)n)
                ;
        } else {
            uint8_t last = VCOUNT;
            while (n) {
                uint8_t vc = VCOUNT;
                if (vc < last)
                    n--;
                last = vc;
            }
        }
        break;
    }
    case 3:
        vdi_input_poll();
        break;
    case 4: {
        APP app;
        int16_t st, ret = 0;
        gem_calls = app_calls = gem_bad = 0;
        st = app_load(app_blob, app_blob_len, &app);
        if (st == APP_OK) {
            /* What the SHELL would have done (sh_ldapp): name the process
             * after the file it is about to run, so that appl_find can
             * find it.  The blob is packed into this image and has no
             * name of its own, so the name is the one the same program
             * is installed under and runs by under the real shell --
             * M11.G4A (the Makefile's SHELL_FILES). */
            proc_name(proc_app, "M11.G4A");
            ret = app_exec(&app);
            app_free(&app);
        }
        intout[6]  = st;
        intout[7]  = (WORD)app.near_base;
        intout[8]  = (WORD)(app.far_addr >> 16);
        intout[9]  = ret;
        intout[10] = (WORD)gem_calls;
        intout[11] = (WORD)gem_bad;
        c4 = 12;
        break;
    }
    case 5: case 6: case 7: case 8: case 9: case 14: {
        uint16_t got = 0;
        int16_t st;
        void *buf = (void *)(uint16_t)intin[1];
        switch (op) {
        case 5:  st = cio_open((const char *)(uint16_t)intin[0],
                               (uint8_t)intin[1], (uint8_t)intin[2]); break;
        case 6:  st = cio_close(intin[0]); break;
        case 7:  st = cio_read(intin[0], buf, intin[2], &got); break;
        case 8:  st = cio_write(intin[0], buf, intin[2]); break;
        case 14: st = cio_xio((uint8_t)intin[0], (const char *)(uint16_t)intin[1],
                              (uint8_t)intin[2], (uint8_t)intin[3]); break;
        default: st = cio_getrec(intin[0], buf, intin[2], &got); break;
        }
        intout[6] = st;
        intout[7] = (WORD)got;
        intout[8] = (WORD)cio_calls;
        c4 = 9;
        break;
    }
    case 10:                                    /* GEM name -> CIO name: in, out */
        sh_cioname((const char *)(uint16_t)intin[0], (char *)(uint16_t)intin[1]);
        c4 = 6;
        break;
    /* The pool and the far allocator, so the gate can see what a load
     * took and a free gave back -- and, with ints, so it can stand in
     * for an application that holds the pool: intin[0] bytes taken,
     * then the cursor wound back to intin[1] when that is not zero. */
    case 11:
        if (contrl[3] >= 1 && intin[0] > 0)
            pool_alloc((uint16_t)intin[0], 2);
        if (contrl[3] >= 2 && intin[1])
            pool_release((uint16_t)intin[1]);
        intout[6] = (WORD)pool_mark();
        intout[7] = (WORD)pool_room();
        intout[8] = (WORD)farmem.brk;
        intout[9] = (WORD)(farmem.brk >> 16);
        c4 = 10;
        break;
    /* GEMDOS, on a call block the harness staged in bank $00 (its ret,
     * function and arguments as src/sys/gemdos.h lays them out): the
     * result, and the round trips it cost.  13 is the application's
     * exit as GEMDOS sees it, between tests. */
    case 12:
        gemdos_call((uint32_t)(uint16_t)intin[0]);
        intout[6] = (WORD)cio_calls;
        intout[7] = (WORD)gemdos_calls;
        intout[8] = (WORD)gemdos_bad;
        c4 = 9;
        break;
    case 13:
        gemdos_release();
        c4 = 6;
        break;
    /* The environment a CIO call runs in, one knob at a time, so a DOS
     * path that dies under gem4xe and lives under a plain program can be
     * bisected from the host: intin[0] the knob, intin[1] its value. */
    case 15:
        switch (intin[0]) {
        case 0: irq_remove(); break;
        case 1: rapidus_restore(); break;
        case 2: rapidus_reg_write(RAP_MCR, (uint8_t)intin[1]); break;
        case 3: rapidus_reg_write(RAP_CMCR, (uint8_t)intin[1]); break;
        case 4: irq_cio_swap = (uint8_t)intin[1]; break;
        case 5: cio_env = (uint8_t)intin[1]; break;
        case 6: NMIEN = (uint8_t)intin[1]; break;
        default: break;
        }
        intout[6] = rapidus.present ? rapidus_reg_read(RAP_MCR) : 0;
        intout[7] = rapidus.present ? rapidus_reg_read(RAP_CMCR) : 0;
        intout[8] = irq_cio_swap;
        intout[9] = PORTB;
        c4 = 10;
        break;
    /* The shell loop (src/aes/shel.c): DESKTOP.G4A from the boot disk,
     * whatever it asks for, until a shutdown.  [6] what sh_main returned
     * -- the programs run, or a negative APP_* status -- [7] the runs,
     * [8] the last program's main() result, [9] the last load status,
     * [10] and [11] the ABI's calls taken and refused, over all of it. */
    case 16:
        gem_calls = app_calls = gem_bad = 0;
        intout[6]  = sh_main();
        intout[7]  = sh_runs;
        intout[8]  = sh_lastret;
        intout[9]  = sh_lastrc;
        intout[10] = (WORD)gem_calls;
        intout[11] = (WORD)gem_bad;
        c4 = 12;
        break;
    case 17: {
        /* THE SCREEN, AGAIN, AT ANOTHER WIDTH.  The overlay has three
         * (src/vbxe/vbxe.h) and the conformance suite should answer for
         * all of them, but `vdev` is set before main() reaches anything
         * the harness can talk to -- so this does over what main() did,
         * in the same order, rather than the harness getting a word in
         * earlier.  It is a re-bring-up and not a mode switch: the seam
         * says vdev is set once and never moves, and every case opens
         * its own workstation afterwards, so what this leaves behind is
         * a machine that has just booted at a different size.
         *
         * intin[0] is the width INDEX, which is also the OVATT code. */
        WORD wi = intin[0];
        if (wi < 0 || wi >= VB_WIDTHS) {
            intout[6] = -1;
            c4 = 7;
            break;
        }
        vram_fill(VR_XDL, 0x00, 0x1000);
        vdev = &vdev_vbxe_tab[wi][0];
        vbxe_xdl_hr(VR_SCREEN0, (uint16_t)vdev->h, 0, (uint8_t)wi);
        vdi_font_default();
        vdi_init();
        ptr_init(PTR_NONE, (WORD)(vdev->w / 2), (WORD)(vdev->h / 2));
        intout[6] = 0;
        intout[7] = (WORD)vdev->w;
        intout[8] = (WORD)vdev->h;
        intout[9] = (WORD)vdev->stride;
        c4 = 10;
        break;
    }
    /* THE SCRAP MANAGER, which is the only AES call that reaches the
     * disk (src/aes/scrap.c).  intin[0] is the near address of the scrap
     * DIRECTORY -- a path ending in a backslash, as the Compendium says
     * one does; [6] what sc_write answered and [7] what sc_clear did.
     *
     * It is a SYS op and not one of the library's 1000+n, because those
     * are compared against tools/aesref.py and a host model cannot hold
     * a disk.  What checks this is tests/emu/m15_gdos.py, on either side
     * of the call: GEMDOS makes the SCRAP.* files and looks for them
     * again with Fsfirst afterwards. */
    case 18:
        sc_init();                  /* the AES's start-up does this (src/gem.c);
                                     * the conformance runner's op 1000 does it
                                     * too, and this gate runs neither */
        intout[6] = sc_write((const char *)(uint16_t)intin[0]);
        intout[7] = sc_clear();
        c4 = 8;
        break;
    default:
        break;
    }
    intout[0] = (WORD)irq_frames;
    intout[1] = (WORD)irq_timer;
    intout[2] = (WORD)irq_qlo;
    intout[3] = (WORD)irq_qhi;
    intout[4] = (WORD)irq_kb_count;
    intout[5] = (WORD)irq_fault;
    contrl[2] = 0;
    contrl[4] = c4;
}

static void run_script(void)
{
    WORD i = 0;
    vdi_result_count = 0;
    while (i < SCRIPT_WORDS) {
        WORD op    = vdi_script[i++];
        WORD npts, nint, k;
        if (op == 0)
            return;
        npts = vdi_script[i++];
        nint = vdi_script[i++];
        contrl[7]  = vdi_script[i++];
        contrl[8]  = vdi_script[i++];
        contrl[9]  = vdi_script[i++];
        contrl[10] = vdi_script[i++];
        contrl[5]  = vdi_script[i++];   /* the sub-opcode: v_gdp's GDP */
        for (k = 0; k < npts * 2 && k < PTSIN_SIZE; k++)
            ptsin[k] = vdi_script[i++];
        for (k = 0; k < nint && k < INTIN_SIZE; k++)
            intin[k] = vdi_script[i++];
        if (op >= 3000) {
            contrl[3] = nint;           /* how many ints the op was given */
            sys_op((WORD)(op - 3000));
        } else if (op >= 2000) {
            intout[0] = (WORD)bench_op((WORD)(op - 2000));
            contrl[2] = 0;
            contrl[4] = 1;
        } else if (op >= 1000) {
            OBJECT *tree = (OBJECT *)(uint16_t)contrl[7];
            GRECT clip;
            WORD c2 = 0, c4 = 0;
            /* The AES calls the VDI underneath, which sets contrl[2]/[4]
             * and intout[0] for its own calls; the record wants what the
             * AES op declares, so its counts are set after it returns and
             * its outputs go through a local first. */
            WORD out[8] = {0, 0, 0, 0, 0, 0, 0, 0}; /* what an op leaves alone reads 0 */
            /* AES ops are 1000 + the AES function number, with the tree
             * address in the contrl[7] slot, the clip in ptsin and the
             * scalars in intin.  Results land in intout/ptsout so the
             * record below captures them like a VDI call's.  Op 1000 is
             * the AES's own start-up: it belongs in the script so that the
             * AES's attribute cache and the workstation it caches are set
             * up together, on both sides, every case. */
            switch (op - 1000) {
            case 0:                         /* gsx_start, events, windows, menus */
                gsx_start();
                ev_init();
                wm_init();
                mn_init();
                mn_start();                 /* the registry: once per AES start */
                sh_init();                  /* far buffers: before any app_load */
                sc_init();                  /* the scrap directory, the same way */
                lang_init();                /* LANG.RSC, or the English in the image */
                lang_font();                /* and SYSTEM.FNT, into the device */
                fs_start();                 /* the selector's name slots, too */
                break;
            case 12:                        /* appl_write: id, len, msg[8] */
                mq_put(proc_app, &intin[2]);
                intout[0] = 1;
                c4 = 1;
                break;
            /* The event calls block until the host injects input; the host
             * knows one is in progress because vdi_result_count has reached
             * this op's index and not passed it.  Results follow the AES's
             * int_out layout: [0] the return value, then the outputs. */
            case 20:                        /* evnt_keybd */
                intout[0] = ev_keybd();
                c4 = 1;
                break;
            case 21:                        /* evnt_button */
                out[0] = ev_button(intin[0], (UWORD)intin[1],
                                   (UWORD)intin[2], &out[1]);
                for (k = 0; k < 5; k++)
                    intout[k] = out[k];
                c4 = 5;
                break;
            case 22:                        /* evnt_mouse */
                out[0] = ev_mouse((const MOBLK *)&intin[0], &out[1]);
                for (k = 0; k < 5; k++)
                    intout[k] = out[k];
                c4 = 5;
                break;
            case 23:                        /* evnt_mesag: the message */
                ev_mesag(out);
                for (k = 0; k < 8; k++)
                    intout[k] = out[k];
                c4 = 8;
                break;
            case 24: {                      /* evnt_timer: lo, hi */
                uint32_t ms = (uint32_t)(uint16_t)intin[0]
                            | ((uint32_t)(uint16_t)intin[1] << 16);
                intout[0] = ev_timer(ms);
                c4 = 1;
                break;
            }
            case 25: {                      /* evnt_multi, GEM int_in order:
                                             * flags clicks mask state
                                             * MOBLK1[5] MOBLK2[5] lo hi */
                uint32_t ms = (uint32_t)(uint16_t)intin[14]
                            | ((uint32_t)(uint16_t)intin[15] << 16);
                WORD msg[8] = {0, 0, 0, 0, 0, 0, 0, 0};
                intout[0] = ev_multi(intin[0], (const MOBLK *)&intin[4],
                                     (const MOBLK *)&intin[9], ms,
                                     combine_cms(intin[1], (UWORD)intin[2],
                                                 (UWORD)intin[3]),
                                     msg, out);
                for (k = 0; k < 6; k++)
                    intout[1 + k] = out[k];
                /* the message, if one was delivered, else zeros */
                for (k = 0; k < 8; k++)
                    intout[7 + k] = msg[k];
                c4 = 15;
                break;
            }
            case 26:                        /* evnt_dclick */
                intout[0] = ev_dclick(intin[0], intin[1]);
                c4 = 1;
                break;
            /* The menu library, AES 30..35, the tree in contrl[7] as for
             * the object calls.  menu_text's string is at intin[1], a
             * bank-$00 address the host staged. */
            case 30:                        /* menu_bar: showit */
                mn_bar(tree, intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 31:                        /* menu_icheck: item, check */
                intout[0] = do_chg(tree, intin[0], CHECKED, intin[1],
                                   FALSE, FALSE);
                c4 = 1;
                break;
            case 32:                        /* menu_ienable: item, enable */
                intout[0] = do_chg(tree, intin[0] & 0x7fff, DISABLED,
                                   !intin[1], (intin[0] & 0x8000) != 0,
                                   FALSE);
                c4 = 1;
                break;
            case 33:                        /* menu_tnormal: title, normal */
                intout[0] = do_chg(tree, intin[0], SELECTED, !intin[1],
                                   TRUE, TRUE);
                c4 = 1;
                break;
            case 34:                        /* menu_text: item, text addr */
                mn_text(tree, intin[0], (const char *)(uint16_t)intin[1]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 35:                        /* menu_register: pid, str addr */
                intout[0] = mn_register(intin[0],
                                        (const char *)(uint16_t)intin[1]);
                c4 = 1;
                break;
            case 40:                        /* objc_add: parent, child */
                ob_add(tree, intin[0], intin[1]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 41:                        /* objc_delete: obj */
                intout[0] = ob_delete(tree, intin[0]);
                c4 = 1;
                break;
            case 42:                        /* objc_draw */
                clip.g_x = ptsin[0]; clip.g_y = ptsin[1];
                clip.g_w = ptsin[2]; clip.g_h = ptsin[3];
                objc_draw(tree, intin[0], intin[1], &clip);
                break;
            case 43:                        /* objc_find */
                intout[0] = objc_find(tree, intin[0], intin[1],
                                      ptsin[0], ptsin[1]);
                c4 = 1;
                break;
            case 44:                        /* objc_offset */
                objc_offset(tree, intin[0], &intout[0], &intout[1]);
                c4 = 2;
                break;
            case 46: {                      /* objc_edit */
                WORD idx = intin[2];
                intout[1] = objc_edit(tree, intin[0], intin[1], &idx, intin[3]);
                intout[0] = idx;
                c4 = 2;
                break;
            }
            case 47:                        /* objc_change */
                clip.g_x = ptsin[0]; clip.g_y = ptsin[1];
                clip.g_w = ptsin[2]; clip.g_h = ptsin[3];
                objc_change(tree, intin[0], &clip, (UWORD)intin[1], intin[2]);
                break;
            case 50:                        /* form_do */
                intout[0] = form_do(tree, intin[0]);
                c4 = 1;
                break;
            case 51: {                      /* form_dial: type, pi, pt */
                GRECT pi, pt;
                pi.g_x = intin[1]; pi.g_y = intin[2];
                pi.g_w = intin[3]; pi.g_h = intin[4];
                pt.g_x = intin[5]; pt.g_y = intin[6];
                pt.g_w = intin[7]; pt.g_h = intin[8];
                intout[0] = form_dial(intin[0], &pi, &pt);
                c4 = 1;
                break;
            }
            case 52:                        /* form_alert: default button,
                                             * the string in the tree slot */
                intout[0] = fm_alert(intin[0], (const char *)tree);
                c4 = 1;
                break;
            case 53:                        /* form_error: the DOS error
                                             * number; the text is the
                                             * system's own (LANG.RSC) */
                intout[0] = fm_error(intin[0]);
                c4 = 1;
                break;
            case 54:                        /* form_center (ob_center) */
                ob_center(tree, &clip);
                intout[0] = clip.g_x; intout[1] = clip.g_y; intout[2] = clip.g_w;
                ptsout[0] = clip.g_h; ptsout[1] = 0;
                c4 = 3;
                c2 = 1;
                break;
            case 55: {                      /* form_keybd: obj, char, nxtob */
                WORD ch = intin[1], nxt = intin[2];
                intout[0] = form_keybd(tree, intin[0], &ch, &nxt);
                intout[1] = ch;
                intout[2] = nxt;
                c4 = 3;
                break;
            }
            case 56: {                      /* form_button: obj, clks */
                WORD nxt = 0;
                intout[0] = form_button(tree, intin[0], intin[1], &nxt);
                intout[1] = nxt;
                c4 = 2;
                break;
            }
            case 70:                        /* graf_rubbox: x,y,minw,minh */
                gr_rubbox(intin[0], intin[1], intin[2], intin[3],
                          &out[0], &out[1]);
                intout[0] = 1;
                intout[1] = out[0];
                intout[2] = out[1];
                c4 = 3;
                break;
            case 71: {                      /* graf_dragbox: w,h,sx,sy,bound */
                GRECT pc;
                pc.g_x = intin[4]; pc.g_y = intin[5];
                pc.g_w = intin[6]; pc.g_h = intin[7];
                gr_dragbox(intin[0], intin[1], intin[2], intin[3], &pc,
                           &out[0], &out[1]);
                intout[0] = 1;
                intout[1] = out[0];
                intout[2] = out[1];
                c4 = 3;
                break;
            }
            case 109:                       /* wind_new */
                wm_new();
                intout[0] = 1;
                c4 = 1;
                break;
            case 72:                        /* graf_mbox: w, h, sx, sy, ex, ey */
                gr_movebox(intin[0], intin[1], intin[2], intin[3],
                           intin[4], intin[5]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 73:                        /* graf_growbox: pi, pt */
            case 74: {                      /* graf_shrinkbox */
                GRECT pi, pt;
                pi.g_x = intin[0]; pi.g_y = intin[1];
                pi.g_w = intin[2]; pi.g_h = intin[3];
                pt.g_x = intin[4]; pt.g_y = intin[5];
                pt.g_w = intin[6]; pt.g_h = intin[7];
                if (op - 1000 == 73)
                    gr_growbox(&pi, &pt);
                else
                    gr_shrinkbox(&pi, &pt);
                intout[0] = 1;
                c4 = 1;
                break;
            }
            case 75:                        /* graf_watchbox: obj, in, out */
                intout[0] = gr_watchbox(tree, intin[0], intin[1], intin[2]);
                c4 = 1;
                break;
            case 76:                        /* graf_slidebox: parent, obj, orient */
                intout[0] = gr_slidebox(tree, intin[0], intin[1], intin[2]);
                c4 = 1;
                break;
            case 78:                        /* graf_mouse: mode, form */
                /* GEM passes a pointer to USER_DEF's 37 words; a script
                 * record carries the words themselves, after the mode,
                 * so the harness need stage nothing for it */
                gr_mouse(intin[0], &intin[1]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 79:                        /* graf_mkstate */
                gr_mkstate(&out[0], &out[1], &out[2], &out[3]);
                intout[0] = 1;
                for (k = 0; k < 4; k++)
                    intout[1 + k] = out[k];
                c4 = 5;
                break;
            /* The scrap manager: the path is the staged buffer, and the
             * same buffer serves both ways -- scrp_read fills it, and
             * scrp_write takes what is in it (src/aes/scrap.c). */
            case 80:                        /* scrp_read: path out */
                intout[0] = sc_read((char *)(uint16_t)contrl[7]);
                c4 = 1;
                break;
            case 81:                        /* scrp_write: path in */
                intout[0] = sc_write((const char *)(uint16_t)contrl[7]);
                c4 = 1;
                break;
            /* The window manager, in GEM int_in order.  Rectangles are
             * four words; wind_get returns 1 then its four words; wind_set
             * takes the field's words as they stand in intin, WF_NAME and
             * WF_NEWDESK with their address high word first as on the
             * 68000 (only the low word can mean anything here). */
            case 100: {                     /* wind_create: kind, rect */
                GRECT t;
                t.g_x = intin[1]; t.g_y = intin[2];
                t.g_w = intin[3]; t.g_h = intin[4];
                intout[0] = wm_create(intin[0], &t);
                c4 = 1;
                break;
            }
            case 101: {                     /* wind_open: wh, rect */
                GRECT t;
                t.g_x = intin[1]; t.g_y = intin[2];
                t.g_w = intin[3]; t.g_h = intin[4];
                intout[0] = wm_open(intin[0], &t);
                c4 = 1;
                break;
            }
            case 102:                       /* wind_close: wh */
                intout[0] = wm_close(intin[0]);
                c4 = 1;
                break;
            case 103:                       /* wind_delete: wh */
                intout[0] = wm_delete(intin[0]);
                c4 = 1;
                break;
            case 104:                       /* wind_get: wh, field */
                intout[0] = wm_get(intin[0], intin[1], out, &intin[2]);
                for (k = 0; k < 4; k++)
                    intout[1 + k] = out[k];
                c4 = 5;
                break;
            case 105:                       /* wind_set: wh, field, words */
                intout[0] = wm_set(intin[0], intin[1], &intin[2]);
                c4 = 1;
                break;
            case 106:                       /* wind_find: x, y */
                intout[0] = wm_find(intin[0], intin[1]);
                c4 = 1;
                break;
            case 107:                       /* wind_update: what */
                wm_update(intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 108:                       /* wind_calc: type, kind, rect */
                wm_calc(intin[0], (UWORD)intin[1], intin[2], intin[3],
                        intin[4], intin[5], &out[0], &out[1], &out[2], &out[3]);
                intout[0] = 1;
                for (k = 0; k < 4; k++)
                    intout[1 + k] = out[k];
                c4 = 5;
                break;
            /* The resource library: the name staged by the host in
             * contrl[7]; where the file landed and what the pool has left
             * come back so the gate can read the fixed-up image out of
             * bank $00 and compare it with the host's, whole. */
            case 110:                       /* rsrc_load: name */
                {
                    RSHDR h;
                    intout[0] = rs_load((const char *)(uint16_t)contrl[7], 0);
                    rs_header(&h);
                    intout[1] = (WORD)(uint16_t)rs_loaded();
                    intout[2] = rs_loaded() ? (WORD)h.rsh_rssize : 0;
                    intout[3] = (WORD)pool_room();
                    intout[4] = rs_loaded() ? (WORD)((uint16_t)rs_loaded() + h.rsh_trindex) : 0;
                }
                c4 = 5;
                break;
            case 111:                       /* rsrc_free */
                intout[0] = rs_free();
                intout[1] = (WORD)pool_room();
                c4 = 2;
                break;
            case 112: {                     /* rsrc_gaddr: type, index */
                uint32_t a = 0;
                intout[0] = rs_gaddr((UWORD)intin[0], (UWORD)intin[1], &a);
                intout[1] = (WORD)a;
                intout[2] = (WORD)(a >> 16);
                c4 = 3;
                break;
            }
            case 113:                       /* rsrc_saddr: type, index, lo, hi */
                intout[0] = rs_saddr((UWORD)intin[0], (UWORD)intin[1],
                                     (uint32_t)(UWORD)intin[2] | ((uint32_t)(UWORD)intin[3] << 16));
                c4 = 1;
                break;
            case 114:                       /* rsrc_obfix: tree, object */
                rs_obfix(tree, intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;

            /* The shell library: the first buffer staged in contrl[7], a
             * second one's address in intin (the script format carries one
             * address a record). */
            case 120:                       /* shel_read: cmd; tail */
                sh_read((char *)(uint16_t)contrl[7], (char *)(uint16_t)intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 121:                       /* shel_write: doex, isgr, iscr, tail; cmd */
                intout[0] = sh_write(intin[0], intin[1], intin[2],
                                     (const char *)(uint16_t)contrl[7],
                                     (const char *)(uint16_t)intin[3]);
                intout[1] = sh_doexec;
                intout[2] = sh_isgem;
                c4 = 3;
                break;
            case 122:                       /* shel_get: buf, len */
                sh_get((uint32_t)(uint16_t)contrl[7], intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 123:                       /* shel_put: buf, len */
                sh_put((uint32_t)(uint16_t)contrl[7], intin[0]);
                intout[0] = 1;
                c4 = 1;
                break;
            case 124:                       /* shel_find: path */
                intout[0] = sh_find((char *)(uint16_t)contrl[7]);
                intout[1] = (WORD)cio_last;
                c4 = 2;
                break;
            case 90:                        /* fsel_input: path; sel address */
            case 91: {                      /* fsel_exinput: ... ; label address */
                char *path = (char *)(uint16_t)contrl[7];
                char *sel = (char *)(uint16_t)intin[0];
                const char *label = (op - 1000 == 91) ? (const char *)(uint16_t)intin[1] : 0;
                WORD button = -1;
                intout[0] = fs_input(path, sel, &button, label);
                intout[1] = button;
                c4 = 2;
                break;
            }
            case 125: {                     /* shel_envrn: name -> value address */
                const char *v = 0;
                sh_envrn(&v, (const char *)(uint16_t)contrl[7]);
                intout[0] = 1;
                intout[1] = (WORD)(uint16_t)v;
                c4 = 2;
                break;
            }
            default:
                break;
            }
            contrl[2] = c2;
            contrl[4] = c4;
        } else {
        contrl[0] = op;
        contrl[1] = npts;
        contrl[3] = nint;
        contrl[6] = VDI_PHYS_HANDLE;    /* the script draws where the AES does */
        vdi();
        }
        if (vdi_result_count < MAX_RESULTS) {
            volatile WORD *r = &vdi_results[vdi_result_count * RESULT_WORDS];
            /* Only the words the call DECLARES are meaningful.  The VDI
             * contract is that intout/ptsout are valid up to contrl[4] and
             * contrl[2]; anything beyond is leftover from an earlier call and
             * a caller must not read it.  Recording it verbatim would make the
             * harness stricter than the contract and fail correct code. */
            r[0] = contrl[2];
            r[1] = contrl[4];
            for (k = 0; k < RESULT_INTOUT; k++)
                r[2 + k] = (WORD)(contrl[4] > k ? intout[k] : 0);
            r[2 + RESULT_INTOUT]     = (WORD)(contrl[2] > 0 ? ptsout[0] : 0);
            r[2 + RESULT_INTOUT + 1] = (WORD)(contrl[2] > 0 ? ptsout[1] : 0);
            r[2 + RESULT_INTOUT + 2] = (WORD)(contrl[2] > 1 ? ptsout[2] : 0);
            vdi_result_count++;
        }
    }
}

TASK void main(void)
{
    /* Touch the scratch area and the result array so the linker keeps
     * them: nothing else on the target references either -- the host is
     * the only writer.  BEFORE the signature, not after: the harness
     * stages a case as soon as it sees 'VD', and everything below here
     * (farmem_probe alone is thousands of frames' worth of bus cycles)
     * is time in which a write of ours would land on what it staged.
     * That race cost a morning: it moved with the size of the image,
     * which is exactly the shape of a bug that looks like the compiler
     * and is not (docs/phase6.md). */
    vdi_scratch[0] = 0;
    vdi_results[0] = 0;

    STATUS[0] = 'V';
    STATUS[1] = 'D';
    STATUS[ST_STAGE] = 0;
    STATUS[ST_GO] = 0;
    STATUS[ST_DONE] = 0;

    /* Which DOS loaded us: read while the machine is still all its own. */
    dos_ident();
    STATUS[8] = dos.kind;
    STATUS[9] = dos.caps;
    STATUS[10] = (unsigned char)dos.dirsep;
    STATUS[11] = (unsigned char)dos.memtop;
    STATUS[12] = (unsigned char)(dos.memtop >> 8);
    STATUS[13] = CIO_NAME_MAX;

    /* First, before the MEMAC window exists and before anything is timed:
     * switch the accelerator's SRAM in over bank $00.  Reported so the
     * harness can refuse a target that is still running its data at
     * 1.79 MHz -- six phases did, unnoticed. */
    rapidus_speedup();
    STATUS[25] = rapidus.present;
    STATUS[26] = rapidus.mcr_before;
    STATUS[27] = rapidus.mcr_after;
    STATUS[28] = rapidus.cmcr_after;
    STATUS[29] = rapidus.synced;

    /* Then the interrupt regime: the OS ROM shadowed, the native vectors
     * filled, the VBI and POKEY on.  Reported so the harness can tell a
     * machine that fell back to polling from one that did not.  Then,
     * as src/gem.c asks it, whether the OS takes COPs of its own: an
     * application's foreign COP goes to it (src/sys/abi.s).  That is a
     * CIO call, and a CIO call wants the vectors in first. */
    irq_install();
    abi_probe_os();
    STATUS[30] = irq.how;
    STATUS[31] = irq.fail;
    STATUS[32] = irq.fast;
    STATUS[33] = irq.timer_div;
    STATUS[34] = (unsigned char)irq.rom_sum;
    STATUS[35] = (unsigned char)(irq.rom_sum >> 8);
    STATUS[36] = (unsigned char)irq.ram_sum;
    STATUS[37] = (unsigned char)(irq.ram_sum >> 8);
    STATUS[38] = irq.via;
    STATUS[39] = irq.bad_byte;

    if (!vbxe_detect()) {
        STATUS[ST_STAGE] = 0xEE;
        for (;;)
            ;
    }
    /* A blit list started in uninitialised VRAM ($FF) never stops, because the
     * "next" bit is always set.  Clear the control region before first use. */
    vram_fill(VR_XDL, 0x00, 0x1000);
    vbxe_xdl_hr(VR_SCREEN0, VB_H, 0, OVATT_WIDTH_NORMAL);
    antic_suspend();                /* DOS's text screen off the bus: antic.h */
    vdev = vdev_vbxe;               /* the conformance runner is about the VBXE device, and says so */
    vdi_font_default();         /* the linked 8x8 into VRAM */
    vdi_init();
    /* No pointing device: the harness IS the pointer.  It writes ptr_state
     * directly (position and buttons), and PTR_NONE keeps ptr_poll() from
     * overwriting that with a POT or joystick read.  v_locator still warps. */
    ptr_init(PTR_NONE, VB_W / 2, VB_H / 2);

    /* Discover linear RAM above bank $00.  Reported at STATUS[16..23] so the
     * harness can check what was actually found on this machine. */
    farmem_probe();
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
    STATUS[16] = farmem.kind;
    STATUS[17] = farmem.first_bank;
    STATUS[18] = farmem.last_bank;
    STATUS[19] = farmem.banks;
    STATUS[20] = (unsigned char)(farmem.bytes >> 16);
    STATUS[21] = (unsigned char)(farmem.bytes >> 24);
    {   /* prove it is really usable: a round trip near the top of the range */
        uint32_t a = far_alloc(4096);
        unsigned char ok = 0;
        if (a) {
            far_write8(a, 0xC3);
            far_write8(a + 4095, 0x3C);
            ok = (unsigned char)((far_read8(a) == 0xC3) &&
                                 (far_read8(a + 4095) == 0x3C));
        }
        STATUS[22] = ok;
        STATUS[23] = (unsigned char)(a >> 16);
    }
    gemdos_init();              /* its far state below any application's */
    /* The system's own two files, as GEM.COM reads them at start-up
     * (src/aes/lang.c): LANG.RSC for what it says, SYSTEM.FNT for the
     * character set it says it in.  Here as well as in the gsx_start op,
     * because a pure VDI script never reaches that one -- test-m21 is
     * exactly such a script. */
    lang_init();
    lang_font();

    /* Which bank is this code actually executing in?  src/farload.s copies it
     * up at load time and nothing else can confirm that it landed: the bridge
     * reports a 16-bit PC and no K register. */
    STATUS[24] = (unsigned char)_fl_running_bank();

    /* Start from a known screen: pen 0 (white), as a GEM desktop would. */
    blit_fill(VR_SCREEN0, VB_STRIDE, VB_STRIDE, VB_H, 0x00);
    blit_run();

    STATUS[ST_VC_PERIOD] = vcount_period();
    STATUS[ST_STAGE] = 1;                       /* ready for scripts */

    for (;;) {
        /* Keys the harness injects between scripts must not be lost: POKEY
         * latches one, so keep draining it into the driver's queue.  Only
         * the keyboard -- moving the cursor here would change what a script
         * left on screen. */
        vdi_key_poll();
        if (STATUS[ST_GO]) {
            STATUS[ST_GO] = 0;
            STATUS[ST_DONE] = 0;
            STATUS[ST_VC_GO] = VCOUNT;
            run_script();
            STATUS[ST_VC_DONE] = VCOUNT;
            STATUS[ST_DONE] = 0xA5;
            if (exit_req) {
                /* The way back, in the reverse of the way in: interrupts
                 * off and the ROM in, the overlay off, the accelerator's
                 * windows written back and slow, then the CPU and the
                 * stack as DOS had them. */
                irq_remove();
                vbxe_off();
                antic_resume();
                rapidus_restore();
                _sys_exit();
            }
        }
    }
}
