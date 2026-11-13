#!/usr/bin/env python3
"""Phase 161 gate: MyDOS's folders through GEMDOS.

MyDOS 4.x has folders -- DOS 2's file system with subdirectories -- and
gem4xe treated it as a flat DOS 2 until now.  build/m15m-boot.atr is the
MyDOS 4.50T fixture with the runner on it, loaded from MyDOS's DUP as
test-m15 loads it from DOS 2's; the calls are made through the runner as
test-m15 makes them:

  Dcaps            folders, and a folder renamed in place -- never moved
  Dcreate          a folder, and one inside it
  Fsfirst          the root lists the folder as a folder
  Fcreate/Fwrite   a file in it, read back; Dsetpath into it, and a bare
                   name opened there; Dgetpath says where
  Frename          a file renamed in its folder; to another folder EACCDN;
                   a folder renamed
  Ddelete          refused for a folder with files in it; REFUSED FOR A
                   FILE'S NAME, the file still there -- MyDOS removes a
                   folder with the same call that deletes a file; done for
                   an empty one
Then the emulator's working copy, read with tools/atr.py, which reads
MyDOS's folders now: KEEP a folder with K.TXT in it, NEWDIR gone,
TEST.TXT still there.

    python3 tests/emu/m66_mydos.py
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from m7_form import STATUS, SYMS              # noqa: E402
from m12_file import Runner                   # noqa: E402
import m15_gdos as m15                        # noqa: E402
from m15_gdos import Gdos, W, L, BUF, BUF_ROOM, FA_SUBDIR, HANDLE_BASE  # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m15m-boot.atr"))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test.txt")
TAG = "m66"
DC_FOLDERS, DC_RENDIR, DC_MOVE = 1, 2, 4
EPTHNF, EACCDN = -34, -36
problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def boot(b):
    """MyDOS boots to its DUP; L M3 loads the runner, which switches the
    65C816 on and waits."""
    b.frames(300)
    b.poke(0xD1FF, 0x01)
    b.poke(0xD191, 0x00)
    b.frames(500)
    for k in ("L", "M", "3", "RETURN"):
        b.key(k)
        b.frames(10)
    for _ in range(300):
        st = bytes(b.memdump(STATUS, 14))
        if st[:2] == b"VD" and st[2] == 1:
            return st
        b.frames(4)
    return None


def main():
    print("gem4xe-m66: MyDOS's folders through GEMDOS")
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m66-")
    disk = os.path.join(work, "m.atr")
    shutil.copy(DISK, disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for(TAG), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    emu = launch(tag=TAG, memsize="1088K", extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        if not check(boot(b) is not None, "the runner came up from MyDOS's DUP"):
            return 1
        r = Runner(b, syms)
        g = Gdos(r, check)
        g.call("Fsetdta", L(r.sc + m15.DTA))

        def call(name, *args):
            return g.call(name, *args)[0]

        def s(path, slot=0):
            return L(g.string(path, slot))

        caps = call("Dcaps", W(1))
        check(caps == DC_FOLDERS | DC_RENDIR,
              f"Dcaps on MyDOS: {caps:#x}, wanted folders and folder rename, no moves")
        check(call("Dcreate", s("A:\\NEWDIR")) == 0, "Dcreate A:\\NEWDIR")
        check(call("Dcreate", s("A:\\NEWDIR\\DEEP")) == 0, "Dcreate A:\\NEWDIR\\DEEP")
        got, _ = g.listing("A:\\*.*", FA_SUBDIR)
        check("NEWDIR" in got and got["NEWDIR"]["attr"] & FA_SUBDIR,
              f"the root lists NEWDIR as a folder: {sorted(got)}")
        print(f"  Dcaps {caps:#x}; NEWDIR and NEWDIR\\DEEP made; the root lists "
              f"{len(got)} entries, NEWDIR a folder")

        data = open(FIXTURE, "rb").read()
        h = call("Fcreate", s("A:\\NEWDIR\\A.TXT"), W(0))
        if check(h >= HANDLE_BASE, f"Fcreate A:\\NEWDIR\\A.TXT: {h}"):
            r.stage(BUF, data)
            n = call("Fwrite", W(h), L(len(data)), L(r.sc + BUF))
            check(n == len(data), f"Fwrite into the folder: {n}")
            call("Fclose", W(h))
        check(call("Dsetpath", s("\\NEWDIR")) == 0, "Dsetpath \\NEWDIR")
        call("Dgetpath", L(r.sc + BUF), W(0))
        where = r.read(BUF, 16).split(b"\0")[0]
        check(where == b"\\NEWDIR", f"Dgetpath: {where!r}")
        h = call("Fopen", s("A.TXT"), W(0))
        if check(h >= HANDLE_BASE, f"Fopen A.TXT, a bare name, in \\NEWDIR: {h}"):
            n = call("Fread", W(h), L(BUF_ROOM), L(r.sc + BUF))
            check(n == len(data) and r.read(BUF, n) == data,
                  f"A.TXT read back {n} bytes, wrote {len(data)}")
            call("Fclose", W(h))
        call("Dsetpath", s("\\"))
        got, _ = g.listing("A:\\NEWDIR\\*.*", FA_SUBDIR)
        check(sorted(got) == ["A.TXT", "DEEP"], f"NEWDIR lists {sorted(got)}")
        print("  A.TXT written into NEWDIR; Dsetpath there, a bare name opened and "
              "read back; NEWDIR lists A.TXT and DEEP")

        rn = call("Frename", W(0), s("A:\\NEWDIR\\A.TXT"), s("A:\\NEWDIR\\B.TXT", 1))
        check(rn == 0, f"Frename A.TXT to B.TXT in its folder: {rn}")
        check(call("Frename", W(0), s("A:\\NEWDIR\\B.TXT"), s("A:\\B.TXT", 1)) == EACCDN,
              "Frename to another folder: MyDOS renames in place, EACCDN")
        rn = call("Frename", W(0), s("A:\\NEWDIR\\DEEP"), s("A:\\NEWDIR\\DEEPER", 1))
        check(rn == 0, f"Frename a folder, DEEP to DEEPER: {rn}")
        got, _ = g.listing("A:\\NEWDIR\\*.*", FA_SUBDIR)
        check(sorted(got) == ["B.TXT", "DEEPER"], f"after the renames NEWDIR lists {sorted(got)}")
        print("  B.TXT renamed in place, refused to another folder, DEEP renamed DEEPER")

        r1 = call("Ddelete", s("A:\\NEWDIR"))
        check(r1 < 0, f"Ddelete of NEWDIR with files in it: {r1}, not refused")
        r2 = call("Ddelete", s("A:\\TEST.TXT"))
        check(r2 == EPTHNF, f"Ddelete of a FILE's name, TEST.TXT: {r2}, wanted EPTHNF")
        h = call("Fopen", s("A:\\TEST.TXT"), W(0))
        check(h >= HANDLE_BASE, "TEST.TXT is gone after Ddelete was asked for it")
        if h >= HANDLE_BASE:
            call("Fclose", W(h))
        check(call("Fdelete", s("A:\\NEWDIR\\B.TXT")) == 0, "Fdelete B.TXT")
        check(call("Ddelete", s("A:\\NEWDIR\\DEEPER")) == 0, "Ddelete the empty DEEPER")
        check(call("Ddelete", s("A:\\NEWDIR")) == 0, "Ddelete NEWDIR, empty now")
        print(f"  Ddelete: refused for a full folder ({r1}) and for a file's name "
              f"({r2}), the file kept; done for empty folders")

        check(call("Dcreate", s("A:\\KEEP")) == 0, "Dcreate A:\\KEEP")
        h = call("Fcreate", s("A:\\KEEP\\K.TXT"), W(0))
        if check(h >= HANDLE_BASE, f"Fcreate A:\\KEEP\\K.TXT: {h}"):
            r.stage(BUF, b"kept\x9b")
            call("Fwrite", W(h), L(5), L(r.sc + BUF))
            call("Fclose", W(h))
    finally:
        emu.stop()

    written = os.path.join(state, "disk.atr")
    if check(os.path.exists(written), "the emulator wrote no working copy"):
        fs = atr.Dos2(atr.ATRImage.load(written))
        dirs = sorted(e.filename for e in fs.entries() if e.is_dir)
        check(dirs == ["KEEP"], f"the root's folders: {dirs}, wanted KEEP alone")
        check(fs.find("TEST.TXT") is not None, "TEST.TXT is not on the disk")
        k = fs.find("KEEP>K.TXT")
        check(k is not None and fs.read("KEEP>K.TXT") == b"kept\x9b",
              "KEEP>K.TXT is not on the disk as written")
        print(f"  the disk: folders {dirs}, KEEP>K.TXT as written, TEST.TXT kept")
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m66: {'PASS' if not problems else 'FAIL'} -- MyDOS's folders "
          f"through GEMDOS, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
