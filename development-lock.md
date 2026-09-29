# Development lock: repository-only access

This is a standing boundary for every agent and automation working on Rawdog.
While this file exists in the project root, inspect **only files inside the
active, canonical Rawdog repository checkout**. Do not browse, list, search,
open, read, hash, index, copy, or otherwise examine files in another checkout,
worktree, project, home directory, temporary directory, mounted volume, or
external service. Symlinks and other aliases do not make an outside target
part of this checkout.

The same boundary applies during tests and subprocesses. Test inputs,
generated fixtures, configuration, databases, caches, logs, reports, and
output must stay inside this checkout. Check their effective paths before
running a test. If the existing runner, dependency, or test cannot be kept
within this boundary, **do not run it**; report what is blocked. Do not use
outside files as examples, baselines, fixtures, or fallback inputs. Tools may
use the operating system to start, but that is not permission to inspect
outside project files or let tests consume outside project data.

No agent may edit, remove, rename, replace, weaken, bypass, or clear this file
or the matching rule in `AGENTS.md`, directly or through another agent, tool,
Git operation, or branch switch. This lock ends **only when the human owner
manually deletes `development-lock.md`** from the project root. Until then,
conflicting work must stop at the boundary.
