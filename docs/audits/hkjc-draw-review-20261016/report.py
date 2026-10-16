"""Export measured results, provenance limits and reproducible experiment notes."""
import json
from collections import Counter
from pathlib import Path

import study
from model_evaluation_decision import _full_record_metric
from wongchoi_paths import HK_RACING


def evidence(base, cand, indices):
    return {k: vars(_full_record_metric([base[i][k] for i in indices],
             [cand[i][k] for i in indices], [base[i]['date'] for i in indices],
             higher_is_better=True, blocks=6, bootstrap=2000, seed=7))
            for k in study.METRICS[:2]}


def main():
    folder = Path(__file__).parent
    output = Path('/private/tmp/hkjc-draw-20261016-study')
    result = json.loads((output/'summary.json').read_text())
    base = study.read(output/'aa.jsonl')
    result['production_parity'] = json.loads((output/'production_parity.json').read_text())
    result['power_before_candidates'] = json.loads((output/'power_before_candidates.json').read_text())
    raw_results = {}
    for row in base:
        meeting = row['meeting']
        if meeting not in raw_results:
            files = list((Path(HK_RACING)/meeting).glob('*全日賽果.json'))
            raw_results[meeting] = json.loads(files[0].read_text()) if files else {}
        races = raw_results[meeting]
        race = next((r for key, r in races.items() if isinstance(r, dict) and
                     study.integer(r.get('race_no') or key) == row['race']), {})
        runners = race.get('results') or []
        first = next((h for h in runners if study.integer(h.get('horse_no')) == row['picks'][0]), {})
        try:
            row['baseline_pick_sp'] = float(first.get('win_odds'))
        except (TypeError, ValueError):
            row['baseline_pick_sp'] = None
    cohorts = {f'field_{bucket}': [i for i, b in enumerate(base) if study.field_bucket(b['field']) == bucket]
               for bucket in ('le8', '9_10', '11_12', '13plus')}
    for label, low, high in (('sp_1_3', 0, 3), ('sp_3_7', 3, 7), ('sp_7_15', 7, 15),
                             ('sp_15_30', 15, 30), ('sp_30plus', 30, float('inf'))):
        cohorts[label] = [i for i, b in enumerate(base) if b['baseline_pick_sp'] is not None and low < b['baseline_pick_sp'] <= high]
    for venue in ('沙田', '跑馬地'):
        cohorts[venue] = [i for i, b in enumerate(base) if b['venue'] == venue and not b['awt']]
    cohorts['AWT'] = [i for i, b in enumerate(base) if b['awt']]
    for going in sorted({b['going'] for b in base}):
        cohorts['going_' + going] = [i for i, b in enumerate(base) if b['going'] == going]
    for arm in study.ARMS:
        cand = study.read(output/(arm+'.jsonl'))
        result['arms'][arm]['cohort_primary_ci'] = {
            label: {'races': len(ix), 'metrics': evidence(base, cand, ix)}
            for label, ix in cohorts.items() if ix}
    result['sp_coverage'] = dict(Counter('missing' if b['baseline_pick_sp'] is None else 'available' for b in base))
    snapshots = []
    for path in sorted(Path(HK_RACING).glob('*/Draw_Stats.json')):
        if path.parent.name[:10] > '2026-10-10':
            continue
        data = json.loads(path.read_text())
        snapshots.append({'meeting': path.parent.name, 'meta': data.get('meta'),
                          'races': len(data.get('races') or [])})
    result['official_snapshots'] = snapshots
    result['official_source'] = 'https://racing.hkjc.com/zh-hk/local/information/draw'
    history = study.load_history()
    result['training_by_context'] = {str(k): int(v) for k, v in history.groupby(['Venue', 'Track']).size().items()}
    result['training_dates'] = [history.Date.min(), history.Date.max()]
    examples = []
    for venue, track, distance, n in (('沙田', 'Turf', 1200, 14), ('跑馬地', 'Turf', 1200, 12),
                                       ('沙田', 'Turf', 1600, 14), ('沙田', 'AWT', 1200, 12)):
        ctx = {'venue': venue, 'track': track, 'distance': distance, 'rail': 'A', 'race_date': '2026-10-10'}
        for draw in range(1, n+1):
            horse = {'barrier': draw, 'python_auto': {'feature_scores': {'draw_score': 75 if draw <= 4 else 65 if draw <= 8 else 50}}}
            values = {arm: study.draw_prediction(arm, horse, ctx, list(range(1, n+1)), history)[0] for arm in study.ARMS}
            examples.append({'venue': venue, 'track': track, 'distance': distance, 'field': n, 'draw': draw, **values})
    result['frozen_curve_examples'] = examples
    (folder/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    winners = [a for a in study.ARMS if result['arms'][a]['statistical_screen_only']['verdict'] != 'REJECT']
    conclusion = ('統計篩查候選：' + ', '.join(winners) + '；來源限制未清，仍不可上線。') if winners else '今輪四個預先登記候選全部未通過統計篩查，沒有候選可以取代現行公式。'
    lines = ['# HKJC 檔位公式比較（2026-10-16）', '',
             '結論：' + conclusion + ' 這不代表 75／65／50 是全域最佳。', '',
             f"基準 commit `{result['baseline_commit']}`；{result['races']} 場、{len(result['dates'])} 個賽日、{result['runner_appearances']} 匹次。",
             f"時間：{result['dates'][0]} 至 {result['dates'][-1]}。Gold 基準 {round(result['baseline']['gold']*result['races'])}/{result['races']}；Good {round(result['baseline']['good_positional']*result['races'])}/{result['races']}。",
             '', 'Gold＝實際前三全部在模型頭四；Good＝模型第一、第二揀都上名。', '',
             '| 候選 | Gold 場數差 | Good 場數差 | NDCG@5 差 | v3 統計篩查 |', '|---|---:|---:|---:|---|']
    labels = {'percentile': '相對檔位連續分', 'pit_group': '分場地／途程歷史差',
              'pit_hierarchy': '檔位／出馬數／欄位分層', 'pit_ridge': '正則化回歸曲線'}
    for arm in study.ARMS:
        screen = result['arms'][arm]['statistical_screen_only']
        detail = screen['detail']
        g = detail['primary']['gold']['delta']*result['races']
        good = detail['primary']['good_positional']['delta']*result['races']
        ndcg = detail['ranking']['ndcg_at5']['delta']
        lines.append(f"| {labels[arm]} | {g:+.0f} | {good:+.0f} | {ndcg:+.6f} | {screen['verdict']} / {screen['reason']} |")
    lines += ['', '## 公式及可解讀範圍', '',
              '完整預先登記公式見 [PROTOCOL.md](PROTOCOL.md)。只測普通馬檔位分；初出馬保留原分。沙田及跑馬地不混池，泥地獨立，途程用 exact distance。',
              f"歷史訓練池 {result['training_rows']} 匹次／{result['training_races']} 場，{result['training_dates'][0]} 至 {result['training_dates'][1]}；逐個賽日只用 date < target_date。不是拿完整語料 fit 完再評自己。",
              '相對檔位 x=(draw−1)/(賽前最大宣告檔位−1)。用最大宣告檔位而非賽後完成馬數。三個 learned 方案的最少 100 匹次／20 場門檻作用於同場地、表面、途程的歷史池。',
              '固定差值／回歸曲線的分數尺度和收縮常數事前鎖定，沒有因結果再搜索 gain、門檻或權重。', '',
              '## 場地分層', '', '| 候選 | 沙田草地 Gold／Good 場差 | 跑馬地 Gold／Good 場差 | 泥地 Gold／Good 場差 |', '|---|---:|---:|---:|']
    for arm in study.ARMS:
        cells = []
        for key in ('ST_turf', 'HV_turf', 'AWT'):
            c = result['arms'][arm]['cohorts'].get(key)
            cells.append('無樣本' if not c else f"{c['metrics']['gold']['delta']*c['races']:+.0f}／{c['metrics']['good_positional']['delta']*c['races']:+.0f}（{c['races']}場）")
        lines.append(f"| {labels[arm]} | " + ' | '.join(cells) + ' |')
    lines += ['', '## 資料及限制', '',
              f"- {result['coverage']['unknown_venue_races']} 場缺少／未能辨認 production 場地，全部候選在這些場次 no-op；沒有偷偷用賽果補場地再當公式收益。",
              '- rail_draw_results 的 FieldSize 是有有效名次及檔位的完成馬數，未能當作完整賽前出馬數認證。訓練端上名機會分母有這個限制，不能宣稱已通過洩漏審計。',
              '- 各賽日之前的結果日期已嚴格截斷；但舊 archive 是後來重建，確切的賽前 artifact 可用時間仍未全面認證。統計篩查是條件性診斷，並非 promotion。',
              '- 官網檔位表按跑道／欄杆位置及途程統計。現有八份獨立存檔中七份標示 23 點後抓取；剩下一份亦缺時間區及首次開跑時間的不可變認證。因此官方表直接入分留待前瞻存檔；沒有將今天官網表套回歷史。',
              '- 官方頁說明：https://racing.hkjc.com/zh-hk/local/information/draw 。官網目前表格及例子只用來核對欄位語意，不參與歷史候選選擇。',
              f"- SP 只在評分後加入 cohort，覆蓋 {result['sp_coverage']}，不入任何公式。場地、出馬數、途程、地況及初出馬 cohort 詳見 results.json；unknown going 不冒充已驗證。",
              '- 候選家族 Holm 修正見 results.json；時間塊及按賽日 2000 次 bootstrap 使用既有 v3 判決器，沒有改判決規則。2026-10-11 起 forward 結果未開。', '',
              '## 驗證及保存', '',
              f"- A/A：325 場 raw ability、排名完全一致；候選=baseline 判 REJECT。直接 production 路徑 {len(result['production_parity']['checks'])} 組抽查 raw 分數及排名完全一致。",
              '- 本次沒有修改 production 評分、權重、golden、數據合約或模型說明。',
              '- 完整公式、CI、六時間塊、cohort、來源 hash 及 sample-floor 覆蓋見 results.json；原始較大 runner dump 留在 /private/tmp。', '',
              '```bash', 'export PYTHONDONTWRITEBYTECODE=1',
              'python3 docs/audits/hkjc-draw-review-20261016/capture.py /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-baseline.jsonl',
              'python3 docs/audits/hkjc-draw-review-20261016/study.py /private/tmp/hkjc-draw-20261016-baseline.jsonl /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-study',
              'python3 docs/audits/hkjc-draw-review-20261016/validate.py',
              'python3 docs/audits/hkjc-draw-review-20261016/report.py', '```', '',
              'canonical_keys.json 保存上一輪同 session 已鎖定的 325 場 keys；原來源 /private/tmp/hkjc-review-20261016-canonical.jsonl。該批 351 場先排除 6 場 runner alignment mismatch，再排除 20 場 dead-speed。沒有按本輪績效再篩選。']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    for number, arm in enumerate(study.ARMS, 86):
        screen = result['arms'][arm]['statistical_screen_only']
        text = f"# EXP-20261016-{number} — HKJC {labels[arm]}\n\n"
        text += '- 平台：HKJC；日期：2026-10-16。\n'
        text += f"- 假設：{labels[arm]}可取代原有絕對檔位分組。\n"
        text += '- 舊記錄：EXP-20261007-01、EXP-20261010-09/13、EXP-20260928-01；新來源是逐日截斷的 rail-tagged results，不重試靜態官方表 raw-rate。\n'
        text += f"- baseline：`{result['baseline_commit']}`；候選公式見審計 PROTOCOL.md。\n"
        text += f"- mode：{'fixed_rule' if arm == 'percentile' else 'walk_forward_oos'}；325 場／33 賽日，2026-04-19 至 2026-10-07。逐日只用之前資料，沒有 holdout 擇參。\n"
        text += f"- 統計篩查：**{screen['verdict']} / {screen['reason']}**。完整數字、CI、六時間塊、Holm、cohort 見 [審計](../audits/hkjc-draw-review-20261016/README.md) 及 results.json。\n"
        text += '\n| Primary | 場數差 | 配對賽日 bootstrap 95% CI（pp） | Holm p |\n|---|---:|---:|---:|\n'
        for key, item in screen['detail']['primary'].items():
            text += f"| {key} | {item['delta']*result['races']:+.0f} | [{100*item['ci_low']:+.2f}, {100*item['ci_high']:+.2f}] | {result['holm'][arm+':'+key]:.4f} |\n"
        text += '\n'
        if arm == 'percentile':
            text += '- 失敗形狀：沙田 Gold +2，但 Good −6；跑馬地 Gold −4、Good −5。連續梯度消除門檻跳變，仍未保住首兩選上名。\n'
        elif arm == 'pit_group':
            text += '- 失敗形狀：沙田 Gold −3、Good −7；跑馬地 Gold −2、Good 不變。泥地 +1/+1 只得 15 場，不足以作獨立選擇。\n'
        elif arm == 'pit_hierarchy':
            text += '- 邊際消融：同樣 D 映射下，在 pit_group 後加入 exact draw／field bucket／rail 分層，Good 額外少 8 場（−6→−14）；沒有證據保留額外複雜度。\n'
        else:
            text += '- 失敗形狀：平滑回歸曲線仍令沙田 Good −8、跑馬地 Good −3；全體 Gold −3、Good −10。未支持以固定尺度 ridge 曲線取代先驗。\n'
        text += '- leakage-audit：FLAG（歷史 artifact 可用時間及訓練 FieldSize 分母尚未認證）。沒有 production promotion。\n'
        text += '- golden／data_contract：production 沒有改動；檢查.sh 覆核，不覆蓋 snapshot。\n'
        text += '- 決定：不作 production promotion。沒有證據證明現行公式全域最佳，亦沒有依本輪結果追加搜索。\n'
        text += '- 重跑命令、數據路徑及來源 SHA256：見審計 README.md／results.json。個別判決原因以上述統計篩查為準；唔可推論檔位資訊無效。\n'
        (study.REPO/f'docs/experiments/EXP-20261016-{number}-hkjc-draw-{arm.replace("_", "-")}.md').write_text(text)


if __name__ == '__main__':
    main()
