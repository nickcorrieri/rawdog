# RAWdog

```text
   ____    ___   _       __   _
  / __ \  /   | | |     / /  | |
 / /_/ / / /| | | | /| / / __| | ___   __ _
/ _, _/ / ___ | | |/ |/ / / _` |/ _ \ / _` |
/_/ |_|/_/  |_| |__/|__/  \__,_|\___/ \__, |
                                      /____/
```

RAW photo managing tool that can fetch, copy, and audit your RAW libraries.

RAWdog is local-first, append-only archival tooling for photographers. It helps
you ingest from SD cards, manage working folders, organize project shoots,
archive permanently to external storage, verify copies, and generate reports.

RAWdog is not sync software, cloud backup software, a DAM, a Lightroom
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

RAWdog supports reusable import profiles. These are the existing RAWdog profiles,
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

RAWdog only suggests this behavior. It does not silently reorganize a source.

`fetch` previews by default. Project/profile memory is written only when the
operator uses `--commit`.

When a project is named during import, RAWdog remembers that project and the
source/destination pair. By default project imports land under:

```text
{destination}/YYYY/YYYYMMDD_PROJECT
```

`YYYYMMDD` is based on the earliest RAW file in the import source. That creates
one project folder. For project plus date buckets, use the den `project-dates`
layout. Its default month buckets look like `Soccer-202601`; day buckets look
like `Soccer-20260115`.

RAWdog keeps canonical memory in its local SQLite database and writes a portable
manifest to:

```text
{destination_project_or_date_folder}/.rawdog/project.json
```

For date-only imports, the configured date folder acts as the destination memory
area, for example `YYYY/YYYY-MM` or `YYYY/MM`.

## Lightroom Workflow

RAWdog does not sync Lightroom or track Lightroom rejects/deletes live. Use
Lightroom or another editor inside the working project folder, then run
`rawdog breed` when the project is ready to archive.

`breed` snapshots the current working project state to append-only archive
destinations. If a local working file was deleted before breed, RAWdog simply
does not copy it in that run. Existing archive files are not deleted.
`rawdog backup` is an explicit alias for the same append-only workflow.

```bash
rawdog breed --project Wedding_Smith --dest /Volumes/WD_BLACK
rawdog breed --project Wedding_Smith --dest /Volumes/Backup_2
```

`breed` is also preview-first. Use `--commit` only after reviewing the planned
archive destinations.

## Commands

Run `rawdog` with no arguments to open the colored workflow chooser. The menu is
organized by job:

- `F` - fetch card or folder files into a working yard.
- `DC` - den copy/archive working files into a den; sources stay in place.
- `J` - junkyard cleanup review; report den-recorded files for manual removal.
- `DM` - den move/consolidate same-drive files into a den.
- `S` - sniff, audit, inspect, score, run slow full audit, or rebuild a folder, yard, or den.
- `P` - review, run, resume, or prune old plans.
- `W` - work queue for longer safe jobs.
- `M` - manage initial setup, defaults, dens, yards, and stores.
- `H` - command examples.
- `Q` - quit.

Top-level workflow keys are letters so numbered menus can stay reserved for
path, den, yard, layout, and plan selections inside a workflow.

Use `rawdog --help` for the full command reference.

For maintainers and coding agents, see:

- `docs/DEN_LAYOUTS_AND_SAFETY.md` for den layout contracts and path safety rules.
- `docs/LLM_PATCHING_GUIDE.md` for decisions made, guardrails, LLM handoff prompts, patch constraints, and release checks.

```bash
rawdog init
rawdog fetch
rawdog breed
rawdog backup
rawdog den
rawdog dens setup
rawdog dens list
rawdog dens remove
rawdog dens rebuild
rawdog yard setup
rawdog yard list
rawdog yard remove
rawdog junkyard
rawdog junkyard-scrap
rawdog yard-reflow
rawdog filename-audit
rawdog sniff
rawdog score
rawdog status
rawdog report
rawdog verify
rawdog wings
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
rawdog plans review
rawdog plans time-shift
rawdog plans resume
rawdog plans active
rawdog plans active-clear --force
```

## Cleanup Consolidation

For old folders or drives that need to be gathered into a RAWdog structure, use
`den`. It scans RAW and camera video files, builds a copy estimate, skips already-present
same-name/same-size files, and reports collisions for review.

RAWdog remains RAW-first, but it also carries camera video files commonly written
beside stills by DSLRs, mirrorless bodies, action cameras, and cinema cameras:
`.mov`, `.mp4`, `.m4v`, `.mts`, `.m2ts`, `.mxf`, `.avi`, `.3gp`, `.mod`,
`.tod`, `.insv`, `.crm`, `.braw`, and `.r3d`.

```bash
rawdog dens setup primary --root /Volumes/Archive
rawdog dens rebuild primary --commit
rawdog yard setup primary --root ~/Pictures/RAWdog
rawdog dens remove primary
rawdog yard remove primary
rawdog sniff /Volumes/OldDrive
rawdog score /Volumes/OldDrive
rawdog
# choose S, then 5 for slow full audit; pick yard, den, common path, or manual path
# choose S, then 6 to report DEN organization or build a same-den date reflow plan
rawdog den-organization /Volumes/Archive
rawdog den-reflow /Volumes/Archive --group-by day
rawdog den-reflow /Volumes/Archive --group-by month --date-only
rawdog den-reflow /Volumes/Archive --group-by month --filename-policy date-og
rawdog yard-reflow ~/Pictures/RAW_YARD --group-by month
rawdog den /Volumes/OldDrive --dest /Volumes/Archive
rawdog den /Volumes/OldDrive --dest /Volumes/Archive --commit
```

App Support remembers known dens and yards. Each registered den or yard also
carries its own portable `.rawdog/store.json` and `.rawdog/store.sqlite` inside
that folder, so the store can still identify itself if a volume path changes.
Successful den copy/move rows under a registered den are written to that den's
local store catalog.

Use `rawdog dens rebuild primary --commit` to completely rebuild a den's
portable catalog from the RAW/camera video files currently on disk. Rebuild scans
the den, removes stale catalog rows for files no longer present, adds newly found
files, and preserves known original-source links when the destination path still
matches an existing catalog row. It does not move, delete, or rename media files.
After JPEG support upgrades, run this once for established dens if they were
cataloged before JPEG files were included.

Use `rawdog den-organization DEN_ROOT` to scan a den for path-shape problems
without moving files. It reports double year folders, files outside a top-level
`YYYY` folder, missing date buckets, year mismatches, and multiple date buckets.
Use `rawdog den-reflow DEN_ROOT --group-by day` or `--group-by month` to create
an in-place same-DEN rename/move plan. It reprocesses the existing den into the
selected date bucket and filename policy without copying to another den.
Existing destination files are never overwritten, and conflicts are marked before
any commit prompt.

Use `rawdog yard-reflow YARD_ROOT --group-by month` to repair a flattened yard
in place. The default filename policy is `date-og`, for example
`20260912-132932-99__LS7A0001.CR3`. This makes Canon rollover names sort by
capture time while keeping the original camera basename searchable. Other
policies include `original`, `og-date`, `og-hash`, `og-iuid`, and `iuid-og`.
This makes Canon rollover names searchable without treating `101EOSR7`,
`102EOSR7`, or `103EOSR7` as proof that files are duplicates.

Use `rawdog filename-audit YARD_OR_DEN LS7A0001 --hash-check` to search by a
partial camera filename/camera ID. RAWdog strips its own date suffixes for this
audit, so `LS7A0001.CR3`, `LS7A0001__20260912-132932-99.CR3`, and
`20260912-132932-99__LS7A0001.CR3` group under the same camera ID.

If a camera clock was wrong by a known offset, use `--time-shift` on reflow to
plan corrected folders and names without rewriting RAW metadata:

```bash
rawdog den-reflow /Volumes/WD_BLACK/RAW_DEN --group-by month --time-shift +1h30m
rawdog yard-reflow ~/Pictures/RAW_YARD --group-by month --time-shift -2d
```

Time-shift reflow plans also create database rows grouped under the execution
plan. Review what RAWdog planned and what happened afterward with:

```bash
rawdog plans time-shift PLAN_ID
rawdog plans time-shift PLAN_ID --export ~/Desktop/time-shift-review.csv
```

Running `dens setup` or `yard setup` on a folder that already has `.rawdog`
metadata relinks that portable store into App Support memory. If the requested
store name is already used by another store of the same type, RAWdog assigns the
next available name instead of crashing. `dens remove` and `yard remove` only
forget the App Support pointer; they do not delete media files or the portable
`.rawdog` catalog.

New `rawdog init` configs default both yard imports and den copy/move plans to
`date-og` filenames. Change this in `M -> 8` or with `rawdog init
--yard-filename-policy original --den-filename-policy original` if you need
literal camera filenames.

Two consolidation workflows are supported:

- External drive to destination drive: audit the source and copy into the destination.
- Same-drive cleanup: audit an old folder on the destination drive, then copy
  or move into the RAWdog structure.

Use `--action copy` for cross-drive consolidation. Use `--action move` only for
same-drive cleanup when you intentionally want the old folder contents relocated
after reviewing the queued plan.

## Safe Plan Queues

Long jobs can be queued as safe plans, previewed, and then committed with an
explicit confirmation. Before any copy or move executes, RAWdog writes a
persisted execution plan to SQLite. The plan records:

- what RAWdog is doing
- what RAWdog is doing it to
- what should be where when done
- execution status
- post-audit status

Queues are for operations such as:

- audit/inspect
- score
- copy
- same-filesystem move of unique files with no overwrite

Destructive cleanup is never queued. RAWdog must not queue deletion, mismatch
cleanup, thumbnail cleanup, overwrite, rename, or automatic dedupe reduction.
No queued operation may silently resolve collisions.

When RAWdog finds a semi-destructive review item, such as a collision, stale
partial, failed move, or destination mismatch, it prints a short copy-paste AI
review prompt with the relevant paths. The prompt is meant for ChatGPT or
another assistant to help the operator reason through the situation before any
manual cleanup or retry. RAWdog still refuses to delete originals or auto-resolve
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
rawdog wings queue run old_drive_cleanup --commit
rawdog plans list
rawdog plans show 1
rawdog plans ops 1
rawdog plans resume 1
rawdog plans prune --dry-run --keep 20
```

`den` layouts are explicit about whether RAWdog preserves existing folders or
generates new date/project folders:

| Layout | Result |
| --- | --- |
| `preserve` | Mirrors source folders exactly. No generated date grouping. Camera wrappers are kept. |
| `preserve-dates` | Keeps meaningful folders, normalizes existing date-like folders to `YYYYMMDD`, drops camera wrappers such as `DCIM/100CANON`, and always puts preserved folders under a top-level `YYYY`. Example: `spring tournament/IMG_0042.CR2` becomes `2021/spring tournament/IMG_0042.CR2`. |
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

If a project source spans many capture dates, RAWdog warns that it may contain
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

Camera folder numbers are not global file numbering. A camera can roll from a
high filename such as `LS7A9999.CR3` back to `LS7A0001.CR3` in a later camera
folder. Do not delete or dedupe by basename alone. Use full path, exact size,
and SHA-256 when deciding whether two files are the same original.

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

`junkyard` starts with a report. It can compare registered yard files or an
arbitrary source folder against a den and reports working files that appear safe
to review for removal because they are represented in the den. RAWdog checks
source-linked catalog rows first, then falls back to unique filename + exact-size
matches in the selected den. Ambiguous filename + size matches are skipped.
The SQLite catalog is only a hint: Junkyard always checks the matched den path on
disk and requires the current den file size to exactly match before a source file
appears in the report.

RAWdog scans RAW, JPEG, and common camera video files. Use `--hash-check` for
exact byte matching: RAWdog reads both the source file and matched den file and
requires matching SHA-256 before reporting the file as cleanup-safe.
`--hash-check` can take a long time on large libraries. RAWdog does not delete
files during `junkyard`.

When candidates are found, RAWdog writes a TSV report with explicit source path,
matched den path, size, match method, and source/den root metadata. Use `rawdog
junkyard-scrap REPORT` to preview removal from that exact report. Scrap
revalidates that each source path is under a registered yard or the report's
source root, each matched den path is under a registered den or the report's den
root, both files exist, and both still match the report size. Add
`--hash-check` to `junkyard-scrap` for exact byte matching before removal. On
`--commit`, only the report's source paths can be removed after typing the exact
confirmation phrase. Cleanup requires SHA-256 exact matching by default; use
`--trust-size` only when you intentionally accept path + size validation. Use
`--each` with `--commit` to confirm each source file one at a time. Den files
are never touched. When a registered yard file is removed, RAWdog marks that row
`deleted` in the yard's portable catalog so later catalog-aware tools do not keep
treating the missing file as present.

```bash
rawdog junkyard --yard primary --den primary
rawdog junkyard --source /Volumes/WD_BLACK/100CANON/2021 --den primary
rawdog junkyard --yard primary --den primary --before 2026-04-01
rawdog junkyard --yard primary --den primary --validate-first
rawdog junkyard --yard primary --den primary --hash-check
rawdog junkyard-scrap ~/Library/Application\ Support/rawdog/reports/junkyard-candidates-YYYYMMDD-HHMMSS.tsv
rawdog junkyard-scrap ~/Library/Application\ Support/rawdog/reports/junkyard-candidates-YYYYMMDD-HHMMSS.tsv --commit
rawdog junkyard-scrap ~/Library/Application\ Support/rawdog/reports/junkyard-candidates-YYYYMMDD-HHMMSS.tsv --commit --each
```

If RAWdog is interrupted, rerun `rawdog plans list`, inspect the latest started
or incomplete plan, review its filesystem manifest with `rawdog plans ops PLAN_ID`,
then press `r` from the operation review or run `rawdog plans run PLAN_ID`.
Rows already copied, moved, skipped, or held for review are not blindly repeated.
During execution, RAWdog shows live progress for total files, total bytes, the
current source/destination, elapsed time, and copied/skipped/failed counts.
For large copy jobs, RAWdog prints a rough time estimate before commit so the
operator can decide whether to run now or leave the plan queued.

For same-drive consolidation, `--action move` uses an atomic filesystem rename
and usually preserves Finder Created date because the original file record moves.
For copy mode, RAWdog copies to `.partial`, renames into place, then immediately
attempts to preserve macOS Finder Created date on that completed destination file
before continuing to the next file. This is best-effort because creation time is
filesystem-specific; RAWdog still preserves modified time and records the source,
destination, and capture-date-derived plan in its database and manifest.

Old dry-run plans can be pruned from the local RAWdog database. Prune is
conservative by default: it removes only old `planned` plans, never `started`,
`failed`, or `needs_review` plans.

Use `rawdog plans review <id>` to inspect failed, skipped, held, and
review-needed rows 20 at a time. Press Enter for the next page or `0` to stop
inspection.

Skipped MOVE rows that are duplicates by name and size are not automatically
destructive. Review them with `rawdog plans force-move-duplicates PLAN_ID`.
That command hashes the source and destination with SHA-256, then `--commit`
removes only sources that are exact byte duplicates. It never overwrites the
destination.

```bash
rawdog plans prune --dry-run --keep 20
rawdog plans prune --commit --keep 20
rawdog plans skipped 33
rawdog plans time-shift 33
rawdog plans force-move-duplicates 33
rawdog plans force-move-duplicates 33 --commit
```

RAWdog does not shell out to hidden `cp`, `mv`, or `rm` commands for plan
execution. It writes an operation manifest for each persisted plan showing the
Python filesystem APIs it will use, such as `Path.mkdir`, Python file copy,
`shutil.copystat`, `os.rename`, and macOS `setattrlist` best-effort metadata
preservation, plus the source, destination, partial path, and safety rule for
each row. Commit and resume prompts require `COMMIT PLAN <id>` after this review.

While a plan is executing, RAWdog writes an `active-run.json` marker beside the
local SQLite database. `rawdog status` and `rawdog plans active` show that active
run and warn you to avoid Homebrew upgrades, drive disconnects, or starting
another plan while a copy/move is running. If RAWdog is force-killed and the
marker is left behind, clear it only after confirming no RAWdog copy/move is
running:

```bash
rawdog plans active-clear --force
```

On macOS, use `rawdog wings` to run or attach to RAWdog through `caffeinate` so
the Mac stays awake during long copy/move work:

```bash
rawdog wings plans resume 10
rawdog wings den /Volumes/Old --dest /Volumes/Archive --commit
rawdog wings --pid 12345
rawdog wings
```

With no arguments, `rawdog wings` attaches to the current active RAWdog run if
one exists. Locking the screen is fine; sleeping, logging out, unplugging drives,
or disconnecting docks is not.

`.partial` files are temporary transfer artifacts created only under the
destination root during copy. They are not original RAW/camera video files, are ignored during
source inventory, and are never merged into archive state. A stale `.partial`
blocks that destination row and requires review; RAWdog does not auto-delete
pre-existing `.partial` files. If RAWdog creates a `.partial` during the current
copy attempt and that copy fails, it removes that current-run artifact before
raising the error.

## Development

RAWdog targets Python 3.12+.

```bash
python -m pytest
```

## Packaging

RAWdog is structured as a normal Python CLI package with a `pyproject.toml`
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

RAWdog source is licensed under the [Apache License 2.0](LICENSE). Operational
use is also covered by [TERMS.md](TERMS.md).

Author: Nicholas Corrieri  
GitHub: @nickcorrieri  
Owner: InnoNotion LLC

Reuse must preserve the source attribution:

```text
Author: Nicholas Corrieri
```

The attribution notice is also recorded in [NOTICE](NOTICE).
