/* runnote.h -- GEM's note to G4DOS's shell: run this plain Atari program,
 * then GEM again (phase 162, docs/run8-plan.md).
 *
 * GEM cannot share the machine with a program written for the Atari
 * itself: such a program loads at $2000 or so, over GEM.  So GEM ends,
 * and asks for itself back.  On G4DOS the asking is this note, in the
 * cassette buffer's tail -- after the shell's own record of where it was
 * (src/shell/shell.c, KEEP), in memory the OS uses only for a cassette:
 *
 *   'R' 'Q'    the mark
 *   step       1: run the program, and leave the note at 2 for the shell
 *              that comes back after it -- or after a RESET.  2: run GEM.
 *   path       the program as the shell's command line takes it,
 *              "D2:\GAMES\X.XEX", NUL-ended
 *   sum        the last byte, over the rest, as the shell's record's is
 *
 * The OS's cold start clears the page, and a program that used it breaks
 * the sum: either way there is no note, and the shell is a prompt.
 * GEM.COM writes it (src/aes/shel.c sh_plain_note) as the last thing it
 * does before it leaves, and SHELL.SYS reads it at once (note_go).
 */
#ifndef GEM4XE_RUNNOTE_H
#define GEM4XE_RUNNOTE_H

#include <stdint.h>

#define NOTE_AT     0x0444          /* $0400 + the shell's 68-byte record */
#define NOTE_LEN    60              /* to $047F, the cassette buffer's end */
#define NOTE_STEP   2
#define NOTE_PATH   3
#define NOTE_ROOM   (NOTE_LEN - NOTE_PATH - 1)  /* the path and its NUL */
#define NOTE_RUN    1
#define NOTE_GEM    2

#define NOTE        ((volatile uint8_t *)NOTE_AT)

/* The sum the note ends in: the shell's record's rotation. */
static uint8_t note_sum(void)
{
    uint16_t i;
    uint8_t s = 0x5A;

    for (i = 0; i < NOTE_LEN - 1; i++)
        s = (uint8_t)((s << 1 | s >> 7) ^ NOTE[i]);
    return s;
}

#endif
