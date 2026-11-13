#!/usr/bin/env python3
"""Prints an mwcc `asm` function body for a game function, for functions that are decompiled but don't match yet.

Usage: python3 tools/asm_fallback.py <function name or 0xADDRESS>
Reads build/asm (run `tools/bin/dsd dis -c config/usa/arm9/config.yaml -a build/asm --ual --main` first).

ARM: converts dsd's UAL syntax to the pre-UAL syntax mwcc's inline assembler accepts (push/pop -> stmdb/ldmia,
lsl/lsr/asr/ror -> mov with a shifted operand, condition code after the load/store size, ...).
Thumb: detected from the dsd directives (.thumb, thumb_func_start, .code 16) or, failing that, from
`kind:function(thumb` in config/**/symbols.txt. The body is passed through unconverted (mwcc's Thumb assembler takes
push/pop/lsl as written) and the header says to compile it in Thumb mode (the project default; `#pragma thumb on` in a
file that has `#pragma thumb off`). The Thumb output has not been assembled with mwcc here.
Literal pools: `ldr rX, .L_pool` with a `.L_pool: .word sym` entry becomes `ldr rX, =sym` (mwcc puts the pool at the
end of the function, like the originals). Data that is not loaded that way (jump tables, unreferenced words, bytes)
stays in place as `dcd`/`dcw`/`dcb` with its label, so a pool never makes the tool give up.
Calls to C++ functions and references to symbols need declarations in scope; mangled names need an `extern "C"`
declaration. The names used are printed as a comment.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COND = r"(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?"
DATA = {"word": "dcd", "short": "dcw", "byte": "dcb"}
THUMB_MARKERS = (".thumb", "thumb_func", ".code 16")
ARM_MARKERS = (".arm", "arm_func", ".code 32")
DIRECTIVES = (".thumb", ".arm", "thumb_func", "arm_func", ".code", ".global", ".type", ".align", ".text", ".section")


def find(target: str) -> list[str]:
    for path in sorted((ROOT / "build/asm").rglob("*.s")):
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"^(\S+): ; (0x[0-9a-f]+)$", line)
            if m and target in (m.group(1), m.group(2)):
                body = []
                for l in lines[i + 1:]:
                    if re.match(r"^\S+: ; 0x", l) or "_func_end" in l:
                        break
                    body.append(l)
                return body
    sys.exit(f"{target} not found in build/asm")


def is_thumb(target: str, raw: list[str]) -> bool:
    stripped = [l.strip() for l in raw]
    if any(l.startswith(THUMB_MARKERS) for l in stripped):
        return True
    if any(l.startswith(ARM_MARKERS) for l in stripped):
        return False
    for path in ROOT.glob("config/**/symbols.txt"):
        for l in path.read_text().splitlines():
            m = re.match(r"^(\S+) kind:function\((\w+)[^)]*\) addr:0x0*([0-9a-fA-F]+)", l)
            if m and (target == m.group(1) or target.lower().replace("0x", "").lstrip("0") == m.group(3).lower()):
                return m.group(2) == "thumb"
    return False


def data_line(s: str) -> str | None:
    """`.L_x: .word v` / `.word v` -> `L_x: dcd v` (None if the line isn't data)."""
    m = re.match(r"^(?:\.L_(\w+): )?\.(word|short|byte)\s+(.*)$", s)
    if not m:
        return None
    label = f"L_{m.group(1)}: " if m.group(1) else ""
    return f"{label}{DATA[m.group(2)]} {m.group(3).replace('.L_', 'L_')}"


def convert(line: str) -> str:
    s = line.split(";")[0].strip()
    d = data_line(s)
    if d:
        return d
    s = s.replace(".L_", "L_")
    if re.match(r"^\w+:$", s):
        return s
    m = re.match(rf"^push{COND} \{{(.*)\}}$", s)
    if m:
        return f"stm{m.group(1) or ''}db sp!, {{{m.group(2)}}}"
    m = re.match(rf"^pop{COND} \{{(.*)\}}$", s)
    if m:
        return f"ldm{m.group(1) or ''}ia sp!, {{{m.group(2)}}}"
    m = re.match(rf"^(lsl|lsr|asr|ror){COND}(s?) (\w+), (\w+), (#?\w+)$", s)
    if m:
        op, cond, flag, rd, rm, amount = m.groups()
        return f"mov{cond or ''}{flag} {rd}, {rm}, {op} {amount}"
    m = re.match(rf"^(ldr|str)(sb|sh|b|h){COND} (.*)$", s)
    if m:
        return f"{m.group(1)}{m.group(3) or ''}{m.group(2)} {m.group(4)}"
    m = re.match(rf"^(stm|ldm){COND} (\w+!?), (.*)$", s)
    if m:
        return f"{m.group(1)}{m.group(2) or ''}ia {m.group(3)}, {m.group(4)}"
    return s


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    raw = [l for l in find(sys.argv[1]) if l.strip()]
    thumb = is_thumb(sys.argv[1], raw)
    raw = [l for l in raw if not l.strip().startswith(DIRECTIVES)]
    pool = {}
    used = set()
    for l in raw:
        m = re.match(r"^\.L_(\w+): \.word (\S+)$", l.strip())
        if m:
            pool[m.group(1)] = m.group(2)
        m = re.match(r"^\s*ldr\w* \w+, \.L_(\w+)$", l)
        if m:
            used.add(m.group(1))
    lines = []
    for l in raw:
        m = re.match(r"^\.L_(\w+): \.word ", l.strip())
        if m and m.group(1) in used:
            continue  # folded into `ldr rX, =value`
        m = re.match(r"^(\s*ldr\w* \w+), \.L_(\w+)$", l)
        if m and m.group(2) in pool:
            l = f"{m.group(1)}, ={pool[m.group(2)]}"
        lines.append(l)
    if thumb:
        body = [data_line(l.strip()) or l.split(";")[0].strip().replace(".L_", "L_") for l in lines]
    else:
        body = [convert(l) for l in lines]
    ident = re.compile(r"^[A-Za-z_]\w*$")
    calls = sorted({l.split()[1] for l in body if re.match(r"^blx? \w", l)} | {v for v in pool.values() if ident.match(v)})
    if calls:
        print(f"// uses: {', '.join(calls)}")
    print("// Thumb function: compile in Thumb mode (project default; `#pragma thumb on` in a `thumb off` file)" if thumb
          else "// ARM function: needs `#pragma thumb off` in a Thumb file")
    print("    nofralloc")
    for l in body:
        if l:
            print(l if re.match(r"^\w+:(\s|$)", l) else f"    {l}")


if __name__ == "__main__":
    main()
