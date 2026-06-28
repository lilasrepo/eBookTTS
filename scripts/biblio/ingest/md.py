# -*- coding: utf-8 -*-
"""Markdown adapter: split a .md file into chapters on level-1/2 ATX headings."""
import os
import re

from .base import Adapter, Chapter, Document

_HEADING_RE = re.compile(r"(?m)^#{1,2}[ \t]+(.+?)[ \t]*$")


class MdAdapter(Adapter):
    exts = (".md",)

    def parse(self, path):
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        title = os.path.splitext(os.path.basename(path))[0]
        matches = list(_HEADING_RE.finditer(raw))
        chapters = []
        if not matches:
            body = raw.strip()
            if body:
                chapters.append(Chapter(title=title, body=body))
            return Document(title=title, chapters=chapters, meta={"source": path})
        # leading content before the first heading is preserved as an untitled chapter
        pre = raw[: matches[0].start()].strip()
        if pre:
            chapters.append(Chapter(title="", body=pre))
        for i, m in enumerate(matches):
            htitle = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            body = raw[start:end].strip()
            chapters.append(Chapter(title=htitle, body=body))
        # first '# ' heading is often the doc title -> use it as Document title
        if matches and raw[matches[0].start():matches[0].start() + 2] == "# ":
            title = matches[0].group(1).strip()
        return Document(title=title, chapters=chapters, meta={"source": path})
