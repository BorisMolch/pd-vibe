# pd-vibe

`pd-vibe` is a fork of [`pdpy`](https://github.com/pdpy-org/pdpy) focused on vibe-coding workflows for Pure Data patches.

`pd-vibe` builds on the excellent `pdpy` project by Fede Camara Halac and contributors.

## Feature Highlights

- `pd2ir`: convert `.pd` patches into machine-friendly IR JSON + human-friendly DSL.
- `pdpatch`: safe CLI editing for `.pd` files while preserving file structure.
- `pddiff`: semantic diffs for patches (more useful than raw line diffs).
- `pd-docs`: living docs pipeline (`init`, `check`, `report`, `update`, `html`).
- `check_docs.py`: hash-based stale-doc detection for CI and local checks.

## What Comes From pdpy vs What Is New

Reused from upstream `pdpy`:
- Core parser/object model via `pdpy_lib.patching.pdpy.PdPy`
- File loading/parsing helpers in `pdpy_lib.utilities.utils`
- Most of the existing `pdpy_lib` module structure and behavior

New in `pd-vibe`:
- New CLIs: `pdpatch`, `pddiff`, `pd-docs`, `check_docs.py`
- Extended `pd2ir` capabilities (`--indices`, `--annotate`, `--doc`, `--doc-json`, `--state`, `--screenshot`)
- New/extended IR modules in `pdpy_lib/ir` (`docgen`, `state`, `screenshot`, `visualize`, plus DSL/registry/build improvements)
- Additional parser/compatibility fix in `pdpy_lib/objects/obj.py`

Detailed code-change metrics are tracked in [`CHANGELOG.md`](CHANGELOG.md).

Compatibility note:

```python
import pdpy_lib as pdpy
```

The internal import path remains `pdpy_lib` for compatibility.
A future major release may introduce a `pd_vibe_lib` namespace migration.

## Upstream Policy

- `pd-vibe` is not positioned as a replacement for `pdpy`; it has a different product focus.
- General bug fixes and parser improvements should be upstreamed when feasible.
- Product-specific tooling workflows remain in this repository.

## Installation

### From source (recommended)

```bash
git clone git@github.com:BorisMolch/pd-vibe.git
cd pd-vibe
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### From PyPI (after publish)

```bash
pip install pd-vibe
```

## Quickstart

```bash
# Convert patch to IR + DSL
./pd2ir my_patch.pd

# Validate syntax only
./pd2ir --validate my_patch.pd

# Edit safely (root canvas)
./pdpatch list my_patch.pd -v
./pdpatch add my_patch.pd osc~ 440
./pdpatch connect my_patch.pd 0 1

# Semantic diff
./pddiff my_patch.pd

# Docs workflow
./pd-docs init path/to/project
./pd-docs report path/to/project
./pd-docs check path/to/project
./pd-docs html path/to/project

# Hash-based docs freshness check
python check_docs.py path/to/project
```

Git difftool setup for `.pd` files:

```bash
git config diff.pd.command 'pddiff --git-difftool'
echo '*.pd diff=pd' >> .gitattributes
```

## Release Checklist

1. Validate changed patches: `./pd2ir --validate path/to/changed_patch.pd`
2. Review semantic patch diffs: `./pddiff --summary path/to/changed_patch.pd`
3. Review docs drift: `./pd-docs report path/to/project`
4. Run test suite: `make test`
5. Build artifacts: `python -m build`

## Current Limitations

- `pdpatch delete` is not implemented yet.
- `pdpatch add` currently targets root canvas only.
- `pd2ir --screenshot` is macOS-only and requires Pd GUI availability.
- `pd-docs check/report/update` require `.pd-docs/refs.json` (created by `pd-docs init`).

## License

- `pd-vibe` is distributed under GPL terms (see [`LICENSE`](LICENSE)).
- Upstream attribution and copyright notices are preserved.
- Source for fork modifications is provided in this repository.

## Upstream References

This fork inherits the following references from upstream `pdpy` for attribution and historical context:

- Pure Data to XML: see [this discussion](https://lists.puredata.info/pipermail/pd-dev/2004-12/003316.html) on the pd-list archives.
- Pure Data to JSON: see [this other one](https://lists.puredata.info/pipermail/pd-dev/2012-06/018434.html) on the pd-list archives.
- Pure Data file format specifications were explained [here](http://puredata.info/docs/developer/PdFileFormat)
- *New* Pd file format [discussion](https://lists.puredata.info/pipermail/pd-dev/2007-09/009483.html) on the pd-list archives.
- `sebpiq`'s repositories: [WebPd_pd-parser](https://github.com/sebpiq/WebPd_pd-parser), as well as [pd-fileutils](https://github.com/sebpiq/pd-fileutils)
- `dylanburati`'s [puredata-compiler](https://github.com/dylanburati/puredata-compiler)

## Copyright

- [pdpy](https://github.com/pdpy-org/pdpy) (upstream fork base): Copyright (C) 2021-2022 Fede Camara Halac and contributors
- [libpd](https://github.com/libpd/libpd): Copyright (c) Peter Brinkmann & the libpd team 2010-2021
- [Pure Data](https://github.com/pure-data/pure-data): Copyright (c) 1997-2021 Miller Puckette and others.
- [pyaudio](https://people.csail.mit.edu/hubert/pyaudio): Copyright (c) 2006 Hubert Pham
