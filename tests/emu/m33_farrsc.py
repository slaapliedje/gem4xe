#!/usr/bin/env python3
"""Phase 45 gate: a resource in far memory, and the same file refused.

FARRSC.RSC is 42 KB -- 702 objects in 28 trees (tools/farrsc.py) -- and
the application pool is 14 KB of bank $00.  Two builds of one program
(src/m33_farrsc.c) ask for it under the stand-in desktop:

  F   M33.G4A, --data-model=large.  Its kit says it can take a far
      address, so rsrc_load puts the file in far memory, and the program
      draws tree 0 from there, hit-tests it, reads a free string through
      the address rsrc_gaddr handed back, and frees it.  The gate reads
      each of those results out of the program's NEAR variables, requires
      the addresses to be ABOVE bank $00 -- which is the whole claim --
      and looks at the screen while the dialog is up.

  G   M33S.G4A, --data-model=small.  Its kit passes no int_in, so it
      cannot ask, and a 16-bit program handed a far resource would have
      its pointers truncated with no error.  rsrc_load must answer 0 and
      nothing else may happen.

Both from one source, so the only difference is the model and the word
the kit sends (docs/far-trees.md, "who may receive a far address").

What the screen check is: the dialog's rectangle, as form_center placed
it, must carry text -- a count of dark pixels well above what an empty
box has.  It is not yet the pixel-exact comparison m4 makes for a pool
tree; the drawing goes through the same objc_draw, and that comparison
is the follow-up once the far tree can be handed to aesref's layout.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, symfile, vbxeref             # noqa: E402
import farrsc                               # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO,  # noqa: E402
                     SYMS)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402
from m17_desktop import header              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m33-boot.atr"))
APP = os.path.join(ROOT, "build", "m33_farrsc.g4a")
APP_SYM = os.path.join(ROOT, "build", "m33_farrsc.sym")
APPS = os.path.join(ROOT, "build", "m33s_farrsc.g4a")
APPS_SYM = os.path.join(ROOT, "build", "m33s_farrsc.sym")
RSC = os.path.join(ROOT, "build", "farrsc.rsc")
NAMES = ("m33_step", "m33_loaded", "m33_bank", "m33_lo", "m33_hdrlo", "m33_hdrhi",
         "m33_ap5", "m33_ap6", "m33_cx", "m33_cy", "m33_cw", "m33_ch",
         "m33_find", "m33_findok", "m33_str0", "m33_gfree", "m33_model",
         "m33_mtfar", "m33_mtnear", "m33_mtlo")
POOL = 14336
DARK_MIN = 2000                 # a 40x28-cell dialog with 20 rows of text has far more


def app_vars(b, syms, sym_path, g4a_path):
    """The program's NEAR variables, read by symbol against where the
    loader put its near region (the m29 pattern)."""
    link_near, near_size, far_banks = header(g4a_path)
    asym = symfile.load(sym_path)
    near = b.peek16(syms["app_near"])
    at = {n: asym[n] + near - link_near for n in NAMES}
    return {n: b.peek16(a) for n, a in at.items()}, at, near


def dark_pixels(path, x, y, w, h):
    from PIL import Image
    px = Image.open(path).convert("RGB").load()
    n = 0
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            r, g, bl = px[vbxeref.SHOT_X0 + xx, vbxeref.SHOT_Y0 + yy]
            if r + g + bl < 384:
                n += 1
    return n


def main(argv=()):
    keep = "--keep" in argv
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    size = os.path.getsize(RSC)
    check(size > POOL, f"the fixture is {size} bytes, which FITS the {POOL}-byte pool -- "
                       "this gate would then prove nothing")
    check(size <= 0xFFFF, f"the fixture is {size} bytes, over the one-bank limit")
    print(f"  FARRSC.RSC: {size} bytes, {farrsc.NOBS_TOTAL} objects in "
          f"{1 + farrsc.FILLER_TREES} trees; the pool is {POOL}")
    syms = symfile.load(SYMS)

    emu = launch(tag="m33", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        t, st = boot(b)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  M3.COM loaded and running {t} frames after RETURN")
        r = Runner(b, syms)
        r.run(PRELUDE)
        script = aesref.encode(PRELUDE + [(SHELL, (), ())], 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in script))
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)
        runs = syms["sh_runs"]
        check(poll(b, runs, 1) >= 0, "the stand-in desktop never started")

        # ---- F: the large-data build, which may take a far address -------
        b.key("F")
        tf = poll(b, runs, 2)
        check(tf >= 0, f"after F: M33.G4A did not start (sh_runs {b.peek16(runs)})")
        if tf < 0:
            return 1
        v, at, near = app_vars(b, syms, APP_SYM, APP)
        tw = poll(b, at["m33_step"], 7)     # drawn, and waiting for a key
        v, at, near = app_vars(b, syms, APP_SYM, APP)
        print(f"  M33.G4A up {tf} frames after F; near ${near:04X}; "
              f"step {v['m33_step']}, {'waiting' if tw >= 0 else 'NOT waiting'} "
              f"{tw if tw >= 0 else ''}".rstrip())
        check(v["m33_model"] == 4, f"M33.G4A's pointers are {v['m33_model']} bytes; expected 4")
        check(v["m33_loaded"] == 1, f"rsrc_load returned {v['m33_loaded']}, expected 1")
        if v["m33_loaded"]:
            hdr = (v["m33_hdrhi"] << 16) | v["m33_hdrlo"]
            tree = (v["m33_bank"] << 16) | v["m33_lo"]
            ptree = (v["m33_ap6"] << 16) | v["m33_ap5"]
            print(f"  the resource at ${hdr:06X} (global[7..8]); tree 0 at ${tree:06X}; "
                  f"ap_ptree ${ptree:06X}")
            check(v["m33_hdrhi"] != 0,
                  f"the AES put the resource in bank $00 (${hdr:06X}) -- it did not go far")
            check(v["m33_bank"] != 0 and v["m33_bank"] == v["m33_hdrhi"],
                  f"tree 0 at ${tree:06X} is not in the resource's bank ${v['m33_hdrhi']:02X}")
            check(v["m33_ap6"] == v["m33_hdrhi"] and hdr < ptree < hdr + size,
                  f"ap_ptree ${ptree:06X} is not inside the resource at ${hdr:06X}")
            check(v["m33_step"] >= 7, f"the program stopped at step {v['m33_step']}")
            print(f"  form_center: ({v['m33_cx']}, {v['m33_cy']}) {v['m33_cw']}x{v['m33_ch']}; "
                  f"objc_find at OK -> {v['m33_find']} (want {farrsc.FR_OK})")
            check(v["m33_findok"] == 1,
                  f"objc_find inside the OK button answered {v['m33_find']}, expected {farrsc.FR_OK}")
            check(v["m33_str0"] == farrsc.FR_FREE0_FIRST,
                  f"free string 0 read as {v['m33_str0']!r} through its far address, "
                  f"expected {farrsc.FR_FREE0_FIRST} ('{farrsc.FREE0[0]}')")
            os.makedirs(SHOTDIR, exist_ok=True)
            shot = os.path.join(SHOTDIR, "m33-far-dialog.png")
            b.screenshot(shot)
            cx, cy, cw, chh = v["m33_cx"], v["m33_cy"], v["m33_cw"], v["m33_ch"]
            ok_rect = 0 <= cx and 0 <= cy and cw > 0 and chh > 0 and cx + cw <= 640 and cy + chh <= 240
            check(ok_rect, f"form_center gave an impossible rectangle ({cx},{cy}) {cw}x{chh}")
            if ok_rect:
                dark = dark_pixels(shot, cx, cy, cw, chh)
                print(f"  {dark} dark pixels inside the dialog's rectangle ({shot})")
                check(dark >= DARK_MIN,
                      f"only {dark} dark pixels in the dialog's rectangle: the far tree was not drawn")
            if not fails and not keep:
                os.remove(shot)
            # let it free the resource; it then waits again, at step 9, so
            # its answer can be read before its near region goes back to
            # the shell
            b.key("RETURN")
            te = poll(b, at["m33_step"], 9)
            v, _, _ = app_vars(b, syms, APP_SYM, APP)
            # menu_text through the FAR tree (src/aes/menu.c mn_text).  It
            # took (uint16_t)ob_spec until 2026-09-18, and since far_alloc
            # hands out whole banks the remainder is the string's OFFSET IN
            # THE FILE -- so the copy went to bank $00 at that offset, on
            # top of whatever lives there.  On a SpartaDOS X machine that
            # was the DOS, and the next directory read jumped into a BRK:
            # a file selector that drew and then hung, three removes from
            # the menu call that did it.
            print(f"  menu_text: wrote far {'yes' if v['m33_mtfar'] else 'NO'}, "
                  f"bank $00 at ${v['m33_mtlo']:04X} "
                  f"{'untouched' if v['m33_mtnear'] else 'CLOBBERED'}")
            check(v["m33_mtfar"] == 1,
                  "menu_text did not write where the far tree's ob_spec points")
            check(v["m33_mtnear"] == 1,
                  f"menu_text wrote into bank $00 at ${v['m33_mtlo']:04X}: "
                  f"the bank was dropped from ob_spec")
            check(te >= 0 and v["m33_gfree"] == 1,
                  f"rsrc_free returned {v['m33_gfree']} (step {v['m33_step']}), expected 1")
            b.key("RETURN")                 # and leave
        # sh_runs counts the desktop too: its return is run 3
        check(poll(b, runs, 3) >= 0, f"the desktop did not come back after M33.G4A "
                                     f"(sh_runs {b.peek16(runs)})")
        b.frames(60)

        # ---- G: the small-data build, which cannot, and must be refused ---
        b.key("G")
        tg = poll(b, runs, 4)
        check(tg >= 0, f"after G: M33S.G4A did not start (sh_runs {b.peek16(runs)})")
        if tg >= 0:
            vs, ats, nears = app_vars(b, syms, APPS_SYM, APPS)
            te = poll(b, ats["m33_step"], 9)    # refused, and waiting to be read
            vs, _, _ = app_vars(b, syms, APPS_SYM, APPS)
            print(f"  M33S.G4A up {tg} frames after G; near ${nears:04X}; "
                  f"rsrc_load returned {vs['m33_loaded']}, step {vs['m33_step']}")
            check(vs["m33_model"] == 2, f"M33S.G4A's pointers are {vs['m33_model']} bytes; expected 2")
            check(vs["m33_loaded"] == 0,
                  f"rsrc_load gave a small-data program a resource that cannot fit the pool")
            check(te >= 0, f"M33S.G4A did not reach its wait (step {vs['m33_step']})")
            b.key("RETURN")                 # and leave
    finally:
        emu.stop()

    print()
    print(f"gem4xe-m33: {'PASS' if not fails else 'FAIL'} -- a resource in far memory, "
          f"and the same file refused, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
