# Phase 139 -- three banks: a squeezed program unpacked around its code

[Phase 138](phase138.md) found it: a 65C816 with exactly three far banks
-- 512 KB, banks $05 to $07 -- could not start the desktop.  gem4xe said
the desktop needed more memory, at phase 137 as at 138.  `test-m37` had
held the boot to three banks for 58 phases, but on a 960K machine, where
the top of the heap is a spare bank and the fault cannot show.

| | was | now |
|---|---|---|
| three banks, the cartridge | "the desktop needs more memory" | the desktop runs, settled at 89 calls as on any machine |
| the boot on 960K, settled | to $083430 (four banks) | to $07E4EC (three) |
| loading a squeezed packed program | the file, the unpacked image and a copy of the code at once | the file and the image, the code inside it |

## Why it did not fit

The one request refused, found by recording the allocator's last
refusal in a probe build, was the desktop's code: 49,048 bytes,
page-aligned, which must end below $D500 in its bank.  The desktop file
is squeezed (format 6).  `app_load_v6` unpacked it into a block taken
from the TOP of the heap, "out of the program's way", and copied the
code out of that into a block of its own.  On three banks the top of the
heap is bank 7, the only bank whose foot was free for the code.  And the
load wanted, at its peak, the squeezed file (28 KB, the shell's cached
copy), the unpacked image (about 55 KB) and the code and variables
(53 KB) at once: about 200 KB of 192.  So no placement alone could have
fixed it.

## Unpacked around its code

A packed program's image (format 5) is its header, its near part, its
code and its fixup lists, in that order; its variables are not in the
file.  So the code needs no copy of its own: the image is unpacked into
a block placed so that the code inside it already sits where code can
run, the fixups patch it where it lies, and afterwards the image is given
back and the code's bytes claimed again, exactly.  Nothing is given out
in between, so the claim cannot miss.

- **`far_alloc_inner(bytes, off, inner, limit)`** (`src/sys/farmem.c`):
  a block that may cross banks, placed so that the `inner` bytes from
  `off` into it are page-aligned and end at or below `limit` in their own
  bank -- what `far_alloc_page` would have given those bytes alone.  The
  block's head may lie in the bank below.  `off` must be a multiple of 4,
  as every block's start is.  `tools/farref.py` has the same rule.
- **The header first.**  `g4z_unpack` writes exactly the count it is
  given and stops, so `app_v6_inner` unpacks the 48-byte header into a
  scratch block to learn where the code is and how long, before the
  image's block is placed.
- **`app_load_v5`** takes the code's place as a parameter: given one, it
  allocates no code block and copies nothing.  (A static would have been
  simpler, but ZWIN, where `app.c` keeps its state, has no four bytes
  left -- and the run `far_alloc_inner` asks for travels down to `fit`
  as a parameter too, its offset and length in one word: as two statics
  in `farmem.c` they took 8 bytes of LoRAM and `test_memory` caught it.)
- **Anything else** -- an image that is not format 5, an offset that is
  not a multiple of 4, no such place -- goes the old way, at the top of
  the heap.

The peak for the desktop is now the file and the image, about 150 KB,
and every squeezed packed program loads with one copy of its code fewer:
QED's and the accessories' too.

## Gates

- **`tests/host/test_farmem.py`**: ten new steps through `far_alloc_inner` in the
  compiler's simulator and the model, which must agree on every answer:
  the desktop's shape (a run at a bank's foot, its block starting in the
  bank below), a small run in a hole, an odd offset, a run past the
  block's end, a run exactly as long as the limit and one a byte longer.
  Fails with the step to the next bank's foot taken out.
- **`test-m37`** holds the settled 960K boot to three banks again, and
  boots the cartridge with the heap cut to three (`m37three`): the
  desktop must run and settle, its calls still for two reads running,
  with every block inside the three banks.  Until this phase that was a
  known failure that passed while the desktop was refused.
- **`test-m17`**'s model of where the desktop lands
  (`tests/emu/m17_desktop.py`, `desk_places`) places the image as the
  loader does now and claims the code back.

- **`test-m57`**'s program (`src/m53_app.c`) gave its 12 KB back from
  the LAST block it had taken, which is the smallest gap above 1 KB --
  over 12 KB only while the heap happened to fall that way.  The new
  layout left a smaller gap, and step 7 quietly did nothing.  It gives
  them back from the biggest block now.

With the in-place load switched off -- every image to the top of the
heap, as before -- `test-m37` fails both checks: the 960K boot reaches
$083430 again, and with three banks the desktop is refused.  `test-m17`
passes either way: on its machine both ways put the desktop's code at the
foot of bank 7, so it cannot tell them apart, and its model is kept exact
for the machines where they differ rather than as evidence for this.
