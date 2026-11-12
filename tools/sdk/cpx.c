/* SPDX-License-Identifier: 0BSD
 *
 * Copyright (C) 2026 Slaapliedje
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * An example: start your own program from a copy of it, under any terms.
 */
/* cpx.c -- a control panel extension, whole and commented.
 *
 *     make KIND=cpx APP=example/cpx.c        ->  cpx.cpx
 *
 * ...which you install as MINE.CPX in \GEM\, and the control panel lists
 * one more module.  This is XCONTROL's shape: the HOST owns the window
 * and the event loop, the MODULE owns the dialog, and they meet at a
 * vtable the module publishes when it loads (include/cpx.h).
 *
 * THE HEADER IS NOT IN HERE.  Your title, the text under your icon, the
 * icon, your id, version and flags are in example/cpx.cpxh, a text file
 * beside this one; tools/mkcpx.py puts them in front of the module, as
 * the 512 bytes the panel lists you from without running you.  Copy
 * cpx.cpxh beside your own source and edit it.
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
 * next boot it is laid over the buffer cpx.cpxh started you with.  Put
 * `bootinit` in cpx.cpxh's flags and the panel will open you once at
 * start-up, with xcpb->booting true, so you can apply it before anybody
 * sees the desk -- and you should draw nothing on that pass.
 */
#include "cpx.h"

#define MY_MARK  0x4B          /* "these 64 bytes are mine and are set" */

static WORD my_opens;          /* how many times this module was opened */
static OBJECT my_tree[3];
static const char my_msg[] = " Opened by the panel ";   /* the work
                                                         * area is 32 cells */
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
    uint8_t FAR *buf;
    WORD msg[8], ret;

    pb->ret = 0;                /* a FORM CPX: finished when this returns */
    /* THE PANEL'S BLOCK ARRIVES HERE, not at cpx_init: at boot the AES
     * loads a module before there is a panel, and cpx_init's is 0 then.
     * Whatever was saved last time is in the buffer IF the AES found the
     * file -- check your own mark before believing it. */
    if (!x || !x->buffer)
        return;
    buf = (uint8_t FAR *)x->buffer;
    if (buf[0] == MY_MARK && !my_opens)
        my_opens = buf[1];
    my_opens++;

    /* THE BOOT PASS.  The panel opens a `bootinit` module once at
     * start-up so it can put its settings back.  Nobody is looking at
     * the screen yet, so apply and return -- do not draw. */
    if (x->booting)
        return;

    /* IN THE PANEL'S WINDOW, through its Xform_do, as XControl's: place
     * the tree at the work area the panel cleared, draw it, and let the
     * panel run it -- it answers redraws and moves the tree's root with
     * the window meanwhile.  A panel without one has nowhere to put it. */
    if (!x->Xform_do)
        return;
    my_build(&pb->rect);
    objc_draw(my_tree, ROOT, MAX_DEPTH,
              pb->rect.g_x, pb->rect.g_y, pb->rect.g_w, pb->rect.g_h);
    for (;;) {
        ret = cpx_xform_do(x, my_tree, 0, msg);
        /* -1 is a message: WM_CLOSED (the closer, which keeps what was
         * set, as OK does) or AC_CLOSE (the window is gone).  Anything
         * else -1 brings -- CT_KEY, a key with no character -- is not
         * this form's, and it goes on. */
        if (ret == -1 && (msg[0] == WM_CLOSED || msg[0] == AC_CLOSE))
            break;
        if (ret != -1)
            break;              /* the one exit object, OK */
    }

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
 * Return the vtable, or 0 to decline, and the AES will count you as
 * refused rather than load you.  Your header is not your business here:
 * it is cpx.cpxh's, in front of the module.
 *
 * `pb` IS THE PANEL'S BLOCK when the panel loads you to open you, and 0
 * when the AES loads you at boot -- so a module that reads it here checks
 * it first.  This one takes the block at cpx_call instead.
 *
 * THIS RUNS THROUGH YOUR OWN crt, so your initialised data really is
 * installed by the time you get here.  (That is worth knowing because
 * the failure is silent: a module entered around its crt has garbage
 * globals and nothing says so.) */
CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb)
{
    (void)pb;
    return &my_info;
}
