"""The far allocator (src/sys/farmem.c, "THE ALLOCATOR"), as a model.

The same rules, step for step, so that a gate can say where the target
put something without reading it back -- the desktop's file, its code
banks and its resource, which the desktop model's G carries addresses of
(tests/emu/m17_desktop.py, desk_places).  tests/host/test_farmem.py runs
one script of requests through this and through farmem.c in the
compiler's simulator, and the two must agree on every address.

A block is (address, length, owner), the table sorted by address; free
space is what lies between.  The owner is the whole ID -- main | tag << 8
(phase 119) -- with the block's purge level in bits 16-17 (phase 120),
which farmem.c keeps in the address's low two bits.  Block 0 is the table itself, at the foot of
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
        self.owner = 0                  # far_owner: the main ID
        self.tag = 0                    # far_tag: kind << 4 | sub-pool
        self.purged = []                # what far_purge_hook was told
        self.blocks = [(self.lo, TABLE, 0)]

    @classmethod
    def from_table(cls, first_bank, last_bank, entries):
        """The target's own table, read out of its memory: [(at, len)]
        with the owner in at's top byte and its tag in len's, as farmem.c
        keeps them.  A block's owner here is the whole ID, main | tag << 8."""
        h = cls(first_bank, last_bank)
        h.blocks = [(at & 0xFFFFFC, ln & 0xFFFFFF,
                     (at >> 24) | (ln >> 24) << 8 | (at & 3) << 16)
                    for at, ln in entries]
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
        self.blocks.insert(i, (a, n, self.owner | self.tag << 8))
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

    # -- purging (phase 120) ---------------------------------------------
    def set_purge(self, addr, level):
        i = self._find(addr)
        if not i:
            return 0
        a, n, o = self.blocks[i]
        self.blocks[i] = (a, n, (o & 0xFFFF) | (level & 3) << 16)
        return 1

    def _purge_level(self, level):
        keep, n = [self.blocks[0]], 0
        for b in self.blocks[1:]:
            if (b[2] >> 16) & 3 == level:
                self.purged.append(b[0])
                n += 1
            else:
                keep.append(b)
        self.blocks = keep
        return n

    def _reclaiming(self, fn, *args):
        """A request, then GS/OS's order: level 3 purged and tried again,
        then 2, then 1, then refused."""
        level = 4
        while True:
            r = fn(*args)
            if r:
                return r
            while level > 1:
                level -= 1
                if self._purge_level(level):
                    break
            else:
                return 0

    # -- the calls -------------------------------------------------------
    def alloc(self, n):
        return self._reclaiming(self._take, n, 0)

    def alloc_span(self, n):
        return self._reclaiming(self._take, n, 1)

    def alloc_page(self, n, limit):
        return self._reclaiming(self._take, n, 2, limit)

    def alloc_top(self, n):
        return self._reclaiming(self._top1, n)

    def claim(self, at, n):
        return self._reclaiming(self._claim1, at, n)

    def alloc_banks(self, k):
        return self._reclaiming(self._banks1, k)

    def _top1(self, n):
        """far_alloc_top: the top of the highest gap it fits."""
        if n == 0:
            return 0
        for i in range(len(self.blocks), -1, -1):
            lo, hi = self.gap_lo(i), self.gap_hi(i)
            if hi - lo < n:
                continue
            a = (hi - n) & ~3
            if a < lo:
                continue
            return self._insert(i, a, n)
        return 0

    def _claim1(self, at, n):
        """far_claim: exactly at..at+n, or 0 if any of it is not free."""
        if n == 0:
            return 0
        end = at + n
        at &= ~3
        for i in range(len(self.blocks) + 1):
            if self.gap_hi(i) <= at:
                continue
            if self.gap_lo(i) > at or end > self.gap_hi(i):
                return 0
            return self._insert(i, at, end - at)
        return 0

    def _banks1(self, k):
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

    def keep(self, addr):
        """far_keep: the block at addr becomes the system's (owner 0)."""
        i = self._find(addr)
        if not i:
            return 0
        a, n, _ = self.blocks[i]
        self.blocks[i] = (a, n, 0)
        return 1

    def free_owner(self, owner):
        """Every block whose main ID is `owner`, whatever its tag."""
        if owner:
            self.blocks = [self.blocks[0]] + [b for b in self.blocks[1:]
                                              if b[2] & 0xFF != owner]

    def free_sub(self, owner, sub):
        """far_free_sub: one sub-pool, 1-15, of one owner."""
        if owner and sub:
            self.blocks = [self.blocks[0]] + [
                b for b in self.blocks[1:]
                if not (b[2] & 0xFF == owner and (b[2] >> 8) & 0x0F == sub)]

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
