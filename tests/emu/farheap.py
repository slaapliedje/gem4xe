"""The target's far heap, read out of its memory for the models
(src/sys/farmem.c; tools/farref.py): shared by every gate that has to say
where the far heap stands before and after a run."""
import copy

import farref

RC_LEVEL = 2                    # src/aes/rsrc.c


def far_heap(b, syms):
    """The target's far heap, as the model holds one: the banks it spans
    and every block in its table, read out of its memory
    (src/sys/farmem.c, far_table/far_blocks; tools/farref.py)."""
    fm = bytes(b.memdump(syms["farmem"], 4))     # kind, first, last, banks
    n = b.peek16(syms["far_blocks"])
    t = int.from_bytes(bytes(b.memdump(syms["far_table"], 4)), "little")
    raw = bytes(b.memdump(t, n * farref.FB_SIZE)) if n else b""
    ents = [(int.from_bytes(raw[i * 8:i * 8 + 4], "little"),
             int.from_bytes(raw[i * 8 + 4:i * 8 + 8], "little"))
            for i in range(n)]
    h = farref.Heap.from_table(fm[1], fm[2], ents)
    # Purge level 2 is the AES's copies of the desktop's resource files
    # (src/aes/rsrc.c, phase 120): a cache, taken at the top of the heap so
    # that nothing the models place moves, and not one of their blocks.
    # The desktop's own program file is level 1 and stays.
    h.blocks = [blk for blk in h.blocks if (blk[2] >> 16) & 3 != RC_LEVEL]
    return h


def heap_then(before, after, desk_len, kept=()):
    """None if `after` is `before` with the desktop's file added -- what
    a desktop run leaves: the shell keeps the file, and everything the
    desktop took is freed with its owner (src/sys/app.c app_free) -- or
    what differs.  Addresses and lengths; owners are the target's to
    number."""
    want = copy.deepcopy(before)
    want.read_file(desk_len)
    # and what the AES kept of the desktop's (G4_DESKICON): the system's
    want.blocks = sorted(want.blocks + list(kept))
    # lengths as the allocator counts them, to the next four: the file's
    # block is its exact length, which a gate may have rounded
    w = [(a, farref.up4(n)) for a, n, _ in want.blocks]
    g = [(a, farref.up4(n)) for a, n, _ in after.blocks]
    if w == g:
        return None
    extra = [f"${a:06X}+{n}" for a, n in g if (a, n) not in w]
    gone = [f"${a:06X}+{n}" for a, n in w if (a, n) not in g]
    return f"blocks not in the model {extra}, and missing {gone}"


def heap_text(h):
    return f"{len(h.blocks)} blocks, largest gap {h.largest(1):,}"
