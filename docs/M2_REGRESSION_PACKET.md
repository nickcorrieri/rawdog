# M2 noncleanup regression packet

Status: **authored and reviewed as text only; execution blocked**. No Python,
imports, compilation, lint runtime, pytest collection, product case, or media
case was executed for this reconciliation. This is not M2 acceptance.

The retained source is local Git commit
`9e49dbba854a143cd4980f393de2ce2723566cdd`; the current product baseline is
`71298357995909e6b8ecb559ccf3296337efe48a`. Only
[the helper](../tests/m2_cases.py), [the packet](../tests/test_m2_regressions.py),
and this mapping document are added. Current product code, existing tests,
cleanup selectors, lock files, and historical evidence remain unchanged.

## Repository admission and execution hold

The [development lock](../development-lock.md) and
[repository harness qualification hold](RAWDOG_REPO_TEST_HARNESS.md) apply.
The shell harness still does not provide a Python/media execution mode. No
old worker/launcher script, external-world environment contract, outside
receipt path, or historical execution command is imported into this packet.

After separate runtime and OS-boundary qualification, a future runner must
supply an explicit, never-used `--basetemp` path of the form
`/Users/nick/Projects/rawdog/scripts/.repo-test-harness-state/m2-NAME`.
The harness state parent must already exist and be independently admitted.
This document does not authorize its creation or a test run.

The session fixture reads that option without using `tmp_path`,
`tmp_path_factory`, or `getbasetemp`. The helper checks the canonical checkout,
rejects outside/parent-traversal spellings before filesystem access, and checks
in-checkout components with `lstat` before descendant access. It claims only the
new leaf with exclusive `mkdir`; an existing root, including a link, is refused
without listing, resetting, pruning, or removing it. Each case then creates an
exclusive random child with working/archive/backup/state/canary directories.
Seed files use exclusive writes; parents are checked for links. Case directories
are retained after tests. The canary is inside that same synthetic case, not outside the
repository. No repository ancestor outside the checkout is inspected by the
admission helper.

Case fixtures import product modules only after admission, check the imported
package path, and write real synthetic JSON configuration. Default CLI config
and database paths point to that case. The old shared-loader monkeypatch is
removed. Qualification must separately contain interpreter startup, imports,
native libraries, configuration, caches, logs, pytest state, and any process
access before collection. A path option or marker is not an isolation receipt.
Do not combine this packet with fixtures that invoke pytest's basetemp allocator
and could reset the claimed root.

## Retained case map

There are **15 retained test functions / 29 static parameter expansions**.
These counts come from source inspection, not pytest collection. Every row is
unrun and still requires independent runtime evidence. Names below have the
`test_` prefix and live in `tests/test_m2_regressions.py`; source lines refer to
the retained commit's file of the same name.

| Test suffix | Source line | Cases | Required observation |
| --- | ---: | ---: | --- |
| `copy_does_not_overwrite_concurrent_destination` | 265 | 1 | Injection runs before publication; source remains `same0001`, competing destination `keeper99`. |
| `move_does_not_overwrite_concurrent_destination` | 283 | 1 | Competing destination and original source both survive unchanged. |
| `transfer_rechecks_destination_parent_components` | 303 | 2 | COPY/MOVE reject the exchanged parent; repository-local canary receives no file. |
| `copy_does_not_consume_unowned_matching_partial` | 325 | 1 | Exact `skipped_existing_partial` result; unowned partial and source remain unchanged. |
| `copy_failure_preserves_replaced_partial_owned_by_another_writer` | 336 | 1 | Injected interruption preserves the replacement partial and source; no destination publishes. |
| `equal_size_distinct_existing_destination_is_collision` | 359 | 2 | COPY/MOVE classify unequal equal-size bytes as collisions. |
| `planner_does_not_claim_distinct_equal_size_file_already_present` | 369 | 1 | Real planner reports a collision; both literal payloads survive. |
| `nonowner_finish_cannot_release_active_writer` | 395 | 1 | Wrong plan/token cannot release the writer; a competing acquisition is blocked. |
| `same_plan_and_pid_without_owner_token_cannot_release_writer` | 409 | 1 | Matching plan/PID with the wrong token cannot release the writer. |
| `reviewed_source_changes_are_held_before_transfer` | 423 | 8 | COPY/MOVE hold same-size, restored-mtime, larger, or removed reviewed sources. |
| `skipped_destination_requires_fresh_evidence` | 446 | 4 | Both persisted skip spellings reject removed or same-size-changed keepers. |
| `failed_required_post_audit_blocks_done` | 468 | 2 | Injected wrong-size or equal-size-wrong-byte destinations cannot yield done/verified. |
| `resumed_completed_row_does_not_trust_equal_size_destination` | 489 | 1 | A successful copy followed by changed destination bytes is held on resume. |
| `quick_catalog_invalidates_previous_full_hash` | 502 | 2 | Same/new-size quick updates clear previous full hashes and full counts. |
| `copied_store_identity_does_not_replace_live_original` | 523 | 1 | A copied portable identity cannot relink the live original; both media copies remain. |

Adaptations retain the literal byte oracles and injection assertions. Lock tests
use the current mandatory token API without legacy `hasattr` fallback. The
unowned-partial case now requires its specific refusal status instead of accepting
any safety refusal. Destination-parent injection uses an in-case `canary` path.
No subprocess code, corpus generator, cleanup/report/force helper, or sidecar
constant is present. Synthetic CR3-named literals are byte fixtures, not decoded
camera images or proof of complete ancillary/sidecar preservation.

## Deferred and excluded source cases

These definitions are deliberately absent from the collected packet, with no
xfail or blanket skip that could be mistaken for acceptance.

| Future qualification unit | Source test suffix | Source line | Cases | Missing evidence |
| --- | --- | ---: | ---: | --- |
| Subprocess lock race | `exclusive_execution_competing_processes` | 385 | 2 | Independently contained child runtimes and same-store contention across shared/separate databases. |
| Subprocess lock independence | `unrelated_store_writers_remain_independent` | 390 | 1 | Qualified child runtimes and simultaneous ownership of unrelated stores. |
| Photo corpus | `primary_raw_and_jpeg_are_separate_payloads` | 542 | 1 | Repository-contained corpus/native helper qualification; no external corpus helper imported. |
| Preview | `long_path_preview_retains_source_and_destination_basenames` | 558 | 1 | Separate long-path display qualification; no file-safety acceptance inferred. |

The entire held cleanup block at source lines **103–263** is excluded:

| Excluded test suffix | Source line | Static expansions |
| --- | ---: | ---: |
| `never_lose_copies_reciprocal_report` | 104 | 2 |
| `registered_archive_source_is_protected` | 117 | 4 |
| `force_cleanup_rejects_reciprocal_keepers` | 132 | 2 |
| `cleanup_preserves_self_keeper` | 143 | 1 |
| `cleanup_requires_independent_storage_object` | 152 | 2 |
| `cleanup_revalidates_same_size_bytes_after_confirmation` | 167 | 8 |
| `cleanup_revalidates_missing_keeper_after_confirmation` | 186 | 2 |
| `cleanup_rejects_original_symlink_components` | 201 | 4 |
| `cleanup_rechecks_path_components_after_confirmation` | 226 | 4 |
| `cleanup_rejects_unique_ancillary_payload_loss` | 251 | 2 |

Historical coordination describes 32 cleanup cases. The named source block has
10 functions and 31 visible parameter expansions; the full source's published
65-case count reconciles as 29 retained + 5 deferred + 31 excluded. This is a
source-inventory discrepancy, not permission to recover or execute another
cleanup case. The whole historical cleanup unit stays held under either count.

## Limits

No retained or deferred case has a new pass/fail result. The in-process lock
controls do not establish process-race behavior. Admission cannot prove native
path closure, stop concurrent replacement or mount/hard-link aliases, or contain
arbitrary runtime access. Current native no-replace transfers require separate
platform qualification; an unsupported-platform refusal is not transfer success.
No real media, cleanup acceptance, broad suite green result, M2 completion,
deployment, or release clearance is claimed.
