# Synthetic worker boundary — authored only

Nothing here has been executed, imported, collected, or runtime-qualified.
Do not run the entry or controls under the current development lock. This is
source for review, not permission to start Python. The existing shell preflight
remains unchanged and fail-closed. No dependency installation is needed or
authorized by these files.

## Admission and fixed ceiling

`worker.py` is both the repository-owned entry script and the reusable boundary
module. Its own absolute `__file__` spelling fixes the data ceiling to its
containing `scripts/synthetic_worker/` directory. Admission requires the EXACT
`/Users/nick/Projects/rawdog/scripts/synthetic_worker/worker.py` location; a copy
elsewhere with the same suffix is refused. Relative script locations,
dot components, alternate filenames, and empty components fail closed. No cwd,
environment setting, command-line argument, root parameter, or prefix-string
comparison chooses the ceiling.

The entry always exits 78 without calling the boundary, importing Rawdog, or
starting product/media work. An environment flag or qualification receipt cannot
enable it. A later execution path requires separately reviewed code after BOTH
OS containment/runtime qualification and explicit approval of named packages.
Even the standard-library imports in these files remain unqualified today.

Bootstrap opens the exact canonical checkout directory with `O_NOFOLLOW`, then
walks `scripts` and `synthetic_worker` by descriptor with `O_NOFOLLOW`. It checks
the script leaf without following links and refuses a symlink or multiply linked
script. These repository directory handles and script-leaf metadata are only
for admission, not authority to access arbitrary repository data. Data operations
remain restricted to a freshly owned run below the script's directory.

The future qualified launcher must admit the actual script BEFORE Python starts
and establish that ancestors ABOVE the canonical checkout are not aliases.
The boundary does not walk or inspect system/home ancestors to manufacture that
proof. It also cannot retroactively validate files Python already imported.
These unresolved bootstrap/import limits are reasons no runtime path is enabled.

## Owned data and operations

`OwnedRun.create()` exclusively creates a `run-…` directory directly below the
fixed ceiling. An optional name is one restricted component, never a root or
path override. Existing directories and live/dangling links cannot be adopted,
reset, or deleted. A retained descriptor and device/inode comparison detect
replacement of the run pathname. The API has no attach operation.

Every public file operation accepts only absolute literal strings inside that
particular fresh run. Exact path components, not spelling prefixes, establish
membership. Parent/dot components, repeated separators, relative paths, sibling
runs, source code, and other repository data are refused before filesystem I/O.
For copy/move, BOTH source and destination spellings pass before either is
accessed. Each nested directory is then opened relative to the owned descriptor
with `O_DIRECTORY | O_NOFOLLOW`; live and dangling leaf/ancestor links are
refused. No `resolve()`, `realpath()`, cwd lookup, or implicit `__fspath__` runs.

Supported operations are new-directory creation, exclusive new byte writes,
reads, SHA-256, metadata reads, name listings, regular-file copy/move/delete,
and empty-directory removal. Listing inspects each immediate entry without
following links and refuses links, multiply linked files, and special files.
No recursive reset, recursive deletion, overwrite, in-place content edit,
permission/ownership/timestamp mutation, link creation, or generic open handle
is exposed. Run roots cannot be deleted by this API; `close()` only closes
descriptors. An error can leave owned partial data for later reviewed handling.

Reads/copies require regular files with exactly one hard link, checked before
and after opening. Deletes and metadata reject multiply linked regular files.
New destinations use `O_CREAT | O_EXCL | O_NOFOLLOW` and mode 0600. No existing
inode is opened for writing, avoiding mutation of a pre-existing outside hard
link. Copies do not preserve arbitrary metadata. Move means copy to a NEW file,
then unlink the checked source; it is not atomic or crash durable. An error may
leave both files or an incomplete destination and never triggers broad cleanup.

## Limits that remain

These wrappers constrain only their own calls. They do not intercept product,
Python-library, SQLite, codec, subprocess, or native-extension I/O. A caller can
bypass a Python API or alter its private state; this is not an adversarial-code
sandbox. Product code and existing test helpers are not wired to it.

Descriptor traversal avoids following replaced path links, but portable POSIX
calls cannot prevent a concurrent actor from moving an already opened directory
outside the ceiling, mounting/aliasing storage, substituting names between a
check and unlink, or adding a hard link after a check. Even a fresh inode can
gain an outside hard link during a write. Mode 0700/0600 reduces accidental
sharing; it does not isolate another process running as the same user. The
initial mkdir/open claim also requires exclusion of concurrent directory
replacement. OS containment and an exclusive synthetic environment are still
required; the source does not claim atomic race safety or runtime clearance.

## Authored controls

`test_boundary_authored.py` contains standard-library unittest controls, with no
product imports, media, catalogs, configuration, pytest fixtures, or external
temporary directories. They have not been run or collected. There is no launch
command here because interpreter/import/cache/report containment is unresolved.

Future qualification must keep interpreter imports, bytecode/cache writes,
test-runner outputs, and any runtime state within an explicitly admitted
closure. These controls leave fresh synthetic run directories in place; they
never recursively clean paths. Malicious-link fixtures point only at disposable
canaries in another fresh run within THIS script directory. Outside spellings
are checked with filesystem calls patched to fail before I/O, never by trying
an operation against a real system/user file. The packet covers healthy file
operations, both endpoints, source-code protection, parent/sibling/cwd inputs,
live/dangling leaf and ancestor links, hard links, root reuse/replacement, and
the unconditional entry gate. Authorship is not a passing test result.

There is no dependency on `tests/m2_cases.py`; that existing helper and the
BRAIN-owned runtime allowlist are intentionally untouched.
