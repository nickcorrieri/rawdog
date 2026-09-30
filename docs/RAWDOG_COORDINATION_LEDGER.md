# Rawdog coordination ledger

Active checkout: `/Users/nick/Projects/rawdog`
Baseline: `cb6785c75cc3c0811d7004da2032f5612f93cd8d` (`main`)

The owner authorized visible worker chats to report directly to **SOL Orchestrator: Rawdog** (`01a0ea18-207a-7450-a629-c2e9a24db2b9`). SOL resolves routine questions and sends **BRAIN: Rawdog** (`01a0e9a1-1cd0-7273-b140-15bc68bc537d`) only significant milestones, material blockers, decision points, or questions it cannot settle. The development lock applies to every chat.

| Chat | First bounded assignment | File ownership |
| --- | --- | --- |
| `01a0efe0-0931-73e2-9d84-399d52be75e2` — BUILD Rawdog Repository Test Harness | Establish a repository-contained test harness and verify path containment; stop tests if runtime inputs or OS isolation cannot meet the lock. | New `scripts/` harness files and `docs/RAWdog_REPO_TEST_HARNESS.md` only. |
| `01a0efe0-3c92-7360-a33a-4aa05beeb4df` — REVIEW Rawdog M2 Reconciliation | Read-only comparison of current main with locally available M2 Git objects; report missing repairs and cleanup hold. | None; read-only. |
| `01a0efe0-77dc-70a2-b225-73e1a8f5117e` — PLAN Rawdog Apple Photos Import Confidence | Review roadmap and document a proposed, read-only import-confidence model. | `docs/LIBRARY_MANAGER_PLAN.md` and `docs/LIBRARY_DISCOVERY_AND_LIGHTROOM.md` only. |

SOL owns this ledger and serializes reviews and local commits. Workers do not branch-switch, merge, cherry-pick, reset, commit, push, release, install dependencies, or access real media. The earlier M2 worktree and temp-based runner are outside the active checkout and prohibited while `development-lock.md` exists. Historical M2 test receipts are not current-checkout verification; M2 is not accepted.

## First-wave receipts

- **M2 reconciliation review complete:** the named M2 commits exist as local Git objects, but main lacks their 13 non-cleanup product paths and associated test/harness changes. A whole merge/cherry-pick of that line would remove or replace the active lock files, so no such operation is permitted. The earlier 159/159 and 3/3 test receipts remain historical; the cleanup hold and 32 unresolved cleanup packet cases remain. No import or test was performed by the reviewer.
- **Photos plan draft complete:** the documentation worker added a proposed read-only M8 import-confidence extension to its two owned files; `git diff --check` passed. SOL review is pending local commit. No Photos access or tests were performed.
- **Repository harness in progress:** the builder identified an external virtual-environment interpreter and external-path use in existing tests. Python/pytest and media-mutating tests remain stopped while it builds a repository-contained, fail-closed path check.
