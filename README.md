# report-html-template

把分析材料（跑完的 notebook、csv、寫好結論的 md）變成**單一檔案的互動式 HTML 分析報告**。

純 Python 3 標準庫實作，**不依賴 numpy／pandas／matplotlib**，圖表為自寫的 SVG 引擎。產出的 HTML 零外部資源，可離線開啟、可直接列印成 PDF。

```
報告內容.md（文字 ＋ 圖表宣告 ＋ 數值定義）
        │
        │  python3 scripts/build.py
        ▼
   單檔 report.html  ──→  python3 scripts/qa_html.py（18 項自動檢查）
```

---

## 為什麼做這個

數據分析的交付常卡在同一組問題：

| 問題 | 這個工具的處理方式 |
|---|---|
| 每份報告的配色、字級、版面都要重新決定，成品不一致 | 版型與視覺設計一次鎖定，內容與呈現分離 |
| 正文寫的數字和圖表對不上（改了資料忘了改內文） | **數值單一來源**：正文用 `{{v:指標名}}` 佔位，數字由 csv 即時計算填入 |
| Notebook 交付對方要有環境才能開 | 輸出單檔 HTML，零外部資源，任何瀏覽器可開 |
| 要轉 PDF 給主管或存檔 | 列印樣式已處理，瀏覽器直接列印即可 |
| 交付前漏檢查（圖沒資料、數字沒來源、口徑沒寫） | `qa_html.py` 18 項檢查，含「正文每個數字都要能在圖表資料中找到」 |

---

## 核心設計

### 1. 內容與呈現分離

一份報告 = 一個 `報告內容.md`。YAML 檔頭定義標題、期間、母體、口徑、資料來源與數值；正文為 markdown；圖表以 fenced block 宣告：

````markdown
```line
title: 日活躍人數走勢
data: data/dau_daily.csv
x: date
series: [新客, 回訪]
event: {at: 2026-09-10, label: 改版上線}
```
````

### 2. 數值單一來源（values 機制）

檔頭宣告數值的**計算方式**而非數值本身：

```yaml
values:
  前段平均: {fn: mean, fig: ts_break, col: raw, seg: pre, fmt: n, nd: 2, unit: 分}
  平均變化率: {fn: pct_change, fig: ts_break, col: raw, a: pre, b: post, fmt: d, nd: 1, unit: "%"}
```

正文寫 `斷點前後由 {{v:前段平均}} 掉到 {{v:後段平均}}（{{v:平均變化率}}）`，建置時從 csv 算出並填入。**資料更新，正文數字跟著更新**，不會出現內文與圖表矛盾。

支援的聚合函式包含 `mean`／`sum`／`max`／`min`／`range`／`diff`／`pct_change`／分位數等。

### 3. 自寫 SVG 圖表引擎（14 種類型）

| 分析問題 | 圖表類型 |
|---|---|
| 隨時間怎麼走、斷點前後差多少 | `line`（可標事件線、分位帶） |
| 總變化拆成幾塊 | `waterfall` |
| 組成前後對照（占比） | `stacked100` |
| 誰貢獻最多 | `ranked` |
| 類別各自多少 | `bars` |
| 多期組成變化（絕對值） | `stacked` |
| 幾群的 D1/D3/D7/D14/D30 留存 | `retention` |
| 類別 × 序列並排比較 | `grouped` |
| 各步驟轉換率 | `funnel` |
| cohort × 天數留存 | `cohort`（熱圖） |
| 分布與分位數 | `hist` |
| 每群前後兩值與變化 | `dumbbell` |
| 星期 × 小時分布 | `dow_hour`（熱圖） |
| 指標 × 分組的檢定強度 | `sigheat`（熱圖） |

另有表格區塊，支援多層表頭、`rowspan`／`colspan` 合併格、欄位群直向粗框、熱力圖著色、**依統計檢定強度分三階深淺的顯著性底色**。

### 4. 交付前自動檢查

`qa_html.py` 18 項，包含結構完整性、無外部資源引用、浮動目錄錨點正確、列印樣式存在，以及最關鍵的一項：**正文出現的每個數字都必須能在圖表／表格資料中找到對應來源**。

---

## 用法

需求：Python 3.8+，無須安裝任何套件。

建置一份報告：

```bash
python3 scripts/build.py --md 報告內容.md --out out/
```

檢查產出：

```bash
python3 scripts/qa_html.py out/你的報告.html
```

盤點手上的材料（列出每個 csv／ipynb 可用的欄位與表格）：

```bash
python3 scripts/inspect_inputs.py ./你的資料夾 --rows 5
```

跑測試：

```bash
python3 tests/run_tests.py
```

---

## 專案結構

```
report-html-template/          # 本體
├── SKILL.md                   # 完整使用說明（作為 Claude skill 的進入點）
├── scripts/
│   ├── build.py               # 建置入口
│   ├── mdcontent.py           # 內容檔解析（YAML 檔頭 + markdown + 圖表宣告）
│   ├── yamlite.py             # 輕量 YAML 解析器（標準庫實作）
│   ├── figures.py             # 圖表宣告 → 資料整形 → 繪圖參數
│   ├── svgchart.py            # SVG 繪圖引擎
│   ├── rhtml.py               # HTML 組裝（版面、目錄、表格、互動）
│   ├── themes.py              # 版型設計 token（配色、字級、間距）
│   ├── qa_html.py             # 交付前 18 項檢查
│   └── inspect_inputs.py      # 材料盤點工具
├── references/                # 圖表宣告格式、內容檔格式、設計決定
├── examples/                  # 9 組可執行範例（示意假資料）
├── tests/run_tests.py         # 測試
├── assets/templates/          # 內容檔範本
└── CHANGELOG-v1.6 ~ v1.11.md

docs/                          # 安裝步驟、使用範例、版本差異對照
dist/                          # 可直接安裝的壓縮檔
```

程式碼約 9,500 行（含測試），全部 Python 標準庫。

---

## 範例

`report-html-template/examples/` 下有 9 組可直接執行的範例，各自附 README 說明資料形狀與對應宣告：

| 範例 | 示範內容 |
|---|---|
| `playtime-demo` | 完整報告：斷點前後比較、指數化、星期效應、前後對照表 |
| `charts-demo` ~ `charts-demo-7` | 各批次新增圖表類型的最小範例 |
| `sig-shade-demo` | 表格的檢定顯著性著色（三階深淺） |

**所有範例的數字皆為示意合成資料，非真實業務數據，不可引用。**

---

## 版本

目前 v1.11。各版新增能力見 `report-html-template/CHANGELOG-*.md`，v1.6 → v1.11 的完整差異對照見 `docs/`。

設計原則：新增能力一律「宣告才生效」，不宣告時行為與前一版完全相同，既有報告重建結果不變（範例附 HTML md5 供回歸驗證）。
