                .rtmodel version, "1"
                .rtmodel core, "*"
                .extern far_a, far_b, far_c
                .public runtime_addr, storage_addr

                .section code, root
runtime_addr:   .word far_a, far_b, far_c                    ; where it RUNS
storage_addr:   .long .scatterTo28 far_a
                .long .scatterTo28 far_b
                .long .scatterTo28 far_c
