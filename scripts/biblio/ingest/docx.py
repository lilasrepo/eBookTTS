# -*- coding: utf-8 -*-
"""DOCX adapter -- STUB (needs a third-party library)."""
from .base import Adapter


class DocxAdapter(Adapter):
    exts = (".docx",)

    def parse(self, path):
        raise NotImplementedError(
            "DocxAdapter needs python-docx -- ask before installing."
        )
