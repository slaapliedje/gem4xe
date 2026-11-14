# Phase 166 -- DUP's L and B

Step 5 of `docs/run8-plan.md`, its last.  DUP.PRG (phase 160) answered
B, K, L, M and N with NOT UNDER GEM.  Since phases 162-165 the AES can
end GEM, run a plain Atari program or the cartridge, and start GEM again,
on every DOS.  So L and B ask for that, as the desktop's icons do.

- **L. BINARY LOAD** asks DUP.SYS's question, LOAD FROM WHAT FILE?, and
  takes a name the way DUP's other letters do (`D2:GAMES>PROG.XEX`).
  DUP opens the file first:
  - no file: DUP's ERROR- 170, as for any letter;
  - not $FF $FF (or SpartaDOS X's $FA $FF) first: ERROR- 180, DOS 2's
    "not a binary file";
  - a binary file whose extension is not .COM, .XEX, .EXE or .OBJ: GEM
    RUNS .COM .XEX .EXE AND .OBJ FILES ONLY.  The AES knows a plain
    program from a GEM one by that extension (`sh_isplain`), and a
    different one would be loaded as a GEM program and refused after
    DUP had gone.
- **B. RUN CARTRIDGE** reads the cookie `G4CT`.  None: NO CARTRIDGE, as
  DUP.SYS says.  BASIC or a cartridge: the name `CAR:`.
- Either way DUP calls `shel_write(SHW_EXEC)` with the name in a buffer of
  its own frame (it is a large-data program; phase 50's bounce), and
  quits.  The AES runs it after DUP, as it runs a program the desktop
  asked for.  What comes back is what started GEM: the desktop, or on an
  appliance floppy DUP again.
- **K, M and N stay refused.**  Binary save, run at an address and
  MEM.SAV each need the memory GEM holds while it runs.

DUP.RSC has three lines more: Q_L, R_NOCART and R_NOTPLAIN.  `test-m65`'s
refused letter is K now.

## Gate

**`test-m71`**, on `dup-test.atr`, the appliance floppy that starts DUP
in the desktop's place, with an SDFS in D2::
- L of README.TXT: ERROR- 180; L of ODD.BIN, a binary file: FILES ONLY;
  K: NOT UNDER GEM.  DUP stays.
- L of `D2:GAMES>PROG.XEX`: PROGRAM RAN, GEM, and DUP's menu again.
- B: the emulator's XL has BASIC, so READY; DOS typed, and DUP again,
  with BASIC switched out.

| broken on purpose | result |
|---|---|
| the extension check always passing | ODD.BIN is not refused; the gate fails |
| DUP not quitting after it asks | no PROGRAM RAN, no READY; the gate fails |

No gate covers NO CARTRIDGE: the emulated XL always has BASIC.
