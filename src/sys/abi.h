/* abi.h -- the application binary interface.
 *
 * An application reaches gem4xe with a COP instruction: COP #$56 'V' for
 * the VDI, COP #$41 'A' for the AES, COP #$44 'D' for GEMDOS,
 * X:C holding the address of its parameter block (src/app/gem.h documents
 * the application's side).  The handler in abi.s
 * catches the trap, records where the block is and which signature was used,
 * and calls gem_entry() on gem4xe's own direct page, data bank and stack.
 * gem_entry() copies the block's inputs into gem4xe's arrays, runs the call,
 * and copies the outputs back: the DRI entry-shim discipline, which is what
 * lets the VDI's argument-free handlers and the AES's fixed arrays serve a
 * caller whose arrays are anywhere in the 16 MB.
 *
 * An application is a far subroutine of gem4xe's: app_run() calls its entry
 * with gem_api_sp set to gem4xe's stack, so that a COP from the application
 * -- which runs on a stack of its own, in its own bank-$00 pool -- is served
 * on gem4xe's, where the depth the VDI and AES need is known to exist.
 */
#ifndef GEM4XE_ABI_H
#define GEM4XE_ABI_H

#include "portab.h"
#include <stdint.h>

/* The COP signature bytes, which the application's gemabi.s makes and
 * abi.s checks (tests/host/test_bind.py keeps the three in step).  They
 * are in $02-$7F because the rest is taken: $00 and $01 are Rapidus OS's
 * -- its system emulation call and kmem, which its SpartaDOS X modules
 * make as well -- and $80-$FF are reserved by WDC for new instructions.
 * They were the ST's trap numbers, $73, $C8 and $01, until that was
 * pointed out; a .g4a built with those is format 1 or 2, and the loader
 * refuses it by name (APP_E_OLDSDK, src/sys/app.h). */
#define ABI_VDI    0x56     /* 'V' */
#define ABI_AES    0x41     /* 'A' */
#define ABI_GEMDOS 0x44     /* 'D' */

/* Written by the handler in abi.s before gem_entry() runs. */
extern uint32_t gem_pb;        /* the parameter block: X:C at the COP */
extern uint8_t  gem_which;     /* the signature byte after the COP opcode */

/* The stack switch.  gem_api_sp is gem4xe's S while an application runs
 * (0 otherwise: a COP from gem4xe's own code stays on the current stack);
 * gem_depth counts nested COPs so only the outermost switches. */
extern uint16_t gem_api_sp;
extern uint8_t  gem_depth;

extern uint16_t gem_calls;     /* COPs served, every process's */
/* Of those, the ones the APPLICATION made.  A gate that wants to know
 * where a program has got to has to count only that program's calls, and
 * gem_calls stopped being that the moment a desk accessory could be
 * resident beside it (src/aes/proc.h). */
extern uint16_t app_calls;
extern uint16_t gem_bad;    /* COPs refused: signature, opcode, bank */
extern uint16_t gem_badop;  /* the opcode the last refusal was in */

/* Nonzero when the OS takes COPs of its own -- Rapidus OS, whose @:SYSDEF
 * says its native interrupt services are there -- so that a COP which is
 * not one of gem4xe's three is passed to it by abi.s.  Zero: it is
 * refused and counted in gem_bad.  abi_probe_os() sets it, once, at start. */
extern uint8_t gem_cop_pass;
void abi_probe_os(void);

/* Set by GEMDOS when a program ends itself -- Pterm, Pterm0, Ptermres, or
 * ^C at the console (src/sys/gemdos.c) -- for the handler in abi.s: the
 * COP that said so does not return to the program, and the code in its
 * block goes to the program's loader as main()'s value would have.
 * gem_entry clears it before every call. */
extern uint8_t gem_term;

void gem_entry(void);          /* the C side of the handler */

/* Call an application's entry point (a far address) as a subroutine and
 * return what its main() returned -- or the code it gave Pterm, if it
 * ended that way.  abi.s. */
SIMPLE_CALL int16_t app_run(uint32_t entry);

#endif /* GEM4XE_ABI_H */
