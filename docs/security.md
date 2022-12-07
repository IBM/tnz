---
title: Security
hide:
  - toc
---

Python 3.10 is aggressive in causing failures for algorithms/options that are not secure enough. If you receive an SSL-related message, there is a good chance of a security weakness in the host/server.

The best course of action is to request that the server be updated to support security best practices in terms of supported encryption algorithms and key sizes.

The other option is to try to use the "less secure" way that the server is "forcing". If this is a problem with the changes in Python 3.10, doing `export ZTI_SECLEVEL=1` (or `SET ZTI_SECLEVEL=1` in Windows) before starting zti should accept the "less secure" option by downgrading the level from 2 to 1.

## Port Defaults

If `SESSION_SSL=0` is used, default port is 992 If `SESSION_SSL=1` is used, default port is 23.