# Phase 154 -- a refused write leaks, it does not corrupt

Found testing 0.15 on the MiSTer core (2026-11-12).  On the G4DOS system
floppy a folder was made, renamed and moved by name, all correctly.
After the move, the core's emulated drive stopped answering for about
half a minute: every listing came back empty and PREFS.RSC was "not on
the disk".  Then the next New folder was refused part way.  The disk was
left with the new folder's entry and map written but its two sectors
still marked free, so the next file made could have been written over
them.

The drive's failures are the core's, or the MiSTer's way of writing an
image to its SD card.  They were never reproduced in the emulator, and
are a known issue for 0.15.  But a real drive refuses writes too -- a bad
sector, a write-protect tab, a disk taken out mid-write, a read-only
FujiNet slot -- and what the engine left on the disk then was gem4xe's.

| | was | now |
|---|---|---|
| the order a sync writes in | data, maps, directories, then the bitmap | the bitmap, then data, maps, directories |
| a chain given back (delete, remove a folder, a file emptied) | freed in the bitmap at once | queued, and freed at the sync, after the directories that stopped pointing at it |
| a new map page | written with the rest | written before the page that links to it |
| a refusal part way through | a used sector could be left marked free | sectors can leak: marked used, nothing using them, the free count behind |

## The rule

A sector is marked used before anything points at it, and freed only
after nothing does.  Then a refused write can leave sectors that are used
in the bitmap and referenced by nothing, which wastes them.  It can never
leave a sector that something references marked free, where the next
allocation would hand it out a second time.

Until now a chain given back was freed in the cached bitmap at once,
before the directory change that stopped pointing at it.  A delete freed
the file's chain and then removed its entry; emptying a file freed its
chain and only then pointed its entry at a new one.  Whatever order the
sync then wrote in, the bitmap held both new allocations, which must go
first, and these frees, which must go last.  So frees are queued now
(`ch_free`, up to four chains a unit), and the bitmap holds only
allocations until the sync has written the directories:

1. the bitmap -- allocations only (`rank`);
2. data, maps and directories;
3. the queued chains freed, and the bitmap again;
4. the superblock's free count, which if it is behind the bitmap is wrong
   by the sectors leaked and nothing more.

A call that queues a chain and then fails before changing what points at
it takes the chain back off the queue (`ch_keep`).  A full queue syncs
first.

One case is left, and no order can close it.  A move between folders
changes two directory sectors.  Refused between the two, the file is in
both folders, its new entry written and its old one not yet removed.
Removing the old entry first would leave it in neither, so this order is
the better failure.

## Gates

**`test-sdfs`** gains a pass for each sector size, 128, 256 and 512.
Eight operations each start from one prepared disk:
- making a folder;
- making a file;
- emptying a file and writing it again;
- deleting a file;
- removing a folder;
- renaming a folder;
- moving a folder;
- moving a file.

Each operation is run with the drive refusing at every write it makes, in
turn: from that write on (a drive that stops), and that write alone (one
that comes back).  That is 1,124 refusals.  After each, the image must
pass `tools/atr.py`'s check except for leaks.  Only a move between
folders may leave two entries sharing a chain.  The harness's
`SDFS_REFUSE` and `SDFS_REFUSE_ONE` (`tests/host/sdfs_host.c`) do the
refusing.

| broken on purpose | result |
|---|---|
| chains freed at once again | deletes, emptyings and folder removals leave used sectors marked free |
| the bitmap written last again | a new folder's sectors marked free -- the MiSTer's disk, exactly |
| (before the fix) a new map page written with the rest | on 128-byte sectors, a second map page whose back link never reached the disk |
