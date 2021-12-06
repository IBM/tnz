"""ditto-like interface to tnz

This module is intended to help with porting Ditto code to python.
Ditto was an IBM internal tool used to automate 3270 interactions.

USAGE
    from tnz.ditto import Ditto
    dit = Ditto()
    dit...

Ditto programs are generally viewed through
a gui. The contents of the program are viewed
in a table format with 6 columns:
      - Enable/Disable
      - Command Session
      - Command Text
      - Verify Session
      - Verify Timeout
      - Verify Text

The strategy to handle Enable/Disable in
python is to use python comments - comment out
the line of code to disable it.

Both the Command and Verify sessions will be
arguments to the various command and verify functions.

Ditto has various different types of commands.
Each type will be a different method and the
method will document the corresponding command type.
Some command types do not have corresponding methods.

The VAR command has no corresponding method. Use python variables.
The VAR command allowed use of various Ditto function. Most can be
translated to python builtin functions:

    Ditto                            python
    LENGTH(string)                   len(string)
    SUBSTRING(string, start,length)  string[start:start+length]
    REPLACE(string, find, replace)   string.replace(find, replace)
    UCASE(string)                    string.upper()
    LCASE(string)                    string.lower()
    TRIM(string)                     string.strip()
    SPLIT(string, delimiter)         string.split(delimiter)
    scriptname.dit(...)              python function call/import?

The GVAR command has no corresponding method. Use python global
variables.

The PW command has no corresponding method. Consider netrc.

The RETURN command has no corresponding method.

The J= commands have no corresponding methods. Use python control
flow.

The IF and END IF commands have no corresponding methods. Use python
control flow.

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
from . import ati as _ati
from . import __version__

__author__ = "Neil Johnson"


class Ditto(object):
    """Manage script processing

       Methods corresponding to Ditto command text:
           close                         C=CLOSE
           connect                       C=CONNECT
           cursor_after                  @=
           cursor_before                 @-
           disconnect                    C=DISCONNECT
           editclear                     C=EDITCLEAR
           enter                         <other>
           execute_external_application  E=
           log                           C=LOG
           logtext                       C=LOGTEXT
           pause                         P=
           restartalllogs                C=RESTARTALLLOGS
           send_without_enter            ~
           waitfor                       C=WAITFOR

       Methods corresponding to Ditto VAR command text functions:
           getchar                       GETCHAR
    """

    def __init__(self, ati=None):
        """Create object to manage script processing
        """
        self.__verify_delay = None  # default?
        self.__command_delay = None  # default?
        self.__auto_clear_more = None  # default?
        self.__sessions = {}

        if ati is None:
            ati = _ati.ati

        self.__ati = ati
        ati.set("TRACE", "ALL")
        ati.set("ONERROR", "1")
        ati.set("DISPLAY", "HOST")

        @ati.when(self.__check_clear_more)
        def clear_more():
            ati.send(_ati.clear)
        self.__clear_more = clear_more

    # public methods

    def close(self, session):
        """Use for Ditto C=CLOSE command text.
        """
        ati = self.__ati
        self.set_session(session)
        self.__sessions.pop(ati.session, None)
        ati.drop("SESSION")

    def connect(self, session):
        """Use for Ditto C=CONNECT command text.
        """
        ati = self.__ati
        session = session.upper()  # TODO more needed?
        props = self.__sessions.get(session, None)
        if props is None:
            raise ValueError(f"session {session} unavailable")

        for k in props:
            ati.set(k, props[k])

        ati_rc = ati.set("SESSION", session)
        if ati_rc == 1:  # reestablished session
            raise RuntimeError("already connected")

        if ati_rc != 0:  # new session
            raise RuntimeError(f"set session error {ati_rc}")

    def cursor_after(self, session, identifier_string):
        """Use for Ditto @=identifier_string command text.
        """
        # would tab be more useful than curright
        key = _ati.curright * len(identifier_string)
        self.__key_at(session, identifier_string, key)

    def cursor_before(self, session, identifier_string):
        """Use for Ditto @-identifier_string command text.
        """
        # would backtab be more useful than curleft?
        key = _ati.curleft
        self.__key_at(session, identifier_string, key)

    def disconnect(self, session):
        """Use for Ditto C=DISCONNECT command text.
        """
        ati = self.__ati
        self.set_session(session)
        tns = ati.get_tnz()
        props = {}
        pnaddr, pnport = tns.getpeername()
        props["SESSION_HOST"] = pnaddr
        props["SESSION_PORT"] = pnport

        lu_name = tns.lu_name
        if lu_name:
            props["SESSION_LU_NAME"] = lu_name

        props["SESSION_PS_SIZE"] = f"{tns.amaxrow}x{tns.amaxcol}"
        props["SESSION_TN_ENHANCED"] = tns.tn3270e
        props["SESSION_DEVICE_TYPE"] = tns.terminal_type
        self.__sessions[ati.session] = props
        ati.drop("SESSION")

    def editclear(self, session):
        """Use for Ditto C=EDITCLEAR command text.
        """
        self.set_session(session)
        tns = self.__ati.get_tnz()
        tns.key_eraseinput()

    def enter(self, session=None, text="", pos=None):
        """Use for Ditto command text that enters a text string.
        """
        if text or pos:
            text = text.replace("[", "[[")
            self.send_without_enter(session, text, pos)

        else:
            self.set_session(session)

        ati_rc = self.__ati.send(_ati.enter)
        if ati_rc != 0:
            raise RuntimeError(f"send enter error {ati_rc}")

    def enter_after(self, session, identifier_string, text):
        """Shorthand for cursor_after followed by enter.
        """
        self.cursor_after(session, identifier_string)
        self.enter(text=text)

    def execute_external_application(self, application):
        """Use for Ditto E=application command text.
        """
        import os
        os.system(application)

    def getchar(self,
                matching,
                length=1,
                direction="A",
                offset=0,
                start="FT"):
        """Like the GETCHAR Ditto function that could be used on VAR
           commands.

           Arguments:
               matching  - The string to match on the screen which
                           serves as a starting point. By default, the
                           first occurrence of matching will be found.
                          *The matching string can begin with "+" or "_"
                          *to force the search for that matching string
                          *to be sequential or on the same line,
                          *respectively.
               length    - the number of characters to extract
               direction - specifies whether to extract characters
                           before ('B') or after ('A') the matching
                           string.
               offset    - specifies the number of characters to ignore
                           from where the matching string was found. The
                           offset is affected by the direction:
                               B - ignore x number of characters from
                                   BEFORE the START of where the
                                   matching string was found
                               A - ignore x number of characters from
                                   AFTER the END of where the matching
                                   string was found
               start     - specifies whether to start searching for the
                           matching string from the top of the screen
                           ('FT') or from the bottom of the screen
                           ('FB').
        """
        ati = self.__ati
        if direction not in ("A", "B"):
            raise ValueError("bad direction")

        if start not in ("FT", "FB"):
            raise ValueError("bad start")

        if start == "FT":
            f_or_l = _ati.FIRST
        else:
            f_or_l = _ati.LAST

        matching_len = len(matching)

        if direction == "A":
            row = 0  # assume same row
            col = offset
        else:
            row = 0  # assume same row
            col = 0 - matching_len - offset - length

        rval = ati.extract(length, f_or_l, matching, (row, col))
        ati_rc = _ati.num(ati.rc)
        if ati_rc != 0:
            raise RuntimeError(f"extract error {ati_rc}")

        return rval

    def log(self):
        """Use for Ditto C=LOG command text.
        """
        self.__ati.set("TRACE", "CAPTURE")

    def logtext(self, text):
        """Use for Ditto C=LOGTEXT(text) command text.
        """
        self.__ati.logwrt(text)

    def pause(self, seconds):
        """Use for Ditto P=seconds command text.
        """
        self.__ati.wait(seconds)

    def restartalllogs(self, text):
        """Use for Ditto C=RESTARTALLLOGS command text.
        """
        ati = self.__ati
        logdest = ati.logdest
        ati.logdest = logdest

    def send_without_enter(self, session, text, pos=None):
        """Use for Ditto ~text command text or to send a keystroke.
        """
        if session is not None:
            self.set_session(session)

        if pos is None:
            ati_rc = self.__ati.send(text)
        else:
            ati_rc = self.__ati.send(pos, text)

        if ati_rc != 0:
            raise RuntimeError(f"send error {ati_rc}")

    def set_session(self, session):
        ati = self.__ati
        if session != ati.session:
            ati_rc = ati.set("SESSION", session)
            if ati_rc != 1:  # reestablished session
                raise RuntimeError(f"set session error {ati_rc}")

    def verify(self, session, text, timeout=None):
        """Use for Ditto verify commands.
        """
        ati = self.__ati
        if session is not None:
            self.set_session(session)

        if timeout is None:
            ati_rc = ati.wait(lambda: ati.scrhas(text))
        else:
            ati_rc = ati.wait(timeout, lambda: ati.scrhas(text))

        if ati_rc != 1:
            raise RuntimeError(f"wait error {ati_rc}")

    def waitfor(self, session):
        """Use for Ditto C=WAITFOR command text.
        """
        ati = self.__ati
        if session is not None:
            self.set_session(session)

        ati_rc = ati.wait(self.__active)
        if ati_rc != 1:
            raise RuntimeError(f"wait error {ati_rc}")

    # properties

    @property
    def VerifyDelay(self):
        return self.__verify_delay

    @VerifyDelay.setter
    def VerifyDelay(self, value):
        self.__verify_delay = bool(value)

    @property
    def CommandDelay(self):
        return self.__command_delay

    @CommandDelay.setter
    def CommandDelay(self, value):
        self.__command_delay = bool(value)

    @property
    def AutoClearMore(self):
        return self.__auto_clear_more

    @AutoClearMore.setter
    def AutoClearMore(self, value):
        value = bool(value)
        if value:
            self.__ati.when(self.__clear_more, _ati.ON)
        else:
            self.__ati.when(self.__clear_more, _ati.OFF)

        self.__auto_clear_more = value

    # private methods

    def __check_clear_more(self):
        ati = self.__ati
        return (ati.value("SESSION") != "NONE" and
                ati.value("KEYLOCK") == "0" and
                ati.scrhas(_ati.CASI, "MORE", (-1, -21)))

    def __active(self):
        ati = self.__ati
        if ati.value("KEYLOCK") != "0":
            return False

        tns = ati.get_tnz()
        if tns.field(0) == (-1, 0):  # no fields
            return False

        return not tns.is_protected(tns.curadd)

    def __unlocked(self):
        return self.__ati.value("KEYLOCK") == "0"

    def __key_at(self, session, identifier_string, key):
        ati = self.__ati

        if session is not None:
            self.set_session(session)

        ati_rc = ati.wait(self.__unlocked)  # needed?
        if ati_rc != 1:
            raise RuntimeError(f"wait error {ati_rc}")

        if not ati.scrhas(identifier_string):
            raise RuntimeError("identifier string not found")

        pos = (ati.numvalue("HITROW"), ati.numvalue("HITCOL"))
        ati_rc = ati.send(pos, key)
        if ati_rc != 0:
            raise RuntimeError(f"send error {ati_rc}")
