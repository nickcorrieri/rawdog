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

RAWDOG supports reusable import profiles. These are the existing RAWDOG profiles,
not a second profile system. A profile stores a source root, destination root,
organization mode, folder template, naming convention, collision policy, verify
preference, dry-run default, and exclude patterns. This supports normal local
working folders, SD-card imports, and external-volume-to-external-volume
workflows where the photographer does not want a local setup.
Use `rawdog fetch --profile last` to reuse the most recently used profile.

`fetch` detects whether the source looks semi-organized or like a raw camera
dump:

- semi-organized sources keep existing project/date folder names by default
- raw camera dumps are suggested for DDD placement
- mixed sources are flagged for operator review

RAWDOG only suggests this behavior. It does not silently reorganize a source.

`fetch` previews by default. Project/profile memory is written only when the
operator uses `--commit`.

When a project is named during import, RAWDOG remembers that project and the
source/destination pair. By default project imports land under:

```text
{destination}/YYYY/YYYYMMDD_PROJECT
```

`YYYYMMDD` is based on the earliest RAW file in the import source. That creates
one project folder. For project plus date buckets, use the den `project-dates`
layout. Its default month buckets look like `Soccer-202601`; day buckets look
like `Soccer-20260115`.

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
`rawdog backup` is an explicit alias for the same append-only workflow.

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
rawdog backup
rawdog den
rawdog dens setup
rawdog dens list
rawdog yard setup
rawdog yard list
rawdog junkyard
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
rawdog plans ops
rawdog plans resume
```

## Cleanup Consolidation

For old folders or drives that need to be gathered into a RAWDOG structure, use
`den`. It scans RAW files, builds a copy estimate, skips already-present
same-name/same-size files, and reports collisions for review.

```bash
rawdog dens setup primary --root /Volumes/Archive
rawdog yard setup primary --root ~/Pictures/RAWDOG
rawdog sniff /Volumes/OldDrive
rawdog score /Volumes/OldDrive
rawdog den /Volumes/OldDrive --dest /Volumes/Archive
rawdog den /Volumes/OldDrive --dest /Volumes/Archive --commit
```

App Support remembers known dens and yards. Each registered den or yard also
carries its own portable `.rawdog/store.json` and `.rawdog/store.sqlite` inside
that folder, so the store can still identify itself if a volume path changes.
Successful den copy/move rows under a registered den are written to that den's
local store catalog.

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

When RAWDOG finds a semi-destructive review item, such as a collision, stale
partial, failed move, or destination mismatch, it prints a short copy-paste AI
review prompt with the relevant paths. The prompt is meant for ChatGPT or
another assistant to help the operator reason through the situation before any
manual cleanup or retry. RAWDOG still refuses to delete originals or auto-resolve
collisions.

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
rawdog plans ops 1
rawdog plans resume 1
rawdog plans prune --dry-run --keep 20
```

`den` layouts are explicit about whether RAWDOG preserves existing folders or
generates new date/project folders:

| Layout | Result |
| --- | --- |
| `preserve` | Mirrors source folders exactly. No generated date grouping. Camera wrappers are kept. |
| `preserve-dates` | Keeps meaningful folders, normalizes existing date-like folders to `YYYYMMDD`, and drops camera wrappers such as `DCIM/100CANON`. For camera dumps, it generates date folders. |
| `date` | Ignores source folders and groups by capture date. Default is month: `YYYY/YYYY-MM`. Choose `--group-by day` for `YYYY/YYYYMMDD`. |
| `project` | Creates one dated project/session folder from the earliest file date, default `YYYY/YYYYMMDD_PROJECT`, and puts files directly inside it. |
| `project-dates` | Creates project plus date buckets. Default is month folders like `YYYY/Soccer-202601`. Choose `--group-by day` for `YYYY/Soccer-20260115`. |

Example project plus month grouping:

```bash
rawdog den /Volumes/WD_BLACK/102EOSR7 \
  --dest /Volumes/WD_BLACK/RAW_DEN \
  --layout project-dates \
  --project Soccer \
  --group-by month
```

If a project source spans many capture dates, RAWDOG warns that it may contain
multiple projects. Scope the project explicitly when needed:

```bash
rawdog den /Volumes/WD_BLACK/102EOSR7 \
  --dest /Volumes/WD_BLACK/RAW_DEN \
  --layout project-dates \
  --project Soccer \
  --group-by month \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

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

Camera-generated folders such as `DCIM`, `100CANON`, `102EOSR7`, `100NIKON`,
`100_FUJI`, `100MSDCF`, `100GOPRO`, `100OLYMP`, `100_PANA`, `100LEICA`,
`100MEDIA`, `NIKON`, or `SONY` are treated as camera dump structure, not project
folders. This applies even when the selected source itself is the camera folder,
such as `/Volumes/WD_BLACK/102EOSR7`.

If a camera dump represents a shoot, client, period, or session that you want
preserved, make that a project/session label instead of relying on the camera
folder name:

```bash
rawdog den /Volumes/WD_BLACK/102EOSR7 \
  --dest /Volumes/WD_BLACK/RAW_DEN \
  --layout project \
  --project Wedding_Smith_Ceremony
```

Dens can contain project folders, including nested project/session groupings.
Camera folders remain transport wrappers; project folders are the human archive
boundary.

`junkyard` is report-only. It compares registered yard files against registered
den catalogs and reports working files that appear safe to review for removal
because they are already recorded in a den. RAWDOG does not delete them.

```bash
rawdog junkyard --yard primary --den primary
```

If RAWDOG is interrupted, rerun `rawdog plans list`, inspect the latest started
or incomplete plan, review its filesystem manifest with `rawdog plans ops PLAN_ID`,
then press `r` from the operation review or run `rawdog plans run PLAN_ID`.
Rows already copied, moved, skipped, or held for review are not blindly repeated.

Old dry-run plans can be pruned from the local RAWDOG database. Prune is
conservative by default: it removes only old `planned` plans, never `started`,
`failed`, or `needs_review` plans.

```bash
rawdog plans prune --dry-run --keep 20
rawdog plans prune --commit --keep 20
```

RAWDOG does not shell out to hidden `cp`, `mv`, or `rm` commands for plan
execution. It writes an operation manifest for each persisted plan showing the
Python filesystem APIs it will use, such as `Path.mkdir`, `shutil.copy2`, and
`os.rename`, plus the source, destination, partial path, and safety rule for
each row. Commit and resume prompts require `COMMIT PLAN <id>` after this review.

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
