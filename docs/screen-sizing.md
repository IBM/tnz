---
title: Screen Sizing
hide:
  - toc
---

Typical desktop applications can be resized. And resizing does not typically change the scale of the content (i.e. the font size) - it changes the amount of viewable content. In the world of terminals, this means a change in the number of character rows and columns. Even though it is common for modern applications to handle window resizing, it is not common for legacy 3270 applications to handle terminal resizing. The tnz library helps with this dilemma by keeping the 3270 terminal size constant for a connected session even when the host acii terminal size may be changing. But this does not help when reconnecting sessions.

One thing that may help keep the 3270 terminal size constant in reconnect scenarios is allowing tnz to select the terminal size for you. It will select from a relatively small set of *standard* terminal sizes the largest size that fits on the host terminal. So, for small changes to the terminal size, the largest *standard* size will tend to not change.