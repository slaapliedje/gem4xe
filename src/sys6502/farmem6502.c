/* farmem6502.c -- far memory on the 6502: PORTB banks behind 24-bit
 * addresses, so that src/sys/farmem.c's allocator and every caller of the
 * far_* helpers work as they do on the 65C816 (docs/6502.md, step 3).
 *
 * A FAR ADDRESS keeps the 65C816's shape: bank << 16 | offset.  Bank 0 is
 * near memory, the 64 KB the CPU sees, read and written directly -- the
 * VDI's "bank $00" pointers mean what they always meant.  Far bank k >= 1
 * is four PORTB banks after the code's (src/sys6502/bank6502.s found them
 * all at load; the code has the first B6_CODE_BANKS):
 *
 *      PORTB bank  B6_CODE_BANKS + 1 + (k - 1) * 4 + (offset >> 14)
 *      window      $4000 + (offset & $3FFF)
 *
 * So a 64 KB far bank is four 16 KB windows' worth, contiguous to the
 * allocator, and every helper here works in pieces that stay inside one.
 *
 * ALL OF THIS IS RESIDENT, and each helper puts the caller's bank back in
 * the window before it returns: the caller may be the VDI, running in a
 * bank of its own, whose code the window holds again by the time this
 * returns to it.  A near buffer handed here must not be in the window
 * itself -- nothing near lives there: resident memory is below $4000 and
 * above $8000.
 */
#include "portab.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"
#include "aes/aes.h"                /* OBJECT, for ob_rd16 and the rest */
#include <string.h>

#ifndef B6_CODE_BANKS
#ifdef __CALYPSI_TARGET_6502__
#error "B6_CODE_BANKS: the banks the code takes (tools/bsp6502/rules.mk)"
#else
#define B6_CODE_BANKS 1             /* a host's parse (make qscan) */
#endif
#endif

#define PORTB   (*(volatile uint8_t *)0xD301)
#define WINDOW  0x4000U
#define PIECE   0x4000U

extern uint8_t b6_cur, b6_count, b6_portb[];

/* A FAR ADDRESS IN NO BANK THERE IS stops here.  Mapped, it would index
 * past b6_portb into whatever follows it; a zero there switches the OS
 * ROM out, and the next interrupt runs the RAM under it (step 4e found
 * one, from a garbage object spec).  The address goes to $0670-$0673,
 * 'F' to $0604 -- src/sys6502/stub6502.c's place for a stop -- and the
 * stack is left as it is, for whoever reads the call chain off page 1. */
void b6_far_bad(uint32_t a)
{
    *(volatile uint32_t *)0x0670 = a;
    *(volatile char *)0x0604 = 'F';
    for (;;)
        ;
}

/* THE HOT HALF IS IN ASSEMBLY: src/sys6502/far6502.s has far_read8,
 * far_write8, far_rd16/32, far_wr16/32, far_get, far_put, far_fill,
 * far_strget and ob_rd16/32, ob_wr16, and reads these two: the PORTB
 * bank of far bank 1's first piece, and the stop above. */
const uint8_t b6_far_base = B6_CODE_BANKS + 1;

/* ob_wr32's four arguments do not fit the registers (the value would go
 * on the C stack), so it stays here, in terms of the assembly's. */
uint32_t ob_wr32(uint32_t t, WORD i, uint8_t off, uint32_t v)
{
    uint16_t k = (uint16_t)i;

    far_wr32(t + (uint32_t)(uint16_t)((k << 4) + (k << 3)) + off, v);
    return v;
}

/* Far to far goes through a near buffer: the window holds one bank. */
static uint8_t bounce[64];

void far_copy(uint32_t dst, uint32_t src, uint16_t len)
{
    uint16_t k;

    while (len) {
        k = len > sizeof bounce ? (uint16_t)sizeof bounce : len;
        far_get(bounce, src, k);
        far_put(dst, bounce, k);
        dst += k;
        src += k;
        len = (uint16_t)(len - k);
    }
}

void far_strput(uint32_t dst, const char *src, uint16_t max)
{
    uint16_t k;

    for (k = 0; k + 1 < max && src[k]; k++)
        far_write8(dst + k, (uint8_t)src[k]);
    far_write8(dst + k, 0);
}

/* The 65C816's two for a block that may cross a 64 KB bank: here every
 * helper already goes piece by piece, and a far address's carry into the
 * bank byte is the next far bank, which is the next four PORTB banks. */
void far_put_span(uint32_t dst, const uint8_t *src, uint16_t len)
{
    far_put(dst, src, len);
}

void far_copy_span(uint32_t dst, uint32_t src, uint32_t len)
{
    while (len) {
        uint16_t k = len > 0x4000UL ? 0x4000U : (uint16_t)len;
        far_copy(dst, src, k);
        dst += k;
        src += k;
        len -= k;
    }
}

/* ---- the probe -------------------------------------------------------
 * The banks are bank6502.s's, found at load.  Those after the code's,
 * four to a far bank; what is left over a whole far bank is not used. */
void farmem_probe(void)
{
    uint8_t data = b6_count > B6_CODE_BANKS ? (uint8_t)(b6_count - B6_CODE_BANKS) : 0;
    uint8_t k = (uint8_t)(data / 4);

    far_heap_clear();
    farmem.kind = k ? FARMEM_UNKNOWN : FARMEM_NONE;
    farmem.first_bank = k ? 1 : 0;
    farmem.last_bank = k;
    farmem.banks = k;
    farmem.bytes = (uint32_t)k << 16;
    farmem.taken = 0;
    if (k)
        far_heap_init();
}

void farmem_release(void) {}
uint16_t farmem_held(void) { return 1; }
