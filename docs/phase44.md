# Phase 44 -- the kit an ST program can be ported against, and a mouse where people plug it in

Two unrelated things, and both came from somebody outside this tree
trying to use it.

A port of **cflib** -- the widget library most FreeMiNT-era GEM programs
lean on -- was compiled against the application kit, and it stopped on
things that were nobody's bug: names the ST publishes and this kit did
not declare, a call whose arguments were in a different order, and three
headers Calypsi's C library simply does not have.  94 of its 141 files
built.  When the last of it was closed the number was 137, and the
remaining four are the ones this port deliberately drops.

And drac030 pointed out that a mouse belongs in **port 2**.  It is the
standard, port 1 is reported to interfere with the keyboard, and gem4xe
read port 1 -- so a user who wired it the way the Atari world wires it
got nothing at all.

## The kit: what a ported program expects to find

**The published names are declared.**  `ED_*`, `K_*`, `MD_*`, AES 4's
`WM_ONTOP`, `WM_UNTOPPED` and `WF_BOTTOM`, the line types and ends, and
the structs an ST resource or binding names -- `CICON`, `CICONBLK`,
`MENU`, `PARMBLK`, `USERBLK`, and `BITBLK`, which a `G_IMAGE` points at
and which had never been declared here at all.  Each carries a line in
`gem.h` saying what THIS AES does with it, which is not always what the
ST's does: `G_CICON` draws its mono form, `G_USERDEF` draws nothing yet,
`menu_popup` is not served *(it is, since Phase 46 -- `docs/phase46.md`)*.  A name that compiles and then quietly does
something else is worse than one that is missing.

One of them is numbered from the VDI's own table rather than the
Compendium: the line types start at 1 for solid, and the table on p595 is
off by one.

**`evnt_multi` has the ST's shape** -- twenty-three arguments, the two
mouse rectangles flat -- because that is the call every ported main loop
makes.  The compact form this tree was written against keeps its
behaviour under `evnt_multi_moblk`, and the four callers in the tree say
so.  It is a C-surface break rather than a reinterpretation: a
fifteen-argument call stops compiling instead of passing a `MOBLK`
pointer where a flags word goes.

It is still not identical to what a FreeMiNT-era program writes, and the
difference is exactly one argument: the AES takes the timer as two words,
low then high, where gemlib's binding takes one long.  So a ported event
loop is one argument away rather than a different shape, and the kit's
README says so at the call.

**`ob_spec` is the union gemlib declares**, including its bit-field.
cflib reaches through it in twelve files, eight of which failed on
nothing else.  Two things about that had to be measured rather than
reasoned about, and both are the sort that fail silently:

- The union is the same four bytes in **both data models**.  Under
  `--data-model=small` a pointer is two bytes and lands on the low word,
  which is where a bank-$00 address is kept; under `--data-model=large`
  it is four, little-endian with the bank in byte 2, so the whole word
  reads as a far pointer whose bank is the high half's zero -- bank $00,
  which is where these structures live.
- The bit-field is declared **backwards**, and its fields are `long`.
  The 68000's compilers allocate a bit-field from the high end and this
  one from the low, so gemlib's order comes out mirrored -- a box's
  character read out of its interior colour.  And gemlib's `unsigned` is
  32 bits where it comes from and 16 here, so declared that way the
  struct is eight bytes and every `OBJECT` field after `ob_spec` moves.

`tests/host/test_sdk.py` compiles both claims, in both models, by reading
the size out of a function's generated code -- never an array bound,
which this compiler answers differently (`tools/ccbug`, B7).

**`printf` links.**  Calypsi's C library asks the board for nine
routines, and without them a program that prints fails at the link with
a message naming the board support rather than the program.
`lib/gemstub.c` is all nine, over GEMDOS, and the mapping is the whole of
its correctness: **a file descriptor is a GEMDOS handle, straight
through**.  The two numberings agree where it matters -- GEMDOS keeps 0
and 1 on the console and hands out files above 3, and the library asks
only that an opened file come back greater than 2 -- so `printf` reaches
the VT-52 console on GEM's screen, `Fforce` still redirects it into a
file, and nothing here remembers anything.

None of that shows at link time: a wrong handle links, and a count and a
buffer the wrong way round link.  So it is gated by RUNNING it, with the
GEMDOS gate replaced by a recorder in the compiler's simulator
(`tests/host/stub_sim.c`).  That is also where the cost came out: stdout
is unbuffered, so a ten-byte line is ten trips through the call gate.
Hand stdio a buffer with `setvbuf` -- your own array, there being no
heap.

**`stat()` and the cookie jar.**  `sys/stat.h` is the kit's, mintlib's in
shape and field names, over one `Fsfirst` with the caller's DTA put back:
kind, size, and the one stamp GEMDOS keeps for all three times.  The date
arithmetic is 32-bit on purpose -- a 64-bit divide miscompiles here --
and was swept against the calendar for every DOS stamp it can express,
1980 to 2107.  `mint/cookie.h` answers `C_NOTFOUND` for every cookie,
there being no jar and no system variable to hang one on, which is the
answer a well-written program defaults on.

## The mouse

**Port 2 by default**, and `MOUSEPORT=1` in `GEM4XE.CFG` for a machine
wired the other way.  The 4 kHz sampler in `src/sys/irq.s` reads one byte
to decide which nibble of `PORTA` to decode, and the polling fallback and
the seeding read follow it.

**And the right button was read from the wrong pin**, which was wrong on
either port.  It was the OTHER port's trigger -- a joystick plugged in
beside the mouse, not the mouse.  A quadrature device occupies one port
completely: four direction lines for the two axes, the trigger for the
left button, and the port's **first paddle line** for the right, POT0 on
port 1 and POT2 on port 2, pulled to 0 held and near 229 free.  That is
how the ST-mouse adapter is built and how Altirra models it, in
`ATMouseController::SetDigitalTrigger`: button 0 sets the port's trigger
bit and button 1 calls `SetPotPosition`.

The paddle has a trap in it.  Its counter climbs THROUGH a scan, so
reading it mid-scan reads low -- indistinguishable from a held button.
Read every poll, it pins the right button down and the desktop becomes
unusable.  It is sampled only from a finished scan and keeps its answer
until the next, and bit 1 of the button word is the cache: bank $00 pays
for no variable to hold it, which is also why the port is one byte the
assembler reads directly rather than a word and a copy.  The budget check
caught both of those, twice, at one byte over.

The device walk in `tests/host/quad_sim.c` now runs every device on
**both** ports and requires the same answer.  The old walk drove the low
nibble, so it agreed with whatever the system happened to read -- which
is why five phases of green gates never noticed the mouse was on the
wrong port.

## Two faults in the build, found by the same outsider's eye

A rule that had lost its recipe: `build/shel.o` shared a body with the
target added above it, so it had prerequisites and nothing to run, no
pattern rule matched, and `make` said "Nothing to be done" and left the
link to fail on a file it was never going to build.  Invisible in any
tree that already had the object, which is every tree here since the day
it broke -- it is a fresh clone that cannot build.

And a bare `make` built exactly one object and exited 0, because the
`-include` of the dependency files sits above `all` and an included
file's first target becomes the default goal.  The comment above `all`
says a plain `make` should leave no disk behind its sources, precisely so
a gate run by hand cannot boot a stale image; that protection had been
off for as long as the `.d` files had existed.

## A second machine, and a gate that read a buffer nobody had filled

drac030 pointed out that the Rapidus is one way to get a 65C816 with
linear RAM and not the only one, so testing only against it proves less
than it looks.  Altirra's core has always carried a CPU model and a
high-bank count of its own, independent of any accelerator device; only
the SDL front end could not reach them.  This tree's fork now can
(`--cpu`, `--highbanks`), so `make test-m5p` runs the same probe on a
bare 65C816 with fifteen high banks -- the shape of an Antonia.  It
reports `FARMEM_UNKNOWN`, which is the right answer rather than a
shortcoming: linear RAM found, board not identified.

**The gate failed for two hours while a byte-for-byte scratch probe of
the same machine passed.**  It was not the machine.  `m5` polled `$0600`
until the runner published `VD` and a ready flag, and then read the
results whether or not that flag had ever come up.  On the slower machine
the runner was still walking banks, so the gate read a zeroed buffer and
announced *"no linear RAM found -- gem4xe cannot run on this machine"*
about a machine with twelve banks of it.  All seven failures it printed
were facts about an empty buffer.

The poll now decides.  Not ready is a failure, named as one, and nothing
below it is called an answer.  Proved by running the gate with the wait
cut to a single iteration: it says *"runner never published a result"*,
which is what it should have said all along.  That is
`probe-poll-for-completion` for the third time in this project, and the
shape is always the same -- the check exists, its verdict is discarded.

## The worse bug the fix exposed

The emulator **saves its machine settings on exit**, and every gate shared
`~/.config/altirra`.  So an AltirraSDL build with no `--cpu` switch at all
**passed** the new plain-65C816 gate, because an earlier run had persisted
`"CPU: Chip type = 2"` and it was simply still sitting there.  A gate that
can pass on a build lacking the very feature it tests is measuring the
config file.

Each run now gets a config directory of its own, seeded from the user's
`settings.ini` with the chip type and high-bank count zeroed: every caller
states the machine it wants, so a remembered one can only ever disagree
silently.  With that in place the pre-patch build fails, as it must.  And
`launch()` asks the CPU what it is whenever a plain 65C816 was requested,
because an emulator that does not know `--cpu` logs the switch and carries
on as a 6502 -- and the gate would have reported that as a finding about
gem4xe rather than about the emulator.
