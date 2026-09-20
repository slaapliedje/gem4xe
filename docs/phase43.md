# Phase 43 -- a DOS command from the desktop

Somebody asked for a shell inside GEM: SpartaDOS X's own prompt, the
way TOSWIN opens the ST's from its desktop.  It exists now as one item,
**File -> DOS command...**, where EmuTOS puts its "Execute EmuCON"
(`deskmain.c` CLIITEM): a line typed into a dialog, run by the DOS's
command processor with GEM's screen left as it is, and a window on
everything it printed.  `VER`, `DIR`, `COPY`, `DEL`, `MKDIR`, `CHKDSK`
-- the CAR: set, which is the CLI people want from inside a desktop.

## What the DOS already had

The SpartaDOS X Programming Guide -- DLT publishes one per version, and
4.50's is in `~/Documents/Atari/SDX/` -- settled the three things a shell
needs, none of which gem4xe had to invent:

- **XCOMLI** (18.9.2, as of 4.42): the whole line in `LBUF`
  (`COMTAB+63`), `BUFOFF` zeroed, one JSR, and COMMAND.COM does what the
  prompt would -- internal commands, CAR: commands, programs, `>>`
  redirection.  Batch files alone are out, and no status comes back.
- **Output to memory** (18.9.5.2): with the console's handle at
  `COMTAB+6` set to 100, the library's FPUTC jumps through `PUT_V` for
  every byte.  `src/sys/cio.s` `sdx_put` is what it jumps to: 6502 code
  that stores the byte through a long address kept in its own operand --
  the 65816 takes a long store in emulation mode -- so the buffer is far
  while the DOS runs in bank $00.
- **jfsymbol** at the fixed `$07EB` (16.1, as of 4.40): a plain `.xex`
  has no XREF block for the loader to resolve, so the two entries are
  looked up by name, once, on the first call -- and only on a SpartaDOS
  X of 4.4 or later (`$0701`, User Guide 6.8) whose `$07EB` is the JMP
  it should be.  Started with `X.COM` there is no symbol list; jfsymbol
  says so and the item stays grey.  A DOS 2 or a SpartaDOS 3 greys it too.

The native-mode call the guide describes (`pea #XCOMLI / cop #$00`, 19.1)
was not needed: `cio.s` already had a gateway to 6502 code, and a fourth
way in -- `sdx_call`, a JSR to whatever address `sdx_vec` holds with A
and X in and out -- serves both entries.  CRITIC is left alone for it:
a command's run is long, and the DOS ran it with the whole VBI.

## The room

XCOMLI loads COMMAND.COM (~3.6 KB) at MEMLO and a program above it.  For
the call `dos_command` raises MEMLO to the pool's cursor and closes the
MEMAC window (`vram_unmap`), so that from there to the DOS's screen at
`$9C00` -- the pool's free top, the window's 4 KB and the idle
`$9000-$9BFF` -- is the command's: about ten KB with the product
resident.  MEMLO goes back afterwards, which is why a program that stays
resident from here does not survive, and why the item is for commands
that print and return.  The DOS's console is under the overlay, so a
command that asks a question has nobody to answer it.

## The window

`src/desk/deskcmd.c` shows the buffer in a window of its own kind: rows
drawn through the one `G_STRING` of a two-object tree -- the AES's own
text drawing, as the text view's lines are -- rather than as items in
the screen tree, since a DIR is longer than `NUM_ITEMS`.  It scrolls by
arrows and slider like a folder window; `hndl_msg` hands it its messages
first.  Near memory was the constraint: the desktop's bss shares a
page-rounded region with a 640-byte stack, and a page more of it is a
page less of the pool for the accessory beside it (test-m28).  So the
window keeps seven direct-page scalars, the tree and the line live on
the stack for the one `objc_draw` that reads them, and the title is the
far buffer's first bytes -- the AES brings a far title near to draw it
(phase 41's `w_ptext`) *(no longer true since Phase 47 --
`docs/phase47.md`: `w_ptext` assigns the 24-bit address instead of
copying, the near buffers are gone and a title has no length cap)*.  The
dialog lives beside the chooser in `PREFS.RSC`, loaded only while it is
up, for the same reason.

Two things learned on the way: an *initialised* static costs a G4A
program its bytes twice, the image and the copy, so it is no way to
dodge a full bss; and the system's own Near region had 56 bytes left
after the gateway grew, which the VDI's two dispatch tables -- 284 bytes
of function pointers -- gave back by going far, at a few cycles a call.

## The gate

`test-sdx816` -- Rapidus OS, the SDX cartridge, `65816.SYS` -- now pulls
the File menu at the pointer, chooses the item, types `VER` and Return,
and reads back: 67 bytes, three lines, a window titled ` ver `, and the
banner *drawn*.  Two things about how.  The press is the emulator's
joystick trigger, not a poke of the pointer record: this is the product
binary with the product's config, an ST mouse, whose sampler reads the
trigger every tick and overwrites a poke -- the first gate to drive the
product's real mouse path, and it found that out.  And the text is read
off the screenshot with the model's own 8x8 font, because the bridge
reads no memory above `$FFFF`; the title comes from `gl_nbuf`, where the
AES put it to draw it.  `tools/deskref.py` learned the one call
`cmd_init` adds -- the probe -- and `aesref` answers it by a `psystem`
flag the boot gate sets from the DOS it booted.

And one gate the timer commit had been owed: `test-m32n` runs the
GEMDOS program on an **NTSC** machine -- the first gate that does --
and `evnt_timer(500)` spans 488 ms there, thirty frames of 16.7,
where a tick of 20 ms assumed on that frame gave 417; `clock()`
agrees to the millisecond, which is `irq.pal` read off the GTIA.
