;;; ---------------------------------------------------------------------------
;;; ctx6502.s -- the context switch on a 6502: what C cannot write.
;;;
;;; src/sys/ctx.h says why contexts share one stack and take turns on it;
;;; src/sys/ctx.s is the 65C816's.  A 6502 program has TWO stacks, and a
;;; context owns its extent of both:
;;;
;;;   page 1    the 6502's own: return addresses, and under each call into
;;;             a bank the caller's bank, which _bcall pushes there
;;;             (src/sys6502/bank6502.s) -- so the banks a context is
;;;             nested through travel with it;
;;;   _Vsp      Calypsi's C stack, a software stack growing down from the
;;;             top of `cstack`: every frame, local and spilled register.
;;;
;;; The shape of a switch, as on the 65C816:
;;;
;;;     push the register file  _Zp, _Vsp, _Vfp, _Temp ($80-$B5): per
;;;                         context, as a 68000 process's registers are.
;;;                         On page 1 it travels with the park, and a C
;;;                         function could not do this -- it restores the
;;;                         registers it saved as its last act.
;;;     push b6_cur         the bank mapped now: the caller of ctx_switch
;;;                         may be running in the window.
;;;     ctx_park()          copies both extents out and says where the
;;;                         incoming context left its S and _Vsp.
;;;     S and _Vsp moved    the outgoing stacks no longer exist.
;;;     ctx_unpark()        copies the incoming extents back; its own
;;;                         frames are below both new pointers.
;;;     pull b6_cur         and map it: the code to return to is there.
;;;     pull the registers  and rts, into whoever parked this context.
;;;
;;; ctx_park answers in _Zp: 0 never run (start it fresh at the top of both
;;; stacks), 1 resume (at ctx_sp_out / ctx_vsp_out), 2 refused (ctx_over:
;;; nothing moved, so this stack still carries our own copy).
;;;
;;; THIS FILE IS RESIDENT: it moves S, and the code that does must not be in
;;; the window when the incoming context's bank goes back.  ctx6502.c may be
;;; banked (A6 has it in `evt`): its calls go through _bcall, whose return
;;; address and saved bank are pushed BELOW S -- never inside an extent
;;; being copied -- and it touches only resident memory (page 1, the C
;;; stack, the records) and far memory through the resident far_* helpers.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .extern _Zp, _Vsp
              .extern ctx_cur, ctx_park, ctx_unpark, ctx_boot, ctx_start0
              .extern b6_cur, b6_portb
              .public ctx_switch, ctx_init
              .public ctx_sp_in, ctx_vsp_in, ctx_sp_out, ctx_vsp_out
              .public ctx_hbase, ctx_vbase, ctx_reg_lo, ctx_reg_hi, ctx_s_now

PORTB:        .equ    0xd301
;;; _Zp's 48, _Vsp, _Vfp, _Temp (the vendor's pseudoRegisters.s).  The
;;; linker's own bounds are checked against it at start-up (ctx_regs_ok).
CTX_REGS:     .equ    54

              .section registers, noinit
              .section cdata, rodata
ctx_reg_lo:   .word   .sectionStart registers
ctx_reg_hi:   .word   .sectionEnd registers + 1

              .section zdata, bss
ctx_sp_in:    .space  1               ; page-1 S at the switch, after the pushes
ctx_sp_out:   .space  1               ; ...and the incoming one's
ctx_hbase:    .space  1               ; the top of the shared page-1 extent
ctx_p:        .space  1               ; P across the move
ctx_vsp_in:   .space  2
ctx_vsp_out:  .space  2
ctx_vbase:    .space  2               ; the top of the shared C-stack extent

              .section code
;;; ---------------------------------------------------------------------------
;;; void ctx_switch(CTX *to) -- the target in _Zp.
;;; ---------------------------------------------------------------------------
ctx_switch:   lda     zp:_Zp
              cmp     ctx_cur
              bne     1$
              lda     zp:_Zp+1
              cmp     ctx_cur+1
              bne     1$
              rts                     ; already the running one

1$:           ldx     #CTX_REGS-1     ; the register file, top byte first
10$:          lda     zp:_Zp,x
              pha
              dex
              bpl     10$
              lda     b6_cur
              pha
              tsx
              stx     ctx_sp_in
              lda     zp:_Vsp
              sta     ctx_vsp_in
              lda     zp:_Vsp+1
              sta     ctx_vsp_in+1
              jsr     ctx_park        ; `to` is still in _Zp
              lda     zp:_Zp
              beq     ctx_fresh
              cmp     #2
              beq     ctx_back

              php                     ; both pointers at once: an interrupt
              pla                     ; handler's C would use _Vsp
              sta     ctx_p
              sei
              ldx     ctx_sp_out
              txs
              lda     ctx_vsp_out
              sta     zp:_Vsp
              lda     ctx_vsp_out+1
              sta     zp:_Vsp+1
              lda     ctx_p           ; P through the NEW stack, below S
              pha
              plp
              jsr     ctx_unpark

ctx_back:     pla                     ; the bank this context was in
              tax
              stx     b6_cur
              lda     b6_portb,x
              sta     PORTB
              ldx     #0
20$:          pla
              sta     zp:_Zp,x
              inx
              cpx     #CTX_REGS
              bne     20$
              rts

;;; Its first turn: the tops of both stacks, and its program.  Nothing is
;;; pulled: it has no saved registers yet.  ctx_boot never returns -- a
;;; finished program switches away for good -- but if it did, it would be
;;; entered again rather than run off the end.
ctx_fresh:    php
              pla
              sta     ctx_p
              sei
              ldx     ctx_hbase
              txs
              lda     ctx_vbase
              sta     zp:_Vsp
              lda     ctx_vbase+1
              sta     zp:_Vsp+1
              lda     ctx_p
              pha
              plp
              jsr     ctx_boot
              jmp     ctx_fresh

;;; ---------------------------------------------------------------------------
;;; void ctx_init(CTX *first) -- the record in _Zp.
;;;
;;; The marks are the CALLER's pointers, taken here and not in C (ctx.s says
;;; why): S before the jsr that got here, and _Vsp, which nothing between
;;; the caller and this has moved.
;;; ---------------------------------------------------------------------------
ctx_init:     tsx
              inx
              inx                     ; undo this jsr's return address
              stx     ctx_hbase
              lda     zp:_Vsp
              sta     ctx_vbase
              lda     zp:_Vsp+1
              sta     ctx_vbase+1
              jmp     ctx_start0      ; `first` still in _Zp

;;; uint16_t ctx_s_now(void) -- page-1 S, for a gate measuring its depth.
ctx_s_now:    tsx
              stx     zp:_Zp
              lda     #0
              sta     zp:_Zp+1
              rts
