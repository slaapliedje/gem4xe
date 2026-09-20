/* rsrc.c -- the resource library: rsrc_load, rsrc_free, rsrc_gaddr,
 * rsrc_saddr, rsrc_obfix.  EmuTOS aes/gemrslib.c, less the colour icons.
 *
 * A .RSC is a dump of OBJECT, TEDINFO, ICONBLK and BITBLK arrays with
 * every pointer an offset from the start of the file and every word in
 * the 68000's byte order.  gem4xe's structures are the same bytes in the
 * 65816's order, so loading is: read the file whole into the bank-$00
 * pool, swap the words of the header and of every table the header
 * counts, then add the pool address to every offset -- the donor's
 * fix_long, with the base a 16-bit address in bank $00 rather than a
 * 68000 pointer.  Strings and image data are bytes and are left alone:
 * a 1-plane image is MSB-first in both worlds, and the VDI's vrt_cpyfm
 * reads it that way.
 *
 * The objects' rectangles are stored as (pixel offset << 8 | character
 * position) and made pixels from the workstation's character cell
 * (fix_chpos); a width of 80 characters means the whole screen.  The
 * donor does that fixup separately (rs_fixit) because its own resource
 * is read before the workstation is open; here the workstation always
 * is, so one call does everything.
 *
 * The pool is why there is one resource at a time: rsrc_load takes from
 * the bump allocator and rsrc_free winds it back, which is only right
 * while nothing else was taken above it -- the file selector's tree,
 * which is taken and released inside one call, is the only other user.
 * The selector's tree is a .RSC too, built into the far image
 * (tools/fselrsc.py), so the fixup takes the header it works on as a
 * parameter, rs_fixit(), rather than the one resource the library holds.
 */
#include <string.h>
#include "portab.h"
#include "aes/aes.h"
#include "aes/proc.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/farmem.h"

/* The running process's resource and the pool mark before it: see
 * src/aes/proc.h for why these belong to a process and not to this file.
 * rs_cur is the one a call acts on; rs_loaded() hands its base out. */
#define rs_1        (rlr->p_rsc)        /* the resident resource's BASE, 0 if none */
#define rs_1mark    (rlr->p_rscmark)    /* the pool before its load */
#define rs_1far     (rlr->p_rscfar)     /* the far heap before its load, when it went far; 0 in the pool */
#define rs_2        (rlr->p_rsc2)
#define rs_2mark    (rlr->p_rscmark2)
#define rs_2far     (rlr->p_rscfar2)
/* The resource a call ACTS ON: the nested one while it is up, so that a
 * dialog loaded over a resident resource answers rsrc_gaddr and is what
 * rsrc_free takes away.  Read-only -- the two slots are assigned by
 * name.
 *
 * A BASE IS A 32-BIT ADDRESS, AND A RESOURCE IN THE POOL IS ONE WHOSE
 * BANK IS ZERO (docs/far-trees.md).  Everything below reaches the file's
 * bytes through far_get/far_put at base + offset, whether the base is in
 * bank $00 or above it, so there is one fixup and one rsrc_gaddr rather
 * than a near one and a far one.  The header is copied out into a local
 * RSHDR where a function needs its counts. */
#define rs_cur      (rs_2 ? rs_2 : rs_1)
#define rs_mark     (rlr->p_rscmark)

static void hdr_get(uint32_t base, RSHDR *h)
{
    far_get((uint8_t *)h, base, sizeof *h);
}

static void hdr_put(uint32_t base, const RSHDR *h)
{
    far_put(base, (const uint8_t *)h, sizeof *h);
}

static uint32_t rd_long(uint32_t far);  /* a 68000 LONG from far memory: defined with the colour icons below */

static void swap_words(void *p, uint16_t n)
{
    uint8_t *b = p;
    while (n--) {
        uint8_t t = b[0];
        b[0] = b[1];
        b[1] = t;
        b += 2;
    }
}

/* A word of the file made a pixel: HIBYTE the pixel offset (signed),
 * LOBYTE the position in characters. */
static void fix_chpos(WORD *pfix, WORD which)
{
    WORD coffset = (WORD)((UWORD)*pfix >> 8);
    WORD cpos = (WORD)(*pfix & 0xFF);

    switch (which) {
    case 0:
        cpos = (WORD)(cpos * gl_wchar);
        break;
    case 1:
        cpos = (WORD)(cpos * gl_hchar);
        break;
    case 2:
        cpos = (WORD)(cpos == 80 ? gl_width : cpos * gl_wchar);
        break;
    default:
        cpos = (WORD)(cpos * gl_hchar);
        break;
    }
    cpos = (WORD)(cpos + (coffset > 128 ? coffset - 256 : coffset));
    *pfix = cpos;
}

void rs_obfix(OBJECT FAR *tree, WORD obj)
{
    WORD *p = &tree[obj].ob_x;
    WORD k;
    for (k = 0; k < 4; k++)
        fix_chpos(p + k, k);
}

/* An offset from the start of the file made an address; -1 stays -1. */
static WORD fix_long(uint32_t base, uint32_t *p)
{
    if (*p == 0xFFFFFFFFUL)
        return 0;
    *p += base;
    return 1;
}

/* The sizes these records have IN THE FILE, written out rather than taken
 * from sizeof -- and the story behind that is worth the space, because it
 * cost an evening and very nearly cost a wrong "fix".
 *
 * sizeof IS RIGHT HERE.  An ICONBLK is 34 bytes in this compiler's
 * generated code, as the file gives it: a function returning
 * sizeof(ICONBLK) compiles to `lda ##34`, &arr[i] scales by 34, and
 * rs_cicons below steps the colour extension correctly.  MControl's own
 * resource -- 22 colour icons, a real ST file -- loads on the machine
 * with every record's geometry and both far addresses matching the file,
 * at a record stride of 50, which is 34 + 12 + 4 and could not be
 * 36 + 12 + 4.
 *
 * WHAT IS WRONG IS THE WAY THE STRUCT WAS MEASURED.  The negative-array
 * idiom -- char p[(sizeof(X)==N)?1:-1] -- answers 36 for this struct,
 * because the compiler's CONSTANT-EXPRESSION evaluator rounds a size up
 * to the alignment while its code generator does not (tools/ccbug, B7 -- whose rule,
 * written down since long before this, is the one this file broke).
 * On that answer the strides below were read as a live bug, a peer was
 * told the fix mattered to their port, and the gates passed either way
 * for the simple reason that the code was correct to begin with.
 *
 * So these four names buy no behaviour at all.  They buy the one
 * thing the
 * episode showed is worth having: a stride that does not depend on a
 * sizeof this compiler reports two different values for, with
 * tools/rsc.py naming the same numbers and tests/host/test_rsrc.py
 * holding the two lists against each other, against the ST's format, and
 * against the tables of the resources this tree builds.  rs_cicons below
 * is deliberately left on sizeof, because it is right and because the
 * two sides of its near record have to agree with each other. */
#define RSZ_OBJECT   24
#define RSZ_TEDINFO  28
#define RSZ_ICONBLK  34
#define RSZ_BITBLK   14

static uint32_t sub_at(uint32_t base, UWORD index, UWORD offset, UWORD size)
{
    return base + offset + (uint32_t)size * index;
}

/* A fixed-up LONG -- native order, as rs_fixit leaves it -- at a far
 * address, and the same written back. */
static uint32_t rd_native(uint32_t at)
{
    uint8_t b[4];
    far_get(b, at, 4);
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8)
         | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}

static void wr_native(uint32_t at, uint32_t v)
{
    uint8_t b[4];
    b[0] = (uint8_t)v;  b[1] = (uint8_t)(v >> 8);
    b[2] = (uint8_t)(v >> 16);  b[3] = (uint8_t)(v >> 24);
    far_put(at, b, 4);
}

/* The donor's get_addr, as a 32-bit address: 0xFFFFFFFF for a type it
 * does not know.  `h` is a native-order copy of the header at `base`. */
static uint32_t addr_at(const RSHDR *h, uint32_t base, UWORD rtype, UWORD rindex)
{
    UWORD offset, size;

    switch (rtype) {
    case R_TREE:
        return rd_native(sub_at(base, rindex, h->rsh_trindex, 4));
    case R_OBJECT:
        offset = h->rsh_object;  size = RSZ_OBJECT;  break;
    case R_TEDINFO:
    case R_TEPTEXT:
        offset = h->rsh_tedinfo; size = RSZ_TEDINFO; break;
    case R_ICONBLK:
    case R_IBPMASK:
        offset = h->rsh_iconblk; size = RSZ_ICONBLK; break;
    case R_BITBLK:
    case R_BIPDATA:
        offset = h->rsh_bitblk;  size = RSZ_BITBLK;  break;
    case R_OBSPEC:                      /* the field offsets are the file's */
        return addr_at(h, base, R_OBJECT, rindex) + 12;
    case R_TEPTMPLT:
        return addr_at(h, base, R_TEDINFO, rindex) + 4;
    case R_TEPVALID:
        return addr_at(h, base, R_TEDINFO, rindex) + 8;
    case R_IBPDATA:
        return addr_at(h, base, R_ICONBLK, rindex) + 4;
    case R_IBPTEXT:
        return addr_at(h, base, R_ICONBLK, rindex) + 8;
    case R_STRING:
        return rd_native(sub_at(base, rindex, h->rsh_frstr, 4));
    case R_IMAGEDATA:
        return rd_native(sub_at(base, rindex, h->rsh_frimg, 4));
    case R_FRSTR:
        offset = h->rsh_frstr;   size = 4; break;
    case R_FRIMG:
        offset = h->rsh_frimg;   size = 4; break;
    default:
        return 0xFFFFFFFFUL;
    }
    return sub_at(base, rindex, offset, size);
}

/* The same as a near pointer, for the two paths that only ever run on a
 * resource IN THE POOL (rs_imfar, rs_cicons): `base` is the pool address
 * the header was read from. */
static void *addr_of(const RSHDR *h, uint32_t base, UWORD rtype, UWORD rindex)
{
    return (void *)(uint16_t)addr_at(h, base, rtype, rindex);
}

static void swap_long(uint16_t *p)      /* a 68000 LONG: its two words swapped too */
{
    uint16_t t = p[0]; p[0] = p[1]; p[1] = t;
}

static uint16_t far_slen(uint32_t a)    /* strlen through a far address */
{
    uint16_t n = 0;
    while (far_read8(a + n))            /* not `*s++` narrowed in one expression: B18 */
        n++;
    return n;
}

/* Everything the donor does in rs_readit and rs_fixit: `h` is the file's
 * bytes, whole and as the file has them, at the address they will be
 * used from.  The header's words are swapped first, then every table it
 * counts. */
void rs_fixit(uint32_t base)
{
    RSHDR h;
    WORD i;
    union {                             /* the largest record, as bytes */
        OBJECT  o;
        TEDINFO t;
        ICONBLK ib;
        BITBLK  bb;
        uint8_t raw[RSZ_ICONBLK];
    } r;

    hdr_get(base, &h);
    swap_words(&h, sizeof h / 2);
    hdr_put(base, &h);

    /* the three tables of longs: each a 68000 LONG, made native, then an
     * offset made an address (the donor's fix_trindex and fix_nptrs) */
    for (i = 0; i < h.rsh_ntree; i++) {
        uint32_t at = sub_at(base, i, h.rsh_trindex, 4), v = rd_long(at);
        fix_long(base, &v);
        wr_native(at, v);
    }
    for (i = 0; i < h.rsh_nstring; i++) {
        uint32_t at = sub_at(base, i, h.rsh_frstr, 4), v = rd_long(at);
        fix_long(base, &v);
        wr_native(at, v);
    }
    for (i = 0; i < h.rsh_nimages; i++) {
        uint32_t at = sub_at(base, i, h.rsh_frimg, 4), v = rd_long(at);
        fix_long(base, &v);
        wr_native(at, v);
    }
    /* fix_objects */
    for (i = 0; i < h.rsh_nobs; i++) {
        uint32_t at = sub_at(base, i, h.rsh_object, RSZ_OBJECT);
        far_get(r.raw, at, RSZ_OBJECT);
        swap_words(r.raw, RSZ_OBJECT / 2);
        swap_long((uint16_t *)&r.o.ob_spec);
        rs_obfix(&r.o, 0);              /* the near copy: a bank-zero tree */
        switch (r.o.ob_type & 0xFF) {
        case G_BOX:
        case G_IBOX:
        case G_BOXCHAR:
            break;
        case G_CICON:
            /* an INDEX into the colour-icon table, not an offset: it is
             * made an address by rs_cicons once the table is placed */
            break;
        default:
            fix_long(base, &r.o.ob_spec);
            break;
        }
        far_put(at, r.raw, RSZ_OBJECT);
    }
    /* fix_tedinfo_std */
    for (i = 0; i < h.rsh_nted; i++) {
        uint32_t at = sub_at(base, i, h.rsh_tedinfo, RSZ_TEDINFO);
        far_get(r.raw, at, RSZ_TEDINFO);
        swap_words(r.raw, RSZ_TEDINFO / 2);
        swap_long((uint16_t *)&r.t.te_ptext);
        swap_long((uint16_t *)&r.t.te_ptmplt);
        swap_long((uint16_t *)&r.t.te_pvalid);
        if (fix_long(base, &r.t.te_ptext))
            r.t.te_txtlen = (WORD)(far_slen(r.t.te_ptext) + 1);
        if (fix_long(base, &r.t.te_ptmplt))
            r.t.te_tmplen = (WORD)(far_slen(r.t.te_ptmplt) + 1);
        fix_long(base, &r.t.te_pvalid);
        far_put(at, r.raw, RSZ_TEDINFO);
    }
    for (i = 0; i < h.rsh_nib; i++) {
        uint32_t at = sub_at(base, i, h.rsh_iconblk, RSZ_ICONBLK);
        far_get(r.raw, at, RSZ_ICONBLK);
        swap_words(r.raw, RSZ_ICONBLK / 2);
        swap_long((uint16_t *)&r.ib.ib_pmask);
        swap_long((uint16_t *)&r.ib.ib_pdata);
        swap_long((uint16_t *)&r.ib.ib_ptext);
        fix_long(base, &r.ib.ib_pmask);
        fix_long(base, &r.ib.ib_pdata);
        fix_long(base, &r.ib.ib_ptext);
        far_put(at, r.raw, RSZ_ICONBLK);
    }
    for (i = 0; i < h.rsh_nbb; i++) {
        uint32_t at = sub_at(base, i, h.rsh_bitblk, RSZ_BITBLK);
        far_get(r.raw, at, RSZ_BITBLK);
        swap_words(r.raw, RSZ_BITBLK / 2);
        swap_long((uint16_t *)&r.bb.bi_pdata);
        fix_long(base, &r.bb.bi_pdata);
        far_put(at, r.raw, RSZ_BITBLK);
    }
}

/* THE IMAGE BITS GO TO FAR MEMORY, and the pool gets them back.
 *
 * A resource is loaded into the application pool -- 14 KB of bank $00 for
 * the desktop, its resource and everything resident beside it -- and
 * DESKTOP.RSC is 6,226 bytes of that.  A quarter of it is icon bitmaps,
 * which are the one part nothing in bank $00 has to reach: an ICONBLK
 * names its mask and its image in 32-bit fields, and gsx_blt has taken a
 * 32-bit address since phase 2, because that is what an MFDB holds.  So
 * the bits are copied up and the pool is wound back over them: 1,536
 * bytes, which is what a second desk accessory costs.
 *
 * tools/rsc.py puts the image block LAST in the file for this, so the
 * release is a wind-back of the tail and not a compaction of the middle
 * -- which would invalidate every offset rs_fixit has just fixed.
 *
 * IT ONLY MOVES WHAT IS PROVABLY REACHED THROUGH A 32-BIT FIELD.  A
 * resource with BITBLKs or free images keeps its bits in the pool, and
 * the reason is rs_gaddr: it answers an application with a NEAR address,
 * so a free image's bytes must be somewhere sixteen bits can name.  An
 * ICONBLK's cannot be asked for that way -- the application is given the
 * ICONBLK and reads the wide field itself.
 *
 * THE FAR BYTES COME BACK AT rs_free WHEN THEY ARE THE TOP OF THE HEAP.
 * The far heap is a bump allocator (src/sys/farmem.h), so a block can be
 * given back only while nothing has been taken above it -- which is the
 * common case, a resource loaded, used and freed with no Malloc between.
 * Then rs_free winds the heap back to where it stood before the load
 * (the mark BEFORE far_alloc, since far_alloc may have skipped to a bank
 * boundary), and a dialog resource loaded and freed per use costs
 * nothing that lasts.  When something IS above it the block stays, and
 * app_free reclaims it with the rest of the program's far memory: with
 * 14 MB that is a note rather than a leak.  The reclaim records are PER
 * SLOT -- a nested resource freed first must not take the outer one's
 * with it -- while rs_imbase/rs_cibase answer for the last load placed. */
typedef struct {
    uint32_t base, mark, top;   /* the block; the heap before and after it */
} FARBLK;
static uint32_t rs_imbase;      /* where they went, 0 if they stayed */
static uint16_t rs_imsize;
static FARBLK   rs_im[2];       /* by slot: [0] the resident, [1] the nested */

void rs_imaddr(uint32_t *base, uint16_t *len)
{
    *base = rs_imbase;
    *len = rs_imsize;
}

static void rs_imfar(uint8_t *mem, uint16_t im_off, uint16_t size)
{
    uint16_t im_len = (uint16_t)(size - im_off);
    uint16_t im_near;
    uint32_t base, mark;
    WORD i;

    RSHDR h;

    hdr_get(rs_cur, &h);                /* the pool copy, fixed up: bank $00 */
    if (!im_len || h.rsh_nbb || h.rsh_nimages)
        return;                         /* see the note: not provably safe --
                                         * and nothing moved, so a resource
                                         * NESTED over another leaves the
                                         * outer's record of its own alone */
    /* ...AND ONLY WHEN THE IMAGE BLOCK IS THE TAIL OF THE FILE.  The pool
     * is wound back over it, so anything the header places at or above
     * rsh_imdata would go with it.  tools/rsc.py and the desktop's
     * resource put the bits last; a resource written by another tool
     * need not -- HypView's has no images at all and 2,632 bytes of its
     * tables above the offset, and moving those "images" put its objects
     * in far memory and the colour-icon records on top of them.  A file
     * laid out that way keeps its bits in the pool. */
    {
        /* the header as eighteen words: (offset word, count word, size)
         * for each table, and the strings' offset with no count */
        static const uint8_t lay[8][3] = {
            {1, 10, RSZ_OBJECT}, {2, 12, RSZ_TEDINFO},
            {3, 13, RSZ_ICONBLK}, {4, 14, RSZ_BITBLK},
            {5, 15, 4}, {8, 16, 4}, {9, 11, 4}, {6, 10, 0}
        };
        const UWORD *hw = (const UWORD *)&h;
        for (i = 0; i < 8; i++)
            if ((uint16_t)(hw[lay[i][0]] + hw[lay[i][1]] * lay[i][2]) > im_off)
                return;
    }
    rs_imbase = 0;
    rs_imsize = 0;
    mark = farmem.brk;
    base = far_alloc(im_len);
    if (!base)
        return;                         /* no far memory: leave them be */
    {
        FARBLK *f = &rs_im[rs_2 ? 1 : 0];
        f->base = base;
        f->mark = mark;
        f->top = farmem.brk;
    }
    im_near = (uint16_t)((uint16_t)mem + im_off);
    far_put(base, (const uint8_t *)im_near, im_len);
    for (i = 0; i < h.rsh_nib; i++) {
        ICONBLK *ib = addr_of(&h, (uint32_t)(uint16_t)mem, R_ICONBLK, i);
        ib->ib_pmask = base + (ib->ib_pmask - im_near);
        ib->ib_pdata = base + (ib->ib_pdata - im_near);
    }
    pool_release(im_near);
    rs_imbase = base;
    rs_imsize = im_len;
}

/* COLOUR ICONS: THE EXTENSION GOES FAR, AND ITS MONO HEADERS COME NEAR.
 *
 * A new-format resource (rsh_vrsn bit 2) carries, after its rsh_rssize
 * bytes, an array of 68000 LONGs -- the file's true length, the offset of
 * the colour-icon table or 0/-1 for none, further extensions, a 0 -- and
 * at that offset one LONG per CICONBLK ending in -1, then the CICONBLKs:
 * each an ICONBLK, a LONG count of colour forms, the mono bits, the mono
 * mask, twelve bytes of text, and the colour forms (EmuTOS
 * aes/gemrslib.c, get_ciconblkptr and fixup_all_ciconblks).  A G_CICON
 * object's ob_spec is an INDEX into that table.
 *
 * MControl's extension is 34,752 bytes and HypView's 21,176, against a
 * pool of 14,336: it has no business there.  So it is streamed to far
 * memory through a slice of the pool, and only what the object library
 * reads through a near pointer comes back down -- one CICON_NEAR per
 * icon: the ICONBLK, its mask and bits named by far address exactly as a
 * mono icon's are once rs_imfar has moved them, its text beside it, and
 * where its colour forms are for the day objc_draw selects one.  They are
 * taken AFTER rs_imfar has wound the pool back, so they sit where the
 * mono images were and cost nothing extra when there were images to
 * move.  Like the image bits, the far block is app_free's to reclaim. */
#define CICON_TEXT  12
typedef struct {
    ICONBLK  ib;
    char     text[CICON_TEXT];
    uint32_t cicons;                    /* far: the first CICON, or 0 */
} CICON_NEAR;                           /* 50 bytes, and even */

#define CICON_MAX   256                 /* a table longer than this is not one */

uint32_t rs_cibase;                     /* where the extension went, 0 if none */
uint16_t rs_cisize;
static FARBLK   rs_ci[2];               /* by slot, as rs_im */

/* Give a slot's far blocks back, each while it is still the top of the
 * heap -- the extension was taken after the images, so it is asked first.
 * `slot` is 1 or 2, as rs_1/rs_2 are named. */
static void rs_farback(WORD slot)
{
    FARBLK *f = &rs_ci[slot - 1];
    if (f->base && farmem.brk == f->top) {
        far_release(f->mark);
        if (rs_cibase == f->base)
            rs_cibase = rs_cisize = 0;
        f->base = 0;
    }
    f = &rs_im[slot - 1];
    if (f->base && farmem.brk == f->top) {
        far_release(f->mark);
        f->base = 0;
    }
}

static uint32_t rd_long(uint32_t far)   /* a 68000 LONG, from far memory */
{
    uint8_t b[4];
    far_get(b, far, 4);
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | b[3];
}

/* `fd` is positioned just past the rsh_rssize bytes already in `h`.
 * 1 on success; 0 and nothing of the pool kept on any failure. */
static WORD rs_cicons(int16_t fd, RSHDR *h, uint16_t size)
{
    uint8_t ext[8], st;
    uint16_t got, n, i, mark, slice, k, bytes;
    uint32_t true_len, tab, ext_len, base, p, remaining, at;
    CICON_NEAR *near;
    uint8_t *buf;

    if (cio_read(fd, ext, sizeof ext, &got) != CIO_OK || got != sizeof ext)
        return 0;
    true_len = ((uint32_t)ext[0] << 24) | ((uint32_t)ext[1] << 16) | ((uint32_t)ext[2] << 8) | ext[3];
    tab      = ((uint32_t)ext[4] << 24) | ((uint32_t)ext[5] << 16) | ((uint32_t)ext[6] << 8) | ext[7];
    if (tab == 0 || tab == 0xFFFFFFFFUL)
        return 1;                       /* new format, no colour icons: an
                                         * outer resource's record stands */
    if (true_len <= (uint32_t)size + sizeof ext || tab < size)
        return 0;
    ext_len = true_len - size;
    rs_cibase = 0;
    rs_cisize = 0;
    {
        FARBLK *f = &rs_ci[rs_2 ? 1 : 0];
        f->mark = farmem.brk;
        base = far_alloc(ext_len);
        if (!base)
            return 0;
        f->base = base;
        f->top = farmem.brk;
    }
    far_put(base, ext, sizeof ext);

    /* the rest of it, through a slice of what the pool has spare */
    mark = pool_mark();
    slice = pool_room();
    slice = slice > 2048 ? 2048 : (uint16_t)(slice & ~1);
    if (slice < 64)
        return 0;
    buf = pool_alloc(slice, 2);
    if (!buf)
        return 0;
    p = base + sizeof ext;
    remaining = ext_len - sizeof ext;
    while (remaining) {
        k = remaining > slice ? slice : (uint16_t)remaining;
        st = cio_read(fd, buf, k, &got);
        if ((st != CIO_OK && st != CIO_OK_EOF) || got == 0) {
            pool_release(mark);
            return 0;
        }
        far_put(p, buf, got);
        p += got;
        remaining -= got;
    }
    pool_release(mark);

    /* One running far address walks the whole extension: the table up to
     * its -1, then each CICONBLK's header, bits, mask, text and forms in
     * the order the file has them.  (A file offset is `at - base + size`;
     * nothing below needs one.) */
    at = base + (tab - size);
    for (n = 0; n < CICON_MAX && rd_long(at) != 0xFFFFFFFFUL; n++)
        at += 4;
    if (n == 0 || n == CICON_MAX)
        return 0;
    at += 4;                            /* past the -1: the first CICONBLK */
    near = pool_alloc((uint16_t)(n * sizeof(CICON_NEAR)), 2);
    if (!near)
        return 0;

    for (i = 0; i < n; i++) {
        CICON_NEAR *c = &near[i];
        uint32_t num;
        far_get((uint8_t *)&c->ib, at, sizeof(ICONBLK));
        swap_words((uint8_t *)&c->ib + 12, 11); /* the WORDs after the
                                                 * three (junk) LONGs */
        num = rd_long(at + sizeof(ICONBLK));
        bytes = (uint16_t)((c->ib.ib_wicon / 16) * c->ib.ib_hicon * 2);
        at += sizeof(ICONBLK) + 4;      /* the mono bits... */
        c->ib.ib_pdata = at;
        at += bytes;                    /* ...the mono mask... */
        c->ib.ib_pmask = at;
        at += bytes;                    /* ...the text, copied near... */
        far_get((uint8_t *)c->text, at, CICON_TEXT);
        c->text[CICON_TEXT - 1] = 0;
        c->ib.ib_ptext = (uint16_t)c->text;
        at += CICON_TEXT;               /* ...and the colour forms */
        c->cicons = num ? at : 0;
        for (k = 0; k < num; k++) {     /* step over each: planes is the
                                         * high word of the first LONG */
            uint16_t planes = (uint16_t)(rd_long(at) >> 16);
            uint32_t sel = rd_long(at + 10);
            at += 22 + (uint32_t)bytes * planes + bytes;
            if (sel)
                at += (uint32_t)bytes * planes + bytes;
        }
    }

    /* the objects: an index becomes the near record's address */
    for (i = 0; i < h->rsh_nobs; i++) {
        OBJECT *obj = addr_of(h, (uint32_t)(uint16_t)h, R_OBJECT, i);
        if ((obj->ob_type & 0xFF) == G_CICON) {
            if (obj->ob_spec >= n)
                return 0;
            obj->ob_spec = (uint16_t)&near[obj->ob_spec];
        }
    }
    rs_cibase = base;
    rs_cisize = (uint16_t)ext_len;
    return 1;
}

void rs_ciaddr(uint32_t *base, uint16_t *len)
{
    *base = rs_cibase;
    *len = rs_cisize;
}

WORD rs_load(const char *name, WORD wants_far)
{
    RSHDR hdr, raw;
    char cio[CIO_NAME_MAX + 1];
    uint16_t got, size, mark;
    int16_t fd;
    uint8_t *mem;
    uint32_t base, fmark = 0;
    WORD ok, gofar, far = 0;

    if (rs_1 && rs_2)               /* one resident and one nested is all */
        return 0;
    sh_cioname(name, cio);          /* A:\X.RSC -> D1:X.RSC */
    fd = cio_open(cio, CIO_A_READ, 0);
    if (fd < 0)
        return 0;
    if (cio_read(fd, &raw, sizeof raw, &got) != CIO_OK || got != sizeof raw) {
        cio_close(fd);
        return 0;
    }
    hdr = raw;                      /* the file's header, read for its size */
    swap_words(&hdr, sizeof hdr / 2);
    size = hdr.rsh_rssize;
    if (size < sizeof hdr) {
        cio_close(fd);
        return 0;
    }
    /* WHERE A RESOURCE GOES, and why the pool is the second choice rather
     * than the first.  The pool is 14,336 bytes of bank $00 -- what is
     * left of the Atari's first 64 KB after the OS, this program's near
     * code and data, zwin and the MEMAC window (src/gem4xe.scm) -- and it
     * is shared by the desktop, every accessory and every program's near
     * region.  Far memory is 14.9 MB.  A resource is read once and then
     * walked by pointer, which a 32-bit pointer does as well as a 16-bit
     * one, so a caller that HOLDS 32-bit pointers has no reason to spend
     * bank $00 on one.
     *
     * So: far whenever the caller said it can take a far address, not
     * merely when the file would not fit.  This was the fallback until
     * 2026-09-19, which meant a small resource always landed in the pool
     * and the pool ran out with 14 MB unused -- two accessories beside
     * the desktop did not fit, and qed had to replace the desktop rather
     * than launch beside it.
     *
     * Colour icons stay pool-only, as they were: rs_fixit's new-format
     * path has not been taught far addresses. */
    mark = pool_mark();
    gofar = wants_far && !(hdr.rsh_vrsn & NEW_FORMAT_RSC);
    mem = gofar ? NULL : pool_alloc(size, 2);
    if (mem) {
        base = (uint32_t)(uint16_t)mem;
        memcpy(mem, &raw, sizeof raw);  /* rs_fixit takes the file as it is */
        {
            uint8_t st = cio_read(fd, mem + sizeof raw, (uint16_t)(size - sizeof raw), &got);
            if ((st != CIO_OK && st != CIO_OK_EOF) || got != size - sizeof raw) {
                cio_close(fd);
                pool_release(mark);
                return 0;
            }
        }
    } else if (gofar) {
        /* THE FAR PATH, taken whenever the caller can receive a far
         * address (docs/far-trees.md, "who may receive a far address": a
         * small-data program never gets here, because its kit passes no
         * int_in and aes_entry zeroes them).  One far_alloc, so the whole
         * resource is inside one bank and tree[obj] is safe to index --
         * far pointer arithmetic does not carry into the bank byte.
         * Streamed up through a small buffer, because a resource that
         * wanted the pool is exactly what there may be no room for. */
        uint8_t buf[128];
        uint16_t left, n, off;

        fmark = farmem.brk;
        base = far_alloc(size);
        if (!base) {
            cio_close(fd);
            return 0;
        }
        far_put(base, (const uint8_t *)&raw, sizeof raw);
        off = sizeof raw;
        left = (uint16_t)(size - sizeof raw);
        while (left) {
            uint8_t st;
            n = left < sizeof buf ? left : (uint16_t)sizeof buf;
            st = cio_read(fd, buf, n, &got);
            if ((st != CIO_OK && st != CIO_OK_EOF) || got != n) {
                cio_close(fd);
                far_release(fmark);
                return 0;
            }
            far_put(base + off, buf, n);
            off = (uint16_t)(off + n);
            left = (uint16_t)(left - n);
        }
        far = 1;
    } else {
        cio_close(fd);
        return 0;
    }
    if (rs_1) {                     /* nested: rs_cur now answers with it */
        rs_2 = base;  rs_2mark = mark;  rs_2far = far ? fmark : 0;
    } else {
        rs_1 = base;  rs_1mark = mark;  rs_1far = far ? fmark : 0;
    }
    rs_fixit(base);
    ok = 1;
    if (!far) {
        rs_imfar(mem, hdr.rsh_imdata, size);
        /* the colour icons, if the file has the extension for them: the
         * fd is still positioned just past the rsh_rssize bytes */
        if (hdr.rsh_vrsn & NEW_FORMAT_RSC)
            ok = rs_cicons(fd, (RSHDR *)mem, size);
    }
    cio_close(fd);
    if (!ok) {                      /* refused whole: nothing half-loaded */
        WORD slot = rs_2 ? 2 : 1;
        if (rs_2)
            rs_2 = 0;
        else
            rs_1 = 0;
        rs_farback(slot);
        pool_release(mark);
        return 0;
    }
    return 1;
}

uint32_t rs_loaded(void)
{
    return rs_cur;
}

void rs_header(RSHDR *h)
{
    if (rs_cur)
        hdr_get(rs_cur, h);
    else
        memset(h, 0, sizeof *h);
}

WORD rs_free(void)
{
    if (rs_2) {                     /* the nested one first: LIFO */
        if (rs_2far)
            far_release(rs_2far);
        else
            pool_release(rs_2mark);
        rs_2 = 0;
        rs_2far = 0;
        rs_farback(2);
        return 1;
    }
    if (!rs_1)
        return 0;
    if (rs_1far)
        far_release(rs_1far);
    else
        pool_release(rs_1mark);
    rs_1 = 0;
    rs_1far = 0;
    rs_farback(1);
    return 1;
}

WORD rs_gaddr(UWORD rtype, UWORD rindex, uint32_t *paddr)
{
    RSHDR h;
    uint32_t a;
    if (!rs_cur)
        return 0;
    hdr_get(rs_cur, &h);
    a = addr_at(&h, rs_cur, rtype, rindex);
    *paddr = a;
    return a != 0xFFFFFFFFUL;
}

WORD rs_saddr(UWORD rtype, UWORD rindex, uint32_t addr)
{
    RSHDR h;
    uint32_t a;
    if (!rs_cur)
        return 0;
    hdr_get(rs_cur, &h);
    a = addr_at(&h, rs_cur, rtype, rindex);
    if (a == 0xFFFFFFFFUL)
        return 0;
    wr_native(a, addr);
    return 1;
}
