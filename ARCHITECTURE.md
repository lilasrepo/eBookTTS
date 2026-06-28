# ARCHITECTURE — biblio 引擎架構與 I/O 契約

建構工具時照這份做。對應 [book/README.md](book/README.md)(操作指南)與 [scripts/biblio/](scripts/biblio/)(引擎)。

## 1. 單位分類學(來源型態不統一,話 與 卷 各是原生單位)
```
作品 book/<slug>/
  └─ 卷 (volume)    發行小說的原生單位;web 對齊官方後的交付單位
       └─ 話 (episode)   網路小說的原生單位
       └─ 章 (chapter)   卷內的 "# " 標題(發行小說內部章節)
            └─ 段 (segment)  TTS 切段(旁白/對白)
```
**輸出單位 = 卷 或 話**(每本二擇一,寫在 book.json)。

## 2. 目錄結構
```
book/<slug>/
  book.json      # 設定 + source_type + output_unit
  source/        # 輸入素材,結構任意(扁平 epub 或巢狀 git tree)
  control/       # 人工/LLM 校的輸入(TSV + gaps.md)
  out/           # 輸出:一個輸出單位一個 .md
  audiobook/     # 輸出:mp3 + _work/_sil/_logs
  build/         # 機器產:manifest.json / verify.json(可 gitignore)
```
界線:`source/`+`control/` = 人給的輸入;`out/`+`audiobook/`+`build/` = 可從輸入重生的輸出。

## 3. book.json 兩個一等欄位
| key | 值 | 說明 |
|---|---|---|
| `source_type` | `web` \| `published` | 網路連載 / 發行單行本 |
| `output_unit` | `卷` \| `話` | 輸出粒度 |

合法組合:
| source_type | output_unit | 卷界來源 | 結果 |
|---|---|---|---|
| `published` | `卷` | 1 source 檔 = 1 卷(自動) | 一卷一檔 |
| `web` | `卷` | `control/volumes.tsv`(話→卷 分組) | 一卷一檔 |
| `web` | `話` | 每個話檔 = 1 話(自動) | 一話一檔 |
| `published` | `話` | — | **無效,build 報錯** |

## 4. Piece(輸出單位抽象,取代卷偏的 VolumeSpec)
```
Piece
  kind:      "卷" | "話"
  id:        檔名鍵。volumes.tsv 明列 -> 照用(Vol-01 / SS-01 / IF-03…)
             自動 -> published卷="Vol-NN" / web話="H-NNNN"
  number:    int(排序用)
  label:     顯示卷/話名
  note:      卷首註記 | None
  fragments: [ (source_rel_path, selector|None), … ]   # 有序;卷=多片段,話=單一
```
`plan(book_dir) -> [Piece]`:按 §3 合法組合分流(自動 或 讀 volumes.tsv)。

## 5. 控制檔 schema(TSV,首列為表頭)
| 檔 | 欄位 |
|---|---|
| `volumes.tsv` | `id ⇥ label ⇥ note ⇥ fragments`(fragments = 逗號分隔的 `relpath[:選擇器]`) |
| `names.tsv` | `katakana ⇥ romaji ⇥ official ⇥ variants` |
| `jp_patches.tsv` | `jp ⇥ zh` |
| `name_syllables.tsv` | `official ⇥ g1\|g2\|…` |
| `name_gaps.md` | 自由格式,人工裁定紀錄 |

## 6. 輸出命名(LOCKED:英數前綴 Vol-/H-)
- 卷:`Vol-NN_<safe(label)>.md`(NN 補零;番外用 volumes.tsv 的 id 如 `SS-01_…`)
- 話:`H-NNNN_<safe(label)>.md`(NNNN = 全域流水號,跨章連續,補零至最大寬度)
- 通則:`out/<piece.id>_<safe(piece.label)>.md`。`safe()` 去除 `\ / : * ? " < > |` 與結尾點/空白。

## 7. Manifest:build/manifest.json(雙層 + 出處 + 設定快照)
```json
{
  "slug": "re-zero",
  "source_type": "web", "output_unit": "卷",
  "config": { "convert": "s2twp", "strip_tl": true, "...": "解析後 cfg 快照" },
  "pieces": [
    { "kind": "卷", "id": "Vol-01", "number": 1, "label": "王都的一日", "note": null,
      "out": "out/Vol-01_王都的一日.md",
      "fragments": ["source/.../chapter010/1.md", "..."],
      "inner": { "unit": "話", "count": 26, "headings": 26 },
      "chars": 210345, "residual_simplified": 0, "simplified_markers": 0 }
  ],
  "totals": { "pieces": 53, "inner_units": 865, "chars": 9230000 }
}
```
- `inner.headings` = 實際輸出的 `# ` 標題數(無標題章如扉頁題詞會使其 < `count`);`verify` 比對它而非 `count`,避免把無標題章誤判成掉章。`simplified_markers` = 高精準殘簡警報(可接受的 OpenCC 詞優先留字會被標出)。
- `verify` 讀 manifest 比對殘簡/marker/章數/字數;`tts` 讀 manifest 取輸出清單,內容仍讀 `out/*.md`。
- `config` 快照 = provenance:能追「這份輸出是哪組設定產的」。

## 8. 資料流
```
          ┌── book.json (旋鈕 + source_type + output_unit) ──┐
source/ ──ingest──► Document(title, [Chapter(title,body)], meta)
control/volumes.tsv ──plan──► [Piece] ──build(管線)──► out/*.md
control/*.tsv ────────────────────────────┘            └──► build/manifest.json ──► verify / tts

管線(鎖定):strip_media? → jp_patch?(轉換前) → OpenCC → strip_credit_lines(一律)
            → strip_tl?(轉換後) → strip_editor_notes? → apply_names? → repair_names?(換名後)
```
