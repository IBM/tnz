---
title: Screen Sizing
hide:
  - toc
---

Typical desktop applications can be resized. And resizing does not typically change the scale of the content (i.e. the font size) - it changes the amount of viewable content. In the world of terminals, this means a change in the number of character rows and columns. Even though it is common for modern applications to handle window resizing, it is not common for legacy 3270 applications to handle terminal resizing. The tnz library helps with this dilemma by keeping the 3270 terminal size constant for a connected session even when the host acii terminal size may be changing. But this does not help when reconnecting sessions.

One thing that may help keep the 3270 terminal size constant in reconnect scenarios is allowing tnz to select the terminal size for you. It will select from a relatively small set of *standard* terminal sizes the largest size that fits on the host terminal. So, for small changes to the terminal size, the largest *standard* size will tend to not change.

## SESSION\_PS\_SIZE

To help with reconnect scenarios, or to just request a specific size, set the `SESSION_PS_SIZE` environment variable to the desired size (for example `export SESSION_PS_SIZE=43x80` for 43 rows by 80 columns). When using `ati.py` or in `zti` you can also use the `SESSION_PS_SIZE` ATI\-like variable in the same way (for example `set SESSION_PS_SIZE=62x160`).

In addition to taking the default largest *standard* terminal size that fits and specifying a specific size, there are some special values that you can set the `SESSION_PS_SIZE` environment variable to that `zti` will use to determine the 3270 terminal size:

*   `MAX` fill host terminal but leave space for header/footer and session selector (column max of *160*)
*   `MAX255` fill host terminal but leave space for header/footer and session selector (column max of *255*)
*   `FULL` fill host terminal (column max of *160*)
*   `FULL255` fill host terminal (column max of *255*)

## Autosize

IBM Personal Communications has a feature that will scale the font so that the 3270 terminal area takes up all of the window area. This behavior can also be simulated using tnz in PuTTY:

1.  Set your font size and window size the way you like it for your shell.
2.  In zti, you can use the `size` command to get the current number of rows and columns of your terminal.
3.  Use PuTTY Change Settings. Choose the Window category. Set the size of the window to your current rows and columns and for "When window is resize", choose "Change the size of the font". Apply those changes.
4.  Enter `autosize` in `zti` to turn on the tnz feature.

When using `goto`, `zti` will use the shell terminal size as your *preferred scale*. It will then use the terminal capability to set the size of the terminal. In this case, not only will the rows and columns change, but the font will change in order to keep all terminal characters in your window \- as opposed to the normal setting that would cause a change to the size of the window instead of the size of the font. But, unlike PCOMM, it may not fill the whole window in order to respect your *preferred scale*.
