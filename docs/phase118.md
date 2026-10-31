# Phase 118 -- a control panel module loaded when it is opened

The first thing [phase 117](phase117.md) made possible, from step 2 of
[memory-plan.md](memory-plan.md).  Every `.CPX` used to be loaded at boot
and kept for the life of the machine, because the pool was a bump
allocator and a module loaded while the desktop was up would have been
freed under the panel the next time a program ran.  Now a module is
loaded when the panel opens it and freed when the panel closes it, as
XCONTROL does on the ST, and a closed module costs bank $00 nothing.

## Boot

A gem4xe module carries its 512-byte header inside itself, not in front
of it as an ST `.CPX` does, so the panel cannot list a module without
running it.  Boot therefore still runs every module once (`sh_cpx`): its
crt installs its data, its `cpx_init` writes its header into the AES's
table, and the panel boot-initialises the ones that ask
(`CPX_BOOTINIT`).  Then, before the floor is marked, `sh_cpxdropall`
frees every module whose header does not say `CPX_RESIDENT`: its near
region, its far image and the resource it loaded, by its owner, in both
allocators.  The slot keeps the header, the file name and the settings,
and its vtable goes to 0.

## Opening one

The panel (`cp_opencpx`) sees the 0 and calls `Cpxload(i, 1)`, GEMDOS
`0x1F3`, gem4xe's own.  The shell (`sh_cpxload`) runs the module again,
from the system's directory whatever the default one is, through
`gd_run`: `Pexec`'s own machinery, split out of `gd_pexec` for this,
because the module runs inside the panel's process and makes calls of
its own.  It is kept because it ends with `Ptermres`, its saved settings
are laid over its header again, and its vtable is live.  When the panel
is done with it, `Cpxload(i, 0)` frees it, unless it is `CPX_RESIDENT`.  A
module that will not load gets the canned memory alert.

`gd_run(child, name, tail, keep, &kept)` is all of `Pexec` after the
load: the shell's words and a DTA, the parent's handles, the resource
slots, `gem_api_sp`, and at the end everything put back and the child
freed by its owner -- unless `keep` and it asked to stay.  `Pexec` is now
the load and a call to it.

## Where the memory goes

The modules load before the accessories, so freeing them leaves a hole
below the accessories, and the desktop is placed in it: `pool_take` puts
a program's near region in the lowest gap it fits.

| the product, everything resident | before | after |
|---|---|---|
| the desktop's near region | $6500 | $4B00, in the modules' hole |
| free above the top: GEMDOS's read slices | 5,632 | 6,912 |
| what a program launched from the desktop gets | 6,912 | 6,912 |

A launched program gets no more, because the hole is below the
accessories and 2,048 bytes, and the room above them is unchanged.
Giving that hole to programs too would mean freeing the modules before
the accessories load and having the panel load each one again for its
boot-init, which is every module read twice at every boot.

`tools/memreport.py` now places the pool's blocks with
`tools/poolref.py`, the rules `pool.c` is held to, rather than with a
bump cursor of its own, so it shows the desktop in the hole as the
machine puts it there.

## Gates

- `test-m35`: TEST.CPX loads, fills its header and is freed: its slot's
  vtable reads 0, its title is still there, `sh_cpxdrops` is 1, and the
  desktop lands exactly where it does on the same system with no module
  at all.  Under the old rule it sat 1,536 bytes higher.
- `test-m44`: on the product's disk, all three modules are freed after
  boot, and the tour then opens General and Color from the panel, which
  loads each again.  `test-m36` and `test-m42` open them too and change
  their settings.
- `make memcheck` and the whole of `make test`.
