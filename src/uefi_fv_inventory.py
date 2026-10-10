#!/usr/bin/env python3
"""List UEFI firmware-volume files and section types without extracting them."""

from __future__ import annotations

import argparse
import struct
import sys
import uuid
from pathlib import Path


FILE_TYPES = {
    0x01: "RAW",
    0x02: "FREEFORM",
    0x03: "SEC_CORE",
    0x04: "PEI_CORE",
    0x05: "PEIM",
    0x06: "DXE_CORE",
    0x07: "DRIVER",
    0x08: "COMBINED_PEIM_DRIVER",
    0x09: "APPLICATION",
    0x0A: "SMM",
    0x0B: "FV_IMAGE",
    0x0C: "COMBINED_SMM_DXE",
    0xF0: "PAD",
}
SECTION_TYPES = {
    0x01: "COMPRESSION",
    0x02: "GUID_DEFINED",
    0x10: "PE32",
    0x11: "PIC",
    0x12: "TE",
    0x13: "DXE_DEPEX",
    0x14: "VERSION",
    0x15: "UI",
    0x16: "COMPAT16",
    0x17: "FIRMWARE_VOLUME_IMAGE",
    0x18: "FREEFORM_SUBTYPE_GUID",
    0x19: "RAW",
    0x1B: "MM_DEPEX",
}


class FirmwareFormatError(Exception):
    """Raised when a firmware-volume structure is malformed."""


def inspect_volume(data: bytes, base: int):
    if base < 0 or base + 56 > len(data) or data[base + 40:base + 44] != b"_FVH":
        raise FirmwareFormatError("no valid _FVH signature at the requested offset")
    volume_length = struct.unpack_from("<Q", data, base + 32)[0]
    header_length = struct.unpack_from("<H", data, base + 48)[0]
    if volume_length < header_length or base + volume_length > len(data):
        raise FirmwareFormatError("firmware-volume bounds are invalid")
    if header_length < 56:
        raise FirmwareFormatError("firmware-volume header is too short")

    files = []
    cursor = (base + header_length + 7) & ~7
    limit = base + volume_length
    while cursor + 24 <= limit:
        header = data[cursor:cursor + 24]
        if header == b"\xff" * 24:
            # Erased/padding slots can precede a file aligned to a larger
            # boundary, so scan the next 8-byte-aligned candidate.
            cursor += 8
            continue
        if header == b"\x00" * 24:
            break
        name = uuid.UUID(bytes_le=header[:16])
        file_type = header[18]
        attributes = header[19]
        file_size = int.from_bytes(header[20:23], "little")
        header_size = 24
        if file_size == 0xFFFFFF and attributes & 0x01:
            if cursor + 32 > limit:
                cursor += 8
                continue
            file_size = struct.unpack_from("<Q", data, cursor + 24)[0]
            header_size = 32
        if file_type not in FILE_TYPES or file_size < header_size or cursor + file_size > limit:
            # Some platform images put wrapper/alignment data in front of the
            # first FFS file. Only accept aligned candidates with plausible
            # PI file types and sizes.
            cursor += 8
            continue
        if file_type == 0xF0:
            cursor = (cursor + file_size + 7) & ~7
            continue

        sections = []
        section_cursor = cursor + header_size
        file_end = cursor + file_size
        while section_cursor + 4 <= file_end:
            section_size = int.from_bytes(data[section_cursor:section_cursor + 3], "little")
            section_type = data[section_cursor + 3]
            section_header_size = 4
            if section_size == 0xFFFFFF:
                if section_cursor + 8 > file_end:
                    raise FirmwareFormatError("truncated extended section header")
                section_size = struct.unpack_from("<I", data, section_cursor + 4)[0]
                section_header_size = 8
            if section_size < section_header_size or section_cursor + section_size > file_end:
                break
            sections.append((section_type, section_size))
            section_cursor = (section_cursor + section_size + 3) & ~3

        files.append((cursor, name, file_type, attributes, file_size, sections))
        cursor = (cursor + file_size + 7) & ~7
    return volume_length, header_length, files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory UEFI FV/FFS metadata without extracting file contents."
    )
    parser.add_argument("image", type=Path, help="offline firmware image, such as an extracted ABL")
    parser.add_argument(
        "--offset", type=lambda value: int(value, 0),
        help="firmware-volume base offset; default: locate the first _FVH signature",
    )
    args = parser.parse_args()

    try:
        data = args.image.read_bytes()
        if args.offset is None:
            signature = data.find(b"_FVH")
            if signature < 0:
                raise FirmwareFormatError("no _FVH signature found")
            base = signature - 40
        else:
            base = args.offset
        volume_length, header_length, files = inspect_volume(data, base)
    except (OSError, FirmwareFormatError, ValueError) as exc:
        print(f"Cannot inventory firmware volume: {exc}", file=sys.stderr)
        return 2

    print(f"Image: {args.image.name}")
    print(f"FV base: 0x{base:x}; size: {volume_length:,}; header: {header_length} bytes")
    print(f"FFS files: {len(files)}")
    for offset, name, file_type, attributes, size, sections in files:
        type_name = FILE_TYPES.get(file_type, f"TYPE_0x{file_type:02x}")
        section_summary = ", ".join(
            f"{SECTION_TYPES.get(kind, f'TYPE_0x{kind:02x}')}:{section_size}"
            for kind, section_size in sections
        ) or "no top-level sections parsed"
        print(
            f"  0x{offset:08x} {name} {type_name} size={size:,} "
            f"attrs=0x{attributes:02x} sections=[{section_summary}]"
        )
    print("Metadata only: no FFS contents were extracted or executed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
