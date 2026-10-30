/* gs.h -- GSlayer: Apple IIGS Toolbox programs on gem4xe.
 *
 * GSlayer is an ordinary gem4xe program (GSLAYER.PRG).  It loads an
 * Apple IIGS application -- a GS/OS load file in Object Module Format --
 * relocates it into memory it took from gem4xe, and runs it.  The program
 * calls the Toolbox the way it does on a IIGS, `jsl $E10000` with the call
 * number in X, and the `jml` GSlayer leaves there brings it here
 * (gsabi.s), where the call is served from Apple's published reference
 * (the Apple IIGS Toolbox Reference, volumes 1-3) -- never from Apple's
 * code.  The program draws into a Super Hi-Res screen kept where a IIGS
 * keeps it, $E1:2000, so a gate can compare it with what Apple's own
 * Toolbox drew on MAME's apple2gs byte for byte (tests/emu/gs1_hello.py).
 *
 * Milestone 1 (docs/gslayer.md): the Tool Locator, the Memory Manager,
 * Misc Tools and enough of QuickDraw II to draw rectangles and text.  A
 * call that is not served yet stops the program and says which; nothing
 * is guessed.
 */
#ifndef GS_H
#define GS_H

#include "gem.h"

/* Bank $E1, as the IIGS lays it out: the Toolbox's entry points, then the
 * Super Hi-Res screen -- 200 lines of 160 bytes, the scan-line control
 * bytes, and sixteen palettes of sixteen colours (Hardware Reference,
 * "Super Hi-Res graphics"). */
#define GS_E1       0xE10000UL
#define GS_TOOLS    0xE10000UL      /* jsl here: the Tool Locator */
#define GS_TOOLS2   0xE10004UL      /* ...the same, one return deeper */
#define GS_GSOS     0xE100A8UL      /* jsl here: GS/OS, the call inline */
#define GS_SHR      0xE12000UL
#define GS_SCB      0xE19D00UL
#define GS_PAL      0xE19E00UL
#define GS_SHR_END  0xE1A000UL

#define GS_LINE     160             /* bytes in a line of pixels */
#define GS_LINES    200

/* Why a run ended (gs_run's value, and GSLAYER.PRG's exit code). */
#define GS_QUIT     0x0000          /* the program quit */
#define GS_UNTOOL   0x0001          /* a Toolbox call not served */
#define GS_UNGSOS   0x0002          /* a GS/OS call not served */
#define GS_RTL      0x0003          /* it returned from its entry */

/* The dispatcher's words (gsabi.s), read and written by the C. */
extern uint16_t gs_x;               /* the call: function << 8 | tool set */
extern uint16_t gs_pop;             /* bytes of input the call removes */
extern uint16_t gs_why;             /* GS_*, when gs_abort ends the run */
extern uint16_t gs_what;            /* ...and the call it was */

/* The program, for gs_run. */
extern uint32_t gs_go;              /* its entry */
extern uint16_t gs_prog_d, gs_prog_s, gs_userid;    /* gs_userid: set before gs_load */
extern uint16_t gs_my_d;            /* GSlayer's own direct page */

uint16_t gs_run(void);              /* run it; why it ended */
void gs_entry(void);                /* $E1:0000's jml lands here */
void gs_entry2(void);               /* ...$E1:0004's */
void gs_gsos_entry(void);           /* ...$E1:00A8's */
void gs_abort(uint16_t why);        /* end the run now, from a tool */

/* A tool: the caller's input at p (its last-pushed parameter first; the
 * output space above all of them), the error it returns, 0 if none.  It
 * sets gs_pop to the bytes of input it takes off the stack. */
typedef uint16_t (*gs_fn)(uint8_t *p);

uint16_t gs_tool(uint8_t *p);       /* the dispatcher's C half */
uint16_t gs_gsos(uint8_t *p);       /* ...and GS/OS's */

/* Little-endian reads and writes of the caller's stack (bank $00). */
#define GS_W(p, o)      ((uint16_t)((p)[o] | (p)[(o) + 1] << 8))
#define GS_L(p, o)      ((uint32_t)GS_W(p, o) | (uint32_t)GS_W(p, (o) + 2) << 16)
void gs_putw(uint8_t *p, uint16_t v);
void gs_putl(uint8_t *p, uint32_t v);

/* The tool sets (gstools.c, gsqd.c). */
uint16_t gs_tl(uint8_t fn, uint8_t *p);    /* $01 Tool Locator */
uint16_t gs_mm(uint8_t fn, uint8_t *p);    /* $02 Memory Manager */
uint16_t gs_mt(uint8_t fn, uint8_t *p);    /* $03 Misc Tools */
uint16_t gs_qd(uint8_t fn, uint8_t *p);    /* $04 QuickDraw II */
uint16_t gs_sane(uint8_t fn, uint8_t *p);  /* $0A SANE, housekeeping */
#define GS_NOTYET   0xFFFF                  /* a tool's "not served" */

/* Memory for the program (gstools.c). */
uint32_t gs_alloc(uint32_t size, uint16_t attr, uint32_t where);
uint32_t gs_handle(uint32_t blk, uint32_t size, uint16_t owner);
extern uint8_t *gs_b0;                       /* the bank $00 arena */
extern uint16_t gs_b0_size;

/* The loader (gsomf.c): the file read, relocated, its entry in gs_go. */
int16_t gs_load(const char *path);

/* The screen, kept at $E1:2000 (gsqd.c). */
void gs_qd_reset(void);

#endif
