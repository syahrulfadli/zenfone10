# Zenfone 10 Diagnostic Tool

This small Python utility collects selected Android properties and Fastboot variables, including the read-only `fastboot flashing get_unlock_ability` query. It is the first stage of investigating bootloader unlock capability; it is not an unlock tool.

## Research status

**Current state:** the bootloader reports `get_unlock_ability=0`. Static analysis maps the historical ASUS client flow: an ASUS-signed unlock APK requests `Secrettoken` from `/unlock/register`, converts it to bytes, and sends it through Binder transaction 7 to the `asuskey` provisioning path. Its signing certificate matches the `com.asus.filemanager` signer trusted by the Zenfone 10 service. The APK is for ROG Phone 5, and ASUS says its unlock tool for 2023-and-earlier phones has been discontinued. This does not establish that its server still issues a token for Zenfone 10 build `WW_35.0604.0404.165`. No valid token or DIY unlock method has been established.

| Work item | Status | Evidence / next action |
| --- | --- | --- |
| Verify the official firmware package and OTA metadata | ✅ Complete | Published ZIP checksum and embedded payload hashes match. |
| Reconstruct ABL and identify its LinuxLoader application | ✅ Complete | ABL hash matches the OTA manifest; LinuxLoader is an AArch64 PE image. |
| Trace `get_unlock_ability` state | ✅ Complete | An `frp` lookup read path stores the final buffer byte's bit 0 as the reported flag. |
| Locate unlock handlers | ✅ Located | Fastboot table maps `flashing unlock` and `oem asus-unlock` to separate handlers; ASUS handler has a token-verification failure branch. |
| Map DMClient network routes | ✅ Complete | `/sync/unlock` posts verified-boot status only. `/key/verify` is a separate keybox flow; no link to the ABL token was found. |
| Inspect installed OpenBeta Binder client | ✅ Complete | It binds to `UnlockService` but calls only string getters; `KeyTool`'s questionnaire token does not reach the byte-array writer. |
| Trace ASUS unlock provisioning chain | ✅ Historical flow mapped | Legacy ASUS APK obtains `Secrettoken` from `/unlock/register` and calls Binder transaction 7; current firmware maps it to `C0(byte[])`. Server support for this model/build is unknown. |
| Audit installed system APKs | ✅ Scoped | Exact package/DEX scan of 194 APKs in `system` found only allowlisted OpenBeta; other partitions were not fully manifest-scanned. |
| Map separate FRP signature path | 🟡 Partial | Static parser references `asuskey2` and `signature`; its relation to `oem asus-unlock` is unknown. |
| Determine whether an authorized flow remains available | ⬜ Queued | Need confirmation that ASUS still issues a token for this model/build; no server request has been sent. |

The sequence follows the status-section style used by [AnyPS5](https://github.com/boykopovar/AnyPS5). Analysis so far is offline; no FRP write, image patch, or device unlock request has been made.

### Next checklist

- [x] Link the ABL verifier to the `asuskey` lookup and locate Android-side unlock service components.
- [x] Trace the DMClient status and keybox routes; confirm `/sync/unlock` carries status, not an unlock token.
- [x] Link the protected local Binder write method to `/ADF/asuskey.bin` and the property-triggered writer.
- [x] Inspect OpenBeta's Binder and native-token call paths; its client does not submit the 256-byte payload.
- [x] Identify the historical authorized Binder input source; legacy ASUS client receives it as `Secrettoken` from `/unlock/register`.
- [x] Check installed `system` APK manifests and DEX for allowlisted clients; only OpenBeta matched, within that partition scan.
- [ ] Map the embedded certificate verifier and compare it with the separate FRP-signature check.
- [ ] Determine whether ASUS's provisioning service still issues tokens for Zenfone 10 build `WW_35.0604.0404.165`.
- [ ] Establish whether the distinct `oem asus-unlock` path can change the standard permission value; current evidence does not show that it can.

## Requirements

- Python 3.10 or newer
- Android Platform Tools (`adb` and `fastboot`) installed and available on `PATH`
- USB debugging enabled and authorized for ADB inspection

## Run

From the repository root:

```sh
python3 src/zenfone_diag.py
```

## Standard unlock client

`python3 src/unlock_client.py` checks for exactly one Fastboot device and refuses to run in `fastbootd`; it is intended for bootloader Fastboot. If the bootloader reports unlock ability `0`, it refuses to proceed. If permission is `1`, it requires explicit terminal confirmation before sending the standard `fastboot flashing unlock` request. If the bootloader does not support the permission query, the default is to stop; `python3 src/unlock_client.py --request-unlock` opts into asking the bootloader anyway, after a separate explicit confirmation. The bootloader still decides whether to accept the standard request, and may require confirmation on-device. If accepted and confirmed, unlocking may factory-reset the phone and erase user data. This client does not bypass OEM authorization.

## Inspect an official firmware archive

After downloading the ASUS firmware ZIP for the exact model/SKU/build, list likely boot-chain entries without extracting it:

```sh
python3 src/firmware_inventory.py /path/to/firmware.zip
```

Use `--all` to list every file. The inventory helper only reads the ZIP directory; it does not extract, flash, or modify the archive.

To read the OTA payload header and partition names from `payload.bin` without extracting partition images:

```sh
python3 src/payload_manifest.py /path/to/firmware.zip
```

This reader reports only manifest metadata, such as payload format, boot-chain partition sizes, operation types, and a patch level if present. It does not extract images or inspect/change the device.

For offline analysis, reconstruct one partition image from a full OTA payload and verify it against the manifest hash:

```sh
python3 src/payload_extract.py /path/to/firmware.zip abl /tmp/zenfone10_abl.img
```

The output path must not already exist. The helper supports full-payload `REPLACE`, `REPLACE_BZ`, and `REPLACE_XZ` operations, and never executes or flashes the resulting image.

For an extracted UEFI image or firmware volume, list its FFS file GUIDs and top-level section types:

```sh
python3 src/uefi_fv_inventory.py /path/to/firmware-volume.bin
```

The inventory is metadata-only; it does not extract or execute UEFI modules.

To inspect Fastboot variables, connect the phone in bootloader/Fastboot mode yourself before running the script. The script does not reboot the phone. Connect only the Zenfone 10 when inspecting; multiple connected devices are listed but not queried.

The script does not issue unlock, flash, erase, reboot, or settings-changing commands. It hides device serial numbers. Some properties/variables may be absent or vendor-specific; an unavailable value is inconclusive and must not be treated as proof that unlocking is possible.
