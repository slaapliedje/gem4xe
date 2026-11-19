;;; ---------------------------------------------------------------------------
;;; gate6502.s -- how a 6502 application calls gem4xe (docs/6502.md, step 5).
;;;
;;; THE GATE, at $2000: the one address a program knows (the kit's
;;; src/app/gemabi6502.s jumps here).  It takes the call's letter in A --
;;; 'V', 'A' or 'D', the 65C816's COP signature byte -- and the parameter
;;; block's window address in _Zp0-1, records them and the caller's bank
;;; (b6_cur: the window is the program's while it runs) for src/sys/abi.c,
;;; and is then a veneer itself: _bcall maps the `abi` bank, calls
;;; gem_entry there, maps the program's bank again and returns to the
;;; program, past the JSR that brought it here -- the kit's, which has put
;;; _Vsp on the system's C stack for the call (src/app/gemabi6502.s).
;;;
;;; THE OS ROM IS OUT once the system has started (step 5c-1): a program
;;; of several banks keeps its data, stack and veneers in the RAM under
;;; it, and every pointer it hands the system points there, so the system
;;; runs with the RAM in -- PORTB bit 0 clear, in PORTB and in every entry
;;; of b6_portb (src/a6_tree.c, ram_vectors) -- and switches the ROM in
;;; only around CIOV and SIOV (src/sys6502/cio6502.s).
;;;
;;; AN INTERRUPT WITH THE ROM OUT reads its vector from the RAM under it:
;;; src/a6_tree.c writes g6_nmi, g6_reset and g6_irq there at start.  Each keeps A, X and PORTB, switches the ROM in, and enters the
;;; ROM's own handler as the CPU would have -- the return (g6_iret) and
;;; the P the CPU pushed, copied from the stack: a PHP would push B set,
;;; and the XL OS reads that as a BRK -- and g6_iret puts back PORTB, X
;;; and A before its RTI.  With the ROM in, the CPU takes the ROM's
;;; vectors and none of this runs.  The pointer sampler's timer and the
;;; keyboard -- ~500 IRQs a second, all gem4xe's own -- skip the ROM:
;;; g6_irq hands them straight to src/sys6502/irq6502.s (irq6_take),
;;; which is resident and ends in its own RTI; the ROM's round trip cost
;;; ~130 cycles of each (step 6a).
;;;
;;; THE PROGRAM'S START, p6_ven: a veneer in RAM, to $4003 -- the JMP in
;;; the program's header (src/app/crt6502.s) -- in a bank written into its
;;; last byte when the program is loaded.  A context's entry must be a
;;; resident function (src/sys6502/ctx6502.c), and this is one.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, _bcall, b6_cur, gem_pb, gem_which, gem_bank6
              .extern gem_entry__b, irq6_take, irq6_mask
              .public g6_gate, p6_ven, g6_nmi, g6_reset, g6_irq

PORTB:        .equ    0xd301

ABI_BANK:     .equ    17              ; --bank abi=17 (tools/bsp6502/rules.mk)

              .section gate, root, noreorder
g6_gate:      sta     gem_which
              lda     zp:_Zp+0
              sta     gem_pb
              lda     zp:_Zp+1
              sta     gem_pb+1
              lda     #0
              sta     gem_pb+2
              sta     gem_pb+3
              lda     b6_cur
              sta     gem_bank6
              jsr     _bcall
              .word   gem_entry__b
              .byte   ABI_BANK

;;; the interrupt handlers for the ROM out: resident code of their own,
;;; apart from the gate, whose fragment nothing outside may name
              .section code
g6_nmi:       pha
              txa
              pha
              lda     PORTB
              pha
              ora     #1
              sta     PORTB
              lda     #.byte1 g6_iret ; the ROM handler's RTI comes here
              pha
              lda     #.byte0 g6_iret
              pha
              tsx                     ; the CPU's P, under A, X, PORTB
              lda     0x0106,x        ; and the return just pushed
              pha
              jmp     (0xfffa)        ; the ROM's, now it is in
g6_irq:       pha
              lda     0xd20e          ; IRQST: 0 = pending
              eor     #0xff
              and     0x10            ; POKMSK
              and     irq6_mask       ; timer 1 or a key, while ours:
              beq     1$              ; served without the ROM (step 6a)
              jmp     irq6_take
1$:           txa
              pha
              lda     PORTB
              pha
              ora     #1
              sta     PORTB
              lda     #.byte1 g6_iret
              pha
              lda     #.byte0 g6_iret
              pha
              tsx
              lda     0x0106,x
              pha
              jmp     (0xfffe)
g6_iret:      pla
              sta     PORTB
              pla
              tax
              pla
              rti
g6_reset:     lda     PORTB           ; the ROM in, and its own reset
              ora     #1
              sta     PORTB
              jmp     (0xfffc)

              .section data, data
p6_ven:       .byte   0x20            ; JSR _bcall: spelt out, in RAM
              .word   _bcall
              .word   0x4003
              .byte   0               ; the program's bank, at load
