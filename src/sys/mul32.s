;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; mul32.s -- _Mul32, the low 32 bits of a 32 x 32 multiply, by quarter squares.
;;;
;;; WHY THIS EXISTS
;;;
;;; The library's _Mul32 takes about 6,000 cycles, and G4BENCH's Mandelbrot
;;; spends 40 of its 60 seconds in it (docs/roadmap-0.12.md, item 1); every
;;; `long` product in a program goes through it.  With this one the
;;; Mandelbrot takes 57% less time (docs/phase92.md).
;;;
;;; HOW.  The 65C816 has no multiply.  x * y for two bytes is
;;; f(x + y) - f(|x - y|), f(n) = floor(n * n / 4) -- a table of 511 words
;;; -- so a byte product is two table reads and a subtract.  Of
;;; a * b mod 2^32, with a = aH:aL and b = bH:bL in 16-bit halves:
;;;
;;;     aL * bL                      in full: four byte products
;;;   + (aL * bH + aH * bL) << 16    only their low 16 bits: three each
;;;
;;; and the second line is skipped for a half that is zero, which is every
;;; product of two numbers under 65,536.  Signed and unsigned are the same
;;; bits in the low 32, so there is one routine for both.
;;;
;;; THE CALL is the library's, read off the compiler's own output
;;; (`long f(long a, long b) { return a * b; }`): a in _Dp+0..3 and b in
;;; _Dp+4..7, low word first; the product in A (low word) and X (high).
;;; The caller tests the result itself (`stx` / `ora`), so the flags this
;;; leaves do not matter -- unlike _Div16's (div16.s).  Y and _Dp+0..7 are
;;; scratch, as the library's are; _Dp+8 and up are the caller's and are
;;; not touched.
;;;
;;; THE FRAME.  The operands and the work are on the stack, and the direct
;;; page is moved onto it for the length of the call (phd ... pld), so every
;;; temporary is a direct-page operand.  An interrupt pushes below S, under
;;; the frame, and leaves it alone.
;;;
;;; THE TABLE is made, not shipped: 1,022 bytes of squares do not pack, and
;;; on the DOS 2 floppy, where GEM.COM and the desktop leave a few sectors
;;; free, they cost nine of them.  It lives in `zfar`, the far variables a
;;; program's crt zeroes, and the first call fills it (build, below) in
;;; about a millisecond.  So this is a PROGRAM's multiply -- every .G4A and the
;;; kit link it -- and not GEM.COM's: the system has no zeroed far section,
;;; and keeps the library's.
;;;
;;; tests/host/test_mul32.py runs it against the library's in the vendor's
;;; simulator, product for product, and reads the table it made.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"

              .extern _Dp
              .public _Mul32, mul32_sqr

;;; the frame, as direct-page offsets once D points at it
tx            .equ    1               ; m8's x
ty            .equ    3               ; m8's y
tp            .equ    5               ; m8's f(x + y)
r0            .equ    7               ; the product, low word
r1            .equ    9               ;   ...and high
mid           .equ    11              ; a middle sum
mhi           .equ    13              ; ...its carry, as $0100
LOCALS        .equ    14
;;;           LOCALS + 1, + 2         the caller's D (phd)
aL            .equ    LOCALS + 3
aH            .equ    LOCALS + 5
bL            .equ    LOCALS + 7
bH            .equ    LOCALS + 9

              .section farcode, noreorder
_Mul32:       lda     long:mul32_sqr+1020
              bne     5$              ; f(510): the table is made
              jsr     .kbank build
5$:           lda     dp:.tiny (_Dp+6)
              pha                     ; bH
              lda     dp:.tiny (_Dp+4)
              pha                     ; bL
              lda     dp:.tiny (_Dp+2)
              pha                     ; aH
              lda     dp:.tiny _Dp
              pha                     ; aL
              phd
              tsc
              sec
              sbc     ##LOCALS
              tcs
              tcd                     ; D = the frame

;;; aL * bL, in full: a0b0 + ((a0b1 + a1b0) << 8) + (a1b1 << 16)
              lda     dp:aL
              and     ##0x00ff
              tay                     ; a0
              lda     dp:bL
              and     ##0x00ff        ; b0
              jsr     .kbank m8
              sta     dp:r0
              lda     dp:aL
              xba
              and     ##0x00ff
              tay                     ; a1
              lda     dp:bL
              xba
              and     ##0x00ff        ; b1
              jsr     .kbank m8
              sta     dp:r1           ; a1b1, the high word's start
              lda     dp:aL
              and     ##0x00ff
              tay                     ; a0
              lda     dp:bL
              xba
              and     ##0x00ff        ; b1
              jsr     .kbank m8
              sta     dp:mid          ; a0b1
              lda     dp:aL
              xba
              and     ##0x00ff
              tay                     ; a1
              lda     dp:bL
              and     ##0x00ff        ; b0
              jsr     .kbank m8       ; a1b0
              clc
              adc     dp:mid
              sta     dp:mid
              lda     ##0
              rol     a
              xba
              sta     dp:mhi          ; the sum's 17th bit, at bit 8 of r1
              lda     dp:mid
              xba
              and     ##0xff00        ; mid << 8, the low word's part
              clc
              adc     dp:r0
              sta     dp:r0
              lda     dp:mid
              xba
              and     ##0x00ff        ; mid >> 8 ...
              ora     dp:mhi          ; ...and its carry
              adc     dp:r1           ; with the carry out of r0
              sta     dp:r1

;;; + (aL * bH) << 16, its low 16 bits: a0c0 + ((a0c1 + a1c0) << 8)
              lda     dp:bH
              beq     20$
              ldx     dp:aL
              jsr     .kbank cross
              clc
              adc     dp:r1
              sta     dp:r1

;;; + (aH * bL) << 16, the same
20$:          lda     dp:aH
              beq     30$
              ldx     dp:bL
              jsr     .kbank cross
              clc
              adc     dp:r1
              sta     dp:r1

30$:          lda     dp:r0
              tay
              ldx     dp:r1
              tsc
              clc
              adc     ##LOCALS
              tcs
              pld
              pla                     ; the four operand words
              pla
              pla
              pla
              tya
              rtl

;;; The low 16 bits of p * q, for p in A and q in X, nonzero p:
;;; p0q0 + ((p0q1 + p1q0) << 8), each byte product by m8.
cross:        sta     dp:mid          ; p, kept
              txa
              sta     dp:mhi          ; q, kept
              and     ##0x00ff
              tay                     ; q0
              lda     dp:mid
              and     ##0x00ff        ; p0
              jsr     .kbank m8
              pha                     ; p0q0
              lda     dp:mhi
              xba
              and     ##0x00ff
              tay                     ; q1
              lda     dp:mid
              and     ##0x00ff        ; p0
              jsr     .kbank m8
              pha                     ; p0q1
              lda     dp:mhi
              and     ##0x00ff
              tay                     ; q0
              lda     dp:mid
              xba
              and     ##0x00ff        ; p1
              jsr     .kbank m8       ; p1q0
              clc
              adc     1,s             ; + p0q1: only its low byte survives
              xba
              and     ##0xff00        ; << 8
              clc
              adc     3,s             ; + p0q0
              tay
              pla
              pla
              tya
              rts

;;; x * y for bytes x in A and y in Y: f(x + y) - f(|x - y|).
m8:           sta     dp:tx
              sty     dp:ty
              clc
              adc     dp:ty
              asl     a
              tax
              lda     long:mul32_sqr,x
              sta     dp:tp
              lda     dp:tx
              sec
              sbc     dp:ty
              bcs     10$
              eor     ##0xffff
              inc     a
10$:          asl     a
              tax
              lda     dp:tp
              sec
              sbc     long:mul32_sqr,x
              rts

;;; The table, made on the first call: f(0) = 0 and f(n) = f(n - 1) +
;;; floor(n / 2).  f(510) is written last, so it being nonzero means the
;;; table is whole.  A, X and Y only: the operands in _Dp are untouched.
build:        ldy     ##0             ; f(n - 1), f(0) = 0 to start
              ldx     ##2             ; 2n, n = 1
10$:          txa
              lsr     a
              lsr     a               ; floor(n / 2)
              phy
              clc
              adc     1,s             ; + f(n - 1)
              ply
              tay
              sta     long:mul32_sqr,x
              inx
              inx
              cpx     ##1022
              bne     10$
              rts

;;; f(n) = floor(n * n / 4), n = 0..510: zeroed at start-up, made by build
              .section zfar, bss
              .align  2
mul32_sqr:    .space  1022
