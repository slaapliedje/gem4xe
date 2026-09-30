;;; ---------------------------------------------------------------------------
;;; cio.s -- calling the Atari OS's CIO from native mode (65C816)
;;;
;;; gem4xe runs native, with its own vectors, direct page, data bank and a
;;; 16-bit stack in bank $00 -- none of which the OS ROM knows.  CIOV is
;;; 6502 code: it wants emulation mode, D = 0, a stack in page 1, and the
;;; OS's own interrupt handlers behind $FFFA/$FFFE, because DOS's disk I/O
;;; is SIO, and SIO is driven by POKEY's serial IRQs and timed by the VBI.
;;; src/sys/irq.c left the emulation-mode vectors exactly as the OS had
;;; them for this reason: in emulation mode the CPU takes its vectors from
;;; $FFFA-$FFFF again, so the OS's handlers come back the moment E is set.
;;;
;;; So one CIO call is a round trip: save gem4xe's machine, become the
;;; machine DOS was running on, JSR CIOV, come back.  In detail --
;;;
;;;   D = $0000, DB = $00     the OS's zero page and page 2/3 tables
;;;   POKMSK = IRQEN          what DOS ran with (ae_pokmsk): keyboard and
;;;                           break, not gem4xe's timer 1 -- the OS has no
;;;                           handler for it worth running
;;;   CRITIC = 1              as the OS's own critical I/O flag: the VBI's
;;;                           stage 2 stays out of the parts that are not
;;;                           SIO (SIO sets and clears CRITIC itself)
;;;   S = $01xx, xx = ae_sp   DOS's stack, at the depth DOS left it: what is
;;;                           above is DOS's frames, what is below is free.
;;;                           Set BEFORE xce, so an NMI arriving between the
;;;                           two lands on it and not on the gem4xe stack
;;;                           pointer's low byte forced into page 1
;;;   sec, xce                emulation mode; the OS's vectors
;;;   ROM in, window 3 slow   what src/sys/irq.c took: the DOS gets the OS
;;;                           ROM back at $C000-$FFFF and, on a Rapidus, the
;;;                           motherboard behind it -- SpartaDOS 3.2 keeps
;;;                           7 KB of itself under the ROM and switches it
;;;                           in for every call.  irq_cio_swap says which.
;;;                           The ROM goes in FIRST: with the ROM in, reads
;;;                           come from the motherboard whatever the MCR
;;;                           says, so the vectors at $FFFA are the OS's
;;;                           at every step (in emulation mode the SRAM
;;;                           copy and the ROM agree on them anyway)
;;;   cli, jsr CIOV           the OS's, from the ROM itself
;;;   sei, window 3 fast, ROM out, clc, xce      back, in that order
;;;
;;; and then the state the OS's handlers have kept for us while gem4xe's
;;; were off: irq_frames is caught up from RTCLOK -- the OS counted the
;;; blanks -- and a key the OS put in CH goes into gem4xe's ring the way its
;;; own handler would have put it (src/sys/irq.s, irq_kput).  The pointer
;;; sampler was silent throughout: quadrature counts during a disk read are
;;; lost, which is the same thing that happens on a real Atari when SIO
;;; runs with the keyboard IRQ off.
;;;
;;; The whole routine is bank-$00 `code`, not farcode: an interrupt taken in
;;; emulation mode returns to a 16-bit PC in bank $00, so the instruction
;;; after `xce` must be there.  It is a __simple_call from C (src/sys/cio.c
;;; fills the IOCB and reads the result): uint16_t cio_call(uint16_t iocb),
;;; the IOCB number in C, ICSTA's copy of Y in C on return.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern ae_sp, ae_pokmsk      ; src/crt_atari.s
              .extern irq_frames, irq_kput, irq_sei ; src/sys/irq.c, irq.s, sei.s
              .extern irq_cio_swap          ; src/sys/irq.c
              .public cio_call, dsk_call, dos_call, sdx_call, cio_env
              .public sdx_vec, sdx_ax, sdx_put, sdx_put_ptr, sdx_put_left

#define POKMSK 0x0010                 /* OS shadow of IRQEN */
#define RTCLOK 0x0012                 /* three bytes, high first */
#define CRITIC 0x0042
#define ATRACT 0x004D
#define CH     0x02FC                 /* the OS keyboard buffer: one key */
#define IRQEN  0xD20E
#define PORTB  0xD301
#define CIOV   0xE456
#define SIOV   0xE459                 /* the DCB in page 3, not an IOCB */
#define KERNEL 0x0703                 /* SpartaDOS: JMP to its kernel, Y = the function */
#define RAP_MCR 0xFF0080              /* src/sys/rapidus.h */
#define MCR_SLOW3 0x08
#define IRQ_SWAP_ROM  0x01            /* src/sys/irq.h */
#define IRQ_SWAP_WIN3 0x02

              .section zdata, bss
cio_sp:       .space  2               ; gem4xe's S across the call
cio_clk:      .space  2               ; RTCLOK+1..2 at entry, low byte first
cio_env:      .space  1               ; bisection knobs: 1 = leave CRITIC alone
cio_iocb:     .space  1               ; iocb * 16, for X
cio_pokmsk:   .space  1               ; gem4xe's POKMSK across the call
cio_stat:     .space  2               ; the OS's Y, zero-extended
cio_which:    .space  1               ; 0 = CIOV, 1 = SIOV (dsk_call), 2 = KERNEL (dos_call)
cio_fn:       .space  1               ; dos_call's function number, for Y
sdx_vec:      .space  2               ; sdx_call's target, a bank-$00 routine
sdx_ax:       .space  2               ; its A (low) and X (high), in and out
sdx_put_left: .space  2               ; sdx_put's room left, counted down

              .section code, root
;;; Four ways in, one round trip.  cio_call takes an IOCB number in A and
;;; ends at CIOV; dsk_call takes nothing, the DCB in page 3 being the
;;; argument, and ends at SIOV -- which is the entry a PBI hard disk is
;;; served through as well as a floppy, so one sector read reaches every
;;; drive gem4xe can see (src/sys/gemdos.c, gd_dfree); dos_call takes a
;;; SpartaDOS kernel function number in A, puts it in Y and ends at the
;;; JMP at $0703, the way the SDX User Guide (6.8, "Page Seven Kernel
;;; Values") says a program calls the kernel.  It answers with the P the
;;; kernel came back with: the carry is what a kernel call reports in.
;;; sdx_call takes nothing either: it ends at a JSR to the bank-$00
;;; address in sdx_vec, with A and X from sdx_ax, puts A and X back there
;;; and answers with P as dos_call does -- the way in to what SpartaDOS X
;;; names by a SYMBOL rather than a vector (src/sys/dos.c dos_command:
;;; jfsymbol, and XCOMLI, its command processor).  CRITIC is left alone
;;; for it: a command's run is long, and the DOS ran it with the VBI whole.
cio_call:     php
              sep     #0x20
              stz     abs:cio_which
              rep     #0x20
              bra     os_call
dsk_call:     php
              sep     #0x20
              lda     #1
              sta     abs:cio_which
              rep     #0x20
              lda     ##0             ; no IOCB to index
              bra     os_call
dos_call:     php
              sep     #0x20
              sta     abs:cio_fn
              lda     #2
              sta     abs:cio_which
              rep     #0x20
              lda     ##0
              bra     os_call
sdx_call:     php
              sep     #0x20
              lda     #3
              sta     abs:cio_which
              rep     #0x20
              lda     ##0
os_call:      jsl     irq_sei         ; not SEI: src/sys/sei.s says why
              phb
              phd
              asl     a
              asl     a
              asl     a
              asl     a
              sep     #0x20
              sta     abs:cio_iocb
              lda     #0
              pha
              plb                     ; DB = $00
              rep     #0x20
              tsc
              sta     abs:cio_sp      ; gem4xe's stack, to come back to
              lda     ##0
              tcd                     ; D = $0000
              sep     #0x20
              lda     POKMSK
              sta     abs:cio_pokmsk
              lda     abs:ae_pokmsk
              sta     POKMSK
              sta     IRQEN           ; DOS's sources: keyboard, break
              lda     abs:cio_env
              lsr     a
              bcs     cio_nocrit
              lda     abs:cio_which
              cmp     #3              ; sdx_call: see above
              beq     cio_nocrit
              lda     #1
              sta     CRITIC
cio_nocrit:   stz     ATRACT
              lda     RTCLOK+2
              sta     abs:cio_clk
              lda     RTCLOK+1
              sta     abs:cio_clk+1
              lda     #1
              xba                     ; B = $01 ...
              lda     abs:ae_sp       ; ... A = DOS's S
              rep     #0x20
              tcs                     ; S = $01xx while still native
              sec
              xce                     ; emulation mode: 8-bit everything
              lda     abs:irq_cio_swap
              beq     cio_go
              lda     PORTB           ; the ROM in, other bits as they are
              ora     #1
              sta     PORTB
              lda     abs:irq_cio_swap
              and     #IRQ_SWAP_WIN3
              beq     cio_go
              lda     long:RAP_MCR    ; and the motherboard behind it
              ora     #MCR_SLOW3
              sta     long:RAP_MCR
cio_go:       cli
              ldx     abs:cio_iocb
              lda     abs:cio_which
              beq     cio_cio
              cmp     #2
              beq     cio_dos
              cmp     #3
              beq     cio_sdx
              jsr     SIOV
              bra     cio_back
cio_cio:      jsr     CIOV
              bra     cio_back
cio_dos:      ldy     abs:cio_fn
              jsr     KERNEL
              php                     ; its P, carry and all, is the answer
              pla
              tay
              bra     cio_back
cio_sdx:      lda     abs:sdx_ax      ; A and X in ...
              ldx     abs:sdx_ax+1
              jsr     sdx_go
              sta     abs:sdx_ax      ; ... and out, with P as dos_call's
              stx     abs:sdx_ax+1
              php
              pla
              tay
cio_back:     sei
              sty     abs:cio_stat
              lda     abs:irq_cio_swap
              beq     cio_took
              and     #IRQ_SWAP_WIN3
              beq     cio_rom
              lda     long:RAP_MCR    ; the SRAM copy again ...
              and     #~MCR_SLOW3
              sta     long:RAP_MCR
cio_rom:      lda     PORTB           ; ... which the ROM going out reveals
              and     #~1
              sta     PORTB
cio_took:     clc
              xce                     ; native; M and X are 8 bits, and X
                                      ; stays so until the end
              rep     #0x20
              lda     abs:cio_sp
              tcs                     ; gem4xe's stack, straight away
              sep     #0x20
              lda     abs:cio_env
              lsr     a
              bcs     cio_keepcrit
              lda     abs:cio_which
              cmp     #3
              beq     cio_keepcrit
              stz     CRITIC
cio_keepcrit:
;;; The blanks the OS counted: RTCLOK is big-endian, so its low two bytes
;;; are picked up one at a time into a little-endian word.
              lda     RTCLOK+2
              sta     abs:cio_stat+1  ; scratch for a moment
              lda     RTCLOK+1
              xba
              lda     abs:cio_stat+1
              rep     #0x20           ; C = RTCLOK now
              sec
              sbc     abs:cio_clk
              clc
              adc     abs:irq_frames
              sta     abs:irq_frames
              sep     #0x20
              stz     abs:cio_stat+1
;;; A key the OS collected.  CH is $FF for none.
              lda     CH
              cmp     #0xff
              beq     cio_nokey
              jsl     irq_kput        ; A = the code, 8-bit A and X, DB = $00
              lda     #0xff
              sta     CH
;;; gem4xe's sources again -- BUT TIMER 1 STAYS OFF: POKEY is still as the
;;; OS's SIO left it, and irq_pokey_resync, which the C side calls next,
;;; reprograms the timer and restarts it before it arms it.  Armed here, a
;;; timer counting by SIO's settings fired again within two hundred cycles
;;; of every acknowledgement under AltirraOS (Altirra's own OS), and on a
;;; 1.79 MHz 65C816 the handler then had every cycle and the resync never
;;; ran: a black screen from the 0.9.2 cartridge (docs/phase81.md).
cio_nokey:    lda     abs:cio_pokmsk
              sta     POKMSK
              and     #0xfe           ; IRQ_TIMER1
              sta     IRQEN
              rep     #0x30
              pld
              plb
              lda     abs:cio_stat
              plp
              rtl

sdx_go:       jmp     (sdx_vec)

;;; sdx_put -- what SpartaDOS X's library calls for every byte a command
;;; prints while the console's handle is 100 (Programming Guide 4.50, 9.7
;;; and 18.9.5.2): 6502 code, the byte in A, every register preserved,
;;; ending in RTS.  The byte is stored through the long address kept in
;;; the store's own operand -- the 65816 takes a long store in emulation
;;; mode, so the buffer is far while the DOS runs in bank $00 -- and the
;;; operand is bumped; sdx_put_left is the room, and a byte past it is
;;; dropped rather than written over whatever follows the buffer.
sdx_put:      php
              pha
              lda     abs:sdx_put_left
              ora     abs:sdx_put_left+1
              beq     sdx_put_full
              pla
              pha
sdx_put_op:   .byte   0x8F            ; sta long ...
sdx_put_ptr:  .byte   0, 0, 0         ; ... here: set from C, bumped below
              inc     abs:sdx_put_ptr
              bne     sdx_put_cnt
              inc     abs:sdx_put_ptr+1
              bne     sdx_put_cnt
              inc     abs:sdx_put_ptr+2
sdx_put_cnt:  lda     abs:sdx_put_left
              bne     sdx_put_dec
              dec     abs:sdx_put_left+1
sdx_put_dec:  dec     abs:sdx_put_left
sdx_put_full: pla
              plp
              rts
