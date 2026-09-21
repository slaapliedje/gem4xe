/* m35_cpx.c -- the smallest control panel extension, for test-m35.
 *
 * It proves the contract and nothing else: that a separately linked
 * module is loaded, entered through its crt so its data is real, fills
 * the panel's header, publishes a vtable, stays resident, and can then
 * be CALLED BACK INTO through that vtable with its own globals intact.
 *
 * THE LAST PART IS THE WHOLE TEST.  Everything before it would also be
 * true of a module whose data was never initialised, or one whose
 * saveds prologue was missing -- both of which fail only later, when
 * something reads a global.  So this module keeps a counter and a
 * signature in initialised data, and cpx_call reports both: a wrong
 * signature means the crt never ran, and a counter that does not
 * advance means the call did not reach this module at all.
 */
#include "cpx.h"

#define M35_SIG   0x3535

/* INITIALISED data, deliberately -- it is installed by the crt walking
 * data_init_table and is not in the image, so a module entered anywhere
 * but its crt reads whatever was here before. */
static WORD m35_sig = M35_SIG;
static WORD m35_calls = 0;
static WORD m35_drawn = 0;

/* What the gate reads.  These are this module's own globals, found the
 * way a gate finds any program's. */
WORD m35_seen_hdr;        /* 1 once cpx_init has filled the header */
WORD m35_seen_call;       /* how many times cpx_call has been entered */
WORD m35_sig_at_call;     /* what m35_sig read DURING cpx_call */

static SAVEDS WORD m35_cpx_call(const GRECT *r)
{
    (void)r;
    m35_calls++;
    m35_seen_call = m35_calls;
    m35_sig_at_call = m35_sig;          /* the proof: our data, from here */
    return 1;
}

static SAVEDS void m35_cpx_draw(const GRECT *clip)
{
    (void)clip;
    m35_drawn++;
}

static SAVEDS void m35_cpx_close(WORD flag)
{
    (void)flag;
}

static CPXINFO m35_info = {
    m35_cpx_call, m35_cpx_draw, 0, 0, 0, 0, 0, 0, 0, m35_cpx_close
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
