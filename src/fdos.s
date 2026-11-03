;;; ---------------------------------------------------------------------------
;;; fdos.s -- G4DOS, gem4xe's own DOS for its floppies: D: over an SDFS
;;; disk, and a loader that runs GEM.COM off it.  docs/fdos.md.
;;;
;;; WHY.  gem-sdx.atr, gem-apps.atr and gem-qed.atr carry no DOS, so that
;;; they can be given away: they boot under SpartaDOS X, which lives in the
;;; machine.  Anywhere else -- an emulator's default setup, a machine with
;;; no SDX -- the system floppy did not boot at all.  This is the cartridge's
;;; answer (src/cartd.s, docs/cartridge.md) brought to the floppy.  It
;;; began as reading alone -- the small half, and all GEM needs to start --
;;; and writes since 2026-11-02, so that what gem4xe saves stays saved.
;;;
;;; HOW IT GETS HERE.  The disk's boot sectors (src/fdboot.s) follow the
;;; sector map the superblock names as its boot file -- G4DOS.SYS, this --
;;; and load it to $0700.  The OS then calls DOSINI, which is fd_install,
;;; and jumps through DOSVEC, which fd_install pointed at fd_boot: the
;;; loader, which runs the disk's GEM.COM, or else its AUTORUN.SYS, or else
;;; the shell, SHELL.SYS (src/shell/shell.c) -- and from then on DOSVEC is
;;; the shell's: a program done, or a RESET, comes back to it.
;;; SpartaDOS X never runs a disk's boot sectors, so under SDX the same
;;; floppy is the ordinary SDFS disk it always was.
;;;
;;; WHAT gem4xe SEES is a DOS 2: $0700 is not a SpartaDOS's 'S' nor a
;;; MyDOS's 'M' (src/sys/dos.h), so paths lose their directories and a
;;; name is looked for by itself.  The handler makes that true: a name is
;;; found in the root or in any directory one level down, root first, and
;;; the listing is every file of those, flat -- the system's \GEM\ and the
;;; applications' \APPS\ seen as one drive, which is how the cartridge's
;;; D1: looks too.  A file written goes to the ROOT, which that search
;;; reads first; see WRITING, below, for the rest.
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

              .public fd_install, fd_boot, fd_dos, fd_exec, fd_top, fd_image_end

HATABS:       .equ    0x031a
MEMLO:        .equ    0x02e7
DOSVEC:       .equ    0x000a
WARMST:       .equ    0x0008          ; 0 at a cold start, $FF at a RESET
RUNAD:        .equ    0x02e0
INITAD:       .equ    0x02e2
COLDSV:       .equ    0xe477
PORTB:        .equ    0xd301
BASICF:       .equ    0x03f8          ; the XL OS's: non-zero, BASIC is off

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
ICCOMZ:       .equ    0x22
ICBALZ:       .equ    0x24
ICBLLZ:       .equ    0x28            ; and ICBLHZ: the count still wanted
ICAX1Z:       .equ    0x2a
ICIDNO:       .equ    0x2e

ST_OK:        .equ    0x01
ST_EOF:       .equ    0x88
ST_BADCMD:    .equ    0x92
ST_READONLY:  .equ    0xa7
ST_NOTFOUND:  .equ    0xaa
ST_NOTSDFS:   .equ    0x94            ; "bad disk format": not an SDFS disk
ST_TOOMANY:   .equ    0xa1            ; DOS 2's 161: a second file to write
ST_DISKFULL:  .equ    0xa2            ; DOS 2's 162
ST_BADNAME:   .equ    0xa5            ; DOS 2's 165: no name, or a wildcard
EOL:          .equ    0x9b

;;; Zero page, the FR0 window, as src/cartd.s uses it: scratch within one
;;; call, and nothing kept between calls -- gem4xe's own loader
;;; (src/farload.s) uses $D4-$E5 between them.
ZP_P:         .equ    0xd4            ; 16-bit: a pointer into a buffer
ZP_T:         .equ    0xd6            ; 16-bit: a count
ZP_IDX:       .equ    0xd8
ZP_SLOT:      .equ    0xd9            ; the IOCB, 0..7
ZP_S:         .equ    0xda            ; 16-bit: fd_dput's source

;;; What an IOCB is doing.
M_CLOSED:     .equ    0
M_FILE:       .equ    1
M_DIR:        .equ    2
M_WFILE:      .equ    3               ; the one file being written

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
S_DELETED:    .equ    0x10
S_DIR:        .equ    0x20
S_LOCKED:     .equ    0x01

;;; ---------------------------------------------------------------------------
;;; $0700: a DOS 2's shape where gem4xe reads it (src/sys/dos.c): not 'S',
;;; not 'M', and DRVBYT at $070A -- D1: and D2:, as a DOS 2.5 comes up.
;;; DOSINI is $0700 (src/fdboot.s's header says so).
;;; ---------------------------------------------------------------------------
              .section fdcode, root
fd_base:      jmp     fd_install      ; $0700: DOSINI
              jmp     fd_exec         ; $0703: the shell's: run a file
              .byte   'G', '4'        ; $0706: G4DOS, to gem4xe (src/sys/dos.c)
fd_xunit:     .byte   0               ; $0708: fd_xsec's unit
fd_xmode:     .byte   0               ; $0709: ...and what it is to do
              .byte   3               ; $070A: DRVBYT, D1: and D2:
              jmp     fd_xsec         ; $070B: a sector, for gem4xe
fd_xsect:     .word   0               ; $070E: ...which one

;;; ---------------------------------------------------------------------------
;;; fd_install -- D: into HATABS, and the machine's vectors.  DOSINI, so it
;;; runs again after every RESET, when the OS has put HATABS back.
;;;
;;; AND BASIC OFF, whatever OPTION said.  The OS runs a cartridge rather
;;; than DOSVEC when it finds one after DOSINI, and an XL's BASIC is one
;;; unless OPTION was held at the cold start.  gem4xe's loader switches a
;;; Rapidus to its 65C816, which is a COLD start, long after anybody let
;;; go of OPTION -- and the machine came up at BASIC's READY instead of
;;; loading GEM again.  So the bank comes out here (PORTB bit 1 set), and
;;; BASICF says so, which keeps it out across a warm start too.  Nothing
;;; on this disk wants BASIC.  (phase 119; test-fdos found it when the
;;; emulator's held OPTION stopped covering the second cold start)
;;;
;;; WHERE DOSVEC GOES: at a cold start the boot's order, at a RESET the
;;; shell's (the loader, below).  WARMST is the OS's word for which.
;;; ---------------------------------------------------------------------------
fd_install:   lda     PORTB
              ora     #0x02
              sta     PORTB
              lda     #1
              sta     BASICF
              ldx     #0
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
              ldx     #fd_zero_end-fd_mode-1
              lda     #0              ; every IOCB closed (M_CLOSED is 0), no
40$:          sta     fd_mode,x       ; sector named by either tag, none of
              dex                     ; the bitmap in hand, nothing owed to
              bpl     40$             ; the free count: fdbss's first bytes
              sta     MEMLO           ; fd_top, $2000 (src/fdos.scm): A is
              lda     #.byte1 fd_top  ; its low byte already
              sta     MEMLO+1
              lda     #0xff
              sta     fd_cur
              sta     fd_wslot        ; nothing being written
              ldx     #.byte0 fd_boot
              ldy     #.byte1 fd_boot
              lda     WARMST
              beq     50$
              ldx     #.byte0 fd_dos
              ldy     #.byte1 fd_dos
50$:          stx     DOSVEC
              sty     DOSVEC+1
              rts

;;; ---------------------------------------------------------------------------
;;; fd_sio -- read sector ZP_T of unit fd_unit into (ZP_P), A bytes of it
;;; (0 for 256).  Carry set on a failure, with the status in Y.
;;; ---------------------------------------------------------------------------
fd_sio:       ldx     #0x40           ; read: 'R', the data coming in
              ldy     #0x52
              bne     fd_sioc
;;; fd_siow -- the same, written: 'P', a put without the drive's verify,
;;; which is what a DOS 2.5 or a SpartaDOS asks for unless told otherwise.
fd_siow:      ldx     #0x80
              ldy     #0x50
fd_sioc:      stx     DSTATS
              sty     DCOMND
              sta     DBYTLO
              ldy     #0
              cmp     #0
              bne     5$
              iny                     ; 0 means 256
5$:           sty     DBYTHI
              lda     #0x31
              sta     DDEVIC
              lda     fd_unit
              sta     DUNIT
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
5$:           jsr     fd_need
              bcs     99$
              jsr     fd_data
              bcs     99$
              ldy     fd_c+C_POS
              lda     fd_dbuf,y
              pha
              iny
              sty     fd_c+C_POS
              jsr     fd_secsz
              cmp     fd_c+C_POS      ; past the sector's end: 0 for 256 (the
              bne     50$             ; increment wrapped), $80 for 128
              jsr     fd_secdone
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

;;; fd_need -- the cursor onto a data sector, C_SEC: the one it has, or the
;;; next entry of the map, the map's own successor first if this one is
;;; used up.  Carry set at a chain that ends early (Y ST_EOF) or on a
;;; failure (Y the SIO status).
fd_need:      lda     fd_c+C_SEC
              ora     fd_c+C_SEC+1
              beq     5$
              clc
              rts
5$:           jsr     fd_secsz        ; 0 or $80
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
              clc
99$:          rts

;;; fd_map / fd_data -- the cursor's map sector, or its data sector, in its
;;; buffer: read unless the buffer's tag says it is there already (the
;;; write side's fd_mread and fd_dread, which both sides share).
fd_map:       lda     fd_c+C_UNIT
              sta     fd_unit
              lda     fd_c+C_MAP
              sta     fd_p
              lda     fd_c+C_MAP+1
              sta     fd_p+1
              jmp     fd_mread

fd_data:      lda     fd_c+C_UNIT
              sta     fd_unit
              lda     fd_c+C_SEC
              sta     fd_s
              lda     fd_c+C_SEC+1
              sta     fd_s+1
              jmp     fd_dread

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
              jsr     fd_rewind
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
              jsr     fd_dforget
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
              lda     fd_dbuf+16      ; the bitmap's first sector
              sta     fd_bms,x
              lda     fd_dbuf+17
              sta     fd_bms+8,x
              lda     fd_dbuf+11      ; and the sectors there are
              sta     fd_tot,x
              lda     fd_dbuf+12
              sta     fd_tot+8,x
              lda     fd_root,x
              ora     fd_root+8,x
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
              jmp     fd_openw
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
              jsr     fd_rewind
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
              cmp     #','
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
              cmp     #','
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
              bne     5$
              jmp     fd_getdir
5$:           ldy     #ST_BADCMD
              rts
10$:          txa
              clc
              adc     #B_FILE
              jsr     fd_use
              lda     ICCOMZ          ; GET CHARACTERS, not GET RECORD, which
              and     #2              ; has to stop at the EOL
              beq     20$
              jsr     fd_burst
              bcs     90$
20$:          jsr     fd_byte
              bcs     90$
              ldy     #ST_OK
90$:          rts

;;; ---------------------------------------------------------------------------
;;; fd_burst -- all but the last of the bytes CIO still wants, straight into
;;; the caller's buffer, before fd_byte hands back that last one in A.
;;;
;;; CIO's GET CHARACTERS calls the handler once a byte: it stores A at
;;; (ICBALZ), steps ICBALZ, counts ICBLLZ down, and goes round again until
;;; that is zero -- and at the end reports ICBLL less ICBLLZ as the bytes
;;; read.  So a handler may store bytes itself as long as it moves ICBALZ
;;; and ICBLLZ on by as many, which is DOS 2's burst I/O, and why DOS 2
;;; read GEM.COM four times as fast as this did a byte at a time: G4DOS
;;; was two thirds of the boot's time, the OS's loop most of the rest.
;;; A whole sector, wanted whole, is read by SIO straight into the buffer;
;;; anything less is copied out of fd_dbuf.  Carry set on a failure, with
;;; the status in Y and the bytes before it accounted for.
;;; ---------------------------------------------------------------------------
fd_bdone:     clc                     ; (in branch reach of what decides)
fd_bfail:     rts
fd_burst:
;;; n: CIO's count less the one fd_byte returns, and no more than the file
;;; has less that one too.
10$:          lda     ICBLLZ
              sec
              sbc     #1
              sta     fd_n
              lda     ICBLLZ+1
              sbc     #0
              sta     fd_n+1
              bcc     fd_bdone        ; CIO wants none (it never asks so)
              lda     fd_c+C_REM+2
              bne     20$             ; 64 KB or more left: no limit there
              lda     fd_c+C_REM
              sec
              sbc     #1
              tax
              lda     fd_c+C_REM+1
              sbc     #0
              bcc     fd_bdone        ; nothing left; fd_byte says EOF
              cmp     fd_n+1
              bcc     15$
              bne     20$
              cpx     fd_n
              bcs     20$
15$:          stx     fd_n
              sta     fd_n+1
20$:          lda     fd_n
              ora     fd_n+1
              beq     fd_bdone
;;; ...and no further than this sector's end: 256 or 128 less where it is.
              jsr     fd_need
              bcs     fd_bfail
              jsr     fd_secsz
              eor     #0x80           ; 0 -> $80 (256, below), $80 -> 0 (128)
              bne     25$
              lda     #0x80
              ldx     #0
              beq     30$
25$:          lda     #0
              ldx     #1              ; X:A = 256
30$:          sec
              sbc     fd_c+C_POS
              sta     ZP_T            ; ZP_T: bytes left in the sector
              txa
              sbc     #0
              sta     ZP_T+1
              cmp     fd_n+1
              bcc     35$
              bne     40$
              lda     ZP_T
              cmp     fd_n
              bcs     40$
35$:          lda     ZP_T            ; the sector ends first: that much
              sta     fd_n
              lda     ZP_T+1
              sta     fd_n+1
;;; The sector is wanted to its end.  From its start, that is all of it:
;;; SIO puts it in the caller's buffer and fd_dbuf keeps what it had.
40$:          lda     fd_c+C_POS
              bne     50$
              lda     fd_n
              cmp     ZP_T
              bne     50$
              lda     fd_n+1
              cmp     ZP_T+1
              bne     50$
              lda     fd_c+C_SEC
              sta     ZP_T
              lda     fd_c+C_SEC+1
              sta     ZP_T+1
              lda     ICBALZ
              sta     ZP_P
              lda     ICBALZ+1
              sta     ZP_P+1
              lda     fd_c+C_UNIT
              sta     fd_unit
              jsr     fd_secsz
              jsr     fd_sio
              bcs     99$
              jmp     60$
;;; Part of a sector: out of fd_dbuf.  fd_n is 255 at most here.
50$:          jsr     fd_data
              bcs     99$
              ldx     fd_c+C_POS
              ldy     #0
55$:          lda     fd_dbuf,x
              sta     (ICBALZ),y
              inx
              iny
              cpy     fd_n
              bne     55$
;;; fd_n bytes are in: CIO's pointer and count, and the cursor, on by that.
60$:          lda     ICBALZ
              clc
              adc     fd_n
              sta     ICBALZ
              lda     ICBALZ+1
              adc     fd_n+1
              sta     ICBALZ+1
              lda     ICBLLZ
              sec
              sbc     fd_n
              sta     ICBLLZ
              lda     ICBLLZ+1
              sbc     fd_n+1
              sta     ICBLLZ+1
              lda     fd_c+C_REM
              sec
              sbc     fd_n
              sta     fd_c+C_REM
              lda     fd_c+C_REM+1
              sbc     fd_n+1
              sta     fd_c+C_REM+1
              bcs     65$
              dec     fd_c+C_REM+2
65$:          lda     fd_c+C_POS
              clc
              adc     fd_n
              sta     fd_c+C_POS
              lda     fd_n+1          ; 256: the whole sector, so it is done
              bne     70$
              jsr     fd_secsz
              cmp     fd_c+C_POS      ; at its end: 0 (wrapped) or $80
              bne     75$
70$:          jsr     fd_secdone
75$:          jmp     10$
99$:          rts

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
              lda     fd_mode,x
              cmp     #M_WFILE
              bne     10$
              jmp     fd_closew
10$:          lda     #M_CLOSED
              sta     fd_mode,x
fd_ok:        ldy     #ST_OK          ; STATUS, and the init vector, too
              rts



;;; ===========================================================================
;;; WRITING.  One file open for writing at a time, created -- or an existing
;;; one emptied -- in the ROOT, which is where the flat view looks first, so
;;; a file saved over one found a folder down shadows it from then on.
;;; DELETE (XIO 33) and RENAME (XIO 32) work wherever the flat view finds
;;; the name.  tools/atr.py's Sdfs is the model -- the same allocation, the
;;; same chains, the same directory entries -- and test-fdos reads what this
;;; writes with it, and checks the bitmap against every chain on the disk.
;;;
;;; THE ORDER ON THE DISK is chosen so that a machine reset at any point
;;; leaves a disk SpartaDOS will read: the file's first map page and its
;;; entry go down at OPEN, with the bitmap; its data sectors are only free
;;; sectors with something in them until CLOSE writes the map that names
;;; them, then the length, then the bitmap, then the free count.
;;;
;;; Its buffers are its own -- the data and the map page being filled, and
;;; a bitmap sector -- and a directory is edited through the read side's
;;; two, whose tags stay true: a sector written from one of them is what
;;; the tag says it is, and one written from elsewhere loses its tag.
;;; ===========================================================================

;;; fd_usz / fd_perm -- for unit fd_unit: its sector size (0 for 256, $80),
;;; and the data sectors a map page names (126, 62).  Both use Y.
fd_usz:       ldy     fd_unit
              lda     fd_ssz,y
              rts
fd_perm:      jsr     fd_usz
              beq     10$
              lda     #62
              rts
10$:          lda     #126
              rts

;;; fd_wsio -- sector ZP_T written from (ZP_P), a buffer the read side does
;;; not tag, so neither of its tags may go on naming that sector.
fd_wsio:      jsr     fd_siow
              php
              ldx     #3              ; fd_dtag, then fd_mtag below it
10$:          lda     fd_unit
              cmp     fd_mtag,x
              bne     20$
              lda     ZP_T
              cmp     fd_mtag+1,x
              bne     20$
              lda     ZP_T+1
              cmp     fd_mtag+2,x
              bne     20$
              lda     #0
              sta     fd_mtag+1,x
              sta     fd_mtag+2,x
20$:          dex
              dex
              dex
              bpl     10$
              plp
              rts

;;; fd_mread / fd_mwrite -- map sector fd_p of fd_unit in fd_mbuf, read
;;; unless its tag says it is there; and written back from there.
fd_mread:     lda     fd_unit
              cmp     fd_mtag
              bne     10$
              lda     fd_p
              cmp     fd_mtag+1
              bne     10$
              lda     fd_p+1
              cmp     fd_mtag+2
              bne     10$
              clc
              rts
10$:          lda     #0
              sta     fd_mtag+1
              sta     fd_mtag+2
              jsr     fd_mptr
              jsr     fd_usz
              jsr     fd_sio
              bcs     90$
              lda     fd_unit
              sta     fd_mtag
              lda     fd_p
              sta     fd_mtag+1
              lda     fd_p+1
              sta     fd_mtag+2
              clc
90$:          rts
fd_mwrite:    jsr     fd_mptr
              jsr     fd_usz
              jmp     fd_siow
fd_mptr:      lda     fd_p
              sta     ZP_T
              lda     fd_p+1
              sta     ZP_T+1
              lda     #.byte0 fd_mbuf
              sta     ZP_P
              lda     #.byte1 fd_mbuf
              sta     ZP_P+1
              rts

;;; fd_dread / fd_dwrite -- data sector fd_s of fd_unit in fd_dbuf, the
;;; same way; fd_dzero makes it a sector of zeros, on the disk too.
fd_dread:     lda     fd_unit
              cmp     fd_dtag
              bne     10$
              lda     fd_s
              cmp     fd_dtag+1
              bne     10$
              lda     fd_s+1
              cmp     fd_dtag+2
              bne     10$
              clc
              rts
10$:          jsr     fd_dforget
              jsr     fd_dptr
              jsr     fd_usz
              jsr     fd_sio
              bcc     fd_dtagit
              rts
fd_dtagit:    lda     fd_unit
              sta     fd_dtag
              lda     fd_s
              sta     fd_dtag+1
              lda     fd_s+1
              sta     fd_dtag+2
              clc
90$:          rts
fd_dwrite:    jsr     fd_dptr
              jsr     fd_usz
              jmp     fd_siow
fd_dzero:     ldx     #0
              txa
10$:          sta     fd_dbuf,x
              inx
              bne     10$
              jsr     fd_dwrite
              bcs     90$
              jmp     fd_dtagit
90$:          rts
fd_dptr:      lda     fd_s
              sta     ZP_T
              lda     fd_s+1
              sta     ZP_T+1
              lda     #.byte0 fd_dbuf
              sta     ZP_P
              lda     #.byte1 fd_dbuf
              sta     ZP_P+1
              rts

;;; ---------------------------------------------------------------------------
;;; The bitmap: a bit a sector, SET when the sector is FREE, sector s at
;;; byte s/8 and bit $80 >> (s mod 8), from the sector the superblock names
;;; (+16).  One of its sectors is kept in fd_bmbuf and written back when
;;; another is wanted, or at fd_sync; the free count the superblock keeps
;;; (+13) is moved by fd_fdelta at fd_sync.
;;; ---------------------------------------------------------------------------
fd_bit:       .byte   0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01

;;; fd_bmat -- sector fd_s's bitmap byte, fd_bmbuf+X, and its bit in
;;; fd_mask; the bitmap sector it is in read first.  Carry set on a failure.
fd_bmat:      lda     fd_s
              sta     fd_k
              lda     fd_s+1
              sta     fd_k+1
              lsr     fd_k+1
              ror     fd_k
              lsr     fd_k+1
              ror     fd_k
              lsr     fd_k+1
              ror     fd_k            ; fd_k: the byte, s / 8
              jsr     fd_usz
              bne     10$
              lda     fd_k            ; 256: the sector is its high byte
              sta     ZP_IDX
              lda     fd_k+1
              jmp     20$
10$:          lda     fd_k            ; 128: k / 128, and k mod 128
              and     #0x7f
              sta     ZP_IDX
              lda     fd_k
              asl     a
              lda     fd_k+1
              rol     a
20$:          ldx     fd_unit
              clc
              adc     fd_bms,x
              sta     fd_bmwant
              lda     fd_bms+8,x
              adc     #0
              sta     fd_bmwant+1
              jsr     fd_bmget
              bcs     90$
              lda     fd_s
              and     #7
              tay
              lda     fd_bit,y
              sta     fd_mask
              ldx     ZP_IDX
              clc
90$:          rts

;;; fd_bmget -- bitmap sector fd_bmwant of fd_unit in fd_bmbuf.
fd_bmget:     lda     fd_bmunit
              cmp     fd_unit
              bne     10$
              lda     fd_bmsec
              cmp     fd_bmwant
              bne     10$
              lda     fd_bmsec+1
              cmp     fd_bmwant+1
              bne     10$
              clc
              rts
10$:          jsr     fd_bmflush
              bcs     90$
              jsr     fd_bforget
              lda     fd_bmwant
              sta     ZP_T
              lda     fd_bmwant+1
              sta     ZP_T+1
              jsr     fd_bmptr
              jsr     fd_usz
              jsr     fd_sio
              bcs     90$
              lda     fd_unit
              sta     fd_bmunit
              lda     fd_bmwant
              sta     fd_bmsec
              lda     fd_bmwant+1
              sta     fd_bmsec+1
              clc
90$:          rts

;;; fd_bmflush -- the bitmap sector in hand back to its disk, if changed.
fd_bmflush:   lda     fd_bmdirty
              beq     80$
              lda     fd_unit
              pha
              lda     fd_bmunit
              sta     fd_unit
              lda     fd_bmsec
              sta     ZP_T
              lda     fd_bmsec+1
              sta     ZP_T+1
              jsr     fd_bmptr
              jsr     fd_usz
              jsr     fd_wsio
              pla
              sta     fd_unit
              bcs     90$
              lda     #0
              sta     fd_bmdirty
80$:          clc
90$:          rts
fd_bmptr:     lda     #.byte0 fd_bmbuf
              sta     ZP_P
              lda     #.byte1 fd_bmbuf
              sta     ZP_P+1
              rts

;;; fd_alloc -- a free sector of fd_unit into fd_s, now in use: the first
;;; free one at or after fd_hint, going round once.  Carry set, Y
;;; ST_DISKFULL, when there is none (or Y the SIO status).
fd_alloc:     lda     fd_hint
              sta     fd_s
              lda     fd_hint+1
              sta     fd_s+1
              lda     #0
              sta     fd_wrap
10$:          ldx     fd_unit         ; past the last sector: round once
              lda     fd_tot+8,x
              cmp     fd_s+1
              bcc     15$
              bne     20$
              lda     fd_tot,x
              cmp     fd_s
              bcs     20$
15$:          lda     fd_wrap
              bne     80$
              inc     fd_wrap
              lda     #1
              sta     fd_s
              lda     #0
              sta     fd_s+1
20$:          jsr     fd_bmat
              bcs     99$
              lda     fd_bmbuf,x
              and     fd_mask
              bne     50$
              inc     fd_s
              bne     10$
              inc     fd_s+1
              jmp     10$
50$:          lda     fd_mask         ; free: it is used now
              eor     #0xff
              and     fd_bmbuf,x
              sta     fd_bmbuf,x
              lda     #1
              sta     fd_bmdirty
              lda     fd_fdelta
              bne     55$
              dec     fd_fdelta+1
55$:          dec     fd_fdelta
              lda     fd_s
              clc
              adc     #1
              sta     fd_hint
              lda     fd_s+1
              adc     #0
              sta     fd_hint+1
              clc
              rts
80$:          ldy     #ST_DISKFULL
              sec
99$:          rts

;;; fd_freesec -- sector fd_s of fd_unit free again.
fd_freesec:   jsr     fd_bmat
              bcs     90$
              lda     fd_bmbuf,x
              ora     fd_mask
              sta     fd_bmbuf,x
              lda     #1
              sta     fd_bmdirty
              inc     fd_fdelta
              bne     80$
              inc     fd_fdelta+1
80$:          clc
90$:          rts

;;; fd_freechain -- every sector of the chain whose first map is fd_p, its
;;; data sectors and its map pages, free.
fd_freechain:
10$:          lda     fd_p
              ora     fd_p+1
              beq     80$
              jsr     fd_mread
              bcs     90$
              jsr     fd_usz
              sta     fd_wrap         ; the page's end: 0 (256 wraps) or $80
              ldy     #4
20$:          lda     fd_mbuf,y
              sta     fd_s
              lda     fd_mbuf+1,y
              sta     fd_s+1
              ora     fd_s
              beq     30$
              tya
              pha
              jsr     fd_freesec
              pla
              tay
              bcs     90$
30$:          iny
              iny
              cpy     fd_wrap
              bne     20$
              lda     fd_p            ; the page itself, its successor kept
              sta     fd_s
              lda     fd_p+1
              sta     fd_s+1
              lda     fd_mbuf
              pha
              lda     fd_mbuf+1
              pha
              jsr     fd_freesec
              pla
              sta     fd_p+1
              pla
              sta     fd_p
              bcc     10$
              rts
80$:          clc
90$:          rts

;;; fd_sync -- the bitmap sector in hand written back, and the
;;; superblock's free count moved by what was taken and given back.
fd_sync:      jsr     fd_bmflush
              bcs     90$
              lda     fd_fdelta
              ora     fd_fdelta+1
              beq     80$
              jsr     fd_bforget
              lda     #1
              sta     ZP_T
              lda     #0
              sta     ZP_T+1
              jsr     fd_bmptr
              lda     #0x80
              jsr     fd_sio
              bcs     90$
              lda     fd_bmbuf+13
              clc
              adc     fd_fdelta
              sta     fd_bmbuf+13
              lda     fd_bmbuf+14
              adc     fd_fdelta+1
              sta     fd_bmbuf+14
              lda     #0x80
              jsr     fd_wsio
              bcs     90$
              lda     #0
              sta     fd_fdelta
              sta     fd_fdelta+1
80$:          clc
90$:          rts

;;; ---------------------------------------------------------------------------
;;; Directories, edited by offset: fd_dmap is the directory's first map,
;;; fd_doff a byte in it -- entry n is at 23 * n, the header entry 0.
;;; ---------------------------------------------------------------------------

;;; fd_dsec -- the directory's data sector number fd_dk into fd_s, made if
;;; the directory does not reach it yet: a sector of zeros, and a map page
;;; when one fills, linked both ways.
fd_dsec:      lda     fd_dmap
              sta     fd_p
              lda     fd_dmap+1
              sta     fd_p+1
10$:          jsr     fd_perm
              sta     fd_wrap
              lda     fd_dk+1
              bne     20$
              lda     fd_dk
              cmp     fd_wrap
              bcs     20$
              jmp     40$
20$:          lda     fd_dk           ; not in this page: the next
              sec
              sbc     fd_wrap
              sta     fd_dk
              lda     fd_dk+1
              sbc     #0
              sta     fd_dk+1
              jsr     fd_mread
              bcs     97$
              lda     fd_mbuf
              ora     fd_mbuf+1
              bne     30$
              jsr     fd_alloc        ; there is none: a new page
              bcs     97$
              lda     fd_s
              sta     fd_mbuf
              lda     fd_s+1
              sta     fd_mbuf+1
              jsr     fd_mwrite
              bcs     97$
              ldx     #0
              txa
25$:          sta     fd_mbuf,x
              inx
              bne     25$
              lda     fd_p
              sta     fd_mbuf+2
              lda     fd_p+1
              sta     fd_mbuf+3
              lda     fd_s
              sta     fd_p
              lda     fd_s+1
              sta     fd_p+1
              jsr     fd_mwrite
              bcs     97$
              lda     fd_unit         ; fd_mbuf is that page now
              sta     fd_mtag
              lda     fd_p
              sta     fd_mtag+1
              lda     fd_p+1
              sta     fd_mtag+2
              jmp     10$
97$:          rts
30$:          lda     fd_mbuf+1
              tax
              lda     fd_mbuf
              sta     fd_p
              stx     fd_p+1
              jmp     10$
40$:          jsr     fd_mread
              bcs     99$
              lda     fd_dk
              asl     a
              clc
              adc     #4
              tay
              lda     fd_mbuf,y
              sta     fd_s
              lda     fd_mbuf+1,y
              sta     fd_s+1
              ora     fd_s
              bne     80$
              tya                     ; none there yet: a sector of zeros
              pha
              jsr     fd_alloc
              bcs     98$
              pla
              tay
              lda     fd_s
              sta     fd_mbuf,y
              lda     fd_s+1
              sta     fd_mbuf+1,y
              jsr     fd_mwrite
              bcs     99$
              jsr     fd_dzero
              bcs     99$
80$:          clc
99$:          rts
98$:          pla
              rts

;;; fd_dput -- fd_dn bytes from (ZP_S) to fd_doff in the directory, across
;;; a sector's end if the entry is.
fd_dput:      lda     #0
              sta     fd_k            ; where in the source
10$:          lda     fd_dn
              beq     80$
              jsr     fd_usz
              bne     20$
              lda     fd_doff+1       ; 256: the high byte is the sector,
              sta     fd_dk           ; the low one where in it
              lda     #0
              sta     fd_dk+1
              lda     fd_doff
              sta     fd_k+1
              jmp     30$
20$:          lda     fd_doff         ; 128
              and     #0x7f
              sta     fd_k+1
              lda     fd_doff
              asl     a
              lda     fd_doff+1
              rol     a
              sta     fd_dk
              lda     #0
              rol     a
              sta     fd_dk+1
30$:          jsr     fd_dsec
              bcs     99$
              jsr     fd_dread
              bcs     99$
              ldx     fd_k+1
40$:          ldy     fd_k
              lda     (ZP_S),y
              sta     fd_dbuf,x
              inc     fd_k
              inc     fd_doff
              bne     45$
              inc     fd_doff+1
45$:          inx
              dec     fd_dn
              beq     50$
              stx     fd_k+1
              jsr     fd_usz
              cmp     fd_k+1          ; the sector's end
              bne     40$
50$:          jsr     fd_dwrite
              bcs     99$
              lda     fd_dn
              bne     10$
80$:          clc
99$:          rts

;;; fd_dfind -- fd_want in the directory fd_dmap: carry clear and its
;;; offset in fd_doff, the entry in fd_ent; or carry set, and fd_dfree the
;;; first free slot or else the end.  fd_hsize: the directory's length.
fd_dfind:     lda     #B_LOOK
              jsr     fd_use
              lda     fd_dmap
              sta     ZP_T
              lda     fd_dmap+1
              sta     ZP_T+1
              jsr     fd_opendir
              bcs     95$
              lda     fd_ent+E_SIZE
              sta     fd_hsize
              lda     fd_ent+E_SIZE+1
              sta     fd_hsize+1
              lda     #E_LEN
              sta     fd_doff
              lda     #0
              sta     fd_doff+1
              lda     #0xff
              sta     fd_dfree+1      ; none yet
10$:          jsr     fd_entry
              bcs     50$
              lda     fd_ent+E_STATUS
              and     #S_INUSE
              bne     20$
              lda     fd_dfree+1      ; a free slot: the first is kept
              cmp     #0xff
              bne     30$
              lda     fd_doff
              sta     fd_dfree
              lda     fd_doff+1
              sta     fd_dfree+1
              jmp     30$
20$:          ldx     #10
25$:          lda     fd_ent+E_NAME,x
              cmp     fd_want,x
              bne     30$
              dex
              bpl     25$
              clc
              rts
30$:          lda     fd_doff
              clc
              adc     #E_LEN
              sta     fd_doff
              bcc     10$
              inc     fd_doff+1
              jmp     10$
50$:          lda     fd_dfree+1
              cmp     #0xff
              bne     60$
              lda     fd_hsize
              sta     fd_dfree
              lda     fd_hsize+1
              sta     fd_dfree+1
60$:          ldy     #ST_NOTFOUND
95$:          sec
              rts

;;; fd_flatfind -- fd_want where the flat view finds it: the root, then
;;; each directory in the root.  As fd_dfind, with fd_dmap where it was.
fd_flatfind:  ldx     fd_unit
              lda     fd_root,x
              sta     fd_dmap
              lda     fd_root+8,x
              sta     fd_dmap+1
              jsr     fd_dfind
              bcc     90$
              lda     #B_LOOK+1
              jsr     fd_use
              ldx     fd_unit
              lda     fd_root,x
              sta     ZP_T
              lda     fd_root+8,x
              sta     ZP_T+1
              jsr     fd_opendir
              bcs     80$
10$:          lda     #B_LOOK+1
              jsr     fd_use
              jsr     fd_entry
              bcs     80$
              lda     fd_ent+E_STATUS
              and     #S_INUSE
              beq     10$
              lda     fd_ent+E_STATUS
              and     #S_DIR
              beq     10$
              lda     fd_ent+E_MAP
              sta     fd_dmap
              lda     fd_ent+E_MAP+1
              sta     fd_dmap+1
              jsr     fd_dfind
              bcs     10$
90$:          rts
80$:          ldy     #ST_NOTFOUND
              sec
              rts

;;; ---------------------------------------------------------------------------
;;; OPEN to write (aux1 8): a file of that name in the root emptied, or a
;;; new one made there.  Its first map page and its entry, length 0, are on
;;; the disk before this returns.
;;; ---------------------------------------------------------------------------
fd_openw:     lda     fd_wslot
              cmp     #0xff
              beq     2$
              ldy     #ST_TOOMANY     ; one at a time
              rts
2$:           lda     ICAX1Z
              and     #0x0f
              cmp     #0x08
              beq     4$
              ldy     #ST_BADCMD      ; not appending or updating, yet
              rts
4$:           jsr     fd_super
              bcc     6$
              rts
6$:           jsr     fd_wild
              bcc     8$
7$:           ldy     #ST_BADNAME
              rts
8$:           ldy     fd_nameat
              jsr     fd_norm
              lda     fd_want
              cmp     #' '
              beq     7$
              ldx     fd_unit
              lda     fd_root,x
              sta     fd_dmap
              lda     fd_root+8,x
              sta     fd_dmap+1
              lda     #1
              sta     fd_hint
              lda     #0
              sta     fd_hint+1
              jsr     fd_dfind
              bcs     20$
              lda     fd_ent+E_STATUS ; there already: not a directory, not
              and     #S_DIR|S_LOCKED ; locked, and its chain goes
              beq     10$
              ldy     #ST_READONLY
              rts
10$:          lda     fd_doff
              sta     fd_woff
              lda     fd_doff+1
              sta     fd_woff+1
              lda     fd_ent+E_MAP
              sta     fd_p
              lda     fd_ent+E_MAP+1
              sta     fd_p+1
              jsr     fd_freechain
              bcs     98$
              jmp     30$
98$:          rts
20$:          lda     fd_dfree
              sta     fd_woff
              lda     fd_dfree+1
              sta     fd_woff+1
30$:          lda     fd_unit
              sta     fd_wunit
              jsr     fd_alloc        ; its first map page, empty, now
              bcs     98$
              lda     fd_s
              sta     fd_wfirst
              sta     fd_wmap
              lda     fd_s+1
              sta     fd_wfirst+1
              sta     fd_wmap+1
              ldx     #0
              txa
35$:          sta     fd_wmbuf,x
              inx
              bne     35$
              jsr     fd_wmflush
              bcs     98$
              ldx     #E_LEN-1        ; its entry: in use, that map, no
              lda     #0              ; length yet, the name
40$:          sta     fd_ebuf,x
              dex
              bpl     40$
              lda     #S_INUSE
              sta     fd_ebuf+E_STATUS
              lda     fd_wfirst
              sta     fd_ebuf+E_MAP
              lda     fd_wfirst+1
              sta     fd_ebuf+E_MAP+1
              ldx     #10
45$:          lda     fd_want,x
              sta     fd_ebuf+E_NAME,x
              dex
              bpl     45$
              lda     fd_woff
              sta     fd_doff
              lda     fd_woff+1
              sta     fd_doff+1
              lda     #.byte0 fd_ebuf
              sta     ZP_S
              lda     #.byte1 fd_ebuf
              sta     ZP_S+1
              lda     #E_LEN
              sta     fd_dn
              jsr     fd_dput
              bcs     99$
              lda     fd_woff         ; past the end: the header's length
              cmp     fd_hsize        ; grows by an entry
              bne     50$
              lda     fd_woff+1
              cmp     fd_hsize+1
              bne     50$
              lda     fd_hsize
              clc
              adc     #E_LEN
              sta     fd_hsize
              bcc     47$
              inc     fd_hsize+1
47$:          lda     #E_SIZE
              sta     fd_doff
              lda     #0
              sta     fd_doff+1
              lda     #.byte0 fd_hsize
              sta     ZP_S
              lda     #.byte1 fd_hsize
              sta     ZP_S+1
              lda     #2
              sta     fd_dn
              jsr     fd_dput
              bcs     99$
50$:          jsr     fd_sync
              bcs     99$
              lda     fd_dmap
              sta     fd_wdir
              lda     fd_dmap+1
              sta     fd_wdir+1
              lda     #0
              sta     fd_widx
              sta     fd_wpos
              sta     fd_wsize
              sta     fd_wsize+1
              sta     fd_wsize+2
              ldx     ZP_SLOT
              lda     #M_WFILE
              sta     fd_mode,x
              stx     fd_wslot
              ldy     #ST_OK
99$:          rts

;;; fd_wmflush -- the map page being filled, to its sector.
fd_wmflush:   lda     fd_wmap
              sta     ZP_T
              lda     fd_wmap+1
              sta     ZP_T+1
              lda     #.byte0 fd_wmbuf
              sta     ZP_P
              lda     #.byte1 fd_wmbuf
              sta     ZP_P+1
              jsr     fd_usz
              jmp     fd_wsio

;;; fd_wsector -- fd_wbuf to a new data sector, named in the map page; a
;;; new page first, linked both ways, when that one is full.
fd_wsector:   jsr     fd_perm
              cmp     fd_widx
              bne     20$
              jsr     fd_alloc
              bcs     99$
              lda     fd_s
              sta     fd_wmbuf
              lda     fd_s+1
              sta     fd_wmbuf+1
              jsr     fd_wmflush
              bcs     99$
              ldx     #0
              txa
10$:          sta     fd_wmbuf,x
              inx
              bne     10$
              lda     fd_wmap
              sta     fd_wmbuf+2
              lda     fd_wmap+1
              sta     fd_wmbuf+3
              lda     fd_s
              sta     fd_wmap
              lda     fd_s+1
              sta     fd_wmap+1
              lda     #0
              sta     fd_widx
20$:          jsr     fd_alloc
              bcs     99$
              lda     fd_s
              sta     ZP_T
              lda     fd_s+1
              sta     ZP_T+1
              lda     #.byte0 fd_wbuf
              sta     ZP_P
              lda     #.byte1 fd_wbuf
              sta     ZP_P+1
              jsr     fd_usz
              jsr     fd_wsio
              bcs     99$
              lda     fd_widx
              asl     a
              clc
              adc     #4
              tay
              lda     fd_s
              sta     fd_wmbuf,y
              lda     fd_s+1
              sta     fd_wmbuf+1,y
              inc     fd_widx
              lda     #0
              sta     fd_wpos
              clc
99$:          rts

;;; fd_wbyte -- A into the file being written.
fd_wbyte:     ldx     fd_wpos
              sta     fd_wbuf,x
              inx
              stx     fd_wpos
              inc     fd_wsize
              bne     10$
              inc     fd_wsize+1
              bne     10$
              inc     fd_wsize+2
10$:          jsr     fd_usz
              cmp     fd_wpos         ; full: 0 (wrapped) or $80
              bne     80$
              jmp     fd_wsector
80$:          clc
              rts

;;; ---------------------------------------------------------------------------
;;; PUT -- the byte CIO hands over, and for PUT CHARACTERS as many of the
;;; ones after it in the caller's buffer as fit this sector, CIO's pointer
;;; and count moved on by as many: fd_burst's way, the other direction.
;;; CIO's PUT loop loads the byte at (ICBALZ), calls this, then steps the
;;; pointer and counts down -- so the bytes taken here are the ones after.
;;; ---------------------------------------------------------------------------
fd_put:       sta     fd_pa
              jsr     fd_slot
              ldx     ZP_SLOT
              lda     fd_mode,x
              cmp     #M_WFILE
              beq     10$
              ldy     #ST_READONLY
              rts
80$:          ldy     #ST_OK
99$:          rts
10$:          lda     fd_wunit
              sta     fd_unit
              lda     fd_pa
              jsr     fd_wbyte
              bcs     99$
              lda     ICCOMZ          ; PUT RECORD: stop at the EOL, so a
              and     #2              ; byte at a time
              beq     80$
20$:          lda     ICBLLZ          ; n: CIO's count less the byte it has
              sec
              sbc     #1
              sta     fd_n
              lda     ICBLLZ+1
              sbc     #0
              sta     fd_n+1
              ora     fd_n
              beq     80$
              jsr     fd_usz          ; room: the sector less what is in
              sec                     ; (0 for all 256)
              sbc     fd_wpos
              sta     ZP_IDX
              lda     fd_n+1
              bne     25$             ; 256 and up
              lda     ZP_IDX
              beq     30$             ; room for 256: n fits
              cmp     fd_n
              bcs     30$
25$:          lda     ZP_IDX          ; as much as there is room for, 255
              bne     27$             ; at most
              lda     #255
27$:          sta     fd_n
              lda     #0
              sta     fd_n+1
30$:          lda     fd_n
              clc
              adc     #1
              sta     ZP_IDX          ; the copy's end, past the byte CIO has
              ldy     #1
              ldx     fd_wpos
35$:          lda     (ICBALZ),y
              sta     fd_wbuf,x
              inx
              iny
              cpy     ZP_IDX
              bne     35$
              stx     fd_wpos
              lda     ICBALZ
              clc
              adc     fd_n
              sta     ICBALZ
              bcc     40$
              inc     ICBALZ+1
40$:          lda     ICBLLZ
              sec
              sbc     fd_n
              sta     ICBLLZ
              bcs     45$
              dec     ICBLLZ+1
45$:          lda     fd_wsize
              clc
              adc     fd_n
              sta     fd_wsize
              bcc     50$
              inc     fd_wsize+1
              bne     50$
              inc     fd_wsize+2
50$:          jsr     fd_usz
              cmp     fd_wpos
              beq     55$
              jmp     20$
55$:          jsr     fd_wsector
              bcc     57$
              rts
57$:          jmp     20$

;;; CLOSE of the file being written: its last sector, its last map page,
;;; its length in its entry, then the bitmap and the free count.
fd_closew:    lda     fd_wunit
              sta     fd_unit
              lda     fd_wpos
              beq     10$
              jsr     fd_wsector
              bcs     90$
10$:          jsr     fd_wmflush
              bcs     90$
              lda     fd_wdir
              sta     fd_dmap
              lda     fd_wdir+1
              sta     fd_dmap+1
              lda     fd_woff
              clc
              adc     #E_SIZE
              sta     fd_doff
              lda     fd_woff+1
              adc     #0
              sta     fd_doff+1
              lda     #.byte0 fd_wsize
              sta     ZP_S
              lda     #.byte1 fd_wsize
              sta     ZP_S+1
              lda     #3
              sta     fd_dn
              jsr     fd_dput
              bcs     90$
              jsr     fd_sync
              bcs     90$
              ldy     #ST_OK
90$:          ldx     ZP_SLOT         ; closed, whatever came of it
              lda     #M_CLOSED
              sta     fd_mode,x
              lda     #0xff
              sta     fd_wslot
              rts

;;; ---------------------------------------------------------------------------
;;; SPECIAL: XIO 33, delete, and XIO 32, rename ("D1:OLD.EXT,NEW.EXT").
;;; ---------------------------------------------------------------------------
fd_special:   jsr     fd_slot
              lda     ICCOMZ
              cmp     #33
              beq     fd_delete
              cmp     #32
              bne     5$
              jmp     fd_rename
5$:           ldy     #ST_BADCMD
              rts

fd_delete:    jsr     fd_super
              bcs     99$
              jsr     fd_wild
              bcc     5$
              ldy     #ST_BADNAME
              rts
5$:           ldy     fd_nameat
              jsr     fd_norm
              jsr     fd_flatfind
              bcs     99$
              lda     fd_ent+E_STATUS
              and     #S_DIR|S_LOCKED
              beq     10$
              ldy     #ST_READONLY
              rts
10$:          lda     fd_ent+E_STATUS
              and     #(~S_INUSE)&0xff
              ora     #S_DELETED
              sta     fd_ebuf
              lda     fd_ent+E_MAP
              sta     fd_p
              lda     fd_ent+E_MAP+1
              sta     fd_p+1
              lda     #1
              sta     fd_hint
              lda     #0
              sta     fd_hint+1
              jsr     fd_freechain
              bcs     99$
              lda     #.byte0 fd_ebuf
              sta     ZP_S
              lda     #.byte1 fd_ebuf
              sta     ZP_S+1
              lda     #1
              sta     fd_dn
              jsr     fd_dput
              bcs     99$
              jsr     fd_sync
              bcs     99$
              ldy     #ST_OK
99$:          rts

fd_rename:    jsr     fd_super
              bcs     3$
              jsr     fd_wild
              bcc     5$
4$:           ldy     #ST_BADNAME
3$:           rts
5$:           ldy     fd_nameat       ; the old name, kept in fd_want2
              jsr     fd_norm
              lda     (ICBALZ),y
              cmp     #','
              bne     4$
              iny
              ldx     #10
6$:           lda     fd_want,x
              sta     fd_want2,x
              dex
              bpl     6$
              jsr     fd_norm         ; the new one, into the entry's name
              lda     fd_want
              cmp     #' '
              beq     4$
              ldx     #10
7$:           lda     fd_want,x
              sta     fd_ebuf+E_NAME,x
              lda     fd_want2,x
              sta     fd_want,x
              dex
              bpl     7$
              jsr     fd_flatfind     ; the old one, where it is
              bcs     99$
              lda     fd_ent+E_STATUS
              and     #S_LOCKED
              beq     10$
              ldy     #ST_READONLY
              rts
10$:          lda     fd_doff
              sta     fd_roff
              lda     fd_doff+1
              sta     fd_roff+1
              ldx     #10             ; the new name may not be there already
20$:          lda     fd_ebuf+E_NAME,x
              sta     fd_want,x
              dex
              bpl     20$
              jsr     fd_dfind
              bcc     4$
              lda     fd_roff
              clc
              adc     #E_NAME
              sta     fd_doff
              lda     fd_roff+1
              adc     #0
              sta     fd_doff+1
              lda     #.byte0 fd_ebuf
              clc
              adc     #E_NAME
              sta     ZP_S
              lda     #.byte1 fd_ebuf
              adc     #0
              sta     ZP_S+1
              lda     #11
              sta     fd_dn
              jsr     fd_dput
              bcs     99$
              ldy     #ST_OK
99$:          rts

;;; ---------------------------------------------------------------------------
;;; fd_xsec ($070B) -- one sector, read or written, for gem4xe's own SDFS
;;; (src/sys/sdfs.c, docs/sdfs-plan.md), which runs where the DOS is this
;;; one and does its own folders.  Unit fd_xunit, sector fd_xsect, through
;;; fd_dbuf; fd_xmode bit 0 writes, bit 7 is a 128-byte sector -- and bit
;;; 6 asks only where fd_dbuf is, in A and X (low, high: what gem4xe's
;;; sdx_call hands back).  Otherwise carry set is a failure, and DSTATS
;;; says which.
;;; The tags stay true: fd_dbuf is that sector afterwards, and a sector
;;; written is no longer what fd_mbuf or the bitmap buffer say they hold.
;;; ---------------------------------------------------------------------------
fd_xsec:      bit     fd_xmode
              bvs     90$
              lda     fd_xunit
              sta     fd_unit
              lda     fd_xsect
              sta     fd_s
              lda     fd_xsect+1
              sta     fd_s+1
              jsr     fd_dptr
              jsr     fd_dforget
              lda     fd_xmode
              lsr     a               ; bit 0, the direction, into carry
              lda     fd_xmode
              and     #0x80           ; SIO's length: $80, or 0 for 256
              bcs     10$
              jsr     fd_sio
              bcs     30$
              jmp     fd_dtagit
10$:          jsr     fd_wsio
              bcs     30$
              jsr     fd_bforget
              jmp     fd_dtagit
30$:          rts
90$:          lda     #.byte0 fd_dbuf
              ldx     #.byte1 fd_dbuf
              rts

;;; ---------------------------------------------------------------------------
;;; THE LOADER -- a file in the Atari's binary format, loaded and run, by
;;; src/cart.s's rules (cart_boot): INITAD called after EVERY segment and
;;; pointed at an RTS once it has -- gem4xe's far image is a hundred chunks,
;;; each followed by a segment that writes INITAD -- and RUNAD called at
;;; the end as a subroutine, so that a program that ends in an RTS comes
;;; back to DOSVEC as one that jumps there does.
;;;
;;; WHICH FILE.  fd_boot, DOSVEC at a cold start: GEM.COM, else AUTORUN.SYS,
;;; else the shell -- the system or an appliance, a disk with one program
;;; on it, a DOS to work in.  fd_dos, DOSVEC once anything has run and
;;; after a RESET: the shell first, then the same -- a disk with no shell
;;; boots again.  A name that will not open is passed over.  fd_exec, at
;;; $0703, is the shell's own: the one file named at X (low) and Y.  Each
;;; name as G4DOS finds it, in the root or a folder in it, root first.
;;;
;;; The name goes on the screen and a dot for each segment after it, the
;;; only sign of life a long load gives.  Nothing to run, or a file that
;;; is not one, says so and stops there: RESET is the way out, to the shell.
;;; ---------------------------------------------------------------------------
ld_names:     .byte   "D:SHELL.SYS", EOL   ; fd_dos from here,
ld_gem:       .byte   "D:GEM.COM", EOL     ; fd_boot from here
              .byte   "D:AUTORUN.SYS", EOL
              .byte   "D:SHELL.SYS", EOL
ld_end:

fd_boot:      ldy     #ld_gem-ld_names
              .byte   0x2c            ; BIT abs: over the next LDY
fd_dos:       ldy     #0
ld_try:       sty     ld_i            ; the name at ld_names+Y
              tya
              clc
              adc     #.byte0 ld_names
              tax
              lda     #.byte1 ld_names
              adc     #0
              tay
              bne     ld_open         ; (always)
fd_exec:      lda     #0xff           ; the shell's: one name, none after it
              sta     ld_i
ld_open:      stx     ICBAL+IOCB1
              sty     ICBAH+IOCB1
              lda     #.byte0 fd_dos
              sta     DOSVEC
              lda     #.byte1 fd_dos
              sta     DOSVEC+1
              lda     #4              ; to read (AUX2 is nothing to this DOS)
              sta     ICAX1+IOCB1
              lda     #3              ; OPEN
              jsr     ld_cio
              bpl     ld_go
              jsr     ld_close
              ldy     ld_i
              bmi     ld_none         ; the shell's file is not there
10$:          iny                     ; the next name
              lda     ld_names-1,y
              cmp     #EOL
              bne     10$
              cpy     #ld_end-ld_names
              bcc     ld_try
ld_none:      jmp     ld_bad          ; none of them

ld_go:        lda     ICBAL+IOCB1     ; the name, on the screen: PUT RECORD
              sta     ICBAL           ; stops at its EOL
              lda     ICBAH+IOCB1
              sta     ICBAH
              lda     #0x40
              sta     ICBLL
              lda     #0
              sta     ICBLH
              tax
              lda     #9
              sta     ICCOM
              jsr     CIOV
              jsr     ld_arm
              lda     #0
              sta     RUNAD
              sta     RUNAD+1
              jsr     ld_word
              bmi     ld_bad
              lda     ld_w
              and     ld_w+1
              cmp     #0xff
              bne     ld_bad          ; not a binary file
20$:          jsr     ld_word
              bmi     ld_done         ; its end
              lda     ld_w
              and     ld_w+1
              cmp     #0xff
              beq     20$             ; a segment's own $FFFF
              lda     ld_w
              sta     ld_start
              lda     ld_w+1
              sta     ld_start+1
              jsr     ld_word
              bmi     ld_bad
              ldx     #IOCB1          ; the segment, start to end inclusive,
              lda     ld_start        ; straight to where it goes
              sta     ICBAL,x
              lda     ld_start+1
              sta     ICBAH,x
              sec
              lda     ld_w
              sbc     ld_start
              sta     ICBLL,x
              lda     ld_w+1
              sbc     ld_start+1
              sta     ICBLH,x
              bcc     ld_bad
              inc     ICBLL,x
              bne     30$
              inc     ICBLH,x
30$:          lda     #7
              jsr     ld_cio
              bmi     ld_bad
              ldx     #.byte0 msg_dot
              ldy     #.byte1 msg_dot
              lda     #1
              jsr     fd_print
              jsr     ld_init
              jsr     ld_arm
              jmp     20$

ld_bad:       jsr     ld_close
              ldx     #.byte0 msg_bad
              ldy     #.byte1 msg_bad
              lda     #msg_bad_end-msg_bad
              jsr     fd_print
99$:          jmp     99$

ld_done:      jsr     ld_close
              lda     RUNAD
              ora     RUNAD+1
              beq     1$              ; nothing to run
              jsr     ld_run
1$:           jmp     (DOSVEC)

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
;;; ld_cio -- CIO's command A on IOCB 1.
ld_cio:       ldx     #IOCB1
              sta     ICCOM,x
              jmp     CIOV

ld_close:     lda     #12
              bne     ld_cio

ld_run:       jmp     (RUNAD)
ld_init:      jmp     (INITAD)

ld_arm:       lda     #.byte0 ld_rts
              sta     INITAD
              lda     #.byte1 ld_rts
              sta     INITAD+1
ld_rts:       rts

;;; fd_dforget -- the data buffer names no sector; fd_bforget -- nor does
;;; the bitmap's.  A is 0 after either, as it was where they were inline.
fd_dforget:   lda     #0
              sta     fd_dtag+1
              sta     fd_dtag+2
              rts
fd_bforget:   lda     #0
              sta     fd_bmsec
              sta     fd_bmsec+1
              rts

;;; fd_rewind -- fd_c at its file's first data sector, none in hand;
;;; fd_secdone -- the sector in hand used up.  A is 0 after either.
fd_rewind:    lda     #0
              sta     fd_c+C_IDX
fd_secdone:   lda     #0
              sta     fd_c+C_SEC
              sta     fd_c+C_SEC+1
              sta     fd_c+C_POS
              rts

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

msg_dot:      .byte   "."
msg_bad:      .byte   EOL, "load failed", EOL
msg_bad_end:

;;; ---------------------------------------------------------------------------
;;; The table CIO dispatches through.
;;; ---------------------------------------------------------------------------
fd_table:     .word   fd_open-1
              .word   fd_close-1
              .word   fd_get-1
              .word   fd_put-1
              .word   fd_ok-1
              .word   fd_special-1
              jmp     fd_ok
fd_image_end:                         ; what G4DOS.SYS carries ends here

;;; ---------------------------------------------------------------------------
;;; Variables and buffers: after the image, so the file does not carry
;;; them, and below MEMLO, so nothing else takes them.  Cleared by nobody:
;;; fd_install sets what has to start known.
;;; ---------------------------------------------------------------------------
              .section fdbss, noinit
;;; first, what fd_install zeroes in one loop: in this order, and fd_dtag
;;; three bytes above fd_mtag, which fd_wsio counts on
fd_mode:      .space  8
fd_mtag:      .space  3               ; unit, sector
fd_dtag:      .space  3
fd_bmsec:     .space  2               ; the bitmap: the sector in fd_bmbuf, 0 none
fd_bmunit:    .space  1
fd_bmdirty:   .space  1
fd_bmwant:    .space  2
fd_fdelta:    .space  2               ; free sectors gained, signed
fd_zero_end:
fd_unit:      .space  1
fd_cur:       .space  1               ; the block in fd_c, $FF none
fd_c:         .space  C_SIZE
fd_blk:       .space  C_SIZE*N_BLOCKS
fd_ssz:       .space  8               ; per unit: 0 for 256, $80
fd_root:      .space  16              ; per unit: the root's map, lo then hi
fd_w:         .space  1
fd_ph:        .space  2
fd_in:        .space  2
fd_ent:       .space  E_LEN
fd_want:      .space  11
fd_nameat:    .space  1
fd_line:      .space  18
fd_lpos:      .space  1
fd_n:         .space  2               ; fd_burst's bytes this time round
fd_digits:    .space  3
;;; per unit, low bytes at +0, high at +8 (fd_root's shape)
fd_bms:       .space  16              ; the bitmap's first sector
fd_tot:       .space  16              ; the disk's sectors
;;; the file being written
fd_wslot:     .space  1               ; its IOCB, $FF none
fd_wunit:     .space  1
fd_wdir:      .space  2               ; the first map of its directory
fd_woff:      .space  2               ; its entry's offset in that
fd_wfirst:    .space  2               ; its own first map
fd_wmap:      .space  2               ; the map page being filled
fd_widx:      .space  1               ; data sectors in that page so far
fd_wpos:      .space  1               ; bytes in fd_wbuf
fd_wsize:     .space  3
fd_pa:        .space  1               ; PUT's byte, across fd_slot
;;; the bitmap (its sector in hand: above)
fd_hint:      .space  2               ; where the next search starts
fd_s:         .space  2               ; a sector: fd_alloc's, fd_dsec's
fd_k:         .space  2
fd_mask:      .space  1
fd_wrap:      .space  1
;;; a directory being edited
fd_dmap:      .space  2               ; its first map
fd_doff:      .space  2               ; where, in it
fd_dn:        .space  1               ; how many bytes
fd_dfree:     .space  2               ; fd_dfind: a free slot, or the end
fd_hsize:     .space  2               ; fd_dfind: its length, from its header
fd_dk:        .space  2               ; fd_dsec: which of its sectors
fd_p:         .space  2
;;; the loader's words: it only reads, and a directory is only edited by a
;;; write, so it borrows the editing's -- but the name it is trying has to
;;; outlast an open, whose lookup is fd_dfind's, so that one is the file
;;; being written's, which nothing is while the loader runs
ld_w:         .equ    fd_doff
ld_start:     .equ    fd_dfree
ld_i:         .equ    fd_wdir
fd_want2:     .space  11              ; RENAME's old name, kept
fd_roff:      .space  2               ; RENAME: the old entry's offset
fd_ebuf:      .space  E_LEN           ; an entry to write
              .section fdbuf, noinit
fd_mbuf:      .space  256             ; a map sector
fd_dbuf:      .space  256             ; a data sector
fd_wbuf:      .space  256             ; the file being written: its data
fd_wmbuf:     .space  256             ; ...and its map page
fd_bmbuf:     .space  256             ; a bitmap sector
fd_top:                               ; MEMLO
