#!/usr/bin/env python3
"""Host tests for the application bindings (src/app/gemlib.c).

A binding's whole job is to fill a parameter block: the opcode, the
sub-function, and the counts that say how many words travel in and out.
gem4xe reads those counts to decide how much to copy (src/sys/abi.c),
so a binding that miscounts loses an argument -- silently, and with
nothing in a compile or a link to say so.

So the library is compiled for the compiler's own simulator together
with tests/host/bind_sim.c, which replaces the three call gates with
recorders and calls every binding once.  What each one built is then
compared with the table below, which is written from the VDI and AES
contracts -- the same source tools/vdiref.py and tools/aesref.py are
written from -- and not from the library.

Two more things are asserted here, and they are what stops the surface
drifting again:

  * every function src/app/gem.h declares is exercised, so a binding
    cannot be added without being checked;
  * every opcode the system serves has a binding, so the library cannot
    fall behind the engine.  The exceptions are named and are the
    opcodes the driver answers with v_nop.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
GEMLIB_C = os.path.join(ROOT, "src", "app", "gemlib.c")
GEM_H = os.path.join(ROOT, "src", "app", "gem.h")
BIND_SIM_C = os.path.join(ROOT, "tests", "host", "bind_sim.c")
ABI_C = os.path.join(ROOT, "src", "sys", "abi.c")
ABI_H = os.path.join(ROOT, "src", "sys", "abi.h")
ABI_S = os.path.join(ROOT, "src", "sys", "abi.s")
GEMABI_S = os.path.join(ROOT, "src", "app", "gemabi.s")
VDI_C = os.path.join(ROOT, "src", "vdi", "vdi.c")

VDI, AES, DOS = 0, 1, 2
H = 7                                   # the handle bind_sim.c passes

# (name, kind, opcode, sub/nin, npts/nout, nints/nain, handle/naout).
# For the VDI: opcode, contrl[5], contrl[1], contrl[3], contrl[6].
# For the AES: opcode and control[1..4].
# For GEMDOS: the function number, which is the ST's.
EXPECT = [
    ("v_opnwk",          VDI, 1, 0, 0, 11, 0),
    ("v_clswk",          VDI, 2, 0, 0, 0, H),
    ("v_clrwk",          VDI, 3, 0, 0, 0, H),
    ("v_updwk",          VDI, 4, 0, 0, 0, H),
    ("v_exit_cur",       VDI, 5, 2, 0, 0, H),
    ("v_enter_cur",      VDI, 5, 3, 0, 0, H),
    ("v_pline",          VDI, 6, 0, 2, 0, H),
    ("v_pmarker",        VDI, 7, 0, 2, 0, H),
    ("v_gtext",          VDI, 8, 0, 1, 3, H),      # "abc"
    ("v_fillarea",       VDI, 9, 0, 3, 0, H),
    ("v_bar",            VDI, 11, 1, 2, 0, H),
    ("v_arc",            VDI, 11, 2, 4, 2, H),
    ("v_pieslice",       VDI, 11, 3, 4, 2, H),
    ("v_circle",         VDI, 11, 4, 3, 0, H),
    ("v_ellipse",        VDI, 11, 5, 2, 0, H),
    ("v_ellarc",         VDI, 11, 6, 2, 2, H),
    ("v_ellpie",         VDI, 11, 7, 2, 2, H),
    ("v_rbox",           VDI, 11, 8, 2, 0, H),
    ("v_rfbox",          VDI, 11, 9, 2, 0, H),
    ("v_justified",      VDI, 11, 10, 2, 6, H),    # two words and "abcd"
    ("vst_height",       VDI, 12, 0, 1, 0, H),
    ("vst_rotation",     VDI, 13, 0, 0, 1, H),
    ("vs_color",         VDI, 14, 0, 0, 4, H),
    ("vsl_type",         VDI, 15, 0, 0, 1, H),
    ("vsl_width",        VDI, 16, 0, 1, 0, H),
    ("vsl_color",        VDI, 17, 0, 0, 1, H),
    ("vsm_type",         VDI, 18, 0, 0, 1, H),
    ("vsm_height",       VDI, 19, 0, 1, 0, H),
    ("vsm_color",        VDI, 20, 0, 0, 1, H),
    ("vst_font",         VDI, 21, 0, 0, 1, H),
    ("vst_color",        VDI, 22, 0, 0, 1, H),
    ("vsf_interior",     VDI, 23, 0, 0, 1, H),
    ("vsf_style",        VDI, 24, 0, 0, 1, H),
    ("vsf_color",        VDI, 25, 0, 0, 1, H),
    ("vq_color",         VDI, 26, 0, 0, 2, H),
    ("v_locator",        VDI, 28, 0, 1, 0, H),
    ("vsm_choice",       VDI, 30, 0, 0, 0, H),     # sampled: nothing in
    ("v_string",         VDI, 31, 0, 0, 0, H),
    ("vswr_mode",        VDI, 32, 0, 0, 1, H),
    ("vsin_mode",        VDI, 33, 0, 0, 2, H),
    ("vql_attributes",   VDI, 35, 0, 0, 0, H),
    ("vqm_attributes",   VDI, 36, 0, 0, 0, H),
    ("vqf_attributes",   VDI, 37, 0, 0, 0, H),
    ("vqt_attributes",   VDI, 38, 0, 0, 0, H),
    ("vst_alignment",    VDI, 39, 0, 0, 2, H),
    ("v_opnvwk",         VDI, 100, 0, 0, 11, 0),
    ("v_clsvwk",         VDI, 101, 0, 0, 0, H),
    ("vq_extnd",         VDI, 102, 0, 0, 1, H),
    ("v_contourfill",    VDI, 103, 0, 1, 1, H),
    ("vsf_perimeter",    VDI, 104, 0, 0, 1, H),
    ("v_get_pixel",      VDI, 105, 0, 1, 0, H),
    ("vst_effects",      VDI, 106, 0, 0, 1, H),
    ("vst_point",        VDI, 107, 0, 0, 1, H),
    ("vsl_ends",         VDI, 108, 0, 0, 2, H),
    ("vro_cpyfm",        VDI, 109, 0, 4, 1, H),
    ("vr_trnfm",         VDI, 110, 0, 0, 0, H),
    ("vsc_form",         VDI, 111, 0, 0, 37, H),   # the cursor's 37 words
    ("vsf_udpat",        VDI, 112, 0, 0, 16, H),
    ("vsl_udsty",        VDI, 113, 0, 0, 1, H),
    ("vr_recfl",         VDI, 114, 0, 2, 0, H),
    ("vqin_mode",        VDI, 115, 0, 0, 1, H),
    ("vqt_extent",       VDI, 116, 0, 0, 3, H),    # "abc"
    ("vqt_width",        VDI, 117, 0, 0, 1, H),
    ("vex_timv",         VDI, 118, 0, 0, 0, H),
    ("vst_load_fonts",   VDI, 119, 0, 0, 1, H),
    ("vst_unload_fonts", VDI, 120, 0, 0, 1, H),
    ("vrt_cpyfm",        VDI, 121, 0, 4, 3, H),
    ("v_show_c",         VDI, 122, 0, 0, 1, H),
    ("v_hide_c",         VDI, 123, 0, 0, 0, H),
    ("vq_mouse",         VDI, 124, 0, 0, 0, H),
    ("vex_butv",         VDI, 125, 0, 0, 0, H),
    ("vex_motv",         VDI, 126, 0, 0, 0, H),
    ("vex_curv",         VDI, 127, 0, 0, 0, H),
    ("vq_key_s",         VDI, 128, 0, 0, 0, H),
    ("vs_clip",          VDI, 129, 0, 2, 1, H),
    ("vqt_name",         VDI, 130, 0, 0, 1, H),
    ("vqt_fontinfo",     VDI, 131, 0, 0, 0, H),

    ("appl_init",        AES, 10, 0, 1, 0, 0),
    ("appl_write",       AES, 12, 2, 1, 1, 0),
    ("appl_find",        AES, 13, 0, 1, 1, 0),
    ("appl_exit",        AES, 19, 0, 1, 0, 0),
    ("evnt_keybd",       AES, 20, 0, 1, 0, 0),
    ("evnt_button",      AES, 21, 3, 5, 0, 0),
    ("evnt_mouse",       AES, 22, 5, 5, 0, 0),     # a MOBLK is five words
    ("evnt_mesag",       AES, 23, 0, 1, 1, 0),
    ("evnt_timer",       AES, 24, 2, 1, 0, 0),
    ("evnt_multi",       AES, 25, 16, 7, 1, 0),
    ("evnt_multi_moblk", AES, 25, 16, 7, 1, 0),
    ("evnt_dclick",      AES, 26, 2, 1, 0, 0),
    ("menu_bar",         AES, 30, 1, 1, 1, 0),
    ("menu_icheck",      AES, 31, 2, 1, 1, 0),
    ("menu_ienable",     AES, 32, 2, 1, 1, 0),
    ("menu_tnormal",     AES, 33, 2, 1, 1, 0),
    ("menu_text",        AES, 34, 1, 1, 2, 0),
    ("menu_register",    AES, 35, 1, 1, 1, 0),
    ("objc_add",         AES, 40, 2, 1, 1, 0),
    ("objc_delete",      AES, 41, 1, 1, 1, 0),
    ("objc_draw",        AES, 42, 6, 1, 1, 0),
    ("objc_draw_grect",  AES, 42, 6, 1, 1, 0),   # gemlib spelling: same call
    ("objc_find",        AES, 43, 4, 1, 1, 0),
    ("objc_offset",      AES, 44, 1, 3, 1, 0),
    ("objc_order",       AES, 45, 2, 1, 1, 0),
    ("objc_edit",        AES, 46, 4, 2, 1, 0),
    ("objc_change",      AES, 47, 8, 1, 1, 0),
    ("objc_sysvar",      AES, 48, 4, 3, 0, 0),
    ("form_do",          AES, 50, 1, 1, 1, 0),
    ("form_dial",        AES, 51, 9, 1, 0, 0),
    ("form_dial_grect",  AES, 51, 9, 1, 0, 0),
    ("form_alert",       AES, 52, 1, 1, 1, 0),
    ("form_error",       AES, 53, 1, 1, 0, 0),
    ("form_center",      AES, 54, 0, 5, 1, 0),
    ("form_center_grect",AES, 54, 0, 5, 1, 0),
    ("form_keybd",       AES, 55, 3, 3, 1, 0),
    ("form_button",      AES, 56, 2, 2, 1, 0),
    ("graf_rubbox",      AES, 70, 4, 3, 0, 0),
    ("graf_dragbox",     AES, 71, 8, 3, 0, 0),
    ("graf_growbox",     AES, 73, 8, 1, 0, 0),
    ("graf_shrinkbox",   AES, 74, 8, 1, 0, 0),
    ("graf_watchbox",    AES, 75, 4, 1, 1, 0),     # int_in[0] is unused
    ("graf_handle",      AES, 77, 0, 5, 0, 0),
    ("graf_mouse",       AES, 78, 1, 1, 1, 0),
    ("graf_mkstate",     AES, 79, 0, 5, 0, 0),
    ("scrp_read",        AES, 80, 0, 1, 1, 0),
    ("scrp_write",       AES, 81, 0, 1, 1, 0),
    ("fsel_input",       AES, 90, 0, 2, 2, 0),
    ("fsel_exinput",     AES, 91, 0, 2, 3, 0),
    ("wind_create",      AES, 100, 5, 1, 0, 0),
    ("wind_create_grect", AES, 100, 5, 1, 0, 0),  # gemlib spelling: same call
    ("wind_open",        AES, 101, 5, 1, 0, 0),
    ("wind_open_grect",  AES, 101, 5, 1, 0, 0),   # gemlib spelling: same call
    ("wind_close",       AES, 102, 1, 1, 0, 0),
    ("wind_delete",      AES, 103, 1, 1, 0, 0),
    ("wind_get",         AES, 104, 2, 5, 0, 0),
    ("wind_get_grect",   AES, 104, 2, 5, 0, 0),
    ("wind_set",         AES, 105, 6, 1, 0, 0),
    ("wind_set_grect",   AES, 105, 6, 1, 0, 0),
    ("wind_set_str",     AES, 105, 6, 1, 0, 0),
    ("wind_find",        AES, 106, 2, 1, 0, 0),
    ("wind_update",      AES, 107, 1, 1, 0, 0),
    ("wind_calc",        AES, 108, 6, 5, 0, 0),
    ("wind_calc_grect",  AES, 108, 6, 5, 0, 0),
    ("rsrc_load",        AES, 110, 0, 1, 1, 0),
    ("rsrc_free",        AES, 111, 0, 1, 0, 0),
    ("rsrc_gaddr",       AES, 112, 2, 1, 0, 1),
    ("rsrc_saddr",       AES, 113, 2, 1, 1, 0),
    ("rsrc_obfix",       AES, 114, 1, 1, 1, 0),
    ("shel_read",        AES, 120, 0, 1, 2, 0),
    ("shel_write",       AES, 121, 3, 1, 2, 0),
    ("shel_get",         AES, 122, 1, 1, 1, 0),
    ("shel_put",         AES, 123, 1, 1, 1, 0),
    ("shel_find",        AES, 124, 0, 1, 1, 0),
    ("shel_envrn",       AES, 125, 0, 1, 2, 0),

    ("Pterm0",   DOS, 0x00, 0, 0, 0, 0),
    ("Cconin",   DOS, 0x01, 0, 0, 0, 0),
    ("Cconout",  DOS, 0x02, 0, 0, 0, 0),
    ("Cauxin",   DOS, 0x03, 0, 0, 0, 0),
    ("Cauxout",  DOS, 0x04, 0, 0, 0, 0),
    ("Cprnout",  DOS, 0x05, 0, 0, 0, 0),
    ("Crawio",   DOS, 0x06, 0, 0, 0, 0),
    ("Crawcin",  DOS, 0x07, 0, 0, 0, 0),
    ("Cnecin",   DOS, 0x08, 0, 0, 0, 0),
    ("Cconws",   DOS, 0x09, 0, 0, 0, 0),
    ("Cconrs",   DOS, 0x0A, 0, 0, 0, 0),
    ("Cconis",   DOS, 0x0B, 0, 0, 0, 0),
    ("Dsetdrv",  DOS, 0x0E, 0, 0, 0, 0),
    ("Cconos",   DOS, 0x10, 0, 0, 0, 0),
    ("Cprnos",   DOS, 0x11, 0, 0, 0, 0),
    ("Cauxis",   DOS, 0x12, 0, 0, 0, 0),
    ("Cauxos",   DOS, 0x13, 0, 0, 0, 0),
    ("Dgetdrv",  DOS, 0x19, 0, 0, 0, 0),
    ("Fsetdta",  DOS, 0x1A, 0, 0, 0, 0),
    ("Super",    DOS, 0x20, 0, 0, 0, 0),
    ("Tgetdate", DOS, 0x2A, 0, 0, 0, 0),
    ("Tsetdate", DOS, 0x2B, 0, 0, 0, 0),
    ("Tgettime", DOS, 0x2C, 0, 0, 0, 0),
    ("Tgettimeofday", DOS, 0x155, 0, 0, 0, 0),
    ("Psystem",  DOS, 0x1F0, 0, 0, 0, 0),
    ("Tsettime", DOS, 0x2D, 0, 0, 0, 0),
    ("Fgetdta",  DOS, 0x2F, 0, 0, 0, 0),
    ("Sversion", DOS, 0x30, 0, 0, 0, 0),
    ("Ptermres", DOS, 0x31, 0, 0, 0, 0),
    ("Dfree",    DOS, 0x36, 0, 0, 0, 0),
    ("Dcreate",  DOS, 0x39, 0, 0, 0, 0),
    ("Ddelete",  DOS, 0x3A, 0, 0, 0, 0),
    ("Dsetpath", DOS, 0x3B, 0, 0, 0, 0),
    ("Fcreate",  DOS, 0x3C, 0, 0, 0, 0),
    ("Fopen",    DOS, 0x3D, 0, 0, 0, 0),
    ("Fclose",   DOS, 0x3E, 0, 0, 0, 0),
    ("Fread",    DOS, 0x3F, 0, 0, 0, 0),
    ("Fwrite",   DOS, 0x40, 0, 0, 0, 0),
    ("Fdelete",  DOS, 0x41, 0, 0, 0, 0),
    ("Fseek",    DOS, 0x42, 0, 0, 0, 0),
    ("Fattrib",  DOS, 0x43, 0, 0, 0, 0),
    ("Mxalloc",  DOS, 0x44, 0, 0, 0, 0),
    ("Fdup",     DOS, 0x45, 0, 0, 0, 0),
    ("Fforce",   DOS, 0x46, 0, 0, 0, 0),
    ("Dgetpath", DOS, 0x47, 0, 0, 0, 0),
    ("Malloc",   DOS, 0x48, 0, 0, 0, 0),
    ("Mfree",    DOS, 0x49, 0, 0, 0, 0),
    ("Mshrink",  DOS, 0x4A, 0, 0, 0, 0),
    ("Pexec",    DOS, 0x4B, 0, 0, 0, 0),
    ("Pterm",    DOS, 0x4C, 0, 0, 0, 0),
    ("Fsfirst",  DOS, 0x4E, 0, 0, 0, 0),
    ("Fsnext",   DOS, 0x4F, 0, 0, 0, 0),
    ("Frename",  DOS, 0x56, 0, 0, 0, 0),
    ("Fdatime",  DOS, 0x57, 0, 0, 0, 0),
]

# The second pass: what each inquiry handed back when the gates answered
# with a pattern -- intout[i] = 100+i, ptsout[i] = 200+i, int_out[i] =
# 300+i.  So 200 is "ptsout[0]" and 104 is "intout[4]", and this table
# says which word of the answer the VDI and the AES put each value in.
# (name, up to five of what the binding handed back, 0 for unused)
ANSWERS = [
    ("vst_height",     200, 201, 202, 203, 0),  # char w/h, cell w/h
    ("vsl_width",      200, 0, 0, 0, 0),
    ("vsm_height",     201, 0, 0, 0, 0),        # the height is the y word
    ("vq_color",       101, 102, 103, 0, 0),    # intout[0] is the index
    ("v_locator",      200, 201, 100, 0, 0),    # x, y, then the terminator
    ("vql_attributes", 100, 101, 102, 200, 0),  # ...and the width
    ("vqm_attributes", 100, 101, 102, 201, 0),  # ...and the height
    ("vqf_attributes", 100, 101, 102, 104, 0),  # five words, not four
    ("vqt_attributes", 100, 105, 200, 203, 0),  # six words and four points
    ("vst_alignment",  100, 101, 0, 0, 0),
    ("v_get_pixel",    100, 101, 0, 0, 0),
    ("vst_point",      100, 200, 201, 202, 203),
    ("vqt_extent",     200, 203, 205, 207, 0),  # four corners
    ("vqt_width",      100, 200, 202, 204, 0),  # the deltas are a POINT apart
    ("vqin_mode",      100, 0, 0, 0, 0),
    ("vq_mouse",       100, 200, 201, 0, 0),
    ("vq_key_s",       100, 0, 0, 0, 0),
    ("vqt_name",       100, 101, 102, 0, 0),    # the id, then the name
    ("evnt_button",    301, 302, 303, 304, 0),  # the AES answers from
    ("evnt_mouse",     301, 302, 303, 304, 0),  # int_out[1] on
    ("objc_offset",    301, 302, 0, 0, 0),
    ("form_center",    301, 302, 303, 304, 0),
    ("graf_handle",    301, 302, 303, 304, 0),
    ("graf_mkstate",   301, 302, 303, 304, 0),
    ("wind_get",       301, 302, 303, 304, 0),
    ("wind_calc",      301, 302, 303, 304, 0),
    # The GRECT spellings answer with the same four words, in x, y, w, h
    # order -- which is what a wrapper can get wrong while building a
    # perfectly correct parameter block.
    ("form_center_grect", 301, 302, 303, 304, 0),
    ("wind_get_grect",    301, 302, 303, 304, 0),
    ("wind_calc_grect",   301, 302, 303, 304, 0),
    # (0,0,10,10) against (5,5,10,10): they overlap, and the overlap is
    # the square from 5,5 to 10,10.  Atari's rc_intersect returns TRUE
    # and writes the answer into the SECOND rectangle.
    ("rc_intersect",   1, 5, 5, 5, 5),
    # ...and their union spans 0,0 to 15,15.
    ("rc_union",       0, 0, 15, 15, 0),
]

# The VDI opcodes with no binding: the driver's own v_nop entries
# (src/vdi/vdi.c's jump tables), where a binding that silently did
# nothing would be worse than a name that is not there.  v_clswk and
# v_updwk are nops too and DO have bindings, because every GEM program
# calls them and a screen has nothing to close or write out.
VDI_NOP_OK = {10, 27, 29, 34}            # cell array twice, valuator, and 34

# Bindings that issue NO system call at all, and so build no parameter block
# for EXPECT to describe. There is exactly one, and it is not a local
# peculiarity: vq_gdos() has "OPCODE N/A" in the Compendium too (7.92) --
# on the ST it is a magic `move.l #-2,d0; trap #2` rather than a VDI call,
# and here, where there is no GDOS to find, it is a constant. It is still
# exercised by bind_sim.c, because the point of that check is that no
# declared function goes unlooked-at.
# rc_intersect and rc_union reach no gate either, for a plainer reason:
# they are arithmetic on two rectangles and Atari's own AES has them in
# FUNCTION.C rather than in a binding table.  What they compute IS
# asserted, in OUTS.
NO_CALL_OK = {"vq_gdos", "rc_intersect", "rc_union"}
AES_NO_BINDING = set()                   # every opcode the shim serves is bound


def read(path):
    with open(path) as f:
        return f.read()


def decl_names(text):
    """The functions a header declares, ignoring the call gates."""
    out = set()
    for m in re.finditer(r'^(?:SIMPLE_CALL\s+)?(?:const\s+)?'
                         r'(?:WORD|UWORD|LONG|void|char|DTA FAR \*)\s*\**'
                         r'(\w+)\s*\(', text, re.M):
        out.add(m.group(1))
    return out - {"vdi_call", "aes_call", "dos_call"}


def called_names(text):
    body = text[text.index("int main(void)"):]
    return (set(re.findall(r'^\s{4}([A-Za-z_]\w*)\(', body, re.M))
            - {"return", "put"})      # put() is the recorder, not a binding


class TestBindingsAreComplete(unittest.TestCase):
    """These need no toolchain: they read the sources."""

    def test_every_declared_binding_is_exercised(self):
        declared = decl_names(read(GEM_H))
        called = called_names(read(BIND_SIM_C))
        self.assertEqual(sorted(declared - called), [],
                         "declared in gem.h and never called by bind_sim.c")

    def test_every_exercised_binding_is_in_the_table(self):
        called = called_names(read(BIND_SIM_C))
        table = {n for n, *_ in EXPECT}
        self.assertEqual(sorted(called - table - NO_CALL_OK), [],
                         "called by bind_sim.c and not in EXPECT")

    def test_every_vdi_opcode_the_driver_serves_has_a_binding(self):
        src = read(VDI_C)
        tables = "".join(src.split("static const VDI_OP jmptb")[1:])
        served = {int(num) for fn, num in
                  re.findall(r'(vdi_\w+|v_nop),?\s*/\*\s*(\d+)', tables)
                  if fn != "v_nop"}
        bound = {op for _, kind, op, *_ in EXPECT if kind == VDI}
        self.assertEqual(sorted(served - bound - VDI_NOP_OK), [],
                         "the driver serves these and the library cannot "
                         "reach them")

    def test_every_aes_opcode_the_shim_serves_has_a_binding(self):
        src = read(ABI_C)
        shim = src[src.index("case 10:"):src.index("default:\n        gem_bad")]
        served = {int(m) for m in re.findall(r'^\s*case (\d+):', shim, re.M)}
        bound = {op for _, kind, op, *_ in EXPECT if kind == AES}
        self.assertEqual(sorted(served - bound - AES_NO_BINDING), [],
                         "the shim serves these and the library cannot "
                         "reach them")


class TestSignatures(unittest.TestCase):
    """The three COP signature bytes, on both sides of the call gate."""

    def test_the_gates_and_the_handler_agree_and_are_legal(self):
        def nums(pattern, path, names=None):
            found = re.findall(pattern, read(path), re.M)
            return {(names or {}).get(k, k): int(v, 16) for k, v in found}

        want = nums(r'^#define ABI_(VDI|AES|GEMDOS)\s+0x([0-9A-Fa-f]+)', ABI_H)
        self.assertEqual(set(want), {"VDI", "AES", "GEMDOS"})
        self.assertEqual(
            nums(r'^ABI_(VDI|AES|GEMDOS):\s+\.equ\s+0x([0-9A-Fa-f]+)', ABI_S),
            want, "the handler (abi.s) checks other bytes than abi.h names")
        self.assertEqual(
            nums(r'^(vdi|aes|dos)_call:\s+cop\s+#0x([0-9A-Fa-f]+)', GEMABI_S,
                 {"vdi": "VDI", "aes": "AES", "dos": "GEMDOS"}),
            want, "the application's gates (gemabi.s) make other bytes than "
                  "abi.h names")
        self.assertEqual(len(set(want.values())), 3)
        for k, v in want.items():
            # $00 and $01 are Rapidus OS's; $80-$FF are reserved by WDC
            self.assertTrue(0x02 <= v <= 0x7F,
                            f"ABI_{k} ${v:02X} is outside $02-$7F")


class TestBlocks(unittest.TestCase):
    """What each binding actually builds, out of the simulator."""

    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "bind")
        os.makedirs(out, exist_ok=True)
        objs = []
        for src in (GEMLIB_C, BIND_SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"),
                            "-I", os.path.join(ROOT, "src", "app"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "bind.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        p = subprocess.run([db, "--nh", "--nx", "--exit-breakpoint", elf],
                           input="run\nprint bind_n\nprint bind_rec\nquit\n",
                           capture_output=True, text=True, timeout=180)
        txt = p.stdout + p.stderr
        m = re.search(r"\$\d+ = (\d+)", txt)
        if not m:
            raise AssertionError(f"the simulator said nothing:\n{txt[-2000:]}")
        n = int(m.group(1))
        vals = [int(v) for v in re.findall(r"\[\s*\d+\s*\] = (-?\d+)", txt)]
        cls.recs = [tuple(vals[i * 6:(i + 1) * 6]) for i in range(n)]

    def test_one_record_per_binding(self):
        blocks = [r for r in self.recs if r[0] != 3]
        self.assertEqual(len(blocks), len(EXPECT),
                         "a binding made more or fewer calls than one")

    def test_each_answer_comes_from_the_word_the_contract_names(self):
        """The other half of a binding's job: reading the answer out of
        the right word.  100+i is intout[i], 200+i ptsout[i], 300+i the
        AES's int_out[i]."""
        got = [r for r in self.recs if r[0] == 3]
        self.assertEqual(len(got), len(ANSWERS),
                         "the answer pass and its table disagree in length")
        bad = []
        for want, rec in zip(ANSWERS, got):
            if tuple(want[1:]) != rec[1:]:
                bad.append(f"{want[0]}: handed back {rec[1:]}, the contract "
                           f"says {tuple(want[1:])}")
        self.assertEqual(bad, [])

    def test_each_block_is_the_one_the_contract_asks_for(self):
        bad = []
        blocks = [r for r in self.recs if r[0] != 3]
        for want, got in zip(EXPECT, blocks):
            name, kind = want[0], want[1]
            if tuple(want[1:]) != got:
                bad.append(f"{name}: built {got}, the contract says "
                           f"{tuple(want[1:])}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
