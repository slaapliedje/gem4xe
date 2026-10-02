# Phase 98 -- the window fields a port asks for

Item 10 of `roadmap-0.12.md`: `wind_get` did not answer `WF_KIND`,
`WF_NAME` or `WF_INFO`, and `wind_set(WF_BOTTOM)` did not send a window
to the bottom.  `docs/differences.md` listed the first three as a
difference.

## The three answers

The Compendium's `wind_get` lists none of them; they are set-only there.
Every later AES answers them -- MagiC, XaAES, N.AES -- and ported code
asks.  So `wm_get` (`src/aes/wind.c`) answers:

- `WF_KIND`: the components the window was created with;
- `WF_NAME`, `WF_INFO`: the string's address, high word first, as
  `wind_set` takes it and as `WF_NEWDESK` answers.  It is kept whole, so
  a large-data program's far title comes back far.

## WF_BOTTOM

Compendium p.460: "place the specified window at the bottom of the
window list (if there is more than one window) and top the new window on
the top of the list."  `wm_mkbottom` beside `wm_mktop`:

1. it moves the window to the first of the root's children, which is
   drawn first, so it sits at the back;
2. it rebuilds every window's rectangle list and the active window;
3. it redraws the window's rectangle from it upward, frames and
   `WM_REDRAW`s, since what the windows above covered of it is theirs
   now;
4. it draws the new top's whole frame active, which it may need where
   it does not overlap.

A window already at the back, or the only one, stays where it is.
`tools/aesref.py` does the same in the same order, and serves the three
answers.

`appl_getinfo(AES_WINDOW)` answers bit 6, "WF_BOTTOM set", where it
answered nothing.  Its comment had said why it could not claim the bit:
a program would be sent to a `wind_set` that answered FALSE.  The kit's
`gem.h` says so too.

## Proof

- **`make test-m8` case 2 (new).**  Three overlapping windows.  It asks
  for the three answers, sends the top one to the back, and then asks
  for the top, the bottom and each window's neighbours.  It walks every
  rectangle list and takes the three `WM_REDRAW`s, one a window, and no
  more.  Last, it sends the same window to the back again, which changes
  nothing.  Every word and every pixel is compared with the model.
  - With the redraw left out of `wm_mkbottom`, the case stalls waiting
    for the redraws.
  - The model, asked with `mesag(k)` for k from 0 to 7, accepted only 3,
    which is how the count in the case was found rather than guessed.
- **`make test-m11`** asks `appl_getinfo(AES_WINDOW)` and requires
  `[1, 64, 0, 0, 0]`.
- `case_size`'s `wind_get(WF_KIND)`, which had both sides refusing,
  now has both answering.
