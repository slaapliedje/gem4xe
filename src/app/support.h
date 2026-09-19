/* support.h -- mintlib's grab-bag of non-ISO string functions, which ST
 * sources reach for by reflex and no ISO C library has.
 *
 * mintlib spells this file <support.h>; Pure C programs get the same
 * names from <string.h>.  Both work here: <string.h> is the compiler's
 * and declares the ISO ones, and these are declared here and implemented
 * in lib/gemcompat.c.
 *
 * WHY THE KIT CARRIES THEM RATHER THAN THE COMPILER'S LIBRARY.  Two
 * reasons, and the second is the one that matters.  They are not in
 * Calypsi's library at all; and the parts of that library gem4xe does
 * lean on are Apache-2.0, which is incompatible with this tree's GPLv2
 * (docs/licence.md) -- lib/clib.c already stands in front of eight ISO
 * functions for that reason, and these belong beside them.
 *
 * The case folding is ASCII.  A GEMDOS file name is upper-case ASCII and
 * that is what these are used on; nothing here knows about the Atari's
 * international characters, and a program that needs those should say so
 * rather than find out from a sort order.
 */
#ifndef GEM4XE_SUPPORT_H
#define GEM4XE_SUPPORT_H

#include <stddef.h>

int   stricmp(const char *a, const char *b);
int   strnicmp(const char *a, const char *b, size_t n);
char *strlwr(char *s);
char *strupr(char *s);

#endif /* GEM4XE_SUPPORT_H */
