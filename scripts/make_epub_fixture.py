# -*- coding: utf-8 -*-
"""Build a MINIMAL valid EPUB3 fixture (stdlib zipfile) + a frozen golden .md, then
self-test the EpubAdapter end-to-end (STEPS 1-9).

Outputs:
  book/_fixtures/sample/source/sample.epub
  book/_fixtures/sample/book.json            (convert:"none", author:"測試", tts dual 32k)
  book/_fixtures/sample/expected.md          (FROZEN golden -- self-test diffs against this)

EPUB layout: mimetype stored-first (ZIP_STORED, no extra field), container.xml,
OEBPS/content.opf (manifest+spine), OEBPS/nav.xhtml (EPUB3 nav), and chapters:
  cover.xhtml   image-only (no <p>)        -> SKIPPED (no speakable text)
  序.xhtml      <section><h1>序</h1><p>..>  -> kept (title from nav)
  ch1.xhtml     正文                        -> kept
  credits.xhtml 製作人員 (credit blurb)     -> SKIPPED (strip_credits)

Run:  python -X utf8 scripts/make_epub_fixture.py
"""
import json
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOOK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX_DIR = os.path.join(BOOK_ROOT, "book", "_fixtures", "sample")
SRC_DIR = os.path.join(FIX_DIR, "source")
EPUB_PATH = os.path.join(SRC_DIR, "sample.epub")

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:sample-0001</dc:identifier>
    <dc:title>樣本書 第 1 卷</dc:title>
    <dc:language>zh-TW</dc:language>
    <dc:creator id="aut">測試</dc:creator>
    <meta refines="#aut" property="role">aut</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="xu" href="%E5%BA%8F.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="credits" href="credits.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="cover"/>
    <itemref idref="xu"/>
    <itemref idref="ch1"/>
    <itemref idref="credits"/>
  </spine>
</package>
"""

# nav hrefs include a percent-encoded CJK filename to exercise norm()'s unquote.
NAV = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>目次</title></head>
<body>
  <nav epub:type="toc">
    <ol>
      <li><a href="%E5%BA%8F.xhtml">序</a></li>
      <li><a href="ch1.xhtml">第一章</a></li>
    </ol>
  </nav>
</body>
</html>
"""

COVER = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>封面</title></head>
<body><div><img src="cover.jpg" alt=""/></div></body>
</html>
"""

XU = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>序</title></head>
<body><section><h1>序</h1>
<p>那是夏日的一天。</p>
<p>燦爛而明媚的晴空。</p>
</section></body>
</html>
"""

CH1 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>第一章</title></head>
<body><section><h1>第一章</h1>
<p>「早安。」她說。</p>
<p>故事就此展開。</p>
</section></body>
</html>
"""

CREDITS = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>製作人員</title></head>
<body><section><h1>製作人員</h1>
<p>本電子書僅供學習交流，嚴禁用於商業用途。</p>
</section></body>
</html>
"""

BOOK_JSON = {
    "slug": "sample",
    "title": "樣本書",
    "author": "測試",
    "lang": "zh",
    "convert": "none",
    "strip_media": True,
    "strip_credits": True,
    "strip_editor_notes": False,
    "names_tsv": None,
    "tts": {
        "mode": "dual",
        "narration": "zh-TW-HsiaoChenNeural",
        "dialogue": "zh-CN-XiaoyiNeural",
        "rate": "+10%",
        "format": {"bitrate": "32k", "channels": 1, "sample_rate": 24000},
        "gap_ms": 250,
    },
}


_EPOCH = (1980, 1, 1, 0, 0, 0)   # fixed zip timestamp -> deterministic epub bytes (else
                                 # writestr stamps NOW and the tracked fixture shows as
                                 # modified after every regen / regress run)


def _zi(name, stored=False):
    zi = zipfile.ZipInfo(name, date_time=_EPOCH)
    zi.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    return zi


def write_epub():
    os.makedirs(SRC_DIR, exist_ok=True)
    with zipfile.ZipFile(EPUB_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype MUST be first and STORED with no extra field.
        z.writestr(_zi("mimetype", stored=True), "application/epub+zip")
        z.writestr(_zi("META-INF/container.xml"), CONTAINER)
        z.writestr(_zi("OEBPS/content.opf"), OPF)
        z.writestr(_zi("OEBPS/nav.xhtml"), NAV)
        z.writestr(_zi("OEBPS/cover.xhtml"), COVER)
        z.writestr(_zi("OEBPS/序.xhtml"), XU)     # 序.xhtml (real CJK zip name)
        z.writestr(_zi("OEBPS/ch1.xhtml"), CH1)
        z.writestr(_zi("OEBPS/credits.xhtml"), CREDITS)


def write_book_json():
    with open(os.path.join(FIX_DIR, "book.json"), "w", encoding="utf-8") as fh:
        json.dump(BOOK_JSON, fh, ensure_ascii=False, indent=2)


def derive_expected():
    """Parse the fixture with the adapter + render via the build pipeline, freeze as golden."""
    from biblio.ingest.epub import EpubAdapter
    from biblio.build import _render_chapter
    from biblio.config import load_book_config
    cfg = load_book_config(FIX_DIR)
    doc = EpubAdapter().parse(EPUB_PATH)
    blocks = [_render_chapter(ch, "none", cfg) for ch in doc.chapters]
    blocks = [b for b in blocks if b.strip()]
    text = "\n\n".join(blocks)
    if text and not text.endswith("\n"):
        text += "\n"
    return doc, text


def main():
    write_epub()
    write_book_json()
    doc, text = derive_expected()
    expected_path = os.path.join(FIX_DIR, "expected.md")
    freeze = "--freeze" in sys.argv or not os.path.exists(expected_path)
    if freeze:
        with open(expected_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("[fixture] wrote", EPUB_PATH)
        print("[fixture] froze golden", expected_path)
    # ---- self-test (STEPS 1-9) ----
    titles = [c.title for c in doc.chapters]
    assert titles == ["序", "第一章"], "chapter titles mismatch: %r" % (titles,)
    assert all("製作人員" not in c.title for c in doc.chapters), "credits leaked"
    assert all("封面" not in c.title for c in doc.chapters), "cover leaked"
    # no Simplified leakage (convert:none passthrough; source is already zh-TW)
    import opencc
    s2tw = opencc.OpenCC("s2tw")
    residual = sum(1 for a, b in zip(text, s2tw.convert(text)) if a != b and "一" <= a <= "鿿")
    assert residual == 0, "residual Simplified chars: %d" % residual
    with open(expected_path, encoding="utf-8") as fh:
        golden = fh.read()
    assert text == golden, "OUTPUT DIFFERS FROM GOLDEN expected.md (byte-for-byte)"
    print("[self-test] PASS | chapters=%r | residual-Simplified=0 | golden byte-identical" % (titles,))


if __name__ == "__main__":
    main()
