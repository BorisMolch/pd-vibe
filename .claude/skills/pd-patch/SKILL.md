---
name: pd-patch
description: Pure Data (Pd) patch analysis and editing. Use when working with .pd files, analyzing audio/visual patches, understanding signal flow, or modifying Pure Data patches. Triggers on .pd file references, Pd object questions, or audio DSP patching tasks.
---

# Pure Data Patch Assistant

Analyze and edit Pure Data (.pd) patches using the IR (Intermediate Representation) system for semantic understanding.

## Quick Start

### Analyze a patch
```bash
/Users/borismo/pdpy/pd2ir <file.pd>
# Generates: file.pd-ir.json, file.pd-ir.dsl
```

### Generate SVG diagram
```bash
/Users/borismo/pdpy/pd2ir --svg <file.pd>
# Generates: file.pd.svg (visual diagram of patch)
```

### Take screenshot using Pd (macOS)
```bash
/Users/borismo/pdpy/pd2ir --screenshot <file.pd>
# Generates: file.pd.png (actual Pd rendering)
# Requires Pure Data installed, opens/closes Pd automatically
```

### Generate documentation for an abstraction
```bash
/Users/borismo/pdpy/pd2ir --doc <file.pd>        # Markdown: file.pd-doc.md
/Users/borismo/pdpy/pd2ir --doc-json <file.pd>   # JSON: file.pd-doc.json
```

### Watch for changes
```bash
/Users/borismo/pdpy/pd2ir --watch <file.pd>
```

## Understanding the DSL Format

The `.pd-ir.dsl` file is the semantic representation of a patch. Key sections:

### Node Format
```
canvas_path::node_id: object_type args...
```
- `c0` = main canvas
- `c0/c1` = first subpatch inside main
- `c0/c1/c2` = nested subpatch

### Subpatches
Marked with comments:
```
# subpatch-name
c0/c1::node_id: object_type
```

### Signal vs Control
- Signal objects end with `~`: `osc~`, `dac~`, `*~`
- Control objects: `route`, `sel`, `pack`

### Symbols (Wireless Connections)
```
symbol-name (global): w[writers] r[readers]
```
- `s symbol-name` = send (writer)
- `r symbol-name` = receive (reader)
- `throw~`/`catch~` = signal send/receive
- `w[]` = orphan (no writer)
- `r[]` = orphan (no reader)

### Wires
```
source_node:outlet -> dest_node:inlet
```

### Cycles
Feedback loops detected:
```
cycles: [node1,node2,node3]
```

## Common Pd Objects

### Audio I/O
- `adc~` - audio input
- `dac~` - audio output
- `inlet~`/`outlet~` - subpatch signal ports

### Oscillators
- `osc~` - sine wave
- `phasor~` - sawtooth/ramp
- `noise~` - white noise

### Math (Signal)
- `*~`, `+~`, `-~`, `/~` - arithmetic
- `clip~` - limit range
- `wrap~` - wrap to 0-1

### Filters
- `lop~` - lowpass
- `hip~` - highpass
- `bp~` - bandpass
- `vcf~` - voltage-controlled filter

### Control
- `metro` - periodic bangs
- `counter` - count bangs
- `sel` - select/route by value
- `route` - route by first element
- `pack`/`unpack` - combine/split lists

### Delay
- `delwrite~`/`delread~` - signal delay
- `vd~` - variable delay (interpolated)
- `delay`/`pipe` - control delay

### Send/Receive
- `s`/`r` - control send/receive
- `throw~`/`catch~` - signal send/receive (summing)
- `send~`/`receive~` - signal send/receive (non-summing)

## Editing Patches

### .pd File Format
```
#N canvas x y width height name;
#X obj x y objectname args...;
#X msg x y message content;
#X connect source_obj source_outlet dest_obj dest_inlet;
```

### Adding an Object
```
#X obj 100 200 osc~ 440;
```

### Adding a Connection
```
#X connect 0 0 1 0;
```
(connect object 0's outlet 0 to object 1's inlet 0)

### Object Index Counting (CRITICAL)

Pd counts objects using sequential indices. **This is the trickiest part of editing .pd files.**

**What to count (creates canvas items):**
- `#X obj` - objects
- `#X msg` - messages
- `#X text` - comments (COUNTS AS OBJECT!)
- `#X floatatom` - number boxes
- `#X symbolatom` - symbol boxes
- `#X array` - arrays

**What NOT to count:**
- `#N canvas` - canvas/subpatch headers
- `#X restore` - subpatch close
- `#X connect` - connections
- `#X coords` - GOP settings

**Example with text comment:**
```
#N canvas 0 0 400 300 10;       <- NOT counted (canvas header)
#X obj 50 50 inlet;             <- index 0
#X obj 50 100 + 1;              <- index 1
#X text 150 100 this adds one;  <- index 2 (comment COUNTS!)
#X obj 50 150 outlet;           <- index 3
#X connect 0 0 1 0;             <- inlet(0) -> +(1)
#X connect 1 0 3 0;             <- +(1) -> outlet(3), NOT 2!
```

**Common mistake:** Ignoring `#X text` and thinking outlet is index 2. The connection `#X connect 1 0 2 0` would connect to the comment (broken patch).

**Subpatch scoping:**
- Inside `#N canvas ... #X restore`, indices reset for that subpatch
- The outer patch sees the entire subpatch block as ONE object
- Each `#N canvas ... #X restore` block counts as 1 object in parent scope

**Example with subpatch:**
```
#N canvas 0 0 500 400 main;     <- canvas header, not counted
#X obj 50 50 osc~ 440;          <- index 0 (in main)
#N canvas 100 100 300 200 sub;  <- subpatch header, not counted
#X obj 20 20 inlet~;            <- index 0 (in subpatch)
#X obj 20 60 *~ 0.5;            <- index 1 (in subpatch)
#X obj 20 100 outlet~;          <- index 2 (in subpatch)
#X connect 0 0 1 0;             <- connects inlet~ to *~ (within subpatch)
#X connect 1 0 2 0;             <- connects *~ to outlet~ (within subpatch)
#X restore 100 100 pd sub;      <- counts as index 1 in main canvas
#X obj 50 150 dac~;             <- index 2 (in main)
#X connect 0 0 1 0;             <- connects osc~ to subpatch (main scope)
#X connect 1 0 2 0;             <- connects subpatch to dac~ (main scope)
```

**Finding object indices:**
1. Count from the top of the relevant scope
2. For objects inside a subpatch, count from after `#N canvas`
3. For connections, use the index within the same scope as the `#X connect`

### Quick Validation

Validate a .pd file syntax without generating output files:
```bash
/Users/borismo/pdpy/pd2ir --validate <file.pd>
```

Or generate only IR (skip slower DSL generation):
```bash
/Users/borismo/pdpy/pd2ir --no-dsl <file.pd>
```

### Annotated DSL output

Add semantic annotations (parameter meanings, units) to the DSL:
```bash
/Users/borismo/pdpy/pd2ir -a <file.pd>
```

Example annotated output:
```
c0::h60eed844: osc~ 440  # 440=oscillator frequency [Hz]
c0::hdbab8f31: lop~ 1000  # 1000=cutoff frequency [Hz]
c0::hd2d0b3ee: *~ 0.5  # 0.5=multiplication factor (often amplitude 0-1)
```

### Finding Objects by Position

When editing, you can find objects by their x,y coordinates in the file:
```bash
grep "#X obj 100 200" file.pd  # Find object at position (100, 200)
```

This is useful when you know where something is visually but not its index.

## Workflow

### Understanding a patch
1. **Generate DSL**: `pd2ir patch.pd` for semantic structure
2. **Read the DSL**: Nodes, wires, symbols sections show full structure
3. **Check symbols**: Look for orphaned send/receives
4. **Trace specific paths**: Follow `~` objects from input to output

### Editing a patch
1. **Generate DSL**: `pd2ir patch.pd` to see structure
2. **Edit .pd file**: Make changes to the raw file
3. **Re-analyze**: Run `pd2ir` again to verify
4. **Compare changes**: Use `pddiff` to see semantic diff

## Abstraction Documentation Generator

The `--doc` flag auto-generates documentation for Pd abstractions by analyzing `$N` argument usage patterns.

### What it detects
- **Arguments**: Finds all `$1`, `$2`, etc. references and infers their type (symbol/number) and purpose
- **Interface**: Lists inlets/outlets with domain (signal/control)
- **Exposed symbols**: Send/receive symbols containing `$N` references
- **Manual docs**: Parses comments with `$N: description` pattern

### Example output (Markdown)
```markdown
# myAbstraction

## Arguments

| # | Name | Type | Description |
|---|------|------|-------------|
| $1 | name | symbol | identifier prefix for send/receive |
| $2 | count | number | instance count |

## Interface

- inlet 0 (signal): signal input
- outlet 0 (signal): signal output

## Symbols
Sends: $1-velocity
Receives: $1Touch
```

### Adding manual documentation to patches
Add comments in your .pd file following this pattern:
```
#X text 10 10 \$1: track name \, \$2: voice count;
```

The generator will extract these descriptions and include them in the output.

## Comparing Patches (Git Diff)

The `pddiff` tool provides semantic diffs for .pd files by converting to DSL first.

### Basic usage
```bash
/Users/borismo/pdpy/pddiff file.pd                     # Working tree vs HEAD
/Users/borismo/pdpy/pddiff file.pd HEAD~1              # Working tree vs previous commit
/Users/borismo/pdpy/pddiff file.pd HEAD~3 HEAD         # Compare two commits
/Users/borismo/pdpy/pddiff --staged file.pd            # Staged vs HEAD
/Users/borismo/pdpy/pddiff --summary *.pd              # Summary only (no full diff)
```

### Example output
```
============================================================
Semantic diff: synth.pd
============================================================

Summary: +5 -2 lines
Changes: Nodes: +2 -1, Wires: +3 -1

--- a/synth.pd (HEAD~1)
+++ b/synth.pd (HEAD)
@@ -12,6 +12,8 @@
 c0::n5: *~ 0.5
+c0::n6: lop~ 1000
+c0::n7: hip~ 20

 wires:
-n5:0 -> dac~:0
+n5:0 -> n6:0 -> n7:0 -> dac~:0
```

### Git integration
Configure git to use pddiff automatically for .pd files:
```bash
git config diff.pd.command '/Users/borismo/pdpy/pddiff --git-difftool'
echo '*.pd diff=pd' >> .gitattributes
```

Then `git diff` will show semantic diffs for .pd files.

## Resources

- pd2ir tool: `/Users/borismo/pdpy/pd2ir`
- pddiff tool: `/Users/borismo/pdpy/pddiff`
- Object registry: `/Users/borismo/pdpy/data/objects.vanilla.json`
- IR module: `/Users/borismo/pdpy/pdpy_lib/ir/`
- Docgen module: `/Users/borismo/pdpy/pdpy_lib/ir/docgen.py`
