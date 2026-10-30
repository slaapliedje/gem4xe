/* gstools.c -- the Tool Locator ($01), Memory Manager ($02), Misc Tools ($03).
 *
 * Each call is the routine of that number in the Apple IIGS Toolbox
 * Reference -- the Tool Locator in chapter 24, the Memory Manager in
 * chapter 12, Misc Tools in chapter 14 -- and takes its inputs off the
 * stack as the reference's "Stack before call" shows them: the last one
 * pushed is at p[0], the output space above all of them.  Only what
 * milestone 1's program uses is here; any other number is GS_NOTYET.
 *
 * THE MEMORY MANAGER, so far.  A handle is the address of a master
 * pointer, and the program dereferences it itself, so the master pointers
 * are real memory in bank $00.  A block asked for in bank $00 (attrBank
 * with a bank $00 location) comes from GSlayer's arena there, page-aligned
 * if attrPage says so; anything else is Malloc'd from gem4xe.  Nothing
 * moves, so every block behaves as locked and fixed -- which no program
 * can tell from a block that is, short of running out of memory.
 */
#include "gs.h"

#define attrBank    0x0001
#define attrAddr    0x0002
#define attrPage    0x0004

#define memErr      0x0201          /* "unable to allocate block" */

#define MP_MAX      64
static uint32_t mp[MP_MAX];         /* the master pointers: handles point here */
static uint32_t mp_size[MP_MAX];
static uint16_t mp_owner[MP_MAX];
static uint32_t mp_free[MP_MAX];    /* what to Mfree, 0 if not Malloc'd */
static uint16_t b0_used;
static uint32_t last_malloc;        /* gs_alloc's Malloc, before aligning */

/* Memory for the program: `size` bytes as `attr` and `where` ask (the
 * Memory Manager's attributes and location, Toolbox Reference chapter
 * 12), or 0. */
uint32_t gs_alloc(uint32_t size, uint16_t attr, uint32_t where)
{
    uint16_t at;
    LONG m;

    if (attr & attrAddr)
        return 0;                       /* a fixed address: not yet */
    last_malloc = 0;
    if ((attr & attrBank) && (where >> 16) == 0) {
        at = b0_used;
        if (attr & attrPage)
            at = (uint16_t)((at + 0xFF) & 0xFF00);
        if (size > gs_b0_size || at > gs_b0_size - (uint16_t)size)
            return 0;
        b0_used = (uint16_t)(at + (uint16_t)size);
        return (uint32_t)(uint16_t)(gs_b0 + at);
    }
    if ((attr & attrBank) && (where >> 16) != 0)
        return 0;                       /* a particular bank: not yet */
    m = Malloc((LONG)size + ((attr & attrPage) ? 0xFF : 0));
    if (m <= 0)
        return 0;
    last_malloc = (uint32_t)m;
    if (attr & attrPage)
        m = (m + 0xFF) & ~0xFFL;
    return (uint32_t)m;
}

/* A block that is already placed, made a handle: what the loader does with
 * each segment, as GS/OS's does (ORCA/C's start-up asks FindHandle for
 * its own code's).  The handle, or 0 if the table is full. */
uint32_t gs_handle(uint32_t blk, uint32_t size, uint16_t owner)
{
    uint16_t i;

    for (i = 0; i < MP_MAX && mp_size[i]; i++)
        ;
    if (i == MP_MAX)
        return 0;
    mp[i] = blk;
    mp_size[i] = size ? size : 1;
    mp_owner[i] = owner;
    mp_free[i] = 0;
    return (uint32_t)(uint16_t)&mp[i];
}

static int16_t slot(uint32_t h)
{
    uint16_t i;

    for (i = 0; i < MP_MAX; i++)
        if (mp_size[i] && (uint32_t)(uint16_t)&mp[i] == (h & 0xFFFFFFUL))
            return (int16_t)i;
    return -1;
}

/* $01: the Tool Locator */
uint16_t gs_tl(uint8_t fn, uint8_t *p)
{
    switch (fn) {
    case 0x02:                          /* TLStartUp */
    case 0x03:                          /* TLShutDown */
        return 0;
    case 0x04:                          /* TLVersion: word out */
        gs_putw(p, 0x0300);
        return 0;
    case 0x06:                          /* TLStatus: word out */
        gs_putw(p, 0xFFFF);
        return 0;
    }
    return GS_NOTYET;
}

/* $02: the Memory Manager */
uint16_t gs_mm(uint8_t fn, uint8_t *p)
{
    uint16_t i;
    uint32_t h, blk, size;

    switch (fn) {
    case 0x02:                          /* MMStartUp: user ID out */
        gs_putw(p, gs_userid);
        return 0;
    case 0x03:                          /* MMShutDown(userID) */
    case 0x11:                          /* DisposeAll(userID) */
        gs_pop = 2;
        return 0;
    case 0x09:                          /* NewHandle(size, userID, attr, where) */
        gs_pop = 12;                    /* where 0, attr 4, ID 6, size 8; out 12 */
        size = GS_L(p, 8);
        blk = gs_alloc(size ? size : 1, GS_W(p, 4), GS_L(p, 0));
        h = blk ? gs_handle(blk, size, GS_W(p, 6)) : 0;
        if (h)
            mp_free[slot(h)] = last_malloc;
        gs_putl(p + 12, h);
        return h ? 0 : memErr;
    case 0x10:                          /* DisposeHandle(handle) */
        gs_pop = 4;
        i = (uint16_t)slot(GS_L(p, 0));
        if (i == 0xFFFF)
            return 0x0206;              /* handleErr: not a handle */
        if (mp_free[i])
            Mfree((void FAR *)mp_free[i]);
        mp_size[i] = 0;                 /* bank $00's arena is not reused */
        mp[i] = 0;
        return 0;
    case 0x1A:                          /* FindHandle(location): handle out */
        gs_pop = 4;
        blk = GS_L(p, 0) & 0xFFFFFFUL;
        h = 0;
        for (i = 0; i < MP_MAX; i++)
            if (mp_size[i] && blk >= mp[i] && blk < mp[i] + mp_size[i])
                h = (uint32_t)(uint16_t)&mp[i];
        gs_putl(p + 4, h);
        return 0;
    case 0x18:                          /* GetHandleSize(handle): long out */
        gs_pop = 4;
        h = GS_L(p, 0);
        size = 0;
        for (i = 0; i < MP_MAX; i++)
            if ((uint32_t)(uint16_t)&mp[i] == h)
                size = mp_size[i];
        gs_putl(p + 4, size);
        return 0;
    case 0x20:                          /* HLock(handle) */
    case 0x22:                          /* HUnlock(handle) */
        gs_pop = 4;                     /* nothing moves: already so */
        return 0;
    }
    return GS_NOTYET;
}

/* $0A: SANE -- its housekeeping only (volume 2, chapter 18).  ORCA/C's
 * start-up asks SANEStatus; a program that never uses floating point
 * gets that far and no further, and one that does stops at its first
 * arithmetic call, which is not served yet. */
static uint16_t sane_on;

uint16_t gs_sane(uint8_t fn, uint8_t *p)
{
    switch (fn) {
    case 0x02:                          /* SANEStartUp(dPageAddr) */
        gs_pop = 2;
        sane_on = 1;
        return 0;
    case 0x03:                          /* SANEShutDown */
        sane_on = 0;
        return 0;
    case 0x06:                          /* SANEStatus: Boolean out */
        gs_putw(p, sane_on ? 0xFFFF : 0);
        return 0;
    }
    return GS_NOTYET;
}

/* $03: Misc Tools */
uint16_t gs_mt(uint8_t fn, uint8_t *p)
{
    (void)p;
    switch (fn) {
    case 0x02:                          /* MTStartUp */
    case 0x03:                          /* MTShutDown */
        return 0;
    }
    return GS_NOTYET;
}
