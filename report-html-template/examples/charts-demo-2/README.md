# charts-demo-2 — v1.2 兩種新圖型的最小範例（示意假資料）

堆疊長條（`stacked`，絕對值）與 cohort 留存熱圖（`cohort`）各一張，配兩份手寫的示意 csv。
**數字全部是示意假資料，不可引用。** 用途：確認 skill 沒改壞、給 Claude 看兩種新圖型的完整宣告、給 Lena 實機看色階與淡階的可辨度。

```
python3 ../../scripts/build.py --md 報告內容.md --out out/
python3 ../../scripts/qa_html.py out/示意遊戲－新圖型樣張（堆疊長條／cohort\ 留存熱圖）.html
```

預期：build exit 0（圖 2 張、表 0 張、數字 key 10 個，約 86 KB），HTML md5 `60963a3058585c0a0c63518c815041fa`，qa_html 16 項全 OK（第 8 項 JS md5 仍是 v1.1 的 `79e2d5b4…`——v1.2 沒動 JS）。

| 檔 | 內容 | 對應宣告 |
|---|---|---|
| `data/stacked.csv` | `月份,買量新客,自然新客,回流,老客`，4 個月 × 4 段（人數，皆 ≥ 0） | `type: stacked`，`segments:` 指定順序（老客在底）、`delta: {a: 2026-05, b: 2026-08, mode: pct}` |
| `data/cohort.csv` | `cohort,size,D0,D1,D3,D7,D14,D30`，9 個註冊週 × 6 個天數，年輕 cohort 的後段天數留空 | `type: cohort`，`size: size`、`days: [D1, D3, D7, D14, D30]`（排除恆為 100% 的 D0）、`scale: ratio`、`highlight_day: D7` |

檔頭 `values:` 示範從兩張圖的資料算數字：`col: total`（堆疊長條算出來的合計）、`pct_change` 用 x 值選兩個月份、
cohort 熱圖用 `from`／`to` 限定已完整觀察的 cohort 再取 `mean`（碰到空白格會報錯，不會默默略過）。

看什麼：
- 堆疊長條：點上方圖例關掉一段——其餘段**不會**往下重排、y 軸不重算（刻意的，見 `references/風格B設計決定.md` 決定 21）；滑到柱子上方空白也有 tooltip。
- cohort 熱圖：D1 欄深色格是白字、其餘是墨色字；W31 之後的 D30 是空白格；圖下方色階條標 7.3%～43.3%（圖內 min／max）。
