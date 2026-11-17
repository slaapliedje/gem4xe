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
;;; THE PROGRAM'S START, p6_ven: a veneer in RAM, to $4003 -- the JMP in
;;; the program's header (src/app/crt6502.s) -- in a bank written into its
;;; last byte when the program is loaded.  A context's entry must be a
;;; resident function (src/sys6502/ctx6502.c), and this is one.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, _bcall, b6_cur, gem_pb, gem_which, gem_bank6
              .extern gem_entry__b
              .public g6_gate, p6_ven

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

              .section data, data
p6_ven:       .byte   0x20            ; JSR _bcall: spelt out, in RAM
              .word   _bcall
              .word   0x4003
              .byte   0               ; the program's bank, at load
