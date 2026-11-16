;;; ---------------------------------------------------------------------------
;;; antic6502.s -- the ANTIC driver's inner loops on the 6502
;;; (src/antic/antic.c; docs/6502.md, "Speed"), where cc6502's C was the
;;; most of a window's redraw:
;;;
;;;   an_fill6    the middle of a filled row (antic_fill_rect)
;;;   an_cblk6    the block under the pointer, saved or put back
;;;   an_cpaint6  the pointer itself (antic_cursor_paint)
;;;
;;; All three IN THE ANTIC BANK, beside their callers: section `antic`,
;;; which the link files put in that bank, so they cost no resident memory.
;;;
;;; ---- an_fill6 ---------------------------------------------------------
;;;   void an_fill6(volatile uint8_t *q, uint8_t n, uint8_t f, uint8_t g)
;;;
;;; n bytes from q: f at the even offsets, g at the odd -- a pattern's two
;;; halves, or one value twice.  The 65C816 build stores them as words; in
;;; cc6502's C either way it was ~25 cycles a byte, here 13: from the top
;;; down, (q),y.  n is at most a row, 40, so Y stays positive.
;;;
;;; q in _Zp0-1, n in A, f in _Zp2, g in _Zp3 (Calypsi's first fit).
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp
              .public an_fill6, an_cblk6, an_cpaint6

              .section antic,text
an_fill6:     tay
              beq     9$
              dey                     ; the last offset, n - 1
              tya
              lsr     a               ; odd?
              bcc     2$
1$:           lda     zp:_Zp+3        ; an odd offset: g
              sta     (_Zp),y
              dey
2$:           lda     zp:_Zp+2        ; an even one: f
              sta     (_Zp),y
              dey
              bpl     1$
9$:           rts

;;; ---- an_cblk6 ---------------------------------------------------------
;;;   void an_cblk6(volatile uint8_t *scr, uint8_t *buf, uint8_t nb,
;;;                 uint8_t nr, uint8_t dir)
;;;
;;; nr rows of nb bytes (nb 1-3) between the screen from scr, a row 40
;;; bytes on, and buf, 3 bytes a row: dir 0 saves the screen into buf, 1
;;; puts it back.  scr in _Zp0-1, buf _Zp2-3, nb A, nr _Zp4, dir _Zp5.
an_cblk6:     sta     zp:_Zp+6
              ldx     zp:_Zp+4
              beq     9$
1$:           ldy     zp:_Zp+6
              dey
              lda     zp:_Zp+5
              bne     3$
2$:           lda     (_Zp),y         ; save: the screen into buf
              sta     (_Zp+2),y
              dey
              bpl     2$
              bmi     5$
3$:           lda     (_Zp+2),y       ; put back
              sta     (_Zp),y
              dey
              bpl     3$
5$:           clc                     ; the next row, and the next three
              lda     zp:_Zp
              adc     #40
              sta     zp:_Zp
              bcc     6$
              inc     zp:_Zp+1
6$:           clc
              lda     zp:_Zp+2
              adc     #3
              sta     zp:_Zp+2
              bcc     7$
              inc     zp:_Zp+3
7$:           dex
              bne     1$
9$:           rts

;;; ---- an_cpaint6 -------------------------------------------------------
;;;   void an_cpaint6(const uint8_t *a)
;;;
;;; The pointer, already clipped by antic_cursor_paint, from eleven bytes:
;;;
;;;   a[0-1]  the screen byte of the first row drawn, at the form's first
;;;           byte column (which may be -1: off the left edge)
;;;   a[2-3]  its mask row, a[4-5] its data row (16-bit words)
;;;   a[6]    rows to draw; a[7] the shift, 0-7
;;;   a[8]    which of the row's three byte columns are on the screen,
;;;           bit c for column c
;;;   a[9]    fg as a byte, $FF or 0; a[10] bg likewise
;;;
;;; Each row, the form's 16 bits shifted into a 24-bit row; a data bit
;;; paints fg, a mask bit that is not data paints bg: antic_plot's rule.
;;; Working state in _Zp2-21: the 24-bit data D at 2-4, the mask M at 5-7,
;;; the arguments at 8-18, scratch at 19-21.
an_cpaint6:   ldy     #10
1$:           lda     (_Zp),y
              sta     _Zp+8,y
              dey
              bpl     1$
              ldx     zp:_Zp+14       ; the rows
              bne     10$
              rts
10$:          ldy     #1              ; the row's words, high byte leftmost
              lda     (_Zp+12),y
              sta     zp:_Zp+2
              lda     (_Zp+10),y
              sta     zp:_Zp+5
              dey
              lda     (_Zp+12),y
              sta     zp:_Zp+3
              lda     (_Zp+10),y
              sta     zp:_Zp+6
              lda     #0
              sta     zp:_Zp+4
              sta     zp:_Zp+7
              ldy     zp:_Zp+15       ; shifted into place
              beq     20$
11$:          lsr     zp:_Zp+2
              ror     zp:_Zp+3
              ror     zp:_Zp+4
              lsr     zp:_Zp+5
              ror     zp:_Zp+6
              ror     zp:_Zp+7
              dey
              bne     11$
20$:          lda     zp:_Zp+16       ; the columns on the screen
              sta     zp:_Zp+19
              ldy     #0
21$:          lsr     zp:_Zp+19
              bcc     29$
              lda     _Zp+2,y         ; bg's bits: the mask's, not data's
              eor     #0xff
              and     _Zp+5,y
              sta     zp:_Zp+20
              ora     _Zp+2,y         ; any bit to paint at all?
              beq     29$
              eor     #0xff
              and     (_Zp+8),y       ; what is left of the screen's
              sta     zp:_Zp+21
              lda     _Zp+2,y
              and     zp:_Zp+17
              ora     zp:_Zp+21
              sta     zp:_Zp+21
              lda     zp:_Zp+20
              and     zp:_Zp+18
              ora     zp:_Zp+21
              sta     (_Zp+8),y
29$:          iny
              cpy     #3
              bne     21$
              clc                     ; the next row: 40 bytes on, and the
              lda     zp:_Zp+8        ; form's next words
              adc     #40
              sta     zp:_Zp+8
              bcc     30$
              inc     zp:_Zp+9
30$:          clc
              lda     zp:_Zp+10
              adc     #2
              sta     zp:_Zp+10
              bcc     31$
              inc     zp:_Zp+11
31$:          clc
              lda     zp:_Zp+12
              adc     #2
              sta     zp:_Zp+12
              bcc     32$
              inc     zp:_Zp+13
32$:          dex
              beq     33$
              jmp     10$             ; out of a branch's reach
33$:          rts
