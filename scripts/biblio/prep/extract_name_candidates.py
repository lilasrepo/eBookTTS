# -*- coding: utf-8 -*-
"""extract_name_candidates -- surface likely CHARACTER NAMES from a built book as a worksheet.

This is the DETERMINISTIC half of the name-dictionary semi-automation (WORKFLOW-MAP step 1.2 /
"C"). It does NOT decide official names -- it hands a ranked candidate pool + sample contexts to
the LLM+human loop (see the biblio skill). Strategy:

  1. Dump any character-intro chapter (登場人物 / 人物介紹 / 角色 / キャラ...) verbatim -- the richest
     source of names, if the book has one.
  2. Score n-gram candidates: count 2-4 char Han tokens, then rank by a NAME SCORE = how often the
     token is immediately followed by a speech/action verb (說/道/問/笑/想...) or preceded by a quote
     opener -- characters speak and act, so this separates names from ordinary frequent phrases.

Reads <book>/out/*.md (preferred: clean Traditional) else <book>/source/. Writes
<book>/control/names_worksheet.md. Pure stdlib + the project's no-deps philosophy.

  python -X utf8 scripts/biblio/prep/extract_name_candidates.py <book_dir> [--min-count N] [--top K]
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

_HAN = r"一-鿿㐀-䶿"
_HAN_RUN = re.compile("[" + _HAN + "]{2,}")
# verbs/particles that typically FOLLOW a speaker/actor name -> strong name signal
_SPEECH_AFTER = "說説道問喊叫笑想覺答應點搖看著的桑君喵嘟"
_AFTER_RE = "[" + re.escape(_SPEECH_AFTER) + "]"
# a character-intro chapter heading
_CHAR_HEAD_RE = re.compile(r"(登場人物|出場人物|人物介紹|人物簡介|角色介紹|主要人物|キャラクター|人物關係)")
# frequent NON-name WORDS to suppress (function words / generic nouns). NOTE: this is a set
# of WORDS (split on spaces) -- a set("...") of one big string would be single CHARS and never
# match a multi-char token. A worksheet tolerates leftover noise (the LLM/human triages), so
# this only needs to clear the highest-frequency offenders, not be exhaustive.
_STOP = set((
    "自己 這麼 那麼 怎麼 什麼 可以 可能 應該 不能 不會 不要 沒有 沒錯 知道 覺得 感覺 看到 聽到 想到 感到 看見 聽見 "
    "這樣 那樣 怎樣 一樣 這種 那種 這些 那些 哪些 一些 一切 一直 一定 一點 一邊 一下 已經 現在 剛才 還是 還有 還會 "
    "只是 就是 不是 但是 可是 因為 所以 如果 雖然 不過 然後 於是 而且 或者 似乎 彷彿 好像 當然 果然 忽然 突然 終於 "
    "居然 竟然 其實 確實 也許 大概 或許 比較 更加 非常 十分 完全 出來 進來 起來 下來 上來 過來 回來 接著 立刻 馬上 "
    "我們 你們 他們 她們 它們 大家 對方 雙方 別人 有人 世界 時間 空間 時候 地方 東西 事情 問題 樣子 情況 狀況 狀態 "
    "身體 眼睛 腦袋 心裡 手中 面前 身後 周圍 前方 後方 旁邊 裡面 外面 上面 下面 前面 後面 表情 笑容 聲音 力量 能力 "
    "之後 之前 之間 以後 以前 之中 其中 部分 全部 整個 結果 原因 理由 目的 意思 意義 內容 開始 結束 繼續 真正 開口 "
    "說道 問道 笑道 喊道 答道 叫道 點了 不知 那個 這個 一個 兩個 幾個 多少"
).split())


def _read_book_text(book_dir):
    """Return list of (chapter_title, body) blocks from out/ (preferred) or source/."""
    blocks = []
    files = sorted(glob.glob(os.path.join(book_dir, "out", "*.md")))
    src = "out"
    if not files:
        files = sorted(glob.glob(os.path.join(book_dir, "source", "**", "*.md"), recursive=True))
        src = "source"
    for f in files:
        raw = open(f, encoding="utf-8").read()
        for part in re.split(r"(?m)^#\s+", raw)[1:] or [raw]:
            nl = part.find("\n")
            title = (part[:nl] if nl >= 0 else "").strip()
            body = part[nl + 1:] if nl >= 0 else part
            blocks.append((title, body))
    return blocks, src, len(files)


def _char_pages(blocks):
    return [(t, b) for t, b in blocks if _CHAR_HEAD_RE.search(t or "")]


def _score_candidates(text, min_count):
    """Count 2-4 char Han n-grams; rank by name-score (followed by a speech/action verb).

    Two precision filters: (1) name-score>0 -- the token is at least once followed by a
    speech/action verb (characters speak/act); (2) left-neighbor diversity>=4 -- a real name
    follows many different chars, whereas a word-fragment (界裡 inside 世界裡) almost always
    follows the SAME char, so low left-diversity = not a standalone token (branching entropy).
    """
    counts = Counter()
    name_hits = Counter()
    left = {}
    for m in _HAN_RUN.finditer(text):
        run = m.group(0)
        L = len(run)
        for n in (2, 3, 4):
            for i in range(L - n + 1):
                tok = run[i:i + n]
                counts[tok] += 1
                if i > 0:
                    left.setdefault(tok, set()).add(run[i - 1])
                else:
                    left.setdefault(tok, set()).add("^")    # run boundary = a distinct left ctx
                j = i + n
                if j < L and re.match(_AFTER_RE, run[j]):
                    name_hits[tok] += 1
    cands = []
    for tok, c in counts.items():
        if c < min_count or tok in _STOP:
            continue
        nh = name_hits.get(tok, 0)
        if nh == 0 or len(left.get(tok, ())) < 4:
            continue
        cands.append((tok, c, nh))
    cands.sort(key=lambda x: (-x[2], -x[1]))
    return cands


def _dedupe_substrings(cands):
    """Collapse a shorter candidate into a longer one it is contained in when their counts are
    close (絲娜⊂亞絲娜, both ~2122; but keep 拉姆 even though 拉姆姆 exists if 拉姆 is far more common).
    Prefer the LONGER form as the canonical name."""
    by_len = sorted(cands, key=lambda x: -len(x[0]))
    kept = []
    for tok, c, nh in by_len:
        covered = next((k for k, kc, _ in kept if tok in k and tok != k and c <= kc * 1.15), None)
        if covered:
            continue
        kept.append((tok, c, nh))
    kept.sort(key=lambda x: (-x[2], -x[1]))
    return kept


def _sample(text, tok):
    i = text.find(tok)
    if i < 0:
        return ""
    s = text[max(0, i - 14):i + len(tok) + 14].replace("\n", " ")
    return s.strip()


def build_worksheet(book_dir, min_count=8, top=80):
    book_dir = os.path.abspath(book_dir)
    blocks, src, nfiles = _read_book_text(book_dir)
    if not blocks:
        raise SystemExit("no text found under %s (out/ or source/)" % book_dir)
    full = "\n".join(b for _, b in blocks)
    char_pages = _char_pages(blocks)
    cands = _dedupe_substrings(_score_candidates(full, min_count))[:top]

    out = []
    out.append("# 人名字典工作表 — %s" % os.path.basename(book_dir))
    out.append("")
    out.append("> 來源:%d 個 %s 檔,%d 字。這是**候選池**,非定論。" % (nfiles, src, len(full)))
    out.append("> 流程:Claude 讀此表 + 下方角色頁/例句 → 產 `control/names.tsv`"
               "(`katakana⇥romaji⇥official⇥variants`,前兩欄可留空)→ 沒把握的落 `name_gaps.md` 給人裁定。")
    out.append("")
    if char_pages:
        out.append("## 角色介紹頁(最可靠的名字來源)")
        for t, b in char_pages:
            out.append("### %s" % t)
            out.append(b.strip()[:4000])
            out.append("")
    else:
        out.append("## 角色介紹頁:無(本書無 登場人物 章;改用下方候選 + 抽樣)")
        out.append("")
    out.append("## 候選名(依 name-score 排序:後接 說/道/問… 的次數越高越像人名)")
    out.append("")
    out.append("| 候選 | 出現 | name-score | 例句 |")
    out.append("|---|---|---|---|")
    for tok, c, nh in cands:
        out.append("| %s | %d | %d | …%s… |" % (tok, c, nh, _sample(full, tok)))
    text = "\n".join(out) + "\n"

    cdir = os.path.join(book_dir, "control")
    os.makedirs(cdir, exist_ok=True)
    path = os.path.join(cdir, "names_worksheet.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path, len(cands), len(char_pages)


def main():
    ap = argparse.ArgumentParser(prog="extract_name_candidates")
    ap.add_argument("book_dir")
    ap.add_argument("--min-count", type=int, default=8, help="min occurrences to consider (default 8)")
    ap.add_argument("--top", type=int, default=80, help="max candidates to list (default 80)")
    a = ap.parse_args()
    path, ncand, npages = build_worksheet(a.book_dir, a.min_count, a.top)
    print("[names] worksheet -> %s | %d candidates | %d character page(s)" % (path, ncand, npages))


if __name__ == "__main__":
    main()
