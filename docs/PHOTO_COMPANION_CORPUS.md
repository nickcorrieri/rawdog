# Companion and storage-condition seed corpus

This is a fixture milestone, not implementation of a library manager. Generate
known synthetic bytes, inspect the current scanner, and retain independent
expected future outcomes. No user photos, real mounts, application configuration,
downloaded media, package installation, or product changes are involved.

```sh
.venv/bin/python tests/photo_companions.py
.venv/bin/python -m pytest tests/test_photo_companions.py
```

The generator accepts no input or output paths. Each call allocates a fresh OS
temporary directory and leaves it available for inspection. It creates 26 tiny
files, with fewer than 100 KB of payload, plus `expected.json` and (when run as a
script) `observed.json`. It neither deletes a directory nor reuses an existing
corpus. Files have a fixed modification time and deterministic bytes; the output
directory is intentionally unique. RAW content reuses the parent's metadata-only
CR2 recipe, while JPEG content reuses its real 8-by-8 synthetic image recipe.

| Fixture | Known seed and expected future outcome |
| --- | --- |
| RAW + JPEG + XMP | One contextual capture, three separate files. Preserve all bundle members; a JPEG is not an exact duplicate of its RAW. |
| Divergent sidecars | Valid XMP packets with ratings 2, 4, and 5. Preserve all versions; no automatic last-write-wins merge. |
| Reused basenames | Another shoot by the same body and another body at the same time. Distinct content and explicit capture identities despite `IMG_0001` reuse. |
| Case and Unicode conflicts | `.jpg`/`.JPG` and NFC/NFD filenames in separate source directories. The manifest states colliding planned targets; no conflicting destination is written. Comparison rules describe target-filesystem conditions, not universal filesystem behavior. |
| AppleDouble | Header-only `._` fixtures, classified as filesystem companions, never captures. This is not a resource-fork restoration test. |
| Interrupted copies | One complete RAW byte stream under `.partial` and one truncated JPEG partial. Neither is a finished capture or automatic recovery approval. |
| Invalid images | Zero-byte JPEG/RAW, truncated JPEG/CR2, and JPEG/RAW extension-container swaps. Retain bytes and flag uncertainty; scanner inclusion is not decoder validation. |
| Storage roles | Identical bytes in working, primary archive and intentional backup locations. Protected copies stay protected; content equality alone gives no removal permission. |
| Offline location | A logical backup record only, with no filesystem path or mounted volume. Offline does not mean deleted and does not count as a currently verified retained copy. |

The current scanner includes 19 of the 26 files. It excludes three XMP sidecars,
two AppleDouble files and two partial files. It includes deliberately malformed
and extension-mismatched inputs because scanning currently recognizes extensions,
not container integrity. These observations are asserted separately from the
future-policy oracle; tests must not convert a known limitation into a promised
capability. Optional ExifTool integration tests explicitly skip if that already
installed tool is unavailable. No RAW decoding, original rewriting, deduplication,
bundle detection, quarantine, or offline-store implementation is claimed.

## Format support conditions for the library-manager plan

Record inventory/hash/copy, metadata read, preview decode, filesystem timestamp
write, and embedded metadata write as separate capabilities. An unreadable preview
must not exclude a file from preservation. The existing RAW and camera-video byte
intake remains available while richer capabilities are qualified incrementally.

| Phase | Families | Conditions |
| --- | --- | --- |
| 1 | Canon CR2/CR3, Sony ARW, Nikon NEF/NRW, DNG, JPG/JPEG; XMP companions | Metadata-first acceptance. Preserve originals. Test camera model and recording mode independently for preview or rewrite claims. JPEG baseline/progressive and grayscale/RGB fixtures precede CMYK, HDR and multi-image claims. |
| 2 | Other existing RAW families; add HEIC/HEIF/HIF, TIFF, PNG | Preserve all container data. Qualify auxiliary images, high bit depth, alpha, multipage and unusual compression separately. Keep unknown vendor companions opaque. |
| 3 | WebP/AVIF and rarer JPEG-family formats | Add on demonstrated library demand, with runtime codec detection. No blanket animation/HDR/codec guarantee. |
| Retained | Existing camera video extension list | Byte preservation and conditional metadata extraction; playback requires container plus codec support. No transcoding or embedded video date repair initially. |

Metadata read/write capability is not camera-image decoding or proof of safe
rewriting. Consult the [official ExifTool format list](https://github.com/exiftool/exiftool/blob/master/README)
and qualify actual files. JPEG metadata includes multiple segments, including
extended XMP and ICC; preserve those during any later narrowly scoped write.
See [ExifTool JPEG tags](https://exiftool.org/TagNames/JPEG.html).

Prefer catalog corrections and preserved originals. A future embedded edit makes
a new byte identity with before/after lineage. Filesystem timestamp repair is a
separate explicit action requiring a trusted instant, filesystem capability and
readback. Preserve tag group, original text, subseconds and unknown timezone state.
QuickTime date fields cannot all be assumed UTC: cameras sometimes store local
values. [ExifTool QuickTime documentation](https://exiftool.org/TagNames/QuickTime.html)
also documents CR3 padding changes during metadata writes.

Sidecar interoperability is format-specific: Adobe uses sidecars for proprietary
RAW and embeds XMP in JPEG/TIFF/DNG. See [Adobe metadata storage rules](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html).
Keep RAW/JPEG representations, bursts, sidecars and spanned video as different
relationship types; missing or ambiguous members block complete-bundle claims.
Live Photos exported from Photos contain separate still and video files; preserve
both. [Apple export documentation](https://support.apple.com/en-au/guide/photos/-pht6e157c5f/mac).

For macOS previews, query available [ImageIO source types](https://developer.apple.com/documentation/imageio/cgimagesourcecopytypeidentifiers%28%29?language=objc)
and record actual decode results and OS/backend versions. RAW support is also
camera/build-specific, as illustrated by [LibRaw's supported-camera list](https://www.libraw.org/supported-cameras).
The synthetic containers here do not establish support for compressed sensor
data, every camera mode, or embedded RAW editing. Those require a later fixture
ledger with provenance, model/mode and the exact capability tested.
