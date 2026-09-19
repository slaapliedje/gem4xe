/* config.c -- GEM4XE.CFG.  See config.h for why this exists at all.
 *
 * Everything here is written to be UNFAILABLE rather than strict.  A
 * parser that refuses a file is a parser that can lock somebody out of
 * their own machine from the one place they cannot see: the answer to a
 * line it does not understand is to ignore that line and read the next.
 */
#include "portab.h"
#include <stdint.h>
#include "config.h"
#include "cio.h"
#include "../vdi/vdi.h"
#include "../vbxe/vbxe.h"   /* VB_WIDE_*: the width index SCREENW keeps */
#include "../vdi/pointer.h"

/* SCREENW's default is NAMED and not left to the zero the rest of the
 * struct starts as: VB_WIDE_NARROW is 0, so an unset SCREENW would have
 * brought every machine up 512 pixels wide.  topmargin and screenh are
 * fine at zero because zero means "the default" for both of them; this
 * one's zero means a screen. */
CONFIG config = { CFG_VIDEO_AUTO, CFG_MOUSE_AUTO, CFG_PRINT_NONE, "P:",
                  CFG_CLOCK_AUTO, 0, 0, VB_WIDE_NORMAL };

#define CFG_LINE 72             /* a whole line, or it is not a setting */

/* A value's name and what it means.  One table per key, so that adding a
 * value is one line and cannot forget the parser.
 *
 * FAR, and the names are ARRAYS rather than pointers, so that the
 * whole table lands in `cfar` with the far code.  Bank $00 has 2,430
 * bytes of near memory for every constant the system owns
 * (src/gem4xe.scm) and a boot-time word list has no claim on any of
 * them; a table of pointers would have put the strings back there. */
#define CFG_NAME  9             /* "TRAKBALL" and a NUL, the longest */
#define NAMES(a)  (a), (WORD)(sizeof (a) / sizeof (a)[0])

typedef struct {
    char    name[CFG_NAME];
    int16_t value;
} CFG_WORD;

static const CFG_WORD FAR cfg_video[] = {
    { "AUTO",  CFG_VIDEO_AUTO  },
    { "VBXE",  CFG_VIDEO_VBXE  },
    { "ANTIC", CFG_VIDEO_ANTIC },
    { "SAFE",  CFG_VIDEO_ANTIC }         /* what somebody would try first */
};

/* The names src/vdi/pointer.h gives the devices, plus the second name
 * two of them are also known by.  Taken from the enum rather than
 * written out: a number here that had drifted from the one there would
 * pick the wrong device and say nothing about it. */
static const CFG_WORD FAR cfg_mouse[] = {
    { "AUTO",     CFG_MOUSE_AUTO   },
    { "NONE",     PTR_NONE         },
    { "ST",       PTR_ST_MOUSE     },
    { "AMIGA",    PTR_AMIGA_MOUSE  },
    { "TRAKBALL", PTR_TRAKBALL     },
    { "TABLET",   PTR_TABLET       },
    { "KOALA",    PTR_TABLET       },    /* the same device, its other name */
    { "XEM1",     PTR_XEM1         },
    { "MOUSTER",  PTR_XEM1         }     /* likewise */
};

static const CFG_WORD FAR cfg_printer[] = {
    { "NONE", CFG_PRINT_NONE },
    { "PCL",  CFG_PRINT_PCL  },
    { "PCL5", CFG_PRINT_PCL  },          /* what somebody would write */
    { "PS",   CFG_PRINT_PS   }
};

static const CFG_WORD FAR cfg_clock[] = {
    { "AUTO", CFG_CLOCK_AUTO },
    { "DOS",  CFG_CLOCK_DOS  },
    { "NONE", CFG_CLOCK_NONE }
};

/* ...and the keys themselves, for the same reason. */
static const char FAR k_video[] = "VIDEO";
static const char FAR k_mouse[] = "MOUSE";
static const char FAR k_mouseport[] = "MOUSEPORT";
static const char FAR k_printer[] = "PRINTER";
static const char FAR k_printto[] = "PRINTTO";
static const char FAR k_clock[] = "CLOCK";
static const char FAR k_topmargin[] = "TOPMARGIN";
static const char FAR k_screenh[] = "SCREENH";
static const char FAR k_screenw[] = "SCREENW";

static char up(char c)
{
    return (c >= 'a' && c <= 'z') ? (char)(c - ('a' - 'A')) : c;
}

static uint8_t blank(char c)
{
    return (uint8_t)(c == ' ' || c == '\t');
}

/* Two NUL-terminated strings: the table's, which is far, and the line's,
 * which the caller has already upper-cased. */
static uint8_t same(const char FAR *a, const char *b)
{
    while (*a && *b) {
        if (*a != *b)
            return 0;
        a++; b++;
    }
    return (uint8_t)(*a == *b);
}

static int16_t lookup(const CFG_WORD FAR *tbl, WORD n,
                      const char *val, int16_t miss)
{
    WORD i;

    for (i = 0; i < n; i++)
        if (same(tbl[i].name, val))
            return tbl[i].value;
    return miss;                /* a value this gem4xe does not know */
}

/* One line, EOL and all.  Trimmed, upper-cased and split on the '=' in
 * place; a line with no '=' -- a comment, a blank, a heading somebody
 * left behind -- is nothing to do. */
/* A small unsigned decimal, clamped to [0, max].  A value with no digit
 * -- or none at all -- leaves the default, the same forgiving rule the
 * word tables follow: a typo must never stop the machine starting. */
static int16_t cfg_num(const char *v, int16_t dflt, int16_t max)
{
    int16_t n = 0;
    WORD any = 0;

    while (*v >= '0' && *v <= '9') {
        n = (int16_t)(n * 10 + (*v++ - '0'));
        if (n > max) n = max;
        any = 1;
    }
    return any ? n : dflt;
}

static void cfg_line(char *s)
{
    char *key, *val, *eq, *p;

    /* the line ends at an EOL, a CR or an LF (a file that came off
     * another machine), or at a comment mark */
    for (p = s; *p; p++) {
        if (*p == (char)CIO_EOL || *p == '\r' || *p == '\n'
            || *p == '#' || *p == ';') {
            *p = '\0';
            break;
        }
    }

    eq = 0;
    for (p = s; *p; p++) {
        *p = up(*p);
        if (*p == '=' && !eq)
            eq = p;
    }
    if (!eq)
        return;
    *eq = '\0';

    key = s;
    while (blank(*key)) key++;
    for (p = eq; p > key && blank(p[-1]); p--)
        ;
    *p = '\0';

    val = eq + 1;
    while (blank(*val)) val++;
    for (p = val; *p; p++)
        ;
    while (p > val && blank(p[-1]))
        *--p = '\0';

    if (same(k_video, key))
        config.video = lookup(NAMES(cfg_video), val, config.video);
    else if (same(k_mouse, key))
        config.mouse = lookup(NAMES(cfg_mouse), val, config.mouse);
    else if (same(k_printer, key))
        config.printer = lookup(NAMES(cfg_printer), val, config.printer);
    else if (same(k_clock, key))
        config.clock = lookup(NAMES(cfg_clock), val, config.clock);
    else if (same(k_mouseport, key)) {
        /* Straight into the pointer layer's own byte: CONFIG has no room
         * for a field bank $00 would have to pay for, and nothing else
         * needs to read it back.  1 or 2, and anything else keeps the
         * standard rather than stopping the machine. */
        ptr_setport(cfg_num(val, 2, 2) == 1 ? PTR_PORT_1 : PTR_PORT_2);
    }
    else if (same(k_topmargin, key))
        config.topmargin = cfg_num(val, config.topmargin, CFG_TOPMARGIN_MAX);
    else if (same(k_screenh, key))
        config.screenh = cfg_num(val, config.screenh, CFG_SCREENH_MAX);
    else if (same(k_screenw, key)) {
        /* The file says the WIDTH; what is kept is the index, which is
         * also the OVATT code the XDL wants.  A width the hardware does
         * not have leaves the setting alone rather than picking the
         * nearest: guessing at a number somebody typed is how a machine
         * comes up in a mode nobody asked for. */
        int16_t px = cfg_num(val, CFG_SCREENW_NORMAL, CFG_SCREENW_WIDE);
        if (px == CFG_SCREENW_NARROW)
            config.screenw = VB_WIDE_NARROW;
        else if (px == CFG_SCREENW_NORMAL)
            config.screenw = VB_WIDE_NORMAL;
        else if (px == CFG_SCREENW_WIDE)
            config.screenw = VB_WIDE_WIDE;
    }
    else if (same(k_printto, key)) {
        /* A NAME, not a word out of a table: the value is taken as it
         * stands (upper-cased, as CIO wants) and truncated rather than
         * refused, because a key or a value this file does not
         * understand must never stop the machine starting. */
        WORD i;
        for (i = 0; i < CFG_PRINTTO_MAX - 1 && val[i]; i++)
            config.printto[i] = val[i];
        config.printto[i] = 0;
    }
    /* anything else: a key this gem4xe does not know, which is what a
     * file written for a later one looks like.  Leave it. */
}

/* READ AS BYTES, NOT AS RECORDS.  cio_getrec would be the obvious call
 * and is the wrong one: it ends a record at the Atari's own EOL and
 * nothing else, so a file that came off a PC -- CR LF, or bare LF --
 * arrives as ONE record too long for any buffer and every setting in it
 * is lost, silently.  This is a file people will edit on whatever they
 * have, so all three endings end a line here, and so does the end of the
 * file with no ending at all. */
void config_read(void)
{
    char line[CFG_LINE];
    uint8_t buf[64];
    uint16_t got, i;
    uint8_t st, over = 0;
    WORD n = 0;
    int16_t fd = cio_open(CFG_FILE, CIO_A_READ, 0);

    if (fd < 0)
        return;                 /* no file: every default stands */
    config.found = 1;

    for (;;) {
        got = 0;
        st = cio_read(fd, buf, sizeof buf, &got);
        if (got > sizeof buf)
            got = sizeof buf;
        for (i = 0; i < got; i++) {
            char c = (char)buf[i];

            if (c == (char)CIO_EOL || c == '\r' || c == '\n') {
                if (!over) {
                    line[n] = '\0';
                    cfg_line(line);
                }
                n = 0;
                over = 0;
            } else if (n < CFG_LINE - 1) {
                line[n++] = c;
            } else {
                over = 1;       /* longer than any setting is: not one */
            }
        }
        if (st != CIO_OK)
            break;              /* the end of the file, or an error */
    }
    if (n && !over) {           /* a last line with no ending */
        line[n] = '\0';
        cfg_line(line);
    }
    cio_close(fd);
}
