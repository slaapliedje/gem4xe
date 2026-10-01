# Phase 84 -- keys carry the ST's scan codes, and their own modifiers

Scoping the reported QED crashes found none, and found this: **none of
QED's menu shortcuts had ever worked on gem4xe.**  Ctrl-N, Ctrl-O,
Ctrl-S, Ctrl-Q -- nothing.  QED's gate (the port's `make check`) chose
everything from the menus with the mouse and never pressed one.

## Two reasons, one after the other

cflib, the library QED's menus come from, matches a shortcut by the
key's **ST scan code** (`menuisk.c`: the high byte of the key word,
looked up in XBIOS `Keytbl`'s caps table), not by its character.
gem4xe's keyboard (`src/vdi/vdi.c`, `kb_translate`) gave a scan code
only to the keys the AES switches on -- RETURN, TAB, the arrows and the
rest -- and every letter and digit came as its character alone, scan
code zero.  Ctrl-N arrived as `$000E` and matched nothing.

Behind that, the second: cflib also wants `K_CTRL` in the modifier
state `evnt_multi` returns with the key, and the AES read that state
live (`vq_key_s`), when the event returned.  POKEY shows CONTROL only
while a key is held, so a Ctrl-N tapped and let go before the program
asked came back without CONTROL.  A shortcut needs both.

## The fix

- **Every key the Atari shares with the ST carries the ST's scan
  code** -- letters, digits, `; - = , . /`, space -- from a table by
  the Atari's key code (`kb_st`).  The Atari's `+` and `*` are the ST's
  keypad keys; `<` and `>` share its one ISO key.  `A` is `$1E61` now,
  as on an ST; Ctrl-N is `$310E`.  GEMDOS's `Cconin` passes the scan
  code on in its third byte, as TOS does.
- **A key's SHIFT and CONTROL travel with it.**  The VDI's queue keeps
  them from the key code itself (`kb_m`), `v_string` answers them in
  `intout[1]`, `gsx_getkey` keeps them (`gl_kmods`), and `ev_multi`
  ORs them into the modifier state of an event that took a key -- what
  the key was pressed with, not what is held at the return.  The event
  recorder files them too.
- **The desktop** told a Control-letter from RETURN, TAB and BACKSPACE
  by `scan == 0`; it compares the whole key word with those three now,
  and Ctrl-I is no longer TAB because its scan code is I's.

In the QED port (`slaapliedje/qed-gem4xe`): `Keytbl` returns the ST's
three tables for every scan code gem4xe sends, the shifted row as the
Atari's keycaps have it, so cflib can turn `$31` back into the `N` the
menu says; and `norm_to_gem`, which replays a recorded macro, puts the
scan code back on, so a replayed ^N is a shortcut too.

## Gates

- **m7**: the key words carry their scan codes (`K()` adds the ST's to a
  character, by the key's name), and a new case takes Ctrl-N, SHIFT-N
  and 1 through `evnt_multi` and wants `$310E` with `K_CTRL`, `$314E`,
  `$0231`.
- **The memory budget** (`tests/host/test_memory.py`) caught the scan
  code table in bank $00's near region the first time -- 83 bytes left
  of the 128 it keeps -- so `kb_st` is `FAR`, in `cfar` beside the fill
  patterns.
- **m32**: `Cconin`'s high word for `k` is `$25`, its scan code, where
  it was required to be 0.
- **QED's gate** (`make check` in the port) taps Ctrl-N and wants a new
  window.  Driven by hand: Ctrl-N, Ctrl-A, Ctrl-C, Ctrl-N, Ctrl-V,
  Ctrl-W, Ctrl-O and Ctrl-Q all do what the menu says.

Programs that compared a whole key word with a character -- `key == 'a'`
-- would stop matching; nothing in this tree did (the AES takes the
character from the low byte and switches on the special keys' whole
words), and an ST program cannot, since TOS has always sent the scan
code.
