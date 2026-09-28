/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* sys/stat.h -- what a port asks a file the POSIX way: its kind, size
 * and dates.  Calypsi's C library has no <sys/stat.h> (and no <sys/> at
 * all), so this one is the kit's, over GEMDOS: stat() is lib/gemstat.c,
 * one Fsfirst with the search's DTA put back afterwards.  The struct is
 * mintlib's in shape and field names -- what a program written against
 * the ST's C libraries reads (st_mode, st_size, st_mtime) -- and the
 * types are the kit's own, there being no <sys/types.h> to take them
 * from.  What this machine cannot answer is zero: no device or inode
 * numbers, no owner, one link; the three times are the file's one
 * stamp, GEMDOS having only that. */
#ifndef GEM4XE_SYS_STAT_H
#define GEM4XE_SYS_STAT_H

#include <time.h>               /* time_t: the compiler's, 64 bits */

typedef unsigned short mode_t;
typedef long           off_t;
typedef short          dev_t;
typedef short          ino_t;
typedef short          nlink_t;
typedef short          uid_t;
typedef short          gid_t;

struct stat {
    dev_t   st_dev;
    ino_t   st_ino;
    mode_t  st_mode;
    nlink_t st_nlink;
    uid_t   st_uid;
    gid_t   st_gid;
    dev_t   st_rdev;
    off_t   st_size;
    time_t  st_atime;
    time_t  st_mtime;
    time_t  st_ctime;
    long    st_blksize;
    long    st_blocks;
};

/* The file types, mintlib's values (octal, as the tradition is). */
#define S_IFMT    0170000
#define S_IFIFO   0010000
#define S_IFCHR   0020000
#define S_IFDIR   0040000
#define S_IFBLK   0060000
#define S_IFREG   0100000
#define S_IFLNK   0120000
#define S_IFSOCK  0140000

#define S_ISDIR(m)  (((m) & S_IFMT) == S_IFDIR)
#define S_ISREG(m)  (((m) & S_IFMT) == S_IFREG)
#define S_ISCHR(m)  (((m) & S_IFMT) == S_IFCHR)
#define S_ISBLK(m)  (((m) & S_IFMT) == S_IFBLK)
#define S_ISFIFO(m) (((m) & S_IFMT) == S_IFIFO)
#define S_ISLNK(m)  (((m) & S_IFMT) == S_IFLNK)
#define S_ISSOCK(m) (((m) & S_IFMT) == S_IFSOCK)

/* The permission bits a GEMDOS attribute can express: read for all,
 * write for all unless FA_RDONLY, execute for a directory. */
#define S_IRUSR 0400
#define S_IWUSR 0200
#define S_IXUSR 0100
#define S_IRGRP 0040
#define S_IWGRP 0020
#define S_IXGRP 0010
#define S_IROTH 0004
#define S_IWOTH 0002
#define S_IXOTH 0001
#define S_IRWXU 0700
#define S_IRWXG 0070
#define S_IRWXO 0007

/* 0 and the struct filled; -1 with errno ENOENT when the path names
 * nothing.  `path` is a GEM path, as Fopen takes one. */
int stat(const char *path, struct stat *st);

#endif
