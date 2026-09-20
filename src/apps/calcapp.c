/* calcapp.c -- the calculator as a PROGRAM (APPS\\CALC.G4A).
 *
 * The same src/apps/calc.c the accessory is built from, with the main()
 * a launched program wants: take everything, run the one panel, give it
 * all back and return to the desktop.  src/apps/calcacc.c is the other
 * main(), and the difference between them is the whole difference
 * between a program and an accessory.
 *
 * The order is the one it has always had -- appl_init, graf_handle,
 * v_opnvwk, then the resource -- because test-m22 runs this from the
 * desktop and a gate that counts calls should not be made to re-learn
 * them for a refactor.
 */
#include "gem.h"

WORD calc_start(void);
WORD calc_ws(void);
void calc_panel(void);

int main(void)
{
    WORD handle;

    appl_init();
    handle = calc_ws();
    if (!handle || !calc_start()) {
        appl_exit();
        return 1;
    }
    calc_panel();
    rsrc_free();
    v_clsvwk(handle);
    appl_exit();
    return 0;
}
