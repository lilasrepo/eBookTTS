# -*- coding: utf-8 -*-
"""Heading-free chapter splitting for plain text (txt fallback / loose prose)."""
import re

from .ingest.base import Chapter

# A line that opens a new chapter. Anchored to start-of-line (MULTILINE).
CHAP_RE = re.compile(
    r"(?m)^(?:"
    r"第[一二三四五六七八九十百千0-9]+[章話回卷部]"        # 第一章 / 第12話 ...
    r"|序章|序幕|序|楔子|終章|尾聲|終幕|後記"               # CJK structural headers
    r"|Chapter\s+\d+|Prologue|Epilogue|Intermission"        # latin
    r")\b?.*$"
)


def regex_split_chapters(text):
    """Split plain text into [Chapter] on recognised heading lines.

    Text before the first heading (if any) becomes a leading untitled chapter so
    no content is lost. Each heading line becomes the chapter title; the rest of
    the lines up to the next heading become the body.
    """
    matches = list(CHAP_RE.finditer(text))
    if not matches:
        body = text.strip()
        return [Chapter(title="", body=body)] if body else []
    chapters = []
    pre = text[: matches[0].start()].strip()
    if pre:
        chapters.append(Chapter(title="", body=pre))
    for i, m in enumerate(matches):
        title = m.group(0).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        chapters.append(Chapter(title=title, body=body))
    return chapters
