# charts-demo-4 — v1.4 兩個新東西的最小範例（示意假資料）

折線的**多條事件虛線**（`line` 的 `vlines`）與**顯著度熱圖**（新 figtype `sigheat`）各一張。
**數字全部是手寫的示意假資料（沒有亂數，重跑一定一樣），不可引用。**
用途：確認 skill 沒改壞、給 Claude 看兩個新東西的完整宣告、給 Lena 實機看事件線與熱圖留白的可辨度。

```
python3 ../../scripts/build.py --md 報告內容.md --out out/
python3 ../../scripts/qa_html.py out/示意遊戲－新圖型樣張（顯著度熱圖／折線事件線）.html
```

預期：build exit 0（圖 2 張、表 0 張、數字 key 10 個，約 74 KB），HTML md5 `25bff0c5aa7bcc0d320d7517eaec476f`，
qa_html 16 項全 OK（第 8 項 JS md5 仍是 v1.1 的 `79e2d5b4…`——**v1.2／v1.3／v1.4 都沒動 JS／CSS**）。

| 檔 | 內容 | 對應宣告 |
|---|---|---|
| `data/dau.csv` | `date,dau,ma7`，2026-06-01～06-30 共 30 列 | `type: line`，兩條序列（`raw` 淡灰細線＋`s1` 藍粗線）＋ `vlines` 三項 |
| `data/sigheat.csv` | `指標,新客,老客,回流`，6 列；回流欄有 **2 格故意留空** | `type: sigheat`，`row:`／`cols:`／`legend_title:`／`highlight_col:` |

檔頭 `values:` 示範從兩張圖的資料算數字：折線**沒有宣告 `break`**，所以一律用 `from`／`to` 指定日期範圍
（`seg: pre`／`post` 用不了，這正是 `vlines` 與 `break` 的差別）；熱圖用欄名取 `max`，或用 `from`／`to` 取某一列指標。

看什麼：

- **折線事件線**：三條垂直虛線（06-05 活動開始、06-12 伺服器異常、06-19 活動結束），沿用斷點虛線的線型（`.bkline`）。
  中間那條是 `color: red`（`#c62828`，inline stroke），線與標籤一起變紅；另外兩條不寫 color ＝ 墨色。
  **事件線不畫前後灰帶、不切段、不影響任何計算式**——要做前後對比請用 `break`（§4.1 有對照表）。
  顏色只有 `red`／`ink` 兩種，寫別的會報「vlines 的 color 只能是 red／ink」。
- **顯著度熱圖**：6 指標 × 3 族群 ＝ 18 格，其中 2 格留白（回流組的留存 D7 與 ARPDAU **沒有做檢定**，不是 0）。
  色階是 cohort 熱圖那一支 `svgchart.heatmap` 的**單一藍色相亮度階**（`fill-opacity` 0.08～1 對應圖內 min～max），
  深色格自動改白字，圖下方色階條標 min／max，並自動註明「空白＝沒有做檢定（不是 0）」。
  `highlight_col: 新客` 把該欄標題加粗。**色階只編碼強度、不編碼方向**（漲或跌另外寫在判讀）。
  顯著門檻畫不成線（熱圖沒有軸），所以寫在 `defs` 的「指標」那行。

兩張圖都沒有用到紅漲綠跌的方向色（事件線的紅是「負面事件」不是「漲」），
熱圖也**沒有序列切換**，只有 tooltip——**JS 與 CSS 一個 byte 都沒動**。
