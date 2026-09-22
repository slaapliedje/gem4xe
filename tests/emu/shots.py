#!/usr/bin/env python3
"""The pictures: the product booted and used, photographed for the README
and the release page.

Not a gate.  Nothing here is compared with anything; the pictures are
for people, and a person looks at them.  What it shares with the gates
is the machine and the way it is driven: the tester's install disk
boots into the desktop with nothing typed, exactly as tests/emu/
product_boot.py has it, and the pointer is then walked and clicked by
the same steps test-m23 and test-m28 use.  The disk is that floppy
without the gate program on it (build/gem-shots.atr): \\APPS\\ is
photographed, and M11.PRG is the tests' business.  Where things are on
the screen is read out of the TARGET -- the desktop's own screen tree,
the AES's menu tree and window frame, a dialog's tree once it is up --
so the tour does not carry coordinates that go stale the day a
resource is edited.

The product has an ST mouse on the joystick port and there is no verb
in the bridge to move one, so the pointer's kind is set to NONE after
the boot: from then on the pointer record is the harness's to write,
as it is in the gates' builds (src/vdi/pointer.c ptr_poll).  That is
the one poke this makes into the running product.

What is photographed, in order:

  boot        the boot screen, the hardware found, while it is held
  desk        the desk as it comes up
  window      a window on A:\\*.*, at its full size
  menu-desk   the Desk drop-down, with the accessory in it
  menu-file   the File drop-down
  about       Desk -> About
  folder      the APPS folder opened
  info        File -> Show Info on the calculator
  text        View -> Text, the same folder as lines
  calc        the calculator, with something in its display
  clock       the clock accessory, over the desktop

Each picture is the overlay alone (the 16-pixel borders cropped) with
its rows doubled: 640x240 is what the VBXE puts out and 640x480 is what
a 4:3 monitor makes of it.

  python3 tests/emu/shots.py [-o docs/shots] [--disk build/gem-shots.atr]
"""
import argparse
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile                              # noqa: E402
from aesref import W_FULLER, OBJ_SIZE, G_ICON   # noqa: E402
from deskref import g_offset, DROOT, WOBS_START   # noqa: E402
from deskrsc import (THEBAR, THEACTIVE, THEDROPS,           # noqa: E402
                     DESKMENU, FILEMENU, VIEWMENU,
                     DESKBOX, ABOUITEM, FILEBOX, SHOWITEM,
                     VIEWBOX, ICONITEM, TEXTITEM,
                     DEOK, FICNCL)
from calcrsc import (C1, C2, C3, C4, C5, C6, CMUL, CEQ, CQUIT)   # noqa: E402
from m7_form import (poke16, apply_step, F, M, B, K, CLICK,   # noqa: E402
                     DCLICK, RETURN)
from m14_sparta import screen               # noqa: E402
from m17_desktop import (header, DESKTOP, DESK_SYM,   # noqa: E402
                         desk_g, desk_places)
from demo_aes import path                   # noqa: E402
from product_boot import REFUSAL, STEP, BOOT_WAIT, boot_screen   # noqa: E402

BUILD = os.path.join(ROOT, "build")
# What the tour wrote, beside the pictures: see Tour.manifest.
MANIFEST = "MANIFEST"
# The boot screen is photographed before the Tour exists -- it happens
# while the machine is still coming up -- so it is outside the shot
# numbering and has to be named in one place for both of them.
BOOT_SHOT = "00-boot.png"
SYMS = os.path.join(BUILD, "gem.sym")
CALC = os.path.join(BUILD, "calc.g4a")
CALC_SYM = os.path.join(BUILD, "calc.sym")
DISK = os.path.join(BUILD, "gem-shots.atr")
OUT = os.path.join(ROOT, "docs", "shots")

NIL = -1
PTR_NONE = 0                    # src/vdi/pointer.h
BORDER = 16                     # the overlay's column in a 672-wide shot
FOLDER, PROGRAM = "APPS", "CALC.PRG"
# The accessories' lines in the Desk box start at ABOUITEM + 2 (deskrsc:
# the one between is the separator), but nothing here counts from it any
# more -- Tour.desk_acc finds an accessory by the NAME it registered, so
# adding one does not quietly re-aim the pictures at a different one.
SUM = [C1, C2, C3, C4, CMUL, C5, C6, CEQ]      # 1234 x 56


def obj(b, tree, i):
    """One OBJECT out of the target, as the AES has it in memory."""
    d = bytes(b.memdump(tree + i * OBJ_SIZE, OBJ_SIZE))
    (nxt, head, tail, typ, flags, state, spec,
     x, y, w, h) = struct.unpack("<hhhHHHIhhhh", d)
    return dict(next=nxt, head=head, tail=tail, type=typ, flags=flags,
                state=state, spec=spec, x=x, y=y, w=w, h=h)


def children(b, tree, parent):
    out, i = [], obj(b, tree, parent)["head"]
    while i != NIL and i != parent and len(out) < 64:
        out.append(i)
        i = obj(b, tree, i)["next"]
    return out


# An object tree is a handful deep -- the desk, a window, its items.  The
# bound is not tidiness: read a tree from the WRONG ADDRESS and the
# nonsense there has cycles, and this used to follow them until Python ran
# out of stack and raised RecursionError from inside the bridge's JSON
# decode, which names neither the tree nor the address.  That is what a
# far G looked like to a gate that still expected a near one.
MAX_TREE_DEPTH = 12

# The Extensions list's first row, and the Open button, in the Control
# Panel as form_center places it.
#
# MEASURED OFF docs/shots/10-cpanel.png AND HALVED, which is the part
# that is easy to get wrong: publish() crops the border and DOUBLES THE
# ROWS, so a y read off a published picture is twice the y the pointer
# wants.  The first attempt clicked at the published number, missed both
# objects, and produced a picture of the panel doing nothing -- which
# looked like a broken feature rather than a wrong coordinate.
CPX_ROW1 = (270, 125)
CPX_ROW2 = (270, 133)           # a row is one 8-pixel cell below the last
CPX_OPEN = (403, 125)


def placed(b, tree, root=0):
    """{obj: (x, y, w, h)} on the screen, for every object under root."""
    out = {}

    def walk(i, ox, oy, depth):
        if depth > MAX_TREE_DEPTH:
            raise RecursionError(
                f"object tree at ${tree:06X} is more than {MAX_TREE_DEPTH} "
                f"deep at object {i} -- it is almost certainly not a tree: "
                f"check the address (a large-data program's G is in FAR "
                f"memory, m17_desktop.desk_g)")
        o = obj(b, tree, i)
        x, y = ox + o["x"], oy + o["y"]
        out[i] = (x, y, o["w"], o["h"])
        for c in children(b, tree, i):
            walk(c, x, y, depth + 1)
    walk(root, 0, 0, 0)
    return out


def middle(r):
    return (r[0] + r[2] // 2, r[1] + r[3] // 2)


def cstring(b, addr, n=13):
    d = bytes(b.memdump(addr, n))
    return d.split(b"\0", 1)[0].decode("latin-1")


class Tour:
    def __init__(self, b, syms, out):
        self.b, self.syms, self.out = b, syms, out
        self.ptr = syms["ptr_state"]
        self.dlink, _, _ = header(DESKTOP)
        self.dsym = symfile.load(DESK_SYM)
        self.clink, _, _ = header(CALC)
        self.csym = symfile.load(CALC_SYM)
        self.n = 0
        # The boot screen is already written by the time a Tour is
        # made (main, below), and it is a picture this owns too.
        self.wrote = [BOOT_SHOT]

    # -- driving -----------------------------------------------------------
    def here(self):
        return (self.b.peek16(self.ptr), self.b.peek16(self.ptr + 2))

    def run(self, steps):
        for st in steps:
            apply_step(self.b, self.ptr, st)

    def go(self, xy):
        self.run([F(2)] + path(self.here(), xy) + [F(4)])

    def click(self, xy):
        self.go(xy)
        self.run(CLICK())
        self.settle()

    def dclick(self, xy):
        self.go(xy)
        self.run(DCLICK(xy))
        self.settle()

    def settle(self, limit=1500):
        """Until the program has made no call for thirty frames."""
        calls = self.syms["app_calls"]
        n, still = self.b.peek16(calls), 0
        for _ in range(0, limit, 10):
            self.b.frames(10)
            now = self.b.peek16(calls)
            still = still + 1 if now == n else 0
            n = now
            if still >= 3:
                return
        print("  (still busy)")

    def shot(self, name):
        self.n += 1
        raw = os.path.join(BUILD, "shots", f"tour-{name}.png")
        self.b.frames(2)
        self.b.screenshot(raw)
        base = f"{self.n:02d}-{name}.png"
        fn = os.path.join(self.out, base)
        publish(raw, fn)
        self.wrote.append(base)
        print(f"  {fn}")

    def manifest(self):
        """What this tour wrote, in order, beside the pictures.

        THE TOUR HAS TO SAY THIS ITSELF.  The names are numbered by the
        order the shots happen in, and one of them is not even a literal
        -- the accessory loop names its shot after the accessory -- so
        nothing can work the list out by reading this file.  Inserting a
        picture renumbers every one after it, which has now happened
        twice and left four superseded PNGs checked in both times; a
        stale picture RENDERS, so it is worse than a broken link.

        tools/readme.py reads this and says which files in docs/shots
        are no longer written and which the README still points at."""
        p = os.path.join(self.out, MANIFEST)
        with open(p, "w") as f:
            f.write("# written by tests/emu/shots.py -- do not edit\n")
            f.write("".join(s + "\n" for s in self.wrote))
        stale = sorted(n for n in os.listdir(self.out)
                       if n.endswith(".png") and n not in set(self.wrote))
        for n in stale:
            print(f"  STALE: {n} is checked in and the tour no longer "
                  f"writes it")
        return stale

    # -- where things are ----------------------------------------------------
    def G(self):
        """The desktop's G, wherever the loader put it this time -- far bss
        for a large-data build, which is what it is since its resource went
        far (src/sys/app.c exports app_far for exactly this)."""
        return desk_g(self.b, self.syms)

    def g_screen(self):
        return self.G() + g_offset("g_screen")

    def tree_of(self, field):
        """peek24: a_menu and its kind are FAR pointers now -- the
        resource they point into is in far memory."""
        return self.b.peek24(self.G() + g_offset(field))

    def desk_icon(self, label):
        """A drive or the trash: the desk's own children."""
        tree = self.g_screen()
        rects = placed(self.b, tree)
        for i in children(self.b, tree, DROOT):
            if i < WOBS_START:
                continue
            if cstring(self.b, obj(self.b, tree, i)["spec"] + 34) == label:
                return middle(rects[i])
        raise KeyError(label)

    def item(self, name):
        """An entry of the window on top, by its label (an icon's, at
        SCREENINFO.i.label, or the start of a text view's line)."""
        tree = self.g_screen()
        rects = placed(self.b, tree)
        # the window roots are ROOT's children beside the desk (deskobj.c
        # obj_init), ordered as they are stacked: the last with anything
        # in it is the window on top
        seen = []
        for top in reversed(children(self.b, tree, 0)):
            if top == DROOT or not children(self.b, tree, top):
                continue
            for i in children(self.b, tree, top):
                o = obj(self.b, tree, i)
                text = (cstring(self.b, o["spec"] + 34) if o["type"] & 0xFF == G_ICON
                        else cstring(self.b, o["spec"], 48))
                seen.append(text.strip())
                if text.strip().startswith(name):
                    return middle(rects[i])
            break
        raise KeyError(f"{name} is not in the window on top: {seen}")

    def gadget(self, which):
        """A gadget of the window on top, as W_ACTIVE was last laid out."""
        rects = placed(self.b, self.syms["W_ACTIVE"])
        return middle(rects[which])

    def menu(self, title, item=None):
        """The middle of a title of the bar, and of an item in its
        drop-down: the item's y under the title's x, straight down."""
        # peek24: gl_mntree is an OBJECT FAR * into the desktop's
        # resource, which is in far memory (src/aes/rsrc.c)
        tree = self.b.peek24(self.syms["gl_mntree"])
        rects = placed(self.b, tree)
        t = middle(rects[title])
        if item is None:
            return t
        return (t[0], middle(rects[item])[1])

    def desk_acc(self, name):
        """An accessory's item in the Desk menu, BY NAME.

        Not by index.  The items were ACC_ITEM and ACC_ITEM + 1 while there
        were two accessories, and a third (the calculator, 2026-09-20)
        shifted nothing but silently left the newcomer unphotographed --
        the tour went on picking the first two and looked fine.  The AES
        writes each accessory's title into the Desk box's children as it
        registers (src/aes/menu.c menu_fixup), so the name is readable
        where the picture will show it.
        """
        tree = self.b.peek24(self.syms["gl_mntree"])
        themenus = obj(self.b, tree, 0)["tail"]
        dabox = obj(self.b, tree, themenus)["head"]
        seen = []
        for i in children(self.b, tree, dabox):
            text = cstring(self.b, obj(self.b, tree, i)["spec"], 32).strip()
            seen.append(text)
            if text == name:
                return i
        raise KeyError(f"{name!r} is not in the Desk menu: {seen}")

    def dialog(self, field, which):
        """An object of one of the desktop's dialogs, once it is up."""
        rects = placed(self.b, self.tree_of(field))
        return middle(rects[which])

    def drop(self, title):
        """Hover the title until its menu is down."""
        self.go(self.menu(title))
        self.b.frames(10)

    def choose(self, title, item):
        self.drop(title)
        self.run(path(self.here(), self.menu(title, item), speed=4) + [F(6)])
        self.run(CLICK())
        self.settle()

    def launch(self, act, what, up=None):
        """act() starts a program: wait until the shell has run one more,
        until up() says it is showing, then until it is idle.  The shell
        counts the run before the program's main(), and a load is disk
        time with no AES calls in it, so app_calls alone settles too
        early."""
        runs = self.b.peek16(self.syms["sh_runs"])
        act()
        for _ in range(300):
            if self.b.peek16(self.syms["sh_runs"]) != runs and (up is None or up()):
                break
            self.b.frames(10)
        else:
            self.shot("fail")
            raise SystemExit(f"{what} never started")
        self.settle()

    def bar_up(self):
        return self.b.peek24(self.syms["gl_mntree"]) != 0

    def cancel_menu(self):
        # a click on the desk, well away from the bar, takes the menu up
        self.click((600, 150))


def publish(raw, fn):
    """The overlay alone, rows doubled, as an indexed PNG."""
    from PIL import Image
    im = Image.open(raw).convert("RGB")
    im = im.crop((BORDER, 0, BORDER + 640, im.height))
    im = im.resize((im.width, im.height * 2), Image.NEAREST)
    colours = im.getcolors(256)
    if colours:
        pal = Image.new("P", (1, 1))
        flat = [c for _, rgb in colours for c in rgb]
        pal.putpalette(flat + [0] * (768 - len(flat)))
        im = im.quantize(palette=pal, dither=Image.NONE)
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    im.save(fn, optimize=True)


def boot(b, syms, out):
    """The disk to the desk, as product_boot.py waits for it: the loader
    switches the CPU, the DOS starts GEM again, the boot screen is held
    and photographed, the desktop settles."""
    b.ok("COLD_RESET")
    for t in range(0, 20000, STEP):
        b.frames(STEP)
        if b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502":
            break
    else:
        raise SystemExit("the loader never switched the CPU")
    print(f"  the CPU switched {t + STEP} frames in")
    # the boot screen is on E:, complete once its hint is up, and held
    # for three seconds: the first picture, before the desk's numbering
    for t in range(0, BOOT_WAIT, STEP):
        b.frames(STEP)
        if boot_screen(b):
            break
    else:
        raise SystemExit("the boot screen never showed its hint")
    raw = os.path.join(BUILD, "shots", "tour-boot.png")
    b.screenshot(raw)
    fn = os.path.join(out, BOOT_SHOT)
    publish(raw, fn)
    print(f"  {fn}")
    calls = syms["app_calls"]
    n, still = b.peek16(calls), 0
    for t in range(0, 20000, 250):
        b.frames(250)
        now = b.peek16(calls)
        still = still + 1 if now == n else 0
        n = now
        if still >= 2 and now:
            break
    else:
        raise SystemExit(f"GEM never settled ({n} calls)")
    if any(REFUSAL in ln for ln in screen(b)):
        raise SystemExit("GEM refused the 65C816")
    print(f"  the desk after {t + 250} frames, {n} calls in")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", default=OUT)
    ap.add_argument("--disk", default=DISK)
    args = ap.parse_args(argv[1:])
    syms = symfile.load(SYMS)

    # Absolute: the emulator does not run in this directory, and a
    # relative path fails inside it as "Cannot open file" and a boot
    # that never switches the CPU.
    disk = os.path.abspath(args.disk)
    emu = launch(tag="shots", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, args.out)
        # the pointer is ours now (src/vdi/pointer.c: PTR_NONE polls nothing)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, args.out)
        b.frames(10)
        t.shot("desk")

        t.dclick(t.desk_icon("DISK A"))
        t.click(t.gadget(W_FULLER))
        t.go((400, 150))
        t.shot("window")

        t.drop(DESKMENU)
        t.shot("menu-desk")
        t.go(t.menu(FILEMENU))
        b.frames(10)
        t.shot("menu-file")
        t.cancel_menu()

        t.choose(DESKMENU, ABOUITEM)
        t.go((400, 200))
        t.shot("about")
        t.click(t.dialog("a_info", DEOK))

        t.dclick(t.item(FOLDER))
        t.go((400, 150))
        t.shot("folder")

        t.click(t.item(PROGRAM))
        t.choose(FILEMENU, SHOWITEM)
        t.go((400, 200))
        t.shot("info")
        t.click(t.dialog("a_finfo", FICNCL))

        t.choose(VIEWMENU, TEXTITEM)
        t.go((400, 200))
        t.shot("text")
        t.choose(VIEWMENU, ICONITEM)

        t.launch(lambda: t.dclick(t.item(PROGRAM)), "the calculator")
        tree = b.peek16(t.csym["tree"] + b.peek16(syms["app_near"]) - t.clink)
        keys = placed(b, tree)
        for k in SUM:
            t.go(middle(keys[k]))
            t.run(CLICK())
            b.frames(10)
        t.go((400, 220))
        t.shot("calc")
        t.launch(lambda: t.click(middle(keys[CQUIT])), "the desktop", t.bar_up)

        # Each accessory in turn, BY NAME (desk_acc) rather than by the
        # index it happened to have when there were two of them.  RETURN
        # puts a form away: OK is the DEFAULT button, so no coordinate
        # arithmetic is needed and the next one can have the screen.
        for name, shot in (("Control Panel", "cpanel"),
                           ("Calculator", "calc-acc")):
            t.choose(DESKMENU, t.desk_acc(name))
            b.frames(60)
            t.go((400, 200))
            b.frames(30)
            t.shot(shot)
            if name == "Control Panel":
                # ...and one of its extensions, opened.  THE POINT OF THE
                # WHOLE SHAPE: the panel lists what the AES loaded and
                # calls that module's cpx_call, so what appears next is a
                # dialog belonging to a separately linked file the panel
                # has never heard of.
                #
                # The two places clicked are MEASURED off the panel's own
                # picture (10-cpanel.png) rather than read out of its
                # tree: the panel is an accessory, so its objects are in
                # its own memory and reaching them wants symbols and a
                # near base this tour does not carry.  That is a fair
                # trade here because the PICTURE is the check -- if the
                # layout moves, 11-general-cpx.png shows the wrong thing
                # instead of passing quietly.
                t.click(CPX_ROW1)
                b.frames(20)
                t.click(CPX_OPEN)
                b.frames(60)
                t.go((400, 200))
                b.frames(30)
                t.shot("general-cpx")
                t.run([K("RETURN", RETURN), F(40)])   # the module's OK
                # ...and the second module, which is the OTHER kind: an
                # EVENT CPX.  It draws itself, returns 1, and the panel
                # then drives it -- so what is photographed here is a
                # module being fed events by a host that owns the loop,
                # which is the half of the contract GENERAL does not use.
                # Any key closes it, which is what the module's cpx_key
                # does with the `quit` it is given.
                t.click(CPX_ROW2)
                b.frames(20)
                t.click(CPX_OPEN)
                b.frames(60)
                t.go((400, 200))
                b.frames(30)
                t.shot("event-cpx")
                # The key does two things: the module puts up one of the
                # PANEL'S canned alerts through XGen_Alert and then asks
                # to be closed.  The alert is worth a picture because it
                # is the one part of the XCPB a module cannot fake --
                # those words are in CPANEL.RSC, not in the module, so
                # what is on the screen is the host speaking on the
                # module's behalf.  Its one button is the default, so a
                # second RETURN takes it away.
                t.run([K("RETURN", RETURN), F(40)])
                t.shot("cpx-alert")
                t.run([K("RETURN", RETURN), F(40)])   # ...and it closes
            t.run([K("RETURN", RETURN), F(40)])

        # The clock last: it has no default button and ends on a key.
        t.choose(DESKMENU, t.desk_acc("Clock"))
        b.frames(60)
        t.go((400, 200))
        b.frames(60)
        t.shot("clock")
    finally:
        emu.stop()
    # ...and what it wrote, so a renumbering cannot leave a superseded
    # picture behind it (Tour.manifest).
    return 1 if t.manifest() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
