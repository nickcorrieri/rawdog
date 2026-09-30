# RAWdog library improvement plan

Owner direction: 2026-09-28. Start with small, known synthetic files and explicit
expected results. Develop against those files, never the owner's photo library.
The owner activated BRAIN mode on 2026-09-28. The parent owns product decisions,
the plan, bounded assignments and acceptance. Codex/GPT builders execute the work;
Sol remains available for independent review. Coordination is entirely Codex/GPT:
no Claude dispatch, relay watchers or external-agent message bridges.

## Product outcome

RAWdog should answer where a file and its related versions live, whether a new
folder is already represented in the library, which copies are intentional
backups, whether dates and placement are justified, and which exact copies can
be reversibly quarantined. Mac and Windows interfaces expose the same operations.
The owner also wants discovery of forgotten card dumps and Lightroom education
and missing-original recovery. See the [discovery and Lightroom specification](LIBRARY_DISCOVERY_AND_LIGHTROOM.md)
for cross-machine inventory, background/startup discovery and acceptance cases.

The initial product does not require a photo editor, facial recognition, cloud
sync engine, or mutation of Lightroom/Photos catalogs. Filesystem timestamp
repair, embedded metadata changes, date correction, organization, and duplicate
cleanup are distinct reviewed operations.

### Reconciliation with the parallel Fido audit

The owner supplied [the other chat's audit and proposed plan](research/2026-09-28-rawdog-library/rawdog-fido-audit-plan.md),
dated 2026-09-28 against the same baseline commit. Its conclusions corroborate
this plan: keep SQLite, strengthen identity and verification, preserve intentional
backups, and share safe services between the CLI and GUI. Its additional safety
findings are included in M2 below. This document remains the consolidated roadmap.

**Recommended first release:** safety repairs → read-only inventory and exact-copy
collision report → reviewed, verified copies into month folders → a thin GUI
targeting Mac and Windows.
M1's accepted synthetic corpus remains the first completed development milestone.
Date/metadata repair, visual relationship inference and reversible pre-trash
cleanup remain requirements for later releases; they are not prerequisites for
useful inventory. Copy-only here means sources and embedded metadata remain
unchanged; catalog date interpretation and proposed destination names are separate.

This release selection is a recommendation, not a newly dispatched build.
“Fido” is the other report's proposed name; RAWDOG branding remains unchanged.
Lightroom education and recovery are now owner-requested product scope; enabling
an adapter still requires confirming the edition/version and selected catalogs.
Neither pasted recommendations nor fixture acceptance authorize real-library work.

## Standing development boundary

- Agents may edit owned source/docs/test paths and generate disposable synthetic
  files. No production photo/video files, real mounted libraries, existing RAWdog
  databases/configuration, or editor libraries are development inputs.
- No dependency installation, downloading photographs, release or publication is
  included in this authorization. Use already installed tools; missing tools
  produce explicit skips or blockers, never an automatic installation.
- Fixture generators allocate fresh OS temporary directories, never clear an
  existing directory, and never accept a user-library input path. Generated
  manifests identify their contents as synthetic.
- Test commands must use temporary configuration, database, library and report
  paths. An OS-enforced worker filesystem boundary is required before unattended
  execution of newly written media-mutating commands. Repository instructions
  and a sentinel alone are not a filesystem sandbox.
- Separate accepted behavior, unimplemented requirements, skipped coverage and
  failed checks. A passing fixture test is not proof of a full camera decoder,
  backup policy, repair workflow, or physical-drive reliability.

## Milestone 1: known seed corpus and result oracle

Build files first; make tests and product work consume their known properties.
Use deterministic, small geometric images and compact metadata containers.
Do not multiply every condition by every format: repeat the fundamental date and
identity cases across primary families, and use representative formats for
orthogonal filesystem, bundle, encoding and failure cases.

| Seed set | Owner | Deliverable and acceptance |
| --- | --- | --- |
| Timestamp and exact identity | Parent initial build, Sol review | 138 files in six extensions, approximately 95 KB; real embedded-date reads, seeded filesystem times, exact duplicate groups, same-name/same-size distinct bytes, positive/negative bulk clock deltas and controls. |
| Patterned JPEG relationships | `photo_conditions` builder | Known original and metadata-only, recompressed, downscaled, upscaled, cropped, oriented and unrelated variants. Saved relation oracle; valid decoded pixels and measured dimensions. |
| Companions and storage conditions | `astra_review` builder | RAW/JPEG/XMP relationships, divergent sidecars, filename/case/Unicode collisions, malformed files, interrupted artifacts, protected backup and logical offline observations. |
| Integrated ratification | `sol_review` | Verify manifests independently of RAWdog outputs, check claims and gaps, run relevant tests and report acceptance or bounded findings. |

Each manifest records a stable case ID; relative path; format and capability
tier; known byte identity and size; actual encoded dimensions where applicable;
capture tag text/offset/subseconds; filesystem timestamps; source/camera context;
copy role/protection; expected relationships; expected decisions; and coverage
limitations. The expected result must not be calculated by the same production
function under test. Record an explicit unknown when truth is not supplied.

The initial timestamp corpus covers credible/missing/suspicious dates, owner
confirmation, EXIF versus filesystem disagreement, `+8h`/`-8h`, `+12d2h`/`-12d2h`
across months, a camera fixed afterward, another camera that must remain untouched,
timezone uncertainty, DST fallback, and four exact copies with different disk
dates. See [the timestamp corpus specification](SYNTHETIC_PHOTO_CORPUS.md).

JPEG relation seeds must include the owner's explicit case: **same photo, same
filename, same capture metadata, smaller dimensions and/or recompressed bytes**.
Label this a generic exported/social-service derivative. Synthetic transforms
do not reproduce or certify Google's or Instagram's actual current pipeline.

RAW metadata-container seeds must remain labeled as such. They can verify real
metadata extraction, inventory, hashing and planning. They cannot qualify camera
compression, rendering, proprietary maker-note preservation or embedded rewriting.

M1 is complete only when the integrated ledger states exactly which cases are
seeded and tested, which are modeled observations, and which remain pending.
Unbuilt cases below are later acceptance obligations, not implicit M1 successes.

### M1 integrated result — 2026-09-28

**Accepted by Sol for the bounded fixture/requirements milestone.** No substantive
blockers remained after independent inspection and regeneration of all three sets.

| Reproducible seed recipe | Files | Media bytes | Focused checks |
| --- | ---: | ---: | ---: |
| [Timestamp/identity generator](../tests/photo_corpus.py) / [specification](SYNTHETIC_PHOTO_CORPUS.md) | 138 | 94,957 | 21 |
| [Patterned JPEG generator](../tests/photo_variants.py) / [specification](JPEG_VARIANT_CORPUS.md) | 13 | 26,999 | 8 |
| [Companion/storage generator](../tests/photo_companions.py) / [specification](PHOTO_COMPANION_CORPUS.md) | 26 | 15,546 | 8 |
| Total | 177 | 137,502 | 37 |

The parent ran the integrated repository suite: **238 passed in 13.65 seconds**;
repository-wide Ruff passed. Sol independently ran the 37 corpus checks with
**37 passed, no skips**, regenerated the totals, checked JPEG dimensions through
ExifTool, and checked names/bytes/mtime/birthtime around read-only inspection.
Companion inspection included 19 files and explicitly excluded seven XMP,
AppleDouble and partial artifacts; it created no source `.rawdog` directory.

The smaller patterned JPEG is 32×24 / 1,156 bytes versus its 64×48 / 2,436-byte
reference, with the same filename/capture metadata subset. A 128×96 upscale is
also explicitly a derivative. This is known synthetic lineage, not an implemented
visual matcher. The original timestamp JPEGs reuse simple solid-color pixels and
must not be used as unrelated-image controls for similarity acceptance.

Actual fixture capabilities: real JPEG decoding, real embedded metadata reading,
seeded macOS birth/modified times, hashing, inventory and existing delta planning.
Logical observations only: offline locations, protection roles and planned path
conflicts. Still unimplemented: new repair, similarity, bundle detection, backup
protection, quarantine and restore behavior. Compressed vendor RAW decoding and
real-drive failure recovery remain unqualified. No product source changed.

Handoff state: BRAIN mode is active. This commit captures the plan, research,
documentation and fixture/test additions against the unchanged product baseline
below. `sol_review` remains available for independent review. The separately
requested Sol orchestrator starts with read-only M2 planning and readiness only;
M2 repair implementation has not been dispatched. Continue from this ledger and
the M2 regression obligations; fixture acceptance does not clear production media
work. Historical audits and their original provenance are retained in the
[research archive](research/2026-09-28-rawdog-library/README.md).

## Format support is a set of capabilities

Every file needs separate recognition, inventory, exact-hash, metadata-read,
preview/decode and approved-write outcomes. Unsupported preview does not make
the original expendable. Detect extension/signature disagreement and record it;
do not treat an extension allowlist as validation of the file's integrity.

Current code recognizes 23 RAW extensions, JPG/JPEG, and 14 camera-video
extensions. It reads a limited capture-date/ImageUniqueID subset through optional
ExifTool. This is narrower than the proposed catalog below.

| Family | Planned support and conditions |
| --- | --- |
| Canon CR2/CR3 | Primary metadata/preservation families. Qualify CR3 RAW/C-RAW, Dual Pixel and RAW Burst separately before decoder/write claims. |
| Sony ARW; Nikon NEF/NRW | Primary metadata/preservation families. Compressed/lossless/uncompressed/reduced-size/high-efficiency recording modes need individual capability evidence. |
| DNG | Primary preservation/metadata. Distinguish camera, converted, linear/ProRAW, lossy and newer compression variants. Never silently convert proprietary RAW to DNG. |
| JPG/JPEG; proposed JPE/JFIF aliases | Primary JPEG family. Baseline/progressive RGB and grayscale first; qualify CMYK/YCCK, unusual subsampling, extended XMP/ICC, HDR gain maps and multi-image forms separately. |
| Existing other RAW: RAF/RW2/ORF/PEF/etc. | Retain existing byte-preservation scope. Qualify metadata/preview by actual family/model rather than promising universal decoding. Legacy CRW and other currently absent variants require explicit recognition work. |
| XMP sidecars | Discover and preserve relationships early. Keep unknown namespaces, provenance and divergent versions. Same basename alone is insufficient for binding. |
| HEIC/HEIF/HIF | Next intake addition for Mac/iPhone libraries. Probe runtime decoding; preserve auxiliary images, depth/gain maps and multi-image relationships. No automatic JPEG conversion. |
| TIFF/TIF and PNG | Next intake addition for edited masters, scans and screenshots. Distinguish multipage/high-bit-depth/alpha/unusual compression; missing capture metadata is a valid state. |
| Current camera videos | Retain current byte-preservation scope. Metadata and playback depend on both container and codec. Preserve split/spanned clips and sidecars. No transcoding or embedded timestamp writing initially. |
| AAE/vendor edits/XML/THM and other companions | Opaque preservation and explicit bundle relations before edit interpretation. A thumbnail is not automatically trash. |
| WebP/AVIF | Later opt-in intake if useful for actual libraries. Qualify animation, HDR, auxiliary images and decoder availability separately. |
| JPEG 2000/JPEG XL/MPO and specialized formats | Deferred interpretation. Explicit opaque preservation may be offered without a full-support claim. |

Raw byte originals remain preserved by default. Initial embedded-write work is
JPEG on a retained-original/new-version workflow. RAW corrections begin in the
catalog or appropriately supported sidecar; writing into vendor RAW requires
separate qualification. A catalog correction must not masquerade as an embedded
change visible to other software.

ExifTool's [format list](https://github.com/exiftool/exiftool/blob/master/README)
describes metadata capabilities, not RAWdog decoder or rewrite safety. JPEG
metadata can span [EXIF, XMP, ICC and other segments](https://exiftool.org/TagNames/JPEG.html).
Adobe's [metadata storage behavior](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html)
differs between proprietary RAW sidecars and embedded JPEG/TIFF/DNG metadata.

## File-condition coverage ledger

The seed-set documents and manifests supply exact built-case evidence. This is
the required backlog of conditions to cover before enabling the corresponding
feature; it is not a claim that every entry is already generated.

| Area | Conditions and required outcome |
| --- | --- |
| Names and paths | Camera rollover/reset; same name across bodies/shoots; renamed exact copies; case-only names/extensions; composed/decomposed Unicode; long names/deep paths; punctuation; destination collisions. Preserve separate identity and show full paths. |
| Dates | No capture tags; file dates copied/reset by import; epoch/future/impossible dates; embedded tag disagreement; modified creation dates; missing offsets/subseconds; timezone travel; DST invalid/ambiguous wall times; wrong camera clock; gradual drift; fixed-camera cutoff; missing camera serial; date-boundary crossing. Preserve observations and uncertainty. |
| Metadata | EXIF-only, XMP-only and conflicting EXIF/XMP/IPTC; orientation; ICC/color/HDR; GPS/privacy-stripped variants; stale dimensions; unknown maker notes; metadata-only edits; sidecar conflict. Do not silently discard one version. |
| Image versions | Exact bytes; equal pixels with different metadata; resized/downsampled; recompressed; upscaled; crop; rotation tag versus rotated pixels; mirrors; color edits; watermarks; screenshots; messaging/social exports; close burst frames; unrelated lookalikes. Separate identity from relationship. |
| Representations and bundles | RAW+JPEG; RAW+XMP; JPEG+XMP; Live Photo still/video; bursts; multi-image containers; scans; exported edits; missing/ambiguous/spanned members. Keep each component and distinguish complete from partial representation. |
| Integrity | Zero-byte/truncated files; extension/signature mismatch; readable metadata with corrupt pixels; malformed/oversized metadata; failed checksums; unreadable/encrypted files; invalid sidecars. Report capability failures without deleting evidence. |
| Copy intent | Working copy, primary archive, intentional backup, disposable download/export, quarantine; same device versus independent device; hardlinks/symlinks/aliases; cloned store metadata; duplicate imports. Do not infer redundancy intent from hashes. |
| Filesystem state | Unmounted/offline drive; changed mount name; stale catalogs; read-only volumes; permission failure; free-space exhaustion; FAT/exFAT/APFS precision and case differences; removable-media interruption; cloud placeholder; package directories; AppleDouble/resource forks; partial files. Do not count an unscanned file as absent. |
| Concurrency and recovery | Change during scan/hash/preview; source/keeper replaced; keeper disappearing; two writers; crash around publish/quarantine/DB update; repeated correction; interrupted/resumed plan; occupied restore path. Revalidate and recover without overwrite. |

The SHA-256 content identity covers the file's primary data stream. A complete
archival payload may also include resource forks, relevant extended attributes
and separately identified companions. Equal primary-stream hashes do not prove
that these are equal or safely retained elsewhere. A cleanup/backup-completeness
decision must account for unique ancillary content. Filesystem timestamps are
separate observations: preserve their pre-operation values without confusing
different copy dates with different photo bytes.

Managed Photos/Lightroom library packages are not ordinary mutable source trees.
Live Photo exports contain a still and video; preserve both as related components.
See [Apple's export documentation](https://support.apple.com/en-au/guide/photos/-pht6e157c5f/mac).

## “Do you already have this in your photo library?” plans

Comparison is a read-only operation with explicit incoming scope, comparison
stores/snapshot, exclusions and capabilities. It can search last-known offline
catalogs, but must distinguish historical evidence from a live verified copy.
Scan databases, reports and decoder/signature caches use explicit output roots
outside the scanned sources; development uses temporary roots. A scan must not
initialize a portable catalog or write `.rawdog` metadata into a source library.
Read-only tests assert unchanged data, birth/modified times, names and relevant
attributes; OS-managed access-time effects are not presented as metadata repair.

1. Inventory incoming files and chosen library scope, with scan IDs and counts.
   Identify packages, placeholders, inaccessible paths and unsupported types.
2. Match fresh full SHA-256 identities. Names, sizes, dates, camera IDs and partial
   fingerprints only narrow candidates; they do not prove equality.
3. Retrieve non-identical candidates using capture/bundle context and, when
   supported, recorded image signatures. Compare decoded pixels or similarity
   under a versioned orientation/color policy. No installed decoder means unknown
   visual relationship, not no match.
4. Produce a per-file report linking every known matching location, provenance,
   dimensions, format, byte size, metadata differences, backup roles and the age
   of verification. Keep the comparison result separate from any action plan.

Basic inventory accounts for every regular file within the selected scope,
including opaque or unsupported formats; parsing/preview support is separate.
Classify `.partial` artifacts, `.rawdog` catalogs and opaque companions explicitly;
being inventoried does not make a file an image or an organization candidate.
Record symlinks and package boundaries without silently traversing them. Persist
scan completion, exclusions and errors. Retain occurrence history on incomplete
scans or unavailable drives, and avoid counting the same occurrence twice when
roots overlap. An absent occurrence requires a completed scan of its scope;
an offline location is not evidence of deletion. Do not invent historical import
events from a file merely being present today.

Signature evidence records dimensions, orientation transform, color/profile
handling, bit depth/alpha where applicable, decoder/backend version and policy
version. Identity, visual relationship, freshness and bundle completeness are
independent fields; the display label must not hide conflicting or partial evidence.

| Result | Meaning and permitted consequence |
| --- | --- |
| Exact copy present, live verified | Same primary data-stream bytes at an identified location; quarantine eligibility additionally requires ancillary-content preservation and a separate protected-keeper check. |
| Exact copy recorded, offline/stale | Historical catalog evidence; retained copy is not currently verified. No cleanup approval. |
| Same decoded pixels | Equal pixels under the recorded decoder/orientation/color policy; bytes/metadata can differ. Keep both by default. |
| Likely derivative | Recompressed/resized/cropped/edited or otherwise related visual candidate. Review only. |
| Possible match | Ambiguous visual/context evidence. No cleanup. |
| Not found in completed scope | No qualifying match in successfully scanned scope. Does not mean absent from offline, unreadable or unselected stores. |
| Unknown/incomplete | Unsupported decoder, unreadable/corrupt file, offline-only scope, placeholder or interrupted scan prevents an answer. |

For the Google/Instagram-style JPEG example, identical name/capture metadata plus
reduced resolution is useful evidence, not proof. A full-resolution original
already in the library should be surfaced beside the smaller candidate. If only
the smaller derivative is present, an incoming original must still be preserved.
Larger size/resolution is not proof of originality; an upscale can be larger.

Use separately reviewed scan/plan modes for: card or folder before import;
recovered drive against all known stores; downloads/exports against originals;
backup coverage audit; and consolidation of multiple sources. Resume must not
present stale earlier observations as fresh checks. Scanning never repairs dates,
renames/moves files, hydrates cloud originals or changes editor catalogs silently.

Folder summaries roll up exact, related, new-in-completed-scope and unknown counts
while preserving per-file evidence. Bundle summaries report complete, partial,
ambiguous or unknown coverage. An existing JPEG does not cover an incoming RAW;
an existing RAW without its unique XMP edits does not cover the complete incoming
bundle. Keep file counts separate from inferred capture counts, and disclose
excluded/unreadable members rather than marking the entire folder already stored.

## Timestamp and placement contract

Store original tag group/text, wall time, timezone certainty, subseconds,
filesystem birth/modified times, evidence source and approved interpretation.
Plausible dates are candidates. Missing EXIF does not make a filesystem date
false, and present EXIF does not make a wrong camera clock correct.

An owner correction specifies signed delta, exact selected files/range, camera
body where available, cutoff when the camera was fixed, and a stable operation
ID. Preview before/after timestamps and affected destinations. Clock correction
and timezone reinterpretation are distinct. Missing body IDs require explicit
selection. Repeated/resumed execution must not apply the delta twice.

When a job includes repair, the required order is: establish accepted shot time
→ preview repair → apply approved
format-specific metadata/filesystem changes → verify results and pre/post byte
identity → regenerate the organization plan. Filesystem-only timestamp repair
must preserve byte hashes. Metadata insertion changes hashes and requires
version lineage; it does not create a new underlying capture.
Copy-only placement can use an accepted catalog date without rewriting the
source's embedded or filesystem timestamps; unresolved dates stay in review.

Before implementing new write commands, reconcile older absolute safety wording
in the existing project documents with these specifically bounded operations:

| Operation | Authorized future behavior and continuing protection |
| --- | --- |
| Comparison scan | No source writes, portable-catalog initialization or automatic repairs. |
| Filesystem timestamp repair | A reviewed plan may change selected creation/modified times to an accepted shot instant; retain previous values and prove the primary byte hash is unchanged. |
| Embedded metadata repair | Start with qualified JPEG writing into a new retained-original version; preserve unique metadata and record pre/post identity. No blanket in-place vendor RAW rewriting. |
| Organization | Explicit reviewed placement plan with no overwrite, saved original location and recovery state; ordinary ingest/archive operations do not silently reorganize existing originals. |
| Duplicate quarantine | Separate reviewed operation on explicitly disposable copies after complete keeper/payload checks. Archive and intentional-backup roles remain protected by default. |

These are product requirements; development authorization remains synthetic-only.
Do not remove append-only/archive protections globally to implement one new
command. Reconcile the policy documents and command-specific guards together.

Final audits separately report byte identity, desired path under the selected
layout/naming policy, metadata/clock confidence, bundle completeness, catalog
consistency and protected-backup coverage. Every failed required check blocks
successful completion. A syntactically tidy directory is not proof of correct
capture-date or project placement.

## Subsequent implementation order

Baseline code review target: `1f1e2d02055a987c4dd7eef2ef02a74779b15731`.
Our original 201-test suite passed, but synthetic adversarial probes reproduced
the following defects. M1 creates fixtures; it does not repair these behaviors.

The parallel audit recorded **200 passed, one preview-display failure** with a
long temporary path, followed by a passing short-path isolated recheck. Our later
238-pass integrated run does not erase that path-sensitive failure. Retain it as
a distinct preview regression to investigate when that area changes. Imported
probe results below come from the saved [independent evidence](research/2026-09-28-rawdog-library/rawdog-independent-audit-evidence.json);
their lock, symlink and skip code paths were also checked statically here. These
probes were not rerun during document reconciliation.

| M2 regression obligation | Baseline evidence |
| --- | --- |
| Never lose every retained copy | Astra's generated overlapping-source report selected two archive files as each other's keeper and removed both. Sol separately reproduced cleanup of a registered den used as source. |
| Atomic no-overwrite | Astra and Sol inserted a destination during copying; final `os.rename` replaced it. A preflight existence check is insufficient. |
| Fresh cleanup identity | Sol changed a source during confirmation and observed deletion without revalidation. |
| Exclusive execution | Parallel audit `RUNLOCK_RACE`: two synchronized acquisitions both succeeded. `runlock.py:97` reads a marker then replaces it, without exclusive acquisition. Test competing processes and separate app databases targeting the same store. |
| Symlink and scope containment | Parallel audit `SYMLINK_FORCE_DELETE`: cleanup deleted a symlink target outside the yard. `cli.py:8963` resolves paths before the symlink rejection at `cli.py:9005`. Check original path components, aliases and source/keeper containment at action time. |
| Fresh skip and source evidence | Parallel audit `STALE_SKIP`: destination removed after planning, yet completion was `done` with zero review. `CHANGED_MOVE`: a changed source was moved before its size mismatch was reported. Bind plans to reviewed file versions; revalidate skips and sources before acting. |
| Truthful audit outcome | Astra and Sol reproduced `size_mismatch` while the plan completed `done` with zero review items. |
| Exact identity for existing-file decisions | Same-name/same-size distinct bytes can be skipped; neither filename nor size proves stored content. |
| Hash-cache validity | Parent and Sol changed a file then quick-cataloged it; the obsolete hash and full-catalog status remained. |
| Separate backup identity | Parent registered a copied portable store identity while both roots existed; the backup root replaced the original registration. Astra independently identified the same path in code. |

Relevant implementation areas are the copy/move primitives, exclusive execution,
cleanup eligibility and mutation steps, execution audit aggregation, store
registration and catalog upserts. Repairs must cover existing CLI entry points as
well as future GUI services. Unique exclusively owned partial files and durable
no-replace publication belong to the same copy contract. Regression tests must
exercise these behaviors directly; broad suite green alone does not discharge
an obligation. No legacy command has been disabled by this documentation change.

| Milestone | Scope and exit gate |
| --- | --- |
| M1: fixtures | Three seed sets and independent oracles; fresh-directory-only generation; honest capability/gap ledger; Sol ratification. |
| M2: safety and audit truth | Exclusive execution, atomic no-replace publish, protected archive/keeper and path-containment checks, action-time identity validation including skips, stale hash invalidation, explicit failing audit outcomes. Reproduce audited failures against seeds and prove repairs. |
| M3: index and exact comparison | Evolve SQLite into content identities + copy locations + machine/store/device/protection observations; clone/relocation distinction; offline history; resumable read-only “already have it?” exact scan. Follow with startup/reconnect discovery and versioned cross-machine snapshot exchange under the discovery specification. |
| M4: date and placement planning | Provenance/uncertainty, owner-scoped deltas, independent expected-location report, then qualified filesystem timestamp and JPEG metadata repair on disposable test copies. Invalid spring-forward times, repeated-operation idempotence and partial-failure recovery fixtures must pass before writes are enabled. |
| M5: image relationships | Read-only equal-pixel and derivative candidates with decoder/capability provenance, false-positive controls and representative performance measurements. No perceptual cleanup rule. |
| M6: reversible cleanup | Same-filesystem quarantine, durable intent/state, protected keeper outside all action candidates, restore without overwrite, separate purge, complete bundle handling and crash recovery. Quarantine does not reclaim space until purge. |
| M7: Mac and Windows interface | Shared service layer behind CLI and both desktop platforms; framework selection remains open. Initial views: Locations, Inventory, Review and Copy Jobs; Review includes discovered folders and qualified Lightroom recovery reports. Later expose Quarantine and broader Activity. Native previews where qualified; no terminal-output parsing. |
| M8: proposed Apple Photos import confidence | After the M3 inventory foundation, add a read-only, permission-scoped report for selected Apple Photos libraries. Keep a Photos record, independently verified original bytes, an iCloud-retrieved and verified original, and an independently verified backup as separate evidence. Report unknown and unverified states and library coverage limits. This extension does not authorize deletion or change M2 cleanup acceptance, M3/M4 work, Lightroom recovery, or M7 GUI sequencing. See the [proposed Photos extension](LIBRARY_DISCOVERY_AND_LIGHTROOM.md#proposed-future-extension-apple-photos-import-confidence-m8). |

There is no need to replace SQLite or build a server. Reuse the existing plans,
manifests, stores, metadata reader and hashing where their contracts are correct.
Extract services from the large CLI as each milestone needs them rather than
rewriting it wholesale. Preserve current supported byte intake during migration.

### Proposed first-release scope within these milestones

The milestone numbers above retain the full feature backlog. The recommended
release draws from M2, M3, the read-only placement portion of M4, and a small M7
interface before shipping M4 writes, M5 inference or M6 cleanup. This proposed
ordering avoids making the GUI wait for every library-management feature.

- Inventory: content, occurrence, store/device/protection, scan and operation
  history in SQLite; exact-copy lookup, collisions, uncertainty and offline history.
- Copy plan: month destinations from accepted dates, an explicit unresolved-date
  review route, original-path → destination ledger, complete companion mapping
  and additional-space estimate. A readable date/original-name/digest scheme is
  a candidate naming policy; persist selected names and handle token collisions
  using full identity. Reconcile the existing naming policy before implementation.
- Execution: preserve sources and file bytes, verify each destination, handle
  interruption and retries without overwrite or duplicate work, and leave no
  automatic cleanup after copying. Preserve ancillary payloads and unique sidecars.
- Interface: Locations, Inventory, Review and Copy Jobs over the same tested
  services. Show original names/full paths, copy roles, date confidence, verification
  freshness, progress and resumable failures. No framework installation is implied.

### Lightroom and camera workflow

Lightroom education and finding missing originals/folders are owner-requested
scope. The [focused specification](LIBRARY_DISCOVERY_AND_LIGHTROOM.md) defines the
user explanation, catalog adapter boundary, recovery evidence and new fixture gaps.
Confirm Lightroom edition/version before implementing its adapter; camera model
is needed only for camera-specific guidance, not as a blocker to general inventory.
For Classic, unavailable drives and external file moves/renames can break catalog
references; its supported Locate/Find Missing Folder workflow can reconnect them.
See [Adobe's missing-photo guidance](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html).
A future reconciliation report should distinguish offline originals, exact matches
and uncertain candidates before any proposed reimport. Any reader uses a safe
catalog snapshot or supported export qualified for that version; no live-catalog
writes or automatic reimport are part of this plan.

Keep observed file, verified original, independent verified backup, Lightroom
association and delivered export as separate evidence. A renamed JPEG export
cannot establish that its RAW original was lost or recovered. Camera counters,
gaps and resets are diagnostic observations only; they cannot establish total
captures, completed imports or loss. No camera settings or real catalogs were
inspected in either audit.

## Orchestration and review

The BRAIN assigns bounded files and acceptance cases to Codex/GPT builders.
Builders generate only fresh fixture worlds, implement scoped changes, perform
integration and the appropriate targeted/shared checks, and report changed paths
plus exact evidence to the BRAIN. Sol reviews independently against the oracle.
The BRAIN resolves product decisions and conflicting findings, accepts or returns
work, maintains the plan/ledger, and dispatches authorized tasks. Routine execution
and review exchanges stay within this team; the owner receives decisions, material
blockers and milestone results. No user message relay is required.

Routine fixes repeat without owner intervention. Escalate missing product intent,
new dependencies or an actual change to the authorized boundary. Record final
review against the actual integrated code state, not an earlier builder version.
Do not claim an independent review of a parent's later unreviewed edit.

### Active BRAIN handoff

- Supervisor: `/root`, BRAIN chat `01a0e9a1-1cd0-7273-b140-15bc68bc537d`;
  owns decisions, planning, delegation and acceptance.
- Independent reviewer: `/root/sol_review`; retain its context for later review.
- Separate chat requested: `SOL Orchestrator: Rawdog`, GPT-6 Sol/high, local
  checkout. This operational role reports to BRAIN and remains distinct from
  `sol_review`. Its initial assignment is read-only M2 planning/readiness: consume
  this committed handoff, summarize readiness and propose bounded assignments.
  Creating that chat does not authorize a repair build or new packet file.
- Available builders: `/root/astra_review` and `/root/photo_conditions`; historical
  role names do not grant simultaneous ownership of the same source files.
- Accepted baseline: M1, 177 synthetic files and 37 focused checks; historical
  integrated run 238 passed. Expanded discovery/Lightroom cases remain unbuilt.
- Captured in this commit: plan/docs, six fixture/test modules and the historical
  research/evidence archive;
  product code remains at `1f1e2d02055a987c4dd7eef2ef02a74779b15731`.
- Next bounded assignment when implementation is dispatched: M2 safety regression
  packet and worker-boundary verification, then scoped repairs with independent
  review. Promotion alone does not start that build.
- Boundaries: synthetic-only development; no installations or real-library work;
  no Claude coordination, relay watchers or bridges. Role changes do not create
  background automations or expand operating permission.

## Estimates and acceptance limits

The earlier 8–14 engineer-week range covered a focused catalog, safety repairs,
quarantine/audits and packaged Mac UI. Windows qualification, cross-machine
discovery, Lightroom adapters, broader formats and visual derivative matching add
scope; the earlier range does not cover this expanded product. Estimate each
milestone after its corpus and capability contract are ratified. A reliable
read-only exact-copy index can be delivered before the broader visual/repair UI.

Synthetic tests do not prove physical-drive failure recovery, all camera models,
all decoder builds or every social-service export. Report those gaps explicitly.
macOS capability should be probed through actual decode results and supported
[ImageIO source types](https://developer.apple.com/documentation/imageio/cgimagesourcecopytypeidentifiers%28%29?language=objc),
recording backend/OS versions rather than asserting universal format support.
