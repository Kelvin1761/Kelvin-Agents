import json

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sm = data['race_analysis']["speed_map"]
sm['leaders'] = [str(x) for x in sm['leaders']]
sm['on_pace'] = [str(x) for x in sm.get('on_pace', [])]
sm['mid_pack'] = [str(x) for x in sm.get('mid_pack', [])]
sm['closers'] = [str(x) for x in sm.get('closers', [])]

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
