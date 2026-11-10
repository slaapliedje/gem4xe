;;; ---------------------------------------------------------------------------
;;; nibs.s -- nib_shift: a row of 4bpp pixels moved by one pixel.
;;;
;;; WHY.  The blitter has no shifter, so a rectangle whose two ends are of
;;; different parity -- a form copied out of a window's work area, whose x
;;; is odd, into a program's memory at x 0, and back -- has every pixel
;;; moved a nibble by the CPU (src/vdi/dev_vbxe.c, copy_rows).  In C that
;;; was a pixel at a time, then a byte at a time at about fifty
;;; instructions a byte: G4BENCH's "screen to memory, back" spent most of
;;; its time there (docs/phase105.md).  Here a byte is a word load, an XBA
;;; and four shifts.
;;;
;;; void nib_shift(uint8_t *dst, const uint8_t *src, uint16_t n)
;;;
;;;     dst[j] = (src[j] << 4) | (src[j + 1] >> 4),   j = 0 .. n - 1
;;;
;;; the low nibble of each source byte and the high nibble of the next: n
;;; destination bytes out of n + 1 source bytes, all in bank $00 (DB).
;;; THE CALL is the compiler's for three 16-bit arguments: dst in A, src in
;;; _Dp+0, n in _Dp+2.  _Dp+0..7 and X, Y are scratch, as to any callee.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .rtmodel codeModel, "large"

              .extern _Dp
              .public nib_shift

ns_src        .equ    _Dp             ; src
ns_n          .equ    _Dp+2           ; n
ns_dst        .equ    _Dp+4           ; dst

              .section farcode, noreorder
nib_shift:    sta     dp:.tiny ns_dst
              ldx     dp:.tiny ns_n
              beq     9$
              ldy     ##0
10$:          lda     (dp:.tiny ns_src),y     ; src[j] low, src[j + 1] high
              xba                             ; src[j] << 8 | src[j + 1]
              lsr     a
              lsr     a
              lsr     a
              lsr     a                       ; the byte wanted, in the low half
              sep     #0x20
              sta     (dp:.tiny ns_dst),y
              rep     #0x20
              iny
              dex
              bne     10$
9$:           rtl

;;; ---------------------------------------------------------------------------
;;; text_row: one row of a string's run, a glyph byte a cell (phase 145).
;;;
;;; WHY.  The VBXE draws a string's visible run as one raster
;;; (src/vdi/dev_vbxe.c, dev_text_run), and that raster is the run's glyph
;;; rows laid side by side.  In C a byte of it was some thirty-five
;;; instructions and a call; here it is twelve.  In this file because the
;;; VBXE device already links it, in every build that has the device.
;;;
;;; void text_row(const WORD *chars, uint16_t n)
;;;
;;;     tr_dst[i] = tr_src[chars[i] & 0xFF],   i = 0 .. n - 1
;;;
;;; tr_src is the face's row and tr_dst the raster's: 24-bit addresses the
;;; caller leaves in the direct page (a .long each), and neither may cross
;;; a bank -- the caller checks the face's row, and the raster is a
;;; far_alloc block, which never does.  chars is in bank $00 (DB).  THE
;;; CALL: chars in A, n in _Dp+0; _Dp+0..7 and X, Y are scratch.
;;; ---------------------------------------------------------------------------

              .public text_row, tr_src, tr_dst

              .section ztiny, bss
tr_src:       .space  4
tr_dst:       .space  4

tr_chars      .equ    _Dp+2           ; chars, walked
tr_out        .equ    _Dp+4           ; tr_dst, walked

              .section farcode, noreorder
text_row:     sta     dp:.tiny tr_chars
              ldx     dp:.tiny _Dp            ; n
              beq     9$
              lda     dp:.tiny tr_dst
              sta     dp:.tiny tr_out
              lda     dp:.tiny (tr_dst+2)
              sta     dp:.tiny (tr_out+2)
10$:          lda     (dp:.tiny tr_chars)     ; chars[i]
              and     ##0xFF
              tay
              sep     #0x20
              lda     [dp:.tiny tr_src],y     ; its byte of this row
              sta     [dp:.tiny tr_out]
              rep     #0x20
              inc     dp:.tiny tr_out
              inc     dp:.tiny tr_chars
              inc     dp:.tiny tr_chars
              dex
              bne     10$
9$:           rtl
