# RAWDOG

RAW photo managing tool that can fetch, copy, and audit your RAW libraries.

RAWDOG is local-first, append-only archival tooling for photographers. It helps
you ingest from SD cards, manage working folders, organize project shoots,
archive permanently to external storage, verify copies, and generate reports.

RAWDOG is not sync software, cloud backup software, a DAM, a Lightroom
replacement, or aggressive dedupe tooling.

Current status: pre-alpha CLI scaffold. The safety model, project/profile
memory, den planning, and queue structure are being built first.

## Core Rule

```text
WORKING LIBRARY != PERMANENT ARCHIVE
```

Your working library is where you import, edit, and organize. Your permanent
archive is append-only and must never be changed just because the working copy
changed.

One-tree-to-another checks are optional verification/reporting workflows, not the
main product shape.

## Import Profiles

RAWDOG supports reusable import profiles. A profile stores a source root,
destination root, organization mode, and folder template. This supports normal
local working folders, SD-card imports, and external-volume-to-external-volume
workflows where the photographer does not want a local setup.
Use `rawdog fetch --profile last` to reuse the most recently used profile.

`fetch` previews by default. Project/profile memory is written only when the
operator uses `--commit`.

When a project is named during import, RAWDOG remembers that project and the
source/destination pair. By default project imports land under:

```text
{destination}/YYYY/YYYYMMDD_PROJECT
```

`YYYYMMDD` is based on the earliest RAW file in the import source.

RAWDOG keeps canonical memory in its local SQLite database and writes a portable
manifest to:

```text
{destination_project_or_date_folder}/.rawdog/project.json
```

For date-only imports, the configured date folder acts as the destination memory
area, for example `YYYY/YYYY-MM` or `YYYY/MM`.

## Lightroom Workflow

RAWDOG does not sync Lightroom or track Lightroom rejects/deletes live. Use
Lightroom or another editor inside the working project folder, then run
`rawdog breed` when the project is ready to archive.

`breed` snapshots the current working project state to append-only archive
destinations. If a local working file was deleted before breed, RAWDOG simply
does not copy it in that run. Existing archive files are not deleted.

```bash
rawdog breed --project Wedding_Smith --dest /Volumes/WD_BLACK
rawdog breed --project Wedding_Smith --dest /Volumes/Backup_2
```

`breed` is also preview-first. Use `--commit` only after reviewing the planned
archive destinations.

## Commands

Run `rawdog` with no arguments to open the colored workflow chooser. Use
`rawdog --help` for the full command reference.

```bash
rawdog init
rawdog fetch
rawdog breed
rawdog den
rawdog sniff
rawdog score
rawdog status
rawdog report
rawdog verify
rawdog projects create
rawdog projects list
rawdog profiles create
rawdog profiles list
rawdog workflows list
rawdog queue create
rawdog queue add-sniff
rawdog queue add-score
rawdog queue add-den
rawdog queue show
rawdog queue run
rawdog plans list
rawdog plans show
rawdog plans resume
```

## Cleanup Consolidation

For old folders or drives that need to be gathered into a RAWDOG structure, use
`den`. It scans RAW files, builds a copy estimate, skips already-present
same-name/same-size files, and reports collisions for review.

```bash
rawdog sniff /Volumes/OldDrive
rawdog score /Volumes/OldDrive
rawdog den /Volumes/OldDrive --dest /Volumes/Archive
rawdog den /Volumes/OldDrive --dest /Volumes/Archive --commit
```

Two consolidation workflows are supported:

- External drive to destination drive: audit the source and copy into the destination.
- Same-drive cleanup: audit an old folder on the destination drive, then copy
  or move into the RAWDOG structure.

Use `--action copy` for cross-drive consolidation. Use `--action move` only for
same-drive cleanup when you intentionally want the old folder contents relocated
after reviewing the queued plan.

## Safe Plan Queues

Long jobs can be queued as safe plans, previewed, and then committed with an
explicit confirmation. Before any copy or move executes, RAWDOG writes a
persisted execution plan to SQLite. The plan records:

- what RAWDOG is doing
- what RAWDOG is doing it to
- what should be where when done
- execution status
- post-audit status

Queues are for operations such as:

- audit/inspect
- score
- copy
- same-filesystem move of unique files with no overwrite

Destructive cleanup is never queued. RAWDOG must not queue deletion, mismatch
cleanup, thumbnail cleanup, overwrite, rename, or automatic dedupe reduction.
No queued operation may silently resolve collisions.

```bash
rawdog queue create old_drive_cleanup
rawdog queue add-sniff old_drive_cleanup /Volumes/OldDrive
rawdog queue add-score old_drive_cleanup /Volumes/OldDrive
rawdog queue add-den old_drive_cleanup /Volumes/OldDrive --dest /Volumes/Archive --action copy
rawdog queue add-sniff old_drive_cleanup /Volumes/Archive
rawdog queue show old_drive_cleanup
rawdog queue run old_drive_cleanup
rawdog queue run old_drive_cleanup --commit
rawdog plans list
rawdog plans show 1
rawdog plans resume 1
```

`den` preserves existing source folder structure by default, which helps when an
old drive already has useful names or partial date/project discipline. Use
`--layout preserve-dates` to preserve the structure but normalize date-like
folders such as `MMDDYYYY`, `MM.DD.YYYY`, `YYYYMMDD`, or `YYYY.MM.DD` into
`YYYYMMDD`. Use `--layout date` or `--layout project` when you want RAWDOG to
place everything under a generated date or project folder.

Saved consolidation workflows can be reused:

```bash
rawdog den /Volumes/OldDrive --dest /Volumes/Archive --workflow old_drive --commit
rawdog den --workflow old_drive
rawdog workflows list
```

`den` is append-only. It is not sync, cleanup, or dedupe deletion.

For same-drive cleanup, queue or run move only when the source folder and
destination root are on the same filesystem:

```bash
rawdog queue add-den same_drive_cleanup /Volumes/Archive/OldMess \
  --dest /Volumes/Archive \
  --action move
rawdog queue run same_drive_cleanup --commit
```

Move still refuses overwrites and collisions.

If RAWDOG is interrupted, rerun `rawdog plans list`, inspect the latest started
or incomplete plan, then resume it explicitly with `rawdog plans resume PLAN_ID`.
Rows already copied, moved, skipped, or held for review are not blindly repeated.

`.partial` files are temporary transfer artifacts created only under the
destination root during copy. They are not original RAW files, are ignored during
source inventory, and are never merged into archive state. A stale `.partial`
blocks that destination row and requires review; RAWDOG does not auto-delete
pre-existing `.partial` files. If RAWDOG creates a `.partial` during the current
copy attempt and that copy fails, it removes that current-run artifact before
raising the error.

## Development

RAWDOG targets Python 3.12+.

```bash
python -m pytest
```

## Packaging

RAWDOG is structured as a normal Python CLI package with a `pyproject.toml`
entry point:

```text
rawdog = "rawdog.cli:app"
```

Install from a local checkout during development with:

```bash
python -m pip install -e ".[test]"
```

Homebrew packaging prep lives in [docs/HOMEBREW.md](docs/HOMEBREW.md) and
[packaging/homebrew/rawdog.rb.template](packaging/homebrew/rawdog.rb.template).
The formula needs release tarball URLs, checksums, and Python dependency
resources before it should be published to a tap.

## License

RAWDOG source is licensed under the [Apache License 2.0](LICENSE). Operational
use is also covered by [TERMS.md](TERMS.md).

Author: Nicholas Corrieri  
GitHub: @nickcorrieri  
Owner: InnoNotion LLC

Reuse must preserve the source attribution:

```text
Author: Nicholas Corrieri
```

The attribution notice is also recorded in [NOTICE](NOTICE).
