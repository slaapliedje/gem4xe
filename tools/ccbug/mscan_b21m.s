; mscan_b21m.s -- B21 without an immediate, cc65816 5.18.2 -O2 --data-model=large,
; kept as the fixture that proves mscan.mixed() can report.  ci_named is
; src/desk/desktop.c's as phase 87 first wrote it (a char folded to upper
; case): one hit, the `lda dp:.tiny (_Dp+4)` that ?L437 opens with, reached
; 8-bit from the folding path and 16-bit from the others.  ci_named_word is
; the shipped version, every character a WORD: the control that must stay
; silent.  (tools/ccbug/README.md, B21.)
ci_named:
            pei     dp:.tiny (_Dp+8)
            pei     dp:.tiny (_Dp+10)
            pei     dp:.tiny (_Dp+12)
            phy
            ldx     ##0
            txy
`?L425`:    tya
            sec
            sbc     ##32
            bvc     `?L1272`
            eor     ##-32768
`?L1272`:   bpl     `?L427`
            jsl     long:`?L1471`
            sta     dp:.tiny (_Dp+10)
            sty     dp:.tiny (_Dp+12)
            clc
            lda     dp:.tiny (_Dp+8)
            adc     dp:.tiny (_Dp+12)
            sta     dp:.tiny (_Dp+8)
            sep     #32
            lda     [.tiny (_Dp+8)]
            sta     1,s
            lda     1,s
            rep     #32
            bne     `?L429`
`?L427`:
            stx     dp:.tiny _Dp
            clc
            lda     dp:.tiny (_Dp+4)
            adc     dp:.tiny _Dp
            sta     dp:.tiny (_Dp+4)
            lda     [.tiny (_Dp+4)]
            and     ##255
            bne     `?L635`
            lda     ##1
            bra     `?L423`
`?L429`:    lda     1,s
            sep     #32
            cmp     #32
            rep     #32
            beq     `?L426`
            sep     #32
            cmp     #97
            rep     #32
            bcc     `?L437`
            lda     ##122
            sep     #32
            cmp     1,s
            rep     #32
            bcc     `?L437`
            lda     1,s
            sec
            sbc     ##32
            sep     #32
            sta     1,s
`?L437`:
            lda     dp:.tiny (_Dp+4)
            sta     dp:.tiny (_Dp+8)
            lda     dp:.tiny (_Dp+6)
            jsl     long:`?L1436`
            lda     [.tiny (_Dp+8)]
            sep     #32
            cmp     1,s
            rep     #32
            beq     `?L440`
`?L635`:    lda     ##0
`?L423`:
            ply
            ply
            sty     dp:.tiny (_Dp+12)
            ply
            sty     dp:.tiny (_Dp+10)
            ply
            sty     dp:.tiny (_Dp+8)
            rtl

ci_named_word:
            pei     dp:.tiny (_Dp+8)
            pei     dp:.tiny (_Dp+10)
            phy
            phy
            phy
            ldx     ##0
            txa
            sta     3,s
            txa
`?W1403`:   sta     5,s
            lda     3,s
            sec
            sbc     ##32
            bvc     `?W1272`
            eor     ##-32768
`?W1272`:   bpl     `?W427`
            jsl     long:`?W1443`
            clc
            lda     dp:.tiny (_Dp+8)
            adc     3,s
            sta     dp:.tiny (_Dp+8)
            lda     [.tiny (_Dp+8)]
            and     ##255
            tax
            bne     `?W429`
`?W427`:
            clc
            lda     dp:.tiny (_Dp+4)
            adc     5,s
            sta     dp:.tiny (_Dp+4)
            lda     [.tiny (_Dp+4)]
            and     ##255
            bne     `?W635`
            lda     ##1
            bra     `?W423`
`?W429`:    cpx     ##32
            bne     `?W433`
            lda     5,s
            bra     `?W1402`
`?W433`:    txa
            sec
            sbc     ##97
            bvc     `?W1274`
            eor     ##-32768
`?W1274`:   bmi     `?W436`
            lda     ##122
            stx     dp:.tiny (_Dp+8)
            sec
            sbc     dp:.tiny (_Dp+8)
            bvc     `?W1276`
            eor     ##-32768
`?W1276`:   bmi     `?W436`
            txa
            sec
            sbc     ##32
            sta     1,s
            bra     `?W437`
`?W436`:    txa
            sta     1,s
`?W437`:
            lda     dp:.tiny (_Dp+4)
            sta     dp:.tiny (_Dp+8)
            lda     dp:.tiny (_Dp+6)
            sta     dp:.tiny (_Dp+10)
            clc
            lda     dp:.tiny (_Dp+8)
            adc     5,s
            sta     dp:.tiny (_Dp+8)
            lda     [.tiny (_Dp+8)]
            and     ##255
            cmp     1,s
            beq     `?W440`
`?W635`:    lda     ##0
`?W423`:
            ply
            ply
            ply
            jmp     long:`?W1431`
`?W440`:    lda     5,s
            inc     a
`?W1402`:   sta     1,s
            lda     3,s
            inc     a
            sta     3,s
            lda     1,s
            jmp     .kbank `?W1403`
            .section farcode,text
ci_copy:
            pei     dp:.tiny (_Dp+8)
            pei     dp:.tiny (_Dp+10)
            pei     dp:.tiny (_Dp+12)
            phy
            phy
            phy
            sta     1,s
            ldx     ##0
`?W448`:    txa
            sec
            sbc     1,s
            bvc     `?W1278`
            eor     ##-32768
`?W1278`:   bmi     `?W447`
            ply
            ply
            ply
            ply
            sty     dp:.tiny (_Dp+12)
`?W1431`:   ply
            sty     dp:.tiny (_Dp+10)
            ply
            sty     dp:.tiny (_Dp+8)
            rtl
