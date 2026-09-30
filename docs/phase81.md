# Phase 81 -- a black screen under AltirraOS: the timer armed too soon

After 0.9.2 the AtariAge user who had reported the white screen had a
black one, and Altirra's debugger stopped at

    (1738:248, 0) C=01F4 X=--3F Y=--34 S=0680 P=74 ( VMX I )  00:FB0C: 00  BRK

-- native mode, interrupts off, a stack in page 6, and `$FB0C`, which is
code in Atari's XL ROM and a keyboard table in AltirraOS.  The setup was
unknown: Altirra or AltirraSDL, and its settings.

## What every gate had in common

`tools/a8test/launcher.py` boots **Atari's XL ROM** (`--kernel xl`), and
every gate runs on it.  A stock Altirra runs **AltirraOS**, its own OS,
when no ROM images are set up.  Booted under AltirraOS (`--kernel llexl`)
on Altirra's own 65C816 at its default 1.79 MHz, the 0.9.2 cartridge never
reached the desktop: 400 seconds, and the far memory probe had not run.
On a 20 MHz Rapidus under AltirraOS it did, and under the XL ROM on the
same 1.79 MHz machine it did.

## An interrupt storm

The CPU's last 4,096 instructions were all gem4xe's interrupt handler.
Each pass read `IRQST` = $F6 -- timer 1 pending -- acknowledged it, and
took it again the instruction after the `RTI`: 8,293 a second whatever
the divisor, which is not the timer's rate but the handler's, back to
back, on a 1.79 MHz CPU.  POKEY's interrupts switched off through the
bridge, the main line ran at once -- it had got as far as a CIO call.

The main line, stepped: `copy_run` (the OS copied under the ROM for the
vectors), then sixty frames in AltirraOS at `$EA2D`, which is its SIO wait
(`TIMFLG`, `STATUS`, `RECVDN`), then the storm.  gem4xe's
`abi_probe_os` opens `@:SYSDEF` to ask whether Rapidus OS is there;
AltirraOS does not know the `@:` device and polls the serial bus for a
handler to load, which times out -- and leaves POKEY as its SIO set it.

**The bug is the order.**  The CIO trampoline's way out
(`src/sys/cio.s`) put gem4xe's interrupt sources back -- timer 1 among
them -- and its `PLP` let interrupts in; the C wrapper's
`irq_pokey_resync`, which gives the timer its own settings back, came
after.  For that moment timer 1 counted by what SIO had left, fired again
within two hundred cycles of every acknowledgement, and the resync never
got a cycle to run.  The same writes made from the bridge, which needs
no CPU time, ended the storm every time.

## The fix

- The trampoline brings the sources back **without timer 1**, and
  `irq_pokey_resync` reprograms the timer, **restarts it** (`STIMER`,
  which it had deliberately not written, to spare the clock the part of a
  tick a CIO call interrupts) and only then arms it.  Every entry into
  the trampoline -- `cio_call`, `dsk_call`, `dos_call`, `sdx_call` -- is
  followed by the resync now, or the mouse would stop after the first
  disk call.
- **The sampler's rate follows the CPU.**  4 kHz is a Rapidus's rate;
  each interrupt costs a native-mode entry, the handler and an `RTI`,
  part of it on the slow bus, which is most of a 1.79 MHz CPU.
  `irq_install` counts turns of a loop over 128 scanlines (`cpu_turns`,
  one `VCOUNT` read per sixteen turns, since on a Rapidus every I/O read
  is a trip to the slow bus) -- 400 on a 20 MHz Rapidus, 25 on a 1.79 MHz
  65C816 -- and below 200 the divisor grows in proportion: 127, ~500 Hz,
  on the slow machine.  `irq_clock` counts time by `irq.timer_div`, so
  the clock does not care.

Under AltirraOS on the 1.79 MHz 65C816 the desktop is up in 88 seconds.

## The gate

`make test-m37` boots the cartridge under AltirraOS on that machine and
requires the desktop, and a sampler divisor above the Rapidus's.  Under
0.9.2 the same case never reached the desktop.

The debugger stop the user saw -- `BRK` at `$FB0C`, the stack at `$0680`
-- was not reproduced exactly: what a storm leaves behind depends on
where it caught the machine and on the emulator.  This is the storm we
could reproduce from the same cartridge and a stock Altirra's defaults.

**Not the reporter's crash, as it turned out.**  Their machine was a PAL
130XE with a Rapidus and Atari's XL ROM, in Windows Altirra, and that
emulator's 65C816 has the native-mode IRQ-shadow bug AltirraSDL fixed in
September (tools/altirra/README.md): docs/phase82.md.  This one is real
all the same, on a stock Altirra's defaults.
