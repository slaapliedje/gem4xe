#!/usr/bin/env python3
"""Phase 10 gate: the application ABI.

The runner's sys op 3004 loads the gate application (src/m11_app.c: a
program linked on its own rules, src/app/gemapp.scm, against nothing of
gem4xe's) from the blob packed into the image, relocates it into the
bank-$00 pool and a far bank, and calls it.  The application makes the
calls a small GEM program makes -- appl_init, graf_handle, v_opnvwk,
drawing, an object tree, a window, a timer wait -- through COP, and
records what every call returned through the ABI's copy-out in its own
memory.

Three things are then compared.  The application's records, read out of
the pool by symbol (build/m11_app.sym, translated by where the loader
put the near part), against the reference's records for the same calls
-- the reference runs the runner's prelude and then the application's
sequence, with the tree decoded from the application's memory as the
loader and the application left it.  The runner's own record of op 3004:
the loader's status, the near base against the pool bounds the linker
reported, the far bank against where the image ends and the first
megabyte, and three counts that must agree -- what main() returned, the
records the application wrote, the COP calls the ABI took -- with none
refused.  And the screen, against the reference's.

Phase 14 added the third entry, GEMDOS (COP #$44): after appl_exit the
application asks the version, the drive, the boot disk's directory entry
by entry, a file that is not there, and how much memory is left, into
dosres[]; the directory count is checked against the image itself and
the calls are added to the COP reconciliation.

Last, the application makes one COP that is not gem4xe's: Rapidus OS's
COP #$01 with a function code the OS does not have (src/m11_cop.s).  On
the stock OS nobody else takes COPs, so gem4xe refuses it -- one call
refused, Y back as it went in.  With --os=ROM the machine runs that ROM as
its OS, from a private emulator profile (build/altirra-m11os) whose XL
kernel entry points at it; under Rapidus OS gem4xe must pass the COP on,
the OS answers -110, and nothing is refused.

  python3 tests/emu/m11_abi.py [--shot] [--os=XLOS816A.ROM]
"""
import os
import re
import shutil
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import vbxeref, vdiref, aesref, symfile, atr  # noqa: E402
from vdiref import (WORK_IN, V_OPNVWK, VSF_COLOR, VSF_INTERIOR, VR_RECFL,  # noqa: E402
                    VST_COLOR, V_GTEXT, VSL_COLOR, V_PLINE)
from aesref import (Obj, Text, APPL_INIT, APPL_EXIT, GRAF_HANDLE, OBJC_DRAW,  # noqa: E402
                    WIND_CREATE, WIND_OPEN, WIND_GET, WIND_CLOSE, WIND_DELETE,
                    EVNT_TIMER, NAME, CLOSER, MOVER, WF_WXYWH, OBJ_SIZE)
from m4_aes import PRELUDE                                          # noqa: E402
from m7_form import poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE, DISK, SYMS, SHOTDIR  # noqa: E402

APP_SYMS = os.path.join(ROOT, "build", "m11_app.sym")
APP_G4A = os.path.join(ROOT, "build", "m11_app.g4a")
LOAD_RUN = 3004
APP_OK = 0
REC_WORDS = vdiref.RESULT_WORDS
FOREIGN_REFUSED = 0x1234        # src/m11_cop.s: Y as it went in
# AES calls src/m11_app.c makes WITHOUT a record_aes(): five objc_sysvar
# probes, three appl_find ones, six appl_getinfo ones and one
# appl_yield, and one graf_mbox -- which is here for the dispatch case
# rather than for an answer, and whose real check is that the screen
# below still matches the model.  They are deliberately outside
# results[], because every entry there is compared against
# tools/aesref.py and these calls' answers are constants a specification
# fixes rather than behaviour a model computes.  They still cost a COP
# each, so the reconciliation below has to know how many -- naming them
# keeps it able to catch a call nobody meant to make.
UNRECORDED_AES = 5 + 3 + 6 + 1 + 1
FOREIGN_OS = -110               # Rapidus OS: an unassigned kmem function
PROFILE_OS = os.path.join(ROOT, "build", "altirra-m11os")


def os_profile(rom):
    """A private emulator profile whose XL kernel is `rom`: the user's own
    settings, with the Path of the entry registered for the XL ROM the
    launcher uses changed.  Set before the emulator starts, which is
    when it reads XDG_CONFIG_HOME.  None if there is no such entry."""
    from a8test.launcher import XLROM
    shared = open(os.path.expanduser("~/.config/altirra/settings.ini")).read()
    for m in re.finditer(r"\[User\\AltirraSDL\\Firmware\\Available\\[0-9A-F]+\]\n"
                         r"(?:\"[^\n]*\n)*", shared, re.I):
        sec = m.group(0)
        if f'"Path" = "{XLROM}"' in sec:
            shutil.rmtree(PROFILE_OS, ignore_errors=True)
            os.makedirs(os.path.join(PROFILE_OS, "altirra"))
            with open(os.path.join(PROFILE_OS, "altirra", "settings.ini"), "w") as f:
                f.write(shared.replace(sec, sec.replace(f'"Path" = "{XLROM}"',
                                                        f'"Path" = "{rom}"')))
            os.environ["XDG_CONFIG_HOME"] = PROFILE_OS
            return PROFILE_OS
    return None

# The application's sequence, as src/m11_app.c makes it -- one entry per
# record it writes: (script record, int_out words the AES binding asks
# for, the return the ABI gives where the runner's op gives none).  The
# two values the application got at run time and used in later calls --
# hbox from graf_handle, the window handle from wind_create -- are read
# from its records, so the reference is given the calls the application
# actually made; its own returns for them are compared like the rest.
TEXT = "gem4xe application"


def app_calls(hbox, wh):
    return [
        ((APPL_INIT,), 1, None),
        ((GRAF_HANDLE,), 5, None),
        ((V_OPNVWK, (), WORK_IN), None, None),
        ((VSF_COLOR, (), (3,)), None, None),
        ((VSF_INTERIOR, (), (1,)), None, None),
        ((VR_RECFL, (20, 20, 619, 219), ()), None, None),
        ((VST_COLOR, (), (1,)), None, None),
        ((V_GTEXT, (24, 32), tuple(ord(c) for c in TEXT)), None, None),
        ((VSL_COLOR, (), (2,)), None, None),
        ((V_PLINE, (30, 200, 300, 180, 600, 210), ()), None, None),
        ((OBJC_DRAW, (0, 0, 640, 240), (0, 8)), 1, 1),
        ((WIND_CREATE, (), (NAME | CLOSER | MOVER, 0, hbox, 640, 240 - hbox)), 1, None),
        ((WIND_OPEN, (), (wh, 320, 40, 280, 150)), 1, None),
        ((WIND_GET, (), (wh, WF_WXYWH)), 5, None),
        ((EVNT_TIMER, (), (40, 0)), 1, None),
        ((WIND_CLOSE, (), (wh,)), 1, None),
        ((WIND_DELETE, (), (wh,)), 1, None),
        ((APPL_EXIT,), 1, None),
    ]


TIMER_INDEX = 14        # evnt_timer's place in the list: the one that needs a plan


def abi_record(rec, nout, ret):
    """What the application records for an AES call: no points, control[2]
    int_out words -- the binding's count, not the runner's -- and the
    return the ABI gives where the runner's op gives none."""
    if nout is None:
        return rec
    io = list(rec[2:2 + vdiref.RESULT_INTOUT])
    if ret is not None:
        io[0] = ret
    return vdiref.record(0, nout, io, [0, 0, 0])


def read_tree(b, addr, n, mem):
    """The application's tree from the target's memory: n objects at addr,
    and the strings the spec words point at, as the model reads them."""
    raw = bytes(b.memdump(addr, OBJ_SIZE * n))
    objs = []
    for i in range(n):
        f = struct.unpack("<hhhHHHIhhhh", raw[i * OBJ_SIZE:(i + 1) * OBJ_SIZE])
        o = Obj(*f)
        if o.ob_type in (aesref.G_STRING, aesref.G_BUTTON, aesref.G_TITLE):
            # a far pointer to bank $00 data: the low word is the address
            sa = o.ob_spec & 0xFFFF
            s = bytes(b.memdump(sa, 64))
            s = s[:s.index(b"\0")].decode("latin-1")
            mem[o.ob_spec] = Text(s)
        objs.append(o)
    return objs


def main(argv):
    keep = "--shot" in argv
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    app = symfile.load(APP_SYMS)
    sa = syms["vdi_script"]
    results_addr, count_addr = syms["vdi_results"], syms["vdi_result_count"]
    script_room = min(a for a in syms.values() if a > sa) - sa
    # The placeholder base the program was LINKED at, from the .G4A
    # header, which is where the loader reads it too.  It used to be the
    # lowest symbol in the .sym, and that stopped being the same thing:
    # a large-data program needs _NearBaseAddress declared
    # (src/app/gemapp.scm) and it is zero, so the lowest symbol became 0
    # and every read came out a page adrift -- while the program itself
    # ran perfectly and returned the right count, which is what made it
    # look like anything but a gate bug.
    with open(APP_G4A, "rb") as f:
        link_near = struct.unpack("<H", f.read(8)[4:6])[0]
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    os_rom = next((os.path.abspath(a[5:]) for a in argv if a.startswith("--os=")), None)
    if os_rom:
        if not os_profile(os_rom):
            print("gem4xe-m11: no firmware entry for the XL ROM in "
                  "~/.config/altirra/settings.ini to point at the ROM")
            return 2
        print(f"the OS: {os_rom}")
    emu = launch(tag="m11", memsize="1088K", extra_args=["--disk", DISK],
                 require_real_rom=not os_rom)
    b = emu.bridge
    try:
        if os_rom:
            # Rapidus OS halts on the 6502 the machine powers up as, so
            # the 65C816 is selected before it runs at all, as the
            # Rapidus BIOS does.
            b.poke(0xD1FF, 0x01)
            b.poke(0xD191, 0x00)
            b.frames(800)
        else:
            b.frames(300)
            b.poke(0xD1FF, 0x01)
            b.poke(0xD191, 0x00)
            b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        # "VD" says the runner is alive; STATUS[2] == 1 says it is
        # ready for scripts, which is what staging one needs.
        for _ in range(200):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1

        script = PRELUDE + [(LOAD_RUN,)]
        words = aesref.encode(script, 0)
        assert len(words) * 2 <= script_room
        b.memload(sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                               for w in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, count_addr, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)
        ok = False
        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                ok = True
                break
            b.frames(4)
        if not ok:
            print("FAIL: the runner did not finish (the application may be wedged)")
            return 1
        b.frames(4)
        shot = os.path.join(SHOTDIR, "m11-00.png")
        b.screenshot(shot)

        # -- the runner's record of op 3004 -----------------------------------
        n = b.peek16(count_addr)
        check(n == len(script), f"{n} runner records, expected {len(script)}")
        got = vdiref.decode(b.memdump(results_addr, n * REC_WORDS * 2), n)
        run = got[-1]
        status, near_base, far_bank, main_ret, calls, bad = run[2 + 6:2 + 12]
        near_base &= 0xFFFF                 # decoded signed; it is an address
        print(f"  load status {status}, near base ${near_base:04X}, far bank "
              f"${far_bank:02X}, main() returned {main_ret}, {calls} COP calls, "
              f"{bad} refused")
        check(status == APP_OK, f"app_load returned {status}")
        pool_lo, pool_hi = b.peek16(syms["app_pool_lo"]), b.peek16(syms["app_pool_hi"])
        check(pool_lo <= near_base < pool_hi and near_base & 0xFF == 0,
              f"near base ${near_base:04X} is not page-aligned inside the pool "
              f"${pool_lo:04X}-${pool_hi:04X}")
        top = b.peek(syms["_fl_top"]) | (b.peek16(syms["_fl_top"] + 1) << 8)
        check(far_bank > (top - 1) >> 16, f"far bank ${far_bank:02X} is not above "
              f"the image's top ${top:06X}")
        check(far_bank < 0x10, f"far bank ${far_bank:02X} is outside the first megabyte")

        # -- the application's own records --------------------------------------
        base = near_base - link_near
        ncalls = b.peek16(app["ncalls"] + base)
        seq = app_calls(0, 0)
        check(ncalls == len(seq), f"the application wrote {ncalls} records, expected {len(seq)}")
        ndos = b.peek16(app["ndos"] + base)

        # -- the COP that is not gem4xe's ----------------------------------------
        # Refused on the stock OS: counted as refused and not as a call, Y
        # untouched.  Passed to Rapidus OS: it never reaches gem_entry, and
        # the OS answers.  Either way the application's calls number the same.
        foreign = struct.unpack("<h", b.memdump(app["foreign"] + base, 2))[0]

        # objc_sysvar (AES 48), read straight out of the application's
        # words.  gem4xe draws no 3D objects, so ZERO is the answer and
        # not a placeholder: AD3DVALUE says how many pixels an object
        # needs each side for its 3D border, and cflib lays every dialog
        # out by it -- EmuTOS answers 2 there because it draws a
        # two-pixel border, and answering 2 here would reserve room for
        # something never painted (Compendium 6.121).
        sv = {n: struct.unpack("<h", b.memdump(app[n] + base, 2))[0]
              for n in ("sv_ad3d", "sv_ad3d1", "sv_ad3d2", "sv_lk3d",
                        "sv_lk3d1", "sv_lk3d2", "sv_col1", "sv_set",
                        "sv_junk")}
        print(f"  objc_sysvar: AD3DVALUE -> {sv['sv_ad3d']} ({sv['sv_ad3d1']},"
              f"{sv['sv_ad3d2']}), LK3DIND -> {sv['sv_lk3d']} "
              f"({sv['sv_lk3d1']},{sv['sv_lk3d2']}), INDBUTCOL {sv['sv_col1']}, "
              f"set {sv['sv_set']}, junk {sv['sv_junk']}")
        check(sv["sv_ad3d"] == 1 and sv["sv_ad3d1"] == 0 and sv["sv_ad3d2"] == 0,
              f"objc_sysvar(AD3DVALUE) answered {sv['sv_ad3d']} "
              f"({sv['sv_ad3d1']},{sv['sv_ad3d2']}); a system that draws no 3D "
              f"border needs no pixels for one, so it must succeed with 0,0")
        check(sv["sv_lk3d"] == 1 and sv["sv_lk3d1"] == 0 and sv["sv_lk3d2"] == 0,
              "objc_sysvar(LK3DIND) must succeed with 0,0: an indicator's text "
              "does not move here and its colour does not change")
        check(sv["sv_col1"] == 0,
              f"objc_sysvar(INDBUTCOL) answered colour {sv['sv_col1']}, not "
              f"white -- the ground an object is actually drawn on")
        check(sv["sv_set"] == 0,
              "objc_sysvar(SV_SET) must be REFUSED: there is nothing behind "
              "these settings to change")
        check(sv["sv_junk"] == 0,
              "objc_sysvar with a `which` outside the six must answer 0")

        # appl_find (AES 13), read the same way.  The runner named the
        # process after the file the shell installs this program as
        # (src/m3_vdi.c, op 4), so its own padded name must find it at
        # pid 0 -- and the UNPADDED spelling must not, because the
        # Compendium tells the caller to pad to eight and a real AES
        # compares over eight.  Softening that here would make a program
        # work on gem4xe and fail on an ST.
        af = {n: struct.unpack("<h", b.memdump(app[n] + base, 2))[0]
              for n in ("af_self", "af_short", "af_none")}
        print(f"  appl_find: \"M11     \" -> {af['af_self']}, \"M11\" -> "
              f"{af['af_short']}, \"NOSUCHPR\" -> {af['af_none']}")
        check(af["af_self"] == 0,
              f"appl_find(\"M11     \") answered {af['af_self']}, not 0: the "
              f"application is process 0 and that is the name it was loaded "
              f"under")
        check(af["af_short"] == -1,
              f"appl_find(\"M11\") answered {af['af_short']}, not -1: an "
              f"unpadded name must find nothing, as it does on an ST")
        check(af["af_none"] == -1,
              f"appl_find(\"NOSUCHPR\") answered {af['af_none']}, not -1")

        # appl_getinfo (AES 130), the same way.  These numbers are the
        # ones src/aes/appl.c commits to, each with the code that keeps
        # the promise named beside it there; what is checked here is that
        # the promise survives the shim's five-word copy-out, which is
        # wider than any other AES call gem4xe serves.
        def words(name):
            raw = b.memdump(app[name] + base, 10)
            return list(struct.unpack("<5h", bytes(raw)))
        font, shell, obj = words("ag_font"), words("ag_shell"), words("ag_obj")
        sysw = words("ag_sys")
        lang = struct.unpack("<h", b.memdump(app["ag_lang"] + base, 2))[0]
        junk = struct.unpack("<h", b.memdump(app["ag_junk"] + base, 2))[0]
        print(f"  appl_getinfo: font {font}, shell {shell}, object {obj}, "
              f"language {lang}, unknown {junk}")
        # The font cell, which is what a ported dialog lays itself out
        # with: the CELL HEIGHT in pixels, the system font's id, and
        # SYSTEM_FONT because it is a bitmap strip.  8 is this device's.
        check(font == [1, 8, 1, 0, 0],
              f"appl_getinfo(AES_LARGEFONT) answered {font}, not [1, 8, 1, 0, 0] "
              f"-- the cell height, the system font id, and a bitmap face")
        # shel_write's highest mode is 5; mode 0 cancels; mode 1 takes
        # effect when the running program exits; no ARGV.
        check(shell == [1, 5, 1, 1, 0],
              f"appl_getinfo(AES_SHELL) answered {shell}, not [1, 5, 1, 1, 0]")
        # No 3D objects, objc_sysvar present (this is the subject cflib's
        # obgframe.c branches on), no GDOS face in a TEDINFO.
        check(obj == [1, 0, 1, 0, 0],
              f"appl_getinfo(AES_OBJECT) answered {obj}, not [1, 0, 1, 0, 0]")
        # The resolution number is -1 BECAUSE THERE ISN'T ONE.  Every
        # value Getrez can answer names an Atari screen -- 0/1/2 the ST's,
        # 4/6/7 the TT's -- and gem4xe's are the VBXE's own (512, 640 or
        # 672 across).  The fact a caller wants is the next word: sixteen
        # colours on this device.  Then no colour icons (G_CICON draws its
        # mono form) and yes to the extended resource format.
        print(f"  appl_getinfo(AES_SYSTEM) -> {sysw}")
        check(sysw == [1, -1, 16, 0, 1],
              f"appl_getinfo(AES_SYSTEM) answered {sysw}, not [1, -1, 16, 0, 1] "
              f"-- -1 is 'not a screen Getrez names', and 16 is this device's "
              f"real colour count")
        # The language: this disk carries no LANG.RSC, so the built-in
        # strings are in use and the AES KNOWS it is English.  With a
        # file loaded it would refuse, because a LANG.RSC carries strings
        # and no identity -- so a 0 here means the gate's disk changed,
        # not that the answer is wrong.
        check(lang == 1,
              f"appl_getinfo(AES_LANGUAGE) answered {lang}, not 1 -- with no "
              f"LANG.RSC on the disk the AES knows the strings are English")
        # ...and the half of the contract that a call answering TRUE for
        # everything would pass anyway.
        check(junk == 0,
              f"appl_getinfo(99) answered {junk}, not 0: a subject this AES "
              f"does not know must be refused")

        # appl_yield (AES 17): somebody else's turn, and here there is
        # nobody else -- one program, no accessory.  So the two halves
        # worth pinning are that it ANSWERS (a call that waited for a
        # process which is never going to run would hang the gate instead
        # of failing it) and that it handed nothing over.  proc_turns is
        # the scheduler's own count of turns given away (src/aes/proc.c);
        # nothing in this whole run should have moved it.
        ay = struct.unpack("<h", b.memdump(app["ay_ret"] + base, 2))[0]
        turns = b.peek16(syms["proc_turns"])
        print(f"  appl_yield -> {ay}; the scheduler gave {turns} turns away")
        check(ay == 1, f"appl_yield answered {ay}, not 1")
        check(turns == 0,
              f"the scheduler handed {turns} turns over with one process "
              f"running -- proc_yield should find nobody to give one to")
        passed = b.peek(syms["gem_cop_pass"])
        want_foreign, want_bad, extra = ((FOREIGN_OS, 0, 0) if os_rom
                                         else (FOREIGN_REFUSED, 1, 0))
        print(f"  the foreign COP #$01: Y {foreign}, gem_cop_pass {passed}, {bad} refused")
        check(passed == (1 if os_rom else 0),
              f"gem_cop_pass is {passed}: abi_probe_os() read the OS wrong")
        check(foreign == want_foreign,
              f"the foreign COP left Y {foreign}, not {want_foreign}"
              + (": it did not reach the OS" if os_rom else ": gem4xe touched it"))
        check(bad == want_bad, f"the ABI refused {bad} call(s), not {want_bad}")
        check(main_ret == ncalls
              and calls == ncalls + ndos + extra + UNRECORDED_AES,
              f"main() returned {main_ret}, {ncalls} records, {ndos} GEMDOS "
              f"calls, {UNRECORDED_AES} unrecorded, {calls} COP calls: they "
              f"should reconcile")

        # -- GEMDOS through COP #$44 ------------------------------------------
        dosres = list(struct.unpack("<8h", b.memdump(app["dosres"] + base, 16)))
        # What Fsfirst/Fsnext should count: the entries a DOS 2 could be
        # handed (atr.Entry.nameable, the rule src/sys/dos.c lists by); the
        # fixture disk's dashed dividers are in use and are not files.
        files = [e.filename for e in atr.Dos2(atr.ATRImage.load(DISK)).entries()
                 if e.in_use and e.nameable]
        print(f"  GEMDOS: version ${dosres[0] & 0xFFFF:04X}, drive {dosres[1]}, "
              f"{dosres[2]} entries (image {len(files)}), Fsnext {dosres[3]}, "
              f"Fopen(missing) {dosres[4]}, {dosres[5]} banks free, DTA {dosres[6]}")
        check(dosres[0] == 0x1500, f"Sversion answered ${dosres[0] & 0xFFFF:04X}, not $1500")
        check(dosres[1] == 0, f"Dgetdrv answered {dosres[1]}, not A")
        check(dosres[2] == len(files), f"Fsfirst/Fsnext saw {dosres[2]} entries; "
              f"the image has {len(files)}")
        check(dosres[3] == -49, f"the search ended with {dosres[3]}, not ENMFIL")
        check(dosres[4] == -33, f"Fopen of a missing file answered {dosres[4]}, not EFILNF")
        check(dosres[5] >= 1, f"Malloc(-1) reports {dosres[5]} whole banks free")
        check(dosres[6] == 1, "Fgetdta did not answer the DTA Fsetdta was given")
        arec = vdiref.decode(b.memdump(app["results"] + base, ncalls * REC_WORDS * 2), ncalls)
        # what the application got back and went on to use
        hbox = arec[1][2 + 4] if ncalls > 1 else 0
        wh = arec[11][2] if ncalls > 11 else 0
        seq = app_calls(hbox, wh)

        mem = {}
        tree = read_tree(b, app["tree"] + base, 3, mem)
        mscript = PRELUDE + [rec for rec, _, _ in seq]
        plan = {len(PRELUDE) + TIMER_INDEX: [("frames", 30)]}
        ref_v, ref_a, want = aesref.run(mscript, tree, mem, plan=plan)
        for i, rec in enumerate(got[:len(PRELUDE)]):
            check(rec == want[i], f"runner call {i} returned {rec}, expected {want[i]}")
        for i, (rec, nout, ret) in enumerate(seq):
            w = abi_record(want[len(PRELUDE) + i], nout, ret)
            if i < ncalls and arec[i] != w:
                check(False, f"application call {i} (op {rec[0]}) recorded {arec[i]}, "
                             f"expected {w}")

        bad_px, shown = vbxeref.compare_to_shot(ref_v.to_rgb(), shot)
        check(not bad_px, f"{bad_px} px differ from the reference; first {shown[:3]}")
        if not fails and not keep:
            os.remove(shot)
    finally:
        emu.stop()

    print(f"gem4xe-m11: {'PASS' if not fails else 'FAIL'} -- the application ABI, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
