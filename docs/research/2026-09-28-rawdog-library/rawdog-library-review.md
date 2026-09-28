# RAWdog library and safety review

Reviewed 2026-09-28 at commit `1f1e2d02055a987c4dd7eef2ef02a74779b15731`. Source review and synthetic fixtures only. No repository changes, dependency installation, or operations on real media.

**Recommendation:** evolve RAWdog into a Mac archive manager with a searchable library catalog, explicit backup protection, reversible duplicate quarantine, and verifiable placement. Reuse the Python engine and existing SQLite/planning primitives. Scope editing, facial recognition, cloud synchronization, and Lightroom catalog mutation separately if they become real requirements.

## Independent review comparison

| Reviewer | Distinct evidence and emphasis |
| --- | --- |
| Astra | Reproduced two archive copies deleting each other through a generated report; reproduced overwrite during copy, equal-size false duplicate skipping, and false-success audit. Flagged clone identity and backup modeling. |
| Sol | Independently reproduced archive deletion, overwrite, and false-success audit. Also reproduced a file changed during confirmation being deleted and an obsolete hash surviving quick cataloging. |
| Parent | Ran all 201 tests; reproduced cloned registration replacing the primary pointer, stale hash/full-catalog status, and the placement report accepting inconsistent filename date versus directory date. Developed the combined product and migration proposal. |

Both independent reviews support fixing the storage engine before expanding cleanup or putting a GUI in front of it. This is a comparison of findings on one task, not a general ranking of models. Sol's separate estimate totals 31–57 engineering days; the staged estimate below budgets more room for a dependable packaged Mac release.

## What is already useful

RAWdog has persisted execution plans and row histories, operation manifests, portable per-store catalogs, capture-date and hash naming policies, SHA-256 utilities, copy verification, same-filesystem moves, and catalog rebuilds. These are substantial foundations. Copying new bytes verifies the partial file before finalization; the weaknesses below concern existing-file decisions, finalization, destructive cleanup, identity, and audit interpretation.

The main structural obstacle to a GUI is the roughly 9,600-line [CLI module](../../../rawdog/cli.py), which contains application workflows alongside terminal presentation. Extract workflows behind stable structured requests/results while retaining the current CLI as a client.

## Findings to fix before expanding cleanup

1. **P1: cleanup can remove archive files, including every copy in a candidate group.** Source scans can overlap the archive. Astra generated a normal report from a parent folder containing two identical archive files: each became the other's retained copy, and committed SHA-256-checked scrap deleted both. Sol independently reproduced deletion of a registered den used as a source. The source resolver permits overlap, the matcher accepts the other file, and cleanup validates the batch before calling `unlink`. Reject protected archive/backup sources by default, reject source/keeper aliasing, and ensure every retained copy is outside the entire mutation set. Evidence: [source resolution](../../../rawdog/cli.py#L7519), [matching](../../../rawdog/cli.py#L7585), [scrap validation](../../../rawdog/cli.py#L7882), [deletion](../../../rawdog/cli.py#L7993).

2. **P1: append-only finalization can overwrite another file.** The existence check happens before copying; finalization uses overwrite-capable `os.rename`. Both Astra and Sol independently inserted a destination during copying and observed it being overwritten. Use exclusive temporary-file creation and an atomic no-replace finalization primitive appropriate to each supported filesystem. Repeating `exists()` does not close the race. Apply the same contract to moves and restoration. Evidence: [copy primitive](../../../rawdog/copier.py#L41), [move primitive](../../../rawdog/copier.py#L151).

3. **P1: a failed audit can still mark a plan complete.** The audit returns `size_mismatch`, but execution counts only statuses beginning with `needs` or ending with `missing` as review items. Both independent reviewers reproduced an expected three-byte file becoming four bytes while the plan finished `done` with zero review items. Model audit outcomes explicitly and block completion on every failed required check. Evidence: [audit result](../../../rawdog/cli.py#L6737), [result aggregation](../../../rawdog/cli.py#L6978), [completion](../../../rawdog/cli.py#L7031).

4. **P1: filename plus size can skip distinct originals.** Canon rollover filenames, timestamps, and camera IDs are useful search attributes, not content identity. Different four-byte files with the same camera basename are skipped as existing. Fetch planning also accepts an existing equal-size destination without hashing. Require full SHA-256 identity before classifying an exact duplicate; otherwise preserve both files and expose a collision or reviewed unique placement. Evidence: [copy comparison](../../../rawdog/copier.py#L33), [planning](../../../rawdog/planner.py#L83), [filename candidate reuse](../../../rawdog/filenames.py#L48).

5. **P1: cleanup proof can become stale during confirmation.** Hashing precedes the user prompt. Scrap then unlinks without revalidation; force-move duplicate removal rechecks size but not the previously verified content. Sol reproduced a file changed at confirmation being deleted. A quarantine/purge operation must validate identities at mutation time, protect the keeper set, record durable intent before changing files, and recover safely after interruption. Evidence: [scrap confirmation and deletion](../../../rawdog/cli.py#L7948), [force-move deletion](../../../rawdog/cli.py#L9103).

6. **P2: a cloned backup can replace the primary registration.** Registration reuses the portable store ID and changes that record's root. The parent review copied a store identity to a second live fixture directory and registered it: two directories remained on disk but only the backup root remained registered. Distinguish relocation from cloning and give intentional backups separate physical identities. Evidence: [store registration](../../../rawdog/stores.py#L78).

7. **P2: a changed file can retain an obsolete hash and full-catalog status.** Quick catalog updates preserve the old SHA-256 and full-catalog timestamp. Status counts full cataloging by path presence. The parent review changed four bytes to eight, ran quick cataloging, and observed the old hash retained while the file counted as fully cataloged with zero stale rows. Record the exact file observation associated with each hash and invalidate verification when that observation changes. A fresh destructive-action check remains necessary even with a cache. Evidence: [quick upsert](../../../rawdog/stores.py#L414), [catalog status](../../../rawdog/stores.py#L446).

8. **P2: correct-looking folders do not prove correct placement.** The organization report checks folder shape and agreement between folder years; it does not compare the file's capture metadata or project assignment against its location. A 2026-named fixture under a valid 2020 date folder produced no findings. The standalone verify command is also unimplemented. Evidence: [organization checks](../../../rawdog/cli.py#L4188), [verify stub](../../../rawdog/cli.py#L7454).

## Content identity and Canon names

| Observation | Recommended interpretation |
| --- | --- |
| Same filename, different full SHA-256 | Different files; preserve both. |
| Different filenames, same full SHA-256 | Exact byte copies; inspect each copy's role. |
| Same full SHA-256 on an intentional backup | Protected replica, excluded from ordinary dedupe. |
| RAW and JPEG from the same capture | Related representations, not byte duplicates. |
| Similar thumbnails or matching EXIF IDs | Review hints; insufficient for removal. |

Retain original filename, source path, capture metadata, camera/body identifier where available, and import provenance. Capture time, original name, and a short hash can produce readable destination names, but only the full digest is identity. Existing files should be renamed only through an explicit reviewed plan. Preserve RAW/JPEG/XMP relationships and account for editors that refer to file paths.

## A small central catalog

SQLite remains an appropriate starting point. Evolve the existing schema and portable catalogs rather than adding a server.

- **Content:** immutable byte identity, full SHA-256, size, media type.
- **Copies:** content ID, store ID, relative path, role, presence, last observed time, and last verified time.
- **Stores:** stable store and volume identity, current mount location, physical-device relationship where known, and online/offline state. Two folders or APFS volumes on one device should not automatically count as independent backups.
- **Capture context:** original and corrected timestamps, metadata source, timezone certainty, project/location, and related RAW/JPEG/sidecar objects.
- **Operations and audits:** expected identities/locations, per-file outcomes, quarantine/restore history, and evidence timestamps.

Keep a central last-known index for offline searching and per-drive portable metadata for recovery. A disconnected drive is offline, not proof that its files are missing. An intentional backup is an explicit policy, not something inferred from equal hashes. Support per-store defaults with per-copy protection when a drive mixes purposes.

Initially, backup tracking can simply answer: where are all known copies, which are protected, which devices hold them, and when were they verified? Automated synchronization is unnecessary for that first release.

## Pre-trash and final audits

Quarantine should be a recoverable operation, not just a folder name. For eligible unwanted copies, move within the same filesystem into a dedicated excluded quarantine area. Persist a manifest before mutation with the original path, quarantine path, content hash, retained copy, reason, and operation state. Provide restore, with no overwrite if the original location is now occupied. Do not promise reclaimed disk space until separately approved purge; quarantine still occupies storage. Keep archive and intentional-backup copies protected by default.

Protect against interruption between filesystem changes and database updates. Do not count quarantined files toward backup coverage, and do not rediscover them as new imports. Cross-volume work requires a separate verified copy-and-cleanup workflow.

Final audits should have separate outcomes for content integrity, expected placement, catalog consistency, and backup coverage. Compare actual files with a saved expected manifest, selected organization policy, capture-date provenance, and approved project assignments. Missing or ambiguous metadata should produce an unresolved finding instead of invented certainty. Reuse the planner's placement rules to prevent audit logic from drifting away from execution.

Acceptance fixtures should cover equal-size distinct Canon files, identical bytes with different names, repeated timestamps across cameras, protected backups, duplicate store IDs, changed files at confirmation, interruption at each quarantine step, restore collisions, unplugged/remounted drives, case-insensitive path collisions, and unsupported or unreadable metadata. These extend rather than duplicate the current suite.

## Mac interface

Prefer a thin SwiftUI desktop app over the existing Python engine if macOS remains the product focus. Define a versioned structured worker protocol for requests, progress, cancellation, plan previews, and results. The GUI should not parse terminal output or mutate the catalog through a separate implementation.

Start with five views: Library, Drives and Backups, Review, Quarantine, and Activity. Users should be able to find every copy of a camera filename, see why two files differ, preview a move, inspect backup coverage, and restore quarantined files. Lead with plain labels such as Import, Archive, Backups, and Review Duplicates; den/yard terminology can remain secondary branding.

Use native file pickers and Quick Look where supported. Packaging the Python runtime and metadata reader, filesystem permissions, reconnecting drives, cancellation, and signing/notarization are part of the effort. Apple documents [SwiftUI file import and resource access](https://developer.apple.com/documentation/SwiftUI/View/fileImporter%28isPresented%3AallowedContentTypes%3AonCompletion%3A%29) and [Quick Look previews](https://developer.apple.com/documentation/quicklook/). Camera-format preview support needs actual compatibility checks; do not assume every RAW format previews.

## Build order and effort

These are planning ranges for one experienced engineer, including focused regression/recovery tests and an initial migration path; they are not measured delivery promises.

| Stage | Deliverable | Approximate effort |
| --- | --- | --- |
| Safety | Fix archive deletion, overwrite race, identity decisions, stale cleanup proof, and false success | 1–2 weeks |
| Catalog | Central content/copy/store model, explicit backups, offline search, hash validity and migration | 2–4 weeks |
| Recovery and audit | Journaled quarantine/restore, separate purge, semantic placement and coverage audits | 2–3 weeks |
| Mac app | Focused native UI, structured worker bridge, progress/cancel, packaging and filesystem testing | 3–5 weeks |

A dependable scoped Mac release is roughly 8–14 engineering weeks. A read-only catalog/browser can ship earlier. Large legacy libraries, difficult drive failures, distribution requirements, and richer photo-management features increase that range. The expensive part is proving safe identity and recovery, not drawing windows.

## Validation and limits

The parent ran the entire existing suite: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` — **201 passed in 5.24 seconds**. Sol separately ran **69 focused tests, all passing in 2.78 seconds**. Astra and Sol were given the same product brief independently; Sol was not shown prior findings. Their synthetic probes expose behavior outside the passing suite. The parent separately reproduced stale catalog hashes, cloned registration replacement, and path-shape-only placement checks.

This review does not constitute exhaustive crash, hardware, or real-library validation. No fixes have been implemented.
