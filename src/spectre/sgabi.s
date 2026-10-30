;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; sgabi.s -- Spectre GS: running a IIGS program, and its calls coming back.
;;;
;;; SG_RUN starts the program the way GS/OS does (GS/OS Reference, "GS/OS
;;; default stack and direct-page space"): A = its user ID, D = the bottom
;;; of its direct-page/stack space, S = the top.  Underneath its first
;;; return address is one into here, so a program that ends with `rtl`
;;; comes back too; one that quits comes back through sg_abort.
;;;
;;; SG_ENTRY is where `jsl $E10000` lands, through the `jml` Spectre GS
;;; puts at $E1:0000 (spectre.c).  The convention is the Toolbox's
;;; (Toolbox Reference, volume 1, "Return from a call", table 2-3): native
;;; mode, 16-bit registers, the call in X, the inputs on the stack above
;;; the caller's return address with room for any output above them.  On
;;; the way back the inputs are gone, D and DB are the caller's, and the
;;; carry and A say the error -- A = 0 and the carry clear if none.
;;;
;;; In between the call is served in C on the CALLER'S stack -- it lies in
;;; Spectre's own memory (spectre.c's arena), so gem4xe's rule that a
;;; program's stack stays in its own memory holds -- with Spectre's direct
;;; page and DB = $00 put back first, because that is what the compiler's
;;; code expects.  sg_tool gets the address of the caller's last input and
;;; sets sg_pop to how many bytes of inputs the call takes; the frame
;;; below them (D, DB, the return address) is slid up over them.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern sg_go, sg_prog_d, sg_prog_s, sg_userid, sg_my_d
              .extern sg_x, sg_pop, sg_why, sg_what
              .extern sgi_save_s, sgi_csp, sgi_err
              .extern sg_tool, sg_gsos
              .public sg_run, sg_entry, sg_entry2, sg_gsos_entry, sg_abort, sg_get_d

SG_UNTOOL     .equ    1
SG_RTL        .equ    3

              .section farcode

;;; uint16_t sg_get_d(void): Spectre's own direct page, for the dispatcher.
sg_get_d:     tdc
              rtl

;;; uint16_t sg_run(void): the program, until it quits or is stopped.
sg_run:       phb
              phd
              tsc
              sta     long:sgi_save_s
              lda     long:sg_prog_s
              tcs                     ; the program's stack
              lda     ##0
              pha
              plb                     ; DB = $00 ...
              plb                     ; ... as GS/OS leaves it
              phk                     ; an rtl from the program: sg_rtl
              lda     ##.word0 (sg_rtl - 1)
              pha
              sep     #0x20
              lda     long:sg_go + 2
              pha
              rep     #0x20
              lda     long:sg_go
              dec     a
              pha                     ; ...and an rtl to its entry, now
              lda     long:sg_prog_d
              tcd
              lda     long:sg_userid
              ldx     ##0
              ldy     ##0
              rtl

sg_rtl:       rep     #0x30
              sta     long:sg_what    ; what it left in A
              lda     ##SG_RTL
              sta     long:sg_why
sg_back:      rep     #0x30
              lda     long:sgi_save_s
              tcs                     ; Spectre's stack, as sg_run had it
              pld
              plb
              lda     long:sg_why
              rtl

;;; void sg_abort(uint16_t why): from anywhere inside a call, the run ends.
;;; Everything the program pushed is simply left behind, under sg_run's S.
sg_abort:     rep     #0x30
              sta     long:sg_why
              brl     sg_back

;;; jsl $E10000 -> jml sg_entry
sg_entry:     phb
              phd
              txa
              sta     long:sg_x
              tsc
              sta     long:sgi_csp    ; D at +1, DB at +3, return at +4
              lda     long:sg_my_d
              tcd
              lda     ##0
              pha
              plb
              plb                     ; DB = $00
              sta     abs:sg_pop
              lda     abs:sgi_csp
              clc
              adc     ##7             ; the caller's last input
              jsl     sg_tool
              sta     abs:sgi_err
              lda     abs:sg_pop
              beq     sg_e_out
              clc
              adc     abs:sgi_csp
              tay                     ; where the frame goes
              ldx     abs:sgi_csp     ; where it is: slide it up, top first
              lda     abs:5,x
              sta     abs:5,y
              lda     abs:3,x
              sta     abs:3,y
              lda     abs:1,x
              sta     abs:1,y
              tya
              tcs
sg_e_out:     pld
              plb
              lda     long:sgi_err
              cmp     ##1             ; carry set: an error
              rtl

;;; jsl $E10004 -> jml sg_entry2.  Not served yet: it stops the program,
;;; saying which call it was.
sg_entry2:    rep     #0x30
              txa
              sta     long:sg_what
              lda     ##SG_UNTOOL
              brl     sg_abort

;;; jsl $E100A8 -> jml sg_gsos_entry: GS/OS, the call number and the
;;; parameter block's address in the six bytes after the jsl.  sg_gsos
;;; gets the address of the return address, which it moves past them.
sg_gsos_entry:
              phb
              phd
              tsc
              sta     long:sgi_csp
              lda     long:sg_my_d
              tcd
              lda     ##0
              pha
              plb
              plb
              lda     abs:sgi_csp
              clc
              adc     ##4             ; the return address
              jsl     sg_gsos
              sta     abs:sgi_err
              pld
              plb
              lda     long:sgi_err
              cmp     ##1
              rtl
