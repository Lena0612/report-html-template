# -*- coding: utf-8 -*-
"""inspect_inputs — 開工第一步：掃一個資料夾，列出裡面有什麼可以拿來填報告（純 stdlib）。

    python3 inspect_inputs.py <資料夾或檔案> [<更多路徑>...] [--rows 5] [--json]

    .csv／.tsv   欄位、列數、前幾列、每欄看起來是數字還是文字、日期欄猜測
    .ipynb       用 json 讀 cells：每個 code cell 的 outputs（text/plain、execute_result 表格、
                 print 出的文字）；markdown cell 的標題與前幾行；圖片 output 只記「有一張圖」不重用
    .md／.txt    標題結構、字數、前幾行（結論與敘述來源）
    .json        最外層鍵（values.json 這類）
    其他         只列檔名與大小

輸出是給 Claude 看的盤點表，讓它決定「哪張圖用哪份資料、哪些數字要放進 values」。
不改任何檔、不需要 pandas。
"""
import csv
import io
import json
import os
import re
import sys

MAX_CELL_TEXT = 1200          # 每個 ipynb output 最多印這麼多字元
DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$|^\d{8}$|^\d{1,2}/\d{1,2}(/\d{2,4})?$")
NUM_RE = re.compile(r"^[-+]?[\d,]*\.?\d+([eE][-+]?\d+)?%?$")


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def sniff(path):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        head = fh.read(20000)
    delim = "\t" if path.lower().endswith(".tsv") or head.count("\t") > head.count(",") else ","
    return head, delim


def guess_type(vals):
    vals = [v.strip() for v in vals if v.strip() != ""]
    if not vals:
        return "空"
    if all(NUM_RE.match(v) for v in vals):
        return "數字" + ("（含 %）" if any(v.endswith("%") for v in vals) else "")
    if all(DATE_RE.match(v) for v in vals):
        return "日期"
    return "文字"


def inspect_csv(path, nrows):
    head, delim = sniff(path)
    rows = list(csv.reader(io.StringIO(head), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return {"kind": "csv", "error": "空檔"}
    hdr = [h.strip() for h in rows[0]]
    body = rows[1:]
    total = sum(1 for _ in io.open(path, encoding="utf-8-sig", errors="replace")) - 1
    cols = []
    for i, h in enumerate(hdr):
        vals = [r[i] for r in body if i < len(r)]
        cols.append({"name": h, "type": guess_type(vals),
                     "sample": [v for v in vals[:3]]})
    return {"kind": "csv", "delimiter": "tab" if delim == "\t" else ",", "columns": cols,
            "n_rows": max(total, 0), "head": [dict(zip(hdr, r)) for r in body[:nrows]],
            "hint": _csv_hint(cols)}


def _csv_hint(cols):
    types = [c["type"] for c in cols]
    names = [c["name"] for c in cols]
    lname = [str(n).strip().lower() for n in names]
    if "日期" in types and types.count("數字") >= 1:
        hint = f"看起來是時間序列：x 用 `{names[types.index('日期')]}`，可畫 type: line"
        if 2 <= types.count("數字") <= 5:
            hint += "；若各欄是同一總量的組成（人數、金額，皆 ≥ 0）也可畫 type: stacked（柱頂合計）"
        return hint
    # v1.1：留存曲線（第一欄是 day／D1 這類天數位移 ＋ 幾群的留存率）
    if len(types) >= 2 and all(t.startswith("數字") for t in types[1:]) and (
            lname[0] in ("day", "days", "d", "天", "天數", "dn") or
            all(_is_day(v) for v in cols[0]["sample"] if str(v).strip())):
        return (f"看起來是留存曲線：x 用 `{names[0]}`，可畫 type: retention"
                f"（series: [{', '.join(names[1:4])}]；值是 0~1 寫 scale: ratio、0~100 寫 scale: pct）")
    # v1.2：cohort 留存熱圖（第一欄 cohort 標籤 ＋ 天數位移欄 D0/D1/D7…，可有 size／n 欄；允許空格）
    day_hdr = [nm for nm in names[1:] if _is_day_hdr(nm)]
    if len(types) >= 3 and types[0] == "文字" and len(day_hdr) >= 2 and \
            all(_is_day_hdr(nm) or str(nm).strip().lower() in ("size", "n", "人數", "cohort_size", "users") for nm in names[1:]):
        return (f"看起來是 cohort 留存熱圖：cohort 用 `{names[0]}`，可畫 type: cohort"
                f"（天數欄 {', '.join(day_hdr[:6])}{'…' if len(day_hdr) > 6 else ''}；值 0~1 寫 scale: ratio、0~100 寫 scale: pct；"
                "尚未觀察到的格子留空白即可）")
    if types and types[0] == "文字" and all(t.startswith("數字") for t in types[1:]) and len(types) >= 2:
        if len(types) == 2:
            # v1.1：漏斗（步驟 ＋ 人數，且人數逐列遞減）
            if lname[1] in ("count", "人數", "users", "uid", "uids", "n") or lname[0] in ("step", "步驟", "stage"):
                return f"看起來是漏斗：可畫 type: funnel（step: {names[0]}, count: {names[1]}；人數要逐步遞減）"
            return f"類別 × 一個數值：可畫 type: bars（x: {names[0]}, y: {names[1]}）"
        if len(types) == 3:
            return (f"類別 × 兩個數值：並排比較（例 前／後）畫 type: grouped（series: [{names[1]}, {names[2]}]）；"
                    f"兩段拆解畫 type: ranked（parts: [{names[1]}, {names[2]}]）；"
                    f"兩段是同一總量的組成（人數、金額，皆 ≥ 0）畫 type: stacked；或當表格")
        if len(types) == 4:
            return (f"類別 × 三個數值：可畫 type: grouped（series: [{names[1]}, {names[2]}, {names[3]}]）；"
                    f"三段是同一總量的組成（皆 ≥ 0）畫 type: stacked（柱頂合計）；或當表格")
        if len(types) <= 6:
            return (f"類別 × {len(types) - 1} 個數值：若是同一總量的組成（皆 ≥ 0）畫 type: stacked"
                    f"（segments: [{', '.join(names[1:])}]，2~5 段）；並排比較挑 2~3 欄畫 grouped；或當表格")
        return "類別 × 多個數值：可當表格（```table），或挑 2~5 欄畫 stacked／挑 2~3 欄畫 grouped／挑兩欄畫 ranked／挑占比欄畫 stacked100"
    if len(types) in (3, 4) and all(t.startswith("數字") for t in types):
        return (f"第一欄若是類別（級距、底台、期別）可畫 type: grouped（x: {names[0]}, series: [{', '.join(names[1:])}]）；"
                "若是連續 x 就當表格或改成 line")
    return "先看前幾列決定：當表格用 ```table，當圖用 ```figure"


def _is_day_hdr(v):
    """欄名是天數位移（D0、D7、Day 7、7、7 天）→ cohort 熱圖的欄。純數字欄名也算（第一欄是文字時才會用到）。"""
    import re as _re
    return bool(_re.match(r"^(?:[Dd]|[Dd]ay\s*|第\s*)?\d+\s*(?:天|日)?$", str(v).strip()))


def _is_day(v):
    """有明確天數標記才算（D1、Day 7、7 天）；純數字不算，免得把底台、級距誤判成留存曲線。"""
    import re as _re
    return bool(_re.match(r"^(?:[Dd]|[Dd]ay\s*)\d+$|^\d+\s*(?:天|日)$", str(v).strip()))


def inspect_ipynb(path, nrows):
    try:
        nb = json.load(io.open(path, encoding="utf-8"))
    except Exception as e:
        return {"kind": "ipynb", "error": f"讀不起來：{e}"}
    cells_out = []
    for idx, c in enumerate(nb.get("cells", [])):
        src = "".join(c.get("source", []))
        ct = c.get("cell_type")
        if ct == "markdown":
            heads = [l.strip() for l in src.splitlines() if l.strip().startswith("#")]
            cells_out.append({"i": idx, "type": "markdown", "headings": heads[:6],
                              "first_lines": [l for l in src.splitlines() if l.strip()][:4],
                              "chars": len(src)})
            continue
        if ct != "code":
            continue
        outs = []
        for o in c.get("outputs", []):
            ot = o.get("output_type")
            if ot == "stream":
                txt = "".join(o.get("text", []))
                outs.append({"type": "print", "text": txt[:MAX_CELL_TEXT],
                             "looks_like_table": _looks_table(txt)})
            elif ot in ("execute_result", "display_data"):
                d = o.get("data", {})
                if "text/html" in d and "<table" in "".join(d["text/html"]):
                    tbl = _html_table("".join(d["text/html"]))
                    outs.append({"type": "table", "shape": tbl["shape"], "columns": tbl["columns"],
                                 "head": tbl["rows"][:nrows]})
                elif "text/plain" in d:
                    txt = "".join(d["text/plain"])
                    outs.append({"type": "result", "text": txt[:MAX_CELL_TEXT],
                                 "looks_like_table": _looks_table(txt)})
                if any(k.startswith("image/") for k in d):
                    outs.append({"type": "image", "note": "有一張圖（只當參考，報告的圖用 svgchart 重畫）"})
            elif ot == "error":
                outs.append({"type": "error", "ename": o.get("ename", ""), "evalue": str(o.get("evalue", ""))[:200]})
        if outs or src.strip():
            first = next((l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")), "")
            cells_out.append({"i": idx, "type": "code", "first_line": first[:120],
                              "n_outputs": len(outs), "outputs": outs})
    return {"kind": "ipynb", "n_cells": len(nb.get("cells", [])), "cells": cells_out}


def _looks_table(txt):
    lines = [l for l in txt.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    cols = [len(re.split(r"\s{2,}|\t|\|", l.strip())) for l in lines[:6]]
    return min(cols) >= 2 and max(cols) - min(cols) <= 1


def _html_table(h):
    """最簡單的 <table> 解析：thead th 當欄名，tbody tr/td 當列（pandas 的 DataFrame HTML）。"""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.cur, self.cell, self.in_cell = [], None, None, False

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.cur = []
            elif tag in ("td", "th"):
                self.cell, self.in_cell = [], True

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cur is not None:
                self.cur.append("".join(self.cell).strip())
                self.in_cell = False
            elif tag == "tr" and self.cur is not None:
                self.rows.append(self.cur)
                self.cur = None

        def handle_data(self, data):
            if self.in_cell:
                self.cell.append(data)
    p = P()
    p.feed(h)
    rows = [r for r in p.rows if r]
    if not rows:
        return {"shape": (0, 0), "columns": [], "rows": []}
    return {"shape": (len(rows) - 1, len(rows[0])), "columns": rows[0], "rows": rows[1:]}


def inspect_md(path):
    txt = io.open(path, encoding="utf-8", errors="replace").read()
    heads = [l.strip() for l in txt.splitlines() if re.match(r"^#{1,6}\s", l)]
    nums = re.findall(r"[-+]?\d[\d,]*\.?\d*\s*(?:%|pp|分|人|次|日|天)", txt)
    return {"kind": "md", "chars": len(txt), "headings": heads[:20],
            "first_lines": [l for l in txt.splitlines() if l.strip()][:6],
            "n_numbers_with_unit": len(nums), "numbers_sample": nums[:12],
            "hint": "結論與敘述來源：本章結論／判讀／結論卡可以直接改寫這裡的句子；數字照抄前先對回 csv"}


def inspect_json(path):
    try:
        d = json.load(io.open(path, encoding="utf-8"))
    except Exception as e:
        return {"kind": "json", "error": f"讀不起來：{e}"}
    if isinstance(d, dict):
        return {"kind": "json", "top": "object", "n_keys": len(d), "keys": list(d)[:30]}
    if isinstance(d, list):
        return {"kind": "json", "top": "array", "n": len(d),
                "first_keys": list(d[0]) [:20] if d and isinstance(d[0], dict) else None}
    return {"kind": "json", "top": type(d).__name__}


def inspect_path(path, nrows):
    ext = os.path.splitext(path)[1].lower()
    info = {"path": path, "size": human(os.path.getsize(path))}
    try:
        if ext in (".csv", ".tsv"):
            info.update(inspect_csv(path, nrows))
        elif ext == ".ipynb":
            info.update(inspect_ipynb(path, nrows))
        elif ext in (".md", ".txt"):
            info.update(inspect_md(path))
        elif ext == ".json":
            info.update(inspect_json(path))
        else:
            info["kind"] = "other"
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def walk(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "out")]
                for f in sorted(files):
                    if not f.startswith("."):
                        out.append(os.path.join(root, f))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print(f"（找不到：{p}）", file=sys.stderr)
    return out


def print_report(infos):
    print(f"盤點 {len(infos)} 個檔案\n")
    for info in infos:
        k = info.get("kind", "other")
        print(f"■ {info['path']}  [{k}, {info['size']}]")
        if "error" in info:
            print(f"   ⚠ {info['error']}")
            continue
        if k == "csv":
            print(f"   {info['n_rows']} 列 × {len(info['columns'])} 欄（分隔：{info['delimiter']}）")
            for c in info["columns"]:
                print(f"   - {c['name']:<20} {c['type']:<8} 例：{', '.join(c['sample'])}")
            for r in info["head"]:
                print("   " + " | ".join(f"{v}" for v in r.values()))
            print(f"   → {info['hint']}")
        elif k == "ipynb":
            print(f"   {info['n_cells']} 個 cell")
            for c in info["cells"]:
                if c["type"] == "markdown":
                    if c["headings"]:
                        print(f"   [md #{c['i']}] {' / '.join(c['headings'][:3])}")
                    elif c["first_lines"]:
                        print(f"   [md #{c['i']}] {c['first_lines'][0][:100]}")
                    continue
                if not c["n_outputs"]:
                    continue
                print(f"   [code #{c['i']}] {c['first_line']}")
                for o in c["outputs"]:
                    if o["type"] == "table":
                        print(f"      表格 {o['shape'][0]} 列 × {o['shape'][1]} 欄：{', '.join(o['columns'][:10])}")
                        for r in o["head"][:3]:
                            print("        " + " | ".join(r))
                    elif o["type"] in ("print", "result"):
                        tag = "表格狀輸出" if o["looks_like_table"] else o["type"]
                        first = [l for l in o["text"].splitlines() if l.strip()][:5]
                        print(f"      {tag}：" + (" ⏎ ".join(l.strip()[:90] for l in first)))
                    elif o["type"] == "image":
                        print(f"      圖片：{o['note']}")
                    elif o["type"] == "error":
                        print(f"      錯誤：{o['ename']} {o['evalue']}")
        elif k == "md":
            print(f"   {info['chars']} 字元；標題：{' / '.join(info['headings'][:6]) or '（無）'}")
            for l in info["first_lines"][:3]:
                print(f"   {l[:110]}")
            print(f"   帶單位的數字 {info['n_numbers_with_unit']} 個，例：{', '.join(info['numbers_sample'][:8])}")
            print(f"   → {info['hint']}")
        elif k == "json":
            print(f"   {info}")
        print()
    print("下一步：決定每張圖用哪份 csv 的哪幾欄（type: line／bars／ranked／stacked100／waterfall／retention／grouped／funnel／stacked／cohort），"
          "哪些數字進 values；然後複製 assets/templates/報告內容.template.md 開始填。")


def main(argv):
    nrows, as_json, paths = 5, False, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--rows":
            i += 1
            nrows = int(argv[i])
        elif a == "--json":
            as_json = True
        else:
            paths.append(a)
        i += 1
    if not paths:
        print(__doc__)
        return 2
    infos = [inspect_path(p, nrows) for p in walk(paths)]
    if as_json:
        print(json.dumps(infos, ensure_ascii=False, indent=1, default=str))
    else:
        print_report(infos)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
