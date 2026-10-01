/* alert.c -- form_alert.  EmuTOS aes/gemfmalt.c, on the memory gem4xe
 * has.
 *
 * An alert is a dialog with no resource behind it: the caller writes one
 * as a string,
 *
 *      [1][This is some text|for the screen.][Ok|Cancel]
 *
 * and the AES makes a ten-object tree of it -- an icon, up to five
 * message lines, up to three buttons -- lays it out in character cells,
 * converts to pixels with the same rs_obfix() an application's resource
 * goes through, draws it over whatever is there, and hands back which
 * button was pressed.
 *
 * THE TREE.  The donor keeps DIALERT in its resident resource and the
 * substrings in static buffers beside it.  gem4xe has neither, so the
 * tree and the buffers are taken from the application pool for the
 * length of the call and released after it, as the file selector's are
 * (src/aes/fsel.c): ten OBJECTs and 5*(MAX_LINELEN+1) + 3*(MAX_BUTLEN+1)
 * bytes of string.  An application whose resource leaves less than that
 * gets 0 back, nothing drawn -- the same refusal the selector makes, and
 * for the same reason.
 *
 * THE ICONS.  Three 32x32 one-plane forms -- note, question, stop -- in
 * far memory (tools/gemdata.py), drawn as G_IMAGE objects, which is what
 * the donor's fm_alert does after it builds the tree.  The one the alert
 * asks for is copied into the pool first: the VDI blits a one-plane form
 * through a near pointer, so a form has to be in bank $00 (128 bytes,
 * for the length of the call).
 *
 * WHAT IS UNDER IT.  bb_save/bb_restore, the pair the menu library uses
 * for a drop-down (docs/phase8.md): the alert covers what it covers and
 * puts it back, so an application need not redraw for one.
 */
#include "portab.h"
#include <string.h>
#include "aes.h"
#include "sys/app.h"
#include "sys/farmem.h"
#include "gemdata.h"
#include "lang_rsc.h"

#define MAX_LINENUM  5
#define MAX_LINELEN  40
#define MAX_BUTNUM   3
#define MAX_BUTLEN   20

#define NUM_ALOBJS   10             /* the root, the icon, 5 lines, 3 buttons */
#define MSGOFF       2
#define BUTOFF       7

/* the string area: one buffer per message line and per button */
#define ALSTR_SIZE   (MAX_LINENUM * (MAX_LINELEN + 1) \
                      + MAX_BUTNUM * (MAX_BUTLEN + 1))

/* The three icons' far addresses.  Not a const table: the address of a
 * far object is not a compile-time constant to this compiler, so they are
 * taken at the call. */
static uint32_t al_icon(WORD n)
{
    switch (n) {
    case 1:  return (uint32_t)(const uint8_t FAR *)gem_icon_note;
    case 2:  return (uint32_t)(const uint8_t FAR *)gem_icon_quest;
    default: return (uint32_t)(const uint8_t FAR *)gem_icon_stop;
    }
}

/* The donor has these in util/; here they are one line each. */
static WORD al_max(WORD a, WORD b) { return a > b ? a : b; }

static void ob_setxywh(OBJECT FAR *tree, WORD obj, const GRECT *pt)
{
    tree[obj].ob_x = pt->g_x;
    tree[obj].ob_y = pt->g_y;
    tree[obj].ob_width = pt->g_w;
    tree[obj].ob_height = pt->g_h;
}

#define endstring(a)    ((a) == ']' || (a) == '\0')
#define endsubstring(a) ((a) == '|' || (a) == ']' || (a) == '\0')

/* The donor's fm_strbrk: break the string at | and ], writing each piece
 * into the buffer the object already points at.  A doubled || or ]] is a
 * literal one, as Atari TOS and PC GEM both have it. */
static const char *fm_strbrk(OBJECT FAR *tree, WORD start, WORD maxnum,
                             WORD maxlen, const char *alert,
                             WORD *pnum, WORD *plen)
{
    WORD i, j, len;
    char *p;

    *plen = 0;
    if (*alert == '[')
        alert++;

    for (i = 0; i < maxnum; i++, alert++) {
        p = (char *)(uint16_t)tree[start + i].ob_spec;
        for (j = 0; j < maxlen; j++) {
            if (endsubstring(*alert)) {
                if (*alert != '\0' && *alert == *(alert + 1))
                    alert++;            /* || or ]]: a literal one */
                else
                    break;
            }
            *p++ = *alert++;
        }
        *p = 0;
        len = (WORD)(p - (char *)(uint16_t)tree[start + i].ob_spec);
        if (len > *plen)
            *plen = len;
        while (!endsubstring(*alert))   /* a substring that was too long */
            alert++;
        if (endstring(*alert))
            break;
    }
    while (!endstring(*alert))          /* whatever is left of the group */
        alert++;
    *pnum = (WORD)(i < maxnum ? i + 1 : maxnum);
    if (*alert)
        alert++;
    return alert;
}

/* [icon][line|line][button|button] -> the pieces, in the tree. */
static void fm_parse(OBJECT FAR *tree, const char *palstr, WORD *picnum,
                     WORD *pnummsg, WORD *plenmsg, WORD *pnumbut, WORD *plenbut)
{
    const char *alert = palstr;

    *picnum = (WORD)(alert[1] - '0');
    alert = fm_strbrk(tree, MSGOFF, MAX_LINENUM, MAX_LINELEN, alert + 3,
                      pnummsg, plenmsg);
    fm_strbrk(tree, BUTOFF, MAX_BUTNUM, MAX_BUTLEN, alert, pnumbut, plenbut);
    *plenbut = (WORD)(*plenbut + 1);    /* half a character each side */
}

/* The donor's fm_build, in character cells: the icon at the left, the
 * message lines beside it, the buttons under whichever is taller. */
static void fm_build(OBJECT FAR *tree, WORD iconnum, WORD nummsg, WORD mlenmsg,
                     WORD numbut, WORD mlenbut)
{
    WORD i, hicon, allbut;
    GRECT al, ic, bt, ms;
    OBJECT FAR *obj;

    r_set(&al, 0, 0, 1, 1);
    r_set(&ms, 1, 1, mlenmsg, 1);
    r_set(&bt, 1, (WORD)(2 + nummsg), mlenbut, 1);
    r_set(&ic, 0, 0, 0, 0);

    if (iconnum) {
        hicon = (WORD)((GEM_ICON_HL + gl_hchar - 1) / gl_hchar);
        r_set(&ic, 1, 1, 4, hicon);
        al.g_w = (WORD)(al.g_w + ic.g_w + 1);
        ms.g_x = (WORD)(ic.g_x + ic.g_w + 1);
    }

    allbut = (WORD)(numbut * mlenbut + 2 * (numbut - 1));
    if (mlenmsg + al.g_w > allbut + 1) {
        al.g_w = (WORD)(al.g_w + mlenmsg + 1);
        bt.g_x = (WORD)((al.g_w - allbut) / 2);
    } else {
        al.g_w = (WORD)(allbut + 2);
        bt.g_x = 1;
    }

    bt.g_y = (WORD)(al_max((WORD)(ic.g_y + ic.g_h), (WORD)(nummsg + 1)) + 1);
    al.g_h = (WORD)(al_max((WORD)(bt.g_y + bt.g_h),
                           (WORD)(ic.g_y + ic.g_h)) + 1);

    ob_setxywh(tree, ROOT, &al);
    for (i = 0, obj = tree; i < NUM_ALOBJS; i++, obj++)
        obj->ob_next = obj->ob_head = obj->ob_tail = NIL;

    if (iconnum) {
        ob_setxywh(tree, 1, &ic);
        ob_add(tree, ROOT, 1);
    }
    for (i = 0; i < nummsg; i++) {
        ob_setxywh(tree, (WORD)(MSGOFF + i), &ms);
        ms.g_y++;
        ob_add(tree, ROOT, (WORD)(MSGOFF + i));
    }
    for (i = 0, obj = tree + BUTOFF; i < numbut; i++, obj++) {
        obj->ob_flags = SELECTABLE | EXIT | FL3DACT;   /* the 3D look's */
        obj->ob_state = NORMAL;
        ob_setxywh(tree, (WORD)(BUTOFF + i), &bt);
        bt.g_x = (WORD)(bt.g_x + mlenbut + 2);
        ob_add(tree, ROOT, (WORD)(BUTOFF + i));
    }
    (--obj)->ob_flags |= LASTOB;

    for (i = 0; i < NUM_ALOBJS; i++)
        rs_obfix(tree, i);
}

/* The tree an alert is made of, in the pool: ten objects, then the
 * strings they point at.  0 when the pool has not the room. */
static OBJECT FAR *al_tree(void)
{
    OBJECT FAR *tree = pool_alloc(NUM_ALOBJS * (uint16_t)sizeof(OBJECT), 2);
    char *str = pool_alloc(ALSTR_SIZE, 2);
    WORD i;

    if (!tree || !str)
        return 0;
    memset(tree, 0, NUM_ALOBJS * sizeof(OBJECT));
    for (i = 0; i < NUM_ALOBJS; i++) {
        tree[i].ob_next = tree[i].ob_head = tree[i].ob_tail = NIL;
        tree[i].ob_type = G_STRING;
        tree[i].ob_flags = NONE;
        tree[i].ob_state = NORMAL;
    }
    tree[ROOT].ob_type = G_BOX;
    tree[ROOT].ob_flags = FL3DBAK;          /* LASTOB goes on the last button;
                                             * FL3DBAK is drawn only with the
                                             * 3D look on, as on the ST */
    tree[ROOT].ob_spec = 0x00011100UL;      /* the donor's DIALERT root:
                                             * no character, one pixel of
                                             * border, colour word 0x1100 */
    tree[ROOT].ob_state = OUTLINED;
    tree[1].ob_type = G_IMAGE;
    for (i = 0; i < MAX_LINENUM; i++, str += MAX_LINELEN + 1) {
        tree[MSGOFF + i].ob_spec = (uint16_t)str;
        *str = 0;
    }
    for (i = 0; i < MAX_BUTNUM; i++, str += MAX_BUTLEN + 1) {
        tree[BUTOFF + i].ob_type = G_BUTTON;
        tree[BUTOFF + i].ob_spec = (uint16_t)str;
        *str = 0;
    }
    return tree;
}

/* form_alert: the string parsed, the tree built and drawn, the button
 * the user pressed (1..3).  0 when the pool cannot hold the tree. */
WORD fm_alert(WORD defbut, const char *palstr)
{
    WORD i, icnum, nummsg, mlenmsg, numbut, mlenbut;
    OBJECT FAR *tree;
    GRECT d, t;
    uint16_t mark;
    BITBLK FAR *bi;
    uint8_t *icon;

    mark = pool_mark();
    tree = al_tree();
    bi = pool_alloc((uint16_t)sizeof(BITBLK), 2);
    /* The icon's own bytes come down beside it: the VDI blits a 1-plane
     * form through a NEAR pointer (raster_1bpp in src/vdi/vdi.c), so a
     * form must be in bank $00 -- a far address would be read with its
     * bank byte dropped, which draws whatever happens to be at that
     * offset in bank $00.  128 bytes, for the length of the call. */
    icon = pool_alloc(GEM_ICON_WB * GEM_ICON_HL, 2);
    if (!tree || !bi || !icon) {
        pool_release(mark);
        return 0;
    }

    gr_mouse(ARROW, 0);

    fm_parse(tree, palstr, &icnum, &nummsg, &mlenmsg, &numbut, &mlenbut);
    fm_build(tree, icnum, nummsg, mlenmsg, numbut, mlenbut);

    if (defbut >= 1 && defbut <= numbut)
        tree[BUTOFF + defbut - 1].ob_flags |= DEFAULT;

    /* the icon: a 32x32 image, whatever the character cell made of it */
    if (icnum) {
        if (icnum < 1 || icnum > 3)
            icnum = 3;
        far_get(icon, al_icon(icnum), GEM_ICON_WB * GEM_ICON_HL);
        bi->bi_pdata = (uint16_t)icon;
        bi->bi_wb = GEM_ICON_WB;
        bi->bi_hl = GEM_ICON_HL;
        bi->bi_x = bi->bi_y = 0;
        bi->bi_color = BLACK;
        tree[1].ob_spec = (uint16_t)bi;
        tree[1].ob_width = tree[1].ob_height = GEM_ICON_HL;
    }

    ob_center(tree, &d);
    rc_intersect(&gl_rscreen, &d);

    wm_update(BEG_UPDATE);
    gsx_gclip(&t);
    bb_save(&d);

    gsx_sclip(&d);
    ob_draw(tree, ROOT, MAX_DEPTH);

    i = fm_do(tree, 0);

    gsx_sclip(&d);
    bb_restore(&d);
    gsx_sclip(&t);
    wm_update(END_UPDATE);

    pool_release(mark);
    return (WORD)(i - BUTOFF + 1);
}

/* form_error: the alert for a DOS error number (the donor's fm_error,
 * gemfmlib.c, and its strings from gem_rsc.c).  TRUE when the user
 * pressed anything but the first button, as the donor answers; an
 * error past 63 shows nothing.
 *
 * The texts are LANG.RSC's, copied out of far memory a string at a time
 * (src/aes/lang.c); they were half a kilobyte of C literals until that
 * file existed, which is half a kilobyte bank $00 could not spare
 * either (src/gem4xe.scm: WHAT GOES FAR AND WHAT MUST NOT).
 *
 * The number itself goes into the last alert's text by hand, there
 * being no sprintf in an AES with no libc -- written over the two
 * characters after the '#' rather than at a counted offset, so a
 * translation may put the phrase where it likes as long as it keeps one
 * `#` and two digits after it (tools/langrsc.py says so to whoever
 * translates it). */
WORD fm_error(WORD n)
{
    char *s;
    WORD which;

    if (n > 63)
        return FALSE;
    switch (n) {
    case 2: case 3: case 18:        which = LS_ERRFILE;  break;
    case 4:                         which = LS_ERRDOCS;  break;
    case 5:                         which = LS_ERREXIST; break;
    case 15:                        which = LS_ERRDRIVE; break;
    case 8: case 10: case 11:       which = LS_ERRMEM;   break;
    default:                        which = LS_ERRTOS;   break;
    }
    s = (char *)lang_str(which);
    if (which == LS_ERRTOS) {
        char *hash = strchr(s, '#');
        if (hash && hash[1] && hash[2]) {
            hash[1] = (char)('0' + n / 10);
            hash[2] = (char)('0' + n % 10);
        }
    }
    return fm_alert(1, s) != 1;
}
