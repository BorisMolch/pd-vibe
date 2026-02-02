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

### Analyze stateful elements (debugging audio bleed)
```bash
/Users/borismo/pdpy/pd2ir --state <file.pd>
```

Shows delay buffers, feedback loops, tables, and how to silence them:
```
## Delay Buffers
- **mydelay** (500ms)
  - Feedback: `c0::hd2d0b3ee` (gain: 0.5)
  - **To silence:** Set `c0::hd2d0b3ee` to 0, then `; mydelay const 0`

## Silence Sequence
1. Set `c0::hd2d0b3ee` to 0 (kill feedback)
2. Wait ~10ms for buffers to drain
3. `; mydelay const 0`
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

### Message Syntax

**Basic messages:**
```
#X msg 100 100 bang;           # sends "bang"
#X msg 100 100 440;            # sends number 440
#X msg 100 100 set \$1;        # sends "set" + first inlet value
```

**Semicolon (;) sends to named receivers:**
```
#X msg 100 100 \; pd dsp 1;           # turn on DSP
#X msg 100 100 \; pd dsp 0;           # turn off DSP
#X msg 100 100 \; myarray const 0;    # zero out array "myarray"
#X msg 100 100 \; myarray resize 44100;  # resize array
#X msg 100 100 \; myvalue 0.5;        # send 0.5 to [r myvalue]
```

**Multiple commands in one message:**
```
#X msg 100 100 \; array1 const 0 \; array2 const 0;  # zero two arrays
```

**Dollar signs ($) in messages vs comments:**
- In messages: `\$1` = argument substitution (becomes value of inlet)
- In comments: `\$1` = literal text for documentation
```
#X msg 100 100 set \$1 \$2;           # substitutes inlet values
#X text 100 100 \$1: track name;      # literal "$1:" for docs
```

**Common array operations:**
```
\; arrayname const 0       # fill with zeros
\; arrayname resize N      # resize to N samples
\; arrayname normalize 1   # normalize to peak of 1
\; arrayname sinesum N 1 0.5 0.25  # fill with harmonics
```

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

### DSL with object indices (for editing)

Show .pd file object indices in DSL output - essential for adding connections:
```bash
/Users/borismo/pdpy/pd2ir -i <file.pd>
```

Example output with indices:
```
c0::h60eed844[0]: osc~ 440
c0::hdbab8f31[3]: lop~ 1000
c0::hd2d0b3ee[5]: *~ 0.5
```

The `[N]` suffix is the object index used in `#X connect` statements. To connect osc~ to lop~:
```
#X connect 0 0 3 0;  # osc~ outlet 0 -> lop~ inlet 0
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

## Common Pitfalls

### Audio bleeding after stop

**Problem:** Audio continues playing after you "stop" a patch.

**Cause:** Stateful elements retain audio:
- **Delay buffers** (`delwrite~`) keep their contents
- **Feedback loops** (`*~ 0.85` feeding back to `delwrite~`) recirculate audio
- **Sample tables** keep loaded audio

**Solution:** Kill feedback FIRST, then clear buffers:
```
1. Set feedback multiplier to 0:  \; feedback-gain 0
2. Wait one buffer cycle (~10ms)
3. Zero the delay buffer:  \; delaybuffer const 0
```

If you clear the buffer while feedback is active, the feedback loop immediately refills it.

### Feedback loop detection

When DSL shows `cycles:`, you have a feedback loop. Example:
```
cycles: [delwrite~:buff,vd~:buff,*~]
```

This means: `delwrite~` → `vd~` reads it → `*~` scales it → back to `delwrite~`

**Safe feedback:** The `*~` multiplier should be < 1.0 (e.g., 0.85) or signal grows infinitely.

**To silence:** The multiplier node is your kill switch. Set it to 0 before clearing buffers.

### $0 vs $1 confusion

- `$0` = **unique instance ID** (different for each patch copy) - use for internal send/receive
- `$1`, `$2`, etc. = **creation arguments** passed when instantiating the abstraction

```
[mysynth foo 440]  ->  $1=foo, $2=440, $0=1001 (unique)
[mysynth bar 880]  ->  $1=bar, $2=880, $0=1002 (different!)
```

Use `$0-` prefix for internal communication that shouldn't leak between instances:
```
[s $0-internal]  # only this instance receives
[s $1-output]    # shared based on argument
```

### Hot vs cold inlets

Most Pd objects only trigger output when the **left (hot) inlet** receives a message:
- Hot inlet (leftmost): triggers computation
- Cold inlets: store value for next computation

```
[+ ]
 |  \
hot  cold

Sending to cold inlet stores the value but doesn't output anything.
Sending to hot inlet adds stored value and outputs result.
```

**Common mistake:** Sending to both inlets simultaneously via `[t b b]` - order matters! Right-to-left execution means cold inlet gets set first.

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

## Programmatic Patch Editing (pdpatch)

The `pdpatch` CLI provides safe programmatic patch editing using text-based manipulation that preserves file structure exactly.

### Create and build a patch
```bash
/Users/borismo/pdpy/pdpatch new synth.pd              # Create empty patch
/Users/borismo/pdpy/pdpatch add synth.pd osc~ 440     # Add oscillator
/Users/borismo/pdpy/pdpatch add synth.pd '*~' 0.5     # Add multiplier (quote *~)
/Users/borismo/pdpy/pdpatch add synth.pd dac~         # Add audio output
/Users/borismo/pdpy/pdpatch connect synth.pd 0 1      # Connect by index
/Users/borismo/pdpy/pdpatch connect synth.pd 1 2      # Connect multiplier to dac~
```

### List objects and connections
```bash
/Users/borismo/pdpy/pdpatch list synth.pd
# Objects in synth.pd:
#   [0] osc~ 440
#   [1] *~ 0.5
#   [2] dac~
# Connections:
#   [0]:0 -> [1]:0
#   [1]:0 -> [2]:0

/Users/borismo/pdpy/pdpatch list synth.pd -v   # With inlet/outlet counts
```

### Connecting objects
```bash
/Users/borismo/pdpy/pdpatch connect synth.pd 0 1              # Default: outlet 0 -> inlet 0
/Users/borismo/pdpy/pdpatch connect synth.pd 0 1 -o 1 -i 0    # Specify ports
```

### How pdpatch works

pdpatch uses **text-based editing** that:
- Preserves file structure exactly (no reordering)
- Correctly counts comments (`#X text`) as objects
- Inserts new objects before the first `#X connect`
- Appends connections at the end of the file
- Validates inlet/outlet counts before connecting

### Limitations

- **Delete not implemented** - edit .pd file directly to delete objects
- **Subpatch add not implemented** - only lists subpatch contents
- **No type-based lookup** - use indices from `pdpatch list`

For complex edits, use direct .pd editing with `pd2ir -i` for indices.

## Common Synth Patterns

### ADSR Envelope Pattern
```
[trigger] -> [t b b] -> [del $1] (retrigger delay)
                    -> [vline~] -> [*~] (VCA)
```
**Critical:** The `[del]` must be stopped on retrigger to prevent double-triggers:
```
[t b b] -> [0, stop( -> [del 10]
        -> [attack, decay, sustain( -> [vline~]
```

### VCA (Voltage-Controlled Amplifier)
```
[osc~] -> [*~] -> [dac~]
           ^
      [envelope]
```
**Anti-pattern:** VCA with constant gain (no envelope input):
```
[osc~] -> [*~ 0.5] -> [dac~]  # No volume control!
```
If audio bleeds, check that the `*~` multiplier receives envelope modulation.

### Retrigger-Safe Envelope
```
#X obj 50 50 inlet;
#X obj 50 90 t b b;
#X msg 150 90 stop;
#X obj 50 130 del 10;
#X msg 50 170 1 10 \, 0.7 50 \, 0 200;
#X obj 50 210 vline~;
#X obj 50 250 outlet~;
#X connect 0 0 1 0;
#X connect 1 0 3 0;
#X connect 1 1 2 0;
#X connect 2 0 3 0;
#X connect 3 0 4 0;
#X connect 4 0 5 0;
#X connect 5 0 6 0;
```
The `[t b b]` sends a bang to `[del]` AND sends "stop" to cancel any pending delay.

### Debugging Audio Bleed

1. **Check state elements:** `pd2ir --state patch.pd`
2. **Trace signal paths:** Look for `*~` objects without envelope input
3. **Kill feedback first:** Set multipliers to 0 before clearing buffers
4. **Check retrigger logic:** `[del]` without `stop` causes double-triggers

## Project Documentation (pd-docs)

The `pd-docs` tool maintains living documentation for Pd projects with smart code-to-doc linking.

### Initialize documentation
```bash
/Users/borismo/pdpy/pd2ir --doc externals/myAbstraction.pd   # Single file
/Users/borismo/pdpy/pd2ir --doc externals/                   # Batch mode
```
Generates markdown files alongside .pd files with:
- Argument documentation (inferred from `$N` usage patterns)
- Inlet/outlet interface descriptions
- Send/receive symbol references
- Dependency chains

### Documentation linking

Generated docs include metadata comments for tracking:
```markdown
<!-- pd-docs: /path/to/source.pd -->
<!-- generated: 2026-02-01T20:06:15 -->
```

### Check for stale documentation
```bash
python /Users/borismo/pdpy/check_docs.py /path/to/docs/      # Basic check
python /Users/borismo/pdpy/check_docs.py /path/to/docs/ -v   # Verbose
```

**Output:**
```
Documentation Status: /path/to/docs/
==================================================

STALE (2 files - source changed):
   sampler~.md
   clock.md

MISSING SOURCE (1 files):
   old_module.md -> /path/to/old_module.pd

OK: 85 files up-to-date
```

The script compares timestamps between documentation and source .pd files.

### Update workflow (for Claude)

After editing a .pd file:
1. Run `check_docs.py` to see what's stale
2. Re-generate with `pd2ir --doc <changed-file.pd>`
3. Review and enhance the generated documentation

### Jambl-Pd Documentation

The Jambl-Pd project has comprehensive documentation at `/Users/borismo/Jambl-iOS/Jambl-Pd/docs/`:
- **88+ documented abstractions** covering samplers, effects, grooves, loaders
- **System architecture** in `index.md` with signal flow diagrams
- **Dependency tracking** (Used By / Dependencies sections)

Key subsystems documented:
- Sampler hierarchy: `polysampler~` → `sampler-voice~` → `sampler~`
- Groove system: `groove~` → `grooveLoader` → `grooveRegion`
- Recording: `recordingBuffer`, `tapBuffer`, `recorder`
- Effects: `vfreeverb_`, `compressor~`, `3eq~`

### Current limitations

- **No hash-based change detection**: Uses timestamps only
- **No dependency-aware flagging**: Changing `sampler~.pd` won't automatically flag `polysampler~.md` as needing review
- **Manual re-generation required**: No auto-sync on file save

## Resources

- pd2ir tool: `/Users/borismo/pdpy/pd2ir`
- pddiff tool: `/Users/borismo/pdpy/pddiff`
- pdpatch tool: `/Users/borismo/pdpy/pdpatch`
- pd-docs tool: `/Users/borismo/pdpy/pd-docs`
- Object registry: `/Users/borismo/pdpy/data/objects.vanilla.json`
- IR module: `/Users/borismo/pdpy/pdpy_lib/ir/`
- Docgen module: `/Users/borismo/pdpy/pdpy_lib/ir/docgen.py`
- State analysis: `/Users/borismo/pdpy/pdpy_lib/ir/state.py`
