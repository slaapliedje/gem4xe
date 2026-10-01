# Phase 89 -- gem4xe's own colour icons, kept between programs

Phase 87 taught the desktop to draw its icons from a DESKICON.RSC, but
the only one there was is the Falcon's, which is Atari's to give away and
not gem4xe's.  Now gem4xe ships its own, drawn for the Atari 8-bit: a
5.25" diskette for a floppy, a CompactFlash card for a hard disk (what
SIDE, IDE+ and the rest are now), an Atari cartridge for a program, a
folder, a page and a bin.  And the desktop no longer reads the file each
time it starts: the first desktop after a boot loads it, and every one
after that takes the icons the AES kept.

## The art

tools/a8icons.py is the only place the pictures are: 32 rows of 32
characters each, one character a pen.  tools/deskiconrsc.py turns it
into build/deskicon.rsc, 9,896 bytes, with every form the AES can use:

- the 4-plane colour form, each pixel's planes being its HARDWARE colour
  (the pen through src/vdi/dev_vbxe.c's map_col), which is what
  rs_chunky reads them as;
- a selected form, each colour one step darker;
- the mono form, for the two-colour ANTIC screen, a pixel set where its
  colour is dark.

**Drawn for tall pixels.**  On 640x240 a pixel is about twice as tall as
it is wide, so the Falcon's icons, drawn 32 x 32 for square pixels, come
out tall and narrow on a TV -- as EmuTOS's do.  gem4xe's are drawn the
shape they should look: the diskette is 28 x 16, square on the screen.
Each sits at the bottom of the same 32 x 32 cell, so the desktop's grid
is unchanged, and a Falcon's file copied over gem4xe's still fits.

**The drive's number is black on white, and has to be.**  The number is
the ICONBLK's character, drawn transparent in its foreground colour.  A
colour icon's mask goes down in the BACKGROUND colour, and the image is
ORed over it, so a background other than white shows through every pixel:
a first draft gave the diskette a black background for a white digit and
drew a black square.  The mono form is drawn in the foreground colour,
so a white digit would also hide the icon on the ANTIC screen.  The
generator refuses both.

## Kept between programs

The desktop starts again after every program, and reading the file each
time cost seconds from a floppy.  So:

- desk_cicons (src/desk/desktop.c) asks the AES first,
  objc_sysvar(SV_INQUIRE, G4_DESKICON), and takes the icons it answers
  with as they are.
- When there are none, it loads DESKICON.RSC as in phase 87, copies the
  six kinds into a Malloc block, and hands the block over with
  objc_sysvar(SV_SET, G4_DESKICON, high, low).
- The AES makes the block the system's: gd_keep checks it is a Malloc
  block, and far_keep re-tags it owner 0 (src/sys/farmem.c), so the
  program's exit leaves it.  A block kept before it is given back.
- G4_DESKICON (101) is gem4xe's own, beside G4_3DLOOK.  The address is
  on the direct page: LoRAM is at its reserve.

A new DESKICON.RSC is therefore seen at the next boot.  The kept block is
9,556 bytes of far memory for as long as the machine is up.

## Shipped

GEM>DESKICON.RSC is on the CF card, the SpartaDOS X floppy, the
cartridge (which carries mkdist.SYSTEM), the release folder and the
pictures' disk.  It is not on the DOS 2 boot floppy, which has 26
sectors free; that desktop draws the mono icons, as before.

## Two bugs on the way

**A selected colour icon in a window lost its label.**  A window's items
are WHITEBAK, and objc_draw skipped an icon's label ground when its
background colour was white.  A selected colour icon swaps its label's
colours only after that test, so its black ground was skipped and its
white letters went onto white.  tools/aesref.py made the same mistake,
so m4 passed it.  Both now ask about the label's own ground.  m4's
colour icon case has a window's item, selected, and fails by 693 pixels
with the old test.

**The desktop model could not find a colour drive icon.**  deskref's
obj_get_obid still took only a G_ICON, which src/desk/deskobj.c stopped
doing in phase 87.  So the model skipped the objc_offset and
graf_growbox of a window reopened from a drive, and m18 found its second
desktop two calls ahead.  It took a temporary call log in the ABI to see
which two.

## Gates

- `test-host`: tests/host/test_a8icons.py holds the art to the
  desktop's labels (read from desktop.c), each digit to a white cell,
  and every pixel's planes to map_col read from dev_vbxe.c.  It breaks
  the generator's colour map to prove the check can fail.
- `test-boot`: the SpartaDOS X floppy's desktop, with its colour drive
  icons, against tools/deskref.py.  The model reads the same file
  (m17_desktop.deskicon_for), takes the far blocks rs_load takes, and
  builds the kept block as desk_cicons does.
- `test-m18`: its disk now carries DESKICON.RSC.  The first desktop
  loads and keeps the icons, the second takes the kept block without
  reading the file, and the heap after both is the heap before plus the
  desktop's file and the kept block.
- `test-m4`: the window's selected item.
- The pictures' disk carries the file, so the gates that drive it
  (m38, m39, m41) see colour icons: tests/emu/shots.py's item() reads a
  G_CICON's label as it reads a G_ICON's, and m39 drops CLOCK.RSC on
  DESKTOP.PRG where it dropped GEM4XE.CFG, which DESKICON.RSC pushed
  below the window's last row.
