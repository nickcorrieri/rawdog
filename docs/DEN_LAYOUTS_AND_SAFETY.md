# RAWDOG Den Layouts And Safety

Author: Nicholas Corrieri

This document is for humans and coding agents patching RAWDOG's den
consolidation behavior. Den planning is one of RAWDOG's highest-risk areas:
it decides where originals will be copied or moved inside an archive. Changes
must be conservative, visible in the CLI, and covered by tests.

## Core Archive Rules

RAWDOG is append-only archival tooling.

- Never delete originals during `den`.
- Never overwrite an existing archive file.
- Never rename source files.
- Keep file names unchanged at the destination.
- Treat camera folders as transport wrappers, not projects.
- Preview first. Commit only after the operator reviews the plan.
- Preserve a review trail in SQLite and operation manifests.

The den root should stay clean. Except for explicit `preserve`, normal archive
layouts should not dump arbitrary source folders directly at the den root.

## Decisions Made

These are explicit product and safety decisions made during early RAWDOG
hardening. Treat them as project policy unless a human operator changes them.

- The den is the archive source of truth. It should be stable, reviewable, and
  append-only.
- A yard is a working library. It can have a portable catalog and can be
  audited/rebuilt, but it is not the permanent archive authority.
- App Support remembers known dens and yards, while each den/yard carries its
  own portable `.rawdog/store.json` and `.rawdog/store.sqlite`.
- Running setup on an existing portable store should relink it into App Support
  memory instead of creating a duplicate or crashing.
- `rawdog` with no subcommand should stay in the menu until the operator exits.
  Menu actions should not kick the operator out after a single dry-run.
- Top-level workflows use letter keys such as `F`, `DC`, `DM`, `J`, `S`, `P`,
  `W`, `M`, `H`, and `Q`. Numbered choices are reserved for path, den, yard,
  layout, plan, and submenu selection inside workflows.
- Initial setup lives under Manage (`M`) after first-run guidance. Hidden
  aliases such as `init` and `setup` may still route to Manage for compatibility.
- Yes/no prompts must accept `y`, `Y`, `yes`, `YES`, `n`, `N`, `no`, and `NO`.
- Folder pickers should retry after invalid input and tell the operator that
  Ctrl-C exits.
- Registered dens/yards should be listed before manual browsing when relevant.
- Operation review must show readable full paths. If a table truncates source
  or destination paths, use row blocks or verbose mode instead.
- Long copy/move jobs should show progress, throughput, and ETA based on the
  current run.
- RAWDOG should support RAW, JPEG, and common camera video files because many
  cameras shoot RAW+JPEG or stills+video in the same folder.
- AppleDouble `._*` sidecar files are not media originals and should not be
  treated as camera captures.
- Camera folders are transport wrappers. If the operator wants a meaningful
  label, they should use a project/session label.
- `preserve` is the only layout allowed to mirror source folders exactly.
- `preserve-dates` means preserve useful labels and date folders, but still
  place them under a top-level `YYYY`.
- Normal archive layouts should avoid writing arbitrary project folders at the
  den root.
- RAWDOG should warn when a plan would create adjacent duplicate years like
  `YYYY/YYYY`.
- Same-drive MOVE is allowed only when source and destination are on the same
  filesystem.
- Cross-drive cleanup should be copy, validate, then manual/report-driven
  cleanup. Do not pretend cross-drive copy is a filesystem move.
- Skipped rows are not delete approval. They mean RAWDOG did not transfer that
  row and the operator should review why.
- Junkyard is report-only. Any actual removal must come from an explicit report
  path and a separate scrap command.
- `junkyard-scrap` is dry-run by default and must revalidate current disk state.
- SQLite is a hint for cleanup, not proof. File presence and size must be
  checked on disk before a yard file appears cleanup-safe.
- Hash checking is optional but is the most meticulous cleanup validation.
- Active run locks prevent concurrent plan execution; force clear is a manual
  operator recovery action.
- `rawdog wings` exists to run RAWDOG under `caffeinate` for long jobs.

## Layout Contract

`rawdog den` supports five layout modes. These are user-facing contracts.

| Layout | Contract |
| --- | --- |
| `preserve` | Mirror source folders exactly. No generated date grouping. Camera wrappers are kept. This is the escape hatch for operators who truly want exact source shape. |
| `preserve-dates` | Preserve meaningful folders, normalize date-like folders, drop camera wrappers, and always place preserved folders under a top-level `YYYY`. |
| `date` | Ignore source folders and group files by capture date. Month default is `YYYY/YYYY-MM`; day grouping is `YYYY/YYYYMMDD`. |
| `project` | Create one dated project/session folder from the earliest capture date. Default is `YYYY/YYYYMMDD_PROJECT`; files go directly inside that project folder. |
| `project-dates` | Create project plus date buckets. Month default is `YYYY/PROJECT-YYYYMM`; day grouping is `YYYY/PROJECT-YYYYMMDD`. |

If behavior is ambiguous, prefer `preserve-dates` over `preserve` for archive
safety because it keeps labels while still year-scoping the den.

## Examples

### Preserve Dates

Source:

```text
spring tournament/IMG_0042.CR2
```

Destination:

```text
2021/spring tournament/IMG_0042.CR2
```

Source:

```text
Trips/05.16.2026 Senior Photos/IMG_0042.CR2
```

Destination:

```text
2026/Trips/20260516_Senior Photos/IMG_0042.CR2
```

Source:

```text
Wedding_Smith/DCIM/100NIKON/IMG_0001.NEF
```

Destination:

```text
2026/Wedding_Smith/20260115/IMG_0001.NEF
```

If that last path ever becomes `2026/2026/...`, treat it as a regression.
RAWDOG has a warning for adjacent duplicate year folders, but layout code
should still avoid producing them.

### Date

Source:

```text
DCIM/100CANON/IMG_0001.CR3
```

Destination with month grouping:

```text
2023/2023-10/IMG_0001.CR3
```

Destination with day grouping:

```text
2023/20231015/IMG_0001.CR3
```

### Project Dates

Command:

```bash
rawdog den /Volumes/CardDump \
  --dest /Volumes/WD_BLACK/RAW_DEN \
  --layout project-dates \
  --project Soccer \
  --group-by month
```

Destination:

```text
2026/Soccer-202601/IMG_0001.CR3
```

## Camera Folder Rules

Camera-generated folders are not project folders. RAWDOG should drop them in
`date`, `project`, `project-dates`, and `preserve-dates` where they are acting
as wrappers.

Examples include:

- `DCIM`
- `100CANON`
- `102EOSR7`
- `100NIKON`
- `100MSDCF`
- `100GOPRO`
- `100OLYMP`
- `100_PANA`
- `100LEICA`
- `100MEDIA`
- `NIKON`
- `SONY`

If the operator wants a shoot label, they should use `--project` or choose a
meaningful parent folder, not rely on a camera folder name.

## Duplicate Year Warning

RAWDOG warns when planned destination paths contain adjacent duplicate year
segments under the den root, for example:

```text
/Volumes/WD_BLACK/RAW_DEN/2024/2024/IMG_0001.CR3
```

The warning is intentionally operator-facing. It does not rewrite the plan
because silent path correction can hide bugs or surprise the operator.

Patch points:

- `rawdog/cli.py`
  - `_print_duplicate_year_warning`
  - `_duplicate_year_destination_paths`
  - `_destination_relative_parts`
  - `_has_adjacent_duplicate_year`
- `rawdog/den.py`
  - `_date_destination_without_duplicate_prefix`
  - `_year_scoped_preserved_path`
  - `_year_scoped_prefix`

The warning must run in both places:

- fresh `rawdog den` plan output
- persisted plan review via `rawdog plans ops`

## Required Tests For Layout Patches

When changing den layout behavior, add or update tests in `tests/test_den.py`.
At minimum, cover:

- meaningful folder under `preserve-dates` lands under `YYYY`
- camera wrapper folders are dropped
- date-like folders are normalized
- `YYYY/YYYY` duplication does not appear
- `preserve` still mirrors source folders exactly
- file names stay unchanged

For duplicate-year warning logic, use `tests/test_cli_picker.py`.

Useful tests:

```bash
.venv/bin/python -m pytest tests/test_den.py
.venv/bin/python -m pytest tests/test_cli_picker.py
.venv/bin/python -m pytest
```

## Manual Review Checklist

Before releasing a layout patch, create a dry-run plan against a small fixture
or real throwaway folder and inspect operation paths:

```bash
rawdog den /path/to/source --dest /path/to/RAW_DEN --layout preserve-dates
rawdog plans ops PLAN_ID --verbose --limit 100
```

Confirm:

- destinations are inside the den root
- no paths land directly under the den root unless `preserve` was selected
- no `YYYY/YYYY` adjacent duplicate appears
- camera wrappers are removed when expected
- source and destination paths are readable in the operation review
