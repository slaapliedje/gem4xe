;;; ---------------------------------------------------------------------------
;;; mul6502.s -- b6_mul16to32, in place of cc6502's _Mul16to32
;;; (docs/6502.md, step 4e).
;;;
;;; Calypsi 5.18's runtime returns the 32-bit product of two 16-bit values
;;; with its two low bytes swapped: 9 * 40 = $0168 comes back $6801.  The
;;; compiler calls it for (uint32_t)(uint16_t)a * (uint16_t)b, which is how
;;; the VDI addresses a row of a far form -- a drop-down's save landed 26 KB
;;; past its buffer.  The library's cannot be replaced at the link -- the
;;; module that holds it comes in for _Mul32 as well -- so
;;; tools/bsp6502/bankasm.py sends every banked call here by this name, and
;;; resident C calls it as a function (uint32_t b6_mul16to32(uint16_t,
;;; uint16_t): the same registers both ways).  It keeps the runtime's
;;; contract:
;;;
;;;   in   _Zp0-1 op1, _Zp2-3 op2 (unsigned)
;;;   out  _Zp0-3 the product
;;;   destroys a, y, _Zp2-5, _Zp8-11 -- and nothing else: the compiler keeps
;;;   values in the other registers across the call
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp
              .public b6_mul16to32

              .section code
b6_mul16to32: lda     #0
              sta     zp:_Zp+8      ; the product, _Zp8-11
              sta     zp:_Zp+9
              sta     zp:_Zp+10
              sta     zp:_Zp+11
              sta     zp:_Zp+4      ; op2 widened to 32 bits, _Zp2-5
              sta     zp:_Zp+5
              ldy     #16
10$:          lsr     zp:_Zp+1      ; the next bit of op1
              ror     zp:_Zp+0
              bcc     20$
              clc
              lda     zp:_Zp+8
              adc     zp:_Zp+2
              sta     zp:_Zp+8
              lda     zp:_Zp+9
              adc     zp:_Zp+3
              sta     zp:_Zp+9
              lda     zp:_Zp+10
              adc     zp:_Zp+4
              sta     zp:_Zp+10
              lda     zp:_Zp+11
              adc     zp:_Zp+5
              sta     zp:_Zp+11
20$:          asl     zp:_Zp+2      ; op2 doubled
              rol     zp:_Zp+3
              rol     zp:_Zp+4
              rol     zp:_Zp+5
              dey
              bne     10$
              lda     zp:_Zp+8      ; out, in order
              sta     zp:_Zp+0
              lda     zp:_Zp+9
              sta     zp:_Zp+1
              lda     zp:_Zp+10
              sta     zp:_Zp+2
              lda     zp:_Zp+11
              sta     zp:_Zp+3
              rts
