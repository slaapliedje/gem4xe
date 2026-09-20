/* portab.h -- the compiler's dialect, in one place.
 *
 * gem4xe is C, but a 65816 C compiler has to say things ISO C cannot:
 * which address space a pointer or an object lives in, how a function is
 * entered, where the linker should put a thing.  Every such word the
 * tree uses is defined here and nowhere else, so that building with a
 * second compiler means a second block in this file and a second set of
 * assembly sources -- not a sweep through 26,000 lines of C.  The C is
 * kept free of the dialect by tests/host/test_portab.py, and the
 * generators under tools/ emit these names too.
 *
 * What each name means, for whoever writes the next block:
 *
 *   FAR         qualifies a pointer or an object to say it is addressed
 *               with 24 bits -- anywhere in the machine, not only in the
 *               bank the data segment lives in.  A FAR pointer is four
 *               bytes; a plain one is two and addressed through DB.
 *   NEAR        the opposite, said explicitly: an object placed in the
 *               near data bank even where the surrounding code would
 *               default to something else.
 *   TINY        an object placed in the direct page, so that the hot
 *               loops that use it get the short addressing mode.  Only
 *               file-scope statics carry it.
 *   SIMPLE_CALL a function whose arguments are passed in registers rather
 *               than on the stack.  gem4xe's three system-call stubs use
 *               it so the parameter block's address arrives in X:C, which
 *               is where the COP handler looks.
 *   TASK        a function that is entered but never returned from, and
 *               so need not preserve anything on entry: main().
 *   SECTION(s)  place the object or function in the named linker section.
 *   memcpy_far  memcpy whose pointers are both FAR.  The library's own
 *               memcpy takes near pointers under the small data model.
 *   cpu_sei()   disable interrupts; the instruction of the same name.
 *   cpu_cli()   enable them.
 */
#ifndef GEM4XE_PORTAB_H
#define GEM4XE_PORTAB_H

#if defined(__CALYPSI__)

#include <calypsi/intrinsics65816.h>

#define FAR          __far
#define NEAR         __near
#define TINY         __attribute__((tiny))
#define SIMPLE_CALL  __simple_call
#define TASK         __task
/* A function that establishes its OWN direct page and data bank on entry
 * and gives the caller's back on exit.  What it costs is `phb phd`, two
 * immediate loads and `pld plb`; what it buys is a function that can be
 * called from a separately linked module and still find its own globals.
 * That is exactly a control panel extension's entry point (src/app/cpx.h)
 * -- without it a module reads its host's memory at its own addresses,
 * silently, which is this project's oldest failure shape. */
#define SAVEDS       __attribute__((saveds))
#define SECTION(s)   __attribute__((section(s)))
#define memcpy_far   __memcpy_far
#define cpu_sei()    __disable_interrupts()
#define cpu_cli()    __enable_interrupts()

#else
#error "portab.h: no dialect for this compiler -- add one here"
#endif

#endif /* GEM4XE_PORTAB_H */
