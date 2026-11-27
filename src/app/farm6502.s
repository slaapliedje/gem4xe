;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; farm6502.s -- far memory for a 6502 program of several banks
;;; (docs/6502.md, step 5c-2; in assembly since speed 4): gem.h's fa_*.
;;;
;;; A far address is the system's (src/sys6502/farmem6502.c): bank 0 is
;;; near memory, read and written as it is; far bank k >= 1 is four PORTB
;;; banks, piece p of it at bank index b6_far_base + (k-1)*4 + p, seen at
;;; $4000 + (offset & $3FFF).  These map that piece into the window
;;; themselves -- PORTB from the system's b6_portb, whose address the link
;;; block gives (src/app/crt6502m.s) -- copy, and map back the program's
;;; own bank, the one b6_cur names: no call into the system.
;;;
;;; SO THEY MUST NOT BE IN A BANK: section `code`, which the program's
;;; link file puts in its shared RAM under the ROM (src/app/
;;; gemappm6502.scm), outside the window it maps; a near buffer handed to
;;; them must be outside it too -- a program's data and stack are.  The
;;; ROM is out throughout (b6_portb's values have bit 0 clear), and an
;;; interrupt puts PORTB back as it found it.  On an Axlon the two
;;; switches, fa_sw1 and fa_sw2, are made calls to the system's ax_sw at
;;; the start (src/app/crt6502m.s): the bank index is the register's value.
;;;
;;; In C every field went through fa_get: a frame, the 32-bit arithmetic,
;;; a memcpy -- ~800 cycles for two bytes, and the desktop reads its window
;;; lists a field at a time.  Here a field in one piece is mapped and read
;;; in place, ~90 cycles.
;;;
;;; Calypsi's convention: arguments in A and _Zp0-7, first fit, left to
;;; right; results in A, _Zp0-1 or _Zp0-3; X, Y and _Zp0-23 are the
;;; callee's to destroy.  The working state is in _Zp8-23:
;;;
;;;   _Zp8-11   FA, the far address being worked on
;;;   _Zp12-13  FW, where it shows: the window, or itself when near
;;;   _Zp14-15  NP, the near pointer
;;;   _Zp16-17  the count left
;;;   _Zp18-19  this piece's count
;;;   _Zp20-21  a pointer into the link block's tables; _Zp22 scratch
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, g6_l_tab, g6_l_cur, g6_l_fbase
              .public fa_get, fa_put, fa_rd8, fa_rd16, fa_rd32
              .public fa_wr8, fa_wr16, fa_wr32
              .public fa_sw1, fa_sw2          ; switches: crt6502m.s's axpatch

PORTB:        .equ    0xd301

              .section code
;;; fmap -- the far address at _Zp+X.. (its bank byte not 0) mapped, its
;;; window address in FW.  Keeps X; destroys A, Y.
fmap:         lda     g6_l_tab
              sta     zp:_Zp+20
              lda     g6_l_tab+1
              sta     zp:_Zp+21
              lda     zp:_Zp+2,x      ; (k - 1) * 4
              sec
              sbc     #1
              asl     a
              asl     a
              sta     zp:_Zp+22
              lda     zp:_Zp+1,x      ; + offset >> 14
              asl     a
              rol     a
              rol     a
              and     #3
              clc
              adc     zp:_Zp+22
              clc
              adc     g6_l_fbase
              tay
fa_sw1:       lda     (_Zp+20),y      ; (an Axlon: TYA, JSR ax_sw, NOP)
              sta     PORTB
              lda     zp:_Zp+0,x
              sta     zp:_Zp+12
              lda     zp:_Zp+1,x
              and     #0x3f
              ora     #0x40
              sta     zp:_Zp+13
              rts

;;; unmap -- the program's own bank back in the window.  Keeps A and X.
unmap:        pha
              lda     g6_l_cur
              sta     zp:_Zp+20
              lda     g6_l_cur+1
              sta     zp:_Zp+21
              ldy     #0
              lda     (_Zp+20),y      ; b6_cur
              tay
              lda     g6_l_tab
              sta     zp:_Zp+20
              lda     g6_l_tab+1
              sta     zp:_Zp+21
fa_sw2:       lda     (_Zp+20),y
              sta     PORTB
              pla
              rts

;;; inpiece -- Z clear when a field of Y + 1 bytes at the far address in
;;; _Zp0-3 stays in its piece (offset & $3FFF <= $3FFF - Y); Z set when it
;;; crosses into the next.
inpiece:      lda     zp:_Zp+1
              ora     #0xc0
              cmp     #0xff
              bne     10$             ; not the piece's last page: inside
              sty     zp:_Zp+22
              lda     #0xff
              sec
              sbc     zp:_Zp+22       ; $FF - Y: the last start inside
              cmp     zp:_Zp+0
              bcs     10$
              lda     #0              ; Z: it crosses
              rts
10$:          lda     #1
              rts

;;; ---- one value ---------------------------------------------------------
;;; fa_rd8(a _Zp0-3) -> A
fa_rd8:       lda     zp:_Zp+2
              bne     10$
              ldy     #0
              lda     (_Zp),y
              rts
10$:          ldx     #0
              jsr     fmap
              ldy     #0
              lda     (_Zp+12),y
              jmp     unmap

;;; fa_wr8(a _Zp0-3, v A)
fa_wr8:       ldx     zp:_Zp+2
              bne     10$
              ldy     #0
              sta     (_Zp),y
              rts
10$:          sta     zp:_Zp+4
              ldx     #0
              jsr     fmap
              lda     zp:_Zp+4
              ldy     #0
              sta     (_Zp+12),y
              jmp     unmap

;;; fa_rd16(a _Zp0-3) -> _Zp0-1; fa_rd32 -> _Zp0-3.  Y + 1 bytes from
;;; FW (set up by fieldin) into _Zp0..
fa_rd16:      ldy     #1
              jmp     rdfield
fa_rd32:      ldy     #3
rdfield:      sty     zp:_Zp+23
              jsr     fieldin
              bcs     30$             ; across two pieces: a byte at a time
              ldx     zp:_Zp+2        ; near or far, before the result
              ldy     zp:_Zp+23       ; lands on it
10$:          lda     (_Zp+12),y
              sta     _Zp,y
              dey
              bpl     10$
              txa
              beq     20$
              jmp     unmap
20$:          rts
30$:          lda     #.byte0 (_Zp+4) ; into _Zp4.., then down
              sta     zp:_Zp+14
              lda     #.byte1 (_Zp+4)
              sta     zp:_Zp+15
              jsr     getcore
              ldy     zp:_Zp+23
31$:          lda     _Zp+4,y
              sta     _Zp,y
              dey
              bpl     31$
              rts

;;; fa_wr16(a _Zp0-3, v _Zp4-5); fa_wr32(a _Zp0-3, v _Zp4-7)
fa_wr16:      ldy     #1
              jmp     wrfield
fa_wr32:      ldy     #3
wrfield:      sty     zp:_Zp+23
              jsr     fieldin
              bcs     30$
              ldy     zp:_Zp+23
10$:          lda     _Zp+4,y
              sta     (_Zp+12),y
              dey
              bpl     10$
              lda     zp:_Zp+2
              beq     20$
              jmp     unmap
20$:          rts
30$:          lda     #.byte0 (_Zp+4)
              sta     zp:_Zp+14
              lda     #.byte1 (_Zp+4)
              sta     zp:_Zp+15
              jmp     putcore

;;; fieldin -- a field of _Zp23 + 1 bytes at _Zp0-3: near, FW is the
;;; address and C clear; far and inside one piece, mapped, FW its window
;;; address and C clear; across two pieces, C set and FA and the count
;;; ready for getcore/putcore (NP is the caller's to set).
fieldin:      lda     zp:_Zp+2
              bne     10$
              lda     zp:_Zp+0
              sta     zp:_Zp+12
              lda     zp:_Zp+1
              sta     zp:_Zp+13
              clc
              rts
10$:          ldy     zp:_Zp+23
              jsr     inpiece
              beq     20$
              ldx     #0
              jsr     fmap
              clc
              rts
20$:          jsr     fa_from0
              ldy     zp:_Zp+23
              iny
              sty     zp:_Zp+16
              lda     #0
              sta     zp:_Zp+17
              sec
              rts

fa_from0:     ldy     #3
10$:          lda     _Zp,y
              sta     _Zp+8,y
              dey
              bpl     10$
              rts

;;; ---- blocks ------------------------------------------------------------
;;; fa_get(dst _Zp0-1, src _Zp4-7, n _Zp2-3)
fa_get:       ldy     #3
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

;;; fa_put(dst _Zp0-3, src _Zp4-5, n _Zp6-7)
fa_put:       jsr     fa_from0
              lda     zp:_Zp+4
              sta     zp:_Zp+14
              lda     zp:_Zp+5
              sta     zp:_Zp+15
              lda     zp:_Zp+6
              sta     zp:_Zp+16
              lda     zp:_Zp+7
              sta     zp:_Zp+17
              jmp     putcore

;;; piece -- FA mapped (or taken as near) and this piece's count: the count
;;; left, or what remains of the 16 KB piece if that is less.  Near, all of
;;; it: near memory is one piece.
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

;;; getcore -- the count from FA to near NP.  putcore the other way.  Each
;;; piece whole pages, then the rest; the program's bank back at the end.
getcore:      lda     zp:_Zp+16
              ora     zp:_Zp+17
              beq     90$
              jsr     piece
              ldy     #0
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
