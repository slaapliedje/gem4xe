# A gem4xe cartridge

Asked for so that somebody can download one file, put it on an Ultimate
Cart, and have a look.  Worth doing, and **a cartridge on its own is not
enough** -- the reason is one layer further down than it looks.

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

## 3. What a cartridge cannot do by itself

gem4xe reaches every file through CIO and a DOS -- `src/sys/dos.c`
identifies `DOS_2`, `DOS_SPARTA` or `DOS_SDX` and works through it.  A
cartridge that contains only gem4xe boots a machine with **no D1: at
all**, and the shell's first act is to load `DESKTOP.PRG` and
`DESKTOP.RSC` from a disk.  There is no disk.

So the cartridge has to bring a file system with it.  Three pieces:

1. **A bootstrap.**  The cart's init runs on the 6502 -- a Rapidus
   cold-boots as one -- finds the accelerator, switches it, and stages
   the image bank by bank from the cart window into far memory.  This is
   `src/farload.s`'s job with a different source, and that code already
   exists, already identifies the CPU before its first store, and
   already refuses a machine it cannot run on.
2. **A read-only CIO handler** that serves the system files out of cart
   banks as `D1:`.  This is the piece that does not exist.  It is
   ordinary Atari work -- a `D:` device in the HATABS, a handful of
   vectors, a directory in ROM -- and it is what lets **gem4xe itself
   stay completely unchanged**: it would see a DOS-2-shaped device and
   never know.
3. **A packer**, `tools/mkcar.py`, laying the banks out and writing the
   16-byte `.car` header.

## 4. The type, and the sizes

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

## 5. The cheaper thing, named because it may be the better one

**Put a freely redistributable DOS on `gem-boot.atr`.**  That disk
already boots standalone into the desktop; only its DOS stops it
shipping.  Swap the DOS and the public release gains a one-file,
no-cartridge, works-everywhere boot disk -- and **FujiNet serves `.atr`
images**, so that is the path a FujiNet user wants anyway.

What stands in the way is a bug rather than a licence: **MyDOS is the
obvious free candidate and MyDOS mangles the staged far image**
(`docs/shipping.md` §2 -- twelve bytes lost at bank `$01` +`$20`,
deterministic, both versions, both load paths, cause unknown).  BW-DOS
is the other candidate and has never been tried here.

That is a bug hunt, not a subsystem.  It is much less work than section
3 and it helps the larger group of people -- anybody with a FujiNet, an
SDrive, an SD cartridge or a real drive -- where the `.car` helps people
with a cartridge that takes one.

## 6. A question about FujiNet

FujiNet is an SIO device: it serves disk images, printers and network,
and it has no cartridge port.  "Downloaded from FujiNet" most likely
means fetching the file over the network rather than booting a `.car`
through it -- in which case what wants to be downloadable is the
**disk image**, and section 5 is the whole answer.  Worth settling
before either is built.

## 7. Recommendation

Both, in this order:

1. **Find a free DOS that does not mangle the staged image.**  Small,
   unblocks the public release immediately, and serves FujiNet, SDrive
   and real drives alike.  The MyDOS fault is a real bug in this tree's
   loader or a real incompatibility, and either is worth knowing.
2. **Then the cartridge**, which is the nicer artifact and the bigger
   build: bootstrap, ROM-disk handler, packer, gate.

Doing 2 without 1 leaves the disk images still needing SpartaDOS X.
Doing 1 without 2 leaves the Ultimate Cart owners without their one
file.  They are not alternatives; one is just much cheaper.
