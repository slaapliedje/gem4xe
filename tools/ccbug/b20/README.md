# B20 standalone reproducer — signed 64-bit division falls into data

Calypsi's own `example/minimal/linker.scm`, with the two memories a
large-model program needs above `$FFFF` (bits and BSS cannot share one):

    (memory FarCode (address (#x30000 . #x3ffff))
            (section farcode ifar cfar))
    (memory FarRAM  (address (#x40000 . #x4ffff))
            (section far zfar))

Build:

    cc65816 --code-model=large --data-model=large -O2 --target atari \
            -o b20.o b20.c
    ln65816 linker.scm b20.o clib-lc-ld-atari.a --rtattr exit=simplified \
            -o b20.elf --list-file b20.map

The link succeeds and says:

    _Div64 in section 'farcode'  placed at address 030159-030160 of size 000008
    Section 'ifar'  placed at address 030161-030168 of size 000008

`_UDiv64` is not in the map at all.  `_Div64`'s eight bytes are

    a0 06 00   ldy ##6
    b7 04      lda [dp:04],y
    57 08      eor [dp:08],y
    18         clc

— the sign of the quotient, and then nothing.  No `rtl`, no `bra`, no
`jsl`: the routine FALLS THROUGH, and the section it needs is neither
placed after it nor linked in.  The divide runs into the `ifar`
initialiser that landed there, which for this program is `b`'s value:
`07 00 00 00 00 00 00 00`, executed as instructions.

    db65816 b20.elf        # never terminates

Same in `--data-model=small` against `clib-lc-sd-atari.a`: `_Div64` is
the same eight bytes and `_UDiv64` is absent there too.

Found by qed on gem4xe: saving a file asks for the time, `localtime()`
divides a 64-bit `time_t`, and the Atari took a native-mode BRK with the
program counter inside a string constant.

`make check-cc` links THIS FILE with THIS SCRIPT and reads the map for
`_UDiv64`; there is no separate regression shape, because the defect is
not in any code a compiler listing would show -- it is in what the linker
did and did not place.  `../README.md` has the entry.
