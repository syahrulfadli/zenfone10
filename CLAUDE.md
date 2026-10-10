# Claude Handoff Guide

At the start of each session, read `AGENTS.md`, `AGENT_HANDOFF.md`, `progress.md`, and `FEASIBILITY.md`, then check `git status` and recent commits. `AGENT_HANDOFF.md` is the concise checkpoint; `progress.md` is the chronological evidence log.

## Continue the Research

The goal is to determine, from evidence, whether an authorized bootloader-unlock path exists for the ASUS Zenfone 10 (`ASUS_AI2302`, Android 15, `WW_35.0604.0404.165`). Continue from the highest-priority open item in `AGENT_HANDOFF.md`; pursue useful read-only analysis rather than stopping at a list of suggestions. Distinguish observed facts, static-analysis conclusions, hypotheses, and unknowns. Prefer the verified local OTA and primary ASUS/AOSP/EDK2 sources. Do not repeat completed scans unless a new method or broader scope makes them useful.

Keep analysis offline and read-only with respect to the phone. Do not trigger unlock provisioning, change FRP or device properties, send unlock/erase/flash commands, patch or boot firmware, or create/derive signing tokens or private keys. Do not store device serials, credentials, or token values. Keep reconstructed images and temporary tooling under `/tmp`; the official firmware ZIP is ignored by Git.

## Keep the Handoff Current

After a meaningful finding, update `progress.md` with evidence and limitations, update `FEASIBILITY.md` and the README checklist when their conclusions change, and refresh `AGENT_HANDOFF.md` with the next concrete step. Keep this file focused on Claude's session startup and continuation workflow. Do not overwrite `AGENTS.md`.

Do not add or run tests unless requested. Before committing, inspect the diff and run `git diff --check`. Use concise imperative commit subjects. The user has authorized commits and pushes to the configured GitHub remote using `syahrulfadli <callsyahrul@outlook.com>`; check the current branch and remote state before publishing.
