# Phase 102 -- the card gate's eight calls

`make test-cf` had failed since before 0.11 with "the desktop is in
call 83, not its first wait 76".  The desk itself matched the model to
the pixel, and 0.11 failed identically, so it was not a regression.
It is not in `make test`: it needs the U1MB flash fixture.

## Finding them

A scratch build logged each call `app_calls` counted into far memory,
and the gate printed it beside the model's script.  After the eighth
call the two lists were the same, call for call.  The eight were:

    shel_read, rsrc_load, rsrc_gaddr, Ptermres     GENERAL.CPX
    shel_read, rsrc_load, rsrc_gaddr, Ptermres     COLOR.CPX

The control panel's modules are programs, run through `app_run` at boot
in the application's record (phase 61), so `src/sys/abi.c` counted their
calls as the application's.  The product floppies carry no modules, so
`make test-boot` never saw them.  The card carries two.

## The fix

`app_calls` is "the calls the application made", and a gate asks it
which call the desktop is in.  The shell now starts it at 0 after the
AUTO programs, the modules and the accessories have run
(`src/aes/shel.c` `sh_start`), just before the desktop.  Nothing before
that point is an application's.

The gate had a gap of its own.  `tests/emu/cf_boot.py` did not tell the
model that the card's SpartaDOS X has a command processor, as
`tests/emu/product_boot.py` does.  So the model greyed File -> DOS
command, which the card's desktop leaves lit, and made one call the
desktop does not.  With both fixed, the desktop
is in call 75, its first wait, and `make test-cf` passes.  `make
test-sd` boots the same gate on the SD card image.
