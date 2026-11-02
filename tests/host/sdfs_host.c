/* The SDFS engine on the host (tests/host/test_sdfs.py): the same
 * src/sys/sdfs.c GEMDOS runs, against an ATR image held in memory and
 * written back when the commands are done.
 *
 *   sdfs_host IMAGE.atr < COMMANDS
 *
 * One command a line, unit 1 throughout; each answers one line, "ok ..."
 * or "err N" with GEMDOS's error number:
 *
 *   put PATH FILE [CHUNK]   PATH made or emptied, FILE's bytes written,
 *                           CHUNK at a time (1000)
 *   get PATH FILE           PATH's bytes to FILE
 *   pwrite PATH POS FILE    PATH opened to read and write, FILE's bytes
 *                           written at POS
 *   ls PATH                 "ok N", then a line an entry: NAME STATUS SIZE
 *   stat PATH               "ok NAME STATUS SIZE"
 *   mkdir PATH  rmdir PATH  del PATH  ren FROM TO
 *   attr PATH [BITS]        the status, after BITS (hex) if given
 *   space                   "ok FREE TOTAL"
 *   forget                  the cache dropped, as for a disk changed
 *
 * sd_now gives one fixed time, so images come out byte for byte the same.
 * Each command is one operation: sd_recheck before it, as the Atari's
 * src/sys/sdcio.c calls it before each open and each XIO.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sdfs.h"

static uint8_t *img;
static long imglen;
static unsigned secsz;
static long nsec;

static long offset_of(uint16_t sec)
{
    if (sec <= 3)
        return 16 + (long)(sec - 1) * 128;
    if (secsz == 128)
        return 16 + (long)(sec - 1) * 128;
    return 16 + 3 * 128 + (long)(sec - 4) * 256;
}

int16_t sd_dev(SDFS *s, uint8_t unit, uint16_t sec, uint8_t *buf,
               uint16_t len, uint8_t write)
{
    long at;

    (void)s;
    if (unit != 1)
        return SD_EDRIVE;
    if (sec < 1 || sec > nsec)
        return SD_EERROR;
    at = offset_of(sec);
    if (at + len > imglen)
        return SD_EERROR;
    if (write)
        memcpy(img + at, buf, len);
    else
        memcpy(buf, img + at, len);
    return 0;
}

void sd_now(uint8_t *stamp)
{
    static const uint8_t t[6] = { 2, 11, 26, 12, 34, 56 };
    memcpy(stamp, t, 6);
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
    char line[900], cmd[32], a[256], b[256], arg3[256];
    long n, chunk;
    int16_t h, e;
    int32_t r;
    FILE *f;

    if (argc != 2) {
        fprintf(stderr, "usage: sdfs_host IMAGE.atr < COMMANDS\n");
        return 2;
    }
    img = slurp(argv[1], &imglen);
    if (!img || imglen < 16 || img[0] != 0x96 || img[1] != 0x02) {
        fprintf(stderr, "%s: not an ATR image\n", argv[1]);
        return 2;
    }
    secsz = img[4] | (img[5] << 8);
    nsec = secsz == 128 ? (imglen - 16) / 128 : 3 + (imglen - 16 - 384) / 256;
    sd_init(s);

    while (fgets(line, sizeof line, stdin)) {
        int k = sscanf(line, "%31s %255s %255s %255s", cmd, a, b, arg3);
        if (k < 1)
            continue;
        sd_recheck(s, 1);           /* as the Atari does, once an operation */
        if (!strcmp(cmd, "put") && k >= 3) {
            uint8_t *data = slurp(b, &n);
            long done = 0;
            chunk = k >= 4 ? atol(arg3) : 1000;
            if (!data) {
                printf("err -1\n");
                continue;
            }
            h = sd_open(s, 1, a, SD_CREATE);
            if (h < 0) {
                printf("err %d\n", h);
                free(data);
                continue;
            }
            e = 0;
            while (done < n) {
                long m = n - done < chunk ? n - done : chunk;
                r = sd_write(s, h, data + done, (uint32_t)m);
                if (r < 0) {
                    e = (int16_t)r;
                    break;
                }
                done += r;
                if (r < m) {
                    e = SD_EACCDN;
                    break;
                }
            }
            r = sd_close(s, h);
            free(data);
            if (e < 0)
                printf("err %d %ld\n", e, done);
            else if (r < 0)
                printf("err %d\n", (int)r);
            else
                printf("ok %ld\n", done);
        } else if (!strcmp(cmd, "pwrite") && k >= 4) {
            uint8_t *data = slurp(arg3, &n);
            if (!data) {
                printf("err -1\n");
                continue;
            }
            h = sd_open(s, 1, a, SD_RW);
            if (h < 0) {
                printf("err %d\n", h);
                free(data);
                continue;
            }
            r = sd_seek(s, h, (uint32_t)atol(b));
            if (r >= 0)
                r = sd_write(s, h, data, (uint32_t)n);
            e = sd_close(s, h);
            free(data);
            if (r < 0)
                printf("err %d\n", (int)r);
            else if (e < 0)
                printf("err %d\n", e);
            else
                printf("ok %ld\n", (long)r);
        } else if (!strcmp(cmd, "get") && k >= 3) {
            uint8_t *data;
            long len;
            h = sd_open(s, 1, a, SD_READ);
            if (h < 0) {
                printf("err %d\n", h);
                continue;
            }
            len = sd_length(s, h);
            data = malloc(len + 1);
            r = sd_read(s, h, data, (uint32_t)len);
            sd_close(s, h);
            if (r < 0) {
                printf("err %d\n", (int)r);
                free(data);
                continue;
            }
            f = fopen(b, "wb");
            fwrite(data, 1, r, f);
            fclose(f);
            free(data);
            printf("ok %ld\n", (long)r);
        } else if (!strcmp(cmd, "ls") && k >= 1) {
            SD_INFO info;
            static char out[64 * 1024];
            int len = 0, cnt = 0;
            h = sd_opendir(s, 1, k >= 2 ? a : "");
            if (h < 0) {
                printf("err %d\n", h);
                continue;
            }
            while ((e = sd_readdir(s, h, &info)) == 0) {
                len += snprintf(out + len, sizeof out - len, "%s %u %lu\n",
                                info.name, info.status, (unsigned long)info.size);
                cnt++;
            }
            sd_closedir(s, h);
            if (e != SD_ENMFIL)
                printf("err %d\n", e);
            else
                printf("ok %d\n%s", cnt, out);
        } else if (!strcmp(cmd, "stat") && k >= 2) {
            SD_INFO info;
            e = sd_stat(s, 1, a, &info);
            if (e < 0)
                printf("err %d\n", e);
            else
                printf("ok %s %u %lu\n", info.name[0] ? info.name : "\\",
                       info.status, (unsigned long)info.size);
        } else if (!strcmp(cmd, "mkdir") && k >= 2) {
            e = sd_mkdir(s, 1, a);
            printf(e < 0 ? "err %d\n" : "ok\n", e);
        } else if (!strcmp(cmd, "rmdir") && k >= 2) {
            e = sd_rmdir(s, 1, a);
            printf(e < 0 ? "err %d\n" : "ok\n", e);
        } else if (!strcmp(cmd, "del") && k >= 2) {
            e = sd_delete(s, 1, a);
            printf(e < 0 ? "err %d\n" : "ok\n", e);
        } else if (!strcmp(cmd, "ren") && k >= 3) {
            e = sd_rename(s, 1, a, b);
            printf(e < 0 ? "err %d\n" : "ok\n", e);
        } else if (!strcmp(cmd, "attr") && k >= 2) {
            e = sd_attrib(s, 1, a, (uint8_t)(k >= 3), (uint8_t)strtol(b, NULL, 16));
            if (e < 0)
                printf("err %d\n", e);
            else
                printf("ok %d\n", e);
        } else if (!strcmp(cmd, "space")) {
            uint16_t fr, tot;
            e = sd_space(s, 1, &fr, &tot);
            if (e < 0)
                printf("err %d\n", e);
            else
                printf("ok %u %u\n", fr, tot);
        } else if (!strcmp(cmd, "forget")) {
            e = sd_sync(s, 1);
            sd_forget(s, 1);
            printf(e < 0 ? "err %d\n" : "ok\n", e);
        } else
            printf("err -32\n");
        fflush(stdout);
    }
    e = sd_sync(s, 1);
    f = fopen(argv[1], "wb");
    fwrite(img, 1, imglen, f);
    fclose(f);
    return e < 0 ? 1 : 0;
}
