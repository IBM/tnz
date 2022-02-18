"""Z terminal interface

Like ATI Session Manager.

Command usage:
    zti [-h] [--nolog] [--noztirc | --rcfile rcfile] [host]

    positional arguments:
      host             hostname[:port] to connect/go to

    optional arguments:
      -h, --help       show this help message and exit
      --nolog          Do not set LOGDEST to zti.log
      --noztirc        Do not SOURCE .ztirc in home directory
      --rcfile rcfile  Filename to run using SOURCE

Create a command plugin by creating a "zti.commands" entry
point through setup.py that takes a single argument of a
command line string.

Environment variables used:
    COLORTERM (see _termlib.py)
    ESCDELAY
    SESSION_PS_SIZE (see tnz.py)
    TERM_PROGRAM (see _termlib.py)
    TNZ_COLORS (see tnz.py)
    TNZ_LOGGING (see tnz.py)
    ZTI_AUTOSIZE
    ZTI_SECLEVEL (see tnz.py)
    ZTI_TITLE
    _BPX_TERMPATH (see _termlib.py)

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
import atexit
import cmd
import ctypes
import logging
import os
import platform
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback

from importlib.metadata import entry_points

from . import _sigx as sigx
from ._termlib import Term as curses
from ._util import session_ps_14bit
from . import ati
from . import rexx
from . import tnz
from . import __version__

__author__ = "Neil Johnson"


class Zti(cmd.Cmd):
    """
    The Zti class provides Z terminal interface (3270) function to
    users of an ascii character terminal. For users of ATI, this
    class performs the function of the ATI session manager and error
    handler.
    """

    def __del__(self):
        """Zti destructor
        """
        self.__bg_wait_end()
        # do not switch to shell mode here
        # doing so may log and logging may encounter errors
        # if this is being done during shutdown

    def __init__(self, stdin=None, stdout=None):
        """A Zti instance is a line-oriented and full-screen ascii
        chraracter terminal interface to 3270 telnet sessions.

        Tab is used for the readline completion key.

        The optional arguments stdin and stdout specify the input and
        output file objects that the Cmd instance or subclass
        instance will use for input and output. If not specified,
        they will default to sys.stdin and sys.stdout
        """
        super().__init__(stdin=stdin, stdout=stdout)

        if stdin:
            self.use_rawinput = False
            self.__stdin = stdin
        else:
            self.__stdin = sys.stdin

        if stdout:
            self.__stdout = stdout
        else:
            self.__stdout = sys.stdout

        self.autosize = False
        if os.getenv("ZTI_AUTOSIZE"):
            self.autosize = True

        self.pend_intro = None
        self.__dirty_ranges = []
        self.single_session = False
        self.colors = 768
        self.cv2attr = {}
        self.stdscr = self._stdscr
        self.rewrite = True
        self.rewrite_cursor = True
        self.rewrite_keylock = True
        self.rewrite_status = True
        self.twin_beg = None
        self.twin_loc = None
        self.twin_end = None
        self.__lock = threading.Lock()
        self.__bg = False
        self.__thread = None
        self.__tty_mode = 0  # 0=shell, 1=prog
        self.__has_color = None

        self.__prog_curs_vis = 0  # cursor invisible in prog mode
        self.__cur_curs_vis = 1  # current cursor state
        self.__shell_mousemask = None

        self.ddmrecv = False  # allow host-initiated ind$file get
        self.ddmsend = False  # allow host-initiated ind$file put
        self.__plugin_kwargs = {}
        self.__plugin_goto = ""
        self.__tb_count = 0
        self.__in_wait = False
        self.__in_script = False
        self.__wait_rc = None
        self.__tracing = False

        self.registered_atexit = False
        self.downloads = []
        self.__downcnt = 0
        self.downloadaction = False

        self.__sessel_y = None
        self.__sessel_x = 0
        self.__sessel = []

        self.__stdin_selected = False
        if _osname == "Windows":
            self.__stdin_selectr = None
            self.__sigwinch_selected = False
        else:
            self.__stdin_selectr = self.__stdin
            self.__sigwinch_selected = True

        if self._zti is None:
            Zti._zti = self

        plugins = []
        zti_plugins = entry_points().get("zti.commands", [])
        for entry in zti_plugins:
            name = entry.name
            plugins.append(name)

            def do_plugin(arg, entry=entry, **kwargs):
                plugin = entry.load()
                self.__bg_wait_end()
                tb_count = self.__tb_count
                plugin_goto = self.__plugin_goto
                self.__plugin_goto = ""
                kwargs.update(**self.__plugin_kwargs)
                self.__plugin_kwargs.clear()
                try:
                    try:
                        self.__tb_count = len(traceback.extract_stack())
                    except Exception:
                        pass

                    with ati.ati.new_program(share_sessions=True):
                        plugin(arg, **kwargs)

                except _ZtiAbort:
                    pass

                except Exception:
                    ati.say(f"{name} failed")
                    self.print_stack(exc=True)

                else:
                    if plugin_goto:
                        self.cmdqueue.append(f"GOTO {plugin_goto}\n")

                finally:
                    self.__tb_count = tb_count

                sessions = ati.ati.sessions.split()
                if sessions:
                    if ati.ati.session not in sessions:
                        ati.ati.session = sessions[0]

            def help_plugin(entry=entry):
                plugin = entry.load()
                self.__shell_mode()
                plugin("--help")

            setattr(self, f"do_{name}", do_plugin)
            setattr(self, f"help_{name}", help_plugin)

        self.plugins = " ".join(plugins)

    # Methods

    def atexit(self):
        while self.downloads:
            download = self.downloads.pop()
            download.remove()

    def cmdloop(self, intro=None):
        """Override cmd.Cmd.cmdloop to handle KeyboardInterrupt.
        """
        self.__shell_mode()
        if self.cmdqueue:
            if intro is None:
                intro = self.intro
                if intro is None:
                    intro = self.pend_intro

            if intro is not None:
                self.pend_intro = intro
                intro = ""

        while True:
            try:
                text = intro
                intro = ""
                super().cmdloop(intro=text)
                return

            except KeyboardInterrupt:
                self.__shell_mode()
                print("\nKeyboardInterrupt")

            except BaseException:
                self.postloop()
                raise

    def complete_goto(self, text, line, begidx, endidx):
        textu = text.upper()
        textl = len(text)
        line_lower = line.islower()
        line_upper = line.isupper()
        slist = ati.ati.sessions.split()
        completions = []
        for session in slist:
            if session.startswith(textu):
                if line_lower:
                    completion = text + session[textl:].lower()
                elif line_upper:
                    completion = text + session[textl:].upper()
                else:
                    completion = text + session[textl:]

                completions.append(completion)

        return completions

    def complete_say(self, text, line, begidx, endidx):
        textu = text.upper()
        textl = len(text)
        line_lower = line.islower()
        line_upper = line.isupper()
        klist = ati.ati.keys()
        completions = []
        for akey in klist:
            if akey.startswith(textu):
                if line_lower:
                    completion = text + akey[textl:].lower()
                elif line_upper:
                    completion = text + akey[textl:].upper()
                else:
                    completion = text + akey[textl:]

                completions.append(completion)

        return completions

    def default(self, line):
        """Override cmd.Cmd.default
        """
        value = ati.value(line)
        print("         >>> "+repr(value))

    def do_EOF(self, arg):
        # Not intended to be used as a command. Performs action when
        # /dev/null is redirected to standard input and when Ctrl+D
        # is pressed. This is intentionally not a docstring so that
        # EOF will not appear as a 'documented command'.

        return True  # see postcmd

    def do_abort(self, arg):
        """Abort the running program.

        This is modelled after the ATI Abort error recovery
        selection. ABORT aborts the error handler. ATI exits
        immediately with a return code of 127. Note that
        ATI would have returned 999.
        """
        if not self.__in_script:
            print("Not in a program. Use EXIT to exit.")
            return

        raise _ZtiAbort(127)

    def do_autosize(self, arg):
        # ready for testing?
        if getattr(curses, "prog_maxyx", curses) is curses:
            print(">>> AUTOSIZE not available.")
            return

        autosize = not self.autosize
        self.autosize = autosize
        if not autosize:
            curses.prog_maxyx = None

        print(f"autosize = {self.autosize}")

    def do_disc(self, arg):
        # The intent would be to model this after the ATI DISC
        # interactive trace command. DISC disconnects the parent ID,
        # leaving ATI running disconnected, and leaving the session
        # logged on and connected to the parent. This is
        # intentionally not a docstring so that DISC will not appear
        # as a 'documented command'.

        print(">>> DISC command not supported.")

    def do_discard(self, arg):
        """Discard a downloaded file.

            Usage:
                discard
                discard all
                discard number

        With no parameters, the oldest download is discarded.
        When 'all' is specified, all downloads are discarded.
        When a number is specified, the indexed download is discarded.
        """
        if len(self.downloads) <= 0:
            print(">>> No downloads to discard")

        self.__bg_wait_end()  # needed

        if arg.lower() == "all":
            while self.downloads:
                download = self.downloads.pop()
                download.remove()
        else:
            if not arg:
                arg = "0"

            try:
                i = int(arg)
            except ValueError:
                print(">>> No download "+repr(arg))
                return

            try:
                download = self.downloads.pop(i)
            except IndexError:
                print(">>> No download "+repr(i))
                return

            download.remove()

    def do_display(self, arg):
        # Debug display for current session.
        # This is intentionally not a docstring so that DISPLAY will not
        # appear as a 'documented command'.
        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if tns:
            print(tns.scrstr())

    def do_downloads(self, arg):
        """List downloads.
        """
        self.__bg_wait_end()
        self.__downcnt = len(self.downloads)
        for i in range(0, self.__downcnt):
            download = self.downloads[i]
            print(str(i)+" "+repr(download))
            os.environ["d"+str(i)] = download.file.name

    def do_drop(self, arg):
        """Drop and ATI-like variable.

           Usage:
               drop NAME

        This is modelled after the DROP function of the ATI GOTO EXEC
        that is often used with the ATI Session Manager. DROP
        disconnects a session.

        This is also modelled after the ATI DROP statement.
        """
        self.__bg_wait_end()
        if self.single_session and "SESSION" in arg.upper().split():
            self.single_session = False

        ati.drop(arg)

    def do_exit(self, arg):
        """Exit to the system.

        This is modelled after the ATI EXIT command/statement. EXIT
        causes ATI processing to be halted.

        1 - EXIT causes control (and any return code) to be passed to
            the next ATI program specified on the execution line. If
            no other programs follow, the return code is returned to
            the caller of ATI.
        2 - If an included programs exits, control is not returned to
            the calling program, but to the next program listed on
            the execution line.
        3 - Task file execution terminates when either an EXIT is
            encountered or after the last statement in the file is
            executed
        4 - A return code is optional; if not specified, it defaults
            to 0.
        """
        return True  # see postcmd

    def do_fields(self, arg):
        # Debug fields for current session.
        # This is intentionally not a docstring so that FIELDS will not
        # appear as a 'documented command'.

        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if not tns:
            return

        saddr = 0
        eaddr = 0
        first = True
        for faddr, _ in tns.fields():
            if first:
                first = False
                eaddr = faddr
            else:
                text = tns.scrstr(saddr, faddr)
                print(repr((saddr, faddr)), repr(text))

            saddr = faddr

        text = tns.scrstr(saddr, eaddr)
        print(repr((saddr, eaddr)), repr(text))

    def do_goto(self, arg):
        """Command to go to a session in full-screen.

        This is modelled after the ATI GOTO interactive trace
        command. GOTO suspends execution and transfers control to the
        indicated session. If no session is supplied, the active
        session is used. If the selected session does not exist, a
        warning is issued. ATI execution resumes upon returning
        (through use of hot-key, disconnection, logoff, etc.). GOTO
        ? will show all sessions under the parent ID.

        This is also modelled after the ATI GOTO EXEC that is often
        used with the ATI Session Manager:

        <TODO need syntax diagram>

        session
            The name of a session to which control is transferred.

        userid
            A user ID on the same node as the current node. The
            session name is simply userid.

        userid AT node
            Information by which the session name is hashed. The
            session name is made by concatenating the last five
            characters of userid, an = sign, and the sixth and
            seventh characters of node. For example, MICHAELG AT
            STLVM3 becomes HAELG=3, and RONB AT STLVM1 becomes
            RONB=1.

        nickname
            A nickname from a NAMES file on the A-disk where a user
            ID and node are stored that specify the session to which
            control is to be transferred.

        ?
            Lists the available current session names.

        DROP
            Disconnects a session. See DROP command.

        INIT
            Initiated a session (brings up a new one).

        QUIET
            Suppresses informational messages.

        RENAME
            Changes the name of the current session to the session
            name specified. See RENAME command.

        This is NOT modelled after the ATI GOTO statement.
        """
        self.__bg_wait_end()

        self.__downcnt = len(self.downloads)
        sessions = ati.ati.sessions
        session = ati.ati.session

        oldsize = ati.ati["SESSION_PS_SIZE"]
        newsize = oldsize

        if arg == "" and sessions == "":

            ati.ati.session = "A"
            session = "A"

        elif arg == "":

            ati.ati.session = session

        elif arg == "?":

            print(sessions)
            return

        elif rexx.words(arg) == 1:

            port = None
            hostname = arg
            sesname = arg

            if ":" in arg:
                parts = arg.split(":", 1)
                hostname = parts[0]
                sesname = parts[0]
                port = parts[1]

            if "." not in hostname:
                fqdn = socket.getfqdn()
                fqdn = fqdn.split(".")
                if len(fqdn) > 1:
                    hostname += "."+".".join(fqdn[1:])

            if "." in hostname:
                parts = hostname.split(".", 1)
                sesname = parts[0]

            if sesname != arg:
                basename = sesname
                sesname = sesname.upper()
                i = 1
                while " "+sesname+" " in " "+sessions+" ":
                    sesname = basename+"~"+str(i)
                    i += 1

            if port is not None:
                oldport = ati.ati["SESSION_PORT"]
                if oldport != port:
                    ati.set("SESSION_PORT", port)

            session_host = ati.ati["SESSION_HOST"]
            if session_host is None or sesname != arg:
                ati.set("SESSION_HOST", hostname)

            if not oldsize:
                if os.environ.get("SESSION_PS_SIZE", "") == "MAX":
                    (columns, lines) = os.get_terminal_size()
                    lines -= 4
                    columns = min(columns - 17, 160)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "MAX255":
                    (columns, lines) = os.get_terminal_size()
                    lines -= 4
                    columns = max(columns - 17, 255)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "FULL":
                    (columns, lines) = os.get_terminal_size()
                    columns = min(columns, 160)  # 160 for ispf
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "FULL255":
                    (columns, lines) = os.get_terminal_size()
                    columns = min(columns, 255)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)

            ati.ati.session = sesname
            if self.single_session and ati.ati.rc == 0:
                if ati.ati.session != ati.ati.sessions:
                    self.single_session = False

            if session_host is None:
                ati.drop("SESSION_HOST")
            elif sesname != arg:
                ati.set("SESSION_HOST", session_host)

            if port is not None:
                if oldport != port:
                    if oldport is None:
                        ati.drop("SESSION_PORT")
                    else:
                        ati.set("SESSION_PORT", oldport)
        else:

            port = None
            hostname = rexx.subword(arg, 2)
            sesname = rexx.word(arg, 1)

            if ":" in hostname:
                parts = hostname.split(":", 1)
                hostname = parts[0]
                port = parts[1]

            if "." not in hostname:
                fqdn = socket.getfqdn()
                fqdn = fqdn.split(".")
                if len(fqdn) > 1:
                    hostname += "."+".".join(fqdn[1:])

            if port is not None:
                oldport = ati.ati["SESSION_PORT"]
                if oldport != port:
                    ati.set("SESSION_PORT", port)

            oldhost = ati.ati["SESSION_HOST"]
            if oldhost != hostname:
                ati.set("SESSION_HOST", hostname)

            if not oldsize:
                if os.environ.get("SESSION_PS_SIZE", "") == "MAX":
                    (columns, lines) = os.get_terminal_size()
                    lines -= 4
                    columns = min(columns - 17, 160)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "MAX255":
                    (columns, lines) = os.get_terminal_size()
                    lines -= 4
                    columns = max(columns - 17, 255)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "FULL":
                    (columns, lines) = os.get_terminal_size()
                    columns = min(columns, 160)  # 160 for ispf
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)
                elif os.environ.get("SESSION_PS_SIZE", "") == "FULL255":
                    (columns, lines) = os.get_terminal_size()
                    columns = min(columns, 255)
                    lines, columns = session_ps_14bit(lines, columns)
                    newsize = f"{lines}x{columns}"
                    ati.set("SESSION_PS_SIZE", newsize)

            ati.ati.session = sesname
            if self.single_session and ati.ati.rc == 0:
                if ati.ati.session != ati.ati.sessions:
                    self.single_session = False

            if oldhost != hostname:
                if oldhost is None:
                    ati.drop("SESSION_HOST")
                else:
                    ati.set("SESSION_HOST", oldhost)

            if port is not None:
                if oldport != port:
                    if oldport is None:
                        ati.drop("SESSION_PORT")
                    else:
                        ati.set("SESSION_PORT", oldport)

        if oldsize != newsize:
            if oldsize is None:
                ati.drop("SESSION_PS_SIZE")
            else:
                ati.set("SESSION_PS_SIZE", oldsize)

        if ati.ati.seslost:
            self.__session_check()
            return

        if len(self.cmdqueue) > 0:  # if more from SOURCE command
            return

        try:
            self.ddmrecv = True  # allow host-initiated ind$file get
            self.ddmsend = True  # allow host-initiated ind$file put
            self.__prog_mode()
            try:
                r2d2rv = self.__r2d2(self.stdscr, _WAIT_GOTO, -1)

            except tnz.TnzTerminalError:
                self.print_stack(exc=True)
                print("Maybe set SESSION_PS_SIZE?")
                r2d2rv = None

            except tnz.TnzError:
                self.print_stack(exc=True)
                r2d2rv = None

        finally:
            self.ddmrecv = False  # ind$file get unexpected
            self.ddmsend = False  # ind$file put unexpected

        if r2d2rv == 10:  # ddmdata
            self.shell_mode()
            tns = ati.ati.get_tnz()
            ddmdata = tns.ddmdata
            ddmdict = dict(tns.ddmdict)
            tns.ddmdata = None
            tns.ddmdict.clear()
            plugin_name = ddmdict.get("plugin")
            if plugin_name:
                del ddmdict["plugin"]
                self.__plugin_kwargs = ddmdict
                self.cmdqueue.append(f"{plugin_name}\n")
                downi = len(self.downloads) - 1
                self.cmdqueue.append(f"discard {downi}\n")
                self.__plugin_goto = ati.ati.session

            else:
                print(ddmdata)

            return

        if r2d2rv == 11:  # downloadaction
            actiontaken = False
            for download in self.downloads:
                if download.actiontaken:
                    continue

                if download.downloadaction:
                    actiontaken = True
                    download.actiontaken = True
                    self.__shell_mode()
                    cmd = download.downloadaction
                    os.system(cmd)

            if actiontaken:
                self.cmdqueue += ["goto "+ati.ati.session+"\n"]

        self.__session_check()

    def do_ha(self, arg):
        # The intent would be to model this after the ATI HA
        # interactive trace command. HA terminates ATI execution.
        # This is intentionally not a docstring so that HA will not
        # appear as a 'documented command'.

        print(">>> HA command not supported. Consider EXIT.")

    def do_host(self, arg):
        # The intent would be to model this after the ATI HOST
        # interactive trace command. HOST executes a CMS or CP
        # command. The command is passed to CMS for evaluation.
        # This is intentionally not a docstring so that HA will not
        # appear as a 'documented command'. The use of the word
        # HOST is quite overused and has become ambiguous.

        print(">>> HOST command not supported. Consider SHELL.")

    def do_lines(self, arg):
        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if not tns:
            return

        lines = tns.readlines
        if lines is None:
            tns.start_readlines()
            lines = tns.readlines

        tns.readlines = []
        if lines:
            print(*lines, sep="\n")

    def do_receive(self, arg):
        """Received a downloaded file.
        """
        if not arg:
            print(">>> Destination file is a required argument")
            return

        if len(self.downloads) <= 0:
            print(">>> No downloads to receive")

        self.__bg_wait_end()  # needed

        download = self.downloads[0]
        name = download.file.name
        dest = arg

        if rexx.words(arg) > 1:
            if rexx.word(arg, 1).lower() == "ascii":
                dest = rexx.subword(arg, 2)
                with open(name, "r+b") as file:
                    bstr = file.read()
                    if bstr.endswith(b'\x1a'):
                        bstr = bstr[:-1]

                    bstr = bstr.replace(b'\r\n', b'\n')
                    cstr = bstr.decode('iso8859-1')  # ?
                    with open(dest, "w", encoding="utf-8") as file2:
                        file2.write(cstr)
                        dest = None

        if dest:
            import shutil
            try:
                shutil.copyfile(name, dest)

            except Exception:
                self.print_stack(exc=True)

        self.downloads.pop(0)
        download.remove()

    def do_rename(self, arg):
        """Rename the current session.

        This is modelled after the RENAME function of the ATI GOTO
        EXEC that is often used with the ATI Session Manager. RENAME
        changes the name of the current session to the session name
        specified.
        """
        if not arg:
            print("new session name required")
            return

        self.__bg_wait_end()
        ati.rename(arg)

    def do_return(self, arg):
        """Return to the program.

        This is modelled after the ATI Continue Executing error
        recovery selection. RETURN lets the ATI program continue
        executing at the line following the WAIT statement that timed
        out.

        This return to script execution function is also performed by
        ATI when processing an unrecognized command during
        interactive tracing.
        """
        if not self.__in_script:
            print("Not in a program. Use EXIT to exit.")
            return

        return -1  # or True?

    def do_say(self, arg):
        """Print the value of an ATI-like variable.

        This should be modelled after the ATI SAY interactive trace
        command. SAY displays the value of a specified identifier,
        using the following format:

        Variable         identifier = 'xxxxx'
        When label       identifier IS AN ACTIVE WHEN BLOCK PRIORITY=pri
        When label       identifier IS AN INACTIVE WHEN BLOCK
        Statement label  identifier IS A STATEMENT LABEL
        Undefined        identifier IS A NONEXISTENT IDENTIFIER

        This is NOT modelled after the ATI SAY statement.
        """
        if not arg:
            print("variable name required")
            return

        name = rexx.word(arg, 1).upper()
        if name in ("MAXWAIT", "SHOWLINE"):
            print(f"{name} IS WRITE-ONLY")
            return

        self.__bg_wait_end()

        value = ati.ati[arg]
        if value is not None:
            if value is True:
                print(name+" = True")

            elif value is False:
                print(name+" = False")

            elif callable(value):
                if value.active:
                    print(name +
                          " is an active when callback priority=%d" %
                          value.pri[0])
                else:
                    print(name+" is an inactive WHEN callback")
            else:
                value = str(value)
                print(name+" = "+repr(value))

        else:
            print(name+" is a nonexistent identifier")

    def do_session(self, arg):
        """Get information about the current session.
        """
        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if not tns:
            print("NONE")
            return

        pnaddr, pnport = tns.getpeername()
        print(f" SESSION_HOST={pnaddr}")
        print(f" SESSION_PORT={pnport}")

        lu_name = tns.lu_name
        if lu_name:
            print(f" SESSION_LU_NAME={lu_name}")

        print(f" SESSION_CODE_PAGE={tns.codec_info[0].name}")
        print(f" SESSION_PS_SIZE={tns.amaxrow}x{tns.amaxcol}")
        print(f" SESSION_TN_ENHANCED={tns.tn3270e:d}")
        print(f" SESSION_DEVICE_TYPE={tns.terminal_type}")

        if tns.alt:
            print(" Alternate code page IBM-"+str(tns.cp_01))
        else:
            print(" Alternate code page not supported")

        print(" socket type: "+repr(tns.getsockettype()))

        if tns.extended_color_mode():
            print(" Extended color mode")
        else:
            print(" Basic color mode")

    def do_set(self, arg):
        """Set the value of an ATI-like variable.

        This is loosely modelled after the ATI SET statement.
        """
        if not arg:
            print("variable name required")
            return

        self.__bg_wait_end()

        name = rexx.word(arg, 1)
        value = rexx.subword(arg, 2)
        ati.set(name, value)
        if self.single_session:
            sessions = ati.ati.sessions
            if sessions and ati.ati.session != sessions:
                self.single_session = False

    def do_shell(self, arg):
        """Execute a shell/system command.
            Usage:
                shell command
                !command
        """
        os.system(arg)

    def do_show(self, arg):
        """Show the current session.

        This is modelled after the ATI SHOW interactive trace
        command. SHOW displays the screen of the current session
        immediately in the case where DISPLAY is set to HOST or
        HOSTCODE and the host screen is being displayed due to an
        interactive trace command being entered.
        """
        self.__bg_wait_end()
        self.__prog_mode()
        self.__r2d2(self.stdscr, _WAIT_FOREVER, -1)

    def do_size(self, arg):
        # Get/Set terminal size
        # This is intentionally not a docstring so that SIZE will not
        # appear as a 'documented command'. Need to refine this command.

        self.__shell_mode(init=True)
        # curses.update_lines_cols() not in z/OS python3.6
        maxy, maxx = self.stdscr.getmaxyx()

        if arg:
            print(">>> SIZE setting not implemented.")
            return

        print("TTY rows, cols: "+repr(maxy)+", "+repr(maxx))

    def do_skip(self, arg):
        """Skip current wait.

        This is modelled after the ATI SKIP interactive trace
        command. SKIP can be used only when ATI is executing a WAIT
        statement. It is used to force a WAIT expression to be
        satisfied, setting the return code of the WAIT to 1.
        """
        if not self.__in_wait:
            print("Not in a wait")
            return

        self.__wait_rc = -2
        return 0

    def do_source(self, arg):
        """Execute a file of commands.
            Usage:
                source filename
        """
        if not arg:
            print(">>> Source file is a required argument")
            return

        try:
            with open(os.path.expanduser(arg)) as myfile:
                self.cmdqueue += myfile.readlines()

        except FileNotFoundError:
            print(">>> Source file "+repr(arg)+" not found.")

    def do_strs(self, arg):
        # Debug strings for current session.
        # This is intentionally not a docstring so that STRS will not
        # appear as a 'documented command'.

        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if not tns:
            return

        faddr, _ = tns.next_field(0, offset=0)
        if faddr < 0:
            faddr = 0
            sa0 = 0
            ea0 = 0
        else:
            sa0 = (faddr + 1) % tns.buffer_size
            ea0 = sa0

        print("adr1" +
              "-adr2" +
              " eh" +
              " fg" +
              " bg" +
              " field attribute or text")
        for sa1, ea1 in tns.char_addrs(sa0, ea0):
            if faddr < 0:
                faddr = 0
            else:
                faddr = (sa1 - 1) % tns.buffer_size

            fav = tns.plane_fa[faddr]
            feh = tns.plane_eh[faddr]
            ffg = tns.plane_fg[faddr]
            fbg = tns.plane_bg[faddr]
            print(rexx.right(str(faddr), 4) +
                  "-"+rexx.right(str(ea1), 4) +
                  " "+rexx.right(rexx.substr(hex(feh), 3), 2, "0") +
                  " "+rexx.right(rexx.substr(hex(ffg), 3), 2, "0") +
                  " "+rexx.right(rexx.substr(hex(fbg), 3), 2, "0") +
                  " "+rexx.right(rexx.substr(hex(fav), 3), 2, "0") +
                  " ("+tns.fav_repr(fav)+")")
            for sa2, ea2 in tns.group_addrs(sa1, ea1):
                ceh = tns.plane_eh[sa2]
                cfg = tns.plane_fg[sa2]
                cbg = tns.plane_bg[sa2]
                print(rexx.right(str(sa2), 4) +
                      "-"+rexx.right(str(ea2), 4) +
                      " "+rexx.right(rexx.substr(hex(ceh), 3), 2, "0") +
                      " "+rexx.right(rexx.substr(hex(cfg), 3), 2, "0") +
                      " "+rexx.right(rexx.substr(hex(cbg), 3), 2, "0") +
                      " "+repr(tns.scrstr(sa2, ea2).rstrip()))

    def do_timeout(self, arg):
        """Timeout current wait in program.

        This is modelled after the ATI TIMEOUT interactive trace
        command. TIMEOUT can be used only when ATI is executing a
        WAIT statement. It is used to force a WAIT timeout, and it
        sets the return code of the WAIT to 0, meaning that the
        expression was NOT satisfied.
        """
        if not self.__in_wait:
            print("Not in a wait")
            return

        self.__wait_rc = -1
        return 0  # timeout - WAIT expression NOT satisfied

    def do_trace(self, arg):
        """TRACE command

        The intent would be to model this after the ATI TRACE
        interactive trace command. TRACE ON sets the ATI internal
        variable DISPLAY to ALL and begins interactive (single-step)
        tracing mode. TRACE n will cause the next n ATI statements to
        be traced independent of the trace mode).
        """
        ati.ati.trace = arg
        self.__tracing = arg.upper() == "ON"
        if self.__tracing:
            return -1  # or True?

    def do_upload(self, arg):

        self.__bg_wait_end()
        tns = ati.ati.get_tnz()
        if not tns:
            print("No session")
            return

        try:
            file = open(os.path.expanduser(arg), mode="rb")

        except FileNotFoundError:
            print(">>> Upload file "+repr(arg)+" not found.")
            return

        tns.upload(file)
        return self.do_goto("")

    def emptyline(self):
        """Override cmd.Cmd.emptyline. Without the override, Cmd will
        repeat the last command. With this override, an empty line will
        behave more like a typical shell.
        """
        if self.__tracing:
            return -1  # or True?

        return

    def erase(self, _):
        """Erase terminal screen

        Called by tnz.py.
        """
        if self.rewrite:
            return

        _logger.debug("schedule rewrite for erase")
        self.rewrite = True

    def extended_color(self, _):
        """Enter extended color mode
        """
        if self.rewrite:
            return

        _logger.debug("schedule rewrite for extended color")

        self.rewrite = True

    def field(self, tns, addr):
        """Field defined

        Called by tnz.py.
        """
        if self.rewrite:
            return

        buffer_size = tns.buffer_size
        epos = addr + 1  # next position
        addr1 = (epos) % buffer_size  # next address
        self.__write_blanks(tns, addr, addr1)
        self.__clean_range(addr, epos)
        eaddr, _ = tns.next_field(addr)
        if eaddr == addr1:
            return  # no data in field

        if eaddr < 0:
            eaddr = addr  # only field that exists

        self.__dirty_range(addr1, eaddr, tns=tns)

    def help_keys(self):
        """Process the HELP KEYS command.
        """
        print("""KEYS:
 ATTN           - Ctrl+C or Alt+A
 CLEAR          - Ctrl+L or Alt+C
 DROP session   - Ctrl+W
 ENTER          - Enter
 End            - End
 eraseeof       - Ctrl+K or Shift+End
 Escape         - Esc
 Next session   - Alt+PgDn
 Open URL       - Ctrl+O or mouse click
 PA1            - Alt+1 or Alt+Insert
 PA2            - Alt+2 or Alt+Home
 PA3            - Alt+3
 PF1-12         - F1-12
 PF13-24        - Shift+F1-12
 Prev session   - Alt+PgUp
 Word Left      - Alt+Left
 Word Right     - Alt+Right
""")

    def help_vars(self):
        """Process the HELP VARS command.
        """
        print("""Variables used when creating a new session:
 SESSION_CODE_PAGE    - code page, e.g. cp037
 SESSION_LU_NAME      - LU name for TN3270E CONNECT
 SESSION_HOST         - tcp/ip hostname
 SESSION_PORT         - tcp/ip port, default is 992
 SESSION_PS_SIZE      - terminal size, e.g. 62x160
 SESSION_SSL          - set to 0 to not force SSL
 SESSION_TN_ENHANCED  - set to 1 allow TN3270E
 SESSION_DEVICE_TYPE  - device-type, e.g. IBM-DYNAMIC
""")

    def onerror(self):
        """Ati error handler
        """
        self.print_stack()
        intro = """
ERROR RECOVERY FOR WAIT TIMEOUT

    - abort   (exit program with RC=127)
    - goto    (go to session, Esc to return)
    - return  (resume with wait RC=1)
    - timeout (resume with wait RC=0)

This recovery process was initiated because the program used
ONERROR=1. Consider the above commands to recover. The above stack
trace provides context for where the error occurred. Use the HELP and
HELP KEYS commands for more information.
"""
        in_script = self.__in_script
        in_wait = self.__in_wait
        try:
            self.__in_script = True
            self.__in_wait = True
            self.__wait_rc = None
            self.cmdloop(intro)

        finally:
            self.__in_script = in_script
            self.__in_wait = in_wait

        return self.__wait_rc

    def pause(self):
        """Pause script
        """
        self.shell_mode()
        in_script = self.__in_script
        in_wait = self.__in_wait
        try:
            self.__in_script = True
            self.__in_wait = False
            self.cmdloop("")

        finally:
            self.__in_script = in_script
            self.__in_wait = in_wait

    def postcmd(self, stop, line):
        """Override cmd.Cmd.postcmd
        """
        if stop is not False and stop is not None:
            if self.stdscr:
                self.__shell_mode()

            if line == "exit":
                self.postloop()
                raise SystemExit()

            if line == "EOF":
                print("")  # newline

            return True

        if len(self.cmdqueue) <= 0:  # if ready for prompt
            if self.stdscr:
                self.__shell_mode()

            if self.single_session and not ati.ati.sessions:
                self.postloop()
                if ati.ati.seslost:
                    raise SystemExit(10)
                else:
                    raise SystemExit(0)

            if self.pend_intro is not None:
                self.intro = self.pend_intro
                self.pend_intro = None
                self.stdout.write(str(self.intro)+"\n")

            if self.__downcnt < len(self.downloads):
                print("downloads:")
                self.do_downloads("")

            self.__update_prompt()  # according to SESSION
            self.__bg_wait_start()

        return False

    def postloop(self):
        """Override cmd.Cmd.postloop

        Command prompt terminating
        """
        self.__bg_wait_end()

        if self.stdscr:
            self.__shell_mode()

    def precmd(self, line):
        """Override cmd.Cmd.precmd behavior. Make it so that the case
        of the command does not matter by always 'executing' the
        lowercase command name.
        """
        if line == "EOF":  # Ctrl+D pressed or end of input
            return line

        cmd = rexx.word(line, 1)
        return line.replace(cmd, cmd.lower(), 1)

    def preloop(self):
        """Override cmd.Cmd.preloop

        Initialize
        """
        self.__update_prompt()  # according to SESSION
        self.__bg_wait_start()

    def print_stack(self, exc=False):
        self.__shell_mode()
        try:
            current_tb_count = len(traceback.extract_stack())
            limit = current_tb_count - self.__tb_count
            if limit <= 1:
                limit = None

            if exc:
                traceback.print_exc(limit=limit)
            else:
                traceback.print_stack(limit=limit)

        except Exception:
            print("<stack trace unavailable>")

    def shell_mode(self):
        self.__shell_mode()

    def show(self):
        # FIXME - wait (even with timeout=0
        # will get updates from host
        # this methods wants to NOT get
        # updates from host - just display
        # what we currently know
        self.wait(0)

    def showline(self, text):
        """ATI-like function for when SHOWLINE is set.
        """
        if self.twin_beg is None:
            return False

        if not self.stdscr:
            return False

        self.__prog_mode()

        maxy, _ = self.stdscr.getmaxyx()

        xpos1, _ = self.twin_beg
        xpos2, _ = self.twin_end
        xpos3, _ = self.twin_loc

        if len(text) > xpos2-xpos1:
            text = text[:xpos2-xpos1]

        self.__tty_write(maxy-1, xpos3, text, 0)
        self.stdscr.refresh()
        return True

    def wait(self, timeout=0, keylock=False):
        """Wait for the screen to change
           or keylock to change to zero.

           Called by ATI to wait/pause/sleep
           when DISPLAY is ALL, HOST, or HOSTCODE.

           Return values:

                0  The wait time expired

                1  The condition was satisfied

               12  Session lost or undefined
        """
        self.__prog_mode()

        if timeout == 0:
            waitc = _WAIT_NONE
        elif keylock:
            waitc = _WAIT_KEYLOCK
        else:
            waitc = _WAIT_SCREEN

        r2d2rv = self.__r2d2(self.stdscr, waitc, timeout)
        if r2d2rv in (0, 1, 12):  # if timeout, satisfied, seslost

            if ((self.rewrite or
                 self.__dirty_ranges or
                 self.rewrite_cursor or
                 self.rewrite_keylock or
                 self.rewrite_status)):
                self.__display(self.stdscr, False)
                self.__refresh()

            return r2d2rv  # return timeout, satisfied, seslost

        self.shell_mode()
        in_script = self.__in_script
        in_wait = self.__in_wait
        try:
            self.__in_script = True
            if not keylock:
                self.__in_wait = True
                self.__wait_rc = None

            self.print_stack()
            intro = """
Program execution paused

    - abort   (exit program with RC=127)
    - exit    (exit to the system)
    - goto    (go to session, Esc to return)
    - return  (resume program with wait RC=1)
    - say     (display the value of the specified variable)
    - shell   (execute a shell/system command)
    - show    (display the current session)
    - timeout (resume program with wait RC=0)

Consider the above commands for program interaction. The above stack
trace provides context for where the program was interrupted. Use the
HELP and HELP KEYS commands for more information.
"""
            self.cmdloop(intro)

        finally:
            self.__in_wait = in_wait
            self.__in_script = in_script

        _logger.debug("Zti.wait returning %r", self.__wait_rc)
        return self.__wait_rc

    def write(self, tns, faddr, saddr, eaddr):
        """tnz calls when data written

        Called by tnz.py.
        """
        if self.rewrite:
            return

        for saddr1, eaddr1 in tns.group_addrs(saddr, eaddr):
            self.__write_group(tns, faddr, saddr1, eaddr1)

        if saddr < eaddr:
            self.__clean_range(saddr, eaddr)
        else:
            self.__clean_range(saddr, tns.buffer_size)
            if eaddr != 0:
                self.__clean_range(0, eaddr)

    def write_data(self, tns, daddr, dlen, force=False):
        """Write data

        Called by tnz.py.
        """
        if self.rewrite:
            return

        if not force:
            self.rewrite_cursor = True  # assume needed

        faddr, _ = tns.field(daddr)
        if faddr < 0:
            faddr = 0

        caddr2 = (daddr + dlen) % tns.buffer_size
        return self.write(tns, faddr, daddr, caddr2)

    def write_data_prep(self, tns, daddr, dlen):
        """Write data prep for when data may overlay field(s)

        Called by tnz.py.

        If data wipes out a field, it may change the attributes
        of existing characters that are now in the "merged" field.
        This will make sure such existing characters get refreshed.
        """
        if self.rewrite or dlen <= 0:
            return

        faddr1, _ = tns.field(daddr)
        if faddr1 < 0:
            return

        buffer_size = tns.buffer_size
        if dlen >= buffer_size:
            return

        if faddr1 != daddr:  # if first char not wiping out field
            caddr2 = (daddr+dlen-1) % buffer_size
            faddr2, _ = tns.field(caddr2)
            if faddr1 == faddr2:  # if no fields being wiped
                return

        saddr = (daddr+dlen) % buffer_size
        eaddr, _ = tns.next_field(saddr, daddr)
        if eaddr < 0:
            self.__dirty_range(saddr, daddr, tns=tns)
        else:
            self.__dirty_range(saddr, eaddr, tns=tns)

    # Private methods

    def __bg_wait(self):
        """Keep sessions alive
           while at the command prompt.
        """
        ztl = []
        while True:
            self.__lock.acquire()
            run_in_bg = self.__bg
            if run_in_bg:
                sessions = ati.ati.sessions.split()
                if not sessions:
                    self.__bg = False
                    run_in_bg = False

            self.__lock.release()

            if not run_in_bg:
                return

            # TODO FIXME what if all sessions lost?

            # choose a Zti to use for wait
            # round robin that choice
            # round robin might only matter
            # if seslost is not handled properly
            # which it is not yet

            for session in sessions:
                tns = ati.ati.get_tnz(session)
                if tns not in ztl:
                    break

                ztn = tns
                tns = None

            if tns:
                ztl.append(tns)
            else:
                tns = ztn
                ztl = [ztn]

            tns.wait()

    def __bg_wait_start(self):
        """Ensure the background
           thread is running to keep
           sessions alive while at
           the command prompt.
        """
        self.__lock.acquire()
        run_in_bg = self.__bg
        self.__lock.release()

        if run_in_bg:
            return  # already running

        if not ati.ati.sessions:
            return  # no sessions

        self.__bg = True
        self.__thread = threading.Thread(target=self.__bg_wait)
        self.__thread.start()

    def __bg_wait_end(self):
        """Ensure the background
           thread that may use
           sessions is NOT running.
           Needed so that command
           processing can use the
           sessions. And needed
           so that application
           can shut down.
        """
        if self.__thread is None:
            return  # not running

        self.__lock.acquire()
        self.__bg = False
        self.__lock.release()

        tnz.wakeup_wait()
        self.__thread.join()
        self.__thread = None

    def __clean_range(self, start, end):
        """See __dirty_range.
        """
        if start >= end:
            raise ValueError(f"{start} >= {end}")

        for i, (sidx, eidx) in enumerate(self.__dirty_ranges):
            if start == sidx and end == eidx:
                self.__dirty_ranges.pop(i)
                return

            if start <= sidx and end >= eidx:
                self.__dirty_ranges.pop(i)

            elif start <= sidx and end > sidx:
                self.__dirty_ranges[i] = (end, eidx)

            elif start < eidx and end >= eidx:
                self.__dirty_ranges[i] = (sidx, start)

            elif start > sidx and end < eidx:
                self.__dirty_ranges[i] = (sidx, start)
                self.__dirty_ranges.append((end, eidx))
                return

    def __color_setup(self):
        if self.__has_color is True:
            pass

        elif self.__has_color is False:
            return

        elif not curses.has_colors():
            self.__has_color = False
            return

        try:
            self.__set_colors()
            self.__has_color = True

        except Exception:
            if self.__has_color:
                raise

            self.__has_color = False

    def __dirty_range(self, start, end, tns=None):
        """Mark a range of screen addresses as dirty.

        Remote commands/orders explicitly update various
        addressable character locations on the screen.
        Some of these operations result in implicit
        updates to presentation of characters on the
        screen. Explicit updates are typically handled
        explicitly. The set of dirty ranges built
        by this method are used to handle the implicit
        updates.
        """
        if start >= end:
            if not tns:
                raise ValueError(f"{start} >= {end}")

            if end:
                self.__dirty_range(0, end)

            self.__dirty_range(start, tns.buffer_size)
            return

        start1 = start
        end1 = end
        for i, (sidx, eidx) in enumerate(self.__dirty_ranges):
            if start >= sidx and end <= eidx:
                return

            if start <= sidx and end >= eidx:
                self.__dirty_ranges.pop(i)

            elif start <= sidx and end >= sidx:
                self.__dirty_ranges.pop(i)
                end1 = eidx

            elif start <= eidx and end >= eidx:
                self.__dirty_ranges.pop(i)
                start1 = sidx

        if start1 != start or end1 != end:
            return self.__dirty_range(start1, end1)

        self.__dirty_ranges.append((start, end))

    def __display(self, window, showcursor):
        _logger.debug("begin __display")
        rewrite = self.rewrite
        rewrite_cursor = self.rewrite_cursor or rewrite
        rewrite_keylock = self.rewrite_keylock or rewrite
        rewrite_status = self.rewrite_status or rewrite
        self.rewrite = False
        self.rewrite_cursor = False
        self.rewrite_keylock = False
        self.rewrite_status = False

        session = ati.ati.session
        tns = ati.ati.get_tnz()
        has_color = min(tns.colors, self.colors) >= 8

        # Determine where host screen will displayed and what fits

        row1 = 1
        col1 = 1

        maxrow = tns.maxrow
        maxcol = tns.maxcol
        currow = tns.curadd // maxcol + 1
        curcol = tns.curadd % maxcol + 1

        if self.autosize:
            # set size of terminal to maxrow X maxcol
            # but maybe not exactly... try to maintain
            # the aspect ratio
            arows, acols = self.autosize
            aspect1 = arows / acols
            srows, scols = self.__scale_size(maxrow, maxcol)
            sr2, sc2 = self.__scale_size(maxrow, maxcol + 9)
            sr3, sc3 = self.__scale_size(maxrow + 4, maxcol)
            sr4, sc4 = self.__scale_size(maxrow + 4, maxcol + 9)
            rat = srows / scols
            rat2 = sr2 / sc2
            rat3 = sr3 / sc3
            rat4 = sr4 / sc4
            if abs(aspect1-rat2) < abs(aspect1-rat):
                srows, scols = sr2, sc2
                rat = rat2
            if abs(aspect1-rat3) < abs(aspect1-rat):
                srows, scols = sr3, sc3
                rat = rat3
            if abs(aspect1-rat4) < abs(aspect1-rat):
                srows, scols = sr4, sc4
                rat = rat4

            curses.prog_maxyx = srows, scols

        if rewrite:
            window.clear()
            acs_hline = curses.ACS_HLINE

        rows, cols = window.getmaxyx()

        row1 = 1
        col1 = 1

        # check for room for header (and footer)
        room_for_header = True
        if (maxrow + 3) > rows:
            room_for_header = False

        if rows > maxrow:
            row1 = 1 + ((rows - maxrow) // 2)
        if cols > maxcol:
            col1 = 1 + ((cols - maxcol) // 2)

        if room_for_header and row1 <= 3:
            row1 = 4

        xpos = col1 - 1
        ypos = row1 - 1

        endy = ypos + maxrow

        self.twin_beg = (0, 0)
        self.twin_end = (min(maxcol, cols), min(maxrow, rows))
        self.twin_loc = (xpos, ypos)

        # Draw session selector

        if showcursor and rewrite:
            sesx = col1 + maxcol
            if sesx + 8 <= cols:  # if fits
                sesx = cols - 8
                sessions = ati.ati.sessions.split()
                sescnt = len(sessions)
                curidx = self.__sessel_y
                if curidx is None:
                    curidx = len(sessions) // 2  # current in middle
                elif curidx >= sescnt:
                    curidx = sescnt - 1
                if curidx >= rows:
                    curidx = rows - 1
                idx = sessions.index(session)
                sessions2 = (sessions[idx-curidx:] +
                             sessions[:idx-curidx])
                sessions2 = sessions2[:rows]
                self.__sessel_x = sesx
                self.__sessel = sessions2
                for sesy, ses in enumerate(sessions2):
                    if ses == session:
                        text = rexx.left("*" + ses, 9)
                        if has_color:
                            attr = self.cv2attr[(247, 0)]  # white
                        else:
                            attr = curses.A_BOLD
                    else:
                        text = rexx.left(" " + ses, 9)
                        if has_color:
                            attr = self.cv2attr[(244, 0)]  # green
                        else:
                            attr = curses.A_NORMAL

                    self.__tty_write(sesy, sesx, text, attr)

        # Window/Icon title

        if rewrite or rewrite_status:
            if os.getenv("ZTI_TITLE") == "1":
                if hasattr(window, "set_title"):
                    window.set_title(session)

        # Draw header (and footer)

        if (room_for_header and
            (rewrite or
             rewrite_cursor or
             rewrite_keylock or
             rewrite_status)):

            _logger.debug("before drawing header/footer")
            keylock = ati.value("KEYLOCK", trace=False)
            dashes = rexx.copies("\u2500", min(cols, maxcol))

            if rewrite:
                window.hline(ypos - 3, xpos, acs_hline, len(dashes))

            if tns.ddm_in_progress():
                statlen = 42
                if maxrow >= 100:
                    statlen += 2

                if maxcol >= 100:
                    statlen += 2

                if rewrite or rewrite_status:
                    window.attron(curses.A_REVERSE)
                    bytecnt = "?"
                    download = tns.download()
                    if hasattr(download, "bytecnt"):
                        bytecnt = download.bytecnt

                    msg = f"File transfer in progress ({bytecnt} bytes)"
                    msg = rexx.left(msg, statlen)
                    self.__tty_write(ypos - 2, xpos, msg)
                    window.attroff(curses.A_REVERSE)

                tsx = xpos + statlen
            else:
                if rewrite or rewrite_status:
                    self.__tty_write(ypos - 2, xpos, "Cursor= (")

                rlen = len(str(maxrow))
                clen = len(str(maxcol))
                if rewrite or rewrite_cursor or rewrite_status:
                    self.__tty_write(ypos-2, xpos+9,
                                     rexx.right(str(currow), rlen) +
                                     "," +
                                     rexx.right(str(curcol), clen))

                tsx = xpos + 9 + clen + 1 + rlen
                if rewrite or rewrite_status:
                    self.__tty_write(ypos-2, tsx,
                                     "), Size= (" +
                                     rexx.right(str(maxrow), rlen) +
                                     "," +
                                     rexx.right(str(maxcol), clen) +
                                     "), ")

                tsx += 10 + rlen + 1 + clen + 3
                if rewrite or rewrite_status or rewrite_keylock:
                    if "1" == keylock:
                        window.attron(curses.A_REVERSE)
                    self.__tty_write(ypos-2, tsx,
                                     "KeyLock= "+keylock)
                    if "1" == keylock:
                        window.attroff(curses.A_REVERSE)

                tsx += 10

            if rewrite:
                self.__tty_write(", Session= ")
                self.__tty_write(rexx.left(session, 12))

            tsx += 23
            if rewrite or rewrite_status:
                self.__tty_write(ypos-2, tsx, ati.ati.time)

            if rewrite:
                window.hline(ypos-1, xpos, acs_hline, len(dashes))

                if (row1 + maxrow) <= rows:  # if room for footer
                    window.hline(endy, xpos, acs_hline, len(dashes))

            _logger.debug("after drawing header/footer")

        # Draw 3270 terminal screen

        dirty_ranges = self.__dirty_ranges
        if dirty_ranges:
            if not rewrite:
                buffer_size = tns.buffer_size
                for sidx, eidx in dirty_ranges:
                    eidx %= buffer_size
                    faddr, _ = tns.field(sidx)
                    for saddr, eaddr in tns.group_addrs(sidx, eidx):
                        self.__write_group(tns, faddr, saddr, eaddr)

            dirty_ranges.clear()

        if rewrite:
            _logger.debug("before drawing terminal")
            faddr, _ = tns.next_field(tns.buffer_size-2)
            if faddr < 0:  # if no fields
                self.write(tns, 0, 0, 0)
            else:
                paddr = faddr
                xaddr = faddr
                for saddr, eaddr in tns.char_addrs(faddr):
                    if paddr == xaddr:
                        xaddr = saddr

                    self.__write_blanks(tns, paddr, saddr)
                    paddr = eaddr
                    faddr = (saddr-1) % tns.buffer_size
                    self.write(tns, faddr, saddr, eaddr)

                self.__write_blanks(tns, paddr, xaddr)

            _logger.debug("after drawing terminal")

        _logger.debug("end __display")

    def __endwin(self):
        selectr = self.__stdin_selectr
        if selectr and self.__stdin_selected:
            self.__stdin_selected = False
            tnz.selector_del(selectr)

        if _osname != "Windows":
            sigx.del_handler(tnz.wakeup_wait)

        curses.endwin()

    def __key_data(self, tns, data):
        try:
            tns.key_data(data, zti=self)

        except UnicodeEncodeError:
            curses.flash()
            curses.beep()
            _logger.exception("cannot encode")

    def __paste_data(self, tns, data):
        try:
            tns.paste_data(data, zti=self)

        except UnicodeEncodeError:
            curses.flash()
            curses.beep()
            _logger.exception("cannot encode")

    def __prep_wait(self):
        if hasattr(curses, "selectr"):
            selectr = curses.selectr
        else:
            selectr = self.__stdin_selectr

        stdin_selected = self.__stdin_selected
        if stdin_selected:
            old_selectr = self.__stdin_selectr
        else:
            old_selectr = None

        if selectr is not old_selectr:
            if stdin_selected:
                self.__stdin_selected = False
                tnz.selector_del(old_selectr)

            if selectr:
                tnz.selector_set(selectr, data=self)
                self.__stdin_selected = True

        self.__stdin_selectr = selectr

    def __prog_mode(self):
        """Set the TTY to prog mode.

        Initialize curses if necessary.
        """
        if self.__tty_mode == 1:  # prog
            return

        if self.autosize:
            (columns, lines) = os.get_terminal_size()
            self.autosize = (lines, columns)

        if not self.stdscr:
            # Initialize curses

            # The ESC key is important since it
            # allows the user to drop back to the
            # command line. The curses default delay
            # to wait to see if ESC (x1b) is the
            # start of an escape sequence or just
            # an escape key feels too long. Set
            # a more reasonable value. Note that
            # this must be done BEFORE curses.initscr
            # (or wrapper) is called. And the
            # following line of code will only set
            # it if it is not already set in the
            # environment.

            os.environ.setdefault("ESCDELAY", "25")

            try:
                self.stdscr = curses.initscr()
                Zti._stdscr = self.stdscr

                curses.cbreak()
                curses.noecho()
                curses.def_prog_mode()
                self.__endwin()

                self.stdscr.keypad(True)
                self.stdscr.notimeout(0)  # faster ESC?

                # TODO only set up mouse if NOT "show" mode?
                mousemask = (curses.BUTTON1_CLICKED |
                             curses.BUTTON1_DOUBLE_CLICKED)
                masks = curses.mousemask(mousemask)
                if masks != 0:  # if successful
                    if self.__shell_mousemask is None:
                        self.__shell_mousemask = masks[1]

                self.__color_setup()

            except Exception:
                if self.stdscr:
                    self.__endwin()
                    self.stdscr = None

                raise
        else:
            self.stdscr.clear()  # avoid showing old screen
            self.stdscr.refresh()  # for above clear
            # TODO only set up mouse if NOT "show" mode?
            mousemask = (curses.BUTTON1_CLICKED |
                         curses.BUTTON1_DOUBLE_CLICKED)
            masks = curses.mousemask(mousemask)
            if masks != 0:  # if successful
                if self.__shell_mousemask is None:
                    self.__shell_mousemask = masks[1]

            self.__color_setup()

        curses.flushinp()
        if _osname != "Windows":
            self.__stdout.write("\x1b[?2004h")  # bracketed paste ON
            self.__stdout.flush()

        if self.__sigwinch_selected:
            sigx.add_handler(signal.SIGWINCH, tnz.wakeup_wait)

        self.rewrite = True
        self.__tty_mode = 1

    def __r2d2(self, win, waitc, timeout):
        """Read and Display 3270 Terminal
        """
        # See https://en.wikipedia.org/wiki/Table_of_keyboard_shortcuts
        # when assigning keyboard shortcuts.

        show = (waitc != _WAIT_GOTO)
        if waitc == _WAIT_NONE:
            timeout = 0
        elif waitc == _WAIT_FOREVER:
            timeout = -1
        elif waitc == _WAIT_GOTO:
            timeout = -1
        elif timeout <= 0:
            raise ValueError("Expected timeout>0")

        insmode = False
        if show:
            self.__prog_curs_vis = 0
        else:
            self.__prog_curs_vis = 1

        tout = timeout
        if timeout > 0:
            etime = time.time() + timeout

        self.__refresh()
        refresh = False
        paste = None

        try:
            while True:
                cstr = self.__tty_read(win, 0, refresh=refresh)
                refresh = None
                if (cstr == "" and  # session change
                    (waitc == _WAIT_KEYLOCK or
                     waitc == _WAIT_SCREEN)):
                    # TODO be more specific about
                    # keylock and screen change
                    return 1  # condition sastisfied

                if not cstr:
                    tns = ati.ati.get_tnz()
                    if not tns:
                        return 12

                    if tns.seslost:
                        return 12

                    if tns.ddmdata or tns.ddmdict:
                        return 10  # have ddmdata

                    if self.downloadaction:
                        self.downloadaction = False
                        return 11  # have download action

                    if ((self.rewrite or
                         self.__dirty_ranges or
                         self.rewrite_cursor or
                         self.rewrite_keylock or
                         self.rewrite_status)):
                        self.__display(win, not show)

                    # show cursor
                    if not show:
                        begx, begy = self.twin_beg
                        endx, endy = self.twin_end
                        currow = tns.curadd // tns.maxcol + 1
                        curcol = tns.curadd % tns.maxcol + 1
                        if (currow > begy and
                                currow <= endy and
                                curcol > begx and
                                curcol <= endx):
                            if insmode:
                                self.__prog_curs_vis = 2  # very visible
                            else:
                                self.__prog_curs_vis = 1  # visible

                            xpos, ypos = self.twin_loc
                            _logger.debug("before win.move")
                            win.move(ypos+currow-1, xpos+curcol-1)
                            _logger.debug("after win.move")

                    cstr = self.__tty_read(win, tout)
                    if waitc in (_WAIT_KEYLOCK, _WAIT_SCREEN):
                        if cstr == "":
                            # TODO be more specific about
                            # keylock and screen change
                            return 1  # condition sastisfied

                        if cstr is None:
                            return 0  # timeout

                tns = ati.ati.get_tnz()
                if not tns:
                    return 12  # seslost

                if tns.seslost:
                    return 12  # seslost

                if tns.ddmdata or tns.ddmdict:
                    return 10  # have ddmdata

                if self.downloadaction:
                    self.downloadaction = False
                    return 11  # have download action

                # check for Alt+letter shortcut

                altc = 0
                if isinstance(cstr, str):
                    if ((cstr and cstr.startswith('\x1b') and
                         len(cstr) == 2 and
                         cstr.lower() == cstr) or
                        (cstr and cstr.startswith("ALT_") and
                         len(cstr) == 5 and
                         str.isalpha(cstr[-1]))):
                        maxcol = tns.maxcol
                        alet1 = cstr[-1].lower()
                        alet2 = alet1.upper()
                        elet1 = tns.codec_info[0].encode(alet1)[0][0]
                        elet2 = tns.codec_info[0].encode(alet2)[0][0]
                        for i in range(0, maxcol):
                            if ((tns.plane_dc[i] != elet1 and
                                 tns.plane_dc[i] != elet2)):
                                continue

                            exn = tns.plane_eh[i]
                            if (exn & 0x0C0) == 0x0C0:  # if underline
                                altc = i+1
                                break

                # process input

                if not cstr:  # session update
                    pass

                elif cstr is True:

                    # maybe resize?

                    (maxy, maxx) = win.getmaxyx()
                    (columns, lines) = os.get_terminal_size()
                    if (maxy != lines) or (maxx != columns):
                        win.clear()
                        win.noutrefresh()
                        win.resize(lines, columns)
                        self.rewrite = True

                elif cstr == "\x1b" or cstr == "KEY_ESC":  # ESC
                    _logger.debug("keyed Esc")
                    return cstr

                elif cstr == "KEY_RESIZE":
                    _logger.warning("KEY_RESIZE")

                    self.rewrite = True
                    try:
                        curses.resize_term(0, 0)  # hack for Windows
                    except Exception:
                        pass

                    (maxy, maxx) = win.getmaxyx()
                    (columns, lines) = os.get_terminal_size()
                    if (maxy != lines) or (maxx != columns):
                        win.resize(lines, columns)
                        win.erase()
                        win.noutrefresh()

                elif show:

                    curses.flash()

                elif cstr.startswith("\x1b[200~"):  # bracketed paste

                    paste = cstr[6:]
                    if paste.endswith("\x1b[201~"):
                        paste = paste[:-6]
                        if paste:
                            if tns.pwait or tns.system_lock_wait:
                                curses.flash()
                                curses.beep()
                            else:
                                self.__paste_data(tns, paste)

                        paste = None

                elif cstr.endswith("\x1b[201~"):  # bracketed paste end

                    paste += cstr[:-6]
                    if paste:
                        if tns.pwait or tns.system_lock_wait:
                            curses.flash()
                            curses.beep()
                        else:
                            self.__paste_data(tns, paste)

                    paste = None

                elif paste is not None:  # more bracketed paste data

                    paste += cstr

                elif cstr == "KEY_SIC":
                    _logger.debug("keyed Shift+Insert")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    elif _osname != "Windows":
                        curses.flash()
                        curses.beep()
                    else:
                        paste = None
                        fmt = 13  # CF_UNICODETEXT
                        k32 = ctypes.windll.kernel32
                        k32.GlobalLock.argtypes = [ctypes.c_void_p]
                        k32.GlobalLock.restype = ctypes.c_void_p
                        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                        u32 = ctypes.windll.user32
                        u32.GetClipboardData.restype = ctypes.c_void_p
                        u32.OpenClipboard(0)
                        try:
                            if u32.IsClipboardFormatAvailable(fmt):
                                data = u32.GetClipboardData(fmt)
                                data_locked = k32.GlobalLock(data)
                                paste = ctypes.wstring_at(data_locked)
                                k32.GlobalUnlock(data_locked)
                        finally:
                            u32.CloseClipboard()

                        if paste:
                            self.__paste_data(tns, paste)

                        paste = None

                elif cstr == "\x0c":  # Ctrl+L
                    _logger.debug("keyed Ctrl+L")

                    self.rewrite = True

                    (maxy, maxx) = win.getmaxyx()
                    (columns, lines) = os.get_terminal_size()
                    if (maxy != lines) or (maxx != columns):
                        # assume Ctrl+L is for size change
                        win.resize(lines, columns)
                        win.erase()
                        win.noutrefresh()

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.clear()

                elif len(cstr) == 1 and cstr.isprintable():

                    keylock = ati.value("KEYLOCK", trace=False)
                    if keylock == "1":
                        curses.flash()
                    else:
                        if insmode:
                            tns.key_ins_data(cstr, zti=self)
                        else:
                            self.__key_data(tns, cstr)

                elif cstr == "\r":
                    _logger.debug("keyed Enter")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.enter()
                        self.rewrite_keylock = True

                elif cstr == "\n":
                    _logger.debug("keyed Shift+Enter")

                    tns.key_newline()

                elif cstr == "\t":
                    _logger.debug("keyed Tab")

                    tns.key_tab(zti=self)
                    self.rewrite_cursor = True

                elif (cstr == "\b" or
                      cstr == "KEY_BACKSPACE" or
                      cstr == "\x7f"):
                    _logger.debug("keyed Backspace")

                    tns.key_backspace(zti=self)
                    self.rewrite_cursor = True

                elif (cstr == "\x0b" or  # Ctrl+K
                      cstr == "\x1b[4~" or  # Shift+End
                      cstr == "\x1b[F" or  # Shift+End
                      cstr == "KEY_SEND"):  # Shift+End
                    _logger.debug("keyed Shift+End or Ctrl+K")

                    tns.key_eraseeof(zti=self)

                elif cstr == "KEY_END":  # End
                    _logger.debug("keyed End")

                    tns.key_end()
                    self.rewrite_cursor = True

                elif (cstr == "\x1b[1~" or
                      cstr == "\x1b H" or
                      cstr == "KEY_HOME"):
                    _logger.debug("keyed Home")

                    tns.key_home(zti=self)
                    self.rewrite_cursor = True

                elif cstr == "KEY_DC":
                    _logger.debug("keyed Delete")

                    tns.key_delete(zti=self)

                elif (cstr == "KEY_BTAB" or  # Shift+Tab
                      cstr == "\x1b[~"):  # Shift+Tab Windows->ssh
                    _logger.debug("keyed Shift+Tab")

                    tns.key_backtab(zti=self)
                    self.rewrite_cursor = True

                elif altc > 0:

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.set_cursor_position(1, altc)
                        tns.enter()
                        self.rewrite_keylock = True
                        self.rewrite_cursor = True

                elif cstr == "KEY_PPAGE":  # PgUp
                    _logger.debug("keyed PgUp")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf7()
                        self.rewrite_keylock = True

                elif cstr == "KEY_NPAGE":  # PgDn
                    _logger.debug("keyed PgDn")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf8()
                        self.rewrite_keylock = True

                elif cstr == "KEY_UP":
                    _logger.debug("keyed Up")

                    tns.key_curup(zti=self)
                    self.rewrite_cursor = True

                elif cstr == "KEY_DOWN":
                    _logger.debug("keyed Dn")

                    tns.key_curdown(zti=self)
                    self.rewrite_cursor = True

                elif cstr == "KEY_LEFT":
                    _logger.debug("keyed Left")

                    tns.key_curleft(zti=self)
                    self.rewrite_cursor = True

                elif cstr == "KEY_RIGHT":
                    _logger.debug("keyed Right")

                    tns.key_curright(zti=self)
                    self.rewrite_cursor = True

                elif cstr in ("\x1b\x1b[D",  # Alt+LEFT
                              "\x1bb",  # Alt+LEFT (Terminal.app)
                              "\x1b[1;3D"):  # Alt+LEFT (Windows)
                    _logger.debug("keyed Alt+Left")

                    tns.key_word_left()
                    self.rewrite_cursor = True

                elif cstr in ("\x1b\x1b[C",  # Alt+RIGHT
                              "\x1bf",  # Alt+RIGHT (Terminal.app)
                              "\x1b[1;3C"):  # Alt+RIGHT (Windows)
                    _logger.debug("keyed Alt+Right")

                    tns.key_word_right()
                    self.rewrite_cursor = True

                elif cstr == "KEY_IC":
                    _logger.debug("keyed Insert")

                    insmode = (not insmode)
                    if insmode:
                        self.__prog_curs_vis = 2  # very visible
                    else:
                        self.__prog_curs_vis = 1  # visible

                elif (cstr == "\x1b1" or  # ESC+1 (Alt+1)
                      cstr == "ALT_1" or  # ESC+1 (Alt+1)
                      cstr == "\x1bKEY_IC" or  # ESC+Insert (Alt+Insert)
                      cstr == "ALT_INS"):  # Alt+Insert
                    _logger.debug("keyed Alt+1 or Alt+Insert")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pa1()
                        self.rewrite_keylock = True

                elif (cstr == "\x1b2" or  # ESC+2 (Alt+2)
                      cstr == "ALT_2" or  # ESC+2 (Alt+2)
                      cstr == "\x1b\x1b[1~" or  # ESC+Home (Alt+Home)
                      cstr == "ALT_HOME"):  # Alt+Home
                    _logger.debug("keyed Alt+2 or Alt+Home")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pa2()
                        self.rewrite_keylock = True

                elif (cstr == "\x1b3" or  # ESC+3 (Alt+3)
                      cstr == "ALT_3"):  # ESC+3 (Alt+3)
                    _logger.debug("keyed Alt+3")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pa3()
                        self.rewrite_keylock = True

                elif (cstr == "\x1ba" or  # ESC+a (Alt+A)
                      cstr == "ALT_A" or  # ESC+a (Alt+A)
                      cstr == "\x03"):  # Ctrl+C
                    _logger.debug("keyed Alt+A or Ctrl+C")

                    tns.attn()

                elif (cstr == "\x1bc" or  # ESC+c (Alt+c)
                      cstr == "ALT_C"):  # ESC+c (Alt+c)
                    _logger.debug("keyed Alt+C")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.clear()
                        self.rewrite = True
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(1)" or
                      cstr == "\x1b[11~"):
                    _logger.debug("keyed F1")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf1()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(2)" or
                      cstr == "\x1b[12~"):
                    _logger.debug("keyed F2")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf2()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(3)" or
                      cstr == "\x1b[13~"):
                    _logger.debug("keyed F3")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf3()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(4)" or
                      cstr == "\x1b[14~"):
                    _logger.debug("keyed F4")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf4()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(5)":
                    _logger.debug("keyed F5")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf5()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(6)":
                    _logger.debug("keyed F6")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf6()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(7)":
                    _logger.debug("keyed F7")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf7()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(8)":
                    _logger.debug("keyed F8")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf8()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(9)":
                    _logger.debug("keyed F9")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf9()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(10)":
                    _logger.debug("keyed F10")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf10()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(11)":
                    _logger.debug("keyed F11")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf11()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(12)":
                    _logger.debug("keyed F12")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf12()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(13)":
                    _logger.debug("keyed Shift+F1")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf13()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(14)":
                    _logger.debug("keyed Shift+F2")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf14()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(15)" or  # Shift+F3
                      cstr == "\x1b[25~"):  # Shift+F3
                    _logger.debug("keyed Shift+F3")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf15()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(16)" or  # Shift+F4
                      cstr == "\x1b[26~"):  # Shift+F4
                    _logger.debug("keyed Shift+F4")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf16()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(17)" or  # Shift+F5
                      cstr == "\x1b[28~"):  # Shift+F5
                    _logger.debug("keyed Shift+F5")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf17()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(18)" or  # Shift+F6
                      cstr == "\x1b[29~"):  # Shift+F6
                    _logger.debug("keyed Shift+F6")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf18()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(19)" or  # Shift+F7
                      cstr == "\x1b[31~"):  # Shift+F7
                    _logger.debug("keyed Shift+F7")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf19()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(20)" or  # Shift+F8
                      cstr == "\x1b[32~"):  # Shift+F8
                    _logger.debug("keyed Shift+F8")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf20()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(21)" or  # Shift+F9
                      cstr == "\x1b[33~"):  # Shift+F9
                    _logger.debug("keyed Shift+F9")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf21()
                        self.rewrite_keylock = True

                elif (cstr == "KEY_F(22)" or  # Shift+F10
                      cstr == "\x1b[34~"):  # Shift+F10
                    _logger.debug("keyed Shift+F10")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf22()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(23)":
                    _logger.debug("keyed Shift+F11")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf23()
                        self.rewrite_keylock = True

                elif cstr == "KEY_F(24)":
                    _logger.debug("keyed Shift+F12")

                    if tns.pwait or tns.system_lock_wait:
                        curses.flash()
                        curses.beep()
                    else:
                        tns.pf24()
                        self.rewrite_keylock = True

                elif (cstr == "\x1b\x1b[5~" or  # Alt+PgUp Putty
                      cstr == "\x1b[5;3~" or  # Alt+PgUp Git Bash
                      cstr == "kPRV3" or      # Alt_PgUp Windows->ssh
                      cstr == "ALT_PGUP" or   # Alt+PgDn Windows
                      cstr == "\x1bKEY_PPAGE"):  # Alt+PgUp z/OS
                    _logger.debug("keyed Alt+PgUp")

                    session = ati.ati.session
                    sessions = ati.ati.sessions
                    pos = rexx.wordpos(session, sessions)
                    pos -= 1
                    if pos < 1:
                        pos = rexx.words(sessions)

                    session = rexx.word(sessions, pos)
                    ati.ati.session = session
                    if ati.ati.seslost:
                        return 12

                    self.rewrite = True

                elif (cstr == "\x1b\x1b[6~" or  # Alt+PgDn Putty
                      cstr == "\x1b[6;3~" or  # Alt+PgDn Git Bash
                      cstr == "kNXT3" or      # Alt_PgUp Windows->ssh
                      cstr == "ALT_PGDN" or   # Alt+PgDn Windows
                      cstr == "\x1bKEY_NPAGE"):  # Alt+PgDn z/OS
                    _logger.debug("keyed Alt+PgDn")

                    session = ati.ati.session
                    sessions = ati.ati.sessions
                    pos = rexx.wordpos(session, sessions)
                    pos += 1
                    if pos > rexx.words(sessions):
                        pos = 1

                    session = rexx.word(sessions, pos)
                    ati.ati.session = session
                    if ati.ati.seslost:
                        return 12

                    self.rewrite = True

                elif cstr == "\x17":  # Ctrl+W
                    _logger.debug("keyed Ctrl+W")

                    ati.drop("SESSION")
                    sessions = ati.ati.sessions
                    if not sessions:
                        return 12

                    session = ati.ati.session
                    ati.ati.session = session
                    if ati.ati.seslost:
                        return 12

                    self.rewrite = True

                elif cstr == "\x0f":  # Ctrl+O
                    _logger.debug("keyed Ctrl+O")

                    wstr = tns.word_at(tns.curadd)
                    import webbrowser
                    if wstr.startswith("http://"):
                        webbrowser.open_new_tab(wstr)
                    elif wstr.startswith("https://"):
                        webbrowser.open_new_tab(wstr)
                    else:
                        curses.flash()
                        curses.beep()

                elif cstr == "KEY_MOUSE":
                    mouserr = False
                    try:
                        mid, mpx, mpy, mpz, mbstate = curses.getmouse()
                    except Exception:
                        mouserr = True

                    if ((not mouserr and
                         mpx >= self.twin_loc[0] and
                         mpy >= self.twin_loc[1] and
                         mpx < (self.twin_loc[0] + self.twin_end[0]) and
                         mpy < (self.twin_loc[1] + self.twin_end[1]))):
                        xpos = mpx - self.twin_loc[0]
                        ypos = mpy - self.twin_loc[1]
                        xpos += self.twin_beg[0]
                        ypos += self.twin_beg[1]

                        if ((mbstate &
                             curses.BUTTON1_DOUBLE_CLICKED) != 0):
                            if tns.pwait or tns.system_lock_wait:
                                curses.flash()
                                curses.beep()
                            else:
                                tns.set_cursor_position(ypos+1, xpos+1)
                                tns.enter()
                                self.rewrite_keylock = True
                                self.rewrite_cursor = True

                        elif (mbstate &
                              curses.BUTTON1_CLICKED) != 0:
                            addr = (ypos * tns.maxcol) + xpos
                            if tns.is_protected(addr):
                                wstr = tns.word_at(addr)
                                if ((wstr.startswith("http://") or
                                     wstr.startswith("https://"))):
                                    import webbrowser
                                    webbrowser.open_new_tab(wstr)
                                else:
                                    tns.set_cursor_position(ypos+1,
                                                            xpos+1)
                                    self.rewrite_cursor = True

                            elif tns.is_pen_detectable(addr):
                                # right action ?
                                tns.set_cursor_position(ypos+1, xpos+1)
                                tns.enter()
                                self.rewrite_keylock = True
                                self.rewrite_cursor = True
                            else:
                                tns.set_cursor_position(ypos+1, xpos+1)
                                self.rewrite_cursor = True

                    elif (not mouserr and
                          mpx > self.__sessel_x and
                          mpy < len(self.__sessel)):

                        session = self.__sessel[mpy]
                        self.__sessel_y = mpy
                        if session:
                            oldses = ati.ati.session
                            if session == oldses:
                                session = None

                        if session:
                            ati.ati.session = session
                            if ati.ati.seslost:
                                return

                            self.rewrite = True

                    else:
                        if not mouserr:
                            _logger.debug("KEY_MOUSE: %r",
                                          (mid, mpx, mpy, mpz, mbstate))

                        curses.flash()

                elif cstr == "\x00":
                    pass  # Windows key? handled by Windows

                else:
                    _logger.warning("Unknown key: %r", cstr)

                if tout == 0:
                    return 0  # timeout

                if tout > 0:
                    tout = max(0, etime-time.time())
        finally:
            pass

    def __refresh(self):
        # put cursor in desired state before we may suspend
        if self.__cur_curs_vis != self.__prog_curs_vis:
            if self.__prog_curs_vis == 0:
                self.stdscr.leaveok(True)
                curses.curs_set(0)
            else:
                self.stdscr.leaveok(False)
                curses.curs_set(self.__prog_curs_vis)

            self.__cur_curs_vis = self.__prog_curs_vis

        self.stdscr.refresh()

    def __scale_size(self, maxrow, maxcol):
        arows, acols = self.autosize
        aspect1 = arows / acols
        aspect2 = maxrow / maxcol
        if aspect1 == aspect2:
            srows = maxrow
            scols = maxcol
        elif aspect1 > aspect2:
            srows = round(maxcol * aspect1)
            scols = maxcol
        else:
            srows = maxrow
            scols = round(maxrow / aspect1)

        return srows, scols

    def __session_check(self):
        while 1:
            seslost = ati.ati.seslost
            if seslost:
                self.__shell_mode()
                exc_info = ati.ati.ses_exc
                if exc_info:
                    msg = "".join(traceback.format_exception(*exc_info))
                    msg = msg.rstrip()
                    ati.say(msg)

                self.do_say("SESLOST")

            tns = ati.ati.get_tnz()
            if not tns:
                break

            if not seslost and not tns.seslost:
                break

            session = ati.ati.session
            ati.ati.session = session

    def __set_colors(self):
        curses.start_color()
        curses.use_default_colors()
        colors = curses.COLORS
        color_pairs = curses.COLOR_PAIRS
        self.colors = colors
        _logger.debug("colors = %d", colors)
        _logger.debug("color_pairs = %d", color_pairs)

        # IBM PCOMM default colors:
        #   name           r,     g,     b
        #   black          0,     0,     0  000000
        #   red          240,    24,    24  f01818
        #   green         36,   216,    48  24d830
        #   yellow       255,   255,     0  ffff00
        #   blue         120,   144,   240  7890f0
        #   pink         255,     0,   255  ff00ff
        #   turquoise     88,   240,   240  58f0f0
        #   white        255,   255,   255  ffffff
        #
        # Converting from 256 to 1000:
        #   name           r,     g,     b
        #   black          0,     0,     0
        #   red          941,    94,    94
        #   green        141,   847,   188
        #   yellow      1000,  1000,     0
        #   blue         471,   565,   941
        #   pink        1000,     0,  1000
        #   turquoise    345,   941,   941
        #   white       1000,  1000,  1000
        #
        # curses defines the following:
        #   COLOR_BLACK
        #   COLOR_BLUE
        #   COLOR_CYAN
        #   COLOR_GREEN
        #   COLOR_MAGENTA
        #   COLOR_RED
        #   COLOR_WHITE
        #   COLOR_YELLOW
        #
        # approximate mapping from 3270 to curses:
        #   COLOR_BLACK     black
        #   COLOR_BLUE      blue
        #   COLOR_CYAN      turquoise
        #   COLOR_GREEN     green
        #   COLOR_MAGENTA   pink
        #   COLOR_RED       red
        #   COLOR_WHITE     white
        #   COLOR_YELLOW    yellow
        #
        # For 16 + 36*r + 6*g + b...
        # Converting from 256 to 5:
        #   name           r,     g,     b    *   **
        #   black          0,     0,     0   16   16
        #   red            4,     0,     0  160  196
        #   green          0,     4,     0   40   77
        #   yellow         5,     5,     0  226  226
        #   blue           2,     2,     4  104  111
        #   pink           5,     0,     5  201  201
        #   turquoise      1,     4,     4   80  123
        #   white          5,     5,     5  231  231
        # * Using FLOOR function
        # ** Using ROUND function

        if colors >= 264:
            black_rgb = (0, 0, 0)
            red_rgb = (941, 94, 94)
            green_rgb = (141, 847, 188)
            yellow_rgb = (1000, 1000, 0)
            blue_rgb = (471, 565, 941)
            pink_rgb = (1000, 0, 1000)
            turquoise_rgb = (345, 941, 941)
            white_rgb = (1000, 1000, 1000)

            color_start = 256
            curses.init_color(color_start, *black_rgb)
            curses.init_color(color_start + 1, *blue_rgb)
            curses.init_color(color_start + 2, *red_rgb)
            curses.init_color(color_start + 3, *pink_rgb)
            curses.init_color(color_start + 4, *green_rgb)
            curses.init_color(color_start + 5, *turquoise_rgb)
            curses.init_color(color_start + 6, *yellow_rgb)
            curses.init_color(color_start + 7, *white_rgb)

            cv2color = {0: color_start,  # default/black
                        241: color_start + 1,  # blue
                        242: color_start + 2,  # red
                        243: color_start + 3,  # pink
                        244: color_start + 4,  # green
                        245: color_start + 5,  # turquoise
                        246: color_start + 6,  # yellow
                        247: color_start + 7,  # white
                        }
        elif colors >= 256:
            cv2color = {0: 16,  # default/black
                        241: 104,  # blue
                        242: 196,  # red
                        243: 201,  # pink
                        244: 40,  # green
                        245: 80,  # turquoise
                        246: 226,  # yellow
                        247: 231,  # white
                        }
        else:
            cv2color = {0: curses.COLOR_BLACK,  # default/black
                        241: curses.COLOR_BLUE,  # blue
                        242: curses.COLOR_RED,  # red
                        243: curses.COLOR_MAGENTA,  # pink
                        244: curses.COLOR_GREEN,  # green
                        245: curses.COLOR_CYAN,  # turquoise
                        246: curses.COLOR_YELLOW,  # yellow
                        247: curses.COLOR_WHITE,  # white
                        }

        color_pair = 0
        for fgid, fg_v in cv2color.items():
            if fgid == 0:
                fg_v = cv2color[244]  # green default?

            for bgid, bg_v in cv2color.items():
                if fg_v == bg_v:
                    continue

                color_pair += 1
                curses.init_pair(color_pair, fg_v, bg_v)
                attr = curses.color_pair(color_pair)
                self.cv2attr[(fgid, bgid)] = attr

    def __shell_mode(self, init=False):
        """Set the TTY to shell mode.

        When init==True, curses will
        be initialized if it is not
        yet initialized... and
        perform what is needed to
        get the current terminal
        size recognized.
        """
        if init:
            # need to make sure that
            # terminal size is refreshed
            # At least on z/OS, seem to
            # have to call initscr to
            # get that to happen.
            if not self.stdscr:
                pass
            elif self.__tty_mode == 0:
                self.stdscr = None
            else:
                self.__endwin()
                self.stdscr = None

            self.__prog_mode()
            self.__endwin()
            if self.__shell_mousemask is not None:
                curses.mousemask(self.__shell_mousemask)

            curses.flushinp()
            self.__tty_mode = 0
            self.__cur_curs_vis = 1  # endwin set
            return

        if self.__tty_mode == 0:  # shell
            return

        if _osname != "Windows":
            self.__stdout.write("\x1b[?2004l")  # bracketed paste OFF
            self.__stdout.flush()

        self.__endwin()
        if self.__shell_mousemask is not None:
            curses.mousemask(self.__shell_mousemask)

        curses.flushinp()
        self.__cur_curs_vis = 1  # endwin set
        self.__tty_mode = 0

        # I have seen behavior where traceback.print_stack
        # does not end up printing anything without doing the
        # following flush.
        self.__stdout.flush()

    def __tty_read(self, win, timeout, refresh=None):
        """Read from tty

        Considers session i/o while waiting for
        input from tty.

        returns a null string if something happened
        with the current session
        """
        if refresh or (timeout != 0 and refresh is None):
            self.__refresh()

        try:
            tns = ati.ati.get_tnz()

            k = None
            win.timeout(0)
            other_selected = False
            self.__prep_wait()
            if self.__stdin_selectr:
                tout = None
            else:
                tout = 0.04  # effective keyboard response time

            if timeout is not None and timeout >= 0:
                etime = time.time() + timeout
                if tout is None or timeout < tout:
                    tout = timeout
            else:
                etime = None

            while True:
                try:
                    k = win.getkey()
                    if k == "\x1b":  # ESC
                        while True:
                            k += win.getkey()
                            # TODO stop loop if char says so

                except curses.error:
                    pass

                if k is not None:
                    return k

                if other_selected:
                    # must be for wakeup_fd
                    return True

                waitrv = self.__wait(tns, tout, zti=self)
                if waitrv is True:
                    return ""

                if waitrv is None:
                    # stdin or wakeup_fd
                    other_selected = True

                if tout == 0:
                    return None

                if etime is not None:
                    tout = min(tout, max(0, etime-time.time()))

        except KeyboardInterrupt:

            return "\x03"  # Ctrl+c

    def __tty_write(self, *argv, spos=0, epos=None):
        """Write to the tty (terminal)

        Parameters similiar to addstr.

        __tty_write(text[, attr])
        __tty_write(y, x, text[, attr])

        text may be a string or bytes
        y is the zero-based row
        x is the zero-based column
        attr is the curses attributes

        When y and x are not specified, text is
        written at the current cursor position.

        When attr is not specified, text is written
        with the current attributes.
        """
        self.__prog_mode()

        if self.__cur_curs_vis != 0:
            self.stdscr.leaveok(True)
            curses.curs_set(0)
            self.__cur_curs_vis = 0

        if len(argv) <= 2:
            instr = argv[0]

            if len(argv) > 1:
                attr = argv[1]
            else:
                attr = None

            if spos == 0 and (epos is None or epos == len(instr)):
                if attr is None:
                    self.stdscr.addstr(instr)
                else:
                    self.stdscr.addstr(instr, attr)

            elif epos is None:
                if attr is None:
                    self.stdscr.addstr(instr[spos:])
                else:
                    self.stdscr.addstr(instr[spos:], attr)

            else:
                if attr is None:
                    self.stdscr.addstr(instr[spos:epos])
                else:
                    self.stdscr.addstr(instr[spos:epos], attr)

        else:  # len(argv) != 1
            ypos = argv[0]
            xpos = argv[1]
            instr = argv[2]

            if len(argv) > 3:
                attr = argv[3]
            else:
                attr = None

            rows, cols = self.stdscr.getmaxyx()
            if ypos >= rows:
                return
            if xpos >= cols:
                return

            if epos is None:
                width = len(instr) - spos
            else:
                width = epos - spos

            if width > (cols - xpos):  # tail of string too long
                epos = spos + (cols - xpos)  # shorten

            insch = None
            if ypos >= (rows - 1) and (xpos + width) >= (cols - 1):
                # curses does not like use of bottom right
                if epos is None:
                    epos = len(instr) - 1
                else:
                    epos -= 1

                insch = instr[epos:epos+1]  # bottom-right char

            if spos == 0 and (epos is None or epos == len(instr)):
                if attr is None:
                    self.stdscr.addstr(ypos, xpos, instr)
                else:
                    self.stdscr.addstr(ypos, xpos, instr, attr)

            elif epos is None:
                if attr is None:
                    self.stdscr.addstr(ypos, xpos, instr[spos:])
                else:
                    self.stdscr.addstr(ypos, xpos, instr[spos:], attr)

            elif attr is None:
                self.stdscr.addstr(ypos, xpos, instr[spos:epos])
            else:
                self.stdscr.addstr(ypos, xpos, instr[spos:epos], attr)

            if insch:  # if skipped bottom-right char
                # use insch to fill in bottom-right char
                if attr is None:
                    self.stdscr.insch(insch)
                else:
                    self.stdscr.insch(insch, attr)

    def __update_prompt(self):
        """Set prompt according to SESSION.
        """
        session = ati.ati.session
        self.prompt = "Session: "+session+"> "

        if self.__in_script:
            self.prompt = "(paused) "+self.prompt

    def __wait(self, tns, timeout=0, zti=None, key=None):
        self.__prep_wait()
        return tns.wait(timeout, zti=zti, key=key)

    def __write_blanks(self, tns, saddr, eaddr):
        """call to write where field attributes are
        """
        has_color = min(tns.colors, self.colors) >= 8

        # Determine location on screen

        xpos1, ypos1 = self.twin_beg
        xpos2, ypos2 = self.twin_end
        xpos, ypos = self.twin_loc

        if has_color:
            attr = self.cv2attr[(0, 0)]
        else:
            attr = curses.A_NORMAL

        for rsp, rep in tns.iterow(saddr, eaddr):
            absy = rsp // tns.maxcol
            if absy < ypos1 or absy >= ypos2:
                continue

            gsx = rsp % tns.maxcol
            gex = (rep-1) % tns.maxcol
            if gex < xpos1 or gsx >= xpos2:
                continue

            # Trim displayed characters, if needed

            if gsx < xpos1:
                rsp += xpos1 - gsx
                gsx = xpos2

            if gex >= xpos2:
                rep -= gex - xpos2 + 1

            gsx += xpos
            absy += ypos

            clen = rep - rsp
            blanks = " " * clen
            self.__tty_write(absy, gsx, blanks, attr)

    def __write_group(self, tns, faddr, caddr1, endpos):
        """Write group of field characters.

        The group of characters all have the
        same attributes and they are on a single
        line/row.
        """
        has_color = min(tns.colors, self.colors) >= 8

        # Determine location on screen

        xpos1, ypos1 = self.twin_beg
        xpos2, ypos2 = self.twin_end
        xpos, ypos = self.twin_loc

        absy = caddr1 // tns.maxcol
        if absy < ypos1 or absy >= ypos2:
            return

        gsx = caddr1 % tns.maxcol
        gex = (endpos - 1) % tns.maxcol
        if gex < xpos1 or gsx >= xpos2:
            return

        # Trim displayed characters, if needed

        if gsx < xpos1:
            caddr1 += xpos1 - gsx
            gsx = xpos2

        if gex >= xpos2:
            endpos -= gex - xpos2 + 1

        gsx += xpos
        absy += ypos

        # Determine attributes - get field attributes

        fattr = tns.plane_fa[faddr]
        f_display = tns.is_displayable_attr(fattr)

        if not f_display:
            clen = endpos - caddr1
            blanks = " " * clen
            if has_color:
                attr = self.cv2attr[(0, 0)]
            else:
                attr = curses.A_INVIS  # ?

            self.__tty_write(absy, gsx, blanks, attr)
            return

        f_protected = tns.is_protected_attr(fattr)
        f_intensified = tns.is_intensified_attr(fattr)
        f_normal = tns.is_normal_attr(fattr)

        f_eh = tns.plane_eh[faddr]
        f_fg = tns.plane_fg[faddr]
        f_bg = tns.plane_bg[faddr]

        # Determine attributes - get character attributes

        c_eh = tns.plane_eh[caddr1]
        c_fg = tns.plane_fg[caddr1]
        c_bg = tns.plane_bg[caddr1]

        # Determine attributes - combine attributes

        if c_eh:
            aeh = c_eh
        else:
            aeh = f_eh

        if c_fg:
            afg = c_fg
        else:
            afg = f_fg

        if c_bg:
            abg = c_bg
        else:
            abg = f_bg

        attr = 0

        if aeh == 0:  # Default
            pass

        elif aeh == 240:  # xF0 Normal
            attr |= curses.A_NORMAL

        elif aeh == 241:  # xF1 Blink
            attr |= curses.A_BLINK

        elif aeh == 242:  # xF2 Reverse Video
            attr |= curses.A_REVERSE

        elif aeh == 244:  # xF4 Underscore
            attr |= curses.A_UNDERLINE

        if afg == 0:
            if f_intensified and not f_protected:
                if tns.extended_color_mode():
                    afg = 247  # F7 White
                else:
                    afg = 242  # F2 Red

            elif f_normal and f_protected:
                if tns.extended_color_mode():
                    afg = 244  # F4 Green
                else:
                    afg = 245  # F5 Turquoise

            elif f_intensified and f_protected:
                afg = 247  # F7 White

        if afg == 0:
            afg = 244  # F4 Green

        if has_color:
            attr ^= self.cv2attr[(afg, abg)]

        # Write to screen

        if endpos == tns.buffer_size:
            text = tns.scrstr(caddr1, 0)
        else:
            text = tns.scrstr(caddr1, endpos)

        self.__tty_write(absy, gsx, text, attr)

    # Readonly properties

    @property
    def prog_mode(self):
        """Read-only boolean. True for prog. False for shell.
        """
        return self.__tty_mode != 0

    class Download():
        """
        A Download instance represents a file downloaded from
        the remote system.
        """
        def __del__(self):
            self.remove()

        def __init__(self, zti, tns):
            """
            Create a Download instance associated with the input
            Zti instance and Tnz instance.
            """
            # delete=False is really for Windows
            # in Windows, cannot do much with a file
            # until it is closed. So, does not help
            # to delete it when it is closed.
            if not zti.registered_atexit:
                zti.registered_atexit = True
                atexit.register(zti.atexit)

            self.start_time = time.time()
            self.end_time = None
            self.bytecnt = 0
            self.name = tns.name
            self.failed = False
            self.closed = False
            self.removed = False
            self.lastcmd = tns.lastcmd
            self.downloadaction = None
            self.actiontaken = False
            self.zti = zti
            self.tns = tns
            self.file = tempfile.NamedTemporaryFile(delete=False)
            zti.downloads.append(self)

            lastcmd = ""
            lastcmd = self.lastcmd
            if (((lastcmd.lower().startswith(".ztiv ") or
                  lastcmd.lower().startswith(".ztie ")) and
                 rexx.words(lastcmd) > 1)):
                self.downloadaction = " ".join([
                    rexx.subword(lastcmd, 2), self.file.name])

        # Methods

        def close(self):
            if self.end_time is None:
                self.end_time = time.time()

            if not self.closed:
                self.closed = True
                self.tns = None
                self.file.close()
                zti = self.zti
                if zti and not zti.downloadaction:
                    if self.downloadaction:
                        zti.downloadaction = True

        def error(self):
            self.failed = True
            self.close()

        def flush(self):
            self.file.flush()

        def read(self, length):
            return self.file.read(length)

        def remove(self):
            self.close()

            if not self.removed:
                try:
                    os.remove(self.file.name)

                except PermissionError:
                    traceback.print_exc()

                except FileNotFoundError:
                    self.removed = True

                else:
                    self.removed = True

            if self.removed and self.zti:
                zti = self.zti
                self.zti = None
                try:
                    zti.downloads.remove(self)
                except ValueError:
                    pass

        def start_upload(self):
            self.file = open(self.file.name, "rb")

        def write(self, data):
            self.file.write(data)
            self.bytecnt += len(data)

        # Private methods

        def __repr__(self):
            if self.failed:
                stat = "Failed"
            elif self.closed:
                stat = ""
            elif self.tns.seslost:
                self.failed = True
                self.close()
                stat = "Failed"
            else:
                stat = "Open"

            if self.downloadaction:
                actcmd = self.downloadaction
            else:
                actcmd = self.lastcmd

            if self.actiontaken:
                actdone = "+"
            else:
                actdone = "_"

            if self.end_time and not stat:
                total_time = self.end_time - self.start_time
                rate = self.bytecnt / total_time
                if rate < 1024:
                    stat = f"({rate} B/s)"
                elif rate < 10*1024*1024:
                    rate //= 1024
                    stat = f"({rate} KB/s)"
                else:
                    rate //= 1024*1024
                    stat = f"({rate} MB/s)"

            mtime = time.ctime(os.path.getmtime(self.file.name))
            return "  ".join((str(mtime),
                              self.file.name,
                              self.name,
                              actdone,
                              actcmd,
                              stat))

    # Internal data and other attributes

    _zti = None
    _stdscr = None


class _ZtiAbort(BaseException):
    pass


# Functions

def create():
    """Create zti instance.
    """
    if Zti._zti:
        return Zti._zti

    try:
        Zti._stdscr = curses.initscr()
    except curses.error:
        _logger.exception("initscr error")
        return None

    try:
        curses.cbreak()
    except curses.error:
        _logger.exception("cbreak error")
        return None
    finally:
        curses.endwin()

    return Zti()


def main():
    """Process zti command.
    """
    from argparse import ArgumentParser

    parser = ArgumentParser(
        prog="zti",
        description="Z Terminal Interface",
        add_help=True)
    if __version__:
        parser.add_argument("--version",
                            action="version",
                            version=f"%(prog)s {__version__}")

    parser.add_argument("--nolog",
                        action="store_true",
                        help="Do not set LOGDEST to zti.log")
    rcgroup = parser.add_mutually_exclusive_group()
    rcgroup.add_argument("--noztirc",
                         action="store_true",
                         help="Do not SOURCE .ztirc in home directory")
    rcgroup.add_argument("--rcfile",
                         metavar="rcfile",
                         default="~/.ztirc",
                         help="Filename to run using SOURCE")
    parser.add_argument("host", nargs="?",
                        help="hostname[:port] to connect/go to")
    args = parser.parse_args()

    if not args.nolog:
        ati.ati.logdest = "zti.log"

    zti = Zti()
    ati.ati.maxlostwarn = 0

    if not args.noztirc:
        try:
            zti.do_source(args.rcfile)
        except Exception:
            pass

    if args.host:
        zti.cmdqueue.append(" ".join(("goto", args.host)))
        zti.single_session = True

    if args.rcfile != "~/.ztirc":
        zti.single_session = True

    intro = """
Welcome to the Z terminal interface!
Enter the GOTO hostname command to get started and
use the Esc key to get back to this command prompt.
Use the HELP and HELP KEYS commands for more information.
"""
    if zti.plugins:
        intro = f"{intro}Installed plugins: {zti.plugins}\n"
    else:
        intro = f"{intro}No plugins installed.\n"

    zti.cmdloop(intro)


# Private data

_WAIT_NONE = 0
_WAIT_KEYLOCK = 1
_WAIT_SCREEN = 2
_WAIT_FOREVER = 3
_WAIT_GOTO = 4
_WAIT_DSR = 5
_WAIT_MORE = 6
_WAIT_HOLDING = 7
_WAIT_NOT_MORE = 8
_WAIT_NOT_HOLDING = 9

_osname = platform.system()
_logger = logging.getLogger("tnz.zti")

if __name__ == "__main__":
    main()
