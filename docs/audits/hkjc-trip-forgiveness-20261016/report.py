"""Measured trip experiment report, with explicit safety and power limits."""
import json
from pathlib import Path

import replay as r
import study


def main():
    result = json.loads((study.OUT/'summary.json').read_text())
    result['validation'] = json.loads((study.OUT/'validation.json').read_text())
    baseline = r.read(study.OUT/'aa.jsonl')
    evidence = {(e['meeting'], e['race']): e for e in r.read(study.EVIDENCE)}
    n = result['races']
    for name in study.ARMS:
        rr = r.read(study.OUT/(name+'.jsonl'))
        max_delta = 0
        for row in rr:
            ev = evidence[(row['meeting'], row['race'])]
            max_delta = max(max_delta, max(abs(v - ev['horses'][k]['auto']['ability_score_raw']) for k, v in row['raw_scores'].items()))
        result['arms'][name]['max_absolute_raw_change'] = max_delta
        result['arms'][name]['changed_top2_membership'] = sum(set(b['picks'][:2]) != set(c['picks'][:2]) for b, c in zip(baseline, rr))
        result['arms'][name]['changed_top4_membership'] = sum(set(b['picks'][:4]) != set(c['picks'][:4]) for b, c in zip(baseline, rr))
    folder = Path(__file__).parent
    (folder/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    labels = {'winner': '外疊仍勝出', 'close_top3': '外疊仍勝出／前三且輸≤3馬位', 'neutral_trip': '沙田消耗分一律60'}
    lines = ['# 高消耗但仍跑好：扣分豁免測試', '',
             f"baseline `{result['baseline_commit']}`；{n}場／{len(result['dates'])}個賽日，{result['dates'][0]} 至 {result['dates'][-1]}。",
             '同 session capture 的 HKJC production code 與目前完全相同，A/A 全部 raw ability 及排名一致；沒有重複抽取、改寫 archive 或開 forward。', '',
             '## 測咗乜', '',
             '只改沙田普通馬近三段往績：日期必須早於今場、有 XW≥3 明確外疊、標籤為高／極高消耗，才按下列條件將該段 52／46 還原 60。沒有額外 bonus。',
             'A：仍勝出；B：仍勝出，或第二／第三且輸距≤3。贏馬 margin 是勝出距離，完全不當作輸距。分數仍按原有最近三段可用值平均。',
             'C：用戶追加要求，沙田普通馬 T 一律60，連低消耗加分亦取消；不重分配內權。追加發生於A/B初步結果後、檢視C績效前，詳見PROTOCOL追加段。三arm重新做Holm。',
             '沙田 R=0.55D+0.25F+0.20T，外權0.2737；SIP及場內限幅照原路跑。HV普通馬V3本來就不使用T，沒有硬加新分。', '',
             '## 配對結果', '',
             '| 方案 | 觸發匹次 | 往績引用 | Gold場數差 | Good場數差 | 完整排名改變場數 | v3統計篩查 |',
             '|---|---:|---:|---:|---:|---:|---|']
    for name in study.ARMS:
        a = result['arms'][name]
        p = a['detail']['primary']
        references = str(result['coverage'][name+'_prior_run_references']) if name != 'neutral_trip' else '不適用'
        lines.append(f"| {labels[name]} | {result['coverage'][name+'_runner_appearances']} | {references} | {p['gold']['delta']*n:+.0f} | {p['good_positional']['delta']*n:+.0f} | {a['changed_races']} | {a['family_decision']} |")
    lines += ['', f"基準 Gold {round(result['baseline']['gold']*n)}/{n}、Good {round(result['baseline']['good_positional']*n)}/{n}。Gold＝實際前三全在模型頭四；Good＝模型首兩選都上名。", '',
              '## 信賴區間及幅度', '', '| 方案／指標 | 差（pp） | 95%賽日配對CI（pp） | Holm p |', '|---|---:|---:|---:|']
    for name in study.ARMS:
        for metric, item in result['arms'][name]['detail']['primary'].items():
            lines.append(f"| {labels[name]}／{metric} | {item['delta']*100:+.3f} | [{item['ci_low']*100:+.3f}, {item['ci_high']*100:+.3f}] | {result['holm'][name+':'+metric]:.4f} |")
    lines += ['', '## 點解唔可以直接話「取消扣分更合理，所以應該上線」', '',
              '- 現有近績維度已計名次及輸距；要量額外排名貢獻，不能只看外疊仍勝出馬本身上名率。',
              '- 這次只取消消耗扣分；幅度會被20%內權、27.37%外權、最近三仗平均及場內cap進一步縮細。觸發不等於有排名變化。',
              '- 既有SIP亦有raw總分門檻，細幅T變化可能觸發／取消原有bonus；報告最大raw差包括這個下游效果，沒有額外改SIP。',
              '- 沒有用 ML 重fit：兩條固定規則已直接測到提議，沒有理由為小改動追加調權重搜索。',
              '- 部件預算及各 ranking metric CI 半寬見 results.json。功效不足只代表判唔清細效益，不會被包裝成改善或改閾值再試。', '',
              '## 資料與驗證', '',
              f"- {result['validation']['parser_safety_checks']} 項 parser／日期安全檢查；{len(result['validation']['production_checks'])} 組 direct production raw ability／完整排名完全一致。",
              '- 當場賽果、SP不進候選條件；SP只在分層評估使用。缺資料一律不猜。',
              '- 歷史文字窗口的確切賽前可用時間尚未全面認證：leakage仍為FLAG。嚴格日期不是完整PASS，不能據此直接promote。',
              '- 缺場地的舊場次保持baseline；venue、field四桶、SP五桶、初出馬場次及going（未知照列）的primary CI見 results.json。',
              '- 2000次bootstrap按賽日、seed7、六個時間塊；三候選×六metrics Holm。v3原始RANKING_WIN仍須經Holm，表內採家族修正後判斷。2026-10-11起forward未開。',
              '- Production code、權重、golden、data-contract baseline沒有改動。', '',
              '## 結論', '']
    for name in study.ARMS:
        a = result['arms'][name]
        lines.append(f"- {labels[name]}：{a['family_decision']}（原始v3：{a['verdict']}／{a['reason']}）。最大raw能力變化 {a['max_absolute_raw_change']:.4f}；頭兩選成員變動{a['changed_top2_membership']}場，頭四選成員變動{a['changed_top4_membership']}場。")
    lines += ['不因邏輯直覺更改現役模型；本次只保存研究方法與證據。', '',
              '## 重跑', '', '```bash', 'export PYTHONDONTWRITEBYTECODE=1',
              '# 如需重新產生同一界線的baseline/evidence（已有同session快照可省）',
              'python3 docs/audits/hkjc-trip-forgiveness-20261016/capture.py /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-baseline.jsonl',
              'python3 docs/audits/hkjc-trip-forgiveness-20261016/study.py',
              'python3 docs/audits/hkjc-trip-forgiveness-20261016/validate.py',
              'python3 docs/audits/hkjc-trip-forgiveness-20261016/report.py', '```',
              'baseline/evidence的路徑與SHA256見results.json。原始dump留在/private/tmp；canonical keys保存在本目錄。capture.py配合hkjc_eval_harness，保持截至2026-10-10的界線；重跑前應將現有snapshot另存，避免覆蓋已量過baseline。']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    for number, name in enumerate(study.ARMS, 90):
        a = result['arms'][name]
        text = f"# EXP-20261016-{number} — HKJC {labels[name]}消耗扣分豁免\n\n"
        text += f"- 日期：2026-10-16；平台：HKJC；baseline：`{result['baseline_commit']}`。\n"
        text += '- 假設：測沙田普通馬消耗分的邊際排名貢獻；winner／close_top3只取消符合條件往績的52／46→60扣分，neutral_trip則T一律60。\n'
        text += '- 舊記錄：EXP-20260902-08、EXP-20260904-07、EXP-20260928-01；不是重試全T中性或反轉trip符號。\n'
        text += f"- 固定條件：{labels[name]}。winner／close_top3要求日期嚴格早於今場、XW≥3、原標籤高／極高；其他資料缺失不猜。neutral_trip無須往績資格，所有沙田普通馬T=60。\n"
        text += '- mode=fixed_rule；325場／33賽日，2026-04-19至2026-10-07；沒有fit或holdout調參，2026-10-11起forward未開。\n'
        text += f"- 家族修正後：**{a['family_decision']}**；原始v3：{a['verdict']}／{a['reason']}。\n\n"
        text += '| 指標 | baseline | candidate | 差 | 95%CI（pp） |\n|---|---:|---:|---:|---:|\n'
        for k, item in a['detail']['primary'].items():
            bv = result['baseline'][k]*n
            text += f"| {k} | {bv:.0f} | {bv+item['delta']*n:.0f} | {item['delta']*n:+.0f}場 | [{100*item['ci_low']:+.3f}, {100*item['ci_high']:+.3f}] |\n"
        text += f"\n觸發{result['coverage'][name+'_runner_appearances']}匹次；完整排名改變{a['changed_races']}場，頭兩選成員變動{a['changed_top2_membership']}場。只取消扣分不足以保證有額外上名捕捉收益，不能將零變化說成規則無用。\n"
        text += '- leakage-audit：FLAG（舊文字artifact賽前可用時間未全面認證）；日期／parser檢查及direct production parity通過。\n'
        text += '- golden／data_contract：production未改；由檢查.sh核對，未record／calibrate新snapshot。\n'
        text += '- 決定：今輪不作production promotion。只按完整家族修正後證據解讀，未merge／deploy任何候選model code。\n'
        text += '- 公式、Holm、六時間塊、ranking power、cohorts、來源hash及重跑：見 [審計](../audits/hkjc-trip-forgiveness-20261016/README.md) 及 results.json。\n'
        (r.REPO/f'docs/experiments/EXP-20261016-{number}-hkjc-trip-{name.replace("_", "-")}.md').write_text(text)


if __name__ == '__main__':
    main()
