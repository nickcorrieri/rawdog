# Repository-contained test harness

The supported path currently runs shell-only containment checks. **Python,
pytest collection, application tests, and media tests remain blocked.** The
harness does not install anything, load application code, launch external programs,
create fixtures, or change either development-lock rule.

## Run from the canonical checkout

Use a clean environment and a shell with startup files disabled. These commands
use the operating system to start the shell; their inspected project paths stay
inside `/Users/nick/Projects/rawdog`. Do not activate the existing virtualenv or
run the script through an interactive/login shell as a substitute.

```sh
cd /Users/nick/Projects/rawdog
/usr/bin/env -i /bin/bash --noprofile --norc scripts/repo-test-harness.sh self-test
/usr/bin/env -i /bin/bash --noprofile --norc scripts/repo-test-harness.sh preflight
```

`self-test` returns 0 only when all 17 shell checks pass. `preflight` deliberately
returns **78 (blocked)**, including if the interpreter symlinks are later replaced.
There is no force flag, fallback runtime, or Python/media execution mode. Unknown
modes return 64. An individual proposed path can also be checked:

```sh
/usr/bin/env -i /bin/bash --noprofile --norc scripts/repo-test-harness.sh check-path /Users/nick/Projects/rawdog/scripts/.repo-test-harness-state/tmp
```

The script uses Bash builtins after shell startup and clears `PATH`. It reads no
home/configuration files and creates no temporary files, databases, caches, logs,
or reports. Results go to the calling tool's stdout/stderr. If saving output,
first validate a repository-local destination; no outside redirection is allowed.

## What the checks establish

The script accepts only the exact canonical checkout or an absolute descendant.
It rejects relative paths, sibling-prefix matches, repeated separators, dot and
parent components, file-as-directory ancestors, and symlink components. Each
component is checked for being a link before any predicate that might follow it.
It never calls `realpath`, follows a link, or searches an outside target.

The self-test checks five admissible paths, ten lexical/ancestor refusals, and two
refusals using the current `.venv/bin/python` symlink (leaf and ancestor). The
canary parent is checked first. If that link is absent or its parent becomes a
symlink, the self-test stops with 78 pending review. No synthetic photo is needed.

These checks establish path admission behavior in the current checkout only.
They are **not OS isolation**: they cannot stop concurrent path replacement,
mount aliases, hard-link aliases, or arbitrary subprocess filesystem access. A
`CONTAINED PATH` result does not qualify a runtime, authorize a write, prove a
file's provenance, or establish that a nonexistent path can be created.

For a later qualified runner, the preflight checks prospective `home`, `config`,
`data`, `cache`, `tmp`, `logs`, `reports`, and `pytest` paths beneath
`scripts/.repo-test-harness-state/`. It does not create those directories, set
Python configuration, or claim those paths are effective for pytest.

## Static evidence and execution blockers

Inspected checkout: `cb6785c75cc3c0811d7004da2032f5612f93cd8d`. The checkout was
clean before this harness was added. Only files and symlink entries within this
checkout were inspected; external targets were not examined.

| Area | Repository evidence | Result |
| --- | --- | --- |
| Existing runner | `README.md` documents `python -m pytest`; `pyproject.toml` requires Python >=3.12, pytest >=8, and discovers `tests/`. Runtime dependencies are platformdirs, rich, and typer. | Python startup/imports must be qualified before even collection. |
| Interpreter | `.venv/bin/python` points to `python3.14`; `python3.14` and `python3.12` link to `/opt/homebrew/opt/python@3.14/bin/python3.14` and `/opt/homebrew/opt/python@3.12/bin/python3.12`. | Outside runtime targets; neither was inspected or executed. |
| Virtualenv configuration | `.venv/pyvenv.cfg` declares a Python 3.12.13 base and executable under `/opt/homebrew/Cellar/`; the default link selects 3.14. Both versioned site-packages directories exist locally. | Runtime/standard-library path closure and version agreement are unproved. A virtualenv does not establish containment. |
| Dependencies/startup | The local 3.14 `_editable_impl_rawdog.pth` names this checkout. | That single entry is local; it does not qualify all dependencies, native libraries, startup hooks, or effective import paths. No package was imported. |
| Configuration/database | `rawdog/config.py` uses platformdirs for default config and database paths. | A future runner must establish effective paths before importing/invoking affected code; setting only `TMPDIR` is insufficient. |
| Corpus temp path | `tests/photo_corpus.py:build_corpus` evaluates `Path("/private/tmp").resolve()` even when `tempfile.gettempdir()` is redirected. It also loads `libc.dylib` when seeding macOS creation times. | Setting temp variables alone does not contain this helper; it remains blocked. |
| External media tools | `tests/photo_variants.py`, photo integration tests, and `rawdog/metadata.py` discover or invoke `sips`/`exiftool`; creation helpers use tempfile APIs. | Tool/runtime/config/output paths and OS isolation are unqualified. No fallback run. |
| Drive discovery | `rawdog/drives.py:standard_path_choices` probes `/Volumes` and offers home-derived paths. | Any future selected tests must exclude or contain these calls before execution. |

No OS isolation mechanism was independently qualified in this bounded work. The
guard self-test does not compensate for that missing qualification. No ordinary
unsandboxed media test, `pytest --collect-only`, package install, or runtime copy
was attempted.

## Verification receipt

Verified in the canonical checkout on 2026-09-29:

- Bash syntax check: exit 0.
- `self-test`: 17 checks passed, exit 0.
- `preflight`: all eight prospective state paths passed admission; all three
  interpreter paths were refused at symlink entries; exit 78 as intended.
- `check-path` for the prospective local temp directory: exit 0.
- `check-path` through `.venv/bin/python/child`: refused at the link, exit 78.
- Unsupported `run` mode: exit 64; no Python or media command launched.

No state directory or test artifact was created by these checks. This receipt
applies only to the shell harness; no Rawdog application test result is claimed.

## Remaining work

A separately authorized follow-up must establish a repository-contained Python
runtime and its complete import/startup/dependency paths without inspecting or
copying prohibited outside files. It must qualify effective configuration,
database, cache, temp, report, and subprocess paths before choosing tests. Media
mutation additionally requires independently qualified OS isolation and synthetic
fixtures whose helpers stay within the checkout. Existing test/application files
were outside this builder's edit scope and remain unchanged.

The current result is a fail-closed shell preflight and containment check, not a
passing Rawdog suite, media-safety acceptance, M2 completion, or release clearance.
