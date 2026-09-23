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

SIG0:         .equ    'G'
SIG1:         .equ    '4'

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
10$:          jmp     10$             ; ours, and nothing to return to

              .section cartdata, root
cart_msg:     .byte   "gem4xe cartridge: bank 127 is running", 0x9b
cart_msg_end:

;;; ---------------------------------------------------------------------------
;;; The six bytes the OS reads.  Exactly six: src/cart.scm gives them a
;;; memory of their own so that code growing into them fails the link.
;;; ---------------------------------------------------------------------------
              .section carthdr, root
              .word   cart_run        ; $BFFA
              .byte   0               ; $BFFC  0 = a cartridge is here
              .byte   4               ; $BFFD  bit 2 = jump to CARTRUN
              .word   cart_init       ; $BFFE
