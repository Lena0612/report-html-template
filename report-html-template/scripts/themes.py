# -*- coding: utf-8 -*-
"""themes — 三種視覺風格。版型與 HTML 結構完全相同，差異全部在這裡。

    A 沉穩商務   襯線標題、白底、細線分隔、留白大、克制
    B 現代儀表板 無襯線、卡片化、淺灰底分區、結論做成數據卡、圓角
    C 編輯風     大標題、開頭粗體 lede、資訊密度高、章節數字大字標

顏色紀律（三種風格共用，不可各自發明）
    --up  #c62828  紅＝重點／漲
    --dn  #2e7d32  綠＝跌
    紅綠只用在方向語意（變化量、漲跌）與重點紅字；
    結論卡 tone 為人工指定；紅色同時代表「漲」與「重點」兩種語意，
    Lena 2026-09-10 決定維持原樣。
    類別／連續量一律中性藍灰（--cat1..3），避免與漲跌語意衝突。
    每個變化數字都自帶 ▲／▼ 與正負號 → 顏色不是唯一線索（紅綠色盲可讀）。
"""

# --------------------------------------------------------------------------
# 共用基礎：版面、行為、可讀性、列印。三種風格共用同一份（不要在這裡放風格）
# --------------------------------------------------------------------------
BASE = r"""
/* ============ 共用基礎（三種風格相同） ============ */
:root{
  --ink:#111111; --ink2:#555555; --ink3:#7a7a78;
  --up:#c62828; --dn:#2e7d32;                 /* 紅＝漲/重點  綠＝跌 */
  --up-bg:#fdeeee; --dn-bg:#eaf3ea;
  --cat1:#2f6f9f; --cat2:#7ba7c4; --cat3:#c2d3dd;   /* 類別＝中性藍 */
  --bg:#ffffff; --panel:#f7f7f5; --line:#e4e2de; --line2:#efeeec;
  --accent:#2f6f9f; --radius:0px; --docw:900px; --tocw:252px;
  /* 字級階層（v3 f）：H1 / H2 / H3 三級，靠「字級」拉開差距，
     不靠顏色或粗細硬撐。正文 16px 為基準，實際數值見各風格覆寫。 */
  --h1:36px; --h2:26px; --h3:20px;
  --f-body:"PingFang TC","Microsoft JhengHei","Noto Sans TC","Hiragino Sans",
           "Helvetica Neue",Arial,sans-serif;
  --f-head:var(--f-body);
  --f-num:"SF Mono",ui-monospace,Menlo,Consolas,var(--f-body);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-body);
     font-size:16px;line-height:1.85;letter-spacing:.01em;
     text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
p{margin:0 0 .85em}
a{color:var(--accent)}
strong{font-weight:700;color:var(--ink)}
h1,h2,h3{font-family:var(--f-head);color:var(--ink)}
.sr{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;
    overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.skip{position:absolute;left:-9999px}
.skip:focus{left:8px;top:8px;background:#fff;padding:6px 10px;z-index:99;
            border:1px solid var(--line)}
[id]{scroll-margin-top:22px}

/* ---- 骨架（目錄改成浮動圖示後，正文單欄置中） ---- */
/* v3 a：區塊加寬 → 容器最大寬度往上調、左右 padding 由 26px 縮到 18px，
   圖表的實際繪圖寬度從 ~780px 變成 ~1044px（風格 B）。 */
.shell{max-width:calc(var(--docw) + 36px);margin:0 auto;padding:0 18px}
.doc{max-width:var(--docw);margin:0 auto;padding:34px 0 60px}

/* ---- 目錄：右下角浮動圖示，hover／focus／tap 才展開 ---- */
/* 面板從按鈕往上、往左長，不蓋住正文閱讀區；scroll-spy 高亮照舊。 */
.toc{position:fixed;right:20px;bottom:20px;z-index:60;
     font-size:13.5px;line-height:1.5}
.toc-btn{display:flex;align-items:center;justify-content:center;
  width:46px;height:46px;padding:0;margin:0;cursor:pointer;border-radius:50%;
  background:#fff;border:1px solid var(--line);color:var(--ink2);font:inherit;
  box-shadow:0 2px 12px rgba(0,0,0,.16)}
.toc-btn:hover{border-color:var(--accent);color:var(--ink)}
.toc-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.toc-ico{display:flex;flex-direction:column;justify-content:center;gap:3.5px;
  width:18px;height:14px}
.toc-ico>i{display:block;height:2px;border-radius:2px;background:currentColor}
.toc-ico>i:nth-child(2){width:74%}
/* padding-bottom 是滑鼠從圖示移到面板的「橋」，避免中途 hover 斷掉 */
.toc-panel{position:absolute;right:0;bottom:100%;width:var(--tocw);
  padding-bottom:12px;opacity:0;visibility:hidden;transform:translateY(8px);
  pointer-events:none;
  transition:opacity .16s ease,transform .16s ease,visibility .16s}
.toc:hover .toc-panel,
.toc:focus-within .toc-panel,
.toc.is-open .toc-panel{opacity:1;visibility:visible;transform:none;
  pointer-events:auto}
.toc-card{display:flex;flex-direction:column;max-height:68vh;
  max-height:min(68vh,560px);background:#fff;border:1px solid var(--line);
  border-radius:12px;padding:10px 10px 8px;
  box-shadow:0 8px 30px rgba(0,0,0,.18)}
.toc-hd{display:flex;align-items:baseline;justify-content:space-between;
  gap:10px;padding:2px 6px 8px;border-bottom:1px solid var(--line)}
.toc-h{font-weight:700;letter-spacing:.16em;font-size:12px;color:var(--ink2)}
.toc-hint{font-size:11px;color:var(--ink3)}
.toc-body{min-height:0;overflow-y:auto;padding:8px 2px 0;
          scrollbar-width:thin}
.toc-list{list-style:none;margin:0;padding:0}
.toc-link{display:block;text-decoration:none;color:var(--ink2);
          padding:5px 8px 5px 10px;border-left:2px solid transparent}
.toc-l1{font-weight:600}
.toc-link:hover{color:var(--ink);background:var(--panel)}
.toc-link.is-cur{color:var(--ink);font-weight:700;
                 border-left-color:var(--accent);background:var(--panel)}
.toc-foot{margin:12px 8px 0;font-size:11.5px;color:var(--ink3);line-height:1.6}

/* ---- 標題區 ---- */
.head{padding:38px 0 22px;border-bottom:1px solid var(--line);position:relative}
.watermark{display:inline-block;margin:0 0 14px;padding:3px 9px;
           font-size:11.5px;font-weight:700;letter-spacing:.04em;
           color:var(--up);background:var(--up-bg);
           border:1px solid rgba(198,40,40,.28);border-radius:3px}
.kicker{margin:0 0 6px;font-size:12px;letter-spacing:.16em;color:var(--ink3)}
.title{margin:0 0 10px;font-size:var(--h1);line-height:1.28;
        font-weight:800;letter-spacing:.01em}
.subtitle{margin:0 0 14px;font-size:15px;color:var(--ink2)}
/* 資料說明：比正文小一號＋次要墨色，一行放在前言之下 */
.datanote{margin:16px 0 0;font-size:12.5px;line-height:1.75;color:var(--ink3)}
.dn-sep{margin:0 .2em 0 .35em;color:var(--ink3);opacity:.5}
.dn-k{color:var(--ink3)}
.dn-v{color:var(--ink2)}
.stylebadge{margin:10px 0 0;font-size:12px;color:var(--ink3)}
.verinfo{margin:16px 0 0;border:1px dashed var(--line);padding:8px 12px;
         font-size:13px;background:var(--panel)}
.verinfo>summary{cursor:pointer;color:var(--ink2);font-size:12.5px}
.verinfo-b{padding-top:8px;color:var(--ink2)}
.verinfo-b p{margin:0 0 .5em}

/* ---- 章節 ---- */
.sec{padding:30px 0 6px}
.sec-h{display:flex;align-items:baseline;gap:12px;margin:0 0 12px;
       font-size:var(--h2);font-weight:700;line-height:1.4}
/* 區塊標頭的 inline SVG icon（結論／建議）：跟著字級縮放、用 currentColor */
.sec-ico{flex:0 0 auto;display:inline-flex;align-self:center;
         width:1.06em;height:1.06em;color:var(--accent)}
.sec-ico svg{width:100%;height:100%;display:block}
.sec-key .sec-ico{color:var(--up)}
/* 子節（H3）：比區塊標頭明顯小一階、比正文明顯大一階 */
.sub-h{margin:22px 0 8px;font-size:var(--h3);font-weight:700;line-height:1.45;
       letter-spacing:.01em}
.sub-h+p,.sub-h+ul{margin-top:0}
.ch-num{font-variant-numeric:tabular-nums;color:var(--accent);font-weight:700}
.ch-num:empty{display:none}
.sec-lead{margin:0 0 16px;font-size:13.5px;color:var(--ink2)}
/* 章首結論：小標之後、說明文字之前，粗體＋左側色條與一般段落區隔 */
.ch-key{margin:0 0 14px;padding:1px 0 1px 14px;border-left:4px solid var(--up);
        font-size:16px;font-weight:700;line-height:1.75;color:var(--ink)}
.ch-key-k{display:inline-block;margin-right:9px;padding:1px 7px;
          font-size:11.5px;font-weight:700;letter-spacing:.06em;color:#fff;
          background:var(--up);vertical-align:.09em}
.lede{font-size:17px;line-height:1.8}
.bul{margin:0 0 1em;padding-left:1.25em}
.bul li{margin:.3em 0}

/* ---- 結論 ---- */
.concl{list-style:none;margin:0;padding:0}
.concl-i{display:grid;grid-template-columns:auto 1fr;gap:14px;
         padding:14px 0;border-top:1px solid var(--line)}
.concl-i:last-child{border-bottom:1px solid var(--line)}
.concl-n{font-variant-numeric:tabular-nums;font-weight:700;color:var(--accent);
         font-size:15px;line-height:1.8}
.concl-b{font-size:16.5px;line-height:1.8}

/* ---- 建議 ---- */
.rec{list-style:none;margin:0;padding:0;counter-reset:r}
.rec-i{padding:14px 0;border-top:1px solid var(--line)}
.rec-i:last-child{border-bottom:1px solid var(--line)}
.rec-h{display:flex;gap:12px;align-items:baseline}
.rec-n{font-variant-numeric:tabular-nums;font-weight:700;color:var(--accent)}
.rec-a{font-weight:700;font-size:16px;flex:1 1 auto}
.rec-tag{flex:0 0 auto;font-size:11.5px;color:var(--ink3);
         border:1px solid var(--line);padding:1px 7px;border-radius:99px}
.rec-m{margin:6px 0 0 26px;font-size:13.5px;color:var(--ink2)}
.rec-kv{display:flex;gap:10px;margin:2px 0}
.rec-k{flex:0 0 66px;color:var(--ink3);font-size:12.5px}
.rec-v{flex:1 1 auto}

/* ---- 圖／表 ---- */
.blk{margin:22px 0 26px}
figure.blk{padding:0}
.cap{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;
     margin:0 0 8px;font-size:14px;line-height:1.5}
.cap-no{flex:0 0 auto;font-weight:700;color:var(--accent);
        font-variant-numeric:tabular-nums;letter-spacing:.02em}
.cap-t{font-weight:600;color:var(--ink)}
.tbl-hint{flex:0 0 auto;margin-left:auto;font-size:11.5px;color:var(--ink3)}
.fig-img{margin:0;background:transparent}
.fig-img img{display:block;width:100%;height:auto}
/* 圖表備註：維度定義／指標定義／著色含義（v3 e：一般小字，不反白、無底色） */
.blk-def{margin:8px 0 0;font-size:12px;line-height:1.6;color:var(--ink2)}
.def-r{display:flex;gap:8px;margin:1px 0}
.blk-def dt{flex:0 0 2.6em;margin:0;color:var(--ink3)}
.blk-def dd{flex:1 1 auto;margin:0}
.blk-note{margin:6px 0 0;font-size:12px;color:var(--ink3);line-height:1.65}
.blk-read{margin:8px 0 0;font-size:13.5px;color:var(--ink2);line-height:1.75}
.read-k{display:inline-block;margin-right:8px;padding:0 6px;font-size:11.5px;
        font-weight:700;color:var(--ink2);background:var(--panel);
        border:1px solid var(--line)}
.xref{color:var(--accent);text-decoration:none;font-weight:600;
      border-bottom:1px solid rgba(47,111,159,.35);
      white-space:nowrap;font-variant-numeric:tabular-nums}
.xref:hover{border-bottom-color:var(--accent);background:var(--panel)}

/* ---- 表格 ---- */
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.data{width:100%;border-collapse:collapse;font-size:13.5px;
           font-variant-numeric:tabular-nums}
table.data th,table.data td{padding:7px 10px;border-bottom:1px solid var(--line2);
                            text-align:left;white-space:nowrap}
table.data td[data-al=right],table.data th[data-al=right]{text-align:right}
table.data td[data-al=center],table.data th[data-al=center]{text-align:center}
table.data thead th{border-bottom:1.5px solid var(--line);font-size:12.5px;
                    color:var(--ink2);font-weight:700;background:var(--panel)}
table.data tbody th{font-weight:600;white-space:nowrap}
table.data th.s{cursor:pointer;user-select:none;-webkit-user-select:none}
table.data th.s:hover{color:var(--ink)}
.sort-ind{display:inline-block;width:1em;margin-left:4px;color:var(--ink3);
          font-size:11px}
.sort-ind::after{content:"\2195";opacity:.4}
th[aria-sort=ascending] .sort-ind::after{content:"\2191";opacity:1}
th[aria-sort=descending] .sort-ind::after{content:"\2193";opacity:1}
table.data tbody tr:hover{background:var(--panel)}
table.data tr.emph th,table.data tr.emph td{font-weight:700;color:var(--ink);
                                            background:var(--panel)}

/* ---- 數字與方向（紅漲綠跌＋▲▼，顏色不是唯一線索） ---- */
.chg{white-space:nowrap;font-weight:700;font-variant-numeric:tabular-nums}
.chg.up{color:var(--up)}
.chg.dn{color:var(--dn)}
.chg.flat{color:var(--ink2)}
.chg-a{font-size:.8em;margin-right:.1em;vertical-align:.04em}
.chg-u{font-weight:400;margin-left:.15em;font-size:.92em}
.num{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--ink);
     font-weight:600}
.hl{color:var(--up);font-weight:700}
/* 反引號內容：等寬字、略小；刻意不加底色（e：內文不要反白） */
code{font-family:var(--f-num);font-size:.92em;letter-spacing:0}

/* ---- 摺疊 ---- */
details.fold{margin:14px 0;border:1px solid var(--line);padding:10px 14px;
             background:var(--panel)}
details.fold>summary{cursor:pointer;font-size:13.5px;font-weight:600;
                     color:var(--ink2)}
details.fold[open]>summary{margin-bottom:8px;padding-bottom:6px;
                           border-bottom:1px solid var(--line)}
.fold-b{font-size:13.5px;color:var(--ink2)}
.fold-b p{margin:0 0 .6em}

.foot{margin:40px 0 0;padding:14px 0 0;border-top:1px solid var(--line);
      font-size:12px;color:var(--ink3)}
.foot-t{margin:0}
.pagemark{display:none}

/* ============ 互動圖表（手寫 inline SVG，零外部函式庫） ============ */
/* SVG 不吃 var()，所有顏色都在這裡用 class 給 → 三種風格的圖表標記完全相同 */
.chart{display:block;width:100%;height:auto;font-family:var(--f-body)}
.chart text{fill:var(--ink2)}
.chart .lb{font-size:15px}
.chart .yl,.chart .xl,.chart .bl,.chart .sh{fill:var(--ink3)}
.chart .ax,.chart .hd{font-size:13.5px;fill:var(--ink3)}
.chart .bl{font-size:15px}
.chart .sh{font-size:14.5px}
.chart .cum{font-weight:700;fill:var(--ink2)}
.chart .an,.chart .hint{font-size:13px;fill:var(--ink3)}
.chart .grid{stroke:var(--line2);stroke-width:1}
.chart .axis{stroke:var(--line);stroke-width:1.2}
.chart .conn{stroke:var(--line);stroke-width:1;stroke-dasharray:3 3}
.chart .bkband{fill:rgba(17,17,17,.05)}
.chart .bkline{stroke:var(--ink2);stroke-width:1.4;stroke-dasharray:6 5}
.chart .ser{fill:none;stroke-linejoin:round;stroke-linecap:round}
.chart .band{stroke:none}
.chart .ref{stroke:var(--ink);stroke-width:1.5;stroke-dasharray:8 5}
/* 序列色：類別／連續量一律中性藍灰；紅綠只留給方向語意 */
.chart .c-raw{stroke:#c8c6c1}
.chart .c-s1{stroke:var(--cat1)}
.chart .c-s2{stroke:var(--cat2)}
.chart .c-s3{stroke:#98a1a8}
.chart .c-ink{stroke:var(--ink)}
.chart .c-q{stroke:var(--cat1)}
.chart rect.c-s1,.chart polygon.c-s1{fill:var(--cat1);stroke:none}
.chart rect.c-s2,.chart polygon.c-s2{fill:var(--cat2);stroke:none}
.chart rect.c-s3,.chart polygon.c-s3{fill:var(--cat3);stroke:none}
.chart rect.c-band,.chart polygon.c-band{fill:rgba(47,111,159,.22);stroke:none}
.chart rect.c-neu{fill:#bab8b3}
.chart rect.c-up{fill:var(--up)}
.chart rect.c-dn{fill:var(--dn)}
.chart rect.c-dn2{fill:#8ebd92}
.chart line.sw{fill:none}
.chart rect.sw.c-band{fill:rgba(47,111,159,.34);stroke:var(--cat1);
  stroke-width:1}
.chart .inseg{font-size:14.5px;font-weight:700;fill:var(--ink)}
.chart .inseg.on-dark{fill:#ffffff}
.chart .vl,.chart .refl,.chart .lgt{font-size:16px;font-weight:700;fill:var(--ink)}
.chart .refl{font-size:14.5px}
.chart .bkl{font-weight:700;fill:var(--ink2)}
/* 疊在資料線上的標籤：白色描邊墊底，線再密也讀得到 */
.chart .refl,.chart .bkl{paint-order:stroke;stroke:#ffffff;stroke-width:3.5;
  stroke-linejoin:round}
.chart .c-up-t{fill:var(--up)}
.chart .c-dn-t{fill:var(--dn)}
/* 互動層：靜態存在、預設隱藏，JS 只移動它 */
.chart rect.hit{fill:transparent;stroke:none}
.chart g.mark rect.bar{transition:opacity .1s}
.chart g.mark.hot rect.bar{opacity:.75;stroke:var(--ink);stroke-width:1.2}
.chart g.lgd[data-key]{cursor:pointer}
.chart g.lgd.static{cursor:default}
.chart g.lgd.off .lgt{opacity:.42;text-decoration:line-through}
.chart g.lgd.off .sw{opacity:.28}
.chart .ser.off,.chart .band.off{opacity:0;pointer-events:none}
.chart .crosshair{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3;
                  opacity:0}
.chart .crosshair.on{opacity:.85}
.chart circle.focus{opacity:0;stroke:#ffffff;stroke-width:1.6}
.chart circle.focus.on{opacity:1}
.chart circle.focus.c-raw{fill:#c8c6c1;stroke:#fff}
.chart circle.focus.c-s1,.chart circle.focus.c-q,
.chart circle.focus.c-band{fill:var(--cat1);stroke:#fff}
.chart circle.focus.c-s2{fill:var(--cat2);stroke:#fff}
.chart circle.focus.c-s3{fill:#98a1a8;stroke:#fff}
.chart circle.focus.c-ink{fill:var(--ink);stroke:#fff}
.scroll-hint{display:none}
/* tooltip：白底墨字，紅綠在白底才有足夠對比 */
.chart-tip{position:fixed;left:0;top:0;z-index:120;pointer-events:none;
  opacity:0;transition:opacity .1s;background:#fff;color:var(--ink);
  border:1px solid var(--line);border-radius:8px;padding:8px 10px;
  box-shadow:0 4px 16px rgba(0,0,0,.16);font-size:13px;line-height:1.6;
  min-width:140px;max-width:290px;font-variant-numeric:tabular-nums;
  font-family:var(--f-body)}
.chart-tip.on{opacity:1}
.tip-t{font-weight:700;margin-bottom:3px;padding-bottom:3px;
  border-bottom:1px solid var(--line2)}
.tip-r{display:flex;gap:16px;justify-content:space-between}
.tip-k{color:var(--ink2);white-space:nowrap}
.tip-v{font-weight:700;white-space:nowrap}
.tip-v.up{color:var(--up)}
.tip-v.dn{color:var(--dn)}

/* ---- 窄螢幕（~400px 可讀）：目錄收成頂部可展開 ---- */
@media (max-width:900px){
  /* 手機一律保留 16px 側邊留白（v3 a 的下限） */
  .shell{padding:0 16px;max-width:none}
  .toc{right:12px;bottom:12px}
  .toc-panel{width:min(78vw,252px)}
  .toc-card{max-height:64vh}
  .doc{max-width:none;padding:18px 0 44px}
  /* 字級階層等比縮小，H1/H2/H3 的級差在窄螢幕照樣看得出來 */
  .title{font-size:calc(var(--h1) * .78)}
  .sec-h{font-size:calc(var(--h2) * .82)}
  .sub-h{font-size:calc(var(--h3) * .9)}
  body{font-size:15.5px;line-height:1.8}
  .concl-b{font-size:15.5px}
  table.data{min-width:600px}
  .datanote{font-size:12px}
}
/* 窄螢幕的圖：字若跟著縮會讀不到 → 維持最小寬度、讓圖自己橫向捲動。
   最小寬度隨 viewBox（1000→1120）等比上調，有效字級與 v2 相同。 */
@media (max-width:760px){
  .fig-img{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .chart{min-width:718px}
  .scroll-hint{display:block;margin-top:5px;font-size:11px;color:var(--ink3)}
}
@media (max-width:430px){
  .shell{padding:0 16px}
  .title{font-size:calc(var(--h1) * .66)}
  .sec-h{font-size:calc(var(--h2) * .74)}
  .sub-h{font-size:calc(var(--h3) * .85)}
  .lede{font-size:16px}
  .rec-m{margin-left:0}
  .rec-k{flex-basis:58px}
  .chart{min-width:672px}
}

/* ---- 列印／轉 PDF ---- */
@media print{
  @page{margin:14mm 13mm}
  html,body{background:#fff!important;font-size:10.5pt;line-height:1.6}
  .toc,.skip,.foot,.tbl-hint,.sort-ind,.toc-hint{display:none!important}
  .toc{display:none!important}          /* 右下角浮動目錄：紙上整個不出現 */
  .shell{display:block;max-width:none;padding:0}
  .doc{max-width:none;padding:0}
  .head{padding-top:0}
  a{color:inherit!important;text-decoration:none}
  .xref{border-bottom:0;font-weight:700}
  .sec,.blk,figure.blk,.tbl,.concl-i,.rec-i,details.fold,.verinfo,
  table.data tr,.sec-h,.sub-h,.ch-key{break-inside:avoid;page-break-inside:avoid}
  .sub-h{break-after:avoid;page-break-after:avoid}
  .ch-key{break-after:avoid;page-break-after:avoid}
  .sec-h{break-after:avoid;page-break-after:avoid}
  .cap{break-after:avoid;page-break-after:avoid}
  .sec{padding-top:16px}
  .fig-img img{max-width:100%;max-height:88vh}
  table.data{min-width:0}
  table.data tbody tr:hover{background:transparent}
  .pagemark{display:block;position:fixed;right:0;bottom:0;font-size:8pt;
            color:var(--up);letter-spacing:.04em}
  details.fold,.verinfo{background:transparent}
  /* 圖：列印時互動層全部收掉、被關掉的序列強制顯示（紙上不能有缺線） */
  .chart-tip{display:none!important}
  .chart .crosshair,.chart circle.focus,.chart .hint{display:none!important}
  .chart .ser.off,.chart .band.off{opacity:1!important}
  .chart g.lgd.off .lgt,.chart g.lgd.off .sw{opacity:1!important;
    text-decoration:none!important}
  .fig-img{overflow:visible!important}
  .chart{min-width:0!important}
  .scroll-hint{display:none!important}
}
"""

# --------------------------------------------------------------------------
# A 沉穩商務
# --------------------------------------------------------------------------
THEME_A = r"""
/* ============ 風格 A：沉穩商務（襯線標題、白底、細線、留白大） ============ */
.theme-a{
  --f-head:"Songti TC","Noto Serif TC","Source Han Serif TC","Songti SC",
           PMingLiU,"Times New Roman",Georgia,serif;
  --accent:#33506b; --line:#e2e0da; --line2:#eceae4; --panel:#f8f7f4;
  --bg:#ffffff;
}
.theme-a .shell{gap:44px}
.theme-a .doc{padding:44px 0 72px}
.theme-a .head{padding:56px 0 26px;border-bottom:2px solid #33506b}
.theme-a .kicker{font-family:var(--f-head);letter-spacing:.3em;font-size:11.5px}
.theme-a .title{font-size:38px;font-weight:600;letter-spacing:.02em;
                line-height:1.35}
.theme-a .subtitle{font-family:var(--f-head);font-size:15.5px}
.theme-a .datanote{border-top:1px solid var(--line);padding-top:12px}
.theme-a .sec{padding:44px 0 8px}
.theme-a .sec-h{font-size:24px;font-weight:600;padding-bottom:10px;
                border-bottom:1px solid var(--line);letter-spacing:.03em}
.theme-a .ch-num{font-family:var(--f-head);font-size:20px;font-weight:600;
                 color:var(--accent)}
.theme-a .ch-num::after{content:"．";color:var(--line)}
.theme-a .lede{font-family:var(--f-head);font-size:18px;line-height:1.95;
               color:var(--ink)}
/* 結論：全篇最顯眼 → 上下雙細線＋加大字級＋留白 */
.theme-a .sec-key{padding:44px 0 20px}
.theme-a .sec-key .sec-h{border-bottom:3px double var(--accent)}
.theme-a .concl{margin-top:6px}
.theme-a .concl-i{padding:18px 0;gap:18px}
.theme-a .concl-n{font-family:var(--f-head);font-size:17px;
                  min-width:1.5em;text-align:right}
.theme-a .concl-b{font-size:17.5px;line-height:1.85}
.theme-a .rec-i{padding:18px 0}
.theme-a .rec-a{font-size:16.5px;font-weight:600}
.theme-a .cap-no{font-family:var(--f-head)}
.theme-a .cap{padding-bottom:6px;border-bottom:1px solid var(--line2)}
.theme-a .blk{margin:30px 0 34px}
.theme-a .fig-img{padding:6px 0}
.theme-a table.data thead th{background:transparent;
                             border-bottom:1.5px solid var(--accent)}
.theme-a table.data th,.theme-a table.data td{padding:8px 12px}
.theme-a .read-k{background:transparent;border:0;border-left:2px solid var(--accent);
                 color:var(--accent);font-family:var(--f-head)}
.theme-a .toc-h{font-family:var(--f-head);letter-spacing:.3em}
.theme-a .toc-link.is-cur{background:transparent;border-left-width:3px}
.theme-a details.fold{background:transparent;border:0;
                      border-top:1px solid var(--line);
                      border-bottom:1px solid var(--line);padding:10px 0}
.theme-a .verinfo{background:transparent}
"""

# --------------------------------------------------------------------------
# B 現代儀表板
# --------------------------------------------------------------------------
THEME_B = r"""
/* ============ 風格 B：現代儀表板（卡片化、淺灰底、結論做成數據卡） ============ */
.theme-b{
  --accent:#2f6f9f; --radius:14px; --bg:#eef1f4; --panel:#f5f7f9;
  --line:#dfe4ea; --line2:#e9edf1;
  /* v3 a：880 → 1120px，配合 .sec/.blk/.fig-img 的 padding 縮小，
     圖的實際繪圖寬度 780px → 1044px（viewBox 1120，縮放比 ~0.93） */
  --docw:1120px;
  /* v3 f：字級階層 H1 38 / H2 27 / H3 20 / 正文 16（px），級差 11 / 7 / 4 */
  --h1:38px; --h2:27px; --h3:20px;
}
.theme-b{background:var(--bg)}
.theme-b .doc{padding:22px 0 56px}
.theme-b .head,.theme-b .sec{background:#fff;border:1px solid var(--line);
  border-radius:var(--radius);padding:22px 20px;margin:0 0 14px;
  box-shadow:0 1px 2px rgba(16,32,48,.05)}
.theme-b .head{padding:26px 20px 22px;border-bottom:1px solid var(--line);
  border-top:4px solid var(--accent)}
.theme-b .title{font-size:var(--h1);font-weight:800;letter-spacing:-.015em}
.theme-b .kicker{font-weight:700;color:var(--accent);letter-spacing:.12em}
.theme-b .datanote{margin-top:14px;padding-top:12px;
                   border-top:1px solid var(--line2)}
/* 章節標頭沿用 C（編輯風）：大號章節序號當視覺定位點，其餘維持 B 的卡片化 */
.theme-b .sec-h{font-size:var(--h2);font-weight:800;letter-spacing:-.01em;
  align-items:flex-start;gap:14px;margin:0 0 10px}
.theme-b .sub-h{font-size:var(--h3);font-weight:700;color:var(--ink);
  padding-left:11px;border-left:3px solid var(--line)}
.theme-b .sec-ico{align-self:flex-start;margin-top:.06em}
.theme-b .ch-num{display:inline-block;min-width:0;height:auto;padding:0;
  border-radius:0;background:transparent;color:#c3d0da;
  font-size:52px;line-height:.78;font-weight:800;letter-spacing:-.04em}
.theme-b .sec-h .sec-t{padding-top:3px}
/* 結論：做成數據卡 */
.theme-b .sec-key{border-top:4px solid var(--up);background:#fff}
.theme-b .sec-key .sec-h::after{content:"最重要";margin-left:8px;padding:2px 8px;
  font-size:11px;font-weight:700;color:var(--up);background:var(--up-bg);
  border-radius:99px;letter-spacing:.02em}
.theme-b .concl{display:grid;gap:12px;
  grid-template-columns:repeat(auto-fit,minmax(268px,1fr))}
.theme-b .concl-i{border:1px solid var(--line);border-top:3px solid var(--accent);
  border-radius:12px;padding:14px 16px;background:var(--panel);gap:10px;
  align-content:start}
.theme-b .concl-i:last-child{border-bottom:1px solid var(--line)}
/* 結論卡 tone 為人工指定（內容檔的 [up]／[dn]／留空），不做自動判斷；
   紅色同時代表「漲」與「重點」兩種語意，Lena 2026-09-10 決定維持原樣。 */
.theme-b .concl-i.tone-up{border-top-color:var(--up)}
.theme-b .concl-i.tone-dn{border-top-color:var(--dn)}
.theme-b .concl-n{display:inline-flex;align-items:center;justify-content:center;
  width:22px;height:22px;border-radius:7px;background:#fff;
  border:1px solid var(--line);font-size:12.5px;line-height:1;color:var(--ink2)}
.theme-b .concl-b{font-size:15.5px;line-height:1.75}
.theme-b .rec{display:grid;gap:10px}
.theme-b .rec-i{border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;background:var(--panel)}
.theme-b .rec-i:last-child{border-bottom:1px solid var(--line)}
.theme-b .rec-n{display:inline-flex;align-items:center;justify-content:center;
  width:22px;height:22px;border-radius:99px;background:var(--accent);color:#fff;
  font-size:12.5px;line-height:1}
.theme-b .rec-tag{background:#fff}
.theme-b .rec-m{margin-left:34px}
.theme-b .rec-kv{background:#fff;border:1px solid var(--line2);border-radius:8px;
  padding:4px 10px;margin:4px 0}
.theme-b .ch-key{background:var(--panel);border:1px solid var(--line2);
  border-left:4px solid var(--up);border-radius:10px;padding:10px 14px;
  margin:0 0 12px}
.theme-b .ch-key-k{border-radius:5px}
.theme-b .blk{border:1px solid var(--line2);border-radius:12px;padding:14px 12px;
  background:var(--panel);margin:16px 0}
.theme-b .fig-img{background:#fff;border-radius:8px;padding:6px}
.theme-b .cap-no{padding:1px 7px;border-radius:6px;background:var(--accent);
  color:#fff;font-size:12px}
.theme-b .tablewrap{background:#fff;border-radius:8px;
  border:1px solid var(--line2)}
.theme-b table.data thead th{background:#fff;
  border-bottom:1.5px solid var(--accent);position:sticky;top:0}
/* v3 e：圖表備註（維度／指標／著色）與母體註腳都不反白、不加底色，
   只是一般小字；只有「判讀」的標籤還是膠囊，那是標籤不是備註。 */
.theme-b .read-k{background:#fff;border-radius:6px}
/* 紅綠數字：只有文字顏色與 ▲▼，不加淡色底（淡色底只留給重點字 .hl） */
.theme-b .hl{background:var(--up-bg);padding:0 3px;border-radius:4px}
.theme-b .toc-card{border-radius:var(--radius)}
.theme-b .toc-btn{border-color:var(--accent);color:var(--accent)}
.theme-b .toc-link{border-radius:8px;border-left:2px solid transparent}
.theme-b .toc-link.is-cur{background:#eaf1f7}
.theme-b details.fold{border-radius:10px;background:#fff}
.theme-b .foot{border-top:0}
@media (max-width:900px){
  .theme-b .head,.theme-b .sec{border-radius:12px;padding:18px 14px}
  .theme-b .ch-num{font-size:38px}
  .theme-b .concl{grid-template-columns:1fr}
  .theme-b table.data thead th{position:static}
}
@media print{
  .theme-b{background:#fff}
  .theme-b .head,.theme-b .sec,.theme-b .blk,.theme-b .concl-i,.theme-b .rec-i,
  .theme-b .rec-kv,.theme-b .ch-key{box-shadow:none;background:#fff}
  .theme-b table.data thead th{position:static}
  .theme-b .concl{grid-template-columns:1fr 1fr}
}
"""

# --------------------------------------------------------------------------
# C 編輯風
# --------------------------------------------------------------------------
THEME_C = r"""
/* ============ 風格 C：編輯風（大標題、粗體 lede、密度高、數字大字標） ============ */
.theme-c{
  --accent:#111111; --line:#d8d6d1; --line2:#e7e5e0; --panel:#f4f2ee;
  --bg:#fbfaf7; --docw:790px;
}
.theme-c{background:var(--bg)}
.theme-c body,.theme-c .doc{line-height:1.72}
.theme-c .doc{padding:26px 0 60px}
.theme-c .head{padding:30px 0 18px;border-bottom:4px solid var(--ink)}
.theme-c .kicker{font-weight:800;letter-spacing:.2em;font-size:11px;
  color:var(--up)}
.theme-c .title{font-size:46px;font-weight:800;line-height:1.15;
  letter-spacing:-.02em;margin-bottom:12px}
.theme-c .subtitle{font-size:14px;font-weight:700;letter-spacing:.02em}
.theme-c .datanote{font-size:11.5px;padding-top:8px;
  border-top:1px solid var(--line)}
.theme-c .sec{padding:26px 0 4px;border-top:1px solid var(--line)}
.theme-c .sec:first-of-type{border-top:0}
.theme-c .sec-h{font-size:26px;font-weight:800;letter-spacing:-.01em;
  align-items:flex-start;gap:14px;margin-bottom:8px}
.theme-c .ch-num{font-size:52px;line-height:.78;font-weight:800;
  color:var(--line);letter-spacing:-.04em}
/* lede：開頭一欄粗體摘要 */
.theme-c .lede{font-size:19.5px;font-weight:700;line-height:1.6;
  letter-spacing:-.005em;padding-left:16px;border-left:5px solid var(--ink);
  margin-bottom:16px}
.theme-c .sec-lead{font-size:12.5px;text-transform:none;
  padding-bottom:8px;border-bottom:1px solid var(--line2)}
/* 結論：黑底標題條＋粗體條列，最顯眼 */
.theme-c .sec-key{border-top:3px solid var(--ink)}
.theme-c .sec-key .sec-h{background:var(--ink);color:#fff;padding:8px 12px;
  margin:0 0 10px;font-size:22px}
.theme-c .sec-key .sec-h .ch-num{display:none}
.theme-c .sec-key .sec-h .sec-t{color:#fff;letter-spacing:.06em}
.theme-c .concl-i{padding:9px 0;gap:12px;border-top:1px solid var(--line2)}
.theme-c .concl-n{font-size:20px;font-weight:800;color:var(--ink);
  min-width:1.3em;text-align:right;line-height:1.5}
.theme-c .concl-b{font-size:16px;font-weight:600;line-height:1.68}
.theme-c .rec-i{padding:10px 0;border-top:1px solid var(--line2)}
.theme-c .rec-n{font-size:18px;font-weight:800;color:var(--ink)}
.theme-c .rec-a{font-size:15.5px}
.theme-c .rec-m{margin:4px 0 0 30px;font-size:12.5px}
.theme-c .rec-k{font-size:11.5px;letter-spacing:.06em}
.theme-c .blk{margin:16px 0 18px}
.theme-c .cap{gap:8px;margin-bottom:6px;font-size:13px;
  padding-bottom:4px;border-bottom:2px solid var(--ink)}
.theme-c .cap-no{color:var(--up);letter-spacing:.04em}
.theme-c .cap-t{font-weight:700}
.theme-c .blk-note{font-size:11.5px;line-height:1.55;padding-top:4px;
  border-top:1px solid var(--line2)}
.theme-c .blk-read{font-size:13px;background:var(--panel);padding:8px 10px}
.theme-c .read-k{background:var(--ink);color:#fff;border:0}
.theme-c table.data{font-size:12.5px}
.theme-c table.data th,.theme-c table.data td{padding:5px 8px}
.theme-c table.data thead th{background:var(--ink);color:#fff;
  border-bottom:0;font-size:11.5px}
.theme-c table.data thead th.s:hover{color:#fff;text-decoration:underline}
.theme-c .sort-ind{color:#fff}
.theme-c .toc-h{font-weight:800;letter-spacing:.2em}
.theme-c .toc-card{border-top:3px solid var(--ink);border-radius:2px}
.theme-c .toc-link{padding:4px 8px}
.theme-c .toc-link.is-cur{background:var(--ink);color:#fff;
  border-left-color:var(--up)}
.theme-c .xref{color:var(--up);border-bottom-color:rgba(198,40,40,.4)}
.theme-c details.fold{background:transparent;border:0;border-top:2px solid var(--ink);
  padding:8px 0}
@media (max-width:900px){
  .theme-c .title{font-size:32px}
  .theme-c .sec-h{font-size:22px}
  .theme-c .ch-num{font-size:38px}
  .theme-c .lede{font-size:17px}
}
@media print{
  .theme-c{background:#fff}
  .theme-c .sec-key .sec-h{background:#fff;color:var(--ink);
    border-top:3px solid var(--ink);border-bottom:3px solid var(--ink);
    padding:6px 0}
  .theme-c .sec-key .sec-h .sec-t{color:var(--ink)}
  .theme-c table.data thead th{background:var(--panel);color:var(--ink)}
  .theme-c .read-k{background:var(--panel);color:var(--ink)}
  .theme-c .toc-link.is-cur{background:transparent;color:var(--ink)}
}
"""

THEMES = {"A": THEME_A, "B": THEME_B, "C": THEME_C}
LABELS = {"A": "沉穩商務", "B": "現代儀表板", "C": "編輯風"}


def build_css(theme):
    t = theme.upper()
    if t not in THEMES:
        raise KeyError(f"未知風格：{theme}（可用 {sorted(THEMES)}）")
    return (BASE.strip() + "\n" + THEMES[t].strip() + "\n")
