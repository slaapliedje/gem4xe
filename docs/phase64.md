# Phase 64 -- Set file mask; and the drive info's DTA

The third of item 4's small desktop items (`docs/roadmap-0.9.md`).

**File -> Set file mask** gives the top window a mask, typed the way a
name is -- eight places and three, `*.BAT`, `?EAD*.*` -- and an empty one
means everything.  Only FILES are held to it: the listing reads the whole
directory and a folder is always listed, as the TOS desktop lists it, or
a mask of `*.TXT` would hide every way down the tree.  The mask goes down
into a folder with the window and comes back up with it, and it is part
of the window's path, so Save desktop keeps it.

A window's path used to END in `*.*`, and four places took three
characters off it to get the directory; they ask `spec_dirlen` now, up to
and including the last backslash.  The desktop does its own matching,
the DOS's rule -- `*` and `?`, and a name without an extension read as
`NAME.` so that `*.*` is everything -- since the system's matcher is not
an application's to call.

## And a fault the gate found in phase 63

The first run listed drive A as five nameless items and "0 bytes" before
any mask was set.  Show info on a drive, one step earlier, counts with
the delete's walk, and the walk sets a DTA of its own; nothing put the
listings' DTA back, so every window listed after it had `Fsfirst` fill
one DTA while the listing read another.  The delete's own code says so
("the listing's DTA is put back first"), and `fun_dinfo` now does it.
It shipped in no release.

`make test-m41` now also masks A:'s window with `*.BAT` (its two BATs and
its folders), then `*.RSC` (the root's folders alone, and down in `GEM`
exactly its seven resources and not `GEM.COM`), back up, and empty
(everything).
