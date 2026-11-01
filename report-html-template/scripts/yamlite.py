# -*- coding: utf-8 -*-
"""yamlite — YAML 子集解析器（純 stdlib，給 ```figure／```table 區塊與檔頭用）。

只支援報告宣告會用到的寫法，錯了就報「第幾行、什麼問題」：

    key: 值                      # 對應（mapping）
    key:                         # 巢狀：底下縮排更深的區塊
      子鍵: 值
    key: [a, b, 3]               # 流式清單
    key: {col: raw, width: 1.3}  # 流式對應（值裡有 , : { } 要用引號包起來）
    key:
      - 項目                     # 區塊清單
      - {col: p50, name: p50}
      - col: p90                 # 清單項目本身是對應
        name: p90
    key: |                       # 區塊文字（CSV 內容），縮排比 key 深的行全部保留
      a,b,c
      1,2,3

規則
  * 縮排只能用空格。註解：行首的 `#`，或行內「空格 + # + 空格」（`值   # 說明`）；
    `#` 後面直接接字的不算註解（所以 `著色: 紅 #c62828` 不會被截掉）。
  * 純數字自動轉成 int／float，`true`／`false`／`null` 也會轉；
    其他一律字串。要保留數字原樣（例如 `07-16`）本來就不是純數字，不會被轉。
  * 以 `{{` 開頭的值視為字面字串（`{{v:key}}` 這類報告標記），不當流式對應。

parse(text, base_ln) 回傳 (物件, 行號表)：行號表以路徑 tuple 為 key，
例如 ("series", 1, "col") → 該值所在的絕對行號，給呼叫端報錯用。
"""
import re

RE_NUM = re.compile(r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$")
RE_INT = re.compile(r"^[-+]?\d+$")


class YamlError(Exception):
    def __init__(self, ln, msg):
        self.ln, self.msg = ln, msg
        super().__init__(f"第 {ln} 行：{msg}")


# ---------------------------------------------------------------- 標量
def scalar(s, ln):
    """單一值：引號字串／數字／布林／null／其他字串。"""
    s = s.strip()
    if not s:
        return ""
    if s[0] in "\"'":
        v, end = _quoted(s, 0, ln)
        if s[end:].strip():
            raise YamlError(ln, f"引號結束後還有多餘文字：{s[end:].strip()[:20]}")
        return v
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    if RE_INT.match(s):
        try:
            return int(s)
        except ValueError:
            return s
    if RE_NUM.match(s):
        return float(s)
    return s


def _quoted(s, i, ln):
    """從 s[i] 的引號開始讀到對應的收尾引號。回傳 (字串, 收尾後的索引)。"""
    q = s[i]
    out, j = [], i + 1
    while j < len(s):
        c = s[j]
        if q == '"' and c == "\\" and j + 1 < len(s):
            nxt = s[j + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
            j += 2
            continue
        if c == q:
            if q == "'" and j + 1 < len(s) and s[j + 1] == "'":
                out.append("'")
                j += 2
                continue
            return "".join(out), j + 1
        out.append(c)
        j += 1
    raise YamlError(ln, f"引號沒有收尾：{s[i:i+20]}")


# ---------------------------------------------------------------- 流式 [] {}
def _flow(s, i, ln, path, lines):
    """解析 s[i] 開頭的 [ 或 {。回傳 (值, 下一個索引)。"""
    open_c = s[i]
    close_c = "]" if open_c == "[" else "}"
    i += 1
    if open_c == "[":
        out = []
        while True:
            i = _skip_ws(s, i)
            if i >= len(s):
                raise YamlError(ln, "清單 [ 沒有用 ] 收尾")
            if s[i] == "]":
                return out, i + 1
            v, i = _flow_value(s, i, ln, path + (len(out),), lines, ",]")
            lines[path + (len(out),)] = ln
            out.append(v)
            i = _skip_ws(s, i)
            if i >= len(s):
                raise YamlError(ln, "清單 [ 沒有用 ] 收尾")
            if s[i] == ",":
                i += 1
            elif s[i] == "]":
                return out, i + 1
            else:
                raise YamlError(ln, f"清單裡的項目之間要用逗號分開：{s[i:i+15]}")
    out = {}
    while True:
        i = _skip_ws(s, i)
        if i >= len(s):
            raise YamlError(ln, "對應 { 沒有用 } 收尾")
        if s[i] == "}":
            return out, i + 1
        # key
        if s[i] in "\"'":
            k, i = _quoted(s, i, ln)
            i = _skip_ws(s, i)
            if i >= len(s) or s[i] != ":":
                raise YamlError(ln, f"{{}} 裡的 `{k}` 後面要接冒號")
            i += 1
        else:
            j = i
            while j < len(s) and s[j] not in ":,}":
                j += 1
            if j >= len(s) or s[j] != ":":
                raise YamlError(ln, f"{{}} 裡缺冒號：`{s[i:j].strip()[:20]}`（格式 {{鍵: 值, 鍵: 值}}）")
            k = s[i:j].strip()
            i = j + 1
        if not k:
            raise YamlError(ln, "{} 裡有空的鍵")
        if k in out:
            raise YamlError(ln, f"鍵 `{k}` 重複了")
        i = _skip_ws(s, i)
        v, i = _flow_value(s, i, ln, path + (k,), lines, ",}")
        lines[path + (k,)] = ln
        out[k] = v
        i = _skip_ws(s, i)
        if i >= len(s):
            raise YamlError(ln, "對應 { 沒有用 } 收尾")
        if s[i] == ",":
            i += 1
        elif s[i] == "}":
            return out, i + 1
        else:
            raise YamlError(ln, f"{{}} 裡的欄位之間要用逗號分開：{s[i:i+15]}")


def _flow_value(s, i, ln, path, lines, stops):
    if i >= len(s):
        raise YamlError(ln, "值不見了")
    c = s[i]
    if c in "\"'":
        v, j = _quoted(s, i, ln)
        return v, j
    if c in "[{" and not s.startswith("{{", i):
        return _flow(s, i, ln, path, lines)
    j = i
    depth = 0
    while j < len(s):
        ch = s[j]
        if ch == "{":
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
        elif ch in stops and depth == 0:
            break
        j += 1
    return scalar(s[i:j], ln), j


def _strip_comment(s):
    """去掉行尾註解：空格 + # + （空格或行尾）。引號開頭的值另外處理。"""
    if s[:1] in "\"'":
        return s
    m = re.search(r"\s+#(?:\s|$)", s)
    return s[:m.start()].rstrip() if m else s


def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t":
        i += 1
    return i


def inline_value(s, ln, path=(), lines=None):
    """一行裡冒號右邊的值：{{標記}}→字串；[ {→流式；引號；否則標量。"""
    if lines is None:
        lines = {}
    s = s.strip()
    if s.startswith("{{"):
        return _strip_comment(s)
    if s and s[0] in "[{":
        v, end = _flow(s, 0, ln, path, lines)
        tail = s[end:].strip()
        if tail and not re.match(r"^#(\s|$)", tail):
            raise YamlError(ln, f"`{s[end - 1]}` 之後還有多餘文字：{tail[:20]}")
        return v
    if s[0] in "\"'":
        v, end = _quoted(s, 0, ln)
        tail = s[end:].strip()
        if tail and not re.match(r"^#(\s|$)", tail):
            raise YamlError(ln, f"引號結束後還有多餘文字：{tail[:20]}")
        return v
    return scalar(_strip_comment(s), ln)


# ---------------------------------------------------------------- 區塊結構
class _Line:
    __slots__ = ("ln", "raw", "indent", "text")

    def __init__(self, ln, raw):
        self.ln, self.raw = ln, raw
        stripped = raw.lstrip(" ")
        self.indent = len(raw) - len(stripped)
        self.text = stripped.rstrip()

    @property
    def blank(self):
        return not self.text or self.text.startswith("#")


def _split_key(text, ln):
    """`key: 值` → (key, 值)；`key:` → (key, "")。找第一個不在引號裡的 `: ` 或行尾 `:`。"""
    if text[0] in "\"'":
        k, j = _quoted(text, 0, ln)
        rest = text[j:].lstrip()
        if not rest.startswith(":"):
            raise YamlError(ln, f"`{k}` 後面要接冒號")
        return k, rest[1:]
    m = re.match(r"^([^:#]+?)\s*:(\s+|$)(.*)$", text)
    if not m:
        raise YamlError(ln, f"這行不是 `欄位: 值`（冒號後面要有空格）：{text[:40]}")
    return m.group(1).strip(), m.group(3)


def parse(text, base_ln=1):
    """解析整段。回傳 (物件, 行號表)。有錯丟 YamlError。"""
    raw_lines = text.replace("\r\n", "\n").split("\n")
    lines = [_Line(base_ln + i, r) for i, r in enumerate(raw_lines)]
    for L in lines:
        if "\t" in L.raw[:L.indent + 1] and L.raw.lstrip(" ").startswith("\t"):
            raise YamlError(L.ln, "縮排不能用 tab，請用空格")
    lnmap = {}
    idx = _next(lines, 0)
    if idx >= len(lines):
        return {}, lnmap
    val, idx = _block(lines, idx, lines[idx].indent, (), lnmap)
    idx = _next(lines, idx)
    if idx < len(lines):
        raise YamlError(lines[idx].ln, f"這行的縮排對不上任何上層欄位：{lines[idx].text[:30]}")
    return val, lnmap


def _next(lines, i):
    while i < len(lines) and lines[i].blank:
        i += 1
    return i


def _is_item(L):
    return L.text == "-" or L.text.startswith("- ")


def _block(lines, i, indent, path, lnmap):
    if _is_item(lines[i]):
        return _seq(lines, i, indent, path, lnmap)
    return _map(lines, i, indent, path, lnmap)


def _block_scalar(lines, i, indent):
    """`key: |` 底下縮排更深的所有行（含空行），去掉共同縮排。"""
    body, j = [], i
    while j < len(lines):
        L = lines[j]
        if not L.text and not L.raw.strip():
            body.append(L)
            j += 1
            continue
        if L.indent <= indent:
            break
        body.append(L)
        j += 1
    while body and not body[-1].raw.strip():
        body.pop()
    if not body:
        return "", j
    common = min(L.indent for L in body if L.raw.strip())
    return "\n".join(L.raw[common:] if L.raw.strip() else "" for L in body), j


def _map(lines, i, indent, path, lnmap):
    out = {}
    while i < len(lines):
        L = lines[i]
        if L.blank:
            i += 1
            continue
        if L.indent < indent:
            break
        if L.indent > indent:
            raise YamlError(L.ln, f"縮排太深（上一個欄位沒有以 `:` 結尾）：{L.text[:30]}")
        if _is_item(L):
            raise YamlError(L.ln, "這裡是對應（key: 值），不能直接放 `- ` 清單項目")
        k, rest = _split_key(L.text, L.ln)
        if k in out:
            raise YamlError(L.ln, f"欄位 `{k}` 重複了")
        p = path + (k,)
        lnmap[p] = L.ln
        rest_s = rest.strip()
        if _strip_comment(rest_s) in ("|", "|-", ">"):
            v, i = _block_scalar(lines, i + 1, indent)
            out[k] = v
            continue
        if rest_s == "":
            j = _next(lines, i + 1)
            if j < len(lines) and lines[j].indent > indent:
                v, i = _block(lines, j, lines[j].indent, p, lnmap)
                out[k] = v
                continue
            out[k] = ""
            i += 1
            continue
        out[k] = inline_value(rest_s, L.ln, p, lnmap)
        i += 1
    return out, i


def _seq(lines, i, indent, path, lnmap):
    out = []
    while i < len(lines):
        L = lines[i]
        if L.blank:
            i += 1
            continue
        if L.indent < indent:
            break
        if L.indent > indent:
            raise YamlError(L.ln, f"縮排對不上清單：{L.text[:30]}")
        if not _is_item(L):
            raise YamlError(L.ln, f"清單裡的每一項都要用 `- ` 開頭：{L.text[:30]}")
        rest = L.text[1:].strip()
        if not rest[:1] in "\"'[{":
            rest = _strip_comment(rest)
        p = path + (len(out),)
        lnmap[p] = L.ln
        if rest == "":
            j = _next(lines, i + 1)
            if j < len(lines) and lines[j].indent > indent:
                v, i = _block(lines, j, lines[j].indent, p, lnmap)
                out.append(v)
                continue
            out.append(None)
            i += 1
            continue
        if _looks_like_map(rest):
            # `- col: p90` ＋ 底下同欄位起始的行：把這行當成子對應的第一行
            col = L.indent + (len(L.text) - len(L.text[1:].lstrip()))
            fake = _Line(L.ln, " " * col + rest)
            sub = lines[:i] + [fake] + lines[i + 1:]
            v, i = _map(sub, i, col, p, lnmap)
            out.append(v)
            continue
        out.append(inline_value(rest, L.ln, p, lnmap))
        i += 1
    return out, i


def _looks_like_map(rest):
    if rest[0] in "[{\"'":
        return False
    if rest.startswith("{{"):
        return False
    return bool(re.match(r"^[^:#]+?\s*:(\s|$)", rest))


# ---------------------------------------------------------------- 小工具
def get_ln(lnmap, path, default=0):
    """找路徑的行號，找不到就往上層找。"""
    p = tuple(path)
    while p:
        if p in lnmap:
            return lnmap[p]
        p = p[:-1]
    return lnmap.get((), default) or default


if __name__ == "__main__":       # 最小自我測試：python3 yamlite.py
    demo = """
key: f1
type: line            # 行首註解
title: 每日平均遊戲時間 #c62828 不是註解
x: date
series:
  - {col: raw, name: 原始 mean, color: raw, width: 1.3, order: 3}
  - col: p90
    name: p90
    width: 1.2
  - "quoted, with comma"
opts: [1, 2.5, a b, "c,d"]
mark: {{v:斷點}} 前後
data: |
  a,b,c
  1,2,3

  4,5,6
empty:
"""
    obj, lm = parse(demo, 10)
    assert obj["key"] == "f1" and obj["type"] == "line"
    assert obj["title"] == "每日平均遊戲時間 #c62828 不是註解"
    assert obj["series"][0] == {"col": "raw", "name": "原始 mean", "color": "raw",
                                "width": 1.3, "order": 3}
    assert obj["series"][1] == {"col": "p90", "name": "p90", "width": 1.2}
    assert obj["series"][2] == "quoted, with comma"
    assert obj["opts"] == [1, 2.5, "a b", "c,d"]
    assert obj["mark"] == "{{v:斷點}} 前後"
    assert obj["data"] == "a,b,c\n1,2,3\n\n4,5,6"
    assert obj["empty"] == ""
    assert lm[("series", 1, "name")] == 18, lm[("series", 1, "name")]
    for bad, want in [("a: [1, 2", "沒有用 ]"), ("a: {x 1}", "缺冒號"),
                      ("a: 1\na: 2", "重複"), ("a:\n  - 1\n b: 2", "縮排"),
                      ("a: 'oops", "引號沒有收尾"), ("a 1", "不是 `欄位: 值`")]:
        try:
            parse(bad)
        except YamlError as e:
            assert want in e.msg, (bad, e.msg)
        else:
            raise AssertionError(bad)
    print("yamlite 自我測試通過")
