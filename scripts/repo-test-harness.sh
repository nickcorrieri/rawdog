#!/bin/bash
# Author: Nicholas Corrieri
# Supported invocation (from the canonical checkout):
# /usr/bin/env -i /bin/bash --noprofile --norc scripts/repo-test-harness.sh self-test
# This is a shell-only preflight, never a Python or media-test launcher.

set -euo pipefail
umask 077
export PATH=''
readonly HARNESS_REPO='/Users/nick/Projects/rawdog'
readonly HARNESS_STATE="$HARNESS_REPO/scripts/.repo-test-harness-state"
HARNESS_ERROR=''

fail() {
    printf 'BLOCKED: %s\n' "$*" >&2
    exit 78
}

# Reject lexical escapes before filesystem predicates. Examine one component
# at a time; -L examines the link itself, before -e/-d could follow its target.
# Missing components are allowed for a prospective output path. No file opens,
# realpath/readlink calls, recursive walks, directory creation, or target probes.
contained_path() {
    local candidate="$1" tail component current="$HARNESS_REPO"
    HARNESS_ERROR=''
    case "$candidate" in
        "$HARNESS_REPO") return 0 ;;
        "$HARNESS_REPO"/*) tail="${candidate#"$HARNESS_REPO"/}" ;;
        *) HARNESS_ERROR='outside canonical checkout'; return 1 ;;
    esac
    case "/$tail/" in
        *'//'*|*'/./'*|*'/../'*)
            HARNESS_ERROR='empty, dot, or parent component'; return 1 ;;
    esac
    while :; do
        component="${tail%%/*}"
        current="$current/$component"
        if [[ -L "$current" ]]; then
            HARNESS_ERROR="symlink component: $current"
            return 1
        fi
        if [[ "$tail" == */* ]]; then
            if [[ -e "$current" && ! -d "$current" ]]; then
                HARNESS_ERROR="non-directory ancestor: $current"
                return 1
            fi
            tail="${tail#*/}"
        else
            return 0
        fi
    done
}

require_path() {
    contained_path "$1" || fail "$HARNESS_ERROR"
}

# No discovery through parents, alternate checkouts, or symlinked cwd aliases.
[[ "${PWD-}" == "$HARNESS_REPO" ]] || fail 'start in the canonical checkout'
[[ "$(pwd -P)" == "$HARNESS_REPO" ]] || fail 'cwd is not the canonical checkout'
for HARNESS_REQUIRED in AGENTS.md development-lock.md; do
    require_path "$HARNESS_REPO/$HARNESS_REQUIRED"
    [[ -f "$HARNESS_REPO/$HARNESS_REQUIRED" ]] || fail "missing $HARNESS_REQUIRED"
done
require_path "$HARNESS_REPO/scripts/repo-test-harness.sh"

self_test() {
    local candidate count=0
    for candidate in \
        "$HARNESS_REPO" \
        "$HARNESS_REPO/AGENTS.md" \
        "$HARNESS_REPO/development-lock.md" \
        "$HARNESS_REPO/scripts/repo-test-harness.sh" \
        "$HARNESS_STATE/tmp/new fixture.raw"; do
        contained_path "$candidate" || fail "expected contained path: $candidate ($HARNESS_ERROR)"
        count=$((count + 1))
    done
    for candidate in \
        '' \
        'relative/path' \
        '/' \
        "${HARNESS_REPO}-sibling/file" \
        "$HARNESS_REPO/../outside" \
        "$HARNESS_REPO/scripts/../../outside" \
        "$HARNESS_REPO/scripts/./file" \
        "$HARNESS_REPO/scripts//file" \
        "$HARNESS_REPO/scripts/" \
        "$HARNESS_REPO/development-lock.md/child"; do
        if contained_path "$candidate"; then
            fail "accepted forbidden path: $candidate"
        fi
        count=$((count + 1))
    done
    # Use the existing checkout's interpreter link as a read-only canary. Guard
    # its parent before lstat; never follow the link or inspect its target.
    require_path "$HARNESS_REPO/.venv/bin"
    [[ -L "$HARNESS_REPO/.venv/bin/python" ]] ||
        fail 'symlink canary unavailable; self-test needs review for this checkout'
    for candidate in \
        "$HARNESS_REPO/.venv/bin/python" \
        "$HARNESS_REPO/.venv/bin/python/child"; do
        if contained_path "$candidate"; then
            fail "accepted interpreter symlink: $candidate"
        fi
        [[ "$HARNESS_ERROR" == 'symlink component: '* ]] ||
            fail "symlink canary failed for another reason: $HARNESS_ERROR"
        count=$((count + 1))
    done
    printf 'PASS: %s shell-only path checks; no files created or tests imported.\n' "$count"
    printf 'Scope: lexical/component checks only; no OS isolation or pytest clearance.\n'
}

preflight() {
    local relative
    printf 'Canonical checkout: %s\n' "$HARNESS_REPO"
    printf 'Shell preflight uses no home/config/temp/cache/data files; output is stdout/stderr.\n'
    printf 'Prospective test state paths (checked, not created or activated):\n'
    for relative in home config data cache tmp logs reports pytest; do
        require_path "$HARNESS_STATE/$relative"
        printf '  %s\n' "$HARNESS_STATE/$relative"
    done
    for relative in .venv/bin/python .venv/bin/python3.12 .venv/bin/python3.14; do
        if contained_path "$HARNESS_REPO/$relative"; then
            printf 'UNQUALIFIED runtime candidate: %s\n' "$HARNESS_REPO/$relative"
        else
            printf 'BLOCKED runtime candidate: %s\n' "$HARNESS_ERROR"
        fi
    done
    printf '%s\n' \
        'BLOCKED: Python, standard-library, dependency, and startup paths are not qualified.' \
        'BLOCKED: media subprocesses and OS isolation are not qualified.' \
        'No Python/pytest collection, application imports, or media execution was attempted.' \
        'See docs/RAWdog_REPO_TEST_HARNESS.md for the repository evidence.'
    return 78
}

case "${1-}" in
    self-test)
        [[ "$#" == 1 ]] || fail 'self-test takes no arguments'
        self_test
        ;;
    preflight)
        [[ "$#" == 1 ]] || fail 'preflight takes no arguments'
        preflight
        ;;
    check-path)
        [[ "$#" -gt 1 ]] || fail 'check-path requires an absolute path'
        shift
        for HARNESS_CANDIDATE in "$@"; do
            require_path "$HARNESS_CANDIDATE"
            printf 'CONTAINED PATH: %s\n' "$HARNESS_CANDIDATE"
        done
        ;;
    *)
        printf 'Usage: repo-test-harness.sh {self-test|preflight|check-path PATH...}\n' >&2
        printf 'No Python or media execution mode is provided.\n' >&2
        exit 64
        ;;
esac
