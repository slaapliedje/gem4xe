/* gemtime.c -- the kit's clock over GEMDOS.  See include/time.h, which
 * says why the kit has a <time.h> of its own at all (B20: a 64-bit
 * time_t puts every date one division away from executing data).
 *
 * EVERY LINE HERE IS 32-BIT ON PURPOSE.  The civil-date arithmetic is
 * Howard Hinnant's days_from_civil / civil_from_days, which needs only
 * integer division by small constants and no 64-bit intermediate; the
 * same algorithm is in gemstat.c and in gem4xe's own gd_unix, for the
 * same reason and by the same counting.
 */
#include "portab.h"
#include "gem.h"
#include <time.h>
#include <string.h>

#define SECS_PER_DAY  86400UL

/* TWO SHAPES ARE AVOIDED BELOW, and both were measured on this compiler
 * at -O1 and -O2 (they are right at -O0, which is what says it is the
 * optimiser and not the arithmetic -- the same algorithm compiled by gcc
 * agrees with Python on every case tests/host/test_gemtime.py checks):
 *
 *   A COMPARISON USED AS A NUMBER.  `y + (m <= 2)` added 255, not 1: the
 *   compiler had the flag as $00/$FF and never narrowed it.  So every
 *   such test here is an `if`, which is clearer anyway.
 *
 *   A NARROWING STORE THROUGH A POINTER.  `*pm = (uint16_t)(long expr)`
 *   stored 0.  So the results are computed into locals of the wide type
 *   and written out once, at the end, which is also the only order in
 *   which a caller can pass the same address twice safely.
 *
 * Neither is exotic C and neither is in tools/ccbug yet; they are
 * recorded here because the next person to "simplify" these two
 * functions back will get a calendar that is wrong only in a release
 * build.
 */

/* Days since 1970-01-01 from a civil date.  March-based internally, so
 * the leap day is the last of the year and needs no special case. */
static int32_t days_from_civil(int32_t y, uint16_t m, uint16_t d)
{
    int32_t era, yoe, doy, doe, mm = (int32_t)m;

    if (mm <= 2)
        y -= 1;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;                                /* 0..399 */
    doy = (153 * (mm > 2 ? mm - 3 : mm + 9) + 2) / 5 + (int32_t)d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;        /* 0..146096 */
    return era * 146097L + doe - 719468L;
}

/* ...and back. */
static void civil_from_days(int32_t z, int32_t *py, uint16_t *pm, uint16_t *pd)
{
    int32_t era, doe, yoe, y, doy, mp, mon, day;

    z += 719468L;
    era = (z >= 0 ? z : z - 146096L) / 146097L;
    doe = z - era * 146097L;                            /* 0..146096 */
    yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    y = yoe + era * 400;
    doy = doe - (365 * yoe + yoe / 4 - yoe / 100);      /* 0..365 */
    mp = (5 * doy + 2) / 153;                           /* 0..11, March-based */
    day = doy - (153 * mp + 2) / 5 + 1;
    mon = mp < 10 ? mp + 3 : mp - 9;
    if (mon <= 2)
        y += 1;
    *pd = (uint16_t)day;
    *pm = (uint16_t)mon;
    *py = y;
}

/* A GEMDOS date word and time word as seconds since 1970. */
static int32_t dos_unix(UWORD date, UWORD time)
{
    uint16_t y = (uint16_t)(1980 + (date >> 9));
    uint16_t m = (uint16_t)((date >> 5) & 15);
    uint16_t d = (uint16_t)(date & 31);

    if (m < 1 || m > 12)                /* a stamp the DOS never set */
        m = 1;
    if (d < 1)
        d = 1;
    return days_from_civil((int32_t)y, m, d) * (int32_t)SECS_PER_DAY
         + (int32_t)(time >> 11) * 3600L
         + (int32_t)((time >> 5) & 63) * 60L
         + (int32_t)(time & 31) * 2L;
}

time_t time(time_t *tp)
{
    struct timeval tv;
    time_t t;

    /* Tgettimeofday is the kit's one door to a monotonic clock and it
     * already counts from 1970 (gem.h).  A system without it answers a
     * negative code, and then the RTC through Tgetdate/Tgettime is what
     * is left -- two-second resolution, which is what a GEMDOS time word
     * carries anyway. */
    if (Tgettimeofday((struct timeval FAR *)&tv, (struct timezone FAR *)0) >= 0)
        t = (time_t)tv.tv_sec;
    else
        t = (time_t)dos_unix((UWORD)Tgetdate(), (UWORD)Tgettime());
    if (tp)
        *tp = t;
    return t;
}

struct tm *gmtime_r(const time_t *tp, struct tm *r)
{
    int32_t secs = (int32_t)*tp;
    int32_t days = secs / (int32_t)SECS_PER_DAY;
    int32_t rem = secs - days * (int32_t)SECS_PER_DAY;
    int32_t y;
    uint16_t m, d;

    if (rem < 0) {                      /* C's division truncates toward 0 */
        rem += (int32_t)SECS_PER_DAY;
        days--;
    }
    civil_from_days(days, &y, &m, &d);
    r->tm_sec = (int)(rem % 60);
    r->tm_min = (int)((rem / 60) % 60);
    r->tm_hour = (int)(rem / 3600);
    r->tm_mday = (int)d;
    r->tm_mon = (int)m - 1;
    r->tm_year = (int)(y - 1900);
    /* 1970-01-01 was a Thursday, so day 0 is weekday 4. */
    r->tm_wday = (int)((days + 4) % 7);
    if (r->tm_wday < 0)
        r->tm_wday += 7;
    r->tm_yday = (int)(days - days_from_civil(y, 1, 1));
    r->tm_isdst = 0;
    return r;
}

/* The one buffer C allows these to share. */
static struct tm tm_static;

struct tm *gmtime(const time_t *tp)
{
    return gmtime_r(tp, &tm_static);
}

struct tm *localtime_r(const time_t *tp, struct tm *r)
{
    return gmtime_r(tp, r);             /* UTC: see include/time.h */
}

struct tm *localtime(const time_t *tp)
{
    return gmtime_r(tp, &tm_static);
}

time_t mktime(struct tm *tp)
{
    int32_t y = (int32_t)tp->tm_year + 1900;
    int32_t mon = tp->tm_mon;
    int32_t days, secs;

    /* Normalise the month first, so tm_mon = 12 means January next year
     * as C requires. */
    y += mon / 12;
    mon %= 12;
    if (mon < 0) {
        mon += 12;
        y--;
    }
    days = days_from_civil(y, (uint16_t)(mon + 1), (uint16_t)tp->tm_mday);
    secs = days * (int32_t)SECS_PER_DAY
         + (int32_t)tp->tm_hour * 3600L
         + (int32_t)tp->tm_min * 60L
         + (int32_t)tp->tm_sec;
    {   /* ...and hand back the normalised fields, as C requires. */
        time_t t = (time_t)secs;
        gmtime_r(&t, tp);
        return t;
    }
}

/* ---- strftime ----------------------------------------------------------- */

static const char *const wday_abb[7] = {"Sun", "Mon", "Tue", "Wed",
                                        "Thu", "Fri", "Sat"};
static const char *const mon_abb[12] = {"Jan", "Feb", "Mar", "Apr", "May",
                                        "Jun", "Jul", "Aug", "Sep", "Oct",
                                        "Nov", "Dec"};

/* A right-justified unsigned number, `width` wide, padded with `pad`.
 * Writes into `p` and answers where it stopped, or 0 when it would pass
 * `end` -- every caller checks, so a full buffer ends the whole call. */
static char *put_num(char *p, char *end, int32_t v, int width, char pad)
{
    char digits[12];
    int n = 0;

    if (v < 0)
        v = 0;
    do {
        digits[n++] = (char)('0' + (int)(v % 10));
        v /= 10;
    } while (v);
    while (n < width)
        digits[n++] = pad;
    if (p + n > end)
        return 0;
    while (n)
        *p++ = digits[--n];
    return p;
}

static char *put_str(char *p, char *end, const char *s)
{
    while (*s) {
        if (p >= end)
            return 0;
        *p++ = *s++;
    }
    return p;
}

size_t strftime(char *s, size_t max, const char *fmt, const struct tm *tp)
{
    char *p = s;
    char *end = s + (max ? max - 1 : 0);    /* room for the NUL */
    int hour12;

    if (!max)
        return 0;
    while (*fmt) {
        if (*fmt != '%') {
            if (p >= end)
                goto full;
            *p++ = *fmt++;
            continue;
        }
        fmt++;
        switch (*fmt) {
        case 'Y': p = put_num(p, end, tp->tm_year + 1900, 1, '0'); break;
        case 'y': p = put_num(p, end, (tp->tm_year + 1900) % 100, 2, '0'); break;
        case 'm': p = put_num(p, end, tp->tm_mon + 1, 2, '0'); break;
        case 'd': p = put_num(p, end, tp->tm_mday, 2, '0'); break;
        case 'e': p = put_num(p, end, tp->tm_mday, 2, ' '); break;
        case 'H': p = put_num(p, end, tp->tm_hour, 2, '0'); break;
        case 'I':
            hour12 = tp->tm_hour % 12;
            p = put_num(p, end, hour12 ? hour12 : 12, 2, '0');
            break;
        case 'M': p = put_num(p, end, tp->tm_min, 2, '0'); break;
        case 'S': p = put_num(p, end, tp->tm_sec, 2, '0'); break;
        case 'j': p = put_num(p, end, tp->tm_yday + 1, 3, '0'); break;
        case 'p': p = put_str(p, end, tp->tm_hour < 12 ? "AM" : "PM"); break;
        case 'a':
            p = put_str(p, end, wday_abb[tp->tm_wday >= 0 && tp->tm_wday < 7
                                         ? tp->tm_wday : 0]);
            break;
        case 'b':
            p = put_str(p, end, mon_abb[tp->tm_mon >= 0 && tp->tm_mon < 12
                                        ? tp->tm_mon : 0]);
            break;
        case 'n': p = put_str(p, end, "\n"); break;
        case 't': p = put_str(p, end, "\t"); break;
        case '%': p = put_str(p, end, "%"); break;
        case '\0':
            /* a trailing '%': write it and stop */
            if (p >= end)
                goto full;
            *p++ = '%';
            continue;
        default:
            /* Not one of ours.  Copy it through as written, so that a
             * conversion this file does not know shows up in the output
             * instead of disappearing (include/time.h lists the set). */
            if (p + 2 > end)
                goto full;
            *p++ = '%';
            *p++ = *fmt;
            break;
        }
        if (!p)
            goto full;
        fmt++;
    }
    *p = '\0';
    return (size_t)(p - s);

full:
    s[0] = '\0';
    return 0;
}
