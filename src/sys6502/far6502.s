;;; ---------------------------------------------------------------------------
;;; far6502.s -- the far_* helpers' hot half, in assembly (docs/6502.md,
;;; "Speed").  src/sys6502/farmem6502.c has the rest and the reasoning:
;;; a far address is bank << 16 | offset; bank 0 is near memory, read and
;;; written directly; far bank k >= 1 is four PORTB banks after the
;;; code's, offset >> 14 picks one, and it shows at $4000 + (offset & $3FFF).
;;;
;;; In C these were a quarter of the 6502 desktop's busy time: every
;;; field of every object went through 32-bit arithmetic, a stack frame and
;;; a memcpy of two bytes, and a string through far_read8 a byte at a time,
;;; mapping and unmapping for each.  Here a field is mapped once and read
;;; in place, a string is walked with a pointer that is remapped only where
;;; it crosses into the next 16 KB piece, and a block goes a page at a time.
;;;
;;; Calypsi's convention (doc/html/assembly-interface): arguments in A and
;;; _Zp0-7, first fit, left to right; results in A, _Zp0-1 or _Zp0-3; X, Y
;;; and _Zp0-23 are the callee's to destroy, _Zp24-47 are kept.  So all the
;;; working state is in _Zp8-23:
;;;
;;;   _Zp8-11   FA, the far address being worked on
;;;   _Zp12-13  FW, where it shows: the window, or itself when near
;;;   _Zp14-15  NP, the near pointer
;;;   _Zp16-17  the count left
;;;   _Zp18-19  this piece's count
;;;   _Zp20-21  scratch; _Zp22-23 ob_wr16's value
;;;
;;; ALL OF IT IS RESIDENT, and every entry puts the caller's bank back in
;;; the window before it returns (unmap): the caller may be banked code
;;; that the window must hold again.  A near buffer is never in the window.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, b6_cur, b6_count, b6_portb, b6_far_base, b6_far_bad
              .public far_read8, far_write8, far_rd16, far_rd32, far_wr16, far_wr32
              .public b6sw_fmap, b6sw_unmap            ; bank switches: bank6502.s's patch
              .public far_get, far_put, far_fill, far_strget, far_put_edge
              .public ob_rd16, ob_rd32, ob_wr16
              .public fmap, unmap             ; for g6z6502.s's g6z_far

PORTB:        .equ    0xd301

              .section zdata, bss
fbuf:         .space  4               ; a field that straddles two pieces
fm_k:         .space  1               ; fmap's last piece: its far bank,
fm_p:         .space  1               ; its offset's top two bits
fm_y:         .space  1               ; and its b6_portb index

              .section code
;;; fmap -- the far address at _Zp+X.. (bank >= 1) mapped, its window
;;; address in FW.  Keeps X; destroys A, Y.  An address in no bank there
;;; is goes to b6_far_bad, which stops (farmem6502.c).
;;;
;;; The last piece mapped is remembered -- its far bank, its offset's top
;;; two bits and its b6_portb index -- so the fields of one tree, which
;;; are nearly always in one piece, skip the arithmetic.  The cache is in
;;; zdata, cleared at start: bank 0 never comes here, so it never matches.
fmap:         lda     zp:_Zp+2,x      ; the far bank, k
              cmp     fm_k
              bne     5$
              lda     zp:_Zp+1,x
              and     #0xc0
              cmp     fm_p
              bne     5$
              ldy     fm_y            ; the piece mapped last time
              jmp     b6sw_fmap
5$:           lda     zp:_Zp+2,x
              cmp     #65
              bcs     fm_bad          ; (k - 1) * 4 would not fit a byte
              sbc     #0              ; carry clear: k - 1
              asl     a
              asl     a
              clc
              adc     b6_far_base     ; B6_CODE_BANKS + 1
              bcs     fm_bad          ; past index 255
              sta     zp:_Zp+20
              lda     zp:_Zp+1,x      ; + offset >> 14
              asl     a
              rol     a
              rol     a
              and     #3
              clc
              adc     zp:_Zp+20
              bcs     fm_bad
              cmp     b6_count
              beq     10$
              bcs     fm_bad          ; past the last bank found
10$:          tay
              sty     fm_y            ; remembered
              lda     zp:_Zp+2,x
              sta     fm_k
              lda     zp:_Zp+1,x
              and     #0xc0
              sta     fm_p
b6sw_fmap:       lda     b6_portb,y
              sta     PORTB
              lda     zp:_Zp+0,x
              sta     zp:_Zp+12
              lda     zp:_Zp+1,x
              and     #0x3f
              ora     #0x40
              sta     zp:_Zp+13
              rts
fm_bad:       lda     zp:_Zp+0,x      ; the address to _Zp0-3, for the stop
              sta     zp:_Zp+0
              lda     zp:_Zp+1,x
              sta     zp:_Zp+1
              lda     zp:_Zp+2,x
              sta     zp:_Zp+2
              lda     zp:_Zp+3,x
              sta     zp:_Zp+3
              jmp     b6_far_bad

;;; unmap -- the caller's bank back in the window.  Keeps A and X.
unmap:        ldy     b6_cur
              pha
b6sw_unmap:      lda     b6_portb,y
              sta     PORTB
              pla
              rts

;;; straddle -- Z set when the far address in _Zp0-3 is within Y bytes of
;;; its piece's end (offset & $3FFF >= $4000 - Y), so a field of Y + 1
;;; bytes from there would cross into the next piece.
straddle:     lda     zp:_Zp+1
              ora     #0xc0
              cmp     #0xff
              bne     10$             ; not the piece's last page
              sty     zp:_Zp+20
              lda     #0
              sec
              sbc     zp:_Zp+20       ; $100 - Y: the first that straddles
              cmp     zp:_Zp+0
              beq     20$
              bcs     10$             ; below it: no
20$:          lda     #0              ; Z: it straddles
              rts
10$:          lda     #1
              rts

;;; ---- one byte --------------------------------------------------------
far_read8:    lda     zp:_Zp+2
              bne     10$
              ldy     #0
              lda     (_Zp),y
              rts
10$:          ldx     #0
              jsr     fmap
              ldy     #0
              lda     (_Zp+12),y
              jmp     unmap

far_write8:   ldx     zp:_Zp+2
              bne     10$
              ldy     #0
              sta     (_Zp),y
              rts
10$:          sta     zp:_Zp+21
              ldx     #0
              jsr     fmap
              lda     zp:_Zp+21
              ldy     #0
              sta     (_Zp+12),y
              jmp     unmap

;;; ---- a field: two or four bytes, one map --------------------------------
far_rd16:     lda     zp:_Zp+2
              bne     10$
              ldy     #1
              lda     (_Zp),y
              tax
              dey
              lda     (_Zp),y
              sta     zp:_Zp+0
              stx     zp:_Zp+1
              rts
10$:          ldy     #1
              jsr     straddle
              beq     20$
              ldx     #0
              jsr     fmap
              ldy     #1
              lda     (_Zp+12),y
              sta     zp:_Zp+1
              dey
              lda     (_Zp+12),y
              sta     zp:_Zp+0
              jmp     unmap
20$:          lda     #2
              jsr     getbuf
              lda     fbuf
              sta     zp:_Zp+0
              lda     fbuf+1
              sta     zp:_Zp+1
              rts

far_rd32:     lda     zp:_Zp+2
              bne     10$
              lda     zp:_Zp+0        ; near: read through a copy of the
              sta     zp:_Zp+12       ; pointer, the result lands on it
              lda     zp:_Zp+1
              sta     zp:_Zp+13
              jmp     30$
10$:          ldy     #3
              jsr     straddle
              beq     20$
              ldx     #0
              jsr     fmap
              jsr     30$
              jmp     unmap
20$:          lda     #4
              jsr     getbuf
              ldy     #3
21$:          lda     fbuf,y
              sta     _Zp,y
              dey
              bpl     21$
              rts
30$:          ldy     #3
31$:          lda     (_Zp+12),y
              sta     _Zp,y
              dey
              bpl     31$
              rts

;;; getbuf -- A bytes (2 or 4) from far _Zp0-3 into fbuf, piece by piece
getbuf:       sta     zp:_Zp+16
              lda     #0
              sta     zp:_Zp+17
              jsr     fa_from0
              lda     #.byte0 fbuf
              sta     zp:_Zp+14
              lda     #.byte1 fbuf
              sta     zp:_Zp+15
              jmp     getcore

;;; putbuf -- A bytes from fbuf to far _Zp0-3
putbuf:       sta     zp:_Zp+16
              lda     #0
              sta     zp:_Zp+17
              jsr     fa_from0
              lda     #.byte0 fbuf
              sta     zp:_Zp+14
              lda     #.byte1 fbuf
              sta     zp:_Zp+15
              jmp     putcore

fa_from0:     ldy     #3
10$:          lda     _Zp,y
              sta     _Zp+8,y
              dey
              bpl     10$
              rts

far_wr16:     lda     zp:_Zp+2        ; value in _Zp4-5
              bne     10$
              ldy     #0
              lda     zp:_Zp+4
              sta     (_Zp),y
              iny
              lda     zp:_Zp+5
              sta     (_Zp),y
              rts
10$:          ldy     #1
              jsr     straddle
              beq     20$
              ldx     #0
              jsr     fmap
              ldy     #0
              lda     zp:_Zp+4
              sta     (_Zp+12),y
              iny
              lda     zp:_Zp+5
              sta     (_Zp+12),y
              jmp     unmap
20$:          lda     zp:_Zp+4
              sta     fbuf
              lda     zp:_Zp+5
              sta     fbuf+1
              lda     #2
              jmp     putbuf

far_wr32:     lda     zp:_Zp+2        ; value in _Zp4-7
              bne     10$
              lda     zp:_Zp+0
              sta     zp:_Zp+12
              lda     zp:_Zp+1
              sta     zp:_Zp+13
              jmp     30$
10$:          ldy     #3
              jsr     straddle
              beq     20$
              ldx     #0
              jsr     fmap
              jsr     30$
              jmp     unmap
20$:          ldy     #3
21$:          lda     _Zp+4,y
              sta     fbuf,y
              dey
              bpl     21$
              lda     #4
              jmp     putbuf
30$:          ldy     #3
31$:          lda     _Zp+4,y
              sta     (_Zp+12),y
              dey
              bpl     31$
              rts

;;; ---- an object's field: tree t, object i, offset (24 bytes an object) --
;;; t in _Zp0-3, i in _Zp4-5, the offset in A; the field's far address
;;; left in _Zp0-3: t + (uint16_t)(i * 24) + offset, as farmem6502.c had.
obaddr:       sta     zp:_Zp+21
              lda     zp:_Zp+5        ; i in 0-255, nearly always: i * 24
              bne     50$             ; + the offset in 16 bits, as i * 3 * 8
              sta     zp:_Zp+19
              lda     zp:_Zp+4
              asl     a               ; 2i (the carry out into 19 leaves
              rol     zp:_Zp+19       ; the carry clear: 19 was 0)
              adc     zp:_Zp+4        ; 3i
              bcc     1$
              inc     zp:_Zp+19
1$:           asl     a               ; 24i, at most 6,120
              rol     zp:_Zp+19
              asl     a
              rol     zp:_Zp+19
              asl     a
              rol     zp:_Zp+19
              clc                     ; + the offset, < 24: no carry out
              adc     zp:_Zp+21
              bcc     2$
              inc     zp:_Zp+19
2$:           clc                     ; t + that, 32 bits
              adc     zp:_Zp+0
              sta     zp:_Zp+0
              lda     zp:_Zp+19
              adc     zp:_Zp+1
              sta     zp:_Zp+1
              bcc     3$
              inc     zp:_Zp+2
              bne     3$
              inc     zp:_Zp+3
3$:           rts
50$:          lda     zp:_Zp+4        ; any other i: i * 8
              asl     a
              sta     zp:_Zp+18
              lda     zp:_Zp+5
              rol     a
              sta     zp:_Zp+19
              asl     zp:_Zp+18
              rol     zp:_Zp+19
              asl     zp:_Zp+18
              rol     zp:_Zp+19
              lda     zp:_Zp+18       ; + i * 16
              asl     a
              tax
              lda     zp:_Zp+19
              rol     a
              tay
              txa
              clc
              adc     zp:_Zp+18
              sta     zp:_Zp+18
              tya
              adc     zp:_Zp+19
              sta     zp:_Zp+19
              clc                     ; t + that, 32 bits
              lda     zp:_Zp+0
              adc     zp:_Zp+18
              sta     zp:_Zp+0
              lda     zp:_Zp+1
              adc     zp:_Zp+19
              sta     zp:_Zp+1
              lda     zp:_Zp+2
              adc     #0
              sta     zp:_Zp+2
              lda     zp:_Zp+3
              adc     #0
              sta     zp:_Zp+3
              clc                     ; + the offset
              lda     zp:_Zp+0
              adc     zp:_Zp+21
              sta     zp:_Zp+0
              bcc     10$
              inc     zp:_Zp+1
              bne     10$
              inc     zp:_Zp+2
              bne     10$
              inc     zp:_Zp+3
10$:          rts

ob_rd16:      jsr     obaddr
              jmp     far_rd16

ob_rd32:      jsr     obaddr
              jmp     far_rd32

ob_wr16:      jsr     obaddr          ; the value in _Zp6-7, returned
              lda     zp:_Zp+6
              sta     zp:_Zp+4
              sta     zp:_Zp+22
              lda     zp:_Zp+7
              sta     zp:_Zp+5
              sta     zp:_Zp+23
              jsr     far_wr16
              lda     zp:_Zp+22
              sta     zp:_Zp+0
              lda     zp:_Zp+23
              sta     zp:_Zp+1
              rts

;;; ---- blocks ------------------------------------------------------------
;;; far_get(dst _Zp0-1, src _Zp4-7, len _Zp2-3)
far_get:      ldy     #3
10$:          lda     _Zp+4,y
              sta     _Zp+8,y
              dey
              bpl     10$
              lda     zp:_Zp+0
              sta     zp:_Zp+14
              lda     zp:_Zp+1
              sta     zp:_Zp+15
              lda     zp:_Zp+2
              sta     zp:_Zp+16
              lda     zp:_Zp+3
              sta     zp:_Zp+17
              jmp     getcore

;;; far_put(dst _Zp0-3, src _Zp4-5, len _Zp6-7)
far_put:      jsr     fa_from0
              lda     zp:_Zp+4
              sta     zp:_Zp+14
              lda     zp:_Zp+5
              sta     zp:_Zp+15
              lda     zp:_Zp+6
              sta     zp:_Zp+16
              lda     zp:_Zp+7
              sta     zp:_Zp+17
              jmp     putcore

;;; far_put_edge(n A, dst _Zp0-3, row _Zp4-5, masks _Zp6-7) -- a form's
;;; row of n bytes (1-48) out to dst, near or far, its first byte merged
;;; under the mask in _Zp6 and its last under _Zp7: what dst holds outside
;;; them stays (src/vdi/dev_antic.c, copy_rows).  The edges are read in
;;; place while the piece is mapped, not with a far_get each.  A row that
;;; crosses a 16 KB piece is not done -- A = 0, and the C does it the long
;;; way -- else A = 1.  The row's two end bytes are left merged.

far_put_edge: sta     zp:_Zp+22       ; n
              jsr     fa_from0
              lda     zp:_Zp+22
              sta     zp:_Zp+16
              lda     #0
              sta     zp:_Zp+17
              jsr     piece
              lda     zp:_Zp+18       ; all of it in this piece?
              cmp     zp:_Zp+22
              beq     10$
              lda     #0
              jmp     unmap
10$:          ldy     #0              ; d ^ ((d ^ s) & m), first then last
              lda     (_Zp+12),y
              eor     (_Zp+4),y
              and     zp:_Zp+6
              eor     (_Zp+12),y
              sta     (_Zp+4),y
              ldy     zp:_Zp+22
              dey
              lda     (_Zp+12),y
              eor     (_Zp+4),y
              and     zp:_Zp+7
              eor     (_Zp+12),y
              sta     (_Zp+4),y
20$:          lda     (_Zp+4),y       ; Y = n - 1 down
              sta     (_Zp+12),y
              dey
              bpl     20$
              lda     #1
              jmp     unmap

;;; piece -- FA mapped (or taken as near) and this piece's count: the count
;;; left, or what remains of the 16 KB piece if that is less.  Near, all
;;; of it: near memory is one piece.
piece:        lda     zp:_Zp+10
              bne     10$
              lda     zp:_Zp+8
              sta     zp:_Zp+12
              lda     zp:_Zp+9
              sta     zp:_Zp+13
              jmp     30$
10$:          ldx     #8
              jsr     fmap
              sec                     ; what the piece has left: $8000 - FW
              lda     #0
              sbc     zp:_Zp+12
              sta     zp:_Zp+18
              lda     #0x80
              sbc     zp:_Zp+13
              sta     zp:_Zp+19
              cmp     zp:_Zp+17       ; less than the count left?
              bcc     40$
              bne     30$
              lda     zp:_Zp+18
              cmp     zp:_Zp+16
              bcc     40$
30$:          lda     zp:_Zp+16       ; no: all of it
              sta     zp:_Zp+18
              lda     zp:_Zp+17
              sta     zp:_Zp+19
40$:          rts

;;; advance -- FA forward and the count left down by this piece's count
advance:      clc
              lda     zp:_Zp+8
              adc     zp:_Zp+18
              sta     zp:_Zp+8
              lda     zp:_Zp+9
              adc     zp:_Zp+19
              sta     zp:_Zp+9
              lda     zp:_Zp+10
              adc     #0
              sta     zp:_Zp+10
              lda     zp:_Zp+11
              adc     #0
              sta     zp:_Zp+11
              sec
              lda     zp:_Zp+16
              sbc     zp:_Zp+18
              sta     zp:_Zp+16
              lda     zp:_Zp+17
              sbc     zp:_Zp+19
              sta     zp:_Zp+17
              rts

;;; getcore -- the count from far FA to near NP.  putcore the other way.
getcore:      lda     zp:_Zp+16
              ora     zp:_Zp+17
              beq     90$
              jsr     piece
              ldy     #0              ; this piece: whole pages, then the rest
              ldx     zp:_Zp+19
              beq     20$
10$:          lda     (_Zp+12),y
              sta     (_Zp+14),y
              iny
              bne     10$
              inc     zp:_Zp+13
              inc     zp:_Zp+15
              dex
              bne     10$
20$:          ldx     zp:_Zp+18
              beq     40$
30$:          lda     (_Zp+12),y
              sta     (_Zp+14),y
              iny
              dex
              bne     30$
              tya                     ; NP past the rest
              clc
              adc     zp:_Zp+14
              sta     zp:_Zp+14
              bcc     40$
              inc     zp:_Zp+15
40$:          jsr     advance
              jmp     getcore
90$:          jmp     unmap

putcore:      lda     zp:_Zp+16
              ora     zp:_Zp+17
              beq     90$
              jsr     piece
              ldy     #0
              ldx     zp:_Zp+19
              beq     20$
10$:          lda     (_Zp+14),y
              sta     (_Zp+12),y
              iny
              bne     10$
              inc     zp:_Zp+13
              inc     zp:_Zp+15
              dex
              bne     10$
20$:          ldx     zp:_Zp+18
              beq     40$
30$:          lda     (_Zp+14),y
              sta     (_Zp+12),y
              iny
              dex
              bne     30$
              tya
              clc
              adc     zp:_Zp+14
              sta     zp:_Zp+14
              bcc     40$
              inc     zp:_Zp+15
40$:          jsr     advance
              jmp     putcore
90$:          jmp     unmap

;;; far_fill(dst _Zp0-3, v A, len _Zp4-5)
far_fill:     sta     zp:_Zp+21
              jsr     fa_from0
              lda     zp:_Zp+4
              sta     zp:_Zp+16
              lda     zp:_Zp+5
              sta     zp:_Zp+17
10$:          lda     zp:_Zp+16
              ora     zp:_Zp+17
              beq     90$
              jsr     piece
              lda     zp:_Zp+21
              ldy     #0
              ldx     zp:_Zp+19
              beq     30$
20$:          sta     (_Zp+12),y
              iny
              bne     20$
              inc     zp:_Zp+13
              dex
              bne     20$
30$:          ldx     zp:_Zp+18
              beq     50$
40$:          sta     (_Zp+12),y
              iny
              dex
              bne     40$
50$:          jsr     advance
              jmp     10$
90$:          jmp     unmap

;;; ---- a string ------------------------------------------------------------
;;; far_strget(dst _Zp0-1, src _Zp4-7, max _Zp2-3): at most max - 1 bytes
;;; and a NUL, which is always written (dst[0] when max is 0 or 1).  FW
;;; walks the piece; at its end FA moves to the next piece's start and is
;;; mapped again.  Near, FW walks all of near memory.
far_strget:   ldy     #3
10$:          lda     _Zp+4,y
              sta     _Zp+8,y
              dey
              bpl     10$
              lda     zp:_Zp+0
              sta     zp:_Zp+14
              lda     zp:_Zp+1
              sta     zp:_Zp+15
              lda     zp:_Zp+2        ; the bytes it may take: max - 1, or 0
              sec
              sbc     #1
              sta     zp:_Zp+16
              lda     zp:_Zp+3
              sbc     #0
              sta     zp:_Zp+17
              bcs     20$
              lda     #0
              sta     zp:_Zp+16
              sta     zp:_Zp+17
20$:          lda     zp:_Zp+10
              bne     30$
              lda     zp:_Zp+8        ; near
              sta     zp:_Zp+12
              lda     zp:_Zp+9
              sta     zp:_Zp+13
              jmp     40$
30$:          ldx     #8
              jsr     fmap
40$:          ldy     #0
50$:          lda     zp:_Zp+16
              ora     zp:_Zp+17
              beq     90$
              lda     (_Zp+12),y
              beq     90$
              sta     (_Zp+14),y
              inc     zp:_Zp+14
              bne     60$
              inc     zp:_Zp+15
60$:          lda     zp:_Zp+16
              bne     61$
              dec     zp:_Zp+17
61$:          dec     zp:_Zp+16
              inc     zp:_Zp+12
              bne     50$
              inc     zp:_Zp+13
              lda     zp:_Zp+10
              beq     50$             ; near: no pieces
              lda     zp:_Zp+13
              cmp     #0x80
              bne     50$
              lda     #0              ; the next piece: (FA & ~$3FFF) + $4000
              sta     zp:_Zp+8
              lda     zp:_Zp+9
              and     #0xc0
              clc
              adc     #0x40
              sta     zp:_Zp+9
              bcc     70$
              inc     zp:_Zp+10
              bne     70$
              inc     zp:_Zp+11
70$:          ldx     #8
              jsr     fmap
              ldy     #0
              jmp     50$
90$:          lda     #0
              sta     (_Zp+14),y
              jmp     unmap
