/* form.c -- the AES form library (EmuTOS aes/gemfmlib.c): form_do, the
 * interactive dialog loop, and form_dial's grow/shrink/finish.
 *
 * form_do owns the screen for the life of the dialog.  It moves an edit
 * cursor between the EDITABLE fields, feeds keys to objc_edit, tracks the
 * button over SELECTABLE objects through graf_watchbox, keeps radio
 * buttons exclusive, and returns the EXIT/TOUCHEXIT object that ended it
 * (with bit 15 set for a double click on a TOUCHEXIT).  RETURN selects the
 * DEFAULT object; TAB and the arrows move between fields.
 */
#include "portab.h"
#include "aes.h"

/* ---- screen ownership -----------------------------------------------------
 * GEM's fm_own suspends the menu bar, takes the mouse's control rectangle
 * and holds off other processes' redraws for the dialog's duration.  With
 * one process what remains is the nesting count they hang off -- the
 * window manager's wind_update(BEG_MCTRL/END_MCTRL) shares it, and the
 * menu hold joins it with menu_bar -- and the control rectangle: the
 * whole screen while the form is up, so that a click on a window's
 * gadget goes to the form and not the window manager, and the top
 * window's work area again after.  (form_dial(FMD_FINISH) redraws the
 * desktop through the window manager's w_drawdesk.) */
/* NOT static: wm_new unwinds it (the Compendium's "the state of
 * wind_update() ... is reset"), and it is the form library's because
 * fm_own is. */
WORD  ml_ocnt;
static GRECT ml_ctrl;       /* the application's rectangle, held */

void fm_own(WORD beg_ownit)
{
    if (beg_ownit) {
        if (ml_ocnt == 0) {
            get_ctrl(&ml_ctrl);
            ct_chgown(&gl_rscreen);
        }
        ml_ocnt++;
    } else {
        ml_ocnt--;
        if (ml_ocnt == 0)
            ct_chgown(&ml_ctrl);
    }
}

/* ob_fs: an object's state, and its flags through pflag. */
static WORD ob_fs(OBJECT FAR *tree, WORD obj, WORD *pflag)
{
    WORD st;

    *pflag = (WORD)tree[obj].ob_flags;
    st = (WORD)tree[obj].ob_state;
    return st;
}

/* The next EDITABLE field after (FORWARD) or before (BACKWARD) start_obj,
 * or the DEFAULT object (DEFLT), skipping hidden and disabled ones;
 * start_obj itself if there is none. */
static WORD find_obj(OBJECT FAR *tree, WORD start_obj, WORD which)
{
    WORD obj, flag, state, inc, theflag;

    obj = 0;
    flag = EDITABLE;
    inc = 1;
    switch (which) {
    case BACKWARD:
        inc = -1;
        /* fall through */
    case FORWARD:
        obj = (WORD)(start_obj + inc);
        break;
    case DEFLT:
        flag = DEFAULT;
        break;
    }

    while (obj >= 0) {
        state = ob_fs(tree, obj, &theflag);
        if (!(theflag & HIDETREE) && !(state & DISABLED)) {
            if (theflag & flag)
                return obj;
        }
        if (theflag & LASTOB)
            obj = -1;
        else
            obj = (WORD)(obj + inc);
    }
    return start_obj;
}

static WORD fm_inifld(OBJECT FAR *tree, WORD start_fld)
{
    if (start_fld == 0)
        start_fld = find_obj(tree, 0, FORWARD);
    return start_fld;
}

/* A key while obj is being edited.  The field-moving keys are consumed
 * (*pchar = 0) and name the next field in *pnew_obj; RETURN/ENTER select
 * the DEFAULT object and end the form (FALSE).  Anything else is left for
 * objc_edit. */
WORD fm_keybd(OBJECT FAR *tree, WORD obj, WORD *pchar, WORD *pnew_obj)
{
    WORD direction = -1;
    WORD new_obj, st;

    switch (*pchar) {
    case RETURN:
    case ENTER:
        obj = 0;
        direction = DEFLT;
        break;
    case ARROW_UP:
        direction = BACKWARD;
        break;
    case TAB:           /* shift/ctrl/alt-tab have the same scancode */
    case ARROW_DOWN:
        direction = FORWARD;
        break;
    }

    if (direction != -1) {
        *pchar = 0;
        new_obj = find_obj(tree, obj, direction);
        *pnew_obj = new_obj;
        if (direction == DEFLT && new_obj != 0) {
            st = (WORD)tree[new_obj].ob_state;
            ob_change(tree, new_obj, (UWORD)(st | SELECTED), TRUE);
            return FALSE;
        }
    }
    return TRUE;
}

/* A click on new_obj, clks times.  Selects it (exclusively among radio
 * buttons; through graf_watchbox otherwise, so the user can slide off),
 * then waits for the button to come up.  FALSE if the click ends the
 * form: an EXIT object selected, or any TOUCHEXIT.  *pnew_obj is the
 * object to go on editing (an EDITABLE one) or the exit object, with
 * bit 15 for a double-clicked TOUCHEXIT. */
WORD fm_button(OBJECT FAR *tree, WORD new_obj, WORD clks, WORD *pnew_obj)
{
    WORD tobj, orword, parent, state, flags, cont, tstate, tflags;
    WORD rets[6];

    cont = TRUE;
    orword = 0;
    state = ob_fs(tree, new_obj, &flags);

    if (flags & TOUCHEXIT) {
        if (clks == 2)
            orword = (WORD)0x8000;
        cont = FALSE;
    }

    if ((flags & SELECTABLE) && !(state & DISABLED)) {
        if (flags & RBUTTON) {
            /* turn the old radio button off and this one on */
            parent = ob_get_par(tree, new_obj);
            tobj = tree[parent].ob_head;
            while (tobj != parent) {
                tstate = ob_fs(tree, tobj, &tflags);
                if ((tflags & RBUTTON) &&
                    ((tstate & SELECTED) || tobj == new_obj)) {
                    if (tobj == new_obj) {
                        tstate |= SELECTED;
                        state = tstate;
                    } else {
                        tstate &= ~SELECTED;
                    }
                    ob_change(tree, tobj, (UWORD)tstate, TRUE);
                }
                tobj = tree[tobj].ob_next;
            }
        } else {
            if (gr_watchbox(tree, new_obj, (WORD)(state ^ SELECTED), state))
                state ^= SELECTED;
        }
        /* not a touchexit: wait for the button to come up */
        if (cont && (flags & (SELECTABLE | EDITABLE)))
            ev_button(1, 0x0001, 0x0000, rets);
    }

    if ((state & SELECTED) && (flags & EXIT))
        cont = FALSE;

    /* a click elsewhere than an editable field does not move the cursor */
    if (cont && !(flags & EDITABLE))
        new_obj = 0;

    *pnew_obj = (WORD)(new_obj | orword);
    return cont;
}

/* Run the dialog until an EXIT or TOUCHEXIT object is chosen; returns it.
 * start_fld is the field to put the cursor in, 0 for the first. */
WORD fm_do(OBJECT FAR *tree, WORD start_fld)
{
    WORD edit_obj, next_obj, which, cont, idx;
    WORD rets[6];

    fm_own(TRUE);
    ev_fq();
    gsx_sclip(&gl_rfull);

    next_obj = fm_inifld(tree, start_fld);
    edit_obj = 0;

    cont = TRUE;
    while (cont) {
        /* the cursor onto the field being edited */
        if (next_obj != 0 && edit_obj != next_obj) {
            edit_obj = next_obj;
            next_obj = 0;
            ob_edit(tree, edit_obj, 0, &idx, EDINIT);
        }

        which = ev_multi(MU_KEYBD | MU_BUTTON, 0, 0, 0, 0x0002FF01UL,
                         0, rets);

        if (which & MU_KEYBD) {
            cont = fm_keybd(tree, edit_obj, &rets[4], &next_obj);
            if (rets[4])
                ob_edit(tree, edit_obj, rets[4], &idx, EDCHAR);
        }

        if (which & MU_BUTTON) {
            next_obj = ob_find(tree, ROOT, MAX_DEPTH, rets[0], rets[1]);
            if (next_obj == NIL) {
                /* GEM rings the bell here; there is no bell yet */
                next_obj = 0;
            } else {
                cont = fm_button(tree, next_obj, rets[5], &next_obj);
            }
        }

        /* leaving the field: take the cursor away */
        if (!cont || (next_obj != 0 && next_obj != edit_obj))
            ob_edit(tree, edit_obj, 0, &idx, EDEND);
    }

    fm_own(FALSE);
    return next_obj;
}

/* The visual effects around a dialog: FMD_GROW/FMD_SHRINK animate a box
 * between pi (the icon, say) and pt (the dialog); FMD_FINISH redraws what
 * the dialog covered; FMD_START reserves the screen. */
WORD fm_dial(WORD fmd_type, const GRECT *pi, const GRECT *pt)
{
    GRECT c;

    gsx_sclip(&gl_rscreen);
    switch (fmd_type) {
    case FMD_START:
        break;
    case FMD_GROW:
        gr_growbox(pi, pt);
        break;
    case FMD_SHRINK:
        gr_shrinkbox(pi, pt);
        break;
    case FMD_FINISH:
        /* the desktop under the dialog, then WM_REDRAW to every window
         * the dialog covered; w_update clips its rectangle in place */
        w_drawdesk(pt);
        c = *pt;
        w_update(DESKWH, &c, DESKWH, FALSE);
        break;
    }
    return TRUE;
}

/* ---- the AES entry points ------------------------------------------- */

WORD form_do(OBJECT FAR *tree, WORD start)
{
    return fm_do(tree, start);
}

WORD form_dial(WORD type, const GRECT *pi, const GRECT *pt)
{
    return fm_dial(type, pi, pt);
}

WORD form_keybd(OBJECT FAR *tree, WORD obj, WORD *pchar, WORD *pnew_obj)
{
    gsx_sclip(&gl_rfull);
    return fm_keybd(tree, obj, pchar, pnew_obj);
}

WORD form_button(OBJECT FAR *tree, WORD new_obj, WORD clks, WORD *pnew_obj)
{
    gsx_sclip(&gl_rfull);
    return fm_button(tree, new_obj, clks, pnew_obj);
}
