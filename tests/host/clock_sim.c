/* clock_sim.c -- src/sys/clock.c's SIO clock under Calypsi's own simulator.
 *
 * An APETime clock on the serial bus -- a FujiNet's -- was asked for the
 * time at every read, and the Control Panel reads it every second: one
 * click a second from the OS's noisy I/O on a 600XL (2026-11-27).  Now it
 * is asked once an hour and the seconds between are counted from the
 * timer (sio_clock).  No emulator here has an APETime device, so this
 * includes clock.c whole, stands in for the bus and the timer, and
 * publishes every read and how many times the bus was asked;
 * tests/host/test_clocksio.py checks them against Python's datetime.
 *
 * The chips are never touched: the probe is marked done with the SIO
 * clock chosen, which is what clock_probe leaves on a machine whose
 * registers said no and whose bus answered.
 */
#include "../../src/sys/clock.c"

/* ---- the stand-ins ------------------------------------------------------ */

volatile uint32_t irq_timer = 1;        /* nonzero: the timer runs */
uint32_t tsim_now;                      /* irq_clock's seconds */
DOS_INFO dos;

void irq_clock(uint32_t *sec, uint32_t *usec)
{
    *sec = tsim_now;
    *usec = 0;
}

void irq_pokey_resync(void) { }
SIMPLE_CALL uint16_t dos_call(uint16_t fn) { (void)fn; return 1; }

uint16_t tsim_asked;                    /* bus transactions */
uint8_t tsim_up = 1;                    /* does anybody answer? */
uint8_t tsim_bus[6];                    /* d m y h m s, as APETime sends */

uint8_t sio_gettime(void *buf)
{
    uint8_t *b = (uint8_t *)buf, i;

    tsim_asked++;
    if (!tsim_up)
        return 138;                     /* a timeout */
    for (i = 0; i < 6; i++)
        b[i] = tsim_bus[i];
    return SIO_OK;
}

/* ---- the cases ---------------------------------------------------------- */

#define NREADS 16
/* per read: second minute hour day month year asked ok */
uint16_t tsim_out[NREADS * 8];
uint16_t tsim_n;
uint16_t tsim_ran;

static void bus(uint8_t d, uint8_t mo, uint8_t y, uint8_t h, uint8_t mi, uint8_t s)
{
    tsim_bus[0] = d;
    tsim_bus[1] = mo;
    tsim_bus[2] = y;
    tsim_bus[3] = h;
    tsim_bus[4] = mi;
    tsim_bus[5] = s;
}

static void fresh(void)
{
    rtc_probed = 1;
    rtc_other = CLOCK_SIO;
    sio_have = 0;
}

static void at(uint32_t now)
{
    CLOCK c;
    uint16_t *o = tsim_out + tsim_n * 8;
    uint8_t ok;

    tsim_now = now;
    ok = clock_read(&c);
    o[0] = c.second;
    o[1] = c.minute;
    o[2] = c.hour;
    o[3] = c.day;
    o[4] = c.month;
    o[5] = c.year;
    o[6] = tsim_asked;
    o[7] = ok;
    tsim_n++;
}

int main(void)
{
    /* 1-5: once an hour, the year carried at midnight */
    fresh();
    bus(31, 12, 26, 23, 59, 30);
    at(1000);                   /* asked: 2026-12-31 23:59:30 */
    at(1029);                   /* counted: 23:59:59 */
    at(1030);                   /* counted: 2027-01-01 00:00:00 */
    at(1000 + 3599);            /* counted, the hour not up */
    bus(1, 1, 27, 1, 0, 5);     /* the bus five seconds on from the count */
    at(1000 + 3600);            /* asked again: its time, not the count */
    /* 6-7: the bus gone: counted on from its last answer, asked an hour later */
    tsim_up = 0;
    at(4600 + 3600);            /* asked, no answer: 02:00:05 counted */
    at(4600 + 3601);            /* not asked again: 02:00:06 */
    /* 8-9: 2028 is a leap year, 2027 is not */
    tsim_up = 1;
    fresh();
    bus(28, 2, 28, 23, 59, 59);
    at(20000);
    at(20001);                  /* 2028-02-29 00:00:00 */
    fresh();
    bus(28, 2, 27, 23, 59, 59);
    at(30000);
    at(30001);                  /* 2027-03-01 00:00:00 */
    /* 12-13: the timer not running yet: every read is the bus's */
    irq_timer = 0;
    fresh();
    bus(5, 6, 27, 12, 0, 0);
    at(40000);
    at(40000);
    irq_timer = 1;
    /* 14: nobody on the bus at all: no time */
    tsim_up = 0;
    fresh();
    at(50000);
    tsim_ran = 1;
    return 0;
}
