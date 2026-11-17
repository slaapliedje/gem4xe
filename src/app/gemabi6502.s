;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; gemabi6502.s -- a 6502 application's three entry points into gem4xe
;;; (docs/6502.md, step 5).
;;;
;;; The 65C816's are COPs (gemabi.s); a 6502 has no software interrupt
;;; that a program may take, so these call the gate at $2000, the one
;;; address of gem4xe's a program knows, with the call's letter in A --
;;; the COP's signature byte, 'V', 'A' or 'D', and the 6502's own 'F' --
;;; and the parameter block's address where Calypsi puts a first pointer
;;; argument, _Zp0-1.  A, X, Y and _Zp0-23 are undefined after, _Zp24-47
;;; as they were: an ordinary call.
;;;
;;; ON THE SYSTEM'S C STACK (step 5b-3): the program's own is in its bank
;;; (crt6502.s), which the system's banks cannot see, so for the call
;;; _Vsp is the system's, kept at start in g6_sysvsp, and the program's
;;; comes back after.  One process to a program, and one call at a time:
;;; a place in the bank is enough to keep it in.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .public vdi_call, aes_call, dos_call, far_call
              .extern _Vsp, g6_sysvsp

GATE:         .equ    0x2000          ; src/sys6502/gate6502.s

              .section zdata, bss
g6_prvsp:     .space  2               ; the program's _Vsp across a call

              .section code
vdi_call:     lda     #0x56
              bne     g6
aes_call:     lda     #0x41
              bne     g6
dos_call:     lda     #0x44
              bne     g6
;;; far_fetch and far_store's (src/app/gemlib.c): 'F', the 6502's own,
;;; with its five-word block where the others have their parameter block
far_call:     lda     #0x46
g6:           tay                     ; the letter, across the swap
              lda     zp:_Vsp
              sta     g6_prvsp
              lda     zp:_Vsp+1
              sta     g6_prvsp+1
              lda     g6_sysvsp
              sta     zp:_Vsp
              lda     g6_sysvsp+1
              sta     zp:_Vsp+1
              tya
              jsr     GATE
              lda     g6_prvsp
              sta     zp:_Vsp
              lda     g6_prvsp+1
              sta     zp:_Vsp+1
              rts
