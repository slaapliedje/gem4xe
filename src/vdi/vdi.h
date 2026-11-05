/* vdi.h -- GEM VDI for gem4xe.
 *
 * Structure follows the Digital Research / EmuTOS screen driver: a fixed
 * parameter block of five arrays, a flat jump table indexed by opcode, and
 * handlers that take no arguments and read the globals.
 *
 * That 1984 ABI is a gift on this machine.  DRI's own entry.a86 copies the
 * caller's arrays into driver-owned globals and runs the whole VDI on a
 * private 256-byte stack; every handler is `void f(void)`.  Nothing here needs
 * argument passing, and nothing needs reentrancy.
 *
 * Only the 37 opcodes the AES and the GEM Desktop actually use are planned;
 * DRI's own shipping driver v_nop'd ten opcodes and so do we.
 */
#ifndef GEM4XE_VDI_H
#define GEM4XE_VDI_H

#include "portab.h"
#include <stdint.h>

typedef int16_t  WORD;
typedef uint16_t UWORD;

/* ---- parameter block -------------------------------------------------- */
/* contrl[] indices, per the VDI spec:
 *   0 opcode                     1 # of points in ptsin
 *   2 # of points out            3 # of words in intin
 *   4 # of words out             5 sub-opcode
 *   6 workstation handle         7-8  pointer parameter 1 (source MFDB)
 *   9-10 pointer parameter 2 (destination MFDB)                          */
#define CONTRL_SIZE 12
#define INTIN_SIZE  128
#define PTSIN_SIZE  128
#define INTOUT_SIZE 64
#define PTSOUT_SIZE 32

extern WORD contrl[CONTRL_SIZE];
extern WORD intin[INTIN_SIZE];
extern WORD ptsin[PTSIN_SIZE];
extern WORD intout[INTOUT_SIZE];
extern WORD ptsout[PTSOUT_SIZE];

/* ---- MFDB ------------------------------------------------------------- */
/* Kept byte-for-byte as the VDI defines it, including fd_wdwidth in 16-bit
 * WORDS, because every GEM application builds one of these by hand and a
 * changed layout breaks all of them.
 *
 * On this device it is only a hint: the driver computes the real byte stride
 * itself (width/2 for 4bpp chunky).  fd_stand likewise has nothing to
 * distinguish -- there is exactly one form here -- so vr_trnfm is a no-op. */
typedef struct {
    /* fd_addr is 32 bits BY SPECIFICATION -- the MFDB is a GEM/68000
     * structure and every application builds one by hand at that layout.
     * It must NOT be a native pointer: Calypsi's small data model makes
     * `void *` 16 bits, which silently shifts every field after it by two
     * bytes.  (Found the hard way: vrt_cpyfm read fd_w out of fd_addr's
     * upper half and drew garbage.)  On this target only the low 16 bits
     * are meaningful, since forms live in bank $00. */
    uint32_t fd_addr;       /* 0 = the physical screen */
    WORD   fd_w;            /* width in pixels */
    WORD   fd_h;            /* height in pixels */
    WORD   fd_wdwidth;      /* (fd_w + 15) / 16 -- WORDS, per the spec */
    WORD   fd_stand;        /* 0 device-specific, 1 VDI standard */
    WORD   fd_nplanes;
    WORD   fd_r1, fd_r2, fd_r3;
} MFDB;

/* ---- workstation ------------------------------------------------------ */
/* A subset of EmuTOS's Vwk, with the field names kept so the port stays
 * recognisable against the donor. */
typedef struct {
    WORD handle;
    WORD clip;              /* clipping enabled */
    WORD xmn_clip, ymn_clip, xmx_clip, ymx_clip;
    WORD wrt_mode;          /* 0 replace, 1 transparent, 2 XOR, 3 rev-trans */
    WORD line_color;
    WORD line_width;
    WORD line_index;        /* line style, 1..7 */
    WORD fill_color;
    WORD fill_style;        /* interior: FIS_HOLLOW .. FIS_USER (donor name) */
    WORD fill_index;        /* vsf_style's index MINUS ONE, as the donor keeps it */
    WORD fill_per;          /* outline fill area */
    WORD text_color;
    /* vsl_ends: LE_SQUARED / LE_ARROWED / LE_ROUNDED at each end of a
     * polyline.  Only an arrow is drawn -- a rounded end on a one-pixel
     * line is the same pixel a squared one puts there. */
    WORD line_beg, line_end;
    /* markers (vsm_*): the shape 0..5, its colour, the height asked for and
     * the whole-number scale that height rounds to. */
    WORD mark_index, mark_color, mark_height, mark_scale;
    /* vst_alignment: where the point v_gtext is given sits in the string.
     * 0/1/2 horizontally (left, centre, right) and 0..5 vertically
     * (baseline, half, ascent, bottom, descent, top) -- the donor's
     * numbering, and the default is left/baseline. */
    WORD h_align, v_align;
    /* vst_effects: the effects actually APPLIED, which is what the call
     * answers with and not necessarily what it was asked for. */
    WORD text_effects;
    /* What the two above resolve to: WHERE the current fill pattern's
     * rows are, as a source and a first row rather than as a pointer.
     * The standard tables are far (`cfar`) and the user's is near --
     * it is in this very struct -- so a pointer that could name either
     * would have to be far, and then "is this the user's?" becomes a
     * near-to-far comparison in the middle of the workstation switch.
     * A source and an index have no such question; pat_bits() does the
     * reading.  patmsk turns a y coordinate into a row: 3 for the
     * 4-row dithers, 7 for the OEM patterns and coarse hatches, 15 for
     * the fine hatches and the user pattern.  Bit 15 is the LEFTMOST
     * pixel of a 16-aligned screen word. */
    WORD  patsrc;           /* PAT_*: which table the rows come from */
    WORD  patidx;           /* the pattern's first row in it */
    WORD  patmsk;
    UWORD ud_patrn[16];     /* vsf_udpat's pattern, FIS_USER */
    UWORD ud_ls;            /* vsl_udsty's line style, index 7 */
    /* THE SURFACE THIS WORKSTATION DRAWS ON.  `vdev` was one global, set
     * before v_opnwk and never moved, because every workstation drew on
     * the one screen the machine had.  A printer workstation is a second
     * device alive at the same time as the screen -- that is what
     * v_opnwk's device id is FOR -- so the device belongs to the
     * workstation and vwk_select binds it, beside the two copies of a Vwk
     * it already makes when the drawing changes hands.
     * A void * rather than the real type: vdi.h is included by code that
     * has no business seeing the seam (src/vdi/vdidev.h). */
    const void FAR *dev;
} Vwk;

/* The physical workstation's handle, by specification; v_opnvwk hands
 * out the ones above it. */
#define VDI_PHYS_HANDLE 1

/* The VDI's sine table (src/vdi/sintbl.c, from EmuTOS by
 * tools/sinconv.py): sines of 0 to 89.6 degrees in 0.8 degree steps,
 * normalised to 0..65536, with no entry for exactly 90.  The GDPs are
 * the only caller. */
#define VDI_SIN_ANGLE_MAX 896
#define VDI_SIN_SIZE      ((VDI_SIN_ANGLE_MAX / 8) + 1)
extern const UWORD FAR vdi_sin_tbl[VDI_SIN_SIZE];

/* A curve is drawn as this many segments, from the larger radius over
 * four and clamped -- fewer than the donor's 32..128, because ptsin
 * holds the points and ours is 64 of them. */
#define MIN_ARC_CT 16
#define MAX_ARC_CT 48

/* v_gdp's sub-opcodes, in contrl[5] */
#define GDP_BAR       1
#define GDP_ARC       2
#define GDP_PIE       3
#define GDP_CIRCLE    4
#define GDP_ELLIPSE   5
#define GDP_ELLARC    6
#define GDP_ELLPIE    7
#define GDP_RBOX      8
#define GDP_RFBOX     9
#define GDP_JUSTIFIED 10

/* vsl_ends */
#define LE_SQUARED 0
#define LE_ARROWED 1
#define LE_ROUNDED 2

/* markers (vsm_type / vsm_height).  The nominal cell is the ST's, so that
 * an application's idea of a "standard" marker is the familiar one. */
#define MIN_MARK_STYLE 1
#define MAX_MARK_STYLE 6
#define DEF_MARK_STYLE 3
#define DEF_MKWD  15
#define DEF_MKHT  11
#define MAX_MKWD 120
#define MAX_MKHT  88

/* fill interior styles (vsf_interior) */
#define FIS_HOLLOW  0
#define FIS_SOLID   1
#define FIS_PATTERN 2
#define FIS_HATCH   3
#define FIS_USER    4
/* Where a fill pattern's rows come from (Vwk.patsrc).  SOLID and HOLLOW
 * carry no rows at all: patmsk is 0 and the row is the constant, which
 * is why the two one-word tables the pointer used to name are gone. */
#define PAT_HOLLOW  0
#define PAT_SOLID   1
#define PAT_DITHER  2
#define PAT_OEM     3
#define PAT_HATCH0  4
#define PAT_HATCH1  5
#define PAT_USER    6

/* vsf_style limits: 24 patterns (8 dithers + 16 OEM), 12 hatches; an index
 * out of range becomes 1, the way the donor's vsf_style does it. */
#define MAX_FILL_PATTERN 24
#define MAX_FILL_HATCH   12
/* The standard tables, generated from the donor by tools/patconv.py into
 * src/vdi/fillpat.c: 8 dithers of 4 rows, 16 OEM patterns of 8, 6 coarse
 * hatches of 8, 6 fine hatches of 16. */
/* FAR, in `cfar` with the far code: 608 bytes of bank $00 is 23% of
 * all the near memory the system has, and these are read a row at a
 * time when a fill's pattern changes, not per pixel (docs/phase24.md). */
extern const UWORD FAR fill_dither[32];
extern const UWORD FAR fill_oem[128];
extern const UWORD FAR fill_hatch0[48];
extern const UWORD FAR fill_hatch1[96];

/* The workstation a call names in contrl[6]: every VDI routine reads and
 * writes this one, and the dispatcher copies the right one in (vdi.c). */
extern Vwk vwk;

/* ---- what a device may call back into the VDI for ---------------------
 * These three are device-INdependent and both devices need them, so they
 * live here rather than being copied into each. */

/* The two of them in order, smallest first. */
void order(WORD *a, WORD *b);

/* The current clip rectangle applied to a rectangle; FALSE when nothing
 * is left of it. */
WORD clip_rect(WORD *x1, WORD *y1, WORD *x2, WORD *y2);

/* Row r of the current fill pattern: sixteen bits, bit 15 the leftmost
 * pixel of a 16-ALIGNED screen word.  Which table it comes from is the
 * workstation's business and so stays here. */
UWORD pat_bits(WORD r);

/* A line style rotated so that it too is anchored to the screen's
 * 16-pixel grid -- bit 15 at pixel 0 of every aligned word, the way a
 * fill pattern is -- which is what lets a styled line be drawn as a
 * patterned span and what keeps the two devices in the same phase. */
UWORD style_anchor(UWORD mask, WORD from, WORD dir);

/* writing modes, as vswr_mode takes them (1-based) */
#define MD_REPLACE 1
#define MD_TRANS   2
#define MD_XOR     3
#define MD_ERASE   4

/* ---- opcodes we implement -------------------------------------------- */
#define V_OPNWK        1
#define V_CLSWK        2
#define V_CLRWK        3
#define V_UPDWK        4
#define V_PLINE        6
#define V_GTEXT        8
#define VST_HEIGHT    12
#define VQT_ATTRIBUTES 38
#define VST_ALIGNMENT 39
#define VSL_TYPE      15
#define VSL_WIDTH     16
#define VSL_COLOR     17
#define VST_COLOR     22
#define VSF_INTERIOR  23
#define VSF_STYLE     24
#define VSF_COLOR     25
#define VSWR_MODE     32
#define VSF_UDPAT    112
#define V_OPNVWK     100
#define V_CLSVWK     101
#define VQ_EXTND     102
#define VRO_CPYFM    109
#define VR_TRNFM     110
#define VR_RECFL     114
#define VRT_CPYFM    121
#define V_ESCAPE       5
#define V_CHOICE      30
#define V_STRING      31
#define VSIN_MODE     33
#define VQIN_MODE    115
#define VEX_TIMV     118
#define VSL_UDSTY    113
#define VEX_BUTV     125
#define VEX_MOTV     126
#define VEX_CURV     127
#define VQ_KEY_S     128
#define VSC_FORM     111
#define V_SHOW_C     122
#define V_HIDE_C     123
#define VQ_MOUSE     124
#define VS_CLIP      129
#define VS_COLOR      14
#define VQ_COLOR      26
#define VST_POINT    107
#define VST_EFFECTS  106
#define VQT_EXTENT   116
#define VQT_WIDTH    117
#define V_PMARKER      7
#define V_FILLAREA     9
#define V_GDP         11
#define VST_ROTATION  13
#define VSM_TYPE      18
#define VSM_HEIGHT    19
#define VSM_COLOR     20
#define VQL_ATTRIBUTES 35
#define VQM_ATTRIBUTES 36
#define VQF_ATTRIBUTES 37
#define V_CONTOURFILL 103
#define VSF_PERIMETER 104
#define V_GET_PIXEL   105
#define VSL_ENDS      108

/* ---- entry point ------------------------------------------------------ */
/* GEM 8x8 system font (from EmuTOS bios/fnt_st_8x8.c via tools/fontconv.py).
 * A 1bpp strip: FONT_STRIDE bytes per row, FONT_H rows, character N's byte on
 * row r at r*FONT_STRIDE + N. */
/* THE FACE IS THE DEVICE'S, and so are its metrics: a 320-pixel screen
 * with an 8-wide cell is forty columns, which is half what a GEM screen
 * is, so the ANTIC device carries Atari's condensed 6x6 instead.  The
 * numbers are in src/vdi/vdidev.h, beside the geometry, because they are
 * chosen together.  The STRIDE is not: every face gem4xe links is
 * repacked into one byte per character per row, whatever the donor's
 * packing was, which is what lets one glyph blit serve all of them. */
#define FONT_STRIDE 256

/* vst_effects, and the two of them this driver can do: a second blit one
 * pixel right thickens a glyph, and a line under the cell underlines it.
 * The others are answered with what WAS applied, which is the contract. */
#define TXT_THICKEN   0x01
#define TXT_LIGHT     0x02
#define TXT_SKEW      0x04
#define TXT_UNDERLINE 0x08
#define TXT_OUTLINE   0x10
#define TXT_SHADOW    0x20
#define TXT_DONE      (TXT_THICKEN | TXT_UNDERLINE)

/* vst_alignment */
#define TA_LEFT 0
#define TA_CENTRE 1
#define TA_RIGHT 2
#define TA_BASE 0
#define TA_HALF 1
#define TA_ASCENT 2
#define TA_BOTTOM 3
#define TA_DESCENT 4
#define TA_TOP 5
/* The 8x8 face.  Unsized: how tall a face is is the DEVICE's business
 * now (vdidev.h), and an extern does not need to know. */
extern const uint8_t FAR font8x8[];

void vdi(void);             /* dispatch on contrl[0]; the GSX "SCREEN" entry */
void vdi_init(void);        /* one-time bring-up of the physical workstation */
void vdi_close_virtuals(void); /* every virtual workstation closed: a program's, at its end */
/* ...and for Pexec, which closes a child's and leaves its parent's
 * (src/sys/gemdos.c): the running context's open ones as a mask of their
 * slots, and all of those closed but the ones in `keep`. */
uint16_t vdi_virtuals_open(void);
void vdi_close_virtuals_but(uint16_t keep);
/* Every workstation `from` owns made `to`'s: a program put aside keeps
 * its workstations under a marker while another runs in its context --
 * they are owned by context, and process 0's is shared (src/aes/shel.c). */
void vdi_retag_virtuals(void *from, void *to);

/* Mouse cursor.  vdi_cursor_move() is what an input poll calls after
 * ptr_poll(): it erases, repositions and redraws only if something changed. */
void vdi_cursor_move(void);

/* The driver's save buffer for the AES -- what a drop-down or an alert
 * saves the screen under itself into (bb_save / bb_restore).  The donor
 * gsx_malloc()s one 25 character columns wide from the OS; here it is a
 * whole screen in VRAM, laid out like the screen, where the blitter can
 * reach it, and only the driver knows where.  Fills in an MFDB naming it,
 * for vro_cpyfm. */
void vdi_save_form(MFDB *m);

/* Drive the input devices once.  Polls the pointer and the keyboard, moves the
 * cursor, and calls whichever vex_* vectors are installed.
 *
 * The application calls this in its own loop.  Since Phase 9 the sampling
 * that cannot wait for the loop is done under interrupt (src/sys/irq.s: the
 * timer IRQ decodes a quadrature device, the keyboard IRQ latches the key) and
 * this call only consumes what the handlers counted -- so the loop may be as
 * slow as it likes without losing anything.  Moving the whole call under the
 * VBI is still possible; the AES above would not notice, which is the point
 * of it being a single entry point. */
void vdi_input_poll(void);

/* Just the keyboard: move POKEY's one-key latch into the driver's queue and
 * re-arm it.  Part of vdi_input_poll(); on its own it is what an idle loop
 * that must not disturb the pointer or the cursor calls, so that a key
 * pressed between two events is still there when someone asks. */
void vdi_key_poll(void);

/* The switch key, CONTROL and TAB, since it was last asked: 0 none, 1 the
 * next program, 2 (with SHIFT) the one before.  Taken from the keys
 * before they are queued, so no program sees it; asking clears it. */
WORD vdi_switchkey(void);

/* The gem4xe ABI for vex_* handlers: they take no arguments and read
 * ptr_state / the VDI globals.  GEM's 68000 convention passes x and y in
 * d0/d1, which has no meaning here; a documented platform convention is
 * better than a fake one. */
typedef void (*VDI_VEC)(void);

#endif /* GEM4XE_VDI_H */
