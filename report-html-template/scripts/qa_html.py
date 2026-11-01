# -*- coding: utf-8 -*-
"""qa_html — 交付前自我檢查（skill 版：純 stdlib；有 node 就多跑 node --check，沒有也能全綠）。

    python3 qa_html.py out/報告.html

檢查項目
  1  所有 href="#..." 都有對應的 id（錨點零死連結）
  2  id 不重複
  3  圖表編號連續無跳號（每章 圖 c-1..c-k / 表 c-1..c-j）
  4  每張圖表都至少被文中的「圖 c-i」引用一次（正向連結）
  5  每個變化數字都同時有 ▲／▼ 與正負號（顏色不是唯一線索）
  6  重點紅字：每段最多 3 處（v1.11 依 Lena 2026-09-17 11:57 從「每段一處」放寬）＋
     每一處 .hl 的**最終生效** color／background 都要真的是重點紅（CSS 串接算出來，不是 grep 原始碼）
  7  零外部資源：任何屬性裡都不得出現 http(s):// 或 //cdn
  8  inline JS 與引擎版本逐字元相同（md5 常數，v1.1／v1.2 79e2d5b4…；v1 是 4a73b940…）；本機有 node 再多跑 node --check
  9  三份 HTML 結構與數字完全相同（只差 <style> 與 body class 與風格標籤）
 10  紅綠只用在方向語意（列出 SVG 內 c-up／c-dn 出現在哪幾張圖）
 11  互動掛勾都在（十字準線／吸附／序列開關／tooltip／可排序表；v1.2 熱圖要有格子 tooltip；
     v1.5 宣告 rowspan／row_groups 的表固定列序＝不可排序，帶 data-fixed="1"，不列入可排序表）
 12  v3 e：「回到引用處」相關的 class／id／JS／CSS 全部為 0
 13  v3 e：圖表備註沒有殘留反白（背景色／膠囊）樣式
 14  v3 d：目錄項目數 == 區塊標頭（h2）數，且不含圖表項
 15  v3 f：H1／H2／H3 的實際字級兩兩之間有明顯級差
 16  標頭 icon 是 inline SVG（不是 emoji／icon 字型）
 17  v1.8：每張圖表的備註最多四列——維度／指標／著色（defs 最多三行、順序固定、至少一行）
     ＋ 母體（note 剛好一行）；v1.6 原本要求剛好四列，Lena 2026-09-16 17:38 第 e 點改成
     「非必要不需要 notes_extra、維度」，所以 defs 只檢查 1~3 行與順序
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

# v1.11 第 6 項要算「最終生效值」，用的是 v1.9 就有的那一套串接判定器
# （tests/cssres.py：specificity ＋ 出現順序 ＋ inline；tests/htmlres.py：對象換成 HTML 元素）。
# 不另外寫一份簡化版——兩份判定器會各自漂移，v1.8 的顏色 bug 就是這樣漏掉的。
_TESTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
try:
    import htmlres as _htmlres
except Exception as _e:                     # noqa: BLE001
    _htmlres, _HTMLRES_ERR = None, _e
else:
    _HTMLRES_ERR = None

OK, BAD = "OK", "FAIL"
# <script> 區塊 md5：互動 JS 不准變（改了就要重跑等價驗證、更新這個常數並在說明檔寫明）。
# v1.1（2026-09-14）：JS 只「新增」第 9 段（分群長條的圖例切換 handler，掛在 data-kind="bar" 的
# g.lgd[data-key] 上），既有 1～8 段逐字元不變。v1／v3 定稿的 md5 是 4a73b94088ed8fc03bccee87ab75fab2。
# v1.2（2026-09-14）：JS 沒動——堆疊長條沿用第 9 段的圖例切換、cohort 熱圖只用第 7 段的 tooltip，常數不變。
JS_MD5 = "79e2d5b43d53764e88de8a6771c64253"

# v1.11：重點紅字的上限與「最終生效」該長什麼樣。HL_MAX 與 mdcontent.HL_MAX 是同一個數字
# （build 期擋在前面、qa 期擋在後面，手改過 HTML 也跑不掉）。
HL_MAX = 3
HL_COLOR = "var(--up)"       # .hl{color:var(--up)}          themes.py L230
HL_BG = "var(--up-bg)"       # .theme-b .hl{background:...}   themes.py L540


class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.hrefs = []          # (href, tag, classes)
        self.ext = []            # 外部資源
        self.svgs = []           # (aria-label 有無, desc 有無)
        self.tables = 0
        self.sortable = 0
        self.fixed = 0           # v1.5：rowspan／列群組的表（合併格排序會散掉，設計上不排序）
        self.in_svg = 0
        self.deco = 0
        self.cur_svg_desc = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if "id" in a:
            self.ids.append(a["id"])
        for k in ("href", "src", "srcset", "data-src", "action", "poster"):
            v = a.get(k)
            if not v:
                continue
            if k == "href":
                self.hrefs.append((v, tag, cls))
            if re.match(r"^\s*(https?:)?//", v) or "cdn" in v.lower():
                self.ext.append((tag, k, v))
        if tag == "svg":
            self.in_svg += 1
            self.cur_svg_desc = False
            if a.get("aria-hidden") == "true":       # 裝飾用 icon，不列入
                self.deco += 1
            else:
                self.svgs.append([bool(a.get("aria-label")), a.get("role"),
                                  False])
        if tag == "desc" and self.in_svg:
            self.cur_svg_desc = True
            if self.svgs:
                self.svgs[-1][2] = True
        if tag == "table":
            self.tables += 1
            if "sortable" in cls:
                self.sortable += 1
            if a.get("data-fixed"):
                self.fixed += 1

    def handle_endtag(self, tag):
        if tag == "svg":
            self.in_svg = max(0, self.in_svg - 1)


def check(path):
    html = io.open(path, encoding="utf-8").read()
    res = []
    p = Scan()
    p.feed(html)
    ids = p.ids
    idset = set(ids)

    # 1 錨點
    frag = [(h[1:], t, c) for h, t, c in p.hrefs if h.startswith("#")]
    dead = [f for f, t, c in frag if f not in idset]
    res.append(("1 錨點", len(frag), OK if not dead else BAD,
                "全部命中" if not dead else f"死連結 {dead[:8]}"))

    # 2 重複 id
    dup = sorted({i for i in ids if ids.count(i) > 1})
    res.append(("2 id 唯一", len(ids), OK if not dup else BAD,
                "無重複" if not dup else f"重複 {dup[:8]}"))

    # 3 編號連續
    caps = re.findall(r'<span class="cap-no">(圖|表) ([A-Z0-9]+)-(\d+)</span>',
                      html)
    seen = {}
    for kind, ch, i in caps:
        seen.setdefault((kind, ch), []).append(int(i))
    gaps = []
    for k, v in sorted(seen.items()):
        if sorted(v) != list(range(1, len(v) + 1)):
            gaps.append((k, v))
    res.append(("3 圖表編號", len(caps), OK if not gaps else BAD,
                ("連續：" + "／".join(f"{k[0]} {k[1]}-1..{max(v)}"
                                    for k, v in sorted(seen.items())))
                if not gaps else f"跳號 {gaps}"))

    # 4 正向引用（v3：回跳功能已移除，只檢查每張圖表都有被引用到）
    anchors = re.findall(r'<(?:figure|div) class="blk (?:fig|tbl)" id="([^"]+)"',
                         html)
    xrefs = re.findall(r'<a class="xref" href="#([^"]+)"', html)
    reffed = set(xrefs)
    unref = [a for a in anchors if a not in reffed]
    dead = [x for x in xrefs if x not in idset]
    res.append(("4 正向引用", f"{len(xrefs)} 引用／{len(anchors)} 圖表",
                OK if (not unref and not dead) else BAD,
                f"未被引用 {unref}／死連結 {dead}"
                if (unref or dead) else
                f"每張圖表都至少被引用一次，{len(xrefs)} 個連結全部命中"))

    # 5 變化數字：顏色不是唯一線索
    chips = re.findall(r'<span class="chg (up|dn|flat)"[^>]*>(.*?)</span></span>',
                       html, re.S)
    bad_chip = [c for c in chips
                if not re.search(r"[▲▼–]", c[1])
                or not re.search(r'class="chg-n">[+\-–]', c[1])]
    res.append(("5 ▲▼＋正負號", len(chips), OK if not bad_chip else BAD,
                "每個變化數字都有箭頭與正負號"
                if not bad_chip else f"缺箭頭或正負號 {len(bad_chip)} 個"))

    # 6 重點紅字克制
    #   v1.11（Lena 2026-09-17 11:57「改引擎，同一段可以多處紅字，不要分段」）：
    #   上限從 1 放寬成 HL_MAX=3。放寬的是**處數**，不是「不檢查」，所以同一項補兩條：
    #     (a) 同段處數 ≤ HL_MAX（切段方式與 v1.10 完全相同，一個字沒改）
    #     (b) 每一處 .hl 的**最終生效** color／background 都要是重點紅
    #         ——同段可以放三處之後，「有沒有真的紅」比「有幾處」更容易出事，
    #           而且不能用 grep 原始碼交差（v1.8 顏色 bug 的教訓）。
    hl_par = [len(re.findall(r'<span class="hl">', seg))
              for seg in re.split(r"</p>|</li>", html)]
    over = [c for c in hl_par if c > HL_MAX]
    n_hl = sum(hl_par)
    bad_color = []
    if _htmlres is None:
        bad_color.append(f"（算不出最終生效值：{_HTMLRES_ERR}）")
    elif n_hl:
        def _is_hl(rec):
            return rec["tag"] == "span" and "hl" in rec["chain"][-1][1]
        for prop, want in (("color", HL_COLOR), ("background", HL_BG)):
            for rec, src, val in _htmlres.resolve(html, prop, _is_hl):
                if val != want:
                    bad_color.append(f"{rec['text'][:12]!r} {prop}={val}（{src}，要 {want}）")
    ok6 = not over and not bad_color
    res.append(("6 重點紅字", n_hl, OK if ok6 else BAD,
                f"共 {n_hl} 處，每段最多 {HL_MAX} 處；"
                f"每一處最終生效 color={HL_COLOR}／background={HL_BG}"
                if ok6 else
                (f"有段落超過 {HL_MAX} 處：{over}；" if over else "")
                + (f"顏色沒生效：{bad_color[:3]}" if bad_color else "")))

    # 7 零外部資源
    prot = len(re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html))
    res.append(("7 零外部資源", f"{len(p.ext)} 個屬性",
                OK if not p.ext and not prot else BAD,
                "無任何外部 src/href（離線可開）"
                if not p.ext and not prot else f"{p.ext[:4]}"))

    # 8 JS：與引擎版本逐字元相同（md5 常數）；有 node 再多做語法檢查
    js = re.findall(r"<script>(.*?)</script>", html, re.S)
    jsres = "沒有 <script>"
    st = BAD
    if len(js) == 1:
        h = hashlib.md5(js[0].encode("utf-8")).hexdigest()
        same = (h == JS_MD5)
        st = OK if same else BAD
        jsres = (f"md5 {h[:10]}… ＝ v1.1 定稿（{len(js[0].splitlines())} 行）" if same
                 else f"md5 {h[:10]}… ≠ v1.1 定稿 {JS_MD5[:10]}…（互動 JS 被改過）")
        if shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                             encoding="utf-8") as fh:
                fh.write(js[0])
                tmp = fh.name
            r = subprocess.run(["node", "--check", tmp], capture_output=True,
                               text=True)
            if r.returncode != 0:
                st = BAD
                jsres += "；node --check 失敗：" + r.stderr.strip()[:200]
            else:
                jsres += "；node --check 通過"
        else:
            jsres += "；本機無 node，略過語法檢查"
    elif js:
        jsres = f"有 {len(js)} 個 <script>，應該只有 1 個"
    res.append(("8 JS 語法", len(js), st, jsres))

    # 9 SVG 無障礙
    no_aria = [s for s in p.svgs if not s[0] or s[1] != "img"]
    no_desc = [s for s in p.svgs if not s[2]]
    res.append(("9 圖無障礙", f"{len(p.svgs)}＋{p.deco} 裝飾",
                OK if not no_aria and not no_desc else BAD,
                "每張圖都有 role=img＋aria-label＋desc"
                if not no_aria and not no_desc
                else f"缺 aria {len(no_aria)}／缺 desc {len(no_desc)}"))

    # 10 紅綠只用在方向語意
    svg_blocks = re.findall(r"<svg class=.*?</svg>", html, re.S)
    where = []
    for i, sb in enumerate(svg_blocks, 1):
        cnt = len(re.findall(r'class="bar c-(?:up|dn|dn2)"', sb))
        if cnt:
            where.append(f"#{i}:{cnt}")
    cat_rg = len(re.findall(r'class="(?:ser|band) c-(?:up|dn)"', html))
    res.append(("10 紅綠語意", f"{len(where)}/{len(svg_blocks)} 張圖用到方向色",
                OK if cat_rg == 0 else BAD,
                f"方向色只出現在 {', '.join(where)}（瀑布／貢獻排序）；"
                f"類別序列用紅綠：{cat_rg} 處"))

    # 11 互動掛勾（依圖型而定：有時間序列圖才要求十字準線／圖例；有柱狀圖才要求 tooltip；
    #    有表格才要求可排序）
    n_xy = html.count('<svg class="chart" data-kind="xy"')
    n_bar = html.count('<svg class="chart" data-kind="bar"')
    n_heat = html.count('<svg class="chart" data-kind="heat"')      # v1.2 cohort 熱圖：只有格子 tooltip
    heat_marks = sum(sb.count('class="mark" data-tip') for sb in
                     re.findall(r'<svg class="chart" data-kind="heat".*?</svg>', html, re.S))
    hooks = {
        "十字準線": html.count('class="crosshair"'),
        "吸附命中區": html.count('class="hit"'),
        "focus 點": html.count('class="focus'),
        "可切換圖例": html.count('class="lgd" data-key'),
        "柱段 tooltip": html.count('class="mark" data-tip'),
        "分群圖例": len(re.findall(r'<svg class="chart" data-kind="bar".*?</svg>', html, re.S)) and
                sum(sb.count('class="lgd" data-key') for sb in re.findall(r'<svg class="chart" data-kind="bar".*?</svg>', html, re.S)),
        "熱圖格 tooltip": heat_marks,
        "可排序表": p.sortable,
        "固定列序表（rowspan／列群組）": p.fixed,
    }
    ok11 = ((n_xy == 0 or (hooks["十字準線"] == n_xy and hooks["吸附命中區"] and
                           hooks["focus 點"] and hooks["可切換圖例"]))
            and (n_bar == 0 or hooks["柱段 tooltip"])
            and (n_heat == 0 or heat_marks)
            and p.sortable + p.fixed == p.tables)
    res.append(("11 互動掛勾", f"xy {n_xy}／bar {n_bar}／heat {n_heat}／表 {p.tables}",
                OK if ok11 else BAD,
                "・".join(f"{k} {v}" for k, v in hooks.items())))

    # 12 「回到引用處」殘留（class／id／JS／CSS／文案）
    style = "".join(re.findall(r"<style>(.*?)</style>", html, re.S))
    # 「本版說明」是 changelog，提到「移除了↩回到引用處」不算功能殘留
    body_only = re.sub(r'<details class="verinfo">.*?</details>', "", html,
                       flags=re.S)
    ghosts = {
        'class="backref"': html.count("backref"),
        'id="xref-*"': len(re.findall(r'id="xref-', html)),
        "fig-back": html.count("fig-back"),
        "回到引用處（正文）": body_only.count("回到引用處"),
        "↩（正文）": body_only.count("\u21a9"),
        ".flash／keyframes": len(re.findall(r"flash|@keyframes fl\b", html)),
        "data-sites": html.count("data-sites"),
    }
    left = {k: v for k, v in ghosts.items() if v}
    res.append(("12 回跳殘留", sum(ghosts.values()), OK if not left else BAD,
                "class／id／JS／CSS／文案全部為 0"
                if not left else f"還有殘留：{left}"))

    # 13 圖表備註不反白：.blk-note／.blk-def 的規則不得帶背景或膠囊
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", style)
    bad_note = []
    for sel, decl in rules:
        if not re.search(r"\.blk-note|\.blk-def|\.def-r", sel):
            continue
        for prop in ("background", "border-radius", "padding"):
            m = re.search(prop + r"\s*:\s*([^;]+)", decl)
            if m and "transparent" not in m.group(1) and m.group(1).strip() != "0":
                bad_note.append(f"{sel.strip()} {{{prop}:{m.group(1).strip()}}}")
    res.append(("13 備註不反白", len(rules), OK if not bad_note else BAD,
                "備註／定義列都是一般小字（無底色、無膠囊）"
                if not bad_note else f"還有反白樣式：{bad_note[:3]}"))

    # 14 目錄只列區塊標頭
    toc_items = len(re.findall(r'class="toc-link toc-l1"', html))
    h2 = re.findall(r'<h2 class="sec-h">.*?</h2>', html, re.S)
    toc_figs = len(re.findall(r'class="toc-l2"|class="toc-sub"', html))
    heads = len(h2) + 1                      # 前言（header）沒有 h2，另計
    res.append(("14 目錄項目", f"{toc_items} 項／區塊標頭 {heads} 個",
                OK if (toc_items == heads and toc_figs == 0) else BAD,
                f"一一對應、沒有圖表項（h2 {len(h2)} ＋ 前言 1）"
                if (toc_items == heads and toc_figs == 0)
                else f"目錄 {toc_items} vs 標頭 {heads}／圖表項 {toc_figs}"))

    # 15 字級階層 H1 > H2 > H3 > 正文
    def px(name):
        vals = re.findall(r"--%s:\s*([\d.]+)px" % name, style)
        return float(vals[-1]) if vals else None
    h1, h2s, h3 = px("h1"), px("h2"), px("h3")
    body = re.findall(r"font-size:\s*([\d.]+)px;line-height", style)
    base = 16.0
    ok15 = None not in (h1, h2s, h3) and h1 - h2s >= 6 and h2s - h3 >= 5 \
        and h3 - base >= 3 and h1 / h2s >= 1.2 and h2s / h3 >= 1.25
    res.append(("15 字級階層",
                f"H1 {h1}／H2 {h2s}／H3 {h3}／正文 {base}",
                OK if ok15 else BAD,
                f"級差 {h1-h2s:.0f}／{h2s-h3:.0f}／{h3-base:.0f} px"
                f"（比例 {h1/h2s:.2f}／{h2s/h3:.2f}／{h3/base:.2f}）"
                if ok15 else "級差不足或抓不到 --h1/--h2/--h3"))

    # 16 有沒有 icon（inline SVG、不是 emoji／icon 字型）
    icos = len(re.findall(r'<span class="sec-ico"', html))
    emoji = len(re.findall("[\U0001F000-\U0001FAFF\u2600-\u27bf"
                           "\u2705\u2714\u2b50\ufe0f]", html))
    fonts = len(re.findall(r"font-awesome|fa-|material-icons", html, re.I))
    res.append(("16 標頭 icon", icos,
                OK if (icos == 2 and not emoji and not fonts) else BAD,
                "結論／建議各一個 inline SVG icon，無 emoji、無 icon 字型"
                if (icos == 2 and not emoji and not fonts)
                else f"icon {icos} 個／emoji {emoji}／icon 字型 {fonts}"))

    # 17 備註列數（Lena 2026-09-16 15:12 定四列，17:38 第 e 點放寬，2026-09-17 第 1 點
    #    再放寬母體那一列）：每個圖表區塊底下是 維度／指標／著色 裡挑 1~3 行（順序固定）
    #    ＋ 母體註腳 0 或 1 行。多寫一個 defs key 就是第五列，build.py 會先擋下來；
    #    這裡是給「手改過 HTML」留的後門檢查。
    #    v1.9 母體那一列從「剛好 1 行」改成「0 或 1 行」（檔頭 note_base 變選填），
    #    補上一條更嚴的：**不准出現空的 <p class="blk-note"></p>**——放寬的是「可以不印」，
    #    不是「可以印一個空殼」。
    parts = re.split(r'<(?:figure|div) class="blk (?:fig|tbl)" id="([^"]+)"', html)[1:]
    bad_note, order = [], ["維度", "指標", "著色"]
    n_empty = 0
    for key, chunk in zip(parts[0::2], parts[1::2]):
        ks = re.findall(r'<div class="def-r"><dt>([^<]*)</dt>', chunk)
        nd = chunk.count('<div class="def-r">')
        nn = chunk.count('<p class="blk-note">')
        empty = len([m for m in re.findall(r'<p class="blk-note">(.*?)</p>', chunk, re.S)
                     if not re.sub(r"<[^>]+>|\s", "", m)])
        n_empty += empty
        bad_k = [k for k in ks if k not in order]
        seq_ok = ks == [k for k in order if k in ks]
        if not (1 <= nd <= 3) or nn > 1 or empty or bad_k or not seq_ok:
            bad_note.append(f"{key}（定義 {nd} 列{'／'.join([''] + ks)}／母體 {nn} 列"
                            + ("／其中 %d 列是空的" % empty if empty else "") + "）")
    nblk = len(parts) // 2
    res.append(("17 備註列數", f"{nblk} 個圖表區塊", OK if not bad_note else BAD,
                "每張圖表都是 維度／指標／著色 裡的 1~3 列（順序固定）＋ 母體 0~1 列、沒有空殼列"
                if not bad_note else f"列數或順序不對：{bad_note[:4]}"))

    return html, res


def norm(html):
    """抹掉「風格」相關差異，剩下的必須三份完全相同。"""
    s = re.sub(r"<style>.*?</style>", "<style>[STYLE]</style>", html, flags=re.S)
    s = re.sub(r'<body class="theme-[abc]">', '<body class="theme-X">', s)
    s = re.sub(r'<p class="stylebadge">.*?</p>',
               '<p class="stylebadge">[LABEL]</p>', s, flags=re.S)
    return s


def main(paths):
    if not paths:
        print("用法：python3 qa_html.py <報告.html>")
        return 2
    htmls = {}
    allok = True
    for path in paths:
        html, res = check(path)
        htmls[path] = html
        print(f"\n=== {path.split('/')[-1]} "
              f"（{len(html.encode('utf-8'))/1024:.0f} KB）===")
        for name, cnt, st, msg in res:
            allok &= (st == OK)
            print(f"  [{st:4}] {name:12} {str(cnt):22} {msg}")

    if len(paths) > 1:
        print("\n=== 三份一致性（結構與數字） ===")
        sig = {p: hashlib.md5(norm(h).encode()).hexdigest()
               for p, h in htmls.items()}
        same = len(set(sig.values())) == 1
        allok &= same
        print(f"  [{OK if same else BAD}] 抹掉 <style>／body class／風格標籤後 "
              f"md5 {'完全相同' if same else '不同'}：")
        for p, s in sig.items():
            print(f"        {s}  {p.split('/')[-1]}")
        base = paths[0]
        for p in paths[1:]:
            a = norm(htmls[base]).splitlines()
            b = norm(htmls[p]).splitlines()
            diff = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            print(f"        內容行差異 {base.split('/')[-1]} vs "
                  f"{p.split('/')[-1]}：{diff} 行")
        # 未抹掉 style 時的差異行數（讓人看到差異只在 style 區）
        for p in paths[1:]:
            a = htmls[base].splitlines()
            b = htmls[p].splitlines()
            diff = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            print(f"        原始行差異（含 <style>）：{diff} 行 "
                  f"→ {p.split('/')[-1]}")
    print(f"\n總結：{'全部通過' if allok else '有項目未通過'}")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
