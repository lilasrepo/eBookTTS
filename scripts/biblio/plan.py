# -*- coding: utf-8 -*-
"""Plan a book into output Pieces (卷/話). Contract: ../../ARCHITECTURE.md §3-4.

source_type/output_unit drive the unit and naming:
  published + 卷 : 1 source file = 1 卷 (auto, Vol-NN); label = source stem
  web       + 卷 : control/volumes.tsv groups 話 -> 卷 (explicit id or Vol-NN)
  web       + 話 : 1 source file = 1 話 (auto, H-NNNN)
  published + 話 : INVALID (published has no 話) -> ValueError
  (source_type unset) : LEGACY 1:1 -- output stem = source filename (back-compat for
                        books predating the contract, e.g. the sample fixture).
"""
import os
from dataclasses import dataclass, field


@dataclass
class Piece:
    kind: str                  # "卷" | "話"
    id: str                    # filename key: Vol-01 / H-0001 / explicit from volumes.tsv
    number: int                # sort/order key (1-based)
    label: str                 # human title (no extension)
    note: str = None           # optional header note (e.g. WEB 後續)
    fragments: list = field(default_factory=list)   # [(source_abs_path, selector|None)]
    legacy: bool = False       # True -> output named by stem only (no id prefix)


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _plan_legacy(sources):
    """No source_type: each source = one 卷, output stem = source filename (back-compat)."""
    return [Piece(kind="卷", id=_stem(s), number=i, label=_stem(s),
                  fragments=[(s, None)], legacy=True)
            for i, s in enumerate(sources, 1)]


def _plan_published(sources):
    """1 source = 1 卷, Vol-NN in natural-sort order; label = source stem."""
    width = max(2, len(str(len(sources))))
    return [Piece(kind="卷", id="Vol-%0*d" % (width, i), number=i,
                  label=_stem(s), fragments=[(s, None)])
            for i, s in enumerate(sources, 1)]


def _plan_web_episodes(sources):
    """1 source = 1 話, H-NNNN global running number in natural-sort order."""
    width = max(4, len(str(len(sources))))
    return [Piece(kind="話", id="H-%0*d" % (width, i), number=i,
                  label=_stem(s), fragments=[(s, None)])
            for i, s in enumerate(sources, 1)]


def _plan_web_volumes(book_dir):
    """control/volumes.tsv: id\\tlabel\\tnote\\tfragments.

    fragments = comma-separated 'relpath[:selector]', relpath RELATIVE to <book>/source/.
    selector (optional) restricts which chapters of that source (see build._select_chapters).
    """
    vt = os.path.join(book_dir, "control", "volumes.tsv")
    if not os.path.exists(vt):
        raise ValueError("source_type=web + output_unit=卷 needs control/volumes.tsv (not found: %s)" % vt)
    src_root = os.path.join(book_dir, "source")
    pieces = []
    with open(vt, encoding="utf-8") as fh:
        rows = [l for l in fh.read().splitlines()[1:] if l.strip()]
    for i, line in enumerate(rows, 1):
        p = (line.split("\t") + ["", "", "", ""])[:4]
        vid, label, note, frags = (p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip())
        fragments = []
        for tok in frags.split(","):
            tok = tok.strip()
            if not tok:
                continue
            relpath, _, sel = tok.partition(":")
            fragments.append((os.path.join(src_root, relpath.strip()), sel.strip() or None))
        missing = [os.path.relpath(f, book_dir) for f, _ in fragments if not os.path.exists(f)]
        if missing:
            raise ValueError("volume %s (%s): fragment file(s) not found: %s"
                             % (vid or i, label, ", ".join(missing)))
        pieces.append(Piece(kind="卷", id=vid or ("Vol-%02d" % i), number=i,
                            label=label, note=note or None, fragments=fragments))
    return pieces


def plan(book_dir, cfg, sources):
    """Return [Piece] for a book, dispatched by source_type/output_unit."""
    st = cfg.get("source_type")
    ou = cfg.get("output_unit", "卷")
    if st is None:
        return _plan_legacy(sources)
    if st == "published":
        if ou == "話":
            raise ValueError("invalid combo: source_type=published with output_unit=話 "
                             "(a published volume has no 話 unit)")
        return _plan_published(sources)
    if st == "web":
        if ou == "卷":
            return _plan_web_volumes(book_dir)
        if ou == "話":
            return _plan_web_episodes(sources)
        raise ValueError("web output_unit must be 卷 or 話, got %r" % (ou,))
    raise ValueError("unknown source_type %r (expect 'web' or 'published')" % (st,))
