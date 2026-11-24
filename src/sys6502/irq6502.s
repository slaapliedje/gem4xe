;;; ---------------------------------------------------------------------------
;;; irq6502.s -- gem4xe's interrupt handlers on a stock 6502 (docs/6502.md,
;;; step 4d).  src/sys/irq.s is the 65C816's.
;;;
;;; A 6502 takes the OS ROM's vectors at $FFFA-$FFFF, which are there and
;;; stay there: the OS, its CIO and the DOS run beside GEM on a 6502.  So
;;; nothing is copied; the handlers go into the OS's own RAM vectors and
;;; hand on what is not theirs:
;;;
;;;   VVBLKI  $0222   the immediate VBI, which runs even while SIO holds
;;;                   CRITIC (the deferred one does not): irq_frames, and
;;;                   the triggers' ring as src/sys/irq.s keeps it; then
;;;                   on to what VVBLKI held, the OS's SYSVBV.  The OS has
;;;                   pushed A, X and Y before it jumps here.
;;;   VIMIRQ  $0216   every IRQ, before the OS's dispatch has pushed
;;;                   anything: POKEY timer 1 (the pointer sampler) and the
;;;                   keyboard are served here, acknowledged as the OS does
;;;                   (the latch low, then POKMSK again), and anything else
;;;                   -- SIO's serial interrupts, BREAK -- goes on to what
;;;                   VIMIRQ held with every register as it came.
;;;
;;; The fast path matters on a 1.79 MHz 6502: the sampler with a pointer
;;; moving costs ~200 cycles a time; with it still, A alone and no decode
;;; (irq6_take); the OS's own dispatch would add more.
;;; src/sys6502/irq6502.c says what rate it runs.
;;;
;;; The state is src/sys6502/irq6502.c's (the names src/sys/irq.h gives),
;;; resident, as all of this is: an interrupt arrives with any bank in the
;;; window.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .extern irq_frames, irq_timer, irq_qlo, irq_qhi
              .extern irq_kb, irq_kb_head, irq_kb_tail, irq_kb_count
              .extern irq_ptr_on, ptr_port, irq_plo, irq_phi, irq_qtab
              .extern irq_prev_lo, irq_prev_hi, irq_pend, irq_tmp
              .extern irq_tq, irq_tq_head, irq_tq_tail, irq6_last
              .public irq6_vbi, irq6_irq, irq6_old_vbi, irq6_old_irq
              .public irq6_hook, irq6_unhook, irq6_take, irq6_mask
              .public irq6_dlo, irq6_dhi

NMIRES:       .equ    0xd40f
IRQST:        .equ    0xd20e          ; read: 0 = pending
IRQEN:        .equ    0xd20e          ; write
KBCODE:       .equ    0xd209
TRIG0:        .equ    0xd010
TRIG1:        .equ    0xd011
PORTA:        .equ    0xd300
POKMSK:       .equ    0x0010
ATRACT:       .equ    0x004d
VIMIRQ:       .equ    0x0216
VVBLKI:       .equ    0x0222
SETVBV:       .equ    0xe45c
IRQ6_QSKIP:   .equ    2               ; src/sys/irq.h: a two-step jump

              .section zdata, bss
irq6_old_vbi: .space  2               ; what VVBLKI held: SYSVBV
irq6_old_irq: .space  2               ; what VIMIRQ held: the OS's dispatch
;;; the IRQs src/sys6502/gate6502.s's g6_irq takes straight here with the
;;; ROM out: timer 1 and the keyboard while hooked, none while not (the
;;; OS has the keyboard back then)
irq6_mask:    .space  1

;;; each axis's last direction, +1 or -1 (0: none yet), for a jump of two
;;; (irq6_take); in the zero page, which costs the decode bytes it has not
              .section zpage, bss
irq6_dlo:     .space  1
irq6_dhi:     .space  1

              .section code
;;; ---------------------------------------------------------------------------
;;; The vertical blank.  A, X, Y are the OS's to restore.
;;; ---------------------------------------------------------------------------
irq6_vbi:     inc     irq_frames
              bne     1$
              inc     irq_frames+1
1$:           lda     TRIG1           ; 1 = pressed, bit 0 TRIG0, bit 1 TRIG1
              and     #1
              asl     a
              sta     irq_tmp+1       ; the IRQ handler's irq_tmp is [0]
              lda     TRIG0
              and     #1
              ora     irq_tmp+1
              eor     #3
              sta     irq_tmp+1
              lda     irq_tq_tail
              sec
              sbc     #1
              and     #3
              tax                     ; the last change's slot
              lda     irq_tmp+1
              cmp     irq_tq,x
              beq     9$              ; no change
              ldx     irq_tq_tail
              sta     irq_tq,x
              inx
              txa
              and     #3
              cmp     irq_tq_head
              beq     9$              ; full: the newest change is dropped
              sta     irq_tq_tail
9$:           lda     #0              ; no attract mode: the OS never
              sta     ATRACT          ; sees a key to reset it by
              jmp     (irq6_old_vbi)

;;; ---------------------------------------------------------------------------
;;; Every IRQ.  Nothing pushed yet.
;;; ---------------------------------------------------------------------------
irq6_irq:     pha
              lda     IRQST
              eor     #0xff
              and     POKMSK
              and     #0x41           ; timer 1, keyboard
              bne     irq6_take
              pla                     ; not ours: on, as it came
              jmp     (irq6_old_irq)

;;; g6_irq comes in here, A pushed, A the pending bits that are ours
;;;
;;; THE STILL POINTER COSTS ONLY A.  Most samples find the port as it was,
;;; so that path touches no other register: the whole of PORTA is compared
;;; with the last sample, both ports' lines, which needs neither ptr_port
;;; nor a shift.  A line of the other port that moved costs one decode that
;;; finds its own pair as it was, which counts nothing.  X and Y are saved
;;; only by the decode and by the keyboard, which need them.
irq6_take:    sta     irq_pend
              eor     #0xff
              and     POKMSK
              sta     IRQEN           ; those latches low ...
              lda     POKMSK
              sta     IRQEN           ; ... and armed again

              lda     irq_pend        ; the keyboard: the raw code into the ring
              and     #0x40
              beq     10$
              txa
              pha
              lda     KBCODE
              ldx     irq_kb_tail
              sta     irq_kb,x
              inx
              txa
              and     #7
              cmp     irq_kb_head
              beq     5$              ; full: the newest is dropped
              sta     irq_kb_tail
5$:           inc     irq_kb_count
              pla
              tax

10$:          lda     irq_pend        ; timer 1: the pointer sampler
              lsr     a
              bcc     90$
              inc     irq_timer
              bne     20$
              inc     irq_timer+1
              bne     20$
              inc     irq_timer+2
              bne     20$
              inc     irq_timer+3
20$:          lda     irq_ptr_on
              beq     80$
              lda     PORTA
              cmp     irq6_last       ; as last time: no line moved
              bne     30$
90$:          pla
              rti

80$:          lda     PORTA           ; off: unlike the next sample, so it
              eor     #0xff           ; decodes, whatever the tables were
              sta     irq6_last       ; rebuilt from
              pla
              rti

30$:          sta     irq6_last       ; a line moved: decode
              txa
              pha
              tya
              pha
              lda     irq6_last
              ldx     ptr_port        ; port 2 is the HIGH nibble
              beq     31$
              lsr     a
              lsr     a
              lsr     a
              lsr     a
31$:          and     #0x0f
              tax
              lda     irq_plo,x       ; this axis's line pair, 0..3
              sta     irq_tmp
              ora     irq_prev_lo     ; (prev << 2) | now
              tay
              lda     irq_tmp
              asl     a
              asl     a
              sta     irq_prev_lo
              lda     irq_qtab,y
              beq     40$             ; no count
              cmp     #IRQ6_QSKIP
              bne     32$
              lda     zp:irq6_dlo     ; a jump of two: the way it last went
              asl     a               ; +-1 -> +-2; none yet (0): none
              beq     40$
              bne     33$
32$:          sta     zp:irq6_dlo     ; +-1: which way it goes
33$:          ldy     #0              ; the delta's high byte
              cmp     #0x80
              bcc     34$
              dey
34$:          clc
              adc     irq_qlo
              sta     irq_qlo
              tya
              adc     irq_qlo+1
              sta     irq_qlo+1
40$:          lda     irq_phi,x
              sta     irq_tmp
              ora     irq_prev_hi
              tay
              lda     irq_tmp
              asl     a
              asl     a
              sta     irq_prev_hi
              lda     irq_qtab,y
              beq     50$             ; no count
              cmp     #IRQ6_QSKIP
              bne     42$
              lda     zp:irq6_dhi     ; a jump of two: the way it last went
              asl     a               ; +-1 -> +-2; none yet (0): none
              beq     50$
              bne     43$
42$:          sta     zp:irq6_dhi     ; +-1: which way it goes
43$:          ldy     #0              ; the delta's high byte
              cmp     #0x80
              bcc     44$
              dey
44$:          clc
              adc     irq_qhi
              sta     irq_qhi
              tya
              adc     irq_qhi+1
              sta     irq_qhi+1
50$:          pla
              tay
              pla
              tax
              pla
              rti

;;; ---------------------------------------------------------------------------
;;; irq6_hook -- the vectors taken, what they held kept; timer 1 armed.
;;; The VBI's through SETVBV (the OS's way: it writes the two bytes where
;;; no VBI can land between them); the IRQ's with I set.
;;; ---------------------------------------------------------------------------
irq6_hook:    lda     VVBLKI
              sta     irq6_old_vbi
              lda     VVBLKI+1
              sta     irq6_old_vbi+1
              lda     #6              ; the immediate VBI
              ldy     #.byte0 irq6_vbi
              ldx     #.byte1 irq6_vbi
              jsr     SETVBV
              php
              sei
              lda     VIMIRQ
              sta     irq6_old_irq
              lda     VIMIRQ+1
              sta     irq6_old_irq+1
              lda     #.byte0 irq6_irq
              sta     VIMIRQ
              lda     #.byte1 irq6_irq
              sta     VIMIRQ+1
              lda     #0x41
              sta     irq6_mask
              lda     POKMSK
              ora     #0x41           ; timer 1, and the keyboard the OS had
              sta     POKMSK
              sta     IRQEN
              plp
              rts

;;; irq6_unhook -- timer 1 off, the vectors as they were.
irq6_unhook:  php
              sei
              lda     #0
              sta     irq6_mask
              lda     POKMSK
              and     #0xfe
              sta     POKMSK
              sta     IRQEN
              lda     irq6_old_irq
              sta     VIMIRQ
              lda     irq6_old_irq+1
              sta     VIMIRQ+1
              plp
              lda     #6
              ldy     irq6_old_vbi
              ldx     irq6_old_vbi+1
              jmp     SETVBV
