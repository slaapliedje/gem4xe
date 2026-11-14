;;; ---------------------------------------------------------------------------
;;; run8.scm -- the stub that runs a plain Atari program after GEM on DOS 2
;;; and MyDOS (src/run8.s), linked where it runs: $0400, the cassette buffer,
;;; and the free bytes after it up to BASIC's line buffer at $0580, with
;;; what runs only once in that buffer.  GEM.COM carries it as bytes
;;; (tools/run8stub.py) and copies it there as it ends.
;;; ---------------------------------------------------------------------------

(define (run8-layout)
  (list
    (list 'memory 'Run8
          '(address (#x0400 . #x057f))
          '(section run8))
    ;; what runs once, before the program or the cartridge: BASIC's line
    ;; buffer, which BASIC uses only once it is running
    (list 'memory 'Run8Go
          '(address (#x0580 . #x05ff))
          '(section run8go))))
