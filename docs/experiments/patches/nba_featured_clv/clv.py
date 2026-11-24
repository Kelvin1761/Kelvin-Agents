"""CLV of NBA featured picks: de-vigged prob of our side at close (last pre-tip two-way quote of the
same O/U line) minus at the 21:00 pick. Control: every O/U line/side seen at 21:00 with a close."""
import json, glob, os, collections, math, random, statistics as st
L = os.path.expanduser('~/WongChoiData/NBA_Market_Eval/ledger')
def fair(o, u): return (1/o)/(1/o+1/u)
picks, ctrl = [], []
for f in sorted(glob.glob(L + '/2026-11-*.jsonl')):
    day = os.path.basename(f)[:10]
    if day < '2026-11-11': continue
    sel, quotes, tips, settle = {}, collections.defaultdict(list), {}, {}
    for line in open(f):
        if '"selection_obs"' in line:
            r = json.loads(line)
            if r.get('snapshot_role') != 'production' or r.get('post_tip'): continue
            ft = (r.get('diagnostics') or {}).get('featured')
            if ft and (r['game_tag'] not in sel or r['recorded_at'] < sel[r['game_tag']]['at']):
                sel[r['game_tag']] = dict(ft, at=r['recorded_at'], tip=r.get('tip_off'))
        elif '"ou_two_way"' in line:
            r = json.loads(line)
            if r.get('tip_unknown') or r.get('post_tip'): continue
            o, u = (r['price'], r['complement_price']) if r['side'] == 'over' else (r['complement_price'], r['price'])
            if not o or not u: continue
            ln = r.get('ou_line') if r.get('ou_line') is not None else r.get('line')
            quotes[(r['game_tag'], r['player'], r['market'], float(ln))].append((r['captured_at'], o, u))
            tips[r['game_tag']] = r.get('tip_off')
        elif '"row_type": "settlement"' in line:
            r = json.loads(line)
            if r.get('actual') is not None and r.get('outcome') != 'void':
                settle[(r['game_tag'], r['player'], r['market'])] = float(r['actual'])
    for g, ft in sel.items():
        k = (g, ft['player'], ft['market'], float(ft['ou_line']))
        obs = sorted(quotes.get(k, []))
        tip = ft.get('tip') or tips.get(g)
        pre = [q for q in obs if q[0] < tip] if tip else obs
        o0, u0 = (ft['price'], ft['other_price']) if ft['side'] == 'over' else (ft['other_price'], ft['price'])
        f0 = fair(o0, u0)
        a = settle.get((g, ft['player'], ft['market']))
        won = None if a is None else ((a > ft['ou_line']) == (ft['side'] == 'over'))
        if not pre or pre[-1][0] <= ft['at'][:19]:
            # same line gone: where did the main line close? (most balanced line, last pre-tip quote)
            best = None
            for kk, oo in quotes.items():
                if kk[:3] != k[:3]: continue
                pp = sorted(q for q in oo if tip and q[0] < tip)
                if pp:
                    _, o1, u1 = pp[-1]
                    cand = (abs(1/o1 - 1/u1), kk[3])
                    best = cand if best is None or cand < best else best
            mv = None if best is None else best[1] - float(ft['ou_line'])
            picks.append(dict(day=day, side=ft['side'], stat=ft['stat'], clv=None, won=won, price=ft['price'],
                              line_move=mv)); continue
        _, o1, u1 = pre[-1]; f1 = fair(o1, u1)
        sgn = 1 if ft['side'] == 'over' else -1
        picks.append(dict(day=day, side=ft['side'], stat=ft['stat'], clv=sgn*(f1-f0), won=won, price=ft['price']))
    # control: every line quoted at/just before 21:00 run (use first quote of the evening) vs close
    for k, obs in quotes.items():
        obs = sorted(obs); tip = tips.get(k[0])
        pre = [q for q in obs if tip and q[0] < tip]
        if len(pre) < 2: continue
        f0, f1 = fair(pre[0][1], pre[0][2]), fair(pre[-1][1], pre[-1][2])
        ctrl.append(dict(day=day, d_over=f1-f0))
def boot(vals_by_day):
    days = sorted(vals_by_day); rnd = random.Random(7); out = []
    for _ in range(2000):
        v = [x for d in (rnd.choice(days) for _ in days) for x in vals_by_day[d]]
        out.append(sum(v)/len(v))
    out.sort(); return out[50], out[1949]
have = [p for p in picks if p['clv'] is not None]
by = collections.defaultdict(list)
for p in have: by[p['day']].append(p['clv'])
print(f"picks {len(picks)}, with close {len(have)}; days {len(by)}")
lo, hi = boot(by)
print(f"mean CLV (pp of fair prob, our side) {100*st.mean(p['clv'] for p in have):+.2f} [{100*lo:+.2f}, {100*hi:+.2f}]  share positive {sum(p['clv']>0 for p in have)/len(have):.2f}  share zero {sum(p['clv']==0 for p in have)/len(have):.2f}")
for side in ('over','under'):
    g=[p for p in have if p['side']==side]
    if g: print(f"  {side}: n={len(g)} mean {100*st.mean(p['clv'] for p in g):+.2f}")
for s in sorted({p['stat'] for p in have}):
    g=[p for p in have if p['stat']==s]; print(f"  {s}: n={len(g)} mean {100*st.mean(p['clv'] for p in g):+.2f}")
w=[p for p in have if p['won'] is not None]
for name,g in (('CLV>0',[p for p in w if p['clv']>0]),('CLV<=0',[p for p in w if p['clv']<=0])):
    if g: print(f"  win rate {name}: {sum(p['won'] for p in g)}/{len(g)} = {sum(p['won'] for p in g)/len(g):.2f}")
lm=[p for p in picks if p['clv'] is None]
fav=sum(1 for p in lm if p.get('line_move') and ((p['line_move']>0) == (p['side']=='under')))
unf=sum(1 for p in lm if p.get('line_move') and ((p['line_move']>0) != (p['side']=='under')))
print(f"no same-line close: {len(lm)}; closing main line moved our way {fav}, against {unf}, unknown/zero {len(lm)-fav-unf}")
cb=collections.defaultdict(list)
for c in ctrl: cb[c['day']].append(c['d_over'])
print(f"control: {len(ctrl)} line-quotes; mean drift of fair P(over) first->close {100*st.mean(c['d_over'] for c in ctrl):+.2f}pp  (under side = minus this)")
