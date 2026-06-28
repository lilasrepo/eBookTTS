# book/ — 加一本書 + dry run 指南

每本書一個資料夾 `book/<slug>/`,設定全在自己的 `book.json`。引擎程式碼在 [../scripts/biblio/](../scripts/biblio/),不必動。

## 1. 資料夾規範
```
book/<slug>/
  book.json          # 設定(唯一的旋鈕)
  source/            # 原始檔:*.epub / *.md / *.txt(也可散放在 <slug>/ 根目錄)
  control/           # 可選:人名字典 / 卷界 / 日文補丁 / 同音表
  out/               # 輸出 .md(build 產生)
  audiobook/         # 輸出 mp3(tts 產生)
```
支援格式:`.epub`(stdlib 手解)、`.md`、`.txt`。`.pdf` / `.docx` 是 stub(要先裝 PyMuPDF / python-docx,會提示)。
每個 source 檔 → 一個 `out/<檔名>.md`(epub 內的章 = `# 標題` 區塊)。

## 2. 最小 dry run(乾淨的繁中/簡中 epub)
```powershell
# 1) 放檔
新增 book/<slug>/source/  並把 epub 丟進去
# 2) 寫最小 book.json(見下)
# 3) 建 .md
python -X utf8 scripts/biblio_cli.py build book/<slug>
# 4)(可選)單章 TTS 煙霧測試 → 再整本
python -X utf8 scripts/biblio_cli.py tts book/<slug> --source <某卷> --chapter 1
python -X utf8 scripts/biblio_cli.py tts book/<slug>
```
最小 `book.json`:
```json
{ "slug": "<slug>", "title": "書名", "author": "作者", "convert": "s2twp" }
```
> 簡中來源即使 `convert` 設 `none` 也會被**強制 s2twp**(輸出永不殘簡)。已是繁中的來源用 `convert:"none"` 直通。

## 3. book.json 全旋鈕
| key | 預設 | 作用 | 何時開 |
|---|---|---|---|
| `convert` | `s2twp` | 簡→繁:`s2twp`(台灣在地化) / `s2tw` / `none`(直通) | 簡中來源用 s2twp;繁中來源用 none |
| `strip_media` | `true` | 去圖片連結 / 殘留 HTML 標記 | 一般留 true |
| ~~`strip_credits`~~ | — | **不是旋鈕**。epub **一律**丟版權/staff/製作資訊整頁,並一律清章內殘留的漢化署名行(圖源:/錄入:/掃圖:/譯者:…,**保留作者/插畫**)。不可關 | 自動 |
| `strip_editor_notes` | `false` | 去 `（譯註：…）` 這類括註(輕量) | 想清譯註但不想動 strip_tl 時 |
| `strip_tl` | `false` | **去漢化組署名/招募/promo/譯註/URL/（暫譯）**(OpenCC 後執行) | **漢化來源開** |
| `names_tsv` | `null` | 人名字典路徑(`變體→官方名` 確定性替換) | 要統一官方譯名時 |
| `jp_patches` | `null` | 未翻日文補丁 `jp_patches.tsv`(OpenCC **前**執行) | 來源有殘留日文句時 |
| `name_syllables` | `null` | 同音/拆名修復表(換名**後**執行) | 同一角色有多種音譯寫法時 |
| `tts.*` | 雙聲 | TTS:`mode` dual/single、narration/dialogue 嗓音、`rate`、`format`、`gap_ms` | 預設即可 |

## 4. 管線順序(鎖定,不可調換)
```
ingest 解析(epub 一律丟版權/製作資訊整頁) → strip_media? → jp_patch?(轉換前) → OpenCC convert
            → strip_credit_lines(一律) → strip_tl?(轉換後) → strip_editor_notes? → apply_names? → repair_names?(換名後)
```
`strip_credit_lines` **一律執行**:清掉章內殘留的漢化署名行(以 圖源:/錄入:/掃圖:/譯者: 等開頭),保留作者/插畫;高精準行錨定,不碰正文(對 fixture 逐位元相同)。其餘 4 個可選步驟未設對應 key 時**完全略過**,乾淨來源的輸出與不加它們時逐位元相同。

## 5. 控制檔格式(只在要開對應旋鈕時才需要)
- `names.tsv` — 表頭 + 每列 `katakana \t romaji \t official \t variants(逗號分隔)`。`apply_names` 取 official 與 variants,長鍵優先單次替換。
- `jp_patches.tsv` — 表頭 + 每列 `日文 \t 繁中`。長句優先。
- `name_syllables.tsv` — 表頭 + 每列 `官方名 \t 群組1|群組2|…`,每群是該音節可互換的繁體字集合。例:`愛蜜莉雅 \t 愛艾|蜜米密|莉|雅婭亞`。

## 6. 驗證(每次 build 後)
- 殘簡應為 0(語境歧義字 范/裡/了 等少量屬正常)。
- 章數 / 字數對來源,防漏章漏段。
- 抽看首尾段落。

## 7. 環境
`pip install opencc edge-tts mutagen` + 系統裝 `ffmpeg`(在 PATH)。建 `.md` 全程離線;TTS 需連網(edge-tts)。Windows 主控台一律 `python -X utf8`。
