"""Shared v2 NBA training/serving features; missing evidence stays missing."""
from __future__ import annotations
import math

FEATURE_CONTRACT = 'nba-ml-features/v2'
FEATURE_COLS = [
    'l10_avg','l10_sd','l10_cov','l10_med','l5_avg','l3_avg','min_avg','pace_projected',
    'usg_pct','ts_pct','def_rtg','opp_def_rating','opp_def_rank','opp_pace','defender_pm',
    'usg_bonus_pct','b2b_flag','b2b_ppg_diff_pct','rest_days','is_home','home_ppg','away_ppg',
    'hit_rate_l10','hit_rate_l5','hit_rate_l3','amc','line_value',
]
PACE_BASELINE = 98.0  # retained from the original ML methodology


def number(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None


def history(values):
    result=[number(value) for value in (values or [])]
    if any(value is None or value<0 for value in result):raise ValueError('invalid historical stat')
    return result


def stats(values):
    if not values:return {key:None for key in ('avg','sd','cov','med')}
    n=len(values);avg=sum(values)/n;sd=math.sqrt(sum((x-avg)**2 for x in values)/n);ordered=sorted(values)
    med=ordered[n//2] if n%2 else (ordered[n//2-1]+ordered[n//2])/2
    return {'avg':round(avg,1),'sd':round(sd,2),'cov':round(sd/avg,3) if avg else 0.0,'med':round(med,1)}


def hit_features(values,line):
    def rate(sample):return round(sum(value>=line for value in sample)/len(sample)*100,0) if sample else None
    clearance=[value-line for value in values if value>=line]
    return {'hit_rate_l10':rate(values),'hit_rate_l5':rate(values[:5]),'hit_rate_l3':rate(values[:3]),
            'amc':round(sum(clearance)/len(clearance),1) if clearance else (0.0 if values else None)}


def build_features(player,stat,line,is_home,opp_abbr=None,*,opp_def_rating=None,opp_def_rank=None,
                   opp_pace=None,defender_pm=None,usg_bonus_pct=None):
    """27 numeric features, with no labels, current-game stats or market prices.

    Context callers resolve the *opponent*, never the player's own team. All
    optional unknowns remain None for the persisted training-only imputer.
    """
    line=number(line)
    if line is None or line<=0:raise ValueError('invalid milestone line')
    gl=player.get('gamelog') or {};adv=player.get('advanced') or {};splits=player.get('splits') or {}
    fatigue=player.get('fatigue') or {};arr=history(gl.get(stat));mins=history(gl.get('MIN'))
    summary=stats(arr);avg=summary['avg'];pace=number(opp_pace)
    pace_projected=round(avg+round((pace-PACE_BASELINE)/PACE_BASELINE*avg,1),1) if avg is not None and pace is not None else None
    normal=number(fatigue.get('normal_ppg'));b2b=number(fatigue.get('b2b_ppg'))
    features={
        **{'l10_'+key:value for key,value in summary.items()},
        'l5_avg':round(sum(arr[:5])/len(arr[:5]),1) if arr else None,
        'l3_avg':round(sum(arr[:3])/len(arr[:3]),1) if arr else None,
        'min_avg':round(sum(mins)/len(mins),1) if mins else None,'pace_projected':pace_projected,
        'usg_pct':number(adv.get('USG_PCT')),'ts_pct':number(adv.get('TS_PCT')),'def_rtg':number(adv.get('DEF_RATING')),
        'opp_def_rating':number(opp_def_rating),'opp_def_rank':number(opp_def_rank),'opp_pace':pace,
        'defender_pm':number(defender_pm),'usg_bonus_pct':number(usg_bonus_pct),
        'b2b_flag':int(fatigue['is_b2b']) if isinstance(fatigue.get('is_b2b'),bool) else None,
        'b2b_ppg_diff_pct':round((b2b-normal)/normal,4) if normal is not None and normal>0 and b2b is not None else None,
        'rest_days':number(fatigue.get('rest_days')),'is_home':int(is_home) if is_home in (True,False,0,1) else None,
        'home_ppg':number(splits.get('Home_PPG')),'away_ppg':number(splits.get('Road_PPG')),'line_value':line,
        **hit_features(arr,line),
    }
    if set(features)!=set(FEATURE_COLS):raise AssertionError('feature contract mismatch')
    return features
