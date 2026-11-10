#!/usr/bin/env python3
"""Progress figures from config/usa/**/delinks.txt + symbols.txt (FFC-DECOMP audit FF1-01). Prints the README lines.

  python3 tools/progress_stats.py

"linked from our C" = delinks files marked `complete` (their .text/.init are compiled and linked; checked byte-for-byte).
"partial" = source files not marked complete: the build links the ORIGINAL bytes for them (tools/configure.py) and only
compiles them so objdiff can count matching functions (`ninja objdiff.json`, then objdiff). Those per-function matches
are not tracked here."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = (".text", ".init")
SEC = re.compile(r"\s+(\.\w+)\s+start:0x([0-9a-f]+)\s+end:0x([0-9a-f]+)(.*)")


def module(d: Path):
    total, files, cur = 0, [], None
    for line in (d / "delinks.txt").read_text().splitlines():
        m = SEC.match(line)
        if m:
            name, a, b, rest = m[1], int(m[2], 16), int(m[3], 16), m[4]
            if cur is None:
                total += (b - a) if "kind:code" in rest else 0
            elif name in CODE:
                cur["code"].append((a, b))
        elif line.strip() == "complete" and cur is not None:
            cur["complete"] = True
        elif line.endswith(":") and not line.startswith(" "):
            cur = {"name": line[:-1], "code": [], "complete": False}
            files.append(cur)
    funcs = []
    for line in (d / "symbols.txt").read_text().splitlines():
        m = re.search(r"kind:function\(\w+,size=0x([0-9a-f]+)\) addr:0x([0-9a-f]+)", line)
        if m:
            funcs.append(int(m[2], 16))
    return total, files, funcs


def main():
    base = ROOT / "config" / "usa" / "arm9"
    dirs = [base, base / "itcm"] + sorted(p for p in (base / "overlays").iterdir() if p.is_dir())
    tot = cb = pb = cf = pf = nf = ncomplete = npartial = 0
    for d in dirs:
        if not (d / "delinks.txt").exists():
            continue
        t, files, funcs = module(d)
        tot += t
        nf += len(funcs)
        for f in files:
            if not f["code"]:
                continue
            n = sum(b - a for a, b in f["code"])
            k = sum(1 for x in funcs if any(a <= x < b for a, b in f["code"]))
            src = (ROOT / f["name"]).is_file()
            if f["complete"]:
                cb += n; cf += k; ncomplete += 1
            elif src:
                pb += n; pf += k; npartial += 1
    marks = sum(p.read_text(errors="replace").count("NONMATCHING") for p in ROOT.glob("src/**/*") if p.is_file()) + \
        sum(p.read_text(errors="replace").count("NONMATCHING") for p in ROOT.glob("libs/**/*") if p.is_file() and p.suffix in (".c", ".cpp", ".h"))
    print(f"functions (symbols.txt): {nf:,}; code bytes (delinks kind:code): {tot:,}")
    print(f"linked from our C (complete files): {ncomplete} files, {cf:,} functions, {cb:,} bytes ({100 * cb / tot:.1f}%)")
    print(f"partial source files (original bytes linked): {npartial} files, {pf:,} functions, {pb:,} bytes; {marks} NONMATCHING markers")


if __name__ == "__main__":
    main()
