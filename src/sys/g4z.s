;;; ---------------------------------------------------------------------------
;;; g4z.s -- g4z_unpack: a G4Z stream from anywhere in memory to anywhere.
;;;
;;; WHY.  A program file is squeezed with G4Z (.G4A format 6, tools/mkg4a.py)
;;; so that it reads off a disk in half the sectors, and a 20 MHz 65816
;;; unpacks it in a fraction of the time the drive would have taken
;;; (docs/phase94.md).  GEM.COM's own unpacker (src/farload.s) runs only
;;; while DOS is loading and reads its input out of bank $00; this one stays,
;;; and reads a packed file that may be bigger than a bank from wherever
;;; far_read_file put it.
;;;
;;; THE FORMAT is farload.s's, which tools/mkxex.py describes, packs and
;;; decodes: bits interleaved with bytes, numbers in interlaced Elias gamma,
;;;
;;;     literals        gamma(n), n bytes
;;;     new offset      gamma(hi), a byte lo, gamma(len - 1)
;;;     repeat          gamma(len), at the last offset
;;;
;;; chosen by a bit: at the start and after a match, 0 is literals and 1 a
;;; new offset; after literals, 0 is a repeat and 1 a new offset.  Here it
;;; is one stream, not chunks: tools/mkg4a.py squeezes a whole file at once.
;;; Every number fits sixteen bits -- a match is at most 4,096 bytes, an
;;; offset at most 65,535, and mkg4a refuses a file with a run of literals
;;; that long -- so only the count left to write is 32-bit.
;;;
;;; int16_t g4z_unpack(uint32_t src, uint32_t dst, uint32_t count)
;;;
;;; src in A (low) and X (high), dst in _Dp+0..3, count in _Dp+4..7: the
;;; compiler's call.  Writes exactly `count` bytes from dst on and answers 0,
;;; or 1 if the stream asked to write past them -- then it stopped at the
;;; end, so a damaged file overwrites nothing that is not its own.
;;;
;;; THE FRAME.  The state is on the stack and the direct page is moved onto
;;; it for the call, so the three 24-bit pointers -- [SRC], [SLO], [DLO] --
;;; are direct-page operands, whose bank bytes a carry moves on.  No
;;; interrupt handler addresses through D (src/sys/irq.s).
;;;
;;; NOT MVN, which farload.s copies with at 7 cycles a byte: the vendor's
;;; simulator does not implement it -- it moves nothing -- and this is
;;; tested there.  The loop below is about 20 a byte, which for the biggest
;;; program there is (QED, 330 KB) is under a second at 20 MHz, against
;;; the minute and more its other 165 KB would take to read.
;;;
;;; tests/host/test_g4z.py runs it in the vendor's simulator, across bank
;;; boundaries both ways, against tools/mkxex.py.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"

              .extern _Dp
              .public g4z_unpack

;;; the frame, as direct-page offsets once D points at it
SRC           .equ    1               ; the next packed byte, 24-bit (+ a pad)
DLO           .equ    5               ; where the next byte goes: offset...
DBK           .equ    7               ; ...and bank
SLO           .equ    9               ; where a copy reads: offset...
SBK           .equ    11              ; ...and bank
CNT           .equ    13              ; bytes still to write, 32-bit
LEN           .equ    17              ; bytes this element writes
LAST          .equ    21              ; the last offset
BITS          .equ    23              ; the bit byte, a 1 below its last bit
AFTER         .equ    25              ; 0 at the start and after a match
V             .equ    27              ; a number being read
ERR           .equ    29              ; the stream ran past count
LOCALS        .equ    30

              .section farcode, noreorder
g4z_unpack:   phd
              tay                     ; Y = src, low word
              tsc
              sec
              sbc     ##LOCALS
              tcs                     ; the frame, D not yet moved
              tya
              sta     SRC,s
              txa
              and     ##0xff
              sta     SRC+2,s         ; the bank, and a zero pad
              lda     dp:.tiny _Dp
              sta     DLO,s
              lda     dp:.tiny (_Dp+2)
              and     ##0xff
              sta     DBK,s
              lda     dp:.tiny (_Dp+4)
              sta     CNT,s
              lda     dp:.tiny (_Dp+6)
              sta     CNT+2,s
              tsc
              tcd                     ; D = the frame
              lda     ##0x80          ; no bits: the next one takes a byte
              sta     dp:BITS
              stz     dp:AFTER
              stz     dp:LAST
              stz     dp:ERR
elem:         lda     dp:CNT
              ora     dp:CNT+2
              beq     done
              jsr     .kbank bit
              lda     dp:AFTER
              bne     afterlit
              bcs     new
              jsr     .kbank gamma    ; literals: n, then n bytes
              sta     dp:LEN
              lda     dp:SRC          ; ...which are the packed bytes
              sta     dp:SLO
              lda     dp:SRC+2
              sta     dp:SBK
              jsr     .kbank copy
              lda     dp:SLO          ; the stream goes on after them
              sta     dp:SRC
              lda     dp:SBK
              sta     dp:SRC+2
              lda     ##1
              sta     dp:AFTER
              bra     elem
afterlit:     bcs     new
              jsr     .kbank gamma    ; a repeat of the last offset
              sta     dp:LEN
              bra     match
new:          jsr     .kbank gamma    ; hi, then lo, then the length - 1
              dec     a
              xba                     ; hi - 1 in the high byte...
              sep     #0x20
              lda     [dp:SRC]        ; ...and lo, 8 bits, in the low one
              rep     #0x20
              inc     dp:SRC
              bne     10$
              inc     dp:SRC+2
10$:          inc     a
              sta     dp:LAST
              jsr     .kbank gamma
              inc     a
              sta     dp:LEN
match:        lda     dp:DLO
              sec
              sbc     dp:LAST
              sta     dp:SLO
              lda     dp:DBK
              sbc     ##0
              sta     dp:SBK
              jsr     .kbank copy
              stz     dp:AFTER
              bra     elem
done:         lda     dp:ERR
              tax
              tsc
              clc
              adc     ##LOCALS
              tcs
              pld
              txa
              rtl

;;; bit -- the next bit, in carry.  The bit byte keeps a 1 below its last
;;; bit: when shifting it out leaves nothing, the byte is used up and the
;;; next is taken, with the 1 shifted in below it.
bit:          sep     #0x20
              asl     dp:BITS
              bne     9$
              lda     [dp:SRC]
              rep     #0x20
              inc     dp:SRC
              bne     5$
              inc     dp:SRC+2
5$:           sep     #0x20
              sec
              rol     a
              sta     dp:BITS
9$:           rep     #0x20           ; carry kept
              rts

;;; gamma -- a number, in A: 1, and for as long as a 0 comes, one more bit
;;; below it; a 1 ends it.
gamma:        lda     ##1
              sta     dp:V
10$:          jsr     .kbank bit
              bcs     20$
              jsr     .kbank bit
              rol     dp:V
              bra     10$
20$:          lda     dp:V
              rts

;;; copy -- LEN bytes from SBK:SLO to DBK:DLO, both moved on, and taken off
;;; CNT; no more than CNT, which sets ERR.  A byte at a time upwards through
;;; [SLO],y and [DLO],y, whose address carries into the bank, so a piece may
;;; cross one; and a match that overlaps what it writes repeats the way the
;;; format means.
copy:         lda     dp:CNT+2
              bne     10$
              lda     dp:CNT
              cmp     dp:LEN
              bcs     10$
              sta     dp:LEN          ; past the end: only what is left
              lda     ##1
              sta     dp:ERR
10$:          lda     dp:LEN
              beq     90$
              ldy     ##0
              sep     #0x20
20$:          lda     [dp:SLO],y
              sta     [dp:DLO],y
              iny
              cpy     dp:LEN
              bne     20$
              rep     #0x20
              lda     dp:SLO
              clc
              adc     dp:LEN
              sta     dp:SLO
              bcc     30$
              inc     dp:SBK
30$:          lda     dp:DLO
              clc
              adc     dp:LEN
              sta     dp:DLO
              bcc     40$
              inc     dp:DBK
40$:          lda     dp:CNT
              sec
              sbc     dp:LEN
              sta     dp:CNT
              lda     dp:CNT+2
              sbc     ##0
              sta     dp:CNT+2
90$:          rts
