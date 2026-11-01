# report-html-b v1.6 → v1.7（2026-09-16）

兩項新能力，**都是「宣告才生效」**：不宣告時 build 出來的 HTML 與 v1.6 逐 byte 相同
（八個樣張 md5 全部沒變、JS／CSS／themes.py 零變動）。

| # | 能力 | 宣告 | 來源 |
|---|---|---|---|
| 1 | 折線圖例從右側搬到 x 軸下方 | `line` 的 `legend: bottom` | Lena 2026-09-16 16:06 第 4 點「圖1-1 圖標放在x軸下方，不是右方」 |
| 2 | 結論從條狀卡片改成純條列（含一層 `　◦ ` 子項） | 檔頭 `conclusion_style: list` | Lena 同一輪第 1 點「結論用條列式，不是卡片」 |

## 1. `legend: bottom`（`scripts/svgchart.py`、`scripts/figures.py`）

- `xy_chart()` 多一個參數 `legend`（預設 `"right"`）。`"bottom"` 時：
  - 邊界 `m=(T, R, B, L)` 的 `R` 改成 `LGD_B_R = 26`、`B` 加 `LGD_B_H = 46`；繪圖區因此寬 +132、矮 46。
  - 圖例改成橫排、置中於繪圖區，文字基線在 `T + ph + LGD_B_DY(44)`
    （x 軸刻度在 `+22`，圖例在它下面一排）。
  - 元素形狀、class（`g.lgd` / `line.sw` / `rect.sw` / `text.vl.lgt`）與 `data-key` 完全沿用右側圖例，
    所以 JS 的序列開關、CSS 的 `.lgd.off` 都不用改。
- 事件線（`vlines`）的 warn icon 與事件標籤掛在 `T + ph`（繪圖區底緣）畫，**不受下邊界加高影響**；
  圖例畫在放大後的下邊界裡，兩者不會疊。
- `height` 不會自己加。要維持原本的繪圖區高度，宣告時把 `height` 加 46。
- 守門：`legend` 只能是 `right`／`bottom`，寫錯 → 報錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML。

## 2. `conclusion_style: list`（`scripts/mdcontent.py`、`scripts/rhtml.py`）

- 檔頭新欄位 `conclusion_style`，只吃 `card`（預設）／`list`。
- `list` 時 `## 結論` 改排成 `<ul class="bul concl-list">`（正文清單的既有樣式，**CSS 零新增**）；
  `　◦ ` 開頭的行變成上一條的子項，排成 `<ul class="bul concl-sub">` 巢狀清單。
- **卡片模式下 `◦` 開頭的行仍然是「上一條寫太長的換行接續」**（v1.6 行為一個字都沒改）。
- `[dn]`／`[up]` 在條列模式只寫進 `<li class="tone-dn">`，不上色——條列沒有卡片上緣那條色帶。
- 守門：值寫錯、或第一條就是 `◦`（沒有可掛的主條目）→ 報錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML。

## 測試（`tests/run_tests.py`）

- A 回歸：六個舊樣張 ＋ v1.6 的 charts-demo-6（`357e1df0…`）／sig-shade-demo（`eef1e0d2…`）
  md5 全部不變；JS `79e2d5b4…`／CSS `84b3f2ce…`／themes.py `f62fd318…` 不變。
- 新樣張 `examples/charts-demo-7`：build ＋ qa 17 項全綠。
- D 段新增四項：圖例座標在 x 軸下方、事件標籤仍在繪圖區內、結論條列與子項的結構、
  以及「拿掉宣告就回到 v1.6 的樣子」（圖例回右側、結論回卡片、◦ 併回同一段）。
- C 負向 19 → 22 條（legend 值錯／conclusion_style 值錯／◦ 子項沒有主條目）。

跑法：`python3 tests/run_tests.py` → `[ALL PASS]`。
