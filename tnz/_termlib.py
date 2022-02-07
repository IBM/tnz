"""tnz terminal library

Provided curses function for tnz.

USAGE
    from ._termlib import Term as curses

REFERENCES:
    https://xtermjs.org/docs/api/vtfeatures
    https://en.wikipedia.org/wiki/ANSI_escape_code
    https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
    https://www.xfree86.org/current/ctlseqs.html
    https://docs.microsoft.com/windows/console/
        console-virtual-terminal-sequences

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""

import asyncio
import atexit
from enum import IntEnum, auto
from functools import wraps
import logging
import os
import platform
import select
import signal
import sys
import time

from . import _sigx as sigx

_osname = platform.system()
if _osname == "Windows":
    import ctypes
    import socket
    import threading

else:
    import fcntl
    import termios
    import tty

__author__ = "Neil Johnson"

_logger = logging.getLogger("tnz.termlib")


class _TermlibError(Exception):
    pass


class _TermlibTimeout(_TermlibError):
    pass


def _log_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except _TermlibError:
            raise

        except Exception:
            _logger.exception("error in %s", func.__name__)
            raise

    return wrapper


def _curses_init(cls):
    class _Key(IntEnum):
        KEY_ENTER = 256
        KEY_BACKSPACE = auto()
        KEY_EXIT = auto()
        KEY_SR = auto()
        KEY_SF = auto()
        KEY_SRIGHT = auto()
        KEY_SLEFT = auto()
        KEY_MULTIPLY = auto()
        KEY_ADD = auto()
        KEY_SEPARATOR = auto()
        KEY_SUBTRACT = auto()
        KEY_DECIMAL = auto()
        KEY_DIVIDE = auto()
        KEY_EQUAL = auto()
        KEY_KP_0 = auto()
        KEY_KP_1 = auto()
        KEY_KP_2 = auto()
        KEY_KP_3 = auto()
        KEY_KP_4 = auto()
        KEY_KP_5 = auto()
        KEY_KP_6 = auto()
        KEY_KP_7 = auto()
        KEY_KP_8 = auto()
        KEY_KP_9 = auto()
        KEY_FIND = auto()
        KEY_SELECT = auto()
        KEY_F1 = auto()
        KEY_F2 = auto()
        KEY_F3 = auto()
        KEY_F4 = auto()
        KEY_A1 = auto()
        KEY_A3 = auto()
        KEY_B2 = auto()
        KEY_BEG = auto()

    maxval = 0
    for key in _Key:
        maxval = key.value
        setattr(cls, key.name, maxval)

    for i, key in enumerate(set(cls._seqname.values()), maxval+1):
        setattr(cls, key, i)

    return cls


@_curses_init
class Term():
    """Like curses, but only function needed by tnz.

    Use initscr() to create an instance.
    """
    def __init__(self):
        """For use only by initscr().
        """
        if self.__stdscr:
            raise self.error("init already done")

        self.__registered_atexit = False
        self.__init()

        try:
            self.def_shell_mode()

        except Exception:
            raise self.error("init failed")

        try:
            self.refresh()

        except Exception:
            self.reset_shell_mode()
            raise self.error("init failed")

    # Methods

    def addstr(self, *args):
        """Write string to program mode screen.
        """
        argc = len(args)
        if argc == 4:
            posy, posx, text, attr = args
            self.move(posy, posx)

        elif argc == 3:
            posy, posx, text = args
            attr = self.__dflt_attr
            self.move(posy, posx)

        elif argc == 2:
            text, attr = args

        elif argc == 1:
            text = args[0]
            attr = self.__dflt_attr

        else:
            raise ValueError("need [y, x,] str[, attr]")

        if text:
            # concerns about non-printable characters?
            # 3270 screens sometimes have them

            pendlist = self.__pendlist

            if self.__pendmove:
                self.__pendmove = False
                if not pendlist:
                    self.__firstmove = True

                pendlist.extend(self.__cup())

            self.__change_attr(attr)
            pendlist.append(text)

    def attroff(self, attr):
        """Disable identified A_ATTRIBUTES attribute(s)
        in default attribute.
        """
        if attr & ~self.A_ATTRIBUTES:
            raise ValueError(f"attr={attr} not valid")

        self.__dflt_attr &= ~attr

    def attron(self, attr):
        """Set default attribute to A_NORMAL
        or enable identified A_ATTRIBUTES attribute(s)
        in default attribute.
        """
        if attr == self.A_NORMAL:
            self.__dflt_attr = attr
            return

        if attr & ~self.A_ATTRIBUTES:
            raise ValueError(f"attr={attr} not valid")

        self.__dflt_attr |= attr

    def clear(self):
        """Erase program screen.
        """
        _logger.debug("clear()")
        self.erase()

    def erase(self):
        """Erase program screen.
        """
        _logger.debug("erase()")
        self.__pendtext = False
        self.__pendmove = True
        self.__firstmove = False

        # It is not clear if the Erase function will
        # erase using the current color or erase using
        # the default color. To be consistent, we will
        # set the current color to the default color
        # before the Erase.

        # Is CUP 1,1 followed by ED after cursor better
        # than ED entire screen? It might if it prevents
        # some terminals from adding the screen to the
        # 'scrolling buffer'.

        self.__pendlist.clear()
        prog_maxyx = Term.prog_maxyx
        self.__pend_maxyx = prog_maxyx
        if prog_maxyx:
            if Term.__alt_screen or prog_maxyx != self.__maxyx:
                nlines, ncols = prog_maxyx
                # ESC [ 8 ; nlines ; ncols t  -> set char width/height
                self.__pendlist.append(f"\x1b[8;{nlines};{ncols}t")

        if self.__flash_reverse:
            self.__pend_attr = self.A_REVERSE
            columns, lines = self.getmaxyx()
            cnt = columns * lines - 1
            self.__pendlist.append(f"\x1b[;7m\x1b[H \x1b[{cnt}b")
        else:
            self.__pend_attr = self.A_NORMAL
            # self.__pendlist.append("\x1b[m\x1b[2J")
            self.__pendlist.append("\x1b[m\x1b[H\x1b[J")

    @_log_errors
    def getkey(self, y=None, x=None, timeout=0, onlymouse=False):
        """Get terminal input key.
        """
        _logger.debug("getkey(%r, %r, %r, %r)",
                      y, x, timeout, onlymouse)

        if not self.__alt_screen:
            raise _TermlibError("unsupported state")

        if x is not None or y is not None:
            self.move(y, x)

        if not onlymouse:
            maxyx = self.__maxyx
            pend_resize = Term.__pend_resize
            sigstp_resize = Term.__sigstp_resize
            flash_resize = Term.__flash_resize
            must_resize = sigstp_resize or flash_resize
            flash_reverse = Term.__flash_reverse

            if flash_resize:
                Term.__flash_reverse = not flash_reverse

            elif flash_reverse:
                raise _TermlibTimeout("flashing")

            if must_resize or (maxyx and pend_resize):
                # when using interactive python, sigwinch
                # has been experienced with every command.
                # compare old and new sizes to determine if
                # a resize actually happened.
                Term.__pend_resize = False
                Term.__sigstp_resize = False
                Term.__flash_resize = False
                columns, lines = os.get_terminal_size(self.__termo_fd)
                curmaxyx = lines, columns
                self.__maxyx = curmaxyx
                if not self.__pend_maxyx:
                    if Term.prog_maxyx != curmaxyx:
                        Term.prog_maxyx = None

                if must_resize or maxyx != curmaxyx:
                    return "KEY_RESIZE"

                _logger.info("maxyx did not change")

        pendinc = self.__pendinc
        if pendinc:
            self.__pendinc = ""

        else:
            pendinc = self.__getchar(timeout=timeout)

        if pendinc[0] == "\x1b":  # 27 (ESC)
            self.__pendinc = pendinc
            key = self.__get_esc_seq(onlymouse=onlymouse)

            # check if window title provided (see __title)

            if not key.startswith("\x1b]l"):  # not window title
                return key

            idx = key.index("\x1b\\")  # ST (string terminator)
            if idx < 0:
                return key

            self.__title_original = key[3:idx]
            self.__pendinc = key[idx+2:]
            return "KEY_RESIZE"  # FIXME

        if onlymouse:
            self.__pendinc = pendinc
            raise _TermlibError("not mouse input")

        key = pendinc

        if len(key) > 1:
            self.__pendinc = key[1:]

        _logger.debug("getkey returning %r", key)
        return key

    @_log_errors
    def getmaxyx(self):
        """Get terminal size.
        """
        pend_maxyx = self.__pend_maxyx
        if pend_maxyx:
            return pend_maxyx

        # is using __maxyx worthwhile? or always get_terminal_size?
        maxyx = self.__maxyx
        if maxyx and not self.__pend_resize:
            return maxyx

        columns, lines = os.get_terminal_size(self.__termo_fd)
        curmaxyx = lines, columns
        if not maxyx:
            self.__maxyx = curmaxyx

        if Term.__alt_screen and not pend_maxyx:
            if Term.prog_maxyx != curmaxyx:
                Term.prog_maxyx = None

        return curmaxyx

    def hline(self, *args):
        """Write horizontal line to program mode screen.
        """
        argc = len(args)
        if argc == 4:
            posy, posx, cstr, crep = args
            return self.addstr(posy, posx, cstr * crep)

        if argc == 2:
            cstr, crep = args
            return self.addstr(cstr * crep)

        raise ValueError("# of args not 2 or 4")

    insch = addstr

    def keypad(self, flag):
        """Enable to return escape sequence translation
        key as much as possible.
        """
        _logger.debug("keypad(%r)", flag)
        self.__keypad = flag

    def leaveok(self, flag):
        """Set to hide cursor during program screen refresh.
        """
        _logger.debug("leaveok(%r)", flag)
        self.__leaveok = flag

    def move(self, y, x):
        """Move program cursor.
        """
        self.__curs_pos = (y, x)
        self.__pendmove = True

    @_log_errors
    def refresh(self):
        """Refresh program screen.
        """
        pendlist = self.__pendlist
        cursor_may_move = bool(pendlist)
        leaveok = self.__leaveok
        curs_vis = self.__curs_vis
        alt_screen = Term.__alt_screen

        _logger.debug("refresh() -- alt_screen=%r", alt_screen)

        if not alt_screen:

            if not self.__registered_atexit:
                self.__registered_atexit = True
                atexit.register(self.__atexit)

            if self.__sav:
                Term.__savwinch = signal.getsignal(signal.SIGWINCH)
                Term.__savtstp = signal.getsignal(signal.SIGTSTP)

            Term.__alt_screen = True
            self.reset_prog_mode()

            if _osname != "Windows":
                sigx.add_handler(signal.SIGWINCH, self.__sigwinch)
                sigx.add_handler(signal.SIGTSTP, self.__sigtstp)
            else:
                self.__run_thread()

            if self.__pendtext:
                if not self.__firstmove:
                    pendlist[:0] = self.__cup()
            else:
                self.__pendmove = True

            Term.__shell_maxyx = None
            if self.__maxyx and not self.__pend_maxyx:
                self.__pend_resize = True  # maybe missed SIGWINCH?
            pendlist.insert(0, "\x1bm")  # normal

            pendlist.extend(self.__mouseq(0, self.__mousemask))

        if not alt_screen or (curs_vis and cursor_may_move):
            pendlist.insert(0, "\x1b[?25l")  # hide cursor
            if curs_vis:
                if curs_vis == 2:
                    pendlist.append("\x1b[1 q")
                else:
                    pendlist.append("\x1b[3 q")

                pendlist.append("\x1b[?25h")

        if not alt_screen:
            # It seems that windows (and who knows, maybe others) save
            # the cursor visibility for the normal screen buffer before
            # switching to the alternate screen buffer. And that state
            # is restored when switching to the normal screen buffer.
            # Therefore, we do not want to make any cursor visibility
            # changes before switching to the alternate screen buffer.
            # And maybe other state is saved/restored as well. Ensure
            # that switching to the alternate screen buffer happens 1st.
            pendlist.insert(0, "\x1b[?1049h")  # alternate screen buffer

        if self.__pendmove and not leaveok and curs_vis is not False:
            pendlist.extend(self.__cup())
            self.__pendmove = False

        pend_maxyx = self.__pend_maxyx
        if pend_maxyx:
            self.__maxyx = pend_maxyx
            if not Term.__shell_maxyx:
                columns, lines = os.get_terminal_size(self.__termo_fd)
                Term.__shell_maxyx = lines, columns

        title = self.__title_pending
        seq = self.__title(title)
        if seq:
            pendlist.extend(seq)
            self.__title_current = title

        if pendlist:
            text = "".join(pendlist)
            self.__firstmove = False
            self.__pendtext = False
            pendlist.clear()
            termo = self.__termo
            termo.write(text)
            termo.flush()

        if Term.__flash_reverse:
            # assume done redrawing in reverse fg,bg
            # rather than sleep here, would it be better
            # to somehow trigger the calling program to
            # call getkey in .1 seconds asynchronously?
            _logger.debug("refresh -- sleep(.1)")
            time.sleep(.1)
            Term.__flash_resize = True

    def set_title(self, title):
        """
        Set the alternate screen window/icon title to input string.
        Pass None to attempt to undo the setting of the title.
        """
        self.__title_pending = title

    def timeout(self, delay):
        """Only timeout(0) supported - curses standin.
        """
        _logger.debug("timeout(%r)", delay)
        if delay != 0:
            raise self.error("only delay=0 supported for timeout")

    # Private methods

    def __atexit(self):
        self.endwin()

    def __change_attr(self, attr):

        pend_attr = self.__pend_attr
        if attr == pend_attr:  # quick test
            return

        if attr & ~(self.A_ATTRIBUTES | self.A_COLOR):
            raise ValueError(f"attr={attr} not valid")

        if self.__flash_reverse:
            attr ^= self.A_REVERSE

        self.__pend_attr = attr
        pendlist = self.__pendlist

        if attr == self.A_NORMAL:
            pendlist.append("\x1b[m")
            return

        sgr = []

        abit = self.A_BOLD
        if attr & abit and not pend_attr & abit:
            pend_attr |= abit
            sgr.append("1")
        elif not attr & abit and pend_attr & abit:
            pend_attr &= ~abit
            sgr.append("22")

        abit = self.A_UNDERLINE
        if attr & abit and not pend_attr & abit:
            pend_attr |= abit
            sgr.append("4")
        elif not attr & abit and pend_attr & abit:
            pend_attr &= ~abit
            sgr.append("24")

        abit = self.A_BLINK
        if attr & abit and not pend_attr & abit:
            pend_attr |= abit
            sgr.append("5")
        elif not attr & abit and pend_attr & abit:
            pend_attr &= ~abit
            sgr.append("25")

        abit = self.A_REVERSE
        if attr & abit and not pend_attr & abit:
            pend_attr |= abit
            sgr.append("7")
        elif not attr & abit and pend_attr & abit:
            pend_attr &= ~abit
            sgr.append("27")

        abit = self.A_INVIS
        if attr & abit and not pend_attr & abit:
            pend_attr |= abit
            sgr.append("8")
        elif not attr & abit and pend_attr & abit:
            pend_attr &= ~abit
            sgr.append("28")

        if sgr:
            pendlist.append("\x1b[")
            pendlist.append(";".join(sgr))
            pendlist.append("m")

        cur_pair_number = pend_attr & self.A_COLOR
        pair_number = attr & self.A_COLOR
        if cur_pair_number == pair_number:
            return

        cur_fg, cur_bg = self.pair_content(cur_pair_number)
        new_fg, new_bg = self.pair_content(pair_number)

        if new_fg == cur_fg:
            pass

        elif new_fg == -1:  # default foreground
            pendlist.append("\x1b[39m")

        else:
            color_content = self.__colors[new_fg]
            if isinstance(color_content, int):
                if color_content <= 7:
                    pendlist.append("\x1b[")
                    pendlist.append(str(new_fg+30))
                else:
                    pendlist.append("\x1b[38;5;")
                    pendlist.append(str(new_fg))

                pendlist.append("m")

            else:
                fg_r, fg_g, fg_b = color_content
                fg_r = fg_r * 255 // 1000
                fg_g = fg_g * 255 // 1000
                fg_b = fg_b * 255 // 1000
                pendlist.append("\x1b[38;2;")
                pendlist.append(str(fg_r))
                pendlist.append(";")
                pendlist.append(str(fg_g))
                pendlist.append(";")
                pendlist.append(str(fg_b))
                pendlist.append("m")

        if new_bg == cur_bg:
            pass

        elif new_bg == -1:  # default background
            pendlist.append("\x1b[49m")

        else:
            color_content = self.__colors[new_bg]
            if isinstance(color_content, int):
                if color_content <= 7:
                    pendlist.append("\x1b[")
                    pendlist.append(str(new_bg+40))
                else:
                    pendlist.append("\x1b[48;5;")
                    pendlist.append(str(new_bg))

                pendlist.append("m")

            else:
                bg_r, bg_g, bg_b = color_content
                bg_r = bg_r * 255 // 1000
                bg_g = bg_g * 255 // 1000
                bg_b = bg_b * 255 // 1000
                pendlist.append("\x1b[48;2;")
                pendlist.append(str(bg_r))
                pendlist.append(";")
                pendlist.append(str(bg_g))
                pendlist.append(";")
                pendlist.append(str(bg_b))
                pendlist.append("m")

    def __cup(self):
        """Return list of strings that, when joined
        together, form a CUP ANSI escape sequence for
        the current/pending cursor position.
        """
        posy, posx = self.__curs_pos
        line, col = posy + 1, posx + 1
        return ["\x1b[",
                str(line),
                ";",
                str(col),
                "H"]

    def __get_esc_seq(self, timeout=.1, onlymouse=False):
        _logger.debug("__get_esc_seq(timeout=%r)", timeout)

        pendinc = self.__pendinc
        self.__pendinc = ""
        first = True
        needinitcheck = (len(pendinc) != 1)

        while True:
            if needinitcheck:
                needinitcheck = False

            else:
                ctime = time.time()
                if first:
                    first = False
                    etime = ctime + timeout
                    tout = timeout

                else:
                    tout = max(0, etime - ctime)

                try:
                    pendinc += self.__getchar(timeout=tout)

                except _TermlibTimeout:
                    _logger.debug("__get_esc_seq -- timeout")
                    break

            sord = ord(pendinc[-1])
            slen = len(pendinc)

            key = self._seqname.get(pendinc, None)
            if key:
                _logger.debug("__get_esc_seq -- matched %r", pendinc)
                if onlymouse:
                    self.__pendinc = pendinc
                    raise _TermlibError("not mouse input")

                break

            if slen > 2 and pendinc[1] == "\x1b":  # ESC ESC
                if onlymouse:
                    self.__pendinc = pendinc
                    raise _TermlibError("not mouse input")

                key = self._seqname.get(pendinc[1:], None)
                if key:
                    _logger.debug("__get_esc_seq -- matched %r",
                                  pendinc[1:])
                    break  # matched known ESC+sequence

            if slen == 2 and (sord < 64 or sord > 95):
                if onlymouse:
                    self.__pendinc = pendinc
                    raise _TermlibError("not mouse input")

                # bad escape sequence
                if sord == 27:  # \x1b (ESC)
                    # maybe ESC prefix to indicate ALT+
                    continue

                break  # 2-byte sequence

            if slen >= 3 and pendinc.startswith("\x1b["):  # CSI
                if 64 <= sord <= 126:
                    break  # complete CSI sequence

                if sord < 32 or sord > 63:
                    # bad character in CSI sequence
                    _logger.error("bad CSI sequence %r", pendinc)
                    if onlymouse:
                        self.__pendinc = pendinc
                        raise _TermlibError("not mouse input")

                    self.__pendinc = pendinc[-1:]
                    pendinc = pendinc[:-1]
                    break

        key = None
        if self.__keypad:
            key = self._seqname.get(pendinc, None)
            if key is not None:
                _logger.debug("__get_esc_seq -- matched %r", pendinc)

        if (pendinc.startswith("\x1b[<") and
                pendinc[-1:].lower() == "m"):
            key = self.__mouse_report(pendinc, clicking=onlymouse)

        if onlymouse and key != "KEY_MOUSE":
            self.__pendinc = pendinc
            raise _TermlibError("not mouse input")

        if key is None:
            key = pendinc

        _logger.debug("__get_esc_seq returning %r", key)
        return key

    def __init(self):
        self.__keypad = True
        self.__leaveok = False

        self.__pendinc = ""
        self.__pendtext = False
        self.__prev_mouse = (0, 0, 0, 0, 0)
        self.__mouse_interval = .2  # seconds
        self.__title_original = ""
        self.__title_current = None
        self.__title_pending = None

        self.__curs_pos = (0, 0)
        self.__pendmove = True
        self.__firstmove = False
        self.__maxyx = None
        self.__pend_maxyx = None

        self.__pend_attr = self.A_NORMAL
        self.__dflt_attr = self.A_NORMAL

        self.__pendlist = []

    def __mouse_report(self, rpt, clicking):
        _logger.debug("mouse report: %r", rpt)
        parms = rpt[3:-1]
        parml = parms.split(";")
        try:
            button, posx, posy = parml
            button = int(button)
            posx = int(posx) - 1
            posy = int(posy) - 1

        except Exception:
            _logger.exception("bad mouse report")
            return None

        _, _, _, prev_time, prev_bstate = self.__prev_mouse
        ctime = time.time()

        _logger.debug("mouse button: %s", hex(button))
        _logger.debug("mouse x: %d", posx)
        _logger.debug("mouse y: %d", posy)

        press = (rpt[-1:] == "M")  # press or release

        mid = 0
        bstate = 0

        mbut = (button & 0x03) + 1

        if button & 0x04:
            _logger.debug("mouse BUTTON_SHIFT")
            bstate |= self.BUTTON_SHIFT

        if button & 0x08:
            _logger.debug("mouse BUTTON_ALT")
            bstate |= self.BUTTON_ALT

        if button & 0x10:
            _logger.debug("mouse BUTTON_CTRL")
            bstate |= self.BUTTON_CTRL

        if mbut == 1:
            if press:
                _logger.debug("mouse BUTTON1_PRESSED")
                bstate |= self.BUTTON1_PRESSED

            else:
                _logger.debug("mouse BUTTON1_RELEASED")
                bstate |= self.BUTTON1_RELEASED

        elif mbut == 2:
            if press:
                _logger.debug("mouse BUTTON2_PRESSED")
                bstate |= self.BUTTON2_PRESSED

            else:
                _logger.debug("mouse BUTTON2_RELEASED")
                bstate |= self.BUTTON2_RELEASED

        elif mbut == 3:
            if press:
                _logger.debug("mouse BUTTON3_PRESSED")
                bstate |= self.BUTTON3_PRESSED

            else:
                _logger.debug("mouse BUTTON3_RELEASED")
                bstate |= self.BUTTON3_RELEASED

        check_more_clicks = False

        if ctime < (prev_time + self.__mouse_interval):
            # multiple mouse events in interval

            if (prev_bstate & self.BUTTON1_CLICKED and
                    bstate & self.BUTTON1_RELEASED):
                _logger.debug("mouse BUTTON1_DOUBLE_CLICKED")
                bstate &= ~self.BUTTON1_RELEASED
                bstate |= self.BUTTON1_DOUBLE_CLICKED

            elif (prev_bstate & self.BUTTON1_CLICKED and
                  bstate & self.BUTTON1_PRESSED):
                _logger.debug("mouse BUTTON1 clicked+pressed")
                bstate |= self.BUTTON1_CLICKED
                check_more_clicks = True

            elif (prev_bstate & self.BUTTON3_CLICKED and
                  bstate & self.BUTTON3_RELEASED):
                _logger.debug("mouse BUTTON3_DOUBLE_CLICKED")
                bstate &= ~self.BUTTON3_RELEASED
                bstate |= self.BUTTON3_DOUBLE_CLICKED

            elif (prev_bstate & self.BUTTON3_CLICKED and
                  bstate & self.BUTTON3_PRESSED):
                _logger.debug("mouse BUTTON3 clicked+pressed")
                bstate |= self.BUTTON3_CLICKED
                check_more_clicks = True

            elif (prev_bstate & self.BUTTON1_PRESSED and
                  bstate & self.BUTTON1_RELEASED):
                _logger.debug("mouse BUTTON1_CLICKED")
                bstate |= self.BUTTON1_CLICKED
                check_more_clicks = True

            elif (prev_bstate & self.BUTTON3_PRESSED and
                  bstate & self.BUTTON3_RELEASED):
                _logger.debug("mouse BUTTON3_CLICKED")
                bstate |= self.BUTTON3_CLICKED
                check_more_clicks = True

        mouse = (mid, posx, posy, ctime, bstate)
        self.__prev_mouse = mouse
        Term.__mouse = mouse

        if clicking:
            return "KEY_MOUSE"

        if check_more_clicks:
            try:
                self.getkey(timeout=self.__mouse_interval,
                            onlymouse=True)
            except self.error:
                pass

        _, _, _, _, bstate = Term.__mouse
        bstate &= self.__mousemask
        if not bstate:
            Term.__mouse = None
            _logger.debug("unreported mouse event")
            raise _TermlibError("not reporting mouse event")

        mouse = (mid, posx, posy, ctime, bstate)
        Term.__mouse = mouse
        return "KEY_MOUSE"

    def __title(self, title):
        """
        Return list of strings that, when joined
        together, form an escape sequence to make the
        pending change to the window/icon title (if any).
        """
        slist = []
        old_title = self.__title_current
        if old_title == title:
            return slist

        if title is not None:
            if old_title is None:
                # push window/icon title, but also request a
                # title report in the likely event that push/pop
                # is not supported
                slist.append("\x1b[22t\x1b[21t")  # push/report title

            slist.append("\x1b]0;")  # set window/icon title
            slist.append(title)
            slist.append("\x1b\\")  # ST (string terminator)

        else:
            # set title in case push/pop unsupported
            # then pop window/icon title in case push worked
            slist.append("\x1b]0;")  # set window/icon title
            slist.append(self.__title_original)
            slist.append("\x1b\\\1b[23t")  # ST, pop title

        return slist

    # Class methods

    @classmethod
    @_log_errors
    def beep(cls):
        """Tell terminal to produce an audible 'beep'.
        """
        _logger.debug("beep()")
        cls.__initscr_required()
        cls.__termo.write("\x07")  # BEL
        cls.__termo.flush()

    @classmethod
    def can_change_color(cls):
        """Returns True - curses standin.
        """
        cls.__initscr_required()
        _logger.debug("can_change_color()")
        return True

    @classmethod
    @_log_errors
    def cbreak(cls):
        """Enable terminal cbreak mode.
        """
        _logger.debug("cbreak()")

        termi_fd = cls.__termi_fd

        if termi_fd is None:
            cls.__initscr_required()

        if _osname == "Windows":
            modei = cls.__get_console_mode(cls.std_input_handle)
            modeo = cls.__get_console_mode(cls.std_output_handle)

            # ENABLE_PROCESSED_OUTPUT             0x0001
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING  0x0004
            modeo |= 0x0005
            # ENABLE_WRAP_AT_EOL_OUTPUT           0x0002
            modeo &= ~0x0002
            # DISABLE_NEWLINE_AUTO_RETURN         0x0008
            # ENABLE_LVB_GRID_WORLDWIDE           0x0010

            # ENABLE_QUICK_EDIT_MODE              0x0040
            # ENABLE_EXTENDED_FLAGS               0x0080
            # ENABLE_VIRTUAL_TERMINAL_INPUT       0x0200
            modei |= 0x02c0
            # ENABLE_PROCESSED_INPUT              0x0001
            # ENABLE_LINE_INPUT                   0x0002
            # ENABLE_ECHO_INPUT                   0x0004
            # ENABLE_INSERT_MODE                  0x0020
            modei &= ~0x0027
            # ENABLE_WINDOW_INPUT                 0x0008
            # ENABLE_MOUSE_INPUT                  0x0010

            cls.__set_terminal_attr(termi_fd, None, (modei, modeo))
            return

        tty.setcbreak(termi_fd)

    @classmethod
    def color_content(cls, color_number):
        """Get r,g,b for input color.
        """
        cls.__initscr_required()
        if not 0 <= color_number <= cls.COLORS:
            raise ValueError(f"{color_number} out of range")

        return cls.__colors.get(color_number, (0, 0, 0))

    @classmethod
    def color_pair(cls, pair_number):
        """Get fg,bg for input color pair.
        """
        cls.__initscr_required()
        if not 0 <= pair_number <= cls.COLOR_PAIRS-1:
            raise ValueError(f"{pair_number} out of range")

        return pair_number & cls.A_COLOR

    @classmethod
    @_log_errors
    def curs_set(cls, visibility):
        """Set cursor visibility.
        """
        cls.__initscr_required()

        old_visibility = cls.__curs_vis

        if cls.__alt_screen:
            if visibility == 2:
                cls.__termo.write("\x1b[1 q\x1b[?25h")
            elif visibility:
                cls.__termo.write("\x1b[3 q\x1b[?25h")
            else:
                cls.__termo.write("\x1b[?25l")

        cls.__curs_vis = visibility
        return old_visibility

    @classmethod
    @_log_errors
    def def_prog_mode(cls):
        """Save terminal attributes as program mode terminal attributes.
        """
        cls.__initscr_required()
        _logger.debug("def_prog_mode()")
        if _osname == "Windows":
            modei = cls.__get_console_mode(cls.std_input_handle)
            modeo = cls.__get_console_mode(cls.std_output_handle)
            cls.__prog_attr = (modei, modeo)
            return

        cls.__prog_attr = termios.tcgetattr(cls.__termi_fd)

    @classmethod
    @_log_errors
    def def_shell_mode(cls):
        """Save terminal attributes as shell mode terminal attributes.
        """
        _logger.debug("def_shell_mode()")

        termi_fd = cls.__termi_fd

        if termi_fd is None:
            cls.__initscr_required()

        if _osname == "Windows":
            modei = cls.__get_console_mode(cls.std_input_handle)
            modeo = cls.__get_console_mode(cls.std_output_handle)
            cls.__shell_attr = (modei, modeo)
            return

        cls.__shell_attr = termios.tcgetattr(termi_fd)

    @classmethod
    @_log_errors
    def endwin(cls, stop=False):
        """Undo initscr/refresh.
        """
        alt_screen = cls.__alt_screen
        _logger.debug("endwin() -- alt_screen=%r", alt_screen)

        if alt_screen:
            codes = ["\x1b[m"]  # all attributes off
            shell_maxyx = cls.__shell_maxyx
            if shell_maxyx:
                nlines, ncols = shell_maxyx
                # ESC [ 8 ; nlines ; ncols t  -> set char width/height
                codes.append(f"\x1b[8;{nlines};{ncols}t")

            stdscr = cls.__stdscr
            if stdscr:
                codes.extend(stdscr.__title(None))
                stdscr.__title_current = None

            codes.append("\x1b[?1000l")  # no mouse button press events
            codes.append("\x1b[1 q")  # default cursor style
            codes.append("\x1b[?25h")  # cursor visible
            codes.append("\x1b[?1049l")  # normal screen buffer
            cls.__termo.write("".join(codes))

            if stop:
                cls.__sav = False

            elif _osname != "Windows":
                try:  # getting to reset_shell_mode really important
                    sigx.del_handler(cls.__sigtstp)
                    sigx.del_handler(cls.__sigwinch)

                except Exception:
                    _logger.exception("cannot delete handler(s)")

                cls.__sav = True

            cls.__alt_screen = False

        cls.__stop_thread()
        cls.__flash_resize = False
        cls.__flash_reverse = False
        cls.reset_shell_mode()

    @classmethod
    def flash(cls):
        """Flash the screen

        Actual curses supports this function even if
        isendwin(). This function is NOT supported if
        isendwin().

        A screen flash is 'simulated' by:
          1. Generating KEY_RESIZE to trigger the calling
             program to redraw the screen
          2. Flipping the reverse attribute when writing
             to the terminal
          3. Use the refresh as a signal that the screen
             has been redrawn. Pause for a small amount of
             time to allow the user to see the reversed
             screen. Return to normal drawing.
        """
        _logger.debug("flash()")
        if not cls.__alt_screen:
            raise _TermlibError("unsupported state")

        if cls.__flash_reverse:
            raise _TermlibError("unsupported flash state")

        cls.__flash_resize = True

    @classmethod
    @_log_errors
    def flushinp(cls):
        """Flush terminal input.
        """
        cls.__initscr_required()
        _logger.debug("flushinp()")
        if _osname == "Windows":
            return  # anything to do on Windows?

        termios.tcflush(cls.__termi_fd, termios.TCIFLUSH)

    @classmethod
    def getmouse(cls):
        """Get pending mouse information.
        """
        try:
            ident, posx, posy, _, bstate = cls.__mouse

        except TypeError as exc:
            raise cls.error("no mouse event") from exc

        cls.__mouse = None
        return ident, posx, posy, 0, bstate

    @classmethod
    def has_colors(cls):
        """Returns True - curses standin.
        """
        cls.__initscr_required()
        _logger.debug("has_colors()")
        return True

    @classmethod
    def init_color(cls, color_number, r, g, b):
        """Set r,g,b for input color.
        """
        cls.__initscr_required()
        if not 0 <= color_number <= cls.COLORS:
            raise ValueError(f"{color_number} out of range")

        cls.__colors[color_number] = (r, g, b)

    @classmethod
    def init_pair(cls, pair_number, fg, bg):
        """Set fg,bg for input color pair.
        """
        cls.__initscr_required()
        if not 1 <= pair_number <= cls.COLOR_PAIRS-1:
            raise ValueError(f"{pair_number} out of range")

        if not -1 <= fg <= cls.COLORS:
            raise ValueError(f"{fg} out of range")

        if not -1 <= bg <= cls.COLORS:
            raise ValueError(f"{bg} out of range")

        attr = cls.__stdscr.__pend_attr
        pend_pair_number = attr & cls.A_COLOR
        if pend_pair_number == pair_number:
            attr |= ~cls.A_COLOR  # bad color
            cls.__stdscr.__pend_attr = attr

        cls.__color_pairs[pair_number] = (fg, bg)

    @classmethod
    def initscr(cls):
        """Initialize curses. Returns curses/window/stdscr instance.
        """
        _logger.debug("initscr()")
        stdscr = cls.__stdscr
        if stdscr:
            stdscr.__init()
            try:
                stdscr.refresh()

            except Exception as exc:
                cls.reset_shell_mode()
                raise cls.error("init failed") from exc

            return stdscr

        termi = sys.stdin
        termi_fd = termi.fileno()

        termo = sys.stdout
        termo_fd = termo.fileno()

        if not os.isatty(termi_fd):
            raise cls.error("stdin is not a tty")

        if not os.isatty(termo_fd):
            raise cls.error("stdout is not a tty")

        if os.getenv("_BPX_TERMPATH") == "OMVS":
            raise cls.error("_BPX_TERMPATH=OMVS")

        cls.__termi = termi
        cls.__termi_fd = termi_fd
        cls.__termo = termo
        cls.__termo_fd = termo_fd

        cls.__lock = None
        cls.selectr = termi  # special to account for Windows
        if _osname == "Windows":
            cls.selectr = None
            k32 = ctypes.windll.kernel32
            # STD_INPUT_HANDLE=-10
            # STD_OUTPUT_HANDLE=-11
            hand = k32.GetStdHandle(-10)
            if hand == -1:  # INVALID_HANDLE_VALUE
                code = k32.GetLastError()
                raise _TermlibError(f"GetStdHandle(-10) code={code}")

            cls.std_input_handle = hand
            hand = k32.GetStdHandle(-11)
            if hand == -1:  # INVALID_HANDLE_VALUE
                code = k32.GetLastError()
                raise _TermlibError(f"GetStdHandle(-11) code={code}")

            cls.std_output_handle = hand

        encoding = termo.encoding
        try:
            "\u2500".encode(encoding)
            cls.ACS_HLINE = "\u2500"
        except Exception:
            pass

        stdscr = Term()
        cls.__stdscr = stdscr
        return stdscr

    @classmethod
    def isendwin(cls):
        """
        Return True if endwin() has been called (that is,
        the curses library has been deinitialized).

        curses.isendwin()
        """
        cls.__initscr_required()
        return not cls.__alt_screen

    @classmethod
    def meta(cls, flag):
        """Only meta(True) supported - curses standin.
        """
        cls.__initscr_required()
        _logger.debug("meta(%r)", flag)
        if not flag:
            raise cls.error("meta(False) not supported")

    @classmethod
    @_log_errors
    def mousemask(cls, mask):
        """Enable disable mouse events.
        """
        _logger.debug("mousemask(%r)", mask)

        oldmask = cls.__mousemask
        availmask = mask

        if availmask and cls.__alt_screen:
            mouselist = cls.__mouseq(oldmask, availmask)
            cls.__termo.write("".join(mouselist))

        cls.__mousemask = availmask
        return availmask, oldmask

    @classmethod
    @_log_errors
    def noecho(cls, when=None):
        """Disable terminal echo mode.
        """
        _logger.debug("noecho()")

        termi_fd = cls.__termi_fd

        if termi_fd is None:
            cls.__initscr_required()

        if _osname == "Windows":
            handle = cls.std_input_handle
            mode = cls.__get_console_mode(handle)
            # ENABLE_ECHO_INPUT=0x0004
            mode &= ~0x0004
            cls.__set_console_mode(handle, mode)
            return

        attr = termios.tcgetattr(termi_fd)
        attr[3] &= ~termios.ECHO

        # Experience has shown that using ICRNL or
        # INLCR (not sure which one?) causes the
        # input file descriptor to be 'ready'
        # continously after a CR or NL (not sure which
        # one?). Such a state negates the use of the
        # select service and causes constant polling.
        # An attempt was initially made to flush the
        # input 'file' after reading a '\n', but this
        # caused a loss of data. Ensure that these
        # harmful flags are turned off here. Although
        # it has nothing to do with 'echo', it is a
        # convenient place to put it.

        attr[0] &= ~termios.INLCR
        attr[0] &= ~termios.ICRNL

        cls.__set_terminal_attr(termi_fd, when, attr)

    @classmethod
    def pair_content(cls, pair_number):
        """Get attribute for normal input color pair.
        """
        cls.__initscr_required()
        if not 0 <= pair_number <= cls.COLOR_PAIRS-1:
            raise ValueError(f"{pair_number} out of range")

        return cls.__color_pairs.get(pair_number, (-1, -1))

    @classmethod
    @_log_errors
    def reset_prog_mode(cls, when=None):
        """Set terminal attributes to program mode.
        """
        _logger.debug("reset_prog_mode()")

        termi_fd = cls.__termi_fd
        attr = cls.__prog_attr

        if termi_fd is None:
            cls.__initscr_required()

        if attr:
            cls.__set_terminal_attr(termi_fd, when, attr)

        else:
            cls.cbreak()
            cls.noecho()

    @classmethod
    @_log_errors
    def reset_shell_mode(cls, when=None):
        """Set terminal attributes to shell mode.
        """
        _logger.debug("reset_shell_mode()")

        termi_fd = cls.__termi_fd
        attr = cls.__shell_attr

        if termi_fd is None or not attr:
            cls.__initscr_required()

        cls.__set_terminal_attr(termi_fd, when, attr)

    @classmethod
    def resize_term(cls, nlines, ncols):
        """Does nothing - curses standin.
        """
        cls.__initscr_required()
        _logger.debug("resize_term(%r, %r)", nlines, ncols)

    @classmethod
    def setupterm(cls, *args):
        """Does nothing - curses standin.
        """
        _logger.debug("setupterm%r", args)

    @classmethod
    def start_color(cls):
        """Initialize color.
        """
        _logger.debug("start_color()")
        cls.__initscr_required()

        for color in range(0, 256):
            cls.__colors[color] = color

        # colors  0 -   7 are standard colors
        # colors  8 -  15 are high intensity colors
        # colors 16 - 255 are remainder of 256 colors
        # 512 definable seems a reasonable max
        colors = 768
        if os.getenv("COLORTERM") not in ("truecolor", "24bit"):
            try:
                colors = int(os.getenv("TNZ_COLORS"))
            except (ValueError, TypeError):
                colors = 0

            if not 8 <= colors <= 768:
                colors = 768
                if os.getenv("TERM_PROGRAM") == "Apple_Terminal":
                    colors = 256

        cls.COLORS = colors
        cls.COLOR_PAIRS = cls.A_COLOR + 1

    @classmethod
    def tigetstr(cls, capname):
        return cls.__caps.get(capname, None)

    @classmethod
    def tparm(cls, bstr, *args):
        slist = ";".join([str(argx) for argx in args])
        string = bstr.decode("latin1")
        return string.format(slist).encode("latin1")

    @classmethod
    def use_default_colors(cls):
        """Does nothing - curses standin.
        """
        cls.__initscr_required()
        _logger.debug("use_default_colors()")

    # Private class methods

    @classmethod
    def __cls_init(cls):
        class _Key(IntEnum):
            KEY_ENTER = 256
            KEY_BACKSPACE = auto()
            KEY_EXIT = auto()
            KEY_SR = auto()
            KEY_SF = auto()
            KEY_SRIGHT = auto()
            KEY_SLEFT = auto()
            KEY_MULTIPLY = auto()
            KEY_ADD = auto()
            KEY_SEPARATOR = auto()
            KEY_SUBTRACT = auto()
            KEY_DECIMAL = auto()
            KEY_DIVIDE = auto()
            KEY_EQUAL = auto()
            KEY_KP_0 = auto()
            KEY_KP_1 = auto()
            KEY_KP_2 = auto()
            KEY_KP_3 = auto()
            KEY_KP_4 = auto()
            KEY_KP_5 = auto()
            KEY_KP_6 = auto()
            KEY_KP_7 = auto()
            KEY_KP_8 = auto()
            KEY_KP_9 = auto()
            KEY_FIND = auto()
            KEY_SELECT = auto()
            KEY_F1 = auto()
            KEY_F2 = auto()
            KEY_F3 = auto()
            KEY_F4 = auto()
            KEY_A1 = auto()
            KEY_A3 = auto()
            KEY_B2 = auto()
            KEY_BEG = auto()

        maxval = 0
        for key in _Key:
            maxval = key.value
            setattr(cls, key.name, maxval)

        for i, key in enumerate(set(cls._seqname.values()), maxval+1):
            setattr(cls, key, i)

    @classmethod
    def __getchar(cls, timeout=0):
        if _osname == "Windows":
            socketr = cls.__socketr
            socketr.settimeout(timeout)
            try:
                bstr = cls.__socketr.recv(1)

            except ConnectionResetError as exc:  # why does this happen?
                _logger.exception("need to rebuild socketpair")
                cls.__stop_thread()
                cls.__run_thread()
                raise _TermlibTimeout("no input") from exc

            except (BlockingIOError, socket.timeout) as exc:
                raise _TermlibTimeout("no input") from exc

            socketb = Term.__socketb
            if socketb:
                Term.__socketb += bstr
                bstr = Term.__socketb

            try:
                cstr = bstr.decode(encoding=Term.__termi.encoding,
                                   errors=Term.__termi.errors)

            except UnicodeDecodeError:
                raise _TermlibTimeout("no input")

            Term.__socketb = b""
            return cstr

        termi = cls.__termi
        termi_fd = cls.__termi_fd
        fflags = fcntl.fcntl(termi_fd, fcntl.F_GETFL)
        selrv = None
        try:
            fcntl.fcntl(termi_fd, fcntl.F_SETFL, fflags | os.O_NONBLOCK)
            cstr = termi.read(1)
            if not cstr:
                selrv = select.select([termi], [], [], timeout)
                if termi in selrv[0]:
                    try:
                        cstr = termi.read(1)

                    except Exception:  # does this still happen?
                        _logger.exception("why does this happen?")

        except BlockingIOError:
            selrv = select.select([termi], [], [], timeout)
            if termi in selrv[0]:
                try:
                    cstr = termi.read(1)

                except Exception:  # does this still happen?
                    _logger.exception("why does this happen?")

        finally:
            fcntl.fcntl(termi_fd, fcntl.F_SETFL, fflags)

        if not cstr:
            raise _TermlibTimeout("no input")

        return cstr

    @classmethod
    def __get_console_mode(cls, handle):
        _logger.debug("__get_console_mode(%r)", handle)
        k32 = ctypes.windll.kernel32
        mode = ctypes.c_ulong()
        cmode = k32.GetConsoleMode(handle, ctypes.byref(mode))
        if cmode == 0:
            code = k32.GetLastError()
            raise _TermlibError(f"GetConsoleMode code={code}")

        mode = mode.value
        _logger.debug("__get_console_mode(%r) -> %04x",
                      handle, mode)
        return mode

    @classmethod
    def __initscr_required(cls):
        if cls.__stdscr is None:
            raise cls.error("must call initscr() first")

    @classmethod
    def __mouseq(cls, oldmask, newmask):
        slist = []
        if not oldmask and newmask:
            # SGR mouse mode, Send Mouse X & Y on button press
            slist.append("\x1b[?1006;1000h")

        elif oldmask and not newmask:
            # no mouse button press events
            slist.append("\x1b[?1000l")

        return slist

    @classmethod
    def __run_thread(cls):
        """Start __win_thread if not already running.
        """
        if not cls.__thread:
            if not cls.__lock:
                cls.__lock = threading.Lock()

            sockw, sockr = socket.socketpair()
            sockw.shutdown(socket.SHUT_RD)
            sockr.shutdown(socket.SHUT_WR)
            sockr.setblocking(False)
            cls.__socketr = sockr
            cls.__socketw = sockw
            cls.__socketb = b""

            thread = threading.Thread(target=cls.__win_thread)
            cls.__thread = thread
            thread.start()

            cls.selectr = sockr  # special to account for Windows

    @classmethod
    def __set_console_mode(cls, handle, mode):
        _logger.debug("__set_console_mode(%r, %04x)", handle, mode)
        k32 = ctypes.windll.kernel32
        cmode = k32.SetConsoleMode(handle, mode)
        if cmode == 0:
            code = k32.GetLastError()
            raise _TermlibError(f"SetConsoleMode code={code}")

    @classmethod
    def __set_terminal_attr(cls, termi_fd, when, attr):
        if _osname == "Windows":
            cls.__termo.flush()
            modei, modeo = attr
            cls.__set_console_mode(cls.std_input_handle, modei)
            cls.__set_console_mode(cls.std_output_handle, modeo)
            return

        if when is None:
            when = termios.TCSANOW

        while True:
            try:
                termios.tcsetattr(termi_fd, when, attr)
                return

            except termios.error:
                _logger.exception("tcsetattr")

    @classmethod
    def __sigtstp(cls, *_, **__):
        _logger.debug("SIGTSTP: stopping=%r", cls.__stopping)
        if not cls.__stopping:
            loop = asyncio.get_event_loop()
            loop.call_soon(cls.__stopcont)
            cls.__stopping = True

    @classmethod
    def __sigwinch(cls, *_, **__):
        cls.__pend_resize = True

    @classmethod
    def __stop_thread(cls):
        """Stop __win_thread if running.
        """
        # first, set status to not run thread

        thread = cls.__thread
        if not thread:
            return

        cls.__lock.acquire()
        cls.__thread = None
        cls.__lock.release()

        # second, wakeup thread

        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        handle = cls.std_input_handle

        class _KeyEventRecord(ctypes.Structure):
            _fields_ = [("bKeyDown", wintypes.BOOL),
                        ("wRepeatCount", wintypes.WORD),
                        ("wVirtualKeyCode", wintypes.WORD),
                        ("wVirtualScanCode", wintypes.WORD),
                        ("UnicodeChar", wintypes.WCHAR),
                        ("dwControlKeyState", wintypes.DWORD),
                        ]

        class _InputRecord(ctypes.Structure):
            _fields_ = [("EventType", wintypes.WORD),
                        ("KeyEvent", _KeyEventRecord)]

        lpb = _InputRecord()
        lpb.EventType = 0x0001  # KEY_EVENT
        lpb.KeyEvent.bKeyDown = 1
        lpb.KeyEvent.wRepeatCount = 1
        lpb.KeyEvent.wVirtualKeyCode = 0x1b
        lpb.KeyEvent.UnicodeChar = "\x1b"
        lpb.KeyEvent.dwControlKeyState = 0

        lpn = ctypes.c_ulong()
        wrv = k32.WriteConsoleInputW(handle, lpb, 1, ctypes.byref(lpn))
        if wrv == 0:
            code = k32.GetLastError()
            raise _TermlibError(f"WriteConsoleInputW error code={code}")

        if lpn.value != 1:
            _logger.warning("WriteConsoleInputW wrote %d characters",
                            lpn.value)

        # third, wait for thread to stop

        thread.join()

        # fourth, cleanup

        cls.selectr = None
        sockw = cls.__socketw
        sockr = cls.__socketr
        cls.__socketr = None
        cls.__socketw = None
        cls.__socketb = b""
        sockw.close()
        sockr.close()

    @classmethod
    def __stopcont(cls):
        cls.__sigstp_resize = True
        cls.endwin(stop=True)
        cls.__termo.flush()
        os.kill(os.getpid(), signal.SIGSTOP)
        cls.__stdscr.refresh()
        cls.__stopping = False

    @classmethod
    def __win_thread(cls):
        """Copy terminal input to socket.
        """
        termi = cls.__termi.buffer
        sock = cls.__socketw
        lock = cls.__lock
        while True:
            lock.acquire()
            run = bool(cls.__thread)
            lock.release()
            if not run:
                return

            bstr = termi.read(1)
            if not bstr:
                _logger.error("__win_thread read no data")
                if termi.closed:
                    return

                bstr = b"\x1a"  # Windows Ctrl+Z ?

            lock.acquire()
            run = bool(cls.__thread)
            lock.release()
            if not run:
                return

            try:
                sock.sendall(bstr)

            except ConnectionResetError:
                _logger.exception("need to rebuild socketpair")
                return

    # Static methods

    @staticmethod
    def notimeout(flag):
        """Does nothing - curses standin for window method.
        """
        _logger.debug("notimeout(%r)", flag)

    @staticmethod
    def noutrefresh():
        """Does nothing - curses standin for window method.
        """
        _logger.debug("noutrefresh()")

    @staticmethod
    def resize(nlines, ncols):
        """Does nothing - curses standin for window method.
        """
        _logger.debug("resize(%r, %r)", nlines, ncols)

    # Data descriptors

    error = _TermlibError

    prog_maxyx = None  # termlib extension

    BUTTON1_PRESSED = 0x80000000
    BUTTON1_RELEASED = 0x40000000
    BUTTON1_CLICKED = 0x20000000
    BUTTON1_DOUBLE_CLICKED = 0x10000000
    BUTTON1_TRIPLE_CLICKED = 0x08000000
    BUTTON2_PRESSED = 0x04000000
    BUTTON2_RELEASED = 0x02000000
    BUTTON2_CLICKED = 0x01000000
    BUTTON2_DOUBLE_CLICKED = 0x00800000
    BUTTON2_TRIPLE_CLICKED = 0x00400000
    BUTTON3_PRESSED = 0x00200000
    BUTTON3_RELEASED = 0x00100000
    BUTTON3_CLICKED = 0x00080000
    BUTTON3_DOUBLE_CLICKED = 0x00040000
    BUTTON3_TRIPLE_CLICKED = 0x00020000
    BUTTON4_PRESSED = 0x00010000
    BUTTON4_RELEASED = 0x00008000
    BUTTON4_CLICKED = 0x00004000
    BUTTON4_DOUBLE_CLICKED = 0x00002000
    BUTTON4_TRIPLE_CLICKED = 0x00001000
    BUTTON_SHIFT = 0x00000004
    BUTTON_CTRL = 0x00000002
    BUTTON_ALT = 0x00000001

    LINES = -1

    A_NORMAL = 0x00000000
    A_ATTRIBUTES = 0xf8000000
    A_BOLD = 0x80000000
    A_REVERSE = 0x40000000
    A_INVIS = 0x20000000
    A_BLINK = 0x10000000
    A_UNDERLINE = 0x08000000

    A_COLOR = 255

    ACS_HLINE = "-"

    COLOR_BLACK = 0
    COLOR_RED = 1
    COLOR_GREEN = 2
    COLOR_YELLOW = 3
    COLOR_BLUE = 4
    COLOR_MAGENTA = 5
    COLOR_CYAN = 6
    COLOR_WHITE = 7

    # Private data descriptors

    __shell_maxyx = None

    __termi = None
    __termi_fd = None
    __termo = None
    __thread = None

    __stdscr = None

    __curs_vis = 1
    __alt_screen = None
    __shell_attr = None
    __prog_attr = None
    __mousemask = 0
    __mouse = None
    __pend_resize = False
    __sigstp_resize = False
    __flash_resize = False
    __flash_reverse = False

    __sav = (_osname != "Windows")
    __savwinch = None
    __savtstp = None
    __stopping = False

    __color_pairs = {0: (-1, -1)}
    __colors = {}

    # Private data descriptors

    __caps = {
        "blink": b"\x1b[5m",
        "bold": b"\x1b[1m",
        "cha": b"\x1b[{}G",
        "civis": b"\x1b[?25l",
        "clear": b"\x1b[H\x1b[J",
        "cnl": b"\x1b[{}E",
        "cnorm": b"\x1b[34h\x1b[?25h",
        "cpl": b"\x1b[{}F",
        "cub": b"\x1b[{}D",
        "cub1": b"\x1b[D",
        "cud": b"\x1b[{}B",
        "cud1": b"\x1b[B",
        "cuf": b"\x1b[{}C",
        "cuf1": b"\x1b[C",
        "cup": b"\x1b[{}H",
        "cuu": b"\x1b[{}A",
        "cuu1": b"\x1b[A",
        "cvvis": b"\x1b[?25h",
        "dsr": b"\x1b[6n",
        "ed": b"\x1b[{}J",
        "el": b"\x1b[{}K",
        "home": b"\x1b[H",
        "hpa": b"\x1b[{}G",
        "hvp": b"\x1b[{}f",
        "rmcup": b"\x1b[?1049l",
        "sd": b"\x1b[{}T",
        "sgr": b"\x1b[{}m",
        "sgr0": b"\x1b[m",
        "smcup": b"\x1b[?1049h",
        "su": b"\x1b[{}S",
    }
    _seqname = {
        # vt sequences:
        "\x1b[1~": "KEY_HOME",
        "\x1b[2~": "KEY_IC",
        "\x1b[3~": "KEY_DC",
        "\x1b[4~": "KEY_END",
        "\x1b[5~": "KEY_PPAGE",
        "\x1b[6~": "KEY_NPAGE",
        "\x1b[7~": "KEY_HOME",
        "\x1b[8~": "KEY_END",
        "\x1b[11~": "KEY_F(1)",
        "\x1b[12~": "KEY_F(2)",
        "\x1b[13~": "KEY_F(3)",
        "\x1b[14~": "KEY_F(4)",
        "\x1b[15~": "KEY_F(5)",
        "\x1b[17~": "KEY_F(6)",
        "\x1b[18~": "KEY_F(7)",
        "\x1b[19~": "KEY_F(8)",
        "\x1b[20~": "KEY_F(9)",
        "\x1b[21~": "KEY_F(10)",
        "\x1b[23~": "KEY_F(11)",
        "\x1b[24~": "KEY_F(12)",
        # xterm sequences
        "\x1b[A": "KEY_UP",
        "\x1b[B": "KEY_DOWN",
        "\x1b[C": "KEY_RIGHT",
        "\x1b[D": "KEY_LEFT",
        "\x1b[F": "KEY_END",
        "\x1b[H": "KEY_HOME",
        "\x1b[1P": "KEY_F(1)",
        "\x1b[1Q": "KEY_F(2)",
        "\x1b[1R": "KEY_F(3)",
        "\x1b[1S": "KEY_F(4)",
        # indicate sequence handled
        "\x1b": "KEY_ESC",
        # discovered in PuTTY
        "\x1b[Z": "KEY_BTAB",
        "\x1b[25~": "KEY_F(15)",
        "\x1b[26~": "KEY_F(16)",
        "\x1b[28~": "KEY_F(17)",
        "\x1b[29~": "KEY_F(18)",
        "\x1b[31~": "KEY_F(19)",
        "\x1b[32~": "KEY_F(20)",
        "\x1b[33~": "KEY_F(21)",
        "\x1b[34~": "KEY_F(22)",
        # PuTTY SCO mode
        "\x1b[M": "KEY_F(1)",
        "\x1b[N": "KEY_F(2)",
        "\x1b[O": "KEY_F(3)",
        "\x1b[P": "KEY_F(4)",
        "\x1b[Q": "KEY_F(5)",
        "\x1b[R": "KEY_F(6)",
        "\x1b[S": "KEY_F(7)",
        "\x1b[T": "KEY_F(8)",
        "\x1b[U": "KEY_F(9)",
        "\x1b[V": "KEY_F(10)",
        "\x1b[W": "KEY_F(11)",
        "\x1b[X": "KEY_F(12)",
        "\x1b[Y": "KEY_F(13)",
        "\x1b[a": "KEY_F(15)",
        "\x1b[b": "KEY_F(16)",
        "\x1b[c": "KEY_F(17)",
        "\x1b[d": "KEY_F(18)",
        "\x1b[e": "KEY_F(19)",
        "\x1b[f": "KEY_F(20)",
        "\x1b[g": "KEY_F(21)",
        "\x1b[h": "KEY_F(22)",
        "\x1b[i": "KEY_F(23)",
        "\x1b[j": "KEY_F(24)",
        # vtxxx (invisible-island)
        "\x1bOP": "KEY_F(1)",
        "\x1bOQ": "KEY_F(2)",
        "\x1bOR": "KEY_F(3)",
        "\x1bOS": "KEY_F(4)",
        # discovered in command prompt
        "\x1b[1;2P": "KEY_F(13)",
        "\x1b[1;2Q": "KEY_F(14)",
        "\x1b[1;2R": "KEY_F(15)",
        "\x1b[1;2S": "KEY_F(16)",
        "\x1b[15;2~": "KEY_F(17)",
        "\x1b[17;2~": "KEY_F(18)",
        "\x1b[18;2~": "KEY_F(19)",
        "\x1b[19;2~": "KEY_F(20)",
        "\x1b[20;2~": "KEY_F(21)",
        "\x1b[21;2~": "KEY_F(22)",
        "\x1b[23;2~": "KEY_F(23)",
        "\x1b[24;2~": "KEY_F(24)",
        "\x1b[2;2~": "KEY_SIC",
        # discovered in iTerm2
        "\x1b[1;2F": "KEY_SEND",
    }
