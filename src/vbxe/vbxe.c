/* vbxe.c -- VBXE surface for gem4xe: detection, MEMAC A windowing, palette,
 * XDL and the blitter.
 *
 * Written in C rather than assembly on purpose.  Everything here is either a
 * handful of register pokes or a memory copy through a window; the hot path in
 * a VDI is the BLITTER, not the CPU, so there is nothing to hand-optimise yet.
 * Measure before moving any of this to as65816.
 */
#include "portab.h"
#include "vbxe.h"
#include "../sys/zwin.h"

uint16_t vbxe_base = 0;

#define REG(off)  (*(volatile uint8_t *)(vbxe_base + (off)))
#define WIN       ((volatile uint8_t *)MEMAC_WIN_ADDR)

void vbxe_reg(uint8_t off, uint8_t val) { REG(off) = val; }
uint8_t vbxe_reg_read(uint8_t off)      { return REG(off); }

/* ---------------------------------------------------------------------- */
/* Detection                                                              */
/* ---------------------------------------------------------------------- */

/* Probe $D600 then $D700.  The base is not fixed -- U1MB selects it through
 * UAUX ($D381) D5:D4 and can disable VBXE entirely -- so it must be found,
 * never assumed.
 *
 * The test is (CORE_REVISION & $0F) == 0 for "full FX core" and the high
 * nibble for the major version.  Never compare the whole byte: Altirra's
 * manual says FX 1.26 reads $11, which contradicts its own bit table and is an
 * erratum -- real hardware and the emulator both read $10.
 */
uint8_t vbxe_detect(void)
{
    uint16_t bases[2];
    uint8_t i;

    bases[0] = 0xD600;
    bases[1] = 0xD700;

    for (i = 0; i < 2; i++) {
        uint8_t core, minor, bcd;
        vbxe_base = bases[i];
        core  = REG(FX_CORE_REVISION);
        minor = REG(FX_MINOR_REVISION);
        if (core == 0xFF || (core & 0x0F) != 0)
            continue;                       /* absent, or the GTIA-only core */
        bcd = (uint8_t)(((minor >> 4) & 7) * 10 + (minor & 0x0F));
        if ((core >> 4) == 1 && bcd >= 20)
            return 1;
    }
    vbxe_base = 0;
    return 0;
}

uint8_t vbxe_major(void)     { return (uint8_t)(REG(FX_CORE_REVISION) >> 4); }
uint8_t vbxe_minor_bcd(void)
{
    uint8_t m = REG(FX_MINOR_REVISION);
    return (uint8_t)(((m >> 4) & 7) * 10 + (m & 0x0F));
}

/* ---------------------------------------------------------------------- */
/* MEMAC A -- the CPU's only view of VRAM                                 */
/* ---------------------------------------------------------------------- */

static uint8_t memac_bank = 0xFF;           /* shadow: BANK_SEL is write-only
                                               in spirit and re-poking it on
                                               every byte would be wasteful */

void vram_map_page(uint8_t page)
{
    if (page != memac_bank) {
        memac_bank = page;
        REG(FX_MEMAC_CONTROL)  = MEMAC_CTL_4K_8000;
        REG(FX_MEMAC_BANK_SEL) = (uint8_t)(0x80 | page);
    }
}

void vram_map(uint32_t addr)
{
    vram_map_page((uint8_t)(addr >> 12));
}

/* Force the next vram_map() to re-program the window.  Needed after anything
 * that could have changed MEMAC state behind our back. */
static void memac_invalidate(void) { memac_bank = 0xFF; }

volatile uint8_t *vram_win(uint32_t addr)
{
    vram_map(addr);
    return WIN + (addr & 0x0FFF);
}

/* Words, not bytes: the CPU is 16-bit and needs no alignment, so a word
 * store is two bus writes for one instruction.  As a byte loop this was
 * 20 instructions a byte and the second-hottest code in every AES row of
 * docs/bench.md; with the pointers and the count in the direct page it is
 * 15 a word.  The window pointer is not volatile: the compiler will not
 * store a word through a volatile pointer without a stack temporary, and
 * a store through a pointer it cannot see past is not one it can drop. */
static TINY uint16_t vw_n;
static const uint16_t * TINY vw_s;
static uint16_t * TINY vw_w;

void vram_write(uint32_t addr, const uint8_t *src, uint16_t len)
{
    while (len) {
        uint16_t off = (uint16_t)(addr & 0x0FFF);
        uint16_t n   = (uint16_t)(MEMAC_WIN_SIZE - off);
        if (n > len)
            n = len;
        vram_map(addr);
        vw_w = (uint16_t *)(WIN + off);
        vw_s = (const uint16_t *)src;
        if ((vw_n = n >> 1) != 0)
            do *vw_w++ = *vw_s++; while (--vw_n);
        if (n & 1)
            *(uint8_t *)vw_w = *(const uint8_t *)vw_s;
        addr += n;
        src  += n;
        len  = (uint16_t)(len - n);
    }
}

void vram_fill(uint32_t addr, uint8_t val, uint16_t len)
{
    while (len) {
        uint16_t off = (uint16_t)(addr & 0x0FFF);
        uint16_t n   = (uint16_t)(MEMAC_WIN_SIZE - off);
        uint16_t i;
        if (n > len)
            n = len;
        vram_map(addr);
        for (i = 0; i < n; i++)
            WIN[off + i] = val;
        addr += n;
        len  = (uint16_t)(len - n);
    }
}

uint8_t vram_read8(uint32_t addr)
{
    vram_map(addr);
    return WIN[addr & 0x0FFF];
}

/* ---------------------------------------------------------------------- */
/* Palette                                                                */
/* ---------------------------------------------------------------------- */

/* rgb is count*3 bytes.  Only D7:D1 of each component reach the DAC, and the
 * bit that comes back out is a copy of the top one -- so $96 reads back as
 * $97.  Any screenshot comparison must expand values the same way.
 *
 * Writing CB auto-increments CSEL, so a run of entries needs no CSEL reload.
 * Colours take effect immediately (unlike the XDL address, which is latched
 * at vertical sync), so upload during blanking or accept tearing.
 */
void vbxe_palette(uint8_t pal, uint8_t first, const uint8_t *rgb, uint16_t count)
{
    uint16_t i;
    REG(FX_PSEL) = (uint8_t)(pal & 3);
    REG(FX_CSEL) = first;
    for (i = 0; i < count; i++) {
        REG(FX_CR) = *rgb++;
        REG(FX_CG) = *rgb++;
        REG(FX_CB) = *rgb++;                /* bumps CSEL */
    }
}

/* ---------------------------------------------------------------------- */
/* XDL                                                                    */
/* ---------------------------------------------------------------------- */

/* A 640-wide 4bpp HR overlay from one screen buffer, `height` lines of
 * it shown.  The BUFFER is always VB_H tall (the VRAM map is laid out for
 * that); a shorter screen displays fewer of its rows, which is what a
 * tube that cuts the top or the bottom off wants -- GEM4XE.CFG's SCREENH,
 * and src/vdi/dev_vbxe.c's three device tables.
 *
 * Two things about the XDL that are easy to get wrong and silent when wrong:
 *   - an entry is only as long as its control word says, so a "blanked"
 *     control word does not blank the bytes behind it: the hardware reads
 *     them as further entries.  Build the list exactly, never patch a word.
 *   - overlay/attribute-map ADDRESSING is not reset per frame (width,
 *     priority, scroll and palette selection are), so it must be set at the
 *     top of every XDL.
 */
void vbxe_xdl_hr(uint32_t screen, uint16_t height, uint8_t topmargin,
                 uint8_t ovatt_width)
{
    uint8_t xdl[24];
    uint16_t ctl = XDLC_GMON | XDLC_HR | XDLC_RPTL | XDLC_OVADR | XDLC_OVATT;
    uint8_t n = 0;

    /* An optional top margin: `topmargin` scanlines that repeat the
     * screen's first line -- which the desktop keeps as background --
     * before the picture proper.  OVSTEP 0 reads that one line over and
     * over, so it costs nothing in VRAM, and it moves the menu bar off
     * the display's very first scanline (where a CRT has not settled and
     * a phone camera catches ringing) and down out of the top overscan a
     * tube may crop.  topmargin 0 emits the exact XDL it always did.
     * GEM4XE.CFG's TOPMARGIN sets it; main hands it over. */
    if (topmargin) {
        xdl[n++] = (uint8_t)(ctl & 0xFF);
        xdl[n++] = (uint8_t)(ctl >> 8);
        xdl[n++] = (uint8_t)(topmargin - 1);      /* repeat -> topmargin lines */
        xdl[n++] = (uint8_t)(screen);             /* OVADR = the first line     */
        xdl[n++] = (uint8_t)(screen >> 8);
        xdl[n++] = (uint8_t)(screen >> 16);
        xdl[n++] = 0;                             /* OVSTEP 0: the same line     */
        xdl[n++] = 0;
        xdl[n++] = OVATT_OVPAL(1) | ovatt_width;
        xdl[n++] = OVATT_PRI_OVER_ALL;
    }

    xdl[n++] = (uint8_t)(ctl & 0xFF);
    xdl[n++] = (uint8_t)(ctl >> 8);
    xdl[n++] = (uint8_t)(height - 1);            /* repeat -> `height` lines */
    xdl[n++] = (uint8_t)(screen);                 /* OVADR, 3 bytes         */
    xdl[n++] = (uint8_t)(screen >> 8);
    xdl[n++] = (uint8_t)(screen >> 16);
    /* OVSTEP is the SCREEN's bytes per row, not the normal screen's:
     * the display and the rasteriser have to agree on where row y+1
     * starts or the picture shears. */
    xdl[n++] = (uint8_t)(VB_STRIDE_OF(ovatt_width));  /* OVSTEP, 12 bits   */
    xdl[n++] = (uint8_t)(VB_STRIDE_OF(ovatt_width) >> 8);
    xdl[n++] = OVATT_OVPAL(1) | ovatt_width;
    xdl[n++] = OVATT_PRI_OVER_ALL;                /* $FF -- see vbxe.h      */
    xdl[n++] = (uint8_t)((XDLC_OVOFF | XDLC_END) & 0xFF);
    xdl[n++] = (uint8_t)((XDLC_OVOFF | XDLC_END) >> 8);

    vram_write(VR_XDL, xdl, n);

    REG(FX_XDL_ADR0) = (uint8_t)(VR_XDL);
    REG(FX_XDL_ADR1) = (uint8_t)(VR_XDL >> 8);
    REG(FX_XDL_ADR2) = (uint8_t)(VR_XDL >> 16);
    /* NO_TRANS so nibble 0 is a real colour: a GUI has to be able to paint
     * its background, not see through it. */
    REG(FX_VIDEO_CONTROL) = VC_XDL_ENABLE | VC_NO_TRANS;
}

/* The window closed, and forgotten: $8000-$8FFF is motherboard RAM until
 * the next vram_map(), which opens it again.  For a DOS command's run
 * (src/sys/dos.c dos_command), which is lent that RAM. */
void vram_unmap(void)
{
    REG(FX_MEMAC_BANK_SEL) = 0;
    REG(FX_MEMAC_CONTROL)  = 0;
    memac_invalidate();
}

/* The way out: overlay off, so ANTIC's own display shows again, and the
 * MEMAC window closed, so $8000-$8FFF is motherboard RAM again for whoever
 * comes next.  The blitter is left to finish whatever it was doing. */
void vbxe_off(void)
{
    REG(FX_VIDEO_CONTROL)  = 0;
    REG(FX_MEMAC_BANK_SEL) = 0;
    REG(FX_MEMAC_CONTROL)  = 0;
    memac_invalidate();
}

/* VBXE generates no VBI of its own -- all timing still comes from ANTIC.
 * Poll VCOUNT ($D40B) for the top of the frame; it works whether or not
 * the vertical blank interrupt is on (src/sys/irq.h). */
void vbxe_wait_vbl(void)
{
    volatile uint8_t *vcount = (volatile uint8_t *)0xD40B;
    while (*vcount != 0)
        ;
}

/* ---------------------------------------------------------------------- */
/* Blitter                                                                */
/* ---------------------------------------------------------------------- */

/* Blit control blocks are staged in RAM and uploaded as one contiguous run,
 * because the blitter has NO jump instruction: the "Next" bit only advances
 * to the physically adjacent BCB. */
#define MAX_BCB 12
ZWIN static uint8_t  bcb[MAX_BCB * BCB_SIZE];
static uint8_t  bcb_count = 0;

void blit_reset(void) { bcb_count = 0; }

static uint8_t *bcb_new(void)
{
    uint8_t *p;
    if (bcb_count >= MAX_BCB)
        return 0;
    p = &bcb[bcb_count * BCB_SIZE];
    bcb_count++;
    return p;
}

/* The 21 bytes of a BCB as the fields they are, so the block is written
 * in a dozen stores: the byte-indexed version cleared it in a loop first,
 * 20 instructions a byte, and was the hottest function in every AES row of
 * docs/bench.md.  The code generator pads nothing and the CPU has no
 * alignment rule, so the words sit where the layout puts them -- but
 * `sizeof` of this struct must not be used where a constant expression is
 * required, where it is padded (compiler bug B7, tools/ccbug); BCB_SIZE is
 * the byte count and check-cc pins the layout. */
typedef struct {
    uint16_t src;      uint8_t src_bank;  uint16_t sstride;  uint8_t sxstep;
    uint16_t dst;      uint8_t dst_bank;  uint16_t dstride;  uint8_t dxstep;
    uint16_t width;    uint8_t height;    /* both minus one; width 9 bits  */
    uint16_t masks;                       /* [15] AND, [16] XOR: callers'  */
    uint16_t coll_zoom;                   /* [17] collision mask, [18] zoom */
    uint16_t patt_ctl;                    /* [19] pattern, [20] mode|next   */
} BCB;

static void bcb_common(uint8_t *p, uint32_t src, uint16_t sstride,
                       uint32_t dst, uint16_t dstride,
                       uint16_t bytes, uint16_t rows)
{
    BCB *b = (BCB *)p;
    b->src      = (uint16_t)src;
    b->src_bank = (uint8_t)(src >> 16);
    b->sstride  = sstride;
    b->sxstep   = 1;
    b->dst      = (uint16_t)dst;
    b->dst_bank = (uint8_t)(dst >> 16);
    b->dstride  = dstride;
    b->dxstep   = 1;
    b->width    = (uint16_t)((bytes - 1) & 0x01FF);       /* 1..512        */
    b->height   = (uint8_t)(rows - 1);                    /* 1..256        */
    b->masks    = 0;
    b->coll_zoom = 0;                                     /* zoom 1x1      */
    b->patt_ctl = 0;
}

/* Solid fill.  and_mask == 0 takes the blitter's constant-source path: it
 * fetches no source bytes at all and runs at 1 cycle/byte, half the cost of a
 * real copy.  This is the most common operation a GUI performs. */
void blit_fill(uint32_t dst, uint16_t stride, uint16_t bytes,
               uint16_t rows, uint8_t value)
{
    uint8_t *p = bcb_new();
    if (!p)
        return;
    bcb_common(p, 0, 0, dst, stride, bytes, rows);
    p[15] = 0x00;                                 /* AND mask: no source    */
    p[16] = value;                                /* XOR mask: the colour   */
    p[20] = BLT_MODE_COPY;
}

/* Constant-source read-modify-write.  and_mask == 0 means no source fetch, so
 * c is just the xor mask; modes 2-6 then combine c with the destination.
 * Note modes 1-5 SKIP a byte whose c is zero -- harmless for OR/XOR, and the
 * AND masks used for 4bpp edges ($F0 / $0F) are never zero. */
static void blit_rmw(uint32_t dst, uint16_t stride, uint16_t bytes,
                     uint16_t rows, uint8_t value, uint8_t mode)
{
    uint8_t *p = bcb_new();
    if (!p)
        return;
    bcb_common(p, 0, 0, dst, stride, bytes, rows);
    p[15] = 0x00;
    p[16] = value;
    p[20] = mode;
}

void blit_and(uint32_t d, uint16_t s, uint16_t b, uint16_t r, uint8_t m)
{ blit_rmw(d, s, b, r, m, BLT_MODE_AND); }

void blit_or(uint32_t d, uint16_t s, uint16_t b, uint16_t r, uint8_t v)
{ blit_rmw(d, s, b, r, v, BLT_MODE_OR); }

void blit_xor(uint32_t d, uint16_t s, uint16_t b, uint16_t r, uint8_t v)
{ blit_rmw(d, s, b, r, v, BLT_MODE_XOR); }

uint8_t blit_pending(void) { return bcb_count; }

void vram_write8(uint32_t addr, uint8_t v)
{
    vram_map(addr);
    WIN[addr & 0x0FFF] = v;
}

void blit_copy(uint32_t src, uint16_t sstride, uint32_t dst,
               uint16_t dstride, uint16_t bytes, uint16_t rows)
{
    uint8_t *p = bcb_new();
    if (!p)
        return;
    bcb_common(p, src, sstride, dst, dstride, bytes, rows);
    p[15] = 0xFF;                                 /* AND mask: pass source  */
    p[16] = 0x00;
    p[20] = BLT_MODE_COPY;
}

void blit_move(uint32_t src, uint16_t sstride, uint32_t dst,
               uint16_t dstride, uint16_t bytes, uint16_t rows)
{
    uint8_t *p;
    uint16_t sneg, dneg;

    if (dst <= src) {
        blit_copy(src, sstride, dst, dstride, bytes, rows);
        return;
    }
    /* The blitter reads and writes a byte at a time, left to right, top
     * to bottom, so a copy to a higher address would overwrite source rows
     * it has yet to read.  Run it the other way: start both at their last
     * byte, step X by -1 and Y by -stride. */
    p = bcb_new();
    if (!p)
        return;
    bcb_common(p, src + (uint32_t)(rows - 1) * sstride + (uint32_t)(bytes - 1),
               0,
               dst + (uint32_t)(rows - 1) * dstride + (uint32_t)(bytes - 1),
               0, bytes, rows);
    sneg = (uint16_t)((uint16_t)(0u - sstride) & 0x1FFFu);   /* 13-bit signed */
    dneg = (uint16_t)((uint16_t)(0u - dstride) & 0x1FFFu);
    p[3]  = (uint8_t)sneg;
    p[4]  = (uint8_t)(sneg >> 8);
    p[5]  = 0xFF;                                 /* source X step: -1      */
    p[9]  = (uint8_t)dneg;
    p[10] = (uint8_t)(dneg >> 8);
    p[11] = 0xFF;                                 /* dest X step: -1        */
    p[15] = 0xFF;
    p[16] = 0x00;
    p[20] = BLT_MODE_COPY;
}

/* Upload the queued list and start it, without waiting. */
void blit_start(void)
{
    uint8_t i;
    if (!bcb_count)
        return;
    /* Chain every block but the last. */
    for (i = 0; i + 1 < bcb_count; i++)
        bcb[i * BCB_SIZE + 20] |= BLT_NEXT;
    bcb[(bcb_count - 1) * BCB_SIZE + 20] &= (uint8_t)~BLT_NEXT;

    vram_write(VR_BCB, bcb, (uint16_t)(bcb_count * BCB_SIZE));

    REG(FX_BL_ADR0) = (uint8_t)(VR_BCB);
    REG(FX_BL_ADR1) = (uint8_t)(VR_BCB >> 8);
    REG(FX_BL_ADR2) = (uint8_t)(VR_BCB >> 16);
    REG(FX_BLITTER_START) = 0;                    /* stop first: required if
                                                     a previous list may be
                                                     running */
    REG(FX_BLITTER_START) = 1;
    memac_invalidate();                           /* the blitter owns VRAM
                                                     while it runs          */
    bcb_count = 0;
}

uint8_t blit_busy(void) { return REG(FX_BLITTER_BUSY); }

void blit_mask(uint32_t src, uint16_t sstride, uint32_t dst, uint16_t dstride,
               uint16_t bytes, uint16_t rows, uint8_t and_mask,
               uint8_t xor_mask, uint8_t mode)
{
    uint8_t *p = bcb_new();
    if (!p)
        return;
    bcb_common(p, src, sstride, dst, dstride, bytes, rows);
    p[15] = and_mask;
    p[16] = xor_mask;
    p[20] = mode;
}

/* Byte 19 of the BCB: D7 enables the pattern counter, D5:D0 hold the repeat
 * length minus one.  Altirra (vbxe.cpp, BlitRow) resets the source pointer to
 * the row's start address when the counter expires. */
void blit_pattern(uint32_t src, uint16_t sstride, uint32_t dst,
                  uint16_t dstride, uint16_t bytes, uint16_t rows,
                  uint8_t and_mask, uint8_t xor_mask, uint8_t mode,
                  uint8_t repeat)
{
    uint8_t *p = bcb_new();
    if (!p)
        return;
    bcb_common(p, src, sstride, dst, dstride, bytes, rows);
    p[15] = and_mask;
    p[16] = xor_mask;
    p[19] = (uint8_t)(0x80 | ((repeat - 1) & 0x3F));
    p[20] = mode;
}

void blit_run(void)
{
    blit_start();
    while (REG(FX_BLITTER_BUSY))                  /* D1 BUSY | D0 BCB_LOAD  */
        ;
}

/* Run the queued list and return how long it took, in VCOUNT ticks (ANTIC's
 * line counter, one tick per two scanlines; a PAL frame is 156).
 *
 * Polling BLITTER_BUSY costs a resync to 1.79 MHz on every read -- which is
 * exactly why the real driver should use the blitter-complete IRQ instead --
 * but VCOUNT advances in real time regardless, so the measurement is honest.
 * It is coarse, not wrong. */
uint16_t blit_time(void)
{
    volatile uint8_t *vc = (volatile uint8_t *)0xD40B;
    uint16_t ticks = 0;
    uint8_t last, v;

    while (*vc != 0)                              /* align to top of frame  */
        ;
    blit_start();
    last = 0;
    while (REG(FX_BLITTER_BUSY)) {
        v = *vc;
        if (v < last)
            ticks = (uint16_t)(ticks + 156);      /* VCOUNT wrapped (PAL)   */
        last = v;
    }
    return (uint16_t)(ticks + last);
}
