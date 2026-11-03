; mscan_small.s -- the small code model, where the compiler's outlined
; `?Lnnn` fragments are reached with `jsr` rather than `jsl`: G4DOS's shell
; is built that way (src/shell/, build/sh/).  `narrow` calls a fragment
; that leaves the accumulator 8-bit and then uses a 16-bit immediate -- one
; join reached in the wrong width; `wide`'s fragment puts it back to 16
; bits, the control that must stay silent.  Until mscan followed `jsr` it
; saw neither fragment, reported this nothing, and reported 99 joins and
; 41 saved registers in the shell's real build that were not there
; (2026-11-03): followed, the build is clean and this fixture is not.
narrow:
            jsr     `?L1`
            lda     ##1
            rts
wide:
            jsr     `?L2`
            lda     ##2
            rts
`?L1`:      sep     #32
            rts
`?L2`:      sep     #32
            rep     #32
            rts
