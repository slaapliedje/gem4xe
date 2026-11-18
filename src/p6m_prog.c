/* p6m_prog.c -- step 5c-1 of docs/6502.md: a program of several banks.
 *
 * Built with the kit (src/app/gem.h, gemlib.c) like src/p6_prog.c, but
 * linked by src/app/gemappm6502.scm: its code in three banks of its own
 * (BANK_TEXT below; gemlib.c in bank 2), its veneers, constants, data
 * and C stack in the RAM under the OS ROM (src/app/crt6502m.s), and its
 * cross-bank calls through _pcall.  A6 loads it as P6PROG.G6A from
 * a6m-boot.atr into three banks from the far heap (src/a6_evt.c).
 *
 * What it does, and what it leaves for tests/emu/p6m_prog.py:
 *
 *   $0640  'p' once main runs, 'x' its calls made, 'a' at its alert,
 *          'E' about to return
 *   $0641  appl_init's ap_id
 *   $0642-3  chain(7): bank 1 to bank 2 to bank 3 and back, with a global
 *            initialised to 5: 7 * 3 + 5 = 26
 *   $0644-5  down(10): bank 2 and bank 3 calling each other ten deep,
 *            10 + 9 + ... + 1 = 55
 *   $0646-7  the sum of ops[k](k + 1) through a table of function
 *            pointers, one in each bank: 101 + 4 + 2 = 107
 *   $0648    the global every bank's functions counted their calls in
 *   $0650-$065F  the string bank 3's name3() points at
 *   $0660-1  form_alert's answer: Return, the default, the second; it
 *            waits at 'a' for the gate to write $0662
 *   $0670    Fread's count of P6PROG.RSC's first 18 bytes, read into a
 *            buffer in the RAM under the ROM, copied to $0680-$0691
 *
 * and its far memory through gem.h's FGET/FSET and fa_* (step 5c-2,
 * src/app/farm6502.c), read back both through them and through the
 * system's far_fetch, which maps the far heap its own way:
 *
 *   $06A0-3  Malloc(20000)'s far address
 *   $06A4    record 0 through FGET: 1 if a, b and c are as FSET put them
 *   $06A5    record 1300 (past the first 16 KB piece): 1 if as put
 *   $06A6    8 bytes put across the piece boundary, read back whole: 1
 *   $06A7    1 if far_fetch saw all three as written
 *   $06A8-$06AF  the 8 bytes far_fetch read across the boundary
 *   $06B0    Fread's count of P6PROG.RSC's first 18 bytes straight into
 *            the far block (gem.h's FA_PARAM: a far address, as it is)
 *   $06B1    1 if they are the bytes the near Fread read
 *   $06B2    Mfree's answer for the block, by its far address (low byte)
 *
 * Every pointer it hands the system is to the RAM under the ROM -- its
 * parameter arrays, the file's name, the buffer, the alert's text -- so
 * the system reads and writes them with the ROM out, as it runs. */
#include "portab.h"
#include "gem.h"

#define STATUS   ((volatile unsigned char *)0x0600)

static int g_add = 5;                   /* data: an initial value */
static uint8_t g_count;                 /* bss */
static uint8_t buf[18];                 /* Fread's, under the ROM */
static const char alert[] = "[1][SEVERAL BANKS|UNDER THE ROM][YES|NO]";
static const char three[] = "BANK THREE";
static const char across[] = "ABCDEFGH";

typedef struct {                        /* 13 bytes: record 1300 is past 16 KB */
    WORD a;
    LONG b;
    uint8_t c;
    char s[6];
} FREC;

static void put16(uint8_t at, WORD v)
{
    STATUS[at] = (unsigned char)v;
    STATUS[at + 1] = (unsigned char)((UWORD)v >> 8);
}

/* ---- bank 3 ---------------------------------------------------------- */
BANK_TEXT("pb3")
int mul3(int x)
{
    g_count++;
    return x * 3;
}

int down2(int n);

int down3(int n)
{
    g_count++;
    return n ? n + down2(n - 1) : 0;
}

int op3(int x)
{
    g_count++;
    return x - 1;
}

const char *name3(void)
{
    g_count++;
    return three;
}

/* ---- bank 2 ---------------------------------------------------------- */
BANK_TEXT("pb2")
int chain(int x)
{
    g_count++;
    return mul3(x) + g_add;
}

int down2(int n)
{
    g_count++;
    return n ? n + down3(n - 1) : 0;
}

int op2(int x)
{
    g_count++;
    return x * 2;
}

/* ---- bank 2: the far memory (step 5c-2) ------------------------------ */
static void put32(uint8_t at, uint32_t v)
{
    uint8_t k;

    for (k = 0; k < 4; k++, v >>= 8)
        STATUS[at + k] = (unsigned char)v;
}

void far_mem(void)
{
    LONG blk = Malloc(20000L);
    FPTR(FREC) r0 = FP_OF(FREC, blk);
    FPTR(FREC) r1 = FIDX(FREC, r0, 1300);
    /* four bytes before the next 16 KB piece starts, wherever Malloc's
     * block began: the 8 bytes straddle it */
    uint32_t edge = ((uint32_t)blk | 0x3FFFu) + 1u - 4u;
    char got[8];
    FREC rec;
    uint8_t k, ok;

    put32(0xA0, (uint32_t)blk);
    if (!blk)
        return;
    FSET(FREC, r0, a, 0x1234);
    FSET(FREC, r0, b, 0x89ABCDEFL);
    FSET(FREC, r0, c, 0x5A);
    fa_put(FFLD(FREC, r0, s), "HELLO", 6);
    FSET(FREC, r1, a, 0x7777);
    FSET(FREC, r1, b, 0x01020304L);
    FSET(FREC, r1, c, 0xA5);
    fa_put(edge, across, 8);

    STATUS[0xA4] = (unsigned char)(FGET(FREC, r0, a) == 0x1234
                                   && FGET(FREC, r0, b) == 0x89ABCDEFL
                                   && FGET(FREC, r0, c) == 0x5A);
    STATUS[0xA5] = (unsigned char)(FGET(FREC, r1, a) == 0x7777
                                   && FGET(FREC, r1, b) == 0x01020304L
                                   && FGET(FREC, r1, c) == 0xA5);
    fa_get(got, edge, 8);
    ok = 1;
    for (k = 0; k < 8; k++)
        if (got[k] != across[k])
            ok = 0;
    STATUS[0xA6] = ok;

    /* the system's view: far_fetch, gate 'F' (src/sys/abi.c) */
    ok = 1;
    far_fetch(&rec, (uint32_t)r0, sizeof rec);
    if (rec.a != 0x1234 || rec.b != 0x89ABCDEFL || rec.c != 0x5A || rec.s[0] != 'H')
        ok = 0;
    far_fetch(&rec, (uint32_t)r1, sizeof rec);
    if (rec.a != 0x7777 || rec.b != 0x01020304L || rec.c != 0xA5)
        ok = 0;
    far_fetch(got, edge, 8);
    for (k = 0; k < 8; k++)
        STATUS[0xA8 + k] = (unsigned char)got[k];
    STATUS[0xA7] = ok;

    /* a far address handed to GEMDOS as it is (gem.h, FA_PARAM) */
    {
        LONG h = Fopen("P6PROG.RSC", 0);
        uint8_t far8[18];

        if (h >= 0) {
            STATUS[0xB0] = (unsigned char)Fread((WORD)h, sizeof far8, (uint32_t)blk + 100u);
            Fclose((WORD)h);
            fa_get(far8, (uint32_t)blk + 100u, sizeof far8);
            ok = 1;
            for (k = 0; k < sizeof far8; k++)
                if (far8[k] != buf[k])
                    ok = 0;
            STATUS[0xB1] = ok;
        }
    }
    STATUS[0xB2] = (unsigned char)Mfree(blk);
}

/* ---- bank 1 ---------------------------------------------------------- */
BANK_TEXT("pb1")
int op1(int x)
{
    g_count++;
    return x + 100;
}

static int (*const ops[3])(int) = { op1, op2, op3 };

void far_mem(void);

int main(void)
{
    WORD ap, k, sum;
    LONG h;
    const char *s;

    STATUS[0x40] = 'p';
    ap = appl_init();
    STATUS[0x41] = (unsigned char)ap;

    put16(0x42, (WORD)chain(7));
    put16(0x44, (WORD)down2(10));
    sum = 0;
    for (k = 0; k < 3; k++)
        sum = (WORD)(sum + ops[k](k + 1));
    put16(0x46, sum);
    s = name3();
    for (k = 0; k < 16 && s[k]; k++)
        STATUS[0x50 + k] = (unsigned char)s[k];
    STATUS[0x48] = g_count;
    STATUS[0x40] = 'x';

    h = Fopen("P6PROG.RSC", 0);
    if (h >= 0) {
        STATUS[0x70] = (unsigned char)Fread((WORD)h, sizeof buf, buf);
        Fclose((WORD)h);
        for (k = 0; k < (WORD)sizeof buf; k++)
            STATUS[0x80 + k] = buf[k];
    }

    far_mem();

    STATUS[0x40] = 'a';
    while (!STATUS[0x62])
        ;
    put16(0x60, form_alert(2, alert));

    appl_exit();
    STATUS[0x40] = 'E';
    return 0x1234;
}
