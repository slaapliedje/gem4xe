#!/usr/bin/env python3
"""LANG.RSC: the system's own text comes off the disk, and a translation
is a file.

form_error is the call that proves it.  An application gives it a DOS
error number and nothing else -- no string -- so every character that
reaches the screen came from the system: from LANG.RSC if the disk has
one, and from the copy in the far image if it has not (src/aes/lang.c).

Three disks, one script:

    m20-en.atr    the product's own LANG.RSC, as `make` builds it
    m20-de.atr    a translation: every string replaced, longer than the
                  English, the error number moved to the end of its alert
    m20-none.atr  no LANG.RSC at all -- the built-in English
    m20-xde.atr, -xfr.atr, -xes.atr   the German, French and Spanish
                  translations that ship, accents and all

The first and the third must draw the same pixels, because the file and
the fallback are the same bytes; the second must draw the translation,
which is what says the file is being read rather than ignored.  Each is
compared with tools/aesref.py's fm_error given the strings that disk
carries, so nothing here asserts a text by eye.

The error numbers are 5 -- which picks a fixed alert -- and 63, which
picks the one carrying the number, written over the two characters after
its '#'.  63 is the case a translation can break and the only rule it
must keep, so the German fixture moves the phrase to prove the target
searches for the '#' rather than counting to it.

  python3 tests/emu/m20_lang.py [--shot]
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, atr, langrsc, symfile, vbxeref   # noqa: E402
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m7_form import CLICK, F, K, STATUS, SYMS, compare   # noqa: E402
from aesref import RETURN                   # noqa: E402
from m12_file import Runner, run_planned    # noqa: E402
from m13_alert import SETTLE, alloc         # noqa: E402

BUILD = os.path.join(ROOT, "build")
DISK = os.path.join(BUILD, "m3-boot.atr")
FORM_ERROR = aesref.FORM_ERROR
ERRORS = (5, 63)                            # a fixed alert, and the numbered one

# The translation, and the two rules tools/langrsc.py asks of one: the
# form_alert grammar, and one '#' with two characters after it.  Every
# string differs from the English, so a screen that still says the
# English is a screen the file never reached.
GERMAN = [(name, "[1][Diese Meldung kommt aus LANG.RSC|"
                 + ("in der Uebersetzung|Fehler Nummer #00" if name == "ERRTOS"
                    else "und ist nicht die englische|" + name.title())
                 + "][ Weiter ]")
          for name, _ in langrsc.STRINGS]

# The translations that ship (phase 96), each in the bytes its font draws.
# German, French and Spanish are in the Atari ST set the linked font has,
# so the model draws them as it draws the English; Polish needs the
# Latin-2 font beside it and is held to its rules in tests/host/test_lang.py.
def shipped(lang):
    t = langrsc.TRANSLATIONS[lang]
    return [(n, langrsc.encode(t[n], lang).decode("latin-1"))
            for n, _ in langrsc.STRINGS]


# (tag, what the disk carries, the strings the model should speak)
DISKS = [("en", langrsc.STRINGS, langrsc.STRINGS),
         ("de", GERMAN, GERMAN),
         ("none", None, langrsc.STRINGS)] + [
        (f"x{lang}", shipped(lang), shipped(lang)) for lang in ("de", "fr", "es")]


def make_disk(tag, strings):
    """A copy of the runner's disk with LANG.RSC replaced, or removed."""
    out = os.path.join(BUILD, f"m20-{tag}.atr")
    img = atr.ATRImage.load(DISK)
    fs = atr.open_fs(img)
    if any(e.filename.upper() == langrsc.FILENAME for e in fs.entries()
           if e.in_use):
        fs.delete(langrsc.FILENAME)
    if strings is not None:
        fs.add_file(langrsc.FILENAME, langrsc.build(strings).file())
    img.save(out)
    return out


def buttons_of(script, strings, mark, pointer):
    """Where the model puts the alert's buttons, which is the only way to
    know where to click: dismissed with RETURN, since a plan that clicks
    has to know the answer first (m13_alert.button_rect)."""
    steps = [F(SETTLE), K("RETURN", RETURN)]
    _, a, _ = aesref.run(script, [], {}, plan={len(PRELUDE): steps},
                         pointer=pointer, pool=mark, lang=strings)
    return a.alert_buttons


def one(tag, on_disk, speaks, keep, check):
    disk = make_disk(tag, on_disk)
    syms = symfile.load(SYMS)
    print(f"{os.path.basename(disk)}: "
          + ("no LANG.RSC" if on_disk is None
             else f"LANG.RSC, {len(langrsc.build(on_disk).file())} bytes"))
    emu = launch(tag=f"m20{tag}", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        st = b""
        for _ in range(200):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            check(False, f"{tag}: the runner did not come up")
            return
        r = Runner(b, syms)
        ptr = syms["ptr_state"]
        r.run(PRELUDE)
        mark, _ = alloc(r)
        for n in ERRORS:
            script = PRELUDE + [(FORM_ERROR, (), (n,))]
            pointer = (b.peek16(ptr), b.peek16(ptr + 2))
            # Where the OK button lands is the model's to say, and it can
            # only say it once it has built the tree: run it once to find
            # the button, then again with the click on it.
            rect = buttons_of(script, speaks, mark, pointer)[0]
            mid = (rect.x + rect.w // 2, rect.y + rect.h // 2)
            shots = []

            def take(bridge, shots=shots, n=n):
                p = os.path.join(SHOTDIR, f"m20-{tag}-{n:02d}.png")
                bridge.screenshot(p)
                shots.append(p)

            steps = [F(SETTLE), ("shot", take)] + CLICK(mid)[:-1]
            plan = {len(PRELUDE): steps}
            ref_v, ref_a, want = aesref.run(
                script, [], {}, plan={k: list(v) for k, v in plan.items()},
                pointer=pointer, pool=mark, lang=speaks)
            err, recs = run_planned(r, ptr, script, plan)
            if not err:
                err = compare(b, r.results, len(recs), script, want)
            if not err and len(shots) != len(ref_a.shots):
                err = f"{len(shots)} shots taken, the model has {len(ref_a.shots)}"
            if not err:
                for rgb, path in zip(ref_a.shots, shots):
                    bad, shown = vbxeref.compare_to_shot(rgb, path)
                    if bad:
                        err = f"{bad} px differ from the model; first {shown[:3]}"
                        break
            for p in shots:
                if os.path.exists(p) and not keep and not err:
                    os.remove(p)
            check(not err, f"{tag}: form_error({n}): {err}")
            print(f"  form_error({n:2d}) {'ok' if not err else 'FAIL'}"
                  f"   {speaks[0][1][:34] if n != 63 else '#' + str(n)}")
    finally:
        emu.stop()


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    os.makedirs(SHOTDIR, exist_ok=True)
    for tag, on_disk, speaks in DISKS:
        one(tag, on_disk, speaks, keep, check)
    print(f"gem4xe-m20: {'PASS' if not fails else 'FAIL'} -- LANG.RSC, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
