/* antic.h -- the secondary display: stock ANTIC and GTIA, no VBXE.
 *
 * ANTIC mode F (GRAPHICS 8): 320 pixels a line, ONE bit each, 40 bytes a
 * line, scanline-sequential with no character-cell indirection.  It is
 * the surface the VDI's second driver rasterises into, and the thing
 * that stops the VBXE's assumptions leaking into portable code.
 *
 * WHERE IT LIVES, AND WHY IT IS 168 LINES.  ANTIC fetches over the chip
 * bus with 16-bit addresses, so the framebuffer has to be in bank $00
 * and in motherboard RAM -- not the accelerator's SRAM, which ANTIC
 * cannot see, and not the banked window $4000-$7FFF, which a DOS
 * switches out from under itself while it services a call and which
 * ANTIC would then happily display.  What is left is the region
 * src/gem4xe.scm reserves for the VBXE's MEMAC window, $8000-$9BFF,
 * which on a machine with no VBXE is simply free: 7,168 bytes, bounded
 * above by SpartaDOS X's screen at $9C00.  Take the display list off the
 * front and 168 lines of 40 bytes is what fits.  The ceiling is memory,
 * not ANTIC.
 *
 *     $8000-$80AE   the display list, 175 bytes
 *     $8100-$9B3F   the framebuffer, 168 x 40 = 6,720 bytes
 *
 * THE FRAMEBUFFER IS LINEAR, which it has no right to be: ANTIC's memory
 * counter wraps at a 4 KB boundary, so a screen that crosses one usually
 * needs its lines re-based and the rasteriser needs to know where.  Here
 * the base is chosen so that the crossing falls exactly BETWEEN two
 * lines -- $8100 + 96*40 is $9000 to the byte -- so one extra LMS at
 * line 96 re-points ANTIC at the address the linear formula already
 * gives, and every line is base + L*40 after all.
 *
 * COLOUR.  Mode F is a hires mode: a set bit takes COLPF1's LUMINANCE on
 * COLPF2's hue, so there are two colours and one of them owns the hue.
 * The VDI's pen 0 is the background and pen 1 the foreground; anything
 * else is device-dependent nonsense here and says so.
 */
#ifndef GEM4XE_ANTIC_H
#define GEM4XE_ANTIC_H

#include <stdint.h>

#define AN_DLIST    0x8000U             /* the display list             */
#define AN_SCREEN   0x8100U             /* the framebuffer              */
#define AN_W        320                 /* pixels across                */
#define AN_H        168                 /* ...and down                  */
#define AN_STRIDE   (AN_W / 8)          /* 40 bytes a line              */
#define AN_BYTES    ((uint16_t)AN_STRIDE * AN_H)
#define AN_SPLIT    96                  /* the line the 4 KB crossing
                                         * falls in front of            */
#define AN_GLYPH_W  8                   /* the system font's cell       */
#define AN_GLYPH_H  8

/* ANTIC and GTIA, the registers this file drives. */
#define AN_DMACTL   0xD400U
#define AN_DLISTL   0xD402U
#define AN_COLPF1   0xD017U
#define AN_COLPF2   0xD018U
#define AN_COLBK    0xD01AU
#define AN_PRIOR    0xD01BU             /* GTIA priority, and its mode  */
/* ...and the OS shadows, written too, so that an OS VBI that is running
 * puts back what this file set rather than what the OS last wanted. */
#define AN_SDMCTL   0x022FU
#define AN_SDLSTL   0x0230U
#define AN_COLOR1   0x02C5U
#define AN_COLOR2   0x02C6U
#define AN_COLOR4   0x02C8U
#define AN_GPRIOR   0x026FU             /* ...and the OS shadow of PRIOR*/

/* Build the display list and turn the screen on.  `fg` and `bg` are
 * Atari colour bytes: fg's luminance and bg's hue are what show. */
void antic_init(uint8_t fg, uint8_t bg);

/* One of the two colours changed: pen 0 is the background's hue and pen
 * 1 the foreground's luminance, which is all mode F has. */
void antic_recolour(int16_t pen, uint8_t value);

/* The screen off again, and the OS's own display list back. */
void antic_off(void);

/* For the OTHER device.  The VBXE overlay hides ANTIC's picture and not
 * its DMA: a GR.0 text screen, which is what DOS leaves behind, halts
 * the CPU for some 8,500 of a PAL frame's 35,568 cycles, and every byte
 * the VDI writes through the MEMAC window and every VBXE register it
 * touches waits on that same bus.  The playfield goes off under the
 * overlay and comes back, as DOS had it, on the way out. */
void antic_suspend(void);
void antic_resume(void);

/* Every byte of the framebuffer to `value`. */
void antic_clear(uint8_t value);

/* One pixel, and a horizontal run from x1 to x2 inclusive; `set` paints
 * the foreground, 0 the background.  Both clip to the screen. */
void antic_plot(int16_t x, int16_t y, uint8_t set);
void antic_hline(int16_t x1, int16_t x2, int16_t y, uint8_t set);

/* A filled rectangle, corners inclusive. */
void antic_rect(int16_t x1, int16_t y1, int16_t x2, int16_t y2, uint8_t set);

/* ---- what the VDI asks a surface for --------------------------------
 * The four GEM writing modes (vdi.h MD_REPLACE..MD_ERASE) over a source,
 * a pen and a destination.  On a one-bit device the pen is 0 or 1 and
 * the modes come out as:
 *
 *   REPLACE   the whole cell is written: dst = pen ? src : ~src
 *   TRANS     the pen goes where the source is set, the rest is left
 *   XOR       dst ^= src, and the pen means nothing
 *   ERASE     the pen goes where the source is CLEAR, the rest is left
 *
 * A solid run is a source of all ones, which is why REPLACE and TRANS
 * come to the same thing for one and ERASE to nothing at all -- exactly
 * what the VBXE driver's paint_rect already decides for itself. */
void antic_span(int16_t x1, int16_t x2, int16_t y, int16_t mode, uint8_t pen);
void antic_rect_mode(int16_t x1, int16_t y1, int16_t x2, int16_t y2,
                     int16_t mode, uint8_t pen);

/* One 8x8 glyph of the system font at (x, y), which is the cell's top
 * left.  1bpp into 1bpp with a shift, where the VBXE driver has to keep
 * the same glyph expanded to 4bpp masks in VRAM at both parities. */
void antic_glyph(uint32_t face, uint16_t ch,
                 int16_t x, int16_t y, int16_t mode, uint8_t pen,
                 int16_t w, int16_t h);

/* A PATTERNED run.  `patrow` is one row of a GEM fill pattern: sixteen
 * bits, bit 15 the leftmost pixel of a 16-ALIGNED screen word, which is
 * how src/vdi/fillpat.c stores them and how the VBXE driver consumes
 * them.  The alignment is the screen's, not the run's, so two rectangles
 * side by side carry one continuous pattern.
 *
 * A styled horizontal LINE is the same thing: the VDI anchors vsl_type's
 * mask to the screen grid with style_anchor() and then draws the line as
 * a patterned span, so this one primitive serves both and the two
 * drivers cannot disagree about the phase. */
void antic_patt_span(int16_t x1, int16_t x2, int16_t y, uint16_t patrow,
                     int16_t mode, uint8_t pen);

/* One row of a one-plane source onto the screen -- vrt_cpyfm, which is
 * how every desktop icon is drawn.  x1..x2 is already clipped, to the
 * screen and to the clip rectangle; `sbit` is the source bit x1 comes
 * from, counting from `row`'s first bit.  A BYTE at a time: the source is
 * shifted into the screen's alignment and each screen byte is read and
 * written once -- or only written, where a replace covers all of it --
 * because every screen access is on the 1.79 MHz bus however fast the
 * CPU is (docs/phase52.md).  Modes are the VDI's, numbered from 1. */
void antic_raster_row(const uint8_t FAR *row, uint16_t sbit,
                      int16_t x1, int16_t x2, int16_t y,
                      int16_t mode, uint8_t pen, uint8_t pap);

/* A vertical line, styled: the mask is indexed by y the same way. */
void antic_vline(int16_t x, int16_t y1, int16_t y2, uint16_t mask,
                 int16_t mode, uint8_t pen);

/* vro_cpyfm's screen-to-screen case: a rectangle moved, overlapping or
 * not.  The shape is the VBXE driver's -- whole bytes when the two ends
 * share their alignment, pixel by pixel otherwise -- and the direction
 * is chosen so that an overlapping move does not eat its own source. */
void antic_copy(int16_t sx, int16_t sy, int16_t dx, int16_t dy,
                int16_t w, int16_t h);

/* ---- the mouse cursor -------------------------------------------------
 * The GEM rule: the MASK is painted in the background colour first and
 * the DATA over it in the foreground, so a mask bit with no data bit is
 * the outline and a clear mask bit leaves the screen alone.  Sixteen
 * rows of sixteen bits each, bit 15 leftmost, at the cell's top left --
 * the caller has already taken the hot spot off.
 *
 * Pixel by pixel, deliberately.  On the VBXE side that cost 12 ms a show
 * through the MEMAC window and had to become four blitter strips
 * (docs/phase8b.md); here the framebuffer is plain motherboard RAM the
 * accelerator writes at full speed, and 256 plots is a quarter of a
 * millisecond. */
void antic_cursor_save(int16_t x, int16_t y);
void antic_cursor_restore(void);

/* ...and forget the saved block WITHOUT putting it back, which is
 * v_clrwk's case: the screen it belonged to is gone. */
void antic_cursor_discard(void);
void antic_cursor_paint(int16_t x, int16_t y, const uint16_t *mask,
                        const uint16_t *data, uint8_t bg, uint8_t fg);

/* v_get_pixel: 0 or 1, and 0 for anything off the screen. */
uint8_t antic_get_pixel(int16_t x, int16_t y);

#endif /* GEM4XE_ANTIC_H */
