# pd-vibe

`pd-vibe` is a fork of [`pdpy`](https://github.com/pdpy-org/pdpy) focused on vibe-coding workflows for Pure Data patches.

## Fork Relationship

- This project builds on upstream `pdpy` and keeps compatibility with `pdpy_lib` internals.
- The Python import path is still:

```python
import pdpy_lib as pdpy
```

- New tooling in this fork:
  - `pd2ir`
  - `pdpatch`
  - `pddiff`
  - `pd-docs`
  - `check_docs.py`

## Installation

### From source (recommended right now)

```bash
git clone git@github.com:BorisMolch/pd-vibe.git
cd pd-vibe
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### From PyPI (after first publish)

```bash
pip install pd-vibe
```

## Tool Quickstart

```bash
# Convert patch to IR + DSL
./pd2ir my_patch.pd

# Validate syntax without writing outputs
./pd2ir --validate my_patch.pd

# Safe patch edits
./pdpatch list my_patch.pd -v
./pdpatch add my_patch.pd osc~ 440
./pdpatch connect my_patch.pd 0 1

# Semantic diff (working tree vs HEAD)
./pddiff my_patch.pd

# Docs workflow
./pd-docs init path/to/project
./pd-docs check path/to/project
./pd-docs report path/to/project
./pd-docs html path/to/project

# Hash-based docs freshness check
python check_docs.py path/to/project
```

Git difftool setup for `.pd` files:

```bash
git config diff.pd.command 'pddiff --git-difftool'
echo '*.pd diff=pd' >> .gitattributes
```

## Release Preparation Checklist

1. Validate changed patches: `./pd2ir --validate path/to/changed_patch.pd`
2. Review semantic patch diffs: `./pddiff --summary path/to/changed_patch.pd`
3. Update/check docs status: `./pd-docs report path/to/project`
4. Run test suite: `make test`
5. Build distribution artifacts: `python -m build`

## Current Limitations

- `pdpatch delete` is not implemented yet.
- `pdpatch add` currently targets root canvas only.
- `pd2ir --screenshot` is macOS-only and requires Pd GUI availability.
- `pd-docs check/report/update` require `.pd-docs/refs.json` (created by `pd-docs init`).

## Upstream References

This fork inherits the following references from upstream `pdpy`, and keeps them here for attribution and historical context:

- Pure Data to XML: see [this discussion](https://lists.puredata.info/pipermail/pd-dev/2004-12/003316.html) on the pd-list archives.
- Pure Data to JSON: see [this other one](https://lists.puredata.info/pipermail/pd-dev/2012-06/018434.html) on the pd-list archives.
- Pure Data file format specifications were explained [here](http://puredata.info/docs/developer/PdFileFormat)
- *New* Pd file format [discussion](https://lists.puredata.info/pipermail/pd-dev/2007-09/009483.html) on the pd-list archives.
- `sebpiq`'s repositories: [WebPd_pd-parser](https://github.com/sebpiq/WebPd_pd-parser), as well as [pd-fileutils](https://github.com/sebpiq/pd-fileutils)
- `dylanburati`'s [puredata-compiler](https://github.com/dylanburati/puredata-compiler)

## Copyright

- `pdpy` (upstream fork base): Copyright (C) 2021-2022 Fede Camara Halac and contributors
- [libpd](https://github.com/libpd/libpd): Copyright (c) Peter Brinkmann & the libpd team 2010-2021
- [Pure Data](https://github.com/pure-data/pure-data): Copyright (c) 1997-2021 Miller Puckette and others.
- [pyaudio](https://people.csail.mit.edu/hubert/pyaudio): Copyright (c) 2006 Hubert Pham
