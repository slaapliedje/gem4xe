;;; i6.scm -- step 4d's interrupt gate (src/i6_irq.c): one bank.
;;;
;;; A6's resident layout (tools/bsp6502/a6.scm), less the AES and the VDI:
;;; the runner and the handlers resident, src/vdi/pointer.c in bank 1.
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80) zzpage zpage))
    (memory StackPage (address (#x100 . #x1ff)) (type ram) (section stack))
    (memory LowRam (address (#x3600 . #x3fff)) (type ram) (section zwin cstack))
    (memory Low (address (#x2000 . #x35ff)) (type rom)
            (section veneer code switch cdata data_init_table idata reset))
    (memory HiText (address (#xa000 . #xb3ff)) (type rom)
            (section (hicdata #xa000) code switch cdata))
    (memory HiRam (address (#xb400 . #xbfff)) (type ram)
            (section b6keep data zdata heap))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1)
            (section dev))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (block cstack (size #x400))
    (block heap (size #x10))
    (block stack (size #x100))
    ))
