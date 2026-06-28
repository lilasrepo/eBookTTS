# biblio — 多格式書籍 → 繁體中文分卷 .md(+ 有聲書)引擎

把任何書(epub / 漢化 .md / txt / 連載話檔)轉成**繁體中文、依卷或話分檔的 Markdown**,人名對齊**官方台版譯名**,並可選產出有聲書。一本書一個資料夾 `book/<slug>/`,設定在各自 `book.json`。

核心原則:**內文永不過 LLM**(怕漏譯/改寫)。轉換用 OpenCC(規則字典、確定性、免費、可無限重跑);LLM 只用在「建人名字典 / 補殘留日文 / 查官方卷界」這類 metadata 研究,凍進 `control/*.tsv`。

## 安裝
```bash
pip install -r requirements.txt        # opencc + edge-tts + mutagen
# 另需系統 ffmpeg 在 PATH(僅 tts 用)。Windows 主控台一律 python -X utf8。
```

## 完整流程

```
階段 0  環境(一次)  pip install -r requirements.txt + ffmpeg
階段 1  加書         ① source/ 放料  ② 寫 book.json(source_type/output_unit/convert)
                     ③ (web+卷)寫 control/volumes.tsv:話→卷
階段 2  人名字典      只有「髒源/漢化」需要;唯一花 LLM token 的步驟 —— 見「流程 B」
階段 3  建置         biblio_cli build  → out/<id>_<label>.md + build/manifest.json
階段 4  驗證         biblio_cli verify → 殘簡 marker / 章數 drop-guard / 字數
階段 5  回歸 gate    regress.py(改引擎後必跑)
階段 6  有聲書(選)  biblio_cli tts → edge-tts 神經 TTS → mp3
```

```bash
# 加一本乾淨官方譯本:只要最小 book.json
#   {"slug":"x","title":"…","author":"…","source_type":"published","output_unit":"卷","convert":"s2tw"}
python -X utf8 scripts/biblio_cli.py build  book/<slug>   # 建 .md + manifest
python -X utf8 scripts/biblio_cli.py verify book/<slug>   # 殘簡=0 / 章數對得上
python -X utf8 scripts/biblio_cli.py tts    book/<slug>   # (可選)有聲書
```

> **迭代迴圈**:改 `control/` 或 `book.json` → 重建(免費/秒級)→ verify → regress。**永遠從 source 重建,不手改 out/。**

### 流程 B — 人名字典(髒源/漢化才需要)
把「每本手查官方譯名」變「LLM 起草 + 人工只審疑義」:
1. `python -X utf8 scripts/biblio/prep/extract_name_candidates.py book/<slug>` → `control/names_worksheet.md`(確定性候選)。
2. Claude:查官方台版譯名(標出處)+ 偵測內部 typo + **★標同形字陷阱**(例:莉莉亞≠莉莉雅)。
3. 寫 `control/names.tsv` + 不確定落 `control/name_gaps.md`(**絕不編造**)。
4. book.json 開 `names_tsv` → 重建 → 驗證。
細節見 [.claude/skills/ebook_load/SKILL.md](.claude/skills/ebook_load/SKILL.md)。

## 共通性與 Token 地圖

整個 **建置/驗證/TTS 是 100% 共用引擎**;每本書的差異只由兩個軸決定:

```
                     乾淨官方源                     髒源/漢化
  發行 (1 epub=1卷)    ✅ 只要 book.json            + names / jp / syllables
  網路 (N話=1卷)       + volumes.tsv               + volumes.tsv 全套
```

**三條鐵則**
1. **內文永不過 LLM** → 字數最大宗永遠 **0 token**。
2. **乾淨發行書 = 端到端 0 token**(只有 book.json)。
3. **OpenCC ≠ 模型、edge-tts ≠ LLM token** → 真 LLM token 只滴在「每本一次、只有髒源才要」的字典/日文研究(Sonnet,<10 萬 token/本),凍進 TSV 後永久 0。

> 結論:要控成本就砍 Phase 1 的**人工裁定工時**,不是砍 token(token 本就趨近 0)。唯一值得自動化的肥肉 = 人名字典半自動化(流程 B)。

## 回歸測試(改引擎前後必跑)
```bash
python -X utf8 scripts/regress.py            # 全建+全驗+逐位元比對 golden,任何非預期變動 = FAIL
python -X utf8 scripts/regress.py --freeze   # 故意改了輸出時,重凍 golden 當新基線
```
`regress.py` 自動探索 `book/` 下每一本書(任何含 `book.json` 的目錄),把輸出 sha256 凍進 `book/_regress/golden.json`。這是讓引擎能安全演化的 gate:**改完引擎跑它,必須全 PASS;只有刻意改輸出才 `--freeze`。**

## 倉庫結構
```
scripts/biblio/        引擎:ingest(epub/md/txt;pdf/docx stub)/ textconv / plan / build / verify / tts
  prep/                控制檔輔助:extract_name_candidates.py(人名候選工作表)
scripts/biblio_cli.py  CLI:build / verify / tts
scripts/regress.py     回歸 gate:全建+全驗+逐位元比 golden(book/_regress/golden.json)
book/<slug>/           一本書:book.json + source/(gitignored) + control/ + out/(gen) + audiobook/(gen)
.claude/skills/ebook_load/ skill:整理 ebook → 繁中 .md(判型 / 建置 / 驗證 / 人名字典)
.claude/skills/ebook_tts/  skill:整理好的 .md → 有聲書(雙聲 / 停頓 / 掉段處理)
```

## 文件地圖
| 檔 | 內容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架構 + I/O 契約:Piece / plan / manifest / 控制檔 schema |
| [book/README.md](book/README.md) | book.json 全旋鈕、控制檔格式、加書指南 |
| [.claude/skills/ebook_load/SKILL.md](.claude/skills/ebook_load/SKILL.md) | skill:整理 ebook → 繁中 .md(判型 / 建置 / 驗證 / 人名字典) |
| [.claude/skills/ebook_tts/SKILL.md](.claude/skills/ebook_tts/SKILL.md) | skill:.md → 有聲書(雙聲 / 停頓 / 掉段處理) |

## 範例

倉庫內含一個合成的最小範例書 `book/_fixtures/sample/`(自製假文,非版權內容),可直接端到端試跑:

```bash
python -X utf8 scripts/biblio_cli.py build  book/_fixtures/sample
python -X utf8 scripts/biblio_cli.py verify book/_fixtures/sample
```

要處理自己的書:在 `book/<slug>/source/` 放入 epub/txt,照「完整流程」寫 `book.json` 即可。版權書內容不隨倉庫散布。
