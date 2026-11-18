;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; crt6502m.s -- the start of a 6502 application of SEVERAL banks
;;; (docs/6502.md, step 5c-1); crt6502.s is a one-bank program's.
;;;
;;; ITS CODE is in banks 1..n of its own, each a 16 KB bank the system
;;; took from the far heap and shows at $4000-$7FFF; its veneers, the
;;; runtime's code, its constants, data, heap and C stack are in the RAM
;;; under the OS ROM (src/app/gemappm6502.scm), which every one of its
;;; banks can see: the system runs with that RAM in (src/a6_tree.c).
;;; Bank 1 begins with the header the system checks:
;;;
;;;   $4000  "G6"       the magic
;;;   $4002  2          the format: several banks
;;;   $4003  JMP start  the entry, which the system calls with bank 1 in
;;;
;;; THE LINK BLOCK, at $C000, which the loader fills (src/a6_evt.c):
;;;
;;;   $C000  g6_banks   [k] the system's bank index of program bank k
;;;   $C010  g6_l_cur   the address of b6_cur, the bank the system thinks
;;;                     is in: its gate maps that one back on return
;;;   $C012  g6_l_tab   the address of b6_portb, PORTB per bank index
;;;   $C014  g6_l_kind  'P' PORTB's banks, 'A' an Axlon's ($CFFF)
;;;
;;; start writes the two addresses into _pcall's own instructions, so a
;;; cross-bank call costs no indirection.  It keeps the system's _Vsp in
;;; g6_sysvsp and runs on its own C stack, as crt6502.s does
;;; (gemabi6502.s swaps them around each call into the system).
;;;
;;; _pcall IS THE PROGRAM'S _bcall (src/sys6502/bank6502.s), with the
;;; program's bank numbers -- tools/bsp6502/bankasm.py --trampoline:
;;;
;;;     F:  jsr _pcall
;;;         .word F__b      ; the function, at its window address
;;;         .byte k         ; the program's bank, 1..n
;;;
;;; It maps g6_banks[k], keeping b6_cur true, calls F, and maps the
;;; caller's bank back.  A and the _Zp pseudo-registers pass through both
;;; ways.  Its scratch is its own: nothing else runs program code while it
;;; is in it (an interrupt is the system's; a process switch happens only
;;; inside a gate call), and a nested call is done with pc_t and pc_a
;;; before it makes its own.  ROM is out throughout: PORTB's values in
;;; b6_portb have bit 0 clear, and on an Axlon PORTB is not written.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp, _Vsp, main, __initialize_sections
              .public __program_root_section, g6_sysvsp, _pcall
              .public g6_banks, g6_l_cur, g6_l_tab, g6_l_kind

PORTB:        .equ    0xd301
AXLON:        .equ    0xcfff

              .section data_init_table
              .section cstack

              .section g6link, root, noreorder
g6_banks:     .space  16
g6_l_cur:     .space  2
g6_l_tab:     .space  2
g6_l_kind:    .space  1

;;; the header and start, one section fixed at $4000 in bank 1: a `root`
;;; section in a memory that is scattered to its store crashes the 5.18
;;; linker ("Placement.hs: Non-exhaustive patterns"), so not that
              .section g6start, text
__program_root_section:
              .byte   'G', '6', 2
              jmp     start

;;; in bank 1, right after the header, in the same fragment: the linker
;;; does not keep two fragments of one section in order
start:        lda     zp:_Vsp+1       ; the system's: g6_sysvsp is bss,
              pha                     ; which the sections' set-up zeroes
              lda     zp:_Vsp
              pha
              lda     g6_l_cur        ; the system's addresses, into
              sta     pc_cur1+1       ; _pcall's instructions
              sta     pc_cur2+1
              lda     g6_l_cur+1
              sta     pc_cur1+2
              sta     pc_cur2+2
              lda     g6_l_tab
              sta     pc_tab1+1
              sta     pc_tab2+1
              lda     g6_l_tab+1
              sta     pc_tab1+2
              sta     pc_tab2+2
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
              jsr     main            ; its veneer, in the shared RAM
              lda     g6_sysvsp       ; main's answer, in _Zp0-1, kept
              sta     zp:_Vsp
              lda     g6_sysvsp+1
              sta     zp:_Vsp+1
              rts

;;; ---------------------------------------------------------------------------
;;; _pcall -- see the head of the file.  In the shared RAM, and written
;;; into: pc_ld's operand is the veneer, the others the system's addresses.
;;; ---------------------------------------------------------------------------
              .section code
_pcall:       sta     pc_a
              pla                     ; JSR's return: the veneer's data - 1
              sta     pc_ld+1
              pla
              sta     pc_ld+2
              ldy     #3
pc_ld:        lda     0xffff,y        ; data - 1 + 3, + 2, + 1
              sta     pc_t-1,y        ; pc_t: the function, then k
              dey
              bne     pc_ld
              ldx     pc_t+2
              lda     g6_banks,x      ; k -> the system's bank index
              tax
pc_cur1:      lda     0xffff          ; b6_cur: the caller's, kept on the
              pha                     ; 6502 stack under the return
              jsr     pc_map
              lda     pc_a
              jsr     pc_go           ; the call
              sta     pc_a
              pla
              tax
              jsr     pc_map
              lda     pc_a
              rts                     ; to the veneer's caller
pc_go:        jmp     (pc_t)
pc_map:
pc_cur2:      stx     0xffff          ; b6_cur
              lda     g6_l_kind
              cmp     #'A'
              beq     pc_ax
pc_tab1:      lda     0xffff,x        ; b6_portb: PORTB, the ROM bit clear
              sta     PORTB
              rts
pc_ax:
pc_tab2:      lda     0xffff,x        ; an Axlon's bank number
              sta     AXLON
              rts

              .section zdata, bss
g6_sysvsp:    .space  2               ; the system's _Vsp (gemabi6502.s)
pc_a:         .space  1               ; A across the switch
;;; JMP (pc_t) reads its operand's high byte from the same page: the
;;; 6502 takes $xx00 for $xxFF+1, so pc_t must not end a page
              .align  2
pc_t:         .space  3               ; the function, and the program's bank
