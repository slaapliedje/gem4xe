#!/bin/bash
# survey.sh -- how far the gem4xe C is from a 6502 build (docs/6502.md).
#
#   tools/bsp6502/survey.sh [OUTDIR]
#
# Compiles every C file of the system with cc6502 -O2 --core 6502, using
# portab.h's 6502 block, and prints a line per file: its errors, its FAR
# uses -- each one a place that needs a banked accessor, because a 6502 has
# no 24-bit address -- and its length.  The device drivers get their
# Makefile -D flags.  Generated headers (deskrsc.h, lang_rsc.h, ...) are
# read from GEN, default build/, so run `make` once first.
#
# A clean compile here is NOT a working build: FAR is defined away.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$ROOT/build/bsp6502}
GEN=${GEN:-$ROOT/build}
CC=${CALYPSI6502:-$HOME/dev/toolchains/calypsi-6502}/bin/cc6502
cd "$ROOT"
mkdir -p "$OUT/log"
: > "$OUT/survey.txt"
for f in src/aes/*.c src/vdi/*.c src/desk/*.c src/sys/*.c src/antic/*.c \
         src/vbxe/*.c src/gem.c src/app/*.c src/apps/*.c; do
  extra=()
  case $f in
    src/vdi/dev_antic.c) extra=(-DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=and_ -DGEM4XE_DEV_ANTIC);;
    src/vdi/dev_vbxe.c)  extra=(-DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=vbd_);;
    src/vdi/dev_print.c) extra=(-DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=prd_ -DGEM4XE_DEV_PRINT);;
  esac
  n=${f//\//_}
  "$CC" -O2 --core 6502 -I src -I src/app -I src/vdi -I "$GEN" "${extra[@]}" \
      -c "$f" -o "$OUT/${n%.c}.o" > "$OUT/log/$n.txt" 2>&1 || true
  printf '%-26s errors %-3s FAR %-4s lines %s\n' "$f" \
      "$(grep -c ' error:' "$OUT/log/$n.txt" || true)" \
      "$(grep -c -w FAR "$f" || true)" "$(wc -l < "$f")" >> "$OUT/survey.txt"
done
awk '{e+=$3; if ($3 == 0) ok++; far+=$5; n++}
     END {printf "%d files, %d compile clean, %d errors, %d FAR uses\n", n, ok, e, far}' \
    "$OUT/survey.txt"
