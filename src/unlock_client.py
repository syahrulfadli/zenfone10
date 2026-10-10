#!/usr/bin/env python3
"""Guarded client for Android's standard Fastboot unlock flow."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys

TIMEOUT_SECONDS = 15


def run(args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "Command timed out"
    except OSError as exc:
        return 127, str(exc)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode, output


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded client for the standard Fastboot unlock flow.")
    parser.add_argument(
        "--request-unlock",
        action="store_true",
        help="allow a standard unlock request if the bootloader cannot report unlock permission",
    )
    options = parser.parse_args()

    fastboot = shutil.which("fastboot")
    if not fastboot:
        print("fastboot was not found. Install Android Platform Tools and retry.")
        return 1

    code, output = run([fastboot, "devices"])
    if code != 0:
        print(f"Could not list Fastboot devices: {output or 'unknown error'}")
        return 1
    device_rows = [line.split() for line in output.splitlines() if len(line.split()) >= 2]
    devices = [fields[0] for fields in device_rows]
    if len(devices) != 1:
        print(f"Expected exactly one Fastboot device; found {len(devices)}. No changes made.")
        return 1

    device = devices[0]
    device_mode = device_rows[0][1].lower()
    if "fastbootd" in device_mode:
        print("Device is in fastbootd (userspace), not bootloader Fastboot. No unlock request sent.")
        print("Switch modes with: fastboot reboot bootloader")
        return 2

    code, output = run([fastboot, "-s", device, "getvar", "is-userspace"])
    mode_match = re.search(r"is-userspace\s*:\s*(yes|no)\b", output, re.IGNORECASE)
    if mode_match and mode_match.group(1).lower() == "yes":
        print("Device is in fastbootd (userspace), not bootloader Fastboot. No unlock request sent.")
        print("Switch modes with: fastboot reboot bootloader")
        return 2
    if not mode_match and device_mode not in ("fastboot", "bootloader"):
        print("Could not verify bootloader Fastboot mode. No unlock request sent.")
        return 2

    code, output = run([fastboot, "-s", device, "flashing", "get_unlock_ability"])
    match = re.search(
        r"(?:\(bootloader\)\s*)?get_unlock_ability\s*:\s*([01])\s*$",
        output,
        re.IGNORECASE | re.MULTILINE,
    )
    ability = match.group(1) if code == 0 and match and "FAILED" not in output.upper() else None
    if ability is None:
        print("Bootloader did not provide a clear unlock permission; permission is unknown.")
        if output:
            print(output)
        if not options.request_unlock:
            print("No unlock request sent. Use --request-unlock only if you intentionally want to ask the bootloader.")
            return 2
    else:
        print(f"Fastboot reports get_unlock_ability={ability}; device serial hidden.")

    if ability == "0":
        print("Unlock is not allowed by the bootloader. No unlock command was sent.")
        return 2

    if ability is None:
        print("Permission is unknown. The bootloader will decide whether to accept the standard request.")
    print("If accepted and confirmed on the phone, unlocking may factory-reset it and erase user data.")
    print("The phone may also display a confirmation screen.")
    if input('Type SEND STANDARD UNLOCK REQUEST to continue: ').strip() != "SEND STANDARD UNLOCK REQUEST":
        print("Confirmation did not match. No changes made.")
        return 1

    code, output = run([fastboot, "-s", device, "flashing", "unlock"])
    if output:
        print(output)
    if code != 0:
        print("Fastboot rejected or failed the unlock request. No bypass was attempted.")
        return code or 1
    print("Unlock request sent. Follow the confirmation instructions shown on the phone.")
    print("This client does not confirm the on-device prompt automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
