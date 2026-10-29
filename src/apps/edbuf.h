/* EDIT's text: a gap buffer and the line ends a file came with.
 *
 * Portable C, like GemARC's engine: the same file runs on the Atari
 * (src/apps/edit.c) and on the host (tests/host/ed_host.c,
 * tests/host/test_edit.py).  Nothing here reads or writes a file; the
 * program loads the bytes into ed_b, calls ed_loaded, and writes the two
 * spans ed_span gives back.
 *
 * THE BYTES ARE KEPT.  The text is the file's bytes, every one, and only
 * the ones an edit touches change -- inverse video, ATASCII graphics,
 * control characters and a stray CR all stay as they were.
 *
 * ONE KIND OF LINE END per file, found once when it is loaded, by the
 * first $9B, CR or LF in it:
 *
 *   ED_ATARI a $9B, or none of the three at all: $9B ends a line.  An
 *            empty or new file is an Atari one, the machine's own.
 *   ED_CRLF  a CR followed by an LF
 *   ED_LF    a bare LF
 *   ED_CR    a bare CR
 *
 * The first one decides, not "any CR or LF anywhere": an Atari text can
 * hold a CR, ATASCII's Control-M graphic, and an ST one a cent sign,
 * $9B, but either is rare before its first line has ended.
 *
 * Only that kind ends a line; any other byte is a character, so a $9B in
 * an ST file is its cent sign and a CR in an Atari file is shown, not
 * taken for a break.  Return puts in the same kind.
 *
 * Positions are offsets in the text, 0 to ed_len, as if there were no
 * gap.  A CR LF is one line end: no position falls between its two
 * bytes, and every move and delete here steps over it whole. */
#ifndef EDIT_BUF_H
#define EDIT_BUF_H

#include <stdint.h>

#ifndef FAR
#define FAR
#endif

#define ED_ATARI   0
#define ED_CRLF    1
#define ED_LF      2
#define ED_CR      3

#define ED_TAB     8                /* a tab's columns, outside Atari files */

typedef struct {
    uint8_t FAR *b;                 /* the buffer: text, gap, text */
    uint16_t cap;                   /* its bytes; never across a bank */
    uint16_t gs, ge;                /* the gap: b[gs] up to b[ge] */
    uint16_t lines;                 /* line ends in the text, plus one */
    uint8_t  eol;                   /* ED_ATARI ... ED_CR */
    uint8_t  dirty;                 /* changed since loaded or saved */
} EDBUF;

void     ed_init(EDBUF *e, uint8_t FAR *buf, uint16_t cap);
/* n bytes are at b[0]: find the line end and count the lines. */
void     ed_loaded(EDBUF *e, uint16_t n);
uint16_t ed_len(const EDBUF *e);
uint16_t ed_room(const EDBUF *e);
uint8_t  ed_at(const EDBUF *e, uint16_t p);
/* The text in two spans, for writing out: b[0..*n1) and *p2 for *n2. */
void     ed_span(const EDBUF *e, uint16_t *n1, uint8_t FAR **p2, uint16_t *n2);

/* The line end that starts at p: its bytes, or 0. */
uint16_t ed_eol_at(const EDBUF *e, uint16_t p);
/* The line end that finishes just before p: its bytes, or 0. */
uint16_t ed_eol_before(const EDBUF *e, uint16_t p);
uint16_t ed_bol(const EDBUF *e, uint16_t p);      /* its line's start */
uint16_t ed_eolpos(const EDBUF *e, uint16_t p);   /* where its line ends */
/* The next line's start, or p's own line's end if it is the last. */
uint16_t ed_next(const EDBUF *e, uint16_t p);
/* The line before p's line: its start, or 0. */
uint16_t ed_prev(const EDBUF *e, uint16_t p);

uint16_t ed_left(const EDBUF *e, uint16_t p);
uint16_t ed_right(const EDBUF *e, uint16_t p);
/* Columns: the column p is drawn at in the line starting at bol, and the
 * position in that line nearest column col without passing it. */
uint16_t ed_col(const EDBUF *e, uint16_t bol, uint16_t p);
uint16_t ed_atcol(const EDBUF *e, uint16_t bol, uint16_t col);
/* A line up or down, as near column goal as that line goes; p itself at
 * the first or last line. */
uint16_t ed_up(const EDBUF *e, uint16_t p, uint16_t goal);
uint16_t ed_down(const EDBUF *e, uint16_t p, uint16_t goal);
/* How many columns byte c takes when it starts at column col. */
uint16_t ed_width(const EDBUF *e, uint8_t c, uint16_t col);

/* Edits: FALSE when the buffer is full (nothing then changes).  Each
 * keeps ed_lines right. */
int      ed_insert(EDBUF *e, uint16_t p, const uint8_t *s, uint16_t n);
int      ed_newline(EDBUF *e, uint16_t p);         /* the file's own end */
void     ed_delete(EDBUF *e, uint16_t p, uint16_t n);
/* The character or line end at p, or before it, deleted; the new p. */
uint16_t ed_del_right(EDBUF *e, uint16_t p);
uint16_t ed_del_left(EDBUF *e, uint16_t p);

#endif
