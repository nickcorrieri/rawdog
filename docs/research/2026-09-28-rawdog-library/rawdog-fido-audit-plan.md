# Rawdog Fido: audit and proposed implementation plan

2026-09-28 · Audit target: `1f1e2d02055a987c4dd7eef2ef02a74779b15731`

Reviewed by the primary agent and an independent GPT-6 Sol/high subagent. This is a proposed plan, not an implementation or permission to operate on the photo library. No real media, application catalog, or repository files were changed. The repository remained clean.

## Recommendation

Build Fido as a preservation-first way to answer **what do I have, where are its copies, and what still needs attention?** Reuse Rawdog's SQLite, scanners, plans, metadata reader, and hashing. Fix the unsafe filesystem operations before enabling organization on originals. The first useful release should inventory multiple locations and propose verified copies into month folders; it should have no deletion or source-renaming capability.

A new NoSQL database is unnecessary. The problem is the identity and evidence recorded in the existing database, and the decisions made from that evidence. SQLite is already in use and fits a local application's transactional records; see [SQLite's application-file guidance](https://www.sqlite.org/appfileformat.html).

Do not infer that photos are lost from renamed exports or Lightroom missing-file indicators. In Lightroom Classic, external renames, moves, and offline drives can break references. Recover those references before reimporting or reorganizing files already under Lightroom management. [Adobe's missing-photo guidance](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html).

## What already exists

- Multiple registered dens and yards, portable store identities, and per-store SQLite catalogs.
- Month/day and project folder layouts, plus configurable destination naming.
- Quick cataloging and full cataloging with SHA-256 hashes.
- Persisted execution plans, progress, partial copies, resume paths, and source-to-destination records.
- Camera RAW, JPEG, and several video extensions, including CR3, MP4, and MOV.

The current default configuration already selects date-prefixed destination filenames: [config.py:50](../../../rawdog/config.py#L50). That could explain some unfamiliar imported names, but this audit did not inspect Nick's media or determine which operations were previously run.

The foundation is useful, but several claimed safety properties fail under realistic conditions. A GUI must not simply call those unsafe operations unchanged.

## Findings that must shape the build

| Priority | Finding and demonstrated consequence | Evidence |
| --- | --- | --- |
| P1 | **Cleanup can delete every copy inside a den.** Selecting a source root that contains a registered den generated reciprocal cleanup rows for two identical files in that den. Hash-checked scrap deleted both. Den protection and protection of the retained copy are missing. | [cli.py:7898](../../../rawdog/cli.py#L7898), [cli.py:7993](../../../rawdog/cli.py#L7993). Parent fixture: two generated rows, zero originals remaining. |
| P1 | **Copy finalization can overwrite an existing archive file.** A file created at the destination while copying was overwritten by the final rename; operation returned `copied`. | [copier.py:53](../../../rawdog/copier.py#L53). Independent `COPY_RACE` probe. |
| P1 | **A previously verified duplicate can change before deletion.** Replacing a source with different, equal-length content after hash review caused deletion of that now-unique file. | [cli.py:9103](../../../rawdog/cli.py#L9103). Independent `CHANGED_DUPLICATE` probe. |
| P1 | **Symlink checking occurs after resolving the link.** Duplicate cleanup deleted a target outside the yard and left a broken yard symlink. | [cli.py:8963](../../../rawdog/cli.py#L8963). Independent `SYMLINK_FORCE_DELETE` probe. |
| P1 | **The active-run marker is not an exclusive lock.** Two synchronized acquisitions both succeeded. This defeats the claimed single-writer protection. | [runlock.py:97](../../../rawdog/runlock.py#L97). Independent `RUNLOCK_RACE` probe. |
| P2 | **Plan completion can conceal failed evidence.** A planned skip whose destination disappeared finished `done`, zero review items. A changed-size MOVE source was relocated, recorded `size_mismatch`, and still finished `done`. | [cli.py:6737](../../../rawdog/cli.py#L6737), [cli.py:6918](../../../rawdog/cli.py#L6918), [cli.py:6976](../../../rawdog/cli.py#L6976). Independent `STALE_SKIP` and `CHANGED_MOVE` probes. |
| P2 | **Catalog hashes can be stale while status says fully cataloged.** Quick scanning a changed file updated its size but preserved its old SHA-256 and full-catalog marker. Status counted the path as fully cataloged. | [stores.py:423](../../../rawdog/stores.py#L423), [stores.py:467](../../../rawdog/stores.py#L467). Parent fixture confirmed an obsolete hash after a size change. |
| P2 | **Same filename and size are treated as an existing copy without proving identity.** Two different fixture contents produced a planned skip. Camera numbering collisions make this directly relevant. This branch alone did not delete the source, but it cannot prove successful preservation. | [den.py:311](../../../rawdog/den.py#L311), [compare.py:8](../../../rawdog/compare.py#L8). Parent fixture hashes differed. |

Additional scope gaps for the proposed organizer:

- The scanner omits XMP, literal MPEG/MPG, HEIC, and TIFF files. A fixture containing eight extensions returned only CR3, JPG, and MP4. This is a gap for the new requested workflow, not a claim that every such format was previously supported. [metadata.py:40](../../../rawdog/metadata.py#L40).
- A RAW file and its XMP companion are not managed as a bundle. Reorganizing the RAW alone can strand editing metadata.
- Store-file identity is primarily an absolute path; a relative path is stored but is not the unique occurrence key. Rebuilding removes absent rows, which can erase useful provenance. A moved drive or incomplete scan must not be mistaken for confirmed deletion. [stores.py:284](../../../rawdog/stores.py#L284), [stores.py:590](../../../rawdog/stores.py#L590).
- Missing embedded dates fall back to filesystem times. Date parsing also treats a timestamp without an offset as UTC. Store the original time, its source, and timezone uncertainty separately; do not present fallback dates as proven capture dates. [metadata.py:100](../../../rawdog/metadata.py#L100), [metadata.py:242](../../../rawdog/metadata.py#L242).
- The command module has 9,581 lines and owns substantive planning, cataloging, cleanup, and execution behavior. Extract only the functions needed by Fido into shared services as they are hardened; avoid a wholesale rewrite.

## Proposed Fido workflow

**Choose locations → inventory → inspect matches and uncertainties → review a copy plan → copy and verify → reconcile Lightroom → export derivatives.**

The visible result should distinguish:

| Status | What it actually establishes |
| --- | --- |
| Seen | A file was observed at a location on a named scan date. |
| Fingerprinted | A stable read produced a full content digest. |
| Copy verified | A recorded destination was read and matched the source's digest. |
| Offline | A known store is not currently available; its last observation is retained. |
| Missing on a completed scan | A previously observed occurrence was absent from a successful scan of its scope. |
| Needs review | Collision, conflicting date, unreadable file, changed source, or uncertain association. |
| Lightroom linked | Supported Lightroom evidence or an explicit user confirmation establishes the association. |
| Export found / upload confirmed | Separate derivative and delivery states; neither establishes original preservation. |

Do not collapse these into a single “imported” checkbox. An existing legacy file can be “observed in den” without inventing an import event or claiming Lightroom knows it.

## Implementation order and acceptance

### 1. Fix the filesystem safety boundary

Protect all entry points, including existing CLI cleanup commands. A Fido-only warning would leave the same hazards accessible elsewhere.

- Initially disable source deletion and MOVE in Fido. Quarantine destructive legacy commands until the findings are repaired. Keep repair scope explicit.
- Acquire a real exclusive lock and account for two app databases targeting the same store.
- Create unique, exclusively owned partial files. Publish completed files atomically without replacing an existing destination. Retain byte verification, handle failure safely, and record completion only after durable publication.
- Bind each plan row to the reviewed source version and content evidence. Recheck before mutation and after reads. Treat changed, missing, unreadable, or size-mismatched rows as unresolved, never successful.
- If cleanup returns later, reject protected den sources, aliases, overlapping roots, self-matches, and any plan that would remove its own retained copies. Revalidate after user confirmation. Prefer a reversible quarantine workflow before offering permanent deletion.

Acceptance: turn every demonstrated probe into a regression test; add two-writer, source-change, destination-appears, interruption/resume, and unavailable-volume cases. No operation overwrites an existing original or reports an unverified row as complete.

### 2. Build the reliable inventory on existing SQLite

Use separate concepts, not a new database product:

- **Content:** full SHA-256, byte length, media kind, metadata evidence.
- **Occurrence:** store ID, relative path, observed size and filesystem timestamps, last seen scan, current/offline/missing state. A copied portable store needs clone detection so two devices do not accidentally share one occurrence identity.
- **Scan:** selected root, start/end, completion, exclusions and errors. Persist in batches so large libraries can resume and the UI need not load everything into memory.
- **Operation history:** original name/path, destination mapping, source and destination evidence, verification time, and failure state. Extend current persisted plans rather than building a parallel job system.
- **Relationships:** RAW/JPEG capture pair, XMP companion, and derived export, with an evidence type and confidence. These relationships do not assert byte equality.

Default inventory does not alter scanned media or write into source folders. Store its results centrally; portable catalog updates are a separate explicit operation. Reuse existing portable store IDs where sound.

Hash caches belong to a specific observed version. Invalidate them when a file changes. Size/mtime shortcuts are hints for scheduling reads, never final evidence for deleting originals. Preserve old observations rather than wiping history on an incomplete scan.

Include all regular files in the basic inventory with explicit classifications, even when the app cannot decode them. Add supported parsing for the actual RAW/video/export formats and retain companions. Do not silently skip an unsupported file and imply the folder is fully accounted for.

Acceptance: changed content cannot retain “verified” status; an unplugged drive stays offline; permission errors make a scan incomplete; reconnecting a drive preserves history; rescanning overlapping roots does not inflate occurrence counts.

### 3. Add collision review and copy-only organization

Match in increasing order of uncertainty:

1. Full SHA-256 plus byte length identifies exact copies despite names or folder differences.
2. Metadata produces candidate relationships: timestamp including subseconds, camera serial/model when available, dimensions, duration, and original filename.
3. Local previews and visual similarity suggest edited/resized exports or related shots. Show side-by-side images or video contact sheets for review. Similarity never authorizes deletion or substitutes an exported JPEG for the RAW.

Different hashes can be different captures, metadata-modified versions, or derivatives. Preserve them until the relationship is understood. Burst frames remain separate assets. Do not require visual inference where hashing already settles exact-byte identity.

Proposed new-copy layout:

```text
Originals/2026/2026-05/20260517-142233__IMG_0123__a1b2c3d4e5f6.CR3
Exports/2026/2026-05/...
Needs-date-review/...
```

The short token is a readable identifier backed by the full digest; extend or disambiguate it if necessary. Preserve the original filename verbatim in the catalog. Keep an XMP companion paired to its RAW's destination stem and retain the original bundle mapping. Unknown capture dates go to review instead of silently using a download date. Persist the chosen name so rescans do not rename assets repeatedly.

Organize new copies, leave old locations intact, show additional disk space, and verify every destination. A retry must recognize verified content even if the destination was renamed by policy. Keep file bytes and embedded metadata unchanged in the first release.

Acceptance: repeated imports are idempotent; same name/date but different content preserves both; renamed exact copies are recognized; RAW/XMP bundles stay together; insufficient space and interruptions preserve all sources; no automatic deletion follows successful copy.

### 4. Reconcile Lightroom and establish a repeatable capture workflow

Lightroom edition and Canon model remain unanswered inputs. This plan assumes neither a particular camera nor Classic's local-catalog behavior for the cloud edition.

For **Lightroom Classic**, first make a catalog backup and inventory the expected original locations. Produce a missing-original reconciliation report with exact matches and uncertain candidates; use Adobe's supported Locate/Find Missing Folder workflow. Do not directly rewrite a live Lightroom database or mass-reimport unresolved photos, which would risk losing the association with existing edits. Any catalog reader must use a safe snapshot or supported export and be validated for the actual installed version.

For future captures: inventory card → copy to the chosen stable originals location → verify → establish an independent verified backup → import/link in Lightroom → edit → export separately. Track backup locations by device, not just by two folder names on one disk. iCloud/upload/print delivery is a separate explicit workflow, not evidence that RAW originals are preserved.

Maintain per-camera import batches with the observed date range, original folder names, counters, and verified counts. Show possible numbering resets and gaps as diagnostics only: resets, rollover, multiple bodies, deletions, and incomplete inventories prevent counters from proving total captures or loss. Camera settings can be recommended after the model is identified; Rawdog should not automatically rename files on the card or alter camera numbering.

Acceptance: existing edits remain linked; exported JPEGs never satisfy “RAW recovered”; offline originals remain distinct from unlocated originals; unknown historical imports stay unknown.

### 5. Add a thin GUI over the safe services

Use four initial views: Locations, Inventory, Review, and Copy jobs. The inventory needs month filters, search by original/current name, media type, copy locations, verification status, and date confidence. Review needs full paths and side-by-side candidates. Jobs need progress, pause/cancel, resume, and a readable outcome.

Start with one local interface appropriate to the confirmed platforms; do not select or install a desktop framework as part of this audit. Keep policy and filesystem decisions outside UI handlers so CLI and GUI share the same tested protections. Image similarity and cloud integrations can follow the useful inventory/copy workflow.

## Verification and limits

- Full existing suite: **201 collected; 200 passed, 1 failed**, in 6.79 seconds. Failure: `test_fetch_plan_example_prints_one_file_source_and_destination` at [test_cli_picker.py:828](../../../tests/test_cli_picker.py#L828); full filename assertion failed in a width-100 rendered preview using a long temporary path.
- Isolated recheck using a shorter temporary root: **1 passed**. The failure is sensitive to path length/rendering; the original full run is not reported as all-green.
- Parent: four fixture probes covering den cleanup, stale catalog hash, format coverage, and same-name/size identity. Independent Sol: six fixture probes covering overwrite, locking, stale skip, changed MOVE, post-review deletion, and symlink deletion.
- All destructive demonstrations operated solely on disposable files under the temporary directory. Existing Python environment used; no packages installed. No patches or release made.
- This reviewed the relevant code and workflow boundaries, not the actual photo collection. It establishes implementation defects and a build plan; it does not establish that Nick lost photos or enumerate missing captures.

Saved evidence: [parent probe script](rawdog-audit-probes.py.txt), [parent probe results](rawdog-audit-probes.json), [independent Sol probe results](rawdog-independent-audit-evidence.json), [full test log](rawdog-audit-tests.txt), and [preview recheck](rawdog-audit-preview-recheck.txt).

**First deliverable:** repaired safety primitives plus Fido's read-only multi-location inventory and collision report. Follow with reviewed copy-only month organization. Keep NoSQL migration, automatic dedupe deletion, live catalog writes, and cloud automation out of the initial build.
