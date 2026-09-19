/* vbxe.h -- VBXE FX 1.2x register map and the gem4xe VRAM layout.
 *
 * Register offsets are within the FX page ($D600 or $D700); the base is
 * detected at runtime because U1MB selects it (UAUX $D381 bits D5:D4) and it
 * must never be hard-coded.  Verified against Altirra's vbxe.cpp and the
 * working map in ~/dev/vbxetxtadv/src/vbxe/vbxe.inc.
 *
 * Do NOT use the VBXE tables in ~/.claude/skills/atari8bit/exotics/vbxe.md --
 * sections 15.3 and 15.7 there are wrong, independently confirmed twice.
 */
#ifndef GEM4XE_VBXE_H
#define GEM4XE_VBXE_H

#include <stdint.h>

/* ---- registers, as offsets from the FX page base ---------------------- */
#define FX_VIDEO_CONTROL   0x40   /* W */
#define FX_CORE_REVISION   0x40   /* R  low nibble 0 = full FX, high = major  */
#define FX_XDL_ADR0        0x41   /* W  (R = MINOR_REVISION, BCD)             */
#define FX_MINOR_REVISION  0x41   /* R */
#define FX_XDL_ADR1        0x42
#define FX_XDL_ADR2        0x43
#define FX_CSEL            0x44   /* colour index; CB write auto-increments   */
#define FX_PSEL            0x45   /* palette 0-3                              */
#define FX_CR              0x46   /* D7:D1 significant                        */
#define FX_CG              0x47
#define FX_CB              0x48   /* writing this bumps CSEL                  */
#define FX_COLMASK         0x49
#define FX_COLDETECT       0x4A   /* R */
#define FX_COLCLR          0x4A   /* W (strobe) */
#define FX_BL_ADR0         0x50   /* W  (R = BLT_COLLISION_CODE)              */
#define FX_BL_ADR1         0x51
#define FX_BL_ADR2         0x52
#define FX_BLITTER_START   0x53   /* W  D0: 1 start, 0 stop                   */
#define FX_BLITTER_BUSY    0x53   /* R  D1 BUSY, D0 BCB_LOAD; idle = 0        */
#define FX_IRQ_CONTROL     0x54   /* W  D0 enable; ANY write acknowledges     */
#define FX_IRQ_STATUS      0x54   /* R  D0 active                             */
#define FX_P0              0x55   /* priority registers, used by the attr map */
#define FX_MEMAC_B_CONTROL 0x5D   /* write-only; UNUSED -- U1MB wins at $4000 */
#define FX_MEMAC_CONTROL   0x5E
#define FX_MEMAC_BANK_SEL  0x5F

/* VIDEO_CONTROL bits */
#define VC_XDL_ENABLE      0x01
#define VC_XCOLOR          0x02
#define VC_NO_TRANS        0x04   /* 1 = no index is transparent              */
#define VC_TRANS15         0x08

/* XDL control word (little-endian 16 bits) */
#define XDLC_TMON          0x0001
#define XDLC_GMON          0x0002
#define XDLC_OVOFF         0x0004
#define XDLC_MAPON         0x0008
#define XDLC_MAPOFF        0x0010
#define XDLC_RPTL          0x0020
#define XDLC_OVADR         0x0040
#define XDLC_OVSCRL        0x0080
#define XDLC_CHBASE        0x0100
#define XDLC_MAPADR        0x0200
#define XDLC_MAPPAR        0x0400
#define XDLC_OVATT         0x0800
#define XDLC_HR            0x1000
#define XDLC_LR            0x2000
#define XDLC_END           0x8000

/* OVATT byte 0: D7:D6 playfield palette, D5:D4 overlay palette,
 *               D1:D0 width (00/11 narrow, 01 normal, 10 wide)          */
#define OVATT_OVPAL(n)     ((uint8_t)((n) << 4))
/* The three the hardware has.  In HR each colour clock is four pixels,
 * so the widths the overlay actually occupies come straight out of the
 * bounds the core renders between -- narrow $40-$BF is 128 colour
 * clocks, normal $30-$CF is 160, wide $2C-$D4 is 168 -- which is 512,
 * 640 and 672 pixels (Altirra vbxe.cpp kBounds; the wide bounds are NOT
 * ANTIC's, which is worth knowing before reusing a playfield number).
 * The encoding has a hole in it: 11 is narrow again, not a fourth
 * width. */
#define OVATT_WIDTH_NARROW 0x00
#define OVATT_WIDTH_NORMAL 0x01
#define OVATT_WIDTH_WIDE   0x02
#define VB_W_NARROW        512
#define VB_W_NORMAL        640
#define VB_W_WIDE          672
/* OVATT byte 1 is the priority mask.  ALWAYS $FF: bits 6/7 changed meaning
 * between FX 1.24 and 1.26, and a priority of $00 renders normally on 1.24
 * but makes the overlay VANISH on 1.26 (bit 7 became COLBAK).            */
#define OVATT_PRI_OVER_ALL 0xFF

/* ---- blitter --------------------------------------------------------- */
#define BCB_SIZE           21     /* 21 on FX 1.2x; 19 on pre-1.20 cores    */
#define BLT_MODE_COPY      0      /* no transparency, no collisions         */
#define BLT_MODE_TRANS     1      /* byte stencil: skip source == 0         */
#define BLT_MODE_ADD       2
#define BLT_MODE_OR        3
#define BLT_MODE_AND       4
#define BLT_MODE_XOR       5
#define BLT_MODE_HR        6      /* NIBBLE stencil -- the 4bpp HR mode     */
#define BLT_NEXT           0x08   /* run the physically next BCB            */
#define BLT_MAX_WIDTH      512    /* width field is NINE bits (1..512)      */

/* ---- display geometry ------------------------------------------------ */
/* HR is 4bpp: 2 pixels per byte, high nibble = LEFT pixel.
 *
 * VB_, the way the other device's are AN_ (src/antic/antic.h).  These are
 * THIS DEVICE'S numbers, and a program that has both linked cannot use
 * either as "the screen": that is vdev->w and vdev->h, which is what the
 * VDI reads as VB_W and VB_H (src/vdi/vdidev.h). */
#define VB_W               640
#define VB_H               240
#define VB_STRIDE          (VB_W / 2)           /* 320 bytes per row        */
#define VB_BYTES           ((uint32_t)VB_STRIDE * VB_H)     /* 76,800       */

/* ---- VRAM map (512 KB) ----------------------------------------------- */
#define VR_SCREEN0         0x00000UL            /* 76,800 -> $12BFF         */
#define VR_SCREEN1         0x13000UL            /* 76,800 -> $25BFF         */
#define VR_XDL             0x30000UL            /* 256                      */
#define VR_BCB             0x30100UL            /* blit control blocks, 1K  */
#define VR_CURSAVE         0x30200UL            /* 16x16 under the pointer  */
#define VR_CURSAVE_STRIDE  16
#define VR_CURSAVE_ROWS    16
/* The current fill pattern, expanded to 4bpp: 16 rows of one 16-pixel repeat
 * written TWICE per row, so a blit may start at any byte of the repeat and
 * read eight bytes before the pattern counter wraps it (see blit_pattern).
 * It follows the cursor save area, however large that is.                */
#define VR_PATT            (VR_CURSAVE + (uint32_t)VR_CURSAVE_STRIDE * VR_CURSAVE_ROWS)
#define VR_PATT_STRIDE     16
#define VR_PATT_ROWS       16
/* Styled lines (src/vdi/vdi.c, style_line): one row of the style, written
 * twice like a pattern row, for a horizontal line; then a 16-byte column --
 * one byte per row, all-set or all-clear -- replicated by the blitter to
 * VR_LINE_V_ROWS, so a vertical line of any screen height is one blit. */
#define VR_LINE_H          (VR_PATT + (uint32_t)VR_PATT_STRIDE * VR_PATT_ROWS)
#define VR_LINE_V          (VR_LINE_H + VR_PATT_STRIDE)
#define VR_LINE_V_ROWS     256
/* The pointer form as blit sources (src/vdi/vdi.c, cursor_expand): for each
 * parity of x an AND strip and an OR strip, VR_CURSOR_ROWS rows of
 * VR_CURSOR_STRIDE bytes -- four strips, written through one MEMAC mapping,
 * so they follow the line strips at the next 256-byte boundary and must not
 * straddle a page (vdi.c checks).  A show is then the save copy and two
 * blits wherever the pointer is; see the note above cursor_expand.        */
#define VR_CURSOR          ((VR_LINE_V + VR_LINE_V_ROWS + 0xFFUL) & ~0xFFUL)
#define VR_CURSOR_STRIDE   16
#define VR_CURSOR_ROWS     16
#define VR_CURSOR_LEN      ((uint32_t)VR_CURSOR_STRIDE * VR_CURSOR_ROWS * 4)
#define VR_FONT            0x31000UL            /* 4bpp glyph masks, both
                                                   parities: 18 KB -> $357FF */
/* The AES's save buffer for menu drop-downs and alerts (bb_save /
 * bb_restore): a whole screen's worth, laid out exactly like the screen, so
 * a save is a same-coordinates vro_cpyfm between the two and always a blit.
 * The donor keeps 25 character columns by the screen height and overflows
 * on a wider drop-down; a full screen costs nothing here.               */
#define VR_SAVE            0x40000UL            /* 76,800 -> $52BFF         */
/* Scratch for vrt_cpyfm (src/vdi/vdi.c): a monochrome form expanded to 4bpp
 * AND and OR strips, half a page each, written through one MEMAC mapping
 * and blitted in bands.  The first page boundary after the save buffer.  */
#define VR_STRIP           ((VR_SAVE + VB_BYTES + 0xFFFUL) & ~0xFFFUL)
#define VR_STRIP_LEN       0x1000UL
/* VR_STRIP + VR_STRIP_LEN onward is free: window backing stores, icons */

/* ---- MEMAC A window --------------------------------------------------- */
/* 4 KB at $8000.  NOT MEMAC B: that is fixed at $4000-$7FFF, where U1MB's
 * extended memory overrides it.  src/gem4xe.scm reserves both regions.    */
#define MEMAC_WIN_ADDR     0x8000
#define MEMAC_WIN_SIZE     0x1000
#define MEMAC_CTL_4K_8000  0x88   /* base $8000, CPU enable, 4K            */

/* ---- API -------------------------------------------------------------- */
extern uint16_t vbxe_base;        /* $D600 or $D700; 0 until vbxe_detect()  */

uint8_t  vbxe_detect(void);       /* 1 if a full FX core >= 1.20 was found  */
uint8_t  vbxe_major(void);
uint8_t  vbxe_minor_bcd(void);

void     vbxe_reg(uint8_t off, uint8_t val);
uint8_t  vbxe_reg_read(uint8_t off);

void     vram_map(uint32_t addr);                     /* window the 4K page */
void     vram_map_page(uint8_t page);                 /* ... by page number  */
void     vram_unmap(void);                            /* closed until the next
                                                         vram_map: RAM lent to
                                                         a DOS command */
/* Map a 4K page and hand back a pointer into the window, so a bulk writer can
 * stream with 16-bit pointer arithmetic instead of paying 32-bit address
 * maths per byte.  Valid until the next vram_* call or blit. */
volatile uint8_t *vram_win(uint32_t addr);
void     vram_write(uint32_t addr, const uint8_t *src, uint16_t len);
void     vram_fill(uint32_t addr, uint8_t val, uint16_t len);
uint8_t  vram_read8(uint32_t addr);

void     vbxe_palette(uint8_t pal, uint8_t first, const uint8_t *rgb, uint16_t count);
/* `ovatt_width` is one of OVATT_WIDTH_*; the picture is VB_W_* pixels
 * across and the caller's screen memory has to be strided to match. */
void     vbxe_xdl_hr(uint32_t screen, uint16_t height, uint8_t topmargin,
                     uint8_t ovatt_width);
void     vbxe_off(void);                              /* overlay and MEMAC off */
void     vbxe_wait_vbl(void);

/* Blitter.  The blit list must be CONTIGUOUS in VRAM -- there is no jump
 * instruction, only a "run the next BCB" bit. */
void     blit_reset(void);                            /* start a new list    */
void     blit_fill(uint32_t dst, uint16_t stride, uint16_t bytes,
                   uint16_t rows, uint8_t value);
void     blit_copy(uint32_t src, uint16_t sstride, uint32_t dst,
                   uint16_t dstride, uint16_t bytes, uint16_t rows);
/* A copy whose source and destination may overlap (a window being moved):
 * runs backwards, from the last byte of the last row, when the destination
 * is the higher address.  The BCB's steps are signed -- X a byte, Y 13
 * bits -- which is what makes it one blit either way. */
void     blit_move(uint32_t src, uint16_t sstride, uint32_t dst,
                   uint16_t dstride, uint16_t bytes, uint16_t rows);
/* Read-modify-write with a constant source.  Used for the odd-nibble edges of
 * a 4bpp rectangle: AND away the nibble to keep, then OR the colour in. */
void     blit_and(uint32_t dst, uint16_t stride, uint16_t bytes,
                  uint16_t rows, uint8_t mask);
void     blit_or(uint32_t dst, uint16_t stride, uint16_t bytes,
                 uint16_t rows, uint8_t bits);
void     blit_xor(uint32_t dst, uint16_t stride, uint16_t bytes,
                  uint16_t rows, uint8_t bits);
void     vram_write8(uint32_t addr, uint8_t v);
/* Blit from a VRAM source through explicit AND/XOR masks in any mode.  The
 * text path uses it twice per glyph: AND to clear the ink pixels, OR to paint
 * them.  See draw_glyph() in src/vdi/vdi.c for why that pair. */
void     blit_mask(uint32_t src, uint16_t sstride, uint32_t dst,
                   uint16_t dstride, uint16_t bytes, uint16_t rows,
                   uint8_t and_mask, uint8_t xor_mask, uint8_t mode);
/* blit_mask with the source read cyclically: after `repeat` bytes the source
 * pointer returns to the START OF THE CURRENT ROW (not to the byte the row's
 * read began at), so the repeat unit must be laid out from the row start.
 * How a small pattern tile fills any width in one control block. 1..64. */
void     blit_pattern(uint32_t src, uint16_t sstride, uint32_t dst,
                      uint16_t dstride, uint16_t bytes, uint16_t rows,
                      uint8_t and_mask, uint8_t xor_mask, uint8_t mode,
                      uint8_t repeat);
uint8_t  blit_pending(void);
void     blit_run(void);                              /* upload, start, wait */
void     blit_start(void);                            /* upload and start only */
uint8_t  blit_busy(void);                             /* non-zero while running */
uint16_t blit_time(void);   /* run the queued list, return elapsed VCOUNT ticks
                               (1 tick = 2 scanlines); PAL frame = 156 ticks   */

#endif /* GEM4XE_VBXE_H */
