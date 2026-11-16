/* v6_tree.c -- step 3c of docs/6502.md: the object library on a 6502,
 * drawing a tree that is in far memory.  Called by src/v6_vdi.c after
 * gsx_start; banked (section far, with the allocator), because the
 * resident program has no room left.
 *
 * test-m25's dialog, written straight into a far block with OB_SET --
 * the four objects, then the two strings -- the strings' ob_spec far
 * addresses, as rsrc_load leaves a resource's.  Nothing of it is near.
 * Then read back the far heap's own way, ob_draw, and objc_find on the
 * OK button.  Results at $0650 (src/v6_vdi.c says where).
 */
#include "portab.h"
#include "aes/aes.h"
#include "sys/farmem.h"

#define STATUS ((volatile unsigned char *)0x0600)

void v6_tree(void)
{
    static const char title[] = "A GEM dialog";
    static const char okstr[] = "  OK  ";
    static const WORD ob[4][10] = {
        /* next head tail  type      flags                state     x   y    w   h */
        { -1,  1,  3,  G_BOX,    NONE,                 OUTLINED, 30, 100, 160, 46 },
        {  2, -1, -1,  G_STRING, NONE,                 NORMAL,    8,   6,  72,  6 },
        {  3, -1, -1,  G_BOX,    NONE,                 NORMAL,    8,  16, 144,  8 },
        {  0, -1, -1,  G_BUTTON, SELECTABLE | EXIT | DEFAULT | LASTOB,
                                                       NORMAL,   56,  30,  36, 10 },
    };
    OBTREE t;
    uint32_t far, spec[4];
    WORD i;
    volatile uint8_t *at = (volatile uint8_t *)0x0650;

    far = far_alloc(4 * sizeof(OBJECT) + sizeof title + sizeof okstr);
    at[0] = (uint8_t)far;
    at[1] = (uint8_t)(far >> 8);
    at[2] = (uint8_t)(far >> 16);
    at[3] = (uint8_t)(far >> 24);
    if (far) {
        t = (OBTREE)far;
        spec[0] = 0x00021100UL;     /* no char, 2px border, $1100 */
        /* both strings' addresses from a local: cc6502 5.18 compiles
         * `spec[3] = spec[1] + sizeof title` as spec[3] += 13, reading
         * the slot it writes -- whatever the C stack left there.  It
         * passed for as long as the leftover happened to be spec[1]
         * (docs/6502.md, step 4e). */
        {
            uint32_t s1 = far + 4 * sizeof(OBJECT);

            spec[1] = s1;
            spec[2] = 0x00011100UL; /* one pixel of border */
            spec[3] = s1 + sizeof title;
        }
        far_put(spec[1], (const uint8_t *)title, sizeof title);
        far_put(spec[3], (const uint8_t *)okstr, sizeof okstr);
        for (i = 0; i < 4; i++) {
            OB_SET(t, i, ob_next, ob[i][0]);
            OB_SET(t, i, ob_head, ob[i][1]);
            OB_SET(t, i, ob_tail, ob[i][2]);
            OB_SET(t, i, ob_type, ob[i][3]);
            OB_SET(t, i, ob_flags, ob[i][4]);
            OB_SET(t, i, ob_state, ob[i][5]);
            OB_SET(t, i, ob_spec, spec[i]);
            OB_SET(t, i, ob_x, ob[i][6]);
            OB_SET(t, i, ob_y, ob[i][7]);
            OB_SET(t, i, ob_width, ob[i][8]);
            OB_SET(t, i, ob_height, ob[i][9]);
        }

        /* What OB_SET wrote, read back the far heap's own way
         * (far_get, test-f6's) and compared with the table: a count
         * of the objects whose 24 bytes are right, at $0655.  The
         * OB_ accessors writing and reading the same wrong place
         * would draw the dialog all the same. */
        {
            OBJECT o;
            uint8_t good = 0;

            for (i = 0; i < 4; i++) {
                far_get((uint8_t *)&o, far + (uint32_t)i * sizeof(OBJECT), sizeof o);
                if (o.ob_next == ob[i][0] && o.ob_head == ob[i][1]
                    && o.ob_tail == ob[i][2] && o.ob_type == (UWORD)ob[i][3]
                    && o.ob_flags == (UWORD)ob[i][4] && o.ob_state == (UWORD)ob[i][5]
                    && o.ob_spec == spec[i] && o.ob_x == ob[i][6]
                    && o.ob_y == ob[i][7] && o.ob_width == ob[i][8]
                    && o.ob_height == ob[i][9])
                    good++;
            }
            STATUS[0x55] = good;
        }

        STATUS[3] = '9';
        ob_draw(t, 0, MAX_DEPTH);
        /* the OK button's middle: (30 + 56 + 18, 100 + 30 + 5) */
        STATUS[0x54] = (unsigned char)objc_find(t, 0, MAX_DEPTH,
                                                30 + 56 + 18, 100 + 30 + 5);
    }
}
