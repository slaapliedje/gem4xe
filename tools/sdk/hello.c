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
/* hello.c -- a gem4xe application, whole.
 *
 * Build it with the kit's Makefile:
 *
 *     make                     -> hello.g4a
 *     make APP=mine.c          -> mine.g4a
 *
 * A gem4xe application links against nothing of the system's.  It
 * reaches the VDI, the AES and GEMDOS through three call gates
 * (COP #$56, COP #$41, COP #$44), and gem.h declares every call each of
 * them serves.  The loader puts this program's near region -- direct
 * page, stack, data -- in gem4xe's bank-$00 pool and its code in a bank
 * of far memory, and calls main(); main's return value is the
 * program's exit status.
 *
 * What a GEM program does at the start, and in this order:
 *
 *   appl_init()     announce yourself to the AES
 *   graf_handle()   ask how big a character and a window gadget are,
 *                   and get the AES's own VDI handle
 *   v_opnvwk()      open a workstation of your own on it
 *
 * ...and the mirror image at the end.  Everything between is yours.
 * This one draws, waits a moment so the screen can be seen, and goes;
 * an interactive program would put an evnt_multi loop there instead
 * and answer WM_REDRAW.
 */
#include "gem.h"

/* v_opnvwk's eleven words: the defaults every GEM program opens with,
 * then the coordinate system (2 = raster, the device's own pixels). */
static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };

int main(void)
{
    WORD work_out[57];              /* 45 words and 12 more of points */
    WORD handle, wchar, hchar, wbox, hbox;
    WORD pxy[8];

    appl_init();
    handle = graf_handle(&wchar, &hchar, &wbox, &hbox);
    v_opnvwk(work_in, &handle, work_out);
    if (!handle) {                  /* no workstation: nothing to draw on */
        appl_exit();
        return 1;
    }

    /* work_out[0] and [1] are the last addressable pixel, so the screen
     * is one more of each: 640 x 240 on VBXE's HR overlay. */
    pxy[0] = 0;
    pxy[1] = 0;
    pxy[2] = work_out[0];
    pxy[3] = work_out[1];
    vsf_interior(handle, 1);        /* solid */
    vsf_color(handle, 0);           /* white */
    vr_recfl(handle, pxy);

    pxy[0] = 40;
    pxy[1] = 40;
    pxy[2] = work_out[0] - 40;
    pxy[3] = work_out[1] - 40;
    vsf_color(handle, 3);           /* cyan */
    vr_recfl(handle, pxy);
    vsf_perimeter(handle, 1);
    v_rbox(handle, pxy);            /* a rounded box round it */

    vst_color(handle, 1);           /* black */
    v_gtext(handle, 64, 80, "Hello from a gem4xe application.");
    v_gtext(handle, 64, 96, "Built with the kit, linked against nothing.");

    vsl_color(handle, 2);
    pxy[0] = 64;  pxy[1] = 120;
    pxy[2] = work_out[0] - 64;  pxy[3] = 120;
    v_pline(handle, 2, pxy);

    v_circle(handle, 320, 170, 30);

    evnt_timer(3000, 0);            /* three seconds, in milliseconds */

    v_clsvwk(handle);
    appl_exit();
    return 0;
}
