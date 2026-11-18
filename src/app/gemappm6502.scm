;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; gemappm6502.scm -- linker rules for a 6502 gem4xe application of
;;; several banks (docs/6502.md, step 5c-1); gemapp6502.scm is a one-bank
;;; program's.
;;;
;;; ITS CODE IN BANKS 1..8 here, a program using as many as it fills, each at $4000-$7FFF, stored at $10000 +
;;; (k-1) * $4000 as the system's link stores its banks: a program's C
;;; puts a function in bank k with `#pragma clang section text="pbK"` or
;;; BANK_TEXT("pbK") (src/portab.h), and tools/bsp6502/bankasm.py
;;; --trampoline _pcall sends every call across through a veneer.  Bank 1
;;; begins with the header (src/app/crt6502m.s).  More banks: more lines,
;;; up to 15 (the link block's g6_banks).
;;;
;;; EVERYTHING ELSE IN THE RAM UNDER THE OS ROM, which the system runs
;;; with in (src/a6_tree.c): the link block the loader fills at $C000,
;;; then the veneers, the runtime's code and the constants to $CFFF;
;;; $D000-$D7FF is the chips; data, bss, heap and the C stack from $D800
;;; to $FDFF.  $FE00-$FFFF is the system's: the OS key table, copied to
;;; $FE00, and the interrupt vectors (src/a6_tree.c).  Zero page is the system's but for
;;; the pseudo-registers at $80-$B5, as for a one-bank program -- the
;;; memory ends there, so a program's zero-page variable fails the link
;;; rather than landing on the system's.
(define memories
  '((memory ZeroPage (address (#x80 . #xb5)) (type ram) (qualifier zpage)
            (section (registers #x80)))
    (memory Link (address (#xc000 . #xc01f)) (type ram)
            (section (g6link #xc000)))
    (memory Shared (address (#xc020 . #xcfff)) (type rom)
            (section veneer code switch cdata data_init_table idata))
    (memory SharedRam (address (#xd800 . #xfdff)) (type ram)
            (section data zdata heap cstack))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1)
            (section (g6start #x4000) pb1 pb1__bank))
    (memory Bank2 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store2)
            (section pb2 pb2__bank))
    (memory Bank3 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store3)
            (section pb3 pb3__bank))
    (memory Bank4 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store4)
            (section pb4 pb4__bank))
    (memory Bank5 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store5)
            (section pb5 pb5__bank))
    (memory Bank6 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store6)
            (section pb6 pb6__bank))
    (memory Bank7 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store7)
            (section pb7 pb7__bank))
    (memory Bank8 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store8)
            (section pb8 pb8__bank))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (memory Store2 (address (#x14000 . #x17fff)) (section Store2))
    (memory Store3 (address (#x18000 . #x1bfff)) (section Store3))
    (memory Store4 (address (#x1c000 . #x1ffff)) (section Store4))
    (memory Store5 (address (#x20000 . #x23fff)) (section Store5))
    (memory Store6 (address (#x24000 . #x27fff)) (section Store6))
    (memory Store7 (address (#x28000 . #x2bfff)) (section Store7))
    (memory Store8 (address (#x2c000 . #x2ffff)) (section Store8))
    (block cstack (size #x400))))
