# -*- coding: utf-8 -*-
"""極簡 CSS 串接檢查：只支援本專案 <style> 用到的選擇器形狀
（`.a`、`tag.a`、`.a .b`、`tag.a.b`、`g.lgd[data-key]`、`:hover`、媒體查詢）。
目的：判斷某個 SVG 元素上的 presentation attribute（fill=/stroke=）
會不會被 class 規則蓋掉。
"""
import re

PROPS = ("fill", "stroke")


def parse_css(css, props=PROPS):
    """回傳 [(selector_text, order, {prop: (value, important)})]；只收非 @media 區塊。

    v1.9：多一個 props 參數，讓同一支串接判定器也能算 HTML 元素的
    border-*／background／color（tests/htmlres.py 用）。不給就是原本的 fill／stroke，
    既有 E 段的判準一個字都沒改。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, order = [], 0, 0
    # 先把 @media {...} 整塊挖掉（列印樣式不影響螢幕渲染；另外單獨回報）
    media = []
    while True:
        m = re.search(r"@media[^{]*\{", css)
        if not m:
            break
        depth, j = 1, m.end()
        while j < len(css) and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        media.append(css[m.start():j])
        css = css[:m.start()] + css[j:]
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel_all, body = m.group(1).strip(), m.group(2)
        decl = {}
        for d in body.split(";"):
            if ":" not in d:
                continue
            k, v = d.split(":", 1)
            k, v = k.strip(), v.strip()
            imp = "!important" in v
            if k in props:
                decl[k] = (v.replace("!important", "").strip(), imp)
        if not decl:
            order += 1
            continue
        for sel in sel_all.split(","):
            out.append((sel.strip(), order, decl))
        order += 1
    return out, media


_SIMPLE = re.compile(r"^([a-zA-Z][\w-]*)?((?:\.[\w-]+)*)((?:\[[^\]]+\])*)"
                     r"((?::[\w-]+)*)$")


def _parse_simple(s):
    m = _SIMPLE.match(s)
    if not m:
        raise ValueError("不支援的選擇器片段：" + s)
    tag = m.group(1)
    classes = [c for c in m.group(2).split(".") if c]
    attrs = re.findall(r"\[([^\]=]+)(?:=[^\]]*)?\]", m.group(3))
    pseudo = [p for p in m.group(4).split(":") if p]
    return tag, classes, attrs, pseudo


def specificity(sel):
    a = b = c = 0
    for part in sel.split():
        if part in (">", "+", "~"):
            continue
        tag, classes, attrs, pseudo = _parse_simple(part)
        b += len(classes) + len(attrs) + len(pseudo)
        if tag:
            c += 1
    return (a, b, c)


def matches(sel, chain):
    """chain＝從外到內的元素串 [(tag, set(classes), set(attr_names)), ...]，
    最後一個是目標元素。descendant 組合子（空白）即可，本專案沒有 > + ~。"""
    parts = [p for p in sel.split() if p]
    ci = len(chain) - 1

    def one(part, el):
        tag, classes, attrs, pseudo = _parse_simple(part)
        if pseudo:                       # :hover 等狀態，靜態渲染不計
            return False
        if tag and tag != el[0]:
            return False
        if not set(classes) <= el[1]:
            return False
        if not set(attrs) <= el[2]:
            return False
        return True

    if not one(parts[-1], chain[-1]):
        return False
    # 其餘部分由內往外貪婪比對
    pi = len(parts) - 2
    ci -= 1
    while pi >= 0:
        while ci >= 0 and not one(parts[pi], chain[ci]):
            ci -= 1
        if ci < 0:
            return False
        pi -= 1
        ci -= 1
    return True


def winner(rules, chain, prop, pres_attr=None, inline=None):
    """回傳 (來源, 值)。來源 ∈ {'inline','css','presentation','initial'}。"""
    best = None
    for sel, order, decl in rules:
        if prop not in decl:
            continue
        try:
            if not matches(sel, chain):
                continue
        except ValueError:
            continue
        val, imp = decl[prop]
        k = (1 if imp else 0, specificity(sel), order)
        if best is None or k > best[0]:
            best = (k, val, sel)
    if inline is not None:
        # inline style 贏過所有非 !important 的規則
        if best is None or best[0][0] == 0:
            return "inline", inline, None
    if best is not None:
        return "css", best[1], best[2]
    if pres_attr is not None:
        return "presentation", pres_attr, None
    return "initial", None, None
