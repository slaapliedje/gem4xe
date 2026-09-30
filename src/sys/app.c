/* app.c -- the G4A loader.  See app.h; the format is tools/mkg4a.py's. */
#include "portab.h"
#include <string.h>
#include "sys/app.h"
#include "sys/abi.h"
#include "sys/cio.h"
#include "sys/dos.h"
#include "sys/gemdos.h"
#include "vdi/vdi.h"
#include "sys/farmem.h"
#include "sys/ctx.h"

/* The pool's bounds, from the linker (src/sys/apppool.s). */
extern const uint16_t app_pool_lo, app_pool_hi;

static uint16_t pool_brk;       /* 0 until the first take: then the cursor */

/* Where the last program's near region went.  A gate that wants to read a
 * program's own variables has to know where the loader put them, and it
 * used to be able to assume the bottom of the pool -- the first thing
 * loaded was the first program.  An accessory is loaded before it
 * (src/aes/shel.c), so the assumption became quietly wrong: test-boot's
 * model placed the desktop on top of the accessory and still matched,
 * because a picture does not depend on where the bss is. */
uint16_t app_near;

/* AND WHERE ITS FAR IMAGE WENT, for the same reason.  A --data-model=
 * large program keeps its globals in far bss, not in the near region, so
 * app_near no longer finds them: a gate relocates a far link address L as
 * ((app_far >> 16) + (L >> 16) - link_bank) << 16 | (L & 0xFFFF), with
 * link_bank read from the .g4a header (byte 14).  The desktop became such
 * a program on 2026-09-19 and every gate that reads its G needs this. */
uint32_t app_far;
uint32_t app_vars;
uint8_t  app_vlink;

/* THE FLOOR.  Nothing may be released below this, and what puts things
 * under it is pool_keep_mark(): "everything taken so far is permanent."
 *
 * It exists because the pool's discipline was a rule in a comment and
 * the machine had no way to keep it.  An accessory is loaded before the
 * first program precisely so that the program's exit -- which winds the
 * pool back to where the program's load found it -- cannot take the
 * accessory with it (src/aes/shel.c).  That is correct, and it was also
 * unenforced: load an accessory a moment later and the first program to
 * exit would free it, silently, and the machine would run on with a
 * process whose variables belonged to somebody else.
 *
 * Now a release that would cross the floor is refused and counted.
 * pool_refused is a number nobody should ever see; test-boot reads it. */
static uint16_t pool_low;
uint16_t pool_refused;

uint16_t pool_mark(void)
{
    if (!pool_brk) {
        pool_brk = app_pool_lo;
        pool_low = app_pool_lo;
    }
    return pool_brk;
}

/* Everything taken so far is permanent. */
void pool_keep_mark(void)
{
    pool_low = pool_mark();
}

uint16_t pool_floor(void)
{
    (void)pool_mark();
    return pool_low;
}

void *pool_alloc(uint16_t size, uint16_t align)
{
    uint16_t base = pool_mark();
    uint16_t mask = (uint16_t)(align - 1);
    base = (uint16_t)((base + mask) & ~mask);
    if (base < pool_brk || (uint32_t)base + size > app_pool_hi)
        return 0;
    pool_brk = (uint16_t)(base + size);
    return (void *)base;
}

void pool_release(uint16_t mark)
{
    if (mark < pool_floor()) {
        pool_refused++;         /* somebody else's memory: see pool_low */
        return;
    }
    pool_brk = mark;
}

uint16_t pool_room(void)
{
    return (uint16_t)(app_pool_hi - pool_mark());
}

#define HDR_SIZE 32

/* -- READING THE BLOB.
 *
 * Every one of these takes the blob as an ADDRESS and not as a pointer,
 * and that is the whole of what an application bigger than a bank costs
 * the loader.  A FAR POINTER'S ARITHMETIC IS SIXTEEN BITS here: `p + n`
 * adds to the offset and leaves the bank byte alone, so a pointer walked
 * off the top of a bank comes back at its bottom (src/sys/farmem.c has
 * the generated code).  Below 64 KB that never showed, because nothing
 * far_alloc hands out crosses a bank and every file gem4xe had loaded was
 * a few KB.  GACS's GEM shell is 139 KB, and the whole of it -- the blob
 * on the way in, the image on the way out, and every fixup offset -- is
 * past where a 16-bit walk stays right. */
static uint8_t rd8(uint32_t at)
{
    return far_read8(at);
}

static uint16_t rd16(uint32_t at)
{
    return (uint16_t)(far_read8(at) | ((uint16_t)far_read8(at + 1) << 8));
}

/* A v2 far fixup offset: three bytes, so that a far image may be bigger
 * than a bank (tools/mkg4a.py). */
static uint32_t rd24(uint32_t at)
{
    return (uint32_t)far_read8(at)
         | ((uint32_t)far_read8(at + 1) << 8)
         | ((uint32_t)far_read8(at + 2) << 16);
}

static uint32_t rd32(uint32_t at)
{
    return (uint32_t)rd16(at) | ((uint32_t)rd16(at + 2) << 16);
}

static int16_t app_load_as(const uint8_t FAR *blob, uint32_t len, APP *app,
                           uint8_t own);

/* A new owner for the program, its far blocks taken as that owner, and
 * the one before put back: whatever app_load takes is the program's, and
 * app_free gives every piece back at once (phase 79). */
int16_t app_load(const uint8_t FAR *blob, uint32_t len, APP *app)
{
    uint8_t own = far_new_owner(), keep = far_owner;
    int16_t st;

    if (!own) {
        memset(app, 0, sizeof *app);
        return APP_E_FAR;
    }
    far_owner = own;
    st = app_load_as(blob, len, app, own);
    far_owner = keep;
    if (st != APP_OK)
        far_free_owner(own);
    return st;
}

/* FORMAT 5: A PACKED PROGRAM (phase 80, tools/mkg4a.py write_v5).
 *
 * Its code and its far variables are placed APART, each at any page of
 * any bank: the code where far_alloc_page finds room under the $D5 page,
 * the variables where it finds room in one bank.  So a 3 KB accessory
 * takes 3 KB and a few hundred bytes, not the two whole banks formats 3
 * and 4 give every program -- which is what made the far heap run out on
 * a 1 MB machine (docs/phase78.md).  Fourteen fixup lists, not four: for
 * each part, the references to the near region, and to the code and to
 * the variables -- a whole 24-bit address, its page byte or its bank
 * byte alone -- delta-coded, which keeps the file no bigger than format
 * 3 (docs/phase80.md).  A page
 * fixup adds to an address's middle byte and cannot carry: the code ends
 * under $D500 wherever it goes, and the variables inside their bank. */
#define HDR_V5 48

static int16_t app_load_v5(uint32_t b, uint32_t len, APP *app)
{
    uint16_t near_size, code_off, vars_off, k, l, n, o;
    uint32_t code_size, vars_size, entry, code, vars, at, end;
    uint8_t  code_link, vars_link, first, second, d[5];
    uint8_t *near;

    if (len < HDR_V5)
        return APP_E_SHORT;
    app->link_near = rd16(b + 4);
    near_size      = rd16(b + 6);
    code_off       = rd16(b + 8);
    code_size      = rd32(b + 10);
    code_link      = rd8(b + 14);
    vars_link      = rd8(b + 15);
    entry          = rd32(b + 16) & 0xFFFFFFUL;
    vars_off       = rd16(b + 20);
    vars_size      = rd32(b + 24);
    if ((uint32_t)HDR_V5 + near_size + code_size > len
        || code_size > 0xD500UL || vars_size > 0x10000UL)
        return APP_E_SHORT;

    app->pool_mark = pool_mark();
    near = pool_alloc(near_size, 0x100);
    if (!near)
        return APP_E_POOL;
    app->near_base = (uint16_t)near;
    app_near = app->near_base;
    app->near_size = near_size;
    code = far_alloc_page(code_size, 0xD500UL);
    vars = vars_size ? far_alloc_page(vars_size, 0x10000UL) : 0;
    if (!code || (vars_size && !vars)) {
        pool_release(app->pool_mark);
        return APP_E_FAR;               /* app_load frees the owner's blocks */
    }
    app->far_addr = code;
    app->far_size = code_size;
    app->link_bank = code_link;
    app->vars_addr = vars;
    app->vars_link = vars_link;
    app_far = code;
    app_vars = vars;
    app_vlink = vars_link;

    for (k = 0; k < near_size; k++)
        near[k] = rd8(b + HDR_V5 + k);
    far_copy_span(code, b + HDR_V5 + near_size, code_size);

    /* near page, code bank, code page, vars bank, vars page */
    d[0] = (uint8_t)((app->near_base - app->link_near) >> 8);
    d[1] = (uint8_t)((code >> 16) - code_link);
    d[2] = (uint8_t)(((code & 0xFFFFUL) - code_off) >> 8);
    d[3] = (uint8_t)(vars ? (vars >> 16) - vars_link : 0);
    d[4] = (uint8_t)(vars ? ((vars & 0xFFFFUL) - vars_off) >> 8 : 0);
    /* Fourteen lists, seven a part (tools/mkg4a.py, V5_LISTS): near page;
     * code long, page, bank; vars long, page, bank.  A LONG entry is a
     * 24-bit address's middle byte, its bank byte after it.  Each list is
     * a count and deltas: a byte 1..255, or 0 and the offset itself. */
    at = b + HDR_V5 + near_size + code_size;
    end = b + len;
    app->fixups = 0;
    for (l = 0; l < 14; l++) {
        uint16_t kind = (uint16_t)(l % 7);
        uint16_t size = l < 7 ? near_size : (uint16_t)code_size;
        first = kind == 0 ? d[0] : kind == 3 ? d[1] : kind == 6 ? d[3]
              : kind <= 2 ? d[2] : d[4];
        second = kind == 1 ? d[1] : kind == 4 ? d[3] : 0;
        if (at + 2 > end)
            return APP_E_SHORT;
        n = rd16(at);
        at += 2;
        o = 0;
        for (k = 0; k < n; k++) {
            uint8_t step = rd8(at++);
            if (step)
                o = (uint16_t)(o + step);
            else {
                o = rd16(at);
                at += 2;
            }
            if (at > end || o >= size || (second && o + 1 >= size))
                return APP_E_FIXUP;
            if (l < 7) {
                near[o] = (uint8_t)(near[o] + first);
                if (second)
                    near[o + 1] = (uint8_t)(near[o + 1] + second);
            } else {
                far_write8(code + o, (uint8_t)(far_read8(code + o) + first));
                if (second)
                    far_write8(code + o + 1,
                               (uint8_t)(far_read8(code + o + 1) + second));
            }
        }
        app->fixups = (uint16_t)(app->fixups + n);
    }
    app->entry = entry + ((uint32_t)d[1] << 16) + ((uint32_t)d[2] << 8);
    return APP_OK;
}

static int16_t app_load_as(const uint8_t FAR *blob, uint32_t len, APP *app,
                           uint8_t own)
{
    uint16_t near_size, far_off, n_nhi, n_nbank, n_fhi, n_fbank, k;
    uint32_t far_size, need, lists, entry, b, far;
    uint8_t  far_banks, dpage, dbank, fw;
    uint16_t bank;
    uint8_t *near;

    memset(app, 0, sizeof *app);     /* a failed load reports zeros */
    b = (uint32_t)blob;              /* an address: see rd8 above */
    if (len < HDR_SIZE)
        return APP_E_SHORT;
    if (rd8(b) != 'G' || rd8(b + 1) != '4' || rd8(b + 2) != 'A')
        return APP_E_MAGIC;
    /* Formats 1 and 2 are programs built for the first COP signatures --
     * $73, $C8 and $01 -- which gem4xe no longer answers ($01 is Rapidus
     * OS's own, src/sys/abi.h).  They are refused by name, so the shell
     * can say to rebuild rather than start a program whose first call
     * goes nowhere. */
    if (rd8(b + 3) == 1 || rd8(b + 3) == 2)
        return APP_E_OLDSDK;
    if (rd8(b + 3) == 5) {
        app->owner = own;           /* app_free frees by it: without this
                                     * every packed program's blocks outlived
                                     * it (m17 caught the desktop's) */
        return app_load_v5(b, len, app);
    }
    if (rd8(b + 3) != 3 && rd8(b + 3) != 4)
        return APP_E_MAGIC;
    /* The ONE difference between 3 and 4, as between 1 and 2 before them:
     * how wide a far fixup offset is.  3's u16 caps the far image at a
     * bank, which every program in this tree but GACS's shell fits inside;
     * 4 writes three bytes and does not.  The near lists are u16 in both,
     * because the near region is a page-aligned slice of a bank-$00 pool
     * and cannot be bigger than the bank. */
    fw = (uint8_t)(rd8(b + 3) == 4 ? 3 : 2);
    app->link_near = rd16(b + 4);
    near_size      = rd16(b + 6);
    far_off        = rd16(b + 8);
    far_size       = rd32(b + 10);
    app->link_bank = rd8(b + 14);
    far_banks      = rd8(b + 15);
    entry          = rd32(b + 16) & 0xFFFFFFUL;
    n_nhi   = rd16(b + 20);
    n_nbank = rd16(b + 22);
    n_fhi   = rd16(b + 24);
    n_fbank = rd16(b + 26);
    lists = HDR_SIZE + near_size + far_size;
    need = lists + 2UL * ((uint32_t)n_nhi + n_nbank)
                 + (uint32_t)fw * ((uint32_t)n_fhi + n_fbank);
    if (need > len)
        return APP_E_SHORT;

    /* A place for each part.  Both allocators are marked first so a
     * failure part-way leaves nothing taken. */
    app->pool_mark = pool_mark();
    app->owner = own;
    near = pool_alloc(near_size, 0x100);
    if (!near)
        return APP_E_POOL;
    app->near_base = (uint16_t)near;
    app_near = app->near_base;      /* for a gate to find it: see above */
    app->near_size = near_size;
    bank = far_alloc_banks(far_banks);
    if (!bank) {
        pool_release(app->pool_mark);
        return APP_E_FAR;
    }
    app->far_addr = ((uint32_t)bank << 16) | far_off;
    app_far = app->far_addr;        /* for a gate to find it: see above */
    app->far_size = far_size;

    /* The bytes, then the patches.  A near address moves by whole pages
     * and a far one by whole banks, so each fixup is one byte plus a
     * constant: the high byte of a near address by the page difference,
     * the bank byte of a far address by the bank difference. */
    near = (uint8_t *)app->near_base;
    far = app->far_addr;
    for (k = 0; k < near_size; k++)
        near[k] = rd8(b + HDR_SIZE + k);
    /* far_copy_span, not memcpy_far: the image may be bigger than a bank
     * and so may the blob, and memcpy_far takes a size_t -- SIXTEEN BITS
     * here, gem4xe being built --data-model=small.  A 115 KB image would
     * have been copied modulo 65,536 with nothing saying so: the loader
     * would report success, every fixup would apply, and the program
     * would run into whatever was left of the previous tenant partway
     * through. */
    far_copy_span(far, b + HDR_SIZE + near_size, far_size);

    dpage = (uint8_t)((app->near_base - app->link_near) >> 8);
    dbank = (uint8_t)(bank - app->link_bank);
    app->fixups = 0;
    {
        uint32_t l = b + lists;
        for (k = 0; k < n_nhi; k++, l += 2) {
            uint16_t o = rd16(l);
            if (o >= near_size)
                return APP_E_FIXUP;
            near[o] += dpage;
        }
        for (k = 0; k < n_nbank; k++, l += 2) {
            uint16_t o = rd16(l);
            if (o >= near_size)
                return APP_E_FIXUP;
            near[o] += dbank;
        }
        /* far + o, computed as an address rather than walked: past 64 KB
         * of image a far pointer's own arithmetic would wrap back to the
         * bottom of its bank and patch the wrong byte. */
        for (k = 0; k < n_fhi; k++, l += fw) {
            uint32_t o = (fw == 3) ? rd24(l) : rd16(l);
            if (o >= far_size)
                return APP_E_FIXUP;
            far_write8(far + o, (uint8_t)(far_read8(far + o) + dpage));
        }
        for (k = 0; k < n_fbank; k++, l += fw) {
            uint32_t o = (fw == 3) ? rd24(l) : rd16(l);
            if (o >= far_size)
                return APP_E_FIXUP;
            far_write8(far + o, (uint8_t)(far_read8(far + o) + dbank));
        }
        app->fixups = (uint16_t)(n_nhi + n_nbank + n_fhi + n_fbank);
    }
    app->entry = entry + ((uint32_t)dbank << 16);
    return APP_OK;
}

/* The program runs as its own owner, in whatever context runs it: record
 * 0 for the desktop, a program, a Pexec child, an AUTO program or a
 * control panel module.  A switch to an accessory and back sets
 * far_owner from the context (src/sys/ctx.c), so the owner lives there. */
int16_t app_exec(const APP *app)
{
    uint16_t keep = ctx_cur->owner;
    int16_t r;

    ctx_cur->owner = app->owner;
    far_owner = (uint8_t)app->owner;
    r = app_run(app->entry);
    ctx_cur->owner = keep;
    far_owner = (uint8_t)keep;
    return r;
}

void app_free(const APP *app)
{
    gemdos_release();               /* its handles, searches and DTA */
    vdi_close_virtuals();           /* its workstations */
    pool_release(app->pool_mark);
    far_free_owner((uint8_t)app->owner); /* and everything it Malloc'd */
}

/* The file, in pieces the size of a slice of the pool (2 KB when the pool
 * has it, sixty-four bytes of stack when it does not -- src/sys/gemdos.c
 * reads the same way), each piece taken from the far heap as it arrives:
 * the heap is a bump allocator and the pieces are whole multiples of its
 * alignment, so they make one extent, which is checked rather than
 * assumed.  CIO hands back fewer bytes than asked only at the end of the
 * file, and a status of EOF there still delivers the bytes before it
 * (src/sys/cio.h).  It says why as well as whether (src/sys/app.h): a
 * file that opened and then failed partway used to come back as the
 * APP_E_FILE a missing one does, and the shell tells the user a missing
 * application "cannot be found" -- so a disk error mid-read reported a
 * file that was plainly there as not existing, with nothing to say how
 * far the read had got. */
int16_t far_read_file(const char *cioname, uint32_t *addr, uint32_t *len)
{
    uint8_t small[64], *slice = 0;
    uint16_t n = 0, got, mark;
    uint32_t start, at, total = 0;
    uint16_t st;                        /* not a byte: B8, tools/ccbug */
    int16_t fd, rc = APP_OK;

    uint32_t room;

    *addr = 0;
    *len = 0;
    /* CIO cannot say how long a file is, so the read takes the largest
     * free extent there is and gives back what it did not fill: one
     * extent, in any bank, and a file as big as the free memory reads
     * (phase 79; the bump heap took it a piece at a time from the top). */
    room = far_largest(1) & ~3UL;
    if (!room)
        return APP_E_FAR;
    fd = cio_open(cioname, CIO_A_READ, 0);
    if (fd < 0)
        return APP_E_FILE;
    start = far_alloc_span(room);
    if (!start) {
        cio_close(fd);
        return APP_E_FAR;
    }
    mark = pool_mark();
    n = pool_room();
    n = n > 2048 ? 2048 : (uint16_t)(n & ~3);
    if (n >= 128)
        slice = pool_alloc(n, 4);
    if (!slice) {
        slice = small;
        n = sizeof small;
    }
    for (;;) {
        st = cio_read(fd, slice, n, &got);
        if (got > n)
            got = n;
        if (st != CIO_OK && st != CIO_OK_EOF && st != CIO_E_EOF) {
            rc = APP_E_READ;            /* a real error, partway */
            break;
        }
        if (got) {
            /* far_alloc_span, not far_alloc: the pieces have to make ONE
             * extent and far_alloc will not cross a bank -- it skips to
             * the next, so a file bigger than the room left in this one
             * broke the `at != start + total` check below and came back
             * as APP_E_FILE, which reads like a missing file.  The blob
             * is only ever reached through a far pointer (app_load), so
             * crossing costs it nothing. */
            at = start + total;
            if (total + got > room) {   /* bigger than the memory there is */
                rc = APP_E_FAR;
                break;
            }
            /* _span: this block came from far_alloc_span and a 2 KB
             * slice of it can straddle a bank, where a far pointer's
             * own increment would wrap to the bottom of that bank. */
            far_put_span(at, slice, got);
            total += got;
        }
        if (got < n || st != CIO_OK)
            break;
    }
    cio_close(fd);
    if (slice != small)
        pool_release(mark);
    *len = total;                       /* how far it got, a failure included */
    if (rc == APP_OK && !total)
        rc = APP_E_SHORT;               /* an empty file */
    if (rc != APP_OK) {
        far_free(start);                /* nothing is kept */
        return rc;
    }
    far_shrink(start, total);           /* the rest is free again */
    *addr = start;
    return APP_OK;
}

int16_t app_load_file(const char *gemname, APP *app)
{
    char cio[CIO_NAME_MAX + 1];
    uint32_t blob, len;
    uint8_t own = far_new_owner(), keep = far_owner;
    int16_t st;

    memset(app, 0, sizeof *app);
    if (!own)
        return APP_E_FAR;
    dos_cioname(gemname, cio);
    far_owner = own;
    st = far_read_file(cio, &blob, &len);
    if (st == APP_OK) {
        st = app_load_as((const uint8_t FAR *)blob, len, app, own);
        /* The file has been copied into place and patched, and nothing
         * reads it again: its memory is free now rather than at the
         * program's end, which the bump heap could not do. */
        far_free(blob);
    }
    far_owner = keep;
    if (st != APP_OK)
        far_free_owner(own);
    return st;
}
