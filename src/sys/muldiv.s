;;; ---------------------------------------------------------------------------
;;; muldiv.s -- umuldiv(a, b, c) = floor(a * b / c), unsigned 16-bit.
;;;
;;; WHY.  The polygon filler (src/vdi/vdi.c, clc_flit) finds where an edge
;;; crosses each scan line as (int32)t * dx / dy, which the compiler makes
;;; a call to the library's _Mul32 and one to _UDivMod32: a third of a
;;; filled circle's time (docs/phase93.md).  The operands are small -- the
;;; caller checks that they are -- and then the 32-bit product of two
;;; 16-bit numbers, divided by a third, has a 16-bit quotient.  That is
;;; one shift-and-add multiply and one sixteen-step division, here.
;;;
;;; THE CALL is the compiler's for three uint16_t arguments: a in A, b in
;;; _Dp+0, c in _Dp+2; the quotient comes back in A.  _Dp+0..7 and Y are
;;; scratch, as they are to any callee.
;;;
;;; THE CONTRACT the caller keeps: c is not zero and a * b / c < 65536,
;;; i.e. the product's high word is below c.  Outside it the answer is
;;; wrong, not a trap; clc_flit only calls this when every coordinate of
;;; the polygon is within +-16383, where |t| <= |dy| makes the quotient at
;;; most |dx| <= 65532.
;;;
;;; FLIT_SCAN is the loop that calls it, one scan line of clc_flit's small
;;; case (flit_small): the compiler keeps every variable of that loop on
;;; the stack and checks each signed compare for overflow, about sixty
;;; cycles an edge of which a circle has dozens on each of a hundred
;;; lines.  Here no compare can overflow -- the caller's +-16383 again --
;;; so each is a subtract and a branch.
;;;
;;; tests/host/test_muldiv.py runs both in the vendor's simulator, the one
;;; against Python and the other against the C it replaced.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"

              .extern _Dp
              .public umuldiv, flit_scan

;;; md's operands: a in A, then these.  _Dp+0..7 are any callee's scratch.
mb            .equ    _Dp             ; b
mc            .equ    _Dp+2           ; c
lo            .equ    _Dp+4           ; the product's low word, then the quotient

;;; src/vdi/vdi.c's, which tests/host/test_muldiv.py holds this to
MAX_INTERSECT .equ    32

;;; uint16_t umuldiv(uint16_t a, uint16_t b, uint16_t c): the compiler
;;; leaves b and c where md wants them.
              .section farcode, noreorder
umuldiv:      jsr     .kbank md
              rtl

;;; a * b: the multiplier a shifts out of the bottom of `lo` while the
;;; product's low bits shift in at the top; A is the high word.
md:           sta     dp:.tiny lo
              lda     ##0
              ldy     ##16
              lsr     dp:.tiny lo     ; C = a's bit 0
10$:          bcc     20$
              clc
              adc     dp:.tiny mb     ; + b
20$:          ror     a               ; the add's carry in at the top
              ror     dp:.tiny lo     ; a product bit in, the next bit of a out
              dey
              bne     10$
;;; A:lo / c, restoring: the quotient's bits shift into the bottom of `lo`.
              ldy     ##16
30$:          asl     dp:.tiny lo
              rol     a
              bcs     40$             ; seventeen bits: certainly >= c
              cmp     dp:.tiny mc
              bcc     50$
40$:          sbc     dp:.tiny mc     ; C is set on both ways in
              inc     dp:.tiny lo
50$:          dey
              bne     30$
              lda     dp:.tiny lo
              rts

;;; WORD flit_scan(const WORD *pt, WORD vectors, WORD y, WORD *out)
;;;
;;; Where each edge pt[i] -> pt[i + 1] crosses scan line y, in edge order,
;;; into out[], at most MAX_INTERSECT of them; answers how many.  Exactly
;;; flit_small's inner loop: an edge from y1 to y2 is crossed when
;;; y1 <= y < y2 or y2 <= y < y1, and the crossing is
;;;
;;;     asr(t * 2|x2 - x1| / |y2 - y1| + 1, 1) + min(x1, x2)
;;;
;;; with t = |y - y1| when x1 <= x2 and |y - y2| when not.  pt in A,
;;; vectors in _Dp+0, y in _Dp+2, out on the stack; the points are near
;;; data, read through DB = $00 as the compiler's are.
F_BASE        .equ    1               ; min(x1, x2)
F_DY          .equ    3               ; |y2 - y1|
F_N           .equ    5               ; crossings so far, in bytes
F_P           .equ    7               ; this edge's first point
F_CNT         .equ    9               ; edges left
F_Y           .equ    11              ; the scan line
F_LOCALS      .equ    12
F_OUT         .equ    F_LOCALS + 4    ; past the return address

flit_scan:    tax
              lda     dp:.tiny (_Dp+2)
              pha                     ; F_Y
              lda     dp:.tiny _Dp
              pha                     ; F_CNT
              phx                     ; F_P
              lda     ##0
              pha                     ; F_N
              pha                     ; F_DY
              pha                     ; F_BASE
fs_next:      lda     F_CNT,s
              bne     11$
              jmp     .kbank fs_done
11$:          ldy     ##6
              lda     (F_P,s),y       ; y2
              ldy     ##2
              sec
              sbc     (F_P,s),y       ; - y1
              beq     80$             ; horizontal: never crossed
              bmi     20$
              sta     F_DY,s          ; y1 < y2
              lda     F_Y,s
              sec
              sbc     (F_P,s),y       ; u = y - y1, crossed if 0 <= u < dy
              bmi     80$
              cmp     F_DY,s
              bcs     80$
              tax                     ; X = u = |y - y1|
              bra     30$
20$:          eor     ##0xffff        ; y2 < y1
              inc     a
              sta     F_DY,s
              ldy     ##6
              lda     F_Y,s
              sec
              sbc     (F_P,s),y       ; v = y - y2, crossed if 0 <= v < dy
              bmi     80$
              cmp     F_DY,s
              bcs     80$
              eor     ##0xffff
              sec
              adc     F_DY,s          ; dy - v
              tax                     ; X = u = |y - y1|
30$:          lda     F_N,s
              cmp     ##MAX_INTERSECT * 2
              bcs     fs_done         ; full: the donor breaks here too
              ldy     ##4
              lda     (F_P,s),y       ; x2
              ldy     ##0
              sec
              sbc     (F_P,s),y       ; - x1
              bmi     40$
              asl     a               ; x1 <= x2: 2(x2 - x1), from x1, by u
              sta     dp:.tiny mb
              lda     (F_P,s),y
              sta     F_BASE,s
              txa
              bra     50$
40$:          eor     ##0xffff        ; x2 < x1: 2(x1 - x2), from x2, by
              inc     a               ; |y - y2| = dy - u
              asl     a
              sta     dp:.tiny mb
              ldy     ##4
              lda     (F_P,s),y
              sta     F_BASE,s
              txa
              eor     ##0xffff
              sec
              adc     F_DY,s
50$:          tax
              lda     F_DY,s
              sta     dp:.tiny mc
              txa
              jsr     .kbank md       ; t * dx / dy
              inc     a
              cmp     ##0x8000
              ror     a               ; asr(q + 1, 1)
              clc
              adc     F_BASE,s
              tax
              lda     F_N,s
              tay
              txa
              sta     (F_OUT,s),y
              iny
              iny
              tya
              sta     F_N,s
80$:          lda     F_P,s           ; the next edge
              clc
              adc     ##4
              sta     F_P,s
              lda     F_CNT,s
              dec     a
              sta     F_CNT,s
              jmp     .kbank fs_next
fs_done:      lda     F_N,s
              lsr     a
              tax
              tsc
              clc
              adc     ##F_LOCALS
              tcs
              txa
              rtl
