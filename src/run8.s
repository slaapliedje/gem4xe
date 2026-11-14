;;; ---------------------------------------------------------------------------
;;; run8.s -- a plain Atari program run after GEM, and GEM again after it,
;;; on a DOS with no shell to ask: DOS 2 and MyDOS (docs/run8-plan.md,
;;; step 2).
;;;
;;; G4DOS has a shell that reads GEM's note (src/sys/runnote.h).  DOS 2 and
;;; MyDOS have DUP.SYS, which reads nothing.  So GEM brings its own: this,
;;; under 384 bytes of 6502 code that GEM copies to $0400 -- the cassette buffer
;;; and the free bytes after it, up to BASIC's line buffer at $0580, which
;;; no DOS and no GEM uses -- and points
;;; DOSVEC at, so that GEM's own way out of the machine (JMP (DOSVEC),
;;; src/crt_atari.s) lands here instead of in DUP.SYS.
;;;
;;; THE HEADER is GEM's to fill in (src/aes/shel.c, sh_plain), at fixed
;;; offsets that tools/run8stub.py checks against this link:
;;;   +0  JMP r8_go
;;;   +3  the DOS's own DOSVEC, which GEM's pointing it here replaced
;;;   +5  the program, as CIO names it: "D2:>GAMES>X.XEX" and an EOL
;;;   +53 GEM itself, as the DOS started it: "D1:GEM.COM" and an EOL
;;;
;;; THE LOADER is G4DOS's (src/fdos.s), on the DOS's CIO: IOCB 1 opened on
;;; the file, $FF $FF, then each segment read straight to where it goes,
;;; INITAD called after every one and pointed at an RTS again, RUNAD called
;;; at the end as a subroutine.  MyDOS has a binary load of its own (XIO
;;; 39/40); DOS 2's is in DUP.SYS, gone, so one loader serves both.
;;;
;;; THE WAY BACK.  The program ends with an RTS from RUNAD, or a JMP
;;; (DOSVEC), or the user presses RESET -- after which the OS calls DOSINI
;;; and jumps through DOSVEC, and the DOS's init sets DOSVEC back to DUP.
;;; So DOSINI is hooked too: the DOS's own init first, then DOSVEC here.
;;; AND THE BOOT IS MARKED DONE.  GEM started as AUTORUN.SYS ran inside the
;;; OS's boot, which never finished: COLDST is still $FF, so any RESET was
;;; a cold start -- the disk booting again, and GEM back only because it is
;;; that disk's AUTORUN.SYS -- and BOOT? never got its disk bit, without
;;; which a warm start calls no DOSINI at all and the D: handler is gone.
;;; Both as a finished boot leaves them, COLDST 0 and BOOT? bit 0, a RESET
;;; is warm and comes here whichever way GEM was started (measured on
;;; MyDOS 4.50, phase 163).
;;; All three come to r8_back, which puts both vectors back as the DOS had
;;; them and loads GEM.  A program that will not load goes straight there.
;;; A program that writes over this page goes wherever its bytes say, as a
;;; program that writes over a DOS does.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public r8_base, r8_dos, r8_prog, r8_gem, r8_end, r8_go, r8_goend

DOSVEC:       .equ    0x000a
DOSINI:       .equ    0x000c
BOOTQ:        .equ    0x0009          ; BOOT?: bit 0, a disk boot was done
COLDST:       .equ    0x0244          ; non-zero: the OS makes a RESET cold
RAMTOP:       .equ    0x006a
BASICF:       .equ    0x03f8          ; the XL OS's: non-zero, BASIC is off
PORTB:        .equ    0xd301          ; bit 1 clear: BASIC in
CARTRUN:      .equ    0xbffa          ; a cartridge's start
RUNAD:        .equ    0x02e0
INITAD:       .equ    0x02e2
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBAH:        .equ    0x0345
ICBLL:        .equ    0x0348
ICBLH:        .equ    0x0349
ICAX1:        .equ    0x034a
ICAX2:        .equ    0x034b
CIOV:         .equ    0xe456
IOCB1:        .equ    0x10

              .section run8, root

r8_base:      jmp     r8_go
r8_dos:       .word   0               ; GEM writes these four
r8_prog:      .space  48              ; ...0 first: the cartridge (r8_cart)
r8_gem:       .space  20

;;; The program: loaded and run, and an RTS from it comes back here.  Here
;;; and not in r8_go, whose page the program may load over.
r8_run:       ldx     #.byte0 r8_prog
              ldy     #.byte1 r8_prog
              jsr     r8_load
r8_back:      ldx     #0xff
              txs
              lda     r8_ini          ; the DOS's vectors, as it had them
              sta     dp:DOSINI
              lda     r8_ini+1
              sta     dp:DOSINI+1
              lda     r8_dos
              sta     dp:DOSVEC
              lda     r8_dos+1
              sta     dp:DOSVEC+1
              lda     r8_portb        ; BASIC, and the rest of PORTB, as GEM
              sta     PORTB           ; left them: the cartridge's start put
              lda     r8_basicf       ; BASIC in, and a program may have
              sta     BASICF          ; switched anything
              ldx     #.byte0 r8_gem
              ldy     #.byte1 r8_gem
              jsr     r8_load         ; GEM leaves through DOSVEC itself
              jmp     (DOSVEC)        ; ...or would not load: the DOS

;;; RESET: the DOS's init, which points DOSVEC at DUP -- and then here.
r8_reset:     jsr     r8_dini
r8_here:      lda     #.byte0 r8_back
              sta     dp:DOSVEC
              lda     #.byte1 r8_back
              sta     dp:DOSVEC+1
              rts
r8_dini:      jmp     (r8_ini)
r8_fail:      jmp     r8_close        ; for the branches that cannot reach it

;;; r8_load -- the binary file named at Y:X loaded and run.  Returns when
;;; it does, or at once when it will not open or is not one.
r8_load:      stx     ICBAL+IOCB1
              sty     ICBAH+IOCB1
              jsr     r8_close
              lda     #4              ; to read
              sta     ICAX1+IOCB1
              lda     #0
              sta     ICAX2+IOCB1
              lda     #3              ; OPEN
              jsr     r8_cio
              bmi     r8_fail
              jsr     r8_arm
              lda     #0
              sta     RUNAD
              sta     RUNAD+1
              jsr     r8_word
              bmi     r8_fail
              lda     r8_w
              and     r8_w+1
              cmp     #0xff
              bne     r8_fail         ; not a binary file
10$:          jsr     r8_word
              bmi     r8_done         ; its end
              lda     r8_w
              and     r8_w+1
              cmp     #0xff
              beq     10$             ; a segment's own $FFFF
              lda     r8_w
              sta     r8_s
              lda     r8_w+1
              sta     r8_s+1
              jsr     r8_word
              bmi     r8_close
              ldx     #IOCB1          ; start to end inclusive, read to start
              lda     r8_s
              sta     ICBAL,x
              lda     r8_s+1
              sta     ICBAH,x
              sec
              lda     r8_w
              sbc     r8_s
              sta     ICBLL,x
              lda     r8_w+1
              sbc     r8_s+1
              sta     ICBLH,x
              bcc     r8_close
              inc     ICBLL,x
              bne     20$
              inc     ICBLH,x
20$:          lda     #7              ; GET BYTES
              jsr     r8_cio
              bmi     r8_close
              jsr     r8_init
              jsr     r8_arm
              jmp     10$

r8_done:      jsr     r8_close
              lda     RUNAD
              ora     RUNAD+1
              beq     r8_rts          ; nothing to run
r8_runad:     jmp     (RUNAD)

;;; r8_word -- two bytes of the file into r8_w.
r8_word:      ldx     #IOCB1
              lda     #.byte0 r8_w
              sta     ICBAL,x
              lda     #.byte1 r8_w
              sta     ICBAH,x
              lda     #2
              sta     ICBLL,x
              lda     #0
              sta     ICBLH,x
              lda     #7
;;; r8_cio -- CIO's command A on IOCB 1.
r8_cio:       ldx     #IOCB1
              sta     ICCOM,x
              jmp     CIOV

r8_close:     lda     #12
              bne     r8_cio

r8_init:      jmp     (INITAD)

r8_arm:       lda     #.byte0 r8_rts
              sta     INITAD
              lda     #.byte1 r8_rts
              sta     INITAD+1
r8_rts:       rts

r8_ini:       .word   0               ; the DOS's DOSINI
r8_portb:     .byte   0               ; PORTB and BASICF as GEM left them
r8_basicf:    .byte   0
r8_w:         .word   0
r8_s:         .word   0
r8_end:

;;; ---------------------------------------------------------------------------
;;; WHAT RUNS ONCE, BEFORE THE PROGRAM OR THE CARTRIDGE: $0580-$05FF, BASIC's
;;; line buffer -- which BASIC uses only once it is running, by when this has
;;; done its work -- so that what has to outlive them fits below it.
;;; ---------------------------------------------------------------------------
              .section run8go, root

r8_go:        ldx     #0xff           ; GEM's exit left the stack anywhere
              txs
              lda     dp:DOSINI       ; RESET comes back here too
              sta     r8_ini
              lda     dp:DOSINI+1
              sta     r8_ini+1
              lda     #.byte0 r8_reset
              sta     dp:DOSINI
              lda     #.byte1 r8_reset
              sta     dp:DOSINI+1
              lda     #0              ; the boot is long over: RESET is warm
              sta     COLDST
              lda     dp:BOOTQ        ; ...and calls DOSINI
              ora     #1
              sta     dp:BOOTQ
              lda     PORTB
              sta     r8_portb
              lda     BASICF
              sta     r8_basicf
              jsr     r8_here
              lda     r8_prog
              beq     r8_cart
              jmp     r8_run

;;; THE CARTRIDGE (phase 165), as DUP's B starts one: BASIC switched in --
;;; which a cartridge plugged in overrides anyway -- RAMTOP at $A0, E:
;;; opened again below it, and a jump through $BFFA.  Its DOS (BASIC's)
;;; goes through DOSVEC to r8_back, and GEM.
r8_cart:      lda     PORTB
              and     #0xfd           ; bit 1 clear: BASIC at $A000
              sta     PORTB
              lda     #0
              sta     BASICF
              lda     #0xa0
              sta     dp:RAMTOP
              ldx     #0
              lda     #12             ; CLOSE E:
              sta     ICCOM
              jsr     CIOV
              ldx     #0
              lda     #3              ; and OPEN it, under the new RAMTOP
              sta     ICCOM
              lda     #.byte0 r8_ename
              sta     ICBAL
              lda     #.byte1 r8_ename
              sta     ICBAH
              lda     #12
              sta     ICAX1
              lda     #0
              sta     ICAX2
              jsr     CIOV
              jmp     (CARTRUN)

r8_ename:     .byte   "E:", 0x9b
r8_goend:
