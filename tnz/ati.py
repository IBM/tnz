"""ATI tnz interface

ATI (Automated Task Interpreter) was an IBM-internal language/runtime
built for automating 3270 terminal interaction. It had a syntax very
similar to Rexx. This module is intended to help with porting ATI
code to python. It is also the base of the zti tool.

Some of these functions have enhancements on top of the ATI function.
Enhancments include using a negative index/position or length to
indicate a position relative to the END of the string. See individual
functions for details.

USAGE
    The way to make a python script that is most like ATI source code
    is to use 'import *'. Be warned that this will override the 'set'
    symbol (otherwise a python builtin function).

        from tnz.ati import *
        set('SESSION', 'SES1')
        wait(lambda: scrhas('RUNNING'))
        drop('SESSION')

    The next step up in being more pythonic is to import the module
    as a symbol, but still make the assumption that python is running
    a single ATI program.

        from tnz import ati
        ati.set('SESSION', 'SES1')
        ati.wait(lambda: ati.scrhas('RUNNING'))
        ati.drop('SESSION')

    In a more complex program that may manage multiple ATI programs,
    the Ati class can be imported.

        from tnz.ati import Ati
        ati = Ati()
        ati.set('SESSION', 'SES1')
        ati.wait(lambda: ati.scrhas('RUNNING'))
        ati.drop('SESSION')

    And a more pythonic way of using ATI-like variables can be used.
    Note that this bypasses much of the ATI tracing/logging.

        from tnz.ati import Ati
        ati = Ati()
        ati.session = 'SES1'
        ati.wait(lambda: ati.scrhas('RUNNING'))
        ati.drop('SESSION')


Special ATI-like variables that did not exist in ATI:

    LOGCOUNT
        Default is 9. Can be set to other positive integers. Used
        only when LOGMAX is non-zero. Used to determine the number of
        backup logs kept when a log reaches the maximum size. When
        the number of bytes in the log is about to exceed this value,
        the log file is closed and a new file is opened for output.
        The old file will be renamed to end in '.n', where 'n' is the
        current total number of backups. The first backup will end in
        '.1', the second in '.2', etc.

    LOGMAX
        Default is 0. Can be set to a positive integer. When
        non-zero, value is the number of bytes at which log
        rollover/rotation occurs. When the number of bytes in the log
        is about to exceed this value, the log file is closed and a
        new file is opened for output.

    LOGTRUNC
        Default is 1. Can be set to 0 or 1. Affects processing done
        when LOGDEST is set. When 1 and LOGDEST identifies an
        existing file, the file will be truncated to 0 bytes before
        logging begins. When 0 and LOGDEST identifies an existing
        file, log entries will be appended to the existing file.
        After LOGDEST is set to a file, LOGTRUNC is set to 0.

Environment variables used:
    COLORTERM (see _termlib.py)
    DATEFORM
    ESCDELAY (see zti.py)
    SESSION_PS_SIZE (see tnz.py)
    TERM_PROGRAM (see _termlib.py)
    TNZ_COLORS (see tnz.py)
    TNZ_LOGGING (see tnz.py)
    ZTI_AUTOSIZE (see zti.py)
    ZTI_SECLEVEL (see tnz.py)
    ZTI_TITLE (see zti.py)
    _BPX_TERMPATH (see _termlib.py)

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
import functools
import inspect
import logging
from logging import handlers
import os
import re
import time
import traceback

from . import tnz as _tnz
from . import _util

# rexx functions that had ATI implementations

from .rexx import copies
from .rexx import index
from .rexx import left
from .rexx import length
from .rexx import right
from .rexx import strip
from .rexx import substr
from .rexx import word
from .rexx import words
from . import __version__

__all__ = ["drop",
           "copies",
           "extract",
           "index", "left", "length",
           "logwrt", "num", "numvalue", "rename",
           "right",
           "say", "scrhas", "send", "set",
           "share",  # share instead of global
           "strip",
           "stripl", "stript",
           "substr",
           "upper", "value", "wait", "when",
           "word", "words",
           "CASI", "EOL", "FIRST", "LAST", "OFF", "ON", "FALSE", "TRUE",
           "clear", "enter", "pa1", "pa2", "pa3",
           "pf1", "pf2", "pf3", "pf4",
           "pf5", "pf6", "pf7", "pf8", "pf9",
           "pf01", "pf02", "pf03", "pf04",
           "pf05", "pf06", "pf07", "pf08",
           "pf09", "pf10", "pf11", "pf12",
           "pf13", "pf14", "pf15", "pf16",
           "pf17", "pf18", "pf18", "pf20",
           "pf21", "pf22", "pf23", "pf24",
           "backtab", "btab",
           "curdown", "cdn", "curleft", "clf",
           "curright", "crt", "curup", "cup",
           "delete", "eraseeof", "ereof", "home", "insert", "ins",
           "newline", "nl", "tab", "reset"]
__author__ = "Neil Johnson"

ati = None


class Ati():
    """
    Automate a set of 3270 terminal sessions.

    Methods with ATI function equivalents:
        drop
        extract
        logwrt
        num
        say
        scrhas
        send
        set
        share <called GLOBAL in ATI>
        value
        wait
        when

    Methods from tnz.rexx with ATI function equivalents:
        copies
        index
        left
        length
        right
        strip
        substr
        word
        words

    Methods from Python with ATI function equivalents:
        stripl
        stript
        upper

    ATI functions with no equivalent method implemented:
        chr
        cms
        include
        keywait
        ord
        pull
        push

    Properties with internal ATI variable equivalents:
        age
        curcol
        currow
        date
        datetime
        display
        hitcol
        hitrow
        hitstr
        keylock
        keyunlock
        logdest
        maxcol
        maxrow
        maxlostwarn
        maxwait
        milliage
        onerror
        rc
        sendstr
        seslost
        session
        sessionid
        sessions
        session24
        showline
        showtype
        time
        trace
        waitsleep
    """

    # dunder methods

    def __enter__(self):
        """Use to process another program.

        Example:
            with tnz.ati.new_program()::
                <code that uses tnz.ati and module functions>
        """
        global ati
        self.__ati_stack.append(ati)
        ati = self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global ati
        ati = self.__ati_stack.pop()

    def __getitem__(self, name):
        """Get value of ATI-like variable. Return None is not set.
        """
        unam = name.upper()

        if unam == "SESSION":
            return self.__gv["SESSION"]

        if unam == "SESSIONS":
            return self.sessions

        if unam == "DATETIME":
            return self.datetime

        if unam == "DATE":
            return self.date

        if unam == "TIME":
            return self.time

        if unam == "MILLIAGE":
            return self.milliage

        if unam == "AGE":
            return self.age

        rval = self.__uv.get(unam, None)

        if rval is not None:
            if rval is _GLOBAL:
                return self.__gv.get(unam, None)

            return rval

        if unam in ("MAXWAIT", "SHOWLINE"):
            raise ValueError(unam+" cannot be accessed")

        if unam == "ARG":
            raise ValueError(unam+" not applicable")

        if unam in ("MAXROW", "MAXCOL", "CURROW", "CURCOL", "KEYLOCK"):
            self.__refresh_vars()

        return self.__gv.get(unam, None)

    def __init__(self):

        self.__bytecnt = 0
        self.__checked_tty = False
        self.__have_tty = False
        self.__zti = None
        self.__in_wait = False

        self.connected = True  # to terminal/stdin/stdout

        milliage = time.time()
        self.__gv = {  # global variables (including internal variables)
            "AUDIT": False,  # new
            "SESSION": "NONE",
            "MAXCOL": 0,
            "MAXROW": 0,
            "CURCOL": 0,
            "CURROW": 0,
            "HITCOL": 1,
            "HITROW": 1,
            "HITSTR": "",
            "KEYLOCK": "0",
            "KEYUNLOCK": 60,
            "SENDSTR": "",
            "MAXLOSTWARN": 5,
            "TRACE": "NONE",
            "WAITSLEEP": 1,
            "MAXWAIT": 120,
            "SESLOST": "",
            "seslost": [],
            "SCRUPDATE": 0,
            "ARG": "",  # ?
            "DISPLAY": "NONE",
            "SCRDELAY": 5,
            "SESSIONID": 0,  # or from env?
            "SHOWTYPE": False,  # or from env?
            "SESSION24": False,  # or from env?
            "VIRTCLI": 0,  # new?
            "LOGTRUNC": True,  # new
            "LOGDEST": "(STDERR)",  # special
            "LOGMAX": 0,  # new
            "LOGCOUNT": 9,  # new
            "SCRLIBS": "(INTERNAL)",  # special
            "ONERROR": False,
            "RC": 0,
        }
        self.__ikeys = tuple(self.__gv) + ("MILLIAGE", "AGE")
        self.__gv.update(milliage=milliage,
                         age=milliage,
                         seslost=[],
                         whens=[],
                         pgm_seed=1,
                         logger=None,  # __log_check will set
                         logger_code=None,  # __log_check will set
                         logger_host=None,  # __log_check will set
                         file_handler=None,
                         stderr_handler=None,
                         lostwarncnt=0)
        self.__uv = {}  # user variables (including global variables)
        self.__whens = []
        self.pgmname = None
        self.ses_exc = None
        self.__pgm_number = 1

        self.__session_tnz = {}
        self.__inwhen = False
        self.__ranwhen = False

    # public methods

    def drop(self, *args):
        """Delete user-defined variable(s).

        Drops one or more user-defined variable(s) or host sessions
        from memory. DROP will cause the value of a variable to be
        reset to its name in capital letters. DROP can be used safely
        on non-GLOBAL variables. Note that statement labels and WHEN
        labels cannot be dropped. Please see 'DROPPING A GLOBAL
        VARIABLE' for the consequences of dropping a GLOBAL variable.

           (ATI)
             DROP varname1 [ ... ] | SESSION

           (python)
             drop(varname1[,varname2...])

        where:
          - varname1, etc. are previously defined user variables.

          - SESSION will cause the current host session to be released.
            If the session was a CMS userid, it will be disconnected,
            and
            if it is not reconnected within 15 minutes, it will be
            logged
            off by CP.

        EXAMPLE:
            DROP counter password

        where:
          - 'counter' and 'password' are variables. After the DROP,
            their
            values will be 'COUNTER' and 'PASSWORD', respectively.
          - Dropping SESSION when it has a value of 'NONE' will cause a
            run time warning to occur.

        RETURN CODES
            Not affected
        """
        self.__logcode("drop%s", args)

        for name in args:
            unam = name.upper()
            if unam == "SESSION":
                if self.__session_tnz:  # if SESSION in SESSIONS (FIXME)
                    self.__drop_session()
                else:
                    self.__sescheck()

                session = self.session
                self.__logresult("%s = %r", unam, session)

            elif unam in self.__ikeys:
                raise ValueError("Internal variables cannot be dropped")

            elif unam in self.__uv:
                value = self.__uv[unam]
                if value is not _GLOBAL:
                    del self.__uv[unam]
                else:
                    self.__gv.pop(unam, None)

                self.__logresult("%s = %r", unam, unam)

    def extract(self, *args, wc=None):
        """Return a text string from the host screen.

        Usage/Syntax:

            extract({length | EOL}[, location][, wc='*'])

            location:
                (r, c) | {FIRST|LAST}, string[, (xr, xc)][, wc='*']

        length
            A numeric value specifying the length of the string to
            be extracted from the host screen.

        EOL
            Causes the extraction to reach as far as the end of
            the host screen line where it began.

        (r, c)
            An absolute begin-extraction location on the host
            screen. It can be used instead of the FIRST or LAST
            sequence if the user knows the coordinates of the
            screen where extraction is to begin. The row value
            range is between 1 and the height of the host screen
            (MAXROW). The column value range is between 1 and the
            width of the host screen (MAXCOL). Negative values for
            r and c can be used and are interpreted as relative to
            the height and width of the screen, respectively. For
            example specifying -1 for r is interpretaed as the
            last (bottom) row of the screen. Default is (1, 1).

        FIRST
            Indicates that the begin-extraction location on the
            host screen is after the location of the first
            occurrence of string on the current host screen.

        LAST
            Indicates that the begin-extraction location on the
            host screen is after the location of the last
            occurrence of string on the current host screen.

        string
            The string to be searched for on the host screen.

        (xr, xc)
            A relative row-column offset from the located string.
            The xr and xc fields are integers that represent the
            offset to the location of the extraction. In
            calculating this address, if the vertical edge of the
            host screen is encountered, a wrap-around to the next
            row wil occur and the offset counting then continues
            at this new location.

            The value for xr can range from -MAXROW to MAXROW. The
            value for xc can range from -MAXCOL to MAXCOL. For
            example, (1, -10) would set the extraction location to
            one row below and ten columns to the left of the first
            character in string.

            If (xr, xc) is not provided, the begin-extraction
            location defaults to one character to the right of
            string. The relative location could be defined as (0,
            n) if string has a length of n.

        wc='*'
            Indicates that '*' is the wildcard character in
            string. If more than one character is specified in the
            wildcard string, only the first character is used. If
            a null is specified, no wildcard is set. The '*' is a
            place holder that is not compared to the corresponding
            character in the string being tested on the host
            screen.


        Usage Notes:

            - The string is searched for on the host screen by
              increasing columns and rows (from top to bottom of
              screen, with each row being searched left to right).

            - Absolute (r, c) is mutually exclusive with the
              FIRST/LAST and string option sequence.

            - If the extraction occurs, HITROW and HITCOL is set
              to the location where the extraction began.


        Return Codes (internal variable RC):

             0  The extraction was completed successfully.

             3  The extraction length was less than one; null
                string returned.

             6  The FIRST and LAST character string was not
                found; null string returned.

             7  Error in the FIRST or LAST sequence relative
                address specification null string returned.

             8  The begin-address specification exceeds screen
                bounds; null string returned.

             9  The extraction extended beyond screen bounds;
                result truncated.

            12  Session lost or undefined; null string returned.
        """
        if len(args) < 1:
            raise ValueError("At least 1 argument required")

        if len(args) > 4:
            raise ValueError("At most 4 arguments allowed")

        aridx = 0
        arlen = len(args)
        varname = None
        if isinstance(args[0], str):
            varname = args[0]
            arlen -= 1
            aridx = 1

        varlen = args[aridx]
        if arlen >= 3:
            f_or_l = args[aridx+1]
            string = args[aridx+2]
        else:
            f_or_l = None
            string = None

        if arlen in (1, 3):
            r_c = None
        else:
            r_c = args[-1]

        if string is not None:
            if f_or_l not in (FIRST, LAST):
                raise ValueError(repr(f_or_l)+" not FIRST or LAST")

        if r_c is None:
            row = 1
            col = 1
        else:
            if len(r_c) != 2:
                raise ValueError(repr(r_c)+" does not have 2 values")

            row, col = r_c

        argstr = str(args)[1:-1].rstrip(",")
        if wc:
            argstr += ", wc="+repr(wc)

        self.__logcode("extract(%s)", argstr)

        # Get screen information

        if self.__sescheck():
            return ""

        tns = self.get_tnz()
        self.__refresh_vars()

        scrstr = tns.scrstr(rstrip=False)
        maxcol = self.__gv["MAXCOL"]
        maxrow = self.__gv["MAXROW"]
        scrsize = maxcol * maxrow

        # Get start index (includes FIRST or LAST)

        if r_c and f_or_l:
            row, col = r_c
            start = (row*maxcol) + col  # relative
        elif r_c:
            row, col = r_c
            if row <= 0:
                row = maxrow + row + 1

            if col <= 0:
                col = maxcol + col + 1
            start = ((row-1)*maxcol) + col - 1
        else:
            start = 0

        if f_or_l:
            rval = self.__find(scrstr,
                               string,
                               fwd=(f_or_l is FIRST),
                               wc=wc)
            start += rval - 1 + len(string)
            if rval <= 0:
                # the FIRST|LAST character string was not found
                # null string returned
                self.set("RC", "6", xtern=False)
                self.__logresult("''")
                return ""

        if start < 0 or start >= scrsize:
            # error in FIRST|LAST sequence relative address
            # specification
            # or
            # begin-address specification exceeds screen bounds
            # null string returned
            if f_or_l:
                self.set("RC", "7", xtern=False)
            else:
                self.set("RC", "8", xtern=False)

            self.__logresult("''")
            return ""

        # Get end index

        if varlen is EOL:
            end = start // maxcol
            end = end * maxcol + maxcol - 1
        else:
            end = start + varlen
            if end > scrsize:
                # extraction extended beyond screen bounds
                # result truncated
                self.set("RC", "9", xtern=False)
                end = scrsize

        # Return results

        if start >= end:
            # extraction length was less than one
            # null string returned
            self.set("RC", "3", xtern=False)
            rval = ""
        else:
            hity, hitx = divmod(start, maxcol)
            self.set("HITROW", hity+1, xtern=False)
            self.set("HITCOL", hitx+1, xtern=False)
            self.set("RC", "0", xtern=False)
            rval = scrstr[start:end]

        if varname is not None:
            return self.set(varname, rval)

        self.__logresult("%s", self.__snip(scrstr[start:end]))
        return rval

    def get_tnz(self, name=None):
        """Return session Tnz instance.

        Or None if there is none.
        """
        if not self.__session_tnz:
            return None

        if name is None:
            name = self.__gv["SESSION"]

        return self.__session_tnz.get(name, None)

    def keys(self):
        """Like dict.keys
        """
        return self.__uv.keys() | self.__ikeys

    def logwrt(self, value):
        """Writes the input string to the current log destination.
        """
        self.__logcode("logwrt(%s)", self.__snip(value))
        self.__gv["logger"].critical(value)

    def new_program(self, share=None, share_sessions=None):
        """Create a new instance for a ATI-like program.

        The new instance will share GLOBAL (including internal)
        variables.
        """
        if share is None and share_sessions is None:
            share = True
            share_sessions = True
        elif share is False and share_sessions is None:
            share_sessions = False
        elif share_sessions is True and share is None:
            share = False
        elif share is True and share_sessions is None:
            share_sessions = True
        elif share_sessions is False:
            share = False

        if share:  # share globals (and internal variables)
            self.__log_check()
            import copy
            new_ati = copy.copy(self)
            new_ati.__bytecnt = 0  # ???
            new_ati.__uv = {}  # user variables
            new_ati.pgmname = None
            new_ati.__gv["pgm_seed"] += 1
            new_ati.__pgm_number = new_ati.__gv["pgm_seed"]
            new_ati.__inwhen = False
            new_ati.__ranwhen = False

        else:  # do not share globals (nor internal variables)
            new_ati = Ati()
            if share_sessions:
                new_ati.__session_tnz = self.__session_tnz
                new_ati.__gv["SESSION"] = self.session

        return new_ati

    def numvalue(self, name, trace=None):  # numvalue:
        """Shorthand for num(value(varname))
        """
        return self.num(self.value(name, trace=trace))

    def rename(self, name):
        """Rename the current session.

        Changes the name of the current session to the session
        name specified. The specified session name cannot match
        the name of a currently established session.

        This function performs the function of the RENAME option
        on the GOTO EXEC and overtyping the session name in the
        ATI session manager.
        """
        self.__logcode("rename(%r)", name)

        unam = name.upper().strip()
        if not unam:
            raise ValueError("no session name")

        if self.__sescheck():
            return

        session = self.session
        if session == name:
            return  # TODO rc=4

        if unam in self.__session_tnz:
            raise RuntimeError(unam+" already established")

        tns = self.__session_tnz[session]
        self.__session_tnz[unam] = tns
        self.__gv["SESSION"] = unam
        del self.__session_tnz[session]

        self.__logresult("SESSION = %r", unam)

    def say(self, value):
        """Print the input string.

        Write input string to standard output (likely the
        terminal). If tracing is active (the internal variable TRACE
        is set to either CODE or ALL), say will also direct output to
        the log destination.
        """
        self.__logcode("say(%r)", value)
        if self.connected:
            self.__shell_mode()
            print(value)

        if str(self.trace).upper() != "NONE":
            logger = self.__gv["logger"]
            logger.critical(value)

    def scrcomp(self, value):
        raise RuntimeError("not implemented")

    def scrhas(self, *args, wc=None):
        """Check current screen for a string.

        Return True if the specified character string exists on
        the current host screen. Otherwise return False.

        Usage/Syntax:

            scrhas(string)               (string is always required)

            scrhas(string,wc='*')        (wc is optional to all)
            scrhas(CASI,string)          (CASI is optional to all)

            scrhas(string,(r,c))

            scrhas(string,FIRST,string2)
            scrhas(string,LAST,string2)

            scrhas(string,(r,c),length)
            scrhas(string,(r,c),(r2,c2))


        CASI
            Signifies that the screen search is to be done case
            independently. Thus, 'Logon' is equivalent to 'LOGON'
            or 'logon'.

        string
            The string that is searched for on the host screen.

        FIRST
            Indicates that the begin-search location on the host
            screen is after the location of the last character of
            the first occurrence of string2 on the current host
            screen.

        LAST
            Indicates that the begin-search location on the host
            screen is after the location of the last character of
            the last occurrence of string2 on the current host
            screen.

        string2
            A string that, along with the FIRST or LAST keyword,
            specifies the location on the host screen where the
            search for the string will begin.

        (r, c)
            An absolute begin-search location on the host screen.
            Row (r) must be an integer between 1 and the host
            screen height (MAXROW). Column (c) is an integer
            between 1 and the host screen width (MAXCOL).

        length
            An optional parameter specifying the length of the
            area to be searched for the indicated string. If
            omitted, the area searched will range from the
            specified start position to the end of the screen.

        (r2, c2)
            Specifies an absolute end-search location diagonally
            opposite to (r, c). Row (r2) and column (c2) must be
            integers from 1 to MAXROW and from 1 to MAXCOL,
            respectively. The (r, c) and (r2, c2) define a
            rectangular window on the screen where the specified
            string is searched for.

        wc='*'
            Indicates that '*' is the wildcard character in
            string. The '*' is a place holder that is not
            compared to the corresponding character in the string
            being tested on the host screen. The wildcard can be
            any character that the user chooses. Whenever a
            character is to be interpreted as a wildcard, wc must
            be specified.


         Usage Notes:

             - The internal variables HITROW, HITCOL, and HITSTR
               are set by this function if the search is
               successful.

             - If a begin location is not specified, the search
               will begin at the upper left corner (1:1) of the
               host screen and will cover the entire screen.

             - If string2 is not found on the current host screen,
               this function returns False.

             - Search direction is by increasing columns and rows.
               (Top to bottom, each row being searched left to
               right.)


         Return Codes (internal variable RC):

              0  The string was found on the host screen.
                 Function returns True.

              1  The string was not found on the host screen.
                 Function returns False.

              6  The FIRST or LAST character string was not found.
                 Function returns False.

              8  The begin-search or end-search location exceeds
                 screen bounds.
                 Function returns False.

             12  Session lost or undefined.
                 Function returns False.
        """
        if len(args) < 1:
            raise ValueError("At least 1 argument required")

        if len(args) > 4:
            raise ValueError("At most 4 arguments allowed")

        aridx = 0
        arlen = len(args)
        casi = False
        if args[0] is CASI:
            casi = True
            arlen -= 1
            aridx = 1

        string = args[aridx]
        r_c = None
        r2_c2 = None
        varlen = None
        if (arlen == 3) and (args[aridx+1] in (FIRST, LAST)):
            f_or_l = args[aridx+1]
            string2 = args[aridx+2]
        else:
            f_or_l = None
            string2 = None
            if arlen >= 2:
                r_c = args[aridx+1]
                if arlen >= 3:
                    if isinstance(args[-1], tuple):
                        r2_c2 = args[-1]
                    else:
                        varlen = args[-1]

        argstr = str(args)[1:-1].rstrip(",")
        if wc:
            argstr += ", wc="+repr(wc)

        self.__logcode("scrhas(%s)", argstr)

        # Get screen information

        if self.__sescheck():
            return False

        tns = self.get_tnz()
        self.__refresh_vars()

        scrstr = tns.scrstr(rstrip=False)
        maxcol = self.__gv["MAXCOL"]
        maxrow = self.__gv["MAXROW"]
        scrsize = maxcol * maxrow

        # Get start index (includes FIRST or LAST)

        if f_or_l:
            fwd = (f_or_l is FIRST)
            rval = self.__find(scrstr, string2, fwd=fwd, casi=casi)
            start = rval - 1 + len(string2)
            if rval <= 0:
                # start string not found
                self.set("RC", "6", xtern=False)
                return False

        elif r_c:
            row, col = r_c
            if row <= 0:
                row = maxrow + row + 1

            if col <= 0:
                col = maxcol + col + 1

            start = ((row-1)*maxcol) + col - 1
            if start < 0 or start >= scrsize:
                self.set("RC", "8", xtern=False)
                return False

        else:
            row = 1
            col = 1
            start = 0

        # Get end index

        if r2_c2:
            row2, col2 = r2_c2
            if row2 <= 0:
                row2 = maxrow + row2 + 1

            if col2 <= 0:
                col2 = maxcol + col2 + 1

            if row2 < row:
                raise ValueError("row2<row")

            if col2 < col:
                raise ValueError("col2<col")

            end = ((row2-1)*maxcol) + col2

        elif varlen is not None:
            end = start + varlen

        else:
            end = scrsize

        # Check if indices in bounds

        if end <= 0 or end > scrsize:
            self.set("RC", "8", xtern=False)
            return False

        # Build subset of screen to search

        if r2_c2:
            scrstr2 = ""
            for i in range(0, row2-row+1):
                ti1 = start + (i*maxcol)
                ti2 = ti1 + col2 - col + 1
                scrstr2 += scrstr[ti1:ti2]

            scrstr = scrstr2
        else:
            scrstr = scrstr[start:end]

        # Perform search

        rval = self.__find(scrstr, string, casi=casi, wc=wc)

        # Return results

        if rval <= 0:
            # SCREEN does not have it
            self.set("RC", "1", xtern=False)
            return False

        if r2_c2:
            rowi, coli = divmod(rval-1, col2-col+1)
            hitrow = row + rowi
            hitcol = col + coli
        else:
            i = rval + start
            hitrow, hitcol = divmod(i-1, maxcol)
            hitrow += 1
            hitcol += 1

        self.set("HITROW", hitrow, xtern=False)
        self.set("HITCOL", hitcol, xtern=False)
        self.set("HITSTR", string, xtern=False)
        self.set("RC", "0", xtern=False)
        return True

    def send(self, *args):
        """Send string to the active session.

        Send a string of characters and/or special keys to the
        active session. The session recognizes them as if the user
        typed the data interactively at the keyboard and, depending
        on the data sent, it performs the necessary action.

        Usage/Syntax:

            send([(row, col),] string)

        string
            The data to be sent to the host screen.

        (row,col)
            The location of the cursor that should be set before the
            data is sent to the host screen. The default is the
            current cursor location.


        Usage Notes:

            1 - After completion of the send function, the internal
                variable SENDSTR will contain the value of string. A
                difference from ATI is that SENDSTR will NOT contain
                characters that were ignored.

            2 - The send function transmits data to the active
                session starting at the current cursor position. The
                programmer can access the internal variables CURROW
                and CURCOL to check the current cursor location. A
                difference from ATI is that the position at which
                data is transmitted can be specified by (row,col).

            3 - <TODO need more on mneumonics>

            Special Keys

                [backtab]
                [curdown]
                [curleft]
                [curright]
                [curup]
                [delete]
                [eraseeof]
                [home]
                [insert]
                [newline]
                [tab]

            The RESET key ([reset])

                The RESET key has three different meanings--depending on
                its location in the input string:

                Terminate INSERT mode
                    Occurs when the key appears in the middle of the
                    input string; i.e., there is data before and
                    after the RESET key.

                Ignore Keyboard Lock Condition
                    Occurs when the key is the first data item in the
                    string being sent. Normally if the keyboard is
                    locked, ATI waits up to 1 minute for the keyboard
                    to unlock before sending data. (Note that this
                    value can be changed using the KEYUNLOCK internal
                    variable. However, there are rare cases when it
                    is necessary to transmit data while the keyboard
                    is locked. For example, the user may want to send
                    '####' to PVM (Pass-Through Virtual Machine) to
                    drop a link, ignoring the condition of the
                    screen. For example:

                        send(reset+'####'+enter)

                    Note: If the keyboard were not to unlock in the
                    time allowed, the session would be dropped.

                Suppress Warning Messages
                    Is not a very common use of the RESET key. By
                    appending a RESET key just before the control
                    key, warnings are not logged by the compiler if
                    the send function was unsuccessful. For example,
                    it is usually desirable not to see warning
                    messages when a LOGOFF or DISCONNECT is sent to a
                    session. For example:

                        send('LOGOFF'+reset)

            Control keys

                [clear]
                [enter]
                [pa1]-[pa3]
                [pf1]-[pf24] (also [pf01]-[pf24])

                Note that there is no equivalent to the ATI HOLDSEND.
                None is needed since ENTER is not implied.

        Return Codes (return value and internal variable RC):

                 0  The string was successfully sent to the host screen.

                 4  Data placed in protected field ignored.

                12  Session lost or undefined.

                14  Session dropped due to excessive keyboard lock;
                    null string returned.
        """
        if len(args) == 1:
            r_c = None
            value = args[0]
        elif len(args) == 2:
            r_c, value = args
        else:
            raise ValueError("wrong number of arguments")

        self.__logcode("send%r", args)

        if self.__sescheck():
            return 12

        tns = self.get_tnz()

        zti = self.__zti
        zti2 = zti
        if zti:
            display = self.__gv["DISPLAY"]
            if display not in ("ALL", "HOST", "HOSTCODE"):
                zti = None
                zti2 = None
            elif not self.connected:
                zti = None
                zti2 = None
            elif not self.__gv["SHOWTYPE"]:
                zti = None

        if not value.startswith(reset):
            keyunlock = self.__gv["KEYUNLOCK"]
            tout = keyunlock
            etime = time.time() + tout
            self.__refresh_vars()
            while TRUE == self.__gv["KEYLOCK"]:
                self.__refresh(tout)
                if self.__sescheck():
                    return 12

                tout = etime - time.time()
                if tout <= 0:
                    self.__sescheck(14)
                    return 14

        if r_c:
            tns.set_cursor_position(*r_c)
            if zti2:
                zti2.rewrite_cursor = True

        sent_sescheck = True
        prev_reset = False
        key_data = tns.key_data
        sendstr = ""
        sent = False
        rest = value
        while rest:
            sent_sescheck = not prev_reset
            prev_reset = False
            i = rest.find("[")
            if i < 0:
                cnt = key_data(rest, zti=zti)
                if zti2:
                    zti2.rewrite_cursor = True

                sendstr += rest[:cnt]
                break

            if i > 0:
                key_data(rest[:i], zti=zti)
                if zti2:
                    zti2.rewrite_cursor = True

                sendstr += rest[:i]
                rest = rest[i:]

            if rest.startswith("[["):
                key_data("[", zti=zti)
                if zti2:
                    zti2.rewrite_cursor = True

                sendstr += "[["
                rest = rest[2:]

            elif rest.startswith(clear):
                tns.clear(zti=zti2)
                sendstr += clear
                rest = rest[len(clear):]
                sent = True
                break

            elif rest.startswith(enter):
                tns.enter()
                sendstr += enter
                rest = rest[len(enter):]
                sent = True
                break

            elif rest.startswith(pa1):
                tns.pa1()
                sendstr += pa1
                rest = rest[len(pa1):]
                sent = True
                break

            elif rest.startswith(pa2):
                tns.pa2()
                sendstr += pa2
                rest = rest[len(pa2):]
                sent = True
                break

            elif rest.startswith(pa3):
                tns.pa3()
                sendstr += pa3
                rest = rest[len(pa3):]
                sent = True
                break

            elif rest.startswith(pf1):
                tns.pf1()
                sendstr += pf1
                rest = rest[len(pf1):]
                sent = True
                break

            elif rest.startswith(pf2):
                tns.pf2()
                sendstr += pf2
                rest = rest[len(pf2):]
                sent = True
                break

            elif rest.startswith(pf3):
                tns.pf3()
                sendstr += pf3
                rest = rest[len(pf3):]
                sent = True
                break

            elif rest.startswith(pf4):
                tns.pf4()
                sendstr += pf4
                rest = rest[len(pf4):]
                sent = True
                break

            elif rest.startswith(pf5):
                tns.pf5()
                sendstr += pf5
                rest = rest[len(pf5):]
                sent = True
                break

            elif rest.startswith(pf6):
                tns.pf6()
                sendstr += pf6
                rest = rest[len(pf6):]
                sent = True
                break

            elif rest.startswith(pf7):
                tns.pf7()
                sendstr += pf7
                rest = rest[len(pf7):]
                sent = True
                break

            elif rest.startswith(pf8):
                tns.pf8()
                sendstr += pf8
                rest = rest[len(pf8):]
                sent = True
                break

            elif rest.startswith(pf9):
                tns.pf9()
                sendstr += pf9
                rest = rest[len(pf9):]
                sent = True
                break

            elif rest.startswith(pf01):
                tns.pf1()
                sendstr += pf01
                rest = rest[len(pf01):]
                sent = True
                break

            elif rest.startswith(pf02):
                tns.pf2()
                sendstr += pf02
                rest = rest[len(pf02):]
                sent = True
                break

            elif rest.startswith(pf03):
                tns.pf3()
                sendstr += pf03
                rest = rest[len(pf03):]
                sent = True
                break

            elif rest.startswith(pf04):
                tns.pf4()
                sendstr += pf04
                rest = rest[len(pf04):]
                sent = True
                break

            elif rest.startswith(pf05):
                tns.pf5()
                sendstr += pf05
                rest = rest[len(pf05):]
                sent = True
                break

            elif rest.startswith(pf06):
                tns.pf6()
                sendstr += pf06
                rest = rest[len(pf06):]
                sent = True
                break

            elif rest.startswith(pf07):
                tns.pf7()
                sendstr += pf07
                rest = rest[len(pf07):]
                sent = True
                break

            elif rest.startswith(pf08):
                tns.pf8()
                sendstr += pf08
                rest = rest[len(pf08):]
                sent = True
                break

            elif rest.startswith(pf09):
                tns.pf9()
                sendstr += pf09
                rest = rest[len(pf09):]
                sent = True
                break

            elif rest.startswith(pf10):
                tns.pf10()
                sendstr += pf10
                rest = rest[len(pf10):]
                sent = True
                break

            elif rest.startswith(pf11):
                tns.pf11()
                sendstr += pf11
                rest = rest[len(pf11):]
                sent = True
                break

            elif rest.startswith(pf12):
                tns.pf12()
                sendstr += pf12
                rest = rest[len(pf12):]
                sent = True
                break

            elif rest.startswith(pf13):
                tns.pf13()
                sendstr += pf13
                rest = rest[len(pf13):]
                sent = True
                break

            elif rest.startswith(pf14):
                tns.pf14()
                sendstr += pf14
                rest = rest[len(pf14):]
                sent = True
                break

            elif rest.startswith(pf15):
                tns.pf15()
                sendstr += pf15
                rest = rest[len(pf15):]
                sent = True
                break

            elif rest.startswith(pf16):
                tns.pf16()
                sendstr += pf16
                rest = rest[len(pf16):]
                sent = True
                break

            elif rest.startswith(pf17):
                tns.pf17()
                sendstr += pf17
                rest = rest[len(pf17):]
                sent = True
                break

            elif rest.startswith(pf18):
                tns.pf18()
                sendstr += pf18
                rest = rest[len(pf18):]
                sent = True
                break

            elif rest.startswith(pf19):
                tns.pf19()
                sendstr += pf19
                rest = rest[len(pf19):]
                sent = True
                break

            elif rest.startswith(pf20):
                tns.pf20()
                sendstr += pf20
                rest = rest[len(pf20):]
                sent = True
                break

            elif rest.startswith(pf21):
                tns.pf21()
                sendstr += pf21
                rest = rest[len(pf21):]
                sent = True
                break

            elif rest.startswith(pf22):
                tns.pf22()
                sendstr += pf22
                rest = rest[len(pf22):]
                sent = True
                break

            elif rest.startswith(pf23):
                tns.pf23()
                sendstr += pf23
                rest = rest[len(pf23):]
                sent = True
                break

            elif rest.startswith(pf24):
                tns.pf24()
                sendstr += pf24
                rest = rest[len(pf24):]
                sent = True
                break

            elif rest.startswith(backtab):
                tns.key_backtab(zti=zti2)
                sendstr += backtab
                rest = rest[len(backtab):]

            elif rest.startswith(curdown):
                tns.key_curdown(zti=zti2)
                sendstr += curdown
                rest = rest[len(curdown):]

            elif rest.startswith(curleft):
                tns.key_curleft(zti=zti2)
                sendstr += curleft
                rest = rest[len(curleft):]

            elif rest.startswith(curright):
                tns.key_curright(zti=zti2)
                sendstr += curright
                rest = rest[len(curright):]

            elif rest.startswith(curup):
                tns.key_curup(zti=zti2)
                sendstr += curup
                rest = rest[len(curup):]

            elif rest.startswith(delete):
                tns.key_delete(zti=zti)
                sendstr += delete
                rest = rest[len(delete):]

            elif rest.startswith(eraseeof):
                tns.key_eraseeof(zti=zti)
                sendstr += eraseeof
                rest = rest[len(eraseeof):]

            elif rest.startswith(home):
                tns.key_home(zti=zti2)
                sendstr += home
                rest = rest[len(home):]

            elif rest.startswith(insert):
                key_data = tns.key_ins_data
                sendstr += insert
                rest = rest[len(insert):]

            elif rest.startswith(newline):
                tns.key_newline(zti=zti2)
                sendstr += newline
                rest = rest[len(newline):]

            elif rest.startswith(tab):
                tns.key_tab(zti=zti2)
                sendstr += tab
                rest = rest[len(tab):]

            elif rest.startswith(reset):
                key_data = tns.key_data
                sendstr += reset
                rest = rest[len(reset):]
                prev_reset = True

            elif rest.startswith("[attn]"):
                tns.attn()
                sendstr += "[attn]"
                rest = rest[len("[attn]"):]
                sent = True
                break

            else:
                raise ValueError("unknown mneumonic")

        self.set("SENDSTR", sendstr, xtern=False)

        if sent and self.__gv["AUDIT"]:
            logger_host = self.__gv["logger_host"]
            lvl = logger_host.getEffectiveLevel()
            if lvl <= logging.INFO:
                logger_host.info("\n"+self.__capture())

        if sent:
            if zti2:
                zti2.rewrite_keylock = True

            # Definately do NOT refresh if this only put
            # characters on the screen. A refresh allows
            # the host to erase the characters just put on
            # the screen.
            # do a full refresh without suspending
            self.__refresh()  # good practice?

        else:
            self.__refresh_vars()

        if not sent or sent_sescheck:
            if self.__sescheck():
                return 12

        if sendstr == value:
            ati_rc = 0
        else:
            ati_rc = 4

        self.set("RC", ati_rc, xtern=False)
        return ati_rc

    def set(self, name, value, xtern=True, trace=None, verifycert=None):
        """Set an ATI-like variable.
        """
        rval = None
        if xtern and trace is not False:
            self.__logcode("set(%r,%s)", name, self.__snip(str(value)))

        unam = name.upper()
        if value is None:
            raise ValueError("value cannot be None")

        if value is True:
            valstr = "1"
        elif value is False:
            valstr = "0"
        else:
            valstr = str(value)

        if verifycert is not None and unam != "SESSION":
            raise RuntimeError("Using verifycert requires SESSION")

        if unam == "SESSION":
            self.__set_session(value,
                               verifycert=verifycert,
                               lognew=False)
            rval = self.rc
            if xtern and trace is not False:
                self.__logresult("RC = %r", rval)
                if rval == 0 or rval == 1:
                    self.__logresult("SESSION = %r", self.session)
                else:
                    self.__logresult("SESLOST = %r", self.seslost)

        elif unam == "AUDIT":
            self.audit = value
            if self.__gv[unam]:
                self.__logresult("%s = TRUE", unam)
            else:
                self.__logresult("%s = FLASE", unam)

        elif unam == "TRACE":
            valstr = valstr.upper().strip()
            self.trace = valstr
            if valstr != "CAPTURE":
                self.__logresult("%s = %r", unam, self.__gv[unam])

        elif unam == "DISPLAY":
            self.display = value
            self.__logresult("%s = %r", unam, self.__gv[unam])

        elif unam == "AGE":
            self.age = value
            self.__logresult("%s = %r", unam, str(self.num(value)))

        elif unam == "ONERROR":
            self.onerror = value
            if self.__gv[unam]:
                self.__logresult("%s = TRUE", unam)
            else:
                self.__logresult("%s = FLASE", unam)

        elif unam == "SESSION24":
            self.session24 = value
            if self.__gv[unam]:
                self.__logresult("%s = TRUE", unam)
            else:
                self.__logresult("%s = FLASE", unam)

        elif unam == "SHOWTYPE":
            self.showtype = value
            if self.__gv[unam]:
                self.__logresult("%s = TRUE", unam)
            else:
                self.__logresult("%s = FLASE", unam)

        elif unam == "WAITSLEEP":
            self.waitsleep = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "SCRUPDATE":
            raise RuntimeError('not implemented')

        elif unam == "KEYUNLOCK":
            self.keyunlock = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "LOGDEST":
            self.logdest = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "MAXLOSTWARN":
            self.maxlostwarn = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "MAXWAIT":
            self.maxwait = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "SCRDELAY":
            self.scrdelay = value
            self.__logresult("%s = %r", unam, str(self.__gv[unam]))

        elif unam == "SHOWLINE":
            self.showline = value
            self.__logresult("%s = %r", unam, valstr)

        elif unam == "SCRLIBS":
            raise RuntimeError('not implemented')

        elif xtern and unam in ("SESSIONS",
                                "MAXCOL",
                                "MAXROW",
                                "CURCOL",
                                "CURROW",
                                "HITCOL",
                                "HITROW",
                                "HISTRL",
                                "KEYLOCK",
                                "TIME",
                                "DATE",
                                "DATETIME",
                                "SENDSTR",
                                "SESLOST"):
            raise RuntimeError(unam+" is read-only")

        elif unam == "SESLOST":
            self.__drop_session()
            self.__gv[unam] = value

        elif unam in self.__ikeys:
            self.__gv[unam] = value
            self.__logresult("%s = %s", unam, self.__snip(valstr))

        elif unam in self.__uv:
            old_value = self.__uv[unam]
            if old_value is _GLOBAL:
                self.__gv[unam] = valstr
            else:
                self.__uv[unam] = valstr

            self.__logresult("%s = %s", unam, self.__snip(valstr))

        else:
            self.__uv[unam] = valstr
            self.__logresult("%s = %s", unam, self.__snip(valstr))

        return rval

    def share(self, *args):
        """Perform the ATI GLOBAL statement function
        """
        self.__logcode("share%s", args)
        for name in args:
            unam = name.upper()
            if unam in self.__ikeys:
                continue

            value = self.__uv.get(unam)
            if value is _GLOBAL:
                continue

            if value is not None:
                if unam in self.__gv:
                    raise RuntimeError(unam+" already set")

                self.__gv[unam] = value

            self.__uv[unam] = _GLOBAL

    def value(self, name, trace=None):
        """returns the contents of the ATI variable
           for the input name
        """
        if trace is not False:
            self.__logcode("value(%r)", name)

        rval = self[name]
        if rval is None:
            rval = name.upper().strip()

        elif rval is True:
            rval = "1"  # TRUE

        elif rval is False:
            rval = "0"  # FALSE

        else:
            rval = str(rval)

        if trace is not False:
            self.__logresult("%s", self.__snip(rval))

        return rval

    def wait(self, *args):
        """Wait for either a specific time limit or for a specified
        wait condition to be satisfied.

        Usage/Syntax:

            wait([{ss | '[[hh:]mm:]ss'}])
            wait([{ss | '[[hh:]mm:]ss'},] {bool | callable})

        hh
            Represents the number of hours to wait.

        mm
            Represents the number of minutes to wait.

        ss
            Represents the number of seconds to wait.

        :
            A delimiter that separates the hour, minute, and second.

        bool
            An expression that evaluates to True or False.

        callable
            An expression in the form of a callable (e.g. lambda)
            that returns a bool.


        Usage Notes:

            - The wait function will return upon a True expression
              (or when the wait time is exceeded).

            - The wait function will continuously request updates of
              the current host session screen. A wait time of 0 will
              cause a host screen update to occur and ATI processing
              to continue immediately.

            - If no time is specified, the wait time will be the
              value of the program variable MAXWAIT.

            - The condition is checked once every second unless the
              value of the internal variable, WAITSLEEP, is changed.

        Return Codes (return value and internal variable RC):

             0  The wait time expired before the expression was
                satisfied.

             1  The expression was satisfied before the wait time
                expired.

            12  Sesesion lost or undefined.
        """
        justtime = False
        timeout = self.__gv["MAXWAIT"]
        if len(args) == 0:
            expr = False
            justtime = True
        elif len(args) == 1:
            if args[0] is False:
                expr = False
            elif args[0] is True:
                expr = True
            elif callable(args[0]):
                expr = args[0]
            else:
                timeout = self.__seconds(args[0])
                expr = False
                justtime = True
        elif len(args) == 2:
            timeout = self.__seconds(args[0])
            expr = args[1]
        else:
            raise ValueError("wrong number of arguments")

        self.__logcode("wait%s", str(args))

        session = self.session
        byte_count = 0
        if session in self.__session_tnz:
            self.__refresh()
            byte_count = self.__ses_bytes()
        else:
            session = ""

        if expr in (True, False):
            func = None
        else:
            func = expr
            expr = False

        loopcnt = 0
        refreshcnt = 0
        sleepcnt = 0
        again = True
        tout = timeout
        otime = time.time()
        etime = otime+timeout
        while again:
            loopcnt += 1
            logger = self.__gv["logger"]
            logger.debug("                >>> tout = %d", tout)

            # maybe refresh satisfied the expression

            if func is not None:
                expr = func()
                otime = time.time()

            if expr:
                break

            rval = self.__runwhens()

            # maybe a WHEN satisfied the expression

            if rval and func is not None:
                expr = func()
                otime = time.time()
                if expr:
                    break

            nsession = self.session
            nbytecnt = 0
            if nsession in self.__session_tnz:
                nbytecnt = self.__ses_bytes()
            else:
                nsession = ""

            ttime = self.__gv["WAITSLEEP"]
            if func is not None:
                ttime = max(0, otime+ttime-time.time())

            tout = min(tout, ttime)
            rrv = 0
            if nsession and nsession in self.__session_tnz:
                if (session == nsession) and (byte_count == nbytecnt):
                    refreshcnt += 1
                    rrv = self.__refresh(tout, keylock=False)
            elif tout > 0:
                sleepcnt += 1
                time.sleep(tout)

            if rrv == -2:  # if force skip
                self.__logerror(">> User SKIP")
                break

            if rrv == -1:  # if force timeout
                self.__logerror(">> User TIMEOUT")

            session = nsession
            byte_count = nbytecnt

            tout = etime - time.time()
            if tout <= 0 or (rrv == -1):  # timeout or force timeout
                ati_rc = 0
                if self.__gv["ONERROR"] and not justtime:

                    self.__logerror(">> WAIT TIMEOUT occurred")

                    raise_it = True
                    if self.connected:
                        if os.isatty(0) and os.isatty(1):
                            if not self.__zti:
                                from . import zti
                                self.__zti = zti.create()

                            if self.__zti:
                                raise_it = False
                                rval = self.__zti.onerror()
                                if rval is None:  # user force ati_rc=1
                                    ati_rc = 1

                        self.__shell_mode()

                    if raise_it:
                        raise RuntimeError("WAIT TIMEOUT occurred")

                self.set("RC", ati_rc, xtern=False)
                return ati_rc

        self.set("RC", "1", xtern=False)
        return 1

    def when(self, *args):
        """ATI WHEN statement function.

        Usage/Syntax:

            @when({bool | callable | lambda: expression})
            def whenlabel():
                statement(s)

            when(whenlabel, [priority, ] ON)
            when(whenlabel, OFF)

        whenlabel
            The assigned name of the WHEN block.

        priority
            A priority level that a WHEN block is given at runtime.
            This determines the order of execution relative to other
            active WHEN blocks. The priority level is an integer
            between 1 and 5. The default priority is 1 (highest) at
            the start of program execution. The priority will remain
            the last value assigned to it on a WHEN ON statement.

        ON
            Used to begin the monitoring of whenlabel. All WHEN
            blocks are initialized to OFF. For any monitoring of WHEN
            blocks to occur, each WHEN must be explicitly turned ON.

        OFF
            Used to suspend the monitoring of whenlabel. It is highly
            recommended to turn off any unnecessary WHEN conditions.
            Excessive WHEN condition monitoring slows processing.

        <TODO - see share method>
            An indicator that a WHEN, when active, will execute in
            all included or called programs as well as the program in
            which it is declared.

        expression
            A WHEN condition in the form of an expression.

        statement(s)
            A list of statements to be executed whenever expression
            is true.


        Usage Notes

            -  The expression used in a WHEN block may involve a host
               screen check and/or an ATI variable check. The WHEN
               conditions may be classified to determine the
               frequency of monitoring.

            -  While a WHEN block is currently being executed, no
               other WHEN expressions are checked.

            -  A WHEN condition can be suspended or executed inside
               of a WHEN execution block.
        """
        if not args:
            raise ValueError("arguments required")

        if args[-1] is ON:
            if len(args) not in (1, 2, 3):
                raise ValueError("wrong number of arguments")

            func = args[0]
            func.ati[0] = self
            if len(args) == 3:
                priority = min(9, max(0, self.num(args[1])))
                self.__logcode("when(%s, %d, ON)",
                               func.__name__,
                               priority)
                func.pri[0] = priority
            else:
                priority = func.pri[0]
                self.__logcode("when(%s, ON)", func.__name__)

            func.active = True
            unam = func.__name__.upper().strip()
            wlist = self.__whens
            if unam not in wlist:
                wlist.append(unam)
                if self.__uv.get(unam, None) is _GLOBAL:
                    # TODO global/shared when not fully handled yet
                    self.__gv[unam] = func
                else:
                    self.__uv[unam] = func

            if not self.__inwhen:
                try:
                    self.__inwhen = True
                    func()

                finally:
                    self.__inwhen = False

            return None

        if args[-1] is OFF:
            if len(args) not in (1, 2):
                raise ValueError("wrong number of arguments")

            func = args[0]

            self.__logcode("when(%s, OFF)", func.__name__)

            func.active = False
            unam = func.__name__.upper().strip()
            try:
                self.__whens.remove(unam)
            except ValueError:
                pass

            return None

        decorator_tag = self.__loctag()

        condition = args[0]

        def when_func(func):
            name = func.__name__
            logtag = self.__loctag()
            pri = [1]  # default/initial priority=1
            ati = [self]

            @functools.wraps(func)
            def when_run():
                ati[0].__logwhen(decorator_tag+"when %s #%r: >>>",
                                 name, pri[0])
                crv = condition()
                if crv:
                    ati[0].__ranwhen = True
                    ati[0].__logwhen(logtag+"when %s: >>>", name)
                    func()
                    ati[0].__logwhen(logtag+"endwhen %s", name)

            when_run.pri = pri
            when_run.ati = ati
            when_run.active = False
            return when_run

        return when_func

    # private methods

    def __capture(self, headfoot=True):
        """Log the screen and return it as a string.
        """
        tns = self.get_tnz()
        self.__refresh_vars()

        crow = str(self.__gv["CURROW"])
        ccol = str(self.__gv["CURCOL"])
        maxcol = self.__gv["MAXCOL"]
        xcol = str(maxcol)
        xrow = str(self.__gv["MAXROW"])
        rlen = len(xrow)
        clen = len(xcol)

        stat = "".join(["Cursor= (",
                        right(crow, rlen),
                        ",",
                        right(ccol, clen),
                        "), Size= (",
                        right(xrow, rlen),
                        ",",
                        right(xcol, clen),
                        "), KeyLock= ",
                        self.__gv["KEYLOCK"],
                        ", Session= ",
                        self.__gv["SESSION"]])

        stat = "".join([left(stat, maxcol-15), self.time])

        if headfoot:
            divline = "-"*maxcol
            lines = [divline, stat, divline]
        else:
            lines = []

        scrstr = tns.scrstr(rstrip=False)
        for i in range(0, len(scrstr), maxcol):
            lines.append(scrstr[i:(i+maxcol)].rstrip())

        if headfoot:
            lines.append(divline)

        return "\n".join(lines)

    def __drop_session(self):
        """perform the DROP SESSION function

        Caller has verified a session is active.
        """
        self.__bytecnt += self.__ses_bytes()
        # self.__logresult("Network Bytes: %d", self.__bytecnt)

        session = self.session
        if session in self.__gv["seslost"]:
            self.__gv["seslost"].remove(session)

        # pick the next session
        if self.__session_tnz:
            found_current = False
            for k in self.__session_tnz:
                if found_current:
                    next_session = k
                    break

                if k == session:
                    found_current = True

            else:
                next_session = next(iter(self.__session_tnz))

        tns = self.__session_tnz.pop(session, None)
        if not self.__session_tnz:
            next_session = "NONE"
            self.__shell_mode()

        self.__gv["SESSION"] = next_session
        self.__refresh_vars()
        if tns:
            tns.shutdown()

        # elif connected and zti, show session? TODO

    def __loctag(self):
        frame = inspect.currentframe()
        progno = right(str(self.__pgm_number), 2)
        lineno = "????"
        while True:
            frame = frame.f_back
            if not frame:
                break

            module = inspect.getmodule(frame)
            if not module:
                continue

            name = module.__name__
            if not self.pgmname and name != __name__:
                self.pgmname = name

            if self.pgmname == name:
                lineno = right("   "+str(frame.f_lineno), 4)
                break

        else:  # program not found
            progno = " ?"

        return progno+"-"+lineno+": "

    def __log_check(self):
        if self.__gv["logger"]:
            return

        _tnz.Tnz.logging()

        # create ATI logger(s)
        # The intention is for each Ati instance to have its own log
        # destination. This basically means that each Ati logger is
        # unique. This is different from normal python logging where
        # the logger is generally specific to a module.
        # Furthermore, there is separate logging for CODE/RESULTS,
        # ERROR, and HOST.

        # TRACE = CODE
        # TRACE = RESULTS -> RESULTS + CODE
        # TRACE = ERROR
        # TRACE = HOST
        # TRACE = ALL -> RESULTS + ERROR + HOST

        # logger is the base and used for ALL and ERROR
        # logger_code is used for CODE and RESULTS
        # logger_host is used for HOST

        name = "tnz.ati."+str(id(self.__gv))
        logger = logging.getLogger(name)
        self.__gv["logger_code"] = logging.getLogger(name+".code")
        self.__gv["logger_host"] = logging.getLogger(name+".host")

        # initialized for TRACE = NONE
        logger.setLevel(logging.CRITICAL)
        self.__gv["logger_code"].setLevel(logging.CRITICAL)
        self.__gv["logger_host"].setLevel(logging.CRITICAL)
        self.__gv["logger"] = logger

    def __logcode(self, *args):
        self.__log_check()
        logger_code = self.__gv["logger_code"]
        lvl = logger_code.getEffectiveLevel()
        if lvl <= logging.INFO+1:
            msg = self.__loctag()+args[0]
            logger_code.log(logging.INFO+1, msg, *args[1:])

    def __logerror(self, *args):
        self.__log_check()
        self.__gv["logger"].warning(args[0], *args[1:])

    def __logresult(self, *args):
        self.__log_check()
        logger_code = self.__gv["logger_code"]
        lvl = logger_code.getEffectiveLevel()
        if lvl <= logging.INFO:
            msg = "         >>> "+args[0]
            logger_code.info(msg, *args[1:])

    def __logwhen(self, *args):
        self.__log_check()
        self.__gv["logger_code"].info(args[0], *args[1:])

    def __refresh(self, timeout=0, keylock=True):
        """Perform I/O.

        When zti is involved, downstream of zti.wait
        there may be calls to this function. It is
        unexpected for that to occur with a non-zero
        timeout. When allowed, zti methods do not
        expect to get back into zti methods.

        Return -1 if user is forcing timeout.

        Return -2 if user is forcing condition satisfied.

        Return 0 if timeout occurred.
            The screen did not change.
            The keyboard did not unlock.

        Return 1 if condition satisfied.
            It may be that the screen changed.
            It may be that the keyboard has unlocked.

        Return 12 if session lost.
        """
        self.__log_check()
        logger = self.__gv["logger"]
        logger.debug("in __refresh(%d)", timeout)

        in_wait = self.__in_wait
        if in_wait and timeout != 0:
            raise RuntimeError("Already in wait")

        okeylock = self.__gv["KEYLOCK"]
        if okeylock != "1":
            self.__refresh_vars()
            okeylock = self.__gv["KEYLOCK"]

        session = self.session
        tns = self.__session_tnz[session]
        seslost = tns.seslost

        if self.connected and not in_wait:
            zti = self.__zti
        else:
            zti = None

        display = self.__gv["DISPLAY"]
        if zti and display not in ("ALL", "HOST", "HOSTCODE"):
            zti = None

        if tns.updated:
            timeout = 0

        tout = timeout
        etime = time.time() + timeout
        while True:
            try:
                self.__in_wait = True
                if zti:
                    rval = zti.wait(tout, keylock=keylock)
                else:
                    rval = tns.wait(tout)

                self.__refresh_vars()

            finally:
                if not in_wait:
                    self.__in_wait = False

            if tns.updated:
                tns.updated = False
                logger_host = self.__gv["logger_host"]
                lvl = logger_host.getEffectiveLevel()
                if lvl <= logging.INFO:
                    logger_host.info("\n"+self.__capture())

                if rval:
                    if rval < 0:  # -1 or -2 from command line
                        return rval

                return 1  # condition satisfied

            if not rval:  # if timeout
                logger.debug("end __refresh(%d) timeout", timeout)
                return 0  # timeout

            if rval < 0:  # -1 or -2 from command line
                return rval

            if not seslost and tns.seslost:
                return 12  # session lost

            if self.__gv["KEYLOCK"] != okeylock:
                return 1  # condition satisfied

            tout = etime - time.time()
            if tout <= 0:
                logger.debug("end __refresh(%d) endtime", timeout)
                return 0  # timeout

    def __refresh_vars(self):
        tns = self.get_tnz()
        if tns:
            self.__gv["MAXROW"] = tns.maxrow
            self.__gv["MAXCOL"] = tns.maxcol
            currow, curcol = divmod(tns.curadd, tns.maxcol)
            self.__gv["CURROW"] = currow + 1
            self.__gv["CURCOL"] = curcol + 1
            if tns.pwait or tns.system_lock_wait:
                self.__gv["KEYLOCK"] = "1"
            else:
                self.__gv["KEYLOCK"] = "0"

    def __runwhens(self):
        logger = self.__gv["logger"]
        logger.debug("in _runwhens")

        if self.__inwhen:
            logger.debug("end _runwhens - in a when")
            return False

        self.__ranwhen = False
        try:
            self.__inwhen = True

            donel = []
            while True:
                wlist = self.__whens
                wlist.sort(key=self.__when_priority)

                for unam in wlist:
                    if unam not in donel:
                        break
                else:
                    break  # did all

                donel.append(unam)
                func = self.__uv[unam]
                if func is _GLOBAL:
                    func = self.__gv[unam]

                func()

        finally:
            self.__inwhen = False

        logger.debug("end _runwhens")
        return self.__ranwhen

    def __sescheck(self, ati_rc=12, trace=None):
        """Utility function to check session status.
           Input ati_rc=14 _forces_ a seslost condition.
        """
        session = self.__gv["SESLOST"]
        if session and ati_rc != 14:
            pass

        else:
            session = self.session
            tns = self.get_tnz()
            if tns and not tns.seslost and ati_rc != 14:
                return False

            # set SESLOST and DROP SESSION
            if tns:
                ses_exc = tns.seslost
                if not ses_exc or ses_exc is True:
                    ses_exc = None
            else:
                ses_exc = None

            self.ses_exc = ses_exc
            self.set("SESLOST", session, xtern=False, trace=trace)

        lostwarncnt = self.__gv["lostwarncnt"]
        maxlostwarn = self.__gv["MAXLOSTWARN"]

        if 0 < maxlostwarn <= lostwarncnt:
            raise RuntimeError("Excessive lost session warnings")

        lostwarncnt += 1
        self.__gv["lostwarncnt"] = lostwarncnt

        logger = self.__gv["logger"]
        if ati_rc == 14:
            logger.warning(
                "WARNING 14: excessive keyboard lock: %s",
                session)
        elif ati_rc == 8:
            logger.warning(
                "WARNING 8: Unable to establish session: %s",
                session)
        else:
            logger.warning(
                "WARNING 12: Session lost or undefined: %s",
                session)

        if trace is False:
            self.rc = ati_rc
        else:
            self.set("RC", ati_rc, xtern=False, trace=trace)

        return True

    def __ses_bytes(self):
        """Get bytes sent/received for current session
        """
        tns = self.get_tnz()
        if not tns:
            return 0

        return tns.bytes_sent + tns.bytes_received

    def __set_session(self, name, verifycert, lognew):
        unam = str(name).upper().strip()

        if not unam:
            raise ValueError("empty session name")

        if " " in unam:
            raise ValueError("space in session name")

        self.__gv["SESLOST"] = ""
        self.ses_exc = None

        zti = self.__zti
        if zti:
            display = self.__gv["DISPLAY"]
            if display not in ("ALL", "HOST", "HOSTCODE"):
                zti = None
            elif not self.connected:
                zti = None

        if zti:
            zti.rewrite = True

        if (unam in self.__session_tnz or
                (unam == self.session and unam != "NONE")):
            # existing session

            if verifycert is not None:
                raise RuntimeError("Used verifycert with old session")

            self.__gv["SESSION"] = unam
            self.__refresh()
            if self.__sescheck(trace=False):
                return

            self.rc = 1
            return

        if lognew:
            self.__logcode("SESSION = %r", unam)

        host = self["SESSION_HOST"]  # __getitem__
        if host:
            self.__logresult("%s = %r", "SESSION_HOST", host)

        port = self["SESSION_PORT"]  # __getitem__
        if port:
            port = int(port)
            self.__logresult("%s = %r", "SESSION_PORT", port)

        secure = self["SESSION_SSL"]  # __getitem__
        if secure is not None:
            secure = bool(self.num(secure))
            self.__logresult("%s = %r", "SESSION_SSL", secure)

        self.__gv["SESSION"] = unam

        try:
            tns = _tnz.connect(host, port, name=unam,
                               secure=secure, verifycert=verifycert)

        except Exception:
            tns = None
            logger = self.__gv["logger"]
            logger.exception("Connect Error")
            if self.connected:
                self.__shell_mode()
                traceback.print_exc()

        if not tns:
            self.__sescheck(8, trace=False)
            return

        self.__session_tnz[unam] = tns

        ps_size = self["SESSION_PS_SIZE"]  # __getitem__
        if ps_size:
            self.__logresult("%s = %r", "SESSION_PS_SIZE", ps_size)
            try:
                asize = _util.session_ps_size(ps_size)
                tns.amaxrow, tns.amaxcol = asize
            except ValueError:
                pass

        self.__logresult("%s = %r", "HA", tns.amaxrow)
        self.__logresult("%s = %r", "WA", tns.amaxcol)

        code_page = self["SESSION_CODE_PAGE"]  # __getitem__
        if code_page:
            code_page = code_page.lower()
            if not code_page.startswith("cp"):
                code_page = "cp"+code_page

            tns.encoding = code_page

        self.__logresult("%s = %r", "encoding", tns.encoding)

        tn3270e = self["SESSION_TN_ENHANCED"]  # __getitem__
        if tn3270e:
            tns.use_tn3270e = bool(self.num(tn3270e))

        lu_name = self["SESSION_LU_NAME"]  # __getitem__
        if lu_name:
            tns.lu_name = lu_name
            tns.use_tn3270e = True

        device_type = self["SESSION_DEVICE_TYPE"]  # __getitem__
        if device_type:
            tns.terminal_type = device_type

        self.__refresh()
        if not self.__sescheck(8, trace=False):
            self.rc = 0

    def __shell_mode(self):
        if self.__zti:
            self.__zti.shell_mode()

    def __when_priority(self, name):
        whenv = self.__uv[name]
        if whenv is _GLOBAL:
            whenv = self.__gv[name]

        return whenv.pri[0]

    # static methods

    @staticmethod
    def escape(text):
        """Escape special characters in text.

        Return a text string that is an escaped version of the input
        text string. The input text is treated as if it has no
        mneumonics and the returned text can be used as input to send
        without having any of it interpreted as a mneumonic.
        """
        return text.replace("[", "[[")

    @staticmethod
    def num(value):
        """Use ATI rules to convert the input string to an integer.
        """
        if isinstance(value, int):
            return int(value)  # int or bool->int

        string = str(value)
        if string.startswith("-"):
            string = string[1:]
            neg = True
        else:
            neg = False

        mat = re.search(r"[^0-9]", string)
        if mat is not None:
            string = string[:mat.start()]

        string = "0" + string
        if neg:
            string = "-" + string

        return int(string)

    # private static methods

    @staticmethod
    def __find(scr, value, casi=False, wc=None, fwd=True):
        """utility function for EXTRACT and SCRHAS
        """
        if not fwd:  # if must reverse strings
            scr = scr[len(scr)::-1]
            value = value[len(value)::-1]

        value = re.escape(value)
        if wc:
            wc = re.escape(wc[0])
            value = value.replace(wc, ".")

        flags = re.IGNORECASE if casi else 0
        regex = re.compile(value, flags)
        mat = re.search(regex, scr)
        if mat is None:
            return 0

        if fwd:
            return mat.start() + 1

        return len(scr) - mat.end() + 1

    @staticmethod
    def __seconds(value):
        """Convert [[hh:[mm:]ss to seconds.
        """
        if isinstance(value, int):
            return int(value)  # bool -> int

        tlist = str(value).split(":", maxsplit=2)
        tss = num(tlist[-1])
        tmm = num(tlist[-2]) if len(tlist) > 1 else 0
        thh = num(tlist[0]) if len(tlist) == 3 else 0
        return tss + (60*tmm) + (60*60*thh)

    @staticmethod
    def __snip(value):
        if len(value) > 40:  # if 'too long'
            value = value[:40].rstrip()
            return repr(value)+"..."

        return repr(value)

    @staticmethod
    def __century():
        """Use full year or only 2 digits.
        """
        dateform = os.environ.get("DATEFORM")
        if not dateform:
            return False

        return dateform.upper() == "LONG"

    # Readonly properties

    @property
    def curcol(self):
        """Cursor column value for current session.
        """
        self.__refresh_vars()
        return self.__gv["CURCOL"]

    @property
    def currow(self):
        """Cursor row value for current session.
        """
        self.__refresh_vars()
        return self.__gv["CURROW"]

    @property
    def date(self):
        """Current Date

        Contains the current date in the form mm/dd/yy. To get the
        date in mm/dd/yyyy form, set the DATEFORM environment
        variable to LONG (in any case).
        """
        if self.__century():
            return time.strftime("%Y/%m/%d")

        return time.strftime("%y/%m/%d")

    @property
    def datetime(self):
        """Current Date/Time

        Contains the current date and time in the form yy/mm/dd
        hh:mm:ss. To get the date in yyyy/mm/dd hh:mm:ss form, set
        the DATEFORM environment variable to LONG (in any case).
        """
        if self.__century():
            return time.strftime("%Y/%m/%d %H:%M:%S")

        return time.strftime("%y/%m/%d %H:%M:%S")

    @property
    def hitcol(self):
        """The column position of the first character of the string
        found by SCRHAS or the start column position of an
        EXTRACT.
        """
        return self.__gv["HITCOL"]

    @property
    def hitrow(self):
        """The row position of the first character of the string
        found by SCRHAS or the start row position of an EXTRACT.
        """
        return self.__gv["HITROW"]

    @property
    def hitstr(self):
        """String found

        The string that was found by the scrhas function.
        """
        return self.__gv["HITSTR"]

    @property
    def keylock(self):
        """Keyboard status

        Contains the keyboard status of the active session. Set to
        '1' if the active session is not accepting any input
        (keyboard lock); otherwise the value is set to '0'.
        """
        self.__refresh_vars()
        return self.__gv["KEYLOCK"]

    @property
    def maxcol(self):
        """Maximum column value for current session.
        """
        self.__refresh_vars()
        return self.__gv["MAXCOL"]

    @property
    def maxrow(self):
        """Maximum row value for current session.
        """
        self.__refresh_vars()
        return self.__gv["MAXROW"]

    @property
    def milliage(self):
        """Program age in milliseconds

        Contains the number of milliseconds that have elapsed since
        the object instance global context was created.
        """
        tval = self.__gv["milliage"]
        tval = time.time() - tval
        milliage = tval * 1000
        return int(milliage)

    @property
    def sendstr(self):
        """Sent string

        Contains the last string that was passed to the host session.
        """
        return self.__gv["SENDSTR"]

    @property
    def seslost(self):
        """Lost session identifier

        Contains the name of the session that was abnormally lost.

        Usage Notes:
          - This variable can be used to check if a session has 'gone
            away'; i.e., PVM drop, Mysterious Logical Device Support
            Drop, Excessive Keyboard Lock Drop, and so on. This
            variable is set upon a session assignment, wait, or send
            functions.

          - It is initialized to null (''), and it is set to null
            after a successful session assignment.
        """
        return self.__gv["SESLOST"]

    @property
    def sessions(self):
        """Available sessions

        A space-separated list of names of active sessions.
        """
        return " ".join(self.__session_tnz)

    @property
    def time(self):
        """Current Time

        Contains the current time in the form hh:mm:ss.
        """
        return time.strftime("%H:%M:%S")

    # Data descriptors

    @property
    def age(self):
        """Program Age in Seconds

        If unchanged by the program, contains the number of seconds
        that have elapsed since the program execution started.

        Usage Notes:

            - At the start of program execution, AGE is set to 0.

            - AGE is incremented once a second
        """
        tval = self.__gv["age"]
        tval = time.time() - tval
        return int(tval)

    @age.setter
    def age(self, value):
        age = self.num(value)
        tval = time.time()
        tval -= age
        self.__gv["age"] = tval

    @property
    def audit(self):
        """Set to 1 to enable audit tracing. Like TRACE='HOST', but
        screens are only traced when an AID is sent.
        """
        return self.__gv["AUDIT"]

    @audit.setter
    def audit(self, value):
        self.__gv["AUDIT"] = bool(self.num(value))

    @property
    def display(self):
        """Display Controls

        Determines how much host or Ati activity is displayed during
        program execution. Valid values:

          NONE
            No host or Ati activity is displayed. This is the default
            setting.

          ALL
            Displays both host screens and Ati functions in an
            alternating manner.

          CODE
            Displays a trace of the current Ati program.

          HOST
            Displays the entire host screen whenever it is referenced.

          HOSTCODE
            Displays the current ATI statement on the bottom line of
            the display with the upper part of the screen showing the
            current session.

          RESULTS
            Displays the results of function calls along with the Ati
            function calls as they are being executed.

          SINGLE
            Causes single-step tracing to begin, with both host
            screens and Ati functions being displayed.

        Usage Notes:

            - At the start of program execution, DISPLAY is set to NONE

            - DISPLAY is a read/write variable and can be changed at
              any time during execution.
        """
        return self.__gv["DISPLAY"]

    @display.setter
    def display(self, value):
        valstr = str(value).upper().strip()
        if self.connected:
            display = self.__gv["DISPLAY"]
            if valstr in ("ALL", "HOST", "HOSTCODE"):
                show = display not in ("ALL", "HOST", "HOSTCODE")
                if not self.__checked_tty:
                    self.__checked_tty = True
                    show = False
                    if os.isatty(0) and os.isatty(1):
                        self.__have_tty = True
                        show = True

                if self.__have_tty and self.__zti is None:
                    from . import zti
                    self.__zti = zti.create()

                if show and self.__zti and self.get_tnz():
                    self.__zti.show()

            elif display in ("ALL", "HOST", "HOSTCODE"):
                self.__shell_mode()

        self.__gv["DISPLAY"] = valstr

    @property
    def keyunlock(self):
        """Keyboard Unlock Wait Time

        The number of seconds that a send will wait for the keyboard to
        unlock before it actually sends the data.

        Usage Notes:

            KEYUNLOCK defaults to 60 (1 minute). If the KEYUNLOCK
            wait period expires due to a locked keyboard, the session
            is dropped (disconnected). In the rare case that an
            application stays in keyboard lock and the user would
            like to wait for it to unlock longer than the 1-minute
            default, KEYUNLOCK can be used to lengthen the time that
            a SEND waits.
        """
        return self.__gv["KEYUNLOCK"]

    @keyunlock.setter
    def keyunlock(self, value):
        self.__gv["KEYUNLOCK"] = max(1, self.num(value))

    @property
    def logcount(self):
        """Number of logs being managed.

        Default is 9. Can be set to other positive integers. Used
        only when LOGMAX is non-zero. Used to determine the number of
        backup logs kept when a log reaches the maximum size. When
        the number of bytes in the log is about to exceed this value,
        the log file is closed and a new file is opened for output.
        The old file will be renamed to end in '.n', where 'n' is the
        current total number of backups. The first backup will end in
        '.1', the second in '.2', etc.
        """
        return self.__gv["LOGCOUNT"]

    @logcount.setter
    def logcount(self, value):
        self.__gv["LOGCOUNT"] = self.num(value)

    @property
    def logdest(self):
        """Log Destination/File

        The name of the file where the history is recorded.

        Usage Notes:

            - If the file specified by expression already exists, the
              the log may be appended or truncated. See LOGTRUNC.

        Return Codes (internal variable RC):

             0  A handler is registered for the specified file

             -  other RC values if a failure occurred?
        """
        return self.__gv["LOGDEST"]

    @logdest.setter
    def logdest(self, value):
        valstr = str(value)
        uval = valstr.upper().strip()

        self.__log_check()
        logger = self.__gv["logger"]
        file_handler = self.__gv["file_handler"]
        stderr_handler = self.__gv["stderr_handler"]

        if file_handler is not None:
            logger.removeHandler(file_handler)
        elif stderr_handler:
            logger.removeHandler(stderr_handler)

        self.__gv["LOGDEST"] = valstr

        if uval == "(STDERR)":
            valstr = uval
            self.__gv["file_handler"] = None
            if stderr_handler:
                logger.addHandler(stderr_handler)

            logger.propagate = True
        else:
            if self.__gv["LOGTRUNC"]:
                filemode = "w"
                self.__gv["LOGTRUNC"] = False
            else:
                filemode = "a"

            logmax = numvalue("LOGMAX", trace=False)
            if logmax > 0:
                logcount = numvalue("LOGCOUNT", trace=False)
                file_handler = handlers.RotatingFileHandler(
                    valstr, filemode,
                    maxBytes=logmax,
                    backupCount=logcount,
                    encoding="utf8")
            else:
                file_handler = logging.FileHandler(
                    valstr, filemode, encoding="utf8")

            self.__gv["file_handler"] = file_handler
            formatter = logging.Formatter(
                "%(asctime)s %(message)s")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.propagate = False

    @property
    def logmax(self):
        """Maximum size of log file

        Default is 0. Can be set to a positive integer. When
        non-zero, value is the number of bytes at which log
        rollover/rotation occurs. When the number of bytes in the log
        is about to exceed this value, the log file is closed and a
        new file is opened for output.
        """
        return self.__gv["LOGMAX"]

    @logmax.setter
    def logmax(self, value):
        self.__gv["LOGMAX"] = self.num(value)

    @property
    def logtrunc(self):
        """Determine if existing log data is truncated (deleted)

        Default is 1. Can be set to 0 or 1. Affects processing done
        when LOGDEST is set. When 1 and LOGDEST identifies an
        existing file, the file will be truncated to 0 bytes before
        logging begins. When 0 and LOGDEST identifies an existing
        file, log entries will be appended to the existing file.
        After LOGDEST is set to a file, LOGTRUNC is set to 0.
        """
        return self.__gv["LOGTRUNC"]

    @logtrunc.setter
    def logtrunc(self, value):
        self.__gv["LOGTRUNC"] = bool(self.num(value))

    @property
    def maxlostwarn(self):
        """Maximum Lost Session Warnings

        Specifies the default maximum number of Lost Session warnings
        that will be output before the progem is aborted.

        Usage notes:

            - If MAXLOSTWARN is set to 0, the automatic aborting
              feature is disabled and an unlimited number of Warning
              12s can appear without the program aborting.

            - Upon program initialization MAXLOSTWARN is set to 5.

            - The setting of MAXLOSTWARN can be changed at any time
              during program execution.
        """
        return self.__gv["MAXLOSTWARN"]

    @maxlostwarn.setter
    def maxlostwarn(self, value):
        self.__gv["MAXLOSTWARN"] = self.num(value)

    @property
    def onerror(self):
        """Control error handler

        Turns the error handler on or off.
        """
        return self.__gv["ONERROR"]

    @onerror.setter
    def onerror(self, value):
        self.__gv["ONERROR"] = bool(self.num(value))

    @property
    def rc(self):
        """Return Code

        The return code from the last function that caused a return
        code to be generated.
        """
        return self.__gv["RC"]

    @rc.setter
    def rc(self, value):
        if value is None:
            raise ValueError("None not allowed")

        if isinstance(value, int):
            self.__gv["RC"] = int(value)
        else:
            self.__gv["RC"] = str(value)

    @property
    def scrdelay(self):
        """Screen Save Delay

        Not implemented.
        """
        return self.__gv["SCRDELAY"]

    @scrdelay.setter
    def scrdelay(self, value):
        self.__gv["SCRDELAY"] = max(0, self.num(value))

    @property
    def scrlibs(self):
        """Screen Library Search List

        Not implemented
        """
        return self.__gv["SCRLIBS"]

    @scrlibs.setter
    def scrlibs(self, value):
        raise RuntimeError('not implemented')

    @property
    def scrupdate(self):
        """Screen Comparison/Save Control

        Not implemented.
        """
        return self.__gv["SCRUPDATE"]

    @scrupdate.setter
    def scrupdate(self, value):
        self.__gv["SCRUPDATE"] = self.num(value)

    @property
    def session(self):
        """Current/Active Session

        Establish/determine the session for host interaction.

        Usage Notes:

            - The purpose of SESSION is to enable you to control
              multiple sessions within a single program. By
              establishing different sessions with unique names, you
              can change the current/active session at any time.

            - A program can check the return code after a SESSION a
              assignment. If the session had existed and a RC=12 is
              set, then the session has 'gone away' since the last
              interaction because of a PVM drop, Mysterious Logical
              Device Support Drop, Excessive Keyboard Lock Drop, and
              so on. See SESLOST -- Lost Session Identifier.

            - This setting can be changed at any time during program
              execution.

        Return Codes (internal variable RC):

             0  New session was established

             1  Session specified was established previously

             8  Unable to establish session

            12  Session specified was lost or undefined
        """
        return self.__gv["SESSION"]

    @session.setter
    def session(self, value):
        self.__set_session(value, verifycert=None, lognew=True)

    @property
    def session24(self):
        """Limit Session Terminal Type

        Limits new sessions to 24x80 with no extended attributes.

        Usage Notes:

            - SESSION24 is not session specific; i.e. if it is set to
              TRUE, it is active on all newly created sessions until
              it is set to FALSE.

            - The default SESSION24 value comes from the SESSION24
              environment variable.
        """
        return self.__gv["SESSION24"]

    @session24.setter
    def session24(self, value):
        self.__gv["SESSION24"] = bool(self.num(value))

    @property
    def sessionid(self):
        """Control Session Name Display

        Not implemented
        """
        return self.__gv["SESSIONID"]

    @sessionid.setter
    def sessionid(self, value):
        self.__gv["SESSIONID"] = self.num(value)

    @property
    def showtype(self):
        """Controls Send To Screen

        Setting to 1 (TRUE) causes the send data to be displayed on
        the screen of the current session when DISPLAY is set to HOST
        or HOSTCODE.

        Usage Notes:

            - SHOWTYPE can be left FALSE; however, when dealing with
              panel applications, CMS, or CP, this feature can
              greatly aid debugging.

            - The value of SHOWTYPE can be set to TRUE or FALSE
              throughout the program. SHOWTYPE is not session
              specific; i.e., if it is set TRUE, it affects all
              sessions in the program until it is set FALSE.

            - The default SHOWTYPE value comes from the SHOWTYPE
              environment variable.

            - The send data is automatically suppressed if the
              application being executed on the particular session
              addresses the screen in a no non-fullscreen mode
              Therefore, the echo does not operate with all
              applications.
        """
        return self.__gv["SHOWTYPE"]

    @showtype.setter
    def showtype(self, value):
        self.__gv["SHOWTYPE"] = bool(self.num(value))

    @property
    def trace(self):
        """Control Tracking/Logging

        Specifies the type of information that is written to the log
        file. Valid values:

          NONE
            No extra information is recorded. This is the default
            setting.

          ALL
            Sends all information from each of the other options to the
            log file.

          CAPTURE
            Logs the current session's screen and returns the TRACE
            variable to its previous value.

          CODE
            Logs a trace of the function calls that involve an Ati
            instance method.

          ERROR
            Causes logging to be done when either of the following
            errors occur:

            - A wait function containing an expression times out
              (returns a 0 code)

            - A FIRST or LAST character string in an extract or scrhas
              function call was not found on the host screen. The
              FIRST or LAST character string is recorded.

          HOST
            Logs each host screen as it is scanned. The screen
            dimensions, cursor position keyboard lock flag, and time
            are also logged above the screen data.

          RESULTS
            Logs a trace of the results of function calls that
            involve an Ati instance method.
        """
        return self.__gv["TRACE"]

    @trace.setter
    def trace(self, value):
        self.__log_check()
        uval = str(value).upper().strip()

        logger = self.__gv["logger"]
        if uval == "CAPTURE":
            if not self.__sescheck():
                logger.critical("\n"+self.__capture(headfoot=False))

        else:
            # ERROR    messages are logged at the WARNING  level
            # CODE     messages are logged at the INFO+1   level
            # RESULTS  messages are logged at the INFO     level
            # HOST     messages are logged at the INFO     level
            if uval == "NONE":
                logger.setLevel(logging.CRITICAL)
                self.__gv["logger_code"].setLevel(logging.CRITICAL)
                self.__gv["logger_host"].setLevel(logging.CRITICAL)

            elif uval == "ERROR":  # more like a warning?
                logger.setLevel(logging.WARNING)
                self.__gv["logger_code"].setLevel(logging.CRITICAL)
                self.__gv["logger_host"].setLevel(logging.CRITICAL)

            elif uval == "CODE":
                logger.setLevel(logging.CRITICAL)
                self.__gv["logger_code"].setLevel(logging.INFO+1)
                self.__gv["logger_host"].setLevel(logging.CRITICAL)

            elif uval == "RESULTS":
                logger.setLevel(logging.CRITICAL)
                self.__gv["logger_code"].setLevel(logging.INFO)
                self.__gv["logger_host"].setLevel(logging.CRITICAL)

            elif uval == "HOST":
                logger.setLevel(logging.CRITICAL)
                self.__gv["logger_code"].setLevel(logging.CRITICAL)
                self.__gv["logger_host"].setLevel(logging.INFO)

            elif uval == "ALL":
                logger.setLevel(logging.INFO)
                self.__gv["logger_code"].setLevel(logging.INFO)
                self.__gv["logger_host"].setLevel(logging.INFO)

            else:
                raise ValueError("bad trace value")

            self.__gv["TRACE"] = uval

    @property
    def waitsleep(self):
        """Check interval for wait/when

        Sets the time interval (in seconds) that the wait function
        conditions and active when functions are checked. Can be an
        integer from 1 to 99.

        Usage Notes:

          - Initialized to 1. That is, the condition of a wait
            function is checked every second or every screen update
            until the wait condition is satisfied or the wait times
            out. This value is used to improve system performance by
            increasing the time between wait rechecks to longer
            intervals.

          - Does not affect the length of a wait. For example, if
            waitsleep=10 and a 2-second wait is requested, the
            maximum wait time is still only 2 seconds, which is
            checked in one interval.
        """
        return self.__gv["WAITSLEEP"]

    @waitsleep.setter
    def waitsleep(self, value):
        self.__gv["WAITSLEEP"] = max(min(self.num(value), 99), 1)

    # write-only data

    def __maxwait(self, value):
        """Maximum Wait Time Default

        Specifies the default maximum wait time for the wait function.
        """
        self.__gv["MAXWAIT"] = max(0, self.__seconds(value))

    maxwait = property(None, __maxwait, None, __maxwait.__doc__)

    def __showline(self, value):
        """Show message line

        Can be used to communicate with the terminal user by using
        the bottom line of the screen for output.
        """
        if self.connected:
            print_check = True
            if self.__zti and self.__zti.prog_mode:
                if self.__zti.showline(value):
                    print_check = False

            if print_check:
                if "showline" in self.__gv:
                    if value != self.__gv["showline"]:
                        print(str(value))
                else:
                    print(str(value))

        self.__gv["showline"] = value

    showline = property(None, __showline, None, __showline.__doc__)

    # private class data

    __ati_stack = []


class _AtiConst():
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


_GLOBAL = {}  # use as value in __uv to indicate to look in __gv

CASI = _AtiConst("CASI")  # use for scrhas
EOL = _AtiConst("EOL")  # use for extract
FIRST = _AtiConst("FIRST")  # use for extract,scrhas
LAST = _AtiConst("LAST")  # use for extract,scrhas
OFF = _AtiConst("OFF")  # use for when
ON = _AtiConst("ON")  # use for when
FALSE = "0"
TRUE = "1"

# control keys
clear = "[clear]"
enter = "[enter]"
pa1 = "[pa1]"
pa2 = "[pa2]"
pa3 = "[pa3]"
pf1 = "[pf1]"
pf2 = "[pf2]"
pf3 = "[pf3]"
pf4 = "[pf4]"
pf5 = "[pf5]"
pf6 = "[pf6]"
pf7 = "[pf7]"
pf8 = "[pf8]"
pf9 = "[pf9]"
pf01 = "[pf01]"
pf02 = "[pf02]"
pf03 = "[pf03]"
pf04 = "[pf04]"
pf05 = "[pf05]"
pf06 = "[pf06]"
pf07 = "[pf07]"
pf08 = "[pf08]"
pf09 = "[pf09]"
pf10 = "[pf10]"
pf11 = "[pf11]"
pf12 = "[pf12]"
pf13 = "[pf13]"
pf14 = "[pf14]"
pf15 = "[pf15]"
pf16 = "[pf16]"
pf17 = "[pf17]"
pf18 = "[pf18]"
pf19 = "[pf19]"
pf20 = "[pf20]"
pf21 = "[pf21]"
pf22 = "[pf22]"
pf23 = "[pf23]"
pf24 = "[pf24]"

backtab = "[backtab]"
btab = "[backtab]"
curdown = "[down]"
cdn = "[down]"
curleft = "[left]"
clf = "[left]"
curright = "[right]"
crt = "[right]"
curup = "[up]"
cup = "[up]"
delete = "[delete]"
eraseeof = "[eraseeof]"
ereof = "[eraseeof]"
home = "[home]"
insert = "[insert]"
ins = "[insert]"
newline = "[newline]"
nl = "[newline]"
tab = "[tab]"

reset = "[reset]"

# these functions are just aliases

stripl = str.lstrip
stript = str.rstrip
upper = str.upper
num = Ati.num

ati = Ati()  # initial/default instance

# functions using singleton Ati instance


def drop(*args):  # DROP: statement
    return ati.drop(*args)


drop.__doc__ = Ati.drop.__doc__


def extract(*args, wc=None):  # EXTRACT: statement
    return ati.extract(*args, wc=wc)


extract.__doc__ = Ati.extract.__doc__


def share(*args):
    return ati.share(*args)


share.__doc__ = Ati.share.__doc__


def logwrt(value):
    return ati.logwrt(value)


logwrt.__doc__ = Ati.logwrt.__doc__


def numvalue(name, trace=None):  # numvalue: -- remove?
    return ati.numvalue(name, trace=trace)


numvalue.__doc__ = Ati.numvalue.__doc__


def rename(name):  # rename: -- remove?
    return ati.rename(name)


rename.__doc__ = Ati.rename.__doc__


def say(value):
    return ati.say(value)


say.__doc__ = Ati.say.__doc__


def scrcomp(value):
    return ati.scrcomp(value)


scrcomp.__doc__ = Ati.scrcomp.__doc__


def scrhas(*args, wc=None):
    return ati.scrhas(*args, wc=wc)


scrhas.__doc__ = Ati.scrhas.__doc__


def send(*args):
    return ati.send(*args)


send.__doc__ = Ati.send.__doc__


def set(name, value, xtern=True, trace=None):
    return ati.set(name, value, xtern=xtern, trace=trace)


set.__doc__ = Ati.set.__doc__


def value(name, trace=None):
    return ati.value(name, trace=trace)


value.__doc__ = Ati.value.__doc__


def wait(*args):
    return ati.wait(*args)


wait.__doc__ = Ati.wait.__doc__


def when(*args):
    return ati.when(*args)


when.__doc__ = Ati.when.__doc__
