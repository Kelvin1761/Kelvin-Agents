"""Frozen existing selection thresholds, shared with report descriptions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    l10:float
    l5:float
    min_odds:float
    max_cov:float
    min_legs:int
    max_legs:int
    target_min:float
    target_max:float


BANKER=Policy(80,80,1.20,.65,2,4,2.0,3.5)
BANKER_FALLBACK=Policy(70,70,1.15,.75,2,4,2.0,4.0)
VALUE=Policy(60,60,1.20,.75,2,4,3.0,5.0)
HIGH=Policy(50,50,1.15,.85,3,5,8.0,15.0)
BUILD_TOLERANCE=1.2
STRATEGY_PROFILE="banker-steady-b2-v1"  # EXP-20261027-21; was banker-only-v1


class SelectedCombo(list):
    def __init__(self,legs,rule):
        super().__init__(legs)
        self.selection_rule=rule


def description(combo_id,legs):
    rule=getattr(legs,'selection_rule',None)
    if combo_id=='1':
        if rule in ('banker','banker_fallback'):
            policy=BANKER if rule=='banker' else BANKER_FALLBACK
            prefix='主門檻' if rule=='banker' else 'fallback 放寬門檻'
        else:
            return (f'{BANKER.min_legs}-{BANKER.max_legs} Legs | 主門檻 L10/L5 ≥{BANKER.l10:g}%、CoV ≤{BANKER.max_cov:g}；'
                    f'fallback ≥{BANKER_FALLBACK.l10:g}%、CoV ≤{BANKER_FALLBACK.max_cov:g} | 須取得真實 SGM 報價 ≥2.0；冇 EV 閘（EXP-20261027-21）')
    else:policy={'2':VALUE,'3':HIGH}[combo_id];prefix='選取門檻'
    return (f'{prefix} | {policy.min_legs}-{policy.max_legs} Legs | L10 ≥{policy.l10:g}%、L5 ≥{policy.l5:g}% | CoV ≤{policy.max_cov:g} | '
            f'單腿乘積建構目標 {policy.target_min:.1f}-{policy.target_max:.1f}x，容許上限20%浮動；真實 SGM 價另行取得')
