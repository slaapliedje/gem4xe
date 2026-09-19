/* mintbind.h -- mintlib's MiNT system-call bindings.
 *
 * gem4xe is not MiNT and does not pretend to be: there are no processes,
 * no signals and no file descriptors beyond GEMDOS's handles.  The GEMDOS
 * calls a MiNT program makes are the same ones plain TOS answers and
 * gem.h declares them; the MiNT-only ones are absent, so a program that
 * reaches for Pdomain or Psignal fails to compile rather than linking
 * against a stub that lies about what happened. */
#ifndef GEM4XE_MINTBIND_H
#define GEM4XE_MINTBIND_H
#include "gem.h"
#endif
