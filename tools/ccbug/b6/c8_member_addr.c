/* C8: a member's address cast to an integer: internal error, any -O */
typedef struct { int a; int b; } S;
unsigned c8(void) { static S s; return (unsigned)&s.b; }
