#!/usr/bin/env python3
"""Edit device_config.equalizer inside the station's user_config.dat container.

Container layout (protobuf-like):
   0x0a <varint L1> <payload1>
   payload1 = 0x0a <varint 10> <uid 10 bytes> 0x12 <varint L2> <json L2 bytes>
Everything after payload1 is kept byte-for-byte.
"""
import json
import sys


def read_varint(buf, pos):
    shift = 0
    value = 0
    while True:
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7


def write_varint(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def parse(data):
    if data[0] != 0x0A:
        raise ValueError("unexpected container tag")
    l1, pos = read_varint(data, 1)
    payload = data[pos:pos + l1]
    rest = data[pos + l1:]
    if payload[0] != 0x0A:
        raise ValueError("unexpected uid tag")
    ulen, p = read_varint(payload, 1)
    uid = payload[p:p + ulen]
    p += ulen
    if payload[p] != 0x12:
        raise ValueError("unexpected json tag")
    l2, p = read_varint(payload, p + 1)
    raw_json = payload[p:p + l2]
    tail = payload[p + l2:]
    return uid, raw_json, rest, tail


def build(uid, raw_json, rest, tail=b""):
    inner = (b"\x0a" + write_varint(len(uid)) + uid
             + b"\x12" + write_varint(len(raw_json)) + raw_json + tail)
    return b"\x0a" + write_varint(len(inner)) + inner + rest


def main():
    path = sys.argv[1]
    data = open(path, "rb").read()
    uid, raw_json, rest, tail = parse(data)
    if len(sys.argv) == 2:
        # round-trip check
        print("roundtrip_ok", build(uid, raw_json, rest, tail) == data, "json_len", len(raw_json))
        return
    cfg = json.loads(raw_json)
    eq = cfg["device_config"]["equalizer"]
    print("current:", json.dumps(eq, ensure_ascii=False))
    new = json.loads(open(sys.argv[2][1:], "r", encoding="utf-8").read() if sys.argv[2].startswith("@") else sys.argv[2])
    cfg["device_config"]["equalizer"] = new
    raw_new = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).encode()
    out = build(uid, raw_new, rest, tail)
    open(path, "wb").write(out)
    print("written", len(out), "bytes (was", len(data), ")")


if __name__ == "__main__":
    main()
