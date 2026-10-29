/* EDIT's text engine on the host (tests/host/test_edit.py): the same
 * src/apps/edbuf.c the Atari runs, driven by keys given as arguments.
 *
 *   ed_host IN OUT CAP KEY...
 *
 * IN is loaded into a CAP-byte buffer (the whole file must fit, as on the
 * Atari), each KEY is applied at the cursor, and the text is written to
 * OUT.  Then one line: "lines L eol E len N cur C col K".
 *
 *   t:TEXT  type TEXT, a byte at a time      n   Return
 *   b       Backspace                        x   Delete
 *   l r     left, right                      u d up, down (keeping the column)
 *   h e     the line's start, its end        g:N the cursor to N
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "edbuf.h"

int main(int argc, char **argv)
{
    EDBUF e;
    uint8_t *buf;
    uint16_t cap, cur = 0, goal = 0, n1, n2;
    uint8_t *p2;
    FILE *f;
    long n;
    int i;

    if (argc < 4) {
        fprintf(stderr, "usage: ed_host IN OUT CAP KEY...\n");
        return 2;
    }
    cap = (uint16_t)atoi(argv[3]);
    buf = malloc(cap);
    ed_init(&e, buf, cap);
    f = fopen(argv[1], "rb");
    if (!f)
        return 1;
    n = (long)fread(buf, 1, cap, f);
    if (fgetc(f) != EOF) {
        printf("too big\n");
        return 3;
    }
    fclose(f);
    ed_loaded(&e, (uint16_t)n);
    for (i = 4; i < argc; i++) {
        const char *k = argv[i];
        int keep_goal = 0;

        switch (k[0]) {
        case 't': {
            size_t j;
            for (j = 2; k[j]; j++)
                if (ed_insert(&e, cur, (const uint8_t *)k + j, 1))
                    cur++;
            break;
        }
        case 'n':
            if (ed_newline(&e, cur))
                cur = ed_right(&e, cur);
            break;
        case 'b': cur = ed_del_left(&e, cur); break;
        case 'x': cur = ed_del_right(&e, cur); break;
        case 'l': cur = ed_left(&e, cur); break;
        case 'r': cur = ed_right(&e, cur); break;
        case 'u': cur = ed_up(&e, cur, goal); keep_goal = 1; break;
        case 'd': cur = ed_down(&e, cur, goal); keep_goal = 1; break;
        case 'h': cur = ed_bol(&e, cur); break;
        case 'e': cur = ed_eolpos(&e, cur); break;
        case 'g': cur = (uint16_t)atoi(k + 2); break;
        default:
            fprintf(stderr, "no key %s\n", k);
            return 2;
        }
        if (!keep_goal)
            goal = ed_col(&e, ed_bol(&e, cur), cur);
    }
    f = fopen(argv[2], "wb");
    if (!f)
        return 1;
    ed_span(&e, &n1, &p2, &n2);
    fwrite(buf, 1, n1, f);
    fwrite(p2, 1, n2, f);
    fclose(f);
    printf("lines %u eol %u len %u cur %u col %u\n", e.lines, e.eol,
           ed_len(&e), cur, ed_col(&e, ed_bol(&e, cur), cur));
    return 0;
}
