# playtime-demo — 完整範例（示意假資料）

這是 2026-09-14 交付給 Lena 的樣張 `報告版型_風格B_現代儀表板_v3.html` 的 skill 版來源：
7 張圖、3 張表、60 個數字，全部改成宣告 ＋ 靜態資料，**不需要 numpy**。

```
python3 ../../scripts/build.py --md 報告內容.md --out out/
python3 ../../scripts/qa_html.py out/示意遊戲－平均遊戲時間下滑.html
```

預期（skill v1.1／v1.2）：`out/示意遊戲－平均遊戲時間下滑.html` 的 md5 ＝ `71e83fef226ba994fd81f62c0bfb5129`，qa_html 16 項全 OK。
（v1.2 沒動 JS／CSS，整檔 md5 與 v1.1 相同。）

與 2026-09-14 交付的 v3 樣張（＝ skill v1 重建結果，md5 `cd646e4371936fe656036712117adc53`）的關係：
- **去掉 `<script>` 區塊後兩者逐 byte 相同**（md5 `fb72619fbcf24188d2cb98f3f5a88632`）：`<style>` `84b3f2cef6…` 不變、7 張 SVG 逐張相同、正文相同。
- 只有 `<script>` 不同：v1.1 在 JS 末尾**新增**第 9 段（分群長條的圖例切換 handler，25 行），既有 1～8 段逐字元不變；
  md5 由 `4a73b94088…` 變成 `79e2d5b43d…`，`qa_html.py` 第 8 項的常數跟著更新。這一段只掛在 `data-kind="bar"` 且有
  `g.lgd[data-key]` 的圖上，本範例的 7 張圖都沒有，所以行為完全不受影響。

## 裡面有什麼

| 檔 | 內容 |
|---|---|
| `報告內容.md` | 全部文字 ＋ 10 個 ```figure／```table 區塊 ＋ 檔頭 12 個計算式數字 |
| `data/ts_break.csv` | 55 日 × 原始 mean／dow 校正／7 日平滑（圖 1-1，type line） |
| `data/band.csv` | 55 日 × p25/p50/p75/p90/mean（圖 2-1，line ＋ band） |
| `data/mixbar.csv` | 前後段 × 三段占比（圖 3-2，stacked100；瀑布 3-1 的四項直接寫在區塊 items） |
| `data/contrib.csv` | 六族群 × 段內／占比效應（圖 4-1，ranked） |
| `data/indexed.csv` | 55 日 × 三條指數（圖 5-1，line） |
| `data/dow.csv` | 星期 × 星期效應（圖 5-2，bars） |
| `data/tbl_*.csv` | 表 1-1／2-1／4-1（cell 用 `顯示@@排序值`） |
| `data/values.json` | 48 個手寫數字；另 12 個在 md 檔頭用計算式從圖資料算（前段平均、變化率、指數後段均值、星期效應極值…） |
| `data/_all_values_frozen.json` | 對照用：60 個數字原本（content_playtime.py）算出來的值 |

**數字全部是合成資料（seed 20260910），不可引用。** 這個範例的用途只有兩個：驗證 skill 沒改壞、給 Claude 看完整寫法。
