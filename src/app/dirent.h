/* dirent.h -- opendir/readdir/closedir, the names an ST program reaches
 * for, over one Fsfirst and a run of Fsnext.
 *
 * mintlib has these over MiNT's Dopendir with an Fsfirst fallback; this
 * machine has no Dopendir, so the fallback is the only path and there is
 * nothing to stub on the way to it.
 *
 * NO HEAP IS USED, and that is not a shortcut.  The kit makes malloc() a
 * LINK ERROR on purpose (lib/clib.c): memory above bank $00 belongs to
 * GEMDOS and is handed out by Malloc, which answers a 32-bit address that
 * a --data-model=small program cannot even hold in a pointer.  So a DIR
 * comes from a small fixed pool in the application's own memory, and
 * opendir() answers NULL when the pool is empty, exactly as it does when
 * the path names nothing.  DIRENT_MAX is how many directories one program
 * may hold open at once; qed, which is the biggest port there is, holds
 * two (it lists syntax files while walking a project).
 *
 * Each DIR carries its OWN DTA and sets it around every call, putting the
 * caller's back afterwards, so a walk in progress elsewhere -- cflib's
 * fsexists, the file selector -- is not disturbed by one here.
 */
#ifndef GEM4XE_DIRENT_H
#define GEM4XE_DIRENT_H

#include "gem.h"

#ifndef DIRENT_MAX
#define DIRENT_MAX 4
#endif

struct dirent {
    char d_name[14];            /* 8.3 and a NUL, as GEMDOS gives it */
};

typedef struct {
    DTA           dta;          /* this directory's search state */
    struct dirent ent;          /* what readdir last answered */
    WORD          used;         /* this pool slot is taken */
    WORD          first;        /* 1 until Fsfirst's result has been handed out */
    WORD          done;         /* 1 once Fsnext has said there is no more */
} DIR;

DIR           *opendir(const char *path);
struct dirent *readdir(DIR *d);
int            closedir(DIR *d);

#endif /* GEM4XE_DIRENT_H */
