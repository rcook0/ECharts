
# Stage-2 Deobfuscation (Heuristic)

This recovers structure from minified bundles — module boundaries, function/property assignments,
and a lightweight cross-reference — without external JS tooling.

## Outputs
- `index_functions.csv` — file, kind, name, line, col
- `index_iife.csv` — file, block_id, start_line, end_line, byte_span
- `xref_calls.csv` — file, callee_string, count
- `summary.md`

## Run
```bash
python deob_stage2.py ../reverse_eng_report/pretty_js
```
