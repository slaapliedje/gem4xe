/* run8sdx.c -- a plain Atari program after GEM under SpartaDOS X, and GEM
 * again after it (phase 164, docs/run8-plan.md step 3).
 *
 * G4DOS's shell reads GEM's note (src/sys/runnote.h); on DOS 2 and MyDOS
 * GEM leaves a stub of its own (src/run8.s).  SpartaDOS X has a better
 * answer of its own: its command processor runs the batch file the
 * environment variable BATCH names, just before it prints its prompt, and
 * deletes the variable as it reads it (User Guide 4.50, 5.2.1); and a
 * program run from a batch file comes back to the batch's next line.
 * Measured on SDX 4.50 (phase 164): typed at the prompt, and set from
 * inside GEM through XCOMLI before GEM ended -- the batch ran after GEM,
 * not inside the call.
 *
 * So GEM writes RUN8.BAT beside its own file, two lines -- the program,
 * then GEM -- sets BATCH to it with SET, through the XCOMLI that File ->
 * DOS command uses (src/sys/dos.c, dos_command), and ends.  SDX loads the
 * program itself, so its own relocatable format runs as well as the
 * Atari's.
 *
 * TWO NAMES, RUN8.BAT and RUN9.BAT, in turn.  A GEM started by the batch's
 * last line runs while SDX still has that batch open, reading it, so the
 * next plain program could not write the same file again: the second one
 * from the same desktop said "cannot be found" (measured, phase 164).  So
 * when one will not open for writing, the other is used; SDX has closed
 * the older by the time it reads BATCH.  Both stay on the disk.
 *
 * THE CARTRIDGE (phase 165) is the name "CAR:": the batch's first line is
 * then SDX's own command for it, CAR for a cartridge or BASIC for the
 * XL/XE's own (User Guide 4.50, 4.7 and 4.4), whichever the AES found at
 * boot (src/sys/dos.c dos_cart).
 *
 * A RESET abandons a batch file -- the User Guide's CLR (4.12) is for the
 * variables "a batch file aborted with <RESET>" leaves -- so a RESET
 * during the program is SDX's prompt, not GEM: type GEM there.
 *
 */
#include "portab.h"
#include <string.h>
#include "aes/aes.h"
#include "sys/app.h"
#include "sys/cio.h"
#include "sys/dos.h"

#define R8S_NAME    24              /* GEM's file, and the batch's */
#define R8S_LINE    (5 + 6 + R8S_NAME)  /* "SET BATCH=" and the batch */

/* GEM's own file under SDX, as the boot disks start it: AUTOEXEC.BAT
 * changes into \GEM and runs GEM, so the current directory first. */
static const char FAR r8s_gems[3][R8S_NAME] = {
    "D1:GEM.COM", "D1:>GEM>GEM.COM", "D1:>GEM.COM"
};
static const char FAR r8s_bat[2][9] = { "RUN8.BAT", "RUN9.BAT" };
static const char FAR r8s_set[] = "SET BATCH=";
static const char FAR r8s_car[] = "CAR";
static const char FAR r8s_basic[] = "BASIC";

/* `far` into `near`, n bytes at most and a NUL: a byte read into a word
 * first (tools/ccbug, B18). */
static WORD r8s_get(char *near, const char FAR *far, WORD n)
{
    WORD i;

    for (i = 0; i < n - 1; i++) {
        int c = (uint8_t)far[i];
        if (!c)
            break;
        near[i] = (char)c;
    }
    near[i] = 0;
    return i;
}

WORD run8_sdx(const char *cmd)
{
    char gem[R8S_NAME], bat[R8S_NAME], prog[CIO_NAME_MAX + 2];
    char line[R8S_LINE];
    WORD g, i, k, n;
    int16_t io;
    uint8_t st;

    for (g = 0; g < 3; g++) {
        r8s_get(gem, r8s_gems[g], R8S_NAME);
        if (sh_ourfile(gem))
            break;
    }
    if (g == 3)
        return APP_E_PLAINGEM;
    /* the batch beside it: GEM's name with RUN8.BAT or RUN9.BAT for its
     * last part (above) */
    for (i = 0, k = 0; gem[i]; i++)
        if (gem[i] == ':' || gem[i] == '>')
            k = i + 1;
    for (i = 0; i < k; i++)
        bat[i] = gem[i];
    for (g = 0; g < 2; g++) {
        r8s_get(bat + k, r8s_bat[g], (WORD)(R8S_NAME - k));
        io = cio_open(bat, CIO_A_WRITE, 0);
        if (io >= 0)
            break;
    }
    if (io < 0)
        return APP_E_FILE;
    if (cmd[0] == 'C' && cmd[1] == 'A' && cmd[2] == 'R' && cmd[3] == ':' && !cmd[4])
        r8s_get(prog, dos_cart == DOS_CART_ROM ? r8s_car : r8s_basic,
                (WORD)sizeof prog);
    else
        dos_cioname(cmd, prog);
    n = (WORD)strlen(prog);
    prog[n] = (char)0x9B;
    st = cio_write(io, prog, (uint16_t)(n + 1));
    k = (WORD)strlen(gem);
    gem[k] = (char)0x9B;
    if (st == CIO_OK)
        st = cio_write(io, gem, (uint16_t)(k + 1));
    if (cio_close(io) != CIO_OK || st != CIO_OK)
        return APP_E_FILE;
    k = r8s_get(line, r8s_set, R8S_LINE);
    for (i = 0; bat[i] && k < R8S_LINE - 1; i++)
        line[k++] = bat[i];
    line[k] = 0;
    if (dos_command((uint32_t)(uint16_t)line, 0, 0) < 0)
        return APP_E_MAGIC;             /* an SDX without XCOMLI: as before */
    return APP_OK;
}
