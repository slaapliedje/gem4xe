/* zwin.h -- bank-$00 bss in the banked window.
 *
 * ZWIN on a definition puts it in section `zwin`, which src/gem4xe.scm
 * places at $4000-$47FF: the first 2 KB of the window a DOS may bank over
 * while it services a call, ahead of the application pool.  It is for
 * data that only gem4xe's own code touches from its own calls -- never an
 * interrupt handler, which can run with a bank in, and never anything a
 * test polls from the host while a DOS call is in flight (m14).  What
 * lives there is the large and the read-mostly: on a Rapidus this window
 * reads at full speed but writes through to the bus (src/sys/rapidus.c),
 * and taking it out of $2000-$3FFF is what gave the stack its room.
 *
 * IT DOES NOT GROW AT THE POOL'S EXPENSE.  That was tried, for two
 * buffers worth 512 bytes, and turned test-m28 red: the conformance
 * runner's pool is 1.5 KB smaller than GEM.COM's and must hold the
 * desktop beside an accessory, and rs_load peaks at the WHOLE resource
 * file (src/aes/rsrc.c).  There were 348 bytes of headroom, not 860.
 * tools/memreport.py models both pools and that peak now, so the next
 * attempt fails at `make memcheck` rather than in the emulator.
 */
#ifndef GEM4XE_ZWIN_H
#define GEM4XE_ZWIN_H

#include "portab.h"

/* The 6502's VBXE device (docs/6502.md, step 6) keeps its window-safe
 * data with the rest of its statics, at $9000-$9EFF: the ANTIC screen's
 * place, free when the VBXE is the screen. */
#ifdef GEM4XE_VBRAM
#define ZWIN SECTION("vbram")
#else
#define ZWIN SECTION("zwin")
#endif

#endif
