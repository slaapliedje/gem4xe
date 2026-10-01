# Phase 88 -- the 3D look on the windows

Phase 85's look raised the buttons and greyed the dialogs and left every
window flat.  TOS 4 raises the windows too, and so does EmuTOS built
with CONF_WITH_3D_OBJECTS.  Now gem4xe does, behind the same switch
(Look: Flat | 3D, the control panel's General module).  With the look
off, every window is drawn exactly as it was.

## The frame

src/aes/wind.c's w3_bldactive is EmuTOS's 3D w_bldactive (GPL, the
same donor as the rest of the window manager), which is TOS 4's frame:

- The closer, fuller, sizer, the four arrows and both elevators are
  activators (FL3DACT): drawn ADJ3DSTD, two pixels, bigger on every
  side, and set in by as much.  So a title bar or a scroll bar is a box
  `gl_hbox + 4` tall or `gl_wbox + 4` wide: 15 and 16 pixels here, where
  flat they are 11 and 12.  The name is an activator too when the window
  has one.  A MOVER with no NAME still gets a bar to drag.
- An untopped window draws all its gadgets.  So a slider set on one is
  redrawn at once, not only on the top window.
- A bar only where it has a gadget, TOS 4's rule.  A window whose only
  gadget is its SIZER gets a vertical bar for it.  wm_calc (wind_calc)
  does the same sums.  The info line is `gl_hbox` tall and no longer
  shares its bottom line with the work area.

**The grounds are grey, which is gem4xe's choice and not TOS 4's
default.**  The Falcon AES gives every gadget the colour word 0x1101
(FALCON.AES GEMWMLIB.C, read as a specification only), and its 3D
drawing turns only a hollow WHITE ground grey.  So a stock Falcon window
has white gadgets with raised edges; the grey ones in Falcon desktop
pictures come from that machine's window-colour settings.  gem4xe has
no per-window colours (WF_COLOR).  Grey is what the look's dialogs
already are, so the activators get a white fill colour, which objc_draw
greys, and the title, the info line and the two bars get the 3D ground
(ob_3dground).  A slider's track keeps its dotted pattern, so the grey
elevator stands out on it.

## Pressing

src/aes/ctrl.c draws a 3D gadget pressed in while it is held, as
EmuTOS's 3D build does.  The closer and fuller use gr_watchbox.  The
mover, the sizer and the elevators stay pressed for their drag.  An
arrow stays pressed until the button comes up: the first WM_ARROWED goes
at the press and the repeat is the poll's, so it is ct_arrow_stop, on
the release, that draws the arrow back up (ct_pressed).  Every one of
these draws is clipped to the window, because a 3D gadget draws outside
its own rectangle.

## Switching with windows open

The look switches the moment it is picked, and a frame is a different
size in the other look.  So objc_sysvar's G4_3DLOOK, when the value
changes, calls w_look: every open window keeps its outer rectangle,
takes the work area its new frame leaves, and its owner is sent a
WM_SIZED of that same rectangle.  That is how a GEM program learns that
its work area moved.  The desktop lays its icons out again on one, so a
folder window's icons drop below the taller title instead of being cut
by it.  General's full-screen redraw at OK then draws everything in the
new look.

**Known, and older than this phase:** for the moment between General's
OK and the control panel closing, the panel's dialog shows leftovers of
General's.  The panel is a dialog, not a window, so the full-screen
redraw does not reach it.  It was the same in phase 85.

## Memory

All of it is far code.  The one new variable, the pressed arrow, is on
the direct page (TINY): LoRAM is exactly at its 256-byte reserve again,
and tools/memreport.py failed the build until it moved.

## Gates

`test-m8` has two new cases, each run on the target and through
tools/aesref.py's model, which has the same frame:

- **[14] the 3D frame.**  wind_calc for every bar rule; a window with
  everything under a smaller one, whose gadgets and slider are drawn;
  then the look switched off and on under both, which must send two
  WM_SIZED each time and give the work areas both frames leave.
- **[15] pressed.**  The closer let go outside it, the elevator and the
  sizer dragged, then an arrow held and let go.  The arrow comes last on
  purpose: with it earlier, the sizer's redraw repainted the whole frame
  and an arrow left pressed in passed unseen.  With it last, an arrow
  that never came back up fails by 82 pixels, which was checked by
  breaking ct_arrow_stop.

The flat cases [0]-[13] are unchanged and pass, as do `m9`, `m17` and
`m19`.
