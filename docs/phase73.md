# Phase 73 -- the drives are D1: to D8: wherever a person reads them

A person with files on D1: and D2: was shown A: and B:: on the desk's
icons ("DISK A"), in window titles ("A:\GEM\*.*"), and in the file
selector's drive buttons and directory line.  The machine's own names
are D1: to D8:, and SpartaDOS X, MyDOS and DOS 2 all say them.

**Underneath it is still A: to H:.**  GEMDOS paths are the ST's, because
every ST program passes and expects them -- QED hands the selector
"A:\" and wants "A:\DOC.TXT" back.  So the change is a translation at
each place a person reads or types a drive, and nowhere else:

| where | shows | built from |
|---|---|---|
| a desk drive icon | the digit on the icon, "DISK D1:" under it | `obj_icon` stores the digit; `icon_letter` gives the letter back to the six places that build a path from an icon |
| a window's title | " D1:\GEM\*.* " | `win_sname` through `drv_show` |
| the selector's drive buttons | D1 to D8 | `tools/fselrsc.py`, text boxes where there were single letters |
| the selector's directory line | "D1:\*.*" | `dir_sset` as the line is filled; `dir_sget` reads what was typed -- "D1:", "1:" or "A:" -- back to "A:"; `path_changed` compares the two across the difference |

The selector's typed line gets a fourth path buffer in the pool's work
area rather than the stack, which an application's call shares.  The
models change with the code -- `tools/deskref.py` (labels, the icon's
character, the title) and `tools/aesref.py` (the selector's line) -- and
`make test-m12`, `test-m14`, `test-m17` and `test-m19` hold both sides
to them as before.  The gates that find a drive icon by its label look
for "DISK D1:".
