/* objc.c -- the AES object library: tree walking, drawing, hit testing,
 * state changes and field editing (EmuTOS aes/gemoblib.c, gemobjop.c,
 * gemobed.c).
 *
 * objc_draw is the centre of the AES.  Everything visible in GEM -- dialogs,
 * menus, the desktop, window contents -- is an object tree drawn by this, so
 * it is the piece worth getting exactly right before anything above it, and
 * "exactly" is meant literally: the host reference in tools/aesref.py mirrors
 * every branch here, and the m4 gate compares pixels.
 *
 * Nothing in this file touches a pixel.  Drawing goes through graf.c, which
 * goes through the VDI parameter block exactly as an application would; the
 * AES has no private path to the screen, which is what keeps the device seam
 * meaningful.
 */
#include "portab.h"
#include "aes.h"
#include "../vdi/vdi.h"
#include "../sys/zwin.h"

/* GEM's scratch strings for formatting and editing a field (the D structure
 * in the donor).  A field longer than MAX_LEN-1 is out of contract. */
ZWIN static char g_rawstr[MAX_LEN];
ZWIN static char g_tmpstr[MAX_LEN];
ZWIN static char g_valstr[MAX_LEN];
ZWIN static char g_fmtstr[MAX_LEN];

/* The TEDINFO of the field being edited, shared by ob_edit's helpers. */
static TEDINFO edblk;

/* ---- tiny string helpers ----------------------------------------------
 * Local rather than <string.h> so the AES stays free of the C library; the
 * copies are bounded, which the donor's are not. */

static WORD str_len(const char *s)
{
    WORD n = 0;
    while (s[n])
        n++;
    return n;
}

/* Copy at most MAX_LEN-1 characters; returns the length copied. */
static WORD str_cpy(char *dst, const char *src)
{
    WORD n = 0;
    while (src[n] && n < MAX_LEN - 1) {
        dst[n] = src[n];
        n++;
    }
    dst[n] = 0;
    return n;
}

/* ---- addresses in ob_spec ---------------------------------------------
 * ob_spec is a 32-bit GEM address, and ALL TWENTY-FOUR BITS OF IT MATTER:
 * a resource too big for the pool loads into far memory and its strings,
 * TEDINFOs and BITBLKs are addressed there (docs/far-trees.md).  This
 * comment used to say the opposite -- "everything the AES reaches lives
 * in bank $00, so the low 16 bits are the pointer" -- which was true
 * before far trees and is what mn_text was still doing afterwards, with
 * the bank thrown away and the copy landing on the DOS. */

#define SPEC_PTR(spec)  ((void FAR *)(uint32_t)(spec))

static uint32_t ob_getspec(const OBJECT FAR *tree, WORD obj)
{
    uint32_t spec = tree[obj].ob_spec;
    if (tree[obj].ob_flags & INDIRECT)
        spec = *(const uint32_t FAR *)SPEC_PTR(spec);
    return spec;
}

/* ---- tree structure ---------------------------------------------------- */

/* The parent of obj, found by walking the sibling chain to the object whose
 * ob_tail points back at us: GEM stores no parent link. */
WORD ob_get_par(OBJECT FAR *tree, WORD obj)
{
    WORD pobj;

    if (obj == ROOT)
        return NIL;
    pobj = tree[obj].ob_next;
    if (pobj != NIL) {
        while (tree[pobj].ob_tail != obj) {
            obj = pobj;
            pobj = tree[obj].ob_next;
        }
    }
    return pobj;
}

/* The sibling before obj under parent, or NIL if obj is the first. */
static WORD get_prev(const OBJECT FAR *tree, WORD parent, WORD obj)
{
    WORD pobj, nobj;

    pobj = tree[parent].ob_head;
    if (pobj == obj)
        return NIL;
    for (;;) {
        nobj = tree[pobj].ob_next;
        if (nobj == obj)
            return pobj;
        if (nobj == parent)
            return NIL;
        pobj = nobj;
    }
}

/* Screen position of obj: its own ob_x/ob_y plus every ancestor's. */
void ob_offset(OBJECT FAR *tree, WORD obj, WORD *px, WORD *py)
{
    WORD x = 0, y = 0;

    do {
        x = (WORD)(x + tree[obj].ob_x);
        y = (WORD)(y + tree[obj].ob_y);
        obj = ob_get_par(tree, obj);
    } while (obj != NIL);
    *px = x;
    *py = y;
}

void ob_actxywh(OBJECT FAR *tree, WORD obj, GRECT *pt)
{
    ob_offset(tree, obj, &pt->g_x, &pt->g_y);
    pt->g_w = tree[obj].ob_width;
    pt->g_h = tree[obj].ob_height;
}

void ob_relxywh(OBJECT FAR *tree, WORD obj, GRECT *pt)
{
    pt->g_x = tree[obj].ob_x;
    pt->g_y = tree[obj].ob_y;
    pt->g_w = tree[obj].ob_width;
    pt->g_h = tree[obj].ob_height;
}

/* ---- editing the tree: what the window manager does to W_TREE ----------- */

/* Make child the last child of parent. */
void ob_add(OBJECT FAR *tree, WORD parent, WORD child)
{
    WORD ptail;

    if (parent == NIL || child == NIL)
        return;
    tree[child].ob_next = parent;
    ptail = tree[parent].ob_tail;
    if (ptail == NIL)
        tree[parent].ob_head = child;
    else
        tree[ptail].ob_next = child;
    tree[parent].ob_tail = child;
}

/* Unlink obj from its parent's chain (the object itself is untouched).
 * FALSE for the root, or an object that is not in its parent's chain. */
WORD ob_delete(OBJECT FAR *tree, WORD obj)
{
    WORD parent, prev, nextsib;

    if (obj == ROOT)
        return FALSE;
    nextsib = tree[obj].ob_next;
    parent = ob_get_par(tree, obj);
    if (tree[parent].ob_head == obj) {
        if (tree[parent].ob_tail == obj) {
            nextsib = NIL;
            tree[parent].ob_tail = NIL;
        }
        tree[parent].ob_head = nextsib;
    } else {
        prev = get_prev(tree, parent, obj);
        if (prev == NIL)
            return FALSE;
        tree[prev].ob_next = nextsib;
        if (tree[parent].ob_tail == obj)
            tree[parent].ob_tail = prev;
    }
    return TRUE;
}

/* Move mov_obj to position new_pos among its siblings: 0 is the first
 * (drawn first, so at the back), NIL the last (drawn last, on top). */
WORD ob_order(OBJECT FAR *tree, WORD mov_obj, WORD new_pos)
{
    WORD parent, chg_obj, ii;

    if (mov_obj == ROOT)
        return FALSE;
    parent = ob_get_par(tree, mov_obj);
    ob_delete(tree, mov_obj);
    chg_obj = tree[parent].ob_head;
    /* An only child: nothing to order against.  The donor would index
     * tree[NIL] for new_pos == NIL, and for 0 leave it without its parent
     * link or the tail set; it simply goes back as the only child. */
    if (chg_obj == NIL) {
        ob_add(tree, parent, mov_obj);
        return TRUE;
    }
    if (new_pos == 0) {
        tree[mov_obj].ob_next = chg_obj;
        tree[parent].ob_head = mov_obj;
    } else {
        if (new_pos == NIL) {
            chg_obj = tree[parent].ob_tail;
        } else {
            for (ii = 1; ii < new_pos; ii++)
                chg_obj = tree[chg_obj].ob_next;
        }
        tree[mov_obj].ob_next = tree[chg_obj].ob_next;
        tree[chg_obj].ob_next = mov_obj;
    }
    if (tree[mov_obj].ob_next == parent)
        tree[parent].ob_tail = mov_obj;
    return TRUE;
}

/* Visit every object from `this` to (not including) `last`, depth-first,
 * no deeper than maxdep below the start, calling routine(tree, obj, x, y)
 * with the object's screen position.  Iterative, the way the donor does it,
 * with a small stack of the positions on the way down. */
void everyobj(OBJECT FAR *tree, WORD this, WORD last, OBJ_ROUTINE routine,
                     WORD startx, WORD starty, WORD maxdep)
{
    WORD tmp, depth, px, py;
    WORD x[MAX_DEPTH + 2], y[MAX_DEPTH + 2];

    x[0] = startx;
    y[0] = starty;
    depth = 1;

    for (;;) {
        /* down: visit this object, then its first child */
        if (this == last)
            return;
        /* Through scalars, not `x[depth] = x[depth-1] + tree[this].ob_x`:
         * Calypsi 5.18 compiles that as `lda (&x[depth-1]),y` -- a LOAD
         * from address x[depth-1]+ob_x, not an add.  tools/ccbug/ has the
         * reproducer; `make check-cc` runs it in the vendor's simulator. */
        px = x[depth - 1];
        py = y[depth - 1];
        px = (WORD)(px + tree[this].ob_x);
        py = (WORD)(py + tree[this].ob_y);
        x[depth] = px;
        y[depth] = py;
        routine(tree, this, px, py);
        if (tree[this].ob_head != NIL && !(tree[this].ob_flags & HIDETREE)
            && depth <= maxdep) {
            depth++;
            this = tree[this].ob_head;
            continue;
        }
        /* across, or back up until there is a sibling to move across to */
        for (;;) {
            tmp = tree[this].ob_next;
            if (tmp == last || this == ROOT)
                return;
            if (tree[tmp].ob_tail != this) {
                this = tmp;         /* a sibling */
                break;
            }
            depth--;                /* tmp is the parent: go up */
            this = tmp;
        }
    }
}

/* ---- the object's drawing attributes ----------------------------------
 * Everything just_draw needs to know about an object in one call: its
 * (indirected) spec, state, type, flags, relative rectangle, and border
 * thickness; returns the BOXCHAR character.  (gemobjop.c ob_sst.) */

static char ob_sst(OBJECT FAR *tree, WORD obj, uint32_t *pspec, WORD *pstate,
                   WORD *ptype, WORD *pflags, GRECT *pt, WORD *pth)
{
    uint32_t spec;
    WORD th, type;
    char ch;

    *pflags = tree[obj].ob_flags;
    spec = ob_getspec(tree, obj);
    *pspec = spec;
    *pstate = tree[obj].ob_state;
    type = tree[obj].ob_type & 0xFF;
    *ptype = type;
    ob_relxywh(tree, obj, pt);

    th = 0;
    ch = 0;
    switch (type) {
    case G_TITLE:
        th = 1;
        break;
    case G_TEXT:
    case G_BOXTEXT:
    case G_FTEXT:
    case G_FBOXTEXT:
        th = ((const TEDINFO FAR *)SPEC_PTR(spec))->te_thickness;
        break;
    case G_BOX:
    case G_BOXCHAR:
    case G_IBOX: {
        /* 68000 byte order inside the LONG: char, thickness, colour.  The
         * thickness is a signed byte -- negative is an outward border --
         * and the sign extension has to go through a local: Calypsi 5.18
         * drops an (int8_t) cast applied to anything derived from a 32-bit
         * value in the same expression (tools/ccbug/, `make check-cc`). */
        WORD hi = (WORD)(spec >> 16);
        int8_t sth = (int8_t)hi;
        th = sth;
        ch = (char)(hi >> 8);
        break;
    }
    case G_BUTTON:
        th = -1;
        if (*pflags & EXIT)
            th--;
        if (*pflags & DEFAULT)
            th--;
        break;
    default:
        break;
    }
    *pth = th;
    return ch;
}

/* ---- formatting a field ------------------------------------------------
 * Merge raw text into a template: each '_' in the template takes the next
 * raw character (from the right for TE_RIGHT), other characters copy
 * through, and an unfilled '_' stays '_'.  A raw string of "@" means empty.
 * fmt must have room for the template. */
void ob_format(WORD just, char *raw, const char *tmpl, char *fmt)
{
    WORD ptlen, prlen, inc;
    WORD pf, pt, pr, ptend, prend;

    if (raw[0] == '@')
        raw[0] = 0;

    ptlen = str_len(tmpl);
    prlen = str_len(raw);
    fmt[ptlen] = 0;

    inc = 1;
    pf = pt = pr = 0;
    if (just == TE_RIGHT) {
        inc = -1;
        pf = (WORD)(ptlen - 1);
        pt = (WORD)(ptlen - 1);
        pr = (WORD)(prlen - 1);
    }
    ptend = (WORD)(pt + inc * ptlen);
    prend = (WORD)(pr + inc * prlen);

    while (pt != ptend) {
        if (tmpl[pt] != '_') {
            fmt[pf] = tmpl[pt];
        } else if (pr != prend) {
            fmt[pf] = raw[pr];
            pr = (WORD)(pr + inc);
        } else {
            fmt[pf] = '_';
        }
        pf = (WORD)(pf + inc);
        pt = (WORD)(pt + inc);
    }
}

/* ---- drawing one object ------------------------------------------------ */

static void just_draw(OBJECT FAR *tree, WORD obj, WORD sx, WORD sy)
{
    WORD bcol, tcol, ipat, icol, tmode, th, tmpth;
    WORD state, type, flags, len;
    WORD tmpx, tmpy;
    uint32_t spec;
    char ch;
    GRECT t, c;
    TEDINFO ted;

    ch = ob_sst(tree, obj, &spec, &state, &type, &flags, &t, &th);

    if ((flags & HIDETREE) || spec == 0xFFFFFFFFUL)
        return;

    t.g_x = sx;
    t.g_y = sy;

    /* Trivial reject on the full extent: outline, shadow and border. */
    if (gl_clip.g_w && gl_clip.g_h) {
        c = t;
        if (state & OUTLINED)
            gr_inside(&c, -3);
        else
            gr_inside(&c, (WORD)((th < 0) ? 3 * th : -3 * th));
        if (!gsx_chkclip(&c))
            return;
    }

    bcol = BLACK;
    tcol = BLACK;
    ipat = IP_HOLLOW;
    icol = WHITE;
    tmode = MD_REPLACE;

    if (type != G_STRING) {
        tmpth = (WORD)((th < 0) ? 0 : th);

        /* the text types: fetch the TEDINFO and crack its colour word */
        switch (type) {
        case G_TEXT:
        case G_BOXTEXT:
        case G_FTEXT:
        case G_FBOXTEXT:
            far_get((uint8_t *)&ted, spec, sizeof ted);   /* not a struct copy: B11 */
            gr_crack((UWORD)ted.te_color, &bcol, &tcol, &ipat, &icol, &tmode);
            break;
        default:
            break;
        }

        /* the box types: crack the colour if not a ted, then draw the
         * border and the filled box */
        switch (type) {
        case G_BOX:
        case G_BOXCHAR:
        case G_IBOX:
            gr_crack((UWORD)spec, &bcol, &tcol, &ipat, &icol, &tmode);
            /* fall through */
        case G_BUTTON:
            if (type == G_BUTTON) {
                bcol = BLACK;
                ipat = IP_HOLLOW;
                icol = WHITE;
            }
            /* fall through */
        case G_BOXTEXT:
        case G_FBOXTEXT:
            if (th != 0) {
                gsx_attr(0, MD_REPLACE, bcol);
                gr_box(t.g_x, t.g_y, t.g_w, t.g_h, th);
            }
            if (type != G_IBOX) {
                gr_inside(&t, tmpth);
                gr_rect(icol, ipat, &t);
                gr_inside(&t, (WORD)-tmpth);
            }
            break;
        default:
            break;
        }

        gsx_attr(1, tmode, tcol);

        /* what is in the box */
        switch (type) {
        case G_FTEXT:
        case G_FBOXTEXT:
            far_strget(g_rawstr, ted.te_ptext, sizeof g_rawstr);
            far_strget(g_tmpstr, ted.te_ptmplt, sizeof g_tmpstr);
            ob_format(ted.te_just, g_rawstr, g_tmpstr, g_fmtstr);
            /* fall through */
        case G_BOXCHAR:
            ted.te_ptext = (uint16_t)g_fmtstr;
            if (type == G_BOXCHAR) {
                g_fmtstr[0] = ch;
                g_fmtstr[1] = 0;
                ted.te_just = TE_CNTR;
                ted.te_font = IBM;
            }
            /* fall through */
        case G_TEXT:
        case G_BOXTEXT:
            c = t;
            gr_inside(&c, tmpth);
            gr_gtext(ted.te_just, ted.te_font,
                     (const char FAR *)SPEC_PTR(ted.te_ptext), &c);
            break;
        case G_IMAGE: {
            const BITBLK FAR *bi = (const BITBLK FAR *)SPEC_PTR(spec);
            gsx_blt(bi->bi_pdata, bi->bi_x, bi->bi_y, t.g_x, t.g_y,
                    (WORD)(bi->bi_wb * 8), bi->bi_hl, MD_TRANS,
                    bi->bi_color, WHITE);
            break;
        }
        case G_ICON:
        case G_CICON: {
            /* The donor's gr_gicon (gemgraf.c): the mask under the image,
             * both transparent, then the character and the label.  Every
             * rectangle in the ICONBLK is relative to the object.
             *
             * A COLOUR ICON DRAWS ITS MONO FORM.  A CICONBLK begins with a
             * plain ICONBLK -- the donor relies on that too (gemoblib.c
             * falls G_CICON through to gr_gicon) -- and rsrc_load leaves a
             * G_CICON's ob_spec pointing at a near copy of that ICONBLK
             * whose bits are in far memory (src/aes/rsrc.c, rs_cicons).
             * The colour planes are kept far beside it for the day this
             * case selects them: on a 16-colour surface that is the
             * natural thing to draw, and it is not drawn yet. */
            ICONBLK ib;
            far_get((uint8_t *)&ib, spec, sizeof ib);   /* not a struct copy: B11 */
            GRECT pi, pl;
            WORD fg = (ib.ib_char >> 12) & 0x0F;
            WORD bg = (ib.ib_char >> 8) & 0x0F;
            WORD ch = ib.ib_char & 0xFF;
            const char FAR *label = (const char FAR *)SPEC_PTR(ib.ib_ptext);

            if (state & SELECTED) {     /* selected: the colours change places */
                WORD tmp = fg;
                fg = bg;
                bg = tmp;
            }
            r_set(&pi, (WORD)(ib.ib_xicon + t.g_x), (WORD)(ib.ib_yicon + t.g_y),
                  ib.ib_wicon, ib.ib_hicon);
            r_set(&pl, (WORD)(ib.ib_xtext + t.g_x), (WORD)(ib.ib_ytext + t.g_y),
                  ib.ib_wtext, ib.ib_htext);

            /* WHITEBAK over a white background leaves what is there */
            if (!((state & WHITEBAK) && bg == WHITE)) {
                gsx_blt(ib.ib_pmask, 0, 0, pi.g_x, pi.g_y, pi.g_w, pi.g_h,
                        MD_TRANS, bg, fg);
                if (label && *label)
                    gr_rect(bg, IP_SOLID, &pl);
            }
            gsx_blt(ib.ib_pdata, 0, 0, pi.g_x, pi.g_y, pi.g_w, pi.g_h,
                    MD_TRANS, fg, bg);

            gsx_attr(TRUE, MD_TRANS, fg);
            if (ch) {
                intin[0] = ch;
                gsx_tblt(SMALL, (WORD)(pi.g_x + ib.ib_xchar),
                         (WORD)(pi.g_y + ib.ib_ychar), 1);
            }
            if (label)
                gr_gtext(TE_CNTR, SMALL, label, &pl);
            /* the state is spent: ob_draw must not invert it again */
            state &= ~SELECTED;
            break;
        }
        /* G_USERDEF is not drawn yet. */
        default:
            break;
        }
    }

    /* the text of a string, title or button: centred vertically, and
     * horizontally too for a button.  A title has no border of its own --
     * the menu bar it sits in provides one. */
    if (type == G_STRING || type == G_TITLE || type == G_BUTTON) {
        len = expand_string(intin, (const char FAR *)SPEC_PTR(spec));
        if (len) {
            gsx_attr(1, MD_TRANS, BLACK);
            tmpx = t.g_x;
            tmpy = (WORD)(t.g_y + (t.g_h - gl_hchar) / 2);
            if (type == G_BUTTON)
                tmpx = (WORD)(tmpx + (t.g_w - len * gl_wchar) / 2);
            gsx_tblt(IBM, tmpx, tmpy, len);
        }
    }

    if (state & OUTLINED) {
        gsx_attr(0, MD_REPLACE, BLACK);
        gr_box((WORD)(t.g_x - 3), (WORD)(t.g_y - 3),
               (WORD)(t.g_w + 6), (WORD)(t.g_h + 6), 1);
        gsx_attr(0, MD_REPLACE, WHITE);
        gr_box((WORD)(t.g_x - 2), (WORD)(t.g_y - 2),
               (WORD)(t.g_w + 4), (WORD)(t.g_h + 4), 2);
    }

    /* the remaining effects apply inside an inward border and, for an
     * outward one, use its thickness for the shadow */
    if (th > 0)
        gr_inside(&t, th);
    else
        th = (WORD)-th;

    if ((state & SHADOWED) && th) {
        gsx_fcolor(bcol);
        bb_fill(MD_REPLACE, FIS_SOLID, 0, t.g_x, (WORD)(t.g_y + t.g_h + th),
                (WORD)(t.g_w + th), (WORD)(2 * th));
        bb_fill(MD_REPLACE, FIS_SOLID, 0, (WORD)(t.g_x + t.g_w + th), t.g_y,
                (WORD)(2 * th), (WORD)(t.g_h + 3 * th));
    }

    if (state & CHECKED) {
        gsx_attr(1, MD_TRANS, BLACK);
        intin[0] = 0x08;                        /* the check mark glyph */
        gsx_tblt(IBM, (WORD)(t.g_x + 2), t.g_y, 1);
    }

    if (state & CROSSED) {
        gsx_attr(0, MD_TRANS, WHITE);
        gsx_cline(t.g_x, t.g_y, (WORD)(t.g_x + t.g_w - 1), (WORD)(t.g_y + t.g_h - 1));
        gsx_cline(t.g_x, (WORD)(t.g_y + t.g_h - 1), (WORD)(t.g_x + t.g_w - 1), t.g_y);
    }

    if (state & DISABLED) {
        gsx_fcolor(WHITE);
        bb_fill(MD_TRANS, FIS_PATTERN, IP_4PATT, t.g_x, t.g_y, t.g_w, t.g_h);
    }

    if (state & SELECTED)
        bb_fill(MD_XOR, FIS_SOLID, IP_SOLID, t.g_x, t.g_y, t.g_w, t.g_h);
}

/* ---- drawing a subtree -------------------------------------------------- */

void ob_draw(OBJECT FAR *tree, WORD obj, WORD depth)
{
    WORD last, pobj, sx, sy;

    last = (obj == ROOT) ? NIL : tree[obj].ob_next;
    pobj = ob_get_par(tree, obj);
    if (pobj != NIL)
        ob_offset(tree, pobj, &sx, &sy);
    else
        sx = sy = 0;

    gsx_moff();
    everyobj(tree, obj, last, just_draw, sx, sy, depth);
    gsx_mon();
}

/* Draw the subtree at start, `depth` levels deep, clipped.  The clip stays
 * in force afterwards, as in the donor: the AES does not restore it. */
void objc_draw(OBJECT FAR *tree, WORD start, WORD depth, const GRECT *clip)
{
    gsx_sclip(clip);
    ob_draw(tree, start, depth);
}

/* ---- hit testing ---------------------------------------------------------
 * The deepest object under (mx,my), searching children LAST to FIRST so
 * that the one drawn on top wins, no deeper than `depth` below start. */

WORD ob_find(OBJECT FAR *tree, WORD currobj, WORD depth, WORD mx, WORD my)
{
    WORD lastfound, dosibs, done, parent, child;
    GRECT t, o;

    lastfound = NIL;
    if (currobj == ROOT) {
        r_set(&o, 0, 0, 0, 0);
    } else {
        parent = ob_get_par(tree, currobj);
        ob_actxywh(tree, parent, &o);
    }

    done = 0;
    dosibs = 0;
    while (!done) {
        ob_relxywh(tree, currobj, &t);
        t.g_x = (WORD)(t.g_x + o.g_x);
        t.g_y = (WORD)(t.g_y + o.g_y);
        if (inside(mx, my, &t) && !(tree[currobj].ob_flags & HIDETREE)) {
            lastfound = currobj;
            child = tree[currobj].ob_tail;
            if (child != NIL && depth) {
                currobj = child;
                depth--;
                o.g_x = t.g_x;
                o.g_y = t.g_y;
                dosibs = 1;
            } else {
                done = 1;
            }
        } else if (dosibs && lastfound != NIL) {
            currobj = get_prev(tree, lastfound, currobj);
            if (currobj == NIL)
                done = 1;
        } else {
            done = 1;
        }
    }
    return lastfound;
}

WORD objc_find(OBJECT FAR *tree, WORD start, WORD depth, WORD mx, WORD my)
{
    return ob_find(tree, start, depth, mx, my);
}

void objc_offset(OBJECT FAR *tree, WORD obj, WORD *px, WORD *py)
{
    ob_offset(tree, obj, px, py);
}

/* ---- changing state ------------------------------------------------------ */

/* Exported for the form and graphics libraries, which change state under
 * whatever clip is already in force. */
void ob_change(OBJECT FAR *tree, WORD obj, UWORD new_state, WORD redraw)
{
    WORD flags, type, th, curr_state;
    uint32_t spec;
    GRECT t;

    ob_sst(tree, obj, &spec, &curr_state, &type, &flags, &t, &th);
    if ((UWORD)curr_state == new_state || spec == 0xFFFFFFFFUL)
        return;
    tree[obj].ob_state = new_state;
    if (!redraw)
        return;

    ob_offset(tree, obj, &t.g_x, &t.g_y);
    gsx_moff();
    if (th < 0)
        th = 0;
    /* A change of SELECTED alone is an XOR of the inside -- cheap, and it
     * is what makes a button flash.  Anything else redraws the object.
     * (Icons never XOR: they would redraw here once they are drawn.) */
    if (type != G_ICON && type != G_CICON && type != G_USERDEF &&
        ((new_state ^ (UWORD)curr_state) & SELECTED)) {
        bb_fill(MD_XOR, FIS_SOLID, IP_SOLID, (WORD)(t.g_x + th), (WORD)(t.g_y + th),
                (WORD)(t.g_w - 2 * th), (WORD)(t.g_h - 2 * th));
        redraw = 0;
    }
    if (redraw)
        just_draw(tree, obj, t.g_x, t.g_y);
    gsx_mon();
}

void objc_change(OBJECT FAR *tree, WORD obj, const GRECT *clip, UWORD newstate,
                 WORD redraw)
{
    gsx_sclip(clip);
    ob_change(tree, obj, newstate, redraw);
}

/* ---- centring a dialog ----------------------------------------------------
 * Move the root to the centre of the screen below the menu bar, and return
 * the rectangle it covers including any outline and shadow -- which is what
 * form_dial needs to clear afterwards. */
void ob_center(OBJECT FAR *tree, GRECT *pt)
{
    WORD xd, yd, wd, hd, th, dummy;
    uint32_t spec;
    GRECT t;

    wd = tree[ROOT].ob_width;
    hd = tree[ROOT].ob_height;
    xd = (WORD)((gl_width - wd) / 2);
    yd = (WORD)(gl_hbox + (gl_height - gl_hbox - hd) / 2);
    tree[ROOT].ob_x = xd;
    tree[ROOT].ob_y = yd;

    if (tree[ROOT].ob_state & OUTLINED) {
        xd = (WORD)(xd - 3);
        if (xd < 0)
            xd = 0;
        yd = (WORD)(yd - 3);
        if (yd < 0)
            yd = 0;
        wd = (WORD)(wd + 6);
        hd = (WORD)(hd + 6);
    }
    if (tree[ROOT].ob_state & SHADOWED) {
        ob_sst(tree, ROOT, &spec, &dummy, &dummy, &dummy, &t, &th);
        if (th < 0)
            th = (WORD)-th;
        wd = (WORD)(wd + 2 * th);
        hd = (WORD)(hd + 2 * th);
    }
    r_set(pt, xd, yd, wd, hd);
}

/* ---- editing a field ------------------------------------------------------
 * A G_FTEXT/G_FBOXTEXT field is three strings: the raw text, a template in
 * which each '_' is a position the text fills, and a validation string
 * saying which characters each position accepts.  The cursor index counts
 * raw characters, not template columns. */

/* Where raw character `pos` lands in the template, as a column. */
static WORD find_pos(const char *str, WORD pos)
{
    WORD i;

    for (i = 0; pos > 0; i++) {
        if (str[i] == '_')
            pos--;
    }
    while (str[i] && str[i] != '_')
        i++;
    return i;
}

/* Skip template text up to chr (or the end), counting the fields passed. */
static WORD scan_to_end(const char *pstr, WORD idx, char chr)
{
    while (*pstr && *pstr != chr) {
        if (*pstr++ == '_')
            idx++;
    }
    return idx;
}

/* Is chr in a validation set like "0..9A..Z "?  Ranges are inclusive and
 * compared as unsigned bytes, so \x80..\xff means every high character. */
static WORD instr(char chr, const char *str)
{
    unsigned char c = (unsigned char)chr, t1, t2;

    while (*str) {
        t1 = t2 = (unsigned char)*str++;
        if (str[0] == '.' && str[1] == '.') {
            str += 2;
            t2 = (unsigned char)*str++;
        }
        if (c >= t1 && c <= t2)
            return 1;
    }
    return 0;
}

static char to_upper(char ch)
{
    WORD c = (uint8_t)ch;           /* a WORD, not a char: B8, tools/ccbug */
    if (c >= 'a' && c <= 'z')
        c -= 32;
    return (char)c;
}

/* Does the validation character valchar admit *in_char?  Most classes
 * fold to upper case on the way through. */
#define VALIDATE_N "0..9A..Z \x80\x8e\x8f\x90\x92\x99\x9a\x9e\xa5\xb5\xb6\xb7\xb8\xc2..\xdc"
#define VALIDATE_A (&VALIDATE_N[4])         /* 0..9 omitted */
#define VALIDATE_n "0..9a..zA..Z \x80..\xff"
#define VALIDATE_a (&VALIDATE_n[4])         /* 0..9 omitted */
#define VALIDATE_F ":?*a..zA..Z0..9_\x80..\xff"
#define VALIDATE_f (&VALIDATE_F[3])         /* :?* omitted */
#define VALIDATE_P ".?*a..zA..Z0..9_\\:\x80..\xff"
#define VALIDATE_p (&VALIDATE_P[3])         /* .?* omitted */

static WORD check(char *in_char, char valchar)
{
    WORD upcase = 1;
    const char *rstr = 0;

    switch (valchar) {
    case '9': rstr = "0..9";     upcase = 0; break;
    case 'A': rstr = VALIDATE_A; break;
    case 'N': rstr = VALIDATE_N; break;
    case 'a': rstr = VALIDATE_a; upcase = 0; break;
    case 'n': rstr = VALIDATE_n; upcase = 0; break;
    case 'F': rstr = VALIDATE_F; break;
    case 'f': rstr = VALIDATE_f; break;
    case 'P': rstr = VALIDATE_P; break;
    case 'p': rstr = VALIDATE_p; break;
    case 'X': return 1;
    case 'x': *in_char = to_upper(*in_char); return 1;
    default:  break;
    }
    if (rstr && instr(*in_char, rstr)) {
        if (upcase)
            *in_char = to_upper(*in_char);
        return 1;
    }
    return 0;
}

/* The screen cell of template column ch_pos of the field being edited. */
static void pxl_rect(OBJECT FAR *tree, WORD obj, WORD ch_pos, GRECT *pt)
{
    GRECT o;

    ob_actxywh(tree, obj, &o);
    gr_just(edblk.te_just, edblk.te_font,
            (const char FAR *)SPEC_PTR(edblk.te_ptmplt), o.g_w, o.g_h, &o);
    pt->g_x = (WORD)(o.g_x + ch_pos * gl_wchar);
    pt->g_y = o.g_y;
    pt->g_w = gl_wchar;
    pt->g_h = gl_hchar;
}

/* dist == 0: toggle the text cursor at template column new_pos (an XOR
 * line, so calling twice removes it).  dist > 0: redraw the field, clipped
 * to `dist` columns from new_pos. */
static void curfld(OBJECT FAR *tree, WORD obj, WORD new_pos, WORD dist)
{
    GRECT oc, t;

    pxl_rect(tree, obj, new_pos, &t);
    if (dist) {
        t.g_w = (WORD)(t.g_w + (dist - 1) * gl_wchar);
    } else {
        gsx_attr(0, MD_XOR, BLACK);
        t.g_y = (WORD)(t.g_y - 3);
        t.g_h = (WORD)(t.g_h + 6);
    }
    gsx_gclip(&oc);
    gsx_sclip(&t);
    if (dist)
        ob_draw(tree, obj, 0);
    else
        gsx_cline(t.g_x, t.g_y, t.g_x, (WORD)(t.g_y + t.g_h - 1));
    gsx_sclip(&oc);
}

/* The template columns of raw index idx and of the end of the text. */
static void ob_stfn(WORD idx, WORD *pstart, WORD *pfinish)
{
    *pstart = find_pos(g_tmpstr, idx);
    *pfinish = find_pos(g_tmpstr, str_len(g_rawstr));
}

/* Delete the raw character at idx; TRUE if there was nothing to delete. */
static WORD ob_delit(WORD idx)
{
    WORD i;

    if (g_rawstr[idx]) {
        for (i = idx; g_rawstr[i]; i++)
            g_rawstr[i] = g_rawstr[i + 1];
        return 0;
    }
    return 1;
}

/* Insert chr at pos in str, which holds at most tot_len bytes with its NUL;
 * a string already full loses its last character. */
static void ins_char(char *str, WORD pos, char chr, WORD tot_len)
{
    WORD ii, len;

    len = str_len(str);
    for (ii = len; ii > pos; ii--)
        str[ii] = str[ii - 1];
    str[ii] = chr;
    if (len + 1 < tot_len)
        str[len + 1] = 0;
    else
        str[tot_len - 1] = 0;
}

WORD ob_edit(OBJECT FAR *tree, WORD obj, WORD in_char, WORD *idx, WORD kind)
{
    WORD pos, len, ii, no_redraw, start, finish, nstart, nfinish;
    WORD dist, tmp_back, cur_pos;
    char bin_char;
    uint32_t ptext;                 /* te_ptext: a 32-bit GEM address */

    if (kind == EDSTART || obj <= 0)
        return 1;

    far_get((uint8_t *)&edblk, ob_getspec(tree, obj), sizeof edblk);   /* B11 */
    ptext = edblk.te_ptext;

    far_strget(g_tmpstr, edblk.te_ptmplt, sizeof g_tmpstr);
    far_strget(g_rawstr, ptext, sizeof g_rawstr);
    /* The validation string is repeated to the template's length: a short
     * one like "9" governs every position. */
    far_strget(g_valstr, edblk.te_pvalid, sizeof g_valstr);
    for (ii = 0; g_valstr[ii]; ii++)
        ;
    len = ii;
    while (ii > 0 && len < edblk.te_tmplen && len < MAX_LEN - 1)
        g_valstr[len++] = g_valstr[ii - 1];
    g_valstr[len] = 0;

    ob_format(edblk.te_just, g_rawstr, g_tmpstr, g_fmtstr);

    switch (kind) {
    case EDINIT:
        *idx = str_len(g_rawstr);
        break;

    case EDCHAR:
        no_redraw = 1;
        ob_stfn(*idx, &start, &finish);
        cur_pos = start;
        curfld(tree, obj, cur_pos, 0);          /* cursor off */

        switch (in_char) {
        case BACKSPACE:
            if (*idx > 0) {
                *idx -= 1;
                no_redraw = ob_delit(*idx);
            }
            break;
        case ESCAPE:
            *idx = 0;
            g_rawstr[0] = 0;
            no_redraw = 0;
            break;
        case DELETE:
            if (*idx <= edblk.te_txtlen - 2)
                no_redraw = ob_delit(*idx);
            break;
        case ARROW_LEFT:
            if (*idx > 0)
                *idx -= 1;
            break;
        case ARROW_RIGHT:
            if (*idx < str_len(g_rawstr))
                *idx += 1;
            break;
        default:
            tmp_back = 0;
            if (*idx > edblk.te_txtlen - 2) {
                /* the field is full: overwrite the last position */
                cur_pos--;
                start = cur_pos;
                tmp_back = 1;
                *idx -= 1;
            }
            bin_char = (char)(in_char & 0xFF);
            if (bin_char) {
                if (check(&bin_char, g_valstr[*idx])) {
                    ins_char(g_rawstr, *idx, bin_char, edblk.te_txtlen);
                    *idx += 1;
                    no_redraw = 0;
                } else {
                    /* not valid here: if it is a template character
                     * ahead, skip to it, padding with spaces */
                    if (tmp_back) {
                        *idx += 1;
                        cur_pos++;
                    }
                    pos = scan_to_end(g_tmpstr + cur_pos, *idx, bin_char);
                    if (pos < edblk.te_txtlen - 2) {
                        for (ii = *idx; ii < pos; ii++)
                            g_rawstr[ii] = ' ';
                        g_rawstr[pos] = 0;
                        *idx = pos;
                        no_redraw = 0;
                    }
                }
            }
            break;
        }

        far_strput(ptext, g_rawstr, edblk.te_txtlen);
        if (!no_redraw) {
            ob_format(edblk.te_just, g_rawstr, g_tmpstr, g_fmtstr);
            ob_stfn(*idx, &nstart, &nfinish);
            if (nstart < start)
                start = nstart;
            dist = (WORD)(((finish > nfinish) ? finish : nfinish) - start);
            if (dist)
                curfld(tree, obj, start, dist);
        }
        break;

    case EDEND:
    default:
        break;
    }

    cur_pos = find_pos(g_tmpstr, *idx);
    curfld(tree, obj, cur_pos, 0);              /* cursor on */
    return 1;
}

/* Edit the field: kind is EDINIT (place the cursor at the end of the
 * text), EDCHAR (apply a key), or EDEND (remove the cursor).  *idx is the
 * cursor index in and out. */
WORD objc_edit(OBJECT FAR *tree, WORD obj, WORD kchar, WORD *idx, WORD kind)
{
    gsx_sclip(&gl_rfull);
    return ob_edit(tree, obj, kchar, idx, kind);
}
