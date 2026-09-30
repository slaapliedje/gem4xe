/* irq.h -- native-mode interrupts on an Atari that never expected them.
 *
 * THE PROBLEM.  In native mode the 65816 takes its vectors from $FFE4-$FFEF
 * (COP, BRK, ABORT, NMI, -, IRQ), and the Atari OS ROM only fills the
 * emulation-mode set at $FFFA-$FFFF: the XL OS has $0000 at $FFEA.  So since
 * Phase 0 gem4xe has run with NMIEN and IRQEN off (src/crt_atari.s), polling
 * the keyboard and the pointer from the main line, and counting time by
 * watching VCOUNT wrap.  That was enough for the gates and useless for the
 * one device people actually plug in: a quadrature mouse loses counts unless
 * it is sampled thousands of times a second.
 *
 * THE FIX.  The ROM is copied into the RAM that sits under it.  On any
 * XL/XE, PORTB bit 0 low swaps the OS ROM out for RAM at $C000-$CFFF and
 * $D800-$FFFF ($D000-$D7FF stays hardware); the copy is made a page at a
 * time -- read with the ROM in, write with it out -- through a buffer on the
 * stack, then the six native vectors are pointed at stubs in bank $00 and
 * the emulation-mode ones are left exactly as the OS had them, for the day
 * CIO is called through them.  Every page is read back and compared before
 * the next, and the vectors after they are written: a mismatch puts the ROM
 * back and leaves the machine in the polled regime it was in, reported
 * rather than assumed.  With NMIEN and IRQEN still off the whole operation
 * is invisible to the OS.
 *
 * ON A RAPIDUS there are two RAMs under the ROM -- the accelerator's SRAM
 * window and the motherboard's -- and which one takes a write depends on
 * the MCR: window 3 fast with write-through off is the SRAM alone (as
 * Altirra's rapidus.cpp models it, UpdateSRAMWindows), fast with it on is
 * both, slow is the motherboard.  With the ROM enabled the SRAM under it
 * is not selected at all, which is why the copy has to go through RAM
 * under the ROM rather than being written straight into the SRAM.  Which
 * way is used is found, not assumed: irq_install() tries the three in the
 * order that spares the DOS most (src/sys/irq.c, find_via) and reports the
 * one that took in irq.via.  The hardware page stays hardware because MCR
 * bit 6 masks it out of the window; that bit is never cleared here.
 *
 * WHAT THE HANDLERS DO -- as little as possible, in src/sys/irq.s:
 *
 *   NMI    the vertical blank: one 16-bit count, irq_frames.  Nothing else;
 *          every consumer runs from the main line and takes the difference.
 *   IRQ    POKEY timer 1, ~4 kHz: read PORTA once, decode both quadrature
 *          pairs through the tables ptr_init() filled in (irq_plo/irq_phi
 *          pick the two lines of each axis out of the nibble, irq_qtab says
 *          what a pair transition is worth), and add to two monotonic
 *          16-bit counters.  Which counter is x and which is y, and what
 *          device it is, the handler never knows.  POKEY keyboard: KBCODE
 *          into an 8-deep ring.  Anything else pending is acknowledged and
 *          ignored.  All POKEY sources are acknowledged through IRQEN with
 *          POKMSK kept consistent, as the OS does.
 *   COP    the application ABI: COP #$56 is a VDI call, #$41 an AES call,
 *          #$44 GEMDOS, the parameter block in X:C (src/sys/abi.s,
 *          src/app/gem.h).  Any other COP is Rapidus OS's, passed to it
 *          when it is there, and refused when it is not.
 *   BRK, ABORT   record which, and park.  ABORT is what a Rapidus raises
 *          for a hardware-protect violation; a BRK is a bug.
 *
 * The handlers save what they use, force DB to $00 (an interrupt can land
 * in the middle of an MVN with DB pointing elsewhere), address everything
 * absolute, and RTI.  They run from far code, in fast SRAM; only the
 * 4-byte JML stubs the vectors point at are in bank $00.
 *
 * TIME.  v_opnwk reports 20 ms a tick, and vdi_input_poll() now calls the
 * timer vector once for every frame irq_frames has advanced since the last
 * poll -- catching up after a long draw rather than losing ticks -- so
 * evnt_timer is accurate to the frame however irregular the polling.  Off
 * the interrupt regime it still watches VCOUNT wrap.
 *
 * LEAVING.  irq_remove() undoes it in reverse: interrupt sources off, a
 * moment for a latched NMI to land while the handlers are still there,
 * then the ROM back in.  sys_exit() in src/crt_atari.s then returns the
 * machine to DOS -- see there, and rapidus_restore() for the write-back
 * of $0000-$3FFF that has to come between the two.
 *
 * Altirra takes the SRAM way; the first real card (a 6S9054E core with
 * BIOS 1.2, 2026-09-13) refused it -- the bytes read back as the ROM's --
 * and took the write-through way, which is what find_via is for.  No CX80
 * has been near this.
 */
#ifndef GEM4XE_IRQ_H
#define GEM4XE_IRQ_H

#include <stdint.h>

/* How the vectors were reached -- irq.how */
#define IRQ_OFF        0    /* polled regime: nothing installed            */
#define IRQ_ROM_COPIED 1    /* the OS ROM copied under itself, then patched */
#define IRQ_RAM_FOUND  2    /* $C000-$FFFF was RAM already: patched in place */

/* Why not -- irq.fail */
#define IRQ_FAIL_NONE  0
#define IRQ_FAIL_COPY  1    /* a page read back wrong: the RAM under the ROM
                               is not there, or not writable                */
#define IRQ_FAIL_VEC   2    /* the vectors read back wrong                  */

/* Which RAM under the ROM took the copy -- irq.via (irq.c, ram_side) */
#define IRQ_VIA_NONE   0    /* no Rapidus: the one there is                 */
#define IRQ_VIA_SRAM   1    /* window 3 fast, write-through off: the SRAM   */
#define IRQ_VIA_BOTH   2    /* window 3 fast, write-through on: SRAM and
                               motherboard together                         */
#define IRQ_VIA_BUS    3    /* window 3 slow: the motherboard, and it stays
                               slow while GEM runs                          */

typedef struct {
    uint8_t  how, fail;
    uint8_t  portb_before;  /* PORTB as found; bit 0 = OS ROM enabled     */
    uint8_t  mcr_before;    /* Rapidus MCR as found (0 without a Rapidus) */
    uint8_t  fast;          /* window 3 switched to the SRAM               */
    uint8_t  via;           /* IRQ_VIA_*: which RAM the copy went to, or
                               the last one tried when none took          */
    uint8_t  bad_byte;      /* after a failure: the first byte that read
                               back wrong, as it read                      */
    uint8_t  timer_div;     /* AUDF1: the pointer sampler's divisor        */
    uint8_t  pal;           /* 1: a PAL machine (GTIA), which sets the
                               sampler's rate and the frame's length      */
    uint16_t rom_sum;       /* 16-bit sum of $C000-$CFFF,$D800-$FFFF read
                               from the ROM, and ... */
    uint16_t ram_sum;       /* ... read back from the RAM copy, before the
                               vectors were written                        */
    uint16_t speed;         /* loop turns in 128 scanlines at install: how
                               fast this CPU really is, which sets
                               timer_div (irq.c, cpu_turns)               */
} IRQ_INFO;

extern IRQ_INFO irq;

/* For src/sys/cio.s, set by irq_install(): what to put back for the DOS's
 * benefit around a CIO call and take again after it.  Bit 0: the OS ROM
 * (PORTB bit 0 high again -- the DOS finds the ROM in, and the RAM under
 * it as it left it); bit 1: window 3 slow (a Rapidus, so the motherboard
 * is what is behind the ROM, not the SRAM copy).  Zero: touch nothing. */
#define IRQ_SWAP_ROM   0x01
#define IRQ_SWAP_WIN3  0x02
extern uint8_t irq_cio_swap;

/* --- the handlers' state, written at interrupt time (src/sys/irq.s) ----- */
extern volatile uint16_t irq_frames;       /* vertical blanks             */
extern volatile uint32_t irq_timer;        /* timer-1 interrupts taken:
                                              32 bits, ~4 kHz, so it is a
                                              clock (irq_clock below)     */

/* The machine's clock, from the timer: seconds and microseconds since
 * irq_install(), exact to one sampler tick (250 us NTSC, 253 PAL) and
 * monotonic for the twelve days the count takes to wrap.  What
 * Tgettimeofday is built on. */
void irq_clock(uint32_t *sec, uint32_t *usec);
extern volatile uint16_t irq_qlo, irq_qhi; /* the two axes' counters      */
extern volatile uint8_t  irq_kb[8];        /* raw KBCODEs, a ring          */
extern volatile uint8_t  irq_kb_head, irq_kb_tail, irq_kb_count;
extern volatile uint8_t  irq_fault;        /* 2 BRK, 3 ABORT (1 was COP,   */
                                           /* now the ABI: src/sys/abi.s)  */

/* --- what the pointer layer gives the handler (pointer.c fills these) --- */
extern uint8_t irq_ptr_on;                 /* sample PORTA at all          */
extern uint8_t irq_plo[16], irq_phi[16];   /* PORTA nibble -> axis pair   */
extern signed char irq_qtab[16];           /* (prev << 2 | now) -> -1/0/+1 */
extern uint8_t irq_prev_lo, irq_prev_hi;   /* the handler's last pairs,
                                              already shifted up two      */

/* The twelve bytes the native vectors get (src/sys/irq.s). */
extern const uint8_t irq_vectab[12];

/* Install: the ROM shadow, the vectors, then NMI (VBI) and IRQ (POKEY
 * timer 1 and keyboard) on.  Returns irq.how.  Call after
 * rapidus_speedup() -- it takes window 3 as that left it -- and before
 * anything that wants a key or a count. */
uint8_t irq_install(void);

/* Everything off and the ROM back, so the OS's own vectors are what the
 * emulation-mode return to DOS will find. */
void    irq_remove(void);

/* AUDCTL, AUDF1, AUDC1 and SKCTL as the sampler and the keyboard want
 * them: after a CIO call, which lends POKEY to the OS (src/sys/cio.c). */
void    irq_pokey_resync(void);

#endif /* GEM4XE_IRQ_H */
