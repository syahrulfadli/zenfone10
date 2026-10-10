#!/usr/bin/env python3
"""Read basic partition metadata from an Android OTA payload inside a ZIP."""

from __future__ import annotations

import argparse
from collections import Counter
import struct
import sys
import zipfile
from pathlib import Path

OPERATION_NAMES = {
    0: "REPLACE",
    1: "REPLACE_BZ",
    2: "MOVE",
    3: "BSDIFF",
    4: "SOURCE_COPY",
    5: "SOURCE_BSDIFF",
    6: "ZERO",
    7: "DISCARD",
    8: "REPLACE_XZ",
    9: "PUFFDIFF",
    10: "BROTLI_BSDIFF",
    11: "ZUCCHINI",
    12: "LZ4DIFF_BSDIFF",
    13: "LZ4DIFF_PUFFDIFF",
}
BOOT_CHAIN_NAMES = {
    "abl", "aop", "cpucp", "devcfg", "hyp", "keymaster", "qupfw",
    "shrm", "tz", "uefi", "uefisecapp", "vbmeta", "vbmeta_system",
    "xbl", "xbl_config", "xbl_ramdump", "xrom",
}


class MetadataError(Exception):
    """Raised when the OTA payload metadata is malformed or unsupported."""


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise MetadataError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
    raise MetadataError("protobuf varint is too long")


def fields(data: bytes):
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        number, wire_type = tag >> 3, tag & 7
        if number == 0:
            raise MetadataError("invalid protobuf field number 0")
        if wire_type == 0:
            value, offset = read_varint(data, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise MetadataError("truncated fixed64 field")
            value, offset = data[offset:end], end
        elif wire_type == 2:
            size, offset = read_varint(data, offset)
            end = offset + size
            if end > len(data):
                raise MetadataError("truncated length-delimited field")
            value, offset = data[offset:end], end
        elif wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise MetadataError("truncated fixed32 field")
            value, offset = data[offset:end], end
        else:
            raise MetadataError(f"unsupported protobuf wire type {wire_type}")
        yield number, wire_type, value


def parse_payload(stream) -> tuple[int, bytes]:
    header = stream.read(20)
    if len(header) < 20 or header[:4] != b"CrAU":
        raise MetadataError("payload header is missing or has invalid magic")
    version, manifest_size = struct.unpack(">QQ", header[4:20])
    if version < 2:
        raise MetadataError(f"payload version {version} is unsupported by this reader")
    signature_size_bytes = stream.read(4)
    if len(signature_size_bytes) != 4:
        raise MetadataError("payload metadata signature size is truncated")
    signature_size = struct.unpack(">I", signature_size_bytes)[0]
    if manifest_size > 64 * 1024 * 1024:
        raise MetadataError("manifest exceeds the 64 MiB safety limit")
    manifest = stream.read(manifest_size)
    if len(manifest) != manifest_size:
        raise MetadataError("payload manifest is truncated")
    return version, manifest


def describe_manifest(manifest: bytes):
    partitions = []
    patch_level = None
    minor_version = None
    for number, wire_type, value in fields(manifest):
        if number == 13 and wire_type == 2:
            name = None
            target_size = None
            operations = Counter()
            for field, wire, item in fields(value):
                if field == 1 and wire == 2:
                    name = item.decode("utf-8", errors="strict")
                elif field == 7 and wire == 2:
                    target_size = next(
                        (nested for info_field, info_wire, nested in fields(item)
                         if info_field == 1 and info_wire == 0),
                        None,
                    )
                elif field == 8 and wire == 2:
                    op_type = next(
                        (nested for op_field, op_wire, nested in fields(item)
                         if op_field == 1 and op_wire == 0),
                        None,
                    )
                    if op_type is None:
                        raise MetadataError("install operation is missing its required type")
                    operations[OPERATION_NAMES.get(op_type, f"UNKNOWN_{op_type}")] += 1
            if name is None:
                raise MetadataError("partition metadata is missing its required name")
            partitions.append((name, target_size, operations))
        elif number == 18 and wire_type == 2:
            patch_level = value.decode("utf-8", errors="strict")
        elif number == 12 and wire_type == 0:
            minor_version = value
    return partitions, patch_level, minor_version


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read OTA payload header and partition names without extracting images."
    )
    parser.add_argument("archive", type=Path, help="firmware ZIP archive")
    parser.add_argument("--entry", default="payload.bin", help="payload entry name (default: payload.bin)")
    args = parser.parse_args()

    try:
        with zipfile.ZipFile(args.archive) as archive:
            with archive.open(args.entry) as payload:
                version, manifest = parse_payload(payload)
        partitions, patch_level, minor_version = describe_manifest(manifest)
    except (OSError, KeyError, zipfile.BadZipFile, MetadataError, UnicodeError) as exc:
        print(f"Cannot read payload metadata: {exc}", file=sys.stderr)
        return 2

    print(f"Archive: {args.archive.name}")
    print(f"Payload format version: {version}")
    print(f"Manifest metadata size: {len(manifest):,} bytes")
    print(f"Update type: {'full' if minor_version == 0 else 'delta/unspecified'}")
    print(f"Security patch level: {patch_level or '(not present)'}")
    boot_chain = [partition for partition in partitions if partition[0] in BOOT_CHAIN_NAMES]
    print(f"Partitions in payload: {len(partitions)}")
    print(f"Boot-chain metadata ({len(boot_chain)} partitions):")
    for name, target_size, operations in boot_chain:
        size_text = f"{target_size:,} bytes" if target_size is not None else "size unavailable"
        operation_text = ", ".join(
            f"{operation}={count}" for operation, count in sorted(operations.items())
        ) or "no operations listed"
        print(f"  {name}: target {size_text}; operations: {operation_text}")
    print("Only the payload header and manifest were read; no partition images were extracted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
