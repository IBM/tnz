"""Telnet-3270 to Z tool and library
"""

from subprocess import check_output
from subprocess import CalledProcessError
from os import path
from os import remove
from os import environ
from setuptools import setup

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

version = environ.get("TRAVIS_TAG", None)
if not version:
    try:
        rv = check_output(["git", "-C", here,
                           "describe", "--tag",
                           "--dirty", "--broken"])
        version = rv.decode("ascii").strip()
        version = version.replace("-", ".", 1)
        version = version.replace("-", "+", 1)
    except CalledProcessError:
        version = "v0.0.0"

version_file = path.join(here, "tnz", "_version.py")
try:
    with open(version_file, mode="x", encoding="ascii") as f:
        f.write(f"__version__ = {version[1:]!r}")

    setup(
        name="tnz",
        version=version[1:],  # git tag w/o 'v' prefix
        description="Telnet-3270 to Z tool and library",
        long_description=long_description,
        url="https://github.com/ibm/tnz",
        author="Neil Johnson",
        author_email="najohnsn@us.ibm.com",
        package_dir={"": "."},
        packages=["tnz"],
        package_data={"tnz": ["logging.json"]},
        python_requires=">=3.6",
        extras_require={
            "full": ["ebcdic"]
        },
        entry_points={
            "console_scripts": [
                "zti=tnz.zti:main"
            ]
        },
        project_urls={
            "Bug Reports": "https://github.com/ibm/tnz/issues",
            "Source": "https://github.com/ibm/tnz",
        }
    )

finally:
    remove(version_file)
