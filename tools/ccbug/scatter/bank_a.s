                .rtmodel version, "1"
                .rtmodel core, "*"
                .public far_a
                .section bankedcode, root
far_a:         lda #1
                rts
                .space 14000, 0xEA
