# rules.mk -- the 6502 build (docs/6502.md), included by the Makefile.
#
# Step 1: the VDI and its ANTIC device in banks of the PORTB window, a
# resident test program calling it through veneers, on a stock 6502.
#
#   resident   src/v6_vdi.c, the trampoline (src/sys6502/bank6502.s), the
#              veneers, the C stand-ins for what is not here yet, the
#              faces and tables, and every banked file's veneers
#   banks 1-3  vdi.c, cut by its two BANK_TEXTs   (sections vdi_a, vdi_b, vdi_c)
#   bank 4     dev_antic.c's functions, font.c and pointer.c   (section dev)
#   bank 5     antic.c                                  (section antic)
#
# Banked files are compiled with --no-cross-call: the optimiser's shared
# fragments go to section `code` whatever the pragma says -- 6.6 KB of
# them, resident, where room is scarcest -- so they are not made.
#
# A banked file is compiled through a wrapper that names its section, to
# assembly (build/b6502/asm/); tools/bsp6502/bankasm.py sends every
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

# the bank of each section, for veneers.py: the same as gem6502.scm's
BANKS6     = --bank vdi_a=1 --bank vdi_b=2 --bank vdi_c=3 --bank dev=4 --bank antic=5

V6_RES     = $(B6)/res/v6_vdi.o $(B6)/res/stub6502.o $(B6)/res/anpack6502.o \
             $(B6)/res/muldiv6502.o $(B6)/res/font6x6.o \
             $(B6)/res/fillpat.o $(B6)/res/sintbl.o $(B6)/res/bank6502.o
V6_UNITS   = vdi dev_antic antic font pointer
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
$(B6)/res/bank6502.o: src/sys6502/bank6502.s
	@mkdir -p $(dir $@)
	$(AS6) --core 6502 $< -o $@

# the wrappers: a section, then the file as it is
$(B6)/w/vdi.c:       ; @mkdir -p $(dir $@); printf '#pragma clang section text="vdi_a"\n#include "../../../src/vdi/vdi.c"\n' > $@
$(B6)/w/dev_antic.c: ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/dev_antic.c"\n' > $@
$(B6)/w/antic.c:     ; @mkdir -p $(dir $@); printf '#pragma clang section text="antic"\n#include "../../../src/antic/antic.c"\n' > $@
$(B6)/w/font.c:      ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/font.c"\n' > $@
$(B6)/w/pointer.c:   ; @mkdir -p $(dir $@); printf '#pragma clang section text="dev"\n#include "../../../src/vdi/pointer.c"\n' > $@

$(B6)/pre/vdi.o:       $(B6)/w/vdi.c src/vdi/vdi.c $(HDRS6)
$(B6)/pre/dev_antic.o: $(B6)/w/dev_antic.c src/vdi/dev_antic.c $(HDRS6)
$(B6)/pre/dev_antic.o: EXTRA6 = $(DEVANTIC6)
$(B6)/pre/antic.o:     $(B6)/w/antic.c src/antic/antic.c $(HDRS6)
$(B6)/pre/font.o:      $(B6)/w/font.c src/vdi/font.c $(HDRS6)
$(B6)/pre/pointer.o:   $(B6)/w/pointer.c src/vdi/pointer.c $(HDRS6)
$(V6_PRE):
	@mkdir -p $(dir $@) $(B6)/asm
	$(CC6) $(CFLAGS6) --no-cross-call $(EXTRA6) -c $< -o $@ \
	    --assembly-source=$(B6)/asm/$(notdir $(@:.o=.s))

$(B6)/bank/%.o: $(B6)/pre/%.o tools/bsp6502/bankasm.py
	@mkdir -p $(dir $@)
	python3 tools/bsp6502/bankasm.py $(B6)/asm/$*.s $(B6)/asm/$*.b.s --tu $* $(BANKS6)
	python3 tools/bsp6502/bankcheck.py --asm $(B6)/asm/$*.b.s $(BANKS6)
	$(AS6) --core 6502 $(B6)/asm/$*.b.s -o $@

build/v6.elf: $(V6_RES) $(V6_BANK) tools/bsp6502/gem6502.scm tools/bsp6502/bankcheck.py
	$(LN6) tools/bsp6502/gem6502.scm $(V6_RES) $(V6_BANK) \
	    -o $@ $(CAL6)/lib/clib-6502.a --verbose --list-file build/v6.map > /dev/null
	python3 tools/bsp6502/bankcheck.py build/v6.map --elf $@ || { rm -f $@; exit 1; }

build/v6.xex: build/v6.elf tools/bsp6502/mkxex6502.py tools/bsp6502/elfsym.py
	python3 tools/bsp6502/mkxex6502.py $< $@

build/v6-boot.atr: build/v6.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ V6.COM $(DISK_DENSITY)

test-v6: build/v6-boot.atr
	python3 tests/emu/v6_vdi.py

.PHONY: test-v6
