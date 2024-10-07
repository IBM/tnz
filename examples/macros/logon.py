from tnz.ati import ati

def do_logon(zti, arg):
    logon_setup()
    ati.wait(lambda: ati.scrhas("Enter:  "))
    ati.send("app1 userid[enter]")
    ati.wait(lambda: ati.scrhas("Password  ===> "))
    ati.send("password[enter]")

    # maybe look for a status message
    ati.wait(lambda: ati.scrhas("ICH70001I"))

    # do something useful
    ati.wait(lambda: ati.scrhas("***"))
    ati.send("[enter]")
    ati.wait(lambda: ati.scrhas("READY"))
    ati.send("logon[enter]")
    ati.wait(lambda: ati.scrhas("LOGGED OFF"))

    # disconnect from host
    ati.drop("SESSION")

def logon_setup():
    ati.set("TRACE", "ALL")
    ati.set("LOGDEST", "example.log")

    ati.set("ONERROR", "1")
    ati.set("DISPLAY", "HOST")
    ati.set("SESSION_HOST", "mvs1")
    ati.set("SESSION", "A")
