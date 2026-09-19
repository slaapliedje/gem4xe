                .rtmodel version, "1"
                .rtmodel core, "*"
                .public far_b
                .section bankedcode, root
far_b:         lda #1
                rts
                .space 14000, 0xEA
