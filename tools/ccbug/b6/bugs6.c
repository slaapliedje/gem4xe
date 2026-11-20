/* cc6502 bugs, each beside the shape that avoids it.  Run by check6.py
 * in db6502; r_*_bug and r_*_fix must both equal the "want" there. */
#include <stdint.h>
#include <stdio.h>
typedef short WORD;

volatile uint8_t  v7f = 0x7F;           /* volatile: nothing folds away */
volatile uint32_t v24 = 0x01000000UL;   /* bits 16-23 are zero */
volatile uint16_t v9 = 9, v40 = 40;
volatile uint32_t vs = 0x12345678UL;

/* C1: a computed byte, cast and widened, gets $FF as its high byte */
unsigned c1_bug(uint8_t k) { return (uint8_t)(k + 1); }
unsigned c1_fix(uint8_t k) { uint8_t b = k + 1; return b; }

/* C2: a 32-bit value narrowed to a byte keeps bits 24-31 */
int c2_bug(uint32_t a) { return (uint8_t)(a >> 16) == 0; }
int c2_fix(uint32_t a) { uint8_t b = a >> 16; return b == 0; }

/* C3: 16x16->32 multiply, the runtime's _Mul16to32 (no C shape avoids it:
 * gem4xe calls its own routine by name) */
uint32_t c3_bug(uint16_t a, uint16_t b) { return (uint32_t)a * b; }
uint32_t c3_fix(uint16_t a, uint16_t b) { return (uint32_t)a * (uint32_t)b; }

/* C4: own parameters forwarded beside the addresses of locals */
extern uint32_t c4_want;
int c4_bug(uint32_t tree, WORD obj, WORD new_state);       /* in fwd.c: inlined here it is C9 */

/* C5: a uint32 parameter forwarded as its high and low words */
extern uint32_t c5_got;
WORD c5_take(WORD h, WORD f, WORD hi, WORD lo, WORD x, WORD y);
WORD c5_bug(WORD h, WORD f, uint32_t s)
{ return c5_take(h, f, (WORD)(s >> 16), (WORD)s, 0, 0); }
WORD c5_fix(WORD h, WORD f, uint32_t s)
{ WORD hi = (WORD)(s >> 16), lo = (WORD)s; return c5_take(h, f, hi, lo, 0, 0); }

/* C6: a comma after a statement expression runs right to left */
extern char *c6_got;
void c6_put(char *p, char v);
#define PUT(p, v)   ({ c6_put((p), (v)); })
char c6_buf[4];
char *c6_bug(char *p) { (PUT(p, 'x'), p += 1); return c6_got; }
char *c6_fix(char *p) { ({ char *q_ = p; p += 1; c6_put(q_, 'x'); }); return c6_got; }

/* C7: a[3] = a[1] + k on a local uint32 array becomes a[3] += k */
volatile uint32_t v1000 = 1000;
uint32_t c7_bug(void)
{ uint32_t a[4]; a[0] = 0; a[1] = v1000; a[2] = 0; a[3] = 5; a[3] = a[1] + 13; return a[3]; }
uint32_t c7_fix(void)
{ uint32_t a[4], t; a[0] = 0; a[1] = v1000; a[2] = 0; a[3] = 5; t = a[1] + 13; a[3] = t; return a[3]; }

int dummy;

static void hex(uint32_t v)
{
    static const char d[] = "0123456789abcdef";
    char b[9];
    int i;
    for (i = 7; i >= 0; i--) { b[i] = d[(uint8_t)v & 15]; v >>= 4; }
    b[8] = 0;
    fputs(b, stdout);
}
static void show(const char *name, uint32_t want, uint32_t got)
{
    fputs(name, stdout); fputs("  want ", stdout); hex(want);
    fputs(" got ", stdout); hex(got);
    puts(want == got ? "  ok" : "  WRONG");
}
#define SHOW(name, want, got)   show((name), (want), (got))

int main(void)
{
    SHOW("C1 (uint8_t)(k + 1), k = $7F, widened", 0x80, c1_bug(v7f));
    SHOW("C1 fix: through a uint8_t local      ", 0x80, c1_fix(v7f));
    SHOW("C2 (uint8_t)(a >> 16) == 0, a = $01000000", 1, c2_bug(v24));
    SHOW("C2 fix: through a uint8_t local      ", 1, c2_fix(v24));
    SHOW("C3 (uint32_t)a * b, 9 * 40           ", 360, c3_bug(v9, v40));
    SHOW("C3 also: both operands uint32_t      ", 360, c3_fix(v9, v40));
    c4_want = 0x00025A40UL;
    SHOW("C4 own params forwarded beside &locals", 1, c4_bug(0x00025A40UL, 7, 1));
    c5_bug(1, 2, vs);
    SHOW("C5 uint32 forwarded as hi, lo words  ", 0x12345678UL, c5_got);
    c5_fix(1, 2, vs);
    SHOW("C5 fix: the words in locals first    ", 0x12345678UL, c5_got);
    SHOW("C6 (({ put(p) }), p += 1): put's p   ", (unsigned)c6_buf, (unsigned)c6_bug(c6_buf));
    SHOW("C6 fix: one ({ }), pointer kept first", (unsigned)c6_buf, (unsigned)c6_fix(c6_buf));
    SHOW("C7 a[3] = a[1] + 13, a[1] = 1000     ", 1013, c7_bug());
    SHOW("C7 fix: through a local              ", 1013, c7_fix());
    printf("END\n");
    return 0;
}
