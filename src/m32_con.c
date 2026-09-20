/* m32_con.c -- the gate program of tests/emu/m32_con.py: GEMDOS's
 * character calls, its standard handles, the memory calls phase 42 filled
 * in, and Pterm.
 *
 * A TOS program in everything but its file's name: it never calls
 * appl_init and reaches the screen and the keyboard through GEMDOS
 * alone.  It writes a page of VT-52 at the console that uses every
 * escape in the Compendium's table, waits for keys the harness types,
 * points its standard handles at a file and back, and ends with Pterm
 * from inside a function -- so the line after the call is what would run
 * if Pterm came back, and main()'s own return is a different number.
 * What each call answered goes into m32_res[] and m32_mem[], which the
 * harness reads by symbol; m32_step says where it has got to.
 *
 * The page is written out again, byte for byte, in the gate: the model
 * draws what the program sends.
 */
#include "portab.h"
#include "gem.h"
#include <time.h>               /* clock_t and CLOCKS_PER_SEC, for clock() */

#define ESC "\033"

WORD m32_res[64];
LONG m32_mem[6];
LONG m32_time[6];               /* Tgettimeofday twice, clock()'s span, its rate */
WORD m32_step;
char m32_line[24];
char m32_text[24];
static char m32_file[40];

static const char *const page[] = {
    ESC "E" "junk row zero\r\njunk row one" ESC "Y" "\042\043" ESC "d",
    ESC "H" "gem4xe console\r\n",
    ESC "p" "reverse" ESC "q" " normal\r\n",
    ESC "b" "\002" "ink 2 " ESC "c" "\003" "paper 3" ESC "c" " " ESC "b" "!" "\r\n",
    "tab\tstop\r\n",
    ESC "Y" "\045\050" "at 5,8",
    ESC "Y" "\046 " "xxxxxxxxxx" ESC "Y" "\046\044" ESC "K",
    ESC "Y" "\047 " "abcdefgh" ESC "Y" "\047\042" ESC "D" ESC "o",
    ESC "Y" "\050 " ESC "v" "0123456789012345678901234567890123456789"
                            "0123456789012345678901234567890123456789" "01234",
    ESC "w" ESC "Y" "\052 " "abcdefghijabcdefghijabcdefghijabcdefghij"
                            "abcdefghijabcdefghijabcdefghijabcdefghij" "klmno",
    ESC "Y" "\053 " "wipe this line" ESC "l" "kept",
    ESC "Y" "\054 " "saved" ESC "j" ESC "Y" "\060 " "elsewhere" ESC "k" " restored",
    ESC "Y" "\062 " "line to delete" ESC "Y" "\063 " "line below" ESC "Y" "\062 " ESC "M",
    ESC "Y" "\064 " ESC "L" "inserted",
    ESC "Y" "\067 " "keep this" ESC "Y" "\070 " "erase below" ESC "Y" "\067\044" ESC "J",
    ESC "H" ESC "I" "above",
    ESC "Y" "\075 " "bottom\r\n",
    ESC "A" ESC "A" ESC "C" ESC "C" ESC "C" "up" ESC "B" "down",
    "\007\b\bX",
};

static const char to_file[] = "to file\r\n!abc";
static const char kid_file[] = "kid hello\r\nend";

/* Pterm, from somewhere that is not main: nothing after the call runs. */
static void finish(void)
{
    m32_step = 9;
    Pterm(42);
    m32_step = 10;
}

int main(void)
{
    WORD i, h, s, con;
    LONG m, p;

    m32_step = 1;
    for (i = 0; i < (WORD)(sizeof page / sizeof page[0]); i++)
        Cconws(page[i]);
    Cconout('!');
    Fwrite(1, 6L, "fwrite");
    Crawio('R');
    con = (WORD)Fopen("CON:", 0);
    m32_res[28] = con;
    m32_res[29] = (WORD)Fwrite(con, 4L, "con:");
    m32_res[30] = (WORD)Fclose(con);

    /* -- the keyboard ---------------------------------------------------- */
    m32_res[0] = Cconis();
    m32_res[1] = (WORD)Crawio(0xFF);
    m32_step = 2;
    m = Cconin();                       /* K */
    m32_res[2] = (WORD)m;
    m32_res[3] = (WORD)(m >> 16);
    m32_step = 3;
    m32_line[0] = 20;
    Cconrs(m32_line);                   /* H I BACKSPACE E Y RETURN */
    m32_res[4] = m32_line[1];
    m32_step = 4;
    m32_res[5] = (WORD)Cnecin();        /* Z, not echoed */
    m32_step = 5;
    m32_res[6] = (WORD)Crawcin();       /* ^C, which ends nothing here */
    m32_step = 6;
    while (!Cconis())                   /* Q */
        ;
    m32_res[7] = Cconis();              /* still there: Cconis took nothing */
    m32_res[8] = (WORD)Cnecin();

    /* -- nothing to wait for ---------------------------------------------- */
    m32_step = 7;
    m32_res[9] = (WORD)Super((void FAR *)SUP_INQUIRE);
    m32_res[10] = (WORD)Super((void FAR *)0L);

    m32_mem[0] = Malloc(-1L);
    p = Mxalloc(1000L, MX_PREFTTRAM);
    m32_mem[1] = p;
    m32_mem[2] = Malloc(-1L);
    m32_res[12] = (WORD)Mshrink((void FAR *)p, 100L);
    m32_mem[3] = Malloc(-1L);
    m32_res[14] = (WORD)Mshrink((void FAR *)p, 2000L);
    m32_res[15] = (WORD)Mfree((void FAR *)p);
    m32_mem[4] = Malloc(-1L);
    m32_res[17] = (WORD)Mfree((void FAR *)p);
    m32_res[18] = (WORD)Mfree((void FAR *)m32_file);

    m32_res[19] = Tsetdate(0x0021);     /* 1980-01-01 */
    m32_res[20] = Tsetdate(0x0020);     /* day 0 */
    m32_res[21] = Tsettime(0xFFFF);     /* 31:63:62 */

    m32_res[22] = Cauxis();
    m32_res[23] = Cauxos();
    m32_res[24] = Cauxin();
    m32_res[25] = Cprnos();
    m32_res[26] = Cprnout('x');
    m32_res[27] = Cconos();

    /* -- handle 1 into a file, and back ------------------------------------ */
    h = (WORD)Fcreate("A:\\M32OUT.TXT", 0);
    m32_res[31] = h;
    s = (WORD)Fdup(1);
    m32_res[32] = s;
    m32_res[33] = (WORD)Fforce(1, h);
    Cconws("to file\r\n");
    Cconout('!');
    m32_res[34] = (WORD)Fwrite(1, 3L, "abc");
    m32_res[35] = (WORD)Fforce(1, s);
    m32_res[36] = (WORD)Fclose(s);
    m32_res[37] = (WORD)Fclose(h);
    m32_res[38] = (WORD)Fclose(h);      /* closed: not ours any more */
    h = (WORD)Fopen("A:\\M32OUT.TXT", 0);
    m32_res[39] = h;
    m32_res[40] = (WORD)Fread(h, 40L, m32_file);
    m32_res[41] = 1;
    for (i = 0; to_file[i]; i++)
        if (m32_file[i] != to_file[i])
            m32_res[41] = 0;
    Fclose(h);

    /* -- handle 0 from it --------------------------------------------------- */
    h = (WORD)Fopen("A:\\M32OUT.TXT", 0);
    m32_res[42] = (WORD)Fforce(0, h);
    m32_res[43] = (WORD)Cconin();       /* 't', and no echo */
    m32_text[0] = 20;
    Cconrs(m32_text);                   /* "o file", the CR dropped */
    m32_res[44] = m32_text[1];
    m32_res[45] = (WORD)Crawcin();      /* '!' */
    m32_res[46] = Cconis();
    Cconrs(m32_text);                   /* "abc", to the end */
    m32_res[47] = m32_text[1];
    m32_res[48] = (WORD)Cconin();       /* the end: 0xFF1A */
    m32_res[49] = (WORD)Fclose(0);
    m32_res[50] = (WORD)Fclose(h);

    /* -- Pexec: a child, with handle 1 forced onto a file for it ------------ */
    h = (WORD)Fcreate("A:\\M32KID.TXT", 0);
    s = (WORD)Fdup(1);
    Fforce(1, h);
    m32_mem[5] = Malloc(-1L);
    m32_res[52] = (WORD)Pexec(PE_LOADGO, "M32KID.PRG", "\005hello", 0);
    m32_res[53] = (WORD)(Malloc(-1L) == m32_mem[5]);
    Fforce(1, s);
    Fclose(s);
    m32_res[54] = (WORD)Fwrite(h, 3L, "end");
    m32_res[59] = (WORD)Fclose(h);
    h = (WORD)Fopen("A:\\M32KID.TXT", 0);
    m32_res[55] = (WORD)Fread(h, 40L, m32_file);
    Fclose(h);
    m32_res[56] = 1;
    for (i = 0; kid_file[i]; i++)
        if (m32_file[i] != kid_file[i])
            m32_res[56] = 0;
    m32_res[57] = (WORD)Pexec(PE_LOADGO, "NOPE.PRG", "\0", 0);
    m32_res[58] = (WORD)Pexec(3, "M32KID.PRG", "\0", 0);

    /* -- the clock: Tgettimeofday and clock() across an evnt_timer ------
     * The gate wants the pair before and after a 500 ms wait, so it can
     * see the seconds and microseconds monotonic and the span right, and
     * clock()'s span in the same units its header names. */
    {
        struct timeval a, b;
        clock_t c0, c1;
        m32_res[59] = (WORD)Tgettimeofday(&a, 0);
        c0 = clock();
        evnt_timer(500, 0);
        m32_res[60] = (WORD)Tgettimeofday(&b, 0);
        c1 = clock();
        m32_time[0] = a.tv_sec;
        m32_time[1] = a.tv_usec;
        m32_time[2] = b.tv_sec;
        m32_time[3] = b.tv_usec;
        m32_time[4] = (LONG)(c1 - c0);
        m32_time[5] = (LONG)CLOCKS_PER_SEC;
    }

    Cconws("\r\ndone");
    m32_step = 8;
    m32_res[51] = (WORD)Cnecin();       /* SPACE, after the last picture */

    /* And end with things open, for the exit to close: a file handle 1
     * has been forced onto, and a duplicate of it. */
    h = (WORD)Fopen("A:\\M32OUT.TXT", 0);
    Fforce(1, h);
    Fdup(1);
    finish();
    return 7;
}
