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
CFLAGS6    = -O2 --core 6502 -I src -I src/vdi -DGEM4XE_BANKED
B6         = build/b6502
DEVANTIC6  = -DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=and_ -DGEM4XE_DEV_ANTIC
HDRS6      = src/portab.h $(wildcard src/vdi/*.h src/sys/*.h src/antic/*.h src/aes/*.h)

# the bank of each section, for bankasm.py and bankcheck.py: the same as
# gem6502.scm's
BANKS6     = --bank vdi_a=1 --bank vdi_b=2 --bank vdi_c=3 --bank dev=4 --bank antic=5 --bank far=6 --bank objc=7 --bank objc_b=8 --bank objc_c=9 --bank graf=10

V6_RES     = $(B6)/res/v6_vdi.o $(B6)/res/stub6502.o $(B6)/res/anpack6502.o \
             $(B6)/res/muldiv6502.o $(B6)/res/font6x6.o \
             $(B6)/res/fillpat.o $(B6)/res/sintbl.o $(B6)/res/bank6502.o \
             $(B6)/res/v6farmem6502.o $(B6)/res/gemdata.o
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

# ---- step 3a: the far heap (tests/emu/f6_far.py) ---------------------------
# src/sys/farmem.c's allocator and src/f6_bank.c banked in section `far`;
# the test program, the resident far_* helpers (src/sys6502/farmem6502.c)
# and the trampoline resident.  One code bank: the helpers' far banks
# start after it (B6_CODE_BANKS).
F6_BANKS6  = --bank far=1
F6_RES     = $(B6)/res/f6_far.o $(B6)/res/f6farmem6502.o $(B6)/res/bank6502.o \
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

.PHONY: test-f6
