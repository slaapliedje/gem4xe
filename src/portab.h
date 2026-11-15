/* SPDX-License-Identifier: LGPL-2.1-or-later */
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

#if defined(__CALYPSI__) && !defined(__CALYPSI_TARGET_6502__)

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
#define BANK_TEXT(s)                    /* the 6502's banks: nothing here */
#define memcpy_far   __memcpy_far
/* Not __disable_interrupts(): an SEI in native mode can start an IRQ
 * storm on Windows Altirra (src/sys/sei.s). */
void irq_sei(void);
#define cpu_sei()    irq_sei()
#define cpu_cli()    __enable_interrupts()

#elif defined(__CALYPSI_TARGET_6502__)

/* THE 6502 BUILD (docs/6502.md) -- a survey block, not a design.  There is
 * no 24-bit address on a 6502: memory beyond 64 KB is a PORTB bank in the
 * $4000-$7FFF window, reached only through code that switches it.  So FAR
 * is defined away here only to see what else breaks; every FAR in the C is
 * a place the 6502 build needs a banked accessor instead (docs/6502.md,
 * "the far data"), and nothing built with this block runs. */
#define FAR
#define NEAR
#define TINY         __attribute__((zpage))
#define SIMPLE_CALL
#define TASK
#define SAVEDS
#define SECTION(s)   __attribute__((section(s)))
/* THE BANKS (docs/6502.md).  BANK_TEXT("name") sends the code after it to
 * section `name`, which the link map puts in a bank of its own; every
 * reference across a bank then goes through a veneer that
 * tools/bsp6502/bankasm.py writes into the file's assembly. */
#define BANK_STR_(x) #x
#define BANK_TEXT(s) _Pragma(BANK_STR_(clang section text=s))
#define memcpy_far   memcpy
void irq_sei(void);
#define cpu_sei()    irq_sei()
#define cpu_cli()    irq_cli()
void irq_cli(void);

#else
#error "portab.h: no dialect for this compiler -- add one here"
#endif

/* A FAR SOURCE OF BYTES (docs/6502.md, step 3b): a face's strip, a form,
 * a buffer far_alloc gave.  On the 65C816 it is a far pointer, read where
 * it points; on the 6502 there is no such pointer -- what is beyond 64 KB
 * is a PORTB bank in the window -- so it is the 24-bit address itself,
 * read through far_read8 (src/sys/farmem.h), which reads bank 0 directly.
 * Adding a byte count to one means the same on both.  FAR_IDX8 is the
 * subscripted form, for code whose 65C816 object must stay as it was. */
#ifdef __CALYPSI_TARGET_6502__
typedef unsigned long far_src8;
#define FAR_RD8(a)      far_read8((unsigned long)(a))
#define FAR_IDX8(a, i)  far_read8((unsigned long)(a) + (i))
#else
typedef const unsigned char FAR *far_src8;
#define FAR_RD8(a)      (*(const unsigned char FAR *)(a))
#define FAR_IDX8(a, i)  (((const unsigned char FAR *)(a))[i])
#endif

/* ...and a far STRING, the same way: a TEDINFO's text, an icon's label.
 * FAR_CHAR(p) is the character at p. */
#ifdef __CALYPSI_TARGET_6502__
typedef unsigned long far_str;
#define FAR_CHAR(p)     ((char)far_read8((unsigned long)(p)))
#else
typedef const char FAR *far_str;
#define FAR_CHAR(p)     (*(p))
#endif

#endif /* GEM4XE_PORTAB_H */
