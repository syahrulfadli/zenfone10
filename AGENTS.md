# Repository Guidelines

## Project Structure & Module Organization

The diagnostic utility lives in `src/zenfone_diag.py`; project usage and safety limits are documented in `README.md`. Keep future code under `src/`, tests under `tests/`, and static assets under `assets/` if needed.

## Build, Test, and Development Commands

Run diagnostics from the repository root with `python3 src/zenfone_diag.py`; the guarded standard Fastboot client is `python3 src/unlock_client.py`. `python3 src/firmware_inventory.py <firmware.zip>` lists archive entries without extracting them. `python3 src/payload_extract.py <firmware.zip> <partition> <output.img>` reconstructs one partition locally and checks its manifest hash. `python3 src/uefi_fv_inventory.py <image>` lists UEFI FFS metadata. The first two require Android Platform Tools on `PATH`; all scripts require Python 3.10+. No external Python dependencies are required. Do not add or run tests unless requested; when tests are introduced, document their command here.

## Coding Style & Naming Conventions

Python code uses four-space indentation, descriptive `snake_case` names, and standard-library modules where practical. Keep subprocess calls argument-based (no shell). The diagnostic utility must remain read-only. Keep experimental bootloader research in separate, clearly named modules; document assumptions and any device operations in `README.md` so contributors can review their effects before use.

## Testing Guidelines

No test framework or coverage requirement is configured. If tests are added, use focused cases and document how to run them. Prefer mocked Fastboot responses; document live-device validation separately and make device-changing actions opt-in.

## Commit & Pull Request Guidelines

There is no Git commit history yet, so no repository-specific commit convention can be inferred. Use concise imperative commit subjects (for example, `Add input validation`). Pull requests should explain the change and its motivation, list validation performed, link related issues when available, and include screenshots for user-facing visual changes.

## Security & Configuration

Do not commit credentials, private keys, or machine-specific configuration. Keep required configuration documented with safe example values, and use environment variables or an approved secret store for sensitive settings.
