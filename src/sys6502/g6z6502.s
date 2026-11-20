;;; ---------------------------------------------------------------------------
;;; g6z6502.s -- g6z_unpack: one G4Z chunk, on a 6502 (docs/6502.md, "Disk").
;;;
;;; The format is tools/mkxex.py's (its docstring, and decode() there is
;;; this in Python): bits interleaved with bytes, read from the top of a
;;; bit byte taken when a bit is wanted and none is left; numbers in
;;; interlaced Elias gamma;
;;;
;;;     literals        gamma(n), n bytes
;;;     new offset      gamma(hi), a byte lo, gamma(len - 1)
;;;     repeat          gamma(len), at the last offset
;;;
;;; chosen by a bit: at the start and after a match 0 is literals and 1 a
;;; new offset; after literals 0 is a repeat and 1 a new offset.  A chunk
;;; ends when its count of bytes out is written; the last offset is carried
;;; from one chunk to the next.
;;;
;;;   in:   _Zp0-1 the packed bytes, _Zp2-3 where they go, _Zp4-5 how
;;;         many come out (any, 0 too), _Zp6-7 the last offset
;;;   out:  A = 0, or 1 if the stream asked to write past the count (it
;;;         stops there, having written nothing past it); _Zp0-1 past
;;;         the chunk, _Zp2-3 past what it wrote, _Zp6-7 the last offset
;;;   uses: X, Y, _Zp8-14
;;;
;;; The source and the destination are near: what is mapped is the
;;; caller's business, and a match reads only what this chunk's output or
;;; an earlier one put at lower addresses of the same space.
;;;
;;; b6_unz, below, is the system file's use of it at load time.
;;;
;;; tests/host/test_g6z6502.py runs it on tests/host/m6502.py against
;;; tools/mkxex.py's packer and decoder, and counts its cycles.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, b6_stop
              .public g6z_unpack, b6_unz, B6_STAGE

ZS:           .equ    _Zp+0           ; the packed stream
ZD:           .equ    _Zp+2           ; the output
ZC:           .equ    _Zp+4           ; bytes still to come out
LAST:         .equ    _Zp+6           ; the last offset
BITS:         .equ    _Zp+8           ; the bit byte, a 1 below its bits
N:            .equ    _Zp+9           ; a number read, a length
MS:           .equ    _Zp+11          ; a match's source
ZUSED:        .equ    15              ; _Zp0-14

              .section code
g6z_unpack:   ldy     #0              ; Y is 0 between the copies
              lda     #0x80           ; no bits: the first one takes a byte
              sta     zp:BITS
              lda     zp:ZC
              ora     zp:ZC+1
              bne     after_m
done:         lda     #0
              rts
over:         lda     #1              ; asked for more than the count
              rts

;;; after a match, or at the start: 0 literals, 1 a new offset
after_m:      asl     zp:BITS
              bne     1$
              jsr     refill
1$:           bcs     newoff
              jsr     gamma           ; literals
              sec                     ; the count down by them
              lda     zp:ZC
              sbc     zp:N
              tax
              lda     zp:ZC+1
              sbc     zp:N+1
              bcc     over
              sta     zp:ZC+1
              stx     zp:ZC
              ldx     zp:N+1          ; whole pages first
              beq     12$
11$:          lda     (ZS),y
              sta     (ZD),y
              iny
              bne     11$
              inc     zp:ZS+1
              inc     zp:ZD+1
              dex
              bne     11$
12$:          ldx     zp:N
              beq     15$
13$:          lda     (ZS),y
              sta     (ZD),y
              iny
              dex
              bne     13$
              tya                     ; both moved on by Y
              clc
              adc     zp:ZS
              sta     zp:ZS
              bcc     14$
              inc     zp:ZS+1
              clc
14$:          tya
              adc     zp:ZD
              sta     zp:ZD
              bcc     16$
              inc     zp:ZD+1
16$:          ldy     #0
15$:          lda     zp:ZC
              ora     zp:ZC+1
              beq     done
;;; after literals: 0 a repeat, 1 a new offset
              asl     zp:BITS
              bne     2$
              jsr     refill
2$:           bcs     newoff
              jsr     gamma           ; a repeat's length
              jmp     match
newoff:       jsr     gamma           ; hi, 1-256
              lda     (ZS),y          ; lo
              inc     zp:ZS
              bne     3$
              inc     zp:ZS+1
3$:           clc                     ; offset = (hi - 1) << 8 | lo, + 1
              adc     #1
              sta     zp:LAST
              lda     zp:N
              adc     #0xff           ; hi - 1, + the carry
              sta     zp:LAST+1
              jsr     gamma           ; the length - 1
              inc     zp:N
              bne     match
              inc     zp:N+1
match:        sec                     ; the count down by the length
              lda     zp:ZC
              sbc     zp:N
              tax
              lda     zp:ZC+1
              sbc     zp:N+1
              bcc     over2
              sta     zp:ZC+1
              stx     zp:ZC
              sec                     ; where it comes from
              lda     zp:ZD
              sbc     zp:LAST
              sta     zp:MS
              lda     zp:ZD+1
              sbc     zp:LAST+1
              sta     zp:MS+1
              ldx     zp:N+1          ; forward: an offset shorter than
              beq     22$             ; the length is a run
21$:          lda     (MS),y
              sta     (ZD),y
              iny
              bne     21$
              inc     zp:MS+1
              inc     zp:ZD+1
              dex
              bne     21$
22$:          ldx     zp:N
              beq     25$
23$:          lda     (MS),y
              sta     (ZD),y
              iny
              dex
              bne     23$
              tya
              clc
              adc     zp:ZD
              sta     zp:ZD
              bcc     24$
              inc     zp:ZD+1
24$:          ldy     #0
25$:          lda     zp:ZC
              ora     zp:ZC+1
              beq     done2
              jmp     after_m
done2:        lda     #0              ; (the ends again, in reach)
              rts
over2:        lda     #1
              rts

;;; the bit byte was empty: the next, its top bit in C
refill:       lda     (ZS),y
              inc     zp:ZS
              bne     1$
              inc     zp:ZS+1
1$:           sec
              rol     a
              sta     zp:BITS
              rts

;;; N = an interlaced Elias gamma: for each bit below the top one a 0 and
;;; the bit, then a 1.  Most are 1: a single 1, out at once
gamma:        lda     #0
              sta     zp:N+1
              lda     #1
              sta     zp:N
              asl     zp:BITS
              bne     1$
              jsr     refill
1$:           bcc     3$
              rts
2$:           asl     zp:BITS
              bne     4$
              jsr     refill
4$:           bcs     9$
3$:           asl     zp:BITS
              bne     5$
              jsr     refill
5$:           rol     zp:N
              rol     zp:N+1
              bcc     2$              ; (always: a number fits sixteen bits)
9$:           rts
;;; ---------------------------------------------------------------------------
;;; b6_unz -- INITAD, after a segment at B6_STAGE: one packed chunk of a
;;; bank, unpacked into the window (tools/bsp6502/mkxex6502.py --pack).
;;; The segment is
;;;
;;;     B6_STAGE   where the bytes go, a word ($4000-$7FFF)
;;;     +2         how many come out, a word
;;;     +4         the packed bytes
;;;
;;; B6_STAGE is ANTIC's screen-to-be, $8000-$9EFF, which nothing in the
;;; file loads into and nothing uses until the system runs.  The DOS's
;;; loader called this: its _Zp bytes go back as they were.  The last
;;; offset goes from one chunk to the next in b6_last.
;;;
;;; NOT IN b6init, though it runs only at load: that section's bounds are
;;; the pool's after main (src/sys6502/abistub6502.c), and a second object's
;;; part of it went elsewhere in Low -- the pool then ran over the code
;;; between, and test-d6's Show hung.  tools/bsp6502/bankcheck.py refuses a
;;; b6init in more than one piece.  A stream that
;;; asks to write past its count stops the load.
;;; ---------------------------------------------------------------------------
B6_STAGE:     .equ    0x8000

              .section code, root     ; called by INITAD only: kept
b6_last:      .word   0               ; (resident code's own: RAM there)
b6_unz:       ldx     #ZUSED - 1
1$:           lda     zp:_Zp,x
              pha
              dex
              bpl     1$
              lda     #.byte0 (B6_STAGE + 4)
              sta     zp:ZS
              lda     #.byte1 (B6_STAGE + 4)
              sta     zp:ZS+1
              ldx     #3
2$:           lda     B6_STAGE,x
              sta     zp:ZD,x
              dex
              bpl     2$
              lda     b6_last
              sta     zp:LAST
              lda     b6_last+1
              sta     zp:LAST+1
              jsr     g6z_unpack
              tay
              lda     zp:LAST
              sta     b6_last
              lda     zp:LAST+1
              sta     b6_last+1
              ldx     #0
3$:           pla
              sta     zp:_Zp,x
              inx
              cpx     #ZUSED
              bne     3$
              tya
              bne     4$
              rts
4$:           lda     #.byte0 badmsg
              ldx     #.byte1 badmsg
              ldy     #badmsg_len
              jmp     b6_stop

              .section cdata, rodata
badmsg:       .byte   "SYSTEM FILE DAMAGED", 0x9b
badmsg_len:   .equ    . - badmsg
