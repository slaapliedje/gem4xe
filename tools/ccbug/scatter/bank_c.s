                .rtmodel version, "1"
                .rtmodel core, "*"
                .public far_c
                .section bankedcode, root
far_c:         lda #1
                rts
                .space 14000, 0xEA
