/* a6_tree.c -- step 4c of docs/6502.md: the AES's window manager and menu
 * bar on a 6502.  Called by src/a6_aes.c once the AES has started on its
 * one process; banked.
 *
 * Two trees are written into far memory, where rsrc_load would put a
 * resource's, by tree_put: the desk (one patterned box the size of the
 * screen, the tree wind_set(WF_NEWDESK) names) and a menu bar laid out as
 * the Resource Construction Set lays one out for this screen's 6x6 cell
 * (bar gl_hchar+2 high, titles gl_hchar+3, the first title indented two
 * cells, the Desk box's eight children).  Then the window manager's calls,
 * test-m8's: two windows, the second over the first, each named; and
 * menu_bar.  The handles wm_create answers go to $0660.
 */
#include "portab.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/vdidev.h"
#include "aes/aes.h"
#include "aes/proc.h"
#include "sys/farmem.h"
#include "sys/hiprobe.h"           /* farmem_probe */
#include "sys/irq.h"
#include "sys/dos.h"                /* dos_ident */
#include "sys/gemdos.h"             /* gemdos_init */
#include <string.h>

void a6_tree(void);
extern unsigned char b6_count;

#define STATUS ((volatile unsigned char *)0x0600)

/* One object: links, type, flags, state, the spec when it is not a
 * string, the box. */
typedef struct {
    WORD next, head, tail, type, flags, state;
    uint32_t spec;
    WORD x, y, w, h;
} OBDEF;

/* The table and its strings into one far block: the objects, then the
 * strings, each string object's ob_spec its far address.  0 when the far
 * heap has not the room.  `str` is every object's string one after the
 * other, each with its NUL, an empty one for an object that has none. */
#define STR_MAX 24                      /* the longest, NUL in */
static OBTREE tree_put(const OBDEF *d, WORD n, const char *str)
{
    uint32_t size = (uint32_t)n * sizeof(OBJECT), far, at;
    const char *s;
    char buf[STR_MAX];
    WORD i;

    for (i = 0, s = str; i < n; i++, s += strlen(s) + 1)
        if (*s)
            size += strlen(s) + 1;
    far = far_alloc(size);
    if (!far)
        return 0;
    at = far + (uint32_t)n * sizeof(OBJECT);
    for (i = 0, s = str; i < n; i++, s += strlen(s) + 1) {
        OBTREE t = (OBTREE)far;
        uint32_t spec = d[i].spec;

        if (*s) {
            /* through a buffer on the stack, below the window: far_put
             * maps the far side over this bank, where `s` is */
            uint16_t len = (uint16_t)(strlen(s) + 1);
            memcpy(buf, s, len);
            far_put(at, (const uint8_t *)buf, len);
            spec = at;
            at += len;
        }
        OB_SET(t, i, ob_next, d[i].next);
        OB_SET(t, i, ob_head, d[i].head);
        OB_SET(t, i, ob_tail, d[i].tail);
        OB_SET(t, i, ob_type, d[i].type);
        OB_SET(t, i, ob_flags, d[i].flags);
        OB_SET(t, i, ob_state, d[i].state);
        OB_SET(t, i, ob_spec, spec);
        OB_SET(t, i, ob_x, d[i].x);
        OB_SET(t, i, ob_y, d[i].y);
        OB_SET(t, i, ob_width, d[i].w);
        OB_SET(t, i, ob_height, d[i].h);
    }
    return (OBTREE)far;
}

/* The tables are this bank's own (BANK_DATA): only tree_put, here, reads
 * them, and resident memory has not the room since the interrupt
 * handlers came in (step 4e).  The strings too since GEMDOS came
 * (step 5b-4): tree_put copies each through its stack.
 *
 * The desk: the box test-m7's desk() is, the size of this screen. */
static const OBDEF desk[1] BANK_DATA("far") = {
    { -1, -1, -1, G_BOX, LASTOB, NORMAL, 0x00001148UL, 0, 0, 320, 192 },
};
static const char desk_str[] BANK_DATA("far") = "";

/* The menu bar: test-m9's shape at 6x6.  Objects 0-6 are the AES's
 * fixed positions (the screen, the bar, the titles' box, the titles, the
 * drop-downs' box); the Desk box has its eight children. */
#define MW 120                          /* the Desk box: 20 cells */
static const OBDEF menu[21] BANK_DATA("far") = {
    /* next head tail  type      flags   state     spec           x   y    w    h */
    { -1,   1,   6, G_IBOX,   NONE,   NORMAL,   0,            0,  0, 320, 192 },  /* 0 */
    {  6,   2,   2, G_BOX,    NONE,   NORMAL,   0x00001100UL, 0,  0, 320,   8 },  /* 1 bar */
    {  1,   3,   5, G_IBOX,   NONE,   NORMAL,   0,           12,  0, 108,   9 },  /* 2 */
    {  4,  -1,  -1, G_TITLE,  NONE,   NORMAL,   0,            0,  0,  36,   9 },  /* 3 Desk */
    {  5,  -1,  -1, G_TITLE,  NONE,   NORMAL,   0,           36,  0,  36,   9 },  /* 4 File */
    {  2,  -1,  -1, G_TITLE,  NONE,   NORMAL,   0,           72,  0,  36,   9 },  /* 5 View */
    {  0,   7,  19, G_IBOX,   NONE,   NORMAL,   0,            0,  9, 320, 183 },  /* 6 */
    { 16,   8,  15, G_BOX,    NONE,   NORMAL,   0x00FF1100UL,12,  0,  MW,  48 },  /* 7 Desk */
    {  9,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0,  0,  MW,   6 },
    { 10,  -1,  -1, G_STRING, NONE,   DISABLED, 0,            0,  6,  MW,   6 },
    { 11,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 12,  MW,   6 },
    { 12,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 18,  MW,   6 },
    { 13,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 24,  MW,   6 },
    { 14,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 30,  MW,   6 },
    { 15,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 36,  MW,   6 },
    {  7,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0, 42,  MW,   6 },
    { 19,  17,  18, G_BOX,    NONE,   NORMAL,   0x00FF1100UL,48,  0,  60,  12 },  /* 16 File */
    { 18,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0,  0,  60,   6 },
    { 16,  -1,  -1, G_STRING, NONE,   NORMAL,   0,            0,  6,  60,   6 },
    {  6,  20,  20, G_BOX,    NONE,   NORMAL,   0x00FF1100UL,84,  0,  60,   6 },  /* 19 View */
    { 19,  -1,  -1, G_STRING, LASTOB, CHECKED,  0,            0,  0,  60,   6 },
};
static const char menu_str[] BANK_DATA("far") =
    "\0" "\0" "\0" " Desk \0" " File \0" " View \0" "\0" "\0"
    "  About gem4xe...\0" "--------------------\0" "1\0" "2\0" "3\0" "4\0" "5\0" "6\0"
    "\0" "  Open\0" "  Quit\0" "\0" "  Icons";

#define KINDS (NAME | CLOSER | FULLER | MOVER | INFO | SIZER)

static void name(WORD wh, WORD field, const char *s)
{
    WORD w[4];
    uint16_t len = (uint16_t)(strlen(s) + 1);
    uint32_t far = far_alloc(len);

    far_put(far, (const uint8_t *)s, len);
    w[0] = (WORD)(far >> 16);
    w[1] = (WORD)far;
    w[2] = w[3] = 0;
    wm_set(wh, field, w);
}

void a6_tree(void)
{
    OBTREE d = tree_put(desk, 1, desk_str);
    OBTREE m = tree_put(menu, 21, menu_str);
    WORD w[4];
    GRECT full, r;

    STATUS[0x5C] = (unsigned char)(d != 0);
    STATUS[0x5D] = (unsigned char)(m != 0);
    if (!d || !m)
        return;
    STATUS[3] = 'a';
    w[0] = (WORD)((uint32_t)d >> 16);
    w[1] = (WORD)(uint32_t)d;
    w[2] = ROOT;
    w[3] = 0;
    wm_set(0, WF_NEWDESK, w);

    full = gl_rfull;
    STATUS[3] = 'b';
    STATUS[0x60] = (unsigned char)wm_create(KINDS, &full);
    name(1, WF_NAME, "First");
    name(1, WF_INFO, "a window on a 6502");
    r.g_x = 10; r.g_y = 20; r.g_w = 200; r.g_h = 110;
    STATUS[3] = 'c';
    wm_open(1, &r);

    STATUS[0x61] = (unsigned char)wm_create(NAME | MOVER | CLOSER, &full);
    name(2, WF_NAME, "Second");
    r.g_x = 100; r.g_y = 70; r.g_w = 200; r.g_h = 100;
    STATUS[3] = 'd';
    wm_open(2, &r);

    STATUS[3] = 'e';
    mn_bar(m, TRUE);
    STATUS[3] = 'f';
}

/* src/a6_aes.c's start, but for ctx_init, which main makes in its own
 * frame.  First the VDI and the process records ... */
void a6_boot(void)
{
    /* the records with the AES's other window-safe state (zwin, LowRam
     * in tools/bsp6502/a6.scm): HiRam has not the room */
    static SECTION("zwin") char proc_store[PROC_STORE];

    STATUS[0] = 'A';
    STATUS[1] = '6';
    STATUS[2] = 0;
    STATUS[8] = b6_count;

    dos_ident();                        /* as src/gem.c: first */
    farmem_probe();
    STATUS[9] = (unsigned char)farmem.banks;
    vdev = &vdev_antic;
    STATUS[3] = '1';
    vdi_font_default();
    vdi_init();
    STATUS[3] = '2';

    proc_init(proc_store);
    ctx_make(&proc_app->p_ctx, 0);
}

/* ... then, the context made, the AES as src/gem.c starts it, and the
 * screen test-a6 holds to the model. */
void a6_aes_up(void)
{
    STATUS[3] = '3';
    gsx_start();
    /* The handlers BEFORE ev_init, as src/gem.c has them: irq_install
     * finds the video standard, and ev_init takes its tick length from
     * the VDI, which answers from irq.pal -- after, a PAL machine's 20 ms
     * tick was taken for NTSC's 17 and every timer and the double-click
     * window ran 18% long (test-e6, step 4f). */
    irq_install();
    STATUS[3] = '4';
    ev_init();
    STATUS[3] = '5';
    wm_init();
    STATUS[3] = '6';
    mn_init();
    gemdos_init();                      /* step 5b-4: its far state */
    STATUS[3] = '7';
    a6_tree();
}
