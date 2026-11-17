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
;;; src/sys/cio.c calls irq_pokey_resync after, since SIO has had POKEY.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public cio_call, dsk_call
              .extern _Zp, b6_cur, b6_portb

CIOV:         .equ    0xe456
SIOV:         .equ    0xe459
PORTB:        .equ    0xd301

              .section code
cio_call:     lda     zp:_Zp+0        ; 1..7
              asl     a
              asl     a
              asl     a
              asl     a
              tax
              jsr     CIOV
              jmp     back

dsk_call:     jsr     SIOV
back:         sty     zp:_Zp+0
              lda     #0
              sta     zp:_Zp+1
              ldx     b6_cur
              lda     b6_portb,x
              sta     PORTB
              rts
