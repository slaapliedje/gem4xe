/* m16_desk.c -- the stand-in desktop of tests/emu/m16_shell.py.
 *
 * A gem4xe application like any other (src/app/gem.h), built as
 * DESKTOP.G4A on the milestone-3 disk (build/m14-boot.atr) in place of
 * the real desktop (src/desk/), so that the shell loop in
 * src/aes/shel.c can be driven from the keyboard by a gate: it loads
 * this first, runs whatever it asks for with shel_write, and loads it
 * again when that returns, until it asks to shut down.  A line of help,
 * then a key:
 *
 *     R   run M11.G4A, the gate application, and come back
 *     C   run CALC.G4A, and K CLOCK.G4A -- the two programs, which
 *         are gated through this same loop (tests/emu/m22_apps.py)
 *     B   run M29.G4A, which is compiled --data-model=large and keeps
 *         its variables in far memory (tests/emu/m29_big.py)
 *     H   run M31.G4A, whose far IMAGE is bigger than a bank -- the
 *         format-2 loader path (tests/emu/m31_huge.py)
 *     T   run M32.G4A, a TOS program in all but name: GEMDOS's console,
 *         its standard handles and Pterm (tests/emu/m32_con.py)
 *     F   run M33.G4A, whose resource does not fit the pool and is loaded
 *         FAR; G runs M33S.G4A, the same program compiled small-data,
 *         which must be refused (tests/emu/m33_farrsc.py)
 *     X   ask for NOPE.G4A, which is not there: the shell's alert, then
 *         the desktop again
 *     V   shel_wdef: the desktop's directory set to A:\SUB, then
 *         M11.G4A -- so the run AFTER this one is the one that starts
 *         somewhere the shell was told rather than the system's place
 *     Q   shut GEM down and return to DOS, having checked shel_rdef and
 *         shel_wdef and returned what it found as main()'s value: bit 0
 *         the name kept, 1 the directory kept, 2 and 3 a fresh pair read
 *         back, 4 the directory V asked for actually used
 *
 * The entry, the exit and the two shel_write calls are the contract the
 * real desktop keeps.
 */
#include "gem.h"

/* No string.h here: an application links against nothing of gem4xe's
 * and the kit is the AES, not a C library. */
static WORD samestr(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (*a == 0 && *b == 0);
}

int main(void)
{
    WORD work_in[11], work_out[57];
    WORD handle, wchar, hchar, wbox, hbox, k;
    WORD verify = 0;
    /* STATIC, not stack: shel_rdef's two buffers are 13 and 114 bytes by
     * contract, and main() already has v_opnvwk's 114-byte work_out on
     * an application stack of 256 (the Makefile's APP_STACK).  As locals
     * they overran it and the desktop drew its line of help in the wrong
     * colour before the keys stopped working at all. */
    static char cmd[13], dir[114];

    appl_init();
    handle = graf_handle(&wchar, &hchar, &wbox, &hbox);
    for (k = 0; k < 10; k++)
        work_in[k] = 1;
    work_in[10] = 2;
    v_opnvwk(work_in, &handle, work_out);

    /* WHERE THE SHELL PUT US.  shel_wdef's directory is used at the next
     * desktop load, so the run after the one that set it is where it
     * shows -- which is why this is read at start-up and not on a key. */
    if (Dgetpath((char FAR *)dir, 0) == 0 && samestr(dir, "\\SUB"))
        verify |= 0x10;

    vst_color(handle, 1);
    v_gtext(handle, 8, hbox + 16, "gem4xe desktop -- R M11, C CALC, K CLOCK, B M29, H M31, T M32, X none, Q quits");

    for (;;) {
        k = (WORD)(evnt_keybd() & 0x00FF);
        if (k == 'r' || k == 'R') {
            shel_write(SHW_EXEC, 1, 0, "M11.G4A", "\0");
            break;
        }
        /* Into the folder first, then the program by its full path --
         * which is what the real desktop does before it runs one
         * (src/desk/deskwin.c do_aopen), and what makes this gate cover
         * the thing that was broken: an application in a FOLDER finding
         * its own resource beside it (docs/phase29.md). */
        if (k == 'c' || k == 'C') {
            Dsetpath("A:\\APPS");
            shel_write(SHW_EXEC, 1, 1, "A:\\APPS\\CALC.G4A", "\0");
            break;
        }
        if (k == 'k' || k == 'K') {
            Dsetpath("A:\\APPS");
            shel_write(SHW_EXEC, 1, 1, "A:\\APPS\\CLOCK.G4A", "\0");
            break;
        }
        /* B: the large-data program (src/m29_big.c).  It is in the root
         * rather than in \APPS\ because what test-m29 is about is the
         * MEMORY MODEL, not the path. */
        if (k == 'b' || k == 'B') {
            shel_write(SHW_EXEC, 1, 0, "M29.G4A", "\0");
            break;
        }
        if (k == 'f' || k == 'F') {
            shel_write(SHW_EXEC, 1, 0, "M33.G4A", "\0");
            break;
        }
        if (k == 'g' || k == 'G') {
            shel_write(SHW_EXEC, 1, 0, "M33S.G4A", "\0");
            break;
        }
        /* H: the one whose far IMAGE crosses a bank (src/m31_huge.c).
         * Format 2 and a chunked copy are what let it load at all; before
         * them the packer refused it and the loader would have copied it
         * modulo 65,536 (src/sys/app.c, copy_far). */
        if (k == 'h' || k == 'H') {
            shel_write(SHW_EXEC, 1, 0, "M31.G4A", "\0");
            break;
        }
        if (k == 't' || k == 'T') {
            shel_write(SHW_EXEC, 1, 0, "M32.G4A", "\0");
            break;
        }
        if (k == 'x' || k == 'X') {
            shel_write(SHW_EXEC, 1, 0, "NOPE.G4A", "\0");
            break;
        }
        if (k == 'v' || k == 'V') {
            shel_wdef("DESKTOP.G4A", "A:\\SUB");
            shel_write(SHW_EXEC, 1, 0, "M11.G4A", "\0");
            break;
        }
        if (k == 'q' || k == 'Q') {
            /* What the shell was told last, then a fresh pair read back:
             * shel_rdef and shel_wdef, checked at the last moment so
             * that every bit lands in one main() result -- each run of
             * the desktop is a new process and cannot carry the last
             * one's answers. */
            shel_rdef(cmd, dir);
            if (samestr(cmd, "DESKTOP.G4A"))
                verify |= 0x01;
            if (samestr(dir, "A:\\SUB"))
                verify |= 0x02;
            shel_wdef("NOPE.G4A", "");
            shel_rdef(cmd, dir);
            if (samestr(cmd, "NOPE.G4A"))
                verify |= 0x04;
            if (dir[0] == 0)
                verify |= 0x08;
            shel_write(SHW_SHUTDOWN, 0, 0, "", "\0");
            break;
        }
    }
    v_clsvwk(handle);
    appl_exit();
    return verify;
}
