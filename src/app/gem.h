/* gem.h -- what a gem4xe application sees of GEM.
 *
 * An application is a separate program: it is linked against nothing of
 * gem4xe's and knows no address inside it.  It reaches the VDI and the AES
 * the way an ST program reaches them through trap #2 -- by a software
 * interrupt, here the 65816's COP, with a parameter block whose five (VDI)
 * or six (AES) fields point at the caller's own arrays:
 *
 *     COP #$56   VDI     X:C = address of a VDIPB     (vdi_call)
 *     COP #$41   AES     X:C = address of an AESPB    (aes_call)
 *     COP #$44   GEMDOS  X:C = address of a GDPB      (dos_call)
 *
 * The block layouts are the ST's (the AES's and GEMDOS's function numbers
 * too), so a GEM binding written for the ST needs only its trap replaced.
 * The signature bytes are letters, 'V', 'A' and 'D', because the ST's trap
 * numbers do not fit this machine: $00 and $01 are Rapidus OS's own COPs
 * and $80-$FF are reserved by WDC (src/sys/abi.h).  A program built with
 * the old ones ($73, $C8, $01) is refused by the loader: rebuild it.
 * Those three are the whole set, and a COP with any other signature is
 * not a gem4xe call at all: under Rapidus OS it is handed to that OS
 * through its own vector, and without one it is refused, counted, and
 * RETURNS WITH THE BLOCK UNTOUCHED -- so a hand-rolled gate does nothing
 * and says nothing.  There is no safe way to report it either: the
 * block's address came from X:C by this convention, and a call that does
 * not follow the convention may not have put a block there at all, so
 * writing an error into it could scribble on the caller.  $42 'B' and
 * $58 'X' are held for a BIOS and an XBIOS if they are ever built
 * (docs/phase41.md); until then nothing answers them.
 * gem4xe copies the caller's arrays in before the call
 * and out after it -- the DRI entry discipline -- so an application's
 * arrays may be exactly as large as its own calls need, and nothing of the
 * application's is ever read while the call is not in progress.
 *
 * On return A, X and Y are undefined; D, DB, S and P are as they were.
 * Trees and forms the AES reads IN PLACE are addressed with 16 bits inside
 * gem4xe (the small data model), so they must be in bank $00 -- which is
 * where an application's data is, its near region being a slice of bank $00
 * (src/app/gemapp.scm).  STRINGS may be FAR: a --data-model=large program
 * keeps its literals in far memory, and the shim brings one down before
 * the call (src/sys/abi.c).  Three sizes, in the order a string grows:
 *
 *   rsrc_load, menu_text, menu_register and the fsel dialog title copy
 *   into a 64-byte near scratch (near_str), so 63 bytes;
 *
 *   form_alert takes the AES's pool instead (pool_str), so 511 -- an
 *   alert a screen can hold does not fit in the scratch;
 *
 *   wind_set(WF_NAME) and WF_INFO copy nothing here.  The AES keeps all
 *   24 bits of the address and reads the string again at every redraw,
 *   as the ST's does, bringing a far one down where the DRAWING happens
 *   (src/aes/wind.c, w_ptext).  A far title of any length is accepted
 *   and an application may still edit it in place, but 40 characters of
 *   it are drawn; a NEAR title is used where it lies and has no cap.
 *
 * A second far string in one call -- which fsel's path/selection,
 * shel_write and shel_find are -- still wants bank $00.
 */
#ifndef GEM4XE_APP_GEM_H
#define GEM4XE_APP_GEM_H

#include "portab.h"
#include <stdint.h>
#include <stddef.h>

typedef short          WORD;
typedef unsigned short UWORD;
typedef long           LONG;

/* gemlib's spelling for a workstation handle. The ST's bindings declare
 * every VDI entry point as taking one of these rather than a bare WORD,
 * so a portable backend written against them names the type -- retroplat's
 * Atari backend does, in the one line it takes to say
 * `void atari_select_font(VdiHdl vdi, ...)`. Adding it costs nothing here
 * and is the difference between that backend compiling and not. */
typedef short          VdiHdl;

/* The five VDI arrays and the six AES arrays, by far pointer: 32 bits in
 * memory each, which makes the block the ST's byte for byte. */
typedef struct {
    WORD FAR *contrl;
    WORD FAR *intin;
    WORD FAR *ptsin;
    WORD FAR *intout;
    WORD FAR *ptsout;
} VDIPB;

typedef struct {
    WORD FAR *control;
    WORD FAR *global;
    WORD FAR *int_in;
    WORD FAR *int_out;
    LONG FAR *addr_in;
    LONG FAR *addr_out;
} AESPB;

/* GEMDOS's block is the ST's trap #1 stack frame with the result in front
 * of it: the function number, then the arguments in the ST's order and
 * sizes (WORD 2, LONG 4), little-endian.  20 bytes holds the longest,
 * Pexec's. */
typedef struct {
    LONG ret;
    WORD fn;
    WORD arg[7];
} GDPB;

/* The three entry points (src/app/gemabi.s).  SIMPLE_CALL puts the
 * block's address in X:C, which is where the COP handler looks. */
SIMPLE_CALL void vdi_call(VDIPB FAR *pb);
SIMPLE_CALL void aes_call(AESPB FAR *pb);
SIMPLE_CALL void dos_call(GDPB FAR *pb);

typedef struct {
    WORD g_x, g_y, g_w, g_h;
} GRECT;

/* -- The AES object, as in aes.h.  ob_spec is four bytes whose low word
 * holds a bank-$00 address for the types that point at something, and it
 * is declared as the union gemlib declares, so that a program written
 * against either reads it the same way: ob_spec.index for the raw bits,
 * ob_spec.tedinfo and the rest for what an object of that type points at.
 *
 * The union is the same four bytes in both data models and needs no
 * conversion in either, which is why it can be spelled this way at all.
 * Measured, not assumed: --data-model=small makes a pointer two bytes, so
 * a member lands on the low word, which is where the near address is;
 * --data-model=large makes it four, little-endian with the bank in byte
 * 2, so the whole long reads as a far pointer whose bank is the high
 * word's zero -- bank $00, which is where these structures live.  An
 * OBJECT is 24 bytes and ob_spec sits at offset 12 either way.
 *
 * THE BIT-FIELD MEMBER IS DECLARED BACKWARDS ON PURPOSE.  A box's four
 * bytes are, from the top: character, border thickness, then the colour
 * word as frame / text / pattern / interior.  The 68000's compilers
 * allocate a bit-field from the HIGH end, so gemlib writes that list in
 * reading order and gets that layout; this compiler allocates from the
 * LOW end, so the same list would come out mirrored -- a character read
 * out of the bottom byte.  Written in reverse it lands exactly where the
 * ST puts it, which is what a resource and a port both expect.  Read out
 * of the generated code, not assumed: `.obspec.interiorcol` compiles to
 * `and ##15` on the low word and `.obspec.character` to a load at byte 2
 * with an `xba`, so the two ends are where they should be.
 *
 * The fields are `long` for the same reason.  gemlib writes `unsigned`,
 * which is 32 bits where it comes from and SIXTEEN here, and a 16-bit
 * storage unit cannot hold the whole word -- written that way the struct
 * comes out eight bytes, which would push every field of an OBJECT after
 * ob_spec four bytes along.  With `long` fields it is the four bytes it
 * has to be. */
struct tedinfo;
struct iconblk;
struct bitblk;
struct userblk;
struct ciconblk;

typedef struct {                /* see the note above: reversed on purpose,
                                 * and named as gemlib names them */
    unsigned long interiorcol : 4;
    unsigned long fillpattern : 4;
    unsigned long textcol     : 4;
    unsigned long framecol    : 4;
    signed   long framesize   : 8;  /* negative draws the border outward */
    unsigned long character   : 8;
} OBSPEC_BITS;

typedef union {
    LONG index;                 /* the raw four bytes: a colour word, a
                                 * character, or an address */
    OBSPEC_BITS      obspec;    /* what a G_BOX and its family carry */
    char            *free_string;
    struct tedinfo  *tedinfo;
    struct iconblk  *iconblk;
    struct bitblk   *bitblk;
    struct userblk  *userblk;
    struct ciconblk *ciconblk;
} OBSPEC;

typedef struct {
    WORD   ob_next, ob_head, ob_tail;
    UWORD  ob_type, ob_flags, ob_state;
    OBSPEC ob_spec;
    WORD   ob_x, ob_y, ob_width, ob_height;
} OBJECT;

#define G_BOX      20
#define G_TEXT     21
#define G_BOXTEXT  22
#define G_IMAGE    23
#define G_USERDEF  24   /* declared so a resource that has one loads and a
                         * port compiles; objc_draw draws nothing for it yet
                         * (src/aes/objc.c), so a USERBLK's routine is never
                         * called */
#define G_IBOX     25
#define G_BUTTON   26
#define G_BOXCHAR  27
#define G_STRING   28
#define G_FTEXT    29
#define G_FBOXTEXT 30
#define G_ICON     31
#define G_TITLE    32
#define G_CICON    33   /* a colour icon; drawn as the mono ICONBLK every
                         * CICONBLK begins with, for now */

/* The VDI's standard colour indices. Object types and colour indices
 * share the G_ prefix and nothing else; these are what vsf_color(),
 * vst_color() and vsl_color() take, and a portable backend written
 * against the ST's bindings uses the names rather than the numbers.
 * Values are gemlib's (mt_gem.h) and the VDI's own default palette
 * order: white is 0 and black is 1, which is the pair that surprises
 * anyone expecting the reverse. */
#define G_WHITE     0
#define G_BLACK     1
#define G_RED       2
#define G_GREEN     3
#define G_BLUE      4
#define G_CYAN      5
#define G_YELLOW    6
#define G_MAGENTA   7
#define G_LWHITE    8
#define G_LBLACK    9

/* objc_sysvar: what a program is told about 3D object rendering.  The
 * Compendium's names (6.121).  gem4xe draws no 3D objects, so the
 * inquiry answers zero throughout and setting is refused -- see
 * ob_sysvar in objc.c for why zero is the TRUE answer and not a stub. */
#define SV_INQUIRE  0
#define SV_SET      1
#define LK3DIND     1           /* indicator: does its text move, its colour change */
#define LK3DACT     2           /* activator: the same two */
#define INDBUTCOL   3           /* an indicator's default colour */
#define ACTBUTCOL   4           /* an activator's */
#define BACKGRCOL   5           /* a background object's */
#define AD3DVALUE   6           /* extra pixels each side for the 3D effect */
#define G_LRED     10
#define G_LGREEN   11
#define G_LBLUE    12
#define G_LCYAN    13
#define G_LYELLOW  14
#define G_LMAGENTA 15

#define NONE       0x0000
#define SELECTABLE 0x0001
#define DEFAULT    0x0002
#define EXIT       0x0004
#define EDITABLE   0x0008
#define RBUTTON    0x0010
#define LASTOB     0x0020
#define TOUCHEXIT  0x0040
#define HIDETREE   0x0080
#define NORMAL     0x0000
#define SELECTED   0x0001
#define CROSSED    0x0002
#define CHECKED    0x0004
#define DISABLED   0x0008
#define OUTLINED   0x0010
#define SHADOWED   0x0020
#define WHITEBAK   0x0040       /* an icon over a white ground: leave it */
#define NIL        (-1)
#define TRUE       1
#define FALSE      0
#define ROOT       0
#define MAX_DEPTH  8

/* gemlib's spellings for the same object flags and states. The ST's own
 * bindings carry both -- the bare names above are the AES's originals and
 * the prefixed ones are what mt_gem.h adds -- and portable code written
 * against a modern ST toolchain uses the prefixed set. Aliases, not new
 * values: OF_SELECTABLE IS SELECTABLE. */
#define OF_NONE       NONE
#define OF_SELECTABLE SELECTABLE
#define OF_DEFAULT    DEFAULT
#define OF_EXIT       EXIT
#define OF_EDITABLE   EDITABLE
#define OF_RBUTTON    RBUTTON
#define OF_LASTOB     LASTOB
#define OF_TOUCHEXIT  TOUCHEXIT
#define OF_HIDETREE   HIDETREE
#define OS_NORMAL     NORMAL
#define OS_SELECTED   SELECTED
#define OS_CROSSED    CROSSED
#define OS_CHECKED    CHECKED
#define OS_DISABLED   DISABLED
#define OS_OUTLINED   OUTLINED
#define OS_SHADOWED   SHADOWED
#define OS_WHITEBAK   WHITEBAK

/* VDI attribute constants -- what vsf_interior(), vsf_style() and
 * vst_effects() take. Values are the VDI's own (gemlib mt_gem.h); note
 * IP_SOLID is 7 and FIS_SOLID is 1, which are different things: the first
 * is a FILL PATTERN INDEX within a style, the second is the style. */
#define FIS_HOLLOW      0
#define FIS_SOLID       1
#define FIS_PATTERN     2
#define FIS_HATCH       3
#define FIS_USER        4

#define IP_HOLLOW       0
#define IP_SOLID        7

/* vswr_mode's modes, vsl_type's line types (1..7: the VDI's own
 * numbering, src/vdi/vdi.c vdi_vsl_type -- the Compendium's table on
 * its vsl_type page is off by one) and vsl_ends's end styles. */
#define MD_REPLACE      1
#define MD_TRANS        2
#define MD_XOR          3
#define MD_ERASE        4

#define SOLID           1
#define LDASHED         2
#define DOTTED          3
#define DASHDOT         4
#define DASH            5
#define DASHDOTDOT      6
#define USERLINE        7

#define SQUARE          0
#define ARROWED         1
#define ROUND           2

#define TXT_NORMAL      0x0000
#define TXT_THICKENED   0x0001
#define TXT_LIGHT       0x0002
#define TXT_SKEWED      0x0004
#define TXT_UNDERLINED  0x0008
#define TXT_OUTLINED    0x0010
#define TXT_SHADOWED    0x0020

/* The sixteen raster operations vro_cpyfm() and vrt_cpyfm() take. S_ONLY
 * is the plain copy and the one a blit almost always wants; D_INVERT and
 * NOT_D are two names for the same 10, which is gemlib's own doing. */
#define ALL_WHITE   0
#define S_AND_D     1
#define S_AND_NOTD  2
#define S_ONLY      3
#define NOTS_AND_D  4
#define D_ONLY      5
#define S_XOR_D     6
#define S_OR_D      7
#define NOT_SORD    8
#define NOT_SXORD   9
#define D_INVERT   10
#define NOT_D      10
#define S_OR_NOTD  11
#define NOT_S      12
#define NOTS_OR_D  13
#define NOT_SANDD  14
#define ALL_BLACK  15

/* BITBLK, what a G_IMAGE's ob_spec points at: 14 bytes, the ST's.  A
 * one-plane form drawn transparently in bi_color; bi_pdata is a LONG
 * holding a bank-$00 address, and bi_wb is a width in BYTES. */
typedef struct bitblk {
    LONG bi_pdata;
    WORD bi_wb;
    WORD bi_hl;
    WORD bi_x, bi_y;
    WORD bi_color;
} BITBLK;

/* ICONBLK, what a G_ICON's ob_spec points at: 34 bytes, the ST's.  The
 * three pointers are LONGs holding bank-$00 addresses; the mask and the
 * data are 1-bit rows of ib_wicon/16 words, the text a C string. */
typedef struct iconblk {
    LONG ib_pmask;
    LONG ib_pdata;
    LONG ib_ptext;
    WORD ib_char;               /* colour << 12 | the letter drawn on it */
    WORD ib_xchar, ib_ychar;
    WORD ib_xicon, ib_yicon, ib_wicon, ib_hicon;
    WORD ib_xtext, ib_ytext, ib_wtext, ib_htext;
} ICONBLK;

/* TEDINFO, what a G_TEXT/G_FTEXT/G_BOXTEXT ob_spec points at: 28 bytes,
 * the ST's.  The three pointers are LONGs holding bank-$00 addresses;
 * te_txtlen and te_tmplen are the strings' lengths with the NUL, which
 * the AES fills in at rsrc_load from the file's own text -- so a field
 * an application means to fill in later still carries a buffer of the
 * right length in the resource. */
typedef struct tedinfo {
    LONG te_ptext;              /* what the field holds: the raw places */
    LONG te_ptmplt;             /* "Name: ________.___" */
    LONG te_pvalid;             /* one class character per place */
    WORD te_font, te_fontid;
    WORD te_just;
    WORD te_color;
    WORD te_fontsize;
    WORD te_thickness;
    WORD te_txtlen, te_tmplen;
} TEDINFO;

/* evnt_multi: its flags, a mouse rectangle (five words, as the AES takes
 * them), and the messages the desktop answers. */
#define MU_KEYBD    0x0001
#define MU_BUTTON   0x0002
#define MU_M1       0x0004
#define MU_M2       0x0008
#define MU_MESAG    0x0010
#define MU_TIMER    0x0020

typedef struct {
    WORD m_out;                 /* report leaving the rectangle, not entering */
    WORD m_x, m_y, m_w, m_h;
} MOBLK;

/* The ST's own shapes of three more things a resource or a port names.
 * Declared for a program that parses a .RSC file itself or compiles
 * unchanged from the ST; none of them is what THIS AES hands out or
 * takes, and each line says what it does instead.  Pointers are LONGs,
 * as in ICONBLK and TEDINFO: addresses, not C pointers. */

/* A colour icon's forms, one CICON per depth (22 bytes, the ST's), and
 * the CICONBLK a G_CICON's ob_spec points at in an ST resource FILE.
 * rsrc_load here reads that layout and converts: a loaded G_CICON's
 * ob_spec points at the AES's own 50-byte near record (the mono ICONBLK
 * first, so it draws as a G_ICON), and the colour forms stay in far
 * memory, parsed and not yet drawn.  Read a loaded tree's ob_spec as an
 * ICONBLK, never as a CICONBLK. */
typedef struct {
    WORD num_planes;
    LONG col_data, col_mask;
    LONG sel_data, sel_mask;
    LONG next_res;
} CICON;

typedef struct ciconblk {
    ICONBLK monoblk;
    LONG    mainlist;           /* the CICON chain */
} CICONBLK;

/* menu_popup's argument (AES 36).
 *
 * mn_tree is a 32-bit ADDRESS and not a pointer, for the MFDB's reason:
 * the small data model makes a pointer sixteen bits, and the AES has to
 * read this struct out of a program built either way.  Fill it with a
 * cast --
 *
 *      MENU me;
 *      me.mn_tree = (LONG)(uint32_t)(OBJECT FAR *)tree;
 *
 * mn_menu is the BOX object, the popup's own parent, whose children are
 * the items; mn_item on the way in is the item to put under the pointer,
 * which is what xpos/ypos actually place, and -1 means the first.
 * mn_scroll is read and handed straight back: this AES does not scroll a
 * menu, and appl_getinfo(AES_MENU) says so. */
typedef struct {
    LONG mn_tree;
    WORD mn_menu, mn_item;
    WORD mn_scroll, mn_keystate;
} MENU;

/* A G_USERDEF's ob_spec points at a USERBLK, and the AES would call
 * ub_code with a PARMBLK; here it does not (G_USERDEF above). */
typedef struct {
    LONG pb_tree;
    WORD pb_obj, pb_prevstate, pb_currstate;
    WORD pb_x, pb_y, pb_w, pb_h;
    WORD pb_xc, pb_yc, pb_wc, pb_hc;
    LONG pb_parm;
} PARMBLK;

typedef struct userblk {
    LONG ub_code;               /* WORD (*)(PARMBLK *) on the ST */
    LONG ub_parm;
} USERBLK;

/* evnt_multi's kstate and evnt_button's: the shift keys as the ST reports
 * them (The Atari Compendium, evnt_keybd/graf_mkstate). */
#define K_RSHIFT    0x0001
#define K_LSHIFT    0x0002
#define K_CTRL      0x0004
#define K_ALT       0x0008
#define K_CAPSLOCK  0x0010

#define MN_SELECTED 10
#define WM_REDRAW   20
#define WM_TOPPED   21
#define WM_CLOSED   22
#define WM_FULLED   23
#define WM_ARROWED  24
#define WM_HSLID    25
#define WM_VSLID    26
#define WM_SIZED    27
#define WM_MOVED    28
#define WM_NEWTOP   29
#define WM_UNTOPPED 30  /* AES 4's: a program may test for them, this */
#define WM_ONTOP    31  /* AES sends neither -- it is single-application */
#define AC_OPEN     40
#define AC_CLOSE    41
/* MultiTOS's shutdown handshake (MESSAGE.H).  Declared so a port that
 * switches on a message code compiles and so a shell can send AP_TERM
 * some day; this AES sends none of them, having one application and no
 * process to ask anything of. */
#define AP_TERM     50
#define AP_TFAIL    51
#define AP_TSUCCESS 52

/* wind_create kinds, wind_get / wind_set fields, wind_update codes */
#define NAME    0x0001
#define CLOSER  0x0002
#define FULLER  0x0004
#define MOVER   0x0008
#define INFO    0x0010
#define SIZER   0x0020
#define UPARROW 0x0040
#define DNARROW 0x0080
#define VSLIDE  0x0100
#define LFARROW 0x0200
#define RTARROW 0x0400
#define HSLIDE  0x0800
#define WF_KIND     1
#define WF_NAME     2
#define WF_INFO     3
#define WF_WORKXYWH 4
#define WF_CURRXYWH 5
#define WF_PREVXYWH 6
#define WF_FULLXYWH 7
#define WF_HSLIDE   8
#define WF_VSLIDE   9
#define WF_TOP      10
#define WF_FIRSTXYWH 11
#define WF_NEXTXYWH 12
#define WF_NEWDESK  14
#define WF_HSLSIZ   15
#define WF_VSLSIZ   16
/* WF_SCREEN answers the AES's menu/alert save buffer and its length.
 * gem4xe's is in VRAM (vdi_save_form), which is not in the address
 * space, so there is nothing to lend and all four words are 0 -- the
 * Compendium warns an application off borrowing it in any case, and
 * TOS 1.02 returns 0 for the length by mistake. */
#define WF_SCREEN   17
/* WF_OWNER and WF_BOTTOM are AES 4's and gated there on appl_getinfo,
 * which gem4xe does not serve; wind_get answers them anyway, because a
 * port that asks unguarded is better served with the truth than with a
 * refusal.  WF_OWNER: the owner's ap_id, the open status, and the
 * handles directly above and below it -- 0 (the desk) for neither.
 * WF_BOTTOM is wind_GET only; wind_set(WF_BOTTOM), which would send a
 * window to the bottom, is not served. */
#define WF_OWNER    20
#define WF_BOTTOM   25
/* WM_ARROWED's word 4 */
#define WA_UPPAGE   0
#define WA_DNPAGE   1
#define WA_UPLINE   2
#define WA_DNLINE   3
#define WA_LFPAGE   4
#define WA_RTPAGE   5
#define WA_LFLINE   6
#define WA_RTLINE   7
/* objc_edit's kind */
#define ED_START    0
#define ED_INIT     1
#define ED_CHAR     2
#define ED_END      3
#define WC_BORDER   0
#define WC_WORK     1
#define END_UPDATE  0
#define BEG_UPDATE  1
#define END_MCTRL   2
#define BEG_MCTRL   3

/* form_dial's types; graf_mouse's shapes and modes; rsrc_gaddr's types */
#define FMD_START   0
#define FMD_GROW    1
#define FMD_SHRINK  2
#define FMD_FINISH  3
#define ARROW       0
#define TEXT_CRSR   1
#define HOURGLASS   2
#define BUSYBEE     2
#define POINT_HAND  3
#define FLAT_HAND   4
#define THIN_CROSS  5
#define THICK_CROSS 6
#define OUTLN_CROSS 7
#define USER_DEF    255
#define M_OFF       256
#define M_ON        257
#define M_SAVE      258
#define M_RESTORE   259
#define M_PREVIOUS  260
#define R_TREE      0
#define R_OBJECT    1
#define R_ICONBLK   3
#define R_STRING    5
#define R_FRSTR     15

/* -- The bindings an application uses; src/app/gemlib.c.  The arrays are
 * the application's own and are left in place after each call so that a
 * caller can look at what came back. */
extern WORD contrl[12], intin[128], ptsin[16], intout[45], ptsout[12];
extern WORD control[5], global[15], int_in[16], int_out[7];
extern LONG addr_in[3], addr_out[1];

void v_opnvwk(WORD *work_in, WORD *handle, WORD *work_out);
void v_clsvwk(WORD handle);
void vr_recfl(WORD handle, WORD *pxy);
void v_pline(WORD handle, WORD count, WORD *pxy);
void v_gtext(WORD handle, WORD x, WORD y, const char *s);
WORD vsf_color(WORD handle, WORD color);
WORD vsf_interior(WORD handle, WORD style);
WORD vsl_color(WORD handle, WORD color);
WORD vst_color(WORD handle, WORD color);

/* An MFDB, the raster calls' form descriptor, laid out as the VDI has
 * had it since 1984 -- with one change forced by the compiler:
 * fd_addr is a 32-bit word, not a pointer, because the small data
 * model makes `void *` 16 bits and would shift every field after it
 * (src/vdi/vdi.h has the account).  A form lives in bank $00 here, so
 * only the low half is ever used; 0 means the screen. */
typedef struct {
    uint32_t fd_addr;
    WORD fd_w, fd_h;
    WORD fd_wdwidth;            /* (fd_w + 15) / 16 -- WORDS, per the spec */
    WORD fd_stand;              /* 0 device-specific, 1 VDI standard */
    WORD fd_nplanes;
    WORD fd_r1, fd_r2, fd_r3;
} MFDB;

/* The rest of the VDI, in the names and the argument order it has had
 * since 1984.  Absent by choice: cell array (10, 27), the valuator
 * (29) and 34, which the driver answers with v_nop -- a binding that
 * silently does nothing is worse than a name that is not there. */
void v_opnwk(WORD *work_in, WORD *handle, WORD *work_out);
void v_clswk(WORD handle);
void v_clrwk(WORD handle);
void v_updwk(WORD handle);      /* a screen has nothing to write out */
void v_enter_cur(WORD handle);
void v_exit_cur(WORD handle);
void v_pmarker(WORD handle, WORD count, const WORD *pxy);
void v_fillarea(WORD handle, WORD count, const WORD *pxy);
void v_bar(WORD handle, const WORD *pxy);
void v_arc(WORD handle, WORD x, WORD y, WORD radius, WORD begang, WORD endang);
void v_pieslice(WORD handle, WORD x, WORD y, WORD radius, WORD begang,
                WORD endang);
void v_circle(WORD handle, WORD x, WORD y, WORD radius);
void v_ellipse(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad);
void v_ellarc(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad,
              WORD begang, WORD endang);
void v_ellpie(WORD handle, WORD x, WORD y, WORD xrad, WORD yrad,
              WORD begang, WORD endang);
void v_rbox(WORD handle, const WORD *pxy);
void v_rfbox(WORD handle, const WORD *pxy);
void v_justified(WORD handle, WORD x, WORD y, const char *s, WORD length,
                 WORD word_space, WORD char_space);
void vst_height(WORD handle, WORD height, WORD *char_width, WORD *char_height,
                WORD *cell_width, WORD *cell_height);
WORD vst_rotation(WORD handle, WORD angle);
void vs_color(WORD handle, WORD index, const WORD *rgb);
WORD vsl_type(WORD handle, WORD style);
WORD vsl_width(WORD handle, WORD width);
WORD vsm_type(WORD handle, WORD symbol);
WORD vsm_height(WORD handle, WORD height);
WORD vsm_color(WORD handle, WORD color);
WORD vst_font(WORD handle, WORD font);
WORD vsf_style(WORD handle, WORD style);
void vq_color(WORD handle, WORD index, WORD flag, WORD *rgb);
WORD v_locator(WORD handle, WORD x, WORD y, WORD *xout, WORD *yout,
               WORD *term);
WORD vsm_choice(WORD handle, WORD *choice);
/* The string device answers ONE key per call, as a GEM key code -- scan
 * code over ASCII, the value evnt_keybd hands out -- or 0 if none is
 * waiting.  That is this driver's convention, not the ST's vsm_string
 * (src/vdi/vdi.c), which is why it does not wear that name. */
WORD v_string(WORD handle, WORD *key);
WORD vswr_mode(WORD handle, WORD mode);
WORD vsin_mode(WORD handle, WORD dev, WORD mode);
void vql_attributes(WORD handle, WORD *attr);   /* type, colour, mode, width */
void vqm_attributes(WORD handle, WORD *attr);   /* type, colour, mode, height */
void vqf_attributes(WORD handle, WORD *attr);   /* style, colour, index,
                                                 * mode, perimeter */
void vqt_attributes(WORD handle, WORD *attr);   /* six words and four points */
void vst_alignment(WORD handle, WORD hin, WORD vin, WORD *hout, WORD *vout);
void vq_extnd(WORD handle, WORD owflag, WORD *work_out);
void v_contourfill(WORD handle, WORD x, WORD y, WORD index);
WORD vsf_perimeter(WORD handle, WORD vis);
void v_get_pixel(WORD handle, WORD x, WORD y, WORD *pel, WORD *index);
WORD vst_effects(WORD handle, WORD effects);
WORD vst_point(WORD handle, WORD point, WORD *char_width, WORD *char_height,
               WORD *cell_width, WORD *cell_height);
void vsl_ends(WORD handle, WORD beg_style, WORD end_style);
void vro_cpyfm(WORD handle, WORD mode, const WORD *pxy, const MFDB *src,
               const MFDB *dst);
void vr_trnfm(WORD handle, const MFDB *src, const MFDB *dst);
void vsc_form(WORD handle, const WORD *form);   /* the 37 words of a cursor */
void vsf_udpat(WORD handle, const WORD *pattern, WORD planes);
void vsl_udsty(WORD handle, WORD pattern);
void vqin_mode(WORD handle, WORD dev, WORD *mode);
void vqt_extent(WORD handle, const char *s, WORD *extent);  /* four points */
WORD vqt_width(WORD handle, WORD ch, WORD *cell_width, WORD *left_delta,
               WORD *right_delta);
/* A handler is 24 bits under the large code model, so a vector is a
 * LONG here rather than a native function pointer. */
WORD vex_timv(WORD handle, LONG newv, LONG *oldv);   /* answers the tick, in ms */
void vex_butv(WORD handle, LONG newv, LONG *oldv);
void vex_motv(WORD handle, LONG newv, LONG *oldv);
void vex_curv(WORD handle, LONG newv, LONG *oldv);
WORD vst_load_fonts(WORD handle, WORD select);

/* Is GDOS installed? On the ST this is not a VDI opcode at all -- it is a
 * magic `move.l #-2,d0; trap #2` (Compendium 7.92, "OPCODE N/A"), and the
 * answer distinguishes FontGDOS from SpeedoGDOS from none. gem4xe has no
 * GDOS: the VDI's device independence lives in v_opnwk's device id here,
 * not in a loadable driver layer. So this answers 0, which is what the
 * older bindings return for "none" and what a caller guarding a
 * vst_load_fonts() with it needs to hear. */
WORD vq_gdos(void);

/* The current font's vertical distances -- dist[3] is the ascent and
 * dist[1] the descent, which is what a layout engine needs to turn a face
 * into a line height. FOUR distances are written, not five: see gemlib.c. */
void vqt_fontinfo(WORD handle, WORD *first, WORD *last, WORD *dist,
                  WORD *width, WORD *effects);
void vst_unload_fonts(WORD handle, WORD select);
void vrt_cpyfm(WORD handle, WORD mode, const WORD *pxy, const MFDB *src,
               const MFDB *dst, const WORD *color);
void v_show_c(WORD handle, WORD reset);
void v_hide_c(WORD handle);
void vq_mouse(WORD handle, WORD *pstatus, WORD *x, WORD *y);
void vq_key_s(WORD handle, WORD *state);
void vs_clip(WORD handle, WORD clip_flag, const WORD *pxy);
WORD vqt_name(WORD handle, WORD element, char *name);   /* name[33] */

WORD appl_init(void);
WORD appl_exit(void);
/* appl_yield -- give the other processes a turn.  This AES schedules
 * cooperatively, so a program that works for a long time between evnt_
 * calls stops every accessory dead; calling this in the loop is how it
 * does not.  It answers at once when there is nobody else to run. */
WORD appl_yield(void);

WORD evnt_keybd(void);          /* scan code << 8 | ASCII, as on the ST */
WORD evnt_button(WORD clicks, UWORD mask, UWORD state,
                 WORD *mx, WORD *my, WORD *mb, WORD *ks);
WORD evnt_mesag(WORD *msg);     /* eight words */
WORD evnt_timer(UWORD lo, UWORD hi);
/* evnt_multi in the ST's shape -- the twenty-three arguments every port
 * arrives with (The Atari Compendium, 6.10), the two mouse rectangles as
 * five words each: flags, x, y, w, h.  msg is eight words, filled when
 * MU_MESAG comes back; the timer is lo then hi.  A program written here
 * may prefer evnt_multi_moblk below, the same call with the rectangles
 * as MOBLKs and 0 for one not asked for; the AES sees no difference. */
WORD evnt_multi(WORD flags, WORD bclk, WORD bmsk, WORD bst,
                WORD m1flags, WORD m1x, WORD m1y, WORD m1w, WORD m1h,
                WORD m2flags, WORD m2x, WORD m2y, WORD m2w, WORD m2h,
                WORD *msg, WORD tlo, WORD thi,
                WORD *mx, WORD *my, WORD *mb, WORD *ks, WORD *kr, WORD *br);
WORD evnt_multi_moblk(UWORD flags, WORD bclk, UWORD bmsk, UWORD bst,
                      const MOBLK *m1, const MOBLK *m2, WORD *msg,
                      UWORD tlo, UWORD thi,
                      WORD *mx, WORD *my, WORD *mb, WORD *ks, WORD *kr, WORD *br);

WORD menu_bar(OBJECT *tree, WORD showit);
WORD menu_icheck(OBJECT *tree, WORD item, WORD check);
WORD menu_ienable(OBJECT *tree, WORD item, WORD enable);
WORD menu_tnormal(OBJECT *tree, WORD title, WORD normal);

/* Tree surgery at run time: objc_add links child as parent's last child,
 * objc_delete unlinks an object from its parent's chain and leaves the
 * object itself alone.  Neither touches the screen -- redraw what you
 * changed.  objc_delete answers 0 for the root, or for an object that is
 * not in its parent's chain. */
WORD objc_add(OBJECT *tree, WORD parent, WORD child);
WORD objc_delete(OBJECT *tree, WORD obj);
WORD objc_draw(OBJECT *tree, WORD start, WORD depth, WORD x, WORD y, WORD w, WORD h);
WORD objc_find(OBJECT *tree, WORD start, WORD depth, WORD mx, WORD my);
WORD objc_offset(OBJECT *tree, WORD obj, WORD *x, WORD *y);
WORD objc_change(OBJECT *tree, WORD obj, WORD resvd, WORD x, WORD y, WORD w, WORD h,
                 WORD state, WORD redraw);
WORD objc_sysvar(WORD mode, WORD which, WORD in1, WORD in2,
                 WORD *out1, WORD *out2);
/* newpos: 0 puts the object first among its siblings (the bottom of the
 * stack), NIL last (the top), n after the nth. */
WORD objc_order(OBJECT *tree, WORD obj, WORD newpos);

WORD form_do(OBJECT *tree, WORD start);
WORD form_dial(WORD type, WORD x1, WORD y1, WORD w1, WORD h1,
               WORD x2, WORD y2, WORD w2, WORD h2);
WORD form_alert(WORD defbut, const char *s);  /* s: near, or far up to 511 bytes */
WORD form_error(WORD n);
WORD form_center(OBJECT *tree, WORD *x, WORD *y, WORD *w, WORD *h);

WORD graf_handle(WORD *wchar, WORD *hchar, WORD *wbox, WORD *hbox);
WORD graf_mouse(WORD mode, const WORD *form);  /* form only for USER_DEF */
WORD graf_growbox(WORD x1, WORD y1, WORD w1, WORD h1, WORD x2, WORD y2, WORD w2, WORD h2);
WORD graf_shrinkbox(WORD x1, WORD y1, WORD w1, WORD h1, WORD x2, WORD y2, WORD w2, WORD h2);
/* graf_mkstate's key state, the ST's bits (biosdefs.h).  This machine
 * can only be asked about SHIFT while no key is down: POKEY reports the
 * shift key on a line of its own and control only in the code of a key
 * that is being held (src/vdi/vdi.c, vq_key_s). */
#define MODE_RSHIFT 0x01
#define MODE_LSHIFT 0x02
#define MODE_CTRL   0x04
#define MODE_ALT    0x08

WORD graf_mkstate(WORD *mx, WORD *my, WORD *mb, WORD *ks);
WORD graf_dragbox(WORD w, WORD h, WORD sx, WORD sy,
                  WORD bx, WORD by, WORD bw, WORD bh, WORD *px, WORD *py);

WORD wind_create(WORD kind, WORD x, WORD y, WORD w, WORD h);
WORD wind_open(WORD handle, WORD x, WORD y, WORD w, WORD h);
WORD wind_get(WORD handle, WORD field, WORD *o1, WORD *o2, WORD *o3, WORD *o4);
WORD wind_set(WORD handle, WORD field, WORD w1, WORD w2, WORD w3, WORD w4);
WORD wind_close(WORD handle);
WORD wind_delete(WORD handle);
WORD wind_find(WORD x, WORD y);
WORD wind_update(WORD code);
WORD wind_calc(WORD type, WORD kind, WORD x, WORD y, WORD w, WORD h,
               WORD *ox, WORD *oy, WORD *ow, WORD *oh);
/* wind_set's WF_NEWDESK takes the tree as the ST does: its address in
 * two words, high first (0 here: the tree is in bank $00), then the
 * object to draw from. */
#define wind_newdesk(tree, root) \
    wind_set(0, WF_NEWDESK, 0, (WORD)(uint16_t)(tree), (root), 0)

/* rsrc_load takes the resource from gem4xe's application pool when it
 * fits, and -- for a program compiled --data-model=large, whose binding
 * says it can take one -- from far memory when it does not
 * (docs/far-trees.md).  rsrc_gaddr answers a bank-$00 address to a
 * small-data program, which is all such a program can hold, and a 24-bit
 * one to a large-data program. */
WORD rsrc_load(const char *name);
WORD rsrc_free(void);
WORD rsrc_gaddr(WORD type, WORD index, void **addr);

/* shel_write's doex: what the shell does once this program returns.  The
 * tail is the ST's: a length byte, then the characters. */
#define SHW_NOEXEC   0          /* back to the desktop */
#define SHW_EXEC     1          /* run cmd, then the desktop again */
#define SHW_SHUTDOWN 4          /* leave GEM (the desktop's Quit) */
WORD shel_write(WORD doex, WORD isgr, WORD iscr, const char *cmd, const char *tail);
/* The shell buffer: 4192 bytes the AES keeps between programs (the ST's
 * SIZE_SHELBUF), where the desktop leaves its DESKTOP.INF text.  The
 * application's copy may be far -- only bytes cross. */
#define SIZE_SHELBUF 4192
WORD shel_get(void FAR *buffer, WORD len);
WORD shel_put(const void FAR *data, WORD len);

/* The rest of the AES. */
/* The message pipe, for messages evnt_mesag cannot carry: `length` is in
 * BYTES and must be a whole number of 16-byte messages -- one is the
 * usual, four the most appl_write will take.  appl_read waits, and reads
 * only your own pipe; both buffers may be far. */
WORD appl_read(WORD id, WORD length, WORD *msg);
WORD appl_write(WORD id, WORD length, const WORD *msg);
WORD evnt_mouse(WORD flags, WORD x, WORD y, WORD w, WORD h,
                WORD *mx, WORD *my, WORD *button, WORD *kstate);
WORD evnt_dclick(WORD rate, WORD setit);
WORD menu_text(OBJECT *tree, WORD item, const char *text);
WORD menu_register(WORD pid, const char *str);

/* menu_popup puts the MENU box (above) up at (xpos, ypos), tracks it
 * until a click, and takes it down.  TRUE with mdata->mn_item set when an
 * item was chosen; FALSE when none was, and then ONLY mdata->mn_keystate
 * is written -- the four words before it are left as you had them, which
 * is what both an ST ROM and EmuTOS do.
 *
 * NO SUBMENUS, and no popup from a popup: the AES's screen save is one
 * buffer, so one of these can be open at a time.  appl_getinfo(AES_MENU)
 * answers 0 for sub-menus and 1 for popups, which is the way to ask. */
WORD menu_popup(const MENU *me, WORD xpos, WORD ypos, MENU *mdata);

/* SUB-MENUS: a menu item that carries a menu of its own, which opens
 * beside it while the pointer rests on it.
 *
 *   menu_attach(ME_ATTACH, tree, item, &md)   attaches md's box to item
 *   menu_attach(ME_INQUIRE, tree, item, &md)  fills md with what is there
 *   menu_attach(ME_REMOVE, tree, item, 0)     takes it off again
 *
 * THE ITEM MUST BE A G_STRING AND AT LEAST TWO CHARACTERS LONG, and its
 * text must be writable, because attaching writes a right-arrow
 * character two bytes from the end of it -- the ROM's mark, so a tree
 * marked here reads the same to anything that inspects it.  The ROM
 * never checks either; this refuses rather than write outside a short
 * string.  Removing puts a SPACE there, not what was there before.
 *
 * One level only: a submenu's own items cannot carry sub-menus, and
 * neither can a popup's.  Ask appl_getinfo(AES_MENU) rather than
 * assuming -- its first word is sub-menus, its second popups, its third
 * scrolling (which is not here), its fourth whether MN_SELECTED's words
 * 5 to 7 carry the tree the item came from, which they do.
 *
 * menu_istart reads or sets which item of the submenu lines up with the
 * parent item; it answers the item, or 0 for an error. */
/* The five numbers the AES runs sub-menus by, in MILLISECONDS except
 * the height, which is in items.  ONE IS LIVE here: mn_display, how long
 * the pointer must rest on an item before its submenu opens.  The other
 * four are kept and handed back -- there is no drag tracking and nothing
 * scrolls (appl_getinfo(AES_MENU) says so) -- and a SET applies a field
 * only when it is not negative, so -1 means "leave this one". */
typedef struct {
    LONG mn_display;            /* before a submenu opens          (200) */
    LONG mn_drag;               /* the diagonal grace period     (10000) */
    LONG mn_delay;              /* before a scroll arrow repeats   (250) */
    LONG mn_speed;              /* between its repeats               (0) */
    WORD mn_height;             /* items before a menu scrolls      (16) */
} MN_SET;
WORD menu_settings(WORD flag, MN_SET *set);
/* The ROM writes bare 0 and 1 (MN_SUBMN.C) and the Compendium does
 * not document the call at all, so the names are this port's --
 * MN_SET itself is taken, by the struct. */
#define MNS_GET     0
#define MNS_SET     1

WORD menu_attach(WORD flag, OBJECT *tree, WORD item, MENU *mdata);
WORD menu_istart(WORD flag, OBJECT *tree, WORD imenu, WORD item);
#define ME_INQUIRE  0
#define ME_ATTACH   1
#define ME_REMOVE   2
#define MIS_INQUIRE 0
#define MIS_SET     1
WORD appl_find(const char *fname);      /* EIGHT chars, blank-padded */

/* appl_getinfo (AES 130) -- what this AES has, asked one subject at a
 * time.  The modes are the Compendium's and gemlib's; the higher ones
 * gemlib carries (64, 65, 96-99, and WINX's 22360) belong to MagiC and
 * N.AES and are refused here, as any mode this AES does not know is.
 *
 * IT ANSWERS NON-ZERO FOR A MODE IT KNOWS and zero for one it does not.
 * The Compendium says the opposite in prose -- "returns 1 if an error
 * occurred or 0 otherwise", p.368 -- and it is wrong: the ROM sets
 * ret = TRUE and only the default case clears it (MULTITOS GEMAPLIB.C),
 * gemlib documents "0 if an error occurred or non-zero otherwise", and
 * every caller in cflib tests it as a truth value.
 *
 * VERSION.  The Compendium makes this AES 4.00 and gem4xe reports 1.40,
 * so a program that checks the version first will never call it -- which
 * is correct, because gem4xe is not an AES 4.  It is served for the
 * programs that ask anyway, and because answering "no" one subject at a
 * time is better than an unknown opcode's -1.  (The third-party way to
 * advertise it below 4.00 is a process named "?AGI" for appl_find, which
 * cflib's own xgetinfo.c tests for; gem4xe registers no such process,
 * and nothing local documents what it should answer.) */
#define AES_LARGEFONT   0
#define AES_SMALLFONT   1
#define AES_SYSTEM      2
#define AES_LANGUAGE    3
#define AES_PROCESS     4
#define AES_PCGEM       5
#define AES_INQUIRE     6
#define AES_WDIALOG     7       /* "reserved" in the Compendium; Mag!X's */
#define AES_MOUSE       8
#define AES_MENU        9
#define AES_SHELL       10
#define AES_WINDOW      11
#define AES_MESSAGE     12
#define AES_OBJECT      13
#define AES_FORM        14
/* AES_LARGEFONT / AES_SMALLFONT's ap_gout3 */
#define SYSTEM_FONT     0
#define OUTLINE_FONT    1
/* AES_LANGUAGE's ap_gout1 */
#define AESLANG_ENGLISH 0
#define AESLANG_GERMAN  1
#define AESLANG_FRENCH  2
#define AESLANG_SPANISH 4
#define AESLANG_ITALIAN 5
#define AESLANG_SWEDISH 6
WORD appl_getinfo(WORD ap_gtype, WORD *ap_gout1, WORD *ap_gout2,
                  WORD *ap_gout3, WORD *ap_gout4);
/* gemlib's convenience, which cflib expects to exist: feature-test, then
 * ask.  On gem4xe the test is settled at compile time -- the AES either
 * serves appl_getinfo or it does not, and this kit is the one that does
 * -- so it forwards, and a port needs no shim of its own. */
WORD appl_xgetinfo(WORD ap_gtype, WORD *ap_gout1, WORD *ap_gout2,
                   WORD *ap_gout3, WORD *ap_gout4);
WORD objc_edit(OBJECT *tree, WORD obj, WORD in_char, WORD *idx, WORD kind);
WORD form_keybd(OBJECT *tree, WORD obj, WORD nxt_obj, WORD thechar,
                WORD *pnxt_obj, WORD *pchar);
WORD form_button(OBJECT *tree, WORD obj, WORD clks, WORD *pnxt_obj);
/* graf_mbox / graf_movebox (72): the same call under both spellings --
 * the Compendium renamed it and an ST source may carry either.  A ghost
 * box walked from (sx,sy) to (ex,ey), for a visual clue.
 * graf_slidebox (76): drag a child within its parent, answering where
 * it ended up, 0..1000 along -- what a dialog's slider is built from
 * (make the bar TOUCHEXIT and call this when it is clicked). */
/* wind_new (109): close and delete every window, and put back
 * wind_update's locks and the pointer's hide count -- the tidy-up a
 * program can ask for after something went wrong.  It leaves the MENU
 * BAR alone; see src/aes/wind.c for why that differs from one of the
 * two donors.  The return is reserved: do not test it. */
WORD wind_new(void);
WORD graf_mbox(WORD w, WORD h, WORD sx, WORD sy, WORD ex, WORD ey);
WORD graf_movebox(WORD w, WORD h, WORD sx, WORD sy, WORD ex, WORD ey);
WORD graf_slidebox(OBJECT *tree, WORD parent, WORD obj, WORD orient);
WORD graf_rubbox(WORD x, WORD y, WORD w, WORD h, WORD *pw, WORD *ph);
WORD graf_watchbox(OBJECT *tree, WORD obj, WORD instate, WORD outstate);
/* fsel_input / fsel_exinput answer their `button` with one of these.  The
 * Compendium names both (fsel_exinput: "FSEL_CANCEL (0) ... FSEL_OK (1)"),
 * and an application that tests the value by its name rather than by 1 is
 * the normal way ST code is written. */
#define FSEL_CANCEL  0
#define FSEL_OK      1
WORD fsel_input(char *path, char *sel, WORD *button);
WORD fsel_exinput(char *path, char *sel, WORD *button, const char *label);
WORD rsrc_saddr(WORD type, WORD index, void *addr);
WORD rsrc_obfix(OBJECT *tree, WORD obj);
/* The scrap manager keeps a DIRECTORY, not the scrap: the clipboard is
 * files called SCRAP.* in it, so two programs agree on a place rather
 * than on a format.  The path is your buffer and must be near, as
 * shel_read's is -- a path can outrun the 63-byte far-string bounce. */
WORD scrp_read(char *path);
WORD scrp_write(const char *path);
/* scrp_clear deletes every SCRAP.* in that directory.  It is PC-GEM's:
 * no Atari AES has opcode 82, so a program that must also run on an ST
 * does the walk itself, as the Compendium tells it to. */
WORD scrp_clear(void);
WORD shel_read(char *cmd, char *tail);
WORD shel_find(char *path);
WORD shel_envrn(char **value, const char *name);

/* -- The GRECT half of the library.
 *
 * rc_intersect and rc_union are Atari's own (FALCON.AES/FUNCTION.C): plain
 * arithmetic on two rectangles, no AES call in either, and every binding
 * library for the ST exposes them because the AES's own redraw loop is
 * written with them -- walk the rectangle list, intersect each against
 * what you meant to draw, draw if anything is left.
 *
 * The `_grect` and `_str` spellings below are gemlib's, not the ROM's:
 * one GRECT where the call underneath takes four loose words, which is
 * how ST source has been written for twenty years.  They are declared
 * here for the same reason VdiHdl is -- they cost nothing, and they are
 * the difference between a real ST application compiling and not. */
WORD rc_intersect(const GRECT *src, GRECT *dst);
void rc_union(const GRECT *src, GRECT *dst);

WORD wind_create_grect(WORD kind, const GRECT *r);
WORD wind_open_grect(WORD handle, const GRECT *r);
WORD wind_get_grect(WORD handle, WORD field, GRECT *r);
WORD wind_set_grect(WORD handle, WORD field, const GRECT *r);
WORD wind_calc_grect(WORD type, WORD kind, const GRECT *in, GRECT *out);
/* WF_NAME / WF_INFO: the string must be NEAR and must outlive the window --
 * the AES keeps the pointer and redraws the title from it.  A far address
 * is refused (the call answers 0) rather than cut to 16 bits. */
WORD wind_set_str(WORD handle, WORD field, const char *str);
WORD form_center_grect(OBJECT *tree, GRECT *r);
WORD form_dial_grect(WORD flag, const GRECT *little, const GRECT *big);
WORD objc_draw_grect(OBJECT *tree, WORD start, WORD depth, const GRECT *r);

/* -- GEMDOS, the ST's osbind names.  Pointers are far so that a buffer
 * Malloc gave out -- which is far memory -- can be read into directly;
 * a near pointer widens to one.  Errors are the ST's negative numbers,
 * src/sys/gemdos.h.  Every call TOS 1.04's GEMDOS has is here, and what
 * each one can mean on this machine is written at its function in
 * src/sys/gemdos.c. */
#define E_OK      0L
#define EINVFN  -32L
#define EFILNF  -33L
#define EPTHNF  -34L
#define ENHNDL  -35L
#define EACCDN  -36L
#define EIHNDL  -37L
#define ENSMEM  -39L
#define EIMBA   -40L
#define EDRIVE  -46L
#define ENMFIL  -49L
#define EGSBF   -67L
#define EPLFMT  -66L

#define FA_RDONLY  0x01
#define FA_HIDDEN  0x02
#define FA_SYSTEM  0x04
#define FA_VOLUME  0x08
#define FA_SUBDIR  0x10
#define FA_ARCHIVE 0x20
#define FA_CHANGED 0x20         /* the same bit, spelled as Pure C and
                                 * gemlib spell it */

/* The longest path GEMDOS composes, NUL included (src/sys/gemdos.c,
 * GD_PATHMAX).  A buffer an application hands to Dgetpath, or builds a
 * search spec in, wants to be this big; <macros.h> spells it PATH_MAX,
 * which is the name mintlib uses and Calypsi's <limits.h> does not have. */
#define GEM_PATH_MAX 128

typedef struct {                /* the ST's, 44 bytes */
    char  d_reserved[21];
    char  d_attrib;
    UWORD d_time;
    UWORD d_date;
    LONG  d_length;             /* unsigned on the ST; long is enough here */
    char  d_fname[14];
} DTA;

typedef struct {                /* Dfree's answer, in clusters of 1 sector */
    LONG b_free, b_total, b_secsiz, b_clsiz;
} DISKINFO;

WORD Sversion(void);
WORD Dsetdrv(WORD drive);       /* returns the drive map */
WORD Dgetdrv(void);
LONG Dsetpath(const char FAR *path);
LONG Dgetpath(char FAR *buf, WORD drive);
LONG Dcreate(const char FAR *path);
LONG Ddelete(const char FAR *path);
LONG Dfree(DISKINFO FAR *info, WORD drive);
void Fsetdta(DTA FAR *dta);
DTA FAR *Fgetdta(void);
LONG Fsfirst(const char FAR *spec, WORD attr);
LONG Fsnext(void);
LONG Fopen(const char FAR *name, WORD mode);
LONG Fcreate(const char FAR *name, WORD attr);
LONG Fclose(WORD handle);
LONG Fread(WORD handle, LONG count, void FAR *buf);
LONG Fwrite(WORD handle, LONG count, const void FAR *buf);
LONG Fseek(LONG offset, WORD handle, WORD mode);
LONG Fdelete(const char FAR *name);
LONG Frename(const char FAR *oldname, const char FAR *newname);
LONG Fattrib(const char FAR *name, WORD wflag, WORD attr);
/* There is no C heap: an application's heap block is zero bytes, and
 * malloc/free refuse at link time (src/sys/clib.c).  Far memory comes from
 * Malloc. */
LONG Malloc(LONG size);         /* -1 asks how much is left; 0: no room */
LONG Mfree(void FAR *block);

LONG Fdatime(WORD *timeptr, WORD handle, WORD wflag);   /* two words: time, date */
WORD Tgetdate(void);
WORD Tgettime(void);

/* MiNT's clock, and the one to pace anything by: seconds since 1970 and
 * microseconds, from a ~4 kHz timer the system keeps, monotonic and exact
 * to a quarter of a millisecond.  On an ST this exists under MiNT and
 * answers EINVFN under plain TOS, where mintlib falls back to the 200 Hz
 * system variable; that variable is not reachable here, so this is the
 * one door.  `tz` may be 0 and answers zeros if not.  clock() in this
 * kit is built on it (gemlib.c). */
struct timeval  { LONG tv_sec, tv_usec; };
struct timezone { WORD tz_minuteswest, tz_dsttime; };
LONG Tgettimeofday(struct timeval FAR *tv, struct timezone FAR *tz);

/* gem4xe's own (0x1F0): the DOS's command processor -- SpartaDOS X's --
 * given `line`, run to completion with GEM's screen left as it is, and
 * every byte it printed caught in `out`, `max` bytes of it (a Malloc'd
 * buffer; the DOS's EOL, $9B, ends its lines).  The bytes caught, or
 * EINVFN on a DOS with no such entry; Psystem(0, 0, 0) asks only that.
 * The command runs on a console it cannot show, so one that asks a
 * question has nobody to answer it. */
LONG Psystem(const char FAR *line, void FAR *out, LONG max);

/* The C functions, through the ST's standard handles: 0 and 1 the
 * console, a VT-52 on GEM's screen; 2 aux:, with nothing behind it here;
 * 3 prn:, the printer GEM4XE.CFG names.  Fforce points one at a file or
 * another device, Fdup keeps one to put back.  An input returns a key as
 * the ST does: ASCII in the low byte, the scan code in the third. */
#define GSH_CONIN   0
#define GSH_CONOUT  1
#define GSH_AUX     2
#define GSH_PRN     3
#define DEV_READY  -1
#define DEV_BUSY    0
LONG Cconin(void);
void Cconout(WORD c);
WORD Cauxin(void);
void Cauxout(WORD c);
WORD Cprnout(WORD c);           /* non-zero if it went */
LONG Crawio(WORD c);            /* 0xFF reads without waiting: 0, no key */
LONG Crawcin(void);
LONG Cnecin(void);
void Cconws(const char FAR *s);
void Cconrs(char FAR *buf);     /* buf[0] the most, buf[1] the count, no NUL */
WORD Cconis(void);
WORD Cconos(void);
WORD Cprnos(void);
WORD Cauxis(void);
WORD Cauxos(void);
LONG Fdup(WORD handle);
LONG Fforce(WORD handle, WORD target);

/* The rest of memory, the clock, and the end.  There is one kind of
 * memory, so Mxalloc's mode is moot, and no user mode for Super to leave.
 * Pterm does not return: what it is given is what the program's loader
 * sees, as it would main()'s value. */
#define MX_STRAM     0
#define MX_TTRAM     1
#define MX_PREFSTRAM 2
#define MX_PREFTTRAM 3
#define SUP_INQUIRE  1L
LONG Mxalloc(LONG size, WORD mode);
LONG Mshrink(void FAR *block, LONG newsize);    /* smaller only */
/* Mode 0, load and go, only: the child's code, or an error.  The tail is
 * the ST's -- a length byte, then the bytes -- and the child reads it with
 * shel_read; the environment is not passed on. */
#define PE_LOADGO    0
LONG Pexec(WORD mode, const char FAR *name, const char FAR *tail,
           const char FAR *env);
LONG Super(void FAR *stack);
WORD Tsetdate(UWORD date);      /* 0; non-zero for a bad date or no clock */
WORD Tsettime(UWORD time);
void Pterm0(void);
void Pterm(WORD code);
void Ptermres(LONG keep, WORD code);

#endif /* GEM4XE_APP_GEM_H */
