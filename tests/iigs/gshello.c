/* gshello.c -- GSlayer milestone 1: the first Toolbox program.
 *
 * Built with ORCA/C (Golden Gate) as a GS/OS S16 application.  The same
 * binary runs twice: on MAME's apple2gs against Apple's own Toolbox, and
 * on gem4xe under GSlayer.  The gate compares the two Super Hi-Res
 * screens byte for byte, so everything drawn here is deterministic.
 *
 * Tool sets used: Tool Locator (1), Memory Manager (2), Misc Tools (3),
 * QuickDraw II (4).  Nothing else, on purpose.
 *
 * When the drawing is done, "GSDONE" is written to $E1:9DF0, in the unused
 * bytes between the SCBs ($E1:9D00-$9DC7) and the palettes ($E1:9E00).
 * That is the harness's signal on both machines, and the only direct
 * hardware write in the program.
 */
#include <types.h>
#include <locator.h>
#include <memory.h>
#include <misctool.h>
#include <quickdraw.h>

#define MODE640     0x80            /* master SCB: 640 mode, palette 0 */

static void done(void)
{
    static char sig[] = "GSDONE";
    unsigned char *p = (unsigned char *) 0xE19DF0L;
    int i;

    for (i = 0; i < 6; i++)
        p[i] = sig[i];
}

int main(void)
{
    Word id;
    Handle dp;
    Rect r;

    TLStartUp();
    id = MMStartUp();
    MTStartUp();

    /* QuickDraw II's three pages of direct page, in bank $00. */
    dp = NewHandle(0x300L, id, attrLocked | attrFixed | attrBank | attrPage,
                   (Pointer) 0L);
    QDStartUp((Word) *(LongWord *) dp, MODE640, 640, id);

    ClearScreen(0xFFFF);            /* every pixel 3: white in 640 mode */

    SetSolidPenPat(0);              /* black */
    SetRect(&r, 40, 30, 240, 90);
    PaintRect(&r);

    SetRect(&r, 300, 30, 600, 150);
    FrameRect(&r);

    MoveTo(320, 60);
    DrawCString("GSlayer");

    MoveTo(320, 80);
    DrawCString("Hello, Toolbox");

    done();
    for (;;)
        ;
}
