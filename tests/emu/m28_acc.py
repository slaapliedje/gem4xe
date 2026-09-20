#!/usr/bin/env python3
"""Phase 36 gate: a desk accessory, resident beside the desktop.

test-m27 proved two contexts can take turns on one engine stack.  This is
the first time that buys anything: M28.ACC is a second PROGRAM, loaded
before the desktop, registering a name in the Desk menu and then sitting
in the message loop a desk accessory never leaves -- while the desktop
runs above it and answers the mouse.

WHAT IT CHECKS, and why each one is here rather than a picture:

  IT LOADED, AND BEFORE THE DESKTOP.  sh_naccs counts what started;
  sh_accfull counts what was found and had no room.  The order is what
  makes the pool's wind-back work in our favour -- an accessory taken
  before the first program is below the desktop's mark, so every return
  to the desktop leaves it standing (src/aes/shel.c).

  IT REGISTERED, AND THE AES KEPT THE POINTER AND NOT A COPY.  The gate
  derives the accessory's near base from gl_acctitle[0] -- the address
  the AES is holding -- and the offset acc_title has in the accessory's
  own link.  If the AES had copied the string, that arithmetic would land
  nowhere and every symbol read afterwards would be nonsense; the fact
  that acc_id and acc_menu then read as sensible values is the proof.

  THE DESK MENU GREW.  The tree is read out of the target through the
  AES's own gl_mntree: the Desk box must have exactly three children now
  (About, the separator, the name), the third one's ob_spec must BE the
  registered pointer, and the box must be three lines high.  That is
  exactly what menu_fixup() does, checked against the object tree rather
  than against a screenshot -- a picture would also pass with the height
  wrong by a pixel.

  IT IS ACTUALLY RUNNING.  The accessory counts its own timer waits.  The
  gate reads that counter, lets the machine run with the desktop up, and
  requires it to have ADVANCED.  A co-residency that only looked right in
  the menu would fail here, and this is the check the whole phase exists
  for.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, symfile                      # noqa: E402
from deskrsc import FILEMENU, QUITITEM      # noqa: E402
from m7_form import (poke16, apply_step, NOT_STARTED, STATUS, ST_GO,  # noqa: E402
                     F, M, B)
from demo_aes import path                   # noqa: E402
from m4_aes import PRELUDE                  # noqa: E402
from m12_file import Runner                 # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL                 # noqa: E402
from m17_desktop import SYMS, header        # noqa: E402  (m3desk's symbols)

DISK = os.path.abspath(os.path.join(ROOT, "build", "m28-boot.atr"))
ACC = os.path.join(ROOT, "build", "m28_acc.g4a")
ACC_SYM = os.path.join(ROOT, "build", "m28_acc.sym")

OB_SIZE = 24                    # aesref.Object: "<hhhHHHIhhhh"
NIL = -1
# The objects every menu tree has in these positions (src/aes/aes.h).
THESCREEN, THEBAR, THEACTIVE, THEDESK = 0, 1, 2, 3
AC_OPEN, AC_CLOSE = 40, 41


def words(b, addr, n):
    """n consecutive WORDs out of the target."""
    d = bytes(b.memdump(addr, 2 * n))
    return [d[2 * i] | (d[2 * i + 1] << 8) for i in range(n)]


def obj(b, tree, i):
    """One OBJECT out of the target, as the AES has it in memory."""
    d = bytes(b.memdump(tree + i * OB_SIZE, OB_SIZE))
    (nxt, head, tail, typ, flags, state, spec,
     x, y, w, h) = struct.unpack("<hhhHHHIhhhh", d)
    return dict(next=nxt, head=head, tail=tail, type=typ, flags=flags,
                state=state, spec=spec, x=x, y=y, w=w, h=h)


def main(argv):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    asym = symfile.load(ACC_SYM)
    link_near, _near_size, _ = header(ACC)

    emu = launch(tag="m28", memsize="1088K", extra_args=["--disk", DISK])
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

        # The shell: it loads the accessories, then the desktop.
        stage = PRELUDE + [(SHELL, (), ())]
        script = aesref.encode(stage, 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in script))
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)

        # Wait for the desktop to be up: sh_runs counts the programs the
        # shell has started, and the desktop is the first.
        runs = syms["sh_runs"]
        for _ in range(0, 4000, 10):
            b.frames(10)
            if b.peek16(runs) >= 1 and b.peek24(syms["gl_mntree"]):
                break
        check(b.peek16(runs) >= 1, "the shell never started the desktop")
        b.frames(120)

        # 1. it loaded, and nothing was turned away
        naccs = b.peek16(syms["sh_naccs"])
        full = b.peek16(syms["sh_accfull"])
        check(naccs == 1, f"{naccs} accessories started, expected 1")
        check(full == 0, f"{full} accessory/ies found with no room for them")
        nproc = b.peek16(syms["proc_n"])
        check(nproc == 2, f"{nproc} processes, expected 2")
        print(f"  {naccs} accessory started, {nproc} processes")

        # 2. it registered, and the AES kept ITS pointer
        reg = b.peek16(syms["gl_accreg"])
        title = b.peek24(syms["gl_acctitle"])
        check(reg == 1, f"{reg} names registered, expected 1")
        if not check(title != 0, "the AES holds no title pointer"):
            return 1
        near = title - (asym["acc_title"] - link_near)
        acc = {n: asym[n] + near - link_near
               for n in ("acc_id", "acc_menu", "acc_ticks", "acc_msgs",
                         "acc_opens", "acc_closes", "acc_last", "acc_ws",
                         "acc_find", "acc_findapp", "acc_yields")}
        acc_id, acc_menu = b.peek16(acc["acc_id"]), b.peek16(acc["acc_menu"])
        check(acc_id == 1, f"the accessory's ap_id is {acc_id}, expected 1")
        check(acc_menu == 0, f"its menu id is {acc_menu}, expected slot 0")
        want = b"  Gate accessory\x00"
        got = bytes(b.memdump(title, len(want)))
        check(got == want, f"the title reads {got!r}, expected {want!r}")
        print(f"  registered '{want[:-1].decode().strip()}' as slot {acc_menu}, "
              f"ap_id {acc_id}; its near region is at ${near:04X}")

        # 3. the Desk drop-down grew by a separator and a name
        # peek24: gl_mntree is an OBJECT FAR *, and the desktop's menu
        # tree is in its resource -- which is in FAR memory since the
        # desktop became a large-data program (src/aes/rsrc.c).
        mntree = b.peek24(syms["gl_mntree"])
        if not check(mntree != 0, "the desktop has installed no menu bar"):
            return 1
        themenus = obj(b, mntree, 0)["tail"]
        dabox = obj(b, mntree, themenus)["head"]
        # GEM's tree is right-threaded: the LAST child's ob_next is the
        # parent, not NIL.  Walking for NIL runs on into the next box.
        kids = []
        i = obj(b, mntree, dabox)["head"]
        while i != NIL and i != dabox and len(kids) < 10:
            kids.append(i)
            i = obj(b, mntree, i)["next"]
        check(kids == [dabox + 1, dabox + 2, dabox + 3],
              f"the Desk box's children are {kids}, expected "
              f"{[dabox + 1, dabox + 2, dabox + 3]}")
        if len(kids) == 3:
            spec = obj(b, mntree, kids[2])["spec"]
            check(spec == title,
                  f"the accessory's item points at ${spec:06X}, not the "
                  f"registered ${title:04X}")
        hchar = b.peek16(syms["gl_hchar"])
        box_h = obj(b, mntree, dabox)["h"]
        check(box_h == 3 * hchar,
              f"the Desk box is {box_h} tall, expected 3 lines of {hchar}")
        print(f"  the Desk drop-down: {len(kids)} items, {box_h} px "
              f"({box_h // hchar} lines of {hchar})")

        # 4. chosen from the Desk menu: AC_OPEN, to the right process,
        #    with the words the donor puts in them.  The coordinates come
        #    out of the TARGET's own tree rather than from a model, since
        #    what is being checked is the dispatch and not the layout.
        def absxy(chain):
            x = y = 0
            for i in chain:
                o = obj(b, mntree, i)
                x += o["x"]
                y += o["y"]
            return x, y

        def centre(chain):
            o = obj(b, mntree, chain[-1])
            x, y = absxy(chain)
            return x + o["w"] // 2, y + o["h"] // 2

        title_xy = centre([THEBAR, THEACTIVE, THEDESK])
        item_xy = centre([themenus, dabox, kids[2]])
        # Straight down from the title into its drop-down: a slant would
        # cross the next title first and drop that menu instead.
        item_xy = (title_xy[0], item_xy[1])
        print(f"  the Desk title at {title_xy}, the accessory's item at "
              f"{item_xy}")
        here = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        steps = ([F(3)] + path(here, title_xy) + [F(10)]
                 + path(title_xy, item_xy, speed=4) + [F(10), B(1), F(14),
                                                       B(0), F(20)])
        for st_ in steps:
            apply_step(b, syms["ptr_state"], st_)
        b.frames(60)

        opens = b.peek16(acc["acc_opens"])
        last = words(b, acc["acc_last"], 8)
        check(opens == 1, f"the accessory was opened {opens} times, expected 1")
        check(last[0] == AC_OPEN,
              f"its last message was {last[0]}, expected AC_OPEN ({AC_OPEN})")
        check(last[3] == THEDESK,
              f"AC_OPEN's msg[3] is {last[3]}, expected the Desk title "
              f"({THEDESK})")
        check(last[4] == acc_menu,
              f"AC_OPEN's msg[4] is {last[4]}, expected the menu id "
              f"{acc_menu}")
        print(f"  Desk -> '{want[:-1].decode().strip()}' delivered AC_OPEN "
              f"{last[:5]}")
        # It asked for nothing on the screen, so the mouse came straight
        # back: the application is the input owner again.
        check(b.peek16(syms["proc_input"]) == b.peek16(syms["proc_tab"]),
              "the application did not get the mouse back")

        # 5. it is running, not merely resident
        t0 = b.peek16(acc["acc_ticks"])
        y0, n0 = b.peek16(acc["acc_yields"]), b.peek16(syms["proc_turns"])
        b.frames(300)
        t1 = b.peek16(acc["acc_ticks"])
        y1, n1 = b.peek16(acc["acc_yields"]), b.peek16(syms["proc_turns"])
        check(t1 > t0,
              f"the accessory's timer did not advance in 300 frames "
              f"({t0} -> {t1}): it is resident but not running")
        print(f"  its own timer went {t0} -> {t1} over 300 frames with the "
              f"desktop up")

        # appl_find (AES 13): the process list searched by NAME, which is
        # the only thing in the tree that walks more than one record.  The
        # accessory asked for its own name once, at start-up, and asks for
        # the application's on every tick -- and the application only HAS
        # a name once the shell has loaded a program into it, so this is
        # the check that sh_ldapp names the one it runs.
        af, afa = b.peek16(acc["acc_find"]), b.peek16(acc["acc_findapp"])
        af = af - 65536 if af >= 32768 else af
        afa = afa - 65536 if afa >= 32768 else afa
        print(f"  appl_find: its own name -> {af}, \"DESKTOP \" -> {afa}")
        check(af == acc_id,
              f"appl_find(\"M28     \") answered {af}, not the accessory's own "
              f"ap_id {acc_id}: the shell did not name it from M28.ACC")
        check(afa == 0,
              f"appl_find(\"DESKTOP \") answered {afa}, not 0: the shell must "
              f"name the process it loads a program into, and the desktop is "
              f"the application")
        print(f"  the scheduler gave {n1} turns away")
        # appl_yield (AES 17) DOES hand a turn over, and this is the only
        # place it can be shown: with one process there is nobody to give
        # one to, so test-m11 can only prove the call answers.  The
        # accessory makes 32 of them per tick and the scheduler's counter
        # has to have moved at least that far -- a handful more for the
        # evnt_multi each tick is fine, but an appl_yield that handed
        # nothing over could not reach it.
        check(y1 > y0, f"the accessory made no appl_yield calls ({y0} -> {y1})")
        check(n1 - n0 >= y1 - y0,
              f"the accessory made {y1 - y0} appl_yield calls and the "
              f"scheduler handed over {n1 - n0} turns: a yield that finds "
              f"the application ready must give it one")
        print(f"  {y1 - y0} appl_yield calls -> {n1 - n0} turns handed over")
        check(b.peek16(acc["acc_msgs"]) == 1,
              f"the accessory was sent {b.peek16(acc['acc_msgs'])} messages, "
              f"expected the one AC_OPEN")

        # 6. AC_CLOSE, when the program the accessory is sitting under
        #    terminates.  File -> Quit ends the desktop, and the shell
        #    tells every registered accessory before it takes the memory
        #    back -- then WAITS for it to have read the message, which is
        #    the barrier proc_drain() is.  The accessory must still be
        #    there afterwards: that is the whole difference between an
        #    accessory and a program.
        title_xy = centre([THEBAR, THEACTIVE, FILEMENU])
        quit_xy = centre([themenus, dabox + 9, QUITITEM])
        quit_xy = (title_xy[0], quit_xy[1])
        here = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        for st_ in ([F(3)] + path(here, title_xy) + [F(10)]
                    + path(title_xy, quit_xy, speed=4)
                    + [F(10), B(1), F(14), B(0), F(30)]):
            apply_step(b, syms["ptr_state"], st_)
        for _ in range(120):
            b.frames(10)
            if b.peek16(acc["acc_closes"]):
                break
        closes = b.peek16(acc["acc_closes"])
        last = words(b, acc["acc_last"], 8)
        check(closes == 1,
              f"the accessory was closed {closes} times, expected 1 when the "
              f"desktop quit")
        if closes:
            check(last[0] == AC_CLOSE,
                  f"its last message was {last[0]}, expected AC_CLOSE "
                  f"({AC_CLOSE})")
            check(last[3] == acc_menu,
                  f"AC_CLOSE's msg[3] is {last[3]}, expected the menu id "
                  f"{acc_menu} -- the word AC_OPEN puts it in msg[4]")
            print(f"  File -> Quit delivered AC_CLOSE {last[:5]}")
        check(b.peek16(syms["proc_n"]) == 2,
              "the accessory's process went with the program it sat under")

        # 7. ...and so did what it was holding.  The accessory opens a
        #    virtual workstation at start-up and keeps it, which it could
        #    not do until one had an owner: vdi_close_virtuals() used to
        #    close every open workstation when any program exited.  The
        #    desktop has just exited, so this is the check that it now
        #    closes only its own -- read out of the VDI's own owner table
        #    against the accessory's context, which is its PROC record
        #    because p_ctx is the first member (src/aes/proc.h).
        ws = b.peek16(acc["acc_ws"])
        check(ws >= 2, f"the accessory's workstation handle is {ws}")
        if ws >= 2:
            # The VDI records each slot's owner as the CONTEXT that opened
            # it.  A closed slot's owner is 0 and the application's is
            # proc_tab, since p_ctx is the first member of its record --
            # so with two processes "neither of those" is the accessory's,
            # and no sizeof(PROC) has to be written down here.
            owner = b.peek16(syms["vwk_own"] + (ws - 1) * 2)
            app_ctx = b.peek16(syms["proc_tab"])
            check(owner != 0,
                  f"workstation {ws} was closed when the desktop exited")
            check(owner != app_ctx,
                  f"workstation {ws} is the application's (${owner:04X})")
            if owner and owner != app_ctx:
                print(f"  it still holds workstation {ws} (owner "
                      f"${owner:04X}, the application is ${app_ctx:04X}) "
                      f"after the desktop exited")
        check(b.peek16(syms["ctx_over"]) == 0,
              f"{b.peek16(syms['ctx_over'])} context park(s) refused")
    finally:
        emu.stop()

    print(f"gem4xe-m28: {'PASS' if not fails else 'FAIL'} -- an accessory "
          f"beside the desktop, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
