#!/bin/sh
# ccdep.sh -- the C compiler, plus a record of what the object really
# depends on.
#
# WHY THIS EXISTS.  Every object rule in the Makefile lists its headers by
# hand, and a hand-written list is a list that can be wrong.  When the VDI's
# device seam (src/vdi/vdidev.h) turned SCR_W from a constant into a field
# of a far struct, build/pointer.o's rule did not name that header, so make
# kept the old object -- one that still read `vdev` as a NEAR pointer.  It
# took the low half of a bank-$02 address for a bank-$00 one, read the
# application pool, got zero, and clamped every pointer position to -1.  Ten
# conformance cases failed and the generated code for the function looked
# perfectly correct, because it was: the object beside it was not.
#
# --dependencies makes the compiler say what it actually opened, in make's
# own format.  It does not also compile, so this is two passes -- but the
# dependency pass is a preprocess and costs 17 ms against the compile's 1.2
# seconds on the largest file in the tree, which is 1.5% for a prerequisite
# list nobody has to maintain.
#
# The Makefile includes build/*.d, so after the first build the prerequisites
# are the compiler's and not anyone's memory.  The hand-written lists on the
# rules STAY: they are what makes the first build after a clean correct,
# before any .d exists.
#
# The .d is written only after the compile succeeds, so a failed build never
# leaves a dependency file that outlives the object it describes.
set -e
CC="${CC65816:?ccdep.sh: CC65816 is not set}"

out=""; prev=""
for a in "$@"; do
    [ "$prev" = "-o" ] && out="$a"
    prev="$a"
done

case "$out" in
    *.o) ;;
    *) exec "$CC" "$@" ;;           # not an object: nothing to record
esac

# CC_ASM=1: the compiler's assembly for this object as well, beside it as
# .s, from exactly these flags and defines -- which is what tools/ccbug/
# mscan.py --build reads.  A separate pass, because --assembly-source
# makes the compiler write ONLY assembly, and its assembly does not
# re-assemble (as65816 rejects its `pea ##1`), so the object cannot be
# made from it.  Off by default: it adds about half a minute to a full
# build (make mscan turns it on).
if [ -n "$CC_ASM" ]; then
    "$CC" --assembly-source "${out%.o}.s" "$@" >/dev/null 2>&1 || true
fi

dep="${out%.o}.d"
tmp="$dep.tmp"
rm -f "$dep"
set +e
"$CC" --dependencies "$@" > "$tmp" 2>/dev/null
set -e
"$CC" "$@"                          # the compile itself, diagnostics and all
[ -s "$tmp" ] && mv "$tmp" "$dep"
rm -f "$tmp"
exit 0
