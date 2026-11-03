;;; ---------------------------------------------------------------------------
;;; shstart.s -- G4DOS's shell (src/shell/shell.c): its start, and its ways
;;; back into the 6502's machine -- CIO, a routine of G4DOS's or the OS's,
;;; the loader, the cold start.  docs/g4dos-plan.md, step 4.
;;;
;;; The shell is a 65C816 program in bank $00 alone, built in the small
;;; code and data models: G4DOS's loader (src/fdos.s) loads it as any .xex,
;;; to $2000 and up, and enters it through RUNAD in emulation mode, on the
;;; OS's stack, with the OS's interrupts running.  What follows is the
;;; shape of the Calypsi board support for the Atari (Calypsi-65816-Atari,
;;; its atari-startup.s, cio.s and cpu.s), which is why it reads as it does:
;;;
;;; THE CPU NEXT, in 6502 instructions: a 65816 program on a 6502 runs as
;;; nonsense.  A Rapidus that came up as a 6502 is switched, which resets
;;; the CPU and starts the machine again from the disk -- COLDST says cold,
;;; so the boot runs its course and comes back here on the 65816.  A
;;; machine with no 65816 is told so and left: going back through DOSVEC
;;; would load this again, and again.
;;;
;;; G4DOS FIRST, OR GO BACK.  The shell's sectors are G4DOS's sector entry, and
;;; SHELL.SYS sits on a disk SpartaDOS X reads as well: run under anything
;;; but G4DOS -- no "G4" at $0706 -- it says so and RETURNS to the DOS's
;;; loader, which called it.  Not through DOSVEC: SpartaDOS X starts again
;;; that way and its banner wipes the message.
;;;
;;; THE SCREEN NEXT, which the OS put under $A000 at the cold start, while
;;; BASIC was in -- in the middle of where the shell's variables go.  G4DOS
;;; has taken BASIC out since (src/fdos.s, fd_install), so with no
;;; cartridge in, $A000-$BFFF is RAM -- tried at $BFFF, not assumed -- and
;;; the editor is opened again at the top of it, RAMTOP $C0, as a boot with
;;; OPTION held would have left it.  A cartridge there leaves no room: said.
;;;
;;; THEN NATIVE, WITH NO INTERRUPTS.  The 65816 takes its interrupts through
;;; vectors the OS never filled ($FFEA, $FFEE), so every source is switched
;;; off before `xce`.  The OS has them back for the length of each call into
;;; it -- the keyboard is an IRQ, SIO is POKEY's IRQs and the VBI's timers --
;;; and sh_call is that round trip: our D, DB and S put aside, the 6502's
;;; machine as the OS left it, the routine, and back.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel core, "*"
              .rtmodel cstartup, "g4sh"

              .extern main, _Dp, _Vfp, _DirectPageStart
              .extern __initialize_sections
              .section stack
              .section data_init_table
              .public __program_root_section, __program_start
              ;; the runtime looks for these by name; here they are one place
              .pubweak __data_initialization_needed
              .pubweak __call_initialize_global_streams
              .pubweak __call_heap_initialize
              .public sh_call, sh_exec, sh_cold
              .public sh_a, sh_x, sh_y

POKMSK:       .equ    0x0010
RAMTOP:       .equ    0x006a
COLDST:       .equ    0x0244
CH:           .equ    0x02fc
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBLL:        .equ    0x0348
ICAX1:        .equ    0x034a
ICAX2:        .equ    0x034b
NMIEN:        .equ    0xd40e
IRQEN:        .equ    0xd20e
PDVS:         .equ    0xd1ff
CIOV:         .equ    0xe456
COLDSV:       .equ    0xe477
G4_EXEC:      .equ    0x0703          ; G4DOS: load and run the file named
                                      ; at X (low) and Y (high), src/fdos.s
EOL:          .equ    0x9b

;;; The registers a call goes in with and comes back with, and what the
;;; OS was running with when it started us: S, and the IRQs it allowed.
              .section zdata, bss
sh_a:         .space  1
sh_x:         .space  1
sh_y:         .space  1
sh_p:         .space  1
sh_vec:       .space  2               ; the routine, or the name
call_sp:      .space  2               ; our S across a call

              .section code, root, noreorder
__program_root_section:
__program_start:
              lda     0x0706          ; G4DOS's, before anything -- a Rapidus
              cmp     #'G'            ; switched to its 65816 for a shell that
              bne     1$              ; then refuses is a cold start for
              lda     0x0707          ; nothing
              cmp     #'4'
              beq     2$
1$:           ldx     #.byte0 msg_g4
              ldy     #.byte1 msg_g4
              lda     #msg_g4_end-msg_g4
              jmp     say             ; and its RTS is ours, to the DOS
2$:           jsr     cpu816          ; returns only on a 65816
              jsr     screen
              tsx
              stx     os_sp
              lda     POKMSK
              sta     os_pokmsk
              sei
              lda     #0
              sta     IRQEN
              sta     POKMSK
              sta     NMIEN
              clc
              xce
              rep     #0x38
              ldx     ##.sectionEnd stack
              txs
              lda     ##_DirectPageStart
              tcd
              lda     ##0
              stz     dp:.tiny(_Vfp+2)
              pha
              plb                     ; DB = $00 ...
              plb                     ; ... the high byte discarded
__data_initialization_needed:
__call_initialize_global_streams:
__call_heap_initialize:
              lda     ##.word2 (.sectionEnd data_init_table)
              sta     dp:.tiny(_Dp+6)
              lda     ##.word0 (.sectionEnd data_init_table)
              sta     dp:.tiny(_Dp+4)
              lda     ##.word2 (.sectionStart data_init_table)
              sta     dp:.tiny(_Dp+2)
              lda     ##.word0 (.sectionStart data_init_table)
              sta     dp:.tiny(_Dp+0)
              jsr     __initialize_sections
              lda     ##0             ; argc
              jsr     main
10$:          bra     10$             ; main does not return

;;; What the OS handed us: in `code`, so loaded afresh with every run.
os_sp:        .byte   0
os_pokmsk:    .byte   0

;;; ---------------------------------------------------------------------------
;;; sh_call -- the 6502 routine at A, with sh_a, sh_x and sh_y in its
;;; registers and its own back in them after; the P it came back with is
;;; the answer (carry, bit 0, is how G4DOS and SIO say they failed).
;;; From C: SIMPLE_CALL uint16_t sh_call(uint16_t addr).
;;;
;;; The 6502's machine: D = 0, DB = 0, S on the OS's page 1 where it was
;;; when we started -- set BEFORE `xce`, so that an interrupt between the
;;; two lands there -- the IRQs the OS ran with, the VBI.  A CIO call is
;;; this with CIOV and X the IOCB times sixteen.
;;; ---------------------------------------------------------------------------
sh_call:      php                     ; I is set: the shell is never native
              phb                     ; with it clear, so no SEI here (one
              phd                     ; in native mode is tests/host/test_sei's)
              rep     #0x30
              sta     abs:sh_vec
              sep     #0x20
              lda     #0
              pha
              plb                     ; DB = $00
              rep     #0x20
              tsc
              sta     abs:call_sp
              lda     ##0
              tcd                     ; D = $0000
              sep     #0x20
              lda     abs:os_pokmsk
              sta     POKMSK
              sta     IRQEN
              lda     #1
              xba                     ; B = $01 ...
              lda     abs:os_sp       ; ... A = the OS's S
              rep     #0x20
              tcs                     ; S = $01xx while still native
              sec
              xce                     ; emulation mode: the OS's vectors
              lda     #0x40
              sta     NMIEN           ; the VBI
              cli
              lda     sh_a
              ldx     sh_x
              ldy     sh_y
              jsr     sh_jump
              php
              sei
              sta     sh_a
              stx     sh_x
              sty     sh_y
              pla
              sta     sh_p
              lda     #0
              sta     NMIEN
              sta     IRQEN
              sta     POKMSK
              clc
              xce                     ; native
              rep     #0x30
              lda     abs:call_sp
              tcs
              lda     abs:sh_p
              and     ##0x00ff
              pld
              plb
              plp
              rts

sh_jump:      jmp     (sh_vec)

;;; ---------------------------------------------------------------------------
;;; sh_exec -- the program named at A (bank $00, "Dn:NAME.EXT" and an EOL)
;;; loaded and run by G4DOS, which does not come back here: the program
;;; leaves through DOSVEC, and DOSVEC loads the shell again.
;;; sh_cold -- the machine started again, from the disk in D1:.
;;; Both put the 6502's machine back as the OS keeps it, on a fresh stack.
;;; ---------------------------------------------------------------------------
sh_exec:      rep     #0x30           ; (I is set, as everywhere native)
              sta     abs:sh_vec
              jsr     to_os
              ldx     sh_vec
              ldy     sh_vec+1
              jmp     G4_EXEC

sh_cold:      rep     #0x30
              jsr     to_os
              jmp     COLDSV

;;; Native to the OS's own: D, DB, emulation mode, S = $01FF, the IRQs and
;;; the VBI on.  Called native, returns in emulation mode: the return
;;; address is taken off the native stack before S is replaced.
to_os:        pla                     ; the return address, 16 bits
              sta     abs:call_sp
              lda     ##0
              tcd
              sep     #0x30
              pha
              plb                     ; DB = $00
              sec
              xce
              ldx     #0xff
              txs
              lda     os_pokmsk
              sta     POKMSK
              sta     IRQEN
              lda     #0x40
              sta     NMIEN
              cli
              lda     call_sp+1
              pha
              lda     call_sp
              pha
              rts

;;; ---------------------------------------------------------------------------
;;; cpu816 -- is this a 65816, and if not, can it be made one?  6502 code.
;;; NMOS or CMOS first, by decimal mode's flags ($99 + 1 is not zero to an
;;; NMOS 6502), since a 65816's `xce` is an unstable opcode on NMOS; then
;;; `clc xce`, which hands a 65816's E back in carry and is a NOP on a
;;; 65C02 -- with ANTIC's NMI off for the three instructions spent native.
;;; ---------------------------------------------------------------------------
RAPBANK:      .equ    0xd190          ; the Rapidus, with its PBI slot selected:
RAPCFG:       .equ    0xd191          ; $00 and $40 while the 6502 runs it

cpu816:       sed
              lda     #0x99
              clc
              adc     #0x01
              cld
              bne     no816
              lda     NMIEN
              pha
              lda     #0
              sta     NMIEN
              clc
              xce
              php
              sec
              xce
              plp
              pla
              sta     NMIEN
              bcc     no816
              rts

;;; A Rapidus that came up as a 6502: every PBI slot asked, the card made to
;;; answer with both bytes, and switched -- the CPU resets HERE, COLDST
;;; making it a cold start, so G4DOS boots again and finds its way back.
no816:        lda     #1
1$:           sta     PDVS
              pha
              lda     RAPBANK
              bne     2$
              lda     RAPCFG
              and     #0x40
              beq     2$
              lda     #1
              sta     COLDST
              lda     #0
              sta     RAPCFG
2$:           pla
              asl     a
              bcc     1$
              sta     PDVS            ; $00: nothing selected

;;; No 65816.  Said, and left there: through DOSVEC is this shell again.
              ldx     #.byte0 msg_816
              ldy     #.byte1 msg_816
              lda     #msg_816_end-msg_816
;;; say_stop -- A characters at Y:X, and nothing after them; say -- the
;;; same, and back.  PUT CHARACTERS, not PUT RECORD: a record ends at the
;;; first EOL, and these begin with one.
say_stop:     jsr     say
3$:           jmp     3$

say:          stx     ICBAL
              sty     ICBAL+1
              sta     ICBLL
              lda     #0
              sta     ICBLL+1
              lda     #11             ; PUT CHARACTERS
              sta     ICCOM
              ldx     #0
              jmp     CIOV

;;; ---------------------------------------------------------------------------
;;; screen -- the editor at the top of the 48 KB (above).  6502 code.
;;; ---------------------------------------------------------------------------
screen:       lda     RAMTOP
              cmp     #0xc0
              bcs     9$              ; there already
              lda     0xbfff          ; RAM?  The byte turned over and read
              eor     #0xff           ; back, then put back as it was
              sta     0xbfff
              cmp     0xbfff
              php
              eor     #0xff
              sta     0xbfff
              plp
              beq     5$
              ldx     #.byte0 msg_cart
              ldy     #.byte1 msg_cart
              lda     #msg_cart_end-msg_cart
              jmp     say_stop
5$:           lda     #0xc0
              sta     RAMTOP
              ldx     #0
              lda     #12             ; CLOSE the editor, and OPEN it again:
              sta     ICCOM           ; the OS puts its screen under RAMTOP
              jsr     CIOV
              ldx     #0
              lda     #3
              sta     ICCOM
              lda     #.byte0 ename
              sta     ICBAL
              lda     #.byte1 ename
              sta     ICBAL+1
              lda     #12
              sta     ICAX1
              lda     #0
              sta     ICAX2
              jsr     CIOV
9$:           rts

msg_816:      .byte   EOL, "G4DOS's shell needs a 65C816.", EOL
msg_816_end:
msg_g4:       .byte   EOL, "SHELL.SYS is G4DOS's shell: boot a", EOL
              .byte   "disk with G4DOS.SYS on it.", EOL
msg_g4_end:
msg_cart:     .byte   EOL, "G4DOS's shell needs $A000-$BFFF:", EOL
              .byte   "take the cartridge out.", EOL
msg_cart_end:
ename:        .byte   "E:", EOL
