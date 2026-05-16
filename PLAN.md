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
WORKING/YYYY/PROJECT/
ARCHIVE/YYYY/PROJECT/
```

Both modes support configurable folder templates.

## Project Workflows

`rawdog fetch` supports:

- Existing project
- New project
- Date-only import

New projects collect name, optional client, optional tags, optional location,
and optional notes.

RAWDOG may suggest likely projects based on date proximity, card identity,
timestamps, camera body, folder structure, and recent imports. It must never
silently auto-assign a project.

## Session Detection

`rawdog fetch --detect-sessions` analyzes capture timestamps and suggests
session splits from large time gaps. The operator may rename sessions, merge
sessions, ignore splits, or assign sessions to existing projects.

Multiple shoots on one card are a normal case, not an edge case.

## Storage

RAWDOG uses SQLite as its local operational database. The initial schema includes
`projects`, `files`, `imports`, `copy_log`, and `anomalies`.

`projects.project_id` is the stable project identifier. `files.project_id` is a
nullable foreign key, allowing date-only imports and project-aware imports to
coexist.

## CLI

Initial CLI commands:

- `rawdog init`
- `rawdog fetch`
- `rawdog breed`
- `rawdog sniff`
- `rawdog status`
- `rawdog report`
- `rawdog verify`

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
