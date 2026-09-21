/* appl.c -- the application manager's inquiries (EmuTOS aes/gemaplib.c's
 * half that answers questions rather than moves messages).
 *
 * One function so far, and it is the one that needed a file of its own:
 * appl_getinfo is fifteen subjects and would have been fifteen cases
 * inside src/sys/abi.c's dispatch, which is a shim and not a library.
 * appl_find's search lives in proc.c because it IS a walk of the process
 * table; this is a walk of the AES itself.
 *
 * THE RULE FOR EVERY ANSWER HERE: it is true of THIS machine, checked
 * against the code that would have to keep the promise, not copied from
 * what an ST answers.  Most of them are 0, and a truthful 0 is the whole
 * point of the call -- a program that asks whether this AES has popup
 * menus and is told "no" draws its own, while one that is told "yes"
 * calls menu_popup and gets -1 from an opcode nobody serves.
 */
#include "portab.h"
#include "aes.h"
#include "proc.h"
#include "sys/farmem.h"         /* appl_read's buffer may be far */
#include "../vdi/font.h"        /* FONT_ID_SYS: the face that is linked in */

/* THE PIPE IS MESSAGES, NOT BYTES, and that is the whole of appl_read.
 *
 * The donor's queue is a 128-byte buffer with a byte count (EmuTOS
 * aes/struct.h, p_queue/p_qindex), so its ap_rdwr blocks for any length
 * at all.  gem4xe's is p_qmax slots of eight words (proc.h), because the
 * window manager COALESCES: a second WM_REDRAW for a window already
 * waiting is unioned into the one in the queue rather than appended, and
 * a WM_ARROWED replaces its predecessor.  That is what keeps a dragged
 * window from queueing a redraw per frame, and it can only be done by
 * something that knows where a message starts.
 *
 * So the unit is sixteen bytes -- which is what every AES message is,
 * and what the Compendium recommends anyway ("It is recommended that
 * message lengths in multiples of 16 bytes be used", p.370).
 *
 * A LONGER READ IS REFUSED, and this is where a working multi-block
 * version was taken out again.  Blocks past the first are the CALLER'S
 * OWN BYTES and not messages, but they would sit in the same queue,
 * where mq_put cannot tell them apart: a continuation block whose first
 * word happened to be WM_REDRAW and whose fourth matched a live window
 * would be unioned into a real redraw by the next one the window manager
 * posted -- silently, and the reader would then wait forever for a block
 * that no longer exists.  The fix is a per-slot flag the queue does not
 * have.  Keeping the coalescing is worth more than a call the Compendium
 * itself says is "normally not used", so the length is one message and a
 * program that wants more sends more of them.
 */
WORD ap_read(WORD ap_id, WORD length, uint32_t buf)
{
    WORD msg[AP_MSGWORDS];

    /* YOUR OWN PIPE, and only yours.  The donor resolves ap_id to a
     * process and will read another's; here that would take a message
     * its owner is waiting for, and leave the caller blocked until some
     * third party wrote to a queue nobody told it about.  The AES 4.0
     * APR_NOWAIT (-1) is not special for the reason it is not special in
     * appl_find: it is gated on appl_getinfo, whose AES_INQUIRE subject
     * answers 0 here, so a caller that asked has already been told. */
    if (ap_id != proc_pid(rlr) || !buf || length != AP_MSGBYTES)
        return FALSE;
    ev_mesag(msg);
    far_put(buf, (const uint8_t *)msg, AP_MSGBYTES);
    return TRUE;
}

/* The Compendium's ap_gtype subjects (p.363-367).  The names are
 * gemlib's, which is what a ported program will have written. */
#define AI_LARGEFONT    0
#define AI_SMALLFONT    1
#define AI_SYSTEM       2
#define AI_LANGUAGE     3
#define AI_PROCESS      4
#define AI_PCGEM        5
#define AI_INQUIRE      6
#define AI_WDIALOG      7
#define AI_MOUSE        8
#define AI_MENU         9
#define AI_SHELL        10
#define AI_WINDOW       11
#define AI_MESSAGE      12
#define AI_OBJECT       13
#define AI_FORM         14
/* AND ONE OF GEM4XE'S OWN.  appl_getinfo exists so a program can ASK
 * rather than guess from a version number, and its subject numbers are
 * the extension point -- so a question this AES answers and no other
 * does belongs here rather than in an opcode nobody else would serve.
 * Atari's go up to 14; this starts where a private one cannot collide
 * with a future Atari subject by accident.  A program that asks an AES
 * which does not know it gets FALSE from the default below, which is
 * the correct answer and exactly what the call is for. */
#define AI_CPX          64

/* THE RESOLUTION NUMBER: gem4xe has none, and says so.
 *
 * AI_SYSTEM's first word is "the resolution number, as would be returned
 * by Getrez()".  Every value that call can answer names an Atari screen
 * -- 0, 1, 2 are the ST's, 4, 6, 7 the TT's -- and gem4xe is not any of
 * them.  Its VBXE surface is 512, 640 or 672 pixels across in sixteen
 * colours, whichever GEM4XE.CFG's SCREENW asked for, and its fallback is
 * 320x168 in two.  Those are the VBXE's own resolutions and the point of
 * offering them is not to pretend they are somebody else's.
 *
 * So -1, which is not a screen.  It was ST Low for one commit, chosen
 * because a program laying itself out for 320x200 fits on anything gem4xe
 * shows -- but that is a plausible wrong answer rather than a true one,
 * and a plausible wrong answer is what turns a missing feature into a
 * bug that looks like something else.  -1 is also the AES's own word for
 * "no such thing": it is what appl_find, wind_create and menu_register
 * answer when there is nothing to give back.
 *
 * What a caller actually needs is next door and is a fact: out2 is the
 * real number of colours.  The size is v_opnwk's work_out and the cell is
 * graf_handle, which is where a program that means it will look. */
#define AI_REZ_NONE     (-1)

WORD ap_getinfo(WORD which, WORD *out1, WORD *out2, WORD *out3, WORD *out4)
{
    WORD ret = TRUE;

    /* The donor's shape: TRUE unless the default clears it (MULTITOS
     * GEMAPLIB.C).  The Compendium's prose has this inverted -- "returns
     * 1 if an error occurred or 0 otherwise", p.368 -- and gemlib, the
     * ROM and every caller in cflib agree it is wrong. */
    *out1 = *out2 = *out3 = *out4 = 0;

    switch (which) {
    case AI_LARGEFONT:
    case AI_SMALLFONT:
        /* ONE FACE, so the large font and the small font are the same
         * one.  The AES has both names -- objc.c asks for SMALL on an
         * icon's label -- but gsx_tblt discards the argument, so they
         * render identically and saying otherwise would have a program
         * lay text out to a face that does not exist.
         *
         * The first word is the CELL HEIGHT IN PIXELS, not a point size.
         * The Compendium says "the AES font's point size"; the ROM
         * answers ws_chmaxh, the workstation's character height, and
         * cflib's appinit.c uses it as sys_big_height.  Three readings
         * against one, and the pixels are what a layout needs. */
        *out1 = gl_hchar;
        *out2 = FONT_ID_SYS;
        *out3 = SYSTEM_FONT;            /* a bitmap strip, not an outline */
        break;

    case AI_SYSTEM:
        *out1 = AI_REZ_NONE;            /* not an Atari screen: see above */
        *out2 = (WORD)(1 << gl_nplanes);  /* 16 on VBXE, 2 on ANTIC */
        *out3 = 0;                      /* colour icons: G_CICON draws its
                                         * MONO form (objc.c) */
        /* The extended resource format IS read: rs_load parses the
         * NEW_FORMAT_RSC extension, the colour-icon table and every
         * CICONBLK (rsrc.c).  Two limits the caller should know and
         * which the other words already say: the colour forms are placed
         * and not drawn, which is what out3's 0 means, and a resource
         * that has to load FAR is refused if it is new-format. */
        *out4 = 1;
        break;

    case AI_LANGUAGE:
        /* gem4xe HAS translations -- LANG.RSC -- and no language NUMBER:
         * the file carries strings and no identity, so the AES cannot
         * tell a German one from a Polish one.  So the answer is the
         * truth when it is known and a refusal when it is not, rather
         * than English either way: with the built-in strings in use the
         * language really is English, and with a file loaded this AES
         * does not know. */
        if (lang_loaded())
            return FALSE;
        *out1 = AESLANG_ENGLISH;
        break;

    case AI_PROCESS:
        /* Cooperative, and proud of it: proc.c is a round robin with no
         * pre-emption and no timer.  appl_find has no MiNT ids to
         * convert between, appl_search is not served (AES 4.0), and
         * neither is rsrc_rcfix. */
        break;

    case AI_PCGEM:
        /* out1 objc_xfind and out3 menu_click: neither is here.  out4 is
         * shel_rdef and shel_wdef, which are -- and this subject is the
         * ONLY place Atari's own documentation admits those two exist
         * (the Compendium, p.364).  out2 is reserved. */
        *out4 = 1;
        break;

    case AI_INQUIRE:
        /* The four "-1 means something extra" extensions, and this AES
         * has none of them.  appl_read is not served at all; shel_get
         * ignores a length that is not positive (and, worse for a
         * caller, still answers TRUE); menu_bar reads its mode as a
         * truth value, so -1 INSTALLS the bar rather than asking about
         * it, and MENU_INSTL is not distinct from it. */
        break;

    case AI_WDIALOG:
        /* Reserved in the Compendium; Mag!X's window-dialog family, of
         * which there is none here.  Answered rather than refused
         * because the ROM answers it -- all four words zero -- and
         * cflib's fontsel.c reads bit 2 of the first. */
        break;

    case AI_MOUSE:
        /* All three of graf_mouse's 258/259/260 are served (grlib.c).
         * The second word stays 0: it asks whether the AES keeps the
         * form PER APPLICATION, and gem4xe keeps ONE, globally -- an
         * accessory that changes the pointer changes the application's,
         * and nothing puts it back until the shell resets it to the
         * arrow between programs.  So the application owns what it wants
         * to see, which is what 0 tells it. */
        *out1 = 1;
        break;

    case AI_MENU:
        /* POPUPS, and nothing else of AES 4's menus.  The four words are
         * plain 0/1 and not a bit field -- read out of MULTITOS's
         * GEMAPLIB.C, where AI_MSG and AI_WIND set theirs to 0x03fe and
         * 0x01ff with a bit list and this one sets four ones.
         *
         * out1 is SUB-MENUS (menu_attach, menu_istart) and out2 is
         * popups: both are here.  out4 is MN_SELECTED's words 5 to 7
         * carrying the tree the item came from, and they are filled in
         * now (ctrl.c) -- with sub-menus the item may be in a tree that
         * is not the menu bar's, so the number alone would name nothing.
         *
         * out3 is SCROLLABLE menus, and they are not here: an item that
         * scrolls needs arrow items written into the caller's strings
         * and the box rebuilt by index as it moves, and nothing serves
         * menu_settings to change the speeds it would run at. */
        *out1 = 1;
        *out2 = 1;
        *out4 = 1;
        break;

    case AI_SHELL:
        /* The modes sh_write acts on are 0, 1, 4 and 5, so 5 is the
         * highest legal one, and there are no extended mode bits to
         * report in the high byte.  (cflib's sendchan.c wants 7 or more
         * before it will speak the AV protocol; it will not, correctly.)
         *
         * Mode 0 CANCELS a previous shel_write here -- it clears the
         * stored command and makes the desktop what runs next -- and
         * mode 1 takes effect when the current program exits rather than
         * launching at once, because the shell's loop starts it only
         * after app_exec returns.  No ARGV passing. */
        *out1 = 5;
        *out2 = 1;
        *out3 = 1;
        break;

    case AI_WINDOW:
        /* Every bit of this is 0, and each for a reason worth keeping:
         * WF_TOP answers one word and not the window below it too;
         * WF_NEWDESK is set-only, so wind_get refuses it; there are no
         * per-window colours (WF_COLOR/WF_DCOLOR) and no WF_BEVENT; and
         * the two gem4xe does serve are HALF each -- WF_OWNER is
         * wind_get only and bit 4 asks for get AND set, WF_BOTTOM is
         * wind_get only and bit 6 asks for the SET.  Claiming either
         * would send a program to a wind_set that answers FALSE.
         * No iconifier, no bottomer, no shift-click-to-bottom, no hot
         * close box. */
        break;

    case AI_MESSAGE:
        /* The AES sends WM_REDRAW, WM_TOPPED, WM_CLOSED, WM_FULLED,
         * WM_ARROWED, WM_HSLID, WM_VSLID, WM_SIZED, WM_MOVED,
         * MN_SELECTED, AC_OPEN and AC_CLOSE -- all of them AES 1's.
         * NONE of the extended ones: WM_NEWTOP, WM_UNTOPPED and WM_ONTOP
         * are declared and never sent (the control manager keeps the
         * mouse until the button is up, which is the ROM's rule), and
         * AP_TERM, CH_EXIT, WM_BOTTOM and the three iconify messages do
         * not exist here at all. */
        break;

    case AI_OBJECT:
        /* No 3D objects -- objc_sysvar says so too, and says it in the
         * same words -- but objc_sysvar itself IS here, which is what
         * cflib's obgframe.c reads this subject for.  1 is "MultiTOS
         * v1.01's", which is the one gem4xe answers.  The system font is
         * the only font an OBJECT can name: the AES never issues
         * vst_font, so a TEDINFO cannot select a GDOS face. */
        *out2 = 1;
        break;

    case AI_FORM:
        /* No flying dialogs: form_do takes the whole screen as the
         * control rectangle for the dialog's life, and there is no
         * mover, no title bar and no drag.  No keyboard tables.  But
         * objc_edit DOES hand the caller back the cursor position it
         * ended on -- ob_edit writes through the index and the shim
         * copies it out -- which is the third word. */
        *out3 = 1;
        break;

    case AI_CPX:
        /* THE CONTROL PANEL'S EXTENSIONS: how many are loaded, and where
         * the table of them is.  The address is FAR and so takes two of
         * the four words, high first -- the same order wind_set(WF_NAME)
         * takes one in, because a 24-bit address in a 16-bit word is
         * this project's oldest bug and one convention for all of them
         * is how it stays fixed.
         *
         * The panel reads the table itself rather than asking for a
         * module at a time: it is a --data-model=large program, the
         * table is a flat array of (CPXINFO address, CPXHEAD), and a
         * call per field would be a call per icon per redraw.
         *
         *   out1  modules loaded
         *   out2  the table's address, high word
         *   out3  ...and low
         *   out4  the size of one entry, so the panel can stride it
         *         without this file and src/app/cpx.h having to agree
         *         about padding
         */
        *out1 = sh_ncpx;
        *out2 = (WORD)(sh_cpxtable() >> 16);
        *out3 = (WORD)(sh_cpxtable() & 0xFFFF);
        *out4 = (WORD)sh_cpxstride();
        break;

    default:
        ret = FALSE;
        break;
    }
    return ret;
}
