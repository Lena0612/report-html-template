# -*- coding: utf-8 -*-
"""figures — 讀 md 裡的 ```figure／```table 宣告 → 呼叫 svgchart 畫圖／組表；
另負責 {{v:key}} 的數值來源（檔頭 values／values_file／從圖表資料算出的內建函數）。

v4（skill 版）取代 content_playtime.py：圖表與數字不再寫在 Python 裡，全部由
內容檔宣告、資料由 csv／json 提供。純 stdlib，不用 numpy／pandas。

型別登錄表（type registry）
    TYPES[name] = dict(load=..., render=..., doc=..., fields=...)
    新增一種圖只要在本檔用 @figtype 註冊 load（讀資料→store）與 render（store→svg），
    build.py／mdcontent.py 不用動。v1 登錄 5 種、v1.1（2026-09-14）加 3 種、v1.2（同日）加 2 種、v1.3（同日）加 3 種＋擴充瀑布、
    v1.4（2026-09-16）加 1 種＋line 加 vlines，共 14 種：
        line        時間序列折線，可含分位帶（svgchart.xy_chart；v1.4 起可加 vlines 多條事件虛線）
        waterfall   瀑布（svgchart.waterfall；v1.3 起不限 4 段、可插 subtotal 中繼點、可用 data csv）
        stacked100  100% 堆疊橫條（svgchart.stacked100）
        ranked      貢獻排序橫條，兩段拆解（svgchart.ranked_bars）
        bars        類別直立柱（svgchart.vbars）
        retention   留存曲線 D1/D3/D7/D14/D30 多群（svgchart.xy_chart ＋ 點標記，v1.1）
        grouped     分群長條 類別 × 序列並排，可加 ▲▼ 變化（svgchart.grouped_bars，v1.1）
        funnel      漏斗 人數／占第一步／占上一步，最大流失步驟強調（svgchart.funnel，v1.1）
        stacked     堆疊長條（絕對值）類別 × 2～5 段，柱頂合計，可標兩類別合計的 ▲▼（svgchart.stacked_bars，v1.2）
        cohort      cohort 留存熱圖 cohort × 天數位移，單色亮度階，允許缺值（svgchart.heatmap，v1.2）
        hist        直方圖＋分位線 raw 值自動分箱或已分箱，p25/p50/p75/p90 虛線＋mean，1～2 組疊圖（svgchart.histogram，v1.3）
        dumbbell    pre/post 分群啞鈴圖 每群 a→b 兩點一線，▲▼ 變化紅漲綠跌（svgchart.dumbbell，v1.3）
        dow_hour    星期×小時熱圖 7 × 24 格，單色亮度階，最大格粗框（svgchart.heatmap 通用化，v1.3）
        sigheat     顯著度熱圖 列＝指標、欄＝任意分組，單色亮度階、值越大越深（svgchart.heatmap，v1.4）

流程（mdcontent.load 依序呼叫）
    ctx = collect(lines, start, md_dir, fm)     掃 ``` 區塊、解析、讀資料 → ctx.store
    values = resolve_values(fm, lnmap, md_dir, ctx)   {{v:key}} 的值（可引用 ctx.store）
    render_all(ctx, values)                     產 SVG／表格材料 → ctx.figs／ctx.tbls
所有問題收進 ctx.problems（行號, 訊息, 提示），由 mdcontent 一次印出、不寫 HTML。
"""
import bisect
import csv
import io
import json
import os
import re

import svgchart as S
import yamlite as Y

# 顏色角色 → CSS class（定義在 themes.py 的共用基礎；SVG 不吃 var() 所以走 class）
COLORS = {
    "s1": "c-s1", "s2": "c-s2", "s3": "c-s3",      # 類別／序列：中性藍 深→淺
    "raw": "c-raw",                                # 原始序列：淡灰細線
    "q": "c-q", "band": "c-band",                  # 分位數線／分位帶
    "ink": "c-ink",                                # 墨色（參考線、mean 虛線）
    "neu": "c-neu",                                # 中性灰（瀑布水位柱）
    "up": "c-up", "dn": "c-dn", "dn2": "c-dn2",    # 方向色：紅漲／綠跌／淺綠
}
# v1.2：堆疊長條要 5 階同色系。CSS 只有 c-s1～c-s3，s4／s5 用 fill-opacity 把 c-s3 再淡兩階
# （themes.py 不動、SVG 仍只寫 class）。相對亮度：s1 .14 → s2 .36 → s3 .63 → s4 .76 → s5 .86。
SHADES = {"s4": ("c-s3", 0.62), "s5": ("c-s3", 0.34)}
RE_KEY = re.compile(r"^[A-Za-z0-9_\-]+$")
RE_V = re.compile(r"\{\{v:([^}]*)\}\}")
DEF_KEYS = ["維度", "指標", "著色"]
# v1.5 第 1 項：檢定顯著底色的標準備註句，由引擎提供（內容檔宣告 sig 就自動補到備註後面）
SIG_DIRW = {"lr": "左右", "tb": "上下"}
SIG_NOTE = "底色著色為經統計檢定有顯著差異，方向為%s著色"
# v1.6 mark: max（A 線）＝一組配對只標數值較大的那一格。決定的是「哪一格上色」，
# 與底下的深淺分級正交：兩個都宣告時＝只有較大那格上色、深淺依 v 落在哪一階。
SIG_NOTE_MAX = "底色著色為經統計檢定有顯著差異，%s配對中只標數值較大的一格"
# v1.6 深淺分級（B 線）：pairs 帶 `v`（檢定強度）時，底色分三階、越深證據越強。
# 決定的是「那一格多深」。三階是刻意的上限——列印／灰階下四階以上的明度差就分不出來
# （見 風格B設計決定.md 決定 36）。沒有任何一組帶 `v` 時完全走 v1.5 的單一階路徑，
# 輸出逐 byte 不變；mark 沒宣告時也一樣。
SIG_LEVELS = 3
SIG_NOTE_LV = "｜底色深淺＝%s，越深證據越強（三階：< %s／%s ~ %s／≥ %s）"
CN = "零一二三四五六七八九十"

COMMON = ["key", "type", "title", "defs", "note", "note_extra", "aria", "desc",
          "hint", "height"]
TABLE_FIELDS = ["key", "title", "columns", "align", "types", "emph_rows", "sortable",
                "defs", "note", "note_extra", "data",
                # v1.5：儲存格合併／列群組粗框／檢定顯著底色（宣告才生效）
                "rowspan", "row_groups", "sig",
                # v1.9：欄位群直向粗框（宣告才生效）
                "col_groups"]
# v1.6：mark 來自 A 線（哪一格）、scale／levels＋pair 的 v 來自 B 線（多深），可併用
SIG_FIELDS = ["dir", "pairs", "note", "mark", "scale", "levels"]
SIG_PAIR = ["row", "col", "a", "b", "v"]
_CELL_MARK = re.compile(r"^\{\{[dn]:\s*([^:}]+?)\s*(?::[^}]*)?\}\}$")
_CELL_NUM = re.compile(r"^[+\-]?\d+(?:\.\d+)?$")


class DeclError(Exception):
    def __init__(self, ln, msg, hint=""):
        self.ln, self.msg, self.hint = ln, msg, hint
        super().__init__(msg)


# ---------------------------------------------------------------- 宣告存取
class Spec:
    """包住一個宣告 dict：帶行號的必填／選填讀取與型別檢查。"""

    def __init__(self, obj, lnmap, ln0, allowed, path=(), expand=None, what="區塊"):
        self.obj, self.lnmap, self.ln0 = obj, lnmap, ln0
        self.path, self.expand, self.what = tuple(path), expand or (lambda s, ln: s), what
        if allowed is not None:
            bad = [k for k in obj if k not in allowed]
            if bad:
                raise DeclError(self.ln(bad[0]), f"{what}不認得的欄位 `{bad[0]}`",
                                f"可用欄位：{'、'.join(allowed)}")

    def ln(self, *path):
        return Y.get_ln(self.lnmap, self.path + tuple(path), self.ln0)

    def has(self, k):
        return k in self.obj and self.obj[k] not in ("", None)

    def req(self, k, typ=None, hint=""):
        if not self.has(k):
            raise DeclError(self.ln(k), f"{self.what}缺 `{k}`", hint)
        return self._typed(k, typ)

    def opt(self, k, default=None, typ=None):
        if not self.has(k):
            return default
        return self._typed(k, typ)

    def _typed(self, k, typ):
        v = self.obj[k]
        ln = self.ln(k)
        if typ == "str":
            if isinstance(v, (list, dict)):
                raise DeclError(ln, f"`{k}` 要是一段文字，不是清單／對應")
            return self.expand(str(v), ln)
        if typ == "num":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise DeclError(ln, f"`{k}` 要是數字（現在是 {v!r}）")
            return float(v)
        if typ == "int":
            if isinstance(v, bool) or not isinstance(v, int):
                if isinstance(v, float) and v.is_integer():
                    return int(v)
                raise DeclError(ln, f"`{k}` 要是整數（現在是 {v!r}）")
            return v
        if typ == "bool":
            if not isinstance(v, bool):
                raise DeclError(ln, f"`{k}` 要是 true／false（現在是 {v!r}）")
            return v
        if typ == "list":
            if not isinstance(v, list):
                raise DeclError(ln, f"`{k}` 要是清單（寫成 [a, b] 或多行 `- ` 項目）")
            return v
        if typ == "dict":
            if not isinstance(v, dict):
                raise DeclError(ln, f"`{k}` 要是對應（寫成 {{a: 1, b: 2}} 或縮排的 `鍵: 值`）")
            return v
        return v

    def sub(self, k, i, item, allowed, what):
        if not isinstance(item, dict):
            raise DeclError(self.ln(k, i), f"`{k}` 的第 {i + 1} 項要寫成 {{欄位: 值, ...}}",
                            f"可用欄位：{'、'.join(allowed)}")
        return Spec(item, self.lnmap, self.ln(k, i), allowed, self.path + (k, i),
                    self.expand, what)


def color_cls(name, ln, default):
    if name is None:
        return default
    s = str(name)
    if s in COLORS:
        return COLORS[s]
    if s in COLORS.values():
        return s
    raise DeclError(ln, f"不認得的顏色角色 `{s}`",
                    "可用：" + "、".join(COLORS) + "（類別用 s1/s2/s3，方向色只在瀑布與貢獻排序用 up/dn/dn2）")


def color_fill(name, ln, default):
    """堆疊長條用：顏色角色 → (class, fill-opacity|None)。多接受 s4／s5 兩個淡階。"""
    if name is None:
        return default
    s = str(name)
    if s in SHADES:
        return SHADES[s]
    if s in COLORS or s in COLORS.values():
        return (color_cls(s, ln, default[0]), None)
    raise DeclError(ln, f"不認得的顏色角色 `{s}`",
                    "堆疊長條的段用同色系深→淺：s1、s2、s3、s4、s5（不寫就照這個順序）；不要用紅綠畫段")


def _need_vals(vals, ln, what="選到的範圍"):
    """v1.2：cohort 熱圖允許缺值（None）；計算式碰到缺值要報錯，不能默默略過。"""
    if any(v is None for v in vals):
        raise DeclError(ln, f"{what}有缺值（空白格）",
                        "cohort 熱圖允許尚未觀察到的天數留空；算數字時請用 from／to 或 a／b 選沒有缺值的 cohort，或改選別的天數欄")
    return vals


# ---------------------------------------------------------------- 資料
def load_csv(sp, ctx, field="data"):
    """`data:` 是路徑（相對於 md 所在資料夾）或 `|` 區塊文字。回傳 (表頭, 列 dict 清單, 來源描述)。"""
    raw = sp.req(field, "str", "寫 data: data/xxx.csv（相對於 md 所在資料夾）或 data: | 換行後直接貼 CSV")
    ln = sp.ln(field)
    if "\n" in raw:                                   # data: | 底下直接貼的 CSV
        text, src = raw, f"第 {ln} 行的 data 區塊"
    else:
        path = raw if os.path.isabs(raw) else os.path.join(ctx.md_dir, raw)
        if not os.path.isfile(path):
            raise DeclError(ln, f"data 檔找不到：{raw}",
                            f"路徑是相對於內容檔所在的資料夾（{ctx.md_dir}）；請確認檔名與大小寫")
        text, src = io.open(path, encoding="utf-8-sig").read(), raw
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise DeclError(ln, f"{src} 至少要有表頭 ＋ 1 列資料")
    hdr = [h.strip() for h in rows[0]]
    if len(set(hdr)) != len(hdr):
        raise DeclError(ln, f"{src} 的表頭有重複欄名：{hdr}")
    out = []
    for i, r in enumerate(rows[1:], 2):
        if len(r) != len(hdr):
            raise DeclError(ln, f"{src} 第 {i} 列有 {len(r)} 欄，表頭是 {len(hdr)} 欄",
                            "含逗號的值要用雙引號包起來")
        out.append({h: c.strip() for h, c in zip(hdr, r)})
    return hdr, out, src


def numcol(rows, col, hdr, ln, src):
    if col not in hdr:
        raise DeclError(ln, f"資料裡沒有 `{col}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
    out = []
    for i, r in enumerate(rows, 2):
        s = r[col].replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            raise DeclError(ln, f"{src} 第 {i} 列的 `{col}` 不是數字：{r[col]!r}")
    return out


def xlabel(v, xfmt):
    if xfmt == "md":
        m = re.match(r"^\d{4}-(\d{2}-\d{2})$", v)
        return m.group(1) if m else v
    return v


def find_x(store, v, ln, what):
    """x 值（原始或顯示文字）→ 索引。"""
    s = str(v)
    for cand in (store["x"], store["labels"]):
        if s in cand:
            return cand.index(s)
    raise DeclError(ln, f"{what} `{s}` 不在 x 欄裡",
                    f"x 的第一個是 {store['x'][0]}、最後一個是 {store['x'][-1]}（共 {len(store['x'])} 個）")


def seg_range(store, seg, ln):
    n, bk = len(store["x"]), store.get("bk")
    if seg in (None, "all", "全部"):
        return 0, n - 1
    if bk is None:
        raise DeclError(ln, f"用 seg: {seg} 之前，這張圖要先宣告 break（斷點）")
    if seg in ("pre", "前段"):
        return 0, bk - 1
    if seg in ("post", "後段"):
        return bk + 1, n - 1
    raise DeclError(ln, f"seg 只能是 pre／post／all（現在是 {seg!r}）")


# ---------------------------------------------------------------- 內建函數（{{v:}} 與 reflines.at）
FNS = ["mean", "sum", "min", "max", "range", "first", "last", "count", "diff", "pct_change"]
FN_FIELDS = ["fn", "fig", "col", "seg", "from", "to", "a", "b", "fmt", "nd", "unit", "comma"]


def _point(store, sel, ln):
    """a／b 的選擇：pre／post／all → 段平均；first／last → 端點；其他 → x 值對應的點。"""
    vals = store["_vals"]
    if sel in ("pre", "post", "all", "前段", "後段", "全部"):
        i0, i1 = seg_range(store, sel, ln)
        seg = vals[i0:i1 + 1]
        if not seg:
            raise DeclError(ln, f"seg {sel} 是空的")
        _need_vals(seg, ln, f"seg {sel}")
        return sum(seg) / len(seg)
    if sel == "first":
        return _need_vals([vals[0]], ln, "first 那一點")[0]
    if sel == "last":
        return _need_vals([vals[-1]], ln, "last 那一點")[0]
    return _need_vals([vals[find_x(store, sel, ln, "a／b")]], ln, f"`{sel}` 那一點")[0]


def compute(spec, ctx, ln, default_fig=None):
    """{fn: mean, fig: ts_break, col: mean, seg: pre} → 數字（未格式化）。"""
    if not isinstance(spec, dict):
        raise DeclError(ln, "計算式要寫成 {fn: mean, fig: 圖key, col: 欄名, ...}")
    bad = [k for k in spec if k not in FN_FIELDS]
    if bad:
        raise DeclError(ln, f"計算式不認得的欄位 `{bad[0]}`", f"可用：{'、'.join(FN_FIELDS)}")
    fn = spec.get("fn")
    if fn not in FNS:
        raise DeclError(ln, f"不認得的函數 `{fn}`", f"只支援：{'、'.join(FNS)}（不是通用算式引擎）")
    fig = spec.get("fig", default_fig)
    if fig not in ctx.store:
        if str(fig) in ctx.broken:
            raise DeclError(ln, f"圖 `{fig}` 本身有錯（見上面）", "")
        raise DeclError(ln, f"計算式引用的圖 `{fig}` 不存在（沒有這個 key 的 ```figure 區塊）",
                        f"目前有資料的圖：{'、'.join(ctx.store) or '（無）'}")
    st = dict(ctx.store[fig])
    cols = st["cols"]
    col = spec.get("col")
    if col is None:
        if len(cols) == 1:
            col = next(iter(cols))
        else:
            raise DeclError(ln, f"要指定 col（圖 `{fig}` 有 {len(cols)} 欄）", f"可用：{'、'.join(cols)}")
    if col not in cols:
        raise DeclError(ln, f"圖 `{fig}` 沒有 `{col}` 這一欄", f"可用：{'、'.join(cols)}")
    st["_vals"] = list(cols[col])
    if fn in ("diff", "pct_change"):
        a = _point(st, str(spec.get("a", "pre")), ln)
        b = _point(st, str(spec.get("b", "post")), ln)
        if fn == "diff":
            return b - a
        if a == 0:
            raise DeclError(ln, "pct_change 的基準 a 是 0，沒法算變化率")
        return (b / a - 1) * 100
    # 單段函數：seg 或 from／to 選範圍
    if "from" in spec or "to" in spec:
        i0 = find_x(st, spec["from"], ln, "from") if "from" in spec else 0
        i1 = find_x(st, spec["to"], ln, "to") if "to" in spec else len(st["_vals"]) - 1
    else:
        i0, i1 = seg_range(st, spec.get("seg"), ln)
    vals = st["_vals"][i0:i1 + 1]
    if not vals:
        raise DeclError(ln, "選到的範圍是空的")
    _need_vals(vals, ln)
    if fn == "mean":
        return sum(vals) / len(vals)
    if fn == "sum":
        return sum(vals)
    if fn == "min":
        return min(vals)
    if fn == "max":
        return max(vals)
    if fn == "range":
        return max(vals) - min(vals)
    if fn == "first":
        return vals[0]
    if fn == "last":
        return vals[-1]
    return float(len(vals))


def format_value(v, spec, ln):
    """數字 → 行內標記字串：fmt n（中性 chip）／d（變化量 chip，自帶正負號）／text（純文字）。"""
    fmt = str(spec.get("fmt", "n"))
    nd = spec.get("nd", 1)
    if isinstance(nd, bool) or not isinstance(nd, int):
        raise DeclError(ln, f"nd 要是整數（小數位數），現在是 {nd!r}")
    unit = str(spec.get("unit", ""))
    comma = bool(spec.get("comma", False))
    if fmt == "d":
        num = f"{v:+,.{nd}f}" if comma else f"{v:+.{nd}f}"
        return "{{d:%s:%s}}" % (num, unit)
    num = f"{v:,.{nd}f}" if comma else f"{v:.{nd}f}"
    if fmt == "n":
        return "{{n:%s:%s}}" % (num, unit)
    if fmt == "text":
        return num + unit
    raise DeclError(ln, f"fmt 只能是 n／d／text（現在是 {fmt!r}）")


def fn_doc(spec):
    sel = (f"{spec.get('a', 'pre')}→{spec.get('b', 'post')}"
           if spec.get("fn") in ("diff", "pct_change")
           else (spec.get("seg") or
                 (f"{spec.get('from', '…')}~{spec.get('to', '…')}" if ("from" in spec or "to" in spec) else "all")))
    return f"{spec.get('fn')}({spec.get('fig')}.{spec.get('col', '')}, {sel})"


# ---------------------------------------------------------------- 型別登錄表
TYPES = {}


def figtype(name, doc, fields, item_fields=None):
    def deco(cls):
        TYPES[name] = dict(load=cls.load, render=cls.render, doc=doc,
                           fields=COMMON + fields, item_fields=item_fields or {})
        return cls
    return deco


@figtype("line", "時間序列折線（可含分位帶）— svgchart.xy_chart",
         ["data", "x", "xfmt", "unit", "nd", "ylab", "ymin", "ymax", "xtick_every", "xticks",
          "series", "break", "break_span", "break_label", "reflines", "vlines", "legend"],
         {"series": ["kind", "col", "id", "name", "label", "color", "width", "dash", "order",
                     "unit", "nd", "lo", "hi", "lo_name", "hi_name"],
          "reflines": ["at", "label", "color", "seg", "from", "to", "anchor"],
          "vlines": ["at", "label", "label2", "color", "icon"]})
class Line:
    SER = ["kind", "col", "id", "name", "label", "color", "width", "dash", "order",
           "unit", "nd", "lo", "hi", "lo_name", "hi_name"]
    REF = ["at", "label", "color", "seg", "from", "to", "anchor"]
    VL = ["at", "label", "label2", "color", "icon"]
    VICON = ("", "warn")          # v1.6：選用，只有 warn（紅色三角驚嘆號）
    VCOL = {"red": "#c62828", "紅": "#c62828", "ink": "", "": ""}
    LEGEND = ("right", "bottom")  # v1.7：選用，圖例放右側（預設）或 x 軸下方

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        xcol = sp.req("x", "str", f"x 欄是橫軸；{src} 的欄位：{'、'.join(hdr)}")
        if xcol not in hdr:
            raise DeclError(sp.ln("x"), f"資料裡沒有 x 欄 `{xcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        xfmt = sp.opt("xfmt", "full", "str")
        if xfmt not in ("full", "md"):
            raise DeclError(sp.ln("xfmt"), "xfmt 只能是 full（原樣）或 md（2026-07-16 → 07-16）")
        xraw = [r[xcol] for r in rows]
        store = {"x": xraw, "labels": [xlabel(v, xfmt) for v in xraw], "cols": {}, "bk": None}
        series = sp.req("series", "list", "至少一條序列：- {col: 欄名, name: 顯示名, color: s1}")
        if not series:
            raise DeclError(sp.ln("series"), "series 是空的")
        for i, s in enumerate(series):
            ss = sp.sub("series", i, s, Line.SER, f"series 第 {i + 1} 項")
            if ss.opt("kind", "line", "str") == "band":
                for k in ("lo", "hi"):
                    c = ss.req(k, "str", "分位帶要給 lo（下緣欄）與 hi（上緣欄）")
                    store["cols"][c] = numcol(rows, c, hdr, ss.ln(k), src)
            else:
                c = ss.req("col", "str", "每條序列要指定 col（資料欄名）")
                store["cols"][c] = numcol(rows, c, hdr, ss.ln("col"), src)
        if sp.has("break"):
            store["bk"] = find_x(store, sp.req("break"), sp.ln("break"), "break")
        return store

    @staticmethod
    def render(sp, store, ctx):
        unit0, nd0 = sp.opt("unit", "", "str"), sp.opt("nd", 1, "int")
        ser = []
        for i, s in enumerate(sp.req("series", "list")):
            ss = sp.sub("series", i, s, Line.SER, f"series 第 {i + 1} 項")
            kind = ss.opt("kind", "line", "str")
            lab = ss.opt("label")
            if isinstance(lab, bool):
                endlab = False if lab is False else None
            else:
                endlab = ss.expand(str(lab), ss.ln("label")) if lab not in (None, "") else None
            common = dict(unit=ss.opt("unit", unit0, "str"), nd=ss.opt("nd", nd0, "int"),
                          ord=ss.opt("order", 0, "int"), endlab=endlab)
            if kind == "band":
                lo, hi = ss.req("lo", "str"), ss.req("hi", "str")
                ser.append(dict(type="band", key=ss.opt("id", "band", "str"),
                                name=ss.opt("hi_name", hi, "str"), name2=ss.opt("lo_name", lo, "str"),
                                cls=color_cls(ss.opt("color"), ss.ln("color"), "c-band"),
                                hi=store["cols"][hi], lo=store["cols"][lo], **common))
            elif kind == "line":
                col = ss.req("col", "str")
                ser.append(dict(type="line", key=ss.opt("id", col, "str"), name=ss.opt("name", col, "str"),
                                cls=color_cls(ss.opt("color"), ss.ln("color"), "c-s1"),
                                w=ss.opt("width", 2.2, "num"), dash=ss.opt("dash", False, "bool"),
                                vals=store["cols"][col], **common))
            else:
                raise DeclError(ss.ln("kind"), f"kind 只能是 line 或 band（現在是 {kind!r}）")
        bk = store["bk"]
        hl = []
        for i, r in enumerate(sp.opt("reflines", [], "list")):
            rs = sp.sub("reflines", i, r, Line.REF, f"reflines 第 {i + 1} 項")
            at = rs.req("at", None, "水平參考線的值：數字，或 {fn: mean, col: 欄名, seg: pre}")
            if isinstance(at, dict):
                at = compute(at, ctx, rs.ln("at"), default_fig=sp.obj.get("key"))
            elif isinstance(at, bool) or not isinstance(at, (int, float)):
                raise DeclError(rs.ln("at"), f"at 要是數字或計算式（現在是 {at!r}）")
            if rs.has("from") or rs.has("to"):
                i0 = find_x(store, rs.req("from"), rs.ln("from"), "from") if rs.has("from") else 0
                i1 = find_x(store, rs.req("to"), rs.ln("to"), "to") if rs.has("to") else len(store["x"]) - 1
            else:
                i0, i1 = seg_range(store, rs.opt("seg", None, "str"), rs.ln("seg"))
            anchor = rs.opt("anchor", "start", "str")
            if anchor not in ("start", "end"):
                raise DeclError(rs.ln("anchor"), "anchor 只能是 start（標籤靠左）或 end（靠右）")
            hl.append((at, rs.opt("label", "", "str"), color_cls(rs.opt("color"), rs.ln("color"), "c-ink"),
                       i0, i1, anchor))
        vl = []
        for i, r in enumerate(sp.opt("vlines", [], "list")):
            vs = sp.sub("vlines", i, r, Line.VL, f"vlines 第 {i + 1} 項")
            at = vs.req("at", None, "垂直事件線的位置：x 欄的值（例 2026-06-02）")
            idx = find_x(store, at, vs.ln("at"), "vlines.at")
            c = vs.opt("color", "", "str")
            if c not in Line.VCOL:
                raise DeclError(vs.ln("color"), f"vlines 的 color 只能是 red／ink（現在是 {c!r}）")
            # v1.6：選用的警示 icon。不宣告＝完全沿用 v1.5 的輸出（逐 byte 相同）。
            ic = vs.opt("icon", "", "str")
            if ic not in Line.VICON:
                raise DeclError(vs.ln("icon"),
                                f"vlines 的 icon 只能是 warn（現在是 {ic!r}）",
                                "目前只有一種事件 icon：icon: warn（紅色三角驚嘆號，畫在線的下端）；"
                                "不要 icon 就整個欄位拿掉")
            # v1.8：選用的第二行標籤（第一行寫日期、第二行寫事件名，寬度砍半，
            # 相鄰事件線的標籤才不會撞在一起）。不宣告＝只畫一行，輸出逐 byte 同 v1.7。
            lb = vs.opt("label", "", "str")
            lb2 = vs.opt("label2", "", "str")
            if lb2 and not lb:
                raise DeclError(vs.ln("label2"),
                                f"vlines 第 {i + 1} 項寫了 label2 卻沒有 label"
                                f"（第二行標籤沒有第一行可以掛）",
                                "label 是第一行（慣例寫日期）、label2 是第二行（事件名）；"
                                "只要一行就只寫 label")
            vl.append((idx, lb, Line.VCOL[c], ic, lb2))
        # v1.5 第 6 項：x 軸指定刻度清單（不等距也可以，例 [2026-05-01, 2026-06-01, …]）
        xt = None
        if sp.has("xticks"):
            if sp.has("xtick_every"):
                raise DeclError(sp.ln("xticks"), "xticks 與 xtick_every 只能擇一",
                                "要每 N 個標一次就用 xtick_every；要自己指定哪幾個就只留 xticks")
            lst = sp.req("xticks", "list", "要標出來的 x 值清單，例 xticks: [2026-05-01, 2026-06-01]")
            if not lst:
                raise DeclError(sp.ln("xticks"), "xticks 是空的",
                                "至少指定一個 x 值；不想自己指定就拿掉 xticks（預設每 7 個標一次）")
            xt = []
            for i, v in enumerate(lst):
                idx = find_x(store, v, sp.ln("xticks", i), "xticks")
                if idx in xt:
                    raise DeclError(sp.ln("xticks", i), f"xticks 的 `{v}` 重複了")
                xt.append(idx)
            xt.sort()
        # v1.7 第 1 項：圖例位置。不宣告＝right（序列名稱標在線的右端，輸出逐 byte 同 v1.6）
        lg = sp.opt("legend", "right", "str")
        if lg not in Line.LEGEND:
            raise DeclError(sp.ln("legend"),
                            f"legend 只能是 right（右側直接標註）或 bottom"
                            f"（x 軸下方橫排）（現在是 {lg!r}）",
                            "要把圖例搬到 x 軸下面就寫 legend: bottom；"
                            "維持右側標註就整個欄位拿掉")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.xy_chart(
            store["labels"], ser, aria, sp.opt("desc", aria, "str"),
            ylab=sp.opt("ylab", "", "str"), h=sp.opt("height", 380.0, "num"),
            ymin=sp.opt("ymin", None, "num"), ymax=sp.opt("ymax", None, "num"),
            bk=bk, bkspan=sp.opt("break_span", 3, "int"), bklabel=sp.opt("break_label", None, "str"),
            hlines=hl, xtick_every=sp.opt("xtick_every", 7, "int"), hint=sp.opt("hint", None, "str"),
            vlines=vl, xtick_at=xt, legend=lg)


@figtype("waterfall", "瀑布：水位 → 變化 → … → 水位；v1.3 起不限 4 段（≤ 12）、可插 subtotal 中繼點、可改用 data: csv — svgchart.waterfall",
         ["items", "data", "name", "kind", "value", "ylab", "unit", "nd", "label_every"],
         {"items": ["name", "kind", "value", "tip"]})
class Waterfall:
    ITEM = ["name", "kind", "value", "tip"]
    KINDS = ("level", "delta", "subtotal")
    MAX = 12

    @staticmethod
    def _records(sp, ctx):
        """回傳 [(name, kind, value|None, tip_rows, ln)]。來源二選一：items:（v1 寫法）或 data: csv（name,kind,value ＋ 其餘欄當 tooltip）。
        tip 文字這裡不展開 {{v:}}（render 才有值），render 會用 sp.expand 再處理。"""
        if sp.has("items") and sp.has("data"):
            raise DeclError(sp.ln("data"), "items 與 data 只能寫一個",
                            "少於 5 段直接寫 items；段多或從 notebook 匯出的用 data: csv（欄 name,kind,value）")
        out = []
        if sp.has("data"):
            hdr, rows, src = load_csv(sp, ctx)
            ncol = sp.opt("name", "name" if "name" in hdr else hdr[0], "str")
            vcol = sp.opt("value", "value" if "value" in hdr else None, "str")
            kcol = sp.opt("kind", "kind" if "kind" in hdr else None, "str")
            for c, k in ((ncol, "name"), (vcol, "value"), (kcol, "kind")):
                if c is not None and c not in hdr:
                    raise DeclError(sp.ln(k), f"資料裡沒有 `{c}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
            if vcol is None:
                raise DeclError(sp.ln("data"), "資料要有 value 欄（或用 value: 指名數值欄）", f"{src} 的欄位：{'、'.join(hdr)}")
            extra = [h for h in hdr if h not in (ncol, vcol, kcol)]
            ln = sp.ln("data")
            for i, r in enumerate(rows, 2):
                nm = r[ncol].strip()
                if not nm:
                    raise DeclError(ln, f"{src} 第 {i} 列的 `{ncol}`（名稱）是空的")
                if kcol:
                    kind = r[kcol].strip().lower()
                    if kind not in Waterfall.KINDS:
                        raise DeclError(ln, f"{src} 第 {i} 列的 `{kcol}` 是 {r[kcol]!r}，只能是 level／delta／subtotal")
                else:
                    kind = "level" if i in (2, len(rows) + 1) else "delta"
                sv = r[vcol].replace(",", "").strip()
                if sv == "":
                    if kind != "subtotal":
                        raise DeclError(ln, f"{src} 第 {i} 列的 `{vcol}` 是空的（只有 subtotal 可以留空，由程式算累計）")
                    val = None
                else:
                    try:
                        val = float(sv)
                    except ValueError:
                        raise DeclError(ln, f"{src} 第 {i} 列的 `{vcol}` 不是數字：{r[vcol]!r}")
                tips = [(h, r[h]) for h in extra if r[h].strip()]
                out.append((nm, kind, val, tips, ln))
        else:
            items = sp.req("items", "list", "至少兩項：- {name: 前段平均, kind: level, value: 39.05}；段多的可改用 data: csv")
            for i, it in enumerate(items):
                s = sp.sub("items", i, it, Waterfall.ITEM, f"items 第 {i + 1} 項")
                name = s.req("name", "str")
                kind = s.req("kind", "str", "kind 是 level（水位柱）、delta（變化柱）或 subtotal（中繼水位，v1.3）")
                if kind not in Waterfall.KINDS:
                    raise DeclError(s.ln("kind"), f"kind 只能是 level、delta 或 subtotal（現在是 {kind!r}）")
                if kind == "subtotal":
                    val = s.opt("value", None, "num")
                else:
                    val = s.req("value", "num", "value 要是數字")
                tip = s.opt("tip", {}, "dict")
                tips = [(s.expand(str(k), s.ln("tip")), s.expand(str(v), s.ln("tip"))) for k, v in tip.items()]
                out.append((name, kind, val, tips, s.ln("value") if s.has("value") else s.ln("name")))
        return out

    @staticmethod
    def _resolve(sp, ctx):
        """算累計、補 subtotal 的值、核對 level／subtotal 與累計是否一致。回傳 [(name, kind, value, tips)] 與 cum 清單。"""
        recs = Waterfall._records(sp, ctx)
        where = sp.ln("items") if sp.has("items") else sp.ln("data")
        if len(recs) < 2:
            raise DeclError(where, "瀑布至少要兩項")
        if len(recs) > Waterfall.MAX:
            raise DeclError(where, f"瀑布最多 {Waterfall.MAX} 段（現在 {len(recs)} 段）",
                            "把小的變化合併成「其他」，或拆成兩張圖（例如先族群、再因子），每張 ≤ 12 段")
        nd = sp.opt("nd", 2, "int")
        tol = 10.0 ** (-nd)
        out, cums, cur = [], [], 0.0
        for i, (name, kind, val, tips, ln) in enumerate(recs):
            if kind == "subtotal":
                if i == 0:
                    raise DeclError(ln, f"第 1 項「{name}」不能是 subtotal（前面沒有東西可累計）", "第一項通常是 level（起點水位）")
                if val is not None and abs(val - cur) > tol:
                    raise DeclError(ln, f"第 {i + 1} 項「{name}」是 subtotal，宣告的 value {val:g} 與到此為止的累計 {cur:.{nd + 2}f} 不符",
                                    "subtotal 的 value 可以不寫（程式自己算）；寫了就得等於前面各段的累計——差異多半是某段 delta 的正負號或小數位")
                val = cur
            elif kind == "level":
                if i > 0 and abs(val - cur) > tol:
                    raise DeclError(ln, f"第 {i + 1} 項「{name}」是 level，值 {val:g} 與前面各段的累計 {cur:.{nd + 2}f} 差 {abs(val - cur):.{nd + 2}f}（超過 nd={nd} 的一個單位）",
                                    "瀑布的恆等式要成立：起點 ＋ 各 delta ＝ 終點。請核對 delta 的正負號與四捨五入，或把 nd 調小；"
                                    "真的只是尾差就把終點 level 改成 subtotal（程式自己算）")
                cur = val
            else:
                cur += val
            out.append((name, kind, val, tips))
            cums.append(cur)
        return out, cums

    @staticmethod
    def load(sp, ctx):
        recs, cums = Waterfall._resolve(sp, ctx)
        names = [r[0] for r in recs]
        vals = [r[2] for r in recs]
        return {"x": names, "labels": names, "cols": {"value": vals, "cum": cums}, "bk": None}

    @staticmethod
    def render(sp, store, ctx):
        recs, _ = Waterfall._resolve(sp, ctx)
        le = sp.opt("label_every", 1, "int")
        if le < 1:
            raise DeclError(sp.ln("label_every"), "label_every 只能是 1（每根都標）或 2（變化柱隔一根標）")
        items = [(sp.expand(name, sp.ln("items") if sp.has("items") else sp.ln("data")), kind, val,
                  [(sp.expand(str(k), sp.ln0), sp.expand(str(v), sp.ln0)) for k, v in tips]) for name, kind, val, tips in recs]
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.waterfall(items, aria, sp.opt("desc", aria, "str"), h=sp.opt("height", 330.0, "num"),
                           ylab=sp.opt("ylab", "", "str"), nd=sp.opt("nd", 2, "int"),
                           unit=sp.opt("unit", "分", "str"), hint=sp.opt("hint", None, "str"), label_every=le)


@figtype("stacked100", "100% 堆疊橫條（組成前後對照）— svgchart.stacked100",
         ["data", "label", "sub", "segments", "colors", "dark", "deltas", "delta_nd", "delta_unit"],
         {"deltas": ["seg", "text", "tone"]})
class Stacked100:
    DELTA = ["seg", "text", "tone"]

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        label_col = sp.opt("label", hdr[0], "str")
        sub_col = sp.opt("sub", "sub" if "sub" in hdr else None, "str")
        for c, k in ((label_col, "label"), (sub_col, "sub")):
            if c is not None and c not in hdr:
                raise DeclError(sp.ln(k), f"資料裡沒有 `{c}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
        segs = sp.opt("segments", [h for h in hdr if h not in (label_col, sub_col)], "list")
        segs = [str(s) for s in segs]
        if len(segs) < 2:
            raise DeclError(sp.ln("data"), "堆疊至少要兩段（表頭除了 label／sub 之外的欄）")
        cols = {c: numcol(rows, c, hdr, sp.ln("segments"), src) for c in segs}
        labels = [r[label_col] for r in rows]
        subs = [r[sub_col] if sub_col else "" for r in rows]
        # 每列加總要是 1（占比）；若是 100（百分比）就換算
        for i in range(len(rows)):
            tot = sum(cols[c][i] for c in segs)
            if 0.98 <= tot <= 1.02:
                continue
            if 98 <= tot <= 102:
                for c in segs:
                    cols[c][i] = cols[c][i] / 100.0
                continue
            raise DeclError(sp.ln("data"), f"{src} 第 {i + 2} 列的占比加總是 {tot:.4g}，應為 1（或 100）")
        return {"x": labels, "labels": labels, "subs": subs, "cols": cols, "segs": segs, "bk": None}

    @staticmethod
    def render(sp, store, ctx):
        segs = store["segs"]
        colors = sp.opt("colors", ["s3", "s2", "s1"][:len(segs)], "list")
        if len(colors) != len(segs):
            raise DeclError(sp.ln("colors"), f"colors 有 {len(colors)} 個，但段有 {len(segs)} 個：{'、'.join(segs)}")
        seg_spec = [(sp.expand(name, sp.ln("segments")), color_cls(c, sp.ln("colors"), "c-s1"))
                    for name, c in zip(segs, colors)]
        dark = set()
        for d in sp.opt("dark", [], "list"):
            if isinstance(d, int) and not isinstance(d, bool):
                if not 1 <= d <= len(segs):
                    raise DeclError(sp.ln("dark"), f"dark 的 {d} 超出範圍（段從 1 數到 {len(segs)}）")
                dark.add(d - 1)
            elif str(d) in segs:
                dark.add(segs.index(str(d)))
            else:
                raise DeclError(sp.ln("dark"), f"dark 的 `{d}` 不是段名也不是序號", f"段：{'、'.join(segs)}")
        bars = []
        for bi, (lab, sub) in enumerate(zip(store["labels"], store["subs"])):
            full = sp.expand(lab, sp.ln("data")) + (("\n" + sp.expand(sub, sp.ln("data"))) if sub else "")
            bars.append((full, [store["cols"][c][bi] for c in segs]))
        deltas = None
        mode = sp.opt("deltas", "auto")
        dnd, dunit = sp.opt("delta_nd", 1, "int"), sp.opt("delta_unit", "pp", "str")
        if isinstance(mode, list):
            deltas = []
            for i, d in enumerate(mode):
                ds = sp.sub("deltas", i, d, Stacked100.DELTA, f"deltas 第 {i + 1} 項")
                seg = ds.req("seg", "int", "seg 是第幾段（從 1 數）")
                tone = ds.opt("tone", "up", "str")
                if tone not in ("up", "dn"):
                    raise DeclError(ds.ln("tone"), "tone 只能是 up（紅）或 dn（綠）")
                deltas.append((seg - 1, ds.req("text", "str"), tone))
        elif mode == "auto":
            if len(bars) == 2:
                deltas = []
                for i in range(len(segs)):
                    v = (bars[1][1][i] - bars[0][1][i]) * 100
                    arrow = "▲" if v > 0 else ("▼" if v < 0 else "–")
                    tone = "up" if v > 0 else ("dn" if v < 0 else "ink")
                    deltas.append((i, f"{arrow} {v:+.{dnd}f} {dunit}", tone))
        elif mode not in ("none", False):
            raise DeclError(sp.ln("deltas"), "deltas 只能是 auto／none 或清單 [{seg: 1, text: ..., tone: up}]")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.stacked100(bars, seg_spec, aria, sp.opt("desc", aria, "str"),
                            h=sp.opt("height", 250.0, "num"), deltas=deltas,
                            hint=sp.opt("hint", None, "str"), dark=tuple(sorted(dark)))


@figtype("ranked", "貢獻排序橫條（每根拆兩段）— svgchart.ranked_bars",
         ["data", "name", "parts", "colors", "sort", "unit", "total", "total_label"])
class Ranked:
    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        name_col = sp.opt("name", hdr[0], "str")
        if name_col not in hdr:
            raise DeclError(sp.ln("name"), f"資料裡沒有 `{name_col}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
        parts = [str(p) for p in sp.opt("parts", [h for h in hdr if h != name_col], "list")]
        if len(parts) != 2:
            raise DeclError(sp.ln("parts"), f"ranked 目前只支援剛好兩個部分（例如 段內效應／占比效應），現在是 {len(parts)} 個：{'、'.join(parts)}")
        p1 = numcol(rows, parts[0], hdr, sp.ln("parts"), src)
        p2 = numcol(rows, parts[1], hdr, sp.ln("parts"), src)
        names = [r[name_col] for r in rows]
        recs = [(n, a, b, a + b) for n, a, b in zip(names, p1, p2)]
        mode = sp.opt("sort", "abs", "str")
        if mode == "abs":
            recs.sort(key=lambda r: -abs(r[3]))
        elif mode != "none":
            raise DeclError(sp.ln("sort"), "sort 只能是 abs（依合計絕對值由大到小）或 none（照資料順序）")
        return {"x": [r[0] for r in recs], "labels": [r[0] for r in recs],
                "cols": {parts[0]: [r[1] for r in recs], parts[1]: [r[2] for r in recs],
                         "total": [r[3] for r in recs]},
                "parts": parts, "bk": None}

    @staticmethod
    def render(sp, store, ctx):
        parts = store["parts"]
        colors = sp.opt("colors", ["dn", "dn2"], "list")
        if len(colors) != 2:
            raise DeclError(sp.ln("colors"), "colors 要剛好兩個（對應兩個部分）")
        tots = store["cols"]["total"]
        total = sp.opt("total", None, "num")
        if total is None:
            total = 0.0
            for t in tots:
                total += t
        if total == 0:
            raise DeclError(sp.ln("data"), "合計是 0，沒法算占比")
        unit = sp.opt("unit", "分", "str")
        rows, cum = [], 0.0
        for i, name in enumerate(store["x"]):
            share = tots[i] / total
            cum += share
            rows.append((sp.expand(name, sp.ln("data")), store["cols"][parts[0]][i],
                         store["cols"][parts[1]][i], tots[i], share, cum))
        n = len(rows)
        cn = CN[n] if 0 < n <= 10 else str(n)
        label = sp.opt("total_label", f"{cn}格加總 = {S.fmt(total, 2, sign=True)} {unit}（恆等式成立）", "str")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.ranked_bars(
            rows, aria, sp.opt("desc", aria, "str"),
            parts=[(sp.expand(parts[0], sp.ln("parts")), color_cls(colors[0], sp.ln("colors"), "c-dn")),
                   (sp.expand(parts[1], sp.ln("parts")), color_cls(colors[1], sp.ln("colors"), "c-dn2"))],
            h=sp.opt("height", None, "num"), unit=unit, hint=sp.opt("hint", None, "str"),
            total=total, total_label=label)


@figtype("bars", "類別直立柱（含正負，中性色）— svgchart.vbars",
         ["data", "x", "y", "color", "unit", "nd", "zero", "value_label", "tip_extra"])
class Bars:
    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        xcol = sp.opt("x", hdr[0], "str")
        ycol = sp.opt("y", hdr[1] if len(hdr) > 1 else None, "str")
        if xcol not in hdr:
            raise DeclError(sp.ln("x"), f"資料裡沒有 `{xcol}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
        if ycol is None:
            raise DeclError(sp.ln("data"), "資料至少要兩欄：類別、數值")
        vals = numcol(rows, ycol, hdr, sp.ln("y"), src)
        cats = [r[xcol] for r in rows]
        return {"x": cats, "labels": cats, "cols": {ycol: vals}, "ycol": ycol, "bk": None}

    @staticmethod
    def render(sp, store, ctx):
        vals = store["cols"][store["ycol"]]
        nd, unit = sp.opt("nd", 2, "int"), sp.opt("unit", "分", "str")
        vlab = sp.opt("value_label", None, "str")
        extra = sp.opt("tip_extra", {}, "dict")
        tips = None
        if vlab is not None or extra:
            ex = [(sp.expand(str(k), sp.ln("tip_extra")), sp.expand(str(v), sp.ln("tip_extra")))
                  for k, v in extra.items()]
            tips = [[(vlab or "值", S.fmt(v, nd, sign=True) + " " + unit)] + ex for v in vals]
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.vbars([sp.expand(c, sp.ln("data")) for c in store["x"]], vals, aria,
                       sp.opt("desc", aria, "str"), h=sp.opt("height", 250.0, "num"), unit=unit, nd=nd,
                       cls=color_cls(sp.opt("color"), sp.ln("color"), "c-s2"),
                       zero=sp.opt("zero", True, "bool"), hint=sp.opt("hint", None, "str"), tips=tips)


# ---------------------------------------------------------------- v1.1 新增：留存曲線／分群長條／漏斗
def _series_items(sp, key, allowed, what, items=None):
    """series 每項可以是欄名字串（`series: [pre, post]`）或 `{col: …, name: …, color: …}`。
    字串會包成 {col: 字串}，行號沿用清單裡那一項的行。"""
    if items is None:
        items = sp.req(key, "list", "至少一條：series: [欄名1, 欄名2] 或 - {col: 欄名, name: 顯示名, color: s1}")
    out = []
    for i, it in enumerate(items):
        if isinstance(it, dict):
            out.append(sp.sub(key, i, it, allowed, f"{what} 第 {i + 1} 項"))
        elif isinstance(it, (str, int, float)) and not isinstance(it, bool):
            out.append(Spec({"col": str(it)}, sp.lnmap, sp.ln(key, i), allowed, sp.path + (key, i),
                            sp.expand, f"{what} 第 {i + 1} 項"))
        else:
            raise DeclError(sp.ln(key, i), f"`{key}` 的第 {i + 1} 項要是欄名或 {{col: 欄名, ...}}")
    return out


def _day_of(txt, ln, i):
    s = str(txt).strip()
    m = re.match(r"^(?:[Dd]|[Dd]ay\s*|第\s*)?(\d+)\s*(?:天|日)?$", s)
    if not m:
        raise DeclError(ln, f"第 {i} 列的 day `{txt}` 不是整數天數", "寫 1、3、7、14、30，或 D1、D3…（會照數字排序）")
    return int(m.group(1))


@figtype("retention", "留存曲線：D1/D3/D7/D14/D30 幾群的留存率（點標記＋類別 x 軸）— svgchart.xy_chart",
         ["data", "x", "xfmt", "xscale", "scale", "unit", "nd", "ylab", "ymin", "ymax",
          "series", "baseline", "markers"],
         {"series": ["col", "id", "name", "label", "color", "width", "dash", "order"]})
class Retention:
    SER = ["col", "id", "name", "label", "color", "width", "dash", "order"]

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        xcol = sp.opt("x", "day" if "day" in hdr else hdr[0], "str")
        if xcol not in hdr:
            raise DeclError(sp.ln("x"), f"資料裡沒有 day 欄 `{xcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        days = [_day_of(r[xcol], sp.ln("data"), i) for i, r in enumerate(rows, 2)]
        order = sorted(range(len(rows)), key=lambda i: days[i])
        days = [days[i] for i in order]
        rows = [rows[i] for i in order]
        dup = sorted({d for d in days if days.count(d) > 1})
        if dup:
            raise DeclError(sp.ln("data"), f"{src} 的 day 重複：{dup}", "每個 day 一列")
        if len(days) < 2:
            raise DeclError(sp.ln("data"), "留存曲線至少要兩個 day")
        items = _series_items(sp, "series", Retention.SER, "series")
        if not items:
            raise DeclError(sp.ln("series"), "series 是空的")
        scale = sp.opt("scale", "auto", "str")
        if scale not in ("auto", "ratio", "pct"):
            raise DeclError(sp.ln("scale"), "scale 只能是 auto（依最大值判斷）／ratio（0~1）／pct（0~100）")
        raw = {}
        for it in items:
            c = it.req("col", "str", "每條序列要有 col（資料欄名）")
            if c in raw:
                raise DeclError(it.ln("col"), f"序列 `{c}` 重複")
            raw[c] = numcol(rows, c, hdr, it.ln("col"), src)
        allv = [v for vs in raw.values() for v in vs]
        mode = scale
        if mode == "auto":
            mode = "ratio" if max(allv) <= 1.0 else "pct"
        top = 1.0 if mode == "ratio" else 100.0
        for it in items:
            c = it.obj["col"]
            for i, v in enumerate(raw[c], 2):
                if v < 0:
                    raise DeclError(it.ln("col"), f"{src} 第 {i} 列的 `{c}` 是負的（{v:g}），留存率不能是負數")
                if v > top:
                    raise DeclError(it.ln("col"),
                                    f"{src} 第 {i} 列的 `{c}` ＝ {v:g}，超過 {top:g}"
                                    f"（{'0~1 比例口徑' if mode == 'ratio' else '0~100 百分比口徑'}）",
                                    "留存率要是 0~1 的比例或 0~100 的百分比；資料是百分比就寫 scale: pct、是比例就寫 scale: ratio")
        cols = {c: ([v * 100.0 for v in vs] if mode == "ratio" else list(vs)) for c, vs in raw.items()}
        xfmt = sp.opt("xfmt", "D", "str")
        if xfmt not in ("D", "raw", "day"):
            raise DeclError(sp.ln("xfmt"), "xfmt 只能是 D（D1、D7）／day（1 天、7 天）／raw（照 csv 原文）")
        if xfmt == "D":
            labels = [f"D{d}" for d in days]
        elif xfmt == "day":
            labels = [f"{d} 天" for d in days]
        else:
            labels = [r[xcol] for r in rows]
        xscale = sp.opt("xscale", "category", "str")
        if xscale not in ("category", "value"):
            raise DeclError(sp.ln("xscale"), "xscale 只能是 category（等距，預設）或 value（照天數比例放）")
        bl = sp.opt("baseline", None, "str")
        if bl is not None:
            trios = [(it.obj["col"], it.opt("name", it.obj["col"], "str"), it.opt("id", it.obj["col"], "str")) for it in items]
            if not any(bl in t for t in trios):
                raise DeclError(sp.ln("baseline"), f"baseline `{bl}` 不是任何一條序列的 col／name／id",
                                f"序列：{'、'.join(t[0] for t in trios)}")
        return {"x": [str(d) for d in days], "labels": labels, "days": days, "cols": cols,
                "bk": None, "mode": mode, "xscale": xscale}

    @staticmethod
    def render(sp, store, ctx):
        unit = sp.opt("unit", "%", "str")
        if unit in ("pct", "percent", "百分比"):
            unit = "%"
        nd = sp.opt("nd", 1, "int")
        items = _series_items(sp, "series", Retention.SER, "series")
        if len(items) > 4:
            raise DeclError(sp.ln("series"), f"留存曲線最多 4 條序列（現在 {len(items)} 條）",
                            "序列 ≤4 用直接標註取代圖例是鎖定的設計決定；多的請拆兩張圖，或等 cohort 熱圖（規劃中）")
        bl = sp.opt("baseline", None, "str")
        markers = sp.opt("markers", True, "bool")
        defaults = ["s1", "s2", "s3"]
        ser, used = [], 0
        for i, it in enumerate(items):
            col = it.req("col", "str")
            name = it.opt("name", col, "str")
            sid = it.opt("id", col, "str")
            is_bl = bl is not None and bl in (col, name, sid)
            if it.has("color"):
                cls = color_cls(it.opt("color"), it.ln("color"), "c-s1")
            elif is_bl:
                cls = "c-ink"
            else:
                if used >= len(defaults):
                    raise DeclError(it.ln("col"), f"第 {i + 1} 條序列請指定 color（s1～s3 已用完）",
                                    "可用 ink／raw，或把其中一條設成 baseline（自動墨色虛線）")
                cls = COLORS[defaults[used]]
                used += 1
            lab = it.opt("label")
            if isinstance(lab, bool):
                endlab = False if lab is False else None
            else:
                endlab = it.expand(str(lab), it.ln("label")) if lab not in (None, "") else None
            ser.append(dict(type="line", key=sid, name=name, cls=cls,
                            w=it.opt("width", 1.8 if is_bl else 2.6, "num"),
                            dash=it.opt("dash", bool(is_bl), "bool"),
                            vals=store["cols"][col], unit=unit, nd=nd,
                            ord=it.opt("order", 0, "int"), endlab=endlab, marker=markers))
        xpos = None
        if store["xscale"] == "value":
            d = store["days"]
            span = (d[-1] - d[0]) or 1
            xpos = [(x - d[0]) / span for x in d]
        ymin, ymax = sp.opt("ymin", 0.0, "num"), sp.opt("ymax", None, "num")
        hi = max(v for s in ser for v in s["vals"]) if ymax is None else ymax
        ticks, _, _ = S.nice_ticks(ymin, hi + (hi - ymin) * .08 if ymax is None else hi, 5)
        ylab_fmt = 0 if all(float(t).is_integer() for t in ticks) else 1
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.xy_chart(store["labels"], ser, aria, sp.opt("desc", aria, "str"),
                          ylab=sp.opt("ylab", "留存率（%）", "str"), h=sp.opt("height", 360.0, "num"),
                          ymin=ymin, ymax=ymax, bk=None, hlines=[], xtick_every=1, ylab_fmt=ylab_fmt,
                          xpos=xpos,
                          hint=sp.opt("hint", "滑過看各群在該天的留存率・點右側標註可切換序列", "str"))


@figtype("grouped", "分群長條：類別 × 序列並排（例 底台 × pre/post，可加 ▲▼ 變化）— svgchart.grouped_bars",
         ["data", "x", "series", "colors", "unit", "nd", "ylab", "ymin", "ymax", "zero",
          "value_label", "delta"],
         {"series": ["col", "id", "name", "color"],
          "delta": ["a", "b", "mode", "nd", "unit", "label"]})
class Grouped:
    SER = ["col", "id", "name", "color"]
    DELTA = ["a", "b", "mode", "nd", "unit", "label"]

    @staticmethod
    def _items(sp, cols_avail):
        if sp.has("series"):
            return _series_items(sp, "series", Grouped.SER, "series")
        return [Spec({"col": c}, sp.lnmap, sp.ln("data"), Grouped.SER, sp.path + ("series", i),
                     sp.expand, f"series 第 {i + 1} 項") for i, c in enumerate(cols_avail)]

    @staticmethod
    def _delta_spec(sp):
        d = sp.opt("delta", None, "dict")
        if d is None:
            return None
        return Spec(d, sp.lnmap, sp.ln("delta"), Grouped.DELTA, sp.path + ("delta",), sp.expand, "delta ")

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        xcol = sp.opt("x", hdr[0], "str")
        if xcol not in hdr:
            raise DeclError(sp.ln("x"), f"資料裡沒有 `{xcol}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
        items = Grouped._items(sp, [h for h in hdr if h != xcol])
        where = sp.ln("series") if sp.has("series") else sp.ln("data")
        if len(items) < 2:
            raise DeclError(where, f"分群長條至少要兩條序列（現在 {len(items)} 條）", "只有一個數值欄請改用 type: bars")
        if len(items) > 3:
            raise DeclError(where, f"分群長條最多 3 條序列（現在 {len(items)} 條，中性藍 s1～s3 用完）",
                            "多的請拆兩張圖、改成表格，或等堆疊長條（規劃中）")
        cols, sers = {}, []
        for it in items:
            c = it.req("col", "str", "每條序列要有 col（資料欄名）")
            if c in cols:
                raise DeclError(it.ln("col"), f"序列 `{c}` 重複")
            cols[c] = numcol(rows, c, hdr, it.ln("col"), src)
            sers.append((c, it.opt("name", c, "str"), it.opt("id", c, "str")))
        cats = [r[xcol] for r in rows]
        store = {"x": cats, "labels": cats, "cols": cols, "bk": None, "sers": sers, "delta": None}
        ds = Grouped._delta_spec(sp)
        if ds is not None:
            def pick(k, default):
                v = ds.opt(k, default, "str")
                for t in sers:
                    if v in t:
                        return t[0]
                raise DeclError(ds.ln(k), f"delta 的 {k} `{v}` 不是任何一條序列的 col／name／id",
                                f"序列：{'、'.join(t[0] for t in sers)}")
            a, b = pick("a", sers[0][0]), pick("b", sers[1][0])
            mode = ds.opt("mode", "pct", "str")
            if mode not in ("pct", "diff"):
                raise DeclError(ds.ln("mode"), "mode 只能是 pct（變化率 %，(b/a−1)×100）或 diff（差值 b−a）")
            vals = []
            for va, vb in zip(cols[a], cols[b]):
                if mode == "pct":
                    vals.append(None if va == 0 else (vb / va - 1) * 100)
                else:
                    vals.append(vb - va)
            store["delta"] = vals
            if "delta" not in cols and all(v is not None for v in vals):
                store["cols"]["delta"] = list(vals)          # 給 {{v:}} 計算式用（col: delta）
        return store

    @staticmethod
    def render(sp, store, ctx):
        items = _series_items(sp, "series", Grouped.SER, "series") if sp.has("series") else None
        colors = sp.opt("colors", None, "list")
        if colors is not None and len(colors) != len(store["sers"]):
            raise DeclError(sp.ln("colors"), f"colors 有 {len(colors)} 個，但序列有 {len(store['sers'])} 條")
        defaults = ["s1", "s2", "s3"]
        series = []
        for i, (col, name, sid) in enumerate(store["sers"]):
            it = items[i] if items else None
            if it is not None and it.has("color"):
                cls = color_cls(it.opt("color"), it.ln("color"), "c-s1")
            elif colors is not None:
                cls = color_cls(colors[i], sp.ln("colors"), "c-s1")
            else:
                cls = COLORS[defaults[i]]
            if it is not None:
                name = it.opt("name", col, "str")
            series.append(dict(key=sid, name=name, cls=cls, vals=store["cols"][col]))
        unit, nd = sp.opt("unit", "", "str"), sp.opt("nd", 1, "int")
        deltas, dlabel = None, "變化"
        ds = Grouped._delta_spec(sp)
        if ds is not None:
            mode = ds.opt("mode", "pct", "str")
            dnd = ds.opt("nd", 1, "int")
            dunit = ds.opt("unit", "%" if mode == "pct" else unit, "str")
            dlabel = ds.opt("label", "變化", "str")
            sep = "" if (dunit in ("%", "") or dunit.startswith(" ")) else " "   # 單位自帶空格就不再補
            deltas = []
            for v in store["delta"]:
                if v is None:
                    deltas.append(("N/A", "ink"))
                    continue
                arrow = "▲" if v > 0 else ("▼" if v < 0 else "–")
                tone = "up" if v > 0 else ("dn" if v < 0 else "ink")
                num = f"{v:+.{dnd}f}" if v != 0 else f"{0:.{dnd}f}"
                deltas.append((f"{arrow} {num}{sep}{dunit}", tone))
        vl = sp.opt("value_label", "auto")
        if vl not in (True, False, "auto"):
            raise DeclError(sp.ln("value_label"), "value_label 只能是 true／false／auto（柱夠寬才標）")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.grouped_bars(
            [sp.expand(c, sp.ln("data")) for c in store["x"]], series, aria, sp.opt("desc", aria, "str"),
            h=sp.opt("height", 300.0, "num"), unit=unit, nd=nd, zero=sp.opt("zero", True, "bool"),
            deltas=deltas, value_labels=vl, hint=sp.opt("hint", None, "str"),
            ylab=sp.opt("ylab", "", "str"), ymin=sp.opt("ymin", None, "num"),
            ymax=sp.opt("ymax", None, "num"), delta_label=dlabel)


@figtype("funnel", "漏斗：步驟由上而下的人數、占第一步 %、占上一步 %（最大流失步驟強調）— svgchart.funnel",
         ["data", "step", "count", "unit", "nd", "show", "emph", "emph_label", "allow_increase",
          "color", "total_label"])
class Funnel:
    SHOW = ["count", "pct_first", "pct_prev"]

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        scol = sp.opt("step", "step" if "step" in hdr else hdr[0], "str")
        ccol = sp.opt("count", "count" if "count" in hdr else (hdr[1] if len(hdr) > 1 else None), "str")
        if scol not in hdr:
            raise DeclError(sp.ln("step"), f"資料裡沒有步驟欄 `{scol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        if ccol is None:
            raise DeclError(sp.ln("data"), "資料至少要兩欄：步驟、人數", f"{src} 的欄位：{'、'.join(hdr)}")
        if ccol not in hdr:
            raise DeclError(sp.ln("count"), f"資料裡沒有人數欄 `{ccol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        counts = numcol(rows, ccol, hdr, sp.ln("count"), src)
        names = [r[scol] for r in rows]
        if len(names) < 2:
            raise DeclError(sp.ln("data"), "漏斗至少要兩步")
        for i, nm in enumerate(names, 2):
            if not nm.strip():
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的步驟名是空的")
        if counts[0] <= 0:
            raise DeclError(sp.ln("data"), f"{src} 第 2 列（第一步「{names[0]}」）的人數是 {counts[0]:g}，第一步要 > 0 才能算占比")
        allow = sp.opt("allow_increase", False, "bool")
        for i in range(1, len(counts)):
            if counts[i] < 0:
                raise DeclError(sp.ln("data"), f"{src} 第 {i + 2} 列「{names[i]}」的人數是負的（{counts[i]:g}）")
            if counts[i] > counts[i - 1] and not allow:
                raise DeclError(sp.ln("data"),
                                f"{src} 第 {i + 2} 列「{names[i]}」的人數 {S.fmt(counts[i], 0)} 比上一步「{names[i - 1]}」"
                                f"的 {S.fmt(counts[i - 1], 0)} 多——漏斗每一步不能比上一步多",
                                "先確認步驟順序與口徑（同一批人？有去重？）；資料本來就會回升（可重複進入）才寫 "
                                "allow_increase: true，並在 note_extra 說明")
        pf = [c / counts[0] * 100.0 for c in counts]
        pp = [100.0] + [(counts[i] / counts[i - 1] * 100.0) if counts[i - 1] else 0.0 for i in range(1, len(counts))]
        return {"x": names, "labels": names, "bk": None,
                "cols": {"count": counts, "pct_first": pf, "pct_prev": pp, "loss_prev": [100.0 - v for v in pp]}}

    @staticmethod
    def render(sp, store, ctx):
        show = sp.opt("show", list(Funnel.SHOW), "list")
        show = [str(s) for s in show]
        bad = [s for s in show if s not in Funnel.SHOW]
        if bad or not show:
            raise DeclError(sp.ln("show"), f"show 只能列 {'、'.join(Funnel.SHOW)}（現在有 {bad[0]!r}）" if bad else "show 不能是空的")
        names, pp = store["x"], store["cols"]["pct_prev"]
        emph = sp.opt("emph", "auto")
        idx = None
        if emph == "auto":
            losses = [(pp[i], i) for i in range(1, len(names)) if pp[i] < 100.0]
            idx = min(losses)[1] if losses else None
        elif emph in ("none", False):
            idx = None
        elif isinstance(emph, int) and not isinstance(emph, bool):
            if not 1 <= emph <= len(names):
                raise DeclError(sp.ln("emph"), f"emph 的 {emph} 不是 1~{len(names)} 的步驟序號（從 1 數）")
            idx = emph - 1
        elif str(emph) in names:
            idx = names.index(str(emph))
        else:
            raise DeclError(sp.ln("emph"), f"emph 只能是 auto（流失最大那步）／none／步驟序號／步驟名（現在是 {emph!r}）",
                            f"步驟：{'、'.join(names)}")
        tl = sp.opt("total_label", None)
        if tl in ("none", False):
            tl = False
        elif tl is not None:
            tl = sp.expand(str(tl), sp.ln("total_label"))
        steps = [(sp.expand(nm, sp.ln("data")), store["cols"]["count"][i], store["cols"]["pct_first"][i], pp[i])
                 for i, nm in enumerate(names)]
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.funnel(steps, aria, sp.opt("desc", aria, "str"), h=sp.opt("height", None, "num"),
                        unit=sp.opt("unit", "人", "str"), nd=sp.opt("nd", 0, "int"), show=show, emph=idx,
                        hint=sp.opt("hint", None, "str"), cls=color_cls(sp.opt("color"), sp.ln("color"), "c-s1"),
                        total_label=tl, emph_text=sp.opt("emph_label", "最大流失", "str"))


# ---------------------------------------------------------------- v1.2 新增：堆疊長條（絕對值）／cohort 留存熱圖
@figtype("stacked", "堆疊長條（絕對值）：類別 × 2～5 段疊加、柱頂合計，可標兩個類別合計的 ▲▼ 變化 — svgchart.stacked_bars",
         ["data", "x", "segments", "colors", "unit", "nd", "ylab", "ymin", "ymax",
          "total_label", "seg_label", "delta"],
         {"segments": ["col", "id", "name", "color"],
          "delta": ["a", "b", "mode", "nd", "unit", "label"]})
class Stacked:
    SEG = ["col", "id", "name", "color"]
    DELTA = ["a", "b", "mode", "nd", "unit", "label"]
    PALETTE = ["s1", "s2", "s3", "s4", "s5"]

    @staticmethod
    def _items(sp, cols_avail):
        if sp.has("segments"):
            return _series_items(sp, "segments", Stacked.SEG, "segments")
        return [Spec({"col": c}, sp.lnmap, sp.ln("data"), Stacked.SEG, sp.path + ("segments", i),
                     sp.expand, f"segments 第 {i + 1} 項") for i, c in enumerate(cols_avail)]

    @staticmethod
    def _delta_spec(sp):
        d = sp.opt("delta", None, "dict")
        if d is None:
            return None
        return Spec(d, sp.lnmap, sp.ln("delta"), Stacked.DELTA, sp.path + ("delta",), sp.expand, "delta ")

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        xcol = sp.opt("x", hdr[0], "str")
        if xcol not in hdr:
            raise DeclError(sp.ln("x"), f"資料裡沒有 `{xcol}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
        items = Stacked._items(sp, [h for h in hdr if h != xcol])
        where = sp.ln("segments") if sp.has("segments") else sp.ln("data")
        if len(items) < 2:
            raise DeclError(where, f"堆疊長條至少要兩段（現在 {len(items)} 段）", "只有一個數值欄請改用 type: bars")
        if len(items) > 5:
            raise DeclError(where, f"堆疊長條最多 5 段（現在 {len(items)} 段，同色系深淺 s1～s5 用完）",
                            "把小的段合併成「其他」，或改成表格（```table）")
        cats = [r[xcol] for r in rows]
        for i, c in enumerate(cats, 2):
            if not c.strip():
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{xcol}`（類別）是空的")
        dup = sorted({c for c in cats if cats.count(c) > 1})
        if dup:
            raise DeclError(sp.ln("data"), f"{src} 的類別 `{xcol}` 有重複：{'、'.join(dup)}",
                            "每個類別一列；同一類別的不同段要放在同一列的不同欄")
        cols, segs = {}, []
        for it in items:
            c = it.req("col", "str", "每一段要有 col（資料欄名）")
            if c in cols:
                raise DeclError(it.ln("col"), f"段 `{c}` 重複")
            vals = numcol(rows, c, hdr, it.ln("col"), src)
            for i, v in enumerate(vals, 2):
                if v < 0:
                    raise DeclError(it.ln("col"),
                                    f"{src} 第 {i} 列的 `{c}` 是負的（{v:g}）——堆疊長條的段不能是負值",
                                    "負值沒法往上疊；有正負的量請用 type: bars（單一數值）或 grouped（並排），"
                                    "或先把口徑改成非負（例如絕對量、人數）")
            cols[c] = vals
            segs.append((c, it.opt("name", c, "str"), it.opt("id", c, "str")))
        totals = [sum(cols[c][i] for c in cols) for i in range(len(cats))]
        store = {"x": cats, "labels": cats, "cols": dict(cols), "bk": None, "segs": segs, "delta": None,
                 "totals": totals}
        if "total" not in store["cols"]:
            store["cols"]["total"] = totals        # 給 {{v:}} 計算式用（col: total）
        ds = Stacked._delta_spec(sp)
        if ds is not None:
            def pick(k):
                v = ds.req(k, "str", "delta 要指定兩個類別：a（基準）與 b（比較），寫 x 欄裡的值")
                if v not in cats:
                    raise DeclError(ds.ln(k), f"delta 的 {k} `{v}` 不是任何一個類別（`{xcol}` 欄的值）",
                                    f"類別：{'、'.join(cats)}")
                return cats.index(v)
            ia, ib = pick("a"), pick("b")
            if ia == ib:
                raise DeclError(ds.ln("b"), "delta 的 a 與 b 是同一個類別")
            mode = ds.opt("mode", "pct", "str")
            if mode not in ("pct", "diff"):
                raise DeclError(ds.ln("mode"), "mode 只能是 pct（變化率 %，(b/a−1)×100）或 diff（差值 b−a）")
            ta, tb = totals[ia], totals[ib]
            val = (None if ta == 0 else (tb / ta - 1) * 100) if mode == "pct" else (tb - ta)
            store["delta"] = (ia, ib, val, mode)
        return store

    @staticmethod
    def render(sp, store, ctx):
        items = _series_items(sp, "segments", Stacked.SEG, "segments") if sp.has("segments") else None
        colors = sp.opt("colors", None, "list")
        if colors is not None and len(colors) != len(store["segs"]):
            raise DeclError(sp.ln("colors"), f"colors 有 {len(colors)} 個，但段有 {len(store['segs'])} 個")
        segs = []
        for i, (col, name, sid) in enumerate(store["segs"]):
            it = items[i] if items else None
            role = Stacked.PALETTE[i]
            default = SHADES.get(role, (COLORS.get(role, "c-s1"), None))
            if it is not None and it.has("color"):
                cls, fo = color_fill(it.opt("color"), it.ln("color"), default)
            elif colors is not None:
                cls, fo = color_fill(colors[i], sp.ln("colors"), default)
            else:
                cls, fo = default
            if it is not None:
                name = it.opt("name", col, "str")
            segs.append(dict(key=sid, name=name, cls=cls, fo=fo, vals=store["cols"][col]))
        unit, nd = sp.opt("unit", "", "str"), sp.opt("nd", 1, "int")
        ymin = sp.opt("ymin", 0.0, "num")
        if ymin > 0:
            raise DeclError(sp.ln("ymin"), f"堆疊長條的 y 軸要從 0 起（ymin 現在是 {ymin:g}）",
                            "柱狀量不截斷 y 軸是鎖定的設計決定；ymin 只能是 0 或負數")
        delta = None
        ds = Stacked._delta_spec(sp)
        if ds is not None and store["delta"] is not None:
            ia, ib, val, mode = store["delta"]
            dnd = ds.opt("nd", 1, "int")
            dunit = ds.opt("unit", "%" if mode == "pct" else unit, "str")
            sep = "" if (dunit in ("%", "") or dunit.startswith(" ")) else " "
            if val is None:
                text, tone = "N/A", "ink"
            else:
                arrow = "▲" if val > 0 else ("▼" if val < 0 else "–")
                tone = "up" if val > 0 else ("dn" if val < 0 else "ink")
                num = f"{val:+,.{dnd}f}" if val != 0 else f"{0:.{dnd}f}"
                text = f"{arrow} {num}{sep}{dunit}"
            delta = dict(a=ia, b=ib, text=text, tone=tone, label=ds.opt("label", "變化", "str"))
        for k in ("total_label", "seg_label"):
            v = sp.opt(k, "auto")
            if v not in (True, False, "auto"):
                raise DeclError(sp.ln(k), f"{k} 只能是 true／false／auto（柱夠寬才標）")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.stacked_bars(
            [sp.expand(c, sp.ln("data")) for c in store["x"]], segs, aria, sp.opt("desc", aria, "str"),
            h=sp.opt("height", 300.0, "num"), unit=unit, nd=nd, ylab=sp.opt("ylab", "", "str"),
            ymin=ymin, ymax=sp.opt("ymax", None, "num"), total_labels=sp.opt("total_label", "auto"),
            seg_labels=sp.opt("seg_label", "auto"), delta=delta, hint=sp.opt("hint", None, "str"))


_MISSING = {"", "-", "—", "–", "na", "n/a", "nan", "null", "none"}


def _day_hdr(txt):
    m = re.match(r"^(?:[Dd]|[Dd]ay\s*|第\s*)?(\d+)\s*(?:天|日)?$", str(txt).strip())
    return int(m.group(1)) if m else None


@figtype("cohort", "cohort 留存熱圖：cohort（列）× 天數位移（欄）的留存率格子，單色亮度階、允許缺值 — svgchart.heatmap",
         ["data", "cohort", "size", "show_size", "days", "scale", "unit", "nd", "value_label", "highlight_day"])
class Cohort:
    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        ccol = sp.opt("cohort", hdr[0], "str")
        if ccol not in hdr:
            raise DeclError(sp.ln("cohort"), f"資料裡沒有 cohort 欄 `{ccol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        size_opt = sp.opt("size", None)
        if size_opt in (False, "none"):
            scol = None
        elif size_opt is None:
            scol = next((h for h in hdr if h.strip().lower() in ("size", "n", "人數", "cohort_size", "users")), None)
        else:
            scol = str(size_opt)
            if scol not in hdr:
                raise DeclError(sp.ln("size"), f"資料裡沒有 size 欄 `{scol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        if sp.has("days"):
            day_cols = [str(d) for d in sp.req("days", "list")]
            miss = [d for d in day_cols if d not in hdr]
            if miss:
                raise DeclError(sp.ln("days"), f"days 裡的 `{miss[0]}` 不是資料的欄名", f"{src} 的欄位：{'、'.join(hdr)}")
            where = sp.ln("days")
        else:
            day_cols = [h for h in hdr if h not in (ccol, scol)]
            where = sp.ln("data")
        if len(day_cols) < 2:
            raise DeclError(where, f"cohort 熱圖至少要兩個天數欄（現在 {len(day_cols)} 個）",
                            "csv 形狀：第一欄 cohort，其餘每欄一個天數位移（D0、D1、D3、D7…），可選 size 欄")
        days = []
        for hcol in day_cols:
            d = _day_hdr(hcol)
            if d is None:
                raise DeclError(where, f"欄 `{hcol}` 不是天數欄（欄名要像 D0、D7、Day 7 或 7）",
                                "不是天數的欄：cohort 人數用 size: 欄名 指名；其他欄用 days: [D1, D3, D7, …] 挑出要畫的欄")
            days.append(d)
        by_day = {}
        for hcol, d in zip(day_cols, days):
            by_day.setdefault(d, []).append(hcol)
        dups = {d: cs for d, cs in by_day.items() if len(cs) > 1}
        if dups:
            d, cs = sorted(dups.items())[0]
            raise DeclError(where, f"{src} 的天數欄重複：D{d} 同時出現在 `{'`、`'.join(cs)}` 這 {len(cs)} 欄",
                            "每個天數位移一欄；欄名 D7 與 7 是同一天")
        order = sorted(range(len(days)), key=lambda i: days[i])
        day_cols = [day_cols[i] for i in order]
        days = [days[i] for i in order]
        cohorts = [r[ccol] for r in rows]
        for i, c in enumerate(cohorts, 2):
            if not c.strip():
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 cohort 標籤是空的")
        seen = {}
        for i, c in enumerate(cohorts, 2):
            if c in seen:
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 cohort `{c}` 與第 {seen[c]} 列重複",
                                "每個 cohort 一列；同一 cohort 的不同天數要放在同一列的不同欄")
            seen[c] = i
        grid = []
        for i, r in enumerate(rows, 2):
            line = []
            for hcol in day_cols:
                sv = r[hcol].strip()
                if sv.lower() in _MISSING:
                    line.append(None)
                    continue
                try:
                    line.append(float(sv.replace(",", "").rstrip("%")))
                except ValueError:
                    raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{hcol}` 不是數字：{r[hcol]!r}",
                                    "尚未觀察到的天數留空白即可（會畫成空白格）")
            grid.append(line)
        allv = [v for line in grid for v in line if v is not None]
        if not allv:
            raise DeclError(sp.ln("data"), f"{src} 沒有任何留存率數值（全部是空白）")
        scale = sp.opt("scale", "auto", "str")
        if scale not in ("auto", "ratio", "pct"):
            raise DeclError(sp.ln("scale"), "scale 只能是 auto（依最大值判斷）／ratio（0~1）／pct（0~100）")
        mode = scale if scale != "auto" else ("ratio" if max(allv) <= 1.0 else "pct")
        top = 1.0 if mode == "ratio" else 100.0
        for i, line in enumerate(grid, 2):
            for hcol, v in zip(day_cols, line):
                if v is None:
                    continue
                if v < 0:
                    raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{hcol}` 是負的（{v:g}），留存率不能是負數")
                if v > top:
                    raise DeclError(sp.ln("data"),
                                    f"{src} 第 {i} 列的 `{hcol}` ＝ {v:g}，超過 {top:g}"
                                    f"（{'0~1 比例口徑' if mode == 'ratio' else '0~100 百分比口徑'}）",
                                    "留存率要是 0~1 的比例或 0~100 的百分比；資料是百分比就寫 scale: pct、是比例就寫 scale: ratio")
        if mode == "ratio":
            grid = [[None if v is None else v * 100.0 for v in line] for line in grid]
        sizes = None
        if scol:
            sizes = []
            for i, r in enumerate(rows, 2):
                sv = r[scol].strip()
                if sv.lower() in _MISSING:
                    sizes.append(None)
                    continue
                try:
                    sizes.append(float(sv.replace(",", "")))
                except ValueError:
                    raise DeclError(sp.ln("size"), f"{src} 第 {i} 列的 `{scol}`（cohort 人數）不是數字：{r[scol]!r}")
        hl = None
        if sp.has("highlight_day"):
            hv = sp.req("highlight_day")
            d = _day_hdr(hv)
            if d is None or d not in days:
                raise DeclError(sp.ln("highlight_day"), f"highlight_day `{hv}` 不是資料裡的天數",
                                f"可用：{'、'.join('D%d' % x for x in days)}")
            hl = days.index(d)
        cols = {f"D{d}": [line[j] for line in grid] for j, d in enumerate(days)}
        if sizes is not None and "size" not in cols:
            cols["size"] = sizes
        return {"x": cohorts, "labels": cohorts, "cols": cols, "bk": None, "days": days,
                "grid": grid, "sizes": sizes, "hl": hl, "mode": mode}

    @staticmethod
    def render(sp, store, ctx):
        unit = sp.opt("unit", "%", "str")
        if unit in ("pct", "percent", "百分比"):
            unit = "%"
        nd = sp.opt("nd", 1, "int")
        vl = sp.opt("value_label", "auto")
        if vl not in (True, False, "auto"):
            raise DeclError(sp.ln("value_label"), "value_label 只能是 true／false／auto（依格寬決定）")
        show_size = sp.opt("show_size", True, "bool")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.heatmap([sp.expand(c, sp.ln("data")) for c in store["x"]], store["days"], store["grid"],
                         aria, sp.opt("desc", aria, "str"), h=sp.opt("height", None, "num"),
                         sizes=store["sizes"] if show_size else None, unit=unit, nd=nd,
                         value_labels=vl, highlight=store["hl"], hint=sp.opt("hint", None, "str"))


@figtype("sigheat", "顯著度熱圖：列＝指標、欄＝任意分組（版本／族群／時段），單色亮度階、值越大底色越深 — svgchart.heatmap（v1.4）",
         ["data", "row", "cols", "unit", "nd", "legend_title", "value_label", "highlight_col"])
class SigHeat:
    """`table` 沒有格子底色、`cohort` 的欄只吃天數，所以另立一型給「檢定統計量的熱力圖」。
    畫法完全沿用 svgchart.heatmap（單色藍亮度階、色盲安全、不用紅綠）。v1.4 新增。"""

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        rcol = sp.opt("row", hdr[0], "str")
        if rcol not in hdr:
            raise DeclError(sp.ln("row"), f"資料裡沒有列標籤欄 `{rcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        if sp.has("cols"):
            vcols = [str(c) for c in sp.req("cols", "list")]
            miss = [c for c in vcols if c not in hdr]
            if miss:
                raise DeclError(sp.ln("cols"), f"cols 裡的 `{miss[0]}` 不是資料的欄名",
                                f"{src} 的欄位：{'、'.join(hdr)}")
        else:
            vcols = [h for h in hdr if h != rcol]
        if len(vcols) < 2:
            raise DeclError(sp.ln("data"), f"顯著度熱圖至少要兩個數值欄（現在 {len(vcols)} 個）")
        labels = [r[rcol] for r in rows]
        seen = {}
        for i, c in enumerate(labels, 2):
            if not c.strip():
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的列標籤是空的")
            if c in seen:
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的列標籤 `{c}` 與第 {seen[c]} 列重複")
            seen[c] = i
        grid = []
        for i, r in enumerate(rows, 2):
            line = []
            for c in vcols:
                sv = r[c].strip()
                if sv.lower() in _MISSING:
                    line.append(None)
                    continue
                try:
                    v = float(sv.replace(",", ""))
                except ValueError:
                    raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{c}` 不是數字：{r[c]!r}",
                                    "顯著度熱圖的格子是檢定統計量（例 |t|）；沒做檢定就留空白")
                if v < 0:
                    raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{c}` 是負的（{v:g}）",
                                    "色階是「值越大越深」，請填絕對值（|t|）或 -log10(p)")
                line.append(v)
            grid.append(line)
        if not [v for line in grid for v in line if v is not None]:
            raise DeclError(sp.ln("data"), f"{src} 沒有任何數值")
        cols = {c: [line[j] for line in grid] for j, c in enumerate(vcols)}
        return {"x": labels, "labels": labels, "cols": cols, "bk": None,
                "grid": grid, "vcols": vcols}

    @staticmethod
    def render(sp, store, ctx):
        vl = sp.opt("value_label", "auto")
        if vl not in (True, False, "auto"):
            raise DeclError(sp.ln("value_label"), "value_label 只能是 true／false／auto")
        hl = None
        if sp.has("highlight_col"):
            hv = str(sp.req("highlight_col"))
            if hv not in store["vcols"]:
                raise DeclError(sp.ln("highlight_col"), f"highlight_col `{hv}` 不是資料的欄名",
                                f"這張圖的數值欄：{'、'.join(store['vcols'])}")
            hl = store["vcols"].index(hv)
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        n = len(store["vcols"])
        return S.heatmap(store["labels"], list(range(n)), store["grid"], aria,
                         sp.opt("desc", aria, "str"), h=sp.opt("height", None, "num"),
                         sizes=None, unit=sp.opt("unit", "", "str"), nd=sp.opt("nd", 2, "int"),
                         value_labels=vl, highlight=hl, hint=sp.opt("hint", None, "str"),
                         legend_title=sp.opt("legend_title", "|t|", "str"),
                         col_labels=store["vcols"], col_key="分組", col_tips=store["vcols"],
                         missing_note="空白＝沒有做檢定（不是 0）")


# ---------------------------------------------------------------- v1.3 新增：直方圖＋分位線／pre-post 啞鈴／星期×小時熱圖
def _num_or_none(sv, ln, src, i, col):
    s = str(sv).strip()
    if s.lower() in _MISSING:
        return None
    try:
        return float(s.replace(",", "").rstrip("%"))
    except ValueError:
        raise DeclError(ln, f"{src} 第 {i} 列的 `{col}` 不是數字：{sv!r}")


def _quantile_sorted(s, q):
    """已排序清單的分位數（線性插補，同 numpy 預設 type 7）。q 是 0～100。"""
    if not s:
        return None
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _quantile_binned(edges, counts, q):
    """已分箱資料的分位數：找到累計人數跨過 q% 的那一箱，箱內線性插補（估算值）。"""
    total = float(sum(counts))
    target = total * q / 100.0
    cum = 0.0
    for i, c in enumerate(counts):
        if c <= 0:
            continue
        if cum + c >= target:
            frac = (target - cum) / c if c else 0.0
            return edges[i] + (edges[i + 1] - edges[i]) * max(0.0, min(1.0, frac))
        cum += c
    return edges[-1]


@figtype("hist", "直方圖＋分位線：raw 值自動分箱（bins／edges）或已分箱 bin_start,bin_end,count；p25/p50/p75/p90 虛線 ＋ mean；1～2 組半透明疊圖 — svgchart.histogram",
         ["data", "value", "group", "bins", "edges", "clip", "bin_start", "bin_end", "count",
          "quantiles", "mean", "unit", "nd", "xlab", "ylab", "yscale", "colors"])
class Hist:
    MAXG = 2

    @staticmethod
    def _edges_from(sp):
        if sp.has("edges") and sp.has("bins"):
            raise DeclError(sp.ln("bins"), "bins 與 edges 只能寫一個", "bins: 20 讓程式等寬分箱；edges: [0, 5, 10, …] 自己給箱界")
        if sp.has("edges"):
            raw = sp.req("edges", "list")
            if len(raw) < 2:
                raise DeclError(sp.ln("edges"), f"edges 至少要兩個數（現在 {len(raw)} 個）", "K 箱要 K+1 個箱界")
            edges = []
            for k, e in enumerate(raw):
                if isinstance(e, bool) or not isinstance(e, (int, float)):
                    raise DeclError(sp.ln("edges"), f"edges 第 {k + 1} 個 {e!r} 不是數字")
                edges.append(float(e))
            for k in range(1, len(edges)):
                if edges[k] <= edges[k - 1]:
                    raise DeclError(sp.ln("edges"), f"edges 要嚴格遞增：第 {k} 個 {edges[k-1]:g} ≥ 第 {k + 1} 個 {edges[k]:g}",
                                    "由小到大、不可重複；負值可以")
            return edges
        return None

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        lower = [h.lower() for h in hdr]
        binned = (sp.has("bin_start") or sp.has("bin_end") or sp.has("count")
                  or ("bin_start" in lower and "bin_end" in lower))
        gcol = sp.opt("group", None, "str")
        if gcol is not None and gcol not in hdr:
            raise DeclError(sp.ln("group"), f"資料裡沒有 group 欄 `{gcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        # 分組（≤ 2 組，依出現順序）
        if gcol:
            gnames = []
            for i, r in enumerate(rows, 2):
                g = r[gcol].strip()
                if not g:
                    raise DeclError(sp.ln("group"), f"{src} 第 {i} 列的 `{gcol}`（組別）是空的")
                if g not in gnames:
                    gnames.append(g)
            if len(gnames) > Hist.MAXG:
                raise DeclError(sp.ln("group"), f"直方圖疊圖最多 {Hist.MAXG} 組（`{gcol}` 有 {len(gnames)} 組：{'、'.join(gnames[:6])}{'…' if len(gnames) > 6 else ''}）",
                                "兩組以上重疊就分不開；請拆成多張圖、只留要比的兩組，或改用 grouped／table")
        else:
            gnames = [""]
        quants = []
        for k, q in enumerate(sp.opt("quantiles", [], "list")):
            if isinstance(q, bool) or not isinstance(q, (int, float)) or not 0 < q < 100:
                raise DeclError(sp.ln("quantiles"), f"quantiles 第 {k + 1} 個 {q!r} 要是 0～100 之間的數（例 25、50、75、90）")
            quants.append(float(q))
        want_mean = sp.opt("mean", False, "bool")
        groups = []
        if binned:
            scol = sp.opt("bin_start", "bin_start", "str")
            ecol = sp.opt("bin_end", "bin_end", "str")
            ccol = sp.opt("count", "count", "str")
            for c, k in ((scol, "bin_start"), (ecol, "bin_end"), (ccol, "count")):
                if c not in hdr:
                    raise DeclError(sp.ln(k) if sp.has(k) else sp.ln("data"), f"資料裡沒有 `{c}` 這一欄",
                                    f"已分箱資料要有 bin_start,bin_end,count 三欄（或用 bin_start:／bin_end:／count: 指名）；{src} 的欄位：{'、'.join(hdr)}")
            ln = sp.ln("data")
            per = {g: [] for g in gnames}
            for i, r in enumerate(rows, 2):
                g = r[gcol].strip() if gcol else ""
                s0 = _num_or_none(r[scol], ln, src, i, scol)
                e0 = _num_or_none(r[ecol], ln, src, i, ecol)
                c0 = _num_or_none(r[ccol], ln, src, i, ccol)
                if s0 is None or e0 is None or c0 is None:
                    raise DeclError(ln, f"{src} 第 {i} 列有空值（bin_start／bin_end／count 都要有）")
                if c0 < 0:
                    raise DeclError(ln, f"{src} 第 {i} 列的 `{ccol}` 是負的（{c0:g}）——人數不能是負數", "直方圖的 count 一律 ≥ 0；負值多半是抄錯或差值欄")
                if e0 <= s0:
                    raise DeclError(ln, f"{src} 第 {i} 列的箱界不對：bin_end {e0:g} ≤ bin_start {s0:g}")
                per[g].append((s0, e0, c0, i))
            edges_ref = None
            for g in gnames:
                bins = sorted(per[g])
                if not bins:
                    raise DeclError(ln, f"組 `{g}` 沒有任何箱")
                edges, counts = [bins[0][0]], []
                for k, (s0, e0, c0, i) in enumerate(bins):
                    if k > 0:
                        prev_e = bins[k - 1][1]
                        if s0 < prev_e - 1e-9:
                            raise DeclError(ln, f"{src} 第 {i} 列的箱 [{s0:g}, {e0:g}) 與上一箱 [{bins[k-1][0]:g}, {prev_e:g}) 重疊", "箱不能重疊；每個區間一列")
                        if s0 > prev_e + 1e-9:                     # 有空隙：補一個 0 人的箱
                            edges.append(s0)
                            counts.append(0.0)
                    edges.append(e0)
                    counts.append(c0)
                if edges_ref is None:
                    edges_ref = edges
                elif len(edges) != len(edges_ref) or any(abs(a - b) > 1e-9 for a, b in zip(edges, edges_ref)):
                    raise DeclError(ln, f"兩組的箱界不一致（`{g}` 與 `{gnames[0]}`）", "疊圖的兩組要用同一套箱界（bin_start／bin_end 逐列相同）")
                total = sum(counts)
                if total <= 0:
                    raise DeclError(ln, f"組 `{g or '（全部）'}` 的 count 加總是 0，畫不出分布")
                qv = {q: _quantile_binned(edges, counts, q) for q in quants}
                mean = sum((edges[k] + edges[k + 1]) / 2 * c for k, c in enumerate(counts)) / total if want_mean else None
                groups.append(dict(name=g, counts=counts, n=total, q=qv, mean=mean))
            edges = edges_ref
            exact = False
        else:
            vcol = sp.opt("value", None, "str")
            if vcol is None:
                cands = [h for h in hdr if h != gcol]
                vcol = "value" if "value" in cands else (cands[0] if cands else None)
                if vcol is None:
                    raise DeclError(sp.ln("data"), "資料至少要一欄數值", f"{src} 的欄位：{'、'.join(hdr)}")
            if vcol not in hdr:
                raise DeclError(sp.ln("value"), f"資料裡沒有 `{vcol}` 這一欄", f"{src} 的欄位：{'、'.join(hdr)}")
            vals = numcol(rows, vcol, hdr, sp.ln("value") if sp.has("value") else sp.ln("data"), src)
            edges = Hist._edges_from(sp)
            if edges is None:
                nb = sp.opt("bins", 20, "int")
                if not 2 <= nb <= 200:
                    raise DeclError(sp.ln("bins"), f"bins 要在 2～200 之間（現在 {nb}）")
                lo, hi = min(vals), max(vals)
                if hi <= lo:
                    hi = lo + 1.0
                step = (hi - lo) / nb
                edges = [round(lo + k * step, 10) for k in range(nb)] + [hi]
            clip = sp.opt("clip", False, "bool")
            K = len(edges) - 1
            per = {g: [] for g in gnames}
            for i, (r, v) in enumerate(zip(rows, vals), 2):
                g = r[gcol].strip() if gcol else ""
                per[g].append((v, i))
            out_lo = sum(1 for g in gnames for v, i in per[g] if v < edges[0])
            out_hi = sum(1 for g in gnames for v, i in per[g] if v > edges[-1])
            if (out_lo or out_hi) and not clip:
                raise DeclError(sp.ln("edges"), f"有 {out_lo + out_hi} 筆值超出 edges 範圍 [{edges[0]:g}, {edges[-1]:g}]（小於下界 {out_lo} 筆、大於上界 {out_hi} 筆）",
                                "把 edges 兩端拉開，或寫 clip: true 把超出的值併入兩端的箱（圖上會註明）")
            for g in gnames:
                counts = [0.0] * K
                svals = sorted(v for v, i in per[g])
                if not svals:
                    raise DeclError(sp.ln("data"), f"組 `{g}` 沒有任何值")
                for v in svals:
                    vv = min(max(v, edges[0]), edges[-1])
                    k = bisect.bisect_right(edges, vv) - 1
                    k = min(max(k, 0), K - 1)
                    counts[k] += 1
                qv = {q: _quantile_sorted(svals, q) for q in quants}
                mean = sum(svals) / len(svals) if want_mean else None
                groups.append(dict(name=g, counts=counts, n=float(len(svals)), q=qv, mean=mean))
            exact = True
        nd = sp.opt("nd", 1, "int")
        labels = [f"{S.fmt(edges[k], nd)}～{S.fmt(edges[k+1], nd)}" for k in range(len(edges) - 1)]
        cols = {}
        for g in groups:
            suf = ("_" + g["name"]) if len(groups) > 1 else ""
            cols["count" + suf] = list(g["counts"])
            cols["share" + suf] = [c / g["n"] * 100.0 for c in g["counts"]]
        return {"x": labels, "labels": labels, "cols": cols, "bk": None, "edges": edges, "groups": groups,
                "exact": exact, "clipped": (not exact) and False or (bool(sp.opt("clip", False, "bool")) and (out_lo + out_hi > 0) if exact else False),
                "n_clipped": (out_lo + out_hi) if exact else 0}

    @staticmethod
    def render(sp, store, ctx):
        groups, edges = store["groups"], store["edges"]
        ng = len(groups)
        yscale = sp.opt("yscale", "count", "str")
        if yscale not in ("count", "share"):
            raise DeclError(sp.ln("yscale"), "yscale 只能是 count（人數）或 share（各組佔比 %）")
        unit, nd = sp.opt("unit", "", "str"), sp.opt("nd", 1, "int")
        colors = sp.opt("colors", None, "list")
        if colors is not None and len(colors) != ng:
            raise DeclError(sp.ln("colors"), f"colors 有 {len(colors)} 個，但組有 {ng} 個")
        defaults = ["s2"] if ng == 1 else ["s1", "s3"]
        fos = [None] if ng == 1 else [0.45, 0.75]
        gs, qlines = [], []
        for i, g in enumerate(groups):
            cls = color_cls(colors[i] if colors else defaults[i], sp.ln("colors"), "c-s2")
            key = f"g{i + 1}"
            name = sp.expand(g["name"], sp.ln("group")) if g["name"] else "全部"
            gs.append(dict(key=key, name=name, cls=cls, fo=fos[i], counts=g["counts"], n=g["n"]))
            pre = (name + " ") if ng > 1 else ""
            for q, x in g["q"].items():
                qlines.append((x, f"{pre}p{q:g} {S.fmt(x, nd)}", cls if ng > 1 else None, key if ng > 1 else None, True))
            if g["mean"] is not None:
                qlines.append((g["mean"], f"{pre}mean {S.fmt(g['mean'], nd)}", cls if ng > 1 else "c-ink", key if ng > 1 else None, False))
        notes = []
        if not store["exact"] and (qlines):
            notes.append("分位線／mean 由已分箱資料以箱內線性插補估算")
        if store.get("n_clipped"):
            notes.append(f"{store['n_clipped']} 筆超出範圍的值併入兩端的箱")
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.histogram(edges, gs, aria, sp.opt("desc", aria, "str"), h=sp.opt("height", 340.0, "num"),
                           unit=unit, nd=nd, ylab=sp.opt("ylab", "人數" if yscale == "count" else "佔比（%）", "str"),
                           yscale=yscale, qlines=qlines, xlab=sp.opt("xlab", "", "str"),
                           hint=sp.opt("hint", None, "str"), notes=notes)


@figtype("dumbbell", "pre/post 分群啞鈴圖：每群一條水平線，空心點＝a（前）、實心點＝b（後），右側 ▲▼ 變化（pct／diff） — svgchart.dumbbell",
         ["data", "group", "a", "b", "mode", "sort", "unit", "nd", "delta_nd", "xmin", "xmax", "xlab", "value_label", "color"],
         {"a": ["col", "name"], "b": ["col", "name"]})
class Dumbbell:
    AB = ["col", "name"]
    MAX = 20

    @staticmethod
    def _ab(sp, k, hdr, src):
        v = sp.req(k, None, f"{k} 是{'前測' if k == 'a' else '後測'}欄：寫欄名，或 {{col: 欄名, name: 顯示名}}")
        if isinstance(v, dict):
            s = Spec(v, sp.lnmap, sp.ln(k), Dumbbell.AB, sp.path + (k,), sp.expand, f"{k} ")
            col = s.req("col", "str", f"{k} 要有 col（資料欄名）")
            name = s.opt("name", col, "str")
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            col, name = str(v), str(v)
        else:
            raise DeclError(sp.ln(k), f"`{k}` 要是欄名或 {{col: 欄名, name: 顯示名}}")
        if col not in hdr:
            raise DeclError(sp.ln(k), f"資料裡沒有 {k} 欄 `{col}`", f"{src} 的欄位：{'、'.join(hdr)}")
        return col, name

    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        gcol = sp.opt("group", hdr[0], "str")
        if gcol not in hdr:
            raise DeclError(sp.ln("group"), f"資料裡沒有群組欄 `{gcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        acol, _ = Dumbbell._ab(sp, "a", hdr, src)
        bcol, _ = Dumbbell._ab(sp, "b", hdr, src)
        if acol == bcol:
            raise DeclError(sp.ln("b"), f"a 與 b 是同一欄 `{acol}`")
        labels = [r[gcol].strip() for r in rows]
        for i, c in enumerate(labels, 2):
            if not c:
                raise DeclError(sp.ln("data"), f"{src} 第 {i} 列的 `{gcol}`（群組）是空的")
        dup = sorted({c for c in labels if labels.count(c) > 1})
        if dup:
            raise DeclError(sp.ln("data"), f"{src} 的群組 `{gcol}` 有重複：{'、'.join(dup)}", "每群一列")
        if len(labels) > Dumbbell.MAX:
            raise DeclError(sp.ln("data"), f"啞鈴圖最多 {Dumbbell.MAX} 組（現在 {len(labels)} 組）",
                            "列太多讀不出來：拆成兩張圖（例如依族群／依底台），或只留變化最大的 20 組、其餘改表格")
        av = numcol(rows, acol, hdr, sp.ln("a"), src)
        bv = numcol(rows, bcol, hdr, sp.ln("b"), src)
        mode = sp.opt("mode", "pct", "str")
        if mode not in ("pct", "diff"):
            raise DeclError(sp.ln("mode"), "mode 只能是 pct（變化率 %，(b/a−1)×100）或 diff（差值 b−a）")
        deltas = []
        for a, b in zip(av, bv):
            if mode == "pct":
                deltas.append(None if a == 0 else (b / a - 1) * 100)
            else:
                deltas.append(b - a)
        for k in ("xmin", "xmax"):
            v = sp.opt(k, None, "num")
            if v is None:
                continue
            bad = [(labels[i], x) for i in range(len(labels)) for x in (av[i], bv[i]) if (x < v if k == "xmin" else x > v)]
            if bad:
                raise DeclError(sp.ln(k), f"{k}={v:g} 會把「{bad[0][0]}」的值 {bad[0][1]:g} 切在圖外（共 {len(bad)} 個值）", "把範圍放寬，或拿掉這個欄位讓程式自動決定")
        order = list(range(len(labels)))
        srt = sp.opt("sort", "delta", "str")
        if srt == "delta":
            order.sort(key=lambda i: (deltas[i] is None, -(deltas[i] or 0.0)))
        elif srt == "abs":
            order.sort(key=lambda i: (deltas[i] is None, -abs(deltas[i] or 0.0)))
        elif srt != "none":
            raise DeclError(sp.ln("sort"), "sort 只能是 delta（變化由大到小）、abs（變化絕對值由大到小）或 none（照資料順序）")
        labels = [labels[i] for i in order]
        av, bv, deltas = [av[i] for i in order], [bv[i] for i in order], [deltas[i] for i in order]
        cols = {acol: av, bcol: bv}
        if all(d is not None for d in deltas) and "delta" not in cols:
            cols["delta"] = list(deltas)
        return {"x": labels, "labels": labels, "cols": cols, "bk": None, "a": av, "b": bv, "delta": deltas,
                "acol": acol, "bcol": bcol, "mode": mode}

    @staticmethod
    def render(sp, store, ctx):
        hdr = [store["acol"], store["bcol"]]
        _, aname = Dumbbell._ab(sp, "a", hdr, "")
        _, bname = Dumbbell._ab(sp, "b", hdr, "")
        unit, nd = sp.opt("unit", "", "str"), sp.opt("nd", 1, "int")
        mode = store["mode"]
        dnd = sp.opt("delta_nd", 1, "int")
        dunit = "%" if mode == "pct" else ((" " + unit) if unit else "")
        rows = []
        for lab, a, b, d in zip(store["x"], store["a"], store["b"], store["delta"]):
            if d is None:
                text, tone = "N/A", "ink"
            elif d == 0:
                text, tone = f"– {0:.{dnd}f}{dunit}", "ink"
            else:
                text = f"{'▲' if d > 0 else '▼'} {d:+,.{dnd}f}{dunit}"
                tone = "up" if d > 0 else "dn"
            rows.append((sp.expand(lab, sp.ln("data")), a, b, text, tone))
        vl = sp.opt("value_label", "auto")
        if vl not in (True, False, "auto"):
            raise DeclError(sp.ln("value_label"), "value_label 只能是 true／false／auto（≤ 12 組才標）")
        show_vals = (vl is True) or (vl == "auto" and len(rows) <= 12)
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.dumbbell(rows, aria, sp.opt("desc", aria, "str"), h=sp.opt("height", None, "num"), unit=unit, nd=nd,
                          a_name=aname, b_name=bname, xmin=sp.opt("xmin", None, "num"), xmax=sp.opt("xmax", None, "num"),
                          xlab=sp.opt("xlab", "", "str"), hint=sp.opt("hint", None, "str"), value_labels=show_vals,
                          delta_head=("變化率" if mode == "pct" else "變化") + (f"（{unit}）" if (mode == "diff" and unit) else ""),
                          cls=color_cls(sp.opt("color"), sp.ln("color"), "c-s1"))


DOW_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
DOW_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DOW_MAP = {}
for _i, _names in enumerate(zip(DOW_EN, ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                                 "一二三四五六日")):
    for _nm in _names:
        _DOW_MAP[str(_nm).lower()] = _i + 1
    for _pre in ("週", "周", "星期", "禮拜"):
        _DOW_MAP[_pre + _names[2]] = _i + 1
for _alias in ("天", "週天", "周天", "星期天", "禮拜天"):
    _DOW_MAP[_alias] = 7
_HOUR_RE = re.compile(r"^(?:h|H|hour\s*|Hour\s*)?(\d{1,2})(?:\s*(?:時|h|H|點)|:00)?$")


def _dow_of(txt):
    s = str(txt).strip()
    if re.match(r"^\d+$", s):
        d = int(s)
        return d if 1 <= d <= 7 else None
    return _DOW_MAP.get(s.lower()) or _DOW_MAP.get(s)


def _hour_of(txt):
    m = _HOUR_RE.match(str(txt).strip())
    return int(m.group(1)) if m else None


@figtype("dow_hour", "星期×小時熱圖：列＝週一～週日、欄＝0～23 時；long（dow,hour,value）或 wide（dow ＋ 24 欄）；單色亮度階、最大格粗框、缺格留白 — svgchart.heatmap",
         ["data", "dow", "hour", "value", "week_start", "dow_labels", "emph", "unit", "nd", "scale", "value_label", "legend"])
class DowHour:
    @staticmethod
    def load(sp, ctx):
        hdr, rows, src = load_csv(sp, ctx)
        lower = {h: h.strip().lower() for h in hdr}
        dcol = sp.opt("dow", None, "str")
        if dcol is None:
            dcol = next((h for h in hdr if lower[h] in ("dow", "weekday", "week_day", "day_of_week", "星期", "週", "周")), hdr[0])
        if dcol not in hdr:
            raise DeclError(sp.ln("dow"), f"資料裡沒有星期欄 `{dcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
        hcol = sp.opt("hour", None, "str")
        if hcol is None:
            hcol = next((h for h in hdr if lower[h] in ("hour", "hr", "hh", "時", "小時", "時段")), None)
        vcol = sp.opt("value", None, "str")
        hour_cols = [h for h in hdr if h != dcol and _hour_of(h) is not None]
        long_mode = hcol is not None or (vcol is not None and len(hour_cols) < 2)
        ln = sp.ln("data")
        grid = [[None] * 24 for _ in range(7)]
        seen = {}
        if long_mode:
            if hcol is None or hcol not in hdr:
                raise DeclError(sp.ln("hour") if sp.has("hour") else ln, f"資料裡沒有小時欄 `{hcol}`",
                                f"long 格式要有 dow,hour,value 三欄（或用 hour:／value: 指名）；{src} 的欄位：{'、'.join(hdr)}")
            if vcol is None:
                rest = [h for h in hdr if h not in (dcol, hcol)]
                vcol = "value" if "value" in rest else (rest[0] if rest else None)
            if vcol is None or vcol not in hdr:
                raise DeclError(sp.ln("value") if sp.has("value") else ln, f"資料裡沒有數值欄 `{vcol}`", f"{src} 的欄位：{'、'.join(hdr)}")
            for i, r in enumerate(rows, 2):
                d = _dow_of(r[dcol])
                if d is None:
                    raise DeclError(ln, f"{src} 第 {i} 列的 `{dcol}` 是 {r[dcol]!r}，不是合法的星期",
                                    "接受 1～7（1＝週一…7＝週日）、Mon～Sun／Monday～Sunday、週一～週日／周一～周日／星期一～星期日")
                hh = _hour_of(r[hcol])
                if hh is None or not 0 <= hh <= 23:
                    raise DeclError(ln, f"{src} 第 {i} 列的 `{hcol}` 是 {r[hcol]!r}，小時要是 0～23 的整數" +
                                    (f"（{hh} 超出 0～23）" if hh is not None else ""), "0～23 或 h0～h23、0時～23時；24 要寫成 0")
                if (d, hh) in seen:
                    raise DeclError(ln, f"{src} 第 {i} 列的（{r[dcol]}, {r[hcol]}）與第 {seen[(d, hh)]} 列重複", "同一個星期×小時只能有一列；要合併先在 SQL 加總")
                seen[(d, hh)] = i
                grid[d - 1][hh] = _num_or_none(r[vcol], ln, src, i, vcol)
        else:
            others = [h for h in hdr if h != dcol and _hour_of(h) is None]
            if others:
                raise DeclError(ln, f"欄 `{others[0]}` 不是小時欄（欄名要像 0～23、h0～h23 或 0時～23時）",
                                "wide 格式：第一欄星期 ＋ 每小時一欄；long 格式（dow,hour,value）請用 hour:／value: 指名欄位")
            if len(hour_cols) < 2:
                raise DeclError(ln, f"小時欄只有 {len(hour_cols)} 個，至少要 2 個（通常 24 個）")
            hs = [_hour_of(h) for h in hour_cols]
            for h, hh in zip(hour_cols, hs):
                if not 0 <= hh <= 23:
                    raise DeclError(ln, f"欄 `{h}` 的小時 {hh} 超出 0～23", "24 要寫成 0")
            dups = sorted({hh for hh in hs if hs.count(hh) > 1})
            if dups:
                raise DeclError(ln, f"{src} 的小時欄重複：{dups[0]} 時出現在多欄", "每小時一欄；欄名 `21` 與 `h21` 是同一小時")
            for i, r in enumerate(rows, 2):
                d = _dow_of(r[dcol])
                if d is None:
                    raise DeclError(ln, f"{src} 第 {i} 列的 `{dcol}` 是 {r[dcol]!r}，不是合法的星期",
                                    "接受 1～7（1＝週一…7＝週日）、Mon～Sun／Monday～Sunday、週一～週日／周一～周日／星期一～星期日")
                if d in seen:
                    raise DeclError(ln, f"{src} 第 {i} 列的星期 `{r[dcol]}` 與第 {seen[d]} 列重複", "每個星期一列")
                seen[d] = i
                for h, hh in zip(hour_cols, hs):
                    grid[d - 1][hh] = _num_or_none(r[h], ln, src, i, h)
        allv = [v for row in grid for v in row if v is not None]
        if not allv:
            raise DeclError(ln, f"{src} 沒有任何數值（全部是空白）")
        scale = sp.opt("scale", "raw", "str")
        if scale not in ("raw", "ratio", "pct"):
            raise DeclError(sp.ln("scale"), "scale 只能是 raw（數值照用，預設）／ratio（0～1 比例，圖上換成 %）／pct（已是百分比）")
        if scale == "ratio":
            grid = [[None if v is None else v * 100.0 for v in row] for row in grid]
        ws = sp.opt("week_start", "mon", "str")
        if ws not in ("mon", "sun"):
            raise DeclError(sp.ln("week_start"), "week_start 只能是 mon（週一在最上，預設）或 sun（週日在最上）")
        order = [0, 1, 2, 3, 4, 5, 6] if ws == "mon" else [6, 0, 1, 2, 3, 4, 5]
        dl = sp.opt("dow_labels", "zh")
        if isinstance(dl, list):
            if len(dl) != 7:
                raise DeclError(sp.ln("dow_labels"), f"dow_labels 要剛好 7 個（週一～週日的順序），現在 {len(dl)} 個")
            names = [str(x) for x in dl]
        elif dl in ("zh", "en"):
            names = DOW_ZH if dl == "zh" else DOW_EN
        else:
            raise DeclError(sp.ln("dow_labels"), "dow_labels 只能是 zh（週一～週日）、en（Mon～Sun）或 7 個標籤的清單")
        labels = [names[i] for i in order]
        grid = [grid[i] for i in order]
        emph = sp.opt("emph", "max", "str")
        if emph not in ("max", "none"):
            raise DeclError(sp.ln("emph"), "emph 只能是 max（把最大格加粗框，預設）或 none")
        best = None
        if emph == "max":
            for ri, row in enumerate(grid):
                for ci, v in enumerate(row):
                    if v is not None and (best is None or v > best[0]):
                        best = (v, ri, ci)
        cols = {f"h{hh}": [grid[ri][hh] for ri in range(7)] for hh in range(24)}
        cols["total"] = [sum(v for v in row if v is not None) for row in grid]
        return {"x": labels, "labels": labels, "cols": cols, "bk": None, "grid": grid, "hours": list(range(24)),
                "emph": (best[1], best[2]) if best else None, "mode": scale}

    @staticmethod
    def render(sp, store, ctx):
        mode = store["mode"]
        unit = sp.opt("unit", "%" if mode in ("ratio", "pct") else "", "str")
        if unit in ("pct", "percent", "百分比"):
            unit = "%"
        allv = [v for row in store["grid"] for v in row if v is not None]
        nd = sp.opt("nd", 0 if all(float(v).is_integer() for v in allv) else 1, "int")
        vl = sp.opt("value_label", "auto")
        if vl not in (True, False, "auto"):
            raise DeclError(sp.ln("value_label"), "value_label 只能是 true／false／auto（放得下才印）")
        legend = sp.opt("legend", "數值", "str")
        labels = [sp.expand(c, sp.ln("dow_labels")) for c in store["x"]]
        emph = store["emph"]
        note = None
        if emph is not None:
            ri, ci = emph
            v = store["grid"][ri][ci]
            note = f"粗框＝最大格：{labels[ri]} {ci} 時 {S.fmt(v, nd)}{unit}"
        title = sp.req("title", "str")
        aria = sp.opt("aria", title, "str")
        return S.heatmap(labels, store["hours"], store["grid"], aria, sp.opt("desc", aria, "str"),
                         h=sp.opt("height", None, "num"), sizes=None, unit=unit, nd=nd, value_labels=vl, highlight=None,
                         hint=sp.opt("hint", "滑過任一格看星期、小時與數值", "str"), legend_title=legend,
                         col_labels=[str(h) for h in store["hours"]], col_key="時", col_tips=[f"{h} 時" for h in store["hours"]],
                         missing_note="空白＝無資料（不是 0）", emph=emph, emph_note=note, fit_labels=True, col_suffix="時")


# ---------------------------------------------------------------- 掃描與組裝
class Ctx:
    def __init__(self, md_dir, fm):
        self.md_dir, self.fm = md_dir, fm
        self.problems = []            # (行號, 訊息, 提示)
        self.blocks = {}              # 開頭行號 → (kind, key|None, 收尾行號)
        self.decls = {}               # key → dict(kind, sp, open_ln)
        self.store = {}               # 圖 key → 資料（給 {{v:}} 函數與 reflines 用）
        self.figs, self.tbls = {}, {}
        self.broken = set()           # 解析失敗的 key（放置時不再重複報錯）
        self.broken_values = set()    # 依賴壞掉的圖而算不出來的數字 key（{{v:}} 不再重複報錯）
        self.values = {}

    def bad(self, ln, msg, hint=""):
        # 第 4 欄 True ＝ 宣告層的根因（先修這些，正文層的連鎖錯誤通常會一起消失）
        self.problems.append((ln, msg, hint, True))

    def guess_broken(self, body):
        """區塊解析不下去時，先從內文撈出 key 登錄成 broken，避免 {{v:}}／[[key]] 連鎖報錯。"""
        for line in body:
            m = re.match(r"^\s*key\s*:\s*(\S+)", line)
            if m:
                self.broken.add(m.group(1).strip("\"'"))
                return

    def expand(self, s, ln):
        """把 SVG 內文字（aria／desc／標籤／tooltip）裡的 {{v:key}} 換成值。"""
        def sub(m):
            k = m.group(1).strip()
            if k in self.values:
                return self.values[k]
            if k in self.broken_values:
                return m.group(0)
            self.bad(ln, f"{{{{v:{k}}}}} 找不到這個數字 key",
                     f"可用的 key：{'、'.join(list(self.values)[:12])}{'…' if len(self.values) > 12 else ''}")
            return m.group(0)
        return RE_V.sub(sub, s)


def collect(lines, start, md_dir, fm):
    """掃 md 的 ``` 區塊：解析宣告、讀資料。回傳 Ctx（figs／tbls 要等 render_all）。"""
    ctx = Ctx(md_dir, fm)
    i = start
    while i < len(lines):
        t = lines[i].strip()
        if not t.startswith("```"):
            i += 1
            continue
        info = t[3:].strip().lower()
        open_ln = i + 1
        j = i + 1
        while j < len(lines) and lines[j].strip() != "```":
            j += 1
        if j >= len(lines):
            ctx.bad(open_ln, f"```{info} 區塊沒有收尾（後面的內容全被吃進區塊裡了）",
                    "在區塊最後一行加一行只有 ``` 的收尾；下面的其他錯誤多半是這個造成的")
            ctx.guess_broken(lines[i + 1:])
            ctx.blocks[open_ln] = (None, None, len(lines))
            break
        close_ln = j + 1
        kind = {"figure": "fig", "fig": "fig", "table": "tbl", "tbl": "tbl"}.get(info)
        if kind is None:
            ctx.bad(open_ln, f"不認得的區塊 ```{info}", "只認得 ```figure（圖）與 ```table（表）")
            ctx.blocks[open_ln] = (None, None, close_ln)
        else:
            key = _declare(ctx, kind, lines[i + 1:j], open_ln)
            ctx.blocks[open_ln] = (kind, key, close_ln)
        i = j + 1
    return ctx


def _declare(ctx, kind, body, open_ln):
    try:
        obj, lnmap = Y.parse("\n".join(body), open_ln + 1)
    except Y.YamlError as e:
        ctx.bad(e.ln, e.msg, "區塊裡是 `欄位: 值`；清單用 [a, b] 或 `- ` 項目；CSV 用 data: | 換行貼")
        ctx.guess_broken(body)
        return None
    if not isinstance(obj, dict) or not obj:
        ctx.bad(open_ln, "區塊裡要是 `欄位: 值`（key／type／title…）")
        ctx.guess_broken(body)
        return None
    key = str(obj.get("key", "")).strip()
    if not key:
        ctx.bad(open_ln, f"```{'figure' if kind == 'fig' else 'table'} 區塊缺 key", "key 是英數／底線，正文用 [[key]] 引用它")
        return None
    if not RE_KEY.match(key):
        ctx.bad(Y.get_ln(lnmap, ("key",), open_ln), f"key `{key}` 只能用英數、底線、連字號")
        return None
    if key in ctx.decls:
        ctx.bad(Y.get_ln(lnmap, ("key",), open_ln), f"key `{key}` 已在第 {ctx.decls[key]['open_ln']} 行宣告過",
                "每個圖表一個 key；要在別處提到它用 [[key]]")
        return None
    ctx.decls[key] = dict(kind=kind, obj=obj, lnmap=lnmap, open_ln=open_ln, ok=False)
    try:
        if kind == "tbl":
            sp = Spec(obj, lnmap, open_ln, TABLE_FIELDS, what="```table ")
            _check_common(sp, ctx)
            sp.req("columns", "list", "表頭：columns: [變數名稱, 上線前, 上線後, ...]")
            load_csv(sp, ctx)
        else:
            typ = str(obj.get("type", "")).strip()
            if typ not in TYPES:
                raise DeclError(Y.get_ln(lnmap, ("type",), open_ln),
                                f"不認得的圖表類型 `{typ}`" if typ else "缺 type",
                                "目前支援：" + "、".join(f"{k}（{v['doc'].split('—')[0].strip()}）" for k, v in TYPES.items()))
            sp = Spec(obj, lnmap, open_ln, TYPES[typ]["fields"], what=f"```figure {typ} ")
            _check_common(sp, ctx)
            ctx.store[key] = TYPES[typ]["load"](sp, ctx)
        ctx.decls[key]["ok"] = True
    except DeclError as e:
        ctx.bad(e.ln, e.msg, e.hint)
        ctx.broken.add(key)
    except Exception as e:                       # 資料怪到程式沒接住：也要報行號、不炸掉
        ctx.bad(open_ln, f"讀這個區塊時出錯：{type(e).__name__}: {e}", "先檢查 data 的欄位與數字格式")
        ctx.broken.add(key)
    return key


def _check_common(sp, ctx):
    sp.req("title", "str", "圖表標題（會顯示在編號後面）")
    defs = sp.req("defs", "dict", "備註：defs: 底下從 維度／指標／著色 這三列裡挑要寫的（至少一列）")
    # v1.6：備註只有四列（維度／指標／著色 ＋ 母體）。母體那一列＝note_base／note_extra 那一行，
    # 不是 defs 的第四個 key——多寫一個 key 就變五列，Lena 2026-09-16 15:12 定的規範。
    extra = [k for k in defs if k not in DEF_KEYS]
    if extra:
        k = extra[0]
        hint = ("母體那一列寫在檔頭 note_base:（母體｜口徑｜n）與這個區塊的 note_extra:，不要放進 defs"
                if str(k).strip() in ("母體", "口徑", "n", "樣本", "母體與口徑")
                else "要補的口徑寫進 note_extra:，要補的定義併進 維度／指標／著色 這三列裡")
        raise DeclError(sp.ln("defs", k), f"defs 多了 `{k}`——備註只能四列：維度／指標／著色 ＋ 母體", hint)
    # v1.8（Lena 2026-09-16 17:38 第 e 點「非必要不需要 notes_extra、維度」）：
    # 三列不再強制全寫，改成「三列裡挑，最多三列、缺的不報錯」。守門剩三條：
    #   ① 至少要有一列（整個 defs 空的＝備註只剩母體那一行，那是漏寫不是精簡）
    #   ② 寫了 key 就不能留空（空值會排出一列空白的定義）
    #   ③ 順序必須是 維度 → 指標 → 著色（同一份報告的備註排列要一致）
    if not defs:
        raise DeclError(sp.ln("defs"), "defs 是空的——備註至少要留一列",
                        "從 維度（軸是什麼）／指標（怎麼算）／著色（顏色代表什麼）挑要寫的；"
                        "整張表都不需要定義時，至少留 指標")
    blank = [k for k in defs if not str(defs[k]).strip()]
    if blank:
        k = blank[0]
        raise DeclError(sp.ln("defs", k), f"defs 的 `{k}` 是空的",
                        "要嘛寫內容，要嘛整列拿掉（v1.8 起缺的列不報錯）")
    got = [k for k in defs]
    if got != [k for k in DEF_KEYS if k in defs]:
        raise DeclError(sp.ln("defs", got[0]),
                        f"defs 的順序要照 維度 → 指標 → 著色（現在是 {'／'.join(got)}）",
                        "可以只寫其中一兩列，但寫到的那幾列要照這個先後")
    # v1.9（Lena 2026-09-17 10:18 第 1 點「不需要 note_base」）：母體註腳從「每個區塊都一定要有」
    # 放寬成「不寫就整塊不渲染」——同一句母體印在 25 個區塊底下本來就是雜訊，母體已經在
    # 標題區的資料說明列講過一次。守門改成下面這條**更嚴**的：寫了 note／note_extra 就不准留空，
    # 免得產出一個空的 <p class="blk-note">（qa 第 17 項有第二道守門）。
    for k in ("note", "note_extra"):
        if k in sp.obj and not str(sp.obj[k] if sp.obj[k] is not None else "").strip():
            raise DeclError(sp.ln(k), f"`{k}` 寫了卻是空的",
                            "要嘛寫內容（母體｜口徑｜n），要嘛整行拿掉"
                            "（v1.9 起不寫就不會印那一行）")


def resolve_values(fm, fm_lnmap, md_dir, ctx):
    """{{v:key}} 的來源：values_file（json）＋ 檔頭 values:。值可以是文字，或 {fn: …} 計算式。"""
    values, doc = {}, []
    src = []
    vf = fm.get("values_file")
    if vf:
        path = vf if os.path.isabs(str(vf)) else os.path.join(md_dir, str(vf))
        ln = Y.get_ln(fm_lnmap, ("values_file",), 0)
        if not os.path.isfile(path):
            ctx.bad(ln, f"values_file 找不到：{vf}", f"路徑相對於內容檔所在資料夾（{md_dir}）")
        else:
            try:
                data = json.load(io.open(path, encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("最外層要是物件 {key: 值}")
                src += [(k, v, ln, f"values_file {vf}") for k, v in data.items()]
            except (ValueError, json.JSONDecodeError) as e:
                ctx.bad(ln, f"values_file {vf} 讀不起來：{e}", "要是合法 JSON，最外層是物件")
    vm = fm.get("values")
    if vm not in (None, ""):
        if not isinstance(vm, dict):
            ctx.bad(Y.get_ln(fm_lnmap, ("values",), 0), "檔頭 values 要是對應（底下縮排寫 key: 值）")
        else:
            src += [(k, v, Y.get_ln(fm_lnmap, ("values", k), 0), "檔頭 values") for k, v in vm.items()]
    seen = {}
    for k, v, ln, where in src:
        k = str(k).strip()
        if k in seen:
            ctx.bad(ln, f"數字 key `{k}` 重複（{seen[k]} 與 {where} 都有）")
            continue
        seen[k] = where
        if isinstance(v, dict):
            try:
                num = compute(v, ctx, ln)
                values[k] = format_value(num, v, ln)
                doc.append((k, values[k], fn_doc(v)))
            except DeclError as e:
                if str(v.get("fig")) in ctx.broken:      # 根因是那張圖，已報過；這裡不再連鎖
                    ctx.broken_values.add(k)
                else:
                    ctx.bad(e.ln or ln, f"{{{{v:{k}}}}} 算不出來：{e.msg}", e.hint)
        elif v is None or isinstance(v, (list,)):
            ctx.bad(ln, f"{{{{v:{k}}}}} 的值要是文字／數字或 {{fn: …}} 計算式")
        else:
            values[k] = str(v)
            doc.append((k, values[k], where))
    ctx.values = values
    return values, doc


def render_all(ctx, values):
    """資料與數值都齊了 → 產每張圖的 SVG、每張表的材料（{{v:}} 在 SVG 文字裡也會展開）。"""
    ctx.values = values
    for key, d in ctx.decls.items():
        if not d["ok"]:
            continue
        obj, lnmap, open_ln = d["obj"], d["lnmap"], d["open_ln"]
        try:
            if d["kind"] == "tbl":
                sp = Spec(obj, lnmap, open_ln, TABLE_FIELDS, expand=ctx.expand, what="```table ")
                ctx.tbls[key] = _table(sp, ctx)
            else:
                typ = str(obj["type"]).strip()
                sp = Spec(obj, lnmap, open_ln, TYPES[typ]["fields"], expand=ctx.expand, what=f"```figure {typ} ")
                svg = TYPES[typ]["render"](sp, ctx.store[key], ctx)
                ctx.figs[key] = dict(title=sp.req("title", "str"), svg=svg, note=_note(sp, ctx),
                                     defs=_defs(sp), ln=open_ln)
        except DeclError as e:
            ctx.bad(e.ln, e.msg, e.hint)
            ctx.broken.add(key)
        except Exception as e:
            ctx.bad(open_ln, f"畫這張圖時出錯：{type(e).__name__}: {e}", "先檢查 series／items 的數值與欄名")
            ctx.broken.add(key)


def _note(sp, ctx):
    base = str(ctx.fm.get("note_base", "")).strip()
    if sp.has("note"):
        return sp.req("note", "str")
    extra = sp.opt("note_extra", "", "str")
    if not base:          # v1.9：檔頭沒寫 note_base 時，note_extra 前面不該掛一根孤兒 ｜
        return extra
    return base + ("｜" + extra if extra else "")


def _defs(sp):
    defs = sp.req("defs", "dict")
    return [(str(k), sp.expand(str(v), sp.ln("defs", k))) for k, v in defs.items()]


def _table(sp, ctx):
    cols = [str(c) for c in sp.req("columns", "list")]
    hdr, rows, src = load_csv(sp, ctx)
    if len(hdr) != len(cols):
        raise DeclError(sp.ln("columns"), f"columns 有 {len(cols)} 欄，但 {src} 的表頭有 {len(hdr)} 欄",
                        "資料第一列是欄位名（跟 columns 對齊，可以用英文短名）")
    aligns = sp.opt("align", ["left"] + ["right"] * (len(cols) - 1), "list")
    types = sp.opt("types", ["text"] + ["num"] * (len(cols) - 1), "list")
    for name, lst, ok in (("align", aligns, ("left", "right", "center")), ("types", types, ("text", "num"))):
        if len(lst) != len(cols):
            raise DeclError(sp.ln(name), f"{name} 要有 {len(cols)} 個（每欄一個）")
        badv = [x for x in lst if x not in ok]
        if badv:
            raise DeclError(sp.ln(name), f"{name} 只能是 {'／'.join(ok)}（現在有 {badv[0]!r}）")
    emph = []
    for e in sp.opt("emph_rows", [], "list"):
        if isinstance(e, bool) or not isinstance(e, int) or not 1 <= e <= len(rows):
            raise DeclError(sp.ln("emph_rows"), f"emph_rows 的 {e!r} 不是 1~{len(rows)} 的列號（從 1 數）")
        emph.append(e - 1)
    sortable = sp.opt("sortable", True, "bool")
    rowspan, groups, sig, signote, cgroups = _table_v15(sp, cols, rows, hdr)
    # 這三種宣告都綁在「列的位置」上，排序會把它們打散 → 自動固定列序
    fixed = bool(rowspan or groups or (sig and sig["dir"] == "tb"))
    if fixed:
        if sp.has("sortable") and sortable:
            why = "rowspan／row_groups" if (rowspan or groups) else "sig 的上下配對（dir: tb）"
            raise DeclError(sp.ln("sortable"), f"{why} 不能跟 sortable: true 併用",
                            "排序會把合併的格子、列群組與上下配對的相鄰關係打散；"
                            "拿掉 sortable: true（宣告這些就自動固定列序，左右配對 dir: lr 則不受影響）")
        sortable = False
    out_rows = []
    for r in rows:
        cells = []
        for h in hdr:
            c = r[h]
            if "@@" in c:
                disp, _, sv = c.partition("@@")
                cells.append((disp.strip(), sv.strip()))
            else:
                cells.append(c)
        out_rows.append(cells)
    note = _note(sp, ctx)
    if signote:
        note = (note + "｜" + signote) if note else signote
    return dict(title=sp.req("title", "str"), headers=cols, rows=out_rows, note=note,
                aligns=aligns, col_types=types, emph_rows=emph, defs=_defs(sp),
                sortable=sortable, rowspan=rowspan, row_groups=groups, sig=sig,
                col_groups=cgroups, ln=sp.ln0)


def _cellnum(c):
    """把 cell 讀成數字，讀不出來回 None。優先用 `顯示@@排序值` 的排序值；
    沒有排序值就把 {{d:…}}／{{n:…}} 的數值挖出來，再去掉千分位、%、pp 與正負號的全形字。
    只給 v1.6 的 sig `mark: max` 比大小用。"""
    if not isinstance(c, str):
        return None
    s = c.split("@@", 1)[1].strip() if "@@" in c else c.strip()
    m = _CELL_MARK.match(s)
    if m:
        s = m.group(1)
    s = (s.replace(",", "").replace("%", "").replace("pp", "")
          .replace("＋", "+").replace("－", "-").replace("−", "-").replace("–", "-").strip())
    return float(s) if _CELL_NUM.match(s) else None


def _table_v15(sp, cols, rows, hdr):
    """v1.5 表格三件事：rowspan 合併欄、列群組粗框、檢定顯著底色
    （v1.6 的 sig 多兩件正交的事：mark＝標哪一格、scale/levels+v＝那一格多深）。
    全部都是「宣告才生效」，沒宣告時回傳空值、輸出與 v1.4／v1.5 逐 byte 相同。"""
    nc, nr = len(cols), len(rows)
    rowspan = []
    for c in sp.opt("rowspan", [], "list"):
        if isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= nc:
            raise DeclError(sp.ln("rowspan"), f"rowspan 的 {c!r} 不是 1~{nc} 的欄號（從 1 數）",
                            f"欄號對應 columns：{'、'.join(f'{i + 1}={h}' for i, h in enumerate(cols))}")
        if c - 1 in rowspan:
            raise DeclError(sp.ln("rowspan"), f"rowspan 的欄號 {c} 重複了")
        rowspan.append(c - 1)
    groups = []
    for g in sp.opt("row_groups", [], "list"):
        if isinstance(g, bool) or not isinstance(g, int) or g < 1:
            raise DeclError(sp.ln("row_groups"), f"row_groups 的 {g!r} 不是正整數",
                            "row_groups 寫每一群有幾列，例 [3, 3, 2]（加起來要等於資料列數）")
        groups.append(g)
    if groups and sum(groups) != nr:
        raise DeclError(sp.ln("row_groups"),
                        f"row_groups 加起來是 {sum(groups)} 列，但資料有 {nr} 列",
                        "每一群幾列、由上往下寫，加總要剛好等於資料列數")
    # v1.9：欄位群直向粗框。跟 row_groups 同一套寫法（由左往右、每群幾欄、加總＝欄數），
    # 但**綁的是欄不是列**，排序只重排列、不會打散欄群，所以不進底下的「自動固定列序」。
    cgroups = []
    for g in sp.opt("col_groups", [], "list"):
        if isinstance(g, bool) or not isinstance(g, int) or g < 1:
            raise DeclError(sp.ln("col_groups"), f"col_groups 的 {g!r} 不是正整數",
                            "col_groups 寫每一群有幾欄，例 [1, 1, 3, 2, 2, 2]"
                            "（加起來要等於 columns 的欄數）")
        cgroups.append(g)
    if cgroups and sum(cgroups) != nc:
        raise DeclError(sp.ln("col_groups"),
                        f"col_groups 加起來是 {sum(cgroups)} 欄，但 columns 有 {nc} 欄",
                        "每一群幾欄、由左往右寫，加總要剛好等於欄數："
                        + "、".join(f"{i + 1}={h}" for i, h in enumerate(cols)))
    if len(cgroups) == 1:
        raise DeclError(sp.ln("col_groups"),
                        "col_groups 只寫了一群＝一條粗框都畫不出來",
                        "直線只畫在群與群之間（最右邊不收），所以至少要分成兩群；"
                        "不需要分隔就整行拿掉")
    sig, signote = None, ""
    if sp.has("sig"):  # noqa: E501  （回傳值在函式尾端連同 cgroups 一起給出去）
        obj = sp.req("sig", "dict", "sig: 底下寫 dir: lr／tb 與 pairs: 清單")
        ss = Spec(obj, sp.lnmap, sp.ln("sig"), SIG_FIELDS, sp.path + ("sig",), sp.expand,
                  what="```table 的 sig ")
        d = ss.req("dir", "str", "lr＝左右配對（同一列的兩欄）／tb＝上下配對（同一欄的兩列）")
        if d not in ("lr", "tb"):
            raise DeclError(ss.ln("dir"), f"sig 的 dir 只能是 lr（左右配對）或 tb（上下配對）（現在是 {d!r}）")
        pairs = ss.req("pairs", "list", "每一組顯著的配對一項：- {row: 2, a: 2, b: 3}（lr）或 - {col: 2, a: 1, b: 2}（tb）")
        if not pairs:
            raise DeclError(ss.ln("pairs"), "sig 的 pairs 是空的", "沒有顯著的配對就不要宣告 sig")
        # v1.6 兩個正交的選項：
        #   mark（A 線）both＝兩格都上底色（預設，v1.5 行為）／max＝只標數值較大的一格
        #   scale + levels + 每組的 v（B 線）＝底色分三階，越深證據越強
        # 併用時＝只有較大那格上色、深淺依那一組的 v 落在哪一階。
        mark = ss.opt("mark", "both", "str")
        if mark not in ("both", "max"):
            raise DeclError(ss.ln("mark"),
                            f"sig 的 mark 只能是 both（兩格都標，預設）或 max（只標數值較大的一格）"
                            f"（現在是 {mark!r}）",
                            "mark 決定「哪一格」上色；要決定「那一格多深」是另一組宣告："
                            "scale／levels ＋ 每組配對的 v（兩個可以一起用）")
        scale, cuts = _sig_scale(ss, pairs)
        cells = {}
        for i, p in enumerate(pairs):
            ps = ss.sub("pairs", i, p, SIG_PAIR, f"sig.pairs 第 {i + 1} 項")
            if d == "lr":
                fixed = ps.req("row", "int", "lr 要寫 row（第幾列，從 1 數）")
                if not 1 <= fixed <= nr:
                    raise DeclError(ps.ln("row"), f"sig.pairs 第 {i + 1} 項的 row {fixed} 不是 1~{nr} 的列號")
                lo, hi = 1, nc
                what = "欄號"
            else:
                fixed = ps.req("col", "int", "tb 要寫 col（第幾欄，從 1 數）")
                if not 1 <= fixed <= nc:
                    raise DeclError(ps.ln("col"), f"sig.pairs 第 {i + 1} 項的 col {fixed} 不是 1~{nc} 的欄號")
                lo, hi = 1, nr
                what = "列號"
            ab = []
            for k in ("a", "b"):
                v = ps.req(k, "int", f"a／b 是配對的兩個{what}（從 1 數）")
                if not lo <= v <= hi:
                    raise DeclError(ps.ln(k), f"sig.pairs 第 {i + 1} 項的 {k} {v} 不是 {lo}~{hi} 的{what}")
                ab.append(v)
            if ab[0] == ab[1]:
                raise DeclError(ps.ln("b"), f"sig.pairs 第 {i + 1} 項的 a 與 b 是同一格（都是 {ab[0]}）",
                                "配對要指到兩個不同的格子")
            rc = [(fixed - 1, v - 1) if d == "lr" else (v - 1, fixed - 1) for v in ab]
            if mark == "max":
                # v1.6（A 線）：一組配對只標數值較大的那一格（數值相等就兩格都標）
                nums = []
                for r0, c0 in rc:
                    val = _cellnum(rows[r0][hdr[c0]])
                    if val is None:
                        raise DeclError(
                            ps.ln("a" if (r0, c0) == rc[0] else "b"),
                            f"sig 宣告了 mark: max，但第 {r0 + 1} 列第 {c0 + 1} 欄"
                            f"（{cols[c0]}）的 {rows[r0][hdr[c0]]!r} 讀不出數字，沒辦法比大小",
                            "給那一格加排序值（寫成 `顯示@@數值`），或把 mark 改回 both")
                    nums.append(val)
                if nums[0] > nums[1]:
                    take = [rc[0]]
                elif nums[1] > nums[0]:
                    take = [rc[1]]
                else:
                    take = list(rc)
            else:
                take = list(rc)
            # v1.6（B 線）：這一組配對的強度值 → 第幾階；沒分階時是 None
            lv = _sig_level(ps, i, cuts)
            for rc1 in take:
                # 同一格被兩組配對指到（A vs B、A vs C）：取最深的那一階，不報錯
                if rc1 not in cells or (lv and cells[rc1] and lv[0] > cells[rc1][0]):
                    cells[rc1] = lv
        sig = dict(dir=d, cells=cells, mark=mark, scale=scale, levels=cuts)
        if ss.opt("note", True, "bool"):
            # 兩句可以疊：前半講「標哪一格」（mark），後半講「多深」（深淺分級）
            signote = (SIG_NOTE_MAX if mark == "max" else SIG_NOTE) % SIG_DIRW[d]
            if cuts:
                c1, c2 = _sig_num(cuts[0]), _sig_num(cuts[1])
                signote += SIG_NOTE_LV % (scale, c1, c1, c2, c2)
    return rowspan, groups, sig, signote, cgroups


def _sig_num(x):
    """把切點／強度值印成人看的字串（去掉尾巴的 0，不做四捨五入以外的加工）。"""
    s = f"{float(x):.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _sig_scale(ss, pairs):
    """v1.6：讀 sig 的 scale／levels。回傳 (統計量名稱, [切點1, 切點2]) 或 (None, None)。

    pairs 只要有任何一組帶 `v`，就是分階模式，scale 與 levels 都必填——引擎不知道你填的是
    |t| 還是 -log10(p)，門檻差十萬八千里，猜錯會讓讀者把「弱證據」看成「強證據」。"""
    graded = any(isinstance(p, dict) and p.get("v") not in ("", None) for p in pairs)
    if not graded:
        for k in ("scale", "levels"):
            if ss.has(k):
                raise DeclError(ss.ln(k), f"pairs 都沒有寫 `v`（檢定強度），就不用寫 `{k}`",
                                "要分深淺就每一組都寫 v: 4.8；只要單一階底色就把 scale／levels 拿掉"
                                "（＝v1.5 的行為）")
        return None, None
    scale = ss.req("scale", "str",
                   "scale: 寫強度值是哪一種統計量，例 scale: \"|t|\"、scale: \"-log10(p)\"、scale: \"Cohen's d\""
                   "（會印進備註，讀者才知道底色深淺在量什麼）")
    lv = ss.req("levels", "list",
                "levels: 兩個切點（由小到大），例 |t| 用 [2.6, 3.3]、-log10(p) 用 [2, 3]（＝p<0.01、p<0.001）")
    if len(lv) != 2:
        raise DeclError(ss.ln("levels"),
                        f"levels 要剛好兩個切點（三階），現在有 {len(lv)} 個",
                        f"底色固定 {SIG_LEVELS} 階：< 切點1／切點1 ~ 切點2／≥ 切點2。"
                        "階數不開放調整——列印與灰階下四階以上的明度差分不出來")
    cuts = []
    for j, x in enumerate(lv):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or x in (float("inf"), float("-inf")):
            raise DeclError(ss.ln("levels"), f"levels 第 {j + 1} 個 {x!r} 不是數字",
                            "兩個切點都要是數字，例 [2.6, 3.3]")
        if x < 0:
            raise DeclError(ss.ln("levels"), f"levels 第 {j + 1} 個 {_sig_num(x)} 是負的",
                            "強度值是 |t|／-log10(p)／效果量絕對值，一律非負（沿用顯著度熱圖的規矩）")
        cuts.append(float(x))
    if not cuts[0] < cuts[1]:
        raise DeclError(ss.ln("levels"),
                        f"levels 要由小到大且不相等（現在是 {_sig_num(cuts[0])}、{_sig_num(cuts[1])}）",
                        "第一個切點＝第 1 階與第 2 階的界、第二個＝第 2 階與第 3 階的界")
    return scale, cuts


def _sig_level(ps, i, cuts):
    """一組 pair 的強度值 → (第幾階, 印出來的值)；沒分階時回 None。"""
    if not cuts:
        if ps.has("v"):
            raise DeclError(ps.ln("v"), f"sig.pairs 第 {i + 1} 項寫了 v，但其他組沒寫",
                            "要嘛每一組都寫 v（底色分三階），要嘛全部不寫（單一階，＝v1.5 的行為）")
        return None
    v = ps.req("v", "num",
               "v＝這組配對的檢定強度（非負，例 |t| 4.8、-log10(p) 3.2）"
               "——要嘛每一組都寫，要嘛全部不寫（全部不寫＝單一階）")
    if v != v or v in (float("inf"), float("-inf")):
        raise DeclError(ps.ln("v"), f"sig.pairs 第 {i + 1} 項的 v 不是有限的數字（{v!r}）")
    if v < 0:
        raise DeclError(ps.ln("v"), f"sig.pairs 第 {i + 1} 項的 v 是負的（{_sig_num(v)}）",
                        "強度值一律非負：帶號 t 值請填 |t|，p 值請換成 -log10(p)"
                        "（色階只編碼證據強弱，方向看 ▲▼ 與正負號）")
    lvl = 1 + (v >= cuts[0]) + (v >= cuts[1])
    return (lvl, _sig_num(v))


def type_help():
    """給 build.py --types 印：每種類型的欄位。"""
    out = []
    for name, t in TYPES.items():
        out.append(f"{name:<11}{t['doc']}")
        out.append(f"{'':11}欄位：{'、'.join(k for k in t['fields'] if k not in COMMON)}")
        for sub, fs in t["item_fields"].items():
            out.append(f"{'':11}{sub} 每項：{'、'.join(fs)}")
    out.append(f"{'（共用）':<10}{'、'.join(COMMON)}")
    out.append(f"{'table':<11}{'、'.join(TABLE_FIELDS)}")
    return "\n".join(out)
