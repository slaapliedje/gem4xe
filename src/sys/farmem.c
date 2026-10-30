/* farmem.c -- discover and allocate linear RAM above bank $00. */
#include "portab.h"
#include "farmem.h"

/* Calypsi wants the address-space qualifier AFTER the base type in a
 * declarator: `uint8_t FAR *p`, not `FAR uint8_t *p`.  The latter parses
 * at file scope but is rejected as a local, which is a confusing way to find
 * out. */

FARMEM farmem;
TINY uint16_t km_heap, km_image;
TINY uint8_t  km_clash, km_held, hiram_lo, hiram_hi;

/* One past the highest far address the loader wrote, recorded by
 * src/farload.s as it copied the image up.  Probing and allocating both
 * start in the bank above it -- which is the first bank the program does not
 * occupy, taken from what actually arrived rather than restated as a
 * constant or predicted by the linker (the far code is spread over one
 * memory per bank from $01 up, and the linker has no operator for the end of
 * a section that lives in several memories).
 *
 * This is not caution, it is a repair.  The first version of this file
 * probed and allocated from bank $01, where the far code lives -- so
 * farmem_probe() wrote a bank number into $010100 and far_alloc() returned
 * $010000, and the program corrupted three bytes of its own text.  The
 * symptom was three unrelated VDI conformance failures that MOVED with the
 * optimisation level, because a different function was sitting on those
 * addresses each time. */
extern const uint8_t _fl_top[3];

static uint16_t far_first_free_bank(void)
{
    uint32_t top = (uint32_t)_fl_top[0] | ((uint32_t)_fl_top[1] << 8) |
                   ((uint32_t)_fl_top[2] << 16);
    uint16_t first = (uint16_t)((top + 0xFFFFUL) >> 16);
    /* Bank $00 is the Atari's own; nothing far may ever start there, even
     * in a build whose image somehow recorded no far bytes at all. */
    return first ? first : 1;
}

/* The offset within each bank used for probing.  $0100 rather than $0000
 * because if a bank turns out to MIRROR bank $00, a write at offset 0 would
 * land in the OS zero page; $0100 is the 6502 stack page, which the 65816 is
 * not using in native mode with its own stack elsewhere. */
#define PROBE_OFF 0x0100

void far_write8(uint32_t addr, uint8_t v)
{
    uint8_t FAR *p = (uint8_t FAR *)addr;
    *p = v;
}

uint8_t far_read8(uint32_t addr)
{
    uint8_t FAR *p = (uint8_t FAR *)addr;
    return *p;
}

void far_put(uint32_t dst, const uint8_t *src, uint16_t len)
{
    uint8_t FAR *p = (uint8_t FAR *)dst;
    while (len--)
        *p++ = *src++;
}

void far_get(uint8_t *dst, uint32_t src, uint16_t len)
{
    uint8_t FAR *p = (uint8_t FAR *)src;
    while (len--)
        *dst++ = *p++;
}

/* Far to far, ascending: the AES's shell buffer and an application's
 * copy of it both live above bank $00 (shel_get, shel_put). */
void far_copy(uint32_t dst, uint32_t src, uint16_t len)
{
    uint8_t FAR *d = (uint8_t FAR *)dst;
    const uint8_t FAR *s = (const uint8_t FAR *)src;
    while (len--)
        *d++ = *s++;
}

/* Far fill (the shell buffer's clearing). */
void far_fill(uint32_t dst, uint8_t v, uint16_t len)
{
    uint8_t FAR *d = (uint8_t FAR *)dst;
    while (len--)
        *d++ = v;
}

/* Bounded strcpy across the bank boundary, both ways: a string an
 * application hands the AES lives in far memory and the AES's own
 * buffers are sized, so neither copy may run past `max` with its NUL. */
void far_strget(char *dst, uint32_t src, uint16_t max)
{
    const char FAR *p = (const char FAR *)src;
    uint16_t k;
    for (k = 0; k + 1 < max && p[k]; k++)
        dst[k] = p[k];
    dst[k] = 0;
}

void far_strput(uint32_t dst, const char *src, uint16_t max)
{
    char FAR *p = (char FAR *)dst;
    uint16_t k;
    for (k = 0; k + 1 < max && src[k]; k++)
        p[k] = src[k];
    p[k] = 0;
}

/* Write every bank's own number into it, then read them all back.
 *
 * This is the classic RAM-sizing trick and it is alias-proof by construction:
 * a bank that mirrors another has been overwritten by the later write and
 * reads back the wrong number.  A bank with no RAM reads back floating bus or
 * ROM.  Either way it fails the same test, so no board-specific knowledge is
 * needed to size the memory -- only to NAME the board.
 *
 * Bank $FF is skipped: on Rapidus it holds the accelerator's registers, and
 * writing the bank number over them would be a poor way to start.
 *
 * AND EVERY BYTE THE PROBE WRITES IS PUT BACK.  The RAM above bank $00 is not
 * only gem4xe's: Rapidus OS hands it out (kmalloc), and SpartaDOS X's
 * 65816.SYS loads at the top of it -- $EF0000 on a 16 MB Rapidus -- so the
 * probe's $EF at $EF0100 landed in the driver's code.  The SDX file calls it
 * serves then failed, and the desktop said DESKTOP.RSC was not on the boot
 * disk, on a machine where every file was where it should be
 * (docs/phase41.md).  The saved bytes are a local: 255 bytes of stack for a
 * moment at start-up, which bank $00's data could not spare as a static.
 */
/* NOT ALL OF IT IS OURS.  The Rapidus OS hands out the high RAM through
 * its kernel allocator (COP #$01), and things live there before gem4xe
 * starts: on a real Rapidus the BIOS takes the top bank at every cold
 * start ($EF0000-$EFFEFF on a 16 MB board, its own state at $EF:EE00 and
 * the allocator's table at $EF:FF00), and SpartaDOS X's 65816.SYS puts
 * its drivers -- SIO816, EXT816 -- in that same bank, CARCACHE and RD816
 * below it.  gem4xe 0.12 unpacked programs at the top of a heap that ran
 * to $EF: with 65816.SYS loaded a tester's machine never reached the
 * desktop, and the BIOS's bank was overwritten on every real Rapidus
 * (docs/phase110.md).  Altirra's stand-in BIOS reserves nothing, which is
 * why no gate saw it.
 *
 * So when the allocator is there (km_ok), every block it has given out
 * is walked with kmgetblk -- blocks lie end to end from LOSEGM's bank --
 * and a bank any of them touches is not one of ours.  The heap is then
 * the longest run that is both RAM and free.  An OS older than 2.42 has
 * no kmgetblk and answers the first call with an error: nothing listed,
 * the probe as before.  Without the OS nothing else can have been
 * loaded there, and the probe is all there is.  Taking the memory FROM
 * the allocator, so nothing loaded later is given it too, is the next
 * step; this one stops taking what is already somebody's. */
#define LOSEGM (*(volatile uint8_t *)0x024D)    /* the first high-RAM bank */
#define HISEGM (*(volatile uint8_t *)0x024E)    /* ...and the last, inclusive */

/* busy: a bit a bank, 32 bytes -- not 256 on the stack beside save[] */
#define BUSY(m, b)  ((m)[(b) >> 3] & (uint8_t)(1 << ((b) & 7)))

/* ...and GEM4XE'S OWN IMAGE is up there too, in the banks from $01 that
 * src/farload.s filled before any of this ran.  The walk also says
 * whether anything allocated overlaps them -- past the first page of
 * bank $01, which the OS takes for itself where the zero page is
 * mirrored there (2.39) and gem4xe never uses (src/gem4xe.scm) -- and
 * where the image's free span starts, for farmem_claim to take it.
 * Returns that first page, or 0 when the image is not in the OS's pool. */
static uint16_t km_busy(uint8_t *busy, uint16_t img_end)
{
    uint32_t base = (uint32_t)LOSEGM << 16, end;
    uint16_t n, b, img_lo = 0;

    farmem.taken = 0;
    km_clash = 0;
    if (!km_ok || !LOSEGM)
        return 0;
    if (LOSEGM == 1)
        img_lo = 0x0100;
    for (n = 0; n < 128; n++) {
        if (km_getblk(n) < 0 || !km_size)
            break;
        end = base + ((uint32_t)km_size << 8);
        if (km_attr & 0x8000) {
            uint16_t p0 = (uint16_t)(base >> 8), p1 = (uint16_t)(end >> 8);
            for (b = (uint16_t)(base >> 16); b <= (uint16_t)((end - 1) >> 16) && b < 256; b++)
                if (!BUSY(busy, b)) {
                    busy[b >> 3] |= (uint8_t)(1 << (b & 7));
                    farmem.taken++;
                }
            if (p0 < img_end && p1 > 0x0101)
                km_clash = (uint8_t)((img_end >> 8) - 1);   /* somebody's,
                                         * inside the image: its last bank */
            else if (img_lo && p0 <= img_lo && p1 > img_lo)
                img_lo = p1;            /* the OS's page at the front */
        }
        base = end;
    }
    return (img_lo && img_lo < img_end && !km_clash) ? img_lo : 0;
}

/* TAKE IT FROM THE ALLOCATOR, so that nothing loaded while gem4xe runs --
 * a driver a DOS command installs, a program that asks the OS -- is
 * given the same banks; and give it back on the way out
 * (farmem_release).  Mode 0: the OS's kfree will not free a resident
 * block.
 *
 * kmalloc takes no address: it places a block at the first free place
 * that fits.  So a block that lands BELOW the place this file chose --
 * a heap fenced by HIGHRAM=, say -- is handed back and the gap under
 * the chosen place filled with a spacer block, and the request made
 * again; the spacers go back when it lands.  A block that lands above,
 * or a fourth miss, and nothing is held: the heap stays where the probe
 * proved RAM, unclaimed, as it was before. */
#define KM_SPACERS 4

static uint16_t km_claim(uint16_t first_page, uint16_t pages, uint16_t mode)
{
    uint16_t sp[KM_SPACERS], n = 0, got = 0, p;

    if (!pages)
        return 0;
    for (;;) {
        km_mode = mode;
        if (km_malloc(pages) < 0)
            break;
        p = km_page;
        if (p == first_page) {
            got = p;
            break;
        }
        km_free(p);
        if (p > first_page || n == KM_SPACERS)
            break;
        km_mode = 0;
        if (km_malloc((uint16_t)(first_page - p)) < 0)
            break;
        sp[n++] = km_page;
    }
    while (n)
        km_free(sp[--n]);
    return got;
}

#define KM_A64  0x0004

void farmem_release(void)
{
    if (km_heap)
        km_free(km_heap);
    if (km_image)
        km_free(km_image);
    km_heap = km_image = 0;
}

/* Both blocks still the allocator's and allocated: asked after a DOS
 * command, which runs a program of SpartaDOS X's own while gem4xe is
 * one, so that a DOS that frees a finished program's blocks would be
 * seen doing it to gem4xe's (src/sys/dos.c). */
uint16_t farmem_held(void)
{
    uint32_t base = (uint32_t)LOSEGM << 16;
    uint16_t n, want = 0, got = 0;

    if (km_heap) want++;
    if (km_image) want++;
    if (!want || !km_ok || !LOSEGM)
        return km_held = (uint8_t)!want;
    for (n = 0; n < 128; n++) {
        uint16_t p;
        if (km_getblk(n) < 0 || !km_size)
            break;
        p = (uint16_t)(base >> 8);
        if ((km_attr & 0x8000)
            && (p == km_heap || p == km_image))
            got++;
        base += (uint32_t)km_size << 8;
    }
    return km_held = (uint8_t)(got == want);
}

void farmem_probe(void)
{
    uint16_t b;
    uint16_t first = far_first_free_bank();
    uint8_t run_first = 0, run_len = 0, best_first = 0, best_len = 0;
    uint16_t img_lo, lo = first, hi = 0xFE;
    uint8_t save[0xFF];                 /* indexed by bank, $01-$FE */
    uint8_t busy[32];                   /* the OS's allocator has it */

    farmem.kind = FARMEM_NONE;
    farmem.first_bank = farmem.last_bank = farmem.banks = 0;
    farmem.bytes = 0;
    km_heap = km_image = 0;
    km_held = 0;
    for (b = 0; b < 32; b++)
        busy[b] = 0;
    img_lo = km_busy(busy, (uint16_t)(first << 8));
    /* WHERE THE HIGH RAM IS, when the OS says.  The Rapidus OS -- which
     * the Antonia II runs too (2.48) -- is told by the board's BIOS where
     * its high RAM lies, LOSEGM to HISEGM, and a bank outside that is not
     * RAM it hands out, whatever a write to it reads back: a board may
     * map other things into the 16 MB (the Antonia II's banked RAM and
     * flash are in it).  And HIGHRAM= in GEM4XE.CFG, for a board whose OS
     * says nothing: the banks the heap may use. */
    if (km_ok && LOSEGM && HISEGM >= LOSEGM) {
        if (lo < LOSEGM) lo = LOSEGM;
        if (hi > HISEGM) hi = HISEGM;
    }
    if (hiram_lo && lo < hiram_lo) lo = hiram_lo;
    if (hiram_hi && hi > hiram_hi) hi = hiram_hi;
    far_blocks = 0;
    far_table = 0;

    /* Name the board if we recognise it.  This does not affect sizing. */
    if (far_read8(0xFF0000UL) == '6' && far_read8(0xFF0001UL) == 'S')
        farmem.kind = FARMEM_RAPIDUS;

    for (b = first; b <= 0xFE; b++)
        save[b] = far_read8(((uint32_t)b << 16) | PROBE_OFF);
    for (b = first; b <= 0xFE; b++)
        far_write8(((uint32_t)b << 16) | PROBE_OFF, (uint8_t)b);

    for (b = first; b <= 0xFF; b++) {
        uint8_t ok = (b >= lo) && (b <= hi) && !BUSY(busy, b) &&
                     (far_read8(((uint32_t)b << 16) | PROBE_OFF) == (uint8_t)b);
        if (ok) {
            if (!run_len)
                run_first = (uint8_t)b;
            run_len++;
        } else {
            if (run_len > best_len) {
                best_len = run_len;
                best_first = run_first;
            }
            run_len = 0;
        }
    }

    /* Back as they were, from the top down: of two banks that are one cell,
     * the lower bank's saved byte is written last, and both read that cell
     * before any write. */
    for (b = 0xFE; b >= first; b--)
        far_write8(((uint32_t)b << 16) | PROBE_OFF, save[b]);

    if (!best_len)
        return;
    /* ...and one bank left for somebody else when the OS is sharing it
     * out: SpartaDOS X's drivers and commands ask it for high RAM, and a
     * DOS command runs while gem4xe holds everything it took. */
    if (km_ok && best_len > 2)
        best_len--;
    if (km_ok) {
        if (img_lo)
            km_image = km_claim(img_lo, (uint16_t)((first << 8) - img_lo), 0);
        km_heap = km_claim((uint16_t)best_first << 8,
                                  (uint16_t)best_len << 8, KM_A64);
        farmem_held();
    }
    if (farmem.kind == FARMEM_NONE)
        farmem.kind = FARMEM_UNKNOWN;
    farmem.first_bank = best_first;
    farmem.banks = best_len;
    farmem.last_bank = (uint8_t)(best_first + best_len - 1);
    farmem.bytes = (uint32_t)best_len << 16;
    far_heap_init();
}

/* -- A FAR POINTER'S ARITHMETIC IS SIXTEEN BITS.
 *
 * This is the fact the three functions below exist for, and it is worth
 * stating plainly because it is not what "24-bit pointer" suggests and
 * because getting it wrong is silent.  Calypsi compiles `p + n` on a
 * `__far` pointer as a 16-bit add to the OFFSET with the bank byte
 * loaded unchanged -- the carry is dropped:
 *
 *     clc
 *     lda  _Dp        ; the offset
 *     adc  _Dp+4      ; + n, low 16 bits only
 *     sta  _Dp
 *     lda  _Dp+2      ; the bank, UNTOUCHED
 *
 * So a walk that runs off the top of a bank comes back at its bottom and
 * reads somebody else's memory.  (The manual is consistent with this and
 * says so obliquely: a `far` OBJECT is capped at 64K minus one byte.
 * Crossing banks is what the `huge` attribute is for, and it widens
 * size_t to 32 bits everywhere, which is not a trade this system makes.)
 *
 * far_alloc's rule follows from it: nothing it hands out crosses a bank,
 * so anything allocated there can be walked with an ordinary far pointer.
 * far_put, far_get and far_copy above are correct for exactly that.
 *
 * A block that MAY straddle a bank, for the one thing that has to: a
 * file read into far memory whole (far_read_file).  far_alloc will not
 * give one, and a file bigger than the room left in the current bank
 * therefore could not be read AT ALL -- which went unnoticed for as long
 * as it did because every file gem4xe had loaded was a few KB.  GACS's
 * shell is 139 KB, and the failure it gave was APP_E_FILE, which reads
 * like a missing file.
 *
 * What lives here must be reached by RECOMPUTING the address for each
 * access -- far_read8, far_write8, far_copy_span -- and never by walking
 * a pointer across the boundary. */
/* Bank-safe copies, for what far_alloc_span handed out: the address is
 * rebuilt at every bank boundary instead of being walked over it.  The
 * inner copies are the ordinary far_put/far_copy, which are correct
 * because each call is given a run that stays inside one bank. */
void far_put_span(uint32_t dst, const uint8_t *src, uint16_t len)
{
    while (len) {
        uint32_t room = 0x10000UL - (dst & 0xFFFFUL);
        uint16_t k = (room >= len) ? len : (uint16_t)room;
        far_put(dst, src, k);
        dst += k;
        src += k;
        len = (uint16_t)(len - k);
    }
}

void far_copy_span(uint32_t dst, uint32_t src, uint32_t len)
{
    while (len) {
        uint32_t droom = 0x10000UL - (dst & 0xFFFFUL);
        uint32_t sroom = 0x10000UL - (src & 0xFFFFUL);
        uint32_t k = len;
        if (k > droom) k = droom;
        if (k > sroom) k = sroom;
        if (k > 0x4000UL) k = 0x4000UL;     /* a uint16_t can count it */
        far_copy(dst, src, (uint16_t)k);
        dst += k;
        src += k;
        len -= k;
    }
}


/* ---------------------------------------------------------------------------
 * THE ALLOCATOR -- blocks with owners, freed in any order (phase 79).
 *
 * It was a bump pointer with marks until 0.9.2, which could only give
 * back the top of the heap and so needed every release to be the reverse
 * of the takes.  Its cost was measured on a 65C816 with 960K: an
 * accessory of 4 KB took two whole banks, a resource loaded between two
 * programs started another, and the desktop never got its turn
 * (docs/phase78.md).  Now:
 *
 *   A TABLE OF BLOCKS, sorted by address, in the first bank of the heap
 *   (it is block 0, the system's).  Free space is what lies between them
 *   -- there is no second list to keep in step with the first.  Each
 *   entry is the address with its OWNER in the top byte, and the length.
 *
 *   OWNERS.  0 is the system: the shell's buffers, the desktop's cached
 *   file, the table.  Every program app_load takes in gets one of its
 *   own (far_new_owner), and far_owner says whose the next block is --
 *   src/sys/ctx.c sets it at every switch, so a block an accessory asks
 *   for at run time is the accessory's.  A program's exit frees its owner
 *   (far_free_owner); an accessory's is never freed, which is what made it
 *   permanent, where the bump allocator needed a floor for that.
 *
 *   FOUR KINDS OF REQUEST, each the lowest that fits:
 *     far_alloc        4-aligned, never across a bank (a far pointer's
 *                      arithmetic is sixteen bits, the note above)
 *     far_alloc_span   4-aligned, MAY cross: a file read whole
 *     far_alloc_page   page-aligned, and ending at or below `limit` in its
 *                      bank: a program's code relocated by pages, which
 *                      must stay under the $D5 page (src/gem4xe.scm)
 *     far_alloc_banks  whole banks, taken from the TOP of the heap down,
 *                      so a big program does not cut the small blocks'
 *                      space at the bottom in two
 *
 * tools/farref.py is the same rules in Python -- the model the desktop
 * gates place the desktop with, held to this file by test_farmem.py.
 */
#define FB_MAX      256                 /* blocks; the table is 2 KB */
#define FB_ADDR     0x00FFFFFFUL

typedef struct {
    uint32_t at;                        /* owner << 24 | address */
    uint32_t len;
} FBLK;

uint8_t  far_owner;
uint16_t far_blocks;
uint32_t far_table;

#define FB(i)       (((FBLK FAR *)far_table)[i])

static uint32_t heap_lo(void) { return (uint32_t)farmem.first_bank << 16; }
static uint32_t heap_hi(void) { return (uint32_t)(farmem.last_bank + 1) << 16; }

static uint32_t fb_start(uint16_t i)
{
    uint32_t at = FB(i).at;
    return at & FB_ADDR;
}

static uint32_t fb_end(uint16_t i)
{
    uint32_t len = FB(i).len;
    return fb_start(i) + ((len + 3) & ~3UL);
}

/* The gap before entry i (i == far_blocks: the gap above the last). */
static uint32_t gap_lo(uint16_t i) { return i ? fb_end((uint16_t)(i - 1)) : heap_lo(); }
static uint32_t gap_hi(uint16_t i) { return i < far_blocks ? fb_start(i) : heap_hi(); }

/* Entry i made the block at..at+len, owner far_owner, the rest moved up. */
static uint32_t fb_insert(uint16_t i, uint32_t at, uint32_t len)
{
    uint16_t k;
    FBLK e;

    if (far_blocks >= FB_MAX)
        return 0;
    for (k = far_blocks; k > i; k--) {
        e = FB(k - 1);
        FB(k) = e;
    }
    e.at = at | ((uint32_t)far_owner << 24);
    e.len = len;
    FB(i) = e;
    far_blocks++;
    return at;
}

static void fb_remove(uint16_t i)
{
    FBLK e;

    far_blocks--;
    for (; i < far_blocks; i++) {
        e = FB(i + 1);
        FB(i) = e;
    }
}

void far_heap_init(void)
{
    uint8_t keep = far_owner;

    far_blocks = 0;
    far_table = 0;
    far_owner = 0;
    if (!farmem.banks)
        return;
    far_table = heap_lo();
    fb_insert(0, far_table, (uint32_t)FB_MAX * sizeof(FBLK));
    far_owner = keep;
}

/* Where a request of `bytes` fits in [lo, hi), or 0.
 *   how 0: 4-aligned, inside one bank      2: page-aligned, below `limit`
 *   how 1: 4-aligned, may cross banks          in its bank */
static uint32_t fit(uint32_t lo, uint32_t hi, uint32_t bytes, uint16_t how,
                    uint32_t limit)
{
    uint32_t a;

    if (how == 2) {
        a = (lo + 0xFFUL) & ~0xFFUL;
        if ((a & 0xFFFFUL) + bytes > limit)
            a = (a | 0xFFFFUL) + 1;     /* the next bank's foot */
        if ((a & 0xFFFFUL) + bytes > limit)
            return 0;
    } else {
        a = (lo + 3) & ~3UL;
        if (how == 0 && (a & 0xFFFFUL) + bytes > 0x10000UL)
            a = (a | 0xFFFFUL) + 1;
    }
    if (a < lo || a + bytes > hi || a + bytes < a)
        return 0;
    return a;
}

static uint32_t take(uint32_t bytes, uint16_t how, uint32_t limit)
{
    uint16_t i;
    uint32_t a;

    if (!far_table || bytes == 0)
        return 0;
    if (how == 0 && bytes > 0x10000UL)  /* no block can be indexed past */
        return 0;                       /* its own bank */
    for (i = 0; i <= far_blocks; i++) {
        a = fit(gap_lo(i), gap_hi(i), bytes, how, limit);
        if (a)
            return fb_insert(i, a, bytes);
    }
    return 0;
}

uint32_t far_alloc(uint32_t bytes)       { return take(bytes, 0, 0); }
uint32_t far_alloc_span(uint32_t bytes)  { return take(bytes, 1, 0); }
uint32_t far_alloc_page(uint32_t bytes, uint32_t limit)
{
    return take(bytes, 2, limit);
}

/* Exactly at..at+bytes, or 0 if any of it is taken or outside the heap:
 * for memory a foreign program finds by ADDRESS, not by asking -- an Apple
 * IIGS program calls the Toolbox at $E1:0000 and draws at $E1:2000
 * (GSlayer, Mclaim in src/sys/gemdos.c).  `at` is rounded down and the
 * end up to 4, as every block's are. */
uint32_t far_claim(uint32_t at, uint32_t bytes)
{
    uint16_t i;
    uint32_t end;

    if (!far_table || bytes == 0)
        return 0;
    end = at + bytes;
    at &= ~3UL;
    if (end < at)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        if (gap_hi(i) <= at)
            continue;
        if (gap_lo(i) > at || end > gap_hi(i))
            return 0;
        return fb_insert(i, at, end - at);
    }
    return 0;
}

/* ...and at the TOP of the highest gap it fits, which may cross banks:
 * for a block that lives only a moment -- the span a squeezed program is
 * unpacked into (src/sys/app.c, phase 94) -- so that what is placed while
 * it lives goes where it would have gone without it.  Taken low, it put
 * every boot-time program above it and left the hole under them when it
 * went (test-m37: the boot past three banks).  Data only, never code, so
 * the SDRAM cache worry below does not reach it. */
uint32_t far_alloc_top(uint32_t bytes)
{
    uint16_t i;
    uint32_t lo, hi, a;

    if (!far_table || bytes == 0)
        return 0;
    for (i = (uint16_t)(far_blocks + 1); i-- > 0; ) {
        lo = gap_lo(i);
        hi = gap_hi(i);
        if (hi - lo < bytes)
            continue;
        a = (hi - bytes) & ~3UL;
        if (a < lo)
            continue;
        return fb_insert(i, a, bytes);
    }
    return 0;
}

/* n whole banks, the LOWEST run that is free: the first bank's number.
 * Low, not from the top where they would keep out of the small blocks'
 * way: on a Rapidus the top of the heap is SDRAM, behind a cache that no
 * gate here can say is coherent for code the loader writes and then runs
 * (docs/rapidus-cache.md), and the first megabyte is SRAM. */
uint16_t far_alloc_banks(uint16_t n)
{
    uint16_t i;
    uint32_t bytes = (uint32_t)n << 16, a;

    if (!far_table || n == 0)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        a = (gap_lo(i) + 0xFFFFUL) & ~0xFFFFUL;
        if (a + bytes > gap_hi(i) || a + bytes < a)
            continue;
        if (!fb_insert(i, a, bytes))
            return 0;
        return (uint16_t)(a >> 16);
    }
    return 0;
}

static uint16_t fb_find(uint32_t addr)
{
    uint16_t i;

    for (i = 0; i < far_blocks; i++)
        if (fb_start(i) == addr)
            return i;
    return 0xFFFF;
}

uint16_t far_free(uint32_t addr)
{
    uint16_t i = fb_find(addr);

    if (i == 0xFFFF || i == 0)          /* not a block; or the table */
        return 0;
    fb_remove(i);
    return 1;
}

/* The block at addr becomes the system's: its owner's exit leaves it,
 * and only far_free gives it back.  The desktop's colour icons, kept
 * across its restarts (objc_sysvar G4_DESKICON, phase 89). */
uint16_t far_keep(uint32_t addr)
{
    uint16_t i = fb_find(addr);
    uint32_t at;

    if (i == 0xFFFF || i == 0)
        return 0;
    at = FB(i).at;
    at &= FB_ADDR;
    FB(i).at = at;
    return 1;
}

void far_free_owner(uint8_t owner)
{
    uint16_t i = 1;

    if (!owner)                         /* the system's are for ever */
        return;
    while (i < far_blocks) {
        uint32_t at = FB(i).at;
        if ((uint8_t)(at >> 24) == owner)
            fb_remove(i);
        else
            i++;
    }
}

uint16_t far_shrink(uint32_t addr, uint32_t bytes)
{
    uint16_t i = fb_find(addr);
    uint32_t len;

    if (i == 0xFFFF || i == 0)
        return 0;
    len = FB(i).len;
    if (bytes == 0 || bytes > len)
        return 0;
    FB(i).len = bytes;
    return 1;
}

uint32_t far_size(uint32_t addr)
{
    uint16_t i = fb_find(addr);
    uint32_t len;

    if (i == 0xFFFF)
        return 0;
    len = FB(i).len;
    return len;
}

/* The biggest request of kind `span` (0: inside a bank, 1: may cross) that
 * would succeed now. */
uint32_t far_largest(uint16_t span)
{
    uint16_t i;
    uint32_t best = 0, lo, hi, n, b;

    if (!far_table)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        lo = (gap_lo(i) + 3) & ~3UL;
        hi = gap_hi(i);
        if (hi <= lo)
            continue;
        if (span) {
            n = hi - lo;
        } else {
            n = 0;
            for (b = lo; b < hi; b = (b | 0xFFFFUL) + 1) {
                uint32_t e = (b | 0xFFFFUL) + 1;
                if (e > hi)
                    e = hi;
                if (e - b > n)
                    n = e - b;
            }
        }
        if (n > best)
            best = n;
    }
    return best;
}

/* An owner that has no blocks, for a program about to be loaded. */
uint8_t far_new_owner(void)
{
    static uint8_t next = 1;
    uint16_t tries, i;

    for (tries = 0; tries < 255; tries++) {
        uint8_t o = next;
        next = (uint8_t)(next == 255 ? 1 : next + 1);
        for (i = 0; i < far_blocks; i++) {
            uint32_t at = FB(i).at;
            if ((uint8_t)(at >> 24) == o)
                break;
        }
        if (i == far_blocks)
            return o;
    }
    return 0;
}
