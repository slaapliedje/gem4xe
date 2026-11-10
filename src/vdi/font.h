/* font.h -- the system font, and loading another one.
 *
 * gem4xe links one 8x8 face (src/vdi/font8x8.c, EmuTOS's Atari ST set) and
 * expands it into VRAM as glyph masks.  A translation usually needs a
 * different CHARACTER SET rather than a different size -- Latin-2 for Polish
 * and Czech, Cyrillic, Greek -- so what is loadable here is the strip: a GEM
 * .FNT file whose cell is the same 8x8 and whose 2 KB of glyphs replace the
 * linked ones (docs/shipping.md, section 5).
 *
 * The cell does not change, and that is a decision rather than an oversight.
 * The AES's geometry is in character cells (gl_wchar, gl_hchar) and is asked
 * for once at start-up; the blitter has no shifter, so every glyph is also a
 * pre-shifted second copy in VRAM; and the host reference draws the same
 * cells.  A face of another SIZE is all of that again, and would earn its
 * place only when there is something to do with it.  A face of another
 * ALPHABET is 2 KB and a file.
 */
#ifndef GEM4XE_VDI_FONT_H
#define GEM4XE_VDI_FONT_H

#include <stdint.h>
#include "vdi.h"

#define FONT_FILE     "SYSTEM.FNT"  /* what the system looks for at start-up */
#define FONT_NAME_MAX 33            /* 32 characters and a NUL, as the format */
#define FONT_ID_SYS   1             /* the face that is linked in */
#define FONT_SYSTEM   1             /* vqt_name's index for it */
#define FONT_LOADED   2             /* and for the one from the file */

/* The strip the VDI draws from: a far address, the linked font until a file
 * replaces it.  Set before the first vdi_font_expand(). */
extern uint32_t vdi_font;

void        vdi_font_where(const char *cioname);  /* where to look for it */
WORD        vdi_font_load(void);                  /* 1 if a font was taken */
void        vdi_font_default(void);               /* back to the linked one */
WORD        vdi_font_faces(void);                 /* 1, or 2 with one loaded */
WORD        vdi_font_id(WORD face);               /* its font_id */
void vdi_font_name(WORD face, WORD *out);         /* its name, 32 words */
WORD        vdi_font_select(WORD id);             /* the face now drawn with */

#endif /* GEM4XE_VDI_FONT_H */
