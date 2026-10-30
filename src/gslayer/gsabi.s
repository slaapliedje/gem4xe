;;; SPDX-License-Identifier: LGPL-2.1-or-later
;;; ---------------------------------------------------------------------------
;;; gsabi.s -- GSlayer: running a IIGS program, and its calls coming back.
;;;
;;; GS_RUN starts the program the way GS/OS does (GS/OS Reference, "GS/OS
;;; default stack and direct-page space"): A = its user ID, D = the bottom
;;; of its direct-page/stack space, S = the top.  Underneath its first
;;; return address is one into here, so a program that ends with `rtl`
;;; comes back too; one that quits comes back through gs_abort.
;;;
;;; GS_ENTRY is where `jsl $E10000` lands, through the `jml` GSlayer
;;; puts at $E1:0000 (gslayer.c).  The convention is the Toolbox's
;;; (Toolbox Reference, volume 1, "Return from a call", table 2-3): native
;;; mode, 16-bit registers, the call in X, the inputs on the stack above
;;; the caller's return address with room for any output above them.  On
;;; the way back the inputs are gone, D and DB are the caller's, and the
;;; carry and A say the error -- A = 0 and the carry clear if none.
;;;
;;; In between the call is served in C on the CALLER'S stack -- it lies in
;;; GSlayer's own memory (gslayer.c's arena), so gem4xe's rule that a
;;; program's stack stays in its own memory holds -- with GSlayer's direct
;;; page and DB = $00 put back first, because that is what the compiler's
;;; code expects.  gs_tool gets the address of the caller's last input and
;;; sets gs_pop to how many bytes of inputs the call takes; the frame
;;; below them (D, DB, the return address) is slid up over them.
;;; ---------------------------------------------------------------------------
              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern gs_go, gs_prog_d, gs_prog_s, gs_userid, gs_my_d
              .extern gs_x, gs_pop, gs_why, gs_what
              .extern gsi_save_s, gsi_csp, gsi_err
              .extern gs_tool, gs_gsos
              .public gs_run, gs_entry, gs_entry2, gs_gsos_entry, gs_abort, gs_get_d

GS_UNTOOL     .equ    1
GS_RTL        .equ    3

              .section farcode

;;; uint16_t gs_get_d(void): GSlayer's own direct page, for the dispatcher.
gs_get_d:     tdc
              rtl

;;; uint16_t gs_run(void): the program, until it quits or is stopped.
gs_run:       phb
              phd
              tsc
              sta     long:gsi_save_s
              lda     long:gs_prog_s
              tcs                     ; the program's stack
              lda     ##0
              pha
              plb                     ; DB = $00 ...
              plb                     ; ... as GS/OS leaves it
              phk                     ; an rtl from the program: gs_rtl
              lda     ##.word0 (gs_rtl - 1)
              pha
              sep     #0x20
              lda     long:gs_go + 2
              pha
              rep     #0x20
              lda     long:gs_go
              dec     a
              pha                     ; ...and an rtl to its entry, now
              lda     long:gs_prog_d
              tcd
              lda     long:gs_userid
              ldx     ##0
              ldy     ##0
              rtl

gs_rtl:       rep     #0x30
              sta     long:gs_what    ; what it left in A
              lda     ##GS_RTL
              sta     long:gs_why
gs_back:      rep     #0x30
              lda     long:gsi_save_s
              tcs                     ; GSlayer's stack, as gs_run had it
              pld
              plb
              lda     long:gs_why
              rtl

;;; void gs_abort(uint16_t why): from anywhere inside a call, the run ends.
;;; Everything the program pushed is simply left behind, under gs_run's S.
gs_abort:     rep     #0x30
              sta     long:gs_why
              brl     gs_back

;;; jsl $E10000 -> jml gs_entry
gs_entry:     phb
              phd
              txa
              sta     long:gs_x
              tsc
              sta     long:gsi_csp    ; D at +1, DB at +3, return at +4
              lda     long:gs_my_d
              tcd
              lda     ##0
              pha
              plb
              plb                     ; DB = $00
              sta     abs:gs_pop
              lda     abs:gsi_csp
              clc
              adc     ##7             ; the caller's last input
              jsl     gs_tool
              sta     abs:gsi_err
              lda     abs:gs_pop
              beq     gs_e_out
              clc
              adc     abs:gsi_csp
              tay                     ; where the frame goes
              ldx     abs:gsi_csp     ; where it is: slide it up, top first
              lda     abs:5,x
              sta     abs:5,y
              lda     abs:3,x
              sta     abs:3,y
              lda     abs:1,x
              sta     abs:1,y
              tya
              tcs
gs_e_out:     pld
              plb
              lda     long:gsi_err
              cmp     ##1             ; carry set: an error
              rtl

;;; jsl $E10004 -> jml gs_entry2.  Not served yet: it stops the program,
;;; saying which call it was.
gs_entry2:    rep     #0x30
              txa
              sta     long:gs_what
              lda     ##GS_UNTOOL
              brl     gs_abort

;;; jsl $E100A8 -> jml gs_gsos_entry: GS/OS, the call number and the
;;; parameter block's address in the six bytes after the jsl.  gs_gsos
;;; gets the address of the return address, which it moves past them.
gs_gsos_entry:
              phb
              phd
              tsc
              sta     long:gsi_csp
              lda     long:gs_my_d
              tcd
              lda     ##0
              pha
              plb
              plb
              lda     abs:gsi_csp
              clc
              adc     ##4             ; the return address
              jsl     gs_gsos
              sta     abs:gsi_err
              pld
              plb
              lda     long:gsi_err
              cmp     ##1
              rtl
