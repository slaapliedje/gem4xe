/* m51_app.c -- the phase 124 gate program: AES 4.0, from the inside.
 *
 * gem4xe reports AES 4.0 since phase 124, and this program makes the calls
 * a program written for 4.0 makes on seeing it, keeping every answer in a
 * global for tests/emu/m51_aes4.py to read by symbol.  It runs from the
 * G4DOS system floppy beside the phase 123 gate accessory (M50.ACC), so
 * that appl_search and appl_find have a second process to find, with two
 * resource files the gate puts beside it: M51E.RSC (EDIT.RSC, a plain
 * resource whose tree 0 is a menu bar) and M51T.RSC (test.rsc, which has
 * colour icons).
 *
 * The AES 4 forms of appl_find -- an upper word of $FFFF or $FFFE -- go
 * through raw(), the kit's own trap with the kit's own arrays: a
 * `const char *` cannot carry a 32-bit value on this machine, so the
 * kit's binding cannot say them, and neither can an unserved opcode.
 */
#include "gem.h"

WORD r_global[15];              /* the global array after appl_init */
WORD r_find[7];                 /* appl_find: NULL, its own name, the
                                 * accessory's, $FFFF|1, $FFFE|0, $FFFF|5
                                 * (nobody), a name nobody has */
WORD r_srch;                    /* processes appl_search listed */
char r_names[4][10];            /* ...their names, types and ids */
WORD r_types[4], r_ids[4];
WORD r_reg;                     /* menu_register(own id, a title) */
WORD r_newname, r_findnew;      /* REG_NEWNAME, and appl_find on it */
WORD r_info[6][5];              /* appl_getinfo 4, 6, 11, 12, 64, AES_CPX */
WORD r_bar[3];                  /* MENU_INQUIRE: before, with its bar, after */
WORD r_rcfix[3];                /* EDIT.RSC: 1; a third resource: 0;
                                 * colour icons: 0 */
WORD r_widths[2];               /* the menu's bar object: rcfix'd, loaded */
WORD r_free;                    /* rsrc_free of the rcfix'd one */
WORD r_top[3];                  /* WF_TOP: top, owner, below */
WORD r_wh[2];
WORD r_bad;                     /* an opcode not served */
WORD r_done;                    /* 1 when every answer is in */
WORD app_quit;                  /* the gate writes 1: end */

static char rsc_e[1600];        /* M51E.RSC's bytes */
static char rsc_t[1500];        /* M51T.RSC's */

static AESPB rpb = { control, global, int_in, int_out, addr_in, addr_out };

static WORD raw(WORD op, WORD nin, WORD nout, WORD nain)
{
    control[0] = op;
    control[1] = nin;
    control[2] = nout;
    control[3] = nain;
    control[4] = 0;
    aes_call(&rpb);
    return int_out[0];
}

static WORD readin(const char *name, char *buf, LONG len)
{
    LONG h = Fopen(name, 0);
    LONG n;

    if (h < 0)
        return 0;
    n = Fread((WORD)h, len, buf);
    Fclose((WORD)h);
    return n > 0;
}

static void info(WORD row, WORD type)
{
    r_info[row][0] = appl_getinfo(type, &r_info[row][1], &r_info[row][2],
                                  &r_info[row][3], &r_info[row][4]);
}

int main(void)
{
    WORD id, i, n, t1, t2, t3, t4, type, pid;
    char name[10];
    OBJECT *t;

    id = appl_init();
    for (i = 0; i < 15; i++)
        r_global[i] = global[i];

    /* appl_find, the kit's way and the raw ways */
    r_find[0] = appl_find(0);
    r_find[1] = appl_find("M51     ");
    r_find[2] = appl_find("M50     ");
    addr_in[0] = (LONG)0xFFFF0001L;
    r_find[3] = raw(13, 0, 1, 1);
    addr_in[0] = (LONG)0xFFFE0000L;
    r_find[4] = raw(13, 0, 1, 1);
    addr_in[0] = (LONG)0xFFFF0005L;
    r_find[5] = raw(13, 0, 1, 1);
    r_find[6] = appl_find("NOBODY  ");

    /* appl_search, before the rename below changes a name */
    n = 0;
    i = appl_search(APP_FIRST, name, &type, &pid);
    while (i && n < 4) {
        for (t1 = 0; t1 < 9; t1++)
            r_names[n][t1] = name[t1];
        r_types[n] = type;
        r_ids[n] = pid;
        n++;
        i = appl_search(APP_NEXT, name, &type, &pid);
    }
    r_srch = n;

    /* menu_register: an application's title takes no Desk slot */
    r_reg = menu_register(id, "  M51 gate");
    r_newname = menu_register(REG_NEWNAME, "RENAMED ");
    r_findnew = appl_find("RENAMED ");

    info(0, AES_PROCESS);
    info(1, AES_INQUIRE);
    info(2, AES_WINDOW);
    info(3, AES_MESSAGE);
    info(4, 64);
    info(5, AES_CPX);

    /* rsrc_rcfix, and the menu bar it holds */
    if (readin("M51E.RSC", rsc_e, sizeof rsc_e)
        && readin("M51T.RSC", rsc_t, sizeof rsc_t)) {
        r_rcfix[0] = rsrc_rcfix(rsc_e);
        if (r_rcfix[0] && rsrc_gaddr(R_TREE, 0, (void **)&t)) {
            r_widths[0] = t[1].ob_width;
            r_bar[0] = menu_bar(0, MENU_INQUIRE);
            menu_bar(t, 1);
            r_bar[1] = menu_bar(0, MENU_INQUIRE);
            menu_bar(t, 0);
            r_bar[2] = menu_bar(0, MENU_INQUIRE);
        }
        if (rsrc_load("M51E.RSC")) {        /* the second, nested */
            OBJECT *t2;
            if (rsrc_gaddr(R_TREE, 0, (void **)&t2))
                r_widths[1] = t2[1].ob_width;
            r_rcfix[1] = rsrc_rcfix(rsc_t); /* a third: refused */
            rsrc_free();
        }
        r_rcfix[2] = rsrc_rcfix(rsc_t);     /* colour icons: refused */
        r_free = rsrc_free();               /* the rcfix'd one */
    }

    /* WF_TOP's three words */
    r_wh[0] = wind_create(NAME, 40, 40, 200, 100);
    r_wh[1] = wind_create(NAME, 80, 60, 200, 100);
    wind_open(r_wh[0], 40, 40, 200, 100);
    wind_open(r_wh[1], 80, 60, 200, 100);
    wind_get(0, WF_TOP, &t1, &t2, &t3, &t4);
    r_top[0] = t1;
    r_top[1] = t2;
    r_top[2] = t3;
    for (i = 1; i >= 0; i--) {
        wind_close(r_wh[i]);
        wind_delete(r_wh[i]);
    }

    r_bad = raw(129, 0, 1, 0);          /* appl_control: not served */
    r_done = 1;

    while (!app_quit)
        evnt_timer(100, 0);
    appl_exit();
    return 0;
}
