/* m53_app.c -- the phase 127 gate program: put aside, and resumed.
 * Phase 129's (tests/emu/m54_switch.py) too, as three copies under three
 * names: it switches when the gate writes step 2, and keeps the id the
 * gate gives each copy.  And phase 130's (m55_desklist.py): step 4 puts
 * up EDIT.RSC's menu bar and names itself for the Desk menu, and every
 * MN_SELECTED it is sent is kept.
 *
 * One window, its own file kept open, and a count in its near data that
 * goes up every turn.  When the gate writes `step`, it calls
 * shel_write(SWM_G4SUSPEND): the desktop comes back, and when the gate
 * starts M53.PRG again from it, the call returns here -- with the count
 * where it was, the window on the screen, the file still open.  It logs
 * every window message, so tests/emu/m53_suspend.py can see the redraws
 * and the WM_ONTOP a resume sends.
 */
#include "gem.h"

WORD r_wh;
WORD r_fh;                      /* M53.PRG, open from the start */
WORD r_ready;
WORD step;                      /* the gate writes 1: put me aside;
                                 * 2: switch to the next; 3: an alert,
                                 * without wind_update (phase 129); 4: a
                                 * menu bar and a title (phase 130) */
WORD r_inalert;                 /* in that alert */
WORD r_alerts;                  /* ...and how many have been answered */
WORD r_id;                      /* the gate's name for this copy, shown
                                 * in its window's title */
static WORD r_shown;
static char r_title[] = " Put aside ? ";
WORD r_apid;
WORD r_vh;                      /* a virtual workstation of its own, which
                                 * must outlive the others' turns (phase 130) */
WORD r_bar;                     /* step 4: the bar is up */
static char r_mtitle[] = "  Gate ?";
static OBJECT *r_menu;
WORD r_mnsel[2];                /* the last MN_SELECTED: title, item */
WORD r_mnsels;                  /* ...and how many */
WORD r_switches;                /* shel_write(SWM_G4SWITCH) returned... */
WORD r_swret;                   /* ...with this, the last time */
WORD app_quit;
uint16_t r_count;               /* every turn, in near data */
WORD r_resumes;                 /* shel_write(SWM_G4SUSPEND) returned */
WORD r_ret[4];                  /* ...with these */
WORD r_read[4];                 /* the file's first two bytes read again */
uint8_t r_head[4][2];           /* ...and what they were */
WORD r_log[48][2];              /* window messages: type, handle */
WORD r_nlog;

static void logmsg(const WORD *m)
{
    if (r_nlog < 48) {
        r_log[r_nlog][0] = m[0];
        r_log[r_nlog][1] = m[3];
        r_nlog++;
    }
}

int main(void)
{
    WORD msg[8], mx, my, mb, ks, kr, br, k;
    LONG fh;

    r_apid = appl_init();
    {
        WORD wi[11], wo[57], i, d;

        r_vh = graf_handle(&d, &d, &d, &d);
        for (i = 0; i < 10; i++)
            wi[i] = 1;
        wi[10] = 2;
        v_opnvwk(wi, &r_vh, wo);
    }
    fh = Fopen("M53.PRG", 0);
    r_fh = (WORD)fh;
    r_wh = wind_create(NAME | MOVER, 60, 40, 300, 120);
    wind_set_str(r_wh, WF_NAME, " Put aside ");
    wind_open(r_wh, 60, 40, 300, 120);
    r_ready = 1;

    while (!app_quit) {
        WORD what = evnt_multi_moblk((UWORD)(MU_MESAG | MU_TIMER), 1, 1, 1,
                                     0, 0, msg, 50, 0,
                                     &mx, &my, &mb, &ks, &kr, &br);
        r_count++;
        if (r_id != r_shown) {
            r_shown = r_id;
            r_title[11] = (char)('0' + (r_id & 7));
            wind_set_str(r_wh, WF_NAME, r_title);
        }
        if (step == 1) {
            step = 0;
            k = (WORD)(r_resumes & 3);
            r_ret[k] = shel_write(SWM_G4SUSPEND, 0, 0, "", "");
            Fseek(0, r_fh, 0);
            r_read[k] = (WORD)Fread(r_fh, 2, r_head[k]);
            r_resumes++;
        }
        if (step == 2) {
            step = 0;
            r_swret = shel_write(SWM_G4SWITCH, 1, 0, "", "");
            r_switches++;
        }
        if (step == 3) {
            step = 0;
            r_inalert = 1;
            form_alert(1, "[1][Put aside?][ OK ]");
            r_inalert = 0;
            r_alerts++;
        }
        if (step == 4) {
            step = 0;
            if (rsrc_load("EDIT.RSC")
                && rsrc_gaddr(R_TREE, 0, (void **)&r_menu)) {
                r_mtitle[7] = (char)('0' + (r_id & 7));
                menu_register(r_apid, r_mtitle);
                menu_bar(r_menu, 1);
                r_bar = 1;
            }
        }
        if (!(what & MU_MESAG))
            continue;
        switch (msg[0]) {
        case MN_SELECTED:
            r_mnsel[0] = msg[3];
            r_mnsel[1] = msg[4];
            r_mnsels++;
            menu_tnormal(r_menu, msg[3], 1);
            break;
        case WM_TOPPED:
            logmsg(msg);
            wind_set(msg[3], WF_TOP, 0, 0, 0, 0);
            break;
        case WM_REDRAW:
        case WM_ONTOP:
        case WM_UNTOPPED:
            logmsg(msg);
            break;
        default:
            break;
        }
    }
    if (r_bar) {
        menu_bar(r_menu, 0);
        rsrc_free();
    }
    if (r_vh > 0)
        v_clsvwk(r_vh);
    Fclose(r_fh);
    wind_close(r_wh);
    wind_delete(r_wh);
    appl_exit();
    return 0;
}
