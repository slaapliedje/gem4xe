# Phase 150 -- the cookie jar (VDI step 3)

The last item of step 3 of [vdi-plan.md](vdi-plan.md) that was agreed
(2026-11-11: the cookie jar, then step 4; text effects and proportional
faces left for later).

| | was | now |
|---|---|---|
| `Getcookie` | not found, every cookie | the system's answer, through MiNT's `Ssystem(S_GETCOOKIE)` |
| `Ssystem` (GEMDOS 0x154) | EINVFN | `S_GETCOOKIE` and the inquiry; any other mode EINVFN |

## What the jar says

A TOS program asks the jar what the machine is before it touches
anything.  A cookie that claimed ST or STE hardware could lead a ported
program to poke a shifter or a YM2149 that are not there.  So the jar
says what is true, in the values EmuTOS uses for a machine that is not
an Atari:

| cookie | value | meaning |
|---|---|---|
| `_MCH` | `$FFFFFFFF` | no ST-compatible machine (EmuTOS's `MCH_NOHARD`) |
| `_VDO` | `$FFFFFFFF` | no ST-compatible video (`VDO_NOHARD`): ask the VDI |
| `_SND` | 0 | no YM2149 and no DMA sound -- an absent `_SND` means a YM, which would be untrue |
| `_CPU` | 0 | nothing past a 68000 to rely on, which is also what an absent `_CPU` means |
| `G4XE` | the version, major << 8 \| minor | gem4xe, 0.13 being `$000D` |

Any other cookie is not found: `NVDI`, `MiNT` and `_IDT` are not
there, so a program that asks for them defaults, as qed does.

## How it is reached

There is no jar in memory.  `$5A0`, where TOS keeps the pointer, is in
the Atari's page 5, which is the DOS's.  So the system answers the
cookies itself, through `Ssystem(S_GETCOOKIE, cookie, address)`, MiNT's
call.  mintlib's `Getcookie` asks that call before it looks for a jar,
so a port's own code finds the answers either way.

- With an address, the value is written there and the call answers 0.
- With no address, it answers the value.
- A cookie not in the jar answers -1.
- `Ssystem(-1, 0, 0)` answers 0, to say the call is there.

Nothing can be added to the jar.

The kit's `Getcookie` (`<mint/cookie.h>`) is built on `Ssystem`, and so
is the control panel's `getcookie` for its modules.  The version comes
from `VERSION`, through `build/version.h`, which now carries
`GEM4XE_VERSION_NUM` as well as the string.

## Gate

`test-m32`, GEMDOS's gate, reads six cookies through `Getcookie` --
`_MCH`, `_VDO`, `_SND`, `_CPU`, `G4XE` and `NVDI`.  It checks each
answer and value: `NVDI` not found and its variable untouched, and
`G4XE`'s version read from `VERSION`.  It also checks the inquiry, a
mode the call has not got (EINVFN), and a cookie asked for with no
address.  `tests/host/test_bind.py` checks the binding.

| broken on purpose | result |
|---|---|
| GEMDOS without `Ssystem` | every cookie not found |
