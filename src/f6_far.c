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
 * and in $0605, the field and string helpers (src/sys6502/far6502.s):
 *
 *   bit 0  far_wr16/far_rd16 at each offset from 3 before a 16 KB piece's
 *          end to 1 after, read back a byte at a time too
 *   bit 1  ...far_wr32/far_rd32 the same
 *   bit 2  far_strget across a piece's end, and cut short by its max
 *   bit 3  ob_wr16/ob_rd16/ob_rd32 at object 3, and at object 2 of a tree
 *          30 bytes below a 64 KB far bank's end: the carry into the bank
 *   bit 4  all of them on near memory (bank 0)
 *
 * STATUS $0600: 'F' '6' as it starts, 'K' at $0602 at the end; the far
 * banks the probe made at $0603.
 */
#include "portab.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"
/* the object helpers, as src/aes/aes.h declares them for the 6502 (here
 * too, so a host's parse -- make qscan -- sees them) */
uint16_t ob_rd16(uint32_t t, int16_t i, uint8_t off);
uint32_t ob_rd32(uint32_t t, int16_t i, uint8_t off);
uint16_t ob_wr16(uint32_t t, int16_t i, uint8_t off, uint16_t v);

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

/* $0605's bits (the head of the file) */
static uint8_t fields(uint32_t a2, uint32_t a5)
{
    uint8_t ok = 0x1F, d, i;         /* each failure clears its bit: with
                                     * plain constants, as a (uint8_t)~bit
                                     * sign-extends in cc6502 (b6scan) */
    uint32_t end, at;
    char s[24];

    /* the end of a2's first 16 KB piece: a2's offset rounded up */
    end = (a2 & 0xFFFFC000UL) + 0x4000UL;
    for (d = 0; d < 5; d++) {
        at = end - 3 + d;
        far_wr16(at, (uint16_t)(0xA100U + d));
        if (far_rd16(at) != (uint16_t)(0xA100U + d)
            || far_read8(at) != d || far_read8(at + 1) != 0xA1)
            ok &= 0xFE;
        far_wr32(at, 0xB2C3D400UL + d);
        if (far_rd32(at) != 0xB2C3D400UL + d
            || far_read8(at) != d || far_read8(at + 3) != 0xB2)
            ok &= 0xFD;
    }

    far_put(end - 5, (const uint8_t *)"PIECE-ENDS", 11);
    far_strget(s, end - 5, sizeof s);
    for (i = 0; i < 11; i++)
        if (s[i] != "PIECE-ENDS"[i])
            ok &= 0xFB;
    far_strget(s, end - 5, 5);
    if (s[3] != 'C' || s[4] != 0)
        ok &= 0xFB;
    s[0] = 'x';
    far_strget(s, end - 5, 0);
    if (s[0] != 0)
        ok &= 0xFB;

    /* object 3, field 10: 3 * 24 + 10 = 82 bytes on */
    if (ob_wr16(a2, 3, 10, 0x5E6FU) != 0x5E6FU || far_rd16(a2 + 82) != 0x5E6FU
        || ob_rd16(a2, 3, 10) != 0x5E6FU)
        ok &= 0xF7;
    far_wr32(a2 + 90, 0x01020304UL);
    if (ob_rd32(a2, 3, 18) != 0x01020304UL)
        ok &= 0xF7;
    /* a tree 30 bytes below a far bank's end: object 2's field 4 is 52
     * bytes on, 22 into the next bank -- if a5's span reaches it */
    at = (a5 & 0xFFFF0000UL) + 0x10000UL - 30;
    if (at < a5)
        at += 0x10000UL;
    if (at + 60 <= a5 + 70000UL) {
        ob_wr16(at, 2, 4, 0x7A7BU);
        if (far_rd16(at + 52) != 0x7A7BU || ob_rd16(at, 2, 4) != 0x7A7BU)
            ok &= 0xF7;
    } else
        ok &= 0xF7;

    /* bank 0: near memory, through the same calls */
    {
        static uint8_t box[32];
        uint32_t n = (uint32_t)(uint16_t)box;

        far_wr16(n + 1, 0x1357U);
        far_wr32(n + 4, 0x2468ACE0UL);
        far_put(n + 10, (const uint8_t *)"NEAR", 5);
        far_strget(s, n + 10, sizeof s);
        if (far_rd16(n + 1) != 0x1357U || box[1] != 0x57
            || far_rd32(n + 4) != 0x2468ACE0UL || box[7] != 0x24
            || s[0] != 'N' || s[3] != 'R' || s[4] != 0
            || ob_wr16(n, 0, 20, 0x99AAU) != 0x99AAU || box[21] != 0x99
            || ob_rd16(n, 0, 20) != 0x99AAU)
            ok &= 0xEF;
    }
    return ok;
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
    STATUS[5] = fields(a2, a5);
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
