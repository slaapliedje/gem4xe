;;; ---------------------------------------------------------------------------
;;; crt_atari.s -- gem4xe Atari entry stub (65C816 / Rapidus)
;;;
;;; WHY THIS EXISTS
;;;
;;; Calypsi's library cstartup begins `clc; xce` to enter 65816 native mode.
;;; That is correct in general and fatal on an Atari, because the 65816 uses
;;; DIFFERENT interrupt vectors in native mode:
;;;
;;;     emulation mode   NMI $FFFA   RESET $FFFC   IRQ/BRK $FFFE
;;;     native mode      NMI $FFEA   ---           IRQ     $FFEE   BRK $FFE6
;;;
;;; The Atari OS ROM only fills the emulation-mode vectors.  So the first VBI
;;; after `xce` -- i.e. within 20 ms, always -- vectors through $FFEA, reads
;;; whatever bytes happen to live there, and derails.  Observed symptom: the
;;; program starts (a breakpoint at __program_start is hit), then the CPU ends
;;; up at $FFFE with RAM overwritten by a repeating pattern.
;;;
;;; So the very first thing that must happen, while still in emulation mode and
;;; while the Atari's own vectors are still the ones in use, is to turn the
;;; interrupt sources off.  DOS enters us here through the .xex run vector at
;;; $02E0 (tools/mkxex.py emits _atari_entry as the run address); we then fall
;;; into the library startup, which may safely do its `xce`.
;;;
;;; The sources are switched off here and, once the program is up, switched
;;; on again by src/sys/irq.c -- which first copies the OS ROM into the RAM
;;; under it and fills the native-mode vectors.  That is also what makes a
;;; return to DOS possible: _sys_exit below is the last thing gem4xe runs,
;;; after irq_remove() has given the ROM back and rapidus_restore() has
;;; written $0000-$3FFF down to the motherboard.  It puts the CPU back in
;;; emulation mode with D, S, POKMSK, IRQEN and NMIEN as this stub found
;;; them, rebuilds the E: screen that gem4xe's buffers ran over, and returns
;;; through the RTS DOS is waiting on.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern __program_start, _fl_ok
              .public _atari_entry, _sys_exit, _exit_msg, _exit_dosvec
              .public _exit_msg2, _exit_wait
              .public ae_sp, ae_pokmsk  ; for the CIO trampoline, src/sys/cio.s

#define NMIEN  0xD40E                 /* ANTIC: VBI / DLI enable */
#define IRQEN  0xD20E                 /* POKEY: IRQ enable */
#define POKMSK 0x0010                 /* OS shadow of IRQEN */
#define DOSVEC 0x000A                 /* DOS's own re-entry point */
#define ICCOM  0x0342                 /* IOCB #0: command */
#define ICBAL  0x0344                 /*          buffer address */
#define CH     0x02FC                 /* the OS: the last key, $FF for none */
#define ICBLL  0x0348                 /*          buffer length */
#define ICAX1  0x034A                 /*          aux 1: open mode */
#define ICAX2  0x034B
#define CIOV   0xE456
#define CIO_OPEN  3
#define CIO_PUTREC 9
#define CIO_CLOSE 12
#define OPEN_RW   12

              .section code, root
_atari_entry:
;;; src/farload.s clears _fl_ok when the machine cannot run gem4xe -- no 65816,
;;; or no RAM where a chunk was going, either of which means the far code
;;; never arrived (or not all of it).
;;; It has already said so on screen, so return to DOS quietly.  This must come
;;; BEFORE the interrupt sources are switched off, or DOS gets its machine back
;;; with no VBI and no SIO.
              lda     _fl_ok
              bne     ae_go
              rts
ae_go:
              tsx
              stx     ae_sp           ; DOS's stack pointer, for _sys_exit
              lda     POKMSK
              sta     ae_pokmsk       ; and what it had enabled
              sei                     ; no maskable IRQs
              lda     #0
              sta     IRQEN           ; POKEY: no timer/serial/key IRQs
              sta     POKMSK          ; keep the OS shadow consistent
              sta     NMIEN           ; ANTIC: no VBI, no DLI
              jmp     __program_start ; into the library startup (does the xce)

ae_sp:        .byte   0               ; S as DOS handed it to us: the byte
                                      ; below it is free, the ones above are
                                      ; DOS's own frames
ae_pokmsk:    .byte   0               ; POKMSK as DOS ran with it

;;; ---------------------------------------------------------------------------
;;; _sys_exit -- back to DOS.  Far-called from C; never returns to it.
;;; Everything above has already been undone (src/sys/irq.c, src/sys/rapidus.c):
;;; the OS ROM is in, its vectors are the ones in use, the interrupt sources
;;; are still off and I is still set.  What is left is the CPU's own state.
;;; ---------------------------------------------------------------------------
_sys_exit:
              sei
              rep     #0x30
              lda     ##0
              tcd                     ; D = $0000: the OS's page zero again
              sep     #0x30
              lda     #0
              pha
              plb                     ; DB = $00 (the handlers restore it, but
                                      ; nothing after this point should trust it)
              sec
              xce                     ; 6502 emulation mode; S is $01xx again
              ldx     ae_sp
              txs                     ; DOS's stack, its return address on top
              lda     ae_pokmsk
              sta     POKMSK
              sta     IRQEN           ; POKEY sources as DOS had them
              lda     #0x40
              sta     NMIEN           ; the VBI: RTCLOK and the shadows again
              cli
;;; The test runner's buffers sit over DOS's display list and screen
;;; ($BC20-$BFFF), so E: is closed and opened afresh: that rebuilds both from
;;; RAMTOP and clears the screen.  CIOV runs from the ROM, in emulation mode,
;;; which is why the ROM had to be back before this point.
              ldx     #0              ; IOCB #0
              lda     #CIO_CLOSE
              sta     ICCOM
              jsr     CIOV
              ldx     #0
              lda     #CIO_OPEN
              sta     ICCOM
              lda     #.byte0 ae_edev
              sta     ICBAL
              lda     #.byte1 ae_edev
              sta     ICBAL+1
              lda     #OPEN_RW
              sta     ICAX1
              lda     #0
              sta     ICAX2
              jsr     CIOV
;;; A last word, if the program left one: the reopen has just cleared the
;;; screen, so a message printed before this point would not be read.
;;; _exit_msg is the bank-$00 address of an EOL-terminated line, or 0.
;;; ...then a second, then -- when there is no DOS to go back to -- a
;;; prompt and a wait.  On the cartridge DOSVEC is the OS's cold start:
;;; leaving is a reboot that clears this screen before anybody could read
;;; it, and boots the cartridge into the same failure again (src/gem.c,
;;; exit_desk).  The three words are side by side, so one loop.
              ldx     #0
ae_lines:     stx     ae_i
              lda     _exit_msg,x
              sta     ICBAL
              lda     _exit_msg+1,x
              sta     ICBAL+1
              ora     ICBAL
              beq     ae_skip
              ldx     #0
              lda     #CIO_PUTREC
              sta     ICCOM
              lda     #0xff
              sta     ICBLL
              stx     ICBLL+1
              jsr     CIOV
ae_skip:      ldx     ae_i
              inx
              inx
              cpx     #6
              bne     ae_lines
              lda     _exit_wait
              ora     _exit_wait+1
              beq     ae_out
              ldx     #0xff
              stx     CH              ; the OS's last key: none
ae_key:       cpx     CH
              beq     ae_key          ; until a key arrives
              stx     CH
;;; Back to DOS.  A plain return goes to whatever loaded the program, and
;;; that is right for a DOS whose command processor is resident -- both
;;; SpartaDOSes, where the CP is waiting for its loader to return and a
;;; re-entry through DOSVEC would set it reading the disk again.  It is
;;; wrong for an Atari DOS 2 whose CP is a separate file: DUP.SYS lives at
;;; $1D00-$3306, which is memory gem4xe has been running in, so the return
;;; address points into wreckage.  There, DOSVEC -- the vector every DOS
;;; keeps pointing at its own re-entry -- reloads the CP first.
;;;
;;; _exit_dosvec says which, and src/sys/dos.c sets it from the DOS it
;;; identified.  Zero (nobody asked) keeps the return, which is what
;;; every phase before this one did.
ae_out:
              lda     _exit_dosvec
              beq     ae_rts
              jmp     (DOSVEC)
ae_rts:       rts                     ; to DOS's own loader

ae_edev:      .byte   "E:", 0x9b
_exit_msg:    .word   0               ; set from C: a line to print on the way out
_exit_msg2:   .word   0               ; ...a second, or 0, and a prompt and a
_exit_wait:   .word   0               ; wait -- the three side by side (ae_lines)
_exit_dosvec: .byte   0               ; set from C: leave through DOSVEC
ae_i:         .byte   0               ; the loop's place across CIOV
