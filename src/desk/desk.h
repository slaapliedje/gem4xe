/* desk.h -- the GEM Desktop's own declarations.
 *
 * The desktop is a gem4xe application (src/app/gem.h) in the donor's
 * shape (EmuTOS desk/): one screen tree that the AES draws as the desk
 * under every window -- ROOT, DROOT the desk itself, then a box per
 * window and then the item objects, icons on the desk or in a window --
 * and a struct of globals, G, as the donor's deskglob.h has.  The
 * resource is DESKTOP.RSC, built on the host by tools/deskrsc.py, whose
 * indices come in through build/deskrsc.h.
 *
 * A folder window is the donor's WNODE: the AES window, its box in the
 * screen tree, the view (which rows of the item grid are shown), and a
 * PNODE, the directory listed -- its search spec and its FNODEs, one per
 * entry read through Fsfirst/Fsnext.  The FNODEs live in far memory,
 * an arena Malloc'd once at start (Mfree is a no-op, src/sys/gemdos.c),
 * because a window's worth of them is more than the near data allows;
 * the AES reads nothing there.  What it does read -- the name and the
 * information lines, the labels behind ib_ptext -- stays in bank $00.
 */
#ifndef GEM4XE_DESK_H
#define GEM4XE_DESK_H

#include "portab.h"
#include "gem.h"
#include "deskrsc.h"

#define DESKWH      0                   /* the desktop's window handle */
#define DROOT       1                   /* the desk: ROOT's first child */
#define NUM_WNODES  4                   /* window objects, DROOT+1 on */
#define WOBS_START  (DROOT + 1 + NUM_WNODES)
#define NUM_ITEMS   16                  /* icons, on the desk and in windows */
#define NUM_SOBS    (WOBS_START + NUM_ITEMS)

#define MAX_DRIVES  8                   /* D1: to D8: */
#define MAX_ICONTEXT_WIDTH 12           /* an icon's label, in characters */
#define LABEL_LEN   (MAX_ICONTEXT_WIDTH + 1)
/* A text view's line: the places it may fill, and so the width the
 * highlight of a selected one covers (the donor's LEN_FNODE, 48).  The
 * resource's template is shorter than this, which is the room a
 * translation has to grow into (tools/deskrsc.py, STFLINE). */
#define LEN_FNODE   48
#define V_ICON      0                   /* the two views, in the donor's */
#define V_TEXT      1                   /* order (G.g_iview) */
/* The five orders a listing can be in, the donor's values: the View
 * menu's items less NAMEITEM, so the item and the order are the same
 * number (deskfpd.h).  NAME is by name alone; TYPE, SIZE and DATE each
 * fall back to the name; NSRT is the order the directory gave. */
#define S_NAME      0
#define S_TYPE      1
#define S_SIZE      2
#define S_DATE      3
#define S_NSRT      4
#define INF_E1_VIEWTEXT 0x80            /* the INF's environment bytes, the */
#define INF_E1_SORTMASK 0x60            /* donor's bits (deskapp.c): the    */
#define INF_E5_NOSORT   0x80            /* fifth carries "no sort", which   */
                                        /* will not fit in the first's two, */
#define INF_E5_NOSIZE   0x10            /* and "do not size to fit"         */

#define DESK_SPEC   0x00001143L         /* the desk: green, pattern 4 (the AES's own) */
#define WINDOW_SPEC 0x00001100L         /* a window's box: white, no pattern */
/* The two the "#Q" line keeps a pair for: this screen and the other
 * one.  Which is which comes from the depth appl_init reported --
 * global[10] -- so it needs no device seam of its own up here. */
#define N_SCREENS   2
#define SCR_COLOUR  0                   /* more than one plane: VBXE */
#define SCR_MONO    1                   /* one: the ANTIC fallback */
/* The pattern and colour fields of an ob_spec, and the rest of the word
 * -- the border and text colours -- which the chooser leaves alone. */
#define PATCOL_MASK 0x00FFL
#define MIN_WINT    4                   /* between icon cells */
#define MIN_HINT    2

#define WINDOW_STYLE (NAME | CLOSER | FULLER | MOVER | INFO | SIZER | \
                      UPARROW | DNARROW | VSLIDE | LFARROW | RTARROW | HSLIDE)

#define LEN_ZPATH   48                  /* "A:\DIR\*.*" and its NUL */
#define CPDATA_LEN  128                 /* the shell buffer's first bytes: the
                                         * donor keeps copy/paste data there,
                                         * and the INF text follows them */
#define INF_REV_LEVEL 2                 /* "#R 02": the donor's DESKTOP.INF */
#define INF_NAME    "DESKTOP.INF"       /* ...and what it is called on the
                                         * boot drive, once it is a file */
#define SH_TAILLEN  128                 /* a command tail, as shel_write copies it */
#define LEN_ZFNAME  14                  /* "FILENAME.EXT" and its NUL */
#define LEN_ZINFO   36                  /* " 1234567 bytes used in 12 items." */
#define NUM_FNODES  64                  /* a window lists this many at most */
/* What an operation is doing, in the walk and in the dialog's title.
 * OP_COUNT is the pass that says what the others will do. */
#define OP_COUNT   0
#define OP_DELETE  1
#define OP_COPY    2
#define OP_MOVE    3

/* A file is copied through this much far memory at a time (the arena).
 * GEMDOS takes a far buffer and shuttles it through a pool slice
 * (src/sys/gemdos.c, gd_xfer), so the desktop's near memory pays
 * nothing for it. */
#define COPY_BUF   1024

#define MAX_DELLEVEL 4                  /* folders inside folders a delete
                                         * walks: a DTA (and a search slot,
                                         * src/sys/gemdos.c) per level */
#define DISPATTR    FA_SUBDIR           /* what a window lists: folders too */
#define F_SELECTED  0x0001              /* f_flags */

/* One directory entry, as Fsfirst/Fsnext gave it: the DTA's fields
 * and the item object showing it, if it is in view.  In far memory. */
typedef struct {
    WORD  f_obid;                       /* 0: not in view */
    WORD  f_flags;                      /* F_SELECTED */
    WORD  f_seq;                        /* where the directory had it, which
                                         * is the order "No sort" restores */
    WORD  f_attr;                       /* FA_* */
    UWORD f_time, f_date;
    LONG  f_size;
    char  f_name[LEN_ZFNAME];
} FNODE;

/* A directory as a window lists it: the search spec and what it found,
 * folders first then by name, as the donor sorts by name (S_NAME). */
typedef struct {
    WORD  p_count;                      /* entries listed */
    LONG  p_size;                       /* their bytes together */
    char  p_spec[LEN_ZPATH];            /* "A:\SUB\*.*" */
    FNODE FAR *p_flist;               /* NUM_FNODES of them */
} PNODE;

/* A folder window.  The one at index k has the box DROOT+1+k in the
 * screen tree (w_root); the window on top is the box last in ROOT's
 * children, objc_order keeping the tree in stacking order. */
typedef struct {
    WORD  w_id;                         /* the AES's handle; 0 = free */
    WORD  w_root;                       /* its box in g_screen */
    WORD  w_cvrow, w_cvcol;             /* the first row and column shown */
    WORD  w_pncol, w_pnrow;             /* the grid the window shows */
    WORD  w_vnrow, w_vncol;             /* the grid the listing is laid on:
                                         * with size to fit the columns are
                                         * the window's, so w_vncol == w_pncol
                                         * and w_cvcol is 0; without it they
                                         * are g_icols and the window scrolls
                                         * sideways over them */
    PNODE w_path;
    char  w_name[LEN_ZPATH + 2];        /* " A:\SUB\*.* " */
    char  w_info[LEN_ZINFO];
} WNODE;

/* A window's place, kept between programs (the donor's WSAVE): the
 * desktop writes them into the shell buffer as "#W" lines of
 * DESKTOP.INF when it exits to run a program, and opens the windows
 * again from them when the shell loads it back.  In far memory. */
typedef struct {
    WORD x_save, y_save, w_save, h_save;
    WORD hsl_save, vsl_save;            /* the view: the row shown first */
    char pth_save[LEN_ZPATH];           /* "" for a free slot */
} WSAVE;

typedef struct {
    WSAVE cs_wnode[NUM_WNODES];
} CSAVE;

/* What an item object's ob_spec points at.  An icon's is its own
 * ICONBLK, a copy of the resource's with the label and the letter
 * filled in; a text view's is the line itself, a G_STRING.  The two
 * share the store because an item is one or the other and never both,
 * and because ob_spec is a NEAR pointer (src/aes/objc.c SPEC_PTR) --
 * the line cannot live out in far memory beside the FNODE it is made
 * from.  Both halves are 47 bytes; the union is 48. */
typedef union {
    struct {
        ICONBLK blk;
        char    label[LABEL_LEN];
    } i;
    char line[LEN_FNODE];
} SCREENINFO;

typedef struct {
    OBJECT  *a_menu;                    /* ADMENU */
    OBJECT  *a_info;                    /* ADDINFO */
    OBJECT  *a_mkdir;                   /* ADMKDBOX */
    OBJECT  *a_delete;                  /* ADDELDIA */
    OBJECT  *a_finfo;                   /* ADFINFO */
    ICONBLK *a_iblist;                  /* IB_HARD .. IB_DOCU */
    WORD     g_handle;                  /* the AES's VDI handle */
    WORD     g_wchar, g_hchar, g_wbox, g_hbox;
    GRECT    g_desk;                    /* the desk under the menu bar */
    WORD     g_wicon, g_hicon;          /* an icon's cell: image plus label */
    WORD     g_iview;                   /* V_ICON or V_TEXT */
    WORD     g_isort;                   /* S_NAME .. S_NSRT */
    WORD     g_ifit;                    /* size to fit: the columns follow
                                         * the window rather than the screen */
    WORD     g_iwext, g_ihext;          /* what an item of that view fills, */
    WORD     g_iwint, g_ihint;          /* and the space in front of it */
    const char *g_fline;                /* the text view's template, and the */
    const char *g_fmark;                /* three marks its first column takes,
                                         * both of the resource and fetched
                                         * once: a fetch per item would be
                                         * sixteen AES calls a redraw */
    WORD     g_icw, g_ich;              /* the grid the cells snap to */
    WORD     g_icols;                   /* the columns the WIDEST window this
                                         * screen can show would hold, which
                                         * is the grid a window that does not
                                         * size to fit is laid out on */
    WORD     g_screenfree;              /* the free chain's head */
    WORD     g_rmsg[8];                 /* evnt_multi's message */
    WORD     g_wcnt;                    /* windows open */
    LONG     g_nfiles, g_ndirs;         /* what a delete counted, then what
                                         * is left of it */
    LONG     g_opsize;                  /* ...and their bytes together, which
                                         * is what Show info calls a folder's
                                         * size */
    DTA FAR *g_dta;                   /* the listing's DTA, then the FNODEs */
    DTA FAR *g_opdta;                 /* MAX_DELLEVEL of them, one per level
                                         * of the walk: our GEMDOS keeps a
                                         * search's state by the DTA that owns
                                         * it, as the ST does */
    CSAVE FAR *g_cnxsave;             /* the windows' places between programs */
    char FAR *g_shelbuf;              /* the desktop's copy of the shell buffer */
    char FAR *g_copybuf;              /* COPY_BUF of it, for file copies */
    WNODE    g_wlist[NUM_WNODES];       /* by w_root - (DROOT + 1) */
    /* Set preferences...: the desk's and a window's pattern and colour,
     * ONE PAIR PER SCREEN, as the INF's "#Q" line carries them.  Per
     * screen because this binary drives two of them (test-m26) and a
     * choice made in sixteen colours must not follow the user onto the
     * mono one -- which is why the donor indexes its own three by
     * resolution (EmuTOS deskapp.c g_patcol).  A byte each: the pattern
     * and colour fields are both inside the low byte of an ob_spec, and
     * the rest of the word is the border and text colours, which this
     * dialog does not touch. */
    UWORD    g_patcol[N_SCREENS][2];    /* [screen][0] desk, [1] window */
    OBJECT     g_screen[NUM_SOBS];
    SCREENINFO g_screeninfo[NUM_ITEMS]; /* by obid - WOBS_START */
} GLOBES;

extern GLOBES G;

/* deskobj.c: the screen tree */
void obj_init(void);
WORD obj_walloc(WORD x, WORD y, WORD w, WORD h);
void obj_wfree(WORD obj, WORD x, WORD y, WORD w, WORD h);
WORD obj_ialloc(WORD wparent, WORD x, WORD y, WORD w, WORD h);
WORD obj_get_obid(WORD drive);
SCREENINFO *obj_info(WORD obj);
WORD obj_text(WORD wparent, WORD x, WORD y, WORD w, WORD h);
WORD obj_icon(WORD wparent, WORD x, WORD y, WORD which,
              const char FAR *label, WORD letter);

/* desktop.c */
void desk_busy(WORD on);

/* deskwin.c: folder windows */
void desk_view(WORD view);
void desk_sort(WORD sort);
void desk_fit(WORD fit);
/* The background the "Set preferences..." dialog chose: remembered for
 * THIS screen, and put on the desk and every window's box.  Call it with
 * the two low bytes; desk_patcol_apply() alone puts the remembered pair
 * back, which is what start-up and Read .INF file do. */
WORD desk_screen(void);                 /* SCR_COLOUR or SCR_MONO */
void desk_patcol(UWORD deskpc, UWORD winpc);
void desk_patcol_apply(void);
void win_view(void);
void win_srtall(void);
void win_bdall(void);
void win_shwall(void);
WORD win_start(void);
WNODE *win_find(WORD wh);
WNODE *win_ontop(void);
void win_close(WNODE *pw, WORD close_window);
void do_wredraw(WORD wh, const GRECT *pc);
void act_chg(WORD wh, WORD root, WORD obj, WORD set, WORD dodraw);
void act_select(WORD wh, WORD root, WORD obj);
/* A click's effect on the selection: SHIFT toggles one item, a plain
 * click makes one the selection, and a click on nothing clears it. */
void act_bsclick(WORD wh, WORD root, WORD obj, WORD kstate);
WORD act_count(WORD root, WORD *pfirst);
/* ...and what a rubber band leaves: everything the box touches. */
void act_allselect(WORD wh, WORD root, const GRECT *box);
WORD do_open(WORD wh, WORD obj);
WORD do_aopen(WNODE *pw, WORD curr, const char FAR *name,
               const char *args);   /* args: a .TTP's line, or "" */
WORD fun_askline(char *line);           /* one line, in the PREFS dialog */
void do_docu(WNODE *pw, const char FAR *name);   /* Show / Print / Cancel */
void win_rebld(WNODE *pw);
/* The listing entry an item object shows, or 0. */
FNODE FAR *win_fnode(WNODE *pw, WORD obj);
void hndl_wmsg(const WORD *msg);
void do_wfull(WORD wh);

/* deskcmd.c: File -> DOS command's window, on what the command printed */
#define LEN_ZCMD    64                  /* the DOS's line buffer, LBUF */
void cmd_init(void);                    /* greys the item on a DOS without */
void cmd_run(const char *line);         /* run it, and show the output */
WORD cmd_file(const char *path, const char *title);   /* show a document */
WORD cmd_print(const char *path);       /* ...or send it to PRN: */
WORD cmd_msg(const WORD *msg);          /* TRUE: the message was its window's */
void cmd_exit(void);
void app_start(void);
void app_save(void);
/* Options -> Save desktop, and Options -> Read .INF file: the same
 * layout the shell buffer carries between programs, kept on the disk so
 * that it survives the machine being switched off. */
WORD inf_save(void);
WORD inf_read(void);
void cnx_get(void);
void cnx_put(void);

/* deskfun.c: what the desktop says, and what the File menu does to files */
WORD fun_alert(WORD defbut, WORD stnum);
void fun_command(void);                 /* File -> DOS command: the dialog */
void fun_mkdir(WNODE *pw);
/* An item dragged out of pw and let go over (dst_wh, dst_obj): a copy,
 * a move when SHIFT is held, a delete over the trash. */
void fun_file2any(WNODE *pw, WORD dst_wh, WORD dst_obj, WORD kstate);
void fun_del(WNODE *pw);
/* File -> Show info: what the selected item is, and the two things the
 * dialog can change about it -- its name and its read-only bit. */
void fun_info(WNODE *pw);

#endif /* GEM4XE_DESK_H */
