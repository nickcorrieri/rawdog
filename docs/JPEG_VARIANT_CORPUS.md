# Patterned JPEG relations and photo-condition requirements

Author: Nicholas Corrieri

This is a small synthetic companion to `SYNTHETIC_PHOTO_CORPUS.md`. It creates
13 JPEG files from an asymmetric 64 by 48 pixel geometric pattern. The patterned
pixels make resized, cropped, rotated, and recompressed images distinguishable.
No photograph, real library, archive, downloaded image, or installed package is
used. Existing macOS `sips` encodes and decodes the images. Existing ExifTool
checks real embedded tags when available.

```sh
.venv/bin/python tests/photo_variants.py
.venv/bin/python -m pytest tests/test_photo_variants.py
```

The generator takes no arguments and always allocates a fresh OS temporary
directory. It writes `media/`, encoder scratch files, `expected.json`, and
`observed.json`. It never cleans an existing folder. Tests keep decoder outputs
in separate new temporary folders. Binary fixtures remain outside Git.

The pattern recipe and embedded metadata are deterministic. Encoded byte
identity is checked across two runs of the installed encoder. Bytes need not be
identical across different macOS encoder versions; the manifest records the
encoder version. The 13 media files occupy about 27 KB on the current encoder,
with an enforced limit of 1 MB. Scratch files are separate from media inventory.

## Seeded relationships

Every case uses `IMG_0001.jpg` except the `.JPEG` extension control. Capture tags
are identical where present: DateTimeOriginal `2024:05:20 10:30:00`, explicit
OffsetTimeOriginal `-05:00`, and SubSecTimeOriginal `125`. ImageDescription and
Orientation are separate metadata. The fixture does not claim to preserve every
EXIF field, maker note, ICC profile, IPTC field, or XMP packet.

| Case | Known seed relationship | Expected future read-only outcome |
| --- | --- | --- |
| Original | Archive reference, 64 x 48 | Reference kept |
| Working exact copy | Same bytes, different filesystem mtime | Exact present; retain pending separate policy review |
| Intentional backup exact copy | Same bytes, separate role and mtime | Exact present; protected backup kept |
| `.JPEG` exact copy | Same bytes, different extension spelling | Exact present |
| Metadata changed | Same JPEG coding data, new description | Same decoded pixels; metadata difference needs review |
| EXIF stripped | Same JPEG coding data, capture and orientation tags removed | Same decoded pixels; preserve provenance difference |
| Recompressed | Same dimensions, lower JPEG quality | Visual derivative candidate; keep and review |
| Reduced and recompressed | 32 x 24, same basename and capture subset | Visual derivative candidate; keep and review |
| Upscaled and recompressed | 128 x 96, same basename and capture subset | Derived; larger dimensions do not make it a better original; keep and review |
| Crop | Center 48 x 32 crop, recompressed | Edited derivative candidate; keep and review |
| Rotated pixels | 90 degree raster rotation, reencoded, 48 x 64 | Orientation/derivative candidate; keep and review |
| Orientation 6 | Same encoded raster, changed EXIF orientation | Orientation candidate; keep and review |
| Different photo | Rearranged geometry, same palette, name and capture tags | Distinct photo kept; false-match control |

The resized export is a generic synthetic export/social derivative. It does not
reproduce or prove the pipeline of Google, Instagram, or any named service.
Tests measure that the reduced export has both fewer pixels and fewer file bytes
than the reference. The upscaled export's larger decoded dimensions are verified
independently; its hash differs and its oracle forbids selecting it as a better
original merely because it is larger.
Stored raster dimensions and orientation-applied dimensions are recorded
separately. macOS `sips` applies EXIF orientation while decoding this corpus.

The oracle knows lineage because the generator created the variants. A future
similarity scanner does not inherit that knowledge. Tests prove the seed bytes,
dimensions, real decode results, metadata subset, exact groups, and negative
control; they do not prove a production visual matching algorithm. Current
RAWdog observations cover read-only inventory, SHA-256 and capture extraction.
Similarity classifications remain future acceptance expectations.

## Read-only “do I have this already?” contract

Use evidence labels rather than an uncalibrated percentage. Identity confidence,
capture-time confidence, and copy/backup protection are separate fields.

| Outcome | Required evidence | Policy |
| --- | --- | --- |
| Exact present | Freshly read full-content SHA-256 and size match on accessible stable files | Show every location and role; keep all files during scan |
| Same decoded pixels, different file | Pixel equality under a recorded decoder, orientation and colour policy; differing full hashes | Describe metadata/rendering differences; keep and review |
| Visual derivative candidate | Similarity signal plus dimensions and other observations | Show candidate relationship and uncertainty; keep and review |
| Related companion | Reliable relationship evidence for RAW/JPEG, XMP, or Live Photo members | Keep each representation and report the group |
| Distinct / conflicting | Different content, collision, conflicting companion version or evidence | Keep independently; report conflict |
| No match in scanned scope | Complete successful scan of named accessible roots and supported capabilities | Say “no match in this scan,” never “not anywhere in your library” |
| Unknown / incomplete | Offline volume, placeholder, unreadable/changed file, unsupported decode, cancelled or partial scan | Keep; report exactly what could not be checked |

A filename, size, EXIF timestamp, camera identifier, or perceptual hash alone is
not exact identity proof. Existing same-name/same-size transfer skips remain
documented skip decisions. They must not be promoted to “exact present.” Matching
pixels describe a specified rendering, not equivalent metadata, editability or
original capture. More pixels or bytes alone do not establish the preferred copy.
No perceptual match, exact-pixel match, or scan outcome authorizes removal. Any
later working-copy cleanup remains separately reviewed, freshly revalidated and
subject to archive/backup protection. Archive deletion and overwrite remain
forbidden.

## Bounded condition backlog

These are requirements to seed later, not claims that this corpus implements
them. Keep scenario coverage compact: baseline plus selected pairs and negative
controls; do not cross every transformation with every vendor extension.

**P0 — trustworthy scan and safe retention.**

- Exact copies in multiple working folders, archives and intentional backups;
  same name/size/time with genuinely different content; same photo with metadata
  removed, inserted or altered; reduced/recompressed exports and false matches.
- Missing, malformed and contradictory capture tags; EXIF versus XMP versus
  filesystem disagreement; no timezone, DST repeated and nonexistent wall times;
  signed owner clock corrections scoped to camera/date range and applied once.
  The main corpus already covers several of these timestamp cases.
- Zero bytes, truncated and structurally damaged images; valid headers with
  incomplete payloads; unavailable decoder; renamed/misleading extensions.
  Metadata readability is not full image health.
- Source modified, replaced, removed or unreadable during scan/hash; drive
  disconnect; cloud placeholder with no locally readable bytes; stale catalog
  row; interrupted scan. Preserve incomplete observations and avoid an absence
  or cleanup conclusion. Never download placeholders implicitly.
- Case and Unicode-normalization destination collisions, long paths and two
  files converging on one destination. Use synthetic path strings for collisions
  that the host filesystem cannot physically represent; hold for review.
- `.partial` imports, abandoned transfer artifacts and mixed completed/incomplete
  batches. AppleDouble `._*`, `.DS_Store`, thumbnails and actual XMP sidecars must
  be distinguished rather than all treated as captures or all ignored.

**P1 — representation and companion fidelity.**

- RAW+JPEG pairs sharing basename/date but distinct originals; matching basename
  from different shoots; XMP sidecars that are orphaned, divergent, newer/older,
  or renamed. Preserve both conflicting sidecar versions; do not choose by mtime
  alone or merge automatically.
- Live Photo still/video pairs with authoritative relationship identifiers when
  available; missing companion, ambiguous match, edited still and separate video.
  Equal basename/time is a candidate, not definitive pairing.
- Orientation flags versus physically rotated pixels, crop, monochrome/export
  edits, ICC profile differences, different colour spaces and bit depths,
  progressive versus baseline JPEG. Specify whether a comparison uses encoded
  samples, oriented samples or colour-managed rendering.
- Symlinks/hard links, volume aliases and remount paths; distinguish one storage
  object observed twice from independent backup copies; prevent cycles and
  scanning outside the selected scope.

**Later — narrowly justified expansion.** Camera drift varying over time,
advanced RAW preview/render comparisons, HDR/auxiliary-image bundles, burst
groups, panorama edits and long video similarity. Add these only with explicit
capability and acceptance boundaries.

## Supported-format boundaries

Current `rawdog/metadata.py` gates inventory by extension: vendor RAW and DNG,
`.jpg`/`.jpeg`, and configured camera video extensions. HEIC/HEIF, PNG, TIFF and
XMP are not currently camera-capture extensions. Recognition, byte copying,
metadata reading, complete decoding, relationship detection and metadata writing
are distinct capabilities; a recognized extension proves none of the others.

This corpus covers genuine JPEG decoding and its explicit EXIF subset only.
The main corpus's compact CR2/CR3/NEF/ARW containers cover metadata parsing, not
camera-compressed RAW decoding or safe RAW metadata rewriting. P0 format claims
must be bounded by extension recognition, safe byte preservation and accurate
unsupported/error reporting. Add genuine synthetic HEIC/PNG/TIFF and companion
cases when their capability milestone is authorized and existing approved tools
can generate them. Do not silently treat unrecognized valuable assets as junk.
