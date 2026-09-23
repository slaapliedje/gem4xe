;;; ---------------------------------------------------------------------------
;;; blkmove.s -- MVN, the 65816's block move, across banks.
;;;
;;; WHY.  src/sys/farmem.c moves memory a byte at a time through a far
;;; pointer, which is what the C language offers and costs what
;;; docs/bench.md measures.  The CPU has an instruction for this: MVN
;;; moves a run of bytes from one bank to another at a documented 7
;;; cycles a byte, and nothing in this tree used it.
;;;
;;; That number decides something.  Holding more than one application
;;; resident means parking a near region in the 14.9 MB and bringing it
;;; back (docs/multitasking.md), and whether that is affordable at a
;;; timer tick is exactly the cost of a few kilobytes of block move.  So
;;; this exists to be MEASURED first and used second.
;;;
;;; THE BANKS ARE IN THE INSTRUCTION, not in a register, so a routine
;;; that moves between banks chosen at run time has to write its own MVN.
;;; The stub is four bytes of bank-$00 RAM -- opcode, destination bank,
;;; source bank, RTL -- built on every call and called with a JSL.
;;;
;;; AND THE OPERAND ORDER IS BACKWARDS from the assembly syntax: `MVN
;;; src,dst` assembles to $54, DST, SRC.  Getting that the wrong way
;;; round moves real bytes to a real place and is not diagnosed by
;;; anything, so blk_check() below exists to say which way round it is
;;; rather than leaving it to be remembered.
;;;
;;; MVN SETS DB to the destination bank as a side effect -- src/sys/irq.s
;;; already knows this, being written to survive an interrupt taken in
;;; the middle of one -- so DB is pushed and popped around it.
;;;
;;; In:  blk_src, blk_dst   24-bit addresses (a .long each, low word first)
;;;      blk_len            bytes, 1..65535.  ZERO WOULD MOVE 65536: MVN
;;;                         takes a count of A+1 and there is no way to
;;;                         say nothing, so a zero length returns having
;;;                         done nothing rather than wrapping the bank.
;;; Out: nothing.  X, Y and A are destroyed, as the library's are.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"
              .rtmodel dataModel, "small"

              .public blk_move, blk_src, blk_dst, blk_len

;;; The parameters are globals rather than arguments on purpose: this is
;;; called from C compiled in two data models and the measurement wanted
;;; one shape, not an ABI argument.  Bank $00, absolute through DB, which
;;; is where a small-data global lives.
              .section zdata, bss
blk_src:      .space  4
blk_dst:      .space  4
blk_len:      .space  2
;;; ...and the instruction this writes and then runs.  RAM, because code
;;; in this build lives in a far bank the loader staged there and the
;;; point is to modify it.
blk_stub:     .space  4

              .section farcode, noreorder
blk_move:     lda     blk_len
              beq     9$              ; see the header: 0 is not 65536 here
              phb
              sep     #0x20           ; 8-bit A to lay the instruction down
              lda     #0x54           ; MVN.  ONE #: `##` is a 16-bit immediate
              sta     blk_stub
              lda     blk_dst+2       ; ...DESTINATION bank first: $54 dst src
              sta     blk_stub+1
              lda     blk_src+2
              sta     blk_stub+2
              lda     #0x6b           ; RTL
              sta     blk_stub+3
              rep     #0x20
              ldx     blk_src         ; source offset
              ldy     blk_dst         ; destination offset
              lda     blk_len
              dec     a               ; MVN moves A+1
              jsl     blk_stub
              plb                     ; MVN left DB on the destination bank
9$:           rtl
