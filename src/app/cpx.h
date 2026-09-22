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
#include <stddef.h>          /* offsetof, for the slot layout check below */

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
 *
 * XCONTROL's parameter block.  Its callbacks run INSIDE THE PANEL and
 * are reached from the module, which is the same cross-link call as a
 * CPXINFO entry in the other direction -- so they obey the same two
 * rules, for the same reasons (see CPXINFO below): each is `saveds` in
 * the panel, and each takes ONE uint32_t, the address of this block.
 *
 * WHICH IS WHY THERE ARE NO ARGUMENTS AND NO RETURN VALUES.  A callback
 * reads what it needs out of the block and writes its answer back into
 * it.  COPS passes every argument list as a struct by value instead,
 * which is a 68000 alignment workaround; this is a 65816 one, and it is
 * forced rather than chosen.
 *
 * Every field and every callback may be 0.  A module must cope: that is
 * what lets this grow without breaking a module built against an older
 * panel, and it is why cpx.h can promise a module anything at all.
 */
typedef struct {
    WORD  handle;               /* the panel's VDI workstation, or 0 */
    WORD  booting;              /* non-zero during boot-time init */
    WORD  country;              /* the system's country code */
    WORD  which;                /* WHICH module is calling.  The panel
                                 * fills this before it opens one, so a
                                 * callback needs nothing to identify
                                 * its caller. */

    /* THE MODULE'S OWN 64 BYTES, in the AES's table -- its header's
     * buffer[].  Read them at cpx_call and they are whatever was last
     * saved; write them and call CPX_Save to keep them. */
    uint32_t buffer;

    /* Write `buffer` to the module's settings file.  ok is 1 when it
     * went, 0 when it did not.
     *
     * THE ST WRITES THOSE BYTES BACK INTO THE .CPX ITSELF, which it can
     * because its header is in the file.  Here the header travels inside
     * the module, so the settings go to a file of their own beside it --
     * which also means a module is never written to while it is loaded,
     * and a module that will not save cannot corrupt itself trying. */
    void (*CPX_Save)(uint32_t xcpb);

    /* One of the canned alerts, so every module says the same thing in
     * the same words -- a person who has read "that file was not found"
     * once should not have to read a second module's version of it.
     * Set `alert` to an XAL_ below, call, then read `ok`.
     *
     * THE TEXT IS THE PANEL'S, in CPANEL.RSC, which is also the only
     * place a translator could reach it: a sentence compiled into a
     * module could not be translated at all. */
    void (*XGen_Alert)(uint32_t xcpb);
    WORD  alert;
    WORD  ok;                   /* what the last callback answered */
} XCPB;

/* XGen_Alert's numbers are Atari's, from the Compendium's table for
 * (*xcpb->XGen_Alert)().  That table has these four and no others.
 *
 * ONLY ALERT 0 ASKS A QUESTION.  The Compendium: "returns TRUE if 'OK'
 * was selected or FALSE if 'Cancel' was selected.  Alerts 1-3 always
 * returns TRUE" -- so a module that tests `ok` after one of the other
 * three gets the 1 an ST would have given it.
 *
 * AN ID THAT IS NOT ONE OF THESE DRAWS NOTHING and answers 0.  There is
 * no sentence to put on the screen for a number nobody has defined, and
 * answering 1 would be reporting a decision the person never made.
 *
 * A NOTE ON WHAT IS NOT HERE: an earlier draft of this header carried
 * XAL_SHUTDOWN as 11 and said the numbers were Atari's.  They are, for
 * these four; 11 is in neither the Compendium's table nor the GEM source
 * corpus, and nothing in this tree ever used it.  A constant that claims
 * an authority it does not have gets believed later, so it is gone
 * rather than guessed at. */
#define XAL_SAVE_DEFAULTS   0
#define XAL_MEM_ERR         1
#define XAL_FILE_ERR        2
#define XAL_FILE_NOT_FOUND  3
#define XAL_NALERT          4

/* ---- what the module hands back --------------------------------------
 *
 * EVERY ENTRY TAKES ONE uint32_t, the far address of the CPXPB below,
 * and that is forced by the compiler rather than chosen.
 *
 * A vtable entry must be `saveds` (see the head of this file), and
 * Calypsi's saveds switches to the callee's direct page BEFORE the body
 * reads its arguments -- which the CALLER left in ITS direct page.  Only
 * A and X survive the prologue, so:
 *
 *     ONE 16-bit argument      safe   (kept in A across the switch)
 *     ONE 32-bit integer       safe   (in X:C, untouched)
 *     ONE POINTER              LOST   (read from [_Dp] after the switch)
 *     TWO arguments or more    LOST from the second on
 *
 * and nothing warns.  The first draft of this header took a `const GRECT
 * *` and three-argument event entries; the module drew its box in the
 * wrong corner of the screen and then printed the rectangle it had been
 * handed -- x=01E1 y=0000 w=3006 h=0000 against 00A0 0016 0140 00CD.
 *
 * So: one address, a block behind it.  Which is GEM's own call ABI
 * anyway (contrl/intin/ptsin/intout/ptsout), so a CPX author writing
 * against this is writing in the idiom the rest of the system uses.
 */

/* The block.  The host fills what the call needs, the module reads it
 * and writes back `quit` and `ret`.  It is the HOST's memory and lives
 * only for the call. */
typedef struct {
    /* THE PANEL'S OWN BLOCK, handed over at cpx_call.  It is here rather
     * than at cpx_init because the AES loads a module at boot and the
     * panel is not in that conversation -- it learns about its modules
     * afterwards, through appl_getinfo(AES_CPX).  A module that wants it
     * keeps it from its first cpx_call. */
    uint32_t xcpb;

    GRECT rect;                 /* cpx_call, cpx_draw, cpx_wmove */
    MRETS mouse;                /* cpx_button, cpx_m1, cpx_m2 */
    WORD  kstate, key;          /* cpx_key */
    WORD  nclicks;              /* cpx_button */
    WORD  event;                /* cpx_hook: which evnt_multi bit */
    WORD  msg[8];               /* cpx_hook: the message, when there is one */
    WORD  quit;                 /* SET THIS to be closed.  The host zeroes
                                 * it before every call and stops asking
                                 * the moment it comes back non-zero. */
    WORD  ret;                  /* cpx_call's answer: see below */
} CPXPB;

typedef struct {
    /* OPEN.  Draw into pb->rect, and say which KIND of module this is by
     * what you put in pb->ret -- XCONTROL's convention, and the only
     * thing that tells the two apart:
     *
     *   0  FINISHED.  A form CPX that ran its own dialog and closed it,
     *      or a CPX_SETONLY module that acted and had nothing to show.
     *      The host takes the screen back and asks nothing further.
     *
     *   1  DRIVE ME.  An event CPX: it has drawn itself into pb->rect
     *      and now wants events, one at a time, through the entries
     *      below.  The host runs its loop and calls cpx_key, cpx_button,
     *      cpx_timer and cpx_draw until one of them sets pb->quit, then
     *      cpx_close.
     *
     * A form CPX is the simpler thing and needs nothing of the host; an
     * event CPX is what a module with live feedback wants -- a slider
     * that shows the effect of dragging it, a sound that plays while the
     * dialog is up -- because it never blocks the host's loop. */
    void (*cpx_call)(uint32_t pb);

    /* THE REST ARE FOR AN EVENT CPX ONLY.  Any of them may be 0 and a
     * host must check: a module that wants only keys writes only
     * cpx_key.  Each is given pb->quit zeroed. */
    void (*cpx_draw)(uint32_t pb);
    void (*cpx_wmove)(uint32_t pb);
    void (*cpx_timer)(uint32_t pb);
    void (*cpx_key)(uint32_t pb);
    void (*cpx_button)(uint32_t pb);
    void (*cpx_m1)(uint32_t pb);
    void (*cpx_m2)(uint32_t pb);
    void (*cpx_hook)(uint32_t pb);
    void (*cpx_close)(uint32_t pb);
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
 * entry in CPXINFO needs SAVEDS on it too, for the same reason.
 *
 * cpx_init is the ONE EXCEPTION to the one-argument rule above, and it
 * gets away with two because it is not called through the vtable: the
 * kit's glue calls it (src/app/cpxmain.c), compiled INTO the module and
 * so sharing its direct page.  Everything the PANEL calls obeys the
 * rule.
 *
 * AND A MODULE MUST BE BUILT --data-model=large, the panel's model.  A
 * vtable is a shared ABI, so both sides have to agree how wide a
 * uint32_t argument is passed; built small, the first test module read
 * its parameter block from the wrong place.
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
/* Where the header starts in a slot.  THE AES LAYS THIS OUT BY HAND
 * (src/aes/shel.c, CPXE_HDR) because it cannot include this file, so the
 * number below and that one have to be the same -- and the compiler is
 * made to check it, two lines down, rather than a gate finding out
 * later.
 *
 * IT IS 20 AND NOT 18, which is the whole reason the check exists: the
 * file name is fourteen useful bytes and this compiler pads it to
 * sixteen (B7, tools/ccbug -- a struct's size is not the sum of its
 * fields).  Written as 14 it built cleanly on both sides, the AES wrote
 * a module's header two bytes below where the panel read it, and the
 * panel saw every module's flags as whatever was in the gap.  So the
 * field is sixteen and says so. */
#define CPX_SLOT_HDR  20

typedef struct {
    uint32_t info;              /* the module's CPXINFO, 0 if none */
    char     file[16];          /* its file name, which is what its
                                 * settings file is named after -- the
                                 * module never knows it and never has to.
                                 * SIXTEEN, not fourteen: see above. */
    CPXHEAD  hdr;               /* what it filled in at load time */
} CPXSLOT;

/* The check.  A negative array bound is a compile error, so a slot whose
 * header moves stops the build here instead of drawing the wrong word. */
typedef char cpx_slot_layout_holds[
    (offsetof(CPXSLOT, hdr) == CPX_SLOT_HDR) ? 1 : -1];

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
