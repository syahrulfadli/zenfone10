# Agent Handoff

Updated: 2026-10-10. Read this with `CLAUDE.md`, `AGENTS.md`, `progress.md`, and `FEASIBILITY.md` before continuing.

## Objective

Find and document evidence about whether an authorized unlock route exists for this Zenfone 10 build. Keep working through evidence-led, offline research; update this checkpoint so another agent can resume without relying on chat history.

## Device and Repository

- Device: Zenfone 10 (`ASUS_AI2302`), Android 15, `WW_35.0604.0404.165`.
- Bootloader: `0.0.024.0-WW-user`; bootloader Fastboot (`is-userspace=no`) reported `unlocked=no`, `secure=yes`, `flashing get_unlock_ability=0`.
- OTA: `zenfone10_WW_35.0604.0404.165.zip` in the repository root, official SHA-256 verified as `03A17EE91EB868C2046D814F46F8F8D3CEDB034945D173D4DCB6C9C3EA82D2AF`. It is Git-ignored. Reconstruct images with `src/payload_extract.py` into new `/tmp` paths; output paths must not already exist.
- Always re-check the current branch, worktree, and remote before editing or pushing; do not assume the hash in an older chat is still current.

## Established Findings

- ABL's `get_unlock_ability` is derived from bit 0 of the last byte read from the FRP partition. The observed device value is `0`; the standard unlock path is not authorized in this state.
- ASUS's archived unlock APK (ROG Phone 5, not this Zenfone) shows the historical service flow: `/unlock/register` returns `Secrettoken`, which is sent through the protected Binder writer into the 256-byte `asuskey` partition. Server support for this model/build is unknown.
- ABL's `oem asus-unlock` and FRP/object signature verifier are distinct paths. The FRP verifier uses a self-signed RSA-2048 public certificate selected by key ID 1 (fingerprint recorded in `FEASIBILITY.md`). This is public trust material, not a signing secret.
- FRP verifier success reaches ABL helper `0x277b0`. Correct EFI_GUID decoding gives `91b72d4d-71e0-4cbf-9b8e-236381cff17a`; an open-source Qualcomm partition-table example labels it as the `frp` partition type, which is cross-device corroboration only.
- Static tracing shows the FRP helper locates a storage handle, reads 4,096 bytes at LBA 0, zero-fills that buffer, and writes those bytes back at LBA 0. The permission reader separately reads `BlockSize` bytes at EFI `LastBlock` and takes bit 0 of the final byte. A read-only `fastboot getvar partition-size:frp` returned `0x80000` (512 KiB), so the permission byte is at offset 524,287 (last byte of the partition) regardless of EFI block size — far outside the first 4,096 bytes the helper zeros. This confirms the erase-FRP path cannot set `get_unlock_ability` to 1.
- ASUS states that its unlock tool for 2023-or-earlier models was discontinued. No working authorized token or DIY unlock method has been established.

## Next Research Tasks

1. Finish mapping the GUID-based handle-selection interface around `0x11010`, distinguishing the common GPT type GUID from any EFI protocol registration. The block read/zero/write behavior is already traced.
2. Trace whether the separate OEM token path (`oem asus-unlock`) can change the `get_unlock_ability`/`flashing unlock` state. Current ABL evidence does not connect that handler to the FRP permission reader.
3. Assess ASUS provisioning support only through public documentation or static client evidence. Do not contact the endpoint or submit device identifiers; the archival APK is cross-model.

Resolved: the `frp` partition extent is confirmed (512 KiB) via read-only `getvar`; the erase-FRP path structurally cannot flip the permission byte.

## Update Protocol

For every material result, add a numbered entry to `progress.md`, update `FEASIBILITY.md` and the README status table/checklist if needed, then revise this file's findings and next tasks. Keep outputs in `/tmp`, preserve the firmware archive, do not add/run tests unless asked, and never store serials or token contents. The user has authorized committing and pushing project work with the configured identity; inspect the diff, run `git diff --check`, commit a concise change, and push only after checking the actual remote/branch state.
