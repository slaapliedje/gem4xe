;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; gemapp6502.scm -- linker rules for a 6502 gem4xe application
;;; (docs/6502.md, step 5).
;;;
;;; THE WHOLE PROGRAM IN ONE BANK: code, constants, the initial values of
;;; its data and the table that copies them, its data, its bss and its
;;; heap, all at $4000-$7FFF, which is where the window shows the bank the
;;; system loads it into.  crt6502.s's header first.
;;;
;;; ZERO PAGE IS THE SYSTEM'S except the pseudo-registers at $80, which
;;; the calling convention shares and which must sit where the system's
;;; do: a program that asks for zero page of its own does not link here.
;;; ITS C STACK IS ITS OWN, the top of the bank (crt6502.s says why);
;;; page 1 is the system's.
(define memories
  '((memory ZeroPage (address (#x80 . #xb5)) (type ram) (qualifier zpage)
            (section (registers #x80)))
    (memory Program (address (#x4000 . #x6fff)) (type rom)
            (section (header #x4000) code switch cdata data_init_table idata))
    (memory ProgramRam (address (#x7000 . #x7fff)) (type ram)
            (section data zdata heap cstack))
    (block cstack (size #x600))))
