from tnz.ditto import Ditto
from tnz.ati import ati

ati.set("TRACE", "ALL")
ati.set("LOGDEST", "example.log")

dit = Ditto()

ati.set("SESSION_HOST", "xrfmcl")
ati.set("SESSION", "A")

dit.verify("A", "Enter:  ")
dit.enter_after("A", "Enter:  ", "xrfmcl userid")
dit.verify("A", "Password  ===> ")
dit.enter_after("A", "Password  ===> ", "password")

# maybe look for a status message
dit.verify("A", "ICH70001I")

# do something useful
dit.verify("A", "***")
dit.enter("A")
dit.verify("A", "READY")
dit.enter("A", "logon")
dit.verify("A", "LOGGED OFF")

# disconnect from host
dit.disconnect("A")
