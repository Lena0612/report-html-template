# -*- coding: utf-8 -*-
"""build — 讀內容檔（md ＋ csv／json 資料）→ 產單檔 HTML（風格 B 現代儀表板，v3 版型）。

    python3 build.py --md 報告內容.md                      # 產到 md 同資料夾的 out/<title>.html
    python3 build.py --md 報告內容.md --out /path/dir/      # 指定資料夾（檔名用 title）
    python3 build.py --md 報告內容.md --out /path/報告.html # 指定完整檔名
    python3 build.py --md 報告內容.md --keys               # 印出可用的 {{v:key}} 與圖表 key
    python3 build.py --types                              # 印出支援的圖表類型與欄位

流程（v4，skill 版）：

    報告內容.md（文字 ＋ ```figure／```table 宣告 ＋ 檔頭 values）
        + data/*.csv、data/values.json
        → mdcontent.load()   解析、讀資料、算數字、畫圖、組 Report
        → Report.render("B") 排版（rhtml.py／themes.py 不動）
        → <title>.html

內容檔有問題（標記打錯、欄名不存在、檔頭缺欄位）就印出「第幾行、什麼問題」
然後以 exit 1 停下來，**不會寫出半成品的 HTML**、也不會動到既有的檔。

只產風格 B：Lena 2026-09-14 定案 A／C 收掉，只留 B_v3。
純 stdlib（Python 3.8+），不需要 numpy／pandas。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import figures       # noqa: E402
import mdcontent     # noqa: E402
from themes import LABELS  # noqa: E402

THEME = "B"


def safe_name(title):
    s = re.sub(r"\{\{[^}]*\}\}|\[\[|\]\]|!!|\*\*", "", title)
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", s).strip(" ._")
    return (s or "report")[:80]


def print_keys(md):
    doc, figs, tbls, problems = mdcontent.keys_report(md)
    if problems:
        print(mdcontent.ContentError(md, sorted(problems, key=lambda x: x[0])).report())
    print(f"\n內容檔可以用的數字標記（共 {len(doc)} 個）：寫 {{{{v:key}}}} 就會換成右邊那個值\n")
    print(f"{'標記':<30}{'目前的值':<28}來源")
    print("-" * 92)
    for k, v, where in doc:
        print(f"{('{{v:' + k + '}}'):<30}{v:<28}{where}")
    print("\n圖（```figure，正文用 [[key]] 引用）：" + ("、".join(figs) or "（無）"))
    print("表（```table，正文用 [[key]] 引用）：" + ("、".join(tbls) or "（無）"))
    return 1 if problems else 0


def main(argv):
    md, out = None, None
    want_keys = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--md":
            i += 1
            md = argv[i] if i < len(argv) else None
        elif a == "--out":
            i += 1
            out = argv[i] if i < len(argv) else None
        elif a == "--keys":
            want_keys = True
        elif a == "--types":
            print("v1.6 支援的圖表類型（```figure 的 type:）與欄位：\n")
            print(figures.type_help())
            return 0
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"[build] 不認識的參數：{a}\n{__doc__}")
            return 2
        i += 1
    if not md:
        print("[build] 要指定 --md 內容檔.md\n" + __doc__)
        return 2
    md = os.path.abspath(md)
    if want_keys:
        return print_keys(md)

    try:
        R = mdcontent.load(md)
    except mdcontent.ContentError as e:
        print(e.report())
        return 1

    md_dir = os.path.dirname(md)
    if out is None:
        out_dir, out_name = os.path.join(md_dir, "out"), None
    elif out.lower().endswith(".html"):
        out_dir, out_name = os.path.dirname(os.path.abspath(out)) or ".", os.path.basename(out)
    else:
        out_dir, out_name = os.path.abspath(out), None
    if out_name is None:
        out_name = safe_name(R.title) + ".html"

    badge = (getattr(R, "badge", "") or "").replace("{風格}", f"{THEME}　{LABELS[THEME]}")
    html = R.render(THEME, badge)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, out_name)
    io.open(path, "w", encoding="utf-8").write(html)
    n_fig = html.count('<figure class="blk fig"')
    n_tbl = html.count('<div class="blk tbl"')
    n_xref = html.count('class="xref"')
    n_toc = html.count('class="toc-link toc-l1"')
    kb = len(html.encode("utf-8")) / 1024
    print(f"[build] {path}")
    print(f"[build] {kb:.0f} KB  圖 {n_fig} 張  表 {n_tbl} 張  引用 {n_xref} 處  目錄 {n_toc} 項  "
          f"數字 key {len(getattr(R, 'value_doc', []))} 個")
    print(f"[build] 內容檔：{md}（{len(io.open(md, encoding='utf-8').read())} 字元）")
    print("[build] 下一步：python3 qa_html.py " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
