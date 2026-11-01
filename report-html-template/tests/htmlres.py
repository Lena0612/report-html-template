# -*- coding: utf-8 -*-
"""htmlres — 把 <style> 的規則跟 HTML 元素（不是 SVG）跑一次 CSS 串接，
算出某個屬性的**最終生效值**與來源（inline／css／initial）。

為什麼要這個：v1.8 的顏色 bug 就是栽在「原始碼寫了屬性、瀏覽器卻用 CSS 的值」。
v1.9 新增的兩項能力也都是靠 inline style 生效（CSS 從 v1.1 起凍結），所以驗收一樣
不能只 grep 原始碼有沒有那串字，要問「這個格子的 border-left 最後到底是多少、誰贏的」。

另外提供 count_matching()：某個選擇器在這份 HTML 裡命中幾個元素。
`.theme-b .sec-key .sec-h::after`（「最重要」膠囊）沒辦法用 inline style 蓋掉，
唯一的驗收方式就是「沒有任何元素命中它的選擇器」。

只支援本專案 <style> 用得到的選擇器形狀，與 cssres.py 同一套。
"""
import re
from html.parser import HTMLParser

import cssres

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr", "path", "circle", "line",
        "rect", "polyline", "polygon", "use", "stop"}
# 本模組會用到的屬性（cssres 預設只收 fill／stroke）
PROPS = ("border-left", "border-left-width", "border-top", "border-right",
         "border", "background", "background-color", "color", "content")


class _Tree(HTMLParser):
    """走一遍文件，對每個元素記下 (由外到內的 chain, inline style dict, 文字內容)。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.ids = []          # 與 stack 同步：每一層的 id（沒有就 None）
        self.out = []

    def _push(self, tag, attrs):
        d = dict(attrs)
        el = (tag, set((d.get("class") or "").split()), set(d.keys()))
        self.stack.append(el)
        self.ids.append(d.get("id"))
        inl = {}
        for decl in (d.get("style") or "").split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                inl[k.strip()] = v.strip()
        # ids＝自己與所有祖先的 id，用來把查詢範圍縮到某一張表／某一個區塊
        self.out.append(dict(tag=tag, chain=list(self.stack), inline=inl,
                             attrs=d, text="",
                             ids=set(x for x in self.ids if x)))
        return self.out[-1]

    def handle_starttag(self, tag, attrs):
        rec = self._push(tag, attrs)
        if tag in VOID:
            self.stack.pop()
            self.ids.pop()
            rec["closed"] = True

    def handle_startendtag(self, tag, attrs):
        self._push(tag, attrs)
        self.stack.pop()
        self.ids.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                del self.ids[i:]
                return

    def handle_data(self, data):
        # 把文字掛到目前最內層那個元素上（只拿來認人，夠用）
        if not self.stack:
            return
        cur = self.stack[-1]
        for rec in reversed(self.out):
            if rec["chain"] and rec["chain"][-1] is cur:
                rec["text"] += data
                return


def _css(html_text):
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html_text, re.S))
    rules, _media = cssres.parse_css(css, PROPS)
    return rules


def elements(html_text):
    """回傳 [dict(tag, chain, inline, attrs, text)]，含 <body> 底下所有元素。"""
    p = _Tree()
    p.feed(html_text)
    return p.out


def resolve(html_text, prop, pick):
    """對 pick(rec) 為真的元素，算 prop 的最終生效值。
    回傳 [(rec, 來源, 值)]；來源 ∈ inline／css／initial。"""
    rules = _css(html_text)
    out = []
    for rec in elements(html_text):
        if not pick(rec):
            continue
        src, val, _sel = cssres.winner(rules, rec["chain"], prop,
                                       None, rec["inline"].get(prop))
        out.append((rec, src, val))
    return out


def count_matching(html_text, selector):
    """某個選擇器命中幾個元素（給「這條 CSS 規則有沒有對象」用）。"""
    n = 0
    for rec in elements(html_text):
        try:
            if cssres.matches(selector, rec["chain"]):
                n += 1
        except ValueError:
            pass
    return n
