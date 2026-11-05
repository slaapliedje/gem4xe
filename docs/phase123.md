# Phase 123 -- AP_TERM: a program can be asked to end

The first of the AES 4 additions ST programs expect, and the one a task
switcher needs before anything else: a way to ask the running program to
end that the program can answer, refuse, or ignore -- and the one that
asked is told which.  A live test of RetroWP on XaAES showed what is lost
without it: the AES could not make the program quit.

## What AES 4 says, and what MultiTOS does

The protocol is MultiTOS's (its AES's `sh_shutdown` and `shel_write` in
`GEMSHLIB.C`, and its process exit in `GEMDISP.C`, read as specification;
the Compendium's `shel_write` and `evnt_mesag` pages beside them).

- `shel_write(SWM_NEWMSG, NM_APTERM, 0)` -- mode 9 -- registers: the
  program understands `AP_TERM`.
- `shel_write(SWM_SHUTDOWN, how, 0)` -- mode 4 -- asks every OTHER process
  to end.  It is **refused, and nothing is sent**, unless every other
  application has registered (and, for `SD_COMPLETE`, every accessory).
  Accessories are sent `AC_CLOSE`, applications `AP_TERM` with the reason
  in `msg[5]`.  `SD_ABORT` ends a shutdown, and only its caller may.
- `shel_write(SWM_AESMSG, ...)` -- mode 10 -- with `AP_TFAIL` and an error
  code in `msg[1]`: the program cannot end.
- The caller is told by `SHUT_COMPLETED`: `msg[3]` 1 once every
  application asked has gone, at once if there were none; 0 if one
  refused, with `msg[4]` who and `msg[5]` its code -- which also ends the
  shutdown.

**One place the two sources disagree.**  The Compendium puts `SD_ABORT`,
`SD_PARTIAL` and `SD_COMPLETE` in `wiscr`; MultiTOS's AES reads them from
`isgem` (`case 4: return sh_shutdown(isgem, AP_TERM)`).  The programs that
use mode 4 were tested against MultiTOS, so gem4xe reads `isgem` -- the
kit's `shel_write(SWM_SHUTDOWN, SD_PARTIAL, 0, ...)`.

## On gem4xe's processes

There is one application -- process 0, the desktop or the program it
started -- and up to six accessories; while a program runs, the desktop
is not a process at all but a dormant image (phase 121).  So a shutdown
asked for by an accessory asks the program; one asked for by the program
or the desktop has no other application to wait for and completes at once.
That is exactly what a switcher will be: an accessory, or the AES itself,
asking the one program to end.

| | where | what |
|---|---|---|
| `PROC.p_msgs` | `src/aes/proc.h` | mode 9's mask; cleared for each program process 0 runs and for each accessory's record |
| `sh_shutdown` | `src/aes/shel.c` | mode 4: the refusal, `AC_CLOSE` / `AP_TERM`, the caller recorded |
| `sh_appgone` | `src/aes/shel.c`, called by `sh_ldapp` after `mn_cleanup` | the program has ended: `SHUT_COMPLETED` 1 to whoever waited -- or the shutdown ends with its own caller |
| `sh_aesmsg` | mode 10 | `AP_TFAIL`: `SHUT_COMPLETED` 0, who, code |
| `sh_broadcast` | mode 7 | eight words to every other process, word 1 the sender, as `appl_write` does |
| `sh_environ` | mode 8 | `ENVIRON_SIZE`, and `ENVIRON_COPY` into a buffer in any bank answering the bytes left over; `ENVIRON_CHANGE` is not served |
| `src/sys/abi.c` | `shel_write` | modes 7 and 10 get their eight words, copied through a far pointer as `appl_write`'s are; mode 8 its buffer's address |

**Modes not served now say so.**  2, 3, 5 and 6 answered 1 -- "done" --
until now; they answer 0.  Mode 5 was the dangerous one: a resolution
change told yes is waited on by `RESCH_COMPLETED`, which would never come.

`appl_getinfo` follows: `AES_SHELL` answers 10, the highest legal mode,
and `AES_MESSAGE` sets bit 3 (`AP_TERM` is sent) and bit 4 (the shutdown
messages; the resolution change half of that bit is refused before
anything is sent).

## Mode 4 meant something else here

gem4xe's own desktop used `shel_write(4, 0, 0)` to mean "GEM ends when I
return" -- its Quit, and two error paths.  Under AES 4 that call is
`SD_ABORT`.  It was never needed: a desktop that returns without asking
for anything already ends the shell's loop (`sh_ldapp`).  So the three
calls are gone, `src/m16_desk.c`'s too, and `tools/deskref.py` -- the
desktop's model -- has neither them nor anything new but the registration.
`test-m12`'s `shel_write` checks now test mode 4 as AES 4's (abort with
none in force and an unknown mode answer 0; 9 answers 1; 5 is refused).

## The programs

| program | registers | on `AP_TERM` |
|---|---|---|
| the desktop | yes | Quit -- and GEM ends, as Quit ends it |
| EDIT | yes | what closing its window does: the changes question; Cancel answers `AP_TFAIL` |
| GEMARC | yes | ends: it holds nothing unsaved |
| G4BENCH | yes | ends from the results; during the run the message waits in the queue |
| Clock, Calculator (application builds) | **no** | they are modal panels that read no messages, so a shutdown is refused while one is up -- which is the rule working |

## The gate

`make test-m50` (`tests/emu/m50_shutdown.py`), on the G4DOS system floppy
with the gate's pair added by the SDK's own `install.py`: `M50.ACC`
(`src/m50_acc.c`) asks when the gate writes its `acc_req`, and
`src/m50_app.c` is on the disk four times, its name saying how it answers.

1. `appl_getinfo`: shell modes to 10, message bits 3 and 4.
2. M50U never registered: refused, 0; nothing sent; it runs on.
3. M50F registered: `AP_TERM` with `msg[5]` `AP_TERM`; its `AP_TFAIL`
   taken; `SHUT_COMPLETED` 0, process 0, code 77; an abort then answers 0.
   Asked again, it ends, and `SHUT_COMPLETED` says 1.
4. M50S never answers: asked again by the same caller, 1; aborted, 1;
   aborted again, 0; nothing sent when it ends later.
5. M50T ends on `AP_TERM`; `SHUT_COMPLETED` 1.
6. The desktop: `AP_TERM` is Quit, GEM ends, G4DOS's shell is back, and
   `SHUT_COMPLETED` went out as the desktop ended -- watched a frame at a
   time while it happens, because afterwards GEM's memory is the DOS's.

Shown to fail: with the refusal removed, four checks; with
`SHUT_COMPLETED` never sent when the program ends, three.

## Not yet

- Programs written for AES 4 decide by `global[0]`, which is still
  `0x0140`, or by `appl_find("?AGI")`, which gem4xe does not answer -- so
  stock gemlib and cflib builds still do not ask `appl_getinfo`.  Raising
  either is the next phase, once `menu_register` from an application,
  `appl_search`, `rsrc_rcfix` and the rest of what an AES 4 program will
  then call answer honestly.
- `CH_EXIT`, resolution changes, `WM_UNTOPPED` / `WM_ONTOP` / `WM_BOTTOM`
  and iconify.
- RetroWP's `AP_TERM` registration is compiled out of its gem4xe build
  (`#ifndef GEM4XE_APP_GEM_H` in `platform/atari/app_shell.c`); it can be
  gated on `appl_getinfo(AES_MESSAGE)` bit 3 now.
