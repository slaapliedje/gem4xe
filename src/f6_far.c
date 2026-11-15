/* f6_far.c -- step 3a of docs/6502.md: the far heap on a stock 6502.
 *
 * src/sys/farmem.c's allocator, unchanged but for how it reaches its
 * table, runs in a bank of its own; the far_* helpers are resident
 * (src/sys6502/farmem6502.c) and map PORTB data banks behind 24-bit
 * addresses.  This program, resident, asks the allocator what
 * tests/emu/f6_far.py asks tools/farref.py's model, and writes every
 * address it got to $0640 (four bytes each) for the gate to compare.
 * Then it moves bytes about and checks them, a bit each in $0604:
 *
 *   bit 0  200 bytes put and got back across a 16 KB PORTB boundary
 *   bit 1  ...copied far to far into another block, and got back
 *   bit 2  far_fill, read back with far_read8
 *   bit 3  far_strput and far_strget
 *   bit 4  100 bytes put across a 64 KB far bank, got back
 *   bit 5  a bank's own code that puts and gets far memory goes on
 *          running in its bank afterwards (f6_banked, bank 1)
 *   bit 6  bank 0 is near memory: far_put to a near address lands there
 *   bit 7  the 16 KB pieces are distinct: a marker every $4000 across the
 *          70,000-byte block, all read back -- without it a map that put
 *          every piece of a far bank in the same PORTB bank passed, its
 *          writes reading back through the same alias
 *
 * STATUS $0600: 'F' '6' as it starts, 'K' at $0602 at the end; the far
 * banks the probe made at $0603.
 */
#include "portab.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"

#define STATUS ((volatile uint8_t *)0x0600)
#define ADDRS  ((volatile uint8_t *)0x0640)

extern uint16_t f6_banked(uint32_t at);    /* src/f6_bank.c, bank 1 */
extern void e_puts(const char *line);       /* src/sys6502/eput6502.s */
extern uint8_t b6_count, b6_portb[];        /* src/sys6502/bank6502.s */

static uint8_t buf[256], back[256];
static uint8_t nearbox[16];

static char line[48];
static uint8_t lp;

static void put_c(char c) { line[lp++] = c; }
static void put_s(const char *s) { while (*s) put_c(*s++); }
static void put_hex(uint32_t v, uint8_t digits)
{
    while (digits--)
        put_c("0123456789ABCDEF"[(uint8_t)(v >> (digits * 4)) & 15]);
}
static void say(void)
{
    line[lp] = (char)0x9B;
    e_puts(line);
    lp = 0;
}

static void note(uint8_t k, uint32_t a)
{
    ADDRS[k * 4 + 0] = (uint8_t)a;
    ADDRS[k * 4 + 1] = (uint8_t)(a >> 8);
    ADDRS[k * 4 + 2] = (uint8_t)(a >> 16);
    ADDRS[k * 4 + 3] = (uint8_t)(a >> 24);
}

static uint8_t same(const uint8_t *a, const uint8_t *b, uint16_t n)
{
    uint16_t i;

    for (i = 0; i < n; i++)
        if (a[i] != b[i])
            return 0;
    return 1;
}

int main(void)
{
    uint32_t a1, a2, a3, a4, a5, a6, a7, a8, at;
    uint16_t i, off;
    uint8_t ok = 0;

    STATUS[0] = 'F';
    STATUS[1] = '6';
    STATUS[2] = 0;
    /* first, before anything banked: what the load-time probe found, on
     * the screen -- the MiSTer core's PORTB is a different machine's */
    put_s("F6 PROBE "); put_hex(b6_count, 2); put_s(" BANKS:");
    for (i = 0; i < 8; i++) {
        put_c(' ');
        put_hex(b6_portb[i], 2);
    }
    say();
    farmem_probe();
    STATUS[3] = farmem.banks;

    /* the requests, as tests/emu/f6_far.py gives them to the model */
    a1 = far_alloc(1000);
    a2 = far_alloc(20000);
    a3 = far_alloc_top(300);
    far_free(a1);
    a4 = far_alloc(500);
    a5 = far_alloc_span(70000UL);
    far_owner = 7;
    a6 = far_alloc(100);
    a7 = far_alloc(200);
    far_free_owner(7);
    far_owner = 0;
    a8 = far_alloc(150);
    note(0, a1); note(1, a2); note(2, a3); note(3, a4);
    note(4, a5); note(5, a6); note(6, a7); note(7, a8);

    for (i = 0; i < 256; i++)
        buf[i] = (uint8_t)(i * 7 + 3);

    /* bit 0: across a 16 KB boundary inside a2 */
    off = (uint16_t)(0x4000U - ((uint16_t)a2 & 0x3FFFU));
    off = off > 50 ? (uint16_t)(off - 50) : (uint16_t)(off + 0x4000U - 50);
    at = a2 + off;
    far_put(at, buf, 200);
    far_get(back, at, 200);
    if (same(buf, back, 200))
        ok |= 0x01;

    /* bit 1: far to far */
    far_copy(a4, at, 200);
    far_get(back, a4, 200);
    if (same(buf, back, 200))
        ok |= 0x02;

    /* bit 2 */
    far_fill(a4 + 10, 0x5A, 100);
    if (far_read8(a4 + 10) == 0x5A && far_read8(a4 + 109) == 0x5A
        && far_read8(a4 + 110) == buf[110] && far_read8(a4 + 9) == buf[9])
        ok |= 0x04;

    /* bit 3 */
    {
        char s[20];

        far_strput(a3, "GEM 6502 FAR", 20);
        far_strget(s, a3, 20);
        if (s[0] == 'G' && s[9] == 'F' && s[12] == 0)
            ok |= 0x08;
    }

    /* bit 4: across a 64 KB far bank inside a5, if it crosses one */
    at = (a5 & 0xFFFF0000UL) + 0x10000UL - 30;
    if (at < a5)
        at += 0x10000UL;
    if (at + 100 <= a5 + 70000UL) {
        far_put_span(at, buf, 100);
        far_get(back, at, 100);
        if (same(buf, back, 100))
            ok |= 0x10;
    }

    /* bit 5 */
    if (f6_banked(a8) == 0x1234)
        ok |= 0x20;

    /* bit 6 */
    far_put((uint32_t)(uint16_t)nearbox, buf, 16);
    if (same(nearbox, buf, 16))
        ok |= 0x40;

    /* bit 7 */
    {
        uint8_t k, good = 1;

        for (k = 0; k < 5; k++)
            far_write8(a5 + (uint32_t)k * 0x4000UL, (uint8_t)(0xC0 + k));
        for (k = 0; k < 5; k++) {
            uint8_t v = far_read8(a5 + (uint32_t)k * 0x4000UL);
            /* in a variable first: cc6502 5.18 SIGN-extends a byte cast
             * widened straight back to int -- (uint8_t)(0xC0 + k) compared
             * as -64 + k, and this check failed with every piece right
             * (docs/6502.md, "cc6502's byte cast") */
            uint8_t want = (uint8_t)(0xC0 + k);

            ADDRS[32 + k] = v;          /* what each piece read back, $0660 */
            if (v != want)
                good = 0;
        }
        if (good)
            ok |= 0x80;
    }

    STATUS[4] = ok;
    /* ...and on the screen, for a machine whose memory a gate cannot read
     * (the MiSTer): the bits, the far banks, then the eight addresses */
    put_s("F6 BITS "); put_hex(ok, 2);
    put_s(ok == 0xFF ? " ALL OK" : " FAILED");
    put_s("  FAR BANKS "); put_hex(farmem.banks, 2);
    say();
    put_hex(a1, 6); put_c(' '); put_hex(a2, 6); put_c(' ');
    put_hex(a3, 6); put_c(' '); put_hex(a4, 6);
    say();
    put_hex(a5, 6); put_c(' '); put_hex(a6, 6); put_c(' ');
    put_hex(a7, 6); put_c(' '); put_hex(a8, 6);
    say();
    STATUS[2] = 'K';
    for (;;)
        ;
}
