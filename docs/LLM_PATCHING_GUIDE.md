# RAWDOG LLM Patching Guide

Author: Nicholas Corrieri

Use this guide when asking ChatGPT, Codex, Claude, Cursor, or another coding
agent to patch RAWDOG. RAWDOG works with original photo/video files, so patching
must be conservative and test-driven.

## Operating Rules For Agents

- Do not install packages, brew casks, CLIs, apps, or system dependencies
  unless a human operator explicitly approves it.
- Do not delete, rename, overwrite, or move real media while developing.
- Use dry-run plans and temporary test folders for manual checks.
- Prefer existing patterns over new abstractions.
- Use `rg` for search.
- Use `apply_patch` for manual file edits.
- Do not revert unrelated local changes.
- Leave `.DS_Store` or other unrelated dirty files alone unless asked.
- Keep release commits scoped.

## Project Shape

Important files:

```text
rawdog/cli.py          CLI, menu flows, plan review, release-facing text
rawdog/den.py          den planning and destination layout logic
rawdog/copier.py       append-only copy/move filesystem primitives
rawdog/execution.py    persisted execution plans and rows
rawdog/inventory.py    file scanning
rawdog/layout.py       source layout detection and camera-folder detection
rawdog/metadata.py     capture time and supported media extensions
rawdog/stores.py       den/yard portable catalogs
tests/test_den.py      den layout regression tests
tests/test_cli_picker.py CLI helper and warning tests
docs/HOMEBREW.md       packaging notes
docs/DEN_LAYOUTS_AND_SAFETY.md den layout contract
```

## Safety Model

RAWDOG is append-only. It is not sync, dedupe deletion, or Lightroom repair
automation yet.

Allowed archive behavior:

- copy missing files
- same-filesystem move when explicitly chosen
- skip same-name/same-size existing destination files
- hold collisions for review
- write SQLite plan/catalog metadata
- write operation manifests

Forbidden archive behavior:

- deleting source originals during `den`
- deleting archive files
- overwriting archive files
- auto-resolving collisions
- renaming source files
- silently changing a user-selected layout

If a patch touches any filesystem operation, inspect `rawdog/copier.py` and
add focused tests before changing behavior.

## Guardrails Erected So Far

This section documents the main guardrails already built into RAWDOG. Do not
remove or weaken them while patching unless a human operator explicitly asks
for that tradeoff.

| Area | Guardrail |
| --- | --- |
| Plan execution | Copy/move work is persisted as an execution plan before filesystem writes. |
| Concurrency | Active run markers prevent two RAWDOG plan executions from running at once. |
| Recovery | `rawdog plans active-clear --force` is the explicit manual escape hatch for stale run locks. |
| Copy safety | Copy uses partial files and final rename instead of writing directly to final destination. |
| Move safety | Same-drive move uses filesystem rename and refuses cross-filesystem fast move. |
| Overwrites | Existing archive files are never overwritten. |
| Collisions | Same-name/different-size collisions are held for review. |
| Skips | Same-name/same-size existing destinations are skipped; skipped rows remain review items, not cleanup permission. |
| Post-audit | Executed rows are checked for destination presence and exact size. |
| Long jobs | Progress output reports file count, bytes, throughput, and ETA for the current run. |
| Sleep prevention | `rawdog wings` wraps RAWDOG commands with `caffeinate`. |
| Operation review | `rawdog plans ops` writes a manifest and shows Python filesystem APIs instead of shell commands. |
| Path readability | Skipped row review uses full `Source:` and `Destination:` lines instead of truncating table columns. |
| Den root hygiene | `preserve-dates`, `date`, `project`, and `project-dates` are expected to year-scope archive output. |
| Duplicate years | Plans warn on adjacent duplicate year destination paths such as `RAW_DEN/2024/2024/...`. |
| Camera wrappers | Camera folders such as `DCIM`, `100CANON`, and `102EOSR7` are treated as wrappers, not project labels. |
| Store memory | App Support tracks known dens/yards, and each store has portable `.rawdog` metadata. |
| Store repair | Setup should relink existing portable stores and repair wrong den/yard registration kind. |
| Den rebuild | `rawdog dens rebuild` rebuilds a den catalog from files on disk without moving media. |
| Yard rebuild | `rawdog yard rebuild` rebuilds a yard catalog from files on disk without moving media. |
| Slow audit | Slow full audit is read-only; SHA-256 grouping is opt-in because it reads file contents and can take a long time. |
| Junkyard | Junkyard is report-only and does not delete files. |
| Scrap | `junkyard-scrap` uses explicit report paths, dry-runs by default, and revalidates roots and file sizes. |
| Exact cleanup | `--hash-check` verifies SHA-256 for meticulous cleanup reports. |
| Media coverage | Scanner includes RAW, JPEG, and common camera video files; AppleDouble `._*` files are ignored. |
| Stubs | Commands that are not implemented must say so clearly instead of pretending to verify/report. |
| Menus | Invalid folder selections should retry; menu workflows should keep the operator inside RAWDOG. |
| Top-level keys | Top-level workflow selection uses letters; numbered choices are reserved for submenus and path/layout/store selection. |

## Decisions Made In Product Discussion

- RAWDOG remains photo-archive tooling, not a general media manager.
- The name can expand to include JPEG and camera video because those files are
  commonly part of a camera-original set.
- Lightroom repair is a possible future workflow, but RAWDOG does not yet
  mutate Lightroom catalogs.
- Keywords from Lightroom may become a future den/filter feature, but current
  den safety should not depend on Lightroom.
- Dens and yards both have catalogs. Dens are archive stores; yards are working
  stores.
- App Support is the index of known stores. Portable `.rawdog` files make a
  store recognizable if a volume path changes.
- Deleting working files should remain report-driven. RAWDOG can say what
  appears safe to scrap, but should not silently clean working folders.
- For cross-drive cleanup, prefer copy plus validation and report-based cleanup
  over destructive move semantics.
- For same-drive cleanup, fast move is acceptable only because filesystem
  rename is quick and avoids duplicate storage.
- Release automation is allowed only after the operator asks to publish.

## Den Layout Rules

Read `docs/DEN_LAYOUTS_AND_SAFETY.md` before touching den layout code.

The short version:

- `preserve` mirrors source folders exactly.
- `preserve-dates` preserves meaningful folders but always year-scopes them.
- `date` ignores source folders and groups by capture date.
- `project` creates one dated project folder.
- `project-dates` creates project date buckets.

Never allow normal archive workflows to silently dump arbitrary folders at the
den root. Never create adjacent duplicate years like:

```text
RAW_DEN/2024/2024/...
```

RAWDOG should warn if such a path appears in a plan.

## Prompt Template For A Den Layout Patch

Use this prompt when handing den layout work to an LLM:

```text
You are patching RAWDOG at /Users/nick/Projects/rawdog.

Read first:
- README.md
- docs/DEN_LAYOUTS_AND_SAFETY.md
- docs/LLM_PATCHING_GUIDE.md
- rawdog/den.py
- rawdog/cli.py
- tests/test_den.py
- tests/test_cli_picker.py

Goal:
[describe the exact layout bug or feature]

Constraints:
- RAWDOG is append-only.
- Never delete, overwrite, or rename originals.
- File names must remain unchanged.
- Keep den root clean.
- preserve is the only exact mirror layout.
- preserve-dates must keep meaningful folders under top-level YYYY.
- Warn on planned destinations like YYYY/YYYY.
- Do not install dependencies.
- Do not touch unrelated files.

Implementation expectations:
- Patch the smallest relevant code path.
- Add regression tests.
- Run ruff and tests.
- Report exact files changed and commands run.

Stop and ask before release/publish unless explicitly authorized.
```

## Prompt Template For A CLI/Menu Patch

```text
You are patching RAWDOG at /Users/nick/Projects/rawdog.

Read:
- README.md
- docs/LLM_PATCHING_GUIDE.md
- rawdog/cli.py
- tests/test_cli_picker.py

Goal:
[describe menu/CLI issue]

Constraints:
- Keep prompts retryable.
- Keep yes/no answers accepting y/yes/n/no in any case.
- Show full paths for risky filesystem operations.
- Do not hide dry-run/commit behavior.
- No destructive behavior.
- Do not install dependencies.

Add tests for helper behavior where possible.
Run:
- .venv/bin/ruff check .
- .venv/bin/python -m pytest tests/test_cli_picker.py
- .venv/bin/python -m pytest
```

## Prompt Template For Junkyard/Cleanup Patch

```text
You are patching RAWDOG at /Users/nick/Projects/rawdog.

Read:
- README.md
- docs/LLM_PATCHING_GUIDE.md
- rawdog/cli.py
- rawdog/stores.py
- tests/test_junkyard.py

Goal:
[describe cleanup/reporting issue]

Hard constraints:
- junkyard is report-only.
- junkyard-scrap must be dry-run by default.
- scrap must use explicit report paths.
- revalidate registered yard/den roots.
- revalidate current file presence and exact size.
- keep optional hash-check for exact byte verification.
- never delete den/archive files.
- never delete anything not listed in the report.

Add tests before release.
```

## Validation Commands

For most patches:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
.venv/bin/python -m compileall rawdog
```

For package/release checks:

```bash
.venv/bin/python -m build --no-isolation
.venv/bin/twine check dist/rawdog-VERSION.tar.gz dist/rawdog-VERSION-py3-none-any.whl
shasum -a 256 dist/rawdog-VERSION.tar.gz
```

For Homebrew tap updates, see `docs/HOMEBREW.md`.

## Release Checklist

Only release when the operator asks for it.

1. Bump version in `pyproject.toml`.
2. Bump version in `rawdog/__init__.py`.
3. Run validation.
4. Build artifacts.
5. Commit the scoped source/docs changes.
6. Tag `vX.Y.Z`.
7. Push `main` and the tag.
8. Create GitHub release with sdist and wheel.
9. Update `/Users/nick/Projects/rawdog-homebrew/Formula/rawdog.rb`.
10. Run `brew style Formula/rawdog.rb`.
11. Run `brew audit --strict --online rawdog`.
12. Commit and push the tap.

Do not stage unrelated `.DS_Store` files.
