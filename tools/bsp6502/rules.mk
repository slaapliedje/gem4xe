# rules.mk -- the 6502 build (docs/6502.md), included by the Makefile.
#
# The test disks are MyDOS's, the program as AUTORUN.SYS: the fixture
# DOS 2 variant (DOS II+/D 6.4) uses extended memory itself, and on the
# MiSTer core's real SIO a bank load under it stopped part way.

# Step 1: the VDI and its ANTIC device in banks of the PORTB window, a
# resident test program calling it through veneers, on a stock 6502.
#
#   resident   src/v6_vdi.c, the trampoline (src/sys6502/bank6502.s), the
#              C stand-ins for what is not here yet, the faces and
#              tables, and the veneers resident code and function
#              pointers need (a call from a bank has its veneer there)
#   banks 1-3  vdi.c, cut by its two BANK_TEXTs   (sections vdi_a, vdi_b, vdi_c)
#   bank 4     dev_antic.c's functions, font.c and pointer.c   (section dev)
#   bank 5     antic.c                                  (section antic)
#   bank 6     src/sys/farmem.c, the far heap's allocator, and src/v6_tree.c,
#              the object library's test               (section far);
#              the far_* helpers resident (src/sys6502/farmem6502.c), and
#              the heap in the PORTB banks after these ten
#   banks 7-9  src/aes/objc.c, the object library, cut by its BANK_TEXTs
#                                         (sections objc, objc_b, objc_c)
#   bank 10    src/aes/graf.c, the AES's drawing        (section graf);
#              its tables (build/gemdata.c) resident
#
# Banked files are compiled with --no-cross-call: the optimiser's shared
# fragments go to section `code` whatever the pragma says -- 6.6 KB of
# them, resident, where room is scarcest -- so they are not made.
#
# A banked file is compiled through a wrapper that names its section, to
# assembly (build/b6502/asm/); tools/bsp6502/bankasm.py, given the
# program's index of which bank each function is in, sends every
# reference across a bank through a veneer it writes into that assembly;
# the link map and the linked code are then checked by
# tools/bsp6502/bankcheck.py before the binary is made.

CAL6      ?= $(HOME)/dev/toolchains/calypsi-6502
CC6        = $(CAL6)/bin/cc6502
AS6        = $(CAL6)/bin/as6502
LN6        = $(CAL6)/bin/ln6502
CFLAGS6    = -O2 --core 6502 -I src -I src/vdi -DGEM4XE_BANKED -Werror=int-conversion
B6         = build/b6502
DEVANTIC6  = -DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=and_ -DGEM4XE_DEV_ANTIC
HDRS6      = src/portab.h $(wildcard src/vdi/*.h src/sys/*.h src/antic/*.h src/aes/*.h)

# the bank of each section, for bankasm.py and bankcheck.py: the same as
# gem6502.scm's
BANKS6     = --bank vdi_a=1 --bank vdi_b=2 --bank vdi_c=3 --bank dev=4 --bank antic=5 --bank far=6 --bank objc=7 --bank objc_b=8 --bank objc_c=9 --bank graf=10

V6_RES     = $(B6)/res/v6_vdi.o $(B6)/res/stub6502.o $(B6)/res/ciostub6502.o $(B6)/res/irqstub6502.o $(B6)/res/v6stub.o $(B6)/res/anpack6502.o \
             $(B6)/res/muldiv6502.o $(B6)/res/font6x6.o \
             $(B6)/res/fillpat.o $(B6)/res/sintbl.o $(B6)/res/bank6502.o \
             $(B6)/res/v6farmem6502.o $(B6)/res/far6502s.o $(B6)/res/antic6502s.o $(B6)/res/gemdata.o $(B6)/res/mul6502s.o
V6_UNITS   = vdi dev_antic antic font pointer v6farmem objc graf v6tree
V6_PRE     = $(V6_UNITS:%=$(B6)/pre/%.o)
V6_BANK    = $(V6_UNITS:%=$(B6)/bank/%.o)

$(B6)/res/%.o: src/%.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -c $< -o $@
$(B6)/res/%.o: src/sys6502/%.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -c $< -o $@
$(B6)/res/%.o: src/vdi/%.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -c $< -o $@
# the far_* helpers: the heap's banks start after the code's ten
$(B6)/res/v6farmem6502.o: src/sys6502/farmem6502.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -DB6_CODE_BANKS=10 -c $< -o $@
# the AES's tables, generated (tools/gemdata.py), resident
$(B6)/res/gemdata.o: build/gemdata.c build/gemdata.h $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -I src/aes -I build -c $< -o $@
$(B6)/res/bank6502.o: src/sys6502/bank6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@

# the wrappers: a section, then the file as it is
$(B6)/w/vdi.c:       ; @mkdir -p $(dir $@); printf '#pragma clang section text="vdi_a"\n#include "../../../src/vdi/vdi.c"\n' > $@
$(B6)/w/dev_antic.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/dev_antic.c"\n' > $@
$(B6)/w/antic.c:     ; @mkdir -p $(dir $@); printf '#pragma clang section text="antic"\n#include "../../../src/antic/antic.c"\n' > $@
$(B6)/w/font.c:      ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/font.c"\n' > $@
$(B6)/w/pointer.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/pointer.c"\n' > $@
$(B6)/w/objc.c:      ; @mkdir -p $(dir $@); printf '#pragma clang section text="objc"\n#include "../../../src/aes/objc.c"\n' > $@
$(B6)/w/graf.c:      ; @mkdir -p $(dir $@); printf '#pragma clang section text="graf"\n#include "../../../src/aes/graf.c"\n' > $@
$(B6)/w/v6tree.c:    ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/v6_tree.c"\n' > $@
$(B6)/w/v6farmem.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/sys/farmem.c"\n' > $@

$(B6)/pre/vdi.o:       $(B6)/w/vdi.c src/vdi/vdi.c $(HDRS6)
$(B6)/pre/vdi.o:       EXTRA6 = --no-inline
$(B6)/pre/dev_antic.o: $(B6)/w/dev_antic.c src/vdi/dev_antic.c $(HDRS6)
$(B6)/pre/dev_antic.o: EXTRA6 = $(DEVANTIC6)
$(B6)/pre/antic.o:     $(B6)/w/antic.c src/antic/antic.c $(HDRS6)
$(B6)/pre/font.o:      $(B6)/w/font.c src/vdi/font.c $(HDRS6)
$(B6)/pre/pointer.o:   $(B6)/w/pointer.c src/vdi/pointer.c $(HDRS6)
$(B6)/pre/v6farmem.o:  $(B6)/w/v6farmem.c src/sys/farmem.c $(HDRS6)
$(B6)/pre/v6farmem.o:  EXTRA6 = -I src/sys
$(B6)/pre/v6tree.o:    $(B6)/w/v6tree.c src/v6_tree.c $(HDRS6)
$(B6)/pre/objc.o:      $(B6)/w/objc.c src/aes/objc.c $(HDRS6)
$(B6)/pre/graf.o:      $(B6)/w/graf.c src/aes/graf.c build/gemdata.h $(HDRS6)
$(B6)/pre/objc.o $(B6)/pre/graf.o: EXTRA6 = -I src/aes -I build
$(V6_PRE):
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) --no-cross-call $(EXTRA6) -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))

# which bank every public banked function is in, program-wide: a call
# within a bank goes straight there, a call from another bank through a
# veneer in the caller's bank (tools/bsp6502/bankasm.py)
$(B6)/v6.idx: $(V6_PRE) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(BANKS6) $(V6_UNITS:%=$(B6)/asm/%.s)

$(B6)/bank/%.o: $(B6)/pre/%.o $(B6)/v6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@)
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/asm/$*.b.s --tu $* $(BANKS6) --index $(B6)/v6.idx
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/asm/$*.b.s $(BANKS6) --index $(B6)/v6.idx
	$(AS6) --core 6502 $(B6)/asm/$*.b.s -o $@

build/v6.elf: $(V6_RES) $(V6_BANK) tools/bsp6502/gem6502.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/gem6502.scm $(V6_RES) $(V6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/v6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/v6.map --elf $@ || { rm -f $@; exit 1; }

build/v6.xex: build/v6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/v6-boot.atr: build/v6.xex
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep

test-v6: build/v6-boot.atr
	python3 tests/emu/v6_vdi.py

.PHONY: test-v6

# ---- step 4c: the AES on one process (tests/emu/a6_aes.py) -----------------
# V6's banks and six more: wind.c in two (wind, wind_b; the rectangle pool
# in wind's, BANK_DATA), menu.c in two (menu, menu_b), the events, the
# processes and appl in evt, the control manager in ctl.  Its bank objects
# are its own (build/b6502/a6bank/): a program's index names its banks.
A6_BANKS6  = $(BANKS6) --bank wind=11 --bank wind_b=12 --bank menu=13 --bank menu_b=14 --bank evt=15 --bank ctl=16 --bank abi=17 --bank rsrc=18
A6_RES     = $(B6)/res/a6_aes.o $(B6)/res/stub6502.o $(B6)/res/anpack6502.o \
             $(B6)/res/muldiv6502.o $(B6)/res/font6x6.o \
             $(B6)/res/fillpat.o $(B6)/res/sintbl.o $(B6)/res/bank6502.o \
             $(B6)/res/a6farmem6502.o $(B6)/res/far6502s.o $(B6)/res/antic6502s.o $(B6)/res/gemdata.o $(B6)/res/ctx6502s.o \
             $(B6)/res/irq6502s.o $(B6)/res/mul6502s.o $(B6)/res/gate6502s.o $(B6)/res/cio6502s.o
A6_UNITS   = vdi dev_antic antic font pointer v6farmem objc graf wind menu event ctrl proc appl grlib form a6tree a6ctx a6irq a6evt a6cio abi abistub rsrc
A6_PRE     = $(A6_UNITS:%=$(B6)/pre/%.o)
A6_BANK    = $(A6_UNITS:%=$(B6)/a6bank/%.o)

$(B6)/res/a6_aes.o: src/a6_aes.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -I src/aes -I src/sys -c $< -o $@
$(B6)/res/a6farmem6502.o: src/sys6502/farmem6502.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -DB6_CODE_BANKS=18 -c $< -o $@

$(B6)/w/wind.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="wind"\n#include "../../../src/aes/wind.c"\n' > $@
$(B6)/w/menu.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="menu"\n#include "../../../src/aes/menu.c"\n' > $@
$(B6)/w/event.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="evt"\n#include "../../../src/aes/event.c"\n' > $@
$(B6)/w/proc.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="evt"\n#include "../../../src/aes/proc.c"\n' > $@
$(B6)/w/appl.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="evt"\n#include "../../../src/aes/appl.c"\n' > $@
$(B6)/w/ctrl.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="ctl"\n#include "../../../src/aes/ctrl.c"\n' > $@
$(B6)/w/grlib.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="ctl"\n#include "../../../src/aes/grlib.c"\n' > $@
$(B6)/w/form.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="ctl"\n#include "../../../src/aes/form.c"\n' > $@
$(B6)/w/a6ctx.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="evt"\n#include "../../../src/sys6502/ctx6502.c"\n' > $@
$(B6)/w/a6irq.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="evt"\n#include "../../../src/sys6502/irq6502.c"\n' > $@
$(B6)/w/a6evt.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/a6_evt.c"\n' > $@
$(B6)/w/a6cio.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/sys/cio.c"\n' > $@
$(B6)/w/abi.c:    ; @mkdir -p $(dir $@); printf '#pragma clang section text="abi"\n#include "../../../src/sys/abi.c"\n' > $@
$(B6)/w/abistub.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="abi"\n#include "../../../src/sys6502/abistub6502.c"\n' > $@
$(B6)/w/rsrc.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="rsrc"\n#include "../../../src/aes/rsrc.c"\n' > $@
$(B6)/w/a6tree.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/a6_tree.c"\n' > $@
$(B6)/pre/wind.o:   $(B6)/w/wind.c src/aes/wind.c build/gemdata.h $(HDRS6)
$(B6)/pre/menu.o:   $(B6)/w/menu.c src/aes/menu.c build/gemdata.h $(HDRS6)
$(B6)/pre/event.o:  $(B6)/w/event.c src/aes/event.c build/gemdata.h $(HDRS6)
$(B6)/pre/proc.o:   $(B6)/w/proc.c src/aes/proc.c $(HDRS6)
$(B6)/pre/appl.o:   $(B6)/w/appl.c src/aes/appl.c build/gemdata.h $(HDRS6)
$(B6)/pre/ctrl.o:   $(B6)/w/ctrl.c src/aes/ctrl.c build/gemdata.h $(HDRS6)
$(B6)/pre/grlib.o:  $(B6)/w/grlib.c src/aes/grlib.c build/gemdata.h $(HDRS6)
$(B6)/pre/form.o:   $(B6)/w/form.c src/aes/form.c build/gemdata.h $(HDRS6)
$(B6)/pre/a6tree.o: $(B6)/w/a6tree.c src/a6_tree.c $(HDRS6)
$(B6)/pre/a6ctx.o:  $(B6)/w/a6ctx.c src/sys6502/ctx6502.c $(HDRS6)
$(B6)/pre/a6irq.o:  $(B6)/w/a6irq.c src/sys6502/irq6502.c $(HDRS6)
$(B6)/pre/a6evt.o:  $(B6)/w/a6evt.c src/a6_evt.c $(HDRS6)
$(B6)/pre/a6cio.o:  $(B6)/w/a6cio.c src/sys/cio.c $(HDRS6)
$(B6)/pre/abi.o:    $(B6)/w/abi.c src/sys/abi.c $(HDRS6)
$(B6)/pre/abistub.o: $(B6)/w/abistub.c src/sys6502/abistub6502.c $(HDRS6)
$(B6)/pre/rsrc.o:   $(B6)/w/rsrc.c src/aes/rsrc.c build/gemdata.h $(HDRS6)
$(B6)/pre/wind.o $(B6)/pre/menu.o $(B6)/pre/event.o $(B6)/pre/proc.o $(B6)/pre/appl.o \
$(B6)/pre/ctrl.o $(B6)/pre/grlib.o $(B6)/pre/form.o $(B6)/pre/a6tree.o $(B6)/pre/a6ctx.o $(B6)/pre/a6irq.o $(B6)/pre/a6evt.o $(B6)/pre/a6cio.o $(B6)/pre/abi.o $(B6)/pre/abistub.o $(B6)/pre/rsrc.o: EXTRA6 = -I src/aes -I build -I src/sys
$(B6)/pre/wind.o $(B6)/pre/menu.o $(B6)/pre/event.o $(B6)/pre/proc.o $(B6)/pre/appl.o \
$(B6)/pre/ctrl.o $(B6)/pre/grlib.o $(B6)/pre/form.o $(B6)/pre/a6tree.o $(B6)/pre/a6ctx.o $(B6)/pre/a6irq.o $(B6)/pre/a6evt.o $(B6)/pre/a6cio.o $(B6)/pre/abi.o $(B6)/pre/abistub.o $(B6)/pre/rsrc.o:
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) --no-cross-call $(EXTRA6) -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))

$(B6)/a6.idx: $(A6_PRE) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(A6_BANKS6) $(A6_UNITS:%=$(B6)/asm/%.s)

$(B6)/a6bank/%.o: $(B6)/pre/%.o $(B6)/a6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(B6)/a6asm
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/a6asm/$*.b.s --tu $* $(A6_BANKS6) --index $(B6)/a6.idx --switch-in-bank
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/a6asm/$*.b.s $(A6_BANKS6) --index $(B6)/a6.idx
	$(AS6) --core 6502 $(B6)/a6asm/$*.b.s -o $@

build/a6.elf: $(A6_RES) $(A6_BANK) tools/bsp6502/a6.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/a6.scm $(A6_RES) $(A6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/a6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/a6.map --elf $@ || { rm -f $@; exit 1; }

# ---- step 5a: a program in a bank of its own (tests/emu/p6_prog.py) -------
# Built as a kit program is: src/app/gem.h and gemlib.c, the 6502's gates
# and start-up, linked whole into one bank by src/app/gemapp6502.scm, and
# (step 5b) written as P6PROG.G6A onto A6's boot disk, which A6 reads
# into a 16 KB bank taken from the far heap (src/a6_evt.c,
# far_alloc_piece).
P6_OBJ     = $(B6)/p6/crt6502.o $(B6)/p6/gemabi6502.o $(B6)/p6/p6_prog.o $(B6)/p6/gemlib.o
KITFLAGS6  = -O2 --core 6502 -I src/app -I src -Werror=int-conversion
$(B6)/p6/p6_prog.o: src/p6_prog.c src/app/gem.h src/portab.h
	@mkdir -p $(dir $@)
	$(CC6) $(KITFLAGS6) -c $< -o $@
$(B6)/p6/gemlib.o: src/app/gemlib.c src/app/gem.h src/portab.h
	@mkdir -p $(dir $@)
	$(CC6) $(KITFLAGS6) -c $< -o $@
$(B6)/p6/crt6502.o: src/app/crt6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/p6/gemabi6502.o: src/app/gemabi6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
build/p6prog.elf: $(P6_OBJ) src/app/gemapp6502.scm
	$(LN6) src/app/gemapp6502.scm $(P6_OBJ) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/p6prog.map > /dev/null

build/a6.xex: build/a6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/p6prog.g6a: build/p6prog.elf tools/bsp6502/mkxex6502.py
	python3 tools/bsp6502/mkxex6502.py --g6a $< $@

# P6PROG.RSC, the resource the program loads (step 5b-3)
build/p6prog.rsc: tools/p6rsc.py tools/rsc.py tools/aesref.py
	python3 tools/p6rsc.py $@

build/a6-boot.atr: build/a6.xex build/p6prog.g6a build/p6prog.rsc
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep --compact --add build/p6prog.g6a P6PROG.G6A \
	    --add build/p6prog.rsc P6PROG.RSC

test-a6: build/a6-boot.atr
	python3 tests/emu/a6_aes.py

# ---- step 4e: the input poll and the event loop (tests/emu/a6_evt.py) ------
# The same program, told to go on: src/a6_evt.c (banked, `far`) installs
# the interrupt handlers (src/sys6502/irq6502.c banked in `evt`, its .s
# resident) and runs an application's loop.
test-e6: build/a6-boot.atr
	python3 tests/emu/a6_evt.py

# ...and on an NTSC machine: the frame, and so the AES's tick, is 17 ms
# there, and the gate holds the tick and the double-click window to it.
test-e6n: build/a6-boot.atr
	python3 tests/emu/a6_evt.py --ntsc

# step 5a: a kit-built program in a bank of its own, through the gate
test-p6: build/a6-boot.atr
	python3 tests/emu/p6_prog.py

# ...and on an Axlon's banks, switched by $CFFF: a 4 MB one (255 banks,
# the MiSTer core's largest) on a 130XE, whose banks src/sys6502/bank6502.s
# takes over PORTB's and patches every bank switch to reach.  Needs an
# AltirraSDL with ilmenit/AltirraSDL#114: before it, 4096K gave 2 MB.
test-p6a: build/a6-boot.atr
	python3 tests/emu/p6_prog.py --axlon 4096K

# cc6502's generated assembly, for a call made with a scratch argument
# (tools/bsp6502/b6asm.py): every banked unit's, so the programs first.
b6asm: build/a6.elf build/v6.elf build/c6.elf build/i6.elf
	python3 tools/bsp6502/b6asm.py

.PHONY: test-a6 test-e6 test-e6n test-p6 test-p6a test-f6a b6asm

# ---- step 3a: the far heap (tests/emu/f6_far.py) ---------------------------
# src/sys/farmem.c's allocator and src/f6_bank.c banked in section `far`;
# the test program, the resident far_* helpers (src/sys6502/farmem6502.c)
# and the trampoline resident.  One code bank: the helpers' far banks
# start after it (B6_CODE_BANKS).
F6_BANKS6  = --bank far=1
F6_RES     = $(B6)/res/f6_far.o $(B6)/res/f6farmem6502.o $(B6)/res/far6502s.o $(B6)/res/bank6502.o \
             $(B6)/res/eput6502.o
F6_UNITS   = farmem f6_bank
F6_BANK    = $(F6_UNITS:%=$(B6)/bank/%.o)

$(B6)/res/f6farmem6502.o: src/sys6502/farmem6502.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -DB6_CODE_BANKS=1 -c $< -o $@

$(B6)/res/eput6502.o: src/sys6502/eput6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@

$(B6)/w/farmem.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/sys/farmem.c"\n' > $@
$(B6)/w/f6_bank.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/f6_bank.c"\n' > $@
$(B6)/pre/farmem.o:  $(B6)/w/farmem.c src/sys/farmem.c $(HDRS6)
$(B6)/pre/f6_bank.o: $(B6)/w/f6_bank.c src/f6_bank.c $(HDRS6)
$(B6)/pre/farmem.o $(B6)/pre/f6_bank.o:
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) -I src/sys --no-cross-call -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))
$(B6)/f6.idx: $(F6_UNITS:%=$(B6)/pre/%.o) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(F6_BANKS6) $(F6_UNITS:%=$(B6)/asm/%.s)

$(B6)/bank/farmem.o $(B6)/bank/f6_bank.o: $(B6)/bank/%.o: $(B6)/pre/%.o $(B6)/f6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@)
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/asm/$*.b.s --tu $* $(F6_BANKS6) --index $(B6)/f6.idx
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/asm/$*.b.s $(F6_BANKS6) --index $(B6)/f6.idx
	$(AS6) --core 6502 $(B6)/asm/$*.b.s -o $@

build/f6.elf: $(F6_RES) $(F6_BANK) tools/bsp6502/f6.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/f6.scm $(F6_RES) $(F6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/f6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/f6.map --elf $@ || { rm -f $@; exit 1; }

build/f6.xex: build/f6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/f6-boot.atr: build/f6.xex
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep

test-f6: build/f6-boot.atr
	python3 tests/emu/f6_far.py

# ...on a 4 MB Axlon: 63 far banks, the last one written (far bank 63)
test-f6a: build/f6-boot.atr
	python3 tests/emu/f6_far.py --axlon 4096K

.PHONY: test-f6

# ---- step 4d: the context switch (tests/emu/c6_ctx.py) ---------------------
# test-m27's runner on the 6502: two contexts in banks of their own (cxa,
# cxb), the far heap's allocator in a third, the switch resident
# (src/sys6502/ctx6502.s; its C half, ctx6502.c, in a bank: far here, evt
# in A6).
C6_BANKS6  = --bank far=1 --bank cxa=2 --bank cxb=3
C6_RES     = $(B6)/res/c6_ctx.o $(B6)/res/ctx6502s.o \
             $(B6)/res/stub6502.o $(B6)/res/ciostub6502.o $(B6)/res/bank6502.o $(B6)/res/c6farmem6502.o $(B6)/res/far6502s.o
C6_UNITS   = v6farmem c6procs c6ctx
C6_PRE     = $(C6_UNITS:%=$(B6)/pre/%.o)
C6_BANK    = $(C6_UNITS:%=$(B6)/c6bank/%.o)

$(B6)/res/c6_ctx.o: src/c6_ctx.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -I src/sys -c $< -o $@
$(B6)/res/ctx6502s.o: src/sys6502/ctx6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/res/c6farmem6502.o: src/sys6502/farmem6502.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -DB6_CODE_BANKS=3 -c $< -o $@

$(B6)/w/c6procs.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="cxa"\n#include "../../../src/c6_procs.c"\n' > $@
$(B6)/w/c6ctx.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="far"\n#include "../../../src/sys6502/ctx6502.c"\n' > $@
$(B6)/pre/c6procs.o: $(B6)/w/c6procs.c src/c6_procs.c $(HDRS6)
$(B6)/pre/c6ctx.o:   $(B6)/w/c6ctx.c src/sys6502/ctx6502.c $(HDRS6)
$(B6)/pre/c6procs.o $(B6)/pre/c6ctx.o:
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) --no-cross-call -I src/sys -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))

$(B6)/c6.idx: $(C6_PRE) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(C6_BANKS6) $(C6_UNITS:%=$(B6)/asm/%.s)

$(B6)/c6bank/%.o: $(B6)/pre/%.o $(B6)/c6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(B6)/c6asm
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/c6asm/$*.b.s --tu $* $(C6_BANKS6) --index $(B6)/c6.idx
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/c6asm/$*.b.s $(C6_BANKS6) --index $(B6)/c6.idx
	$(AS6) --core 6502 $(B6)/c6asm/$*.b.s -o $@

build/c6.elf: $(C6_RES) $(C6_BANK) tools/bsp6502/c6.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/c6.scm $(C6_RES) $(C6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/c6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/c6.map --elf $@ || { rm -f $@; exit 1; }

build/c6.xex: build/c6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/c6-boot.atr: build/c6.xex
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep

test-c6: build/c6-boot.atr
	python3 tests/emu/c6_ctx.py

.PHONY: test-c6

# ---- step 4d: the interrupt handlers (tests/emu/i6_irq.py) -----------------
# src/i6_irq.c resident with the handlers (src/sys6502/irq6502.s and .c);
# the VDI's pointer layer, src/vdi/pointer.c, in one bank (dev) to select
# the trak-ball through.
I6_BANKS6  = --bank dev=1
I6_RES     = $(B6)/res/i6_irq.o $(B6)/res/irq6502.o $(B6)/res/irq6502s.o \
             $(B6)/res/bank6502.o
I6_UNITS   = pointer
I6_PRE     = $(I6_UNITS:%=$(B6)/pre/%.o)
I6_BANK    = $(I6_UNITS:%=$(B6)/i6bank/%.o)

$(B6)/res/i6_irq.o: src/i6_irq.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -I src/sys -c $< -o $@
# a filled row's middle, in the ANTIC bank (src/sys6502/antic6502.s)
$(B6)/res/antic6502s.o: src/sys6502/antic6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
# the far_* helpers' hot half (src/sys6502/far6502.s)
$(B6)/res/cio6502s.o: src/sys6502/cio6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/res/gate6502s.o: src/sys6502/gate6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/res/far6502s.o: src/sys6502/far6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/res/mul6502s.o: src/sys6502/mul6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(B6)/res/irq6502s.o: src/sys6502/irq6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@

$(B6)/i6.idx: $(I6_PRE) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(I6_BANKS6) $(I6_UNITS:%=$(B6)/asm/%.s)

$(B6)/i6bank/%.o: $(B6)/pre/%.o $(B6)/i6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(B6)/i6asm
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/i6asm/$*.b.s --tu $* $(I6_BANKS6) --index $(B6)/i6.idx
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/i6asm/$*.b.s $(I6_BANKS6) --index $(B6)/i6.idx
	$(AS6) --core 6502 $(B6)/i6asm/$*.b.s -o $@

build/i6.elf: $(I6_RES) $(I6_BANK) tools/bsp6502/i6.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/i6.scm $(I6_RES) $(I6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/i6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/i6.map --elf $@ || { rm -f $@; exit 1; }

build/i6.xex: build/i6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/i6-boot.atr: build/i6.xex
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep

test-i6: build/i6-boot.atr
	python3 tests/emu/i6_irq.py

.PHONY: test-i6
