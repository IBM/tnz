---
title: Security
hide:
  - toc
---

## SSL Verification

Use environment variable `SESSION_SSL_VERIFY=cert` to require that the
server provide a trusted certificate.

Use environment variable `SESSION_SSL_VERIFY=hostname` to require that
the certificate hostname match the requested hostname. Note that this
also requires that the server provide a trusted certificate.

## Cipher Issues

Python 3.10 is aggressive in causing failures for algorithms/options that are not secure enough. If you receive an SSL-related message, there is a good chance of a security weakness in the host/server.

The best course of action is to request that the server be updated to support security best practices in terms of supported encryption algorithms and key sizes.

The other option is to try to use the "less secure" way that the server is "forcing". If this is a problem with the changes in Python 3.10, doing `export ZTI_SECLEVEL=1` (or `SET ZTI_SECLEVEL=1` in Windows) before starting zti should accept the "less secure" option by downgrading the level from 2 to 1.

## Port Defaults

If `SESSION_SSL=0` is used, the default port is 23. If `SESSION_SSL=1` is used, the default port is 992.
