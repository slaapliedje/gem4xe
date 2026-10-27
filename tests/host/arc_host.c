/* GemARC's engine on the host (tests/host/test_gemarc.py): the same
 * src/apps/arccodec.c and arcfile.c the Atari runs, over stdio.
 *
 *   arc_host l ARCHIVE                 the members, one a line
 *   arc_host x ARCHIVE DIR             every member into DIR/
 *   arc_host a ARCHIVE TEMP DIR/ NAME...   NAMEs from DIR/ put in
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include "arcfile.h"

#define MAXF 16
static FILE *files[MAXF];

int pf_open(const char *name)
{
    int h;
    for (h = 0; h < MAXF && files[h]; h++)
        ;
    if (h == MAXF || !(files[h] = fopen(name, "rb")))
        return -1;
    return h;
}

int pf_create(const char *name)
{
    int h;
    for (h = 0; h < MAXF && files[h]; h++)
        ;
    if (h == MAXF || !(files[h] = fopen(name, "wb")))
        return -1;
    return h;
}

long pf_read(int h, uint8_t *buf, long n)
{
    return (long)fread(buf, 1, (size_t)n, files[h]);
}

long pf_write(int h, const uint8_t *buf, long n)
{
    return (long)fwrite(buf, 1, (size_t)n, files[h]);
}

long pf_seek(int h, long offset)
{
    return fseek(files[h], offset, SEEK_SET) ? -1 : offset;
}

void pf_close(int h)
{
    fclose(files[h]);
    files[h] = 0;
}

int pf_delete(const char *name)
{
    return remove(name);
}

int pf_rename(const char *from, const char *to)
{
    return rename(from, to);
}

void pf_stamp(const char *name, uint16_t *date, uint16_t *time)
{
    struct stat st;
    struct tm *t;
    if (stat(name, &st))
        return;
    t = localtime(&st.st_mtime);
    *date = (uint16_t)(((t->tm_year - 80) << 9) | ((t->tm_mon + 1) << 5) | t->tm_mday);
    *time = (uint16_t)((t->tm_hour << 11) | (t->tm_min << 5) | (t->tm_sec / 2));
}

void pf_setstamp(int h, uint16_t date, uint16_t time)
{
    (void)h; (void)date; (void)time;
}

void arc_progress(const char *name)
{
    (void)name;
}

static uint16_t prefix[ARC_LZW_ENTRIES];
static uint8_t suffix[ARC_LZW_ENTRIES], stack[ARC_LZW_ENTRIES];
static uint32_t htab[ARC_HASH];
static uint16_t codetab[ARC_HASH];
static uint8_t ib[2048], ob[2048];
static ARC_ENTRY list[512];

int main(int argc, char **argv)
{
    uint16_t n, i;
    int r;

    arc_tables(prefix, suffix, stack, htab, codetab);
    arc_buffers(ib, ob, sizeof ib);
    if (argc == 3 && !strcmp(argv[1], "l")) {
        r = arc_list(argv[2], list, 512, &n);
        for (i = 0; i < n; i++)
            printf("%s %u %lu %lu %04X %04X %04X\n", list[i].name,
                   list[i].method, (unsigned long)list[i].csize,
                   (unsigned long)list[i].osize, list[i].crc,
                   list[i].date, list[i].time);
        return r;
    }
    if (argc == 4 && !strcmp(argv[1], "x")) {
        char out[1024];
        int bad = 0;
        r = arc_list(argv[2], list, 512, &n);
        if (r)
            return r;
        for (i = 0; i < n; i++) {
            snprintf(out, sizeof out, "%s/%s", argv[3], list[i].name);
            r = arc_extract(argv[2], &list[i], out);
            printf("%s %d\n", list[i].name, r);
            bad |= r != 0;
        }
        return bad;
    }
    if (argc >= 6 && !strcmp(argv[1], "a")) {
        static char names[ARC_ADD_MAX][ARC_NAMELEN];
        uint16_t c = 0;
        for (i = 5; i < argc && c < ARC_ADD_MAX; i++, c++) {
            strncpy(names[c], argv[i], ARC_NAMELEN - 1);
            names[c][ARC_NAMELEN - 1] = 0;
        }
        r = arc_add(argv[2], argv[3], argv[4], names, c, list, 512);
        printf("add %d\n", r);
        return r;
    }
    fprintf(stderr, "usage: arc_host l|x|a ...\n");
    return 2;
}
