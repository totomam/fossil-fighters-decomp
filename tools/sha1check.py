#!/usr/bin/env python3
"""`shasum -c` replacement (FF1-03): verify '<sha1>  <path>' lines with hashlib; exit 1 on mismatch/missing."""
import hashlib, sys

def main(argv):
    bad = 0
    for lst in argv[1:]:
        for line in open(lst):
            line = line.strip()
            if not line:
                continue
            want, path = line.split(None, 1)
            path = path.lstrip("*")
            try:
                got = hashlib.sha1(open(path, "rb").read()).hexdigest()
            except OSError as e:
                print(f"{path}: FAILED open ({e.strerror})"); bad += 1; continue
            ok = got == want.lower()
            print(f"{path}: {'OK' if ok else 'FAILED'}")
            bad += not ok
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
