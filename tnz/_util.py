"""tnz utility functions

Usage: from . import _util.py

Copyright 2021 IBM Inc. All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
"""

import json
import logging
import os

__author__ = "Neil Johnson"

_logger = logging.getLogger(__name__)

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



def load_theme():
    """Load color theme from TNZ_THEME environment variable.
    
    Returns a dictionary mapping color names to RGB tuples (0-1000 scale),
    or None if TNZ_THEME is not set or the file cannot be loaded.
    
    Expected JSON format:
    {
        "black": "#000000",
        "red": "#f01818",
        "green": "#24d830",
        "yellow": "#ffff00",
        "blue": "#7890f0",
        "magenta": "#ff00ff",
        "cyan": "#58f0f0",
        "white": "#ffffff"
    }
    
    Hex values should be in format #RRGGBB.
    """
    theme_path = os.environ.get('TNZ_THEME')
    if not theme_path:
        return None
    
    try:
        with open(theme_path, 'r') as f:
            theme_data = json.load(f)
        
        # Validate and convert hex colors to RGB tuples (0-1000 scale)
        color_names = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']
        theme = {}
        
        for color_name in color_names:
            if color_name not in theme_data:
                _logger.warning(f"TNZ_THEME: Missing color '{color_name}' in theme file")
                return None
            
            hex_color = theme_data[color_name]
            if not isinstance(hex_color, str) or not hex_color.startswith('#') or len(hex_color) != 7:
                _logger.warning(f"TNZ_THEME: Invalid hex color for '{color_name}': {hex_color}")
                return None
            
            try:
                # Convert hex to RGB (0-255) then to curses scale (0-1000)
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)
                
                # Convert from 0-255 to 0-1000 scale
                r_1000 = int(round(r * 1000 / 255))
                g_1000 = int(round(g * 1000 / 255))
                b_1000 = int(round(b * 1000 / 255))
                
                theme[color_name] = (r_1000, g_1000, b_1000)
            except ValueError as e:
                _logger.warning(f"TNZ_THEME: Failed to parse hex color for '{color_name}': {hex_color} - {e}")
                return None
        
        _logger.info(f"TNZ_THEME: Loaded theme from {theme_path}")
        return theme
        
    except FileNotFoundError:
        _logger.warning(f"TNZ_THEME: Theme file not found: {theme_path}")
        return None
    except json.JSONDecodeError as e:
        _logger.warning(f"TNZ_THEME: Invalid JSON in theme file: {theme_path} - {e}")
        return None
    except Exception as e:
        _logger.warning(f"TNZ_THEME: Error loading theme file: {theme_path} - {e}")
        return None