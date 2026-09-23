# The gem4xe application kit.
#
#     make                          hello.g4a, from example/hello.c
#     make APP=mine.c               mine.g4a
#     make APP=mine.c NAME=prog     prog.g4a
#     make APP=mine.c ASM="a.s b.s" mine.g4a, with your assembly linked in
#     make clean
#
# THREE KINDS OF THING, and KIND says which:
#
#     make KIND=prg APP=example/hello.c   a program        install as .PRG
#     make KIND=acc APP=example/acc.c     a desk accessory install as .ACC
#     make KIND=cpx APP=example/cpx.c     a panel module   install as .CPX
#
# All three come out as a .g4a -- that is the CONTAINER, and it is the
# same format for all of them.  The EXTENSION you install it under is the
# ROLE, and it is what the system reads: the desktop launches a .PRG, the
# AES loads a .ACC and a .CPX from its own directory at start-up.  See
# README.md, "What kind of thing are you building".
#
# A .acc is built exactly like a program; what makes it one is the shape
# of its main() (example/acc.c).  A .cpx is built --data-model=large and
# gets its main() from lib/cpxmain.c, so you write cpx_init() instead
# (example/cpx.c).
#
# A program is linked THREE times -- once at the placeholder addresses
# lib/gemapp.scm gives it, once with its near region a page higher and
# once with its far region a bank higher -- and tools/mkg4a.py takes the
# bytes that moved as the loader's fixup lists.  Neither the compiler
# nor the linker emits relocations for a program that is placed at load
# time, so they are derived rather than declared; see the comment at the
# top of tools/mkg4a.py.
#
# The three budget numbers are yours to raise, and the link enforces
# them:
#
#   BSS    bytes of near memory that carry no bits -- your stack, your
#          uninitialised data.  It includes STACK.
#   BITS   bytes that do -- constants, the initial values of data.
#   STACK  of BSS, how much is stack.  The AES calls back into your
#          program (a redraw inside form_do, say), so leave room.
#
# All of it comes out of the application pool: 14,336 bytes in bank $00
# for the WHOLE machine, shared with the desktop, every desk accessory
# and every control panel extension resident.  About 8 KB of that is
# free with what gem4xe ships, so ask for what you need and no more --
# bank $00 is the scarce thing on a machine with 14.9 MB.  Your CODE is
# not in that budget: it goes in a far bank of its own, and you have
# 64 KB of it.

CALYPSI ?= $(HOME)/dev/toolchains/calypsi-65816
KIND    ?= prg
APP     ?= example/hello.c
ASM     ?=
NAME    ?= $(basename $(notdir $(APP)))

# A module is --data-model=large because the panel hands it 24-bit
# addresses -- its parameter block, its 64 bytes, its callbacks -- and a
# small-data program cannot follow one.  The linker refuses to mix
# runtime models, so the whole kit is rebuilt in that model beside it and
# Calypsi's own clib-lc-ld.a replaces clib-lc-sd.a.
ifeq ($(KIND),cpx)
  DATAMODEL ?= large
  LDLIB     ?= clib-lc-ld.a
  KIT_EXTRA  = $(B)/cpxmain.o
  BSS       ?= 1024
  BITS      ?= 256
  STACK     ?= 512
else
  DATAMODEL ?= small
  LDLIB     ?= clib-lc-sd.a
  KIT_EXTRA  =
  BSS       ?= 2048
  BITS      ?= 256
  STACK     ?= 256
endif

CC  = $(CALYPSI)/bin/cc65816
AS  = $(CALYPSI)/bin/as65816
LD  = $(CALYPSI)/bin/ln65816
# The code model must be large -- your code is in a far bank and every
# call to it is a jsl -- and the data model small, because the near
# region is addressed through DB.  gem4xe itself is built this way.
CFLAGS = --code-model=large --data-model=$(DATAMODEL) -O2 -I include

# $(B)/clib.o is lib/clib.c: memcpy, memset and the str* functions.  They
# are here rather than taken from clib-lc-sd.a because Calypsi's come from
# Apache NuttX and Apache 2.0 cannot be linked into a GPLv2 binary -- and
# gem4xe is GPLv2.  If your program is under something else you may use
# the library's instead; if it is GPL, use these.
#
# ASM names assembly sources of your own, linked after the program in the
# order given.  Code goes in `farcode`, and a function returns with rtl:
# every call into it is a jsl.
# ONE BUILD DIRECTORY PER DATA MODEL.  A program is small-data and a
# module is large-data, the linker refuses to mix the two, and an object
# left over from the other model is NEWER than its source -- so `make
# KIND=cpx` followed by `make` used to link a large-data library against
# a small-data program and stop with a runtime-model mismatch.  Keeping
# them apart means the two builds coexist and neither needs a clean.
B = build/$(DATAMODEL)

ASM_OBJS = $(patsubst %.s,$(B)/%.o,$(notdir $(ASM)))
OBJS = $(B)/crt_gemapp.o $(B)/gemabi.o $(B)/gemlib.o $(B)/gemstat.o \
       $(B)/gemtime.o $(B)/gemcompat.o $(B)/gemstub.o $(B)/clib.o \
       $(KIT_EXTRA) $(B)/$(NAME).o $(ASM_OBJS)
LDOPT = lib/gemapp.scm $(OBJS) $(LDLIB) --rtattr exit=simplified \
        --cstartup gemapp --stack-size $(STACK)

all: $(NAME).g4a

$(B):
	@mkdir -p $(B)

$(B)/%.o: lib/%.s | $(B)
	$(AS) -o $@ $<

$(B)/%.o: lib/%.c include/gem.h | $(B)
	$(CC) $(CFLAGS) -o $@ $<

# The bindings without interprocedural cross-jumping.  At -O2 the compiler
# shares one identical tail across the GEMDOS bindings and parks it inside
# one function's section, so under --data-model=large a program that calls
# Fread links clock, Tgettimeofday and Psystem it never calls -- 352 bytes,
# and more with every binding added.  Without the sharing each binding is
# its own section: 3-13 bytes more per binding you CALL, nothing for the
# rest.  Keep this flag if you build the bindings with your own rules.
$(B)/gemlib.o: lib/gemlib.c include/gem.h | $(B)
	$(CC) $(CFLAGS) --no-interprocedural-cross-jump -o $@ $<

# gemstub.c is nine functions that end the same way, which is the same
# shape -- without the flag, printf links the six stubs it never calls.
$(B)/gemstub.o: lib/gemstub.c include/gem.h | $(B)
	$(CC) $(CFLAGS) --no-interprocedural-cross-jump -o $@ $<

# THE CALENDAR, AT -O0, and that is measured rather than cautious.  At -O1
# and above this compiler mangles civil_from_days (lib/gemtime.c names the
# two shapes): the month comes back 0, a comparison used as a number adds
# 255 instead of 1, and a plain 32-bit store through a pointer writes 0.
# The same source under gcc is right, and -O0 is right, so it is the
# optimiser.  It costs 589 bytes on a file that formats a date, and a
# wrong date is not worth 589 bytes.  Do not "tidy" this line.
#
# gemtime.c is time(), gmtime(), localtime(), mktime(), strftime() and
# clock(); gemcompat.c is stricmp(), strlwr(), opendir() and the rest of
# what an ST source reaches for.  Both are in OBJS above because the kit
# SHIPS them and the README promises them -- they were shipped and never
# compiled until 0.6.1, so a program that called clock() did not link.
$(B)/gemtime.o: lib/gemtime.c include/gem.h include/time.h | $(B)
	$(CC) --code-model=large --data-model=$(DATAMODEL) -O0 -I include -o $@ $<

$(B)/gemcompat.o: lib/gemcompat.c include/gem.h | $(B)
	$(CC) $(CFLAGS) -o $@ $<

$(B)/$(NAME).o: $(APP) include/gem.h | $(B)
	$(CC) $(CFLAGS) -o $@ $<

# A module's main(): it reads the slot address the AES left in the
# command tail, calls YOUR cpx_init(), publishes what you return and ends
# with Ptermres so the module stays resident.  You do not write this.
$(B)/cpxmain.o: lib/cpxmain.c include/cpx.h include/gem.h | $(B)
	$(CC) $(CFLAGS) -o $@ $<

$(foreach s,$(ASM),$(eval $(B)/$(basename $(notdir $(s))).o: $(s) | $(B) ; $$(AS) -o $$@ $$<))

# At the placeholders, then a page up, then a bank up.
$(B)/$(NAME).elf: $(OBJS) lib/gemapp.scm
	$(LD) $(LDOPT) -o $@ --list-file $(B)/$(NAME).map \
	    --memories-expression "(app-layout #x1000 #x020000 $(BSS) $(BITS))"
$(B)/$(NAME)-near.elf: $(OBJS) lib/gemapp.scm
	$(LD) $(LDOPT) -o $@ \
	    --memories-expression "(app-layout #x1100 #x020000 $(BSS) $(BITS))"
$(B)/$(NAME)-far.elf: $(OBJS) lib/gemapp.scm
	$(LD) $(LDOPT) -o $@ \
	    --memories-expression "(app-layout #x1000 #x030000 $(BSS) $(BITS))"

$(NAME).g4a: $(B)/$(NAME).elf $(B)/$(NAME)-near.elf $(B)/$(NAME)-far.elf
	python3 tools/mkg4a.py $(B)/$(NAME).elf $(B)/$(NAME)-near.elf \
	    $(B)/$(NAME)-far.elf $@ --syms $(B)/$(NAME).sym

clean:
	rm -rf build $(NAME).g4a

.PHONY: all clean
