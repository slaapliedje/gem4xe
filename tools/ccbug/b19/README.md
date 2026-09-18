# B19 standalone reproducer — Calypsi issue #91

Everything here is Calypsi's own `example/minimal/linker.scm` with ONE
added memory, so `--data-model=large` globals have a home above `$FFFF`:

    (memory FarRAM (address (#x30000 . #x3ffff))
            (section far zfar cfar))

Build it:

    cc65816 --code-model=large --data-model=large -O2 -o b19.o b19.c
    ln65816 linker.scm b19.o clib-lc-ld.a --rtattr exit=simplified -o b19.elf

    symbol 'arr' referenced from section 'farcode' at offset 000004 in
    b19.o: value 196610 is out of range, allowed range is -32768 to 65535

`p - arr` comes out as `sbc ##arr` — the whole address in a 16-bit field.
`##.word0 arr` was wanted, and the compiler emits exactly that for
pointer ADDITION (`arr + 3` links, rc=0):

    lda     ##.word0 (arr+3)
    lda     ##.word2 (arr+3)

This directory is the report's evidence; `../b19_ptrdiff.c` is the
regression shape `make check-cc` reads, and `../README.md` has the entry.
