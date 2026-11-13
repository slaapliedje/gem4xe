/* mkfs_host.c -- src/apps/mkfs.c on the host, for tests/host/test_mkfs.py.
 *
 *   mkfs_host sdfs|dos2 SECSIZE SECTORS [LABEL [STAMP [BAD]]]
 *
 * Every sector the engine writes is printed in the order it writes them,
 * "S <sector> <length> <hex>", and then "R <what it answered>": the test
 * lays them on a blank image of its own and reads that with tools/atr.py.
 * BAD, a sector number, makes the drive's bad list hold that one sector.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mkfs.h"

static int32_t out(void *ctx, uint16_t sec, const uint8_t *buf, uint16_t len)
{
    uint16_t i;

    (void)ctx;
    printf("S %u %u ", sec, len);
    for (i = 0; i < len; i++)
        printf("%02x", buf[i]);
    printf("\n");
    return 0;
}

int main(int argc, char **argv)
{
    static uint8_t buf[512];
    uint8_t bad[4] = { 0xFF, 0xFF, 0xFF, 0xFF };
    MKFS m;
    int32_t r;

    if (argc < 4) {
        fprintf(stderr, "usage: mkfs_host sdfs|dos2 SECSIZE SECTORS [LABEL [STAMP [BAD]]]\n");
        return 2;
    }
    memset(&m, 0, sizeof m);
    m.secsize = (uint16_t)atoi(argv[2]);
    m.sectors = (uint16_t)atoi(argv[3]);
    m.label = argc > 4 ? argv[4] : 0;
    m.stamp = argc > 5 ? (uint16_t)strtoul(argv[5], 0, 0) : 0;
    if (argc > 6) {
        unsigned b = (unsigned)atoi(argv[6]);
        bad[0] = (uint8_t)b;
        bad[1] = (uint8_t)(b >> 8);
    }
    m.bad = bad;
    m.buf = buf;
    m.put = out;
    r = strcmp(argv[1], "sdfs") == 0 ? mkfs_sdfs(&m) : mkfs_dos2(&m);
    printf("R %ld\n", (long)r);
    return 0;
}
