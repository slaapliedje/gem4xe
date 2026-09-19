#!/usr/bin/env python3
"""What of the ST's GEM surface gem4xe serves, by enumeration.

WHY THIS EXISTS.  "Are all the calls there?" has been answered twice by
reading and judgement, and judgement was wrong both times -- once about
what qed needs, once about what cflib needs.  This answers it
mechanically instead, against the surface a real ST program is written
to: FreeMiNT's **gemlib**, the binding library those programs link.

It is a REPORT, not a gate.  A name gemlib declares and gem4xe does not
is not automatically a defect: gemlib carries MagiC and AES 4.x
extensions, MiNT-only calls, the AV protocol (dead on a single-
application system), UTF-16 text, GDOS and metafile drivers, and a lot
of its own conveniences (`wind_get_int`, `form_xdial_grect`, the `_grect`
family).  The value is that the LIST is complete, so a judgement about
any one name is made against the whole rather than from memory.

    python3 tools/surface.py [--gemlib DIR] [--missing]

gemlib is expected at ~/dev/gemlib (github.com/freemint/gemlib).  Its
single-thread names are macros over `mt_*`, so all three spellings are
collected.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GEMLIB = os.path.expanduser("~/dev/gemlib")

AES = r'^(appl|evnt|menu|objc|form|graf|scrp|fsel|wind|rsrc|shel)_'
VDI = r'^(v_|vs|vq|vr|vex)'

# Why a name gemlib has is not a gem4xe gap.  Each pattern says which.
EXCUSED = [
    (r'^(v_(alpha|curtext|curup|curdown|curleft|curright|curhome|cur)|'
     r'v_(ee|rv|dspcur|rmcur))', "VT-52 escapes: gem4xe's console is its own"),
    (r'^(v_(bit_image|write_meta|meta_extents|clear_disp_list|form_adv|'
     r'output_window|page_size|copies|trays|orient|offset|hardcopy|escape2000)|'
     r'vq_(page_name|tray_names|scan|tdimensions|calibrate)|vqp_|vsp_|'
     r'vs_(calibrate|mute)|v_sound)', "GDOS, metafile and printer drivers"),
    (r'^(v_(fontinit|loadcache|savecache|flushcache|set_app_buff)|'
     r'vqt_(cachesize|get_table)|vst_(error|scratch)|vq_vgdos)',
     "FSM/SpeedoGDOS font machinery"),
    (r'16n?$|16n_pxy$|^vqt_extentn$|^v_gtextn$', "UTF-16 / counted text, MagiC"),
    (r'^appl_(bvset|control|options|search)$',
     "AV/OLGA and MiNT: dead on a single-application system"),
    (r'^(v_(cellarray)|vq_(cellarray|chcells|curaddress|tabstatus)|'
     r'vs_curaddress|vrq_|vsm_(locator|string|valuator)|vs_palette)',
     "opcodes the driver answers with nothing (kit README says why)"),
    (r'_grect$|^(wind_(get|set)_(int|ptr)|wind_set_ptr_int|wind_sget|'
     r'evnt_multi_fast|graf_(xhandle|rubbbox|rubberbox)|vs_clip_(off|pxy))',
     "gemlib's own conveniences, not AES calls"),
    (r'^(objc_x|form_x|wind_x|fsel_boxinput|graf_multirubber|graf_wwatchbox|'
     r'form_w|objc_w|menu_(click|unregister)|shel_help|wind_draw|'
     r'appl_getinfo_str)',
     "AES 4.x / MagiC extensions"),
]


def decls(path):
    txt = open(path, errors="replace").read()
    txt = re.sub(r'/\*.*?\*/', ' ', txt, flags=re.S)
    txt = re.sub(r'//[^\n]*', ' ', txt)
    out = {m.group(1) for m in
           re.finditer(r'\b([a-z][a-z0-9_]{2,})\s*\([^;{)]*\)\s*;', txt)}
    out |= {m.group(1) for m in
            re.finditer(r'^#define\s+([a-z][a-z0-9_]{2,})\s*\(', txt, re.M)}
    out |= {m.group(1)[3:] for m in
            re.finditer(r'\b(mt_[a-z][a-z0-9_]{2,})\s*\(', txt)}
    return out


def main(argv):
    gl = GEMLIB
    if "--gemlib" in argv:
        gl = argv[argv.index("--gemlib") + 1]
    if not os.path.isdir(gl):
        print(f"gemlib not found at {gl} -- clone github.com/freemint/gemlib")
        return 2
    g = set()
    for f in ("gem.h", "mt_gem.h", "gemx.h"):
        p = os.path.join(gl, f)
        if os.path.exists(p):
            g |= decls(p)
    x = decls(os.path.join(ROOT, "src", "app", "gem.h"))
    keep = lambda s: {n for n in s if re.match(AES, n) or re.match(VDI, n)}
    g, x = keep(g), keep(x)

    missing = sorted(g - x)
    excused, real = {}, []
    for n in missing:
        for pat, why in EXCUSED:
            if re.search(pat, n):
                excused.setdefault(why, []).append(n)
                break
        else:
            real.append(n)

    split = lambda s: (sorted(n for n in s if re.match(AES, n)),
                       sorted(n for n in s if re.match(VDI, n)))
    ga, gv = split(g)
    xa, xv = split(x)
    print(f"the ST's surface, as FreeMiNT's gemlib declares it: "
          f"{len(ga)} AES + {len(gv)} VDI")
    print(f"gem4xe declares {len(xa)} AES + {len(xv)} VDI, and covers "
          f"{len(g & x)} of gemlib's names\n")

    for why, names in sorted(excused.items()):
        print(f"  {len(names):3d} excused -- {why}")
    ra, rv = split(set(real))
    print(f"\n  {len(real):3d} NOT EXCUSED: {len(ra)} AES, {len(rv)} VDI")
    for group, names in (("AES", ra), ("VDI", rv)):
        if not names:
            print(f"\n{group}: nothing")
            continue
        print(f"\n{group}:")
        for i in range(0, len(names), 4):
            print("  " + "".join(f"{n:<22}" for n in names[i:i + 4]))
    if "--missing" in argv:
        print("\nall names gemlib has and gem4xe does not:")
        for i in range(0, len(missing), 4):
            print("  " + "".join(f"{n:<22}" for n in missing[i:i + 4]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
