# -*- coding: utf-8 -*-
"""svgchart — 手寫 inline SVG 圖表（可互動，零外部函式庫、零 CDN、零字型檔）。

為什麼自己畫，不用 Chart.js／Plotly／D3
  1. 單檔離線可開、可轉 PDF：不能有任何外部 <script src>。
  2. 我們要的圖型（分位帶＋斷點陰影、瀑布、貢獻排序堆疊）現成庫都得繞。
  3. 顏色與線型紀律要能寫死（紅漲綠跌、mean 墨色虛線不與分位數共用線型）。

靜態完整、互動加值
  SVG 標記本身就是完整的圖（軸、格線、線、柱、關鍵值直接標註都在標記裡）。
  JS 只做四件事：十字準線、tooltip、序列開關、focus 點位移動。
  關掉 JS 或列印時圖照樣完整可讀。

互動掛勾（給 rhtml.py 的 JS 用，不要改名）
  svg.chart[data-kind="xy"]     時間序列／分位帶：十字準線＋吸附＋tooltip＋序列開關
  g.plot[data-xs][data-labs]    每個 x 的像素位置與標籤
  [data-vals]                   序列數值（CSV，順序同 x）；band 另有 data-vals2
  rect.hit[data-i]              每個 x 的命中區
  line.crosshair / circle.focus 靜態存在、預設隱藏，JS 只移動它
  g.mark[data-tip]              柱／段的命中區，data-tip 是 JSON：{"t":標題,"r":[[標籤,值]]}
  g.lgd[data-key]               可點的直接標註（＝圖例），切換 [data-key] 的 .off
  v1.3（2026-09-14）新增 histogram／dumbbell 兩個畫法、waterfall 擴到 N 段（含 subtotal）、heatmap 通用化給
  dow_hour 用；全部只用上面既有的掛勾與 CSS class，rhtml.py 的 JS 與 themes.py 的 CSS 一個 byte 都沒動。
  v1.4（2026-09-16）只動 xy_chart：多一個 vlines 參數（多條垂直事件虛線，沿用 .bkline 線型、顏色走 inline
  stroke）；新圖型 sigheat 直接沿用既有 heatmap，JS 與 CSS 同樣一個 byte 都沒動。
  v1.8（2026-09-16）修 v1.4 起就存在的顏色 bug：vlines 的紅色本來寫成 presentation attribute
  （stroke="…"／fill="…"），但 CSS 有 `.chart .bkline{stroke:var(--ink2)}` 與 `.chart .bkl{fill:var(--ink2)}`，
  presentation attribute 的優先權低於任何 class 規則 → 紅色從來沒有渲染出來，跟其他事件線同一個灰。
  改成 inline style="stroke:…"／style="fill:…"（優先權高於 class 規則，做法與 v1.5 檢定底色相同），
  CSS 一個 byte 都不用動。v1.8 另加 vlines 的第二行標籤（label2，宣告才生效）。

顏色一律用 CSS class（SVG presentation attribute 不吃 var()），
定義在 themes.py 的共用基礎裡，所以三種風格的圖表標記完全相同。
"""
import html as _html
import json
import math

# v3：內容容器加寬（風格 B 的 --docw 1120px、左右 padding 縮小）後，
# 圖的實際繪圖寬度約 1044px。viewBox 寬度跟著重算成 1120，
# 讓 SVG 的縮放比維持 ~0.93（v2 是 1000/780≈0.78）：
# 字級是等比縮放不是拉扁，比例不變、實際字級反而變大（15px → 14px 有效）。
VB_W = 1120.0


# ---------------------------------------------------------------- 小工具
def esc(s):
    return _html.escape(str(s), quote=True)


def n(v, nd=1):
    """數字→字串，去掉多餘的 0（SVG 座標用）。"""
    s = f"{float(v):.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt(v, nd=1, sign=False, unit=""):
    s = f"{v:+.{nd}f}" if sign else f"{v:,.{nd}f}"
    return s + unit


def tipjson(title, rows):
    return esc(json.dumps({"t": title, "r": [[a, b] for a, b in rows]},
                          ensure_ascii=False))


def nice_ticks(lo, hi, target=5):
    """好看的軸刻度。回傳 (ticks, lo, hi)。"""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(target, 2)
    if abs(raw) >= 1:
        mag = 10 ** (len(f"{int(abs(raw))}") - 1)
    else:
        # v4（skill 版）修正：原式 10 ** -len(小數位去前導零) 對 0.625、0.05 這類值會算出
        # 1e-9～1e-10 的刻度，底下的 while 迴圈要跑幾十億次（示意資料間距都 ≥ 1 所以沒踩到）。
        # 改成正確的量級：10^floor(log10(raw))。raw ≥ 1 的分支與輸出完全不變。
        mag = 10.0 ** math.floor(math.log10(abs(raw))) if raw > 0 else 1.0
    for m in (1, 2, 2.5, 5, 10):
        step = mag * m
        if step >= raw:
            break
    t0 = step * (lo // step)
    ticks = []
    v = t0
    while v <= hi + step * .001 and len(ticks) < 1000:     # 上限：任何情況都不准跑不完
        if v >= lo - step * .001:
            ticks.append(round(v, 10))
        v += step
    if not ticks:
        ticks = [lo, hi]
    return ticks, min(ticks[0], lo), max(ticks[-1], hi)


class Scale:
    def __init__(self, d0, d1, p0, p1):
        self.d0, self.d1, self.p0, self.p1 = float(d0), float(d1), p0, p1
        self.k = (p1 - p0) / ((d1 - d0) or 1.0)

    def __call__(self, v):
        return self.p0 + (float(v) - self.d0) * self.k


def _svg_open(h, kind, aria, desc):
    return (f'<svg class="chart" data-kind="{kind}" role="img" '
            f'viewBox="0 0 {n(VB_W)} {n(h)}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'aria-label="{esc(aria)}"><desc>{esc(desc)}</desc>')


def _hint(x, y, text):
    return f'<text class="an hint" x="{n(x)}" y="{n(y)}">{esc(text)}</text>'


# v1.6 新增：折線事件線（vlines）的警示 icon。形狀與 rhtml.ICON_WARN 的行內
# {{warn}} 完全一樣（24×24 viewBox 的紅色三角驚嘆號），縮放後畫在事件線的**下端**，
# 所以正文的 {{warn}} 與圖上的標記是同一個符號。不用 emoji、不引字型、不改 CSS。
# 只有 vlines 宣告 icon: warn 才會呼叫到；沒宣告時 xy_chart 的輸出逐 byte 不變。
WARN_RED = "#c62828"
WARN_SCALE = 0.62          # 24 × 0.62 ≒ 14.9px 高
WARN_LIFT = 7.0            # icon 底邊離 x 軸的距離

# v1.7 新增：xy_chart 的圖例可以從右側搬到 x 軸下方（legend="bottom"）。
# 右側圖例本來吃掉 m 的 R＝158px；搬到下面之後 R 縮回 LGD_B_R、下邊界多留 LGD_B_H
# 一條圖例帶。事件線的 warn icon 與標籤掛在 T+ph（繪圖區底緣）跟著繪圖框走，
# 圖例畫在 T+ph+LGD_B_DY（＞x 軸刻度文字的 T+ph+22），兩者不會疊。
# 只有宣告 legend: bottom 才走這條；不宣告時 xy_chart 的輸出逐 byte 同 v1.6。
LGD_B_R = 26.0             # 圖例搬走之後右邊只留呼吸空間
LGD_B_H = 46.0             # 下邊界多留的圖例帶高度
LGD_B_DY = 44.0            # 圖例文字基線離繪圖區底緣的距離（x 軸刻度在 +22）
LGD_SW_W = 20.0            # 色塊／線段寬（與右側圖例相同）
LGD_TX = 27.0              # 文字相對色塊左緣的位移（與右側圖例相同）
LGD_GAP = 30.0             # 兩個圖例項之間的間距

# v1.8 新增：vlines 的事件標籤可以拆成兩行（第一行日期、第二行事件名），
# 讓相鄰事件線的標籤不會左右撞在一起。只有宣告 label2 才會畫第二行；
# 不宣告時 xy_chart 的輸出與「v1.7 ＋ 顏色修正」逐 byte 相同。
VL_L2_DY = 17.0            # 第二行基線離第一行的距離（.an 13px ＋ 行距）


def warn_icon(cx, ybase, color=WARN_RED):
    """紅色三角驚嘆號：底邊中心對齊 (cx, ybase)。"""
    sc = WARN_SCALE
    x0, y0 = cx - 12.0 * sc, ybase - 24.0 * sc
    return (f'<g transform="translate({n(x0,2)},{n(y0,2)}) scale({n(sc,3)})" '
            f'fill="{color or WARN_RED}" aria-hidden="true">'
            f'<path d="M12 2.6 23 21.4H1z"></path>'
            f'<path d="M11.05 8.9h1.9v6.1h-1.9z" fill="#fff"></path>'
            f'<circle cx="12" cy="18.1" r="1.15" fill="#fff"></circle></g>')


# ---------------------------------------------------------------- XY 圖
def xy_chart(xlabels, series, aria, desc, ylab="", h=380.0, ymin=None,
             ymax=None, bk=None, bkspan=3, bklabel=None, hlines=(),
             xtick_every=7, ytick_n=5, m=(26, 158, 48, 62), hint=None,
             ylab_fmt=1, extra_marks="", xpos=None, vlines=(), xtick_at=None,
             legend="right"):
    """時間序列／分位帶。series 為 dict list：

    {"type":"line","key":..,"name":..,"vals":[..],"cls":"c-s1","w":2.4,
     "dash":False,"ord":1,"unit":"分","endlab":None,"tip":True,
     "marker":False}            # v1.1：True 在每個資料點畫空心圓（留存曲線用）
    {"type":"band","key":"band","name":"p25~p75","lo":[..],"hi":[..],
     "cls":"c-band","name2":"p25","ord":2}
    hlines: [(value, "標籤", "cls", x_from_idx, x_to_idx)] → 墨色虛線參考線
    xpos: v1.1 選用。每個 x 在 0~1 的相對位置（非等距 x，例如留存曲線 xscale: value
          把 D1/D3/D7/D14/D30 照天數放）。None＝等距類別軸（v1 行為，輸出逐 byte 不變）。
    xtick_at: v1.5 選用。要標出來的 x 索引清單（不等距刻度，例 5/1、6/1、7/1、8/1）。
          None＝沿用 xtick_every 每 N 個標一次（v1 行為，輸出逐 byte 不變）。
    legend: v1.7 選用。"right"（預設）＝序列名稱直接標在線的右端（v1～v1.6 行為，
          輸出逐 byte 不變）；"bottom"＝橫排圖例改放 x 軸下方，右邊界縮回
          LGD_B_R、下邊界加高 LGD_B_H（繪圖區因此變寬、變矮一條圖例帶）。
    vlines: (x 索引, 標籤, 顏色) 或 v1.6 起的 (x 索引, 標籤, 顏色, icon)，
          v1.8 起可再加第 5 個欄位 label2＝標籤第二行。
          icon 目前只有 "warn"＝紅色三角驚嘆號，畫在事件線**下端**、標籤跟著移到下面；
          不給第 4 個欄位（或給空字串）時輸出與 v1.5 逐 byte 相同。
          label2 不給（或給空字串）時只畫一行，輸出與 v1.7 逐 byte 相同（顏色修正除外）。
    """
    T, R, B, L = m
    if legend == "bottom":
        # 右側不用再留標註位 → 繪圖區變寬；下邊界多一條圖例帶
        R, B = LGD_B_R, B + LGD_B_H
    pw, ph = VB_W - L - R, h - T - B
    nx = len(xlabels)
    if xpos is None:
        xs = Scale(0, max(nx - 1, 1), L, L + pw)
    else:
        _xp = [L + pw * float(p) for p in xpos]
        xs = lambda i: _xp[int(i)]                    # noqa: E731
    vals_all = []
    for s in series:
        if s["type"] == "band":
            vals_all += list(s["lo"]) + list(s["hi"])
        else:
            vals_all += list(s["vals"])
    for hv in hlines:
        vals_all.append(hv[0])
    lo = min(vals_all) if ymin is None else ymin
    hi = max(vals_all) if ymax is None else ymax
    pad = (hi - lo) * .08
    ticks, lo2, hi2 = nice_ticks(lo - pad if ymin is None else lo,
                                 hi + pad if ymax is None else hi, ytick_n)
    ys = Scale(lo2, hi2, T + ph, T)

    o = [_svg_open(h, "xy", aria, desc)]
    A = o.append
    A(f'<g class="plot" data-xs="{",".join(n(xs(i), 2) for i in range(nx))}" '
      f'data-labs="{esc("|".join(xlabels))}">')

    # 斷點 ±N 天陰影（所有時間軸圖共用同一組，圖可上下對齊疊看）
    if bk is not None:
        x0, x1 = xs(max(bk - bkspan, 0)), xs(min(bk + bkspan, nx - 1))
        A(f'<rect class="bkband" x="{n(x0,2)}" y="{n(T)}" '
          f'width="{n(x1-x0,2)}" height="{n(ph)}"></rect>')

    # 格線與 y 軸刻度
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" '
          f'x2="{n(L+pw)}" y2="{n(y,2)}"></line>')
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" '
          f'text-anchor="end">{esc(fmt(t, ylab_fmt))}</text>')
    if ylab:
        A(f'<text class="lb ax" x="2" y="{n(T-10)}">{esc(ylab)}</text>')

    # x 軸
    A(f'<line class="axis" x1="{n(L)}" y1="{n(T+ph)}" x2="{n(L+pw)}" '
      f'y2="{n(T+ph)}"></line>')
    if xtick_at is None:
        for i in range(0, nx, xtick_every):
            A(f'<text class="lb xl" x="{n(xs(i),2)}" y="{n(T+ph+22)}" '
              f'text-anchor="middle">{esc(xlabels[i])}</text>')
        if (nx - 1) % xtick_every:
            A(f'<text class="lb xl" x="{n(xs(nx-1),2)}" y="{n(T+ph+22)}" '
              f'text-anchor="middle">{esc(xlabels[nx-1])}</text>')
    else:
        # v1.5：指定刻度清單＝只標這幾個（不自動補最後一個，指定什麼就是什麼）
        for i in xtick_at:
            A(f'<text class="lb xl" x="{n(xs(i),2)}" y="{n(T+ph+22)}" '
              f'text-anchor="middle">{esc(xlabels[i])}</text>')

    # 參考線（墨色虛線；mean 與分位數不共用線型）
    for hv in hlines:
        v, lab, cls, i0, i1 = hv[:5]
        lab_at = hv[5] if len(hv) > 5 else "start"
        y = ys(v)
        A(f'<line class="ref {cls}" x1="{n(xs(i0),2)}" y1="{n(y,2)}" '
          f'x2="{n(xs(i1),2)}" y2="{n(y,2)}"></line>')
        if lab_at == "end":
            A(f'<text class="vl refl" x="{n(xs(i1)-4,2)}" y="{n(y-8,2)}" '
              f'text-anchor="end">{esc(lab)}</text>')
        else:
            A(f'<text class="vl refl" x="{n(xs(i0)+6,2)}" y="{n(y-8,2)}">'
              f'{esc(lab)}</text>')

    # v1.4 新增：多條垂直事件虛線（vlines）。沿用 .bkline 線型；
    # 顏色以 inline style 指定（不改 CSS、不引外部資源），紅＝跌點。
    # v1.8 修正：本來用 presentation attribute（stroke=／fill=）指定顏色，會被
    # `.chart .bkline{stroke:var(--ink2)}`／`.chart .bkl{fill:var(--ink2)}` 這兩條
    # class 規則蓋掉（presentation attribute 的串接優先權低於任何 CSS 規則），
    # 紅色從來沒有渲染出來。改成 inline style 之後才真的紅。
    for _vl in vlines:
        vi, vlab, vcol = _vl[0], _vl[1], _vl[2]
        vicon = _vl[3] if len(_vl) > 3 else ""      # v1.6：選用，只有 "warn"
        vlab2 = _vl[4] if len(_vl) > 4 else ""      # v1.8：選用，標籤第二行
        xv = xs(vi)
        st = f' style="stroke:{vcol}"' if vcol else ""
        A(f'<line class="bkline" x1="{n(xv,2)}" y1="{n(T)}" x2="{n(xv,2)}" '
          f'y2="{n(T+ph)}"{st}></line>')
        fl = f' style="fill:{vcol}"' if vcol else ""
        if vicon == "warn":
            # v1.6：icon 與它的事件標籤一起放在圖下方（線的下端），不跟序列擠在圖頂
            yb = T + ph - WARN_LIFT
            A(warn_icon(xv, yb, vcol or WARN_RED))
            if vlab:
                # v1.8：有第二行時第一行往上推一個行高，第二行留在原本的基線
                ytop = yb - 3.5 - (VL_L2_DY if vlab2 else 0.0)
                A(f'<text class="an bkl" x="{n(xv+11,2)}" '
                  f'y="{n(ytop,2)}"{fl}>{esc(vlab)}</text>')
                if vlab2:
                    A(f'<text class="an bkl" x="{n(xv+11,2)}" '
                      f'y="{n(ytop+VL_L2_DY,2)}"{fl}>{esc(vlab2)}</text>')
        elif vlab:
            A(f'<text class="an bkl" x="{n(xv+6,2)}" y="{n(T+13)}"{fl}>'
              f'{esc(vlab)}</text>')
            if vlab2:
                # v1.8：第二行接在第一行下面一個行高（.an 13px／.bkl 粗體）
                A(f'<text class="an bkl" x="{n(xv+6,2)}" '
                  f'y="{n(T+13+VL_L2_DY)}"{fl}>{esc(vlab2)}</text>')

    # 斷點虛線
    if bk is not None:
        xb = xs(bk)
        A(f'<line class="bkline" x1="{n(xb,2)}" y1="{n(T)}" x2="{n(xb,2)}" '
          f'y2="{n(T+ph)}"></line>')
        if bklabel:
            A(f'<text class="an bkl" x="{n(xb+7,2)}" y="{n(T+13)}">'
              f'{esc(bklabel)}</text>')

    # 序列
    for s in series:
        key, cls = s["key"], s.get("cls", "c-s1")
        if s["type"] == "band":
            up = " ".join(f"{n(xs(i),2)},{n(ys(v),2)}"
                          for i, v in enumerate(s["hi"]))
            dn = " ".join(f"{n(xs(i),2)},{n(ys(v),2)}"
                          for i, v in reversed(list(enumerate(s["lo"]))))
            n3 = s.get("name3") or f'{s["name2"]}~{s["name"]}'
            A(f'<polygon class="band {cls}" data-key="{key}" '
              f'data-name="{esc(s["name"])}" data-name2="{esc(s["name2"])}" '
              f'data-name3="{esc(n3)}" '
              f'data-vals="{",".join(n(v,2) for v in s["hi"])}" '
              f'data-vals2="{",".join(n(v,2) for v in s["lo"])}" '
              f'data-unit="{esc(s.get("unit",""))}" '
              f'data-nd="{s.get("nd",1)}" '
              f'data-ord="{s.get("ord",0)}" points="{up} {dn}"></polygon>')
        else:
            pts = " ".join(f"{n(xs(i),2)},{n(ys(v),2)}"
                           for i, v in enumerate(s["vals"]))
            dash = ' stroke-dasharray="7 5"' if s.get("dash") else ""
            A(f'<polyline class="ser {cls}" data-key="{key}" '
              f'data-name="{esc(s["name"])}" '
              f'data-vals="{",".join(n(v,2) for v in s["vals"])}" '
              f'data-unit="{esc(s.get("unit",""))}" '
              f'data-nd="{s.get("nd",1)}" '
              f'data-ord="{s.get("ord",0)}" '
              f'stroke-width="{n(s.get("w",2.2),2)}"{dash} '
              f'points="{pts}"></polyline>')
            if s.get("marker"):
                # v1.1 點標記：空心圓走 .ser（fill:none）＋序列色 stroke，帶同一個 data-key，
                # 所以圖例切換／列印強制顯示都沿用既有 CSS；沒有 data-vals，JS 不會把它當序列。
                for i, v in enumerate(s["vals"]):
                    A(f'<circle class="ser pt {cls}" data-key="{key}" '
                      f'cx="{n(xs(i),2)}" cy="{n(ys(v),2)}" r="{n(s.get("marker_r", 4.6),2)}" '
                      f'stroke-width="{n(s.get("marker_w", 2.4),2)}"></circle>')

    A(extra_marks)

    # 直接標註（＝可點的圖例；序列 ≤4 用標註取代圖例框）
    # v1.7：legend="bottom" 改成 x 軸下方的橫排圖例（元素形狀、class、data-key 都不變，
    # 所以 JS 的序列開關與 CSS 完全沿用）；legend="right" 是預設，這段逐 byte 同 v1.6。
    if legend == "bottom":
        ents = []
        for s in series:
            if s.get("endlab") is False:
                continue
            txt = s.get("endlab") or s["name"]
            ents.append((txt, s["key"], s.get("cls", "c-s1"), s["type"],
                         bool(s.get("dash")),
                         LGD_TX + _tw(txt, 16.0)))
        total = sum(e[5] for e in ents) + LGD_GAP * max(len(ents) - 1, 0)
        lx = max(L, L + (pw - total) / 2.0)
        ly = T + ph + LGD_B_DY
        for txt, key, cls, typ, dash, w in ents:
            if typ == "band":
                A(f'<g class="lgd" data-key="{key}" tabindex="0" role="button">'
                  f'<rect class="sw {cls}" x="{n(lx,2)}" y="{n(ly-10,2)}" width="20" '
                  f'height="12"></rect>'
                  f'<text class="vl lgt" x="{n(lx+LGD_TX,2)}" y="{n(ly,2)}">'
                  f'{esc(txt)}</text></g>')
            else:
                da = ' stroke-dasharray="6 4"' if dash else ""
                A(f'<g class="lgd" data-key="{key}" tabindex="0" role="button">'
                  f'<line class="sw {cls}" x1="{n(lx,2)}" y1="{n(ly-4,2)}" '
                  f'x2="{n(lx+LGD_SW_W,2)}" y2="{n(ly-4,2)}" stroke-width="3"{da}></line>'
                  f'<text class="vl lgt" x="{n(lx+LGD_TX,2)}" y="{n(ly,2)}">'
                  f'{esc(txt)}</text></g>')
            lx += w + LGD_GAP
    else:
        labs = []
        for s in series:
            if s.get("endlab") is False:
                continue
            if s["type"] == "band":
                v = s["hi"][-1]
                txt = s.get("endlab") or s["name"]
            else:
                v = s["vals"][-1]
                txt = s.get("endlab") or s["name"]
            labs.append([ys(v), txt, s["key"], s.get("cls", "c-s1"),
                         s["type"], bool(s.get("dash"))])
        labs.sort(key=lambda r: r[0])
        mines = 27.0
        for i in range(1, len(labs)):
            if labs[i][0] - labs[i - 1][0] < mines:
                labs[i][0] = labs[i - 1][0] + mines
        over = labs[-1][0] - (T + ph) if labs else 0
        if over > 0:
            for r in labs:
                r[0] -= over
        lx = L + pw + 14
        for y, txt, key, cls, typ, dash in labs:
            if typ == "band":
                A(f'<g class="lgd" data-key="{key}" tabindex="0" role="button">'
                  f'<rect class="sw {cls}" x="{n(lx)}" y="{n(y-9,2)}" width="20" '
                  f'height="12"></rect>'
                  f'<text class="vl lgt" x="{n(lx+27)}" y="{n(y+1,2)}">'
                  f'{esc(txt)}</text></g>')
            else:
                da = ' stroke-dasharray="6 4"' if dash else ""
                A(f'<g class="lgd" data-key="{key}" tabindex="0" role="button">'
                  f'<line class="sw {cls}" x1="{n(lx)}" y1="{n(y-3,2)}" '
                  f'x2="{n(lx+20)}" y2="{n(y-3,2)}" stroke-width="3"{da}></line>'
                  f'<text class="vl lgt" x="{n(lx+27)}" y="{n(y+1,2)}">'
                  f'{esc(txt)}</text></g>')

    # 互動層（靜態存在、預設隱藏，JS 只移動）
    A(f'<line class="crosshair" x1="0" y1="{n(T)}" x2="0" '
      f'y2="{n(T+ph)}"></line>')
    for s in series:
        if s["type"] == "band":
            A(f'<circle class="focus {s.get("cls","")}" '
              f'data-key="{s["key"]}" data-role="hi" r="4.2" cx="-99" '
              f'cy="-99"></circle>')
            A(f'<circle class="focus {s.get("cls","")}" '
              f'data-key="{s["key"]}" data-role="lo" r="4.2" cx="-99" '
              f'cy="-99"></circle>')
        else:
            A(f'<circle class="focus {s.get("cls","")}" '
              f'data-key="{s["key"]}" r="4.2" cx="-99" cy="-99"></circle>')
    if xpos is None:
        step = pw / max(nx - 1, 1)
        for i in range(nx):
            A(f'<rect class="hit" data-i="{i}" x="{n(xs(i)-step/2,2)}" '
              f'y="{n(T)}" width="{n(step,2)}" height="{n(ph)}"></rect>')
    else:
        # 非等距 x：命中區以相鄰兩點的中點為界，兩端各外推半個間距
        bounds = [(xs(i - 1) + xs(i)) / 2 for i in range(1, nx)]
        d0 = (xs(1) - xs(0)) / 2 if nx > 1 else pw / 2
        d1 = (xs(nx - 1) - xs(nx - 2)) / 2 if nx > 1 else pw / 2
        bounds = [xs(0) - d0] + bounds + [xs(nx - 1) + d1]
        for i in range(nx):
            A(f'<rect class="hit" data-i="{i}" x="{n(bounds[i],2)}" '
              f'y="{n(T)}" width="{n(bounds[i+1]-bounds[i],2)}" height="{n(ph)}"></rect>')
    A(_hint(L, h - 6, hint or "滑過圖面看該日各序列數值・點右側標註可切換序列"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 瀑布圖
def _wrap2(s):
    """x 軸名稱太長時折成兩行：優先在空格／斜線／括號斷，沒有就從中間切。"""
    s = str(s)
    best = None
    for sep in (" ", "／", "/", "（", "(", "：", ":"):
        i = s.find(sep, 1)
        if 0 < i < len(s) - 1 and (best is None or abs(i - len(s) / 2) < abs(best[0] - len(s) / 2)):
            best = (i, sep)
    if best is None:
        m = (len(s) + 1) // 2
        return s[:m], s[m:]
    i, sep = best
    if sep in ("（", "("):
        return s[:i], s[i:]
    return s[:i].rstrip(), s[i + 1:].lstrip()


def waterfall(items, aria, desc, h=330.0, ylab="", m=(30, 34, 54, 62),
              nd=2, unit="分", hint=None, label_every=1):
    """items: [(name, kind, value, extra_rows)]，kind = 'level' | 'delta' | 'subtotal'。
    y 軸自 0 起不截斷；增／減用一對對立色（紅漲綠跌）＋中性灰水位柱。

    v1.3 擴充（2026-09-14）：段數不限 4（figures.py 限 ≤ 12）。
      subtotal      中繼水位：柱高＝到此為止的累計（value 由 figures 算好傳進來），中性灰，tooltip 標「累計」。
      label_every   2 ＝ 變化柱隔一根標數字（水位／中繼永遠標），段多時避免數字疊字。
      名稱比格寬長 → 折成兩行（下緣多留 16px）；累計掉到 0 以下 → y 軸往下延伸、零線畫在 0。
    這些只在用到時才改變輸出：4 段、無中繼、名稱不超寬、全程 ≥ 0 的舊宣告，輸出逐 byte 不變
    （examples/playtime-demo 整檔 md5 71e83fef… 是這條保證的驗證）。"""
    T, R, B, L = m
    # 計算每根柱的起訖
    bars, cur = [], 0.0
    for name, kind, v, rows in items:
        if kind == "level":
            bars.append((name, kind, 0.0, v, v, rows))
            cur = v
        elif kind == "subtotal":
            bars.append((name, kind, 0.0, cur, cur, rows))
        else:
            bars.append((name, kind, cur, cur + v, v, rows))
            cur += v
    nb = len(bars)
    slot = (VB_W - L - R) / nb
    wrapped = [_wrap2(b[0]) if _tw(b[0], 15) > slot - 8 else None for b in bars]
    if any(wrapped):
        B += 16
    pw, ph = VB_W - L - R, h - T - B
    hi = max(max(b[2], b[3]) for b in bars)
    lo = min(min(b[2], b[3]) for b in bars)
    if lo < 0:
        ticks, lo2, hi2 = nice_ticks(lo * 1.06, hi * 1.06, 5)
    else:
        ticks, lo2, hi2 = nice_ticks(0, hi * 1.06, 5)
    ys = Scale(lo2, hi2, T + ph, T)
    bw = min(slot * .52, 96)
    yz = ys(0) if lo < 0 else T + ph

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y,2)}"></line>')
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" '
          f'text-anchor="end">{esc(fmt(t,0))}</text>')
    if ylab:
        A(f'<text class="lb ax" x="2" y="{n(T-12)}">{esc(ylab)}</text>')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(yz)}" x2="{n(L+pw)}" '
      f'y2="{n(yz)}"></line>')

    prev_x1, prev_end = None, None
    for i, (name, kind, v0, v1, dv, rows) in enumerate(bars):
        cx = L + slot * (i + .5)
        x0 = cx - bw / 2
        ytop, ybot = ys(max(v0, v1)), ys(min(v0, v1))
        cls = ("c-neu" if kind in ("level", "subtotal")
               else ("c-up" if dv > 0 else "c-dn"))
        if prev_x1 is not None and prev_end is not None:
            A(f'<line class="conn" x1="{n(prev_x1,2)}" y1="{n(ys(prev_end),2)}" '
              f'x2="{n(x0,2)}" y2="{n(ys(prev_end),2)}"></line>')
        val = (fmt(dv, nd, sign=True) if kind == "delta" else fmt(v1, nd))
        arrow = "" if kind != "delta" else ("▲ " if dv > 0 else "▼ ")
        if kind == "level":
            tip_rows = [("水位", fmt(v1, nd) + " " + unit)]
        elif kind == "subtotal":
            tip_rows = [("累計", fmt(v1, nd) + " " + unit)]
        else:
            tip_rows = [("變化", arrow + val + " " + unit)]
        tip_rows = tip_rows + list(rows)
        A(f'<g class="mark" data-tip="{tipjson(name, tip_rows)}" '
          f'tabindex="0" role="button" aria-label="{esc(name)} {esc(val)}">'
          f'<rect class="bar {cls}" x="{n(x0,2)}" y="{n(ytop,2)}" '
          f'width="{n(bw,2)}" height="{n(max(ybot-ytop,1.5),2)}"></rect>'
          f'<rect class="hit" x="{n(cx-slot/2,2)}" y="{n(T)}" '
          f'width="{n(slot,2)}" height="{n(ph)}"></rect></g>')
        if kind != "delta" or i % max(int(label_every), 1) == 0:
            lab_cls = "vl" + ("" if kind != "delta" else
                              (" c-up-t" if dv > 0 else " c-dn-t"))
            A(f'<text class="{lab_cls}" x="{n(cx,2)}" y="{n(ytop-11,2)}" '
              f'text-anchor="middle">{esc(arrow + val)}</text>')
        if wrapped[i]:
            l1, l2 = wrapped[i]
            A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+24)}" '
              f'text-anchor="middle">{esc(l1)}</text>')
            A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+41)}" '
              f'text-anchor="middle">{esc(l2)}</text>')
        else:
            A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+24)}" '
              f'text-anchor="middle">{esc(name)}</text>')
        prev_x1, prev_end = x0 + bw, v1
    A(_hint(L, h - 8, hint or "滑過任一柱看數值與占比"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 100% 堆疊
def stacked100(bars, segs, aria, desc, h=250.0, m=(28, 30, 58, 124),
               deltas=None, hint=None, dark=()):
    """bars: [(標籤, [占比...])]（每列加總=1）；segs: [(名稱, cls)]；
    deltas: [(段索引, "▲ +13.0 pp", "up"/"dn")] 標在最後一列下方。"""
    T, R, B, L = m
    pw, ph = VB_W - L - R, h - T - B
    nbar = len(bars)
    bh = min((ph - 26 * (nbar - 1)) / nbar, 54)
    gap = 3.0
    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    seg_centers = []
    for bi, (blab, vs) in enumerate(bars):
        y = T + bi * (bh + 26)
        main, _, sub = blab.partition("\n")
        if sub:
            A(f'<text class="lb bl" x="{n(L-12)}" y="{n(y+bh/2-3,2)}" '
              f'text-anchor="end">{esc(main)}</text>')
            A(f'<text class="an" x="{n(L-12)}" y="{n(y+bh/2+15,2)}" '
              f'text-anchor="end">{esc(sub)}</text>')
        else:
            A(f'<text class="lb bl" x="{n(L-12)}" y="{n(y+bh/2+5,2)}" '
              f'text-anchor="end">{esc(blab)}</text>')
        x = L
        centers = []
        for si, v in enumerate(vs):
            w = pw * v
            name, cls = segs[si]
            ww = max(w - gap, 2)
            A(f'<g class="mark" data-tip="'
              f'{tipjson(name, [(main + " 占比", f"{v*100:.1f}%")])}" '
              f'tabindex="0" role="button" '
              f'aria-label="{esc(blab)} {esc(name)} {v*100:.1f}%">'
              f'<rect class="bar {cls}" x="{n(x,2)}" y="{n(y,2)}" '
              f'width="{n(ww,2)}" height="{n(bh,2)}"></rect></g>')
            tcls = "vl inseg" + (" on-dark" if si in dark else "")
            if w > 92:
                A(f'<text class="{tcls}" x="{n(x+ww/2,2)}" '
                  f'y="{n(y+bh/2+5,2)}" text-anchor="middle">'
                  f'{esc(f"{name} {v*100:.0f}%")}</text>')
            elif w > 46:
                A(f'<text class="{tcls}" x="{n(x+ww/2,2)}" '
                  f'y="{n(y+bh/2+5,2)}" text-anchor="middle">'
                  f'{esc(f"{v*100:.0f}%")}</text>')
            centers.append(x + ww / 2)
            x += w
        seg_centers.append(centers)
    if deltas:
        y = T + (nbar - 1) * (bh + 26) + bh + 20
        for si, txt, tone in deltas:
            cx = seg_centers[-1][si]
            A(f'<text class="vl c-{tone}-t" x="{n(cx,2)}" y="{n(y,2)}" '
              f'text-anchor="middle">{esc(txt)}</text>')
    A(_hint(L, h - 8, hint or "滑過任一色塊看該期占比"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 貢獻排序
def ranked_bars(rows, aria, desc, parts, h=None, m=(30, 290, 40, 150),
                unit="分", hint=None, total=None, total_label=None):
    """rows: [(名稱, 部分1, 部分2, 合計, 占總比, 累積比)]，同方向的量。
    parts: [(部分名, cls), (部分名, cls)]（同色系深淺，不用彩虹）。"""
    T, R, B, L = m
    nb = len(rows)
    rh = 34.0
    h = h or (T + B + nb * rh + 16)
    pw, ph = VB_W - L - R, nb * rh
    vmax = max(abs(r[3]) for r in rows) * 1.02
    xs = Scale(0, vmax, L, L + pw)
    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(T)}" x2="{n(L)}" '
      f'y2="{n(T+ph)}"></line>')
    for i, (name, p1, p2, tot, share, cum) in enumerate(rows):
        y = T + i * rh + 5
        bh = rh - 15
        A(f'<text class="lb bl" x="{n(L-12)}" y="{n(y+bh/2+5,2)}" '
          f'text-anchor="end">{esc(name)}</text>')
        x = L
        for pi, pv in enumerate((p1, p2)):
            w = xs(abs(pv)) - L
            pname, pcls = parts[pi]
            A(f'<g class="mark" data-tip="'
              f'{tipjson(name, [(pname, fmt(pv,2,sign=True)+" "+unit), ("合計貢獻", fmt(tot,2,sign=True)+" "+unit), ("占總變化", f"{share*100:.1f}%")])}" '
              f'tabindex="0" role="button" '
              f'aria-label="{esc(name)} {esc(pname)} {fmt(pv,2,sign=True)}">'
              f'<rect class="bar {pcls}" x="{n(x,2)}" y="{n(y,2)}" '
              f'width="{n(max(w,1.2),2)}" height="{n(bh,2)}"></rect></g>')
            x += w
        A(f'<text class="vl c-dn-t" x="{n(x+10,2)}" y="{n(y+bh/2+5,2)}">'
          f'{esc("▼ " + fmt(tot,2,sign=True))}</text>')
        A(f'<text class="lb sh" x="{n(VB_W-118)}" y="{n(y+bh/2+5,2)}" '
          f'text-anchor="end">{esc(f"{share*100:.1f}%")}</text>')
        A(f'<text class="lb sh cum" x="{n(VB_W-6)}" '
          f'y="{n(y+bh/2+5,2)}" text-anchor="end">'
          f'{esc(f"{cum*100:.1f}%")}</text>')
    A(f'<text class="lb hd" x="{n(VB_W-118)}" y="{n(T-9)}" '
      f'text-anchor="end">占總變化</text>')
    A(f'<text class="lb hd" x="{n(VB_W-6)}" y="{n(T-9)}" '
      f'text-anchor="end">累積</text>')
    # 兩個部分的直接標註（不開圖例框）
    if nb:
        y0 = T - 9
        A(f'<g class="lgd static"><rect class="sw {parts[0][1]}" '
          f'x="{n(L)}" y="{n(y0-10)}" width="18" height="11"></rect>'
          f'<text class="vl lgt" x="{n(L+24)}" y="{n(y0)}">'
          f'{esc(parts[0][0])}</text>'
          f'<rect class="sw {parts[1][1]}" x="{n(L+120)}" y="{n(y0-10)}" '
          f'width="18" height="11"></rect>'
          f'<text class="vl lgt" x="{n(L+144)}" y="{n(y0)}">'
          f'{esc(parts[1][0])}</text></g>')
    if total is not None:
        # v4（skill 版）：加總說明文字可由宣告傳入（total_label）；沒傳就維持原本的字。
        tl = (total_label if total_label is not None
              else f"六格加總 = {fmt(total,2,sign=True)} {unit}（恆等式成立）")
        A(f'<text class="an" x="{n(L)}" y="{n(h-8)}">{esc(tl)}</text>')
    A(_hint(L + 330, h - 8, hint or "滑過任一色塊看該族群的段內／占比拆解"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 直立柱
def vbars(cats, vals, aria, desc, h=250.0, m=(28, 34, 52, 62), unit="分",
          nd=2, cls="c-s2", zero=True, hint=None, tips=None):
    """類別柱狀（含正負）。中性色，不用紅綠——這不是漲跌語意。"""
    T, R, B, L = m
    pw, ph = VB_W - L - R, h - T - B
    lo, hi = min(min(vals), 0), max(max(vals), 0)
    ticks, lo2, hi2 = nice_ticks(lo * 1.25, hi * 1.25, 5)
    ys = Scale(lo2, hi2, T + ph, T)
    slot = pw / len(cats)
    bw = min(slot * .5, 62)
    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y,2)}"></line>')
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" '
          f'text-anchor="end">{esc(fmt(t,nd if abs(t)%1 else 0))}</text>')
    y0 = ys(0)
    if zero:
        A(f'<line class="axis" x1="{n(L)}" y1="{n(y0,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y0,2)}"></line>')
    for i, (c, v) in enumerate(zip(cats, vals)):
        cx = L + slot * (i + .5)
        yv = ys(v)
        top, bot = min(y0, yv), max(y0, yv)
        rows = (tips[i] if tips else [("值", fmt(v, nd, sign=True) + " " + unit)])
        A(f'<g class="mark" data-tip="{tipjson(c, rows)}" tabindex="0" '
          f'role="button" aria-label="{esc(c)} {esc(fmt(v,nd,sign=True))}">'
          f'<rect class="bar {cls}" x="{n(cx-bw/2,2)}" y="{n(top,2)}" '
          f'width="{n(bw,2)}" height="{n(max(bot-top,1.2),2)}"></rect>'
          f'<rect class="hit" x="{n(cx-slot/2,2)}" y="{n(T)}" '
          f'width="{n(slot,2)}" height="{n(ph)}"></rect></g>')
        ty = (top - 9) if v >= 0 else (bot + 19)
        A(f'<text class="vl" x="{n(cx,2)}" y="{n(ty,2)}" '
          f'text-anchor="middle">{esc(fmt(v,nd,sign=True))}</text>')
        A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+24)}" '
          f'text-anchor="middle">{esc(c)}</text>')
    A(_hint(L, h - 8, hint or "滑過任一柱看數值"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 文字寬度粗估（v1.1）
def _tw(s, px=15.0):
    """沒有字型量測，用 em 粗估：CJK 全形算 1 em、其餘算 0.56 em。只拿來排圖例。"""
    return sum((1.0 if ord(c) > 0x2E80 else 0.56) for c in str(s)) * px


# ---------------------------------------------------------------- 分群長條（v1.1）
def grouped_bars(cats, series, aria, desc, h=300.0, m=(46, 34, 52, 62), unit="",
                 nd=1, zero=True, deltas=None, value_labels="auto", hint=None,
                 ylab="", ymin=None, ymax=None, delta_label="變化"):
    """類別 × 序列並排直立柱（例 底台 × pre/post、族群 × 指標）。v1.1 新增。

    series: [{"key":..,"name":..,"cls":"c-s1","vals":[..]}]（2～3 條，中性藍 s1～s3）
    deltas: 每個類別一個 (文字, tone) 或 None，標在該組柱頂上方；tone 是 up／dn／ink
            （紅漲綠跌 ＋ ▲▼ ＋ 正負號，顏色不是唯一線索）
    互動掛勾：每根柱 g.mark[data-tip]（tooltip 列出該類別所有序列 ＋ 變化）；
              每條序列包在 g.ser[data-key] 裡，上方 g.lgd[data-key] 圖例點了切換整條
              （沿用 .ser.off 的 CSS：關掉＝透明、列印強制顯示；y 軸尺度固定不重算）。
    """
    T, R, B, L = m
    pw, ph = VB_W - L - R, h - T - B
    nc, ns = len(cats), len(series)
    slot = pw / nc
    gap = 4.0
    bw = min((slot * .74 - gap * (ns - 1)) / ns, 64.0)
    gw = bw * ns + gap * (ns - 1)
    show_vals = (value_labels is True) or (value_labels == "auto" and bw >= 34 and nc * ns <= 18)
    vcls = "vl" if bw >= 46 else "inseg"

    allv = [v for s in series for v in s["vals"]]
    lo, hi = min(min(allv), 0.0), max(max(allv), 0.0)
    span = (hi - lo) or 1.0
    head = 8 + (18 if show_vals else 0) + (20 if deltas else 0)      # 柱頂上方要留的像素
    hi_ext = hi + span * head / max(ph - head, 1) if (hi > 0 and ymax is None) else hi
    lo_ext = lo - span * 18 / max(ph - 18, 1) if (lo < 0 and ymin is None) else lo
    if ymin is not None:
        lo_ext = ymin
    if ymax is not None:
        hi_ext = ymax
    ticks, lo2, hi2 = nice_ticks(lo_ext, hi_ext, 5)
    ys = Scale(lo2, hi2, T + ph, T)

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y,2)}"></line>')
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" '
          f'text-anchor="end">{esc(fmt(t,nd if abs(t)%1 else 0))}</text>')
    if ylab:
        A(f'<text class="lb ax" x="2" y="{n(T-16)}">{esc(ylab)}</text>')
    y0 = ys(0)
    if zero:
        A(f'<line class="axis" x1="{n(L)}" y1="{n(y0,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y0,2)}"></line>')

    # 圖例（右上，可點切換；同一列右對齊）
    widths = [18 + 7 + _tw(s["name"], 16) + 22 for s in series]
    lx = L + pw - (sum(widths) - 22)
    ly = T - 16
    for s, w in zip(series, widths):
        A(f'<g class="lgd" data-key="{esc(s["key"])}" tabindex="0" role="button">'
          f'<rect class="sw {s["cls"]}" x="{n(lx,2)}" y="{n(ly-11)}" width="18" height="12"></rect>'
          f'<text class="vl lgt" x="{n(lx+25,2)}" y="{n(ly)}">{esc(s["name"])}</text></g>')
        lx += w

    ustr = (" " + unit) if unit else ""
    for si, s in enumerate(series):
        A(f'<g class="ser" data-key="{esc(s["key"])}">')
        for ci, (c, v) in enumerate(zip(cats, s["vals"])):
            cx = L + slot * (ci + .5)
            x0 = cx - gw / 2 + si * (bw + gap)
            yv = ys(v)
            top, bot = min(y0, yv), max(y0, yv)
            rows = [(t["name"], fmt(t["vals"][ci], nd) + ustr) for t in series]
            if deltas and deltas[ci]:
                rows.append((delta_label, deltas[ci][0]))
            A(f'<g class="mark" data-tip="{tipjson(c, rows)}" tabindex="0" role="button" '
              f'aria-label="{esc(c)} {esc(s["name"])} {esc(fmt(v,nd))}{esc(ustr)}">'
              f'<rect class="bar {s["cls"]}" x="{n(x0,2)}" y="{n(top,2)}" '
              f'width="{n(bw,2)}" height="{n(max(bot-top,1.2),2)}"></rect>'
              f'<rect class="hit" x="{n(x0,2)}" y="{n(T)}" width="{n(bw,2)}" '
              f'height="{n(ph)}"></rect></g>')
            if show_vals:
                ty = (top - 7) if v >= 0 else (bot + 17)
                A(f'<text class="{vcls}" x="{n(x0+bw/2,2)}" y="{n(ty,2)}" '
                  f'text-anchor="middle">{esc(fmt(v,nd))}</text>')
        A("</g>")

    # 每組的 ▲▼ 變化標記（在該組最高柱上方；不屬於任何序列，切換序列時仍在）
    if deltas:
        for ci, d in enumerate(deltas):
            if not d:
                continue
            text, tone = d
            cx = L + slot * (ci + .5)
            ytop = min(ys(max(s["vals"][ci], 0.0)) for s in series)
            y = max(ytop - (27 if show_vals else 9), T + 12)
            tcls = "vl" + (" c-up-t" if tone == "up" else (" c-dn-t" if tone == "dn" else ""))
            A(f'<text class="{tcls}" x="{n(cx,2)}" y="{n(y,2)}" '
              f'text-anchor="middle">{esc(text)}</text>')

    for ci, c in enumerate(cats):
        cx = L + slot * (ci + .5)
        A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+24)}" '
          f'text-anchor="middle">{esc(c)}</text>')
    A(_hint(L, h - 8, hint or "滑過任一柱看該類別各序列數值・點上方圖例可切換序列"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 漏斗（v1.1）
def funnel(steps, aria, desc, h=None, m=(44, 0, 44, 150), unit="人", nd=0,
           show=("count", "pct_first", "pct_prev"), emph=None, hint=None,
           cls="c-s1", total_label=None, emph_text="最大流失"):
    """步驟由上而下的水平長條，左對齊、長度＝占第一步比例。v1.1 新增。

    steps: [(名稱, 人數, 占第一步%, 占上一步%)]（% 為 0～100；第一步的占上一步 ＝ 100）
    show:  要顯示哪些數字：count（人數，接在條末）／pct_first／pct_prev（右側兩欄）
    emph:  要強調的步驟索引（0 起；通常是流失最大那一步）或 None。強調只用位置與字級：
           整列鋪中性淡底（沿用 .bkband）、步驟名改粗體大字、數字下加「最大流失」小字；
           條的顏色不變（單色 s1，不用紅綠）。
    互動掛勾：每一步 g.mark[data-tip]（觸控 tap 等同 hover）。
    """
    T, _r, B, L = m
    show = tuple(show)
    pct_cols = [c for c in ("pct_first", "pct_prev") if c in show]
    colw = 118.0
    R = 24.0 + colw * len(pct_cols)
    pw = VB_W - L - R
    nb = len(steps)
    rh = 46.0
    ph = nb * rh
    h = h or (T + B + ph)
    maxw = pw - (110.0 if "count" in show else 12.0)
    first = steps[0][1] or 1.0
    ustr = (" " + unit) if unit else ""

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    heads = {"pct_first": "占第一步", "pct_prev": "占上一步"}
    colx = {}
    for j, c in enumerate(pct_cols):
        x = VB_W - 6 - colw * (len(pct_cols) - 1 - j)
        colx[c] = x
        A(f'<text class="lb hd" x="{n(x)}" y="{n(T-9)}" text-anchor="end">{heads[c]}</text>')
    if "count" in show:
        A(f'<text class="lb hd" x="{n(L)}" y="{n(T-9)}">人數{("（" + unit + "）") if unit else ""}</text>')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(T)}" x2="{n(L)}" y2="{n(T+ph)}"></line>')

    for i, (name, cnt, pf, pp) in enumerate(steps):
        y = T + i * rh
        bh = rh - 16
        by = y + 8
        is_e = (emph is not None and i == emph)
        if is_e:
            A(f'<rect class="bkband" x="6" y="{n(y,2)}" width="{n(VB_W-12)}" height="{n(rh)}"></rect>')
        lab_cls = "vl" if is_e else "lb bl"
        A(f'<text class="{lab_cls}" x="{n(L-12)}" y="{n(by+bh/2+5,2)}" '
          f'text-anchor="end">{esc(name)}</text>')
        w = max(maxw * (cnt / first), 1.5)
        rows = []
        if "count" in show:
            rows.append(("人數", fmt(cnt, nd) + ustr))
        if "pct_first" in show:
            rows.append(("占第一步", f"{pf:.1f}%"))
        if "pct_prev" in show and i > 0:
            rows.append(("占上一步", f"{pp:.1f}%"))
            loss = pp - 100.0
            rows.append(("流失（vs 上一步）",
                         f"▼ {loss:+.1f}%" if loss < 0 else (f"▲ {loss:+.1f}%" if loss > 0 else "– 0.0%")))
        A(f'<g class="mark" data-tip="{tipjson(f"步驟 {i+1}：{name}", rows)}" tabindex="0" '
          f'role="button" aria-label="{esc(name)} {esc(fmt(cnt,nd))}{esc(ustr)} 占第一步 {pf:.1f}%">'
          f'<rect class="bar {cls}" x="{n(L)}" y="{n(by,2)}" width="{n(w,2)}" '
          f'height="{n(bh,2)}"></rect>'
          f'<rect class="hit" x="{n(L)}" y="{n(y,2)}" width="{n(pw)}" height="{n(rh)}"></rect></g>')
        if "count" in show:
            A(f'<text class="vl" x="{n(L+w+10,2)}" y="{n(by+bh/2+5,2)}">'
              f'{esc(fmt(cnt,nd) + ustr)}</text>')
        if "pct_first" in show:
            A(f'<text class="lb sh" x="{n(colx["pct_first"])}" y="{n(by+bh/2+5,2)}" '
              f'text-anchor="end">{pf:.1f}%</text>')
        if "pct_prev" in show and i > 0:
            A(f'<text class="lb sh cum" x="{n(colx["pct_prev"])}" y="{n(by+bh/2+5,2)}" '
              f'text-anchor="end">{pp:.1f}%</text>')
        if is_e:
            if pct_cols:
                ex, anchor = colx.get("pct_prev") or colx["pct_first"], "end"
            else:
                ex, anchor = L + w + 10, "start"
            A(f'<text class="an" x="{n(ex,2)}" y="{n(y+rh-2,2)}" text-anchor="{anchor}">'
              f'{esc(emph_text)}</text>')

    if total_label is not False:
        tl = total_label or (f"整體轉換 {steps[-1][2]:.1f}%（{steps[0][0]} → {steps[-1][0]}，{nb} 步）")
        A(f'<text class="an" x="{n(L)}" y="{n(h-8)}">{esc(tl)}</text>')
    A(_hint(L + 440, h - 8, hint or "滑過任一步看人數與轉換率"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 底色亮度 → 字色（v1.2）
# 只拿來決定「這格／這段要用墨色字還是白字」。數值鏡射 themes.py 風格 B 的色票
# （--cat1／--cat2／--cat3／中性灰），SVG 標記本身仍然只寫 class、不寫色碼。
FILL_HEX = {"c-s1": "#2f6f9f", "c-s2": "#7ba7c4", "c-s3": "#c2d3dd", "c-neu": "#bab8b3",
            "c-up": "#c62828", "c-dn": "#2e7d32", "c-dn2": "#8ebd92", "c-band": "#c8dbe9"}


def _lum(hex6, alpha=1.0):
    """相對亮度（WCAG）。alpha < 1 視為疊在白底上（fill-opacity 的視覺結果）。"""
    h = hex6.lstrip("#")
    out = 0.0
    for i, w in ((0, .2126), (2, .7152), (4, .0722)):
        c = int(h[i:i + 2], 16) / 255.0
        c = c * alpha + (1.0 - alpha)
        c = c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        out += w * c
    return out


DARK_LUM = 0.22      # 底色相對亮度低於這個門檻就改用白字（--cat1 全色 0.145、七成 0.30；WCAG 白字對比 ≥ 3.9）


def on_dark(cls, alpha=None):
    """這個底色（class ＋ fill-opacity 疊白底）夠深、要改用白字嗎？拿不到色票就當淺色底。"""
    hex6 = FILL_HEX.get(cls)
    if not hex6:
        return False
    return _lum(hex6, 1.0 if alpha is None else float(alpha)) < DARK_LUM


def _fo(alpha):
    return "" if alpha is None or float(alpha) >= 1.0 else f' fill-opacity="{n(alpha, 3)}"'


# ---------------------------------------------------------------- 堆疊長條（絕對值；v1.2）
def stacked_bars(cats, segs, aria, desc, h=300.0, m=(46, 34, 52, 62), unit="", nd=1,
                 ylab="", ymin=0.0, ymax=None, total_labels="auto", seg_labels="auto",
                 delta=None, hint=None):
    """類別 × 2～5 段疊加的直立柱（絕對值；跟 stacked100 的占比組成不同）。v1.2 新增。

    segs:  [{"key":..,"name":..,"cls":"c-s1","fo":None|0.62,"vals":[..]}]，**第一段在底**，
           fo 是 fill-opacity（s4／s5 是 c-s3 的淡階，CSS 不加新 class）。值一律 ≥ 0（figures 先驗）。
    delta: None 或 dict(a=類別索引, b=類別索引, text="▲ +12.3%", tone="up"/"dn"/"ink", label="變化")：
           把兩個類別「合計」的變化標在 b 那根柱頂上方（紅漲綠跌 ＋ ▲▼ ＋ 正負號）。
    互動掛勾：每一段 g.mark[data-tip]（tooltip 列出該類別全部段 ＋ 合計）；每個類別另有一個只含
           rect.hit 的 g.mark，滑到柱子上方的空白也看得到同一份 tooltip；每段包在 g.ser[data-key]，
           上方 g.lgd[data-key] 圖例沿用 v1.1 第 9 段 JS 切換 .off——**關掉的段只是隱藏，其餘段位置
           不重排、y 軸不重算**（設計決定 13：切換序列不改尺度）。合計標籤不屬於任何段，切換時仍在。
    """
    T, R, B, L = m
    pw, ph = VB_W - L - R, h - T - B
    nc, ns = len(cats), len(segs)
    slot = pw / nc
    bw = min(slot * .62, 88.0)
    totals = [sum(s["vals"][i] for s in segs) for i in range(nc)]
    show_tot = (total_labels is True) or (total_labels == "auto" and slot >= 40 and nc <= 24)
    show_seg = (seg_labels is True) or (seg_labels == "auto" and bw >= 44)
    head = 8 + (20 if show_tot else 0) + (20 if delta else 0)
    hi = max(max(totals), 0.0)
    lo = 0.0 if ymin is None else min(float(ymin), 0.0)
    span = (hi - lo) or 1.0
    hi_ext = hi + span * head / max(ph - head, 1) if ymax is None else ymax
    ticks, lo2, hi2 = nice_ticks(lo, hi_ext, 5)
    ys = Scale(lo2, hi2, T + ph, T)
    ustr = (" " + unit) if unit else ""

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" x2="{n(L+pw)}" '
          f'y2="{n(y,2)}"></line>')
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" '
          f'text-anchor="end">{esc(fmt(t,nd if abs(t)%1 else 0))}</text>')
    if ylab:
        A(f'<text class="lb ax" x="2" y="{n(T-16)}">{esc(ylab)}</text>')
    y0 = ys(0)
    A(f'<line class="axis" x1="{n(L)}" y1="{n(y0,2)}" x2="{n(L+pw)}" y2="{n(y0,2)}"></line>')

    # 圖例（右上，可點切換；宣告順序＝堆疊順序，由左到右＝由底到頂）
    widths = [18 + 7 + _tw(s["name"], 16) + 22 for s in segs]
    lx = L + pw - (sum(widths) - 22)
    ly = T - 16
    for s, w in zip(segs, widths):
        A(f'<g class="lgd" data-key="{esc(s["key"])}" tabindex="0" role="button">'
          f'<rect class="sw {s["cls"]}"{_fo(s.get("fo"))} x="{n(lx,2)}" y="{n(ly-11)}" width="18" height="12"></rect>'
          f'<text class="vl lgt" x="{n(lx+25,2)}" y="{n(ly)}">{esc(s["name"])}</text></g>')
        lx += w

    # 每個類別的 tooltip 內容（全部段 ＋ 合計；delta 的 b 類別多一列）
    tips = []
    for ci, c in enumerate(cats):
        rows = [(s["name"], fmt(s["vals"][ci], nd) + ustr) for s in segs]
        rows.append(("合計", fmt(totals[ci], nd) + ustr))
        if delta and ci == delta["b"]:
            rows.append((f'{delta.get("label", "變化")}（vs {cats[delta["a"]]}）', delta["text"]))
        tips.append(tipjson(c, rows))

    # 整欄命中區（畫在段的下面：滑到柱子上方空白也有 tooltip；不可聚焦，免得讀屏重複）
    for ci, c in enumerate(cats):
        cx = L + slot * (ci + .5)
        A(f'<g class="mark" data-tip="{tips[ci]}">'
          f'<rect class="hit" x="{n(cx-slot/2,2)}" y="{n(T)}" width="{n(slot,2)}" height="{n(ph)}"></rect></g>')

    # 段（第一段在底）
    cum = [0.0] * nc
    for s in segs:
        A(f'<g class="ser" data-key="{esc(s["key"])}">')
        dark = on_dark(s["cls"], s.get("fo"))
        for ci, (c, v) in enumerate(zip(cats, s["vals"])):
            if v <= 0:
                continue
            cx = L + slot * (ci + .5)
            x0 = cx - bw / 2
            ybot, ytop = ys(cum[ci]), ys(cum[ci] + v)
            hh = max(ybot - ytop, 1.2)
            A(f'<g class="mark" data-tip="{tips[ci]}" tabindex="0" role="button" '
              f'aria-label="{esc(c)} {esc(s["name"])} {esc(fmt(v,nd))}{esc(ustr)}">'
              f'<rect class="bar {s["cls"]}"{_fo(s.get("fo"))} x="{n(x0,2)}" y="{n(ytop,2)}" '
              f'width="{n(bw,2)}" height="{n(hh,2)}"></rect></g>')
            if show_seg and hh >= 20:
                tcls = "inseg" + (" on-dark" if dark else "")
                A(f'<text class="{tcls}" x="{n(cx,2)}" y="{n(ytop+hh/2+5,2)}" '
                  f'text-anchor="middle">{esc(fmt(v,nd))}</text>')
            cum[ci] += v
        A("</g>")

    # 柱頂合計（不屬於任何段）＋ 兩類別合計的 ▲▼ 變化
    for ci, c in enumerate(cats):
        cx = L + slot * (ci + .5)
        ytop = ys(max(totals[ci], 0.0))
        if show_tot:
            A(f'<text class="vl" x="{n(cx,2)}" y="{n(ytop-7,2)}" '
              f'text-anchor="middle">{esc(fmt(totals[ci],nd))}</text>')
        if delta and ci == delta["b"]:
            y = max(ytop - (27 if show_tot else 9), T + 12)
            tone = delta.get("tone", "ink")
            tcls = "vl" + (" c-up-t" if tone == "up" else (" c-dn-t" if tone == "dn" else ""))
            A(f'<text class="{tcls}" x="{n(cx,2)}" y="{n(y,2)}" '
              f'text-anchor="middle">{esc(delta["text"])}</text>')
        A(f'<text class="lb xl" x="{n(cx,2)}" y="{n(T+ph+24)}" '
          f'text-anchor="middle">{esc(c)}</text>')
    A(_hint(L, h - 8, hint or "滑過任一柱看該類別各段與合計・點上方圖例可隱藏／顯示該段（其餘段位置不變）"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- cohort 留存熱圖（v1.2）／星期×小時熱圖（v1.3 共用）
def heatmap(cohorts, days, grid, aria, desc, h=None, sizes=None, unit="%", nd=1,
            value_labels="auto", highlight=None, hint=None, cls="c-s1",
            legend_title="留存率", m=(44, 24, 30, 12), row_h=36.0,
            col_labels=None, col_key="day", col_tips=None,
            missing_note="空白＝尚未觀察到（不是 0）", emph=None, emph_note=None,
            fit_labels=False, col_suffix=None):
    """cohort（列）× 天數位移（欄）的留存率格子。v1.2 新增，data-kind="heat"。

    grid:   list[list[float|None]]，值為 0～100 的 %；None ＝ 尚未觀察到（空白格，不畫）。
    sizes:  每個 cohort 的人數（顯示在標籤旁 n=…）或 None。
    色階：  單一色相（--cat1）的亮度階，用 fill-opacity 從 0.08（最小值）到 1.0（最大值）——
            色盲安全、不用紅綠、不加任何 CSS class；格內數字依底色亮度自動選墨色／白字。
            圖下方有色階條標 min／max。
    value_labels: auto（格寬 ≥58 印「42.0%」、36～58 印整數「42」、更窄不印）／True／False。
    互動掛勾：每格 g.mark[data-tip]（cohort／day／留存率／n；tap 等同 hover）；沒有序列切換。
    列印：數字是靜態 <text>，全部可見。

    v1.3 通用化（星期×小時熱圖 dow_hour 共用同一個畫法；下面的參數不給就是 v1.2 行為，cohort 輸出逐 byte 不變）：
      col_labels   欄標題文字（預設 D{d}）；col_key／col_tips  tooltip 那一列的鍵與值（預設 "day"／D{d}）
      missing_note 有空白格時圖下方的註記；emph=(列, 欄) 在該格外加墨色粗框（最大格），emph_note 寫在色階條下一行
      fit_labels   True ＝ 格內數字估寬放不下就不印（欄很多時只留 tooltip）；col_suffix  欄標題列尾端的單位字（例「時」）
    """
    T, R, B, LP = m
    nr, ncol = len(cohorts), len(days)
    lw = max(_tw(c, 15) for c in cohorts) + 18
    size_txt = [("n=" + fmt(s, 0)) if s is not None else "" for s in sizes] if sizes else None
    sw = (max(_tw(t, 13) for t in size_txt) + 16) if size_txt else 0.0
    L = LP + lw + sw
    pw = VB_W - L - R
    gap = 2.0
    cw = pw / ncol
    leg_h = 44.0
    h = h or (T + nr * row_h + leg_h + B)
    ph = nr * row_h
    vals = [v for row in grid for v in row if v is not None]
    vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 100.0)
    amin, amax = 0.08, 1.0
    if col_labels is None:
        col_labels = [f"D{d}" for d in days]
    if col_tips is None:
        col_tips = [f"D{d}" for d in days]

    def alpha(v):
        if vmax <= vmin:
            return 0.6
        return amin + (amax - amin) * (v - vmin) / (vmax - vmin)

    if value_labels is True:
        mode = "full"
    elif value_labels is False:
        mode = "none"
    else:
        mode = "full" if cw >= 58 else ("int" if cw >= 36 else "none")

    o = [_svg_open(h, "heat", aria, desc)]
    A = o.append
    A('<g class="plot">')
    # 欄標題（天數位移）；highlight 那欄加粗
    for ci, d in enumerate(days):
        cx = L + cw * (ci + .5)
        hcls = "lb hd cum" if (highlight is not None and ci == highlight) else "lb hd"
        A(f'<text class="{hcls}" x="{n(cx,2)}" y="{n(T-10)}" text-anchor="middle">{esc(col_labels[ci])}</text>')
    if col_suffix:
        A(f'<text class="lb hd" x="{n(L+pw+4,2)}" y="{n(T-10)}">{esc(col_suffix)}</text>')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(T-3)}" x2="{n(L+pw)}" y2="{n(T-3)}"></line>')
    missing = False
    emph_box = None
    for ri, c in enumerate(cohorts):
        y = T + ri * row_h
        ty = y + row_h / 2 + 5
        A(f'<text class="lb bl" x="{n(LP+lw-10,2)}" y="{n(ty,2)}" text-anchor="end">{esc(c)}</text>')
        if size_txt and size_txt[ri]:
            A(f'<text class="an" x="{n(L-8,2)}" y="{n(ty,2)}" text-anchor="end">{esc(size_txt[ri])}</text>')
        for ci, d in enumerate(days):
            v = grid[ri][ci]
            if v is None:
                missing = True
                continue
            x = L + cw * ci + gap / 2
            a = alpha(v)
            shown = fmt(v, nd) + unit
            rows = [(col_key, col_tips[ci]), (legend_title, shown)]
            if sizes and sizes[ri] is not None:
                rows.append(("n", fmt(sizes[ri], 0)))
            if emph is not None and (ri, ci) == tuple(emph):
                rows.append(("", "最大格"))
                emph_box = (x, y + gap / 2, cw - gap, row_h - gap)
            A(f'<g class="mark" data-tip="{tipjson(c, rows)}" tabindex="0" role="button" '
              f'aria-label="{esc(c)} {esc(col_tips[ci])} {esc(shown)}">'
              f'<rect class="bar {cls}"{_fo(a)} x="{n(x,2)}" y="{n(y+gap/2,2)}" '
              f'width="{n(cw-gap,2)}" height="{n(row_h-gap,2)}"></rect></g>')
            if mode != "none":
                txt = shown if mode == "full" else fmt(v, 0)
                if fit_labels and _tw(txt, 14.5) > cw - gap - 4:
                    continue
                tcls = "inseg" + (" on-dark" if on_dark(cls, a) else "")
                A(f'<text class="{tcls}" x="{n(x+(cw-gap)/2,2)}" y="{n(ty,2)}" '
                  f'text-anchor="middle">{esc(txt)}</text>')
    if emph_box:
        # 最大格：墨色實線粗框（.ser 給 fill:none、.c-ink 給墨色 stroke；不加 CSS），畫在所有格子之上
        ex, ey, ew, eh = emph_box
        A(f'<rect class="ser c-ink" stroke-width="2.4" x="{n(ex+1,2)}" y="{n(ey+1,2)}" '
          f'width="{n(ew-2,2)}" height="{n(eh-2,2)}"></rect>')
    # 色階條（圖下方左側）：min → max
    ly = T + ph + 16
    A(f'<text class="an" x="{n(L)}" y="{n(ly+11)}">{esc(legend_title)}　{esc(fmt(vmin, nd) + unit)}</text>')
    sx = L + _tw(legend_title, 13) + _tw(fmt(vmin, nd) + unit, 13) + 22
    steps = 12
    for k in range(steps):
        a = amin + (amax - amin) * k / (steps - 1)
        A(f'<rect class="sw {cls}"{_fo(a)} x="{n(sx + k*20,2)}" y="{n(ly)}" width="20" height="14"></rect>')
    A(f'<text class="an" x="{n(sx + steps*20 + 8,2)}" y="{n(ly+11)}">{esc(fmt(vmax, nd) + unit)}</text>')
    if missing:
        A(f'<text class="an" x="{n(VB_W-R)}" y="{n(ly+11)}" text-anchor="end">{esc(missing_note)}</text>')
    if emph_box and emph_note:
        A(f'<text class="an" x="{n(VB_W-R)}" y="{n(ly+30)}" text-anchor="end">{esc(emph_note)}</text>')
    A(_hint(L, h - 8, hint or "滑過任一格看 cohort、天數、留存率與 n"))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- 直方圖＋分位線（v1.3）
def histogram(edges, groups, aria, desc, h=340.0, m=(46, 34, 52, 62), unit="", nd=1,
              ylab="人數", yscale="count", qlines=(), xlab="", hint=None, notes=()):
    """直方圖（v1.3 新增，data-kind="bar"）。x 是數值軸（允許負值），y 從 0 起。

    edges:  箱界 [e0, e1, …, eK]，遞增，共 K 箱（figures.py 已驗）。
    groups: [{"key":..,"name":..,"cls":"c-s1","fo":None|0.45,"counts":[K 個 ≥ 0],"n": 總數}]，1～2 組。
            2 組時半透明疊圖（fill-opacity），每組再描一條同色階梯外框（polyline.ser）讓兩個輪廓在重疊處仍分得開；
            上方 g.lgd[data-key] 圖例沿用 v1.1 第 9 段 JS 切換（bars 與外框、該組的分位線都掛同一個 data-key）。
    yscale: "count"（人數）或 "share"（各組佔比 %，每組各除以自己的 n；兩組人數差很多時用這個比形狀）。
    qlines: [(x, 文字, cls|None, key|None, dashed)] 垂直參考線：分位數＝虛線（.ref，預設墨色）、mean＝實線；
            cls 給組的顏色 class 時線跟組同色；key 有值時放進該組的 g.ser（跟著圖例切換）。
            標籤在圖頂，估寬會撞就往下錯一行（最多三行）。
    notes:  圖下方提示列末尾的補充（例：已分箱資料的分位是箱內線性插補）。
    互動掛勾：每箱一個整欄 rect.hit 的 g.mark（滑到柱子上方也有 tooltip）＋ 每根柱的 g.mark；tooltip 列出各組人數與佔比。
    """
    T, R, B, L = m
    pw, ph = VB_W - L - R, h - T - B
    K = len(edges) - 1
    ng = len(groups)
    xs = Scale(edges[0], edges[-1], L, L + pw)
    series = []
    for g in groups:
        tot = float(g.get("n") or sum(g["counts"])) or 1.0
        vals = [c / tot * 100.0 for c in g["counts"]] if yscale == "share" else list(g["counts"])
        series.append(vals)
    hi = max(max(v) for v in series) if series else 1.0
    if hi <= 0:
        hi = 1.0
    head = 34 if qlines else 12                       # 圖頂要留給分位線標籤的空間
    hi_ext = hi + hi * head / max(ph - head, 1)
    ticks, lo2, hi2 = nice_ticks(0, hi_ext, 5)
    ys = Scale(lo2, hi2, T + ph, T)
    y0 = ys(0)
    gap = 3.0 if K <= 12 else 1.0
    ustr = (" " + unit) if unit else ""

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    for t in ticks:
        y = ys(t)
        A(f'<line class="grid" x1="{n(L)}" y1="{n(y,2)}" x2="{n(L+pw)}" y2="{n(y,2)}"></line>')
        lab = fmt(t, 0 if float(t).is_integer() else 1) + ("%" if yscale == "share" else "")
        A(f'<text class="lb yl" x="{n(L-10)}" y="{n(y+5,2)}" text-anchor="end">{esc(lab)}</text>')
    if ylab:
        A(f'<text class="lb ax" x="2" y="{n(T-16)}">{esc(ylab)}</text>')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(y0,2)}" x2="{n(L+pw)}" y2="{n(y0,2)}"></line>')
    # x 軸刻度（數值軸，好看的刻度、只留在範圍內）
    xt, _, _ = nice_ticks(edges[0], edges[-1], 8)
    xt = [t for t in xt if edges[0] - 1e-9 <= t <= edges[-1] + 1e-9]
    for t in xt:
        x = xs(t)
        A(f'<line class="axis" x1="{n(x,2)}" y1="{n(y0,2)}" x2="{n(x,2)}" y2="{n(y0+5,2)}"></line>')
        A(f'<text class="lb xl" x="{n(x,2)}" y="{n(y0+22,2)}" text-anchor="middle">'
          f'{esc(fmt(t, 0 if float(t).is_integer() else nd))}</text>')
    if xlab:
        A(f'<text class="lb ax" x="{n(L+pw)}" y="{n(h-10)}" text-anchor="end">{esc(xlab)}</text>')

    # 圖例（2 組才有；右上、可點切換）／單組只標 n
    if ng > 1:
        names = [f'{g["name"]}（n={fmt(g.get("n") or sum(g["counts"]), 0)}）' for g in groups]
        widths = [18 + 7 + _tw(nm, 16) + 22 for nm in names]
        lx = L + pw - (sum(widths) - 22)
        ly = T - 16
        for g, nm, w in zip(groups, names, widths):
            A(f'<g class="lgd" data-key="{esc(g["key"])}" tabindex="0" role="button">'
              f'<rect class="sw {g["cls"]}"{_fo(g.get("fo"))} x="{n(lx,2)}" y="{n(ly-11)}" width="18" height="12"></rect>'
              f'<text class="vl lgt" x="{n(lx+25,2)}" y="{n(ly)}">{esc(nm)}</text></g>')
            lx += w
    else:
        g = groups[0]
        A(f'<text class="an" x="{n(L+pw)}" y="{n(T-14)}" text-anchor="end">'
          f'{esc("n = " + fmt(g.get("n") or sum(g["counts"]), 0))}</text>')

    # 每箱的 tooltip（各組人數＋佔比）
    tips = []
    for i in range(K):
        title = f"{fmt(edges[i], nd)}～{fmt(edges[i+1], nd)}{ustr}"
        rows = []
        for g in groups:
            tot = float(g.get("n") or sum(g["counts"])) or 1.0
            pre = (g["name"] + " ") if ng > 1 else ""
            rows.append((pre + "人數", fmt(g["counts"][i], 0)))
            rows.append((pre + "佔比", f"{g['counts'][i] / tot * 100:.1f}%"))
        tips.append(tipjson(title, rows))
    # 整欄命中區（畫在柱子下面）
    for i in range(K):
        xa, xb = xs(edges[i]), xs(edges[i + 1])
        A(f'<g class="mark" data-tip="{tips[i]}">'
          f'<rect class="hit" x="{n(xa,2)}" y="{n(T)}" width="{n(xb-xa,2)}" height="{n(ph)}"></rect></g>')
    # 柱（每組一個 g.ser；2 組疊畫）
    for g, vals in zip(groups, series):
        A(f'<g class="ser" data-key="{esc(g["key"])}">')
        for i, v in enumerate(vals):
            if v <= 0:
                continue
            xa, xb = xs(edges[i]), xs(edges[i + 1])
            x0, w = xa + gap / 2, max(xb - xa - gap, 1.0)
            yv = ys(v)
            A(f'<g class="mark" data-tip="{tips[i]}" tabindex="0" role="button" '
              f'aria-label="{esc(g["name"])} {esc(fmt(edges[i], nd))}～{esc(fmt(edges[i+1], nd))}{esc(ustr)} {esc(fmt(g["counts"][i], 0))}">'
              f'<rect class="bar {g["cls"]}"{_fo(g.get("fo"))} x="{n(x0,2)}" y="{n(yv,2)}" '
              f'width="{n(w,2)}" height="{n(max(y0-yv,1.2),2)}"></rect></g>')
        A("</g>")
    # 2 組：每組再描一條階梯外框（畫在全部柱子之上，重疊處靠外框分辨）
    if ng > 1:
        for g, vals in zip(groups, series):
            pts = [f"{n(xs(edges[0]),2)},{n(y0,2)}"]
            for i, v in enumerate(vals):
                yv = ys(max(v, 0.0))
                pts.append(f"{n(xs(edges[i]),2)},{n(yv,2)}")
                pts.append(f"{n(xs(edges[i+1]),2)},{n(yv,2)}")
            pts.append(f"{n(xs(edges[-1]),2)},{n(y0,2)}")
            A(f'<g class="ser" data-key="{esc(g["key"])}">'
              f'<polyline class="ser {g["cls"]}" stroke-width="1.8" points="{" ".join(pts)}"></polyline></g>')

    # 分位線／mean：垂直線 ＋ 圖頂標籤（估寬避撞、最多三行）
    if qlines:
        placed = []                                        # (row, x_end)
        rows_y = [T + 14, T + 31, T + 48]
        for x, text, lcls, key, dashed in sorted(qlines, key=lambda q: q[0]):
            px = xs(x)
            if dashed:
                line = (f'<line class="ref{(" " + lcls) if lcls else ""}" x1="{n(px,2)}" y1="{n(T+4)}" '
                        f'x2="{n(px,2)}" y2="{n(y0,2)}"></line>')
            else:
                line = (f'<line class="{lcls or "c-ink"}" stroke-width="2" x1="{n(px,2)}" y1="{n(T+4)}" '
                        f'x2="{n(px,2)}" y2="{n(y0,2)}"></line>')
            tw = _tw(text, 14.5)
            anchor, tx = "start", px + 5
            if tx + tw > L + pw:
                anchor, tx = "end", px - 5
            row = 0
            for r in range(len(rows_y)):
                left = tx if anchor == "start" else tx - tw
                if all(not (rr == r and left < xe + 8) for rr, xe in placed):
                    row = r
                    break
            else:
                row = len(placed) % len(rows_y)
            placed.append((row, (tx + tw) if anchor == "start" else tx))
            lab = (f'<text class="refl" x="{n(tx,2)}" y="{n(rows_y[row])}" text-anchor="{anchor}">{esc(text)}</text>')
            if key:
                A(f'<g class="ser" data-key="{esc(key)}">{line}{lab}</g>')
            else:
                A(line)
                A(lab)

    base_hint = hint or ("滑過任一箱看各組人數與佔比・點上方圖例可切換組別" if ng > 1 else "滑過任一箱看人數與佔比")
    if notes:
        base_hint = base_hint + "・" + "；".join(notes)
    A(_hint(L, h - 8, base_hint))
    A("</g></svg>")
    return "".join(o)


# ---------------------------------------------------------------- pre/post 分群啞鈴圖（v1.3）
def dumbbell(rows, aria, desc, h=None, m=(44, 150, 44, 150), unit="", nd=1, a_name="前", b_name="後",
             xmin=None, xmax=None, xlab="", hint=None, value_labels=True, delta_head="變化", cls="c-s1",
             row_h=None):
    """每群一條水平線、兩端圓點：空心＝a（前）、實心＝b（後）；右側欄標 ▲▼ 變化。v1.3 新增，data-kind="bar"。

    rows: [(群組, a, b, 變化文字 "▲ +12.3%", tone "up"/"dn"/"ink")]，已依 figures 的 sort 排好。
    連線用方向色（紅漲綠跌）＋右側 ▲▼ 正負號文字——顏色不是唯一線索；圓點一律中性藍（前後用空心／實心分，不用兩色）。
    零 CSS 變動的畫法：實心點是 rx=ry 的 rect（rect.c-s1 有 fill）、空心點是 circle.ser（fill:none ＋ .c-s1 stroke）、
    連線是 3px 高的 rect.bar.c-up／c-dn（rect.c-up 有 fill；也讓 QA 第 10 項把它列進方向色清單）。
    互動掛勾：每列一個 g.mark[data-tip]（整列命中；tooltip：a、b、變化），沒有序列切換；圖例是靜態的 ○ 前 ● 後。
    """
    T, R, B, L = m
    nb = len(rows)
    rh = row_h or (34.0 if nb <= 12 else max(26.0, 34.0 - (nb - 12) * 1.0))
    ph = nb * rh
    h = h or (T + ph + B)
    pw = VB_W - L - R
    allv = [v for r in rows for v in (r[1], r[2])]
    lo = min(allv) if xmin is None else float(xmin)
    hi = max(allv) if xmax is None else float(xmax)
    if hi <= lo:
        hi = lo + 1.0
    pad_px = 62.0 if value_labels else 14.0              # 讓數值標籤留在圖內
    xs = Scale(lo, hi, L + pad_px, L + pw - pad_px)
    r = 6.5
    ustr = (" " + unit) if unit else ""

    o = [_svg_open(h, "bar", aria, desc)]
    A = o.append
    A('<g class="plot">')
    xt, _, _ = nice_ticks(lo, hi, 6)
    xt = [t for t in xt if lo - 1e-9 <= t <= hi + 1e-9]
    for t in xt:
        x = xs(t)
        A(f'<line class="grid" x1="{n(x,2)}" y1="{n(T)}" x2="{n(x,2)}" y2="{n(T+ph)}"></line>')
        A(f'<text class="lb xl" x="{n(x,2)}" y="{n(T+ph+22)}" text-anchor="middle">'
          f'{esc(fmt(t, 0 if float(t).is_integer() else nd))}</text>')
    A(f'<line class="axis" x1="{n(L)}" y1="{n(T+ph)}" x2="{n(L+pw)}" y2="{n(T+ph)}"></line>')
    # 靜態圖例（○ 前 ● 後）與右欄標題
    ly = T - 12
    A(f'<g class="lgd static"><circle class="ser {cls}" cx="{n(L+8)}" cy="{n(ly-4)}" r="{n(r)}" stroke-width="2.4"></circle>'
      f'<text class="vl lgt" x="{n(L+22)}" y="{n(ly+1)}">{esc(a_name)}</text>')
    ax = L + 22 + _tw(a_name, 16) + 22
    A(f'<rect class="{cls}" x="{n(ax-r,2)}" y="{n(ly-4-r,2)}" width="{n(2*r)}" height="{n(2*r)}" rx="{n(r)}" ry="{n(r)}"></rect>'
      f'<text class="vl lgt" x="{n(ax+14,2)}" y="{n(ly+1)}">{esc(b_name)}</text></g>')
    A(f'<text class="lb hd" x="{n(VB_W-6)}" y="{n(T-9)}" text-anchor="end">{esc(delta_head)}</text>')
    if xlab:
        A(f'<text class="lb ax" x="{n(L+pw)}" y="{n(h-8)}" text-anchor="end">{esc(xlab)}</text>')

    for i, (name, a, b, dtext, tone) in enumerate(rows):
        y = T + i * rh + rh / 2
        xa, xb = xs(a), xs(b)
        tip = tipjson(name, [(a_name, fmt(a, nd) + ustr), (b_name, fmt(b, nd) + ustr), (delta_head, dtext)])
        A(f'<g class="mark" data-tip="{tip}" tabindex="0" role="button" '
          f'aria-label="{esc(name)} {esc(a_name)} {esc(fmt(a, nd))}{esc(ustr)} {esc(b_name)} {esc(fmt(b, nd))}{esc(ustr)} {esc(dtext)}">')
        A(f'<rect class="hit" x="6" y="{n(T+i*rh,2)}" width="{n(VB_W-12)}" height="{n(rh,2)}"></rect>')
        A(f'<text class="lb bl" x="{n(L-12)}" y="{n(y+5,2)}" text-anchor="end">{esc(name)}</text>')
        x0, x1 = min(xa, xb) + r, max(xa, xb) - r
        if x1 - x0 > 0.5:
            ccls = "c-up" if tone == "up" else ("c-dn" if tone == "dn" else "c-neu")
            A(f'<rect class="bar {ccls}" x="{n(x0,2)}" y="{n(y-1.5,2)}" width="{n(x1-x0,2)}" height="3"></rect>')
        A(f'<circle class="ser {cls}" cx="{n(xa,2)}" cy="{n(y,2)}" r="{n(r)}" stroke-width="2.4"></circle>')
        A(f'<rect class="{cls}" x="{n(xb-r,2)}" y="{n(y-r,2)}" width="{n(2*r)}" height="{n(2*r)}" rx="{n(r)}" ry="{n(r)}"></rect>')
        if value_labels:
            lv, rv = (a, b) if xa <= xb else (b, a)
            A(f'<text class="lb sh" x="{n(min(xa,xb)-r-6,2)}" y="{n(y+5,2)}" text-anchor="end">{esc(fmt(lv, nd))}</text>')
            A(f'<text class="lb sh" x="{n(max(xa,xb)+r+6,2)}" y="{n(y+5,2)}">{esc(fmt(rv, nd))}</text>')
        tcls = "vl" + (" c-up-t" if tone == "up" else (" c-dn-t" if tone == "dn" else ""))
        A(f'<text class="{tcls}" x="{n(VB_W-6)}" y="{n(y+5,2)}" text-anchor="end">{esc(dtext)}</text>')
        A("</g>")
    A(_hint(L, h - 8, hint or f"滑過任一列看{a_name}／{b_name}與變化"))
    A("</g></svg>")
    return "".join(o)
