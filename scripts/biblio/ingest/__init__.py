# -*- coding: utf-8 -*-
"""Ingest adapters registry + source discovery."""
import os
import re

from .epub import EpubAdapter
from .md import MdAdapter
from .txt import TxtAdapter
from .pdf import PdfAdapter
from .docx import DocxAdapter
from .gitrepo import GitRepoAdapter

ADAPTERS = {
    ".epub": EpubAdapter,
    ".md": MdAdapter,
    ".txt": TxtAdapter,
    ".pdf": PdfAdapter,
    ".docx": DocxAdapter,
}

# names ignored when listing a book dir's sources
_RESERVED = {"out", "audiobook", "control", "source", "book.json"}


def adapter_for(path):
    """Return an adapter INSTANCE for a path.

    A directory -> GitRepoAdapter (delegates per file). A file -> by extension.
    Raises ValueError for an unsupported extension.
    """
    if os.path.isdir(path):
        return GitRepoAdapter()
    ext = os.path.splitext(path)[1].lower()
    cls = ADAPTERS.get(ext)
    if cls is None:
        raise ValueError("no adapter for extension %r (%s)" % (ext, path))
    return cls()


def _natkey(name):
    """Natural-sort key: split digit runs, compare numerically.

    Makes '... - 01'..'- 08' order correctly and lands 'SSS短篇集 - 01' after the
    plain '- 0N' stems (shared literal prefix; the longer 'SSS...' segment sorts
    after the plain stems).
    """
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def list_sources(book_dir):
    """Return the source files for a book dir (absolute paths, natural-sorted).

    Layout detect: if <book_dir>/source/ exists, list its files; ELSE list loose
    files in the dir root. Reserved names (out/, audiobook/, control/, book.json)
    and dotfiles are ignored. Only files whose extension is in ADAPTERS are kept.
    """
    book_dir = os.path.abspath(book_dir)
    src_sub = os.path.join(book_dir, "source")
    base = src_sub if os.path.isdir(src_sub) else book_dir
    out = []
    for name in os.listdir(base):
        if name.startswith("."):
            continue
        if base == book_dir and name.lower() in _RESERVED:
            continue
        full = os.path.join(base, name)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(name)[1].lower() in ADAPTERS:
            out.append(full)
    # sort on the extension-stripped stem so 'x - 08' precedes 'x - 08.5'
    # (with the extension, '.epub' vs '.5...' inverts the order of fractional volumes).
    out.sort(key=lambda p: _natkey(os.path.splitext(os.path.basename(p))[0]))
    return out
