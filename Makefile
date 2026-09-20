# gem4xe -- GEM for the Atari 8-bit (VBXE + Rapidus + U1MB)
#
#   make            build/hello.xex and the bootable test disk
#   make test-emu   Phase 0 hardware gate (VBXE / Rapidus / MEMAC / CPU switch)
#   make test-m1    Milestone 1: Calypsi C running on the 65C816
#   make test-m6    the far code really is in, and running from, bank $01
#   make test-m7    evnt_* and form_do under host-driven input
#   make test-m8    the window manager: rectangle lists, moves, WM_REDRAW
#   make test-m9    menus: the bar, drop-downs, MN_SELECTED under host input
#   make test-m10   native-mode interrupts: the ROM shadow, VBI, timer, keys,
#                   a trak-ball counted in the handler, and the way back to DOS
#   make test-m11   the application ABI: a separately linked program loaded,
#                   relocated and run, calling GEM through COP
#   make test-m26   one binary, two screens: GEM.COM with a VBXE, without
#                   one, and in safe mode from GEM4XE.CFG
#   make check-cc   the compiler bugs we work around, in the vendor's simulator
#   make bench      GEMBench's tests on this machine, in milliseconds (docs/bench.md)
#   make test       all of them
#   make emu-stop   kill leftover emulators (never use pkill -f: it kills the shell)

CALYPSI  ?= $(HOME)/dev/toolchains/calypsi-65816
EMUTOS   ?= $(HOME)/dev/emutos
# The compiler, through tools/ccdep.sh, which records what each object
# really depends on into build/*.d and is included below.  The hand-written
# header lists on the rules stay: they are what makes the first build after
# a clean correct.  See the top of that script for what a missing one cost.
CC65816   = $(CALYPSI)/bin/cc65816
export CC65816
CC        = tools/ccdep.sh
AS        = $(CALYPSI)/bin/as65816
LD        = $(CALYPSI)/bin/ln65816
LIB       = clib-lc-sd.a

# Large code puts every C function in `farcode`, which src/gem4xe.scm places
# in banks $01 upwards -- one linker memory per bank, filled in order, so no
# function straddles a bank -- and src/farload.s copies up as DOS loads the
# file.  Data stays small -- globals and constants are addressed through the
# data bank register, so they have to remain in bank $00 (see the linker
# script).
CFLAGS    = --code-model=large --data-model=small -O2 -I src
# --override lets src/sys/div16.o replace the library's _Div16/_Mod16, which
# leave the wrong flags for the compiler's own `beq` (see that file).
LDFLAGS   = --rtattr exit=simplified --override _Div16 --override _Mod16

# What the compiler said each object opened, last time it was compiled.
# The FIRST target make sees is its default goal, and an included file's
# targets count -- so once build/*.d exist, the first of them (build/abi.o
# and its header list) became the goal of a bare `make`, which then built
# one object and stopped, silently and successfully.  `all` is named here
# rather than moving the include, so the answer does not depend on where
# in this file the include happens to sit.
.DEFAULT_GOAL := all
-include $(wildcard build/*.d)

SRC_DOS  ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['dos']['sd_dos2'])" 2>/dev/null)
# A double-density DOS 2 disk, [dos].dd_dos2: 720 x 256 is where the DOS 2
# product disk lives, because 707 sectors of 253 bytes hold GEM, the desktop,
# the DOS's own shell and applications besides -- and because that DOS runs
# AUTORUN.SYS, which is how the disk comes up in the desktop.
SRC_DD   ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['dos']['dd_dos2'])" 2>/dev/null)
# SpartaDOS 3.2 boot disk and the SpartaDOS X cartridge, [spartados] in
# fixtures.toml -- the SpartaGEM gate (docs/phase13.md) boots the one and
# then the other, with the same program.
SRC_SP32 ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['spartados']['disk_32'])" 2>/dev/null)
SRC_SDX  ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['spartados']['sdx_cart'])" 2>/dev/null)
# An Ultimate 1MB flash image carrying SpartaDOS X (test-m14u, test-m15u):
# needs the patched emulator's --u1mbrom (tools/altirra/), ALTIRRASDL=...
SRC_U1MB ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['u1mb']['flash'])" 2>/dev/null)

HELLO_OBJS = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/hello.o
M2_OBJS    = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m2_vbxe.o build/vbxe.o
# The context switch on its own: farmem for the parked extents, app_run
# out of abi.s for the way a context enters its program, and the runner's
# own stubs for the engine that is deliberately not linked.
M27_OBJS   = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m27_ctx.o \
             build/ctx.o build/ctxs.o build/farmem.o build/abis.o
# The ANTIC surface milestone: no VBXE object at all, which is the point
M24_OBJS   = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m24_antic.o build/antic.o build/font8x8.o
# The VDI on the ANTIC device: the same vdi.c, compiled for the other
# side of the seam and linked against dev_antic.o.
M25_OBJS   = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m25_antic_vdi.o \
             build/vdi.o build/dev_antic.o build/dev_print.o build/emit.o build/antic.o build/pointer.o \
             build/font8x8.o build/font6x6.o build/fillpat.o build/sintbl.o build/font.o \
             build/farmem.o build/irq.o build/irqs.o build/rapidus.o \
             build/cio.o build/cios.o build/dos.o build/m25_stub.o \
             build/graf.o build/objc.o build/grlib.o build/event.o \
             build/proc.o build/appl.o build/ctx.o build/ctxs.o \
             build/wind.o build/ctrl.o build/menu.o build/form.o \
             build/alert.o build/gemdata.o build/lang.o build/lang_rsc.o \
             build/rsrc.o build/apppool.o
# The VDI on the PRINTER: the same vdi.c again, on the third device --
# a page in far memory rather than a screen -- plus the emitters, which
# are the only reason this milestone needs CIO.  No AES: nothing draws an
# object tree onto paper here, so the stub answers for the call gate.
M30_OBJS   = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m30_print.o \
             build/vdi.o build/dev_print.o build/emit.o build/pointer.o \
             build/font8x8.o build/fillpat.o build/sintbl.o build/font.o \
             build/farmem.o build/irq.o build/irqs.o build/rapidus.o \
             build/cio.o build/cios.o build/dos.o build/m25_stub.o \
             build/graf.o build/objc.o build/grlib.o build/event.o \
             build/proc.o build/appl.o build/ctx.o build/ctxs.o \
             build/wind.o build/ctrl.o build/menu.o build/form.o \
             build/alert.o build/gemdata.o build/lang.o build/lang_rsc.o \
             build/rsrc.o build/apppool.o
M3_OBJS    = build/crt_atari.o build/farload.o build/div16.o build/clib.o build/m3_vdi.o build/vdi.o build/dev_vbxe.o build/pointer.o build/dev_print.o build/emit.o build/objc.o build/graf.o build/event.o build/proc.o build/appl.o build/ctx.o build/ctxs.o build/grlib.o build/form.o build/alert.o build/wind.o build/ctrl.o build/menu.o build/farmem.o build/rapidus.o build/irq.o build/irqs.o build/abi.o build/abis.o build/app.o build/apppool.o build/cio.o build/cios.o build/dos.o build/gemdos.o build/rsrc.o build/shel.o build/scrap.o build/app_blob.o build/font8x8.o build/fillpat.o build/sintbl.o build/vbxe.o build/antic.o build/fsel.o build/fsel_rsc.o build/gemdata.o build/lang.o build/lang_rsc.o build/font.o build/clock.o build/con.o build/config.o

# GEM.COM, the product (src/gem.c): the runner's objects with the runner
# itself and its compiled-in test application taken out, linked on the
# same rules with the application pool given the whole of $4000-$7FFF
# (src/gem4xe.scm, `layout`).
# GEM.COM links BOTH devices and chooses at start-up, so the ANTIC
# surface, its driver and its face come in on top of the runner's set.
GEM_OBJS   = $(filter-out build/m3_vdi.o build/app_blob.o,$(M3_OBJS)) \
             build/dev_antic.o build/font6x6.o \
             build/bootinfo.o build/gem.o

# A gem4xe application: its own C startup and bindings (src/app), linked
# against nothing of gem4xe's, on the application's own linker rules.
APP_OBJS   = build/app/crt_gemapp.o build/app/gemabi.o build/app/gemlib.o build/app/m11_app.o \
             build/app/m11_cop.o
# Its near budget (src/app/gemapp.scm): the stack and data, then the
# constants; and the stack's share of the first.  Decimal, because a `#`
# in a make variable starts a comment.
APP_BSS    = 2048
APP_BITS   = 256
APP_STACK  = 256
# The STAND-IN desktop's own share of the constants (src/m16_desk.c).  It
# learned shel_rdef and shel_wdef and with them five more string literals
# -- two paths and three names -- and the link failed with "Failed to
# place 4 section fragment(s), total 0f".  RAISED FOR THAT ONE PROGRAM and
# not for every application: APP_BITS comes out of the same near budget as
# the data, and 320 everywhere made test-m32's Pexec answer -39 for want
# of memory to put a child in.
#
# ITS OWN NAME, not DESK_BITS, which the real desktop also used: the two
# went opposite ways on 2026-09-19 -- the real one down to 128 because its
# constants are far now, this one still needing 320 because it is a
# small-data program -- and sharing the name made `make test-m16` fail to
# link the moment the other shrank.
M16_BITS   = 320

# Everything a gate boots, and the product: a plain `make` leaves no disk
# behind its sources (a gate run by hand, rather than through its test-m*
# target, otherwise boots a stale image and compares it against a fresh
# linker map).
all: build/hello-boot.atr build/m2-boot.atr build/m3-boot.atr build/m6split-boot.atr \
     build/m12-d2.atr build/m14-boot.atr build/m17-boot.atr build/gem-boot.atr \
     build/gem-sdx.atr build/gem-apps.atr build/gem-cf.img

build/%.o: src/%.s
	@mkdir -p build
	$(AS) -o $@ $<

build/%.o: src/%.c
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The two device files.  GEM4XE_DEV_IMPL says "this is one device's own
# translation unit", so vdidev.h gives it compile-time geometry instead
# of the pointer, and GEM4XE_DEV_PREFIX stamps its functions -- which is
# what lets BOTH be linked into one binary without a rename by hand.
build/dev_vbxe.o: src/vdi/dev_vbxe.c src/vdi/vdidev.h src/vdi/vdi.h src/vbxe/vbxe.h
	@mkdir -p build
	$(CC) $(CFLAGS) -DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=vbd_ \
	      -I src -I src/vdi -o $@ $<

build/font6x6.o: src/vdi/font6x6.c
	@mkdir -p build
	$(CC) $(CFLAGS) -I src/vdi -o $@ $<

src/vdi/font6x6.c: tools/fontconv6.py
	python3 tools/fontconv6.py "$(EMUTOS)/bios/fnt_st_6x6.c" $@

# The page (src/vdi/dev_print.c): the third device behind the same seam,
# 640x800 at 1bpp in far memory.  docs/printing.md has the geometry.
build/dev_print.o: src/vdi/dev_print.c src/vdi/vdidev.h src/vdi/vdi.h src/vdi/print.h
	@mkdir -p build
	$(CC) $(CFLAGS) -DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=prd_ \
	      -DGEM4XE_DEV_PRINT -I src -I src/vdi -o $@ $<

# The page, off the machine (src/vdi/emit.c): PCL 5 and PostScript, and
# where they go.  Above the device seam -- it reads the page, it does not
# draw on it -- so no device macros.
build/emit.o: src/vdi/emit.c src/vdi/print.h src/vdi/vdi.h src/sys/cio.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I src/vdi -o $@ $<

build/dev_antic.o: src/vdi/dev_antic.c src/vdi/vdidev.h src/vdi/vdi.h src/antic/antic.h
	@mkdir -p build
	$(CC) $(CFLAGS) -DGEM4XE_DEV_IMPL -DGEM4XE_DEV_PREFIX=and_ \
	      -DGEM4XE_DEV_ANTIC -I src -I src/vdi -o $@ $<

# There is no second copy of the device-INdependent halves any more.
# build/vdi.o, build/pointer.o and build/font.o serve both screens: that
# is what the vtable bought, and it is checkable rather than claimed --
# test-m3 and test-m25 link the same vdi.o.
build/m25_antic_vdi.o: src/m25_antic_vdi.c src/vdi/vdi.h src/vdi/vdidev.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I src/vdi -o $@ $<

build/m30_print.o: src/m30_print.c src/vdi/vdi.h src/vdi/vdidev.h src/vdi/print.h
	@mkdir -p build
	$(CC) $(CFLAGS) -DGEM4XE_DEV_PRINT -I src -I src/vdi -o $@ $<

build/vbxe.o: src/vbxe/vbxe.c src/vbxe/vbxe.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src/vbxe -o $@ $<

build/antic.o: src/antic/antic.c src/antic/antic.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src/antic -I src -o $@ $<

build/m24_antic.o: src/m24_antic.c src/antic/antic.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/m2_vbxe.o: src/m2_vbxe.c src/vbxe/vbxe.h
build/m3_vdi.o:  src/m3_vdi.c  src/vbxe/vbxe.h src/antic/antic.h src/vdi/vdi.h src/vdi/vdidev.h src/sys/irq.h src/sys/abi.h src/sys/app.h src/sys/cio.h src/sys/dos.h

build/vdi.o: src/vdi/vdi.c src/vdi/vdi.h src/vdi/vdidev.h src/vdi/pointer.h src/sys/irq.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/pointer.o: src/vdi/pointer.c src/vdi/pointer.h src/vdi/vdi.h src/vdi/vdidev.h src/sys/irq.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/objc.o: src/aes/objc.c src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/graf.o: src/aes/graf.c src/aes/aes.h src/vdi/vdi.h build/gemdata.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

build/proc.o: src/aes/proc.c src/aes/proc.h src/aes/aes.h src/sys/ctx.h src/sys/app.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/appl.o: src/aes/appl.c src/aes/aes.h src/aes/proc.h src/vdi/font.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/event.o: src/aes/event.c src/aes/aes.h src/aes/proc.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/grlib.o: src/aes/grlib.c src/aes/aes.h src/vdi/vdi.h build/gemdata.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

build/alert.o: src/aes/alert.c src/aes/aes.h src/sys/app.h build/gemdata.h build/lang_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

build/form.o: src/aes/form.c src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/wind.o: src/aes/wind.c src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/ctrl.o: src/aes/ctrl.c src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/menu.o: src/aes/menu.c src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/div16.o: src/sys/div16.s
	@mkdir -p build
	$(AS) -o $@ $<

# Our own memcpy/memset/str* so that no Apache-2.0 object from the
# vendor's C library is linked into a GPLv2 binary (src/sys/clib.c has
# the argument, and docs/licence.md what is still outstanding).
build/clib.o: src/sys/clib.c
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/farmem.o: src/sys/farmem.c src/sys/farmem.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/rapidus.o: src/sys/rapidus.c src/sys/rapidus.h src/vbxe/vbxe.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The interrupt regime: the C side installs and removes it, the assembly
# side is the handlers and the bank-$00 stubs the vectors point at.
build/irq.o: src/sys/irq.c src/sys/irq.h src/sys/rapidus.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/irqs.o: src/sys/irq.s
	@mkdir -p build
	$(AS) -o $@ $<

# The application ABI: the COP handler and the far-call trampoline in
# assembly, the parameter-block copy-in/out and the AES's crysbind in C,
# then the loader and the linker-reported bounds of its bank-$00 pool.
build/abi.o: src/sys/abi.c src/sys/abi.h src/vdi/vdi.h src/aes/aes.h src/sys/gemdos.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/abis.o: src/sys/abi.s
	@mkdir -p build
	$(AS) -o $@ $<

# The context switch: the bookkeeping in C, the three instructions C
# cannot write in assembly (src/sys/ctx.h).
build/ctx.o: src/sys/ctx.c src/sys/ctx.h src/sys/abi.h src/sys/farmem.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/ctxs.o: src/sys/ctx.s
	@mkdir -p build
	$(AS) -o $@ $<

build/m27_ctx.o: src/m27_ctx.c src/sys/ctx.h src/sys/farmem.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/app.o: src/sys/app.c src/sys/app.h src/sys/abi.h src/sys/cio.h src/sys/dos.h src/sys/farmem.h src/sys/gemdos.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/apppool.o: src/sys/apppool.s
	@mkdir -p build
	$(AS) -o $@ $<

# The file layer's floor: CIO through the OS, the IOCB side in C and the
# round trip into emulation mode in assembly.
build/cio.o: src/sys/cio.c src/sys/cio.h src/sys/irq.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/cios.o: src/sys/cio.s
	@mkdir -p build
	$(AS) -o $@ $<

# The DOS seam: which DOS booted, its path syntax, its listing's marks.
build/dos.o: src/sys/dos.c src/sys/dos.h src/sys/cio.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# GEM.COM itself: it names both devices and the config, so it has to be
# rebuilt when the seam moves.
build/gem.o: src/gem.c src/vdi/vdi.h src/vdi/vdidev.h src/vdi/pointer.h \
             src/vdi/font.h src/vdi/print.h src/aes/aes.h src/sys/config.h \
             src/sys/bootinfo.h src/sys/clock.h src/vbxe/vbxe.h src/antic/antic.h \
             build/lang_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

# GEM4XE.CFG: what the machine should be told before it has a screen.
build/config.o: src/sys/config.c src/sys/config.h src/sys/cio.h src/vdi/pointer.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The boot screen: what was found, on E:, before the GEM screen comes up.
# It says the version, which is the one place the C sees VERSION.
build/version.h: VERSION
	@mkdir -p build
	printf '#define GEM4XE_VERSION "%s"\n' "$$(cat VERSION)" > $@
build/bootinfo.o: src/sys/bootinfo.c src/sys/bootinfo.h src/sys/cio.h src/sys/irq.h \
             src/sys/rapidus.h src/sys/farmem.h src/sys/dos.h src/sys/config.h \
             src/sys/clock.h src/vbxe/vbxe.h src/vdi/pointer.h src/aes/aes.h \
             build/lang_rsc.h build/version.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

# GEMDOS for the applications: the ST's trap #1 on CIO, through the seam.
build/gemdos.o: src/sys/gemdos.c src/sys/clock.h src/sys/gemdos.h src/sys/dos.h src/sys/cio.h src/sys/farmem.h src/sys/app.h \
             src/sys/abi.h src/sys/con.h src/sys/config.h src/aes/proc.h src/sys/ctx.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The console GEMDOS's character calls reach: a VT-52 on GEM's screen,
# drawn through the AES (src/sys/con.h).  The runner links it and the
# printer's settings with GEMDOS, so config.o is in M3_OBJS now too.
build/con.o: src/sys/con.c src/sys/con.h src/sys/farmem.h src/aes/aes.h src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The file layer proper: the resource loader and the shell library.
build/rsrc.o: src/aes/rsrc.c src/aes/aes.h src/sys/app.h src/sys/cio.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The AES's own artwork -- eight mouse forms, three alert icons -- from the
# one script the reference reads them from too.
build/gemdata.c build/gemdata.h: tools/gemdata.py
	@mkdir -p build
	python3 tools/gemdata.py build/gemdata.c build/gemdata.h
build/gemdata.o: build/gemdata.c src/aes/aes.h
	$(CC) $(CFLAGS) -I src -o $@ $<

# LANG.RSC: what the system says.  One description makes three things --
# the file a translator replaces, the same bytes as the far fallback, and
# the indices the C uses (tools/langrsc.py).
build/lang.rsc build/lang_rsc.c build/lang_rsc.h: tools/langrsc.py tools/rsc.py
	@mkdir -p build
	python3 tools/langrsc.py build/lang.rsc build/lang_rsc.c build/lang_rsc.h
build/lang_rsc.o: build/lang_rsc.c
	@mkdir -p build
	$(CC) $(CFLAGS) -o $@ $<
build/clock.o: src/sys/clock.c src/sys/clock.h src/sys/cio.h src/sys/dos.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/font.o: src/vdi/font.c src/vdi/font.h src/vdi/vdi.h src/vdi/vdidev.h src/sys/cio.h src/sys/farmem.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

# The character sets a translation can ship as SYSTEM.FNT, written out of
# an EmuTOS checkout in the format the VDI reads (tools/mkfnt.py).  Not
# built by `all`: the product's font is the one linked in, and these are
# for whoever is translating.  `make fonts` writes them.
FONTS = build/l2.fnt build/ru.fnt build/gr.fnt build/tr.fnt
fonts: $(FONTS)
build/l2.fnt: tools/mkfnt.py ; @mkdir -p build && python3 tools/mkfnt.py $(EMUTOS)/bios/fnt_l2_8x8.c $@
build/ru.fnt: tools/mkfnt.py ; @mkdir -p build && python3 tools/mkfnt.py $(EMUTOS)/bios/fnt_ru_8x8.c $@
build/gr.fnt: tools/mkfnt.py ; @mkdir -p build && python3 tools/mkfnt.py $(EMUTOS)/bios/fnt_gr_8x8.c $@
build/tr.fnt: tools/mkfnt.py ; @mkdir -p build && python3 tools/mkfnt.py $(EMUTOS)/bios/fnt_tr_8x8.c $@

# The system font as a file, and the same font inverted: what test-m21
# loads, built from the strip that is checked in so the gate needs no
# EmuTOS checkout.
build/st.fnt: tools/mkfnt.py src/vdi/font8x8.c
	@mkdir -p build
	python3 tools/mkfnt.py --from-strip src/vdi/font8x8.c $@
build/inv.fnt: tools/mkfnt.py build/st.fnt
	python3 tools/mkfnt.py --invert build/st.fnt $@

build/lang.o: src/aes/lang.c src/aes/aes.h src/sys/cio.h src/sys/farmem.h src/vdi/font.h build/lang_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

build/fsel_rsc.c build/fsel_rsc.h: tools/fselrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/fselrsc.py build/fsel_rsc.c build/fsel_rsc.h
build/fsel_rsc.o: build/fsel_rsc.c
	$(CC) $(CFLAGS) -o $@ $<
build/fsel.o: src/aes/fsel.c src/aes/aes.h src/sys/app.h src/sys/cio.h src/sys/dos.h src/sys/farmem.h build/fsel_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<
build/shel.o: src/aes/shel.c src/aes/aes.h src/sys/app.h src/sys/cio.h src/sys/dos.h src/sys/farmem.h build/lang_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<
build/scrap.o: src/aes/scrap.c src/aes/aes.h src/sys/farmem.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -I build -o $@ $<

# A .G4A program (src/app/*: the startup and the bindings, plus its own
# body) is linked three times -- at its placeholder addresses, with the
# near region up a page, with the far region up a bank -- so that
# tools/mkg4a.py can find every byte that depends on where it is loaded.
# $(call g4a,name,objects,near bss,near bits,stack,more mkg4a args,more targets)
# The stack is part of the near bss (src/app/gemapp.scm); its size is the
# linker's --stack-size, so the map shows what each application asked for.
# build/app/clib.o is src/sys/clib.c -- the same eight ISO C functions the
# engine uses, for the same reason: Calypsi's are Apache-2.0 and this is a
# GPLv2 tree (docs/licence.md).  It is part of the LIBRARY and not of a
# program, so the kit ships it and anybody's application gets it.
G4A_LIB = build/app/crt_gemapp.o build/app/gemabi.o build/app/gemlib.o \
          build/app/gemstat.o build/app/gemtime.o build/app/gemcompat.o \
          build/app/gemstub.o build/app/clib.o

# ...and the same three for an application compiled --data-model=large.
# The linker refuses to mix runtime models, so a large-data program needs
# a large-data library beside it and Calypsi's own clib-lc-ld.a rather
# than clib-lc-sd.a.  The SOURCES are the same files: only the model
# differs (docs/gacs.md).
G4A_LIB_LD = build/appld/crt_gemapp.o build/appld/gemabi.o build/appld/gemlib.o \
             build/appld/gemstat.o build/appld/gemtime.o \
             build/appld/gemcompat.o build/appld/gemstub.o build/appld/clib.o
LIB_LD     = clib-lc-ld.a

build/app/clib.o: src/sys/clib.c
	@mkdir -p build/app
	$(CC) $(CFLAGS) -o $@ $<

build/appld/clib.o: src/sys/clib.c
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 -I src -o $@ $<

build/appld/%.o: src/app/%.s
	@mkdir -p build/appld
	$(AS) -o $@ $<

build/appld/%.o: src/app/%.c src/app/gem.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -o $@ $<
# The bindings without interprocedural cross-jumping.  At -O2 in the large
# model the compiler shares one identical tail across the GEMDOS bindings
# and parks it inside one function's section, so a program that calls
# Fread links clock, Tgettimeofday and Psystem it never calls -- 352 bytes,
# and one more binding every time one is added (tools/ccbug/README.md,
# "Reading the map").  Without the sharing each binding is its own
# section and costs a program 3-13 bytes more per binding it CALLS;
# tools/ccbug/objchain.py then finds nothing that brings clock in.
build/appld/gemlib.o: src/app/gemlib.c src/app/gem.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 --no-interprocedural-cross-jump \
	    -I src -I src/app -o $@ $<
build/appld/gemstub.o: src/app/gemstub.c src/app/gem.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 --no-interprocedural-cross-jump \
	    -I src -I src/app -o $@ $<
# The kit's calendar, AT -O0, and this is measured rather than cautious.
# At -O1 and above the compiler mangles civil_from_days (src/app/gemtime.c
# says which two shapes and what they produced): the month came back 0, a
# comparison used as a number added 255 instead of 1, and a plain 32-bit
# store through a pointer wrote 0.  The same source compiled by gcc agrees
# with Python on every case tests/host/test_gemtime.py checks, and -O0
# agrees too, so it is the optimiser.  The price is 589 bytes -- 3,932
# against 3,343 -- on a file that formats a date, and a wrong date is not
# worth 589 bytes.  tests/host/test_gemtime.py checks that this line still
# says -O0, so it cannot be "tidied" back without the gate saying so.
build/appld/gemtime.o: src/app/gemtime.c src/app/gem.h src/app/time.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O0 -I src -I src/app -o $@ $<
build/app/gemtime.o: src/app/gemtime.c src/app/gem.h src/app/time.h
	@mkdir -p build/app
	$(CC) --code-model=large --data-model=small -O0 -I src -I src/app -o $@ $<
# $(8), when given, is the runtime library: a --data-model=large program
# needs clib-lc-ld.a and the large-data half of the application library,
# because the linker refuses to mix runtime models.
#
# $(9) and $(10) are how many banks of CODE and of far VARIABLES the
# program wants, both one unless said otherwise -- which is every program
# here but m31_huge, and GACS's shell in the other repository, whose
# 102 KB of farcode and 119 KB of zfar are what made them parameters
# (src/app/gemapp.scm).
define g4a
build/$(1).elf: $(2) src/app/gemapp.scm
	$$(LD) src/app/gemapp.scm $(2) $(if $(8),$(8),$$(LIB)) --rtattr exit=simplified --cstartup gemapp -o $$@ \
	    --list-file build/$(1).map --stack-size $(5) \
	    --memories-expression "(app-layout-n #x1000 #x020000 $(3) $(4) $(if $(9),$(9),1) $(if $(10),$(10),1))"
build/$(1)-near.elf: $(2) src/app/gemapp.scm
	$$(LD) src/app/gemapp.scm $(2) $(if $(8),$(8),$$(LIB)) --rtattr exit=simplified --cstartup gemapp -o $$@ \
	    --stack-size $(5) --memories-expression "(app-layout-n #x1100 #x020000 $(3) $(4) $(if $(9),$(9),1) $(if $(10),$(10),1))"
build/$(1)-far.elf: $(2) src/app/gemapp.scm
	$$(LD) src/app/gemapp.scm $(2) $(if $(8),$(8),$$(LIB)) --rtattr exit=simplified --cstartup gemapp -o $$@ \
	    --stack-size $(5) --memories-expression "(app-layout-n #x1000 #x030000 $(3) $(4) $(if $(9),$(9),1) $(if $(10),$(10),1))"
build/$(1).g4a build/$(1).sym $(7): build/$(1).elf build/$(1)-near.elf build/$(1)-far.elf tools/mkg4a.py
	python3 tools/mkg4a.py build/$(1).elf build/$(1)-near.elf build/$(1)-far.elf \
	        build/$(1).g4a --syms build/$(1).sym $(6)
endef

build/app/%.o: src/app/%.s
	@mkdir -p build/app
	$(AS) -o $@ $<

build/app/%.o: src/app/%.c src/app/gem.h
	@mkdir -p build/app
	$(CC) $(CFLAGS) -I src/app -o $@ $<
# The bindings in the small model take the same flag as the large
# (build/appld/gemlib.o below says why), not for a saving -- the small
# model shares no tail -- but so that the kit, whose Makefile gives
# gemlib.c the flag in every model, rebuilds the gate application byte
# for byte (tests/host/test_sdk.py).
build/app/gemlib.o: src/app/gemlib.c src/app/gem.h
	@mkdir -p build/app
	$(CC) $(CFLAGS) --no-interprocedural-cross-jump -I src/app -o $@ $<
# gemstub.c is nine functions that end the same way (`r < 0 ? -errno : 0`),
# which is the shape the compiler shares a tail across -- and a program
# that calls printf would then link the six it does not use.
build/app/gemstub.o: src/app/gemstub.c src/app/gem.h
	@mkdir -p build/app
	$(CC) $(CFLAGS) --no-interprocedural-cross-jump -I src/app -o $@ $<

build/app/%.o: src/%.c src/app/gem.h
	@mkdir -p build/app
	$(CC) $(CFLAGS) -I src/app -o $@ $<

# The gate application's one COP that is not gem4xe's (tests/emu/m11_abi.py).
build/app/m11_cop.o: src/m11_cop.s
	@mkdir -p build/app
	$(AS) -o $@ $<

# The gate application (src/m11_app.c).  The .g4a is what a loader reads
# from disk; the C array is the same bytes for the runner to load from
# the image, there being no file layer yet.
$(eval $(call g4a,m11_app,$(APP_OBJS),$(APP_BSS),$(APP_BITS),$(APP_STACK),--c-array build/app_blob.c app_blob,build/app_blob.c))

build/app_blob.o: build/app_blob.c
	$(CC) $(CFLAGS) -o $@ $<

# The gate accessory (src/m28_acc.c): a .G4A like any other program, on
# the disk with the extension the AES looks for.  Its near region is the
# smallest of anything here -- it draws nothing and owns no window -- so
# what test-m28 measures is close to the floor an accessory costs.
ACC_OBJS   = $(G4A_LIB) build/app/m28_acc.o
# 160 bits, not 128: the two eight-character names it hands appl_find are
# near constants, and 128 left six bytes free.
$(eval $(call g4a,m28_acc,$(ACC_OBJS),1152,160,384,,))

# The shipped applications (src/apps): the first programs written to the
# application ABI that are not tests.  Each is one C file, one resource
# built on the host, and the same three-way link every .g4a takes.
build/apps/%.o: src/apps/%.c src/app/gem.h build/calcrsc.h build/clockrsc.h \
                build/cpanelrsc.h
	@mkdir -p build/apps
	$(CC) $(CFLAGS) -I src/app -I build -o $@ $<

build/calc.rsc build/calcrsc.h: tools/calcrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/calcrsc.py build/calc.rsc build/calcrsc.h

build/clock.rsc build/clockrsc.h: tools/clockrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/clockrsc.py build/clock.rsc build/clockrsc.h

CALC_OBJS  = $(G4A_LIB) build/apps/calc.o build/apps/calcapp.o
CLOCK_OBJS = $(G4A_LIB) build/apps/clock.o build/apps/clockapp.o
$(eval $(call g4a,calc,$(CALC_OBJS),1536,256,512,,))
$(eval $(call g4a,clock,$(CLOCK_OBJS),1536,256,512,,))

# The clock AS AN ACCESSORY (src/apps/clockacc.c): the same clock.o, a
# different main, and the extension the AES looks for in the system's own
# directory.  The reservations are what the map says it uses rather than
# round numbers, because an accessory is charged to the application pool
# for as long as the machine is on -- 14 KB for the desktop, its resource
# and everything resident beside it (docs/phase36.md).
CLOCKACC_OBJS = $(G4A_LIB) build/apps/clock.o build/apps/clockacc.o
$(eval $(call g4a,clockacc,$(CLOCKACC_OBJS),1152,128,384,,))

# The control panel (src/apps/cpanel.c), an accessory for the same reason
# the clock is one and a stronger one besides: the moment somebody wants
# the double-click rate changed is the moment one did not register, and
# the Desk menu is the only door open from inside a program.  It draws
# nothing itself -- the AES draws the form -- so it needs no workstation
# and less near memory than the clock.
build/cpanel.rsc build/cpanelrsc.h: tools/cpanelrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/cpanelrsc.py build/cpanel.rsc build/cpanelrsc.h

# COMPILED --data-model=large, which is what buys the pool back: a
# program that holds 32-bit pointers may be handed a resource in far
# memory, and since 2026-09-19 rs_load puts one there whenever it can
# rather than only when the pool is too small (src/aes/rsrc.c).  So
# CPANEL.RSC costs bank $00 nothing at all, and what is left is the
# queue and the near region.  The reservations are what the map says
# rather than round numbers, because an accessory is charged to the pool
# for as long as the machine is on.
build/appsld/%.o: src/apps/%.c src/app/gem.h build/calcrsc.h build/clockrsc.h \
                  build/cpanelrsc.h
	@mkdir -p build/appsld
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -I build -o $@ $<

CPANEL_OBJS = $(G4A_LIB_LD) build/appsld/cpanel.o build/appsld/cpanelacc.o
$(eval $(call g4a,cpanelacc,$(CPANEL_OBJS),640,128,384,,,$(LIB_LD)))

# The calculator AS AN ACCESSORY: the same calc.o, the other main().
# The ST shipped one, and it is what the Desk menu is FOR -- a thing you
# want while you are using something else.  Large-data like the control
# panel, so CALC.RSC costs bank $$00 nothing.
CALCACC_OBJS = $(G4A_LIB_LD) build/appsld/calc.o build/appsld/calcacc.o
# 512 and 128: the map answers 384 bytes of bss -- which IS the stack,
# its statics having gone to far bss with the large data model -- and 20
# of bits.  256 + 512 + 128 is 896, four pages.
$(eval $(call g4a,calcacc,$(CALCACC_OBJS),512,128,384,,,$(LIB_LD)))

# The desktop (src/desk): a bigger near region than the gate application's,
# for the object trees a desktop keeps in bank $00, and DESKTOP.RSC beside
# it on the disk (tools/deskrsc.py; the icons from EmuTOS desk/icons.c
# through tools/iconconv.py, checked in like the font).  The milestone-3
# desktop (src/m16_desk.c: a line of help, R/X/Q) stays as the stand-in
# test-m16 drives the shell loop with.
# The near region is 15 pages: the direct page, the bss, the constants.
# The bss holds the desktop's globals (GLOBES, src/desk/desk.h: the screen
# tree, the window nodes, the icon records, ~2 KB) and its stack, which
# is the gate application's 256 bytes and more: the folder window's open
# -- the button, do_open, do_dopen, do_wopen, a call to the AES on top --
# ran 256 bytes out (phase 14, milestone 5).
#
# 640 is the desktop's stack and the low-water mark says ~300 bytes of it
# are ever used; 2944 of bss is what the rest of it measures.  For a
# while the stack was 896 and the bss 3200, because the honest numbers
# crashed -- which was never the desktop's doing: it is the emulator's
# SEI-shadow IRQ storm (tools/altirra/, patch 1), which paints the whole
# of bank $00, hardware registers and all, and which a couple of hundred
# bytes of layout anywhere is enough to trip or untrip.  THAT IS WHY THE
# NUMBERS HERE ARE THE MEASURED ONES AND NOT A DODGE: a dodge lasts
# until the next thing that moves the code, which phase 27 demonstrated
# by moving the storm from m19 into m18.  The desktop gates run against
# a patched emulator -- ALTIRRASDL=<build> -- and say so when they find
# the storm (tests/emu/m7_form.py storm_check).  docs/phase26.md.
#
# The pool is shared with DESKTOP.RSC (6226 bytes) and with GEMDOS's
# work area (src/sys/gemdos.c), which is why the desktop gates run a
# runner whose staging leaves the pool the room GEM.COM leaves it
# (build/m3desk.xex, above).
# COMPILED --data-model=large.  The desktop's resource is the largest
# single thing in the pool -- 4862 bytes resident, 6398 while it loads --
# and a program that holds 32-bit pointers is handed it in far memory
# instead (src/aes/rsrc.c).  That is what makes room for a second
# accessory beside it, and for the six the Desk box has slots for.
DESK_OBJS  = $(G4A_LIB_LD) build/deskld/desktop.o build/deskld/deskobj.o \
             build/deskld/deskwin.o build/deskld/deskfun.o \
             build/deskld/deskcmd.o
# Small now that the globals are far: the map answers 639 bytes of bss --
# which is the 640-byte stack and almost nothing else, G having moved to
# far bss -- and 30 of bits.  256 + 768 + 128 is 1152, five pages.
DESK_BSS   = 768
DESK_BITS  = 128
# The near region is page-rounded (src/sys/app.c app_load): DP + bss + bits.
# The next byte costs a page (test-m28: tools/memreport.py).
DESK_STACK = 640
DESK_H     = src/app/gem.h src/desk/desk.h build/deskrsc.h

build/deskld/%.o: src/desk/%.c $(DESK_H)
	@mkdir -p build/deskld
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -I build -o $@ $<

$(eval $(call g4a,desktop,$(DESK_OBJS),$(DESK_BSS),$(DESK_BITS),$(DESK_STACK),,,$(LIB_LD)))
$(eval $(call g4a,m16_desk,$(G4A_LIB) build/app/m16_desk.o,$(APP_BSS),$(M16_BITS),$(APP_STACK)))

# HELLO.PRG (src/hello_app.c): the desktop's hello-world demo, shipped in
# \APPS\ in place of the M11 gate app -- a real window a user can open and
# close, not a fixture that flashes and exits (tools/mkdist.py).
$(eval $(call g4a,hello_app,$(G4A_LIB) build/app/hello_app.o,$(APP_BSS),$(APP_BITS),$(APP_STACK)))

tools/deskicons.py: tools/iconconv.py
	python3 tools/iconconv.py $(EMUTOS)/desk/icons.c $@

# VERSION is a prerequisite because the About box says it: 0.1.1 shipped
# with a resource built for 0.1, and the desktop gates found it a phase
# later, when the model (which reads VERSION) had every tree two bytes
# from where the stale file put it (docs/phase38.md).
build/desktop.rsc build/deskrsc.h build/prefs.rsc: tools/deskrsc.py tools/rsc.py tools/aesref.py tools/deskicons.py VERSION
	@mkdir -p build
	python3 tools/deskrsc.py build/desktop.rsc build/deskrsc.h build/prefs.rsc

# The GEM 8x8 system font, extracted from EmuTOS (GPL v2+) by fontconv.py.
# Checked in so the host reference reads the same bytes the target links.
build/font8x8.o: src/vdi/font8x8.c
	@mkdir -p build
	$(CC) $(CFLAGS) -o $@ $<

src/vdi/font8x8.c:
	python3 tools/fontconv.py $(EMUTOS)/bios/fnt_st_8x8.c $@

# The standard fill patterns -- dithers, OEM patterns, hatches -- extracted
# from EmuTOS's vdi_fill.c by patconv.py, likewise checked in.
build/fillpat.o: src/vdi/fillpat.c src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

src/vdi/fillpat.c:
	python3 tools/patconv.py $(EMUTOS)/vdi/vdi_fill.c $@

# The VDI's sine table, from EmuTOS's vdi_gdp.c by sinconv.py: the GDPs
# draw every curve out of it, and tools/vdiref.py reads the generated file
# so the reference and the driver cannot disagree about a circle.
build/sintbl.o: src/vdi/sintbl.c src/vdi/vdi.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

src/vdi/sintbl.c:
	python3 tools/sinconv.py $(EMUTOS)/vdi/vdi_gdp.c $@

build/hello.elf: $(HELLO_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(HELLO_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/hello.map

build/m2.elf: $(M2_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M2_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m2.map

# _atari_entry, not __program_start: the stub must disable NMI/IRQ in emulation
# mode before the library startup's `xce`.  See src/crt_atari.s.
build/hello.xex: build/hello.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry

build/m3.elf: $(M3_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M3_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m3.map

build/m2.xex: build/m2.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry

build/m25.elf: $(M25_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M25_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m25.map

build/m25.xex: build/m25.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry

build/m25-boot.atr: build/m25.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ M25.COM $(DISK_DENSITY)

build/m30.elf: $(M30_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M30_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m30.map

build/m30.xex: build/m30.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry

# The printer gate's disk (test-m30).  SpartaDOS, not the DOS 2 floppy
# the other VDI milestones boot from, for one reason: the milestone
# WRITES, and a page in PostScript is 129 KB -- more than a DOS 2.5
# enhanced-density disk holds in total.  320 KB of SpartaDOS is where the
# two files fit, and it is the medium the product ships on anyway.
build/m30-boot.atr: build/m30.xex tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ --name M30.COM $(SP_SECTORS)

build/m27.elf: $(M27_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M27_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m27.map

build/m27.xex: build/m27.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/m27.sym

build/m24.elf: $(M24_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M24_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m24.map

build/m24.xex: build/m24.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry

build/gem.elf: $(GEM_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(GEM_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/gem.map \
	      --memories-expression "(layout #x010000 #x7fff)"

build/gem.xex: build/gem.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/gem.sym

# GEMDIAG.COM: GEM.COM with a mark before every start-up step and the
# console keys bisecting the two things only Altirra has ever run
# (src/sys/diag.h) -- for a machine no emulator has been near.  The same
# objects on the same layout; src/gem.c compiled once more with the marks
# in.  Not part of any disk: it is copied next to GEM.COM by hand.
DIAG_OBJS  = $(filter-out build/gem.o,$(GEM_OBJS)) build/gem_diag.o build/diag.o

build/gem_diag.o: src/gem.c src/sys/diag.h build/lang_rsc.h
	@mkdir -p build
	$(CC) $(CFLAGS) -DGEM_DIAG -I src -I build -o $@ $<

build/diag.o: src/sys/diag.c src/sys/diag.h src/sys/rapidus.h
	@mkdir -p build
	$(CC) $(CFLAGS) -I src -o $@ $<

build/gemdiag.elf: $(DIAG_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(DIAG_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/gemdiag.map \
	      --memories-expression "(layout #x010000 #x7fff)"

build/gemdiag.com: build/gemdiag.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/gemdiag.sym

diag: build/gemdiag.com

# --syms lets the conformance harness find vdi_script by name instead of
# hard-coding an address that moves on every rebuild.
build/m3.xex: build/m3.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/m3.sym

# The desktop gates' runner: the same code with the staging buffers cut
# to the few calls they stage (the prelude, the shell op, the pool
# probes) and the pool run up to where that staging starts, so the
# desktop and DESKTOP.RSC are loaded into a pool the size GEM.COM gives
# them rather than the conformance runner's half of the window.  One
# object differs, so the link is the same list with it swapped in.
M3DESK_SIZES = -D SCRIPT_WORDS=128 -D SCRATCH_BYTES=512 -D MAX_RESULTS=24
M3DESK_OBJS  = $(patsubst build/m3_vdi.o,build/m3desk_vdi.o,$(M3_OBJS))

build/m3desk_vdi.o: src/m3_vdi.c src/vbxe/vbxe.h src/vdi/vdi.h src/sys/irq.h src/sys/abi.h src/sys/app.h src/sys/cio.h src/sys/dos.h
	@mkdir -p build
	$(CC) $(CFLAGS) $(M3DESK_SIZES) -I src -o $@ $<

build/m3desk.elf: $(M3DESK_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M3DESK_OBJS) -o $@ $(LIB) $(LDFLAGS) \
	      --list-file build/m3desk.map \
	      --memories-expression "(layout #x010000 #x78ff)"

build/m3desk.xex: build/m3desk.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/m3desk.sym

# The runner outgrew a single-density disk (620 free sectors; the .xex
# alone wants more), so the fixture is converted to DOS 2.5 enhanced density
# on the way (tools/atr.py enhance()), and the program goes into the upper
# half FIRST -- the sectors a DOS 2.0 cannot reach -- so that every boot
# proves the fixture DOS reads them.  The same disk build serves the small
# programs too: one disk format, not one that works until the file grows.
DISK_DENSITY = --enhanced --high

# The disk also carries what the file layer's gate reads back through CIO
# (tests/emu/m12_file.py): a text fixture and a resource file built on
# the host (tools/mkrsc.py), so rsrc_load has something to load.  OUT.TXT
# is on it because the gate WRITES that name: the emulator's disk changes
# under the run while the image on the host does not, and the selector's
# listing is predicted from the image.  A file that is already there is
# overwritten, so the directory the selector reads is the one the host
# read -- with the name on both sides rather than neither.
# NOT LANG.RSC.  The runner's disks are what test-m12's file selector
# lists and what its far-heap accounting counts, and a tenth file
# overflows the selector's nine lines while the language resource in far
# memory moves the heap cursor by its own size -- both of which that gate
# measures.  test-m20 makes its own copies of this disk with the file
# added, removed and translated, which is the point there; every other
# gate runs on the English linked into the image (src/aes/lang.c).
DISK_FILES = --add tests/fixtures/test.txt TEST.TXT --add build/test.rsc TEST.RSC \
             --add tests/fixtures/out.txt OUT.TXT

# The applications the shell loop runs (docs/phase14.md, milestone 3): the
# desktop, and the gate application as the program the desktop launches.
# On the runner's disks for test-m16, on the product's because that is the
# product.
SHELL_FILES = --add build/m16_desk.g4a DESKTOP.PRG --add build/m11_app.g4a M11.PRG
SHELL_DEPS  = build/m16_desk.g4a build/m11_app.g4a
DESK_FILES  = --add build/desktop.g4a DESKTOP.PRG --add build/desktop.rsc DESKTOP.RSC \
              --add build/m11_app.g4a M11.PRG
DESK_DEPS   = build/desktop.g4a build/desktop.rsc build/prefs.rsc build/m11_app.g4a
# The two accessories (src/apps), on the media with room for them: the
# SpartaDOS floppy, the CF card, and test-m22's own disk.  A prerequisite
# list is expanded where it is written, so these live above every rule
# that names them.
# In a FOLDER, as the product has them: an application and its resource
# live together in \APPS\, and finding the resource from there is the
# thing test-m22 now covers (docs/phase29.md).
APP_FILES = --mkdir APPS \
            --add build/calc.g4a "APPS>CALC.PRG" --add build/calc.rsc "APPS>CALC.RSC" \
            --add build/clock.g4a "APPS>CLOCK.PRG" --add build/clock.rsc "APPS>CLOCK.RSC"
APP_DEPS  = build/calc.g4a build/calc.rsc build/clock.g4a build/clock.rsc
# The gate accessory (src/m28_acc.c), in the system's own directory with
# the extension the AES looks for there: an accessory is not in \APPS\
# with the programs, because it is not one -- it is loaded once at
# start-up and outlives every program (src/aes/shel.c).
ACC_FILES = --add build/m28_acc.g4a M28.ACC
ACC_DEPS  = build/m28_acc.g4a
# The accessory the PRODUCT ships: the clock, in the system's own
# directory rather than \APPS\, because an accessory is not a program the
# desktop launches -- the AES loads it once at start-up and it outlives
# every program (src/aes/shel.c).
ACCP_DEPS = build/clockacc.g4a build/clock.rsc \
            build/cpanelacc.g4a build/cpanel.rsc \
            build/calcacc.g4a build/calc.rsc

# The large-data gate application (src/m29_big.c): the ONE object in the
# tree compiled --data-model=large, which is the model GACS's engine and
# RetroWP's are written to (docs/gacs.md).  Its own rule rather than the
# pattern rule, because $(CFLAGS) says small.
build/appld/m29_big.o: src/m29_big.c src/app/gem.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -o $@ $<
BIG_OBJS = $(G4A_LIB_LD) build/appld/m29_big.o
$(eval $(call g4a,m29_big,$(BIG_OBJS),1024,256,384,,,$(LIB_LD)))

# The far-resource gate application (src/m33_farrsc.c), built TWICE from
# one source: --data-model=large, whose kit asks for far addresses, and
# --data-model=small, whose kit does not.  FARRSC.RSC is 42 KB against a
# 14 KB pool (tools/farrsc.py), so the first loads it far and the second
# must be refused (docs/far-trees.md).
build/farrsc.rsc build/farrsc.h: tools/farrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/farrsc.py build/farrsc.rsc build/farrsc.h
build/appld/m33_farrsc.o: src/m33_farrsc.c src/app/gem.h build/farrsc.h
	@mkdir -p build/appld
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -I build -o $@ $<
build/app/m33_farrsc.o: src/m33_farrsc.c src/app/gem.h build/farrsc.h
	@mkdir -p build/app
	$(CC) $(CFLAGS) -I src/app -I build -o $@ $<
FARRSC_OBJS  = $(G4A_LIB_LD) build/appld/m33_farrsc.o
FARRSCS_OBJS = $(G4A_LIB) build/app/m33_farrsc.o
$(eval $(call g4a,m33_farrsc,$(FARRSC_OBJS),1024,256,384,,,$(LIB_LD)))
$(eval $(call g4a,m33s_farrsc,$(FARRSCS_OBJS),1024,256,384))

# The console gate application (src/m32_con.c): GEMDOS's character calls,
# its standard handles and Pterm, run through the shell loop by
# tests/emu/m32_con.py.  A small-data program like the first one, so its
# page of VT-52 is near constants: 1 KB of them.
M32_OBJS = $(G4A_LIB) build/app/m32_con.o
$(eval $(call g4a,m32_con,$(M32_OBJS),1024,1024,384,,))
# ...and the child it runs with Pexec (src/m32_kid.c).
$(eval $(call g4a,m32_kid,$(G4A_LIB) build/app/m32_kid.o,1024,256,384,,))

# The application whose far IMAGE is bigger than a bank (src/m31_huge.c).
# Nothing in this tree had one until GACS's GEM shell was linked for this
# machine, so the .G4A's u16 far fixup offsets and app_load's 16-bit
# size_t both sat undisturbed -- and neither would have said so.  Format 2
# and a chunked copy answer them; this is what proves it here rather than
# in another repository.  Four blocks of far CONSTANTS, because only bytes
# that are in the file grow the image.
build/m31_data.c: tools/m31data.py
	@mkdir -p build
	python3 tools/m31data.py $@
build/app/m31_data.o: build/m31_data.c
	@mkdir -p build/app
	$(CC) --code-model=large --data-model=large -O2 -I src -o $@ $<
build/app/m31_huge.o: src/m31_huge.c src/app/gem.h
	@mkdir -p build/app
	$(CC) --code-model=large --data-model=large -O2 -I src -I src/app -o $@ $<
HUGE_OBJS = $(G4A_LIB_LD) build/app/m31_huge.o build/app/m31_data.o
$(eval $(call g4a,m31_huge,$(HUGE_OBJS),1024,256,384,,,$(LIB_LD),2,1))

build/test.rsc: tools/mkrsc.py tools/rsc.py tools/aesref.py
	@mkdir -p build
	python3 tools/mkrsc.py $@

# The selector's second drive: the fixture DOS disk with fifteen small
# files on it, D2: when test-m12 boots (tools/mkfsdisk.py).
build/m12-d2.atr: tools/mkfsdisk.py tools/atr.py
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkfsdisk.py "$(SRC_DOS)" $@

# The runner's disk is DOUBLE density, and that is why the gates type an
# L before the name.  The single-density fixture's DOS boots to a command
# prompt (nicer to drive) but its 1040 enhanced sectors held the runner
# with nothing to spare -- 117 KB of program on a 128 KB disk -- and the
# boot code it carries cannot read a double-density disk at all: written
# onto one, it stops at BOOT ERROR.  The double-density fixture's DOS
# boots its own disk, gives the familiar DOS 2 menu, and leaves 190
# sectors free, so the runner has 48 KB to grow into.  L is that menu's
# BINARY LOAD, and the file is called M3 with no extension so that the
# three keys after it are the ones every gate already typed.
# The shell gate (test-m16) runs on the SpartaDOS disk, whose size is
# ours to choose (tools/mkspdisk.py --sectors).
build/m3-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc
	@test -n "$(SRC_DD)" || { echo "no double-density DOS fixture: set [dos].dd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DD)" $< $@ M3 --sweep $(DISK_FILES)

# The product disks: the system with the desktop beside it, one per DOS,
# and both of them boot into it with nothing typed.
#
# The DOS 2 one is DOUBLE density.  Single density does not hold GEM.COM
# at all and enhanced holds it with three sectors to spare, which left no
# room for the DOS's own shell -- and a DOS with no shell to return to
# dies when GEM hands the machine back.  720 sectors of 253 bytes hold
# the system, DOS.SYS, DUP.SYS and the rest for applications, which is
# what makes the disk a place to keep them rather than one program.
# M11.PRG -- the demonstration program -- is NOT on this one: 180 KB is
# the tightest medium gem4xe ships on, and by the time the desktop could
# save a layout (phase 25) the demo was the difference between having
# room for somebody's own program and not.  The SpartaDOS floppy and the
# CF card both carry it.  The program
# is named AUTORUN.SYS because that is what the DOS runs at boot, and
# --sweep takes everything but the DOS off the fixture, which was
# somebody's magazine disk (docs/shipping.md, section 2).
build/816.com: tools/mk816.py
	@mkdir -p build
	python3 tools/mk816.py $@

# The DOS 2 floppy carries the SYSTEM and the clock accessory, and no
# applications: a DOS 2 disk has no directories, so \APPS\ cannot exist
# on it, and the calculator and the clock live on the install disk and
# the card (docs/shipping.md section 1).  The system got a third smaller
# when its far image started travelling packed (tools/mkxex.py), which
# is what gave this disk its DOS shell back, the documented GEM4XE.CFG
# and the accessory, with a hundred-odd sectors left over --
# tests/emu/product_boot.py holds a floor of 80, so that the smallest
# disk is still somewhere a person can put a program of their own.
# GEM4XE.CFG as it ships: every setting commented out, so that finding
# the file is finding its documentation.  Translated to the Atari's EOL
# ($9B) on the way to the disk -- src/sys/config.c reads CR, LF and EOL
# alike, but a file that a DOS editor opens should already be in the
# form that editor writes.
build/gem4xe.cfg: dist/gem4xe.cfg
	@mkdir -p build
	python3 -c "import sys; \
	    open(sys.argv[2],'wb').write(open(sys.argv[1],'rb').read() \
	        .replace(b'\r\n', b'\n').replace(b'\n', b'\x9b'))" $< $@

# ...and the safe-mode one the ANTIC gate boots with, which is the same
# file with the one line uncommented.
build/safe.cfg: dist/gem4xe.cfg
	@mkdir -p build
	python3 -c "import sys; \
	    open(sys.argv[2],'wb').write(open(sys.argv[1],'rb').read() \
	        .replace(b'# VIDEO=AUTO', b'VIDEO=ANTIC') \
	        .replace(b'\r\n', b'\n').replace(b'\n', b'\x9b'))" $< $@

# ...and the one test-cf-dosclock boots with: CLOCK=DOS, so that the
# SpartaDOS X kernel is the clock even on a machine that has the chip.
build/dosclock.cfg: dist/gem4xe.cfg
	@mkdir -p build
	python3 -c "import sys; \
	    open(sys.argv[2],'wb').write(open(sys.argv[1],'rb').read() \
	        .replace(b'# CLOCK=AUTO', b'CLOCK=DOS') \
	        .replace(b'\r\n', b'\n').replace(b'\n', b'\x9b'))" $< $@

# The DOS's own DUP.SYS stays: it is what GEM returns to when it quits.
# (It went, for a while, when the system outgrew the disk with the shell
# on it -- docs/shipping.md section 2 -- and came back with the packed
# far image.)  The system and nothing else, as every floppy is since
# phase 42: the desk accessory went when the rest of GEMDOS took this disk
# under its floor of free sectors, and it and the applications are on
# gem-apps.atr (docs/media.md) -- which a DOS 2 cannot read, so this disk
# is a gate's more than anybody's way in.
DOS2_FILES = --add build/desktop.g4a DESKTOP.PRG --add build/desktop.rsc DESKTOP.RSC \
	     --add build/lang.rsc LANG.RSC --add build/816.com 816.COM
# No GEM4XE.CFG on this one since phase 43: every value in the file is the
# default, and the seven sectors were what File -> DOS command cost the
# floppy's floor (docs/shipping.md section 1).  The SpartaDOS X floppy
# and the card carry it.
build/gem-boot.atr: build/gem.xex build/desktop.g4a build/desktop.rsc build/m11_app.g4a build/lang.rsc build/816.com
	@test -n "$(SRC_DD)" || { echo "no double-density DOS fixture: set [dos].dd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DD)" $< $@ AUTORUN.SYS --sweep \
	    $(DOS2_FILES)

# The same shipped disk with the safe-mode line uncommented: what a user
# writes from the DOS prompt when the VBXE's output is not something
# their monitor will show (tests/emu/m26_fallback.py).
build/gem-antic.atr: build/gem.xex build/desktop.g4a build/desktop.rsc build/m11_app.g4a build/lang.rsc build/816.com build/safe.cfg
	@test -n "$(SRC_DD)" || { echo "no double-density DOS fixture: set [dos].dd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DD)" $< $@ AUTORUN.SYS --sweep \
	    $(DOS2_FILES) --add build/safe.cfg GEM4XE.CFG

# The pictures' disk (make shots): SpartaDOS 3.2 booting the card's layout,
# the system and the applications, so that \APPS\ and the Desk menu's Clock
# can be photographed.  It was the SpartaDOS 3.2 product floppy's layout
# too, until that floppy was retired after phase 42: the installer is
# SpartaDOS X's, and a machine with a drive to install onto has SpartaDOS X
# in its flash (docs/media.md).
SP_LAYOUT = --name "GEM>GEM.COM" --boot "CD >GEM|GEM" --mkdir GEM \
	    --add build/desktop.g4a "GEM>DESKTOP.PRG" \
	    --add build/desktop.rsc "GEM>DESKTOP.RSC" \
	    --add build/prefs.rsc "GEM>PREFS.RSC" \
	    --add build/lang.rsc "GEM>LANG.RSC" \
	    --add build/816.com "GEM>816.COM" \
	    --add build/gem4xe.cfg "GEM>GEM4XE.CFG"
SP_APPS   = --mkdir APPS \
	    --add build/clockacc.g4a "GEM>CLOCK.ACC" \
	    --add build/clock.rsc "GEM>CLOCK.RSC" \
	    --add build/cpanelacc.g4a "GEM>CONTROL.ACC" \
	    --add build/cpanel.rsc "GEM>CPANEL.RSC" \
	    --add build/calcacc.g4a "GEM>CALC.ACC" \
	    --add build/calc.rsc "GEM>CALC.RSC" \
	    --add build/calc.g4a "APPS>CALC.PRG" --add build/calc.rsc "APPS>CALC.RSC" \
	    --add build/clock.g4a "APPS>CLOCK.PRG" --add build/clock.rsc "APPS>CLOCK.RSC"
SP_DEPS   = build/gem.xex build/lang.rsc build/816.com build/gem4xe.cfg $(DESK_DEPS) $(APP_DEPS) $(ACCP_DEPS) tools/mkspdisk.py tools/atr.py

build/gem-shots.atr: $(SP_DEPS)
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) $(SP_LAYOUT) $(SP_APPS)

# The CF card: an APT table and two SDFS partitions, with the system in
# \GEM\ and the demonstration application in \APPS\ -- the install
# layout of docs/shipping.md section 4, on the volume it was written for.
# It needs no fixture: unlike a floppy, a card carries no DOS of its own,
# because SpartaDOS X boots from U1MB flash and the U1MB's PBI BIOS --
# from the same flash -- reads the APT table and mounts the partitions as
# D1: and D2: before any DOS runs.  No SIDE.SYS, no driver on the card.
# tools/apt.py writes the table, tests/host/test_apt.py checks it against
# the rules Altirra's own parser applies, and test-cf boots it.
build/gem-cf.img: build/gem.xex build/desktop.g4a build/desktop.rsc build/prefs.rsc build/hello_app.g4a \
                  build/lang.rsc build/gem4xe.cfg build/816.com $(APP_DEPS) $(ACCP_DEPS) tools/mkcf.py tools/apt.py tools/atr.py
	@rm -f $@
	python3 tools/mkcf.py $@

# The same card with CLOCK=DOS in its GEM4XE.CFG.  The emulated U1MB and
# SIDE 2 both carry the chip, so on the card above the DOS is never
# asked; this one makes src/sys/clock.c ask it, which is what a machine
# with neither -- an Antonia and an IDE Plus 2 -- does on its own.
build/gem-cf-dosclock.img: build/gem-cf.img build/dosclock.cfg
	@rm -f $@
	python3 tools/mkcf.py $@ --cfg build/dosclock.cfg

# The same card in the shape an SD card takes in a SubCart or an AVGCART:
# a 64 MB FAT32 partition first (the cart's own browser reads it), the
# APT table and the two partitions after it.  The cart's SIDE 2
# emulation hands the whole card to the U1MB's PBI BIOS, so the boot is
# test-cf's; test-sd runs it on this image.  Needs mkfs.fat (dosfstools),
# so it is `make sd`, not part of `all`.  GEMDIAG.COM rides along: the
# card is what goes to a real machine (docs/phase39.md).
sd: build/gem-sd.img
build/gem-sd.img: build/gem-cf.img build/gemdiag.com
	@rm -f $@
	python3 tools/mkcf.py $@ --fat 64 --add build/gemdiag.com "GEM>GEMDIAG.COM"

# The release floppy: the card's system partition on a double-sided
# double-density SDFS disk, and NO DOS -- it boots under the SpartaDOS X
# in a cartridge or in U1MB flash, which is the one DOS that lives in the
# machine rather than on the disk, so the disk is gem4xe's to give away
# where gem-boot.atr is not.  Needs no fixture to build; test-boot boots
# it when [spartados].sdx_cart names a cartridge.
build/gem-sdx.atr: build/gem.xex build/desktop.g4a build/desktop.rsc build/prefs.rsc \
                   build/lang.rsc build/gem4xe.cfg build/816.com tools/mkfloppy.py tools/mkcf.py tools/atr.py
	@rm -f $@
	python3 tools/mkfloppy.py $@

# ...and its other half: the applications and the desk accessory, with an
# INSTALL.BAT of their own and no AUTOEXEC.BAT, because it is not a boot
# disk (tools/mkfloppy.py, docs/media.md).  No DOS, so it travels too.
build/gem-apps.atr: build/hello_app.g4a $(APP_DEPS) $(ACCP_DEPS) tools/mkfloppy.py tools/mkcf.py tools/atr.py
	@rm -f $@
	python3 tools/mkfloppy.py --apps $@

# The SpartaDOS disk: a fresh SDFS volume booting the 3.2 fixture's DOS,
# the same files as the DOS 2 disk, the shell's applications and a
# directory tree for the selector (tools/mkspdisk.py).  2048 sectors of
# 128: SpartaDOS loads M3.COM's 100 KB from anywhere, where DOS 2.5 could
# not go past sector 720 -- and 1040 no longer hold it with the desktop
# beside it.  The gates size everything from the image, not from here.
# 2560 sectors, which is bigger than a floppy on purpose: it leaves more
# than 999 free, and 999 is what a directory listing's three characters
# could say.  Dfree reads the file system's own count now (src/sys/gemdos.c),
# so test-m15 proves the old ceiling is gone rather than describing it.
SP_SECTORS = --sectors 2560
build/m14-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES)

# The accessories' disk (test-m22): test-m16's, with the two programs
# and their resources added.  A disk of its own rather than SHELL_FILES,
# because the file layer's gates count what is in a directory -- the
# selector shows nine names and test-m12 predicts the listing -- and four
# more files there would be four more names.
build/m22-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) $(APP_DEPS) tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES) $(APP_FILES)

# The large-data gate's disk (test-m29): test-m16's stand-in desktop and
# the one program in the tree compiled --data-model=large, in the root.
# A disk of its own rather than test-m22's, because adding a file to a
# fixture moves every pool and directory number the gates on it measure
# (docs/phase15.md).
build/m29-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) build/m29_big.g4a tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES) \
	    --add build/m29_big.g4a M29.PRG

# The far-resource gate's disk (test-m33): the stand-in desktop, the two
# builds of the one program, and the resource neither could load before.
build/m33-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) build/m33_farrsc.g4a build/m33s_farrsc.g4a build/farrsc.rsc tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES) \
	    --add build/m33_farrsc.g4a M33.PRG --add build/m33s_farrsc.g4a M33S.PRG \
	    --add build/farrsc.rsc FARRSC.RSC

# And the same again for the application whose far IMAGE crosses a bank
# (src/m31_huge.c).  Its own disk for the reason m29's is its own: a file
# added to a fixture moves every pool and directory number the gates on it
# measure.
build/m31-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) build/m31_huge.g4a tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES) \
	    --add build/m31_huge.g4a M31.PRG

# The console gate's disk (test-m32), its own for the same reason: the
# stand-in desktop, and the program as M32.PRG in the root.
build/m32-boot.atr: build/m3.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(SHELL_DEPS) build/m32_con.g4a build/m32_kid.g4a tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(SHELL_FILES) \
	    --add build/m32_con.g4a M32.PRG --add build/m32_kid.g4a M32KID.PRG

# The desktop gate's disk (test-m17): the runner again, with the real
# desktop and its resource where test-m16's stand-in was.
build/m17-boot.atr: build/m3desk.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(DESK_DEPS) tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(DESK_FILES)

# The desktop-and-accessory gate's disk (test-m23): test-m17's, with the
# two accessories in \APPS\ as the product media carries them.  This is
# the disk that reproduces the user's own layout -- the real desktop, a
# folder, and an application inside it that waits for the mouse.
# The accessories gate's disk (test-m28): test-m17's, with one accessory
# in the system's directory, which is where the AES looks for *.ACC.
build/m28-boot.atr: build/m3desk.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(DESK_DEPS) $(ACC_DEPS) tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(DESK_FILES) $(ACC_FILES)

build/m23-boot.atr: build/m3desk.xex tests/fixtures/test.txt tests/fixtures/out.txt build/test.rsc $(DESK_DEPS) $(APP_DEPS) tools/mkspdisk.py tools/atr.py
	@test -n "$(SRC_SP32)" || { echo "no SpartaDOS fixture: set [spartados].disk_32 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkspdisk.py "$(SRC_SP32)" $< $@ $(SP_SECTORS) --tree $(DISK_FILES) $(DESK_FILES) $(APP_FILES)

# The same program linked with bank $01 cut down to its top 16 KB, so that
# the far image is forced to spill into bank $02 today rather than on the day
# the code grows past 64 KB.  test-m6 boots this one as well as the real
# build and requires both to copy up, run from the bank the linker chose, and
# start the far heap above it.  The layout function is in src/gem4xe.scm.
build/m6split.elf: $(M3_OBJS) src/gem4xe.scm
	$(LD) src/gem4xe.scm $(M3_OBJS) -o $@ $(LIB) $(LDFLAGS) --list-file build/m6split.map \
	      --memories-expression "(layout #x01c000 #x67ff)"

build/m6split.xex: build/m6split.elf
	python3 tools/mkxex.py $< $@ --entry _atari_entry --syms build/m6split.sym

# Same program, same disk shape as the runner's: double density, called
# M3, started from the DOS menu's BINARY LOAD.
build/m6split-boot.atr: build/m6split.xex
	@test -n "$(SRC_DD)" || { echo "no double-density DOS fixture: set [dos].dd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DD)" $< $@ M3 --sweep

build/m2-boot.atr: build/m2.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ M2.COM $(DISK_DENSITY)

build/m27-boot.atr: build/m27.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ M27.COM $(DISK_DENSITY)

build/m24-boot.atr: build/m24.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ M24.COM $(DISK_DENSITY)

build/hello-boot.atr: build/hello.xex
	@test -n "$(SRC_DOS)" || { echo "no DOS fixture: set [dos].sd_dos2 in fixtures.toml"; exit 1; }
	@rm -f $@
	python3 tools/mkdisk.py "$(SRC_DOS)" $< $@ HELLO.COM $(DISK_DENSITY)

test: test-host check-cc test-emu test-m1 test-m2 test-m3 test-m4 test-m5 test-m5p test-m6 test-m7 test-m8 test-m9 test-m10 test-m11 test-m12 test-m13 test-m14 test-m14x test-m15 test-m15x test-m15d test-m16 test-m17 test-m18 test-m19 test-m20 test-m21 test-m22 test-m23 test-m24 test-m25 test-m26 test-m27 test-m28 test-m29 test-m30 test-m31 test-m32 test-m32n test-m33 test-boot test-install

# GACS's engine on the 65816 -- the application gem4xe exists for, asked
# whether it still compiles, links and computes there (docs/gacs.md).
# Needs the GACS checkout (GACS=, default ~/dev/gacs) and Calypsi's own
# simulator, so it is not part of `make test`: it depends on another
# project, the way test-m14u depends on a flash image.
gacs-check:
	python3 tools/gacscheck.py

# The cc65816 code generation bugs gem4xe works around, run in the vendor's
# own simulator: fails only if a workaround shape has stopped compiling
# right; a bug that has gone away is reported so its workaround can go.
check-cc:
	python3 tools/ccbug/check.py --calypsi $(CALYPSI)

# B17's scan: every source compiled alone at -O2, looking for a call the
# compiler reaches with an 8-bit accumulator.  Not part of `make test`,
# because it compiles the whole tree a second time; run it after a
# toolchain change, or when something dies inside a callee that is not
# at fault.
mscan:
	python3 tools/ccbug/mscan.py --tree

# Calypsi #82's shape: a negative Y with LONG addressing, where the
# 65816 adds Y to a 24-bit base as unsigned 16 bits and the access
# lands one bank away.  Fixed in the 5.18 this tree requires, so this
# guards a shape rather than a live bug -- but the author who found it
# reports the compiler picks the bad form by register pressure, which
# testing cannot catch and only reading the output can.  check-cc
# asserts the fixture still reports both of its sites.
negyscan:
	python3 tools/ccbug/negyscan.py --tree

# The host tests want the gate application built, because the kit's own
# test rebuilds it out of the kit and compares the bytes: what test-m11
# proves about that binary is what the kit inherits.
# Built only when the Calypsi tool chain is here.  The host tests are the
# part of the suite that needs nothing but Python 3, and CI runs them on a
# machine that has no compiler (.github/workflows/host-tests.yml); every
# case that wants a built program skips itself when it is absent, but a
# prerequisite cannot, so these are asked for conditionally rather than
# always.  GEM.COM is here because tests/host/test_licence.py refuses to
# pass by skipping: it asserts build/gem.map exists, so the product must
# be linked before the host tests run.  `make test` puts test-host first
# and on a clean tree nothing had linked it -- the m11_app fixture alone
# makes *a* map, which lifts that file's "no maps" skip without making
# the one it actually checks.
test-host: $(if $(wildcard $(CC65816)),build/m11_app.g4a build/gem.xex)
	python3 -m unittest discover -s tests/host -t .

# The application kit (tools/mksdk.py, tools/sdk/): what somebody who is
# not this repository needs in order to build a program that runs on
# gem4xe -- the header, the bindings and the start-up as source, the
# linker's rules, the packer, and one whole example.  Its gate is in the
# host tests (tests/host/test_sdk.py), which builds it out of a copy of
# itself in a directory of its own.
SDK_FILES = tools/mksdk.py tools/sdk/README.md tools/sdk/Makefile \
            tools/sdk/hello.c src/app/gem.h src/portab.h src/app/gemlib.c \
            src/app/gemabi.s src/app/crt_gemapp.s src/app/gemapp.scm \
            src/sys/clib.c tools/mkg4a.py tools/mkxex.py COPYING

sdk: build/gem4xe-sdk.tar.gz
build/gem4xe-sdk.tar.gz: $(SDK_FILES)
	python3 tools/mksdk.py build/gem4xe-sdk --tar $@

# The distribution: what a tester is handed -- the bootable disks, the
# system's files loose for a disk of their own, the kit, and a page that
# says how to try it (tools/dist/README.md, filled in by tools/mkdist.py
# from the images and from the desktop's own menu, so the half of it
# that could go stale cannot).  DIST is the name it takes: the date and
# the commit unless you say otherwise.
DIST ?= build/gem4xe-$(shell date +%F)-$(shell git rev-parse --short HEAD 2>/dev/null || echo local)
DIST_DISKS = build/gem-boot.atr build/gem-sdx.atr build/gem-apps.atr build/gem-cf.img
DIST_SYS   = build/gem.xex build/desktop.g4a build/desktop.rsc \
             build/lang.rsc build/816.com build/hello_app.g4a build/gem4xe.cfg \
             build/prefs.rsc \
             $(APP_DEPS) $(ACCP_DEPS)

dist: $(DIST_SYS) $(DIST_DISKS) build/gem4xe-sdk.tar.gz \
      tools/mkdist.py tools/dist/README.md tools/mksdk.py
	python3 tools/mkdist.py $(DIST) --tar $(DIST).tar.gz

# The release: the distribution for the public.  What differs is what it
# does NOT carry -- gem-boot.atr boots a DOS that is not gem4xe's to give
# away (fixtures.toml.example), so it stays home and the page says so --
# and the name, which is the version in VERSION rather than the date.  It
# comes as a tarball and, for Windows, the same tree as a zip; the two
# DOS-less floppies travel on their own as well, under the release's name,
# for whoever wants the disks and nothing else.  One checksum file covers
# the four, for the release page.  The first line asks the desktop's
# resource what version its About box says, because 0.1.1 went out
# saying 0.1 (phase38.md).
VERSION := $(shell cat VERSION)
RELEASE  = build/gem4xe-$(VERSION)

release: $(DIST_SYS) build/gem-cf.img build/gem-sdx.atr build/gem-apps.atr build/gem4xe-sdk.tar.gz \
         tools/mkdist.py tools/dist/README.md tools/mksdk.py
	@python3 -c 'import sys; sys.exit(b"version $(VERSION)\0" not in open("build/desktop.rsc","rb").read())' \
	    || { echo "build/desktop.rsc does not say version $(VERSION) (phase38.md)"; exit 1; }
	python3 tools/mkdist.py $(RELEASE) --public --tar $(RELEASE).tar.gz --zip $(RELEASE).zip
	cp build/gem-sdx.atr $(RELEASE).atr
	cp build/gem-apps.atr $(RELEASE)-apps.atr
	cd build && sha256sum gem4xe-$(VERSION).tar.gz gem4xe-$(VERSION).zip gem4xe-$(VERSION).atr \
	    gem4xe-$(VERSION)-apps.atr > gem4xe-$(VERSION).sha256

test-emu: 
	python3 tests/emu/p0_probe.py

test-m1: build/hello-boot.atr
	python3 tests/emu/m1_toolchain.py

test-m2: build/m2-boot.atr
	python3 tests/emu/m2_vbxe.py

test-m3: build/m3-boot.atr
	python3 tests/emu/m3_vdi.py

test-m4: build/m3-boot.atr
	python3 tests/emu/m4_aes.py

# The same probe on a SECOND MACHINE: a bare 65C816 with high banks and
# no accelerator, which is what an Antonia is and what proves nothing here
# depends on the Rapidus.  Needs this tree's AltirraSDL fork for --cpu and
# --highbanks (tools/altirra/altirra-sdl-cpu-highbanks.patch).
test-m5p: build/m3-boot.atr
	python3 tests/emu/m5_farmem.py --plain816

test-m5: build/m3-boot.atr
	python3 tests/emu/m5_farmem.py

test-m6: build/m3-boot.atr build/m6split-boot.atr
	python3 tests/emu/m6_farcode.py

# The event and form layer driven from the host: keys through POKEY, the
# pointer through ptr_state, frames counted -- and the reference walks the
# same input plan.
test-m7: build/m3-boot.atr
	python3 tests/emu/m7_form.py

# The window manager: wind_* against the reference's model of the rectangle
# lists, with the redraw messages the application would get and the pixels
# of every uncover, move and slider change.
test-m8: build/m3-boot.atr
	python3 tests/emu/m8_wind.py

# The menu library: menu_bar and the calls that change a menu tree, then
# hovers and presses through the bar while the application waits, with
# screenshots taken inside the wait for the drop-downs themselves.
test-m9: build/m3-boot.atr
	python3 tests/emu/m9_menu.py

# Native-mode interrupts: the OS ROM shadowed under itself and the vectors
# filled, then each source counted against the emulator -- frames, the
# POKEY timer's rate, keys into the ring, a trak-ball's counts taken in
# the handler with nothing polling -- and finally the return to DOS.
test-m10: build/m3-boot.atr
	python3 tests/emu/m10_irq.py

# The application ABI: the gate application is loaded from the blob in the
# image, relocated into the pool and a far bank, and run; every word it
# got back through the ABI's copy-out is compared with the reference's,
# and the screen with the reference's screen.
test-m11: build/m3-boot.atr build/m11_app.sym
	python3 tests/emu/m11_abi.py

# The same gate with Rapidus OS as the machine's OS ([rapidus].os in
# fixtures.toml): the application's COP that is not gem4xe's must reach the
# OS and be answered, where test-m11 requires it refused.
SRC_RAPIDUS_OS ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['rapidus']['os'])" 2>/dev/null)
test-m11-os: build/m3-boot.atr build/m11_app.sym
	@test -n "$(SRC_RAPIDUS_OS)" || { echo "no Rapidus OS fixture: set [rapidus].os in fixtures.toml"; exit 1; }
	python3 tests/emu/m11_abi.py --os="$(SRC_RAPIDUS_OS)"

# GEM under Rapidus OS with SpartaDOS X's 65816.SYS loaded from CONFIG.SYS
# ([rapidus].os, [spartados].sdx_cart and .driver_65816): the desktop must
# come up, which it did not while a process record's resource slots were
# left as the pool had them (docs/phase41.md).
SRC_65816 ?= $(shell python3 -c "import tomllib;print(tomllib.load(open('fixtures.toml','rb'))['spartados']['driver_65816'])" 2>/dev/null)
test-sdx816: build/gem-sdx.atr build/gem.sym build/desktop.sym
	@test -n "$(SRC_RAPIDUS_OS)" && test -n "$(SRC_SDX)" && test -n "$(SRC_65816)" || { echo "needs [rapidus].os, [spartados].sdx_cart and [spartados].driver_65816 in fixtures.toml"; exit 1; }
	python3 tests/emu/sdx816.py --os="$(SRC_RAPIDUS_OS)" --cart="$(SRC_SDX)" --driver="$(SRC_65816)"

# The file layer: CIO called through the OS from native mode, rsrc_load
# and rsrc_obfix against tools/rsc.py, the shell library's buffers, and
# the file selector driven over two disks -- its listings predicted from
# the images with tools/atr.py, its screens compared with the reference's.
test-m12: build/m3-boot.atr build/m12-d2.atr
	python3 tests/emu/m12_file.py

# Alerts and the pointer's shape: form_alert's parsing, layout and drawing
# against the reference, and each of graf_mouse's forms on the screen.
test-m13: build/m3-boot.atr
	python3 tests/emu/m13_alert.py

# SpartaGEM: the same program on a SpartaDOS disk, loaded by SpartaDOS
# 3.2g from it (test-m14) and by SpartaDOS X 4.50 from the vendor's
# emulator cartridge with the disk as D1: (test-m14x).  The DOS seam,
# CIO in the directory tree and the file selector walking it, against
# the image and the reference.
test-m14: build/m14-boot.atr
	python3 tests/emu/m14_sparta.py

test-m14x: build/m14-boot.atr
	@test -n "$(SRC_SDX)" || { echo "no SDX fixture: set [spartados].sdx_cart in fixtures.toml"; exit 1; }
	python3 tests/emu/m14_sparta.py --sdx="$(SRC_SDX)"

# ... and SpartaDOS X from an Ultimate 1MB flash image, U1MB switched on
# (test-m14u, test-m15u): the machine as it is actually built.  Not in
# `make test`: it needs the patched emulator and a saved BIOS profile.
test-m14u: build/m14-boot.atr
	@test -n "$(SRC_U1MB)" || { echo "no U1MB fixture: set [u1mb].flash in fixtures.toml"; exit 1; }
	python3 tests/emu/m14_sparta.py --u1mb="$(SRC_U1MB)"

# GEMDOS on CIO: the ST's trap #1 as a call block, answered from CIO and
# the DOS seam -- searches, paths, files, far memory, errors -- against the
# image, on SpartaDOS 3.2g (test-m15), SpartaDOS X (test-m15x) and DOS 2
# (test-m15d), whose flat directory answers the tree calls with EPTHNF.
test-m15: build/m14-boot.atr
	python3 tests/emu/m15_gdos.py

test-m15x: build/m14-boot.atr
	@test -n "$(SRC_SDX)" || { echo "no SDX fixture: set [spartados].sdx_cart in fixtures.toml"; exit 1; }
	python3 tests/emu/m15_gdos.py --sdx="$(SRC_SDX)"

test-m15u: build/m14-boot.atr
	@test -n "$(SRC_U1MB)" || { echo "no U1MB fixture: set [u1mb].flash in fixtures.toml"; exit 1; }
	python3 tests/emu/m15_gdos.py --u1mb="$(SRC_U1MB)"

test-m15d: build/m3-boot.atr build/m12-d2.atr
	python3 tests/emu/m15_gdos.py --dos2

# The shell loop: sh_main runs DESKTOP.PRG, what it asks for, the desktop
# again, until it asks to shut down -- with the harness at the keyboard
# and the screen checked against the model at each stop.  On the SpartaDOS
# disk, the only runner disk with room for the .G4A files.
test-m16: build/m14-boot.atr
	python3 tests/emu/m16_shell.py

# The desktop: DESKTOP.PRG under the shell, driven at the mouse and checked
# against tools/deskref.py -- the desktop itself transcribed against the AES
# model (phase 14, milestone 4).
test-m17: build/m17-boot.atr build/desktop.g4a build/desktop.sym
	python3 tests/emu/m17_desktop.py

# The two accessories (src/apps): the calculator driven at its keypad and
# the clock left to tick, both run through the shell loop and both checked
# against what the host AES makes of their own resources.
test-m22: build/m22-boot.atr build/calc.sym build/clock.sym
	python3 tests/emu/m22_apps.py

# A program run from the desktop and the desktop's windows back after it
# (phase 14, milestone 6): two runs of the desktop against the model, with
# M11.PRG between them.
test-m18: build/m17-boot.atr build/desktop.g4a build/desktop.sym
	python3 tests/emu/m18_launch.py

# An accessory opened from a folder and used: the real desktop at the
# mouse, a folder, and a program that waits for the mouse itself.
test-m23: build/m23-boot.atr build/desktop.g4a build/desktop.sym build/calc.sym
	python3 tests/emu/m23_deskapp.py

# The ANTIC surface, on a machine with no VBXE in it at all.
test-m24: build/m24-boot.atr
	python3 tests/emu/m24_antic.py

test-m27: build/m27-boot.atr
	python3 tests/emu/m27_ctx.py

test-m28: build/m28-boot.atr
	python3 tests/emu/m28_acc.py

test-m29: build/m29-boot.atr
	python3 tests/emu/m29_big.py

# A resource in far memory, and the same file refused to a program that
# cannot hold a far address (docs/far-trees.md, step 2).
test-m33: build/m33-boot.atr
	python3 tests/emu/m33_farrsc.py

# GEMDOS's console, standard handles, memory calls and Pterm, from a
# program that never calls the AES (docs/phase42.md).
test-m32: build/m32-boot.atr build/m32_con.sym
	python3 tests/emu/m32_con.py

# The same program on an NTSC machine -- the only gate that runs one.  The
# frame is 16.7 ms there, and vex_timv says so (src/vdi/vdi.c); a tick of
# 20 ms assumed on it made every evnt_timer a fifth short, which the timer
# case's floor on evnt_timer(500) is placed to catch.  The screens are
# not compared: the models are laid out on a PAL frame.
test-m32n: build/m32-boot.atr build/m32_con.sym
	python3 tests/emu/m32_con.py --ntsc

# An application bigger than a bank, loaded and run.  tests/host/test_g4a.py
# proves the FILE -- that applying its fixups reproduces the linker's own
# shifted link, byte for byte -- and this proves the LOADER, which is the
# half a Python check cannot reach: format 2's three-byte fixup offsets and
# the chunked image copy that replaced a memcpy_far whose size_t is sixteen
# bits.  Both failures would have been quiet.
test-m31: build/m31-boot.atr
	python3 tests/emu/m31_huge.py

# The VDI on the printer, and the page off the machine: the third device
# through the seam, checked from the files it writes rather than from a
# screenshot, because paper is not photographable from here.
test-m30: build/m30-boot.atr
	python3 tests/emu/m30_print.py

# Where bank $00 has gone, and whether there is enough of it left.  Run it
# after a change that adds a table or a program; tests/host/test_memory.py
# runs it too, so make test says so without being asked.
memcheck: build/gem.xex build/m3desk.xex build/desktop.g4a build/desktop.rsc build/clockacc.g4a build/clock.rsc
	python3 tools/memreport.py

# ...and the VDI itself on it: the same vdi.c, the other side of the seam.
test-m25: build/m25-boot.atr
	python3 tests/emu/m25_antic_vdi.py

# ONE BINARY, TWO SCREENS: the shipped GEM.COM on a machine with a VBXE
# and on one without, and then the safe mode -- VIDEO=ANTIC in
# GEM4XE.CFG beating a VBXE that works.  Nothing is typed in any of the
# three; the disks start GEM themselves.
test-m26: build/gem-boot.atr build/gem-antic.atr build/gem.sym
	python3 tests/emu/m26_fallback.py

# The desktop's writes to a disk (phase 14, milestone 7; phase 19): File
# -> New folder, File -> Delete, and File -> Show info -- which is also
# the rename -- driven at the mouse and the keyboard against the model,
# and the disk image read back when the run is over.
# The gate boots a copy of milestone 5's disk, made afresh every run --
# it is the first whose target rewrites the directory it booted from.
test-m19: build/m17-boot.atr build/desktop.g4a build/desktop.sym
	python3 tests/emu/m19_files.py

# What the system says, and where it says it from (docs/shipping.md,
# section 5): form_error on three disks -- the product's LANG.RSC, a
# translation of it, and no file at all -- each compared with the model
# given the strings that disk carries.
test-m20: build/m3-boot.atr build/lang.rsc
	python3 tests/emu/m20_lang.py

# A loadable font (docs/shipping.md, section 5): the system font as a
# file, inverted so every glyph differs, loaded at start-up off one disk
# and absent from another -- with vqt_name, vst_font and the GDOS pair
# either way.
test-m21: build/m3-boot.atr build/inv.fnt
	python3 tests/emu/m21_font.py

# The product disk booting into the desktop with nothing typed: the
# batch file the SpartaDOSes run, the loader's refusal on the 6502, the
# switch, and the desk against the model (docs/shipping.md, section 2).
# EVERY product disk: the gate reads them all, and naming only one here
# left the other stale whenever GEM.COM was rebuilt -- which looked exactly
# like the far image being mangled by the DOS, and cost an afternoon
# twice (docs/phase16.md).
# gem-sdx.atr carries no DOS and boots under the SDX cartridge fixture;
# with none named it is read but not booted, and the gate says so rather
# than failing.  gem-apps.atr is not a boot disk and is only read
# (tests/emu/product_boot.py).
test-boot: build/gem-boot.atr build/gem-sdx.atr build/gem-apps.atr build/desktop.g4a build/desktop.sym
	python3 tests/emu/product_boot.py --sdx="$(SRC_SDX)"

# The same boot off the product CF card, on the machine this project is
# for: the U1MB flash's SpartaDOS X and PBI BIOS, a SIDE 2 with the card
# on its IDE bus.  Outside `make test` for the same reason as test-m14u:
# it needs both the U1MB fixture and the patched emulator (ALTIRRASDL=).
# The installer (docs/media.md): SpartaDOS X runs each floppy's INSTALL.BAT
# onto a blank drive, the drive is listed, and the machine boots GEM from
# it -- the accessory from the applications disk loaded beside the desktop.
test-install: build/gem-sdx.atr build/gem-apps.atr build/gem.sym
	@test -n "$(SRC_SDX)" || { echo "no SDX fixture: set [spartados].sdx_cart in fixtures.toml"; exit 1; }
	python3 tests/emu/install.py --sdx="$(SRC_SDX)"

test-cf: build/gem-cf.img build/desktop.g4a build/desktop.sym
	@test -n "$(SRC_U1MB)" || { echo "no U1MB fixture: set [u1mb].flash in fixtures.toml"; exit 1; }
	python3 tests/emu/cf_boot.py

test-sd: build/gem-sd.img build/desktop.g4a build/desktop.sym
	@test -n "$(SRC_U1MB)" || { echo "no U1MB fixture: set [u1mb].flash in fixtures.toml"; exit 1; }
	python3 tests/emu/cf_boot.py --card build/gem-sd.img

test-cf-dosclock: build/gem-cf-dosclock.img build/desktop.g4a build/desktop.sym
	@test -n "$(SRC_U1MB)" || { echo "no U1MB fixture: set [u1mb].flash in fixtures.toml"; exit 1; }
	python3 tests/emu/cf_boot.py --card build/gem-cf-dosclock.img

# The same card on every U1MB firmware release in [u1mb.firmware] (fixtures.toml,
# name = flash image).  The gate walks the BIOS setup by what its screen says, so
# one gate covers releases whose setup pages differ (docs/shipping.md); each
# release logs to build/cf-firmware/<name>.log, and any failure fails the run.
U1MB_FW ?= $(shell python3 -c "import tomllib;fw=tomllib.load(open('fixtures.toml','rb'))['u1mb'].get('firmware',{});print(' '.join(k+'='+v for k,v in fw.items()))" 2>/dev/null)
test-cf-firmware: build/gem-cf.img build/desktop.g4a build/desktop.sym
	@test -n "$(U1MB_FW)" || { echo "no firmware list: set [u1mb.firmware] in fixtures.toml"; exit 1; }
	@mkdir -p build/cf-firmware; bad=; \
	for t in $(U1MB_FW); do \
	  v=$${t%%=*}; rom=$${t#*=}; \
	  if python3 tests/emu/cf_boot.py --flash "$$rom" > build/cf-firmware/$$v.log 2>&1; \
	  then echo "U1MB $$v: PASS"; \
	  else echo "U1MB $$v: FAIL, build/cf-firmware/$$v.log"; bad="$$bad $$v"; fi; \
	done; \
	test -z "$$bad" || { echo "test-cf-firmware: failed on$$bad"; exit 1; }

# A GEM-style desktop drawn entirely through the 37 VDI opcodes, screenshotted
# and checked against the reference.  A demo that is also a regression test.
demo: build/m3-boot.atr
	python3 tests/emu/demo_desktop.py

# A session with the AES itself -- menu, dialog, a window opened, dragged,
# sized, fulled and closed -- driven through the emulator's input and
# captured a frame at a time into build/movie/gem4xe.mp4 and .gif.  Every
# result and screenshot is checked against the reference as the gates are.
# `--keep-frames` keeps the PNGs; `--dry` runs the model only.
movie: build/m3-boot.atr
	python3 tests/emu/demo_aes.py

# The product booted and used -- the desktop, its menus and dialogs, a
# folder, both views, the calculator, the clock accessory -- photographed
# into docs/shots/ as 640x480 PNGs for the README and the release page.
# Coordinates are read out of the running desktop's own object trees, so
# it is a tour, not a script of pixel positions; it is not a gate.
shots: build/gem-shots.atr build/desktop.sym build/calc.sym
	python3 tests/emu/shots.py --disk build/gem-shots.atr

# GEMBench's tests, shaped for this machine: the dialog, text, graphics,
# window, divide, float, RAM, ROM and blit rows timed to a VCOUNT tick
# and reported in milliseconds.  Not a gate; the baseline is docs/bench.md.
bench: build/m3-boot.atr
	python3 tests/emu/bench_gem.py

# NEVER `pkill -f AltirraSDL` here: the pattern matches this shell too and
# takes the session with it.  pgrep -x matches the process NAME only.
# An emulator halted at a debugger breakpoint ignores SIGTERM, so escalate
# rather than reporting a kill that did not happen.
emu-stop:
	@pgrep -x AltirraSDL | while read p; do kill $$p 2>/dev/null; done; true
	@sleep 1; pgrep -x AltirraSDL | while read p; do \
		kill -9 $$p 2>/dev/null && echo "emu-stop: SIGKILL $$p (was wedged)"; done; true
	@n=$$(pgrep -x AltirraSDL | wc -l); echo "emu-stop: $$n emulator(s) left"

clean:
	rm -rf build

.PHONY: all fonts sdk dist release diag memcheck gacs-check shots test test-host check-cc mscan negyscan test-emu test-m1 test-m2 test-m3 test-m4 test-m5 test-m5p test-m6 test-m7 test-m8 test-m9 test-m10 test-m11 test-m12 test-m13 test-m14 test-m14x test-m14u test-m15 test-m15x test-m15u test-m15d test-m16 test-m17 test-m18 test-m19 test-m20 test-m21 test-m22 test-m23 test-m24 test-m25 test-m26 test-m27 test-m28 test-m29 test-m30 test-m31 test-m32 test-m32n test-m33 test-boot test-install test-cf test-sd test-cf-dosclock test-cf-firmware test-m11-os test-sdx816 sd demo movie bench emu-stop clean
