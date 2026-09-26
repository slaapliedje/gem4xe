# Phase 60 -- the desktop's keyboard, and compiler bug B23

The second item of 0.9 (`docs/roadmap-0.9.md`).  The desktop received
keys and threw them away; it now answers the TOS desktop's own.

## The keys

| key | does |
|---|---|
| ^O ^I ^N ^H ^U ^D | File: Open, Show info, New folder, Close folder, Close window, Delete |
| ^Z | File -> DOS command (EmuTOS's key for its console) |
| ^Q | File -> Quit |
| ^S | Options -> Save desktop |
| 1 to 9 | open drive D1: to D9: |
| the arrows | scroll the top window a line; with SHIFT, a page |
| ESC | read the top window's directory again |
| DELETE | File -> Delete |

Each shortcut is written beside its item in the menu, TOS-style (`^O`),
which is why the File menu is two columns wider.  A key does what
choosing the item does, through the same `hndl_menu`, with the title
shown selected while it runs -- and nothing for an item that is greyed
out.

Two places this keyboard is not an ST's:

- **The drives are the digits.**  TOS opens a drive with Alt and its
  letter; there is no Alt here, and the icons are labelled by number, so
  `1` is the first drive.  The letters are left alone.
- **The arrows are CONTROL keys** (CONTROL with `- = + *`), so SHIFT
  with an arrow is CONTROL and SHIFT at once.  The VDI's key translation
  read past the end of the OS's 192-byte key table for that combination;
  it takes the control row now, and SHIFT is seen in the modifier state
  -- which is how SHIFT and an arrow mean a page.

## B23

That fix is where the phase's real finding came from.  Written as

    if (code & 0x80) idx += 128;
    else if (code & 0x40) idx += 64;

it made **every key on the desktop arrive as its shifted character** --
`1` as `!`, `a` as `A` -- which showed as `1` doing nothing at all.
The raw code in the interrupt ring was `$1F`, plain, and the OS's table
said `'1'` there; the translation said `'!'`.  In the compiler's own
simulator the function alone gave the wrong row at `-O2` and the right
one at `-O0` and `-O1`.  The listing shows why: the byte is stored at
`1,s` and loaded as a WORD from `0,s`, so it is in the HIGH byte and the
low byte is whatever lies below the stack; `bpl` tests bit 7 rightly, and
the else-if's `bit ##64` tests the stray byte.

`tools/ccbug` has it as B23 -- `bugs.c` holds a plain and a shifted code,
one of which is wrong whichever way the stray bit lies -- and the
translation takes the row as a number now.  And since nothing a function
owns can ever be at `0,s`, `mscan --build` reports any operand there in
the build's own assembly; there are none, and `mscan_b23.s`, the
reproducer's listing, proves the check can say otherwise.

## The gate

`make test-m38` boots the product disk and uses nothing but keys: `1`
opens drive A's window; `^N` makes a folder, its name typed; the down
arrow scrolls it into view (it was the third row, below the window's
edge, which the first run found by clicking on the frame); `^D` deletes
it; `^U` closes the window; and `^Q` leaves the shell asked to shut down
(`sh_doexec`, which is -1 while the desktop runs).  Each is checked by
what it did, not by a picture.  Not gated: ESC, DELETE, SHIFT with an
arrow, and the shortcuts for Show info, Save desktop and DOS command,
whose items the older gates already drive with the mouse.
