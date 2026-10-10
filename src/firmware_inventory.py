#!/usr/bin/env python3
"""List firmware ZIP contents without extracting or modifying the archive."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

BOOT_CHAIN_HINTS = (
    "abl",
    "boot",
    "devcfg",
    "hyp",
    "keymaster",
    "modem",
    "payload",
    "sbl",
    "tz",
    "vbmeta",
    "vendor_boot",
    "xbl",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory names and sizes in an ASUS firmware ZIP without extracting it."
    )
    parser.add_argument("archive", type=Path, help="path to the locally downloaded firmware ZIP")
    parser.add_argument("--all", action="store_true", help="show every non-directory archive entry")
    args = parser.parse_args()

    if not args.archive.is_file():
        print(f"Archive not found: {args.archive}", file=sys.stderr)
        return 2

    try:
        with zipfile.ZipFile(args.archive) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"Cannot read ZIP archive: {exc}", file=sys.stderr)
        return 2

    total_bytes = sum(entry.file_size for entry in entries)
    print(f"Archive: {args.archive.name}")
    print(f"Files: {len(entries)}; total uncompressed size: {total_bytes:,} bytes")
    print("No archive entries were extracted or modified.")

    selected = entries if args.all else [
        entry for entry in entries
        if any(hint in entry.filename.lower() for hint in BOOT_CHAIN_HINTS)
    ]
    if not selected:
        print("No filenames matched the boot-chain hints. Use --all to list every entry.")
        return 0

    print("\nArchive entries:")
    for entry in selected:
        print(f"{entry.file_size:>12,}  {entry.filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
