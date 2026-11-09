/* m45_acc.c -- the gate accessory with a WINDOW of its own (test-m45).
 *
 * Two things in the 0.12 roadmap need an accessory and neither of the
 * shipped ones will do: they put up dialogs, not windows, and they are
 * too big for six of them to share the pool.
 *
 *   ITEM 11, THE SLOTS.  The gate's disk carries seven copies of this
 *   file, A1.ACC to A7.ACC.  Six must load and register -- every slot
 *   the Desk box has -- and the seventh must be turned away, and the
 *   person told.  So this is as small as an accessory can be: no
 *   workstation, a near region of a few hundred bytes.
 *
 *   ITEM 12, THE MESSAGES.  On AC_OPEN it opens a window, and every
 *   WM_* the AES sends about that window must come HERE: a WM_REDRAW
 *   when it opens or is uncovered, a WM_TOPPED when it is clicked from
 *   behind another, a WM_MOVED when its bar is dragged, a WM_CLOSED from
 *   its close box.  It answers them as a GEM program does and counts
 *   them, and the gate reads the counts.  A message about some OTHER
 *   window -- one the AES should have sent its owner -- is counted
 *   apart, as the misdelivery it is.
 *
 * Its redraw paints its work area white through its own rectangle list,
 * with a one-object tree, so that what the gate photographs is a window
 * drawn by its owner and not whatever was under it.
 *
 *   ITEM 13, THE INPUT (phase 134).  While its window is open it waits
 *   for a press and a key as well as a message, and counts them: a press
 *   inside its window and a key typed while it is on top are its own;
 *   once the desktop's window is on top, or the bare desk is pressed,
 *   neither may reach it -- the desktop's, as the top window's owner.
 *   WHILE ITS WINDOW IS BEHIND, it polls -- a timer of 0 ms, a GEM
 *   program's way of polling -- so that it runs all the time it is not
 *   the owner, which is the case the AES's rule is for: a process with
 *   nothing to wake it never runs then, and could not take what is not
 *   its own however input were handed out, which made the first version
 *   of this check pass with the rule removed (and 20 ms gave it too few
 *   turns to land on a key).  On top it waits quietly: polling all the
 *   time slowed the machine until the desktop missed a double-click.
 *   It knows it is behind from WM_UNTOPPED (phase 125), and on top again
 *   because it tops itself.
 */
#include "gem.h"

/* Everything the gate reads, by symbol out of build/m45_acc.sym. */
WORD acc_id;                    /* what appl_init answered */
WORD acc_menu;                  /* what menu_register answered */
WORD acc_opens;                 /* AC_OPEN */
WORD acc_closes;                /* AC_CLOSE */
WORD acc_wh = -1;               /* its window, -1 for none */
WORD acc_redraws;               /* WM_REDRAW for its window */
WORD acc_topped;                /* WM_TOPPED */
WORD acc_moved;                 /* WM_MOVED */
WORD acc_closed;                /* WM_CLOSED */
WORD acc_foreign;               /* a WM_ message for a window not its own */
WORD acc_buttons;               /* presses it was given (item 13) */
WORD acc_keys;                  /* ...and keys */
WORD acc_untopped;              /* WM_UNTOPPED: its window went behind */
WORD acc_last[8];               /* the last message, word for word */
static WORD acc_top;            /* its window is on top, it believes */

static char acc_title[] = "  Window gate";

/* Where it opens: away from the desktop's icons and from where the
 * desktop opens a drive's window, so both can be clicked. */
#define WX  288
#define WY  120
#define WW  240
#define WH  80
#define KIND (NAME | CLOSER | MOVER)

/* White, solid, a frame of nothing: the colour word is frame 1, text 1,
 * pattern 7, interior 0 (src/app/gem.h's OBSPEC_BITS). */
static OBJECT paper[1] = {
    { NIL, NIL, NIL, G_BOX, LASTOB, NORMAL, { 0x00001170L }, 0, 0, 0, 0 }
};

static void redraw(WORD wh, WORD x, WORD y, WORD w, WORD h)
{
    WORD rx, ry, rw, rh;

    wind_update(BEG_UPDATE);
    wind_get(wh, WF_WORKXYWH, &paper[0].ob_x, &paper[0].ob_y,
             &paper[0].ob_width, &paper[0].ob_height);
    wind_get(wh, WF_FIRSTXYWH, &rx, &ry, &rw, &rh);
    while (rw && rh) {
        /* the part of this piece the message asked for */
        WORD x1 = rx > x ? rx : x, y1 = ry > y ? ry : y;
        WORD x2 = rx + rw < x + w ? rx + rw : x + w;
        WORD y2 = ry + rh < y + h ? ry + rh : y + h;
        if (x2 > x1 && y2 > y1)
            objc_draw(paper, ROOT, 0, x1, y1, x2 - x1, y2 - y1);
        wind_get(wh, WF_NEXTXYWH, &rx, &ry, &rw, &rh);
    }
    wind_update(END_UPDATE);
}

int main(void)
{
    WORD msg[8];
    WORD i;

    acc_id = appl_init();
    acc_menu = menu_register(acc_id, acc_title);

    for (;;) {
        if (acc_wh >= 0) {
            /* a window open: its presses and keys too (item 13) */
            WORD mx, my, mb, ks, kr, nc, ev;

            ev = evnt_multi(MU_MESAG | MU_BUTTON | MU_KEYBD
                            | (acc_top ? 0 : MU_TIMER),
                            1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                            msg, 0, 0, &mx, &my, &mb, &ks, &kr, &nc);
            if (ev & MU_BUTTON) {
                /* one press, however long it is held: a wait for "down"
                 * is satisfied for as long as the button is, so a GEM
                 * program waits for it to come up again */
                acc_buttons++;
                evnt_button(1, 1, 0, &mx, &my, &mb, &ks);
            }
            if (ev & MU_KEYBD)
                acc_keys++;
            if (!(ev & MU_MESAG))
                continue;
        } else
            evnt_mesag(msg);
        for (i = 0; i < 8; i++)
            acc_last[i] = msg[i];
        switch (msg[0]) {
        case AC_OPEN:
            acc_opens++;
            if (acc_wh >= 0) {                  /* open: bring it up */
                wind_set(acc_wh, WF_TOP, 0, 0, 0, 0);
                break;
            }
            acc_wh = wind_create(KIND, WX, WY, WW, WH);
            if (acc_wh >= 0)
                wind_open(acc_wh, WX, WY, WW, WH);
            acc_top = 1;
            break;
        case AC_CLOSE:
            /* the AES has destroyed it already (src/aes/menu.c) */
            acc_closes++;
            acc_wh = -1;
            break;
        case WM_REDRAW:
        case WM_TOPPED:
        case WM_MOVED:
        case WM_CLOSED:
            if (msg[3] != acc_wh || acc_wh < 0) {
                acc_foreign++;
                break;
            }
            if (msg[0] == WM_REDRAW) {
                acc_redraws++;
                redraw(msg[3], msg[4], msg[5], msg[6], msg[7]);
            } else if (msg[0] == WM_TOPPED) {
                acc_topped++;
                wind_set(msg[3], WF_TOP, 0, 0, 0, 0);
                acc_top = 1;
            } else if (msg[0] == WM_MOVED) {
                acc_moved++;
                wind_set(msg[3], WF_CURRXYWH, msg[4], msg[5], msg[6], msg[7]);
            } else {
                acc_closed++;
                wind_close(msg[3]);
                wind_delete(msg[3]);
                acc_wh = -1;
            }
            break;
        case WM_UNTOPPED:
            if (msg[3] == acc_wh && acc_wh >= 0) {
                acc_untopped++;
                acc_top = 0;
            }
            break;
        default:
            if (msg[0] >= WM_REDRAW && msg[0] <= WM_MOVED && msg[3] != acc_wh)
                acc_foreign++;              /* some other window's */
            break;
        }
    }
}
