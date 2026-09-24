;;; ---------------------------------------------------------------------------
;;; cartd.scm -- the cartridge's D: handler, linked where it RUNS, which is
;;; where it rides: the boot bank, from $B004, behind its four-byte header.
;;;
;;; It used to be linked at $0700 and copied there -- the room a DOS would
;;; have taken on a machine with none.  That is exactly where a DOS lives on
;;; a machine that booted one, and the cartridge now shares D: with a DOS
;;; when there is one (src/cartd.s), so the code stays in the ROM and only
;;; its state and an eleven-byte fetch stub go down to page 6.  The boot
;;; bank is what the window shows whenever CIO calls a handler: every path
;;; that switches it puts it back before returning.
;;;
;;; The ceiling is $BFF9: $BFFA-$BFFF is the header the OS reads
;;; (src/cart.scm), and a handler that grew into it would turn the
;;; cartridge into one the machine boots straight past.  tools/mkcar.py
;;; checks the fit as well, and that the link starts where the header ends.
;;;
;;; ONE MEMORY, code and the directory together.  The directory is DATA in
;;; the ROM, patched by the packer at cd_dir and cd_dirlen; nothing in this
;;; link is writable at run time, and nothing is bss -- the state that is
;;; lives at fixed addresses in page 6, named in src/cartd.s.
;;; ---------------------------------------------------------------------------

(define (cartd-layout)
  (list
    (list 'memory 'DevCode
          '(address (#xb004 . #xbff9))
          '(section devcode devdata cdata))))
