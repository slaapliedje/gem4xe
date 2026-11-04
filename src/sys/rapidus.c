/* rapidus.c -- switch the Rapidus SRAM in over bank $00.  See rapidus.h. */
#include "portab.h"
#include "rapidus.h"
#include "vbxe/vbxe.h"          /* MEMAC_WIN_ADDR, MEMAC_WIN_SIZE */

RAPIDUS rapidus;

/* The linker's direct page (src/gem4xe.scm, base-address _DirectPageStart);
 * the library startup loads D from it. */
extern char _DirectPageStart;

static uint8_t reg_read(uint32_t a)
{
    volatile uint8_t FAR *p = (volatile uint8_t FAR *)a;
    return *p;
}

static void reg_write(uint32_t a, uint8_t v)
{
    volatile uint8_t FAR *p = (volatile uint8_t FAR *)a;
    *p = v;
}

uint8_t rapidus_reg_read(uint32_t a)     { return reg_read(a); }
void    rapidus_reg_write(uint32_t a, uint8_t v) { reg_write(a, v); }

/* Bring a window's SRAM copy up to date from the motherboard.  Only valid
 * while the window is still slow and write-through is on: a read then comes
 * from the motherboard and a write lands in both.  Copying the window that
 * holds this function's own stack frame onto itself is fine -- each byte is
 * written back with the value just read, and nothing else runs. */
static void sync_window(uint8_t w)
{
    volatile uint8_t *p = (volatile uint8_t *)((uint16_t)w << 14);
    uint16_t n = 0x4000;

    do {
        *p = *p;
        p++;
    } while (--n);
}

void rapidus_speedup(void)
{
    uint8_t mcr, cmcr, keep_slow, fast, w, here;

    rapidus.present = 0;
    rapidus.synced = 0;
    /* The signature names the FPGA ("6S" for a Spartan 6) and then the
     * core's version, which is not checked: Altirra's core is 0.38E, the
     * firmware on a real card was seen loading "6s9054e" (2026-09-13) --
     * printed in lower case, and whether the bytes at $FF0000 are too
     * has not been seen, so either case of the S is a Rapidus here.
     * GEMDIAG.COM shows the eight bytes as found (src/sys/diag.c). */
    if (reg_read(RAP_SIG) != '6' || (reg_read(RAP_SIG + 1) | 0x20) != 's')
        return;
    rapidus.present = 1;

    mcr  = reg_read(RAP_MCR);
    cmcr = reg_read(RAP_CMCR);
    rapidus.mcr_before = mcr;
    rapidus.cmcr_before = cmcr;

    /* The windows that must not go fast: whatever the MEMAC window spans,
     * and the OS/hardware window, which is not ours to decide. */
    keep_slow = MCR_SLOW3;
    for (w = RAP_WIN(MEMAC_WIN_ADDR);
         w <= RAP_WIN(MEMAC_WIN_ADDR + MEMAC_WIN_SIZE - 1); w++)
        keep_slow |= (uint8_t)(1 << w);

    /* Windows about to change from slow to fast. */
    fast = (uint8_t)(mcr & MCR_SLOWALL & ~keep_slow);

    /* Without write-through nothing has kept the SRAM copies current. */
    if (!(mcr & MCR_WRTHRU)) {
        mcr |= MCR_WRTHRU;
        reg_write(RAP_MCR, mcr);
        for (w = 0; w < 4; w++) {
            if (fast & (1 << w)) {
                sync_window(w);
                rapidus.synced |= (uint8_t)(1 << w);
            }
        }
    }

    mcr = (uint8_t)((mcr & ~fast) | (keep_slow & ~MCR_SLOW3));
    reg_write(RAP_MCR, mcr);
    rapidus.mcr_after = mcr;

    /* Fast writes for $0000-$3FFF, if that is where the linker put what the
     * program writes: the direct page, the stack and the data.  If any of
     * them is elsewhere this is left alone -- slower, still correct. */
    if (!(mcr & MCR_SLOW0)
        && RAP_WIN(&_DirectPageStart) == 0
        && RAP_WIN(&here) == 0
        && RAP_WIN(&rapidus) == 0) {
        cmcr |= CMCR_FAST0;
        reg_write(RAP_CMCR, cmcr);
    }
    rapidus.cmcr_after = cmcr;
}

/* $4000-$7FFF slow again, on GEM4XE.CFG's say -- which is read after the
 * speed-up, because reading it takes CIO and CIO takes the vectors.  The
 * window's copy goes down to the motherboard first: it is fast, so a read
 * comes from the SRAM, and write-through (on since the speed-up) lands each
 * byte in both.  Whatever was written there before write-through came on --
 * the window fast from the firmware without it -- reaches the motherboard
 * that way too, and nothing is lost when the reads move there.  No bank is
 * in: this runs between CIO calls, and nothing else banks. */
void rapidus_slow_bank(void)
{
    uint8_t mcr;

    if (!rapidus.present)
        return;
    mcr = reg_read(RAP_MCR);
    if (!(mcr & MCR_SLOW1))
        sync_window(1);
    mcr |= MCR_SLOW1;
    reg_write(RAP_MCR, mcr);
    rapidus.mcr_after = mcr;
}

/* The way back, for a return to DOS.  Window 0 first gets its write-through
 * back and is copied onto itself -- reads still come from the SRAM, so the
 * copy carries everything written since the speed-up down to the
 * motherboard, the OS variables and the direct page and stack included --
 * and then the MCR is put back as it was found.  Window 3 is irq_remove()'s
 * to restore; it is the one that changed it.  Runs on the stack it is
 * writing back, which is fine: every byte goes back with the value it has. */
void rapidus_restore(void)
{
    uint8_t mcr;

    if (!rapidus.present)
        return;
    if (rapidus.cmcr_after & CMCR_FAST0) {
        rapidus.cmcr_after &= (uint8_t)~CMCR_FAST0;
        reg_write(RAP_CMCR, rapidus.cmcr_after);
        sync_window(0);
    }
    mcr = reg_read(RAP_MCR);
    mcr = (uint8_t)((mcr & ~MCR_SLOWALL) | (rapidus.mcr_before & MCR_SLOWALL));
    reg_write(RAP_MCR, mcr);
    rapidus.mcr_after = mcr;
}
