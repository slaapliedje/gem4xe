/* shel.c -- the shell library: shel_read, shel_write, shel_get, shel_put,
 * shel_find, shel_envrn, and the shell loop that runs the desktop and
 * the programs it asks for.  EmuTOS aes/gemshlib.c.
 *
 * What the donor's shell library keeps -- the command and tail the next
 * application starts with, the environment, and the 4 KB the desktop
 * parks its state in between programs -- is nothing the AES reads itself;
 * it is memory it lends the applications, across their lifetimes.  So it
 * lives in far memory, taken from the far allocator ONCE, at AES start-up
 * and before any application is loaded: far_alloc is a bump allocator that
 * app_free winds back to where app_load found it, and anything taken
 * after an application would go with it.  The environment is the one
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
#include "sys/gemdos.h"
#include "sys/farmem.h"
#include "sys/ctx.h"
#include "aes/proc.h"
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
 * copy, not a disk read), so a name that is still DESKTOP.G4A comes out
 * of the cache and any other is loaded from the file like a program.
 * That costs a disk read per return to the desktop for a caller that
 * changed it, which is the right way round. */
#define SH_DESKNAME "DESKTOP.G4A"   /* what the shell runs unless told */
#define SH_DESKLEN  13          /* LEN_ZFNAME: NAME.EXT and its NUL */
#define SH_CDIRLEN  114         /* LEN_ZPATH: a path with its drive */
static uint32_t sh_desk_far, sh_cdir_far;

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
    sh_cdir_far = far_alloc(SH_CDIRLEN);
    if (sh_desk_far)
        far_strput(sh_desk_far, SH_DESKNAME, SH_DESKLEN);
    if (sh_cdir_far)
        far_write8(sh_cdir_far, 0);     /* empty: the system's directory */
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
    case 4:                                 /* SHW_SHUTDOWN */
        sh_doexec = doex;
        sh_isgem = 0;
        break;
    case 5:                                 /* SHW_RESCHNG: one resolution */
        far_write8(sh_cmd_far, 0);
        far_write8(sh_tail_far, 0);
        break;
    default:
        break;
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
 * BEFORE THE FIRST PROGRAM, because both allocators are bump allocators
 * that app_free winds back to where app_load found them (src/sys/app.h:
 * "applications are released in the reverse order of their loading").
 * An accessory taken BEFORE the desktop is below the desktop's mark, so
 * every return to the desktop leaves it standing; one taken after would
 * be freed underneath itself the first time a program exited.  The same
 * rule reaches into the accessory: everything it will ever want from
 * bank $00 -- its resource included -- it must take while it is starting
 * up, which is what the donor tells an accessory writer for a different
 * reason (a DA's memory is not freed on a resolution change, so it is
 * told to embed its resource rather than load one).
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
    if (app_load_file(name, &app) != APP_OK || !ctx_make(&p->p_ctx, app.entry)) {
        proc_drop(p);
        return FALSE;
    }
    proc_name(p, name);                 /* what appl_find will search */
    ctx_switch(&p->p_ctx);              /* runs until it parks */
    p->p_stat = P_LIVE;                 /* it has had its first turn */
    sh_naccs++;
    return TRUE;
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
    while (n < NUM_PROCS - 1) {
        uint16_t got = 0;
        uint8_t  st = cio_getrec(fd, line, sizeof line, &got);

        /* CIO answers 1 for a record and 3 for the last one, not 0 --
         * the selector's own test (fs_active), and getting it backwards
         * is a directory that reads as empty. */
        if (st != CIO_OK && st != CIO_OK_EOF)
            break;
        if ((dos_dirline(line, got, fname, 0) & DOS_ENT_KIND) == DOS_ENT_FILE
            && dos_wildcmp("*." ACC_EXT, fname)) {
            strcpy(names[n], fname);
            n++;
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

WORD sh_runs;                   /* programs started, the desktop included */
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
    WORD st, was = sh_next;

    if (was == SH_DESKTOP) {
        /* The last program ran in its own directory (the desktop's
         * do_aopen set it, src/desk/deskwin.c); the desktop's files are
         * in the system's, and its DESKTOP.RSC is a bare name -- unless
         * shel_wdef named another, which is what its directory is for.
         *
         * `cmd` TWICE, and not a buffer of its own: THIS FRAME IS ON THE
         * ENGINE'S STACK FOR AS LONG AS THE PROGRAM RUNS, and GEMDOS
         * refuses a Pexec with less than GD_PEXEC_STACK of that stack
         * left, because a child's calls are served below the parent's on
         * it (src/gem4xe.scm).  A 114-byte second buffer here answered
         * ENSMEM to every Pexec in test-m32 -- including one for a file
         * that is not there, which is the guard firing before it looks. */
        gemdos_home();
        far_strget(cmd, sh_cdir_far, SH_CDIRLEN);
        if (cmd[0])
            gemdos_chdir(cmd);
        /* The CACHED image only while the name is still the default one:
         * far memory holds one desktop, read before the keep mark, and a
         * program that asked for another gets it from the file. */
        far_strget(cmd, sh_desk_far, SH_DESKLEN);
        if (sh_desk_blob && !strcmp(cmd, SH_DESKNAME))
            st = app_load((const uint8_t FAR *)sh_desk_blob, sh_desk_len, &app);
        else
            st = app_load_file(cmd, &app);
    } else {
        far_strget(cmd, sh_cmd_far, SH_CMDLEN);
        sh_next = SH_DESKTOP;
        sh_isgem = 1;
        st = app_load_file(cmd, &app);
    }
    sh_lastrc = st;
    if (st != APP_OK) {
        if (was == SH_DESKTOP)      /* nothing to return to: the loop ends */
            sh_doexec = 4;
        return st;
    }
    /* What appl_find will search, and it is the APPLICATION's record by
     * definition -- an application is process 0 (proc.h).  Named after
     * the load rather than before it, so that a failure leaves the name
     * of whatever is actually there instead of one for a program that
     * never started. */
    proc_name(proc_app, cmd);   /* the desktop's name is in cmd too now */
    sh_runs++;
    sh_doexec = -1;                 /* what the program asks for */
    sh_lastret = app_exec(&app);

    /* The program has gone.  The mouse comes back here whatever it left
     * it set to, and every accessory is told -- before app_free takes the
     * memory back and before the loop's wm_init destroys the windows,
     * because an accessory that has taken anything while this program was
     * alive has to be given the chance to give it back.  Then it is given
     * the TURNS to do that in: the donor blocks appl_exit until every
     * accessory has read the message, and proc_drain is that barrier. */
    proc_input = proc_app;
    mn_cleanup();
    proc_drain(ACC_ROUNDS);
    app_free(&app);
    /* A desktop that returns without asking for anything has nothing
     * left to do: that is a shutdown, not the desktop again forever. */
    if (was == SH_DESKTOP && sh_doexec == -1)
        sh_doexec = 4;
    return 0;
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
    if (!sh_desk_blob) {
        char cio[CIO_NAME_MAX + 1];
        WORD rs;
        sh_cioname(SH_DESKNAME, cio);
        rs = far_read_file(cio, &sh_desk_blob, &sh_desk_len);
        if (rs != APP_OK) {
            sh_lastrc = rs;             /* the desktop's own load, too */
            return rs;
        }
    }
    sh_accs();                  /* before the first program: see above */

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
    pool_keep_mark();
    far_keep_mark();
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
                      :                      lang_str(LS_APPNOTLOAD));
        rc = sh_ldapp();
    } while (sh_doexec != 4);
    return rc ? rc : sh_runs;
}
