/* C9: inlining a function that returns a call on its local's address:
 * internal error in lookupVariable at -O1/-O2, cc6502 and cc65816 alike.
 * `take(&x); return x;` compiles. */
int take(int *a);
static int fwd(void) { int x; return take(&x); }
int f(void) { return fwd(); }
