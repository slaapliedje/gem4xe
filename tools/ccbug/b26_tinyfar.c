/* B26 -- a FAR pointer that lives in the direct page, indexed by a
 * variable, is dereferenced as a 16-bit pointer:
 *
 *   put_var:   tay ; sta (.tiny p),y       ; the data bank's, not p's
 *   put_const: ldy ##68 ; sta [.tiny p],y  ; right
 *
 * `(dp),y` takes the bank from the data bank register, so the store
 * lands in bank $00 (or wherever DBR is) at p's low sixteen bits plus
 * the index, and the read reads from there.  A constant index is right,
 * and so is a local copy of the pointer.  Every -O level, and the small
 * and large data models alike: the pointer is declared __far.  Met in
 * src/desk/deskcmd.c, where the viewer's path was written through
 * cmd_buf and never arrived -- and went to bank $00's page 0 instead.
 *
 * This file is compiled alone and its ASSEMBLY read (check.py): the
 * defect is the addressing mode, which is plain in the output. */
char __far * __attribute__((tiny)) b26_p;

void b26_put_var(int i, char c) { b26_p[i] = c; }          /* the bug */
char b26_get_var(int i) { return b26_p[i]; }               /* the bug */
void b26_put_const(char c) { b26_p[68] = c; }              /* right */
char b26_get_local(int i)                                  /* the shape */
{
    char __far *q = b26_p;                                 /* to write */

    return q[i];
}
