/* m35_cpx.c -- an EVENT control panel extension, for test-m35.
 *
 * The worked example of the harder half of the contract, and the gate
 * for it.  GENERAL.CPX is a form CPX: it runs its own form_do and is
 * finished when cpx_call returns.  This one draws itself, returns 1, and
 * is then driven by the panel one event at a time until it says stop
 * (src/app/cpx.h; the panel's loop is cp_drivecpx in src/apps/cpanel.c).
 *
 * WHAT IT PROVES, and each of these would otherwise fail silently:
 *
 *   ITS DATA IS REAL.  m35_sig is INITIALISED data, installed by this
 *   module's own crt walking data_init_table -- it is not in the image.
 *   Every entry below reads it and records what it saw, so a module
 *   entered without its crt, or one whose `saveds` prologue went
 *   missing, reports a wrong signature rather than working by luck.
 *
 *   THE HOST REACHES EVERY ENTRY.  A count per entry, so a forwarding
 *   loop that quietly drops timers -- or calls cpx_key for a button --
 *   is a number that did not move rather than a dialog that feels odd.
 *
 *   AND `quit` IS HONOURED.  It closes on a key, and the panel must stop
 *   asking: m35_after_quit counts anything that arrives afterwards and
 *   must stay 0.
 *
 * It draws a real box rather than nothing, because a module that draws
 * nothing cannot be told from one that was never called.  The tree is
 * two objects built here: this module has no resource and no workstation
 * of its own -- a CPX draws through the AES's, which objc_draw uses.
 */
#include "cpx.h"

#define M35_SIG   0x3535

/* INITIALISED, deliberately: see above. */
static WORD m35_sig = M35_SIG;

/* What the gate reads. */
WORD m35_seen_hdr;        /* cpx_init filled the header */
WORD m35_n_call;          /* ...and each entry the panel reached */
WORD m35_n_key;
WORD m35_n_button;
WORD m35_n_timer;
WORD m35_n_draw;
WORD m35_n_close;
WORD m35_after_quit;      /* anything at all after quit was set: must be 0 */
WORD m35_sig_seen;        /* m35_sig, read from inside a forwarded call */
WORD m35_got_x, m35_got_y, m35_got_w, m35_got_h;   /* the GRECT as read */

static WORD m35_quit;     /* our own copy, to notice a host that ignores it */

static OBJECT m35_tree[2];
static const char m35_msg[] = " Event CPX -- press a key ";

static void m35_note(void)
{
    if (m35_quit)
        m35_after_quit++;
    m35_sig_seen = m35_sig;
}

static SAVEDS void m35_cpx_call(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_n_call++;
    m35_note();

    m35_tree[0].ob_next = NIL;
    m35_tree[0].ob_head = 1;
    m35_tree[0].ob_tail = 1;
    m35_tree[0].ob_type = G_BOX;
    m35_tree[0].ob_flags = NONE;
    m35_tree[0].ob_state = OUTLINED;
    m35_tree[0].ob_spec.index = 0x00021100L;
    m35_got_x = pb->rect.g_x; m35_got_y = pb->rect.g_y;
    m35_got_w = pb->rect.g_w; m35_got_h = pb->rect.g_h;
    m35_tree[0].ob_x = (WORD)(pb->rect.g_x + 24);
    m35_tree[0].ob_y = (WORD)(pb->rect.g_y + 96);
    m35_tree[0].ob_width = (WORD)(sizeof m35_msg * 8);
    m35_tree[0].ob_height = 24;

    m35_tree[1].ob_next = 0;
    m35_tree[1].ob_head = NIL;
    m35_tree[1].ob_tail = NIL;
    m35_tree[1].ob_type = G_STRING;
    m35_tree[1].ob_flags = LASTOB;
    m35_tree[1].ob_state = NORMAL;
    m35_tree[1].ob_spec.index = (int32_t)(uint32_t)(const char FAR *)m35_msg;
    m35_tree[1].ob_x = 4;
    m35_tree[1].ob_y = 8;
    m35_tree[1].ob_width = (WORD)((sizeof m35_msg - 1) * 8);
    m35_tree[1].ob_height = 8;

    objc_draw(m35_tree, ROOT, MAX_DEPTH,
              m35_tree[0].ob_x, m35_tree[0].ob_y,
              m35_tree[0].ob_width, m35_tree[0].ob_height);
    pb->ret = 1;                        /* an EVENT CPX: drive me */
}

static SAVEDS void m35_cpx_key(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_n_key++;
    m35_note();
    m35_quit = 1;
    pb->quit = 1;                       /* any key closes it */
}

static SAVEDS void m35_cpx_button(uint32_t pbaddr)
{
    (void)pbaddr;
    m35_n_button++;
    m35_note();
}

static SAVEDS void m35_cpx_timer(uint32_t pbaddr)
{
    (void)pbaddr;
    m35_n_timer++;
    m35_note();
}

static SAVEDS void m35_cpx_draw(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;

    m35_n_draw++;
    m35_note();
    objc_draw(m35_tree, ROOT, MAX_DEPTH, pb->rect.g_x, pb->rect.g_y,
              pb->rect.g_w, pb->rect.g_h);
}

static SAVEDS void m35_cpx_close(uint32_t pbaddr)
{
    (void)pbaddr;
    m35_n_close++;
    m35_sig_seen = m35_sig;             /* not m35_note: close IS after quit */
}

static CPXINFO m35_info = {
    m35_cpx_call, m35_cpx_draw, 0, m35_cpx_timer, m35_cpx_key,
    m35_cpx_button, 0, 0, 0, m35_cpx_close
};

CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr)
{
    WORD i;
    static const char title[] = "Test CPX";

    (void)pb;
    hdr->magic = CPX_MAGIC;
    hdr->flags = 0;
    hdr->cpx_id = 0x4D333500L;          /* 'M35\0' */
    hdr->cpx_version = 1;
    for (i = 0; title[i] && i < 17; i++)
        hdr->title_txt[i] = title[i];
    hdr->title_txt[i] = 0;
    for (i = 0; title[i] && i < 13; i++)
        hdr->i_text[i] = title[i];
    hdr->i_text[i] = 0;
    m35_seen_hdr = 1;
    return &m35_info;
}
