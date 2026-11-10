;;; ---------------------------------------------------------------------------
;;; anpack.s -- an_pack6_s: one row of a string's run, six pixels a cell.
;;;
;;; WHY.  ANTIC draws a string a row at a time (src/antic/antic.c,
;;; antic_text): each row of the run is packed into a buffer, six bits a
;;; cell since the device's face is the 6x6, already shifted to where the
;;; screen byte starts.  In C the packing was half of a text screen's time
;;; (make bench-antic): a shift by the number of bits pending, which on
;;; this CPU is a loop, for every byte it put out (phase 146).  Here each
;;; glyph's six pixels go into the byte being built one at a time -- a
;;; shift, a rotate, a count -- and there is no shift by a variable at all.
;;; The six are written out, not looped: a count would cost as much again.
;;;
;;; In (the direct page, set by an_pack6 in antic.c):
;;;   ap_sr     24-bit address of the face's row (a .long); the row's 256
;;;             bytes, and the one after, in one bank
;;;   ap_chars  the cells' characters, int16 each, bank $00 (DB)
;;;   ap_buf    where the row goes, bank $00
;;;   ap_n      how many cells
;;;   ap_lead   blank pixels before the first, 0..7
;;; Out: buf as an_pack6 always left it -- lead zero bits, then six of each
;;; glyph (its bits 7..2), MSB first, and a last partial byte left-aligned.
;;; X, Y, A and _Dp+0..7 are destroyed, as any callee's.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"

              .extern _Dp
              .public an_pack6_s, ap_sr, ap_chars, ap_buf, ap_n, ap_lead

              .section ztiny, bss
ap_sr:        .space  4
ap_chars:     .space  2
ap_buf:       .space  2
ap_n:         .space  2
ap_lead:      .space  2

ap_g          .equ    _Dp             ; the glyph, in the high byte, shifting
ap_out        .equ    _Dp+2           ; the byte being built, the low byte
ap_bufp       .equ    _Dp+4           ; buf, walked
ap_left       .equ    _Dp+6           ; cells to go


              .section farcode, noreorder
an_pack6_s:   lda     dp:.tiny ap_buf
              sta     dp:.tiny ap_bufp
              stz     dp:.tiny ap_out
              lda     ##8
              sec
              sbc     dp:.tiny ap_lead
              tax                             ; free bits in the byte
              lda     dp:.tiny ap_n
              sta     dp:.tiny ap_left
              bne     10$
              jmp     .kbank 50$              ; no cells
10$:          lda     (dp:.tiny ap_chars)     ; chars[i]
              and     ##0xFF
              tay
              lda     [dp:.tiny ap_sr],y      ; its row: the byte, and the next
              xba                             ; ...the byte in the high half
              and     ##0xFC00                ; its six pixels
              sta     dp:.tiny ap_g
              asl     dp:.tiny ap_g           ; pixel 1: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     21$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
21$:
              asl     dp:.tiny ap_g           ; pixel 2: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     22$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
22$:
              asl     dp:.tiny ap_g           ; pixel 3: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     23$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
23$:
              asl     dp:.tiny ap_g           ; pixel 4: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     24$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
24$:
              asl     dp:.tiny ap_g           ; pixel 5: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     25$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
25$:
              asl     dp:.tiny ap_g           ; pixel 6: the top bit
              rol     dp:.tiny ap_out         ; ...into the byte being built
              dex
              bne     26$
              sep     #0x20                   ; full: stored
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
              inc     dp:.tiny ap_bufp
              ldx     ##8
26$:
              inc     dp:.tiny ap_chars
              inc     dp:.tiny ap_chars
              dec     dp:.tiny ap_left
              beq     50$
              jmp     .kbank 10$              ; six pixels are past a branch's reach
50$:          cpx     ##8                     ; a byte begun and not full
              beq     99$
55$:          asl     dp:.tiny ap_out         ; ...left-aligned
              dex
              bne     55$
              sep     #0x20
              lda     dp:.tiny ap_out
              sta     (dp:.tiny ap_bufp)
              rep     #0x20
99$:          rtl

;;; ---------------------------------------------------------------------------
;;; an_put_row_s: a packed row of the run onto the screen (phase 146).
;;;
;;; WHY.  antic_text put each byte of the row through AN_PUT, the op's mix
;;; worked out in C for every byte: about ten microseconds a byte, of a
;;; screen of text's 6,240, where the write itself is one access on the
;;; 1.79 MHz bus.  Here a middle byte of an op that does not read the
;;; screen -- replace -- is four instructions, and the rest the same mix:
;;;
;;;     t1 = (d & x1) ^ y1,  t0 = (d & x0) ^ y0
;;;     d' = t0 ^ (s & (t1 ^ t0))         the op (antic.c AN_MIX)
;;;     d'' = d ^ (m & (d ^ d'))          inside the mask m only
;;;
;;; In (the direct page, set by antic_text):
;;;   pr_buf    the packed row, bank $00
;;;   pr_scr    the screen byte under buf[0], bank $00
;;;   pr_last   the last byte's index (0 when the run is one byte)
;;;   pr_lm, pr_rm   the first and the last byte's masks
;;;   pr_x1, pr_y1, pr_x0, pr_y0   the op (antic.c AN_OP)
;;; X, Y, A and _Dp+0..7 are destroyed.
;;; ---------------------------------------------------------------------------

              .public an_put_row_s, pr_buf, pr_scr, pr_last, pr_lm, pr_rm
              .public pr_x1, pr_y1, pr_x0, pr_y0

              .section ztiny, bss
pr_buf:       .space  2
pr_scr:       .space  2
pr_last:      .space  2
pr_lm:        .space  1
pr_rm:        .space  1
pr_x1:        .space  1
pr_y1:        .space  1
pr_x0:        .space  1
pr_y0:        .space  1

pr_s          .equ    _Dp             ; the source byte
pr_m          .equ    _Dp+1           ; its mask
pr_d          .equ    _Dp+2           ; the screen byte
pr_t1         .equ    _Dp+3
pr_t0         .equ    _Dp+4
pr_k          .equ    _Dp+5           ; y1 ^ y0, the fast path's

              .section farcode, noreorder
an_put_row_s: sep     #0x20
              lda     dp:.tiny pr_y1
              eor     dp:.tiny pr_y0
              sta     dp:.tiny pr_k
              ldy     ##0
              lda     dp:.tiny pr_lm          ; the first byte
              ldx     dp:.tiny pr_last
              bne     2$
              and     dp:.tiny pr_rm          ; ...which is also the last
2$:           jsr     .kbank 80$
              ldy     ##1
              cpy     dp:.tiny pr_last
              bcs     30$                     ; no middle bytes
              lda     dp:.tiny pr_x1          ; does the op read the screen?
              ora     dp:.tiny pr_x0
              bne     20$
10$:          lda     (dp:.tiny pr_buf),y     ; the fast path: write only
              and     dp:.tiny pr_k
              eor     dp:.tiny pr_y0
              sta     (dp:.tiny pr_scr),y
              iny
              cpy     dp:.tiny pr_last
              bcc     10$
              bra     30$
20$:          lda     #0xFF                   ; the op reads: the whole mix (8-bit A: one #)
              jsr     .kbank 80$
              iny
              cpy     dp:.tiny pr_last
              bcc     20$
30$:          ldy     dp:.tiny pr_last        ; the last byte, if it is not
              beq     39$                     ; ...the first
              lda     dp:.tiny pr_rm
              jsr     .kbank 80$
39$:          rep     #0x20
              rtl

;;; Byte Y through the op under the mask in A (8-bit A, 16-bit Y).
80$:          sta     dp:.tiny pr_m
              lda     (dp:.tiny pr_buf),y
              sta     dp:.tiny pr_s
              lda     (dp:.tiny pr_scr),y
              sta     dp:.tiny pr_d
              and     dp:.tiny pr_x1
              eor     dp:.tiny pr_y1
              sta     dp:.tiny pr_t1
              lda     dp:.tiny pr_d
              and     dp:.tiny pr_x0
              eor     dp:.tiny pr_y0
              sta     dp:.tiny pr_t0
              eor     dp:.tiny pr_t1          ; t1 ^ t0
              and     dp:.tiny pr_s
              eor     dp:.tiny pr_t0          ; d'
              eor     dp:.tiny pr_d           ; d ^ d'
              and     dp:.tiny pr_m
              eor     dp:.tiny pr_d           ; d''
              sta     (dp:.tiny pr_scr),y
              rts
