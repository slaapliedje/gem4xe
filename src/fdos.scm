;;; ---------------------------------------------------------------------------
;;; fdos.scm -- the floppy's DOS, G4DOS (src/fdos.s), and its boot
;;; sectors (src/fdboot.s), each linked where it runs.
;;;
;;; G4DOS.SYS is the bytes from $0700 to fd_image_end: what src/fdboot.s
;;; reads to $0700 and nothing more.  Its variables and its five sector
;;; buffers are after it, in memories of their own at fixed addresses --
;;; a section's place in a memory is the linker's to choose, and fd_base
;;; has to be $0700 to the byte (tools/mkfloppy.py checks it) -- and MEMLO
;;; is the end of the buffers, $2000.  THAT IS THE CEILING: gem4xe's direct
;;; page is $2000 (src/gem4xe.scm), and nothing it loads is below $3000.
;;; A DOS 2.5 leaves MEMLO at $1CFC, a SpartaDOS 3.2 near $2000; SpartaDOS
;;; X leaves it at $1C1D, which is what gem4xe was measured under.  The
;;; three memories below are full to within a few dozen bytes: what G4DOS
;;; gains next has to come out of what it has (docs/fdos.md).
;;;
;;; The boot code is sectors 2 and 3, $3080-$317F, which the OS loads
;;; after sector 1's superblock, and sector 1's tail, $3030-$307F, past the
;;; superblock's fields: where a SpartaDOS keeps boot code too.
;;; ---------------------------------------------------------------------------

(define (fdos-layout)
  (list
    (list 'memory 'FdCode
          '(address (#x0700 . #x19a4))
          '(section fdcode))
    (list 'memory 'FdBss
          '(address (#x19a5 . #x1aff))
          '(section fdbss))
    (list 'memory 'FdBuf
          '(address (#x1b00 . #x1fff))
          '(section fdbuf))))

(define (fdboot-layout)
  (list
    (list 'memory 'Boot1
          '(address (#x3030 . #x307f))
          '(section boot1))
    (list 'memory 'BootCode
          '(address (#x3080 . #x317f))
          '(section bootcode))))

;;; tests/emu/fdwtest.s: the program test-fdosw has G4DOS's loader run in
;;; place of GEM.COM, above MEMLO and below the pattern at $4000.
(define (fdwtest-layout)
  (list
    (list 'memory 'TCode
          '(address (#x3000 . #x3fff))
          '(section tcode))))
