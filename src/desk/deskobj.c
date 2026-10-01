/* deskobj.c -- the desktop's screen tree.
 *
 * The donor's deskobj.c: one OBJECT array holds the desk, the window
 * boxes and every item, and the items not in use hang on a free chain
 * through ob_next.  A window's items are freed by moving the whole
 * chain of them to the head of the free chain -- one relink, however
 * many there are.
 */
#include "portab.h"
#include "desk.h"

static const OBJECT gl_sampob[2] = {
    { NIL, NIL, NIL, G_IBOX, NONE, NORMAL, 0L,        0, 0, 0, 0 },
    { NIL, NIL, NIL, G_BOX,  NONE, NORMAL, WINDOW_SPEC, 0, 0, 0, 0 },
};

static void r_set(OBJECT *obj, WORD x, WORD y, WORD w, WORD h)
{
    obj->ob_x = x;
    obj->ob_y = y;
    obj->ob_width = w;
    obj->ob_height = h;
}

/* The AES's objc_add: link obj as the last child of parent. */
static void obj_add(OBJECT *tree, WORD parent, WORD obj)
{
    OBJECT *pp = &tree[parent];
    WORD last = pp->ob_tail;

    tree[obj].ob_next = parent;
    if (last == NIL)
        pp->ob_head = obj;
    else
        tree[last].ob_next = obj;
    pp->ob_tail = obj;
}

/* Every non-item object with its links cut, the items chained free,
 * ROOT a G_IBOX over the whole screen, DROOT and the window boxes
 * zero-size children of it. */
void obj_init(void)
{
    WORD i;
    OBJECT *obj;

    for (i = 0, obj = G.g_screen; i < WOBS_START; i++, obj++)
        obj->ob_head = obj->ob_next = obj->ob_tail = NIL;
    for (; i < NUM_SOBS - 1; i++, obj++)
        obj->ob_next = (WORD)(i + 1);
    obj->ob_next = NIL;
    G.g_screenfree = WOBS_START;

    G.g_screen[ROOT] = gl_sampob[0];
    r_set(&G.g_screen[ROOT], 0, 0,
          (WORD)(G.g_desk.g_x + G.g_desk.g_w), (WORD)(G.g_desk.g_y + G.g_desk.g_h));
    for (i = 0, obj = &G.g_screen[DROOT]; i < NUM_WNODES + 1; i++, obj++) {
        *obj = gl_sampob[1];
        obj_add(G.g_screen, ROOT, (WORD)(DROOT + i));
    }
}

/* A window object: the first one with no size, from DROOT+1. */
WORD obj_walloc(WORD x, WORD y, WORD w, WORD h)
{
    WORD i;
    OBJECT *obj;

    for (i = DROOT + 1, obj = &G.g_screen[i]; i < WOBS_START; i++, obj++) {
        if (!(obj->ob_width && obj->ob_height)) {
            r_set(obj, x, y, w, h);
            return i;
        }
    }
    return 0;
}

/* Resize a window object and free its children; a zero size frees it. */
void obj_wfree(WORD obj, WORD x, WORD y, WORD w, WORD h)
{
    OBJECT *window = &G.g_screen[obj];
    OBJECT *item;
    WORD i, oldfree;

    r_set(window, x, y, w, h);
    if (window->ob_head >= WOBS_START) {
        oldfree = G.g_screenfree;
        G.g_screenfree = window->ob_head;
        for (i = window->ob_head; ; i = item->ob_next) {
            item = &G.g_screen[i];
            if (item->ob_next < WOBS_START) {  /* the last child: it links to the parent */
                item->ob_next = oldfree;
                break;
            }
        }
    }
    window->ob_head = window->ob_tail = NIL;
}

/* An item at x/y/w/h under wparent, off the free chain: its number, or
 * 0 when there is none left. */
WORD obj_ialloc(WORD wparent, WORD x, WORD y, WORD w, WORD h)
{
    WORD objnum = G.g_screenfree;
    OBJECT *obj;

    if (objnum < WOBS_START)
        return 0;
    obj = &G.g_screen[objnum];
    G.g_screenfree = obj->ob_next;
    obj->ob_next = obj->ob_head = obj->ob_tail = NIL;
    obj_add(G.g_screen, wparent, objnum);
    r_set(obj, x, y, w, h);
    return objnum;
}

/* THE DRIVES ARE D1: TO D8:, WHERE A PERSON READS THEM, and A: to H:
 * underneath, where GEMDOS and every ST program read them (phase 73).  An
 * icon shows its drive's digit and a label that says "D1:"; the letter
 * a path wants is recovered here, so nothing that builds a path has to
 * know which the icon shows.  0 for an icon that is not a drive. */
WORD icon_letter(WORD obj)
{
    WORD c = (WORD)(obj_info(obj)->i.blk.ib_char & 0xFF);

    if (c >= '1' && c <= '8')
        return (WORD)('A' + c - '1');
    if (c >= 'A' && c <= 'P')
        return c;
    return 0;
}

/* A path as it is shown: "A:\GEM" as "D1:\GEM", anything else as it is.
 * At most n bytes go into d, the NUL among them; d's end is returned. */
char *drv_show(char *d, const char *path, WORD n)
{
    char *end = d + n - 1;

    if (path[0] >= 'A' && path[0] <= 'H' && path[1] == ':' && n > 3) {
        *d++ = 'D';
        *d++ = (char)('1' + path[0] - 'A');
        path++;
    }
    while (*path && d < end)
        *d++ = *path++;
    *d = 0;
    return d;
}

/* The desk icon of a drive letter, or 0. */
WORD obj_get_obid(WORD drive)
{
    WORD objnum;

    for (objnum = G.g_screen[DROOT].ob_head; objnum >= WOBS_START;
         objnum = G.g_screen[objnum].ob_next) {
        if ((G.g_screen[objnum].ob_type == G_ICON || G.g_screen[objnum].ob_type == G_CICON)
            && icon_letter(objnum) == drive)
            return objnum;
    }
    return 0;
}

SCREENINFO *obj_info(WORD obj)
{
    return &G.g_screeninfo[obj - WOBS_START];
}

/* The store an item object's ob_spec points into, emptied before it is
 * written.  The two halves of the union are different lengths and an
 * item slot is reused in both views, so without this what a slot holds
 * past its own text is what the LAST item to use it left there -- and
 * G is compared with the model byte for byte (tests/emu/m17_desktop.py),
 * which makes residue a thing that has to be modelled rather than a
 * thing nobody sees. */
static void obj_clear(SCREENINFO *si)
{
    char *p = si->line;
    WORD i;

    for (i = 0; i < (WORD)sizeof(SCREENINFO); i++)
        p[i] = 0;
}

/* An icon item under wparent at (x, y): a copy of the resource's
 * ICONBLK with the label and the letter, the image centred in the cell
 * -- the donor's app_blddesk for one ANODE, and win_bldview for one
 * FNODE.  0 when the items are all in use. */
WORD obj_icon(WORD wparent, WORD x, WORD y, WORD which,
              const char FAR *label, WORD letter)
{
    WORD obid;
    OBJECT *pob;
    SCREENINFO *si;
    ICONBLK *pic;
    char *d;

    obid = obj_ialloc(wparent, x, y, G.g_wicon, G.g_hicon);
    if (!obid)
        return 0;
    pob = &G.g_screen[obid];
    pob->ob_state = NORMAL;
    pob->ob_flags = NONE;
    pob->ob_type = G_ICON;
    si = obj_info(obid);
    obj_clear(si);
    pic = &si->i.blk;
    if (G.g_cicon && G.g_cicon[which].col4) {
        /* DESKICON.RSC's (desktop.c, desk_cicons): drawn in colour */
        *pic = G.g_cicon[which].ib;
        si->i.col4 = G.g_cicon[which].col4;
        si->i.sel4 = G.g_cicon[which].sel4;
        pob->ob_type = G_CICON;
    } else {
        *pic = G.a_iblist[which];
    }
    pob->ob_spec.index = (LONG)(uint32_t)pic;
    pic->ib_xicon = (WORD)((G.g_wicon - pic->ib_wicon) / 2);
    pic->ib_ytext = pic->ib_hicon;
    pic->ib_wtext = (WORD)(MAX_ICONTEXT_WIDTH * G.g_wchar);
    pic->ib_htext = (WORD)(G.g_hchar + 2);
    if (letter >= 'A' && letter <= 'H')         /* the digit, D1:'s 1 */
        letter = (WORD)('1' + letter - 'A');
    pic->ib_char = (WORD)((pic->ib_char & 0xFF00) | letter);
    d = si->i.label;
    while (*label && d < si->i.label + LABEL_LEN - 1)
        *d++ = *label++;
    *d = 0;
    pic->ib_ptext = (LONG)(uint32_t)si->i.label;
    return obid;
}

/* An item object for the TEXT view: a G_STRING over the line, which the
 * caller fills in place (deskwin.c win_line) rather than handing over,
 * so that no 48-byte copy of it stands on the desktop's stack.  0 when
 * the items are all in use, as obj_icon's is. */
WORD obj_text(WORD wparent, WORD x, WORD y, WORD w, WORD h)
{
    WORD obid = obj_ialloc(wparent, x, y, w, h);
    OBJECT *pob;
    SCREENINFO *si;

    if (!obid)
        return 0;
    pob = &G.g_screen[obid];
    pob->ob_state = NORMAL;
    pob->ob_flags = NONE;
    pob->ob_type = G_STRING;
    si = obj_info(obid);
    obj_clear(si);
    pob->ob_spec.index = (LONG)(uint32_t)si->line;
    return obid;
}
