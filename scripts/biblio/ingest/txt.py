# -*- coding: utf-8 -*-
"""Plain-text adapter -- STUB.

Intended implementation: read the .txt (UTF-8), then chapter-split with
``biblio.chapters.regex_split_chapters`` as the fallback segmentation. Left as a
stub until a real .txt source needs it.
"""
from .base import Adapter


class TxtAdapter(Adapter):
    exts = (".txt",)

    def parse(self, path):
        raise NotImplementedError(
            "TxtAdapter not implemented yet; intended impl = read UTF-8 then "
            "biblio.chapters.regex_split_chapters(text) for heading-free segmentation."
        )
