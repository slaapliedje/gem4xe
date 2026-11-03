/* doscmd.h -- the DOS's commands: G4DOS's command line, in the words a
 * Linux user already has (docs/g4dos-plan.md, step 4).
 *
 *     ls [-l]  cd  pwd  cp  mv  rm  mkdir  rmdir  cat  more  df  help
 *
 * with the old names beside them for fingers that remember them -- DIR,
 * COPY, REN, DEL, MD, RD, TYPE, CHKDSK -- and a program run by typing its
 * name.  A path is D1:/GEM/NAME.EXT: '/', SpartaDOS's '>' and GEM's '\'
 * all go between folders, "." and ".." are what Linux makes them, and
 * '*' and '?' match in a path's last part.
 *
 * ONE IMPLEMENTATION, TWO HOSTS.  The shell G4DOS loads runs these at its
 * prompt; gem4xe runs them for File -> DOS command and GEMDOS's Psystem
 * where the DOS is G4DOS (src/sys/sdcio.c), as SpartaDOS X's XCOMLI does
 * elsewhere.  Both over the SDFS engine (sdfs.h), and like it this file is
 * portable C: the host builds it too, and tests/host/test_doscmd.py holds
 * it to tools/atr.py.  It knows nothing of the screen; the platform gives
 * it four functions, below.
 *
 * ALL ITS STATE IS ONE BLOCK, a DC_STATE, the caller's, and FAR, as the
 * engine's is: on the Atari under GEM a call runs on an application's
 * bank-$00 stack, which has no room for paths.
 */
#ifndef GEM4XE_DOSCMD_H
#define GEM4XE_DOSCMD_H

#include "sdfs.h"

#define DC_PATH   64            /* a path from a unit's root, '\' between parts */
#define DC_LINE   128           /* a command line */
#define DC_ARGS   16            /* the words on it */
#define DC_OUT    40            /* output gathered before it goes */
#define DC_BUF    512           /* cp's and cat's buffer */
#define DC_EOL    0x9B          /* ATASCII's end of line: what the output ends
                                   each line with */

typedef struct {
    SDFS FAR *fs;
    uint8_t  drive;             /* the current unit, 1..8 */
    uint8_t  cols;              /* the screen's width ... */
    uint8_t  rows;              /* ... and height: 0, more never waits */
    uint8_t  col;               /* where the next byte goes on it */
    uint8_t  row;               /* lines since more last waited */
    uint8_t  paging;            /* more is running */
    uint8_t  quit;              /* ...and its reader said q */
    uint8_t  argc;
    uint8_t  on;                /* bytes in out */
    uint8_t  cr;                /* cat: the byte before was a CR */
    uint8_t  lscol;             /* ls: names on this row so far */
    uint8_t  du;                /* cp, mv: the destination's unit ... */
    uint8_t  dfold;             /* ... and it is a folder */
    uint8_t  lng;               /* ls: the long form */
    uint8_t  wild;              /* ls: a wildcard's names, not inside them */
    uint8_t  lsgap;             /* ls: spaces owed after the last name */
    uint8_t  keep;              /* cp for mv: the file keeps its time */
    uint8_t  pad;
    int16_t  err;               /* the last command's error, 0 none */
    uint16_t argv[DC_ARGS];     /* where each word starts in line */
    char     out[DC_OUT];
    char     line[DC_LINE];
    char     cwd[SD_UNITS][DC_PATH];    /* each unit's folder, "" the root */
    char     a[DC_PATH];        /* the path a command is working on */
    char     b[DC_PATH];        /* ...and where it is going */
    char     c[DC_PATH];        /* a wildcard's folder */
    char     d[DC_PATH];        /* cp's and mv's destination, as given */
    char     pat[14];           /* a wildcard's last part */
    SD_INFO  info;              /* the entry a listing is on */
    SD_INFO  info2;             /* ...and one a command looked up */
    uint8_t  buf[DC_BUF];
} DC_STATE;

/* ---- what the platform gives -------------------------------------------
 * dc_out: n bytes of output, lines ended by DC_EOL; and $9C, ATASCII's
 * delete-line, after more's prompt.
 * dc_key: a key, for more's prompt, or -1 where there is no keyboard.
 * dc_exec: run the program at `path` of `unit` -- which does not come back
 * where it can -- or a negative error, said already, where it cannot.
 * dc_reboot: start the machine again, or a negative error, said. */
void    dc_out(DC_STATE FAR *h, const char FAR *s, uint16_t n);
int16_t dc_key(DC_STATE FAR *h);
int16_t dc_exec(DC_STATE FAR *h, uint8_t unit, const char FAR *path);
int16_t dc_reboot(DC_STATE FAR *h);

/* ---- the commands -------------------------------------------------------
 * dc_init: D1:'s root, a screen cols by rows (rows 0: never wait).
 * dc_run: one line, to its 0 or its EOL: 0, or the last error a command
 * on it had (negative, GEMDOS's numbers, sdfs.h).
 * dc_prompt: where the user is, as the prompt says it: "D1:/GEM$ ". */
void    dc_init(DC_STATE FAR *h, SDFS FAR *fs, uint8_t cols, uint8_t rows);
int16_t dc_run(DC_STATE FAR *h, const char FAR *line);
void    dc_prompt(DC_STATE FAR *h);
/* the output gathered so far, given to dc_out */
void    dc_flush(DC_STATE FAR *h);
/* A message in the commands' own words, and a line end: what a platform's
 * dc_exec says when it cannot. */
void    dc_say(DC_STATE FAR *h, const char FAR *what, const char FAR *msg);

#endif
