---
title: User Macros
---

Users may define macros for `zti`. When defined, user macros appear in the list of available commands for `zti`. User macros are created by placing Python files in the ZTI macros directory, which defaults to the path `~/.zti-mac`. This path may be overridden with the `ZTI_MACROS_DIR` environment variables.

User macro file names must take the form `my_macro.py`, and must contain a function with the signature,

```python
    def do_my_macro(zti, arg):
        ...
```

This function is invoked when the macro command is run from `zti`. It is passed the current `zti` instance as the first argument and any arguments to the command as the second argument.

The macro file may optionally also contain a function with the signature,

```python
    def help_my_macro(zti):
        ...
```

This function will be registered as the help command for the main macro command.

See `examples/macros/logon.py` for an example of a user macro.

A macro file name may not contain more than one period character. User macros which conflict with existing ZTI commands are ignored.