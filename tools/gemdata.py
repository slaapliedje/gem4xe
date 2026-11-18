#!/usr/bin/env python3
"""The AES's built-in artwork: the mouse forms and the alert icons.

    python3 tools/gemdata.py build/gemdata.c build/gemdata.h

graf_mouse picks one of eight cursors and form_alert draws one of three
32x32 icons, and neither is anything a caller supplies -- they are the
AES's own, the same shapes on every GEM machine.  Both are transcribed
from the donor (EmuTOS aes/mforms.c and aes/gem_rsc.c, GPLv2, generated
there from mform.rsc and gem.rsc), so this file is the one place they
live: it emits C for the target and tools/aesref.py imports it for the
model.  The two therefore cannot drift.

A mouse form is what vsc_form takes and what the ST's MFORM holds: a hot
spot, one plane, the mask's colour and the data's, then sixteen words of
mask and sixteen of data -- 37 words.  The target's copies live in far
memory (gsx_mfset copies one into intin), because bank $00 has no room
for 592 bytes of artwork.

An alert icon is a BITBLK: 32 rows of 4 bytes, drawn transparently in
one colour, which is exactly what objc_draw's G_IMAGE case already
blits.  The data goes far as well; only the three BITBLK headers, which
point at it, are near.
"""
import os
import sys

MFORMS = {
    "ARROW": dict(
        hot=(0, 0), planes=1, mask_col=0, data_col=1,
        mask=[
            0xC000, 0xE000, 0xF000, 0xF800,
            0xFC00, 0xFE00, 0xFF00, 0xFF80,
            0xFFC0, 0xFFE0, 0xFE00, 0xEF00,
            0xCF00, 0x8780, 0x0780, 0x0380,
        ],
        data=[
            0x0000, 0x4000, 0x6000, 0x7000,
            0x7800, 0x7C00, 0x7E00, 0x7F00,
            0x7F80, 0x7C00, 0x6C00, 0x4600,
            0x0600, 0x0300, 0x0300, 0x0000,
        ],
    ),
    "TEXT_CRSR": dict(
        hot=(7, 7), planes=1, mask_col=0, data_col=1,
        mask=[
            0x1FF8, 0x1FF8, 0x1FF8, 0x07E0,
            0x03C0, 0x03C0, 0x03C0, 0x03C0,
            0x03C0, 0x03C0, 0x03C0, 0x03C0,
            0x07E0, 0x1FF8, 0x1FF8, 0x1FF8,
        ],
        data=[
            0x0000, 0x0E70, 0x03C0, 0x0180,
            0x0180, 0x0180, 0x0180, 0x0180,
            0x0180, 0x0180, 0x0180, 0x0180,
            0x0180, 0x03C0, 0x0E70, 0x0000,
        ],
    ),
    "HOURGLASS": dict(
        hot=(8, 8), planes=1, mask_col=0, data_col=1,
        mask=[
            0xFFFF, 0xFFFF, 0xFFFF, 0x7FFE,
            0x7FFE, 0x3FFC, 0x1FF8, 0x0FF0,
            0x0FF0, 0x1FF8, 0x3FFC, 0x7FFE,
            0x7FFE, 0xFFFF, 0xFFFF, 0xFFFF,
        ],
        data=[
            0x0000, 0x7FFE, 0x2004, 0x1008,
            0x1448, 0x0AB0, 0x0560, 0x02C0,
            0x0340, 0x04A0, 0x0910, 0x1088,
            0x12A8, 0x3554, 0x7FFE, 0x0000,
        ],
    ),
    "POINT_HAND": dict(
        hot=(0, 0), planes=1, mask_col=0, data_col=1,
        mask=[
            0x3000, 0x7800, 0x7C00, 0x3E07,
            0x1F0F, 0x0F9E, 0x07DE, 0x07FE,
            0x1FFE, 0x3FFF, 0x7FFF, 0x7FFE,
            0x3FFE, 0x1FFE, 0x0FFF, 0x01FF,
        ],
        data=[
            0x3000, 0x4800, 0x4400, 0x2207,
            0x1109, 0x0892, 0x0452, 0x0632,
            0x1912, 0x2481, 0x5241, 0x4982,
            0x2602, 0x1802, 0x0E01, 0x0180,
        ],
    ),
    "FLAT_HAND": dict(
        hot=(8, 8), planes=1, mask_col=0, data_col=1,
        mask=[
            0x0000, 0x0180, 0x0FF0, 0x1FFE,
            0x1FFF, 0x1FFF, 0x1FFF, 0xFFFF,
            0xFFFF, 0xFFFF, 0x7FFF, 0x3FFF,
            0x1FFE, 0x0FFC, 0x0FFC, 0x1FFE,
        ],
        data=[
            0x0000, 0x0D80, 0x1270, 0x124E,
            0x1249, 0x1249, 0x1249, 0xF249,
            0x9001, 0x9801, 0x4401, 0x4001,
            0x3002, 0x0804, 0x0804, 0x1FFE,
        ],
    ),
    "THIN_CROSS": dict(
        hot=(7, 7), planes=1, mask_col=0, data_col=1,
        mask=[
            0x0000, 0x0380, 0x0380, 0x0380,
            0x0380, 0x0380, 0x0380, 0x7FFC,
            0x7FFC, 0x7FFC, 0x0380, 0x0380,
            0x0380, 0x0380, 0x0380, 0x0380,
        ],
        data=[
            0x0000, 0x0000, 0x0100, 0x0100,
            0x0100, 0x0100, 0x0100, 0x0100,
            0x3FF8, 0x0100, 0x0100, 0x0100,
            0x0100, 0x0100, 0x0100, 0x0000,
        ],
    ),
    "THICK_CROSS": dict(
        hot=(8, 8), planes=1, mask_col=0, data_col=1,
        mask=[
            0x0000, 0x07C0, 0x07C0, 0x07C0,
            0x07C0, 0x07C0, 0xFFFE, 0xFFFE,
            0xFFFE, 0xFFFE, 0xFFFE, 0x07C0,
            0x07C0, 0x07C0, 0x07C0, 0x07C0,
        ],
        data=[
            0x0000, 0x0000, 0x0380, 0x0380,
            0x0380, 0x0380, 0x0380, 0x7FFC,
            0x7FFC, 0x7FFC, 0x0380, 0x0380,
            0x0380, 0x0380, 0x0380, 0x0000,
        ],
    ),
    "OUTLN_CROSS": dict(
        hot=(8, 8), planes=1, mask_col=0, data_col=1,
        mask=[
            0x07E0, 0x07E0, 0x0660, 0x0660,
            0x0660, 0xFE7F, 0xFE7F, 0xC003,
            0xC003, 0xFE7F, 0xFE7F, 0x0660,
            0x0660, 0x0660, 0x07E0, 0x07E0,
        ],
        data=[
            0x0000, 0x03C0, 0x0240, 0x0240,
            0x0240, 0x0240, 0x7E7E, 0x4002,
            0x4002, 0x7E7E, 0x0240, 0x0240,
            0x0240, 0x0240, 0x03C0, 0x0000,
        ],
    ),
}

ALERT_ICONS = {
    "NOTE": [
        0x0000, 0x0000, 0x0001, 0x8000,
        0x0002, 0x4000, 0x0002, 0x4000,
        0x0004, 0x2000, 0x0005, 0xA000,
        0x0009, 0x9000, 0x000B, 0xD000,
        0x0013, 0xC800, 0x0017, 0xE800,
        0x0026, 0x6400, 0x002C, 0x3400,
        0x004C, 0x3200, 0x005C, 0x3A00,
        0x009C, 0x3900, 0x00BC, 0x3D00,
        0x013C, 0x3C80, 0x017E, 0x7E80,
        0x027E, 0x7E40, 0x02FE, 0x7F40,
        0x04FE, 0x7F20, 0x05FE, 0x7FA0,
        0x09FF, 0xFF90, 0x0BFF, 0xFFD0,
        0x13FE, 0x7FC8, 0x17FC, 0x3FE8,
        0x27FC, 0x3FE4, 0x2FFE, 0x7FF4,
        0x4FFF, 0xFFF2, 0x4000, 0x0002,
        0x7FFF, 0xFFFE, 0x0000, 0x0000,
    ],
    "QUEST": [
        0x0000, 0x0000, 0x7FFF, 0xFFFE,
        0x4000, 0x0002, 0x4FFF, 0xFFF2,
        0x2FFF, 0xFFF4, 0x27F8, 0x3FE4,
        0x17E0, 0x1FE8, 0x13C0, 0x0FC8,
        0x0BC3, 0x07D0, 0x09E7, 0x8790,
        0x05FF, 0x87A0, 0x04FF, 0x8720,
        0x02FF, 0x0F40, 0x027E, 0x1E40,
        0x017C, 0x3E80, 0x013C, 0x7C80,
        0x00BC, 0x7D00, 0x009F, 0xF900,
        0x005E, 0x7A00, 0x004C, 0x3200,
        0x002C, 0x3400, 0x0026, 0x6400,
        0x0017, 0xE800, 0x0013, 0xC800,
        0x000B, 0xD000, 0x0009, 0x9000,
        0x0005, 0xA000, 0x0004, 0x2000,
        0x0002, 0x4000, 0x0002, 0x4000,
        0x0001, 0x8000, 0x0000, 0x0000,
    ],
    "STOP": [
        0x0000, 0x0000, 0x0000, 0x0000,
        0x003F, 0xFC00, 0x0040, 0x0200,
        0x009F, 0xF900, 0x013F, 0xFC80,
        0x027F, 0xFE40, 0x04FF, 0xFF20,
        0x09FF, 0xFF90, 0x13FF, 0xFFC8,
        0x27EF, 0xF7E4, 0x2FC7, 0xE3F4,
        0x2FE3, 0xC7F4, 0x2FF1, 0x8FF4,
        0x2FF8, 0x1FF4, 0x2FFC, 0x3FF4,
        0x2FFC, 0x3FF4, 0x2FF8, 0x1FF4,
        0x2FF1, 0x8FF4, 0x2FE3, 0xC7F4,
        0x2FC7, 0xE3F4, 0x27EF, 0xF7E4,
        0x13FF, 0xFFC8, 0x09FF, 0xFF90,
        0x04FF, 0xFF20, 0x027F, 0xFE40,
        0x013F, 0xFC80, 0x009F, 0xF900,
        0x0040, 0x0200, 0x003F, 0xFC00,
        0x0000, 0x0000, 0x0000, 0x0000,
    ],
}

MFORM_NAMES = ["ARROW", "TEXT_CRSR", "HOURGLASS", "POINT_HAND",
               "FLAT_HAND", "THIN_CROSS", "THICK_CROSS", "OUTLN_CROSS"]
ICON_NAMES = ["NOTE", "QUEST", "STOP"]

MFORM_WORDS = 37                    # what vsc_form's intin holds
ICON_WB, ICON_HL = 4, 32            # a 32x32 icon, bytes per row and rows


def mform_words(name):
    """One form as the 37 words vsc_form wants, in its order: hot x, hot
    y, planes, mask colour, data colour, mask, data."""
    f = MFORMS[name]
    return ([f["hot"][0], f["hot"][1], f["planes"], f["mask_col"], f["data_col"]]
            + f["mask"] + f["data"])


def icon_bytes(name):
    """One icon as the bytes a BITBLK points at: MSB first, as the VDI's
    vrt_cpyfm reads a one-plane form."""
    out = bytearray()
    for w in ALERT_ICONS[name]:
        out += bytes((w >> 8, w & 0xFF))
    return bytes(out)


def emit(c_path, h_path):
    """The far tables, and a header naming them."""
    lines = ['/* Generated by tools/gemdata.py -- do not edit. */',
             '#include <stdint.h>', '#include "portab.h"', '#include "aes/aes.h"', '',
             '/* The eight mouse forms, 37 words each, in graf_mouse order.  On the',
             ' * 6502 in the bank of src/aes/graf.c, gsx_mfform\'s, its only reader:',
             ' * resident memory has not 592 bytes for them (docs/6502.md, 4e). */',
             '#ifdef __CALYPSI_TARGET_6502__',
             '#define GEM_MFORMS_AT BANK_DATA("graf")',
             '#else',
             '#define GEM_MFORMS_AT',
             '#endif',
             'const WORD FAR gem_mforms[%d][%d] GEM_MFORMS_AT = {' % (len(MFORM_NAMES), MFORM_WORDS)]
    for name in MFORM_NAMES:
        w = mform_words(name)
        lines.append('    {   /* %s */' % name)
        # (WORD) on every one: a mask word like 0xC000 does not fit a
        # signed 16-bit int, and the compiler is right to say so
        for i in range(0, MFORM_WORDS, 6):
            lines.append('        '
                         + ', '.join('(WORD)0x%04X' % x for x in w[i:i + 6]) + ',')
        lines.append('    },')
    lines.append('};')
    lines.append('')
    lines.append('/* The three alert icons, 32 rows of 4 bytes, MSB first.  On the 6502')
    lines.append(' * in alert__bank, which tools/bsp6502/a6.scm puts in alert.c\'s bank (docs/6502.md, 5b-5). */')
    lines += ['#ifdef __CALYPSI_TARGET_6502__', '#define GEM_ICONS_AT BANK_DATA("alert")',
              '#else', '#define GEM_ICONS_AT', '#endif']
    for name in ICON_NAMES:
        data = icon_bytes(name)
        lines.append('const uint8_t FAR gem_icon_%s[%d] GEM_ICONS_AT = {'
                     % (name.lower(), len(data)))
        for i in range(0, len(data), 12):
            lines.append('    ' + ', '.join('0x%02X' % b for b in data[i:i + 12]) + ',')
        lines.append('};')
    lines.append('')
    with open(c_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    hd = ['/* Generated by tools/gemdata.py -- do not edit. */',
          '#ifndef GEMDATA_H', '#define GEMDATA_H', '#include "portab.h"', '',
          '#define GEM_MFORM_WORDS %d' % MFORM_WORDS,
          '#define GEM_MFORMS      %d' % len(MFORM_NAMES),
          '#define GEM_ICON_WB     %d' % ICON_WB,
          '#define GEM_ICON_HL     %d' % ICON_HL, '',
          'extern const WORD FAR gem_mforms[GEM_MFORMS][GEM_MFORM_WORDS];']
    for name in ICON_NAMES:
        hd.append('extern const uint8_t FAR gem_icon_%s[%d];'
                  % (name.lower(), ICON_WB * ICON_HL))
    hd += ['', '#endif']
    with open(h_path, 'w') as f:
        f.write('\n'.join(hd) + '\n')


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(argv[0])) or '.', exist_ok=True)
    emit(argv[0], argv[1])
    print(f"{argv[0]}: {len(MFORM_NAMES)} mouse forms, {len(ICON_NAMES)} alert icons")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
