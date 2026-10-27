/* GemARC's codecs: what an ARC archive's members are stored as.
 *
 * Portable C -- the same file is compiled for the Atari and on the host
 * (tests/host/test_gemarc.py) -- with no file of its own: bytes come in
 * through arc_in() and go out through arc_out(), which src/apps/arcfile.c
 * supplies, and the big tables are handed in by arc_tables().  Written
 * from the format, not from anybody's ARC: SEA's ARC 5 and PKWARE's
 * PKARC are the archives, and the methods are these --
 *
 *   1, 2  stored               (1 has the short, ARC 1 header)
 *   3     packed               RLE90: $90 n repeats the last byte n-1 more
 *                              times, $90 0 is a $90
 *   4     squeezed             RLE90, then a Huffman tree in the member
 *   8     crunched             RLE90, then LZW, 9 to 12 bits, a code 256 to
 *                              clear, in Unix compress's bit groups; the
 *                              member starts with its bit count, 12
 *   9     squashed             LZW to 13 bits, no RLE90, no bit count
 *
 * 5 to 7 are ARC 4's own crunching, which nothing in an Atari's archives
 * uses (1,331 of 1,402 members are 8, the rest 2-4): ARC_E_METHOD.
 *
 * What the archive says a member's data was is checked by its CRC-16 --
 * the ARC CRC, $A001 reflected, starting at 0 -- over what comes out. */
#ifndef GEMARC_CODEC_H
#define GEMARC_CODEC_H

#include <stdint.h>

#ifndef FAR
#define FAR
#endif

#define ARC_MARK      0x1A
#define ARC_NAMELEN   13            /* "FILENAME.EXT" and its NUL */
#define ARC_HDR_OLD   25            /* method 1: no original size */
#define ARC_HDR       29

#define ARC_STORED1   1
#define ARC_STORED    2
#define ARC_PACKED    3
#define ARC_SQUEEZED  4
#define ARC_CRUNCHED  8
#define ARC_SQUASHED  9

#define ARC_OK        0
#define ARC_E_METHOD  1             /* a method this does not decode */
#define ARC_E_DATA    2             /* the member's data is not what its
                                       method makes */
#define ARC_E_CRC     3             /* it decoded, and is not what was
                                       stored */
#define ARC_E_WRITE   4             /* the output would not take it */

/* The platform's side (src/apps/arcfile.c). */
int  arc_in(void);                  /* the member's next byte, -1 at its end */
void arc_out(uint8_t c);            /* a byte to wherever output goes */
int  arc_out_failed(void);          /* nonzero once a write has failed */

/* The tables, from the caller: LZW's string table to 13 bits, and the
 * compressor's hash.  ARC_LZW_ENTRIES of each prefix, suffix and stack;
 * ARC_HASH of each hash word and code. */
#define ARC_LZW_ENTRIES 8192
#define ARC_HASH        5003
void arc_tables(uint16_t FAR *prefix, uint8_t FAR *suffix, uint8_t FAR *stack,
                uint32_t FAR *htab, uint16_t FAR *codetab);

uint16_t arc_crc(uint16_t crc, uint8_t c);

/* A member, decoded: arc_in() to arc_out(), the CRC of what came out in
 * *crc.  ARC_OK or the first thing that went wrong. */
int arc_decode(uint8_t method, uint16_t *crc);

/* Making one.  Pass 1 reads the file through arc_in() and counts what
 * each method would make of it, writing nothing; pass 2, over the same
 * bytes again, writes the method chosen through arc_out(). */
typedef struct {
    uint32_t size;                  /* the file */
    uint32_t packed;                /* RLE90 */
    uint32_t crunched;              /* RLE90 and LZW, the bit count byte in */
    uint16_t crc;
} ARC_SIZES;

void    arc_measure(ARC_SIZES *s);
uint8_t arc_choose(const ARC_SIZES *s, uint32_t *csize);
void    arc_encode(uint8_t method);

#endif
