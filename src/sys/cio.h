/* cio.h -- the Atari OS's CIO, from gem4xe.
 *
 * gem4xe has no file system of its own and wants none: DOS is resident,
 * and every disk it can read -- ATR, SIO2SD, a hard disk behind a PBI --
 * is behind CIO's D: device.  What is here is the thin layer over an
 * IOCB: pick a free one, fill it in, call, read the status back.  The
 * call itself is the round trip into emulation mode that the OS needs
 * (src/sys/cio.s), which is why every CIO call costs what a mode switch
 * costs and why the layer above -- rsrc_load, fsel_input, shel_find --
 * reads in big pieces rather than a byte at a time.
 *
 * Addresses are the OS's, as the Altirra source has them
 * (src/h/at/atcore/ksyms.h, cio.h): the IOCBs at $0340, sixteen bytes
 * each, eight of them; IOCB 0 is the OS's own, E:, and is left alone.
 *
 * Buffers and names must be in bank $00 -- CIO takes a 16-bit address.
 * The small data model's plain pointers are bank $00 by construction, so
 * the types say so.  Names are copied into a buffer here with the EOL the
 * OS wants appended; a name without a device ("TEST.RSC") gets "D:".
 *
 * Statuses are the OS's own: 1 is success, $88 end of file, $AA file
 * not found (cio.h in the Altirra source lists them all).  The functions
 * return the status; cio_open returns the IOCB number instead, or the
 * status negated, so that a caller can tell the two apart.
 */
#ifndef GEM4XE_CIO_H
#define GEM4XE_CIO_H

#include "portab.h"
#include <stdint.h>

/* ICCOM */
#define CIO_OPEN     0x03
#define CIO_GETREC   0x05
#define CIO_GETCHR   0x07
#define CIO_PUTREC   0x09
#define CIO_PUTCHR   0x0B
#define CIO_CLOSE    0x0C
#define CIO_STATUS   0x0D

/* ICAX1 at open */
#define CIO_A_READ   0x04
#define CIO_A_DIR    0x06       /* the directory, as lines */
#define CIO_A_RAWDIR 0x14       /* the directory as its own 23-byte
                                   entries, on a SpartaDOS (src/sys/dos.h,
                                   DOS_CAP_RAWDIR) */
#define CIO_A_WRITE  0x08
#define CIO_A_APPEND 0x09
#define CIO_A_UPDATE 0x0C

/* ICSTA */
#define CIO_OK       0x01
#define CIO_OK_EOF   0x03       /* success, and the next read would not be */
#define CIO_E_BREAK  0x80
#define CIO_E_INUSE  0x81
#define CIO_E_NODEV  0x82
#define CIO_E_NOTOPEN 0x85
#define CIO_E_EOF    0x88
#define CIO_E_TRUNC  0x89       /* a record longer than the buffer */
#define CIO_E_NOTFOUND 0xAA

#define CIO_EOL      0x9B

#define CIO_NAME_MAX 63         /* the longest name the buffer holds:
                                   "D8:XXXXXXXX.XXX" is 15, and a
                                   SpartaDOS path is nine more per
                                   directory (src/sys/dos.h); bank $00
                                   is short of room for a longer one */

/* The IOCB the OS lays out at $0340 (ksyms.h). */
typedef struct {
    uint8_t  ichid;             /* $FF when free */
    uint8_t  icdno;
    uint8_t  iccom;
    uint8_t  icsta;
    uint16_t icbal;             /* buffer address */
    uint16_t icptl;
    uint16_t icbll;             /* buffer length; bytes moved on return */
    uint8_t  icax1, icax2, icax3, icax4, icax5, icax6;
} IOCB;

#define CIO_IOCBS   8
#define CIO_IOCB    ((volatile IOCB *)0x0340)

/* Open `name` (NUL-terminated, C style; a missing device becomes D:) with
 * ICAX1 = aux1, ICAX2 = aux2.  Returns the IOCB number, 1..7, or the
 * status negated: -CIO_E_INUSE when no IOCB is free. */
int16_t  cio_open(const char *name, uint8_t aux1, uint8_t aux2);
/* The same file on the IOCB it was on: how a seek backwards is done
 * (src/sys/gemdos.c, gd_seek). */
int16_t  cio_reopen(int16_t iocb, const char *name, uint8_t aux1, uint8_t aux2);
uint8_t  cio_close(int16_t iocb);

/* Up to `len` bytes into `buf`; *got is how many arrived, which is fewer
 * only at the end of the file (the status then says CIO_E_EOF, and the
 * bytes before it are good). */
uint8_t  cio_read(int16_t iocb, void *buf, uint16_t len, uint16_t *got);

/* One EOL-terminated record into `buf`, EOL included, at most `len`
 * bytes; *got as above. */
uint8_t  cio_getrec(int16_t iocb, void *buf, uint16_t len, uint16_t *got);

uint8_t  cio_write(int16_t iocb, const void *buf, uint16_t len);
uint8_t  cio_status(int16_t iocb);
/* A special command on a name -- XIO: delete (33), rename (32, the name
 * "OLD,NEW"), lock and unlock (35, 36), and on a DOS with directories
 * make, remove and change one (42, 43, 44).  A free IOCB is used and
 * given back; the status is returned. */
uint8_t  cio_xio(uint8_t cmd, const char *name, uint8_t aux1, uint8_t aux2);
#define CIO_X_RENAME  32
#define CIO_X_DELETE  33
#define CIO_X_LOCK    35
#define CIO_X_UNLOCK  36
#define CIO_X_MKDIR   42
#define CIO_X_RMDIR   43
#define CIO_X_CHDIR   44

/* The bare call: the IOCB is filled in already.  src/sys/cio.s. */
SIMPLE_CALL uint16_t cio_call(uint16_t iocb);

/* ---- the disk, under the file system ---------------------------------- */
/* One sector, read through the OS's SIO with the DCB in page 3 -- which is
 * the path a PBI hard disk answers on as well as a floppy, so this reaches
 * every drive gem4xe can see.  It is how Dfree learns what a volume has
 * left: the file system's own count, rather than three characters of a
 * directory listing (src/sys/gemdos.c).
 *
 * `buf` must be in bank $00, where the OS can write it.  The answer is the
 * SIO status: 1 is success, and anything else means the drive did not
 * answer -- a virtual drive of the DOS's own, most likely, which is why
 * the caller keeps a path that does not need this. */
#define SIO_OK        0x01
#define SIO_PERCOM_LEN 12       /* the drive's geometry, as it reports it */
uint8_t dsk_read(uint8_t unit, uint16_t sector, void *buf, uint16_t len);
uint8_t dsk_percom(uint8_t unit, void *buf);   /* SIO_PERCOM_LEN bytes */
/* The drive asked for its status, the answer thrown away: SIO_OK or the
 * error, 138 when nobody answered.  One round of the OS's retries. */
uint8_t dsk_status(uint8_t unit);
SIMPLE_CALL uint16_t dsk_call(uint16_t unused);

/* ---- the DOS's kernel, for what CIO has no call for ------------------- */
/* A SpartaDOS kernel function, by number in Y, through the JMP at $0703
 * (SDX User Guide 6.8: `kernel`, with `device` at $0761 set first).  The
 * same round trip as CIO.  The answer is the P register the kernel came
 * back with, so bit 0 is its carry -- which is how a kernel call says
 * "busy" or "no".  Only src/sys/clock.c uses it, for kd_gettd. */
#define DOS_KERNEL     0x0703
#define DOS_DEVICE     0x0761
#define DOS_DATE       0x077B   /* day, month, year (binary; 80.. is 19xx) */
#define DOS_TIME       0x077E   /* hour, minute, second */
#define DOS_KD_GETTD   100      /* the clock, into DOS_DATE and DOS_TIME */
#define DOS_KD_SETTD   101      /* ...and set from them (cc65's
                                 * asminc/atari.inc, SDX_KD_SETTD) */
SIMPLE_CALL uint16_t dos_call(uint16_t fn);

/* ---- SpartaDOS X's entries, by address --------------------------------- */
/* The fourth way in (src/sys/cio.s): a JSR to whatever bank-$00 address
 * sdx_vec holds, A and X from sdx_ax and back into it, and the P it came
 * back with as the result -- for the entries SpartaDOS X names by a
 * symbol (src/sys/dos.c dos_command).  sdx_put is the 6502 routine the
 * DOS's PUT_V points at while a command runs: every byte printed is
 * stored through sdx_put_ptr, a long address bumped as it goes, while
 * sdx_put_left says there is room. */
SIMPLE_CALL uint16_t sdx_call(uint16_t unused);
extern uint16_t sdx_vec, sdx_ax, sdx_put_left;
extern uint8_t  sdx_put[], sdx_put_ptr[3];

extern uint16_t cio_calls;      /* round trips made */
extern uint8_t  cio_env;        /* bisection knobs (src/sys/cio.s): 1 = leave CRITIC alone */
extern uint8_t  cio_last;       /* the last status */

#endif /* GEM4XE_CIO_H */
