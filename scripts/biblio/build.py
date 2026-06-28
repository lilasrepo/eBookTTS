# -*- coding: utf-8 -*-
"""build_book -- sources -> one Markdown file per output Piece (卷/話) under <book_dir>/out/.

A book is planned into Pieces (see plan.py / ARCHITECTURE.md): a Piece is one output unit
(a 卷 or a 話) built from one or more source FRAGMENTS. published books are 1 source = 1 卷;
web books group 話 -> 卷 via volumes.tsv or emit 1 話 per file. Output is named by the Piece
id+label (Vol-NN_label.md / H-NNNN_label.md), or by source stem for legacy books with no
source_type. Every full build also writes build/manifest.json (ARCHITECTURE.md §7).

Per-chapter transform order (ARCH, LOCKED -- mirrors the legacy fan-translation pipeline and must not be
reordered): strip_media? -> jp_patch?(pre-OpenCC) -> opencc(convert) -> strip_credit_lines
-> strip_tl?(post-OpenCC) -> strip_editor_notes? -> apply_names(names_tsv)? -> repair_names?
(post-names). strip_credit_lines is ALWAYS-ON (drops stray 圖源:/錄入: scanlation footers,
keeps 作者/插畫; high precision so clean prose is untouched -- byte-identical for the sample book /
fixtures, which have no such lines). The optional fan-TL steps are OFF unless their book.json
key is set, so a clean source's output is unchanged. convert is per-SOURCE: a Simplified-language
source (REVIEWER B1: a mixed-language book is zh-CN) is FORCED through s2twp regardless of book.json.
"""
import json
import os
import re
import sys

from .config import load_book_config
from .ingest import adapter_for, list_sources
from . import textconv
from .plan import plan


def _detect_convert_mode(cfg, meta):
    """Per-source convert mode. Force s2twp on a Simplified-language source.

    REVIEWER B1: such a book is mixed -- vol08 dc:language=zh-CN. A single book-level
    convert knob is insufficient; honor book.json convert for zh-TW sources but force
    s2twp when the source declares Simplified, so the no-Simplified rule always holds.
    """
    mode = cfg.get("convert", "s2twp")
    lang = (meta or {}).get("language") or ""
    low = lang.strip().lower()
    is_simplified = low.startswith("zh-cn") or low.startswith("zh-hans") or low in ("zh", "zh-chs")
    if is_simplified and mode == "none":
        sys.stderr.write(
            "[biblio] WARNING: source language %r is Simplified; forcing s2twp "
            "(book.json convert=%r ignored for this source).\n" % (lang, mode)
        )
        return "s2twp"
    return mode


def _safe(label):
    """Windows-legal file component from an already-extensionless label (NOT a path).

    Unlike a filename stem, must NOT splitext -- a label like '... - 08.5' would lose '.5'.
    """
    s = re.sub(r'[\\/:*?"<>|]', "_", label)     # strip path-illegal chars
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(". ")                            # trailing dots/spaces illegal on Windows
    return s or "untitled"


def _out_name(piece):
    """out/ filename for a Piece. Legacy -> '<stem>.md'; else '<id>_<safe(label)>.md'."""
    if piece.legacy:
        return _safe(piece.label) + ".md"
    return "%s_%s.md" % (piece.id, _safe(piece.label))


def _select_chapters(doc, selector):
    """Pick a source Document's chapters for a fragment. None -> all. '<a>-<b>' / '<n>'
    -> 1-based inclusive chapter slice. Fails LOUD on a bad/empty selector instead of
    silently dropping the fragment (volumes.tsv is hand-edited)."""
    chapters = doc.chapters
    if not selector:
        return chapters
    sel = selector.strip()
    n = len(chapters)
    try:
        if "-" in sel:
            a, _, b = sel.partition("-")
            lo = int(a) if a.strip() else 1
            hi = int(b) if b.strip() else n
        else:
            lo = hi = int(sel)
    except ValueError:
        raise ValueError("bad chapter selector %r (expect 'N' or 'A-B')" % (selector,))
    if not (1 <= lo <= hi <= n):
        raise ValueError("selector %r out of range for %d-chapter source (need 1<=lo<=hi<=%d)"
                         % (selector, n, n))
    sub = chapters[lo - 1:hi]
    if not sub:
        raise ValueError("selector %r selected 0 chapters" % (selector,))
    return sub


def _parse_source(src, cache):
    """Parse a source file into a Document, memoized so a source shared by several Pieces
    (or selectors) is parsed once. Credit/copyright/staff PAGES are dropped inside the epub
    adapter unconditionally (not a book.json toggle); stray credit FOOTER lines that ride
    along with real content are scrubbed later per-chapter by textconv.strip_credit_lines."""
    if src in cache:
        return cache[src]
    doc = adapter_for(src).parse(src)
    cache[src] = doc
    return doc


def _render_chapter(chapter, convert_mode, cfg):
    """Apply the per-chapter transform pipeline; return the chapter's Markdown block.

    The TITLE goes through the same script/name conversion as the body -- nav/ncx titles
    are in the source script (vol08's are Simplified) and would otherwise leak unconverted
    into the '# ' heading (residual Simplified) and bypass the name dictionary.
    """
    names_tsv = cfg.get("names_tsv_path")
    jp_path = cfg.get("jp_patches_path")
    syl_path = cfg.get("name_syllables_path")

    body = chapter.body
    if cfg.get("strip_media", True):
        body = textconv.strip_media(body)
    if jp_path:
        body = textconv.jp_patch(body, jp_path)            # BEFORE OpenCC
    body = textconv.opencc_convert(body, convert_mode)
    body = textconv.strip_credit_lines(body)               # always: drop scanlation credit footers
    if cfg.get("strip_tl", False):
        body = textconv.strip_tl(body)                     # AFTER OpenCC
    if cfg.get("strip_editor_notes", False):
        body = textconv.strip_editor_notes(body)
    if names_tsv:
        body = textconv.apply_names(body, names_tsv)
    if syl_path:
        body = textconv.repair_names(body, syl_path)       # AFTER apply_names
    body = body.strip()

    title = textconv.opencc_convert(chapter.title or "", convert_mode)
    if names_tsv:
        title = textconv.apply_names(title, names_tsv)
    if syl_path:
        title = textconv.repair_names(title, syl_path)
    title = title.strip()

    head = "# " + title if title else ""
    if head and body:
        return head + "\n\n" + body
    return head or body


_CONFIG_KEYS = ("source_type", "output_unit", "convert", "strip_media", "strip_credits",
                "strip_editor_notes", "strip_tl", "names_tsv", "jp_patches", "name_syllables")


def _build_piece(piece, cfg, parse_cache):
    """Build one Piece -> (out_text, manifest_entry). Merges all its fragments in order."""
    book_dir = cfg["book_dir"]
    web_volume = cfg.get("source_type") == "web" and piece.kind == "卷"

    blocks = []
    chapter_count = 0
    frag_rel = []
    convert_modes = set()
    for src, sel in piece.fragments:
        doc = _parse_source(src, parse_cache)
        convert_mode = _detect_convert_mode(cfg, doc.meta)
        convert_modes.add(convert_mode)
        chapters = _select_chapters(doc, sel)
        for ch in chapters:
            block = _render_chapter(ch, convert_mode, cfg)
            if block.strip():
                blocks.append(block)
        chapter_count += len(chapters)
        frag_rel.append(os.path.relpath(src, book_dir).replace("\\", "/"))

    out_text = "\n\n".join(blocks)
    if piece.note:                          # volume-level note (e.g. WEB 後續) as a blockquote
        out_text = "> " + piece.note.strip() + "\n\n" + out_text
    if out_text and not out_text.endswith("\n"):
        out_text += "\n"

    out_name = _out_name(piece)
    out_path = os.path.join(book_dir, "out", out_name)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(out_text)

    inner_unit = "話" if web_volume else "章"
    inner_count = len(piece.fragments) if web_volume else chapter_count
    # headings actually emitted (a title-less chapter -- e.g. an epigraph page -- renders
    # body with no '# ', so heading count < chapter count legitimately). verify recounts
    # headings on disk and compares to THIS, not to inner_count, so a title-less chapter is
    # not mistaken for a dropped one; a real drop still shows up as a char-count mismatch.
    emitted_heads = len(re.findall(r"(?m)^#\s+\S", out_text))
    entry = {
        "kind": piece.kind, "id": piece.id, "number": piece.number,
        "label": piece.label, "note": piece.note,
        "out": "out/" + out_name,
        "fragments": frag_rel,
        "convert": sorted(convert_modes),
        "inner": {"unit": inner_unit, "count": inner_count, "headings": emitted_heads},
        "chars": len(out_text),
        "residual_simplified": textconv.count_residual_simplified(out_text),
        "simplified_markers": textconv.count_simplified_markers(out_text),
    }
    return entry


def build_book(book_dir, only_source=None):
    """Plan -> build every Piece (or those matching only_source) -> out/*.md.

    Returns a manifest dict; also persists it to build/manifest.json on a FULL build
    (skipped when only_source is set, to avoid clobbering with a partial manifest).
    """
    cfg = load_book_config(book_dir)
    sources = list_sources(book_dir)
    pieces = plan(cfg["book_dir"], cfg, sources)
    if only_source:
        n = only_source.lower()
        pieces = [p for p in pieces
                  if n in p.id.lower() or n in (p.label or "").lower()
                  or any(n in os.path.basename(f).lower() for f, _ in p.fragments)]

    os.makedirs(os.path.join(cfg["book_dir"], "out"), exist_ok=True)
    parse_cache = {}
    entries = []
    seen_out = {}
    for piece in pieces:
        name = _out_name(piece)
        if name in seen_out:
            raise ValueError("output filename collision: piece %r and %r both -> out/%s"
                             % (seen_out[name], piece.id, name))
        seen_out[name] = piece.id
        entries.append(_build_piece(piece, cfg, parse_cache))

    manifest = {
        "slug": cfg["slug"],
        "source_type": cfg.get("source_type"),
        "output_unit": cfg.get("output_unit", "卷"),
        "config": {k: cfg.get(k) for k in _CONFIG_KEYS},
        "book_dir": cfg["book_dir"],
        "pieces": entries,
        "totals": {
            "pieces": len(entries),
            "inner_units": sum(e["inner"]["count"] for e in entries),
            "chars": sum(e["chars"] for e in entries),
        },
    }
    if not only_source:
        build_dir = os.path.join(cfg["book_dir"], "build")
        os.makedirs(build_dir, exist_ok=True)
        with open(os.path.join(build_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest
