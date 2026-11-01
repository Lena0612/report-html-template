# -*- coding: utf-8 -*-
"""rhtml — 單檔 HTML 分析報告產生器（版型固定、風格可換、內容外掛）。

設計原則（下一步要包成 Claude Desktop skill，所以這裡不放任何案子內容）：

1. **內容與版型分離**：內容由呼叫端組 `Report` 物件（章節／圖／表／文字），
   本模組只負責產生 HTML 骨架、編號、錨點、目錄、JS。
   v3 起「文字內容」再往外搬一層：`content/報告內容.md` → `mdcontent.py`
   解析 → 組出 `Report` → 本模組排版。Lena 直接編那個 md。
2. **版型固定**：標題 → 前言 → 結論 → 建議 → 各章節 → 附錄。順序寫死在
   `Report.render()`，不由內容決定。
3. **風格用參數切換**：`render(theme="A"|"B"|"C")` 只換 `<style>` 與 `<body class>`，
   HTML 結構與文字完全相同（所以三份樣張可以用 diff 驗證只有外觀不同）。
4. **單檔自帶**：CSS inline、JS inline、圖片 base64 內嵌。零外部 CDN／零 JS 函式庫。

行內標記（mini markup，寫在任何文字欄位裡）
-------------------------------------------------
    [[key]]          → 圖表交叉引用超連結，label 自動產生（「圖 3-2」「表 2-1」）
                       （v3 e：只留「文中 → 圖表」的正向連結，
                        「↩ 回到引用處」整個功能移除）
    {{d:-4.7:分}}    → 變化量 chip：負→綠 ▼、正→紅 ▲（一律帶正負號與箭頭）
    {{n:39.1:分}}    → 中性數字（等寬數字、墨色）
    !!重點!!         → 重點紅字（一段最多一處，engine 會在 QA 時計數）
    **粗體**         → <strong>

紅綠語意（東亞金融慣例，與西方相反）
-------------------------------------------------
    紅 #c62828 ＝ 重點／「漲」    綠 #2e7d32 ＝「跌」
    顏色不是唯一線索：`{{d:...}}` 一律自動加 ▲／▼ 與正負號（色盲可讀）。
    紅綠只用在「方向語意」與「重點」上；類別序列一律中性藍／灰。
"""
import html as _html
import os
import re
import textwrap

RE_XREF = re.compile(r"\[\[([A-Za-z0-9_\-]+)\]\]")
RE_DELTA = re.compile(r"\{\{d:([^:}]+):([^}]*)\}\}")
RE_NUM = re.compile(r"\{\{n:([^:}]+):([^}]*)\}\}")
RE_HL = re.compile(r"!!(.+?)!!")
# 反引號 `...`：印成 <code>（等寬字），裡面的標記不展開（v3：之前會把反引號原樣印出來）
RE_CODE = re.compile(r"`([^`\n]+)`")
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
# v1.5：{{warn}} → 內嵌 SVG 紅色三角驚嘆號（取代紅色「!」；⚠ 是 emoji 會被 QA 16 擋）
RE_WARN = re.compile(r"\{\{warn\}\}")

ARROW_UP, ARROW_DOWN, ARROW_FLAT = "▲", "▼", "–"  # ▲ ▼ –

# 區塊標頭 icon（v3 g）：一律 inline SVG。
# 不用 emoji（跨平台字型不一致、列印可能掉字），也不引 icon 字型（會變成外部依賴）。
# currentColor + em 尺寸 → 跟著字級與風格色走，列印照樣印得出來。
_ICO = ('<span class="sec-ico"><svg viewBox="0 0 24 24" aria-hidden="true" '
        'focusable="false" fill="none" stroke="currentColor" '
        'stroke-width="2.1" stroke-linecap="round" '
        'stroke-linejoin="round">%s</svg></span>')
# 結論＝圈中打勾
ICON_CONCL = _ICO % ('<circle cx="12" cy="12" r="9.1"/>'
                     '<path d="M7.7 12.4l2.9 2.9 5.7-6.3"/>')
# 建議＝清單＋往右的箭頭（可執行的動作）
ICON_REC = _ICO % ('<path d="M3.6 6.6h9.6M3.6 12h9.6M3.6 17.4h6.4"/>'
                   '<path d="M15.4 17.4l3.9-3.9-3.9-3.9"/>')


def _ico_styled(ico, style):
    """給 icon 的外層 <span class="sec-ico"> 掛一段 inline style。
    v1.9 conclusion_badge: false 拿掉 sec-key 之後，用它把 .sec-key .sec-ico 的紅色補回來。
    沒人呼叫時 ICON_CONCL／ICON_REC 一個 byte 都不變。"""
    return ico.replace('<span class="sec-ico">',
                       '<span class="sec-ico" style="%s">' % style, 1)

# 警示 icon（v1.5，宣告 {{warn}} 才出現）：紅色三角驚嘆號，inline SVG。
# 不用 emoji（⚠ U+26A0 會被 qa_html 第 16 項擋掉）、不加 CSS（尺寸與顏色寫在標記上，
# 沿用 --up #c62828 的紅＝警示／重點語彙）；螢幕閱讀器讀得到後面的 .sr 文字。
ICON_WARN = (
    '<span class="warn-ico"><svg viewBox="0 0 24 24" width="1em" height="1em" '
    'style="vertical-align:-.14em" aria-hidden="true" focusable="false" '
    'fill="#c62828"><path d="M12 2.6 23 21.4H1z"/>'
    '<path d="M11.05 8.9h1.9v6.1h-1.9z" fill="#fff"/>'
    '<circle cx="12" cy="18.1" r="1.15" fill="#fff"/></svg></span>'
    '<span class="sr">警示</span>')

# 檢定顯著底色（v1.5 第 1 項）：中性藍的亮度階（比照 cohort／顯著度熱圖的單色思路），
# 不用紅綠（紅綠已被漲跌佔走，會撞 qa 第 10 項）。走 inline style 不加 CSS；
# print-color-adjust 讓列印／轉 PDF 時底色不被瀏覽器省略。
#
# v1.6 第 1 項：深淺三階。同一個色相（--cat1 #2f6f9f 兌白），只動明度，
# 三階的 CIE L* 是 89.6 / 79.4 / 69.5——每階差約 10 個 L*，加上白底恰好四級等距，
# 灰階列印（Rec.709 luma 225 / 196 / 169，相鄰對比 1.33／1.35）也分得出來。
# 刻意不做連續漸層、不做四階以上：白底再切四階，每階只剩 8 個 L*，列印就糊在一起。
# 第 1 階就是 v1.5 的 #d7e3ee：沒宣告強度值時走同一個字串，輸出逐 byte 不變。
SIG_SHADE = {1: "#d7e3ee", 2: "#b0c8db", 3: "#8baec9"}


def _sig_bg(c):
    return ("background:%s;-webkit-print-color-adjust:exact;"
            "print-color-adjust:exact" % c)


SIG_BG = _sig_bg(SIG_SHADE[1])
SIG_DIR = {"lr": "左右", "tb": "上下"}
SIG_NOTE = "底色著色為經統計檢定有顯著差異，方向為%s著色"
# 列群組粗框（v1.5 第 5 項）：沿用 --line 色票，只加粗不換色。
RG_TOP = "border-top:2px solid var(--line)"
RG_BOT = "border-bottom:2px solid var(--line)"
# v1.9 第 2 項：欄位群直向粗框（```table 的 col_groups）。跟 row_groups 同色票、同 2px，
# 只畫「群與群之間」那幾條——欄向本來一條直線都沒有，最右邊再收一條會變成沒有左緣的半框
# （Lena 2026-09-17 第 8 點的草圖也只在群之間畫 ｜）。沒宣告時完全不進這條路徑。
CG_LEFT = "border-left:2px solid var(--line)"
# v1.9 第 3 項：結論每一條各自一個區塊（檔頭 conclusion_box: true）。CSS 凍結，所以走
# inline style（與 v1.5 檢定底色、v1.8 事件線紅色同一個做法）。灰底＝預設；標了 [up]
# （漲／重點）的那一條才是紅底紅字——沿用 .theme-b .concl-i.tone-up 既有的 tone 語意，
# 不另外發明一套標記。
_CB = "border-radius:12px;padding:12px 16px;margin:0 0 10px"
CONCL_BOX = "background:var(--panel);border:1px solid var(--line);" + _CB
CONCL_BOX_UP = "background:var(--up-bg);border:1px solid var(--up);color:var(--up);" + _CB
# v1.9 第 1 項的一半：conclusion_badge: false ＝拿掉 .theme-b .sec-key .sec-h::after
# 那顆「最重要」膠囊。::after 的 content 沒辦法被 inline style 蓋掉、CSS 又凍結，
# 唯一的路是不要掛 sec-key 這個 class；.sec-key 另外帶的兩條宣告（4px 紅上框、白底）
# 與 icon 的紅色用 inline style 原樣補回來，所以除了那顆膠囊，最終生效值一項都不變。
SECKEY_INLINE = "border-top:4px solid var(--up);background:#fff"
SECICO_UP = "color:var(--up)"


def esc(s):
    return _html.escape(str(s), quote=True)


# --------------------------------------------------------------------------
# 內容元件（純資料，不含 HTML）
# --------------------------------------------------------------------------
class Item:
    """圖或表。kind = 'fig' | 'tbl'。編號在 render 時由 Report 指派。"""

    def __init__(self, kind, key, title, note, reading=None, defs=None):
        self.kind = kind
        self.key = key
        self.title = title
        self.note = note          # 母體／口徑／n（9.2 規矩：缺一不可）
        self.reading = reading    # 判讀
        self.defs = defs or []    # [(標籤, 說明)]：維度定義／指標定義／著色含義
        self.no = None            # 例：'3-2'
        self.ch = None

    @property
    def label(self):
        head = "圖" if self.kind == "fig" else "表"   # 圖 / 表
        return f"{head} {self.no}"

    @property
    def anchor(self):
        return f"{self.kind}-{self.key}"


class Figure(Item):
    """svg：完整的 inline SVG 標記字串（見 svgchart.py）。靜態即完整，
    互動由 JS 加在既有標記上。"""

    def __init__(self, key, title, svg, note, reading=None, alt=None,
                 defs=None):
        super().__init__("fig", key, title, note, reading, defs)
        self.svg = svg
        self.alt = alt or title


class Table(Item):
    def __init__(self, key, title, headers, rows, note, reading=None,
                 aligns=None, emph_rows=(), sortable=True, col_types=None,
                 defs=None, rowspan=(), row_groups=(), sig=None,
                 col_groups=()):
        """rows 的每個 cell 可為 str，或 (顯示字串, 排序值) tuple。

        v1.5 三個選用參數（不給＝與 v1.4 逐 byte 相同）：
          rowspan    [欄索引…]（0 起）：這些欄相鄰同值的列真的合併成一格
          row_groups [每群列數…]：群與群之間畫一條粗線
        v1.9 一個選用參數（不給＝與 v1.8 逐 byte 相同）：
          col_groups [每群欄數…]：欄群與欄群之間畫一條直的粗線（只畫中間、不收右緣）。
                     與列無關，所以**不會**像 rowspan／row_groups 那樣自動關掉排序。
          sig        {"dir": "lr"|"tb", "cells": {(列,欄): None｜(第幾階, 強度值字串)},
                     "mark": "both"|"max", "scale": 統計量名稱}：檢定顯著格的底色。
                     cells 的鍵＝要上色的格（mark: max 時一組配對只會有一格進來）；
                     值＝None 走單一階（v1.5 行為），給 (階, 值) 就上對應深淺（v1.6）。
                     兩者正交，可併用。傳 set 亦可＝全部單一階
        """
        super().__init__("tbl", key, title, note, reading, defs)
        self.headers = headers
        self.rows = rows
        self.aligns = aligns or (["left"] + ["right"] * (len(headers) - 1))
        self.emph_rows = set(emph_rows)
        self.sortable = sortable
        self.col_types = col_types or (["text"] + ["num"] * (len(headers) - 1))
        self.rowspan = list(rowspan or ())
        self.row_groups = list(row_groups or ())
        self.col_groups = list(col_groups or ())
        self.sig = sig or None


class Sub:
    """子節標頭（H3）。字級階層：H1 報告標題 > H2 區塊 > H3 子節。"""

    def __init__(self, title):
        self.title = title


class Para:
    def __init__(self, text, cls=""):
        self.text, self.cls = text, cls


class Bullets:
    def __init__(self, items, cls=""):
        self.items, self.cls = items, cls


class Details:
    def __init__(self, summary, blocks):
        self.summary, self.blocks = summary, blocks


class Chapter:
    def __init__(self, title, subtitle=None, takeaway=None):
        self.title = title
        self.subtitle = subtitle
        self.takeaway = takeaway      # 本章結論：小標之後、說明文字之前
        self.blocks = []
        self.no = None

    # -- 內容 API（呼叫端只用這幾個） --
    def para(self, text, cls=""):
        self.blocks.append(Para(text, cls)); return self

    def sub(self, title):
        self.blocks.append(Sub(title)); return self

    def bullets(self, items, cls=""):
        self.blocks.append(Bullets(items, cls)); return self

    def figure(self, *a, **k):
        it = Figure(*a, **k); self.blocks.append(it); return it

    def table(self, *a, **k):
        it = Table(*a, **k); self.blocks.append(it); return it

    def details(self, summary, blocks):
        self.blocks.append(Details(summary, blocks)); return self


# --------------------------------------------------------------------------
# 報告
# --------------------------------------------------------------------------
class Report:
    def __init__(self, title, subtitle, produced, project=None,
                 kicker=None, watermark=None, version_note=None):
        self.title = title
        self.subtitle = subtitle          # 副標（與標題、前言同一區塊）
        self.produced = produced
        self.project = project
        self.kicker = kicker or ""
        self.watermark = watermark        # 例：示意假資料・不可引用
        self.version_note = version_note  # 本版說明（樣張用，可為 None）
        self.meta_rows = []
        self.preface_lede = ""
        self.preface_blocks = []
        self.conclusions = []             # [(text, tone)]
        # v1.7 第 2 項：結論的呈現方式。"card"＝條狀卡片（v1～v1.6 預設，輸出逐 byte 不變）；
        # "list"＝純條列（<ul class="bul">，可有一層 ◦ 子項）。只有檔頭宣告才會切換。
        self.conclusion_style = "card"
        self.concl_subs = {}              # 第 i 條（0 起）→ [子項文字…]，只有 list 模式用
        # v1.9 結論區三個開關（預設值＝v1.8 行為；只有檔頭宣告才會切換）
        self.conclusion_lead = True       # 「紅＝漲、綠＝跌，▲▼ 與正負號同步。」那行小字
        self.conclusion_badge = True      # 區塊標題右邊那顆「最重要」膠囊（CSS ::after）
        self.conclusion_box = False       # 每一條結論各自一個灰底區塊（list／numbered 才有意義）
        self.recommendations = []         # [dict(action, impact, owner, tag)]
        self.chapters = []
        self.appendix_blocks = []
        # v1.5 三個開關（預設值＝v1.4 行為）
        self.hints = True                 # 圖表標題旁的互動提示小字（關掉不影響排序）
        self.show_appendix = True         # 附錄整節（含目錄那一項）
        self.concl_pre = []               # 結論：卡片清單「之前」的圖表區塊
        self.concl_post = []              # 結論：卡片清單「之後」的圖表區塊
        self._items = {}                  # key -> Item
        self._xrefs = {}                  # key -> 被引用次數（QA 用）

    # ---- 內容 API ----
    def meta(self, k, v):
        self.meta_rows.append((k, v)); return self

    def preface(self, lede, blocks):
        self.preface_lede = lede
        self.preface_blocks = blocks
        return self

    def conclusion(self, text, tone=""):
        self.conclusions.append((text, tone)); return self

    def conclusion_sub(self, text):
        """list 模式的 ◦ 子項：掛在最後一條結論底下。"""
        self.concl_subs.setdefault(len(self.conclusions) - 1, []).append(text)
        return self

    def recommend(self, action, impact, tag=""):
        self.recommendations.append(dict(action=action, impact=impact, tag=tag))
        return self

    def chapter(self, title, subtitle=None, takeaway=None):
        ch = Chapter(title, subtitle, takeaway)
        self.chapters.append(ch)
        return ch

    def appendix(self, blocks):
        self.appendix_blocks = blocks; return self

    # ---- 編號：走訪一次，指派 圖 c-i / 表 c-j ----
    def _number(self):
        self._items.clear()

        def walk(blocks, ch_no, counters):
            for b in blocks:
                if isinstance(b, Item):
                    counters[b.kind] += 1
                    b.ch = ch_no
                    b.no = f"{ch_no}-{counters[b.kind]}"
                    if b.key in self._items:
                        raise ValueError(f"圖表 key 重複：{b.key}")
                    self._items[b.key] = b
                elif isinstance(b, Details):
                    walk(b.blocks, ch_no, counters)

        # 結論區塊裡的圖表（v1.5 第 8 項）：編號 C-1、C-2（C＝Conclusion，
        # 比照附錄的 A；不佔用章節的 1-1，讀者一眼知道它在結論不在第 1 章）
        cc = {"fig": 0, "tbl": 0}
        walk(self.concl_pre, "C", cc)
        walk(self.concl_post, "C", cc)
        for i, ch in enumerate(self.chapters, 1):
            ch.no = i
            walk(ch.blocks, i, {"fig": 0, "tbl": 0})
        # 附錄的圖表編號用 A-1 / A-2
        walk(self.appendix_blocks, "A", {"fig": 0, "tbl": 0})

    # ---- 行內標記展開 ----
    def _inline(self, text, ctx="body"):
        s = esc(text)
        # 先把 `...` 抽成佔位符，避免裡面的 {{n:..}}／**／!! 被下面的規則展開；最後再放回
        codes = []

        def keep(m):
            codes.append(f"<code>{m.group(1)}</code>")
            return f"\x00{len(codes) - 1}\x00"
        s = RE_CODE.sub(keep, s)

        def xref(m):
            key = m.group(1)
            it = self._items.get(key)
            if it is None:
                raise KeyError(f"[[{key}]] 找不到對應的圖表")
            self._xrefs[key] = self._xrefs.get(key, 0) + 1
            return (f'<a class="xref" href="#{it.anchor}" '
                    f'title="跳到{esc(it.label)}：'
                    f'{esc(it.title)}">{esc(it.label)}</a>')

        def delta(m):
            raw, unit = m.group(1).strip(), m.group(2).strip()
            first = raw[0]
            if first == "+":
                cls, arrow = "up", ARROW_UP
            elif first == "-":
                cls, arrow = "dn", ARROW_DOWN
            else:
                cls, arrow = "flat", ARROW_FLAT
            unit_html = f'<span class="chg-u">{esc(unit)}</span>' if unit else ""
            sr = "上升" if cls == "up" else (
                "下降" if cls == "dn" else "持平")
            return (f'<span class="chg {cls}" data-v="{esc(raw)}">'
                    f'<span class="chg-a" aria-hidden="true">{arrow}</span>'
                    f'<span class="sr">{sr}</span>'
                    f'<span class="chg-n">{esc(raw)}</span>{unit_html}</span>')

        def num(m):
            v, unit = m.group(1).strip(), m.group(2).strip()
            u = f'<span class="chg-u">{esc(unit)}</span>' if unit else ""
            return f'<span class="num" data-v="{esc(v)}">{esc(v)}{u}</span>'

        s = RE_XREF.sub(xref, s)
        s = RE_DELTA.sub(delta, s)
        s = RE_NUM.sub(num, s)
        s = RE_WARN.sub(lambda m: ICON_WARN, s)
        s = RE_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
        s = RE_HL.sub(lambda m: f'<span class="hl">{m.group(1)}</span>', s)
        for i, c in enumerate(codes):
            s = s.replace(f"\x00{i}\x00", c)
        return s

    # ---- 區塊渲染 ----
    def _render_blocks(self, blocks, ind=6):
        out = []
        for b in blocks:
            if isinstance(b, Sub):
                out.append(f'<h3 class="sub-h">{self._inline(b.title)}</h3>')
            elif isinstance(b, Para):
                cls = f' class="{b.cls}"' if b.cls else ""
                out.append(f"<p{cls}>{self._inline(b.text)}</p>")
            elif isinstance(b, Bullets):
                cls = f' class="bul {b.cls}"' if b.cls else ' class="bul"'
                lis = "".join(f"<li>{self._inline(x)}</li>" for x in b.items)
                out.append(f"<ul{cls}>{lis}</ul>")
            elif isinstance(b, Figure):
                out.append(self._render_figure(b))
            elif isinstance(b, Table):
                out.append(self._render_table(b))
            elif isinstance(b, Details):
                inner = self._render_blocks(b.blocks, ind + 2)
                out.append(
                    '<details class="fold">'
                    f'<summary>{self._inline(b.summary)}</summary>'
                    f'<div class="fold-b">{inner}</div></details>')
            else:
                raise TypeError(f"未知區塊：{type(b)}")
        pad = " " * ind
        return ("\n" + pad).join(out)

    def _defs(self, it):
        """備註三類資訊：維度定義／指標定義／著色含義（排版克制，一行一類）。"""
        if not it.defs:
            return ""
        rows = "".join(
            f'<div class="def-r"><dt>{esc(k)}</dt>'
            f"<dd>{self._inline(v)}</dd></div>" for k, v in it.defs)
        return f'        <dl class="blk-def">{rows}</dl>\n'

    def _render_figure(self, f):
        return (
            f'<figure class="blk fig" id="{f.anchor}">\n'
            f'        <figcaption class="cap">'
            f'<span class="cap-no">{esc(f.label)}</span>'
            f'<span class="cap-t">{self._inline(f.title)}</span>'
            + ('<span class="tbl-hint">可互動：滑過看數值</span>'
               if self.hints else "")
            + '</figcaption>\n'
            + f'        <div class="fig-img" tabindex="0">{f.svg}'
            + ('<span class="scroll-hint">窄螢幕可左右捲動看完整張圖</span>'
               if self.hints else "")
            + '</div>\n'
            + self._defs(f)
            # v1.9：檔頭沒寫 note_base 又沒有 note／note_extra 時，母體註腳整塊不渲染
            # （不是留一個空的 <p class="blk-note">）。有內容時輸出與 v1.8 逐 byte 相同。
            + (f'        <p class="blk-note">{self._inline(f.note)}</p>\n'
               if (f.note or "").strip() else "")
            + (f'        <p class="blk-read"><span class="read-k">'
               f'判讀</span>{self._inline(f.reading)}</p>\n'
               if f.reading else "")
            + "      </figure>")

    @staticmethod
    def _spans(t):
        """v1.5 第 4 項：算 rowspan。t.rowspan 列的欄（0 起）把相鄰同值的列合併；
        後一欄的合併不會跨過前一欄的分界（階層式，第 2 層不會併到第 1 層之外）。
        回傳 ({(列, 欄): 合併列數}, {被吃掉的 (列, 欄)})。"""
        span, skip = {}, set()
        nrow = len(t.rows)

        def disp(r, i):
            row = t.rows[r]
            c = row[i] if i < len(row) else ""
            return c[0] if isinstance(c, (tuple, list)) else c
        edge = [True] + [False] * (nrow - 1)      # 上層欄的分界
        for ci in t.rowspan:
            starts, r = [], 0
            while r < nrow:
                starts.append(r)
                v = str(disp(r, ci))
                e = r + 1
                if v.strip():
                    while e < nrow and not edge[e] and str(disp(e, ci)) == v:
                        e += 1
                if e - r > 1:
                    span[(r, ci)] = e - r
                    for k in range(r + 1, e):
                        skip.add((k, ci))
                r = e
            for r in starts:
                edge[r] = True
        return span, skip

    def _render_table(self, t):
        # v1.9：欄位群直向粗框。cg＝「這一欄的左邊要畫一條 2px」的欄索引集合，
        # 只收群與群之間的邊界（第一欄不畫、最後一欄右邊也不收）。沒宣告＝空集合，
        # 底下兩個迴圈都不會多吐一個字元，輸出與 v1.8 逐 byte 相同。
        cg = set()
        if t.col_groups:
            at = 0
            for g in t.col_groups:
                if at:
                    cg.add(at)
                at += g
        ths = []
        for i, h in enumerate(t.headers):
            typ = t.col_types[i] if i < len(t.col_types) else "text"
            al = t.aligns[i] if i < len(t.aligns) else "left"
            srt = (' class="s" tabindex="0" role="button" aria-sort="none"'
                   if t.sortable else "")
            ind = ('<span class="sort-ind" aria-hidden="true"></span>'
                   if t.sortable else "")
            cst = f' style="{CG_LEFT}"' if i in cg else ""
            ths.append(f'<th data-type="{typ}" data-al="{al}"{srt}{cst}>'
                       f'<span class="th-t">{self._inline(h)}</span>{ind}</th>')
        span, skip = self._spans(t) if t.rowspan else ({}, set())
        gstart, last = set(), len(t.rows) - 1
        if t.row_groups:
            at = 0
            for g in t.row_groups:
                if at:
                    gstart.add(at)
                at += g
        sig = t.sig or {}
        sigcells = sig.get("cells") or {}
        if not isinstance(sigcells, dict):        # 舊呼叫端給 set：全部當單一階
            sigcells = {k: None for k in sigcells}
        sigwhat = SIG_DIR.get(sig.get("dir"), "上下")
        # v1.6：mark: max 時這一格的語意是「配對中數值較大的一格」，tooltip 要跟著改口；
        # 深淺階的 tooltip 也接在同一句後面，兩種宣告併用時不會出現兩句矛盾的說明。
        sigbase = ("經統計檢定有顯著差異，此格為%s配對中數值較大的一格"
                   if sig.get("mark") == "max" else
                   "經統計檢定有顯著差異（與%s配對的另一格比較）") % sigwhat
        sigtip = esc(sigbase)
        sigscale = sig.get("scale") or "檢定強度"
        trs = []
        for r, row in enumerate(t.rows):
            tds = []
            for i, cell in enumerate(row):
                if (r, i) in skip:
                    continue
                al = t.aligns[i] if i < len(t.aligns) else "left"
                if isinstance(cell, (tuple, list)):
                    disp, sv = cell[0], cell[1]
                    dv = f' data-v="{esc(sv)}"'
                else:
                    disp, dv = cell, ""
                tag = "th" if i == 0 else "td"
                sc = ' scope="row"' if i == 0 else ""
                rs = span.get((r, i))
                if rs:
                    dv += f' rowspan="{rs}"'
                    if i == 0:
                        sc = ' scope="rowgroup"'
                # 一個格子最多只能有一個 style 屬性：檢定底色（v1.5／v1.6）與欄群
                # 粗框（v1.9）都往 cs 裡疊，最後一次吐出來。只有底色時字串與 v1.8 相同。
                cs = []
                if (r, i) in sigcells:
                    mk = sigcells[(r, i)]
                    if mk is None:                # 單一階：與 v1.5 逐 byte 相同
                        dv += f' data-sig="1" title="{sigtip}"'
                        cs.append(SIG_BG)
                    else:                         # v1.6 深淺階：值與階數進 title，色盲／灰階都讀得到
                        lv, vs = mk
                        tip = esc("%s｜%s＝%s（第 %d 階／共 %d 階，越深證據越強）"
                                  % (sigbase, sigscale, vs, lv, len(SIG_SHADE)))
                        dv += f' data-sig="1" data-sig-lv="{lv}" title="{tip}"'
                        cs.append(_sig_bg(SIG_SHADE[lv]))
                if i in cg:
                    cs.append(CG_LEFT)
                if cs:
                    dv += f' style="{";".join(cs)}"'
                tds.append(f'<{tag}{sc} data-al="{al}"{dv}>'
                           f"{self._inline(disp)}</{tag}>")
            cls = ' class="emph"' if r in t.emph_rows else ""
            st = []
            if r in gstart:
                st.append(RG_TOP)
            if t.row_groups and r == last:
                st.append(RG_BOT)
            stl = f' style="{";".join(st)}"' if st else ""
            trs.append(f'<tr{cls}{stl}>{"".join(tds)}</tr>')
        sc = ' sortable' if t.sortable else ''
        fix = (' data-fixed="1"'
               if (t.rowspan or t.row_groups or sig.get("dir") == "tb") else '')
        hint = ('<span class="tbl-hint">點欄位可排序'
                '（點第三次回原順）</span>'
                if t.sortable and self.hints else "")
        return (
            f'<div class="blk tbl" id="{t.anchor}">\n'
            f'        <div class="cap"><span class="cap-no">{esc(t.label)}</span>'
            f'<span class="cap-t">{self._inline(t.title)}</span>{hint}</div>\n'
            f'        <div class="tablewrap" tabindex="0">'
            f'<table class="data{sc}"{fix}>\n'
            f"          <thead><tr>{''.join(ths)}</tr></thead>\n"
            f"          <tbody>{''.join(trs)}</tbody>\n"
            f"        </table></div>\n"
            + self._defs(t)
            # v1.9：檔頭沒寫 note_base 又沒有 note／note_extra 時，母體註腳整塊不渲染
            # （不是留一個空的 <p class="blk-note">）。有內容時輸出與 v1.8 逐 byte 相同。
            + (f'        <p class="blk-note">{self._inline(t.note)}</p>\n'
               if (t.note or "").strip() else "")
            + (f'        <p class="blk-read"><span class="read-k">'
               f'判讀</span>{self._inline(t.reading)}</p>\n'
               if t.reading else "")
            + "      </div>")

    # ---- 目錄 ----
    def _toc(self):
        secs = [("sec-top", "前言"),
                ("sec-concl", "結論"),
                ("sec-rec", "建議")]
        for ch in self.chapters:
            secs.append((f"sec-ch{ch.no}", f"{ch.no}. {ch.title}"))
        if self.show_appendix:                    # v1.5 第 2 項：關掉就不留空項
            secs.append(("sec-appendix", "附錄｜方法與 caveat"))
        # v3 d：只列各區塊的標頭，圖表清單整個拿掉。
        li = [f'<li><a class="toc-link toc-l1" href="#{sid}">'
              f"{esc(name)}</a></li>" for sid, name in secs]
        return "\n        ".join(li)

    # ---- 主渲染 ----
    def render(self, theme, theme_label=""):
        """單趟渲染（v3：「↩ 回到引用處」移除後，不必先跑一趟收集引用點）。
        `_xrefs` 只留「每個 key 被引用幾次」，給 QA 檢查每張圖表都有被引用。"""
        from themes import build_css
        self._number()
        self._xrefs.clear()
        body = self._body(theme_label)
        toc = self._toc()
        css = build_css(theme)
        title_txt = re.sub(r"\{\{[^}]*\}\}|\[\[|\]\]|!!|\*\*", "", self.title)
        return TEMPLATE.format(
            title=esc(title_txt), css=css, toc=toc, body=body,
            theme=theme.lower(), js=JS, skip="跳到主內容",
            pagemark=esc(self.watermark or ""))

    def _body(self, theme_label=""):
        body_parts = []
        A = body_parts.append

        # 1 標題＋副標＋前言（同一區塊）→ 資料說明（淡字縮小）
        wm = (f'<p class="watermark">{esc(self.watermark)}</p>'
              if self.watermark else "")
        dnote = ""
        if self.meta_rows:
            sep = '<span class="dn-sep" aria-hidden="true">｜</span>'
            dnote = ('<p class="datanote">' + sep.join(
                f'<span class="dn-i"><span class="dn-k">{esc(k)}：</span>'
                f'<span class="dn-v">{self._inline(v)}</span></span>'
                for k, v in self.meta_rows) + "</p>")
        vnote = ""
        if self.version_note:
            vnote = ('<details class="verinfo"><summary>'
                     '本版說明（樣張用，'
                     '實際報告可移除）</summary>'
                     f'<div class="verinfo-b">'
                     f"{self._render_blocks(self.version_note, 8)}</div></details>")
        # v1.9 第 1 項：副標沒填就**整行不渲染**（不是印空字串、不是留一個空 <p>）。
        # 有填的時候後面補回原本的換行與縮排，輸出與 v1.8 逐 byte 相同。
        sub = (f'<p class="subtitle">{esc(self.subtitle)}</p>\n      '
               if self.subtitle else "")
        A(f"""  <header class="head" id="sec-top" data-nav="1">
      {wm}
      <p class="kicker">{esc(self.kicker)}</p>
      <h1 class="title">{self._inline(self.title)}</h1>
      {sub}<p class="lede">{self._inline(self.preface_lede)}</p>
      {self._render_blocks(self.preface_blocks)}
      {dnote}
      <p class="stylebadge">{esc(theme_label)}</p>
      {vnote}
    </header>""")

        # 3 結論（全篇最顯眼）
        cli = []
        for i, (text, tone) in enumerate(self.conclusions, 1):
            tc = f" tone-{tone}" if tone else ""
            cli.append(f'<li class="concl-i{tc}">'
                       f'<span class="concl-n">{i}</span>'
                       f'<span class="concl-b">{self._inline(text)}</span></li>')
        # v1.7：條列模式——同樣一批文字改用 <ul class="bul">（正文清單的既有樣式），
        # ◦ 子項排成巢狀清單。tone 只寫進 class，條列沒有卡片上緣色條可以上色。
        # v1.8：numbered＝外層換成 <ol class="bul concl-list">（.bul 沒有 list-style:none，
        # 所以瀏覽器直接排 1. 2. 3.，CSS 一個 byte 都不用改）。<ul> 巢在 <ol> 裡時
        # UA 預設會退回 disc，所以子項補一個 inline list-style-type:circle 把 ◦ 釘住
        # ——「小項目維持不變」。list 模式的輸出與 v1.7 逐 byte 相同。
        numbered = self.conclusion_style == "numbered"
        if self.conclusion_style in ("list", "numbered"):
            sub_open = ('<ul class="bul concl-sub" style="list-style-type:circle">'
                        if numbered else '<ul class="bul concl-sub">')
            cli = []
            for i, (text, tone) in enumerate(self.conclusions):
                tc = f' class="tone-{tone}"' if tone else ""
                subs = self.concl_subs.get(i) or []
                inner = (sub_open
                         + "".join(f"<li>{self._inline(x)}</li>" for x in subs)
                         + "</ul>") if subs else ""
                # v1.9：conclusion_box: true → 每一條各自一個區塊。灰底是預設，
                # 標了 [up] 的那一條才紅底紅字（tone 的既有語意，不另外發明標記）。
                bx = ""
                if self.conclusion_box:
                    bx = ' style="%s"' % (CONCL_BOX_UP if tone == "up"
                                          else CONCL_BOX)
                cli.append(f"<li{tc}{bx}>{self._inline(text)}{inner}</li>")
        # v1.5 第 8 項：結論除了條狀卡片，還可以放 ```table／```figure 區塊。
        # 卡片仍是預設；區塊宣告在第一張卡片之前就排在卡片上方，否則排在下方。
        cpre = ("\n      " + self._render_blocks(self.concl_pre)
                if self.concl_pre else "")
        cpost = ("\n      " + self._render_blocks(self.concl_post)
                 if self.concl_post else "")
        # v1.9 第 1 項的另一半 ＋ 第 4 點：
        #   conclusion_badge: false → 不掛 sec-key（唯一能讓 ::after「最重要」不渲染的路），
        #                             .sec-key 原本那兩條宣告與 icon 的紅色用 inline 補回來
        #   conclusion_lead:  false → 「紅＝漲、綠＝跌…」那行連同它那一行一起不出現
        # 兩個都不宣告時，下面三個字串與 v1.8 的模板逐 byte 相同。
        if self.conclusion_badge:
            sec_open = '<section class="sec sec-key" id="sec-concl" data-nav="1">'
            icon = ICON_CONCL
        else:
            sec_open = ('<section class="sec" id="sec-concl" data-nav="1"'
                        ' style="%s">' % SECKEY_INLINE)
            icon = _ico_styled(ICON_CONCL, SECICO_UP)
        lead = ('\n      <p class="sec-lead">紅＝漲、綠＝跌，▲▼ 與正負號同步。</p>'
                if self.conclusion_lead else "")
        A("""  %s
      <h2 class="sec-h"><span class="ch-num"></span>%s<span class="sec-t">結論</span></h2>%s%s
      %s
        %s
      %s%s
    </section>""" % (sec_open, icon, lead, cpre,
                     '<ol class="bul concl-list">' if numbered
                     else '<ul class="bul concl-list">'
                     if self.conclusion_style == "list" else '<ol class="concl">',
                     "\n        ".join(cli),
                     "</ul>" if self.conclusion_style == "list" else "</ol>",
                     cpost))

        # 4 建議
        rli = []
        for i, r in enumerate(self.recommendations, 1):
            tag = (f'<span class="rec-tag">{esc(r["tag"])}</span>'
                   if r["tag"] else "")
            rli.append(
                f'<li class="rec-i"><div class="rec-h">'
                f'<span class="rec-n">{i}</span>'
                f'<span class="rec-a">{self._inline(r["action"])}</span>{tag}</div>'
                f'<div class="rec-m">'
                f'<div class="rec-kv"><span class="rec-k">預期影響</span>'
                f'<span class="rec-v">{self._inline(r["impact"])}</span></div>'
                f"</div></li>")
        A("""  <section class="sec" id="sec-rec" data-nav="1">
      <h2 class="sec-h"><span class="ch-num"></span>%s<span class="sec-t">建議</span></h2>
      <ol class="rec">
        %s
      </ol>
    </section>""" % (ICON_REC, "\n        ".join(rli)))

        # 5 各章節
        for ch in self.chapters:
            key = (f'<p class="ch-key"><span class="ch-key-k">本章結論</span>'
                   f'<span class="ch-key-b">{self._inline(ch.takeaway)}</span></p>'
                   if ch.takeaway else "")
            sub = (f'<p class="sec-lead">{self._inline(ch.subtitle)}</p>'
                   if ch.subtitle else "")
            A(f"""  <section class="sec sec-ch" id="sec-ch{ch.no}" data-nav="1">
      <h2 class="sec-h"><span class="ch-num">{ch.no}</span><span class="sec-t">{self._inline(ch.title)}</span></h2>
      {key}
      {sub}
      {self._render_blocks(ch.blocks)}
    </section>""")

        # 附錄（v1.5 第 2 項：檔頭 appendix: false 就整節不出現，標題也不留）
        if self.show_appendix:
            A(f"""  <section class="sec sec-app" id="sec-appendix" data-nav="1">
      <h2 class="sec-h"><span class="ch-num"></span><span class="sec-t">附錄｜方法、口徑與 caveat</span></h2>
      {self._render_blocks(self.appendix_blocks)}
    </section>""")

        return "\n".join(body_parts)

    # ---- QA 用 ----
    def xref_count(self):
        return sum(self._xrefs.values())

    def items(self):
        return dict(self._items)


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body class="theme-{theme}">
<a class="skip" href="#sec-top">{skip}</a>
<div class="pagemark" aria-hidden="true">{pagemark}</div>
<nav id="toc" class="toc" aria-label="目錄">
  <button class="toc-btn" id="tocbtn" type="button" aria-expanded="false"
          aria-controls="tocpanel" title="目錄（滑過或點一下展開）">
    <span class="toc-ico" aria-hidden="true"><i></i><i></i><i></i></span>
    <span class="sr">目錄</span>
  </button>
  <div class="toc-panel" id="tocpanel">
    <div class="toc-card">
      <div class="toc-hd"><span class="toc-h">目錄</span><span class="toc-hint">點標題可跳轉</span></div>
      <div class="toc-body">
      <ol class="toc-list">
        {toc}
      </ol>
      <p class="toc-foot">「圖 1-1」「表 2-1」都是超連結，點了跳到該圖表。</p>
      </div>
    </div>
  </div>
</nav>
<div class="shell">
  <main class="doc" id="doc">
{body}
    <footer class="foot">
      <p class="foot-t">單檔自帶 HTML（CSS／JS／圖表內嵌），離線可開、可直接列印或轉 PDF。</p>
    </footer>
  </main>
</div>
<script>
{js}
</script>
</body>
</html>
"""

# --------------------------------------------------------------------------
# 原生 JS：scroll-spy／雙向引用／表格排序／目錄摺疊／列印前展開
# 全部手寫，無任何外部函式庫。
# --------------------------------------------------------------------------
JS = textwrap.dedent(r"""
(function () {
  'use strict';

  /* ---------- 1. 浮動目錄 scroll-spy ---------- */
  var links = [].slice.call(document.querySelectorAll('.toc-link.toc-l1'));
  var secs = links.map(function (a) {
    return document.querySelector(a.getAttribute('href'));
  });
  var ticking = false;
  function spy() {
    ticking = false;
    var probe = Math.max(90, window.innerHeight * 0.18);
    var cur = 0;
    for (var i = 0; i < secs.length; i++) {
      if (!secs[i]) { continue; }
      if (secs[i].getBoundingClientRect().top - probe <= 0) { cur = i; }
    }
    /* 捲到底時強制高亮最後一節 */
    if (window.innerHeight + window.scrollY >=
        document.body.scrollHeight - 4) { cur = secs.length - 1; }
    for (var j = 0; j < links.length; j++) {
      var on = (j === cur);
      links[j].classList.toggle('is-cur', on);
      if (on) { links[j].setAttribute('aria-current', 'true'); }
      else { links[j].removeAttribute('aria-current'); }
    }
    var box = document.querySelector('.toc-body');
    var act = links[cur];
    if (box && act && box.scrollHeight > box.clientHeight + 8) {
      var br = box.getBoundingClientRect(), ar = act.getBoundingClientRect();
      if (ar.top < br.top + 8 || ar.bottom > br.bottom - 8) {
        box.scrollTop += (ar.top - br.top) - br.height * 0.35;
      }
    }
  }
  function onScroll() {
    if (!ticking) { ticking = true; requestAnimationFrame(spy); }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  window.addEventListener('hashchange', onScroll);

  /* ---------- 2.（v3 e）圖表引用只留正向連結 ---------- */
  /* 文中「圖 3-1」是純 <a href="#fig-...">，跳轉交給瀏覽器，不需要 JS。 */

  /* ---------- 3. 表格排序（原生，三態：升→降→原順序） ---------- */
  function parseVal(td, type) {
    var raw = td.getAttribute('data-v');
    var s = (raw !== null ? raw : td.textContent) || '';
    s = s.replace(/　/g, ' ').trim();
    if (type === 'num') {
      if (/^(N\/A|—|-|–|\s*)$/.test(s)) { return null; }
      var t = s.replace(/,/g, '').replace(/[^0-9.eE+\-]/g, '');
      var m = t.match(/[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?/);
      var v = m ? parseFloat(m[0]) : NaN;
      return isNaN(v) ? null : v;
    }
    return s;
  }
  [].forEach.call(document.querySelectorAll('table.sortable'), function (tb) {
    var tbody = tb.tBodies[0];
    var rows = [].slice.call(tbody.rows);
    rows.forEach(function (r, i) { r.setAttribute('data-i', i); });
    var ths = [].slice.call(tb.tHead.rows[0].cells);
    ths.forEach(function (th, ci) {
      if (!th.classList.contains('s')) { return; }
      function run() {
        var state = th.getAttribute('aria-sort');
        var next = state === 'none' ? 'ascending'
                 : (state === 'ascending' ? 'descending' : 'none');
        ths.forEach(function (o) {
          if (o.classList.contains('s')) { o.setAttribute('aria-sort', 'none'); }
        });
        th.setAttribute('aria-sort', next);
        var type = th.getAttribute('data-type') || 'text';
        var arr = [].slice.call(tbody.rows);
        if (next === 'none') {
          arr.sort(function (a, b) {
            return (+a.getAttribute('data-i')) - (+b.getAttribute('data-i'));
          });
        } else {
          var dir = next === 'ascending' ? 1 : -1;
          arr.sort(function (a, b) {
            var x = parseVal(a.cells[ci], type), y = parseVal(b.cells[ci], type);
            if (x === null && y === null) { return 0; }
            if (x === null) { return 1; }   /* N/A 一律排最後 */
            if (y === null) { return -1; }
            if (type === 'num') { return (x - y) * dir; }
            return String(x).localeCompare(String(y), 'zh-Hant') * dir;
          });
        }
        arr.forEach(function (r) { tbody.appendChild(r); });
      }
      th.addEventListener('click', run);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); }
      });
    });
  });

  /* ---------- 4. 右下角浮動目錄：hover／focus 由 CSS 開，這裡補 tap ---------- */
  /* 桌機滑過（:hover）與鍵盤 focus（:focus-within）不需要 JS；                */
  /* 觸控裝置沒有 hover，所以 tap 圖示 → toggle .is-open。                     */
  var tocEl = document.getElementById('toc');
  var tocBtn = document.getElementById('tocbtn');
  function tocClose() {
    if (tocEl) { tocEl.classList.remove('is-open'); }
    if (tocBtn) { tocBtn.setAttribute('aria-expanded', 'false'); }
  }
  function tocToggle() {
    if (!tocEl) { return; }
    var on = tocEl.classList.toggle('is-open');
    if (tocBtn) { tocBtn.setAttribute('aria-expanded', on ? 'true' : 'false'); }
  }
  if (tocBtn) {
    tocBtn.addEventListener('click', function (e) {
      e.preventDefault();
      tocToggle();
    });
  }
  document.addEventListener('click', function (e) {          /* 點外面收起 */
    if (!tocEl || !tocEl.classList.contains('is-open')) { return; }
    if (!tocEl.contains(e.target)) { tocClose(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { tocClose(); }
  });
  [].forEach.call(document.querySelectorAll('.toc-link'), function (a) {
    a.addEventListener('click', tocClose);
  });

  /* ---------- 5. 列印前展開所有摺疊，列印後還原 ---------- */
  var reopen = [];
  function beforePrint() {
    reopen = [];
    [].forEach.call(document.querySelectorAll('details'), function (d) {
      if (!d.open) { reopen.push(d); d.open = true; }
    });
  }
  function afterPrint() {
    reopen.forEach(function (d) { d.open = false; });
    reopen = [];
    tocClose();
  }
  window.addEventListener('beforeprint', beforePrint);
  window.addEventListener('afterprint', afterPrint);
  if (window.matchMedia) {
    var pm = window.matchMedia('print');
    var ph = function (m) { if (m.matches) { beforePrint(); } else { afterPrint(); } };
    if (pm.addEventListener) { pm.addEventListener('change', ph); }
    else if (pm.addListener) { pm.addListener(ph); }
  }

  /* ---------- 6. 互動圖表：tooltip 層 ---------- */
  var tip = null;
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function theTip() {
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'chart-tip';
      tip.setAttribute('role', 'tooltip');
      tip.setAttribute('aria-hidden', 'true');
      document.body.appendChild(tip);
    }
    return tip;
  }
  function tipHTML(title, rows) {
    var h = title ? '<div class="tip-t">' + esc(title) + '</div>' : '';
    for (var i = 0; i < rows.length; i++) {
      var v = String(rows[i][1]), c = '';
      if (/^\s*[▲+]/.test(v)) { c = ' up'; }        /* ▲ 或 + → 紅（漲） */
      else if (/^\s*[▼-]/.test(v)) { c = ' dn'; }   /* ▼ 或 - → 綠（跌） */
      h += '<div class="tip-r"><span class="tip-k">' + esc(rows[i][0]) +
           '</span><span class="tip-v' + c + '">' + esc(v) + '</span></div>';
    }
    return h;
  }
  function placeTip(x, y) {
    var t = theTip(), pad = 15;
    var w = t.offsetWidth, hh = t.offsetHeight;
    var nx = x + pad, ny = y + pad;
    if (nx + w > window.innerWidth - 8) { nx = x - w - pad; }   /* 靠邊翻邊 */
    if (ny + hh > window.innerHeight - 8) { ny = y - hh - pad; }
    if (nx < 4) { nx = 4; }
    if (ny < 4) { ny = 4; }
    t.style.left = nx + 'px';
    t.style.top = ny + 'px';
  }
  function showTip(html, x, y) {
    var t = theTip();
    t.innerHTML = html;
    t.classList.add('on');
    t.setAttribute('aria-hidden', 'false');
    placeTip(x, y);
  }
  function hideTip() {
    if (tip) {
      tip.classList.remove('on');
      tip.setAttribute('aria-hidden', 'true');
    }
  }
  window.addEventListener('scroll', hideTip, { passive: true });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { hideTip(); }
  });

  /* ---------- 7. 柱／段：滑過（或 tap）顯示該項數值與占比 ---------- */
  [].forEach.call(document.querySelectorAll('svg.chart g.mark[data-tip]'),
    function (g) {
      var d;
      try { d = JSON.parse(g.getAttribute('data-tip')); } catch (err) { return; }
      var html = tipHTML(d.t, d.r || []);
      function on(ev) {
        g.classList.add('hot');
        showTip(html, ev.clientX, ev.clientY);
      }
      function off() { g.classList.remove('hot'); hideTip(); }
      g.addEventListener('pointerenter', on);
      g.addEventListener('pointermove', on);
      g.addEventListener('pointerdown', on);      /* 觸控：tap 等同 hover */
      g.addEventListener('pointerleave', off);
      g.addEventListener('pointercancel', off);
      g.addEventListener('focus', function () {
        var r = g.getBoundingClientRect();
        g.classList.add('hot');
        showTip(html, r.left + r.width / 2, r.top);
      });
      g.addEventListener('blur', off);
    });

  /* ---------- 8. 時間序列／分位帶：十字準線＋吸附＋序列開關 ---------- */
  [].forEach.call(document.querySelectorAll('svg.chart[data-kind="xy"]'),
    function (svg) {
      var plot = svg.querySelector('.plot');
      if (!plot) { return; }
      var xs = (plot.getAttribute('data-xs') || '').split(',').map(Number);
      var labs = (plot.getAttribute('data-labs') || '').split('|');
      var cross = svg.querySelector('.crosshair');
      var focus = [].slice.call(svg.querySelectorAll('circle.focus'));
      var vbw = (svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width)
        || 1120;
      var sers = [].slice.call(svg.querySelectorAll('[data-vals]'))
        .map(function (el) {
          var pts = (el.getAttribute('points') || '').trim().split(/\s+/)
            .map(function (p) { var a = p.split(','); return [+a[0], +a[1]]; });
          return {
            el: el,
            key: el.getAttribute('data-key'),
            name: el.getAttribute('data-name'),
            name2: el.getAttribute('data-name2'),
            name3: el.getAttribute('data-name3'),
            unit: el.getAttribute('data-unit') || '',
            nd: +(el.getAttribute('data-nd') || 1),
            ord: +(el.getAttribute('data-ord') || 0),
            vals: (el.getAttribute('data-vals') || '').split(',').map(Number),
            vals2: el.getAttribute('data-vals2')
              ? el.getAttribute('data-vals2').split(',').map(Number) : null,
            pts: pts
          };
        });
      sers.sort(function (a, b) { return a.ord - b.ord; });

      function setFocus(key, role, pt) {
        for (var i = 0; i < focus.length; i++) {
          var c = focus[i];
          if (c.getAttribute('data-key') !== key) { continue; }
          var r = c.getAttribute('data-role');
          if (role ? r !== role : !!r) { continue; }
          if (pt) {
            c.setAttribute('cx', pt[0]);
            c.setAttribute('cy', pt[1]);
            c.classList.add('on');
          } else { c.classList.remove('on'); }
        }
      }
      function nearest(ev) {
        var ux = null, m = svg.getScreenCTM();
        if (m && svg.createSVGPoint) {
          var p = svg.createSVGPoint();
          p.x = ev.clientX; p.y = ev.clientY;
          ux = p.matrixTransform(m.inverse()).x;
        } else {
          var r = svg.getBoundingClientRect();
          ux = (ev.clientX - r.left) / (r.width || 1) * vbw;
        }
        var best = 0, bd = Infinity;
        for (var i = 0; i < xs.length; i++) {
          var d = Math.abs(xs[i] - ux);
          if (d < bd) { bd = d; best = i; }
        }
        return best;
      }
      function show(ev) {
        var i = nearest(ev);
        if (cross) {
          cross.setAttribute('x1', xs[i]);
          cross.setAttribute('x2', xs[i]);
          cross.classList.add('on');
        }
        var rows = [];
        sers.forEach(function (s) {
          var off = s.el.classList.contains('off');
          var np = s.pts.length;
          if (s.vals2) {
            setFocus(s.key, 'hi', off ? null : s.pts[i]);
            setFocus(s.key, 'lo', off ? null : s.pts[np - 1 - i]);
            if (!off) {                          /* 分位帶併成一列範圍 */
              rows.push([s.name3 || (s.name2 + '~' + s.name),
                         s.vals2[i].toFixed(s.nd) + '~' +
                         s.vals[i].toFixed(s.nd) + ' ' + s.unit]);
            }
          } else {
            setFocus(s.key, null, off ? null : s.pts[i]);
            if (!off) {
              rows.push([s.name, s.vals[i].toFixed(s.nd) + ' ' + s.unit]);
            }
          }
        });
        showTip(tipHTML(labs[i] || '', rows), ev.clientX, ev.clientY);
      }
      function hide() {
        if (cross) { cross.classList.remove('on'); }
        focus.forEach(function (c) { c.classList.remove('on'); });
        hideTip();
      }
      svg.addEventListener('pointermove', show);
      svg.addEventListener('pointerdown', show);   /* 觸控：tap 等同 hover */
      svg.addEventListener('pointerleave', hide);
      svg.addEventListener('pointercancel', hide);

      /* 直接標註＝可點的圖例；y 軸尺度固定不重算，切換序列不會造成尺度誤讀 */
      [].forEach.call(svg.querySelectorAll('g.lgd[data-key]'), function (g) {
        function toggle() {
          var key = g.getAttribute('data-key');
          var on = g.classList.toggle('off');
          [].forEach.call(svg.querySelectorAll('[data-key="' + key + '"]'),
            function (el) {
              if (on) { el.classList.add('off'); }
              else { el.classList.remove('off'); }
            });
          hide();
        }
        g.addEventListener('click', toggle);
        g.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
        });
      });
    });

  /* ---------- 9.（v1.1）柱狀圖的圖例切換：分群長條 ---------- */
  /* 第 8 段只掛在 data-kind="xy" 的圖上；分群長條（data-kind="bar"）的上方圖例  */
  /* 同樣用 g.lgd[data-key]，點了切換同 svg 內所有 [data-key] 的 .off（整條序列  */
  /* 包在 g.ser[data-key] 裡，CSS 沿用 .ser.off）。既有的 bar 圖沒有 g.lgd[data-key]，*/
  /* 所以這一段對 v1 的圖完全不會掛上任何事件；y 軸尺度同樣固定不重算。            */
  [].forEach.call(document.querySelectorAll('svg.chart[data-kind="bar"]'),
    function (svg) {
      [].forEach.call(svg.querySelectorAll('g.lgd[data-key]'), function (g) {
        function toggle() {
          var key = g.getAttribute('data-key');
          var on = g.classList.toggle('off');
          [].forEach.call(svg.querySelectorAll('[data-key="' + key + '"]'),
            function (el) {
              if (on) { el.classList.add('off'); }
              else { el.classList.remove('off'); }
            });
          hideTip();
        }
        g.addEventListener('click', toggle);
        g.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
        });
      });
    });

  spy();
})();
""").strip()
