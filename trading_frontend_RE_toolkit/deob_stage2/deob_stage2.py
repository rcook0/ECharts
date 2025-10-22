
import sys, re, csv
from pathlib import Path
from collections import defaultdict

FUNC_DECL = re.compile(r'^\s*function\s+([A-Za-z_$][\w$]*)\s*\(', re.M)
PROP_FUNC = re.compile(r'([A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\s*=\s*function\s*\(', re.M)
PROTO_FUNC = re.compile(r'([A-Za-z_$][\w$]*\.prototype\.[A-Za-z_$][\w$]*)\s*=\s*function\s*\(', re.M)
CALL_LIKE = re.compile(r'([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(', re.M)

IIFE_START = re.compile(r'\(\s*function\s*\(')

def read_text(p):
    return Path(p).read_text(encoding='utf-8', errors='replace')

def index_iife(text):
    starts = [m.start() for m in IIFE_START.finditer(text)]
    blocks = []
    for i, s in enumerate(starts):
        e = len(text)
        for j in range(i+1, len(starts)):
            e = starts[j]
            break
        blocks.append((s, e))
    return blocks

def linecol(text, pos):
    line = text.count('\n', 0, pos) + 1
    col = pos - (text.rfind('\n', 0, pos) + 1)
    return line, col

def main():
    if len(sys.argv) < 2:
        print("Usage: python deob_stage2.py <pretty_js_dir>")
        sys.exit(1)
    src_dir = Path(sys.argv[1])
    out_dir = Path(__file__).parent

    fun_rows, iife_rows, xref_rows = [], [], []
    callee_counts = defaultdict(int)

    for path in sorted(src_dir.glob("*.pretty.js")):
        text = read_text(path)

        # IIFE blocks
        for bid, (s,e) in enumerate(index_iife(text), start=1):
            sl, sc = linecol(text, s)
            el, ec = linecol(text, e)
            iife_rows.append([path.name, bid, sl, el, e - s])

        # Functions
        for m in FUNC_DECL.finditer(text):
            name = m.group(1)
            ln, col = linecol(text, m.start())
            fun_rows.append([path.name, "decl", name, ln, col])

        for r, kind in [(PROP_FUNC,"prop"), (PROTO_FUNC,"proto")]:
            for m in r.finditer(text):
                name = m.group(1)
                ln, col = linecol(text, m.start())
                fun_rows.append([path.name, kind, name, ln, col])

        # Call-like tokens
        for m in CALL_LIKE.finditer(text):
            callee = m.group(1)
            callee_counts[(path.name, callee)] += 1

    for (fname, callee), cnt in callee_counts.items():
        xref_rows.append([fname, callee, cnt])

    # Write CSVs
    (out_dir / "index_functions.csv").write_text("file,kind,name,line,col\n", encoding="utf-8")
    with open(out_dir / "index_functions.csv", "a", encoding="utf-8") as f:
        for r in fun_rows:
            f.write(",".join(map(lambda x: str(x), r)) + "\n")

    (out_dir / "index_iife.csv").write_text("file,block_id,start_line,end_line,byte_span\n", encoding="utf-8")
    with open(out_dir / "index_iife.csv", "a", encoding="utf-8") as f:
        for r in iife_rows:
            f.write(",".join(map(lambda x: str(x), r)) + "\n")

    (out_dir / "xref_calls.csv").write_text("file,callee,count\n", encoding="utf-8")
    with open(out_dir / "xref_calls.csv", "a", encoding="utf-8") as f:
        for r in xref_rows:
            f.write(",".join(map(lambda x: str(x), r)) + "\n")

    summary = []
    summary.append("# Deob Stage-2 Summary")
    summary.append(f"- Files processed: {len(list(src_dir.glob('*.pretty.js')))}")
    summary.append(f"- Functions indexed: {len(fun_rows)}")
    summary.append(f"- IIFE blocks found: {len(iife_rows)}")
    summary.append(f"- Call-like tokens: {len(xref_rows)}")
    (out_dir / "summary.md").write_text("\\n".join(summary), encoding="utf-8")

if __name__ == "__main__":
    main()
