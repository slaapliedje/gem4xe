/* p6_prog.c -- step 5a of docs/6502.md: a program in a bank of its own.
 *
 * Built with the kit alone -- src/app/gem.h and lib/gemlib.c, the 6502's
 * gates (src/app/gemabi6502.s) and start-up (src/app/crt6502.s), linked
 * whole into one 16 KB bank (src/app/gemapp6502.scm) -- and loaded by
 * A6 into a bank from the far heap (src/a6_evt.c), it knows no address of
 * the system's but the gate's.  Everything it passes is in its own bank
 * or on the shared C stack: its arrays, its parameter blocks, the
 * window's title, the text it draws, the message buffers.
 *
 * What it does, and what it leaves at $0640 for tests/emu/p6_prog.py:
 *
 *   $0640  'p' once main runs, 'W' waiting for its redraw, 'G' in its GEMDOS
 *          calls, 'D' drawn, 'a' at its alert, 'E' about to return
 *   $0641  ap_id from appl_init; $0642-3 global[0] (the AES version)
 *   $0644  the workstation handle from v_opnvwk; $0645 the window's
 *   $0646  the character height graf_handle answered
 *   $0647  the first message's type; $0648 the window it names
 *   $0649-$0650  the window's work area: x, y, w, h (two bytes each)
 *   $0651  the rectangles its redraw painted
 *   $0652  rsrc_load's answer; $0653 rsrc_gaddr's for tree 0
 *   $0654-$0657  the tree's far address
 *   $0658  object 1's ob_type, fetched
 *   $0659  object 2's ob_state, stored SELECTED and fetched back
 *   $065A-$065D  objc_offset of object 2: x, y
 *   $065E  graf_handle's cell width; $065F rsrc_free's answer
 *   $0660-1  form_alert's answer (step 5b-5); it waits at 'a' for the
 *            gate to write $0662 before it raises the alert
 *
 * and GEMDOS's (step 5b-4), every address one in its own bank:
 *
 *   $0680-1  Sversion; $0682 1 if Fgetdta gave back the DTA it set
 *   $0683    Fsfirst("*.RSC")'s answer (low byte); $0684-7 the DTA's
 *            length; $0690-$069D the DTA's name
 *   $0688-9  Fopen("P6PROG.RSC")'s handle; $068A Fread's count of the
 *            header (18 bytes, at $06A0-$06B1); $068B Fseek(0)'s answer;
 *            $068C the count of a second read of the first 4 bytes, and
 *            $06B4-$06B7 those bytes; $068E Fclose's answer
 *   $068F    Dgetpath's answer, and the path at $06B8 (8 bytes)
 *   $06C0-3  Fopen of a file that is not there: the error, a LONG
 *
 * ITS RESOURCE (step 5b-3) is P6PROG.RSC (tools/p6rsc.py), loaded into
 * the far heap: its tree is a far address (gem.h, GEMTREE), read and
 * written through far_fetch and far_store.  The text it draws is object
 * 1's string, read that way -- the same words it once carried itself, so
 * the gate's pixels say whether the read was right.
 *
 * Its redraw is what a GEM program owes its window: the AES draws the
 * frame and nothing inside it, so on WM_REDRAW the program walks the
 * window's rectangle list (WF_FIRSTXYWH, WF_NEXTXYWH) inside a
 * wind_update and paints each piece the redraw asks for -- white, and
 * its text -- clipped to it.  Without it the inside of the window shows
 * whatever was on the screen under it: window 2's title bar, here.
 *
 * and after its text it sends process 0 -- A6's application, which logs
 * every message it gets -- P6_HELLO with its ap_id and its window. */
#include "portab.h"
#include "gem.h"

#define STATUS   ((volatile unsigned char *)0x0600)
#define P6_HELLO 0x4138

static WORD work_in[11] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2 };
static WORD work_out[57];
static const char title[] = " BANKED ";
static char text[16];                   /* object 1's string, fetched */
static DTA dta;                         /* its own, in its bank */
static uint8_t hdr[18];                 /* P6PROG.RSC's header, read */
static char path[8];
/* its alert, in its bank: the default is the SECOND button, so Return
 * answers 2, which the first button's index could not fake */
static const char alert[] = "[1][FROM A BANK|ON A 6502][OK|NO]";

static void put32(uint8_t at, LONG v)
{
    STATUS[at] = (unsigned char)v;
    STATUS[at + 1] = (unsigned char)((uint32_t)v >> 8);
    STATUS[at + 2] = (unsigned char)((uint32_t)v >> 16);
    STATUS[at + 3] = (unsigned char)((uint32_t)v >> 24);
}

/* GEMDOS, from a bank (step 5b-4): the calls a program opening its own
 * file makes, and one that fails */
static void files(void)
{
    LONG r, h;
    uint8_t i;

    r = Sversion();
    STATUS[0x80] = (unsigned char)r;
    STATUS[0x81] = (unsigned char)((UWORD)r >> 8);
    Fsetdta(&dta);
    STATUS[0x82] = (unsigned char)(Fgetdta() == FAR_ARG(&dta));
    r = Fsfirst("*.RSC", 0);
    STATUS[0x83] = (unsigned char)r;
    put32(0x84, dta.d_length);
    for (i = 0; i < 14; i++)
        STATUS[0x90 + i] = (unsigned char)dta.d_fname[i];

    h = Fopen("P6PROG.RSC", 0);
    STATUS[0x88] = (unsigned char)h;
    STATUS[0x89] = (unsigned char)((uint32_t)h >> 8);
    r = Fread((WORD)h, sizeof hdr, hdr);
    STATUS[0x8A] = (unsigned char)r;
    for (i = 0; i < sizeof hdr; i++)
        STATUS[0xA0 + i] = hdr[i];
    STATUS[0x8B] = (unsigned char)Fseek(0, (WORD)h, 0);
    r = Fread((WORD)h, 4, hdr);
    STATUS[0x8C] = (unsigned char)r;
    for (i = 0; i < 4; i++)
        STATUS[0xB4 + i] = hdr[i];
    STATUS[0x8E] = (unsigned char)Fclose((WORD)h);
    for (i = 0; i < sizeof path; i++)   /* not zero: a "" must be written */
        path[i] = (char)0xFF;
    STATUS[0x8F] = (unsigned char)Dgetpath(path, 0);
    for (i = 0; i < sizeof path; i++)
        STATUS[0xB8 + i] = (unsigned char)path[i];
    put32(0xC0, Fopen("NOFILE.XYZ", 0));
}

/* *a cut to what it shares with *b; 0 if nothing */
static WORD meet(WORD *a, const WORD *b)
{
    WORD x2 = a[0] + a[2], y2 = a[1] + a[3];
    WORD bx2 = b[0] + b[2], by2 = b[1] + b[3];

    if (b[0] > a[0]) a[0] = b[0];
    if (b[1] > a[1]) a[1] = b[1];
    if (bx2 < x2) x2 = bx2;
    if (by2 < y2) y2 = by2;
    a[2] = (WORD)(x2 - a[0]);
    a[3] = (WORD)(y2 - a[1]);
    return a[2] > 0 && a[3] > 0;
}

static void put16(uint8_t at, WORD v)
{
    STATUS[at] = (unsigned char)v;
    STATUS[at + 1] = (unsigned char)((UWORD)v >> 8);
}

int main(void)
{
    WORD ap, vh, wh, wc, hc, wb, hb, x, y, w, h, ox, oy;
    GEMTREE tree = 0;
    OBJECT o;
    WORD msg[8], r[4], pxy[4];
    uint8_t pieces = 0;

    STATUS[0x40] = 'p';
    ap = appl_init();
    STATUS[0x41] = (unsigned char)ap;
    put16(0x42, global[0]);
    vh = graf_handle(&wc, &hc, &wb, &hb);
    STATUS[0x46] = (unsigned char)hc;
    v_opnvwk(work_in, &vh, work_out);
    STATUS[0x44] = (unsigned char)vh;
    STATUS[0x5E] = (unsigned char)wc;

    STATUS[0x52] = (unsigned char)rsrc_load("P6PROG.RSC");
    STATUS[0x53] = (unsigned char)rsrc_gaddr(R_TREE, 0, &tree);
    put16(0x54, (WORD)tree);
    put16(0x56, (WORD)(tree >> 16));
    far_fetch(&o, OB_ADDR(tree, 1), sizeof o);
    STATUS[0x58] = (unsigned char)o.ob_type;
    far_fetch(text, (uint32_t)o.ob_spec.index, sizeof text - 1);
    text[sizeof text - 1] = 0;
    far_fetch(&o, OB_ADDR(tree, 2), sizeof o);
    o.ob_state |= SELECTED;
    far_store(OB_ADDR(tree, 2), &o, sizeof o);
    o.ob_state = 0;
    far_fetch(&o, OB_ADDR(tree, 2), sizeof o);
    STATUS[0x59] = (unsigned char)o.ob_state;
    objc_offset(tree, 2, &ox, &oy);
    put16(0x5A, ox);
    put16(0x5C, oy);
    STATUS[0x40] = 'G';
    files();

    wh = wind_create(NAME, 30, 40, 180, 60);
    STATUS[0x45] = (unsigned char)wh;
    wind_set_str(wh, WF_NAME, title);
    wind_open(wh, 30, 40, 180, 60);

    STATUS[0x40] = 'W';
    do {
        evnt_mesag(msg);
    } while (msg[0] != WM_REDRAW);
    STATUS[0x47] = (unsigned char)msg[0];
    STATUS[0x48] = (unsigned char)msg[3];
    wind_get(wh, WF_WORKXYWH, &x, &y, &w, &h);
    put16(0x49, x);
    put16(0x4B, y);
    put16(0x4D, w);
    put16(0x4F, h);
    vswr_mode(vh, 1);
    vsf_interior(vh, FIS_SOLID);
    vsf_color(vh, 0);
    wind_update(BEG_UPDATE);
    graf_mouse(M_OFF, 0);
    wind_get(wh, WF_FIRSTXYWH, &r[0], &r[1], &r[2], &r[3]);
    while (r[2] && r[3]) {
        if (meet(r, &msg[4])) {
            pxy[0] = r[0];
            pxy[1] = r[1];
            pxy[2] = (WORD)(r[0] + r[2] - 1);
            pxy[3] = (WORD)(r[1] + r[3] - 1);
            vs_clip(vh, 1, pxy);
            vr_recfl(vh, pxy);
            v_gtext(vh, (WORD)(x + 4), (WORD)(y + 12), text);
            pieces++;
        }
        wind_get(wh, WF_NEXTXYWH, &r[0], &r[1], &r[2], &r[3]);
    }
    vs_clip(vh, 0, pxy);
    graf_mouse(M_ON, 0);
    wind_update(END_UPDATE);
    STATUS[0x51] = pieces;
    STATUS[0x40] = 'D';

    STATUS[0x40] = 'a';
    while (!STATUS[0x62])
        ;
    put16(0x60, form_alert(2, alert));

    msg[0] = P6_HELLO;
    msg[1] = ap;
    msg[2] = 0;
    msg[3] = ap;
    msg[4] = wh;
    msg[5] = msg[6] = msg[7] = 0;
    appl_write(0, 16, msg);

    STATUS[0x5F] = (unsigned char)rsrc_free();
    STATUS[0x40] = 'E';
    return 0x1234;
}
