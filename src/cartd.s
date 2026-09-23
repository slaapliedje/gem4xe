;;; ---------------------------------------------------------------------------
;;; cartd.s -- D1:, read-only, out of the cartridge.
;;;
;;; WHY THIS AND NOT A DOS.  gem4xe reaches every file through CIO, so a
;;; cartridge carrying only gem4xe would boot a machine with no D1: and
;;; nothing to load DESKTOP.PRG from.  But the demo is READ-ONLY, and most
;;; of what a DOS is is the write side: the free-sector bitmap, the
;;; allocation, the VTOC, the business of changing a disk without
;;; corrupting it.  None of that has to exist.
;;;
;;; What gem4xe actually asks a D1: for is three things: open a file by
;;; name and read it, a directory as DOS 2's 17-character text records,
;;; and which drives there are.  That is this file, and gem4xe does not
;;; change: it sees a device in HATABS that answers CIO the way a DOS 2
;;; does and never learns where the bytes came from.
;;;
;;; WHAT IT REFUSES.  PUT and SPECIAL answer with an error rather than
;;; pretending -- a write that silently did nothing would leave a program
;;; believing it had saved.
;;;
;;; IT RUNS IN RAM.  Reading a file means switching its payload bank into
;;; $A000-$BFFF, so code in the window would delete itself (src/cart.s's
;;; copier has the same problem).  It is linked at $0700, where a DOS
;;; would have been, and carried in the cartridge as bytes.
;;;
;;; AND IT NEVER READS $D5xx.  Real AtariMax hardware switches bank on a
;;; read of that page and this tree's Altirra deliberately does not, so a
;;; read would work on the machine it was tested on and change bank under
;;; itself on a real cartridge.  The bank is selected by WRITING to
;;; $D500+n, where the ADDRESS carries the bank and the value is ignored.
;;;
;;; THE BOOT BANK GOES BACK after every call, because the caller may be
;;; running from it -- src/cart.s is.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public cd_install, cd_dir, cd_dirlen, cd_end, cd_drvbyt

CCTL:         .equ    0xd500
BOOT_BANK:    .equ    127
WINDOW_HI:    .equ    0xa0            ; the window's high byte

HATABS:       .equ    0x031a
ICBAL:        .equ    0x0344
ICBAH:        .equ    0x0345
MEMLO:        .equ    0x02e7          ; the OS: the first byte nobody owns

ST_OK:        .equ    0x01
ST_EOF:       .equ    0x88
ST_NOTFOUND:  .equ    0xaa
ST_READONLY:  .equ    0xa7
ST_BADCMD:    .equ    0x92

EOL:          .equ    0x9b

;;; A directory entry as tools/mkcar.py writes it.  SIXTEEN BYTES, so the
;;; index is four shifts rather than a multiply:
;;;
;;;   0   name, eight characters, space padded
;;;   8   extension, three
;;;  11   the bank it starts in
;;;  12   the page within that bank ($A000 + page*256) -- which is why the
;;;       packer aligns every file to a page: it buys a one-byte field and
;;;       costs at most 255 bytes a file
;;;  13   the length, three bytes, low first
ENT_BANK:     .equ    11
ENT_PAGE:     .equ    12
ENT_LEN:      .equ    13
MAX_FILES:    .equ    24

;;; Zero page: the FR0/FRE/FR1 window src/farload.s uses, for its reason --
;;; this runs with the OS's interrupts going and its handlers address zero
;;; page through D, so there is no direct page of our own.
ZP_SRC:       .equ    0xd4            ; 16-bit
ZP_ENT:       .equ    0xd6            ; 16-bit: the entry being compared
ZP_IDX:       .equ    0xd8            ; 8-bit:  which entry
ZP_SLOT:      .equ    0xd9            ; 8-bit:  the IOCB, 0..7
ZP_NUM:       .equ    0xda            ; 16-bit: scratch for the sector count

;;; ---------------------------------------------------------------------------
;;; $0700, IN A DOS 2'S SHAPE -- sixteen bytes before a line of code.
;;;
;;; $070A is DRVBYT, the bitmap of drives a DOS 2 will talk to, and
;;; src/sys/gemdos.c's Drvmap RETURNS IT.  On a machine with a DOS that
;;; byte has an owner; on this one it would have been whatever instruction
;;; happened to be linked there -- cd_install's third branch offset, as it
;;; turned out -- and the desktop would have drawn an icon for every bit
;;; that byte happened to have set.  So the handler owns it, and says ONE
;;; DRIVE, which is the truth: the cartridge is D1: and there is nothing
;;; else on this machine.
;;;
;;; Entry is a JMP rather than the first instruction, so that the head can
;;; grow without src/cart.s having to know: the bootstrap calls $0700.
;;; And $4C is not 'S', which is what src/sys/dos.c reads this byte for
;;; (dos_ident: a SpartaDOS is the one thing it has to tell apart).
;;;
;;; The rest is zero and deliberately not modelled.  A DOS 2's other
;;; variables here are its own file manager's -- buffer counts, sector
;;; numbers, its error byte -- and nothing outside a DOS 2 reads them.
;;; Inventing values would be inventing a DOS.
;;;
;;; IT IS AT THE TOP OF `devcode` AND NOT IN A SECTION OF ITS OWN.  A
;;; section was the first try and the linker placed it LAST, at $0BA4:
;;; the order sections are named in a memory is not the order fragments
;;; are laid into it (src/cartd.scm says so now).  One section is one
;;; fragment, so being first in the source of the section that starts at
;;; $0700 is what actually puts it there -- and tools/mkcar.py checks the
;;; address rather than trusting either story.
;;; ---------------------------------------------------------------------------
DEV_TOP:      .equ    0x0f00          ; $0700 + the 2 KB the bootstrap copies

              .section devcode, root

cd_entry:     jmp     cd_install      ; $0700
              .space  7               ; $0703-$0709: a DOS 2's, and not ours
cd_drvbyt:    .byte   1               ; $070A  DRVBYT: D1:, and nothing else
              .space  5               ; $070B-$070F

;;; ---------------------------------------------------------------------------
;;; (cd_install proper -- put D: in HATABS.)
;;;
;;; The OS installs E:, S:, K:, P: and C:; D: is a DOS's to add and there
;;; is no DOS here.  The slot is still SEARCHED for rather than assumed:
;;; a machine that did have one would otherwise get two D: entries, and
;;; CIO takes the first it finds.
;;; ---------------------------------------------------------------------------
cd_install:   ldx     #0
10$:          lda     HATABS,x
              beq     20$             ; a free slot
              cmp     #'D'
              beq     20$             ; one already: replace it
              inx
              inx
              inx
              cpx     #33
              bcc     10$
              rts                     ; no room, and nothing to be done
20$:          lda     #'D'
              sta     HATABS,x
              lda     #.byte0 cd_table
              sta     HATABS+1,x
              lda     #.byte1 cd_table
              sta     HATABS+2,x
;;; Every IOCB starts closed.  Page 6 and this bss are not cleared by the
;;; OS, so it cannot be left to what happened to be there.
              ldx     #7
              lda     #0
30$:          sta     cd_mode,x
              dex
              bpl     30$
;;; ...and MEMLO, which is what a DOS moves and the OS leaves at $0700.
;;; DEV_TOP rather than the handler's own end: the bootstrap copies a
;;; fixed 2 KB down, so that is the memory this device has taken whether
;;; the handler fills it or not, and a handler that grows does not have
;;; to remember to move a second number.
              lda     #.byte0 DEV_TOP
              sta     MEMLO
              lda     #.byte1 DEV_TOP
              sta     MEMLO+1
              rts

;;; ---------------------------------------------------------------------------
;;; cd_bank_in / cd_bank_out -- the window, and the rule about it.
;;; ---------------------------------------------------------------------------
cd_bank_in:   ldx     ZP_SLOT
              lda     cd_bank,x
              tax                     ; there is no ldx abs,x on a 6502
              sta     CCTL,x          ; the ADDRESS selects; A is ignored
              rts

cd_bank_out:  ldx     #BOOT_BANK
              sta     CCTL,x
              rts

;;; ---------------------------------------------------------------------------
;;; cd_slot -- X is CIO's IOCB offset ($00, $10 ... $70); ZP_SLOT becomes
;;; 0..7, which is what every per-IOCB table is indexed by.
;;; ---------------------------------------------------------------------------
cd_slot:      txa
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              sta     ZP_SLOT
              rts

;;; ---------------------------------------------------------------------------
;;; cd_entptr -- ZP_ENT = cd_dir + ZP_IDX*16.
;;; ---------------------------------------------------------------------------
cd_entptr:    lda     ZP_IDX
              asl     a
              asl     a
              asl     a
              asl     a
              clc
              adc     #.byte0 cd_dir
              sta     ZP_ENT
              lda     #.byte1 cd_dir
              adc     #0
              sta     ZP_ENT+1
;;; the high bit of idx*16 that the shifts dropped
              lda     ZP_IDX
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              clc
              adc     ZP_ENT+1
              sta     ZP_ENT+1
              rts

;;; ---------------------------------------------------------------------------
;;; cd_norm -- the spec at (ZP_SRC), from offset Y, into cd_want as the
;;; ELEVEN space-padded characters an entry carries.
;;;
;;; This is what makes "D1:GEM.COM" match "GEM     COM": the comparison is
;;; done in the entry's shape, so the dot and the absent padding are dealt
;;; with once, here, instead of in the compare loop.
;;; ---------------------------------------------------------------------------
cd_norm:      sty     ZP_IDX          ; borrow it: where the name starts
              ldx     #10
              lda     #' '
10$:          sta     cd_want,x
              dex
              bpl     10$
              ldy     ZP_IDX
              ldx     #0
20$:          lda     (ZP_SRC),y
              beq     90$
              cmp     #EOL
              beq     90$
              cmp     #'.'
              beq     30$
              cpx     #8
              bcs     25$             ; longer than eight: ignore the rest
              sta     cd_want,x
              inx
25$:          iny
              bne     20$
30$:          iny                     ; past the dot
              ldx     #8
40$:          lda     (ZP_SRC),y
              beq     90$
              cmp     #EOL
              beq     90$
              cpx     #11
              bcs     45$
              sta     cd_want,x
              inx
45$:          iny
              bne     40$
90$:          rts

;;; ---------------------------------------------------------------------------
;;; cd_cmp -- cd_want against the entry at ZP_ENT.  Carry set if equal.
;;; ---------------------------------------------------------------------------
cd_cmp:       ldy     #10
10$:          lda     (ZP_ENT),y
              cmp     cd_want,y
              bne     90$
              dey
              bpl     10$
              sec
              rts
90$:          clc
              rts

;;; ---------------------------------------------------------------------------
;;; cd_open -- "Dn:NAME.EXT" to read, or "Dn:*.*" for the directory.
;;;
;;; The unit digit is ignored on purpose: there is one device here, and a
;;; program asking for D2: has asked for a drive that does not exist.
;;; Giving it this one is friendlier than a refusal on a machine whose
;;; whole file system is a cartridge.
;;; ---------------------------------------------------------------------------
cd_open:      jsr     cd_slot
              lda     ICBAL,x
              sta     ZP_SRC
              lda     ICBAH,x
              sta     ZP_SRC+1
;;; past "D", an optional unit digit, and ":"
              ldy     #1
              lda     (ZP_SRC),y
              cmp     #':'
              beq     10$
              iny
10$:          iny
              sty     cd_nameat
;;; a wildcard anywhere in the name means the directory
              ldy     cd_nameat
20$:          lda     (ZP_SRC),y
              beq     30$
              cmp     #EOL
              beq     30$
              cmp     #'*'
              beq     cd_opendir
              cmp     #'?'
              beq     cd_opendir
              iny
              bne     20$
30$:          jmp     cd_openfile

cd_opendir:   ldx     ZP_SLOT
              lda     #2
              sta     cd_mode,x
              lda     #0
              sta     cd_idx,x
              sta     cd_pos,x
              ldy     #ST_OK
              rts

cd_openfile:  ldy     cd_nameat
              jsr     cd_norm
              lda     #0
              sta     ZP_IDX
10$:          lda     ZP_IDX
              cmp     cd_dirlen
              bcs     90$
              jsr     cd_entptr
              jsr     cd_cmp
              bcs     20$
              inc     ZP_IDX
              bne     10$
90$:          ldy     #ST_NOTFOUND
              rts
;;; Found.  Everything the read needs is taken out of the entry now, so
;;; that a GET touches only the per-IOCB tables.
20$:          ldx     ZP_SLOT
              ldy     #ENT_BANK
              lda     (ZP_ENT),y
              sta     cd_bank,x
              ldy     #ENT_PAGE
              lda     (ZP_ENT),y
              clc
              adc     #WINDOW_HI
              sta     cd_ptrh,x
              lda     #0
              sta     cd_ptrl,x
              ldy     #ENT_LEN
              lda     (ZP_ENT),y
              sta     cd_rem0,x
              iny
              lda     (ZP_ENT),y
              sta     cd_rem1,x
              iny
              lda     (ZP_ENT),y
              sta     cd_rem2,x
              lda     #1
              sta     cd_mode,x
              ldy     #ST_OK
              rts

;;; ---------------------------------------------------------------------------
;;; cd_get -- one byte, in A, with the status in Y.  CIO calls this once
;;; per byte for every read there is.
;;; ---------------------------------------------------------------------------
cd_get:       jsr     cd_slot
              ldx     ZP_SLOT
              lda     cd_mode,x
              cmp     #1
              beq     cd_getfile
              cmp     #2
              beq     cd_getdir
              ldy     #ST_BADCMD
              rts

cd_getfile:   lda     cd_rem0,x
              ora     cd_rem1,x
              ora     cd_rem2,x
              bne     10$
              ldy     #ST_EOF
              rts
10$:          jsr     cd_bank_in
              ldx     ZP_SLOT
              lda     cd_ptrl,x
              sta     ZP_SRC
              lda     cd_ptrh,x
              sta     ZP_SRC+1
              ldy     #0
              lda     (ZP_SRC),y
              pha
              jsr     cd_bank_out
;;; ...and on to the next byte.  A page past the end of the window is the
;;; next bank, which is what makes a file longer than 8 KB work at all.
              ldx     ZP_SLOT
              inc     cd_ptrl,x
              bne     20$
              inc     cd_ptrh,x
              lda     cd_ptrh,x
              cmp     #0xc0
              bcc     20$
              lda     #WINDOW_HI
              sta     cd_ptrh,x
              inc     cd_bank,x
20$:          sec
              lda     cd_rem0,x
              sbc     #1
              sta     cd_rem0,x
              bcs     30$
              lda     cd_rem1,x
              sbc     #0
              sta     cd_rem1,x
              lda     cd_rem2,x
              sbc     #0
              sta     cd_rem2,x
30$:          pla
              ldy     #ST_OK
              rts

;;; ---------------------------------------------------------------------------
;;; cd_getdir -- the listing, one character at a time, generated rather
;;; than buffered: position and entry are all the state there is.
;;;
;;; DOS 2's record, which is what src/sys/dos.c's dos_dirline reads:
;;;
;;;   0   ' ' or '*' for locked          10..12  the extension
;;;   1   ' '                            13      ' '
;;;   2..9  the name, eight              14..16  the size in sectors
;;;                                      17      EOL
;;;
;;; NO "FREE SECTORS" LINE.  A real DOS 2 ends its listing with one;
;;; dos_dirline rejects it (its second character is not a space) and the
;;; desktop counts what it read, so leaving it out costs nothing and is
;;; one fewer state.  Said here because its absence is deliberate.
;;; ---------------------------------------------------------------------------
cd_getdir:    lda     cd_idx,x
              cmp     cd_dirlen
              bcc     10$
              ldy     #ST_EOF
              rts
10$:          lda     cd_pos,x
              bne     20$
;;; the first character of a line: work the entry's size out once
              sta     ZP_IDX
              lda     cd_idx,x
              sta     ZP_IDX
              jsr     cd_entptr
              jsr     cd_sectors
              ldx     ZP_SLOT
20$:          lda     cd_pos,x
              cmp     #17
              bcs     50$             ; the EOL
              cmp     #2
              bcc     40$             ; the two leading spaces
              cmp     #13
              bcc     30$             ; name and extension
              beq     40$             ; the space before the size
;;; 14..16: the three digits
              sec
              sbc     #14
              tay
              lda     cd_digits,y
              jmp     90$
;;; 2..12 map onto the entry's first eleven bytes
30$:          sec
              sbc     #2
              tay
              lda     (ZP_ENT),y
              jmp     90$
40$:          lda     #' '
              jmp     90$
50$:          lda     #EOL
              ldx     ZP_SLOT
              inc     cd_idx,x
              lda     #0
              sta     cd_pos,x
              lda     #EOL
              ldy     #ST_OK
              rts
90$:          ldx     ZP_SLOT
              inc     cd_pos,x
              ldy     #ST_OK
              rts

;;; ---------------------------------------------------------------------------
;;; cd_sectors -- the entry at ZP_ENT, as three digits in cd_digits.
;;;
;;; A DOS 2 sector carries 125 bytes of a file, and the desktop shows what
;;; this says, so it is rounded UP: a file of one byte occupies a sector.
;;; A count past 999 is pinned there, as a DOS 2's own three columns are.
;;; ---------------------------------------------------------------------------
cd_sectors:   ldy     #ENT_LEN
              lda     (ZP_ENT),y
              sta     ZP_NUM
              iny
              lda     (ZP_ENT),y
              sta     ZP_NUM+1
              iny
              lda     (ZP_ENT),y
              bne     70$             ; over 64 KB: peg it
;;; divide by 125, rounding up: count the subtractions
              lda     #0
              sta     cd_digits       ; the quotient, borrowed
              lda     ZP_NUM
              ora     ZP_NUM+1
              beq     20$             ; an empty file is no sectors
10$:          inc     cd_digits
              sec
              lda     ZP_NUM
              sbc     #125
              sta     ZP_NUM
              lda     ZP_NUM+1
              sbc     #0
              sta     ZP_NUM+1
              bcc     20$             ; went negative: that was the last
              lda     ZP_NUM
              ora     ZP_NUM+1
              bne     10$
20$:          lda     cd_digits
              cmp     #250
              bcc     30$
70$:          lda     #249            ; nothing here is that big; pin it
30$:          ldy     #'0'-1
40$:          iny
              sec
              sbc     #100
              bcs     40$
              adc     #100
              sty     cd_digits
              ldy     #'0'-1
50$:          iny
              sec
              sbc     #10
              bcs     50$
              adc     #10
              sty     cd_digits+1
              clc
              adc     #'0'
              sta     cd_digits+2
              rts

;;; ---------------------------------------------------------------------------
;;; The rest of the device.  CLOSE forgets; STATUS says it is well; PUT
;;; and SPECIAL refuse, because this cartridge cannot be written and a
;;; write that silently did nothing would be worse than one that failed.
;;; ---------------------------------------------------------------------------
cd_close:     jsr     cd_slot
              ldx     ZP_SLOT
              lda     #0
              sta     cd_mode,x
              ldy     #ST_OK
              rts

cd_status:    ldy     #ST_OK
              rts

cd_put:       ldy     #ST_READONLY
              rts

cd_special:   ldy     #ST_BADCMD
              rts

cd_initv:     rts

;;; ---------------------------------------------------------------------------
;;; The table CIO dispatches through.  Every vector is the address MINUS
;;; ONE, because CIO pushes it and returns to it.
;;; ---------------------------------------------------------------------------
              .section devdata, root
cd_table:     .word   cd_open-1
              .word   cd_close-1
              .word   cd_get-1
              .word   cd_put-1
              .word   cd_status-1
              .word   cd_special-1
              jmp     cd_initv

;;; The directory tools/mkcar.py writes into the image, and how many
;;; entries of it are real.  Both are patched by the packer at these two
;;; public symbols.
cd_dirlen:    .byte   0
cd_dir:       .space  16*MAX_FILES

              .section devdata, root
cd_mode:      .space  8               ; 0 closed, 1 a file, 2 the directory
cd_bank:      .space  8
cd_ptrl:      .space  8
cd_ptrh:      .space  8
cd_rem0:      .space  8
cd_rem1:      .space  8
cd_rem2:      .space  8
cd_idx:       .space  8               ; the directory: which entry
cd_pos:       .space  8               ; ...and where in its line
cd_want:      .space  11              ; the spec, in an entry's shape
cd_digits:    .space  3
cd_nameat:    .space  1

              .section devdata, root
cd_end:       .byte   0               ; the packer measures up to here
