# cc6502 bugs, run in Calypsi's own simulator

    python3 tools/ccbug/b6/check6.py --calypsi DIR [--calypsi DIR2]   # a Calypsi 6502 install

bugs6.c, other.c and fwd.c are built with `--core 6502` at -O0 and -O2,
linked `--semi-hosted` with linker.scm (Calypsi's example/minimal map with
the switch section printf needs), and run in db6502.  Each bug prints its
expected and actual value beside the shape gem4xe uses instead.  c8, c9
and c10 each crash the compiler and are only compiled.

| | shape | 5.18 | 5.18.4 |
|---|---|---|---|
| C1 | `(uint8_t)(k + 1)` widened: high byte $FF | wrong | wrong |
| C2 | `(uint8_t)(a >> 16) == 0` tests bits 16-31 | wrong | wrong |
| C3 | `_Mul16to32`: low two bytes swapped (9 * 40 = $6801) | wrong | wrong |
| C4 | own params forwarded beside `&locals` (objc.c's ob_change) | not reproduced here | |
| C5 | a uint32 forwarded as its hi, lo words: low twice | wrong | wrong |
| C6 | `(({ put(p) }), p += 1)`: put gets p + 1 | wrong | wrong |
| C7 | `a[3] = a[1] + 13` becomes `a[3] += 13` | wrong | fixed |
| C8 | `(unsigned)&s.b`: internal error | crash | crash |
| C9 | inlined `return take(&local)`: internal error, -O1/-O2 (cc65816 too) | crash | crash |
| C10 | `if ((x, -1) < 0)`, `--core 6502`: BIT #255 | crash | crash |

The exit status counts the workaround shapes that came out wrong.
