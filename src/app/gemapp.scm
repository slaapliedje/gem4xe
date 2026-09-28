;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; gemapp.scm -- linker rules for a gem4xe application.
;;;
;;; An application is linked at PLACEHOLDER addresses and relocated by the
;;; loader: its near region -- direct page, stack, data -- to a page-aligned
;;; slice of gem4xe's application pool in bank $00, and its far region --
;;; the code -- to a bank of the far heap.  tools/mkg4a.py links the program
;;; three times, once here and once with each region shifted (a page, a
;;; bank), and the bytes that moved are the fixups; so the placeholders
;;; below are never seen at run time, and nothing in the program may depend
;;; on them.  The near region is one page for the direct page, then what
;;; carries no bits (the stack, data, zdata) and then what does (constants,
;;; the initial values of data, the init table): the linker will not mix the
;;; two kinds in one memory, and the loader wants one extent, so the split
;;; is fixed here.  The loader relocates by pages, which is why the direct
;;; page -- the only thing whose low byte matters -- sits at a page boundary.
;;;
;;; The sizes are the application's budget: a near region of a page of
;;; direct page plus `bss` bytes without bits plus `bits` bytes with, out
;;; of gem4xe's pool (src/gem4xe.scm), and one bank of code.  All are
;;; limits the link enforces and the loader checks again against what it
;;; has.  The gate application (src/m11_app.c) links with 2 KB and 256
;;; bytes; the desktop asks for more, and the loader never sees the
;;; difference -- it reads the extent from the file's header, rounded up
;;; to whole pages (tools/mkg4a.py), since the loader relocates by pages;
;;; page multiples here waste none of it.  The stack's share of `bss` is
;;; the link's --stack-size (the Makefile's g4a macro), over the 256
;;; bytes below: the desktop's calls nest deeper than the gate
;;; application's and ran that out (phase 14, milestone 5).

;;; (1 2 ... n), because this Scheme has no iota.
(define (upto n)
  (if (= n 0) '() (append (upto (- n 1)) (list n))))

;;; The far VARIABLES, in the banks ABOVE the code -- because the linker
;;; will not put sections that carry bits and sections that do not in one
;;; memory, and `far`/`zfar` carry none: they are made at start-up, `zfar`
;;; zeroed and `far` copied from `ifar` by the crt's data_init_table walk.
;;; Banks of their own also mean an application's data can grow without
;;; moving its code.
;;;
;;; ONE MEMORY PER BANK, and NOT one memory spanning them, which is what
;;; this was for an afternoon.  A FAR POINTER'S ARITHMETIC IS SIXTEEN BITS
;;; on this compiler -- `p + n` adds to the offset and leaves the bank byte
;;; alone, so a walk off the top of a bank comes back at its bottom
;;; (src/sys/farmem.c carries the generated code, and the manual agrees
;;; obliquely by capping a `far` OBJECT at 64K minus one byte).  So NO
;;; OBJECT MAY STRADDLE A BANK, and a memory that spans three gives the
;;; linker no reason not to let one.  It let one: GACS's 22 KB component
;;; table landed at $04EE7E-$053221, and reading it would have wrapped
;;; back into the middle of its own arena partway through, quietly, with
;;; every published figure wrong in a way no compile could see.
;;;
;;; The cost of getting it right is real and lands on the APPLICATION: the
;;; linker places a section fragment whole, and a compilation unit's `zfar`
;;; is ONE fragment, so a program with more than a bank of statics in one
;;; .c file cannot be placed at all.  It has to spread them over several,
;;; which is what GACS's shell does (shells/gem/store*.c).  That is a
;;; better failure than the alternative: it is a link error rather than a
;;; wrong number on a record sheet.
;;;
;;; HOW MANY is the application's business and has to be told, not guessed.
;;; The count reaches the loader through the .G4A header, where
;;; tools/mkg4a.py takes it from the linker's MAP -- the far variables
;;; carry no bytes and are nowhere in the image, so a count taken from the
;;; image alone would leave them in memory the far heap goes on to hand
;;; somebody else.  Defaults of one, so m29_big, m31_huge, the desktop and
;;; the two accessories are unchanged.
;;;
;;; Each bank stops below $D500 like the code banks do.  For CODE that page
;;; is mandatory (gem4xe.scm, THE HOLE); data is never branched to and has
;;; no such hazard, so this is caution rather than necessity.  It costs
;;; 11 KB a bank out of a 14 MB far heap.
;;; A BANK IS NAMED, NOT JUST COUNTED, and that is the second half of the
;;; same fact.  The linker places a section fragment whole, and it does not
;;; SPLIT a bss section across memories the way it splits `farcode` -- that
;;; one is a fragment per function and spills bank to bank happily, while
;;; `zfar` arrives as one unit per compilation unit and, offered three
;;; memories of 54,528, coalesces and fails to fit any of them.
;;;
;;; So bank 1 takes `zfar`, which is where the compiler puts a static by
;;; default, and bank 2 upward take `zfar2`, `zfar3` and so on -- names an
;;; application asks for explicitly, one line per file:
;;;
;;;     #pragma clang section bss="zfar2"
;;;
;;; That makes the split the PROGRAMMER's, said out loud in the file whose
;;; storage it is, rather than a placement the linker guesses at.  It is
;;; also the only arrangement in which the rule above -- no object may
;;; straddle a bank -- is kept by construction: every memory is inside one
;;; bank, so nothing the linker does can violate it.
;;;
;;; Initialised far data (`far`, and the `ifar` it is copied from) stays in
;;; bank 1 alone.  Giving banks 2+ their own would need a matching
;;; initialiser section each and a crt walk that knew about them, for a
;;; kind of data that is a few hundred bytes even in the largest program
;;; here.  A program that manages to overflow it will get a link error.
(define (app-far-bss base0 n)
  (map (lambda (b)
         (let ((base (+ base0 (* (- b 1) #x10000)))
               (bss (if (= b 1) 'zfar
                        (string->symbol (string-append
                                          "zfar" (number->string b 10))))))
           (list 'memory
                 (string->symbol (string-append "AppFarBss"
                                                (number->string b 10)))
                 (list 'address (cons base (+ base #xd4ff)))
                 (if (= b 1)
                     (list 'section 'far bss)
                     (list 'section bss)))))
       (upto n)))

;;; The CODE, and its constants.  Two memories per bank, either side of the
;;; $D5 page, for the reason gem4xe.scm's own far-bank has them: Altirra
;;; gives a taken branch a page-crossing read folded into bank $00, and
;;; $D5xx there is cartridge control, so no code is placed in that page of
;;; any bank (THE HOLE).  The system's code has spanned banks since it was
;;; written; an application's could not until an application needed it to.
(define (app-far-code far n)
  (apply append
    (map (lambda (b)
           (let ((base (+ far (* (- b 1) #x10000)))
                 (name (string-append "AppFar" (number->string b 10))))
             (list
               (list 'memory (string->symbol name)
                     (list 'address (cons base (+ base #xd4ff)))
                     '(section farcode switch cfar libcode code ifar))
               (list 'memory (string->symbol (string-append name "h"))
                     (list 'address (cons (+ base #xd600) (+ base #xffff)))
                     '(section farcode switch cfar libcode code ifar)))))
         (upto n))))

;;; One bank of code and one of far variables, which is what every program
;;; in this tree but GACS's shell needs.  More of either: app-layout-n.
(define (app-layout near far bss bits)
  (app-layout-n near far bss bits 1 1))

(define (app-layout-n near far bss bits cbanks fbanks)
  (append
  (list
    (list 'memory 'AppDP
          (list 'address (cons near (+ near #xff)))
          '(section (registers ztiny)))
    ;; `near`, `znear` and `inear` are the bank-$00 sections of a program
    ;; compiled --data-model=LARGE: there, a global goes far unless it is
    ;; declared __near, and a program that hands the AES a tree or a
    ;; string must declare those, since the ABI takes only bank $00
    ;; (src/sys/abi.c, near_of).  A small-data program has none of them
    ;; and loses nothing by their being named.
    (list 'memory 'AppBss
          (list 'address (cons (+ near #x100) (+ near #xff bss)))
          '(section stack data zdata heap near znear))
    (list 'memory 'AppBits
          (list 'address (cons (+ near #x100 bss) (+ near #xff bss bits)))
          '(section cdata idata data_init_table inear))
    ;; Two far memories, either side of the bank's $D5 page: the emulator's
    ;; native-mode branch reads a wrong-page address folded into bank $00,
    ;; and $D5xx there is cartridge control (src/gem4xe.scm, THE HOLE).
    ;;
    ;; `far` and `zfar` are here for an application compiled
    ;; --data-model=LARGE, where a pointer is 24 bits and the compiler puts
    ;; every global up here instead of in bank $00.  That is the model the
    ;; two programs this project exists for are written to (docs/gacs.md):
    ;; GACS's tables are 22 KB and its sheet another 33, against the 2 KB
    ;; of bank $00 an application gets, so its engine works out of far
    ;; memory -- and it already does, because its own first rule is that a
    ;; shell hands the engine a buffer.  A small-data application has
    ;; neither section and loses nothing by their being named.
    ;;
    ;; `far` carries bits, `zfar` does not, and `ifar` is the INITIALISER
    ;; for `far` -- the bytes the crt's data_init_table walk copies into
    ;; it at start-up, which the linker emits and which has to be placed
    ;; or the link stops with "Failed to place 'ifar'".  That is how this
    ;; list was found to be short: by trying it.
    ;;
    ;; Unlike the near region there is no loader constraint that the
    ;; bits and the no-bits sections be one extent, since the whole bank
    ;; moves together and the fixups are per address.  So all three go in
    ;; both memories and the linker decides.
    )
  (app-far-code far cbanks)
  (app-far-bss (+ far (* cbanks #x10000)) fbanks)
  (list
    '(block stack (size #x0100))
    '(block heap  (size #x0000))
    '(base-address _DirectPageStart AppDP 0)
    ;; Where a __near variable is addressed from, and it is ZERO.
    ;;
    ;; A large-data program reaches near data as `stx .near sym`, which
    ;; the assembler turns into the absolute address `sym -
    ;; _NearBaseAddress` with DB naming the bank.  The crt sets DB = $00
    ;; and the loader relocates bank-$00 addresses by pages, so the
    ;; offsets have to BE those addresses: the base is the bottom of the
    ;; bank, not the bottom of the program's data.
    ;;
    ;; Naming AppBss here instead cost an afternoon and looked like
    ;; anything but what it was.  Every near access became an offset from
    ;; $1100 -- so the first store in main went to $0000, the program
    ;; scribbled the OS's zero page and wedged before it reached its own
    ;; first statement, and the give-away was in the .G4A header all
    ;; along: near page fixups fell from fourteen to one, because an
    ;; offset needs no relocating and an address does.
    ;; Computed from `near` rather than written as a constant, because
    ;; mkg4a links three times and one of those moves the near region up
    ;; a page: a fixed offset would put the base at $0100 in that link,
    ;; the addresses would differ from the base link's for a reason that
    ;; is not relocation, and every near byte would look like a fixup.
    (list 'base-address '_NearBaseAddress 'AppDP (- near)))))

(define memories (app-layout #x1000 #x020000 #x800 #x100))
