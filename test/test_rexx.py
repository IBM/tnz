from tnz import rexx

def test_right():
    assert rexx.right("",1) == " "
    assert rexx.right("",2) == "  "

def test_left():
    assert rexx.left("",1) == " "
    assert rexx.left("",2) == "  "

def test_strip():
    assert rexx.strip('  ab c  ') == 'ab c'
    assert rexx.strip('  ab c  ','L') == 'ab c  '
    assert rexx.strip('  ab c  ','t') == '  ab c'
    assert rexx.strip('12.7000',char='0') == '12.7'
    assert rexx.strip('0012.700',char='0') == '12.7'

def test_substr():
    assert rexx.substr("",2,1) == " "
    assert rexx.substr("",2,2) == "  "
    assert rexx.substr("",2,2) == "  "
    assert rexx.substr("",-1,-1) == " "
    assert rexx.substr("",-2,-1) == " "
    assert rexx.substr("",-2,-2) == "  "
    assert rexx.substr("",-2,-2) == "  "
    assert rexx.substr('abc',2) == 'bc'
    assert rexx.substr('abc',2,4) == 'bc  '
    assert rexx.substr('abc',2,6,'.') == 'bc....'


def test_more():
    assert rexx.right(" a",1) == "a"
    assert rexx.right(" a",2) == " a"
    assert rexx.left("a ",1) == "a"
    assert rexx.left("a ",2) == "a "
    assert rexx.substr("a",1,1) == "a"
    assert rexx.substr(" a",2,1) == "a"
    assert rexx.substr(" a",1,2) == " a"
    assert rexx.substr(" a",2,2) == "a "
    assert rexx.substr("a",-1,-1) == "a"
    assert rexx.substr("a ",-2,-1) == "a"
    assert rexx.substr(" a",-1,-2) == " a"
    assert rexx.substr("a ",-2,-2) == " a"

    assert rexx.word("a b c d e",4) == "d"
    assert rexx.words("a b c d e") == 5
    assert rexx.right("abcde",3) == "cde"
    #assert rexx.num("5bcde") == 5
    assert rexx.left("abcde",1+2) == "abc"
    #assert rexx.stripl("   ab de ") == "ab de "
    #assert rexx.stript("   ab de ") == "   ab de"

    assert rexx.wordindex("Now is the time",3) == 8
    assert rexx.wordindex("Now is the time",6) == 0

    assert rexx.wordindex("a b c d e",1) == 1
    assert rexx.wordindex("a b c d e",2) == 3
    assert rexx.wordindex("a b c d e",5) == 9
    assert rexx.wordindex("a b c d e",6) == 0

    assert rexx.subword("Now is the time",2,2) == "is the"
    assert rexx.subword("Now is the time",3) == "the time"
    assert rexx.subword("Now is the time",5) == ""

    assert rexx.subword("a b c d e",1) == "a b c d e"
    assert rexx.subword("a b c d e",2) == "b c d e"
    assert rexx.subword("a b c d e",3) == "c d e"
    assert rexx.subword("a b c d e",5) == "e"
    assert rexx.subword("a b c d e",6) == ""
    assert rexx.subword("a b c d e",7) == ""

    assert rexx.subword("a b c d e",1,1) == "a"
    assert rexx.subword("a b c d e",2,1) == "b"
    assert rexx.subword("a b c d e",3,1) == "c"
    assert rexx.subword("a b c d e",5,1) == "e"
    assert rexx.subword("a b c d e",6,1) == ""
    assert rexx.subword("a b c d e",7,1) == ""

    assert rexx.subword("a b c d e",1,2) == "a b"
    assert rexx.subword("a b c d e",2,2) == "b c"
    assert rexx.subword("a b c d e",3,2) == "c d"
    assert rexx.subword("a b c d e",5,2) == "e"
    assert rexx.subword("a b c d e",6,2) == ""
    assert rexx.subword("a b c d e",7,2) == ""

    assert rexx.delword("Now is the time ",3) == "Now is "
    assert rexx.delword("Now is the  time",5) == "Now is the  time"
    assert rexx.delword("Now is   the time",3,1) == "Now is   time"
    assert rexx.delword("Now is the  time",2,2) == "Now time"

    assert rexx.delword("a b c d e",1) == ""
    assert rexx.delword(" a b c d e",1) == " "
    assert rexx.delword("a b c d e",2) == "a "
    assert rexx.delword("a b c d e",3) == "a b "
    assert rexx.delword("a b c d e",5) == "a b c d "
    assert rexx.delword("a b c d e",6) == "a b c d e"
    assert rexx.delword("a b c d e",7) == "a b c d e"

    assert rexx.delword("a b c d e",1,1) == "b c d e"
    assert rexx.delword(" a b c d e",1,1) == " b c d e"
    assert rexx.delword("a b c d e",2,1) == "a c d e"
    assert rexx.delword("a b c d e",3,1) == "a b d e"
    assert rexx.delword("a b c d e",5,1) == "a b c d "
    assert rexx.delword("a b c d e",6,1) == "a b c d e"
    assert rexx.delword("a b c d e",7,1) == "a b c d e"

    # is this supported?
    #assert rexx.delword("a b c d e","c") == "a b d e"
    #assert rexx.delword("a b c c d e","c") == "a b c d e"
    #assert rexx.delword("a b c d c e","c",4) == "a b c d e"

    assert rexx.space("abc  def  ") == "abc def"
    assert rexx.space("  abc def",3) == "abc   def"
    assert rexx.space("abc  def  ",1) == "abc def"
    assert rexx.space("abc  def  ",0) == "abcdef"
    assert rexx.space("abc  def  ",2,"+") == "abc++def"

    assert rexx.wordpos("the","now is the time") == 3
    assert rexx.wordpos("The","now is the time") == 0
    assert rexx.wordpos("is the","now is the time") == 2
    assert rexx.wordpos("is   the","now is the time") == 2
    assert rexx.wordpos("is   time","now is   the time") == 0
    assert rexx.wordpos("be","To be or not to be") == 2
    assert rexx.wordpos("be","To be or not to be",3) == 6

