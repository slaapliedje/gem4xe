; mscan_b23.s -- B23's shape, cc65816 5.18.2 -O2, kept as the fixture that proves
; mscan.stack_zero() can report: one hit, the lda 0,s in idx_of (tools/ccbug/README.md).
idx_of:     phy
            sep     #32
            sta     1,s
            rep     #32
;      WORD idx = (WORD)(code & 0x3F);
            lda     ##63
            and     1,s
            and     ##255
            tax
;      if (code & 0x80) idx += 128;
            lda     0,s
            bpl     `?L4`
            txa
            clc
            adc     ##128
            bra     `?L3`
`?L4`:
;      else if (code & 0x40) idx += 64;
            bit     ##64
            beq     `?L7`
            txa
            clc
            adc     ##64
            bra     `?L3`
`?L7`:      txa
`?L3`:
;      return idx;
;  }
            ply
            rtl
