;;; ---------------------------------------------------------------------------
;;; cartd.s -- D1: out of the cartridge, read-only, and on top of a DOS if
;;; the machine booted one.
;;;
;;; WHY THIS AND NOT A DOS.  gem4xe reaches every file through CIO, so a
;;; cartridge carrying only gem4xe would boot a machine with no D1: and
;;; nothing to load DESKTOP.PRG from.  But the ROM is READ-ONLY, and most of
;;; what a DOS is is the write side: the free-sector bitmap, the allocation,
;;; the VTOC, the business of changing a disk without corrupting it.  None
;;; of that has to exist for the ROM.
;;;
;;; TWO WAYS TO RUN, decided by what is in HATABS when this is installed:
;;;
;;;   NO DOS.  The ROM is D1: and the only D:.  Everything is served from
;;;   the cartridge; PUT and SPECIAL refuse, because a write that silently
;;;   did nothing would leave a program believing it had saved.  This is
;;;   the one-file demo of docs/cartridge.md, unchanged.
;;;
;;;   A DOS BOOTED FIRST ($BFFD bit 0 asks the OS to boot a disk before it
;;;   starts the cartridge).  Then D1: is an OVERLAY -- the floppy on top,
;;;   the ROM underneath -- and every other unit is the DOS's own:
;;;
;;;     OPEN to read    the DOS first; the ROM if the DOS has no such file,
;;;                     so what you saved on the floppy is what you get
;;;     OPEN to write   the DOS: the floppy is where writes go
;;;     the directory   the ROM's entries the floppy does not also have,
;;;                     then the floppy's own listing, VERBATIM -- its
;;;                     free-sector line has to stay last, because Dfree
;;;                     reads the last line (src/sys/gemdos.c)
;;;     XIO, STATUS     the DOS
;;;
;;;   Nothing in gem4xe changes for this: every write site in the system
;;;   is an Fcreate -- DESKTOP.INF, a CPX's .CFG, a copy -- and none is an
;;;   update in place, so no write ever has to modify a file in ROM.
;;;
;;; IT RUNS FROM THE ROM, and its state lives in page 6.  It used to be
;;; copied to $0700 and run there, which is exactly where a DOS lives; so
;;; the code stays in the boot bank, which is what the cartridge window
;;; shows whenever this is called, and the one thing that must not run
;;; from the window -- switching a payload bank in to read a byte -- is an
;;; eleven-byte stub copied to $0610.
;;;
;;; AND IT NEVER READS $D5xx.  Real AtariMax hardware switches bank on a
;;; read of that page and this tree's Altirra deliberately does not.  The
;;; bank is selected by WRITING to $D500+n, where the ADDRESS carries the
;;; bank and the value is ignored.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public cd_install, cd_dir, cd_dirlen, cd_end

CCTL:         .equ    0xd500
BOOT_BANK:    .equ    127
WINDOW_HI:    .equ    0xa0            ; the window's high byte

HATABS:       .equ    0x031a
MEMLO:        .equ    0x02e7

;;; CIO's copy of the IOCB it is working on, in zero page, and which IOCB.
ICDNOZ:       .equ    0x21            ; the unit: 1 for D:, D1:
ICBALZ:       .equ    0x24
ICBAHZ:       .equ    0x25
ICBLLZ:       .equ    0x28
ICBLHZ:       .equ    0x29
ICAX1Z:       .equ    0x2a
ICIDNO:       .equ    0x2e            ; the IOCB, times sixteen

ST_OK:        .equ    0x01
ST_EOF:       .equ    0x88
ST_NOTFOUND:  .equ    0xaa
ST_READONLY:  .equ    0xa7
ST_BADCMD:    .equ    0x92

EOL:          .equ    0x9b

;;; A DOS handler table, as HATABS points at it: six vectors, each the
;;; address MINUS ONE, then a JMP to its init.
V_OPEN:       .equ    0
V_CLOSE:      .equ    2
V_GET:        .equ    4
V_PUT:        .equ    6
V_STATUS:     .equ    8
V_SPECIAL:    .equ    10

;;; A directory entry as tools/mkcar.py writes it.  SIXTEEN BYTES, so the
;;; index is four shifts rather than a multiply:
;;;
;;;   0   name, eight characters, space padded
;;;   8   extension, three
;;;  11   the bank it starts in
;;;  12   the page within that bank ($A000 + page*256) -- which is why the
;;;       packer aligns every file to a page
;;;  13   the length, three bytes, low first
ENT_BANK:     .equ    11
ENT_PAGE:     .equ    12
ENT_LEN:      .equ    13
MAX_FILES:    .equ    24

;;; Zero page: the FR0/FRE window, for src/farload.s's reason -- this runs
;;; with the OS's interrupts going and its handlers address zero page
;;; through D, so there is no direct page of our own.  Scratch within one
;;; call only; nothing here is kept between calls.
ZP_SRC:       .equ    0xd4            ; 16-bit: the byte to fetch (the stub's)
ZP_ENT:       .equ    0xd6            ; 16-bit: the entry being compared
ZP_IDX:       .equ    0xd8            ; 8-bit:  which entry
ZP_SLOT:      .equ    0xd9            ; 8-bit:  the IOCB, 0..7
ZP_T:         .equ    0xda            ; 16-bit: the DOS's table / a count

;;; ---------------------------------------------------------------------------
;;; PAGE 6.  The OS neither uses nor clears it once it is up, gem4xe's map
;;; leaves $0200-$06FF alone, and so does every DOS this has met.  Shared
;;; with src/cart.s, which owns $0600-$060B, the loader's $0620-$0625 and
;;; the demo's listing at $06C0; the addresses are repeated there.
;;; ---------------------------------------------------------------------------
CD_HASDOS:    .equ    0x060c          ; 1 if a DOS was here first (cart.s reads)
STUB:         .equ    0x0610          ; the byte fetch, eleven bytes
;;; per IOCB, eight of each
cd_mode:      .equ    0x0626          ; M_*
cd_bank:      .equ    0x062e
cd_ptrl:      .equ    0x0636
cd_ptrh:      .equ    0x063e
cd_rem0:      .equ    0x0646
cd_rem1:      .equ    0x064e
cd_rem2:      .equ    0x0656
cd_idx:       .equ    0x065e          ; the directory: which entry
cd_pos:       .equ    0x0666          ; ...and where in its line
cd_seen0:     .equ    0x066e          ; ROM entries the floppy also has,
cd_seen1:     .equ    0x0676          ; a bit each: 0-7, 8-15, 16-23
cd_seen2:     .equ    0x067e
;;; one of each
cd_want:      .equ    0x0686          ; 11: a name, in an entry's shape
cd_digits:    .equ    0x0691          ; 3
cd_nameat:    .equ    0x0694
cd_dosl:      .equ    0x0695          ; the DOS's handler table, 0 = none
cd_dosh:      .equ    0x0696
cd_fvec:      .equ    0x0697          ; 2: where cd_fwd jumps
cd_fa:        .equ    0x0699          ; A across a forward
cd_acc:       .equ    0x069a          ; 11: a floppy line's name, as it passes
cd_apos:      .equ    0x06a5          ; where in that line
cd_c1:        .equ    0x06a6          ; its characters 1 and 13, which are
cd_c13:       .equ    0x06a7          ; spaces on a file's line
cd_bll:       .equ    0x06a8          ; ICBLL/ICBLH, kept while we read the
cd_blh:       .equ    0x06a9          ; floppy's directory ourselves
cd_ty:        .equ    0x06aa          ; a status, kept
CD_STATE_END: .equ    0x06ab          ; must not reach $06C0

;;; What an IOCB is doing.
M_CLOSED:     .equ    0
M_FILE:       .equ    1               ; a ROM file
M_DIR:        .equ    2               ; the ROM's directory, no DOS
M_FWD:        .equ    3               ; the DOS's, for everything
M_UROM:       .equ    4               ; the overlay's listing: the ROM part,
                                      ; with the floppy's still to come
M_UDOS:       .equ    5               ; ...and now the floppy's, forwarded
M_UONLY:      .equ    6               ; the ROM part, and no floppy after it

              .section devcode, root

;;; ---------------------------------------------------------------------------
;;; The entry, at a fixed place: src/cart.s calls the first byte.
;;; ---------------------------------------------------------------------------
cd_entry:     jmp     cd_install

;;; ---------------------------------------------------------------------------
;;; cd_install -- put D: in HATABS, over a DOS's if there is one.
;;;
;;; The slot is SEARCHED for rather than assumed.  If a D: is there, a DOS
;;; booted first: its table is kept and every call this does not serve
;;; goes to it.  If it is our own table -- installed twice -- it is not
;;; kept, or every forward would come back here for ever.
;;; ---------------------------------------------------------------------------
cd_install:   lda     #0
              sta     cd_dosl
              sta     cd_dosh
              sta     CD_HASDOS
              ldx     #0
10$:          lda     HATABS,x
              beq     30$             ; a free slot: no DOS
              cmp     #'D'
              beq     20$
              inx
              inx
              inx
              cpx     #33
              bcc     10$
              rts                     ; no room, and nothing to be done
20$:          lda     HATABS+2,x
              cmp     #.byte1 cd_table
              bne     25$
              lda     HATABS+1,x
              cmp     #.byte0 cd_table
              beq     30$             ; ours already
25$:          lda     HATABS+1,x
              sta     cd_dosl
              lda     HATABS+2,x
              sta     cd_dosh
              lda     #1
              sta     CD_HASDOS
30$:          lda     #'D'
              sta     HATABS,x
              lda     #.byte0 cd_table
              sta     HATABS+1,x
              lda     #.byte1 cd_table
              sta     HATABS+2,x
;;; The fetch stub down to page 6.
              ldx     #cd_stub_end-cd_stub
40$:          lda     cd_stub-1,x
              sta     STUB-1,x
              dex
              bne     40$
;;; Every IOCB starts closed: page 6 is not cleared by the OS.
              ldx     #7
              lda     #M_CLOSED
50$:          sta     cd_mode,x
              dex
              bpl     50$
              lda     CD_HASDOS
              bne     90$
;;; NO DOS: $0700-$070F in a DOS 2's shape, because the machine has no
;;; other owner for it.  $070A is DRVBYT, which src/sys/gemdos.c's Drvmap
;;; returns -- one bit, D1:, which is the truth -- and the zero at $0700 is
;;; a DOS 2's boot flag, which is what src/sys/dos.c reads it for.  MEMLO
;;; goes past the sixteen bytes.  With a DOS none of this is ours.
              ldx     #15
              lda     #0
60$:          sta     0x0700,x
              dex
              bpl     60$
              lda     #1
              sta     0x070a
              lda     #0x10
              sta     MEMLO
              lda     #0x07
              sta     MEMLO+1
90$:          rts

;;; The stub, as it is copied: X the bank, Y zero, ZP_SRC the address.
;;; POSITION INDEPENDENT, and it has to be.  The value written to $D500,x is
;;; ignored -- the address selects -- and the boot bank goes back before the
;;; rts, because the rts goes back into it.
cd_stub:      sta     CCTL,x
              lda     (ZP_SRC),y
              ldx     #BOOT_BANK
              sta     CCTL,x
              rts
cd_stub_end:

;;; ---------------------------------------------------------------------------
;;; cd_fwd -- the DOS's routine Y (V_OPEN .. V_SPECIAL), with A as given
;;; and X the IOCB, as CIO would have called it.  jsr for its answer, jmp
;;; to hand the call over: the DOS's rts goes wherever ours would have.
;;; ---------------------------------------------------------------------------
cd_fwd:       sta     cd_fa
              lda     cd_dosl
              sta     ZP_T
              lda     cd_dosh
              sta     ZP_T+1
              lda     (ZP_T),y
              clc
              adc     #1
              sta     cd_fvec
              iny
              lda     (ZP_T),y
              adc     #0
              sta     cd_fvec+1
              ldx     ICIDNO
              lda     cd_fa
              jmp     (cd_fvec)

;;; ---------------------------------------------------------------------------
;;; cd_slot -- ZP_SLOT becomes the IOCB, 0..7, from CIO's own copy of it.
;;; ---------------------------------------------------------------------------
cd_slot:      lda     ICIDNO
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
;;; the high bits of idx*16 that the shifts dropped
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
;;; cd_norm -- the spec at (ICBALZ), from offset Y, into cd_want as the
;;; ELEVEN space-padded characters an entry carries.
;;; ---------------------------------------------------------------------------
cd_norm:      sty     ZP_IDX          ; borrow it: where the name starts
              ldx     #10
              lda     #' '
10$:          sta     cd_want,x
              dex
              bpl     10$
              ldy     ZP_IDX
              ldx     #0
20$:          lda     (ICBALZ),y
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
40$:          lda     (ICBALZ),y
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
;;; cd_find -- the entry named in cd_want: carry set and ZP_IDX/ZP_ENT on
;;; it, or carry clear.  cd_findacc is the same for cd_acc.
;;; ---------------------------------------------------------------------------
cd_find:      lda     #0
              sta     ZP_IDX
10$:          lda     ZP_IDX
              cmp     cd_dirlen
              bcs     80$
              jsr     cd_entptr
              ldy     #10
20$:          lda     (ZP_ENT),y
              cmp     cd_want,y
              bne     30$
              dey
              bpl     20$
              sec
              rts
30$:          inc     ZP_IDX
              bne     10$
80$:          clc
              rts

cd_findacc:   ldy     #10
10$:          lda     cd_acc,y
              sta     cd_want,y
              dey
              bpl     10$
              jmp     cd_find

;;; ---------------------------------------------------------------------------
;;; cd_open -- "Dn:NAME.EXT" to read, "Dn:*.*" for the directory, or, with a
;;; DOS underneath, anything at all.
;;; ---------------------------------------------------------------------------
cd_open:      jsr     cd_slot
              lda     cd_dosh
              beq     cd_openrom      ; no DOS: every unit is the ROM
              lda     ICDNOZ
              cmp     #1
              bne     cd_openfwd      ; D2: and up are the DOS's
              lda     ICAX1Z
              and     #0x18
              bne     cd_openfwd      ; a write goes to the floppy -- and so
                                      ; does a RAW directory (AUX1 $14, which
                                      ; gem4xe asks a SpartaDOS for): the
                                      ; ROM's part is DOS 2 text, and mixed
                                      ; into 23-byte entries it is rubbish
              jsr     cd_wild
              bcc     5$
              jmp     cd_uopen        ; the overlay's directory
;;; A file to read: the floppy's if it has one, the ROM's if not.
5$:           ldy     #V_OPEN
              lda     #0
              jsr     cd_fwd
              tya
              bmi     cd_openrom      ; not there: the ROM underneath
              ldx     ZP_SLOT
              lda     #M_FWD
              sta     cd_mode,x
              rts                     ; Y is the DOS's own OK

cd_openfwd:   ldx     ZP_SLOT
              lda     #M_FWD
              sta     cd_mode,x
              ldy     #V_OPEN
              lda     #0
              jmp     cd_fwd          ; the DOS answers, and a failure is its

;;; The ROM's own: a file, or (with no DOS) the directory.
cd_openrom:   jsr     cd_wild
              bcc     cd_openfile
              ldx     ZP_SLOT
              lda     #M_DIR
              sta     cd_mode,x
              jsr     cd_dirzero
              ldy     #ST_OK
              rts

cd_openfile:  ldy     cd_nameat
              jsr     cd_norm
              jsr     cd_find
              bcs     20$
              ldx     ZP_SLOT
              lda     #M_CLOSED
              sta     cd_mode,x
              ldy     #ST_NOTFOUND
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
              lda     #M_FILE
              sta     cd_mode,x
              ldy     #ST_OK
              rts

;;; cd_wild -- past "D", an optional unit digit and ":", into cd_nameat;
;;; carry set if the name has a wildcard in it, which means the directory.
cd_wild:      ldy     #1
              lda     (ICBALZ),y
              cmp     #':'
              beq     10$
              iny
10$:          iny
              sty     cd_nameat
20$:          lda     (ICBALZ),y
              beq     80$
              cmp     #EOL
              beq     80$
              cmp     #'*'
              beq     90$
              cmp     #'?'
              beq     90$
              iny
              bne     20$
80$:          clc
              rts
90$:          sec
              rts

;;; cd_dirzero -- the listing from the top, and nothing yet seen.
cd_dirzero:   ldx     ZP_SLOT
              lda     #0
              sta     cd_idx,x
              sta     cd_pos,x
              sta     cd_seen0,x
              sta     cd_seen1,x
              sta     cd_seen2,x
              rts

;;; ---------------------------------------------------------------------------
;;; cd_uopen -- the overlay's directory: the ROM's entries the floppy does
;;; not also have, then the floppy's listing as the DOS gives it.
;;;
;;; WHICH ROM ENTRIES THE FLOPPY HAS is worked out HERE, by reading the
;;; floppy's directory once through and marking each name that is also in
;;; the ROM, and then opening it again for the listing the caller reads.
;;; That costs a second read of the floppy's directory.  What it buys is
;;; that the floppy's listing can go out VERBATIM and LAST -- its free-sector
;;; line has to be the last line, because Dfree reads the last one -- with
;;; no line of it held back in a buffer, and page 6 has no room for one per
;;; IOCB.  The first pass needs only the name of the line going past.
;;;
;;; While this reads the floppy itself, CIO's length is zero: a DOS 2 reads
;;; straight into the caller's buffer when a GET asks for a lot at once,
;;; and the caller's buffer is not where these bytes are going.
;;; ---------------------------------------------------------------------------
cd_uopen:     jsr     cd_dirzero
              lda     ICBLLZ
              sta     cd_bll
              lda     ICBLHZ
              sta     cd_blh
              lda     #0
              sta     ICBLLZ
              sta     ICBLHZ
              ldy     #V_OPEN
              jsr     cd_fwd
              tya
              bmi     80$             ; no floppy directory: the ROM's alone
              lda     #0
              sta     cd_apos
10$:          ldy     #V_GET
              lda     #0
              jsr     cd_fwd
              cpy     #0x80
              bcs     40$             ; the end of it
              jsr     cd_accum
              jmp     10$
40$:          ldy     #V_CLOSE
              lda     #0
              jsr     cd_fwd
              ldy     #V_OPEN         ; ...and again, for the listing proper
              lda     #0
              jsr     cd_fwd
              tya
              bmi     80$
              lda     #M_UROM
              bne     90$
80$:          lda     #M_UONLY
90$:          ldx     ZP_SLOT
              sta     cd_mode,x
              lda     cd_bll
              sta     ICBLLZ
              lda     cd_blh
              sta     ICBLHZ
              ldy     #ST_OK
              rts

;;; cd_accum -- one byte of the floppy's listing, A.  A file's line is DOS
;;; 2's: a space at 1 and at 13, the name at 2..9, the extension at 10..12
;;; (src/sys/dos.c), and the size after -- three digits on a DOS 2, FOUR on
;;; a MyDOS double-density disk, which is why the length is a range.  At
;;; its EOL, a ROM entry of the same name is marked.
cd_accum:     cmp     #EOL
              beq     50$
              ldx     cd_apos
              cpx     #1
              bne     10$
              sta     cd_c1
10$:          cpx     #13
              bne     20$
              sta     cd_c13
20$:          cpx     #2
              bcc     30$
              cpx     #13
              bcs     30$
              sta     cd_acc-2,x
30$:          inx
              beq     40$             ; a very long line: stay at 255
              stx     cd_apos
40$:          rts
50$:          lda     cd_apos
              ldx     #0
              stx     cd_apos
              cmp     #17
              bcc     40$             ; too short for a file's line: 17 is
              cmp     #21             ; DOS 2's, 18 MyDOS's, whose sizes have
              bcs     40$             ; four digits on a double-density disk
              lda     cd_c1
              cmp     #' '
              bne     40$
              lda     cd_c13
              cmp     #' '
              bne     40$
              jsr     cd_findacc
              bcc     40$
              jmp     cd_mark

;;; cd_mark / cd_isseen -- the seen bit of entry ZP_IDX for IOCB ZP_SLOT.
cd_mark:      jsr     cd_bit
              ora     cd_seen0,x
              sta     cd_seen0,x
              rts
cd_isseen:    jsr     cd_bit          ; A: the bit if seen, 0 if not
              and     cd_seen0,x
              rts

;;; cd_bit -- A the bit, X the slot plus eight times the byte: so that
;;; cd_seen0,x reaches cd_seen1 and cd_seen2, which follow it at eight.
cd_bit:       lda     ZP_IDX
              and     #7
              tax
              lda     #1
10$:          dex
              bmi     20$
              asl     a
              bne     10$
20$:          pha
              lda     ZP_IDX
              lsr     a
              lsr     a
              lsr     a               ; 0, 1 or 2
              asl     a
              asl     a
              asl     a               ; ...times eight
              clc
              adc     ZP_SLOT
              tax
              pla
              rts

;;; ---------------------------------------------------------------------------
;;; cd_get -- one byte, in A, with the status in Y.  CIO calls this once
;;; per byte for every read there is.
;;; ---------------------------------------------------------------------------
cd_get:       jsr     cd_slot
              ldx     ZP_SLOT
              lda     cd_mode,x
              cmp     #M_FILE
              beq     cd_getfile
              cmp     #M_FWD
              beq     cd_getfwd
              cmp     #M_UDOS
              beq     cd_getfwd
              cmp     #M_DIR
              bcc     10$
              jmp     cd_getdir       ; M_DIR, M_UROM, M_UONLY
10$:          ldy     #ST_BADCMD
              rts

cd_getfwd:    ldy     #V_GET
              lda     #0
              jmp     cd_fwd

cd_getfile:   lda     cd_rem0,x
              ora     cd_rem1,x
              ora     cd_rem2,x
              bne     10$
              ldy     #ST_EOF
              rts
10$:          lda     cd_ptrl,x
              sta     ZP_SRC
              lda     cd_ptrh,x
              sta     ZP_SRC+1
              lda     cd_bank,x
              tax
              ldy     #0
              jsr     STUB            ; the byte, and the boot bank back
              pha
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
;;; cd_getdir -- the ROM's listing, one character at a time, generated
;;; rather than buffered: position and entry are all the state there is.
;;; An entry the floppy also has is skipped (never, with no DOS).
;;;
;;; DOS 2's record, which is what src/sys/dos.c's dos_dirline reads:
;;;
;;;   0   ' ' or '*' for locked          10..12  the extension
;;;   1   ' '                            13      ' '
;;;   2..9  the name, eight              14..16  the size in sectors
;;;                                      17      EOL
;;;
;;; NO "FREE SECTORS" LINE of its own.  A real DOS 2 ends its listing with
;;; one; dos_dirline rejects it and the desktop counts what it read.  In the
;;; overlay the floppy's comes last, which is where Dfree looks for it.
;;; ---------------------------------------------------------------------------
cd_getdir:    lda     cd_pos,x
              bne     20$
;;; the first character of a line: past what the floppy has, then the size
5$:           lda     cd_idx,x
              cmp     cd_dirlen
              bcs     cd_dirend
              sta     ZP_IDX
              jsr     cd_isseen       ; A: the bit, or 0
              ldx     ZP_SLOT         ; (which sets Z by itself: test A)
              cmp     #0
              beq     8$
              inc     cd_idx,x
              jmp     5$
8$:           jsr     cd_entptr
              jsr     cd_sectors
              ldx     ZP_SLOT
20$:          lda     cd_idx,x
              sta     ZP_IDX
              jsr     cd_entptr
              ldx     ZP_SLOT
              lda     cd_pos,x
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
50$:          inc     cd_idx,x
              lda     #0
              sta     cd_pos,x
              lda     #EOL
              ldy     #ST_OK
              rts
90$:          inc     cd_pos,x
              ldy     #ST_OK
              rts

;;; The ROM's part is done: the floppy's listing next, if there is one.
cd_dirend:    ldx     ZP_SLOT
              lda     cd_mode,x
              cmp     #M_UROM
              bne     10$
              lda     #M_UDOS
              sta     cd_mode,x
              jmp     cd_getfwd
10$:          ldy     #ST_EOF
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
              sta     ZP_T
              iny
              lda     (ZP_ENT),y
              sta     ZP_T+1
              iny
              lda     (ZP_ENT),y
              bne     70$             ; over 64 KB: peg it
;;; divide by 125, rounding up: count the subtractions
              lda     #0
              sta     cd_digits       ; the quotient, borrowed
              lda     ZP_T
              ora     ZP_T+1
              beq     20$             ; an empty file is no sectors
10$:          inc     cd_digits
              sec
              lda     ZP_T
              sbc     #125
              sta     ZP_T
              lda     ZP_T+1
              sbc     #0
              sta     ZP_T+1
              bcc     20$             ; went negative: that was the last
              lda     ZP_T
              ora     ZP_T+1
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
;;; The rest of the device.  CLOSE forgets, and closes the floppy's side of
;;; anything that has one.  With no DOS, STATUS says it is well and PUT and
;;; SPECIAL refuse; with one, all three are the DOS's -- a write to D1: goes
;;; to the floppy, and so do rename, delete and format.
;;; ---------------------------------------------------------------------------
cd_close:     jsr     cd_slot
              ldx     ZP_SLOT
              lda     cd_mode,x
              pha
              lda     #M_CLOSED
              sta     cd_mode,x
              pla
              cmp     #M_FWD
              beq     10$
              cmp     #M_UROM
              beq     10$
              cmp     #M_UDOS
              beq     10$
              ldy     #ST_OK
              rts
10$:          ldy     #V_CLOSE
              lda     #0
              jmp     cd_fwd

;;; STATUS on an IOCB the ROM is serving is the ROM's to answer; on one the
;;; DOS has, or by name on a closed one, it is the DOS's.
cd_status:    lda     cd_dosh
              beq     10$
              jsr     cd_slot
              ldx     ZP_SLOT
              lda     cd_mode,x
              beq     5$              ; closed: a status by name
              cmp     #M_FWD
              beq     5$
              cmp     #M_UDOS
              bne     10$
5$:           ldy     #V_STATUS
              lda     #0
              jmp     cd_fwd
10$:          ldy     #ST_OK
              rts

cd_put:       sta     cd_fa
              jsr     cd_slot
              ldx     ZP_SLOT
              lda     cd_mode,x
              cmp     #M_FWD
              bne     10$
              ldy     #V_PUT
              lda     cd_fa
              jmp     cd_fwd
10$:          ldy     #ST_READONLY
              rts

cd_special:   lda     cd_dosh
              beq     10$
              ldy     #V_SPECIAL
              lda     #0
              jmp     cd_fwd
10$:          ldy     #ST_BADCMD
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
;;; public symbols -- in the ROM, where they are read.
cd_dirlen:    .byte   0
cd_dir:       .space  16*MAX_FILES

              .section devdata, root
cd_end:       .byte   0               ; the packer measures up to here
