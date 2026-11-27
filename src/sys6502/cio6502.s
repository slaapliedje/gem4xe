;;; ---------------------------------------------------------------------------
;;; cio6502.s -- the OS's CIO and SIO from gem4xe on a stock 6502
;;; (docs/6502.md, step 5b).  src/sys/cio.s is the 65C816's, which has a
;;; mode to switch; here there is none, and the OS's vectors are its own
;;; (src/sys6502/irq6502.s), so a call is a JSR.  What is left to do:
;;;
;;;   cio_call(iocb)   IOCB `iocb` (1..7) filled in by src/sys/cio.c: X is
;;;                    iocb * 16, then CIOV.  The status comes back in Y.
;;;   dsk_call(0)      the DCB at $0300 filled in: SIOV.  The status, Y.
;;;
;;; Both answer the status in _Zp0-1, as Calypsi returns a 16-bit value,
;;; and put back the bank gem4xe had in the window: a DOS that keeps its
;;; buffers in a PORTB bank (SpartaDOS X can) maps its own and need not
;;; map ours again.  The buffer a caller passes must be outside the
;;; window for the same reason; cio.c's name buffer is in HiRam, and the
;;; loader's in ScreenTail (src/a6_evt.c).
;;;
;;; RESIDENT: CIO returns with whatever the DOS left in the window.
;;; THE ROM is switched in for the call and out after (step 5c-1).
;;; src/sys/cio.c calls irq_pokey_resync after, since SIO has had POKEY.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public cio_call, dsk_call, cio_bank
              .public b6sw_cio            ; bank switches: bank6502.s's patch
              .extern _Zp, b6_cur, b6_portb, b6_kind

CIOV:         .equ    0xe456
SIOV:         .equ    0xe459
PORTB:        .equ    0xd301
AXLON:        .equ    0xcfff

              .section code
cio_call:     lda     zp:_Zp+0        ; 1..7
              asl     a
              asl     a
              asl     a
              asl     a
              tax
              jsr     rom_in
              lda     cio_bank        ; a bank for the call's buffer?
              beq     1$
              lda     b6_kind
              cmp     #'A'
              beq     2$
              lda     cio_bank
              sta     PORTB           ; (its ROM bit set by the caller)
              jmp     1$
2$:           lda     cio_bank        ; an Axlon's bank number: the ROM
              sta     AXLON           ; is in, so the register hears it
1$:           jsr     CIOV
              jmp     back

dsk_call:     jsr     rom_in
              jsr     SIOV
back:         sty     zp:_Zp+0
              lda     #0
              sta     zp:_Zp+1
              ldx     b6_cur
b6sw_cio:        lda     b6_portb,x
              sta     PORTB
              lda     cio_pb          ; PORTB as it was: the ROM out again
              sta     PORTB           ; where it was out (on an Axlon the
              rts                     ; patched store above called ax_sw)
;;; the OS ROM in for the call: on a PORTB machine the system runs with it
;;; out (step 5c-1, src/sys6502/gate6502.s)
rom_in:       lda     PORTB
              sta     cio_pb
              ora     #1
              sta     PORTB
              rts

              .section zdata, bss
cio_pb:       .space  1               ; PORTB before the call
cio_bank:     .space  1               ; 0, or PORTB (an Axlon: its bank) for the call (a6_evt.c)
