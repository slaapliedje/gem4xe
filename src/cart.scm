;;; ---------------------------------------------------------------------------
;;; cart.scm -- the cartridge window, $A000-$BFFF.
;;;
;;; A cartridge is not a program the linker places wherever it likes: it is
;;; 8,192 bytes at a fixed address whose last six are a header the OS reads
;;; before any of it runs.  So there are two memories and not one, and the
;;; header's is exactly six bytes long -- if the code grows into $BFFA the
;;; link fails rather than quietly overwriting the thing that says a
;;; cartridge is there.
;;;
;;; THE HEADER, which the OS reads at cold start (OS Manual, "Cartridges"):
;;;
;;;     $BFFA-$BFFB   CARTRUN  where to jump once the OS is up
;;;     $BFFC         0 means a cartridge IS here.  Non-zero means no
;;;                   cartridge, which is what the bus reads as when the
;;;                   slot is empty
;;;     $BFFD         flags: bit 0 boot a disk too, bit 2 jump to CARTRUN,
;;;                   bit 7 a diagnostic cartridge (jumped to BEFORE the
;;;                   OS initialises, which this is not)
;;;     $BFFE-$BFFF   CARTINI  called during OS init, before CARTRUN
;;;
;;; ONE BANK ONLY.  This maps the window, not the whole cartridge: a 1 MB
;;; AtariMax carries 128 of these and only one is visible at a time.  What
;;; is linked here is the bank that is mapped at RESET -- bank 127, which
;;; is where that mapper starts (Altirra, kATCartridgeMode_MaxFlash_1024K:
;;; InitBank(127, -1, 127)) -- so the bootstrap lives in it and the other
;;; 127 banks are payload the bootstrap switches in and reads.
;;; ---------------------------------------------------------------------------

(define (cart-layout)
  (list
    (list 'memory 'CartCode
          '(address (#xa000 . #xafff))
          '(section cartcode cartdata cdata))
    (list 'memory 'CartHdr
          '(address (#xbffa . #xbfff))
          '(section carthdr))))
