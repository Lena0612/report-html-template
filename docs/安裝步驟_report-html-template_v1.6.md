# 安裝步驟 — report-html-template v1.6

> 這份是「怎麼把這包裝到妳桌機上」。怎麼寫報告看旁邊的 `使用範例.md`。

## 這一包跟妳手上那份差在哪

| | |
|---|---|
| **改名** | skill 名稱由 `report-html-b` 改成 **`report-html-template`**（妳 09-16 16:40 指定）。**只改名稱字串，引擎與 HTML 輸出零變動**——八個樣張的 md5 改名前後逐 byte 相同。 |
| **妳手上如果是 v1.4** | 多了 v1.5 的八項（表格檢定底色 `sig`、`rowspan` 合併格、`row_groups` 列群組粗框、`line` 的 `xticks`、`{{warn}}` 警示 icon、結論區可放表格、`appendix: false`、`hints: false`）＋ 下面 v1.6 那四項。 |
| **妳手上如果是 v1.5** | 多了 v1.6 的三項能力（`line` 事件線 `icon: warn`、`sig` 的 `mark: max` 只標較大格、`sig` 檢定底色依強度分**深淺三階**）＋ 一條規範（**備註固定四列**：維度／指標／著色 ＋ 母體，`defs` 多一個鍵會直接報錯）。 |
| **沒動的** | 版心 1120、配色、字級、版型、互動 JS、CSS **一個 byte 都沒動**（JS md5 從 v1.1 起就是 `79e2d5b43d…`）。沒有新圖型，還是 14 種 ＋ 表格。 |
| **新東西都是「宣告才生效」** | 不宣告 = 輸出跟舊版逐 byte 相同。舊的 `報告內容.md` 直接拿來 build 不會變樣。**唯一的例外是備註四列**：`defs` 如果寫了第四個鍵（例如 `母體:`），這版會擋下來要妳改。 |

逐條的完整版本差異看 `CHANGELOG-v1.6.md`。

---

## 0. 先看這三件事

| | |
|---|---|
| **環境需求** | **只要 Python 3.7 以上，純標準庫。不需要 numpy、不需要 pandas、不需要 pip install 任何東西。** |
| **會不會上網** | 不會。build 出來的 HTML 也是零外部資源，離線可開、可直接列印轉 PDF。 |
| **這包是什麼** | skill 樹本體（61 檔）＋ 本安裝步驟 ＋ 使用範例。引擎版本 **v1.6，凍住不動**。 |

確認 Python 有了就好：

```bash
python3 --version        # 3.7 以上都可以
```

> Windows 桌機：把下面所有 `python3` 換成 `py -3`，路徑分隔用 `\`，`~` 換成 `%USERPROFILE%`。
> 指令本身（`build.py`／`qa_html.py`／`run_tests.py`）完全一樣。

---

## 1. 這包解開長什麼樣

```
report-html-template/
  SKILL.md                      主說明（第 6 節是報錯表）
  安裝步驟.md                    本檔
  使用範例.md                    ← 寫報告看這份
  CHANGELOG-v1.6.md             v1.5 → v1.6 差在哪、改名紀錄
  scripts/                      引擎（7 支 .py）
    build.py                    報告內容.md → HTML
    qa_html.py                  17 項自我檢查
    inspect_inputs.py           盤點資料夾
    mdcontent.py figures.py yamlite.py svgchart.py rhtml.py themes.py
  references/                   三份規格書
    內容檔格式說明.md             報告內容.md 每一段怎麼寫
    圖表與數值宣告格式.md          14 種圖＋表格的完整欄位表（§3.1 是備註四列正本）
    風格B設計決定.md              鎖定的設計決定
  assets/templates/報告內容.template.md    可直接 build 的空骨架
  examples/                     8 個樣張（每個都是一個完整的小專案）
  tests/run_tests.py            回歸測試，裝完跑這支
```

**`scripts/` 裡的東西不要改。** 版型、配色、字級、互動都鎖死了，改了下次更新會被蓋掉，
而且 `tests/run_tests.py` 會紅。妳要調的東西全部在 `報告內容.md` 裡。

---

## 2. ⚠ 妳桌機上已經有一個 `report-html-template` 資料夾

**先不要解壓縮、先不要覆蓋。** 照下面三步走。

### 2-1 先確認舊的是哪一版、裡面有沒有妳自己的東西

```bash
cd <舊的 report-html-template 資料夾>

# ① 是哪一版？看 SKILL.md 標題那一行的結尾
grep -m1 '^# ' SKILL.md
#   → 印出 …（skill v1.4）／（skill v1.5）  = 舊的 skill 樹
#   → 沒有 SKILL.md 這個檔                  = 不是 skill 樹，是妳自己的工作資料夾

# ② 有幾個樣張？v1.6 是 8 個
ls examples/ 2>/dev/null | wc -l
#   5 個 = v1.4 ／ 6 個 = v1.5 ／ 8 個 = v1.6

# ③ 有沒有 tests/？ v1.5 以前沒有
ls tests/run_tests.py 2>/dev/null

# ④ 最重要：裡面有沒有妳自己寫的報告？
find . -name '報告內容.md' -not -path './examples/*' -not -path './assets/*'
find . -name '*.html' -not -path './examples/*'
ls data/ 2>/dev/null
```

第 ④ 步印出東西 = **裡面有妳的工作檔，絕對不能直接覆蓋**。

### 2-2 整個改名留著，不要刪

不管舊的是哪一版，**一律改名保留，不要 `rm -rf`**。硬碟很便宜，重寫一份報告很貴。

```bash
mv report-html-template report-html-template.舊_20260916
```

改名（不是複製）比較安全：舊資料夾整個離開原位，新的解上來不會跟殘留檔混在一起。
確認新版跑得起來、妳的報告也搬過去之後，過幾天再刪舊的。

### 2-3 覆蓋前一定要留下來的東西

舊資料夾裡這幾類是**妳的**，不是引擎的，新版不會有：

| 要留的 | 長怎樣 | 搬到哪 |
|---|---|---|
| 妳自己寫的 `報告內容.md` | 在 `examples/` 與 `assets/` **以外**的任何地方 | 搬到新的工作資料夾（見第 5 節，建議放在 skill 樹外面） |
| 對應的 `data/*.csv`、`data/values.json` | 同上 | 跟著 `報告內容.md` 一起搬 |
| 產出的 `*.html` | 已經交出去的報告 | 另存一份，不要留在 skill 樹裡 |
| 妳改過的引擎檔 | `scripts/*.py` 如果妳動過 | **先跟我說一聲**，我看一下是不是要併進正式版；不要直接蓋回新版 |

一次搬走的寫法：

```bash
mkdir -p ~/reports/從舊template搬出來
cd report-html-template.舊_20260916
# 把 examples／assets 以外的 報告內容.md 跟它旁邊的 data/ 一起搬
find . -name '報告內容.md' -not -path './examples/*' -not -path './assets/*'
# 看清楚上面印出的路徑，再一個一個 cp -r 它們的「上一層資料夾」過去
```

---

## 3. 解壓縮

解到跟舊資料夾**同一個上層目錄**（這樣路徑習慣不變）：

```bash
cd <舊資料夾的上一層>
unzip -q 報告版型_report-html-template_v1.6.zip
ls -d report-html-template          # 應該出現了
```

zip 裡的最上層就叫 `report-html-template`，所以解完直接就是對的名字，**不用再改名**。

如果妳是把它當 Claude Code 的 skill 用（讓 Claude 自己讀 SKILL.md 幫妳做報告）：

```bash
unzip -q 報告版型_report-html-template_v1.6.zip -d ~/.claude/skills/
ls ~/.claude/skills/report-html-template/SKILL.md
```

> 這包**沒有**自動安裝到任何地方，解在哪就在哪。兩種用法（純命令列 / 當 skill）可以並存。

---

## 4. 確認裝好了：跑這一行

```bash
python3 report-html-template/tests/run_tests.py
```

**看到最後一行是 `[ALL PASS]` 就是成功。** 全程約 20～40 秒，會印四段：

```
=== A 回歸：六個舊樣張的 HTML md5 要逐 byte 相同 ===
  [OK  ] playtime-demo    71e83fef226ba994fd81f62c0bfb5129
  ...（六個）
=== A 回歸：JS／CSS 逐字元不變、themes.py 檔案零變動 ===
  [OK  ] JS               79e2d5b43d53764e88de8a6771c64253
  [OK  ] CSS              84b3f2cef683bed91dbfe2cfe9b818a0
  [OK  ] themes.py        f62fd318132b25010543040a97d0e27c
=== A 回歸：兩個 v1.6 新樣張 build ＋ qa 17 項全綠 ===
  ...
=== C 負向（19 條）：宣告寫錯要報對的錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML ===
  ...（19 條）

[ALL PASS]
```

有任何一行 `[FAIL]`，**把那幾行整段貼給我**，先不要自己動 `scripts/`。

### 再實際做一份報告出來看看

```bash
cd report-html-template
python3 scripts/build.py --md examples/playtime-demo/報告內容.md --out /tmp/試跑
python3 scripts/qa_html.py "/tmp/試跑/示意遊戲－平均遊戲時間下滑.html"
```

`build.py` 印一行 `[build] …html` ＋ 統計（圖幾張表幾張），`qa_html.py` 最後印
**`總結：全部通過`**（17 項全 `[OK  ]`）。用瀏覽器打開那個 HTML，**拔掉網路也要能正常顯示與互動**。

---

## 5. 開始寫自己的報告

**建議把工作資料夾放在 skill 樹外面**，這樣下次更新引擎直接覆蓋 `report-html-template/`
也不會碰到妳的東西：

```bash
mkdir -p ~/reports/我的報告/data
cp <report-html-template 解在哪>/assets/templates/報告內容.template.md ~/reports/我的報告/報告內容.md

# 資料放 ~/reports/我的報告/data/*.csv，然後：
python3 <report-html-template 解在哪>/scripts/build.py \
        --md ~/reports/我的報告/報告內容.md \
        --out ~/reports/我的報告/out
```

`data:` 路徑是**相對於 `報告內容.md` 所在資料夾**，不是相對於 `build.py`，所以工作資料夾放哪都行。

怎麼填 `報告內容.md` → 看 `使用範例.md`。

---

## 6. 裝完之後

- 這版是 **v1.6，凍住**。之後累積幾個改動我會再出一包，不會一天給妳三個版本。
- 有件事先講明：**v7 的印尼報告是用 v1.7 引擎產的**（圖例搬到 x 軸下方），這包是 v1.6。
  妳拿到的那份 HTML 成品不受影響；但如果妳自己用這包重 build 同一份 `報告內容.md`，
  **圖例會回到圖的右邊**。要對齊再跟我說。
- `scripts/` 動過、或 `run_tests.py` 出現 `[FAIL]`，貼給我，不要自己修。
