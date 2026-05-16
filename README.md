# RAWDOG

RAW photo managing tool that can fetch, copy, and audit your RAW libraries.

RAWDOG is local-first, append-only archival tooling for photographers. It helps
you ingest from SD cards, manage working folders, organize project shoots,
archive permanently to external storage, verify copies, and generate reports.

RAWDOG is not sync software, cloud backup software, a DAM, a Lightroom
replacement, or aggressive dedupe tooling.

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

```bash
rawdog init
rawdog fetch
rawdog breed
rawdog sniff
rawdog status
rawdog report
rawdog verify
rawdog profiles create
rawdog profiles list
```

## Development

RAWDOG targets Python 3.12+.

```bash
python -m pytest
```

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
