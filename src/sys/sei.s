;;; ---------------------------------------------------------------------------
;;; sei.s -- interrupts off in native mode, WITHOUT an SEI (65C816)
;;;
;;; Windows Altirra's 65C816 (to 4.50-test21 at least; AltirraSDL has the
;;; fix since PR #88, tools/altirra/README.md) lets the one IRQ through
;;; that arrives as an SEI, SEP or PLP sets I -- as a 6502 does -- and in
;;; native mode never forgets that it did: the IRQ is taken again at the
;;; handler's first fetch, and every fetch after, until the stack has
;;; wrapped through bank $00.  With timer 1 at 4 kHz that is a matter of
;;; seconds to minutes, and it was the cartridge's crash on AtariAge after
;;; 0.9.2 (docs/phase82.md).
;;;
;;; An INTERRUPT sets I without that shadow.  So irq_sei makes a COP from
;;; one address, irq_sei_ret, and irq_cop -- where src/sys/irq.s's COP
;;; vector goes -- knows it by the return address the CPU pushed, all 24
;;; bits, and returns with I set in the P its RTI pulls.  Any other COP
;;; goes on to gem_cop (src/sys/abi.s, or a gate's stub) exactly as it
;;; came.  About 60 cycles against an SEI's two.
;;;
;;; A file of its own because every program that runs with interrupts
;;; links it, and they link different halves of the rest: m27 has abi.s
;;; and no irq.s, m30 irq.s and cio.s and no abi.s.
;;; tests/host/test_sei.py keeps SEI out of native-mode code.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern gem_cop
              .public irq_sei, irq_cop

              .section farcode, root

;;; ---------------------------------------------------------------------------
;;; irq_sei -- a far subroutine; every register, both widths and the flags
;;; come back as they went in, with I set.  C reaches it as cpu_sei()
;;; (src/portab.h).  With I already set -- which is how gem4xe runs before
;;; irq_install, when $FFE4 is not yet its COP vector -- nothing is done
;;; and no COP is made.
;;; ---------------------------------------------------------------------------
irq_sei:      php
              rep     #0x20
              pha
              lda     3,s             ; the caller's P
              and     ##0x0004
              bne     irq_sei_on
              pla
              plp                     ; I clear before and after: no shadow
              cop     #0x49
irq_sei_ret:  rtl
irq_sei_on:   pla
              plp
              rtl

irq_sei_key:  .long   irq_sei_ret     ; what irq_cop compares, 24 bits,
                                      ; read long: DB is the caller's there

;;; ---------------------------------------------------------------------------
;;; irq_cop -- every native COP, first.  Nothing saved or written before
;;; the test, since irq_sei is called from inside ABI calls too.
;;; ---------------------------------------------------------------------------
irq_cop:      rep     #0x30
              pha
;;; 1,s A   3,s P   4,s PC   6,s PB
              lda     4,s
              cmp     long:irq_sei_key
              bne     irq_cop_on
              lda     5,s
              cmp     long:irq_sei_key+1
              bne     irq_cop_on
              sep     #0x20
              lda     3,s
              ora     #0x04           ; the RTI sets I: no SEI, no shadow
              sta     3,s
              rep     #0x20
              pla
              rti
irq_cop_on:   pla                     ; gem_cop reads the caller's widths
              jmp     long:gem_cop    ; from the P in the frame, not M, X
