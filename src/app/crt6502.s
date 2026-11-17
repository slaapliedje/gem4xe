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
;;; ITS OWN C STACK (step 5b-3), at the top of its bank: the `cstack`
;;; block gemapp6502.scm places there.  The system's C stack is 1 KB of
;;; resident memory that every system call needs all of, so a program does
;;; not run on it.  start keeps the system's _Vsp in g6_sysvsp and moves
;;; to its own; each call into the system (gemabi6502.s) moves back to the
;;; one kept here for the call and to the program's after; and when main
;;; returns, start puts the system's back.  Page 1 is still the
;;; system's, shared, as a process switch copies it in and out.  A local's
;;; address is a window address, which the system turns into this bank's
;;; far address like any other (src/sys/abi.c, win_far).
;;;
;;; It initializes its own sections, as Calypsi's start-up does, through
;;; the runtime's __initialize_sections and the table the link makes,
;;; calls main() and returns what main returned (_Zp0-1).
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, _Vsp, main, __initialize_sections
              .public __program_root_section, g6_sysvsp

              .section data_init_table
              .section cstack

              .section header, root, noreorder
__program_root_section:
              .byte   'G', '6', 1
              jmp     start

              .section zdata, bss
g6_sysvsp:    .space  2               ; the system's _Vsp (gemabi6502.s)

              .section code
start:        lda     zp:_Vsp+1       ; the system's, on page 1 until the
              pha                     ; sections are set up: g6_sysvsp is
              lda     zp:_Vsp         ; bss, which that zeroes
              pha
              lda     #.byte0 (.sectionEnd cstack)
              sta     zp:_Vsp
              lda     #.byte1 (.sectionEnd cstack)
              sta     zp:_Vsp+1
              lda     #.byte0 (.sectionStart data_init_table)
              sta     zp:_Zp+0
              lda     #.byte1 (.sectionStart data_init_table)
              sta     zp:_Zp+1
              lda     #.byte0 (.sectionEnd data_init_table)
              sta     zp:_Zp+2
              lda     #.byte1 (.sectionEnd data_init_table)
              sta     zp:_Zp+3
              jsr     __initialize_sections
              pla
              sta     g6_sysvsp
              pla
              sta     g6_sysvsp+1
              jsr     main
              lda     g6_sysvsp       ; main's answer, in _Zp0-1, kept
              sta     zp:_Vsp
              lda     g6_sysvsp+1
              sta     zp:_Vsp+1
              rts
