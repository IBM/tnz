"""py3270-like interface to tnz

Goal 1
------
Allow a python program to be built that, other
than the import statement, is compatable with
py3270.

Goal 2
------
Allow a program like the following to be built:
    from tnz import py3270 as *
    <use x3270-script functions/variables>

In such a program, other than the from/import
statement, the remainder of the program is a
valid script for the x3270 family of programs.

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""

from enum import Enum
from functools import wraps

from . import ati as _ati
from . import rexx as _rexx
from . import zti as _zti
from . import __version__

__all__ = ["AnsiText",
           "Ascii", "AsciiField", "Connect",
           "CloseScript", "ContinueScript",
           "Disconnect", "Ebcdic", "EbcdicField",
           "Enter",
           "Info",
           "Expect", "Keymap",
           "MoveCursor",
           "PauseScript",
           "PrintText",
           "Query", "ReadBuffer",
           "Script",
           "Snap",
           "Source",
           "String",
           "Title",
           "Toggle",
           "Transfer", "Wait",
           "InputField", "NVTMode",
           "Output", "Unlock", "Seconds",
           "send", "receive", "tso", "vm",
           "binary", "add", "keep", "replace", "append",
           "fixed", "variable", "undefined",
           "tracks", "cylinders", "avblock",
           "yes", "no", "remove"]
__author__ = "Neil Johnson"


def _x3270(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        try:
            rval = func(*args, **kwargs)
            if not rval:
                rval = ["ok"]

        except Exception as exc:
            rval = [f"data: {exc}", "error"]

        rval.insert(-1, self.status_str())
        if self is _emulator:
            print(*rval, sep="\n")

        return rval

    return wrapper


class CommandError(Exception):
    """Raised if Command.execute fails.
    """


class Command(object):
    """Represents a x3270 script command.
    """
    def __init__(self, app, cmdstr):
        if isinstance(cmdstr, bytes):
            cmdstr = cmdstr.decode("ascii")

        self.app = app  # actually, Emulator
        self.cmdstr = cmdstr
        self.status_line = None
        self.data = None
        self.__text = None

    def execute(self):
        """Execute the command.
        """
        cmdstr = self.cmdstr.strip()
        if not cmdstr.endswith(")"):
            parts = cmdstr.split(maxsplit=1)
            if len(parts) == 1:
                cmdstr += "()"
            else:
                cmdstr = parts[0] + "(" + parts[1] + ")"

        textl = eval(cmdstr, {}, self.app.locals)
        self.__text = textl
        datal = list(map(str.encode, textl))  # to ascii?
        self.data = datal
        self.status_line = datal[-2]

        if textl[-1] != "ok":
            raise CommandError(f"execute failed: {textl!r}")


class Emulator(object):
    """Represents an x/s3270 emulator.
    """
    # x3270 actions
    # See http://x3270.bgp.nu/x3270-man.html

    @_x3270
    def Attn(self):
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        tns.attn()
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    @_x3270
    def AltCursor(self):
        raise RuntimeError("AltCursor not implemented")

    @_x3270
    def BackSpace(self):
        self.__send(_ati.curleft)

    @_x3270
    def BackTab(self):
        self.__send(_ati.backtab)

    @_x3270
    def CircumNot(self):
        # what about "^" for NVT mode?
        if self.__insert:
            self.__send("[insert]\u00ac")
        else:
            self.__send("\u00ac")

    @_x3270
    def Clear(self):
        self.send_clear()

    @_x3270
    def Compose(self):
        raise RuntimeError("Compose not implemented")

    @_x3270
    def Connect(self, host):
        if self.is_connected():
            raise RuntimeError("Already connected")

        self.connect(host)

    @_x3270
    def CursorSelect(self):
        raise RuntimeError("CursorSelect not implemented")

    @_x3270
    def Cut(self):
        raise RuntimeError("Cut not implemented")

    @_x3270
    def Delete(self):
        self.__send(_ati.delete)

    @_x3270
    def DeleteField(self):
        self.delete_field()

    @_x3270
    def DeleteWord(self, *args):
        raise RuntimeError("DeleteWord not implemented")

    @_x3270
    def Disconnect(self):
        self.terminate()

    @_x3270
    def Down(self, *args):
        self.__send(_ati.curdown)

    @_x3270
    def Dup(self, *args):
        raise RuntimeError("Dup not implemented")

    @_x3270
    def Enter(self):
        self.send_enter()

    @_x3270
    def Erase(self):
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        tns.key_backspace(zti=self.__zti)

    @_x3270
    def EraseEOF(self):
        self.__send(_ati.ereof)

    @_x3270
    def EraseInput(self):
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        tns.key_eraseinput(zti=self.__zti)

    @_x3270
    def Execute(self, cmd):
        import os
        os.system(cmd)

    @_x3270
    def FieldEnd(self):
        raise RuntimeError("FieldEnd not implemented")

    @_x3270
    def FieldMark(self):
        raise RuntimeError("FieldMark not implemented")

    @_x3270
    def HandleMenu(self, name):
        raise RuntimeError("HandleMenu not implemented")

    @_x3270
    def HexString(self, hex_digits):
        raise RuntimeError("HexString not implemented")

    @_x3270
    def Home(self):
        self.__send(_ati.home)

    @_x3270
    def Insert(self):
        self.__insert = True

    @_x3270
    def Interrupt(self, *args):
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        tns.send_command(244)  # IP (Interrupt Process)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    @_x3270
    def Key(self, keysym_or_code):
        raise RuntimeError("Key not implemented")

    @_x3270
    def Keymap(self, keymap):
        raise RuntimeError("Keymap not implemented")

    @_x3270
    def KybdSelect(self, *args):
        raise RuntimeError("KybdSelect not implemented")

    @_x3270
    def Left(self):
        self.__send(_ati.curleft)

    @_x3270
    def Left2(self, *args):
        self.__send("[left][left]")

    @_x3270
    def Macro(self, macro):
        raise RuntimeError("Macro not implemented")

    @_x3270
    def MonoCase(self):
        raise RuntimeError("MonoCase not implemented")

    @_x3270
    def MoveCursor(self, row, col):
        self.__send((row+1, col+1), "")

    @_x3270
    def MoveCursorSelect(self):
        raise RuntimeError("MoveCursorSelect not implemented")

    @_x3270
    def Newline(self, *args):
        self.__send(_ati.newline)

    @_x3270
    def NextWord(self, *args):
        raise RuntimeError("NextWord not implemented")

    @_x3270
    def PA(self, value):
        self.__send(f"[pa{value}]")
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    @_x3270
    def PF(self, value):
        self.__send(f"[pf{value}]")
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    @_x3270
    def PreviousWord(self, *args):
        raise RuntimeError("PreviousWord not implemented")

    @_x3270
    def Printer(self, cmd, logical_unit=None):
        raise RuntimeError("Printer not implemented")

    @_x3270
    def PrintText(self, command):
        raise RuntimeError("PrintText not implemented")

    @_x3270
    def PrintWindow(self, command):
        raise RuntimeError("PrintWindow not implemented")

    @_x3270
    def Quit(self):
        self.terminate()

    @_x3270
    def Reconnect(self):
        self.reconnect()

    @_x3270
    def Redraw(self):
        raise RuntimeError("Redraw not implemented")

    @_x3270
    def Reset(self):
        raise RuntimeError("Reset not implemented")

    @_x3270
    def Right(self):
        self.__send(_ati.curright)

    @_x3270
    def Right2(self):
        self.__send("[right][right]")

    @_x3270
    def Script(self, command, *args):
        raise RuntimeError("Script not implemented")

    @_x3270
    def Scroll(self, dir):
        raise RuntimeError("Scroll not implemented")

    @_x3270
    def SelectAll(self, atom):
        raise RuntimeError("SelectAll not implemented")

    @_x3270
    def SetFont(self, font):
        raise RuntimeError("SetFont not implemented")

    @_x3270
    def String(self, string):
        if self.__insert:
            string = self.__encode(string)
            self.__send("[insert]"+string)
        else:
            self.send_string(string)

    @_x3270
    def Tab(self, *args):
        self.__send(_ati.tab)

    @_x3270
    def Toggle(self, option, value=None):
        if option.startswith("_"):
            raise ValueError(f"{option!r} not valid")

        if not hasattr(self, option):
            raise ValueError(f"no {option!r} option")

        if value is not None:
            setattr(self, option, bool(value))
        else:
            value = getattr(self, option)
            setattr(self, option, not value)

    @_x3270
    def ToggleInsert(self):
        self.__insert = not self.__insert

    @_x3270
    def ToggleReverse(self):
        raise RuntimeError("ToggleReverse not implemented")

    @_x3270
    def Transfer(self, **kwargs):
        dir = kwargs.pop("Direction", receive)
        host_file = kwargs.pop("HostFile")
        local_file = kwargs.pop("LocalFile")
        host_type = kwargs.pop("Host", tso)
        mode = kwargs.pop("Mode", ascii)
        opt_cr = kwargs.pop("Cr", remove)
        remap = kwargs.pop("Remap", yes)
        exist = kwargs.pop("Exist", keep)

        if host_type != cics:
            recfm = kwargs.pop("Recfm", None)
            lrecl = kwargs.pop("Lrecl", None)
            blksize = kwargs.pop("Blksize", None)

        if host_type == tso:
            allocation = kwargs.pop("Allocation", None)
            p_space = kwargs.pop("PrimarySpace", None)
            s_space = kwargs.pop("SecondarySpace", None)
            avblock = kwargs.pop("Avblock", None)

        _ = kwargs.pop("BufferSize", None)

        if kwargs:
            raise RuntimeError(f"unknown keyword(s) {kwargs!r}")

        parml = [host_file]
        if host_type == vm:
            parml.append("(")

        if mode == ascii:
            parml.append("ASCII")
            if opt_cr != keep:
                parml.append("CRLF")

        assist = (mode == ascii and remap == yes)

        if dir == send and exist == append:
            parml.append("APPEND")

        if recfm is not None and (mode != vm or dir == send):
            recfm = recfm.name[0].upper()
            if host_type == vm:
                parml.append(f"RECFM {recfm}")
            else:
                parml.append(f"RECFM({recfm})")

        if lrecl is not None and (mode != vm or dir == send):
            if host_type == vm:
                parml.append(f"LRECL {lrecl}")
            else:
                parml.append(f"LRECL({lrecl})")

        if blksize is not None and mode == tso:
            parml.append(f"BLKSIZE({blksize})")

        if host_type == tso and dir == send:
            if (allocation is not None or
                    p_space is not None or
                    s_space is not None):
                if allocation == avblock:
                    quantity = f"AVBLOCK({avblock}"
                elif allocation is None:
                    quantity = ""
                else:
                    quantity = allocation.name.upper()

                if p_space is None:
                    increment = ""
                else:
                    increment = f",{p_space}"

                if s_space is not None:
                    if increment:
                        increment = f"{increment},{s_space}"
                    else:
                        increment = f",,{s_space}"

                parml.append(f"SPACE({quantity}{increment})")

        parms = " ".join(parml)

        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        if dir == send:
            rval = tns.put_file(local_file, parms, assist=assist)
        else:
            rval = tns.get_file(parms, local_file, assist=assist)

        return [str(rval)]

    @_x3270
    def Unselect(self):
        raise RuntimeError("Unselect not implemented")

    @_x3270
    def Up(self):
        self.__send(_ati.curup)

    # x3270-script functions
    # See http://x3270.bgp.nu/x3270-script.html

    @_x3270
    def AnsiText(self, *args):
        raise RuntimeError("AnsiText not implemented")

    @_x3270
    def Ascii(self, *args):
        rval = []
        append = rval.append
        ati, _ = self.__set_session()
        maxcol = ati.maxcol
        argc = len(args)
        if argc == 0:
            saddr = 0
            eaddr = 0

        elif argc == 1:
            saddr = 0
            eaddr = int(args[0])
            if eaddr == ati.maxrow * maxcol:
                eaddr = 0

        elif argc == 3:
            row, col, length = args
            saddr = row * maxcol + col
            eaddr = saddr + length
            if eaddr == ati.maxrow * maxcol:
                eaddr = 0

        elif argc == 4:
            row, col, rows, cols = args
            saddr = row * maxcol + col
            erow = row + rows - 1
            ecol = col + cols
            eaddr = erow * maxcol + ecol
            if eaddr == ati.maxrow * maxcol:
                eaddr = 0

        else:
            raise ValueError("bad number of args")

        tns = ati.get_tnz()
        scrstr = tns.scrstr(saddr=saddr, eaddr=eaddr, rstrip=False)
        if argc < 3:
            for pos in range(0, len(scrstr), maxcol):
                append("data: "+ascii(scrstr[pos:pos+maxcol])[1:-1])

        elif argc == 3:
            len1 = maxcol - col
            append("data: "+ascii(scrstr[:len1])[1:-1])
            for pos in range(len1, len(scrstr), maxcol):
                append("data: "+ascii(scrstr[pos:pos+maxcol])[1:-1])

        else:
            len1 = maxcol - col
            append("data: "+ascii(scrstr[:cols])[1:-1])
            for pos in range(len1, len(scrstr), maxcol):
                idx = pos+col
                append("data: "+ascii(scrstr[idx:idx+cols])[1:-1])

        append("ok")
        return rval

    @_x3270
    def AsciiField(self):
        rval = []
        append = rval.append
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        address = tns.curadd
        faddr0, _ = tns.field(address)
        if faddr0 < 0:
            faddr1 = faddr0
        else:
            faddr1, _ = tns.next_field(address)

        append("data: "+ascii(tns.scrstr(faddr0, faddr1)[1:-1]))
        append("ok")
        return rval

    @_x3270
    def Ebcdic(self, *args):
        rval = []
        append = rval.append
        ati, _ = self.__set_session()
        maxcol = ati.maxcol
        argc = len(args)
        if argc == 0:
            spos = 0
            epos = maxcol * ati.maxrow

        elif argc == 1:
            spos = 0
            epos = int(args[0])

        elif argc == 3:
            row, col, length = args
            spos = row * maxcol + col
            epos = spos + length

        elif argc == 4:
            row, col, rows, cols = args
            spos = row * maxcol + col
            erow = row + rows - 1
            ecol = col + cols
            epos = erow * maxcol + ecol

        else:
            raise ValueError("bad number of args")

        tns = ati.get_tnz()
        bstr = tns.plane_dc[spos:epos]
        if argc < 3:
            for pos in range(0, len(bstr), maxcol):
                append("data: "+_b2e(bstr[pos:pos+maxcol]))

        elif argc == 3:
            len1 = maxcol - col
            append("data: "+_b2e(bstr[:len1]))
            for pos in range(len1, len(bstr), maxcol):
                append("data: "+_b2e(bstr[pos:pos+maxcol]))

        else:
            len1 = maxcol - col
            append("data: "+_b2e(bstr[:cols]))
            for pos in range(len1, len(bstr), maxcol):
                idx = pos+col
                append("data: "+_b2e(bstr[idx:idx+cols]))

        append("ok")
        return rval

    @_x3270
    def CloseScript(self, status=None):
        if self.__zti is None:
            self.__zti = _zti.create()

        if self.__zti is None:
            raise RuntimeError("zti unavailble")

        if status is not None:
            ati = self.__ati
            if ati:
                self.__set_display(ati, False)

            print(repr(status))

        self.__zti.cmdloop()

    @_x3270
    def ContinueScript(self, param=None):
        raise RuntimeError("ContinueScript not implemented")

    @_x3270
    def EbcdicField(self):
        rval = []
        append = rval.append
        ati, _ = self.__set_session()
        tns = ati.get_tnz()
        address = tns.curadd
        faddr0, _ = tns.field(address)
        if faddr0 < 0:
            faddr1 = faddr0
        else:
            faddr1, _ = tns.next_field(address)

        append("data: "+_b2e(tns.rcba(tns.plane_dc, faddr0, faddr1)))
        append("ok")
        return rval

    @_x3270
    def Expect(self, text, timeout=None):
        raise RuntimeError("Expect not implemented")

    @_x3270
    def Info(self, message):
        ati, _ = self.__set_session()
        ati.set("SHOWLINE", message)

    @_x3270
    def PauseScript(self):
        if self.__zti is None:
            self.__zti = _zti.create()

        if self.__zti is None:
            raise RuntimeError("zti unavailble")

        self.__zti.onerror()  # need a zti.pause?

    @_x3270
    def Query(self, keyword=None):
        rval = []
        append = rval.append
        ati, _ = self.__set_session()
        tns = ati.get_tnz()

        if keyword is not None:
            keyword = keyword.lower()

        if keyword is None or keyword == "bindpluname":
            append(f"data: BindPluName:")  # ?

        if keyword is None or keyword == "connectionstate":
            if tns.tn3270:
                if tns.tn3270e:
                    state = "tn3270e 3270"
                else:
                    state = "tn3270 3270"
            else:
                state = "NVT"

            append(f"data: ConnectionState: {state}")

        if keyword is None or keyword == "codepage":
            if tns.alt:
                alt = "+"
            else:
                alt = ""

            append(f"data: CodePage: {tns.cp_00}{alt}")

        if keyword is None or keyword == "cursor":
            row, col = divmod(tns.curadd, tns.maxcol)
            append(f"data: Cursor: {row} {col}")

        if keyword is None or keyword == "formatted":
            if tns.field(0) == (-1, 0):
                append(f"data: Formatted: unformatted")
            else:
                append(f"data: Formatted: formatted")

        if keyword is None or keyword == "host":
            pnaddr, pnport = tns.getpeername()
            append(f"data: Host: host {pnaddr} {pnport}")

        if keyword is None or keyword == "localencoding":
            append(f"data: LocalEncoding: UTF-8")  # ?

        if keyword is None or keyword == "luname":
            lu_name = tns.lu_name
            if not lu_name:
                lu_name = ""

            append(f"data: LuName: {lu_name}")

        if keyword is None or keyword == "model":
            append(f"data: Model: {tns.terminal_type}")

        if keyword is None or keyword == "screencursize":
            append(f"data: ScreenCurSize: {tns.maxrow} {tns.maxcol}")

        if keyword is None or keyword == "screenmaxsize":
            append(f"data: ScreenMaxSize: {tns.amaxrow} {tns.amaxcol}")

        if keyword is None or keyword == "ssl":
            if tns.secure:
                if tns.host_verified:
                    ssl = "secure host-verified"
                else:
                    ssl = "secure host-unverified"
            else:
                ssl = "not-secure"

            append(f"data: Ssl: {ssl}")

        if not rval:
            raise ValueError("Query: Unknown paramaeter")

        if keyword is not None:
            rval[0] = _rexx.delword(rval[0], 2, 1)  # remove label

        append("ok")
        return rval

    @_x3270
    def ReadBuffer(self, *args):
        raise RuntimeError("ReadBuffer not implemented")

    @_x3270
    def Snap(self, *args):
        raise RuntimeError("Snap not implemented")

    @_x3270
    def Source(self, file):
        raise RuntimeError("Source not implemented")

    @_x3270
    def Title(self, text):
        raise RuntimeError("Title not implemented")

    @_x3270
    def Wait(self, *args):
        argc = len(args)
        if argc == 1:
            timeout = None
            wait = args[0]

        elif argc == 2:
            timeout, wait = args

        else:
            raise ValueError(f"Bad Wait arg count {argc}")

        ati = self.__ati
        if not ati:
            ati = _ati.ati

        if wait == WaitCode.Tn3270:  # 3270Mode
            condition = self.__check_3270mode

        elif wait == "3270Mode":
            condition = self.__check_3270mode

        elif wait == 3270:
            condition = self.__check_3270mode

        elif wait == Disconnect:
            condition = self.__check_disconnect

        elif wait == self.Disconnect:
            condition = self.__check_disconnect

        elif wait == Emulator.Disconnect:
            condition = self.__check_disconnect

        elif wait == InputField:
            condition = self.__field_ready

        elif wait == NVTMode:
            condition = self.__check_nvtmode

        elif wait == Output:
            ati, _ = self.__set_session()
            tns = ati.get_tnz()
            rval = tns.wait(timeout, zti=self.__zti)
            if not rval:  # timeout?
                return

            ati, ati_rc = self.__set_session(force=True)
            if ati_rc != 1:
                raise RuntimeError(f"Lost session {ati.seslost}")

            return

        elif wait == Unlock:
            condition = self.__unlocked

        elif wait == Seconds:
            ati.wait(timeout)
            return

        else:
            raise ValueError(f"Bad wait {wait!r}")

        if timeout is None:
            ati_rc = ati.wait(condition)
        else:
            ati_rc = ati.wait(timeout, condition)

        if ati_rc != 1:
            if ati_rc != 12 or wait != Disconnect:
                raise RuntimeError(f"wait error {ati_rc}")

        if wait != Disconnect:
            if ati.seslost:
                raise RuntimeError(f"Lost session {ati.seslost}")

    @_x3270
    def WindowState(self, mode):
        raise RuntimeError("WindowState not implemented")

    # dunder methods

    def __init__(self, visible=False, timeout=30,
                 ati=None, args=None, name=None):
        """Create an emulator instance.

        `visible` controls the visibility of the emulator
        `timeout` controls the default timeout for Wait commands
        `args` allows use of s/x3270 arguments

        `ati` can be used to specify a `Tnz.ati` instance
        `name` can be used to specify the session name in `ati
        """
        if name is _SESSION:
            ati = None
            name = None

        else:
            if not ati:
                ati = _ati.ati

            if not name:
                Emulator.__cnt += 1
                name = "~"+str(Emulator.__cnt)

        self.timeout = timeout

        self.__visible = visible
        self.__ati = ati
        self.__name = name
        self.__host = None
        self.__port = None
        self.__secure = None
        self.__connected = False
        self.__zti = None
        self.__insert = False

        # x3270 toggles

        self.aidWait = True
        self.altCursor = False
        self.blankFill = False
        self.crosshair = False
        self.lineWrap = False
        self.marginedPaste = False
        self.monoCase = False
        self.overlayPaste = False
        self.screenTrace = False
        self.showTiming = False
        self.trace = False
        self.underscore = False
        self.visibleControl = False

        self.locals = {
            # methods
            "Ascii": self.Ascii,
            "AsciiField": self.AsciiField,
            "Connect": self.Connect,
            "CloseScript": self.CloseScript,
            "ContinueScript": self.ContinueScript,
            "Disconnect": self.Disconnect,
            "Ebcdic": self.Ebcdic,
            "EbcdicField": self.EbcdicField,
            "Info": self.Info,
            "Expect": self.Expect,
            "MoveCursor": self.MoveCursor,
            "PauseScript": self.PauseScript,
            "PrintText": self.PrintText,
            "Query": self.Query,
            "ReadBuffer": self.ReadBuffer,
            "Script": self.Script,
            "Snap": self.Snap,
            "Source": self.Source,
            "Title": self.Title,
            "Toggle": self.Toggle,
            "Transfer": self.Transfer,
            "Wait": self.Wait,
            "WindowState": self.WindowState,
            # constants
            "InputField": InputField,
            "NVTMode": NVTMode,
            "Output": Output,
            "Seconds": Seconds,
            "Unlock": Unlock,
            "send": send,
            "receive": receive,
            "tso": tso,
            "vm": vm,
            "cics": cics,
            "binary": binary,
            "add": add,
            "keep": keep,
            "replace": replace,
            "append": append,
            "fixed": fixed,
            "variable": variable,
            "undefined": undefined,
            "tracks": tracks,
            "cylinders": cylinders,
            "avblock": avblock,
            "yes": yes,
            "no": no,
            "remove": remove,
        }

        if visible:
            self.__zti = _zti.create()

        if args:
            if "-trace" in args:
                ati.set("TRACE", "ALL")

            idx = args.index("-tracefile")
            if idx >= 0:
                ati.set("LOGDEST", args[idx+1])

    # [public] methods

    def connect(self, host, port=None, secure=None):
        self.terminate()
        ati = self.__ati
        if ati:
            savename = True

        else:
            savename = False
            ati = _ati.ati

        prefix = ""
        luname = None
        hport = None
        hsecure = None
        verifycert = None
        parts = host.split("@", 1)
        if len(parts) > 1:
            luname, hostname = parts
            parts = luname.split(":", 1)
            if len(parts) > 1:
                prefix, luname = parts

            parts = hostname.split(":", 1)
            if len(parts) > 1:
                hostname, hport = parts
                hport = int(hport)

        else:
            parts = host.split(":")
            len_parts = len(parts)
            if len_parts == 1:
                hostname = parts[0]

            elif parts[-1].isdecimal():
                hport = int(parts[-1])
                hostname = parts[-2]
                if len_parts > 2:
                    prefix = "".join(parts[:-2])
            else:
                hostname = parts[-1]
                prefix = "".join(parts[:-1])

        if "L" in prefix:
            hsecure = True
            verifycert = True

        if "Y" in prefix:
            verifycert = False

        if port is None:
            port = hport

        if secure is None:
            secure = hsecure

        session_host = ati["SESSION_HOST"]
        if session_host != hostname:
            ati.set("SESSION_HOST", hostname)

        session_port = ati["SESSION_PORT"]
        if session_port != port:
            if port is not None:
                ati.set("SESSION_PORT", port)
            else:
                ati.drop("SESSION_PORT")

        session_ssl = ati["SESSION_SSL"]
        if session_ssl != secure:
            if secure is not None:
                ati.set("SESSION_SSL", secure)
            else:
                ati.drop("SESSION_SSL")

        if not ati.onerror:
            ati.set("ONERROR", "1")

        name = self.__name
        if savename:
            self.__set_display(ati, self.__visible)

        else:
            seslost = ati.seslost
            if seslost:
                name = seslost

        if not name:
            Emulator.__cnt += 1
            name = "~"+str(Emulator.__cnt)

        ati_rc = ati.set("SESSION", name, verifycert=verifycert)
        if ati_rc != 0:
            raise RuntimeError(f"set session error {ati_rc}")

        if savename:
            self.__name = ati.session  # upper, word#1

        self.__host = hostname
        self.__port = port
        self.__secure = secure
        self.__connected = True

    def delete_field(self):
        self.__send("[tab][backtab][eraseeof]")

    def exec_command(self, cmdstr):
        if isinstance(cmdstr, bytes):
            cmdstr = cmdstr.decode("ascii")

        cmd = Command(self, cmdstr)
        cmd.execute()
        return cmd

    def fill_field(self, ypos, xpos, tosend, _=None):
        self.move_to(ypos, xpos)
        self.delete_field()
        self.__send(tosend)

    def is_connected(self):
        ati = self.__ati
        if not ati:
            ati = _ati.ati
            if ati.seslost:
                return False

            if not ati.sessions:
                return False

            session = ati.session
            ati_rc = ati.set("SESSION", session)
            return ati_rc == 1

        if self.__connected:
            self.__set_session(force=True)

        return self.__connected

    def move_to(self, ypos, xpos):
        self.__send((ypos, xpos), "")

    def reconnect(self):
        host = self.__host
        port = self.__port
        secure = self.__secure
        self.terminate()
        self.connect(host, port, secure)

    def save_screen(self, file_path):
        raise RuntimeError("save_screen not implemented")

    def send_string(self, tosend, ypos=None, xpos=None):
        tosend = self.__encode(tosend)
        if ypos is not None and xpos is not None:
            self.__send((ypos, xpos), tosend)
        else:
            self.__send(tosend)

    def send_enter(self):
        self.__send(_ati.enter)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_clear(self):
        self.__send(_ati.clear)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf3(self):
        self.__send(_ati.pf3)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf4(self):
        self.__send(_ati.pf4)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf5(self):
        self.__send(_ati.pf5)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf6(self):
        self.__send(_ati.pf6)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf7(self):
        self.__send(_ati.pf7)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf8(self):
        self.__send(_ati.pf8)
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def send_pf(self, value):
        self.__send("[pf"+str(value)+"]")
        if self.aidWait:
            self.Wait(self.timeout, Unlock)

    def status_str(self):
        return self.__status_str()

    def string_found(self, ypos, xpos, string):
        length = len(string)
        ati, _ = self.__set_session()
        return ati.scrhas(string, (ypos, xpos), length)

    def string_get(self, ypos, xpos, length):
        ati, _ = self.__set_session()
        return ati.extract(length, (ypos, xpos))

    def terminate(self):
        ati = self.__ati
        if not ati:
            ati = _ati.ati
            if ati.seslost:
                return

            if ati.sessions:
                ati.drop("SESSION")

            return

        if self.__connected:
            self.__connected = False
            session = self.__name
            if ati.seslost == session:
                return

            self.__set_display(ati, False)
            if ati.session == session:
                ati_rc = 0
            else:
                ati_rc = ati.set("SESSION", session)

            if ati_rc <= 1:
                ati.drop("SESSION")

    def wait_for_field(self):
        self.Wait(self.timeout, InputField)

    # private methods - including
    # x3270-script support functions

    def __check_3270mode(self):
        ati, ati_rc = self.__set_session(force=True)
        if ati_rc != 1:
            return True  # stop waiting - lost session

        tns = ati.get_tnz()
        if not tns.tn3270:
            return False

        return tns.field(0) != (-1, 0)

    def __check_disconnect(self):
        return self.__set_session(force=True) != 1

    def __check_nvtmode(self):
        ati, ati_rc = self.__set_session(force=True)
        if ati_rc != 1:
            return True  # stop waiting - lost session

        tns = ati.get_tnz()
        if tns.tn3270:
            return False

        # TODO wait for a character
        return True

    def __field_ready(self):
        ati, ati_rc = self.__set_session(force=True)
        if ati_rc != 1:
            return True  # stop waiting - lost session

        if ati.value("KEYLOCK") != "0":
            return False

        tns = ati.get_tnz()
        if tns.field(0) == (-1, 0):  # no fields
            return False

        return not tns.is_protected(tns.curadd)

    def __send(self, *args):
        ati, _ = self.__set_session()
        ati_rc = ati.send(*args)
        if ati_rc != 0:
            if ati_rc > 4:
                self.__connected = False

            raise RuntimeError(f"send error {ati_rc}")

    def __set_session(self, force=False):
        ati = self.__ati
        if not ati:
            ati = _ati.ati
            if ati.seslost:
                if force:
                    return ati, 12

                raise RuntimeError(f"Lost session {ati.seslost}")

            if not ati.sessions:
                if force:
                    return ati, 12

                raise RuntimeError("No sessions")

            if not force:
                return ati, 1

            session = ati.session
            ati_rc = ati.set("SESSION", session)
            return ati, ati_rc

        if not self.__connected:
            if force:
                return ati, 12

            raise RuntimeError("Not connected")

        session = self.__name
        if ati.session == session and not force:
            return ati, 1

        visible = self.__visible
        if not visible:
            self.__set_display(ati, False)

        ati_rc = ati.set("SESSION", session)
        if ati_rc == 1:
            self.__set_display(ati, visible)

        else:
            self.__connected = False
            self.__set_display(ati, False)
            if ati_rc == 0:
                ati.drop("SESSION")

            if not force:
                raise RuntimeError(f"Set session error {ati_rc}")

        return ati, ati_rc

    def __status_str(self):
        sks = "L"  # keyboard state
        ssf = "U"  # screen formatting
        sfp = "U"  # field protection
        scs = "N"  # connection state
        sem = "N"  # emulator mode
        smn = "?"  # model number
        smr = "24"  # number of rows
        smc = "80"  # number of columns
        scr = "0"  # cursor row
        scc = "0"  # cursor column
        swi = "0x00"  # windows id
        set = "-"  # execution time

        connected = True
        ati = self.__ati
        if not ati:
            ati = _ati.ati
            if ati.seslost or not ati.sessions:
                connected = False
        else:
            try:
                ati, _ = self.__set_session()
            except Exception:
                connected = False

        if connected:
            keylock = ati.keylock
            maxrow = ati.maxrow
            maxcol = ati.maxcol
            currow = ati.currow
            curcol = ati.curcol

            # TODO need more than KEYLOCK
            # to distinguish between
            # keyboard locked for error
            # and keyboard locked for host
            if keylock == "0":
                sks = "U"  # keyboard unlocked
            elif keylock == "1":
                sks = "L"  # keyboard locked for host
            else:
                sks = "E"  # keyboard locked for error

            ssf = "F"  # formatted screen
            scs = f"C({self.__host})"
            sem = "I"  # 3270 mode
            smr = str(maxrow)
            smc = str(maxcol)
            scr = str(currow-1)
            scc = str(curcol-1)

        result = " ".join([sks, ssf, sfp, scs, sem, smn,
                           smr, smc, scr, scc, swi, set])
        return result

    def __unlocked(self):
        ati, ati_rc = self.__set_session(force=True)
        if ati_rc != 1:
            return True  # stop waiting - lost session

        return ati.value("KEYLOCK") == "0"

    # private static methods

    @staticmethod
    def __encode(string):
        string = string.replace("[", "[[")
        string = string.replace("\\b", _ati.curleft)
        string = string.replace("\\f", _ati.clear)
        string = string.replace("\\n", _ati.enter)
        string = string.replace("\\r", _ati.newline)
        string = string.replace("\\t", _ati.tab)
        return string

    # private class methods

    @classmethod
    def __set_display(cls, ati, visible):
        if visible:
            display = "HOST"
        else:
            display = "NONE"

        if ati.display != display:
            ati.set("DISPLAY", display)

    # private class data

    __cnt = 0


class WaitCode(Enum):
    """Use for Emulator.Wait"""
    Tn3270 = 1  # 3270Mode
    Disconnect = 2
    InputField = 3
    NVTMode = 4
    Output = 5
    Unlock = 6
    Seconds = 7


class Transfer(Enum):
    """Use for Emulator.Transfer"""
    send = 1
    receive = 2
    tso = 3
    vm = 4
    cics = 5
    binary = 6
    add = 7
    keep = 8
    replace = 9
    append = 10
    fixed = 11
    variable = 12
    undefined = 13
    tracks = 14
    cylinders = 15
    avblock = 16
    yes = 17
    no = 18
    remove = 19


InputField = WaitCode.InputField
NVTMode = WaitCode.NVTMode
Output = WaitCode.Output
Unlock = WaitCode.Unlock
Seconds = WaitCode.Seconds

send = Transfer.send
receive = Transfer.receive
tso = Transfer.tso
vm = Transfer.vm
cics = Transfer.cics
binary = Transfer.binary
add = Transfer.add
keep = Transfer.keep
replace = Transfer.replace
append = Transfer.append
fixed = Transfer.fixed
variable = Transfer.variable
undefined = Transfer.undefined
tracks = Transfer.tracks
cylinders = Transfer.cylinders
avblock = Transfer.avblock
yes = Transfer.yes
no = Transfer.no
remove = Transfer.remove


def _b2e(bstr):
    hstr = bstr.hex()
    hlst = []
    for i in range(0, len(hstr), 2):
        hlst.append(hstr[i:i+2])

    return " ".join(hlst)


_SESSION = {}  # current session
_emulator = Emulator(name=_SESSION)

# Script commands

AnsiText = _emulator.AnsiText
Ascii = _emulator.Ascii
AsciiField = _emulator.AsciiField
Connect = _emulator.Connect
CloseScript = _emulator.CloseScript
ContinueScript = _emulator.ContinueScript
Disconnect = _emulator.Disconnect
Ebcdic = _emulator.Ebcdic
EbcdicField = _emulator.EbcdicField
Info = _emulator.Info
Enter = _emulator.Enter
Expect = _emulator.Expect
Keymap = _emulator.Keymap
MoveCursor = _emulator.MoveCursor
PauseScript = _emulator.PauseScript
PrintText = _emulator.PrintText
Query = _emulator.Query
ReadBuffer = _emulator.ReadBuffer
Script = _emulator.Script
Snap = _emulator.Snap
Source = _emulator.Source
String = _emulator.String
Title = _emulator.Title
Transfer = _emulator.Transfer
Wait = _emulator.Wait

# Actions

# Abort
AltCursor = _emulator.AltCursor
# Ascii1
Attn = _emulator.Attn
BackSpace = _emulator.BackSpace
BackTab = _emulator.BackTab
# Bell
# Capabilities
# Charset = _emulator.Charset ?action or command?
CircumNot = _emulator.CircumNot
Clear = _emulator.Clear
# Close
Compose = _emulator.Compose
# Connect
CursorSelect = _emulator.CursorSelect
Cut = _emulator.Cut
# Default = _emulator.Default
Delete = _emulator.Delete
DeleteField = _emulator.DeleteField
DeleteWord = _emulator.DeleteWord
# Disconnect
Down = _emulator.Down
Dup = _emulator.Dup
Enter = _emulator.Enter
Erase = _emulator.Erase
EraseEOF = _emulator.EraseEOF
EraseInput = _emulator.EraseInput
FieldEnd = _emulator.FieldEnd
FieldMark = _emulator.FieldMark
HandleMenu = _emulator.HandleMenu
HexString = _emulator.HexString
Home = _emulator.Home
Insert = _emulator.Insert
Interrupt = _emulator.Interrupt
Key = _emulator.Key
Keymap = _emulator.Keymap  # ???
KybdSelect = _emulator.KybdSelect
Left = _emulator.Left
Left2 = _emulator.Left2
Macro = _emulator.Macro
MonoCase = _emulator.MonoCase
MoveCursor = _emulator.MoveCursor
MoveCursorSelect = _emulator.MoveCursorSelect
Newline = _emulator.Newline
PA = _emulator.PA
PF = _emulator.PF
PreviousWord = _emulator.PreviousWord
# PasteString = _emulator.PasteString
Printer = _emulator.Printer
PrintText = _emulator.PrintText
PrintWindow = _emulator.PrintWindow
Quit = _emulator.Quit
Reconnect = _emulator.Reconnect
Redraw = _emulator.Redraw
Reset = _emulator.Reset
Right = _emulator.Right
Right2 = _emulator.Right2
Script = _emulator.Script
Scroll = _emulator.Scroll
SelectAll = _emulator.SelectAll
SetFont = _emulator.SetFont
String = _emulator.String
Tab = _emulator.Tab
Toggle = _emulator.Toggle
ToggleInsert = _emulator.ToggleInsert
ToggleReverse = _emulator.ToggleReverse
Transfer = _emulator.Transfer
Unselect = _emulator.Unselect
Up = _emulator.Up
# ignore = _emulator.ignore
# insert_selection = _emulator.insert_selection
# move_select = _emulator.move_select
# select_end = _emulator.select_end
# select_extend = _emulator.select_extend
# select_start = _emulator.select_start
# set_select = _emulator.set_select
# start_extend = _emulator.start_extend
