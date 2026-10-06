;;; B23's wide form: src/vdi/vdi.c's kb_queue as cc65816 5.18.2 compiled it at
;;; -O2 before phase 107.  `lda 7,s` reads a byte the function stored 8
;;; bits wide, then `inc a; dec a; bmi` tests bit 15 -- the stray byte above.
;;; mscan.stray_sign() must find exactly one site here.
kb_queue:   phy
            phy
            phy
            phy
            sep     #32
            sta     7,s
            rep     #32
            lda     121
            sta     3,s
            lda     ##63
            and     7,s
            and     ##255
            sta     5,s
            sta     1,s
            cmp     ##3
            bne     `?L3367`
            jmp     .kbank `?L1814`
`?L3367`:   cmp     ##4
            bne     `?L3368`
            jmp     .kbank `?L1813`
`?L3368`:   cmp     ##17
            bne     `?L3369`
            jmp     .kbank `?L1814`
`?L3369`:   lda     7,s
            sep     #32
            rol     a
            rol     a
            rol     a
            and     #3
            rep     #32
            and     ##255
            sta     1,s
            cmp     ##3
            bne     `?L1820`
            lda     ##2
            sta     1,s
`?L1820`:   lda     1,s
            asl     a
            asl     a
            asl     a
            asl     a
            asl     a
            asl     a
            clc
            adc     5,s
            sta     1,s
            lda     3,s
            tay
            lda     (1,s),y
            sep     #32
            sta     5,s
            rep     #32
            lda     7,s
            bit     ##192
            bne     `?L1822`
            sep     #32
            lda     kb_caps
            rep     #32
            beq     `?L1822`
            lda     5,s
            sep     #32
            cmp     #97
            rep     #32
            bcc     `?L1822`
            lda     ##122
            sep     #32
            cmp     5,s
            rep     #32
            bcc     `?L1822`
            lda     ##64
            clc
            adc     1,s
            tay
            lda     (3,s),y
            sep     #32
            sta     1,s
            bra     `?L2949`
`?L1822`:   sep     #32
            lda     5,s
            sta     1,s
`?L2949`:   rep     #32
            lda     ##.word0 `?L1860`
            sta     dp:.tiny _Dp
            lda     ##.word2 `?L1860`
            sta     dp:.tiny (_Dp+2)
            lda     1,s
            and     ##255
            jsl     long:_ValueSwitch16
`?L1830`:   lda     ##0x537f
            sta     1,s
            jmp     .kbank `?L1809`
`?L1838`:   lda     ##0x1c0d
            sta     1,s
            jmp     .kbank `?L1809`
`?L1828`:   sep     #32
            lda     #1
            sta     kb_caps
            rep     #32
            lda     ##0
            sta     1,s
            jmp     .kbank `?L1809`
`?L1829`:   sep     #32
            lda     #1
            eor     kb_caps
            sta     kb_caps
            rep     #32
            lda     ##0
            sta     1,s
            bra     `?L1809`
`?L1837`:   lda     ##0xf09
            sta     1,s
            bra     `?L1809`
`?L1836`:   lda     ##0xe08
            sta     1,s
            bra     `?L1809`
`?L1831`:   lda     ##0x4d00
            sta     1,s
            bra     `?L1809`
`?L1832`:   lda     ##0x4b00
            sta     1,s
            bra     `?L1809`
`?L1833`:   lda     ##0x5000
            sta     1,s
            bra     `?L1809`
`?L1834`:   lda     ##0x4800
            sta     1,s
            bra     `?L1809`
`?L1835`:   lda     ##0x11b
            sta     1,s
            bra     `?L1809`
`?L1827`:   lda     1,s
            sep     #32
            cmp     #-128
            rep     #32
            bcs     `?L1858`
            lda     ##63
            and     7,s
            and     ##255
            tax
            lda     long:kb_st,x
            and     ##255
            xba
            and     ##-256
            sta     dp:.tiny _Dp
            lda     1,s
            and     ##255
            ora     dp:.tiny _Dp
            sta     1,s
            bra     `?L1809`
`?L1858`:   lda     ##0
            sta     1,s
            bra     `?L1809`
`?L1813`:   lda     ##0x6100
            sta     1,s
            bra     `?L1809`
`?L1814`:   lda     ##0x6200
            sta     1,s
`?L1809`:
            lda     kb_tail
            inc     a
            and     ##7
            sep     #32
            sta     3,s
            rep     #32
            lda     1,s
            beq     `?L1293`
            lda     3,s
            sep     #32
            cmp     kb_head
            rep     #32
            beq     `?L1293`
            lda     kb_tail
            and     ##255
            asl     a
            tax
            lda     1,s
            sta     kb_q,x
            lda     7,s
            bit     ##64
            bne     `?L1681`
            ldx     ##0
            bra     `?L1682`
`?L1681`:   ldx     ##2
`?L1682`:   inc     a
            dec     a
            bmi     `?L1684`
            ldy     ##0
            bra     `?L1685`
`?L1684`:   ldy     ##4
`?L1685`:   txa
            sta     dp:.tiny _Dp
            tya
            ora     dp:.tiny _Dp
            pha
            lda     kb_tail
            and     ##255
            tax
            pla
            sep     #32
            sta     kb_m,x
            lda     3,s
            sta     kb_tail
            rep     #32
`?L1293`:   ply
            ply
            ply
            ply
            rtl
