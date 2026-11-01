# charts-demo-6 — skill v1.6 兩項新能力的最小樣張

示意假資料，不可引用。只為了驗證 v1.6 新增的兩個**宣告才生效**的欄位：

| # | 能力 | 怎麼開 | 看哪裡 |
|---|---|---|---|
| 1 | 折線事件線的警示 icon | `vlines` 的 `icon: warn` | 圖 3-1（`dau_ev`）5/23 與 6/12 兩條紅虛線的下端 |
| 2 | 顯著底色只標數值較大的一格 | `table` 的 `sig.mark: max` | 表 4-1（`sig_max`）第 1～3 列 |

兩個都不宣告時，輸出與 skill v1.5 逐 byte 相同（playtime-demo、charts-demo、
charts-demo-2／-3／-4／-5 六個樣張的 HTML md5 全部沒變，見 `tests/run_tests.py`）。
qa_html.py 從 v1.6 起是 **17 項**（新增第 17 項「備註四列」），這份樣張 17 項全綠。

這份**刻意不宣告深淺分級**（`scale`／`levels`／`v`），所以表 4-1 是單一階底色、
只是一組配對只標一格。要看深淺三階請看 `examples/sig-shade-demo`；
兩者是正交的、可以併用（`mark` 決定哪一格、`v` 決定多深），併用的組合案例在
`tests/run_tests.py` 的「B 組合」段（在這份樣張上動態補 `scale`／`levels`／`v` 再驗）。

重建：

```bash
python3 scripts/build.py --md examples/charts-demo-6/報告內容.md --out out/
python3 scripts/qa_html.py "out/示意遊戲－v1.6 新能力樣張（事件線警示 icon／顯著底色只標較大格）.html"
```
