/* osbind.h -- the TOS system-call bindings, under the name an ST source
 * includes.  On the ST this declares the BIOS, XBIOS and GEMDOS traps;
 * here the system serves GEMDOS and a handful of the others, and gem.h
 * declares all of it, so this is the one door pointing at the other.
 *
 * A program that includes <osbind.h> and calls something this machine
 * does not serve gets a compile error naming the call, which is the
 * answer it wants -- better than a binding that links and returns a
 * plausible number. */
#ifndef GEM4XE_OSBIND_H
#define GEM4XE_OSBIND_H
#include "gem.h"
#endif
