# -*- coding: utf-8 -*-
"""mdcontent — 讀 `報告內容.md` → 組出 rhtml.Report。

v4（skill 版）：文字、圖表宣告、數字來源全部在一份 md 裡，資料由 csv／json 提供。

    報告內容.md               文字 ＋ ```figure／```table 宣告（Lena 或 Claude 編）
    data/*.csv, values.json   圖表資料與數字
    figures.py                宣告 → svgchart 畫圖／組表；{{v:key}} 數值
    本檔                       解析 md、把兩邊接起來
    rhtml.py / themes.py      版型與風格（不動）

格式（完整說明見 references/內容檔格式說明.md 與 references/圖表與數值宣告格式.md）
--------------------------------------------------------------------
    ---                       ← 檔頭 front-matter（YAML 子集）
    title: 遊戲－議題
    values:                   ← {{v:key}} 的來源（也可用 values_file: data/values.json）
      前段平均: {{n:39.05:分}}
      週最高: {fn: max, fig: dow, col: value, fmt: d, nd: 2, unit: " 分"}
    ---

    ## 前言                    ← `##` 一個區塊；前言／結論／建議／附錄／本版說明
    ## 結論                       是保留字，其餘 `##` 一律當成編號章節
    - [dn] 一句話結論           ← 結論用清單，[dn] 綠／[up] 紅／不寫＝灰
    ## 建議
    - [立即] 動作
      預期影響：...
    ## 現象確認：...            ← 章節
    本章結論：一句
    說明段落
    ```figure                 ← 圖表宣告，自帶位置（放在哪、圖就在哪）
    key: ts_break
    type: line
    ...
    ```
    判讀：一句                 ← 緊接在收尾 ``` 的下一行
    ### 子節標題               ← `###` 子節（H3）

行內標記：`{{v:key}}` 數字（來自 values）、`{{n:39:分}}` 手寫數字、
`{{d:-4.7:分}}` 變化量、`!!重點!!`（v1.11：一段最多 3 處）、`**粗體**`、
`[[key]]` 文中引用圖表。

錯誤處理：不靜默略過、也不整份爆掉。解析時把所有問題收集起來，
一次印出「第幾行、什麼問題、可用的值是哪些」，HTML 不會被覆蓋。
"""
import difflib
import io
import os
import re

import figures
import yamlite as Y
from rhtml import Bullets, Details, Figure, Para, Report, Sub, Table

# v1.9 第 1 項（Lena 2026-09-17 10:18 第 1 點「不需要 subtitle／produced／note_base」）：
# subtitle 與 produced 從必填改成選填（note_base 從 v1.5 起本來就是選填）。
# 沒寫＝那一塊整個不渲染：副標連 <p class="subtitle"> 整行都不出現、
# 產出日期不會在資料說明列留下一個空欄位或多一根 ｜ 分隔線。
FM_REQ = ["title", "period", "population", "source", "byline"]
FM_OPT = ["subtitle", "produced",
          "disclaimer", "badge", "values", "values_file", "note_base",
          # v1.5 兩個開關：附錄可關、互動提示可關（不寫＝v1.4 行為）
          "appendix", "hints",
          # v1.7：結論的呈現方式（不寫＝card，條狀卡片，輸出逐 byte 同 v1.6）
          "conclusion_style",
          # v1.9 結論區三個開關（不寫＝v1.8 行為，輸出逐 byte 不變）
          "conclusion_lead", "conclusion_badge", "conclusion_box"]
FM_BOOL = ["appendix", "hints",
           "conclusion_lead", "conclusion_badge", "conclusion_box"]
FM_ALL = FM_REQ + FM_OPT
FM_TEXT = FM_REQ + ["subtitle", "produced",
                    "disclaimer", "badge", "values_file", "note_base"]
CONCL_STYLE = ("card", "list", "numbered")
# v1.7：card＝條狀卡片（預設）／list＝純條列（•）
# v1.8：numbered＝編號條列（1. 2. 3.），子項仍是 ◦（Lena 2026-09-16 17:38 第 a 點）

SEC_PREFACE, SEC_CONCL, SEC_REC, SEC_APP, SEC_VER = (
    "前言", "結論", "建議", "附錄", "本版說明")
RESERVED = [SEC_PREFACE, SEC_CONCL, SEC_REC, SEC_APP, SEC_VER]
REQUIRED_SECS = [SEC_PREFACE, SEC_CONCL, SEC_REC, SEC_APP]

TONE = {"dn": "dn", "跌": "dn", "綠": "dn",
        "up": "up", "漲": "up", "紅": "up",
        "": "", "中性": "", "灰": ""}

K_CSUB = "\u25e6"                          # ◦：結論條列模式的子項記號
K_TAKE = "本章結論："
K_LEAD = "導言："
K_READ = "判讀："
K_TITLE = "標題："
K_IMPACT = "預期影響："
FOLD_OPEN = ":::摺疊"
FOLD_CLOSE = ":::"

RE_EMBED_LINE = re.compile(r"^\{\{(fig|tbl):([^}]*)\}\}$")
RE_ANY_MARK = re.compile(r"\{\{([^}]*)\}\}")
RE_XREF = re.compile(r"\[\[([^\]]*)\]\]")
RE_LI = re.compile(r"^[-*]\s+(.*)$")
RE_CODE = re.compile(r"`[^`]*`")            # 反引號內＝字面值，標記不展開
# 只吃 [dn]／[立即] 這種單層方括號；[[fig]] 開頭的句子不會被誤判成標記
RE_TAG = re.compile(r"^\[([^\[\]]*)\]\s*(.*)$")

# v1.11（Lena 2026-09-17 11:57「改引擎，同一段可以多處紅字，不要分段」）：
# 重點紅字從「一段最多一處」放寬成「一段最多 HL_MAX 處」。
# 放寬的是處數，不是「不檢查」——上限仍然是硬的，超過就報錯＋行號＋不產 HTML。
# 為什麼訂 3：紅字是「一眼看到哪裡最重要」的工具，一段三處已經是
# 「現象 → 來源 → 元凶」三層的極限（印尼合併版 v11 結論 3 的資產子項就是這三層：
# 資產減少 → 少在儲值&獎勵 → 每日任務獎勵_德撲幣）；再多就沒有重點可言。
HL_MAX = 3
RE_HL_PAIR = re.compile(r"!!(.+?)!!")


class ContentError(Exception):
    """帶行號的解析錯誤集合。build.py 抓到就印出來、不寫 HTML。"""

    def __init__(self, path, problems):
        self.path = path
        self.problems = problems
        super().__init__(f"{path}：{len(problems)} 個問題")

    def report(self):
        out = [f"內容檔解析失敗：{self.path}"]
        roots = [p for p in self.problems if len(p) > 3 and p[3]]
        rest = [p for p in self.problems if not (len(p) > 3 and p[3])]

        def emit(items):
            for p in items:
                ln, msg, hint = p[0], p[1], p[2]
                where = f"第 {ln} 行" if ln else "檔頭"
                out.append(f"  {where}：{msg}")
                if hint:
                    out.append(f"           → {hint}")
        if roots and rest:
            out.append("【先修這些：圖表宣告／資料層的根因】")
            emit(roots)
            out.append("【接著才看這些：正文層，多半是上面造成的連鎖】")
            emit(rest)
        else:
            emit(roots + rest)
        out.append(f"共 {len(self.problems)} 個問題；HTML 沒有重新產生，"
                   f"改完再跑一次 build.py。")
        return "\n".join(out)


class _Placed:
    """解析失敗的圖表在正文的替身：讓後面的「判讀：」有東西掛、不再多報一條。"""
    reading = None
    title = None


class _Parser:
    def __init__(self, path, data):
        self.path = path
        self.values = data["values"]
        self.figs = data["figs"]
        self.tbls = data["tbls"]
        self.blocks = data.get("blocks", {})      # 開頭行號 → (kind, key, 收尾行號)
        self.broken = data.get("broken", set())
        self.broken_values = data.get("broken_values", set())
        self.problems = list(data.get("problems", []))
        self.used = set()

    # ---------------------------------------------------------------- 錯誤
    def bad(self, ln, msg, hint=""):
        self.problems.append((ln, msg, hint))

    # ------------------------------------------------------ 行內標記檢查／展開
    def inline(self, text, ln):
        """展開 {{v:key}}，並檢查其他標記有沒有打錯。回傳展開後的字串。"""
        def sub_v(m):
            body = m.group(1)
            head, _, rest = body.partition(":")
            head = head.strip()
            if head == "v":
                key = rest.strip()
                if key in self.values:
                    return self.values[key]
                if key in self.broken_values:          # 根因是壞掉的圖，已報過
                    return m.group(0)
                near = _near(key, self.values)
                self.bad(ln, f"{{{{v:{key}}}}} 找不到這個數字 key",
                         (f"是不是要打 {near}？"
                          "（全部的 key 跑 `python3 build.py --keys`）") if near
                         else "數字 key 在檔頭 values: 或 values_file 裡定義；"
                              "跑 `python3 build.py --keys` 會全部列出來")
                return f"{{{{v:{key}}}}}"
            if head in ("n", "d"):
                if rest.count(":") != 1:
                    self.bad(ln, f"{{{{{body}}}}} 格式不對",
                             "數字要寫成 {{n:39.1:分}}、變化量要寫成 "
                             "{{d:-4.7:分}}（數字和單位之間一個冒號）")
                return m.group(0)
            if head == "warn":                      # v1.5：警示 icon（紅色三角驚嘆號）
                if rest.strip():
                    self.bad(ln, f"{{{{{body}}}}} 不吃參數", "警示 icon 就寫 {{warn}}（不用加冒號與文字）")
                return m.group(0)
            if head in ("fig", "tbl"):
                self.bad(ln, f"{{{{{body}}}}} 這種寫法已停用",
                         "圖表改用 ```figure／```table 區塊宣告（區塊放哪、圖就在哪）；"
                         f"文中要提到圖表請用 [[{rest.strip()}]]")
                return m.group(0)
            self.bad(ln, f"不認識的標記 {{{{{body}}}}}",
                     "可用：{{v:數字key}}、{{n:39.1:分}}、{{d:-4.7:分}}、{{warn}}")
            return m.group(0)

        # 反引號 `...` 內的內容整段跳過（要寫「標記長什麼樣」就把它包起來）
        parts, chk = [], []
        pos = 0
        for m in RE_CODE.finditer(text):
            parts.append(RE_ANY_MARK.sub(sub_v, text[pos:m.start()]))
            chk.append(text[pos:m.start()])
            parts.append(m.group(0))
            pos = m.end()
        parts.append(RE_ANY_MARK.sub(sub_v, text[pos:]))
        chk.append(text[pos:])
        s, plain = "".join(parts), "".join(chk)
        if plain.count("{{") != plain.count("}}"):
            self.bad(ln, "標記的大括號沒有成對（{{ 與 }} 數量不同）")
        for m in RE_XREF.finditer(plain):
            key = m.group(1).strip()
            if key not in self.figs and key not in self.tbls and key not in self.broken:
                self.bad(ln, f"[[{key}]] 找不到這個圖表 key", self._keyhint())
        if plain.count("!!") % 2:
            self.bad(ln, "!! 沒有成對", "重點紅字要寫成 !!這幾個字!!")
        else:
            # v1.11：成對檢查保留，另外補兩條——
            # (a) 數量對得上：`!!` 的對數要等於真的配得出來的處數。
            #     `!!!!`（空內容）或 `!!a!!!!b!!` 這種畸形會讓 parity 過關但渲染跟寫的人想的不一樣。
            # (b) 同一段最多 HL_MAX 處紅字（v1.11 從 1 放寬而來）。
            n_hl = len(RE_HL_PAIR.findall(plain))
            if n_hl != plain.count("!!") // 2:
                self.bad(ln, f"!! 配對不出來（{plain.count('!!')} 個 !! 只組得出 {n_hl} 處紅字）",
                         "每一處都要寫成 !!這幾個字!!，中間不能是空的、也不要多打一個 !")
            elif n_hl > HL_MAX:
                self.bad(ln, f"同一段最多 {HL_MAX} 處重點紅字（這一段有 {n_hl} 處）",
                         "紅字是「一眼看到哪裡最重要」，一段超過三處就沒有重點了；"
                         "請刪到三處以內，或把這一段拆開")
        if plain.count("**") % 2:
            self.bad(ln, "** 沒有成對", "粗體要寫成 **這幾個字**")
        return s

    def _keyhint(self):
        return (f"已宣告的圖：{'、'.join(self.figs) or '（無）'}；"
                f"表：{'、'.join(self.tbls) or '（無）'}")

    # ---------------------------------------------------------------- 切區塊
    def split_secs(self, lines, start):
        secs, cur = [], None
        i = start
        while i < len(lines):
            raw = lines[i].rstrip()
            ln = i + 1
            if ln in self.blocks:                     # ``` 區塊整段原樣收進目前區塊
                close_ln = self.blocks[ln][2]
                if cur is None:
                    self.bad(ln, "圖表區塊不在任何 `## 章節` 裡", "圖表要放在章節或附錄底下")
                else:
                    for k in range(i, close_ln):
                        cur[2].append((k + 1, lines[k].rstrip()))
                i = close_ln
                continue
            i += 1
            if raw.startswith("# ") or raw.strip() == "#":
                self.bad(ln, "不要用 `#` 一層標題", "報告大標在檔頭的 title 欄位；"
                                                "區塊用 `##`、子節用 `###`")
                continue
            if raw.startswith("## "):
                name = raw[3:].strip()
                if not name:
                    self.bad(ln, "`##` 後面沒有標題")
                    continue
                if any(s[0] == name for s in secs):
                    self.bad(ln, f"區塊 `{name}` 重複了")
                cur = (name, ln, [])
                secs.append(cur)
                continue
            if cur is None:
                if raw.strip():
                    self.bad(ln, f"這行不在任何區塊裡：{raw.strip()[:40]}",
                             "正文要放在某個 `## 區塊` 底下")
                continue
            cur[2].append((ln, raw))
        return secs

    # ------------------------------------------------------------ 一般內容區塊
    def blocks_of(self, body, target, allow_items=True):
        """把 (行號, 文字) 串成 Para／Bullets／Sub／Details／圖表，附加到 target。"""
        buf, bul, i, last = [], [], 0, None

        def flush():
            nonlocal buf, bul, last
            if buf:
                target.para(self.join(buf))
                last = None
            if bul:
                target.bullets(bul)
                last = None
            buf, bul = [], []

        while i < len(body):
            ln, raw = body[i]
            t = raw.strip()
            i += 1
            if ln in self.blocks:                     # ```figure／```table
                flush()
                kind, key, close_ln = self.blocks[ln]
                while i < len(body) and body[i][0] <= close_ln:
                    i += 1
                last = self.attach(ln, kind, key, target, allow_items)
                continue
            if not t:
                flush()
                continue
            if t.startswith(FOLD_OPEN):
                flush()
                summary = t[len(FOLD_OPEN):].strip()
                inner, closed = [], False
                while i < len(body):
                    ln2, raw2 = body[i]
                    i += 1
                    if raw2.strip() == FOLD_CLOSE:
                        closed = True
                        break
                    inner.append((ln2, raw2))
                if not closed:
                    self.bad(ln, f"`{FOLD_OPEN}` 沒有用一行 `:::` 收尾")
                if not summary:
                    self.bad(ln, f"`{FOLD_OPEN}` 後面要寫摺疊起來的標題")
                box = _Box()
                self.blocks_of(inner, box, allow_items=False)
                target.details(self.inline(summary, ln), box.blocks)
                last = None
                continue
            if t.startswith("### "):
                flush()
                target.sub(self.inline(t[4:].strip(), ln))
                last = None
                continue
            if t.startswith("#"):
                self.bad(ln, f"標題層級只到 `###`：{t[:30]}")
                continue
            m = RE_EMBED_LINE.match(t)
            if m:
                flush()
                self.bad(ln, f"{{{{{m.group(1)}:{m.group(2).strip()}}}}} 這種寫法已停用",
                         "圖表改用 ```figure／```table 區塊宣告，區塊放在這裡、圖就出現在這裡；"
                         "文中提到圖表用 [[key]]")
                last = _Placed()
                continue
            if t.startswith(K_READ) or t.startswith(K_TITLE):
                kind = K_READ if t.startswith(K_READ) else K_TITLE
                val = t[len(kind):].strip()
                if last is None:
                    self.bad(ln, f"`{kind}` 要緊接在 ```figure／```table 區塊的收尾 ``` 下一行")
                elif kind == K_READ:
                    last.reading = self.inline(val, ln)
                else:
                    last.title = self.inline(val, ln)
                continue
            if t.startswith(K_TAKE) or t.startswith(K_LEAD):
                flush()
                kind = K_TAKE if t.startswith(K_TAKE) else K_LEAD
                val = self.inline(t[len(kind):].strip(), ln)
                if not hasattr(target, "takeaway"):
                    self.bad(ln, f"`{kind}` 只能寫在章節裡（不是前言／結論／"
                                 f"建議／附錄）")
                elif kind == K_TAKE:
                    target.takeaway = val
                else:
                    target.subtitle = val
                continue
            if t.startswith(K_IMPACT):
                self.bad(ln, f"`{K_IMPACT}` 只能寫在「建議」的清單項目底下")
                continue
            mli = RE_LI.match(t)
            if mli:
                if buf:
                    flush()
                bul.append(self.inline(mli.group(1).strip(), ln))
                last = None
                continue
            if bul:
                flush()
            buf.append((ln, t))
            last = None
        flush()

    def join(self, buf):
        """同一段的多行黏成一句（中文不用空白；兩邊都是英數才補一個空白）。"""
        out = ""
        for ln, t in buf:
            t = self.inline(t, ln)
            if out and re.search(r"[0-9A-Za-z]$", out) and re.match(r"[0-9A-Za-z]", t):
                out += " "
            out += t
        return out

    # ------------------------------------------------------------ 圖表區塊放置
    def attach(self, ln, kind, key, target, allow_items):
        if kind is None or key is None or key in self.broken:
            return _Placed()                      # 解析階段已報過錯
        reg = self.figs if kind == "fig" else self.tbls
        word = "圖" if kind == "fig" else "表"
        if not allow_items:
            self.bad(ln, f"摺疊區塊裡不能放{word}表", "圖表請放在章節正文裡")
            return _Placed()
        if not hasattr(target, "figure"):
            self.bad(ln, f"這裡不能放{word}表（只有章節與附錄可以）")
            return _Placed()
        if key in self.used:
            self.bad(ln, f"{word}表 `{key}` 已經放過一次了")
            return _Placed()
        if key not in reg:
            return _Placed()
        self.used.add(key)
        spec = reg[key]
        title = self.inline(spec["title"], ln)
        note = self.inline(spec["note"], ln)
        defs = [(k, self.inline(v, ln)) for k, v in spec["defs"]]
        if kind == "fig":
            return target.figure(key, title, spec["svg"], note, defs=defs)
        rows = []
        for row in spec["rows"]:
            rows.append([(self.inline(c[0], ln), c[1]) if isinstance(c, tuple)
                         else self.inline(c, ln) for c in row])
        return target.table(key, title, spec["headers"], rows, note,
                            aligns=spec["aligns"], col_types=spec["col_types"],
                            emph_rows=spec["emph_rows"], defs=defs,
                            sortable=spec.get("sortable", True),
                            rowspan=spec.get("rowspan", ()),
                            row_groups=spec.get("row_groups", ()),
                            col_groups=spec.get("col_groups", ()),
                            sig=spec.get("sig"))

    # ---------------------------------------------------------------- 結論
    def conclusions(self, R, body):
        """條狀卡片是預設；v1.5 起也吃 ```table／```figure 區塊（第一張卡片之前
        宣告的排在卡片上方，之後宣告的排在下方）。

        v1.7／v1.8：檔頭寫 conclusion_style: list（•）或 numbered（1. 2. 3.）
        時改成純條列，並且多吃一層
        `　◦ 子項`（掛在上一條底下）。沒宣告時完全是 v1.6 的路徑——`◦` 開頭的行
        仍然是「同一條寫太長換行接續」。"""
        got = 0
        listmode = R.conclusion_style in ("list", "numbered")
        pre, post, last = _App(), _App(), None
        i = 0
        while i < len(body):
            ln, raw = body[i]
            i += 1
            if ln in self.blocks:                     # ```table／```figure
                kind, key, close_ln = self.blocks[ln]
                while i < len(body) and body[i][0] <= close_ln:
                    i += 1
                last = self.attach(ln, kind, key, post if got else pre, True)
                continue
            t = raw.strip()
            if not t:
                continue
            if t.startswith(K_READ) and last is not None:
                last.reading = self.inline(t[len(K_READ):].strip(), ln)
                continue
            if listmode and t.startswith(K_CSUB):
                sub = t[len(K_CSUB):].strip()
                if not got:
                    self.bad(ln, f"「{SEC_CONCL}」的第一條就是 `◦` 子項，"
                                 f"上面沒有可以掛的主條目：{sub[:30]}",
                             "子項要寫在某一條 `- 一句話` 底下；"
                             "它自己要獨立成一條就改成 `- ` 開頭")
                elif not sub:
                    self.bad(ln, "這條 `◦` 子項沒有內容")
                else:
                    R.conclusion_sub(self.inline(sub, ln))
                last = None
                continue
            m = RE_LI.match(t)
            if not m:
                if got:                      # 一條寫太長換行接續：接到上一條
                    txt, tone = R.conclusions[-1]
                    R.conclusions[-1] = (txt + self.inline(t, ln), tone)
                    continue
                self.bad(ln, f"「{SEC_CONCL}」裡每一條都要用 `- ` 開頭："
                             f"{t[:30]}",
                         "格式：`- [dn] 一句話`（[dn] 綠／[up] 紅／不寫＝灰）")
                continue
            txt, tone = m.group(1).strip(), ""
            mt = RE_TAG.match(txt)
            if mt:
                raw_tone = mt.group(1).strip()
                if raw_tone not in TONE:
                    self.bad(ln, f"結論的顏色標記 `[{raw_tone}]` 不認得",
                             "只有 [dn]（綠、跌）、[up]（紅、漲）、"
                             "不寫（灰、中性）三種")
                else:
                    tone, txt = TONE[raw_tone], mt.group(2).strip()
            if not txt:
                self.bad(ln, "這條結論沒有內容")
                continue
            R.conclusion(self.inline(txt, ln), tone)
            got += 1
            last = None
        R.concl_pre, R.concl_post = pre.blocks, post.blocks
        if not got:
            self.bad(body[0][0] if body else 0, f"「{SEC_CONCL}」是空的",
                     "條狀卡片是結論的預設形式，至少要有一條 `- 一句話`"
                     "（表格是加在卡片之外的，不能取代卡片）")

    # ---------------------------------------------------------------- 建議
    def recommends(self, R, body):
        cur, field = None, None
        for ln, raw in body:
            t = raw.strip()
            if not t:
                continue
            m = RE_LI.match(t)
            if m:
                field = "action"
                txt = m.group(1).strip()
                tag = ""
                mt = RE_TAG.match(txt)
                if mt:
                    tag, txt = mt.group(1).strip(), mt.group(2).strip()
                if not txt:
                    self.bad(ln, "這條建議沒有動作內容")
                    continue
                cur = dict(action=self.inline(txt, ln), impact="", tag=tag,
                           ln=ln)
                R.recommendations.append(cur)
                continue
            if t.startswith(K_IMPACT):
                field = "impact"
                if cur is None:
                    self.bad(ln, f"`{K_IMPACT}` 前面要先有一條 `- ` 建議")
                else:
                    cur["impact"] = self.inline(t[len(K_IMPACT):].strip(), ln)
                continue
            if cur is not None and field:      # 寫太長換行接續
                cur[field] += self.inline(t, ln)
                continue
            self.bad(ln, f"「{SEC_REC}」裡只認得 `- 動作` 與 `{K_IMPACT}...`："
                         f"{t[:30]}",
                     "格式：\n             - [立即] 動作\n"
                     "               預期影響：會影響什麼")
        for r in R.recommendations:
            if not r["impact"]:
                self.bad(r.pop("ln"), f"這條建議少了 `{K_IMPACT}` 那一行")
            else:
                r.pop("ln", None)
        if not R.recommendations:
            self.bad(body[0][0] if body else 0, f"「{SEC_REC}」是空的")


def _near(key, pool):
    """打錯字時給最接近的 key（她不必去翻說明檔）。"""
    hit = difflib.get_close_matches(key, list(pool), n=2, cutoff=0.5)
    return "、".join(f"`{h}`" for h in hit) if hit else ""


class _Box:
    """摺疊區塊的收納盒（只收 Para／Bullets／Sub）。"""

    def __init__(self):
        self.blocks = []

    def para(self, text, cls=""):
        self.blocks.append(Para(text, cls)); return self

    def bullets(self, items, cls=""):
        self.blocks.append(Bullets(items, cls)); return self

    def sub(self, title):
        self.blocks.append(Sub(title)); return self

    def details(self, summary, blocks):
        self.blocks.extend(blocks); return self


class _App:
    """前言／附錄／本版說明的收納盒（可放圖表）。"""

    def __init__(self):
        self.blocks = []

    def para(self, text, cls=""):
        self.blocks.append(Para(text, cls)); return self

    def bullets(self, items, cls=""):
        self.blocks.append(Bullets(items, cls)); return self

    def sub(self, title):
        self.blocks.append(Sub(title)); return self

    def details(self, summary, blocks):
        self.blocks.append(Details(summary, blocks)); return self

    def figure(self, *a, **k):
        it = Figure(*a, **k); self.blocks.append(it); return it

    def table(self, *a, **k):
        it = Table(*a, **k); self.blocks.append(it); return it


# ---------------------------------------------------------------- 檔頭
def front_matter(lines, problems):
    """`---` 之間的 YAML 子集。回傳 (fm dict, 行號表, 正文起始索引)。"""
    if not lines or lines[0].strip() != "---":
        problems.append((1, "檔頭不見了", "第一行要是 ---，接著 title: ... 等欄位，再用一行 --- 收尾"))
        return {}, {}, 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        problems.append((len(lines), "檔頭沒有收尾的 ---", ""))
        return {}, {}, len(lines)
    try:
        fm, lnmap = Y.parse("\n".join(lines[1:end]), 2)
    except Y.YamlError as e:
        problems.append((e.ln, f"檔頭：{e.msg}", "檔頭每行是 `欄位: 值`；values 底下縮排兩格寫 key: 值"))
        return {}, {}, end + 1
    if not isinstance(fm, dict):
        problems.append((2, "檔頭要是 `欄位: 值` 的形式", ""))
        return {}, {}, end + 1
    for k in list(fm):
        ln = Y.get_ln(lnmap, (k,), 2)
        if k not in FM_ALL:
            problems.append((ln, f"檔頭不認識的欄位 `{k}`",
                             f"可用欄位：{'、'.join(FM_ALL)}（{'、'.join(FM_OPT)} 可以不寫）"))
            fm.pop(k)
        elif k in FM_TEXT and isinstance(fm[k], (list, dict)):
            problems.append((ln, f"檔頭欄位 `{k}` 要是一段文字", ""))
            fm.pop(k)
    miss = [k for k in FM_REQ if str(fm.get(k, "") if fm.get(k) is not None else "").strip() == ""]
    if miss:
        problems.append((0, f"檔頭缺欄位：{'、'.join(miss)}", "這些是標題區與資料說明要用的，不能空著"))
    return fm, lnmap, end + 1


def load(path):
    """讀 md → Report。有問題丟 ContentError（含行號）。"""
    if not os.path.exists(path):
        raise ContentError(path, [(0, "找不到這個內容檔",
                                   "用 `build.py --md 檔案.md` 指定")])
    text = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
    lines = text.split("\n")
    md_dir = os.path.dirname(os.path.abspath(path))
    problems = []
    fm, fm_lnmap, start = front_matter(lines, problems)

    # 1 掃 ``` 區塊、讀資料 → 2 算數字 → 3 畫圖／組表
    ctx = figures.collect(lines, start, md_dir, fm)
    values, value_doc = figures.resolve_values(fm, fm_lnmap, md_dir, ctx)
    figures.render_all(ctx, values)

    P = _Parser(path, dict(values=values, figs=ctx.figs, tbls=ctx.tbls,
                           blocks=ctx.blocks, broken=ctx.broken,
                           broken_values=ctx.broken_values,
                           problems=problems + ctx.problems))
    P.value_doc = value_doc
    P.decls = ctx.decls

    def fmv(k):
        v = fm.get(k)
        if v in (None, ""):
            return ""
        return P.inline(str(v), Y.get_ln(fm_lnmap, (k,), 0))

    R = Report(title=fmv("title") or "（缺 title）", subtitle=fmv("subtitle"),
               produced=fmv("produced"), kicker=fmv("byline"),
               watermark=fmv("disclaimer"))
    R.badge = fmv("badge")
    # v1.5 兩個開關（不寫＝v1.4 行為：附錄要有、互動提示要印）
    flags = {}
    for k in FM_BOOL:
        if k in fm and fm[k] not in (None, ""):
            v = fm[k]
            if not isinstance(v, bool):
                P.bad(Y.get_ln(fm_lnmap, (k,), 0),
                      f"檔頭 `{k}` 要是 true／false（現在是 {v!r}）",
                      {"appendix": "appendix: false ＝ 這份報告不要附錄那一節（連目錄那一項一起不出現）",
                       "hints": "hints: false ＝ 不印圖表標題旁的互動提示小字（排序、滑過看數值照常可用）",
                       "conclusion_lead": "conclusion_lead: false ＝ 結論標題底下那行「紅＝漲、綠＝跌…」不印",
                       "conclusion_badge": "conclusion_badge: false ＝ 結論標題旁那顆「最重要」膠囊不印",
                       "conclusion_box": "conclusion_box: true ＝ 結論每一條各自一個灰底區塊"
                                         "（要先有 conclusion_style: list 或 numbered）"}[k])
            else:
                flags[k] = v
    R.show_appendix = flags.get("appendix", True)
    R.hints = flags.get("hints", True)
    R.conclusion_lead = flags.get("conclusion_lead", True)
    R.conclusion_badge = flags.get("conclusion_badge", True)
    R.conclusion_box = flags.get("conclusion_box", False)
    # v1.7：結論樣式（不寫＝card）。宣告才生效，值寫錯就擋下來、不默默吃掉。
    cstyle = fm.get("conclusion_style")
    if cstyle not in (None, ""):
        if not isinstance(cstyle, str) or cstyle.strip() not in CONCL_STYLE:
            P.bad(Y.get_ln(fm_lnmap, ("conclusion_style",), 0),
                  f"檔頭 `conclusion_style` 只能是 card（條狀卡片）、"
                  f"list（純條列）或 numbered（編號條列 1. 2. 3.）"
                  f"（現在是 {cstyle!r}）",
                  "conclusion_style: list ＝結論改成條列、可用 `　◦ ` 寫子項；"
                  "numbered ＝同一份條列改成 1. 2. 3. 編號（子項維持 ◦）；"
                  "要卡片就整行拿掉")
        else:
            R.conclusion_style = cstyle.strip()
    # v1.9：conclusion_box 是「條列的每一條各自一個區塊」，card 本來就是一張張卡片，
    # 兩個併用只會疊出卡片裡再包一個框。宣告錯了就擋下來、不默默吃掉。
    if R.conclusion_box and R.conclusion_style not in ("list", "numbered"):
        P.bad(Y.get_ln(fm_lnmap, ("conclusion_box",), 0),
              "檔頭 `conclusion_box: true` 要配 conclusion_style: list 或 numbered"
              f"（現在是 {R.conclusion_style}）",
              "card（預設）本來就是一條一張卡片，不需要再包一層區塊；"
              "要編號＋灰底區塊就寫 conclusion_style: numbered ＋ conclusion_box: true")
    for k, label in (("period", "資料時間區間"), ("population", "資料母體"),
                     ("source", "資料來源"), ("produced", "產出日期")):
        v = fmv(k)
        if v:
            R.meta(label, v)

    secs = P.split_secs(lines, start)
    names = [s[0] for s in secs]
    need = [k for k in REQUIRED_SECS if k != SEC_APP or R.show_appendix]
    miss = [k for k in need if k not in names]
    if miss:
        P.bad(0, f"少了這些區塊：{'、'.join('## ' + m for m in miss)}",
              "版型順序寫死在 rhtml.py：標題→前言→結論→建議→各章→附錄"
              + ("（真的不要附錄就在檔頭寫 appendix: false）" if SEC_APP in miss else ""))
    if not R.show_appendix and SEC_APP in names:
        P.bad([s[1] for s in secs if s[0] == SEC_APP][0],
              "檔頭寫了 appendix: false，卻還有一節 `## 附錄`",
              "二選一：把檔頭那行拿掉，或把 `## 附錄` 整節刪掉")

    for name, ln, body in secs:
        if name == SEC_PREFACE:
            box = _App()
            P.blocks_of(body, box)
            lede, rest = "", box.blocks
            if rest and isinstance(rest[0], Para):
                lede, rest = rest[0].text, rest[1:]
            else:
                P.bad(ln, f"「{SEC_PREFACE}」的第一段要是一段文字（會排成 lede）")
            R.preface(lede, rest)
        elif name == SEC_CONCL:
            P.conclusions(R, body)
        elif name == SEC_REC:
            P.recommends(R, body)
        elif name == SEC_APP:
            box = _App()
            P.blocks_of(body, box)
            R.appendix(box.blocks)
        elif name == SEC_VER:
            box = _App()
            P.blocks_of(body, box)
            R.version_note = box.blocks
        else:
            ch = R.chapter(name)
            P.blocks_of(body, ch)

    unused = [k for k in list(ctx.figs) + list(ctx.tbls) if k not in P.used]
    if unused:
        P.bad(ctx.decls[unused[0]]["open_ln"] if unused[0] in ctx.decls else 0,
              f"圖表 `{unused[0]}` 宣告了但沒有被放進任何章節",
              "```figure 區塊要放在章節或附錄底下，放哪圖就在哪")
    if P.problems:
        seen, uniq = set(), []
        for p in sorted(P.problems, key=lambda x: x[0]):
            if tuple(p[:3]) not in seen:
                seen.add(tuple(p[:3]))
                uniq.append(p)
        raise ContentError(path, uniq)
    R.value_doc = value_doc
    R.decl_keys = dict(figs=list(ctx.figs), tbls=list(ctx.tbls))
    return R


def keys_report(path):
    """給 build.py --keys：只跑到數字解析，印出可用的 {{v:key}} 與圖表 key。"""
    text = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
    lines = text.split("\n")
    md_dir = os.path.dirname(os.path.abspath(path))
    problems = []
    fm, fm_lnmap, start = front_matter(lines, problems)
    ctx = figures.collect(lines, start, md_dir, fm)
    values, value_doc = figures.resolve_values(fm, fm_lnmap, md_dir, ctx)
    return value_doc, [k for k, d in ctx.decls.items() if d["kind"] == "fig"], \
        [k for k, d in ctx.decls.items() if d["kind"] == "tbl"], problems + ctx.problems
