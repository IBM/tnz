"""Terminal key mappings for ZTI.

The default mappings intentionally include only non-printable terminal input
values. Printable characters are intentionally excluded so they cannot be
customized and remain subject to normal terminal input handling.
"""

import json
import os
from pathlib import Path

DEFAULT_KEYMAP = {
    "\r": "enter",
    "\n": "newline",
    "\t": "tab",
    "\b": "backspace",
    "\x03": "attn",
    "\x0b": "eraseeof",
    "\x0c": "clear",
    "\x0f": "open_url",
    "\x17": "drop_session",
    "\x1b": "escape",
    "\x1b[1~": "home",
    "\x1b[4~": "eraseeof",
    "\x1b[5;3~": "prev_session",
    "\x1b[6;3~": "next_session",
    "\x1b[11~": "pf1",
    "\x1b[12~": "pf2",
    "\x1b[13~": "pf3",
    "\x1b[14~": "pf4",
    "\x1b[25~": "pf15",
    "\x1b[26~": "pf16",
    "\x1b[28~": "pf17",
    "\x1b[29~": "pf18",
    "\x1b[31~": "pf19",
    "\x1b[32~": "pf20",
    "\x1b[33~": "pf21",
    "\x1b[34~": "pf22",
    "\x1b[1;3D": "word_left",
    "\x1b[1;3C": "word_right",
    "\x1b\x1b[D": "word_left",
    "\x1b\x1b[C": "word_right",
    "\x1b\x1b[5~": "prev_session",
    "\x1b\x1b[6~": "next_session",
    "\x1b\x1b[1~": "pa2",
    "\x1bb": "word_left",
    "\x1bf": "word_right",
    "\x1bH": "home",
    "\x1bF": "eraseeof",
    "\x1b1": "pa1",
    "\x1b2": "pa2",
    "\x1b3": "pa3",
    "\x1ba": "attn",
    "\x1bc": "clear",
    "\x7f": "backspace",
    "KEY_BACKSPACE": "backspace",
    "KEY_BTAB": "backtab",
    "KEY_DC": "delete",
    "KEY_DOWN": "curdown",
    "KEY_END": "end",
    "KEY_ESC": "escape",
    "KEY_F(1)": "pf1",
    "KEY_F(2)": "pf2",
    "KEY_F(3)": "pf3",
    "KEY_F(4)": "pf4",
    "KEY_F(5)": "pf5",
    "KEY_F(6)": "pf6",
    "KEY_F(7)": "pf7",
    "KEY_F(8)": "pf8",
    "KEY_F(9)": "pf9",
    "KEY_F(10)": "pf10",
    "KEY_F(11)": "pf11",
    "KEY_F(12)": "pf12",
    "KEY_F(13)": "pf13",
    "KEY_F(14)": "pf14",
    "KEY_F(15)": "pf15",
    "KEY_F(16)": "pf16",
    "KEY_F(17)": "pf17",
    "KEY_F(18)": "pf18",
    "KEY_F(19)": "pf19",
    "KEY_F(20)": "pf20",
    "KEY_F(21)": "pf21",
    "KEY_F(22)": "pf22",
    "KEY_F(23)": "pf23",
    "KEY_F(24)": "pf24",
    "KEY_HOME": "home",
    "KEY_IC": "insert",
    "KEY_LEFT": "curleft",
    "KEY_MOUSE": "mouse",
    "KEY_NPAGE": "next_page",
    "KEY_PPAGE": "prev_page",
    "KEY_RESIZE": "resize",
    "KEY_RIGHT": "curright",
    "KEY_SEND": "eraseeof",
    "KEY_UP": "curup",
    "ALT_1": "pa1",
    "ALT_2": "pa2",
    "ALT_3": "pa3",
    "ALT_A": "attn",
    "ALT_C": "clear",
    "ALT_HOME": "pa2",
    "ALT_INS": "pa1",
    "ALT_PGDN": "next_session",
    "ALT_PGUP": "prev_session",
}


def _is_customizable_key(key):
    """Return True only for key sequences that are not printable text."""
    if not isinstance(key, str) or not key:
        return False

    return not (len(key) == 1 and key.isprintable())


def load_keymap(path=None):
    """Load the terminal keymap, merging in user overrides.

    The customizable file is expected to be JSON mapping key sequences to
    action names. Printable single-character mappings are ignored so normal
    text entry remains unchanged.
    """
    keymap = DEFAULT_KEYMAP.copy()
    config_path = path or os.getenv("ZTI_KEYMAP")
    if not config_path:
        return keymap

    filename = Path(config_path).expanduser()
    if not filename.is_file():
        return keymap

    try:
        with filename.open("r", encoding="utf-8") as handle:
            custom = json.load(handle)
    except (OSError, ValueError):
        return keymap

    if not isinstance(custom, dict):
        return keymap

    for raw_key, action in custom.items():
        key = str(raw_key)
        if not _is_customizable_key(key):
            continue

        keymap[key] = str(action)

    return keymap
