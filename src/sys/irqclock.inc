/* irqclock.inc -- the timer's count as seconds and microseconds:
 * irq_clock (irq.h), for the 65C816's src/sys/irq.c and the 6502's
 * src/sys6502/irq6502.c alike, which both keep irq_timer and irq.  A
 * fragment rather than a file of its own so that neither build's object
 * lists change; included once by each. */
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
