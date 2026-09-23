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
              bne     cart_no816

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
              bcc     cart_no816

;;; 3. A 65816, and we are running on it.  Everything after this step is
;;;    the staging, which is step two of docs/cartridge.md.
              lda     #CPU_816
              sta     CARTCPU
              lda     #4
              sta     CARTSTEP
              jsr     cart_say816
10$:          jmp     10$             ; ours, and nothing to return to

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

;;; ---------------------------------------------------------------------------
;;; The six bytes the OS reads.  Exactly six: src/cart.scm gives them a
;;; memory of their own so that code growing into them fails the link.
;;; ---------------------------------------------------------------------------
              .section carthdr, root
              .word   cart_run        ; $BFFA
              .byte   0               ; $BFFC  0 = a cartridge is here
              .byte   4               ; $BFFD  bit 2 = jump to CARTRUN
              .word   cart_init       ; $BFFE
