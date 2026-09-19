/* gemlib.c -- an application's GEM bindings, over the three COP entries.
 *
 * The shape is the classic GEM library's: one set of arrays, a parameter
 * block pointing at them, a binding per call that fills the arrays, makes
 * the call and unpacks the results.  The control words an AES binding
 * fills -- opcode and the four counts -- are the ST's: gem4xe reads the
 * counts to know how much to copy in and out, exactly as the AES does.
 *
 * The arrays are sized for what THIS library's bindings need, not for the
 * VDI's maxima: v_opnvwk's 45 intout and 12 ptsout words set the two
 * output sizes, nothing here passes more than 16 points, and intin is
 * the VDI's own 128 words (src/vdi/vdi.h) because v_gtext takes a line
 * of text that long -- the desktop's window titles and info lines are
 * up to 80 characters.  An application that adds a binding with larger
 * needs grows them.
 */
#include "portab.h"
#include "gem.h"

WORD contrl[12], intin[128], ptsin[16], intout[45], ptsout[12];
WORD control[5], global[15], int_in[16], int_out[7];
LONG addr_in[3], addr_out[1];

static VDIPB vpb = { contrl, intin, ptsin, intout, ptsout };
static AESPB apb = { control, global, int_in, int_out, addr_in, addr_out };

/* contrl[5] is the sub-function: the GDP for opcode 11, the escape for
 * opcode 5, and zero for everything else. */
static void vdi_sub(WORD op, WORD sub, WORD npts, WORD nint, WORD handle)
{
    contrl[0] = op;
    contrl[1] = npts;
    contrl[3] = nint;
    contrl[5] = sub;
    contrl[6] = handle;
    vdi_call(&vpb);
}

static void vdi(WORD op, WORD npts, WORD nint, WORD handle)
{
    vdi_sub(op, 0, npts, nint, handle);
}

static WORD aes(WORD op, WORD nin, WORD nout, WORD nain, WORD naout)
{
    control[0] = op;
    control[1] = nin;
    control[2] = nout;
    control[3] = nain;
    control[4] = naout;
    aes_call(&apb);
    return int_out[0];
}

/* -- VDI ------------------------------------------------------------- */

void v_opnvwk(WORD *work_in, WORD *handle, WORD *work_out)
{
    WORD i;
    for (i = 0; i < 11; i++)
        intin[i] = work_in[i];
    vdi(100, 0, 11, *handle);
    *handle = contrl[6];
    for (i = 0; i < 45; i++)
        work_out[i] = intout[i];
    for (i = 0; i < 12; i++)
        work_out[45 + i] = ptsout[i];
}

void v_clsvwk(WORD handle)
{
    vdi(101, 0, 0, handle);
}

void vr_recfl(WORD handle, WORD *pxy)
{
    WORD i;
    for (i = 0; i < 4; i++)
        ptsin[i] = pxy[i];
    vdi(114, 2, 0, handle);
}

void v_pline(WORD handle, WORD count, WORD *pxy)
{
    WORD i;
    for (i = 0; i < count * 2; i++)
        ptsin[i] = pxy[i];
    vdi(6, count, 0, handle);
}

void v_gtext(WORD handle, WORD x, WORD y, const char *s)
{
    WORD n = 0;
    ptsin[0] = x;
    ptsin[1] = y;
    while (*s && n < 128)
        intin[n++] = (WORD)(unsigned char)*s++;
    vdi(8, 1, n, handle);
}

static WORD attr1(WORD op, WORD handle, WORD v)
{
    intin[0] = v;
    vdi(op, 0, 1, handle);
    return intout[0];
}

WORD vsf_color(WORD handle, WORD color)    { return attr1(25, handle, color); }

/* No GDOS here, and that is a property of the design rather than a gap:
 * the VDI's device independence is in v_opnwk's device id, so a printer
 * is a second driver rasterising the same opcodes, not a loadable one.
 * See gem.h -- this is not a VDI opcode on the ST either. */
WORD vq_gdos(void) { return 0; }
WORD vsf_interior(WORD handle, WORD style) { return attr1(23, handle, style); }
WORD vsl_color(WORD handle, WORD color)    { return attr1(17, handle, color); }
WORD vst_color(WORD handle, WORD color)    { return attr1(22, handle, color); }

/* -- VDI: the rest of the surface --------------------------------------
 *
 * Every opcode src/vdi/vdi.c serves has a binding here, in the names and
 * the argument order the VDI has had since 1984, so that GEM source
 * written for an ST compiles against this header.  What is deliberately
 * absent: opcodes 10 and 27 (cell array), 29 (valuator) and 34, which
 * the driver answers with v_nop -- a binding that silently does nothing
 * is worse than a name that is not there.  v_clswk and v_updwk ARE here,
 * because every GEM program calls them and a screen driver has nothing
 * to do for either, which is what DRI's own driver does with them too.
 */

static void pts(const WORD *p, WORD n)
{
    WORD i;
    for (i = 0; i < n; i++)
        ptsin[i] = p[i];
}

static void ptsx(WORD *p, WORD n)
{
    WORD i;
    for (i = 0; i < n; i++)
        p[i] = ptsout[i];
}

static void intx(WORD *p, WORD n)
{
    WORD i;
    for (i = 0; i < n; i++)
        p[i] = intout[i];
}

/* A string into intin, as v_gtext and v_justified pass one. */
static WORD str_in(const char *s, WORD at)
{
    WORD n = at;
    while (*s && n < 128)
        intin[n++] = (WORD)(unsigned char)*s++;
    return n;
}

/* An MFDB travels as an address in contrl, and lives in bank $00: the
 * driver reads it with a near pointer (src/vdi/vdi.c, rform_of). */
static void form_in(WORD at, const MFDB *f)
{
    contrl[at] = (WORD)(uint16_t)f;
    contrl[at + 1] = 0;
}

void v_opnwk(WORD *work_in, WORD *handle, WORD *work_out)
{
    WORD i;
    for (i = 0; i < 11; i++)
        intin[i] = work_in[i];
    vdi(1, 0, 11, 0);
    *handle = contrl[6];
    for (i = 0; i < 45; i++)
        work_out[i] = intout[i];
    for (i = 0; i < 12; i++)
        work_out[45 + i] = ptsout[i];
}

void v_clswk(WORD handle)       { vdi(2, 0, 0, handle); }
void v_clrwk(WORD handle)       { vdi(3, 0, 0, handle); }
void v_updwk(WORD handle)       { vdi(4, 0, 0, handle); }
void v_enter_cur(WORD handle)   { vdi_sub(5, 3, 0, 0, handle); }
void v_exit_cur(WORD handle)    { vdi_sub(5, 2, 0, 0, handle); }

void v_pmarker(WORD handle, WORD count, const WORD *pxy)
{
    pts(pxy, (WORD)(count * 2));
    vdi(7, count, 0, handle);
}

void v_fillarea(WORD handle, WORD count, const WORD *pxy)
{
    pts(pxy, (WORD)(count * 2));
    vdi(9, count, 0, handle);
}

/* The GDPs, opcode 11 with the sub-function in contrl[5]. */
void v_bar(WORD handle, const WORD *pxy)
{
    pts(pxy, 4);
    vdi_sub(11, 1, 2, 0, handle);
}

static void arc_in(WORD x, WORD y, WORD radius, WORD begang, WORD endang)
{
    WORD i;
    ptsin[0] = x;
    ptsin[1] = y;
    for (i = 2; i < 6; i++)
        ptsin[i] = 0;
    ptsin[6] = radius;
    ptsin[7] = 0;
    intin[0] = begang;
    intin[1] = endang;
}

void v_arc(WORD handle, WORD x, WORD y, WORD radius, WORD begang, WORD endang)
{
    arc_in(x, y, radius, begang, endang);
    vdi_sub(11, 2, 4, 2, handle);
}

void v_pieslice(WORD handle, WORD x, WORD y, WORD radius, WORD begang,
                WORD endang)
{
    arc_in(x, y, radius, begang, endang);
    vdi_sub(11, 3, 4, 2, handle);
}

void v_circle(WORD handle, WORD x, WORD y, WORD radius)
{
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = ptsin[3] = ptsin[5] = 0;
    ptsin[4] = radius;
    vdi_sub(11, 4, 3, 0, handle);
}

void v_ellipse(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad)
{
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = xrad;
    ptsin[3] = yrad;
    vdi_sub(11, 5, 2, 0, handle);
}

void v_ellarc(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad,
              WORD begang, WORD endang)
{
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = xrad;
    ptsin[3] = yrad;
    intin[0] = begang;
    intin[1] = endang;
    vdi_sub(11, 6, 2, 2, handle);
}

void v_ellpie(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad,
              WORD begang, WORD endang)
{
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = xrad;
    ptsin[3] = yrad;
    intin[0] = begang;
    intin[1] = endang;
    vdi_sub(11, 7, 2, 2, handle);
}

void v_rbox(WORD handle, const WORD *pxy)
{
    pts(pxy, 4);
    vdi_sub(11, 8, 2, 0, handle);
}

void v_rfbox(WORD handle, const WORD *pxy)
{
    pts(pxy, 4);
    vdi_sub(11, 9, 2, 0, handle);
}

void v_justified(WORD handle, WORD x, WORD y, const char *s, WORD length,
                 WORD word_space, WORD char_space)
{
    WORD n;
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = length;
    ptsin[3] = 0;
    intin[0] = word_space;
    intin[1] = char_space;
    n = str_in(s, 2);
    vdi_sub(11, 10, 2, n, handle);
}

void vst_height(WORD handle, WORD height, WORD *char_width, WORD *char_height,
                WORD *cell_width, WORD *cell_height)
{
    ptsin[0] = 0;
    ptsin[1] = height;
    vdi(12, 1, 0, handle);
    *char_width = ptsout[0];
    *char_height = ptsout[1];
    *cell_width = ptsout[2];
    *cell_height = ptsout[3];
}

WORD vst_rotation(WORD handle, WORD angle) { return attr1(13, handle, angle); }

void vs_color(WORD handle, WORD index, const WORD *rgb)
{
    intin[0] = index;
    intin[1] = rgb[0];
    intin[2] = rgb[1];
    intin[3] = rgb[2];
    vdi(14, 0, 4, handle);
}

WORD vsl_type(WORD handle, WORD style) { return attr1(15, handle, style); }

WORD vsl_width(WORD handle, WORD width)
{
    ptsin[0] = width;
    ptsin[1] = 0;
    vdi(16, 1, 0, handle);
    return ptsout[0];
}

WORD vsm_type(WORD handle, WORD symbol) { return attr1(18, handle, symbol); }

WORD vsm_height(WORD handle, WORD height)
{
    ptsin[0] = 0;
    ptsin[1] = height;
    vdi(19, 1, 0, handle);
    return ptsout[1];
}

WORD vsm_color(WORD handle, WORD color) { return attr1(20, handle, color); }
WORD vst_font(WORD handle, WORD font)   { return attr1(21, handle, font); }
WORD vsf_style(WORD handle, WORD style) { return attr1(24, handle, style); }

void vq_color(WORD handle, WORD index, WORD flag, WORD *rgb)
{
    intin[0] = index;
    intin[1] = flag;
    vdi(26, 0, 2, handle);
    rgb[0] = intout[1];
    rgb[1] = intout[2];
    rgb[2] = intout[3];
}

/* The locator, sampled: the position comes back whether or not one was
 * given, and the terminator is 0 when nothing ended the sample. */
WORD v_locator(WORD handle, WORD x, WORD y, WORD *xout, WORD *yout,
               WORD *term)
{
    ptsin[0] = x;
    ptsin[1] = y;
    vdi(28, 1, 0, handle);
    *xout = ptsout[0];
    *yout = ptsout[1];
    *term = intout[0];
    return contrl[4];
}

/* The choice device sampled.  This machine has none -- there are no
 * function keys on a GEM keyboard here -- so the answer is always 0,
 * which is what "nothing was chosen" means. */
WORD vsm_choice(WORD handle, WORD *choice)
{
    vdi(30, 0, 0, handle);              /* sampled: nothing goes in */
    *choice = intout[0];
    return contrl[4];
}

/* One key, as a GEM key code -- scan code over ASCII -- or nothing:
 * gem4xe's string device answers a key at a time (src/vdi/vdi.c). */
WORD v_string(WORD handle, WORD *key)
{
    vdi(31, 0, 0, handle);
    if (contrl[4] < 1)
        return 0;
    *key = intout[0];
    return 1;
}

WORD vswr_mode(WORD handle, WORD mode) { return attr1(32, handle, mode); }

WORD vsin_mode(WORD handle, WORD dev, WORD mode)
{
    intin[0] = dev;
    intin[1] = mode;
    vdi(33, 0, 2, handle);
    return intout[0];
}

void vql_attributes(WORD handle, WORD *attr)
{
    vdi(35, 0, 0, handle);
    intx(attr, 3);
    attr[3] = ptsout[0];
}

void vqm_attributes(WORD handle, WORD *attr)
{
    vdi(36, 0, 0, handle);
    intx(attr, 3);
    attr[3] = ptsout[1];
}

void vqf_attributes(WORD handle, WORD *attr)
{
    vdi(37, 0, 0, handle);
    intx(attr, 5);                      /* style, colour, index, mode,
                                         * perimeter */
}

void vqt_attributes(WORD handle, WORD *attr)
{
    vdi(38, 0, 0, handle);
    intx(attr, 6);
    ptsx(attr + 6, 4);
}

void vst_alignment(WORD handle, WORD hin, WORD vin, WORD *hout, WORD *vout)
{
    intin[0] = hin;
    intin[1] = vin;
    vdi(39, 0, 2, handle);
    *hout = intout[0];
    *vout = intout[1];
}

void vq_extnd(WORD handle, WORD owflag, WORD *work_out)
{
    WORD i;
    intin[0] = owflag;
    vdi(102, 0, 1, handle);
    for (i = 0; i < 45; i++)
        work_out[i] = intout[i];
    for (i = 0; i < 12; i++)
        work_out[45 + i] = ptsout[i];
}

void v_contourfill(WORD handle, WORD x, WORD y, WORD index)
{
    ptsin[0] = x;
    ptsin[1] = y;
    intin[0] = index;
    vdi(103, 1, 1, handle);
}

WORD vsf_perimeter(WORD handle, WORD vis) { return attr1(104, handle, vis); }

void v_get_pixel(WORD handle, WORD x, WORD y, WORD *pel, WORD *index)
{
    ptsin[0] = x;
    ptsin[1] = y;
    vdi(105, 1, 0, handle);
    *pel = intout[0];
    *index = intout[1];
}

WORD vst_effects(WORD handle, WORD effects) { return attr1(106, handle, effects); }

WORD vst_point(WORD handle, WORD point, WORD *char_width, WORD *char_height,
               WORD *cell_width, WORD *cell_height)
{
    intin[0] = point;
    vdi(107, 0, 1, handle);
    *char_width = ptsout[0];
    *char_height = ptsout[1];
    *cell_width = ptsout[2];
    *cell_height = ptsout[3];
    return intout[0];
}

void vsl_ends(WORD handle, WORD beg_style, WORD end_style)
{
    intin[0] = beg_style;
    intin[1] = end_style;
    vdi(108, 0, 2, handle);
}

void vro_cpyfm(WORD handle, WORD mode, const WORD *pxy, const MFDB *src,
               const MFDB *dst)
{
    pts(pxy, 8);
    intin[0] = mode;
    form_in(7, src);
    form_in(9, dst);
    vdi(109, 4, 1, handle);
}

void vr_trnfm(WORD handle, const MFDB *src, const MFDB *dst)
{
    form_in(7, src);
    form_in(9, dst);
    vdi(110, 0, 0, handle);
}

void vsc_form(WORD handle, const WORD *form)
{
    WORD i;
    for (i = 0; i < 37; i++)
        intin[i] = form[i];
    vdi(111, 0, 37, handle);
}

void vsf_udpat(WORD handle, const WORD *pattern, WORD planes)
{
    WORD i;
    for (i = 0; i < 16; i++)
        intin[i] = pattern[i];
    (void)planes;                       /* one plane's worth here */
    vdi(112, 0, 16, handle);
}

void vsl_udsty(WORD handle, WORD pattern)
{
    intin[0] = pattern;
    vdi(113, 0, 1, handle);
}

void vqin_mode(WORD handle, WORD dev, WORD *mode)
{
    intin[0] = dev;
    vdi(115, 0, 1, handle);
    *mode = intout[0];
}

void vqt_extent(WORD handle, const char *s, WORD *extent)
{
    WORD n = str_in(s, 0);
    vdi(116, 0, n, handle);
    ptsx(extent, 8);
}

/* vqt_fontinfo (131) -- the current font's vertical distances.
 *
 * The unpacking is the Compendium's own binding (7.111) and it is not a
 * straight copy: the distances are the ODD ptsout entries and the effects
 * offsets are the even ones between them, so dist[i] comes from
 * ptsout[2i+1]. FOUR distances are transferred, not the five the prose
 * describes -- dist[4], the top line, is never written by the binding, so
 * a caller wanting it has none. */
void vqt_fontinfo(WORD handle, WORD *first, WORD *last, WORD *dist,
                  WORD *width, WORD *effects)
{
    vdi(131, 0, 0, handle);
    *first   = intout[0];
    *last    = intout[1];
    *width   = ptsout[0];
    dist[0]  = ptsout[1];
    dist[1]  = ptsout[3];
    dist[2]  = ptsout[5];
    dist[3]  = ptsout[7];
    effects[0] = ptsout[2];
    effects[1] = ptsout[4];
    effects[2] = ptsout[6];
}

/* Three points, and the deltas are a point apart -- [0] the cell, [2]
 * the left delta, [4] the right one. */
WORD vqt_width(WORD handle, WORD ch, WORD *cell_width, WORD *left_delta,
               WORD *right_delta)
{
    intin[0] = ch;
    vdi(117, 0, 1, handle);
    *cell_width = ptsout[0];
    *left_delta = ptsout[2];
    *right_delta = ptsout[4];
    return intout[0];
}

/* The vector exchanges.  A handler is 24 bits under the large code model,
 * so the address travels as the LONG at contrl[7] and the one that was
 * there comes back at contrl[9] (src/vdi/vdi.c, vex). */
static LONG vex(WORD op, LONG newv, WORD handle)
{
    contrl[7] = (WORD)newv;
    contrl[8] = (WORD)(newv >> 16);
    contrl[9] = contrl[10] = 0;
    vdi(op, 0, 0, handle);
    return (LONG)((uint32_t)(UWORD)contrl[9]
                  | ((uint32_t)(UWORD)contrl[10] << 16));
}

WORD vex_timv(WORD handle, LONG newv, LONG *oldv)
{
    *oldv = vex(118, newv, handle);
    return intout[0];                   /* the tick, in milliseconds */
}

void vex_butv(WORD handle, LONG newv, LONG *oldv) { *oldv = vex(125, newv, handle); }
void vex_motv(WORD handle, LONG newv, LONG *oldv) { *oldv = vex(126, newv, handle); }
void vex_curv(WORD handle, LONG newv, LONG *oldv) { *oldv = vex(127, newv, handle); }

WORD vst_load_fonts(WORD handle, WORD select)
{
    return attr1(119, handle, select);
}

void vst_unload_fonts(WORD handle, WORD select)
{
    intin[0] = select;
    vdi(120, 0, 1, handle);
}

void vrt_cpyfm(WORD handle, WORD mode, const WORD *pxy, const MFDB *src,
               const MFDB *dst, const WORD *color)
{
    pts(pxy, 8);
    intin[0] = mode;
    intin[1] = color[0];
    intin[2] = color[1];
    form_in(7, src);
    form_in(9, dst);
    vdi(121, 4, 3, handle);
}

void v_show_c(WORD handle, WORD reset)
{
    intin[0] = reset;
    vdi(122, 0, 1, handle);
}

void v_hide_c(WORD handle) { vdi(123, 0, 0, handle); }

void vq_mouse(WORD handle, WORD *pstatus, WORD *x, WORD *y)
{
    vdi(124, 0, 0, handle);
    *pstatus = intout[0];
    *x = ptsout[0];
    *y = ptsout[1];
}

void vq_key_s(WORD handle, WORD *state)
{
    vdi(128, 0, 0, handle);
    *state = intout[0];
}

void vs_clip(WORD handle, WORD clip_flag, const WORD *pxy)
{
    pts(pxy, 4);
    intin[0] = clip_flag;
    vdi(129, 2, 1, handle);
}

WORD vqt_name(WORD handle, WORD element, char *name)
{
    WORD i;
    intin[0] = element;
    vdi(130, 0, 1, handle);
    for (i = 0; i < 32; i++)
        name[i] = (char)intout[i + 1];
    name[32] = 0;
    return intout[0];
}

/* -- AES ------------------------------------------------------------- */

WORD appl_init(void)
{
    return aes(10, 0, 1, 0, 0);
}

WORD appl_exit(void)
{
    return aes(19, 0, 1, 0, 0);
}

WORD appl_yield(void)
{
    return aes(17, 0, 1, 0, 0);
}

WORD graf_handle(WORD *wchar, WORD *hchar, WORD *wbox, WORD *hbox)
{
    WORD h = aes(77, 0, 5, 0, 0);
    *wchar = int_out[1];
    *hchar = int_out[2];
    *wbox  = int_out[3];
    *hbox  = int_out[4];
    return h;
}

WORD objc_draw(OBJECT *tree, WORD start, WORD depth, WORD x, WORD y, WORD w, WORD h)
{
    int_in[0] = start;
    int_in[1] = depth;
    int_in[2] = x;
    int_in[3] = y;
    int_in[4] = w;
    int_in[5] = h;
    addr_in[0] = (LONG)(uint32_t)(OBJECT FAR *)tree;
    return aes(42, 6, 1, 1, 0);
}

WORD wind_create(WORD kind, WORD x, WORD y, WORD w, WORD h)
{
    int_in[0] = kind;
    int_in[1] = x;
    int_in[2] = y;
    int_in[3] = w;
    int_in[4] = h;
    return aes(100, 5, 1, 0, 0);
}

WORD wind_open(WORD handle, WORD x, WORD y, WORD w, WORD h)
{
    int_in[0] = handle;
    int_in[1] = x;
    int_in[2] = y;
    int_in[3] = w;
    int_in[4] = h;
    return aes(101, 5, 1, 0, 0);
}

WORD wind_get(WORD handle, WORD field, WORD *o1, WORD *o2, WORD *o3, WORD *o4)
{
    WORD r;
    int_in[0] = handle;
    int_in[1] = field;
    r = aes(104, 2, 5, 0, 0);
    *o1 = int_out[1];
    *o2 = int_out[2];
    *o3 = int_out[3];
    *o4 = int_out[4];
    return r;
}

WORD wind_close(WORD handle)
{
    int_in[0] = handle;
    return aes(102, 1, 1, 0, 0);
}

WORD wind_delete(WORD handle)
{
    int_in[0] = handle;
    return aes(103, 1, 1, 0, 0);
}

WORD wind_set(WORD handle, WORD field, WORD w1, WORD w2, WORD w3, WORD w4)
{
    int_in[0] = handle;
    int_in[1] = field;
    int_in[2] = w1;
    int_in[3] = w2;
    int_in[4] = w3;
    int_in[5] = w4;
    return aes(105, 6, 1, 0, 0);
}

WORD wind_find(WORD x, WORD y)
{
    int_in[0] = x;
    int_in[1] = y;
    return aes(106, 2, 1, 0, 0);
}

WORD wind_update(WORD code)
{
    int_in[0] = code;
    return aes(107, 1, 1, 0, 0);
}

WORD wind_calc(WORD type, WORD kind, WORD x, WORD y, WORD w, WORD h,
               WORD *ox, WORD *oy, WORD *ow, WORD *oh)
{
    WORD r;
    int_in[0] = type;
    int_in[1] = kind;
    int_in[2] = x;
    int_in[3] = y;
    int_in[4] = w;
    int_in[5] = h;
    r = aes(108, 6, 5, 0, 0);
    *ox = int_out[1];
    *oy = int_out[2];
    *ow = int_out[3];
    *oh = int_out[4];
    return r;
}

WORD evnt_timer(UWORD lo, UWORD hi)
{
    int_in[0] = (WORD)lo;
    int_in[1] = (WORD)hi;
    return aes(24, 2, 1, 0, 0);
}

WORD evnt_keybd(void)
{
    return aes(20, 0, 1, 0, 0);
}

WORD evnt_button(WORD clicks, UWORD mask, UWORD state,
                 WORD *mx, WORD *my, WORD *mb, WORD *ks)
{
    WORD r;
    int_in[0] = clicks;
    int_in[1] = (WORD)mask;
    int_in[2] = (WORD)state;
    r = aes(21, 3, 5, 0, 0);
    *mx = int_out[1];
    *my = int_out[2];
    *mb = int_out[3];
    *ks = int_out[4];
    return r;
}

WORD evnt_mesag(WORD *msg)
{
    addr_in[0] = (LONG)(uint32_t)(WORD FAR *)msg;
    return aes(23, 0, 1, 1, 0);
}

/* The ST's int_in: flags, the button's clicks/mask/state, the two mouse
 * rectangles as five words each, the timer's two words -- 16 words. */
WORD evnt_multi_moblk(UWORD flags, WORD bclk, UWORD bmsk, UWORD bst,
                      const MOBLK *m1, const MOBLK *m2, WORD *msg,
                      UWORD tlo, UWORD thi,
                      WORD *mx, WORD *my, WORD *mb, WORD *ks, WORD *kr, WORD *br)
{
    static const MOBLK none = { 0, 0, 0, 0, 0 };
    const WORD *p;
    WORD r, i;

    int_in[0] = (WORD)flags;
    int_in[1] = bclk;
    int_in[2] = (WORD)bmsk;
    int_in[3] = (WORD)bst;
    p = (const WORD *)((flags & MU_M1) && m1 ? m1 : &none);
    for (i = 0; i < 5; i++)
        int_in[4 + i] = p[i];
    p = (const WORD *)((flags & MU_M2) && m2 ? m2 : &none);
    for (i = 0; i < 5; i++)
        int_in[9 + i] = p[i];
    int_in[14] = (WORD)tlo;
    int_in[15] = (WORD)thi;
    addr_in[0] = (LONG)(uint32_t)(WORD FAR *)msg;
    r = aes(25, 16, 7, 1, 0);
    *mx = int_out[1];
    *my = int_out[2];
    *mb = int_out[3];
    *ks = int_out[4];
    *kr = int_out[5];
    *br = int_out[6];
    return r;
}

/* The ST's shape of the same call: the rectangles arrive flat, five
 * words each, and go into two MOBLKs for the call above. */
WORD evnt_multi(WORD flags, WORD bclk, WORD bmsk, WORD bst,
                WORD m1flags, WORD m1x, WORD m1y, WORD m1w, WORD m1h,
                WORD m2flags, WORD m2x, WORD m2y, WORD m2w, WORD m2h,
                WORD *msg, WORD tlo, WORD thi,
                WORD *mx, WORD *my, WORD *mb, WORD *ks, WORD *kr, WORD *br)
{
    MOBLK m1, m2;

    m1.m_out = m1flags;
    m1.m_x = m1x;
    m1.m_y = m1y;
    m1.m_w = m1w;
    m1.m_h = m1h;
    m2.m_out = m2flags;
    m2.m_x = m2x;
    m2.m_y = m2y;
    m2.m_w = m2w;
    m2.m_h = m2h;
    return evnt_multi_moblk((UWORD)flags, bclk, (UWORD)bmsk, (UWORD)bst, &m1, &m2,
                            msg, (UWORD)tlo, (UWORD)thi, mx, my, mb, ks, kr, br);
}

/* -- the menu, object, form, graphics and resource libraries: a tree in
 * addr_in[0] and words after it. */

static LONG tree_addr(OBJECT *tree)
{
    return (LONG)(uint32_t)(OBJECT FAR *)tree;
}

WORD menu_bar(OBJECT *tree, WORD showit)
{
    int_in[0] = showit;
    addr_in[0] = tree_addr(tree);
    return aes(30, 1, 1, 1, 0);
}

WORD menu_icheck(OBJECT *tree, WORD item, WORD check)
{
    int_in[0] = item;
    int_in[1] = check;
    addr_in[0] = tree_addr(tree);
    return aes(31, 2, 1, 1, 0);
}

WORD menu_ienable(OBJECT *tree, WORD item, WORD enable)
{
    int_in[0] = item;
    int_in[1] = enable;
    addr_in[0] = tree_addr(tree);
    return aes(32, 2, 1, 1, 0);
}

WORD menu_tnormal(OBJECT *tree, WORD title, WORD normal)
{
    int_in[0] = title;
    int_in[1] = normal;
    addr_in[0] = tree_addr(tree);
    return aes(33, 2, 1, 1, 0);
}

WORD objc_add(OBJECT *tree, WORD parent, WORD child)
{
    int_in[0] = parent;
    int_in[1] = child;
    addr_in[0] = tree_addr(tree);
    return aes(40, 2, 1, 1, 0);
}

WORD objc_delete(OBJECT *tree, WORD obj)
{
    int_in[0] = obj;
    addr_in[0] = tree_addr(tree);
    return aes(41, 1, 1, 1, 0);
}

WORD objc_find(OBJECT *tree, WORD start, WORD depth, WORD mx, WORD my)
{
    int_in[0] = start;
    int_in[1] = depth;
    int_in[2] = mx;
    int_in[3] = my;
    addr_in[0] = tree_addr(tree);
    return aes(43, 4, 1, 1, 0);
}

WORD objc_offset(OBJECT *tree, WORD obj, WORD *x, WORD *y)
{
    WORD r;
    int_in[0] = obj;
    addr_in[0] = tree_addr(tree);
    r = aes(44, 1, 3, 1, 0);
    *x = int_out[1];
    *y = int_out[2];
    return r;
}

WORD objc_change(OBJECT *tree, WORD obj, WORD resvd, WORD x, WORD y, WORD w, WORD h,
                 WORD state, WORD redraw)
{
    int_in[0] = obj;
    int_in[1] = resvd;
    int_in[2] = x;
    int_in[3] = y;
    int_in[4] = w;
    int_in[5] = h;
    int_in[6] = state;
    int_in[7] = redraw;
    addr_in[0] = tree_addr(tree);
    return aes(47, 8, 1, 1, 0);
}

/* objc_sysvar -- what the AES will tell you about 3D object rendering.
 * Four words in, three out, and NO TREE: the Compendium's binding
 * (6.121) and the AES's own table agree, 48 with 4/3/0.
 *
 * gem4xe draws no 3D objects, so an inquiry answers zero throughout and
 * a set is refused with 0.  That is the useful answer and not an empty
 * one: AD3DVALUE says how much room an object needs for its 3D border,
 * and a system that draws none needs none -- cflib lays its objects out
 * by exactly this. */
WORD objc_sysvar(WORD mode, WORD which, WORD in1, WORD in2,
                 WORD *out1, WORD *out2)
{
    WORD r;
    int_in[0] = mode;
    int_in[1] = which;
    int_in[2] = in1;
    int_in[3] = in2;
    r = aes(48, 4, 3, 0, 0);
    if (out1)
        *out1 = int_out[1];
    if (out2)
        *out2 = int_out[2];
    return r;
}


WORD objc_order(OBJECT *tree, WORD obj, WORD newpos)
{
    int_in[0] = obj;
    int_in[1] = newpos;
    addr_in[0] = tree_addr(tree);
    return aes(45, 2, 1, 1, 0);
}

WORD form_do(OBJECT *tree, WORD start)
{
    int_in[0] = start;
    addr_in[0] = tree_addr(tree);
    return aes(50, 1, 1, 1, 0);
}

WORD form_dial(WORD type, WORD x1, WORD y1, WORD w1, WORD h1,
               WORD x2, WORD y2, WORD w2, WORD h2)
{
    int_in[0] = type;
    int_in[1] = x1;
    int_in[2] = y1;
    int_in[3] = w1;
    int_in[4] = h1;
    int_in[5] = x2;
    int_in[6] = y2;
    int_in[7] = w2;
    int_in[8] = h2;
    return aes(51, 9, 1, 0, 0);
}

WORD form_alert(WORD defbut, const char *s)
{
    int_in[0] = defbut;
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)s;
    return aes(52, 1, 1, 1, 0);
}

WORD form_error(WORD n)
{
    int_in[0] = n;
    return aes(53, 1, 1, 0, 0);
}

WORD form_center(OBJECT *tree, WORD *x, WORD *y, WORD *w, WORD *h)
{
    WORD r;
    addr_in[0] = tree_addr(tree);
    r = aes(54, 0, 5, 1, 0);
    *x = int_out[1];
    *y = int_out[2];
    *w = int_out[3];
    *h = int_out[4];
    return r;
}

static WORD graf_box(WORD op, WORD x1, WORD y1, WORD w1, WORD h1,
                     WORD x2, WORD y2, WORD w2, WORD h2)
{
    int_in[0] = x1;
    int_in[1] = y1;
    int_in[2] = w1;
    int_in[3] = h1;
    int_in[4] = x2;
    int_in[5] = y2;
    int_in[6] = w2;
    int_in[7] = h2;
    return aes(op, 8, 1, 0, 0);
}

WORD graf_growbox(WORD x1, WORD y1, WORD w1, WORD h1, WORD x2, WORD y2, WORD w2, WORD h2)
{
    return graf_box(73, x1, y1, w1, h1, x2, y2, w2, h2);
}

WORD graf_shrinkbox(WORD x1, WORD y1, WORD w1, WORD h1, WORD x2, WORD y2, WORD w2, WORD h2)
{
    return graf_box(74, x1, y1, w1, h1, x2, y2, w2, h2);
}

/* The AES drags the outline for us and answers where it was let go:
 * the desktop's drag-and-drop, and the same call the control manager
 * moves a window with. */
WORD graf_dragbox(WORD w, WORD h, WORD sx, WORD sy,
                  WORD bx, WORD by, WORD bw, WORD bh, WORD *px, WORD *py)
{
    WORD r;

    int_in[0] = w;
    int_in[1] = h;
    int_in[2] = sx;
    int_in[3] = sy;
    int_in[4] = bx;
    int_in[5] = by;
    int_in[6] = bw;
    int_in[7] = bh;
    r = aes(71, 8, 3, 0, 0);
    *px = int_out[1];
    *py = int_out[2];
    return r;
}

WORD graf_mouse(WORD mode, const WORD *form)
{
    int_in[0] = mode;
    addr_in[0] = (LONG)(uint32_t)(const WORD FAR *)form;
    return aes(78, 1, 1, 1, 0);
}

WORD graf_mkstate(WORD *mx, WORD *my, WORD *mb, WORD *ks)
{
    WORD r = aes(79, 0, 5, 0, 0);
    *mx = int_out[1];
    *my = int_out[2];
    *mb = int_out[3];
    *ks = int_out[4];
    return r;
}

WORD rsrc_load(const char *name)
{
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)name;
#ifdef __CALYPSI_DATA_MODEL_LARGE__
    /* This program holds 32-bit pointers, so it can take a resource in far
     * memory: int_in[0] bit 0 says so, and the AES goes far only when the
     * file will not fit the pool AND this is set (docs/far-trees.md).  The
     * small-data build below passes no int_in at all, and aes_entry zeroes
     * them, so it can never ask by accident -- and a 16-bit program handed
     * a far resource would have its pointers truncated with no error. */
    int_in[0] = 1;
    return aes(110, 1, 1, 1, 0);
#else
    return aes(110, 0, 1, 1, 0);
#endif
}

WORD rsrc_free(void)
{
    return aes(111, 0, 1, 0, 0);
}

WORD rsrc_gaddr(WORD type, WORD index, void **addr)
{
    WORD r;
    int_in[0] = type;
    int_in[1] = index;
    r = aes(112, 2, 1, 0, 1);
#ifdef __CALYPSI_DATA_MODEL_LARGE__
    *addr = (void *)(uint32_t)addr_out[0];  /* all 24 bits: it may be far */
#else
    *addr = (void *)(uint16_t)addr_out[0];  /* a pool resource: bank $00 */
#endif
    return r;
}

WORD shel_write(WORD doex, WORD isgr, WORD iscr, const char *cmd, const char *tail)
{
    int_in[0] = doex;
    int_in[1] = isgr;
    int_in[2] = iscr;
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)cmd;
    addr_in[1] = (LONG)(uint32_t)(const char FAR *)tail;
    return aes(121, 3, 1, 2, 0);
}

WORD shel_get(void FAR *buffer, WORD len)
{
    int_in[0] = len;
    addr_in[0] = (LONG)(uint32_t)buffer;
    return aes(122, 1, 1, 1, 0);
}

WORD shel_put(const void FAR *data, WORD len)
{
    int_in[0] = len;
    addr_in[0] = (LONG)(uint32_t)data;
    return aes(123, 1, 1, 1, 0);
}

/* -- AES: the rest of the surface --------------------------------------
 *
 * The calls src/sys/abi.c serves and the library did not reach: an
 * application can now make every one of them by name.  The counts are
 * the ST's -- the AES reads control[1..4] to know how much to copy in
 * and out, so a binding that miscounts is a binding that loses an
 * argument.
 */

WORD appl_read(WORD id, WORD length, WORD *msg)
{
    int_in[0] = id;
    int_in[1] = length;
    addr_in[0] = (LONG)(uint32_t)(WORD FAR *)msg;
    return aes(11, 2, 1, 1, 0);
}

WORD appl_write(WORD id, WORD length, const WORD *msg)
{
    int_in[0] = id;
    int_in[1] = length;
    addr_in[0] = (LONG)(uint32_t)(const WORD FAR *)msg;
    return aes(12, 2, 1, 1, 0);
}

WORD evnt_mouse(WORD flags, WORD x, WORD y, WORD w, WORD h,
                WORD *mx, WORD *my, WORD *button, WORD *kstate)
{
    WORD r;
    int_in[0] = flags;
    int_in[1] = x;
    int_in[2] = y;
    int_in[3] = w;
    int_in[4] = h;
    r = aes(22, 5, 5, 0, 0);
    *mx = int_out[1];
    *my = int_out[2];
    *button = int_out[3];
    *kstate = int_out[4];
    return r;
}

WORD evnt_dclick(WORD rate, WORD setit)
{
    int_in[0] = rate;
    int_in[1] = setit;
    return aes(26, 2, 1, 0, 0);
}

WORD menu_text(OBJECT *tree, WORD item, const char *text)
{
    int_in[0] = item;
    addr_in[0] = tree_addr(tree);
    addr_in[1] = (LONG)(uint32_t)(const char FAR *)text;
    return aes(34, 1, 1, 2, 0);
}

WORD menu_register(WORD pid, const char *str)
{
    int_in[0] = pid;
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)str;
    return aes(35, 1, 1, 1, 0);
}

/* The name is EIGHT CHARACTERS, blank-padded, and the caller does the
 * padding: appl_find("QED") finds nothing and appl_find("QED     ")
 * finds it.  That is the ST's contract, kept rather than softened, so a
 * program that works here works there. */
WORD appl_find(const char *fname)
{
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)fname;
    return aes(13, 0, 1, 1, 0);
}

/* FIVE out words, not one: int_out[0] is the answer and 1..4 the four
 * values -- the widest copy-out of any AES call gem4xe serves.  The
 * count in the control block is what makes the shim copy them, and this
 * reads all four unconditionally, as the ST's binding does; a count that
 * said 3 would hand the caller the last call's words 3 and 4 rather than
 * zeros, which is what test-m11 shows when it is made to.  A caller may
 * pass a null pointer for any of them (gemlib allows it). */
WORD appl_getinfo(WORD ap_gtype, WORD *ap_gout1, WORD *ap_gout2,
                  WORD *ap_gout3, WORD *ap_gout4)
{
    WORD r;
    int_in[0] = ap_gtype;
    r = aes(130, 1, 5, 0, 0);
    if (ap_gout1) *ap_gout1 = int_out[1];
    if (ap_gout2) *ap_gout2 = int_out[2];
    if (ap_gout3) *ap_gout3 = int_out[3];
    if (ap_gout4) *ap_gout4 = int_out[4];
    return r;
}

WORD appl_xgetinfo(WORD ap_gtype, WORD *ap_gout1, WORD *ap_gout2,
                   WORD *ap_gout3, WORD *ap_gout4)
{
    return appl_getinfo(ap_gtype, ap_gout1, ap_gout2, ap_gout3, ap_gout4);
}

/* objc_edit: `idx` is both the cursor position going in and the one
 * that comes back (the ST passes it by address; here it is a word in
 * and a word out, which is what the shim does with it). */
WORD objc_edit(OBJECT *tree, WORD obj, WORD in_char, WORD *idx, WORD kind)
{
    WORD r;
    int_in[0] = obj;
    int_in[1] = in_char;
    int_in[2] = *idx;
    int_in[3] = kind;
    addr_in[0] = tree_addr(tree);
    r = aes(46, 4, 2, 1, 0);
    *idx = int_out[1];
    return r;
}

WORD form_keybd(OBJECT *tree, WORD obj, WORD nxt_obj, WORD thechar,
                WORD *pnxt_obj, WORD *pchar)
{
    WORD r;
    int_in[0] = obj;
    int_in[1] = thechar;
    int_in[2] = nxt_obj;
    addr_in[0] = tree_addr(tree);
    r = aes(55, 3, 3, 1, 0);
    *pnxt_obj = int_out[1];
    *pchar = int_out[2];
    return r;
}

WORD form_button(OBJECT *tree, WORD obj, WORD clks, WORD *pnxt_obj)
{
    WORD r;
    int_in[0] = obj;
    int_in[1] = clks;
    addr_in[0] = tree_addr(tree);
    r = aes(56, 2, 2, 1, 0);
    *pnxt_obj = int_out[1];
    return r;
}

/* graf_mbox (72).  The Compendium calls it graf_movebox now and says
 * graf_mbox is what "older C bindings" used (p.407); a port may carry
 * either spelling, so both are here and both are the one opcode. */
/* wind_new (109): close and delete every window this program has, and
 * put wind_update's locks and the pointer's hide count back.  The
 * return is reserved -- do not test it. */
WORD wind_new(void)
{
    return aes(109, 0, 1, 0, 0);
}

WORD graf_mbox(WORD w, WORD h, WORD sx, WORD sy, WORD ex, WORD ey)
{
    int_in[0] = w;  int_in[1] = h;
    int_in[2] = sx; int_in[3] = sy;
    int_in[4] = ex; int_in[5] = ey;
    return aes(72, 6, 1, 0, 0);
}

WORD graf_movebox(WORD w, WORD h, WORD sx, WORD sy, WORD ex, WORD ey)
{
    return graf_mbox(w, h, sx, sy, ex, ey);
}

/* graf_slidebox (76): answers where the child ended up, 0..1000 of the
 * way along its parent -- a measurement, not a status. */
WORD graf_slidebox(OBJECT *tree, WORD parent, WORD obj, WORD orient)
{
    int_in[0] = parent;
    int_in[1] = obj;
    int_in[2] = orient;
    addr_in[0] = (LONG)(uint32_t)(OBJECT FAR *)tree;
    return aes(76, 3, 1, 1, 0);
}

WORD graf_rubbox(WORD x, WORD y, WORD w, WORD h, WORD *pw, WORD *ph)
{
    WORD r;
    int_in[0] = x;
    int_in[1] = y;
    int_in[2] = w;
    int_in[3] = h;
    r = aes(70, 4, 3, 0, 0);
    *pw = int_out[1];
    *ph = int_out[2];
    return r;
}

WORD graf_watchbox(OBJECT *tree, WORD obj, WORD instate, WORD outstate)
{
    int_in[1] = obj;
    int_in[2] = instate;
    int_in[3] = outstate;
    addr_in[0] = tree_addr(tree);
    return aes(75, 4, 1, 1, 0);
}

/* The file selector.  The path and the name are the caller's buffers
 * and come back written; the button is 1 for OK and 0 for Cancel. */
WORD fsel_input(char *path, char *sel, WORD *button)
{
    WORD r;
    addr_in[0] = (LONG)(uint32_t)(char FAR *)path;
    addr_in[1] = (LONG)(uint32_t)(char FAR *)sel;
    r = aes(90, 0, 2, 2, 0);
    *button = int_out[1];
    return r;
}

WORD fsel_exinput(char *path, char *sel, WORD *button, const char *label)
{
    WORD r;
    addr_in[0] = (LONG)(uint32_t)(char FAR *)path;
    addr_in[1] = (LONG)(uint32_t)(char FAR *)sel;
    addr_in[2] = (LONG)(uint32_t)(const char FAR *)label;
    r = aes(91, 0, 2, 3, 0);
    *button = int_out[1];
    return r;
}

WORD rsrc_saddr(WORD type, WORD index, void *addr)
{
    int_in[0] = type;
    int_in[1] = index;
    addr_in[0] = (LONG)(uint32_t)(void FAR *)addr;
    return aes(113, 2, 1, 1, 0);
}

WORD rsrc_obfix(OBJECT *tree, WORD obj)
{
    int_in[0] = obj;
    addr_in[0] = tree_addr(tree);
    return aes(114, 1, 1, 1, 0);
}

WORD scrp_read(char *path)
{
    addr_in[0] = (LONG)(uint32_t)(char FAR *)path;
    return aes(80, 0, 1, 1, 0);
}

WORD scrp_write(const char *path)
{
    addr_in[0] = (LONG)(uint32_t)(const char FAR *)path;
    return aes(81, 0, 1, 1, 0);
}

WORD scrp_clear(void)
{
    return aes(82, 0, 1, 0, 0);
}

WORD shel_read(char *cmd, char *tail)
{
    addr_in[0] = (LONG)(uint32_t)(char FAR *)cmd;
    addr_in[1] = (LONG)(uint32_t)(char FAR *)tail;
    return aes(120, 0, 1, 2, 0);
}

WORD shel_find(char *path)
{
    addr_in[0] = (LONG)(uint32_t)(char FAR *)path;
    return aes(124, 0, 1, 1, 0);
}

WORD shel_envrn(char **value, const char *name)
{
    addr_in[0] = (LONG)(uint32_t)(void FAR *)value;
    addr_in[1] = (LONG)(uint32_t)(const char FAR *)name;
    return aes(125, 0, 1, 2, 0);
}

/* -- GEMDOS ---------------------------------------------------------- */

static GDPB dpb;

/* The arguments go into the block as the ST's trap #1 pushes them: at
 * byte offsets from 6, WORDs two wide and LONGs four, low byte first. */
static void dw(WORD off, WORD v)
{
    dpb.arg[(off - 6) >> 1] = v;
}

static void dl(WORD off, LONG v)
{
    dpb.arg[(off - 6) >> 1] = (WORD)v;
    dpb.arg[(off - 4) >> 1] = (WORD)(v >> 16);
}

static LONG dos(WORD fn)
{
    dpb.fn = fn;
    dos_call(&dpb);
    return dpb.ret;
}

WORD Sversion(void)                       { return (WORD)dos(0x30); }
WORD Dgetdrv(void)                        { return (WORD)dos(0x19); }
WORD Dsetdrv(WORD drive)                  { dw(6, drive); return (WORD)dos(0x0E); }
LONG Dsetpath(const char FAR *path)     { dl(6, (LONG)path); return dos(0x3B); }
LONG Dcreate(const char FAR *path)      { dl(6, (LONG)path); return dos(0x39); }
LONG Ddelete(const char FAR *path)      { dl(6, (LONG)path); return dos(0x3A); }
LONG Fdelete(const char FAR *name)      { dl(6, (LONG)name); return dos(0x41); }
LONG Fsnext(void)                         { return dos(0x4F); }
LONG Fclose(WORD handle)                  { dw(6, handle); return dos(0x3E); }
LONG Malloc(LONG size)                    { dl(6, size); return dos(0x48); }
LONG Mfree(void FAR *block)             { dl(6, (LONG)block); return dos(0x49); }
void Fsetdta(DTA FAR *dta)              { dl(6, (LONG)dta); dos(0x1A); }
DTA FAR *Fgetdta(void)                  { return (DTA FAR *)dos(0x2F); }

LONG Dgetpath(char FAR *buf, WORD drive)
{
    dl(6, (LONG)buf);
    dw(10, drive);
    return dos(0x47);
}

LONG Dfree(DISKINFO FAR *info, WORD drive)
{
    dl(6, (LONG)info);
    dw(10, drive);
    return dos(0x36);
}

LONG Fsfirst(const char FAR *spec, WORD attr)
{
    dl(6, (LONG)spec);
    dw(10, attr);
    return dos(0x4E);
}

LONG Fopen(const char FAR *name, WORD mode)
{
    dl(6, (LONG)name);
    dw(10, mode);
    return dos(0x3D);
}

LONG Fcreate(const char FAR *name, WORD attr)
{
    dl(6, (LONG)name);
    dw(10, attr);
    return dos(0x3C);
}

LONG Fread(WORD handle, LONG count, void FAR *buf)
{
    dw(6, handle);
    dl(8, count);
    dl(12, (LONG)buf);
    return dos(0x3F);
}

LONG Fwrite(WORD handle, LONG count, const void FAR *buf)
{
    dw(6, handle);
    dl(8, count);
    dl(12, (LONG)buf);
    return dos(0x40);
}

LONG Fseek(LONG offset, WORD handle, WORD mode)
{
    dl(6, offset);
    dw(10, handle);
    dw(12, mode);
    return dos(0x42);
}

LONG Frename(const char FAR *oldname, const char FAR *newname)
{
    dw(6, 0);
    dl(8, (LONG)oldname);
    dl(12, (LONG)newname);
    return dos(0x56);
}

LONG Fattrib(const char FAR *name, WORD wflag, WORD attr)
{
    dl(6, (LONG)name);
    dw(10, wflag);
    dw(12, attr);
    return dos(0x43);
}

/* The three GEMDOS calls phase 16 filled in and the library had not
 * caught up with (src/sys/gemdos.c). */
LONG Fdatime(WORD *timeptr, WORD handle, WORD wflag)
{
    dl(6, (LONG)(uint32_t)(WORD FAR *)timeptr);
    dw(10, handle);
    dw(12, wflag);
    return dos(0x57);
}

WORD Tgetdate(void)
{
    return (WORD)dos(0x2A);
}

WORD Tgettime(void)
{
    return (WORD)dos(0x2C);
}

LONG Tgettimeofday(struct timeval FAR *tv, struct timezone FAR *tz)
{
    dl(6, (LONG)(uint32_t)tv);
    dl(10, (LONG)(uint32_t)tz);
    return dos(0x155);
}

LONG Psystem(const char FAR *line, void FAR *out, LONG max)
{
    dl(6, (LONG)(uint32_t)line);
    dl(10, (LONG)(uint32_t)out);
    dl(14, max);
    return dos(0x1F0);
}

/* clock(): elapsed time since the program first asked, in CLOCKS_PER_SEC
 * units as the compiler's <time.h> defines them, over Tgettimeofday.  It
 * lives here and not in clib.c because it is a binding -- and because
 * clib.c is also gem4xe's own, where there is no call gate to make.  A
 * program written against mintlib's clock() -- the ST's 200 Hz tick --
 * that scales by CLOCKS_PER_SEC runs unchanged. */
#include <time.h>
clock_t clock(void)
{
    static LONG  s0;
    static WORD  started;
    struct timeval tv;

    uint32_t ms;

    Tgettimeofday(&tv, 0);
    if (!started) {
        s0 = tv.tv_sec;
        started = 1;
    }
    /* In 32 bits throughout: milliseconds since the first call (good for
     * 49 days), scaled to the header's rate a second at a time so nothing
     * overflows.  clock_t is 64 bits on this compiler, and a 64-bit
     * quotient did not come out right here (it answered the dividend), so
     * the wide type carries the result and takes no part in the sum. */
    ms = (uint32_t)(tv.tv_sec - s0) * 1000UL + (uint32_t)tv.tv_usec / 1000UL;
    return (clock_t)((ms / 1000UL) * (uint32_t)CLOCKS_PER_SEC
                     + (ms % 1000UL) * (uint32_t)CLOCKS_PER_SEC / 1000UL);
}

/* The C functions, the rest of memory, setting the clock and the end:
 * the calls phase 42 filled in (src/sys/gemdos.c). */
void Pterm0(void)                       { dos(0x00); }
LONG Cconin(void)                       { return dos(0x01); }
void Cconout(WORD c)                    { dw(6, c); dos(0x02); }
WORD Cauxin(void)                       { return (WORD)dos(0x03); }
void Cauxout(WORD c)                    { dw(6, c); dos(0x04); }
WORD Cprnout(WORD c)                    { dw(6, c); return (WORD)dos(0x05); }
LONG Crawio(WORD c)                     { dw(6, c); return dos(0x06); }
LONG Crawcin(void)                      { return dos(0x07); }
LONG Cnecin(void)                       { return dos(0x08); }
void Cconws(const char FAR *s)          { dl(6, (LONG)s); dos(0x09); }
void Cconrs(char FAR *buf)              { dl(6, (LONG)buf); dos(0x0A); }
WORD Cconis(void)                       { return (WORD)dos(0x0B); }
WORD Cconos(void)                       { return (WORD)dos(0x10); }
WORD Cprnos(void)                       { return (WORD)dos(0x11); }
WORD Cauxis(void)                       { return (WORD)dos(0x12); }
WORD Cauxos(void)                       { return (WORD)dos(0x13); }
LONG Super(void FAR *stack)             { dl(6, (LONG)stack); return dos(0x20); }
WORD Tsetdate(UWORD date)               { dw(6, (WORD)date); return (WORD)dos(0x2B); }
WORD Tsettime(UWORD time)               { dw(6, (WORD)time); return (WORD)dos(0x2D); }
LONG Mxalloc(LONG size, WORD mode)      { dl(6, size); dw(10, mode); return dos(0x44); }
LONG Fdup(WORD handle)                  { dw(6, handle); return dos(0x45); }
LONG Fforce(WORD handle, WORD target)   { dw(6, handle); dw(8, target); return dos(0x46); }
void Pterm(WORD code)                   { dw(6, code); dos(0x4C); }

LONG Pexec(WORD mode, const char FAR *name, const char FAR *tail,
           const char FAR *env)
{
    dw(6, mode);
    dl(8, (LONG)name);
    dl(12, (LONG)tail);
    dl(16, (LONG)env);
    return dos(0x4B);
}

void Ptermres(LONG keep, WORD code)
{
    dl(6, keep);
    dw(10, code);
    dos(0x31);
}

LONG Mshrink(void FAR *block, LONG newsize)
{
    dw(6, 0);                           /* the ST's binding pushes a zero word */
    dl(8, (LONG)block);
    dl(12, newsize);
    return dos(0x4A);
}

/* -- The GRECT half of the library (src/app/gem.h).
 *
 * rc_intersect and rc_union are Atari's own, transcribed from the rule
 * rather than the code: the intersection is the later of the two left
 * edges to the earlier of the two right ones, and it exists only if that
 * leaves a positive width AND a positive height.  Both write their answer
 * into the SECOND rectangle, which is the ST's order and the reason a
 * redraw loop can pass the window's work area first and the dirty
 * rectangle second and have the dirty one come back clipped.
 *
 * The rest are gemlib's spellings over calls this library already has:
 * one GRECT where the AES takes four loose words.  Nothing here reaches
 * the AES that the call underneath does not. */
WORD rc_intersect(const GRECT *src, GRECT *dst)
{
    WORD x, y, w, h;

    x = src->g_x > dst->g_x ? src->g_x : dst->g_x;
    y = src->g_y > dst->g_y ? src->g_y : dst->g_y;
    w = src->g_x + src->g_w < dst->g_x + dst->g_w
        ? (WORD)(src->g_x + src->g_w) : (WORD)(dst->g_x + dst->g_w);
    h = src->g_y + src->g_h < dst->g_y + dst->g_h
        ? (WORD)(src->g_y + src->g_h) : (WORD)(dst->g_y + dst->g_h);
    dst->g_x = x;
    dst->g_y = y;
    dst->g_w = (WORD)(w - x);
    dst->g_h = (WORD)(h - y);
    return (WORD)(w > x && h > y);
}

void rc_union(const GRECT *src, GRECT *dst)
{
    WORD x, y, w, h;

    x = src->g_x < dst->g_x ? src->g_x : dst->g_x;
    y = src->g_y < dst->g_y ? src->g_y : dst->g_y;
    w = src->g_x + src->g_w > dst->g_x + dst->g_w
        ? (WORD)(src->g_x + src->g_w) : (WORD)(dst->g_x + dst->g_w);
    h = src->g_y + src->g_h > dst->g_y + dst->g_h
        ? (WORD)(src->g_y + src->g_h) : (WORD)(dst->g_y + dst->g_h);
    dst->g_x = x;
    dst->g_y = y;
    dst->g_w = (WORD)(w - x);
    dst->g_h = (WORD)(h - y);
}

WORD wind_create_grect(WORD kind, const GRECT *r)
{
    return wind_create(kind, r->g_x, r->g_y, r->g_w, r->g_h);
}

WORD wind_open_grect(WORD handle, const GRECT *r)
{
    return wind_open(handle, r->g_x, r->g_y, r->g_w, r->g_h);
}

WORD wind_get_grect(WORD handle, WORD field, GRECT *r)
{
    return wind_get(handle, field, &r->g_x, &r->g_y, &r->g_w, &r->g_h);
}

WORD wind_set_grect(WORD handle, WORD field, const GRECT *r)
{
    return wind_set(handle, field, r->g_x, r->g_y, r->g_w, r->g_h);
}

WORD wind_calc_grect(WORD type, WORD kind, const GRECT *in, GRECT *out)
{
    return wind_calc(type, kind, in->g_x, in->g_y, in->g_w, in->g_h,
                     &out->g_x, &out->g_y, &out->g_w, &out->g_h);
}

/* The string is an address in two words, high first -- the ST's intin
 * layout, which src/aes/wind.c reads back from pinwds[1].  The whole
 * address goes in rather than the low half, on tree_addr's discipline:
 * the AES addresses what it reads in place with 16 bits, so a string
 * that is NOT in bank $00 is a caller's bug, and a high word of zero
 * would hide it behind whatever happens to live at that offset. */
WORD wind_set_str(WORD handle, WORD field, const char *str)
{
    LONG a = (LONG)(uint32_t)(const char FAR *)str;
    return wind_set(handle, field, (WORD)((uint32_t)a >> 16), (WORD)a, 0, 0);
}

WORD form_center_grect(OBJECT *tree, GRECT *r)
{
    return form_center(tree, &r->g_x, &r->g_y, &r->g_w, &r->g_h);
}

WORD form_dial_grect(WORD flag, const GRECT *little, const GRECT *big)
{
    return form_dial(flag, little->g_x, little->g_y, little->g_w, little->g_h,
                     big->g_x, big->g_y, big->g_w, big->g_h);
}

WORD objc_draw_grect(OBJECT *tree, WORD start, WORD depth, const GRECT *r)
{
    return objc_draw(tree, start, depth, r->g_x, r->g_y, r->g_w, r->g_h);
}
