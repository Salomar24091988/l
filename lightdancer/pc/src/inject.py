"""Добавляет в onefile-exe PyInstaller скрипт-заплатку перед точкой входа."""
import marshal, struct, sys, zlib

MAGIC = b"MEI\014\013\012\013\016"
COOKIE = "!8sIIii64s"
ENTRY = "!IIIIBc"

def read(path):
    data = open(path, "rb").read()
    pos = data.rfind(MAGIC)
    magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack_from(COOKIE, data, pos)
    tail = data[pos + struct.calcsize(COOKIE):]
    start = pos + struct.calcsize(COOKIE) - pkg_len
    toc, p = [], start + toc_off
    end = p + toc_len
    while p < end:
        size, epos, clen, ulen, flag, typ = struct.unpack_from(ENTRY, data, p)
        name = data[p + struct.calcsize(ENTRY):p + size].rstrip(b"\0").decode("utf-8")
        toc.append([name, flag, typ, data[start + epos:start + epos + clen], ulen])
        p += size
    return data[:start], toc, pyver, pylib, tail

def write(path, stub, toc, pyver, pylib, tail):
    body, entries = bytearray(), bytearray()
    for name, flag, typ, blob, ulen in toc:
        pos = len(body)
        body += blob
        nm = name.encode("utf-8") + b"\0"
        base = struct.calcsize(ENTRY)
        size = base + len(nm)
        size += (16 - size % 16) % 16
        entries += struct.pack(ENTRY, size, pos, len(blob), ulen, flag, typ) + nm.ljust(size - base, b"\0")
    toc_off = len(body)
    pkg_len = len(body) + len(entries) + struct.calcsize(COOKIE)
    cookie = struct.pack(COOKIE, MAGIC, pkg_len, toc_off, len(entries), pyver, pylib)
    open(path, "wb").write(stub + bytes(body) + bytes(entries) + cookie + tail)

if __name__ == "__main__":
    src, hook_src, out, before = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    stub, toc, pyver, pylib, tail = read(src)
    names = [t[0] for t in toc]
    assert "pyi_rth_wheel" not in names
    code = compile(open(hook_src, encoding="utf-8").read(), "pyi_rth_wheel.py", "exec")
    raw = marshal.dumps(code)
    entry = ["pyi_rth_wheel", 1, b"s", zlib.compress(raw, 9), len(raw)]
    toc.insert(names.index(before), entry)
    write(out, stub, toc, pyver, pylib, tail)
    # проверка: перечитать
    stub2, toc2, *_ = read(out)
    assert stub2 == stub and [t[0] for t in toc2] == [t[0] for t in toc]
    for a, b in zip(toc, toc2):
        assert a[3] == b[3] and a[1:3] == b[1:3]
    print("ok", len(toc2), "entries; scripts:", [t[0] for t in toc2 if t[2] == b"s"], "tail", len(tail))
