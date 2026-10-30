/* hiprobe.c -- which banks above bank $00 are RAM, and ours to use.
 *
 * The Atari's part of far memory: the probe that finds and sizes the
 * linear RAM, and the Rapidus OS's kernel allocator, from which the banks
 * are taken and to which they are given back.  It fills FARMEM and starts
 * the allocator (src/sys/farmem.c), which knows nothing of the machine.
 * Moved out of farmem.c in phase 116 (docs/memory-plan.md, step 1).
 */
#include "portab.h"
#include "farmem.h"
#include "hiprobe.h"

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
    far_heap_clear();                   /* nothing handed out yet */

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
