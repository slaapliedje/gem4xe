;;; eput6502.s -- e_puts(line): a line on the OS's screen editor, E:
;;; (IOCB 0, PUT RECORD), for a 6502 test program to say what it found
;;; where only a screenshot can read it -- on the MiSTer, say.  The line
;;; ends with an EOL ($9B); at most 120 bytes go.  The pointer comes in
;;; _Zp, as Calypsi passes it.  Resident.

              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .extern _Zp
              .public e_puts

ICCOM:        .equ    0x342
ICBAL:        .equ    0x344
ICBLL:        .equ    0x348
CIOV:         .equ    0xe456

              .section code
e_puts:       ldx     #0
              lda     #9              ; PUT RECORD
              sta     ICCOM
              lda     zp:_Zp
              sta     ICBAL
              lda     zp:_Zp+1
              sta     ICBAL+1
              lda     #120
              sta     ICBLL
              lda     #0
              sta     ICBLL+1
              jmp     CIOV
