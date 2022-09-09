from tnz.ati import *
from tnz.ati import Ati
from tnz.ati import AtiError


def test_num():
    assert num("5bcde") == 5


def test_stripl():
    assert stripl("   ab de ") == "ab de "


def test_stript():
    assert stript("   ab de ") == "   ab de"


def test_init():
    assert value("CURCOL") == "0"
    assert value("CURROW") == "0"
    assert value("DISPLAY") == "NONE"
    assert value("HITCOL") == "1"
    assert value("HITROW") == "1"
    assert value("KEYLOCK") == "0"
    assert value("KEYUNLOCK") == "60"
    assert value("LOGDEST") == "(STDERR)"
    assert value("MAXCOL") == "0"
    assert value("MAXLOSTWARN") == "5"
    assert value("MAXROW") == "0"
    assert value("ONERROR") == "0"
    assert value("RC") == "0"
    assert value("SCRDELAY") == "5"
    assert value("SCRUPDATE") == "0"
    assert value("SENDSTR") == ""
    assert value("SESLOST") == ""
    assert value("SESSION") == "NONE"
    assert value("SESSIONID") in ("0", "1")
    assert value("SESSIONS") == ""
    assert value("SESSION24") in ("0", "1")
    assert value("SHOWTYPE") in ("0", "1")
    assert value("TRACE") == "NONE"
    assert value("WAITSLEEP") == "1"


def test_badses():
    set("SESSION_PORT", 9)  # no tcp? or discard?
    assert set("SESSION", "BADSES") in (0, 8, 12)
    assert send(enter) == 12
    assert value("SESSION") == "NONE"
    assert value("SESSIONS") == ""
    assert value("SESLOST") == "BADSES"
    drop("SESSION_PORT")


def test_maxlostwarn():
    with Ati():
        set("MAXLOSTWARN", 1)
        set("SESSION_PORT", 9)  # no tcp? or discard?
        got_expected_error = False
        try:
            set("SESSION", "BADSES")

        except AtiError:
            got_expected_error = True

        if not got_expected_error:
            assert value("RC") == "0"
            got_expected_error = False
            try:
                send(enter)

            except AtiError:
                got_expected_error = True

            assert got_expected_error

    with Ati():
        set("MAXLOSTWARN", 2)
        set("SESSION_PORT", 9)  # no tcp? or discard?
        assert set("SESSION", "BADSES") in (0, 8, 12)
        if value("RC") == "0":
            assert send(enter) == 12

        got_expected_error = False
        try:
            send(enter)

        except AtiError:
            got_expected_error = True

        assert got_expected_error
