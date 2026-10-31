#!/usr/bin/env python3
"""The bank-$00 pool's rules (src/sys/pool.c), in Python.

tests/host/test_pool.py runs one script of requests through pool.c in the
compiler's simulator and through this, and every answer must agree.  The
rules, as src/sys/pool.h states them:

  alloc(n, a)    at the top, always
  take(n, a)     the lowest gap it fits, below the first block, between
                 two or above the last
  release(m)     the current owner's blocks at or above m go, one of its
                 blocks straddling m ends at m; refused under the floor
  free(p)        one block, by its address
  free_owner(o)  every block of o; o == 0 is the system's and does nothing
  free_sub(o, s) every block of o in sub-pool s, 1-15 (the tag's low
                 nibble: far_tag, src/sys/farmem.h)
  room()         above the top

A zero-sized alloc or take is a place, not a block.
"""


class Pool:
    def __init__(self, lo, hi, slots=32):
        self.lo, self.hi, self.slots = lo, hi, slots
        self.blocks = []            # [at, len, owner, tag], sorted by at
        self.owner = 0
        self.tag = 0
        self.low = lo
        self.refused = 0
        self.full = 0

    def top(self):
        return self.blocks[-1][0] + self.blocks[-1][1] if self.blocks else self.lo

    mark = top

    @staticmethod
    def _fit(lo, hi, n, a):
        base = (lo + a - 1) & ~(a - 1) & 0xFFFF
        if base < lo or base + n > hi:
            return 0
        return base

    def _insert(self, i, at, n):
        if len(self.blocks) >= self.slots:
            self.full += 1
            return 0
        self.blocks.insert(i, [at, n, self.owner, self.tag])
        return at

    def alloc(self, n, a):
        base = self._fit(self.top(), self.hi, n, a)
        if not base or not n:
            return base
        return self._insert(len(self.blocks), base, n)

    def take(self, n, a):
        if not n:
            return self.alloc(n, a)
        lo = self.lo
        for i in range(len(self.blocks) + 1):
            hi = self.blocks[i][0] if i < len(self.blocks) else self.hi
            base = self._fit(lo, hi, n, a)
            if base:
                return self._insert(i, base, n)
            if i < len(self.blocks):
                lo = self.blocks[i][0] + self.blocks[i][1]
        return 0

    def keep_mark(self):
        self.low = self.top()

    def release(self, m):
        if m < self.low:
            self.refused += 1
            return
        kept = []
        for at, n, own, tag in self.blocks:
            if own == self.owner and at >= m:
                continue
            if own == self.owner and at + n > m:
                n = m - at
            kept.append([at, n, own, tag])
        self.blocks = kept

    def free(self, p):
        for i, (at, _, _, _) in enumerate(self.blocks):
            if at == p:
                del self.blocks[i]
                return 1
        return 0

    def free_owner(self, o):
        if o:
            self.blocks = [b for b in self.blocks if b[2] != o]

    def free_sub(self, o, s):
        if o and s:
            self.blocks = [b for b in self.blocks
                           if not (b[2] == o and b[3] & 0x0F == s)]

    def room(self):
        return self.hi - self.top()
