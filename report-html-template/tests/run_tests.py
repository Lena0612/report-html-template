# -*- coding: utf-8 -*-
"""report-html-b 自我測試（skill v1.9）。

    python3 tests/run_tests.py

v1.6 是兩條並行分支合併的版本，這支腳本把兩邊的測試併在一起：
  A 回歸 — 六個舊樣張用現在的引擎重建，HTML md5 必須跟 v1.5 定版逐 byte 相同。
          v1.6 的三項新能力（事件線 icon／sig mark: max／sig 底色深淺三階）都是
          「宣告才生效」，舊樣張沒宣告 → 一個 byte 都不該變。
          再加 v1.6 的兩個新樣張 charts-demo-6（icon ＋ mark）與 sig-shade-demo
          （深淺三階）：build 成功、qa_html 17 項全過。
  B 組合 — mark: max（標哪一格）與 scale/levels+v（那一格多深）是正交的兩件事，
          必須能併用：只有較大那格上色、深淺依檢定強度。
  C 負向 — 宣告寫錯時要「報對的錯 ＋ exit 1 ＋ 不寫出 HTML」，不可以默默吞掉。
          22 條＝事件線／mark 那條線 5 條 ＋ 深淺分級那條線 13 條 ＋ 併用 1 條
          ＋ v1.7 的 3 條（legend 值錯／conclusion_style 值錯／◦ 子項沒有主條目）。
  D v1.7 — 圖例搬到 x 軸下方（legend: bottom）與結論改純條列（conclusion_style: list）。
          新樣張 charts-demo-7 build ＋ qa 17 項全綠；再把兩個宣告各拿掉一次，
          驗「不宣告就回到 v1.6 的樣子」（圖例回右側、結論回條狀卡片）。
  E v1.8 — ① 顏色 bug：事件線的紅色本來寫成 presentation attribute，被 CSS 的
          `.chart .bkline{stroke:var(--ink2)}`／`.chart .bkl{fill:var(--ink2)}` 蓋掉，
          從 v1.4 起就沒紅過。這一段**不看原始碼有沒有屬性**，而是把 <style> 的規則
          跟每個 SVG 元素跑一次串接（specificity ＋ 出現順序 ＋ inline），算出**最終生效**
          的 fill／stroke，要求兩條跌點線與它們的標籤真的是 #c62828，而且全文件
          零處「presentation attribute 被 CSS 蓋掉」。
          ② 事件標籤第二行（label2）：宣告才生效，兩行同 x、差一個行高、都上紅。
          ③ 備註放寬（defs 1~3 列）：拿掉 維度 之後 build ＋ qa 仍全綠、備註剩兩列。

  F v1.9 — ① 檔頭 subtitle／produced／note_base 從必填改成選填：沒寫就**整塊不渲染**
          （不是空字串、不是空 <p>），資料說明列不留孤兒 ｜、母體註腳整段消失；
          title 等其餘必填仍然要擋。
          ② 欄位群直向粗框 col_groups：算**最終生效**的 border-left（誰贏的、值多少），
          檢定底色與粗框要併進同一個 style 屬性、rowspan 合併格也要帶得到、
          最右邊不收線、**不**把排序關掉。
          ③ 結論區三個開關 conclusion_lead／conclusion_badge／conclusion_box：
          「最重要」膠囊是 CSS ::after，沒辦法用 inline style 蓋掉，所以驗的是
          「沒有任何元素命中 .theme-b .sec-key .sec-h」；拿掉 sec-key 之後它原本帶的
          4px 紅上框、白底與 icon 紅色要用 inline 原樣補回來（比最終生效值，不比原始碼）。
          三項都附「拿掉宣告要逐 byte 回到 v1.8 的 md5」的還原比對。

  G v1.11 — 重點紅字從「一段最多一處」放寬成「一段最多 3 處」（Lena 2026-09-17 11:57
          「改引擎，同一段可以多處紅字，不要分段」）。放寬的是處數、不是不檢查，所以這一段驗：
          正向（同段 3 處真的渲染成 3 個 .hl、內容與順序對、**最終生效**的 color 與
          background 都是重點紅）、qa 17 項仍全綠、CSS 零變動、改回單處要逐 byte 回到
          v1.10 的 md5、build 期與 qa 期用的是同一個上限常數。
          負向 3 條併在 C 段（超過上限／!! 沒成對／!!!! 配對不出來），
          一律 exit 1 ＋ 行號 ＋ 不產 HTML。

全部通過印 [ALL PASS] 並 exit 0；有一項不過就列出來、exit 1。
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import cssres  # noqa: E402  串接判定（specificity ＋ 出現順序 ＋ inline）
import htmlres  # noqa: E402  同一支串接判定器，對象換成 HTML 元素（v1.9 F 段用）

RED = "#c62828"
# 這兩個 class 是顏色 bug 的現場：事件線與事件標籤。不管有沒有寫顏色屬性都要算出最終色。
WATCH = {"bkline", "bkl"}

# v1.5 定版（2026-09-16）的 HTML md5。改引擎預設行為就會變，變了就是改壞了。
# v1.8 只有一個例外：修掉事件線顏色 bug 之後，**有用到 vlines 紅色**的樣張
# （charts-demo-4／-6／-7）逐 byte 會變，變的內容剛好只有
#   stroke="#c62828" → style="stroke:#c62828"、fill="#c62828" → style="fill:#c62828"
# 兩種替換（已逐 byte 驗過）。沒用到 vlines 紅色的樣張一個 byte 都不准變。
BASELINE = {
    "playtime-demo": "71e83fef226ba994fd81f62c0bfb5129",
    "charts-demo": "a08feea5023b54e4b8af833fc74cd33d",
    "charts-demo-2": "60963a3058585c0a0c63518c815041fa",
    "charts-demo-3": "342070f854158fb6664961a29a2090a9",
    # charts-demo-4：v1.7 是 25bff0c5aa7bcc0d320d7517eaec476f（紅色沒生效的版本）
    "charts-demo-4": "277bf872c2c8b5dbfeef0183857100e5",
    # charts-demo-5 是 sig 這段唯一的守門員：v1.5 的單一階底色路徑一變它就會紅
    "charts-demo-5": "49d04f74e7a485e36f0d6e0f31f3a869",
    # charts-demo-6：v1.7 是 357e1df0444c545a5aaf5b5cec42f8d3（紅色沒生效的版本）
    "charts-demo-6": "ca1b7ccff537fafa52eae1d07cf090c8",
    "sig-shade-demo": "eef1e0d240d56ba0e4e6e61d9cf4862a",
}
# 只受顏色修正影響、且變動內容必須剛好是那兩種替換的樣張
COLORFIX = {
    "charts-demo-4": ("25bff0c5aa7bcc0d320d7517eaec476f", 1),
    "charts-demo-6": ("357e1df0444c545a5aaf5b5cec42f8d3", 2),
    "charts-demo-7": ("c7810a3ba5a831220554371a8ab436a9", 2),
}
# charts-demo-7 的 v1.8 md5：F 段「拿掉 v1.9 的宣告要逐 byte 回到 v1.8」的比對基準。
# （它本來只在 COLORFIX 裡有 v1.7 的值，v1.8 的值到 v1.9 才需要固定下來）
D7_MD5 = "f5f22578f6621a0c7ad719423dfb1775"
JS_MD5 = "79e2d5b43d53764e88de8a6771c64253"    # 互動 JS，從 v1.1 起不准變
CSS_MD5 = "84b3f2cef683bed91dbfe2cfe9b818a0"   # themes.py 的 CSS，從 v1.1 起不准變
THEMES_MD5 = "f62fd318132b25010543040a97d0e27c"  # themes.py 檔案本身，v1.6 零變動
QA_ITEMS = 17                                   # v1.6 新增第 17 項「備註四列」

# 併用組合：在 charts-demo-6（本來只有 mark: max）補上 scale／levels／每組的 v
COMBO = ("""  mark: max
  pairs:
    - {row: 1, a: 2, b: 3}
    - {row: 2, a: 2, b: 3}
    - {row: 3, a: 2, b: 3}""",
         """  mark: max
  scale: "|t|"
  levels: [2.58, 3.29]
  pairs:
    - {row: 1, a: 2, b: 3, v: 5.91}
    - {row: 2, a: 2, b: 3, v: 2.12}
    - {row: 3, a: 2, b: 3, v: 3.04}""")

# 負向案例：把 demo 的內容檔改一行（或幾行）→ 應該報這個錯、exit 1、不產 HTML。
# 每一項都另外要求錯誤訊息帶得出行號（「第 N 行」），Lena 才知道去改哪裡。
NEG = [
    # ---- 事件線 icon ／ sig mark 這條線（5 條）----
    ("vlines 的 icon 打錯", "charts-demo-6",
     [("  - {at: 2026-05-23, label: 跌點 1, color: red, icon: warn}",
       "  - {at: 2026-05-23, label: 跌點 1, color: red, icon: danger}")],
     "vlines 的 icon 只能是 warn"),
    ("vlines 的 color 打錯（v1.4 既有守門，順便回歸）", "charts-demo-6",
     [("  - {at: 2026-05-23, label: 跌點 1, color: red, icon: warn}",
       "  - {at: 2026-05-23, label: 跌點 1, color: green, icon: warn}")],
     "vlines 的 color 只能是 red／ink"),
    ("sig 的 mark 打錯", "charts-demo-6",
     [("  mark: max", "  mark: 最大")],
     "sig 的 mark 只能是 both"),
    ("sig 的 mark: max 但配對的格子不是數字", "charts-demo-6",
     [("每日開局數,3.42,3.05,{{d:-0.37:局}},0.004",
       "每日開局數,N/A,3.05,{{d:-0.37:局}},0.004")],
     "讀不出數字，沒辦法比大小"),
    ("sig 的 a 與 b 指到同一格（v1.5 既有守門，順便回歸）", "charts-demo-6",
     [("    - {row: 1, a: 2, b: 3}", "    - {row: 1, a: 2, b: 2}")],
     "a 與 b 是同一格"),
    # ---- 底色深淺分級這條線（13 條）----
    ("強度值給負數", "sig-shade-demo",
     [("    - {row: 1, a: 2, b: 3, v: 5.91}", "    - {row: 1, a: 2, b: 3, v: -5.91}")],
     "第 1 項的 v 是負的"),
    ("強度值非數字", "sig-shade-demo",
     [("    - {row: 2, a: 2, b: 3, v: 3.04}", "    - {row: 2, a: 2, b: 3, v: 很顯著}")],
     "`v` 要是數字"),
    ("階數超界（三個切點）", "sig-shade-demo",
     [("  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1",
       "  levels: [1.96, 2.58, 3.29]\n  pairs:\n    - {row: 1")],
     "levels 要剛好兩個切點（三階），現在有 3 個"),
    ("只有一個切點", "sig-shade-demo",
     [("  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1",
       "  levels: [2.58]\n  pairs:\n    - {row: 1")],
     "levels 要剛好兩個切點（三階），現在有 1 個"),
    ("切點沒有由小到大", "sig-shade-demo",
     [("  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1",
       "  levels: [3.29, 2.58]\n  pairs:\n    - {row: 1")],
     "levels 要由小到大且不相等"),
    ("切點是負數", "sig-shade-demo",
     [("  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1",
       "  levels: [-1, 3.29]\n  pairs:\n    - {row: 1")],
     "levels 第 1 個 -1 是負的"),
    ("切點非數字", "sig-shade-demo",
     [("  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1",
       "  levels: [p<.01, 3.29]\n  pairs:\n    - {row: 1")],
     "levels 第 1 個 'p<.01' 不是數字"),
    ("有 v 卻沒寫 scale", "sig-shade-demo",
     [('  scale: "|t|"\n  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1',
       "  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1")],
     "sig 缺 `scale`"),
    ("有 v 卻沒寫 levels", "sig-shade-demo",
     [('  scale: "|t|"\n  levels: [2.58, 3.29]\n  pairs:\n    - {row: 1',
       '  scale: "|t|"\n  pairs:\n    - {row: 1')],
     "sig 缺 `levels`"),
    ("只有一部分 pair 帶 v", "sig-shade-demo",
     [("    - {row: 3, a: 2, b: 3, v: 2.12}", "    - {row: 3, a: 2, b: 3}")],
     "第 3 項缺 `v`"),
    ("沒有 v 卻寫了 levels", "sig-shade-demo",
     [('sig:\n  dir: tb\n  scale: "|t|"\n  levels: [2.58, 3.29]\n  pairs:\n'
       "    - {col: 4, a: 3, b: 4, v: 3.12}\n    - {col: 4, a: 5, b: 6, v: 6.41}",
       "sig:\n  dir: tb\n  levels: [2.58, 3.29]\n  pairs:\n"
       "    - {col: 4, a: 3, b: 4}\n    - {col: 4, a: 5, b: 6}")],
     "pairs 都沒有寫 `v`（檢定強度），就不用寫 `levels`"),
    ("備註超過四列（defs 多寫 母體）", "sig-shade-demo",
     [("  著色: 階界 2.58／3.29 ＝大樣本下的 p<.01／p<.001；沒上底色＝未達 p<.05（每局手數 |t| 0.84）",
       "  著色: 階界 2.58／3.29 ＝大樣本下的 p<.01／p<.001；沒上底色＝未達 p<.05（每局手數 |t| 0.84）\n"
       "  母體: 全站活躍玩家，前 31 天／後 30 天")],
     "defs 多了 `母體`——備註只能四列"),
    ("備註多寫一列 口徑", "sig-shade-demo",
     [("  維度: 三個底台（盲注級距）× 前段／後段；同一底台的兩列合併成一群",
       "  維度: 三個底台（盲注級距）× 前段／後段；同一底台的兩列合併成一群\n"
       "  口徑: 斷點當日不計入兩段")],
     "defs 多了 `口徑`——備註只能四列"),
    # ---- 兩條線併用（1 條，v1.6 合併時新增）----
    ("mark: max ＋ v 併用，但某一格不是數字", "charts-demo-6",
     [COMBO, ("平均遊戲時間,43.8,39.1,{{d:-4.7:分}},<0.001@@0.0005",
              "平均遊戲時間,—,39.1,{{d:-4.7:分}},<0.001@@0.0005")],
     "讀不出數字，沒辦法比大小"),
    # ---- v1.7：圖例搬家／結論條列（3 條）----
    ("legend 的值打錯", "charts-demo-7",
     [("height: 446\nlegend: bottom", "height: 446\nlegend: 下方")],
     "legend 只能是 right（右側直接標註）或 bottom"),
    ("conclusion_style 的值打錯", "charts-demo-7",
     [("appendix: false\nconclusion_style: list",
       "appendix: false\nconclusion_style: 條列")],
     "檔頭 `conclusion_style` 只能是 card（條狀卡片）、list（純條列）或 numbered"),
    ("條列模式第一條就是 ◦ 子項（上面沒有主條目）", "charts-demo-7",
     [("- [dn] 兩個跌點各掉一階", "　◦ 兩個跌點各掉一階")],
     "的第一條就是 `◦` 子項，上面沒有可以掛的主條目"),
    # ---- v1.8：事件標籤第二行 ＋ 備註列數放寬（5 條）----
    ("vlines 寫了 label2 卻沒有 label", "charts-demo-7",
     [("  - {at: 2026-05-13, label: 活動開始}",
       "  - {at: 2026-05-13, label2: 活動開始}")],
     "寫了 label2 卻沒有 label"),
    ("defs 整個空的（一列都沒寫）", "charts-demo-7",
     [("defs:\n  維度: 日（2026-05-03 ~ 07-01，60 個日值）× 兩條序列\n"
       "  指標: DAU（人）；7 日移動平均為尾端視窗，前 6 天用已有天數\n"
       "  著色: 深藍實線＝DAU、虛線＝7 日移動平均；紅色虛線＋三角驚嘆號＝跌點；墨色虛線＝一般事件\n",
       "defs: {}\n")],
     "defs 是空的——備註至少要留一列"),
    ("defs 的順序不是 維度 → 指標 → 著色", "sig-shade-demo",
     [("  維度: 三個底台（盲注級距）× 前段／後段；同一底台的兩列合併成一群\n"
       "  指標: 平均遊戲時間（分）＝該段每日平均；變化＝後段減前段",
       "  指標: 平均遊戲時間（分）＝該段每日平均；變化＝後段減前段\n"
       "  維度: 三個底台（盲注級距）× 前段／後段；同一底台的兩列合併成一群")],
     "defs 的順序要照 維度 → 指標 → 著色"),
    ("defs 寫了 key 卻留空值", "charts-demo-6",
     [("  指標: DAU（人）；7 日移動平均為尾端視窗，前 6 天用已有天數",
       "  指標:")],
     "defs 的 `指標` 是空的"),
    ("defs 多了第四列（v1.6 既有守門，放寬後要繼續擋）", "charts-demo-7",
     [("  指標: 每天取一次分位、前後各 28 日均值（示意）",
       "  指標: 每天取一次分位、前後各 28 日均值（示意）\n"
       "  母體: 全站活躍玩家")],
     "defs 多了 `母體`——備註只能四列"),
    # ---- v1.9：欄位群直向粗框 ＋ 結論區三個開關 ＋ 必填放寬後仍要擋（7 條）----
    ("col_groups 加起來跟欄數對不上", "sig-shade-demo",
     [('columns: [指標, 上線前, 上線後, 變化, "|t|"]',
       'columns: [指標, 上線前, 上線後, 變化, "|t|"]\ncol_groups: [1, 2, 1]')],
     "col_groups 加起來是 4 欄，但 columns 有 5 欄"),
    ("col_groups 有 0（不是正整數）", "sig-shade-demo",
     [('columns: [指標, 上線前, 上線後, 變化, "|t|"]',
       'columns: [指標, 上線前, 上線後, 變化, "|t|"]\ncol_groups: [1, 0, 2, 2]')],
     "col_groups 的 0 不是正整數"),
    ("col_groups 只寫一群（一條粗框都畫不出來）", "sig-shade-demo",
     [('columns: [指標, 上線前, 上線後, 變化, "|t|"]',
       'columns: [指標, 上線前, 上線後, 變化, "|t|"]\ncol_groups: [5]')],
     "col_groups 只寫了一群＝一條粗框都畫不出來"),
    ("conclusion_box: true 卻沒有 conclusion_style（＝卡片）", "charts-demo-7",
     [("appendix: false\nconclusion_style: list",
       "appendix: false\nconclusion_box: true")],
     "`conclusion_box: true` 要配 conclusion_style: list 或 numbered"),
    ("conclusion_lead 不是 true／false", "charts-demo-7",
     [("appendix: false\nconclusion_style: list",
       "appendix: false\nconclusion_lead: 不要\nconclusion_style: list")],
     "檔頭 `conclusion_lead` 要是 true／false"),
    ("conclusion_badge 不是 true／false", "charts-demo-7",
     [("appendix: false\nconclusion_style: list",
       "appendix: false\nconclusion_badge: 拿掉\nconclusion_style: list")],
     "檔頭 `conclusion_badge` 要是 true／false"),
    ("note_extra 寫了卻是空的（母體註腳放寬之後的新守門）", "sig-shade-demo",
     [("note_extra: 檢定：Welch t（雙尾），|t| 為示意值、未實跑\n", "note_extra:\n")],
     "`note_extra` 寫了卻是空的"),
    ("subtitle 放寬成選填之後，型別還是要擋（寫成清單）", "charts-demo-7",
     [("subtitle: xy 圖的 legend: bottom 與檔頭的 conclusion_style: list，兩項都是宣告才生效",
       "subtitle:\n  - xy 圖的 legend\n  - 結論改條列")],
     "檔頭欄位 `subtitle` 要是一段文字"),
    # ---- v1.11 重點紅字放寬之後的守門（3 條）：放寬上限不等於拿掉上限 ----
    ("同一段紅字超過上限（4 處 > HL_MAX 3）", "sig-shade-demo",
     [("- !!全部數字都是示意假資料!!，不是任何真實遊戲的輸出，不可引用、不可做決定。",
       "- !!全部數字都是示意假資料!!，!!不是任何真實遊戲的輸出!!，!!不可引用!!、!!不可做決定!!。")],
     "同一段最多 3 處重點紅字（這一段有 4 處）"),
    ("!! 沒有成對（v1.10 既有守門，放寬之後要保留）", "sig-shade-demo",
     [("- !!全部數字都是示意假資料!!，不是任何真實遊戲的輸出，不可引用、不可做決定。",
       "- !!全部數字都是示意假資料!!，!!不是任何真實遊戲的輸出，不可引用、不可做決定。")],
     "!! 沒有成對"),
    ("!! 配對不出來（!!!! 這種畸形，成對檢查過得了但渲染不是寫的人想的）", "sig-shade-demo",
     [("- !!全部數字都是示意假資料!!，不是任何真實遊戲的輸出，不可引用、不可做決定。",
       "- !!!!全部數字都是示意假資料，不是任何真實遊戲的輸出，不可引用、不可做決定。")],
     "!! 配對不出來"),
]


def _md5(path):
    return hashlib.md5(io.open(path, "rb").read()).hexdigest()


def _build(md, out):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "build.py"),
                           "--md", md, "--out", out],
                          capture_output=True, text=True)


def _only_html(d):
    hs = [f for f in os.listdir(d) if f.endswith(".html")]
    return os.path.join(d, hs[0]) if hs else None


def _qa(html):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "qa_html.py"), html],
                          capture_output=True, text=True)


def _edit(work, pairs, fails, title):
    """把 (old, new) 逐對套進樣張目錄底下所有 .md／.csv；每一對都要剛好命中一次。"""
    for old, new in pairs:
        hit = 0
        for root, _dirs, files in os.walk(work):
            for fn in files:
                if not fn.endswith((".md", ".csv")):
                    continue
                p = os.path.join(root, fn)
                t = io.open(p, encoding="utf-8").read()
                if old in t:
                    hit += t.count(old)
                    io.open(p, "w", encoding="utf-8").write(t.replace(old, new, 1))
        if hit != 1:
            fails.append(f"{title}: 要改的那一段命中 {hit} 次（應為 1）：{old[:40]!r}")
            return False
    return True


def resolved_colors(html_text):
    """把 <style> 的規則跟每個 SVG 元素跑一次串接，回傳
    [(tag, class, 屬性, 最終生效值, 來源, 有沒有寫 presentation attribute)]；
    來源 ∈ inline／css／presentation／initial。

    這一段刻意**不看原始碼寫了什麼屬性**——v1.4~v1.7 的紅色 bug 就是
    「屬性明明寫了 stroke=#c62828，瀏覽器卻照 CSS 畫成灰」，只驗屬性存在會漏掉。
    """
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html_text, re.S))
    rules, _media = cssres.parse_css(css)
    out = []
    for sm in re.finditer(r"<svg\b.*?</svg>", html_text, re.S):
        try:
            root = ET.fromstring(sm.group(0))
        except ET.ParseError:
            out.append(("(parse-error)", "", "", "", "error", False))
            continue

        def walk(el, chain):
            tag = el.tag.split("}")[-1]
            cls = set((el.get("class") or "").split())
            ch = chain + [(tag, cls, set(el.attrib.keys()))]
            inl = {}
            for d in (el.get("style") or "").split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    inl[k.strip()] = v.strip()
            for prop in ("fill", "stroke"):
                pres, ist = el.get(prop), inl.get(prop)
                # 事件線與它的標籤一律算（就算沒寫任何顏色屬性也要算出「灰」），
                # 其餘元素只在寫了顏色時才算。
                if pres is None and ist is None and not (cls & WATCH):
                    continue
                src, val, _sel = cssres.winner(rules, ch, prop, pres, ist)
                out.append((tag, " ".join(sorted(cls)), prop, val, src, pres is not None))
            for c in el:
                walk(c, ch)
        walk(root, [])
    return out


def check_colors(name, html_text, want_red_lines, want_red_labels, fails):
    """① 沒有任何 presentation attribute 被 CSS 蓋掉
       ② 跌點線／跌點標籤的**最終生效顏色**是 #c62828（而且是 inline 來源）"""
    res = resolved_colors(html_text)
    shadowed = [r for r in res if r[4] == "css" and r[5]]
    ok = not shadowed
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} 零處 presentation attribute 被 CSS 蓋掉")
    if not ok:
        fails.append(f"{name}: {len(shadowed)} 處顏色屬性被 CSS 蓋掉 → {shadowed[:4]}")
    lines = [r for r in res if r[0] == "line" and "bkline" in r[1] and r[2] == "stroke"]
    labs = [r for r in res if r[0] == "text" and "bkl" in r[1] and r[2] == "fill"]
    red_l = [r for r in lines if r[3] == RED and r[4] == "inline"]
    red_t = [r for r in labs if r[3] == RED and r[4] == "inline"]
    ok = len(red_l) == want_red_lines and len(red_t) == want_red_labels
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} 跌點線最終生效 {RED} ×{len(red_l)}"
          f"（要 {want_red_lines}）／標籤 ×{len(red_t)}（要 {want_red_labels}）")
    if not ok:
        fails.append(f"{name}: 紅線 {len(red_l)}/{want_red_lines}、紅標籤 "
                     f"{len(red_t)}/{want_red_labels}；實際 {lines + labs}")
    # 其餘事件線必須仍是 CSS 的墨色（不能一修就整排變紅）
    rest = [r for r in lines + labs if r[3] != RED]
    bad = [r for r in rest if not (r[4] == "css" and "--ink2" in r[3])]
    ok = not bad
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} 其餘事件線／標籤 {len(rest)} 個"
          f"維持 CSS 墨色 var(--ink2)")
    if not ok:
        fails.append(f"{name}: 非跌點的事件線顏色不對 → {bad[:4]}")
    return res


def main():
    tmp = tempfile.mkdtemp(prefix="rhtmlb-test-")
    fails = []

    print("=== A 回歸：八個樣張的 HTML md5 要逐 byte 相同 ===")
    for name, want in BASELINE.items():
        md = os.path.join(ROOT, "examples", name, "報告內容.md")
        od = os.path.join(tmp, name)
        r = _build(md, od)
        if r.returncode != 0:
            fails.append(f"{name}: build 失敗\n{r.stdout}{r.stderr}")
            print(f"  [FAIL] {name:<16} build 失敗")
            continue
        got = _md5(_only_html(od))
        ok = got == want
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} {got}"
              + ("" if ok else f"  ≠ {want}"))
        if not ok:
            fails.append(f"{name}: md5 {got} ≠ 定版 {want}（預設行為被改掉了）")

    print("=== A 回歸：JS／CSS 逐字元不變、themes.py 檔案零變動 ===")
    any_html = None
    for name in BASELINE:
        od = os.path.join(tmp, name)
        if os.path.isdir(od) and _only_html(od):
            any_html = _only_html(od)
            break
    if any_html:
        h = io.open(any_html, encoding="utf-8").read()
        js = re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)
        cs = re.findall(r"<style[^>]*>(.*?)</style>", h, re.S)
        for what, blocks, want in (("JS ", js, JS_MD5), ("CSS", cs, CSS_MD5)):
            got = hashlib.md5(blocks[0].encode("utf-8")).hexdigest() if blocks else "（找不到）"
            ok = got == want
            print(f"  [{'OK  ' if ok else 'FAIL'}] {what}              {got}")
            if not ok:
                fails.append(f"{what} md5 {got} ≠ 定版 {want}")
    got = _md5(os.path.join(SCRIPTS, "themes.py"))
    ok = got == THEMES_MD5
    print(f"  [{'OK  ' if ok else 'FAIL'}] themes.py       {got}")
    if not ok:
        fails.append(f"themes.py md5 {got} ≠ {THEMES_MD5}（v1.6 不該動這個檔）")

    print(f"=== A 回歸：兩個 v1.6 新樣張 build ＋ qa {QA_ITEMS} 項全綠 ===")
    newdemo = {}
    for name in ("charts-demo-6", "sig-shade-demo"):
        md = os.path.join(ROOT, "examples", name, "報告內容.md")
        od = os.path.join(tmp, name)
        r = _build(md, od)
        if r.returncode != 0:
            fails.append(f"{name} build 失敗\n{r.stdout}{r.stderr}")
            print(f"  [FAIL] {name:<16} build")
            continue
        html = _only_html(od)
        newdemo[name] = io.open(html, encoding="utf-8").read()
        q = _qa(html)
        nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
        ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} build ＋ qa {nitem} 項全綠")
        if not ok:
            fails.append(f"{name} qa 沒有全綠或項數不是 {QA_ITEMS}（{nitem}）\n" + q.stdout)

    body = newdemo.get("charts-demo-6", "")
    n_icon = body.count('d="M12 2.6 23 21.4H1z"')
    n_sig = body.count('data-sig="1"')
    n_lv = body.count("data-sig-lv=")
    ok = n_icon == 3 and n_sig == 3 and n_lv == 0
    print(f"  [{'OK  ' if ok else 'FAIL'}] charts-demo-6    圖內 warn icon 2 ＋正文 1 ＝{n_icon}；"
          f"顯著格 {n_sig}（3 組各只標 1 格）；沒有深淺階 {n_lv}")
    if not ok:
        fails.append(f"charts-demo-6 icon={n_icon}（要 3）／sig={n_sig}（要 3）／lv={n_lv}（要 0）")

    body = newdemo.get("sig-shade-demo", "")
    lv = [body.count('data-sig-lv="%d"' % i) for i in (1, 2, 3)]
    ncell = body.count('data-sig="1"')
    # 兩張表共 5 組配對 × 每組 2 格（沒宣告 mark ＝兩格都標）＝10 格；
    # 強度值 5.91/3.04/2.12（lr 表）與 3.12/6.41（tb 表）→ 第 1 階 2 格、第 2 階 4 格、第 3 階 4 格
    ok = lv == [2, 4, 4] and ncell == 10 and "此格為" not in body
    print(f"  [{'OK  ' if ok else 'FAIL'}] sig-shade-demo   三階格數 第1階{lv[0]}／第2階{lv[1]}／第3階{lv[2]}"
          f"；沒宣告 mark 時兩格都標（共 {ncell} 格）")
    if not ok:
        fails.append(f"sig-shade-demo 三階分布 {lv}（要 [2,4,4]）／sig 格 {ncell}（要 10）")

    print("=== B 組合：mark: max（標哪一格）＋ v／levels（多深）要能併用 ===")
    work = os.path.join(tmp, "combo")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-6"), work)
    if _edit(work, [COMBO], fails, "併用組合"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("併用組合 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] build")
        else:
            h = io.open(_only_html(od), encoding="utf-8").read()
            cells = re.findall(r'data-sig="1"(?: data-sig-lv="(\d)")?[^>]*?title="([^"]*)"', h)
            lvs = [c[0] for c in cells]
            # 3 組配對各只標 1 格（mark: max），三格的深淺分別是 3／1／2（依 v）
            ok1 = lvs == ["3", "1", "2"]
            print(f"  [{'OK  ' if ok1 else 'FAIL'}] 只標較大格 {len(cells)} 個、深淺依 v＝{lvs}（要 ['3','1','2']）")
            if not ok1:
                fails.append(f"併用：格數/階數 {lvs} ≠ ['3','1','2']")
            # tooltip 要兩件事都講到，而且不重複「經統計檢定有顯著差異」
            tip = cells[0][1] if cells else ""
            ok2 = ("配對中數值較大的一格" in tip and "第 3 階／共 3 階" in tip
                   and tip.count("經統計檢定有顯著差異") == 1)
            print(f"  [{'OK  ' if ok2 else 'FAIL'}] tooltip 同時講「哪一格」與「多深」且不重複")
            if not ok2:
                fails.append("併用 tooltip 不對：" + tip)
            # 引擎自動補的備註句：mark 那句 ＋ 深淺那句，接在一起、不互相蓋掉
            note = [re.sub(r"<[^>]+>", "", m) for m in
                    re.findall(r'<p class="blk-note">(.*?)</p>', h, re.S) if "底色" in m]
            n = note[0] if note else ""
            ok3 = ("配對中只標數值較大的一格" in n and "底色深淺＝|t|" in n
                   and n.count("底色著色為經統計檢定有顯著差異") == 1
                   and "方向為左右著色" not in n)
            print(f"  [{'OK  ' if ok3 else 'FAIL'}] 備註句 mark ＋ 深淺兩句疊加、沒有重複或矛盾")
            if not ok3:
                fails.append("併用備註句不對：" + n)

    print(f"=== C 負向（{len(NEG)} 條）：宣告寫錯要報對的錯 ＋ 行號 ＋ exit 1 ＋ 不產 HTML ===")
    for i, (title, ex, pairs, want) in enumerate(NEG, 1):
        work = os.path.join(tmp, "neg", str(i))
        shutil.copytree(os.path.join(ROOT, "examples", ex), work)
        if not _edit(work, pairs, fails, title):
            print(f"  [FAIL] {i:2d} {title} — 找不到要改的那一段")
            continue
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        msg = r.stdout + r.stderr
        wrote = os.path.isdir(od) and any(f.endswith(".html") for f in os.listdir(od))
        lined = bool(re.search(r"第 \d+ 行", msg))
        ok = r.returncode == 1 and want in msg and lined and not wrote
        print(f"  [{'OK  ' if ok else 'FAIL'}] {i:2d} {title}")
        if not ok:
            fails.append(f"{title}: exit={r.returncode} 產檔={wrote} 有行號={lined} "
                         f"訊息含 {want!r}={want in msg}\n{msg[:600]}")

    print("=== D v1.7：圖例搬到 x 軸下方／結論改純條列（宣告才生效）===")
    d7 = os.path.join(ROOT, "examples", "charts-demo-7")
    od = os.path.join(tmp, "charts-demo-7")
    r = _build(os.path.join(d7, "報告內容.md"), od)
    body7 = ""
    if r.returncode != 0:
        fails.append("charts-demo-7 build 失敗\n" + r.stdout + r.stderr)
        print("  [FAIL] charts-demo-7    build")
    else:
        html = _only_html(od)
        body7 = io.open(html, encoding="utf-8").read()
        q = _qa(html)
        nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
        ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
        print(f"  [{'OK  ' if ok else 'FAIL'}] charts-demo-7    build ＋ qa {nitem} 項全綠")
        if not ok:
            fails.append(f"charts-demo-7 qa 沒有全綠或項數不是 {QA_ITEMS}（{nitem}）\n" + q.stdout)

    def _legend_at(body):
        """回傳 (圖例文字座標清單, 繪圖區右緣 x, 繪圖區底緣 y)。"""
        svg = re.search(r'<svg class="chart" data-kind="xy".*?</svg>', body, re.S)
        if not svg:
            return [], None, None
        svg = svg.group(0)
        ax = re.search(r'<line class="axis" x1="([\d.]+)" y1="([\d.]+)" '
                       r'x2="([\d.]+)"', svg)
        lg = [(float(a), float(b)) for a, b in
              re.findall(r'<text class="vl lgt" x="([\d.]+)" y="([\d.]+)"', svg)]
        return lg, float(ax.group(3)), float(ax.group(2))

    lg, px_r, py_b = _legend_at(body7)
    ok = bool(lg) and all(x < px_r and y > py_b for x, y in lg)
    print(f"  [{'OK  ' if ok else 'FAIL'}] legend: bottom   {len(lg)} 個圖例都在 x 軸下方"
          f"（x < {px_r}、y > {py_b}）")
    if not ok:
        fails.append(f"legend: bottom 的圖例座標不對：{lg}（繪圖區右緣 {px_r}／底緣 {py_b}）")

    # 事件線的 warn icon 與標籤仍掛在繪圖區底緣（不受下邊界加高影響）
    warn_y = [float(y) for y in
              re.findall(r'<text class="an bkl" x="[\d.]+" y="([\d.]+)"'
                         r' style="fill:#c62828"', body7)]
    ok = len(warn_y) == 2 and all(y < py_b for y in warn_y)
    print(f"  [{'OK  ' if ok else 'FAIL'}] 事件標籤在繪圖區內  {warn_y}（要全部 < {py_b}）")
    if not ok:
        fails.append(f"事件標籤掉出繪圖區：{warn_y}（底緣 {py_b}）")

    n_sub = body7.count('<ul class="bul concl-sub">')
    n_list = body7.count('<ul class="bul concl-list">')
    n_card = body7.count('<ol class="concl">')
    ok = n_list == 1 and n_card == 0 and n_sub == 1
    print(f"  [{'OK  ' if ok else 'FAIL'}] conclusion_style: list  條列 {n_list}／"
          f"卡片 {n_card}／有子項的條目 {n_sub}")
    if not ok:
        fails.append(f"結論條列模式不對：list={n_list}／card={n_card}／sub={n_sub}")

    # 不宣告就回到 v1.6 的樣子：圖例回右側、結論回條狀卡片、◦ 子項併回同一段
    for title, pairs, check in (
            ("拿掉 legend: bottom → 圖例回右側", [("legend: bottom\n", "")], "legend"),
            ("拿掉 conclusion_style: list → 結論回條狀卡片",
             [("conclusion_style: list\n", "")], "concl")):
        work = os.path.join(tmp, "d7-" + check)
        shutil.copytree(d7, work)
        if not _edit(work, pairs, fails, title):
            print(f"  [FAIL] {title} — 找不到要改的那一段")
            continue
        o2 = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), o2)
        if r.returncode != 0:
            fails.append(f"{title}：build 失敗\n" + r.stdout + r.stderr)
            print(f"  [FAIL] {title}")
            continue
        b2 = io.open(_only_html(o2), encoding="utf-8").read()
        if check == "legend":
            lg2, r2, _b2 = _legend_at(b2)
            ok = bool(lg2) and all(x > r2 for x, _y in lg2)
            note = f"圖例 x＝{[x for x, _ in lg2]}（要全部 > 繪圖區右緣 {r2}）"
        else:
            ok = (b2.count('<ol class="concl">') == 1
                  and b2.count('<ul class="bul concl-list">') == 0
                  and b2.count('<ul class="bul concl-sub">') == 0
                  and "◦ 事件線的三角驚嘆號" in b2)
            note = ("結論回到 <ol class=\"concl\"> 卡片、◦ 子項併回同一段"
                    if ok else "沒有回到 v1.6 的卡片樣子")
        print(f"  [{'OK  ' if ok else 'FAIL'}] {title}：{note}")
        if not ok:
            fails.append(f"{title} 不成立：{note}")

    print("=== E v1.8-1：顏色 bug 修掉了沒（算最終生效色，不看原始碼有沒有屬性）===")
    colorsets = {"charts-demo-4": (1, 1), "charts-demo-6": (2, 2), "charts-demo-7": (2, 2)}
    for name, (nl, nt) in colorsets.items():
        od = os.path.join(tmp, name)
        if not (os.path.isdir(od) and _only_html(od)):
            od = os.path.join(tmp, "e-" + name)
            r = _build(os.path.join(ROOT, "examples", name, "報告內容.md"), od)
            if r.returncode != 0:
                fails.append(f"{name} build 失敗（E 段）\n{r.stdout}{r.stderr}")
                print(f"  [FAIL] {name:<16} build")
                continue
        check_colors(name, io.open(_only_html(od), encoding="utf-8").read(), nl, nt, fails)
    # 沒有 vlines 的樣張：整份文件也不准有被蓋掉的顏色屬性
    for name in ("playtime-demo", "charts-demo", "charts-demo-2", "charts-demo-3",
                 "charts-demo-5", "sig-shade-demo"):
        od = os.path.join(tmp, name)
        h = io.open(_only_html(od), encoding="utf-8").read()
        sh = [r for r in resolved_colors(h) if r[4] == "css" and r[5]]
        ok = not sh
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} 零處顏色屬性被 CSS 蓋掉")
        if not ok:
            fails.append(f"{name}: {len(sh)} 處顏色屬性被 CSS 蓋掉 → {sh[:4]}")
    # 顏色修正之後三個樣張的 md5 會變，但變動內容必須剛好是那兩種替換
    for name, (old_md5, npair) in COLORFIX.items():
        od = os.path.join(tmp, name)
        if not (os.path.isdir(od) and _only_html(od)):
            od = os.path.join(tmp, "e-" + name)
        h = io.open(_only_html(od), encoding="utf-8").read()
        back = h.replace(' style="stroke:#c62828"', ' stroke="#c62828"')
        back = back.replace(' style="fill:#c62828"', ' fill="#c62828"')
        got = hashlib.md5(back.encode("utf-8")).hexdigest()
        n1 = h.count(' style="stroke:#c62828"')
        n2 = h.count(' style="fill:#c62828"')
        ok = got == old_md5 and n1 == npair and n2 == npair
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name:<16} 把 inline style 換回舊寫法就回到 v1.7 的 md5"
              f"（{npair} 線 ＋ {npair} 標籤）")
        if not ok:
            fails.append(f"{name}: 還原後 md5 {got} ≠ v1.7 {old_md5}"
                         f"（style stroke {n1}／fill {n2}，要各 {npair}）"
                         "——表示這次改動不只顏色那兩處")

    print("=== E v1.8-2：事件標籤第二行 label2（宣告才生效）===")
    work = os.path.join(tmp, "label2")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    pairs = [("  - {at: 2026-05-13, label: 活動開始}",
              "  - {at: 2026-05-13, label: 5/13, label2: 活動開始}"),
             ("  - {at: 2026-05-23, label: 跌點 1, color: red, icon: warn}",
              "  - {at: 2026-05-23, label: 5/23, label2: 跌點 1, color: red, icon: warn}")]
    if _edit(work, pairs, fails, "label2"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("label2 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] label2 build")
        else:
            h = io.open(_only_html(od), encoding="utf-8").read()
            svg = re.search(r'<svg class="chart" data-kind="xy".*?</svg>', h, re.S).group(0)
            lab = re.findall(r'<text class="an bkl" x="([\d.]+)" y="([\d.]+)"'
                             r'(?: style="fill:(#\w+)")?>([^<]*)</text>', svg)
            ink2 = [t for t in lab if t[3] in ("5/13", "活動開始")]
            red2 = [t for t in lab if t[3] in ("5/23", "跌點 1")]
            ok = (len(ink2) == 2 and ink2[0][0] == ink2[1][0]
                  and abs(float(ink2[1][1]) - float(ink2[0][1]) - 17.0) < 1e-6
                  and ink2[0][3] == "5/13" and ink2[1][3] == "活動開始")
            print(f"  [{'OK  ' if ok else 'FAIL'}] 墨色事件線兩行：同 x、差一個行高 17px、"
                  f"第一行日期第二行事件名 → {[(t[1], t[3]) for t in ink2]}")
            if not ok:
                fails.append(f"label2 墨色兩行不對：{ink2}")
            ok = (len(red2) == 2 and red2[0][0] == red2[1][0]
                  and abs(float(red2[1][1]) - float(red2[0][1]) - 17.0) < 1e-6
                  and all(t[2] == "#c62828" for t in red2))
            print(f"  [{'OK  ' if ok else 'FAIL'}] 紅色跌點線兩行：兩行都帶 inline "
                  f"style fill:#c62828 → {[(t[1], t[2], t[3]) for t in red2]}")
            if not ok:
                fails.append(f"label2 紅色兩行不對：{red2}")
            # 兩行的下緣仍在繪圖區內
            ax = re.search(r'<line class="axis" x1="[\d.]+" y1="([\d.]+)"', svg)
            py_b = float(ax.group(1))
            ok = all(float(t[1]) < py_b for t in red2 + ink2)
            print(f"  [{'OK  ' if ok else 'FAIL'}] 兩行標籤都還在繪圖區內（y < {py_b}）")
            if not ok:
                fails.append("label2 兩行標籤掉出繪圖區")
            # 跌點 1 拆成兩行（2 個紅標籤）＋ 跌點 2 仍一行（1 個）＝ 3
            check_colors("label2-demo", h, 2, 3, fails)

    print("=== E v1.8-2b：結論改編號條列 conclusion_style: numbered ===")
    work = os.path.join(tmp, "numbered")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    if _edit(work, [("appendix: false\nconclusion_style: list",
                     "appendix: false\nconclusion_style: numbered")],
             fails, "numbered"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("numbered build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] numbered build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            n_ol = h.count('<ol class="bul concl-list">')
            n_ul = h.count('<ul class="bul concl-list">')
            n_card = h.count('<ol class="concl">')
            n_sub = h.count('<ul class="bul concl-sub" style="list-style-type:circle">')
            ok = n_ol == 1 and n_ul == 0 and n_card == 0 and n_sub == 1
            print(f"  [{'OK  ' if ok else 'FAIL'}] 外層變 <ol>（{n_ol}）、沒有 <ul> 條列（{n_ul}）"
                  f"與卡片（{n_card}）；子項用 inline list-style-type:circle 釘住 ◦（{n_sub}）")
            if not ok:
                fails.append(f"numbered 結構不對：ol={n_ol}／ul={n_ul}／card={n_card}／sub={n_sub}")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] numbered 之後 qa {nitem} 項仍全綠")
            if not ok:
                fails.append("numbered qa 沒全綠\n" + q.stdout)
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", h, re.S))
            got = hashlib.md5(css.encode("utf-8")).hexdigest()
            ok = got == CSS_MD5
            print(f"  [{'OK  ' if ok else 'FAIL'}] CSS 沒有為了編號而改動（{got}）")
            if not ok:
                fails.append(f"numbered 動到 CSS：{got} ≠ {CSS_MD5}")
            # 條列的文字與 v1.7 的 list 模式一字不差，只有外層標籤換掉
            b7 = io.open(_only_html(os.path.join(tmp, "charts-demo-7")),
                         encoding="utf-8").read()
            back = h.replace('<ol class="bul concl-list">', '<ul class="bul concl-list">')
            back = back.replace('<ul class="bul concl-sub" style="list-style-type:circle">',
                                '<ul class="bul concl-sub">')
            # </ol> 只有結論那一個會被換回 </ul>：用結論區段比對
            seg = lambda t: re.search(r'id="sec-concl".*?</section>', t, re.S).group(0)
            ok = seg(back).replace("</ol>", "</ul>") == seg(b7)
            print(f"  [{'OK  ' if ok else 'FAIL'}] 換回 list 的標籤之後結論區段與 v1.7 逐字相同"
                  f"（文字沒被動到）")
            if not ok:
                fails.append("numbered 除了外層標籤以外還改到別的東西")

    print("=== E v1.8-3：備註放寬成 1~3 列（維度／指標／著色 挑著寫）===")
    work = os.path.join(tmp, "defs2")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    pairs = [("  維度: 日（2026-05-03 ~ 07-01，60 個日值）× 兩條序列\n", ""),
             ("  維度: 類別 × 指標（前／後各一列）× 五個分位，每個指標的兩列合併成一群\n"
              "  指標: 每天取一次分位、前後各 28 日均值（示意）\n", "")]
    if _edit(work, pairs, fails, "defs 1~3 列"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("defs 放寬 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] defs 放寬 build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] 少寫 defs 之後 build ＋ qa {nitem} 項仍全綠")
            if not ok:
                fails.append("defs 放寬後 qa 沒全綠\n" + q.stdout)
            blocks = re.split(r'<(?:figure|div) class="blk (?:fig|tbl)" id="([^"]+)"', h)[1:]
            got = {}
            for k, chunk in zip(blocks[0::2], blocks[1::2]):
                got[k] = re.findall(r'<div class="def-r"><dt>([^<]*)</dt>', chunk)
            ok = (got.get("fig-dau_ev") == ["指標", "著色"]
                  and got.get("tbl-quant_tb") == ["著色"])
            print(f"  [{'OK  ' if ok else 'FAIL'}] 備註列數跟著少：圖1-1 {got.get('fig-dau_ev')}／"
                  f"表1-1 {got.get('tbl-quant_tb')}")
            if not ok:
                fails.append(f"defs 放寬後的備註列不對：{got}")


    # ==================================================================== F v1.9
    print("=== F v1.9-1：subtitle／produced／note_base 改選填（沒寫＝整塊不渲染）===")
    base_md5 = BASELINE["sig-shade-demo"]
    drop3 = [("subtitle: 表格單格底色依檢定強度分三階，越深證據越強；備註固定四列\n", ""),
             ("produced: 2026-09-16\n", ""),
             ("note_base: 母體：示意假資料・全站活躍玩家（當日至少開一局）｜口徑："
              "前段 2026-05-01~05-31、後段 2026-06-02~07-01，斷點 6/1 當日不計入兩段｜"
              "n：前 31 天 648,213 人日／後 30 天 601,940 人日\n", ""),
             ]
    work = os.path.join(tmp, "fm-opt")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    h9 = ""
    if _edit(work, drop3, fails, "檔頭三欄改選填"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("三個檔頭欄位都不寫時 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] 三個欄位都不寫 build")
        else:
            html = _only_html(od)
            h9 = io.open(html, encoding="utf-8").read()
            # ① 副標整塊不渲染：沒有 <p class="subtitle">，也沒有留一行空白
            n_sub = h9.count('<p class="subtitle"')
            glued = re.search(r'</h1>\n      <p class="lede">', h9) is not None
            ok = n_sub == 0 and glued
            print(f"  [{'OK  ' if ok else 'FAIL'}] 沒寫 subtitle：<p class=\"subtitle\"> {n_sub} 個，"
                  f"h1 與 lede 直接相接（沒留空白行）＝{glued}")
            if not ok:
                fails.append(f"subtitle 沒寫時仍留下痕跡：p={n_sub}／相接={glued}")
            # ② 產出日期整項不渲染：資料說明列少一項，分隔線也跟著少一根
            dn_i, dn_sep = h9.count('class="dn-i"'), h9.count('class="dn-sep"')
            ok = dn_i == 3 and dn_sep == 2 and "產出日期" not in h9
            print(f"  [{'OK  ' if ok else 'FAIL'}] 沒寫 produced：資料說明 {dn_i} 項／"
                  f"分隔線 {dn_sep} 根（要 3／2，不留孤兒 ｜）")
            if not ok:
                fails.append(f"produced 沒寫時資料說明不對：dn-i={dn_i}／dn-sep={dn_sep}")
            # ③ 沒有 note_base 時，note_extra 前面不該掛一根孤兒 ｜
            notes = [re.sub(r"<[^>]+>", "", m).strip() for m in
                     re.findall(r'<p class="blk-note">(.*?)</p>', h9, re.S)]
            nblk = len(re.findall(
                r'<(?:figure|div) class="blk (?:fig|tbl)" id="', h9))
            bad = [n for n in notes if n.startswith("｜") or not n]
            ok = not bad and len(notes) == nblk == 2
            print(f"  [{'OK  ' if ok else 'FAIL'}] 沒寫 note_base：{nblk} 個區塊的 "
                  f"{len(notes)} 條備註都沒有空殼、也沒有開頭那根孤兒 ｜")
            if not ok:
                fails.append(f"note_base 沒寫時備註不對：{nblk} 區塊／{len(notes)} 條／壞的 {bad[:2]}")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] 三個欄位都不寫之後 qa {nitem} 項仍全綠")
            if not ok:
                fails.append("檔頭三欄不寫之後 qa 沒全綠\n" + q.stdout)
    # 連 note／note_extra 都沒有的區塊：母體註腳整塊不渲染（不是留一個空的 <p>）
    work = os.path.join(tmp, "nonote")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    if _edit(work, [("note_base: 母體：示意假資料｜口徑：示意｜n：示意\n", ""),
                    ("note_extra: 示意假資料；圖例位置由 legend: bottom 宣告，"
                     "height 比 v1.6 版多 46px 以補回圖例帶\n", "")],
             fails, "母體註腳整塊不渲染"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("完全沒有母體註腳時 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] 完全沒有母體註腳 build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            blocks = re.split(
                r'<(?:figure|div) class="blk (?:fig|tbl)" id="([^"]+)"', h)[1:]
            got = {k: c.count('<p class="blk-note">')
                   for k, c in zip(blocks[0::2], blocks[1::2])}
            empty = h.count('<p class="blk-note"></p>')
            ok = got == {"fig-dau_ev": 0, "tbl-quant_tb": 1} and empty == 0
            print(f"  [{'OK  ' if ok else 'FAIL'}] 圖 1-1 沒有母體註腳那一段就整塊不渲染"
                  f"（{got}）、零個空殼 <p class=\"blk-note\"></p>（{empty}）")
            if not ok:
                fails.append(f"母體註腳沒有整塊不渲染：{got}／空殼 {empty}")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] 母體註腳缺席之後 qa {nitem} 項仍全綠"
                  f"（第 17 項放寬成 0~1 列、另外擋空殼）")
            if not ok:
                fails.append("母體註腳缺席後 qa 沒全綠\n" + q.stdout)

    # 沒有 title 仍要擋（放寬的只有 subtitle／produced，不是整個檔頭）
    work = os.path.join(tmp, "fm-no-title")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    if _edit(work, [("title: 示意遊戲－檢定底色深淺三階樣張\n", "")],
             fails, "缺 title"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        wrote = os.path.isdir(od) and any(f.endswith(".html") for f in os.listdir(od))
        msg = r.stdout + r.stderr
        ok = r.returncode == 1 and "檔頭缺欄位：title" in msg and not wrote
        print(f"  [{'OK  ' if ok else 'FAIL'}] title 仍是必填：exit={r.returncode}／"
              f"報「檔頭缺欄位：title」／不產 HTML＝{not wrote}")
        if not ok:
            fails.append(f"缺 title 沒有被擋：exit={r.returncode} 產檔={wrote}\n{msg[:400]}")
    # 還原比對：三行寫回去就要逐 byte 回到 v1.8 的 md5
    restore3 = [("byline: 數據分析一組 | Lena\n",
                 "subtitle: 表格單格底色依檢定強度分三階，越深證據越強；備註固定四列\n"
                 "byline: 數據分析一組 | Lena\n"),
                ("disclaimer: 示意假資料・不可引用\n",
                 "produced: 2026-09-16\n"
                 "note_base: 母體：示意假資料・全站活躍玩家（當日至少開一局）｜口徑："
                 "前段 2026-05-01~05-31、後段 2026-06-02~07-01，斷點 6/1 當日不計入兩段｜"
                 "n：前 31 天 648,213 人日／後 30 天 601,940 人日\n"
                 "disclaimer: 示意假資料・不可引用\n"),
                ]
    work = os.path.join(tmp, "fm-opt-back")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    if _edit(work, drop3, fails, "檔頭三欄改選填（還原）") and _edit(
            work, restore3, fails, "檔頭三欄還原"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        got = _md5(_only_html(od)) if r.returncode == 0 else "build 失敗"
        ok = got == base_md5
        print(f"  [{'OK  ' if ok else 'FAIL'}] 把三行寫回去 → 逐 byte 回到 v1.8 的 md5（{got}）")
        if not ok:
            fails.append(f"檔頭三欄還原後 md5 {got} ≠ v1.8 {base_md5}"
                         + ("\n" + r.stdout + r.stderr if r.returncode else ""))

    print("=== F v1.9-2：欄位群直向粗框 col_groups（宣告才生效）===")
    work = os.path.join(tmp, "colgroups")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    cgpairs = [('columns: [指標, 上線前, 上線後, 變化, "|t|"]',
                'columns: [指標, 上線前, 上線後, 變化, "|t|"]\ncol_groups: [1, 2, 1, 1]'),
               ("columns: [底台, 分段, 樣本數, 平均遊戲時間, 變化, \"|t|\"]",
                "columns: [底台, 分段, 樣本數, 平均遊戲時間, 變化, \"|t|\"]\n"
                "col_groups: [2, 1, 2, 1]")]
    if _edit(work, cgpairs, fails, "col_groups"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("col_groups build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] col_groups build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            WANT = "2px solid var(--line)"
            seg = re.search(r'<div class="blk tbl" id="tbl-sig_lr".*?</table>',
                            h, re.S).group(0)
            thead = re.search(r"<thead>.*?</thead>", seg, re.S).group(0)
            ths = re.findall(r"<th [^>]*>", thead)
            n_th_b = sum(1 for t in ths if "border-left:2px solid var(--line)" in t)
            ok = len(ths) == 5 and n_th_b == 3
            print(f"  [{'OK  ' if ok else 'FAIL'}] 表頭 {len(ths)} 欄裡 {n_th_b} 條直粗框"
                  f"（col_groups [1,2,1,1] 的三個群界，要 5 欄 3 條）")
            if not ok:
                fails.append(f"col_groups 表頭不對：{len(ths)} 欄／{n_th_b} 條（要 5／3）")
            # 最終生效值（不是看原始碼有沒有那串字）：群界欄＝inline 2px，其餘欄＝完全沒有。
            # 範圍縮在 tbl-sig_lr 這張表：5 欄 ×（表頭 1 列 ＋ 內容 4 列）＝25 格，
            # 其中群界 3 欄 × 5 列 ＝ 15 格該有粗框。
            res = htmlres.resolve(h, "border-left",
                                  lambda rec: rec["tag"] in ("th", "td")
                                  and "tbl-sig_lr" in rec["ids"])
            edge = [(s2, v) for _r, s2, v in res if v == WANT]
            other = [(s2, v) for _r, s2, v in res if v != WANT]
            ok = (len(res) == 25 and len(edge) == 15
                  and all(s2 == "inline" for s2, _ in edge)
                  and all(s2 == "initial" and v is None for s2, v in other))
            print(f"  [{'OK  ' if ok else 'FAIL'}] 最終生效（共 {len(res)} 格）："
                  f"{len(edge)} 格 border-left＝{WANT} 且來源 inline（要 15）、"
                  f"其餘 {len(other)} 格完全沒有 border-left（要 10）")
            if not ok:
                fails.append(f"col_groups 最終生效值不對：n={len(res)}／edge={len(edge)}"
                             f"／other={other[:4]}")
            # 最右邊不收線（她的草圖只在群之間畫 ｜）
            n_right = h.count("border-right:2px solid")
            ok = n_right == 0
            print(f"  [{'OK  ' if ok else 'FAIL'}] 最右欄不收線：border-right {n_right} 處（要 0）")
            if not ok:
                fails.append(f"col_groups 多畫了右緣線 {n_right} 處")
            # 檢定底色 ＋ 粗框同格：只能有一個 style 屬性、兩件事都在裡面
            both = re.findall(r'<td[^>]*data-sig="1"[^>]*>', seg)
            merged = [t for t in both if "background:#" in t
                      and "border-left:2px solid var(--line)" in t]
            twice = [t for t in both if t.count(" style=") > 1]
            ok = len(merged) >= 1 and not twice
            print(f"  [{'OK  ' if ok else 'FAIL'}] 底色格同時要粗框時併進同一個 style"
                  f"（{len(merged)} 格）、沒有一格有兩個 style 屬性")
            if not ok:
                fails.append(f"底色＋粗框沒併好：merged={len(merged)}／雙 style={len(twice)}")
            # 底色格的最終底色沒有被粗框擠掉
            bg = htmlres.resolve(h, "background",
                                 lambda rec: rec["attrs"].get("data-sig") == "1")
            ok = bg and all(s2 == "inline" and v and v.startswith("#")
                            for _r, s2, v in bg)
            print(f"  [{'OK  ' if ok else 'FAIL'}] {len(bg)} 個底色格的最終底色仍是 inline 色值")
            if not ok:
                fails.append(f"底色被粗框擠掉：{[(a, b) for _r, a, b in bg[:4]]}")
            # col_groups 綁欄不綁列 → 不該把排序關掉
            ok = ('<table class="data sortable"' in seg
                  and 'data-fixed="1"' not in seg)
            print(f"  [{'OK  ' if ok else 'FAIL'}] col_groups 沒有把排序關掉"
                  f"（它綁的是欄，排序只重排列）")
            if not ok:
                fails.append("col_groups 誤把表格變成固定列序")
            # rowspan 合併過的欄：粗框要掛在那個跨列的格子上
            seg2 = re.search(r'<div class="blk tbl" id="tbl-sig_tb".*?</table>',
                             h, re.S).group(0)
            rs = [t for t in re.findall(r"<td[^>]*rowspan=\"2\"[^>]*>", seg2)
                  if "border-left:2px solid var(--line)" in t]
            ok = len(rs) == 3
            print(f"  [{'OK  ' if ok else 'FAIL'}] rowspan 合併格也帶得到直粗框：{len(rs)} 格（要 3）")
            if not ok:
                fails.append(f"rowspan 合併格沒帶到直粗框：{len(rs)}")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] col_groups 之後 qa {nitem} 項仍全綠")
            if not ok:
                fails.append("col_groups 之後 qa 沒全綠\n" + q.stdout)
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", h, re.S))
            got = hashlib.md5(css.encode("utf-8")).hexdigest()
            ok = got == CSS_MD5
            print(f"  [{'OK  ' if ok else 'FAIL'}] CSS 沒有為了直粗框而改動（{got}）")
            if not ok:
                fails.append(f"col_groups 動到 CSS：{got} ≠ {CSS_MD5}")
    # 還原比對：兩行 col_groups 拿掉就要逐 byte 回到 v1.8 的 md5
    work = os.path.join(tmp, "colgroups-back")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    if _edit(work, cgpairs, fails, "col_groups（還原）") and _edit(
            work, [("\ncol_groups: [1, 2, 1, 1]", ""),
                   ("\ncol_groups: [2, 1, 2, 1]", "")], fails, "col_groups 還原"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        got = _md5(_only_html(od)) if r.returncode == 0 else "build 失敗"
        ok = got == base_md5
        print(f"  [{'OK  ' if ok else 'FAIL'}] 拿掉 col_groups → 逐 byte 回到 v1.8 的 md5（{got}）")
        if not ok:
            fails.append(f"col_groups 還原後 md5 {got} ≠ v1.8 {base_md5}")

    print("=== F v1.9-3：結論區三個開關（導言／最重要膠囊／每條一個區塊）===")
    d7md = os.path.join(ROOT, "examples", "charts-demo-7", "報告內容.md")
    before = io.open(_only_html(os.path.join(tmp, "charts-demo-7")),
                     encoding="utf-8").read()
    work = os.path.join(tmp, "concl9")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    c9 = [("appendix: false\nconclusion_style: list",
           "appendix: false\nconclusion_style: numbered\n"
           "conclusion_lead: false\nconclusion_badge: false\nconclusion_box: true"),
          ("- [dn] 結論改成條列之後", "- [up] 結論改成條列之後")]
    if _edit(work, c9, fails, "結論三開關"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("結論三開關 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] 結論三開關 build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            # ① 導言那一行整行不出現（不是留一行空白）
            n_lead = h.count('<p class="sec-lead">紅＝漲')
            glued = '結論</span></h2>\n      <ol class="bul concl-list">' in h
            ok = n_lead == 0 and glued
            print(f"  [{'OK  ' if ok else 'FAIL'}] conclusion_lead: false：導言 {n_lead} 行，"
                  f"h2 與清單直接相接＝{glued}")
            if not ok:
                fails.append(f"conclusion_lead 沒關乾淨：lead={n_lead}／相接={glued}")
            # ② 「最重要」膠囊：驗的是「沒有任何元素命中那條 ::after 的選擇器」
            hit_before = htmlres.count_matching(before, ".theme-b .sec-key .sec-h")
            hit_after = htmlres.count_matching(h, ".theme-b .sec-key .sec-h")
            ok = hit_before == 1 and hit_after == 0
            print(f"  [{'OK  ' if ok else 'FAIL'}] conclusion_badge: false："
                  f".theme-b .sec-key .sec-h 命中數 {hit_before} → {hit_after}"
                  f"（「最重要」::after 沒有對象可以渲染）")
            if not ok:
                fails.append(f"最重要膠囊沒關掉：命中 {hit_before} → {hit_after}")
            # ③ 拿掉 sec-key 之後，它原本帶的樣式要用 inline 原樣補回來——比最終生效值
            def eff(doc, prop, pick):
                return [(s2, v) for _r, s2, v in htmlres.resolve(doc, prop, pick)]
            sec = lambda rec: (rec["tag"] == "section"
                               and rec["attrs"].get("id") == "sec-concl")
            ico = lambda rec: ("sec-ico" in rec["chain"][-1][1]
                               and any(e[2] and "sec-concl" in str(
                                   e) for e in [()]) is False)
            b_bt, a_bt = eff(before, "border-top", sec), eff(h, "border-top", sec)
            b_bg, a_bg = eff(before, "background", sec), eff(h, "background", sec)
            ok = ([v for _s, v in b_bt] == [v for _s, v in a_bt] == ["4px solid var(--up)"]
                  and [v for _s, v in b_bg] == [v for _s, v in a_bg] == ["#fff"])
            print(f"  [{'OK  ' if ok else 'FAIL'}] 結論區的 4px 紅上框與白底最終生效值不變："
                  f"{b_bt}{b_bg} → {a_bt}{a_bg}")
            if not ok:
                fails.append(f"拿掉 sec-key 之後樣式沒補回來：{b_bt}{b_bg} → {a_bt}{a_bg}")
            first_ico = lambda doc: [
                (s2, v) for _r, s2, v in htmlres.resolve(
                    doc, "color", lambda rec: "sec-ico" in rec["chain"][-1][1])][0]
            ok = first_ico(before)[1] == first_ico(h)[1] == "var(--up)"
            print(f"  [{'OK  ' if ok else 'FAIL'}] 結論 icon 的紅色最終生效值不變："
                  f"{first_ico(before)} → {first_ico(h)}")
            if not ok:
                fails.append(f"結論 icon 顏色跑掉：{first_ico(before)} → {first_ico(h)}")
            # ④ 每條結論各自一個區塊：灰底是預設，[up] 那條紅底紅字
            lis = htmlres.resolve(h, "background",
                                  lambda rec: rec["tag"] == "li"
                                  and "concl-sub" not in "".join(
                                      sorted(rec["chain"][-2][1]))
                                  and rec["inline"].get("border-radius") == "12px")
            grey = [v for _r, s2, v in lis if v == "var(--panel)" and s2 == "inline"]
            red = [v for _r, s2, v in lis if v == "var(--up-bg)" and s2 == "inline"]
            redc = [v for _r, s2, v in htmlres.resolve(
                h, "color", lambda rec: rec["tag"] == "li"
                and rec["inline"].get("background") == "var(--up-bg)")
                if v == "var(--up)"]
            ok = len(lis) == 3 and len(grey) == 2 and len(red) == 1 and len(redc) == 1
            print(f"  [{'OK  ' if ok else 'FAIL'}] conclusion_box: true：3 條結論各一個區塊"
                  f"（灰底 {len(grey)}／紅底 {len(red)}、紅底那條連字也是紅的 {len(redc)}）")
            if not ok:
                fails.append(f"結論區塊不對：共 {len(lis)}／灰 {len(grey)}／紅 {len(red)}／紅字 {len(redc)}")
            # ⑤ 子項沒有被包成區塊（她要的是「每一點」一個區塊，不是每一行）
            subs = [1 for _r, s2, v in htmlres.resolve(
                h, "background", lambda rec: rec["tag"] == "li"
                and "concl-sub" in rec["chain"][-2][1]) if s2 == "inline"]
            ok = not subs
            print(f"  [{'OK  ' if ok else 'FAIL'}] ◦ 子項沒有各自再包一個區塊（{len(subs)} 個）")
            if not ok:
                fails.append(f"◦ 子項被多包了 {len(subs)} 個區塊")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] 三個開關之後 qa {nitem} 項仍全綠")
            if not ok:
                fails.append("結論三開關之後 qa 沒全綠\n" + q.stdout)
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", h, re.S))
            got = hashlib.md5(css.encode("utf-8")).hexdigest()
            ok = got == CSS_MD5
            print(f"  [{'OK  ' if ok else 'FAIL'}] CSS 沒有為了結論區塊而改動（{got}）")
            if not ok:
                fails.append(f"結論三開關動到 CSS：{got} ≠ {CSS_MD5}")
    # 還原比對：三個開關拿掉、style 改回 list → 逐 byte 回到 v1.8 的 charts-demo-7
    work = os.path.join(tmp, "concl9-back")
    shutil.copytree(os.path.join(ROOT, "examples", "charts-demo-7"), work)
    if _edit(work, c9[:1], fails, "結論三開關（還原）") and _edit(
            work, [("appendix: false\nconclusion_style: numbered\n"
                    "conclusion_lead: false\nconclusion_badge: false\n"
                    "conclusion_box: true",
                    "appendix: false\nconclusion_style: list")], fails, "結論三開關還原"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        got = _md5(_only_html(od)) if r.returncode == 0 else "build 失敗"
        ok = got == D7_MD5
        print(f"  [{'OK  ' if ok else 'FAIL'}] 拿掉三個開關 → 逐 byte 回到 v1.8 的 md5（{got}）")
        if not ok:
            fails.append(f"結論三開關還原後 md5 {got} ≠ v1.8 {D7_MD5}")

    print("=== G v1.11：同一段多處重點紅字（Lena 2026-09-17 11:57「不要分段」）===")
    # 正向：把 sig-shade-demo 的免責那一行改成同段 3 處紅字。要驗三件事：
    #   ① 真的渲染成 3 個 .hl，而且全部落在**同一個 </li> 段**裡（不是被拆到別段去）
    #   ② 每一處的**最終生效** color／background 都是重點紅（串接算出來，不是 grep 原始碼）
    #   ③ qa 17 項仍全綠（第 6 項自己就會擋上限與顏色）
    HL1 = "- !!全部數字都是示意假資料!!，不是任何真實遊戲的輸出，不可引用、不可做決定。"
    HL3 = ("- !!全部數字都是示意假資料!!，!!不是任何真實遊戲的輸出!!，"
           "!!不可引用、不可做決定!!。")
    work = os.path.join(tmp, "hl3")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    if _edit(work, [(HL1, HL3)], fails, "同段 3 處紅字"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        if r.returncode != 0:
            fails.append("同段 3 處紅字 build 失敗\n" + r.stdout + r.stderr)
            print("  [FAIL] 同段 3 處紅字 build")
        else:
            html = _only_html(od)
            h = io.open(html, encoding="utf-8").read()
            segs = [len(re.findall(r'<span class="hl">', seg))
                    for seg in re.split(r"</p>|</li>", h)]
            n_all, n_max = sum(segs), (max(segs) if segs else 0)
            ok = n_all == 3 and n_max == 3
            print(f"  [{'OK  ' if ok else 'FAIL'}] 同段 3 處紅字渲染成功："
                  f"全文 {n_all} 處、最密的一段 {n_max} 處（要 3／3）")
            if not ok:
                fails.append(f"同段多紅字沒渲染對：全文 {n_all}／最密 {n_max}（要 3／3）")
            txt = re.findall(r'<span class="hl">(.*?)</span>', h)
            want = ["全部數字都是示意假資料", "不是任何真實遊戲的輸出", "不可引用、不可做決定"]
            ok = txt == want
            print(f"  [{'OK  ' if ok else 'FAIL'}] 三處紅字的內容與順序正確（{txt}）")
            if not ok:
                fails.append(f"三處紅字內容不對：{txt} ≠ {want}")

            def is_hl(rec):
                return rec["tag"] == "span" and "hl" in rec["chain"][-1][1]
            col = htmlres.resolve(h, "color", is_hl)
            bg = htmlres.resolve(h, "background", is_hl)
            okc = len(col) == 3 and all(v == "var(--up)" for _r, _s, v in col)
            okb = len(bg) == 3 and all(v == "var(--up-bg)" for _r, _s, v in bg)
            print(f"  [{'OK  ' if (okc and okb) else 'FAIL'}] 三處的最終生效值："
                  f"color {[(s2, v) for _r, s2, v in col]}／"
                  f"background {[(s2, v) for _r, s2, v in bg]}")
            if not (okc and okb):
                fails.append(f"同段多紅字的最終生效顏色不對：color={col}／bg={bg}")
            q = _qa(html)
            nitem = len(re.findall(r"^\s*\[(?:OK  |BAD )\]", q.stdout, re.M))
            ok = "總結：全部通過" in q.stdout and nitem == QA_ITEMS
            print(f"  [{'OK  ' if ok else 'FAIL'}] 同段 3 處紅字之後 qa {nitem} 項仍全綠")
            if not ok:
                fails.append("同段 3 處紅字之後 qa 沒全綠\n" + q.stdout)
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", h, re.S))
            got = hashlib.md5(css.encode("utf-8")).hexdigest()
            ok = got == CSS_MD5
            print(f"  [{'OK  ' if ok else 'FAIL'}] CSS 沒有為了放寬紅字而改動（{got}）")
            if not ok:
                fails.append(f"紅字放寬動到 CSS：{got} ≠ {CSS_MD5}")
    # 還原比對：改回單處紅字 → 逐 byte 回到 v1.10 的 sig-shade-demo
    work = os.path.join(tmp, "hl3-back")
    shutil.copytree(os.path.join(ROOT, "examples", "sig-shade-demo"), work)
    if _edit(work, [(HL1, HL3)], fails, "同段 3 處紅字（還原）") and _edit(
            work, [(HL3, HL1)], fails, "同段 3 處紅字還原"):
        od = os.path.join(work, "out")
        r = _build(os.path.join(work, "報告內容.md"), od)
        got = _md5(_only_html(od)) if r.returncode == 0 else "build 失敗"
        ok = got == BASELINE["sig-shade-demo"]
        print(f"  [{'OK  ' if ok else 'FAIL'}] 改回單處紅字 → 逐 byte 回到 v1.10 的 md5（{got}）")
        if not ok:
            fails.append(f"紅字還原後 md5 {got} ≠ v1.10 {BASELINE['sig-shade-demo']}")
    # 上限是硬的：build 期（mdcontent）與 qa 期（qa_html）必須是同一個數字，
    # 改一邊忘了改另一邊要當場被抓到。
    import mdcontent as _mdc
    _qa_src = io.open(os.path.join(SCRIPTS, "qa_html.py"), encoding="utf-8").read()
    m = re.search(r"^HL_MAX = (\d+)$", _qa_src, re.M)
    ok = bool(m) and int(m.group(1)) == _mdc.HL_MAX == 3
    print(f"  [{'OK  ' if ok else 'FAIL'}] build 期與 qa 期的上限是同一個數字"
          f"（mdcontent {_mdc.HL_MAX}／qa_html {m.group(1) if m else '?'}，要 3）")
    if not ok:
        fails.append("HL_MAX 兩邊不一致或不是 3")

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if fails:
        print(f"[{len(fails)} FAIL]")
        for f in fails:
            print(" -", f)
        return 1
    print("[ALL PASS]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
