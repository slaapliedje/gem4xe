;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; crt6502.s -- a 6502 application's start (docs/6502.md, step 5).
;;;
;;; The program is one 16 KB bank at $4000-$7FFF (gemapp6502.scm), and it
;;; begins with a header the system checks before it runs anything:
;;;
;;;   $4000  "G6"       the magic
;;;   $4002  1          the format
;;;   $4003  JMP start  the entry, which the system calls with the bank in
;;;
;;; It runs on the SYSTEM'S stacks -- page 1 and the C stack under _Vsp,
;;; which a process switch copies in and out -- so nothing here sets
;;; either.  It initializes its own sections, as Calypsi's start-up does,
;;; through the runtime's __initialize_sections and the table the link
;;; makes, calls main() and returns what main returned (A, _Zp0-1).
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, main, __initialize_sections
              .public __program_root_section

              .section data_init_table

              .section header, root, noreorder
__program_root_section:
              .byte   'G', '6', 1
              jmp     start

              .section code
start:        lda     #.byte0 (.sectionStart data_init_table)
              sta     zp:_Zp+0
              lda     #.byte1 (.sectionStart data_init_table)
              sta     zp:_Zp+1
              lda     #.byte0 (.sectionEnd data_init_table)
              sta     zp:_Zp+2
              lda     #.byte1 (.sectionEnd data_init_table)
              sta     zp:_Zp+3
              jsr     __initialize_sections
              jmp     main
