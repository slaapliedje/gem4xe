/* macros.h -- mintlib's, as far as an ST source reaches into it: min,
 * max, and PATH_MAX, which mintlib's <limits.h> has and Calypsi's does
 * not.  The value is the system's own (gem.h, GEM_PATH_MAX). */
#ifndef GEM4XE_MACROS_H
#define GEM4XE_MACROS_H

#include "gem.h"

#ifndef min
#define min(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef max
#define max(a, b) ((a) > (b) ? (a) : (b))
#endif
#ifndef PATH_MAX
#define PATH_MAX GEM_PATH_MAX
#endif

#endif
