# Phase 158 -- the desktop formats and copies disks

Step 4 of `docs/disk-plan.md`.  The desktop's File menu has had TOS's
**Format...** since the first menu, greyed: it was the last item on the
"not yet" list (`tools/deskrsc.py NOT_YET`), kept so the menu had TOS's
shape.  It works now, and so does TOS's other way in:

| you do | the desktop runs |
|---|---|
| File -> Format..., with a drive selected on the desk | DISKUTIL `F 3`: its dialog on Format, D3: the destination |
| ...with no drive selected | the top window's drive, or DISKUTIL's own choice |
| a drive dragged onto another drive on the desk | DISKUTIL `C 1 2`: its dialog on Copy, D1: to D2: |

The desktop asks nothing itself: DISKUTIL's dialog is where the choice
is made, and its alert is where you confirm.  Let go anywhere else, a
dragged drive stays where it was.  The desk's icons keep their places,
as before; a drive could not be dragged at all until now.

DISKUTIL is found as EDIT is found from the viewer: `\APPS\DISKUTIL.PRG`
on the current drive, then on every other drive the DOS has.  The
applications floppy may be in any of them.  The search is now one
function, `do_apps`, which EDIT's lookup also uses.  With DISKUTIL on no
disk, an alert says where it is: "Formatting and copying disks is
DISKUTIL.PRG, in \APPS\ on the applications disk.  Put that disk in a
drive."

## Why a program, and not the desktop's own code

TOS's desktop formats in its own code.  This one's code must fit one
place in a 512 KB machine's three banks: about 4 KB spare after phase
152, which 1.4 KB of desktop code had nearly broken.  DISKUTIL's 9 KB
of code would not fit there.  This step's share of the desktop is the
drag and the menu case.  Its code is 51,542 bytes now, and `test-m37`
still starts it in three banks.

## Gate

**`test-m64`**: the desktop on the G4DOS system floppy, the applications
floppy in D2:.
- D2: selected and File -> Format...: DISKUTIL comes up on Format, its
  status line saying D2:'s 1440 sectors of 256.  Exit, and the desktop
  is back.
- D1: dragged onto D2:: DISKUTIL on Copy, onto D2:.  Exit, and the
  desktop is back.
- D2: taken out (the bridge's `EJECT`) and Format... again: the alert.
  OK, and the desktop goes on.

Nothing is formatted here; `test-m63` does that.  This is about the
desktop reaching DISKUTIL with the right tail.

| broken on purpose | result |
|---|---|
| the drag's two drives swapped | DISKUTIL opens copying onto D1:, and the gate says so |

**The desktop's model** (`tools/deskref.py`, which `test-m17` and
`test-m19` hold the desktop to call by call) learned the drag too.  A
press on a desk drive now samples the button (`graf_mkstate`) before it
is a click, and the first suite after the change failed test-m17 on
exactly that call.  The model raises rather than guesses where a drop
on another drive would run DISKUTIL; no gate that drives the model does
that.
