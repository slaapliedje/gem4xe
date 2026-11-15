/* v6stub.c -- what a 6502 program without the window manager links
 * against (src/v6_vdi.c's, steps 1-3): objc.c re-fits the windows after
 * a desktop icon changes (w_look) and reads wind.c's empty rectangle.
 * A program with src/aes/wind.c (step 4c) has the real ones. */
#include "portab.h"
#include "aes/aes.h"

void  w_look(void) {}
GRECT gl_rzero;
