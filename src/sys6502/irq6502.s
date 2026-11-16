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
;;; moving costs ~200 cycles a time, less with it still (the decode is
;;; skipped when the port's lines are as they were), and the OS's own
;;; dispatch would add more; src/sys6502/irq6502.c says what rate it runs.
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
              .public irq6_hook, irq6_unhook

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

              .section zdata, bss
irq6_old_vbi: .space  2               ; what VVBLKI held: SYSVBV
irq6_old_irq: .space  2               ; what VIMIRQ held: the OS's dispatch

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
              bne     10$
              pla                     ; not ours: on, as it came
              jmp     (irq6_old_irq)

10$:          sta     irq_pend
              eor     #0xff
              and     POKMSK
              sta     IRQEN           ; those latches low ...
              lda     POKMSK
              sta     IRQEN           ; ... and armed again
              txa
              pha
              tya
              pha

              lda     irq_pend        ; timer 1: the pointer sampler
              lsr     a
              bcs     11$
              jmp     40$
11$:          inc     irq_timer
              bne     20$
              inc     irq_timer+1
              bne     20$
              inc     irq_timer+2
              bne     20$
              inc     irq_timer+3
20$:          lda     irq_ptr_on
              bne     22$
              lda     #0xff           ; off: the next sample decodes, whatever
              sta     irq6_last       ; the tables were rebuilt from
              jmp     40$
22$:          lda     PORTA
              ldx     ptr_port        ; port 2 is the HIGH nibble
              beq     21$
              lsr     a
              lsr     a
              lsr     a
              lsr     a
21$:          and     #0x0f
              cmp     irq6_last       ; as last time: no pair moved, and a
              bne     23$             ; still pointer costs no decode
              jmp     40$
23$:          sta     irq6_last
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
              beq     30$
              bmi     25$
              inc     irq_qlo
              bne     30$
              inc     irq_qlo+1
              jmp     30$
25$:          lda     irq_qlo
              bne     26$
              dec     irq_qlo+1
26$:          dec     irq_qlo
30$:          lda     irq_phi,x
              sta     irq_tmp
              ora     irq_prev_hi
              tay
              lda     irq_tmp
              asl     a
              asl     a
              sta     irq_prev_hi
              lda     irq_qtab,y
              beq     40$
              bmi     35$
              inc     irq_qhi
              bne     40$
              inc     irq_qhi+1
              jmp     40$
35$:          lda     irq_qhi
              bne     36$
              dec     irq_qhi+1
36$:          dec     irq_qhi

40$:          lda     irq_pend        ; the keyboard: the raw code into the ring
              and     #0x40
              beq     90$
              lda     KBCODE
              ldx     irq_kb_tail
              sta     irq_kb,x
              inx
              txa
              and     #7
              cmp     irq_kb_head
              beq     45$             ; full: the newest is dropped
              sta     irq_kb_tail
45$:          inc     irq_kb_count

90$:          pla
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
              lda     POKMSK
              ora     #0x41           ; timer 1, and the keyboard the OS had
              sta     POKMSK
              sta     IRQEN
              plp
              rts

;;; irq6_unhook -- timer 1 off, the vectors as they were.
irq6_unhook:  php
              sei
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
