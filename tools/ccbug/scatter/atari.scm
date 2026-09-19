;;; An Atari XL/XE: ONE 16 KB window at $4000-$7FFF, banks behind it.
(define memories
  '((memory program (address (#x2000 . #x3fff)) (type any)
            (section (programStart #x2000) startup code cdata data
                     data_init_table))
    (memory zeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80)))
    (memory stackPage (address (#x100 . #x1ff)) (type ram))
    (memory bankSlot (address (#x4000 . #x7fff))
            (scatter-to RAM-banks)
            :generate-instances
            (section bankedcode))
    (memory bankedRAM (address (#x10000 . #x1fffff))
            (section RAM-banks))
    ))
