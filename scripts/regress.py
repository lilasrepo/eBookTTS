# -*- coding: utf-8 -*-
"""One-command regression gate for the biblio engine.

Rebuilds every book under book/, verifies it, and asserts every out/*.md is
BYTE-IDENTICAL to a frozen golden (sha256 in book/_regress/golden.json) and that
verify's totals are unchanged: any UNINTENDED output change FAILS the suite; an
INTENTIONAL change is re-blessed with --freeze. Run this before/after any engine
edit -- it is the safety rail that lets the engine evolve without silent breakage.

BOOKS is auto-discovered from the book/ dirs present in this checkout (any dir with
a book.json), so it works whether you have just the bundled fixture or many books.

Usage:
  python -X utf8 scripts/regress.py            # check; exit 1 on any drift
  python -X utf8 scripts/regress.py --freeze   # re-bless current output as golden
  python -X utf8 scripts/regress.py --only sample
A book whose source/ is absent (sparse checkout) is SKIPPED, not failed.
"""
import argparse
import contextlib
import glob
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GOLDEN = os.path.join(ROOT, "book", "_regress", "golden.json")

# Auto-discover every book (any dir under book/ that has a book.json), fixture first.
def _discover_books():
    base = os.path.join(ROOT, "book")
    found = []
    for dirpath, _dirs, files in os.walk(base):
        if "book.json" in files:
            found.append(os.path.relpath(dirpath, base).replace(os.sep, "/"))
    # fixture(s) first (cheap), then the rest sorted for stable order
    fix = sorted(b for b in found if b.startswith("_fixtures/"))
    rest = sorted(b for b in found if not b.startswith("_fixtures/"))
    return fix + rest

BOOKS = _discover_books()


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def _has_source(book_dir):
    src = os.path.join(book_dir, "source")
    if not os.path.isdir(src):
        return False
    return any(not n.startswith(".") for n in os.listdir(src))


def measure(book_rel):
    """build + verify a book, return {files:{name:sha}, verify:{totals}} or None if no source."""
    from biblio.build import build_book
    from biblio.verify import verify_book
    book_dir = os.path.join(ROOT, "book", book_rel)
    if not _has_source(book_dir):
        return None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):  # silence build tables + force-s2twp warnings
        build_book(book_dir)
        rep = verify_book(book_dir)
    files = {os.path.basename(p): _sha(p)
             for p in sorted(glob.glob(os.path.join(book_dir, "out", "*.md")))}
    return {"files": files, "verify": rep["totals"]}


def _diff_book(name, golden, current):
    """Return list of human-readable drift reasons (empty = identical)."""
    reasons = []
    gf, cf = golden.get("files", {}), current["files"]
    for fn in sorted(set(gf) | set(cf)):
        if fn not in cf:
            reasons.append("MISSING out/%s" % fn)
        elif fn not in gf:
            reasons.append("NEW out/%s (not in golden)" % fn)
        elif gf[fn] != cf[fn]:
            reasons.append("CHANGED out/%s" % fn)
    gv, cv = golden.get("verify", {}), current["verify"]
    for k in sorted(set(gv) | set(cv)):
        if gv.get(k) != cv.get(k):
            reasons.append("verify.%s %s->%s" % (k, gv.get(k), cv.get(k)))
    return reasons


def run(only=None, freeze=False):
    books = [b for b in BOOKS if not only or b.split("/")[-1] in only or b in only]
    golden = {}
    if os.path.exists(GOLDEN):
        with open(GOLDEN, encoding="utf-8") as fh:
            golden = json.load(fh)

    results = []          # (name, status, detail)
    new_golden = dict(golden)
    for b in books:
        name = b.split("/")[-1]
        try:
            cur = measure(b)
        except Exception as e:                      # a build/verify crash is a hard fail
            results.append((name, "FAIL", "build/verify error: %s" % e))
            continue
        if cur is None:
            results.append((name, "SKIP", "no source/ (sparse checkout)"))
            continue
        if freeze:
            new_golden[name] = cur
            results.append((name, "FROZEN", "%d files" % len(cur["files"])))
            continue
        if name not in golden:
            results.append((name, "FAIL", "no golden yet -- run --freeze to bless"))
            continue
        reasons = _diff_book(name, golden[name], cur)
        if reasons:
            results.append((name, "FAIL", "; ".join(reasons)))
        else:
            results.append((name, "PASS", "%d files byte-identical | markers=%s issues=%s"
                            % (len(cur["files"]), cur["verify"].get("simplified_markers"),
                               cur["verify"].get("issues"))))

    # fixture structural self-test (titles / no credits leak / golden expected.md) -- a deeper
    # check than hashing, only meaningful for the fixture; runs when the fixture is in scope.
    if any(b == "_fixtures/sample" for b in books) and not freeze:
        import subprocess
        p = subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(ROOT, "scripts", "make_epub_fixture.py")],
                           capture_output=True, text=True, encoding="utf-8")
        ok = "PASS" in (p.stdout or "") and "byte-identical" in (p.stdout or "")
        results.append(("_fixtures self-test", "PASS" if ok else "FAIL",
                        (p.stdout or p.stderr or "").strip().splitlines()[-1] if (p.stdout or p.stderr) else "no output"))

    if freeze:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(new_golden, fh, ensure_ascii=False, indent=2, sort_keys=True)

    # report
    width = max(len(n) for n, _, _ in results)
    print("[regress] %s%s" % ("FREEZE -> %s\n" % os.path.relpath(GOLDEN, ROOT) if freeze else "",
                              "checking %d book(s) vs golden" % len(books) if not freeze else ""))
    failed = 0
    for name, status, detail in results:
        if status == "FAIL":
            failed += 1
        print("  %-5s %-*s | %s" % (status, width, name, detail))
    total = len([r for r in results if r[1] != "SKIP"])
    print("[regress] %d/%d ok, %d FAIL%s" %
          (total - failed, total, failed, "" if not freeze else " (frozen)"))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(prog="regress")
    ap.add_argument("--freeze", action="store_true", help="re-bless current output as golden")
    ap.add_argument("--only", default="", help="comma-separated book slugs to limit to")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    sys.exit(run(only=only, freeze=args.freeze))


if __name__ == "__main__":
    main()
