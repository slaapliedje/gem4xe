/* hiprobe.h -- linear memory above bank $00, discovered rather than assumed.
 *
 * gem4xe requires a 65C816 with linear RAM.  Two boards provide it and they do
 * not agree on the map:
 *
 *   Rapidus   14.5 MB SDRAM at $080000-$EFFFFF, plus SRAM in banks $01-$07,
 *             registers in bank $FF.  Signature "6S9038E " at $FF0000.
 *   Antonia   65816 with 4 MB or 8 MB.  NOT emulated by Altirra, so nothing
 *             here about it has been tested -- see farmem_probe().
 *
 * Hardcoding either map would make the other fail silently, so this PROBES:
 * it writes each bank's own number into it and reads them all back, which
 * finds real RAM, sizes it, and rejects mirrors in one pass.  Any board that
 * exposes linear RAM works, tested or not.
 *
 * That is the same reasoning as the pointer seam: the thing above the seam
 * asks for memory, not for a particular accelerator.
 *
 * WHAT IT WILL NOT HAND OUT: the banks the program itself is running from.
 * gem4xe's code lives in the banks from $01 up (src/gem4xe.scm), copied up
 * at load time by src/farload.s, so probing and allocation both begin at the
 * first bank above the highest address the loader wrote -- taken from the
 * loader's own record of it, not written down twice.
 *
 * Moved out of farmem.h in phase 116; the allocator it starts is there.
 */
#ifndef GEM4XE_HIPROBE_H
#define GEM4XE_HIPROBE_H

#include <stdint.h>
#include "portab.h"
#include "farmem.h"

/* What gem4xe holds of the OS's allocator (phase 112), on the direct
 * page -- LoRAM, where FARMEM is, is at its reserve.  Page numbers (the
 * top two bytes of an address), 0 for none: the heap's block, and the
 * one over the banks its own image was loaded into; farmem_release()
 * gives both back. */
extern TINY uint16_t km_heap, km_image;
extern TINY uint8_t  km_clash;  /* something was in gem4xe's image banks:
                                 * the image's last bank, 0 when nothing */
extern TINY uint8_t  km_held;   /* farmem_held(): both blocks still ours */
extern TINY uint8_t  hiram_lo;  /* HIGHRAM= in GEM4XE.CFG: the banks the */
extern TINY uint8_t  hiram_hi;  /* heap may use, inclusive; 0: not said */

/* The Rapidus OS kernel allocator (src/sys/sei.s): km_ok says it is there
 * (src/sys/abi.c), km_getblk(n) lists its blocks. */
SIMPLE_CALL int16_t km_getblk(uint16_t n);
SIMPLE_CALL int16_t km_malloc(uint16_t pages);   /* mode in km_mode */
SIMPLE_CALL int16_t km_free(uint16_t page);
extern uint16_t km_size, km_attr, km_mode, km_page;
extern uint8_t  km_ok;

void     farmem_probe(void);
void     farmem_release(void);  /* the OS's blocks back, on the way out */
uint16_t farmem_held(void);     /* both still allocated: km_held */

#endif /* GEM4XE_HIPROBE_H */
