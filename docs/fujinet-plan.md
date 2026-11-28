# The FujiNet browser: plan

A GEM program for a FujiNet on the serial bus.  It browses the TNFS
hosts the FujiNet knows, walks their folders, and mounts a disk image
into one of the eight drive slots.  It also shows and sets the
FujiNet's Wi-Fi and host list, which makes it the "FujiNet
configurator" that the 0.19 notes promised.  It is one kit program
built for both CPUs: `FUJINET.PRG` for the 65C816 and `FUJINET.G6A` for
the 6502.  On the 6502 it is the first application beyond the desktop
and the Control Panel.

## What the FujiNet takes

Everything here comes from the FujiNet's own sources, read 2026-11-27:
`fujinet-firmware` 3a30a5f (`include/fujiCommandID.h`,
`lib/device/fujiDevice/`, `lib/device/sio/sioFuji.*`) and `fujinet-lib`
e90dd5f (`include/fujinet-fuji.h`, `fujinet-const.h`).  Both are GPLv3.
We take the protocol from them, the way the ST's sources are taken: as
a specification.  No code is copied.

The FujiNet answers as SIO device **$70**, unit 1.  Every command is an
ordinary SIO frame: DCOMND is the command, DAUX1 and DAUX2 carry its
parameters, and the payload is a read, a write or nothing.

| Command | DCOMND | AUX1 / AUX2 | Data |
|---|---|---|---|
| Read host slots | $F4 | -- | read 8 x 32: host names, NUL-padded |
| Write host slots | $F3 | -- | write 8 x 32 |
| Read device slots | $F2 | -- | read 8 x 38: host slot, mode, 36-byte file name |
| Write device slots | $F1 | -- | write 8 x 38 |
| Mount host | $F9 | host slot | -- |
| Unmount host | $E6 | host slot | -- |
| Open directory | $F7 | host slot | write 256: path, NUL, optional filter, NUL |
| Read directory entry | $F6 | max length / flags | read `max length` |
| Close directory | $F5 | -- | -- |
| Set directory position | $E4 | position, 16 bits | -- |
| Set device full path | $E2 | device slot / host << 4 \| mode | write 256: the path |
| Get device full path | $DA | device slot | read 256 |
| Mount image | $F8 | device slot / mode (1 read, 2 read-write) | -- |
| Unmount image | $E9 | device slot | -- |
| Get Wi-Fi status | $FA | -- | read 1 |
| Get SSID | $FE | -- | read 33 + 64: SSID, password |
| Set SSID | $FB | -- | write 33 + 64 |
| Scan networks | $FD | -- | read 4: the count in byte 0 |
| Get scan result | $FC | index | read 33 + 1: SSID, RSSI |
| Get adapter config | $E8 | -- | read 140: SSID, host name, IP, gateway, mask, DNS, MAC, BSSID, firmware version |

**A directory entry** is a NUL-terminated name, with `/` on the end of
a folder.  Two bytes of $7F mean the listing is over.  With AUX2 bit 7
set, 13 bytes come first:

- the date and time, 6 bytes, the year counted from 1970;
- the size, 4 bytes, little-endian;
- a folder flag;
- a truncated flag;
- the media type.

AUX2 $C0-$FF asks for a block of entries in one frame.  That is faster,
but it is a later step.

## What gem4xe needs first

**A program cannot send an SIO frame today.**  The kernel's `sio_devt`
(`src/sys/cio.c`) does it for disks and for the clock, with the timer-1
sampler stopped and resynchronised around the call.  That is the
MiSTer fix from test-d6sio.  A program must go through the same path,
never through SIOV of its own.

So step 2 adds one gem4xe GEMDOS call, numbered next after Drwsec:

    LONG Dsio(WORD dev, WORD cmd, WORD aux, WORD dir, void *buf, WORD len)
    GD_DSIO 0x1FB

- **Only device $70** is accepted at first.  Anything else answers
  `EINVFN`.  A program must not be able to write sectors behind G4DOS's
  back.  The network devices $71-$78 can be allowed later, if a program
  wants them.
- `len` is at most 512: the device slots are 304 bytes.  The kernel copies the buffer through a bank-$00
  bounce buffer, so the program's buffer may be far on both CPUs.
- The SIO status is the answer: 1 is OK; anything else is the OS's
  error, which comes back negative.

## Steps

1. **A FujiNet the gates can reach.**
   - Altirra has none built in.  FujiNet-PC (the firmware built for
     Linux) talks NetSIO to Altirra through a custom device.  Our
     AltirraSDL does compile the custom device; whether NetSIO works
     through it has not been tried.
   - Set it up with a local `tnfsd` serving a fixture folder: a few
     folders, ATRs, a long name and an empty folder.
   - If NetSIO cannot be made to work, the fallback is a stand-in $70
     device written as an Altirra custom device script.  It would
     answer the commands above from a fixture.
   - DONE when a bridge script reads the host slots and lists the
     fixture folder.
   - **Probe passed 2026-11-27**, not yet a gate.
     - The rig:
       - FujiNet-PC 3a30a5f, built with CMake, `-DFUJINET_TARGET=ATARI`,
         against Arch's mbedtls3.
       - Its config sets `[BOIP] enabled=1 host=localhost` and Host1 =
         SD; the SD folder holds the fixture.
       - The NetSIO hub (`python3 -m netsiohub`, from
         fujinet-emulator-bridge 59d41f8) on UDP 9997 and TCP 9996.
       - AltirraSDL with `--adddevice custom,path=.../netsio.atdevice`.
     - Through SIOV from a 64K XL, every command answered with status
       1:
       - Read host slots and Read device slots: "SD", and eight empty
         drives (host $FF).
       - Mount host and Open directory `/GAMES/`.
       - Read directory entry with AUX2 $80: `DEMOS/` (folder flag 1),
         `calc2.atr` (size 327696, media 1), `edit-test.atr`, then
         $7F $7F.
       - Close.
     - Without the hub, every command times out (status 138).
     - FujiNet-PC exits with 75 ("restart me") after a minute with no
       hub; it must be run in a loop, as its own `run-fujinet` does.
2. **Dsio**, in `src/sys/gemdos.c` for both CPUs, with the kit's
   binding.
   - A host test checks the argument checks and the bounce copy.
   - A gate on each CPU sends a frame and gets the answer from step 1.
   - Break-run: send to device $31 and see `EINVFN`.
   - **Built 2026-11-27**, uncommitted.
     - The call is `Dsio(dev, cmd, aux, dir, len, buf)`: `dir` is
       DS_NONE, DS_READ or DS_WRITE, and `buf` comes last, as in
       Drwsec.  It answers 0, EDRVNR, EUNCMD or ERROR; the kit gains
       TOS's `ERROR` (-1).
     - The kernel side is `sio_fuji` in `src/sys/cio.c`.
     - Both systems build with it, and the binding test covers it.
     - `make test-dsio` (`tests/emu/dsio_fuji.py`) passes on the
       65C816 against the step-1 rig.  It is not in `make test`.
     - The 6502 has no GEMDOS runner, so its path is first gated by
       the browser itself, in step 4.
     - Break-run: with the copy back to the caller removed, every read
       came back as the fill pattern.
   - **Found:** opening a missing folder does not come back as ERROR.
     - The FujiNet answers the first try with an error.  The OS's SIO
       then retries the command once, and that retry's 256-byte data
       frame is not taken, so the call ends in a timeout (EDRVNR).
     - This was seen over NetSIO; whether a real FujiNet does the same
       is not known.
     - So the browser must ask the FujiNet again (Read host slots)
       before it says there is none.
3. **The protocol in C**, `src/apps/fujicmd.c`: one function per
   command in the table, with the frame layouts as structs.  Each
   layout is checked against the sizes above at compile time, under
   both compilers, because of B7: never measure a struct with an array
   bound.
4. **The browser.**
   - One window lists the eight host slots.  Opening a host lists its
     root, and opening a folder goes down a level.  A Close box at a
     folder goes up a level.  The info line shows the path and the
     count.
   - A disk image is mounted with a dialog: drive D1:-D8:, read-only or
     read-write.  The program sets the device path, mounts the image,
     and writes the device slots back so the FujiNet keeps the slot
     after a reboot.
   - A Drives window lists the eight device slots, with Eject.
5. **Settings.**
   - A dialog edits the host slots.
   - A Wi-Fi dialog shows the status and the adapter config (IP and
     firmware version), scans for networks and picks one.
   - The password is typed, sent once and never kept or shown.  The
     FujiNet's own Get SSID answers with it, so the program blanks it
     before anything is drawn.
6. **Mounting under a running system.**  This is the risky step.
   - The disk in a slot changes under G4DOS and under any open drive
     window.  The program tells the kernel that the drive's media
     changed, so G4DOS drops what it had cached and the desktop
     redraws that drive's window.
   - Remounting **the drive the system was booted from** is refused,
     with an alert saying why.  The 6502 system still loads its
     resources and the Control Panel from it.
   - A gate mounts an image into D2:, opens D2:'s window, and sees the
     new disk's files.
7. **Ship it.**
   - The program goes on the applications floppy and on the 6502
     floppy.
   - Gates: `test-fuji` on the 65C816 and `test-fuji6` on the 6502,
     both in `make test`.
   - A section in the guide, and a row in docs/gates.md.

## Open questions

- **The name on the desktop:** decided 2026-11-27, "FujiNet".
- **Mount and reboot:** decided 2026-11-27, yes.  A *Mount and
  reboot* button in the mount dialog mounts the image into D1:, writes
  the device slots, turns the FujiNet's CONFIG boot off (Config boot
  $D9, AUX1 0) and cold-starts the machine.  It asks first, because
  anything unsaved is lost.  This is the one case where D1: may be
  replaced, since nothing of the running system survives it.

## Risks

- **The serial bus.** Every frame goes through the path test-d6sio
  gated, but no gate has had a real FujiNet on it.  Real hardware
  is the only test for timing.  The 600XL tester also has a SUBCart on
  the same bus.
- **Speed.** A directory of 200 entries is 200 frames of about 40
  bytes at 19,200 baud: a few seconds.  The block mode in step 4's
  follow-up is the cure if it is too slow.
- **The 6502's room.** The program must fit the 6502's banks with the
  desktop loaded.  How big it may be is measured in step 4, not
  guessed.
