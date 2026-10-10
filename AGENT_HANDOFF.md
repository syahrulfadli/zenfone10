# Agent Handoff

Updated: 2026-10-10. Read this with `CLAUDE.md`, `AGENTS.md`, `progress.md`, and `FEASIBILITY.md` before continuing.

## Objective

Find and document evidence about whether an authorized unlock route exists for this Zenfone 10 build. Keep working through evidence-led, offline research; update this checkpoint so another agent can resume without relying on chat history.

**Current answer (see `FEASIBILITY.md` → "Answer to the research question").** Yes, an authorized path exists and is supported by this firmware: the standard Android OEM-unlock flow (`ro.oem_unlock_supported=1`, `frp` as the allow-unlock store). It needs no ASUS token — only the Developer Options "OEM unlocking" toggle, which the OS persists to `frp` so `get_unlock_ability` becomes 1. The device reports `get_unlock_ability=0` because that toggle is currently unavailable, which is a device-runtime/account condition (network / Google account / FRP / MDM policy), not a firmware-removed capability. ASUS's own token unlock is present in the bootloader but unusable (provisioning discontinued; no public token source). No offline firmware trick flips the `frp` bit.

## Device and Repository

- Device: Zenfone 10 (`ASUS_AI2302`), Android 15, `WW_35.0604.0404.165`.
- Bootloader: `0.0.024.0-WW-user`; bootloader Fastboot (`is-userspace=no`) reported `unlocked=no`, `secure=yes`, `flashing get_unlock_ability=0`.
- OTA: `zenfone10_WW_35.0604.0404.165.zip` in the repository root, official SHA-256 verified as `03A17EE91EB868C2046D814F46F8F8D3CEDB034945D173D4DCB6C9C3EA82D2AF`. It is Git-ignored. Reconstruct images with `src/payload_extract.py` into new `/tmp` paths; output paths must not already exist.
- Always re-check the current branch, worktree, and remote before editing or pushing; do not assume the hash in an older chat is still current.

## Established Findings

- ABL's `get_unlock_ability` is derived from bit 0 of the last byte read from the FRP partition. The observed device value is `0`; the standard unlock path is not authorized in this state.
- ASUS's archived unlock APK (ROG Phone 5, not this Zenfone) shows the historical service flow: `/unlock/register` returns `Secrettoken`, which is sent through the protected Binder writer into the 256-byte `asuskey` partition. Server support for this model/build is unknown.
- ABL's `oem asus-unlock` and FRP/object signature verifier are distinct paths. The FRP verifier uses a self-signed RSA-2048 public certificate selected by key ID 1 (fingerprint recorded in `FEASIBILITY.md`). This is public trust material, not a signing secret.
- The generic partition selector at PE RVA `0x11010` (used by the verifier and ~39 call sites) enumerates handles via `gBS->LocateHandleBuffer` by EFI protocol — `EFI_BLOCK_IO` (`964e5b21-…`) or `EFI_SIMPLE_FILE_SYSTEM` (`964e5b22-…`) — then `gBS->HandleProtocol` for `EFI_DEVICE_PATH` (`09576e91-…`) and a Qualcomm vendor partition-info protocol (`6848de61-eb61-4def-9a8e-3817cbeb8f1c`), matching partitions by name. A whole-`.text` xref scan shows the `frp` GPT partition-type GUID (`91b72d4d-…`) is referenced only once, at `0x277d8` inside the erase helper `0x277b0`, as a local type-match value. GPT type GUID vs EFI protocol GUIDs are thus distinct in value, code, and purpose.
- FRP verifier success reaches ABL helper `0x277b0`. Correct EFI_GUID decoding gives `91b72d4d-71e0-4cbf-9b8e-236381cff17a`; an open-source Qualcomm partition-table example labels it as the `frp` partition type, which is cross-device corroboration only.
- Static tracing shows the FRP helper locates a storage handle, reads 4,096 bytes at LBA 0, zero-fills that buffer, and writes those bytes back at LBA 0. The permission reader separately reads `BlockSize` bytes at EFI `LastBlock` and takes bit 0 of the final byte. A read-only `fastboot getvar partition-size:frp` returned `0x80000` (512 KiB), so the permission byte is at offset 524,287 (last byte of the partition) regardless of EFI block size — far outside the first 4,096 bytes the helper zeros. This confirms the erase-FRP path cannot set `get_unlock_ability` to 1.
- The `oem asus-unlock` success path (`0xa528c` → verifier `0xaff70` → `0x1ae90`) sets the device-info *IsUnlocked* byte (`0x2b3eb2`) and persists the DeviceInfo struct via Qualcomm vendor store protocol `8e5eff91-21b6-47d3-af2b-c15a01e020ec`. It never reads/writes the `IsAllowUnlock` global (`0x2cbf30`, backing `get_unlock_ability`) nor the `frp` partition — a whole-`.text` xref finds only three accesses to `0x2cbf30`, all in the `frp` reader `0x9e458` and the `get_unlock_ability` reporter `0xa2760`. So the ASUS token path is an independent, signed-token-gated unlock that bypasses `get_unlock_ability`; it cannot be driven without an ASUS-signed token.
- ASUS states that its unlock tool for 2023-or-earlier models was discontinued. No working authorized token or DIY unlock method has been established.

## Next Research Tasks

1. The core question is answered (above). If deeper confirmation is wanted on *why* the toggle is greyed, inspect (read-only) the framework overlay `config_oemUnlockSupported` and any default `DISALLOW_OEM_UNLOCK` user restriction in the `system`/`product` images; and note the on-device greying hint (e.g. "Connect to the internet or contact your operator"). Do not change device properties or state.
2. Optional firmware detail: the standard `flashing unlock` handler `0xa27b8` success mechanics were not fully traced (linear disassembler desyncs on literal pools around `0xacc44`/`0xad044`); a function-aware disassembler could confirm exactly how it checks the `frp` allow bit and sets the unlock state. Not required for the conclusion.

Resolved: (a) the `frp` partition extent is confirmed (512 KiB) via read-only `getvar`; the erase-FRP path structurally cannot flip the permission byte. (b) The `0x11010` handle-selection interface is fully mapped (EFI protocol-based, by-name) and proven distinct from the `frp` GPT type GUID (used only in erase helper `0x277b0`). (c) The `oem asus-unlock` token path is proven decoupled from `get_unlock_ability`; it is an independent signed-token-gated unlock needing an ASUS token that is not publicly obtainable. (d) Firmware supports the standard OEM-unlock flow (`ro.oem_unlock_supported=1`, `ro.frp.pst=…/frp`), which is token-free and gated by the Developer Options toggle — this is the authorized route.

## Disassembly tooling

Host objdump lacks the aarch64 target. A working AArch64 disassembler is set up under the session scratchpad (not committed): `python3-capstone`+`libcapstone5` fetched with `apt-get download` and unpacked locally; run Python with `PYTHONPATH=<root>/usr/lib/python3/dist-packages` and `LD_LIBRARY_PATH=<root>/usr/lib/x86_64-linux-gnu`. Reconstruct `abl` with `src/payload_extract.py` (run it without `-I`, which drops its sibling-import path), decompress the inner LZMA FV, and extract the single `LinuxLoader` PE32+ (`ImageBase=0`, so RVA==file offset). A next agent on a fresh machine must redo this setup.

## Update Protocol

For every material result, add a numbered entry to `progress.md`, update `FEASIBILITY.md` and the README status table/checklist if needed, then revise this file's findings and next tasks. Keep outputs in `/tmp`, preserve the firmware archive, do not add/run tests unless asked, and never store serials or token contents. The user has authorized committing and pushing project work with the configured identity; inspect the diff, run `git diff --check`, commit a concise change, and push only after checking the actual remote/branch state.
