/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* gemstat.c -- stat() over GEMDOS.  See include/sys/stat.h.
 *
 * One Fsfirst answers everything a DTA holds: the attribute, the size and
 * the one stamp.  The search uses a DTA of its own and puts the program's
 * back, so a stat() in the middle of somebody's Fsfirst/Fsnext walk does
 * not break the walk (src/sys/gemdos.c keeps a search's state by the DTA
 * that owns it, as the ST does).
 */
#include "portab.h"
#include "gem.h"
#include <sys/stat.h>
#include <errno.h>
#include <string.h>

/* A DOS date and time as seconds since 1970 UTC, in 32-bit arithmetic --
 * a 64-bit divide miscompiles here (tools/ccbug/README.md) and a 32-bit
 * count reaches 2106.  Days from the civil date by the days-from-civil
 * algorithm, the way src/sys/gemdos.c gd_unix counts them. */
static uint32_t dos_unix(UWORD date, UWORD time)
{
    uint32_t y = (uint32_t)1980 + (date >> 9);
    uint32_t m = (date >> 5) & 15;
    uint32_t d = date & 31;
    uint32_t era, yoe, doy, doe, days;

    if (m < 1 || m > 12)                /* a stamp never set */
        m = 1;
    if (d < 1)
        d = 1;
    if (m <= 2)
        y--;
    era = y / 400;
    yoe = y - era * 400;
    doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    days = era * 146097 + doe - 719468;
    return days * 86400UL
         + (uint32_t)(time >> 11) * 3600UL
         + (uint32_t)((time >> 5) & 63) * 60UL
         + (uint32_t)(time & 31) * 2UL;
}

int stat(const char *path, struct stat *st)
{
    DTA dta;
    DTA FAR *was = Fgetdta();
    LONG r;
    uint32_t stamp;
    WORD attr;

    Fsetdta((DTA FAR *)&dta);
    r = Fsfirst(path, FA_RDONLY | FA_HIDDEN | FA_SYSTEM | FA_SUBDIR);
    Fsetdta(was);
    if (r < 0) {
        errno = ENOENT;
        return -1;
    }
    memset(st, 0, sizeof *st);
    attr = (WORD)(unsigned char)dta.d_attrib;
    if (attr & FA_SUBDIR)
        st->st_mode = S_IFDIR | S_IRWXU | S_IRWXG | S_IRWXO;
    else if (attr & FA_RDONLY)
        st->st_mode = S_IFREG | S_IRUSR | S_IRGRP | S_IROTH;
    else
        st->st_mode = S_IFREG | S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH;
    st->st_nlink = 1;
    st->st_size = dta.d_length;
    stamp = dos_unix(dta.d_date, dta.d_time);
    st->st_mtime = (time_t)stamp;
    st->st_atime = (time_t)stamp;
    st->st_ctime = (time_t)stamp;
    st->st_blksize = 256;
    st->st_blocks = (dta.d_length + 255) / 256;
    return 0;
}
