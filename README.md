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

## Commands

```bash
rawdog init
rawdog fetch
rawdog breed
rawdog sniff
rawdog status
rawdog report
rawdog verify
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
