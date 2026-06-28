---
name: ebook_load
description: >
  把一本書(epub / 漢化 .md / txt / 連載話檔)整理成繁體中文分卷 .md,用 scripts/biblio 引擎。
  觸發詞:「加一本書」「整理 ebook」「把這套 epub 轉成繁中 md」「建置/驗證某本書」
  「建人名字典 / 對齊官方台版譯名」「web 連載切卷」「out 殘留簡體 / 垃圾標題」。
  Ingest an epub / fan-translation / web episodes into per-volume Traditional-Chinese markdown
  via the biblio engine; build + verify a book; generate the official-Taiwan-name dictionary.
  做完 .md 後要產有聲書 → 用 ebook_tts。
---

# ebook_load — 多格式書籍 → 繁中分卷 .md

驅動 `scripts/biblio` 確定性引擎,把書整理成繁中 `.md`(+ manifest)。**有聲書是另一隻 skill `ebook_tts`**(本 skill 只到 `.md`)。

**內文永不過 LLM**(怕漏譯/改寫);LLM 只用在「建人名字典 / 補殘留日文 / 查官方卷界」這類 metadata 研究,凍進 `control/*.tsv` 後建置全程 0 token、可無限重跑。完整脈絡:[README.md](../../../README.md)、[ARCHITECTURE.md](../../../ARCHITECTURE.md)、[book/README.md](../../../book/README.md)。

## 何時用
- 使用者要把某本書(epub / 漢化 md / txt / 連載話檔)整理成繁中 `.md`。
- 要新增一本書到 `book/<slug>/`、或重建/驗證既有書。
- 要建/補人名字典(對齊官方台版譯名)、處理殘留簡體或垃圾標題。
- (整理好的 `.md` 要轉有聲書 → 改用 `ebook_tts`。)

## 環境
`pip install opencc edge-tts mutagen` + 系統 `ffmpeg` 在 PATH。Windows 主控台一律 `python -X utf8`,檔案 UTF-8。建 `.md` 全離線、0 token。

---

## 流程 A — 加一本書並建置成 .md

1. **放料**:`book/<slug>/source/` 丟入 epub/md/txt(或散放 `book/<slug>/` 根)。

2. **判型 → 寫 `book.json`**。先定兩軸,照下表選:

   | | 乾淨官方源 | 髒源/漢化 |
   |---|---|---|
   | **發行**(1 檔=1 卷) | 只要 book.json | + names/jp/syllables |
   | **網路**(N 話=1 卷) | + volumes.tsv | + volumes.tsv 全套 |

   最小 `book.json`:`{"slug":"...","title":"...","author":"...","source_type":"published","output_unit":"卷","convert":"s2tw"}`。
   - `source_type`: `published`(發行)| `web`(網路連載)。
   - `output_unit`: `卷` | `話`(web 才有意義;published 固定卷)。
   - `convert`: **官方繁中譯本即使乾淨也建議 `s2tw`** —— OCR 常夾帶零星簡體,而 OpenCC 無法區分台版異體字與真簡體,故無可靠的「只修簡體」自動法;`s2tw` 把簡體**降到近乎零**(代價:異體字正規化 台→臺)。**注意:不是零** —— OpenCC 詞優先,少數字會在詞境保留(有的正確,如「佣金」佣≠傭;有的邊界,如人名「杰特」、「涌上心頭」台版多作 傑/湧),`verify` 的 Simplified-markers 會把這幾顆標出來給人瞄一眼(每卷 0–1 顆)。要逐字保留官方用字才用 `none`(但殘留更多)。簡中漢化源用 `s2twp`。
   - 髒源再開:`"strip_tl":true`(去漢化組署名/譯註)、`"names_tsv":"control/names.tsv"`、`"jp_patches":"control/jp_patches.tsv"`、`"name_syllables":"control/name_syllables.tsv"`。
   - **web+卷** 還需 `control/volumes.tsv`(`id⇥label⇥note⇥fragments`,fragments 是 source/ 下的 `relpath[:章選擇器]` 逗號清單)。
   - **簡中來源即使 `convert:none` 也會被自動強制 s2twp**(build 偵測 dc:language=zh-CN);輸出永不殘簡。

3. **建置 + 驗證**:
   ```bash
   python -X utf8 scripts/biblio_cli.py build  book/<slug>
   python -X utf8 scripts/biblio_cli.py verify book/<slug>
   ```
   `build` 產 `out/<id>_<label>.md`(卷=`Vol-NN`、話=`H-NNNN`)+ `build/manifest.json`。
   `verify` 比對 manifest:**Simplified-markers 必須 0**(>0 = 真簡體殘留,改 convert 或查源);`residual` 是異體字噪音(僅供參考);章數對不上 = 可能掉章。

4. **交付確認**:章數/字數合理、垃圾標題已清、人名一致。要產有聲書 → 接 `ebook_tts`。

> 改了 `control/` 或 `book.json` 後重跑 `build` 即更新(OpenCC 確定性、免費、幾秒)。**永遠從 source 重建,別手改 out/。**

---

## 流程 B — 驗證 → 診斷 → 修正 迭代迴圈(模型自我校正)

build 不是一次就交付。**你(模型)要讀 `verify` 報告 → 診斷根因 → 改旋鈕/control/引擎規則 → regress 重驗 → 重跑,直到乾淨**。這是 metadata 層的確定性校正,**不是讓 LLM 改內文**(內文永不過 LLM,見硬規則)。**只改「設定 / control 檔 / 引擎的確定性規則」,絕不手改 `out/`。**

```
build ─► verify ─► 讀報告
                     │  全 ok?──► 交付
                     └─ 有 issue ─► 診斷根因(下表)─► 改旋鈕/control/規則
                                       └─► regress.py(別弄壞他書)─► 重跑 build ─► verify(回圈)
```

**診斷表:症狀 → 根因 → 動作**

| verify / 肉眼症狀 | 根因 | 動作(只動設定/規則,不動 out/) |
|---|---|---|
| `Simplified-markers > 0`(標出某字,如 `戏`) | 該書 `convert:none` 但源混入零星真簡體 | 評估改 `convert:s2tw`(整本清,代價異體字正規化);或單顆可接受就留(verify 已標給人看)。**別為一字硬改全書**——先看那字語境 |
| `char mismatch` / 章數 ≠ manifest | 掉章 / out 被手改 | 從 source 重 build(永不手補 out);查 adapter 是否誤丟章 |
| 標題出現垃圾(封面逐字、■、單字、對白開頭) | 商業 epub 前置頁雜質 | adapter 多半已自動降級;殘留個案 → 調 epub adapter 的標題/credits 規則(context-bound) |
| 簡轉繁斷詞誤轉(如 `第N卷发售`→`捲髮售`) | OpenCC 詞優先選錯字 | 加進 `textconv._POSTFIX_RULES`(**務必 context-bound**,別誤傷合法詞如「捲髮」) |
| 人名不一致 / 音譯多寫法 | 缺字典或字典不全 | 走**流程 C**(人名字典):建/補 `control/names.tsv`;同音變體 → `name_syllables.tsv` |
| 漢化組署名/譯註殘留 | 髒源 | 開 `strip_tl:true`;個案行 → 調 `strip_credit_lines` 規則 |
| 殘留日文整句 | 漢化漏譯 | `scan_japanese`/`extract_jp` 抽句 → 你譯成 `jp_patches.tsv`(metadata 研究,非改內文) |

**迭代守則:**
- **改引擎規則(adapter/postfix/strip)前後必跑 `regress.py`** —— 確認沒弄壞其他已交付書(逐位元比 golden)。這是迴圈的安全閘。
- 不確定的譯名/裁定 → 落 `control/name_gaps.md` 給人決定,**絕不編造**(硬規則 #5)。
- 每次只改一個旋鈕/規則 → 重驗 → 看 marker/字數變化,定位因果;別一次改多項。
- marker 收斂到 0(或剩可解釋的個位數,記錄原因)+ 章數對 + 垃圾標題清 = 可交付。

---

## 流程 C — 人名字典半自動化(只有髒源/漢化書需要)

目標:把「每本手查官方譯名」變成「LLM 起草 → 人工只審疑義」。乾淨官方譯本**不需要**(名字已是官方版)。簡中源若 s2twp 轉出的名已與官方一致(實測常見)亦**不需要**。

1. **抽候選**(確定性):
   ```bash
   python -X utf8 scripts/biblio/prep/extract_name_candidates.py book/<slug>
   ```
   產 `control/names_worksheet.md`:任何「登場人物」頁的逐字 dump + 依 **name-score**(後接 說/道/問 的次數)排序的候選名 + 例句。**這是候選池,含雜訊,你要篩。**

2. **你(Claude)建字典**:
   - 讀 `names_worksheet.md`(角色頁最可靠);再抽讀 `out/*.md` 幾章補漏(工作表會漏低頻角色)。
   - 把同一角色的**各種音譯寫法歸成一組**(如 雷姆/蕾姆),決定**官方台版名**。
   - **查證官方譯名**:web 搜尋 zh.wikipedia / 該作 Fandom,以片假名+羅馬字為角色唯一鍵(不靠中文),**標明出處**。台版出版社常非台灣角川(請逐作查證)。
   - 寫 `control/names.tsv`,表頭 + 每列 `katakana⇥romaji⇥official⇥variants`(前兩欄可留空或填 zh;引擎只用 official 與 variants 逗號清單,長鍵優先單次替換)。
3. **不確定就落 `control/name_gaps.md`**(出處衝突、沒把握、同音歧義),列出選項給人裁定 —— **絕不編造**。
4. `book.json` 設 `"names_tsv":"control/names.tsv"` → `build` → `verify`。人改完 `name_gaps.md`/`names.tsv` 後重跑(免費)。
5.(髒源加值)同音/拆名變體 → `control/name_syllables.tsv`(`official⇥g1|g2|…`,每群是該音節可互換字,如 `愛蜜莉雅⇥愛艾|蜜米密|莉|雅婭亞`)→ 開 `name_syllables`。殘留日文句 → `scan_japanese`/`extract_jp` 抽句 → 你翻成 `control/jp_patches.tsv`(`jp⇥zh`)→ 開 `jp_patches`。

---

## 鎖定規則 / 常見坑
- **改引擎前後必跑回歸 gate**:`python -X utf8 scripts/regress.py` —— 全建+全驗+逐位元比對 `book/_regress/golden.json`,**必須全 PASS**;只有刻意改輸出時才 `--freeze` 重凍基線。加新書進回歸 = 加進 `regress.py` 的 `BOOKS` 後 `--freeze` 一次。
- **管線順序不可調換**(build.py):`strip_media → jp_patch(轉換前) → OpenCC → strip_credit_lines(一律) → strip_tl(轉換後) → strip_editor_notes → apply_names → repair_names`。
- **版權/製作資訊處理是自動的,不是旋鈕**:epub **一律**丟版權/staff/製作資訊整頁(adapter 層,含免責聲明/disclaimer 整章),`strip_credit_lines` **一律**清章內殘留的漢化署名行(以 圖源:/錄入:/掃圖:/譯者: 等開頭),**保留作者/插畫**。高精準行錨定 → 不誤殺正文。要全套清漢化署名/promo/譯註/URL 才另開 `strip_tl`(較廣,乾淨源勿開)。
- **簡轉繁斷詞誤轉**:`textconv._postfix` 已修常見個案(`第N卷发售`→誤`捲髮售`→`卷發售`),且**嚴格保護**合法詞(「捲髮」不誤傷)。讀到新誤轉個案 → 加進 `_POSTFIX_RULES`(務必 context-bound)。
- **內文不餵 LLM**;LLM 只碰 control 檔的研究。**OpenCC 不是模型**(規則字典、0 token)。
- 亂的商業 epub 前置頁(封面逐字、■、對白)會變垃圾標題:adapter 已自動丟「無內文的前置頁」、降級「單字/符號/對白開頭」標題;少數整句 epigraph 標題會殘留(可接受)。
- 大目錄印 CJK 一律 `python -X utf8`;暫存放專案內、勿放 AppData。

## 參考
- [README.md](../../../README.md) — 完整流程、共通性 2×2、token 地圖、回歸 gate
- [ARCHITECTURE.md](../../../ARCHITECTURE.md) — Piece / plan / manifest / control 檔 schema(架構 + I/O 契約)
- [book/README.md](../../../book/README.md) — book.json 全旋鈕、控制檔格式
- [book/re-zero/control/](../../../book/re-zero/control/) — web+卷 全套控制檔的活範本(volumes.tsv / names.tsv / jp_patches.tsv)
- **有聲書**:整理好的 `.md` → 用 skill `ebook_tts`
