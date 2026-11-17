;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; gemabi6502.s -- a 6502 application's three entry points into gem4xe
;;; (docs/6502.md, step 5).
;;;
;;; The 65C816's are COPs (gemabi.s); a 6502 has no software interrupt
;;; that a program may take, so these JUMP to the gate at $2000, the one
;;; address of gem4xe's a program knows, with the call's letter in A --
;;; the COP's signature byte, 'V', 'A' or 'D' -- and the parameter
;;; block's address where Calypsi puts a first pointer argument, _Zp0-1.
;;; The gate returns here's caller; A, X, Y and _Zp0-23 are undefined
;;; after, _Zp24-47 as they were: an ordinary call.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .public vdi_call, aes_call, dos_call

GATE:         .equ    0x2000          ; src/sys6502/gate6502.s

              .section code
vdi_call:     lda     #0x56
              jmp     GATE
aes_call:     lda     #0x41
              jmp     GATE
dos_call:     lda     #0x44
              jmp     GATE
