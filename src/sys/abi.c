/* abi.c -- the application binary interface: what a COP does.
 *
 * gem_entry() is the DRI entry shim.  The 1984 screen driver's handlers are
 * argument-free and read fixed CONTRL/INTIN/PTSIN arrays; the shim copies
 * the caller's arrays in before dispatch and its results back after
 * (vdi/entry.a86 in the GEM/3 tree; EmuTOS's aes/gemsuper.c xif() does the
 * same for the AES).  gem4xe keeps that discipline for the reason it was
 * invented: the caller's arrays can then be anywhere -- here, anywhere in
 * the 16 MB -- and the handlers never learn.
 *
 * VDI (COP #$56): contrl[0..11], intin[0..contrl[3]-1] and
 * ptsin[0..2*contrl[1]-1] come in; contrl, intout[0..contrl[4]-1] and
 * ptsout[0..2*contrl[2]-1] go back.  The counts are capped at gem4xe's
 * array sizes, never at the caller's: a caller declares the sizes it
 * built, as on the ST.
 *
 * AES (COP #$41): control[0..4], int_in[0..control[1]-1] and
 * addr_in[0..control[3]-1] come in, int_out[0..control[2]-1] goes back, and
 * global is written on appl_init.  The dispatch is EmuTOS's crysbind()
 * shape with the same int_in/addr_in packing (include/aesdefs.h there):
 * that packing IS the AES binding contract, and the one an application
 * built for GEM expects.  int_out[0] is the return value, 1 for a call that
 * has none -- crysbind's `ret = TRUE` default -- and -1 for an opcode
 * gem4xe does not have.
 *
 * Trees and forms an application passes by address must be in bank $00 --
 * the AES addresses them near, as the small data model does -- so the
 * loader gives an application a bank-$00 pool (src/sys/app.c), and a far
 * tree or form is refused and counted in gem_bad rather than truncated to
 * garbage.  A STRING is the exception the near budget allows: a
 * --data-model=large program keeps its every string literal in far memory
 * (Calypsi cfar), so near_str() copies a SHORT far string into a near
 * scratch before the AES sees it -- enough for a resource name, a menu
 * label, an alert (form_alert, rsrc_load, menu_text, menu_register) and
 * fsel's dialog title.  The strings that could be longer or come in pairs
 * -- fsel's path and selection, shel_write's, shel_find's -- still want a
 * near buffer, until a bigger scratch can be afforded.  Message buffers and the parameter block's own arrays are
 * written through far pointers and can be anywhere.
 *
 * GEMDOS (COP #$44): the block is the ST's trap #1 frame with the result
 * in front of it (src/sys/gemdos.h); gemdos_call() reads its arguments
 * through far pointers and writes the result back, so nothing is copied
 * here.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "aes/aes.h"
#include "aes/proc.h"
#include "sys/abi.h"
#include "sys/cio.h"
#include "sys/gemdos.h"
#include "sys/farmem.h"
#include "sys/app.h"

uint32_t gem_pb;
uint8_t  gem_which;
uint16_t gem_api_sp;
uint8_t  gem_depth;
uint16_t gem_calls;
uint16_t app_calls;             /* of those, the application's: see abi.h */
uint16_t gem_bad;
uint8_t  gem_cop_pass;
uint8_t  gem_term;

/* Whether the OS takes COPs of its own.  Rapidus OS -- drac030's 65C816 XL
 * OS -- has an "@:" device whose one file, SYSDEF, describes the system
 * (its specification, "The @: device"): byte 10 is the CPU, 2 for a
 * 65C816, and bit 0 of byte 13 says the native interrupt services are
 * there, which is its COP handler and the RAM vectors behind it.  Any
 * other OS has no @: device, the open fails, and a COP that is not
 * gem4xe's has nobody to go to. */
#define SYSDEF_CPU     10
#define SYSDEF_NATIVE  13
#define CPU_65C816     2

void abi_probe_os(void)
{
    uint8_t def[SYSDEF_NATIVE + 1];
    uint16_t got = 0;
    uint8_t st;
    int16_t n;

    gem_cop_pass = 0;
    n = cio_open("@:SYSDEF", 4, 0);     /* 4: read */
    if (n < 0)
        return;
    st = cio_read(n, def, sizeof def, &got);
    cio_close(n);
    if ((st == CIO_OK || st == CIO_OK_EOF) && got == sizeof def &&
        def[SYSDEF_CPU] == CPU_65C816 && (def[SYSDEF_NATIVE] & 1))
        gem_cop_pass = 1;
}

/* The parameter blocks as they lie in the caller's memory: 32-bit
 * addresses, the ST's layout (src/app/gem.h). */
typedef struct {
    uint32_t contrl, intin, ptsin, intout, ptsout;
} VDIPB_IMG;

typedef struct {
    uint32_t control, global, int_in, int_out, addr_in, addr_out;
} AESPB_IMG;

/* EmuTOS's crysbind sizes (aes/funcdef.h): what an AES call can carry. */
#define C_SIZE  5
#define I_SIZE  16
#define O_SIZE  7
#define AI_SIZE 3

/* AES_VERSION 0x0140 is AES 1.40, TOS 1.04's, which is what EmuTOS reports
 * when built with none of the later extensions (menu popups, 3D objects,
 * window colours) -- gem4xe has none of them either, and the number is a
 * promise about which functions exist. */
#define AES_VERSION 0x0140

/* ---- VDI ---------------------------------------------------------------- */

static void vdi_entry(const VDIPB_IMG FAR *pb)
{
    WORD FAR *c  = (WORD FAR *)pb->contrl;
    WORD FAR *ii = (WORD FAR *)pb->intin;
    WORD FAR *pi = (WORD FAR *)pb->ptsin;
    WORD FAR *io = (WORD FAR *)pb->intout;
    WORD FAR *po = (WORD FAR *)pb->ptsout;
    WORD k, n;

    for (k = 0; k < CONTRL_SIZE; k++)
        contrl[k] = c[k];
    n = contrl[3];
    if (n > INTIN_SIZE)
        n = INTIN_SIZE;
    for (k = 0; k < n; k++)
        intin[k] = ii[k];
    n = (WORD)(contrl[1] * 2);
    if (n > PTSIN_SIZE)
        n = PTSIN_SIZE;
    for (k = 0; k < n; k++)
        ptsin[k] = pi[k];

    vdi();

    for (k = 0; k < CONTRL_SIZE; k++)
        c[k] = contrl[k];
    n = contrl[4];
    if (n > INTOUT_SIZE)
        n = INTOUT_SIZE;
    for (k = 0; k < n; k++)
        io[k] = intout[k];
    n = (WORD)(contrl[2] * 2);
    if (n > PTSOUT_SIZE)
        n = PTSOUT_SIZE;
    for (k = 0; k < n; k++)
        po[k] = ptsout[k];
}

/* ---- AES ---------------------------------------------------------------- */

/* A near address the caller passed as a int32_t: bank $00 or nothing. */
static void *near_of(int32_t a)
{
    if ((uint32_t)a >> 16) {
        gem_bad++;
        return 0;
    }
    return (void *)(uint16_t)a;
}

/* A caller STRING (int32_t) as a near pointer.  In a --data-model=large
 * program every string literal is FAR (Calypsi cfar), and the AES reads
 * strings near, so near_of() would hand it NULL and the call would do
 * nothing -- form_alert draws blank, rsrc_load opens no file, menu_text
 * writes no item.  Copy a far string into a near scratch instead, the same
 * copy-in the parameter blocks get (see the file head); a near string is
 * returned as itself, so nothing changes for a small-data program.
 *
 * The scratch is SMALL because bank $00 is nearly spent (tools/memreport.py):
 * a big buffer fits neither the near budget (as a static) nor gem4xe's 2 KB
 * stack across a deep AES call (as a local -- objc_draw overran it, m17).
 * So a far string is capped at STR_SCRATCH-1, which covers a resource name,
 * a menu label and the alerts a program actually raises.  The opcodes that
 * take a longer or a second string -- fsel, shel_write, shel_find -- still
 * want a near one; a bigger scratch (a bank-$00 map rebalance) is the
 * follow-up that would carry them.  str_used winds back to 0 each call. */
#define STR_SCRATCH 64
static char str_scratch[STR_SCRATCH];
static uint16_t str_used;

static char *near_str(int32_t a)
{
    uint16_t start;

    if (!((uint32_t)a >> 16))
        return (char *)(uint16_t)a;         /* near, or NULL */
    start = str_used;
    while (str_used < STR_SCRATCH - 1) {
        uint8_t c = far_read8((uint32_t)a++);
        str_scratch[str_used++] = (char)c;
        if (!c)
            return &str_scratch[start];
    }
    str_scratch[STR_SCRATCH - 1] = 0;        /* truncate, keep a terminator */
    return &str_scratch[start < STR_SCRATCH - 1 ? start : STR_SCRATCH - 1];
}

/* THE SAME BOUNCE FOR A STRING THAT WILL NOT FIT IN SIXTY-FOUR BYTES.
 * An alert is five lines and three buttons -- a couple of hundred bytes,
 * and RetroWP alone calls form_alert from fifty-one places.  The scratch
 * above cannot grow to meet that: it is permanently resident in bank $00,
 * which has hundreds of bytes free in total.  It does not have to.
 * fm_alert already takes the AES's POOL for its icon and its BITBLK, and
 * the pool is exactly the right home for a copy this size: near, because
 * fm_strbrk points the tree's ob_spec INTO the string; lasting the whole
 * call, because the tree is drawn from those pointers; and gone at the
 * end of it, because the caller winds the pool back to its mark.  512
 * bytes is the ceiling, which is longer than an alert a screen can hold. */
#define POOL_STR_MAX 512

static const char *pool_str(int32_t a)
{
    uint32_t p = (uint32_t)a;
    uint16_t n = 0;
    char *dst;

    if (!(p >> 16))
        return (const char *)(uint16_t)p;       /* near, or NULL */
    while (n < POOL_STR_MAX - 1 && far_read8(p + n))
        n++;
    dst = pool_alloc((uint16_t)(n + 1), 1);
    if (dst)
        far_get((uint8_t *)dst, p, (uint16_t)(n + 1));
    return dst;
}

/* rsrc_gaddr's answer, for aes_entry to copy to addr_out[0] -- the one
 * AES call that returns an address (the donor's ad_rso). */
static uint32_t ad_rso;

static WORD crysbind(WORD opcode, WORD FAR *global, const WORD *int_in,
                     WORD *int_out, const int32_t *addr_in)
{
    OBJECT FAR *tree = 0;
    GRECT clip;
    WORD ret = 1;                   /* TRUE unless the call says otherwise */
    WORD k;

    str_used = 0;                   /* one call's far-string bounces */

    /* Every op that takes a tree takes it in addr_in[0]. */
    switch (opcode) {
    case 30: case 31: case 32: case 33: case 34:
    case 40: case 41:
    case 42: case 43: case 44: case 45: case 46: case 47:
    case 50: case 54: case 55: case 56:
    case 75:
    case 114:
        tree = (OBJECT FAR *)(uint32_t)addr_in[0];    /* any bank: see docs/far-trees.md */
        if (!tree)
            return -1;
        break;
    default:
        break;
    }

    switch (opcode) {
    /* Application manager */
    case 10:                        /* appl_init */
        global[0] = AES_VERSION;
        global[1] = 1;              /* concurrent applications */
        global[2] = 0;              /* ap_id: the one application */
        for (k = 3; k < 15; k++)
            global[k] = 0;
        global[10] = gl_nplanes;
        ret = proc_pid(rlr);        /* ap_id */
        break;
    case 12:                        /* appl_write: id, len, buffer */
        {
            const WORD FAR *m = (const WORD FAR *)addr_in[0];
            WORD msg[8];
            for (k = 0; k < 8; k++)
                msg[k] = m[k];
            /* The destination was read and thrown away while there was
             * one process; it is honoured now, and word 1 says who sent
             * it -- which for appl_write is the only place in gem4xe
             * where a real sender exists. */
            msg[1] = proc_pid(rlr);
            mq_put(proc_of(int_in[0]), msg);
        }
        break;
    case 19:                        /* appl_exit */
        break;

    /* Event manager */
    case 20:                        /* evnt_keybd */
        ret = ev_keybd();
        break;
    case 21:                        /* evnt_button: clicks, mask, state */
        ret = ev_button(int_in[0], (UWORD)int_in[1], (UWORD)int_in[2],
                        &int_out[1]);
        break;
    case 22:                        /* evnt_mouse: MOBLK */
        ev_mouse((const MOBLK *)&int_in[0], &int_out[1]);
        break;
    case 23: {                      /* evnt_mesag: buffer */
        WORD FAR *m = (WORD FAR *)addr_in[0];
        WORD msg[8];
        ev_mesag(msg);
        for (k = 0; k < 8; k++)
            m[k] = msg[k];
        break;
    }
    case 24:                        /* evnt_timer: lo, hi */
        ev_timer((uint32_t)(uint16_t)int_in[0]
                 | ((uint32_t)(uint16_t)int_in[1] << 16));
        break;
    case 25: {                      /* evnt_multi */
        WORD FAR *m = (WORD FAR *)addr_in[0];
        WORD msg[8] = {0, 0, 0, 0, 0, 0, 0, 0};
        uint32_t ms = 0;
        if (int_in[0] & MU_TIMER)
            ms = (uint32_t)(uint16_t)int_in[14]
               | ((uint32_t)(uint16_t)int_in[15] << 16);
        ret = ev_multi(int_in[0], (const MOBLK *)&int_in[4],
                       (const MOBLK *)&int_in[9], ms,
                       combine_cms(int_in[1], (UWORD)int_in[2],
                                   (UWORD)int_in[3]),
                       msg, &int_out[1]);
        if (ret & MU_MESAG)
            for (k = 0; k < 8; k++)
                m[k] = msg[k];
        break;
    }
    case 26:                        /* evnt_dclick: rate, setit */
        ret = ev_dclick(int_in[0], int_in[1]);
        break;

    /* Menu manager */
    case 30:                        /* menu_bar: tree, showit */
        mn_bar(tree, int_in[0]);
        break;
    case 31:                        /* menu_icheck: tree, item, check */
        ret = do_chg(tree, int_in[0], CHECKED, int_in[1], FALSE, FALSE);
        break;
    case 32:                        /* menu_ienable: tree, item, enable */
        ret = do_chg(tree, int_in[0] & 0x7fff, DISABLED, !int_in[1],
                     (int_in[0] & 0x8000) != 0, FALSE);
        break;
    case 33:                        /* menu_tnormal: tree, title, normal */
        ret = do_chg(tree, int_in[0], SELECTED, !int_in[1], TRUE, TRUE);
        break;
    case 34: {                      /* menu_text: tree, item, text */
        const char *s = (const char *)near_str(addr_in[1]);
        if (!s)
            return -1;
        mn_text(tree, int_in[0], s);
        break;
    }
    case 35: {                      /* menu_register: pid, string */
        const char *s = (const char *)near_str(addr_in[0]);
        if (!s)
            return -1;
        ret = mn_register(int_in[0], s);
        break;
    }

    /* Object manager.  objc_add and objc_delete are the tree surgery the
     * window manager already does to its own tree (src/aes/objc.c): an
     * application that builds or edits a tree at run time needs them, and
     * the desktop wanted them badly enough to keep a private copy. */
    case 40:                        /* objc_add: parent, child */
        ob_add(tree, int_in[0], int_in[1]);
        break;
    case 41:                        /* objc_delete: obj */
        ret = ob_delete(tree, int_in[0]);
        break;
    case 42:                        /* objc_draw: start, depth, clip */
        clip.g_x = int_in[2]; clip.g_y = int_in[3];
        clip.g_w = int_in[4]; clip.g_h = int_in[5];
        objc_draw(tree, int_in[0], int_in[1], &clip);
        break;
    case 43:                        /* objc_find: start, depth, mx, my */
        ret = objc_find(tree, int_in[0], int_in[1], int_in[2], int_in[3]);
        break;
    case 44:                        /* objc_offset: obj */
        objc_offset(tree, int_in[0], &int_out[1], &int_out[2]);
        break;
    case 45:                        /* objc_order: obj, newpos */
        ret = ob_order(tree, int_in[0], int_in[1]);
        break;
    case 46: {                      /* objc_edit: obj, char, idx, kind */
        WORD idx = int_in[2];
        gsx_sclip(&gl_rfull);
        ret = objc_edit(tree, int_in[0], int_in[1], &idx, int_in[3]);
        int_out[1] = idx;
        break;
    }
    case 47:                        /* objc_change: obj, -, clip, state, redraw */
        clip.g_x = int_in[2]; clip.g_y = int_in[3];
        clip.g_w = int_in[4]; clip.g_h = int_in[5];
        objc_change(tree, int_in[0], &clip, (UWORD)int_in[6], int_in[7]);
        break;
    /* objc_sysvar takes NO TREE, which is why it is not in the list at the
     * top of this function that fetches addr_in[0]: its four words are the
     * whole of its input (Compendium 6.121, and the AES's own binding table
     * gives it as 48, 4 in, 3 out, 0 addresses). */
    case 48:                        /* objc_sysvar: mode, which, in1, in2 */
        ret = ob_sysvar(int_in[0], int_in[1], int_in[2], int_in[3],
                        &int_out[1], &int_out[2]);
        break;

    /* Form manager */
    case 50:                        /* form_do: start */
        ret = form_do(tree, int_in[0]);
        break;
    case 51: {                      /* form_dial: type, pi, pt */
        GRECT pi, pt;
        pi.g_x = int_in[1]; pi.g_y = int_in[2];
        pi.g_w = int_in[3]; pi.g_h = int_in[4];
        pt.g_x = int_in[5]; pt.g_y = int_in[6];
        pt.g_w = int_in[7]; pt.g_h = int_in[8];
        ret = form_dial(int_in[0], &pi, &pt);
        break;
    }
    case 52: {                      /* form_alert: defbut, string */
        uint16_t mark = pool_mark();
        const char *s = pool_str(addr_in[0]);
        if (!s) {
            pool_release(mark);
            return -1;
        }
        ret = fm_alert(int_in[0], s);
        pool_release(mark);
        break;
    }
    case 53:                        /* form_error: number */
        ret = fm_error(int_in[0]);
        break;
    case 54:                        /* form_center */
        ob_center(tree, &clip);
        int_out[1] = clip.g_x; int_out[2] = clip.g_y;
        int_out[3] = clip.g_w; int_out[4] = clip.g_h;
        break;
    case 55: {                      /* form_keybd: obj, char, nxtob */
        WORD ch = int_in[1], nxt = int_in[2];
        gsx_sclip(&gl_rfull);
        ret = form_keybd(tree, int_in[0], &ch, &nxt);
        int_out[1] = nxt;
        int_out[2] = ch;
        break;
    }
    case 56: {                      /* form_button: obj, clks */
        WORD nxt = 0;
        gsx_sclip(&gl_rfull);
        ret = form_button(tree, int_in[0], int_in[1], &nxt);
        int_out[1] = nxt;
        break;
    }

    /* Graphics manager */
    case 70:                        /* graf_rubbox */
        gr_rubbox(int_in[0], int_in[1], int_in[2], int_in[3],
                  &int_out[1], &int_out[2]);
        break;
    case 71: {                      /* graf_dragbox */
        GRECT pc;
        pc.g_x = int_in[4]; pc.g_y = int_in[5];
        pc.g_w = int_in[6]; pc.g_h = int_in[7];
        gr_dragbox(int_in[0], int_in[1], int_in[2], int_in[3], &pc,
                   &int_out[1], &int_out[2]);
        break;
    }
    case 73:                        /* graf_growbox */
    case 74: {                      /* graf_shrinkbox */
        GRECT pi, pt;
        pi.g_x = int_in[0]; pi.g_y = int_in[1];
        pi.g_w = int_in[2]; pi.g_h = int_in[3];
        pt.g_x = int_in[4]; pt.g_y = int_in[5];
        pt.g_w = int_in[6]; pt.g_h = int_in[7];
        if (opcode == 73)
            gr_growbox(&pi, &pt);
        else
            gr_shrinkbox(&pi, &pt);
        break;
    }
    case 75:                        /* graf_watchbox: -, obj, in, out */
        ret = gr_watchbox(tree, int_in[1], int_in[2], int_in[3]);
        break;
    case 77:                        /* graf_handle */
        int_out[1] = gl_wchar;
        int_out[2] = gl_hchar;
        int_out[3] = gl_wbox;
        int_out[4] = gl_hbox;
        ret = gl_handle;
        break;
    case 78: {                      /* graf_mouse: mode, form */
        const WORD *form = 0;
        if (int_in[0] == USER_DEF) {
            form = (const WORD *)near_of(addr_in[0]);
            if (!form)
                return -1;
        }
        gr_mouse(int_in[0], form);
        break;
    }
    case 79:                        /* graf_mkstate */
        gr_mkstate(&int_out[1], &int_out[2], &int_out[3], &int_out[4]);
        break;

    /* Scrap manager.  Both directions want the caller's own memory: one
     * writes a path into it and the other reads a path out of it, and a
     * path can be longer than near_str's 63-byte scratch, so the bounce
     * that serves form_alert is no use here.  A far pointer is refused,
     * as shel_find's and shel_read's are (src/app/gem.h). */
    case 80: {                      /* scrp_read: the path, out */
        char *p = near_of(addr_in[0]);
        ret = p ? sc_read(p) : 0;
        break;
    }
    case 81: {                      /* scrp_write: the path, in */
        const char *p = near_of(addr_in[0]);
        ret = p ? sc_write(p) : 0;
        break;
    }

    /* Window manager */
    case 100:                       /* wind_create: kind, rect */
        clip.g_x = int_in[1]; clip.g_y = int_in[2];
        clip.g_w = int_in[3]; clip.g_h = int_in[4];
        ret = wm_create(int_in[0], &clip);
        break;
    case 101:                       /* wind_open: handle, rect */
        clip.g_x = int_in[1]; clip.g_y = int_in[2];
        clip.g_w = int_in[3]; clip.g_h = int_in[4];
        ret = wm_open(int_in[0], &clip);
        break;
    case 102:                       /* wind_close */
        ret = wm_close(int_in[0]);
        break;
    case 103:                       /* wind_delete */
        ret = wm_delete(int_in[0]);
        break;
    case 104:                       /* wind_get: handle, field */
        ret = wm_get(int_in[0], int_in[1], &int_out[1], &int_in[2]);
        break;
    case 105: {                     /* wind_set: handle, field, words */
        WORD w[4];
        for (k = 0; k < 4; k++)
            w[k] = int_in[2 + k];
        /* WF_NAME and WF_INFO pass a string's address, and it goes
         * through UNTOUCHED -- no near_of, no near_str.  The window
         * manager keeps all 24 bits of it and brings a far title down
         * into bank $00 at DRAW time (w_ptext, src/aes/wind.c), which is
         * the only place it can be done without breaking the ST's
         * contract: the AES re-reads the application's string at every
         * redraw, so a bounce that happened once here would freeze the
         * title at whatever it said during the call.  Until 2026-09-16
         * there was nowhere in bank $00 to put the two buffers that
         * needs; the LoRAM/Near boundary found them (src/gem4xe.scm). */
        ret = wm_set(int_in[0], int_in[1], w);
        break;
    }
    case 106:                       /* wind_find: x, y */
        ret = wm_find(int_in[0], int_in[1]);
        break;
    case 107:                       /* wind_update */
        wm_update(int_in[0]);
        break;
    case 108:                       /* wind_calc */
        wm_calc(int_in[0], (UWORD)int_in[1], int_in[2], int_in[3],
                int_in[4], int_in[5],
                &int_out[1], &int_out[2], &int_out[3], &int_out[4]);
        break;

    /* File selector: the path and name are the application's buffers,
     * the button its word. */
    case 90:                        /* fsel_input: path, sel */
    case 91: {                      /* fsel_exinput: path, sel, label */
        char *path = near_of(addr_in[0]);   /* the app's buffers, near */
        char *sel = near_of(addr_in[1]);
        /* the label is a title fs_input only reads, and a program's is a far
         * literal ("Open design", GACS main.c) -- the one fsel string that
         * is IN-only and short, so bounce it while path/sel stay near. */
        const char *label = (opcode == 91) ? near_str(addr_in[2]) : 0;
        if (path && sel && (opcode == 90 || label))
            ret = fs_input(path, sel, &int_out[1], label);
        else
            ret = 0;
        break;
    }

    /* Resource library.  The global's ap_ptree / ap_rscmem / ap_rsclen
     * (words 5-6, 7-8, 9) are what the donor's rs_load leaves there; the
     * addresses are bank $00, so the high words are 0. */
    case 110: {                     /* rsrc_load: name */
        const char *name = near_str(addr_in[0]);
        /* int_in[0] bit 0: the caller takes far addresses.  aes_entry
         * zeroes int_in and copies only control[1] of them, so a kit that
         * passes none -- the small-data one -- can never set this by
         * accident (docs/far-trees.md). */
        ret = name ? rs_load(name, (WORD)(int_in[0] & 1)) : 0;
        if (ret) {
            RSHDR h;
            uint32_t b = rs_loaded(), tr;
            rs_header(&h);
            tr = b + h.rsh_trindex;
            global[5] = (WORD)(tr & 0xFFFF);        /* ap_ptree */
            global[6] = (WORD)(tr >> 16);
            global[7] = (WORD)(b & 0xFFFF);         /* the header */
            global[8] = (WORD)(b >> 16);
            global[9] = (WORD)h.rsh_rssize;
        }
        break;
    }
    case 111:                       /* rsrc_free */
        ret = rs_free();
        for (k = 5; k < 10; k++)
            global[k] = 0;
        break;
    case 112:                       /* rsrc_gaddr: type, index -> addr_out */
        ret = rs_gaddr((UWORD)int_in[0], (UWORD)int_in[1], &ad_rso);
        break;
    case 113:                       /* rsrc_saddr: type, index, addr */
        ret = rs_saddr((UWORD)int_in[0], (UWORD)int_in[1], (uint32_t)addr_in[0]);
        break;
    case 114:                       /* rsrc_obfix: tree, object */
        rs_obfix(tree, int_in[0]);
        break;

    /* Shell library */
    case 120: {                     /* shel_read: cmd, tail */
        char *cmd = near_of(addr_in[0]);
        char *tail = near_of(addr_in[1]);
        if (cmd && tail)
            sh_read(cmd, tail);
        else
            ret = 0;
        break;
    }
    case 121: {                     /* shel_write: doex, isgr, iscr, cmd, tail */
        const char *cmd = near_of(addr_in[0]);   /* far: not yet */
        const char *tail = near_of(addr_in[1]);
        if (int_in[0] == 1 && !(cmd && tail))
            ret = 0;
        else
            ret = sh_write(int_in[0], int_in[1], int_in[2], cmd, tail);
        break;
    }
    case 122: {                     /* shel_get: buffer, len -- the buffer
                                     * may be far: the AES only copies bytes */
        uint32_t buf = (uint32_t)addr_in[0];
        if (buf)
            sh_get(buf, int_in[0]);
        else
            ret = 0;
        break;
    }
    case 123: {                     /* shel_put: data, len */
        uint32_t buf = (uint32_t)addr_in[0];
        if (buf)
            sh_put(buf, int_in[0]);
        else
            ret = 0;
        break;
    }
    case 124: {                     /* shel_find: path (unchanged here) */
        char *path = near_of(addr_in[0]);   /* far: not yet */
        ret = path ? sh_find(path) : 0;
        break;
    }
    case 125: {                     /* shel_envrn: &value, name */
        const char **pp = near_of(addr_in[0]);
        const char *name = near_str(addr_in[1]);
        if (pp && name)
            sh_envrn(pp, name);
        else
            ret = 0;
        break;
    }

    default:
        gem_bad++;
        ret = -1;
        break;
    }
    return ret;
}

static void aes_entry(const AESPB_IMG FAR *pb)
{
    const WORD FAR *ctl = (const WORD FAR *)pb->control;
    const WORD FAR *ii  = (const WORD FAR *)pb->int_in;
    const int32_t FAR *ai  = (const int32_t FAR *)pb->addr_in;
    WORD FAR *io = (WORD FAR *)pb->int_out;
    WORD control[C_SIZE];
    WORD int_in[I_SIZE];
    WORD int_out[O_SIZE];
    int32_t addr_in[AI_SIZE];
    WORD k, n;

    for (k = 0; k < C_SIZE; k++)
        control[k] = ctl[k];
    for (k = 0; k < I_SIZE; k++)
        int_in[k] = 0;
    for (k = 0; k < O_SIZE; k++)
        int_out[k] = 0;
    for (k = 0; k < AI_SIZE; k++)
        addr_in[k] = 0;
    n = control[1];
    if (n > I_SIZE)
        n = I_SIZE;
    for (k = 0; k < n; k++)
        int_in[k] = ii[k];
    n = control[3];
    if (n > AI_SIZE)
        n = AI_SIZE;
    for (k = 0; k < n; k++)
        addr_in[k] = ai[k];

    int_out[0] = crysbind(control[0], (WORD FAR *)pb->global,
                          int_in, int_out, addr_in);

    n = control[2];
    if (n > O_SIZE)
        n = O_SIZE;
    for (k = 0; k < n; k++)
        io[k] = int_out[k];
    if (control[0] == 112 && control[4] > 0)
        *(uint32_t FAR *)pb->addr_out = ad_rso;
}

/* ---- the entry ---------------------------------------------------------- */

void gem_entry(void)
{
    /* Only this call can end the program (abi.s reads the flag after it):
     * a GEMDOS call a milestone runner makes directly, not through a COP,
     * can leave it set, and it must not end the next program's first
     * call. */
    gem_term = 0;
    /* A COP that is nobody's here -- not one of the three, and no OS to
     * pass it to (abi.s) -- is refused and is not a call: counting it
     * would number an application's calls differently on a machine whose
     * OS takes that COP, where it never arrives here at all. */
    if (gem_which != ABI_VDI && gem_which != ABI_AES && gem_which != ABI_GEMDOS) {
        gem_bad++;
        return;
    }
    gem_calls++;
    /* ...and the application's own count, which is what a gate means when
     * it asks "which call is the desktop inside".  gem_calls counts every
     * process's, and the moment an accessory was resident that stopped
     * identifying anybody's progress: test-boot put the desktop five
     * calls past its first wait, which is exactly the accessory's
     * appl_init, rsrc_load, rsrc_gaddr, menu_register and evnt_mesag. */
    if (rlr == proc_app)
        app_calls++;
    switch (gem_which) {
    case ABI_VDI:
        vdi_entry((const VDIPB_IMG FAR *)gem_pb);
        break;
    case ABI_AES:
        aes_entry((const AESPB_IMG FAR *)gem_pb);
        break;
    case ABI_GEMDOS:
        gemdos_call(gem_pb);
        break;
    default:
        gem_bad++;
        break;
    }
}
