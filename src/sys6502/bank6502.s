;;; ---------------------------------------------------------------------------
;;; bank6502.s -- the PORTB window, owned by gem4xe (docs/6502.md).
;;;
;;; On a 6502 every bank is reached through $4000-$7FFF, switched by PORTB.
;;; Calypsi places code in a bank and calls it with a plain JSR to the
;;; window address, never switching anything, so this file is what does:
;;;
;;;   b6_probe   INITAD at load: which PORTB values give distinct banks.
;;;   b6_sel     INITAD at load: bank b6_next mapped, for the segment after.
;;;   b6_main    INITAD at load: main memory back in the window.
;;;   _bcall     the trampoline every veneer calls (tools/bsp6502/veneers.py):
;;;                  F:  jsr _bcall
;;;                      .word F__b      ; the function, at its window address
;;;                      .byte n         ; its bank
;;;              It maps bank n, calls F__b, maps the caller's bank again and
;;;              returns to F's caller.  A and the _Zp pseudo-registers pass
;;;              through both ways (Calypsi's arguments and results); X and Y
;;;              are a call's to destroy anyway.  Parameters that go on the C
;;;              stack are on Calypsi's virtual stack, not the 6502's, so the
;;;              two bytes this pushes there are nobody's business.
;;;
;;; ALL OF IT IS RESIDENT, below the window, and so is everything an
;;; interrupt runs: an IRQ arrives with any bank mapped.
;;;
;;; THE MAP IS FOUND, NOT ASSUMED.  Which PORTB bits select a bank depends on
;;; the board (a 130XE: bits 2-3; 1088K boards: 1, 2, 3, 5, 6, 7), and on a
;;; 130XE bit 1 clear is BASIC over $A000 and bit 7 clear the self-test ROM
;;; over $5000.  So every value with bit 4 (CPU bank enable) clear is tried,
;;; the safest first, and a value is kept only when what it maps is RAM
;;; across the window, the resident sentinel at $A000-$BFFF still reads, and
;;; no value kept before it maps the same bank.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel cpu, "*"

              .public b6_probe, b6_sel, b6_main, b6_next, _bcall, b6_report
              .public b6_cur, b6_count, b6_portb, bc_t, b6_kind, b6_sites
              .public b6sw_call, b6sw_ret, b6sw_sel, b6sw_main
              .public b6init_lo, b6init_hi, b6_stop
              .public bc_a, _bcall_go

PORTB:        .equ    0xd301
AXLON:        .equ    0xcfff          ; an Axlon's bank register (write only)
BANKMAX:      .equ    64              ; PORTB values tried, and its table
DOSVEC:       .equ    0x000a

              .section zpage, bss
bc_t:         .space  2               ; the callee, for JMP (bc_t)
bc_p:         .space  2               ; the veneer's data
bc_a:         .space  1               ; A across the switch
;;; the probe's own, while a PORTB value it tries is in: that value may
;;; map ROM over $A000-$BFFF, b6keep with it, so nothing there is read
;;; until main is back (a 130XE's BASIC; 1088K never showed it)
pr_m:         .space  1               ; main's PORTB
pr_n:         .space  1               ; banks kept so far

;;; NOINIT, not bss: b6_probe fills these during the load, before the C
;;; startup runs -- which zeroes bss, and with it the PORTB table, after
;;; which every veneer would map PORTB 0: the OS ROM out.
              .section b6keep, noinit
b6_cur:       .space  1               ; the bank mapped now: 0 is main
b6_count:     .space  1               ; banks found, main not counted
b6_kind:      .space  1               ; 'P' PORTB's banks, 'A' an Axlon's
b6_next:      .space  1               ; for b6_sel, written by the loader
b6_portb:     .space  BANKMAX + 1     ; PORTB for each bank, [0] main
pr_v:         .space  1
pr_k:         .space  1

;;; THE SENTINEL: a resident constant in $A000-$BFFF.  A PORTB value that
;;; puts BASIC (or anything) over it is not one to keep.
              .section hicdata, rodata
sentinel:     .byte   0x47, 0x34, 0x58, 0x45  ; "G4XE"

              .section code
;;; ---------------------------------------------------------------------------
;;; _bcall -- see the head of the file.
;;; ---------------------------------------------------------------------------
_bcall:       sta     bc_a
              pla                     ; JSR's return: the veneer's data - 1
              sta     bc_p
              pla
              sta     bc_p+1
              ldy     #1
              lda     (bc_p),y
              sta     bc_t
              iny
              lda     (bc_p),y
              sta     bc_t+1
              iny
              lda     (bc_p),y
              tax                     ; the bank to go to
;;; a bank's own veneer comes in here (tools/bsp6502/bankasm.py
;;; --fast-veneers): A in bc_a, the callee in bc_t, its bank in X, and on
;;; the stack only the return into the veneer's caller
_bcall_go:    lda     b6_cur          ; the caller's, on the 6502 stack under
              pha                     ; the return into the caller
              stx     b6_cur
b6sw_call:       lda     b6_portb,x
              sta     PORTB
              lda     bc_a
              jsr     bc_jmp          ; the call
              sta     bc_a
              pla
              tax
              stx     b6_cur
b6sw_ret:        lda     b6_portb,x
              sta     PORTB
              lda     bc_a
              rts                     ; to the veneer's caller
bc_jmp:       jmp     (bc_t)

;;; THE LOAD-TIME CODE -- the probe and the patch -- is in section b6init,
;;; which every link file puts in Low, below the window: a PORTB value tried
;;; may map ROM over $A000-$BFFF (the sentinel's check is for that), and
;;; code running there would vanish under it.
              .section b6init, root
;;; ...and dead once main runs, so a call's scratch may have its bytes
;;; then: the bounds, for src/sys6502/abistub6502.c's pool (step 5b-4)
              .section cdata, rodata
b6init_lo:    .word   .sectionStart b6init
b6init_hi:    .word   .sectionEnd b6init
              .section b6init, root
;;; ---------------------------------------------------------------------------
;;; b6_probe -- INITAD, before any bank's segment.  Fills b6_portb and
;;; b6_count.  Uses nothing of the C runtime: none of it is set up yet.
;;;
;;; Each candidate v: map it, write a pattern to $5000 and $7FFF and read it
;;; back, check the resident sentinel, and only then write its own index to
;;; $4000 and read it back.  Then the main bank's $4000 is
;;; checked for the main marker and every bank kept so far for its own
;;; index: a candidate that aliases one of them has overwritten it, and an
;;; earlier keeper overwritten means the earlier one is the duplicate --
;;; so the newest wins, which is why the candidates come safest LAST.
;;; ---------------------------------------------------------------------------
b6_probe:     lda     PORTB
              ora     #0x10           ; main: CPU sees main RAM
              sta     b6_portb
              sta     pr_m
              sta     PORTB
              lda     #0
              sta     AXLON           ; and an Axlon's bank 0, which is main
              sta     b6_count
              sta     pr_n
              sta     b6_cur
              lda     #'P'
              sta     b6_kind
              lda     #0xa5           ; main's marker
              sta     0x4000
              lda     #0              ; candidate counter k = 0..63
              sta     pr_k
20$:          jsr     cand            ; A = the PORTB value for k
              sta     pr_v
              sta     PORTB
              lda     #0x5a
              sta     0x5000
              lda     #0xc3
              sta     0x7fff
              lda     0x5000
              cmp     #0x5a
              bne     40$
              lda     0x7fff
              cmp     #0xc3
              bne     40$
              lda     sentinel        ; resident $A000-$BFFF still there?
              cmp     #0x47
              bne     40$
              lda     sentinel+3
              cmp     #0x45
              bne     40$
;;; Only now the index: a candidate refused above may map a bank already
;;; kept (on a board where bit 1 or 7 is not a bank bit, each bank answers
;;; to BASIC or the self test on and off), and its index written there
;;; would make the keeper look like a duplicate for dedup to drop.
              ldx     pr_n            ; the index this one would get
              inx
              stx     0x4000
              cpx     0x4000
              bne     40$
              lda     pr_m            ; main untouched?
              sta     PORTB
              lda     0x4000
              cmp     #0xa5
              bne     40$
              ldx     pr_n            ; keep it
              inx
              stx     b6_count
              lda     pr_v
              sta     b6_portb,x
              jsr     dedup           ; earlier keepers it overwrote go
              lda     b6_count
              sta     pr_n
40$:          lda     pr_m
              sta     PORTB
              lda     #0xa5           ; main's marker again, in case the
              sta     0x4000          ; candidate was main memory itself
              inc     pr_k
              lda     pr_k
              cmp     #BANKMAX
              bne     20$
              jsr     axprobe         ; X = an Axlon's banks, 0 for none
              cpx     b6_count
              beq     50$
              bcc     50$             ; PORTB's are as many: PORTB
              stx     b6_count
              lda     #'A'
              sta     b6_kind
              jmp     patch
50$:          rts

;;; axprobe -- an Axlon's banks, in X.  Its bank n is register value n,
;;; bank 0 main memory, and a value past its size aliases a smaller one.
;;; So 255 down to 1 each write their number at $4000 -- every alias
;;; first, the bank itself last -- and then 1 up are read back: the first
;;; that does not hold its own number, or whose $7FFF is not RAM, ends
;;; them.  Main's marker is written again (an alias of main took it), and
;;; must still be there when all is done.  With no Axlon the register is
;;; ROM, every write lands in main, and bank 1 reads main's marker: none.
axprobe:      ldx     #255
10$:          stx     AXLON
              stx     0x4000
              dex
              bne     10$
              stx     AXLON           ; 0: main
              lda     #0xa5
              sta     0x4000
              ldx     #1
20$:          stx     AXLON
              cpx     0x4000
              bne     30$
              lda     #0x3c
              sta     0x7fff
              cmp     0x7fff
              bne     30$
              inx
              bne     20$             ; past 255: all of them
30$:          dex                     ; the last that held
              lda     #0
              sta     AXLON
              lda     0x4000
              cmp     #0xa5
              beq     40$
              ldx     #0              ; main overwritten: not an Axlon
40$:          rts

;;; patch -- the machine is an Axlon's: every bank switch made one.  Each
;;; site (b6_sites, at the end of this file) is
;;;     lda b6_portb,x   (or ,y)     BD/B9 lo hi
;;;     sta PORTB                    8D 01 D3
;;; and becomes TXA (or TYA), NOP, NOP, STA AXLON: the bank's number IS
;;; the register's value, and PORTB stays main's.  A site that is not that
;;; stops the load with a word on the screen, as a missing bank does.
patch:        lda     #.byte0 b6_sites
              sta     bc_p
              lda     #.byte1 b6_sites
              sta     bc_p+1
10$:          ldy     #0
              lda     (bc_p),y
              sta     bc_t
              iny
              lda     (bc_p),y
              sta     bc_t+1
              bne     25$
              rts                     ; the zero after the last
25$:          dey
              lda     (bc_t),y
              ldx     #0x8a           ; TXA
              cmp     #0xbd
              beq     30$
              ldx     #0x98           ; TYA
              cmp     #0xb9
              bne     badsite
30$:          ldy     #3
              lda     (bc_t),y
              cmp     #0x8d
              bne     badsite
              iny
              lda     (bc_t),y
              cmp     #.byte0 PORTB
              bne     badsite
              iny
              lda     (bc_t),y
              cmp     #.byte1 PORTB
              bne     badsite
              ldy     #0
              txa
              sta     (bc_t),y
              lda     #0xea           ; NOP
              iny
              sta     (bc_t),y
              iny
              sta     (bc_t),y
              ldy     #4
              lda     #.byte0 AXLON
              sta     (bc_t),y
              iny
              lda     #.byte1 AXLON
              sta     (bc_t),y
              lda     bc_p
              clc
              adc     #2
              sta     bc_p
              bcc     10$
              inc     bc_p+1
              jmp     10$

badsite:      lda     #.byte0 sitemsg
              ldx     #.byte1 sitemsg
              ldy     #sitemsg_len
              jmp     stop

;;; cand -- the k-th candidate.  Bit 4 clear, bit 0 set (the OS stays);
;;; k's six bits spread over 1, 2, 3, 5, 6, 7, with 1 and 7 INVERTED so
;;; that k = 63 is the value with BASIC and the self-test off -- tried last
;;; and so the one kept on a 130XE.
cand:         lda     pr_k
              eor     #0x21           ; k bit 0 -> PORTB bit 1, k bit 5 -> 7
              tax
              lda     #0x01
              sta     pr_v
              txa
              and     #0x01
              beq     1$
              lda     pr_v
              ora     #0x02
              sta     pr_v
1$:           txa
              and     #0x02
              beq     2$
              lda     pr_v
              ora     #0x04
              sta     pr_v
2$:           txa
              and     #0x04
              beq     3$
              lda     pr_v
              ora     #0x08
              sta     pr_v
3$:           txa
              and     #0x08
              beq     4$
              lda     pr_v
              ora     #0x20
              sta     pr_v
4$:           txa
              and     #0x10
              beq     5$
              lda     pr_v
              ora     #0x40
              sta     pr_v
5$:           txa
              and     #0x20
              beq     6$
              lda     pr_v
              ora     #0x80
              sta     pr_v
6$:           lda     pr_v
              rts

;;; dedup -- the keeper just added is at b6_count.  Each earlier keeper is
;;; mapped and its $4000 read: not its own index any more means the new one
;;; aliases it, so the earlier one is dropped and the list closed up.
dedup:        ldx     #1
10$:          cpx     b6_count
              bcs     90$
              lda     b6_portb,x
              sta     PORTB
              txa
              cmp     0x4000
              beq     30$             ; still its own: a distinct bank
              ldy     b6_count        ; dropped: the newest takes its slot
              lda     b6_portb,y
              sta     b6_portb,x
              dey
              sty     b6_count
              lda     b6_portb,x      ; ...and is renumbered there
              sta     PORTB
              stx     0x4000
              jmp     10$
30$:          inx
              jmp     10$
90$:          lda     b6_portb
              sta     PORTB
              rts

              .section code
;;; ---------------------------------------------------------------------------
;;; b6_sel -- INITAD: bank b6_next in the window, for the segment that the
;;; loader puts after this.  A bank the machine does not have stops the load
;;; with a word on the screen, and back to DOS.
;;; ---------------------------------------------------------------------------
b6_sel:       ldx     b6_next
              cpx     b6_count
              beq     10$
              bcs     nobank
10$:          stx     b6_cur
b6sw_sel:        lda     b6_portb,x
              sta     PORTB
              rts

b6_main:      ldx     #0
              stx     b6_cur
b6sw_main:       lda     b6_portb,x
              sta     PORTB
              rts

nobank:       lda     #.byte0 nomsg
              ldx     #.byte1 nomsg
              ldy     #nomsg_len
;;; stop -- the message at X:A, Y bytes, on E:, and back to DOS
b6_stop:
stop:         sta     0x344
              stx     0x345
              sty     0x348
              jsr     b6_main
              ldx     #0              ; PUT RECORD on E:
              lda     #9
              sta     0x342
              lda     #0
              sta     0x349
              jsr     0xe456
              jmp     (DOSVEC)

;;; ---------------------------------------------------------------------------
;;; b6_report -- INITAD after b6_probe, when the loader is asked for it
;;; (tools/bsp6502/mkxex6502.py --report): "B6 nn pp pp pp pp" on E:, the
;;; banks found and the first PORTB values, before any bank is loaded --
;;; for a machine whose memory nothing can read (the MiSTer core).
;;; ---------------------------------------------------------------------------
b6_report:    lda     b6_count
              ldx     #3
              jsr     hexout
              ldy     #0
10$:          lda     b6_portb,y
              sty     pr_k
              tya
              asl     a
              asl     a
              asl     a
              adc     #6              ; "B6 nn " is 6, then 3 a value
              sec
              sbc     pr_k
              sbc     pr_k
              sbc     pr_k
              sbc     pr_k
              sbc     pr_k            ; = 6 + 3y
              tax
              lda     b6_portb,y
              jsr     hexout
              ldy     pr_k
              iny
              cpy     #4
              bne     10$
              ldx     #0
              lda     #9
              sta     0x342
              lda     #.byte0 repmsg
              sta     0x344
              lda     #.byte1 repmsg
              sta     0x345
              lda     #repmsg_len
              sta     0x348
              lda     #0
              sta     0x349
              jmp     0xe456

;;; two hex digits of A at repmsg+X
hexout:       pha
              lsr     a
              lsr     a
              lsr     a
              lsr     a
              jsr     10$
              sta     repmsg,x
              pla
              and     #15
              jsr     10$
              sta     repmsg+1,x
              rts
10$:          cmp     #10
              bcc     20$
              adc     #6              ; carry set: +7, 'A'-'0'-10
20$:          adc     #0x30
              rts

;;; in cdata, which the loader itself puts in place: `data` is copied there
;;; by the C startup, which has not run when this does
              .section cdata, rodata
repmsg:       .byte   "B6 nn pp pp pp pp", 0x9b
repmsg_len:   .equ    . - repmsg

              .section cdata, rodata
nomsg:        .byte   "NOT ENOUGH EXTENDED MEMORY", 0x9b
nomsg_len:    .equ    . - nomsg
sitemsg:      .byte   "AXLON: A BANK SWITCH NOT AS EXPECTED", 0x9b
sitemsg_len:  .equ    . - sitemsg

;;; EVERY BANK SWITCH there is, for patch (an Axlon's machine): each is a
;;; public label b6sw_* on a LDA b6_portb,X/Y then STA PORTB, in this file
;;; and in src/sys6502/cio6502.s, ctx6502.s and far6502.s.
;;; tools/bsp6502/mkxex6502.py writes each one's address here, in the
;;; image it loads, and a zero after -- having checked the bytes at each.
B6_SITES:     .equ    15
              .section cdata, rodata
b6_sites:     .space  2 * B6_SITES + 2
