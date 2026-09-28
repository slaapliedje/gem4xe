;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; crt_gemapp.s -- the start-up of a gem4xe application.
;;;
;;; An application is a far subroutine of gem4xe's: the loader (src/sys/app.c)
;;; puts its near region somewhere in bank $00 and its far code in a bank of
;;; its own, then `jsl`s here in native mode with 16-bit registers and
;;; gem4xe's own S, D and DB.  This does what the library's cstartup does --
;;; a stack, a direct page, DB = $00, the data sections initialised, main --
;;; but keeps what it found and puts it back, so that main's return is the
;;; application's exit and the `rtl` lands in the loader with main's value
;;; in A.  What it found is kept on the application's own stack, not in a
;;; variable: every data section is initialised after it is saved, and a
;;; zeroed zdata word was the first thing that returned into nowhere.
;;; It replaces the library's cstartup rather than adding to it:
;;; __program_root_section and __program_start are defined here, so the
;;; linker never pulls the library's, whose `clc xce` and reset vector have
;;; no place inside a running program.
;;;
;;; The order at entry matters to the ABI: gem4xe's S is recorded as the jsl
;;; left it and nothing is pushed on gem4xe's stack before this side takes
;;; its own.  src/sys/abi.s records the same S as gem_api_sp, the stack a
;;; COP from the application is served on; anything pushed here first
;;; would sit exactly where that stack begins.
;;;
;;; Everything here is position-independent by fixup, not by construction:
;;; the immediates that name the stack, the direct page and the init table
;;; are patched by the loader from the fixup lists tools/mkg4a.py derived
;;; by linking the program at two addresses and comparing.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel core, "*"
              .rtmodel cstartup, "gemapp"

              .extern main, _Dp, _Vfp, _DirectPageStart
              .extern __initialize_sections
              .section stack
              .section data_init_table
              .public __program_root_section, __program_start
              ;; The runtime looks for these three by name to know that a
              ;; C start-up is present; here they are all the same place.
              .pubweak __data_initialization_needed
              .pubweak __call_initialize_global_streams
              .pubweak __call_heap_initialize

              .section farcode, root, noreorder
__program_root_section:
__program_start:
              tsc
              tay                     ; gem4xe's S, held until ours is up
              ldx     ##.sectionEnd stack
              txs                     ; our own stack from here on
              phy                     ; gem4xe's S, D and DB, on it
              phd
              phb
              lda     ##_DirectPageStart
              tcd
              lda     ##0
              stz     dp:.tiny(_Vfp+2)
              pha
              plb                     ; DB = $00 ...
              plb                     ; ... and the high byte discarded
__data_initialization_needed:
__call_initialize_global_streams:
__call_heap_initialize:
              lda     ##.word2 (.sectionEnd data_init_table)
              sta     dp:.tiny(_Dp+6)
              lda     ##.word0 (.sectionEnd data_init_table)
              sta     dp:.tiny(_Dp+4)
              lda     ##.word2 (.sectionStart data_init_table)
              sta     dp:.tiny(_Dp+2)
              lda     ##.word0 (.sectionStart data_init_table)
              sta     dp:.tiny(_Dp+0)
              jsl     __initialize_sections
              lda     ##0             ; argc
              jsl     main
              tax                     ; main's return value
              plb                     ; gem4xe's DB ...
              pld                     ; ... direct page ...
              ply                     ; ... and stack
              tya
              tcs
              txa
              rtl
