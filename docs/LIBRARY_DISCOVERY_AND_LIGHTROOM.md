# Finding forgotten photos and missing Lightroom originals

Owner direction, 2026-09-28: target a Mac and Windows GUI, explain Lightroom
libraries, locate missing originals/folders across machines and drives, and catch
card dumps made outside Rawdog. This extends the [library plan](LIBRARY_MANAGER_PLAN.md).
It is a product specification; no real machines, media or catalogs are being scanned.

## The experience

Rawdog should answer four separate questions:

1. Where have we found this original and its related files?
2. Which independent copies have been verified, and how recently?
3. Where does a selected Lightroom catalog expect the original to be?
4. What appeared or changed outside Rawdog since our previous inventory?

An illustrative discovery card: “New photo folder found on Travel SSD. Some files
already have verified copies; others have no known backup. Review this folder.”
Offer inspect, compare, plan copies, register an intentional backup or dismiss
this observation. Dismissal does not establish backup coverage or ignore future
changes. Never force a user to remember which importer they used.

## Explain Lightroom using the user's actual evidence

For Lightroom Classic, distinguish these items in plain language:

| Item | Explanation in the interface |
| --- | --- |
| Original | The RAW/JPEG/video file, with its actual computer, drive and path. |
| Catalog | Records pointing to originals and holding edits/organization; show the selected catalog and snapshot date. |
| Preview / Smart Preview | A representation that may remain viewable while the original is unavailable. It does not establish an available original. |
| Export | A rendered derivative such as a resized JPEG; separate from its RAW or edited master. |
| Backup | A separately identified copy with a role, device and verification history; track catalog backups separately from original-file backups. |

Classic imports create catalog references to photos; previews permit work while
originals are disconnected. See Adobe's [catalog explanation](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/lightroom-catalog-basics.html)
and [Smart Preview documentation](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/lightroom-smart-previews.html).
Teach with evidence such as “Lightroom expects this path; Rawdog last saw the
original on this drive,” avoiding an unexplained red “missing” badge.

Confirm the edition. Lightroom desktop also has distinct Local and Cloud workflows;
Classic catalog behavior must not be assumed for them. Adobe describes these in
[accessing local and cloud photos](https://helpx.adobe.com/lightroom/desktop/add-import-and-capture-photos/access-photos.html).
Start with a qualified Classic adapter; other editions remain separate capabilities.

## One searchable inventory across selected machines and locations

Index all regular files within enrolled roots, classifying media, companions,
catalogs, partial artifacts and opaque files separately. Offer photo folders first
and an explicit broader drive search for forgotten locations. Display excluded,
inaccessible and never-scanned locations. Do not claim an entire machine was
searched when only selected roots were scanned. Scanning scope does not authorize
organization of every discovered file.

Start with local SQLite inventories and versioned, explicitly exchanged snapshots
from other machines. A combined index imports observations; it does not need the
photo bytes or a live SQLite file shared between computers. Automatic exchange
can follow later with explicit pairing and selected scope. No automatic network
discovery, remote media mutation or background installation is required now.

Record these separately:

- Machine/enrollment identity, storage identity, root mapping and original relative
  path spelling. Drive letters and mount names are observations, not identities.
- File/content identity, companions and roles; physical storage/independence
  evidence. Two computers seeing one network share are not two backups.
- Scan scope, exclusions, errors, completion, observation and verification times,
  plus adapter/capability versions. Unknown coverage remains unknown.
- Snapshot schema, source identity/generation and monotonically increasing source
  revision. Reject stale/replayed updates; machine clocks do not establish ordering.
- Historical presence and scoped absence observations. Importing an incomplete or
  older snapshot must not erase newer knowledge or imply a file was deleted.

Offline devices remain searchable by their last known inventory. A remote snapshot
is dated evidence, not a live check by the current computer. Distinguish relocation
from cloned portable IDs, aliases and ambiguous volume identities; do not merge
them silently. Overlapping roots must not inflate occurrence counts. Snapshot
imports use selected scopes and bounded data validation; reported paths are data,
never permission to operate on another machine or traverse outside enrolled roots.

This can grow toward a complete inventory as each machine/drive is enrolled and
scanned. A machine never scanned or an unplugged unknown drive cannot be searched.
Cloud placeholders are reported without silently downloading originals.

## Catch “I dumped my cards here and forgot”

Use filesystem notifications as prompts to inspect, with reconciliation scans as
the correctness mechanism. Implement platform-specific event handling later;
do not make reliable discovery depend on an uninterrupted notification stream.

| Trigger | Required behavior |
| --- | --- |
| First enrollment | Establish the existing inventory; label it newly observed, without inventing when it was copied or imported. |
| App startup / resume | Reconcile enrolled available roots against the last completed scan. Catch changes made while Rawdog was closed. |
| Folder event while running | Queue affected scope for inspection, coalesce bursts and preserve incomplete work. |
| Drive reconnect | Reidentify the drive, reconcile its enrolled roots and expose unresolved identity conflicts. |
| Scheduled reconciliation | While the app or an enabled helper runs, rescan to catch dropped events, renamed folders and event-history gaps. |
| Optional background helper | With explicit enablement, observe changes while the GUI is closed; show running/paused status. Startup reconciliation remains necessary. |

If both GUI and helper are off, discovery waits until the next run. Files created
and removed entirely between observations may never be knowable. Files outside
enrolled roots need a broader scan before Rawdog can discover them. Show last
completed scan and any discovery gap rather than promise continuous protection.

Directory enumeration must discover new paths even when a copied photo keeps an
old modification timestamp. First-seen time is not shot time or actual copy time.
Group likely card dumps using folder boundaries, camera metadata and capture
ranges as hints; mixed cameras, reused DCIM names and preexisting files are valid.

Wait for a stable read before assigning a content digest; a quiet interval or
unchanged size alone does not prove copying is finished. Changed-during-read,
partial, truncated and unreadable files stay pending or need review. A matching
existing backup must be checked under the ordinary freshness and payload rules.

Newly observed, exact copy known, independent backup verified and Lightroom
reference observed are separate fields. Catalog linkage is unknown if no current
qualified catalog evidence exists; “not in the selected catalog snapshot” is
narrower than “never imported.” Detect changed content or companions at an old
path, and avoid repeated notifications for an unchanged observation.

Discovery produces a review queue. It does not move, repair, import into Lightroom
or delete found files. An ordinary finder/explorer card dump should be a supported
way to get work into that queue.

## Locate missing Lightroom files and folders

Read a consistent, version-qualified catalog snapshot or supported export. The
acquisition method must handle an open catalog correctly; copying only one file
from a live database is not assumed to yield a consistent snapshot. Record catalog
identity/version, snapshot age, selected scope and unavailable metadata fields.
Do not promise a stable private schema or alter a live catalog. Different catalogs,
virtual copies and multiple references to one original remain distinct records.

1. Extract expected source paths and available original-name, capture-date, camera,
   dimensions and format evidence. Determine whether expected storage is offline,
   inaccessible, path-remapped, or scanned and missing. Unknown stays unknown.
2. Search Rawdog's available and historical inventories, including other machines.
   Prefer a previously recorded trusted original digest when one exists. Do not
   assume Lightroom supplies one or derive an “expected hash” from the candidate.
3. Rank other candidates using date/offset uncertainty, camera/body, dimensions,
   format, name history, companions and folder context. Same date/name/metadata
   alone cannot prove identity. Surface competing candidates and why each matches.
4. Re-read accessible candidates for freshness and integrity; distinguish exact
   known content from a likely original, derivative-only match, offline candidate,
   ambiguous result, or no match in completed scope. Do not substitute a JPEG or
   Smart Preview for a missing RAW. Clock corrections are explicit hypotheses.
5. Propose folder relocation only with per-file mappings and completeness counts.
   One matching filename does not prove an entire folder moved. Handle split
   folders, extra files, unresolved descendants and already-valid references.
6. Present a recovery report with source evidence and the supported Lightroom
   Locate/Find Missing Folder steps. Later owner-reviewed relinking must preserve
   catalog edit associations; do not mass-reimport or report recovery merely
   because a candidate was found. Confirm linkage using fresh supported evidence.

Adobe documents [reconnecting missing photos and folders](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html).
An exact original found only in a protected backup remains protected: propose a
verified working copy at an approved stable location rather than turning the
backup into the working library. No absence result proves destruction everywhere.

## Proposed future extension: Apple Photos import confidence (M8)

This is a read-only proposal after the M3 inventory foundation, not dispatched
implementation or accepted coverage. With the user's permission, compare an
incoming source against explicitly selected Apple Photos libraries and report
four independent observations per asset or bundle:

| Evidence | Report only when |
| --- | --- |
| Record seen in Photos | A qualified, dated read-only observation identifies a record in a selected library. This says nothing by itself about the original bytes or backup. |
| Original bytes independently verified | Accessible original bytes are read and matched to the incoming source by fresh full-content identity, including the required related components and ancillary payload checks. A preview, derivative or matching name/metadata cannot establish this. |
| Original retrieved from iCloud and verified | The user explicitly permits retrieval; the retrieved unmodified original bytes are independently checked against the incoming source, with bundle completeness and retrieval provenance recorded. Cloud presence or a thumbnail alone is unverified. |
| Independent backup verified | A separate copy on independently identified storage is freshly verified under the ordinary full-payload and backup-role rules. A Photos record, iCloud copy, or second view of the same storage is not this evidence. |

Show each observation's source, scope, time, capability and verification status.
Use explicit unknown/unverified states for inaccessible originals, unavailable
cloud content, unsupported access, incomplete Live Photo or sidecar payloads,
stale observations and interrupted checks. Library size, Photos import-success
messages, and matching names, dates or camera metadata do not prove that original
bytes were retained. Optimized storage may leave originals in iCloud; referenced
imports may point to files outside the Photos library. Do not infer an accessible
original from the existence of a Photos record or library package.

Preserve incoming sources and Photos libraries. No automatic import, catalog edit,
original hydration, cloud retrieval, file move or deletion follows a match.
Require explicit user permission for library selection and for any later cloud
retrieval; report the libraries and asset scopes actually inspected, plus excluded,
inaccessible, offline or unselected libraries. A match or absence in one library
does not answer for every library on a machine or account. A mere Photos match
never grants deletion authority; any future cleanup remains under its separate
reviewed keeper, payload, backup and action-time safety gates.

The supported read-only observation/export method and available original-byte
access must be qualified per macOS/Photos version before implementation. Current
Apple capability research is preliminary; version-specific API behavior, managed
versus referenced import coverage, cloud retrieval semantics and multi-library
coverage remain unverified. Keep these gaps visible rather than claiming an
adapter or test acceptance. Proposed synthetic cases should distinguish all four
evidence fields and the unknown states without using personal Photos libraries.

## Mac and Windows delivery

Mac and Windows are product targets. Keep scanning, matching, planning and job
policy in shared services; put native dialogs, notifications, filesystem events,
timestamp access and publication primitives behind platform adapters. Choose the
GUI framework after a small two-platform prototype; SwiftUI alone does not cover
the Windows target. No framework or helper is selected or installed by this plan.

Qualify each platform's permissions, long/reserved paths, separators, case/Unicode
behavior, removable-drive identities, timestamps, locking, no-overwrite publication
and crash recovery. Windows reparse points and Mac aliases/symlinks need explicit
traversal rules. Cross-platform destination conflicts must be caught before copies.
The current Mac fixture results are not Windows test evidence.

## Additional synthetic acceptance cases — not built yet

| Seed/scenario | Expected result |
| --- | --- |
| App closed; new folder with old preserved timestamps | Next complete scan finds it despite backdated mtime. |
| Existing file replaced at the same path; sidecar added later | Previous identity is invalidated; new content/companion is reviewed. |
| Missed events, interrupted scan, helper disabled | Reconciliation catches retained changes; gap/completion state stays honest. |
| Copy still growing, partial rename, equal-size rewrite | No premature stable-hash, complete-import or backup claim. |
| Forgotten dump outside enrolled roots | No false discovery promise; broader selected scan finds it. |
| Drive unplug/reconnect with different letter/name | Keep history; reidentify or show ambiguity, never infer deletion from unplugging. |
| Old snapshot after new snapshot; reset clock | Old evidence cannot overwrite newer source revisions. |
| Same share on two machines; cloned volume metadata | Do not count aliases as independent backups or collapse actual clones. |
| Missing catalog path; renamed exact original elsewhere | Use known digest when available and report a verified candidate with provenance. |
| Same name/date from another camera; resized JPEG only | Ambiguous/derivative result; no false RAW recovery. |
| Missing folder split across drives; one member unresolved | Per-file mapping and partial status, no blanket folder-complete claim. |
| Multiple catalogs/virtual copies; stale catalog snapshot | Preserve reference identity and age; do not fabricate current linkage. |
| Mac/Windows case, Unicode, reserved-name and path conflicts | Preserve original spelling and report unsafe destination mappings. |

Use small generated media and literal expected observations; model multiple hosts,
restarts and event gaps without touching real devices. Start matching tests from a
normalized synthetic catalog-reference contract. Such tests do not qualify an
actual Lightroom reader: that needs separately constructed synthetic-photo
catalogs or supported exports for each declared version, with no personal catalog
access. OS event and filesystem claims require native Mac and Windows checks.

Build after M2 safety and the M3 inventory foundation: local discovery first,
snapshot exchange second, qualified Classic recovery reports next. A thin GUI can
expose each service as it is ready. Helper installation, actual networking and
catalog adapters receive separate bounded implementation/acceptance work; no such
work has been dispatched here. Existing 177-file M1 acceptance remains unchanged.
