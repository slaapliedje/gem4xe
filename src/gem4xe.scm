;;; gem4xe linker rules -- Atari XL/XE, 65C816 with linear RAM.
;;;
;;; Bank $00 (BASIC off, DOS resident, XL OS on):
;;;   $0000-$00FF  OS zero page          -- not ours
;;;   $0100-$01FF  6502 stack page       -- not ours (we run a 16-bit stack elsewhere)
;;;   $0200-$06FF  OS vars / page 6      -- not ours ($02E0/$02E2 are the .xex vectors)
;;;   $0700-$1FFF  DOS resident          -- not ours
;;;   $2000-$20FF  direct page           <- ours
;;;   $2100-$375F  stack / data / zdata  <- ours (the stack is 2 KB; see below)
;;;   $37B0-$3FFD  near code and rodata  <- ours
;;;                (that boundary moves; the memories below are what it is)
;;;   $3FFE-$3FFF  the cstartup's reset word, inert
;;;   $4000-$47FF  zwin: bss no interrupt handler touches  <- ours; see BANKED
;;;   $4800-$67FF  the application pool             <- ours; see BANKED below
;;;   $6800-$7FFF  the test runner's host-poked buffers        <- ours
;;;                (the runner's link; GEM.COM gives the pool the whole window)
;;;   $8000-$9BFF  RESERVED: VBXE MEMAC A window       -- nothing may RUN here,
;;;                but it is plain RAM until vbxe_init() opens the window, so
;;;                farload's staging buffer and its unpacker borrow it at
;;;                LOAD time (farstage, stagecode)
;;;   $9C00-$9FFF  the rest of the MEMAC window: SpartaDOS X's screen
;;;                (MEMTOP $9C1F), so not even the stage goes there
;;;   $A000-$BFFF  NOT OURS: SpartaDOS X is a cartridge and this is it.
;;;                Under a disk DOS it is RAM and gem4xe leaves it alone.
;;;   $C000-$CFFF  OS ROM   -- and under it, RAM a DOS may live in (src/sys/irq.c)
;;;   $D000-$D7FF  hardware (VBXE regs at $D640/$D740)
;;;   $D800-$FFFF  OS ROM   -- likewise
;;;
;;; THE BANKED WINDOW, $4000-$7FFF.  On a 130XE, a U1MB or an Axlon this is
;;; where extended RAM is switched in by PORTB (or $CFFF), and the first
;;; twelve phases kept out of it for that reason.  It is main RAM whenever
;;; the bank bits are at their reset values, which is whenever nobody is in
;;; the middle of banking -- and the only thing that banks on a gem4xe
;;; machine is a DOS servicing its own call: SpartaDOS X with USE BANKED
;;; keeps its buffers and drivers in a "system bank" here and switches it in
;;; while it works, and a RAMdisk driver does the same.  Both put it back
;;; before returning, and both address a caller's buffer in main memory
;;; through their memory-index mechanism (SDX Programming Guide 4.50, 3.7
;;; and 22.4.3: main RAM is index $00 and the transfer loops live below
;;; $4000 for exactly this reason), so a CIO buffer here is served
;;; correctly.  On a Rapidus the accelerator's window 1 is bypassed for as
;;; long as PORTB has the bank in (Altirra rapidus.cpp, UpdateSRAMWindows:
;;; window1Enabled = !slow && !xramEnabled), so the SRAM copy of the pool is
;;; neither read nor written by the DOS's bank work, and the pool is FAST --
;;; which $A000, sharing its window with MEMAC, never was.  What the region
;;; may not hold is anything an interrupt handler needs, since a handler can
;;; run while a bank is in; gem4xe's are all in $2000-$3FFF.
;;;
;;; Banks $01-$0F: the far code, two memories per bank (the hole below).  A probe
;;; (src/sys/farmem.c) finds one unbroken run of RAM from bank $01 to $EF on a
;;; Rapidus, but only the first megabyte of it is the accelerator's SRAM; the
;;; far image is kept inside that, and the far heap starts in the bank after
;;; the last one the image reached.
;;;
;;; ONE MEMORY PER BANK, NOT ONE MEMORY SPANNING THEM.  The 65816 program
;;; counter wraps within its bank, so a function that straddles $01FFFF /
;;; $020000 is executed as two unrelated halves.  The linker does not know
;;; that: given a single memory $010000-$0FFFFF it will happily place a
;;; function across the seam (tried, and it did).  Given fifteen memories it
;;; fills them in the order they are defined and never splits a fragment, so
;;; every function lands whole inside one bank and the image spills into the
;;; next bank only when the current one cannot hold the next whole function.
;;; The cost is that `.sectionEnd farcode` no longer means anything -- the
;;; section is in several memories -- so the loader RECORDS how far it wrote
;;; (src/farload.s, _fl_top) rather than the linker predicting it.
;;;
;;; WHAT GOES FAR AND WHAT MUST NOT
;;;
;;; `farcode`, `switch` and `cfar` are the only sections that move.  Everything
;;; a far function reaches for its DATA stays in bank $00, because the small
;;; data model addresses globals and constants ABSOLUTE, through the data bank
;;; register -- so `cdata`, `idata`, `data_init_table`, `data` and `zdata` are
;;; all bank $00 by requirement, not by preference.  A `switch` table is read
;;; with long addressing and could sit anywhere; it travels with the code it
;;; belongs to.  `cfar` holds what is declared `__far const` -- the system
;;; font -- and is read with long addressing too, at the cost of a far
;;; pointer in the two places that read it.  Bank $00 is 3.8 KB of data for
;;; everything, and the window manager's tables alone want 2 KB of it.
;;;
;;; No `reset` section is used at run time: a .xex is entered through the DOS
;;; run vector at $02E0, which tools/mkxex.py points at _atari_entry.

;;; THE HOLE AT $xxD500-$xxD5FF.  No code is placed in the $D5 page of any
;;; far bank.  That is not a property of the machine -- the 65816's program
;;; counter wraps inside its bank and bank $01's $D5xx is ordinary SRAM --
;;; it is a property of the emulator the gates run on.  Altirra's 65C816
;;; gives a taken branch the 6502's page-crossing penalty cycle in native
;;; mode too, and performs it as a read of the wrong-page address FOLDED
;;; INTO BANK $00 (cpumachine.inl, kStateJccFalseRead: AT_CPU_READ_BYTE, not
;;; an ExtReadByte in bank K).  A branch that ends in $01D5xx and lands in
;;; the next page therefore puts $D5xx on the motherboard bus, which is
;;; cartridge control: with SpartaDOS X on a MaxFlash cartridge any access
;;; to $D500-$D50F selects that bank, and the DOS's next call into the
;;; cartridge runs garbage.  Real silicon has no such cycle (W65C816S data
;;; sheet, instruction table note 7); this was one build's BNE from $01D59A
;;; to $01D604, and it cost a day (docs/phase14.md).  Until the emulator is
;;; fixed the hole costs 256 bytes a bank and makes the failure impossible
;;; instead of layout-dependent.
;;;
;;; Two far memories per bank, either side of that page.  `first` is where
;;; bank $01's memory starts: its bottom for the real build, and higher for
;;; a test link -- `make test-m6` links a second image with
;;; `--memories-expression "(layout #x01c000 #x67ff)"`, which leaves bank $01 too
;;; small for the code and forces the spill, so the mechanism is exercised
;;; long before the code grows into it on its own.
(define (far-bank b first)
  (let ((name (string-append "FarCode" (number->string b 16)))
        (base (* b #x10000)))
    (list
      (list 'memory (string->symbol name)
            (list 'address (cons first (+ base #xd4ff)))
            '(section cfar farcode switch))
      (list 'memory (string->symbol (string-append name "h"))
            (list 'address (cons (+ base #xd600) (+ base #xffff)))
            '(section cfar farcode switch)))))

(define (far-banks first)
  (append (far-bank 1 first)
          (apply append (map (lambda (b) (far-bank b (* b #x10000)))
                             '(2 3 4 5 6 7 8 9 10 11 12 13 14 15)))))

;;; A layout is a far start and where the application pool ends: the
;;; runner links `(layout #x010000 #x67ff)`, which leaves $6800-$7FFF for
;;; its host-poked buffers, and GEM.COM `(layout #x010000 #x7fff)`, which
;;; has no such buffers and gives the pool the whole banked window.
(define (layout far-start pool-end)
  (append (far-banks far-start) (bank0 pool-end)))

;;; Bank $00.  The far memories go ahead of these in the final list.  The
;;; linker fills same-section memories in definition order, and nothing here
;;; shares a section with them, so only the far memories' order among
;;; themselves matters.
(define (bank0 pool-end)
  (append
  '((memory DirectPage (address (#x2000 . #x20ff))
            (section (registers ztiny)))
    ;; The stack and the data.  The linker will not mix sections that carry
    ;; bits with BSS in one memory, so bank $00 is two memories with a
    ;; boundary that has to be moved by hand when one side outgrows it --
    ;; a link that does fails, loudly.  7.9 KB is all of bank $00 that
    ;; gem4xe's own data and near code get, and everything an interrupt
    ;; handler touches has to be in it (the banked window above).
    ;;
    ;; The boundary was $3580 and both sides ran at 99%, which is how a
    ;; thirty-five byte addition to the loader turned test-m14x red
    ;; (docs/phase24.md).  Moving the fill patterns to `cfar` freed 608
    ;; bytes of near memory and the boundary shares what that bought:
    ;; each side has a few hundred bytes now rather than a few.
    ;;
    ;; It moved again on 2026-09-16, up 192 bytes to $3740, to pay for the
    ;; far window title (src/aes/wind.c) -- and on 2026-09-18, up 16 more
    ;; to $3750, for the four tree pointers that became FAR
    ;; (docs/far-trees.md): gl_mntree, gl_wtree, gl_awind, gl_newdesk, two
    ;; bytes each, which took LoRAM from 256 free to 248 and memreport
    ;; said so.  And again on 2026-09-18, up 16 more to $3760, for
    ;; WINDOW's w_owner -- one word per window, eight windows, so that
    ;; wind_get(WF_OWNER) can answer who created it.  Each of those was
    ;; memreport failing the build, which is the point of it.
    ;; THIS IS THE ONLY BOUNDARY IN
    ;; BANK $00 THAT CAN BE MOVED SAFELY, and the reason is that Near
    ;; holds code and constants: what it needs is settled at LINK time, so
    ;; taking too much fails the link and nothing else.  The other two
    ;; candidates both fail at RUN time under conditions no link can see,
    ;; and both were tried first and caught by gates -- the application
    ;; pool by test-m28 (rs_load's peak; see the note below) and the stack
    ;; by test-m32 (GD_PEXEC_STACK; see the block at the end).
    (memory LoRAM      (address (#x2100 . #x37af))
            (section stack data zdata heap))

    ;; Near code: the entry stub, farload, the C startup, the CIO
    ;; trampoline (src/sys/cio.s: emulation mode returns to bank $00, so
    ;; it cannot be far) and every library routine that is not compiled
    ;; far -- plus all constant data.  There is no overflow memory: a link
    ;; that outgrows this memory fails rather than spilling somewhere slow.
    (memory Near       (address (#x37b0 . #x3ffd))
            (section code libcode cdata idata data_init_table))

    ;; The library cstartup always emits a `reset` section -- a word pointing
    ;; at __program_start.  A .xex has no reset vector, so this is inert filler
    ;; that simply has to land somewhere the loader will not mind: the last
    ;; word of gem4xe's own 8 KB.
    (memory Vector     (address (#x3ffe . #x3fff))
            (section (reset #x3ffe))))

  ;; The application pool: where a loaded application's near part -- its
  ;; direct page, stack and data -- goes (src/sys/app.c), and where the
  ;; shell's and the selector's trees and buffers are taken from
  ;; (src/aes/shel.c, src/aes/fsel.c).  Nothing is linked into it; the
  ;; block only reserves the extent, and src/sys/apppool.s reports the
  ;; bounds the linker gave it, so the loader learns them from the map
  ;; rather than restating them.  In the banked window (see the note at
  ;; the top): fast on a Rapidus, and out of the cartridge's way.  It runs
  ;; from above the zwin memory to wherever the layout ends it.
  ;; Bank-$00 data that is not the interrupt handlers' -- the window
  ;; gadget trees, the message queue, the formatting strings, the blit
  ;; list -- in the banked window's first 2 KB (section zwin, named on
  ;; each variable), so that the stack can be a real stack.  Window 0 is
  ;; the only one a Rapidus runs at full speed both ways (src/sys/rapidus.c),
  ;; and the stack wants that more than any of these do: what moved here
  ;; is read far more than written, and a write costs one bus cycle.
  ;;
  ;; THE POOL IS NOT A PLACE TO BORROW FROM, and this is measured.  Growing
  ;; zwin by 512 bytes at the pool's expense was tried, for the two buffers
  ;; a far window title needs, and it turned test-m28 red: the desktop
  ;; alerted "DESKTOP.RSC is not on the boot disk" because rs_load could
  ;; not allocate.  What binds is not GEM.COM's pool but the CONFORMANCE
  ;; RUNNER's, which ends at $78FF and must hold an accessory and the
  ;; desktop at once, and rs_load takes the WHOLE resource file --
  ;; rsh_rssize, 6,308 bytes for the desktop's -- before rs_fixit moves
  ;; the icons far (src/aes/rsrc.c).  That transient peak is 1,536 bytes
  ;; above the resident cost, and it left 348 bytes of headroom, not 860.
  ;; The stack gave the 194 bytes instead (see the block below).
  '((memory Window     (address (#x4000 . #x47ff))
            (section zwin)))
  (list (list 'memory 'AppPool (list 'address (cons #x4800 pool-end))
              '(section apppool)))

  ;; The conformance runner's host-poked buffers, in the rest of the
  ;; window -- when there is a rest: GEM.COM has no such buffers and its
  ;; layout ends the pool at the top of the window, and then this memory
  ;; is not defined at all, so a stray `teststage` section fails its link
  ;; rather than landing somewhere.  A bss section cannot share a memory
  ;; with sections that carry bits, so it gets its own -- which also means
  ;; nothing else can land in it by accident.  What the SDX note says of a
  ;; CIO buffer in the pool holds for the runner's buffers, which the
  ;; file-layer gate hands to CIO on purpose.
  (if (< pool-end #x7fff)
      (list (list 'memory 'TestStage
                  (list 'address (cons (+ pool-end 1) #x7fff))
                  '(section teststage)))
      '())

  '(
    ;; The load-time staging buffer, inside the MEMAC A window.  It holds no
    ;; linked content -- it is bss, and tools/mkxex.py writes it a chunk at a
    ;; time from the .xex -- so placing it over a region the driver later maps
    ;; VBXE VRAM onto costs nothing.  The unpacker that empties it is the
    ;; same kind of thing, load-time only, and goes in the rest of the window
    ;; (StageCode -- its own memory, because a bss section cannot share one
    ;; with a section that carries bits).  Both stop short of the window's
    ;; last kilobyte, which is SpartaDOS X's display list and screen: a DOS
    ;; loads the chunks, and it wants its screen back afterwards.
    ;; src/farload.s sizes the payload to fit; a chunk too big for this
    ;; memory, or an unpacker too big for its 507 bytes, fails the link.
    (memory Stage      (address (#x8000 . #x9a04))
            (section farstage))
    (memory StageCode  (address (#x9a05 . #x9bff))
            (section stagecode))

    ;; 2 KB.  The shell's chain -- the runner or GEM.COM, sh_main, the
    ;; loader, app_run -- is on it under an application, and a COP is
    ;; served on top of that: gem_entry, crysbind, the window manager, the
    ;; object library, the VDI.  At 1 KB that chain ran out inside
    ;; wind_open's first redraw and the pushes went on down into zdata
    ;; (phase 14, milestone 3: vec_curv became a return address).
    ;;
    ;; AND IT CANNOT BE SHRUNK, although the gates' low-water marks make
    ;; it look as though it could.  The deepest the engine has ever gone
    ;; is 1,390 bytes of the 2,048, but 1,024 of the rest are not spare:
    ;; GEMDOS refuses a Pexec with less than GD_PEXEC_STACK left
    ;; (src/sys/gemdos.c), because the child's own calls are served
    ;; BELOW the parent's on this one stack.  1.75 KB was tried and
    ;; test-m32 answered ENSMEM to every Pexec, including one for a file
    ;; that does not exist -- which is the guard firing before it even
    ;; looks.  A low-water mark measures what has happened, not what is
    ;; reserved.
    (block stack   (size #x0800))
    (block heap    (size #x0000))   ;; nothing here calls malloc
    (base-address _DirectPageStart DirectPage 0))

  ;; The pool's block is its memory's whole extent, so apppool.s reports
  ;; the same bounds whichever layout linked.
  (list (list 'block 'apppool (list 'size (- (+ pool-end 1) #x4800))))
  ))

;;; The far code -- banks $01-$0F, filled from the bottom of bank $01.  A .xex
;;; cannot load above $FFFF; src/farload.s copies the image up as DOS reads
;;; the file.  This default is the conformance runner's layout: 10 KB of
;;; pool and 6 KB of test stage.  The runner's buffers are 6016 bytes
;;; (src/m3_vdi.c), so the stage is as small as it can be and the pool has
;;; the rest.
(define memories (layout #x010000 #x67ff))
