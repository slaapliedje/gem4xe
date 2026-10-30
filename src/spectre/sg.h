/* sg.h -- Spectre GS: Apple IIGS Toolbox programs on gem4xe.
 *
 * Spectre GS is an ordinary gem4xe program (SPECTRE.PRG).  It loads an
 * Apple IIGS application -- a GS/OS load file in Object Module Format --
 * relocates it into memory it took from gem4xe, and runs it.  The program
 * calls the Toolbox the way it does on a IIGS, `jsl $E10000` with the call
 * number in X, and the `jml` Spectre GS leaves there brings it here
 * (sgabi.s), where the call is served from Apple's published reference
 * (the Apple IIGS Toolbox Reference, volumes 1-3) -- never from Apple's
 * code.  The program draws into a Super Hi-Res screen kept where a IIGS
 * keeps it, $E1:2000, so a gate can compare it with what Apple's own
 * Toolbox drew on MAME's apple2gs byte for byte (tests/emu/sg1_hello.py).
 *
 * Milestone 1 (docs/spectre.md): the Tool Locator, the Memory Manager,
 * Misc Tools and enough of QuickDraw II to draw rectangles and text.  A
 * call that is not served yet stops the program and says which; nothing
 * is guessed.
 */
#ifndef SG_H
#define SG_H

#include "gem.h"

/* Bank $E1, as the IIGS lays it out: the Toolbox's entry points, then the
 * Super Hi-Res screen -- 200 lines of 160 bytes, the scan-line control
 * bytes, and sixteen palettes of sixteen colours (Hardware Reference,
 * "Super Hi-Res graphics"). */
#define SG_E1       0xE10000UL
#define SG_TOOLS    0xE10000UL      /* jsl here: the Tool Locator */
#define SG_TOOLS2   0xE10004UL      /* ...the same, one return deeper */
#define SG_GSOS     0xE100A8UL      /* jsl here: GS/OS, the call inline */
#define SG_SHR      0xE12000UL
#define SG_SCB      0xE19D00UL
#define SG_PAL      0xE19E00UL
#define SG_SHR_END  0xE1A000UL

#define SG_LINE     160             /* bytes in a line of pixels */
#define SG_LINES    200

/* Why a run ended (sg_run's value, and SPECTRE.PRG's exit code). */
#define SG_QUIT     0x0000          /* the program quit */
#define SG_UNTOOL   0x0001          /* a Toolbox call not served */
#define SG_UNGSOS   0x0002          /* a GS/OS call not served */
#define SG_RTL      0x0003          /* it returned from its entry */

/* The dispatcher's words (sgabi.s), read and written by the C. */
extern uint16_t sg_x;               /* the call: function << 8 | tool set */
extern uint16_t sg_pop;             /* bytes of input the call removes */
extern uint16_t sg_why;             /* SG_*, when sg_abort ends the run */
extern uint16_t sg_what;            /* ...and the call it was */

/* The program, for sg_run. */
extern uint32_t sg_go;              /* its entry */
extern uint16_t sg_prog_d, sg_prog_s, sg_userid;    /* sg_userid: set before sg_load */
extern uint16_t sg_my_d;            /* Spectre's own direct page */

uint16_t sg_run(void);              /* run it; why it ended */
void sg_entry(void);                /* $E1:0000's jml lands here */
void sg_entry2(void);               /* ...$E1:0004's */
void sg_gsos_entry(void);           /* ...$E1:00A8's */
void sg_abort(uint16_t why);        /* end the run now, from a tool */

/* A tool: the caller's input at p (its last-pushed parameter first; the
 * output space above all of them), the error it returns, 0 if none.  It
 * sets sg_pop to the bytes of input it takes off the stack. */
typedef uint16_t (*sg_fn)(uint8_t *p);

uint16_t sg_tool(uint8_t *p);       /* the dispatcher's C half */
uint16_t sg_gsos(uint8_t *p);       /* ...and GS/OS's */

/* Little-endian reads and writes of the caller's stack (bank $00). */
#define SG_W(p, o)      ((uint16_t)((p)[o] | (p)[(o) + 1] << 8))
#define SG_L(p, o)      ((uint32_t)SG_W(p, o) | (uint32_t)SG_W(p, (o) + 2) << 16)
void sg_putw(uint8_t *p, uint16_t v);
void sg_putl(uint8_t *p, uint32_t v);

/* The tool sets (sgtools.c, sgqd.c). */
uint16_t sg_tl(uint8_t fn, uint8_t *p);    /* $01 Tool Locator */
uint16_t sg_mm(uint8_t fn, uint8_t *p);    /* $02 Memory Manager */
uint16_t sg_mt(uint8_t fn, uint8_t *p);    /* $03 Misc Tools */
uint16_t sg_qd(uint8_t fn, uint8_t *p);    /* $04 QuickDraw II */
uint16_t sg_sane(uint8_t fn, uint8_t *p);  /* $0A SANE, housekeeping */
#define SG_NOTYET   0xFFFF                  /* a tool's "not served" */

/* Memory for the program (sgtools.c). */
uint32_t sg_alloc(uint32_t size, uint16_t attr, uint32_t where);
uint32_t sg_handle(uint32_t blk, uint32_t size, uint16_t owner);
extern uint8_t *sg_b0;                       /* the bank $00 arena */
extern uint16_t sg_b0_size;

/* The loader (sgomf.c): the file read, relocated, its entry in sg_go. */
int16_t sg_load(const char *path);

/* The screen, kept at $E1:2000 (sgqd.c). */
void sg_qd_reset(void);

#endif
