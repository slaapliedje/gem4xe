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
