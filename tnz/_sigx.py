"""Signal extension module.
Multiple signal handlers.

Copyright 2021, 2023 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""

import logging
import signal

from . import tnz
from . import ati

__author__ = "Neil Johnson"


def add_handler(signalnum, handler):
    """Similar to signal.signal, but old signal handler (if any, and
    not including special special values signal.SIG_IGN and
    signal.SIG_DFL) removed. The old special value is saved so that
    it can be restored when all handlers are deleted. This function
    does not accept a special value as input.
    """
    handall = _handall
    handold = signal.getsignal(signalnum)
    global _handling
    handling = _handling
    if (signalnum not in handling and
            handold not in (handall, signal.SIG_DFL)):
        try:
            raise RuntimeError("handler already established")
        except RuntimeError:
            _logger.exception("signal %r has handler: %r",
                              signalnum, handold)
            return

    handmap = _handmap
    discard = False
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, handling)
    try:
        if signalnum not in handling:
            handling = handling.copy()
            handling.add(signalnum)

        handlst = handmap.get(signalnum, None)
        if handlst is None:
            handlst = []
            handmap[signalnum] = handlst

        handlst.append(handler)
        _handling = handling
        signal.signal(signalnum, handall)

    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if discard:
            _handling.discard(signalnum)


def del_handler(handler):
    """Deletes all signal handlers associated with the input handler.
    For each signal that has all handlers deleted, the default signal
    behavior is restored.
    """
    handling = _handling
    handmap = _handmap
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, handling)
    try:
        for signalnum in frozenset(handmap.keys()):
            handlst = handmap[signalnum]
            try:
                handlst.remove(handler)

            except ValueError:
                pass

            if not handlst:
                del handmap[signalnum]
                signal.signal(signalnum, signal.SIG_DFL)

    except Exception:
        _logger.exception("del_handler error")
        raise

    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


# Private functions

def _handlst(handlst):
    for handler in handlst:
        handler()

    tnz.wakeup_wait()

def _handall(signalnum, *_):
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, _handling)
    try:
        handlst = _handmap.get(signalnum)
        ati.ati.loop.call_soon_threadsafe(_handlst, handlst[:])

    except Exception:
        _logger.exception("_handall error")

    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


# Private data

_logger = logging.getLogger("tnz.sigx")
_handling = set()  # set of keys in _handmap
_handmap = {}  # key: signalnum, value: list of handlers
