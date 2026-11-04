/* The DOS's commands on the host (tests/host/test_doscmd.py): the same
 * src/sys/doscmd.c and src/sys/sdfs.c the Atari runs, against ATR images
 * held in memory as D1:, D2: ... and written back when the lines are done.
 *
 *   doscmd_host [-c COLS] [-r ROWS] [-k KEYS] [-w N] D1.atr [D2.atr ...] < LINES
 *
 * Each line is run as typed at the prompt, and answered as
 *
 *   $ LINE              the line, after the prompt it was typed at
 *   ...                 what the commands printed, ATASCII's EOL a newline
 *   = N                 dc_run's answer: 0, or the last error
 *
 * More's pause prints "{more}" and takes the next of KEYS (a space when
 * they are used up); a program run prints "{exec Dn:PATH}" and a reboot
 * "{reboot}".  -w N makes DN: write-protected: every write to it is
 * refused, as a drive does with the tab on, or a FujiNet slot mounted
 * read-only.  sd_now gives one fixed time, as in sdfs_host.c.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "doscmd.h"

#define UNITS 8

static struct {
    const char *path;
    uint8_t *img;
    long len;
    unsigned secsz;
    long nsec;
    int wprot;
} d[UNITS];

static const char *keys = "";
static int at_bol = 1;              /* the output is at a line's start */

static long offset_of(int u, uint16_t sec)
{
    if (d[u].secsz == 512)
        return 16 + (long)(sec - 1) * 512;
    if (sec <= 3 || d[u].secsz == 128)
        return 16 + (long)(sec - 1) * 128;
    return 16 + 3 * 128 + (long)(sec - 4) * 256;
}

int16_t sd_dev(SDFS *s, uint8_t unit, uint16_t sec, uint8_t *buf,
               uint16_t len, uint8_t write)
{
    int u = unit - 1;
    long at;

    (void)s;
    if (unit < 1 || unit > UNITS || !d[u].img)
        return SD_EDRIVE;
    if (sec < 1 || sec > d[u].nsec)
        return SD_EERROR;
    at = offset_of(u, sec);
    if (at + len > d[u].len)
        return SD_EERROR;
    if (write && d[u].wprot)
        return SD_EWRPRO;
    if (write)
        memcpy(d[u].img + at, buf, len);
    else
        memcpy(buf, d[u].img + at, len);
    return 0;
}

uint16_t sd_devsec(SDFS *s, uint8_t unit)
{
    (void)s;
    return unit >= 1 && unit <= UNITS && d[unit - 1].img
           ? (uint16_t)d[unit - 1].secsz : 0;
}

void sd_now(uint8_t *stamp)
{
    static const uint8_t t[6] = { 2, 11, 26, 12, 34, 56 };
    memcpy(stamp, t, 6);
}

void dc_out(DC_STATE *h, const char *s, uint16_t n)
{
    uint16_t i;

    (void)h;
    for (i = 0; i < n; i++) {
        uint8_t c = (uint8_t)s[i];
        if (c == DC_EOL)
            putchar('\n');
        else if (c == 0x9C)
            fputs("{del}", stdout);
        else
            putchar(c);
        at_bol = c == DC_EOL;
    }
}

int16_t dc_key(DC_STATE *h)
{
    (void)h;
    if (!*keys)
        return ' ';
    return (uint8_t)*keys++;
}

int16_t dc_exec(DC_STATE *h, uint8_t unit, const char *path)
{
    (void)h;
    printf("{exec D%d:%s}\n", unit, path);
    return 0;
}

int16_t dc_reboot(DC_STATE *h)
{
    (void)h;
    printf("{reboot}\n");
    return 0;
}

static uint8_t *slurp(const char *path, long *n)
{
    FILE *f = fopen(path, "rb");
    uint8_t *b;

    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    *n = ftell(f);
    fseek(f, 0, SEEK_SET);
    b = malloc(*n ? *n : 1);
    if (fread(b, 1, *n, f) != (size_t)*n) {
        fclose(f);
        return NULL;
    }
    fclose(f);
    return b;
}

int main(int argc, char **argv)
{
    SDFS *s = malloc(sizeof(SDFS));
    DC_STATE *h = malloc(sizeof(DC_STATE));
    char line[300];
    int i = 1, u = 0, cols = 38, rows = 0, wp = 0;
    int16_t e;

    for (; i < argc && argv[i][0] == '-'; i += 2) {
        if (i + 1 >= argc)
            break;
        if (!strcmp(argv[i], "-c"))
            cols = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "-r"))
            rows = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "-k"))
            keys = argv[i + 1];
        else if (!strcmp(argv[i], "-w"))
            wp = atoi(argv[i + 1]);
    }
    if (wp >= 1 && wp <= UNITS)
        d[wp - 1].wprot = 1;
    for (; i < argc && u < UNITS; i++, u++) {
        if (!strcmp(argv[i], "-"))      /* an empty drive */
            continue;
        d[u].path = argv[i];
        d[u].img = slurp(argv[i], &d[u].len);
        if (!d[u].img || d[u].len < 16 || d[u].img[0] != 0x96
            || d[u].img[1] != 0x02) {
            fprintf(stderr, "%s: not an ATR image\n", argv[i]);
            return 2;
        }
        d[u].secsz = d[u].img[4] | (d[u].img[5] << 8);
        d[u].nsec = d[u].secsz == 128 ? (d[u].len - 16) / 128
                  : d[u].secsz == 512 ? (d[u].len - 16) / 512
                  : 3 + (d[u].len - 16 - 384) / 256;
    }
    if (!u) {
        fprintf(stderr, "usage: doscmd_host [-c COLS] [-r ROWS] [-k KEYS] "
                "[-w N] D1.atr [D2.atr ...] < LINES\n");
        return 2;
    }
    sd_init(s);
    dc_init(h, s, (uint8_t)cols, (uint8_t)rows);
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\r\n")] = 0;
        dc_prompt(h);
        printf("%s\n", line);
        at_bol = 1;
        e = dc_run(h, line);
        printf("%s= %d\n", at_bol ? "" : "\n", e);
    }
    for (u = 0; u < UNITS; u++) {
        FILE *f;
        if (!d[u].img || d[u].wprot)
            continue;
        sd_sync(s, (uint8_t)(u + 1));
        f = fopen(d[u].path, "wb");
        if (!f || fwrite(d[u].img, 1, d[u].len, f) != (size_t)d[u].len) {
            fprintf(stderr, "%s: cannot write it back\n", d[u].path);
            return 2;
        }
        fclose(f);
    }
    return 0;
}
