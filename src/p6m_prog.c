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

/* ---- bank 1 ---------------------------------------------------------- */
BANK_TEXT("pb1")
int op1(int x)
{
    g_count++;
    return x + 100;
}

static int (*const ops[3])(int) = { op1, op2, op3 };

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

    STATUS[0x40] = 'a';
    while (!STATUS[0x62])
        ;
    put16(0x60, form_alert(2, alert));

    appl_exit();
    STATUS[0x40] = 'E';
    return 0x1234;
}
