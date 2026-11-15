;;; gem6502.scm -- the 6502 build's memory (docs/6502.md).
;;;
;;; An XL/XE with BASIC off and a PORTB expansion.  Resident -- always
;;; mapped -- is $2000-$3FFF and $A000-$BFFF; $4000-$7FFF is the window;
;;; $8000-$9EFF is ANTIC's display list and screen (src/antic/antic.h),
;;; which nothing here may take.  Below $2000 is the DOS's.
;;;
;;; EACH BANK IS A MEMORY of its own at $4000-$7FFF, scattered to a store
;;; address the loader reads its bank number from: bank n at
;;; $10000 + (n-1) * $4000 (tools/bsp6502/mkxex6502.py).  A section names
;;; its bank, so what goes where is the source's choice, not the linker's
;;; packing -- and the --bank list given to tools/bsp6502/veneers.py must
;;; say the same.  tools/bsp6502/bankcheck.py reads the map this makes.
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80) zzpage zpage))
    (memory StackPage (address (#x100 . #x1ff)) (type ram) (section stack))
    (memory Low (address (#x2000 . #x3fff)) (type rom)
            (section veneer code switch cdata data_init_table idata reset))
    (memory HiText (address (#xa000 . #xb3ff)) (type rom)
            (section (hicdata #xa000) code switch cdata))
    (memory HiRam (address (#xb400 . #xbfff)) (type ram)
            (section b6keep data zdata cstack heap))
    ;; the page after ANTIC's screen, which ends at $9F00
    (memory ScreenTail (address (#x9f00 . #x9fff)) (type ram) (section zwin))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1)
            (section vdi_a))
    (memory Bank2 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store2)
            (section vdi_b))
    (memory Bank3 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store3)
            (section vdi_c))
    (memory Bank4 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store4)
            (section dev))
    (memory Bank5 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store5)
            (section antic))
    (memory Bank6 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store6)
            (section far))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (memory Store2 (address (#x14000 . #x17fff)) (section Store2))
    (memory Store3 (address (#x18000 . #x1bfff)) (section Store3))
    (memory Store4 (address (#x1c000 . #x1ffff)) (section Store4))
    (memory Store5 (address (#x20000 . #x23fff)) (section Store5))
    (memory Store6 (address (#x24000 . #x27fff)) (section Store6))
    (block cstack (size #x400))
    (block heap (size #x10))
    (block stack (size #x100))
    ))
