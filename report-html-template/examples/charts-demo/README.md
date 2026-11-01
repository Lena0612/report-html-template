# charts-demo — v1.1 三種新圖型的最小範例（示意假資料）

留存曲線（`retention`）、分群長條（`grouped`）、漏斗（`funnel`）各一張，配三份手寫的示意 csv。
**數字全部是示意假資料，不可引用。** 用途：確認 skill 沒改壞、給 Claude 看三種新圖型的完整宣告。

```
python3 ../../scripts/build.py --md 報告內容.md --out out/
python3 ../../scripts/qa_html.py out/示意遊戲－新圖型樣張（留存曲線／分群長條／漏斗）.html
```

預期：build exit 0（圖 3 張、表 0 張、數字 key 11 個），qa_html 16 項全 OK；HTML md5 `a08feea5023b54e4b8af833fc74cd33d`（v1.1 與 v1.2 重建相同）。

| 檔 | 內容 | 對應宣告 |
|---|---|---|
| `data/retention.csv` | `day,新客,老客,全體`，5 個 day × 3 群，值為 0～1 比例 | `type: retention`，`scale: ratio`、`unit: pct`、`baseline: 全體` |
| `data/grouped.csv` | `底台,上線前,上線後`，5 個類別 × 2 序列 | `type: grouped`，`delta: {a: 上線前, b: 上線後, mode: pct}` |
| `data/funnel.csv` | `step,count`，5 步遞減 | `type: funnel`，`show: [count, pct_first, pct_prev]`、`emph: auto` |

檔頭 `values:` 示範從三張圖的資料算數字：`col: delta`（分群長條算出來的變化率）、
`col: pct_first`／`loss_prev`／`count`（漏斗算出來的欄）、`a: D1, b: D7`（留存曲線用 D 標籤選點）。
