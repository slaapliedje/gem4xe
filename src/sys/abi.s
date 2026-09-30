;;; ---------------------------------------------------------------------------
;;; abi.s -- the COP handler and app_run (65C816 native)
;;;
;;; An application calls gem4xe with COP #$56 (VDI), COP #$41 (AES) or
;;; COP #$44 (GEMDOS), the parameter block's address in X:C
;;; (src/app/gem.h).  The CPU pushes PB, PC and P, sets I, clears the
;;; decimal flag, and arrives here through the bank-$00 stub in
;;; src/sys/irq.s and irq_cop in src/sys/sei.s, which takes its own COP
;;; and passes every other with M and X 16 bits wide -- the caller's
;;; widths are the ones in the P on the stack.
;;;
;;; A COP that is not one of those three is somebody else's.  Under Rapidus
;;; OS it is the OS's -- COP #$00 is its system emulation call and #$01 its
;;; kmem, which its SpartaDOS X modules make as well -- and the OS's
;;; specification says a program that takes the COP vector ends with a jump
;;; to the old one.  So when abi_probe_os() found the OS's native services
;;; (gem_cop_pass), a foreign COP leaves through the OS's own RAM vector,
;;; VCOPN, with every register and both widths as the caller had them: the
;;; frame is still the CPU's, and the OS handler restores it and RTIs.  With
;;; no such OS there is nobody to give it to, and it is refused and counted
;;; (gem_entry, gem_bad), as before.
;;;
;;; What this does: save the caller's registers, D and DB; switch to
;;; gem4xe's direct page and data bank; note where the parameter block is
;;; and which signature byte follows the COP; move onto gem4xe's stack if
;;; an application is running and this is the outermost call; give
;;; interrupts back if the caller had them; call gem_entry() (src/sys/abi.c,
;;; the copy-in / copy-out shim); undo all of it; RTI.  A, X and Y are
;;; returned as they were, so the ABI clobbers nothing the caller sees --
;;; results travel through the block.
;;;
;;; The stack switch is what makes an application's stack its own business.
;;; The application runs on a 256-byte stack in its bank-$00 pool; the VDI
;;; and the AES want more than that below them (objc_draw recurses).  So a
;;; COP from the application is served on gem4xe's stack, at the depth
;;; app_run left it: everything below gem_api_sp is free, because app_run
;;; records S at the very moment of the jsl and the application's crt takes
;;; its own stack before pushing anything more.  A nested COP -- the AES
;;; calling back into the application is not a thing today, but gem_depth
;;; costs nothing -- stays where it is.
;;;
;;; gem4xe's pseudo registers _Dp[0..7] are scratch here: they are caller-
;;; saved in Calypsi's convention, so nothing in gem4xe holds a value in
;;; them across the app_run() call that an application runs inside.
;;; ---------------------------------------------------------------------------

              .rtmodel version, "1"
              .rtmodel core, "*"

              .extern _DirectPageStart, _Dp
              .extern gem_entry, gem_pb, gem_which, gem_api_sp, gem_depth
              .extern gem_cop_pass, gem_term, irq_sei
              .public gem_cop, app_run

ABI_VDI:      .equ    0x56            ; src/sys/abi.h, src/app/gemabi.s
ABI_AES:      .equ    0x41
ABI_GEMDOS:   .equ    0x44
VCOPN:        .equ    0x0256          ; Rapidus OS's native COP vector, LONG

              .section zdata, bss
app_entry:    .space  4               ; the application's entry, for JML [abs]

              .section farcode, root

;;; ---------------------------------------------------------------------------
;;; The COP handler.
;;; ---------------------------------------------------------------------------
gem_cop:      rep     #0x30
              pha
              phx
              phy
              phd
              phb
;;; The frame:  1,s B   2,s D   4,s Y   6,s X   8,s A   10,s P   11,s PC   13,s PB
              sep     #0x20
              lda     #0
              pha
              plb                     ; DB = $00
              rep     #0x20
              lda     ##_DirectPageStart
              tcd                     ; gem4xe's direct page
              lda     8,s             ; the block: X:C at the COP
              sta     abs:gem_pb
              lda     6,s
              sta     abs:gem_pb+2
              lda     11,s            ; PC is past the signature byte ...
              dec     a
              sta     dp:.tiny(_Dp+0)
              sep     #0x20
              lda     13,s            ; ... in bank PB
              sta     dp:.tiny(_Dp+2)
              lda     [.tiny _Dp]
              sta     abs:gem_which
              cmp     #ABI_VDI
              beq     gem_cop_ours
              cmp     #ABI_AES
              beq     gem_cop_ours
              cmp     #ABI_GEMDOS
              beq     gem_cop_ours
              lda     abs:gem_cop_pass
              bne     gem_cop_foreign ; the OS's: see the file head
gem_cop_ours: lda     10,s            ; the caller's I, read before the
              and     #0x04           ; frame goes out of reach
              sta     dp:.tiny(_Dp+4)
              stz     dp:.tiny(_Dp+5)
              lda     abs:gem_depth
              inc     a
              sta     abs:gem_depth
              dec     a
              rep     #0x20
              bne     gem_cop_stay    ; nested: already on gem4xe's stack
              lda     abs:gem_api_sp
              beq     gem_cop_stay    ; no application running: nowhere to go
              tsc
              tax
              lda     abs:gem_api_sp
              tcs
              phx                     ; the caller's S, on gem4xe's stack
              bra     gem_cop_call
gem_cop_stay: tsc
              tax
              phx                     ; the same S, so the exit is one path
gem_cop_call: lda     dp:.tiny(_Dp+4)
              bne     gem_cop_go
              cli                     ; the caller ran with interrupts on
gem_cop_go:   jsl     gem_entry
              jsl     irq_sei         ; not SEI: src/sys/sei.s says why
              sep     #0x20
              dec     abs:gem_depth
              lda     abs:gem_term
              bne     gem_cop_term    ; the program ended itself: see below
gem_cop_out:  rep     #0x30
              pla
              tcs                     ; the caller's stack
              plb
              pld
              ply
              plx
              pla
              rti

;;; Pterm, Pterm0, Ptermres, or ^C at the console (src/sys/gemdos.c): the
;;; program has ended, and this COP does not return to it.  It goes where
;;; the program's main() would have returned to instead -- app_run, whose
;;; S gem_api_sp has kept since the jsl into the program.  The crt took a
;;; stack of its own below that, so everything the program pushed, and
;;; everything this call has, lies under it and is simply left behind.
;;; The `rtl` is the one the crt's would have been, with the block's
;;; result -- the code -- in A where main's value would be; D and DB are
;;; gem4xe's already, and app_run puts the interrupt state back.  With no
;;; program running there is nothing to end, and the call returns as any
;;; other does.
gem_cop_term: stz     abs:gem_term
              rep     #0x30
              lda     abs:gem_api_sp
              beq     gem_cop_out
              lda     abs:gem_pb      ; the block's result word
              sta     dp:.tiny(_Dp+0)
              lda     abs:gem_pb+2
              sta     dp:.tiny(_Dp+2)
              lda     [.tiny _Dp]
              tax
              sep     #0x20
              stz     abs:gem_depth
              rep     #0x20
              lda     abs:gem_api_sp
              tcs
              txa
              rtl

;;; A COP for the OS.  A is 8 bits, DB is $00, and nothing but the five
;;; saves is on the stack above the CPU's frame.  The caller's M and X are
;;; read from its P while the frame is in reach, and pick one of four ways
;;; out: each takes the saves off in 16 bits, gives back the widths the
;;; caller had, and makes the jump the OS's own $FFE4 stub makes.  (No
;;; flag can carry the choice past the pulls -- they set N and Z -- and
;;; there is no long BIT to read it back after DB has gone.)
gem_cop_foreign:
              lda     10,s            ; the caller's P
              and     #0x30           ; M and X
              beq     gem_cop_f00
              cmp     #0x10
              beq     gem_cop_f10
              cmp     #0x20
              beq     gem_cop_f20
              rep     #0x30           ; M 8, X 8
              plb
              pld
              ply
              plx
              pla
              sep     #0x30
              jmp     [VCOPN]         ; JML through the OS's native COP vector
gem_cop_f20:  rep     #0x30           ; M 8, X 16
              plb
              pld
              ply
              plx
              pla
              sep     #0x20
              jmp     [VCOPN]
gem_cop_f10:  rep     #0x30           ; M 16, X 8
              plb
              pld
              ply
              plx
              pla
              sep     #0x10
              jmp     [VCOPN]
gem_cop_f00:  rep     #0x30           ; M 16, X 16
              plb
              pld
              ply
              plx
              pla
              jmp     [VCOPN]

;;; ---------------------------------------------------------------------------
;;; int16_t app_run(uint32_t entry) -- __simple_call, entry in X:C.
;;;
;;; Calls the application's entry as a far subroutine and returns what its
;;; main() returned.  The application's crt (src/app/crt_gemapp.s) saves
;;; and restores S, D and DB itself, so this side has nothing to unwind.
;;; A program that ends with Pterm comes back here without its crt, from
;;; the COP handler (gem_cop_term), with interrupts off, so the caller's P
;;; is kept across the call and put back either way.
;;; gem_api_sp is taken INSIDE the trampoline, after the jsl has pushed
;;; app_run's return address: S there is the first free byte, and it is
;;; the S the crt records as well, so the two agree on where gem4xe's stack
;;; resumes.  Cleared on return: a COP with no application running stays on
;;; the caller's stack.
;;; ---------------------------------------------------------------------------
app_run:      sta     abs:app_entry
              txa
              sta     abs:app_entry+2
              sep     #0x20
              stz     abs:gem_depth
              rep     #0x20
              php                     ; the caller's I, for a Pterm
              jsl     app_tramp
              tax                     ; main's return value, or Pterm's code
              stz     abs:gem_api_sp
              plp
              txa
              rtl
app_tramp:    tsc
              sta     abs:gem_api_sp
              jmp     [app_entry]     ; JML through the bank-$00 long pointer
