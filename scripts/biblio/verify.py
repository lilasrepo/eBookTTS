# -*- coding: utf-8 -*-
"""verify_book -- re-check a built book against its build/manifest.json (ARCHITECTURE.md §7).

For every Piece: out file exists; recompute residual-Simplified and char count from the
file on disk and compare to the manifest; count '# ' headings; confirm fragment sources
still exist. Pure read-only -- never writes out/. Returns a report dict and prints a summary.
"""
import json
import os
import re

from . import textconv

_HEAD_RE = re.compile(r"(?m)^#\s+\S")


def verify_book(book_dir):
    book_dir = os.path.abspath(book_dir)
    mpath = os.path.join(book_dir, "build", "manifest.json")
    if not os.path.exists(mpath):
        raise FileNotFoundError("no manifest: %s (run build first)" % mpath)
    with open(mpath, encoding="utf-8") as fh:
        man = json.load(fh)

    issues = []
    rows = []
    total_residual = 0
    total_markers = 0
    for e in man.get("pieces", []):
        out_path = os.path.join(book_dir, e["out"])
        row = {"id": e["id"], "out": e["out"], "ok": True, "notes": []}
        if not os.path.exists(out_path):
            row["ok"] = False
            row["notes"].append("MISSING out file")
            issues.append("%s: missing %s" % (e["id"], e["out"]))
            rows.append(row)
            continue
        text = open(out_path, encoding="utf-8").read()
        chars = len(text)
        residual = textconv.count_residual_simplified(text)
        markers = textconv.count_simplified_markers(text)
        heads = len(_HEAD_RE.findall(text))
        total_residual += residual
        total_markers += markers
        row.update(chars=chars, residual=residual, markers=markers, headings=heads)

        if chars != e.get("chars"):
            row["ok"] = False
            row["notes"].append("char mismatch manifest=%s disk=%s" % (e.get("chars"), chars))
            issues.append("%s: char mismatch" % e["id"])
        if markers > 0:                      # the real alarm: actual Simplified content leaked
            row["ok"] = False
            chars_seen = "".join(sorted(textconv.list_simplified_markers(text)))
            row["notes"].append("%d Simplified markers (%s)" % (markers, chars_seen))
            issues.append("%s: %d Simplified markers" % (e["id"], markers))
        # ARCHITECTURE §7: 章數 drop guard -- compare disk headings to the count build actually
        # EMITTED (inner.headings), not the chapter count: a title-less chapter (epigraph page)
        # legitimately yields heads < chapters. They match by construction unless the file was
        # altered on disk; a dropped chapter also trips the char-count mismatch above. Old
        # manifests w/o inner.headings fall back to inner.count (prior behaviour).
        inner = e.get("inner") or {}
        if inner.get("unit") == "章":
            expected_heads = inner.get("headings", inner.get("count"))
            if heads != expected_heads:
                row["notes"].append("heading count %d != manifest %s" % (heads, expected_heads))
        if residual != e.get("residual_simplified"):
            row["notes"].append("residual now %d (manifest %s)" % (residual, e.get("residual_simplified")))
        # fragment sources still present?
        for fr in e.get("fragments", []):
            if not os.path.exists(os.path.join(book_dir, fr)):
                row["ok"] = False
                row["notes"].append("missing source %s" % fr)
                issues.append("%s: missing source %s" % (e["id"], fr))
        rows.append(row)

    report = {
        "slug": man.get("slug"),
        "source_type": man.get("source_type"),
        "output_unit": man.get("output_unit"),
        "pieces": rows,
        "totals": {
            "pieces": len(rows),
            "ok": sum(1 for r in rows if r["ok"]),
            "residual_simplified": total_residual,
            "simplified_markers": total_markers,
            "issues": len(issues),
        },
        "issues": issues,
    }
    return report


def print_report(rep):
    t = rep["totals"]
    print("[verify] %s (%s/%s) -> %d/%d pieces ok | Simplified-markers=%d | residual(variants)=%d | %d issue(s)"
          % (rep["slug"], rep["source_type"], rep["output_unit"], t["ok"], t["pieces"],
             t["simplified_markers"], t["residual_simplified"], t["issues"]))
    for r in rep["pieces"]:
        flag = "ok " if r["ok"] else "!! "
        extra = ("  <- " + "; ".join(r["notes"])) if r["notes"] else ""
        print("  %s%-22s | %5s 章 | %8s chars | SimpMark %-3s | resid %-4s | %s%s"
              % (flag, r["id"], r.get("headings", "?"), r.get("chars", "?"),
                 r.get("markers", "?"), r.get("residual", "?"), r["out"], extra))
    if rep["issues"]:
        print("  ISSUES:")
        for i in rep["issues"]:
            print("    - " + i)
