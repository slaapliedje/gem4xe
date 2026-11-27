/* MINES' field on the host (tests/host/test_mines.py): the same
 * src/apps/minefld.c the Atari runs, driven by moves given as arguments.
 *
 *   mines_host SEED W H MINES MOVE...
 *
 * MOVE is o:X,Y (open), f:X,Y (flag) or c:X,Y (chord).  After each move,
 * one line: "move N state S flags F opened O boom B dirty I,J,...".
 * At the end, the field twice, a row a line: what a player sees
 * ('.' closed, 'F' flag, '0'-'8' open, '*' an open mine), then the truth
 * ('M' a mine, else its count, '-' before the mines are laid).
 */
#include <stdio.h>
#include <stdlib.h>
#include "minefld.h"

int main(int argc, char **argv)
{
    int a, x, y, i;

    if (argc < 5) {
        fprintf(stderr, "usage: mines_host SEED W H MINES MOVE...\n");
        return 2;
    }
    mf_seed((uint32_t)strtoul(argv[1], 0, 0));
    mf_new((uint8_t)atoi(argv[2]), (uint8_t)atoi(argv[3]), (uint16_t)atoi(argv[4]));
    for (a = 5; a < argc; a++) {
        char op = argv[a][0];

        if (sscanf(argv[a] + 2, "%d,%d", &x, &y) != 2)
            return 2;
        if (op == 'o')
            mf_open((uint8_t)x, (uint8_t)y);
        else if (op == 'f')
            mf_flag((uint8_t)x, (uint8_t)y);
        else if (op == 'c')
            mf_chord((uint8_t)x, (uint8_t)y);
        else
            return 2;
        printf("move %d state %d flags %u opened %u boom %u dirty ", a - 5,
               mf_state, mf_flags, mf_opened, mf_boom);
        for (i = 0; i < mf_ndirty; i++)
            printf("%s%u", i ? "," : "", mf_dirty[i]);
        printf("%s\n", mf_ndirty ? "" : "-");
    }
    printf("size %u %u mines %u\n", mf_w, mf_h, mf_mines);
    for (y = 0; y < mf_h; y++) {
        for (x = 0; x < mf_w; x++) {
            uint8_t v = mf_cell[y * mf_w + x];

            if (v & MF_OPEN)
                putchar(v & MF_MINE ? '*' : '0' + (v & MF_COUNT));
            else
                putchar(v & MF_FLAG ? 'F' : '.');
        }
        putchar('\n');
    }
    for (y = 0; y < mf_h; y++) {
        for (x = 0; x < mf_w; x++) {
            uint8_t v = mf_cell[y * mf_w + x];

            if (mf_state == MF_FRESH)
                putchar('-');
            else
                putchar(v & MF_MINE ? 'M' : '0' + (v & MF_COUNT));
        }
        putchar('\n');
    }
    return 0;
}
