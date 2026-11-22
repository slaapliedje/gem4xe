/* minefld.h -- MINES' field, the game without the GEM (src/apps/minefld.c).
 *
 * Portable C, so tests/host/test_mines.py runs the very same file on the
 * host.  The field is globals rather than a struct behind a pointer: the
 * one shape cc65816 5.18 gets wrong silently, P->a = P->b OP e through a
 * near pointer (tools/ccbug, rule 15), cannot be written against them.
 */
#ifndef MINEFLD_H
#define MINEFLD_H

#include <stdint.h>

#define MF_MAXW   30
#define MF_MAXH   16
#define MF_CELLS  480                   /* MF_MAXW * MF_MAXH */

/* A square: its count of mined neighbours, and what is known of it. */
#define MF_COUNT  0x0F
#define MF_MINE   0x10
#define MF_OPEN   0x20
#define MF_FLAG   0x40

/* The game's state. */
#define MF_FRESH   0                    /* no square opened: no mines laid */
#define MF_PLAYING 1
#define MF_WON     2
#define MF_LOST    3

extern uint8_t  mf_cell[MF_CELLS];      /* y * mf_w + x */
extern uint8_t  mf_w, mf_h, mf_state;
extern uint16_t mf_mines;               /* laid, or to be laid */
extern uint16_t mf_flags;               /* flags standing */
extern uint16_t mf_opened;              /* squares open */
extern uint16_t mf_boom;                /* the square that went off */

/* What the last call changed, square by square, for the caller to draw:
 * each square at most once, so the list cannot overflow. */
extern uint16_t mf_dirty[MF_CELLS];
extern uint16_t mf_ndirty;

/* The generator, seeded by the caller: the field is the same for the
 * same seed and the same first square, which is what the tests use. */
void mf_seed(uint32_t seed);

/* A new field, all squares closed; the mines are laid at the first open,
 * clear of that square and, where there is room, of its neighbours --
 * the first click never loses. */
void mf_new(uint8_t w, uint8_t h, uint16_t mines);

/* A square opened: a mine loses; a square with no mined neighbour opens
 * every square round it, and so on outwards.  A flagged or open square
 * is left alone. */
void mf_open(uint8_t x, uint8_t y);

/* A closed square's flag put up or taken down. */
void mf_flag(uint8_t x, uint8_t y);

/* An open square whose number its flags already account for: every other
 * closed square round it opened.  A wrong flag loses here. */
void mf_chord(uint8_t x, uint8_t y);

#endif
