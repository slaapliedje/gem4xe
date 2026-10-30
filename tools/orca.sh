#!/bin/sh
# orca.sh -- build an Apple IIGS program with ORCA/C, for the Spectre GS gates.
#
#   tools/orca.sh SRC.c OUT
#
# Compiles and links SRC.c with Golden Gate's ORCA/C (ref/iix: the Windows
# build under Wine, see ref/iix's own notes) into a GS/OS load file at OUT.
# The result carries Byte Works' ORCA/C runtime, so it is built here and
# never committed or shipped.  No Golden Gate is exit 2, which a gate takes
# as a SKIP, like any absent cross-toolchain.
set -e
IIX=${IIX:-$(dirname "$0")/../ref/iix}
if [ ! -x "$IIX" ]; then
    echo "orca: no Golden Gate iix at $IIX (set IIX=)"
    exit 2
fi
IIX=$(cd "$(dirname "$IIX")" && pwd)/$(basename "$IIX")
NAME=$(basename "$1" .c)
WORK=$(dirname "$IIX")/wine-gg/drive_c/work/g4x-$NAME
WIN='C:\work\g4x-'$NAME
rm -rf "$WORK"
mkdir -p "$WORK"
cp "$1" "$WORK/$NAME.c"
[ -x "$(dirname "$IIX")/iix-clean" ] && "$(dirname "$IIX")/iix-clean"
(cd "$WORK" && "$IIX" compile "$NAME.c" keep="$WIN\\$NAME") > "$WORK/compile.log" 2>&1 || true
if ! grep -q '^0 errors found' "$WORK/compile.log"; then
    echo "orca: $1 did not compile:"
    cat "$WORK/compile.log"
    exit 1
fi
(cd "$WORK" && "$IIX" link "$WIN\\$NAME" keep="$WIN\\OUT") > "$WORK/link.log" 2>&1 || true
if [ ! -s "$WORK/OUT" ]; then
    echo "orca: $1 did not link:"
    cat "$WORK/link.log"
    exit 1
fi
cp "$WORK/OUT" "$2"
echo "$2: $(wc -c < "$2") bytes, from $1 (ORCA/C)"
