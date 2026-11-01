# charts-demo-7 — skill v1.7 新能力樣張

兩項都是**宣告才生效**，不宣告時輸出與 v1.6 逐 byte 相同：

| 能力 | 宣告 | 在哪 |
|---|---|---|
| 圖例搬到 x 軸下方 | `legend: bottom` | `type: line` 的圖表宣告 |
| 結論改純條列（可有一層 `　◦ ` 子項） | `conclusion_style: list` | 檔頭 front-matter |

重建：

    python3 scripts/build.py --md examples/charts-demo-7/報告內容.md --out /tmp/o
    python3 scripts/qa_html.py "/tmp/o/示意遊戲－v1.7 新能力樣張（圖例搬到 x 軸下方／結論改條列）.html"
