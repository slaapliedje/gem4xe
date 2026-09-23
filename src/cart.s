;;; ---------------------------------------------------------------------------
;;; cart.s -- gem4xe on a cartridge: the bootstrap, step one.
;;;
;;; WHAT THIS IS FOR.  The public release's own disk answers BOOT ERROR on
;;; its own: it carries no DOS by design and wants SpartaDOS X in the
;;; machine (docs/cartridge.md).  A cartridge needs none, which makes it
;;; the one-file demo somebody can put on a flash cart and look at.
;;;
;;; WHAT THIS IS, TODAY.  The smallest thing that proves the format and
;;; the boot path: a cartridge that comes up, says so, and can be read
;;; back by a gate.  The CPU switch and the staging go on top of it, and
;;; they go on top ONE AT A TIME -- this is the piece that de-risks
;;; everything after it, because a wrong .car header or a wrong mapper
;;; looks exactly like broken code.
;;;
;;; EVERY INSTRUCTION HERE IS A PLAIN 6502 ONE.  A Rapidus always cold-
;;; boots as a 6502 (src/farload.s says why and does the switch), so this
;;; runs on one whatever the machine turns out to be.
;;;
;;; THE MAPPER, and one hazard worth writing down.  An AtariMax 1 Mbit
;;; selects its bank through $D500-$D5FF: a WRITE with A7 clear selects
;;; bank A0-A6, a write with A7 set switches the cartridge off.  Real
;;; AtariMax hardware ALSO switches on a READ of that page -- the read
;;; latch -- and this tree's Altirra deliberately does not, so that
;;; SpartaDOS X's probe of $D500-$D503 leaves the bank alone.
;;;
;;; So: **never read $D5xx**.  Code that does is correct here and changes
;;; bank under itself on a real cartridge, which is the worst shape of
;;; bug there is -- it works on the machine you are testing on.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public cart_init, cart_run

;;; What a gate reads.  Page 6 is the one page of RAM the OS neither uses
;;; nor clears once it is up, which is what it has always been for.
CARTSIG:      .equ    0x0600          ; 'G','4' when the cartridge ran
CARTSTEP:     .equ    0x0602          ; how far it got, so a failure says where
CARTCPU:      .equ    0x0603          ; what it decided the machine is
CARTFLEN:     .equ    0x0604          ; 16-bit: bytes read back through D1:
CARTFSUM:     .equ    0x0606          ; 16-bit: and their sum
CARTDLEN:     .equ    0x0608          ; 16-bit: bytes of the DIRECTORY
CARTDSUM:     .equ    0x060a          ; 16-bit: and their sum
;;; ...and the listing itself, up to 64 bytes, so the gate can look at the
;;; RECORDS rather than at a checksum of them.  A sum that matches proves
;;; the bytes; it does not prove they are in DOS 2's shape, and the shape
;;; is what src/sys/dos.c parses.
CARTDTXT:     .equ    0x0680
CARTDMAX:     .equ    64
;;; ...and how far the load got, for the same reason: a machine that comes
;;; up black has to be able to say which of a dozen things did not happen.
STEP_OPEN:    .equ    16              ; D1:GEM.COM opened
STEP_SEG:     .equ    17              ; ...and segments are going in
STEP_RUN:     .equ    18              ; loaded; the run vector is next
STEP_BAD:     .equ    19              ; it is not a binary this can load

SIG0:         .equ    'G'
SIG1:         .equ    '4'

CPU_UNKNOWN:  .equ    0               ; nothing decided yet
CPU_816:      .equ    1               ; a 65816, and we are running on it
CPU_NO816:    .equ    2               ; not one, and no Rapidus to switch

;;; The machine, and the card.  Same addresses and same reasoning as
;;; src/farload.s, which does this from a DOS instead of from here.
NMIEN:        .equ    0xd40e
PDVS:         .equ    0xd1ff          ; PBI device select, one bit per device
RAPBANK:      .equ    0xd190          ; FPGA bank register
RAPCFG:       .equ    0xd191          ; FPGA config: bit 6 set = 6502
RAPCFG_6502:  .equ    0x40
COLDST:       .equ    0x0244          ; the OS: non-zero at RESET means cold

;;; The mapper.  A WRITE to $D500+n selects bank n; the ADDRESS carries the
;;; bank and the value written is ignored.  A write with A7 set switches
;;; the cartridge off instead, so the payload banks (0..126) are reached
;;; with the address alone and never stray into $D580.
CCTL:         .equ    0xd500
BOOT_BANK:    .equ    127             ; what RESET maps: the bootstrap's

;;; Where the payload goes.  Bank $01 is where gem4xe's own far code lives
;;; and test-m6 proves it is writable on this machine, so it is the honest
;;; destination for a demonstration of the transport.
DEST_BANK:    .equ    0x01
PAY_BANKS:    .equ    2               ; tools/mkcar.py --test-banks
PAGES:        .equ    32              ; 8 KB a bank

;;; THE COPIER RUNS FROM RAM, and that is the whole shape of this step.
;;; Selecting a payload bank replaces $A000-$BFFF -- which is where the
;;; code doing the selecting would be.  A loop that switched banks from
;;; the cartridge would delete itself between one instruction and the
;;; next.  So the loop is copied down to page 6 first and called there,
;;; and it puts the bootstrap's bank back before it returns, so that the
;;; `rts` lands in a window that exists again.
STUB:         .equ    0x0610          ; page 6, above the flags

;;; The read-only D1: (src/cartd.s).  It rides in the boot bank at a FIXED
;;; offset -- the page after the bootstrap, which src/cart.scm stops at
;;; $AFFF so the two cannot collide -- and runs at $0700, where a DOS
;;; would have been.  It cannot run from the cartridge for the same reason
;;; the copier cannot: reading a file switches the window it would be in.
DEV_AT:       .equ    0xb000          ; where it rides
DEV_ORG:      .equ    0x0700          ; where it runs
DEV_ROOM:     .equ    0x0800          ; how much there is room for
;;; A four-byte header in front of it: 'C', 'D', and the length.  Erased
;;; flash reads as $FF, and without this the bootstrap copied 2 KB of $FF
;;; to $0700 and CALLED it on an image that carries no handler -- which
;;; survived by luck and would not have on the next machine.
DEV_HDR:      .equ    4
;;; ...and the blob itself, as its own constant rather than DEV_AT+DEV_HDR
;;; written at the point of use.  `.byte1 DEV_AT+DEV_HDR` binds as
;;; `(.byte1 DEV_AT) + DEV_HDR` -- $B0 + 4 -- so the copy read from $B404,
;;; found erased flash, and called it.  The arithmetic is done here, once,
;;; where it is a number and not an expression.
DEV_BLOB:     .equ    0xb004

CIOV:         .equ    0xe456
IOCB1:        .equ    0x10
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBAH:        .equ    0x0345
ICBLL:        .equ    0x0348
ICBLH:        .equ    0x0349
ICAX1:        .equ    0x034a
ICAX2:        .equ    0x034b

;;; The .xex loader (cart_boot).  These are the OS's own vectors, and the
;;; whole of the Atari binary format that is not a segment header:
;;;
;;;     INITAD  called after EVERY segment, and pointed at an RTS once it
;;;             has been -- so it fires only for the segment that set it
;;;     RUNAD   jumped to when the file ends
;;;
;;; tools/mkxex.py measured that rule rather than assuming it (2026-09-18)
;;; and gem4xe's far image depends on it: every staged chunk is a segment
;;; followed by a two-byte segment writing INITAD, and a loader that fired
;;; the vector only once would unpack the first chunk and silently skip
;;; the other hundred.
RUNAD:        .equ    0x02e0
INITAD:       .equ    0x02e2
DOSVEC:       .equ    0x000a          ; where a program goes when it ends
COLDSV:       .equ    0xe477          ; the OS's cold start

;;; The loader's own variables, in page 6 above the flags.  They must
;;; outlive `jsr (INITAD)`, which runs gem4xe's chunk unpacker, and that
;;; uses zero page $D4-$E5 (src/farload.s) -- so these are not in zero
;;; page at all.  Nothing here needs indirect addressing: CIO is given
;;; the destination and does the storing.
LD_W:         .equ    0x0640          ; 16-bit: the header word just read
LD_START:     .equ    0x0642          ; 16-bit: this segment's first address
LD_LEN:       .equ    0x0644          ; 16-bit: and how many bytes it carries

;;; The unpacker's pointers, in the floating-point package's FR0/FRE/FR1.
;;; NOT a direct page of our own: this runs with the OS's interrupts
;;; going and its VBI and IRQ handlers address zero page through D, so a
;;; `tcd` here would send RTCLOK's increments into whatever we pointed D
;;; at.  src/farload.s learned that the hard way and says so at length.
DP_SRC:       .equ    0xd4            ; 16-bit: the cartridge window
DP_DST:       .equ    0xd8            ; 24-bit: where the next byte goes
DP_CNT:       .equ    0xe0            ; 8-bit:  how many banks
DP_RUN:       .equ    0xe4            ; 8-bit:  which bank we are on

              .section cartcode, root

;;; ---------------------------------------------------------------------------
;;; cart_init -- called by the OS during its own start-up, BEFORE the
;;; screen exists and before most of the OS's variables are set.  The
;;; rule for this entry is that almost nothing is safe to touch yet, so
;;; it records that it ran and returns; the work is cart_run's.
;;; ---------------------------------------------------------------------------
cart_init:    lda     #1
              sta     CARTSTEP        ; 1 = the OS called our init
              rts

;;; ---------------------------------------------------------------------------
;;; cart_run -- the OS is up, the screen is up, and this is ours.
;;;
;;; It does not return.  A cartridge that is jumped to here owns the
;;; machine: there is nothing to return TO, the OS having finished its
;;; start-up and handed over.
;;; ---------------------------------------------------------------------------
cart_run:     lda     #2
              sta     CARTSTEP        ; 2 = the OS jumped to CARTRUN
              lda     #SIG0
              sta     CARTSIG
              lda     #SIG1
              sta     CARTSIG+1
;;; Say so on the screen as well, so that a person putting this on a real
;;; cartridge sees something rather than a black frame.  E: is open on
;;; IOCB #0 by the time CARTRUN is reached, which is the one thing about
;;; the machine this entry may rely on.
              ldx     #0              ; IOCB #0
              lda     #11             ; PUT RECORD
              sta     0x0342,x
              lda     #.byte0 cart_msg
              sta     0x0344,x
              lda     #.byte1 cart_msg
              sta     0x0345,x
              lda     #cart_msg_end-cart_msg
              sta     0x0348,x
              lda     #0
              sta     0x0349,x
              jsr     0xe456          ; CIOV
              lda     #3
              sta     CARTSTEP        ; 3 = and it printed

;;; ---------------------------------------------------------------------------
;;; Which CPU is this?  Every instruction from here to the point where a
;;; 65816 is confirmed is a plain 6502 one, because that is what the
;;; machine may be.  The sequence is src/farload.s's fl_check, for its
;;; reasons -- it is the same question asked from a different place, and
;;; asking it a second way would only give it a second way to be wrong.
;;;
;;; 1. NMOS or CMOS?  Decimal ADC sets N and Z from the BINARY result on
;;;    an NMOS 6502 and from the decimal one on everything later, so
;;;    $99 + $01 = $00 reads as non-zero on a 6502 alone.  This has to go
;;;    first: $FB (XCE) is an unstable read-modify-write on NMOS, so it
;;;    cannot be the instruction that leads.
;;; ---------------------------------------------------------------------------
              sed
              lda     #0x99
              clc
              adc     #0x01
              cld
              beq     1$
              jmp     cart_no816      ; out of a branch's reach since staging
1$:

;;; 2. CMOS -- a 65C02 or a 65816?  `clc xce` returns the old E flag in
;;;    carry on a 65816; on a 65C02 $FB is a one-byte NOP and carry stays
;;;    clear.  The machine is in NATIVE MODE for three instructions, where
;;;    the interrupt vectors move to $FFEA/$FFEE and this OS has never
;;;    filled them -- so ANTIC's NMI goes off across the window rather
;;;    than being gambled on.
              lda     NMIEN
              pha
              lda     #0
              sta     NMIEN
              clc
              xce
              php                     ; carry now says what the CPU is
              sec
              xce                     ; ...back to emulation mode at once
              plp
              pla
              sta     NMIEN
              bcs     2$
              jmp     cart_no816
2$:

;;; 3. A 65816, and we are running on it.
;;;
;;; WHAT THIS CARTRIDGE IS IS DECIDED BY WHAT IS ON IT, not by a build
;;; switch, because the three images this tree makes are the three steps
;;; of docs/cartridge.md and each has to keep working:
;;;
;;;   no D1: at all      the staging demonstration (step two)
;;;   a D1:, no GEM.COM  open a file and read it back (step three)
;;;   a D1: with GEM.COM boot it (step four), and never come back
;;;
;;; So the question is asked of the image rather than answered in advance,
;;; and an image that is missing what it needs falls back to the thing it
;;; can still prove instead of hanging with a black screen.
              lda     #CPU_816
              sta     CARTCPU
              lda     #4
              sta     CARTSTEP
              jsr     cart_say816
              jsr     cart_dev        ; a read-only D1:, if this image has one
              bcc     20$
              jsr     cart_boot       ; ...and the system off it, if it has one
              jsr     cart_demo       ; no GEM.COM: read what IS there
              jmp     10$
20$:          jsr     cart_stage
10$:          jmp     10$             ; ours, and nothing to return to

;;; ---------------------------------------------------------------------------
;;; cart_dev -- the read-only D1: down into RAM and installed.  Carry set
;;; if this image carries one at all.
;;; ---------------------------------------------------------------------------
cart_dev:     lda     DEV_AT
              cmp     #'C'
              beq     1$
              clc
              rts                     ; no handler on this image
1$:           lda     DEV_AT+1
              cmp     #'D'
              beq     2$
              clc
              rts
2$:           lda     #10
              sta     CARTSTEP        ; 10 = installing D1:
;;; The handler down to $0700, a page at a time.  The length in the header
;;; is rounded up to a page, which is why only its high byte is read.
              lda     #.byte0 DEV_BLOB
              sta     dp:DP_SRC
              lda     #.byte1 DEV_BLOB
              sta     dp:DP_SRC+1
              lda     #.byte0 DEV_ORG
              sta     dp:DP_DST
              lda     #.byte1 DEV_ORG
              sta     dp:DP_DST+1
              ldx     #DEV_ROOM/256
10$:          ldy     #0
20$:          lda     (dp:DP_SRC),y
              sta     (dp:DP_DST),y
              iny
              bne     20$
              inc     dp:DP_SRC+1
              inc     dp:DP_DST+1
              dex
              bne     10$
              jsr     DEV_ORG         ; a jmp to cd_install is its first byte

              lda     #11
              sta     CARTSTEP        ; 11 = installed
;;; ...and where a program goes when it ENDS.  With no DOS the OS leaves
;;; DOSVEC pointing at its memo pad, which is a strange place for the
;;; desktop's Quit to arrive.  A cold start is the honest answer on a
;;; cartridge: the machine comes back up, finds the cartridge still in the
;;; slot, and boots the desktop again -- which is what "quit" means when
;;; the system IS the machine.
              lda     #.byte0 COLDSV
              sta     DOSVEC
              lda     #.byte1 COLDSV
              sta     DOSVEC+1
              sec
              rts

;;; ---------------------------------------------------------------------------
;;; cart_demo -- a file read back off the D1:, which is step three's proof.
;;;
;;; The read is the proof.  Installing a handler proves nothing: CIO will
;;; happily dispatch into a table of rubbish.  So the bootstrap opens a
;;; file through the ordinary OS path -- the same CIOV every program uses
;;; -- reads it a byte at a time and records how many and their sum, and
;;; the gate compares both against the file on the host.
;;;
;;; This is what an image with no system on it does INSTEAD of booting.
;;; ---------------------------------------------------------------------------
;;; OPEN #1, 4, 0, "D1:HELLO.TXT"
cart_demo:
              ldx     #IOCB1
              lda     #3
              sta     ICCOM,x
              lda     #.byte0 dev_name
              sta     ICBAL,x
              lda     #.byte1 dev_name
              sta     ICBAH,x
              lda     #4
              sta     ICAX1,x
              lda     #0
              sta     ICAX2,x
              jsr     CIOV
              bpl     25$             ; ...and out of a branch's reach again
              jmp     90$             ; no such file, and CARTFLEN stays 0
25$:
              lda     #12
              sta     CARTSTEP        ; 12 = opened
;;; ...and read it.  ICCOM 7 with a length of zero is CIO's "one
;;; character, in A", which is the shape every Atari handler is written
;;; to and so the honest way to exercise one.
30$:          ldx     #IOCB1
              lda     #7
              sta     ICCOM,x
              lda     #0
              sta     ICBLL,x
              sta     ICBLH,x
              jsr     CIOV
              cpy     #1
              bne     80$
              clc
              adc     CARTFSUM
              sta     CARTFSUM
              bcc     40$
              inc     CARTFSUM+1
40$:          inc     CARTFLEN
              bne     30$
              inc     CARTFLEN+1
              jmp     30$
80$:          ldx     #IOCB1
              lda     #12             ; CLOSE
              sta     ICCOM,x
              jsr     CIOV
              lda     #13
              sta     CARTSTEP        ; 13 = read to the end and closed

;;; ...and the DIRECTORY, which is the other half of what a D1: is for:
;;; a file the desktop can open is no use if it cannot see that the file
;;; is there.  Opened with AUX1 6 -- "the directory, as lines" -- and read
;;; the same way, so what is exercised is the same path the desktop takes.
              ldx     #IOCB1
              lda     #3
              sta     ICCOM,x
              lda     #.byte0 dev_dir
              sta     ICBAL,x
              lda     #.byte1 dev_dir
              sta     ICBAH,x
              lda     #6              ; CIO_A_DIR (src/sys/cio.h)
              sta     ICAX1,x
              lda     #0
              sta     ICAX2,x
              jsr     CIOV
              bmi     85$
              lda     #14
              sta     CARTSTEP        ; 14 = the directory opened
82$:          ldx     #IOCB1
              lda     #7
              sta     ICCOM,x
              lda     #0
              sta     ICBLL,x
              sta     ICBLH,x
              jsr     CIOV
              cpy     #1
              bne     84$
              pha
              clc
              adc     CARTDSUM
              sta     CARTDSUM
              bcc     83$
              inc     CARTDSUM+1
83$:          pla
              ldx     CARTDLEN
              cpx     #CARTDMAX
              bcs     835$
              sta     CARTDTXT,x      ; A still holds it: keep the first 64
835$:         inc     CARTDLEN
              bne     82$
              inc     CARTDLEN+1
              jmp     82$
84$:          ldx     #IOCB1
              lda     #12
              sta     ICCOM,x
              jsr     CIOV
              lda     #15
              sta     CARTSTEP        ; 15 = and the listing came back
85$:          ldx     #.byte0 msg_d1
              ldy     #.byte1 msg_d1
              lda     #msg_d1_end-msg_d1
              jmp     cart_print
90$:          rts

dev_name:     .byte   "D1:HELLO.TXT", 0x9b
dev_dir:      .byte   "D1:*.*", 0x9b

;;; ---------------------------------------------------------------------------
;;; cart_boot -- D1:GEM.COM, loaded and run.  This is the whole of step
;;; four: the thing the cartridge is FOR.
;;;
;;; WHAT THIS IS.  It is the one job of a DOS that read-only did not make
;;; go away: loading a program.  An Atari binary is a run of segments,
;;;
;;;     $FFFF                      once, at the start
;;;     <first> <last> <bytes>     repeated, `last` INCLUSIVE
;;;
;;; and two of those segments are vectors rather than code: INITAD, which
;;; the loader calls after the segment that wrote it, and RUNAD, which it
;;; jumps to at the end.
;;;
;;; THE INITAD RULE IS NOT A DETAIL HERE.  gem4xe's far image -- the code
;;; in banks $01 and up, which is most of the system -- travels as chunks
;;; aimed at a staging buffer, each followed by a two-byte segment that
;;; writes INITAD, and src/farload.s unpacks one chunk per call.  A loader
;;; that fired the vector once would unpack the first chunk, skip the
;;; other hundred, and jump into an image that is nine tenths absent.  So
;;; this does what a DOS does and tools/mkxex.py measured in 2026-09-18:
;;; call INITAD after EVERY segment, and point it at an RTS once it has.
;;;
;;; IT READS A SEGMENT WHERE THE SEGMENT GOES.  CIO is handed the
;;; destination and the length and does the storing, so the loader holds
;;; no pointer of its own and never becomes a second copy of the format.
;;; It also keeps the cost down: the handler is a byte at a time either
;;; way (CIO's own loop calls GET once per byte) but one CIOV entry per
;;; SEGMENT instead of one per byte is the difference this can make.
;;;
;;; IT RUNS FROM THE CARTRIDGE, which is only safe because the handler
;;; puts the boot bank back before every return (src/cartd.s).  Nothing
;;; here may assume that of anything else.
;;;
;;; It returns only if there is no system to boot.
;;; ---------------------------------------------------------------------------
cart_boot:    ldx     #IOCB1
              lda     #3
              sta     ICCOM,x
              lda     #.byte0 boot_name
              sta     ICBAL,x
              lda     #.byte1 boot_name
              sta     ICBAH,x
              lda     #4
              sta     ICAX1,x
              lda     #0
              sta     ICAX2,x
              jsr     CIOV
              bpl     1$
;;; No system on this cartridge -- and CLOSE IT ANYWAY.  A refused OPEN
;;; leaves this machine's CIO with the IOCB still claimed, so the next
;;; OPEN of it answers 129, "already open", rather than doing anything.
;;; That cost an afternoon's worth of confusion: the step-three image
;;; stopped reading HELLO.TXT the moment a GEM.COM it does not carry was
;;; looked for first, and the failure was two calls away from its cause.
              jsr     ld_close
              rts
1$:           lda     #STEP_OPEN
              sta     CARTSTEP
;;; SAY SO, AND KEEP SAYING SO.  The system is 165 KB and CIO reads it a
;;; byte at a time through a handler on a 1.79 MHz bus, which is about
;;; twenty-six seconds on this machine (docs/cartridge.md measures it and
;;; says what could be done about it).  Twenty-six seconds of an unchanging
;;; screen is indistinguishable from a machine that has hung, so there is
;;; a dot per segment: it costs one CIO call against a hundred thousand
;;; and it is the difference between waiting and wondering.
              ldx     #.byte0 msg_load
              ldy     #.byte1 msg_load
              lda     #msg_load_end-msg_load
              jsr     cart_print
;;; The vectors, before a byte is read.  INITAD has to be safe to call
;;; from the very first segment, which is one no file has written it in.
              jsr     ld_arm
              lda     #0
              sta     RUNAD
              sta     RUNAD+1
;;; $FFFF.  A file that does not start with it is not an Atari binary,
;;; and loading it would scatter its bytes over the machine at addresses
;;; it never meant.
              jsr     ld_word
              bpl     5$
2$:           jmp     ld_bad          ; ...out of a branch's reach from here
5$:           lda     LD_W
              and     LD_W+1
              cmp     #0xff
              bne     2$

10$:          jsr     ld_word
              bmi     ld_done         ; the end of the file, which is normal
              lda     LD_W
              and     LD_W+1
              cmp     #0xff
              beq     10$             ; another $FFFF: legal between segments
              lda     LD_W
              sta     LD_START
              lda     LD_W+1
              sta     LD_START+1
              jsr     ld_word
              bmi     ld_bad
;;; last - first + 1, and a `last` below `first` is a corrupt header
;;; rather than a segment of 65,536 bytes.
              sec
              lda     LD_W
              sbc     LD_START
              sta     LD_LEN
              lda     LD_W+1
              sbc     LD_START+1
              sta     LD_LEN+1
              bcc     ld_bad
              inc     LD_LEN
              bne     20$
              inc     LD_LEN+1
20$:          ldx     #IOCB1
              lda     LD_START
              sta     ICBAL,x
              lda     LD_START+1
              sta     ICBAH,x
              lda     LD_LEN
              sta     ICBLL,x
              lda     LD_LEN+1
              sta     ICBLH,x
              lda     #7
              sta     ICCOM,x
              jsr     CIOV
              bmi     ld_bad          ; short: the file stops mid-segment
              lda     #STEP_SEG
              sta     CARTSTEP
              jsr     ld_dot
;;; ...and the vector, in the order a DOS does it: call it, THEN disarm.
;;; A segment that has just written INITAD is the one whose call means
;;; anything, and every other segment gets the RTS this left behind.
              jsr     ld_init
              jsr     ld_arm
              jmp     10$

ld_done:      jsr     ld_close
              lda     RUNAD
              ora     RUNAD+1
              beq     ld_bad          ; loaded, and nowhere to start
              lda     #STEP_RUN
              sta     CARTSTEP
              jmp     (RUNAD)         ; ...and gem4xe has the machine

ld_bad:       jsr     ld_close
              lda     #STEP_BAD
              sta     CARTSTEP
              ldx     #.byte0 msg_bad
              ldy     #.byte1 msg_bad
              lda     #msg_bad_end-msg_bad
              jmp     cart_print

;;; ld_word -- the next two bytes of the file into LD_W.  Y is CIO's
;;; status, so the caller's `bmi` is "the file ended here".
ld_word:      ldx     #IOCB1
              lda     #.byte0 LD_W
              sta     ICBAL,x
              lda     #.byte1 LD_W
              sta     ICBAH,x
              lda     #2
              sta     ICBLL,x
              lda     #0
              sta     ICBLH,x
              lda     #7
              sta     ICCOM,x
              jmp     CIOV

ld_close:     ldx     #IOCB1
              lda     #12
              sta     ICCOM,x
              jmp     CIOV

;;; ld_dot -- one character on the screen, for one segment.  A length of
;;; zero is CIO's "the byte is in A" for PUT, the mirror of the GET this
;;; file already leans on, and it leaves IOCB #1's open file alone.
ld_dot:       lda     #11
              sta     ICCOM
              lda     #0
              sta     ICBLL
              sta     ICBLH
              lda     #'.'
              ldx     #0              ; IOCB #0, which is E:
              jmp     CIOV

;;; ld_arm -- point INITAD at an RTS, which is what a DOS leaves behind
;;; after it has called the vector.
ld_arm:       lda     #.byte0 ld_rts
              sta     INITAD
              lda     #.byte1 ld_rts
              sta     INITAD+1
              rts

ld_init:      jmp     (INITAD)
ld_rts:       rts

boot_name:    .byte   "D1:GEM.COM", 0x9b

;;; ---------------------------------------------------------------------------
;;; cart_stage -- the payload out of the cartridge and into far memory.
;;;
;;; PROBE BEFORE WRITING.  A 65816 with nothing where the payload is going
;;; is just as fatal as a 6502 and much less obvious, so the destination
;;; is written and read back before a byte of payload goes near it --
;;; src/farload.s's rule, and the two values are its two values.
;;; ---------------------------------------------------------------------------
cart_stage:   lda     #7
              sta     CARTSTEP        ; 7 = staging

              lda     #0
              sta     dp:DP_DST
              sta     dp:DP_DST+1
              lda     #DEST_BANK
              sta     dp:DP_DST+2
              ldy     #0
              lda     #0xa5
              sta     [dp:DP_DST],y
              cmp     [dp:DP_DST],y
              bne     cart_noram
              lda     #0x5a
              sta     [dp:DP_DST],y
              cmp     [dp:DP_DST],y
              bne     cart_noram

;;; The loop, down to page 6.  Copied backwards so one index does both
;;; ends; the stub is well under 256 bytes and the link fails if it grows
;;; past the page, because cart_stub_end-cart_stub would not fit X.
              ldx     #cart_stub_end-cart_stub
20$:          lda     cart_stub-1,x
              sta     STUB-1,x
              dex
              bne     20$

              lda     #PAY_BANKS
              sta     dp:DP_CNT
              lda     #0
              sta     dp:DP_RUN
              sta     dp:DP_DST
              sta     dp:DP_DST+1
              lda     #DEST_BANK
              sta     dp:DP_DST+2
              jsr     STUB            ; ...and the window is ours again

              lda     #8
              sta     CARTSTEP        ; 8 = staged
              ldx     #.byte0 msg_staged
              ldy     #.byte1 msg_staged
              lda     #msg_staged_end-msg_staged
              jmp     cart_print

cart_noram:   lda     #9
              sta     CARTSTEP        ; 9 = nowhere to put it
              ldx     #.byte0 msg_noram
              ldy     #.byte1 msg_noram
              lda     #msg_noram_end-msg_noram
              jmp     cart_print

;;; ---------------------------------------------------------------------------
;;; cart_stub -- POSITION INDEPENDENT, and it has to be: it is assembled
;;; here and runs at $0610.  Every reference is a zero-page one, a
;;; hardware address, or a relative branch; there is no `jsr` and no `jmp`
;;; to a label of its own.  Adding one would assemble cleanly and jump
;;; into the cartridge window from RAM.
;;;
;;; THE VALUE WRITTEN TO $D500,X IS IGNORED -- the address selects the
;;; bank -- and this NEVER READS that page.  Real AtariMax hardware
;;; switches bank on a read of $D5xx and this tree's Altirra deliberately
;;; does not, so a read here would be correct on the machine it was
;;; tested on and change bank under itself on a real cartridge.
;;; ---------------------------------------------------------------------------
cart_stub:    ldx     dp:DP_RUN
30$:          sta     CCTL,x          ; select payload bank X
              lda     #0
              sta     dp:DP_SRC
              lda     #0xa0
              sta     dp:DP_SRC+1     ; the window, $A000
              ldx     #PAGES
40$:          ldy     #0
50$:          lda     (dp:DP_SRC),y
              sta     [dp:DP_DST],y
              iny
              bne     50$
              inc     dp:DP_SRC+1
              inc     dp:DP_DST+1
              bne     60$
              inc     dp:DP_DST+2
60$:          dex
              bne     40$
              inc     dp:DP_RUN
              ldx     dp:DP_RUN
              cpx     dp:DP_CNT
              bcc     30$
              ldx     #BOOT_BANK
              sta     CCTL,x          ; ...before the rts needs it back
              rts
cart_stub_end:

;;; ---------------------------------------------------------------------------
;;; cart_no816 -- not a 65816.  Before saying so, look for a Rapidus that
;;; has simply cold-booted as a 6502, which is how one ALWAYS comes up.
;;;
;;; THE CARTRIDGE MAKES THIS EASIER THAN A DISK DOES.  farload does the
;;; same thing from INITAD and has to force a cold start so that the DOS
;;; runs its start-up file again; here the cartridge is still in the slot
;;; after the reset and the OS calls us again by itself.  COLDST is still
;;; set, for the same reason it is there: the switch resets the CPU and
;;; the OS would otherwise treat that as a warm start.
;;;
;;; AND IT CANNOT LOOP.  Switching resets the CPU and nothing else: the
;;; card keeps its mode across it (Altirra rapidus.cpp, SwitchCPU ->
;;; ResetCPU, which does not touch mFPGAConfigReg), so the second pass
;;; finds a 65816 and stops.  A card that answers the probe and ignores
;;; the write falls through to the next slot and then to the message.
;;;
;;; The slot is not assumed.  All eight are tried -- one bit each, and
;;; the eighth shift leaves $00, which is also "nothing selected" -- and
;;; the card must answer with BOTH bytes, so a machine with something
;;; else on the bus is left alone.
;;; ---------------------------------------------------------------------------
cart_no816:   lda     #5
              sta     CARTSTEP        ; 5 = looking for a Rapidus
              lda     #1              ; PBI device 1, then 2, 4, ...
20$:          sta     PDVS            ; select it; the registers appear
              pha
              lda     RAPBANK
              bne     30$             ; open bus, or not in 6502 mode
              lda     RAPCFG
              and     #RAPCFG_6502
              beq     30$             ; a 65816 already: not our business
;;; It answers on both.  Come up cold, and switch.
              lda     #1
              sta     COLDST
              lda     #0
              sta     RAPCFG          ; ...and the CPU resets HERE
;;; Still running, so nothing took the write: try the next slot.
30$:          pla
              asl     a
              bcc     20$
              sta     PDVS            ; $00: nothing selected, as we found it

              lda     #CPU_NO816
              sta     CARTCPU
              lda     #6
              sta     CARTSTEP        ; 6 = and there was no Rapidus
              ldx     #.byte0 msg_no816
              ldy     #.byte1 msg_no816
              lda     #msg_no816_end-msg_no816
              jsr     cart_print
40$:          jmp     40$

cart_say816:  ldx     #.byte0 msg_816
              ldy     #.byte1 msg_816
              lda     #msg_816_end-msg_816
;;; fall through

;;; ---------------------------------------------------------------------------
;;; cart_print -- X:Y the text, A its length, on IOCB #0.
;;; ---------------------------------------------------------------------------
cart_print:   pha
              lda     #11             ; PUT RECORD
              sta     0x0342
              stx     0x0344
              sty     0x0345
              pla
              sta     0x0348
              lda     #0
              sta     0x0349
              ldx     #0              ; IOCB #0
              jmp     0xe456          ; CIOV, and its rts is ours

              .section cartdata, root
cart_msg:     .byte   "gem4xe cartridge: bank 127 is running", 0x9b
cart_msg_end:
msg_816:      .byte   "65816 mode: ready to stage", 0x9b
msg_816_end:
msg_no816:    .byte   "this machine has no 65C816; gem4xe needs one", 0x9b
msg_no816_end:
msg_staged:   .byte   "staged 2 banks to $010000", 0x9b
msg_staged_end:
msg_noram:    .byte   "no RAM at $010000; gem4xe needs linear memory", 0x9b
msg_noram_end:
msg_d1:       .byte   "D1: is up; read HELLO.TXT from the cartridge", 0x9b
msg_d1_end:
msg_bad:      .byte   "D1:GEM.COM is not a program this can load", 0x9b
msg_bad_end:
msg_load:     .byte   "loading gem4xe off the cartridge", 0x9b
msg_load_end:

;;; ---------------------------------------------------------------------------
;;; The six bytes the OS reads.  Exactly six: src/cart.scm gives them a
;;; memory of their own so that code growing into them fails the link.
;;; ---------------------------------------------------------------------------
              .section carthdr, root
              .word   cart_run        ; $BFFA
              .byte   0               ; $BFFC  0 = a cartridge is here
              .byte   4               ; $BFFD  bit 2 = jump to CARTRUN
              .word   cart_init       ; $BFFE
