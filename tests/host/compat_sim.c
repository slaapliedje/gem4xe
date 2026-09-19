/* compat_sim.c -- drive src/app/gemcompat.c under Calypsi's simulator.
 *
 * The four GEMDOS calls the directory walk makes are stubbed here, so the
 * test needs no machine and no disk: Fsfirst/Fsnext hand out a table of
 * names, and Fgetdta/Fsetdta are a variable.  That is enough to check the
 * things that actually go wrong in a directory walk -- the search spec
 * built from the caller's path, the caller's DTA being put back, two
 * walks interleaved, and a pool that runs out -- none of which a run
 * against a real disk would show as clearly.
 */
#include "portab.h"
#include "gem.h"
#include "support.h"
#include "dirent.h"
#include <string.h>

/* ---- the fake directory ------------------------------------------------- */

#define NENT 5
static const char *const entries[NENT] = {
    "AUTOEXEC.BAT", "GEM.COM", "QED.RSC", "SUB", "X32G.DOS"
};

static DTA FAR *cur_dta;
/* Each open search keeps its position by the DTA that owns it, which is
 * what the real GEMDOS does (src/sys/gemdos.c). */
#define NSEARCH 4
static DTA FAR *search_dta[NSEARCH];
static WORD     search_pos[NSEARCH];

char csim_spec[64];             /* the last spec Fsfirst was given */
WORD csim_missing;              /* 1: make the next Fsfirst fail */
WORD csim_empty;                /* 1: make the next Fsfirst answer ENMFIL */

void Fsetdta(DTA FAR *dta) { cur_dta = dta; }
DTA FAR *Fgetdta(void) { return cur_dta; }

static WORD slot_for(DTA FAR *d)
{
    WORD i;
    for (i = 0; i < NSEARCH; i++)
        if (search_dta[i] == d)
            return i;
    for (i = 0; i < NSEARCH; i++)
        if (search_dta[i] == 0) {
            search_dta[i] = d;
            return i;
        }
    return 0;
}

static void fill(DTA FAR *d, WORD n)
{
    WORD i;
    for (i = 0; i < 14; i++)
        d->d_fname[i] = 0;
    strcpy((char *)d->d_fname, entries[n]);
    d->d_attrib = (char)(n == 3 ? FA_SUBDIR : 0);
    d->d_length = (LONG)n * 100;
}

LONG Fsfirst(const char FAR *spec, WORD attr)
{
    WORD s;
    (void)attr;
    strncpy(csim_spec, (const char *)spec, sizeof csim_spec - 1);
    csim_spec[sizeof csim_spec - 1] = 0;
    if (csim_missing)
        return EFILNF;
    s = slot_for(cur_dta);
    if (csim_empty) {
        search_pos[s] = NENT;
        return ENMFIL;
    }
    search_pos[s] = 0;
    fill(cur_dta, 0);
    return 0;
}

LONG Fsnext(void)
{
    WORD s = slot_for(cur_dta);
    if (search_pos[s] + 1 >= NENT)
        return ENMFIL;
    search_pos[s]++;
    fill(cur_dta, search_pos[s]);
    return 0;
}

/* ---- what the test reads ------------------------------------------------ */

char csim_spec_plain[64];       /* the spec built from "A:\\SUB"   */
char csim_spec_slash[64];       /* ...and from "A:\\SUB\\"        */
char csim_spec_drive[64];       /* ...and from "A:"               */
char csim_names[NENT][14];      /* every name readdir handed back */
WORD csim_count;                /* how many it handed back        */
WORD csim_dta_restored;         /* the caller's DTA was put back  */
char csim_a3[14], csim_b1[14];  /* two walks, interleaved         */
WORD csim_pool_full;            /* DIRENT_MAX+1 opens: the last failed */
WORD csim_pool_reuse;           /* ...and a close frees a slot    */
WORD csim_missing_null;         /* opendir of a missing path is NULL */
WORD csim_empty_ok;             /* an empty directory still opens */
WORD csim_empty_read;           /* ...and reads as nothing        */
WORD csim_close_twice;          /* closedir twice is an error     */
WORD csim_stricmp, csim_stricmp_ne, csim_strnicmp;
char csim_lwr[16], csim_upr[16];
WORD csim_ran;

static DTA caller_dta;

int main(void)
{
    DIR *d, *e, *pool[DIRENT_MAX + 1];
    struct dirent *ent;
    WORD i;

    /* the spec opendir builds, from three spellings of a path */
    d = opendir("A:\\SUB");
    strcpy(csim_spec_plain, csim_spec);
    if (d) closedir(d);
    d = opendir("A:\\SUB\\");
    strcpy(csim_spec_slash, csim_spec);
    if (d) closedir(d);
    d = opendir("A:");
    strcpy(csim_spec_drive, csim_spec);
    if (d) closedir(d);

    /* a whole walk, with the caller's DTA set first so the restore shows */
    Fsetdta((DTA FAR *)&caller_dta);
    d = opendir("A:\\");
    while ((ent = readdir(d)) != 0 && csim_count < NENT) {
        strcpy(csim_names[csim_count], ent->d_name);
        csim_count++;
    }
    csim_dta_restored = (WORD)(Fgetdta() == (DTA FAR *)&caller_dta);
    closedir(d);

    /* two open at once, read alternately: each must keep its own place */
    d = opendir("A:\\");
    e = opendir("B:\\");
    readdir(d); readdir(d);                 /* d has yielded 0 and 1 */
    ent = readdir(e);                       /* e yields its FIRST, 0 */
    if (ent) strcpy(csim_b1, ent->d_name);
    ent = readdir(d);                       /* d must yield 2, not 0 */
    if (ent) strcpy(csim_a3, ent->d_name);
    closedir(d); closedir(e);

    /* the pool: DIRENT_MAX opens succeed and one more does not */
    for (i = 0; i < DIRENT_MAX + 1; i++)
        pool[i] = opendir("A:\\");
    csim_pool_full = (WORD)(pool[DIRENT_MAX] == 0);
    closedir(pool[0]);
    pool[0] = opendir("A:\\");
    csim_pool_reuse = (WORD)(pool[0] != 0);
    for (i = 0; i < DIRENT_MAX; i++)
        if (pool[i]) closedir(pool[i]);

    /* a path that names nothing */
    csim_missing = 1;
    csim_missing_null = (WORD)(opendir("A:\\NOPE") == 0);
    csim_missing = 0;

    /* an empty directory is still a directory */
    csim_empty = 1;
    d = opendir("A:\\EMPTY");
    csim_empty_ok = (WORD)(d != 0);
    csim_empty_read = (WORD)(d && readdir(d) == 0);
    csim_empty = 0;
    if (d) {
        csim_close_twice = (WORD)(closedir(d) == 0 && closedir(d) == -1);
    }

    /* the non-ISO string functions */
    csim_stricmp = (WORD)(stricmp("GEM4XE", "gem4xe") == 0);
    csim_stricmp_ne = (WORD)(stricmp("abc", "abd") < 0);
    csim_strnicmp = (WORD)(strnicmp("GEM4XE", "gem4zz", 4) == 0
                           && strnicmp("GEM4XE", "gem4zz", 5) != 0);
    strcpy(csim_lwr, "MiXeD.TXT");
    strlwr(csim_lwr);
    strcpy(csim_upr, "MiXeD.TXT");
    strupr(csim_upr);

    csim_ran = 1;
    return 0;
}
