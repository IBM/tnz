"""
The tnz package joins users with hosts over 3270 data streams. This
includes the zti emulator (see zti module).

First modules to look at to use 3270 APIs:
    ati     high level ATI-like APIs
    ditto   high level IBM-internal-Ditto-like APIs
    py3270  high level py3270-like APIs
    tnz     low level APIs

The rexx module as a small subset of Rexx-like functions.

Module cp310 provides an additional code page for APL terminals.

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""
__author__ = "Neil Johnson"

try:
    import ebcdic as _
except ImportError:
    pass

try:
    from ._version import __version__

except ImportError:
    __version__ = None
