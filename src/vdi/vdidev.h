/* vdidev.h -- the seam between the VDI and the surface it draws on.
 *
 * Everything above this line is device-INdependent: the dispatcher, the
 * workstation state, clipping, attributes, text metrics, the inquiries.
 * Everything below it knows what a pixel is made of.  Two devices
 * implement it:
 *
 *   src/vdi/dev_vbxe.c   640x240, 4bpp, VRAM on the 1.79 MHz chip bus,
 *                        so every primitive compiles a BLIT LIST and the
 *                        CPU touches pixels only where the blitter
 *                        genuinely cannot help;
 *   src/vdi/dev_antic.c  320x168, 1bpp, plain motherboard RAM the
 *                        accelerator writes at full speed, so every
 *                        primitive writes BYTES and there is nothing to
 *                        flush.
 *
 * BOTH ARE LINKED, and which one draws is decided when the program
 * starts: a machine with a VBXE gets the VBXE, one without gets ANTIC,
 * and a line in GEM4XE.CFG can override either way.  That is why the
 * geometry and the calls below are a POINTER to a table rather than
 * constants and direct calls -- `vdev` is set once, before v_opnwk, and
 * never moves again.
 *
 * NOTHING ABOVE THE SEAM CHANGED to make that so.  The names SCR_W,
 * FONT_H, dev_fill_rect and the rest still mean what they meant; they
 * are macros onto the table now, so src/vdi/vdi.c reads exactly as it
 * did when there was one device compiled in.  The cost is an indirect
 * call, which on a 65816 in the large code model is a jsl through a
 * pointer and no trampoline (docs/phase32.md).
 *
 * A DEVICE'S OWN FILE does not see those macros: it defines
 * GEM4XE_DEV_IMPL first, keeps its geometry as compile-time constants --
 * they are constants, for it -- and names its functions with its own
 * prefix.  The table at the end of the file is where the two meet.
 *
 * THE PEN IS THE VDI'S, not the hardware's.  A caller passes the pen it
 * was given and the device maps it -- through map_col on VBXE, and to
 * nothing at all on a device with two colours.  That is the difference
 * between a seam and a leak: the VDI has no business knowing that one
 * device has a palette and the other has a luminance.
 */
#ifndef GEM4XE_VDIDEV_H
#define GEM4XE_VDIDEV_H

#include "portab.h"
#include "vdi.h"

/* ---- a device's own geometry -----------------------------------------
 * Compiled ONLY into the two device files, which define GEM4XE_DEV_IMPL
 * and are each built for one device: there, the numbers really are
 * constants and the code should be able to fold them.  Portable code
 * gets the same names below, off `vdev`, and never sees these. */
#ifdef GEM4XE_DEV_IMPL
#ifdef GEM4XE_DEV_PRINT
   /* A PAGE, not a screen: 640 x 800 dots of far memory, declared to the
    * printer at 100 dpi, which is 6.4 x 8.0 inches and fits Letter and
    * A4 with better than three-quarters of an inch of margin.
    * docs/printing.md has the arithmetic, and the reason for 800 rather
    * than a rounder number: 80 bytes a row by 800 is 64,000 against a
    * bank's 65,536, so the whole page is addressable inside ONE far bank
    * and every loop below is plain 16-bit arithmetic.
    *
    * The face is the 8x8, the same one the VBXE screen draws with, so
    * the printer reports the same 80 columns and a form laid out for the
    * screen lands on the page at identical coordinates. */
#  include "../vdi/print.h"
#  define SCR_W       PR_W
#  define SCR_H       PR_H
#  define SCR_STRIDE  PR_STRIDE
#  define TEXT_PREFILL  0
#  define FONT_W        8
#  define FONT_H        8
#  define FONT_TOP      6
#  define FONT_ASCENT   6
#  define FONT_HALF     4
#  define FONT_DESCENT  1
#  define FONT_BOTTOM   1
#  define FONT_POINT    9
#elif defined(GEM4XE_DEV_ANTIC)
#  include "../antic/antic.h"
#  define SCR_W       AN_W
#  define SCR_H       AN_H
#  define SCR_STRIDE  AN_STRIDE
#  define TEXT_PREFILL  0
   /* Atari's condensed face (bios/fnt_st_6x6.c), which is what the ST
    * uses for icon labels in low resolution -- GEM's own answer to a
    * screen short of pixels.  6 wide is 53 columns here where 8 would be
    * 40, and 6 tall is 28 rows where 8 would be 21: more of both, and a
    * face designed to be read at that size rather than one squeezed. */
#  define FONT_W        6
#  define FONT_H        6
#  define FONT_TOP      4     /* Fonthead.top: baseline to top of cell */
#  define FONT_ASCENT   4
#  define FONT_HALF     3
#  define FONT_DESCENT  1
#  define FONT_BOTTOM   1
#  define FONT_POINT    8
#else
#  include "../vbxe/vbxe.h"
/* THE ONLY DEVICE WHOSE GEOMETRY IS NOT COMPILE-TIME, and it is the
 * width that forces it: the overlay has three (512, 640, 672) and one
 * device file answers for all of them, so VB_W and VB_STRIDE are the
 * NORMAL screen and not this one.  A far read per primitive, which is
 * nothing beside the VRAM write it is computing an address for.
 *
 * SCR_H stays compile-time and that is not an oversight: it is the
 * BUFFER's bound, 240 whatever is shown, a safe superset that
 * everything above the seam has already clipped to vdev->h.  A stride
 * is not a bound -- it is the step from one row to the next -- so the
 * same argument does not reach it, and using 320 on a 672-pixel screen
 * puts every row after the first in the wrong place.  test-m3 running
 * the conformance suite at all three widths is what said so. */
#  define SCR_W       (vdev->w)
#  define SCR_H       VB_H
#  define SCR_STRIDE  (vdev->stride)
#  define TEXT_PREFILL  1
#  define FONT_W        8
#  define FONT_H        8
#  define FONT_TOP      6     /* Fonthead.top: baseline to top of cell */
#  define FONT_ASCENT   6     /* and the rest of the head EmuTOS records */
#  define FONT_HALF     4     /* for this face, which vst_alignment needs */
#  define FONT_DESCENT  1
#  define FONT_BOTTOM   1
#  define FONT_POINT    9
#endif
#endif /* GEM4XE_DEV_IMPL */

/* A raster form as the copy sees it: an MFDB resolved, or the screen.
 * `base` is 24-bit because on one device it is a VRAM address and on the
 * other a bank-$00 one, and the VDI does not care which. */
typedef struct {
    uint32_t base;
    uint16_t stride;
    WORD     w, h;
    WORD     screen;
} RFORM;

/* ---- the table --------------------------------------------------------
 * One of these per device, built at the end of the device's own file and
 * pointed at by `vdev` when the program has decided which screen it has.
 * The comments below are the seam's contract and are why this is a
 * struct of pointers rather than a jump table: each entry says what it
 * promises, and the two devices are held to the same promise.
 */
typedef struct {
    /* ---- the surface ------------------------------------------------
     * What v_opnwk reports and every clip in the VDI is bounded by.  The
     * portable code reads them as SCR_W, SCR_H and SCR_STRIDE, which is
     * what they were called when they were constants. */
    WORD w, h;
    WORD stride;                /* bytes per row, in the DEVICE's packing */

    /* ---- the system font's metrics ----------------------------------
     * The face itself is the VDI's business (src/vdi/font.c); its SHAPE
     * is the device's, because a screen 320 pixels wide cannot spend
     * eight of them on a character and still be a GEM.  Read above the
     * seam as FONT_W, FONT_H, FONT_TOP and the rest. */
    WORD font_w, font_h;
    WORD font_top, font_ascent, font_half, font_descent, font_bottom;
    WORD font_point;
    /* The face itself: the 1bpp strip vdi_font starts out pointing at
     * (src/vdi/font.h).  A device that has 53 columns and one that has
     * 80 do not want the same one, and a .FNT loaded later replaces it
     * for whichever is running. */
    const uint8_t FAR *font_face;

    /* A solid rectangle in the current pen, corners inclusive, already
     * clipped by the caller.  MD_REPLACE's and MD_ERASE's shape; the mode
     * itself is decided above the seam, because that decision is the same
     * whatever the pixels are made of. */
    void (*fill_rect)(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen);

    /* ...and the same rectangle inverted, which is MD_XOR. */
    void (*xor_rect)(WORD x1, WORD y1, WORD x2, WORD y2);

    /* A rectangle in the current fill pattern and writing mode, corners
     * inclusive and already clipped.  The pattern's ROWS come from the VDI
     * (pat_bits) because which table they are in is the workstation's
     * business; how they reach the screen is the device's. */
    void (*patt_rect)(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen);

    /* A horizontal or vertical line in the current pen and mode, styled by
     * `mask` -- already anchored to the screen's grid by style_anchor, so
     * both devices draw a dash in the same place.  The device clips it. */
    void (*style_line)(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask);

    /* ---- text -------------------------------------------------------------
     * One glyph of the system font with its top-left at (cx, cy), in the
     * current writing mode and text colour.  `overlay` is 0 for the letter
     * itself and 1 for the second pass that thickens it -- which is not the
     * same as "draw it transparently", because in XOR and erase modes the
     * overlay is drawn in THAT mode too and the device may take a different
     * path for it.  The device clips the cell: a partial glyph is not
     * something GEM asks for, and whether a whole one can be blitted is the
     * device's question, not the VDI's. */
    void (*glyph)(WORD ch, WORD cx, WORD cy, WORD overlay);

    /* The font strip changed (src/vdi/font.c loaded another face).  A device
     * that keeps the glyphs in some other form re-derives it here: VBXE
     * expands all 256 into 4bpp masks in VRAM at both x parities, 8 KB of
     * them; ANTIC blits the strip as it stands and this is empty. */
    void (*font_changed)(void);

    /* A ONE-PLANE source expanded into the device's colours -- how the AES
     * draws icons and glyph masks (vrt_cpyfm).  `ink` and `bg` are VDI pens.
     * The source is a near pointer because a form lives in bank $00. */
    /* THE SOURCE IS FAR, and that is not decoration.  A 1bpp memory form
     * is an icon's mask or image, and those come out of a resource --
     * which src/aes/rsrc.c moves to far memory so the 14 KB application
     * pool does not have to hold a quarter of DESKTOP.RSC.  An MFDB's
     * fd_addr has been 32 bits since phase 2, but it used to be
     * truncated here on the way in, because a memory form had always
     * been in bank $00. */
    void (*raster_1bpp)(const uint8_t FAR *bits, uint16_t stride,
                        WORD sx, WORD sy, WORD w, WORD h,
                        WORD dx, WORD dy, WORD mode, WORD ink, WORD bg);

    /* ---- the pointer -----------------------------------------------------
     * The VDI owns WHERE it is: the hot spot, the nesting count that
     * v_show_c and v_hide_c keep, and whether it is currently drawn.  The
     * device owns what it is MADE of and what was underneath it.
     *
     * `mask` and `data` are the sixteen rows GEM's MFORM carries, bit 15
     * leftmost; `bg` and `fg` are VDI pens.  A device keeps whatever it
     * needs of them -- VBXE expands the pair into 4bpp strips in VRAM at
     * both x parities, which is a kilobyte written once per form; ANTIC
     * blits the rows as they stand. */
    void (*cursor_form)(WORD bg, WORD fg, const UWORD *mask, const UWORD *data);

    /* Save what is under (cx, cy) and paint the form over it, done and on
     * the screen by the time this returns. */
    void (*cursor_show)(WORD cx, WORD cy);

    /* Put back what was under it. */
    void (*cursor_hide)(void);

    /* Forget what was under it WITHOUT putting it back -- v_clrwk's case,
     * where restoring would stamp stale pixels onto a cleared screen. */
    void (*cursor_discard)(void);

    /* A DIAGONAL line, styled the same way.  It is separate from
     * dev_style_line because on one device the two could not be less alike:
     * a horizontal run is a single patterned blit and a diagonal is the one
     * primitive the blitter cannot accelerate at all, so it goes pixel by
     * pixel through the MEMAC window.  The VDI decides which it is -- that
     * is geometry, and the same either way -- and the device decides what
     * that costs.
     *
     * The AES never draws one: every box and frame it makes is axis-aligned
     * (it calls neither the GDPs nor v_fillarea), so this is an
     * application's path, and it is slow on both devices for different
     * reasons. */
    void (*line_diag)(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask);

    /* ---- rasters ----------------------------------------------------------
     * The screen described as a form: an MFDB with a null address means "the
     * screen", and only the device knows where that is and how wide a row of
     * it is. */
    void (*screen_form)(RFORM *f);

    /* vro_cpyfm's copy, both rectangles already clipped by the VDI and known
     * to be inside their forms.  Source and destination may be the same form
     * and may overlap, so the device picks its direction.  VBXE takes one
     * blit when the two ends share their alignment and the width is a whole
     * number of bytes, and falls to pixel-by-pixel otherwise, because its
     * blitter has no shifter. */
    void (*copy_form)(const RFORM *src, WORD sx, WORD sy,
                      const RFORM *dst, WORD dx, WORD dy, WORD w, WORD h);

    /* The off-screen area the AES saves under menus and dialogs into,
     * described as an MFDB.  Where it is and what shape it has are entirely
     * the device's: VRAM on one, and there is no such thing to spare in bank
     * $00 on the other. */
    void (*save_form)(MFDB *m);

    /* ---- the rest ---------------------------------------------------------
     * The screen, cleared.  The pointer is the VDI's to put back afterwards.
     */
    void (*clear_screen)(void);

    /* One pixel read back: `value` is what the device stores there and is
     * what v_get_pixel reports as intout[0], `pen` the VDI pen it maps to.
     * Both, because the VDI's contract asks for both and only the device can
     * answer either. */
    void (*get_pixel)(WORD x, WORD y, WORD *value, WORD *pen);

    /* The value this device stores for a VDI pen -- the units dev_get_pixel
     * and dev_row_pixel answer in. */
    WORD (*pen_value)(WORD pen);

    /* One screen row into SCR_STRIDE bytes, and a pixel out of it.  This is
     * the paint bucket's, and it is the one primitive that has to look at
     * what is already on the screen a whole row at a time; keeping the row
     * in the DEVICE's packed form and asking for pixels out of it is what
     * stops a 640-pixel row costing 640 bytes of a 2 KB stack. */
    void (*read_row)(WORD y, uint8_t *px);
    WORD (*row_pixel)(const uint8_t *px, WORD x);

    /* How many colours the device can show at once.  v_opnwk reports it, so
     * it is what the AES and every application lay themselves out for -- and
     * it is why this is a device question and not a constant: a two-colour
     * workstation also has to say it cannot do colour at all, the way the
     * ST's monochrome one does. */
    WORD (*colours)(void);

    /* ...and how many PLANES that is.  The AES reads it out of vq_extnd and
     * sizes its menu save buffer from it, so a device that lies here wastes
     * memory or loses part of a menu. */
    WORD (*planes)(void);

    /* The palette: sixteen VDI pens' worth of 8-bit RGB, or one of them.
     * The device permutes into whatever order its hardware wants -- and a
     * device with two colours takes what it can of it. */
    void (*palette_all)(const uint8_t *rgb);
    void (*palette_one)(WORD pen, const uint8_t *rgb);

    /* Whatever the device precomputed about the current pattern or pen is
     * stale.  The VDI calls this when a workstation is selected or reset or
     * when the user pattern is replaced: it cannot know WHETHER a device
     * caches anything, only that the ground has moved.  VBXE keeps the
     * pattern expanded to 4bpp in VRAM with a line's strip beside it and
     * throws both away; ANTIC caches nothing and this is empty. */
    void (*invalidate)(void);

    /* Whatever the device has queued, done and on the screen.  A blit list
     * started and waited for on VBXE; nothing at all on ANTIC, where the
     * write WAS the drawing. */
    void (*flush)(void);

    /* Does v_gtext paint a replace-mode string's background ONCE, for the
     * whole run, and then draw the glyphs over it -- rather than each glyph
     * painting its own cell?  The pixels are the same either way.  It is
     * worth it where each piece of work is a blit: on VBXE a cell at an
     * odd x is five blits of background before its glyph, and a string is
     * one fill (docs/phase53.md).  ANTIC touches each byte once anyway and
     * would only do more, so it is 0 there.  LAST, and that is on purpose:
     * an initialiser that stops short zero-fills it, so only the device
     * that wants it has to say so. */
    WORD text_prefill;
} VDIDEV;

/* THE DEVICE IN USE.
 *
 * The PROGRAM sets this, once, before vdi_init(), and it never moves
 * again -- src/gem.c after vbxe_detect() and the config file, a
 * milestone to whichever device it is about.  Deliberately not a
 * function that picks for itself: the program is what knows whether it
 * has brought the surface up, and only one thing should be able to
 * decide, so there is no second copy of the answer to disagree.
 *
 * Nothing above the seam names it.  vdi.c and the AES read SCR_W,
 * FONT_H and dev_fill_rect exactly as they did when there was one device
 * compiled in; the macros below are where those names land now.
 *
 * FAR, and so are the tables: each is about 130 bytes, and bank $00
 * has 2,430 for every constant the system owns (src/gem4xe.scm).  Two of
 * them there would be a tenth of it spent on a table read once per
 * primitive, so they live in `cfar` with the far code and the reads are
 * 24-bit.  At 20 MHz that is a few cycles against a VRAM write at 1.79.
 *
 * IT IS NULL UNTIL THE PROGRAM SETS IT, and every macro below
 * dereferences it.  A VDI call before that is a null far read, not a
 * diagnosable error -- which is why setting it is the first line of
 * every bring-up and not something arranged later. */
extern const VDIDEV FAR *vdev;

/* The two tables, in the two device files.  A build links whichever
 * devices it has a screen for; naming one that is not linked is a link
 * error, which is the right time to find out. */
/* Every VBXE screen the overlay can show: [width][height], the widths
 * VB_WIDE_* (512/640/672 pixels, GEM4XE.CFG's SCREENW) and the heights
 * 240/224/200 for a tube that crops (SCREENH).  The program picks one
 * before vdi_init and never moves again. */
/* The bounds are written out rather than taken from src/vbxe/vbxe.h's
 * VB_WIDTHS/VB_HEIGHTS: nothing above the seam includes that header, and
 * this declaration is above it.  dev_vbxe.c defines the table with the
 * named constants and would not link if the two disagreed. */
extern const VDIDEV FAR vdev_vbxe_tab[3][3];
/* ...and the plain one, 640x240, for a runner with nothing to say about
 * it.  A POINTER, so `vdev = vdev_vbxe` where it used to be `&vdev_vbxe`. */
extern const VDIDEV FAR *const vdev_vbxe;
extern const VDIDEV FAR vdev_antic;
/* ...and the page, which is a device open BESIDE one of those rather
 * than instead of it: a workstation carries its own (src/vdi/vdi.h). */
extern const VDIDEV FAR vdev_print;
/* ...and the page it draws on, which unlike a screen has to be taken
 * before it can be drawn on and given back after (src/vdi/print.h). */
int16_t pr_page_open(void);
void    pr_page_close(void);

#ifdef GEM4XE_DEV_IMPL
/* A DEVICE'S OWN FILE keeps the names the seam gave it and has its own
 * prefix stamped on them, so both devices can be linked at once and
 * neither had to be renamed by hand.  GEM4XE_DEV_PREFIX comes from the
 * Makefile, beside GEM4XE_DEV_IMPL. */
#  define DEV_CAT_(a, b) a ## b
#  define DEV_CAT(a, b)  DEV_CAT_(a, b)
#  define DEV_(name)     DEV_CAT(GEM4XE_DEV_PREFIX, name)
#  define dev_fill_rect      DEV_(fill_rect)
#  define dev_xor_rect       DEV_(xor_rect)
#  define dev_patt_rect      DEV_(patt_rect)
#  define dev_style_line     DEV_(style_line)
#  define dev_glyph          DEV_(glyph)
#  define dev_font_changed   DEV_(font_changed)
#  define dev_raster_1bpp    DEV_(raster_1bpp)
#  define dev_cursor_form    DEV_(cursor_form)
#  define dev_cursor_show    DEV_(cursor_show)
#  define dev_cursor_hide    DEV_(cursor_hide)
#  define dev_cursor_discard DEV_(cursor_discard)
#  define dev_line_diag      DEV_(line_diag)
#  define dev_screen_form    DEV_(screen_form)
#  define dev_copy_form      DEV_(copy_form)
#  define dev_save_form      DEV_(save_form)
#  define dev_clear_screen   DEV_(clear_screen)
#  define dev_get_pixel      DEV_(get_pixel)
#  define dev_pen_value      DEV_(pen_value)
#  define dev_read_row       DEV_(read_row)
#  define dev_row_pixel      DEV_(row_pixel)
#  define dev_colours        DEV_(colours)
#  define dev_planes         DEV_(planes)
#  define dev_palette_all    DEV_(palette_all)
#  define dev_palette_one    DEV_(palette_one)
#  define dev_invalidate     DEV_(invalidate)
#  define dev_flush          DEV_(flush)
#else
#  define SCR_W         (vdev->w)
#  define SCR_H         (vdev->h)
#  define SCR_STRIDE    (vdev->stride)
#  define TEXT_PREFILL  (vdev->text_prefill)
/* The widest row either device can hand back, for the one buffer that
 * has to be an array rather than a pointer (vdi.c, the paint bucket). */
/* 336 is the widest overlay's stride -- VB_W_WIDE / 2 in
 * src/vbxe/vbxe.h -- written out because nothing above the seam
 * includes that header.  Too small and the paint bucket reads a row
 * into a buffer shorter than the row. */
#  define SCR_STRIDE_MAX 336

#  define FONT_W        (vdev->font_w)
#  define FONT_H        (vdev->font_h)
#  define FONT_TOP      (vdev->font_top)
#  define FONT_ASCENT   (vdev->font_ascent)
#  define FONT_HALF     (vdev->font_half)
#  define FONT_DESCENT  (vdev->font_descent)
#  define FONT_BOTTOM   (vdev->font_bottom)
#  define FONT_POINT    (vdev->font_point)

#  define dev_fill_rect     (vdev->fill_rect)
#  define dev_xor_rect      (vdev->xor_rect)
#  define dev_patt_rect     (vdev->patt_rect)
#  define dev_style_line    (vdev->style_line)
#  define dev_glyph         (vdev->glyph)
#  define dev_font_changed  (vdev->font_changed)
#  define dev_raster_1bpp   (vdev->raster_1bpp)
#  define dev_cursor_form   (vdev->cursor_form)
#  define dev_cursor_show   (vdev->cursor_show)
#  define dev_cursor_hide   (vdev->cursor_hide)
#  define dev_cursor_discard (vdev->cursor_discard)
#  define dev_line_diag     (vdev->line_diag)
#  define dev_screen_form   (vdev->screen_form)
#  define dev_copy_form     (vdev->copy_form)
#  define dev_save_form     (vdev->save_form)
#  define dev_clear_screen  (vdev->clear_screen)
#  define dev_get_pixel     (vdev->get_pixel)
#  define dev_pen_value     (vdev->pen_value)
#  define dev_read_row      (vdev->read_row)
#  define dev_row_pixel     (vdev->row_pixel)
#  define dev_colours       (vdev->colours)
#  define dev_planes        (vdev->planes)
#  define dev_palette_all   (vdev->palette_all)
#  define dev_palette_one   (vdev->palette_one)
#  define dev_invalidate    (vdev->invalidate)
#  define dev_flush         (vdev->flush)
#endif /* GEM4XE_DEV_IMPL */

#endif /* GEM4XE_VDIDEV_H */
