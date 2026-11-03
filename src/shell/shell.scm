;;; shell.scm -- G4DOS's shell (src/shell/shell.c), all of it in bank $00.
;;;
;;; G4DOS's loader puts it above G4DOS, which ends at $2000 (src/fdos.scm),
;;; and the OS's screen is at the top of the 48 KB with no cartridge in --
;;; G4DOS takes BASIC out -- its display list at $BC20.  Between the two,
;;; the shell: its direct page, then code, constants and data in one
;;; memory, its stack and the engine's cache among them.  Small code and
;;; data models both, so a FAR pointer the commands hand down is a bank-$00
;;; one, its low word the address (shell.c) -- and the far sections are put
;;; here by name, which `type any` alone does not do.
(define memories
  '((memory DirectPage (address (#x2000 . #x20ff))
            (section (registers ztiny)))
    (memory LoRAM (address (#x2100 . #xbbff))
            (type any)
            (section cfar far zfar ifar))
    (block stack (size #x0600))
    (base-address _DirectPageStart DirectPage 0)))
