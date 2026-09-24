# Phase 50 -- MyDOS, and the page a 6502 means when it wraps

`docs/shipping.md` has carried this since the product floppies:

> **MyDOS does not work, and the reason is not known.**  GEM crashes
> under it every time, at the same place: twelve bytes of the far image
> are missing at bank `$01` offset `$20` [...] it wants an hour with a
> watchpoint that the bridge does not have yet.

It mattered more after 0.7.  The cartridge answered "does a demo need a
DOS" with no; the disk route -- a bootable `.atr` for somebody with a
FujiNet, an SDrive or a real drive -- still wants one, and a disk's
advantage over a cartridge is that it can be **written**.  MyDOS is the
obvious writable DOS to put under it, and this bug was the thing in the
way.

## The watchpoint the bridge does not have, so the program reports on itself

`BP_SET` does nothing on the accelerated CPU and `WATCH_SET` is blind to
the Rapidus's fast RAM (`docs/phase14.md`, `docs/phase38.md`).  So
instead of watching the machine, the program was made to say what it
saw: the same `GEM.COM`, with every `INITAD` segment pointed at a
logger that records **who called it** (the return address on the
stack), **the chunk header** at `_fl_hdr` and **a sum of the staging
buffer**, then calls the real `_fl_copy` and **photographs the damaged
bytes** after it returns.  `RUNAD` is a `jmp *`, so GEM never runs and
the far image can be compared with the linker's output afterwards.

Run under the DOS 2 that works first, as the control: twenty calls,
every header and sum exactly what a host-side simulation of the file
says they should be, far image perfect.  Then MyDOS:

- **all twenty calls saw exactly the right chunk** -- so MyDOS's binary
  loader was never the problem, which is what everybody (including this
  tree) had assumed;
- after call 0, `$010020-$01002B` held the right bytes; at call 1 they
  were zeros -- so they went bad **while MyDOS was reading the next
  segment**, not while ours was unpacking;
- the twelve bytes are exactly CIO's zero-page IOCB, `$20-$2B`, one
  bank up.

Every call came from MyDOS at `$1294`.  The code around it:

    $1282  ldy #$F4
    $1284  lda $FF2C,y     ; $FF2C + $F4 = $10020
    $1287  sta ICHID,x
    ...
    $1291  jsr $1300       ; -> jmp (INITAD): our unpacker
    $1294  ...
    $1297  ldy #$F4
    $1299  lda ICHID,x
    $129c  sta $FF2C,y

MyDOS saves CIO's zero-page IOCB across the `INITAD` call by stashing it
in the IOCB it is loading through, and it reaches `$0020` as `$FF2C +
$F4`, because **a 6502 wraps at 64 KB**.  **A 65816 does not** -- not in
native mode and not in emulation mode either: absolute indexed and
`(zp),y` carry into the next bank.  So on the 65816 the save reads
`$010020-$01002B`, our unpacker writes chunk 0 there, and the "restore"
writes the stale snapshot back over it.  Every call.  The chunk that
filled those bytes came out zeros every time.

The other five wrong bytes -- `$014809`, `$014885`, `$014989` and so on
-- were never a second bug.  They are LZ matches in later chunks that
copy from the zeroed bytes.

This is **the real chip's behaviour**, not an emulator quirk: it would
have done exactly this on the user's 130XE.

## The fix, and where it lives

Not in MyDOS, which is somebody else's and was right on the CPU it was
written for.  In the link: **bank `$01`'s first page is nobody's.**
`$010000-$0100FE` is where *any* 6502 code lands when it leans on the
wrap -- `lda $FFxx,y`, `(zp),y` from a pointer above `$FF00` -- so it is
the page to give up, and 256 bytes of a 16 MB machine is the price.

`src/gem4xe.scm` already had a hole of this shape: 256 bytes at `$D500`
in every far bank, for an Altirra fault.  The new one sits beside it as
`wrap-page-end`, and `far-banks` applies it whatever start address a
caller links with, so the rule is in one place and not in four
Makefile lines.  The far image now starts at `$010100`.  MyDOS still
writes its twelve bytes into bank `$01` on every `INITAD`; they just
land somewhere nothing lives.

## And MyDOS's `$070A` is not a drive map

With the image arriving whole, the desktop came up under MyDOS for the
first time -- with one drive icon, labelled **D**.  `Drvmap` returns DOS
2's `DRVBYT` at `$070A` as a bitmap, and MyDOS keeps `$08` there on a
one-drive machine: bit 3, drive D.

What `$070A` *means* to MyDOS was not looked up, so it is not guessed
at.  What is certain is that MyDOS signs its boot record the way a
SpartaDOS does -- `$0700` is `'M'` where SpartaDOS puts `'S'` and DOS 2
puts zero -- so `dos_ident` now sets `DOS_CAP_DRVBYT` for every DOS 2
**except** MyDOS, and `gd_drvmap` trusts the byte only when that is set.
MyDOS gets what a SpartaDOS gets: A and B claimed, and `DESKTOP.INF` left
to say which icons there are.  The cartridge's own `D1:` keeps its
`DRVBYT = 1`, since its `$0700` is a `JMP`.

## The gate

`make test-mydos` (`tests/emu/mydos_boot.py`), in `make test` behind a
fixture, `[dos].mydos`:

1. **the link, on the host**: nothing of the far image below `$010100`;
2. **the disk**: MyDOS's boot flag, and `AUTORUN.SYS` byte for byte
   `build/gem.xex`;
3. **the boot**: the CPU switched, GEM settled, no IRQ fault;
4. **every byte** of the far image against the linker's output -- not a
   sample, because the old failure was twelve of 163,842;
5. **the desk** pixel for pixel against the model, with the drive map
   worked out from the disk's boot flag rather than asked of the machine.

Both fixes were taken out in turn and the gate went red each time: with
the wrap page given back, five failures including *"the far image
differs in 17 of 163842 bytes, first $010020"* -- the original report,
byte for byte; with MyDOS's `DRVBYT` trusted again, 1,474 pixels of desk
where the drive icons are.

The fixture needed one tool change.  The MyDOS disk to hand carries 64
files, and `atr.Dos2.add_file` deliberately will not reuse a deleted
entry that still has a count, so after `--sweep` its directory was as
full as before.  `mkdisk.py --compact` turns the deleted entries behind
the last file into end-of-directory; only the MyDOS rule uses it, so no
product disk changes.

## What this does and does not unlock

**MyDOS now works**, as `AUTORUN.SYS`, with the desktop, from a
double-density floppy -- and it is a DOS that can write, so *Save
desktop* and file copies behave as they do everywhere else.

**It is not shipped**, and should not be until one question is answered
that this tree has never recorded: whether MyDOS 4.50 may be
redistributed.  It is widely described as having been released to the
public domain; that needs checking against a primary source before a
MyDOS floppy goes on the release page, for the same reason the DOS 2
floppy stays home.
