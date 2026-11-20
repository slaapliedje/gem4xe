/* C10: --core 6502 only: "internal error: illegal instruction: BIT #255"
 * (BIT immediate is a 65C02 instruction); --core 65c02 compiles it. */
void alert(void);
int x;
void f(void) { if ((x, -1) < 0) alert(); }
