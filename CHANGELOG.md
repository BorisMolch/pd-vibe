# Changelog

## 2026-02-15

### Fork Baseline Transparency

Baseline comparison: `37dd744` (fork baseline) -> current branch.

- Overall: `24 files changed, 6603 insertions(+), 137 deletions(-)`
- CLI/tooling layer (`pd2ir`, `pdpatch`, `pddiff`, `pd-docs`, `check_docs.py`):
  - `5 files changed, 2339 insertions(+), 10 deletions(-)`
- `pdpy_lib` internals (`pdpy_lib/ir`, `pdpy_lib/objects/obj.py`):
  - `9 files changed, 2500 insertions(+), 104 deletions(-)`

### Notes

- The parser/object engine remains primarily inherited from upstream `pdpy`.
- `pd-vibe` adds a substantial tooling layer and IR/documentation workflow features.
