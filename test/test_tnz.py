from tnz import tnz

def test_0fields():
    z = tnz.Tnz()
    assert list(z.fields()) == []
    assert list(z.char_addrs(0,0)) == [(0,0)]
    assert list(z.char_addrs(1,1)) == [(1,1)]
    assert list(z.char_addrs(1919,1919)) == [(1919,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,1919)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]
    assert z.field(0) == (-1, 0)
    assert z.field(1919) == (-1, 0)

    # test eraseinput
    assert z.curadd == 0
    assert z.scrstr().isspace()
    z.plane_dc[0] = 193
    z.plane_dc[1] = 193
    z.plane_dc[-1] = 193
    z.plane_dc[-2] = 193
    assert not z.scrstr().isspace()
    z.curadd = 1
    z.key_eraseinput()
    assert z.curadd == 0
    assert z.scrstr().isspace()

def test_1fields():
    z = tnz.Tnz()
    z.plane_fa[1919] = 64
    assert list(z.fields()) == [(1919,64)]
    assert list(z.char_addrs(0,0)) == [(0,1919)]
    assert list(z.char_addrs(1,1)) == [(1,1919),(0,1)]
    assert list(z.char_addrs(1918,1918)) == [(1918,1919),(0,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,1919)]

    # test eraseinput
    assert z.curadd == 0
    assert z.scrstr().isspace()
    z.plane_dc[0] = 193
    z.plane_dc[1] = 193
    z.plane_dc[1918] = 193
    z.plane_dc[1917] = 193
    assert not z.scrstr().isspace()
    z.curadd = 1
    z.key_eraseinput()
    assert z.curadd == 0
    assert z.scrstr().isspace()

    z.plane_fa[1919] = 0
    z.plane_fa[0] = 64
    assert list(z.fields()) == [(0,64)]
    assert list(z.char_addrs(1,1)) == [(1,0)]
    assert list(z.char_addrs(1919,1919)) == [(1919,0),(1,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,0),(1,1918)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]

    # test eraseinput
    assert z.curadd == 0
    assert z.scrstr().isspace()
    z.plane_dc[1] = 193
    z.plane_dc[2] = 193
    z.plane_dc[-1] = 193
    z.plane_dc[-2] = 193
    assert not z.scrstr().isspace()
    z.key_eraseinput()
    assert z.curadd == 1
    assert z.scrstr().isspace()

    z.plane_fa[0] = 0
    z.plane_fa[80] = 64
    assert list(z.fields()) == [(80,64)]
    assert list(z.char_addrs(0,0)) == [(0,80),(81,0)]
    assert list(z.char_addrs(1,1)) == [(1,80),(81,1)]
    assert list(z.char_addrs(1919,1919)) == [(1919,80),(81,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,80),(81,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,80),(81,1919)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]
    assert list(z.char_addrs(79,79)) == [(79,80),(81,79)]
    assert list(z.char_addrs(81,81)) == [(81,80)]

    # test eraseinput
    assert z.curadd == 1
    assert z.scrstr().isspace()
    z.plane_dc[0] = 193
    z.plane_dc[1] = 193
    z.plane_dc[78] = 193
    z.plane_dc[79] = 193
    z.plane_dc[81] = 193
    z.plane_dc[82] = 193
    z.plane_dc[-1] = 193
    z.plane_dc[-2] = 193
    assert not z.scrstr().isspace()
    z.key_eraseinput()
    assert z.curadd == 0
    assert z.scrstr().isspace()

def test_2fields():
    z = tnz.Tnz()
    z.plane_fa[80] = 64
    z.plane_fa[160] = 64
    assert list(z.fields()) == [(80,64),(160,64)]
    assert list(z.char_addrs(0,0)) == [(0,80),(81,160),(161,0)]
    assert list(z.char_addrs(1,1)) == [(1,80),(81,160),(161,1)]
    assert list(z.char_addrs(1919,1919)) == [(1919,80),(81,160),(161,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,80),(81,160),(161,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,80),(81,160),(161,1919)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]
    assert list(z.char_addrs(79,79)) == [(79,80),(81,160),(161,79)]
    assert list(z.char_addrs(81,81)) == [(81,160),(161,80)]

    # test eraseinput
    assert z.scrstr().isspace()
    z.plane_dc[0] = 193
    z.plane_dc[1] = 193
    z.plane_dc[78] = 193
    z.plane_dc[79] = 193
    z.plane_dc[81] = 193
    z.plane_dc[82] = 193
    z.plane_dc[158] = 193
    z.plane_dc[159] = 193
    z.plane_dc[161] = 193
    z.plane_dc[162] = 193
    z.plane_dc[-1] = 193
    z.plane_dc[-2] = 193
    assert not z.scrstr().isspace()
    z.key_eraseinput()
    assert z.curadd == 0
    assert z.scrstr().isspace()

    z.plane_fa[160] = 0
    z.plane_fa[81] = 64
    assert list(z.fields()) == [(80,64),(81,64)]
    assert list(z.char_addrs(0,0)) == [(0,80),(82,0)]
    assert list(z.char_addrs(1,1)) == [(1,80),(82,1)]
    assert list(z.char_addrs(1919,1919)) == [(1919,80),(82,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,80),(82,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,80),(82,1919)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]
    assert list(z.char_addrs(79,79)) == [(79,80),(82,79)]
    assert list(z.char_addrs(82,82)) == [(82,80)]

    # test eraseinput
    assert z.scrstr().isspace()
    z.plane_dc[0] = 193
    z.plane_dc[1] = 193
    z.plane_dc[78] = 193
    z.plane_dc[79] = 193
    z.plane_dc[82] = 193
    z.plane_dc[83] = 193
    z.plane_dc[-1] = 193
    z.plane_dc[-2] = 193
    assert not z.scrstr().isspace()
    z.key_eraseinput()
    assert z.curadd == 0
    assert z.scrstr().isspace()

    assert list(z.fields()) == [(80,64),(81,64)]
    assert list(z.char_addrs(0,0)) == [(0,80),(82,0)]
    assert list(z.char_addrs(1,1)) == [(1,80),(82,1)]
    assert list(z.char_addrs(1919,1919)) == [(1919,80),(82,1919)]
    assert list(z.char_addrs(1918,1918)) == [(1918,80),(82,1918)]
    assert list(z.char_addrs(0,1919)) == [(0,80),(82,1919)]
    assert list(z.char_addrs(1919,0)) == [(1919,0)]
    assert list(z.char_addrs(79,79)) == [(79,80),(82,79)]
    assert list(z.char_addrs(82,82)) == [(82,80)]


def test_bit6():
    # test that tnz.bit6 does GA23-0059-4 Figure D-1
    assert(tnz.bit6(0x00)==0x40)
    assert(tnz.bit6(0x01)==0xc1)
    assert(tnz.bit6(0x02)==0xc2)
    assert(tnz.bit6(0x03)==0xc3)
    assert(tnz.bit6(0x04)==0xc4)
    assert(tnz.bit6(0x05)==0xc5)
    assert(tnz.bit6(0x06)==0xc6)
    assert(tnz.bit6(0x07)==0xc7)
    assert(tnz.bit6(0x08)==0xc8)
    assert(tnz.bit6(0x09)==0xc9)
    assert(tnz.bit6(0x0a)==0x4a)
    assert(tnz.bit6(0x0b)==0x4b)
    assert(tnz.bit6(0x0c)==0x4c)
    assert(tnz.bit6(0x0d)==0x4d)
    assert(tnz.bit6(0x0e)==0x4e)
    assert(tnz.bit6(0x0f)==0x4f)
    assert(tnz.bit6(0x10)==0x50)
    assert(tnz.bit6(0x11)==0xd1)
    assert(tnz.bit6(0x12)==0xd2)
    assert(tnz.bit6(0x13)==0xd3)
    assert(tnz.bit6(0x14)==0xd4)
    assert(tnz.bit6(0x15)==0xd5)
    assert(tnz.bit6(0x16)==0xd6)
    assert(tnz.bit6(0x17)==0xd7)
    assert(tnz.bit6(0x18)==0xd8)
    assert(tnz.bit6(0x19)==0xd9)
    assert(tnz.bit6(0x1a)==0x5a)
    assert(tnz.bit6(0x1b)==0x5b)
    assert(tnz.bit6(0x1c)==0x5c)
    assert(tnz.bit6(0x1d)==0x5d)
    assert(tnz.bit6(0x1e)==0x5e)
    assert(tnz.bit6(0x1f)==0x5f)
    assert(tnz.bit6(0x20)==0x60)
    assert(tnz.bit6(0x21)==0x61)
    assert(tnz.bit6(0x22)==0xe2)
    assert(tnz.bit6(0x23)==0xe3)
    assert(tnz.bit6(0x24)==0xe4)
    assert(tnz.bit6(0x25)==0xe5)
    assert(tnz.bit6(0x26)==0xe6)
    assert(tnz.bit6(0x27)==0xe7)
    assert(tnz.bit6(0x28)==0xe8)
    assert(tnz.bit6(0x29)==0xe9)
    assert(tnz.bit6(0x2a)==0x6a)
    assert(tnz.bit6(0x2b)==0x6b)
    assert(tnz.bit6(0x2c)==0x6c)
    assert(tnz.bit6(0x2d)==0x6d)
    assert(tnz.bit6(0x2e)==0x6e)
    assert(tnz.bit6(0x2f)==0x6f)
    assert(tnz.bit6(0x30)==0xf0)
    assert(tnz.bit6(0x31)==0xf1)
    assert(tnz.bit6(0x32)==0xf2)
    assert(tnz.bit6(0x33)==0xf3)
    assert(tnz.bit6(0x34)==0xf4)
    assert(tnz.bit6(0x35)==0xf5)
    assert(tnz.bit6(0x36)==0xf6)
    assert(tnz.bit6(0x37)==0xf7)
    assert(tnz.bit6(0x38)==0xf8)
    assert(tnz.bit6(0x39)==0xf9)
    assert(tnz.bit6(0x3a)==0x7a)
    assert(tnz.bit6(0x3b)==0x7b)
    assert(tnz.bit6(0x3c)==0x7c)
    assert(tnz.bit6(0x3d)==0x7d)
    assert(tnz.bit6(0x3e)==0x7e)
    assert(tnz.bit6(0x3f)==0x7f)

def test_conv():
    # test &0x3f is sufficient to reverse bit6
    # just look for 3f in code
    assert(0x00==0x40&0x3f)
    assert(0x01==0xc1&0x3f)
    assert(0x02==0xc2&0x3f)
    assert(0x03==0xc3&0x3f)
    assert(0x04==0xc4&0x3f)
    assert(0x05==0xc5&0x3f)
    assert(0x06==0xc6&0x3f)
    assert(0x07==0xc7&0x3f)
    assert(0x08==0xc8&0x3f)
    assert(0x09==0xc9&0x3f)
    assert(0x0a==0x4a&0x3f)
    assert(0x0b==0x4b&0x3f)
    assert(0x0c==0x4c&0x3f)
    assert(0x0d==0x4d&0x3f)
    assert(0x0e==0x4e&0x3f)
    assert(0x0f==0x4f&0x3f)
    assert(0x10==0x50&0x3f)
    assert(0x11==0xd1&0x3f)
    assert(0x12==0xd2&0x3f)
    assert(0x13==0xd3&0x3f)
    assert(0x14==0xd4&0x3f)
    assert(0x15==0xd5&0x3f)
    assert(0x16==0xd6&0x3f)
    assert(0x17==0xd7&0x3f)
    assert(0x18==0xd8&0x3f)
    assert(0x19==0xd9&0x3f)
    assert(0x1a==0x5a&0x3f)
    assert(0x1b==0x5b&0x3f)
    assert(0x1c==0x5c&0x3f)
    assert(0x1d==0x5d&0x3f)
    assert(0x1e==0x5e&0x3f)
    assert(0x1f==0x5f&0x3f)
    assert(0x20==0x60&0x3f)
    assert(0x21==0x61&0x3f)
    assert(0x22==0xe2&0x3f)
    assert(0x23==0xe3&0x3f)
    assert(0x24==0xe4&0x3f)
    assert(0x25==0xe5&0x3f)
    assert(0x26==0xe6&0x3f)
    assert(0x27==0xe7&0x3f)
    assert(0x28==0xe8&0x3f)
    assert(0x29==0xe9&0x3f)
    assert(0x2a==0x6a&0x3f)
    assert(0x2b==0x6b&0x3f)
    assert(0x2c==0x6c&0x3f)
    assert(0x2d==0x6d&0x3f)
    assert(0x2e==0x6e&0x3f)
    assert(0x2f==0x6f&0x3f)
    assert(0x30==0xf0&0x3f)
    assert(0x31==0xf1&0x3f)
    assert(0x32==0xf2&0x3f)
    assert(0x33==0xf3&0x3f)
    assert(0x34==0xf4&0x3f)
    assert(0x35==0xf5&0x3f)
    assert(0x36==0xf6&0x3f)
    assert(0x37==0xf7&0x3f)
    assert(0x38==0xf8&0x3f)
    assert(0x39==0xf9&0x3f)
    assert(0x3a==0x7a&0x3f)
    assert(0x3b==0x7b&0x3f)
    assert(0x3c==0x7c&0x3f)
    assert(0x3d==0x7d&0x3f)
    assert(0x3e==0x7e&0x3f)
    assert(0x3f==0x7f&0x3f)
