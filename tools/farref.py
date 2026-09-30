"""The far allocator (src/sys/farmem.c, "THE ALLOCATOR"), as a model.

The same rules, step for step, so that a gate can say where the target
put something without reading it back -- the desktop's file, its code
banks and its resource, which the desktop model's G carries addresses of
(tests/emu/m17_desktop.py, desk_places).  tests/host/test_farmem.py runs
one script of requests through this and through farmem.c in the
compiler's simulator, and the two must agree on every address.

A block is (address, length, owner), the table sorted by address; free
space is what lies between.  Block 0 is the table itself, at the foot of
the heap, 2 KB, the system's.
"""

FB_MAX = 256
FB_SIZE = 8
TABLE = FB_MAX * FB_SIZE


def up4(n):
    return (n + 3) & ~3


class Heap:
    def __init__(self, first_bank, last_bank):
        self.lo = first_bank << 16
        self.hi = (last_bank + 1) << 16
        self.owner = 0
        self.blocks = [(self.lo, TABLE, 0)]

    @classmethod
    def from_table(cls, first_bank, last_bank, entries):
        """The target's own table, read out of its memory: [(at, len)]
        with the owner in at's top byte, as farmem.c keeps it."""
        h = cls(first_bank, last_bank)
        h.blocks = [(at & 0xFFFFFF, ln, at >> 24) for at, ln in entries]
        return h

    # -- gaps ------------------------------------------------------------
    def _end(self, i):
        a, n, _ = self.blocks[i]
        return a + up4(n)

    def gap_lo(self, i):
        return self._end(i - 1) if i else self.lo

    def gap_hi(self, i):
        return self.blocks[i][0] if i < len(self.blocks) else self.hi

    def _insert(self, i, a, n):
        if len(self.blocks) >= FB_MAX:
            return 0
        self.blocks.insert(i, (a, n, self.owner))
        return a

    @staticmethod
    def _fit(lo, hi, n, how, limit):
        if how == 2:
            a = (lo + 0xFF) & ~0xFF
            if (a & 0xFFFF) + n > limit:
                a = (a | 0xFFFF) + 1
            if (a & 0xFFFF) + n > limit:
                return 0
        else:
            a = up4(lo)
            if how == 0 and (a & 0xFFFF) + n > 0x10000:
                a = (a | 0xFFFF) + 1
        if a < lo or a + n > hi:
            return 0
        return a

    def _take(self, n, how, limit=0):
        if n == 0 or (how == 0 and n > 0x10000):
            return 0
        for i in range(len(self.blocks) + 1):
            a = self._fit(self.gap_lo(i), self.gap_hi(i), n, how, limit)
            if a:
                return self._insert(i, a, n)
        return 0

    # -- the calls -------------------------------------------------------
    def alloc(self, n):
        return self._take(n, 0)

    def alloc_span(self, n):
        return self._take(n, 1)

    def alloc_page(self, n, limit):
        return self._take(n, 2, limit)

    def alloc_banks(self, k):
        n = k << 16
        if k == 0:
            return 0
        for i in range(len(self.blocks) + 1):
            a = (self.gap_lo(i) + 0xFFFF) & ~0xFFFF
            if a + n > self.gap_hi(i):
                continue
            if not self._insert(i, a, n):
                return 0
            return a >> 16
        return 0

    def _find(self, addr):
        for i, (a, _, _) in enumerate(self.blocks):
            if a == addr:
                return i
        return None

    def free(self, addr):
        i = self._find(addr)
        if not i:                       # None, or 0: the table
            return 0
        del self.blocks[i]
        return 1

    def free_owner(self, owner):
        if owner:
            self.blocks = [self.blocks[0]] + [b for b in self.blocks[1:]
                                              if b[2] != owner]

    def shrink(self, addr, n):
        i = self._find(addr)
        if not i or n == 0 or n > self.blocks[i][1]:
            return 0
        a, _, o = self.blocks[i]
        self.blocks[i] = (a, n, o)
        return 1

    def largest(self, span):
        best = 0
        for i in range(len(self.blocks) + 1):
            lo, hi = up4(self.gap_lo(i)), self.gap_hi(i)
            if hi <= lo:
                continue
            if span:
                n = hi - lo
            else:
                n, b = 0, lo
                while b < hi:
                    e = min((b | 0xFFFF) + 1, hi)
                    n = max(n, e - b)
                    b = e
            best = max(best, n)
        return best

    # -- what the shell does with it -------------------------------------
    def read_file(self, length):
        """far_read_file (src/sys/app.c): the largest span, filled, and
        shrunk to the file's length."""
        room = self.largest(1) & ~3
        a = self.alloc_span(room) if room else 0
        if not a or length > room:
            if a:
                self.free(a)
            return 0
        self.shrink(a, length)
        return a
