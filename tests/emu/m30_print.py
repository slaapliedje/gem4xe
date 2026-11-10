#!/usr/bin/env python3
"""Phase 36 gate: the VDI on the printer, and the page off the machine.

The THIRD device through src/vdi/vdidev.h's seam and the first that is
not a screen.  The same src/vdi/vdi.c that draws on the VBXE in test-m3
and on ANTIC in test-m25 draws 640 x 800 dots into far memory here, and
src/vdi/emit.c writes them out through v_updwk as PCL 5 and PostScript.

THERE IS NOTHING TO PHOTOGRAPH, so this gate is checked from the FILES
THE ATARI WROTE.  They land in a host directory by way of Altirra's H:
device, which is what PRINTTO= would name on a machine with a FujiNet,
and then:

  * the PCL is decoded back to a page -- PCL 5 raster is lossless and
    tools/emitref.py's decoder is strict enough to have caught the bug --
    and compared with tools/vdiref.py driving tools/devref.py's Printer,
    all 512,000 dots of it;
  * the PCL is also compared BYTE FOR BYTE with the model's, so the
    blank-row skip and the escape sequences are pinned and not merely
    plausible;
  * the PostScript is handed to GHOSTSCRIPT, rendered at 100 dpi, and
    the bitmap that comes back is compared with the same page.  That is
    the only honest check of a program written in a language that has an
    interpreter: it catches the y-flip, the DeviceGray inversion and the
    image matrix, none of which fails visibly and all of which would be
    discovered on paper otherwise.

Neither model was written for a printer and neither was edited for one.
"""
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                  # noqa: E402
import devref                               # noqa: E402
import emitref as E                         # noqa: E402
import vdiref                               # noqa: E402
from vdiref import (V_OPNWK, V_GTEXT, V_PLINE, VR_RECFL, VSF_COLOR, VRO_CPYFM,  # noqa: E402
                    VSF_INTERIOR, VSL_COLOR, VST_COLOR, VSWR_MODE, WORK_IN)
from m14_sparta import type_line, wait_prompt, screen    # noqa: E402
CONFIG_DIR = config_dir_for("m30")          # this run's own (see m19)

SRC_DISK = os.path.abspath(os.path.join(ROOT, "build", "m30-boot.atr"))
DISK = os.path.abspath(os.path.join(ROOT, "build", "m30-run.atr"))
STATUS = 0x0600
FIS_SOLID, MD_REPLACE, MD_XOR = 1, 1, 3
PR_W, PR_H = E.PR_W, E.PR_H
GS = shutil.which("gs")


def text(x, y, s):
    return (V_GTEXT, (x, y), tuple(ord(c) for c in s))


# src/m30_print.c's calls, in its order.  A rule across the head and the
# foot so the last row and both ends of a row are covered, a short mark
# at each edge somewhere the rules are not, a block whose ends are at
# neither end of a byte, a hole XORed in it, two lines of text one of
# them at an odd x, and a diagonal -- the one primitive no blitter ever
# helped with and which here has no blitter at all.  MOST OF THE PAGE IS
# LEFT BLANK on purpose: a border down the sides would put ink in all 800
# rows and leave the PCL's blank-row skip untested, which is the one
# thing about it that could stop working and still print.
SCRIPT = [
    (V_OPNWK, (), WORK_IN),
    (VSF_COLOR, (), (1,)),
    (VSF_INTERIOR, (), (FIS_SOLID,)),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VR_RECFL, (0, 0, PR_W - 1, 2), ()),
    (VR_RECFL, (0, PR_H - 3, PR_W - 1, PR_H - 1), ()),
    (VR_RECFL, (0, 400, 2, 420), ()),
    (VR_RECFL, (PR_W - 3, 400, PR_W - 1, 420), ()),
    (VR_RECFL, (37, 60, 122, 140), ()),
    (VSWR_MODE, (), (MD_XOR,)),
    (VR_RECFL, (60, 80, 100, 120), ()),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VST_COLOR, (), (1,)),
    text(24, 200, "GEM4XE -- 640 x 800 DOTS AT 100 DPI"),
    text(25, 216, "...AND THE SAME LINE AT AN ODD X."),
    (VSL_COLOR, (), (1,)),
    (V_PLINE, (300, 300, 420, 340), ()),
    # vro_cpyfm's logic modes on the page (phase 142): S XOR D over the
    # text, NOT S beside it, at odd x
    (VRO_CPYFM, (37, 60, 122, 140, 41, 190, 126, 270), (6,)),
    (VRO_CPYFM, (37, 60, 122, 140, 201, 190, 286, 270), (12,)),
]


def model():
    """The page, as the models have it.  One argument changed from the
    two screen gates: the device."""
    v = vdiref.VDI(dev=devref.Printer())
    v.run(SCRIPT)
    return bytes(v.dev.a.mem)


def fresh_disk():
    """A copy of the built disk, and the emulator's own working copy of
    it dropped, so the run starts from the fixture as built and its
    writes land somewhere the gate can find them (m19_files)."""
    shutil.copyfile(SRC_DISK, DISK)
    with open(DISK, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    state = os.path.join(CONFIG_DIR, "disk_state", sha)
    if os.path.isdir(state):
        shutil.rmtree(state)
    return os.path.join(state, "disk.atr")


def render(ps, x0=76, y0=108):
    """Ghostscript, told to put the BoundingBox's corner on the origin
    and draw 640x800 at 100 dpi -- one device pixel on each of the page's
    dots.  pbmraw writes 1 for black and a 1 in the page means ink, so
    the bits come back in the polarity they went in."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "p.ps"), os.path.join(d, "p.pbm")
        with open(src, "wb") as f:
            f.write(ps)
        r = subprocess.run(
            [GS, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pbmraw",
             "-r100", "-g%dx%d" % (PR_W, PR_H), "-sOutputFile=" + out,
             "-c", "%d %d translate" % (-x0, -y0), "-f", src],
            capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode("latin-1")[:400])
        with open(out, "rb") as f:
            d = f.read()
    i, fields = 0, []
    while len(fields) < 3:
        while d[i:i + 1].isspace():
            i += 1
        if d[i:i + 1] == b"#":              # gs stamps one in
            while d[i:i + 1] not in (b"\n", b""):
                i += 1
            continue
        j = i
        while not d[j:j + 1].isspace():
            j += 1
        fields.append(d[i:j])
        i = j
    if fields != [b"P4", b"%d" % PR_W, b"%d" % PR_H]:
        raise RuntimeError("gs gave back %r" % fields)
    return d[i + 1:]


def differ(a, b):
    """Where two pages first disagree, in dots rather than bytes."""
    out = []
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            d = a[i] ^ b[i]
            for bit in range(8):
                if d & (0x80 >> bit):
                    out.append(((i % E.PR_STRIDE) * 8 + bit, i // E.PR_STRIDE))
                    if len(out) >= 4:
                        return out
    return out


def main(argv):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    want = model()
    ink = sum(bin(b).count("1") for b in want)
    print(f"  the model's page: {ink:,} dots of {PR_W * PR_H:,}")

    written = fresh_disk()
    # --bootrw: the writes go to the image rather than to a scratch copy
    # the gate would never see (m19_files).
    emu = launch(tag="m30", memsize="1088K", vbxe=False,
                 extra_args=["--bootrw", "--disk", DISK])
    b = emu.bridge
    try:
        t = wait_prompt(b, limit=4000)
        if not check(t >= 0, "SpartaDOS never reached its prompt"):
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  the DOS prompt after {t} frames on the 6502")
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)                # -> 65C816 (resets; DOS reboots)
        b.frames(100)
        t = wait_prompt(b, limit=4000)
        if not check(t >= 0, "SpartaDOS did not come back on the 65816"):
            return 1
        print(f"  and after {t + 100} frames on the 65816")
        type_line(b, "M30")

        # src/m30_print.c leaves a progress mark at STATUS[4]: f probed
        # the far heap, p took the page, w opened the workstation, r and
        # t drew, l is about to write the PCL, P has, S has written the
        # PostScript too.  A gate that finds the machine stopped can then
        # say WHERE, which on a device with nothing to photograph is the
        # only thing standing in for a screenshot.
        mark, last = b"", None
        for _ in range(0, 24000, 100):
            b.frames(100)
            st = bytes(b.memdump(STATUS, 5))
            if st[4:5] != last:
                last = st[4:5]
                mark += last
            if st[:3] == b"AVK":
                break
        st = bytes(b.memdump(STATUS, 5))
        if not check(st[:3] == b"AVK",
                     f"the milestone did not finish: it stopped at "
                     f"{st[4:5]!r}, having reached {mark!r}"):
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "65C816", f"CPU is {cpu}")
        print(f"  the VDI opened a workstation on the printer, {cpu}, "
              f"no VBXE in the machine")
        b.frames(120)                       # let SpartaDOS flush
    finally:
        emu.stop()

    # -- what the Atari wrote ------------------------------------------
    if not check(os.path.exists(written),
                 f"the emulator wrote no working copy at {written}"):
        return 1
    fs = atr.Sdfs(atr.ATRImage.load(written))
    names = {e.filename.upper() for e in fs.entries("")}
    if not check({"PAGE.PCL", "PAGE.PS"} <= names,
                 f"the disk holds {sorted(names)}, not both pages"):
        return 1
    pcl = fs.read("PAGE.PCL")
    ps = fs.read("PAGE.PS")
    print(f"  the Atari wrote {len(pcl):,} bytes of PCL and {len(ps):,} "
          f"of PostScript")

    # -- PCL, decoded back to a page -----------------------------------
    try:
        got = E.from_pcl(pcl)
    except ValueError as e:
        check(False, f"the PCL will not decode: {e}")
        got = None
    if got is not None:
        check(got == want,
              f"the decoded page differs from the model at dots "
              f"{differ(got, want)}")
        if got == want:
            print(f"  the PCL decodes to the model's page, all "
                  f"{PR_W * PR_H:,} dots")
    check(pcl == E.pcl(want),
          f"the PCL is not the model's byte for byte: {len(pcl)} bytes "
          f"against {len(E.pcl(want))}, first difference at "
          f"{next((i for i in range(min(len(pcl), len(E.pcl(want)))) if pcl[i] != E.pcl(want)[i]), None)}")
    check(len(pcl) < E.PR_BYTES // 2,
          f"{len(pcl):,} bytes of PCL for a page that is mostly paper -- "
          f"the blank-row skip is not skipping")

    # -- PostScript, through Ghostscript -------------------------------
    check(ps == E.ps(want), "the PostScript is not the model's byte for byte")
    if not GS:
        print("  (ghostscript not installed: the PostScript was not rendered)")
    else:
        try:
            shot = render(ps)
        except RuntimeError as e:
            check(False, f"ghostscript would not render the page: {e}")
            shot = None
        if shot is not None:
            check(shot == want,
                  f"ghostscript's rendering differs from the model at dots "
                  f"{differ(shot, want)}")
            if shot == want:
                print(f"  ghostscript renders the PostScript back to the "
                      f"same {PR_W * PR_H:,} dots")

    ok = not fails
    print(f"gem4xe-m30: {'PASS' if ok else 'FAIL'} -- the VDI on the "
          f"printer, {len(fails)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
