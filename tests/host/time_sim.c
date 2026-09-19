/* time_sim.c -- drive src/app/gemtime.c under Calypsi's own simulator.
 *
 * The kit's <time.h> exists to keep a 32-bit time_t (ccbug B20), and a
 * calendar written twice -- once here and once in the C library -- is
 * only worth having if it agrees with everybody else's.  So this file
 * runs a spread of timestamps through gmtime_r, mktime and strftime and
 * publishes what came out; tests/host/test_gemtime.py compares every
 * field against Python's datetime, which is the reference.
 *
 * The three GEMDOS calls gemtime.c makes are stubbed here, so nothing
 * needs a machine: Tgettimeofday answers a fixed second, and the RTC
 * pair answers a known date so that time()'s FALLBACK path is exercised
 * too -- that path is the one a system without the MiNT clock takes and
 * it would otherwise never be run by anything.
 */
#include "portab.h"
#include "gem.h"
#include <time.h>
#include <string.h>

/* ---- the stubs ---------------------------------------------------------- */

LONG tsim_gtod_rc = 0;              /* >= 0: Tgettimeofday answers */
LONG tsim_gtod_sec = 1000000000L;   /* 2001-09-09 01:46:40 UTC */

LONG Tgettimeofday(struct timeval FAR *tv, struct timezone FAR *tz)
{
    (void)tz;
    if (tsim_gtod_rc < 0)
        return tsim_gtod_rc;
    tv->tv_sec = tsim_gtod_sec;
    tv->tv_usec = 0;
    return 0;
}

/* 2026-09-19, 14:30:20 -- a GEMDOS date word is (y-1980)<<9 | m<<5 | d
 * and a time word is h<<11 | m<<5 | s/2. */
WORD Tgetdate(void) { return (WORD)(((2026 - 1980) << 9) | (9 << 5) | 19); }
WORD Tgettime(void) { return (WORD)((14 << 11) | (30 << 5) | (20 / 2)); }

/* ---- what the test reads ------------------------------------------------ */

#define NCASES 14

/* The timestamps, chosen for the edges a calendar gets wrong: the epoch,
 * both sides of a leap day in a leap year and in a century year, the
 * turns of years, and the ends of the 32-bit range. */
const long tsim_in[NCASES] = {
             0L,          /* 1970-01-01 00:00:00 Thursday */
         86399L,          /* the last second of that day */
      68256000L,          /* 1972-02-29, a leap day */
      68342400L,          /* 1972-03-01, the day after */
     951782400L,          /* 2000-02-29, the century that IS a leap year */
     951868800L,          /* 2000-03-01 */
    1078012800L,          /* 2004-02-29 */
     946684799L,          /* 1999-12-31 23:59:59 */
     946684800L,          /* 2000-01-01 00:00:00 */
    1789828220L,          /* 2026-09-19 14:30:20, the RTC stub's date */
    2147483647L,          /* the last second a 32-bit signed time_t holds */
    -1L,                  /* one second before the epoch: 1969-12-31 */
    -86400L,              /* 1969-12-31 00:00:00 */
   -2147483648L,          /* the first second it holds: 1901-12-13 */
};

/* seven fields per case: year, mon, mday, hour, min, sec, wday, yday */
short tsim_out[NCASES * 8];
long  tsim_back[NCASES];            /* mktime(gmtime(t)) -- must be t */
char  tsim_us[24], tsim_de[24], tsim_iso[24], tsim_hms[24], tsim_mix[40];
short tsim_trunc;                   /* strftime into a buffer too small: 0 */
short tsim_truncbuf;                /* ...and it left the buffer unusable */
long  tsim_time_gtod, tsim_time_rtc;
short tsim_ran;

int main(void)
{
    struct tm tm;
    short i;
    time_t t;

    for (i = 0; i < NCASES; i++) {
        t = (time_t)tsim_in[i];
        gmtime_r(&t, &tm);
        tsim_out[i * 8 + 0] = (short)(tm.tm_year + 1900);
        tsim_out[i * 8 + 1] = (short)(tm.tm_mon + 1);
        tsim_out[i * 8 + 2] = (short)tm.tm_mday;
        tsim_out[i * 8 + 3] = (short)tm.tm_hour;
        tsim_out[i * 8 + 4] = (short)tm.tm_min;
        tsim_out[i * 8 + 5] = (short)tm.tm_sec;
        tsim_out[i * 8 + 6] = (short)tm.tm_wday;
        tsim_out[i * 8 + 7] = (short)tm.tm_yday;
        tsim_back[i] = (long)mktime(&tm);       /* must come back unchanged */
    }

    /* The four formats qed asks for (src/global.c), on the RTC date. */
    t = (time_t)1789828220L;
    gmtime_r(&t, &tm);
    strftime(tsim_us, sizeof tsim_us, "%m/%d/%Y", &tm);
    strftime(tsim_de, sizeof tsim_de, "%d.%m.%Y", &tm);
    strftime(tsim_iso, sizeof tsim_iso, "%Y-%m-%d", &tm);
    strftime(tsim_hms, sizeof tsim_hms, "%H:%M:%S", &tm);
    strftime(tsim_mix, sizeof tsim_mix, "%a %b %e %I%p j=%j %% %q", &tm);

    /* A buffer that cannot hold the result: C says 0, and says nothing
     * about the buffer, so this one empties it. */
    tsim_trunc = (short)strftime(tsim_us + 12, 4, "%Y-%m-%d", &tm);
    tsim_truncbuf = (short)tsim_us[12];

    tsim_gtod_rc = 0;
    tsim_time_gtod = (long)time((time_t *)0);
    tsim_gtod_rc = -32;                         /* EINVFN: no MiNT clock */
    tsim_time_rtc = (long)time((time_t *)0);

    tsim_ran = 1;
    return 0;
}
