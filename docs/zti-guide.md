---
title: Zti
---

The terminal emulator in tnz is called zti. There are various settings
that impact the presentation of the 3270 terminal screen on the terminal
controlling zti. Some of these can be found in [colors](colors.md) and
[screen sizing](screen-sizing.md). Some others are documented on this
page.

# Cursor

Zti, like other 3270 terminal emulators, keep track of an insert/replace
mode. The mode determines whether a keyed character replaces the current
one on the screen or gets inserted before it. The shape of the cursor
can be used as an indication of the current mode. The following cursor
shapes may be available in your controlling terminal:

1. Blinking block
2. Steady block
3. Blinking underline
4. Steady underline
5. Blinking bar
6. Steady bar

By default, zti will use **1** (blinking block) for insert mode and
**3** (blinking underline) for replace mode. The capability for terminal
emulators to handle these cursor styles varies. For instance, usability
of a blinking underline cursor on an empty underlined field may not be
very visible in some terminals. To customize the cursor style,
environment variables can be used to set the desired styles. Here is
an example to set variables that achieve the default settings:

```
export ZTI_CURSOR_INSERT=1
export ZTI_CURSOR_REPLACE=3
```

The values for the cursor styles correspond to `DECSCUSR` arguments.
You may need to consult your terminal documentation for the supported
values. The following links may be helpful in finding supported values:

- [https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences#cursor-shape](
https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences#cursor-shape)
- [https://terminalguide.namepad.de/seq/csi_sq_t_space](
https://terminalguide.namepad.de/seq/csi_sq_t_space)
- [https://iterm2.com/feature-reporting](
https://iterm2.com/feature-reporting)
