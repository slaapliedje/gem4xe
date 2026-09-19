/* bind_sim.c -- every binding in src/app/gemlib.c, called once, with the
 * three call gates replaced by recorders.
 *
 * The library's job is to fill a parameter block: the opcode, the
 * sub-function, and the counts that say how many words travel in and
 * out.  gem4xe reads those counts to know how much to copy (src/sys/
 * abi.c), so a binding that miscounts is a binding that loses an
 * argument -- and neither the compiler nor a link check would say so.
 *
 * So: compile this with gemlib.c for the compiler's own simulator,
 * call every binding, and record what each one built.  tests/host/
 * test_bind.py compares the record with the VDI and AES contracts,
 * written out there from the specification rather than from this code.
 *
 * Then a second pass for the other half of a binding's job: an inquiry
 * has to read its answer out of the RIGHT word.  The gates fill intout
 * and ptsout with a pattern -- intout[i] is 100+i, ptsout[i] is 200+i
 * -- and the pass records what each inquiry handed back, so a binding
 * that reads ptsout[2] where the VDI puts the answer in ptsout[4]
 * says so.  That is the shape of the defect this phase found in the
 * driver itself (docs/phase20.md).
 */
#include "gem.h"

#define NREC   260
#define RECW   6                /* kind, then five words of the block */

WORD bind_n;
WORD bind_rec[NREC * RECW];
static WORD rec_blocks = 1;     /* the first pass records the blocks */
static WORD fill_out;           /* the second fills the answers */

static void put(WORD kind, WORD a, WORD b, WORD c, WORD d, WORD e)
{
    WORD i = (WORD)(bind_n * RECW);

    if (bind_n >= NREC)
        return;
    bind_rec[i] = kind;
    bind_rec[i + 1] = a;
    bind_rec[i + 2] = b;
    bind_rec[i + 3] = c;
    bind_rec[i + 4] = d;
    bind_rec[i + 5] = e;
    bind_n++;
}

/* The answers the second pass hands back: a word's own index, so where
 * a binding read it from is visible in what it returned. */
static void pattern(void)
{
    WORD i;

    for (i = 0; i < 45; i++)
        intout[i] = (WORD)(100 + i);
    for (i = 0; i < 12; i++)
        ptsout[i] = (WORD)(200 + i);
    for (i = 0; i < 7; i++)
        int_out[i] = (WORD)(300 + i);
}

/* The gates: opcode and counts out of the arrays the library filled. */
SIMPLE_CALL void vdi_call(VDIPB FAR *pb)
{
    (void)pb;
    if (rec_blocks)
        put(0, contrl[0], contrl[5], contrl[1], contrl[3], contrl[6]);
    if (fill_out)
        pattern();
}

SIMPLE_CALL void aes_call(AESPB FAR *pb)
{
    (void)pb;
    if (rec_blocks)
        put(1, control[0], control[1], control[2], control[3], control[4]);
    if (fill_out)
        pattern();
}

SIMPLE_CALL void dos_call(GDPB FAR *pb)
{
    if (rec_blocks)
        put(2, pb->fn, 0, 0, 0, 0);
}

#define H 7                     /* the workstation handle, to see it travel */

static WORD w4[4]  = { 1, 2, 3, 4 };
static WORD w8[8]  = { 1, 2, 3, 4, 5, 6, 7, 8 };
static WORD w16[16];
static WORD w37[37];
static WORD out[64];
static char name[40];
static char path[80];
static OBJECT tree[2];
static MFDB form;
static DTA dta;
static DISKINFO disk;

int main(void)
{
    WORD a, b, c, d;
    LONG old;
    char *env;
    GRECT r1, r2;

    /* -- VDI, in opcode order ------------------------------------------ */
    v_opnwk(w16, &a, out);
    v_clswk(H);
    v_clrwk(H);
    v_updwk(H);
    v_exit_cur(H);
    v_enter_cur(H);
    v_pline(H, 2, w4);
    v_pmarker(H, 2, w4);
    v_gtext(H, 1, 2, "abc");
    v_fillarea(H, 3, w8);
    v_bar(H, w4);
    v_arc(H, 1, 2, 3, 0, 900);
    v_pieslice(H, 1, 2, 3, 0, 900);
    v_circle(H, 1, 2, 3);
    v_ellipse(H, 1, 2, 3, 4);
    v_ellarc(H, 1, 2, 3, 4, 0, 900);
    v_ellpie(H, 1, 2, 3, 4, 0, 900);
    v_rbox(H, w4);
    v_rfbox(H, w4);
    v_justified(H, 1, 2, "abcd", 100, 1, 1);
    vst_height(H, 8, &a, &b, &c, &d);
    vst_rotation(H, 0);
    vs_color(H, 1, w4);
    vsl_type(H, 1);
    vsl_width(H, 1);
    vsl_color(H, 1);
    vsm_type(H, 1);
    vsm_height(H, 8);
    vsm_color(H, 1);
    vst_font(H, 1);
    vst_color(H, 1);
    vsf_interior(H, 1);
    vsf_style(H, 1);
    vsf_color(H, 1);
    vq_color(H, 1, 0, out);
    v_locator(H, 1, 2, &a, &b, &c);
    vsm_choice(H, &a);
    v_string(H, &a);
    vswr_mode(H, 1);
    vsin_mode(H, 1, 2);
    vql_attributes(H, out);
    vqm_attributes(H, out);
    vqf_attributes(H, out);
    vqt_attributes(H, out);
    vst_alignment(H, 0, 0, &a, &b);
    v_opnvwk(w16, &a, out);
    v_clsvwk(H);
    vq_extnd(H, 1, out);
    v_contourfill(H, 1, 2, 3);
    vsf_perimeter(H, 1);
    v_get_pixel(H, 1, 2, &a, &b);
    vst_effects(H, 1);
    vst_point(H, 9, &a, &b, &c, &d);
    vsl_ends(H, 0, 1);
    vro_cpyfm(H, 3, w8, &form, &form);
    vr_trnfm(H, &form, &form);
    vsc_form(H, w37);
    vsf_udpat(H, w16, 1);
    vsl_udsty(H, 0x5555);
    vr_recfl(H, w4);
    vqin_mode(H, 1, &a);
    vqt_extent(H, "abc", out);
    vqt_width(H, 'A', &a, &b, &c);
    vex_timv(H, 0x012345L, &old);
    vst_load_fonts(H, 0);
    vst_unload_fonts(H, 0);
    vrt_cpyfm(H, 1, w8, &form, &form, w4);
    v_show_c(H, 1);
    v_hide_c(H);
    vq_mouse(H, &a, &b, &c);
    vex_butv(H, 0x012345L, &old);
    vex_motv(H, 0x012345L, &old);
    vex_curv(H, 0x012345L, &old);
    vq_key_s(H, &a);
    vs_clip(H, 1, w4);
    vqt_name(H, 1, name);
    vqt_fontinfo(H, &a, &b, w4, &c, w16);
    /* vq_gdos builds no parameter block at all -- on the ST it is not a VDI
       opcode but a magic trap, and here it is a constant. Called so the
       "every declared binding is exercised" test can see it; it records
       nothing, so it needs no EXPECT row. Called BARE, with the result
       dropped, because called_names() matches a name at four spaces of
       indent and a (void) cast in front of it hides the call from the very
       check this line exists to satisfy. */
    vq_gdos();

    /* -- AES, in opcode order ------------------------------------------ */
    appl_init();
    appl_write(0, 16, w8);
    appl_find("SCRENSAV");              /* eight, as the contract says */
    appl_getinfo(AES_LARGEFONT, &a, &b, &c, &d);
    appl_xgetinfo(AES_LARGEFONT, &a, &b, &c, &d);
    appl_yield();
    appl_exit();
    evnt_keybd();
    evnt_button(1, 1, 1, &a, &b, &c, &d);
    evnt_mouse(0, 1, 2, 3, 4, &a, &b, &c, &d);
    evnt_mesag(out);
    evnt_timer(100, 0);
    evnt_multi(0x0011, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, out, 100, 0,
               &a, &b, &c, &d, &a, &b);
    evnt_multi_moblk(0x0011, 1, 1, 1, 0, 0, out, 100, 0,
               &a, &b, &c, &d, &a, &b);
    evnt_dclick(3, 0);
    menu_bar(tree, 1);
    menu_icheck(tree, 1, 1);
    menu_ienable(tree, 1, 1);
    menu_tnormal(tree, 1, 1);
    menu_text(tree, 1, "x");
    menu_register(0, "x");
    objc_add(tree, 0, 1);
    objc_delete(tree, 1);
    objc_draw(tree, 0, 8, 1, 2, 3, 4);
    r1.g_x = 1; r1.g_y = 2; r1.g_w = 3; r1.g_h = 4;
    objc_draw_grect(tree, 0, 8, &r1);
    objc_find(tree, 0, 8, 1, 2);
    objc_offset(tree, 1, &a, &b);
    objc_order(tree, 1, 0);
    a = 0;
    objc_edit(tree, 1, 'x', &a, 1);
    objc_change(tree, 1, 0, 1, 2, 3, 4, 1, 1);
    objc_sysvar(SV_INQUIRE, AD3DVALUE, 0, 0, &a, &b);
    form_do(tree, 0);
    form_dial(0, 1, 2, 3, 4, 5, 6, 7, 8);
    r2.g_x = 5; r2.g_y = 6; r2.g_w = 7; r2.g_h = 8;
    form_dial_grect(0, &r1, &r2);
    form_alert(1, "[1][x][ OK ]");
    form_error(2);
    form_center(tree, &a, &b, &c, &d);
    form_center_grect(tree, &r1);
    form_keybd(tree, 1, 0, 13, &a, &b);
    form_button(tree, 1, 1, &a);
    graf_rubbox(1, 2, 3, 4, &a, &b);
    graf_dragbox(1, 2, 3, 4, 5, 6, 7, 8, &a, &b);
    graf_growbox(1, 2, 3, 4, 5, 6, 7, 8);
    graf_shrinkbox(1, 2, 3, 4, 5, 6, 7, 8);
    graf_watchbox(tree, 1, 1, 0);
    graf_handle(&a, &b, &c, &d);
    graf_mouse(0, 0);
    graf_mkstate(&a, &b, &c, &d);
    scrp_read(path);
    scrp_write("X:\\");
    fsel_input(path, name, &a);
    fsel_exinput(path, name, &a, "x");
    r1.g_x = 1; r1.g_y = 2; r1.g_w = 3; r1.g_h = 4;
    wind_create(0, 1, 2, 3, 4);
    wind_create_grect(0, &r1);
    wind_open(1, 1, 2, 3, 4);
    wind_open_grect(1, &r1);
    wind_close(1);
    wind_delete(1);
    wind_get(1, 4, &a, &b, &c, &d);
    wind_get_grect(1, 4, &r1);
    wind_set(1, 2, 1, 2, 3, 4);
    r1.g_x = 1; r1.g_y = 2; r1.g_w = 3; r1.g_h = 4;
    wind_set_grect(1, 2, &r1);
    wind_set_str(1, WF_NAME, "x");
    wind_find(1, 2);
    wind_update(1);
    wind_calc(0, 0, 1, 2, 3, 4, &a, &b, &c, &d);
    wind_calc_grect(0, 0, &r1, &r2);
    rsrc_load("X.RSC");
    rsrc_free();
    rsrc_gaddr(0, 1, (void **)&env);
    rsrc_saddr(0, 1, path);
    rsrc_obfix(tree, 1);
    shel_read(path, name);
    shel_write(1, 1, 1, "X", "");
    shel_get(path, 8);
    shel_put(path, 8);
    shel_find(path);
    shel_envrn(&env, "PATH=");
    /* rc_intersect and rc_union reach no gate -- they are arithmetic on
     * two rectangles.  Called here so the surface check sees them; what
     * they COMPUTE is asserted in the second pass below. */
    r1.g_x = 0; r1.g_y = 0; r1.g_w = 10; r1.g_h = 10;
    r2.g_x = 5; r2.g_y = 5; r2.g_w = 10; r2.g_h = 10;
    rc_intersect(&r1, &r2);
    rc_union(&r1, &r2);

    /* -- GEMDOS, in function order ------------------------------------- */
    Pterm0();                   /* the recorder returns, so the ends do too */
    Cconin();
    Cconout('A');
    Cauxin();
    Cauxout('A');
    Cprnout('A');
    Crawio(0xFF);
    Crawcin();
    Cnecin();
    Cconws(path);
    Cconrs(path);
    Cconis();
    Dsetdrv(0);
    Cconos();
    Cprnos();
    Cauxis();
    Cauxos();
    Dgetdrv();
    Fsetdta(&dta);
    Super(path);
    Tgetdate();
    Tsetdate(0x0021);
    Tgettime();
    struct timeval tv;                  /* declared here: the test reads
                                         * a call by its four-space indent */
    Tgettimeofday(&tv, 0);
    Psystem(path, 0, 0L);
    Tsettime(0);
    Fgetdta();
    Sversion();
    Ptermres(0L, 0);
    Dfree(&disk, 0);
    Dcreate(path);
    Ddelete(path);
    Dsetpath(path);
    Fcreate(path, 0);
    Fopen(path, 0);
    Fclose(6);
    Fread(6, 16L, path);
    Fwrite(6, 16L, path);
    Fdelete(path);
    Fseek(0L, 6, 0);
    Fattrib(path, 1, 1);
    Mxalloc(16L, 0);
    Fdup(1);
    Fforce(1, 6);
    Dgetpath(path, 0);
    Malloc(16L);
    Mfree(path);
    Mshrink(path, 8L);
    Pexec(0, path, name, 0);
    Pterm(0);
    Fsfirst(path, 0);
    Fsnext();
    Frename(path, name);
    Fdatime(w4, 6, 0);

    /* -- the answers, and the words they were read from ---------------- */
    rec_blocks = 0;
    fill_out = 1;
    vst_height(H, 8, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    put(3, vsl_width(H, 1), 0, 0, 0, 0);
    put(3, vsm_height(H, 8), 0, 0, 0, 0);
    vq_color(H, 1, 0, out);
    put(3, out[0], out[1], out[2], 0, 0);
    v_locator(H, 1, 2, &a, &b, &c);
    put(3, a, b, c, 0, 0);
    vql_attributes(H, out);
    put(3, out[0], out[1], out[2], out[3], 0);
    vqm_attributes(H, out);
    put(3, out[0], out[1], out[2], out[3], 0);
    vqf_attributes(H, out);
    put(3, out[0], out[1], out[2], out[4], 0);
    vqt_attributes(H, out);
    put(3, out[0], out[5], out[6], out[9], 0);
    vst_alignment(H, 0, 0, &a, &b);
    put(3, a, b, 0, 0, 0);
    v_get_pixel(H, 1, 2, &a, &b);
    put(3, a, b, 0, 0, 0);
    put(3, vst_point(H, 9, &a, &b, &c, &d), a, b, c, d);
    vqt_extent(H, "abc", out);
    put(3, out[0], out[3], out[5], out[7], 0);
    put(3, vqt_width(H, 'A', &a, &b, &c), a, b, c, 0);
    vqin_mode(H, 1, &a);
    put(3, a, 0, 0, 0, 0);
    vq_mouse(H, &a, &b, &c);
    put(3, a, b, c, 0, 0);
    vq_key_s(H, &a);
    put(3, a, 0, 0, 0, 0);
    put(3, vqt_name(H, 1, name), (WORD)(unsigned char)name[0],
        (WORD)(unsigned char)name[1], 0, 0);
    evnt_button(1, 1, 1, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    evnt_mouse(0, 1, 2, 3, 4, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    appl_getinfo(AES_LARGEFONT, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    appl_xgetinfo(AES_LARGEFONT, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    objc_offset(tree, 1, &a, &b);
    put(3, a, b, 0, 0, 0);
    form_center(tree, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    graf_handle(&a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    graf_mkstate(&a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    wind_get(1, 4, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    wind_calc(0, 0, 1, 2, 3, 4, &a, &b, &c, &d);
    put(3, a, b, c, d, 0);
    /* The GRECT spellings: the same four words, and the point is that they
     * land in x, y, w, h IN THAT ORDER.  A wrapper that swapped w and h
     * would pass every block check above and be wrong on screen. */
    form_center_grect(tree, &r1);
    put(3, r1.g_x, r1.g_y, r1.g_w, r1.g_h, 0);
    wind_get_grect(1, 4, &r1);
    put(3, r1.g_x, r1.g_y, r1.g_w, r1.g_h, 0);
    wind_calc_grect(0, 0, &r1, &r2);
    put(3, r2.g_x, r2.g_y, r2.g_w, r2.g_h, 0);
    /* rc_intersect: (0,0,10,10) against (5,5,10,10) overlaps in the square
     * from 5,5 to 10,10 -- and the answer is written into the SECOND
     * rectangle, which is the ST's order.  rc_union of the same two spans
     * 0,0 to 15,15. */
    r1.g_x = 0; r1.g_y = 0; r1.g_w = 10; r1.g_h = 10;
    r2.g_x = 5; r2.g_y = 5; r2.g_w = 10; r2.g_h = 10;
    a = rc_intersect(&r1, &r2);
    put(3, a, r2.g_x, r2.g_y, r2.g_w, r2.g_h);
    r2.g_x = 5; r2.g_y = 5; r2.g_w = 10; r2.g_h = 10;
    rc_union(&r1, &r2);
    put(3, r2.g_x, r2.g_y, r2.g_w, r2.g_h, 0);
    return 0;
}
