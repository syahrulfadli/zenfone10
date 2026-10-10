# Bootloader Unlock Feasibility

## Device and observed state

- Device: ASUS Zenfone 10, model `ASUS_AI2302`
- Android/build: Android 15, `WW_35.0604.0404.165`
- Android security patch: `2026-08-05` (matches the ASUS release note for this build)
- Bootloader: `0.0.024.0-WW-user` (`version-bootloader`; `version` is unavailable)
- OEM unlocking option: unavailable (reported by the owner)
- Read-only bootloader Fastboot results: `is-userspace=no`, `unlocked=no`, `secure=yes`, `flashing get_unlock_ability=0`.

The device is currently locked. The user verified bootloader Fastboot with `is-userspace=no`; that mode reports `get_unlock_ability=0`. The earlier rejected requests were made in `fastbootd` and do not count as unlock attempts by the bootloader. No unlock, flash, erase, or downgrade operation succeeded.

## Evidence and limits

Android documents `fastbootd` as separate from bootloader Fastboot. Once switched to bootloader Fastboot, this device reported `get_unlock_ability=0`. Android's bootloader guidance says devices should deny the standard unlock operation unless `get_unlock_ability` is `1`; therefore the standard unlock path is denied in the observed state.

ASUS stated on ZenTalk that its unlock tool has been discontinued for phone models released in 2023 or earlier. The Zenfone 10 falls in that group. ASUS does publish a Zenfone 10 kernel source package for version `35.0604.0404.165`, matching this device's build. That listing is for kernel source; it does not establish that bootloader source, signing material, or an unlock authorization service is available. ASUS's firmware page also says downgrading is not possible after the listed update.

## Assessment

**Standard unlock client: denied by the bootloader's reported permission.** The guarded client refuses when `get_unlock_ability=0`. Separately, this ABL registers an `oem asus-unlock` handler that verifies a token before continuing. A valid token and its current availability have not been established, so this finding is not yet a usable unlock method.

## Public advisory review

The Android August 2026 bulletin says patch level `2026-08-05` addresses the Android issues listed for the `2026-08-01` bulletin and earlier patch levels. AOSP also explains that chipset/vendor fixes and device-partner advisories can be separate from the Android patch-level declaration. Therefore, the patch date does not by itself establish the patch state of every proprietary boot-chain component.

Targeted searches of public ASUS, AOSP, and Qualcomm material did not find a supported unlock procedure or a public advisory that maps bootloader version `0.0.024.0-WW-user` to a specific unlock method. This does not resolve the vendor token path found in the firmware; continue static analysis to determine its requirements. No bypass has been demonstrated.

## Firmware payload inventory

The official ASUS ZIP for this exact build was checked against ASUS's published SHA-256. The OTA `FILE_SIZE`, `FILE_HASH`, `METADATA_SIZE`, and `METADATA_HASH` properties also match the embedded `payload.bin` and its metadata. This internal consistency check complements the independently published ASUS ZIP checksum. Its OTA payload manifest identifies a full payload with 37 partitions, including `abl`, `xbl`, `tz`, `boot`, `init_boot`, `recovery`, and `vbmeta`. The boot-chain summary reports `abl` target size 729,088 bytes, `xbl` 1,208,320 bytes, and `tz` 3,936,256 bytes; their payload operations are compressed replacements (`REPLACE_XZ`). This is metadata only: it does not expose source code, signing keys, or an unlock authorization. The manifest has no security-patch field, while ASUS's release page lists `2026-08-05`. The ABL partition was later reconstructed locally for static inspection; no image was written to the phone.

The `abl` image was reconstructed offline to `/tmp/zenfone10_abl.img` and its SHA-256 matched the manifest's partition hash (`8ce6dfcc5ff045f69558d9edeaa20f99aae6f19078a55749e81c05709bfd147e`). ELF inspection identifies an ELF32 ARM executable with no section table; a basic printable-string scan found no Fastboot/unlock terms. This is a limited static observation, not a conclusion about the code's behavior. The image was not executed or written to the phone.

The ABL image contains a UEFI firmware volume with a guided LZMA section. Its decompressed FV contains one `LinuxLoader` AArch64 PE32 application. Static strings in that image include authorization-related indicators (`IsAllowUnlock`, `IsAuthorized`, `IsDebugUnlocked`, and an authorized-hash failure message). This suggests vendor authorization checks are present, but strings alone do not establish their exact logic or an unlock method. No OEM command was sent to the phone; no image was patched or flashed.

An AArch64 cross-reference pass refined those observations. `IsAllowUnlock is %d` is passed to a logging helper. At PE RVA `0x9e458`, the UTF-16 string `frp` is passed to a lookup helper; on its success path, code allocates a buffer from the returned descriptor and invokes a read callback. At RVA `0x9e5a8`, it stores bit 0 of the buffer's last byte to the `IsAllowUnlock` global. The `get_unlock_ability` handler reports that global. Nearby messages include `Error Reading FRP partition` and `Failed to allocate memory for unlock value`. The callback implementation and FRP data format are not yet identified. This does not show that changing FRP data would be accepted or safe.

The Fastboot command table around PE RVA `0x106e08` maps `flashing get_unlock_ability` to handler `0xa2760`, `flashing unlock` to `0xa27b8`, and `oem asus-unlock` to `0xa528c`. The ASUS handler obtains an argument and calls verifier `0xaff70`; a nonzero return follows the `Verify unlock token fail.` branch, while the success path performs additional state checks and contains a `Device unlocked successfully.` message. The verifier's strings include `verify_RD_unlock` and `asuskey`; its call path passes a 981-byte DER block at image address `0x2b2429` through wrapper `0xafdc0`. Local OpenSSL inspection identifies that block as a self-signed ASUS X.509 certificate with an RSA 2048-bit public key and SHA-256/RSA certificate signature. Its encoded validity ended on 2023-03-29; this does not prove the bootloader checks certificate dates. A separate code path at `0xa0904` reports `Verify FRP Unlock Signature Failed!!`. This strongly suggests a signed vendor token path, but the token format, private signing-key source, current token availability, and relationship to standard `flashing unlock` remain unresolved. The bundled certificate contains a public key; it cannot produce a valid signature by itself.

Further static tracing shows that `oem asus-unlock` calls the verifier without setting a token argument at that call site. The verifier allocates a 256-byte buffer, passes the UTF-16 name `asuskey` to a lookup helper at PE RVA `0x12030`, then passes the bundled certificate to a crypto wrapper. The lookup enumerates handles supporting UEFI Block I/O and Device Path, selects hard-drive partition nodes, obtains partition metadata through an additional protocol, and compares its name field with the requested `asuskey`. It then invokes the Block I/O `ReadBlocks` method (the method at protocol offset 24) into the verifier buffer. This identifies the ABL lookup backend and ties it to the same named partition that Android's `/vendor/bin/writekey` writes. The exact authorized blob source and precise signed bytes remain unresolved. The protocol GUID and method layout were checked against the primary EDK2 Block I/O and Device Path headers; the extra partition-metadata protocol is vendor-specific.

The Android-side firmware contains a local provisioning path. `system/etc/init/init.asus.unlock.rc` labels a disabled one-shot `/vendor/bin/writekey` service as the user unlock tool; a property trigger starts it. The native library `system/fake-libs64/libunlock.asus.so` exposes JNI names including `getNativeKey` and `writeNativeSign`, and references `/ADF/asuskey.bin` plus readiness properties. The vendor `writekey` executable references `/dev/block/bootdevice/by-name/asuskey` and `/ADF/asuskey.bin`, and imports file-read/write and property APIs.

Static decompilation of `DMClient.apk` (SHA-256 `cce7ee9702220f12f907d6cb20d5fe98091ea94af8bf76cc68b095ab26e1b26c`) separated two network routes that the earlier string scan could not distinguish. `HttpSyncUnlockStatus` reads `ro.boot.verifiedbootstate`, maps `green` to `0` and another nonempty value to `1`, then posts only that status to `/sync/unlock`; its success callback updates sync state and schedules another job. It does not receive or forward an unlock token. `HttpGetAsusKeybox` is separate: it uploads a report and keybox type to `/key/verify`, then passes the response's keybox field to `ASUSKeyBox2Service`. No direct call from that keybox route to the unlock Binder was found, so it must not be treated as the source of the ABL token.

The APK manifest declares `com.asus.dm.c2dm.UnlockService` exported, with Binder interface `com.asus.unlockservice.IAsusUnlockService`. Its byte-array write method writes to `/ADF/asuskey.bin`, sets `sys.debug.write.asuskey`, and waits for `vendor.debug.asuskey.ready`. The method checks the caller UID against a fixed package allowlist and verifies the caller's signing certificate against the DMClient package before accepting it. This confirms a protected local handoff to the vendor writer, but does not identify the authorized caller's byte source or prove the exact bytes consumed by ABL. JADX 1.5.6 reconstructed these target classes, although the overall APK pass reported 18 decompilation errors; findings above are limited to the successfully reconstructed methods. No endpoint was contacted, service/property was triggered, or device operation performed.

Static AArch64 disassembly of `/vendor/bin/writekey` (SHA-256 `bfe0a9299cbd38017f9bfb3f55e51af71b14b417cd8522b3cdd939a8c9bbed37`) shows it reads `/ADF/asuskey.bin` into a buffer and requires exactly 256 bytes. It then opens `/dev/block/bootdevice/by-name/asuskey` in `wb+` mode, writes those 256 bytes, calls `sync`, and sets `vendor.debug.asuskey.ready=1`; it removes the input file after reading it. Its dynamic imports cover ordinary file I/O, logging, sync, and property APIs, with no crypto library dependency. Combined with the ABL's name-matched Block I/O read into a 256-byte verifier buffer, this maps both ends of the on-device provisioning path to the same partition. Static inspection still does not reveal the authorized Binder caller's blob source or prove what bytes the vendor provisioning service would provide at runtime. The helper does not appear to perform signature verification; the ABL verifier is the relevant cryptographic gate.

A separate FRP/object path references fields `asuskey2` and `signature` before a 256-byte signature-verification call; its trust key and relation to the `oem asus-unlock` verifier remain unresolved.

For this audit, the `system`, `vendor`, `product`, and `system_ext` images were reconstructed locally from the verified full OTA and each output hash matched its payload manifest entry. `debugfs` was used read-only to inspect the filesystem and extract only the listed small files. No Android property was set, no helper was executed, and no device operation was performed. The built-in public certificate and these services do not themselves provide an authorized signing token.

## Recommended next steps

1. Trace the authorized source of bytes sent to `UnlockService` through `libunlock.asus.so` and the DMClient caller; do not trigger the property-gated service on-device.
2. Compare the embedded-certificate verifier with the separate FRP `asuskey2`/`signature` check.
3. Establish whether ASUS's authorized provisioning service still supports this model/build and compare it with the standard `flashing unlock` permission check.
4. Keep the host client from sending a standard unlock request while permission is `0`. No FRP edit, image patch, unlock, flash, or downgrade has been attempted; ASUS says downgrade is unavailable for the listed firmware.

## References

- [Android Open Source Project: Lock and unlock the bootloader](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)
- [AOSP update_engine: OTA payload and manifest format](https://android.googlesource.com/platform/system/update_engine/+/HEAD/update_metadata.proto)
- [ASUS ZenTalk: Bootloader unlock tool discontinuation](https://zentalk.asus.com/t5/zenfone-10/release-bootloader-unlock-tool-discontinuation-products-eol/td-p/500937)
- [ASUS Zenfone 10 downloads and kernel source](https://www.asus.com/us/supportonly/zenfone%2010/helpdesk_download/)
- [ASUS Zenfone 10 firmware and downgrade note](https://www.asus.com/us/supportonly/zenfone%2010/helpdesk_bios/)
- [Android Security Bulletin: August 2026](https://source.android.com/docs/security/bulletin/2026/2026-08-01)
- [Android Security Bulletin overview and partner-bulletin scope](https://source.android.com/docs/security/bulletin/asb-overview)
- [Qualcomm Security Bulletins](https://docs.qualcomm.com/securitybulletin/)
- [TianoCore EDK2: Block I/O protocol](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/BlockIo.h)
- [TianoCore EDK2: Device Path protocol](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/DevicePath.h)
