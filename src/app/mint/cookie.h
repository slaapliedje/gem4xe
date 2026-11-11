/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* mint/cookie.h -- the ST's cookie jar, as this machine answers it.
 *
 * A TOS program asks the jar what the machine is (_MCH), what the CPU
 * is (_CPU), whether MiNT is there; a port written against mintlib does
 * it through Getcookie().  There is no jar in memory here and no system
 * variable to hang one on, so the system answers the cookies itself,
 * through MiNT's Ssystem(S_GETCOOKIE), which is what mintlib's Getcookie
 * asks first (phase 150; before it, nothing was found):
 *
 *   _MCH, _VDO  $FFFFFFFF: no ST-compatible machine, no ST video --
 *               EmuTOS's values for a machine that is not an Atari
 *   _SND        0: no YM2149, no DMA sound
 *   _CPU        0: nothing beyond a 68000 to rely on
 *   G4XE        gem4xe, its version: major << 8 | minor
 *
 * and nothing else -- never NVDI, MiNT or _IDT, so a program that asks
 * for those still takes "plain TOS" and defaults, as qed does with _IDT
 * (docs/qed.md).  The names and values are mintlib's, so a comparison
 * against either compiles and reads the same. */
#ifndef GEM4XE_MINT_COOKIE_H
#define GEM4XE_MINT_COOKIE_H

#include "gem.h"                /* Ssystem */

#define C_FOUND      0
#define C_NOTFOUND  (-1)

/* The cookies a port is likeliest to ask for, spelled as mintlib spells
 * them: a long of four characters. */
#define C__CPU  0x5F435055L     /* '_CPU' */
#define C__MCH  0x5F4D4348L     /* '_MCH' */
#define C__VDO  0x5F56444FL     /* '_VDO' */
#define C__SND  0x5F534E44L     /* '_SND' */
#define C__FDC  0x5F464443L     /* '_FDC' */
#define C__IDT  0x5F494454L     /* '_IDT' */
#define C__AKP  0x5F414B50L     /* '_AKP' */
#define C_MiNT  0x4D694E54L     /* 'MiNT' */
#define C_NVDI  0x4E564449L     /* 'NVDI' */
#define C_FSMC  0x46534D43L     /* 'FSMC' */
#define C_G4XE  0x47345845L     /* 'G4XE': gem4xe's own */

/* The value into *value (which may be 0), and C_FOUND; C_NOTFOUND when
 * the jar has no such cookie. */
static inline int Getcookie(long cookie, long *value)
{
    long v;

    if (Ssystem(S_GETCOOKIE, cookie, (long)&v) != 0)
        return C_NOTFOUND;
    if (value)
        *value = v;
    return C_FOUND;
}

#endif
