/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* clib.c -- the C library functions gem4xe uses, so that it uses nobody
 * else's -- plus two it does NOT use itself, memcmp and memchr, which are
 * here for the same reason on an application's behalf; and malloc and
 * free, which it refuses (at the end).
 *
 * WHY THIS EXISTS, AND IT IS NOT ABOUT CODE.
 *
 * Calypsi's C library carries these as `libs/libc/string/lib_*.c`, taken
 * from Apache NuttX and licensed Apache 2.0 -- which is INCOMPATIBLE
 * WITH GPLv2, the licence this tree is under and the one it inherits
 * from EmuTOS.  Linking them put Apache-2.0 object code inside GEM.COM,
 * and there are only two ways out of that: distribute the result under
 * GPLv3, which Apache 2.0 is compatible with and which the donor's AES
 * files permit only by an argument about what silence means; or link
 * none of it.  This is linking none of it.  It is also what the project
 * plan recommended on size grounds before the licence was looked at.
 *
 * WHAT IS LEFT AFTER THIS, so that nobody reads a clean link as a clean
 * licence: the compiler's own runtime -- _Dp, _Mul16, _UDivMod16,
 * _JmpIndLong, _ValueSwitch16, _MoveLongNear, __memcpy_far, _FillDP2,
 * __initialize_sections and the startup -- is still the library's, 815
 * bytes of it, under "Permission to use with the Calypsi tool chain is
 * hereby granted".  That is a smaller problem than this one was and of a
 * different kind: the tool chain's licence expressly permits producing
 * software for retro machines, so the intent is plain, and what does not
 * close is the GPL's own requirement that the whole work be
 * GPL-licensable -- the gap GCC's Runtime Library Exception fills.
 * docs/licence.md has it in full.
 *
 * These are the ISO C functions, written to the standard's own wording
 * and nothing else's.  They are all cold: six strlen, five strcpy, two
 * memset, one each of the rest across the whole engine, and none in a
 * drawing path -- so a byte at a time is the right shape, and they go in
 * `farcode` with the rest of the C, costing bank $00 nothing.
 */
#include "portab.h"
#include <stddef.h>
#include <time.h>              /* for clock_t: the refusal at the end */

void *memcpy(void *dst, const void *src, size_t n)
{
    char *d = (char *)dst;
    const char *s = (const char *)src;

    while (n--)
        *d++ = *s++;
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    char *d = (char *)dst;

    while (n--)
        *d++ = (char)c;
    return dst;
}

size_t strlen(const char *s)
{
    size_t n = 0;

    while (s[n])
        n++;
    return n;
}

char *strcpy(char *dst, const char *src)
{
    char *d = dst;

    while ((*d++ = *src++) != 0)
        ;
    return dst;
}

char *strcat(char *dst, const char *src)
{
    char *d = dst;

    while (*d)
        d++;
    while ((*d++ = *src++) != 0)
        ;
    return dst;
}

/* The comparisons are on UNSIGNED chars, which the standard requires and
 * which matters here: a filename from a DOS can hold $80-$FF, and a
 * signed compare would order those before every letter. */
int strcmp(const char *a, const char *b)
{
    const unsigned char *p = (const unsigned char *)a;
    const unsigned char *q = (const unsigned char *)b;

    while (*p && *p == *q) {
        p++;
        q++;
    }
    return (int)*p - (int)*q;
}

int strncmp(const char *a, const char *b, size_t n)
{
    const unsigned char *p = (const unsigned char *)a;
    const unsigned char *q = (const unsigned char *)b;

    while (n && *p && *p == *q) {
        p++;
        q++;
        n--;
    }
    return n ? (int)*p - (int)*q : 0;
}

/* The terminator counts as part of the string, so strchr(s, 0) finds it. */
char *strchr(const char *s, int c)
{
    char want = (char)c;

    for (;;) {
        if (*s == want)
            return (char *)s;
        if (!*s)
            return 0;
        s++;
    }
}

/* THESE TWO HAVE NO CALLER IN THE ENGINE, and are here anyway.  An
 * application built with the kit links this same file (tools/mksdk.py),
 * and a program that reaches for memcmp or memchr -- both of which a
 * ported ST program does by reflex -- would otherwise have them
 * satisfied QUIETLY from the vendor's clib-lc-ld.a, putting Apache-2.0
 * object code in a GPLv2 binary with nothing to show for it in a link
 * map anybody reads.  RetroWP's platform layer writes its own pair for
 * exactly this reason (retroplat backends/atari/clib_gem4xe.c); it
 * should not have to.  The linker leaves out what nothing references,
 * so the engine pays nothing for them. */
int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *p = (const unsigned char *)a;
    const unsigned char *q = (const unsigned char *)b;

    while (n--) {
        if (*p != *q)
            return (int)*p - (int)*q;
        p++;
        q++;
    }
    return 0;
}

/* Unlike strchr, the terminator is nothing special here: memchr searches
 * n bytes whatever they are, and answers NULL if the byte is not there. */
void *memchr(const void *s, int c, size_t n)
{
    const unsigned char *p = (const unsigned char *)s;
    unsigned char want = (unsigned char)c;

    while (n--) {
        if (*p == want)
            return (void *)p;
        p++;
    }
    return 0;
}

/* MALLOC AND FREE REFUSE, AT LINK TIME.  An application's heap block is zero
 * bytes (src/app/gemapp.scm) because memory above bank $00 is GEMDOS's to hand
 * out -- Malloc -- so the library's malloc, which a program ported from the ST
 * reaches for by reflex, used to link cleanly and then answer NULL to every
 * call: a program found its fonts missing and drew no text, with nothing
 * failing.  It is Apache 2.0 besides (above).  These stand in front of the
 * library's and call a function that does not exist, so a program that uses
 * them does not link, and the error names the fix.  One that does not call
 * them pays nothing: the linker leaves out what nothing references, in both
 * data models. */
extern void gem4xe_has_no_heap__use_GEMDOS_Malloc(void);

void *malloc(size_t n)
{
    (void)n;
    gem4xe_has_no_heap__use_GEMDOS_Malloc();
    return 0;
}

void free(void *p)
{
    (void)p;
    gem4xe_has_no_heap__use_GEMDOS_Malloc();
}

/* clock() is NOT here, and that is deliberate.  `clock.o` is in the
 * library this links against, and for a while this file refused it by
 * name, because nothing on the machine drove the library's tick and a
 * program asking for elapsed time got a number with no meaning -- the
 * malloc failure again.  There is a tick now: Tgettimeofday, from the
 * system's ~4 kHz timer, and clock() is built on it in the kit's
 * gemlib.c, beside the binding it calls.  It cannot be here, because
 * this file is gem4xe's own too, and gem4xe has no call gate to make
 * a call through.  An application links gemlib.c and gets the real one;
 * the engine references neither and the library's is never pulled. */
