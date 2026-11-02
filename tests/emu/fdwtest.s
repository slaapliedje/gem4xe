;;; ---------------------------------------------------------------------------
;;; fdwtest.s -- G4DOS's write side, exercised through CIO by a plain 6502
;;; program that G4DOS's own loader runs in place of GEM.COM
;;; (tests/emu/fdos_write.py builds the disk and reads what this left).
;;;
;;; Every CIO call's status goes to RES+n, in the order of the table in
;;; fdos_write.py; RES+0 becomes 'D' when the last one is done.  The
;;; pattern -- byte i of $4000-$7FFF is (i/256)*13 + 3 + (i mod 256)*7 --
;;; is what the gate expects in the files, computed again on the host.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public t_start

CIOV:         .equ    0xe456
ICCOM:        .equ    0x0342
ICBAL:        .equ    0x0344
ICBAH:        .equ    0x0345
ICBLL:        .equ    0x0348
ICBLH:        .equ    0x0349
ICAX1:        .equ    0x034a
ICAX2:        .equ    0x034b
IOCB1:        .equ    0x10
IOCB2:        .equ    0x20
EOL:          .equ    0x9b

RES:          .equ    0x0600          ; what the gate reads
PAT:          .equ    0x4000          ; 16 KB of the pattern
PAT500:       .equ    0x41f4          ; PAT+500 (.byte0 binds before a +)
RBUF:         .equ    0x8000          ; reading back, 13,000 bytes

P:            .equ    0xcb            ; user zero page: a pointer
ACC:          .equ    0xcd
X13:          .equ    0xce
N:            .equ    0xcf            ; RES's next slot
Q:            .equ    0xd0            ; another pointer (not G4DOS's $D4-$DB)

C_OPEN:       .equ    3
C_GETC:       .equ    7
C_PUTR:       .equ    9
C_PUTC:       .equ    11
C_CLOSE:      .equ    12
C_RENAME:     .equ    32
C_DELETE:     .equ    33

              .section tcode, root
t_start:      lda     #0
              sta     RES
              lda     #1
              sta     N
              jsr     t_gen

;;; NEW.DAT: 1,000 bytes as one PUT CHARACTERS (the burst), then a record
;;; a byte at a time
              ldx     #IOCB1
              jsr     t_close
              lda     #.byte0 nm_new
              ldy     #.byte1 nm_new
              jsr     t_openw
              lda     #.byte0 PAT
              ldy     #.byte1 PAT
              jsr     t_buf
              lda     #.byte0 1000
              ldy     #.byte1 1000
              ldx     #C_PUTC
              jsr     t_xfer                          ; 2
              lda     #.byte0 rec
              ldy     #.byte1 rec
              jsr     t_buf
              lda     #20
              ldy     #0
              ldx     #C_PUTR
              jsr     t_xfer                          ; 3
              jsr     t_close1                        ; 4

;;; BIG.DAT: 39,000 bytes in three PUTs, past the first map page
              lda     #.byte0 nm_big
              ldy     #.byte1 nm_big
              jsr     t_openw                         ; 5
              jsr     t_big13000                      ; 6
              jsr     t_big13000                      ; 7
              jsr     t_big13000                      ; 8
              jsr     t_close1                        ; 9

;;; OLD.TXT, which is there: emptied and written again, 300 bytes
              lda     #.byte0 nm_old
              ldy     #.byte1 nm_old
              jsr     t_openw                         ; 10
              lda     #.byte0 PAT500
              ldy     #.byte1 PAT500
              jsr     t_buf
              lda     #.byte0 300
              ldy     #.byte1 300
              ldx     #C_PUTC
              jsr     t_xfer                          ; 11
              jsr     t_close1                        ; 12

;;; REN.TXT to RENAMED.TXT; KEEP.DAT, which is in SUB, deleted
              lda     #.byte0 nm_ren
              ldy     #.byte1 nm_ren
              ldx     #C_RENAME
              jsr     t_xio                           ; 13
              lda     #.byte0 nm_keep
              ldy     #.byte1 nm_keep
              ldx     #C_DELETE
              jsr     t_xio                           ; 14

;;; refusals: a second file to write ($A1), a wildcard ($A5)
              lda     #.byte0 nm_a
              ldy     #.byte1 nm_a
              jsr     t_openw                         ; 15
              ldx     #IOCB2
              lda     #.byte0 nm_b
              ldy     #.byte1 nm_b
              jsr     t_open2                         ; 16
              ldx     #IOCB2
              jsr     t_close
              jsr     t_close1                        ; 17
              lda     #.byte0 nm_wild
              ldy     #.byte1 nm_wild
              jsr     t_openw                         ; 18
              ldx     #IOCB1
              jsr     t_close
              lda     #.byte0 nm_a
              ldy     #.byte1 nm_a
              ldx     #C_DELETE
              jsr     t_xio                           ; 19

;;; NEW.DAT read back: 1,006 bytes, then end of file
              lda     #.byte0 nm_new
              ldy     #.byte1 nm_new
              jsr     t_openr                         ; 20
              lda     #.byte0 RBUF
              ldy     #.byte1 RBUF
              jsr     t_buf
              lda     #.byte0 1006
              ldy     #.byte1 1006
              ldx     #C_GETC
              jsr     t_xfer                          ; 21
              lda     #.byte0 RBUF
              ldy     #.byte1 RBUF
              jsr     t_buf
              lda     #10
              ldy     #0
              ldx     #C_GETC
              jsr     t_xfer                          ; 22: $88
              jsr     t_close1                        ; 23

;;; BIG.DAT read back in three, each compared with the pattern by the gate
;;; -- which reads RBUF after the LAST one; the first two are counted here
              lda     #.byte0 nm_big
              ldy     #.byte1 nm_big
              jsr     t_openr                         ; 24
              jsr     t_get13000                      ; 25
              jsr     t_cmp13000                      ; 26: mismatches
              jsr     t_get13000                      ; 27
              jsr     t_cmp13000                      ; 28
              jsr     t_get13000                      ; 29
              jsr     t_cmp13000                      ; 30
              jsr     t_close1                        ; 31

              lda     #'D'
              sta     RES
99$:          jmp     99$

;;; ---------------------------------------------------------------------------
;;; The pattern into PAT: byte (h, l) is h*13 + 3 + l*7.
t_gen:        lda     #.byte0 PAT
              sta     P
              lda     #.byte1 PAT
              sta     P+1
              lda     #3
              sta     X13
              ldx     #64
10$:          lda     X13
              sta     ACC
              ldy     #0
20$:          lda     ACC
              sta     (P),y
              clc
              adc     #7
              sta     ACC
              iny
              bne     20$
              inc     P+1
              lda     X13
              clc
              adc     #13
              sta     X13
              dex
              bne     10$
              rts

t_big13000:   lda     #.byte0 PAT
              ldy     #.byte1 PAT
              jsr     t_buf
              lda     #.byte0 13000
              ldy     #.byte1 13000
              ldx     #C_PUTC
              jmp     t_xfer

t_get13000:   lda     #.byte0 RBUF
              ldy     #.byte1 RBUF
              jsr     t_buf
              lda     #.byte0 13000
              ldy     #.byte1 13000
              ldx     #C_GETC
              jmp     t_xfer

;;; RBUF against PAT, 13,000 bytes: the mismatches, 255 at most, to RES.
t_cmp13000:   lda     #0
              sta     ACC
              lda     #.byte0 PAT
              sta     P
              lda     #.byte1 PAT
              sta     P+1
              lda     #.byte0 RBUF
              sta     Q
              lda     #.byte1 RBUF
              sta     Q+1
              ldx     #51             ; 50 pages, and 200 bytes of a 51st
10$:          ldy     #0
20$:          cpx     #1
              bne     25$
              cpy     #200
              beq     40$
25$:          lda     (P),y
              cmp     (Q),y
              beq     30$
              inc     ACC
              bne     30$
              dec     ACC
30$:          iny
              bne     20$
              inc     P+1
              inc     Q+1
              dex
              bne     10$
40$:          lda     ACC
              jmp     t_res

;;; ---------------------------------------------------------------------------
;;; CIO, IOCB 1 unless said: open to write (aux1 8), to read (4), a
;;; transfer (X the command, A/Y the length), close, XIO (A/Y the name).
t_openw:      ldx     #IOCB1
t_open2:      sta     ICBAL,x
              tya
              sta     ICBAH,x
              lda     #8
              bne     t_open
t_openr:      ldx     #IOCB1
              sta     ICBAL,x
              tya
              sta     ICBAH,x
              lda     #4
t_open:       sta     ICAX1,x
              lda     #0
              sta     ICAX2,x
              lda     #C_OPEN
              sta     ICCOM,x
              jsr     CIOV
              tya
              jmp     t_res

t_buf:        sta     ICBAL+IOCB1
              sty     ICBAH+IOCB1
              rts

t_xfer:       sta     ICBLL+IOCB1
              sty     ICBLH+IOCB1
              txa
              sta     ICCOM+IOCB1
              ldx     #IOCB1
              jsr     CIOV
              tya
              jmp     t_res

t_close1:     ldx     #IOCB1
              jsr     t_close
              tya
              jmp     t_res
t_close:      lda     #C_CLOSE
              sta     ICCOM,x
              jmp     CIOV

t_xio:        stx     ICCOM+IOCB1
              sta     ICBAL+IOCB1
              sty     ICBAH+IOCB1
              lda     #0
              sta     ICAX1+IOCB1
              sta     ICAX2+IOCB1
              ldx     #IOCB1
              jsr     CIOV
              tya
              ;; fall through

;;; A into RES+N, and N on.
t_res:        ldx     N
              sta     RES,x
              inc     N
              rts

nm_new:       .byte   "D1:NEW.DAT", EOL
nm_big:       .byte   "D1:BIG.DAT", EOL
nm_old:       .byte   "D1:OLD.TXT", EOL
nm_ren:       .byte   "D1:REN.TXT,RENAMED.TXT", EOL
nm_keep:      .byte   "D1:KEEP.DAT", EOL
nm_a:         .byte   "D1:A.X", EOL
nm_b:         .byte   "D1:B.X", EOL
nm_wild:      .byte   "D1:*.X", EOL
rec:          .byte   "HELLO", EOL
