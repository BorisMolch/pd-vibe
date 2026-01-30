# Pure Data DSL Reference

## DSL File Structure

```
patch <name>

<nodes section>
<chains~ section>
<wires section>
<symbols section>
<cycles section>
```

## Node ID Format

Node IDs encode semantic meaning:

### Semantic Anchors (highest priority)
- `r:symbol:domain` - receive object
- `s:symbol:domain` - send object
- `catch~:symbol:signal` - signal catch
- `throw~:symbol:signal` - signal throw
- `inlet#N` / `outlet#N` - interface nodes
- `table:name:domain` - named table
- `array:size:domain` - array with size

### Hash-based IDs (fallback)
- `h` + 8-char hash - computed from connections and args
- `#N` suffix for disambiguation when needed

## Domain Types

- `signal` - audio rate (`~` objects)
- `control` - message rate
- `unknown` - not determined

## Symbol Entry Format

```
name (scope): w[writers] r[readers]
```

- `scope`: `global` or `local` (subpatch-scoped)
- `writers`: nodes that send to this symbol
- `readers`: nodes that receive from this symbol

### Orphan Detection
- `w[]` - no writers (external input expected)
- `r[]` - no readers (output goes nowhere)

## Wire Format

```
source_id:outlet -> dest_id:inlet [-> next:inlet ...]
```

Chains show connected paths for easier tracing.

## Signal Chain Format

```
chains~:
  node1:type(args) -> node2:type(args) -> node3:type
```

Linear signal paths collapsed for readability.

## Canvas Hierarchy

```
c0 = root canvas
c0/c1 = first subpatch
c0/c1/c2 = nested subpatch
c0/c3 = second subpatch at root level
```

## JSON IR Schema

```json
{
  "version": "0.1",
  "source": "file.pd",
  "canvases": [...],
  "nodes": [...],
  "edges": [...],
  "symbols": {...}
}
```

### Node Schema
```json
{
  "id": "string",
  "canvas": "string",
  "kind": "object|message|gui|subpatch|comment",
  "type": "string",
  "args": ["..."],
  "domain": "signal|control|unknown",
  "io": {"inlets": N, "outlets": N}
}
```

### Edge Schema
```json
{
  "id": "string",
  "source": "node_id",
  "target": "node_id",
  "source_port": N,
  "target_port": N,
  "kind": "wire|symbol"
}
```
