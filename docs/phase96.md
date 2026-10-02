# Phase 96 -- LANG.RSC in four more languages

Asked for beside the 0.12 work: `LANG.RSC` "for the common ones that
the Atari 8bit was popular in" -- Germany, the UK and Poland, and
Spanish and French.  The UK is the English already built in.  The other
four are new.

## What is translated

`LANG.RSC` is what the *system* says (`docs/shipping.md` section 5):

- `form_error`'s alerts;
- the shell's "cannot be found / loaded / was built for an older
  gem4xe";
- the boot screen's labels and values;
- the lines printed on the way back to DOS.

That is 43 strings.  The desktop's menus and dialogs are `DESKTOP.RSC`'s,
an application's own, and are not part of this.

The five long `form_error` alerts, "Version" and "Printer" are
**EmuTOS's own translations** (its `po/de.po`, `fr.po`, `es.po`,
`pl.po`): the same GPL donor gem4xe's English texts come from.  The
rest are new.

## The rules, and `check()`

`tools/langrsc.py` holds the four tables beside the English, and
`check(lang)` holds each to every rule a translation must keep.  The
build refuses a table that breaks one, and `tests/host/test_lang.py`
runs it, on the English too.  The rules:

- **form_alert's grammar**, with the English icon and number of buttons;
  five lines of forty; buttons of twenty.
- **The `#` and two characters** in the error-number alert.
- **`LANG_MAXLEN`**, the English's longest, 130 bytes.  `lang_str`
  copies into a near buffer of that size, and bank $00 has no byte to
  widen it with (phase 95 spent the last six).  Three of EmuTOS's
  "no room for another document" alerts were longer and are shortened.
- **The boot screen and the exit lines are plain ASCII.**  They go to E:,
  the OS's text screen, which draws ATASCII: a byte from `$80` up is an
  inverse glyph there, and the system font is not used.  So they are
  written the way 8-bit software always wrote them: German ae, oe, ue,
  ss, and French, Spanish and Polish without their accents.  They fit
  `bootinfo.c`'s columns: a label 9, a value 26, the "hold SHIFT" row 36.

The test also feeds `check()` a broken table, to show it speaks: a
missing `#`, a changed icon, a ten-column label, a 41-column line, a
character not in the set, a missing string, and an accent on E:.

## The characters

Everything GEM draws (the alerts) uses the system font:

- **German, French and Spanish** are written in the Atari ST character
  set the linked font has.  `ATARIST` is EmuTOS's own Latin-1 table
  (`tools/bug.c`).  A character not in it is refused, not replaced.
- **Polish** is ISO-8859-2, for the Latin-2 font `make fonts` writes out
  of EmuTOS (`build/l2.fnt`), which ships beside it as `SYSTEM.FNT`
  (phase 21's loader reads it).

## Where they go

`make langs` writes `build/lang/XX/LANG.RSC`.  The release carries them
under `system/LANG/DE/`, `FR/`, `ES/` and `PL/` (Polish with its
`SYSTEM.FNT`), and the page's file table says what each is for: copy it
over the one beside `GEM.COM`.  `make dist` and `make release` now need
`build/l2.fnt`, so an EmuTOS checkout (`EMUTOS=`).

## Proof

- `make test-m20` boots three more disks, with the German, French and
  Spanish files that ship.  It draws `form_error`'s fixed alert and the
  numbered one on each, and compares them with `tools/aesref.py`, pixel
  for pixel.  "déjà", "schreibgeschützt" and "aplicación" are on the
  screen.
- Polish cannot be modelled: the model draws the linked set.  A scratch
  run of the same gate with `SYSTEM.FNT` on the disk shows "Przedmiot z
  tą nazwą już istnieje" and "Błąd TOS #63."; the 68 and 43 pixels it
  differs from the model by are the Latin-2 glyphs.
