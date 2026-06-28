# -*- coding: utf-8 -*-
"""Adapter base types shared by every ingest format."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chapter:
    title: str
    body: str


@dataclass
class Document:
    title: str
    chapters: List[Chapter] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class Adapter:
    """Base class for format adapters.

    Subclasses declare ``exts`` (tuple of lowercase extensions, incl dot) and
    implement ``parse(path) -> Document``.
    """
    exts = ()

    def parse(self, path):  # pragma: no cover - interface
        raise NotImplementedError
