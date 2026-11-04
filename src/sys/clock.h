/* clock.h -- the machine's clock, for GEMDOS's Tgetdate and Tgettime.
 *
 * The Atari has no clock of its own.  Two of the cards this machine may
 * have do: the Ultimate 1MB at $D3E2 and the SIDE / SIDE 2 at $D5E2, the
 * same DS1305 wired the same way, bit-banged through that one register
 * (docs/phase15.md).  A machine with neither asks the serial bus, where a
 * FujiNet answers, and then its DOS, which knows any clock it loaded a
 * driver for (a SpartaDOS kernel call, clock.c).  A machine with none of
 * that says so and GEMDOS answers the
 * ST's epoch, 1 January 1980, which is what a TOS with a dead clock
 * answers as well.
 *
 * Which register -- if either -- is settled ONCE, by a READ-ONLY test,
 * before anything is written to it.  The reason is in clock.c and it is
 * not a small one: $D3E2 on a machine without a U1MB is the PIA
 * mirrored, and writing to it stops the mouse.
 */
#ifndef GEM4XE_CLOCK_H
#define GEM4XE_CLOCK_H

#include <stdint.h>

typedef struct {
    uint8_t second, minute, hour;       /* 0-59, 0-59, 0-23 */
    uint8_t day, month;                 /* 1-31, 1-12 */
    uint16_t year;                      /* 1980..2079 */
    uint8_t present;                    /* 0: no clock answered */
} CLOCK;

/* Read it.  Answers 0 and leaves `c` at the epoch when no clock is
 * there -- which is a read of a register no hardware is driving, so what
 * comes back is $FF and fails the check that it is a plausible time. */
uint8_t clock_read(CLOCK *c);

/* Set it, for GEMDOS's Tsetdate and Tsettime: every field of `c`, which
 * the caller has range-checked.  1 when a clock took it; 0 when there is
 * none, or the DOS's driver would not.  The chip is written with its
 * write protect lifted for the moment and put back as it was. */
uint8_t clock_write(const CLOCK *c);

/* Which card the clock is on, for the boot screen: probes if clock_read
 * has not yet. */
#define CLOCK_NONE 0
#define CLOCK_U1MB 1
#define CLOCK_SIDE 2
#define CLOCK_DOS  3                /* whatever the DOS's driver reads */
#define CLOCK_SIO  4                /* an APETime clock: a FujiNet's */
uint8_t clock_card(void);

/* Where to look.  src/gem.c sets it from GEM4XE.CFG before the first
 * read; the numbers are CFG_CLOCK_* in src/sys/config.h and the two
 * lists must agree -- tests/host/test_print.py says so. */
#define CLOCK_HOW_AUTO 0            /* the chips, the bus, then the DOS */
#define CLOCK_HOW_DOS  1            /* the DOS only */
#define CLOCK_HOW_NONE 2            /* nothing: the epoch */
extern uint8_t clock_how;

#endif /* GEM4XE_CLOCK_H */
