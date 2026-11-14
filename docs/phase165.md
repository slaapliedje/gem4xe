# Phase 165 -- the cartridge's icon, and the DOS 2 floppy goes

Step 4 of `docs/run8-plan.md`, and a decision taken on the way.

## The DOS 2 floppy goes

`gem-boot.atr`, the floppy that booted DOS 2, went.  It was the only
reason for a second GEM.COM, `gem-dos2.xex`: the product less G4DOS's
half of GEMDOS, to fit 720 sectors.  Since phase 152, every few hundred
bytes of new code had cost a squeezed resource, and this phase took it
under its floor of free sectors again.  Nobody runs DOS 2: people use
MyDOS or SpartaDOS X.  The release never carried the disk either, since
its DOS isn't gem4xe's to give away.  The decision was the user's.

- **GEM still runs under DOS 2.**  The code paths stay, because MyDOS is
  a DOS 2 underneath and shares them: the disk format, DUP.SYS on Quit,
  and the stub that runs plain programs.  `test-m15` (GEMDOS on DOS 2)
  and the gates whose runner disks boot DOS 2 still run.
- **Gone:** `gem-boot.atr`, `gem-dos2.xex` and its `src/sys/nog4.c`
  stand-ins, and the free-sector floor that guarded them.
- **What booted it boots the MyDOS disk, `gem-mydos.atr`, instead:**
  `test-boot` (whose DOS 2 entry went; MyDOS is `test-mydos`'s), `test-m26`,
  `test-kmem`, `test-vbxefeat`, `test-m46`, `test-m68` and G4BENCH's disk.
  `gem-antic.atr`, `test-m26`'s safe-mode disk, is MyDOS's now.
- **The tester's build** (`make dist`) carries `gem-mydos.atr` where it
  carried `gem-boot.atr`.  The public release still leaves out a DOS
  that isn't gem4xe's.

## What cartridge there is

`dos_cart_probe` (`src/sys/dos.c`) looks once, at boot.  Three things it
met on the way:

- **TRAMSZ, the OS's own word, is no use.**  It is 1 with a cartridge,
  with BASIC and with neither, because the XL's BASIC counts at power-on
  and G4DOS then switches it out.  RAM under BASIC can read $BFFC = 0,
  just as a cartridge's header does.
- **A write test fails.**  Under the emulated Rapidus, a byte written to
  $BFFC read back as written while $BFFD beside it still read the
  cartridge's.  So there is no write: BASIC is switched out and then in,
  and ten bytes are looked at both ways (the header at $BFFA-$BFFF and
  $A000-$A003).  A cartridge overrides BASIC in the hardware and reads the
  same both times; with no cartridge, the first look is RAM and the
  second BASIC.
- **After `rapidus_speedup`, not before.**  That call is what leaves
  $8000-$BFFF slow, the VBXE's MEMAC window being in it.  Before it, the
  probe read the card's SRAM and found nothing.

Two exceptions:
- **Under SpartaDOS X** the ROM at $A000 is SDX's own.  It hides both
  BASIC and a cartridge on top, and came out as a cartridge.  There the
  answer is BASIC, which SDX's own `BASIC` command runs on any XL/XE.  A
  cartridge on top of SDX is `CAR` at its prompt.
- **gem4xe's own cartridge** (`src/cart.s`) also came out as a cartridge,
  and its icon would only start gem4xe again.  Its boot bank says
  "gem4xe cartridge", and the probe looks for that.

The answer is the cookie `G4CT` (0 none, 1 BASIC, 2 a cartridge), and
`G4CT_*` and `SH_CARTRIDGE` are in the kit's `gem.h`.

## The icon

After the drives, the desk shows **BASIC** or **CARTRIDGE**, as the user
chose: BASIC on every XL/XE, CARTRIDGE instead when one is plugged in.
Its character is a lower-case `c`, TOS's letter for the cartridge's
drive, which `icon_letter` doesn't take for a drive.  The pictures:
- the colour DESKICON.RSC has a cartridge in the computer's slot
  (`tools/a8icons.py`);
- the mono DESKTOP.RSC has EmuTOS's removable-disk picture, as TOS
  showed a cartridge as a disk.

**A data-loss bug went with it.**  `fun_file2any` took any desk icon that
was not a drive for the trash, so files dropped on the new icon would
have been deleted.  The trash is now known by its own character, none
(`icon_trash`), and the cartridge by its `c`.

Opening it is `shel_write(SHW_EXEC)` with the name `CAR:`, so any program
can ask, and DUP's B will.  GEM ends as for a plain program:
- **G4DOS, MyDOS and DOS 2: the stub.**  It is split now:
  - what has to outlive the cartridge stays in $0400-$057F;
  - what runs once before it (`r8_go`, and `r8_cart`, which switches
    BASIC in, sets RAMTOP to $A0, opens E: again and jumps through $BFFA)
    is in $0580-$05FF, BASIC's line buffer, which BASIC uses only once it
    is running;
  - `r8_back` puts PORTB and BASICF back as GEM left them.
- **On G4DOS too**, because G4DOS's shell keeps its variables in
  $A000-$BFFF and can't load with a cartridge in, or with BASIC switched
  in after BASIC's `DOS`.  For the same reason, plain programs go through
  the stub on G4DOS when a cartridge is plugged in, by G4DOS's flat name.
- **SpartaDOS X:** the batch file's first line is `CAR` or `BASIC`.

## Gate

**`test-m70`**, five machines; on each, the icon is opened from the desk:
- **G4DOS, BASIC.**  A file dragged onto the icon is not deleted and no
  dialog comes.  BASIC opened: READY, then `DOS`, then GEM again, with
  BASIC switched out.
- **G4DOS, our test cartridge.**  An 8 KB cartridge the gate makes (it
  prints CART RAN and leaves through DOSVEC, as BASIC's `DOS` does):
  CART RAN, then GEM.
- **MyDOS, BASIC** and **MyDOS, the cartridge**: the same through the stub.
- **SpartaDOS X, BASIC**: through the batch file and SDX's own command.

| broken on purpose | result |
|---|---|
| the trash as "any icon not a drive" again | the drop brings up DELETE FILE(S); the gate fails |

The first version of that check looked for "Delete" on the screen, and
passed with the bug put back: the dialog says DELETE FILE(S), in
capitals.  It looks for the dialog's "Number of files" now.

The probe's two wrong turns were seen as failures while it was written,
not broken afterwards on purpose: before `rapidus_speedup`, and with the
write test, it read 0 with the test cartridge in.
