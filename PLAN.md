# RAWDOG Implementation Plan

RAWDOG is a RAW photo managing tool that can fetch, copy, and audit your RAW
libraries.

The product is photography-first archival tooling with intentionally memorable
branding. The project name, repository name, package branding, and CLI name are
RAWDOG.

## Product Boundaries

RAWDOG is append-only RAW archival tooling. It supports SD card ingest,
working-library organization, project-aware RAW workflows, archive commits,
verification, and reports.

RAWDOG is not sync software, cloud backup software, DAM software, a Lightroom
replacement, or aggressive dedupe tooling.

The core rule is:

```text
WORKING LIBRARY != PERMANENT ARCHIVE
```

Working libraries are local and mutable by the photographer. Permanent archives
are append-only and become the source of truth. Deletions must never propagate
backward into archive storage.

The old "make sure SOURCE -> DESTINATION" workflow is not RAWDOG's main product
shape. It may exist as an explicit verification/report option for operators who
want to check whether one source tree is represented in one destination tree,
but it is secondary to the photographer workflow: fetch, organize, breed,
verify, and report.

## Safety Rules

RAWDOG must never:

- delete archive files
- overwrite archive files
- rename originals
- auto-clean libraries
- auto-resolve collisions
- auto-merge projects

Collision policy is final:

```text
same filename + same filesize -> skip + document
```

No suffixes, duplicate renaming, or `__copy` variants are introduced.

## Organization Modes

RAWDOG supports two organization modes:

- Date-oriented
- Project-oriented

`rawdog init` asks how shoots are organized and stores the preference in config.

Date-oriented layouts default to:

```text
WORKING/YYYY/YYYY-MM/
ARCHIVE/YYYY/YYYY-MM/
```

Project-oriented layouts default to:

```text
WORKING/YYYY/YYYYMMDD_PROJECT/
ARCHIVE/YYYY/YYYYMMDD_PROJECT/
```

Both modes support configurable folder templates.

Users are not forced into a local working-library setup. RAWDOG supports import
profiles for local-to-external, external-to-external, SD-card-to-external, and
custom folder workflows. A profile records source root, destination root,
organization mode, and folder template so recurring shoots can reuse the last
known setup while one-off imports can override it. `rawdog fetch --profile last`
reuses the most recently used profile.

Commands are preview-first. `fetch` and `breed` do not mutate project/profile
memory, destination manifests, or archive files unless the operator explicitly
uses `--commit`. Source and destination roots must be distinct, and destination
roots cannot be nested inside source roots.

## Project Workflows

`rawdog fetch` supports:

- Existing project
- New project
- Date-only import
- Existing import profile
- New import profile
- Custom source/destination paths per import

`rawdog den` supports old-library consolidation. It is the RAWDOG version of
"clean up this old mess into the new structure": inspect a source, estimate the
copy queue, skip existing same-name/same-size files, surface collisions, and
copy append-only only when explicitly committed. `den` preserves existing source
folder structure by default so useful custom folder names and partial
date/project discipline survive consolidation. `preserve-dates` keeps the
structure but normalizes date-like folders such as `MMDDYYYY`, `MM.DD.YYYY`,
`YYYYMMDD`, or `YYYY.MM.DD` into `YYYYMMDD` moving forward. Optional `date` and
`project` layouts are available when the operator wants RAWDOG to impose a new
structure.

Consolidation workflows are tracked in SQLite so old-drive cleanups can be
planned, resumed, and reviewed without retyping source/destination roots.

`den` supports two transfer workflows:

- Cross-drive consolidation: copy from a messy source drive into a destination drive.
- Same-drive consolidation: copy or move from an old messy folder into a RAWDOG
  destination folder on the same drive.

Move is opt-in, same-filesystem only, and still requires reviewing the queued
plan before execution.

## Safe Plan Queues

RAWDOG can queue multi-step safe plans for long-running jobs, such as:

```text
audit -> copy -> audit -> copy
```

Queued steps may inspect, score, copy, or move unique files on the same
filesystem with no overwrite. Destructive actions are never queueable. Cleanup
of thumbnails, mismatch resolution, deletion, overwrite, rename, and automatic
dedupe reduction must require a separate explicit interactive command and must
not run independently from a queue.

Every copy or move execution starts by writing a durable execution plan to
SQLite. The plan records:

- what RAWDOG is doing
- what RAWDOG is doing it to
- what should be where when done
- execution progress
- post-execution audit status

If execution is interrupted, RAWDOG can inspect the latest plans and resume an
incomplete plan from the persisted row statuses. Execution is row-based: copied,
moved, skipped, collision, failed, and audited rows are marked individually.

New projects collect name, optional client, optional tags, optional location,
and optional notes.

When a project name is supplied during import, RAWDOG saves the project and the
source/destination pair as reusable memory. The default project folder is:

```text
{destination}/YYYY/YYYYMMDD_PROJECT
```

`YYYYMMDD` comes from the earliest RAW file in the project source. `PROJECT` is
the normalized project folder name.

RAWDOG memory has two layers:

- Canonical local memory in RAWDOG's SQLite database.
- Portable destination memory in `{destination_project_or_date_folder}/.rawdog/project.json`.

Destination memory is written under the destination project/date folder so an
external-volume workflow can carry project context with the drive. It is a
manifest, not a sync database, and it is never used to delete, rename, overwrite,
or auto-clean archive files.

Date-only imports also get destination memory. In that case the destination
folder is the configured date group, such as `{destination}/YYYY/YYYY-MM/` or
`{destination}/YYYY/MM/`, and `project_name` is null.

RAWDOG may suggest likely projects based on date proximity, card identity,
timestamps, camera body, folder structure, and recent imports. It must never
silently auto-assign a project.

## Session Detection

`rawdog fetch --detect-sessions` analyzes capture timestamps and suggests
session splits from large time gaps. The operator may rename sessions, merge
sessions, ignore splits, or assign sessions to existing projects.

Multiple shoots on one card are a normal case, not an edge case.

## Lightroom / Editor Workflow

RAWDOG does not sync Lightroom, watch Lightroom catalogs, or propagate
Lightroom rejects/deletes into archive storage. Lightroom, Capture One, and
similar tools are treated as working-library editors.

The intended flow is:

1. `rawdog fetch` imports RAWs into a working project/date folder.
2. The photographer edits, rejects, rates, exports, or deletes local working
   files in Lightroom or another editor.
3. `rawdog breed` archives the intentional current project state to one or more
   append-only destinations.
4. `rawdog sniff` / `rawdog report` can later report differences, but reports
   never become cleanup actions.

If Lightroom deletes a local working file before `breed`, RAWDOG does not copy
that file in that breed run. If the file already exists in an archive, RAWDOG
does not delete it from the archive.

`breed` can be run against multiple archive destinations over time, for example:

```bash
rawdog breed --project Wedding_Smith --dest /Volumes/WD_BLACK
rawdog breed --project Wedding_Smith --dest /Volumes/Backup_2
```

## Storage

RAWDOG uses SQLite as its local operational database. The initial schema includes
`projects`, `files`, `imports`, `copy_log`, and `anomalies`.

`projects.project_id` is the stable project identifier. `files.project_id` is a
nullable foreign key, allowing date-only imports and project-aware imports to
coexist.

## CLI

Running `rawdog` with no arguments opens a colored terminal workflow chooser.
`rawdog --help` remains the full command reference.

Initial CLI commands:

- `rawdog init`
- `rawdog fetch`
- `rawdog breed`
- `rawdog den`
- `rawdog sniff`
- `rawdog score`
- `rawdog status`
- `rawdog report`
- `rawdog verify`
- `rawdog profiles create`
- `rawdog profiles list`
- `rawdog workflows list`
- `rawdog queue create`
- `rawdog queue add-sniff`
- `rawdog queue add-score`
- `rawdog queue add-den`
- `rawdog queue show`
- `rawdog queue run`
- `rawdog plans list`
- `rawdog plans show`
- `rawdog plans resume`

## Incremental Build Order

1. Project skeleton
2. Config/init
3. Drive detection
4. SQLite schema
5. Inventory engine
6. Project system
7. Session detection
8. Fetch command
9. Breed command
10. Verification
11. Reports, including optional source-to-destination checks
12. Tests
13. Packaging/docs

Out of scope: watchers, daemons, cloud sync, GUI, accounts, and servers.
