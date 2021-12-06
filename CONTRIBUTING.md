## Contributing In General
Our project welcomes external contributions. If you have an itch,
please feel free to scratch it.

To contribute code or documentation, please submit a [pull
request](https://github.com/ibm/tnz/pulls).

A good way to familiarize yourself with the codebase and contribution
process is to look for and tackle low-hanging fruit in the [issue
tracker](https://github.com/ibm/tnz/issues).

**Note: We appreciate your effort, and want to avoid a situation
where a contribution requires extensive rework (by you or by us),
sits in backlog for a long time, or cannot be accepted at all!**

### Proposing new features

If you would like to implement a new feature, please [raise an
issue](https://github.com/ibm/tnz/issues) before sending a pull
request so the feature can be discussed. This is to avoid you wasting
your valuable time working on a feature that the maintainers are not
interested in accepting into the code base.

### Fixing bugs

If you would like to fix a bug, please [raise an
issue](https://github.com/ibm/tnz/issues) before sending a pull
request so it can be tracked.

## Legal

Each source file must include a license header for the Apache
Software License 2.0. Using the SPDX format is the simplest approach.
e.g.

```
/*
Copyright <holder> All Rights Reserved.

SPDX-License-Identifier: Apache-2.0
*/
```

We have tried to make it as easy as possible to make contributions.
This applies to how we handle the legal aspects of contribution. Use
the same approach - the [Developer's Certificate of Origin 1.1 (DCO)]
(https://github.com/hyperledger/fabric/blob/main/docs/source/DCO1.1.txt)
approach. We simply ask that when submitting a patch for review, the
developer must include a sign-off statement in the commit message.

Here is an example Signed-off-by line, which indicates that the
submitter accepts the DCO:

```
Signed-off-by: John Doe <john.doe@example.com>
```

You can include this automatically when you commit a change to your
local git repository using the following command:

```
git commit -s
```

## Setup
Nothing more than install the required dependencies:
```
pip install -r requirements.txt
```

## Testing
Testing is done with `pytest`.

## Coding style guidelines
Follow [PEP8](https://www.python.org/dev/peps/pep-0008/) for code style.
```
pycodestyle tnz/*.py
```
