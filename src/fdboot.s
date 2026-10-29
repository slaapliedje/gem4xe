;;; ---------------------------------------------------------------------------
;;; fdboot.s -- the boot sectors of gem4xe's own SDFS floppies: load the
;;; boot file the superblock names, G4DOS.SYS (src/fdos.s), to $0700.
;;;
;;; The OS loads the three boot sectors to $3000, as sector 1's header says
;;; (tools/atr.py boot_gem4xe), and calls $3006, a JMP to here: sectors 2
;;; and 3, at $3080.  Sector 1 itself is the file system's -- the
;;; superblock -- and is not touched.
;;;
;;; WHAT THIS DOES is what a SpartaDOS's boot sectors do with the same
;;; field: +40 of the superblock is the boot file's first sector-map
;;; sector, and the file's data sectors, in the map's order, go to memory
;;; one after another from $0700.  Carry clear back to the OS, which then
;;; calls DOSINI -- $0700, the header's init address -- and jumps through
;;; DOSVEC, which that pointed at the loader.
;;;
;;; ON A FAILURE it says so and waits, rather than answering the OS with a
;;; carry: a carry is BOOT ERROR, printed for ever, which told the last
;;; person who met it nothing (tools/mkfloppy.py, NO_DOS).
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

SB:           .equ    0x3000          ; the superblock, as the OS loaded it
MAPBUF:       .equ    0x3200          ; one map sector at a time
DEST0:        .equ    0x0700
LIMIT:        .equ    0x1c            ; and nothing at or past $1C00

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

;;; Zero page that nothing owns while a disk boots: the floating point
;;; package's, which the OS does not use for this.
ZP_DST:       .equ    0xd4            ; 16-bit: where the next sector goes
ZP_MAP:       .equ    0xd6            ; 16-bit: the map sector in hand
ZP_I:         .equ    0xd8            ; its next entry, as a byte offset
ZP_LIM:       .equ    0xd9            ; the sector size's low byte: 0, $80
ZP_SEC:       .equ    0xda            ; 16-bit

              .section bootcode, root
fb_start:     jmp     fb_go           ; $3080: the header's JMP lands here
fb_fj:        jmp     fb_fail         ; within a branch's reach of them all
fb_go:        lda     SB+40
              sta     ZP_MAP
              lda     SB+41
              sta     ZP_MAP+1
              ora     ZP_MAP
              beq     fb_fj           ; no boot file
              lda     SB+31           ; 0 for 256-byte sectors, $80 for 128
              beq     5$
              cmp     #0x80
              bne     fb_fj
5$:           sta     ZP_LIM
              lda     #.byte0 DEST0
              sta     ZP_DST
              lda     #.byte1 DEST0
              sta     ZP_DST+1
;;; a map sector
10$:          lda     ZP_MAP
              sta     ZP_SEC
              lda     ZP_MAP+1
              sta     ZP_SEC+1
              lda     #.byte0 MAPBUF
              ldx     #.byte1 MAPBUF
              jsr     fb_read
              bcs     fb_fj
              lda     #4
              sta     ZP_I
;;; its data sectors, in order, to memory
20$:          ldy     ZP_I
              lda     MAPBUF,y
              sta     ZP_SEC
              lda     MAPBUF+1,y
              sta     ZP_SEC+1
              iny
              iny
              sty     ZP_I
              ora     ZP_SEC
              beq     fb_done         ; a zero entry: the file ends
              lda     ZP_DST+1
              cmp     #LIMIT
              bcs     fb_fj         ; bigger than a DOS may be
              lda     ZP_DST
              ldx     ZP_DST+1
              jsr     fb_read
              bcs     fb_fj
              lda     ZP_LIM          ; on by a sector
              bne     30$
              inc     ZP_DST+1        ; 256
              jmp     40$
30$:          clc                     ; 128
              adc     ZP_DST
              sta     ZP_DST
              bcc     40$
              inc     ZP_DST+1
40$:          lda     ZP_I
              cmp     ZP_LIM          ; past the map's end: 0 (wrapped) or $80
              bne     20$
              lda     MAPBUF          ; the next map
              sta     ZP_MAP
              lda     MAPBUF+1
              sta     ZP_MAP+1
              ora     ZP_MAP
              bne     10$
fb_done:      clc
              rts

;;; fb_read -- sector ZP_SEC of D1: to X:A, a sector's worth.
fb_read:      sta     DBUFLO
              stx     DBUFHI
              lda     #0x31
              sta     DDEVIC
              lda     #1
              sta     DUNIT
              lda     #0x52           ; 'R'
              sta     DCOMND
              lda     #0x40
              sta     DSTATS
              lda     #7
              sta     DTIMLO
              lda     ZP_LIM
              sta     DBYTLO
              ldx     #0
              cmp     #0
              bne     5$
              inx                     ; 256
5$:           stx     DBYTHI
              lda     ZP_SEC
              sta     DAUX1
              lda     ZP_SEC+1
              sta     DAUX2
              jsr     SIOV
              lda     DSTATS
              bmi     90$
              clc
              rts
90$:          sec
              rts

;;; It did not load: say so through the screen editor, and wait.  In
;;; SECTOR 1, past the superblock's fields (+48 to +127), which is where a
;;; SpartaDOS keeps boot code of its own: sectors 2 and 3 are full.
              .section boot1, root
fb_fail:      ldx     #0
              lda     #11             ; put characters
              sta     ICCOM,x
              lda     #.byte0 fb_msg
              sta     ICBAL,x
              lda     #.byte1 fb_msg
              sta     ICBAH,x
              lda     #fb_msg_end-fb_msg
              sta     ICBLL,x
              lda     #0
              sta     ICBLH,x
              jsr     CIOV
10$:          jmp     10$

fb_msg:       .byte   0x9b, "gem4xe: G4DOS.SYS did not load.", 0x9b
fb_msg_end:
