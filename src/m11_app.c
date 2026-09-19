/* m11_app.c -- the Phase 10 gate application.
 *
 * A gem4xe application, linked against nothing of gem4xe's
 * (src/app/gemapp.scm, src/app/gem.h): it reaches the VDI and the AES
 * through the two COP entries and nothing else.  The test runner loads
 * it from the blob tools/mkg4a.py packed into the image, relocates it
 * into the bank-$00 pool and a far bank, and calls it; it makes the calls
 * a small GEM program makes -- appl_init, graf_handle, a virtual
 * workstation, some drawing, an object tree, a window with a timer wait
 * inside it, and back out -- and writes what every call returned into
 * results[], one record per call in the runner's RESULT format
 * (src/m3_vdi.c), so that the harness can read them out of the pool by
 * symbol and compare them with the reference's, exactly as it compares
 * the runner's own.
 *
 * Every array the records are made from is this program's own -- the
 * bindings in src/app/gemlib.c leave them as the call left them -- so a
 * record here is a record of what came back THROUGH the ABI's copy-out,
 * not of gem4xe's internal state.
 *
 * After the AES is done it asks GEMDOS -- the third entry, COP #$44 --
 * the questions a desktop asks first: the version, the drive, how many
 * entries the boot disk's directory has, what a missing file answers,
 * how much memory there is.  Those go into dosres[], and ndos counts the
 * calls so the harness can reconcile gem4xe's COP count with the
 * application's.
 */
#include "portab.h"
#include "gem.h"

#define NREC       18
#define REC_WORDS  20
#define REC_INTOUT 15

WORD results[NREC][REC_WORDS];
WORD ncalls;
WORD dosres[8];
WORD ndos;
WORD foreign;               /* Y after a COP that is not gem4xe's: m11_cop.s */
/* objc_sysvar's answers.  NOT recorded into results[]: every entry there
 * is compared against tools/aesref.py, and this call's answers are
 * constants a specification fixes (Compendium 6.121) rather than
 * behaviour a model computes -- so the gate reads them here and asserts
 * them directly, and the compared sequence is left alone. */
WORD sv_ad3d, sv_ad3d1, sv_ad3d2;   /* AD3DVALUE: return, and the two values */
WORD sv_lk3d, sv_lk3d1, sv_lk3d2;   /* LK3DIND: the same */
WORD sv_col1;                       /* INDBUTCOL's colour */
WORD sv_set;                        /* a SV_SET: must be refused */
WORD sv_junk;                       /* a `which` that is not one of the six */
static DTA dta;

extern WORD m11_cop01(void);

/* The object tree: a box with a string and a button in it.  The strings
 * are addressed at run time, as rsrc_obfix would address a resource's,
 * so that ob_spec carries a bank-$00 address whatever the pool gave. */
static char s_hello[] = "Hello, GEM";
static char s_ok[]    = "OK";

static OBJECT tree[3] = {
    /* next head tail  type      flags       state  spec         x    y    w    h */
    { -1,   1,   2,   G_BOX,    NONE,       NORMAL, 0x00FF1101L, 100, 60, 200, 100 },
    {  2,  -1,  -1,   G_STRING, NONE,       NORMAL, 0,           16,  16,  80,   8 },
    { -1,  -1,  -1,   G_BUTTON, SELECTABLE | EXIT | LASTOB,
                                            NORMAL, 0,           60,  60,  80,  16 },
};

static void record_vdi(void)
{
    WORD *r = results[ncalls];
    WORD k;
    if (ncalls >= NREC)
        return;
    r[0] = contrl[2];
    r[1] = contrl[4];
    for (k = 0; k < REC_INTOUT; k++)
        r[2 + k] = (WORD)(contrl[4] > k ? intout[k] : 0);
    r[2 + REC_INTOUT]     = (WORD)(contrl[2] > 0 ? ptsout[0] : 0);
    r[2 + REC_INTOUT + 1] = (WORD)(contrl[2] > 0 ? ptsout[1] : 0);
    r[2 + REC_INTOUT + 2] = (WORD)(contrl[2] > 1 ? ptsout[2] : 0);
    ncalls++;
}

/* An AES record: control[2] says how many of int_out came back. */
static void record_aes(void)
{
    WORD *r = results[ncalls];
    WORD k;
    if (ncalls >= NREC)
        return;
    r[0] = 0;
    r[1] = control[2];
    for (k = 0; k < REC_INTOUT; k++)
        r[2 + k] = (WORD)(control[2] > k && k < 7 ? int_out[k] : 0);
    r[2 + REC_INTOUT] = r[2 + REC_INTOUT + 1] = r[2 + REC_INTOUT + 2] = 0;
    ncalls++;
}

int main(void)
{
    WORD work_in[11], work_out[57];
    WORD handle, wchar, hchar, wbox, hbox;
    WORD wh, x, y, w, h, k;
    WORD pxy[8];

    ncalls = 0;
    tree[1].ob_spec.index = (LONG)(uint32_t)(char FAR *)s_hello;
    tree[2].ob_spec.index = (LONG)(uint32_t)(char FAR *)s_ok;

    appl_init();                                        record_aes();
    handle = graf_handle(&wchar, &hchar, &wbox, &hbox); record_aes();

    for (k = 0; k < 10; k++)
        work_in[k] = 1;
    work_in[10] = 2;
    v_opnvwk(work_in, &handle, work_out);               record_vdi();

    vsf_color(handle, 3);                               record_vdi();
    vsf_interior(handle, 1);                            record_vdi();
    pxy[0] = 20; pxy[1] = 20; pxy[2] = 619; pxy[3] = 219;
    vr_recfl(handle, pxy);                              record_vdi();

    vst_color(handle, 1);                               record_vdi();
    v_gtext(handle, 24, 32, "gem4xe application");      record_vdi();

    vsl_color(handle, 2);                               record_vdi();
    pxy[0] = 30; pxy[1] = 200; pxy[2] = 300; pxy[3] = 180; pxy[4] = 600; pxy[5] = 210;
    v_pline(handle, 3, pxy);                            record_vdi();

    objc_draw(tree, 0, 8, 0, 0, 640, 240);              record_aes();

    wh = wind_create(NAME | CLOSER | MOVER, 0, hbox, 640, (WORD)(240 - hbox));
                                                        record_aes();
    wind_open(wh, 320, 40, 280, 150);                   record_aes();
    wind_get(wh, WF_WORKXYWH, &x, &y, &w, &h);          record_aes();
    evnt_timer(40, 0);                                  record_aes();
    wind_close(wh);                                     record_aes();
    wind_delete(wh);                                    record_aes();
    appl_exit();                                        record_aes();

    {
        LONG r, m;
        WORD n = 0;

        dosres[0] = Sversion();
        dosres[1] = Dgetdrv();
        Fsetdta(&dta);
        r = Fsfirst("A:\\*.*", FA_SUBDIR);
        while (r == E_OK) {
            n++;
            r = Fsnext();
        }
        dosres[2] = n;
        dosres[3] = (WORD)r;                            /* ENMFIL */
        dosres[4] = (WORD)Fopen("A:\\NOPE.XYZ", 0);      /* EFILNF */
        m = Malloc(-1L);
        dosres[5] = (WORD)(m >> 16);                    /* banks left */
        dosres[6] = (WORD)(Fgetdta() == &dta);
        ndos = (WORD)(7 + n);
    }

    /* And one COP that is not gem4xe's at all: Rapidus OS's COP #$01,
     * which gem4xe must pass to the OS when it is running and refuse when
     * it is not (src/sys/abi.s). */
    /* objc_sysvar (opcode 48): what the AES says about 3D objects, which
     * here is that there are none.  AD3DVALUE is the one cflib asks. */
    sv_ad3d = objc_sysvar(SV_INQUIRE, AD3DVALUE, 0, 0, &sv_ad3d1, &sv_ad3d2);
    sv_lk3d = objc_sysvar(SV_INQUIRE, LK3DIND, 0, 0, &sv_lk3d1, &sv_lk3d2);
    objc_sysvar(SV_INQUIRE, INDBUTCOL, 0, 0, &sv_col1, &k);
    sv_set  = objc_sysvar(SV_SET, INDBUTCOL, 1, 0, &k, &k);
    sv_junk = objc_sysvar(SV_INQUIRE, 99, 0, 0, &k, &k);

    foreign = m11_cop01();
    return ncalls;
}
