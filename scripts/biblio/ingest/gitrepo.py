# -*- coding: utf-8 -*-
"""Directory ("git repo") adapter -- STUB.

Intended implementation: scan the directory for source files and delegate each to
``adapter_for(path)``, concatenating the per-file Documents. A directory passed to
``adapter_for`` resolves here.
"""
from .base import Adapter


class GitRepoAdapter(Adapter):
    exts = ()

    def parse(self, path):
        raise NotImplementedError(
            "GitRepoAdapter not implemented yet; intended impl = scan the dir for "
            "sources and delegate each file to ingest.adapter_for(file)."
        )
