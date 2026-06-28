# -*- coding: utf-8 -*-
"""build_audiobook: <book_dir>/out/*.md -> <book_dir>/audiobook/<stem>/NNN_title.mp3.

Adapts tts_build.py mechanics, parameterized by cfg.tts + book_dir:
  - dual/single voice split (narration vs 「」『』 dialogue)
  - edge-tts atomic synth (.part->rename) + exponential backoff, skip-existing resume
  - ffmpeg silence(gap_ms) inserted at run boundaries; ffmpeg concat re-encode to
    cfg.tts.format; ID3 TPE1 = cfg.author ONLY.
  - only_source restricts to one volume; only_chapter restricts to one chapter (smoke test).
"""
import asyncio
import glob
import os
import random
import re
import subprocess

from .config import load_book_config

_DIALOGUE_RE = re.compile(r"([^「『]*)([「『][^」』]*[」』])?")
_SPEAKABLE = re.compile(r"[0-9A-Za-z぀-ヿ一-鿿가-힣]")
_SENT_RE = re.compile(r"(?<=[。！？!?…」』])")
_MAXLEN = 4500


def _normalize(t):
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    t = re.sub(r"[─―—]+", "", t)        # decorative dashes ─ ― —
    t = t.replace("\n", " ").replace("\t", " ").replace("・", " ")  # 中点 ・
    return re.sub(r"\s+", " ", t).strip()


def _chunk(text, maxlen=_MAXLEN):
    text = text.strip()
    if not text:
        return []
    if len(text) <= maxlen:
        return [text]
    out, cur = [], ""
    for s in _SENT_RE.split(text):
        if not s:
            continue
        if len(cur) + len(s) <= maxlen:
            cur += s
        else:
            if cur:
                out.append(cur)
            while len(s) > maxlen:
                out.append(s[:maxlen]); s = s[maxlen:]
            cur = s
    if cur:
        out.append(cur)
    return out


def _spans_dual(body, tts):
    sp = []
    for narr, dial in _DIALOGUE_RE.findall(body):
        if narr.strip():
            sp.append((tts["narration"], _normalize(narr)))
        if dial:
            sp.append((tts["dialogue"], _normalize(dial.strip("「』」『"))))
    return [(v, t) for v, t in sp if t]


def _spans_single(body, tts):
    t = _normalize(body)
    return [(tts["narration"], t)] if t else []


def _merge_runs(spans):
    runs = []
    for v, t in spans:
        if runs and runs[-1][0] == v:
            runs[-1][1] += " " + t
        else:
            runs.append([v, t])
    return runs


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()[:60] or "untitled"


def _load_chapters(md_path):
    """Split one volume .md into (title, body) on '# ' headings (mirror tts_build)."""
    with open(md_path, encoding="utf-8") as fh:
        raw = fh.read()
    blocks = re.split(r"(?m)^#\s+", raw)
    chapters = []
    for b in blocks[1:]:
        nl = b.find("\n")
        title = (b[:nl] if nl >= 0 else b).strip()
        body = b[nl + 1:] if nl >= 0 else ""
        body = re.sub(r"^\s*-{3,}\s*", "", body)
        chapters.append((title, body))
    return chapters


def _ffmpeg_enc(fmt):
    return ["-c:a", "libmp3lame", "-b:a", fmt.get("bitrate", "32k"),
            "-ac", str(fmt.get("channels", 1)), "-ar", str(fmt.get("sample_rate", 24000))]


def _ensure_silence(work_dir, gap_ms):
    if gap_ms <= 0:
        return None
    sildir = os.path.join(work_dir, "_sil")
    os.makedirs(sildir, exist_ok=True)
    p = os.path.join(sildir, "sil_%d.mp3" % gap_ms)
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
                        "-t", "%.3f" % (gap_ms / 1000.0), "-c:a", "libmp3lame",
                        "-b:a", "48k", p], check=True, capture_output=True)
    return p


def _plan_volume(md_path, audio_root, tts, only_chapter=None):
    stem = os.path.splitext(os.path.basename(md_path))[0]
    finaldir = os.path.join(audio_root, stem)
    workdir = os.path.join(audio_root, "_work", stem)
    chapters = _load_chapters(md_path)
    mode = tts.get("mode", "dual")
    plan = []
    for ci, (title, body) in enumerate(chapters, 1):
        if only_chapter is not None and ci != only_chapter:
            continue
        spans = _spans_single(body, tts) if mode == "single" else _spans_dual(body, tts)
        spans = _merge_runs(spans)
        segs = []
        sidx = 0
        for ri, (v, t) in enumerate(spans):
            for piece in _chunk(t):
                if _SPEAKABLE.search(piece):
                    segs.append(dict(text=piece, voice=v, rate=tts.get("rate", "+10%"),
                                     run=ri,
                                     out=os.path.join(workdir, "c%03d" % ci, "s%04d.mp3" % sidx)))
                sidx += 1
        if segs:
            plan.append(dict(idx=ci, title=title, segs=segs,
                             mp3=os.path.join(finaldir, "%03d_%s.mp3" % (ci, _safe(title)))))
    return dict(stem=stem, dir=finaldir, chapters=plan)


async def _synth(seg, sem, retries=6):
    import edge_tts
    out = seg["out"]
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return ("skip", out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    async with sem:
        tmp = out + ".part"
        delay = 4.0
        last = "?"
        for attempt in range(1, retries + 1):
            try:
                await edge_tts.Communicate(seg["text"], seg["voice"], rate=seg["rate"]).save(tmp)
                if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    os.replace(tmp, out)
                    return ("ok", out)
                last = "empty file"
            except Exception as e:
                last = str(e)[:140]
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < retries:
                await asyncio.sleep(delay + random.uniform(0, 1.0))
                delay = min(delay * 2, 60)
        return ("fail", "%s :: %s" % (out, last))


def _concat(parts, out_path, enc):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    listfile = out_path + ".txt"
    with open(listfile, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % os.path.abspath(p).replace("\\", "/"))
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", listfile] + enc + [out_path], capture_output=True)
    os.remove(listfile)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-400:])


def _chapter_parts(segs, sil):
    parts, prev = [], None
    for s in segs:
        if not (os.path.exists(s["out"]) and os.path.getsize(s["out"]) > 0):
            continue
        if prev is not None and s["run"] != prev and sil:
            parts.append(sil)
        parts.append(s["out"]); prev = s["run"]
    return parts


def _tag(mp3, title, album, idx, artist):
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TALB, TRCK, TCON, TPE1
        a = MP3(mp3, ID3=ID3)
        if a.tags is None:
            a.add_tags()
        a.tags.add(TIT2(encoding=3, text=title))
        a.tags.add(TALB(encoding=3, text=album))
        a.tags.add(TRCK(encoding=3, text=str(idx)))
        a.tags.add(TCON(encoding=3, text="Audiobook"))
        a.tags.add(TPE1(encoding=3, text=artist or ""))   # TPE1 = cfg.author ONLY
        a.save()
    except Exception as e:
        print("    [tag warn] %s: %s" % (os.path.basename(mp3), e))


def _duration(mp3):
    try:
        from mutagen.mp3 import MP3
        return MP3(mp3).info.length
    except Exception:
        return 0.0


async def _run(cfg, only_source, only_chapter):
    book_dir = cfg["book_dir"]
    tts = cfg["tts"]
    out_glob = os.path.join(book_dir, "out", "*.md")
    files = sorted(glob.glob(out_glob))
    if only_source:
        needle = only_source.lower()
        files = [f for f in files if needle in os.path.basename(f).lower()]
    if not files:
        print("no matching %s" % out_glob)
        return {"volumes": []}

    audio_root = os.path.join(book_dir, "audiobook")
    enc = _ffmpeg_enc(tts.get("format", {}))
    sil = _ensure_silence(os.path.join(audio_root, "_work"), tts.get("gap_ms", 250))
    sem = asyncio.Semaphore(12)
    artist = cfg.get("author")

    manifest = {"book_dir": book_dir, "volumes": []}
    for md in files:
        vp = _plan_volume(md, audio_root, tts, only_chapter=only_chapter)
        all_segs = [s for ch in vp["chapters"] for s in ch["segs"]]
        print("\n=== %s | %d章 | %d段 | mode=%s ===" %
              (vp["stem"], len(vp["chapters"]), len(all_segs), tts.get("mode", "dual")))
        tasks = [asyncio.create_task(_synth(s, sem)) for s in all_segs]
        done = {"ok": 0, "skip": 0, "fail": 0}
        for fut in asyncio.as_completed(tasks):
            status, _info = await fut
            done[status] += 1
        chap_mp3s, total = [], 0.0
        for ch in vp["chapters"]:
            parts = _chapter_parts(ch["segs"], sil)
            if not parts:
                continue
            _concat(parts, ch["mp3"], enc)
            _tag(ch["mp3"], ch["title"], vp["stem"], ch["idx"], artist)
            d = _duration(ch["mp3"]); total += d; chap_mp3s.append(ch["mp3"])
        print("    %d chapter mp3 | %.1f min | synth %s" % (len(chap_mp3s), total / 60.0, done))
        manifest["volumes"].append({"name": vp["stem"], "chapters": len(chap_mp3s),
                                    "minutes": round(total / 60.0, 1)})
    return manifest


def build_audiobook(book_dir, only_source=None, only_chapter=None):
    """Synthesize an audiobook for a book dir. Returns a manifest dict."""
    cfg = load_book_config(book_dir)
    return asyncio.run(_run(cfg, only_source, only_chapter))
