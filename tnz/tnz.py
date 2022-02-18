"""TN3270 terminal class.

Low level APIs for telnet-3270 for Z tool and library.

Usage:
    from tnz import tnz

Environment variables used:
    SESSION_PS_SIZE
    TNZ_COLORS
    TNZ_LOGGING
    ZTI_SECLEVEL

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
import asyncio
import enum
import json
import logging
import os
import platform
import re
import ssl
import sys
from . import __version__

__author__ = "Neil Johnson"
_wait_event = None
_loop = None


class Tnz:
    """One instance for each terminal and the connection.

    Methods for actions taken at the terminal:
        attn                         ATTN
        enter                        ENTER
        clear                        CLEAR
        key_backspace                Backspace
        key_backtab                  Backtab
        key_curdown                  Down
        key_curleft                  Left
        key_curright                 Right
        key_curup                    Up
        key_data                     characters/string
        key_delete                   Delete
        key_end                      (End)
        key_eraseeof                 Erase EOF
        key_eraseinput               ERASE INPUT
        key_home                     Home
        key_insdata                  insert characters/string
        key_newline                  NL
        key_tab                      Tab
        key_wordl                    (Word Left)
        key_wordr                    (Word Right)
        pa2, pa2, pa3                PAx
        pfX (pf1, pf2, ... pf24)     PFxx

    Additional methods to enhance the terminal experience:
        paste_data                   multiline characters/string

    Characters in the terminal:
        scrstr                       Method to get characters/string

    Attributes in the terminal:
        plane_fa                     Field attributes
        plane_eh                     Extended highlighting
        plane_fg                     Forground color
        plane_bg                     Background color

    Various methods perform actions taken by the remote application.
    Use the wait method to wait for the remote application to request
    actions and for the instance to process them.

    The data in the 3270 terminal is located by an address. This may
    be different from other applications that use a row and column or
    an x position and a y position. In addition, vectors described
    using addresses typically wrap - for instance from address 2 to
    address 1 produces a vector start at address 2, continues to the
    end of the terminal, continues at the beginning of the terminal,
    and terminates at address 1.

    The send method and the send_* methods send data to the remote host.
    """

    def __init__(self, name=None):
        """Create a new Tnz object.
        """
        self.use_tn3270e = False
        self.lu_name = None
        try:
            self.colors = int(os.getenv("TNZ_COLORS", "768"))
        except ValueError:
            self.colors = 768

        self.__secure = False
        self.__host_verified = False
        self.__loop = None
        self.__connect_task = None
        self.__zti = None
        self.__waiting = False
        self.__wait_rv = None
        self._transport = None  # asyncio.Transport
        self.__rec = []
        self.__pndrec = b""
        self.__eor = False
        self.__tn3270e = False
        self.__work_buffer = b""
        self._binary_local = False
        self._binary_remote = False
        # file transfer
        self.file_appends = None  # File to write downloads to
        self.__indstemp = False
        self.__indsfile = None
        self.__indsisf = None
        self.__inds_rm = None
        self.__indsenc = None
        self.__indspend = b""
        self.ddmrecv = False  # allow host-initiated ind$file get
        self.ddmsend = False  # allow host-initiated ind$file put
        self.__ddmtdat = ""
        self.ddmdata = None
        self.ddmdict = {}
        self.__ddmdata = False
        self.__ddmopen = False
        self.__ddmrecnum = 0
        self.__ddmascii = False
        self.__ddmmsg = None
        self.lastcmd = None
        self.__ddmfile = None
        self.__ddmupload = False
        # session status
        self.updated = False  # character buffer updated
        self.seslost = False  # session/connection lost

        # readlines
        self.readlines = None
        self.readlines_pa2 = True
        self.__readlines_row = 0
        self.__readlines_maxrow = 0

        self.__indstr = ""
        self.__indsdict = {}

        # ddm limits for inbound and outbound
        # 32767 is what HOD documents as the max
        # 0000 results in no data coming across
        # 2500 is what HOD sets by default
        # 2048 is what x3270 seems to set
        # Experience with TSO (under VICOM) has shown
        # that TSO IND$FILE may not handle 32767. It
        # seems like 32639 works. Is there a higher
        # number that also works? Is there something
        # that can be done to get 32767 to work?
        self._limin = 32639
        self._limout = 32767

        self._sendbuf = []
        self.local_do = []
        self.local_will = []
        self.local_wont = []
        self.local_dont = []
        self.remote_do = []
        self.remote_will = []
        self.remote_wont = []
        self.remote_dont = []

        self.bytes_sent = 0
        self.bytes_received = 0

        self.terminal_type = "IBM-DYNAMIC"  # will be ascii-encoded
        self.dmaxrow = 24  # 3270 Default Screen Size
        self.dmaxcol = 80  # 3270 Default Screen Size
        self.amaxrow = 24  # default Alternate number of rows
        self.amaxcol = 80  # default Alternate number of columns
        self.maxrow = self.dmaxrow  # default
        self.maxcol = self.dmaxcol  # default
        self.buffer_size = self.maxrow * self.maxcol

        self.curadd = 0  # cursor address

        self.bufadd = 0  # buffer address
        self.addr16bit = False

        self.aid = 0x60  # AID_NONE
        self.__reply_mode = 0  # Field mode
        self.__reply_cattrs = b""  # Character mode attrs of interest
        self.pwait = False  # PWAIT/TWAIT input inhibit
        # SYSTEM LOCK is associated with partition
        # SYSTEM LOCK can be reset by operator
        self.system_lock_wait = True  # System Lock input inhibit
        self.read_state = self.__ReadState.NORMAL
        self.inop = 0x06  # (RM) right initialization
        self.inpid = 0

        # Claim not capable of color
        # for situations where the terminal (tty)
        # is not used (i.e. the only view of the
        # 3270 screen is plain text only).
        self.capable_color = False
        self.__extended_color_mode = False

        buffer_size = self.buffer_size
        self.plane_dc = bytearray(buffer_size)  # data characters
        self.plane_fa = bytearray(buffer_size)  # field attributes
        self.plane_eh = bytearray(buffer_size)  # extended hilite
        self.plane_cs = bytearray(buffer_size)  # character set
        self.plane_fg = bytearray(buffer_size)  # foreground color
        self.plane_bg = bytearray(buffer_size)  # background color

        self.__pt_erase = False
        self.__proc_eh = 0  # extended highlighting
        self.__proc_cs = 0  # character set
        self.__proc_fg = 0  # foreground color
        self.__proc_bg = 0  # background color

        self.codec_info = {}
        self.encoding = "cp037"
        self.encoding = "cp037", 1

        self.alt = 0  # No support for GE (default)
        if sys.stdout.isatty():
            if str(sys.stdout.encoding).upper().startswith("UTF"):
                from . import cp310 as _
                self.encoding = "cp310", 1
        else:
            import locale
            preferredencoding = locale.getpreferredencoding()
            if preferredencoding.upper().startswith("UTF"):
                from . import cp310 as _
                self.encoding = "cp310", 1

        if name:
            self.name = name
        else:
            self.name = str(hash(self))

        self.need_shutdown = False

        # Begin "smart" detection of default properties

        try:
            self.encoding = "cp1047"
        except LookupError:
            pass

        if self.colors >= 8 and sys.stdin.isatty():
            # Claim capable of color for zti
            self.capable_color = True

        ps_size = os.getenv("SESSION_PS_SIZE", None)
        if ps_size:
            try:
                from . import _util
                asize = _util.session_ps_size(ps_size)
                self.amaxrow, self.amaxcol = asize
            except ValueError:
                self.__logger.exception("SESSION_PS_SIZE error")
                ps_size = None

        if ps_size is None:
            try:
                columns, lines = os.get_terminal_size()
                if lines >= 62 and columns >= 160:
                    self.amaxrow = 62
                    self.amaxcol = 160
                elif lines >= 27 and columns >= 132:
                    self.amaxrow = 27
                    self.amaxcol = 132
                elif lines >= 43:
                    self.amaxrow = 43
                    self.amaxcol = 80
                elif lines >= 32:
                    self.amaxrow = 32
                    self.amaxcol = 80
                else:
                    self.amaxrow = 24
                    self.amaxcol = 80
            except OSError:
                pass

    # Methods

    def address(self, address_bytes):
        """
        Return an integer buffer address for the input encoded byte
        string address.
        """
        if not isinstance(address_bytes, bytes):
            raise TypeError("input address_bytes must be bytes")

        if len(address_bytes) != 2:
            raise ValueError("input address_bytes must be 2 bytes")

        if not self.addr16bit and address_bytes[0] & 0x40:
            high_6bits = address_bytes[0] & 0x3f
            low_6bits = address_bytes[1] & 0x3f
            return high_6bits * 64 + low_6bits

        if not self.addr16bit and address_bytes[0] & 0x80:
            raise ValueError("reserved address mode")

        addr = int.from_bytes(address_bytes, "big")

        if self.addr16bit and addr > self.buffer_size:  # weird?
            self.addr16bit = False
            addr = self.address(address_bytes)
            self.addr16bit = True

        return addr

    def address_bytes(self, address):
        """
        Return an encoded byte string for the input integer buffer
        address.
        """
        if isinstance(address, bytes):
            raise TypeError("bytes not expected")

        value = address
        if not self.addr16bit and self.buffer_size <= 4095:
            _bit6 = bit6
            high_6bits, low_6bits = divmod(address, 64)
            value = _bit6(low_6bits) + 256 * _bit6(high_6bits)

        return value.to_bytes(2, byteorder="big")

    def attn(self):
        """Send 3270 ATTN
        """
        if self.__tn3270e:
            self.send_command(244)  # IP (Interrupt Process)
        else:
            self.send_command(243)  # BRK (Break)

    def clear(self, zti=None):
        """Send CLEAR
        """
        self.__extended_color_mode = False

        buffer_size = self.buffer_size
        self.plane_dc = bytearray(buffer_size)  # data characters
        self.plane_fa = bytearray(buffer_size)  # field attributes
        self.plane_eh = bytearray(buffer_size)  # extended hilite
        self.plane_cs = bytearray(buffer_size)  # character set
        self.plane_fg = bytearray(buffer_size)  # foreground color
        self.plane_bg = bytearray(buffer_size)  # background color

        self.curadd = 0  # cursor address

        if zti:
            zti.erase(self)

        self.updated = True

        return self.key_aid(0x6d)  # AID_CLEAR

    def close(self):
        """Close the connection.
        """
        transport = self._transport
        if transport:
            self._transport = None
            transport.abort()

    def connect(self, host=None, port=None,
                secure=False, verifycert=True):
        """Connect to the host.
        """
        if self._transport:
            raise TnzError("Already connected")

        if host is None:
            host = "127.0.0.1"  # default host

        if port is None:
            if secure is False:
                port = 23  # default insecure port
            else:
                port = 992  # default port

        self.__secure = False
        self.__host_verified = False

        class _TnzProtocol(asyncio.BaseProtocol):
            @staticmethod
            def connection_made(transport):
                self._transport = transport
                self.need_shutdown = True
                self.seslost = False

            @staticmethod
            def connection_lost(exc):
                if not self.seslost:
                    if exc:
                        self.seslost = (type(exc), exc, None)
                    else:
                        self.seslost = True

                _wait_event.set()

            @staticmethod
            def data_received(data):
                """Handle received data
                """
                self._data_received(data)

            @staticmethod
            def eof_received():
                """Handle EOF
                """
                self._log_warn("eof_received()")

            @staticmethod
            def pause_writing():
                """Handle pause writing
                """
                self._log_warn("pause_writing")

            @staticmethod
            def resume_writing():
                """Handle resume writing
                """
                self._log_warn("resume_writing")

        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if os.getenv("ZTI_SECLEVEL", "2") == "1":
                context.set_ciphers("DEFAULT@SECLEVEL=1")

            if verifycert:
                context.load_verify_locations("ibm-cacerts.pem")
                self.__host_verified = True  # ? too soon ?

            else:
                context.check_hostname = False  # insecure FIXME
                context.verify_mode = ssl.CERT_NONE  # insecure FIXME

        else:
            context = None

        coro = self.__connect(_TnzProtocol, host, port, context)
        loop = self.__get_event_loop()
        task = loop.create_task(coro)
        self.__connect_task = task

    def ddm_in_progress(self):
        """Return bool indicating if ddm is in progress.
        """
        return self.__ddmopen

    def download(self):
        """Return current Download (or None).
        """
        if not self.__indstemp:
            return None

        return self.__indsfile

    def enter(self, text=None, zti=None):
        """Send ENTER
        """
        if text:
            self.key_data(text, zti=zti)

        return self.key_aid(0x7d)  # AID_ENTER

    def extended_color_mode(self):
        """Return bool indicating if screen using extended colors.
        """
        return self.__extended_color_mode

    def field(self, address):
        """Return field address and attribute value as tuple.

        Get the field address and attribute value associated with the
        input address.
        """
        self.__check_address(address)
        search = self.__patn0l.search
        plane_fa = self.plane_fa
        endpos = address + 1
        mat = search(plane_fa, 0, endpos)
        if not mat:
            if endpos >= self.buffer_size:
                return -1, 0  # no fields

            mat = search(plane_fa, endpos)
            if not mat:
                return -1, 0  # no fields

        return mat.start(), mat[0][0]

    def fields(self, saddr=None, eaddr=None):
        """A generator of all fields as (address, attribute).
        """
        next_field = self.next_field
        if saddr is None:
            faddr, fattr = next_field(0, eaddr, offset=0)
            if eaddr is None:
                eaddr = faddr

        else:
            if eaddr is None:
                eaddr = saddr

            faddr, fattr = next_field(saddr, eaddr, offset=0)

        paddr = (eaddr - 1) % self.buffer_size  # stop before end
        while faddr >= 0:
            yield faddr, fattr
            if faddr == paddr:  # if stop because next is end
                return

            faddr, fattr = next_field(faddr, eaddr)

    def char_addrs(self, saddr=None, eaddr=None):
        """A generator of character data address ranges.
        """
        next_data = self.next_data
        if saddr is None:
            faddr, _ = self.next_field(0, eaddr, offset=-1)
            if faddr < 0:  # no fields
                faddr = 0

            start, end = next_data(faddr, eaddr)
            if eaddr is None:
                eaddr = start

        else:
            if eaddr is None:
                eaddr = saddr

            start, end = next_data(saddr, eaddr)

        while start >= 0:
            yield start, end
            if end == eaddr:
                return

            start, end = next_data(end, eaddr)

    def group_addrs(self, saddr, eaddr):
        """A generator of character data address range groups.

        A generator function that iterates through groups of
        characters. The characters in each group have all the same
        attributes. Each iteration returns a tuple with the start and
        end addresses.

        It is assumed that the input address(es) are valid for the
        current buffer size. They are in the range from 0 to
        buffer_size-1, inclusive.
        """
        buffer_size = self.buffer_size
        iterbs = self.__iterbs
        iterow = self.iterow
        plane_eh = self.plane_eh
        plane_fg = self.plane_fg
        plane_bg = self.plane_bg
        for saddr1, eaddr1 in self.char_addrs(saddr, eaddr):
            for rsp, rep in iterow(saddr1, eaddr1):
                ieh = iterbs(plane_eh, rsp, rep)
                ifg = iterbs(plane_fg, rsp, rep)
                ibg = iterbs(plane_bg, rsp, rep)
                tsa = rsp
                eeh = -1
                efg = -1
                ebg = -1
                while tsa != rep:
                    if tsa >= eeh:
                        eeh = next(ieh)

                    if tsa >= efg:
                        efg = next(ifg)

                    if tsa >= ebg:
                        ebg = next(ibg)

                    tea = min(eeh, efg, ebg)
                    if tea == buffer_size:
                        yield tsa, 0
                    else:
                        yield tsa, tea

                    tsa = tea

    def get_file(self, parms, filename, assist=True):
        """
        Get host file into local file.

        Would be nice, when the local system is Z, to transfer in
        binary. However, when transfer is done in binary, no
        information about the record format comes across. So, there
        is no knowledge if the host records were fixed-80 or variable
        length - so there is no indication as to where the line
        breaks should be.

        Transfering using the ASCII CRLF options seems to cause the
        host to convert between cp037 and iso8859-1. If something
        other than cp037 is expected/needed, support must be added to
        translate back from iso8859-1 to cp037. Then using the
        desired code page (e.g. cp1047) to translate to Unicode.
        """
        self.__log_info("get_file(%r, %r, assist=%r)",
                        filename, parms, assist)

        from . import rexx

        parmsu = parms.upper()
        opts = rexx.subword(parmsu, 2)
        if rexx.word(opts, 2).startswith("("):
            opts = rexx.subword(opts, 2)[1:]
        elif rexx.word(opts, 3).startswith("("):
            opts = rexx.subword(opts, 3)[1:]

        opts = " "+opts+" "

        encoding = None
        if assist:
            # See assist comment in put_file
            parmsu = parms.upper()
            preopt = rexx.subword(parms, 1, 1)
            opts = rexx.subword(parmsu, 2).split()
            paren = False
            if "(" in opts:
                i = opts.index("(")
                paren = True
                preopt = rexx.subword(parms, 1, i+1)
                opts = opts[i+1:]
            elif len(opts) > 1 and opts[1].startswith("("):
                opts[1] = opts[1][1:]
                paren = True
                preopt = rexx.subword(parms, 1, 2)
                opts = opts[1:]
            elif len(opts) > 2 and opts[2].startswith("("):
                opts[2] = opts[2][1:]
                paren = True
                preopt = rexx.subword(parms, 1, 3)
                opts = opts[2:]

            if paren and opts[-1].endswith(")"):
                opts[-1] = opts[-1][:-1].strip()
                if not opts[-1]:
                    opts.pop()

            if ("ASCII" in opts) and ("CRLF" in opts):
                encoding = self.encoding
                parms = [preopt]
                if paren:
                    parms.append("(")

                opts.remove("ASCII")
                parms.extend(opts)
                parms = " ".join(parms)
                opts = " "+" ".join(opts)+" "
                self.__log_debug("parms=%r", parms)

        self.__ddmmsg = None

        try:
            self.__indsenc = encoding
            if encoding:
                if " APPEND " in opts:
                    mode = "a"
                else:
                    mode = "w"

                enc = "UTF-8"  # avoid encoding errors
            else:
                if " APPEND " in opts:
                    mode = "ab"
                else:
                    mode = "wb"

                enc = None

            with open(filename, mode, encoding=enc) as self.__indsfile:
                # do not enter IND$FILE until file is open
                # (avoids an inconstent state if error opening file)
                self.__log_debug("entering IND$FILE GET %s", parms)
                self.enter("IND$FILE GET "+parms)

                while (not self.__ddmmsg and not self.seslost):
                    self.wait(3)  # query reply, command acknowledge
        finally:
            self.__log_debug("clearing __indsfile")
            self.__indsfile = None

        self.__log_info("get_file: %s", self.__ddmmsg)

        return self.__ddmmsg

    def getpeername(self):
        """Return remote address to which socket is connected.
        """
        transport = self._transport
        if not transport:
            return "?", "?"

        return transport.get_extra_info("peername")

    def getsockettype(self):
        """Return type of socket.
        """
        transport = self._transport
        if not transport:
            return "?"

        return type(transport.get_extra_info("socket"))

    def is_pen_detectable(self, address):
        """
        Return True or False to indicate if the address is
        selector-pen detectable
        """
        _, fattr = self.field(address)
        return self.is_detectable_attr(fattr)

    def is_protected(self, address):
        """
        Return True or False to indicate if the address is protected
        """
        fa1, fattr = self.field(address)
        return (fa1 == address) or bool(fattr & 0x20)

    def is_unprotected(self):
        """
        Return True or False to indicate if all fields are
        unprotected
        """
        for _, fattr in self.fields():
            if self.is_protected_attr(fattr):
                return False

        return True

    def iterow(self, saddr, eaddr):
        """
        Iterate through rows of bytes in the input bytearray.

        Note that the inputs are addresses and the outputs are
        positions. In other words, the outputs for each iteration
        will always have the start less than the end and buffer_size
        is used when the vector goes to the end of the bytearray.
        """
        saddr1 = saddr
        if saddr >= eaddr:
            eaddr1 = self.buffer_size
        else:
            eaddr1 = eaddr

        maxcol = self.maxcol
        while saddr1 != eaddr1:
            row = saddr1 // maxcol
            tea = min(eaddr1, (row+1) * maxcol)
            yield saddr1, tea
            saddr1 = tea

        if saddr >= eaddr:
            saddr1 = 0
            while saddr1 != eaddr:
                row = saddr1 // maxcol
                tea = min(eaddr, (row+1) * maxcol)
                yield saddr1, tea
                saddr1 = tea

    def key_aid(self, aid):
        """Process an aid key.
        """
        if self.pwait:
            raise TnzError("PWAIT Input Inhibit")

        if self.system_lock_wait:
            raise TnzError("System Lock Input Inhibit")

        if self.read_state == self.__ReadState.RENTER:
            raise TnzError("Retry Enter State")

        self.inpid = 0  # Inbound Partition Identifier (INPID)
        self.inop = 0x06  # (RM) INOP = Read Modified

        if aid != 0x7f:  # not trigger action (AID_TRIGA)
            self.system_lock_wait = True  # System Lock Condition
            self.pwait = True  # Partition Wait Condition (PWAIT)

        self.read_state = self.__ReadState.RENTER  # Retry Enter State
        self.send_aid(aid)  # transmit data inbound

    def key_backspace(self, zti=None):
        """
        Process backspace key, which behaves like a cursor left
        followed by a delete as long as cursor is not on a field
        attribute nor is there a field attribute to the left.
        """
        self.__log_debug("  backspace")
        addr0 = self.curadd
        faddr, fattr = self.field(addr0)
        if faddr == addr0:  # if on field attribute
            return False

        if fattr & 0x20:  # if protected
            return False

        addr1 = (addr0 - 1) % self.buffer_size  # left
        if faddr == addr1:  # left is field attribute
            return False

        self.curadd = addr1
        self.key_delete(zti=zti)
        return True

    def key_backtab(self, zti=None):
        """Process backtab key.
        """
        self.__log_debug("  backtab")

        addr = self.curadd
        faddr, fav = self.field(addr)
        if faddr < 0:
            self.curadd = 0
            return

        buffer_size = self.buffer_size
        addrm1 = (addr-1) % buffer_size
        if faddr in (addr, addrm1):
            addr = (faddr-1) % buffer_size
            faddr, fav = self.field(addr)

        fa1 = faddr
        plane_fa = self.plane_fa
        field = self.field
        while True:
            if not fav & 0x20:  # if unprotected
                addr = (faddr+1) % buffer_size
                fav = plane_fa[addr]
                if fav == 0:
                    self.curadd = addr
                    return

            faddr = (faddr-1) % buffer_size
            faddr, fav = field(faddr)
            if faddr == fa1:
                self.curadd = 0
                return

    def key_curdown(self, zti=None):
        """Process cursor down key.
        """
        self.__log_debug("  curdown")
        addr = self.curadd
        addr = (addr + self.maxcol) % self.buffer_size
        self.curadd = addr

    def key_curleft(self, zti=None):
        """Process cursor left key.
        """
        self.__log_debug("  curleft")
        addr = self.curadd
        addr = (addr - 1) % self.buffer_size
        self.curadd = addr

    def key_curright(self, zti=None):
        """Process cursor right key.
        """
        self.__log_debug("  curright")
        addr = self.curadd
        addr = (addr+1) % self.buffer_size
        self.curadd = addr

    def key_curup(self, zti=None):
        """Process cursor up key.
        """
        self.__log_debug("  curup")
        addr = self.curadd
        addr = (addr - self.maxcol) % self.buffer_size
        self.curadd = addr

    def key_data(self, text, onerow=False, zti=None):
        """Process keyboard character data.
        """
        start = 0
        strlen = len(text)
        ypos = self.curadd // self.maxcol
        while start < strlen:
            elist = []
            for cii, codec in self.codec_info.items():
                try:
                    bstr, consumed = codec.encode(text[start:])

                except UnicodeEncodeError as exc:
                    elist.append(exc)
                    bstr = None
                    if exc.start:
                        end = start + exc.start
                        bstr, consumed = codec.encode(text[start:end])

                if bstr:
                    self.__key_bytes(bstr, cii, onerow, zti)
                    break

            else:
                self.__log_error("Could not encode: %r", elist)
                raise elist[0]

            start += consumed
            if onerow and self.curadd // self.maxcol != ypos:
                break

        return start

    def key_delete(self, zti=None):
        """Process delete key.
        """
        self.__log_debug("  delete")
        addr0 = self.curadd
        faddr, fattr = self.field(addr0)
        if faddr == addr0:  # if on field attribute
            return False

        if fattr & 0x20:  # if protected field
            return False

        if faddr < 0:  # if no fields
            addr3 = addr0

        else:  # else faddr is field address
            addr3, _ = self.next_field(addr0)
            self.plane_fa[faddr] = bit6(fattr | 1)  # Set MDT

        self.__log_debug("  delete %d %d %d", faddr, addr0, addr3)
        buffer_size = self.buffer_size
        addr1 = (addr0+1) % buffer_size  # address of source for copy
        addr2 = (addr3-1) % buffer_size  # address of last char in field
        if addr1 != addr3:
            self.ucba(self.plane_dc, addr0,
                      self.rcba(self.plane_dc, addr1, addr3))
            self.ucba(self.plane_eh, addr0,
                      self.rcba(self.plane_eh, addr1, addr3))
            self.ucba(self.plane_cs, addr0,
                      self.rcba(self.plane_cs, addr1, addr3))
            self.ucba(self.plane_fg, addr0,
                      self.rcba(self.plane_fg, addr1, addr3))
            self.ucba(self.plane_bg, addr0,
                      self.rcba(self.plane_bg, addr1, addr3))

        self.plane_dc[addr2] = 0
        self.plane_eh[addr2] = 0
        self.plane_cs[addr2] = 0
        self.plane_fg[addr2] = 0
        self.plane_bg[addr2] = 0

        if zti:
            zti.write(self, faddr, addr0, addr3)

        return True

    def key_end(self):
        """Process End key - go to end of text in field.

        End is not a 3270 key, but common on modern keyboard.

        Cursor will move onto a null character in the current field
        where the character to the left is
        not a null character and all characters to the right
        are null characters.

        If cursor is in an unprotected field and the field does
        not end in a null character, the cursor will be put on
        the last character in the field.

        If cursor is in a protected field and the field does not
        end in a null character, the cursor will be put on the
        field attribute of the next field.
        """
        self.__log_debug("  key_end")
        caddr = self.curadd
        faddr, fattr = self.field(caddr)
        if faddr == -1:  # no fields
            return

        buffer_size = self.buffer_size
        faddr1 = (faddr+1) % buffer_size
        eaddr, _ = self.next_field(caddr)
        if faddr1 == eaddr:  # 0-length field
            return

        field_dc = self.rcba(self.plane_dc, faddr1, eaddr)
        if field_dc[-1] == 0x40:  # blank
            offset = len(field_dc.rstrip(b"\x00\x40"))
        else:
            offset = len(field_dc.rstrip(b"\x00"))

        caddr = (faddr1+offset) % buffer_size
        if caddr == eaddr and not self.is_protected_attr(fattr):
            caddr = (caddr-1) % buffer_size

        self.curadd = caddr

    def key_eraseeof(self, zti=None):
        """Process eraseeof key.
        """
        self.__log_debug("  eraseeof")
        addr0 = self.curadd
        faddr, fattr = self.field(addr0)
        if faddr == addr0:  # if on field attribute
            return False

        if fattr & 0x20:  # if protected field
            return False

        if faddr < 0:
            addr2 = addr0
        else:
            addr2, _ = self.next_field(addr0)
            fattr = bit6(fattr | 1)  # Set MDT (Modified Data Tag)
            self.plane_fa[faddr] = fattr

        self.__erase(addr0, addr2)
        if zti:
            zti.write(self, faddr, addr0, addr2)

        return True

    def key_eraseinput(self, zti=None):
        """Process ERASE INPUT key.
        """
        self.__erase_input(0, 0, zti=zti)
        self._reset_mdt()
        self.key_home(zti=zti)

    def key_home(self, zti=None):
        """Process home key.
        """
        if self.is_protected(0):
            curadd = self.__tab(0)
        else:
            curadd = 0

        self.__log_debug(" home -> %r", curadd)
        self.curadd = curadd

    def key_ins_data(self, text, zti=None):
        """Process keyboard character data in insert mode.
        """
        self.__log_debug("  key_ins_data")

        if self.pwait:
            raise TnzError("PWAIT Input Inhibit")

        if self.system_lock_wait:
            raise TnzError("System Lock Input Inhibit")

        addr0 = self.curadd
        faddr, fattr = self.field(addr0)
        if faddr == addr0:  # if on field attribute
            return 0

        if fattr & 0x20:  # if protected field
            return 0

        buffer_size = self.buffer_size
        plane_dc = self.plane_dc
        plane_eh = self.plane_eh
        plane_cs = self.plane_cs
        plane_fg = self.plane_fg
        plane_bg = self.plane_bg

        if faddr < 0:
            addr2 = addr0
            datalen = buffer_size
        else:
            addr2, _ = self.next_field(addr0)
            if addr0 < addr2:
                datalen = addr2 - addr0
            else:
                datalen = buffer_size - addr0 + addr2

        if datalen < len(text):
            text = text[:datalen]

        inslen = 0
        i = (addr2 - 1) % buffer_size
        while inslen < len(text):
            dc_byte = plane_dc[i]
            if dc_byte not in (0, 0x40):  # not 0 or space
                break

            inslen += 1
            i = (i-1) % buffer_size

        if inslen <= 0:
            return 0

        text = text[:inslen]

        # copy existing data to the right

        addr1 = (addr0+inslen) % buffer_size  # copy target address
        addr3 = (i+1) % buffer_size  # copy source end address
        ucba = self.ucba
        rcba = self.rcba
        ucba(plane_dc, addr1, rcba(plane_dc, addr0, addr3))
        ucba(plane_eh, addr1, rcba(plane_eh, addr0, addr3))
        ucba(plane_cs, addr1, rcba(plane_cs, addr0, addr3))
        ucba(plane_fg, addr1, rcba(plane_fg, addr0, addr3))
        ucba(plane_bg, addr1, rcba(plane_bg, addr0, addr3))

        self.key_data(text)
        if zti:
            zti.write(self, faddr, addr0, addr2)
            zti.rewrite_cursor = True

        return len(text)

    def key_newline(self, zti=None):
        """Process newline key.
        """
        self.__log_debug("  newline")
        addr0 = self.curadd
        line = addr0 // self.maxcol  # current line
        addr1 = (line+1) * self.maxcol  # first col in next row
        buffer_size = self.buffer_size
        if self.field(0) == (-1, 0):  # if no fields
            self.curadd = addr1 % buffer_size
        else:
            addr1 = (addr1 - 1) % buffer_size  # last col current row
            self.curadd = addr1
            self.key_tab()

    def key_tab(self, zti=None):
        """Process tab key.
        """
        curadd = self.curadd
        self.curadd = self.__tab(curadd)
        self.__log_debug(" tab @ %r -> %r", curadd, self.curadd)

    def key_word_left(self):
        """Move cursor left to the previous word.
        """
        self.__log_debug("  key_word_left")
        addr1 = (self.curadd-1) % self.buffer_size
        text = self.scrstr(addr1, addr1)
        mat = re.search(r"(?<=\s)\S(?=[\S]*[\s]*\Z)", text)
        if mat:
            self.curadd = (addr1+mat.start()) % self.buffer_size

    def key_word_right(self):
        """Move cursor right to the next word.
        """
        self.__log_debug("  key_word_right")
        caddr = self.curadd
        text = self.scrstr(caddr, caddr)
        mat = re.search(r"(?<=\s)\S", text)
        if mat:
            self.curadd = (caddr+mat.start()) % self.buffer_size

    def next_data(self, saddr, eaddr=None):
        """Get the address range of the next field data.
        """
        self.__check_address(saddr)
        if eaddr is None:
            eaddr = saddr
        else:
            self.__check_address(eaddr)

        if saddr < eaddr:
            mat = self.__pat0s.search(self.plane_fa, saddr, eaddr)
            if mat:
                return mat.start(), mat.end()

            return -1, -1  # no fields

        pat0s = self.__pat0s
        plane_fa = self.plane_fa
        buffer_size = self.buffer_size
        mat = pat0s.search(plane_fa, saddr, buffer_size)
        if mat:
            start = mat.start()
            end = mat.end() % buffer_size
            if eaddr and not end:
                mat = pat0s.match(plane_fa, 0, eaddr)
                if mat:
                    return start, mat.end()

            return start, end

        if eaddr:
            mat = pat0s.search(plane_fa, 0, eaddr)
            if mat:
                return mat.start(), mat.end()

        return -1, -1  # no fields

    def next_field(self, saddr, eaddr=None, offset=1):
        """Get the address and attribute value of the next field.

        Get the address and attribute value associated with the next
        field relative to the input field address. The first location
        for searching is the address AFTER the input saddr. If
        eaddr is specified.
        """
        self.__check_address(saddr)
        buffer_size = self.buffer_size
        saddr = (saddr + offset) % buffer_size
        if eaddr is None:
            eaddr = saddr
        else:
            self.__check_address(eaddr)

        if saddr < eaddr:
            mat = self.__patn0.search(self.plane_fa, saddr, eaddr)
        else:
            search = self.__patn0.search
            plane_fa = self.plane_fa
            mat = search(plane_fa, saddr, buffer_size)
            if not mat and eaddr:
                mat = search(plane_fa, 0, eaddr)

        if not mat:
            return -1, 0  # no fields

        return mat.start(), mat[0][0]

    def pa1(self):
        """Send PA1
        """
        return self.key_aid(0x6c)  # AID_PA1

    def pa2(self):
        """Send PA2
        """
        return self.key_aid(0x6e)  # AID_PA2 (CNCL)

    def pa3(self):
        """Send PA3
        """
        return self.key_aid(0x6b)  # AID_PA3

    def paste_data(self, data, zti=None):
        """Process pasted character data.
        """
        if self.pwait:
            raise TnzError("PWAIT Input Inhibit")

        if self.system_lock_wait:
            raise TnzError("System Lock Input Inhibit")

        ca0 = self.curadd
        ypos, xpos = divmod(ca0, self.maxcol)
        chars_pasted = 0
        datal = data.splitlines()
        for lined in datal:
            if lined:
                self.set_cursor_position(ypos+1, xpos+1)
                rrv = self.key_data(lined, onerow=True, zti=zti)
                if rrv == 0:
                    break

                chars_pasted += rrv

            ypos += 1
            if ypos >= self.maxrow:
                break

        self.curadd = ca0
        return chars_pasted

    def pf1(self):
        """Send PF1
        """
        return self.key_aid(0xf1)  # AID_PF1

    def pf2(self):
        """Send PF2
        """
        return self.key_aid(0xf2)  # AID_PF2

    def pf3(self):
        """Send PF3
        """
        return self.key_aid(0xf3)  # AID_PF3

    def pf4(self):
        """Send PF4
        """
        return self.key_aid(0xf4)  # AID_PF4

    def pf5(self):
        """Send PF5
        """
        return self.key_aid(0xf5)  # AID_PF5

    def pf6(self):
        """Send PF6
        """
        return self.key_aid(0xf6)  # AID_PF6

    def pf7(self):
        """Send PF7
        """
        return self.key_aid(0xf7)  # AID_PF7

    def pf8(self):
        """Send PF8
        """
        return self.key_aid(0xf8)  # AID_PF8

    def pf9(self):
        """Send PF9
        """
        return self.key_aid(0xf9)  # AID_PF9

    def pf10(self):
        """Send PF10
        """
        return self.key_aid(0x7a)  # AID_PF10

    def pf11(self):
        """Send PF11
        """
        return self.key_aid(0x7b)  # AID_PF11

    def pf12(self):
        """Send PF12
        """
        return self.key_aid(0x7c)  # AID_PF12

    def pf13(self):
        """Send PF13
        """
        return self.key_aid(0xc1)  # AID_PF13

    def pf14(self):
        """Send PF14
        """
        return self.key_aid(0xc2)  # AID_PF14

    def pf15(self):
        """Send PF15
        """
        return self.key_aid(0xc3)  # AID_PF15

    def pf16(self):
        """Send PF16
        """
        return self.key_aid(0xc4)  # AID_PF16

    def pf17(self):
        """Send PF17
        """
        return self.key_aid(0xc5)  # AID_PF17

    def pf18(self):
        """Send PF18
        """
        return self.key_aid(0xc6)  # AID_PF18

    def pf19(self):
        """Send PF19
        """
        return self.key_aid(0xc7)  # AID_PF19

    def pf20(self):
        """Send PF20
        """
        return self.key_aid(0xc8)  # AID_PF20

    def pf21(self):
        """Send PF21
        """
        return self.key_aid(0xc9)  # AID_PF21

    def pf22(self):
        """Send PF22
        """
        return self.key_aid(0x4a)  # AID_PF22

    def pf23(self):
        """Send PF23
        """
        return self.key_aid(0x4b)  # AID_PF23

    def pf24(self):
        """Send PF24
        """
        return self.key_aid(0x4c)  # AID_PF24

    def put_file(self, filename, parms, assist=True):
        """Put host file from local file.
        """
        self.__log_info("put_file(%r, %r, assist=%r)",
                        filename, parms, assist)

        from . import rexx

        encoding = None
        if assist:
            # Seems that only reasonable way to transfer
            # a chararacter oriented in a host record/line
            # oriented "file" is to transfer it to the
            # host as ASCII. AND line separators MUST be
            # CRLF. Well, not quite. It seems like the host
            # translation table does strange things - like
            # translate 7c (ascii '|') to 6a (ebcdic 'B&'),
            # which is incorrect since the 'B&' character
            # is unicode 00A6. It SHOULD translate 7c to
            # 4f. To avoid bad translations, we will
            # transfer as BINARY CRLF - __next_get will
            # do the ascii->ebcdic translation. The strange
            # thing is that the CRLF still needs to be in
            # ascii. The CR is not a problem since it is
            # the same in both ascii and ebcdic. The LF
            # should NOT be a problem since ebcdic 0A is RPT.
            # What sort of file would have a RPT???
            parmsu = parms.upper()
            preopt = rexx.subword(parms, 1, 1)
            opts = rexx.subword(parmsu, 2).split()
            paren = False
            if "(" in opts:
                i = opts.index("(")
                paren = True
                preopt = rexx.subword(parms, 1, i+1)
                opts = opts[i+1:]
            elif len(opts) > 1 and opts[1].startswith("("):
                opts[1] = opts[1][1:]
                paren = True
                preopt = rexx.subword(parms, 1, 2)
                opts = opts[1:]
            elif len(opts) > 2 and opts[2].startswith("("):
                opts[2] = opts[2][1:]
                paren = True
                preopt = rexx.subword(parms, 1, 3)
                opts = opts[2:]

            if paren and opts[-1].endswith(")"):
                opts[-1] = opts[-1][:-1].strip()
                if not opts[-1]:
                    opts.pop()

            if ("ASCII" in opts) and ("CRLF" in opts):
                encoding = self.encoding
                parms = [preopt]
                if paren:
                    parms.append("(")

                opts.remove("ASCII")
                parms.extend(opts)
                parms = " ".join(parms)
                self.__log_debug("parms=%r", parms)

        self.__ddmmsg = None

        try:
            self.__indsenc = encoding
            if encoding:
                mode = "r"
            else:
                mode = "rb"

            self.__indspend = b""
            with open(filename, mode) as self.__indsfile:
                # do not enter IND$FILE until file is open
                # (avoids an inconstent state if error opening file)
                self.__log_debug("entering IND$FILE PUT %s", parms)
                self.enter("IND$FILE PUT "+parms)

                while (not self.__ddmmsg and not self.seslost):
                    self.wait(3)  # query reply, command acknowledge
        finally:
            self.__log_debug("clearing __indsfile")
            self.__indsfile = None

        self.__log_info("put_file: %s", self.__ddmmsg)

        return self.__ddmmsg

    def scrstr(self, saddr=0, eaddr=0, rstrip=None):
        """Return a string representation of the character buffer.
        """
        if rstrip is None:
            rstrip = (not saddr and not eaddr)

        rcba = self.rcba
        plane_dc = self.plane_dc
        plane_cs = self.plane_cs
        codec_info = self.codec_info
        trans_dc_to_c = self.__trans_dc_to_c
        strl = []
        addr0 = saddr
        for addr1 in self.__iterbs_addr(plane_cs, saddr, eaddr):
            bytes1 = rcba(plane_dc, addr0, addr1)
            bytes1 = bytes1.translate(trans_dc_to_c)
            cii = plane_cs[addr0]
            strl.append(codec_info[cii].decode(bytes1)[0])
            addr0 = addr1

        str1 = "".join(strl).translate(self.__trans_ords)
        if not rstrip:
            return str1

        maxcol = self.maxcol
        strl = []
        for i in range(0, self.buffer_size, maxcol):
            strl.append(str1[i:i+maxcol].rstrip())

        strl.append("")
        return "\n".join(strl)

    def send(self, data=None):
        """
        Send input byte array as data to the host. This method will
        escape IAC bytes.
        """
        if data:
            data = data.replace(b"\xff", b"\xff\xff")  # IAC -> IAC IAC
            self._sendbuf.append(data)

        transport = self._transport
        if not transport:
            self._log_warn("transport not available yet")
            return

        if transport.is_closing():
            self._log_warn("transport is closing")
            return

        data = b"".join(self._sendbuf)
        transport.write(data)
        self.bytes_sent += len(data)
        self._sendbuf.clear()

    def send_3270_data(self, value):
        """
        Send input byte array as a 3270-DATA record to the host.
        This method will escape IAC bytes and send EOR after the
        data.
        """
        append = self._sendbuf.append
        value = value.replace(b"\xff", b"\xff\xff")  # IAC -> IAC IAC
        if self.__tn3270e:
            append(bytes(5))  # 3270-DATA TN3270E Header

        append(value)
        append(b"\xff\xef")  # IAC EOR
        self.send()

    def send_aid(self, aid, short=None):
        """
        Process the sending of an AID (enter command). Used by
        methods with the name of the AID (e.g. enter).
        """
        self.__log_debug("o>> send_aid 0x%02x", aid)
        rec = bytes([aid])
        gotcmd = False
        reply_mode = self.__reply_mode
        reply_cattrs = self.__reply_cattrs

        if self.inpid:
            raise TnzError(f"PID={self.inpid} not implemented")

        if self.__indstr:
            self.__log_debug("Removing SPECIAL: %s", self.__indstr)
            self.__indstr = ""

        if short is None:
            short = 0x6b <= aid <= 0x6f  # PAx or CLEAR

        if short:
            self.aid = aid
            self.send_3270_data(rec)
            return

        baddr = self.address_bytes(self.curadd)
        self.__log_debug(" cursor %r", self.curadd)
        rec += baddr

        for (sa1, ea1) in self.char_addrs():
            fattr = self.plane_fa[sa1-1]
            if fattr & 1 == 0:  # if MDT is off
                continue

            if not gotcmd:
                if self.is_displayable_attr(fattr):
                    gotcmd = True
                    self.lastcmd = self.scrstr(sa1, ea1).strip()

            rec += b"\x11"  # SBA (Set Buffer Address)
            baddr = self.address_bytes(sa1)
            self.__log_debug(" SBA(x11) %r", sa1)
            rec += baddr

            blst = []
            append = blst.append
            if reply_mode in (0x00, 0x01):  # [Extended] Field mode
                self.__append_char_bytes(blst, sa1, ea1)

            elif reply_mode == 2:  # Character mode
                # TODO following needs to NOT append null characters
                # (nor their attributes)
                eh_attr = 0
                fg_attr = 0
                bg_attr = 0
                for sa2, ea2 in self.group_addrs(sa1, ea1):
                    eh1 = eh_attr
                    fg1 = fg_attr
                    bg1 = bg_attr
                    if b"\x41" in reply_cattrs:
                        eh1 = self.plane_eh[sa2]

                    if b"\x42" in reply_cattrs:
                        fg1 = self.plane_fg[sa2]

                    if b"\x45" in reply_cattrs:
                        bg1 = self.plane_bg[sa2]

                    if eh1 != eh_attr:
                        append(bytes([0x28, 0x41, eh1]))  # SA 41 eh

                    if fg1 != fg_attr:
                        append(bytes([0x28, 0x42, fg1]))  # SA 42 fg

                    if bg1 != bg_attr:
                        append(bytes([0x28, 0x45, bg1]))  # SA 45 bg

                    self.__append_char_bytes(blst, sa2, ea2)

            else:
                raise TnzError(f"bad reply mode {reply_mode}")

            data = b"".join(blst)
            data = data.replace(b"\x00", b"")  # remove nulls
            if len(data) != 0:
                self.__log_debug(" AID: %d byte(s) of data @ %r",
                                 len(data), sa1)
                rec += data

        self.aid = aid
        self.send_3270_data(rec)

    def send_command(self, code):
        """Send telnet command to the host.

        Send a single-byte telnet command to the remote.

        Supported commands:
            NAME               CODE  MEANING
            NOP                241   No operation.
            Data Mark          242   The data stream portion of a Synch.
            Break              243   NVT character BRK.
            Interrupt Process  244   The function IP.
            Abort output       245   The function AO.
            Are You There      246   The function AYT.
            Erase character    247   The function EC.
            Erase Line         248   The function EL.
            Go ahead           249   The GA signal.

        See other methods for other commands:
            NAME               METHOD
            EOR                send_rec()
            SE                 send_sub()
            SB                 send_sub()
            WILL               send_will()
            WON'T              send_wont()
            DO                 send_do()
            DON'T              send_dont()
        """
        if not 241 <= code <= 249:
            raise TnzError(f"Telnet command {code} not valid")

        self.__log_info("o>> IAC %d", code)
        self._sendbuf.append(bytes([0xff, code]))  # IAC code
        self.send()

    def send_do(self, opt, buffer=False):
        """Send DO to the host.
        """
        if opt == 0:  # TRANSMIT-BINARY
            self._binary_remote = True

        elif opt == 25:  # END-OF-RECORD
            self.__eor = True

        if opt not in self.local_do:
            self.local_do.append(opt)
            if opt in self.local_dont:
                self.local_dont.remove(opt)

        self.__log_info("o>> IAC DO %s", self.__tnon(opt))
        self._sendbuf.append(bytes([0xff, 0xfd, opt]))  # IAC DO opt
        if not buffer:
            self.send()

    def send_dont(self, opt, buffer=False):
        """Send DON'T to the host.
        """
        if opt == 0:
            self._binary_remote = False

        elif opt == 25:  # END-OF-RECORD
            self.__eor = False

        if opt not in self.local_dont:
            self.local_dont.append(opt)
            if opt in self.local_do:
                self.local_do.remove(opt)

        self.__log_info("o>> IAC DONT %s", self.__tnon(opt))
        self._sendbuf.append(bytes([0xff, 0xfe, opt]))
        if not buffer:
            self.send()

    def send_rec(self, value):
        """
        Send input byte array as a record to the host. This method
        will escape IAC bytes and send EOR after the data.
        """
        value = value.replace(b"\xff", b"\xff\xff")  # IAC -> IAC IAC
        append = self._sendbuf.append
        append(value)
        append(b"\xff\xef")  # IAC EOR
        self.send()

    def send_sub(self, value, buffer=False):
        """
        Send input subcommand data to the host. This method will
        bookend the data with IAC SB adn IAC SE.
        """
        value = value.replace(b"\xff", b"\xff\xff")  # IAC -> IAC IAC
        append = self._sendbuf.append
        append(b"\xff\xfa")  # IAC SB
        append(value)
        append(b"\xff\xf0")  # IAC SE
        if not buffer:
            self.send()

    def send_terminal_type(self, buffer=False):
        """Send the terminal type to the host.
        """
        self.__log_info("o>> TERMINAL-TYPE IS %s",
                        self.terminal_type)
        data = b"".join([b"\x18",  # TERMINAL-TYPE
                         b"\x00",  # IS
                         self.terminal_type.encode("ascii")])
        return self.send_sub(data, buffer=buffer)

    def send_will(self, opt, buffer=False):
        """Send WILL to the host.
        """
        if opt not in self.local_will:
            self.local_will.append(opt)
            if opt in self.local_wont:
                self.local_wont.remove(opt)

        self.__log_info("o>> IAC WILL %s", self.__tnon(opt))
        self._sendbuf.append(bytes([0xff, 0xfb, opt]))  # IAC WILL opt
        if not buffer:
            self.send()

    def send_wont(self, opt, buffer=False):
        """Send WON'T to the host.
        """
        if opt not in self.local_wont:
            self.local_wont.append(opt)
            if opt in self.local_will:
                self.local_will.remove(opt)

        self.__log_info("o>> IAC WONT %s", self.__tnon(opt))
        self._sendbuf.append(bytes([0xff, 0xfc, opt]))
        if not buffer:
            self.send()

    def set_cursor_address(self, address):
        """Set the cursor address to the input address.
        """
        self.__check_address(address)
        self.curadd = address

    def set_cursor_position(self, row, col):
        """Set the cursor address from the input row and column.

        First (row, col) is (1, 1).
        """
        maxrow = self.maxrow
        if not 0 < row <= maxrow:
            raise ValueError(f"{row} not in range 0-{maxrow}")

        maxcol = self.maxcol
        if not 0 < col <= maxcol:
            raise ValueError(f"{col} not in range 0-{maxcol}")

        self.curadd = ((row-1)*maxcol) + col - 1

    def shutdown(self):
        """Shut down the connection.
        """
        task = self.__connect_task
        if task:
            task.cancel()
            loop = self.__get_event_loop()
            if not loop.is_running():
                # skip if ANY loop is running?
                loop.run_until_complete(task)

        transport = self._transport
        if transport:
            self._transport = None
            # any way to handle need_shutdown?
            transport.abort()

    def start_readlines(self):
        """Initialize readlines.
        """
        self.readlines = []
        self.__readlines_row = 0
        self.__readlines_check()

    def upload(self, file):
        """Upload data from file-like object to remote server.
        """
        if not self.__ddmopen:
            raise ValueError("file transfer not in progress")

        if not self.__ddmupload:
            raise ValueError("download in progress")

        if self.__indsfile is not None:
            raise ValueError("file transfer in progress")

        self.__indsfile = file
        self.__next_get()

        data = self.__indsisf
        rec = b"\x88"  # SF (Structured Field AID)
        if not data:
            isf = b"\xd0\x46\x08"  # D04608 Get Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x22\x00"  # Error Code Get Past End of File
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Get Past End Of File send")
            self.__inds_rm = None
        else:
            self.__log_debug("DDM Data for Get send")
            self.__log_debug("SF: %r", data)
            rec += data
            self.__inds_rm = rec

        self.send_3270_data(rec)

        if data:
            # read BEFORE next ddm get
            # so file data transfer is in parallel with
            # network data transfer.
            self.__next_get()

    def uploading(self):
        """Return bool indicating if currently uploading.
        """
        if not self.__indstemp:
            return False

        return self.__indsfile

    def wait(self, timeout=None, zti=None, key=None):
        """Wait for event.

        Returns after timeout seconds or when data is received.
        """
        self.__log_debug("tnz.wait(%r, %r, %r)", timeout, zti, key)
        loop = self.__get_event_loop()
        wait_event = _wait_event
        if not wait_event and self.__connect_task:
            loop.stop()
            loop.run_forever()
            wait_event = _wait_event

        if not wait_event:
            self.__log_error("nothing to wait on")
            return True

        if self.seslost:
            self.__log_debug("tnz.wait setting timeout=0")
            timeout = 0

        if self.__waiting:
            raise TnzError("Already waiting")

        event_wait = wait_event.wait()
        if timeout is None:
            timeout_handle = None
        else:
            def callback():
                if not wait_event.is_set():
                    self.__wait_rv = False
                    wait_event.set()

            timeout_handle = loop.call_later(timeout, callback)

        try:
            self.__waiting = True
            if zti:
                self.__zti = zti
                self.ddmrecv = zti.ddmrecv  # host-initiated get
                self.ddmsend = zti.ddmsend  # host-initiated put

            self.__loop.run_until_complete(event_wait)
            if self.seslost:
                return True

            return self.__wait_rv

        finally:
            wait_event.clear()
            self.__wait_rv = None
            self.__waiting = False
            if zti:
                self.__zti = None
                self.ddmrecv = False
                self.ddmsend = False

            if timeout_handle:
                timeout_handle.cancel()

    def word_at(self, address):
        """Return the word at the input address.
        """
        fa1, _ = self.field(address)
        if fa1 == address:
            return ""

        if fa1 > 0:
            buffer_size = self.buffer_size
            fa1 = (fa1+1) % buffer_size
            fa2, _ = self.next_field(fa1)
            if fa1 < address:
                pos = address - fa1
            else:
                pos = address + buffer_size - fa1
        else:
            fa1 = 0
            fa2 = 0
            pos = address

        scr = self.scrstr(fa1, fa2)
        idx1 = scr.find(" ", pos)
        if idx1 == pos:
            return ""

        if idx1 < 0:
            idx1 = len(scr)

        idx2 = scr.rfind(" ", 0, pos)
        if idx2 < 0:
            idx2 = 0
        else:
            idx2 += 1

        return scr[idx2:idx1]

    # Internal methods

    def _data_received(self, buff):
        zti = self.__zti
        bcnt = len(buff)
        cmd = []
        buff = self.__work_buffer + buff[:bcnt]
        bcnt += len(self.__work_buffer)
        self.__work_buffer = b""

        b_start = 0
        b_start_data = 0
        b_last = bcnt - 1
        while b_start < bcnt:
            pos_iac = buff.find(0xff, b_start, bcnt)  # find IAC
            if pos_iac < 0:  # IAC not found
                self.__log_info("RECV: IAC not found")
                if self.__eor:
                    self.__pndrec += buff[b_start_data:bcnt]
                    self.__log_debug("RECV: %d bytes pending",
                                     len(self.__pndrec))
                else:
                    self.__log_error("Unexpected data: %r",
                                     buff[b_start, pos_iac])

                b_start = bcnt
                b_start_data = bcnt
                break

            if pos_iac >= b_last:
                # what follows IAC?
                break

            byte2 = buff[pos_iac+1]
            if byte2 == 239:  # if EOR (end of record for tn3270)
                data = self.__pndrec + buff[b_start_data:pos_iac]
                self.__pndrec = b""
                data = data.replace(b"\xff\xff", b"\xff")  # 0xff=IAC
                self.__rec.append(data)
                b_start = pos_iac + 2
                b_start_data = b_start
                continue

            if byte2 == 0xff:  # escaped 0xff (IAC) part of data
                b_start = pos_iac + 2
                continue

            if pos_iac != b_start_data:  # some data before IAC
                self._log_warn("RECV: Data interrupted by command")
                if self.__eor:
                    self.__pndrec += buff[b_start_data:pos_iac]
                    self._log_warn("RECV: %d bytes pending",
                                   len(self.__pndrec))
                else:
                    self.__log_error("Unexpected data: %r",
                                     buff[b_start_data, pos_iac])

            if 251 <= byte2 <= 254:  # //WILL or WON'T or DO or DON'T
                cmd_end = pos_iac + 3
                if cmd_end > bcnt:
                    self._log_warn("RECV: Command %02x incomplete",
                                   byte2)
                    b_start_data = bcnt
                    break

                cmd.append(buff[pos_iac:cmd_end])
                b_start = pos_iac + 3
                b_start_data = b_start
                continue

            if byte2 == 250:  # if SB (subcommand begin)
                pos_se = buff.find(b"\xff\xf0",  # IAC SE
                                   pos_iac+2, bcnt)
                if pos_se < 0:  # if subcommand end not found
                    self._log_warn("RECV: Subcommand %r incomplete",
                                   buff[pos_iac:bcnt])
                    b_start_data = bcnt
                    break

                cmd.append(buff[b_start:pos_se])
                b_start = pos_se+2
                b_start_data = b_start
                continue

            # single-byte command (IAC + one byte)

            b_start = pos_iac + 2
            b_start_data = b_start
            cmd.append(buff[pos_iac:b_start])

        if b_start < bcnt:
            rcnt = bcnt - b_start  # remaining bytes
            self._log_warn("RECV: %d byte(s) not processed", rcnt)
            self.__work_buffer = buff[b_start:bcnt]

        for cmd1 in cmd:
            self._process(cmd1)

        rec = self.__rec
        if self.__waiting and rec:
            self.__wait_rv = True
            _wait_event.set()

        while rec:
            rec_bytes = rec.pop(0)
            try:
                self._proc3270ds(rec_bytes, zti=zti)

            except TnzError:
                self.__logger.exception("3270 command/order error")
                self.__log_error("Record: %s", rec_bytes.hex())
                self.seslost = sys.exc_info()
                if zti:
                    raise

                import traceback
                traceback.print_exc()
                break

        return bcnt

    def _log_warn(self, *args, **kwargs):
        return self.__log(logging.WARN, *args, **kwargs)

    def _proc3270ds(self, b_str, zti=None):
        """Process input byte array as a 3270 data stream.
        """
        if not b_str:
            return

        data_type = 0
        # request_flag = 0
        response_flag = 0
        seq_number = 0

        if self.__tn3270e:
            header = b_str[:5]
            b_str = b_str[5:]
            self.__log_debug("TN3270E Header: %r", header)
            data_type = header[0]
            # request_flag = header[1]
            response_flag = header[2]
            seq_number = int.from_bytes(header[3:5], "big")
            if data_type == 0:  # 3270-DATA
                pass
            elif data_type == 1:  # SCS-DATA
                raise TnzError("DATA-TYPE SCS-DATA not implemented")
            elif data_type == 2:  # RESPONSE
                raise TnzError("DATA-TYPE RESPONSE not implemented")
            elif data_type == 3:  # BIND-IMAGE
                raise TnzError("DATA-TYPE BIND-IMAGE not implemented")
            elif data_type == 4:  # UNBIND
                raise TnzError("DATA-TYPE UNDINB not implemented")
            elif data_type == 5:  # NVT-DATA
                raise TnzError("DATA-TYPE NVT-DATA not implemented")
            elif data_type == 6:  # REQUEST
                raise TnzError("DATA-TYPE REQUEST not implemented")
            elif data_type == 7:  # SSCP-LU-DATA
                raise TnzError("DATA-TYPE SSCP-LU-DATA not implemented")
            else:
                raise TnzError(f"DATA-TYPE {data_type} not implemented")

        command_hex = hex(b_str[0])
        rtn_name = "_process_command_" + command_hex
        rtn = getattr(self, rtn_name, self._process_command_unknown)
        rtn(b_str, 0, len(b_str), zti=zti)

        if response_flag == 2:
            rsp = (b"\x02\x00" +  # DATA-TYPE=RESPONSE REQUEST-FLAG=0
                   b"\x00" +  # success (use x01 for error)
                   seq_number.to_bytes(2, byteorder="big") +
                   b"\x00")  # successful (Device End)
            self.__log_debug("Sending TN3270E response: %r", rsp)
            self.send_rec(rsp)

    def _process(self, data):
        """Process host data.
        """
        if data[:2] == b"\xff\xfd":  # IAC DO
            self.__log_info("i<< IAC DO %s", self.__tnon(data[2]))
            opt = data[2]

            if data[2] == 40:  # TN3270E
                if self.use_tn3270e:
                    self.send_will(40, buffer=True)
                else:
                    self.send_wont(40, buffer=True)

            elif data[2] == 0:  # TRANSMIT-BINARY
                if opt not in self.local_will:
                    self.send_will(0, buffer=True)

            elif data[2] == 24:  # TERMINAL-TYPE
                if opt not in self.local_will:
                    self.send_will(24, buffer=True)

            elif data[2] == 25:  # END-OF-RECORD
                if opt not in self.local_will:
                    self.send_will(25, buffer=True)

                if opt not in self.local_do:
                    self.send_do(25, buffer=True)

            elif data[2] == 46:  # START_TLS
                if not hasattr(self.__loop, "start_tls"):
                    self._log_warn("START_TLS unsupported.")
                    self._log_warn("Python >= 3.7 required")
                    self.send_wont(data[2], buffer=True)

                else:
                    if opt not in self.local_will:
                        self.send_will(data[2], buffer=True)

                    self.__log_info("o>> START_TLS FOLLOWS")
                    self.send_sub(b"\x2e\x01", buffer=True)

            else:
                # e.g. Timing mark (6)
                self.send_wont(data[2], buffer=True)

            if opt not in self.remote_do:
                self.remote_do.append(opt)
                if opt in self.remote_dont:
                    self.remote_dont.remove(opt)

        elif data[:2] == b"\xff\xfe":  # //IAC DON'T
            self.__log_info("i<< IAC DONT "+self.__tnon(data[2]))

            opt = data[2]
            if opt not in self.remote_dont:
                self.remote_dont.append(opt)
                if opt in self.remote_do:
                    self.remote_do.remove(opt)

            if opt not in (0, 25):  # END-OF_RECORD nor TRANSMIT-BINARY
                if opt not in self.local_wont:
                    self.send_wont(data[2], buffer=True)

        elif data[:2] == b"\xff\xfb":  # IAC WILL
            self.__log_info("i<< IAC WILL %s", self.__tnon(data[2]))

            # requesting permission
            # or confirming request
            if data[2] == 0 and not self._binary_remote:
                # requesting permission
                # confirm/grant permission
                self.send_do(0, buffer=True)

            opt = data[2]
            if opt not in self.remote_will:
                self.remote_will.append(opt)
                if opt in self.remote_wont:
                    self.remote_wont.remove(opt)

        elif data[:2] == b"\xff\xfc":  # //IAC WON'T
            self.__log_info("i<< IAC WONT %s", self.__tnon(data[2]))

            opt = data[2]
            if opt not in self.remote_wont:
                self.remote_wont.append(opt)
                if opt in self.remote_will:
                    self.remote_will.remove(opt)

        elif data[:2] == b"\xff\xef":  # IAC EOR
            pass

        elif data == b"\xff\xfa\x28\x08\x02":  # IAC SB ...
            self.__log_info("i<< TN3270E SEND DEVICE-TYPE")
            rsp = b"\x28\x02\x07"+self.terminal_type.encode("ascii")
            if self.lu_name:
                self.__log_info("o>> %s %s %s %s %s %s",
                                "TN3270E", "DEVICE-TYPE", "REQUEST",
                                self.terminal_type,
                                "CONNECT", self.lu_name)
                rsp += b"\x01"+self.lu_name.encode("ascii")
            else:
                self.__log_info("o>> %s %s %s %s",
                                "TN3270E", "DEVICE-TYPE", "REQUEST",
                                self.terminal_type)

            self.send_sub(rsp)

        elif data[:5] == b"\xff\xfa\x28\x02\x04":  # IAC SB ...
            i = data.find(b"\x01")  # find CONNECT
            if i < 0:
                device_type = data[5:].decode("ascii")
                device_name = ""
            else:
                device_type = data[5:i].decode("ascii")
                device_name = data[i+1:].decode("ascii")
                device_name = " CONNECT "+device_name

            self.__log_info("i<<" +
                            " TN3270E" +  # x28
                            " DEVICE-TYPE" +  # x02
                            " IS %s%s",  # x04
                            device_type, device_name)

            funb = b""
            funb = b"\x02"
            funl = []
            for fun in funb:
                if fun == 0:
                    funl.append("BIND-IMAGE")
                elif fun == 1:
                    funl.append("DATA-STREAM-CTL")
                elif fun == 2:
                    funl.append("RESPONSES")
                elif fun == 3:
                    funl.append("SCS-CTL-CODES")
                elif fun == 4:
                    funl.append("SYSREQ")
                else:
                    funl.append(repr(fun))

            self.__log_info("o>>" +
                            " TN3270E" +  # x28
                            " FUNCTIONS" +  # x03
                            " REQUEST %r",  # x07
                            funl)
            self.send_sub(b"\x28\x03\x07"+funb)

            self._binary_local = True
            self._binary_remote = True
            self.__eor = True
            self.__tn3270e = True

        elif data[:5] == b"\xff\xfa\x28\x03\x04":  # IAC SB ...
            funl = []
            for fun in data[5:]:
                if fun == 0:
                    funl.append("BIND-IMAGE")
                elif fun == 1:
                    funl.append("DATA-STREAM-CTL")
                elif fun == 2:
                    funl.append("RESPONSES")
                elif fun == 3:
                    funl.append("SCS-CTL-CODES")
                elif fun == 4:
                    funl.append("SYSREQ")
                else:
                    funl.append(repr(fun))

            self.__log_info("i<<" +
                            " TN3270E" +  # x28
                            " FUNCTIONS" +  # x03
                            " IS %r",  # x04
                            funl)

        elif data == b"\xff\xfa\x18\x01":  # IAC SB TERMINAL-TYPE SEND
            self.__log_info("i<< TERMINAL-TYPE SEND")
            self.send_terminal_type(buffer=True)

        elif data == b"\xff\xfa\x2e\x01":  # IAC SB ...
            self.__log_info("i<< START_TLS FOLLOWS")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            coro = self.__start_tls(context)
            task = self.__loop.create_task(coro)
            self.__connect_task = task

        elif data[0] == 255 and 241 <= data[1] <= 249:  # IAC command
            self.__log_info("i<< IAC %d", data[1])

        else:
            self._log_warn("i<< UNKNOWN! %s", data.hex())

        self.send()  # any any buffered data

    def _process_cmnd_0xf1(self, b_str, start, stop, pid, zti=None):
        """
        Process WSF Outbound 3270DS W (Write) partition command.
        Input is Outbound 3270DS structured field. Called by
        process_wsf_0x40.
        """
        self._process_w(b_str, start+4, stop, pid, zti=zti)

    def _process_cmnd_0xf5(self, b_str, start, stop, pid, zti=None):
        """
        Process WSF Outbound 3270DS EW (Erase/Write) partition
        command.  Input is Outbound 3270DS structured field. Called
        by process_wsf_0x40.
        """
        if pid:
            raise TnzError("Non-zero PID not implemented")

        self._process_ew(b_str, start+4, stop, zti=zti)

    def _process_cmnd_0x7e(self, b_str, start, stop, pid, zti=None):
        """
        Process WSF Outbound 3270DS EWA (Erase/Write Alternate)
        partition command. Input is Outbound 3270DS structured field.
        Called by process_wsf_0x40.
        """
        if pid:
            raise TnzError("Non-zero PID not implemented")

        self._process_ewa(b_str, start+4, stop, zti=zti)

    def _process_cmnd_0x6f(self, _, start, stop, pid, zti=None):
        """
        Process WSF Outbound 3270DS EAU (Erase All Unprotected)
        partition command. Input is Outbound 3270DS structured field.
        Called by process_wsf_0x40.
        """
        cmnd_len = stop - start
        if cmnd_len != 5:
            raise TnzError("EAU must be 5 bytes, got {cmnd_len}")

        self._process_eau(pid=pid, zti=zti)

    def _process_cmnd_unknown(self, b_str, start, stop, pid, zti=None):
        raise TnzError("Unknown CMND: "+hex(b_str[start+4]))

    def _process_command_0x6e(self, _, start, stop, zti=None):
        """
        Process RMA (Read Modified All) 3270 Data Stream Command.
        Input is 3270 data stream data.
        """
        cmnd_len = stop - start
        if cmnd_len != 1:
            raise TnzError("RMA must be 1 byte, got {cmnd_len}")

        self.__log_debug("Read Modified All (RMA)")
        self.read_state = self.__ReadState.NORMAL  # Normal Read state
        self.send_aid(self.aid, short=False)

    def _process_command_0xf1(self, b_str, start, stop, zti=None):
        """
        Process W (Write) 3270 Data Stream Command. Input is 3270
        data stream data.
        """
        return self._process_w(b_str, start, stop, zti=zti)

    def _process_command_0xf2(self, _, start, stop, zti=None):
        """
        Process RB (Read Buffer) 3270 Data Stream Command. Input is
        3270 data stream data.
        """
        cmnd_len = stop - start
        if cmnd_len != 1:
            raise TnzError("RB must be 1 byte, got {cmnd_len}")

        self.read_state = self.__ReadState.NORMAL  # Normal Read state
        self.__read_buffer()  # send reply

    def _process_command_0xf3(self, b_str, start, stop, zti=None):
        """
        Process WSF (Write Structured Field) 3270 Data Stream
        Command. Input is 3270 data stream data.
        """
        self.__log_debug("WSF")
        cmnd_len = stop - start
        if cmnd_len < 4:
            raise TnzError("WSF needs 4 bytes, got {cmnd_len}")

        from_bytes = int.from_bytes
        i = start + 1
        while i < stop:
            sfl = from_bytes(b_str[i:(i+2)], "big")  # length
            if sfl == 0:
                sfl = stop - i

            if sfl < 3:
                raise TnzError(f"Bad structured field length: {sfl}")

            if i + sfl > stop:
                self.__log_error("sfl=%s", sfl)
                self.__log_error("sf=%s", b_str[i:stop].hex())
                raise TnzError("WSF len and data inconsistent")

            wsf_hex = hex(b_str[i+2])
            rtn_name = "_process_wsf_" + wsf_hex
            rtn = getattr(self, rtn_name, self._process_wsf_unknown)
            rtn(b_str, i, i+sfl, zti=zti)
            i += sfl

    def _process_command_0xf5(self, b_str, start, stop, zti=None):
        """
        Process EW (Erase/Write) 3270 Data Stream Command. Input is
        3270 data stream data.
        """
        return self._process_ew(b_str, start, stop, zti=zti)

    def _process_command_0xf6(self, _, start, stop, zti=None):
        """
        Process RM (Read Modified) 3270 Data Stream Command. Input is
        3270 data stream data.
        """
        self.__log_debug("Read Modified (RM)")
        command_len = stop - start
        if command_len != 1:
            raise TnzError("RM must be 1 byte, got {command_len}")

        # TODO: if read_state is Retry Enter, do retry of INOP
        # TODO: if read_state is Retry Read, do retry of read

        if self.__inds_rm and self.__indsfile:
            # When using IND$FILE PUT in TSO, there have
            # been occurrances where a RM is requested
            # during the upload. This appears to be a
            # request to resend the last DDM DATA-FOR-GET.
            # Why are we forced to send the data twice?
            # Seems to occur only for larger amounts of
            # data. Perhaps the host did not have a large
            # enough buffer and it needs to be sent again
            # once the larger buffer is obtained?
            self.send_3270_data(self.__inds_rm)
        else:
            self.send_aid(self.aid)

    def _process_command_0x6f(self, b_str, start, stop, zti=None):
        """
        Process EAU (Erase All Unprotected) 3270 Data Stream Command.
        Input is 3270 data stream data.
        """
        command_len = stop - start
        if command_len != 1:
            raise TnzError("EAU must be 1 byte, got {command_len}")

        return self._process_eau(pid=0, zti=zti)

    def _process_command_0x7e(self, b_str, start, stop, zti=None):
        """
        Process EWA (Erase/Write Alternate) 3270 Data Stream Command.
        Input is 3270 data stream data.
        """
        return self._process_ewa(b_str, start, stop, zti=zti)

    _process_command_0x1 = _process_command_0xf1  # W
    _process_command_0x2 = _process_command_0xf2  # RB
    _process_command_0x5 = _process_command_0xf5  # EW
    _process_command_0x6 = _process_command_0xf6  # RM
    _process_command_0xd = _process_command_0x7e  # EWA
    _process_command_0xf = _process_command_0x6f  # EAU
    _process_command_0x11 = _process_command_0xf3  # WSF

    def _process_command_unknown(self, b_str, start, stop, zti=None):
        command_hex = hex(b_str[start])
        self.__log_error(b_str[start:stop].hex())
        self.__log_error(self.codec_info[0].
                         decode(b_str[start:stop], errors="ignore")[0])
        raise TnzError(f"Unknown command: {command_hex}")

    def _process_data(self, data, begidx, endidx, zti=None):
        """Process host character data.
        """
        if not isinstance(data, bytes):
            raise TypeError("input data must be bytes")

        datalen = endidx - begidx
        if datalen <= 0:
            # or better to just return?
            raise ValueError("no input data to process")

        if self.plane_fa[self.bufadd-1] == 124:
            spc = self.codec_info[0].decode(data[begidx:endidx])[0]
            self.__log_debug("SPECIAL DATA: %s", spc)
            self.__indstr += spc

        row = self.bufadd // self.maxcol
        if row < self.__readlines_row:
            self.__readlines_row = 0

        saddr = self.bufadd
        if zti:
            zti.write_data_prep(self, saddr, datalen)

        self.ucba(self.plane_dc, saddr, data, begidx, endidx)
        self.ucba(self.plane_fa, saddr, b"\x00"*datalen)
        self.ucba(self.plane_eh, saddr, [self.__proc_eh]*datalen)
        self.ucba(self.plane_cs, saddr, [self.__proc_cs]*datalen)
        self.ucba(self.plane_fg, saddr, [self.__proc_fg]*datalen)
        self.ucba(self.plane_bg, saddr, [self.__proc_bg]*datalen)

        oldadd = self.bufadd
        self.bufadd = (self.bufadd + datalen) % self.buffer_size

        self.__log_debug(" %d byte(s) of data @ %r -> %r",
                         datalen, oldadd, self.bufadd)
        if zti:
            # Use force=True to indicate that the data that was just
            # updated may have removed a field attribute. It also
            # indicates that the update did not change the cursor.
            zti.write_data(self, saddr, datalen, force=True)

    def _process_ddm_0xd00012(self, b_str, start, stop, zti=None):
        """Process DDM Open request

        Called by process_wsf_0xd0.
        """
        ddmupload = (b_str[start+14] == 1)
        if ddmupload:
            self.__log_debug("DDM Open Request (Upload)")
        else:
            self.__log_debug("DDM Open Request (Download)")

        ddm_len = stop - start
        if ddm_len < 35:
            raise TnzError("DDM-Open needs 35 bytes, got {ddm_len}")

        # b_str[start:stop]
        #  5:11 = 010601010403
        #         Fixed Parameter Changes File, etc.
        # 11:21 = 0A0A0000000011010100
        #         Functions Required Sequential Insert
        # 21:26 = 50055203F0
        #         Data Not Compressed
        # 26:28 = 0309
        #         File Nm. Header w/length
        # 26:30 = 08062704
        #         Record Size Header w/length
        # 28:35 = "FT:DATA"
        #         File Name for File Xfr. Data
        # 30:32 = llll
        #         Size (LIMIN-17)
        # 32:34 = 0309
        #         File Nm. Header w/length
        # 34:41 = "FT:DATA"
        #         File Name for File Xfr. Data

        if b_str[start+26] == 3:  # no size
            ft_bytes = b_str[start+28:(start+35)]
        elif b_str[start+26] == 8:  # has size
            ft_bytes = b_str[start+34:(start+41)]
        else:  # ?
            # Open Failed Exception
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x00\x08"  # D00008 Open Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x01\x00"  # Open Failed Exception
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Open Failed Exception send")
            self.send_3270_data(rec)
            self.__log_error("DDM Open unexpected")
            return

        ft_str = ft_bytes.decode("iso8859-1", errors="replace")
        self.__log_debug("ft: %s", ft_str)

        rec = b"\x88"  # SF (Structured Field AID)
        isf = b"\xd0\x00\x09"  # D00009 Open Acknowledgement
        isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
        rec += isf

        indstr = self.__indstr
        if not self.__indsfile and indstr:
            self.__indstr = ""
            try:
                indsdict = json.loads(indstr)

            except ValueError:
                self.__log_error("Not valid json: %r", indstr)

            else:
                self.__log_debug("indsdict: %r", indsdict)
                filename = indsdict.get("filename", None)
                enc = indsdict.get("encoding", None)
                cmd = indsdict.get("command", None)
                mode = "r" if ddmupload else "w"
                if enc == "binary":
                    mode += "b"
                    enc = None
                elif not enc:
                    enc = self.encoding

                if ddmupload and cmd and filename:
                    os.system(cmd)

                try:
                    if ddmupload and cmd and not filename:
                        self.__indsfile = os.popen(cmd)
                    elif filename:
                        self.__indsfile = open(filename, mode)

                except OSError:
                    self.__indstemp = False
                    # Open Request Error
                    rec = b"\x88"  # SF (Structured Field AID)
                    isf = b"\xd0\x00\x08"  # D00008 Open Error
                    isf += b"\x69\x04"  # Error Code Header
                    isf += b"\x01\x00"  # Open Failed Exception
                    isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
                    rec += isf
                    self.__log_debug("DDM Open Failed Exception send")
                    self.send_3270_data(rec)
                    self.__log_error("sf[14]=%r", b_str[start+14])
                    self.__log_error("DDM Open File failed")
                    return

                except Exception:
                    self.__indstemp = False
                    self.__logger.exception("open file error")

                else:
                    self.__indstemp = True
                    self.__indspend = b""
                    self.__indsenc = enc
                    self.__indsdict = {} if ddmupload else indsdict

        if (not self.__indsfile and
            ((not ddmupload and not self.ddmrecv) or
                (ddmupload and not self.ddmsend))):  # unexpected
            # Open Request Error
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x00\x08"  # D00008 Open Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x01\x00"  # Open Failed Exception
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Open Failed Exception send")
            self.send_3270_data(rec)
            self.__log_error("sf[14]=%r", b_str[start+14])
            self.__log_error("DDM Open unexpected")
            return

        self.__log_debug("DDM Open Ack send")
        self.send_3270_data(rec)  # send ddm open acknowledgement

        oldupload = self.__ddmupload
        self.__ddmupload = ddmupload
        self.__ddmdata = (ft_str == "FT:DATA")
        self.__ddmascii = (ft_str != "FT:DATA")
        self.__ddmopen = True
        self.__ddmrecnum = 0
        self.__inds_rm = None

        if self.__ddmfile and oldupload == ddmupload:
            self.__ddmfile = None

        if zti:  # zti for user interaction
            zti.rewrite_status = True
            if not self.__indsfile:
                if self.__ddmfile and ddmupload:
                    self.__indstemp = True
                    self.__indsenc = None
                    # same temp file back to remote
                    self.__ddmfile.start_upload()
                    self.__indsfile = self.__ddmfile
                    self.__ddmfile = None
                elif not ddmupload:
                    self.__indstemp = True
                    self.__indsenc = None
                    self.__indsfile = zti.Download(zti, self)

        if ddmupload and self.__indsfile:
            # Sequential Get: x"0A0A0001000000000100"
            # read BEFORE first ddm get
            # so file data transfer is in parallel with
            # network data transfer.
            if self.__indsfile:
                self.__indsisf = b""
                self.__next_get()
            else:
                self.__indsisf = None

        if not self.__indsfile and self.file_appends:
            self.__indsenc = None
            self.__indsfile = self.file_appends

    def _process_ddm_0xd04511(self, b_str, start, stop, zti=None):
        """Process DDM Set Cursor request

        Called by process_wsf_0xd0.
        """
        self.__log_debug("DDM Set Cursor Request")

        if self.__ddmopen and self.__indsfile is None:
            return  # upload file must be provided by user

        if not self.__indsfile or not self.__ddmopen:
            # Set Cursor Error
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x45\x08"  # D04508 Set Cursor Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x60\x00"  # Command Syntax Error
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Set Cursor Syntax Error send")
            self.send_3270_data(rec)
            self.__log_error("DDM Set Cursor unexpected")
            return

        if b_str[(start+5):(start+10)] != b"\x01\x05\x00\x06\x00":
            self.__log_error("Not 'Rel-Pos.' for Set Cursor")
            self.__log_error("sf=%r", b_str[start:stop])

        if b_str[(start+10):(start+15)] != b"\x09\x05\x01\x03\x00":
            self.__log_error("Not 'Next' for Set Cursor")
            self.__log_error("sf=%r", b_str[start:stop])

    def _process_ddm_0xd04611(self, b_str, start, stop, zti=None):
        """Process DDM Get request

        Called by process_wsf_0xd0.
        """
        self.__log_debug("DDM Get Request")

        if self.__ddmopen and self.__indsfile is None:
            return  # upload file must be provided by user

        if not self.__indsfile or not self.__ddmopen:
            # Get Request Error
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x46\x08"  # D04608 Get Request Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x60\x00"  # Command Syntax Error
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Get Syntax Error send")
            self.send_3270_data(rec)
            self.__log_error("DDM Get unexpected")
            return

        if b_str[(start+5):(start+16)] != b"\x01\x04\x00\x80":
            self.__log_error("No Feedback Requested for Get")
            self.__log_error("sf=%r", b_str[start:stop])

        data = self.__indsisf
        rec = b"\x88"  # SF (Structured Field AID)
        if not data:
            isf = b"\xd0\x46\x08"  # D04608 Get Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x22\x00"  # Error Code Get Past End of File
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Get Past End Of File send")
            self.__inds_rm = None
        else:
            self.__log_debug("DDM Data for Get send")
            self.__log_debug("SF: %r", data)
            rec += data
            self.__inds_rm = rec

        self.send_3270_data(rec)
        if zti:
            zti.rewrite_status = True

        if data:
            # read BEFORE next ddm get
            # so file data transfer is in parallel with
            # network data transfer.
            self.__next_get()

    def _process_ddm_0xd04711(self, _, __, ___, zti=None):
        """Process DDM Insert request

        Called by process_wsf_0xd0.
        """
        # b_str[i1:i2]
        #  5:10 = 0105008000
        #         Feedback Requested

        self.__log_debug("DDM Insert Request")

        if not self.__ddmopen:
            # Insert Request Error
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x47\x08"  # D04708 Insert Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x60\x00"  # Command Syntax Error
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Insert Syntax Error send")
            self.send_3270_data(rec)
            self.__log_error("DDM insert unexpected")

    def _process_ddm_0xd04704(self, b_str, start, stop, zti=None):
        """Process DDM Data To Insert request

        Called by process_wsf_0xd0.
        """
        self.__log_debug("DDM Data To Insert")
        ddm_len = stop - start
        if ddm_len < 11:
            raise TnzError("DDM-Open needs 11 bytes, got {ddm_len}")

        if not self.__ddmopen:
            # Insert Request Error
            rec = b"\x88"  # SF (Structured Field AID)
            isf = b"\xd0\x47\x08"  # D04708 Insert Error
            isf += b"\x69\x04"  # Error Code Header
            isf += b"\x60\x00"  # Command Syntax Error
            isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
            rec += isf
            self.__log_debug("DDM Data to Insert Syntax Error send")
            self.send_3270_data(rec)
            self.__log_error("DDM Data To Insert unexpected")
            return

        # b_str[start:stop]
        #  5:7  = C080
        #         Data Not Compressed
        #  7:8  = 61
        #         Begin Data Code
        #  8:10 = dddd
        #         Data Length plus 5
        # 10:   = data

        datalen = int.from_bytes(b_str[(start+8):(start+10)], "big")
        if datalen <= 5:
            # seems like this may happen when the host
            # does not like the limin or limout value
            raise TnzError("DDM data length is bad")

        datalen -= 5
        data = b_str[(start+10):(start+10+datalen)]
        if len(data) != datalen:
            raise TnzError("DDM data length is inconsistent")

        self.__log_debug("DDM Inserting %d byte(s)", len(data))

        if self.__ddmascii:
            data_str = data.decode("iso8859-1", errors="ignore")
        else:
            data_str = self.codec_info[0].decode(data,
                                                 errors="ignore")[0]

        if not self.__ddmdata:  # DDM MSG (not DATA)
            self.__log_debug("DDM MSG: %r", data_str)
            self.__ddmmsg = data_str

        self.__ddmrecnum += 1

        rec = b"\x88"  # SF (Structured Field AID)
        isf = b"\xd0\x47\x05"  # D04705 Data Acknowledgement
        isf += b"\x63\x06"  # record number header
        isf += self.__ddmrecnum.to_bytes(4, byteorder="big")
        isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
        rec += isf
        self.__log_debug("DDM Data Ack send")
        self.send_3270_data(rec)

        if self.__ddmdata:  # DDM DATA (not MSG)
            # do file data transfer in parallel with
            # network data transfer.
            if self.__indsenc:  # if decoding needed
                if data.endswith(b"\x1a"):
                    data = data[:-1]

                # IND$FILE uses CRLF to mark record
                # boundries. To be consistent with
                # universal newlines, we want to convert
                # CRLF to LF. There is also the
                # complexity of translating data that
                # is EBCDIC except for the ascii CRLF
                # bytes marking the records. And is it
                # possible that CRLF could be split
                # across two data blocks? And consider
                # that CR is the same byte value in both
                # ascii and EBCDIC. And consider that
                # EBCDIC translation often equates
                # EBCDIC NL with unicode LF.
                data = data.replace(b"\n", b"")
                data = data.decode(self.__indsenc)
                data = data.replace("\r", "\n")

            if self.__indsfile:  # if have file for saving
                self.__log_debug("ddm writing file")
                self.__indsfile.write(data)
                self.__log_debug("ddm wrote file")
                if zti:
                    zti.rewrite_status = True

            if isinstance(data, bytes) and (not self.__indsfile or
                                            self.__indstemp):
                # unsolicited
                if self.__ddmrecnum == 1:
                    self.__ddmtdat = ""
                    if self.__indsdict:
                        if data.endswith(b"\x1a"):
                            data = data[:-1]

                        data = data.decode("iso8859-1")
                        data = data.replace("\r\n", "\n")
                        self.__ddmtdat = data

                elif self.__ddmtdat:
                    self._log_warn("clearing ddmtdat for 2nd rec")

        else:  # DDM MSG (not DATA)
            self.__ddmopen = False
            self.__log_debug("DDM closed (got MSG)")

            if self.__indstemp:
                self.__indsfile.close()
                self.__ddmfile = self.__indsfile
                self.__indsfile = None
                self.__indstemp = False
                indsdict = self.__indsdict
                self.ddmdict = indsdict
                if indsdict:
                    self.__indsdict = {}
                    cmd = indsdict.get("command", None)
                    nowait = indsdict.get("async", None)
                    try:
                        if cmd and not nowait:
                            os.system(cmd)
                        elif cmd and nowait:
                            import subprocess
                            subprocess.Popen(cmd,
                                             stdin=None,
                                             stdout=None,
                                             stderr=None,
                                             close_fds=True)
                    except Exception:
                        self.__logger.exception("command error")

            else:
                if self.__indsfile is self.file_appends:
                    self.__indsfile.flush()
                else:
                    self.__indsfile.close()

                self.__indsfile = None

            self.ddmdata = self.__ddmtdat
            content_var = self.ddmdict.get("content_var")
            if content_var:
                self.ddmdict[content_var] = self.__ddmtdat
                del self.ddmdict["content_var"]

            self.__ddmtdat = ""

    def _process_ddm_0xd04112(self, _, __, ___, zti=None):
        """Process DDM Close request

        Called by process_wsf_0xd0.
        """
        self.__log_debug("DDM Close Request")

        # send close reply/acknowledgement
        rec = b"\x88"  # SF (Structured Field AID)
        isf = b"\xd0\x41\x09"  # D04109 Close Acknowledgement
        isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf
        rec += isf
        self.__log_debug("DDM Close Ack send")
        self.send_3270_data(rec)

    def _process_ddm_unknown(self, b_str, start, stop, zti=None):
        ddm_req = b_str[(start+2):min((start+5), stop)]
        raise TnzError(f"Bad DDM request: {ddm_req}")

    def _process_eau(self, pid=0, zti=None):
        """Perform host-initiated EAU (Erase All Unprotected)
        """
        self.__log_debug("Erase All Unprotected (EAU)")
        if pid:
            raise TnzError("Non-zero PID not implemented")

        self.__erase_input(0, 0, zti=zti)
        self._reset_mdt()
        self.key_home(zti=zti)
        self._restore_keyboard(zti=zti)

    def _process_ew(self, b_str, start, stop, zti=None):
        """Perform host-initiated EW (Erase/Write)
        """
        if stop - start <= 1:  # if no WCC
            return

        self.__log_debug("Erase/Write (EW) 0x%02x", b_str[start])

        self.lastcmd = ""
        self.__erase_reset(ipz=False, zti=zti)
        self._process_orders_data(b_str, start+2, stop, zti=zti)
        self._process_wcc(b_str[start+1], zti=zti)
        self.updated = True
        self.__readlines_row = 0
        self.__readlines_check()

    def _process_ewa(self, b_str, start, stop, zti=None):
        """Perform host-initiated EWA (Erase/Write Alternate)
        """
        if stop - start <= 1:  # if no WCC
            return

        self.__log_debug("Erase/Write Alternate (EWA) 0x%02x",
                         b_str[start])

        self.lastcmd = ""
        self.__erase_reset(ipz=True, zti=zti)
        self._process_orders_data(b_str, start+2, stop, zti=zti)
        self._process_wcc(b_str[start+1], zti=zti)
        self.updated = True
        self.__readlines_row = 0
        self.__readlines_check()

    def _process_order(self, order, start, stop, zti=None):
        """Process outbound data stream order.

        Call the appropriate method to process the input order.

        Args:
            order (bytes): outbound data stream orders and data
            start (int): index of first byte of order in input bytes
            stop (int): stop index indicating end of orders and data

        Returns:
            The index after the last byte process by the order.
        """
        rtn_name = "_process_order_" + hex(order[start])
        rtn = getattr(self, rtn_name, self._process_order_unknown)
        return rtn(order, start, stop, zti=zti)

    def _process_order_0x5(self, _, start, stop, zti=None):
        """Process Program Tab (PT) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 1:
            raise TnzError(f"PT requires 1 byte, got {order_len}")

        oldadd = self.bufadd
        if not self.plane_fa[oldadd] and self.__pt_erase:
            addr0, _ = self.next_field(oldadd, 0)
            if addr0 > 0:
                self.__pt_erase = False
            elif addr0 < 0:
                addr0 = 0

            self.__erase(oldadd, addr0)
            if zti:
                zti.write_data(self, oldadd, addr0)

        bufadd = self.__tab(oldadd, 0)
        self.bufadd = bufadd
        self.__log_debug(" Program Tab @ %r -> %r", oldadd, bufadd)
        return start + 1

    def _process_order_0x8(self, order, start, stop, zti=None):
        """Process Graphic Escape (GE) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 2:
            raise TnzError(f"GE requires 2 bytes, got {order_len}")

        self.__pt_erase = False
        ge_byte = order[start+1]
        addr1 = self.bufadd
        self.__log_debug(" Graphic Escape 0x%02x @ %r", ge_byte, addr1)

        if zti:
            zti.write_data_prep(self, addr1, 1)

        self.plane_dc[addr1] = ge_byte
        self.plane_fa[addr1] = 0
        self.plane_eh[addr1] = self.__proc_eh
        self.plane_cs[addr1] = 1
        self.plane_fg[addr1] = self.__proc_fg
        self.plane_bg[addr1] = self.__proc_bg

        self.bufadd = (addr1+1) % self.buffer_size

        if zti:
            # Use force=True to indicate that the data that was
            # just updated may have removed a field attribute. It
            # also indicates that the update did not change the
            # cursor.
            zti.write_data(self, addr1, 1, force=True)

        return start+2

    def _process_order_0x11(self, order, start, stop, zti=None):
        """Process Set Buffer Address (SBA) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 3:
            raise TnzError(f"SBA requires 3 bytes, got {order_len}")

        self.__pt_erase = False
        newaddr = self.address(order[(start+1):(start+3)])
        self.__log_debug(" Set Buffer Address %r", newaddr)
        self.__check_address(newaddr)
        self.bufadd = newaddr
        return start+3

    def _process_order_0x12(self, order, start, stop, zti=None):
        """Process Erase Unprotected to Address (EUA) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 3:
            raise TnzError(f"EUA requires 3 bytes, got {order_len}")

        self.__pt_erase = False
        addr = self.address(order[(start+1):(start+3)])
        self.__log_debug(" Erase Unprotected to Address (EUA) %r", addr)
        self.__check_address(addr)
        self.__erase_input(self.bufadd, addr, zti=zti)
        self.bufadd = addr
        return start+3

    def _process_order_0x13(self, _, start, stop, zti=None):
        """Process Insert Cursor (IC) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 1:
            raise TnzError(f"IC requires 1 byte, got {order_len}")

        self.__pt_erase = False
        bufadd = self.bufadd
        self.__log_debug(" Insert Cursor %r", bufadd)
        self.curadd = bufadd

        if zti:
            zti.rewrite_cursor = True

        return start+1

    def _process_order_0x1d(self, order, start, stop, zti=None):
        """Process Start Field (SF) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 1:
            raise TnzError(f"SF requires 1 bytes, got {order_len}")

        self.__pt_erase = False
        fattr = order[start+1]
        bufadd = self.bufadd
        self.__log_debug(" Start Field Value=x%02x @ %r", fattr, bufadd)
        self.plane_dc[bufadd] = 0
        self.plane_fa[bufadd] = bit6(fattr)
        self.plane_eh[bufadd] = 0
        self.plane_cs[bufadd] = 0
        self.plane_fg[bufadd] = 0
        self.plane_bg[bufadd] = 0
        self.bufadd = (bufadd+1) % self.buffer_size

        if zti:
            zti.field(self, bufadd)

        return start+2

    def _process_order_0x28(self, order, start, stop, zti=None):
        """Process Set Attribute (SA) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 3:
            raise TnzError(f"SA requires 3 bytes, got {order_len}")

        self.__pt_erase = False
        cat = order[start+1]
        cav = order[start+2]

        self.__log_debug(" Set Attribute Type=0x%x Value=0x%x",
                         cat, cav)

        if cat == 0x00:  # all character attributes
            self.__proc_eh = 0  # extended highlighting
            self.__proc_cs = 0  # character set
            self.__proc_fg = 0  # foreground color
            self.__proc_bg = 0  # background color

        elif cat == 0x41:  # extended highlighting
            self.__proc_eh = cav

        elif cat == 0x42:  # foreground color
            if not self.__extended_color_mode:
                if zti:
                    zti.extended_color(self)

                self.__extended_color_mode = True

            self.__proc_fg = cav  # foreground color

        elif cat == 0x43:  # character set
            self.__proc_cs = cav

        elif cat == 0x45:  # background color
            if not self.__extended_color_mode:
                if zti:
                    zti.extended_color(self)

                self.__extended_color_mode = True

            self.__proc_bg = cav  # background color

        else:
            raise TnzError(f"Bad character attribute type: {cat}")

        return start+3

    def _process_order_0x29(self, order, start, stop, zti=None):
        """Process Start Field Extended (SFE) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 1:
            raise TnzError(f"SFE requires 1 byte, got {order_len}")

        self.__pt_erase = False
        bufadd = self.bufadd
        self.plane_dc[bufadd] = 0
        self.plane_fa[bufadd] = 0x40  # bit6(0) default
        self.plane_eh[bufadd] = 0
        self.plane_cs[bufadd] = 0
        self.plane_fg[bufadd] = 0
        self.plane_bg[bufadd] = 0

        start, pairs = self.__set_attributes(bufadd,
                                             order, start + 1, zti=zti)
        self.__log_debug(" Start Field Extended Value=%r @ %r",
                         pairs, bufadd)
        self.bufadd = (bufadd+1) % self.buffer_size
        if zti:
            zti.field(self, bufadd)

        return start

    def _process_order_0x2c(self, order, start, stop, zti=None):
        """Process Modify Field (MF) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 1:
            raise TnzError(f"MF requires 1 byte, got {order_len}")

        self.__pt_erase = False
        bufadd = self.bufadd
        if not self.plane_fa[bufadd]:
            raise TnzTerminalError(f"Not a field: {bufadd}")

        i, pairs = self.__set_attributes(bufadd,
                                         order, start + 1, zti=zti)
        self.__log_debug(" Modify Field=%r @ %r",
                         pairs, bufadd)
        self.bufadd = (bufadd+1) % self.buffer_size
        if zti:
            zti.field(self, bufadd)

        return i

    def _process_order_0x3c(self, order, start, stop, zti=None):
        """Process Repeat to Address (RA) order.

        Called by process_order.
        """
        order_len = stop - start
        if order_len < 4:
            raise TnzError(f"RA requires 4 bytes, got {order_len}")

        self.__pt_erase = False
        stop_address = self.address(order[(start+1):(start+3)])
        cs_attr = self.__proc_cs
        getxt = ""
        return_value = start + 4
        data_byte = order[start+3]
        if data_byte == 0x08:  # if GE (Graphic Escape)
            cs_attr = 1
            data_byte = order[return_value]
            getxt = "GE "
            return_value += 1

        self.__log_debug(" Repeat to Address %r, %s0x%02x",
                         stop_address, getxt, data_byte)
        self.__check_address(stop_address)

        bufadd = self.bufadd
        if bufadd < stop_address:
            rlen = stop_address - bufadd
        elif stop_address < bufadd:
            rlen = stop_address + self.buffer_size - bufadd
        else:
            rlen = self.buffer_size

        if zti:
            zti.write_data_prep(self, bufadd, rlen)

        ucba = self.ucba
        ucba(self.plane_dc, bufadd, bytes([data_byte]*rlen))
        ucba(self.plane_fa, bufadd, b"\x00"*rlen)
        ucba(self.plane_eh, bufadd, [self.__proc_eh]*rlen)
        ucba(self.plane_cs, bufadd, bytes([cs_attr]*rlen))
        ucba(self.plane_fg, bufadd, [self.__proc_fg]*rlen)
        ucba(self.plane_bg, bufadd, [self.__proc_bg]*rlen)

        self.bufadd = stop_address

        if zti:
            # Use force=True to indicate that the data that was
            # just updated may have removed a field attribute. It
            # also indicates that the update did not change the
            # cursor.
            zti.write_data(self, bufadd, rlen, force=True)

        return return_value

    def _process_order_unknown(self, order, start, stop, zti=None):
        raise TnzError("Unknown order: "+hex(order[start]))

    def _process_orders_data(self, b_str, start, end, zti=None):
        """Process a byte array of a stream of orders and data.
        """
        self.bufadd = self.curadd
        self.__proc_eh = 0
        self.__proc_cs = 0
        self.__proc_fg = 0
        self.__proc_bg = 0
        self.__pt_erase = False
        patord = self.__patord
        process_data = self._process_data
        process_order = self._process_order
        while start < end:
            pat = patord.search(b_str, start, end)
            if not pat:
                process_data(b_str, start, end, zti=zti)
                return

            ordidx = pat.start()
            if start < ordidx:
                process_data(b_str, start, ordidx, zti=zti)
                self.__pt_erase = True

            start = process_order(b_str, ordidx, end, zti=zti)

    def _process_w(self, b_str, start, stop, pid=0, zti=None):
        """Perform host-initiated W (Write)
        """
        if stop - start <= 1:  # if no WCC
            return

        self.__log_debug("Write (W) 0x%02x", b_str[start])

        if pid:
            raise TnzError("Non-zero PID not implemented")

        self._process_wcc(b_str[start+1], for_mdt=True)
        self._process_orders_data(b_str, start+2, stop, zti=zti)
        self._process_wcc(b_str[start+1], zti=zti)
        self.updated = True

        self.__readlines_check()

    def _process_wcc(self, wcc, for_mdt=False, zti=None):
        """Process a WCC (Write Control Character).
        """
        self.__log_debug(" WCC 0x%02x for_mdt=%r", wcc, for_mdt)
        if for_mdt:
            if wcc & 0x01:  # if bit 7 is 1
                self.__log_debug("  WCC reset modified data bit = 1")
                self._reset_mdt()

        else:
            if wcc & 0x40:  # if bit 1 is 1
                self._reset_partition()

            if wcc & 0x08:  # if bit 4 is 1
                self.__log_error(" Start printer not implemented.")

            if wcc & 0x04:  # if bit 5 is 1
                self.__log_info("<--- ALARM --->")

            if wcc & 0x02:  # if bit 6 is 1
                self.__log_debug("  WCC keyboard restore bit = 1")
                self._restore_keyboard(zti=zti)

    def _process_wsf_0x1(self, b_str, start, stop, zti=None):
        """Process Read Partition structured field.

        Called by process_command_0xf3. Input is outbound structured
        field data.
        """
        self.__log_debug("Read Partition")
        pid = b_str[start+3]  # 00-7e (read ops) or ff (query ops)
        rp_type = b_str[start+4]

        if rp_type in (0x02, 0x03) and pid != 255:
            raise TnzTerminalError(f"pid={pid}, type={rp_type}")

        if self.read_state == self.__ReadState.RENTER:
            self.__log_error("Read Partition in Retry Enter state")
            # TODO: reject

        self.read_state = self.__ReadState.RREAD  # Retry Read state

        if rp_type == 0x02:  # Query
            self.inop = rp_type  # type of operation
            self.__query_reply()

        elif rp_type == 0x03:  # Query List
            self.inop = rp_type  # type of operation
            reqtype = b_str[start+5]
            qcode = b_str[start+6:stop]
            self.__query_reply(reqtype=reqtype, qcode=qcode)

        elif rp_type == 0x6e:  # Read Modified All (RMA)
            self.inpid = pid
            self.inop = rp_type  # type of operation
            self.send_aid(0x61, short=False)  # AID_READP

        elif rp_type == 0xf2:  # Read Buffer (RB)
            self.inpid = pid
            self.inop = rp_type  # type of operation
            self.aid = 0x61  # AID_READP
            self.__read_buffer()  # send reply

        elif rp_type == 0xf6:  # Read Modified (RM)
            self.inpid = pid
            self.inop = rp_type  # type of operation
            self.send_aid(0x61)  # AID_READP

        else:
            raise TnzTerminalError(f"Unknown type=0x{rp_type:02x}")

    def _process_wsf_0x3(self, b_str, start, stop, zti=None):
        """Process Erase/Reset structured field.

        Called by process_command_0xf3.
        Input is outbound structured field data.
        """
        self.__extended_color_mode = False

        sf_len = stop - start
        if sf_len < 4:
            raise TnzError(f"Erase/Reset needs 4 bytes, got {sf_len}")

        self.__erase_reset(ipz=bool(b_str[start+3] & 0x80), zti=zti)
        self.updated = True
        self.__readlines_row = 0
        self.__readlines_check()

    def _process_wsf_0x9(self, b_str, start, stop, zti=None):
        """Process Set Reply Mode structured field.

        Called by process_command_0xf3.
        Input is outbound structured field data.
        """
        pid = b_str[start+3]  # Partition identifier (OO through 7E)
        if pid:
            raise TnzError("Non-zero PID not implemented")

        mode = b_str[start+4]
        if mode <= 1:  # Field or Extended Field
            self.__reply_cattrs = b""

        elif mode == 2:  # Character mode
            self.__reply_cattrs = b_str[start+5:stop]

        else:
            raise TnzError(f"Bad reply mode: {mode}")

        self.__reply_mode = mode

    def _process_wsf_0x40(self, b_str, start, stop, zti=None):
        """Process Outbound 3270DS structured field.

        Called by process_command_0xf3.
        Input is outbound structured field data.
        """
        self.__log_debug("Outbound 3270DS")

        pid = b_str[start+3]  # Partition identifier (OO through 7E)

        rtn_name = "_process_cmnd_" + hex(b_str[start+4])
        rtn = getattr(self, rtn_name, self._process_cmnd_unknown)
        rtn(b_str, start, stop, pid=pid, zti=zti)

    def _process_wsf_0xd0(self, b_str, start, stop, zti=None):
        """Process DDM structured field.

        Called by process_command_0xf3.
        Input is outbound structured field data.

        See http://x3270.bgp.nu/SS-HCS12-1372-00.pdf

        Only DFT file transfers are supported. DFT file transfers use
        structured fields as opposed to other strange encodings.

        Outbound transmission = host to PC = download
        Inbound transmission = PC to host = upload

        Downloads use IND$FILE GET, which use DDM DOWNLOAD requests
        Uploads use IND$FILE PUT, which use DDM GET requests

        General idea of download:
            IND$FILE GET
            Read Partition Query from host
            Query Reply from PC
            Open for Download from host
            Open Acknowledgement from PC
            Download Data Buffer from host
            Data Acknowledgement from PC
            - repeat at Download Data Buffer -
            Close Request from host
            Close Acknowledgement from PC
            Open for Messages from host
            Open Acknowledgement from PC
            MSG : File Transfer Complete from host
            Data Acknowledgement from PC

        General idea of upload:
            IND$FILE PUT
            Read Partition Query from host
            Query Reply from PC
            Open for Upload from host
            Open Acknowledgement from PC
            Set Cursor And Get from host
            Upload Data Buffer from PC
            - repeat at Sest Cursor And Get -
            Get Past End of File Error from PC
            Close Request from host
            Close Reply from PC
            Open for Messages from host
            Open Acknowledgement from PC
            MSG : Transfer Complete from host
            Data Acknowledgement from PC
        """
        ddm_req = b_str[(start+2):(start+5)]
        rtn_name = "_process_ddm_0x" + ddm_req.hex()
        rtn = getattr(self, rtn_name, self._process_ddm_unknown)
        rtn(b_str, start, stop, zti=zti)

    def _process_wsf_unknown(self, b_str, start, stop, zti=None):
        raise TnzError(f"Bad Structured Field ID: {b_str[start+2]}")

    def _reset_mdt(self):
        """Reset the MDT (modified data tag) for all fields.
        """
        plane_fa = self.plane_fa
        _bit6 = bit6
        for faddr, fattr in self.fields():
            nattr = _bit6(fattr & (255 ^ 1))  # turn off MDT
            if fattr != nattr:
                plane_fa[faddr] = nattr

    def _reset_partition(self):
        """Perform host-initiated Reset Partition.
        """
        self.__reply_mode = 0  # Field mode
        self.__reply_cattrs = b""

    def _restore_keyboard(self, zti=None):
        """Perform host-initiated Restore Keyboard
        """
        self.aid = 0x60  # AID_NONE
        self.read_state = self.__ReadState.NORMAL
        self.system_lock_wait = False
        # Acknowledgment of an inbound transmission ?
        self.inop = 0x06  # (RM) INOP = Read Modified
        self.pwait = False

        if zti:
            zti.rewrite_keylock = True

    # Private methods

    def __addlines(self, keep_all=False):
        # hint: use keep_all=True before pressing pa2
        # to include blank lines at the bottom of the screen
        row = self.__readlines_row
        maxrow = self.__readlines_maxrow
        if row >= maxrow:
            return

        maxcol = self.maxcol
        saddr = row * maxcol
        eaddr = maxrow * maxcol
        rowcnt = (eaddr - saddr) // maxcol

        newstr = self.scrstr(saddr, eaddr)
        for i in range(0, eaddr-saddr, maxcol):
            self.readlines.append(newstr[i:i+maxcol].rstrip())

        if not keep_all:
            readlines = self.readlines
            while rowcnt:
                line = readlines.pop()
                if line:
                    readlines.append(line)
                    break

                rowcnt -= 1

        row += rowcnt
        self.__readlines_row = row
        if (keep_all or row >= maxrow) and self.readlines_pa2:
            if not self.__indsfile:  # if get/put not in progress
                self.pa2()

    def __append_char_bytes(self, blst, saddr, eaddr):
        """
        Append data character bytes to the input list (blst) starting
        at saddr and ending at (not including) eaddr. A GE (Graphic
        Escape) is appended when the character byte is from character
        set 1.
        """
        plane_dc = self.plane_dc
        rcba = self.rcba
        addr0 = saddr
        for addr1 in self.__iterbs_addr(self.plane_cs, saddr, eaddr):
            cii = self.plane_cs[addr0]
            if cii == 0:
                blst.append(rcba(plane_dc, addr0, addr1))

            elif cii == 1:
                for addr2 in self.__range_addr(addr0, addr1):
                    blst.append(b"\x08")  # GE (Graphic Escape)
                    blst.append(plane_dc[addr2:addr2+1])
            else:
                raise TnzError(f"cs={cii} not implemented")

            addr0 = addr1

    def __check_address(self, address):
        if not 0 <= address < self.buffer_size:
            raise TnzTerminalError(f"Invalid address: {address}")

    async def __connect(self, protocol, host, port, ssl_context):
        self.__log_debug("__connect(%r, %r, %r, %r)",
                         protocol, host, port, ssl_context)
        loop = asyncio.get_event_loop()
        if hasattr(asyncio, "current_task"):
            task = asyncio.current_task()
        else:
            task = asyncio.Task.current_task()

        # initialize using running loop implicitly

        global _wait_event
        if not _wait_event and loop is _loop:
            _wait_event = asyncio.Event()

        # connect

        try:
            await loop.create_connection(protocol, host, port,
                                         ssl=ssl_context)

        except asyncio.CancelledError:
            self.seslost = True
            _wait_event.set()
            return  # assume from shutdown/close

        except (OSError, UnicodeError):
            self.seslost = sys.exc_info()
            self.__logger.exception("create_connection error")
            _wait_event.set()
            return  # exception consumed

        finally:
            if self.__connect_task is task:
                self.__connect_task = None

    def __erase(self, saddr, eaddr):
        """Process erase function.

        Assume input range contains no fields.
        """
        size = eaddr - saddr
        if size <= 0:
            size += self.buffer_size

        zeros = b"\x00" * size
        ucba = self.ucba
        ucba(self.plane_dc, saddr, zeros)
        ucba(self.plane_eh, saddr, zeros)
        ucba(self.plane_cs, saddr, zeros)
        ucba(self.plane_fg, saddr, zeros)
        ucba(self.plane_bg, saddr, zeros)

    def __erase_input(self, saddr, eaddr, zti=None):
        self.__log_debug("  ERASE INPUT %d %d", saddr, eaddr)
        field = self.field
        plane_fa = self.plane_fa
        erase = self.__erase
        for sa1, ea1 in self.char_addrs(saddr, eaddr):
            if sa1 != saddr:
                faddr = sa1 - 1
                fav = plane_fa[faddr]
            else:
                faddr, fav = field(sa1)

            if fav & 0x20:  # if protected field
                continue

            erase(sa1, ea1)
            if zti:
                zti.write(self, faddr, sa1, ea1)

            self.updated = True

    def __erase_reset(self, ipz=False, zti=None):
        """Erase/Reset

        Resets the device to implicit partition state destroying
        all existing (implicit or explicit) partitions. Function
        creates an implicit partition zero with default partition
        characteristics and a default size if ips is False or of
        alternate size if ipz is True.
        """
        self.__extended_color_mode = False

        if ipz:
            self.maxrow = self.amaxrow
            self.maxcol = self.amaxcol
        else:
            self.maxrow = self.dmaxrow
            self.maxcol = self.dmaxcol

        buffer_size = self.maxrow * self.maxcol
        self.buffer_size = buffer_size
        self.plane_dc = bytearray(buffer_size)  # data characters
        self.plane_fa = bytearray(buffer_size)  # field attributes
        self.plane_eh = bytearray(buffer_size)  # extended hilite
        self.plane_cs = bytearray(buffer_size)  # character set
        self.plane_fg = bytearray(buffer_size)  # foreground color
        self.plane_bg = bytearray(buffer_size)  # background color

        self.addr16bit = buffer_size >= 16384
        self.curadd = 0

        if zti:
            zti.erase(self)

    def __get_event_loop(self):
        global _loop
        loop = self.__loop
        if not loop:
            loop = _loop

            if not loop:
                if platform.system() == "Windows":
                    # default policy does not support add_reader
                    pol = asyncio.WindowsSelectorEventLoopPolicy()
                    asyncio.set_event_loop_policy(pol)

                loop = asyncio.get_event_loop()

            self.__loop = loop

        if not _loop:
            _loop = loop

        return loop

    def __iterbs(self, bav, pos, endpos):
        """
        Iterate through sequences of same-value bytes in the input
        bytearray.

        Each iteration is represented by a single end position that
        can be used to describe a vector. For the first iteration,
        the start position of the vector is the input start address.
        For subsequent iterations, the start address is the position
        for the previos iteration.
        """
        if pos >= endpos:
            raise ValueError("pos >= endpos")

        for mat in self.__patbs.finditer(bav, pos, endpos):
            yield mat.end()

    def __iterbs_addr(self, bav, saddr=0, eaddr=None):
        """
        Iterate through sequences of same-value bytes in the input
        bytearray.

        Each iteration is represented by a single end address that
        can be used to describe a vector. For the first iteration,
        the start address of the vector is the input start address.
        For subsequent iterations, the start address is the address
        for the previous iteration.
        """
        if eaddr is None:
            eaddr = saddr

        if saddr >= eaddr:
            endpos = len(bav)
        else:
            endpos = eaddr

        finditer = self.__patbs.finditer
        for mat in finditer(bav, saddr, endpos):
            taddr = mat.end()
            if saddr >= eaddr and taddr >= endpos:
                if eaddr != 0 and bav[-1] == bav[0]:
                    break

                taddr = 0

            yield taddr

        if saddr >= eaddr and eaddr != 0:
            for mat in finditer(bav, 0, eaddr):
                yield mat.end()

    def __key_bytes(self, data, codec_index, onerow, zti):
        if self.pwait:
            raise TnzError("PWAIT Input Inhibit")

        if self.system_lock_wait:
            raise TnzError("System Lock Input Inhibit")

        buffer_size = self.buffer_size

        if onerow:
            cax = self.curadd // self.maxcol  # y
            cax += 1
            cax *= self.maxcol
            cax %= buffer_size
        else:
            cax = self.curadd

        chars_keyed = 0
        plane_bg = self.plane_bg
        plane_dc = self.plane_dc
        plane_cs = self.plane_cs
        plane_eh = self.plane_eh
        plane_fa = self.plane_fa
        plane_fg = self.plane_fg
        field = self.field
        next_field = self.next_field
        while True:
            if not data:
                return chars_keyed

            ca1 = self.curadd
            if plane_fa[ca1]:
                self.__log_debug(" data rejected, on field attribute")
                return chars_keyed  # on field attribute

            datalen = len(data)
            # ca2 = (ca1 + datalen) % buffer_size

            fa1, fattr = field(ca1)
            if fattr & 0x20:  # if protected
                self.__log_debug("Rejected - Field protected @ %r", fa1)
                return chars_keyed  # on protected field

            fa2, _ = next_field(ca1, cax)
            if fa2 < 0:
                fa2 = cax

            if ca1 < fa2:
                fieldlen = fa2 - ca1
            else:
                fieldlen = buffer_size + fa2 - ca1

            usedlen = min(fieldlen, datalen)
            zeros = b"\x00" * usedlen

            self.ucba(plane_dc, ca1, data[:usedlen])
            self.ucba(plane_eh, ca1, zeros)
            self.ucba(plane_cs, ca1, bytes([codec_index]) * usedlen)
            self.ucba(plane_fg, ca1, zeros)
            self.ucba(plane_bg, ca1, zeros)

            fattr = bit6(fattr | 1)  # Set MDT (Modified Data Tag)
            plane_fa[fa1] = fattr

            self.curadd = (self.curadd + usedlen) % buffer_size

            if zti:
                zti.write(self, fa1, ca1, self.curadd)
                zti.rewrite_cursor = True

            chars_keyed += usedlen
            data = data[usedlen:]
            if self.curadd == cax:
                return chars_keyed

            fattr = plane_fa[self.curadd]
            if fattr:  # if on field attribute
                if not fattr & 0x10:  # if alphanumeric field
                    self.curadd += 1
                    self.curadd %= buffer_size
                else:
                    self.key_tab()

    def __log(self, lvl, *args, **kwargs):
        self.__log_check()
        self.__logger.log(lvl, "%s "+args[0],
                          self.name, *args[1:], **kwargs)

    def __log_debug(self, *args, **kwargs):
        return self.__log(logging.DEBUG, *args, **kwargs)

    def __log_error(self, *args, **kwargs):
        return self.__log(logging.ERROR, *args, **kwargs)

    def __log_info(self, *args, **kwargs):
        return self.__log(logging.INFO, *args, **kwargs)

    def __next_get(self):
        """
        Set up for next get structure field to transfer data to the
        host for a put.
        """
        self.__ddmrecnum += 1

        # 2 bytes for the structure field length
        # ...plus...
        isf = b"\xd0\x46\x05"  # D04605 Data for Get
        isf += b"\x63\x06"  # Record Number Header
        isf += self.__ddmrecnum.to_bytes(4, byteorder="big")
        isf += b"\xc0\x80"  # Data Not Compressed
        isf += b"\x61"  # Begin Data Code
        # ...plus...
        # 2 bytes for length of data (plus 5)
        # and end with the actual data

        maxlen = self._limin - len(isf) - 2 - 2

        if self.__indsenc:
            if len(self.__indspend) >= maxlen:
                data = self.__indspend[:maxlen]
                self.__indspend = self.__indspend[maxlen:]
            else:
                rem = maxlen - len(self.__indspend)
                rem *= 4  # at most 4 bytes per
                data = self.__indsfile.read(rem)
                # IND$FILE takes CRLF to delimit record
                # boundries. Universal newlines enables
                # this by converting LF to CRLF. Consider
                # that data will be EBCDIC except for the
                # LF in the CRLF sequence - which will be
                # the byte value for EBCDIC RPT (ascii LF).
                # Note that CR is the same in both ascii
                # and EBCDIC. And condier that EBCDIC
                # translation often equates EBCDIC NL with
                # unicode LF.
                data = data.replace("\n", "\r")
                data = data.encode(self.__indsenc)
                data = data.replace(b"\r", b"\r\n")

                self.__indspend += data
                if len(self.__indspend) >= maxlen:
                    data = self.__indspend[:maxlen]
                    self.__indspend = self.__indspend[maxlen:]
                else:
                    data = self.__indspend
                    self.__indspend = b""
        else:
            data = self.__indsfile.read(maxlen)

        if not data:
            self.__log_debug("DDM NEXT none (no record %d)",
                             self.__ddmrecnum)
            self.__indsisf = b""
            return

        self.__log_debug("DDM NEXT record (%d) is %d byte(s)",
                         self.__ddmrecnum, len(data))

        isf += (len(data)+5).to_bytes(2, byteorder="big")
        isf += data
        isf = (len(isf)+2).to_bytes(2, byteorder="big")+isf

        self.__indsisf = isf

    def __query_reply(self, reqtype=None, qcode=None):
        """Perform query reply.
        """
        self.__log_debug("query reply %r %r", reqtype, qcode)
        rec = b"\x88"  # SF (Structured Field AID)

        # 80 Query Reply (Summary)
        sfb = b"\x80"  # Summary Query Reply
        sfb += b"\x80"  # Summary
        sfb += b"\x81"  # Usable Area
        sfb += b"\x85"  # Character Sets
        if self.capable_color:
            sfb += b"\x86"  # Color

        sfb += b"\x87"  # Highlight/Highlighting
        sfb += b"\x88"  # Reply Modes
        sfb += b"\x95"  # DDM (for file transfer)
        sfb += b"\xa6"  # Implicit Partitions

        # End of Summary
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 81 Query Reply (Usable Area)
        sfb = b"\x81"  # QCODE for the Usable Area Query Reply
        # Flags bit 0   - Reserved
        # (4)   bit 1   - Page printer
        #       bit 2   - Reserved
        #       bit 3   - HC A "hard copy" device
        #       bit 4-7 - ADDR Addressing modes
        #             0 - Reserved
        #             1 - 12/14-bit addressing allowed
        #             2 - Reserved
        #             3 - 12/14/16-bit addressing allowed
        #             F - Unmapped (no explicit address)
        sfb += b"\x01"  # Flags (4)
        # Flags bit 0   - VCP Variable cells supported
        # (5)   bit 1   - CHAR Non-matrix character
        #       bit 2   - CELLUNITS Value in bytes 6 & 7, 8 and 9; pels
        #       bit 3-7 - Reserved
        sfb += b"\x00"  # Flags (5)
        sfb += self.amaxcol.to_bytes(2, byteorder="big")  # W
        sfb += self.amaxrow.to_bytes(2, byteorder="big")  # H
        sfb += b"\x00"  # UNITS Pel measurement - inches
        # Horizontal distance between points as fraction ?
        sfb += (1).to_bytes(2, byteorder="big")  # Xr numerator
        sfb += (96).to_bytes(2, byteorder="big")  # Xr denominator
        # Vertical distance between points as fraction ?
        sfb += (1).to_bytes(2, byteorder="big")  # Yr numerator
        sfb += (96).to_bytes(2, byteorder="big")  # Yr denominator
        sfb += b"\x06"  # AW Number of X units in default cell?
        sfb += b"\x0c"  # AH Number of Y units in default cell?
        # BUFSZ onward may not be needed
        # Only set BUFSZ non-zero if paritions NOT supported
        # End of Usable Area
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # A6 Query Reply (Implicit Partitions)
        sfb = b"\xa6"  # Implicit Partition Query Reply
        sfb += b"\x00\x00"  # Flags (Reserved)

        # Implicit Partition Screen Sizes for Display Devices
        sfb += b"\x0b"  # Length of this self-defining parameter
        sfb += b"\x01"  # Implicit Partition Sizes
        sfb += b"\x00"  # Flags (Reserved)
        sfb += self.dmaxcol.to_bytes(2, byteorder="big")  # WD
        sfb += self.dmaxrow.to_bytes(2, byteorder="big")  # HD
        sfb += self.amaxcol.to_bytes(2, byteorder="big")  # WA
        sfb += self.amaxrow.to_bytes(2, byteorder="big")  # HA
        # End of Implicit Partitions
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 85 Query Reply (Character Sets)
        sfb = b"\x85"  # Character Sets Query Reply
        # Flags bit 0   - ALT Graphic Escape (GE) supported
        # (1)   bit 1   - MULTID Multiple LCIDs are supported
        #       bit 2   - LOADABLE LOAD PS are supported
        #       bit 3   - EXT LOAD PS EXTENDED is supported
        #       bit 4   - MS >1 size of character slot are supported
        #       bit 5   - CH2 2-byte coded character sets are supported
        #       bit 6   - GF CGCSGID is present
        #       bit 7   - Reserved
        if self.alt:
            sfb += b"\x82"  # Flags (1)
        else:
            sfb += b"\x02"  # Flags (1)
        # Flags bit 0   - Reserved
        # (2)   bit 1   - PSCS Load PS slot size match not required
        #       bit 2-7 - Reserved
        sfb += b"\x00"  # Flags (2)

        sfb += b"\x06"  # SDW Default character slot width
        sfb += b"\x0c"  # SDH Default character slot height

        sfb += b"\x00" * 4  # FORM Supported LOAD PS format types
        sfb += b"\x07"  # DL Length of each descriptor (one build below)

        # Character Set Descriptor 1

        # GA23-0059-4 describes SET as being at byte 1
        # does that mean byte 0 is reserved? or a misprint?
        sfb += b"\x00"  # SET Device specific Char Set ID (PS store No.)
        # Flags bit 0   - LOAD Loadable character set
        # (3)   bit 1   - TRIPLE Triple-plane character set
        #       bit 2   - CHAR Double-byte coded character set
        #       bit 3   - CB No LCID compare
        #       bit 4-7 - Reserved
        sfb += b"\x00"  # Flags (3)
        sfb += b"\x00"  # LCID Local character set ID (alias)
        # SW and SH only present if MS=1
        # sfb += b"\x00"  # SW Width of the character slots
        # sfb += b"\x00"  # SH Height of the character slots
        # SUBSN only present if CH2=1
        # sfb += b"\x00"  # SUBSN Starting subsection
        # sfb += b"\x00"  # SUBSN Ending subsection

        # CGCSGID made up of 2-byte chararacter set number followed
        # by 2-byte code page number.
        sfb += (self.cs_00).to_bytes(2, byteorder="big")
        sfb += (self.cp_00).to_bytes(2, byteorder="big")

        if self.alt:
            # Character Set Descriptor 2

            sfb += b"\x01"  # SET Device specific Char Set ID
            # Flags bit 0   - LOAD Loadable character set
            # (3)   bit 1   - TRIPLE Triple-plane character set
            #       bit 2   - CHAR Double-byte coded character set
            #       bit 3   - CB No LCID compare
            #       bit 4-7 - Reserved
            sfb += b"\x00"  # Flags (3)
            sfb += b"\xF1"  # LCID Local character set ID (alias)
            # SW and SH only present if MS=1
            # sfb += b"\x00"  # SW Width of the character slots
            # sfb += b"\x00"  # SH Height of the character slots
            # SUBSN only present if CH2=1
            # sfb += b"\x00"  # SUBSN Starting subsection
            # sfb += b"\x00"  # SUBSN Ending subsection

            # CGCSGID made up of 2-byte chararacter set number followed
            # by 2-byte code page number.
            sfb += (self.cs_01).to_bytes(2, byteorder="big")
            sfb += (self.cp_01).to_bytes(2, byteorder="big")

        # End of Character Sets)
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 87 Query Reply (Highlight)
        # from some testing done on 5/1/2019, it seems that
        # mvs "console switch" will not take place unless
        # blink highlighting is supported. Blink highlighting
        # is probably the kind of highlighting LEAST supported
        # by modern terminals. Since claiming support seems
        # to be required, clain support for all highlighting.
        # this was the case for a 62x160 screen size.
        # it did not seem to be the case for smaller screen sizes.
        sfb = b"\x87"  # QCODE for the Highlight Query Reply
        sfb += b"\x05"  # attribute-value/action pairs that follow
        sfb += b"\x00\xf0"  # value 00 -> action f0 = normal
        sfb += b"\xf1\xf1"  # value f1 -> action f1 = blink
        sfb += b"\xf2\xf2"  # value f2 -> action f2 = reverse
        sfb += b"\xf4\xf4"  # value f4 -> action f4 = underscore
        sfb += b"\xf8\xf8"  # value f8 -> action f8 = intensify
        # End of Highlight
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 88 Query Reply (Reply Modes)
        sfb = b"\x88"  # QCODE for the Reply Modes Query Reply
        sfb += b"\x00"  # Field Mode
        sfb += b"\x01"  # Extended Field Mode
        sfb += b"\x02"  # Character mode
        # End of Reply Modes
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 95 Query Reply (DDM)
        # (for file transfer)
        sfb = b"\x95"  # QCODE for the DDM Query Reply
        sfb += b"\x00\x00"  # Flags reserved
        sfb += self._limin.to_bytes(2, byteorder="big")  # LIMIN
        sfb += self._limout.to_bytes(2, byteorder="big")  # LIMOUT
        sfb += b"\x01"  # NSS Number of subsets supported
        sfb += b"\x01"  # DDMSS DDM subset identifier
        # End of DDM
        sfb = b"\x81"+sfb  # Query Reply
        sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
        rec += sfb

        # 86 Query Reply (Color)
        # Where are these color identifiers defined?
        #    F1  241   Blue
        #    F2  242   Red
        #    F3  243   Pink
        #    F4  244   Green
        #    F5  245   Turquoise
        #    F6  246   Yellow
        #    F7  247   White
        if self.capable_color:
            sfb = b"\x86"  # QCODE for the Color Query Reply
            sfb += b"\x00"  # flags (none defined for terminal)
            sfb += b"\x08"  # NP number of CAV/COLOR pairs
            sfb += b"\x00\xf4"  # Default -> Green
            sfb += b"\xf1\xf1"  # F1 -> Blue
            sfb += b"\xf2\xf2"  # F2 -> Red
            sfb += b"\xf3\xf3"  # F3 -> Pink
            sfb += b"\xf4\xf4"  # F4 -> Green
            sfb += b"\xf5\xf5"  # F5 -> Turquoise
            sfb += b"\xf6\xf6"  # F6 -> Yellow
            sfb += b"\xf7\xf7"  # F7 -> White?
            # End of Highlight
            sfb = b"\x81"+sfb  # Query Reply
            sfb = (len(sfb)+2).to_bytes(2, byteorder="big")+sfb
            rec += sfb

        self.send_3270_data(rec)

    def __range_addr(self, saddr, eaddr):
        if saddr >= eaddr:
            endpos = self.buffer_size
        else:
            endpos = eaddr

        for addr in range(saddr, endpos):
            yield addr

        if 0 < eaddr <= saddr:
            for addr in range(0, eaddr):
                yield addr

    def __read_buffer(self):
        """Process RB (Read Buffer) 3270 Data Stream Command.
        """
        self.__log_debug("Read Buffer (RB)")

        if self.inpid:
            raise TnzError(f"PID={self.inpid} not implemented")

        # similiar to send_aid but sends SF but no SBA

        self.__log_debug(" aid: 0x%02x", self.aid)
        baddr = self.address_bytes(self.curadd)
        self.__log_debug(" cursor %r", baddr)
        rec = bytes([self.aid]) + baddr

        reply_mode = self.__reply_mode
        reply_cattrs = self.__reply_cattrs
        buffer_size = self.buffer_size
        addr = 0
        while addr < buffer_size:
            while addr < buffer_size:
                fattr = self.plane_fa[addr]
                if not fattr:
                    break

                self.__log_debug(" SF %s", hex(fattr))
                sfb = [0x1d, fattr]  # SF (Start Field) fattr
                if reply_mode:  # Extended Field or Character
                    sfe = [0x29, 0]  # SFE (Start Field Extended) 0

                    attr = self.plane_eh[addr]
                    if attr:  # if not default
                        sfe[1] += 1
                        sfe.append(0x41, attr)

                    attr = self.plane_fg[addr]
                    if attr:  # if not default
                        sfe[1] += 1
                        sfe.append(0x42, attr)

                    attr = self.plane_cs[addr]
                    if attr:  # if not default
                        sfe[1] += 1
                        sfe.append(0x43, attr)

                    attr = self.plane_bg[addr]
                    if attr:  # if not default
                        sfe[1] += 1
                        sfe.append(0x45, attr)

                    if sfe[1] != 0x40:  # if not default`
                        if fattr:
                            sfe[1] += 1
                            sfe.append(0xc0, fattr)

                        sfb = sfe

                rec += bytes(sfb)
                addr += 1
            else:
                break

            eindex = self.__pat0s.search(self.plane_fa, addr).end()
            eaddr = eindex % buffer_size

            blst = []
            append = blst.append
            if reply_mode in (0x00, 0x01):  # [Extended] Field mode
                # TODO following needs to NOT append null characters
                self.__append_char_bytes(blst, addr, eaddr)

            elif reply_mode == 0x02:  # Character mode
                # TODO following needs to NOT append null characters
                # (nor their attributes)
                eh_attr = 0
                fg_attr = 0
                bg_attr = 0
                for sa2, ea2 in self.group_addrs(addr, eaddr):
                    eh1 = eh_attr
                    fg1 = fg_attr
                    bg1 = bg_attr
                    if 0x41 in reply_cattrs:
                        eh1 = self.plane_eh[sa2]

                    if 0x42 in reply_cattrs:
                        fg1 = self.plane_fg[sa2]

                    if 0x45 in reply_cattrs:
                        bg1 = self.plane_bg[sa2]

                    if eh1 != eh_attr:
                        append(bytes([0x28, 0x41, eh1]))  # SA 41 eh

                    if fg1 != fg_attr:
                        append(bytes([0x28, 0x42, fg1]))  # SA 42 fg

                    if bg1 != bg_attr:
                        append(bytes([0x28, 0x45, bg1]))  # SA 45 bg

                    self.__append_char_bytes(blst, sa2, ea2)

            else:
                raise TnzError(f"bad reply mode {reply_mode}")

            data = b"".join(blst)
            self.__log_debug(" RB: %s byte(s) of data @ %r",
                             len(data), addr)
            rec += data
            addr = eindex

        self.__log_debug(" End of RB response logging")
        self.send_3270_data(rec)

    def __readlines_check(self):
        if self.readlines is None:
            return

        saddr = self.buffer_size - 22
        vm_status = self.scrstr(saddr, 0).rstrip().upper()
        keep_all = (" MORE" in vm_status or
                    " HOLDING" in vm_status)
        if (" READ" in vm_status or
            " RUNNING" in vm_status or
                keep_all):
            self.__readlines_maxrow = self.maxrow - 2
            addr = self.__readlines_maxrow * self.maxcol
            if (not self.is_protected(addr) and
                    self.is_protected(addr - 1)):
                self.__addlines(keep_all)

        elif self.is_unprotected():  # TSO?
            self.__readlines_maxrow = self.maxrow - 1
            self.__addlines()
            if self.readlines:
                line = self.readlines.pop()
                if line not in ("***", " ***"):
                    self.readlines.append(line)

    def __set_attributes(self, addr, b_str, b_idx, zti=None):
        """
        Set field attributes according to input attributes in the
        format used by MF and SFE.
        """
        pairs = []
        start = b_idx + 1
        stop = start + b_str[b_idx] * 2
        for pair_index in range(start, stop, 2):
            fat = b_str[pair_index]
            fav = b_str[pair_index + 1]
            pairs.append((bytes([fat]), bytes([fav])))

            if fat == 0xc0:  # 3270 field attribute
                self.plane_fa[addr] = bit6(fav)

            elif fat == 0x41:  # extended highlighting
                self.plane_eh[addr] = fav

            elif fat == 0x42:  # foreground color
                if not self.__extended_color_mode:
                    if zti:
                        zti.extended_color(self)

                    self.__extended_color_mode = True

                self.plane_fg[addr] = fav

            elif fat == 0x43:  # character set
                self.plane_cs[addr] = fav

            elif fat == 0x45:  # background color
                if not self.__extended_color_mode:
                    if zti:
                        zti.extended_color(self)
                    self.__extended_color_mode = True

                self.plane_bg[addr] = fav

            else:
                raise TnzError(f"Bad field attribute type: {fat}")

        return stop, pairs

    async def __start_tls(self, context):
        self.__log_debug("__start_tls(%r)", context)

        loop = asyncio.get_event_loop()
        if hasattr(asyncio, "current_task"):
            task = asyncio.current_task()
        else:
            task = asyncio.Task.current_task()

        transport = self._transport
        protocol = transport.get_protocol()
        self._transport = None
        try:
            transport = await loop.start_tls(transport,
                                             protocol,
                                             context)
        except asyncio.CancelledError:
            self.seslost = True
            _wait_event.set()

        except OSError:  # what could this be?
            self.seslost = sys.exc_info()
            self.__logger.exception("start_tls error")
            _wait_event.set()

        else:
            self._transport = transport
            self.__secure = True
            self.__log_debug("__start_tls transport: %r", transport)

        finally:
            if self.__connect_task is task:
                self.__connect_task = None

    def __tab(self, saddr, eaddr=None):
        """Process tab action starting at input address.

        Returns result address.
        """
        plane_fa = self.plane_fa
        if not plane_fa[saddr]:  # if start on character
            saddr, _ = self.next_field(saddr, eaddr)
            if saddr < 0 or saddr == eaddr:
                return 0

        is_protected_attr = self.is_protected_attr
        saddr = (saddr+1) % self.buffer_size
        for sa1, _ in self.char_addrs(saddr, eaddr):
            fattr = plane_fa[sa1-1]
            if not is_protected_attr(fattr):
                return sa1

        return 0

    # Class methods

    @classmethod
    def logging(cls):
        """Initialize logging
        """
        cls.__log_check()

    # Private class methods

    @classmethod
    def __log_check(cls):
        if cls.__logger:
            return

        logger = logging.getLogger("tnz")
        cls.__logger = logger

        tnz_logging = os.getenv("TNZ_LOGGING")
        if tnz_logging == "":
            return

        if tnz_logging is None:
            dirname = os.path.expanduser(__file__)
            dirname = os.path.abspath(dirname)
            dirname = os.path.dirname(dirname)
            tnz_logging = os.path.join(dirname, "logging.json")

        with open(tnz_logging) as file:
            logd = json.load(file)

        from logging.config import dictConfig

        logd["disable_existing_loggers"] = False
        dictConfig(logd)

    @classmethod
    def __tnon(cls, value):
        """Translate input byte to a telnet option name.
        """
        if isinstance(value, int):
            value = bytes([value])

        name = cls.__tn_options.get(value)
        if name:
            return name

        return "0x"+value.hex()

    # Static methods

    @staticmethod
    def fav_repr(fav):
        """Return string representation of field attribute value.
        """
        fa_str = ""
        if fav & 0x20:  # if protected field
            fa_str += "P"  # protected
        else:
            fa_str += "u"  # unprotected

        if fav & 0x10:  # if numeric-only field
            fa_str += "N"  # numeric
        else:
            fa_str += "a"  # alphanumeric

        if not fav & 12:  # if b00..
            fa_str += "00"  # Display/not selector-pen-detectable
        elif fav & 12 == 4:  # if b01..
            fa_str += "01"  # Display/selector-pen-detectable
        elif fav & 12 == 8:  # if b10..
            fa_str += "10"  # Intensified display/pen-detect
        else:  # b11..
            fa_str += "11"  # Nondisplay, nondetectable (nonprint)

        if fav & 1 != 0:
            fa_str += "M"  # Modified
        else:
            fa_str += "m"  # Not modified

        return fa_str

    @staticmethod
    def is_detectable_attr(attr):
        """
        Return whether or not the input field attribute is for a
        selector-pen-detectable field.
        """
        return attr & 0x0c in (0x08, 0x04)  # b....10.. or b....01..

    @staticmethod
    def is_displayable_attr(attr):
        """
        Return whether or not the input field attribute is for a
        displayable field.
        """
        return attr & 0x0c != 0x0c  # not b....11..

    @staticmethod
    def is_intensified_attr(attr):
        """
        Return whether or not the input field attribute is for an
        intensified field.
        """
        return attr & 0x0c == 0x08  # b....10..

    @staticmethod
    def is_modified_attr(attr):
        """
        Return whether or not the input field attribute is for a
        modified field.
        """
        return bool(attr & 0x01)  # b.......1 MDT (Modified Data Tag)

    @staticmethod
    def is_normal_attr(attr):
        """
        Return whether or not the input field attribute is for a
        normal field.
        """
        return not attr & 0x0c  # b....00..

    @staticmethod
    def is_numeric_attr(attr):
        """
        Return whether or not the input field attribute is for a
        numeric field.
        """
        return attr & 0x10  # b...1....

    @staticmethod
    def is_protected_attr(attr):
        """
        Return whether or not the input field attribute is for a
        protected field.
        """
        return bool(attr & 0x20)  # b..1.....

    @staticmethod
    def rcba(value, start, stop):
        """read circular byte array

        value: byte array
        start: first index into byte array
        stop: last index into byte array
        returns copy of data from array
        """
        bal = len(value)
        if not bal:
            raise ValueError("no array")

        if start > bal:
            raise ValueError("start too big")

        if stop > bal:
            raise ValueError("stop too big")

        if start < stop:
            return value[start:stop]

        return value[start:]+value[:stop]

    @staticmethod
    def ucba(dst, start, src, begidx=0, endidx=None):
        """update circular byte array

        dst: target circular byte array
        start: first index into target byte array
        src: data to copy to array
        begidx: start index in data to copy (default is 0)
        endidx: end index in data to copy (default is len(src))
        """
        if endidx is None:
            endidx = len(src)

        bdl = endidx - begidx
        if bdl <= 0:
            raise ValueError("no data")

        bal = len(dst)
        if bdl > bal:
            raise ValueError("too much data")

        if start >= bal:
            raise ValueError("start too big")

        len1 = bal - start
        if len1 < bdl:
            len2 = bdl - len1
        else:
            len1 = bdl
            len2 = 0

        enda = start + len1
        endd = begidx + len1
        dst[start:enda] = src[begidx:endd]
        if len2:
            dst[:len2] = src[endd:endidx]

    # Readonly properties

    @property
    def host_verified(self):
        """Bool indicating if secure and host was verified.
        """
        return self.__host_verified

    @property
    def secure(self):
        """Bool indicating if connection is secure.
        """
        return self.__secure

    @property
    def tn3270(self):
        """Bool indicating if NOT NVT mode.
        """
        return self.__eor

    @property
    def tn3270e(self):
        """Bool indicating if using TN3270E.
        """
        return self.__tn3270e

    # Data descriptors

    @property
    def encoding(self):
        """Name of encoding.
        """
        return self.__encoding

    @encoding.setter
    def encoding(self, value):
        if isinstance(value, tuple):
            encoding, idx = value
        else:
            encoding, idx = value, 0

        code_page = re.findall("\\d+$", encoding)
        if len(code_page) != 1:
            raise ValueError("Does not end in code page number")

        code_page = int(code_page[0])

        import codecs
        self.codec_info[idx] = codecs.lookup(encoding)

        if idx == 0:
            self.__encoding = encoding
            self.cs_00 = 697  # FIXME how do we determine?
            self.cp_00 = code_page

        elif idx == 1:
            if code_page == 310:
                self.alt = 1  # Support GE for char set ID 01
                self.cs_01 = 963
            else:
                self.cs_01 = 697  # FIXME how do we determine?

            self.cp_01 = code_page

    # Class data

    __logger = None  # will be set by __log_check

    # Private class data

    # Translate data characters to printable characters
    # NULL 0x00 -> space
    # SUB  0x3f -> a solid circle
    # DUP  0x1c -> an overscore asterisk
    # FM   0x1e -> an overscore semicolon
    # FF   0x0c -> space
    # CR   0x0d -> space
    # NL   0x15 -> space
    # EM   0x19 -> space
    # EO   0xff -> space
    __trans_dc_to_c = bytes.maketrans(
        b"\x00\x0c\x0d\x15\x19\xff",
        b"\x40\x40\x40\x40\x40\x40")

    # The translation to characters that are not in the
    # code page must be done by unicode ordinal.
    __trans_ords = {0x1a: 0x2218,  # SUB -> solid circle
                    0x1c: 0x2611,  # DUP -> check-mark???
                    0x1e: 0x2612}  # FM -> x-mark???

    # compiled regular expression patterns
    __pat0s = re.compile(b"\x00+")
    __patn0 = re.compile(b"[^\x00]")
    __patn0l = re.compile(b"[^\x00][\x00]*\\Z")
    __patbs = re.compile(b"(.)\\1*")
    __patord = re.compile(b"[\x05\x08\x11\x12\x13\x1d\x28\x29\x2c\x3c]")
    __pat0n0s = re.compile(b"[^\x00]\x00+")

    class __ReadState(enum.Enum):
        """3270 DS READ STATE
        """
        NORMAL = enum.auto()
        RENTER = enum.auto()
        RREAD = enum.auto()

    __tn_options = {b"\x00": "TRANSMIT-BINARY",
                    b"\x01": "ECHO",
                    b"\x03": "SUPPRESS-GO-AHEAD",
                    b"\x06": "TIMING-MARK",
                    b"\x18": "TERMINAL-TYPE",
                    b"\x19": "END-OF-RECORD",
                    b"\x1d": "3270-REGIME",
                    b"\x28": "TN3270E",
                    b"\x2e": "START_TLS",
                    }


class TnzError(RuntimeError):
    """General Tnz error.
    """


class TnzTerminalError(TnzError):
    """May be related to terminal characteristics.
    """


# Functions

def bit6(control_int):
    """Translate 6-bit control characters to printable characters.
    This
    is used for bytes that have bits 0 and 1 reserved in order to
    make the byte a printable character. See figure D-1 in Data
    Stream Programmers Reference.
    """
    control_int &= 63  # x3f - zero bits 0,1
    cc11 = control_int | 192  # input with bits 0,1 = 11

    if control_int == 48:
        return cc11  # 11 0000 -> xF0

    cc01 = control_int | 64  # input with bits 0,1 = 01

    if control_int == 33:
        return cc01  # 10 0001 -> x61

    if 0 < (control_int & 0x0f) < 10:  # if low nibble 1-9
        return cc11  # aa aaaa -> 11aa aaaa

    return cc01  # aa aaaa -> 01aa aaaa


def connect(host=None, port=None,
            secure=None, verifycert=None,
            name=None):
    """Create a new Tnz object and connect to the host.

    secure = False if do not care about security
    secure = True for encrypted connection
    verifycert only has meaning when secure is True
    """
    tnz = Tnz(name=name)

    if port is None and secure is not False:
        port = 992
        if verifycert is None:
            verifycert = False

    if secure and verifycert is None:
        verifycert = True

    if secure is None:
        secure = bool(port != 23)

    tnz.connect(host, port, secure=secure, verifycert=verifycert)

    return tnz


def selector_set(fileno, data=None):
    """Add input fd for wait read events.
    """
    _loop.add_reader(fileno, _read_available, data)


def selector_del(fileno):
    """Remove input fd from wait read events.
    """
    _loop.remove_reader(fileno)


def wakeup_wait(*_, **__):
    """Trigger wait event.
    """
    if _wait_event:
        _loop.call_soon_threadsafe(_wait_event.set)


# Private functions

def _read_available(_):
    if _wait_event:
        _wait_event.set()


# Private data

_loop = None  # event loop for all sessions
_wait_event = None  # event for all Wait calls
