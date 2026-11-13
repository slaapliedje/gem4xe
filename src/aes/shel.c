/* shel.c -- the shell library: shel_read, shel_write, shel_get, shel_put,
 * shel_find, shel_envrn, and the shell loop that runs the desktop and
 * the programs it asks for.  EmuTOS aes/gemshlib.c.
 *
 * What the donor's shell library keeps -- the command and tail the next
 * application starts with, the environment, and the 4 KB the desktop
 * parks its state in between programs -- is nothing the AES reads itself;
 * it is memory it lends the applications, across their lifetimes.  So it
 * lives in far memory, taken from the far allocator ONCE, at AES start-up
 * and as the system's (owner 0), which no program's exit frees.  (Both
 * allocators were bump allocators then, wound back by app_free, which is
 * why this is done before any application is loaded.)  The environment is the one
 * exception, a constant in bank $00, because shel_envrn hands out a
 * pointer INTO it and an application's pointers are 16 bits.
 *
 * shel_write records a request, as the donor's does: which program to
 * run next and how.  Acting on it is sh_main's, the shell loop: the
 * desktop, then whatever it asked for, then the desktop again, until
 * something asks to shut down (SHW_SHUTDOWN).  The request sits in
 * sh_doexec for whoever asks (src/m3_vdi.c reads it back in the gate).
 *
 * NAMES.  A GEM application names a file the TOS way, X:\DIR\NAME.EXT,
 * and the Atari OS the CIO way: Dn:NAME.EXT on DOS 2, Dn:>DIR>NAME.EXT
 * on a SpartaDOS.  sh_cioname maps the first onto whichever the machine
 * booted -- the rule is the DOS seam's, src/sys/dos.h -- and leaves
 * anything else alone for CIO to judge, which is where a name with no
 * device at all gets its D: (src/sys/cio.c).  Every file the AES opens
 * on an application's behalf goes through it.
 */
#include "portab.h"
#include <string.h>
#include "aes/aes.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/sdcio.h"                  /* sdc_folder: beside the modules */
#include "sys/runnote.h"                /* a plain program: GEM's note */
#include "sys/gemdos.h"
#include "sys/farmem.h"
#include "sys/ctx.h"
#include "sys/abi.h"                    /* app_run: a CPX is run, not exec'd */
#include "aes/proc.h"
#include "sys/pool.h"
#include "../vdi/vdi.h"
#include "sys/zwin.h"
#include "lang_rsc.h"

#define SH_CMDLEN   128         /* MAXPATHLEN: the command, NUL-terminated */
#define SH_TAILLEN  128         /* CMDTAILSIZE: architectural              */
#define SH_BUFLEN   4192        /* SIZE_SHELBUF: TOS 1.04's, as EmuTOS      */

/* The environment, the TOS way: NAME=<NUL>value<NUL> ... <NUL>.  TOS puts
 * the NUL right after PATH= and the search list after it, and every
 * application that reads PATH= skips that NUL (the donor's sh_path does);
 * so does the one path gem4xe offers, the default drive. */
static const char sh_env[] = "PATH=\0D:\0";

WORD sh_doexec;                 /* the pending request: SHW_*, or -1  */
WORD sh_isgem;
static WORD sh_next;            /* what runs next: SH_DESKTOP, SH_PROGRAM */
static uint32_t sh_cmd_far, sh_tail_far, sh_buf_far;   /* 0 until sh_init */

/* ---- shel_rdef and shel_wdef -----------------------------------------
 *
 * WHAT RUNS AS THE DESKTOP, and the directory it runs in.  Neither call
 * is an Atari one: the Falcon ROM's CRYSBIND.H puts SHEL_SPATH at 126
 * and GEMBIND.C never dispatches it, 127 is not there at all, and the
 * Compendium's own binding table leaves both blank.  They are PC-GEM's,
 * and the only place Atari's documentation admits they exist is
 * appl_getinfo's AES_PCGEM subject, whose fourth word says whether they
 * are implemented -- which is now 1 (src/aes/appl.c).
 *
 * THE BUFFER SIZES ARE THE DONOR'S, not this file's convenience: EmuTOS
 * declares sh_desk as LEN_ZFNAME (13) and sh_cdir as LEN_ZPATH (114),
 * and a program written against those would be overrun by anything
 * longer.  shel_rdef writes no more than that and shel_wdef keeps no
 * more, which costs a long desktop path and buys a caller that cannot
 * be made to scribble.
 *
 * BOTH HALVES DO SOMETHING HERE, which was not a given.  The directory
 * is where the desktop is run from, in place of the system's -- the
 * donor's sh_chdef does exactly this for DESKTOP_APP.  The name is the
 * program the shell loads as the desktop: gem4xe keeps the default one
 * cached in far memory because it runs again after every program (a
 * copy, not a disk read), so a name that is still DESKTOP.PRG comes out
 * of the cache and any other is loaded from the file like a program.
 * That costs a disk read per return to the desktop for a caller that
 * changed it, which is the right way round. */
#define SH_DESKNAME "DESKTOP.PRG"   /* what the shell runs unless told */
#define SH_DESKLEN  13          /* LEN_ZFNAME: NAME.EXT and its NUL */
#define SH_CDIRLEN  114         /* LEN_ZPATH: a path with its drive */
static uint32_t sh_desk_far, sh_cdir_far;

/* THE RING (phase 129, switcher step 3): everything loaded and not
 * running, in the order the switch key goes round them -- a program put
 * aside by its record (sh_suspend), and the desktop, while it is not the
 * one running, by SH_DESKREC.  The one running is the gap between the
 * last entry and the first.  The switch key goes to the first entry, and
 * with SHIFT to the last, and whatever stops goes into the gap: so the
 * circle keeps its order however it is gone round -- the order the
 * programs were started in, then the desktop, as MultiTOS's list of
 * processes does for its Control-Alternate-Tab.  A program the desktop
 * starts comes in just before the desktop, so one CONTROL-TAB from it
 * goes back where it was started from.
 *
 * A count word and SH_PROGS entries, in far memory after the desktop's
 * directory (sh_init) rather than a block of their own, so that no
 * gate's model of the heap has one more block to place.  SH_PROGS is how
 * many programs may be loaded at once besides the desktop: all of them
 * aside while the desktop runs, or one running and the rest aside beside
 * the desktop's entry. */
#define SH_RINGBYTES (2 + 4 * SH_PROGS)     /* SH_PROGS: aes.h */
#define SH_DESKREC   1UL
#define sh_ring      (sh_cdir_far + SH_CDIRLEN)

#define SH_DESKTOP  0
#define SH_PROGRAM  1

void sh_init(void)
{
    if (sh_cmd_far)             /* the AES starts up once per script */
        return;
    sh_cmd_far  = far_alloc(SH_CMDLEN);
    sh_tail_far = far_alloc(SH_TAILLEN);
    sh_buf_far  = far_alloc(SH_BUFLEN);
    sh_desk_far = far_alloc(SH_DESKLEN);
    sh_cdir_far = far_alloc(SH_CDIRLEN + SH_RINGBYTES);
    if (sh_desk_far)
        far_strput(sh_desk_far, SH_DESKNAME, SH_DESKLEN);
    if (sh_cdir_far) {
        far_write8(sh_cdir_far, 0);     /* empty: the system's directory */
        far_fill(sh_ring, 0, 2);        /* nothing loaded */
    }
    if (sh_cmd_far && sh_tail_far && sh_buf_far) {
        far_write8(sh_cmd_far, 0);
        far_write8(sh_tail_far, 0);
        far_fill(sh_buf_far, 0, SH_BUFLEN);   /* the donor's is zeroed BSS:
                                               * the desktop tests its first
                                               * byte for '#' */
    }
    sh_doexec = -1;
    sh_isgem = 0;
}

/* shel_rdef: what the shell will run as the desktop, and where. */
void sh_rdef(char *lpcmd, char *lpdir)
{
    if (!sh_desk_far)
        return;
    far_strget(lpcmd, sh_desk_far, SH_DESKLEN);
    far_strget(lpdir, sh_cdir_far, SH_CDIRLEN);
}

/* shel_wdef: and what it will be from now on.  An empty directory means
 * the system's, which is where the desktop's own files are and what the
 * shell did before this call existed. */
void sh_wdef(const char *lpcmd, const char *lpdir)
{
    if (!sh_desk_far)
        return;
    far_strput(sh_desk_far, lpcmd, SH_DESKLEN);
    far_strput(sh_cdir_far, lpdir, SH_CDIRLEN);
}

void sh_read(char *pcmd, char *ptail)
{
    if (!sh_cmd_far)
        return;
    far_strget(pcmd, sh_cmd_far, SH_CMDLEN);
    far_get((uint8_t *)ptail, sh_tail_far, SH_TAILLEN);
}

/* aes.h says SH_SAVELEN; this is the check that it holds both. */
typedef char sh_savelen_holds_both[(SH_SAVELEN == SH_CMDLEN + SH_TAILLEN) ? 1 : -1];

void sh_push(uint32_t save, const char *cmd, uint32_t tail)
{
    if (!sh_cmd_far)
        return;
    far_copy(save, sh_cmd_far, SH_CMDLEN);
    far_copy(save + SH_CMDLEN, sh_tail_far, SH_TAILLEN);
    far_strput(sh_cmd_far, cmd, SH_CMDLEN);
    if (tail)
        far_copy(sh_tail_far, tail, SH_TAILLEN);
    else
        far_write8(sh_tail_far, 0);
}

void sh_pop(uint32_t save)
{
    if (!sh_cmd_far)
        return;
    far_copy(sh_cmd_far, save, SH_CMDLEN);
    far_copy(sh_tail_far, save + SH_CMDLEN, SH_TAILLEN);
}

/* ---- AES 4's shutdown (phase 123) -------------------------------------
 *
 * MultiTOS's protocol, from its sh_shutdown and shel_write (GEMSHLIB.C,
 * read as specification), on gem4xe's processes: process 0, the one
 * application -- the desktop or a program -- and the accessories.
 *
 * A shutdown is ASKED, never forced.  Every other application must have
 * said, with shel_write(SWM_NEWMSG, NM_APTERM), that it understands
 * AP_TERM -- in a complete shutdown every accessory too -- or nothing is
 * sent and the caller is answered 0: a program that never registered may
 * be holding work it would lose.  Then the accessories are sent AC_CLOSE
 * (and AP_TERM, in a complete one), the application AP_TERM with the
 * reason in msg[5], and the caller is the one shutting down until it
 * aborts or ends.  It is told by SHUT_COMPLETED: msg[3] 1 once the
 * application it waited for has gone -- at once if there was none -- or
 * 0 if one answered AP_TFAIL, with msg[4] who and msg[5] its code.
 *
 * WHERE THE MODE IS READ.  The Compendium puts SD_ABORT / SD_PARTIAL /
 * SD_COMPLETE in wiscr; MultiTOS's own AES reads them from isgem
 * (`case 4: return sh_shutdown(isgem, AP_TERM)`), and that is what the
 * programs written for it were tested against.  isgem it is. */
/* In the window, not LoRAM: only shel_write and the shell loop touch it,
 * from gem4xe's own calls and never an interrupt (src/sys/zwin.h), and
 * LoRAM had no two bytes to spare (test_memory's budget). */
ZWIN static PROC *sh_shutpd;    /* who is shutting down, or 0 */
ZWIN uint16_t sh_shutdone;      /* SHUT_COMPLETED sent, for the gate */
/* Phase 131: the program about to be resumed is to find AP_TERM waiting
 * (sh_term, sh_close); and the desktop's Quit is asking every program
 * aside to end, one at a time (sh_closing, sh_quitround). */
ZWIN static uint8_t sh_term;
ZWIN uint8_t sh_closing;
/* Phase 132: the desktop could not be loaded with programs aside, and one
 * of them was resumed in its place -- once; a second failure ends GEM. */
ZWIN static uint8_t sh_nodesk;

static WORD sh_shutdown(WORD how)
{
    PROC *me = rlr;
    WORD i, wait = 0;

    switch (how) {
    case SD_ABORT:
        if (!sh_shutpd || sh_shutpd != me)
            return 0;           /* not shutting down, or not its own */
        sh_shutpd = 0;
        return 1;
    case SD_PARTIAL:
    case SD_COMPLETE:
        if (sh_shutpd)
            return sh_shutpd == me;
        break;
    default:
        return 0;
    }
    for (i = 0; i < proc_n; i++) {
        PROC *p = &proc_tab[i];
        if (p == me || p->p_stat == P_FREE || p->p_stat == P_DONE)
            continue;
        if ((p == proc_app || how == SD_COMPLETE)
            && !(p->p_msgs & NM_APTERM))
            return 0;           /* one would lose its work: refused */
    }
    for (i = 0; i < MAX_ACCS; i++) {
        PROC *p = mn_owner(i);
        if (p && p != me)
            ap_sendmsg(p, AC_CLOSE, i, 0, AP_TERM, 0, 0);
    }
    for (i = 1; i < proc_n; i++) {
        PROC *p = &proc_tab[i];
        if (p != me && how == SD_COMPLETE)
            ap_sendmsg(p, AP_TERM, i, 0, AP_TERM, 0, 0);
    }
    if (proc_app != me) {
        ap_sendmsg(proc_app, AP_TERM, 0, 0, AP_TERM, 0, 0);
        wait = 1;
    }
    sh_shutpd = me;
    if (!wait) {
        ap_sendmsg(me, SHUT_COMPLETED, 1, 0, 0, 0, 0);
        sh_shutdone++;
    }
    return 1;
}

/* Whether process 0 is the desktop, for appl_search's APP_SHELL (phase
 * 124): set by sh_ldapp around the run, as the loop knows which it is
 * starting. */
ZWIN static WORD sh_deskrun;

WORD sh_desk_running(void)
{
    return sh_deskrun;
}

/* The application has ended: whoever was waiting on it is told -- or,
 * if it was the one shutting down, the shutdown ends with it. */
static void sh_appgone(void)
{
    PROC *p = sh_shutpd;

    if (!p)
        return;
    sh_shutpd = 0;
    if (p == proc_app)
        return;
    ap_sendmsg(p, SHUT_COMPLETED, 1, 0, 0, 0, 0);
    sh_shutdone++;
}

/* shel_write(SWM_AESMSG): eight words for the AES.  AP_TFAIL is the one
 * it understands -- the application asked to end cannot -- and ends the
 * shutdown, telling the one that asked who refused and why. */
WORD sh_aesmsg(const WORD *msg)
{
    PROC *p = sh_shutpd;

    if (msg[0] == AP_TFAIL && sh_closing && rlr == proc_app) {
        sh_closing = 0;                 /* the desktop's Quit stops here: it
                                         * stays in front (phase 131) */
        if (!p)
            return 1;
    }
    if (msg[0] != AP_TFAIL || !p)
        return 0;
    sh_shutpd = 0;
    ap_sendmsg(p, SHUT_COMPLETED, 0, proc_pid(rlr), msg[1], 0, 0);
    sh_shutdone++;
    return 1;
}

/* shel_write(SWM_BROADCAST): the message to every other process that is
 * there to read it, with word 1 the sender's id, as appl_write does. */
WORD sh_broadcast(const WORD *msg)
{
    WORD m[8], i;

    for (i = 0; i < 8; i++)
        m[i] = msg[i];
    m[1] = proc_pid(rlr);
    for (i = 0; i < proc_n; i++) {
        PROC *p = &proc_tab[i];
        if (p != rlr && p->p_stat != P_FREE && p->p_stat != P_DONE)
            mq_put(p, m);
    }
    return 1;
}

/* shel_write(SWM_ENVIRON): the AES's environment, sh_env, by size or
 * copied into the caller's buffer (which may be far: bytes cross).  The
 * copy answers how many bytes did NOT fit.  Changing it is not served. */
WORD sh_environ(WORD how, WORD len, uint32_t buf)
{
    WORD n = (WORD)sizeof sh_env;

    if (how == ENVIRON_SIZE)
        return n;
    if (how != ENVIRON_COPY || !buf || len < 0)
        return 0;
    if (len > n)
        len = n;
    far_copy(buf, (uint32_t)(uint16_t)sh_env, (uint16_t)len);
    return (WORD)(n - len);
}

/* ---- A PROGRAM PUT ASIDE (switcher step 2, docs/switcher-plan.md) --------
 *
 * shel_write(SWM_G4SUSPEND) from the running program puts it aside: its
 * state goes into one far record, it stops where it is -- inside this
 * call -- and the desktop comes back.  Started again from the desktop,
 * under the same name, it is RESUMED instead of loaded: the record is
 * put back and the call returns 1, the program's windows on the screen
 * again, redraws queued and WM_ONTOP for the top one.  XM/GEM's shape:
 * one program running, the others frozen, the desktop the way between
 * them.  Up to SH_PROGS of them, in the ring above, which the switch key
 * goes round (phase 129, sh_hotkey); the desktop is never put aside -- it
 * ends, kept dormant (phase 121), as it does to run any program.
 *
 * THE RECORD, in far memory, the system's (owner 0, so nothing of the
 * program's frees it), written in sequence rather than as a struct
 * (Calypsi's sizes, B7):
 *   SU_PARK   the park buffer the shell takes in place of the one the
 *             program keeps -- its engine stack is parked in that one
 *   SU_POOL   where the pool's section starts (the windows' is variable)
 *   SU_NAME   the eight-character name it was started under
 *   SU_TITLE  what it called itself for the Desk menu (menu_register), a
 *             copy, since the string may be in its own bank-$00 memory,
 *             which is not there while it is aside; SU_TPTR the pointer,
 *             which is again when it runs
 *   SU_APP    its APP and SU_CTX its context: the SHELL writes these two,
 *             after the switch, since both are the shell's to see
 *   SU_PROC   process 0's record after its context: queue count, waits,
 *             resources, files, DTA, name, messages
 *   SU_QUEUE  the application queue's sixteen messages
 *   SU_MENU   its menu bar, if the bar was its
 *   SU_DIR    the current drive and directories (gemdos_dirsave)
 *   SU_WIN    its windows (wm_save)
 *   then the pool: a count, and each of its bank-$00 blocks -- address,
 *   length, tag and bytes -- which are then FREED, so the desktop can
 *   take its own region back; resuming claims them where they were.
 * Its far blocks stay where they are, its own.  Its workstations, which
 * are owned by CONTEXT and process 0's context is shared, are kept under
 * SH_SUSPMARK until it runs again (vdi_retag_virtuals).
 *
 * A program that is not process 0, the desktop, a program not started
 * by the shell (an AUTO program, a Pexec child), or one with nowhere to
 * keep the record is refused: 0, and it carries on. */
#define SU_PARK     0
#define SU_POOL     4
#define SU_NAME     8
#define SU_TITLE    16
#define SU_TPTR     (SU_TITLE + MN_TITLELEN)
#define SU_APP      (SU_TPTR + 4)
#define SU_CTX      (SU_APP + sizeof(APP))
#define SU_PROC     (SU_CTX + sizeof(CTX))
#define SU_QUEUE    (SU_PROC + (sizeof(PROC) - sizeof(CTX)))
#define SU_MENU     (SU_QUEUE + NUM_MSGS * 16)
#define SU_DIR      (SU_MENU + 4)
#define SU_WIN      (SU_DIR + gemdos_dirsize())
/* ...under a MARKER OF ITS OWN: its owner, a number no context's address
 * can be (contexts are all above $2000) and one no other program loaded
 * has.  Phase 127 had one marker, which was right for one program aside
 * and wrong for two: resuming either retagged both programs' workstations
 * to process 0, the context every program runs in, and when it ended
 * vdi_close_virtuals closed the other's under it (phase 130). */
#define SH_SUSPMARK(own) ((void *)(uint16_t)(own))

/* What the one that ran last leaves the ring (ring_turn): its record if
 * it was put aside, SH_DESKREC if it was the desktop and it ended, 0 if
 * it was a program and it ended. */
ZWIN static uint32_t sh_left;
ZWIN uint8_t sh_parked;                 /* it was put aside in this run */
/* The owner of the program the shell is running: a program IT runs in
 * that program's context -- a Pexec child -- has another, and is not the
 * shell's to put aside (its parent's frames are under it). */
ZWIN static uint8_t sh_runown;
/* The program the Desk menu chose (sh_request), until a poll can switch
 * to it: a ring entry, or SH_SELF for the one running, or 0; with
 * SH_CLOSE when it was chosen with SHIFT, to be asked to end (phase
 * 131). */
ZWIN static uint32_t sh_want;          /* SH_SELF, SH_CLOSE: aes.h */

/* The ring's count, its entries, one entry; and the ring written back. */
static WORD ring_n(void)
{
    uint16_t n = 0;

    if (sh_cdir_far)
        far_get((uint8_t *)&n, sh_ring, 2);
    return (WORD)n;
}

static WORD ring_get(uint32_t *e)
{
    WORD n = ring_n();

    if (n)
        far_get((uint8_t *)e, sh_ring + 2, (uint16_t)(4 * n));
    return n;
}

static uint32_t ring_at(WORD k)
{
    uint32_t a;

    far_get((uint8_t *)&a, sh_ring + 2 + 4 * (uint32_t)k, 4);
    return a;
}

static void ring_put(const uint32_t *e, WORD n)
{
    uint16_t c = (uint16_t)n;

    far_put(sh_ring, (const uint8_t *)&c, 2);
    if (n)
        far_put(sh_ring + 2, (const uint8_t *)e, (uint16_t)(4 * n));
}

/* The entry that is the program `cmd` names, or -1: the same eight
 * characters appl_find would search (proc_name).  Names are unique in
 * the ring, since starting a name that is there resumes it. */
static WORD ring_find(const char *cmd)
{
    char name[AP_NAMELEN], want[AP_NAMELEN];
    WORD n = ring_n(), i;
    uint32_t a;

    if (!n)
        return -1;
    proc_nameto(want, cmd);             /* not proc_name: process 0 is
                                         * still whoever it is */
    for (i = 0; i < n; i++) {
        a = ring_at(i);
        if (a == SH_DESKREC)
            continue;
        far_get((uint8_t *)name, a + SU_NAME, AP_NAMELEN);
        if (memcmp(name, want, AP_NAMELEN) == 0)
            return i;
    }
    return -1;
}

/* The entry `a`'s place in the ring, or -1: a choice the menu made may
 * have gone (ended) before a poll could act on it. */
static WORD ring_index(uint32_t a)
{
    WORD n = ring_n(), i;

    for (i = 0; i < n; i++)
        if (ring_at(i) == a)
            return i;
    return -1;
}

/* What is about to run leaves the ring from entry k (-1: it was not in
 * it -- a program loaded, or the desktop at boot), and what ran last
 * takes its place in the gap (sh_left), which keeps the circle's order:
 * the entries after k, the one that stopped, the entries before k. */
static void ring_turn(WORD k)
{
    uint32_t e[SH_PROGS], t[SH_PROGS];
    uint32_t keep = sh_left;
    WORD n = ring_get(e), m = 0, i;

    sh_left = 0;
    if (k < 0) {
        if (keep && n < SH_PROGS)
            t[m++] = keep;
        for (i = 0; i < n; i++)
            t[m++] = e[i];
    } else {
        for (i = (WORD)(k + 1); i < n; i++)
            t[m++] = e[i];
        if (keep)
            t[m++] = keep;
        for (i = 0; i < k; i++)
            t[m++] = e[i];
    }
    ring_put(t, m);
}

/* What runs next is the ring's entry `to`: the desktop, or a program put
 * aside by its name, which sh_ldapp finds in the ring again. */
static void sh_goto(uint32_t to)
{
    char name[AP_NAMELEN + 1];
    WORD i;

    sh_isgem = 1;
    if (to == SH_DESKREC) {
        sh_next = SH_DESKTOP;
        sh_doexec = 0;
        return;
    }
    far_get((uint8_t *)name, to + SU_NAME, AP_NAMELEN);
    for (i = AP_NAMELEN; i > 0 && name[i - 1] == ' '; i--)
        ;
    name[i] = 0;
    far_strput(sh_cmd_far, name, (uint16_t)(i + 1));
    sh_next = SH_PROGRAM;
    sh_doexec = 1;
}

/* What runs in place of the one that stops: the desktop, for
 * shel_write(SWM_G4SUSPEND); the ring's first entry or its last, for the
 * switch key and shel_write(SWM_G4SWITCH) -- 0 when the ring is empty. */
#define SH_TONEXT   1
#define SH_TOPREV   2

static uint32_t ring_pick(WORD how)
{
    WORD n = ring_n();

    if (!n)
        return 0;
    if (how == SH_TOPREV)
        return ring_at((WORD)(n - 1));
    return ring_at(0);
}

/* Put the running program aside, with the ring's entry `to` to run in
 * its place: 1 once it is resumed, 0 refused, -1 no room for its record
 * (phase 132) -- which is far memory without purging the dormant desktop
 * or its resource files (far_keep1), since the program's memory stays held
 * while it is aside and they could not then be read again. */
static WORD sh_suspend(uint32_t to)
{
    uint8_t own = (uint8_t)proc_app->p_ctx.owner;
    uint8_t keep = far_owner, keept = far_tag, tag, wait;
    uint16_t at, len, nb, i;
    uint32_t rec, park, p, size, tree;
    char title[MN_TITLELEN];
    WORD max;

    if (rlr != proc_app || sh_deskrun || !own || own != sh_runown
        || ctx_root != proc_shell || !to)
        return 0;
    size = SU_WIN + wm_savesize() + 2;
    for (nb = 0; pool_owned(own, nb, &at, &len, &tag); nb++)
        size += 6 + len;
    far_owner = 0;                      /* the system's: see above */
    far_tag = 0;
    far_keep1 = 1;                      /* not at the dormant desktop's cost */
    rec = far_alloc_top(size);
    park = 0;
    if (rec)
        park = far_alloc(CTX_MAX);
    far_keep1 = 0;
    far_owner = keep;
    far_tag = keept;
    if (!park) {
        if (rec)
            far_free(rec);
        return -1;                      /* no room: phase 132 says so */
    }
    far_put(rec + SU_PARK, (const uint8_t *)&park, 4);
    far_put(rec + SU_NAME, (const uint8_t *)proc_app->p_name, AP_NAMELEN);
    title[0] = 0;
    if (mn_apptitle)
        far_strget(title, mn_apptitle, MN_TITLELEN);
    far_put(rec + SU_TITLE, (const uint8_t *)title, MN_TITLELEN);
    far_put(rec + SU_TPTR, (const uint8_t *)&mn_apptitle, 4);
    far_put(rec + SU_PROC, (const uint8_t *)proc_app + sizeof(CTX),
            (uint16_t)(sizeof(PROC) - sizeof(CTX)));
    far_put(rec + SU_QUEUE, (const uint8_t *)gl_appqueue(&max), NUM_MSGS * 16);
    tree = 0;
    if (mn_barowner() == 0)
        tree = (uint32_t)gl_mntree;
    far_put(rec + SU_MENU, (const uint8_t *)&tree, 4);
    gemdos_dirsave(rec + SU_DIR);
    p = rec + SU_WIN;
    p += wm_save(p);
    far_put(rec + SU_POOL, (const uint8_t *)&p, 4);
    far_put(p, (const uint8_t *)&nb, 2);
    p += 2;
    for (i = 0; i < nb; i++) {
        pool_owned(own, i, &at, &len, &tag);
        far_put(p, (const uint8_t *)&at, 2);
        far_put(p + 2, (const uint8_t *)&len, 2);
        far_put(p + 4, &tag, 1);
        far_put(p + 6, (const uint8_t *)at, len);
        p += 6 + len;
    }
    pool_free_owner(own);
    vdi_retag_virtuals(&proc_app->p_ctx, SH_SUSPMARK(own));
    sh_left = rec;
    sh_parked = 1;
    sh_closing = 0;                     /* a switch away ends a Quit's round */
    sh_goto(to);
    wait = ev_appwait;                  /* the switch key's: in an evnt_ */
    ctx_switch(ctx_root);               /* the shell; back here when it is
                                         * started again (sh_unpark) */
    ev_appwait = wait;                  /* ...which it still is */
    return 1;
}

/* shel_write(SWM_G4SWITCH): a program is put aside for the ring's next
 * (how 1), the one before (2), or the one `cmd` names (0, the eight
 * characters appl_find takes); the desktop, which is never put aside,
 * ends instead, with that program as the next thing the shell runs --
 * its answer to AP_G4SWITCH.  0 when there is nothing to switch to. */
static WORD sh_switch(WORD how, const char *cmd)
{
    uint32_t to = 0;
    WORD k;

    if (rlr != proc_app)
        return 0;
    if (how == SH_TONEXT || how == SH_TOPREV) {
        to = ring_pick(how);
    } else if (how == 0 && cmd) {
        k = ring_find(cmd);
        if (k >= 0)
            to = ring_at(k);
    }
    if (!to)
        return 0;
    if (!sh_deskrun)
        return (WORD)(sh_suspend(to) == 1);
    sh_goto(to);
    return 1;
}

/* The Desk menu's list (phase 130, src/aes/menu.c): how many programs
 * are loaded -- the desktop and every program, running or aside -- or 0
 * when the desktop is the only one, and the menu is then the program's
 * own. */
WORD sh_nprogs(void)
{
    WORD n = ring_n();

    return n ? (WORD)(n + 1) : 0;
}

/* The i-th of them, the desktop first and then round the circle: its
 * ring entry, or 0 for the one running; and in `text` (MN_TITLELEN) what
 * the menu says -- the title it gave menu_register, else LANG.RSC's name
 * for the desktop, else its own eight characters. */
uint32_t sh_prog(WORD i, char *text)
{
    WORD n = ring_n(), k = i, j;
    uint32_t e = 0;

    if (!sh_deskrun) {                  /* the desktop is in the ring */
        for (j = 0; j < n && ring_at(j) != SH_DESKREC; j++)
            ;
        k = (WORD)(j + i);              /* from it, then the running one */
        if (k > n)                      /* in the gap after the last */
            k = (WORD)(k - n - 1);
        else if (k == n)
            k = -1;
    } else {
        k = (WORD)(i - 1);              /* the desktop is the running one */
    }
    if (k >= 0)
        e = ring_at(k);
    text[0] = 0;
    if (!e && mn_apptitle)
        far_strget(text, mn_apptitle, MN_TITLELEN);
    else if (e && e != SH_DESKREC)
        far_strget(text, e + SU_TITLE, MN_TITLELEN);
    if (!text[0] && (e == SH_DESKREC || (!e && sh_deskrun))) {
        const char *d = lang_str(LS_MENU_DESKTOP);

        for (j = 0; j < MN_TITLELEN - 1 && d[j]; j++)   /* not strncpy: */
            text[j] = d[j];             /* the vendor's, and Apache-2.0 */
        text[j] = 0;
    } else if (!text[0]) {
        char name[AP_NAMELEN];

        if (e)
            far_get((uint8_t *)name, e + SU_NAME, AP_NAMELEN);
        else
            memcpy(name, proc_app->p_name, AP_NAMELEN);
        text[0] = text[1] = ' ';
        for (j = 0; j < AP_NAMELEN && name[j] != ' '; j++)
            text[2 + j] = name[j];
        text[2 + j] = 0;
    }
    return e;
}

/* ...and one chosen: switched to at the next poll that may (sh_hotkey),
 * since the menu is not yet over when it is chosen. */
void sh_request(uint32_t e)
{
    sh_want = e;
}

/* CLOSING ONE (phase 131): asked, never forced -- phase 123's rule, since
 * a program that never said it understands AP_TERM may be holding work
 * it would lose.  Whether `e` said so (shel_write(SWM_NEWMSG,
 * NM_APTERM)): the one running from its record, one aside from the copy
 * of its record it was put aside with, and the desktop, which answers
 * AP_TERM as Quit (src/desk/desktop.c), always. */
static WORD sh_takes_apterm(uint32_t e)
{
    WORD m = 0;

    if (e == SH_DESKREC)
        return TRUE;
    if (e == SH_SELF) {
        m = proc_app->p_msgs;
    } else {
        /* p_msgs is the record's last word, and SU_PROC holds the record
         * after its context, as far as sizeof(PROC) says in code -- the
         * same reckoning sh_suspend copied it with (Calypsi stopped with
         * an internal error on the pointer difference, ScaleIndex.hs) */
        far_get((uint8_t *)&m, e + SU_PROC + (sizeof(PROC) - sizeof(CTX) - 2), 2);
    }
    if (m & NM_APTERM)
        return TRUE;
    return FALSE;
}

/* The program `e` asked to end: AP_TERM to the one running; one aside, or
 * the desktop, switched to with AP_TERM waiting for it (sh_term, posted
 * by sh_ldapp as it is resumed).  One that cannot be asked is told so,
 * in an alert, and nothing else happens. */
/* An alert put up from a poll, in whatever process 0 is running: no
 * switch from inside it, so ev_appwait is put down for its length. */
static void sh_tell(WORD ls)
{
    uint8_t wait = ev_appwait;

    ev_appwait = 0;
    fm_alert(1, lang_str(ls));
    ev_appwait = wait;
}

static void sh_close(uint32_t e)
{
    WORD k, name[AP_NAMELEN / 2];

    if (!sh_takes_apterm(e)) {
        sh_tell(LS_NOTERM);
        return;
    }
    if (e == SH_SELF) {
        ap_sendmsg(proc_app, AP_TERM, 0, 0, AP_TERM, 0, 0);
        return;
    }
    sh_term = 1;
    if (!sh_deskrun) {
        k = sh_suspend(e);
        if (k != 1)
            sh_term = 0;
        if (k < 0)
            sh_tell(LS_NOASIDE);
        return;
    }
    for (k = 0; k < AP_NAMELEN / 2; k++)
        name[k] = 0;
    far_get((uint8_t *)name, e + SU_NAME, AP_NAMELEN);
    ap_sendmsg(proc_app, AP_G4SWITCH, 0, name[0], name[1], name[2], name[3]);
}

/* THE SWITCH KEY (phase 129): CONTROL-TAB, and SHIFT-CONTROL-TAB back,
 * which the VDI takes before the key queue (src/vdi/vdi.c), seen at every
 * poll.  Process 0's polls only, and only while a program runs there
 * (not the shell between two): an accessory's turn or the shell's
 * leaves it for the next, which is what lets a second press go one
 * further.  Acted on only while process 0 waits in an evnt_ call of its
 * own (ev_appwait), with nothing mid-gesture and nobody holding the
 * screen -- inside a form_do, a drag or an alert it is dropped, since
 * what is on the screen then is in no window a resume could redraw.  A
 * program is put aside; the desktop is sent AP_G4SWITCH and ends itself,
 * so that it leaves the way it always does (sh_switch). */
/* THE DESK MENU'S CHOICE (phase 130) comes the same way, and is KEPT
 * until a poll may act on it, not dropped: the menu ends with the button
 * still down, which is mid-gesture, and the choice is not undone by
 * that.  It is checked against the ring when acted on, since what was
 * chosen may have ended in between.  For the desktop, AP_G4SWITCH says 0
 * and carries the program's eight characters in msg[4..7]. */
void sh_hotkey(void)
{
    WORD how, k, name[AP_NAMELEN / 2];
    uint32_t to;

    if (rlr != proc_app || ctx_root != proc_shell)
        return;
    how = vdi_switchkey();
    if (!how && !sh_want)
        return;
    if (!ev_appwait || !ct_idle() || gl_ctmown || !wm_lockfree(0))
        return;                         /* the key dropped, a choice kept */
    if (how) {
        to = ring_pick(how);
    } else {
        to = sh_want;
        sh_want = 0;
        if ((to & ~SH_CLOSE) != SH_SELF && ring_index(to & ~SH_CLOSE) < 0)
            return;                     /* gone in between */
        if (to & SH_CLOSE) {
            sh_close(to & ~SH_CLOSE);
            return;
        }
    }
    if (!to)
        return;
    if (!sh_deskrun) {
        if (sh_suspend(to) < 0)
            sh_tell(LS_NOASIDE);        /* no room to keep it: phase 132 */
        return;
    }
    if (how) {
        ap_sendmsg(proc_app, AP_G4SWITCH, how, 0, 0, 0, 0);
        return;
    }
    for (k = 0; k < AP_NAMELEN / 2; k++)
        name[k] = 0;
    if (to != SH_DESKREC)
        far_get((uint8_t *)name, to + SU_NAME, AP_NAMELEN);
    ap_sendmsg(proc_app, AP_G4SWITCH, 0, name[0], name[1], name[2], name[3]);
}

WORD sh_write(WORD doex, WORD isgem, WORD isover, const char *pcmd,
              const char *ptail)
{
    (void)isover;
    if (!sh_cmd_far)
        return 0;
    switch (doex) {
    case 0:                                 /* SHW_NOEXEC: the desktop */
        far_write8(sh_cmd_far, 0);
        sh_doexec = doex;
        sh_isgem = 1;
        sh_next = SH_DESKTOP;
        break;
    case 1:                                 /* SHW_EXEC */
        far_strput(sh_cmd_far, pcmd, SH_CMDLEN);
        far_put(sh_tail_far, (const uint8_t *)ptail, SH_TAILLEN);
        sh_doexec = doex;
        sh_isgem = (isgem != 0);
        sh_next = SH_PROGRAM;
        break;
    case 4:                                 /* SWM_SHUTDOWN: above */
        return sh_shutdown(isgem);
    case 9:                                 /* SWM_NEWMSG: NM_APTERM */
        rlr->p_msgs = isgem;
        break;
    case SWM_G4SUSPEND:                     /* gem4xe's: above */
        return (WORD)(sh_suspend(SH_DESKREC) == 1);
    case SWM_G4SWITCH:
        return sh_switch(isgem, pcmd);
    default:
        /* 2 (a thread), 3 (an accessory now), 5 (a resolution change --
         * there is one resolution, and a program told yes would wait for
         * a RESCH_COMPLETED that never came), 6: not served, and SAID so.
         * They answered 1 until phase 123, which a program reads as done.
         * 7, 8 and 10 come through sh_broadcast, sh_environ and
         * sh_aesmsg, which take what those modes point at. */
        return 0;
    }
    return 1;
}

/* The buffer the application names is a full 24-bit address, as the ST's
 * is a 32-bit one: the desktop keeps its copy in far memory. */
void sh_get(uint32_t pbuffer, WORD len)
{
    if (!sh_buf_far || len <= 0)
        return;
    if (len > SH_BUFLEN)
        len = SH_BUFLEN;
    far_copy(pbuffer, sh_buf_far, (uint16_t)len);
}

void sh_put(uint32_t pdata, WORD len)
{
    if (!sh_buf_far || len <= 0)
        return;
    if (len > SH_BUFLEN)
        len = SH_BUFLEN;
    far_copy(sh_buf_far, pdata, (uint16_t)len);
}

/* The donor's, on the constant: the value after the name, or NULL. */
void sh_envrn(const char **ppath, const char *psrch)
{
    const char *p;
    WORD len = (WORD)strlen(psrch);

    *ppath = 0;
    for (p = sh_env; *p; ) {
        if (strncmp(p, psrch, len) == 0) {
            *ppath = p + len;
            break;
        }
        while (*p++)
            ;
    }
}

/* A GEM path into the name CIO opens: the DOS seam's rule (src/sys/dos.h).
 * `cio` holds CIO_NAME_MAX + 1. */
void sh_cioname(const char *gem, char *cio)
{
    /* Through GEMDOS, not straight to the DOS: a resource named without
     * a path belongs to the directory Dsetpath last named, which is the
     * application's own -- the desktop changes into it before it runs
     * one (src/desk/deskwin.c do_aopen).  Before this, an application in
     * a folder could not find its own resource: it opened in whatever
     * directory the boot batch had left the DOS in. */
    gd_cioname(gem, cio);
}

/* Does the file exist where the name says, or on the default drive (the
 * one entry in PATH=, and where CIO looks for a bare name anyway)?  The
 * donor rewrites pspec to where it found the file; here the name it was
 * given is already the name that opens it, so pspec is left alone. */
WORD sh_find(char *pspec)
{
    char name[CIO_NAME_MAX + 1];
    int16_t fd;

    sh_cioname(pspec, name);
    fd = cio_open(name, CIO_A_READ, 0);
    if (fd < 0)
        return 0;
    cio_close(fd);
    return 1;
}

/* ---- the shell loop ------------------------------------------------- */

/* ---- the accessories ---------------------------------------------------
 *
 * Every *.ACC in the system's own directory, loaded ONCE, before the
 * first program, and never freed.  Both halves of that sentence are
 * load-bearing.
 *
 * BEFORE THE FIRST PROGRAM, because until phase 117 bank $00's application
 * pool was a bump allocator that app_free wound back to where app_load
 * found it, and an accessory taken after the desktop would have been
 * freed underneath itself the first time a program exited.  Both
 * allocators free by owner now (src/sys/pool.h), so an accessory's
 * blocks -- taken at boot or later, its resource included -- are its own
 * and no program's exit touches them; the order stays because it is the
 * order the gates and tools/memreport.py measure, and the floor the
 * shell marks after it is what a mistaken release is refused against.
 * Loading an accessory later is a step of its own (docs/memory-plan.md).
 *
 * NEVER FREED, so the APP record app_load fills in is not kept: there is
 * nothing to give back.  What the AES keeps is a process (src/aes/proc.h)
 * and a context (src/sys/ctx.h).
 *
 * HOW MANY.  The Desk box has six slots; bank $00 has room for rather
 * fewer, the pool being 14 KB and the desktop with its resource most of
 * it.  So the loop stops when the pool says no and not when a constant
 * does, which is also what the donor does when its one allocation for
 * all the accessories fails.
 *
 * The directory is read the file selector's way (fs_active, src/aes/fsel.c):
 * the CIO directory channel, a line at a time, parsed by the DOS seam so
 * that a SpartaDOS and a DOS 2 list alike.  The names are collected
 * first and loaded afterwards, because loading reads files too.
 */
#define ACC_EXT     "ACC"
#define ACC_DIRLINE 17                  /* DOS 2's record, less its EOL */
#define ACC_NAMELEN 13                  /* NAME.EXT and its NUL: dos_dirline's */

WORD sh_naccs;                          /* accessories running */
WORD sh_accfull;                        /* found, and no room for: for the gate */

/* One accessory: a process, a queue, a context, and its first turn.
 * The turn is the donor's barrier in the simplest form it can take --
 * ctx_switch does not come back until the accessory has parked, and an
 * accessory parks when it reaches its first evnt_ call, which is after
 * it has registered its name. */
static WORD sh_ldacc(const char *name)
{
    APP   app;
    PROC *p;
    WORD *q;

    q = pool_alloc((WORD)(ACC_MSGS * 8 * sizeof(WORD)), 2);
    if (!q)
        return FALSE;
    p = proc_new(q, ACC_MSGS);
    if (!p)
        return FALSE;
    app_kind = OWN_ACC;                 /* its blocks say what it is */
    if (app_load_file(name, &app) != APP_OK || !ctx_make(&p->p_ctx, app.entry)) {
        proc_drop(p);
        return FALSE;
    }
    p->p_ctx.owner = app.owner;         /* what it takes is its own */
    p->p_ctx.floor = (uint16_t)(app.near_base + CTX_FLOOR);   /* ctx.h */
    proc_name(p, name);                 /* what appl_find will search */
    ctx_switch(&p->p_ctx);              /* runs until it parks */
    p->p_stat = P_LIVE;                 /* it has had its first turn */
    sh_naccs++;
    return TRUE;
}

/* ---- the AUTO folder ---------------------------------------------------
 *
 * \GEM\AUTO\, read before the accessories and before the keep mark, one
 * program at a time in the order the directory lists them -- which is
 * the ST's order and the only one a user can control, by the order they
 * copy the files in.
 *
 * WHY \GEM\AUTO\ AND NOT \AUTO\.  The ST puts it at the root because
 * TOS is the machine; here the system lives in \GEM\ and the accessories
 * are already \GEM\*.ACC rather than the root's, for the same reason --
 * the system is a directory you install, not a machine you boot.  So
 * AUTO goes beside them, travels with the system floppy's INSTALL.BAT,
 * and a second gem4xe on another drive keeps its own.
 *
 * WHAT RESIDENT MEANS, which is the whole of the design.  A program run
 * here is loaded and executed exactly as any other; when it returns, its
 * two regions are given back UNLESS it ended with Ptermres, in which
 * case they are simply not released and the next program is loaded above
 * them.  That works because both allocators free a program by its owner
 * (src/sys/pool.h, src/sys/farmem.c), and an owner nobody frees is
 * permanent; this also runs BEFORE pool_keep_mark(), so a resident
 * program's memory is under the floor, exactly as an accessory's is.
 *
 * So the ST's contract is kept -- run at boot, stay if you ask to -- by
 * the machinery accessories already proved, rather than by a second
 * allocator nobody needs yet.
 *
 * WHAT A RESIDENT PROGRAM CAN DO is up to it: it has run, so it has had
 * every chance to take a VDI vector (vex_timv and its kind), open files,
 * or leave data where something else will find it.  What it does NOT get
 * is a process record or a turn -- that is an accessory, and an
 * accessory is what to write if you want events.  A lister of what is
 * resident wants this table, which is why the names are kept rather than
 * counted.
 */
/* WHICH FILES AUTO RUNS.  TOS runs *.PRG and nothing else, and the
 * reason generalises: every program here is started with NO command
 * line, so an extension whose entire meaning is "takes parameters"
 * cannot be one of them.  .TTP is therefore deliberately absent, and
 * .G4A is present because it is what 0.5 shipped.  The desktop's list is
 * win_exts[] (src/desk/deskwin.c) and this one is that list less .TTP;
 * they are separate because they answer different questions -- what a
 * person may double-click, and what boots without being asked. */
static WORD sh_isprog(const char *name)
{
    static const char FAR exts[][4] = { "PRG", "G4A", "APP", "TOS" };
    const char *s = name;
    WORD i;

    while (*s && *s != '.')
        s++;
    if (s[0] != '.' || s[4])
        return FALSE;
    for (i = 0; i < 4; i++)
        if (s[1] == exts[i][0] && s[2] == exts[i][1] && s[3] == exts[i][2])
            return TRUE;
    return FALSE;
}

#define AUTO_DIR    "AUTO"
#define AUTO_MAX    6                   /* named, so a lister can show them;
                                         * six as the accessories are, and the
                                         * names are collected on the engine
                                         * stack exactly as sh_accs does it */

WORD sh_nauto;                          /* programs run out of AUTO */
WORD sh_nres;                           /* ...of which stayed resident */
/* THE NAMES ARE FAR, and memreport made that decision rather than me:
 * as a bank-$00 array this table was 104 bytes and took LoRAM from 323
 * free to 213, under its floor of 256, and the build failed.  Which is
 * the right answer anyway and the one the head of this file already
 * argues -- what the shell keeps FOR applications, across their
 * lifetimes, belongs in far memory; only what the AES reads itself has
 * to be near.  Nothing reads this but a lister. */
static uint32_t sh_res_far;             /* AUTO_MAX x ACC_NAMELEN, or 0 */
static uint32_t sh_auto_far;            /* ...and what the scan found */

/* One AUTO program: run it, and keep it only if it asked. */
static void sh_ldauto(const char *path, const char *name)
{
    APP  app;
    WORD st;
    RSHOLD held;

    app_kind = OWN_AUTO;
    if (app_load_file(path, &app) != APP_OK)
        return;                         /* a bad one is skipped, not fatal */
    proc_name(proc_app, name);
    gd_termres = 0;                     /* it has to ask, every time */
    sh_nauto++;
    rs_hold(&held);                     /* what it loads is its own */
    (void)app_exec(&app);
    rs_unclaim(&held);
    st = gd_termres;
    gd_termres = 0;
    if (!st) {
        app_free(&app);
        return;
    }
    /* IT STAYS.  Nothing is released, so its owner's blocks are kept and
     * the keep mark below puts them under the floor.  Past AUTO_MAX it is
     * still resident -- refusing to keep a program that has already run
     * and installed itself would be worse than not listing it -- so only
     * the NAME is dropped. */
    /* THE NAME, NOT THE PATH.  ACC_NAMELEN is NAME.EXT and its NUL, the
     * width a directory entry has; "AUTO>" in front of it is five bytes
     * this field does not have and the directory is not news to anybody
     * reading the list.  The gate caught the truncation, which is what a
     * fixed-width copy does instead of failing. */
    if (sh_nres < AUTO_MAX && sh_res_far)
        far_strput(sh_res_far + (uint32_t)sh_nres * ACC_NAMELEN,
                   name, ACC_NAMELEN);
    sh_nres++;
}

/* THE SCAN, IN A FRAME OF ITS OWN, and that is the whole reason it is a
 * separate function rather than the top of sh_auto.
 *
 * sh_ldauto RUNS A PROGRAM.  Whatever is on the engine stack when it does
 * is underneath that program for as long as it lives -- and this is
 * called from sh_start, so the scan's buffers would be under it too.
 * With the names collected in one frame and the programs run in another,
 * the first is gone before the second begins.  m17 measured the
 * difference: collected and run in one frame the engine stack came
 * within 216 bytes of its bottom and the gate said so.
 *
 * sh_accs never had the problem because ctx_switch gives an accessory a
 * stack of its own; an AUTO program runs on this one, as a program does.
 *
 * NOT STATIC, because this compiler inlines a static with one call site
 * (the same reason do_aopen is not, src/desk/deskwin.c) -- and inlining
 * it would put the buffers straight back into sh_auto's frame and undo
 * exactly what it is for.
 *
 * Returns how many names went into sh_auto_far. */
WORD sh_autoscan(void)
{
    char cio[CIO_NAME_MAX + 1], line[ACC_DIRLINE + 8], fname[ACC_NAMELEN];
    WORD n = 0;
    int16_t fd;

    sh_cioname(AUTO_DIR ">*.*", cio);
    fd = cio_open(cio, CIO_A_DIR, 0);
    if (fd < 0)
        return 0;                       /* no AUTO folder: nothing to do */
    /* Taken only when there IS one, and before the keep mark like every
     * other thing this file keeps, so a machine with no AUTO folder pays
     * nothing for the feature. */
    if (!sh_auto_far) {
        sh_auto_far = far_alloc(AUTO_MAX * ACC_NAMELEN);
        sh_res_far  = far_alloc(AUTO_MAX * ACC_NAMELEN);
    }
    if (!sh_auto_far || !sh_res_far) {
        cio_close(fd);
        return 0;
    }
    while (n < AUTO_MAX) {
        uint16_t got = 0;
        uint8_t  st = cio_getrec(fd, line, sizeof line, &got);
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        if ((dos_dirline(line, got, fname, 0) & DOS_ENT_KIND) == DOS_ENT_FILE
            && sh_isprog(fname)) {
            far_strput(sh_auto_far + (uint32_t)n * ACC_NAMELEN,
                       fname, ACC_NAMELEN);
            n++;
        }
        if (st == CIO_OK_EOF)
            break;
    }
    cio_close(fd);
    return n;
}

/* Run what the scan found, in the order the directory gave -- which is
 * the ST's order, and the only one a user controls, by the order they
 * copy the files in.  The scan's frame is gone by now. */
static void sh_auto(void)
{
    WORD n = sh_autoscan();
    WORD i;

    for (i = 0; i < n; i++) {
        char path[ACC_NAMELEN + sizeof AUTO_DIR + 2];
        WORD k, j;

        for (k = 0; k < (WORD)(sizeof AUTO_DIR) - 1; k++)
            path[k] = AUTO_DIR[k];
        path[k++] = '>';
        far_strget(path + k, sh_auto_far + (uint32_t)i * ACC_NAMELEN,
                   ACC_NAMELEN);
        for (j = 0; path[k + j]; j++)
            ;
        path[k + j] = 0;
        sh_ldauto(path, path + k);
    }
}

/* ---- the control panel's extensions ------------------------------------
 *
 * \GEM\*.CPX, listed here beside the accessories.  Each file is the
 * module's 512-byte header, then the module (src/app/cpx.h), so the
 * table is filled by READING headers, as XControl does -- nothing runs to
 * be listed (phase 133).  Only a module whose flags ask is loaded at
 * boot: CPX_BOOTINIT, so the panel can boot-init it; CPX_RESIDENT, which
 * is never freed; CPX_SETONLY, which acts at boot and has no dialog.
 * After the panel has boot-initialised them, every one that is not
 * resident is FREED again before the keep mark (sh_cpxdropall).  The rest
 * are loaded when they are opened (Cpxload, sh_cpxload below) and freed
 * when they close: the ST's rule, and phase 118's.  A module costs the
 * pool nothing while it is closed.
 *
 * Until phase 133 every module was run at boot just to fill a header
 * kept inside it, and six was the most there could be.
 *
 * ON DEMAND became possible in phase 117.  Until then bank $00's pool
 * was a bump allocator, and a module loaded while the desktop was up sat
 * above the desktop's mark and would have been freed out from under the
 * panel the moment the desktop exited to run a program.  Both allocators
 * free by owner now, and a module is an owner of its own.
 *
 * WHAT THE SHELL DOES AND DOES NOT DO.  It finds them, reads their
 * headers, loads the ones that ask, and keeps the vtables.  It does not
 * draw anything: the panel (CONTROL.ACC) asks for the list and drives
 * whichever the user picks.  That split is the point of a CPX -- the
 * host owns the window and the event loop, the module owns the dialog.
 */
#define CPX_EXT     "CPX"
#define CPX_MAX     16                  /* a ceiling: the table is sized to
                                         * what the scan finds, and XControl
                                         * lists ten before it scrolls */

WORD sh_ncpx;                           /* modules listed */
WORD sh_cpxbad;                         /* ...and found but refused: the gate */
WORD sh_cpxcfgs;                        /* settings files found and read */
ZWIN WORD sh_cpxdrops;                  /* ...freed after boot-init, for the gate;
                                         * zwin: LoRAM is at its floor */
ZWIN WORD sh_cpxruns;                   /* ...loaded at boot, for the gate */
static uint32_t sh_cpx_far;             /* CPX_MAX owners (CPXE_OWN), then
                                         * sh_ncpx slots (CPXE_SLOT) */

/* One entry of the table, laid out by hand because this file must agree
 * with src/app/cpx.h without including it -- the AES is small-data and
 * cpx.h is the application's header, in the application's model. */
#define CPXE_INFO   0                   /* uint32_t: the module's CPXINFO  */
#define CPXE_FILE   4                   /* char[16]: its file name         */
#define CPXE_FILELEN 16                 /* SIXTEEN: fourteen useful bytes,
                                         * padded, because the application
                                         * side is a struct and this
                                         * compiler pads one (src/app/cpx.h
                                         * says what that cost) */
#define CPXE_HDR    20                  /* CPX_HDR_SIZE bytes of header    */
#define CPX_HDR_SZ  512
#define CPXE_SIZE   (CPXE_HDR + CPX_HDR_SZ)
/* Each loaded module's owner, a byte a slot IN FRONT of the slots, where
 * the panel's stride never reaches: what frees it.  0: not loaded.  In
 * front because the table is as long as the scan found, and the owners
 * cannot sit after an end only the scan knows without a second near
 * variable to remember it. */
#define CPXE_OWN(i)  (sh_cpx_far + (uint32_t)(i))
#define CPXE_SLOT(i) (sh_cpx_far + CPX_MAX + (uint32_t)(i) * CPXE_SIZE)
#define CPXH_MAGIC  0                   /* the header's magic word */
#define CPXH_FLAGS  2                   /* ...and its flags word */
#define CPX_MAGICW  0x6811              /* src/app/cpx.h CPX_MAGIC */
#define CPXF_SETONLY  0x0001            /* src/app/cpx.h's three flags */
#define CPXF_BOOTINIT 0x0002
#define CPXF_RESIDENT 0x0004
/* Where a module's settings live inside its header, and how many.  The
 * panel reaches them through XCPB's `buffer` and writes them back with
 * CPX_Save; the shell reads them off the disk below.  Atari's offsets
 * (src/app/cpx.h's map). */
#define CPXH_BUF    142
#define CPXH_BUFLEN 64
#define CPX_CFGEXT  "CFG"

/* ONE MODULE, AND WHY IT IS RUN RATHER THAN CALLED.
 *
 * The obvious thing is to load the module and call its cpx_init through
 * a far pointer -- Calypsi compiles that to a real long indirect call
 * and it works.  IT WOULD BE WRONG.  A program's initialised data is not
 * in its image: the crt installs it, walking data_init_table
 * (src/app/crt_gemapp.s).  Enter a module anywhere but its crt and every
 * initialised global it has is whatever was in that memory before --
 * silently, which is the failure shape this project keeps meeting.
 *
 * So a module is RUN, as a program, through app_run, and it ends with
 * Ptermres so the shell keeps it -- the AUTO folder's machinery exactly
 * (sh_ldauto above), for the same reason and with the same guarantee.
 * By the time it returns its data is live, its dialog is built, and the
 * vtable it published is callable.
 *
 * HOW IT PUBLISHES.  Its command tail carries the address of its own
 * slot in the table below -- three bytes, in the ST's tail shape, a
 * length byte then the bytes -- and the kit's cpx glue writes the
 * CPXINFO pointer there before returning.  The tail is how a program has
 * always been told what to do, so nothing new had to be invented for
 * it. */
/* A MODULE'S SETTINGS, read off the disk into its header's buffer once
 * the header itself has been read, which is the ST's order: XControl
 * keeps the saved bytes in the .CPX and hands them over with the rest.
 * Here they are in a file beside the module, so they are laid over the
 * header's defaults.  A module sees them at cpx_call, as XCPB's buffer.
 *
 * A missing file is the normal case and is silent: it means nothing has
 * been saved yet, and the defaults in the header stand. */
/* A MODULE'S FILE NAMED AS THE BOOT FOUND IT (phase 141): a bare name,
 * through the DOS seam, so it is the DOS's own folder that decides --
 * where the scan found the modules at boot, before anybody set a GEMDOS
 * path.  Through sh_cioname a runtime call went by GEMDOS's path
 * instead, which the desktop sets to the folder of the last program it
 * ran: a module, its settings and CONTROL.INF were looked for, or
 * written, somewhere else (docs/phase141.md).  app_load_file names a
 * file this way already, which is why booting one always worked. */
static void sh_cpxcio(const char *name, char *cio)
{
    dos_cioname(name, cio);
}

static void sh_cpxcfg(uint32_t e, const char *name)
{
    char cfg[CIO_NAME_MAX + 1], base[ACC_NAMELEN + 8];
    uint8_t buf[CPXH_BUFLEN];
    int16_t fd;
    uint16_t got = 0;
    WORD i;

    for (i = 0; i < ACC_NAMELEN - 1 && name[i] && name[i] != '.'; i++)
        base[i] = name[i];
    base[i++] = '.';
    base[i++] = CPX_CFGEXT[0];
    base[i++] = CPX_CFGEXT[1];
    base[i++] = CPX_CFGEXT[2];
    base[i] = 0;
    sh_cpxcio(base, cfg);
    fd = cio_open(cfg, CIO_A_READ, 0);
    if (fd < 0)
        return;                         /* nothing saved yet */
    if (cio_read(fd, buf, (uint16_t)CPXH_BUFLEN, &got) == CIO_OK
        || got == CPXH_BUFLEN) {
        far_put(e + CPXE_HDR + CPXH_BUF, buf, CPXH_BUFLEN);
        sh_cpxcfgs++;
    }
    cio_close(fd);
}

/* A MODULE'S HEADER, the file's first 512 bytes, into slot e -- in
 * pieces, through a buffer the size of the settings, because 512 bytes
 * of bank $00's stack is not there to spend.  1 if it is a header of
 * ours; 0 for a short file or a foreign one (an ST's CPX begins with
 * 100, a bare .G4A with 'G4A'), which is then not listed. */
static WORD sh_cpxhead(uint32_t e, const char *name)
{
    char cio[CIO_NAME_MAX + 1];
    uint8_t buf[CPXH_BUFLEN];
    int16_t fd;
    uint16_t got;
    WORD k, ok = 1;

    sh_cpxcio(name, cio);
    fd = cio_open(cio, CIO_A_READ, 0);
    if (fd < 0)
        return 0;
    for (k = 0; ok && k < CPX_HDR_SZ / CPXH_BUFLEN; k++) {
        uint8_t st;

        got = 0;
        st = cio_read(fd, buf, (uint16_t)CPXH_BUFLEN, &got);
        /* CIO answers 1 for a read, and 3 when the next would find the
         * end -- either is a whole piece if every byte came */
        if ((st != CIO_OK && st != CIO_OK_EOF) || got != CPXH_BUFLEN
            || (k == 0 && (buf[CPXH_MAGIC] != (CPX_MAGICW & 0xFF)
                           || buf[CPXH_MAGIC + 1] != (CPX_MAGICW >> 8))))
            ok = 0;
        else
            far_put(e + CPXE_HDR + (uint32_t)k * CPXH_BUFLEN, buf,
                    CPXH_BUFLEN);
    }
    cio_close(fd);
    return ok;
}

/* MODULE i LOADED AT BOOT, because its header asks: run, as above, with
 * its slot's address in the tail.  A module that declines, or ends
 * without asking to stay, stays LISTED -- its header is good -- with no
 * vtable, and opening it tries again and says why it could not. */
static void sh_ldcpx(WORD i)
{
    APP      app;
    uint32_t e = CPXE_SLOT(i);
    uint8_t  tail[5];
    uint32_t info = 0;
    RSHOLD   held;
    char     name[CPXE_FILELEN];

    far_strget(name, e + CPXE_FILE, CPXE_FILELEN);
    app_kind = OWN_CPX;
    if (app_load_file(name, &app) != APP_OK) {
        sh_cpxbad++;
        return;
    }
    tail[0] = 3;                        /* the ST's tail: a length, then it */
    tail[1] = (uint8_t)(e & 0xFF);
    tail[2] = (uint8_t)((e >> 8) & 0xFF);
    tail[3] = (uint8_t)((e >> 16) & 0xFF);
    tail[4] = 0x0D;
    far_put(sh_tail_far, tail, sizeof tail);
    far_strput(sh_cmd_far, name, SH_CMDLEN);
    gd_termres = 0;
    rs_hold(&held);                     /* its resource is its own */
    (void)app_exec(&app);               /* as its own owner */
    rs_unclaim(&held);
    far_get((uint8_t *)&info, e + CPXE_INFO, 4);
    if (!info || !gd_termres) {
        /* It declined, or ended without asking to stay -- either way
         * there is nothing to keep and keeping it would be a leak that
         * never comes back, since this is below the keep mark. */
        app_free(&app);
        info = 0;
        far_put(e + CPXE_INFO, (const uint8_t *)&info, 4);
        sh_cpxbad++;
        gd_termres = 0;
        return;
    }
    gd_termres = 0;
    far_write8(CPXE_OWN(i), (uint8_t)app.owner);
    sh_cpxruns++;
}

/* The directory, once to count and once to fill: one pass would need
 * the names kept somewhere until the table could be sized, which is
 * bank $00's stack again.  With tab 0 it counts the *.CPX names; with a
 * table it reads each one's header into the next slot, and a file that
 * is not one of ours is passed over and counted as refused.  Either way
 * it answers how many it took, at most `most`. */
static WORD sh_cpxdir(uint32_t tab, WORD most)
{
    char cio[CIO_NAME_MAX + 1], line[ACC_DIRLINE + 8], fname[ACC_NAMELEN];
    WORD n = 0;
    int16_t fd;

    sh_cpxcio("*." CPX_EXT, cio);
    fd = cio_open(cio, CIO_A_DIR, 0);
    if (fd < 0)
        return 0;
    while (n < most) {
        uint16_t got = 0;
        uint8_t  st = cio_getrec(fd, line, sizeof line, &got);
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        if ((dos_dirline(line, got, fname, 0) & DOS_ENT_KIND) == DOS_ENT_FILE
            && dos_wildcmp("*." CPX_EXT, fname)) {
            if (!tab)
                n++;
            else if (sh_cpxhead(CPXE_SLOT(n), fname)) {
                far_strput(CPXE_SLOT(n) + CPXE_FILE, fname, CPXE_FILELEN);
                sh_cpxcfg(CPXE_SLOT(n), fname);
                n++;
            } else
                sh_cpxbad++;
        }
        if (st == CIO_OK_EOF)
            break;
    }
    cio_close(fd);
    return n;
}

/* The scan, in a frame of its own, for sh_autoscan's reason: the
 * modules that load at boot are RUN afterwards (sh_cpx), and the scan's
 * buffers must not be under them. */
WORD sh_cpxscan(void)
{
    WORD n;

    /* THE NAMES FIRST, AND THE TABLE ONLY IF THERE ARE ANY.  Opening a
     * WILDCARD as a directory succeeds whether or not anything matches
     * -- unlike the AUTO folder, where a missing directory fails to open
     * and the question never arises.  Allocating here regardless cost
     * every machine 3,160 bytes of far memory for a table it had no
     * modules to put in, and test-m16 said so: it checks that the far
     * heap moved by the desktop's file and nothing else, which is
     * exactly the kind of quiet growth it exists to catch. */
    n = sh_cpxdir(0, CPX_MAX);
    if (!n)
        return 0;                       /* no modules: nothing is taken */
    if (!sh_cpx_far)
        sh_cpx_far = far_alloc(CPX_MAX + (uint32_t)n * CPXE_SIZE);
    if (!sh_cpx_far)
        return 0;
    far_fill(sh_cpx_far, 0, CPX_MAX + (uint32_t)n * CPXE_SIZE);
    /* the second pass takes no more than the first counted: the table
     * has room for exactly that many */
    sh_ncpx = sh_cpxdir(sh_cpx_far, n);
    return sh_ncpx;
}

/* WHAT THE PANEL ASKS FOR.  The module's vtable, by index, or 0.  This
 * is the whole of the shell's side of the contract: it finds and loads
 * and keeps, and hands back what it kept.  Drawing and events are the
 * panel's (CONTROL.ACC), because a CPX's entire shape is that the host
 * owns the window and the module owns the dialog. */
uint32_t sh_cpxinfo(WORD i)
{
    uint32_t info = 0;

    if (i < 0 || i >= sh_ncpx || !sh_cpx_far)
        return 0;
    far_get((uint8_t *)&info, CPXE_SLOT(i) + CPXE_INFO, 4);
    return info;
}

/* THE WHOLE TABLE, for appl_getinfo(AI_CPX): a program strides it
 * itself rather than asking for one field at a time, which would be a
 * call per icon per redraw.  0 when nothing is listed -- and nothing is
 * allocated then either, so a machine with no modules pays nothing. */
uint32_t sh_cpxtable(void)
{
    return sh_ncpx ? CPXE_SLOT(0) : 0;
}

WORD sh_cpxstride(void)
{
    return CPXE_SIZE;
}

/* ...and its header, for a lister: the title, the icon and the flags,
 * read from the front of its file. */
uint32_t sh_cpxhdr(WORD i)
{
    if (i < 0 || i >= sh_ncpx || !sh_cpx_far)
        return 0;
    return CPXE_SLOT(i) + CPXE_HDR;
}

/* MODULE i FREED, unless it asked to stay: its owner's blocks in both
 * allocators, which is its near region, its far image and whatever it
 * loaded -- its resource included.  The slot keeps the header, the file
 * name and the settings, which is all the panel lists it from, and its
 * vtable goes to 0, which is how the panel knows to ask for it again.
 * 1 if it was freed. */
static WORD sh_cpxdrop(WORD i)
{
    uint32_t e = CPXE_SLOT(i);
    uint32_t zero = 0;
    uint8_t  own;
    UWORD    flags = 0;

    if (sh_cpxinfo(i) == 0)
        return 0;
    far_get((uint8_t *)&flags, e + CPXE_HDR + CPXH_FLAGS, 2);
    if (flags & CPXF_RESIDENT)
        return 0;
    own = far_read8(CPXE_OWN(i));
    if (!own)
        return 0;                       /* never the system's */
    pool_free_owner(own);
    far_free_owner(own);
    far_put(e + CPXE_INFO, (const uint8_t *)&zero, 4);
    far_write8(CPXE_OWN(i), 0);
    return 1;
}

/* After the panel has boot-initialised them (it runs as an accessory,
 * before this), every module that did not ask to stay goes. */
static void sh_cpxdropall(void)
{
    WORD i;

    sh_cpxdrops = 0;
    for (i = 0; i < sh_ncpx; i++)
        sh_cpxdrops += sh_cpxdrop(i);
}

/* Cpxload (GEMDOS 0x1F3, src/sys/gemdos.h): module i loaded again, or
 * freed.  0 when it is loaded (or freed) now, a GEMDOS error when not.
 *
 * LOADING IS RUNNING IT, as at boot and for the same reason (sh_ldcpx,
 * "why it is run rather than called"): its crt installs its data and its
 * cpx_init builds its dialog and publishes its vtable.  It is run through
 * gd_run, Pexec's own machinery, because this is a call from inside the
 * panel's process and the module makes calls of its own; it is kept
 * because it ends with Ptermres.  Its header and settings are the slot's
 * already, and the module leaves them alone (src/app/cpxmain.c). */
int32_t sh_cpxload(WORD i, WORD on)
{
    uint32_t e, info = 0;
    char     name[CPXE_FILELEN], cio[CIO_NAME_MAX + 1];
    uint8_t  tail[5];
    uint16_t near;
    APP      app;
    WORD     st, kept;

    if (i < 0 || i >= sh_ncpx || !sh_cpx_far)
        return GD_ERANGE;
    if (!on) {
        sh_cpxdrop(i);
        return 0;
    }
    if (sh_cpxinfo(i))
        return 0;                       /* resident, or still open */
    if (!gd_room_to_run())
        return GD_ENSMEM;
    e = CPXE_SLOT(i);
    far_strget(name, e + CPXE_FILE, CPXE_FILELEN);
    sh_cpxcio(name, cio);
    near = app_near;
    app_kind = OWN_CPX;
    st = app_load_cio(cio, &app);
    if (st != APP_OK) {
        app_near = near;
        return gd_loaderr(st);
    }
    tail[0] = 3;                        /* the ST's tail: a length, then it */
    tail[1] = (uint8_t)(e & 0xFF);
    tail[2] = (uint8_t)((e >> 8) & 0xFF);
    tail[3] = (uint8_t)((e >> 16) & 0xFF);
    tail[4] = 0x0D;
    (void)gd_run(&app, name, (uint32_t)(uint16_t)tail, 1, &kept);
    app_near = near;
    far_get((uint8_t *)&info, e + CPXE_INFO, 4);
    if (!kept || !info) {
        if (kept) {                     /* stayed, and published nothing */
            pool_free_owner((uint8_t)app.owner);
            far_free_owner((uint8_t)app.owner);
        }
        info = 0;
        far_put(e + CPXE_INFO, (const uint8_t *)&info, 4);
        return GD_EPLFMT;
    }
    far_write8(CPXE_OWN(i), (uint8_t)app.owner);
    return 0;
}

/* ---- managing the modules (phase 141, docs/cpanel-plan.md step 4) ------
 *
 * Cpxfile (GEMDOS 0x1F6, src/sys/gemdos.h): what the panel's Options do
 * to the modules' folder and table, here because only here are the
 * modules' files named as the boot found them (sh_cpxcio). */

/* RELOAD: the folder read again into a table of its own, as at boot.
 * Refused while a module that is not resident is loaded -- one is open.
 * A resident module keeps its slot, its vtable, its owner and its live
 * settings, found again by its file name; one whose file has gone stays
 * loaded, unlisted, until the machine restarts.  The old table is given
 * back.  Answers how many are listed. */
static int32_t sh_cpxreload(void)
{
    uint32_t old = sh_cpx_far, tab = 0, oe, info, size;
    WORD oldn = sh_ncpx, n, i, j;
    uint8_t keep = far_owner, keept = far_tag, own;
    UWORD flags;
    char a[CPXE_FILELEN], b[CPXE_FILELEN];
    uint8_t buf[CPXH_BUFLEN];

    for (i = 0; i < oldn; i++) {
        flags = 0;
        far_get((uint8_t *)&flags, CPXE_SLOT(i) + CPXE_HDR + CPXH_FLAGS, 2);
        if (sh_cpxinfo(i) && !(flags & CPXF_RESIDENT))
            return GD_EACCDN;
    }
    n = sh_cpxdir(0, CPX_MAX);
    if (n) {
        size = CPX_MAX + (uint32_t)n * CPXE_SIZE;
        far_owner = 0;                  /* the system's, as the first one */
        far_tag = 0;
        tab = far_alloc(size);
        far_owner = keep;
        far_tag = keept;
        if (!tab)
            return GD_ENSMEM;
        far_fill(tab, 0, size);
    }
    sh_cpx_far = tab;
    sh_cpxbad = 0;
    sh_ncpx = n ? sh_cpxdir(tab, n) : 0;
    for (i = 0; old && i < oldn; i++) {
        oe = old + CPX_MAX + (uint32_t)i * CPXE_SIZE;
        info = 0;
        far_get((uint8_t *)&info, oe + CPXE_INFO, 4);
        if (!info)
            continue;
        far_strget(a, oe + CPXE_FILE, CPXE_FILELEN);
        own = far_read8(old + (uint32_t)i);
        for (j = 0; j < sh_ncpx; j++) {
            far_strget(b, CPXE_SLOT(j) + CPXE_FILE, CPXE_FILELEN);
            if (strcmp(a, b) == 0) {
                far_put(CPXE_SLOT(j) + CPXE_INFO, (const uint8_t *)&info, 4);
                far_write8(CPXE_OWN(j), own);
                far_get(buf, oe + CPXE_HDR + CPXH_BUF, CPXH_BUFLEN);
                far_put(CPXE_SLOT(j) + CPXE_HDR + CPXH_BUF, buf, CPXH_BUFLEN);
                break;
            }
        }
    }
    if (old)
        far_free(old);
    return sh_ncpx;
}

/* UNLOAD: slot i out of the table until the next reload or restart --
 * XControl's -- refused for one that is loaded: resident, or open. */
static int32_t sh_cpxunload(WORD i)
{
    WORD k;

    if (i < 0 || i >= sh_ncpx || !sh_cpx_far)
        return GD_ERANGE;
    if (sh_cpxinfo(i))
        return GD_EACCDN;
    for (k = i; k < sh_ncpx - 1; k++) {
        far_copy(CPXE_SLOT(k), CPXE_SLOT(k + 1), CPXE_SIZE);
        far_write8(CPXE_OWN(k), far_read8(CPXE_OWN(k + 1)));
    }
    far_fill(CPXE_SLOT(sh_ncpx - 1), 0, CPXE_SIZE);
    far_write8(CPXE_OWN(sh_ncpx - 1), 0);
    sh_ncpx--;
    return 0;
}

/* A FILE MADE BESIDE THE MODULES (phase 141).  On G4DOS a bare name made
 * goes to the root -- its flat view's rule, src/fdos.s WRITING -- so a
 * module's NAME.CFG goes into the folder its NAME.CPX was found in, and
 * anything else into the first module's: where the panel and the AES
 * look for them, beside the modules, not in the root.  Another DOS makes
 * a bare name in its own folder, where the boot found the modules, so it
 * is left a bare name there. */
static WORD sh_cpxbeside(const char *name, char *cio)
{
    char near_[ACC_NAMELEN + 2], pre[CIO_NAME_MAX + 1];
    WORD i, n;

    if (dos.kind != DOS_G4DOS)
        return 0;
    for (i = 0; i < ACC_NAMELEN && name[i] && name[i] != '.'; i++)
        near_[i] = name[i];
    n = i;
    if (name[i] == '.' && (name[i + 1] | 0x20) == 'c'
        && (name[i + 2] | 0x20) == 'f' && (name[i + 3] | 0x20) == 'g') {
        near_[n++] = '.';
        near_[n++] = 'C';
        near_[n++] = 'P';
        near_[n++] = 'X';
        near_[n] = 0;
    } else if (sh_ncpx && sh_cpx_far)
        far_strget(near_, CPXE_SLOT(0) + CPXE_FILE, ACC_NAMELEN);
    else
        return 0;
    if (!sdc_folder(near_, pre))
        return 0;
    n = (WORD)strlen(pre);
    for (i = 0; name[i] && n < CIO_NAME_MAX; i++) {
        int c = (uint8_t)name[i];       /* not a byte: B8/B21, tools/ccbug --
                                         * a char changed in place left the
                                         * join after it in either width */

        if (c >= 'a' && c <= 'z')
            c -= 0x20;
        pre[n++] = (char)c;
    }
    pre[n] = 0;
    strcpy(cio, pre);
    return 1;
}

#define CF_RELOAD   0                   /* src/app/gem.h, Cpxfile */
#define CF_UNLOAD   1
#define CF_READ     2
#define CF_WRITE    3
#define CF_RENAME   4
#define CF_FIND     5
#define CF_MAXIO    64                  /* bytes a read or write: a .CFG */

/* The modules' folder, for the panel: a file of up to CF_MAXIO bytes read
 * or written, a file renamed, the n-th name matching a pattern -- each
 * name bare, and named as the boot found the modules.  `a` and `b` are
 * the caller's far addresses. */
int32_t sh_cpxfile(WORD op, WORD i, uint32_t a, uint32_t b)
{
    char name[ACC_NAMELEN + 2], cio[CIO_NAME_MAX + 1];
    uint8_t buf[CF_MAXIO];
    uint16_t got = 0;
    int16_t fd;
    uint8_t st;
    WORD n;

    if (op == CF_RELOAD)
        return sh_cpxreload();
    if (op == CF_UNLOAD)
        return sh_cpxunload(i);
    if (op < CF_READ || op > CF_FIND || !a)
        return GD_EINVFN;
    far_strget(name, a, ACC_NAMELEN);
    sh_cpxcio(name, cio);
    if (op == CF_READ || op == CF_WRITE) {
        if (i < 0 || i > CF_MAXIO || !b)
            return GD_ERANGE;
        if (op == CF_READ) {
            fd = cio_open(cio, CIO_A_READ, 0);
            if (fd < 0)
                return GD_EFILNF;
            st = cio_read(fd, buf, (uint16_t)i, &got);
            cio_close(fd);
            if (st != CIO_OK && st != CIO_OK_EOF && !got)
                return GD_EREADF;
            far_put(b, buf, got);
            return (int32_t)got;
        }
        far_get(buf, b, (uint16_t)i);
        n = sh_cpxbeside(name, cio);
        fd = cio_open(cio, CIO_A_WRITE, 0);
        if (fd < 0)
            return GD_EACCDN;
        st = cio_write(fd, buf, (uint16_t)i);
        cio_close(fd);
        if (st != CIO_OK && st != CIO_OK_EOF)
            return GD_EACCDN;
        if (n) {
            /* a copy an older gem4xe saved in the root would be found
             * before this one, the root being read first: it goes */
            cio[0] = 'D';
            cio[1] = '1';
            cio[2] = ':';
            cio[3] = (char)dos.dirsep;
            sh_cpxcio(name, cio + 4);
            (void)cio_xio(CIO_X_DELETE, cio, 0, 0);
        }
        return (int32_t)i;
    }
    if (op == CF_RENAME) {
        char nn[ACC_NAMELEN + 2];

        if (!b)
            return GD_EINVFN;
        far_strget(nn, b, ACC_NAMELEN);
        n = (WORD)strlen(cio);
        if (n + 1 + (WORD)strlen(nn) > CIO_NAME_MAX)
            return GD_EPTHNF;
        cio[n] = ',';
        strcpy(cio + n + 1, nn);
        st = cio_xio(CIO_X_RENAME, cio, 0, 0);
        if (st != CIO_OK && st != CIO_OK_EOF)
            return GD_EACCDN;           /* SDX 4.49e's XIO 32 says so too */
        return 0;
    }
    /* CF_FIND: the i-th file whose name matches `a`, into b */
    {
        char line[ACC_DIRLINE + 8], fname[ACC_NAMELEN];
        WORD k = 0;

        if (!b)
            return GD_EINVFN;
        fd = cio_open(cio, CIO_A_DIR, 0);
        if (fd < 0)
            return GD_ENMFIL;
        for (;;) {
            uint16_t len = 0;

            st = cio_getrec(fd, line, sizeof line, &len);
            if (st != CIO_OK && st != CIO_OK_EOF)
                break;
            if ((dos_dirline(line, len, fname, 0) & DOS_ENT_KIND)
                == DOS_ENT_FILE && dos_wildcmp(name, fname) && k++ == i) {
                cio_close(fd);
                far_strput(b, fname, ACC_NAMELEN);
                return 0;
            }
            if (st == CIO_OK_EOF)
                break;
        }
        cio_close(fd);
        return GD_ENMFIL;
    }
}

/* The scan, then the modules that asked to be loaded at boot. */
static void sh_cpx(void)
{
    WORD n = sh_cpxscan();
    WORD i;

    for (i = 0; i < n; i++) {
        UWORD flags = 0;
        far_get((uint8_t *)&flags, CPXE_SLOT(i) + CPXE_HDR + CPXH_FLAGS, 2);
        if (flags & (CPXF_BOOTINIT | CPXF_RESIDENT | CPXF_SETONLY))
            sh_ldcpx(i);
    }
}

static void sh_accs(void)
{
    char  names[NUM_PROCS - 1][ACC_NAMELEN];
    char  cio[CIO_NAME_MAX + 1], line[ACC_DIRLINE + 8], fname[ACC_NAMELEN];
    WORD  n = 0, i;
    int16_t fd;

    sh_cioname("*.*", cio);
    fd = cio_open(cio, CIO_A_DIR, 0);
    if (fd < 0)
        return;
    /* THE WHOLE DIRECTORY, not the first six.  One past the slots used to
     * stop the read, so a seventh accessory was never even seen -- left
     * out with nothing said, and the person who copied it in left to
     * wonder why it is not in the Desk menu.  Now it is counted with the
     * ones that had no room, and sh_main says so (phase 103). */
    for (;;) {
        uint16_t got = 0;
        uint8_t  st = cio_getrec(fd, line, sizeof line, &got);

        /* CIO answers 1 for a record and 3 for the last one, not 0 --
         * the selector's own test (fs_active), and getting it backwards
         * is a directory that reads as empty. */
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        if ((dos_dirline(line, got, fname, 0) & DOS_ENT_KIND) == DOS_ENT_FILE
            && dos_wildcmp("*." ACC_EXT, fname)) {
            if (n < NUM_PROCS - 1)
                strcpy(names[n++], fname);
            else
                sh_accfull++;               /* past the six slots */
        }
        if (st == CIO_OK_EOF)
            break;
    }
    cio_close(fd);

    for (i = 0; i < n; i++)
        if (!sh_ldacc(names[i]))
            sh_accfull++;
}

/* The desktop's file, read once and kept.  The far heap above the
 * shell's own buffers belongs to whichever program is running and is
 * wound back when it exits (app_free), so the desktop's bytes are taken
 * before the first program and stay for every return to it: a loaded
 * desktop costs a copy, not a disk read. */
static uint32_t sh_desk_blob, sh_desk_len;

/* KEPT, AND PURGEABLE (phase 120).  The file above is worth keeping only
 * while nothing else wants the room, and it can always be read again: so
 * it is purge level 1, the last to go (src/sys/farmem.h), and when it has
 * gone the next return to the desktop reads it from the disk and keeps it
 * again.  The system's, whoever is running when it is read. */
static WORD sh_desk_cache(void)
{
    char cio[CIO_NAME_MAX + 1];
    uint8_t keep = far_owner, keept = far_tag;
    WORD rs;

    if (sh_desk_blob)
        return APP_OK;
    sh_cioname(SH_DESKNAME, cio);
    far_owner = 0;
    far_tag = 0;
    rs = far_read_file(cio, &sh_desk_blob, &sh_desk_len);
    far_owner = keep;
    far_tag = keept;
    if (rs != APP_OK)
        sh_desk_blob = 0;
    else
        far_set_purge(sh_desk_blob, 1);
    return rs;
}

/* THE DESKTOP, DORMANT (phase 121).  When the desktop ends to run a
 * program, its image -- code and variables, unpacked and relocated -- is
 * kept at purge level 1 instead of freed (src/sys/app.c app_keep), and
 * when the program ends the desktop is run again from it (app_revive):
 * no unpacking, no relocating, no reading.  Its record is here, in zwin
 * rather than a block of far memory, so that no gate's model of the heap
 * has one more block to place.  sh_dorm is 0 when there is nothing kept,
 * or when what was kept has been purged. */
ZWIN static APP  sh_dorm_app;
ZWIN static uint32_t sh_dorm_near;      /* its near region, saved */
ZWIN static uint8_t sh_dorm;
ZWIN uint16_t sh_revived;               /* desktops run from a kept image */

/* far_purge_hook: whatever the shell and the AES kept that has just been
 * purged is forgotten, since its address may be given out again. */
static void sh_purged(uint32_t addr)
{
    if (addr == sh_desk_blob)
        sh_desk_blob = 0;
    if (sh_dorm && (addr == sh_dorm_app.far_addr || addr == sh_dorm_near
                    || (sh_dorm_app.vars_addr && addr == sh_dorm_app.vars_addr)))
        sh_dorm = 0;                    /* a level is purged whole: all go */
    rs_cache_purged(addr);
}

/* The kept desktop made runnable again, if there is one: APP_OK and *app
 * ready, or not, and then nothing is kept any more. */
static WORD sh_revive(APP *app)
{
    WORD st;

    if (!sh_dorm)
        return APP_E_FILE;
    sh_dorm = 0;
    *app = sh_dorm_app;
    st = app_revive(app, sh_dorm_near);
    if (st != APP_OK)
        app_forget(&sh_dorm_app, sh_dorm_near);
    else
        sh_revived++;
    return st;
}

WORD sh_runs;                   /* programs started, the desktop included */
/* RUN A PROGRAM IN A CONTEXT OF ITS OWN (switcher step 1,
 * docs/switcher-plan.md).  It used to be called from here, nested: the
 * shell's frames -- sh_main, sh_ldapp, app_exec -- under the program's
 * for as long as it ran, which is what a switcher cannot have, since a
 * second program could not then start without unwinding the first.
 *
 * Process 0's context is whoever is running as process 0, because rlr IS
 * ctx_cur; the shell and the program take turns in it.  So the shell's
 * bookkeeping moves to proc_shell (proc.h), which becomes ctx_root, the
 * place a finished context returns to; the program gets process 0's
 * context made new, in the park buffer proc_shell was keeping; and the
 * switch parks the shell's frames and starts the program at the top of
 * the engine stack.  When the program returns ctx_boot switches to
 * ctx_root, and everything is put back the other way.
 *
 * Between the two assignments to ctx_cur and their switch, rlr is not a
 * process: nothing here may call the AES there.
 *
 * What app_exec did around app_run -- the owner and the stack's floor --
 * is the context's now, which ctx_park applies at the switch.  Programs
 * started anywhere else (AUTO, the modules, Pexec) are app_exec's still:
 * they run in whatever context runs them. */
static WORD sh_run(const APP *app, uint32_t resume)
{
    CTX *pc = &proc_app->p_ctx, *sc = proc_shell;
    uint32_t spare = sc->save, give = 0;
    WORD r;

    memcpy(sc, pc, sizeof *sc);         /* the shell, as it runs */
    ctx_cur = ctx_root = sc;
    if (resume) {
        /* PUT ASIDE BEFORE: its context as it was parked, in the park
         * buffer it kept; the spare is not needed and goes back */
        far_get((uint8_t *)pc, resume + SU_CTX, sizeof *pc);
        far_free(resume);
        give = spare;
    } else {
        pc->save = spare;
        ctx_reset(pc, app->entry);
        pc->owner = app->owner;
        pc->floor = app->stack_floor ? app->stack_floor
                                     : (uint16_t)(app->near_base + CTX_FLOOR);
    }
    ctx_switch(pc);                     /* back when it has ended, or has
                                         * been put aside (sh_suspend) */
    if (sh_parked) {
        far_put(sh_left + SU_APP, (const uint8_t *)app, sizeof *app);
        far_put(sh_left + SU_CTX, (const uint8_t *)pc, sizeof *pc);
        far_get((uint8_t *)&spare, sh_left + SU_PARK, 4);
        r = 0;
    } else {
        r = (WORD)pc->entry;            /* main()'s, ctx_boot */
        spare = pc->save;
    }
    memcpy(pc, sc, sizeof *pc);         /* and the shell is process 0 again */
    sc->save = spare;
    ctx_cur = ctx_root = pc;
    if (give)
        far_free(give);
    if (sh_parked)
        proc_fresh(proc_app);           /* for whatever runs next */
    return r;
}

/* A program put aside (record `rec`), put back -- all but its context,
 * which sh_run takes: its bank-$00 blocks first, where they were -- if
 * one's place is taken nothing else is touched and it stays put aside --
 * then its record, its queue, its directories, its workstations, its
 * menu bar and its windows.  APP_OK, with *app its APP again; or
 * APP_E_POOL. */
static int16_t sh_unpark(APP *app, uint32_t rec)
{
    uint32_t p, tree;
    uint16_t nb, i, at, len;
    uint8_t tag, own, keep = far_owner, keept = far_tag;
    WORD max;

    far_get((uint8_t *)app, rec + SU_APP, sizeof *app);
    own = (uint8_t)app->owner;
    far_get((uint8_t *)&p, rec + SU_POOL, 4);
    far_get((uint8_t *)&nb, p, 2);
    p += 2;
    for (i = 0; i < nb; i++) {
        far_get((uint8_t *)&at, p, 2);
        far_get((uint8_t *)&len, p + 2, 2);
        far_get(&tag, p + 4, 1);
        far_owner = own;
        far_tag = tag;
        if (!pool_claim(at, len)) {
            far_owner = keep;
            far_tag = keept;
            pool_free_owner(own);       /* the ones claimed so far */
            return APP_E_POOL;
        }
        far_get((uint8_t *)at, p + 6, len);
        p += 6 + len;
    }
    far_owner = keep;
    far_tag = keept;
    far_get((uint8_t *)proc_app + sizeof(CTX), rec + SU_PROC,
            (uint16_t)(sizeof(PROC) - sizeof(CTX)));
    far_get((uint8_t *)gl_appqueue(&max), rec + SU_QUEUE, NUM_MSGS * 16);
    gemdos_dirload(rec + SU_DIR);
    vdi_retag_virtuals(SH_SUSPMARK(own), &proc_app->p_ctx);
    far_get((uint8_t *)&mn_apptitle, rec + SU_TPTR, 4);  /* its own memory
                                                          * again: mn_init
                                                          * forgot it */
    far_get((uint8_t *)&tree, rec + SU_MENU, 4);
    if (tree)
        mn_bar((OBJECT FAR *)tree, TRUE);
    wm_restore(rec + SU_WIN);
    app_near = app->near_base;
    app_far = app->far_addr;
    app_vars = app->vars_addr;
    app_vlink = app->vars_link;
    return APP_OK;
}

/* The desktop's Quit, with programs aside (phase 131): every one of them
 * asked to end, one at a time -- or, if one cannot be asked, none of them
 * and the desktop back, with the alert that says so (APP_E_LOADED). */
static WORD sh_closenext(void);

static WORD sh_quitround(void)
{
    WORD n = ring_n(), i;

    for (i = 0; i < n; i++)
        if (!sh_takes_apterm(ring_at(i))) {
            sh_goto(SH_DESKREC);
            return APP_E_LOADED;
        }
    sh_closing = 1;
    sh_closenext();
    return 0;
}

/* The next program aside, resumed with AP_TERM waiting -- or, when none
 * is left, GEM ends, as the Quit asked. */
static WORD sh_closenext(void)
{
    WORD n = ring_n(), i;
    uint32_t e;

    for (i = 0; i < n; i++) {
        e = ring_at(i);
        if (e != SH_DESKREC) {
            sh_term = 1;
            sh_goto(e);
            return 1;
        }
    }
    sh_closing = 0;
    sh_doexec = 4;
    return 0;
}

/* THE DESKTOP COULD NOT BE LOADED, and programs are aside (phase 132):
 * not the end of GEM, which would leave them as they are, but one of them
 * resumed in its place, with the alert that says why.  The one just put
 * aside joins the ring first -- the desktop's ring_turn never ran -- and
 * is the one chosen; otherwise the ring's first program.  Once: if that
 * fails too, the next failure of the desktop ends GEM (sh_nodesk). */
static WORD sh_nodeskgo(void)
{
    WORD n, i;
    uint32_t e = sh_left;

    sh_nodesk = 1;
    if (e && e != SH_DESKREC) {
        ring_turn(-1);                  /* sh_left into the ring, in front */
    } else {
        e = 0;
        n = ring_n();
        for (i = 0; i < n && !e; i++)
            if (ring_at(i) != SH_DESKREC)
                e = ring_at(i);
        if (!e) {
            sh_doexec = 4;
            return APP_E_NODESK;
        }
    }
    sh_goto(e);
    return APP_E_NODESK;
}

/* ---- plain Atari programs (phase 162, docs/run8-plan.md) ---------------
 *
 * A program in the Atari's own binary format loads where it was built to,
 * $2000 or so -- over gem4xe -- so it cannot run beside GEM.  GEM ends
 * instead, as Quit ends it, and leaves the DOS a note: run this, then
 * GEM again (src/sys/runnote.h).  G4DOS's shell reads it.
 *
 * WHICH FILES.  The names the desktop gives a plain program's icon --
 * .COM, .XEX, .EXE, .OBJ, which no GEM program carries -- and then the
 * Atari's own mark, $FF $FF, as the file's first two bytes.  Only those
 * names are opened to look, so a GEM program costs nothing more; and a
 * file of those names without the mark goes on to the G4A loader, which
 * refuses it as it refused it before. */
static const char FAR sh_plainx[] = "COMXEXEXEOBJ";

static WORD sh_isplain(const char *cmd)
{
    char cio[CIO_NAME_MAX + 1];
    uint8_t two[2];
    uint16_t got = 0;
    int16_t io;
    WORD i, e = -1;

    for (i = 0; cmd[i]; i++)
        if (cmd[i] == '.')
            e = i + 1;
        else if (cmd[i] == '\\' || cmd[i] == ':')
            e = -1;
    if (e < 0 || i - e != 3)
        return 0;
    for (i = 0; sh_plainx[i]; i += 3)
        if ((cmd[e] & 0xDF) == sh_plainx[i]
            && (cmd[e + 1] & 0xDF) == sh_plainx[i + 1]
            && (cmd[e + 2] & 0xDF) == sh_plainx[i + 2])
            break;
    if (!sh_plainx[i])
        return 0;
    dos_cioname(cmd, cio);
    io = cio_open(cio, CIO_A_READ, 0);
    if (io < 0)
        return 0;
    (void)cio_read(io, two, 2, &got);
    cio_close(io);
    return (WORD)(got == 2 && two[0] == 0xFF && two[1] == 0xFF);
}

/* GEM ends, with the note for the program at `cmd` -- written in the
 * shell's form, A:\X becoming D1:\X -- or the reason it cannot: a program
 * put aside, which GEM's ending would lose without asking it, or a DOS
 * with no way back yet (that load fails as it did before: not a G4A). */
static WORD sh_plain(const char *cmd)
{
    WORD n = ring_n(), i, k = 0;

    for (i = 0; i < n; i++)
        if (ring_at(i) != SH_DESKREC)
            return APP_E_PLAIN;
    if (dos.kind != DOS_G4DOS)
        return APP_E_MAGIC;
    i = 0;
    if (cmd[0] && cmd[1] == ':' && cmd[2] == '\\') {
        NOTE[NOTE_PATH] = 'D';
        NOTE[NOTE_PATH + 1] = (uint8_t)('1' + ((cmd[0] | 0x20) - 'a'));
        NOTE[NOTE_PATH + 2] = ':';
        k = 3;
        i = 2;
    }
    for (; cmd[i]; i++, k++) {
        if (k >= NOTE_ROOM - 1)
            return APP_E_FILE;
        NOTE[NOTE_PATH + k] = (uint8_t)cmd[i];
    }
    NOTE[NOTE_PATH + k] = 0;
    NOTE[0] = 'R';
    NOTE[1] = 'Q';
    NOTE[NOTE_STEP] = NOTE_RUN;
    NOTE[NOTE_LEN - 1] = note_sum();
    sh_doexec = 4;                      /* the loop ends, and GEM with it */
    return APP_OK;
}

WORD sh_lastret;                /* what the last one's main() returned */
WORD sh_lastrc;                 /* the last load's status (APP_*) */

/* The desktop or the requested program: loaded, run, freed.  The load
 * status, which sh_main reports to the user before the next iteration;
 * and after a program the desktop is what runs next unless the program
 * asked otherwise -- the donor's rule, set before the program runs so
 * that its own shel_write wins. */
static WORD sh_ldapp(void)
{
    APP app;
    char cmd[SH_CMDLEN];
    WORD st, was = sh_next, k = -1, quit = 0;
    uint8_t stops;
    uint32_t resume = 0;

    if (was == SH_DESKTOP) {
        /* The last program ran in its own directory (the desktop's
         * do_aopen set it, src/desk/deskwin.c); the desktop's files are
         * in the system's, and its DESKTOP.RSC is a bare name -- unless
         * shel_wdef named another, which is what its directory is for.
         *
         * `cmd` TWICE, and not a buffer of its own: this frame was on
         * the engine's stack for as long as the program ran, and GEMDOS
         * refuses a Pexec with less than GD_PEXEC_STACK of that stack
         * left, because a child's calls are served below the parent's on
         * it (src/gem4xe.scm).  A 114-byte second buffer here answered
         * ENSMEM to every Pexec in test-m32 -- including one for a file
         * that is not there, which is the guard firing before it looks.
         * Since phase 126 the frame is PARKED while the program runs
         * (sh_run), so that reason has gone; the one buffer does no harm
         * and stays. */
        gemdos_home();
        far_strget(cmd, sh_cdir_far, SH_CDIRLEN);
        if (cmd[0])
            gemdos_chdir(cmd);
        /* The CACHED image only while the name is still the default one:
         * far memory holds one desktop, read before the keep mark, and a
         * program that asked for another gets it from the file. */
        far_strget(cmd, sh_desk_far, SH_DESKLEN);
        app_kind = OWN_DESK;
        if (!strcmp(cmd, SH_DESKNAME) && sh_revive(&app) == APP_OK) {
            app_kind = 0;               /* nothing was loaded to use it */
            st = APP_OK;
        } else if (!strcmp(cmd, SH_DESKNAME) && sh_desk_cache() == APP_OK) {
            far_set_purge(sh_desk_blob, 0);     /* not while it is read */
            st = app_load((const uint8_t FAR *)sh_desk_blob, sh_desk_len, &app);
            far_set_purge(sh_desk_blob, 1);
        } else {
            st = app_load_file(cmd, &app);
        }
    } else {
        far_strget(cmd, sh_cmd_far, SH_CMDLEN);
        sh_next = SH_DESKTOP;
        sh_isgem = 1;
        if (sh_isplain(cmd)) {          /* GEM ends to run it (above) */
            sh_lastrc = sh_plain(cmd);
            return sh_lastrc;
        }
        k = ring_find(cmd);
        if (k >= 0) {
            /* started again: resumed where it was put aside -- or not, if
             * its bank-$00 memory has been taken meanwhile (by a module
             * or a resource loaded at run time), and it stays aside */
            resume = ring_at(k);
            st = sh_unpark(&app, resume);
            if (st != APP_OK) {
                resume = 0;
                st = APP_E_TAKEN;
            }
        } else if (sh_left && ring_n() >= SH_PROGS) {
            st = APP_E_MANY;            /* SH_PROGS loaded already */
        } else {
            st = app_load_file(cmd, &app);
        }
    }
    sh_lastrc = st;
    if (st != APP_OK) {
        /* what ran last is still in sh_left, for whatever runs instead;
         * nothing is to be asked to end, nor a Quit's round go on */
        sh_term = 0;
        sh_closing = 0;
        if (was == SH_DESKTOP && ring_n() && !sh_nodesk)
            return sh_nodeskgo();
        if (was == SH_DESKTOP)      /* nothing to return to: the loop ends */
            sh_doexec = 4;
        return st;
    }
    sh_nodesk = 0;
    /* The ring turns: this one out, the last one in (ring_turn).  The
     * desktop's entry is wherever the turns have put it -- and absent at
     * boot, or when the desktop runs again because what it started did
     * not load, which is the one case where it is sh_left itself. */
    if (was == SH_DESKTOP) {
        WORD n = ring_n(), i;

        for (i = 0; i < n && ring_at(i) != SH_DESKREC; i++)
            ;
        if (i < n)
            k = i;
        if (sh_left == SH_DESKREC)
            sh_left = 0;
    }
    ring_turn(k);
    /* What appl_find will search, and it is the APPLICATION's record by
     * definition -- an application is process 0 (proc.h).  Named after
     * the load rather than before it, so that a failure leaves the name
     * of whatever is actually there instead of one for a program that
     * never started. */
    proc_name(proc_app, cmd);   /* the desktop's name is in cmd too now */
    if (!resume)
        proc_app->p_msgs = 0;   /* registers for itself, or does not */
    sh_deskrun = (was == SH_DESKTOP);
    sh_runown = (uint8_t)app.owner;
    if (sh_term) {                  /* resumed to be asked to end (sh_close,
                                     * sh_closenext): the message waits */
        sh_term = 0;
        ap_sendmsg(proc_app, AP_TERM, 0, 0, AP_TERM, 0, 0);
    }
    sh_runs++;
    sh_doexec = -1;                 /* what the program asks for */
    stops = gem_stack_stops;
    sh_lastret = sh_run(&app, resume);
    sh_deskrun = 0;
    if (sh_parked) {
        /* PUT ASIDE, not ended (sh_suspend): nothing of it is freed, and
         * what runs next is what sh_goto chose -- the desktop, or the
         * ring's next.  The accessories close their windows, as they do
         * between programs: the loop's wm_init is about to empty the
         * table. */
        sh_parked = 0;
        proc_input = proc_app;
        mn_cleanup();
        proc_drain(ACC_ROUNDS);
        return 0;
    }

    /* The program has gone.  The mouse comes back here whatever it left
     * it set to, and every accessory is told -- before app_free takes the
     * memory back and before the loop's wm_init destroys the windows,
     * because an accessory that has taken anything while this program was
     * alive has to be given the chance to give it back.  Then it is given
     * the TURNS to do that in: the donor blocks appl_exit until every
     * accessory has read the message, and proc_drain is that barrier. */
    sh_left = 0;                /* ended: it leaves the ring nothing... */
    if (was == SH_DESKTOP)
        sh_left = SH_DESKREC;   /* ...but the desktop is always there */
    proc_input = proc_app;
    mn_cleanup();
    sh_appgone();               /* SHUT_COMPLETED, if one waited on it */
    proc_drain(ACC_ROUNDS);
    /* THE DESKTOP'S QUIT WITH PROGRAMS ASIDE (phase 131): not the end of
     * GEM until each of them has been asked and has gone -- and the
     * desktop kept dormant meanwhile, since sh_goto asks for a program.
     * And a program that ended during that round: the next one. */
    if (was == SH_DESKTOP && sh_doexec == -1 && ring_n())
        quit = sh_quitround();
    else if (was != SH_DESKTOP && sh_closing)
        sh_closenext();
    /* The default desktop, ending to run a program it will come back
     * from: kept, dormant (sh_revive above).  Anything else is freed. */
    if (was == SH_DESKTOP && sh_doexec == 1 && !strcmp(cmd, SH_DESKNAME)
        && app_keep(&app, &sh_dorm_near)) {
        sh_dorm_app = app;
        sh_dorm = 1;
    } else {
        app_free(&app);
    }
    /* A desktop that returns without asking for anything has nothing
     * left to do: that is a shutdown, not the desktop again forever. */
    if (was == SH_DESKTOP && sh_doexec == -1)
        sh_doexec = 4;
    /* stopped for its stack (src/sys/abi.c): the loop says so, on the
     * bare desk, before whatever runs next */
    if (gem_stack_stops != stops)
        return APP_E_STACK;
    return quit;
}

/* The donor's sh_main: until a shutdown, reset the windows and the menu,
 * clear the screen, report the last failure, run the next thing.  The
 * one departure is what a load failure of the desktop itself means:
 * the donor has a ROM desktop that cannot fail to load, and here it is
 * a file, so the loop ends and the caller hears which way (a negative
 * APP_* status); otherwise the count of programs run. */
WORD sh_main(void)
{
    WORD rc = 0;

    if (!sh_cmd_far)
        return APP_E_POOL;
    far_purge_hook = sh_purged;
    {
        WORD rs = sh_desk_cache();
        if (rs != APP_OK) {
            sh_lastrc = rs;             /* the desktop's own load, too */
            return rs;
        }
    }
    /* AUTO FIRST, then the accessories, which is TOS's order -- an AUTO
     * program is meant to be able to set up something an accessory then
     * finds.  Both are before the keep mark below, so a program that
     * ended with Ptermres is as permanent as an accessory is. */
    /* AUTO, THEN THE MODULES, THEN THE ACCESSORIES -- and that order is
     * load-bearing rather than tidy.  A control panel extension may want
     * its settings applied at BOOT (CPX_BOOTINIT, src/app/cpx.h), and it
     * is the PANEL that does that, because the panel is the host and
     * already knows the shape of both parameter blocks; the AES would
     * have to learn them to do it here, in a second place where they
     * could drift.  So the modules have to EXIST by the time CONTROL.ACC
     * starts: an accessory runs its main() at load and parks at its
     * first evnt_ call, which is after it has had the chance.
     *
     * All three are before the keep mark below, so everything any of
     * them took is permanent. */
    sh_auto();
    sh_cpx();                   /* ...so the panel can boot-init them */
    sh_accs();
    sh_cpxdropall();            /* ...and then they go, until opened */
    /* The AUTO programs and the modules ran in the application's record
     * (they are programs, run through app_run), so their calls were
     * counted as the application's.  They are not the desktop's: start
     * its count here, or a gate asking which call the desktop is in is
     * a module's four calls out for every .CPX (phase 102). */
    app_calls = 0;

    /* EVERYTHING TAKEN SO FAR IS PERMANENT, and from here the machine
     * keeps that rather than this file arranging it.  Above this mark is
     * a program's: its near region, its resource, its far image, and
     * whatever it asks GEMDOS for -- and a program's exit winds both
     * allocators back to here and no further.  Below it are the shell's
     * buffers, the selector's names, the desktop's cached image, the
     * process records and every accessory with its queue, its resource
     * and its context.  A release that would cross it is refused and
     * counted (src/sys/app.c), which is the difference between a rule and
     * a comment: an accessory loaded a moment too late used to be freed
     * by the first program to exit, in silence. */
    pool_keep_mark();                   /* the far heap needs no floor: what
                                         * was taken so far belongs to the
                                         * system or to a program nothing
                                         * will free (phase 79) */
    sh_runs = 0;
    sh_lastret = 0;
    sh_lastrc = 0;
    sh_next = SH_DESKTOP;
    sh_isgem = 1;
    sh_doexec = 0;
    do {
        wm_init();
        mn_init();
        ratinit();                          /* the pointer on, as the donor */
        /* ...and the ARROW, which the donor does not do here because it
         * does not have to: a form belongs to a PROCESS there, and
         * set_mown gives the mouse's new owner its own form back
         * (geminput.c).  gem4xe runs one process, so the form is one
         * global and the shell is the only thing between two programs
         * that can put it right.  Without this the desktop's hourglass
         * -- desk_busy(TRUE), set just before shel_write and deliberately
         * never cleared, because the donor's desktop is about to stop
         * owning the mouse -- stays over the program it started, for as
         * long as that program runs. */
        gr_mouse(ARROW, 0);
        gsx_sclip(&gl_rscreen);
        ob_draw(gl_wtree, ROOT, 0);         /* the desk, edge to edge */
        if (rc)
            fm_alert(1, rc == APP_E_FILE   ? lang_str(LS_APPNOTFOUND)
                      : rc == APP_E_OLDSDK ? lang_str(LS_APPOLDSDK)
                      : rc == APP_E_STACK  ? lang_str(LS_APPSTACK)
                      : rc == APP_E_LOADED ? lang_str(LS_QUITLOADED)
                      : rc == APP_E_MANY   ? lang_str(LS_TOOMANY)
                      : rc == APP_E_TAKEN  ? lang_str(LS_NORESUME)
                      : rc == APP_E_NODESK ? lang_str(LS_NODESK)
                      : rc == APP_E_PLAIN  ? lang_str(LS_PLAINASIDE)
                      :                      lang_str(LS_APPNOTLOAD));
        /* ...and before the first desktop, an accessory that was found
         * and not loaded: past the six slots, or no room in the pool.
         * TOS leaves it out silently; this says so once, at boot, on the
         * bare desk (phase 103). */
        else if (!sh_runs && sh_accfull)
            fm_alert(1, lang_str(LS_ACCFULL));
        rc = sh_ldapp();
    } while (sh_doexec != 4);
    return rc ? rc : sh_runs;
}
