# -*- coding: utf-8 -*-
"""EPUB adapter -- Python STDLIB ONLY (zipfile, xml.etree.ElementTree, html, re,
posixpath, urllib.parse). NO lxml / ebooklib / pip.

Pipeline (see DESIGN EPUB_PLAN STEP 1-9):
  1. container.xml -> opf path.
  2. opf -> manifest(id->href,media-type,properties) + spine(idref order, linear) +
     metadata(dc:title/creator/language).
  3. norm(href, base): drop #frag, percent-decode, normalize relative to base, into
     ONE zip-key namespace so TOC hrefs and spine hrefs compare equal.
  4. TOC titles: prefer EPUB3 nav (item properties contains 'nav'); else EPUB2 toc.ncx.
     nav hrefs are relative to the NAV file's own dir, NOT opf_dir.
  5. each spine XHTML -> plain text (ignore <head>; block tags -> breaks; unescape).
  6. chapter title = nav title, else first <h1>/<h2>, else first non-empty line.
  7. SKIP image-only/empty chapters (no speakable CJK/letter/digit).
  8. strip_credits: drop credits/copyright/staff chapters (Traditional + Simplified).
  9. assemble Document(title=dc:title, chapters in spine order, meta).

XML NAMESPACES: EPUB OPF/NCX/XHTML are namespaced; ET reports tags as "{ns}local".
NEVER hardcode a prefix -- match on local-name via ln(); for namespaced attrs
(epub:type, properties) iterate attrib.items() and compare key.split('}')[-1].
"""
import html
import posixpath
import re
import zipfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from .base import Adapter, Chapter, Document

# Title-level credit/staff markers (Traditional + Simplified variants). The adapter
# tests the ORIGINAL (pre-conversion) title, so Simplified forms must be listed too.
_CREDIT_TITLE_RE = re.compile(
    r"(製作人員|制作人员|製作群|制作群|製作信息|制作信息|版權所有|版权所有"
    r"|版權|版权|免責聲明|免责声明|聲明與免責|声明与免责|disclaimer|staff|credits|colophon)",
    re.IGNORECASE,
)
# Blurb markers for a short body that is really a community-credits / copyright page
# (Traditional + Simplified). MUST be production-specific only — genre/prose words
# like 輕小說 / 網站 appear in normal light-novel text (e.g. the prologue mentions
# "可樂＆薯條＆輕小說") and previously caused the 序 chapter to be wrongly dropped.
_CREDIT_BLURB_RE = re.compile(
    r"(製作人員|制作人员|製作信息|制作信息|製作群|制作群|wenku8|本電子書|本电子书"
    r"|僅供.{0,6}學習|仅供.{0,6}学习|掃圖|扫图|錄入|录入|嵌字|漢化組|汉化组"
    r"|貼吧|贴吧|duokan|多看書城|多看书城|zhangyue|掌閱|掌阅|repost|EPUB\s*by)",
    re.IGNORECASE,
)
_CREDIT_BLURB_MAXLEN = 600   # only treat a SHORT body as a blurb

# At least one speakable char (CJK / kana / hangul / latin / digit).
_SPEAKABLE_RE = re.compile(r"[0-9A-Za-z぀-ヿ一-鿿가-힣]")

# Block-level elements that should produce a line/paragraph break.
_BLOCK_TAGS = {"p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
               "div", "section", "li", "blockquote", "tr"}
_SKIP_SUBTREE = {"script", "style"}


def ln(el):
    """Local-name of an ElementTree element tag (namespace-stripped)."""
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else ""


def _attr(el, name):
    """Fetch an attribute by local-name (tolerant of namespaced attr keys)."""
    for k, v in el.attrib.items():
        if k.split("}")[-1] == name:
            return v
    return None


def norm(href, base):
    """Map an href into a single zip-internal key namespace.

    Drops '#frag', percent-decodes (vol08 nav hrefs are %-encoded CJK), then
    normalizes relative to ``base`` (the OPF dir for spine/ncx, the NAV file dir
    for nav links). Returns a posix path with no leading './'.
    """
    if href is None:
        return None
    href = href.split("#", 1)[0]
    href = unquote(href)
    joined = posixpath.join(base, href) if base else href
    return posixpath.normpath(joined).lstrip("/")


def _collapse_ws(s):
    """Collapse all runs of whitespace to single spaces and strip (for titles)."""
    return re.sub(r"\s+", " ", s or "").strip()


def _xhtml_to_text(raw):
    """Convert one XHTML document to plain text.

    Tries ET (namespaces handled via ln); on parse failure falls back to a regex
    tag stripper. Ignores <head>; drops <script>/<style> subtrees; block tags and
    <br> become breaks; entities unescaped; <h1>/<h2> texts collected for the
    title fallback. Returns (text, h_titles).
    """
    body_el = None
    try:
        root = ET.fromstring(_strip_prolog(raw))
        for el in root.iter():
            if ln(el) == "body":
                body_el = el
                break
        if body_el is None:
            body_el = root
        return _walk_body(body_el)
    except ET.ParseError:
        return _regex_fallback(raw), _regex_h_titles(raw)


def _strip_prolog(raw):
    """Drop an XML declaration / DOCTYPE that sometimes confuses ET."""
    raw = re.sub(r"^﻿", "", raw)
    raw = re.sub(r"(?s)^\s*<\?xml[^>]*\?>", "", raw)
    raw = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", raw)
    return raw.strip()


def _walk_body(body_el):
    """Document-order walk accumulating text + tail; returns (text, h_titles)."""
    parts = []
    h_titles = []

    def rec(el):
        tag = ln(el)
        if tag in _SKIP_SUBTREE:
            if el.tail:
                parts.append(el.tail)
            return
        if tag in _BLOCK_TAGS:
            parts.append("\n")
        if el.text:
            parts.append(el.text)
        if tag in ("h1", "h2"):
            t = _collapse_ws("".join(el.itertext()))
            if t:
                h_titles.append((tag, t))
        for child in list(el):
            rec(child)
        if tag in _BLOCK_TAGS:
            parts.append("\n")
        if el.tail:
            parts.append(el.tail)

    # Walk children of body (not body's own tag, which is not a content break).
    if body_el.text:
        parts.append(body_el.text)
    for child in list(body_el):
        rec(child)

    text = html.unescape("".join(parts))
    return _normalize_text(text), h_titles


def _normalize_text(text):
    """Per-line strip (source XHTML is pretty-printed with deep <p> indentation,
    so leading whitespace must go too), collapse 3+ newlines to 2, strip outer blanks."""
    lines = [ln_.strip() for ln_ in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _regex_fallback(raw):
    """Tolerant tag stripper for non-well-formed XHTML (still drops head/script/style)."""
    raw = re.sub(r"(?is)<head\b.*?</head>", "", raw)
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(p|div|section|li|blockquote|tr|h[1-6])>", "\n", raw)
    raw = re.sub(r"(?is)<(p|div|section|li|blockquote|tr|h[1-6])\b[^>]*>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", "", raw)
    return _normalize_text(html.unescape(raw))


def _regex_h_titles(raw):
    """Extract <h1>/<h2> inner text for the title fallback in the regex path."""
    out = []
    for tag in ("h1", "h2"):
        m = re.search(r"(?is)<%s\b[^>]*>(.*?)</%s>" % (tag, tag), raw)
        if m:
            inner = re.sub(r"(?s)<[^>]+>", "", m.group(1))
            t = _collapse_ws(html.unescape(inner))
            if t:
                out.append((tag, t))
    return out


def detect_simplified_lang(language):
    """True if a dc:language value indicates Simplified Chinese (force s2twp)."""
    if not language:
        return False
    low = language.strip().lower()
    return low.startswith("zh-cn") or low.startswith("zh-hans") or low == "zh_cn"


def _is_credits(title, body, strip_credits):
    """Decide whether a chapter is a credits/staff/copyright page."""
    if not strip_credits:
        return False
    if title and _CREDIT_TITLE_RE.search(title):
        return True
    if body and len(body) <= _CREDIT_BLURB_MAXLEN and _CREDIT_BLURB_RE.search(body):
        return True
    return False


# Front-matter / junk-heading detection. ONLY consulted when a spine doc has NO nav-TOC
# title and NO <h1>/<h2> -- i.e. the weak "first non-empty line" title fallback, which on
# messy commercial epubs grabs cover glyphs ('S'), scene dividers ('■'), or illustration
# caption dialogue. Books with a real nav/ncx TOC (a book with a real TOC) never reach this path.
_PROSE_RUN_RE = re.compile(r"[一-鿿]{12,}")       # 12+ consecutive Han == genuine prose
_TITLE_WORD_RE = re.compile(r"[0-9A-Za-z一-鿿぀-ヿ가-힣]")
_QUOTE_OPENERS = "「『“”＂\"（(《【〈〔"


def _has_prose_run(text):
    return bool(_PROSE_RUN_RE.search(text))


def _first_line(text):
    for line in text.split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


def _is_junk_title(t):
    """A first-line fallback that is NOT a real chapter title: single char, symbol-only
    (■ ▲ ●), a dialogue/quote opener, or a full prose line (too long / sentence-final).
    Used (with no-prose) to DROP a whole front-matter page."""
    t = t.strip()
    if len(t) <= 1:
        return True
    if not _TITLE_WORD_RE.search(t):                 # pure symbols/punctuation
        return True
    if t[0] in _QUOTE_OPENERS:                       # caption/epigraph dialogue
        return True
    if len(t) >= 30:                                 # a prose paragraph, not a title
        return True
    if len(t) > 18 and t[-1] in "。！？!?…":           # a full sentence
        return True
    return False


def _nontitle_first_line(t):
    """HIGH-confidence non-title (for demoting a heading on a KEPT prose page): single char,
    pure symbol (■/▲/●), or a dialogue opener. Deliberately excludes the length heuristics so
    legit long titles (e.g. a skit-style book with very long titles) are never clipped."""
    t = t.strip()
    return len(t) <= 1 or not _TITLE_WORD_RE.search(t) or t[:1] in _QUOTE_OPENERS


class EpubAdapter(Adapter):
    exts = (".epub",)

    def parse(self, path):
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())

            # STEP 1 -- locate OPF via container.xml
            opf_path = self._find_opf(z)
            opf_dir = posixpath.dirname(opf_path)

            # STEP 2 -- parse OPF
            opf_root = ET.fromstring(z.read(opf_path))
            meta = self._parse_metadata(opf_root)
            manifest = self._parse_manifest(opf_root)
            spine, spine_toc_id = self._parse_spine(opf_root)

            # STEP 4 -- TOC titles (nav preferred, ncx fallback)
            toc_title = self._resolve_nav(z, manifest, opf_dir)
            if not toc_title:
                toc_title = self._resolve_ncx(z, manifest, opf_dir, spine_toc_id)

            # zip keys of the nav item itself (so we can drop it if it sits in spine)
            nav_keys = self._nav_keys(manifest, opf_dir)

            # STEP 5-8 -- per spine doc -> chapter
            chapters = []
            for idref, linear in spine:
                m = manifest.get(idref)
                if not m or not m.get("href"):
                    continue
                doc_key = norm(m["href"], opf_dir)
                if doc_key not in names:
                    continue
                # Drop the nav document itself (vol08 ships it in-spine, linear=no,
                # with TOC link text that would otherwise survive as junk).
                if doc_key in nav_keys:
                    continue
                # Drop non-linear spine items (front-matter/aux pages).
                if linear == "no":
                    continue
                raw = z.read(doc_key).decode("utf-8", errors="replace")
                text, h_titles = _xhtml_to_text(raw)
                # STEP 7 -- skip image-only / empty (no speakable text)
                if not text or not _SPEAKABLE_RE.search(text):
                    continue
                # STEP 6 -- title resolution + front-matter/junk-heading guard.
                # nav/ncx TOC and <h1>/<h2> are trusted. Only the weak first-line fallback
                # is policed: drop a junk-titled page with no real prose (cover/divider/
                # caption), and suppress a junk first-line heading on a real prose page.
                nav_title = toc_title.get(doc_key)
                h1 = self._h1_title(h_titles)
                if nav_title:
                    title = nav_title
                elif h1:
                    title = h1
                else:
                    first = _first_line(text)
                    # Drop a cover / scene-divider / caption page: junk first-line title AND
                    # no real prose. A page WITH prose is kept, but if its first line is a
                    # high-confidence non-title (■ / single char / dialogue opener) suppress
                    # that junk heading while keeping the prose body. Length-based heuristics
                    # are intentionally NOT used here, so legit long fallback titles (some books
                    # 小劇場 skits) keep their headings -> those books stay byte-identical.
                    if _is_junk_title(first) and not _has_prose_run(text):
                        continue
                    title = "" if _nontitle_first_line(first) else first[:60]
                # STEP 8 -- strip credits/staff/copyright
                if _is_credits(title, text, strip_credits=True):
                    continue
                chapters.append(Chapter(title=title, body=text))

        # STEP 9 -- assemble
        return Document(title=meta.get("title") or "", chapters=chapters, meta=meta)

    # ---- STEP 1 ----
    @staticmethod
    def _find_opf(z):
        croot = ET.fromstring(z.read("META-INF/container.xml"))
        rootfiles = [el for el in croot.iter() if ln(el) == "rootfile"]
        if not rootfiles:
            raise ValueError("no <rootfile> in META-INF/container.xml")
        # prefer the oebps-package media-type, else first.
        chosen = None
        for rf in rootfiles:
            mt = _attr(rf, "media-type")
            if mt == "application/oebps-package+xml":
                chosen = rf
                break
        chosen = chosen or rootfiles[0]
        opf = _attr(chosen, "full-path")
        if not opf:
            raise ValueError("<rootfile> has no full-path")
        return opf.lstrip("/")

    # ---- STEP 2: metadata ----
    @staticmethod
    def _parse_metadata(opf_root):
        meta_el = next((el for el in opf_root if ln(el) == "metadata"), opf_root)
        title = language = publisher = source = None
        creators = []          # list of (id, text)
        roles = {}             # creator-id -> role (from EPUB3 <meta refines>)
        for el in meta_el.iter():
            tag = ln(el)
            if tag == "title" and title is None:
                title = _collapse_ws(el.text)
            elif tag == "language" and language is None:
                language = (el.text or "").strip()
            elif tag == "publisher" and publisher is None:
                publisher = _collapse_ws(el.text)
            elif tag == "source" and source is None:
                source = (el.text or "").strip()
            elif tag == "creator":
                creators.append((_attr(el, "id"), _collapse_ws(el.text)))
                # legacy opf:role attribute, if present
                r = _attr(el, "role")
                if r:
                    roles[_attr(el, "id")] = r
            elif tag == "meta":
                # EPUB3 role refinement: <meta refines="#id" property="role">aut</meta>
                refines = _attr(el, "refines")
                prop = _attr(el, "property")
                if refines and prop == "role":
                    roles[refines.lstrip("#")] = (el.text or "").strip()
        # author = creator flagged role 'aut', else first creator
        author = None
        for cid, ctext in creators:
            if cid and roles.get(cid) == "aut":
                author = ctext
                break
        if author is None and creators:
            author = creators[0][1]
        return {
            "title": title,
            "language": language,
            "author": author,
            "creators": [c[1] for c in creators],
            "publisher": publisher,
            "source": source,
        }

    # ---- STEP 2: manifest ----
    @staticmethod
    def _parse_manifest(opf_root):
        manifest = {}
        for el in opf_root.iter():
            if ln(el) == "item":
                mid = _attr(el, "id")
                if mid is None:
                    continue
                manifest[mid] = {
                    "href": _attr(el, "href"),
                    "media_type": _attr(el, "media-type"),
                    "properties": _attr(el, "properties"),
                }
        return manifest

    # ---- STEP 2: spine ----
    @staticmethod
    def _parse_spine(opf_root):
        spine = []
        toc_id = None
        spine_el = next((el for el in opf_root.iter() if ln(el) == "spine"), None)
        if spine_el is not None:
            toc_id = _attr(spine_el, "toc")
            for c in spine_el:
                if ln(c) == "itemref":
                    idref = _attr(c, "idref")
                    if idref:
                        spine.append((idref, _attr(c, "linear")))
        return spine, toc_id

    # ---- STEP 4: nav item zip keys (for self-drop) ----
    @staticmethod
    def _nav_keys(manifest, opf_dir):
        keys = set()
        for m in manifest.values():
            props = m.get("properties")
            if props and "nav" in props.split() and m.get("href"):
                keys.add(norm(m["href"], opf_dir))
        return keys

    # ---- STEP 4: EPUB3 nav ----
    @staticmethod
    def _resolve_nav(z, manifest, opf_dir):
        nav_item = None
        for m in manifest.values():
            props = m.get("properties")
            if props and "nav" in props.split():
                nav_item = m
                break
        if not nav_item or not nav_item.get("href"):
            return {}
        nav_key = norm(nav_item["href"], opf_dir)
        try:
            nav_raw = z.read(nav_key)
        except KeyError:
            return {}
        try:
            root = ET.fromstring(_strip_prolog(nav_raw.decode("utf-8", "replace")))
        except ET.ParseError:
            return {}
        # nav hrefs are relative to the NAV FILE's own dir, NOT opf_dir.
        nav_dir = posixpath.dirname(nav_key)
        # choose <nav epub:type contains 'toc'> else first <nav>
        navs = [el for el in root.iter() if ln(el) == "nav"]
        toc_nav = None
        for nv in navs:
            etype = _attr(nv, "type") or ""
            if "toc" in etype.split():
                toc_nav = nv
                break
        toc_nav = toc_nav or (navs[0] if navs else root)
        titles = {}
        for a in toc_nav.iter():
            if ln(a) == "a" and _attr(a, "href"):
                key = norm(_attr(a, "href"), nav_dir)
                title = _collapse_ws("".join(a.itertext()))
                if key and title:
                    titles.setdefault(key, title)
        return titles

    # ---- STEP 4: EPUB2 ncx fallback ----
    @staticmethod
    def _resolve_ncx(z, manifest, opf_dir, spine_toc_id):
        ncx = None
        if spine_toc_id and spine_toc_id in manifest:
            ncx = manifest[spine_toc_id]
        if not ncx:
            for m in manifest.values():
                if m.get("media_type") == "application/x-dtbncx+xml":
                    ncx = m
                    break
        if not ncx or not ncx.get("href"):
            return {}
        ncx_key = norm(ncx["href"], opf_dir)
        try:
            root = ET.fromstring(_strip_prolog(z.read(ncx_key).decode("utf-8", "replace")))
        except (KeyError, ET.ParseError):
            return {}
        titles = {}
        for np in root.iter():
            if ln(np) != "navPoint":
                continue
            label = None
            src = None
            for sub in np.iter():
                st = ln(sub)
                if st == "navLabel" and label is None:
                    txt = next((t for t in sub.iter() if ln(t) == "text"), None)
                    if txt is not None:
                        label = _collapse_ws(txt.text)
                elif st == "content" and src is None:
                    src = _attr(sub, "src")
            if label and src:
                # ncx src are opf-dir-relative
                key = norm(src, opf_dir)
                if key:
                    titles.setdefault(key, label)
        return titles

    # ---- STEP 6: title fallback ----
    @staticmethod
    def _h1_title(h_titles):
        """First <h1> then <h2> inner text, else '' (a trusted in-document heading)."""
        for want in ("h1", "h2"):
            for tag, t in h_titles:
                if tag == want and t:
                    return t
        return ""
