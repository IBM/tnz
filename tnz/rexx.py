"""useful rexx functions

This module is intended to help with porting ATI code to python.
ATI had several rexx-like functions that will likely be in this
module as python functions. Other functions are included that may
be useful in parsing strings in a rexx-like manner.

Some of these functions have enhancements on top of the rexx
function. Enhancments include using a negative index/position or
length to indicate a position relative to the END of the string. See
individual functions for details.

USAGE
    from rexx import *

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
import re as _re
from . import __version__

__author__ = "Neil Johnson"


def copies(string, cnt):
    """returns cnt concatenated copies of string. The cnt must be a
    positive whole number or zero."""

    if cnt < 0:
        raise ValueError("cnt="+repr(cnt)+" is not valid")

    return str(string)*cnt


def delword(string, sw_or_n, len_or_si=None):
    """returns string after deleting the substring that starts at
    the nth word and is of length blank-delimited words. If you omit
    length, or if length is greater than the number of words from n
    to the end of string, the function deletes the remaining words in
    string (including the nth word). The length must be a positive
    whole number or zero. The n must be a positive whole number. If n
    is greater than the number of words in string, the function
    returns string unchanged. The string deleted includes any blanks
    following the final word involved but none of the blanks
    preceding the first word involved."""

    if isinstance(sw_or_n, str):
        sword = sw_or_n
        sidx = len_or_si
        if sidx is None:
            sidx = 1

        pos1 = wordpos(string, sword, sidx)
        if pos1 <= 0:
            return string

        cnt = words(string)
        if cnt <= 0:
            return string

        return delword(string, pos1, cnt)

    idx = sw_or_n
    if idx <= 0:
        raise ValueError("n must be greater than zero")

    length = len_or_si
    if length is None:
        sidx = wordindex(string, idx)
        if not sidx:
            return string

        return string[0:sidx-1]

    sidx = wordindex(string, idx+length)
    if not sidx:
        return delword(string, idx)

    return delword(string, idx)+string[sidx-2:].lstrip()


def index(haystack, needle, start=1):
    """returns the character position of one string, needle, in
    another, haystack, or returns 0 if the string needle is not found
    or is a null string. By default the search starts at the first
    character of haystack (start has the value 1). You can override
    this by specifying a different start point, which must be a
    positive whole number.
    """
    if start <= 0:
        raise ValueError("start="+repr(start)+" is not valid")

    return 1+haystack.find(needle, start-1)


def left(string, length, pad=" "):
    """returns a string of length length, containing the leftmost
    length characters of string. The string returned is padded with
    pad characters (or truncated) on the right as needed. The default
    pad character is a blank. length must be a positive whole number
    or zero.
    """
    if length < 0:
        raise ValueError("length="+repr(length)+" is not valid")

    return substr(string, 1, length, pad=pad)


def length(string):
    """returns the length of string.
    """
    return len(string)


def pos(needle, haystack, start=1):
    """returns the character position of one string, needle, in
    another, haystack, or returns 0 if the string needle is not found
    or is a null string. By default the search starts at the first
    character of haystack (start has the value 1). You can override
    this by specifying a different start point, which must be a
    positive whole number.
    """
    if start <= 0:
        raise ValueError("start="+repr(start)+" is not valid")

    return 1+haystack.find(needle, start-1)


def right(string, length, pad=" "):
    """returns a string of length length containing the rightmost
    length characters of string. The string returned is padded with
    pad characters (or truncated) on the left as needed. The default
    pad character is a blank. The length must be a positive whole
    number or zero."""

    if length < 0:
        raise ValueError("length="+repr(length)+" is not valid")

    return substr(string, -1, -length, pad=pad)


def space(string, cnt=1, pad=" "):
    """returns the blank-delimited words in string with cnt pad
    characters between each word. If you specify cnt, it must be a
    positive whole number or zero. If it is 0, all blanks are
    removed. Leading and trailing blanks are always removed. The
    default for cnt is 1, and the default pad character is a blank.
    """
    if cnt < 0:
        raise ValueError("cnt="+repr(cnt)+" is not valid")

    return (pad * cnt).join(string.split())


def strip(string, option="B", char=" "):
    """returns string with leading or trailing characters or both
    removed, based on the option you specify. The following are valid
    options. (Only the capitalized letter is needed; all characters
    following it are ignored.)

    Both
        removes both leading and trailing characters from string.
        This is the default.

    Leading
        removes leading characters from string.

    Trailing
        removes trailing characters from string.

    The third argument, char, specifies the character to be removed,
    and the default is a blank. With rexx, if you specify char, it
    must be exactly one character long. With this function, all
    characters specified in the char string are considered for
    removal from string.

    Here are some examples:

    strip('  ab c  ')           -> 'ab c'
    strip('  ab c  ','L')       -> 'ab c  '
    strip('  ab c  ','t')       -> '  ab c'
    strip('12.7000',char='0')   -> '12.7'
    strip('0012.700',char='0')  -> '12.7'
    """

    if option[0] == "B" or option[0] == "b":
        return string.strip(char)
    elif option[0] == "L" or option[0] == "l":
        return string.lstrip(char)
    elif option[0] == "T" or option[0] == "t":
        return string.rstrip(char)
    else:
        raise ValueError("option="+repr(option)+" is not valid")


def substr(string, idx, length=None, pad=" "):
    """returns the substring of string that begins at the idx'th
    character and is of length length, padded with pad if necessary.

    In rexx, idx must be a positive whole number. In this function, idx
    can also be negative. When idx is negative, the begining of the
    substring is relative to the end of string like in python. For
    example, -1 refers to the last chararacter in string and -2
    refers to the second to last character in string and so on.

    In this function, length can be negative. A negative length
    means that idx refers to the last character in the substring
    instead of the first. The length of the returned substring is
    always abs(length).

    If you omit length, the rest of the string is returned. The
    default pad character is a blank.

    Here are some examples:

    substr('abc',2)          ->    'bc'
    substr('abc',2,4)        ->    'bc  '
    substr('abc',2,6,'.')    ->    'bc....'

    See also the 'left' and 'right' functions.
    """
    if not idx:
        raise ValueError(f"n={idx} is not valid")

    if length == 0:
        return ""

    if length is None:
        if idx < 0:
            return string[:idx]

        return string[idx-1:]

    if idx > 0 and length >= 0:
        string = string[idx-1:idx-1+length]

    elif idx > 0:
        if idx + length >= 0:
            string = string[idx+length:idx]
        else:
            string = string[:idx]

    elif length >= 0:
        if idx + length < 0:
            string = string[idx:idx+length]
        else:
            string = string[idx:]

    elif idx < -1:
        string = string[idx+length+1:idx+1]
    else:
        string = string[idx+length+1:]

    padding = copies(pad, abs(length) - len(string))
    if length >= 0:
        return string + padding

    return padding + string


def subword(string, wpos, length=None):
    """returns the substring of string that starts at the nth word,
    and is up to length blank-delimited words. The n must be a
    positive whole number. If you omit length, it defaults to the
    number of remaining words in string. The returned string never
    has leading or trailing blanks, but includes all blanks between
    the selected words.
    """
    if wpos <= 0:
        raise ValueError("n must be a positive whole number")

    if length is None:
        cpos = wordindex(string, wpos)
        if not cpos:
            return ""

        return string[cpos-1:].strip()

    if length < 0:
        raise ValueError("length cannot be negative")

    if not length:
        return ""

    cpos = wordindex(string, wpos+length)
    if not cpos:
        return subword(string, wpos)

    return subword(string[:cpos-2], wpos)


def word(string, wpos):
    """returns the nth blank-delimited word in string or returns the
    null string if fewer than n words are in string. The n must be a
    positive whole number. This function is exactly equivalent to
    subword(string,n,1).
    """
    return subword(string, wpos, 1)


def wordindex(string, wpos):
    """returns the position of the first character in the nth
    blank-delimited word in string or returns 0 if fewer than n words
    are in string. The n must be a positive whole number.
    """
    if wpos <= 0:
        raise ValueError("n must be a positive whole number")

    i = 0
    for mat in _re.finditer(r"\S+", string):
        i += 1
        if i == wpos:
            return 1 + mat.start()

    return 0


def wordpos(phrase, string, start=1):
    """returns the word number of the first word of phrase found in
    string or returns 0 if phrase contains no words or if phrase is
    not found. Multiple blanks between words in either phrase or
    string are treated as a single blank for the comparison, but
    otherwise the words must match exactly.

    By default the search starts at the first word in string. You can
    override this by specifying start (which must be positive), the
    word at which to start the search."""

    ws2 = " "+space(subword(string, start))+" "
    i = ws2.find(" "+space(phrase)+" ")
    if i < 0:
        return 0

    return start+words(ws2[0:i])


def words(sentence):
    """returns the number of blank-delimited words in string.
    """
    return sum(1 for _ in _re.finditer(r"\S+", sentence))
