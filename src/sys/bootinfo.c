/* bootinfo.c -- the boot screen.  bootinfo.h says what it is for; this
 * is how it is drawn, which is one CIO write a row on E:, the row built
 * on the stack first because forty PUTCHRs a row through the OS is
 * forty trips to the slow bus and back.
 *
 * No row is ever the full forty columns: E: wraps a fortieth character
 * onto the next row by itself and the EOL behind it would then leave a
 * blank one.  Everything is INSET columns in from the left and at most
 * WIDTH across, which is 36 -- and E: has a left margin of its own,
 * LMARGN, two as the OS sets it, which counts towards the inset: the
 * rows carry only what E: does not add, so the block sits where it was
 * drawn under a DOS that has moved the margin.
 *
 * Everything constant here is FAR, the logo and the names alike: bank
 * $00 has 2,430 bytes for every near constant the system owns
 * (src/gem4xe.scm) and a screen shown once at boot has no claim on
 * them.  The names are arrays for the reason src/sys/config.c gives --
 * a table of pointers would put the text back in bank $00.
 */
#include "portab.h"
#include <string.h>
#include "sys/bootinfo.h"
#include "sys/cio.h"
#include "sys/irq.h"
#include "sys/rapidus.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"
#include "sys/dos.h"
#include "sys/config.h"
#include "sys/clock.h"
#include "vbxe/vbxe.h"
#include "vdi/pointer.h"
#include "aes/aes.h"
#include "lang_rsc.h"
#include "version.h"

/* The screen, in columns. */
#define COLS     40
#define INSET    2                      /* in from the left, LMARGN included */
#define WIDTH    (COLS - 2 * INSET)     /* the rule, and the widest row */
#define LABEL    (LANG_BOOT_LABEL + 1)  /* the label column, gap included */
#define VALUE    (WIDTH - LABEL)        /* what is left for the value */

static WORD margin;                     /* the inset less what E: adds */
static uint8_t dos_ink;                 /* COLOR1 as DOS had it */

/* E:, and what it makes of a byte. */
#define E_IOCB    0                     /* the OS opens it on this one */
#define E_CLEAR   0x7D                  /* clear the screen, cursor home */
#define E_EOL     0x9B
#define E_INVERSE 0x80                  /* the bit that inverts a glyph */

#define CRSINH   (*(volatile uint8_t *)0x02F0)  /* 1: E: draws no cursor */
#define LMARGN   (*(volatile uint8_t *)0x0052)  /* E:'s own left margin  */
#define COLOR1   (*(volatile uint8_t *)0x02C5)  /* the OS's COLPF1 shadow:
                                                 * its VBI's first stage
                                                 * copies it, CRITIC or no */
#define COLPF1   (*(volatile uint8_t *)0xD017)  /* the ink's luminance   */
#define COLPF2   (*(volatile uint8_t *)0xD018)  /* the paper             */
#define COLBK    (*(volatile uint8_t *)0xD01A)  /* the border            */
#define PAL      (*(volatile uint8_t *)0xD014)  /* GTIA: bits 1-3 clear on PAL */
#define VCOUNT   (*(volatile uint8_t *)0xD40B)
#define SKSTAT   (*(volatile uint8_t *)0xD20F)  /* bit 2 low: a key held */
#define IRQEN    (*(volatile uint8_t *)0xD20E)  /*   bit 3 low: SHIFT    */
#define POKMSK   (*(volatile uint8_t *)0x0010)  /* the OS's IRQEN shadow */
#define COLPF3   (*(volatile uint8_t *)0xD019)  /* the logo's colour     */
#define CHBASE   (*(volatile uint8_t *)0xD409)  /* ANTIC: the glyphs' page */
#define CHBAS    (*(volatile uint8_t *)0x02F4)  /* its OS shadow         */
#define SDLSTL   (*(volatile uint16_t *)0x0230) /* the OS's display list */

#define INK      0x00                   /* GEM's black on white */
#define PAPER    0x0E

#define HOLD_SECONDS 3                  /* EmuTOS's, and enough to read */

#define LOGO_ROWS 5                     /* the logo: five rows of five */
#define LOGO_LETTERS 6                  /* cells a letter, see below   */

/* THE RAINBOW.  The logo is coloured the way this machine colours
 * things: the beam is followed down the screen and COLPF3 rewritten
 * every two lines, a hue a band, the bands walking down a step a frame.
 * The text screen cannot do it as it stands -- in ANTIC mode 2 the ink
 * takes COLPF2's hue and only COLPF1's luminance, so on white paper the
 * ink is grey or nothing -- so for the hold the logo's five rows are
 * mode 4, where a character is four two-bit cells and the cell value 3
 * is COLPF2 for a plain character and COLPF3 for an inverse one.  A
 * character set of one glyph, all eight bytes $FF, makes a space paper
 * and an inverse space the raster's colour, and the rows as E: wrote
 * them need not change at all.  The set lives at $8000: the loader's
 * staging buffer, spent before main() and in the 16 KB the speed-up
 * leaves on the motherboard bus, which is where ANTIC reads.  Nothing
 * is written for the rest of the frame: CHBASE goes to the set as the
 * first logo row begins and back to the OS's as the rule's row begins,
 * both in the horizontal blank a VCOUNT step opens with, and the OS's
 * rows above and below never see the strange set.  Interrupts are held
 * off for those forty lines and no longer, so a mouse sample cannot
 * push a write into the picture.  No display list interrupt, no
 * WSYNC: VCOUNT is polled, which needs nothing installed and nothing
 * in bank $00, and the accelerator's answer to a halted bus is not a
 * thing this screen wants to find out. */
#define GLYPHS     0x8000               /* the one-glyph set, 1 KB     */
#define DL_TEXT    8                    /* ANTIC's first line          */
#define DL_BLANK   24                   /* the OS list's three $70s    */
#define LOGO_TOP   ((DL_TEXT + DL_BLANK + 8) / 2)  /* row 1, in VCOUNT */
#define LOGO_BANDS (LOGO_ROWS * 4)      /* VCOUNT steps down the logo  */
#define LOGO_END   (LOGO_TOP + LOGO_BANDS)

/* The hues, twice each so a band is four lines: 1 to 15 is the hue
 * circle, and at this luminance every one of them shows on white. */
#define HUES 30
#define HUE_LUM 0x06
static const uint8_t FAR hues[HUES] = {
    0x10 | HUE_LUM, 0x10 | HUE_LUM, 0x20 | HUE_LUM, 0x20 | HUE_LUM,
    0x30 | HUE_LUM, 0x30 | HUE_LUM, 0x40 | HUE_LUM, 0x40 | HUE_LUM,
    0x50 | HUE_LUM, 0x50 | HUE_LUM, 0x60 | HUE_LUM, 0x60 | HUE_LUM,
    0x70 | HUE_LUM, 0x70 | HUE_LUM, 0x80 | HUE_LUM, 0x80 | HUE_LUM,
    0x90 | HUE_LUM, 0x90 | HUE_LUM, 0xA0 | HUE_LUM, 0xA0 | HUE_LUM,
    0xB0 | HUE_LUM, 0xB0 | HUE_LUM, 0xC0 | HUE_LUM, 0xC0 | HUE_LUM,
    0xD0 | HUE_LUM, 0xD0 | HUE_LUM, 0xE0 | HUE_LUM, 0xE0 | HUE_LUM,
    0xF0 | HUE_LUM, 0xF0 | HUE_LUM,
};

/* The logo rows' bytes in the OS's display list, once found; NULL
 * while the logo is plain black. */
static uint8_t *logo_dl[LOGO_ROWS];
static uint8_t phase;                   /* where the bands are this frame */

/* GEM4XE in block capitals, five rows of five cells a letter, one bit a
 * cell, the top row first. */
static const uint8_t FAR logo[LOGO_LETTERS][LOGO_ROWS] = {
    { 0x0F, 0x10, 0x13, 0x11, 0x0F },   /* G */
    { 0x1F, 0x10, 0x1E, 0x10, 0x1F },   /* E */
    { 0x11, 0x1B, 0x15, 0x11, 0x11 },   /* M */
    { 0x11, 0x11, 0x1F, 0x01, 0x01 },   /* 4 */
    { 0x11, 0x0A, 0x04, 0x0A, 0x11 },   /* X */
    { 0x1F, 0x10, 0x1E, 0x10, 0x1F },   /* E */
};

/* The machine's own names.  The version is build/version.h's, from the
 * VERSION file. */
static const char FAR s_version[] = GEM4XE_VERSION;
static const char FAR s_cpu[]     = "65C816";
static const char FAR s_rapidus[] = ", Rapidus";
static const char FAR s_mb[]      = " MB, ";
static const char FAR s_sdx[]     = "SpartaDOS X";
static const char FAR s_sparta[]  = "SpartaDOS 3";
static const char FAR s_dos2[]    = "DOS 2";
static const char FAR s_cfg[]     = CFG_FILE;
static const char FAR s_lang[]    = LANG_FILE;
static const char FAR s_antic[]   = "ANTIC";
static const char FAR s_vbxe[]    = "VBXE ";
static const char FAR s_u1mb[]    = "U1MB, ";
static const char FAR s_side[]    = "SIDE, ";
static const char FAR s_dos[]     = "DOS, ";
static const char FAR s_ps[]      = "PostScript, ";
static const char FAR s_pcl[]     = "PCL 5, ";
static const char FAR s_digit[]   = "0123456789ABCDEF";

typedef char ROW[COLS + 1];             /* one row, built and then written */

/* The first n characters of a row, and the end of the line. */
static void row_out(char *row, WORD n)
{
    row[n] = (char)E_EOL;
    cio_write(E_IOCB, row, (uint16_t)(n + 1));
}

static void blank(void)
{
    ROW row;

    row_out(row, 0);
}

static void rule(void)
{
    ROW row;
    WORD i;

    for (i = 0; i < margin; i++)
        row[i] = ' ';
    for (; i < margin + WIDTH; i++)
        row[i] = '_';
    row_out(row, i);
}

/* A label and its value.  The value is copied first: it may well be
 * lang_str's one buffer, which fetching the label would overwrite. */
static void line(WORD label, const char FAR *value)
{
    ROW row;
    char v[VALUE + 1];
    const char *l;
    WORD n, i;

    for (n = 0; n < VALUE && value[n]; n++)
        v[n] = value[n];
    v[n] = '\0';
    l = lang_str(label);
    for (i = 0; i < margin; i++)
        row[i] = ' ';
    n = margin;
    for (i = 0; i < LABEL - 1 && l[i]; i++)    /* cut, and a gap kept */
        row[n++] = l[i];
    while (n < margin + LABEL)
        row[n++] = ' ';
    for (i = 0; v[i]; i++)
        row[n++] = v[i];
    row_out(row, n);
}

/* ---- the values: built in a buffer wider than a line, and line() cuts -- */

static char *app(char *p, const char FAR *s)
{
    while (*s)
        *p++ = *s++;
    return p;
}

static char *dec(char *p, uint16_t v)
{
    char t[5];
    WORD n = 0;

    do {
        t[n++] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    while (n)
        *p++ = t[--n];
    return p;
}

static char *two(char *p, uint8_t v)    /* two digits, for a date */
{
    *p++ = (char)('0' + v / 10);
    *p++ = (char)('0' + v % 10);
    return p;
}

static char *hex2(char *p, uint8_t v)
{
    *p++ = s_digit[v >> 4];
    *p++ = s_digit[v & 0x0F];
    return p;
}

/* ---- the screen ------------------------------------------------------ */

void boot_begin(void)
{
    ROW row;
    char v[COLS], *p;
    WORD r, i, k, b;
    uint16_t tenths;

    margin = (WORD)(LMARGN < INSET ? INSET - LMARGN : 0);
    CRSINH = 1;                         /* from the next character on */
    dos_ink = COLOR1;
    COLOR1 = INK;                       /* the shadow: see bootinfo.h */
    COLPF1 = INK;
    COLPF2 = PAPER;
    COLBK  = PAPER;
    row[0] = (char)E_CLEAR;
    cio_write(E_IOCB, row, 1);
    blank();

    for (r = 0; r < LOGO_ROWS; r++) {
        for (i = 0; i < margin; i++)
            row[i] = ' ';
        k = margin;
        for (i = 0; i < LOGO_LETTERS; i++) {
            uint8_t bits = logo[i][r];
            for (b = 4; b >= 0; b--)
                row[k++] = (bits & (1 << b)) ? (char)(' ' | E_INVERSE) : ' ';
            row[k++] = ' ';             /* the gap between letters */
        }
        row_out(row, (WORD)(k - 1));    /* not the last gap */
    }
    rule();
    blank();

    line(LS_BOOT_VERSION, s_version);

    p = app(v, s_cpu);                  /* src/farload.s let it this far */
    if (rapidus.present)
        p = app(p, s_rapidus);
    *p = '\0';
    line(LS_BOOT_CPU, v);

    /* The vectors: how irq_install() reached them, or why it could not
     * (src/sys/irq.h) -- and on a Rapidus the MCR and CMCR as the
     * firmware left them, which is the board's setup in two bytes, then
     * a letter for the RAM under the ROM the copy went to (S the SRAM
     * alone, W both through write-through, M the motherboard: irq.via),
     * and after a refusal the byte that read back instead.  A report
     * from a machine no emulator has been near needs this line more
     * than any other: the native-mode vectors are what every application
     * calls in through, and this is the one place that says whether they
     * exist.  Twenty-six columns, all of them spoken for. */
    p = app(v, lang_str(irq.how == IRQ_ROM_COPIED ? LS_BOOT_IRQ_COPIED
                      : irq.how == IRQ_RAM_FOUND  ? LS_BOOT_IRQ_RAM
                      : irq.fail == IRQ_FAIL_COPY ? LS_BOOT_IRQ_NOCOPY
                      : irq.fail == IRQ_FAIL_VEC  ? LS_BOOT_IRQ_NOVEC
                                                  : LS_BOOT_NONE));
    if (rapidus.present) {
        *p++ = ' ';
        *p++ = '(';
        *p++ = '$';
        p = hex2(p, rapidus.mcr_before);
        *p++ = '/';
        *p++ = '$';
        p = hex2(p, rapidus.cmcr_before);
        *p++ = '/';
        *p++ = irq.via == IRQ_VIA_SRAM ? 'S'
             : irq.via == IRQ_VIA_BOTH ? 'W'
             : irq.via == IRQ_VIA_BUS  ? 'M' : '-';
        if (irq.fail != IRQ_FAIL_NONE) {
            *p++ = ':';
            p = hex2(p, irq.bad_byte);
        }
        *p++ = ')';
    } else if (irq.fail != IRQ_FAIL_NONE) {
        *p++ = ' ';
        *p++ = '$';
        p = hex2(p, irq.bad_byte);
    }
    *p = '\0';
    line(LS_BOOT_IRQ, v);

    /* Sixteen banks to the megabyte; one decimal, rounded. */
    tenths = (uint16_t)(((uint16_t)farmem.banks * 10 + 8) / 16);
    p = dec(v, (uint16_t)(tenths / 10));
    *p++ = '.';
    p = dec(p, (uint16_t)(tenths % 10));
    p = app(p, s_mb);
    p = app(p, lang_str(LS_BOOT_BANKS));
    *p++ = ' ';
    *p++ = '$';
    p = hex2(p, farmem.first_bank);
    *p++ = '-';
    *p++ = '$';
    p = hex2(p, farmem.last_bank);
    *p = '\0';
    line(LS_BOOT_MEMORY, v);
    /* ...and, under it, when the OS had already given out some of the
     * banks gem4xe's own code was loaded into: that memory was
     * somebody's, and is gem4xe's now -- a driver or a RAM disk there is
     * gone, and the person at the machine should hear it here, before
     * whatever it was fails later (src/sys/farmem.c, km_busy). */
    if (km_clash) {
        p = app(v, lang_str(LS_BOOT_CLASH));
        *p++ = '$';
        p = hex2(p, km_clash);
        *p = '\0';
        line(LS_BOOT_MEMORY, v);
    }

    line(LS_BOOT_DOS, dos.kind == DOS_SDX    ? s_sdx
                    : dos.kind == DOS_SPARTA ? s_sparta
                                             : s_dos2);
    if (config.found)
        line(LS_BOOT_CONFIG, s_cfg);
    else
        line(LS_BOOT_CONFIG, lang_str(LS_BOOT_DEFAULTS));
    if (lang_loaded())
        line(LS_BOOT_LANG, s_lang);
    else
        line(LS_BOOT_LANG, lang_str(LS_BOOT_BUILTIN));
}

void boot_video(int16_t video)
{
    char v[COLS], *p;

    if (video != CFG_VIDEO_VBXE) {
        line(LS_BOOT_VIDEO, s_antic);
        return;
    }
    p = app(v, s_vbxe);
    p = dec(p, vbxe_major());
    *p++ = '.';
    p = two(p, vbxe_minor_bcd());       /* 1.26, as the core numbers itself */
    *p++ = ' ';
    *p++ = '(';
    *p++ = '$';                         /* $D640: the first register, which is
                                         * the address the manuals give, not
                                         * the page vbxe_base holds */
    p = hex2(p, (uint8_t)(vbxe_base >> 8));
    p = hex2(p, (uint8_t)(vbxe_base + FX_CORE_REVISION));
    *p++ = ')';
    *p = '\0';
    line(LS_BOOT_VIDEO, v);
}

void boot_clock(void)
{
    char v[COLS], *p;
    CLOCK c;
    uint8_t card = clock_card();

    if (card == CLOCK_NONE) {
        line(LS_BOOT_CLOCK, lang_str(LS_BOOT_NONE));
        return;
    }
    clock_read(&c);
    p = app(v, card == CLOCK_U1MB ? s_u1mb : card == CLOCK_SIDE ? s_side : s_dos);
    p = dec(p, c.year);
    *p++ = '-';
    p = two(p, c.month);
    *p++ = '-';
    p = two(p, c.day);
    *p++ = ' ';
    p = two(p, c.hour);
    *p++ = ':';
    p = two(p, c.minute);
    *p++ = ':';
    p = two(p, c.second);
    *p = '\0';
    line(LS_BOOT_CLOCK, v);
}

void boot_pointer(int16_t kind)
{
    WORD s;

    switch (kind) {
    case PTR_ST_MOUSE:    s = LS_BOOT_PTR_ST;     break;
    case PTR_AMIGA_MOUSE: s = LS_BOOT_PTR_AMIGA;  break;
    case PTR_TRAKBALL:    s = LS_BOOT_PTR_CX80;   break;
    case PTR_CX77:        s = LS_BOOT_PTR_TABLET; break;
    case PTR_KOALA:       s = LS_BOOT_PTR_KOALA; break;
    case PTR_XEM1:        s = LS_BOOT_PTR_XEM1;   break;
    case PTR_JOY:         s = LS_BOOT_PTR_JOY;    break;
    default:              s = LS_BOOT_NONE;       break;
    }
    line(LS_BOOT_POINTER, lang_str(s));
}

void boot_printer(void)
{
    char v[COLS + CFG_PRINTTO_MAX], *p;

    if (config.printer == CFG_PRINT_NONE) {
        line(LS_BOOT_PRINTER, lang_str(LS_BOOT_NONE));
        return;
    }
    p = app(v, config.printer == CFG_PRINT_PS ? s_ps : s_pcl);
    p = app(p, config.printto);
    *p = '\0';
    line(LS_BOOT_PRINTER, v);
}

/* ---- the hold -------------------------------------------------------- */

/* VCOUNT, read into a word.  The polls below compare the word, never
 * the byte: a spin loop that compares a byte and is followed by 16-bit
 * code is cc65816 5.18's B16 (tools/ccbug) -- the width switch lands
 * before the back edge, and the second pass reads VCOUNT as a word,
 * takes three bytes for the compare's two and runs into the branch's
 * operand.  This costs a call per poll, which at 20 MHz is nothing. */
static uint16_t vcount(void)
{
    return VCOUNT;
}

/* The logo's rows to mode 4, if the OS's list is the one it builds for
 * GRAPHICS 0: blank lines, then a mode-2 instruction a row, the first
 * carrying the address.  Walked, not assumed -- a list with anything
 * else in it leaves the logo black, which is a boot screen too.  Done
 * with the beam below the logo, so no frame shows a mode-4 row with
 * the OS's set, whose space is empty in both colours. */
static void logo_on(void)
{
    uint8_t *dl = (uint8_t *)SDLSTL, *p = dl;
    uint8_t *rows[LOGO_ROWS + 1];
    WORD r;

    while (*p == 0x70)
        p++;
    for (r = 0; r <= LOGO_ROWS; r++) {  /* the blank row, then the logo */
        if ((*p & 0x0F) != 0x02)
            return;
        rows[r] = p;
        p += (*p & 0x40) ? 3 : 1;       /* an address follows an LMS */
    }
    memset((void *)GLYPHS, 0, 1024);
    memset((void *)GLYPHS, 0xFF, 8);
    while (vcount() < LOGO_END)
        ;
    for (r = 0; r < LOGO_ROWS; r++) {
        logo_dl[r] = rows[r + 1];
        *logo_dl[r] = (uint8_t)((*logo_dl[r] & 0xF0) | 0x04);
    }
}

static void logo_off(void)
{
    WORD r;

    if (!logo_dl[0])
        return;
    while (vcount() < LOGO_END)           /* this frame's rows are drawn */
        ;
    for (r = 0; r < LOGO_ROWS; r++)
        *logo_dl[r] = (uint8_t)((*logo_dl[r] & 0xF0) | 0x02);
    CHBASE = CHBAS;
}

/* One frame: the wait for the top of the logo, then the beam followed
 * down it.  Each band's colour is fetched before its line is waited
 * for, so the store is the first thing after the poll, in the blank. */
static void frame(void)
{
    uint16_t line;
    uint8_t i, c;

    while (vcount() >= LOGO_TOP - 1)      /* the rest of this frame */
        ;
    while (vcount() < LOGO_TOP - 1)       /* the OS's blank lines */
        ;
    if (!logo_dl[0]) {
        while (vcount() < LOGO_TOP)
            ;
        return;
    }
    cpu_sei();
    i = phase;
    c = hues[i];
    line = LOGO_TOP;
    while (vcount() < line)
        ;
    CHBASE = GLYPHS >> 8;
    COLPF3 = c;
    while (++line < LOGO_END) {
        if (++i == HUES)
            i = 0;
        c = hues[i];
        while (vcount() < line)
            ;
        COLPF3 = c;
    }
    while (vcount() < line)               /* the rule's row: the OS's set */
        ;
    CHBASE = CHBAS;
    cpu_cli();
    phase = (uint8_t)(phase ? phase - 1 : HUES - 1);    /* down a band */
}

static uint8_t key_held(void)
{
    return (uint8_t)((SKSTAT & 0x04) == 0);
}

static uint8_t shift_held(void)
{
    return (uint8_t)((SKSTAT & 0x08) == 0);
}

/* The key that ended the hold is not a keystroke for the desktop: out of
 * the handler's ring, and out of POKEY's own latch (the bit low then
 * high, as the OS clears it).  POKMSK is kept in step with IRQEN by both
 * regimes (src/sys/irq.c), so this changes nothing else. */
static void kb_drain(void)
{
    irq_kb_head = irq_kb_tail;
    IRQEN = (uint8_t)(POKMSK & ~0x40);
    IRQEN = POKMSK;
}

void boot_end(void)
{
    ROW row;
    const char *h;
    WORD n, i, k;
    uint16_t frames, hold;
    uint8_t paused = 0;

    rule();
    blank();
    /* The hint: inverse, centred, as EmuTOS sets it. */
    h = lang_str(LS_BOOT_HOLD);
    n = (WORD)strlen(h);
    if (n > WIDTH)
        n = WIDTH;
    k = (WORD)(margin + (WIDTH - n) / 2);
    for (i = 0; i < k; i++)
        row[i] = ' ';
    for (i = 0; i < n; i++)
        row[k + i] = (char)(h[i] | E_INVERSE);
    row_out(row, (WORD)(k + n));
    CRSINH = 0;                         /* DOS gets its cursor back */

    /* Three seconds of frames -- 50 or 60 to the second -- any key ends
     * it, and SHIFT holds it for as long as SHIFT is held, the rainbow
     * running all the while. */
    hold = (uint16_t)(((PAL & 0x0E) == 0 ? 50 : 60) * HOLD_SECONDS);
    logo_on();
    frames = 0;
    while (!key_held()) {
        frame();
        if (shift_held())
            paused = 1;
        else if (paused || ++frames >= hold)
            break;
    }
    logo_off();
    kb_drain();
    COLOR1 = dos_ink;                   /* the OS's VBI restores the rest */
}
