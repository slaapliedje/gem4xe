/* irq.c -- the OS ROM shadowed into RAM, the native vectors filled, and
 * the interrupt sources switched on.  What and why: irq.h. */
#include "portab.h"
#include "irq.h"
#include "rapidus.h"

IRQ_INFO irq;
uint8_t  irq_cio_swap;

volatile uint16_t irq_frames, irq_qlo, irq_qhi;
volatile uint32_t irq_timer;

#define GTIA_PAL (*(volatile uint8_t *)0xD014)  /* bits 1-3 clear on PAL */

/* THE TIMER IS A CLOCK.  Timer 1 runs at the 64 kHz base clock over
 * (TIMER_DIV + 1) -- ~3,995 Hz on NTSC, ~3,959 on PAL, the base being
 * the machine's master clock over 28 -- and irq.s counts every interrupt
 * into 32 bits.  This turns the count into seconds and microseconds,
 * keeping the split in tenths of a tick so that the fraction of a tick
 * per second is never dropped (it would cost PAL twelve seconds a day).
 * Read the count in halves with the low word twice, because the
 * interrupt can carry into the high word between the two loads. */
static uint32_t tick32(void)
{
    volatile uint16_t *w = (volatile uint16_t *)&irq_timer;
    uint16_t lo1 = w[0], hi = w[1], lo2 = w[0];
    if (lo2 < lo1)                      /* it wrapped between the reads */
        hi = w[1];
    return ((uint32_t)hi << 16) | lo2;
}

void irq_clock(uint32_t *sec, uint32_t *usec)
{
    static uint32_t last, secs, rem10, rate10;
    uint32_t now, delta, us100;

    if (!rate10) {                      /* from the divisor and the machine */
        uint32_t base = irq.pal ? 63337UL : 63920UL;   /* the 64 kHz clock */
        uint32_t div = (uint32_t)irq.timer_div + 1;
        rate10 = (base * 10 + div / 2) / div;          /* ticks/s, x10 */
    }
    us100 = (100000000UL + rate10 / 2) / rate10;       /* us per tenth, x100 */
    now = tick32();
    delta = now - last;
    last = now;
    while (delta > 100000000UL) {       /* hours unasked: in pieces */
        rem10 += 1000000000UL;
        delta -= 100000000UL;
        secs += rem10 / rate10;
        rem10 %= rate10;
    }
    rem10 += delta * 10;
    secs += rem10 / rate10;
    rem10 %= rate10;
    *sec = secs;
    *usec = (rem10 * us100) / 100;
}
volatile uint8_t  irq_kb[8], irq_kb_head, irq_kb_tail, irq_kb_count;
volatile uint8_t  irq_fault;

uint8_t     irq_ptr_on;
uint8_t     irq_plo[16], irq_phi[16];
signed char irq_qtab[16];
uint8_t     irq_prev_lo, irq_prev_hi;
uint8_t     irq_pend, irq_tmp;         /* the handler's scratch */

#define PORTB   (*(volatile uint8_t *)0xD301)
#define NMIEN   (*(volatile uint8_t *)0xD40E)
#define IRQEN   (*(volatile uint8_t *)0xD20E)
#define POKMSK  (*(volatile uint8_t *)0x0010)
#define AUDF1   (*(volatile uint8_t *)0xD200)
#define AUDC1   (*(volatile uint8_t *)0xD201)
#define AUDCTL  (*(volatile uint8_t *)0xD208)
#define STIMER  (*(volatile uint8_t *)0xD209)
#define SKCTL   (*(volatile uint8_t *)0xD20F)

#define PORTB_OSROM  0x01
#define NMIEN_VBI    0x40
#define IRQ_TIMER1   0x01
#define IRQ_KEY      0x40

/* AUDF1 for the pointer sampler.  The 64 kHz base clock over (n + 1):
 * n = 15 is ~3.96 kHz on a PAL machine, ~4.0 kHz on NTSC, a sample every
 * 250 us -- an ST mouse pushed hard makes a transition every few hundred.
 * Reported in irq.timer_div so a gate can derive the rate it should
 * measure rather than repeat the number, and so irq_clock can count time
 * by it.
 *
 * THAT IS A RAPIDUS'S RATE, AND ONLY A RAPIDUS CAN PAY IT.  Each
 * interrupt costs a native-mode entry, the handler and an RTI, part of it
 * on the slow bus -- nothing to a 20 MHz CPU and most of a 1.79 MHz one.
 * Altirra's own 65C816 runs at 1.79 MHz unless told otherwise, and there
 * the sampler took the whole machine: under AltirraOS, which took the
 * interrupts about twice as often, gem4xe never got past its first steps
 * -- an AtariAge report of a black screen from the 0.9.2 cartridge
 * (docs/phase81.md).  So the rate follows the CPU: cpu_turns() counts
 * 400 on a 20 MHz Rapidus and 25 on a 1.79 MHz 65C816, and below
 * SPEED_FULL the divisor grows in proportion, which keeps the sampler's
 * share of the machine about what it is on a Rapidus.  A slow machine's
 * mouse is sampled less often and loses counts when it is pushed hard;
 * that is the cost, and it is not a machine that stops. */
#define TIMER_DIV    15
#define SPEED_FULL   200
#define DIV_MAX      255

static uint8_t timer_div_for(uint16_t speed)
{
    uint16_t d;

    if (speed >= SPEED_FULL)
        return TIMER_DIV;
    if (speed < (uint16_t)((TIMER_DIV + 1) * SPEED_FULL / (DIV_MAX + 1)))
        return DIV_MAX;                 /* slower than that: the floor */
    d = (uint16_t)((TIMER_DIV + 1) * SPEED_FULL / speed - 1);
    return (uint8_t)(d > DIV_MAX ? DIV_MAX : d);
}

#define VCOUNT  (*(volatile uint8_t *)0xD40B)

/* How fast this CPU really is: sixteen turns of a loop in its own memory
 * per look at VCOUNT, while ANTIC draws 128 scanlines -- ANTIC's DMA and
 * all, which is what a program gets.  The look is an I/O read, and on a
 * Rapidus every I/O read is a trip to the 1.79 MHz bus, so it is taken
 * once per sixteen turns or it would be the bus that was measured.
 * Every read of VCOUNT goes into a word first: spinning on a byte is
 * compiler bug B16 at -O2 (tools/ccbug). */
static volatile uint16_t turn_sink;

static uint16_t cpu_turns(void)
{
    uint16_t n = 0, v, k;

    do v = VCOUNT; while (v != 8);
    do v = VCOUNT; while (v == 8);
    do {
        for (k = 0; k < 16; k++)
            turn_sink = k;
        n++;
        v = VCOUNT;
    } while (v < 72);
    return n;
}

#define VEC_BASE     0xFFE4
#define VEC_LEN      12

/* The OS window: two runs, the hardware page between them left alone. */
static const uint16_t run_lo[2] = { 0xC000, 0xD800 };
static const uint16_t run_hi[2] = { 0xD000, 0x0000 };   /* 0 = wraps: $10000 */

static uint8_t rom_in;                  /* PORTB bit 0 as found */
static uint8_t win3_fast;               /* MCR bit 3 clear as found (Rapidus) */
static uint8_t via;                     /* IRQ_VIA_*: which RAM takes the copy */

/* Window 3 between its two configurations: the OS ROM (as found) and the
 * RAM under it.  Reads with the ROM in come from the motherboard whatever
 * the MCR says (irq.h), so the ROM side needs only PORTB.
 *
 * On a Rapidus there are two RAMs under the ROM and `via` says which one
 * the copy goes to -- decided by find_via(), below, not assumed:
 *
 *   IRQ_VIA_SRAM   window 3 fast, write-through off.  Altirra's model
 *                  (rapidus.cpp, UpdateSRAMWindows): the write lands in
 *                  the SRAM alone.  THE RAM UNDER THE ROM IS NOT OURS.  A
 *                  DOS may live there: SpartaDOS 3.2's X builds load
 *                  $CC00-$CFF2 and $E6ED-$FFF8 and reach them by switching
 *                  the ROM out, and Phase 13 found the port had overwritten
 *                  them with the ROM copy -- every CIO open then answered
 *                  $81, from whatever the DOS's entry point had become.  So
 *                  this is the first choice: the motherboard keeps what the
 *                  DOS put there, invisible until a CIO call makes the
 *                  window slow again (src/sys/cio.s, irq_cio_swap).  While
 *                  write-through is off the other fast windows write to the
 *                  SRAM alone as well; what the copy loop writes there is
 *                  its own stack and sums, which nothing reads from the
 *                  motherboard side.
 *   IRQ_VIA_BOTH   window 3 fast, write-through on: the SRAM and the
 *                  motherboard together.  How the card's own firmware
 *                  plants its native NMI vector (MODULE.ROM 1.2), so it
 *                  is the next thing to try when a card has refused the
 *                  first -- the 6S9054E of 2026-09-13 did, and took this
 *                  one -- at the cost of the motherboard's copy.
 *   IRQ_VIA_BUS    window 3 slow: the motherboard's RAM under the ROM, the
 *                  same one a machine without a Rapidus has, and the OS
 *                  then runs from it at bus speed.  The vectors are the
 *                  only thing fetched there while GEM runs, so that costs
 *                  next to nothing; what it costs is the DOS's copy.
 *
 * Without a Rapidus there is only one RAM under the ROM, the copy goes
 * into it, and a DOS living there does not survive.  SpartaGEM needs the
 * accelerator's SRAM; docs/phase13.md. */
static void os_side(void)
{
    PORTB = irq.portb_before;
    if (rapidus.present)
        rapidus_reg_write(RAP_MCR, irq.mcr_before);
}

static void ram_side(uint8_t writing)
{
    PORTB = (uint8_t)(irq.portb_before & ~PORTB_OSROM);
    if (rapidus.present) {
        uint8_t mcr = irq.mcr_before;
        if (via == IRQ_VIA_BUS) {
            mcr |= MCR_SLOW3;
        } else {
            mcr &= (uint8_t)~MCR_SLOW3;
            if (writing) {
                if (via == IRQ_VIA_SRAM)
                    mcr &= (uint8_t)~MCR_WRTHRU;
                else
                    mcr |= MCR_WRTHRU;
            }
        }
        rapidus_reg_write(RAP_MCR, mcr);
    }
}

/* Copy one run of the window from the OS side to the RAM side, a page at a
 * time through a buffer on the stack, verifying each page as it goes.
 * Returns 0 on a mismatch; the sums accumulate either way. */
static uint8_t copy_run(uint16_t lo, uint16_t hi)
{
    uint8_t buf[256];
    uint16_t page = lo;
    do {
        volatile uint8_t *p = (volatile uint8_t *)page;
        uint16_t i;
        os_side();
        for (i = 0; i < 256; i++) {
            buf[i] = p[i];
            irq.rom_sum += buf[i];
        }
        ram_side(1);
        for (i = 0; i < 256; i++)
            p[i] = buf[i];
        for (i = 0; i < 256; i++) {
            uint8_t v = p[i];
            irq.ram_sum += v;
            if (v != buf[i]) {
                irq.bad_byte = v;
                return 0;
            }
        }
        page += 256;
    } while (page != hi);
    return 1;
}

/* The RAM side was RAM already: nothing to copy, just sum it, so the report
 * is the same shape either way. */
static void sum_run(uint16_t lo, uint16_t hi)
{
    uint16_t page = lo;
    do {
        volatile uint8_t *p = (volatile uint8_t *)page;
        uint16_t i;
        for (i = 0; i < 256; i++)
            irq.rom_sum += p[i];
        page += 256;
    } while (page != hi);
    irq.ram_sum = irq.rom_sum;
}

/* Plant the twelve native-vector bytes on the RAM side and read them back.
 * The first byte that differs is kept for the boot screen (so is the copy
 * loop's, above). */
static uint8_t write_vectors(void)
{
    volatile uint8_t *v = (volatile uint8_t *)VEC_BASE;
    uint8_t i;
    for (i = 0; i < VEC_LEN; i++)
        v[i] = irq_vectab[i];
    for (i = 0; i < VEC_LEN; i++)
        if (v[i] != irq_vectab[i]) {
            irq.bad_byte = v[i];
            return 0;
        }
    return 1;
}

/* Which RAM under the ROM takes a write, on a Rapidus.  The vector bytes
 * are the probe: each way is tried in turn, SRAM first because it is the
 * one that spares the DOS, until one reads back.  The motherboard's twelve
 * bytes are kept and put back if none does, so a DOS living under the ROM
 * is no worse off for the asking; the SRAM's get the same twelve, which is
 * what a write-through machine would have there anyway. */
static uint8_t find_via(void)
{
    volatile uint8_t *v = (volatile uint8_t *)VEC_BASE;
    uint8_t keep[VEC_LEN];
    uint8_t i, w;

    via = IRQ_VIA_BUS;
    ram_side(1);
    for (i = 0; i < VEC_LEN; i++)
        keep[i] = v[i];
    for (w = IRQ_VIA_SRAM; w <= IRQ_VIA_BUS; w++) {
        via = w;
        ram_side(1);
        if (write_vectors())
            return 1;
    }
    for (w = IRQ_VIA_BUS; w >= IRQ_VIA_SRAM; w--) {
        via = w;
        ram_side(1);
        for (i = 0; i < VEC_LEN; i++)
            v[i] = keep[i];
    }
    via = IRQ_VIA_BUS;
    return 0;
}

/* The POKEY registers the sampler and the keyboard depend on.  Written at
 * install, and again after every CIO call (src/sys/cio.c), which leaves
 * timer 1 disarmed until this has run (src/sys/cio.s): the OS's SIO
 * takes AUDCTL and the audio-control registers for its serial clock and
 * SKCTL for its serial modes, and what it leaves them as on its way out
 * is its business, not something to rely on.
 *
 * AND STIMER, WHICH THIS DID NOT WRITE UNTIL 0.9.3.  It restarts the
 * count, and leaving it out kept the clock from losing the part of a
 * tick a CIO call interrupts.  But the new AUDCTL and AUDF1 are not what
 * the channel counts by until it reloads: under AltirraOS -- Altirra's own
 * OS, which a stock Altirra runs -- the channel was left counting fast,
 * timer 1 fired again within two hundred cycles of every acknowledgement,
 * and on a 1.79 MHz 65C816 the handler took every cycle there was -- so
 * the reprogramming has to come BEFORE the timer is armed, and the
 * trampoline arming it on its way out was the other half of the bug.
 * gem4xe never got past its first CIO call: a black screen, from the
 * 0.9.2 cartridge, reported on AtariAge (docs/phase81.md).  A part of a
 * tick per CIO call is what the restart costs the clock. */
void irq_pokey_resync(void)
{
    AUDCTL = 0;                     /* 64 kHz base, no linking */
    AUDF1  = irq.timer_div;
    AUDC1  = 0;                     /* silent */
    SKCTL  = 3;                     /* keyboard scan and debounce, as the OS
                                       leaves it: the keyboard IRQ needs the
                                       scan running */
    STIMER = 0;                     /* ...counting by those, from now */
    IRQEN  = POKMSK;                /* and only now armed: the CIO trampoline
                                       brings the sources back without timer
                                       1 (src/sys/cio.s) */
}

static void sources_on(void)
{
    irq_frames = irq_timer = 0;
    irq_qlo = irq_qhi = 0;
    irq_kb_head = irq_kb_tail = irq_kb_count = 0;
    irq_fault = 0;
    irq_prev_lo = irq_prev_hi = 0;

    irq_pokey_resync();             /* which loads the divisor */
    POKMSK = IRQ_TIMER1 | IRQ_KEY;
    IRQEN  = 0;                     /* drop anything latched while off ... */
    IRQEN  = POKMSK;                /* ... then arm */
    NMIEN  = NMIEN_VBI;
    cpu_cli();
}

uint8_t irq_install(void)
{
    uint8_t ok;

    irq.how  = IRQ_OFF;
    irq.fail = IRQ_FAIL_NONE;
    irq.fast = 0;
    irq.via  = IRQ_VIA_NONE;
    irq.bad_byte = 0;
    irq_cio_swap = 0;
    irq.speed = cpu_turns();
    irq.timer_div = timer_div_for(irq.speed);
    irq.pal = (GTIA_PAL & 0x0E) == 0;
    irq.rom_sum = irq.ram_sum = 0;
    irq.portb_before = PORTB;
    irq.mcr_before = rapidus.present ? rapidus_reg_read(RAP_MCR) : 0;
    rom_in = (uint8_t)(irq.portb_before & PORTB_OSROM);
    win3_fast = (uint8_t)(rapidus.present && !(irq.mcr_before & MCR_SLOW3));
    via = IRQ_VIA_NONE;

    if (rapidus.present) {
        ok = find_via();
        irq.via = via;
        if (!ok) {
            os_side();
            irq.fail = IRQ_FAIL_VEC;
            return irq.how;
        }
    }

    if (!rom_in && (!rapidus.present || (win3_fast && via != IRQ_VIA_BUS))) {
        /* $C000-$FFFF already reads and writes as the RAM side: an OS in
         * RAM, or a caller that did this before us.  Patch in place. */
        sum_run(run_lo[0], run_hi[0]);
        sum_run(run_lo[1], run_hi[1]);
        irq.how = IRQ_RAM_FOUND;
    } else {
        ok = copy_run(run_lo[0], run_hi[0]);
        if (ok)
            ok = copy_run(run_lo[1], run_hi[1]);
        if (!ok) {
            os_side();
            irq.fail = IRQ_FAIL_COPY;
            return irq.how;
        }
        irq.how = IRQ_ROM_COPIED;
    }
    ram_side(1);
    if (!write_vectors()) {
        os_side();
        irq.how  = IRQ_OFF;
        irq.fail = IRQ_FAIL_VEC;
        return irq.how;
    }
    ram_side(0);
    irq.fast = (uint8_t)(rapidus.present && via != IRQ_VIA_BUS);
    /* What a CIO call has to give the DOS back: the ROM, if it was in when
     * we came, and on a Rapidus the motherboard behind it -- unless that
     * is where the copy went, and window 3 is slow already. */
    if (irq.how == IRQ_ROM_COPIED)
        irq_cio_swap = (uint8_t)(IRQ_SWAP_ROM | (irq.fast ? IRQ_SWAP_WIN3 : 0));
    sources_on();
    return irq.how;
}

void irq_remove(void)
{
    volatile uint16_t spin;

    if (irq.how == IRQ_OFF)
        return;
    NMIEN  = 0;
    IRQEN  = 0;
    POKMSK = 0;
    /* An NMI ANTIC asserted just before NMIEN went low is still coming;
     * let it land on the handlers while they are still what the vectors
     * point at.  Long enough at any clock. */
    for (spin = 0; spin < 512; spin++)
        ;
    cpu_sei();
    os_side();
    irq_cio_swap = 0;
    irq.how  = IRQ_OFF;
    irq.fast = 0;
}
