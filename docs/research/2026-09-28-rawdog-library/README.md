# Library review research archive — 2026-09-28

These are historical reviews and receipts for product baseline
`1f1e2d02055a987c4dd7eef2ef02a74779b15731`. They are evidence inputs, not the
active roadmap or operating authorization. Use the consolidated
[library-manager plan](../../LIBRARY_MANAGER_PLAN.md) and
[discovery/Lightroom specification](../../LIBRARY_DISCOVERY_AND_LIGHTROOM.md)
for current scope, sequencing and BRAIN handoff.

## Contents and provenance

| Archived artifact | Original source and purpose |
| --- | --- |
| [Combined library review](rawdog-library-review.md) | `/private/tmp/rawdog-library-review-2026-09-28.md`; this BRAIN chat's synthesis of Astra, Sol and parent review. |
| [Parallel Fido review](rawdog-fido-audit-plan.md) | Parallel chat artifact `rawdog-fido-audit-plan.md`; independently proposed roadmap against the same product baseline. |
| [Parallel parent probe source](rawdog-audit-probes.py.txt) | Original `rawdog-audit-probes.py`, preserved as inert text. Four temporary-fixture probes; this archive does not run them. |
| [Parallel parent probe results](rawdog-audit-probes.json) | Recorded results for overlap/deletion, stale catalog hash, format scanning and same-name/size identity. |
| [Parallel independent Sol evidence](rawdog-independent-audit-evidence.json) | Six summarized synthetic probe receipts, including locking, overwrite, stale skip, changed MOVE and duplicate cleanup. The original independent probe source was not available in this source directory and is not invented here. |
| [Parallel full-suite receipt](rawdog-audit-tests.txt) | Original `rawdog-audit-tests.log`: 200 passed, one failed in 6.79 seconds. |
| [Parallel isolated recheck](rawdog-audit-preview-recheck.txt) | Original `rawdog-audit-preview-recheck.log`: one passed in 0.34 seconds; does not replace the original full-suite result. |
| [Provenance manifest](provenance.json) | Exact original paths, observed modification times, byte lengths and SHA-256 values for both source and archived artifacts. |

The six parallel artifacts came from
`/Users/nick/.codex/visualizations/2026/09/25/01a0da18-e72b-76e2-854c-93df23d93e88/`.
Although that directory contains `2026/09/25`, the review and saved receipts are
dated September 28. The manifest records observed timestamps without asserting
they establish when every individual probe executed.

Every source was inspected before copying; no secrets or unrelated content were
identified. The script, JSON and logs preserve their exact original bytes. The
script's `.py.txt` suffix keeps historical probe code out of runnable Python
discovery; its machine-specific import path remains historical context. Logs
use `.txt` names to avoid the repository's ignored-log rule. Do not execute this
archive as a test suite or point any probe at a real library.
The full-suite log retains its two whitespace-only excerpt lines (28 and 30)
verbatim; they are historical evidence, not newly introduced code whitespace.

Markdown copies change links only: repository-source links are relative with
line anchors, and archived evidence links refer to sibling files. Source line
numbers refer to the stated baseline and may drift after future implementation.
Original and archived hashes make these transformations explicit. Findings,
historical wording and test receipts are retained, including recommendations
later superseded by the consolidated Mac/Windows roadmap.

## Distinct verification receipts

The combined review records this chat's original **201 passed** baseline run and
Sol's **69 passed** focused run. The parallel review records **200 passed / one
preview-display failure**, followed by a successful isolated short-path recheck.
These are separate historical invocations, not contradictory replacements for
one shared receipt. Their differing path conditions and retained failure remain
visible in the reports.

The consolidated plan separately records M1 acceptance: 177 generated files,
37 focused corpus checks, and the parent's later **238 passed** integrated run.
Those are prior receipts, not checks performed while packaging this archive.
No product repairs, mutating probes, full suites, installations, generated media
binaries or temporary corpus outputs are part of this archival commit.
