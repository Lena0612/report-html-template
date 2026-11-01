# report-html-b v1.8 → v1.9（2026-09-17）

三項**宣告才生效**的新能力 ＋ 一項**驗證判準放寬（有補位）**。
不宣告時，八個樣張的 HTML md5 逐 byte 與 v1.8 相同；JS／CSS／`themes.py` 零變動。

| # | 項目 | 型態 | 來源 |
|---|---|---|---|
| 1 | `subtitle`／`produced`／`note_base` 從必填改成選填，沒填＝整塊不渲染 | 宣告才生效（不寫才有差） | Lena 2026-09-17 10:18 第 1 點 |
| 2 | ```` ```table ```` 的 `col_groups`＝欄位群直向粗框 | 宣告才生效 | 同上第 8 點（點名表 1-7） |
| 3 | 檔頭 `conclusion_lead`／`conclusion_badge`／`conclusion_box` 三個結論區開關 | 宣告才生效 | 同上第 4、5 點 |
| 4 | `qa_html` 第 17 項的「母體註腳剛好 1 列」→「0 或 1 列，且不准是空殼」 | 判準變更（補位更嚴） | 第 1 點的連帶 |

---

## 1. 三個檔頭欄位改選填（`scripts/mdcontent.py`、`scripts/rhtml.py`、`scripts/figures.py`）

```
FM_REQ  v1.8: title subtitle period population source produced byline
        v1.9: title          period population source          byline
```

- **`subtitle`**：沒寫時 `<p class="subtitle">` **整行不出現**（不是留一個空的 `<p>`、也不是留一行空白）。
  有寫時輸出與 v1.8 逐 byte 相同。
- **`produced`**：沒寫時標題區的資料說明列少掉「產出日期」那一項，**連它前面那根 `｜` 分隔線一起少**
  （既有的 `if v: R.meta(...)` 本來就會跳過，這次只是把必填拿掉）。
- **`note_base`**：v1.5 起本來就是選填，但有兩個毛病：
  1. 沒有 `note_base`、只有 `note_extra` 時，備註會印成 `｜補充…`（開頭掛一根孤兒 `｜`）→ 修掉。
  2. `_check_common` 會報「缺母體註腳」，等於逼每個區塊都要有一行母體 → **放寬**。
  沒有母體註腳時，`<p class="blk-note">` **整塊不渲染**。
- 放寬的同時補一條**更嚴**的守門：`note`／`note_extra` 寫了 key 卻留空 → 報錯 ＋ 行號 ＋ exit 1
  （作法與 v1.8 的 `defs` 空值守門一致）。

## 2. `col_groups`＝欄位群直向粗框（`scripts/figures.py`、`scripts/rhtml.py`）

```yaml
columns: [玩法, 佔牌桌時間下滑%, 人均分鐘 前, 人均分鐘 後, 分鐘變化%, 人均手數 前, 人均手數 後, 每手秒數 前, 每手秒數 後, 手數貢獻比, 秒數貢獻比]
col_groups: [1, 1, 3, 2, 2, 2]     # 由左往右：每一群幾欄，加總＝欄數
```

- 命名與寫法對齊既有的 `row_groups`（每群幾個、由外往內數、加總要對）。
- 走 **inline style**（`border-left:2px solid var(--line)`），沿用 `row_groups` 的色票與線寬，
  **CSS 一個 byte 都不用改**。
- **只畫群與群之間**，最右邊不收線：欄向本來一條直線都沒有，右緣再收一條會變成沒有左緣的半框。
  （`row_groups` 收底線是因為每列本來就有 1px 橫線、需要一條更粗的收尾；欄向沒有這個前提。）
- **不會**把排序關掉。`rowspan`／`row_groups`／`sig dir: tb` 綁的是「列的位置」，排序會打散它們；
  `col_groups` 綁的是欄，排序只重排列，粗框跟著欄走。所以它不進 `fixed` 那條路、不帶 `data-fixed="1"`。
- 一格同時要「檢定底色」與「直粗框」時，兩段宣告**併進同一個 `style` 屬性**
  （一個元素不能有兩個 `style=`）。只有底色時字串與 v1.8 完全相同。
- `rowspan` 合併過的格子照樣帶得到粗框（線會跨滿那幾列）。
- 守門：非正整數 ／ 加總跟欄數對不上（錯誤訊息會把欄號對照表印出來）／ 只寫一群
  （一條線都畫不出來）→ 報錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML。

## 3. 結論區三個開關（`scripts/mdcontent.py`、`scripts/rhtml.py`）

```yaml
conclusion_style: numbered
conclusion_lead: false      # 不印「紅＝漲、綠＝跌，▲▼ 與正負號同步。」那行小字
conclusion_badge: false     # 不印區塊標題右邊那顆「最重要」膠囊
conclusion_box: true        # 每一條結論各自一個區塊（灰底；標 [up] 的那條紅底紅字）
```

- `conclusion_lead: false`：那一行**連同它那一行**一起不出現（不留空白行）。
- `conclusion_badge: false`：「最重要」是 `themes.py` 的
  `.theme-b .sec-key .sec-h::after{content:"最重要"}`。**`::after` 的 `content` 沒辦法被 inline style
  蓋掉**，CSS 又凍結，所以唯一的路是**不要掛 `sec-key` 這個 class**。
  `.sec-key` 另外帶的兩條宣告（`border-top:4px solid var(--up)`、`background:#fff`）與
  `.sec-key .sec-ico{color:var(--up)}` 用 inline style **原樣補回來**——驗收比的是
  **最終生效值**（`4px solid var(--up)`／`#fff`／`var(--up)` 三項在開關前後完全相同），
  差別只有來源從 `css` 變成 `inline`。
  ⚠ 只針對出貨中的風格 B 還原；風格 A／C 的 `.sec-key` 規則已於 2026-09-14 收掉，不在還原範圍。
- `conclusion_box: true`：`list`／`numbered` 的每一條 `<li>` 掛一段 inline style
  （`background:var(--panel)` ＋ 1px 框 ＋ 圓角 ＋ padding ＋ 下邊距）。
  **紅底紅字綁既有的 tone 語意**：標 `[up]`（漲／重點）的那一條改成
  `background:var(--up-bg)` ＋ `border:1px solid var(--up)` ＋ `color:var(--up)`，
  不另外發明一套標記。`◦` 子項不包框（要的是「每一點」一個區塊，不是每一行）。
  守門：配 `card`（或沒寫 `conclusion_style`）→ 報錯（卡片本來就是一張張卡片）。

## 4. `qa_html` 第 17 項（`scripts/qa_html.py`）

| | v1.8 | v1.9 |
|---|---|---|
| defs 列數 | 維度／指標／著色 挑 1~3 列，順序固定 | 同 |
| 母體註腳 | **剛好 1 列** | **0 或 1 列** |
| 空殼 | （不可能發生） | **新增：`<p class="blk-note"></p>` 一個都不准有** |

放寬的是「可以不印」，不是「可以印一個空殼」——補位的那一條比原本更嚴。

## 測試（`tests/run_tests.py`，新增 `tests/htmlres.py`）

- A 回歸：八個樣張 md5 全部維持 v1.8 定版；JS／CSS／`themes.py` 三個 md5 不變。
- C 負向：27 → **35 條**（col_groups 三條、結論三開關三條、note_extra 空值、subtitle 型別）。
- **F 段（新）**：三項新能力各自的正向 ＋ 還原比對。
  - `tests/htmlres.py`＝把 `<style>` 的規則跟 **HTML 元素**（不是 SVG）跑一次串接，
    算某個屬性的最終生效值與來源；另提供 `count_matching()` 問「某條選擇器命中幾個元素」。
    `cssres.parse_css()` 多一個 `props` 參數（不給就是原本的 fill／stroke，E 段判準一個字沒改）。
  - 還原比對三條：把 subtitle／produced／note_base 寫回去、把 col_groups 拿掉、
    把三個結論開關拿掉 —— 各自要**逐 byte** 回到 v1.8 的 md5。

跑法：`python3 tests/run_tests.py` → `[ALL PASS]`。
