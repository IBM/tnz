---
title: Colors
---

By default, *tnz* will emulate a 3270 terminal that has 8 colors and `zti` will assume a host terminal capable of true color is being used and use a *tnz\-defined color palette* to display those 8 terminal colors.

## TNZ_COLORS Environment Variable

If you do not want (or cannot use, in the case of `Terminal.app`) this default color behavior, you can use the `TNZ_COLORS` environment variable. Use `export TNZ_COLORS=256` to direct `zti` to use the 256\-color palette instead of true color. Set to an integer less than 16 and `zti` will assume only the *standard* ansi colors can be used (for example `export TNZ_COLORS=8`). This can be helpful if your terminal doesn't support true color or if you want to change the colors to your liking \- terminal emulators typically allow you to set the ansi colors. Set to an integer less than 8 and tnz will emulate a 3270 terminal that has no color capability and `zti` will not use any color capability.

## TNZ_THEME Environment Variable

For more precise control over the color palette, you can use the `TNZ_THEME` environment variable to specify a JSON file containing custom color definitions. This allows you to define the exact hex values for each of the 8 standard terminal colors.

To use a custom theme:

1. Create a JSON file with color definitions (see example below)
2. Set the environment variable: `export TNZ_THEME=/path/to/theme.json`
3. Start `zti` or `ztd`

### Theme File Format

The theme JSON file must contain hex color values for all 8 standard colors:

```json
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
```

Each color value must be a hex string in the format `#RRGGBB`. The theme will only be applied if the terminal supports true color (colors >= 264). If any color is missing or invalid, the default IBM PCOMM color palette will be used instead.

### Example Themes

**Solarized Dark Theme:**
```json
{
    "black": "#002b36",
    "red": "#dc322f",
    "green": "#859900",
    "yellow": "#b58900",
    "blue": "#268bd2",
    "magenta": "#d33682",
    "cyan": "#2aa198",
    "white": "#fdf6e3"
}
```

**Gruvbox Theme:**
```json
{
    "black": "#282828",
    "red": "#cc241d",
    "green": "#98971a",
    "yellow": "#d79921",
    "blue": "#458588",
    "magenta": "#b16286",
    "cyan": "#689d6a",
    "white": "#ebdbb2"
}
```

## Color Palette Reference

The following table describes, for each color mode, the host terminal colors used for the 8 different 3270 colors. If different colors are desired, check the zti\-hosting terminal for the capability to change the color palette. You may need to use TNZ\_COLORS=8 to get zti to use the customized color palette.

**The actual terminal 8\-bit color palette may not match the table above. It is common for terminal emulators to customize the palette.** 