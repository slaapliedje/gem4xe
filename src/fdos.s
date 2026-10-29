;;; ---------------------------------------------------------------------------
;;; fdos.s -- a read-only DOS for gem4xe's own floppies: D: over an SDFS
;;; disk, and a loader that runs GEM.COM off it.  docs/fdos.md.
;;;
;;; WHY.  gem-sdx.atr, gem-apps.atr and gem-qed.atr carry no DOS, so that
;;; they can be given away: they boot under SpartaDOS X, which lives in the
;;; machine.  Anywhere else -- an emulator's default setup, a machine with
;;; no SDX -- the system floppy did not boot at all.  This is the cartridge's
;;; answer (src/cartd.s, docs/cartridge.md) brought to the floppy: gem4xe
;;; needs a DOS only to READ its files, and reading is the small half.
;;;
;;; HOW IT GETS HERE.  The disk's boot sectors (src/fdboot.s) follow the
;;; sector map the superblock names as its boot file -- G4DOS.SYS, this --
;;; and load it to $0700.  The OS then calls DOSINI, which is fd_install,
;;; and jumps through DOSVEC, which fd_install pointed at fd_run: the
;;; loader, which opens D1:GEM.COM through this handler and runs it.
;;; SpartaDOS X never runs a disk's boot sectors, so under SDX the same
;;; floppy is the ordinary SDFS disk it always was.
;;;
;;; WHAT gem4xe SEES is a DOS 2: $0700 is not a SpartaDOS's 'S' nor a
;;; MyDOS's 'M' (src/sys/dos.h), so paths lose their directories and a
;;; name is looked for by itself.  The handler makes that true: a name is
;;; found in the root or in any directory one level down, root first, and
;;; the listing is every file of those, flat -- the system's \GEM\ and the
;;; applications' \APPS\ seen as one drive, which is how the cartridge's
;;; D1: looks too.  Writes refuse: PUT answers read-only, and gem4xe's
;;; three write sites (Save desktop, a CPX's settings, a copy) already
;;; put up an alert when a write fails.
;;;
;;; SDFS, as tools/atr.py reads it and writes it.  Sector 1's superblock:
;;; +9 the root directory's first sector-map sector, +31 the sector size
;;; ($80 = 128, 0 = 256), +40 the boot file's map.  A file is a chain of
;;; MAP sectors -- +0 the next map, +2 the previous, then the file's data
;;; sectors, two bytes each -- and a directory is a file of 23-byte
;;; entries: status, map sector, length (three bytes), name (eight),
;;; extension (three), date, time.  Entry 0 is the directory's own header,
;;; whose length is the directory's.  Status $08 is in use, $20 a
;;; directory, and an entry without $08 is deleted.
;;;
;;; THE SECTORS COME FROM THE OS's SIO, never a driver of our own: one
;;; loader that brought its own (exec816) did not work with the SIDE2's or
;;; the U1MB's drives, and the OS's own routine is what every DOS calls.
;;; Two buffers, one for a map sector and one for a data sector, each
;;; tagged with its unit and sector, so a file read straight through costs
;;; one SIO call per sector and nothing more.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public fd_install, fd_run, fd_top, fd_image_end

HATABS:       .equ    0x031a
MEMLO:        .equ    0x02e7
DOSVEC:       .equ    0x000a
RUNAD:        .equ    0x02e0
INITAD:       .equ    0x02e2
COLDSV:       .equ    0xe477

;;; SIO's device control block and the OS's entry.
DDEVIC:       .equ    0x0300
DUNIT:        .equ    0x0301
DCOMND:       .equ    0x0302
DSTATS:       .equ    0x0303
DBUFLO:       .equ    0x0304
DBUFHI:       .equ    0x0305
DTIMLO:       .equ    0x0306
DBYTLO:       .equ    0x0308
DBYTHI:       .equ    0x0309
DAUX1:        .equ    0x030a
DAUX2:        .equ    0x030b
SIOV:         .equ    0xe459

CIOV:         .equ    0xe456
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBAH:        .equ    0x0345
ICBLL:        .equ    0x0348
ICBLH:        .equ    0x0349
ICAX1:        .equ    0x034a
ICAX2:        .equ    0x034b
IOCB1:        .equ    0x10

;;; CIO's copy of the IOCB it is working on.
ICDNOZ:       .equ    0x21
ICBALZ:       .equ    0x24
ICAX1Z:       .equ    0x2a
ICIDNO:       .equ    0x2e

ST_OK:        .equ    0x01
ST_EOF:       .equ    0x88
ST_BADCMD:    .equ    0x92
ST_READONLY:  .equ    0xa7
ST_NOTFOUND:  .equ    0xaa
ST_NOTSDFS:   .equ    0x94            ; "bad disk format": not an SDFS disk
EOL:          .equ    0x9b

;;; Zero page, the FR0 window, as src/cartd.s uses it: scratch within one
;;; call, and nothing kept between calls -- gem4xe's own loader
;;; (src/farload.s) uses $D4-$E5 between them.
ZP_P:         .equ    0xd4            ; 16-bit: a pointer into a buffer
ZP_T:         .equ    0xd6            ; 16-bit: a count
ZP_IDX:       .equ    0xd8
ZP_SLOT:      .equ    0xd9            ; the IOCB, 0..7

;;; What an IOCB is doing.
M_CLOSED:     .equ    0
M_FILE:       .equ    1
M_DIR:        .equ    2

;;; A cursor: a place in a file.  Ten bytes, the same in every block.
C_UNIT:       .equ    0
C_MAP:        .equ    1               ; 2: the map sector being followed
C_IDX:        .equ    3               ; which of its entries is next
C_SEC:        .equ    4               ; 2: the data sector in hand, 0 = none
C_POS:        .equ    6               ; the next byte in it
C_REM:        .equ    7               ; 3: bytes left in the file
C_SIZE:       .equ    10
;;; The blocks: 0 and 1 the lookup's two directories, 2 and 3 the
;;; listing's, 4 + n an IOCB's file.
B_LOOK:       .equ    0
B_LIST:       .equ    2
B_FILE:       .equ    4
N_BLOCKS:     .equ    12

;;; A directory entry's fields.
E_STATUS:     .equ    0
E_MAP:        .equ    1
E_SIZE:       .equ    3
E_NAME:       .equ    6               ; eight, then the extension's three
E_LEN:        .equ    23
S_INUSE:      .equ    0x08
S_DIR:        .equ    0x20

;;; ---------------------------------------------------------------------------
;;; $0700: a DOS 2's shape where gem4xe reads it (src/sys/dos.c): not 'S',
;;; not 'M', and DRVBYT at $070A -- D1: and D2:, as a DOS 2.5 comes up.
;;; DOSINI is $0700 (src/fdboot.s's header says so).
;;; ---------------------------------------------------------------------------
              .section fdcode, root
fd_base:      jmp     fd_install      ; $0700: DOSINI
              jmp     fd_run          ; $0703
              .byte   0, 0, 0, 0      ; $0706
              .byte   3               ; $070A: DRVBYT, D1: and D2:
              .byte   0, 0, 0, 0, 0   ; $070B

;;; ---------------------------------------------------------------------------
;;; fd_install -- D: into HATABS, and the machine's vectors.  DOSINI, so it
;;; runs again after every RESET, when the OS has put HATABS back.
;;; ---------------------------------------------------------------------------
fd_install:   ldx     #0
10$:          lda     HATABS,x
              beq     30$             ; a free slot
              cmp     #'D'
              beq     30$             ; a D: already (ours, after a RESET)
              inx
              inx
              inx
              cpx     #33
              bcc     10$
              rts
30$:          lda     #'D'
              sta     HATABS,x
              lda     #.byte0 fd_table
              sta     HATABS+1,x
              lda     #.byte1 fd_table
              sta     HATABS+2,x
              ldx     #7
              lda     #M_CLOSED
40$:          sta     fd_mode,x
              dex
              bpl     40$
              lda     #0xff
              sta     fd_cur
              lda     #0
              sta     fd_mtag+1
              sta     fd_mtag+2
              sta     fd_dtag+1
              sta     fd_dtag+2
              lda     #.byte0 fd_top
              sta     MEMLO
              lda     #.byte1 fd_top
              sta     MEMLO+1
              lda     #.byte0 fd_run
              sta     DOSVEC
              lda     #.byte1 fd_run
              sta     DOSVEC+1
              rts

;;; ---------------------------------------------------------------------------
;;; fd_sio -- read sector ZP_T of unit fd_unit into (ZP_P), A bytes of it
;;; (0 for 256).  Carry set on a failure, with the status in Y.
;;; ---------------------------------------------------------------------------
fd_sio:       sta     DBYTLO
              ldy     #0
              cmp     #0
              bne     5$
              iny                     ; 0 means 256
5$:           sty     DBYTHI
              lda     #0x31
              sta     DDEVIC
              lda     fd_unit
              sta     DUNIT
              lda     #0x52           ; 'R'
              sta     DCOMND
              lda     #0x40
              sta     DSTATS
              lda     ZP_P
              sta     DBUFLO
              lda     ZP_P+1
              sta     DBUFHI
              lda     #7
              sta     DTIMLO
              lda     ZP_T
              sta     DAUX1
              lda     ZP_T+1
              sta     DAUX2
              jsr     SIOV
              ldy     DSTATS
              bmi     90$
              clc
              rts
90$:          sec
              rts

;;; ---------------------------------------------------------------------------
;;; The cursor in hand, fd_c, and the blocks it is loaded from and saved to.
;;; fd_use: A the block wanted.  The one in hand is kept until another is
;;; wanted, so a file read straight through copies nothing.
;;; ---------------------------------------------------------------------------
fd_use:       cmp     fd_cur
              beq     90$
              pha
              lda     fd_cur
              cmp     #0xff
              beq     20$
              jsr     fd_boff
              ldy     #0
10$:          lda     fd_c,y
              sta     fd_blk,x
              inx
              iny
              cpy     #C_SIZE
              bne     10$
20$:          pla
              sta     fd_cur
              jsr     fd_boff
              ldy     #0
30$:          lda     fd_blk,x
              sta     fd_c,y
              inx
              iny
              cpy     #C_SIZE
              bne     30$
90$:          rts

;;; X = A * 10
fd_boff:      asl     a
              sta     ZP_IDX
              asl     a
              asl     a
              clc
              adc     ZP_IDX
              tax
              rts

;;; fd_secsz -- the cursor's unit's sector size into A: 0 for 256, $80.
fd_secsz:     ldx     fd_c+C_UNIT
              lda     fd_ssz,x
              rts

;;; ---------------------------------------------------------------------------
;;; fd_byte -- the next byte of the cursor's file in A, carry clear; carry
;;; set at its end (Y ST_EOF) or on a failure (Y the SIO status).
;;; ---------------------------------------------------------------------------
fd_byte:      lda     fd_c+C_REM
              ora     fd_c+C_REM+1
              ora     fd_c+C_REM+2
              bne     5$
              ldy     #ST_EOF
              sec
              rts
5$:           lda     fd_c+C_SEC
              ora     fd_c+C_SEC+1
              bne     40$
;;; A data sector is wanted: the next entry of the map, the map's own
;;; successor first if this one is used up.
              jsr     fd_secsz        ; 0 or $80
              sec
              sbc     #4
              lsr     a               ; entries per map: 126 or 62
              cmp     fd_c+C_IDX
              bne     20$
              jsr     fd_map          ; the map in hand, for its link
              bcs     99$
              lda     fd_mbuf
              sta     fd_c+C_MAP
              lda     fd_mbuf+1
              sta     fd_c+C_MAP+1
              ora     fd_c+C_MAP
              bne     15$
              ldy     #ST_EOF         ; the chain ends before the length
              sec
              rts
15$:          lda     #0
              sta     fd_c+C_IDX
20$:          jsr     fd_map
              bcs     99$
              lda     fd_c+C_IDX
              asl     a
              clc
              adc     #4
              tay
              lda     fd_mbuf,y
              sta     fd_c+C_SEC
              lda     fd_mbuf+1,y
              sta     fd_c+C_SEC+1
              inc     fd_c+C_IDX
              lda     #0
              sta     fd_c+C_POS
40$:          jsr     fd_data
              bcs     99$
              ldy     fd_c+C_POS
              lda     fd_dbuf,y
              pha
              iny
              sty     fd_c+C_POS
              jsr     fd_secsz
              cmp     fd_c+C_POS      ; past the sector's end: 0 for 256 (the
              bne     50$             ; increment wrapped), $80 for 128
              lda     #0
              sta     fd_c+C_SEC
              sta     fd_c+C_SEC+1
              sta     fd_c+C_POS
50$:          lda     fd_c+C_REM
              sec
              sbc     #1
              sta     fd_c+C_REM
              bcs     60$
              lda     fd_c+C_REM+1
              sbc     #0
              sta     fd_c+C_REM+1
              lda     fd_c+C_REM+2
              sbc     #0
              sta     fd_c+C_REM+2
60$:          pla
              clc
99$:          rts

;;; fd_map / fd_data -- the cursor's map sector, or its data sector, in its
;;; buffer: read unless the buffer's tag says it is there already.
fd_map:       lda     fd_c+C_UNIT
              cmp     fd_mtag
              bne     10$
              lda     fd_c+C_MAP
              cmp     fd_mtag+1
              bne     10$
              lda     fd_c+C_MAP+1
              cmp     fd_mtag+2
              bne     10$
              clc
              rts
10$:          lda     fd_c+C_MAP
              sta     ZP_T
              lda     fd_c+C_MAP+1
              sta     ZP_T+1
              lda     #.byte0 fd_mbuf
              sta     ZP_P
              lda     #.byte1 fd_mbuf
              sta     ZP_P+1
              lda     #0
              sta     fd_mtag+1       ; nothing there until it has arrived
              sta     fd_mtag+2
              lda     fd_c+C_UNIT
              sta     fd_unit
              jsr     fd_secsz
              jsr     fd_sio
              bcs     90$
              lda     fd_c+C_UNIT
              sta     fd_mtag
              lda     fd_c+C_MAP
              sta     fd_mtag+1
              lda     fd_c+C_MAP+1
              sta     fd_mtag+2
              clc
90$:          rts

fd_data:      lda     fd_c+C_UNIT
              cmp     fd_dtag
              bne     10$
              lda     fd_c+C_SEC
              cmp     fd_dtag+1
              bne     10$
              lda     fd_c+C_SEC+1
              cmp     fd_dtag+2
              bne     10$
              clc
              rts
10$:          lda     fd_c+C_SEC
              sta     ZP_T
              lda     fd_c+C_SEC+1
              sta     ZP_T+1
              lda     #.byte0 fd_dbuf
              sta     ZP_P
              lda     #.byte1 fd_dbuf
              sta     ZP_P+1
              lda     #0
              sta     fd_dtag+1
              sta     fd_dtag+2
              lda     fd_c+C_UNIT
              sta     fd_unit
              jsr     fd_secsz
              jsr     fd_sio
              bcs     90$
              lda     fd_c+C_UNIT
              sta     fd_dtag
              lda     fd_c+C_SEC
              sta     fd_dtag+1
              lda     fd_c+C_SEC+1
              sta     fd_dtag+2
              clc
90$:          rts

;;; ---------------------------------------------------------------------------
;;; fd_entry -- the next 23-byte entry of the cursor's directory into
;;; fd_ent.  Carry set at the directory's end (or a failure).
;;; ---------------------------------------------------------------------------
fd_entry:     ldx     #0
10$:          stx     ZP_IDX
              jsr     fd_byte
              bcs     90$
              ldx     ZP_IDX
              sta     fd_ent,x
              inx
              cpx     #E_LEN
              bne     10$
              lda     fd_ent+E_STATUS
              beq     80$             ; a zero status ends a directory
              clc
              rts
80$:          sec
90$:          rts

;;; fd_opendir -- the cursor in hand onto the directory whose map is
;;; ZP_T, past its header, its length taken from the header.
fd_opendir:   lda     fd_unit
              sta     fd_c+C_UNIT
              lda     ZP_T
              sta     fd_c+C_MAP
              lda     ZP_T+1
              sta     fd_c+C_MAP+1
              lda     #0
              sta     fd_c+C_IDX
              sta     fd_c+C_SEC
              sta     fd_c+C_SEC+1
              sta     fd_c+C_POS
              lda     #0xff
              sta     fd_c+C_REM
              sta     fd_c+C_REM+1
              sta     fd_c+C_REM+2
              jsr     fd_entry        ; the header
              bcs     90$
              sec                     ; the length, less the header read
              lda     fd_ent+E_SIZE
              sbc     #E_LEN
              sta     fd_c+C_REM
              lda     fd_ent+E_SIZE+1
              sbc     #0
              sta     fd_c+C_REM+1
              lda     fd_ent+E_SIZE+2
              sbc     #0
              sta     fd_c+C_REM+2
              clc
90$:          rts

;;; ---------------------------------------------------------------------------
;;; fd_next -- the next FILE of the flat view into fd_ent, carry clear; or
;;; carry set when there are no more.  fd_w is which walk (0 the lookup's,
;;; 1 the listing's), each with its two blocks, its phase and whether it
;;; is inside a directory:
;;;
;;;   phase 0   the root's files
;;;   phase 1   the root again, and each directory's files as it passes
;;;   phase 2   done
;;;
;;; One level down, no further: what gem4xe's disks have, \GEM\ and
;;; \APPS\, and what a DOS 2's flat names can be found in without guessing.
;;; ---------------------------------------------------------------------------
fd_next:      ldx     fd_w
              lda     fd_ph,x
              cmp     #2
              bne     5$
              sec
              rts
5$:           cmp     #1
              beq     30$
;;; phase 0: the root's files
              jsr     fd_outer
              jsr     fd_entry
              bcs     20$
              jsr     fd_isfile
              bcs     fd_next
              clc
              rts
20$:          ldx     fd_w            ; the root again, for its directories
              lda     #1
              sta     fd_ph,x
              jsr     fd_rootdir
              bcs     fd_end
              jmp     fd_next
;;; phase 1: inside a directory, or looking for the next one
30$:          lda     fd_in,x
              beq     50$
              jsr     fd_inner
              jsr     fd_entry
              bcs     40$
              jsr     fd_isfile
              bcs     fd_next
              clc
              rts
40$:          ldx     fd_w
              lda     #0
              sta     fd_in,x
              jmp     fd_next
50$:          jsr     fd_outer
              jsr     fd_entry
              bcs     fd_end
              lda     fd_ent+E_STATUS
              and     #S_INUSE
              beq     fd_next
              lda     fd_ent+E_STATUS
              and     #S_DIR
              beq     fd_next
              lda     fd_ent+E_MAP    ; a directory: into it
              sta     ZP_T
              lda     fd_ent+E_MAP+1
              sta     ZP_T+1
              jsr     fd_inner
              jsr     fd_opendir
              bcs     fd_next         ; unreadable: past it
              ldx     fd_w
              lda     #1
              sta     fd_in,x
              jmp     fd_next
fd_end:       ldx     fd_w
              lda     #2
              sta     fd_ph,x
              sec
              rts

;;; carry clear for an entry that is a file in use
fd_isfile:    lda     fd_ent+E_STATUS
              and     #S_INUSE
              beq     80$
              lda     fd_ent+E_STATUS
              and     #S_DIR
              bne     80$
              clc
              rts
80$:          sec
              rts

;;; the walk's two blocks: its outer (the root) and inner
fd_outer:     lda     fd_w
              asl     a
              jmp     fd_use
fd_inner:     lda     fd_w
              asl     a
              ora     #1
              jmp     fd_use

;;; fd_walk -- walk fd_w from the top, over unit fd_unit's root.
fd_walk:      ldx     fd_w
              lda     #0
              sta     fd_ph,x
              sta     fd_in,x
fd_rootdir:   jsr     fd_outer
              ldx     fd_unit
              lda     fd_root,x
              sta     ZP_T
              lda     fd_root+8,x
              sta     ZP_T+1
              jmp     fd_opendir

;;; ---------------------------------------------------------------------------
;;; fd_super -- unit fd_unit's sector 1: its root and its sector size, kept
;;; per unit.  Read at every OPEN, because a disk may have been changed.
;;; Carry set, Y the status, if it cannot be read or is not SDFS.
;;; ---------------------------------------------------------------------------
fd_super:     lda     #1
              sta     ZP_T
              lda     #0
              sta     ZP_T+1
              lda     #.byte0 fd_dbuf
              sta     ZP_P
              lda     #.byte1 fd_dbuf
              sta     ZP_P+1
              lda     #0
              sta     fd_dtag+1       ; the data buffer is the superblock now
              sta     fd_dtag+2
              lda     #0x80
              jsr     fd_sio
              bcs     90$
              ldx     fd_unit
              lda     fd_dbuf+31
              beq     10$             ; 256
              cmp     #0x80
              bne     80$
10$:          sta     fd_ssz,x
              lda     fd_dbuf+9
              sta     fd_root,x
              lda     fd_dbuf+10
              sta     fd_root+8,x
              ora     fd_root,x
              beq     80$
              clc
              rts
80$:          ldy     #ST_NOTSDFS
              sec
90$:          rts

;;; ---------------------------------------------------------------------------
;;; The handler.  CIO calls through the table at the end, each vector the
;;; address less one.
;;; ---------------------------------------------------------------------------
fd_slot:      lda     ICIDNO
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              sta     ZP_SLOT
              lda     ICDNOZ
              and     #7
              sta     fd_unit
              rts

fd_open:      jsr     fd_slot
              ldx     ZP_SLOT
              lda     #M_CLOSED
              sta     fd_mode,x
              lda     ICAX1Z
              and     #0x08
              beq     5$
              ldy     #ST_READONLY    ; a write: this disk is read-only here
              rts
5$:           jsr     fd_super
              bcc     8$
              rts
8$:           jsr     fd_wild
              bcc     20$
;;; The directory.
              lda     #1
              sta     fd_w
              jsr     fd_walk
              lda     #0
              sta     fd_lpos
              ldx     ZP_SLOT
              lda     #M_DIR
              sta     fd_mode,x
              ldy     #ST_OK
              rts
;;; A file: walk until its name.
20$:          ldy     fd_nameat
              jsr     fd_norm
              lda     #0
              sta     fd_w
              jsr     fd_walk
              bcs     80$
30$:          jsr     fd_next
              bcs     80$
              ldx     #10
40$:          lda     fd_ent+E_NAME,x
              cmp     fd_want,x
              bne     30$
              dex
              bpl     40$
;;; Found: the IOCB's own block onto it.
              lda     ZP_SLOT
              clc
              adc     #B_FILE
              jsr     fd_use
              lda     fd_unit
              sta     fd_c+C_UNIT
              lda     fd_ent+E_MAP
              sta     fd_c+C_MAP
              lda     fd_ent+E_MAP+1
              sta     fd_c+C_MAP+1
              lda     fd_ent+E_SIZE
              sta     fd_c+C_REM
              lda     fd_ent+E_SIZE+1
              sta     fd_c+C_REM+1
              lda     fd_ent+E_SIZE+2
              sta     fd_c+C_REM+2
              lda     #0
              sta     fd_c+C_IDX
              sta     fd_c+C_SEC
              sta     fd_c+C_SEC+1
              sta     fd_c+C_POS
              ldx     ZP_SLOT
              lda     #M_FILE
              sta     fd_mode,x
              ldy     #ST_OK
              rts
80$:          ldy     #ST_NOTFOUND
              rts

;;; fd_wild -- past "D", a unit digit and ":", into fd_nameat; carry set
;;; if the name has a wildcard in it, which means the directory.
fd_wild:      ldy     #1
              lda     (ICBALZ),y
              cmp     #':'
              beq     10$
              iny
10$:          iny
              sty     fd_nameat
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

;;; fd_norm -- the name at (ICBALZ) from Y into fd_want, as eleven
;;; space-padded characters, an entry's shape (src/cartd.s cd_norm).
fd_norm:      sty     ZP_IDX
              ldx     #10
              lda     #' '
10$:          sta     fd_want,x
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
              bcs     25$
              sta     fd_want,x
              inx
25$:          iny
              bne     20$
30$:          iny
              ldx     #8
40$:          lda     (ICBALZ),y
              beq     90$
              cmp     #EOL
              beq     90$
              cpx     #11
              bcs     45$
              sta     fd_want,x
              inx
45$:          iny
              bne     40$
90$:          rts

fd_get:       jsr     fd_slot
              ldx     ZP_SLOT
              lda     fd_mode,x
              cmp     #M_FILE
              beq     10$
              cmp     #M_DIR
              beq     fd_getdir
              ldy     #ST_BADCMD
              rts
10$:          txa
              clc
              adc     #B_FILE
              jsr     fd_use
              jsr     fd_byte
              bcs     90$
              ldy     #ST_OK
90$:          rts

;;; ---------------------------------------------------------------------------
;;; fd_getdir -- the listing, a character at a time: DOS 2's 17-character
;;; record (src/sys/dos.c dos_dirline), made into fd_line when the last
;;; one has gone out.
;;;
;;;   0   ' ' or '*' locked            10..12  the extension
;;;   1   ' '                          13      ' '
;;;   2..9  the name                   14..16  the size in DOS 2 sectors
;;;                                    17      EOL
;;; ---------------------------------------------------------------------------
fd_getdir:    lda     fd_lpos
              bne     50$
              lda     #1
              sta     fd_w
              jsr     fd_next
              bcc     10$
              ldy     #ST_EOF
              rts
10$:          lda     #' '
              sta     fd_line
              sta     fd_line+1
              sta     fd_line+13
              ldx     #10
20$:          lda     fd_ent+E_NAME,x
              sta     fd_line+2,x
              dex
              bpl     20$
              jsr     fd_sectors
              lda     fd_digits
              sta     fd_line+14
              lda     fd_digits+1
              sta     fd_line+15
              lda     fd_digits+2
              sta     fd_line+16
              lda     #EOL
              sta     fd_line+17
50$:          ldx     fd_lpos
              lda     fd_line,x
              inx
              cpx     #18
              bne     60$
              ldx     #0
60$:          stx     fd_lpos
              ldy     #ST_OK
              rts

;;; fd_sectors -- fd_ent's length as DOS 2 sectors of 125 bytes, rounded
;;; up, as three digits in fd_digits (src/cartd.s cd_sectors).
fd_sectors:   lda     fd_ent+E_SIZE
              sta     ZP_T
              lda     fd_ent+E_SIZE+1
              sta     ZP_T+1
              lda     fd_ent+E_SIZE+2
              bne     70$
              lda     #0
              sta     fd_digits
              lda     ZP_T
              ora     ZP_T+1
              beq     20$
10$:          inc     fd_digits
              sec
              lda     ZP_T
              sbc     #125
              sta     ZP_T
              lda     ZP_T+1
              sbc     #0
              sta     ZP_T+1
              bcc     20$
              lda     ZP_T
              ora     ZP_T+1
              bne     10$
20$:          lda     fd_digits
              cmp     #250
              bcc     30$
70$:          lda     #249
30$:          ldy     #'0'-1
40$:          iny
              sec
              sbc     #100
              bcs     40$
              adc     #100
              sty     fd_digits
              ldy     #'0'-1
50$:          iny
              sec
              sbc     #10
              bcs     50$
              adc     #10
              sty     fd_digits+1
              clc
              adc     #'0'
              sta     fd_digits+2
              rts

fd_close:     jsr     fd_slot
              ldx     ZP_SLOT
              lda     #M_CLOSED
              sta     fd_mode,x
              ldy     #ST_OK
              rts

fd_status:    ldy     #ST_OK
              rts

fd_put:       ldy     #ST_READONLY
              rts

fd_special:   ldy     #ST_BADCMD
              rts

fd_initv:     rts

;;; ---------------------------------------------------------------------------
;;; fd_run -- DOSVEC: D1:GEM.COM, loaded and run, by src/cart.s's rules
;;; (cart_boot): call INITAD after EVERY segment and point it at an RTS
;;; once it has -- gem4xe's far image is a hundred chunks, each followed by
;;; a segment that writes INITAD -- and jump through RUNAD at the end.
;;;
;;; DOSVEC goes to the OS's cold start first: when gem4xe quits, there is
;;; no DOS to go back to, and starting again from the disk is what is left.
;;; A RESET runs DOSINI, which points DOSVEC here again: GEM reloads.
;;; ---------------------------------------------------------------------------
fd_run:       lda     #.byte0 COLDSV
              sta     DOSVEC
              lda     #.byte1 COLDSV
              sta     DOSVEC+1
              ldx     #.byte0 msg_load
              ldy     #.byte1 msg_load
              lda     #msg_load_end-msg_load
              jsr     fd_print
              ldx     #IOCB1
              lda     #3
              sta     ICCOM,x
              lda     #.byte0 boot_name
              sta     ICBAL,x
              lda     #.byte1 boot_name
              sta     ICBAH,x
              lda     #4
              sta     ICAX1,x
              lda     #0
              sta     ICAX2,x
              jsr     CIOV
              bpl     1$
              jmp     ld_bad
1$:           jsr     ld_arm
              lda     #0
              sta     RUNAD
              sta     RUNAD+1
              jsr     ld_word
              bpl     5$
2$:           jmp     ld_bad
5$:           lda     ld_w
              and     ld_w+1
              cmp     #0xff
              bne     2$
10$:          jsr     ld_word
              bmi     ld_done
              lda     ld_w
              and     ld_w+1
              cmp     #0xff
              beq     10$
              lda     ld_w
              sta     ld_start
              lda     ld_w+1
              sta     ld_start+1
              jsr     ld_word
              bmi     ld_bad
              sec
              lda     ld_w
              sbc     ld_start
              sta     ld_len
              lda     ld_w+1
              sbc     ld_start+1
              sta     ld_len+1
              bcc     ld_bad
              inc     ld_len
              bne     20$
              inc     ld_len+1
20$:          ldx     #IOCB1
              lda     ld_start
              sta     ICBAL,x
              lda     ld_start+1
              sta     ICBAH,x
              lda     ld_len
              sta     ICBLL,x
              lda     ld_len+1
              sta     ICBLH,x
              lda     #7
              sta     ICCOM,x
              jsr     CIOV
              bmi     ld_bad
              ldx     #.byte0 msg_dot
              ldy     #.byte1 msg_dot
              lda     #1
              jsr     fd_print
              jsr     ld_init
              jsr     ld_arm
              jmp     10$

ld_done:      jsr     ld_close
              lda     RUNAD
              ora     RUNAD+1
              beq     ld_bad
              jmp     (RUNAD)

ld_bad:       jsr     ld_close
              ldx     #.byte0 msg_bad
              ldy     #.byte1 msg_bad
              lda     #msg_bad_end-msg_bad
              jsr     fd_print
99$:          jmp     99$             ; nothing more to be done from here

ld_word:      ldx     #IOCB1
              lda     #.byte0 ld_w
              sta     ICBAL,x
              lda     #.byte1 ld_w
              sta     ICBAH,x
              lda     #2
              sta     ICBLL,x
              lda     #0
              sta     ICBLH,x
              lda     #7
              sta     ICCOM,x
              jmp     CIOV

ld_close:     ldx     #IOCB1
              lda     #12
              sta     ICCOM,x
              jmp     CIOV

ld_init:      jmp     (INITAD)

ld_arm:       lda     #.byte0 ld_rts
              sta     INITAD
              lda     #.byte1 ld_rts
              sta     INITAD+1
ld_rts:       rts

;;; fd_print -- A characters at Y:X to the screen, through IOCB 0.
fd_print:     sta     ICBLL
              stx     ICBAL
              sty     ICBAH
              lda     #0
              sta     ICBLH
              ldx     #0
              lda     #11
              sta     ICCOM,x
              jmp     CIOV

boot_name:    .byte   "D1:GEM.COM", EOL
msg_load:     .byte   EOL, "gem4xe: loading"
msg_load_end:
msg_dot:      .byte   "."
msg_bad:      .byte   EOL, "gem4xe: GEM.COM did not load from D1:", EOL
msg_bad_end:

;;; ---------------------------------------------------------------------------
;;; The table CIO dispatches through.
;;; ---------------------------------------------------------------------------
fd_table:     .word   fd_open-1
              .word   fd_close-1
              .word   fd_get-1
              .word   fd_put-1
              .word   fd_status-1
              .word   fd_special-1
              jmp     fd_initv
fd_image_end:                         ; what G4DOS.SYS carries ends here

;;; ---------------------------------------------------------------------------
;;; Variables and buffers: after the image, so the file does not carry
;;; them, and below MEMLO, so nothing else takes them.  Cleared by nobody:
;;; fd_install sets what has to start known.
;;; ---------------------------------------------------------------------------
              .section fdbss, noinit
fd_unit:      .space  1
fd_cur:       .space  1               ; the block in fd_c, $FF none
fd_c:         .space  C_SIZE
fd_blk:       .space  C_SIZE*N_BLOCKS
fd_mode:      .space  8
fd_ssz:       .space  8               ; per unit: 0 for 256, $80
fd_root:      .space  16              ; per unit: the root's map, lo then hi
fd_mtag:      .space  3               ; unit, sector
fd_dtag:      .space  3
fd_w:         .space  1
fd_ph:        .space  2
fd_in:        .space  2
fd_ent:       .space  E_LEN
fd_want:      .space  11
fd_nameat:    .space  1
fd_line:      .space  18
fd_lpos:      .space  1
fd_digits:    .space  3
ld_w:         .space  2
ld_start:     .space  2
ld_len:       .space  2
              .section fdbuf, noinit
fd_mbuf:      .space  256             ; a map sector
fd_dbuf:      .space  256             ; a data sector
fd_top:                               ; MEMLO
