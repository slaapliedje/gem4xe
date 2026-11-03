;;; m25_stub.s -- the symbols this milestone reaches and has no use for.
;;;
;;; src/sys/irq.s points the native-mode COP vector at gem_cop, which is
;;; the ABI's entry (src/sys/abi.s) -- an application's way into the AES.
;;; A VDI milestone has no application and no AES, so linking abi.o would
;;; drag in the whole of both.  A COP here is a program that has gone
;;; wrong; returning is as good an answer as any.
;;;
;;; The four words below are the call gate's, which a context carries
;;; across a switch (src/sys/ctx.c), and app_run is how a context enters
;;; its program.  This runner has one process and never switches, so the
;;; words are never read and app_run is never called -- but the AES's
;;; event layer needs A process to exist, and the linker needs the
;;; symbols.  app_run answering zero is the honest stub: there is no
;;; program here to run.
              .rtmodel version, "1"
              .rtmodel cpu, "65816"

              .section zdata, bss
              .public gem_pb, gem_which, gem_api_sp, gem_depth
gem_pb:       .space  4
gem_api_sp:   .space  2
gem_which:    .space  1
gem_depth:    .space  1

              .section code
              .public gem_cop, app_run
              .public sdc_claims, sdc_open, sdc_close, sdc_xfer, sdc_xio
              .public sdc_command
gem_cop:      rti
;;; src/sys/cio.c asks src/sys/sdcio.c whether the engine has a name or an
;;; IOCB; with no GEMDOS here it never comes on, and sdc_claims says no --
;;; so the other four are never called either.
sdc_claims:
sdc_open:
sdc_close:
sdc_xfer:
sdc_xio:
sdc_command:
app_run:      lda     ##0
              rtl
              .end
