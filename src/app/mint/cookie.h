/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* mint/cookie.h -- the ST's cookie jar, which this machine has not got.
 *
 * A TOS program asks the jar what the machine is (_MCH), what the CPU
 * is (_CPU), whether MiNT is there; a port written against mintlib does
 * it through Getcookie().  There is no jar here and no system variable
 * to hang one on, so Getcookie() answers C_NOTFOUND for every cookie,
 * which is the answer a well-written program takes as "plain TOS" and
 * defaults on -- qed does, with its _IDT cookie (docs/qed.md).  The
 * names and values are mintlib's, so a comparison against either
 * compiles and reads the same. */
#ifndef GEM4XE_MINT_COOKIE_H
#define GEM4XE_MINT_COOKIE_H

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

static inline int Getcookie(long cookie, long *value)
{
    (void)cookie;
    (void)value;
    return C_NOTFOUND;
}

#endif
