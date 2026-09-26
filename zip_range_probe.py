"""List a remote ZIP or extract one small member using HTTP byte ranges.

Requires only the Python standard library. The complete archive is never fetched.
"""

import argparse
import json
import struct
import sys
import urllib.request
import zlib
from pathlib import Path


TAIL = 65536
MAX_DIRECTORY = 8_000_000
MAX_MEMBER = 4_000_000


def get_range(url: str, start: int | None, end: int | None) -> tuple[bytes, int]:
    if start is None:
        header = f"bytes=-{end}"
    else:
        header = f"bytes={start}-{end}"
    request = urllib.request.Request(url, headers={"Range": header})
    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 206:
            raise RuntimeError(f"server did not honor Range: HTTP {response.status}")
        content_range = response.headers.get("Content-Range", "")
        if "/" not in content_range:
            raise RuntimeError("missing Content-Range")
        total = int(content_range.rsplit("/", 1)[1])
        data = response.read(MAX_DIRECTORY + 1)
    if len(data) > MAX_DIRECTORY:
        raise RuntimeError("range response exceeds directory limit")
    if start is not None and len(data) != end - start + 1:
        raise RuntimeError("short range response")
    return data, total


def directory(url: str) -> list[dict]:
    tail, total = get_range(url, None, TAIL)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise RuntimeError("ZIP end record not found in last 64 KiB")
    end = struct.unpack_from("<IHHHHIIH", tail, eocd)
    count, size, offset = end[4], end[5], end[6]
    if count == 0xFFFF or size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
        loc = tail.rfind(b"PK\x06\x07", 0, eocd)
        if loc < 0:
            raise RuntimeError("ZIP64 locator missing")
        zip64_offset = struct.unpack_from("<IIQI", tail, loc)[2]
        record, _ = get_range(url, zip64_offset, zip64_offset + 55)
        if record[:4] != b"PK\x06\x06":
            raise RuntimeError("ZIP64 end record missing")
        fields = struct.unpack_from("<IQHHIIQQQQ", record)
        count, size, offset = fields[7], fields[8], fields[9]
    if size > MAX_DIRECTORY:
        raise RuntimeError(f"central directory exceeds {MAX_DIRECTORY} bytes")
    if offset + size > total:
        raise RuntimeError("central directory exceeds archive")
    raw, _ = get_range(url, offset, offset + size - 1)
    entries = []
    i = 0
    while i < len(raw):
        if raw[i:i + 4] != b"PK\x01\x02":
            raise RuntimeError(f"bad central-directory entry at byte {i}")
        h = struct.unpack_from("<IHHHHHHIIIHHHHHII", raw, i)
        name_len, extra_len, comment_len = h[10:13]
        name_raw = raw[i + 46:i + 46 + name_len]
        name = name_raw.decode("utf-8" if h[3] & 0x800 else "cp437")
        extra = raw[i + 46 + name_len:i + 46 + name_len + extra_len]
        compressed, uncompressed, local_offset = h[8], h[9], h[16]
        pos = 0
        while pos + 4 <= len(extra):
            tag, length = struct.unpack_from("<HH", extra, pos)
            value = extra[pos + 4:pos + 4 + length]
            if tag == 1:
                j = 0
                if uncompressed == 0xFFFFFFFF:
                    uncompressed = struct.unpack_from("<Q", value, j)[0]
                    j += 8
                if compressed == 0xFFFFFFFF:
                    compressed = struct.unpack_from("<Q", value, j)[0]
                    j += 8
                if local_offset == 0xFFFFFFFF:
                    local_offset = struct.unpack_from("<Q", value, j)[0]
            pos += 4 + length
        entries.append({"name": name, "compressed": compressed,
                        "uncompressed": uncompressed, "offset": local_offset,
                        "method": h[4], "crc32": h[7]})
        i += 46 + name_len + extra_len + comment_len
    if len(entries) != count:
        raise RuntimeError(f"entry count mismatch: {len(entries)} != {count}")
    return entries


def extract(url: str, entry: dict) -> bytes:
    if max(entry["compressed"], entry["uncompressed"]) > MAX_MEMBER:
        raise RuntimeError(f"member exceeds {MAX_MEMBER} byte micro-sample limit")
    offset = entry["offset"]
    header, _ = get_range(url, offset, offset + 29)
    h = struct.unpack_from("<IHHHHHIIIHH", header)
    if h[0] != 0x04034B50:
        raise RuntimeError("bad local file header")
    start = offset + 30 + h[9] + h[10]
    raw, _ = get_range(url, start, start + entry["compressed"] - 1)
    if entry["method"] == 0:
        data = raw
    elif entry["method"] == 8:
        decoder = zlib.decompressobj(-15)
        data = decoder.decompress(raw, MAX_MEMBER + 1)
        if not decoder.eof or decoder.unconsumed_tail:
            raise RuntimeError("member exceeds decompression limit or is incomplete")
    else:
        raise RuntimeError(f"unsupported compression method {entry['method']}")
    if len(data) != entry["uncompressed"] or zlib.crc32(data) != entry["crc32"]:
        raise RuntimeError("size or CRC mismatch")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="direct URL to a public ZIP with HTTP Range support")
    parser.add_argument("--contains", help="list only members containing this substring")
    parser.add_argument("--entry", help="exact member path to extract")
    parser.add_argument("--output", type=Path, help="local output file for --entry")
    args = parser.parse_args()
    entries = directory(args.url)
    if args.entry:
        if not args.output:
            parser.error("--entry requires --output")
        matches = [entry for entry in entries if entry["name"] == args.entry]
        if len(matches) != 1:
            raise RuntimeError(f"expected one exact entry, found {len(matches)}")
        data = extract(args.url, matches[0])
        args.output.write_bytes(data)
        print(json.dumps({"entry": args.entry, "bytes": len(data), "output": str(args.output)}))
    else:
        for entry in entries:
            if not args.contains or args.contains in entry["name"]:
                print(json.dumps({k: entry[k] for k in ("name", "compressed", "uncompressed")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"zip_range_probe: {exc}", file=sys.stderr)
        sys.exit(1)
