#!/usr/bin/env python3
"""Read-only ADB/Fastboot diagnostics for an ASUS Zenfone 10."""

from __future__ import annotations

import shutil
import re
import subprocess
import sys
from dataclasses import dataclass


TIMEOUT_SECONDS = 8
ADB_PROPERTIES = (
    "ro.product.model",
    "ro.build.version.release",
    "ro.build.version.incremental",
    "ro.build.version.security_patch",
    "ro.oem_unlock_supported",
    "ro.boot.flash.locked",
    "ro.boot.vbmeta.device_state",
    "persist.sys.oem_unlock_allowed",
)
FASTBOOT_VARIABLES = ("product", "unlocked", "secure", "is-userspace")


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(args: list[str]) -> CommandResult:
    """Run a fixed ADB/Fastboot argument list without invoking a shell."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout.strip(), result.stderr.strip())
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "Command timed out")
    except OSError as exc:
        return CommandResult(127, "", str(exc))


def adb_devices(adb: str) -> list[tuple[str, str]]:
    result = run_command([adb, "devices"])
    if result.returncode != 0:
        print(f"ADB error: {result.stderr or result.stdout or 'unknown error'}")
        return []

    devices: list[tuple[str, str]] = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            # Keep serials private: report only each device's connection state.
            devices.append((fields[0], fields[1]))
    return devices


def print_adb_report(adb: str, device_id: str) -> None:
    print("\nADB device detected (serial hidden). Read-only properties:")
    for prop in ADB_PROPERTIES:
        result = run_command([adb, "-s", device_id, "shell", "getprop", prop])
        value = result.stdout if result.returncode == 0 and result.stdout else "(empty or unavailable)"
        print(f"  {prop}: {value}")


def fastboot_devices(fastboot: str) -> list[str]:
    result = run_command([fastboot, "devices"])
    if result.returncode != 0:
        print(f"Fastboot error: {result.stderr or result.stdout or 'unknown error'}")
        return []
    return [line.split()[0] for line in result.stdout.splitlines() if line.split()]


def print_fastboot_report(fastboot: str, device_id: str) -> None:
    print("\nFastboot device detected (serial hidden). Read-only variables:")
    for variable in FASTBOOT_VARIABLES:
        result = run_command([fastboot, "-s", device_id, "getvar", variable])
        # Fastboot commonly writes getvar output to stderr.
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        value = "(unsupported or unavailable)"
        for line in output.splitlines():
            if variable in line and ":" in line:
                value = line.split(":", 1)[1].strip()
                break
        print(f"  {variable}: {value}")

    # This is a read-only Fastboot command; unlock/flash commands are never sent.
    result = run_command([fastboot, "-s", device_id, "flashing", "get_unlock_ability"])
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = re.search(r"(?:\(bootloader\)\s*)?get_unlock_ability\s*:\s*([01])\s*$", output, re.IGNORECASE | re.MULTILINE)
    if result.returncode == 0 and match and "FAILED" not in output.upper():
        value = match.group(1)
    else:
        value = "(unsupported or unavailable)"
    print(f"  flashing get_unlock_ability: {value}")


def main() -> int:
    adb = shutil.which("adb")
    fastboot = shutil.which("fastboot")
    if not adb and not fastboot:
        print("Neither adb nor fastboot was found. Install Android Platform Tools and retry.")
        return 1

    print("Zenfone 10 diagnostic — read-only mode")
    print("This tool does not unlock, flash, erase, reboot, or change device settings.")

    if adb:
        devices = adb_devices(adb)
        if not devices:
            print("\nADB: no visible devices")
        elif len(devices) > 1:
            print(f"\nADB: {len(devices)} devices detected; connect only the target phone to inspect it.")
        else:
            device_id, state = devices[0]
            print(f"\nADB connection state: {state}")
            if state == "device":
                print_adb_report(adb, device_id)
            else:
                print("ADB shell properties were not read because the device is not authorized/ready.")
    else:
        print("\nADB: not installed")

    if fastboot:
        devices = fastboot_devices(fastboot)
        if not devices:
            print("\nFastboot: no visible devices")
        elif len(devices) > 1:
            print(f"\nFastboot: {len(devices)} devices detected; connect only the target phone to inspect it.")
        else:
            print_fastboot_report(fastboot, devices[0])
    else:
        print("\nFastboot: not installed")

    print("\nInterpretation: unavailable variables do not prove that unlocking is supported or blocked.")
    print("Share the report after reviewing it; it omits device serial numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
