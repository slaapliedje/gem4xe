;;; ---------------------------------------------------------------------------
;;; enter6502.s -- cc6502's frame helpers, faster (docs/6502.md, speed 4).
;;;
;;; Every function cc6502 compiles that keeps a register or a local calls
;;; the runtime's b6_AllocStackSave on the way in and b6_RestoreRegisters (or
;;; b6_DeallocStackRestore) on the way out, and those were a fifth of the
;;; 6502 desktop's busy time.  These are the same helpers with the same
;;; contracts -- the registers each takes and leaves, A kept -- under
;;; names of their own, b6_AllocStackSave and the rest: the linker will
;;; not let an object override the library's enter.o and stack.o (its
;;; own members are resolved inside the archive), so
;;; tools/bsp6502/bankasm.py --fast-frames sends every call in a
;;; compiled file here, as it sends _Mul16to32 to mul6502.s.  The
;;; library's own code keeps the library's.
;;;
;;; Two things are faster:
;;;
;;;   - the pseudo-registers are saved and restored by an unrolled run,
;;;     entered at the right place by an RTS through a table: 11 cycles a
;;;     byte, not the loop's 15, past a 20-cycle dispatch;
;;;   - _Vsp is moved without PHP/SEI/PLP.  The library holds interrupts
;;;     off across the two bytes because an interrupt handler written in C
;;;     would push onto _Vsp, and could land between them.  NO HANDLER OF
;;;     GEM4XE'S RUNS C (src/sys6502/irq6502.s, gate6502.s: assembly, and
;;;     the OS's own), and none may: one that did would need the
;;;     interrupt-safe library back, or a stack of its own.
;;;
;;; Resident in the system (Low); in a program, its shared RAM with the
;;; rest of the runtime.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Vsp, _Vfp, _Zp
              .public b6_AllocStackSave, b6_AllocStack
              .public b6_AllocStackLarge, b6_DeallocStackLarge
              .public b6_DeallocStackRestore, b6_DeallocStack, b6_RestoreRegisters
              .public b6_DecVspY0, b6_DecVsp, b6_IncVsp, b6_DecVsp16, b6_IncVsp16
              .public b6_LoadVspEA, b6_LoadVfpEA, b6_AllocStackVLA, b6_DeallocStackVLA

FirstSave:    .equ    _Zp + 24        ; the callee-saved pseudo-registers
NSAVE:        .equ    24              ; _Zp24-47

              .section code
;;; ---------------------------------------------------------------------------
;;; b6_AllocStackSave: Y = registers to save - 1, X = locals (negated, 0 for
;;; none).  _Vsp down by Y + 1, FirstSave[0..Y] to (_Vsp), then _Vsp down
;;; by the locals.  Keeps A and X; Y comes back $FF, as the library's.
;;; ---------------------------------------------------------------------------
b6_AllocStackSave:
              pha
              tya
              eor     #0xff           ; _Vsp + ~Y = _Vsp - (Y + 1)
              clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              bcs     1$
              dec     zp:_Vsp+1
1$:           cpy     #NSAVE
              bcs     slow_save       ; (never: there are 24 to save)
              lda     sv_hi,y
              pha
              lda     sv_lo,y
              pha
              rts                     ; into the run at FirstSave+Y
slow_save:    lda     FirstSave,y
              sta     (_Vsp),y
              dey
              bpl     slow_save
              bmi     sv_done
sv23:         lda     zp:FirstSave+23
              sta     (_Vsp),y
              dey
sv22:         lda     zp:FirstSave+22
              sta     (_Vsp),y
              dey
sv21:         lda     zp:FirstSave+21
              sta     (_Vsp),y
              dey
sv20:         lda     zp:FirstSave+20
              sta     (_Vsp),y
              dey
sv19:         lda     zp:FirstSave+19
              sta     (_Vsp),y
              dey
sv18:         lda     zp:FirstSave+18
              sta     (_Vsp),y
              dey
sv17:         lda     zp:FirstSave+17
              sta     (_Vsp),y
              dey
sv16:         lda     zp:FirstSave+16
              sta     (_Vsp),y
              dey
sv15:         lda     zp:FirstSave+15
              sta     (_Vsp),y
              dey
sv14:         lda     zp:FirstSave+14
              sta     (_Vsp),y
              dey
sv13:         lda     zp:FirstSave+13
              sta     (_Vsp),y
              dey
sv12:         lda     zp:FirstSave+12
              sta     (_Vsp),y
              dey
sv11:         lda     zp:FirstSave+11
              sta     (_Vsp),y
              dey
sv10:         lda     zp:FirstSave+10
              sta     (_Vsp),y
              dey
sv9:          lda     zp:FirstSave+9
              sta     (_Vsp),y
              dey
sv8:          lda     zp:FirstSave+8
              sta     (_Vsp),y
              dey
sv7:          lda     zp:FirstSave+7
              sta     (_Vsp),y
              dey
sv6:          lda     zp:FirstSave+6
              sta     (_Vsp),y
              dey
sv5:          lda     zp:FirstSave+5
              sta     (_Vsp),y
              dey
sv4:          lda     zp:FirstSave+4
              sta     (_Vsp),y
              dey
sv3:          lda     zp:FirstSave+3
              sta     (_Vsp),y
              dey
sv2:          lda     zp:FirstSave+2
              sta     (_Vsp),y
              dey
sv1:          lda     zp:FirstSave+1
              sta     (_Vsp),y
              dey
sv0:          lda     zp:FirstSave+0
              sta     (_Vsp),y
              dey
sv_done:      jmp     alloc1          ; the locals, and A back

;;; b6_AllocStack: X = locals (negated, 0 for none).  Keeps A.
b6_AllocStack:  pha
alloc1:       txa
              beq     2$
              clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              bcs     2$
              dec     zp:_Vsp+1
2$:           pla
              rts

;;; b6_AllocStackLarge / b6_DeallocStackLarge: X more pages down (negated) or
;;; up.  Keeps A.
b6_AllocStackLarge:
b6_DeallocStackLarge:
              pha
              txa
              clc
              adc     zp:_Vsp+1
              sta     zp:_Vsp+1
              pla
              rts

;;; ---------------------------------------------------------------------------
;;; b6_RestoreRegisters: Y = registers to restore - 1.  FirstSave[0..Y] from
;;; (_Vsp), then _Vsp up by Y + 1.  Keeps A; X comes back Y + 1 and Y $FF,
;;; as the library's.  b6_DeallocStackRestore drops the locals (X) first.
;;; ---------------------------------------------------------------------------
b6_DeallocStackRestore:
              jsr     b6_DeallocStack
b6_RestoreRegisters:
              pha
              tya
              tax
              inx                     ; what goes: the registers' bytes
              cpy     #NSAVE
              bcs     slow_rst
              lda     rs_hi,y
              pha
              lda     rs_lo,y
              pha
              rts
slow_rst:     lda     (_Vsp),y
              sta     FirstSave,y
              dey
              bpl     slow_rst
              bmi     dealloc1
rs23:         lda     (_Vsp),y
              sta     zp:FirstSave+23
              dey
rs22:         lda     (_Vsp),y
              sta     zp:FirstSave+22
              dey
rs21:         lda     (_Vsp),y
              sta     zp:FirstSave+21
              dey
rs20:         lda     (_Vsp),y
              sta     zp:FirstSave+20
              dey
rs19:         lda     (_Vsp),y
              sta     zp:FirstSave+19
              dey
rs18:         lda     (_Vsp),y
              sta     zp:FirstSave+18
              dey
rs17:         lda     (_Vsp),y
              sta     zp:FirstSave+17
              dey
rs16:         lda     (_Vsp),y
              sta     zp:FirstSave+16
              dey
rs15:         lda     (_Vsp),y
              sta     zp:FirstSave+15
              dey
rs14:         lda     (_Vsp),y
              sta     zp:FirstSave+14
              dey
rs13:         lda     (_Vsp),y
              sta     zp:FirstSave+13
              dey
rs12:         lda     (_Vsp),y
              sta     zp:FirstSave+12
              dey
rs11:         lda     (_Vsp),y
              sta     zp:FirstSave+11
              dey
rs10:         lda     (_Vsp),y
              sta     zp:FirstSave+10
              dey
rs9:          lda     (_Vsp),y
              sta     zp:FirstSave+9
              dey
rs8:          lda     (_Vsp),y
              sta     zp:FirstSave+8
              dey
rs7:          lda     (_Vsp),y
              sta     zp:FirstSave+7
              dey
rs6:          lda     (_Vsp),y
              sta     zp:FirstSave+6
              dey
rs5:          lda     (_Vsp),y
              sta     zp:FirstSave+5
              dey
rs4:          lda     (_Vsp),y
              sta     zp:FirstSave+4
              dey
rs3:          lda     (_Vsp),y
              sta     zp:FirstSave+3
              dey
rs2:          lda     (_Vsp),y
              sta     zp:FirstSave+2
              dey
rs1:          lda     (_Vsp),y
              sta     zp:FirstSave+1
              dey
rs0:          lda     (_Vsp),y
              sta     zp:FirstSave+0
              dey
              jmp     dealloc1

;;; b6_DeallocStack: X = bytes to drop.  Keeps A.
b6_DeallocStack:
              pha
dealloc1:     txa
              clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              bcc     1$
              inc     zp:_Vsp+1
1$:           pla
              rts

;;; the runs' entries, less one, for the RTS: [k] enters at register k
              .section cdata, rodata
sv_lo:        .byte   .byte0 (sv0-1), .byte0 (sv1-1), .byte0 (sv2-1), .byte0 (sv3-1)
              .byte   .byte0 (sv4-1), .byte0 (sv5-1), .byte0 (sv6-1), .byte0 (sv7-1)
              .byte   .byte0 (sv8-1), .byte0 (sv9-1), .byte0 (sv10-1), .byte0 (sv11-1)
              .byte   .byte0 (sv12-1), .byte0 (sv13-1), .byte0 (sv14-1), .byte0 (sv15-1)
              .byte   .byte0 (sv16-1), .byte0 (sv17-1), .byte0 (sv18-1), .byte0 (sv19-1)
              .byte   .byte0 (sv20-1), .byte0 (sv21-1), .byte0 (sv22-1), .byte0 (sv23-1)
sv_hi:        .byte   .byte1 (sv0-1), .byte1 (sv1-1), .byte1 (sv2-1), .byte1 (sv3-1)
              .byte   .byte1 (sv4-1), .byte1 (sv5-1), .byte1 (sv6-1), .byte1 (sv7-1)
              .byte   .byte1 (sv8-1), .byte1 (sv9-1), .byte1 (sv10-1), .byte1 (sv11-1)
              .byte   .byte1 (sv12-1), .byte1 (sv13-1), .byte1 (sv14-1), .byte1 (sv15-1)
              .byte   .byte1 (sv16-1), .byte1 (sv17-1), .byte1 (sv18-1), .byte1 (sv19-1)
              .byte   .byte1 (sv20-1), .byte1 (sv21-1), .byte1 (sv22-1), .byte1 (sv23-1)
rs_lo:        .byte   .byte0 (rs0-1), .byte0 (rs1-1), .byte0 (rs2-1), .byte0 (rs3-1)
              .byte   .byte0 (rs4-1), .byte0 (rs5-1), .byte0 (rs6-1), .byte0 (rs7-1)
              .byte   .byte0 (rs8-1), .byte0 (rs9-1), .byte0 (rs10-1), .byte0 (rs11-1)
              .byte   .byte0 (rs12-1), .byte0 (rs13-1), .byte0 (rs14-1), .byte0 (rs15-1)
              .byte   .byte0 (rs16-1), .byte0 (rs17-1), .byte0 (rs18-1), .byte0 (rs19-1)
              .byte   .byte0 (rs20-1), .byte0 (rs21-1), .byte0 (rs22-1), .byte0 (rs23-1)
rs_hi:        .byte   .byte1 (rs0-1), .byte1 (rs1-1), .byte1 (rs2-1), .byte1 (rs3-1)
              .byte   .byte1 (rs4-1), .byte1 (rs5-1), .byte1 (rs6-1), .byte1 (rs7-1)
              .byte   .byte1 (rs8-1), .byte1 (rs9-1), .byte1 (rs10-1), .byte1 (rs11-1)
              .byte   .byte1 (rs12-1), .byte1 (rs13-1), .byte1 (rs14-1), .byte1 (rs15-1)
              .byte   .byte1 (rs16-1), .byte1 (rs17-1), .byte1 (rs18-1), .byte1 (rs19-1)
              .byte   .byte1 (rs20-1), .byte1 (rs21-1), .byte1 (rs22-1), .byte1 (rs23-1)

              .section code
;;; ---------------------------------------------------------------------------
;;; stack.o's: _Vsp moved by A, Y, Y:A, Y:X or _Zp0-1; stack addresses
;;; into the zero page at X.  The same contracts, A kept where the
;;; library keeps it.
;;; ---------------------------------------------------------------------------
;;; b6_DecVsp: A = the count, negated (added, carry clear); b6_DecVspY0 also Y = 0
b6_DecVspY0:    ldy     #0
b6_DecVsp:      clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              bcs     1$
              dec     zp:_Vsp+1
1$:           rts

;;; b6_IncVsp: Y = bytes to drop - 1.  Keeps A.
b6_IncVsp:      pha
              tya
              sec
              adc     zp:_Vsp
              sta     zp:_Vsp
              bcc     1$
              inc     zp:_Vsp+1
1$:           pla
              rts

;;; b6_DecVsp16: Y:A = the negated count
b6_DecVsp16:    clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              tya
              adc     zp:_Vsp+1
              sta     zp:_Vsp+1
              rts

;;; b6_IncVsp16: Y:X = bytes to drop.  Keeps A.
b6_IncVsp16:    pha
              txa
              clc
              adc     zp:_Vsp
              sta     zp:_Vsp
              tya
              adc     zp:_Vsp+1
              sta     zp:_Vsp+1
              pla
              rts

;;; b6_LoadVspEA / b6_LoadVfpEA: _Vsp (_Vfp) + A into the zero page at X
b6_LoadVspEA:   clc
              adc     zp:_Vsp
              sta     0,x
              lda     zp:_Vsp+1
              adc     #0
              sta     1,x
              rts

b6_LoadVfpEA:   clc
              adc     zp:_Vfp
              sta     0,x
              lda     zp:_Vfp+1
              adc     #0
              sta     1,x
              rts

;;; b6_AllocStackVLA / b6_DeallocStackVLA: _Vsp down / up by _Zp0-1
b6_AllocStackVLA:
              sec
              lda     zp:_Vsp
              sbc     zp:_Zp
              sta     zp:_Vsp
              lda     zp:_Vsp+1
              sbc     zp:_Zp+1
              sta     zp:_Vsp+1
              rts

b6_DeallocStackVLA:
              clc
              lda     zp:_Vsp
              adc     zp:_Zp
              sta     zp:_Vsp
              lda     zp:_Vsp+1
              adc     zp:_Zp+1
              sta     zp:_Vsp+1
              rts
