#!/usr/bin/env python3
"""The gem4xe distribution: what a tester is handed.

    tools/mkdist.py build/gem4xe-<stamp> [--tar out.tar.gz] [--zip out.zip]
                    [--public]

Four things, and a page that explains them:

  * the cartridge, which is the one that needs nothing else -- no DOS,
    no disk, nothing typed (docs/cartridge.md);
  * the bootable disks, when this tree has the DOS fixtures to build
    them (they are not always here, and the artefact says which are
    missing rather than pretending);
  * the system's own files, loose, for putting on a disk of somebody
    else's making;
  * the application kit (tools/mksdk.py), for writing something to run
    on it.

The page is generated, and that is the point of this tool rather than a
directory of `cp` rules.  Two of its sections are read out of the
program itself -- what the desktop's File and View menus offer, and
what they offer DISABLED -- so the honest half of "what works" cannot
drift from the resource; and the disks' contents are read back out of
the images with tools/atr.py, so what the page lists is what is on
them.  The cartridge is no exception: its directory is read back out of
the packed ROM (tools/mkcar.py, read_car), not restated from the recipe
that made it.

--public is the release (`make release`): the same, without the two
floppies that boot a DOS which is not gem4xe's to give away, and with
the page's few passages about them saying so instead.  The third floppy,
gem-sdx.atr, carries no DOS and travels in both.  --zip writes the same
tree as --tar does, for the people whose machine opens one and not the
other.
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr                                  # noqa: E402
import deskrsc                              # noqa: E402
import mkcar                                # noqa: E402
import mkcf                                 # noqa: E402
import mksdk                                # noqa: E402

BUILD = os.path.join(ROOT, "build")
TEMPLATE = os.path.join(ROOT, "tools", "dist", "README.md")

# One of the floppies boots a DOS that is not gem4xe's to give away
# (fixtures.toml.example: "a commercial or shareware Atari image you
# already have").  A build handed to a tester in the room carries it; the
# public release (--public, `make release`) does not, and its page says so
# and says how to make one.  The card image (tools/mkcf.py) and the two
# SDFS floppies (tools/mkfloppy.py) are built from this tree's own files
# and carry no DOS -- the SpartaDOS X they run under comes from the
# machine's own flash or cartridge -- so they travel in both.  A SpartaDOS
# 3.2 floppy, gem-sp.atr, was retired after phase 42: the installer is
# SpartaDOS X's.
THIRD_PARTY_DOS = {"gem-boot.atr"}

# (file in build/, where it goes, how it is read, what it says about itself)
DISKS = [
    ("gem4xe-sys.car", "gem4xe.car", "car",
     "**A cartridge, and the one file that needs nothing else.**  Put it "
     "on an Ultimate Cart, a MaxFlash or anything else that takes an "
     "AtariMax 1 Mbit image, turn the machine on, and the desktop comes "
     "up: no DOS, no disk, nothing typed.  Everything below is on it.\n\n"
     "It carries its own read-only `D1:` — a CIO handler over a "
     "directory in the ROM, which is what a DOS reduces to once nothing "
     "needs writing — so the system reaches its files the ordinary "
     "way and never learns where they came from.  The bootstrap finds a "
     "**Rapidus that has cold-booted as a 6502, switches it**, and loads "
     "`GEM.COM` off that `D1:` itself.\n\n"
     "Two things to know.  **Reading 165 KB out of the ROM through CIO "
     "takes about twenty-six seconds** — a Rapidus comes up with "
     "every window on the 1.79 MHz bus and nothing raises that until GEM "
     "is running — so it prints a dot per segment while it works; it "
     "has not hung.  And it is **read-only**, so *Options → Save "
     "desktop* and copying a file will tell you they cannot.  Everything "
     "else works, because nothing else writes.  It wants the same machine "
     "the rest of this does: a 65C816 and VBXE."),
    ("gem-boot.atr", "disks/gem-boot.atr", "dos2",
     "A double-density DOS 2 floppy, 180 KB.  GEM is AUTORUN.SYS, which "
     "this DOS runs at boot, and the DOS's own DUP.SYS is beside it, "
     "which is what GEM hands the machine back to when it quits.  The "
     "system and nothing else: a DOS 2 cannot read the applications "
     "floppy's directories, so this disk is for trying GEM rather than "
     "for keeping it, and its Desk menu holds only the About item."),
    ("gem-sdx.atr", "disks/gem-sdx.atr", "sdfs",
     "A double-sided double-density SDFS floppy, 360 KB, with **no DOS on "
     "it**: the system -- the card's `\\GEM\\`, without the desk "
     "accessory -- an `AUTOEXEC.BAT` that changes into `\\GEM\\` and runs "
     "GEM, and `INSTALL.BAT`.  It boots under **SpartaDOS X** -- from a "
     "cartridge or from Ultimate 1MB flash -- which is the one DOS that "
     "lives in the machine rather than on the disk, and that is why this "
     "floppy can be given away where the other two cannot.  Put it in D1: "
     "and turn the machine on.  Its other half is `disks/gem-apps.atr`."),
    ("gem-apps.atr", "disks/gem-apps.atr", "sdfs",
     "The applications: the calculator, the clock and a hello-world "
     "program in `\\APPS\\`, and the clock desk accessory in `\\GEM\\`, on "
     "the same 360 KB geometry with no DOS and nothing that boots.  Put it "
     "in a second drive beside a system disk and the desktop opens it "
     "there; its `INSTALL.BAT` puts it on your own drive beside the "
     "system.  An accessory is loaded from the system's own `\\GEM\\` "
     "when GEM starts, so the Clock is in the Desk menu once this disk "
     "is installed, not while it sits in a drive."),
    ("gem-cf.img", "disks/gem-cf.img", None,
     "A 16 MB CF card: an APT partition table and two SDFS partitions, "
     "with the system and the desk accessory in `\\GEM\\` and the "
     "applications in `\\APPS\\`. "
     "It carries no DOS \u2014 SpartaDOS X and the PBI BIOS that mounts "
     "the partitions both come from Ultimate 1MB flash \u2014 so this "
     "one wants a U1MB machine."),
]

# (file in build/, the name it takes on a disk)
SYSTEM = [
    ("gem.xex", "GEM.COM"),
    ("desktop.g4a", "DESKTOP.PRG"),
    ("desktop.rsc", "DESKTOP.RSC"),
    ("prefs.rsc", "PREFS.RSC"),
    ("lang.rsc", "LANG.RSC"),
    ("816.com", "816.COM"),
    ("gem4xe.cfg", "GEM4XE.CFG"),
    ("hello_app.g4a", "HELLO.PRG"),
    ("calc.g4a", "CALC.PRG"),
    ("calc.rsc", "CALC.RSC"),
    ("clock.g4a", "CLOCK.PRG"),
    ("clock.rsc", "CLOCK.RSC"),
    ("clockacc.g4a", "CLOCK.ACC"),
    ("cpanelacc.g4a", "CONTROL.ACC"),
    ("cpanel.rsc", "CPANEL.RSC"),
    ("calcacc.g4a", "CALC.ACC"),
    ("general.g4a", "GENERAL.CPX"),
    ("general.rsc", "GENERAL.RSC"),
]

WHAT_IT_IS = {
    "GEM.COM": "the system: the VDI, the AES, GEMDOS and the shell",
    "DESKTOP.PRG": "the desktop, which is an application like any other",
    "DESKTOP.RSC": "its resource -- the menu, the dialogs, the icons",
    "PREFS.RSC": "the Set preferences chooser, loaded only while it is open",
    "LANG.RSC": "what the system says, so a translation is a file",
    "816.COM": "puts a Rapidus into 65C816 mode by hand, if the loader "
               "somehow does not",
    "GEM4XE.CFG": "the screen and the mouse, in plain text -- edit it from "
                  "the DOS prompt if the display comes up wrong.  Ships "
                  "with everything commented out and documented",
    "HELLO.PRG": "a hello-world program: a window you open and close, "
                 "to have something to double-click",
    "CALC.PRG": "a calculator: whole numbers, and a division that "
                "truncates rather than pretending otherwise",
    "CALC.RSC": "its panel -- every key of it, and every word",
    "CLOCK.PRG": "a clock.  With an Ultimate 1MB it shows the time; "
                 "without one it counts up from midnight, which is what "
                 "the machine knows",
    "CLOCK.RSC": "its panel, and the templates that decide how a time "
                 "and a date are written",
    "CLOCK.ACC": "THE SAME CLOCK AS A DESK ACCESSORY.  Put it beside "
                 "GEM.COM, with CLOCK.RSC, and it appears in the Desk "
                 "menu: the AES loads it once at start-up and it stays "
                 "there, ticking, through every program the desktop runs. "
                 "An accessory goes in the system's own directory, never "
                 "in \\APPS\\ -- it is not something the desktop "
                 "launches",
    "CONTROL.ACC": "THE CONTROL PANEL, a desk accessory: the settings that "
                   "belong to the machine rather than to a program, and a "
                   "host for the extensions below.  Beside GEM.COM with "
                   "CPANEL.RSC",
    "CPANEL.RSC": "its panel and the list it shows the extensions in",
    "CALC.ACC": "the same calculator as a desk accessory, so it is "
                "reachable from inside whatever you are running.  It "
                "shares CALC.RSC with CALC.PRG",
    "GENERAL.CPX": "A CONTROL PANEL EXTENSION, the ST's .CPX: the "
                   "double-click speed, the menu delay, and the date and "
                   "time.  Put it beside GEM.COM with GENERAL.RSC and the "
                   "control panel grows a page -- the AES loads every "
                   "*.CPX it finds there and CONTROL.ACC lists them.  What "
                   "you set is saved and put back at the next boot",
    "GENERAL.RSC": "its dialog",
}


def stamp():
    """A name for this build: the date, and the commit if there is one."""
    day = datetime.date.today().isoformat()
    try:
        sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short",
                              "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                               capture_output=True, text=True,
                               check=True).stdout.strip()
        return f"{day}-{sha}" + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return day


def menu_items():
    """The desktop's menu, item by item, as the resource has it:
    (label, enabled).  NOT_YET is what the desktop disables at start."""
    r = deskrsc.build()
    first, _ = r.trees[deskrsc.ADMENU]
    items = []
    for idx in range(deskrsc.NOBS_MENU):
        o = r.objects[first + idx]
        s = getattr(o.spec, "s", None)
        if not isinstance(s, str) or not s.startswith("  ") or set(s) == {"-", " "}:
            continue
        items.append((idx, s.strip(), idx not in deskrsc.NOT_YET))
    return items


def bullets(items, want_enabled):
    out = []
    for _idx, label, enabled in items:
        if enabled == want_enabled:
            out.append(f"- **{label}**")
    return "\n".join(out)


def human(n):
    return f"{n / 1048576:.0f} MB" if n >= 1 << 20 else f"{n // 1024} KB"


def disk_section(src, dest, kind, prose):
    """One disk, with what is really on it read back out of the image."""
    lines = [f"### `{dest}` \u2014 {human(os.path.getsize(src))}",
             "", prose, ""]
    if kind == "dos2":
        fs = atr.Dos2(atr.ATRImage.load(src))
        names = sorted(e.filename for e in fs.entries() if e.in_use)
        free = fs.free_count()
        lines.append("Files: " + ", ".join(f"`{n}`" for n in names) + ".")
        lines.append("")
        lines.append(f"{free} sectors free — about {free * 253 // 1024} KB "
                     f"for programs of your own.")
    elif kind == "sdfs":
        fs = atr.Sdfs(atr.ATRImage.load(src))
        # the root, and what each directory on it holds, one level down:
        # the install layout is the point of these disks
        names = []
        for e in sorted(fs.entries(""), key=lambda e: (e.is_dir, e.filename)):
            if e.is_dir:
                inside = sorted(x.filename for x in fs.entries(e.filename))
                names.append(f"`{e.filename}\\` ("
                             + ", ".join(f"`{n}`" for n in inside) + ")")
            else:
                names.append(f"`{e.filename}`")
        free = fs.free_count()
        lines.append("Files: " + ", ".join(names) + ".")
        lines.append("")
        lines.append(f"{free} sectors free — about "
                     f"{free * (fs.secsize - 2) // 1024} KB.")
    elif kind == "car":
        ctype, ok, used, names = mkcar.read_car(
            src, os.path.join(BUILD, "cartd.elf"))
        if not ok:
            raise SystemExit(f"mkdist: {src}'s checksum is not the sum of its "
                             f"ROM, so an emulator will refuse the image")
        if ctype != mkcar.CART_TYPE_MAXFLASH_1M:
            raise SystemExit(f"mkdist: {src} is cartridge type {ctype}, not "
                             f"{mkcar.CART_TYPE_MAXFLASH_1M} (AtariMax 1 Mbit)")
        lines.append(f"Files, read out of the image's own directory: "
                     + ", ".join(f"`{n}`" for n in names) + ".")
        lines.append("")
        lines.append(f"{used} of {mkcar.BANKS} banks of "
                     f"{mkcar.BANK // 1024} KB used — room for about "
                     f"{(mkcar.BANKS - used) * mkcar.BANK // 1024} KB more.")
    return "\n".join(lines) + "\n"


def card_layout():
    """What goes in which directory of the card, read from the tool that
    builds it, so the page's install-by-hand recipe is the card's own."""
    dirs = {}
    for _path, name in mkcf.SYSTEM + mkcf.APPS:
        d, n = name.split(">")
        dirs.setdefault(d, []).append(n)
    return dirs


# The passages of the page that differ between the build handed to a
# tester (which has the floppies) and the public release (which has not).
# Everything else on the page is the same text.
TESTER = {
    "emu_disk": "--disk disks/gem-boot.atr",
    "emu_note": "",
    "install": (
        "**If you already have an APT drive**, do not write the card image "
        "over\nit.  `gem-sdx.atr` and `gem-apps.atr` each carry an "
        "`INSTALL.BAT` that\ncopies what the disk holds onto a drive you "
        "name.  At the SpartaDOS X\nprompt (quit GEM to get there), on the "
        "drive the floppy is in,\n`-INSTALL` and the drive to put it on --\n\n"
        "    -INSTALL D2:\n\n"
        "-- first with `gem-sdx.atr`, then with `gem-apps.atr`.  The "
        "system's gives\nthe drive an `AUTOEXEC.BAT` that starts GEM, "
        "unless it has one already,\nwhich is left alone.  Installing a "
        "newer gem4xe is the same again.\n\n"
        "If what you have is a **loader that reads FAT** -- a SIDE3, an "
        "AVGCART\n-- or an SDrive-MAX, a FujiNet or a real drive, then the "
        "floppies are\nwhat you want: copy `gem-sdx.atr` (SpartaDOS X in "
        "the machine) or\n`gem-boot.atr` (DOS 2) onto the card you already "
        "have and load it like\nanything else.  `docs/media.md` in the "
        "source tree has the whole matrix\nand the reasoning."),
    "dosnote": (
        "**The DOS on each disk image is not gem4xe's**, and is there so "
        "that the\ndisk boots.  Whoever owns it owns it; the images are for "
        "trying this\nout, not for redistribution."),
}


def public_text():
    """The same passages for the release, wrapped here because two of
    them carry lists read out of tools/mkcf.py."""
    layout = card_layout()
    gemdir = ", ".join(f"`{n}`" for n in layout["GEM"])
    appsdir = ", ".join(f"`{n}`" for n in layout["APPS"])
    boot = " and ".join(f"`{line}`" for line in mkcf.BOOT)
    fill = lambda t: textwrap.fill(t, 72)  # noqa: E731
    return {
        "emu_disk": "--cart gem4xe.car",
        "emu_note": fill(
            "That is the whole of it: `gem4xe.car` needs no disk and no "
            "DOS.  For the floppies instead, `--cart SDX.car --disk "
            "disks/gem-sdx.atr` -- `disks/gem-sdx.atr` carries no DOS "
            "(*What is in the download*, below) and boots under SpartaDOS "
            "X, and `SDX.car` is a SpartaDOS X cartridge image, which this "
            "download does not include: the SpartaDOS X Upgrade Project "
            "offers one for emulators at <https://sdx.atari8.info/>, and "
            "Altirra reads it as it is.  Without one, make a disk of your "
            "own: a bootable SpartaDOS 3.2 or DOS 2 disk with the files in "
            "`system/` on it, started at boot the way *Booting* describes "
            "or by hand from the DOS prompt, and `--disk` that "
            "instead.") + "\n",
        "install": fill(
            "**If you already have an APT drive**, do not write the card "
            "image over it.  `gem-sdx.atr` and `gem-apps.atr` each carry "
            "an `INSTALL.BAT` that copies what the disk holds onto a drive "
            "you name.  At the SpartaDOS X prompt (quit GEM to get there), "
            "on the drive the floppy is in, `-INSTALL` and the drive to put "
            "it on --") +
            "\n\n    -INSTALL D2:\n\n" + fill(
            f"-- first with `gem-sdx.atr`, then with `gem-apps.atr`.  The "
            f"system's gives the drive an `AUTOEXEC.BAT` of two lines, "
            f"{boot}, unless it has one already, which is left alone; "
            f"installing a newer gem4xe is the same again.  Or by hand "
            f"from `system/`, the way the card has them: {gemdir} into "
            f"`\\GEM\\`; {appsdir} into `\\APPS\\`.") + "\n\n" + fill(
            "If what you have is a **loader that reads FAT** -- a SIDE3, an "
            "AVGCART -- or an SDrive-MAX, a FujiNet or a real drive, then "
            "a floppy is what you want.  On a machine that runs SpartaDOS "
            "X -- a cartridge, or an Ultimate 1MB with it in flash -- that "
            "is `gem-sdx.atr`: copy it onto the card you already have and "
            "load it like anything else.  On one that does not, put the "
            "files in `system/` on a DOS 2 or SpartaDOS disk of your own "
            "-- this download carries no such disk, because it would boot "
            "a DOS that is not gem4xe's to give away; from the source "
            "tree, `make dist` builds the DOS 2 one, given your DOS image "
            "in `fixtures.toml` -- and `docs/media.md` there has the whole "
            "matrix and the reasoning."),
        "dosnote": fill(
            "**No disk in this download carries a DOS.**  The card image "
            "and `gem-sdx.atr` run under the SpartaDOS X in your machine "
            "-- Ultimate 1MB flash or a cartridge -- and the floppy `make "
            "dist` also builds, `gem-boot.atr`, is not here because it "
            "boots a DOS that is not gem4xe's to give away."),
    }


def build(out, tar=None, require_clean=False, public=False, zip_path=None):
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    made, missing, left_out = [], [], []

    for src, dest, kind, prose in DISKS:
        p = os.path.join(BUILD, src)
        if public and src in THIRD_PARTY_DOS:
            left_out.append(dest)
            continue
        if not os.path.isfile(p):
            missing.append((dest, src))
            continue
        d = os.path.join(out, dest)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(p, d)
        made.append(disk_section(p, dest, kind, prose))

    sysrows = ["| file | | |", "|---|---|---|"]
    for src, name in SYSTEM:
        p = os.path.join(BUILD, src)
        if not os.path.isfile(p):
            raise SystemExit(f"mkdist: build/{src} is not built")
        os.makedirs(os.path.join(out, "system"), exist_ok=True)
        shutil.copyfile(p, os.path.join(out, "system", name))
        sysrows.append(f"| `{name}` | {os.path.getsize(p):,} bytes | "
                       f"{WHAT_IT_IS[name]} |")

    mksdk.build(os.path.join(out, "sdk", "gem4xe-sdk"),
                os.path.join(out, "sdk", "gem4xe-sdk.tar.gz"))
    shutil.rmtree(os.path.join(out, "sdk", "gem4xe-sdk"))
    shutil.copyfile(os.path.join(ROOT, "COPYING"),
                    os.path.join(out, "COPYING"))

    # THE SOURCE TRAVELS WITH THE BINARIES, because the GPL says it must
    # and because there is nowhere else to point: section 3 wants the
    # source alongside or a written offer, and a URL is neither.
    # `git archive` is exactly what is committed, so the tarball and the
    # stamp in this page's title describe the same tree.
    src_tar = os.path.join(out, "src", "gem4xe-src.tar.gz")
    os.makedirs(os.path.dirname(src_tar), exist_ok=True)
    # A DIRTY TREE CANNOT BE RELEASED.  `git archive` writes what is
    # COMMITTED, so on a dirty tree the tarball would not be the source
    # these binaries were built from -- which is the one thing it exists
    # to be.  `make all` and the individual disk targets are what to use
    # mid-change; this one wants a commit.
    if require_clean and stamp().endswith("-dirty"):
        raise SystemExit(
            "mkdist: the working tree has uncommitted changes, so the "
            "source tarball would not match the binaries beside it.  "
            "Commit first (docs/licence.md, 'the source travels with the "
            "binaries'), or build the disks on their own with `make all`.")
    ident = "gem4xe-" + stamp()
    r = subprocess.run(["git", "archive", "--format=tar.gz",
                        f"--prefix={ident}/", "HEAD"],
                       cwd=ROOT, capture_output=True)
    if r.returncode:
        raise SystemExit("mkdist: git archive failed: "
                         + r.stderr.decode("utf-8", "replace")[:300])
    with open(src_tar, "wb") as f:
        f.write(r.stdout)

    # ...and the version on its own, so a tester who has unpacked the
    # folder and forgotten where it came from can still quote one.  BOTH
    # numbers, because they answer different questions: the release is
    # what the About box shows and what a human says out loud, and the
    # date and commit are what identifies the build exactly.
    with open(os.path.join(out, "VERSION"), "w") as f:
        f.write(f"{deskrsc.VERSION} ({stamp()})\n")

    disks = "\n".join(made)
    if missing:
        disks += ("\n" + "\n".join(
            f"*(`{d}` is not in this build: `build/{s}` was not made — it "
            f"needs a DOS image this tree did not have.)*"
            for d, s in missing) + "\n")
    if left_out:
        disks += ("\n*(" + " and ".join(f"`{d}`" for d in left_out)
                  + ", which `make dist` also builds, is not in this "
                  "download: it boots a DOS that is not gem4xe's to "
                  "give away.  `disks/gem-sdx.atr` and `disks/gem-apps.atr` "
                  "carry none, which is why they are here; *On real "
                  "storage*, above, says how to "
                  "make one of the others from `system/`.)*\n")

    items = menu_items()
    with open(TEMPLATE) as f:
        page = f.read()
    page = page.format(version=deskrsc.VERSION, stamp=stamp(), disks=disks,
                       system="\n".join(sysrows),
                       works=bullets(items, True),
                       notyet=bullets(items, False),
                       **(public_text() if public else TESTER))
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(page)

    if tar:
        with tarfile.open(tar, "w:gz") as t:
            t.add(out, arcname=os.path.basename(out))
    # The same tree as a zip, for Windows, where a .tar.gz is a second
    # program away.  Directory entries are left out, and the members are
    # sorted so two builds of the same tree zip alike.
    if zip_path:
        base = os.path.basename(out)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for dirpath, dirnames, filenames in os.walk(out):
                dirnames.sort()
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    z.write(full, os.path.join(base, os.path.relpath(full, out)))
    return made, missing


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--tar")
    ap.add_argument("--zip", help="the same tree as a zip, for Windows")
    ap.add_argument("--public", action="store_true",
                    help="the release: without the floppies that boot a "
                         "DOS which is not gem4xe's to give away")
    a = ap.parse_args(argv[1:])
    made, missing = build(a.out, a.tar, require_clean=True, public=a.public,
                          zip_path=a.zip)
    print(f"{a.out}: {len(made)} disk(s), {len(SYSTEM)} system files, "
          f"the kit and the page"
          + (f"; {len(missing)} disk(s) not built" if missing else "")
          + ("; the DOS-bearing floppies left out" if a.public else "")
          + (f"; {a.tar}" if a.tar else "")
          + (f"; {a.zip}" if a.zip else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
