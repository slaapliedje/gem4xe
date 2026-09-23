/* cpx.c -- a control panel extension, whole and commented.
 *
 *     make KIND=cpx APP=example/cpx.c        ->  cpx.g4a
 *
 * ...which you install as MINE.CPX beside GEM.COM, and the control panel
 * grows a page.  This is XCONTROL's shape: the HOST owns the window and
 * the event loop, the MODULE owns the dialog, and they meet at a vtable
 * the module publishes when it loads (include/cpx.h).
 *
 * A CPX IS A PROGRAM TOO, but you do not write its main() -- lib/cpxmain.c
 * does.  It is linked in for you: it reads the slot address the AES put
 * in the command tail, calls YOUR cpx_init(), publishes what you return,
 * and ends with Ptermres so the module stays.  You write cpx_init() and
 * the entries it hands back.
 *
 * TWO KINDS, and cpx_call decides which you are by what it leaves in
 * pb->ret:
 *
 *     0   a FORM CPX.  You ran your own form_do and you are finished.
 *         This file is one.
 *     1   an EVENT CPX.  You drew yourself and the panel now feeds you
 *         events -- cpx_key, cpx_button, cpx_timer, cpx_draw -- until
 *         you set pb->quit.
 *
 * EVERY ENTRY TAKES ONE uint32_t, and that is the compiler's rule, not a
 * taste.  A cross-module entry must be SAVEDS so it sets up its own
 * direct page and data bank; this compiler emits that switch BEFORE the
 * body reads an argument the caller left in the CALLER's direct page, so
 * a second argument of any kind -- or a first one that is a pointer --
 * arrives as garbage, with nothing refused and nothing warned.  One
 * uint32_t, cast inside.  include/cpx.h has the measurements.
 *
 * YOUR SIXTY-FOUR BYTES.  The AES keeps a buffer per module and hands
 * you its address in xcpb->buffer.  Write what you like into it and call
 * CPX_Save, and the AES writes it to <YOURNAME>.CFG beside the module;
 * next boot it is laid back over whatever you wrote at cpx_init time.
 * Set CPX_BOOTINIT in your flags and the panel will open you once at
 * start-up, with xcpb->booting true, so you can apply it before anybody
 * sees the desk -- and you should draw nothing on that pass.
 */
#include "cpx.h"

#define MY_MARK  0x4B          /* "these 64 bytes are mine and are set" */

static WORD my_opens;          /* how many times this module was opened */
static OBJECT my_tree[3];
static const char my_msg[] = " An extension, opened by the panel ";
static const char my_ok[] = "  OK  ";

/* ---- the dialog ------------------------------------------------------
 *
 * Built object by object rather than loaded from a .RSC, so that this
 * example is one file.  A real module would rsrc_load() its own resource
 * at cpx_init time and keep it: a module is loaded before the first
 * program, and anything allocated afterwards is freed underneath it.
 *
 * THERE IS NO WORKSTATION HERE.  A CPX draws through the AES's, which is
 * what objc_draw and form_do already use, so there is no v_opnvwk. */
static void my_build(const GRECT *r)
{
    my_tree[0].ob_next = NIL;
    my_tree[0].ob_head = 1;
    my_tree[0].ob_tail = 2;
    my_tree[0].ob_type = G_BOX;
    my_tree[0].ob_flags = NONE;
    my_tree[0].ob_state = OUTLINED;
    my_tree[0].ob_spec.index = 0x00021100L;
    my_tree[0].ob_x = r->g_x;
    my_tree[0].ob_y = r->g_y;
    my_tree[0].ob_width = r->g_w;
    my_tree[0].ob_height = r->g_h;

    my_tree[1].ob_next = 2;
    my_tree[1].ob_head = my_tree[1].ob_tail = NIL;
    my_tree[1].ob_type = G_STRING;
    my_tree[1].ob_flags = NONE;
    my_tree[1].ob_state = NORMAL;
    my_tree[1].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)my_msg;
    my_tree[1].ob_x = 8;
    my_tree[1].ob_y = 16;
    my_tree[1].ob_width = (WORD)((sizeof my_msg - 1) * 8);
    my_tree[1].ob_height = 8;

    my_tree[2].ob_next = ROOT;
    my_tree[2].ob_head = my_tree[2].ob_tail = NIL;
    my_tree[2].ob_type = G_BUTTON;
    my_tree[2].ob_flags = SELECTABLE | DEFAULT | EXIT | LASTOB;
    my_tree[2].ob_state = NORMAL;
    my_tree[2].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)my_ok;
    my_tree[2].ob_x = (WORD)(r->g_w / 2 - 24);
    my_tree[2].ob_y = (WORD)(r->g_h - 32);
    my_tree[2].ob_width = 48;
    my_tree[2].ob_height = 16;
}

/* ---- the one entry this module needs --------------------------------- */

static SAVEDS void my_cpx_call(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
    XCPB FAR *x = (XCPB FAR *)pb->xcpb;
    uint8_t FAR *buf = (uint8_t FAR *)x->buffer;

    my_opens++;

    /* THE BOOT PASS.  The panel opens a CPX_BOOTINIT module once at
     * start-up so it can put its settings back.  Nobody is looking at
     * the screen yet, so apply and return -- do not draw. */
    if (x->booting) {
        pb->ret = 0;
        return;
    }

    /* pb->rect is the panel's work area, in screen coordinates: draw
     * inside it and nowhere else. */
    my_build(&pb->rect);
    objc_draw(my_tree, ROOT, MAX_DEPTH,
              pb->rect.g_x, pb->rect.g_y, pb->rect.g_w, pb->rect.g_h);
    form_do(my_tree, 0);

    /* Keep the count across a reboot.  The buffer is the AES's; CPX_Save
     * writes it to a file named after this module, so two modules can
     * never argue over one file -- you never learn your own name. */
    buf[0] = MY_MARK;
    buf[1] = (uint8_t)my_opens;
    if (x->CPX_Save) {
        x->CPX_Save(pb->xcpb);
        /* x->ok is 1 if it went.  A module that cares says so with
         * XGen_Alert(XAL_FILE_ERR) rather than a sentence of its own. */
    }

    pb->ret = 0;                /* a FORM CPX: I am finished */
}

static CPXINFO my_info = {
    my_cpx_call,                /* cpx_call   -- the only one required */
    0,                          /* cpx_draw   -- event CPXs need this */
    0, 0, 0, 0, 0, 0, 0, 0      /* wmove, timer, key, button, m1, m2,
                                 * hook, close: 0 is allowed, and the
                                 * host checks before every call */
};

/* ---- what the AES calls when the module loads ------------------------
 *
 * Fill in the header -- your title, your id, your flags -- and return
 * the vtable.  Return 0 to decline, and the AES will count you as
 * refused rather than load you.
 *
 * THIS RUNS THROUGH YOUR OWN crt, so your initialised data really is
 * installed by the time you get here.  (That is worth knowing because
 * the failure is silent: a module entered around its crt has garbage
 * globals and nothing says so.) */
CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr)
{
    static const char title[] = "Example";
    const uint8_t FAR *buf = (const uint8_t FAR *)pb->buffer;
    WORD i;

    hdr->magic = CPX_MAGIC;
    hdr->flags = CPX_BOOTINIT;      /* open me once at boot */
    hdr->cpx_id = 0x4D494E45L;      /* 'MINE' -- yours to choose */
    hdr->cpx_version = 1;

    /* The title the panel lists, and the shorter one under an icon. */
    for (i = 0; title[i] && i < 17; i++)
        hdr->title_txt[i] = title[i];
    hdr->title_txt[i] = 0;
    for (i = 0; title[i] && i < 13; i++)
        hdr->i_text[i] = title[i];
    hdr->i_text[i] = 0;

    /* Whatever was saved last time is already in the buffer IF the AES
     * found the file -- check your own mark before believing it, because
     * an absent file leaves the bytes as you wrote them here. */
    if (buf[0] == MY_MARK)
        my_opens = buf[1];

    return &my_info;
}
