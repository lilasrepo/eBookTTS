# -*- coding: utf-8 -*-
"""Per-book configuration loader.

A book dir holds an optional ``book.json``; missing keys fall back to DEFAULTS.
``convert:"none"`` MUST stay a true no-op downstream (see textconv.opencc_convert).
"""
import copy
import json
import os

DEFAULTS = {
    "slug": None,
    "title": None,
    "author": None,
    "lang": "zh",
    "source_type": None,         # web | published | None(=legacy 1:1). See ARCHITECTURE.md §3
    "output_unit": "卷",         # 卷 | 話 (web only). published is always 卷
    "convert": "s2twp",          # one of: s2twp | s2tw | none
    "strip_media": True,
    "strip_credits": True,
    "strip_editor_notes": False,
    "strip_tl": False,           # remove fan-TL credits/promo/notes (AFTER OpenCC). OFF by default.
    "names_tsv": None,           # path RELATIVE to book_dir, or None
    "jp_patches": None,          # REL path to jp_patches.tsv (jp\tzh), applied BEFORE OpenCC. None=off
    "name_syllables": None,      # REL path to name_syllables.tsv, homophone repair AFTER names. None=off
    "tts": {
        "mode": "dual",
        "narration": "zh-TW-HsiaoChenNeural",
        "dialogue": "zh-CN-XiaoyiNeural",
        "rate": "+10%",
        "format": {"bitrate": "32k", "channels": 1, "sample_rate": 24000},
        "gap_ms": 250,
    },
}


def _deep_merge(base, over):
    """Return base updated by over; nested dicts merged, scalars/lists replaced."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_book_config(book_dir):
    """Load <book_dir>/book.json merged over DEFAULTS.

    Adds derived keys:
      - ``book_dir``: absolute book dir.
      - ``slug``: defaults to the book dir basename when unset.
      - ``names_tsv_path``: absolute path resolved against book_dir (or None).
    """
    book_dir = os.path.abspath(book_dir)
    cfg = copy.deepcopy(DEFAULTS)
    jpath = os.path.join(book_dir, "book.json")
    if os.path.exists(jpath):
        with open(jpath, encoding="utf-8") as fh:
            user = json.load(fh)
        cfg = _deep_merge(cfg, user)
    cfg["book_dir"] = book_dir
    if not cfg.get("slug"):
        cfg["slug"] = os.path.basename(book_dir.rstrip("\\/"))
    names_tsv = cfg.get("names_tsv")
    cfg["names_tsv_path"] = os.path.join(book_dir, names_tsv) if names_tsv else None
    jp = cfg.get("jp_patches")
    cfg["jp_patches_path"] = os.path.join(book_dir, jp) if jp else None
    syl = cfg.get("name_syllables")
    cfg["name_syllables_path"] = os.path.join(book_dir, syl) if syl else None
    return cfg
