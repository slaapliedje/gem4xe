/* time.h -- the kit's clock, with a THIRTY-TWO BIT time_t.
 *
 * WHY THIS FILE EXISTS, which is the only interesting thing about it.
 * Calypsi's own <time.h> says `typedef int64_t time_t`, and a 64-bit
 * time_t is a loaded gun on this compiler: _Div64 is eight bytes that
 * end in `clc` and fall through into whatever the linker placed next, so
 * ANY signed 64-bit division executes data (tools/ccbug, B20).  Nothing
 * in the program is near a division -- `(time(NULL) - then) / 60` is
 * enough, and so is asking the C library to format a date, because its
 * localtime() divides a time_t to get the day.
 *
 * That is not a hypothetical.  It killed qed on an Atari, saving a file:
 * the editor asked for the time, Calypsi's localtime() divided, and the
 * machine took a native-mode BRK with the program counter inside a
 * string constant.  This tree had already met the same defect twice and
 * stepped around it both times without naming it -- gemstat.c does its
 * date arithmetic in uint32_t "a 64-bit divide miscompiles here", and
 * gemlib.c's clock() says a 64-bit quotient "answered the dividend".
 * Three local dodges are a sign that the type is wrong, not the code.
 *
 * So the kit takes the type back.  time_t is `long`: 32 bits, seconds
 * since 1970-01-01 UTC, good until 2038 -- which is further away than
 * this machine's RTC can tell you about anyway, since a GEMDOS date
 * carries seven bits of year from 1980 and stops in 2107.  Every
 * function below is 32-bit throughout, so no program that keeps to this
 * header can reach _Div64 through the clock.
 *
 * SHADOWING.  A kit include directory comes before the compiler's own,
 * so this file is the <time.h> an application gets.  That is deliberate
 * and it is also why the declarations here match C's: a program that
 * includes <time.h> and calls localtime() must compile unchanged.
 *
 * WHAT IS NOT HERE.  There is no timezone and no DST: the machine has
 * one clock and no way to know where it is, so localtime() IS gmtime()
 * and both answer UTC.  strftime() takes the conversions listed at its
 * declaration and no others.  difftime(), ctime() and asctime() are
 * absent rather than wrong -- a program that wants them will fail to
 * link, which says more than a stub that lies.
 */
#ifndef GEM4XE_TIME_H
#define GEM4XE_TIME_H

#include <stddef.h>             /* size_t */

typedef long time_t;
typedef long clock_t;

/* The ST's 200 Hz tick, which is what a program written against mintlib
 * scales by.  gemlib.c's clock() answers in these units over
 * Tgettimeofday (gem.h). */
#define CLOCKS_PER_SEC 200

struct tm {
    int tm_sec;                 /* 0-59 (no leap seconds here) */
    int tm_min;                 /* 0-59 */
    int tm_hour;                /* 0-23 */
    int tm_mday;                /* 1-31 */
    int tm_mon;                 /* 0-11 */
    int tm_year;                /* years since 1900 */
    int tm_wday;                /* 0-6, Sunday is 0 */
    int tm_yday;                /* 0-365 */
    int tm_isdst;               /* always 0: there is no DST here */
};

/* Seconds since 1970 UTC from the system clock, and into *tp when tp is
 * not null.  (time_t)-1 if the machine has no clock. */
time_t time(time_t *tp);

/* Broken-down UTC.  localtime is gmtime: see the head of this file. */
struct tm *gmtime(const time_t *tp);
struct tm *gmtime_r(const time_t *tp, struct tm *result);
struct tm *localtime(const time_t *tp);
struct tm *localtime_r(const time_t *tp, struct tm *result);

/* The inverse: a broken-down time back to seconds.  tm_wday and tm_yday
 * are recomputed and the other fields are normalised, as C requires. */
time_t mktime(struct tm *tp);

/* The conversions this one knows -- and it knows no others, copying an
 * unrecognised one through as it stands so a mistake is visible:
 *
 *   %Y  year, all four digits      %y  year within the century, 00-99
 *   %m  month, 01-12               %d  day of the month, 01-31
 *   %e  day of the month, space-padded
 *   %H  hour, 00-23                %I  hour, 01-12
 *   %M  minute, 00-59              %S  second, 00-59
 *   %j  day of the year, 001-366   %p  AM or PM
 *   %a  abbreviated weekday        %b  abbreviated month
 *   %n  newline   %t  tab   %%  a per-cent sign
 *
 * The bytes written, not counting the NUL; 0 (and an unusable buffer) if
 * the result would not fit, as C says. */
size_t strftime(char *s, size_t max, const char *fmt, const struct tm *tp);

clock_t clock(void);

#endif
