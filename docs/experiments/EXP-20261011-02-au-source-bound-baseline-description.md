# EXP-20261011-02：原來源 baseline 描述

狀態：**DESCRIPTIVE／PIT FLAG；無 candidate verdict**。Locked baseline commit：0328f13a9564c787837e3c4aa1cfff19235c9b0c。


這是 retrospective baseline 診斷，沒有候選、調參、KEEP／REJECT 或改善判決。計算前鎖定 `baseline_description_registration.json`（SHA256 105095774387bf4c05cea6c4a69f6055468d5f018b47fe40cf3baafc028c2746），使用原來源 serving dump bbf573f599ab6bbdfa9d8b9331a073876cdfa79713e50bfa5435d866498486af。

3,385 場中，1,879 場與 source-bound complete reported finish roster 完全相同：18,075 馬、57 賽日、2026-08-05 至 2026-10-10；1,506 場逐項保留排除原因。月份組成為 504／1,002／373 場；馬匹數 <=8／9–10／11–12／13+ 為 612／629／452／186 場。完整 finish roster 的選擇會排除 DNF／partial，不能代表全體 evaluation population。

Canonical Gold 373/1879（19.851%）、Good positional 491/1879（26.131%）、Pass 941/1879（50.080%）。這些是現存來源重算 baseline 的描述值；沒有 CI、候選差值或歷史 live accuracy 證明。完整 ranking 指標、exact source venue、actual serving going string 或 UNKNOWN cohorts 留在 JSON。

19 個 leaf 共 2,413 個 cohort 記錄；outcome AUC 僅限 08-05 至 09-26，保護 09-27 起既有 speed/class blind shadow。所有 finite score（包括 60）都保留，60 不自動當 missing。equal-race AUC 與 pair-pooled AUC 同時記錄。無候選排序或挑選最佳 leaf。random Gold expectation 是輔助描述，沒有取代 primary 指標。

PIT fit eligibility 仍未獲授予；不是證明所有歷史樣本無法恢復。Source capture、resource版本、官方 event cutoff、完整人口、CI／power 與 venue class taxonomy 仍需驗證。

重跑命令（先載入同目錄 environment.json）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/describe_original_serving_baseline.py
```

來源規格、input hashes、實際排除、各 cohort 組成及計算限制在 `baseline_description_registration.json`、`original_serving_baseline_description.json`、`describe_original_serving_baseline.py`、`original_serving_baseline_description.log`。不讀 blind candidate performance，不改 production 或判決規則。
