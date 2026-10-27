# Phase 113 -- Install devices

A tester mounted a disk as D4: in the Ultimate 1MB loader, booted
SpartaDOS X and gem4xe, and found no icon for it.  The desk's drive icons
come from GEMDOS's `Dsetdrv` map, and SpartaDOS X keeps no map of its
drives (Programming Guide 4.50, chapter 5, has none), so since phase 50
gem4xe has answered a guess there -- D1: and D2: -- rather than ask eight
drives at every start, an absent one costing a SIO timeout.  Install icon
(phase 74) could add the icon by hand.  *Options -> Install devices*,
EmuTOS's item (`desk/deskins.c`, `ins_devices`), now does it by asking.

## Asking: Dprobe

`Dprobe` is gem4xe's own GEMDOS call, `0x1F1`, beside `Psystem`.  It asks
D1: to D8: once and keeps the answer, which `Dsetdrv` returns from then
on.  A drive is there unless the answer says nobody is: a timeout (138),
and through the DOS also no such device (130) or a drive it does not
serve (160).  An empty drive answers, and is there: an icon is for a
device, not a disk, as on the ST.  The current drive is always there.

How it asks was measured, three DOSes in `make test-m46`, each with D1:
attached and nothing else:

| DOS | first try, its root opened through the DOS | as built |
|---|---|---|
| SpartaDOS X | 1.8 s | the same: through SDX, which also knows its RAM disk |
| SpartaDOS 3.2 | 33 s -- 4.7 s for each absent drive, its retries on the OS's | 7.2 s: SIO's status command, one round of the OS's retries |
| DOS 2 | -- | 0.6 s: SIO status, and only for the drives in its own map (`DRVBYT`) |

SIO first for SpartaDOS X too cost 8.4 s.  A PBI hard disk answers SIO
as well as a floppy does, its BIOS hooking the same entry, so the
Ultimate 1MB's and SIDE's partitions are asked the same way.

## The item

`fun_devices` (src/desk/deskfun.c) is EmuTOS's: every drive that answers
gets an icon if it has none, labelled as the desk labels one (`DISK D4:`,
the resource's word), every icon whose drive does not answer goes, and
the ones that stay keep their labels.  It takes the set over from the
desk the way Install icon does, so *Save desktop* writes `#M` lines and
the next start shows the same icons without asking.  The pointer is busy
while the drives are asked.

## Not done

The desk does not notice a disk mounted while it runs; Install devices
asks when somebody chooses it.  Watching the drives while the desktop is
idle, and a disk naming its own icon (an SDFS volume name, an icon file
in its root), is the next idea, after GemARC.
