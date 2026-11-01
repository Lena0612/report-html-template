# report-html-b skill v1.5 → v1.6（2026-09-16）

**這一版是兩條並行分支合併的結果**（同一天下午各自開發、各自驗過、都沒安裝）：

- **A 線**：折線事件線的警示 icon ＋ 檢定底色只標數值較大的一格
- **B 線**：檢定底色依檢定強度分深淺三階 ＋ 備註固定四列

兩線唯一重疊的是 `figures.py` 與 `rhtml.py` 的 sig 那一段。合併原則是**兩者正交、可併用**：
`mark` 決定「哪一格上色」、`scale`／`levels` ＋ 每組的 `v` 決定「那一格多深」。

三項能力**都是「宣告才生效」**，第四項是規範；不宣告時輸出與 v1.5 逐 byte 相同。
沒有新圖型、沒有新 CSS、沒有新 JS，版心／配色／字級／版型一個字都沒動。

## 1. `vlines` 的 `icon: warn`（A 線；Lena 14:12 第 2 點）

```
vlines:
  - {at: 2026-05-28, label: v9.5 換版}                        # 一般事件：墨色虛線、標籤在圖頂（v1.5 行為）
  - {at: 2026-06-02, label: 6/2 跌點, color: red, icon: warn}  # 跌點：紅虛線 ＋ 三角驚嘆號在圖下方
```

- 在事件線的**下端**（離 x 軸 7px）畫一個紅色三角驚嘆號，**形狀與行內 `{{warn}}` 完全相同**
  （同一組 path，24×24 viewBox 縮 0.62 ≒ 14.9px 高），顏色跟著 `vlines.color` 走（預設 `#c62828`）。
- 宣告 `icon` 時**事件標籤也一起移到圖下方**，不跟序列與圖頂的直接標註擠在一起。
- 為什麼要改引擎：`{{warn}}` 是 HTML `<span>`，塞不進折線圖的 `<svg>`；v5 只能在圖內放紅色「!」。
- 只有 `warn` 一種，不吃參數（`icon: danger` 會報錯並提示）。

改到的檔：`scripts/svgchart.py`（新增 `warn_icon()` ＋ vlines 迴圈多吃第 4 個欄位）、
`scripts/figures.py`（`Line.VL` 多一個 `icon`、值域檢查）。

## 2. `sig` 的 `mark: max`（A 線；Lena 14:12 第 1 點 ＋ Wayne 定案）

```
sig:
  dir: lr
  mark: max          # 一組配對只標數值較大的一格；不寫＝both＝v1.5 行為（兩格都標）
  pairs:
    - {row: 1, a: 2, b: 3}
```

- 決定的是**哪一格**上色，不決定深淺。只寫 `mark: max`（不寫 `v`）＝單一階 `#d7e3ee`，
  跟 v1.5 同一個色，只是一組配對改成只標一格。
- 大小比較優先用該格的排序值（`顯示@@排序值`），沒有排序值就從 `{{d:…}}`／`{{n:…}}` 挖數值，
  再去掉千分位、`%`、`pp` 與全形正負號；**讀不出數字會報錯**（不猜）。
- 兩格數值相同時兩格都標。
- 備註標準句自動換成「底色著色為經統計檢定有顯著差異，左右（／上下）配對中只標數值較大的一格」；
  `note: false` 可以關掉（自己寫在「著色」那一列時用）。

改到的檔：`scripts/figures.py`（`SIG_FIELDS` 多 `mark`、`_cellnum()`、`_table_v15()` 多吃 `hdr`）、
`scripts/rhtml.py`（tooltip 那一句文案分兩種）。

## 3. `sig` 的底色深淺三階（B 線；Lena 15:12「可以有深淺底色（不只單色）」）

```
sig:
  dir: lr
  scale: "|t|"           # 強度值是哪一種統計量（必填，會印進備註與 tooltip）
  levels: [2.58, 3.29]   # 兩個切點（必填，由小到大、非負）→ 固定三階
  pairs:
    - {row: 1, a: 2, b: 3, v: 5.91}
```

- 決定的是**那一格多深**：`#d7e3ee`（L\* 89.6）／`#b0c8db`（79.4）／`#8baec9`（69.5），
  同一個藍色相只動明度，每階差約 10 個 L\*；灰階 luma 225／196／169（相鄰對比 1.33／1.35）。
- **第 1 階就是 v1.5 那個 `#d7e3ee`**，所以一組都不帶 `v` 時輸出逐 byte 不變。
- **階數固定 3、不開放調**（四階以上影印會糊，見 風格B設計決定.md 決定 36）。
- 上色格多帶 `data-sig-lv="1|2|3"`，`title` 帶統計量名稱、數值與第幾階（色盲／灰階也讀得到）。
- 備註句自動接上「｜底色深淺＝|t|，越深證據越強（三階：< 2.58／2.58 ~ 3.29／≥ 3.29）」。

改到的檔：`scripts/figures.py`（`SIG_FIELDS` 多 `scale`／`levels`、`SIG_PAIR` 多 `v`、
`_sig_num()`／`_sig_scale()`／`_sig_level()`）、`scripts/rhtml.py`（`SIG_SHADE` 三階色票 ＋ `_sig_bg()`）。

## 4. 備註固定四列（B 線；Lena 15:12 的規範）

每張圖表的備註固定是 `defs` 的 維度／指標／著色 三列 ＋ 母體一列（`note`／`note_extra`／檔頭 `note_base`）。
`defs` 多寫任何一個鍵（例 `母體:`、`口徑:`）就報錯，`qa_html.py` **新增第 17 項**再查一次
（每個圖表區塊要剛好 3 個 `.def-r` ＋ 1 個 `.blk-note`）。既有 16 項的判準一項都沒改。

## 2 ＋ 3 併用（合併時新寫的組合語意）

`mark` 與深淺分級是**正交**的，可以只用一個，也可以一起寫：

```
sig:
  dir: lr
  mark: max
  scale: "|t|"
  levels: [2.58, 3.29]
  pairs:
    - {row: 1, a: 2, b: 3, v: 5.91}     # 較大那格上第 3 階
    - {row: 2, a: 2, b: 3, v: 2.12}     # 較大那格上第 1 階
```

- 結果＝**只有較大那格上色、深淺依檢定強度**。
- tooltip 兩件事各講一次：「…此格為左右配對中數值較大的一格｜|t|＝5.91（第 3 階／共 3 階，越深證據越強）」。
- 自動備註句也是兩句相疊、不重複也不矛盾：
  「底色著色為經統計檢定有顯著差異，左右配對中只標數值較大的一格｜底色深淺＝|t|，越深證據越強（三階：…）」。

## 檔案變動總表

| 檔 | 變動 | 來源 |
|---|---|---|
| `scripts/svgchart.py` | +37 行（`warn_icon()`、vlines 迴圈、docstring） | 全部取 A |
| `scripts/figures.py` | icon 欄位、mark 欄位、`_cellnum()`、`SIG_NOTE_MAX`（A）＋ `SIG_LEVELS`／`SIG_NOTE_LV`、`scale`／`levels`／`v`、`defs` 四列守門、`_sig_num()`／`_sig_scale()`／`_sig_level()`（B）＋ sig 主段合寫 | **A＋B 合併** |
| `scripts/rhtml.py` | `SIG_SHADE` 三階色票 ＋ `_sig_bg()`、cells 改 dict（B）＋ mark 版 tooltip 文案（A）＋ 兩者相接的 `sigbase`（新寫） | **A＋B 合併** |
| `scripts/qa_html.py` | 新增第 17 項「備註四列」，既有 16 項一字未改 | 全部取 B |
| `scripts/build.py` | 只有 `--types` 的一行版號字樣 v1.5 → v1.6 | 合併時統一 |
| `scripts/themes.py` | **零變動**（md5 `f62fd318132b25010543040a97d0e27c`、CSS md5 `84b3f2cef683bed91dbfe2cfe9b818a0`） | — |
| `scripts/mdcontent.py`／`yamlite.py`／`inspect_inputs.py` | **零變動** | — |
| `SKILL.md`、`references/*.md`、`assets/templates/報告內容.template.md` | 兩邊的新增都在（vlines icon、sig mark；深淺三階、備註四列 §3.1、決定 36／37、報錯表）；全樹版號統一 v1.6 | **A＋B 合併** |
| `examples/charts-demo-6/` | **新增**：事件線 icon ＋ `mark: max` 的最小樣張 | A |
| `examples/sig-shade-demo/` | **新增**：底色深淺三階的最小樣張 | B |
| `tests/run_tests.py` | **新增**：兩邊的測試併成一支 | A＋B＋新增組合案例 |

## 驗收（`python3 tests/run_tests.py` → `[ALL PASS]`）

六個舊樣張用 v1.6 重建，HTML md5 逐位元不變：

| 樣張 | md5 |
|---|---|
| playtime-demo | `71e83fef226ba994fd81f62c0bfb5129` |
| charts-demo | `a08feea5023b54e4b8af833fc74cd33d` |
| charts-demo-2 | `60963a3058585c0a0c63518c815041fa` |
| charts-demo-3 | `342070f854158fb6664961a29a2090a9` |
| charts-demo-4 | `25bff0c5aa7bcc0d320d7517eaec476f` |
| charts-demo-5 | `49d04f74e7a485e36f0d6e0f31f3a869`（sig 這段的守門員：宣告了 sig 但沒帶 mark 也沒帶 v） |

JS md5 `79e2d5b43d53764e88de8a6771c64253`（未變）／CSS md5 `84b3f2cef683bed91dbfe2cfe9b818a0`（未變）／
`themes.py` 檔案 md5 `f62fd318132b25010543040a97d0e27c`（未變）。

兩個新樣張 build exit 0、`qa_html.py` **17 項**全綠：
`charts-demo-6`（圖內 icon 2 個＋正文 1 個、顯著底色 3 格＝3 組配對各 1 格、沒有深淺階）、
`sig-shade-demo`（5 組配對共 10 格，第 1 階 2 格／第 2 階 4 格／第 3 階 4 格）。

併用組合：`charts-demo-6` 補上 `scale`／`levels`／`v` 後，3 格各自落在第 3／1／2 階，
tooltip 與自動備註句都同時講到「哪一格」與「多深」且不重複。

負向案例 **19 條**（都要「報對的錯 ＋ 行號 ＋ exit 1 ＋ 不寫任何 HTML」）：

- 事件線／mark 這條線 5 條：`vlines.icon` 非 warn ／`vlines.color` 非 red／ink ／`sig.mark` 非 both／max ／
  `mark: max` 但配對格讀不出數字 ／`sig.pairs` 的 a 與 b 指到同一格。
- 深淺分級這條線 13 條：`v` 負數／非數字、`levels` 1 個／3 個／倒序／負數／非數字、
  有 `v` 沒 `scale`、有 `v` 沒 `levels`、只有部分 pair 帶 `v`、沒 `v` 卻寫 `levels`、
  `defs` 多一個 `母體` 鍵／多一個 `口徑` 鍵。
- 併用 1 條：`mark: max` ＋ `v` 併用但某一格不是數字。

隔離環境：`python3 -I` ＋ 行程內 meta_path 封 numpy／pandas／scipy／matplotlib／statsmodels，
**先斷言五個都真的 ImportError** 才往下跑，八個 example 全綠；zip 解到乾淨目錄再跑一次同樣全綠。

## 安裝

```bash
# 先備份現行安裝版（v1.5）
cp -r ~/.claude/skills/report-html-b ~/.claude/skills/report-html-b.v15.bak
# 再覆蓋
rm -rf ~/.claude/skills/report-html-b && unzip -q report-html-b-v1.6.zip -d ~/.claude/skills/
python3 ~/.claude/skills/report-html-b/tests/run_tests.py     # 要印 [ALL PASS]
```

**這份還沒安裝到 `~/.claude/skills/report-html-b`**（照指示放工作區等你驗）。
