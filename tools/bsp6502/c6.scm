;;; c6.scm -- step 4d's context-switch gate (src/c6_ctx.c): three banks.
;;;
;;; A6's resident layout (tools/bsp6502/a6.scm), less the AES: bank 1 the
;;; far heap's allocator (src/sys/farmem.c), banks 2 and 3 the two
;;; contexts' programs (src/c6_procs.c), the heap in the banks after.
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80) zzpage zpage))
    (memory StackPage (address (#x100 . #x1ff)) (type ram) (section stack))
    (memory LowRam (address (#x3600 . #x3fff)) (type ram) (section zwin cstack))
    (memory Low (address (#x2000 . #x35ff)) (type rom)
            (section veneer b6init code switch cdata data_init_table idata reset))
    (memory HiText (address (#xa000 . #xb3ff)) (type rom)
            (section (hicdata #xa000) code switch cdata))
    (memory HiRam (address (#xb400 . #xbfff)) (type ram)
            (section b6keep data zdata heap))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1)
            (section far))
    (memory Bank2 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store2)
            (section cxa))
    (memory Bank3 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store3)
            (section cxb))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (memory Store2 (address (#x14000 . #x17fff)) (section Store2))
    (memory Store3 (address (#x18000 . #x1bfff)) (section Store3))
    (block cstack (size #x400))
    (block heap (size #x10))
    (block stack (size #x100))
    ))
