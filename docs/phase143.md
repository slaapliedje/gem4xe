# Phase 143 -- forms, formats and curves (VDI step 1)

The second half of step 1 of [vdi-plan.md](vdi-plan.md), after the copy
modes of [phase 142](phase142.md).  Step 1 is done: what the VDI drew
wrong, quietly, it draws as TOS does.

| | was | now |
|---|---|---|
| `vrt_cpyfm` into a form | drawn on the screen, whatever the destination MFDB named | drawn into the form, bounded by it, and not by the clip rectangle |
| `vrt_cpyfm`, erase mode, on the page | a clear source bit printed in colors[0] | colors[1], as on the screens and in TOS |
| `vr_trnfm` | an empty function | standard format to the device's and back, in place too |
| `v_bez_on` | answered whatever `intout[0]` held | 0, "no curves", so a program draws its own |

## vrt_cpyfm into a form

The device table has a new entry, `raster_form`: a one-plane source
expanded into a form that is not the screen.  On the VBXE it goes a row
at a time through the buffer `copy_rows` uses; on ANTIC and the page a
pixel at a time.  The rules are the screen's: in replace a set bit takes
colors[0] and a clear one colors[1]; in transparent a set bit takes
colors[0]; in XOR a set bit inverts; in erase a clear bit takes
colors[1].

The VDI clips the destination to the form, as it already clipped
`vro_cpyfm`'s forms.  It does not apply the clip rectangle, which is the
screen's: EmuTOS applies it only when the destination is the screen.  A
destination form with another number of planes than the device's is
refused.  Written as if it had the device's four, a one-plane form would
be written past its end.

## The page's erase mode

The page's `dev_raster_1bpp` painted a clear source bit in erase mode
in colors[0].  The two screens use colors[1], which is what the
Compendium and EmuTOS say.  The page's own glyph routine does not go
through that function, so text was never affected; only `vrt_cpyfm` on
a printer workstation was.

## vr_trnfm

The VDI's standard format is the planes one after another: plane 0
holds bit 0 of every pixel, each plane `fd_h` rows of `fd_wdwidth`
words.  The device's format is what `vro_cpyfm` moves:

- on the VBXE, 4-bit chunky, two pixels to the byte, the left one high;
- on ANTIC and the page, one plane, where the two formats are the same
  bytes.

`vr_trnfm` converts sixteen pixels at a time, a word of each plane
against eight chunky bytes.  It sets the destination's `fd_stand` to
the other format, as TOS does.  A one-plane form is copied.  A form of
any other depth is left alone.

Source and destination may be the same form.  In place, a one-plane form
needs nothing; a four-plane one is converted through a buffer from
`far_alloc_top`, in the first megabyte.  With no room for the buffer,
nothing is converted, which is EmuTOS's rule too.

## Bezier curves

`v_bez_on` is a GDOS call: opcode 11, sub-function 13, with one point
(`v_bez_off` has none).  gem4xe has no curves, so `v_bez_on` answers 0
now and a program knows to draw its own.  Before, it answered whatever
`intout[0]` held.

The plan said `v_bez` itself, opcode 6 with sub-function 13, should
stop drawing its points as a polyline.  It still draws them, because
that is what TOS does without a GDOS: its `v_pline` ignores the
sub-function.  Compatibility with TOS wins over the plan here.

## Gate

- **`test-m3`** gains seven cases (353 over the three widths):
  - `vrt_cpyfm` into a memory form in all four modes, at odd x, the last
    past the form's top and right edges, with a clip rectangle set that
    must not apply, and the form then shown on the screen;
  - a refusal into a one-plane form;
  - `vr_trnfm` from standard to the device's and onto the screen;
  - the device's to standard in place;
  - in place there and back;
  - at one plane;
  - `v_bez_on` and `v_bez_off`.

  The standard-format form is written by the harness from its pixels,
  a third time after the driver and the model.  The harness compares
  every memory form a case touches, byte for byte, and the `fd_stand`
  left in each MFDB.  Each destination is staged with `fd_stand` the
  wrong way round, so that setting it shows.
- **`test-m25`** draws a mark with `vrt_cpyfm` into the bank-$00 form of
  its memory round trip -- in XOR over the text there, in replace, and
  in erase past the form's edge -- and puts the form on the screen.  The
  gate's model of the form is written from the four modes' definitions.
- **`test-m30`** puts the mark over the inked block in erase mode with
  colors {1, 0}: its clear bits print as paper.

The page's `raster_form` is not checked.  The printer model's bank-$00
addresses are its page, so it cannot hold a memory form.  The function
is the same code as ANTIC's, which `test-m25` checks.

`vdi_scratch` in the m3 runner is 2 KB and the runner's buffers fill
$6800-$7F80, so vr_trnfm's forms are 16 x 4: the 172 bytes left held
two of them and four MFDBs.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| `vrt_cpyfm`'s form path off | m3's form case: the form's bytes differ; m25: 352 pixels |
| depth check removed | the refusal case: the one-plane form written, `$11` for `$00` |
| `fd_stand` never written | three `vr_trnfm` cases: `fd_stand` wrong; there and back: the bytes |
| `v_bez_on`'s answer removed | its record differs |
| in place without the buffer | both in-place cases: the bytes |
| standard to the device's, pixel order swapped | that case: `$41` for `$14` |
| the page's erase colour back to colors[0] | m30: the decoded page and the PCL |
