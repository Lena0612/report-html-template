# report-html-b v1.7 → v1.8（2026-09-16）

一個 **bug 修正**（會改到產出）＋ 兩項**宣告才生效**的新能力 ＋ 一項**驗證判準放寬**。

| # | 項目 | 型態 | 來源 |
|---|---|---|---|
| 1 | vlines 的紅色改用 inline `style`（修 v1.4 起就存在的顏色 bug） | 修 bug | Lena 2026-09-16 17:38 第 b 點「跌點虛線跟字體要紅色！！！」 |
| 2 | `vlines` 的 `label2:`＝事件標籤第二行 | 宣告才生效 | 同上，「其他虛線也要補上日期」而標籤會撞 |
| 3 | `conclusion_style: numbered`＝結論條列改 1. 2. 3. | 宣告才生效 | 同上第 a 點 |
| 4 | `defs` 從「剛好三列」放寬成「維度／指標／著色 挑 1~3 列」 | 判準變更 | 同上第 e 點「非必要不需要 notes_extra、維度」 |

## 1. 顏色 bug（`scripts/svgchart.py`）

v1.4 起 `vlines` 用 **SVG presentation attribute** 給色：

```
<line class="bkline" … stroke="#c62828">
<text class="an bkl"  … fill="#c62828">
```

但 `themes.py` 的 CSS 有 `.chart .bkline{stroke:var(--ink2)}` 與 `.chart .bkl{fill:var(--ink2)}`。
**presentation attribute 在串接裡輸給任何一條 CSS 規則**，所以紅色從來沒有渲染出來，
兩條跌點線跟其他事件線一樣是墨灰。（warn icon 的 `<g fill="#c62828">` 沒有 class、沒有規則蓋得到，
所以三角驚嘆號一直是紅的——肉眼「有紅色」才一直沒被抓到。）

改成 inline `style="stroke:…"`／`style="fill:…"`（與 v1.5 檢定底色相同的做法）。
**`themes.py` 零變動**（md5 `f62fd318132b25010543040a97d0e27c`）、CSS 零變動
（md5 `84b3f2cef683bed91dbfe2cfe9b818a0`）、JS 零變動（`79e2d5b43d53764e88de8a6771c64253`）。

**影響範圍**：只有宣告 `vlines` ＋ `color: red` 的產出會變。
`charts-demo-4`／`charts-demo-6`／`charts-demo-7` 三個樣張的 md5 會變，
其餘六個一個 byte 都沒變。三個變動的樣張把 inline style 機械式換回舊寫法會逐 byte 回到 v1.7 的 md5
（測試 E 段有守）。

## 2. `label2`（`scripts/svgchart.py`、`scripts/figures.py`）

```yaml
vlines:
  - {at: 2026-05-28, label: 5/28, label2: Gaple 底台縮減}
```

`label` 是第一行（慣例寫日期）、`label2` 是第二行（事件名），差一個行高 `VL_L2_DY = 17.0`、同一個 x。
`icon: warn` 那一路是**第一行往上推一個行高、第二行留在原本的基線**，所以標籤群仍貼著繪圖區下緣。
兩行共用同一個顏色來源（有 `color: red` 就兩行都紅）。
守門：寫了 `label2` 卻沒有 `label` → 報錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML。
不宣告 `label2` 時輸出與「v1.7 ＋ 顏色修正」逐 byte 相同。

## 3. `conclusion_style: numbered`（`scripts/mdcontent.py`、`scripts/rhtml.py`）

`card`（預設）／`list`（•）／**`numbered`（1. 2. 3.）**。
`numbered` 時外層從 `<ul class="bul concl-list">` 換成 `<ol class="bul concl-list">`——
`.bul` 沒有 `list-style:none`，瀏覽器直接排 1. 2. 3.，**CSS 一個 byte 都不用改**。
`<ul>` 巢在 `<ol>` 裡時 UA 預設會把 marker 退回 `disc`，所以子項補一個 inline
`style="list-style-type:circle"` 把 ◦ 釘住（「小項目維持不變」）。
`list` 模式的輸出與 v1.7 逐 byte 相同。

## 4. `defs` 放寬（`scripts/figures.py`、`scripts/qa_html.py`）

| | v1.6／v1.7 | v1.8 |
|---|---|---|
| 三列都要有 | 是（缺 → 報「defs 缺 X」） | **否**，三列裡至少一列即可 |
| 第四個 key | 擋 | **照樣擋**（負向案例 27 有守） |
| `defs` 整個空 | （不可能發生） | **新增：報錯** |
| 寫了 key 卻空值 | （被「缺 X」擋掉） | **新增：報錯** |
| 列的順序 | （三列必然固定） | **新增：必須 維度 → 指標 → 著色** |
| `qa_html` 第 17 項 | 備註剛好四列 | defs 1~3 列（順序固定）＋ 母體剛好 1 列 |

## 測試（`tests/run_tests.py`，新增 `tests/cssres.py`）

- A 回歸：**八個**樣張 md5（charts-demo-4／-6 是顏色修正後的新值，其餘六個維持 v1.5 定版）；
  JS／CSS／themes.py 三個 md5 不變。
- C 負向：22 → **27 條**（label2 沒有 label／defs 空／defs 順序／defs 空值／defs 第四列）。
- **E 段（新）——顏色 bug 的驗收不看原始碼有沒有屬性**：把 `<style>` 的規則跟每個 SVG 元素跑一次
  CSS 串接（specificity ＋ 出現順序 ＋ inline ＋ `!important`，`tests/cssres.py`），算出**最終生效**的
  `fill`／`stroke`，要求
  ① 全文件零處「presentation attribute 被 CSS 蓋掉」、
  ② 跌點線與它們的標籤最終是 `#c62828` 且來源是 inline、
  ③ 其餘事件線／標籤仍走 CSS 的 `var(--ink2)`（不能一修就整排變紅）、
  ④ 把 inline style 換回舊寫法要逐 byte 回到 v1.7 的 md5。
  另外驗 `label2` 兩行的座標與顏色、`numbered` 的結構與 CSS 不變、`defs` 少寫之後 qa 仍全綠。

跑法：`python3 tests/run_tests.py` → `[ALL PASS]`。
