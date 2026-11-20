;;; Calypsi's example/minimal map, plus the switch section printf needs
(define memories
  '((memory flash (address (#x8000 . #xffff))
            (section code idata cdata switch data_init_table (reset #xfffc)))
    (memory zeropage (address (#x00 . #xff))
            (section registers zzpage zpage))
    (memory RAM (address (#x0100 . #x7fff))
            (section (stack (#x100 . #x1ff))
                     cstack data zdata))
    (block cstack (size #x800))
    (block stack (size #x100))
    ))
