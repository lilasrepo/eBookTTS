# -*- coding: utf-8 -*-
"""PDF adapter -- STUB (needs a third-party library)."""
from .base import Adapter


class PdfAdapter(Adapter):
    exts = (".pdf",)

    def parse(self, path):
        raise NotImplementedError(
            "PdfAdapter needs PyMuPDF/pdfplumber -- ask before installing."
        )
