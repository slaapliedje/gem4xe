# A gem4xe cartridge

One file you download, put on a flash cartridge, and look at.
**Read-only**, which is the detail that decides everything below: it
means there is no DOS to write, and most of what a DOS is does not have
to exist.

---

## 1. The barrier it would remove is real

The public release ships `gem4xe-0.6.1.atr`, and **it does not boot on
its own**.  It carries no DOS by design: it boots under SpartaDOS X,
which lives in the machine rather than on the disk.  Run it without one
and you get a blue screen of `BOOT ERROR`, which is what I got the first
time I pointed the kit's own screenshot tool at it.

The release page says so honestly and points at
<https://sdx.atari8.info/> -- but "download SpartaDOS X separately, work
out which image, put it in your cartridge slot" is three steps before
anything happens.  There is a `gem-boot.atr` in this tree that boots
standalone into the desktop with nothing typed, and the public release
leaves it out because **the DOS on it is not gem4xe's to give away**.

So: the thing standing between a newcomer and the desktop is a DOS
licence, not a technical problem.

## 2. The memory map is already clear

`src/gem4xe.scm` has said this since the map was written:

    $A000-$BFFF  NOT OURS: SpartaDOS X is a cartridge and this is it.
                 Under a disk DOS it is RAM and gem4xe leaves it alone.

gem4xe runs with a cartridge in that window every time it boots under
SDX, and it never touches it.  `$8000-$9BFF` is the MEMAC window and is
borrowed only at LOAD time, by `farload.s`'s staging buffer.

**So a cartridge costs gem4xe nothing and needs no change to the map.**
That was the thing most likely to sink this, and it does not.

## 3. It does not need a DOS

The request is for a **demo**: something to put on a flash cartridge and
look at.  Read-only is fine.  That is not a small relaxation, it is most
of the problem.

**What a DOS mostly is, is the write side** -- a free-sector bitmap,
allocation, a VTOC, directory maintenance, the whole business of
changing a disk without corrupting it.  A read-only device needs none of
it.

What gem4xe actually asks a `D1:` for, and this is the complete list:

| | |
|---|---|
| open a file by name, read it, close it | `DESKTOP.PRG`, `DESKTOP.RSC`, `LANG.RSC`, the accessories, the extensions, and anything you double-click |
| a directory | opened as `D1:*.*` and read as text -- **17-character records**, `src/sys/dos.c`'s `DIRLINE`, which is DOS 2's own format |
| which drives exist | a bitmap |

That is a **CIO device handler**, not a DOS: a `D` entry in HATABS and a
handful of vectors over a directory laid out in ROM.  Hundreds of lines
of 6502, not thousands, and the directory-as-text format is the easiest
thing in the world to generate from a table.

**And nothing writes at boot.**  There are exactly three write sites in
the whole system -- `CPX_Save` (`src/apps/cpanel.c`), *Options -> Save
desktop* (`src/desk/deskwin.c`) and a file copy (`src/desk/deskfun.c`)
-- and all three are things a person does on purpose, after the desktop
is up.  `CPX_Save` already reports failure through `xcpb->ok`, and the
other two already put up an alert.  So a read-only disk **boots to a
complete desktop** and only disappoints somebody who tries to save.

That is the answer to "do we need an open source DOS": **no.**

## 4. What it still has to carry

A cartridge containing *only* gem4xe still boots a machine with **no
D1: at all**, and the shell's first act is to load `DESKTOP.PRG` from a
disk that is not there.  So it brings its files with it.  Three pieces:

1. **A bootstrap.**  The cart's init runs on the 6502 -- a Rapidus
   cold-boots as one -- finds the accelerator, switches it, and stages
   the image bank by bank from the cart window into far memory.  This is
   `src/farload.s`'s job with a different source, and that code already
   exists, already identifies the CPU before its first store, and
   already refuses a machine it cannot run on.
2. **The read-only CIO handler** of section 3.  This is the piece that
   does not exist, and it is what lets **gem4xe itself stay completely
   unchanged**: it sees a DOS-2-shaped device and never knows.
3. **A packer**, `tools/mkcar.py`, laying the banks out and writing the
   16-byte `.car` header.

## 5. The type, and the sizes

**AtariMax 1 Mbit (`MaxFlash_1024K`)**: 128 banks of 8 KB at
`$A000-$BFFF`.  That is the type SpartaDOS X's own cartridge image uses,
so it is proven on this rig, in Altirra, and on an Ultimate Cart.
MegaCart 512K/1M/2M are the alternatives if a 16 KB window turns out to
be easier to stage from.

    GEM.COM                    112,831
    DESKTOP.PRG                 41,745
    resources, accessories      ~30,000
    the system, near enough    ~190 KB   against 1 MB

Comfortable, with room for `\APPS\` and a few documents so there is
something to double-click.

**And it is testable**: Altirra takes `--cart`, so a gate can boot the
`.car` and compare the desk against the model exactly as `test-boot`
does today.  That matters -- this would otherwise be a feature only
hardware could check.

## 6. The disk route, which this replaces rather than needs

The earlier draft of this document recommended finding a freely
redistributable DOS first, and putting it on `gem-boot.atr` -- which
already boots standalone into the desktop and is left out of the public
release only because its DOS is not gem4xe's to give away.

**That is no longer the prerequisite.**  It was the recommendation while
"the cartridge needs a file system, therefore it needs a DOS" was the
reading; section 3 is why it does not.  The cartridge is now the
*shorter* path to a thing somebody can download and run, because a
read-only handler over a ROM directory is smaller than finding, testing
and shipping somebody else's DOS.

It keeps an independent value, and a real one: a bootable `.atr` serves
everybody with a FujiNet, an SDrive, an SD cartridge or a real drive,
and a `.car` serves only people with a cartridge that takes one.  So it
is worth doing **after**, not before.  When it is:

- **MyDOS is the obvious candidate and MyDOS mangles the staged far
  image** (`docs/shipping.md` §2 -- twelve bytes lost at bank `$01`
  +`$20`, deterministic, both versions, both load paths, cause unknown).
  A bug hunt, and the answer is worth having whatever is decided here.
- **BW-DOS** is the other candidate and has never been tried.

## 7. FujiNet

FujiNet is an SIO device -- disks, printer, network -- with no cartridge
port, so it cannot present a `.car` to the machine.  What it can do is
**fetch one**, which is what "downloaded from FujiNet" means: the file
arrives over the network and goes onto the flash cartridge.  Nothing
here depends on that, and nothing here has to serve it.

## 8. The order to build it

1. **The packer and the bootstrap.**  DONE, 2026-09-23 --
   `tools/mkcar.py`, `src/cart.s`, `src/cart.scm`, gated as `test-m37`.
   A 1 MB AtariMax image whose bank 127 the machine comes up on, boots,
   prints and can be read back.  The gate checks the header on the host
   *and* the boot on the machine, because a wrong type or a wrong bank
   gives a cartridge that is perfectly valid and does nothing -- silence,
   not an error, which is indistinguishable from broken code.  Confirmed
   by moving the bootstrap to bank 0 and watching it say so.

   Two things it settled.  The Calypsi linker drops an object nothing
   references, so every cartridge section is `root` -- without it the
   link succeeds and produces an empty ROM.  And **never read `$D5xx`**:
   real AtariMax hardware switches bank on a read of that page and this
   tree's Altirra deliberately does not, so code that reads it works
   here and changes bank under itself on a real cartridge.

   Still to come in this step: the CPU switch, which is
   `src/farload.s`'s `fl_no816` with the cart's own re-entry after the
   reset instead of a DOS's.
2. **The read-only `D1:`**, with the directory a table the packer
   writes.  gem4xe does not change.
3. **The whole system on it**, and a gate: Altirra takes `--cart`, so
   booting the `.car` and comparing the desk against the model is the
   same shape as `test-boot`.  This would otherwise be a feature only
   hardware could check, and it is not.

The demo it produces is a machine that comes up in the desktop with
drive icons, a folder to open, accessories in the Desk menu and a
program to double-click -- from one file, with nothing typed and nothing
else to find.
