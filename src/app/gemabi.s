;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; gemabi.s -- an application's three entry points into gem4xe.
;;;
;;; The whole binding is a software interrupt.  Calypsi's __simple_call puts
;;; a far-pointer first argument in X (bank) : C (low 16 bits), and that is
;;; where gem4xe's COP handler (src/sys/abi.s) takes the parameter block
;;; from; the byte after COP says which manager is wanted, as a letter: #$56
;;; 'V' the VDI, #$41 'A' the AES, #$44 'D' GEMDOS (src/sys/abi.h).  They
;;; are in $02-$7F because the rest is taken: $00 and $01 are Rapidus OS's
;;; and its SpartaDOS X modules', and $80-$FF are WDC's, reserved for new
;;; instructions.  Nothing here knows an address of gem4xe's: the COP
;;; vector is in the OS's RAM shadow, which gem4xe fills.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel core, "*"
              .public vdi_call, aes_call, dos_call

              .section farcode
vdi_call:     cop     #0x56
              rtl
aes_call:     cop     #0x41
              rtl
dos_call:     cop     #0x44
              rtl
