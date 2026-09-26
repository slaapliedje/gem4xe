/* bugs.c -- the cc65816 5.18 code generation bugs gem4xe works around.
 *
 * Every bug is a pair of shapes: the one that miscompiles and the one the
 * sources use instead.  check.py builds this with the vendor's own minimal
 * linker script and C library, runs it in db65816's simulator, and reads the
 * results back through the volatile globals.  A bug that has gone away is
 * news (the workaround can go); a workaround shape that has stopped working
 * is a failure, because gem4xe is built on it.
 *
 * The shapes are lifted from where each bug was met: everyobj() in
 * src/aes/objc.c (B1), gsx_tcalc() in src/aes/graf.c (B2, B3), ob_sst()
 * in src/aes/objc.c (B4), vdi_vrt_cpyfm() in src/vdi/vdi.c (B5), the BCB
 * overlay in src/vbxe/vbxe.c (B7), sh_cioname() in src/aes/shel.c (B8),
 * gd_xfer() in src/sys/gemdos.c (B9) and snap_icon() in src/desk/desktop.c
 * (B10).
 * Keep them recognisable rather than minimal.
 */
#include <stdint.h>

typedef short WORD;

/* ---- B1: stack array element + operand loads instead of adds ---------- */

typedef struct { WORD pad[8]; WORD ob_x, ob_y; } OBJ;
OBJ tree[3];

/* `x[depth] = x[depth-1] + tree[this].ob_x` becomes `ldy ob_x; lda (&x),y`
 * -- a load from address &x[depth-1] + ob_x, not an add. */
/* NOT static, and that is load-bearing.  As a static function called with
 * literals, -O1 and above inline it, `depth` constant-folds, the indexed
 * shape never arises and the row reports the bug as FIXED -- which it is
 * not.  This project told the vendor B1 was fixed in 5.18.1 on exactly
 * that reading.  External linkage keeps the shape. */
WORD b1_bug(OBJ *t, WORD this, WORD depth, WORD startx)
{
    WORD x[12];
    x[0] = startx;
    x[depth] = (WORD)(x[depth - 1] + t[this].ob_x);
    return x[depth];
}

/* The element through a scalar first. */
WORD b1_fix(OBJ *t, WORD this, WORD depth, WORD startx)
{
    WORD x[12], prev;
    x[0] = startx;
    prev = x[depth - 1];
    x[depth] = (WORD)(prev + t[this].ob_x);
    return x[depth];
}

WORD b3_len(const char *s) { WORD n = 0; while (*s++) n++; return n; }

/* ---- B2: the flags after _Div16 / _Mod16 are not the result's ---------- */

/* At -O2 `if (a / b)` is `jsl _Div16; beq`.  The library leaves N
 * and Z from the sign word (dividend ^ divisor) on the non-negative path, so
 * 8/8 tests as zero and 7/8 as non-zero; _Mod16 likewise tests the dividend.
 * The fix is a replacement _Div16/_Mod16 (src/sys/div16.s, linked with
 * --override), so there is no source-level "fixed" shape: check.py links
 * this program both ways. */
volatile WORD b2_hc = 8;

WORD b2_div_truth(const char *s, WORD *ph)
{
    WORD n = b3_len(s);
    if (*ph / b2_hc)            /* gsx_tcalc: does one line of text fit? */
        return n;
    return 0;
}
WORD b2_mod_truth(const char *s, WORD *ph)
{
    WORD n = b3_len(s);
    if (*ph % b2_hc)
        return n;
    return 0;
}

/* ---- B3: `*out = c ? a : b` in an inlined static function ------------- */

/* The conditional store lands in a dead stack slot; *pn is never written. */
static void b3_bug_callee(const char *s, WORD *pw, WORD *pn)
{
    WORD n = b3_len(s), m = *pw;
    *pn = (n < m) ? n : m;
}
WORD b3_bug(const char *s, WORD *pw, WORD *ph)
{
    WORD num;
    (void)ph;
    b3_bug_callee(s, pw, &num);
    return num;
}

/* Return the value instead. */
static WORD b3_fix_callee(const char *s, WORD *pw)
{
    WORD n = b3_len(s), m = *pw;
    return (n < m) ? n : m;
}
WORD b3_fix(const char *s, WORD *pw, WORD *ph) { (void)ph; return b3_fix_callee(s, pw); }

/* ---- B4: (int8_t) of a 32-bit-derived value does not sign-extend ------- */

volatile uint32_t b4_spec = 0x00FE1100;   /* char 0x00, thickness -2, colour */

static WORD b4_bug(uint32_t spec) { return (WORD)(int8_t)((spec >> 16) & 0xFF); }

static WORD b4_fix(uint32_t spec)
{
    WORD hi = (WORD)(spec >> 16);
    int8_t th = (int8_t)hi;
    return th;
}

/* ---- B5: a shifted load through a spilled pointer drops the load ------- */

/* `stride = p->field * 2u` where p is a local that lives on the stack (a
 * call preceded it) and is dead afterwards: the compiler gives stride the
 * pointer's own slot and emits `tsc; adc #slot; tax; asl 0,x` -- the slot is
 * shifted in place, so stride = p << 1 and p->field is never read.  Any
 * shift-shaped operator does it (* 2, << 1, x + x, * 4, / 2u, >> 1); * 3
 * does not, a byte field does not, a global or parameter pointer does not,
 * and a pointer still live afterwards does not.  All -O levels.
 *
 * This was the Phase 2b "unexplained" wrong-row read in vrt_cpyfm. */
typedef struct { uint32_t fd_addr; WORD fd_w, fd_h, fd_wdwidth, fd_stand; } MFDB;
MFDB b5_mfdb;
uint8_t b5_form[32];
WORD b5_contrl[8], b5_ptsin[4];

void b5_order(WORD *a, WORD *b) { if (*a > *b) { WORD t = *a; *a = *b; *b = t; } }

static WORD b5_walk(const uint8_t *bits, WORD sy1, uint16_t stride)
{
    WORD row, sum = 0;
    for (row = 0; row < 4; row++)
        sum = (WORD)(sum + bits[(uint16_t)((sy1 + row) * stride)]);
    return sum;
}

WORD b5_bug(void)
{
    MFDB *src = (MFDB *)(uint16_t)b5_contrl[7];
    WORD sy1 = b5_ptsin[1], sy2 = b5_ptsin[3];
    const uint8_t *bits;
    uint16_t stride;
    if (!src) return -1;
    b5_order(&sy1, &sy2);                       /* spills src to the stack */
    bits   = (const uint8_t *)(uint16_t)src->fd_addr;
    stride = (uint16_t)((uint16_t)src->fd_wdwidth * 2u);   /* src dead here */
    return b5_walk(bits, sy1, stride);
}

/* The field through a scalar first. */
WORD b5_fix(void)
{
    MFDB *src = (MFDB *)(uint16_t)b5_contrl[7];
    WORD sy1 = b5_ptsin[1], sy2 = b5_ptsin[3], wd;
    const uint8_t *bits;
    uint16_t stride;
    if (!src) return -1;
    b5_order(&sy1, &sy2);
    bits   = (const uint8_t *)(uint16_t)src->fd_addr;
    wd     = src->fd_wdwidth;
    stride = (uint16_t)((uint16_t)wd * 2u);
    return b5_walk(bits, sy1, stride);
}

/* The same slot-sharing with `- 1` in place of the shift: `n = p->len - 1`
 * where p is a local pointer (a call's return, so it lives on the stack)
 * that is dead after the line compiles to `tsc; adc #slot; tax; dec 0,x`
 * -- the POINTER decremented in place, the field never read, and n is a
 * bank-0 address less one.  inf_sset() in src/aes/fsel.c: a positive
 * length became a negative n, so no field of the file selector ever
 * received its text. */
typedef struct {
    uint32_t te_ptext, te_ptmplt, te_pvalid;
    WORD te_font, te_fontid, te_just, te_color, te_fontsize, te_thickness;
    WORD te_txtlen, te_tmplen;
} B5_TED;
B5_TED b5_ted;
char b5_text1[16], b5_text2[16];

B5_TED *b5_ted_of(WORD obj) { return obj ? &b5_ted : 0; }

WORD b5_dec_bug(WORD obj, const char *pstr)
{
    B5_TED *ted = b5_ted_of(obj);
    char *text = (char *)(uint16_t)ted->te_ptext;
    WORD n = ted->te_txtlen - 1;                /* ted dead here */
    WORD k = 0;
    while (n > 0 && *pstr) {
        *text++ = *pstr++;
        n--;
        k++;
    }
    *text = 0;
    return k;
}

/* The field into a scalar, the arithmetic on the scalar. */
WORD b5_dec_fix(WORD obj, const char *pstr)
{
    B5_TED *ted = b5_ted_of(obj);
    char *text = (char *)(uint16_t)ted->te_ptext;
    WORD len = ted->te_txtlen;
    WORD n = (WORD)(len - 1);
    WORD k = 0;
    while (n > 0 && *pstr) {
        *text++ = *pstr++;
        n--;
        k++;
    }
    *text = 0;
    return k;
}

/* ---- B7: sizeof a struct is padded where a constant expression is needed - */

/* The code generator lays a struct out with no padding -- a 16-bit member
 * sits at an odd offset if that is where it falls, the 65816 having no
 * alignment rule -- and `sizeof` in an ordinary expression says so.  But
 * `sizeof` where an integer constant expression is required (an enum, an
 * array bound, _Static_assert) is evaluated with 16-bit members aligned to
 * 2 and comes out larger.  A stride taken from such a constant walks off
 * the elements.  Write the byte count out instead (BCB_SIZE, src/vbxe). */
typedef struct { uint16_t a; uint8_t b; uint16_t c; } B7_S;      /* 5 bytes */
enum { B7_STRIDE = sizeof(B7_S) };                                /* says 6 */
B7_S b7_arr[3];

static WORD b7_bug(void)
{
    const uint8_t *p = (const uint8_t *)b7_arr + B7_STRIDE;
    return (WORD)((const B7_S *)p)->c;
}

static WORD b7_fix(void)
{
    const uint8_t *p = (const uint8_t *)b7_arr + 5;
    return (WORD)((const B7_S *)p)->c;
}

/* ---- B8: a byte local narrowed on one path is stored from 8-bit mode ---- */

/* `if (c >= 'a' && c <= 'z') c = (char)(c - 0x20); out[k] = c;` -- the
 * folding in sh_cioname (src/aes/shel.c).  The taken path does the
 * subtraction in 16 bits, switches to 8-bit accumulator to store the byte
 * local, and falls into the join with the mode still 8-bit; the other
 * path arrives 16-bit.  The join then loads the destination POINTER for
 * the store with an 8-bit `lda`, so the first lowercase character of a
 * name is written to page zero and its slot is left untouched.  -O2 only
 * (the -O1 code stores the byte differently).  An `unsigned char` local
 * is the same shape and the same bug; the sources hold the character in
 * a WORD and narrow it once, at the store. */
void b8_bug(const char *name, char *out)      /* not static: inlined, the shape is gone */
{
    WORD k = 0;
    for (; *name; name++, k++) {
        char c = *name;
        if (c >= 'a' && c <= 'z')
            c = (char)(c - 0x20);
        out[k] = c;
    }
    out[k] = 0;
}

void b8_fix(const char *name, char *out)
{
    WORD k = 0;
    for (; *name; name++, k++) {
        WORD c = (uint8_t)*name;
        if (c >= 'a' && c <= 'z')
            c -= 0x20;
        out[k] = (char)c;
    }
    out[k] = 0;
}

char b8_out1[8], b8_out2[8];

/* ---- B9: `got = c ? m : 0` when &got is passed on the other path ------- */

/* gd_xfer (src/sys/gemdos.c): one loop moves bytes either way, a write
 * setting the count moved from the status (`got = ok ? m : 0`) and a read
 * having the callee fill it (`cio_read(..., &got)`).  The conditional
 * assignment on the write path is evaluated into a scratch slot and
 * thrown away, and `got` is then loaded from an unrelated slot -- the
 * bytes-moved total is garbage.  -O2.  The sources test the status and
 * break, then assign `got = m` plainly. */
uint8_t b9_st;
uint8_t b9_write(uint8_t *p, uint16_t m) { (void)p; (void)m; return b9_st; }
uint8_t b9_read(uint8_t *p, uint16_t m, uint16_t *got) { (void)p; *got = m / 2; return 1; }

int32_t b9_bug(int32_t count, WORD write)
{
    uint8_t buf[8], st;
    int32_t done = 0;
    uint16_t m, got;

    while (count > 0) {
        m = count > 8L ? 8 : (uint16_t)count;
        if (write) {
            st = b9_write(buf, m);
            got = (st == 1 || st == 3) ? m : 0;
        } else {
            st = b9_read(buf, m, &got);
        }
        done += got;
        count -= got;
        if (got < m || (st != 1 && st != 3))
            break;
    }
    return done;
}

int32_t b9_fix(int32_t count, WORD write)
{
    uint8_t buf[8];
    WORD st;
    int32_t done = 0;
    uint16_t m, got;

    while (count > 0) {
        m = count > 8L ? 8 : (uint16_t)count;
        if (write) {
            st = b9_write(buf, m);
            if (st != 1 && st != 3)
                break;
            got = m;
        } else {
            st = b9_read(buf, m, &got);
        }
        done += got;
        count -= got;
        if (got < m || (st != 1 && st != 3))
            break;
    }
    return done;
}


/* ---- B10: both parameters clamped in place, then read from nowhere ----- */

/* snap_icon (src/desk/desktop.c): a static function that clamps its two
 * WORD parameters (`if (gx > cols - 1) gx = cols - 1;`) and then multiplies
 * them, inlined into its caller at -O2.  The clamps store to the right
 * slots -- and the products that follow load BOTH parameters from a slot
 * the function never wrote, so the answer is whatever the stack held.
 * The first desk icon landed right because that slot was zero; the second
 * came out at (31744, 3595).  The sources clamp into fresh locals. */
typedef struct { WORD g_x, g_y, g_w, g_h; } B10RECT;
struct { B10RECT desk; WORD icw, ich; } b10 = { { 0, 11, 640, 229 }, 106, 45 };

static void b10_bug_snap(WORD gx, WORD gy, WORD *px, WORD *py)
{
    WORD columns = b10.desk.g_w / b10.icw;
    WORD rows = b10.desk.g_h / b10.ich;
    WORD spare;

    if (gx > columns - 1)
        gx = (WORD)(columns - 1);
    if (gy > rows - 1)
        gy = (WORD)(rows - 1);
    spare = (WORD)(b10.desk.g_w - columns * b10.icw);
    *px = (WORD)(gx * b10.icw + spare / columns);
    spare = (WORD)(b10.desk.g_h - rows * b10.ich);
    *py = (WORD)(gy * b10.ich + spare / rows + b10.desk.g_y);
}

static void b10_fix_snap(WORD gx, WORD gy, WORD *px, WORD *py)
{
    WORD columns = b10.desk.g_w / b10.icw;
    WORD rows = b10.desk.g_h / b10.ich;
    WORD spare;
    WORD cx = gx > columns - 1 ? (WORD)(columns - 1) : gx;
    WORD cy = gy > rows - 1 ? (WORD)(rows - 1) : gy;

    spare = (WORD)(b10.desk.g_w - columns * b10.icw);
    *px = (WORD)(cx * b10.icw + spare / columns);
    spare = (WORD)(b10.desk.g_h - rows * b10.ich);
    *py = (WORD)(cy * b10.ich + spare / rows + b10.desk.g_y);
}

/* The stack under the caller's frame holds something other than zero,
 * as it does after any earlier call. */
void b10_dirty(void)
{
    volatile WORD junk[16];
    WORD i;
    for (i = 0; i < 16; i++)
        junk[i] = (WORD)(0x5555 + i);
}

WORD b10_bug(WORD gx, WORD gy)
{
    WORD x, y;
    b10_bug_snap(gx, gy, &x, &y);
    return (WORD)(x + y);
}

WORD b10_fix(WORD gx, WORD gy)
{
    WORD x, y;
    b10_fix_snap(gx, gy, &x, &y);
    return (WORD)(x + y);
}

/* ---- results ------------------------------------------------------------ */

volatile WORD r_b1_bug, r_b1_fix;                       /* want 476 */
volatile WORD r_b2_eq, r_b2_lt, r_b2_mod;               /* want 7, 0, 0 */
volatile WORD r_b3_bug, r_b3_fix;                       /* want 7 */
volatile WORD r_b4_bug, r_b4_fix;                       /* want -2 */
volatile WORD r_b5_bug, r_b5_fix;                       /* want 120 */
volatile WORD r_b5_dec_bug, r_b5_dec_fix;               /* want 4 */
volatile WORD r_b7_bug, r_b7_fix;                       /* want 801 */
volatile WORD r_b8_bug, r_b8_fix;                       /* want 'T' = 84 */
volatile WORD r_b9_bug, r_b9_fix;                       /* want 20 */
volatile WORD r_b10_bug, r_b10_fix;                     /* want 207 */
volatile WORD r_b12_bug, r_b12_fix;                     /* want 112 */
volatile WORD r_b12_neg;                                /* want -113 */
volatile WORD r_b13_bug, r_b13_fix;                     /* want 48 */
volatile WORD r_b14_bug, r_b14_fix;                     /* want 192 */
volatile WORD r_b15_bug, r_b15_fix;                     /* want 164 */
volatile WORD r_b16_fix;                                /* want 119 */
volatile WORD r_b23_bug, r_b23_fix;                     /* want 0x1F5F */

/* ---- B12: a signed 16-bit >> is not an arithmetic shift --------------- */

/* Isin (src/vdi/vdi.c): the VDI's sine table is indexed by the angle over
 * eight.  `angle >> 3` compiles to three logical shifts and then a sign
 * extension from the WRONG bit -- `eor ##4 / and ##7 / sec / sbc ##4`,
 * which keeps three bits and throws the rest away.  900 >> 3 is 0, not
 * 112; 900 >> 4 is -8, not 56; -900 >> 3 is -1, not -113.  A shift by ONE
 * emits a plain `lsr` and so is right only for a non-negative value, and
 * 32-bit shifts are right.  The compiler does emit the correct `cmp
 * ##-32768 / ror a` in some contexts, so this cannot be tested by reading
 * one listing -- which is why it is here.
 *
 * Every curve gem4xe drew came out as a point at the centre of itself.
 * The sources shift an UNSIGNED copy and do the sign by hand (asr()). */
volatile WORD b12_in = 900;

static WORD b12_bug(WORD a) { return (WORD)(a >> 3); }
static WORD b12_fix(WORD a) { return (WORD)((uint16_t)a >> 3); }

static WORD b12_asr(WORD v, WORD n)     /* what src/vdi/vdi.c uses */
{
    if (v >= 0)
        return (WORD)((uint16_t)v >> n);
    return (WORD)(-(WORD)(((uint16_t)(-v) + (uint16_t)((1u << n) - 1u)) >> n));
}

/* ---- B13/B14: an arrowhead's two ends -------------------------------- */

/* draw_arrow (src/vdi/vdi.c) computes the vector from an arrowhead's tip
 * to the first point far enough back to carry it.  Two things go wrong,
 * and neither reproduces in a small function -- lifted out on their own
 * both shapes compile correctly, which is why the whole calculation is
 * here.  Every arrowhead the VDI drew was wrong.
 *
 *   B13   dx = pt[0] - pt[i * inc * 2];       the SECOND element reads as
 *                                             zero (B1's shape, through a
 *                                             pointer parameter)
 *   B14   draw_arrow(&pt[(n-1)*2], n, -1)     the negative index inside --
 *                                             pt[-2] -- reads neither
 *                                             point
 *
 * The sources take the far element into a scalar and address every point
 * as a non-negative index from the array's base. */
WORD b13_pts[6] = { 40, 90, 200, 90, 0, 0 };
WORD b14_pts[6] = { 40, 90, 200, 90, 0, 0 };
volatile WORD b13_count = 2;

static uint16_t b13_isqrt(uint32_t v)
{
    uint32_t rem = 0, root = 0;
    WORD i;

    for (i = 0; i < 16; i++) {
        root <<= 1;
        rem = (rem << 2) | (v >> 30);
        v <<= 2;
        if (rem > root) { rem -= root + 1; root += 2; }
    }
    return (uint16_t)(root >> 1);
}

static WORD b13_mdr(WORD m1, WORD m2, WORD d)
{
    int32_t v = (int32_t)m1 * m2;

    v = (v < 0) ? (v - d / 2) : (v + d / 2);
    return (WORD)(v / d);
}

/* returns the x of the head's first corner: 48 for this line */
static WORD b13_arrow_bug(WORD *pt, WORD count, WORD inc)
{
    WORD len = 8, wid = 4, dx = 0, dy = 0, i, nskip = 0;
    WORD line_len, dxf, dyf, htx, hty, bx;
    uint32_t len2 = 0;

    for (i = 1; i < count; i++) {
        nskip = i;
        dx = (WORD)(pt[0] - pt[i * inc * 2]);
        dy = (WORD)(pt[1] - pt[i * inc * 2 + 1]);
        len2 = (uint32_t)((int32_t)dx * dx + (int32_t)dy * dy);
        if (len2 >= (uint32_t)(len * len))
            break;
    }
    (void)nskip;
    line_len = (WORD)b13_isqrt(len2);
    if (line_len < len)
        return -1;
    dxf = b13_mdr(dx, 1000, line_len);
    dyf = b13_mdr(dy, 1000, line_len);
    htx = b13_mdr(len, dxf, 1000);
    hty = b13_mdr(len, dyf, 1000);
    bx  = b13_mdr(wid, (WORD)-dyf, 1000);
    (void)hty;
    return (WORD)(pt[0] + bx - htx);
}

static WORD b13_arrow_fix(WORD *pt, WORD count, WORD tip, WORD inc)
{
    WORD len = 8, wid = 4, dx = 0, dy = 0, i, nskip = 0;
    WORD line_len, dxf, dyf, htx, hty, bx;
    WORD tx = pt[tip], ty = pt[tip + 1];
    uint32_t len2 = 0;

    for (i = 1; i < count; i++) {
        WORD j = (WORD)(tip + i * inc * 2), qx = pt[j], qy = pt[j + 1];

        nskip = i;
        dx = (WORD)(tx - qx);
        dy = (WORD)(ty - qy);
        len2 = (uint32_t)((int32_t)dx * dx + (int32_t)dy * dy);
        if (len2 >= (uint32_t)(len * len))
            break;
    }
    (void)nskip;
    line_len = (WORD)b13_isqrt(len2);
    if (line_len < len)
        return -1;
    dxf = b13_mdr(dx, 1000, line_len);
    dyf = b13_mdr(dy, 1000, line_len);
    htx = b13_mdr(len, dxf, 1000);
    hty = b13_mdr(len, dyf, 1000);
    bx  = b13_mdr(wid, (WORD)-dyf, 1000);
    (void)hty;
    return (WORD)(tx + bx - htx);
}

/* ---- B15: p->a = p->b OP e is compiled as p->a OP= e ------------------ */

/* `st->end = st->start + 64` where st is a near pointer that lives on the
 * stack (a call preceded it) compiles to `ldy ##end; lda ##64; clc; adc
 * (slot,s),y; sta (slot,s),y`: the load is done at the DESTINATION's
 * offset, so the statement is st->end += 64 and st->start is never read.
 * The trigger is exact: the right-hand side, after casts and parentheses,
 * is ONE binary operation whose LEFT operand is another member (or
 * element) of the same pointer.  `+ - & | ^ <<` and a signed `>>` do it,
 * `+ 1`/`- 1` become `inc/dec n,x` and `* 2` an `asl n,x` on the
 * destination; any element width; variable indices on either side (`p[n]
 * = p[1] + 64` and `p[2] = p[n] + 64` both ignore n); a (WORD) cast
 * around the right-hand side changes nothing, and two such statements in
 * a row are both wrong.  Not triggered: the member on the RIGHT of the
 * operator (`k - p->y`), more than one operator at the top level (`p->y
 * * 2 + k`), a call or _Div16 between the load and the store, a global
 * pointer, a far pointer, or the pointer still in X.  All -O levels.
 *
 * B1 (a stack array), B5 (a dead pointer's slot) and B13 (a pointer
 * parameter) are faces of the same defect.  This one was met in the
 * vendor C library: __fs_fdopen's `stream->fs_bufend =
 * &stream->fs_bufstart[BUFSIZ]` leaves fs_bufend as garbage + 64, and any
 * fwrite or fread longer than 64 bytes then runs off the end of the
 * buffer (Calypsi-65816-Atari, docs/cc65816-bug.md, links its own fdopen
 * before the library to get round it).  The sources never write
 * `P->a = P->b OP e` through a pointer: the member goes through a scalar. */
typedef struct { WORD fd; WORD start; WORD end; } B15_STREAM;
B15_STREAM b15_stream;
WORD b15_pool[8];
volatile WORD b15_base = 100;

/* A stand-in for malloc: the first free slot's address.  A one-line
 * callee is inlined and the pointer never leaves X, so this one loops. */
WORD b15_alloc(WORD n)
{
    WORD i;
    for (i = 0; i < 8; i++)
        if (b15_pool[i] == 0) {
            b15_pool[i] = (WORD)(n + 1);
            return (WORD)(b15_base + i);
        }
    return 0;
}

WORD b15_bug(B15_STREAM *st)
{
    st->start = b15_alloc(0);                   /* spills st to the stack */
    st->end = (WORD)(st->start + 64);
    return st->end;
}

/* The member through a scalar first. */
WORD b15_fix(B15_STREAM *st)
{
    WORD start;
    st->start = b15_alloc(0);
    start = st->start;
    st->end = (WORD)(start + 64);
    return st->end;
}

/* ---- B16: a byte spin loop's width switch lands before its back edge -- */

/* `while (vc < 19) ;` on a volatile byte, with an early return before it
 * and 16-bit code after it, compiles at -O2 to `?L: lda vc; cmp #19;
 * rep #32; bcc ?L`: the second pass loads a word and the compare eats
 * the rep's opcode, so execution runs into the branch's operand.  That
 * shape cannot be run; it is b16.c, compiled alone and its listing read.
 * The sources read the byte into a word through a helper and compare
 * the word (src/sys/bootinfo.c's vcount()), which is what runs here.
 * Nothing in the simulator has a beam, so this helper moves it on a
 * line per read; the caller's code is the same either way. */
volatile uint8_t b16_vc;                    /* VCOUNT */

static WORD b16_vcount(void)
{
    b16_vc++;
    return b16_vc;
}

WORD b16_fix(WORD p)
{
    if (p)
        return 0;
    while (b16_vcount() >= 19) ;            /* the frame's wrap */
    while (b16_vcount() < 19) ;             /* the top of the logo */
    return (WORD)(b16_vc + 100);
}

/* ---- B23: a second bit test of a byte reads a stray stack byte ------- */

/* kb_translate (src/vdi/vdi.c): the row of the OS's key table from the
 * shift (bit 6) and control (bit 7) bits of POKEY's code.  At -O2 the
 * byte is stored at 1,s and loaded as a WORD from 0,s -- the code in the
 * HIGH byte, whatever lies below the stack in the low one -- so `bpl`
 * tests bit 7 rightly and the `bit ##64` for the else-if tests the stray
 * byte.  On the desktop every key came out as its shifted character.
 * Two separate ifs happened to be right; the row taken as a number is. */
WORD b23_bug(uint8_t code)
{
    WORD idx = (WORD)(code & 0x3F);

    if (code & 0x80)
        idx += 128;
    else if (code & 0x40)
        idx += 64;
    return idx;
}

WORD b23_fix(uint8_t code)
{
    WORD idx = (WORD)(code & 0x3F), row = (WORD)(code >> 6);

    if (row == 3)
        row = 2;
    return (WORD)(idx + (row << 6));
}

/* Both codes, packed: a plain $1F and a shifted $5F must come back as
 * themselves, whatever the stray byte holds -- one of the two is wrong
 * whichever way its bit 6 lies. */
static WORD b23_pair(WORD (*f)(uint8_t))
{
    return (WORD)((f(0x1F) << 8) | f(0x5F));
}

__task int main(void)
{
    WORD w = 200, h;

    tree[2].ob_x = 376;
    r_b1_bug = b1_bug(tree, 2, 1, 100);
    r_b1_fix = b1_fix(tree, 2, 1, 100);

    h = 8;  r_b2_eq  = b2_div_truth("centred", &h);     /* 8 / 8 = 1: 7 */
    h = 7;  r_b2_lt  = b2_div_truth("centred", &h);     /* 7 / 8 = 0: 0 */
    h = 16; r_b2_mod = b2_mod_truth("centred", &h);     /* 16 % 8 = 0: 0 */

    r_b3_bug = b3_bug("centred", &w, &h);
    r_b3_fix = b3_fix("centred", &w, &h);

    r_b4_bug = b4_bug(b4_spec);
    r_b4_fix = b4_fix(b4_spec);

    for (h = 0; h < 32; h++) b5_form[h] = (uint8_t)(h * 3);
    b5_mfdb.fd_addr = (uint16_t)b5_form;
    b5_mfdb.fd_wdwidth = 2;                     /* 4 bytes per row */
    b5_contrl[7] = (WORD)(uint16_t)&b5_mfdb;
    b5_ptsin[1] = 1; b5_ptsin[3] = 4;
    r_b5_bug = b5_bug();                        /* rows 1..4: 12+24+36+48 */
    r_b5_fix = b5_fix();
    b5_ted.te_ptext = (uint16_t)b5_text1;
    b5_ted.te_txtlen = 5;                       /* four characters and the NUL */
    r_b5_dec_bug = b5_dec_bug(1, "SAMPLE");    /* 4 copied */
    b5_ted.te_ptext = (uint16_t)b5_text2;
    r_b5_dec_fix = b5_dec_fix(1, "SAMPLE");

    b7_arr[1].a = 0x1111; b7_arr[1].b = 0x22; b7_arr[1].c = 801;
    b7_arr[2].a = 0x4444; b7_arr[2].b = 0x55; b7_arr[2].c = 0x6666;
    r_b7_bug = b7_bug();                        /* element 1's c, by stride */
    r_b7_fix = b7_fix();

    for (h = 0; h < 8; h++) b8_out1[h] = b8_out2[h] = (char)0xEE;
    b8_bug("test", b8_out1);                    /* out[0] must be 'T' */
    b8_fix("test", b8_out2);
    r_b8_bug = (uint8_t)b8_out1[0];
    r_b8_fix = (uint8_t)b8_out2[0];

    b9_st = 1;
    r_b9_bug = (WORD)b9_bug(20, 1);             /* 8 + 8 + 4 written */
    r_b9_fix = (WORD)b9_fix(20, 1);

    b10_dirty();
    r_b10_bug = b10_bug(1, 2);                  /* (106, 101): 207 */
    b10_dirty();
    r_b10_fix = b10_fix(1, 2);

    r_b12_bug = b12_bug(b12_in);                /* 900 >> 3 = 112 */
    r_b12_fix = b12_fix(b12_in);
    r_b12_neg = b12_asr((WORD)-(b12_in), 3);    /* -900 >> 3 = -113 */

    /* the head at the START of the line: its first corner is x = 48 */
    r_b13_bug = b13_arrow_bug(b13_pts, b13_count, 1);
    r_b13_fix = b13_arrow_fix(b13_pts, b13_count, 0, 1);
    /* and the head at its END, reached by a negative index: x = 192 */
    r_b14_bug = b13_arrow_bug(&b14_pts[2], b13_count, -1);
    r_b14_fix = b13_arrow_fix(b14_pts, b13_count, 2, -1);

    /* start is 100, so end should be 164; the bug adds 64 to end's old 0 */
    b15_stream.end = 0;
    r_b15_bug = b15_bug(&b15_stream);
    b15_pool[0] = 0;
    b15_stream.end = 0;
    r_b15_fix = b15_fix(&b15_stream);

    /* the polls stop at line 19, so 119 */
    b16_vc = 0;
    r_b16_fix = b16_fix(0);

    r_b23_bug = b23_pair(b23_bug);              /* $1F and $5F: 0x1F5F */
    r_b23_fix = b23_pair(b23_fix);
    return 0;
}
