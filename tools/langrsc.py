#!/usr/bin/env python3
"""LANG.RSC -- everything the SYSTEM says, in one file a translator ships.

    python3 tools/langrsc.py build/lang.rsc build/lang_rsc.c build/lang_rsc.h
    python3 tools/langrsc.py --lang de build/lang/de/LANG.RSC

Three outputs from one description, because the three must not disagree:

    lang.rsc      the file.  GEM.COM reads it at start-up and keeps it in
                  far memory; replacing it is how gem4xe is translated
                  (docs/shipping.md, section 5).
    lang_rsc.c    the same bytes as a `FAR` array: the English the
                  system falls back on when the file is not there, so a
                  disk without LANG.RSC still speaks.
    lang_rsc.h    the indices, so src/ and this file cannot disagree
                  about which string is which.

It is a real .RSC -- tools/rsc.py writes it, an RCS could open it -- with
free strings and nothing else.  No trees: the file selector's tree stays
in the far image (tools/fselrsc.py) because the selector copies its whole
resource into the application pool each time it opens, and 1 KB of alert
text would be 1 KB less for the application's own resource every time
(docs/phase11.md has that budget).  Widening a translated selector is
therefore still to do, and section 5 says so.

THE TEXTS are the donor's, from EmuTOS's gem_rsc.c by way of
src/aes/alert.c and src/aes/shel.c, where they were C literals until this
file existed.  Two rules for whoever translates them:

  * `|` breaks a line, `[n][text][buttons]` is form_alert's grammar, and
    the first `[n]` chooses the icon (0 none, 1 note, 2 question, 3 stop).
  * ST_ERRTOS carries the error number in the two digits after its `#`.
    fm_error writes them there by searching for the `#`, not by counting
    characters, so a translation may move the phrase but must keep one
    `#` followed by two digits.

THE TRANSLATIONS below -- German, French, Spanish and Polish, for where
the Atari 8-bit was most at home (phase 96) -- are kept to every rule by
check(), which the build and tests/host/test_lang.py both run:
form_alert's grammar with the English icon and button count, five lines
of forty, buttons of twenty, the boot screen's labels in BOOT_LABEL
columns, the exit messages in forty (they go to the DOS screen), the `#`,
and every string inside LANG_MAXLEN -- the near buffer lang_str copies
into is sized by the English and bank $00 has no room to widen it.

THE CHARACTERS: German, French and Spanish are written in the Atari ST
character set the system font has (ATARIST below, EmuTOS's own Latin-1
table, tools/bug.c); Polish is ISO-8859-2, for the Latin-2 font
`make fonts` writes, which ships beside it as SYSTEM.FNT.  The five long
form_error alerts and two labels are EmuTOS's translations (its po/, the
same GPL donor); ERRDOCS is shortened to fit, and ERRFILE keeps the
English icon.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                              # noqa: E402

# The name on the disk, which src/aes/aes.h calls LANG_FILE.
FILENAME = "LANG.RSC"

# (name, text).  The order is the index order: appending is safe, and
# reordering is not -- build/lang_rsc.h is what the C uses.
STRINGS = [
    # form_error's five, by the DOS error it is given (src/aes/alert.c)
    ("ERRFILE", "[2][This application cannot|find the folder or file|"
                "you just tried to access.][  OK  ]"),
    ("ERRDOCS", "[1][This application does not|have room to open another|"
                "document.  To make room,|close any document that|"
                "you do not need.][  OK  ]"),
    ("ERREXIST", "[1][An item with this name|already exists in the|"
                 "directory, or this item|is set to Read Only status.][  OK  ]"),
    ("ERRDRIVE", "[1][The drive you specified|does not exist.][Cancel]"),
    ("ERRMEM", "[1][There is not enough memory|in your computer for the|"
               "application you just tried|to run.][  OK  ]"),
    ("ERRTOS", "[3][TOS error #00.][Cancel]"),
    # the shell, when it cannot run what it was asked for (src/aes/shel.c)
    ("APPNOTFOUND", "[1][This application|cannot be found.][ OK ]"),
    ("APPNOTLOAD", "[1][This application|cannot be loaded.][ OK ]"),
    ("APPOLDSDK", "[1][This application was built|for an older gem4xe.|"
                  "Rebuild it with the|current SDK.][ OK ]"),
    # the boot screen (src/sys/bootinfo.c): the labels down its left
    # column, and the few values that are words rather than the machine's
    # own names and numbers.  A label is cut at BOOT_LABEL columns there,
    # so a translation keeps them short.
    ("BOOT_VERSION", "Version"),
    ("BOOT_CPU", "Processor"),
    ("BOOT_MEMORY", "Memory"),
    ("BOOT_DOS", "DOS"),
    ("BOOT_CONFIG", "Settings"),
    ("BOOT_LANG", "Language"),
    ("BOOT_VIDEO", "Screen"),
    ("BOOT_CLOCK", "Clock"),
    ("BOOT_POINTER", "Pointer"),
    ("BOOT_PRINTER", "Printer"),
    ("BOOT_BUILTIN", "built in"),
    ("BOOT_DEFAULTS", "defaults"),
    ("BOOT_NONE", "none"),
    ("BOOT_PTR_ST", "ST mouse"),
    ("BOOT_PTR_AMIGA", "Amiga mouse"),
    ("BOOT_PTR_CX80", "CX80 trak-ball"),
    ("BOOT_PTR_TABLET", "touch tablet"),
    ("BOOT_PTR_XEM1", "mouSTer (XEM1)"),
    ("BOOT_BANKS", "banks"),
    ("BOOT_HOLD", "Hold SHIFT to pause this screen"),
    # the vectors line (src/sys/irq.h: how irq_install() reached them, or
    # why not), and the refusal that follows a "why not" on the way out
    ("BOOT_IRQ", "Vectors"),
    ("BOOT_IRQ_COPIED", "OS copied"),
    ("BOOT_IRQ_RAM", "OS in RAM"),
    ("BOOT_IRQ_NOCOPY", "copy failed"),
    ("BOOT_IRQ_NOVEC", "not kept"),
    ("EXIT_NOCOPY", "gem4xe: no RAM under the OS ROM"),
    ("EXIT_NOVEC", "gem4xe: the vectors did not take"),
    ("EXIT_NOIRQ", "gem4xe: no interrupt vectors installed"),
    ("EXIT_NOVBXE", "gem4xe: VIDEO=VBXE, but no VBXE found"),
    # the desktop never started (src/gem.c, exit_desk): which reason, the
    # memory it found when that was the reason, and -- on a cartridge,
    # where leaving is a cold start that would wipe the screen -- a wait
    ("EXIT_NOFAR", "gem4xe: the desktop needs more memory"),
    ("EXIT_FARKB", "KB of memory above bank $00"),
    ("EXIT_NOFILE", "gem4xe: DESKTOP.PRG is not on the disk"),
    ("EXIT_NODESK", "gem4xe: the desktop could not be loaded"),
    ("EXIT_ANYKEY", "Press a key to start again"),
    # an accessory found and not loaded, said at boot before the desktop
    # (src/aes/shel.c, sh_main): past the six slots, or no memory for it
    ("ACCFULL", "[1][Not every desk accessory|could be loaded. There are|six places for them, and|memory may allow fewer.][ OK ]"),
]

# The longest string the system will ever copy into its near buffer, and
# the reason src/sys/lang.h can size that buffer without asking anyone.
MAXLEN = max(len(s) for _, s in STRINGS)

TRANSLATIONS = {
    "de": {
        "ERRFILE": "[2][Die Anwendung kann den|Ordner oder die Datei|nicht finden, auf die|zugegriffen werden soll.][  OK  ]",
        "ERRDOCS": "[1][Diese Anwendung hat keinen|Platz für ein weiteres|Dokument. Schließen Sie|ein unbenötigtes Dokument.][  OK  ]",
        "ERREXIST": "[1][Eine Datei mit diesem Namen|existiert entweder schon in|diesem Ordner oder sie ist|schreibgeschützt.][  OK  ]",
        "ERRDRIVE": "[1][Das angegebene Laufwerk|existiert nicht.][Abbruch]",
        "ERRMEM": "[1][Es ist nicht genug freier|Speicher vorhanden um die|gewünschte Anwendung zu|starten.][  OK  ]",
        "ERRTOS": "[3][TOS-Fehler #00.][Abbruch]",
        "APPNOTFOUND": "[1][Diese Anwendung|wurde nicht gefunden.][ OK ]",
        "APPNOTLOAD": "[1][Diese Anwendung kann|nicht geladen werden.][ OK ]",
        "APPOLDSDK": "[1][Diese Anwendung wurde für|ein älteres gem4xe gebaut.|Bitte mit dem aktuellen|SDK neu bauen.][ OK ]",
        "BOOT_VERSION": "Version",
        "BOOT_CPU": "Prozessor",
        "BOOT_MEMORY": "Speicher",
        "BOOT_DOS": "DOS",
        "BOOT_CONFIG": "Optionen",
        "BOOT_LANG": "Sprache",
        "BOOT_VIDEO": "Anzeige",
        "BOOT_CLOCK": "Uhr",
        "BOOT_POINTER": "Zeiger",
        "BOOT_PRINTER": "Drucker",
        "BOOT_BUILTIN": "eingebaut",
        "BOOT_DEFAULTS": "Standard",
        "BOOT_NONE": "keine",
        "BOOT_PTR_ST": "ST-Maus",
        "BOOT_PTR_AMIGA": "Amiga-Maus",
        "BOOT_PTR_CX80": "CX80-Trackball",
        "BOOT_PTR_TABLET": "Grafiktablett",
        "BOOT_PTR_XEM1": "mouSTer (XEM1)",
        "BOOT_BANKS": "Baenke",
        "BOOT_HOLD": "SHIFT halten, um anzuhalten",
        "BOOT_IRQ": "Vektoren",
        "BOOT_IRQ_COPIED": "OS kopiert",
        "BOOT_IRQ_RAM": "OS im RAM",
        "BOOT_IRQ_NOCOPY": "Kopie misslungen",
        "BOOT_IRQ_NOVEC": "nicht gehalten",
        "EXIT_NOCOPY": "gem4xe: kein RAM unter dem OS-ROM",
        "EXIT_NOVEC": "gem4xe: Vektoren greifen nicht",
        "EXIT_NOIRQ": "gem4xe: keine IRQ-Vektoren gesetzt",
        "EXIT_NOVBXE": "gem4xe: VIDEO=VBXE, aber keine VBXE",
        "EXIT_NOFAR": "gem4xe: Desktop braucht mehr Speicher",
        "EXIT_FARKB": "KB Speicher ueber Bank $00",
        "EXIT_NOFILE": "gem4xe: DESKTOP.PRG fehlt",
        "EXIT_NODESK": "gem4xe: Desktop nicht ladbar",
        "EXIT_ANYKEY": "Taste druecken fuer Neustart",
        "ACCFULL": "[1][Nicht alle Accessories|konnten geladen werden. Es|gibt sechs Plätze, und der|Speicher reicht evtl. für|weniger.][ OK ]",
    },
    "fr": {
        "ERRFILE": "[2][Cette application ne trouve pas|le dossier ou le fichier auquel|vous tentez d'accéder.][  OK  ]",
        "ERRDOCS": "[1][Cette application n'a pas|la place d'ouvrir un autre|document. Fermez un document|dont vous n'avez plus besoin.][  OK  ]",
        "ERREXIST": "[1][Un objet portant ce nom existe|déjà dans ce dossier, ou bien|il est en lecture seule.][  OK  ]",
        "ERRDRIVE": "[1][Le lecteur spécifié|n'existe pas.][Annuler]",
        "ERRMEM": "[1][Votre ordinateur n'a pas|suffisamment de mémoire pour|l'application que vous venez|d'essayer de lancer.][  OK  ]",
        "ERRTOS": "[3][Erreur TOS #00.][Annuler]",
        "APPNOTFOUND": "[1][Cette application|est introuvable.][ OK ]",
        "APPNOTLOAD": "[1][Impossible de charger|cette application.][ OK ]",
        "APPOLDSDK": "[1][Cette application a été|compilée pour un gem4xe|plus ancien. Recompilez-la|avec le SDK actuel.][ OK ]",
        "BOOT_VERSION": "Version",
        "BOOT_CPU": "CPU",
        "BOOT_MEMORY": "Memoire",
        "BOOT_DOS": "DOS",
        "BOOT_CONFIG": "Reglages",
        "BOOT_LANG": "Langue",
        "BOOT_VIDEO": "Ecran",
        "BOOT_CLOCK": "Horloge",
        "BOOT_POINTER": "Pointeur",
        "BOOT_PRINTER": "Imprim.",
        "BOOT_BUILTIN": "integree",
        "BOOT_DEFAULTS": "par defaut",
        "BOOT_NONE": "aucune",
        "BOOT_PTR_ST": "souris ST",
        "BOOT_PTR_AMIGA": "souris Amiga",
        "BOOT_PTR_CX80": "trackball CX80",
        "BOOT_PTR_TABLET": "tablette tactile",
        "BOOT_PTR_XEM1": "mouSTer (XEM1)",
        "BOOT_BANKS": "banques",
        "BOOT_HOLD": "Maintenez SHIFT pour figer l'ecran",
        "BOOT_IRQ": "Vecteurs",
        "BOOT_IRQ_COPIED": "OS copie",
        "BOOT_IRQ_RAM": "OS en RAM",
        "BOOT_IRQ_NOCOPY": "echec de la copie",
        "BOOT_IRQ_NOVEC": "non conserves",
        "EXIT_NOCOPY": "gem4xe: pas de RAM sous la ROM",
        "EXIT_NOVEC": "gem4xe: vecteurs non installes",
        "EXIT_NOIRQ": "gem4xe: aucun vecteur d'interruption",
        "EXIT_NOVBXE": "gem4xe: VIDEO=VBXE, mais pas de VBXE",
        "EXIT_NOFAR": "gem4xe: le bureau manque de memoire",
        "EXIT_FARKB": "Ko de memoire au-dela de la banque $00",
        "EXIT_NOFILE": "gem4xe: DESKTOP.PRG est absent",
        "EXIT_NODESK": "gem4xe: impossible de charger le bureau",
        "EXIT_ANYKEY": "Appuyez sur une touche pour redemarrer",
        "ACCFULL": "[1][Certains accessoires n'ont|pas pu être chargés. Il y a|six emplacements, et la|mémoire peut en limiter|le nombre.][ OK ]",
    },
    "es": {
        "ERRFILE": "[2][Esta aplicación no puede|encontrar la carpeta o archivo|al que intenta acceder.][  OK  ]",
        "ERRDOCS": "[1][Esta aplicación no tiene|espacio para otro documento.|Cierre algún documento que|no necesite.][  OK  ]",
        "ERREXIST": "[1][Un elemento con este nombre|ya existe en el directorio,|o este elemento es de solo|lectura.][  OK  ]",
        "ERRDRIVE": "[1][El dispositivo especificado|no existe.][Cancelar]",
        "ERRMEM": "[1][No hay suficiente memoria|en tu ordenador para la|aplicación que intenta|ejecutar.][  OK  ]",
        "ERRTOS": "[3][Error TOS #00.][Cancelar]",
        "APPNOTFOUND": "[1][No se encuentra|esta aplicación.][ OK ]",
        "APPNOTLOAD": "[1][No se puede cargar|esta aplicación.][ OK ]",
        "APPOLDSDK": "[1][Esta aplicación se compiló|para un gem4xe anterior.|Vuelva a compilarla con|el SDK actual.][ OK ]",
        "BOOT_VERSION": "Version",
        "BOOT_CPU": "CPU",
        "BOOT_MEMORY": "Memoria",
        "BOOT_DOS": "DOS",
        "BOOT_CONFIG": "Ajustes",
        "BOOT_LANG": "Idioma",
        "BOOT_VIDEO": "Pantalla",
        "BOOT_CLOCK": "Reloj",
        "BOOT_POINTER": "Puntero",
        "BOOT_PRINTER": "Impresora",
        "BOOT_BUILTIN": "integrado",
        "BOOT_DEFAULTS": "por defecto",
        "BOOT_NONE": "ninguno",
        "BOOT_PTR_ST": "raton ST",
        "BOOT_PTR_AMIGA": "raton Amiga",
        "BOOT_PTR_CX80": "trackball CX80",
        "BOOT_PTR_TABLET": "tableta tactil",
        "BOOT_PTR_XEM1": "mouSTer (XEM1)",
        "BOOT_BANKS": "bancos",
        "BOOT_HOLD": "Mantenga SHIFT para pausar",
        "BOOT_IRQ": "Vectores",
        "BOOT_IRQ_COPIED": "OS copiado",
        "BOOT_IRQ_RAM": "OS en RAM",
        "BOOT_IRQ_NOCOPY": "copia fallida",
        "BOOT_IRQ_NOVEC": "no se mantienen",
        "EXIT_NOCOPY": "gem4xe: no hay RAM bajo la ROM",
        "EXIT_NOVEC": "gem4xe: los vectores no se fijaron",
        "EXIT_NOIRQ": "gem4xe: sin vectores de interrupcion",
        "EXIT_NOVBXE": "gem4xe: VIDEO=VBXE, pero no hay VBXE",
        "EXIT_NOFAR": "gem4xe: el escritorio necesita memoria",
        "EXIT_FARKB": "KB de memoria sobre el banco $00",
        "EXIT_NOFILE": "gem4xe: falta DESKTOP.PRG en el disco",
        "EXIT_NODESK": "gem4xe: no se pudo cargar el escritorio",
        "EXIT_ANYKEY": "Pulse una tecla para reiniciar",
        "ACCFULL": "[1][No se pudieron cargar|todos los accesorios. Hay|seis espacios, y la memoria|puede admitir menos.][ OK ]",
    },
    "pl": {
        "ERRFILE": "[2][Ten program nie może|znaleźć folderu lub pliku,|którego próbowałeś użyć.][  OK  ]",
        "ERRDOCS": "[1][Ten program nie ma miejsca,|aby otworzyć kolejny|dokument. Aby zrobić miejsce,|zamknij nieużywane dokumenty.][  OK  ]",
        "ERREXIST": "[1][Przedmiot z tą nazwą już|istnieje w katalogu,|lub ma on ustawiony|status Tylko odczyt.][  OK  ]",
        "ERRDRIVE": "[1][Dysk, który określono|nie istnieje.][Anuluj]",
        "ERRMEM": "[1][Nie ma wystarczająco|pamięci w komputerze dla|programu, który chciano|uruchomić.][  OK  ]",
        "ERRTOS": "[3][Błąd TOS #00.][Anuluj]",
        "APPNOTFOUND": "[1][Nie można znaleźć|tego programu.][ OK ]",
        "APPNOTLOAD": "[1][Nie można wczytać|tego programu.][ OK ]",
        "APPOLDSDK": "[1][Ten program zbudowano dla|starszej wersji gem4xe.|Zbuduj go ponownie|z obecnym SDK.][ OK ]",
        "BOOT_VERSION": "Wersja",
        "BOOT_CPU": "Procesor",
        "BOOT_MEMORY": "Pamiec",
        "BOOT_DOS": "DOS",
        "BOOT_CONFIG": "Opcje",
        "BOOT_LANG": "Jezyk",
        "BOOT_VIDEO": "Ekran",
        "BOOT_CLOCK": "Zegar",
        "BOOT_POINTER": "Wskaznik",
        "BOOT_PRINTER": "Drukarka",
        "BOOT_BUILTIN": "wbudowany",
        "BOOT_DEFAULTS": "domyslne",
        "BOOT_NONE": "brak",
        "BOOT_PTR_ST": "mysz ST",
        "BOOT_PTR_AMIGA": "mysz Amiga",
        "BOOT_PTR_CX80": "trackball CX80",
        "BOOT_PTR_TABLET": "tablet dotykowy",
        "BOOT_PTR_XEM1": "mouSTer (XEM1)",
        "BOOT_BANKS": "bankow",
        "BOOT_HOLD": "Przytrzymaj SHIFT: pauza",
        "BOOT_IRQ": "Wektory",
        "BOOT_IRQ_COPIED": "OS skopiowany",
        "BOOT_IRQ_RAM": "OS w RAM",
        "BOOT_IRQ_NOCOPY": "kopia nieudana",
        "BOOT_IRQ_NOVEC": "nie utrzymane",
        "EXIT_NOCOPY": "gem4xe: brak RAM pod ROM-em systemu",
        "EXIT_NOVEC": "gem4xe: wektory nie zadzialaly",
        "EXIT_NOIRQ": "gem4xe: brak wektorow przerwan",
        "EXIT_NOVBXE": "gem4xe: VIDEO=VBXE, ale brak VBXE",
        "EXIT_NOFAR": "gem4xe: pulpit wymaga wiecej pamieci",
        "EXIT_FARKB": "KB pamieci powyzej banku $00",
        "EXIT_NOFILE": "gem4xe: brak DESKTOP.PRG na dysku",
        "EXIT_NODESK": "gem4xe: nie mozna wczytac pulpitu",
        "EXIT_ANYKEY": "Nacisnij klawisz, aby zaczac od nowa",
        "ACCFULL": "[1][Nie wszystkie akcesoria|udało się wczytać. Jest|sześć miejsc, a pamięci|może wystarczyć na mniej.][ OK ]",
    },
}

# Latin-1 to the Atari ST character set, for the letters the three
# Western languages use (EmuTOS tools/bug.c, i2a).  A character not here
# is refused rather than replaced: a translation should say what it
# means or be told it cannot.
ATARIST = {
    "¡": 0xAD, "¿": 0xA8, "«": 0xAE, "»": 0xAF, "°": 0xF8, "£": 0x9C,
    "Ä": 0x8E, "Å": 0x8F, "Æ": 0x92, "Ç": 0x80, "É": 0x90, "Ñ": 0xA5,
    "Ö": 0x99, "Ü": 0x9A, "ß": 0x9E, "à": 0x85, "á": 0xA0, "â": 0x83,
    "ä": 0x84, "å": 0x86, "æ": 0x91, "ç": 0x87, "è": 0x8A, "é": 0x82,
    "ê": 0x88, "ë": 0x89, "ì": 0x8D, "í": 0xA1, "î": 0x8C, "ï": 0x8B,
    "ñ": 0xA4, "ò": 0x95, "ó": 0xA2, "ô": 0x93, "ö": 0x94, "ù": 0x97,
    "ú": 0xA3, "û": 0x96, "ü": 0x81, "ÿ": 0x98,
}
# Each language's character set, and the font it needs beside it, if any
CHARSET = {"de": "atarist", "fr": "atarist", "es": "atarist", "pl": "latin2"}
FONT = {"pl": "l2.fnt"}
EXIT_COLS = 40          # the DOS screen's width, where the EXIT_ lines go
# The boot screen and the exit lines are on E:, the OS's text screen, in
# ATASCII: a byte from $80 up is an inverse glyph there, and the system
# font is not used.  So what goes there is plain ASCII, written the way
# 8-bit software always wrote it -- German ae oe ue ss, the others without
# their accents -- and fits src/sys/bootinfo.c's columns: a row is 36,
# a value 26 after its label.
ON_E = re.compile(r"[ -_a-z|]*")
BOOT_ROW, BOOT_VALUE = 36, 26


def encode(text, lang):
    """A translation's text as the bytes its font draws."""
    if CHARSET.get(lang) == "latin2":
        return text.encode("iso-8859-2")
    out = bytearray()
    for c in text:
        if ord(c) < 0x80:
            out.append(ord(c))
        elif c in ATARIST:
            out.append(ATARIST[c])
        else:
            raise ValueError(f"{lang}: {c!r} is not in the Atari ST set")
    return bytes(out)


ALERT = re.compile(r"\[(\d)\]\[([^\]]*)\]\[([^\]]*)\]")


def check(lang, table=None):
    """What is wrong with one translation, as a list of sentences: empty
    when it keeps every rule above."""
    t = TRANSLATIONS[lang] if table is None else table
    eng = dict(STRINGS)
    bad = []
    for name in eng:
        if name not in t:
            bad.append(f"{name}: missing")
    for name in t:
        if name not in eng:
            bad.append(f"{name}: not a string the system has")
    for name, text in t.items():
        if name not in eng:
            continue
        try:
            b = encode(text, lang)
        except (ValueError, UnicodeEncodeError) as e:
            bad.append(f"{name}: {e}")
            continue
        if len(b) > MAXLEN:
            bad.append(f"{name}: {len(b)} bytes, past LANG_MAXLEN {MAXLEN}")
        m, e = ALERT.fullmatch(text), ALERT.fullmatch(eng[name])
        if e:
            if not m:
                bad.append(f"{name}: not form_alert's [n][text][buttons]")
                continue
            lines, buttons = m.group(2).split("|"), m.group(3).split("|")
            if m.group(1) != e.group(1):
                bad.append(f"{name}: icon {m.group(1)}, English {e.group(1)}")
            if len(buttons) != len(e.group(3).split("|")):
                bad.append(f"{name}: a different number of buttons")
            if len(lines) > 5 or any(len(x) > 40 for x in lines):
                bad.append(f"{name}: more than five lines of forty")
            if any(len(x) > 20 for x in buttons):
                bad.append(f"{name}: a button wider than twenty")
        if name in BOOT_LABELS and len(text) > BOOT_LABEL:
            bad.append(f"{name}: a label of {len(text)}, past {BOOT_LABEL}")
        if name.startswith("EXIT_") and len(text) > EXIT_COLS:
            bad.append(f"{name}: {len(text)} columns, past {EXIT_COLS}")
        if name.startswith(("BOOT_", "EXIT_")):
            if not ON_E.fullmatch(text):
                bad.append(f"{name}: not plain ASCII, which E: draws")
            room = (BOOT_ROW if name == "BOOT_HOLD"
                    else BOOT_VALUE if name.startswith("BOOT_")
                    and name not in BOOT_LABELS else None)
            if room and len(text) > room:
                bad.append(f"{name}: {len(text)} columns, past {room}")
    if "ERRTOS" in t and not re.search(r"#..", t["ERRTOS"]):
        bad.append("ERRTOS: no # with two characters after it")
    return bad
# The boot screen's labels, and the columns a label gets before it is cut
# (src/sys/bootinfo.c draws them; the other BOOT_ strings are values).
BOOT_LABELS = tuple("BOOT_" + n for n in
                    "VERSION CPU IRQ MEMORY DOS CONFIG LANG VIDEO CLOCK POINTER PRINTER".split())
BOOT_LABEL = 9
assert all(len(s) <= BOOT_LABEL for n, s in STRINGS if n in BOOT_LABELS), \
    "a boot-screen label is wider than its column"


def build(strings=None, lang=None):
    """The resource: English, or `lang`'s translation in its own
    character set -- in the English order, which is the index order."""
    if lang:
        bad = check(lang)
        if bad:
            raise SystemExit(f"{lang}: " + "; ".join(bad))
        t = TRANSLATIONS[lang]
        # rsc.py writes a string as Latin-1: these bytes, unchanged
        strings = [(n, encode(t[n], lang).decode("latin-1")) for n, _ in STRINGS]
    r = rsc.Rsc()
    for _, s in (strings or STRINGS):
        r.free_string(s)
    return r


def c_source(data, path):
    lines = [f"/* {os.path.basename(path)}: LANG.RSC as the system falls back "
             f"on it, {len(data)} bytes.  Generated -- do not edit. */",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"const uint8_t FAR lang_rsc[{len(data)}] = {{"]
    for i in range(0, len(data), 12):
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in data[i:i + 12]) + ",")
    lines.append("};")
    return "\n".join(lines) + "\n"


def c_header(data, path):
    lines = [f"/* {os.path.basename(path)}: what the system says, by index.  "
             "Generated -- do not edit. */",
             "#ifndef GEM4XE_LANG_RSC_H", "#define GEM4XE_LANG_RSC_H",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"#define LANG_RSC_SIZE {len(data)}",
             f"#define LANG_NSTRING  {len(STRINGS)}",
             f"#define LANG_MAXLEN   {MAXLEN}",
             f"#define LANG_BOOT_LABEL {BOOT_LABEL}",
             "extern const uint8_t FAR lang_rsc[LANG_RSC_SIZE];"]
    lines += [f"#define LS_{name:<12s} {i}" for i, (name, _) in enumerate(STRINGS)]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) == 4 and argv[1] == "--lang":
        lang, out = argv[2], argv[3]
        data = build(lang=lang).file()
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        print(f"{out}: {lang}, {len(data)} bytes")
        return 0
    if len(argv) != 4:
        print(__doc__)
        return 2
    data = build().file()
    with open(argv[1], "wb") as f:
        f.write(data)
    for path, text in ((argv[2], c_source(data, argv[2])),
                       (argv[3], c_header(data, argv[3]))):
        with open(path, "w") as f:
            f.write(text)
    print(f"{argv[1]}: {len(data)} bytes, {len(STRINGS)} strings, "
          f"longest {MAXLEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
