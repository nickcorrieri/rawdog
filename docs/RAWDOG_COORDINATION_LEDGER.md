# Rawdog coordination ledger

Active checkout: `/Users/nick/Projects/rawdog`
Baseline: `cb6785c75cc3c0811d7004da2032f5612f93cd8d` (`main`)

The owner authorized visible worker chats to report directly to **SOL Orchestrator: Rawdog** (`01a0ea18-207a-7450-a629-c2e9a24db2b9`). SOL resolves routine questions and sends **BRAIN: Rawdog** (`01a0e9a1-1cd0-7273-b140-15bc68bc537d`) only significant milestones, material blockers, decision points, or questions it cannot settle. The development lock applies to every chat.

| Chat | First bounded assignment | File ownership |
| --- | --- | --- |
| `01a0efe0-0931-73e2-9d84-399d52be75e2` — BUILD Rawdog Repository Test Harness | Establish a repository-contained test harness and verify path containment; stop tests if runtime inputs or OS isolation cannot meet the lock. | New `scripts/` harness files and `docs/RAWdog_REPO_TEST_HARNESS.md` only. |
| `01a0efe0-3c92-7360-a33a-4aa05beeb4df` — REVIEW Rawdog M2 Reconciliation | Read-only comparison of current main with locally available M2 Git objects; report missing repairs and cleanup hold. | None; read-only. |
| `01a0efe0-77dc-70a2-b225-73e1a8f5117e` — PLAN Rawdog Apple Photos Import Confidence | Review roadmap and document a proposed, read-only import-confidence model. | `docs/LIBRARY_MANAGER_PLAN.md` and `docs/LIBRARY_DISCOVERY_AND_LIGHTROOM.md` only. |
| `01a0efe4-909e-7c60-a8ad-f611f3aebc45` — BUILD Rawdog M2 Store Repair | Selectively reconcile the store hash-cache and portable-identity repair from local Git objects. | `rawdog/stores.py` and `tests/test_stores.py` only. |

SOL owns this ledger and serializes reviews and local commits. Workers do not branch-switch, merge, cherry-pick, reset, commit, push, release, install dependencies, or access real media. The earlier M2 worktree and temp-based runner are outside the active checkout and prohibited while `development-lock.md` exists. Historical M2 test receipts are not current-checkout verification; M2 is not accepted.

## First-wave receipts

- **M2 reconciliation review complete:** the named M2 commits exist as local Git objects, but main lacks their 13 non-cleanup product paths and associated test/harness changes. A whole merge/cherry-pick of that line would remove or replace the active lock files, so no such operation is permitted. The earlier 159/159 and 3/3 test receipts remain historical; the cleanup hold and 32 unresolved cleanup packet cases remain. No import or test was performed by the reviewer.
- **Photos plan draft complete:** the documentation worker added a proposed read-only M8 import-confidence extension to its two owned files; `git diff --check` passed. SOL review is pending local commit. No Photos access or tests were performed.
- **Repository harness complete:** the builder added `scripts/repo-test-harness.sh` and `docs/RAWdog_REPO_TEST_HARNESS.md`. SOL reran Bash syntax and 17 shell-only containment checks (both exit 0); preflight deliberately returned 78 because the virtual-environment interpreter and other runtime paths remain outside or unqualified. Python/pytest and media-mutating tests did not run. The guard is not OS isolation.
- **Selective M2 import order approved:** first the two-path store unit; then transfer foundation (`rawdog/{safety,verifier,compare,copier,den,inventory,planner}.py` and five scoped tests); then execution and locks (`rawdog/{runlock,db,models,execution,cli}.py` and two scoped tests). The independent reviewer supplied the path and dependency map from local Git objects. Packet and historical worker scripts require separate lock-compliant reconciliation and are not current test clearance. No whole-branch operation is authorized.
- **Store unit statically reviewed:** the builder reconciled only `rawdog/stores.py` and `tests/test_stores.py` from local commit `6acf06a`; the independent Sol reviewer found no actionable defect in quick-catalog evidence invalidation or copied portable-ID protection. `git diff --check` passed. No Python or media tests ran, and this is not M2 acceptance.
