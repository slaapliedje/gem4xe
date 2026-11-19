;;; ---------------------------------------------------------------------------
;;; antic6502.s -- the ANTIC driver's inner loops on the 6502
;;; (src/antic/antic.c; docs/6502.md, "Speed"), where cc6502's C was the
;;; most of a window's redraw:
;;;
;;;   an_fill6    the middle of a filled row (antic_fill_rect)
;;;   an_rect6    a whole constant-op rectangle, every row (the same)
;;;   an_cblk6    the block under the pointer, saved or put back
;;;   an_cpaint6  the pointer itself (antic_cursor_paint)
;;;   an_vline6   a vertical line, styled (antic_vline)
;;;   an_frect6   antic_fill_rect from the clipping on (speed 6)
;;;   an_vl6      antic_vline from the clipping on, into an_vline6's rows
;;;   an_pack6_s  one row of a string's glyphs, packed (antic_text)
;;;   an_put_row_s  ...and that row onto the screen through the op
;;;   an_text6    every row of a string, the two above in turn
;;;   an_shl6     a form's row shifted left (dev's bank: copy_rows)
;;;   an_shl6a    the same, here (antic_raster_row: an icon's row)
;;;
;;; All of them IN THE ANTIC BANK, beside their callers: section `antic`,
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
              .extern ap_sr, ap_chars, ap_buf, ap_n, ap_lead, an_pack6_c
              .extern pr_buf, pr_scr, pr_last, pr_lm, pr_rm
              .extern pr_x1, pr_y1, pr_x0, pr_y0
              .public an_fill6, an_rect6, an_cblk6, an_cpaint6, an_vline6
              .public an_pack6_s, an_put_row_s, an_shl6, an_text6, an_shl6a
              .public an_frect6, an_vl6, an_rev4
              .extern an_fr, an_vl

FR_SCREEN:    .equ    0x8100          ; AN_SCREEN, src/antic/antic.h

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

;;; ---- an_rect6 ---------------------------------------------------------
;;;   void an_rect6(const uint8_t *a)
;;;
;;; A rectangle whose op is a constant per byte (antic_fill_rect's how 0),
;;; all of it: antic_fill_rect clips it and works the op out, then hands
;;; over ten bytes:
;;;
;;;   a[0-1]  the first row's first byte
;;;   a[2]    rows, 1-192; a[3] last, the row's last byte offset, 0-39
;;;   a[4]    the left edge's mask (with the right's when last is 0)
;;;   a[5]    the right edge's mask
;;;   a[6]    the first row's pattern index (y & 15); a[7] the index mask,
;;;           15 for a pattern, 0 for solid
;;;   a[8-9]  32 bytes: [i] the value of row i's EVEN offsets from the
;;;           first byte, [16 + i] its odd ones'
;;;
;;; An edge byte is (d & ~m) | (v & m); the middle is v.  Per row in C it
;;; was ~30 cycles of setup before the middle (docs/6502.md, "Speed").
;;; Working state: the arguments at _Zp2-11, v even 12, v odd 13, scratch
;;; 14, ~lm 15, ~rm 16.
an_rect6:     ldy     #9
1$:           lda     (_Zp),y
              sta     _Zp+2,y
              dey
              bpl     1$
              lda     zp:_Zp+6
              eor     #0xff
              sta     zp:_Zp+15
              lda     zp:_Zp+7
              eor     #0xff
              sta     zp:_Zp+16
              ldx     zp:_Zp+4        ; rows
              bne     10$
              rts
10$:          lda     zp:_Zp+8        ; this row's two values
              and     zp:_Zp+9
              tay
              lda     (_Zp+10),y
              sta     zp:_Zp+12
              tya
              ora     #16
              tay
              lda     (_Zp+10),y
              sta     zp:_Zp+13
              ldy     #0              ; the left edge
              lda     (_Zp+2),y
              and     zp:_Zp+15
              sta     zp:_Zp+14
              lda     zp:_Zp+12
              and     zp:_Zp+6
              ora     zp:_Zp+14
              sta     (_Zp+2),y
              ldy     zp:_Zp+5        ; last
              beq     30$
              lda     (_Zp+2),y       ; the right edge
              and     zp:_Zp+16
              sta     zp:_Zp+14
              tya
              lsr     a
              lda     zp:_Zp+12
              bcc     11$
              lda     zp:_Zp+13
11$:          and     zp:_Zp+7
              ora     zp:_Zp+14
              sta     (_Zp+2),y
              dey                     ; the middle, last - 1 down to 1
              beq     30$
              tya
              lsr     a
              bcc     22$
21$:          lda     zp:_Zp+13       ; an odd offset
              sta     (_Zp+2),y
              dey
              beq     30$
22$:          lda     zp:_Zp+12       ; an even one
              sta     (_Zp+2),y
              dey
              bne     21$
30$:          clc                     ; the next row
              lda     zp:_Zp+2
              adc     #40
              sta     zp:_Zp+2
              bcc     31$
              inc     zp:_Zp+3
31$:          inc     zp:_Zp+8
              dex
              bne     10$
              rts

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

;;; ---- an_vline6 --------------------------------------------------------
;;;   void an_vline6(const uint8_t *a)
;;;
;;; A one-pixel column, every row: antic_vline clips it and hands over
;;;
;;;   a[0-1]  the top row's byte          a[7]   AND for a set style bit
;;;   a[2]    rows, 1-192                 a[8]   XOR for a set style bit
;;;   a[3-4]  the style, 16 bits          a[9]   AND for a clear one
;;;   a[5-6]  the top row's style bit     a[10]  XOR for a clear one
;;;
;;; A row is d = (d & AND) ^ XOR: AN_MIX for the one pixel, with the bits
;;; outside the column ANDed by ones and XORed by nothing.  The style bit
;;; moves down a place a row and wraps at 16.  In C a row was ~110
;;; cycles, the most of it the style's shift; here ~40.
;;; ---------------------------------------------------------------------------
an_vline6:    ldy     #10
1$:           lda     (_Zp),y
              sta     _Zp+2,y
              dey
              bpl     1$
an_vl6_rows:  ldy     #0              ; (an_vl6 enters here, state set)
2$:           lda     zp:_Zp+5        ; the style bit of this row
              and     zp:_Zp+7
              bne     4$
              lda     zp:_Zp+6
              and     zp:_Zp+8
              bne     4$
              lda     (_Zp+2),y       ; clear
              and     zp:_Zp+11
              eor     zp:_Zp+12
              sta     (_Zp+2),y
              jmp     5$
4$:           lda     (_Zp+2),y       ; set
              and     zp:_Zp+9
              eor     zp:_Zp+10
              sta     (_Zp+2),y
5$:           lda     zp:_Zp+2        ; the next row, 40 bytes on
              clc
              adc     #40
              sta     zp:_Zp+2
              bcc     6$
              inc     zp:_Zp+3
6$:           lsr     zp:_Zp+8        ; the style bit down one
              ror     zp:_Zp+7
              bcc     7$
              lda     #0x80           ; out of the bottom: bit 15 again
              sta     zp:_Zp+8
7$:           dec     zp:_Zp+4
              bne     2$
              rts

;;; ---- an_frect6 --------------------------------------------------------
;;;   uint8_t an_frect6(void)
;;;
;;; antic_fill_rect, all of it, for every op that is a constant or an XOR
;;; per byte (src/antic/antic.c, an_fr): the arguments are in an_fr --
;;;   +0 x1  +2 y1  +4 x2  +6 y2   (int16, either order, any value)
;;;   +8 rows  sixteen pattern words indexed by y & 15, 0 for solid; each
;;;            word's HIGH byte is the even screen bytes', the low the odd
;;;   +10 mode (1 replace, 2 transparent, 3 XOR, 4 erase)  +12 pen
;;; Answers 0 if it is done (drawn, or nothing to draw), and 1 for what it
;;; leaves to an_fill_c: a pattern in transparent or erase, and any other
;;; mode.  The value a byte takes is (s ^ inv), s the source -- the
;;; pattern's half or $FF -- and inv $FF for replace in pen 0; XOR flips
;;; s's bits instead.  An edge byte is (d & k) ^ (v & m), k ~m for a
;;; constant and $FF for XOR; the middle is v, or d ^ v.  In C this setup
;;; was ~2,000 cycles a rectangle (docs/6502.md, "Speed 6").
;;;
;;; Working state, all in the caller-saved _Zp0-23:
;;;   0 v at an even offset from the first byte, 1 at an odd one
;;;   2 the pattern index (y & 15, counting up)  3 patterned?
;;;   4 scratch  5 the first byte is odd  6 scratch
;;;   8-9 rows  10 bit 7: XOR  11 inv  13 b1  14 last (offset of the
;;;   last byte)  15 lm  16 rm  17 rows left  20-21 the row's first byte
;;;   22 k left  23 k right
an_frect6:    ldx     #12
1$:           lda     an_fr,x
              sta     zp:_Zp,x
              dex
              bpl     1$
              lda     zp:_Zp+11       ; the mode
              bne     90$
              lda     zp:_Zp+10
              cmp     #1
              beq     3$
              cmp     #2
              beq     2$
              cmp     #3
              beq     5$
              cmp     #4
              bne     90$
              lda     zp:_Zp+8        ; erase: a solid source erases nothing
              ora     zp:_Zp+9
              bne     90$
              rts                     ; (A is 0)
2$:           lda     zp:_Zp+8        ; transparent: solid only
              ora     zp:_Zp+9
              bne     90$
3$:           ldx     #0              ; replace (and solid transparent):
              lda     zp:_Zp+12       ; inv $FF in pen 0
              bne     4$
              dex
4$:           stx     zp:_Zp+11
              lda     #0
              sta     zp:_Zp+10
              beq     10$
5$:           lda     #0x80           ; XOR
              sta     zp:_Zp+10
              lda     #0
              sta     zp:_Zp+11
              beq     10$
90$:          lda     #1              ; an_fill_c's
              rts

10$:          lda     zp:_Zp+4        ; x2 < x1: swap
              cmp     zp:_Zp+0
              lda     zp:_Zp+5
              sbc     zp:_Zp+1
              bvc     11$
              eor     #0x80
11$:          bpl     12$
              ldx     zp:_Zp+0
              lda     zp:_Zp+4
              sta     zp:_Zp+0
              stx     zp:_Zp+4
              ldx     zp:_Zp+1
              lda     zp:_Zp+5
              sta     zp:_Zp+1
              stx     zp:_Zp+5
12$:          lda     zp:_Zp+6        ; y2 < y1: swap
              cmp     zp:_Zp+2
              lda     zp:_Zp+7
              sbc     zp:_Zp+3
              bvc     13$
              eor     #0x80
13$:          bpl     14$
              ldx     zp:_Zp+2
              lda     zp:_Zp+6
              sta     zp:_Zp+2
              stx     zp:_Zp+6
              ldx     zp:_Zp+3
              lda     zp:_Zp+7
              sta     zp:_Zp+3
              stx     zp:_Zp+7
14$:          lda     zp:_Zp+5        ; off the screen: nothing
              bmi     91$             ; x2 < 0
              lda     zp:_Zp+7
              bmi     91$             ; y2 < 0
              lda     zp:_Zp+1
              bmi     15$             ; x1 < 0: 0, below
              lda     zp:_Zp+0
              cmp     #0x40
              lda     zp:_Zp+1
              sbc     #0x01
              bcs     91$             ; x1 >= 320
              bcc     16$
15$:          lda     #0
              sta     zp:_Zp+0
              sta     zp:_Zp+1
16$:          lda     zp:_Zp+3
              bmi     17$             ; y1 < 0: 0
              bne     91$             ; y1 >= 256
              lda     zp:_Zp+2
              cmp     #192
              bcs     91$             ; y1 >= 192
              bcc     18$
17$:          lda     #0
              sta     zp:_Zp+2
18$:          lda     zp:_Zp+4        ; x2 > 319: 319
              cmp     #0x40
              lda     zp:_Zp+5
              sbc     #0x01
              bcc     19$
              lda     #0x3F
              sta     zp:_Zp+4
              lda     #0x01
              sta     zp:_Zp+5
19$:          lda     zp:_Zp+7        ; y2 > 191: 191
              bne     20$
              lda     zp:_Zp+6
              cmp     #192
              bcc     21$
20$:          lda     #191
              sta     zp:_Zp+6
              bne     21$
91$:          lda     #0
              rts

21$:          lda     zp:_Zp+0        ; the edges' masks
              and     #7
              tax
              lda     fr_left,x
              sta     zp:_Zp+15
              lda     zp:_Zp+4
              and     #7
              tax
              lda     fr_right,x
              sta     zp:_Zp+16
              lda     zp:_Zp+5        ; b2 = x2 >> 3, for last
              lsr     a
              lda     zp:_Zp+4
              ror     a
              lsr     a
              lsr     a
              sta     zp:_Zp+14
              lda     zp:_Zp+1        ; b1 = x1 >> 3
              lsr     a
              lda     zp:_Zp+0
              ror     a
              lsr     a
              lsr     a
              sta     zp:_Zp+13
              and     #1
              sta     zp:_Zp+5
              lda     zp:_Zp+14       ; last = b2 - b1
              sec
              sbc     zp:_Zp+13
              sta     zp:_Zp+14
              bne     22$
              lda     zp:_Zp+15       ; one byte: both edges in it
              and     zp:_Zp+16
              sta     zp:_Zp+15
22$:          bit     zp:_Zp+10       ; k: $FF for XOR, else ~m
              bpl     23$
              lda     #0xff
              sta     zp:_Zp+22
              sta     zp:_Zp+23
              bne     24$
23$:          lda     zp:_Zp+15
              eor     #0xff
              sta     zp:_Zp+22
              lda     zp:_Zp+16
              eor     #0xff
              sta     zp:_Zp+23
24$:          lda     zp:_Zp+6        ; rows = y2 - y1 + 1
              sec
              sbc     zp:_Zp+2
              clc
              adc     #1
              sta     zp:_Zp+17
              lda     #0              ; the first byte: the screen
              sta     zp:_Zp+21       ; + y1 * 40 + b1
              lda     zp:_Zp+2
              asl     a
              rol     zp:_Zp+21
              asl     a
              rol     zp:_Zp+21
              asl     a
              rol     zp:_Zp+21
              sta     zp:_Zp+4        ; y1 * 8
              ldx     zp:_Zp+21
              asl     a
              rol     zp:_Zp+21
              asl     a
              rol     zp:_Zp+21       ; y1 * 32
              clc
              adc     zp:_Zp+4
              sta     zp:_Zp+20
              txa
              adc     zp:_Zp+21
              sta     zp:_Zp+21
              lda     zp:_Zp+20
              clc
              adc     zp:_Zp+13
              sta     zp:_Zp+20
              bcc     25$
              inc     zp:_Zp+21
25$:          lda     zp:_Zp+20
              clc
              adc     #.byte0 FR_SCREEN
              sta     zp:_Zp+20
              lda     zp:_Zp+21
              adc     #.byte1 FR_SCREEN
              sta     zp:_Zp+21
              lda     zp:_Zp+8        ; patterned?
              ora     zp:_Zp+9
              sta     zp:_Zp+3
              bne     30$
              lda     #0xff           ; solid: one value for every byte
              eor     zp:_Zp+11
              sta     zp:_Zp+0
              sta     zp:_Zp+1

30$:          lda     zp:_Zp+3        ; A ROW: its pattern's two values
              beq     40$
              lda     zp:_Zp+2
              and     #15
              asl     a
              tay
              lda     (_Zp+8),y       ; the low byte: odd screen bytes
              eor     zp:_Zp+11
              sta     zp:_Zp+4
              iny
              lda     (_Zp+8),y       ; the high: even ones
              eor     zp:_Zp+11
              ldx     zp:_Zp+5
              bne     31$
              sta     zp:_Zp+0        ; b1 even: offset parity = screen's
              lda     zp:_Zp+4
              sta     zp:_Zp+1
              jmp     40$
31$:          sta     zp:_Zp+1        ; b1 odd: swapped
              lda     zp:_Zp+4
              sta     zp:_Zp+0
40$:          ldy     #0              ; the left edge
              lda     (_Zp+20),y
              and     zp:_Zp+22
              sta     zp:_Zp+6
              lda     zp:_Zp+0
              and     zp:_Zp+15
              eor     zp:_Zp+6
              sta     (_Zp+20),y
              ldy     zp:_Zp+14       ; last
              beq     60$
              lda     (_Zp+20),y      ; the right edge
              and     zp:_Zp+23
              sta     zp:_Zp+6
              tya
              lsr     a
              lda     zp:_Zp+0
              bcc     41$
              lda     zp:_Zp+1
41$:          and     zp:_Zp+16
              eor     zp:_Zp+6
              sta     (_Zp+20),y
              dey                     ; the middle, last - 1 down to 1
              beq     60$
              bit     zp:_Zp+10
              bmi     50$
              tya
              lsr     a
              bcc     43$
42$:          lda     zp:_Zp+1        ; an odd offset
              sta     (_Zp+20),y
              dey
              beq     60$
43$:          lda     zp:_Zp+0        ; an even one
              sta     (_Zp+20),y
              dey
              bne     42$
              beq     60$
50$:          tya                     ; XOR's middle
              lsr     a
              bcc     53$
52$:          lda     (_Zp+20),y
              eor     zp:_Zp+1
              sta     (_Zp+20),y
              dey
              beq     60$
53$:          lda     (_Zp+20),y
              eor     zp:_Zp+0
              sta     (_Zp+20),y
              dey
              bne     52$
60$:          clc                     ; the next row
              lda     zp:_Zp+20
              adc     #40
              sta     zp:_Zp+20
              bcc     61$
              inc     zp:_Zp+21
61$:          inc     zp:_Zp+2
              dec     zp:_Zp+17
              beq     62$
              jmp     30$
62$:          lda     #0
              rts

;;; antic.c's an_left and an_right: bit 7 is the leftmost pixel
fr_left:      .byte   0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01
fr_right:     .byte   0x80, 0xC0, 0xE0, 0xF0, 0xF8, 0xFC, 0xFE, 0xFF

;;; ---- an_vl6 -----------------------------------------------------------
;;;   void an_vl6(void)
;;;
;;; antic_vline, all of it (src/antic/antic.c, an_vl): the column x from
;;; y1 to y2, in a 16-bit style anchored to the screen's rows, in a mode
;;; and pen --
;;;   +0 x  +2 y1  +4 y2  (int16, y either order)  +6 the style
;;;   +8 mode (1 replace, 2 transparent, 3 XOR, 4 erase; else replace with
;;;      both pens the pen, as an_op_pen has it)  +10 pen
;;; clipped, and the op for the one pixel worked out as an_vline6's AND
;;; and XOR each way, then an_vline6's rows (an_vl6_rows).  In C this
;;; setup was ~1,200 cycles a line (docs/6502.md, "Speed 6").
;;; The arguments are copied to _Zp13-23; an_vline6's state is _Zp2-12.
an_vl6:       ldx     #10
1$:           lda     an_vl,x
              sta     zp:_Zp+13,x
              dex
              bpl     1$
              lda     zp:_Zp+14       ; x off the screen: nothing
              bmi     90$
              lda     zp:_Zp+13
              cmp     #0x40
              lda     zp:_Zp+14
              sbc     #0x01
              bcs     90$             ; x >= 320
              lda     zp:_Zp+17       ; y2 < y1: swap
              cmp     zp:_Zp+15
              lda     zp:_Zp+18
              sbc     zp:_Zp+16
              bvc     2$
              eor     #0x80
2$:           bpl     3$
              ldx     zp:_Zp+15
              lda     zp:_Zp+17
              sta     zp:_Zp+15
              stx     zp:_Zp+17
              ldx     zp:_Zp+16
              lda     zp:_Zp+18
              sta     zp:_Zp+16
              stx     zp:_Zp+18
3$:           lda     zp:_Zp+18       ; y2 < 0: nothing
              bmi     90$
              bne     4$              ; y2 > 191: 191
              lda     zp:_Zp+17
              cmp     #192
              bcc     5$
4$:           lda     #191
              sta     zp:_Zp+17
5$:           lda     zp:_Zp+16       ; y1 < 0: 0
              bpl     6$
              lda     #0
              sta     zp:_Zp+15
              beq     7$
6$:           bne     90$             ; y1 >= 256
              lda     zp:_Zp+15
              cmp     #192
              bcs     90$             ; y1 > 191
7$:           lda     zp:_Zp+17       ; rows = y2 - y1 + 1
              sec
              sbc     zp:_Zp+15
              bcc     90$
              adc     #0              ; (carry set: + 1)
              sta     zp:_Zp+4
              lda     zp:_Zp+19       ; the style
              sta     zp:_Zp+5
              lda     zp:_Zp+20
              sta     zp:_Zp+6
              lda     zp:_Zp+15       ; its bit for the top row,
              and     #7              ; 0x8000 >> (y1 & 15)
              tax
              ldy     vl_bit,x
              ldx     #0
              lda     zp:_Zp+15
              and     #8
              bne     8$
              sty     zp:_Zp+8        ; rows 0-7 of the 16: the high byte
              stx     zp:_Zp+7
              jmp     10$
8$:           sty     zp:_Zp+7        ; rows 8-15: the low one
              stx     zp:_Zp+8
              jmp     10$
90$:          rts

10$:          lda     #0              ; the top row's byte: the screen
              sta     zp:_Zp+3        ; + y1 * 40 + x / 8
              lda     zp:_Zp+15
              asl     a
              rol     zp:_Zp+3
              asl     a
              rol     zp:_Zp+3
              asl     a
              rol     zp:_Zp+3
              sta     zp:_Zp+2        ; y1 * 8
              ldx     zp:_Zp+3
              asl     a
              rol     zp:_Zp+3
              asl     a
              rol     zp:_Zp+3        ; y1 * 32
              clc
              adc     zp:_Zp+2
              sta     zp:_Zp+2
              txa
              adc     zp:_Zp+3
              sta     zp:_Zp+3
              lda     zp:_Zp+14       ; x / 8
              lsr     a
              lda     zp:_Zp+13
              ror     a
              lsr     a
              lsr     a
              clc
              adc     zp:_Zp+2
              sta     zp:_Zp+2
              bcc     11$
              inc     zp:_Zp+3
11$:          lda     zp:_Zp+2
              clc
              adc     #.byte0 FR_SCREEN
              sta     zp:_Zp+2
              lda     zp:_Zp+3
              adc     #.byte1 FR_SCREEN
              sta     zp:_Zp+3
              lda     zp:_Zp+13       ; m, the column's bit
              and     #7
              tax
              lda     vl_bit,x
              sta     zp:_Zp+13       ; m (x is done with)
              eor     #0xff
              sta     zp:_Zp+14       ; ~m
              ldx     #0              ; onb: $FF for a pen
              lda     zp:_Zp+23
              beq     12$
              dex
12$:          stx     zp:_Zp+15       ; onb (y1 is done with)
              lda     zp:_Zp+22       ; the op: x1 y1 x0 y0 by mode
              bne     20$             ; (a mode >= 256: the default)
              lda     zp:_Zp+21
              cmp     #1
              beq     21$
              cmp     #2
              beq     22$
              cmp     #3
              beq     23$
              cmp     #4
              beq     24$
20$:          lda     #0              ; none of the four: replace, both
              ldx     zp:_Zp+15       ; pens the pen
              ldy     #0
              jmp     30$             ; A x1, X y1, Y x0, (_Zp16) y0
21$:          lda     zp:_Zp+15       ; replace: 0 onb 0 ~onb
              eor     #0xff
              sta     zp:_Zp+16
              lda     #0
              ldx     zp:_Zp+15
              ldy     #0
              jmp     31$
22$:          lda     #0              ; transparent: 0 onb $FF 0
              sta     zp:_Zp+16
              ldx     zp:_Zp+15
              ldy     #0xff
              jmp     31$
23$:          lda     #0              ; XOR: $FF $FF $FF 0
              sta     zp:_Zp+16
              lda     #0xff
              tax
              tay
              jmp     31$
24$:          lda     zp:_Zp+15       ; erase: $FF 0 0 onb
              sta     zp:_Zp+16
              lda     #0xff
              ldx     #0
              ldy     #0
              jmp     31$
30$:          pha
              lda     zp:_Zp+15
              sta     zp:_Zp+16
              pla
31$:          ora     zp:_Zp+14       ; AND for a set bit: x1 | ~m
              sta     zp:_Zp+9
              txa                     ; XOR for a set bit: y1 & m
              and     zp:_Zp+13
              sta     zp:_Zp+10
              tya                     ; AND for a clear bit: x0 | ~m
              ora     zp:_Zp+14
              sta     zp:_Zp+11
              lda     zp:_Zp+16       ; XOR for a clear bit: y0 & m
              and     zp:_Zp+13
              sta     zp:_Zp+12
              jmp     an_vl6_rows

vl_bit:       .byte   0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01

;;; ---- an_pack6_s -------------------------------------------------------
;;;   void an_pack6_s(void)       arguments in zero page, antic.c's an_pack6
;;;
;;; One row of a run of 6x6 glyphs into ap_buf: ap_lead (0-7) zero bits,
;;; then bits 7..2 of each glyph's byte -- ap_sr plus the low byte of
;;; ap_chars[i], i < ap_n -- MSB first, a last partial byte left-aligned
;;; with zeros.  The byte being built is A with a SENTINEL bit below the
;;; ones shifted in: when the sentinel comes out into the carry, A holds
;;; eight and goes into the buffer, and a new sentinel starts the next.
;;; A glyph row of nothing -- a space, the most of a menu's padding --
;;; shifts zeros in without the glyph's own shifts.  ap_n is at most 53
;;; (a string stops at the screen's 320 pixels), so the chars' byte index
;;; stays under 256.  A face in a PORTB bank goes to the C
;;; (src/sys6502/anpack6502.c, an_pack6_c): no font the system has is
;;; one, and its bytes cannot be read with this bank mapped.
;;;
;;; In cc6502's C it was ~460 cycles a glyph, a third of a menu's drawing;
;;; here ~90, ~50 a space.
;;;   _Zp+0  the glyph's bits     _Zp+1  chars' byte index
;;;   _Zp+2  glyphs left          Y      the output index
;;; ---------------------------------------------------------------------------
an_pack6_s:   lda     zp:ap_sr+2
              ora     zp:ap_sr+3
              beq     1$
              jmp     an_pack6_c
1$:           lda     zp:ap_n
              sta     zp:_Zp+2
              lda     #0
              sta     zp:_Zp+1
              tay
              lda     #1              ; the sentinel, then the lead's zeros
              ldx     zp:ap_lead
              beq     3$
2$:           asl     a
              dex
              bne     2$
3$:           ldx     zp:_Zp+2
              bne     39$
              jmp     8$              ; no glyphs: the lead alone
39$:          tax                     ; X: the byte being built
4$:           sty     zp:_Zp+3        ; the next char, its low byte
              ldy     zp:_Zp+1
              lda     (ap_chars),y
              iny
              iny
              sty     zp:_Zp+1
              tay
              lda     (ap_sr),y       ; the glyph's row
              ldy     zp:_Zp+3
              cmp     #0
              beq     6$
              sta     zp:_Zp+0
              txa
              asl     zp:_Zp+0
              rol     a
              bcc     20$
              sta     (ap_buf),y
              iny
              lda     #1
20$:          asl     zp:_Zp+0
              rol     a
              bcc     21$
              sta     (ap_buf),y
              iny
              lda     #1
21$:          asl     zp:_Zp+0
              rol     a
              bcc     22$
              sta     (ap_buf),y
              iny
              lda     #1
22$:          asl     zp:_Zp+0
              rol     a
              bcc     23$
              sta     (ap_buf),y
              iny
              lda     #1
23$:          asl     zp:_Zp+0
              rol     a
              bcc     24$
              sta     (ap_buf),y
              iny
              lda     #1
24$:          asl     zp:_Zp+0
              rol     a
              bcc     25$
              sta     (ap_buf),y
              iny
              lda     #1
25$:          jmp     7$
6$:           txa                     ; nothing in it: six zeros
              asl     a
              bcc     30$
              sta     (ap_buf),y
              iny
              lda     #1
30$:          asl     a
              bcc     31$
              sta     (ap_buf),y
              iny
              lda     #1
31$:          asl     a
              bcc     32$
              sta     (ap_buf),y
              iny
              lda     #1
32$:          asl     a
              bcc     33$
              sta     (ap_buf),y
              iny
              lda     #1
33$:          asl     a
              bcc     34$
              sta     (ap_buf),y
              iny
              lda     #1
34$:          asl     a
              bcc     35$
              sta     (ap_buf),y
              iny
              lda     #1
35$:
7$:           tax
              dec     zp:_Zp+2
              beq     71$
              jmp     4$
71$:          txa
8$:           cmp     #1              ; the sentinel alone: nothing left
              beq     9$
10$:          asl     a               ; left-aligned: until the sentinel
              bcc     10$             ; is out
              sta     (ap_buf),y
9$:           rts

;;; ---- an_text6 ---------------------------------------------------------
;;;   void an_text6(uint8_t rows)
;;;
;;; A string's rows, all of them: each packed (an_pack6_s) and put
;;; (an_put_row_s), then the face a row on (+256) and the screen a line
;;; (+40).  antic_text sets the arguments once; in C the loop around the
;;; two was ~1,900 cycles a row.  The count rides the 6502's stack: the
;;; packer may call C, which owns _Zp0-23.  rows in A, 1 or more.
;;; ---------------------------------------------------------------------------
an_text6:     pha
              jsr     an_pack6_s
              jsr     an_put_row_s
              inc     zp:ap_sr+1
              bne     1$
              inc     zp:ap_sr+2
              bne     1$
              inc     zp:ap_sr+3
1$:           lda     zp:pr_scr
              clc
              adc     #40
              sta     zp:pr_scr
              bcc     2$
              inc     zp:pr_scr+1
2$:           pla
              sec
              sbc     #1
              bne     an_text6
              rts

;;; ---- an_put_row_s -----------------------------------------------------
;;;   void an_put_row_s(void)     arguments in zero page, antic_text's
;;;
;;; pr_last + 1 bytes of pr_buf onto the screen at pr_scr, through the op
;;; (AN_PUT's formula):
;;;     t1 = (d & x1) ^ y1,  t0 = (d & x0) ^ y0
;;;     d' = (s & t1) | (~s & t0)  =  t0 ^ ((t0 ^ t1) & s)
;;; kept inside the mask: pr_lm on the first byte, pr_rm on the last, both
;;; on one that is both.  The bytes between: with x1 and x0 both zero (a
;;; replace) d' is (s & (y0 ^ y1)) ^ y0, the screen not read.  pr_last is
;;; at most 40.  In C ~150 cycles a byte; here ~22 between for a replace,
;;; ~48 for a mode that reads, ~70 an edge.
;;;   _Zp+0  the mask  _Zp+1  d  _Zp+2  t1  _Zp+3  t0  _Zp+4  y0 ^ y1
;;;   _Zp+5-6  x0 ^ x1, y0 ^ y1
;;; ---------------------------------------------------------------------------
an_put_row_s: ldy     #0
              lda     zp:pr_last
              bne     1$
              lda     zp:pr_lm        ; one byte, both edges
              and     zp:pr_rm
              jmp     pr_one
1$:           lda     zp:pr_lm
              jsr     pr_one
              iny
              cpy     zp:pr_last
              beq     9$
              lda     zp:pr_x1
              ora     zp:pr_x0
              bne     5$
              lda     zp:pr_y0        ; no read
              eor     zp:pr_y1
              sta     zp:_Zp+4
2$:           lda     (pr_buf),y
              and     zp:_Zp+4
              eor     zp:pr_y0
              sta     (pr_scr),y
              iny
              cpy     zp:pr_last
              bne     2$
              beq     9$
5$:           lda     zp:pr_x0        ; read: x0 ^ x1 and y0 ^ y1, and
              eor     zp:pr_x1        ; d' = (d & x0) ^ y0
              sta     zp:_Zp+5        ;      ^ (((d & X) ^ Y) & s)
              lda     zp:pr_y0
              eor     zp:pr_y1
              sta     zp:_Zp+6
6$:           lda     (pr_scr),y
              sta     zp:_Zp+1
              and     zp:_Zp+5
              eor     zp:_Zp+6
              and     (pr_buf),y
              sta     zp:_Zp+2
              lda     zp:_Zp+1
              and     zp:pr_x0
              eor     zp:pr_y0
              eor     zp:_Zp+2
              sta     (pr_scr),y
              iny
              cpy     zp:pr_last
              bne     6$
9$:           lda     zp:pr_rm
;;; one byte, Y its offset, A the mask
pr_one:       sta     zp:_Zp+0
              lda     (pr_scr),y
              sta     zp:_Zp+1
              and     zp:pr_x1
              eor     zp:pr_y1
              sta     zp:_Zp+2
              lda     zp:_Zp+1
              and     zp:pr_x0
              eor     zp:pr_y0
              sta     zp:_Zp+3
              eor     zp:_Zp+2
              and     (pr_buf),y
              eor     zp:_Zp+3        ; d'
              eor     zp:_Zp+1
              and     zp:_Zp+0
              eor     zp:_Zp+1        ; inside the mask
              sta     (pr_scr),y
              rts

;;; ---- an_shl6a: an_shl6's twin in this bank, for antic_raster_row ------
an_shl6a:     sta     zp:_Zp+3        ; n
1$:           ldy     zp:_Zp+3
              lda     (_Zp),y
              asl     a
              sta     (_Zp),y
              dey
2$:           lda     (_Zp),y
              rol     a
              sta     (_Zp),y
              dey
              bpl     2$
              dec     zp:_Zp+2
              bne     1$
              rts

;;; ---- an_shl6 ----------------------------------------------------------
;;;   void an_shl6(uint8_t *row, uint8_t n, uint8_t off)
;;;
;;; row[i] = row[i] << off | row[i + 1] >> (8 - off), i < n, off 1-7: a
;;; form's row moved left into the destination's bit positions
;;; (src/vdi/dev_antic.c, copy_rows); row[n] is read, and shifted too, as
;;; scratch.  The whole row one bit at a time, off times, from the end:
;;; ~7 cycles a byte a bit, where cc6502's C was ~60 a byte.  In DEV'S
;;; bank, beside copy_rows, not the antic bank: no veneer.
;;;
;;; row in _Zp0-1, n in A, off in _Zp2.
;;; ---------------------------------------------------------------------------
;;; a nibble read backwards: antic.c's and_style_line reverses a line
;;; style with it (speed 7).  Here because a constant table in the bank's
;;; data section would share it with the variables there.
an_rev4:      .byte   0x0, 0x8, 0x4, 0xc, 0x2, 0xa, 0x6, 0xe
              .byte   0x1, 0x9, 0x5, 0xd, 0x3, 0xb, 0x7, 0xf

              .section dev,text
an_shl6:      sta     zp:_Zp+3        ; n
1$:           ldy     zp:_Zp+3        ; row[n] first: its top bit into C
              lda     (_Zp),y
              asl     a
              sta     (_Zp),y
              dey
2$:           lda     (_Zp),y
              rol     a
              sta     (_Zp),y
              dey
              bpl     2$
              dec     zp:_Zp+2
              bne     1$
              rts
