# Phase 107 -- MagiC's check boxes, radio buttons and group frames

A tester's photo of QED's Global Settings dialog: the check boxes on the
right drawn as full framed buttons, each touching the next, and in the
3D look overlapping by half; the panels' titles as big framed buttons.

## Why

QED's resource is MagiC's.  Of its 679 objects only three carry an
extended type; the rest are plain `G_BUTTON`s and `G_STRING`s that
MagiC, XaAES and N.AES draw as something else, by their `ob_state`:

- `WHITEBAK` (`0x40`) marks one of MagiC's kinds, and the state's HIGH
  BYTE says which -- CF-Lib reads it the same way (`get_magx_obj`);
- a button with `0xFE` is a **group frame**: a rectangle whose title is
  set into its top edge;
- a button with bit 15 is a **check box**, or a **radio button** when it
  is `RBUTTON`: an indicator and a label, never a framed button.  Its
  low nibble is the letter to underline, `0xFF` none;
- an `EXIT` button is an ordinary one with that letter underlined;
- a string is underlined whole with `0xFF`, or has its letter
  underlined with `0x00`-`0x0F`.

QED lays its dialogs out for that: check boxes one text row apart.  On
any other AES CF-Lib's `fix_dial` turns them into `G_USERDEF`s it draws
itself; the port leaves `fix_dial` a no-op, because gem4xe draws no
`G_USERDEF`.  So they were framed buttons, packed edge to edge.

## The change

`src/aes/objc.c` draws them.  `ob_magx` reads the kind; `mx_draw` draws
a check box, a radio button or a frame whole, on the dialog's ground
(white flat, the 3D ground in the 3D look):

- the indicator is one text row tall less two and a character and a
  half wide -- square on the VBXE's tall pixels -- with a cross in it
  when a check box is `SELECTED`; a radio button's box has its corners
  cut and a solid centre;
- the label one character after it; a frame's title a character in,
  over its top edge;
- `DISABLED` greys the whole object, as it does any other.

They take **no 3D growth and no edge**: MagiC frames none of them, and
growing an object one row tall by two pixels a side is what overlapped
them.  `ob_change` redraws them for a change of `SELECTED` rather than
inverting the row.  An `EXIT` button and a string keep their own
drawing and gain the shortcut's rule; a whole underline is a rule along
the object's last row.

`appl_getinfo(AES_OBJECT)` answers bit 2 of its fourth word, which is
the bit CF-Lib's `init_userdef` reads before converting anything.  No
`G_SHORTCUT` type (bit 3).

The desktop set `WHITEBAK` on every item of a window, its text view's
`G_STRING` lines too, where it meant nothing -- and now would underline
each name's first letter.  It sets it on icons only
(`src/desk/deskwin.c`, `tools/deskref.py`).

## Found on the way: CONTROL from a stray byte

`test-m7`'s Ctrl-N case failed on this change, deterministically: the
`1` typed after Ctrl-N came back with `K_CTRL`.  The bridge had pushed
`$1F`.  The fault was in `kb_queue` (`src/vdi/vdi.c`), unchanged and
not recompiled:

    kb_m[t] = ((code & 0x40) ? 2 : 0) | ((code & 0x80) ? 4 : 0);

At -O2 the compiler stored `code` as a byte at `7,s`, loaded it back
**16 bits wide** and tested CONTROL with `inc a; dec a; bmi` -- bit 15,
a stray stack byte (the caller's `Y`).  So whether a key arrived with
CONTROL depended on what was on the stack; Ctrl-N passed the gate
because that byte suited, and moving the code after `objc.o` changed
it.  On the machine that is a shortcut missed, or a plain key taken for
one.  B23's family (tools/ccbug).  It is `(code >> 5) & 6` now: two
shifts and a mask on the byte, which compiles to `lsr`s in 8 bits and
an `and ##6` that drops the stray half.

## Proof

- **`make test-m4`**, four new cases: check boxes plain, with a shortcut
  and selected, disabled; a radio pair; a group frame; an `EXIT`
  button's and a string's shortcut and a whole underline -- flat and in
  the 3D look, then `objc_find` over a check box's LABEL (it is the
  object), and `objc_change` selecting and clearing each kind.  With
  `ob_magx` answering "none" in the C alone, all four fail: 4,373,
  5,729, 131 and 131 pixels.  21/21 with it.
- **`make test-m11`** holds `appl_getinfo(AES_OBJECT)` to `[1, 0, 1, 0, 4]`.
- **`make test-m7`** 13/13 again with the `kb_queue` fix (12/13 without
  it on this layout; 13/13 on the old one, by luck).
- `test-m9`, `test-m17` (the desktop, text view included), `test-m38`
  (the desktop from the keyboard), `test-m37`: pass.  `make memcheck`
  ok.
- QED's Global Settings on the card, flat and 3D: the four panels are
  titled frames, the check boxes sit one to a row with their letters
  underlined, OK, Cancel and Choose carry theirs.

## Not done

QED's editable number fields are 3D `FTEXT`s and still take the 3D
look's two-pixel growth, so in 3D they nudge the word beside them
("characters", "kBytes").  CF-Lib calls them `MX_EDIT3D`
(`te_thickness == -2`); MagiC draws them sunken without growing them.
