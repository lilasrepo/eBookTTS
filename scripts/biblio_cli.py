# -*- coding: utf-8 -*-
"""biblio CLI.

  python -X utf8 scripts/biblio_cli.py build  <book_dir> [--source NAME] [--allow-drift]
  python -X utf8 scripts/biblio_cli.py verify <book_dir> [--strict] [--allow-drift]
  python -X utf8 scripts/biblio_cli.py tts    <book_dir> [--source NAME] [--chapter N]
  python -X utf8 scripts/biblio_cli.py doctor                 # env self-check
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # make 'biblio' importable

from biblio.build import build_book          # noqa: E402
from biblio.tts import build_audiobook       # noqa: E402
from biblio.verify import verify_book, print_report  # noqa: E402
from biblio.doctor import run_doctor         # noqa: E402
from biblio import textconv                  # noqa: E402


def _guarded(fn, args):
    """Run fn(args) with the OpenCC drift guard configured; guard error -> clean message, exit 1."""
    textconv.set_allow_drift(args.allow_drift)
    try:
        textconv.preflight()
        fn(args)
    except RuntimeError as e:
        if "requirements pin" not in str(e):
            raise
        print("[biblio] ERROR: %s" % e, file=sys.stderr)
        sys.exit(1)


def _cmd_build(args):
    m = build_book(args.book_dir, only_source=args.source)
    t = m["totals"]
    print("[build] %s (%s/%s) -> %d piece(s), %d %s, %d chars" %
          (m["slug"], m["source_type"], m["output_unit"], t["pieces"],
           t["inner_units"], "inner-units", t["chars"]))
    for v in m["pieces"]:
        print("  %-24s | %4d %s | %8d chars | convert=%-12s | resid %-4d | %s"
              % (v["id"], v["inner"]["count"], v["inner"]["unit"], v["chars"],
                 ",".join(v["convert"]), v["residual_simplified"], v["out"]))


def _cmd_verify(args):
    rep = verify_book(args.book_dir)
    print_report(rep)
    if getattr(args, "strict", False) and rep["totals"]["issues"] > 0:
        sys.exit(1)


def _cmd_tts(args):
    m = build_audiobook(args.book_dir, only_source=args.source, only_chapter=args.chapter)
    print("[tts] %s -> %d volume(s)" % (m.get("book_dir", "?"), len(m.get("volumes", []))))
    for v in m.get("volumes", []):
        print("  %-40s | %3d ch | %.1f min" % (v["name"], v["chapters"], v["minutes"]))


def _cmd_doctor(args):
    if not run_doctor():
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(prog="biblio_cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="plan + convert sources -> out/*.md + build/manifest.json")
    b.add_argument("book_dir")
    b.add_argument("--source", default=None, help="build only the piece matching this substring")
    b.add_argument("--allow-drift", action="store_true",
                   help="proceed (WARN only) when OpenCC version != requirements pin")
    b.set_defaults(func=lambda a: _guarded(_cmd_build, a))

    v = sub.add_parser("verify", help="re-check out/*.md against build/manifest.json")
    v.add_argument("book_dir")
    v.add_argument("--strict", action="store_true",
                   help="exit 1 if any issues (for CI / new-book gating)")
    v.add_argument("--allow-drift", action="store_true",
                   help="proceed (WARN only) when OpenCC version != requirements pin")
    v.set_defaults(func=lambda a: _guarded(_cmd_verify, a))

    t = sub.add_parser("tts", help="out/*.md -> audiobook mp3s")
    t.add_argument("book_dir")
    t.add_argument("--source", default=None, help="only the volume matching this substring")
    t.add_argument("--chapter", type=int, default=None, help="only this chapter number (smoke test)")
    t.set_defaults(func=_cmd_tts)

    d = sub.add_parser("doctor", help="environment self-check (versions / opencc / ffmpeg)")
    d.set_defaults(func=_cmd_doctor)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
