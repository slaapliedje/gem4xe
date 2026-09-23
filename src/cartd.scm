;;; ---------------------------------------------------------------------------
;;; cartd.scm -- the cartridge's D: handler, linked where it RUNS.
;;;
;;; It travels in the cartridge and it runs in RAM, and those are two
;;; different addresses.  It cannot run from the cartridge: reading a file
;;; means switching a payload bank into $A000-$BFFF, which is where the
;;; handler would be (src/cart.s learned this for the copier).  And unlike
;;; the copier it is too big to write position-independently -- it has
;;; branches, tables and calls of its own -- so it is linked HERE, at the
;;; address it will run at, and carried as bytes.
;;;
;;; $0700 IS WHERE A DOS GOES.  gem4xe's map (src/gem4xe.scm) gives
;;; $0000-$1FFF to "the OS and DOS"; the engine starts at $2000 and the
;;; application pool at $4800.  This handler IS the DOS on a cartridge
;;; machine, so it takes the room a DOS would have taken and gem4xe needs
;;; to know nothing about it.
;;;
;;; The ceiling is $1FFF and the link enforces it.  A handler that grew
;;; past it would land on the engine's direct page and stack.
;;; ---------------------------------------------------------------------------

(define (cartd-layout)
  (list
    ;; THE ORDER SECTIONS ARE NAMED HERE IS NOT THE ORDER THEY ARE LAID
    ;; DOWN IN.  A fourth section, `devhead`, was added for the sixteen
    ;; bytes at $0700 that a DOS 2 would have owned -- $070A in them is
    ;; DRVBYT, which src/sys/gemdos.c's Drvmap returns -- and named first
    ;; here; the linker placed it LAST, at $0BA4, and the desktop would
    ;; have read an instruction as its list of drives.  What decides
    ;; placement is the fragments, and one `.section` directive is one
    ;; fragment: those bytes are at the top of `devcode` now (src/cartd.s)
    ;; and tools/mkcar.py checks the address rather than trusting either
    ;; story.
    ;;
    ;; ONE MEMORY, and the per-IOCB state is DATA rather than bss.  The
    ;; handler travels in the cartridge as a run of bytes and is copied
    ;; to $0700 whole, so a bss section would have been a hole in the
    ;; middle of it -- and asking the linker for one wants a data model
    ;; this bare 6502 handler does not have.  A hundred bytes of zeros
    ;; in a megabyte of ROM is the cheaper answer; cd_install sets the
    ;; one field that has to start at a particular value anyway.
    (list 'memory 'DevCode
          '(address (#x0700 . #x1fff))
          '(section devcode devdata cdata))))
