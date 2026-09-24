"""A gem4xe cartridge: the format, and the boot path.

WHY A CARTRIDGE AT ALL.  The release's own disk answers BOOT ERROR on
its own -- it carries no DOS by design and wants SpartaDOS X in the
machine -- so "download one file and look at it" does not work today.  A
cartridge needs no DOS, because gem4xe asks a D1: for reads and nothing
else at boot (docs/cartridge.md).

WHAT THIS GATE PROVES, which is the first of three steps and
deliberately only the first:

  THE IMAGE IS A CARTRIDGE.  tools/mkcar.py's header, type and checksum
  are what an Atari reads as one.  A wrong type or a wrong checksum
  gives a machine that boots straight past it -- SILENCE, not an error
  -- which is indistinguishable from broken code, and is why this is
  gated before any code goes on top of it.

  BANK 127 IS THE ONE THAT COMES UP.  An AtariMax 1 Mbit maps its LAST
  bank at reset.  Putting the bootstrap in bank 0 produces a perfectly
  valid cartridge that does nothing at all.

  THE OS CALLED BOTH ENTRIES.  CARTSTEP counts how far it got: 1 is
  CARTINI during the OS's own start-up, 2 is the jump to CARTRUN once
  the machine is up, 3 is after it printed.  A number short of 3 says
  WHICH of those did not happen, rather than leaving a blank screen to
  be guessed at.

  THE CPU SWITCH, BOTH WAYS.  A Rapidus ALWAYS cold-boots as a 6502, so
  a cartridge that ran only on a machine somebody had already switched
  by hand would be a poor first screen.  This finds the card, switches
  it, and the reset brings the machine straight back to the cartridge --
  which is EASIER here than from a disk, where farload has to force a
  cold start so the DOS runs its start-up file again.  The cartridge is
  still in the slot; the OS calls it again by itself.

  AND IT CANNOT LOOP, which is worth proving rather than reasoning
  about.  Switching resets the CPU and nothing else -- the card keeps
  its mode across it -- so the second pass finds a 65816 and stops.  The
  same image is then booted on a machine with NO Rapidus, where it must
  say so and stop rather than search forever.  Two machines, two
  answers, and they have to differ or the pair proves nothing.

  THE WHOLE SYSTEM BOOTS OFF IT, which is what the cartridge is for: the
  release's own system files on the cartridge's D1:, GEM.COM loaded by a
  .xex loader in the bootstrap, and the DESK at the end compared against
  tools/deskref.py exactly as test-boot compares the product disks.  That
  is the claim -- one file, nothing typed, nothing else to find -- and it
  would otherwise be a thing only hardware could check.

WHAT IT DOES NOT PROVE, said plainly: nothing about the boot screen's
report, the far image's arrival or the pool, all of which test-boot
already checks and none of which the cartridge changes.  What is new here
is where the bytes came from.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch, config_dir_for  # noqa: E402
import atr, mkcar, symfile, vbxeref         # noqa: E402
from m4_aes import SHOTDIR                  # noqa: E402
from product_boot import desk_model         # noqa: E402

CAR = os.path.abspath(os.path.join(ROOT, "build", "gem4xe.car"))
CAR_D1 = os.path.abspath(os.path.join(ROOT, "build", "gem4xe-d1.car"))
CAR_SYS = os.path.abspath(os.path.join(ROOT, "build", "gem4xe-sys.car"))
# A MyDOS floppy for the overlay (Makefile, build/cart-floppy.atr): the DOS
# and a HELLO.TXT whose contents are tests/fixtures/out.txt -- NOT the
# ROM's -- so which one a read gets says which layer won.
FLOPPY = os.path.abspath(os.path.join(ROOT, "build", "cart-floppy.atr"))
FLOPPY_HELLO = os.path.join(ROOT, "tests", "fixtures", "out.txt")
CD_HASDOS = 0x060C                          # src/cartd.s
CARTWLEN, CARTWSUM = 0x06B0, 0x06B2         # src/cart.s cart_wtest
STEP_WRITTEN, STEP_READBACK = 20, 21
# What cart_wtest writes, written down here from what it is for rather than
# read out of the ROM: a line, EOL and all.
SAVED_NAME = "SAVED.TXT"
SAVED_TXT = b"written through the cartridge's D1:\x9b"
MYDOS_MAP = 0x03                            # src/sys/gemdos.c: MyDOS's $070A
                                            # is not a drive map, so A and B
SYMS = os.path.join(ROOT, "build", "gem.sym")
FIXTURES = [("HELLO.TXT", os.path.join(ROOT, "tests", "fixtures", "test.txt")),
            ("OUT.TXT", os.path.join(ROOT, "tests", "fixtures", "out.txt"))]
CARTFLEN, CARTFSUM = 0x0604, 0x0606
CARTDLEN, CARTDSUM, CARTDTXT = 0x0608, 0x060A, 0x3000   # src/cart.s
STEP_DIR = 15
CARTSIG, CARTSTEP, CARTCPU = 0x0600, 0x0602, 0x0603      # src/cart.s
WANT_SIG = b"G4"
STEP_PRINTED, STEP_816, STEP_NO816 = 3, 6, 6
STEP_STAGED, STEP_NORAM = 8, 9
STEP_OPEN, STEP_SEG, STEP_RUN, STEP_BAD = 16, 17, 18, 19
CPU_816, CPU_NO816 = 1, 2
DEST = 0x010000                             # src/cart.s DEST_BANK
PAY_BANKS = 2                               # ...and PAY_BANKS
DRVBYT = 0x070A                             # src/cartd.s cd_drvbyt
MEMLO = 0x02E7                              # ...and what cd_install sets it to
                                            # with no DOS: past the
DEV_TOP = 0x0710                             # $0700 + the DOS-2-shaped sixteen
DOS_2 = 0                                   # src/sys/dos.h
FARMEM_BRK = 8                              # src/sys/farmem.h
LOAD_WAIT = 6000                            # frames to give the load; it takes
                                            # about 1,300, and the margin is for
                                            # a slower machine, not a hung one

problems = []


def word(b, addr):
    d = bytes(b.memdump(addr, 2))
    return d[0] | (d[1] << 8)


def expect_listing():
    """The directory a DOS 2 would print for the fixtures, built HERE from
    src/sys/dos.c's description of the record and not from the handler.

    That is the point of it: the handler and this agreeing is only worth
    something if this was written from the format rather than from the
    handler's output.  dos_dirline reads position 0 as the lock mark, 1 as
    a space, 2..9 as the name, 10..12 as the extension, 13 as a space and
    14..16 as the size in sectors -- and a DOS 2 sector carries 125 bytes
    of a file, rounded up.
    """
    out = b""
    for name, path in FIXTURES:
        with open(path, "rb") as f:
            n = len(f.read())
        sec = max(1, -(-n // 125))
        base, _, ext = name.partition(".")
        out += f"  {base:<8}{ext:<3} {sec:03d}\x9b".encode("latin-1")
    return out


def d1():
    """The read-only D1: -- a file opened and read through real CIO, and
    the directory, which is the half that makes a desktop show anything.

    THE CARTRIDGE DOES THE READING, through the ordinary CIOV every
    program uses, because installing a handler proves nothing: CIO will
    dispatch into a table of rubbish just as willingly.  What comes back
    here is how many bytes it got and their sum, checked against the
    files on this machine.
    """
    if not os.path.exists(CAR_D1):
        check(False, f"{CAR_D1} is not built (make build/gem4xe-d1.car)")
        return
    emu = launch(tag="m37d1", memsize="1088K", extra_args=["--cart", CAR_D1])
    b = emu.bridge
    try:
        b.frames(1500)
        step = b.peek(CARTSTEP)
        flen, fsum = word(b, CARTFLEN), word(b, CARTFSUM)
        dlen, dsum = word(b, CARTDLEN), word(b, CARTDSUM)
        print(f"  D1:  step {step}, HELLO.TXT {flen} bytes sum {fsum}, "
              f"directory {dlen} bytes sum {dsum}")
        check(step >= 11, f"D1: was never installed (step {step})")
        check(step >= 12, "D1:HELLO.TXT would not open")
        check(step >= STEP_DIR, f"the directory did not read (step {step})")

        with open(FIXTURES[0][1], "rb") as f:
            want = f.read()
        check(flen == len(want),
              f"read {flen} bytes of HELLO.TXT, not {len(want)}")
        check(fsum == sum(want) & 0xFFFF,
              f"the bytes read sum to {fsum}, not {sum(want) & 0xFFFF} -- "
              f"the length is right and the content is not, which is a bank "
              f"or a page wrong rather than a length")

        wantdir = expect_listing()
        check(dlen == len(wantdir),
              f"the listing is {dlen} bytes, not {len(wantdir)}")
        check(dsum == sum(wantdir) & 0xFFFF,
              f"the listing sums to {dsum}, not {sum(wantdir) & 0xFFFF}")

        # ...and the RECORDS, not a checksum of them.  A sum proves the
        # bytes and not their shape, and the shape is what dos_dirline
        # parses -- a listing in the wrong one reads as an empty disk.
        got = bytes(b.memdump(CARTDTXT, min(dlen, 255)))
        check(got == wantdir[:len(got)],
              f"the directory records differ:\n    got  {got!r}\n"
              f"    want {wantdir[:len(got)]!r}")
        for i in range(0, len(got) - 17, 18):
            r = got[i:i + 18]
            check(r[1] == 0x20 and r[13] == 0x20,
                  f"record {r!r} has no space at 1 and 13, which is the "
                  f"first thing dos_dirline tests")
            check(r[17] == 0x9B, f"record {r!r} does not end in EOL")
        b.screenshot(os.path.join(ROOT, "build", "shots", "m37d1.png"))
    finally:
        emu.stop()


def cart_listing():
    """D1:, as GEMDOS will read it back -- which is the cartridge's own
    directory and not a second list of one.  The size is what a DOS 2
    line can say: whole 125-byte sectors, which is what the handler
    prints and what src/sys/dos.c multiplies back up."""
    out = []
    for name, path in mkcar.system():
        n = os.path.getsize(path)
        out.append((name, 0, 0, 0, max(1, -(-n // 125)) * 125))
    return {"A:\\": out}


def floppy_copy(tag):
    """A fresh copy of the floppy for one run, with the emulator's own
    working copy of it dropped, and where that run's writes will land.
    Mounted --bootrw, AltirraSDL writes to a working copy under its
    configuration directory, keyed by the image's SHA-256, and reuses it
    on the next mount of the same bytes (tests/emu/m19_files.py has the
    account); so the pair is dropped first and read afterwards."""
    import hashlib
    import shutil
    disk = os.path.abspath(os.path.join(ROOT, "build", f"{tag}-floppy.atr"))
    shutil.copyfile(FLOPPY, disk)
    with open(disk, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    state = os.path.join(config_dir_for(tag), "disk_state", sha)
    if os.path.isdir(state):
        shutil.rmtree(state)
    return disk, os.path.join(state, "disk.atr")


def overlay():
    """THE CARTRIDGE OVER A DOS: the demonstration image with a MyDOS
    floppy in D1:, so the OS boots the DOS first ($BFFD bit 0) and the
    cartridge's D1: becomes an overlay -- the floppy on top, the ROM
    underneath (src/cartd.s).  Three things, each through the ordinary
    CIOV, each checked here against what it should be rather than what
    the cartridge reports:

      a READ of a name both layers have gets the FLOPPY's bytes -- which
      is what makes a file you saved win over the one in ROM;
      the DIRECTORY is the ROM's entries the floppy does not have, then
      the floppy's own listing, its free-sector line last (Dfree reads
      the last line);
      a WRITE goes to the floppy -- checked in the floppy IMAGE afterwards,
      not in what the machine says about it -- and reads back through the
      same D1:.
    """
    for need in (CAR_D1, FLOPPY):
        if not os.path.exists(need):
            check(False, f"{need} is not built")
            return
    disk, written = floppy_copy("m37ovl")
    emu = launch(tag="m37ovl", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk, "--cart", CAR_D1])
    b = emu.bridge
    try:
        b.frames(1500)
        step = b.peek(CARTSTEP)
        hasdos = b.peek(CD_HASDOS)
        flen, fsum = word(b, CARTFLEN), word(b, CARTFSUM)
        dlen = word(b, CARTDLEN)
        wlen, wsum = word(b, CARTWLEN), word(b, CARTWSUM)
        print(f"  over MyDOS: step {step}, a DOS underneath {bool(hasdos)}, "
              f"HELLO.TXT {flen} bytes, directory {dlen} bytes, "
              f"the write read back {wlen} bytes")
        check(hasdos == 1, "the cartridge did not find the floppy's DOS in "
                           "HATABS: it is not an overlay, it is the only D:")
        check(step == STEP_READBACK,
              f"step {step}, not {STEP_READBACK}: 15 is the listing, 20 the "
              f"write and 21 its read-back")
        with open(FLOPPY_HELLO, "rb") as f:
            want = f.read()
        check((flen, fsum) == (len(want), sum(want) & 0xFFFF),
              f"HELLO.TXT read as {flen} bytes summing {fsum}; the floppy's is "
              f"{len(want)} and {sum(want) & 0xFFFF} -- the ROM's won, or a "
              f"byte went missing")
        got = bytes(b.memdump(CARTDTXT, min(dlen, 255)))
        lines = got.split(b"\x9b")[:-1]
        rom_part = f"  {'OUT':<8}{'TXT':<3} {max(1, -(-os.path.getsize(FIXTURES[1][1]) // 125)):03d}".encode()
        check(lines[:1] == [rom_part],
              f"the listing starts {lines[:1]!r}, not the ROM's OUT.TXT alone "
              f"-- its HELLO.TXT should be hidden by the floppy's")
        names = [ln[2:13].decode("latin-1") for ln in lines[1:]]
        for n in ("DOS     SYS", "DUP     SYS", "HELLO   TXT"):
            check(n in names, f"the floppy's {n.split()[0]} is not in the listing")
        check(bool(lines) and b"FREE" in lines[-1].upper(),
              f"the last line is {lines[-1:]!r}, not the floppy's free-sector "
              f"line, which Dfree reads the last line for")
        check((wlen, wsum) == (len(SAVED_TXT), sum(SAVED_TXT) & 0xFFFF),
              f"the write read back as {wlen} bytes summing {wsum}, not "
              f"{len(SAVED_TXT)} and {sum(SAVED_TXT) & 0xFFFF}")
    finally:
        emu.stop()
    if not check(os.path.exists(written),
                 f"the emulator left no working copy of the floppy at {written}"):
        return
    fs = atr.Dos2(atr.ATRImage.load(written))
    on = {e.filename.upper() for e in fs.entries() if e.in_use}
    check(SAVED_NAME in on, f"{SAVED_NAME} is not on the FLOPPY: the write "
                            f"went somewhere else")
    if SAVED_NAME in on:
        check(fs.read(SAVED_NAME) == SAVED_TXT,
              f"{SAVED_NAME} on the floppy holds {fs.read(SAVED_NAME)!r}")
    check(fs.read("HELLO.TXT") == want, "the floppy's HELLO.TXT changed")
    print(f"  the floppy afterwards: {', '.join(sorted(on))}")


def whole_system(floppy=False):
    """THE CARTRIDGE THE REQUEST ASKED FOR: one file, put in a slot, and
    the desktop comes up with nothing typed and nothing else to find.

    Everything in front of this is transport; this is the product.  The
    bootstrap loads D1:GEM.COM with a .xex loader of its own -- the one
    job of a DOS that read-only did not make go away -- and the desk at
    the end is compared with tools/deskref.py, the desktop's own model,
    exactly as test-boot compares the two product floppies.  A cartridge
    that came up with the wrong desk would otherwise be something only
    hardware could notice.

    The load is TIMED and the time printed.  It is the one number a
    person will feel, and a change in it -- the system growing, the
    handler getting slower -- should be visible rather than discovered.
    """
    if not os.path.exists(CAR_SYS):
        check(False, f"{CAR_SYS} is not built (make build/gem4xe-sys.car)")
        return
    syms = symfile.load(SYMS)
    tag = "m37sysfl" if floppy else "m37sys"
    extra = ["--cart", CAR_SYS]
    if floppy:
        # WITH A DOS UNDERNEATH: the system still loads from the ROM -- the
        # floppy has no GEM.COM -- and the AES's *.ACC scan still finds the
        # ROM's accessories through the overlay's listing.
        disk, _ = floppy_copy(tag)
        extra = ["--disk", disk] + extra
    emu = launch(tag=tag, memsize="1088K", extra_args=extra)
    b = emu.bridge
    try:
        step = 0
        for t in range(0, LOAD_WAIT, 25):
            b.frames(25)
            step = b.peek(CARTSTEP)
            if step >= STEP_RUN:
                break
        print(f"  the whole system{' over MyDOS' if floppy else ''}: "
              f"step {step} after {t + 25} frames "
              f"({(t + 25) / 50:.0f}s of PAL time to read it off the ROM)")
        check(step != STEP_BAD, "the bootstrap would not load D1:GEM.COM: it "
                                "read the file and it is not an Atari binary")
        check(step >= STEP_OPEN, f"D1:GEM.COM would not open (step {step}) -- "
                                 f"is it on the image?")
        if not check(step >= STEP_RUN,
                     f"the load never reached the run vector (step {step})"):
            return
        # ...and the machine's own DOS-shaped variables, which on a
        # cartridge nothing else owns (src/cartd.s).
        check(b.peek(CD_HASDOS) == int(floppy),
              f"the cartridge says a DOS is {'absent' if floppy else 'present'}")
        if floppy:
            # MyDOS's, and not a drive map: A and B are claimed instead
            drvbyt = MYDOS_MAP
        else:
            drvbyt, memlo = b.peek(DRVBYT), b.peek16(MEMLO)
            check(drvbyt == 1, f"DRVBYT is {drvbyt}, not 1 -- Drvmap returns "
                               f"that byte and the desktop draws an icon per bit")
            check(memlo == DEV_TOP, f"MEMLO is ${memlo:04X}, not ${DEV_TOP:04X}: "
                                    f"the sixteen bytes at $0700 are not protected")

        calls = syms["app_calls"]
        n, still = b.peek16(calls), 0
        for t in range(0, 20000, 250):
            b.frames(250)
            now = b.peek16(calls)
            still = still + 1 if now == n else 0
            n = now
            if still >= 2 and now:
                break
        else:
            check(False, f"GEM never settled ({n} calls)")
        fault = b.peek(syms["irq_fault"])
        check(fault == 0, f"irq_fault {fault} (src/sys/irq.s)")
        kind = b.peek(syms["dos"])
        check(kind == DOS_2, f"the system calls this a kind-{kind} DOS, not "
                             f"DOS 2 -- dos_ident read $0700 as something else")
        mark = b.peek16(syms["app_near"])
        brk = int.from_bytes(bytes(b.memdump(syms["farmem"] + FARMEM_BRK, 4)),
                             "little")
        pointer = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        room = (b.peek16(syms["app_pool_hi"]) - b.peek16(syms["pool_brk"])) & 0xFFFF
        # THE DESK PICTURE DOES NOT SHOW THE ACCESSORIES, so it must not
        # be what says they loaded.  The AES finds them by opening the
        # system's directory and reading it a line at a time (src/aes/shel.c)
        # -- the one thing the real system does with this handler that
        # the read-back above does not -- and a cartridge that served
        # files but listed nothing would give a desk identical to this
        # one.  sh_naccs is the witness: the model has no opinion about
        # it, so the two agreeing here is not the two agreeing wrongly.
        naccs, full = b.peek16(syms["sh_naccs"]), b.peek16(syms["sh_accfull"])
        want = sum(1 for name, _p in mkcar.system() if name.endswith(".ACC"))
        check(naccs + full == want,
              f"the AES found {naccs + full} accessories on the cartridge, "
              f"not the {want} that are on it -- the *.ACC scan reads the "
              f"DIRECTORY, which the file read-back above never touches")
        print(f"  GEM settled {n} calls in, DOS kind {kind}, drive map "
              f"{drvbyt:#04x}, pool ${mark:04X} with {room} bytes left, "
              f"{naccs} accessor{'y' if naccs == 1 else 'ies'} running"
              + (f" and {full} with no room" if full else ""))
        ref_v, ref_a, d = desk_model(mark, brk, pointer, drvbyt, cart_listing())
        check(len(ref_a.shots) == 1, f"the model took {len(ref_a.shots)} shots")
        os.makedirs(SHOTDIR, exist_ok=True)
        shot = os.path.join(SHOTDIR, f"{tag}-desk.png")
        b.screenshot(shot)
        bad, shown = vbxeref.compare_to_shot(ref_a.shots[0], shot)
        check(not bad, f"the desk off the cartridge, {bad} px differ from the "
                       f"model; first {shown[:3]}")
        print(f"  the desk {'ok' if not bad else 'FAIL'} against the model, "
              f"booted from one file with nothing typed")
    finally:
        emu.stop()


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def main():
    print("gem4xe-m37: a cartridge")

    # The file first, on the host: a bad header is cheaper to find here
    # than by watching a machine ignore it.
    with open(CAR, "rb") as f:
        car = f.read()
    check(car[:4] == b"CART", f"the file starts {car[:4]!r}, not b'CART'")
    ctype = int.from_bytes(car[4:8], "big")
    check(ctype == mkcar.CART_TYPE_MAXFLASH_1M,
          f"cartridge type {ctype}, not {mkcar.CART_TYPE_MAXFLASH_1M} "
          f"(AtariMax 1 Mbit)")
    rom = car[16:]
    check(len(rom) == mkcar.BANK * mkcar.BANKS,
          f"{len(rom)} bytes of ROM, not {mkcar.BANK * mkcar.BANKS}")
    want = int.from_bytes(car[8:12], "big")
    check(sum(rom) & 0xFFFFFFFF == want,
          "the checksum in the header is not the sum of the ROM, so "
          "Altirra will refuse the image")

    # ...and that the bootstrap is in the bank the machine comes up on.
    boot = rom[mkcar.BOOT_BANK * mkcar.BANK:(mkcar.BOOT_BANK + 1) * mkcar.BANK]
    check(boot[-4] == 0,
          f"$BFFC of bank {mkcar.BOOT_BANK} is ${boot[-4]:02X}, not 0: the "
          f"OS does not see a cartridge there")
    check(boot[-3] & 0x04,
          f"$BFFD is ${boot[-3]:02X}, and bit 2 is what makes the OS jump "
          f"to CARTRUN")
    check(boot != bytes([mkcar.ERASED]) * mkcar.BANK,
          f"bank {mkcar.BOOT_BANK} is erased -- the bootstrap went "
          f"somewhere else, and a cartridge that maps an empty bank at "
          f"reset is valid and does nothing")

    for tag, rapidus, want_step, want_cpu, what in (
            ("m37", True, STEP_STAGED, CPU_816,
             "a Rapidus, cold-booted as a 6502 as one always is"),
            ("m37no816", False, STEP_NO816, CPU_NO816,
             "a plain 6502 with no accelerator")):
        emu = launch(tag=tag, memsize="1088K", rapidus=rapidus,
                     extra_args=["--cart", CAR])
        b = emu.bridge
        try:
            # Long enough for the switch, the CPU reset and the second pass.
            b.frames(900)
            sig = bytes(b.memdump(CARTSIG, 2))
            step, cpu = b.peek(CARTSTEP), b.peek(CARTCPU)
            print(f"  {what}: CARTSIG {sig!r}, CARTSTEP {step}, CARTCPU {cpu}")
            check(step >= 1, f"{tag}: the OS never called CARTINI -- it did "
                             f"not see a cartridge at all (the header, or "
                             f"the type)")
            check(step >= 2, f"{tag}: CARTINI ran and the OS never jumped to "
                             f"CARTRUN: $BFFD bit 2")
            check(step >= STEP_PRINTED,
                  f"{tag}: CARTRUN ran and never finished printing")
            check(sig == WANT_SIG, f"{tag}: CARTSIG {sig!r}, not {WANT_SIG!r}")
            check(step == want_step, f"{tag}: CARTSTEP {step}, not {want_step}")
            check(cpu == want_cpu, f"{tag}: CARTCPU {cpu}, not {want_cpu}")
            if want_cpu == CPU_816:
                # ...and every byte of the payload, out of the cartridge
                # and into far memory.  Compared HERE rather than by the
                # cartridge: what the machine says about its own copy is
                # worth less than what the copy says.
                bad = 0
                for k in range(PAY_BANKS):
                    got = bytes(b.memdump(DEST + k * mkcar.BANK, mkcar.BANK))
                    want = mkcar.test_pattern(k)
                    n = sum(1 for x, y in zip(got, want) if x != y)
                    print(f"    bank {k} -> ${DEST + k * mkcar.BANK:06X}: "
                          f"{mkcar.BANK - n}/{mkcar.BANK} bytes")
                    bad += n
                check(bad == 0, f"{tag}: {bad} byte(s) of the payload did not "
                                f"arrive -- the pattern depends on the offset "
                                f"AND the bank, so a swap or a doubled bank "
                                f"shows here too")
            b.screenshot(os.path.join(ROOT, "build", "shots", f"{tag}.png"))
        finally:
            emu.stop()

    # ...and the two answers must differ, or the pair proves nothing: a
    # cartridge that said CPU_816 on every machine would pass the first
    # case and be wrong about the second.
    check(CPU_816 != CPU_NO816, "the two machines are expected to give the "
                                "same answer, so this gate is vacuous")

    d1()
    overlay()
    whole_system()
    whole_system(floppy=True)

    print(f"\ngem4xe-m37: {'PASS' if not problems else 'FAIL'} -- a "
          f"cartridge, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
