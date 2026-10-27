---
name: ebook_tts
description: >
  把整理好的繁中分卷 .md 轉成有聲書(每章一個 mp3),用 scripts/biblio 引擎 + edge-tts。
  觸發詞:「轉有聲書 / audiobook」「把這本 md 念成語音」「跑 TTS」「某卷有聲書重跑/補掉段」
  「換聲音 / 調語速 / 改 mp3 位元率」。
  Turn the per-volume Traditional-Chinese .md (from ebook_load) into an audiobook: per-chapter
  mp3 via edge-tts, dual voice, ffmpeg silence + concat, ID3 tags. 先要有 out/*.md → 用 ebook_load。
---

# ebook_tts — 繁中分卷 .md → 有聲書

把 `book/<slug>/out/*.md` 念成每章一個 mp3。**前置:該書要先用 `ebook_load` 建好 `out/*.md` + `build/manifest.json`**(本 skill 不轉文字、不碰 source)。

## 何時用
- 使用者要把已整理好的書(繁中 `.md`)轉成有聲書 / audiobook。
- 要重跑某卷、補掉段、換聲音 / 語速 / 位元率。
- (還沒有 `out/*.md` → 先用 `ebook_load` 整理。)

## 環境
依賴照 README.md「安裝」(`edge-tts>=7.3.1`、`mutagen==1.48.1`),**裝套件前先問使用者**;另需系統 `ffmpeg` 在 PATH。**TTS 需連網**(edge-tts 呼叫微軟,0 LLM token)。一卷雙聲約數分鐘合成、~80MB(mp3 32k)。Windows 主控台 `python -X utf8`。暫存放專案內(`audiobook/_work` 段快取,含 `_work/_sil` 靜音;`audiobook/_logs`),勿放 AppData。

---

## 流程

1. **確認前置**:`book/<slug>/out/*.md` 存在(沒有就先 `ebook_load`)。

2. **聲音設定**(在 `book.json` 的 `tts` 區,沿用即可,要改才動):
   ```json
   "tts": {
     "mode": "dual",
     "narration": "zh-TW-HsiaoChenNeural",
     "dialogue":  "zh-CN-XiaoyiNeural",
     "rate": "+10%",
     "format": { "bitrate": "32k", "channels": 1, "sample_rate": 24000 },
     "gap_ms": 250
   }
   ```
   - `mode`:`dual`(雙聲:旁白 narration / 「」『』對白 dialogue)| `single`(單聲,只用 narration)。
   - `format`:mp3 位元率(`32k` 對語音夠用、省空間;要更清楚可 `48k`)。
   - `gap_ms`:同聲連續段落間插入的靜音(ffmpeg anullsrc),250ms 自然。
   - ID3:`TPE1`(演出者)**只署 `book.json` 的 author**,絕不含漢化/製作組。

3. **先驗一卷,過了才跑全批**:
   ```bash
   python -X utf8 scripts/biblio_cli.py tts book/<slug> --source "<某卷檔名片段>"
   ```
   檢查:章數對、檔名 `NNN_章名.mp3`、ID3 演出者正確、`synth {ok, skip, fail}` 的 fail 數。把檢查結果回報使用者,**等使用者說 go 才跑全批**。

4. **全批**:
   ```bash
   python -X utf8 scripts/biblio_cli.py tts book/<slug>
   ```
   只有段層級可續跑(段 mp3 已在 `_work` 就不重合成)。每次執行都會對所選卷的每章重新 concat、重寫 ID3、覆蓋章 mp3;已完成的卷要用 `--source` 排除(若 `_work` 已刪 → 整卷重新合成)。建議用背景執行 + 逐卷回報。輸出 `audiobook/<卷名>/NNN_章名.mp3`。

5. **清理**:僅在 fail=0,或每個掉段都已記入 `audiobook/_logs/dropped_fragments.txt` 並判定良性後,先問使用者,同意才刪暫存(只刪 `_work`,含 `_sil`),只留分章 mp3:
   ```bash
   rm -rf book/<slug>/audiobook/_work
   ```
   刪了 `_work` 後再重跑該卷 = 整卷重新合成。

---

## 掉段(fail)處理 —— 多半良性,但要查清

`synth` 報 `fail: N` **不代表章壞掉**:引擎遇失敗段會**跳過該段、仍把整章組起來**(章 mp3 完整可播)。

- **重跑該卷**(skip-existing,只重試失敗段;需 `_work` 仍在):`tts ... --source "<卷>"`。仍 fail → 不是網路問題,是**內容**。
- **定位失敗段文字**(用引擎的 `_plan_volume` 比對磁碟 mp3),確認性質:
  - 最常見 = **對白裡夾的孤立日文假名**(`の`/`ぬ`/`だもんで`),中文對話聲念不出單一假名 → edge-tts 回 "No audio",**正確跳過,0 中文遺失**。
  - 把這類掉段記到 `audiobook/_logs/dropped_fragments.txt`(清單 + 性質)交付時說明。
- 真要救假名 SFX → 可加「空音段改送日文聲」的 fallback 重跑(會多一個日文聲,通常不必)。

---

## 坑 / 鎖定
- **edge-tts 不是 LLM token**(免費神經 TTS)。**OpenCC 在 build 階段已做完**,tts 只讀 `out/*.md` 純文字。
- `--chapter N` 的 **N 是 1-based**(序=1)。只給單章做煙霧測試用。
- 章節切分 = `out/*.md` 的 `# ` 標題;標題怎麼切是 `ebook_load` 階段決定的,tts 不改。
- 不同書共用同一套引擎,聲音/格式差異全在各自 `book.json` 的 `tts` 區。

## 參考
- [README.md](../../../README.md) — 全流程、token 地圖
- [ARCHITECTURE.md](../../../ARCHITECTURE.md) — 單位分類學(章/段)、manifest
- **整理 .md**:還沒有 `out/*.md` → 用 skill `ebook_load`
