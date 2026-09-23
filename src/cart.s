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

;;; 3. A 65816, and we are running on it.  Everything after this step is
;;;    the staging, which is step two of docs/cartridge.md.
              lda     #CPU_816
              sta     CARTCPU
              lda     #4
              sta     CARTSTEP
              jsr     cart_say816
              jsr     cart_stage
              jsr     cart_dev
10$:          jmp     10$             ; ours, and nothing to return to

;;; ---------------------------------------------------------------------------
;;; cart_dev -- the read-only D1: down into RAM, installed, and read.
;;;
;;; The read is the proof.  Installing a handler proves nothing: CIO will
;;; happily dispatch into a table of rubbish.  So the bootstrap opens a
;;; file through the ordinary OS path -- the same CIOV every program uses
;;; -- reads it a byte at a time and records how many and their sum, and
;;; the gate compares both against the file on the host.
;;; ---------------------------------------------------------------------------
cart_dev:     lda     DEV_AT
              cmp     #'C'
              beq     1$
              rts                     ; no handler on this image
1$:           lda     DEV_AT+1
              cmp     #'D'
              beq     2$
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
              jsr     DEV_ORG         ; cd_install is its first byte

              lda     #11
              sta     CARTSTEP        ; 11 = installed

;;; OPEN #1, 4, 0, "D1:HELLO.TXT"
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

;;; ---------------------------------------------------------------------------
;;; The six bytes the OS reads.  Exactly six: src/cart.scm gives them a
;;; memory of their own so that code growing into them fails the link.
;;; ---------------------------------------------------------------------------
              .section carthdr, root
              .word   cart_run        ; $BFFA
              .byte   0               ; $BFFC  0 = a cartridge is here
              .byte   4               ; $BFFD  bit 2 = jump to CARTRUN
              .word   cart_init       ; $BFFE
