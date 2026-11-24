/* a6_cfg.c -- GEM4XE.CFG on a stock 6502: the pointer's two settings.
 *
 * src/sys/config.c reads the whole file for the 65C816, into a CONFIG that
 * bank $00 keeps.  The 6502's resident memory has not the room for that
 * record or for the code, so this reads the file from a bank and keeps
 * nothing but what it returns:
 *
 *   MOUSE=      the device, by config.c's names (AUTO, the default, is an
 *               ST mouse, as on the 65C816)
 *   MOUSEPORT=  1 or 2, straight into the pointer layer (ptr_setport), as
 *               config.c does it
 *
 * Every other key is left alone: a file written for the 65C816 build
 * reads here as it is.  Lines end at an EOL, a CR or an LF, as config.c's
 * do, and so does the end of the file; a line longer than any setting is
 * not one.  No file is not an error: the defaults stand.
 */
#include "portab.h"
#include <stdint.h>
#include "sys/cio.h"
#include "sys/config.h"
#include "vdi/vdi.h"
#include "vdi/pointer.h"

#define A6_LINE 72              /* config.c's CFG_LINE: a line means the same
                                 * to both CPUs, comment and all */

typedef struct {
    char    name[9];
    uint8_t kind;
} A6_NAME;

/* config.c's cfg_mouse, the same names for the same devices */
BANK_DATA("far") static const A6_NAME a6_mice[] = {
    { "AUTO",     PTR_ST_MOUSE    },
    { "NONE",     PTR_NONE        },
    { "ST",       PTR_ST_MOUSE    },
    { "AMIGA",    PTR_AMIGA_MOUSE },
    { "TRAKBALL", PTR_TRAKBALL    },
    { "CX80",     PTR_TRAKBALL    },
    { "CX22",     PTR_TRAKBALL    },
    { "TABLET",   PTR_CX77        },
    { "CX77",     PTR_CX77        },
    { "KOALA",    PTR_KOALA       },
    { "KOALAPAD", PTR_KOALA       },
    { "XEM1",     PTR_XEM1        },
    { "MOUSTER",  PTR_XEM1        },
    { "JOY",      PTR_JOY         },
    { "JOYSTICK", PTR_JOY         }
};
#define A6_MICE (sizeof a6_mice / sizeof a6_mice[0])

BANK_DATA("far") static const char a6_cfgfile[] = CFG_FILE;
BANK_DATA("far") static const char a6_kmouse[] = "MOUSE";
BANK_DATA("far") static const char a6_kport[] = "MOUSEPORT";

static uint8_t a6_same(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (uint8_t)(*a == *b);
}

/* KEY=VALUE, upper-cased, the blanks around both dropped; a comment
 * (# or ;) ends the line */
static void a6_cfg_line(char *s, uint8_t *kind)
{
    char *eq = 0, *p, *key, *val;
    uint8_t i;

    for (p = s; *p; p++) {
        if (*p == '#' || *p == ';') {
            *p = 0;
            break;
        }
        if (*p >= 'a' && *p <= 'z')
            *p = (char)(*p - 32);
        if (*p == '=' && !eq)
            eq = p;
    }
    if (!eq)
        return;
    *eq = 0;
    key = s;
    while (*key == ' ' || *key == '\t')
        key++;
    for (p = eq; p > key && (p[-1] == ' ' || p[-1] == '\t'); p--)
        ;
    *p = 0;
    val = eq + 1;
    while (*val == ' ' || *val == '\t')
        val++;
    for (p = val; *p; p++)
        ;
    while (p > val && (p[-1] == ' ' || p[-1] == '\t'))
        *--p = 0;

    if (a6_same(key, a6_kmouse)) {
        for (i = 0; i < A6_MICE; i++)
            if (a6_same(val, a6_mice[i].name)) {
                *kind = a6_mice[i].kind;
                break;
            }
    } else if (a6_same(key, a6_kport)) {
        if (val[0] == '1' && !val[1])
            ptr_setport(PTR_PORT_1);
        else if (val[0] == '2' && !val[1])
            ptr_setport(PTR_PORT_2);
    }
}

/* The pointer device GEM4XE.CFG names, an ST mouse if it names none. */
uint8_t a6_cfg_mouse(void)
{
    char line[A6_LINE];
    uint8_t buf[32];
    uint16_t got, i;
    uint8_t st, n = 0, over = 0, kind = PTR_ST_MOUSE;
    int16_t fd = cio_open(a6_cfgfile, CIO_A_READ, 0);

    if (fd < 0)
        return kind;
    for (;;) {
        got = 0;
        st = cio_read(fd, buf, sizeof buf, &got);
        if (got > sizeof buf)
            got = sizeof buf;
        for (i = 0; i < got; i++) {
            char c = (char)buf[i];

            if (c == (char)CIO_EOL || c == '\r' || c == '\n') {
                if (!over) {
                    line[n] = 0;
                    a6_cfg_line(line, &kind);
                }
                n = 0;
                over = 0;
            } else if (n < A6_LINE - 1) {
                line[n++] = c;
            } else {
                over = 1;
            }
        }
        if (st != CIO_OK)
            break;
    }
    if (n && !over) {
        line[n] = 0;
        a6_cfg_line(line, &kind);
    }
    cio_close(fd);
    return kind;
}
