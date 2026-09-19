#!/usr/bin/env python3
"""Phase 7 gate: the AES event and form layer, driven from the host.

Where m4 compares drawings, this compares *behaviour under input*: the
harness pokes the pointer (ptr_state), holds keys through POKEY and runs
frames while the target is blocked inside an evnt_* or form_do call, and
tools/aesref.py walks the same input plan with the same frame semantics.
Three things are compared, as in m4: every returned word, the screen, and
the tree's memory -- form_do's edits land in te_ptext and ob_state, and a
wrong write there is invisible on screen.

A plan is a list of steps applied while the target is inside one op:

    ("frames", n)                    run n frames (n ticks of the timer)
    ("move", x, y)                   put the pointer at x,y, run a frame
    ("button", s)                    set the button state, run a frame
    ("key", name, code[, shift, ctrl])   hold the key for a frame; `name`
                                     is the bridge's, `code` the word the
                                     AES delivers for it

Each plan starts with a settle -- see aesref.run() for why -- and ends on
the step that completes the op, so a plan that expects a click to be
counted through the double-click delay says so with an explicit
("frames", n) after the press, kept well clear of the delay's edge:
a tick is a PAL frame and the target sees one more or one fewer than the
harness ran when the op's first or last poll straddles a frame boundary.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import vbxeref, vdiref, aesref, symfile     # noqa: E402
from aesref import (Obj, Layout, NIL, G_BOX, G_IBOX, G_BUTTON, G_FTEXT,   # noqa: E402
                    G_BOXCHAR, LASTOB, DEFAULT, SELECTABLE, EXIT, EDITABLE,
                    RBUTTON, TOUCHEXIT, SELECTED, SHADOWED,
                    TAB, RETURN, BACKSPACE, ESCAPE, ARROW_UP, ARROW_DOWN,
                    MU_KEYBD, MU_BUTTON, MU_M1, MU_M2, MU_TIMER,
                    FMD_START, FMD_GROW, FMD_SHRINK, FMD_FINISH, WF_NEWDESK,
                    EVNT_KEYBD, EVNT_BUTTON, EVNT_MOUSE, EVNT_TIMER,
                    EVNT_MULTI, EVNT_DCLICK, FORM_DO, FORM_DIAL, FORM_KEYBD,
                    FORM_BUTTON, GRAF_GROWBOX, GRAF_SHRINKBOX, GRAF_WATCHBOX,
                    GRAF_MKSTATE, WIND_SET, APPL_TPLAY, APPL_TRECORD,
                    APPEVNT_TIMER, APPEVNT_BUTTON, APPEVNT_MOUSE)
from m4_aes import dialog, form, draw, key, mem_diff, PRELUDE   # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
SYMS = os.path.join(ROOT, "build", "m3.sym")
SHOTDIR = os.path.join(ROOT, "build", "shots")
STATUS, ST_GO, ST_DONE = 0x0600, 3, 4


# -- trees ------------------------------------------------------------------

def panel(L):
    """A dialog with everything form_do reacts to: two editable fields, a
    radio group, a TOUCHEXIT box, a plain SELECTABLE toggle, an EXIT
    button and the DEFAULT one."""
    return [
        #    next head tail type       flags                 state     spec        x    y    w    h
        Obj(NIL,  1,  10,  G_BOX,     0,                    SHADOWED, 0x00021100, 100,  40, 440, 160),
        Obj(2,  NIL, NIL,  G_FTEXT,   EDITABLE,             0, L.ted("", "Name: ____", "X"),   16,  16,  80,   8),
        Obj(3,  NIL, NIL,  G_FTEXT,   EDITABLE,             0, L.ted("", "Num: ___", "9"),     16,  32,  64,   8),
        Obj(7,    4,   6,  G_IBOX,    0,                    0,        0x00001100,  16,  56, 220,  16),
        Obj(5,  NIL, NIL,  G_BUTTON,  RBUTTON | SELECTABLE, SELECTED, L.text("Left"),   0,   0,  60,  16),
        Obj(6,  NIL, NIL,  G_BUTTON,  RBUTTON | SELECTABLE, 0,        L.text("Mid"),   72,   0,  60,  16),
        Obj(3,  NIL, NIL,  G_BUTTON,  RBUTTON | SELECTABLE, 0,        L.text("Right"), 144,  0,  60,  16),
        Obj(8,  NIL, NIL,  G_BOXCHAR, TOUCHEXIT,            0,        0x54021100, 300,  16,  40,  40),
        Obj(9,  NIL, NIL,  G_BUTTON,  SELECTABLE | EXIT | DEFAULT, 0, L.text("OK"),   300, 120,  60,  20),
        Obj(10, NIL, NIL,  G_BUTTON,  SELECTABLE | EXIT,    0,        L.text("Cancel"), 370, 120, 60, 20),
        Obj(0,  NIL, NIL,  G_BUTTON,  SELECTABLE | LASTOB,  0,        L.text("Toggle"), 16, 120,  80, 20),
    ]


def desk(L):
    """A desktop background: one patterned box the size of the screen, the
    tree wind_set(WF_NEWDESK) hands the AES for form_dial(FMD_FINISH)."""
    return [Obj(NIL, NIL, NIL, G_BOX, LASTOB, 0, 0x00001148, 0, 0, 640, 240)]


# Screen positions of the panel's controls (root at 100,40).
TOGGLE, CANCEL, OK, RIGHT, TOUCH = (156, 170), (500, 170), (430, 170), (290, 104), (420, 76)
# ...and of the dialog's (root at 160,60).
D_OK, D_CANCEL, D_HELP = (220, 142), (316, 142), (412, 142)


# -- plan steps ---------------------------------------------------------------

def F(n):
    return ("frames", n)


def M(x, y):
    return ("move", x, y)


def B(s):
    return ("button", s)


def K(name, code, shift=False, ctrl=False):
    return ("key", name, code, shift, ctrl)


def CLICK(xy=None):
    """A single click at xy (or where the pointer is), run through the
    double-click delay: 11 ticks at the default rate, so 14 frames puts
    the delivery well inside the wait and the release well after it."""
    return ([M(*xy)] if xy else []) + [B(1), F(14), B(0), F(2)]


def DCLICK(xy):
    """Two clicks two frames apart: the second lands with 5 ticks of the
    delay to spare and extends it by 3, so the pair is delivered as one
    2-click event 14 ticks after the first press."""
    return [M(*xy), B(1), F(2), B(0), F(2), B(1), F(2), B(0), F(14)]


# -- the tape (appl_tplay / appl_trecord) -----------------------------------
# An EVNTREC is six bytes: the kind as a WORD, then a LONG, both
# little-endian, which is what this compiler lays the struct out as
# (src/aes/event.c reads the offsets out of the generated code).  TAPE
# carries the addresses from the tree builder, which runs before the
# body, to the body, which needs them.
TAPE = {}


def evntrec(recs):
    return b"".join(struct.pack("<hi", ev, val) for ev, val in recs)


def tape_tree(L):
    """dialog(), plus a tape to play and room to record one into."""
    TAPE["play"] = L.raw(evntrec([
        (APPEVNT_MOUSE,  320 | (140 << 16)),
        (APPEVNT_BUTTON, 1 | (1 << 16)),
        (APPEVNT_TIMER,  60),
        (APPEVNT_BUTTON, 0),
        (APPEVNT_MOUSE,  400 | (180 << 16)),
    ]))
    TAPE["nplay"] = 5
    TAPE["rec"] = L.raw(bytes(6 * 8))
    return dialog(L)


Z5 = (0, 0, 0, 0, 0)


def multi(flags, clicks=0, mask=0, state=0, m1=Z5, m2=Z5, ms=0):
    return (EVNT_MULTI, (), (flags, clicks, mask, state) + tuple(m1) + tuple(m2)
            + (ms & 0xFFFF, ms >> 16))


# -- cases ------------------------------------------------------------------
# (name, tree builder, body, plan[, second tree builder]).  Plan keys index
# the body; the body may be a function of the second tree's address.

def tape_body(_):
    """appl_tplay, then appl_trecord and the tape it took played back.

    WHAT THE TAPE LEAVES BEHIND IS THE BUTTON, not the pointer.  A
    graf_mkstate after a playback was the obvious check and it is
    VACUOUS: gem4xe polls the hardware every ev_poll, so the emulator's
    own pointer snaps back the moment playback ends, and a tplay that
    skipped every mouse record passed.  What survives is the button
    TRANSITION -- bchange keeps pr_xrat and pr_yrat from the moment of
    it, and nothing polls those back -- so an evnt_multi(MU_BUTTON)
    satisfied at entry reports where the TAPE pressed, which is nowhere
    the plan has been.  evnt_button will NOT do: it registers a wait and
    spins for a FRESH transition (ev_block), so a stored one is
    invisible to it, which cost a run to find out.

    The first tape is staged by the host, so what it should answer is
    written in this file: a press at (320, 140).  Then the round trip --
    six records taken while the plan moves to (250, 120) and clicks,
    played back after the pointer has been moved away -- must answer
    with the recording's own press.  A recorder that filed nothing but
    the passage of time (which is what it does on a quiet machine, and
    why appl_trecord returns at all) would have nothing to play and the
    wait would never be satisfied.
    """
    return [
        multi(MU_TIMER, ms=100),                  # park the pointer
        (GRAF_MKSTATE,),                          # where the PLAN left it
        (APPL_TPLAY, (), (TAPE["nplay"], 100, TAPE["play"])),
        multi(MU_BUTTON, 1, 1, 1),                # the TAPE's press
        (APPL_TRECORD, (), (6, TAPE["rec"])),     # six, while the plan moves
        multi(MU_TIMER, ms=100),                  # and away again
        (APPL_TPLAY, (), (6, 100, TAPE["rec"])),
        multi(MU_BUTTON, 1, 1, 1),                # the RECORDED press
    ]


CASES = [
    ("appl_tplay and appl_trecord: the tape, and a round trip", tape_tree,
     tape_body,
     {0: [F(2), M(100, 60), F(4)],
      2: [F(4)],
      4: [F(2), M(250, 120), B(1), F(3), B(0), F(3)],
      5: [F(2), M(60, 200), F(4)],
      6: [F(8)]},
     # a tree of one, only so that the body may be a function: it needs
     # the addresses the tree builder staged
     lambda L2: [Obj(NIL, NIL, NIL, G_BOX, LASTOB, 0, 0x00021100, 0, 0, 8, 8)]),

    ("evnt_keybd and evnt_multi(MU_KEYBD): keys through POKEY", dialog,
     [draw(), (EVNT_KEYBD,), (EVNT_KEYBD,), (EVNT_KEYBD,),
      multi(MU_KEYBD), multi(MU_KEYBD | MU_TIMER, ms=2000)],
     {1: [F(3), K("A", 0x61)],
      2: [F(2), K("RETURN", RETURN)],
      3: [F(2), K("MINUS", ARROW_UP, ctrl=True)],
      4: [F(2), K("EQUALS", ARROW_DOWN, ctrl=True)],
      5: [F(5), K("B", 0x62)]}),

    ("evnt_button: press, release, satisfied at entry; graf_mkstate", dialog,
     [(EVNT_BUTTON, (), (1, 1, 1)), (EVNT_BUTTON, (), (1, 1, 0)),
      (EVNT_BUTTON, (), (1, 1, 0)), (GRAF_MKSTATE,),
      multi(MU_BUTTON, 1, 1, 1), multi(MU_BUTTON, 1, 1, 0), (GRAF_MKSTATE,)],
     # The pointer boots at (0,0), which is the menu strip: a press there
     # belongs to the control manager (Phase 8), so step onto the desktop
     # first.
     {0: [F(3), M(300, 100), B(1)], 1: [F(3), B(0)],
      4: [F(3), M(300, 100), B(1)], 5: [F(3), B(0)]}),

    ("evnt_multi(MU_BUTTON): clicks through the double-click delay", dialog,
     [multi(MU_BUTTON, 2, 1, 1), multi(MU_BUTTON, 1, 1, 0),
      multi(MU_BUTTON, 2, 1, 1),
      (EVNT_DCLICK, (), (0, 0)), (EVNT_DCLICK, (), (4, 1)),
      (EVNT_DCLICK, (), (3, 1)), (EVNT_DCLICK, (), (0, 0))],
     {0: [F(3), B(1), F(14)], 1: [F(3), B(0)],
      2: [F(3)] + DCLICK((200, 150))}),

    ("evnt_mouse and evnt_multi(MU_M1|MU_M2): rectangle crossings", dialog,
     [(EVNT_MOUSE, (), (0, 100, 100, 50, 50)),
      (EVNT_MOUSE, (), (1, 100, 100, 50, 50)),
      multi(MU_M1 | MU_M2, m1=(0, 0, 0, 50, 50), m2=(1, 150, 100, 100, 40)),
      (GRAF_MKSTATE,)],
     {0: [F(3), M(110, 120)],
      1: [F(3), M(130, 130), F(2), M(200, 120)],
      2: [F(3), M(205, 125), F(2), M(10, 10)]}),

    ("evnt_timer and evnt_multi(MU_TIMER)", dialog,
     [(EVNT_TIMER, (), (60, 0)), (EVNT_TIMER, (), (0, 0)),
      multi(MU_TIMER, ms=100), multi(MU_TIMER | MU_KEYBD, ms=0),
      multi(MU_KEYBD | MU_TIMER, ms=2000)],
     {0: [F(6)], 1: [F(3)], 2: [F(9)], 4: [F(4), K("C", 0x63)]}),

    ("form_keybd and form_button on a form", form,
     [draw(),
      (FORM_KEYBD, (), (1, TAB, 0)), (FORM_KEYBD, (), (2, ARROW_UP, 0)),
      (FORM_KEYBD, (), (1, key('x'), 0)), (FORM_KEYBD, (), (1, RETURN, 0)),
      (FORM_BUTTON, (), (6, 1)), (FORM_BUTTON, (), (6, 1)),
      (FORM_BUTTON, (), (1, 1))],
     {}),

    ("form_do on a dialog: RETURN, a click, a disabled button, re-select", dialog,
     [draw(), (FORM_DO, (), (0,)), (FORM_DO, (), (0,)), (FORM_DO, (), (0,))],
     {1: [F(3), K("RETURN", RETURN)],
      2: [F(3)] + CLICK(D_CANCEL)[:-1],
      3: [F(3)] + CLICK(D_HELP) + CLICK(D_OK) + CLICK()[:-1]}),

    ("form_do on a panel: fields, radios, toggle, slide-off, TOUCHEXIT", panel,
     [draw(), (FORM_DO, (), (0,)), draw(), (FORM_DO, (), (1,))],
     {1: [F(3)] + CLICK(TOGGLE) + CLICK() +
         [M(*CANCEL), B(1), F(14), M(500, 100), F(2), B(0), F(2)] +
         CLICK(RIGHT) + CLICK((50, 200)) +
         [K("A", 0x61), K("B", 0x62), K("TAB", TAB), K("7", 0x37), K("1", 0x31)] +
         DCLICK(TOUCH),
      3: [F(3), K("EQUALS", ARROW_DOWN, ctrl=True), K("BACKSPACE", BACKSPACE),
          K("9", 0x39), K("MINUS", ARROW_UP, ctrl=True), K("ESC", ESCAPE),
          K("Z", 0x7A), K("RETURN", RETURN)]}),

    ("graf_watchbox: in, out, in, release; then with the button up", panel,
     [draw(), (EVNT_BUTTON, (), (1, 1, 1)),
      (GRAF_WATCHBOX, (), (10, SELECTED, 0)), (GRAF_WATCHBOX, (), (10, SELECTED, 0)),
      (GRAF_MKSTATE,)],
     {1: [F(3), M(*TOGGLE), B(1)],
      2: [F(3), M(156, 100), F(2), M(*TOGGLE), F(2), B(0)]}),

    ("form_dial: grow and shrink leave the screen alone; FINISH redraws the desk",
     dialog,
     lambda desk_addr: [
         draw(),
         (FORM_DIAL, (), (FMD_START, 300, 100, 20, 20, 160, 60, 320, 110)),
         (FORM_DIAL, (), (FMD_GROW, 300, 100, 20, 20, 160, 60, 320, 110)),
         (FORM_DIAL, (), (FMD_SHRINK, 300, 100, 20, 20, 160, 60, 320, 110)),
         (GRAF_GROWBOX, (), (10, 10, 40, 30, 160, 60, 320, 110)),
         (GRAF_SHRINKBOX, (), (10, 10, 40, 30, 160, 60, 320, 110)),
         (WIND_SET, (), (0, WF_NEWDESK, 0, desk_addr, 0)),
         (FORM_DIAL, (), (FMD_FINISH, 0, 0, 0, 0, 160, 60, 320, 110))],
     {}, desk),
]


# -- driving the target -----------------------------------------------------

def poke16(b, addr, value):
    b.poke(addr, value & 0xFF)
    b.poke(addr + 1, (value >> 8) & 0xFF)


def apply_step(b, ptr, step, done=None):
    """Apply one step.  A ("frames", n) step runs a frame at a time and
    stops when done() says the op has completed -- the frames left after
    satisfaction are dropped, as the reference drops them -- so a timer's
    plan need not name the exact tick.  A ("shot", fn) step runs no frame:
    fn(bridge) screenshots the target where the reference keeps a copy of
    its own screen (aesref.AES.shots)."""
    kind = step[0]
    if kind == "frames":
        for _ in range(step[1]):
            b.frames(1)
            if done and done():
                break
        return
    if kind in ("shot", "probe"):
        # between frames, as the reference takes its: step[1](bridge)
        step[1](b)
        return
    if kind == "move":
        poke16(b, ptr, step[1])
        poke16(b, ptr + 2, step[2])
    elif kind == "button":
        poke16(b, ptr + 4, step[1])
    elif kind == "key":
        b.key(step[1], shift=len(step) > 3 and step[3], ctrl=len(step) > 4 and step[4])
    else:
        raise ValueError(step)
    b.frames(1)


NOT_STARTED = 0xFFFF     # what the harness leaves in vdi_result_count
FINISH = 16              # frames an op may take to return after its last stimulus


def drive(b, count_addr, ptr, plan, read=None):
    """Apply each op's plan while the target is inside that op.  Returns an
    error string, or None; a non-None error leaves the target blocked.

    The count is the index of the op the target is inside: the runner's
    completed-call count, or whatever `read` derives it from -- the
    desktop gate (m17) reads the ABI's own call counter instead, since the
    desktop is a program, not a script the runner walks."""
    read = read or (lambda: b.peek16(count_addr))
    # The runner zeroes the count when it picks up ST_GO; until then the
    # count is the sentinel, not the last case's total.
    for _ in range(50):
        if read() != NOT_STARTED:
            break
        b.frames(2)
    else:
        return "runner did not start the script"
    for k in sorted(plan):
        n = None
        for _ in range(200):
            n = read()
            if n >= k:
                break
            b.frames(2)
        if n != k:
            if n is not None and n > k:
                return f"op {k} completed without its plan (count {n})"
            return f"timed out waiting for op {k} (count {n})"
        for j, step in enumerate(plan[k]):
            n = read()
            if n != k:
                return f"op {k} completed before step {j} {step} (count {n})"
            apply_step(b, ptr, step, lambda: read() != k)
        # The last step satisfies the wait; what the op does on its way out
        # -- the file selector's fm_dial(FMD_FINISH) redraws the screen it
        # covered before it returns -- can run a frame or two past it.  The
        # reference takes no time there, so those frames are the harness's
        # and not the plan's: a bound on the target's finishing, not a
        # measurement of it.  Ops after k that need no plan -- a call
        # satisfied at entry, a graf_mkstate -- complete in the same frame,
        # so the count may run past k+1; running past the next planned op
        # is caught above.
        for _ in range(FINISH):
            n = read()
            if n > k:
                break
            b.frames(1)
        if n <= k:
            return f"op {k} did not complete on its plan (count {n})"
    return None


def storm_check(b, addr=0x2000):
    """A verdict when the machine has been painted by the emulator's
    SEI-shadow IRQ storm rather than stopped by anything the program
    did; None when it has not.

    The storm pushes four bytes at every opcode fetch until the stack
    has wrapped through bank $00 (tools/altirra/, patch 1), so it writes
    the HARDWARE as well as the RAM.  Nothing a C program does can leave
    ANTIC's registers holding the same byte pair its own memory is full
    of, so the two conditions together tell a wild write in gem4xe from
    a wild machine underneath it -- which took three phases to recognise
    the first time (docs/phase26.md), and is one HWSTATE now.
    """
    dmp = bytes(b.memdump(addr, 256))
    common = sorted({c: dmp.count(c) for c in set(dmp)}.items(),
                    key=lambda kv: -kv[1])[:2]
    if len(common) < 2 or sum(n for _, n in common) < 230:
        return None                             # memory is not a pair
    if common[1][1] < 32:
        return None                             # ...it is one value and a few:
                                                # memory a program zeroed, not
                                                # memory something alternated
    pair = {f"${v:02x}" for v, _ in common}
    st = b.cmd("HWSTATE")
    if not st.get("ok"):
        return None
    regs = [v for part in ("antic", "gtia", "pokey")
            for k, v in (st.get(part) or {}).items()
            if isinstance(v, str) and len(v) == 3 and v.startswith("$")]
    if len(regs) < 20 or sum(v in pair for v in regs) * 10 < len(regs) * 8:
        return None                             # the hardware disagrees
    return ("the whole machine reads " + "/".join(sorted(pair)) + " -- RAM "
            f"at ${addr:04X} AND ANTIC, GTIA and POKEY's registers.  Nothing "
            "gem4xe does can write those: this is the emulator's SEI-shadow "
            "IRQ storm (tools/altirra/altirra-65c816-native-mode.patch), and "
            "the run says nothing about the desktop.  Re-run it with "
            "ALTIRRASDL=<a build with the three patches>.")


def compare(b, results_addr, n, script, want):
    """The first of the target's n result records that differs from the
    reference's, as a message; None if none does."""
    got = vdiref.decode(b.memdump(results_addr, n * vdiref.RESULT_WORDS * 2), n)
    for i, rec in enumerate(got[:len(want)]):
        if rec != want[i]:
            return (f"call {i} (op {script[i][0]}) returned {rec}, "
                    f"expected {want[i]}")
    return None


def main(argv):
    keep = "--shot" in argv
    only = None
    for a in argv:
        if a.startswith("--only="):        # --only=3,4 runs those cases
            only = {int(x) for x in a[7:].split(",")}
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    sa, sc = syms["vdi_script"], syms["vdi_scratch"]
    results_addr, count_addr = syms["vdi_results"], syms["vdi_result_count"]
    ptr = syms["ptr_state"]
    scratch_room = min(a for a in syms.values() if a > sc) - sc
    script_room = min(a for a in syms.values() if a > sa) - sa

    emu = launch(tag="m7", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    out = []
    try:
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

        for idx, case in enumerate(CASES):
            if only is not None and idx not in only:
                continue
            name, build, body, plan = case[:4]
            extra = case[4] if len(case) > 4 else None
            L = Layout(sc, max_objs=12)
            objs = build(L)
            image = L.pack(objs)
            layouts = [(L, objs, image)]
            trees = {}
            if extra:
                L2 = Layout(L.next, max_objs=1)
                objs2 = extra(L2)
                layouts.append((L2, objs2, L2.pack(objs2)))
                trees[L2.base] = objs2
                body = body(L2.base)
            assert layouts[-1][0].next - sc <= scratch_room, (name, scratch_room)
            for lay, _, img in layouts:
                b.memload(lay.base, img)
            mem = {}
            for lay, _, _ in layouts:
                mem.update(lay.mem)
            script = PRELUDE + body
            plan = {k + len(PRELUDE): v for k, v in plan.items()}
            # Where the last case left the pointer is where this one starts.
            pointer = (b.peek16(ptr), b.peek16(ptr + 2))

            ref_v, ref_a, want = aesref.run(script, objs, mem, plan=dict(plan),
                                            pointer=pointer, trees=trees)

            words = aesref.encode(script, sc)
            assert len(words) * 2 <= script_room, (name, len(words), script_room)
            b.memload(sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                                   for w in words))
            b.poke(STATUS + ST_DONE, 0)
            poke16(b, count_addr, NOT_STARTED)
            b.poke(STATUS + ST_GO, 1)
            err = drive(b, count_addr, ptr, plan)
            if err:
                # What the target did record, against the reference, is the
                # best clue to why it stopped where it did.
                n = b.peek16(count_addr)
                err += "; " + (compare(b, results_addr, n, script, want)
                               or f"the {n} records so far match")
                out.append((idx, name, err))
                print(f"  [{idx}] {name:<66s} FAIL")
                print(f"   target blocked: {err}; cannot continue")
                break
            ok = False
            for _ in range(300):
                if b.peek(STATUS + ST_DONE) == 0xA5:
                    ok = True
                    break
                b.frames(4)
            if not ok:
                out.append((idx, name, "timed out"))
                break
            b.frames(4)

            n = b.peek16(count_addr)
            if n != len(want):
                err = f"{n} calls recorded, expected {len(want)}"
            else:
                err = compare(b, results_addr, n, script, want)
            if not err:
                for lay, lobjs, img in layouts:
                    err = mem_diff(lay, lobjs, bytes(b.memdump(lay.base, len(img))))
                    if err:
                        break

            shot = os.path.join(SHOTDIR, f"m7-{idx:02d}.png")
            b.screenshot(shot)
            bad, shown = vbxeref.compare_to_shot(ref_v.to_rgb(), shot)
            if bad and not err:
                err = f"{bad} px differ; first {shown[:3]}"
            out.append((idx, name, err))
            if not err and not keep:
                os.remove(shot)
            print(f"  [{idx}] {name:<66s} {'ok' if not err else 'FAIL'}")
    finally:
        emu.stop()

    fails = [r for r in out if r[2]]
    print()
    for idx, name, e in fails:
        print(f"   FAIL [{idx}] {name}: {e}")
    want = len(CASES) if only is None else len(only)
    print(f"gem4xe-m7: {len(out) - len(fails)}/{want} event/form cases passed")
    return 1 if fails or len(out) < want else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
