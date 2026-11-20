/* C4's caller, alone so that it is not inlined into main (which is C9):
 * its own first two parameters forwarded as the callee's first two,
 * beside the addresses of six locals */
#include <stdint.h>
typedef short WORD;
int c4_take(uint32_t tree, WORD obj, uint32_t *spec, WORD *state, WORD *type,
            WORD *flags, int *t, WORD *th);
int c4_bug(uint32_t tree, WORD obj, WORD new_state)
{
    WORD flags, type, th, state;
    uint32_t spec;
    int t[4];
    int r = c4_take(tree, obj, &spec, &state, &type, &flags, t, &th);
    return r && state != new_state;
}
