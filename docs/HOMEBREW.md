# RAWDOG Homebrew Packaging

Author: Nicholas Corrieri

RAWDOG can be packaged for Homebrew after a tagged source release exists.
Do not publish the formula until the source tarball checksum and dependency
resource blocks are filled in.

## Release Inputs

- GitHub repository: `https://github.com/nickcorrieri/rawdog`
- Formula name: `rawdog`
- CLI binary: `rawdog`
- License: `Apache-2.0`
- Python requirement: `python@3.12` or newer
- Runtime dependencies: `platformdirs`, `pydantic`, `rich`, `typer`

## Formula Prep

1. Tag a release, for example `v0.1.0`.
2. Download the release tarball from GitHub.
3. Generate the tarball checksum:

```bash
shasum -a 256 rawdog-0.1.0.tar.gz
```

4. Fill in `url`, `sha256`, and Python package resource blocks in
   `packaging/homebrew/rawdog.rb.template`.
5. Rename or copy the completed template to `Formula/rawdog.rb` in the tap.
6. Run Homebrew audit and install checks from the tap checkout:

```bash
brew audit --strict --online rawdog
brew install --build-from-source rawdog
rawdog --help
```

## Notes

Homebrew should install RAWDOG as a local CLI. It should not create daemons,
launch agents, cloud services, accounts, or background sync behavior.
