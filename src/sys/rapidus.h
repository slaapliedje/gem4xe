/* rapidus.h -- the accelerator's speed map for bank $00.
 *
 * A Rapidus runs its 65C816 at ~20 MHz from its own SDRAM, but bank $00 is
 * the motherboard's 64 KB, and every access to it waits for the 1.79 MHz bus
 * -- unless the board's SRAM is switched in over it.  The Memory Control
 * Register in bank $FF divides bank $00 into four 16 KB windows, each either
 * SLOW (reads and writes go to the motherboard) or FAST (reads come from a
 * copy in SRAM).  Write-through keeps the copy coherent: with it on, a write
 * lands in both, at motherboard speed.  For $0000-$3FFF alone, CMCR bit 6
 * drops the write-through, so writes there are fast too and the motherboard
 * copy goes stale.
 *
 * The board comes up with every window slow, and gem4xe ran that way through
 * six phases without knowing: the code was in fast SDRAM, but under the small
 * data model every global, the stack and the direct page are in bank $00, so
 * a glyph blit that should take microseconds took 6 ms.  It surfaced as
 * form_do missing the second click of a double-click.
 *
 * WHICH WINDOWS GO FAST is not written down here; it follows from the map:
 *   - the window(s) holding the VBXE MEMAC window MUST stay slow.  MEMAC
 *     substitutes VRAM for motherboard RAM on the bus; a fast window never
 *     reaches the bus and would read the SRAM copy instead of VRAM.
 *   - $C000-$FFFF is left as found by THIS file: OS ROM and hardware.
 *     src/sys/irq.c switches it fast once its SRAM holds the RAM copy of
 *     the OS with the native-mode vectors patched, and back on exit.
 *   - $0000-$3FFF drops write-through only if the linker really did put the
 *     direct page, the stack and the data there -- checked, not assumed.
 *   - everything else goes fast-read, coherent by write-through.
 *
 * COHERENCE: if write-through was OFF when this runs, the SRAM copy of a slow
 * window may be stale (DOS loaded the program with the CPU, and those writes
 * only reached the motherboard).  Each window about to go fast is then
 * re-synced by copying it onto itself with write-through on and the window
 * still slow: reads come from the motherboard, writes land in both.
 *
 * THE WAY BACK: once $0000-$3FFF stops writing through, the motherboard
 * copy of the OS variables, DOS and the direct page is stale.  A return to
 * DOS in 6502 mode has to write it back first -- rapidus_restore() clears
 * CMCR bit 6 and copies the window onto itself again, then puts the MCR's
 * speed bits back as they were found.  sys_exit() (src/crt_atari.s) is the
 * only caller, after irq_remove() has given the OS ROM back.
 */
#ifndef GEM4XE_RAPIDUS_H
#define GEM4XE_RAPIDUS_H

#include <stdint.h>

/* The bank $FF register file, reachable only from the 65C816.  Semantics as
 * Altirra's rapidus.cpp implements them; no public register document exists. */
#define RAP_SIG      0xFF0000UL     /* "6S9038E " */
#define RAP_MCR      0xFF0080UL     /* Memory Control Register */
#define RAP_CMCR     0xFF0081UL     /* Complementary MCR */

#define MCR_SLOW0    0x01           /* $0000-$3FFF on the motherboard bus */
#define MCR_SLOW1    0x02           /* $4000-$7FFF */
#define MCR_SLOW2    0x04           /* $8000-$BFFF */
#define MCR_SLOW3    0x08           /* $C000-$FFFF */
#define MCR_SLOWALL  0x0F
#define MCR_WRTHRU   0x20           /* fast windows write through to the bus */
#define MCR_IO       0x40           /* $D000-$D7FF is hardware */
#define MCR_BASEOS   0x80           /* $C000-$FFFF is the Atari OS ROM */
#define CMCR_FAST0   0x40           /* $0000-$3FFF: no write-through */

#define RAP_WIN(a)   ((uint8_t)((uint16_t)(a) >> 14))   /* window of an address */

typedef struct {
    uint8_t present;        /* signature seen; the rest is meaningless if 0 */
    uint8_t mcr_before;
    uint8_t mcr_after;
    uint8_t cmcr_after;
    uint8_t synced;         /* bit per window re-synced before going fast */
    uint8_t cmcr_before;    /* the CMCR as found: with mcr_before, the
                               firmware's setup, which the boot screen shows */
} RAPIDUS;

extern RAPIDUS rapidus;

/* Configure the speed map as described above.  Call before vbxe_init() maps
 * the MEMAC window -- a re-sync copies the window onto itself, which must be
 * plain RAM at the time -- and before anything timing-sensitive. */
void rapidus_speedup(void);

/* Undo it: write $0000-$3FFF back and restore the MCR's speed bits.  For the
 * return to DOS only; nothing is fast afterwards. */
void rapidus_restore(void);

/* BANKWINDOW=SLOW in GEM4XE.CFG (src/sys/config.c): $4000-$7FFF, where an
 * XE's extra memory banks appear, back on the motherboard bus after the
 * speed-up made it fast.  For finding out whether a DOS that banks there
 * (SpartaDOS X, USE BANKED) and the fast copy disagree on a real card;
 * Altirra's card hands the window to the bank whenever one is in. */
void rapidus_slow_bank(void);

/* The register file, for src/sys/irq.c's window 3 switch. */
uint8_t rapidus_reg_read(uint32_t a);
void    rapidus_reg_write(uint32_t a, uint8_t v);

#endif /* GEM4XE_RAPIDUS_H */
