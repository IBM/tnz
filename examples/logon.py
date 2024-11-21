from dotenv import load_dotenv
import os

from tnz.ati import ati

load_dotenv(override=True) # take environment variables from .env

ati.set("TRACE", "ALL")
ati.set("LOGDEST", "example.log")

ati.set("ONERROR", "1")
ati.set("DISPLAY", "HOST")
ati.set("SESSION_HOST", os.getenv("SESSION_HOST", "mvs1"))
ati.set("SESSION_CODE_PAGE", os.getenv("SESSION_CODE_PAGE", "cp1047"))
ati.set("SESSION", "A")

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
