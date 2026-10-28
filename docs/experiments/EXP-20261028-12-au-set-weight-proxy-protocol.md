# EXP-20261028-12 預先登記：定磅賽唔再用負磅代理（§7 正確性修正）

> 量度之前寫。結果另寫 `EXP-20261028-12-au-set-weight-proxy-results.md`。

- **提出**：用戶 2026-10-28。Warwick Farm R1「ASAHI SUPER DRY PLATE」係定磅賽：59kg 4 歲閹馬、57kg 4 歲母馬、
  56.5kg 3 歲、54.5kg 3 歲雌馬 —— 負磅由年齡同性別定，但報告寫「讓磅賽由能力定磅，頂磅＝讓磅官評為能力最高」，
  而且照計入官方評分對位。
- **語料**：`scratch/au_fq_weight_class_dump_20261028.py`，乾淨窗 2026-08-05 起。

## 錯處（獨立可證，唔靠績效）

`_handicap_weight_proxy` 自己個 docstring 寫：負磅代理只喺**讓磅賽**有意義，定磅／WFA 賽「is refused」。
但 `_is_wfa_or_sw_race()` 只認 `wfa`／`sw`／`weight for age`／`set weights`／`maiden plate`。
淨係寫 `PLATE`、`QUALITY`、`STAKES`、`MAIDEN`（冇 handicap）、`QTIS` 等嘅場全部漏網，照用負磅代理。
即係 code 聲稱嘅行為同實際唔符 → 合約 §7。

## 候選

- **B1（§7）**：改成**正面認讓磅**：賽事名有 `handicap`／`hcp`／`hcap`／`benchmark`／`bm<數字>`／
  評分組別（`0 - 58`、`rating 0-64`、`rst`…）先當讓磅賽，用負磅代理；其他一律唔用（冇評分就只用級數代理）。
  分類規則喺睇結果前寫死喺 dump 嘅 `classify_title()`，結果檔會列每類場數。
- **B2（對照，唔係候選）**：只將 B1 嘅「明確定磅字眼」（plate／quality／stakes／maiden 冇 handicap／wfa／sw／set weight）
  剔走，冇字眼嘅贊助商名照舊用代理 —— 用嚟分開「修 regex」同「未知名稱當定磅」各自嘅影響。

報告文案：讓磅賽先寫「讓磅賽由能力定磅」；定磅賽唔再出負磅代理行。純顯示，跟 B1 一齊。

## 判決（§7）

上線條件全部要滿足：
1. 錯處獨立可證（上面）。
2. 零顯著退步：v3 fixed_rule 全紀錄 Gold／Good 冇顯著負；預先聲明分層（馬群大細 ×4、首選 SP ×5、
   **今場係咪代理場**）冇一個 CI 全負。
3. leakage audit PASS（賽事名係賽前資料）。
4. 結果檔明寫「呢個冇通過表現閘，唔係已證實改善」。

另跑 §8 做參考（改咗 leaf 資訊）—— 唔影響 §7 判決，但 refit arm 結果會照報。

## 診斷（唔做判決）

喺 B1 判定為定磅嘅場，負磅代理嘅預測力係咪其實係年齡／性別：分別報負磅代理、年齡、性別（雄 vs 雌）嘅場內配對 AUC。
如果負磅代理有料而且係年齡／性別帶出嚟，就另開登記測「年齡／性別」做正式特徵 —— **唔喺今次加**。

## 唔准做嘅嘢

睇完結果改分類字眼、改 B1 範圍、將 B2 當候選上線。

## 附註（量度前，2026-10-28）

睇 describe 嘅 title 樣本（未睇任何賽果判決）發現賽事名喺約 45 字截斷：「COUNTRY BOOSTED MAIDEN HANDI」、
「CG&amp;E MAIDEN HA」被判成定磅。`classify_title` 補兩樣：先 unescape `&amp;`；長度 ≥ 40 而尾字係
"handicap" 嘅前綴（≥ 2 字）當讓磅。另外語料有 4,359 匹賽事名係空白（舊 Logic），歸 `unknown`——
B1 會當佢哋唔係讓磅（冇負磅代理），B2 照舊。兩個 arm 嘅分別因此亦包括呢批空白名。
