"""tnz utility functions

Usage: from . import _util.py

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""

__author__ = "Neil Johnson"

_SESSION_PS_SIZES = {
    "2": (24, 80),
    "3": (32, 80),
    "4": (43, 80),
    "5": (27, 132),
    "6": (24, 132),
    "7": (36, 80),
    "8": (36, 132),
    "9": (48, 80),
    "10": (48, 132),
    "11": (72, 80),
    "12": (72, 132),
    "13": (144, 80),
    "14": (144, 132),
    "15": (25, 80),
    "16": (25, 132),
    "17": (62, 160),
    "18": (26, 80),
    "19": (26, 132),
    }


def session_ps_size(ps_size):
    """Convert SESSION_PS_SIZE to rows, cols.
    This is according to the values defined by HOD.
    It is best to use a rowsXcols notation, but
    integers are support to support historical roots
    in using HOD.
    """
    rows, cols = _SESSION_PS_SIZES.get(str(ps_size), (0, 0))
    if rows and cols:
        return rows, cols

    try:
        ps_size = ps_size.upper().split("X", 1)
        return int(ps_size[0]), int(ps_size[1])

    except Exception as exc:
        raise ValueError("Not a SESSION_PS_SIZE value") from exc


def session_ps_14bit(max_h, max_w):
    """Trim size to 14-bit limitation
    """
    # why 16383 instead of 16384 for 14-bit?
    max_h = max(max_h, 24)
    max_w = max(max_w, 80)
    max_h = min(max_h, 204)  # 16383 // 80
    max_w = min(max_w, 682)  # 16383 // 24

    if max_h >= 127 and max_w >= 129:
        return 127, 129  # 127*129=16383

    if max_h >= 129 and max_w >= 127:
        return 129, 127  # 129*127=16383

    if max_h * max_w <= 16383:
        return max_h, max_w

    return 16383 // max_w, max_w
