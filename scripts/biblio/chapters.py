# -*- coding: utf-8 -*-
"""Heading-free chapter splitting (used by txt fallback / loose prose) and
book.json chapter overrides."""
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


def apply_overrides(chapters, overrides):
    """Merge/split chapters per an optional book.json "chapters" override list.

    Each override is a dict:
      {"merge": [i, j, ...]}            -> combine those 0-based chapters into one
                                           (title from the first; bodies joined).
      {"split": i, "at": "<regex>", "titles": [...]}
                                        -> split chapter i's body on the regex; the
                                           optional titles list names the pieces.
      {"title": i_or_slug, "to": "..."} -> rename a chapter's title.
    Unknown keys are ignored. Returns a new chapter list.
    """
    if not overrides:
        return chapters
    out = list(chapters)
    for ov in overrides:
        if "merge" in ov:
            idxs = sorted(ov["merge"])
            if not idxs:
                continue
            first = idxs[0]
            bodies = [out[i].body for i in idxs if 0 <= i < len(out)]
            merged = Chapter(title=out[first].title, body="\n\n".join(b for b in bodies if b))
            keep = [c for k, c in enumerate(out) if k not in set(idxs)]
            keep.insert(min(first, len(keep)), merged)
            out = keep
        elif "split" in ov:
            i = ov["split"]
            if not (0 <= i < len(out)):
                continue
            pat = re.compile(ov.get("at", r"\n\n"))
            pieces = [p.strip() for p in pat.split(out[i].body) if p.strip()]
            titles = ov.get("titles", [])
            new = [Chapter(title=(titles[k] if k < len(titles) else out[i].title), body=p)
                   for k, p in enumerate(pieces)]
            out = out[:i] + new + out[i + 1:]
        elif "title" in ov and "to" in ov:
            i = ov["title"]
            if isinstance(i, int) and 0 <= i < len(out):
                out[i] = Chapter(title=ov["to"], body=out[i].body)
    return out
