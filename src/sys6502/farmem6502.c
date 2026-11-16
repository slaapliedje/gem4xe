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
static void far_bad(uint32_t a)
{
    *(volatile uint32_t *)0x0670 = a;
    *(volatile char *)0x0604 = 'F';
    for (;;)
        ;
}

/* Bank in the window for `a` (a far address, bank >= 1); the window
 * address in *w; the bytes from there to the end of the 16 KB piece. */
static uint16_t map(uint32_t a, uint8_t **w)
{
    uint16_t off = (uint16_t)a;
    uint8_t k = (uint8_t)(a >> 16);
    uint8_t b = (uint8_t)(B6_CODE_BANKS + 1 + (uint8_t)((k - 1) * 4) + (off >> 14));

    if (b > b6_count || k > 15)     /* k: past 15 the index wraps */
        far_bad(a);
    PORTB = b6_portb[b];
    *w = (uint8_t *)(WINDOW + (off & (PIECE - 1)));
    return (uint16_t)(PIECE - (off & (PIECE - 1)));
}

static void unmap(void)
{
    PORTB = b6_portb[b6_cur];
}

static uint8_t is_near(uint32_t a)
{
    /* the bank byte, stored first: cc6502 compares (uint8_t)(a >> 16)
     * as bits 16-31 (tools/bsp6502/b6scan.py) */
    uint8_t bank = (uint8_t)(a >> 16);

    return bank == 0;
}

void far_write8(uint32_t addr, uint8_t v)
{
    uint8_t *w;

    if (is_near(addr)) {
        *(uint8_t *)(uint16_t)addr = v;
        return;
    }
    map(addr, &w);
    *w = v;
    unmap();
}

uint8_t far_read8(uint32_t addr)
{
    uint8_t *w, v;

    if (is_near(addr))
        return *(const uint8_t *)(uint16_t)addr;
    map(addr, &w);
    v = *w;
    unmap();
    return v;
}

void far_put(uint32_t dst, const uint8_t *src, uint16_t len)
{
    uint8_t *w;
    uint16_t k;

    if (is_near(dst)) {
        memcpy((void *)(uint16_t)dst, src, len);
        return;
    }
    while (len) {
        k = map(dst, &w);
        if (k > len)
            k = len;
        memcpy(w, src, k);
        unmap();
        dst += k;
        src += k;
        len = (uint16_t)(len - k);
    }
}

void far_get(uint8_t *dst, uint32_t src, uint16_t len)
{
    uint8_t *w;
    uint16_t k;

    if (is_near(src)) {
        memcpy(dst, (const void *)(uint16_t)src, len);
        return;
    }
    while (len) {
        k = map(src, &w);
        if (k > len)
            k = len;
        memcpy(dst, w, k);
        unmap();
        dst += k;
        src += k;
        len = (uint16_t)(len - k);
    }
}

/* A field's two or four bytes (FAR_GETF, src/sys/farmem.h), through
 * far_get, which maps once for both unless they straddle a piece. */
uint16_t far_rd16(uint32_t addr)
{
    uint16_t v;

    far_get((uint8_t *)&v, addr, 2);
    return v;
}

uint32_t far_rd32(uint32_t addr)
{
    uint32_t v;

    far_get((uint8_t *)&v, addr, 4);
    return v;
}

void far_wr16(uint32_t addr, uint16_t v)
{
    far_put(addr, (const uint8_t *)&v, 2);
}

void far_wr32(uint32_t addr, uint32_t v)
{
    far_put(addr, (const uint8_t *)&v, 4);
}

/* An object's field: tree t, object i, the field's offset (OB_GET,
 * src/aes/aes.h).  24 bytes an object. */
static uint32_t ob_at(uint32_t t, WORD i, uint8_t off)
{
    uint16_t k = (uint16_t)i;

    return t + (uint32_t)(uint16_t)((k << 4) + (k << 3)) + off;
}

uint16_t ob_rd16(uint32_t t, WORD i, uint8_t off) { return far_rd16(ob_at(t, i, off)); }
uint32_t ob_rd32(uint32_t t, WORD i, uint8_t off) { return far_rd32(ob_at(t, i, off)); }
uint16_t ob_wr16(uint32_t t, WORD i, uint8_t off, uint16_t v) { far_wr16(ob_at(t, i, off), v); return v; }
uint32_t ob_wr32(uint32_t t, WORD i, uint8_t off, uint32_t v) { far_wr32(ob_at(t, i, off), v); return v; }

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

void far_fill(uint32_t dst, uint8_t v, uint16_t len)
{
    uint8_t *w;
    uint16_t k;

    if (is_near(dst)) {
        memset((void *)(uint16_t)dst, v, len);
        return;
    }
    while (len) {
        k = map(dst, &w);
        if (k > len)
            k = len;
        memset(w, v, k);
        unmap();
        dst += k;
        len = (uint16_t)(len - k);
    }
}

void far_strget(char *dst, uint32_t src, uint16_t max)
{
    uint16_t k;
    char c;

    for (k = 0; k + 1 < max; k++) {
        c = (char)far_read8(src + k);
        if (!c)
            break;
        dst[k] = c;
    }
    dst[k] = 0;
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
