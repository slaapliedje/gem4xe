/* gemcompat.c -- the names an Atari ST source expects and no ISO C
 * library has: the non-ISO string functions (<support.h>) and the
 * directory walk (<dirent.h>).
 *
 * This file exists so that a port does not have to write it.  qed wrote
 * all of it in its own shim before it was here, which is the evidence
 * that it belongs in the kit rather than in each program.
 */
#include "portab.h"
#include "gem.h"
#include "support.h"
#include "dirent.h"
#include <string.h>

/* ---- the non-ISO string functions --------------------------------------
 *
 * ASCII case folding, written here rather than taken from <ctype.h>: the
 * library's is Apache-2.0 and this tree is GPLv2 (see support.h), and it
 * is four lines. */
static int lower(int c)
{
    return (c >= 'A' && c <= 'Z') ? c + ('a' - 'A') : c;
}

static int upper(int c)
{
    return (c >= 'a' && c <= 'z') ? c - ('a' - 'A') : c;
}

int stricmp(const char *a, const char *b)
{
    int ca, cb;

    do {
        ca = lower((unsigned char)*a++);
        cb = lower((unsigned char)*b++);
        if (ca != cb)
            return ca - cb;
    } while (ca);
    return 0;
}

int strnicmp(const char *a, const char *b, size_t n)
{
    int ca, cb;

    while (n--) {
        ca = lower((unsigned char)*a++);
        cb = lower((unsigned char)*b++);
        if (ca != cb)
            return ca - cb;
        if (!ca)
            break;
    }
    return 0;
}

char *strlwr(char *s)
{
    char *p;

    for (p = s; *p; p++)
        *p = (char)lower((unsigned char)*p);
    return s;
}

char *strupr(char *s)
{
    char *p;

    for (p = s; *p; p++)
        *p = (char)upper((unsigned char)*p);
    return s;
}

/* ---- the directory walk -------------------------------------------------
 *
 * The pool <dirent.h> describes.  A slot is free when `used` is 0, which
 * is what a program's BSS starts as, so nothing has to initialise it. */
static DIR dir_pool[DIRENT_MAX];

/* Every GEMDOS attribute a directory listing should show: read-only,
 * hidden, system and subdirectories, plus the ordinary files that need no
 * bit at all.  (Volume label, $08, is deliberately not among them.) */
#define DIR_ATTR (FA_RDONLY | FA_HIDDEN | FA_SYSTEM | FA_SUBDIR)

DIR *opendir(const char *path)
{
    DIR *d = 0;
    char spec[GEM_PATH_MAX];
    DTA FAR *was;
    LONG r;
    WORD i;
    size_t n;

    for (i = 0; i < DIRENT_MAX; i++)
        if (!dir_pool[i].used) {
            d = &dir_pool[i];
            break;
        }
    if (!d)
        return 0;                       /* the pool is full: see dirent.h */

    /* The path with \*.* on the end, however the caller spelled it: a
     * bare "A:" needs no separator, "A:\FOLDER" does. */
    n = strlen(path);
    if (n > sizeof spec - 5)
        n = sizeof spec - 5;
    memcpy(spec, path, n);
    if (n && spec[n - 1] != '\\' && spec[n - 1] != ':')
        spec[n++] = '\\';
    strcpy(spec + n, "*.*");

    was = Fgetdta();
    Fsetdta((DTA FAR *)&d->dta);
    r = Fsfirst(spec, DIR_ATTR);
    Fsetdta(was);

    d->first = 1;
    d->done = 0;
    d->ent.d_name[0] = '\0';
    /* ENMFIL AND NOTHING ELSE means "empty".  gd_fsfirst opens the
     * directory first and only then matches, so ENMFIL is "it is there
     * and holds nothing that matches" -- while a path that names nothing
     * fails earlier, at the open, with EFILNF or EPTHNF.  Folding those
     * together hands the caller a DIR for a directory that is not there;
     * tests/host/test_gemcompat.py exists partly because the first
     * version of this file did exactly that. */
    if (r == ENMFIL)
        d->done = 1;                    /* empty, but still a directory */
    else if (r < 0)
        return 0;                       /* the path names nothing */
    d->used = 1;
    return d;
}

struct dirent *readdir(DIR *d)
{
    DTA FAR *was;
    LONG r;

    if (!d || !d->used || d->done)
        return 0;
    if (d->first) {
        d->first = 0;                   /* Fsfirst's answer, held since opendir */
    } else {
        was = Fgetdta();
        Fsetdta((DTA FAR *)&d->dta);
        r = Fsnext();
        Fsetdta(was);
        if (r < 0) {
            d->done = 1;
            return 0;
        }
    }
    strncpy(d->ent.d_name, d->dta.d_fname, sizeof d->ent.d_name - 1);
    d->ent.d_name[sizeof d->ent.d_name - 1] = '\0';
    return &d->ent;
}

int closedir(DIR *d)
{
    if (!d || !d->used)
        return -1;
    d->used = 0;                        /* the slot goes back to the pool */
    return 0;
}
