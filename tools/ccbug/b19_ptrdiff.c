/* B19 -- a pointer DIFFERENCE against a far array emits the array's
 * address as a bare 16-bit immediate, which the linker cannot satisfy.
 *
 * Under --data-model=large an ordinary global lives in far memory.  The
 * difference `p - arr` only needs the 16-bit offset, because a far
 * pointer's arithmetic is 16-bit within its bank -- so subtracting the
 * LOW WORD of the array's address is the right instruction.  What the
 * compiler emits is
 *
 *      sec
 *      lda     dp:.tiny _Dp        ; p, low word
 *      sbc     ##arr               ; <-- the WHOLE address in 16 bits
 *
 * and `##arr` asks the linker for a 16-bit immediate holding a symbol
 * that is not in the first 64 KB.  It refuses, correctly:
 *
 *      symbol 'arr' referenced from section 'farcode' at offset ...:
 *      value 542819 is out of range, allowed range is -32768 to 65535
 *
 * `##.word0 arr` is the instruction that was wanted, and it is what the
 * compiler already emits everywhere it loads a far address as a VALUE
 * (`lda ##.word0 sym` / `ldx ##.word2 sym`).  Only the difference gets it
 * wrong.
 *
 * FOUND BY: qed, porting to gem4xe.  Three of its globals tripped it --
 * two 11-byte char arrays and a 12 KB struct array -- and a cast to an
 * integer type does NOT help: `(unsigned long)p - (unsigned long)arr`
 * folds back to the same 16-bit subtraction with the same immediate.  The
 * workarounds are to put the array in bank $00 (`__near`, only affordable
 * for a small one) or to avoid the subtraction entirely, which for qed
 * meant recovering an index by comparing pointers instead.
 *
 * The shape is ordinary C -- `idx = ptr - array` is how you turn a
 * pointer back into a subscript -- so any program ported to the large
 * data model can meet it, and it fails at LINK time in a message that
 * names the symbol rather than the line.
 */

/* Big enough that nothing folds it away, and `extern` so the compiler
 * cannot see a definition and constant-fold the difference. */
extern char arr[4096];

short b19_index(const char *p)
{
    return (short)(p - arr);
}

/* The same shape through an integer cast, which does not help. */
short b19_index_cast(const char *p)
{
    return (short)(((unsigned long)(const void *)p
                    - (unsigned long)(const void *)arr));
}
