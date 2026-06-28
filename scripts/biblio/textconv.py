# -*- coding: utf-8 -*-
"""Generic text transforms for the biblio pipeline.

GENERIC subset of convert.py's proven logic. Does NOT import legacy fan-translation-only steps
(jp_patch / NAME_SYLLABLES / NICK / repair_names / strip_tl). convert:"none" is a
true passthrough and is never routed through an OpenCC instance.
"""
import os
import re

_CC_CACHE = {}


# Surgical fixes for OpenCC word-segmentation mis-picks that occur AFTER s2twp/s2tw.
# Each entry is (compiled pattern, replacement). Rules must be context-bound so they
# NEVER touch a legitimately-converted word -- e.g. 捲髮 (curly hair) is correct and is
# left alone; only "第N捲" (a book VOLUME mis-read as the 捲 of 捲髮) is rerouted to 卷,
# and the "卷发售" -> mis-"捲髮售" chain further fixes 髮售 -> 發售. Applied only when a
# real conversion ran (mode != none); a no-op on already-correct Traditional sources.
_POSTFIX_RULES = [
    # 第N卷发售 -> wrongly 第N捲髮售 : restore both the 卷 and the 發.
    (re.compile(r"(第[一二三四五六七八九十百0-9]+)捲髮(?=[售行])"), r"\1卷發"),
    # 第N卷 (book volume) wrongly 第N捲 — 捲 here is never "curly".
    (re.compile(r"(第[一二三四五六七八九十百0-9]+)捲"), r"\1卷"),
    # standalone 髮售/髮行 (發售/發行 mis-pick) not caught above.
    (re.compile(r"髮(?=[售行])"), "發"),
]


def _postfix(text):
    """Apply surgical post-OpenCC segmentation fixes (see _POSTFIX_RULES)."""
    for pat, repl in _POSTFIX_RULES:
        text = pat.sub(repl, text)
    return text


def opencc_convert(text, mode):
    """Simplified->Traditional. mode: s2twp | s2tw | none(passthrough).

    none -> returns the SAME object (identity); never constructs OpenCC.
    """
    if mode == "none" or not mode:
        return text
    if mode not in ("s2twp", "s2tw"):
        raise ValueError("unsupported convert mode: %r" % (mode,))
    cc = _CC_CACHE.get(mode)
    if cc is None:
        import opencc
        cc = opencc.OpenCC(mode)
        _CC_CACHE[mode] = cc
    return _postfix(cc.convert(text))


def count_residual_simplified(text):
    """Length-preserving s2tw diff: count CJK chars that STILL differ after a char-level
    Traditional conversion. NOISY: also flags Traditional orthographic VARIANTS the publisher
    legitimately chose (台/臺, 爲/為, 只/隻, 里/裡...), so a nonzero count is NOT by itself an
    error. Use count_simplified_markers() for the real "is this Simplified?" signal.
    """
    cc = _CC_CACHE.get("s2tw")
    if cc is None:
        import opencc
        cc = opencc.OpenCC("s2tw")
        _CC_CACHE["s2tw"] = cc
    conv = cc.convert(text)
    return sum(1 for a, b in zip(text, conv) if a != b and "一" <= a <= "鿿")


# Simplified ALARM (review signal only -- there is NO reliable auto-fix). OpenCC's own dict
# treats publisher-variant chars (台/里/干/斗/伙/游...) as "Simplified->Traditional" exactly
# like real Simplified (没/猫/来), so the two are not algorithmically separable. We therefore
# do NOT auto-convert in convert:none mode; the convert knob is the only conversion control.
# count_simplified_markers is a CONSERVATIVE, high-precision detector: a char counts only if
# s2t changes it AND it is not itself a Traditional char (not a TSCharacters key) AND s2tw
# also changes it AND it is not in the hand-blacklist of TW-valid variants below. markers>0
# => real Simplified almost certainly present; markers==0 does NOT guarantee zero (rare
# variant-confusable chars are deliberately excluded to keep precision high). To force
# Traditional, set book.json convert to s2tw/s2twp.
_SIMP_BLACKLIST = set(
    "霉准几游占抛里伙采托征郁后台斗干凶丑据岩着适种余脚筑于厘划刹踪雇咨尸栖撑奥"
    "泄痹棱胜祢虱爲污癡祕纔脣麽僞啓吁丢岳云"
)
_TS_KEYS = None
_SIMP_DECISION = {}


def _cc(mode):
    cc = _CC_CACHE.get(mode)
    if cc is None:
        import opencc
        cc = opencc.OpenCC(mode)
        _CC_CACHE[mode] = cc
    return cc


def _ts_keys():
    """Set of Traditional chars (keys of OpenCC TSCharacters.txt); empty if unavailable."""
    global _TS_KEYS
    if _TS_KEYS is None:
        _TS_KEYS = set()
        try:
            import opencc
            p = os.path.join(os.path.dirname(opencc.__file__), "dictionary", "TSCharacters.txt")
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        _TS_KEYS.add(line.split("\t")[0])
        except Exception:
            _TS_KEYS = set()
    return _TS_KEYS


def _is_simplified_char(c):
    d = _SIMP_DECISION.get(c)
    if d is None:
        if c in _SIMP_BLACKLIST or not ("一" <= c <= "鿿"):
            d = False
        else:
            d = (_cc("s2t").convert(c) != c and c not in _ts_keys()
                 and _cc("s2tw").convert(c) != c)
        _SIMP_DECISION[c] = d
    return d


def count_simplified_markers(text):
    """Conservative, high-precision count of REAL Simplified chars (see _SIMP_BLACKLIST note).
    A review flag, not a gate: >0 means real Simplified is almost certainly present."""
    return sum(1 for c in text if _is_simplified_char(c))


def list_simplified_markers(text):
    """{char: count} of detected Simplified chars, for reporting/adjudication."""
    out = {}
    for c in text:
        if _is_simplified_char(c):
            out[c] = out.get(c, 0) + 1
    return out


def strip_media(text):
    """Drop image links + leftover structural HTML, keep prose (mirror convert.strip_media)."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"<img\b[^>]*>", "", text)
    text = re.sub(r"</?a\b[^>]*>", "", text)
    text = re.sub(r"/res/imgs/\S*", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</?(?:ul|ol|li|details|summary|div|span|p)\b[^>]*>", "", text)
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*){2,}", "\n\n", text)
    return text


# editor/translator role token required before the colon so plain parenthetical prose
# is preserved; tolerates ONE level of nested parens inside the note.
_NOTE_ROLE = r"(?:編註|編注|编注|编註|譯註|譯注|译注|译註|譯者註|譯者注|作者註|作者注|校註|校注|校对|校對)"
_NOTE_INNER = r"(?:[^（）()]|[（(][^（）()]*[）)])*"
_EDITOR_NOTE_RE = re.compile(r"[（(]\s*" + _NOTE_ROLE + r"\s*[:：]" + _NOTE_INNER + r"[）)]")


def strip_editor_notes(text):
    """Remove （編註：…）/（譯註：…）/(編註:...) notes incl 1-level nested parens.

    GENERIC util (NOT the legacy strip_tl). Requires an editor/translator role token before
    the colon so plain parenthetical prose is preserved.
    """
    return _EDITOR_NOTE_RE.sub("", text)


def _load_names(names_tsv_path):
    """Build {variant: official} from names.tsv (katakana\\tromaji\\tofficial\\tvariants)."""
    mapping = {}
    if not names_tsv_path or not os.path.exists(names_tsv_path):
        return mapping
    with open(names_tsv_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        official = cols[2].strip()
        if not official:
            continue
        variants = cols[3] if len(cols) > 3 else ""
        keys = [official] + [v.strip() for v in variants.split(",")]
        for k in keys:
            if k and len(k) >= 2:
                mapping.setdefault(k, official)
    return mapping


def apply_names(text, names_tsv_path):
    """Longest-first single-pass variant->official replacement."""
    mapping = _load_names(names_tsv_path)
    if not mapping:
        return text
    keys = sorted(mapping, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) for k in keys))
    return pat.sub(lambda m: mapping[m.group(0)], text)


# ============================================================================
# Optional fan-translation steps (ported from the legacy fan-translation pipeline, now data-driven
# and gated by book.json). All three are OFF unless their config key is set, so a
# clean source's output is byte-identical with or without this block.
# ============================================================================

_JP_CACHE = {}
_SYL_CACHE = {}


def _load_jp_patches(path):
    """Load jp_patches.tsv (jp\\tzh); longest-jp-first so longer phrases win."""
    pats = []
    if not path or not os.path.exists(path):
        return pats
    with open(path, encoding="utf-8") as fh:
        for line in fh.read().splitlines()[1:]:
            if "\t" in line:
                jp, zh = line.split("\t", 1)
                if jp and zh and jp != zh:
                    pats.append((jp, zh))
    return sorted(pats, key=lambda kv: -len(kv[0]))


def jp_patch(text, jp_patches_path):
    """Fill the fan-TL's untranslated Japanese lines. MUST run BEFORE OpenCC.

    Data-driven by jp_patches.tsv (jp\\tzh). A no-op when the file is missing/empty.
    """
    if jp_patches_path not in _JP_CACHE:
        _JP_CACHE[jp_patches_path] = _load_jp_patches(jp_patches_path)
    for jp, zh in _JP_CACHE[jp_patches_path]:
        if jp in text:
            text = text.replace(jp, zh)
    return text


# --- strip_credit_lines: drop a stray scanlation/typeset credit FOOTER line (圖源:/錄入:/
# 掃圖:/譯者:...) that rides along inside a real chapter. A standalone credits PAGE is already
# dropped by the epub adapter; this catches the lines that don't sit on their own page (e.g.
# a 蛇足篇 short-story ends with "圖源：halo"). KEEPS 作者/插畫 (genuine book credit -- not in
# the role set). Always-on (credit removal is not a per-book toggle). HIGH PRECISION: a line
# must BEGIN with a credit-role label + separator, so prose mentioning 校對/維基百科 or an
# in-world currency table (王鈔　五萬) is never touched -- that over-reach is exactly why the
# broader strip_tl (which kills any line containing 維基百科/URL) is NOT used for clean sources.
_CREDIT_LINE_ROLE = (
    r"(?:圖源|图源|錄入|录入|掃圖|扫图|修圖|修图|嵌字|校對|校对|譯者|译者|轉載|转载|轉錄|转录"
    r"|時軸|时轴|後期|后期|監製|监制|渣翻|機翻|机翻|個人漢化|个人汉化|個人汉化)"
)
_CREDIT_LINE = re.compile(
    r"(?m)^[ \t　]*" + _CREDIT_LINE_ROLE
    + r"(?:[ \t　]*[＆&、,，/／・]+[ \t　]*" + _CREDIT_LINE_ROLE + r")*"
    + r"[ \t　]*[:：／/＆&][^\n]*$"
)


def strip_credit_lines(text):
    """Remove scanlation/typeset credit footer lines (圖源:/錄入:/掃圖:/譯者:...); keep 作者/插畫."""
    text = _CREDIT_LINE.sub("", text)
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*){2,}", "\n\n", text)   # collapse blank runs left behind
    return text


# --- strip_tl: remove fan-TL credits / promo / translator notes. Runs AFTER OpenCC,
# so every marker is Traditional. High precision: inline note parens require a
# role+colon INSIDE; whole-line drops require the line to BE a credit/note. Verbatim
# port of the legacy strip_tl -- generic to CN fan-translations, not source-specific.
_TL_ROLE = r"(?:譯註|譯注|译注|译註|譯者註|譯者注|作者註|作者注|潤色|润色|校對|校对|翻譯|翻译|嵌字|錄入|录入|注|註|PS|ps)"
_in0 = r"[（(][^（）()]*[）)]"
_in1 = r"[（(](?:[^（）()]|" + _in0 + r")*[）)]"
_TL_INLINE = re.compile(r"[（(]\s*" + _TL_ROLE + r"\s*[:：](?:[^（）()]|" + _in1 + r")*[）)]")
_TL_SLASH = re.compile(r"[/／]\s*" + _TL_ROLE + r"\s*[:：][^/／\n]*[/／]")
_TL_BRACKET = re.compile(r"「\s*" + _TL_ROLE + r"\s*[:：][^」\n]*」")
_TL_UNCLOSED = re.compile(r"[（(]\s*" + _TL_ROLE + r"\s*[:：][^\n]*$", re.M)
_TL_ZANYI = re.compile(r"[（(]\s*(?:暫譯|暂译)[^（）()]*[）)]")
_TL_LINE = re.compile(
    r"^\s*(?:"
    r"(?:翻譯|翻译|校對|校对|潤色|润色|嵌字|錄入|录入|圖源|图源|時軸|时轴|後期|后期|監製|监制|翻校|渣翻|機翻|個人漢化|个人汉化)\s*[:：].*"
    r"|(?:譯註|譯注|译注|译註)\s*[:：].*"
    r"|僅供學習.*|仅供学习.*|嚴禁用於商.*|严禁用于商.*"
    r"|Fandom\s*Image\s*"
    r"|.*(?:置頂公告|置顶公告).*"
    r"|\(?bilibili\.com\)?\S*.*|動態-?嗶哩嗶哩.*|动态-?哔哩哔哩.*"
    r"|.*https?://.*|.*維基百科.*"
    r"|.*官方譯名.*|.*暫譯為.*|.*譯文中.*"
    r")$")


def strip_tl(text):
    """Drop fan-TL signatures/promo/notes; keep story prose. Run AFTER OpenCC."""
    text = _TL_INLINE.sub("", text)
    text = _TL_SLASH.sub("", text)
    text = _TL_BRACKET.sub("", text)
    text = _TL_ZANYI.sub("", text)
    text = _TL_UNCLOSED.sub("", text)
    text = "\n".join(ln for ln in text.split("\n") if not _TL_LINE.match(ln))
    text = re.sub(r"[ \t　]{2,}", " ", text)
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*){2,}", "\n\n", text)
    return text


# --- repair_names: homophone-variant (同音異譯) + pause-split name repair. Runs
# AFTER apply_names to catch forms the exact dict missed. Data-driven by
# name_syllables.tsv: each row = official\tg1|g2|... where each group is the set of
# interchangeable Traditional chars for that syllable (e.g. 愛蜜莉雅\t愛艾|蜜米密|莉|雅婭亞).
_SEP = r"[ \t　\.．。…‥・ー—\-、，,─＝]"


def _load_name_syllables(path):
    """Parse name_syllables.tsv -> {official: [[chars],...]}."""
    table = {}
    if not path or not os.path.exists(path):
        return table
    with open(path, encoding="utf-8") as fh:
        for line in fh.read().splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            official = cols[0].strip()
            groups = [list(g) for g in cols[1].strip().split("|") if g]
            if official and groups:
                table[official] = groups
    return table


def _mkre(syls):
    # split across inline pause punctuation allowed only on 3+ syllable names.
    # re.escape each group char so a stray -, ], ^ or \ in the TSV can't form a range/negation.
    gap = _SEP + "{0,4}" if len(syls) >= 3 else ""
    return re.compile(gap.join("[" + "".join(re.escape(ch) for ch in s) + "]" for s in syls))


def _build_repair(table):
    rules = sorted(((off, _mkre(s)) for off, s in table.items()), key=lambda x: -len(x[0]))
    return rules, set(table)


def repair_names(text, name_syllables_path):
    """Collapse homophone/pause-split name variants to the official form."""
    if name_syllables_path not in _SYL_CACHE:
        _SYL_CACHE[name_syllables_path] = _build_repair(_load_name_syllables(name_syllables_path))
    rules, offsets = _SYL_CACHE[name_syllables_path]
    for off, rx in rules:
        def repl(m, off=off):
            s = m.group(0)
            if s == off:
                return off
            clean = re.sub(_SEP + r"+", "", s)
            if clean != off and clean in offsets:   # a *different* official name -> leave alone
                return s
            return off
        text = rx.sub(repl, text)
    return text
