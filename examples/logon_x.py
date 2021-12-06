from tnz.py3270 import Emulator

em = Emulator(visible=True, args=["-trace",
                                  "-tracefile",
                                  "example.log"])
em.connect('xrfmcl')


def string_wait(string):
    while True:
        em.wait_for_field()
        c = em.exec_command(b"Ascii()")
        if string in b"\n".join(c.data).decode():
            return

        em.exec_command(b"Wait(Output)")


string_wait("Enter:  ")
em.send_string("xrfmcl userid\\n")

string_wait("Password  ===> ")
em.send_string("password\\n")

# if your host unlocks the keyboard before truly being ready you can use:
em.wait_for_field()

# maybe look for a status message
string_wait("ICH70001I")

# do something useful
string_wait("***")
em.send_enter()
string_wait("READY")
em.send_string("logon\\n")
string_wait("LOGGED OFF")

# disconnect from host
em.terminate()
