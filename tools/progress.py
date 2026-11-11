#!/usr/bin/env python3
"""Progress figures for the README, computed from config/usa/**/delinks.txt and symbols.txt (+ objdiff).

Two different things are counted, and they are not the same:
  * "linked from our C": a delinks entry marked `complete`. The linker uses the object compiled from our C for it.
  * "matching functions in partial files": a file without `complete` still links the ORIGINAL bytes
    (tools/configure.py), but is compiled so objdiff can compare each function with the game.
    This part needs a build (`ninja objdiff.json`) and is skipped with --no-objdiff.

Usage: python3 tools/progress.py [--no-objdiff] [--json]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cfg = root / "config" / "usa" / "arm9"
modules = [cfg] + [cfg / "itcm", cfg / "dtcm"] + sorted((cfg / "overlays").glob("ov*"))
CODE = {".text", ".init"}  # sections of kind:code


def parse_delinks(path):
    """Returns (module code sections, entries). An entry is (name, complete, [(section, start, end)])."""
    header, entries, cur = [], [], None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            cur = (line.rstrip(":"), False, [])
            entries.append(cur)
            continue
        s = line.split()
        if s[0] == "complete":
            entries[-1] = cur = (cur[0], True, cur[2])
            continue
        m = re.match(r"(\.\w+)\s+start:(0x[0-9a-f]+) end:(0x[0-9a-f]+)", line.strip())
        if m:
            sec = (m[1], int(m[2], 16), int(m[3], 16))
            (header if cur is None else cur[2]).append(sec)
    return header, entries


def functions(path):
    out = []
    for line in path.read_text().splitlines():
        m = re.search(r"kind:function\((?:thumb|arm),size=(0x[0-9a-f]+)\) addr:(0x[0-9a-f]+)", line)
        if m:
            out.append((int(m[2], 16), 0))
    return sorted({a for a, _ in out})


def measure():
    r = dict(entries=0, complete=0, code_total=0, code_complete=0, fn_total=0, fn_complete=0)
    for mod in modules:
        d = mod / "delinks.txt"
        if not d.exists():
            continue
        header, entries = parse_delinks(d)
        fns = functions(mod / "symbols.txt")
        # Code of the module: the code sections of its header (the whole module range).
        r["code_total"] += sum(e - s for n, s, e in header if n in CODE)
        r["fn_total"] += len(fns)
        for name, complete, secs in entries:
            if name.startswith("_dsd_gap") or not secs:
                continue
            r["entries"] += 1
            if not complete:
                continue
            r["complete"] += 1
            code = [(s, e) for n, s, e in secs if n in CODE]
            r["code_complete"] += sum(e - s for s, e in code)
            r["fn_complete"] += sum(1 for a in fns if any(s <= a < e for s, e in code))
    return r


def objdiff_partial():
    if not (root / "objdiff.json").exists():
        sys.exit("objdiff.json missing: run `python3 tools/configure.py usa && ninja partial objdiff.json` first")
    exe = root / "tools" / "bin" / "objdiff-cli"
    out = root / "build" / "progress_report.json"
    subprocess.run([str(exe), "report", "generate", "-p", str(root), "-o", str(out)],
                   capture_output=True, text=True, check=True)
    rep = json.loads(out.read_text())
    n = m = u = 0
    for unit in rep["units"]:
        md = unit["metadata"]
        if md.get("auto_generated") or md.get("complete"):
            continue
        u += 1
        n += int(unit["measures"].get("total_functions", 0))
        m += int(unit["measures"].get("matched_functions", 0))
    return dict(partial_files=u, partial_fn_total=n, partial_fn_matching=m)


def main():
    r = measure()
    if "--no-objdiff" not in sys.argv:
        r.update(objdiff_partial())
    if "--json" in sys.argv:
        print(json.dumps(r, indent=1))
        return
    pc = lambda a, b: f"{100 * a / b:.1f}%"
    print(f"delinks entries (source files): {r['entries']}, complete: {r['complete']}, partial: {r['entries'] - r['complete']}")
    print(f"linked from our C (complete entries): {r['fn_complete']:,} of {r['fn_total']:,} functions, "
          f"{r['code_complete']:,} of {r['code_total']:,} code bytes ({pc(r['code_complete'], r['code_total'])})")
    if "partial_fn_total" in r:
        print(f"functions that match in partial files: {r['partial_fn_matching']:,} of {r['partial_fn_total']:,} "
              f"in {r['partial_files']} files (these still link the original bytes)")


main()
