# Milestone 1: small synthetic photo corpus

The first milestone is seeded files and independently stated expected results.
Repair features follow this corpus. No user media, mounted photo library, existing
RAWdog database, or downloaded photograph is used.

The generator creates **138 files, approximately 95 KB of media total**, with
an expected-results manifest and RAWdog's read-only observations. Every JPEG is
8 by 8 pixels. The six extensions are `.jpg`, `.jpeg`, Canon `.CR2` and `.CR3`,
Nikon `.NEF`, and Sony `.ARW`.

Run from the checkout:

```sh
.venv/bin/python tests/photo_corpus.py
.venv/bin/python -m pytest tests/test_photo_corpus.py
```

The generator always allocates a fresh OS temporary directory and accepts no
user-library or destination arguments. It never cleans an existing directory.
The only media it changes are bytes it just generated. It writes `expected.json`
and `observed.json` beside a `media` subdirectory. Generated binary files stay out
of Git; the small deterministic recipe and literal expectations are versioned.

No packages are installed. Generation uses the Python standard library. Tests
use an already installed ExifTool for actual metadata extraction and macOS `sips`
for JPEG pixel decoding. Those integration checks explicitly skip when the
corresponding existing tool is unavailable; they must not be reported as passed.

## Seeded cases

Each of these 23 cases is emitted in all six extensions:

| Case | Seed and expected future decision |
| --- | --- |
| No capture metadata, plausible filesystem dates | Retain a dated candidate with filesystem provenance; plausibility alone does not authorize embedding a claimed shot time. |
| No capture metadata, owner confirms filesystem date | Propose capture metadata using that date and the confirmed timezone. |
| No capture metadata, epoch date | Flag uncertainty; do not invent a shot time. |
| No capture metadata, future date | Flag uncertainty against a fixed reference date. |
| Filesystem created/modified dates disagree | Keep both observations; request evidence before deciding which describes the shot. |
| Approved embedded shot time, wrong filesystem dates | Propose setting filesystem creation and modification times to the shot instant; embedded metadata remains unchanged. |
| Suspicious embedded date, plausible filesystem dates | Flag disagreement; EXIF is not automatically correct. |
| Camera slow by eight hours | Apply explicit owner delta `+8h`. |
| Camera fast by eight hours | Apply explicit owner delta `-8h`. |
| Camera slow by twelve days and two hours, May | Apply explicit owner delta `+12d2h`. |
| Same camera error, July | Apply the same correction months later within the selected scope. |
| Camera fast by twelve days and two hours | Apply explicit owner delta `-12d2h`. |
| Camera fixed in August | Control: leave its correct timestamp alone. |
| Different camera body | Control: leave it outside the selected correction scope. |
| Shot time without timezone | Preserve local wall time; do not silently claim an absolute instant or repair filesystem dates. |
| First 01:30 during DST fallback | Explicit `-04:00` identifies one instant. |
| Second 01:30 during DST fallback | Explicit `-05:00` identifies a different instant. |
| Exact duplicate in working folder 1 | Same content hash despite different filesystem dates; eligible for review only. |
| Exact duplicate in working folder 2 | Same bytes, another folder and another set of filesystem dates. |
| Exact duplicate in primary archive | Protected retained copy. |
| Exact duplicate in intentional backup | Protected backup, not unwanted duplication. |
| Reused camera filename, first content | Same filename and size as the next file, different bytes; retain independently. |
| Reused camera filename, second content | Distinct content; JPEG variants also have different decoded pixel colours. |

All paths intentionally reuse `IMG_0001` so tests cannot accidentally rely on
camera basenames as unique identifiers. There are six exact-copy groups, each
with four files, one group per extension. RAW and JPEG representations are never
collapsed into an exact-byte duplicate group.

## What is physically seeded

- Real bytes and full SHA-256 values, repeatable across runs.
- Real filesystem modification timestamps and, on macOS, real filesystem birth
  timestamps. `ctime` is not creation time. Other systems explicitly mark birth
  time as unseeded rather than claiming to have changed it.
- Real EXIF capture tags, subseconds, explicit offsets, body identifiers, and
  image identifiers where the case calls for embedded capture metadata.
- Independent literal expected corrected timestamps and owner approval/delta
  inputs. RAWdog code is not used to calculate those expected answers.
- Working/archive/intentional-backup roles in the oracle. These are seeded policy
  inputs, not a claim that production backup protection is implemented.

The RAW files are compact, family-recognizable **metadata containers**: TIFF
structures for CR2/NEF/ARW and Canon BMFF metadata boxes for CR3. ExifTool reads
their real embedded fields. They do not contain camera-compressed sensor data,
full proprietary maker notes, or a realistic RAW preview pipeline. They prove
metadata/scan/hash/planning behavior, not RAW decoding or safe metadata rewriting
of every camera model. The JPEGs are genuine decodable images with synthetic
pixels; metadata-free JPEG cases contain no EXIF.

## Policy recorded for later implementation

The trusted shot instant is chosen first. Date confidence, provenance, timezone,
owner-supplied correction, and selected scope must be recorded separately.
Corrected time = selected original time + signed owner delta. Preserve the
original observation, and never apply an approved delta twice. A single constant
delta does not model a gradually drifting clock; that would require another case
and a separate policy.

When the shot instant is accepted, filesystem creation/modified times can be
repaired to that instant as the user requested. This does not require changing
the file's bytes. When trusted filesystem evidence is used to add embedded shot
metadata, record that the value was supplied later. Metadata insertion changes
the file's full hash, so preserve pre/post identities and lineage. Do not use
the changed hash as evidence that the underlying photo is a newly discovered shot.
Editing managed RAW originals versus adding sidecars remains a separate
format-specific implementation decision; this milestone does neither.

The distinction between embedded `CreateDate`, filesystem creation time, and
filesystem modification time must remain visible. ExifTool's `AllDates` refers
to three common embedded tags, not both filesystem timestamps; see the
[ExifTool FAQ](https://exiftool.org/faq.html). Its
[supported-format list](https://exiftool.org/index.html) distinguishes read/write
support from creating a complete vendor RAW image.

## Acceptance boundaries

Tests verify the generator, seeded timestamps, exact and non-exact groups,
real metadata extraction through RAWdog, metadata-before-mtime precedence,
filesystem fallback, and existing explicit-delta reflow plans. Planning tests
check source bytes/mtime remain unchanged and no proposed destination appears.

Expected repair, confidence assessment, selective bulk correction, metadata
insertion, backup protection, and idempotent correction policies are **future
acceptance requirements**, not implemented features or green assertions here.
In particular, RAWdog currently interprets timezone-free EXIF as UTC. The oracle
marks that case unresolved instead of baking the current assumption into a test.

Later milestones should run those transformations only on fresh copies of this
corpus, then compare observed outcomes against the saved oracle and audit trail.
No milestone requires pointing development commands at the owner's library.
