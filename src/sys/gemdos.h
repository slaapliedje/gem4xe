/* gemdos.h -- GEMDOS, for the applications: the ST's trap #1 on CIO.
 *
 * GEM on the ST is VDI and AES over GEMDOS, and a GEM application --
 * the Desktop first of all -- asks GEMDOS for its files: Fsfirst and
 * Fsnext to list a directory, Fopen/Fread/Fwrite/Fclose, Dsetpath,
 * Dcreate, Frename, Malloc.  gem4xe has CIO behind it (src/sys/cio.h)
 * and one of three DOSes behind that (src/sys/dos.h), so this is the
 * third face of the ABI (src/sys/abi.h): COP #$44 -- 'D', where the ST
 * has trap #1 -- with X:C at a block laid out as the ST's stack frame is:
 *
 *     +0  LONG  the result, written back
 *     +4  WORD  the function number
 *     +6  ...   the arguments, in the ST's order and sizes (WORD 2,
 *               LONG 4), so that an ST binding's stack picture IS the
 *               block's picture, four bytes along
 *
 * Handles, paths, the DTA and the error numbers are the ST's, so that
 * the donor's desktop code reads unchanged.  What differs is written
 * down, function by function, in gemdos.c: what CIO has no way to do
 * says EINVFN rather than pretending.
 *
 * PATHS.  The application speaks GEM -- A:\DIR\NAME.EXT, or a name
 * relative to a per-drive current directory GEMDOS keeps -- and the
 * DOS seam turns the composed path into what CIO opens.  A drive is a
 * D: unit: A = D1: .. H = D8:.  Where the DOS has no directories, a
 * path with one is EPTHNF.
 *
 * SEARCHES.  Fsfirst opens the directory once and reads as much of it
 * ahead as a bank-$00 buffer allows -- a CIO call costs six frames on
 * a SpartaDOS whether it moves one entry or forty (measured, Phase
 * 14) -- into a slot in far memory keyed by the DTA; Fsnext walks the
 * slot.  Seven slots; an eighth search takes the oldest.  The DTA is
 * the ST's 44 bytes, in the application's memory wherever it says.
 *
 * MEMORY.  Malloc is the far heap (src/sys/farmem.h): the bump
 * allocator, wound back when the application exits.  Each block carries
 * its size, so the LAST one can be given back (Mfree) or cut down
 * (Mshrink) in place, which is all a bump allocator can mean by either;
 * a block below it keeps its memory until the program ends.  Malloc(-1)
 * says how much is left.
 *
 * CHARACTERS.  The ST's six standard handles are here: 0 and 1 the
 * console, 2 aux:, 3 prn:, 4 and 5 nothing.  The console is a VT-52 drawn
 * on GEM's screen (src/sys/con.h) and read from its keyboard; prn: is
 * where GEM4XE.CFG sends the printer (PRINTTO), and nowhere when it says
 * there is no printer; aux: has no device behind it yet.  Fforce points a
 * standard handle at a file or another device and Fdup keeps one to put
 * back, and every C function reads and writes through the handle it is
 * the ST's for -- so a program's Cconws lands in a file once handle 1
 * has been forced onto one.
 *
 * PROCESSES.  Pterm, Pterm0 and Ptermres end the program there and then:
 * the COP does not return to it, and its loader sees the code as it would
 * have seen main()'s (src/sys/abi.s).  Nothing stays resident after
 * Ptermres; there is nothing on this machine for a TSR to hook.  Pexec
 * runs another program and has it back: mode 0, load and go, with the
 * child above its parent in the pool and the far heap and given back
 * when it ends, and what GEMDOS keeps per process -- the handles, the
 * DTA, the name shel_read answers -- the child's while it runs and the
 * parent's again after it.
 */
#ifndef GEM4XE_GEMDOS_H
#define GEM4XE_GEMDOS_H

#include <stdint.h>

/* Function numbers: the ST's. */
#define GD_PTERM0    0x00
#define GD_CCONIN    0x01
#define GD_CCONOUT   0x02
#define GD_CAUXIN    0x03
#define GD_CAUXOUT   0x04
#define GD_CPRNOUT   0x05
#define GD_CRAWIO    0x06
#define GD_CRAWCIN   0x07
#define GD_CNECIN    0x08
#define GD_CCONWS    0x09
#define GD_CCONRS    0x0A
#define GD_CCONIS    0x0B
#define GD_DSETDRV   0x0E
#define GD_CCONOS    0x10
#define GD_CPRNOS    0x11
#define GD_CAUXIS    0x12
#define GD_CAUXOS    0x13
#define GD_DGETDRV   0x19
#define GD_FSETDTA   0x1A
#define GD_SUPER     0x20
#define GD_TGETDATE  0x2A
#define GD_TSETDATE  0x2B
#define GD_TGETTIME  0x2C
#define GD_TSETTIME  0x2D
/* MiNT's: seconds and microseconds, the call a program that wants a real
 * clock makes -- mintlib's gettimeofday tries it first and falls back to
 * _hz_200, which this machine cannot offer (no supervisor mode, no system
 * variable an application may read). */
#define GD_TGETTIMEOFDAY 0x155
/* gem4xe's own, numbered above anything MiNT or MagiC has: the DOS's
 * command processor given a line, and what it printed caught in a far
 * buffer (src/sys/dos.c dos_command).  Psystem in src/app/gem.h. */
#define GD_PSYSTEM   0x1F0
#define GD_FGETDTA   0x2F
#define GD_SVERSION  0x30
#define GD_PTERMRES  0x31
#define GD_DFREE     0x36
#define GD_DCREATE   0x39
#define GD_DDELETE   0x3A
#define GD_DSETPATH  0x3B
#define GD_FCREATE   0x3C
#define GD_FOPEN     0x3D
#define GD_FCLOSE    0x3E
#define GD_FREAD     0x3F
#define GD_FWRITE    0x40
#define GD_FDELETE   0x41
#define GD_FSEEK     0x42
#define GD_FATTRIB   0x43
#define GD_MXALLOC   0x44
#define GD_FDUP      0x45
#define GD_FFORCE    0x46
#define GD_DGETPATH  0x47
#define GD_MALLOC    0x48
#define GD_MFREE     0x49
#define GD_MSHRINK   0x4A
#define GD_PEXEC     0x4B
#define GD_PTERM     0x4C
#define GD_FSFIRST   0x4E
#define GD_FSNEXT    0x4F
#define GD_FRENAME   0x56
#define GD_FDATIME   0x57

/* Errors: the ST's. */
#define GD_ERROR    -1L         /* the generic one: Tsetdate's refusal */
#define GD_EREADF   -11L        /* a read failed partway: Pexec's load */
#define GD_EINVFN   -32L        /* no such function here */
#define GD_EFILNF   -33L        /* file not found */
#define GD_EPTHNF   -34L        /* path not found */
#define GD_ENHNDL   -35L        /* no handle left */
#define GD_EACCDN   -36L        /* access denied: locked, full, exists */
#define GD_EIHNDL   -37L        /* not a handle of ours */
#define GD_ENSMEM   -39L        /* no memory */
#define GD_EIMBA    -40L        /* not a block Malloc gave out */
#define GD_EDRIVE   -46L        /* no such drive */
#define GD_ENMFIL   -49L        /* no more files */
#define GD_ERANGE   -64L        /* a seek past the end of the file */
#define GD_EPLFMT   -66L        /* not a program Pexec can load */
#define GD_EGSBF    -67L        /* Mshrink asked to make a block bigger */

/* What a character call says about a device, and what a program ends
 * with when ^C ends it at the console. */
#define GD_DEV_READY  -1L
#define GD_DEV_BUSY   0L
#define GD_TERM_CTRLC -32
/* Input that will never come -- a forced handle at the end of its file,
 * or aux: with nothing behind it.  The ST hangs there; MiNT answers this,
 * and so does gem4xe. */
#define GD_CEOF     0xFF1AL

/* File attributes, in Fsfirst's mask and the DTA. */
#define FA_RDONLY   0x01
#define FA_HIDDEN   0x02
#define FA_SYSTEM   0x04
#define FA_VOLUME   0x08
#define FA_SUBDIR   0x10
#define FA_ARCHIVE  0x20

/* The DTA: 44 bytes, the ST's layout, the numbers little-endian as the
 * application reads them.  The reserved bytes are GEMDOS's own. */
#define DTA_SIZE    44
#define DTA_ATTRIB  21          /* BYTE */
#define DTA_TIME    22          /* UWORD: h << 11 | m << 5 | s / 2 */
#define DTA_DATE    24          /* UWORD: (y - 1980) << 9 | mo << 5 | d */
#define DTA_LENGTH  26          /* ULONG */
#define DTA_FNAME   30          /* char[14], NAME.EXT */

/* Fopen's modes. */
#define GD_O_READ   0
#define GD_O_WRITE  1
#define GD_O_RDWR   2

/* HANDLES.  0..5 are the standard handles; a file Fopen or Fcreate opens
 * is its IOCB's number plus GD_HANDLE_BASE, 7..13; Fdup's are the four
 * after those.  The devices have handles of their own, the ST's negative
 * ones, which Fopen answers for their names -- "CON:", "AUX:", "PRN:". */
#define GD_STDS        6
#define GD_HANDLE_BASE 6
#define GD_DUP_BASE    14       /* GD_HANDLE_BASE + CIO_IOCBS */
#define GD_DUPS        4
#define GD_HCON       -1
#define GD_HAUX       -2
#define GD_HPRN       -3

/* The call block's size, the largest argument list being Pexec's. */
#define GD_PB_SIZE  20

/* The largest sector gd_dfree will read into the pool: SDFS on a CF card
 * (tools/apt.py) is 512, and nothing gem4xe mounts is bigger. */
#define GD_SECMAX   512

/* Once, after dos_ident and farmem_probe and before any application is
 * loaded: GEMDOS's state is a far allocation that must not be in the
 * region an application's exit winds back. */
void gemdos_init(void);

/* One call: the block at `pb`, the result written into it. */
void gemdos_call(uint32_t pb);

/* The application has exited: its handles closed, its searches freed,
 * the DTA and the standard handles back to the defaults, the printer
 * closed and the console as a program finds it. */
void gemdos_release(void);
/* The current drive and directory as the boot left them: what the
 * shell restores before the desktop runs again. */
void gemdos_home(void);
/* ...and INTO one, which is what shel_wdef's directory names. */
void gemdos_chdir(const char *path);
/* A name the AES opens, resolved through GEMDOS's current
 * directory when there is one (src/sys/gemdos.c). */
void gd_cioname(const char *name, char *cio);

extern uint16_t gemdos_calls;   /* calls made */
extern uint16_t gemdos_bad;     /* of which EINVFN */

#endif /* GEM4XE_GEMDOS_H */
