---
title: Colors
---

By default, *tnz* will emulate a 3270 terminal that has 8 colors and `zti` will assume a host terminal capable of true color is being used and use a *tnz\-defined color palette* to display those 8 terminal colors.

If you do not want (or cannot use, in the case of `Terminal.app`) this default color behavior, you can use the `TNZ_COLORS` environment variable. Use `export TNZ_COLORS=256` to direct `zti` to use the 256\-color palette instead of true color. Set to an integer less than 16 and `zti` will assume only the *standard* ansi colors can be used (for example `export TNZ_COLORS=8`). This can be helpful if your terminal doesn't support true color or if you want to change the colors to your liking \- terminal emulators typically allow you to set the ansi colors. Set to an integer less than 8 and tnz will emulate a 3270 terminal that has no color capability and `zti` will not use any color capability.

The following table describes, for each color mode, the host terminal colors used for the 8 different 3270 colors. If different colors are desired, check the zti\-hosting terminal for the capability to change the color palette. You may need to use TNZ\_COLORS=8 to get zti to use the customized color palette.

**The actual terminal 8\-bit color palette may not match the table above. It is common for terminal emulators to customize the palette.**