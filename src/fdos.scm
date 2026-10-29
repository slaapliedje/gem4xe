;;; ---------------------------------------------------------------------------
;;; fdos.scm -- the floppy's read-only DOS (src/fdos.s) and its boot
;;; sectors (src/fdboot.s), each linked where it runs.
;;;
;;; G4DOS.SYS is the bytes from $0700 to fd_image_end: what src/fdboot.s
;;; reads to $0700 and nothing more.  Its variables and its two sector
;;; buffers are after it, in memories of their own at fixed addresses --
;;; a section's place in a memory is the linker's to choose, and fd_base
;;; has to be $0700 to the byte (tools/mkfloppy.py checks it) -- and MEMLO
;;; is the end of the buffers, $1700.  gem4xe runs with MEMLO as high as
;;; $1C1D under SpartaDOS X; nothing it loads is below $3000.
;;;
;;; The boot code is sectors 2 and 3, $3080-$317F, which the OS loads
;;; after sector 1's superblock, and sector 1's tail, $3030-$307F, past the
;;; superblock's fields: where a SpartaDOS keeps boot code too.
;;; ---------------------------------------------------------------------------

(define (fdos-layout)
  (list
    (list 'memory 'FdCode
          '(address (#x0700 . #x13ff))
          '(section fdcode))
    (list 'memory 'FdBss
          '(address (#x1400 . #x14ff))
          '(section fdbss))
    (list 'memory 'FdBuf
          '(address (#x1500 . #x16ff))
          '(section fdbuf))))

(define (fdboot-layout)
  (list
    (list 'memory 'Boot1
          '(address (#x3030 . #x307f))
          '(section boot1))
    (list 'memory 'BootCode
          '(address (#x3080 . #x317f))
          '(section bootcode))))
