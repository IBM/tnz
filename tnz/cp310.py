"""Python Character Mapping Codec cp310
Usage: from tnz import cp310 as _
See https://en.wikipedia.org/wiki/Code_page_310.
See CP00310.txt in
ftp://ftp.software.ibm.com/software/globalization/gcoc/attachments

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
import codecs
from . import __version__

__author__ = "Neil Johnson"

# Codec APIs


class _Codec(codecs.Codec):
    def encode(self, input, errors='strict'):
        return codecs.charmap_encode(input, errors, encoding_table)

    def decode(self, input, errors='strict'):
        return codecs.charmap_decode(input, errors, DECODING_TABLE)


class _IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input, final=False):
        return codecs.charmap_encode(
            input, self.errors, encoding_table)[0]


class _IncrementalDecoder(codecs.IncrementalDecoder):
    def decode(self, input, final=False):
        return codecs.charmap_decode(
            input, self.errors, DECODING_TABLE)[0]


class _StreamWriter(_Codec, codecs.StreamWriter):
    pass


class _StreamReader(_Codec, codecs.StreamReader):
    pass

# encodings module API


def _getregentry():
    return codecs.CodecInfo(
        name='cp310',
        encode=_Codec().encode,
        decode=_Codec().decode,
        incrementalencoder=_IncrementalEncoder,
        incrementaldecoder=_IncrementalDecoder,
        streamreader=_StreamReader,
        streamwriter=_StreamWriter,
    )


# Decoding Table

DECODING_TABLE = (
    '\U0000FFFD'  # 0x00 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x01 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x02 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x03 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x04 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x05 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x06 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x07 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x08 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x09 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x0F -> INVALID CHARACTER
    '\U0000FFFD'  # 0x10 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x11 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x12 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x13 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x14 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x15 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x16 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x17 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x18 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x19 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x1F -> INVALID CHARACTER
    '\U0000FFFD'  # 0x20 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x21 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x22 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x23 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x24 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x25 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x26 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x27 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x28 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x29 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x2F -> INVALID CHARACTER
    '\U0000FFFD'  # 0x30 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x31 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x32 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x33 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x34 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x35 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x36 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x37 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x38 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x39 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x3F -> INVALID CHARACTER
    ' '           # 0x40 -> SPACE
    '\U0001d434'  # 0x41 -> 1D434 0332
    '\U0001d435'  # 0x42 -> 1D435 0332
    '\U0001d436'  # 0x43 -> 1D436 0332
    '\U0001d437'  # 0x44 -> 1D437 0332
    '\U0001d438'  # 0x45 -> 1D438 0332
    '\U0001d439'  # 0x46 -> 1D439 0332
    '\U0001d43a'  # 0x47 -> 1D43A 0332
    '\U0001d43b'  # 0x48 -> 1D43B 0332
    '\U0001d43c'  # 0x49 -> 1D43C 0332
    '\U0000FFFD'  # 0x4A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x4B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x4C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x4D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x4E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x4F -> INVALID CHARACTER
    '\U0000FFFD'  # 0x50 -> INVALID CHARACTER
    '\U0001d43d'  # 0x51 -> 1D43D 0332
    '\U0001d43e'  # 0x52 -> 1D43E 0332
    '\U0001d43f'  # 0x53 -> 1D43F 0332
    '\U0001d440'  # 0x54 -> 1D440 0332
    '\U0001d441'  # 0x55 -> 1D441 0332
    '\U0001d442'  # 0x56 -> 1D442 0332
    '\U0001d443'  # 0x57 -> 1D443 0332
    '\U0001d444'  # 0x58 -> 1D444 0332
    '\U0001d445'  # 0x59 -> 1D445 0332
    '\U0000FFFD'  # 0x5A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x5B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x5C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x5D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x5E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x5F -> INVALID CHARACTER
    '\U0000FFFD'  # 0x60 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x61 -> INVALID CHARACTER
    '\U0001d446'  # 0x62 -> 1D446 0332
    '\U0001d447'  # 0x63 -> 1D447 0332
    '\U0001d448'  # 0x64 -> 1D448 0332
    '\U0001d449'  # 0x65 -> 1D449 0332
    '\U0001d44a'  # 0x66 -> 1D44a 0332
    '\U0001d44b'  # 0x67 -> 1D44b 0332
    '\U0001d44c'  # 0x68 -> 1D44c 0332
    '\U0001d44d'  # 0x69 -> 1D44d 0332
    '\U0000FFFD'  # 0x6A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x6B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x6C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x6D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x6E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x6F -> INVALID CHARACTER
    '\U000022c4'  # 0x70 -> 22C4 / 25C6
    '\U00002227'  # 0x71 ->
    '\U000000a8'  # 0x72 ->
    '\U0000233b'  # 0x73 ->
    '\U00002378'  # 0x74 ->
    '\U00002377'  # 0x75 ->
    '\U000022a2'  # 0x76 ->
    '\U000022a3'  # 0x77 ->
    '\U00002228'  # 0x78 ->
    '\U0000FFFD'  # 0x79 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7A -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7B -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7C -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7D -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7E -> INVALID CHARACTER
    '\U0000FFFD'  # 0x7F -> INVALID CHARACTER
    '\U0000223c'  # 0x80 -> 223C / 007E
    '\U00002551'  # 0x81 ->
    '\U00002550'  # 0x82 ->
    '\U000023b8'  # 0x83 ->
    '\U000023b9'  # 0x84 ->
    '\U00002502'  # 0x85 -> 2502 / 23A5 (23a5 uncommon in font?)
    '\U0000FFFD'  # 0x86 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x87 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x88 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x89 -> INVALID CHARACTER
    '\U00002191'  # 0x8A ->
    '\U00002193'  # 0x8B ->
    '\U00002264'  # 0x8C ->
    '\U00002308'  # 0x8D ->
    '\U0000230a'  # 0x8E ->
    '\U00002192'  # 0x8F ->
    '\U00002395'  # 0x90 ->
    '\U0000258c'  # 0x91 ->
    '\U00002590'  # 0x92 ->
    '\U00002580'  # 0x93 ->
    '\U00002584'  # 0x94 ->
    '\U00002588'  # 0x95 -> 2588 / 25A0
    '\U0000FFFD'  # 0x96 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x97 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x98 -> INVALID CHARACTER
    '\U0000FFFD'  # 0x99 -> INVALID CHARACTER
    '\U00002283'  # 0x9A ->
    '\U00002282'  # 0x9B ->
    '\U00002311'  # 0x9C -> 2311 / 00A4
    '\U000025cb'  # 0x9D ->
    '\U000000b1'  # 0x9E ->
    '\U00002190'  # 0x9F ->
    '\U000000af'  # 0xA0 -> 00AF / 203E
    '\U000000b0'  # 0xA1 ->
    '\U00002500'  # 0xA2 ->
    '\U00002219'  # 0xA3 -> 2219 / 2022
    '\U00002099'  # 0xA4 ->
    '\U0000FFFD'  # 0xA5 -> INVALID CHARACTER
    '\U0000FFFD'  # 0xA6 -> INVALID CHARACTER
    '\U0000FFFD'  # 0xA7 -> INVALID CHARACTER
    '\U0000FFFD'  # 0xA8 -> INVALID CHARACTER
    '\U0000FFFD'  # 0xA9 -> INVALID CHARACTER
    '\U00002229'  # 0xAA ->
    '\U0000222a'  # 0xAB ->
    '\U000022a5'  # 0xAC ->
    '['           # 0xAD ->
    '\U00002265'  # 0xAE ->
    '\U00002218'  # 0xAF ->
    '\U0000237a'  # 0xB0 ->
    '\U00002208'  # 0xB1 -> 2208 / 03B5
    '\U00002373'  # 0xB2 ->
    '\U00002374'  # 0xB3 ->
    '\U00002375'  # 0xB4 ->
    '\U0000FFFD'  # 0xB5 -> INVALID CHARACTER
    '\U000000d7'  # 0xB6 ->
    '\U00002216'  # 0xB7 -> 2216 005C
    '\U000000f7'  # 0xB8 ->
    '\U0000FFFD'  # 0xB9 -> INVALID CHARACTER
    '\U00002207'  # 0xBA ->
    '\U00002206'  # 0xBB ->
    '\U000022a4'  # 0xBC ->
    ']'           # 0xBD ->
    '\U00002260'  # 0xBE ->
    '\U00002502'  # 0xBF -> 2223 / 2502
    '\U0000007b'  # 0xC0 ->
    '\U0000207d'  # 0xC1 ->
    '\U0000207a'  # 0xC2 -> 207A / 002B
    '\U000025a0'  # 0xC3 -> 25A0 / 220E
    '\U00002514'  # 0xC4 ->
    '\U0000250c'  # 0xC5 ->
    '\U0000251c'  # 0xC6 ->
    '\U00002534'  # 0xC7 -> or 22A5?
    '\U000000a7'  # 0xC8 ->
    '\U0000FFFD'  # 0xC9 -> INVALID CHARACTER
    '\U00002372'  # 0xCA ->
    '\U00002371'  # 0xCB ->
    '\U00002337'  # 0xCC ->
    '\U0000233d'  # 0xCD ->
    '\U00002342'  # 0xCE ->
    '\U00002349'  # 0xCF ->
    '\U0000007d'  # 0xD0 ->
    '\U0000207e'  # 0xD1 ->
    '\U0000207b'  # 0xD2 -> 207B / 002D
    '\U0000253c'  # 0xD3 ->
    '\U00002518'  # 0xD4 ->
    '\U00002510'  # 0xD5 ->
    '\U00002524'  # 0xD6 ->
    '\U0000252c'  # 0xD7 ->
    '\U000000b6'  # 0xD8 ->
    '\U0000FFFD'  # 0xD9 -> INVALID CHARACTER
    '\U00002336'  # 0xDA ->
    '\U000001c3'  # 0xDB -> 01C3 / 0021
    '\U00002352'  # 0xDC ->
    '\U0000234b'  # 0xDD ->
    '\U0000235e'  # 0xDE ->
    '\U0000235d'  # 0xDF ->
    '\U00002261'  # 0xE0 ->
    '\U00002081'  # 0xE1 ->
    '\U00002082'  # 0xE2 ->
    '\U00002083'  # 0xE3 ->
    '\U00002364'  # 0xE4 ->
    '\U00002365'  # 0xE5 ->
    '\U0000236a'  # 0xE6 ->
    '\U000020ac'  # 0xE7 ->
    '\U0000FFFD'  # 0xE8 -> INVALID CHARACTER
    '\U0000FFFD'  # 0xE9 -> INVALID CHARACTER
    '\U0000233f'  # 0xEA ->
    '\U00002340'  # 0xEB ->
    '\U00002235'  # 0xEC ->
    '\U00002296'  # 0xED ->
    '\U00002339'  # 0xEE ->
    '\U00002355'  # 0xEF ->
    '\U00002070'  # 0xF0 ->
    '\U000000b9'  # 0xF1 ->
    '\U000000b2'  # 0xF2 ->
    '\U000000b3'  # 0xF3 ->
    '\U00002074'  # 0xF4 ->
    '\U00002075'  # 0xF5 ->
    '\U00002076'  # 0xF6 ->
    '\U00002077'  # 0xF7 ->
    '\U00002078'  # 0xF8 ->
    '\U00002079'  # 0xF9 ->
    '\U0000FFFD'  # 0xFA -> INVALID CHARACTER
    '\U0000236b'  # 0xFB ->
    '\U00002359'  # 0xFC ->
    '\U0000235f'  # 0xFD ->
    '\U0000234e'  # 0xFE ->
    '\U0000FFFD'  # 0xFF -> INVALID CHARACTER
)

# Encoding table
encoding_table = codecs.charmap_build(DECODING_TABLE)

# automatically register


def _codec_search(encoding):
    if encoding == 'cp310':
        return _getregentry()


codecs.register(_codec_search)
