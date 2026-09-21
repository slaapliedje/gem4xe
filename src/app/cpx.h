/* cpx.h -- the control panel extension contract.
 *
 * A CPX is a module the control panel hosts: it brings its own dialog and
 * its own settings, and CONTROL.ACC finds it, shows its icon, opens it and
 * hands it events.  The point of the shape is that the Desk menu has six
 * slots and this machine has one of them -- a panel that hosts modules is
 * unbounded where a panel that IS its settings is not.
 *
 * It is the ST's shape on purpose.  The 512-byte header below is Atari's,
 * field for field, and the ten entry points are XCONTROL's, so somebody
 * who has written a CPX recognises this and a CPX's SOURCE is most of the
 * way here.  The contract is read out of COPS (freemint/cops, GPL-2, by
 * Sven & Wilfried Behne and later F. Naumann & O. Skancke), which is a
 * licence gem4xe can take -- unlike Atari's own XCONTROL sources, which
 * are All Rights Reserved and are specification only.
 *
 * WHAT IS NOT THE ST'S, AND WHY.
 *
 * A .CPX ON AN ST IS A 68000 GEMDOS EXECUTABLE.  Nothing can change that,
 * so a gem4xe CPX is a .G4A (tools/mkg4a.py) carrying this header INSIDE
 * it -- see the file section below for why it is not in front.  The
 * header travels; the machine code cannot.  A port is a recompile plus
 * whatever the two AESes differ by, not a translation.
 *
 * THE CALLBACKS TAKE ORDINARY ARGUMENTS.  COPS passes every multi-argument
 * callback as a STRUCT BY VALUE -- `struct Sl_xy_args`, `struct
 * Popup_args` -- which is a 68000 alignment workaround and buys nothing
 * here.  They are argument lists again.  This is the one change a ported
 * CPX's source has to make and it is mechanical.
 *
 * EVERY ENTRY POINT IS `saveds`.  A CPX is linked separately from the
 * panel that calls it, so when the panel calls through CPXINFO the live
 * direct page and data bank are the PANEL's.  `saveds` makes a function
 * establish its own on entry and give the caller's back on exit
 * (src/portab.h) -- without it a CPX reads its own globals at the panel's
 * addresses, silently, which is this project's oldest failure shape.  The
 * loader relocates both constants, so a module works wherever it lands.
 *
 * THERE IS NO PER-CPX STACK AND NO setjmp.  COPS gives each module a
 * malloc'd stack and a jmp_buf so an interrupted Xform_do can be resumed.
 * On the 65816 the hardware stack is confined to bank zero, which is the
 * scarcest thing on this machine, and one CPX is open at a time -- so a
 * CPX runs on the panel's stack and Xform_do returns rather than jumping.
 */
#ifndef GEM4XE_CPX_H
#define GEM4XE_CPX_H

#include "gem.h"

/* ---- the file ---------------------------------------------------------
 * A gem4xe CPX is a .G4A named *.CPX.  Nothing is in front of it: the
 * header below is a variable INSIDE the module, which the module copies
 * into the panel's when its entry is called.
 *
 * THE ST PUTS THE HEADER IN THE FILE so XCONTROL can list every module
 * without loading any -- it reads 512 bytes and closes the file again.
 * That buys nothing here, because every module IS loaded, at boot,
 * before the keep mark (src/aes/shel.c, sh_cpx).  And it has to be:
 * both of gem4xe's allocators are bump allocators, so memory taken
 * while the desktop is up sits ABOVE the desktop's own mark and
 * app_free reclaims it the moment the desktop exits to run a program.
 * A module loaded on demand would be freed out from under the panel by
 * the next thing the user launched, silently.
 *
 * So: loaded when the accessories are, kept as long as they are, and a
 * header that travels in the module rather than in front of it -- which
 * also means the loader needs no special case and a CPX is a .G4A the
 * ordinary tools already build.
 */
#define CPX_MAGIC    0x6811         /* 'CPX' for this machine: not $601A,
                                     * which is a 68000 `bra.s` and would
                                     * be a lie about what follows */
#define CPX_HDR_SIZE 512

/* cpxhead flags */
#define CPX_SETONLY   0x0001        /* no dialog: it acts and returns */
#define CPX_BOOTINIT  0x0002        /* wants its init run at start-up */
#define CPX_RESIDENT  0x0004        /* stay loaded once opened */

/* THE HEADER IS 512 BYTES AND EVERY OFFSET IS ATARI'S.  Do not measure it
 * with sizeof in a constant expression -- this compiler answers two
 * different numbers for a struct with a trailing array (B7,
 * tools/ccbug) -- and do not reorder it.  tests/host/test_cpx.py asserts
 * the offsets against this comment rather than against the struct, so
 * that the struct cannot quietly drift away from the format.
 *
 *    0  u16  magic
 *    2  u16  flags
 *    4  u32  cpx_id          who wrote it; Atari assigned these
 *    8  u16  cpx_version
 *   10  char i_text[14]      under the icon
 *   24  u16  icon[48]        32x24 mono, the panel's grid
 *  120  u16  i_info          colour and character (see below)
 *  122  char title_txt[18]   the dialog's title
 *  140  u16  t_info          the title's colours
 *  142  char buffer[64]      THE MODULE'S OWN SETTINGS.  The ST writes
 *                            these back into the .CPX itself, which it
 *                            can because its header is in the file;
 *                            CPX_Save here puts them in a file beside
 *                            the module, so a module is never written
 *                            to while it is loaded
 *  206  char reserved[306]
 *  512
 */
typedef struct {
    UWORD  magic;
    UWORD  flags;
    LONG   cpx_id;
    UWORD  cpx_version;
    char   i_text[14];
    UWORD  icon[48];
    /* BIT-FIELDS ARE DECLARED BACKWARDS HERE, as ob_spec's are in gem.h
     * and for the same reason: this compiler allocates them low-end-first
     * within a 16-bit unit and the 68000 allocates high-end-first, so the
     * ST's `i_color:4; reserved:4; i_char:8` is this order to land on the
     * same bits of the same word. */
    UWORD  i_info;              /* i_char<<8 | reserved<<4 | i_color */
    char   title_txt[18];
    UWORD  t_info;              /* c_back<<12 | pattern<<8 | c_text<<4 | c_board */
    char   buffer[64];
    char   reserved[306];
} CPXHEAD;

/* i_info / t_info, since they are words here rather than bit-fields. */
#define CPX_ICOLOR(i)   ((i) & 0x000F)
#define CPX_ICHAR(i)    (((i) >> 8) & 0x00FF)
#define CPX_TBOARD(t)   ((t) & 0x000F)
#define CPX_TTEXT(t)    (((t) >> 4) & 0x000F)
#define CPX_TPATTERN(t) (((t) >> 8) & 0x000F)
#define CPX_TBACK(t)    (((t) >> 12) & 0x000F)

/* The mouse as a module is handed it (XCONTROL's MRETS). */
typedef struct {
    WORD x, y, buttons, kstate;
} MRETS;

/* ---- what the panel hands the module ---------------------------------
 * XCONTROL's parameter block, with the argument lists flattened.  Every
 * pointer here is the PANEL's, live for as long as the module is open.
 */
typedef struct {
    WORD  handle;               /* the panel's VDI workstation */
    WORD  booting;              /* non-zero during boot-time init */
    WORD  country;              /* the system's country code */

    /* the module's own 64 bytes out of its header, to read and change */
    void FAR * (*Get_Buffer)(void);
    /* ...and written back into the file.  0 on failure. */
    WORD  (*CPX_Save)(const void FAR *p, LONG bytes);

    /* a resource the module brought with it */
    void  (*rsh_fix)(WORD nobs, WORD nte, WORD nib, WORD nbb,
                     OBJECT FAR *ob, TEDINFO FAR *te, ICONBLK FAR *ib,
                     BITBLK FAR *bb, LONG FAR *frstr, LONG FAR *frimg,
                     LONG FAR *trindex);
    void  (*rsh_obfix)(OBJECT FAR *tree, WORD obj);

    /* the panel's window, for a module that draws its own */
    WORD  (*GetFirstRect)(GRECT *r);
    WORD  (*GetNextRect)(GRECT *r);

    /* a form that returns instead of blocking: the panel keeps the event
     * loop, so a module never calls form_do */
    WORD  (*Xform_do)(OBJECT FAR *tree, WORD edit_obj, WORD FAR *msg);

    /* what the module wants added to the panel's evnt_multi */
    void  (*Set_Evnt_Mask)(WORD mask, const MOBLK *m1, const MOBLK *m2,
                           LONG evtime);

    /* the canned alerts, so every panel says the same thing */
    WORD  (*XGen_Alert)(WORD which);
} XCPB;

/* XGen_Alert's numbers are Atari's. */
#define XAL_SAVE_DEFAULTS   0
#define XAL_MEM_ERR         1
#define XAL_FILE_ERR        2
#define XAL_FILE_NOT_FOUND  3
#define XAL_SHUTDOWN       11

/* ---- what the module hands back --------------------------------------
 * The module's entry point is called ONCE, with the block above, and
 * returns this.  Everything in it may be 0 except cpx_call.
 *
 * EVERY ONE OF THESE MUST BE `saveds` in the module that defines them --
 * see the head of this file.  CPX_ENTRY spells that for the entry point;
 * a module writes SAVEDS on the rest itself.
 */
typedef struct {
    /* open: draw into `r`, or return 0 to decline.  A CPX_SETONLY module
     * does its work here and returns 0. */
    WORD (*cpx_call)(const GRECT *r);
    void (*cpx_draw)(const GRECT *clip);
    void (*cpx_wmove)(const GRECT *work);
    void (*cpx_timer)(WORD *quit);
    void (*cpx_key)(WORD kstate, WORD key, WORD *quit);
    void (*cpx_button)(const MRETS *m, WORD nclicks, WORD *quit);
    void (*cpx_m1)(const MRETS *m, WORD *quit);
    void (*cpx_m2)(const MRETS *m, WORD *quit);
    WORD (*cpx_hook)(WORD event, WORD *msg, const MRETS *m,
                     WORD *key, WORD *nclicks);
    void (*cpx_close)(WORD flag);
} CPXINFO;

/* THE ENTRY POINT.  A module defines exactly one, named cpx_init, and
 * the panel calls it ONCE after loading:
 *
 *     CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr);
 *
 * It fills *hdr with its own header -- its title, its icon, its flags,
 * and the 64 bytes it keeps settings in -- and returns its vtable, or 0
 * to decline (a module that finds no hardware it can configure should
 * decline rather than appear and do nothing).
 *
 * IT MUST BE saveds, which is the whole reason CPX_ENTRY is a macro and
 * not a comment.  A module is linked separately from the panel, so the
 * direct page and data bank live on entry are the PANEL's; without
 * saveds a module reads its own globals at the panel's addresses,
 * silently, which is this project's oldest failure shape.  Every other
 * entry in CPXINFO needs SAVEDS on it too, for the same reason -- the
 * panel calls those directly.
 *
 * WHERE SETTINGS GO.  The ST writes the 64 bytes back into the .CPX file
 * itself, which it can because the header is in the file.  Here they go
 * to a file of their own beside the module, so that a module is never
 * written to while it is loaded -- see CPX_Save. */
#define CPX_ENTRY  SAVEDS

/* ---- what the PANEL uses ----------------------------------------------
 * A control panel asks the AES what is loaded and reads the table.  It
 * is a flat array of slots, each a 32-bit CPXINFO address followed by
 * that module's CPXHEAD, and the AES reports the stride so this header
 * and the AES need not agree about padding.
 *
 * Both of these are inline rather than library code because a panel is
 * the only caller and they are four lines; and they exist at all so
 * that nobody assembles a 24-bit address out of two words by hand,
 * which is where this project's oldest bug lives.
 */
typedef struct {
    uint32_t info;              /* the module's CPXINFO, 0 if none */
    CPXHEAD  hdr;               /* what it filled in at load time */
} CPXSLOT;

/* How many modules the AES has loaded, and where they are.  Returns the
 * count; *table is the far address of slot 0 and *stride one slot's
 * size.  0 on an AES that has no extensions, or knows no such subject. */
static __inline WORD cpx_count(uint32_t *table, WORD *stride)
{
    WORD n = 0, hi = 0, lo = 0, st = 0;

    if (!appl_getinfo(AES_CPX, &n, &hi, &lo, &st))
        return 0;
    *table  = ((uint32_t)(UWORD)hi << 16) | (UWORD)lo;
    *stride = st;
    return n;
}

/* Slot i, as a far pointer the panel can read the header out of. */
static __inline CPXSLOT FAR *cpx_slot(uint32_t table, WORD stride, WORD i)
{
    return (CPXSLOT FAR *)(table + (uint32_t)i * (UWORD)stride);
}

#endif /* GEM4XE_CPX_H */
