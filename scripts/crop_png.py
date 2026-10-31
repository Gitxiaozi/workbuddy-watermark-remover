import zlib, struct, sys

def read_png(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8
    idat = b''
    ihdr = None
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+ln]
        if typ == b'IHDR':
            ihdr = chunk
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
        pos += 12 + ln
    return ihdr, idat

def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c

def unfilter(raw, w, h, bpp):
    stride = w * bpp
    out = bytearray(stride * h)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ft = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos+stride]); pos += stride
        if ft == 0:
            pass
        elif ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i-bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                c = prev[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + paeth(a, prev[i], c)) & 0xFF
        else:
            raise ValueError('bad filter %d' % ft)
        out[y*stride:(y+1)*stride] = line
        prev = line
    return out

def write_png(path, w, h, bpp, colortype, px):
    stride = w * bpp
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y*stride:(y+1)*stride]
    def chunk(typ, payload):
        return struct.pack('>I', len(payload)) + typ + payload + struct.pack('>I', zlib.crc32(typ + payload) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, colortype, 0, 0, 0)
    out = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b'')
    open(path, 'wb').write(out)

def main():
    src, dst, cut = sys.argv[1], sys.argv[2], int(sys.argv[3])
    ihdr, idat = read_png(src)
    w, h, bitdepth, colortype = struct.unpack('>IIBB', ihdr[:10])
    print('src', w, h, 'bitdepth', bitdepth, 'colortype', colortype)
    assert bitdepth == 8, bitdepth
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[colortype]
    px = unfilter(zlib.decompress(idat), w, h, bpp)
    nh = h - cut
    write_png(dst, w, nh, bpp, colortype, px)
    print('dst', w, nh)


if __name__ == '__main__':
    main()
