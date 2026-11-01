# charts-demo-3 — v1.3 四種新圖型的最小範例（示意假資料）

直方圖＋分位線（`hist`）、pre/post 分群啞鈴圖（`dumbbell`）、多段拆解瀑布（`waterfall` ＋ `subtotal`）、
星期×小時熱圖（`dow_hour`）各一張。**數字全部是程式產生的示意假資料（固定亂數種子，重跑一樣），不可引用。**
用途：確認 skill 沒改壞、給 Claude 看四種新圖型的完整宣告、給 Lena 實機看疊圖與熱圖的可辨度。

```
python3 ../../scripts/build.py --md 報告內容.md --out out/
python3 ../../scripts/qa_html.py out/示意遊戲－新圖型樣張（直方圖／啞鈴／多段瀑布／星期×小時）.html
```

預期：build exit 0（圖 4 張、表 0 張、數字 key 12 個，約 170 KB），HTML md5 `342070f854158fb6664961a29a2090a9`，
qa_html 16 項全 OK（第 8 項 JS md5 仍是 v1.1 的 `79e2d5b4…`——**v1.2 與 v1.3 都沒動 JS／CSS**）。

| 檔 | 內容 | 對應宣告 |
|---|---|---|
| `data/hist_raw.csv` | `group,value`，3,000 列 raw 值（新客 1,600／老客 1,400） | `type: hist`，`value:`／`group:` ＋ `edges:`（5 分一箱到 120）、`clip: true`、`quantiles: [50, 90]` |
| `data/dumbbell.csv` | `底台,上線前,上線後`，8 個底台 | `type: dumbbell`，`a:`／`b:` 指欄名與顯示名、`mode: pct`、`sort: delta` |
| （無 csv） | 瀑布九段直接寫在宣告的 `items:` 裡 | `type: waterfall`，`kind: level／delta／subtotal`，中繼點 `組內小計` 的 value 留空 |
| `data/dow_hour.csv` | long 格式 `dow,hour,active_users`，168 列其中一格（週二 4 時）故意留空 | `type: dow_hour`，`dow:`／`hour:`／`value:`、`week_start: mon`、`emph: max` |

檔頭 `values:` 示範從四張圖的資料算數字：直方圖用 `count_<組名>`／`share_<組名>`、啞鈴用 `delta` 欄取 max／min、
瀑布用 `cum` 欄取 first／last／指定段（`from: 組內小計`）、熱圖用 `h21` 欄與 `total` 欄。

看什麼：
- **直方圖**：兩組半透明疊圖（深藍＝新客、灰藍＝老客）＋ 各自的階梯外框；p50／p90 虛線是**該組的顏色**，
  點上方圖例關掉一組時分位線一起消失。raw 值算的分位是精確值（已分箱資料才會印「估算」那行註記）。
- **啞鈴圖**：空心圓＝上線前、實心圓＝上線後（形狀是主要線索，兩點同為中性藍）；
  右欄 `▲ +3.0%`／`▼ -7.4%` 紅漲綠跌**且一定帶正負號**，顏色不是唯一線索。
- **多段瀑布**：九段，中間插一個 `subtotal`（組內小計，值由程式算）；水位柱與中繼柱中性灰、變化柱紅綠；
  y 軸自 0 起不截斷。程式核對「起點 ＋ 各段 ＝ 終點」，對不上會報第幾項。
- **星期×小時熱圖**：7×24 格，週一在最上；最大格（週六 21 時）加**墨色粗框**；
  週二 4 時是**空白格**（無資料，不是 0）；色階條標圖內 min／max；四位數的值放不進格子時只在 tooltip。

四種圖裡只有直方圖有序列切換（沿用 v1.1 第 9 段 JS handler），其餘只有 tooltip——**JS 一個 byte 都沒動**。
