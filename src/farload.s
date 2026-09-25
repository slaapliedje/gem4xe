;;; ---------------------------------------------------------------------------
;;; farload.s -- load-time copy-up of 65816 far code into linear RAM.
;;;
;;; WHY THIS EXISTS
;;;
;;; An Atari DOS loader has no concept of 65816 banks: a .xex segment header is
;;; two 16-bit addresses, so nothing can be loaded above $FFFF.  But bank $00
;;; offers gem4xe about 12 KB of code space once the OS, DOS, the U1MB banking
;;; window and the MEMAC window are subtracted, and the VDI alone is 15 KB.
;;;
;;; So the linker places `farcode` in the banks above -- one memory per bank
;;; from $01 upwards, inside the accelerator's first megabyte (src/gem4xe.scm)
;;; -- and the far image travels in the .xex as a series of chunks aimed at a
;;; staging buffer in bank $00.  DOS calls through INITAD ($02E2) after
;;; loading a segment, and this is what it calls: it unpacks one chunk from
;;; the buffer to its real home and returns.  By the time DOS reaches the run
;;; vector the far image is assembled.
;;;
;;; THE CHUNKS ARE PACKED -- an LZ77, tools/mkxex.py has the format -- because
;;; the far image is two thirds of a double-density floppy and most of a
;;; minute of a 1050's reading, and packing makes it a third smaller.  What
;;; this costs is the unpacking, and that is cheap: a token is a few literal
;;; bytes and then a copy from output already written, which is in the banks
;;; above and is read back with the same long pointers that write it.  Both
;;; copies go a page-run at a time -- as far as the nearer of the two
;;; pointers is from the end of its page -- so the inner loop is Y-indexed
;;; and the 24-bit arithmetic happens per run, not per byte.
;;;
;;; The loader does not know or care which banks the linker chose: every
;;; chunk carries its own 24-bit destination and how many bytes it unpacks
;;; to.  What it does keep is _fl_top, the highest address it has written
;;; past, so that the far heap can start above whatever actually arrived
;;; (src/sys/farmem.c).
;;;
;;; tools/mkxex.py packs those chunks and is the other half of this file; the
;;; two share the layout through the linker symbols _fl_hdr / _fl_buf / _fl_end
;;; rather than a repeated constant.
;;;
;;; THE STAGING BUFFER LIVES AT $8000, IN THE MEMAC A WINDOW, AND SO DOES THE
;;; UNPACKER.  That region is already reserved -- no code or data may be
;;; placed there, because the driver maps VBXE VRAM over it at run time --
;;; and it is plain motherboard RAM until vbxe_init() opens the window.  So
;;; staging there costs nothing at all, and neither does the code that runs
;;; only while DOS is loading: _fl_copy and the unpacker are in `stagecode`,
;;; which src/gem4xe.scm places above the buffer, and they are gone with the
;;; buffer once the window opens.  What must outlive the load -- _fl_ok,
;;; which the entry point reads, and _fl_top, which the far heap is derived
;;; from -- is in `code`, in bank $00 proper, along with the checks and the
;;; messages, which are plain 6502 code and are wanted on a machine that
;;; may not have a MEMAC window at all.
;;;
;;; WHAT IT REFUSES TO DO
;;;
;;; Writing above bank $00 needs a 65816: on an NMOS 6502 the long store
;;; `sta $9F` is an unstable undocumented opcode, so running this on the wrong
;;; machine would corrupt memory rather than fail.  The CPU is therefore
;;; identified before the first store, and linear RAM is probed rather than
;;; assumed -- a 65816 with nothing where a chunk is going is just as fatal
;;; and much less obvious, so EVERY chunk's destination is probed before it is
;;; written, not only the first.  Either failure prints a line, marks the
;;; machine unusable and returns to DOS.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel core, "*"

              .public _fl_copy, _fl_ok, _fl_top
              .public _fl_hdr, _fl_buf, _fl_end
              .public _fl_running_bank

FL_CHUNK:     .equ    0x1a00          ; staging payload: 26 pages -- with the
                                      ; header and the unpacker after it,
                                      ; what fits the Stage memories
                                      ; (src/gem4xe.scm), which stop under
                                      ; SpartaDOS X's screen
FL_HDR:       .equ    5               ; the chunk header, see _fl_hdr

;;; CIO, for the two failure messages.  DOS is still resident and IOCB #0 is
;;; open on E: at this point, which is the whole reason the diagnostics can be
;;; a printed line rather than a wedged machine.
CH:           .equ    0x02fc          ; the OS's last key, $FF when none
ICHID:        .equ    0x0340          ; IOCB #1: the DOS's own load channel
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBLL:        .equ    0x0348
IOCB1:        .equ    0x0010          ; the offset of IOCB #1 from IOCB #0
CIOV:         .equ    0xe456
PUTREC:       .equ    0x09
CLOSE:        .equ    0x0c
EOL:          .equ    0x9b
DOSVEC:       .equ    0x000a          ; the DOS's own re-entry

NMIEN:        .equ    0xd40e

;;; The Rapidus, from the 6502 side.  Its registers are mapped only while
;;; its PBI device is SELECTED -- Altirra's rapidus.cpp does it in
;;; SelectPBIDevice(), which enables the memory layer -- so PDVS comes
;;; first, and $D190/$D191 read open bus until it does.  Measured at a DOS
;;; prompt on a booted machine (docs/phase23.md): with the Rapidus's slot
;;; selected, $D190 reads $00 (the FPGA bank register, which answers only
;;; in 6502 mode) and $D191 reads $40 (bit 6 set: the 6502); every other
;;; slot, and a machine with no Rapidus in it, reads $FF at both.
PDVS:         .equ    0xd1ff          ; PBI device select, one bit per device
RAPBANK:      .equ    0xd190          ; FPGA bank register
RAPCFG:       .equ    0xd191          ; FPGA config: bit 6 set = 6502
RAPCFG_6502:  .equ    0x40
COLDST:       .equ    0x0244          ; the OS: non-zero at RESET means cold

;;; --- staging area -----------------------------------------------------------
;;; Placed by src/gem4xe.scm at $8000.  The header and the payload are ADJACENT
;;; ON PURPOSE: that lets mkxex.py describe a whole chunk -- where it goes, how
;;; much it unpacks to, and the packed bytes themselves -- in one .xex segment.
;;;
;;; _fl_end marks the end of the payload; mkxex.py sizes its chunks from it.

              .section farstage, bss
_fl_hdr:      .space  3               ; +0  destination, 24-bit little-endian
_fl_count:    .space  2               ; +3  bytes the chunk unpacks to, 0 = idle
_fl_buf:      .space  FL_CHUNK        ; +5  the packed payload
_fl_end:

;;; The loader's one pointer lives in the OS's zero page, in the
;;; floating-point package's FR0 ($D4-$DD), which nothing touches during a
;;; binary load: the address being probed for RAM, and the bank named when
;;; there is none.  NOT in a direct page of its own: INITAD is called in
;;; emulation mode with the OS's interrupts running, and the OS's VBI and
;;; IRQ handlers address zero page through D -- a `tcd` here would send
;;; RTCLOK's increments into whatever the loader pointed D at (found the
;;; hard way in Calypsi-65816-Atari, whose copier this one grew out of).
;;; The unpacker keeps its state beside its own code, in fast RAM
;;; (ff_start below).
DP_DST:       .equ    0xd8            ; 24-bit: the address being probed

              .section code, root

;;; _fl_ok -- cleared if this machine cannot run gem4xe.  _atari_entry reads it
;;; and returns to DOS rather than starting a program whose code never arrived.
;;; It is initialised data inside `code`, so DOS loads it before any INITAD.
_fl_ok:       .byte   1
fl_checked:   .byte   0
fl_fastup:    .byte   0               ; the fast unpacker has been copied up

;;; fl_fastbank -- the bank above the far image, where the unpacker runs.
;;; Not known to this file: tools/mkxex.py writes it, in a segment of its
;;; own ahead of the first chunk, from where the image really ends.  GEM's
;;; far heap starts there later (farmem.c, from _fl_top) and takes it back.
fl_fastbank:  .byte   0

;;; _fl_top -- one past the highest far address written so far, 24-bit
;;; little-endian (the end of the last chunk: they come in address order);
;;; the far heap starts in the bank above it.  Where the far
;;; image ends is decided by the linker, but it is spread over several
;;; memories and the linker has no operator for "the end of a section that is
;;; in several memories" -- so the loader records where it actually put
;;; things, which is the more honest number anyway.  Like _fl_ok it lives in
;;; `code`, so DOS loads the zeros fresh with every run and cstartup, which
;;; only touches `data` and `zdata`, never sees it.
_fl_top:      .byte   0, 0, 0

;;; ---------------------------------------------------------------------------
;;; _fl_copy -- DOS calls this through INITAD after each chunk segment.
;;;
;;; In `stagecode`, above the staging buffer: load-time only, like the buffer
;;; (see the top of the file).  The one thing here that runs before the CPU
;;; is known is the first three instructions, and they are 6502 ones.
;;;
;;; IT DOES NOT UNPACK HERE.  Until GEM's own rapidus_speedup() runs, every
;;; window of bank $00 is on the 1.79 MHz bus, and this window always is --
;;; so an unpacker running here fetches every instruction, and reaches every
;;; zero-page pointer, at 1.79 MHz.  The byte-at-a-time one that did was
;;; 57% of loading GEM.COM off a DOS 2 floppy, eight seconds of a
;;; twenty-one second boot (docs/phase56.md).  So the first chunk copies
;;; ff_start..ff_end up into the bank above the far image -- the Rapidus's
;;; fast SRAM, free until the far heap takes it -- and every chunk is
;;; unpacked there, in native mode, with MVN doing the copying.  The code
;;; goes up to the SAME 16-bit address it was linked at, so its own jumps
;;; and addresses need nothing done to them.
;;;
;;; Native mode needs both kinds of interrupt kept out: IRQ by SEI, and
;;; ANTIC's NMI by NMIEN, because the native vectors at $FFEA/$FFEE are
;;; ones the OS never filled (src/crt_atari.s).  An emulation-mode NMI
;;; would do no better: it does not save the program bank, and would come
;;; back to bank $00.  A chunk is a few milliseconds; the VBI misses at most
;;; one frame of them, and NMIEN is put back to the OS's $40 after.
;;; ---------------------------------------------------------------------------
              .section stagecode, root
_fl_copy:
              lda     fl_checked
              bne     fl_ready
              jsr     fl_check        ; first call: identify the machine
fl_ready:
              lda     _fl_ok
              beq     fl_out          ; wrong machine -- never write far RAM
              lda     _fl_count
              ora     _fl_count+1
              bne     fl_go           ; something is staged
fl_out:       rts                     ; nothing staged (the priming call)
fl_go:

;;; Is there RAM where this chunk is going, and -- the first time -- where
;;; the unpacker is?  Probe the addresses themselves rather than trusting a
;;; documented memory map; the image may spill into a further bank, and the
;;; first bank having RAM says nothing about the next.
              lda     fl_fastup
              bne     fl_probe_dst
              lda     #.byte0 ff_start
              sta     dp:DP_DST
              lda     #.byte1 ff_start
              sta     dp:DP_DST+1
              lda     fl_fastbank
              sta     dp:DP_DST+2
              sta     fl_cpmvn+1      ; the copy's destination bank...
              sta     fl_jsl+3        ; ...and the call's
              jsr     fl_probe
fl_probe_dst:
              lda     long:_fl_hdr
              sta     dp:DP_DST
              lda     long:_fl_hdr+1
              sta     dp:DP_DST+1
              lda     long:_fl_hdr+2
              sta     dp:DP_DST+2
              jsr     fl_probe

              php
              sei
              lda     #0
              sta     NMIEN
              clc
              xce                     ; native; M and X still 8 bits
              lda     fl_fastup
              bne     fl_unpack
              rep     #0x30
              ldx     ##ff_start
              ldy     ##ff_start
              lda     ##ff_end-ff_start-1
fl_cpmvn:     .byte   0x54, 0, 0      ; mvn 0 -> fl_fastbank (patched above)
              phk
              plb                     ; MVN left the bank register on it
              sep     #0x30
              lda     #1
              sta     fl_fastup
fl_unpack:    rep     #0x30
fl_jsl:       .byte   0x22            ; jsl fl_fastbank:ff_unpack
              .word   ff_unpack
              .byte   0               ; (patched above)
              sep     #0x30
              sec
              xce                     ; emulation again
              lda     #0x40
              sta     NMIEN           ; the OS's: the VBI, no DLI
              plp
              rts

;;; fl_probe -- is DP_DST RAM?  Two patterns, each read back.
fl_probe:     ldy     #0
              lda     #0xa5
              sta     [dp:DP_DST],y
              cmp     [dp:DP_DST],y
              bne     fl_noram_far
              lda     #0x5a
              sta     [dp:DP_DST],y
              cmp     [dp:DP_DST],y
              bne     fl_noram_far
              rts
fl_noram_far: jmp     fl_noram        ; in `code`: out of a branch's reach

;;; ---------------------------------------------------------------------------
;;; ff_start..ff_end -- the unpacker, run in the bank above the far image.
;;;
;;; Entered by JSL in native mode, A, X and Y 16 bits wide, interrupts out.
;;; The bank register is pointed at this bank, so its variables below are
;;; plain absolute addresses; the packed bytes are read with long
;;; addressing out of bank $00, X counting through them.  The format is
;;; tools/mkxex.py's (unpack() there is this, in Python): a token, its
;;; literals, then unless the chunk's count has run out an offset word --
;;; zero for no match -- and a match of four bytes and more.
;;;
;;; Every copy is ONE MVN per piece: MVN moves a byte at a time upwards, so
;;; a match that overlaps what it writes -- a run, offset one -- repeats the
;;; way the format means.  A piece stops at the end of either bank, since
;;; MVN's addresses wrap within one; ff_copy works that out and goes round.
;;; ---------------------------------------------------------------------------
ff_start:
ff_dlo:       .word   0               ; where the next byte goes: offset...
ff_dbk:       .word   0               ; ...and bank
ff_slo:       .word   0               ; where a copy reads: offset...
ff_sbk:       .word   0               ; ...and bank
ff_cnt:       .word   0               ; bytes the chunk has still to write
ff_len:       .word   0               ; bytes this copy has still to write
ff_tok:       .word   0
ff_off:       .word   0
ff_n:         .word   0               ; this piece

ff_unpack:    phb
              phk
              plb
              lda     long:_fl_hdr
              sta     ff_dlo
              lda     long:_fl_hdr+2
              and     ##0xff
              sta     ff_dbk
              lda     long:_fl_count
              sta     ff_cnt
              ldx     ##0
ff_token:     lda     ff_cnt
              beq     ff_done
              lda     long:_fl_buf,x
              inx
              and     ##0xff
              sta     ff_tok
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              jsr     ff_length       ; ff_len = the literal count
              lda     ff_len
              beq     ff_match
              txa                     ; the literals are the packed bytes
              clc
              adc     ##_fl_buf
              sta     ff_slo
              stz     ff_sbk
              jsr     ff_copy
              lda     ff_slo
              sec
              sbc     ##_fl_buf
              tax
ff_match:     lda     ff_cnt
              beq     ff_done         ; a chunk may end after its literals
              lda     long:_fl_buf,x  ; the offset, or 0 for no match
              inx
              inx
              and     ##0xffff
              beq     ff_token
              sta     ff_off
              lda     ff_dlo
              sec
              sbc     ff_off
              sta     ff_slo
              lda     ff_dbk
              sbc     ##0
              sta     ff_sbk
              lda     ff_tok
              and     ##0x0f
              jsr     ff_length
              lda     ff_len
              clc
              adc     ##4             ; a match is four bytes at least
              sta     ff_len
              jsr     ff_copy
              bra     ff_token
;;; One past the chunk is the top of the far image so far: tools/mkxex.py
;;; sends the chunks in address order, and refuses to do otherwise, so the
;;; last is the highest.  Then the chunk is consumed: DOS may call INITAD
;;; again after a segment that carries none -- the run vector, for one --
;;; and a zero count is what makes that a no-op.
ff_done:      lda     ff_dlo
              sta     long:_fl_top
              sep     #0x20
              lda     ff_dbk
              sta     long:_fl_top+2
              rep     #0x20
              lda     ##0
              sta     long:_fl_count
              plb
              rtl

;;; ff_length -- ff_len from a token's nibble in A: the nibble itself, or if
;;; it is 15, that plus every byte that follows up to and including the
;;; first that is not 255.
ff_length:    sta     ff_len
              cmp     ##15
              bne     ff_len_done
ff_len_more:  lda     long:_fl_buf,x
              inx
              and     ##0xff
              pha
              clc
              adc     ff_len
              sta     ff_len
              pla
              cmp     ##255
              beq     ff_len_more
ff_len_done:  rts

;;; ff_copy -- ff_len bytes from ff_sbk:ff_slo to ff_dbk:ff_dlo, both moved
;;; on, and taken off ff_cnt.  X is kept.
ff_copy:      phx
ff_cp_more:   lda     ff_len
              beq     ff_cp_done
              sta     ff_n
              lda     ff_slo          ; no further than the source bank's end
              beq     ff_cp_s
              eor     ##0xffff
              inc     a
              cmp     ff_n
              bcs     ff_cp_s
              sta     ff_n
ff_cp_s:      lda     ff_dlo          ; ...or the destination's
              beq     ff_cp_d
              eor     ##0xffff
              inc     a
              cmp     ff_n
              bcs     ff_cp_d
              sta     ff_n
ff_cp_d:      sep     #0x20
              lda     ff_dbk
              sta     ff_mvn+1        ; MVN's operands: destination bank,
              lda     ff_sbk
              sta     ff_mvn+2        ; then source bank
              rep     #0x20
              ldx     ff_slo
              ldy     ff_dlo
              lda     ff_n
              dec     a
ff_mvn:       .byte   0x54, 0, 0
              phk
              plb                     ; MVN left the bank register on it
              lda     ff_slo
              clc
              adc     ff_n
              sta     ff_slo
              bcc     ff_cp_s2
              inc     ff_sbk
ff_cp_s2:     lda     ff_dlo
              clc
              adc     ff_n
              sta     ff_dlo
              bcc     ff_cp_d2
              inc     ff_dbk
ff_cp_d2:     lda     ff_len
              sec
              sbc     ff_n
              sta     ff_len
              lda     ff_cnt
              sec
              sbc     ff_n
              sta     ff_cnt
              bra     ff_cp_more
ff_cp_done:   plx
              rts
ff_end:

              .section code, root
;;; ---------------------------------------------------------------------------
;;; fl_check -- is this machine a 65816 with RAM where the far image goes?
;;;
;;; Run once, before the first store.  Every instruction up to the point where
;;; a 65816 is confirmed is a plain 6502 instruction.
;;; ---------------------------------------------------------------------------
fl_check:
              lda     #1
              sta     fl_checked

;;; 1. NMOS or CMOS?  Decimal-mode ADC sets N and Z from the BINARY result on
;;;    an NMOS 6502 and from the decimal result on everything later, so
;;;    $99 + $01 = $00 is reported as non-zero by a 6502 alone.  This is the
;;;    only test that is safe to run first: $FB (XCE) is an unstable
;;;    read-modify-write on NMOS, so it cannot be the one that goes first.
              sed
              lda     #0x99
              clc
              adc     #0x01
              cld
              bne     fl_no816

;;; 2. CMOS -- but a 65C02 or a 65816?  On a 65816 `clc xce` returns the old
;;;    E flag in carry; on a 65C02 $FB is a one-byte NOP and carry stays clear.
;;;    The machine is in native mode for the three instructions in between,
;;;    where the interrupt vectors move to $FFEA/$FFEE and the Atari OS has
;;;    never filled them -- so ANTIC's NMI is switched off across the window
;;;    rather than gambling on it (see src/crt_atari.s for the full story).
              lda     NMIEN
              pha
              lda     #0
              sta     NMIEN
              clc
              xce
              php                     ; carry now says what the CPU is
              sec
              xce                     ; ...back to emulation mode immediately
              plp
              pla
              sta     NMIEN
              bcc     fl_no816

;;; 3. A 65816.  The other half of the requirement -- RAM where the image is
;;;    going -- is checked chunk by chunk in _fl_copy, since the image may
;;;    reach banks this first call knows nothing about.
              rts

;;; fl_noram -- a chunk's destination is not RAM.  Reached from _fl_copy with
;;; DP_DST naming the bank, which is put into the message so the user learns
;;; WHERE the machine stops, not just that it does.
fl_noram:     lda     dp:DP_DST+2
              pha
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              jsr     fl_hex
              sta     msg_noram_bank
              pla
              and     #0x0f
              jsr     fl_hex
              sta     msg_noram_bank+1
              ldx     #.byte0 msg_noram
              ldy     #.byte1 msg_noram
              lda     #msg_noram_end-msg_noram
              bra     fl_fail

fl_hex:       cmp     #10
              bcc     fl_hex_d
              adc     #6               ; carry is set: +7, so 10 -> 'A'
fl_hex_d:     adc     #'0'
              rts

;;; ---------------------------------------------------------------------------
;;; fl_no816 -- this is not a 65816.  Before saying so, look for a Rapidus
;;; that has simply cold-booted as a 6502, which is how one ALWAYS comes up:
;;; Altirra's device does it in ColdReset() ("reset FPGA, force boot on
;;; 6502") and the card does the same.  A machine that can run gem4xe would
;;; otherwise need a person to switch it before gem4xe would load, which is
;;; a poor first screen for a program that could do it itself.
;;;
;;; What is written, in the order it is written:
;;;
;;;   PDVS         the slot, because the card's registers are mapped only
;;;                while its PBI device is selected -- so this comes
;;;                first, and it comes before the two reads as well
;;;   COLDST = 1   the switch RESETS the CPU, and the OS treats that reset
;;;                as a WARM start -- which is exactly when a DOS does not
;;;                run its start-up file.  Without this the machine comes
;;;                back to a prompt instead of loading GEM again.
;;;   RAPCFG = 0   bit 6 clear: the 65816.  The CPU resets HERE and nothing
;;;                below this runs.
;;;
;;; The slot is not assumed.  Every one of the eight is tried -- one bit
;;; each, so the mask is shifted left and the eighth shift leaves $00,
;;; which is also "nothing selected" -- and the card must answer with BOTH
;;; of the bytes measured above, so a machine with something else on the
;;; bus is left alone.  The select is put back either way, which is the PBI
;;; convention: a driver selects for the length of its own call and
;;; deselects after.  This runs only on a machine that has already failed
;;; the CPU test, so the alternative to looking at the bus here is refusing
;;; a machine that could have run.
;;;
;;; Every instruction is a plain 6502 one: that is the machine we are on.
;;; ---------------------------------------------------------------------------
fl_no816:     lda     #1              ; PBI device 1, then 2, 4, ...
fl_slot:      sta     PDVS            ; select it; the registers appear
              pha
              lda     RAPBANK
              bne     fl_nextslot         ; open bus, or not in 6502 mode
              lda     RAPCFG
              and     #RAPCFG_6502
              beq     fl_nextslot         ; a 65816 already: not our business
;;; It answers on both.  Come up cold, and switch.
              lda     #1
              sta     COLDST
              lda     #0
              sta     RAPCFG          ; ...and the CPU resets here
;;; Still running, so nothing took the write: try the next slot, and let
;;; COLDST stand.  A card that answers a probe and then ignores a switch
;;; is a machine that will refuse below anyway, and a cold RESET on it is
;;; no worse than a warm one.
fl_nextslot:      pla
              asl     a
              bcc     fl_slot
;;; Eight shifts and A is $00, which is also "nothing selected" -- the PBI
;;; convention, and what the bus was before we looked.
              sta     PDVS

              ldx     #.byte0 msg_no816
              ldy     #.byte1 msg_no816
              lda     #msg_no816_end-msg_no816
;;; fl_fail -- say why on IOCB #0, wait to be read, and give the machine
;;; back.
;;;
;;; Printing is not enough on its own.  This runs from INITAD, inside the
;;; DOS's own read loop, and the DOS goes on to read the other hundred
;;; kilobytes whatever we do -- a minute of a floppy grinding after a
;;; message nobody is still reading.  So the load is ABANDONED: the DOS's
;;; file is closed (IOCB #1, the channel every DOS 2 and SpartaDOS loads
;;; a binary on) and DOSVEC takes the machine back to its prompt.
;;;
;;; And the message is WAITED ON, because coming back is what wipes it: a
;;; DOS 2 redraws its menu over the top and a SpartaDOS prints its banner.
;;; A key -- read from the OS's own CH, so no IOCB has to be opened at a
;;; moment when the DOS owns them -- is what says it has been read.
;;; _fl_ok stays clear as well, so a DOS that somehow returns here finds
;;; the entry point refusing too.
fl_fail:      stx     ICBAL
              sty     ICBAL+1
              sta     ICBLL
              lda     #0
              sta     ICBLL+1
              sta     _fl_ok
              lda     #PUTREC
              sta     ICCOM
              ldx     #0
              jsr     CIOV
              ldx     #.byte0 msg_key
              ldy     #.byte1 msg_key
              stx     ICBAL
              sty     ICBAL+1
              lda     #msg_key_end-msg_key
              sta     ICBLL
              lda     #0
              sta     ICBLL+1
              lda     #PUTREC
              sta     ICCOM
              ldx     #0
              jsr     CIOV
              lda     #0xff
              sta     CH              ; drop whatever was already typed
fl_anykey:    lda     CH
              cmp     #0xff
              beq     fl_anykey
              lda     #0xff
              sta     CH
              lda     ICHID+IOCB1     ; $FF when the channel is not open
              cmp     #0xff
              beq     fl_gone
              lda     #CLOSE
              sta     ICCOM+IOCB1
              ldx     #IOCB1
              jsr     CIOV
fl_gone:      ldx     #0xff
              txs                     ; the DOS's own re-entry wants its stack
              jmp     (DOSVEC)

;;; _fl_running_bank -- which bank is the far code EXECUTING in?
;;;
;;; It lives in `farcode` on purpose: `phk` then reports the bank this very
;;; routine was placed in and copied to, so a build where the far image ended
;;; up somewhere else -- or never arrived -- answers differently.  Nothing
;;; else can tell us: the emulator bridge exposes a 16-bit PC and no K
;;; register, so the target has to say it itself.
              .section farcode, root
_fl_running_bank:
              phk
              sep     #0x20
              pla                     ; the pushed bank byte
              rep     #0x20
              and     ##0x00ff        ; B holds leftovers; the C ABI wants 16 bits
              rtl

;;; The messages are `cdata`, which is bank $00 RAM: the bank number in the
;;; second one is filled in by fl_noram before it is printed.
              .section cdata, rodata
;;; Two lines, and the second one is the important one: a machine that
;;; cannot run gem4xe has not been damaged by finding out.  Forty columns.
msg_no816:    .byte   "gem4xe needs a 65C816: this is a 6502.", EOL
msg_no816_end:
msg_noram:    .byte   "gem4xe: no linear RAM in bank $"
msg_noram_bank:
              .byte   "xx", EOL
msg_noram_end:
;;; The second line, and the one that matters: the machine was not
;;; damaged by being asked.  One record a line -- CIO's PUT RECORD stops
;;; at the first EOL, whatever length it was given.
msg_key:      .byte   "Nothing was changed.  Press a key.", EOL
msg_key_end:
