;;; a6.scm -- step 4c's program: gem6502.scm's memory and six more banks
;;; (the window manager, the menus, the events and the control manager).
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
;; the top of Low as RAM, 2.75 KB of it -- the code shrank by 2.5 KB in
;; step 4a (veneers in the banks), and a page more when step 4d put the
;; context switch's C in a bank (the 6502's CTX is 4 bytes longer): what
;; the AES keeps in zwin (src/sys/zwin.h), the process records
;; (src/a6_aes.c) and the C stack, so that HiRam holds the rest of the
;; bss, which the linker keeps whole.  A section is placed in one memory
;; whole: zwin cannot spill into ScreenTail.
    ;; the page after ANTIC's screen, which ends at $9F00
    ;; and a buffer outside the window that CIO reads a program through
    ;; (src/a6_evt.c)
    (memory ScreenTail (address (#x9f00 . #x9fff)) (type ram) (section zwin bounce))
    (memory LowRam (address (#x3500 . #x3fff)) (type ram) (section zwin cstack))
    (memory Low (address (#x2000 . #x34ff)) (type rom)
            (section (gate #x2000) veneer b6init code switch cdata data_init_table idata reset))
    (memory HiText (address (#xa000 . #xb4df)) (type rom)
            (section (hicdata #xa000) code switch cdata))
    (memory HiRam (address (#xb4e0 . #xbfff)) (type ram)
            (section b6keep data zdata heap))
    ;; page 5 and the top of page 4, $0480-$05FF: the OS's user area and
    ;; the FP package's buffer, which nothing here uses and MyDOS leaves
    ;; zero (its own code is in $0400-$047F).  The A6 gate's records
    ;; (src/a6_evt.c), which gave HiText the 224 bytes GEMDOS's veneers
    ;; and tables needed (step 5b-4)
    (memory Page5 (address (#x480 . #x5ff)) (type ram) (section page5))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1)
            (section vdi_a vdi_a__bank))
    (memory Bank2 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store2)
            (section vdi_b vdi_b__bank))
    (memory Bank3 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store3)
            (section vdi_c vdi_c__bank))
    (memory Bank4 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store4)
            (section dev dev__bank))
    (memory Bank5 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store5)
            (section antic antic__bank))
    (memory Bank6 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store6)
            (section far far__bank))
    (memory Bank7 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store7)
            (section objc objc__bank))
    (memory Bank8 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store8)
            (section objc_b objc_b__bank))
    (memory Bank9 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store9)
            (section objc_c objc_c__bank))
    (memory Bank10 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store10)
            (section graf graf__bank))
    (memory Bank11 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store11)
            (section wind wind__bank))
    (memory Bank12 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store12)
            (section wind_b wind_b__bank))
    (memory Bank13 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store13)
            (section menu menu__bank))
    (memory Bank14 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store14)
            (section menu_b menu_b__bank))
    (memory Bank15 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store15)
            (section evt evt__bank))
    (memory Bank16 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store16)
            (section ctl ctl__bank))
    ;; src/sys/abi.c, the call gate's C (docs/6502.md, step 5)
    (memory Bank17 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store17)
            (section abi abi__bank))
    ;; src/aes/rsrc.c, the resource loader, and its variables (step 5b-3)
    (memory Bank18 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store18)
            (section rsrc rsrc__bank))
    ;; src/sys/gemdos.c in two, and dos.c, con.c, clock.c (step 5b-4)
    (memory Bank19 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store19)
            (section gemdos gemdos__bank))
    (memory Bank20 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store20)
            (section gemdos_b gemdos_b__bank))
    (memory Bank21 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store21)
            (section gdos gdos__bank))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (memory Store2 (address (#x14000 . #x17fff)) (section Store2))
    (memory Store3 (address (#x18000 . #x1bfff)) (section Store3))
    (memory Store4 (address (#x1c000 . #x1ffff)) (section Store4))
    (memory Store5 (address (#x20000 . #x23fff)) (section Store5))
    (memory Store6 (address (#x24000 . #x27fff)) (section Store6))
    (memory Store7 (address (#x28000 . #x2bfff)) (section Store7))
    (memory Store8 (address (#x2c000 . #x2ffff)) (section Store8))
    (memory Store9 (address (#x30000 . #x33fff)) (section Store9))
    (memory Store10 (address (#x34000 . #x37fff)) (section Store10))
    (memory Store11 (address (#x38000 . #x3bfff)) (section Store11))
    (memory Store12 (address (#x3c000 . #x3ffff)) (section Store12))
    (memory Store13 (address (#x40000 . #x43fff)) (section Store13))
    (memory Store14 (address (#x44000 . #x47fff)) (section Store14))
    (memory Store15 (address (#x48000 . #x4bfff)) (section Store15))
    (memory Store16 (address (#x4c000 . #x4ffff)) (section Store16))
    (memory Store17 (address (#x50000 . #x53fff)) (section Store17))
    (memory Store18 (address (#x54000 . #x57fff)) (section Store18))
    (memory Store19 (address (#x58000 . #x5bfff)) (section Store19))
    (memory Store20 (address (#x5c000 . #x5ffff)) (section Store20))
    (memory Store21 (address (#x60000 . #x63fff)) (section Store21))
    (block cstack (size #x400))
    (block heap (size #x10))
    (block stack (size #x100))
    ))
