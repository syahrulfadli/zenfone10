#!/usr/bin/env python3
"""Reconstruct one full-OTA partition image from an Android payload ZIP."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import lzma
import sys
import zipfile
from pathlib import Path

from payload_manifest import MetadataError, fields


OP_NAMES = {0: "REPLACE", 1: "REPLACE_BZ", 8: "REPLACE_XZ"}


def parse_payload_manifest(stream):
    header = stream.read(20)
    if len(header) != 20 or header[:4] != b"CrAU":
        raise MetadataError("invalid or truncated payload header")
    version = int.from_bytes(header[4:12], "big")
    manifest_size = int.from_bytes(header[12:20], "big")
    if version < 2:
        raise MetadataError(f"payload version {version} is unsupported")
    sig_size_raw = stream.read(4)
    if len(sig_size_raw) != 4:
        raise MetadataError("truncated metadata signature size")
    metadata_sig_size = int.from_bytes(sig_size_raw, "big")
    if manifest_size > 64 * 1024 * 1024:
        raise MetadataError("manifest exceeds the 64 MiB safety limit")
    manifest = stream.read(manifest_size)
    if len(manifest) != manifest_size:
        raise MetadataError("truncated payload manifest")
    data_base = 24 + manifest_size + metadata_sig_size
    return manifest, data_base


def parse_operation(data: bytes) -> dict:
    operation = {"type": None, "offset": 0, "length": 0, "extents": []}
    for number, wire_type, value in fields(data):
        if number == 1 and wire_type == 0:
            operation["type"] = value
        elif number == 2 and wire_type == 0:
            operation["offset"] = value
        elif number == 3 and wire_type == 0:
            operation["length"] = value
        elif number == 6 and wire_type == 2:
            extent = {"start": None, "blocks": None}
            for field, wire, item in fields(value):
                if field == 1 and wire == 0:
                    extent["start"] = item
                elif field == 2 and wire == 0:
                    extent["blocks"] = item
            if extent["start"] is None or extent["blocks"] is None:
                raise MetadataError("destination extent is incomplete")
            operation["extents"].append(extent)
    if operation["type"] is None:
        raise MetadataError("install operation is missing its type")
    return operation


def find_partition(manifest: bytes, wanted: str):
    block_size = 4096
    selected = None
    for number, wire_type, value in fields(manifest):
        if number == 3 and wire_type == 0:
            block_size = value
        elif number == 13 and wire_type == 2:
            name = None
            size = None
            expected_hash = None
            operations = []
            for field, wire, item in fields(value):
                if field == 1 and wire == 2:
                    name = item.decode("utf-8", errors="strict")
                elif field == 7 and wire == 2:
                    for info_field, info_wire, info_value in fields(item):
                        if info_field == 1 and info_wire == 0:
                            size = info_value
                        elif info_field == 2 and info_wire == 2:
                            expected_hash = info_value
                elif field == 8 and wire == 2:
                    operations.append(parse_operation(item))
            if name == wanted:
                if size is None:
                    raise MetadataError(f"partition {wanted!r} has no target size")
                if selected is not None:
                    raise MetadataError(f"duplicate partition {wanted!r} in manifest")
                selected = (size, expected_hash, operations)
    if selected is None:
        raise MetadataError(f"partition {wanted!r} is absent from the payload")
    return block_size, selected


def extract_partition(stream, data_base: int, payload_size: int, block_size: int,
                       size: int, operations: list[dict], output: Path) -> bytes:
    digest = hashlib.sha256()
    # Exclusive creation prevents replacing an existing file.
    with output.open("xb") as destination:
        destination.truncate(size)
        for operation in operations:
            op_type = operation["type"]
            if op_type not in OP_NAMES:
                raise MetadataError(
                    f"unsupported operation {op_type}; this helper handles full-payload replacements only"
                )
            start = data_base + operation["offset"]
            end = start + operation["length"]
            if end > payload_size or end < start:
                raise MetadataError("operation data range exceeds payload bounds")
            stream.seek(start)
            blob = stream.read(operation["length"])
            if len(blob) != operation["length"]:
                raise MetadataError("operation data is truncated")
            if op_type == 0:
                decoded = blob
            elif op_type == 1:
                decoded = bz2.decompress(blob)
            else:
                decoded = lzma.decompress(blob)

            cursor = 0
            for extent in operation["extents"]:
                extent_capacity = extent["blocks"] * block_size
                start_block = extent["start"]
                if start_block == (1 << 64) - 1:
                    cursor += extent_capacity
                    continue
                if cursor + extent_capacity > len(decoded):
                    raise MetadataError("decompressed operation is shorter than its destination extents")
                byte_offset = start_block * block_size
                if byte_offset + extent_capacity > size:
                    raise MetadataError("destination extent exceeds partition size")
                destination.seek(byte_offset)
                destination.write(decoded[cursor:cursor + extent_capacity])
                cursor += extent_capacity
            if cursor != len(decoded):
                raise MetadataError("decompressed operation length does not match destination extents")

        destination.flush()

    with output.open("rb") as image:
        for chunk in iter(lambda: image.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct a single partition from a full Android OTA payload ZIP."
    )
    parser.add_argument("archive", type=Path, help="firmware ZIP archive")
    parser.add_argument("partition", help="partition name, for example abl")
    parser.add_argument("output", type=Path, help="new image path; existing files are never overwritten")
    args = parser.parse_args()

    output_preexisted = args.output.exists()
    try:
        with zipfile.ZipFile(args.archive) as archive:
            info = archive.getinfo("payload.bin")
            with archive.open("payload.bin") as payload:
                manifest, data_base = parse_payload_manifest(payload)
                block_size, (size, expected_hash, operations) = find_partition(manifest, args.partition)
                if not operations:
                    raise MetadataError("partition has no replacement operations")
                if any(operation["type"] not in OP_NAMES for operation in operations):
                    raise MetadataError("partition contains unsupported delta operations")
                actual_hash = extract_partition(
                    payload, data_base, info.file_size, block_size, size, operations, args.output
                )
    except (OSError, KeyError, zipfile.BadZipFile, MetadataError, EOFError, lzma.LZMAError,
            UnicodeError) as exc:
        if not output_preexisted:
            args.output.unlink(missing_ok=True)
        print(f"Cannot extract partition: {exc}", file=sys.stderr)
        return 2

    matches = expected_hash is not None and actual_hash == expected_hash
    print(f"Partition: {args.partition}")
    print(f"Image size: {size:,} bytes")
    print(f"Operations: {len(operations)} ({', '.join(OP_NAMES[op['type']] for op in operations)})")
    print(f"Manifest image SHA-256: {actual_hash.hex()}")
    print(f"Partition hash matches manifest: {matches}")
    print(f"Output: {args.output}")
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
