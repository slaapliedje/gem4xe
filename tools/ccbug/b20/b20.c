/* B20 -- a signed 64-bit division calls _Div64, which is EIGHT BYTES
 * that fall through, and the routine it falls through to is not linked.
 *
 *   cc65816 --code-model=large --data-model=large -O2 --target atari \
 *           -o b20.o b20.c
 *   ln65816 linker.scm b20.o clib-lc-ld-atari.a --rtattr exit=simplified \
 *           -o b20.elf --list-file b20.map
 *
 * The link SUCCEEDS.  The map then says:
 *
 *   _Div64 in section 'farcode'  placed at address 030159-030160 of size 000008
 *   Section 'ifar'  placed at address 030161-030168 of size 000008
 *
 * and `_UDiv64` does not appear in the map at all.  The eight bytes are
 *
 *   a0 06 00   ldy ##6
 *   b7 04      lda [dp:04],y
 *   57 08      eor [dp:08],y      ; the sign of the quotient
 *   18         clc
 *
 * with no rts, rtl, bra or jsl: _Div64 computes the sign and FALLS
 * THROUGH into the next section.  What the linker put there is the
 * `ifar` initialiser for `b` below -- so the divide executes
 * `07 00 00 00 00 00 00 00`, the constant 7, as instructions.
 *
 * Under db65816 the program never terminates.  On an Atari it took a
 * native-mode BRK.
 *
 * FOUND BY: qed on gem4xe, saving a file.  QED asks for the time, the C
 * library's localtime() divides a 64-bit time_t, and the machine died
 * three calls below anything either program wrote.
 *
 * BOTH DATA MODELS.  Nothing here is far-pointer specific: --data-model=small
 * gives _Div64 the same eight bytes and links no _UDiv64 either.
 *
 * `make check-cc` links this file with the linker.scm beside it and asks
 * the map whether _UDiv64 is there.  It is the whole test: no listing
 * shows this, because the defect is what the linker did NOT place.
 */
#include <stdint.h>

const char *msg = "scrap.*";        /* a cfar section, to compete for the slot */
volatile int64_t a = 1000000, b = 7;
volatile int64_t r;

int main(void)
{
    r = a / b;                      /* -> _Div64; want 142857 */
    return (int)r;
}
