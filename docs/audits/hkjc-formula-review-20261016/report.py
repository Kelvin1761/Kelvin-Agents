"""Render the compact review and per-hypothesis experiment records."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    result = json.loads((HERE / "results.json").read_text())
    study = result["study"]
    names = {"no_form": "近績分設60", "no_consistency": "穩定性分設60",
             "rank67_equal45": "第六七名近績分40→60", "top3_margin": "亞季輸逾3位按輸距減close credit",
             "fallback_same_scale": "缺詳情套用同一穩定性公式",
             "sectional": "段速", "trainer_signal": "騎練", "stability": "狀態穩定",
             "race_shape": "檔位走位", "class_advantage": "級數", "horse_health": "健康",
             "form_line": "賽績線", "trackwork": "晨操", "distance_fit": "同程"}

    def table(arms):
        lines = ["| 測試 | 改排名場數 | Gold 差（場） | Good 差（場） | NDCG@5 差 |", "|---|---:|---:|---:|---:|"]
        for arm in arms:
            a = study["arms"][arm]
            m = a["metrics"]
            label = names.get(arm, names.get(arm.removeprefix("neutral_"), arm))
            lines.append(f"| {label} | {a['changed_races']} | {round(m['gold']['delta']*325):+d} | {round(m['good_positional']['delta']*325):+d} | {m['ndcg_at5']['delta']:+.6f} |")
        return "\n".join(lines)

    text = """# HKJC 全公式審查及狀態穩定性測試

結論：保留九維權重、近績與穩定性配方。修正 consistency 將 0 名次當作已完成賽績嘅解析錯誤；
修正模型說明漏列 SIP、將 60 一律等同缺資料、現役九維仍寫成七維嘅描述。
呢個冇通過表現閘，唔係一個已證實嘅改善。0 名次改動按評估合約 §7 正確性修正處理。

## 語料與把尺

- baseline `dd22b05d`，2026-04-12 至 2026-10-07；351 場可發現紀錄。
- 6 場 production 評分失敗，20 場來自 speed_score 全死賽日，最後 **325 場／33 賽日／4,101 次出賽**。
- baseline Gold **44/325（13.54%）**；Good **81/325（24.92%）**。
- Gold = 實際前三全部喺模型頭四；Good = 模型頭兩揀都上名。
- 真 production orchestrator + 賽日前 PIT 騎練統計；只讀原始 artifact，禁止寫回存檔／部署。
- A/A 325/325 場逐匹 raw score、逐位排名完全相同；重新執行 SIP 同全場檔位限幅。
- 原先固定五個 arm 同一 stability 家族，Holm 調整；賽日 bootstrap 2000 次、六時間塊。
- 統計 screen 按 v3。全 archive 衍生欄位仍有 provenance FLAG，不能由 PIT aggregate 或日期檢查推定全模型無洩漏。
- 2026-10-11 起嘅**賽果**無用作候選評估，保留既有 forward 確認用途。操作性 data_contract 校準只讀特徵，不讀賽果。

## 四個討論點

""" + table(["no_form", "no_consistency", "rank67_equal45", "top3_margin", "fallback_same_scale"]) + """

1. **重疊**：場內中心化 F/C 相關 r=0.788；非60值樣本嘅場內 AUC 分別0.672、0.653。
   有重疊唔等於可以剷。no_form Good −3.38pp，未調整95% CI [−5.95, −0.32]；
   Holm 家族調整後不宣稱顯著發現。no_consistency Good 0pp，CI [−1.83,+1.58]，無法證明冇價值。
2. **名次粗化**：17,826 筆往績觀察入面，812 筆第六或以後但輸≤2.5位；同一歷史賽事可能重複出現，唔係812場獨立賽事。
   固定提升第六七名分數反而少5場Good。只否決呢條固定規則，唔代表所有連續化都無效。
3. **亞季不看輸距**：244筆亞季輸>3位；另52筆冠軍正數距離不可當落後輸距。
   最初混入冠軍嘅測試及「Good少1場」解讀已撤回；PROTOCOL.md保留更正記錄。
   現表只對rank=2/3套既有3位門檻及原折減公式，數字由更正後輸出生成。
4. **缺資料換尺**：624次非初出出賽無可解析逐仗詳情，其中597次有有效近績、27次冇有效名次。
   統一後備尺多1場Gold、1場Good，但增益集中喺最早時間塊，其餘五塊為0；
   排序證據弱，Holm後無支持，**不啟用**。真production獨立重跑與離線候選325/325場排名一致。

以上五個 arm 統計 screen 全部 REJECT。證據不足唔等於證明所有可能改法都無效。

## 獨立 bug：0 名次

原來 FormScorer 已排除<=0；consistency fallback 同逐仗解析冇排除。
0會進入樣本數、近期權重分母同近三仗平均，甚至令未完成賽事讀落似名次回暖。
4,101次出賽入面23次last6含0，13次逐仗詳情包含非正數名次。

獨立預登記、只剔除非正數名次後：325場中3場較後排名變；所有已登記primary／ranking指標逐場都不變。
五個baseline首選SP桶（77／111／106／27／4場）primary全部不變；SP只喺評分完之後做分層。
所有場嘅primary差都係0，所以任何馬群／場地primary分層都係0。
此改動只刪無效資料，不加入新欄位／統計／未來資訊，scoped leakage audit PASS；不據此聲稱整個舊archive provenance已PASS。

已修正兩個解析入口，加三個回歸測試。無改權重、門檻、有效名次嘅分數、後備公式設計。

## 全九維消融

每次只將一維設60，不重新分配權重，重新行SIP／限幅。用嚟量現行配方嘅邊際影響，唔係維度重要性排名，
亦唔係可以照抄嘅新權重。多個消融不做無限組合搜索。

""" + table([k for k in study["arms"] if k.startswith("neutral_")]) + """

健康、晨操嘅差異細，CI跨0；未有證據支持剷走。其餘多項設60會減少Good，維持現行。
各arm完整CI、場地／馬群分層、六時間塊、Holm p同功效半寬見 results.json。

## ML：沿用既定逐日權重學習，唔搜參

乾淨325場輸入先剔死日，再做walk-forward。首10賽日維持現行；其後每個賽日只用之前賽日fit。
現有hkjc_weight_study：場內softmax tau=3、L2=2、非負權重總和1，初出馬不改。
保留SIP residual係原工具限制：不重新判斷每組新權重對SIP觸發嘅影響，故只係權重診斷，不能直接作production promotion。

結果 **Gold 44→40，Good 81→75**。NDCG@5 Δ −0.010063，賽日95% CI [−0.017593, −0.002934]。
v3統計screen REJECT／primary_regression。呢個係既定ML設計輸，唔係證明所有ML方法都輸。
較早未先剔死日嘅試跑已作廢，正式結論只用 -ml-clean.jsonl。

## 九維公式路徑審查

完整數值、分支、fallback、初出馬、所有helper同SIP原碼由 [ALL_FORMULAS.md](ALL_FORMULAS.md) 自動抽取；
易讀外層說明由 explain_model.py 生成，唔人手改官方模型說明檔。

| 維度 | 現役公式／路徑 | 今次審查結論 |
|---|---|---|
| 狀態穩定 | 5/9 F+4/9 C；保留舊四捨五入兼容 | 保留；剔無效名次 |
| 騎練 | .55 J+.45 T；基礎EB實績、細樣本tier、近仗人馬、組合、同程、換騎；除去配備再−3 | 全部追到來源；既有配備forward未開 |
| 段速 | 60+L400、完成時間等級、能量／L400趨勢、引擎型態、路程；訊號不足海外替代／60；再加最快第一段 | 已核對最新第一段加分；較早審計未包括此項，今輪以最新code重跑 |
| 檔位走位 | 沙田 .55 draw+.25 fit+.20 trip；谷草非初出 draw+.45(surface−60)；全場median±10 | 兩地公式分開；rail修正只用賽日前紀錄，唔將場內限幅當新訊號 |
| 健康 | .611 risk+.389 weight；risk由醫療、休息日數、體重趨勢與波幅重算 | 風險分高係較健康；負磅同時參與級數，保留既有設計，未當作bug |
| 晨操 | 趨勢起點+clip(.5快操+1試閘+.1踱步+.05游泳,−4,8) | 次數非負時下限−4通常用唔到；不據此改式；消融功效弱 |
| 同程 | .02(D−60)，D=60+舊class同程加減嘅等效raw調整/.02 | 有上名／未上名／無資料三級；V2只係shadow |
| 賽績線 | 強弱底分+min(8,3×高班贏+同班贏−低班贏)；全部跑唔近則上限60 | 對手之後表現必須係目標賽日前已知；存檔文字provenance唔能夠單靠有分認證 |
| 級數 | .75 class+.25 weight；class=60+經驗／季內；weight按實際負磅54／64／70 | 呢度「班次分」主要係生涯與季內代理，唔係直接官評差值，名稱唔等於全部內涵 |

信心、場地適性、診斷路程分唔直接入九維加權；但某些相同原始資料仍可能經其他路徑入分。
所有已追到嘅公式唔等於每個假設都獲得獨立績效證明；本輪無新增全維度門檻／權重搜索。

## 說明修正與驗證

- explain_model.py 由production AST抽SIP條件，補齊 raw 64≤分<68、輕磅、內檔及速度／近績門檻嘅+1。
- 移除「60永遠等同冇證據」；HKJC顯示60係換尺中位基準，基礎分60要對照source。
- 七維文字標明係歷史校準，現役係九維。
- golden --record曾因新賽日資料改變抽樣，已保留原known-good snapshot，無將reroll同code一齊覆蓋。
- data_contract已重新calibrate，改動只係引擎指紋；未用賽果揀參。
- 檢查.sh --quick／完整檢查及針對性名次回歸測試均需在最終保存前通過。

## 重跑與版本

原始runner dump留喺 /private/tmp，路徑、SHA256及大小見 results.json；冇複製整份語料。
要重現**修正前baseline**，先喺獨立worktree checkout dd22b05d，再將本審查資料夾複製入同一相對路徑。
修正後code會正確剔0，不能冒充原baseline；production零名次arm保留作對照。

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 docs/audits/hkjc-formula-review-20261016/capture.py /private/tmp/hkjc-review-20261016-evidence.jsonl /private/tmp/hkjc-review-20261016-capture-baseline.jsonl
python3 docs/audits/hkjc-formula-review-20261016/study.py /private/tmp/hkjc-review-20261016-capture-baseline.jsonl /private/tmp/hkjc-review-20261016-evidence.jsonl /private/tmp/hkjc-review-20261016-study
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --until 2026-10-10 --arm docs/audits/hkjc-formula-review-20261016/runtime_arm.py --out /private/tmp/hkjc-review-20261016-fallback-runtime.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --until 2026-10-10 --arm docs/audits/hkjc-formula-review-20261016/invalid_status_arm.py --out /private/tmp/hkjc-review-20261016-valid-status-runtime.jsonl
```

ML需先將baseline中error／speed_score死日剔除寫canonical.jsonl，再用hkjc_weight_study.py --arm wf_refit。
finalize.py會核對fallback production排名並寫摘要；report.py產生本報告及實驗記錄。
先前來源版本：EXP-20261010-05/06、EXP-20261015-02及 hkjc-9d-full-audit-2026-10.md。
"""
    (HERE / "README.md").write_text(text)
    experiments = [
        (80, "stability-overlap", "近績與穩定性重疊可以靠單獨設60簡化", ["no_form", "no_consistency"], "REJECT／UNRESOLVABLE：近績設60退步；穩定性設60無確定收益，維持兩項。"),
        (81, "rank67-bucket", "第六七名同第四五名同分可減少粗化損失", ["rank67_equal45"], "REJECT：Good少5場。"),
        (82, "top3-margin", "亞季但輸距大嘅close credit應按輸距折減", ["top3_margin"], "見更正後配對結果：原先混入冠軍嘅測試已撤回；不啟用新規則。"),
        (83, "consistency-fallback-scale", "缺詳情改用同一穩定性尺有益", ["fallback_same_scale"], "REJECT：Gold／Good各多1場，但集中最早塊，排序CI跨0。"),
        (84, "invalid-finish-correctness", "非完成0名次不應進入consistency樣本及趨勢", [], "§7 CORRECTNESS FIX：三場較後排名改動，全部已登記指標及SP分層primary不變；唔係已證實表現改善。"),
        (85, "nine-dimension-weight-recheck", "最新code下既定walk-forward權重refit可贏現役", [], "REJECT：Gold少4場，Good少6場，維持九維權重。"),
    ]
    index_rows = []
    for number, slug, hypothesis, arms, verdict in experiments:
        eid = f"EXP-20261016-{number}"
        name = f"{eid}-hkjc-{slug}.md"
        body = f"""# {eid} — HKJC {hypothesis}

- 日期：2026-10-16；平台：HKJC。
- 假設：{hypothesis}。
- baseline：dd22b05d；最新production重播、PIT騎練。
- 語料：2026-04-12至2026-10-07，325場／33賽日／4,101次出賽；baseline Gold44、Good81。
- 搜索過：EXP-20261010-05/06、EXP-20261015-02、九維審計、docs/experiments相關form／consistency記錄。
- 工具與候選：docs/audits/hkjc-formula-review-20261016/PROTOCOL.md；無效名次另有INVALID_STATUS_PROTOCOL.md。
- 評估：固定規則全紀錄；ML用只向前walk-forward。無開2026-10-11起賽果；無調閾值／換指標。
- 95% CI：賽日bootstrap2000；六時間塊；五個stability arm共一家族Holm調整；有部件預算／CI半寬。

"""
        if arms:
            body += table(arms) + "\n\n"
        body += f"""## 結論

**{verdict}**

詳細CI、分層、來源限制、命令、dataset hash：[審查報告](../audits/hkjc-formula-review-20261016/README.md)、[機讀結果](../audits/hkjc-formula-review-20261016/results.json)。
本次候選唔因單一cohort或點估計而上線。原先五個規則候選model code無合入production。
0名次屬獨立正確性修正：scoped leakage PASS（只刪無效歷史，無新資訊）；全部primary逐場無變，SP五桶亦無變。
全archive歷史衍生欄位仍有provenance FLAG，唔用本輪診斷宣稱全模型無洩漏。
Golden保留原snapshot且一致；data_contract重新calibrate，完整檢查另行記錄。
狀態：研究與證據已記錄；只有0名次解析及模型說明修正準備交付。commit由保存流程記錄。
"""
        (REPO / "docs/experiments" / name).write_text(body)
        index_rows.append(f"| [{eid}]({name}) | 2026-10-16 | HKJC | {hypothesis} | {verdict} |")
    index = REPO / "docs/experiments/INDEX.md"
    current = index.read_text()
    marker = "|---|---|---|---|---|"
    lines = current.splitlines()
    missing = []
    for row in index_rows:
        prefix = row.split("]", 1)[0] + "]"
        found = next((i for i, line in enumerate(lines) if line.startswith(prefix)), None)
        if found is None:
            missing.append(row)
        else:
            lines[found] = row
    current = "\n".join(lines) + "\n"
    if missing:
        current = current.replace(marker, marker + "\n" + "\n".join(missing), 1)
    index.write_text(current)
    print("report + six hypothesis records written")


if __name__ == "__main__":
    main()
