"""A 6502 for the host tests: the documented NMOS instructions, their flags
and their cycles (a taken branch +1, +1 more across a page; an indexed
read across a page +1), and nothing of the machine around it.  Enough to
run a routine of src/sys6502/ as the compiler calls it and count what it
costs; tests/host/test_g6z6502.py is its user.

    cpu = Cpu(mem)              # mem: a bytearray of 65,536
    cycles = cpu.call(addr)     # JSR there; returns when it RTSes

A BRK, or an opcode that is not a documented one, stops it with the
address: a routine that reaches one is wrong, not slow.
"""

SENTINEL = 0xFFF0


class Cpu:
    def __init__(self, mem):
        self.m = mem
        self.a = self.x = self.y = 0
        self.s = 0xFF
        self.c = self.z = self.i = self.d = self.v = self.n = 0
        self.pc = 0
        self.cycles = 0

    # ---- flags and the stack -------------------------------------------
    def p(self):
        return (self.n << 7 | self.v << 6 | 0x20 | 0x10 | self.d << 3
                | self.i << 2 | self.z << 1 | self.c)

    def setp(self, v):
        self.n, self.v = v >> 7 & 1, v >> 6 & 1
        self.d, self.i, self.z, self.c = v >> 3 & 1, v >> 2 & 1, v >> 1 & 1, v & 1

    def nz(self, v):
        self.z = int(v == 0)
        self.n = v >> 7
        return v

    def push(self, v):
        self.m[0x100 + self.s] = v & 0xFF
        self.s = (self.s - 1) & 0xFF

    def pull(self):
        self.s = (self.s + 1) & 0xFF
        return self.m[0x100 + self.s]

    def rd16(self, a):
        return self.m[a & 0xFFFF] | self.m[(a + 1) & 0xFFFF] << 8

    def zp16(self, a):
        return self.m[a & 0xFF] | self.m[(a + 1) & 0xFF] << 8

    # ---- running ---------------------------------------------------------
    def call(self, addr, limit=50_000_000):
        self.push((SENTINEL - 1) >> 8)
        self.push((SENTINEL - 1) & 0xFF)
        self.pc = addr
        start = self.cycles
        while self.pc != SENTINEL:
            self.step()
            if self.cycles - start > limit:
                raise AssertionError("runs away at $%04X" % self.pc)
        return self.cycles - start

    def adc(self, v):
        if self.d:
            raise AssertionError("decimal mode at $%04X" % self.pc)
        r = self.a + v + self.c
        self.v = int(~(self.a ^ v) & (self.a ^ r) & 0x80 != 0)
        self.c = r >> 8
        self.a = self.nz(r & 0xFF)

    def cmp(self, reg, v):
        r = reg - v
        self.c = int(r >= 0)
        self.nz(r & 0xFF)

    def step(self):
        m, pc = self.m, self.pc
        op = m[pc]
        e = OPS.get(op)
        if e is None:
            raise AssertionError("opcode $%02X at $%04X" % (op, pc))
        name, mode, cyc = e
        b1 = m[(pc + 1) & 0xFFFF]
        w = b1 | m[(pc + 2) & 0xFFFF] << 8
        extra = 0
        # the operand's address, and the instruction's length
        if mode == "imp" or mode == "acc":
            ln, ea = 1, None
        elif mode == "imm":
            ln, ea = 2, (pc + 1) & 0xFFFF
        elif mode == "zp":
            ln, ea = 2, b1
        elif mode == "zpx":
            ln, ea = 2, (b1 + self.x) & 0xFF
        elif mode == "zpy":
            ln, ea = 2, (b1 + self.y) & 0xFF
        elif mode == "abs":
            ln, ea = 3, w
        elif mode in ("abx", "aby"):
            r = self.x if mode == "abx" else self.y
            ln, ea = 3, (w + r) & 0xFFFF
            extra = int((w & 0xFF00) != (ea & 0xFF00))
        elif mode == "izx":
            ln, ea = 2, self.zp16(b1 + self.x)
        elif mode == "izy":
            base = self.zp16(b1)
            ln, ea = 2, (base + self.y) & 0xFFFF
            extra = int((base & 0xFF00) != (ea & 0xFF00))
        elif mode == "ind":
            lo = m[w]
            hi = m[(w & 0xFF00) | ((w + 1) & 0xFF)]      # the page wrap
            ln, ea = 3, lo | hi << 8
        elif mode == "rel":
            ln, ea = 2, (pc + 2 + (b1 - 256 if b1 & 0x80 else b1)) & 0xFFFF
        npc = (pc + ln) & 0xFFFF
        if name in ("STA", "STX", "STY") or mode not in ("abx", "aby", "izy") \
                or name in RMW:
            extra = 0                   # no page penalty: a store, a RMW
        self.cycles += cyc + extra

        def rd():
            return m[ea]

        if name == "LDA": self.a = self.nz(rd())
        elif name == "LDX": self.x = self.nz(rd())
        elif name == "LDY": self.y = self.nz(rd())
        elif name == "STA": m[ea] = self.a
        elif name == "STX": m[ea] = self.x
        elif name == "STY": m[ea] = self.y
        elif name == "ADC": self.adc(rd())
        elif name == "SBC": self.adc(rd() ^ 0xFF)
        elif name == "AND": self.a = self.nz(self.a & rd())
        elif name == "ORA": self.a = self.nz(self.a | rd())
        elif name == "EOR": self.a = self.nz(self.a ^ rd())
        elif name == "CMP": self.cmp(self.a, rd())
        elif name == "CPX": self.cmp(self.x, rd())
        elif name == "CPY": self.cmp(self.y, rd())
        elif name == "BIT":
            v = rd()
            self.z = int(self.a & v == 0)
            self.n, self.v = v >> 7 & 1, v >> 6 & 1
        elif name in RMW:
            v = self.a if mode == "acc" else m[ea]
            if name == "ASL":
                self.c, v = v >> 7, v << 1 & 0xFF
            elif name == "LSR":
                self.c, v = v & 1, v >> 1
            elif name == "ROL":
                self.c, v = v >> 7, (v << 1 | self.c) & 0xFF
            elif name == "ROR":
                self.c, v = v & 1, v >> 1 | self.c << 7
            elif name == "INC":
                v = (v + 1) & 0xFF
            elif name == "DEC":
                v = (v - 1) & 0xFF
            self.nz(v)
            if mode == "acc":
                self.a = v
            else:
                m[ea] = v
        elif name == "INX": self.x = self.nz((self.x + 1) & 0xFF)
        elif name == "INY": self.y = self.nz((self.y + 1) & 0xFF)
        elif name == "DEX": self.x = self.nz((self.x - 1) & 0xFF)
        elif name == "DEY": self.y = self.nz((self.y - 1) & 0xFF)
        elif name == "TAX": self.x = self.nz(self.a)
        elif name == "TAY": self.y = self.nz(self.a)
        elif name == "TXA": self.a = self.nz(self.x)
        elif name == "TYA": self.a = self.nz(self.y)
        elif name == "TSX": self.x = self.nz(self.s)
        elif name == "TXS": self.s = self.x
        elif name == "PHA": self.push(self.a)
        elif name == "PLA": self.a = self.nz(self.pull())
        elif name == "PHP": self.push(self.p())
        elif name == "PLP": self.setp(self.pull())
        elif name == "CLC": self.c = 0
        elif name == "SEC": self.c = 1
        elif name == "CLI": self.i = 0
        elif name == "SEI": self.i = 1
        elif name == "CLD": self.d = 0
        elif name == "SED": self.d = 1
        elif name == "CLV": self.v = 0
        elif name == "NOP": pass
        elif name in BRANCH:
            flag, want = BRANCH[name]
            if getattr(self, flag) == want:
                self.cycles += 1 + int((npc & 0xFF00) != (ea & 0xFF00))
                npc = ea
        elif name == "JMP": npc = ea
        elif name == "JSR":
            ret = (pc + 2) & 0xFFFF
            self.push(ret >> 8)
            self.push(ret & 0xFF)
            npc = ea
        elif name == "RTS":
            lo = self.pull()
            npc = ((self.pull() << 8 | lo) + 1) & 0xFFFF
        elif name == "RTI":
            self.setp(self.pull())
            lo = self.pull()
            npc = self.pull() << 8 | lo
        else:
            raise AssertionError("%s at $%04X" % (name, pc))
        self.pc = npc


RMW = {"ASL", "LSR", "ROL", "ROR", "INC", "DEC"}
BRANCH = {"BPL": ("n", 0), "BMI": ("n", 1), "BVC": ("v", 0), "BVS": ("v", 1),
          "BCC": ("c", 0), "BCS": ("c", 1), "BNE": ("z", 0), "BEQ": ("z", 1)}


def _table():
    t = {}

    def add(name, *codes):
        for code, mode, cyc in codes:
            t[code] = (name, mode, cyc)

    # the eight ALU instructions share a layout
    for name, base in (("ORA", 0x00), ("AND", 0x20), ("EOR", 0x40), ("ADC", 0x60),
                       ("STA", 0x80), ("LDA", 0xA0), ("CMP", 0xC0), ("SBC", 0xE0)):
        rows = [(0x01, "izx", 6), (0x05, "zp", 3), (0x09, "imm", 2), (0x0D, "abs", 4),
                (0x11, "izy", 5), (0x15, "zpx", 4), (0x19, "aby", 4), (0x1D, "abx", 4)]
        for off, mode, cyc in rows:
            if name == "STA":
                if mode == "imm":
                    continue
                cyc = {"izy": 6, "aby": 5, "abx": 5}.get(mode, cyc)
            add(name, (base + off, mode, cyc))
    for name, base in (("ASL", 0x00), ("ROL", 0x20), ("LSR", 0x40), ("ROR", 0x60)):
        add(name, (base + 0x0A, "acc", 2), (base + 0x06, "zp", 5), (base + 0x16, "zpx", 6),
            (base + 0x0E, "abs", 6), (base + 0x1E, "abx", 7))
    add("INC", (0xE6, "zp", 5), (0xF6, "zpx", 6), (0xEE, "abs", 6), (0xFE, "abx", 7))
    add("DEC", (0xC6, "zp", 5), (0xD6, "zpx", 6), (0xCE, "abs", 6), (0xDE, "abx", 7))
    add("LDX", (0xA2, "imm", 2), (0xA6, "zp", 3), (0xB6, "zpy", 4), (0xAE, "abs", 4),
        (0xBE, "aby", 4))
    add("LDY", (0xA0, "imm", 2), (0xA4, "zp", 3), (0xB4, "zpx", 4), (0xAC, "abs", 4),
        (0xBC, "abx", 4))
    add("STX", (0x86, "zp", 3), (0x96, "zpy", 4), (0x8E, "abs", 4))
    add("STY", (0x84, "zp", 3), (0x94, "zpx", 4), (0x8C, "abs", 4))
    add("CPX", (0xE0, "imm", 2), (0xE4, "zp", 3), (0xEC, "abs", 4))
    add("CPY", (0xC0, "imm", 2), (0xC4, "zp", 3), (0xCC, "abs", 4))
    add("BIT", (0x24, "zp", 3), (0x2C, "abs", 4))
    for name, code in (("BPL", 0x10), ("BMI", 0x30), ("BVC", 0x50), ("BVS", 0x70),
                       ("BCC", 0x90), ("BCS", 0xB0), ("BNE", 0xD0), ("BEQ", 0xF0)):
        add(name, (code, "rel", 2))
    add("JMP", (0x4C, "abs", 3), (0x6C, "ind", 5))
    add("JSR", (0x20, "abs", 6))
    for name, code, cyc in (("RTS", 0x60, 6), ("RTI", 0x40, 6), ("PHA", 0x48, 3),
                            ("PLA", 0x68, 4), ("PHP", 0x08, 3), ("PLP", 0x28, 4),
                            ("CLC", 0x18, 2), ("SEC", 0x38, 2), ("CLI", 0x58, 2),
                            ("SEI", 0x78, 2), ("CLD", 0xD8, 2), ("SED", 0xF8, 2),
                            ("CLV", 0xB8, 2), ("INX", 0xE8, 2), ("INY", 0xC8, 2),
                            ("DEX", 0xCA, 2), ("DEY", 0x88, 2), ("TAX", 0xAA, 2),
                            ("TAY", 0xA8, 2), ("TXA", 0x8A, 2), ("TYA", 0x98, 2),
                            ("TSX", 0xBA, 2), ("TXS", 0x9A, 2), ("NOP", 0xEA, 2)):
        add(name, (code, "imp", cyc))
    return t


OPS = _table()
