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
             $(B6)/res/bank6502.o \
             $(B6)/res/v6farmem6502.o $(B6)/res/far6502s.o $(B6)/res/antic6502s.o $(B6)/res/gemdata.o $(B6)/res/mul6502s.o $(B6)/res/enter6502s.o
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

$(B6)/pre/vdi.o:       $(B6)/w/vdi.c src/vdi/vdi.c src/vdi/fillpat.c src/vdi/sintbl.c $(HDRS6)
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
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/asm/$*.b.s --tu $* $(BANKS6) --index $(B6)/v6.idx --fast-frames --fast-veneers
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
A6_BANKS6  = $(BANKS6) --bank wind=11 --bank wind_b=12 --bank menu=13 --bank menu_b=14 --bank evt=15 --bank ctl=16 --bank abi=17 --bank rsrc=18 --bank gemdos=19 --bank gemdos_b=20 --bank gdos=21
A6_RES     = $(B6)/res/a6_aes.o $(B6)/res/stub6502.o $(B6)/res/anpack6502.o \
             $(B6)/res/muldiv6502.o $(B6)/res/font6x6.o \
             $(B6)/res/bank6502.o \
             $(B6)/res/a6farmem6502.o $(B6)/res/far6502s.o $(B6)/res/antic6502s.o $(B6)/res/gemdata.o $(B6)/res/ctx6502s.o \
             $(B6)/res/irq6502s.o $(B6)/res/mul6502s.o $(B6)/res/gate6502s.o $(B6)/res/cio6502s.o $(B6)/res/enter6502s.o \
             $(B6)/res/g6z6502.o
A6_UNITS   = vdi dev_antic antic font pointer v6farmem objc graf wind menu event ctrl proc appl grlib form a6tree a6ctx a6irq a6evt a6cio abi abistub rsrc alert gemdos dos con clock
A6_PRE     = $(A6_UNITS:%=$(B6)/pre/%.o)
A6_BANK    = $(A6_UNITS:%=$(B6)/a6bank/%.o)

$(B6)/res/a6_aes.o: src/a6_aes.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -I src/aes -I src/sys -c $< -o $@
$(B6)/res/a6farmem6502.o: src/sys6502/farmem6502.c $(HDRS6)
	@mkdir -p $(dir $@)
	$(CC6) $(CFLAGS6) -DB6_CODE_BANKS=21 -c $< -o $@

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
# form_alert (docs/6502.md, 5b-5), beside the resource loader: rs_obfix
# is its, and the alert icons are in this bank too (tools/gemdata.py)
$(B6)/w/alert.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="rsrc"\n#include "../../../src/aes/alert.c"\n' > $@
# GEMDOS (docs/6502.md, 5b-4): gemdos.c in two banks, the second taken by
# BANK_TEXT in the file; the DOS's identity, the console and the clock in
# a third
$(B6)/w/gemdos.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="gemdos"\n#include "../../../src/sys/gemdos.c"\n' > $@
$(B6)/w/dos.c:    ; @mkdir -p $(dir $@); printf '#pragma clang section text="gdos"\n#include "../../../src/sys/dos.c"\n' > $@
$(B6)/w/con.c:    ; @mkdir -p $(dir $@); printf '#pragma clang section text="gdos"\n#include "../../../src/sys/con.c"\n' > $@
$(B6)/w/clock.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="gdos"\n#include "../../../src/sys/clock.c"\n' > $@
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
$(B6)/pre/a6irq.o:  $(B6)/w/a6irq.c src/sys6502/irq6502.c src/sys/irqclock.inc $(HDRS6)
$(B6)/pre/a6evt.o:  $(B6)/w/a6evt.c src/a6_evt.c $(HDRS6)
$(B6)/pre/a6cio.o:  $(B6)/w/a6cio.c src/sys/cio.c $(HDRS6)
$(B6)/pre/abi.o:    $(B6)/w/abi.c src/sys/abi.c $(HDRS6)
$(B6)/pre/abistub.o: $(B6)/w/abistub.c src/sys6502/abistub6502.c $(HDRS6)
$(B6)/pre/rsrc.o:   $(B6)/w/rsrc.c src/aes/rsrc.c build/gemdata.h $(HDRS6)
$(B6)/pre/alert.o:  $(B6)/w/alert.c src/aes/alert.c build/gemdata.h build/lang_rsc.h $(HDRS6)
$(B6)/pre/gemdos.o: $(B6)/w/gemdos.c src/sys/gemdos.c build/version.h $(HDRS6)
$(B6)/pre/dos.o:    $(B6)/w/dos.c src/sys/dos.c $(HDRS6)
$(B6)/pre/con.o:    $(B6)/w/con.c src/sys/con.c $(HDRS6)
$(B6)/pre/clock.o:  $(B6)/w/clock.c src/sys/clock.c $(HDRS6)
$(B6)/pre/wind.o $(B6)/pre/menu.o $(B6)/pre/event.o $(B6)/pre/proc.o $(B6)/pre/appl.o \
$(B6)/pre/ctrl.o $(B6)/pre/grlib.o $(B6)/pre/form.o $(B6)/pre/a6tree.o $(B6)/pre/a6ctx.o $(B6)/pre/a6irq.o $(B6)/pre/a6evt.o $(B6)/pre/a6cio.o $(B6)/pre/abi.o $(B6)/pre/abistub.o $(B6)/pre/rsrc.o $(B6)/pre/alert.o $(B6)/pre/gemdos.o $(B6)/pre/dos.o $(B6)/pre/con.o $(B6)/pre/clock.o: EXTRA6 = -I src/aes -I build -I src/sys
$(B6)/pre/wind.o $(B6)/pre/menu.o $(B6)/pre/event.o $(B6)/pre/proc.o $(B6)/pre/appl.o \
$(B6)/pre/ctrl.o $(B6)/pre/grlib.o $(B6)/pre/form.o $(B6)/pre/a6tree.o $(B6)/pre/a6ctx.o $(B6)/pre/a6irq.o $(B6)/pre/a6evt.o $(B6)/pre/a6cio.o $(B6)/pre/abi.o $(B6)/pre/abistub.o $(B6)/pre/rsrc.o $(B6)/pre/alert.o $(B6)/pre/gemdos.o $(B6)/pre/dos.o $(B6)/pre/con.o $(B6)/pre/clock.o:
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) --no-cross-call $(EXTRA6) -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))

$(B6)/a6.idx: $(A6_PRE) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(A6_BANKS6) $(A6_UNITS:%=$(B6)/asm/%.s)

$(B6)/a6bank/%.o: $(B6)/pre/%.o $(B6)/a6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(B6)/a6asm
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/a6asm/$*.b.s --tu $* $(A6_BANKS6) --index $(B6)/a6.idx --switch-in-bank --fast-frames --fast-veneers
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

# packed (--pack, docs/6502.md "Disk"): its banks unpacked as they load
# tests/host/test_g6z6502.py reads these: built before the host tests,
# or it compares a fresh a6.elf with a stale a6.xex (a suite did, once a
# source was touched mid-run).  Only when cc6502 is here, as Makefile's
# own test-host prerequisites are only when cc65816 is.
test-host: $(if $(wildcard $(CC6)),build/a6.xex build/desk6.g6a build/cpanel6.g6a build/p6mprog.g6a)

build/a6.xex: build/a6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py tools/mkxex.py
	python3 tools/bsp6502/mkxex6502.py --pack $< $@

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

# ...and on each PORTB size the 6502 build serves: 320K (RAMBO and COMPY),
# 576K and 1088K.  Every other gate is 1088K, where every free PORTB bit is
# a bank bit; below that BASIC or the self test is not, and the probe must
# refuse those candidates without spoiling a bank it kept.
test-b6probe: build/a6-boot.atr
	python3 tests/emu/b6_probe.py

# ---- step 5c-1: a program of several banks (tests/emu/p6m_prog.py) ------
# src/p6m_prog.c in three banks of its own (BANK_TEXT pb1..pb3) and the
# kit's gemlib.c in bank 2, banked by bankasm.py with the program's own
# trampoline (--trampoline _pcall, src/app/crt6502m.s); its veneers,
# runtime and data in the RAM under the OS ROM (src/app/gemappm6502.scm).
# A .G6A of format 2 (mkxex6502.py), on a boot disk of its own as
# P6PROG.G6A, which A6 loads into three banks from the far heap.
P6M        = $(B6)/p6m
P6M_BANKS  = --bank pb1=1 --bank pb2=2 --bank pb3=3
P6M_UNITS  = p6m_prog gemlib
P6M_OBJ    = $(P6M)/crt6502m.o $(P6M)/gemabi6502.o $(P6M)/farm6502.o $(P6M)/enter6502.o $(P6M_UNITS:%=$(P6M)/bank/%.o)
$(P6M)/w/p6m_prog.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb1"\n#include "../../../../src/p6m_prog.c"\n' > $@
$(P6M)/w/gemlib.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb2"\n#include "../../../../src/app/gemlib.c"\n' > $@
$(P6M)/pre/%.o: $(P6M)/w/%.c src/p6m_prog.c src/app/gemlib.c src/app/gem.h src/portab.h
	@mkdir -p $(dir $@) $(P6M)/asm
	$(CC6) $(KITFLAGS6) --no-cross-call -c $< -o $@ --assembly-source=$(P6M)/asm/$(notdir $(@:.o=.s))
$(P6M)/p6m.idx: $(P6M_UNITS:%=$(P6M)/pre/%.o) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(P6M_BANKS) $(P6M_UNITS:%=$(P6M)/asm/%.s)
$(P6M)/bank/%.o: $(P6M)/pre/%.o $(P6M)/p6m.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(P6M)/basm
	python3 tools/bsp6502/bankasm.py $(P6M)/asm/$*.s $(P6M)/basm/$*.b.s --tu $* $(P6M_BANKS) \
	    --index $(P6M)/p6m.idx --trampoline _pcall --switch-in-bank --fast-frames
	python3 tools/bsp6502/bankcheck.py --asm $(P6M)/basm/$*.b.s $(P6M_BANKS) --index $(P6M)/p6m.idx
	$(AS6) --core 6502 $(P6M)/basm/$*.b.s -o $@
# gem.h's fa_* (step 5c-2): in no bank -- they map the window -- so not
# through bankasm, and into the shared RAM with the runtime.  Assembly
# since speed 4 (the C was a memcpy and a frame a field).
$(P6M)/farm6502.o: src/app/farm6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
# cc6502's frame helpers, faster (bankasm --fast-frames): the system's
$(P6M)/enter6502.o: src/sys6502/enter6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(P6M)/crt6502m.o: src/app/crt6502m.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
$(P6M)/gemabi6502.o: src/app/gemabi6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
build/p6mprog.elf: $(P6M_OBJ) src/app/gemappm6502.scm tools/bsp6502/bankcheck.py
	$(LN6) src/app/gemappm6502.scm $(P6M_OBJ) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/p6mprog.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/p6mprog.map --elf $@ || { rm -f $@; exit 1; }
build/p6mprog.g6a: build/p6mprog.elf tools/bsp6502/mkxex6502.py tools/mkxex.py
	python3 tools/bsp6502/mkxex6502.py --g6a --pack $< $@
build/a6m-boot.atr: build/a6.xex build/p6mprog.g6a build/p6prog.rsc
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep --compact --add build/p6mprog.g6a P6PROG.G6A \
	    --add build/p6prog.rsc P6PROG.RSC
test-p6m: build/a6m-boot.atr
	python3 tests/emu/p6m_prog.py
# ...and refused on an Axlon, whose $CFFF needs the ROM in
test-p6ma: build/a6m-boot.atr
	python3 tests/emu/p6m_prog.py --axlon 4096K

# ---- step 5c-3: the desktop, a program of several banks ---------------------
# src/desk/*.c, the 65C816's desktop, built for the 6502 through gem.h's
# far accessors (step 5c-2): eight banks -- desktop.c, deskobj.c,
# deskfun.c in two and deskwin.c in three (BANK_TEXT in the files),
# deskcmd.c with the kit's gemlib.c -- and P6M's start-up, gates and far
# helpers.
# On build/a6d-boot.atr as P6PROG.G6A, with the desktop's resources.
D6         = $(B6)/d6
D6_BANKS   = --bank pb1=1 --bank pb2=2 --bank pb3=3 --bank pb4=4 --bank pb5=5 \
             --bank pb6=6 --bank pb7=7 --bank pb8=8
D6_UNITS   = desktop deskobj deskfun deskwin deskcmd gemlib
D6_OBJ     = $(P6M)/crt6502m.o $(P6M)/gemabi6502.o $(P6M)/farm6502.o $(P6M)/enter6502.o $(D6_UNITS:%=$(D6)/bank/%.o)
D6_DEPS    = $(wildcard src/desk/*.c) src/desk/desk.h build/deskrsc.h src/app/gemlib.c src/app/gem.h src/portab.h
$(D6)/w/desktop.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb1"\n#include "../../../../src/desk/desktop.c"\n' > $@
$(D6)/w/deskobj.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb6"\n#include "../../../../src/desk/deskobj.c"\n' > $@
$(D6)/w/deskfun.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb2"\n#include "../../../../src/desk/deskfun.c"\n' > $@
$(D6)/w/deskwin.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb3"\n#include "../../../../src/desk/deskwin.c"\n' > $@
$(D6)/w/deskcmd.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb5"\n#include "../../../../src/desk/deskcmd.c"\n' > $@
$(D6)/w/gemlib.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb5"\n#include "../../../../src/app/gemlib.c"\n' > $@
# the assembly is what bankasm reads (cc6502 writes no object with it)
$(D6)/asm/%.s: $(D6)/w/%.c $(D6_DEPS)
	@mkdir -p $(dir $@)
	$(CC6) $(KITFLAGS6) -I build -I src/desk --no-cross-call -c $< -o $(D6)/asm/$*.tmp --assembly-source=$@
$(D6)/d6.idx: $(D6_UNITS:%=$(D6)/asm/%.s) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(D6_BANKS) $(D6_UNITS:%=$(D6)/asm/%.s)
$(D6)/bank/%.o: $(D6)/asm/%.s $(D6)/d6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(D6)/basm
	python3 tools/bsp6502/bankasm.py $< $(D6)/basm/$*.b.s --tu $* $(D6_BANKS) \
	    --index $(D6)/d6.idx --trampoline _pcall --switch-in-bank --fast-frames
	python3 tools/bsp6502/bankcheck.py --asm $(D6)/basm/$*.b.s $(D6_BANKS) --index $(D6)/d6.idx
	$(AS6) --core 6502 $(D6)/basm/$*.b.s -o $@
build/desk6.elf: $(D6_OBJ) src/app/gemappm6502.scm tools/bsp6502/bankcheck.py
	$(LN6) src/app/gemappm6502.scm $(D6_OBJ) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/desk6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/desk6.map --elf $@ || { rm -f $@; exit 1; }
build/desk6.g6a: build/desk6.elf tools/bsp6502/mkxex6502.py tools/mkxex.py
	python3 tools/bsp6502/mkxex6502.py --g6a --pack $< $@
# D1: A6 and the desktop's resources; D2: the desktop itself -- a floppy
# has not room for A6's 21 banks and its eight (A6 tries D2: after D1:)
build/a6d-boot.atr: build/a6.xex build/desktop.rsc build/deskicon.rsc build/prefs.rsc
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ AUTORUN.SYS --sweep --compact \
	    --add build/desktop.rsc DESKTOP.RSC --add build/deskicon.rsc DESKICON.RSC --add build/prefs.rsc PREFS.RSC
test-d6: build/a6d-boot.atr build/a6d-desk.atr
	python3 tests/emu/d6_desk.py

# the sampler silent through SIO (src/sys/cio.c), with real serial timing
test-d6sio: build/a6d-boot.atr build/a6d-desk.atr
	python3 tests/emu/d6_sio.py

build/a6d-desk.atr: build/desk6.g6a build/p6mprog.g6a build/cpanel6.g6a build/cpanel.rsc \
                    build/general.rsc build/color.rsc
	@test -n "$(SRC_MYDOS)" || { echo "no MyDOS fixture: set [dos].mydos in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_MYDOS)" $< $@ P6PROG.G6A --sweep --compact \
	    --add build/p6mprog.g6a P6M.G6A --add build/cpanel6.g6a CPANEL.G6A \
	    --add build/cpanel.rsc CPANEL.RSC --add build/general.rsc GENERAL.RSC \
	    --add build/color.rsc COLOR.RSC

# ---- step 5f: the control panel as a 6502 program --------------------------
# src/apps/cpanel.c with General and Color built in (src/apps/cpanel6.c is
# its main): the panel's main and General in bank 1, the panel in banks
# 2-4 (BANK_TEXT in the file), Color and the kit's gemlib.c in bank 5;
# each module's cpx_init renamed, and
# its header compiled in from its .cpxh (tools/mkcpx.py --c).  CPANEL.G6A
# on the desktop's disk with its resources.
C6P        = $(B6)/cp6
C6P_BANKS  = --bank pb1=1 --bank pb2=2 --bank pb3=3 --bank pb4=4 --bank pb5=5
C6P_UNITS  = cpanel6 cpanel general color gemlib
C6P_OBJ    = $(P6M)/crt6502m.o $(P6M)/gemabi6502.o $(P6M)/farm6502.o $(P6M)/enter6502.o $(C6P_UNITS:%=$(C6P)/bank/%.o)
C6P_DEPS   = src/apps/cpanel.c src/apps/general.c src/apps/color.c src/apps/cpanel6.c src/app/cpx.h \
             src/app/gemlib.c src/app/gem.h src/portab.h build/cpanelrsc.h build/generalrsc.h \
             build/colorrsc.h build/cp6_general.h build/cp6_color.h
build/cp6_general.h: src/apps/general.cpxh tools/mkcpx.py
	python3 tools/mkcpx.py --c $< cp6_general $@
build/cp6_color.h: src/apps/color.cpxh tools/mkcpx.py
	python3 tools/mkcpx.py --c $< cp6_color $@
$(C6P)/w/cpanel6.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb1"\n#include "../../../../src/apps/cpanel6.c"\n' > $@
$(C6P)/w/cpanel.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb2"\n#include "../../../../src/apps/cpanel.c"\n' > $@
$(C6P)/w/general.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb1"\n#define cpx_init general_cpx_init\n#include "../../../../src/apps/general.c"\n' > $@
$(C6P)/w/color.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb5"\n#define cpx_init color_cpx_init\n#include "../../../../src/apps/color.c"\n' > $@
$(C6P)/w/gemlib.c:  ; @mkdir -p $(dir $@); printf '#pragma clang section text="pb5"\n#include "../../../../src/app/gemlib.c"\n' > $@
$(C6P)/asm/%.s: $(C6P)/w/%.c $(C6P_DEPS)
	@mkdir -p $(dir $@)
	$(CC6) $(KITFLAGS6) -I build -I src/apps --no-cross-call -c $< -o $(C6P)/asm/$*.tmp --assembly-source=$@
$(C6P)/cp6.idx: $(C6P_UNITS:%=$(C6P)/asm/%.s) tools/bsp6502/bankasm.py
	python3 tools/bsp6502/bankasm.py --index $@ $(C6P_BANKS) $(C6P_UNITS:%=$(C6P)/asm/%.s)
$(C6P)/bank/%.o: $(C6P)/asm/%.s $(C6P)/cp6.idx tools/bsp6502/bankasm.py tools/bsp6502/bankcheck.py
	@mkdir -p $(dir $@) $(C6P)/basm
	python3 tools/bsp6502/bankasm.py $< $(C6P)/basm/$*.b.s --tu $* $(C6P_BANKS) \
	    --index $(C6P)/cp6.idx --trampoline _pcall --switch-in-bank --fast-frames
	python3 tools/bsp6502/bankcheck.py --asm $(C6P)/basm/$*.b.s $(C6P_BANKS) --index $(C6P)/cp6.idx
	$(AS6) --core 6502 $(C6P)/basm/$*.b.s -o $@
build/cpanel6.elf: $(C6P_OBJ) src/app/gemappm6502.scm tools/bsp6502/bankcheck.py
	$(LN6) src/app/gemappm6502.scm $(C6P_OBJ) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/cpanel6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/cpanel6.map --elf $@ || { rm -f $@; exit 1; }
build/cpanel6.g6a: build/cpanel6.elf tools/bsp6502/mkxex6502.py tools/mkxex.py
	python3 tools/bsp6502/mkxex6502.py --g6a --pack $< $@

# cc6502's generated assembly, for a call made with a scratch argument
# (tools/bsp6502/b6asm.py): every banked unit's, so the programs first.
b6asm: build/a6.elf build/v6.elf build/c6.elf build/i6.elf build/p6mprog.elf
	python3 tools/bsp6502/b6asm.py

.PHONY: test-a6 test-e6 test-e6n test-p6 test-p6a test-b6probe test-p6m test-p6ma test-d6 test-d6sio test-f6a b6asm

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
# cc6502's frame helpers, faster: in place of clib's enter.o and stack.o
$(B6)/res/enter6502s.o: src/sys6502/enter6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@
# the G4Z unpacker, and the load-time hook that uses it (mkxex6502.py --pack)
$(B6)/res/g6z6502.o: src/sys6502/g6z6502.s
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
