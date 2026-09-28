/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* gemstub.c -- the routines Calypsi's C library asks the BOARD to provide,
 * answered over GEMDOS.
 *
 * `printf` is not an exotic thing for a program to do, and without these
 * it does not link.  What the linker says is
 *
 *     missing stub routine '_Stub_write' needs to be provided for your
 *     hardware/board-support
 *
 * which names the board support rather than anything the author wrote, so
 * a porter meeting it has no reason to look here.  The C library reaches
 * the platform through nine functions (calypsi/stubs.h) and this file is
 * all nine.
 *
 * A FILE DESCRIPTOR HERE IS A GEMDOS HANDLE, passed straight through with
 * no table and no translation.  It works because the two numberings agree
 * where it matters: GEMDOS gives every program 0 and 1 on the console, 2
 * on AUX: and 3 on PRN:, and hands out files above those -- and Calypsi
 * asks only that an opened file come back greater than 2, with 0, 1 and 2
 * left to stdin, stdout and stderr.  So `printf` writes to handle 1 and
 * reaches the VT-52 console the system draws on GEM's screen, `Fforce`
 * still redirects it into a file as it does on an ST, and nothing in this
 * file has to remember anything.
 *
 * WHAT IS NOT THE SAME AS A UNIX SYSTEM CALL, and cannot be:
 *
 *   O_APPEND seeks to the end ONCE, at open.  GEMDOS has no append mode,
 *   so a second program writing the same file, or a seek of the caller's
 *   own, ends the appending.  The ST's C libraries do the same thing and
 *   a program written for one is not surprised.
 *
 *   The errors are GEMDOS's, mapped to the nearest errno.  GEMDOS does
 *   not distinguish "no such file" from "no such path" the way the
 *   distinction is usually wanted, so both arrive as ENOENT.
 *
 *   There is no heap here and these functions take none: the C library's
 *   own buffering is what it allocates, and it is refused
 *   (lib/clib.c) -- a program that wants a buffer gives stdio one with
 *   setvbuf, or writes unbuffered.
 */
#include "portab.h"
#include "gem.h"
#include <calypsi/stubs.h>
#include <fcntl.h>
#include <errno.h>
#include <stdio.h>

/* GEMDOS's negative codes as the nearest errno, POSITIVE -- every stub
 * returns it negated, which is the contract in calypsi/stubs.h. */
static int errno_of(LONG r)
{
    switch (r) {
    case EFILNF:                        /* no such file */
    case EPTHNF:                        /* ...or path */
    case ENMFIL:                        /* no more files */
        return ENOENT;
    case ENHNDL:                        /* no handle left */
        return EMFILE;
    case EACCDN:                        /* access denied */
        return EACCES;
    case EIHNDL:                        /* not a handle of ours */
        return EBADF;
    case ENSMEM:
        return ENOSPC;
    case EINVFN:
        return EINVAL;
    default:
        return EIO;
    }
}

int _Stub_open(const char *path, int oflag, ...)
{
    LONG r;
    WORD mode = 0;                      /* GEMDOS: 0 read, 1 write, 2 both */

    if ((oflag & O_ACCMODE) == O_WRONLY)
        mode = 1;
    else if ((oflag & O_ACCMODE) == O_RDWR)
        mode = 2;

    if (oflag & O_TRUNC) {
        r = Fcreate(path, 0);           /* creates, or empties what is there */
    } else {
        r = Fopen(path, mode);
        if (r < 0 && (oflag & O_CREAT))
            r = Fcreate(path, 0);
    }
    if (r < 0)
        return -errno_of(r);
    if (oflag & O_APPEND)               /* see the note at the top */
        Fseek(0L, (WORD)r, SEEK_END);
    return (int)r;
}

int _Stub_close(int fd)
{
    LONG r = Fclose((WORD)fd);
    return r < 0 ? -errno_of(r) : 0;
}

long _Stub_lseek(int fd, long offset, int whence)
{
    /* SEEK_SET, SEEK_CUR and SEEK_END are 0, 1 and 2, and so are GEMDOS's
     * three modes: the same three numbers mean the same three things. */
    LONG r = Fseek(offset, (WORD)fd, (WORD)whence);
    return r < 0 ? -errno_of(r) : r;
}

int _Stub_fgetpos(int fd, fpos_t *pos)
{
    LONG r = Fseek(0L, (WORD)fd, SEEK_CUR);
    if (r < 0)
        return -errno_of(r);
    *pos = (fpos_t)r;
    return 0;
}

int _Stub_fsetpos(int fd, const fpos_t *pos)
{
    LONG r = Fseek((LONG)*pos, (WORD)fd, SEEK_SET);
    return r < 0 ? -errno_of(r) : 0;
}

size_t _Stub_read(int fd, void *buf, size_t count)
{
    LONG r = Fread((WORD)fd, (LONG)count, buf);
    return r < 0 ? (size_t)(-errno_of(r)) : (size_t)r;
}

size_t _Stub_write(int fd, const void *buf, size_t count)
{
    LONG r = Fwrite((WORD)fd, (LONG)count, buf);
    return r < 0 ? (size_t)(-errno_of(r)) : (size_t)r;
}

int _Stub_rename(const char *oldpath, const char *newpath)
{
    LONG r = Frename(oldpath, newpath);
    return r < 0 ? -errno_of(r) : 0;
}

int _Stub_remove(const char *path)
{
    LONG r = Fdelete(path);
    return r < 0 ? -errno_of(r) : 0;
}
