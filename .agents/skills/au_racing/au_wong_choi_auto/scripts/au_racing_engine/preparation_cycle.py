"""Point-in-time preparation chronology, independent of ranking and wall clock."""
from datetime import date
import re

LONG_BREAK_DAYS = 90  # Matches the existing health display's >90-day definition.


def _date(value):
    try:
        return date.fromisoformat(str(value or ''))
    except ValueError:
        return None


def preparation_cycle(entries, meeting_date, *, career_starts=None):
    target = _date(meeting_date)
    result = {'as_of': str(meeting_date or ''), 'stage': 'unknown', 'label': '',
              'days_since_last_run': None, 'prior_spell_days': None,
              'completed_prep_runs': None, 'prep_start_date': None,
              'return_run_date': None, 'return_finish': None, 'return_margin': None,
              'evidence_dates': [], 'summary': ''}
    if target is None:
        return result
    valid = {}
    for entry in entries:
        day = _date(entry.get('date'))
        trial = entry.get('is_trial') or re.search(r'trial|試閘', str(entry.get('kind','')), re.I)
        if day and day < target and not trial:
            valid.setdefault(day, entry)
    dates = sorted(valid, reverse=True)
    result['evidence_dates'] = [d.isoformat() for d in dates]
    if not dates:
        if career_starts == 0:
            result.update(stage='debut', label='初出', completed_prep_runs=0)
        return result
    gap = (target - dates[0]).days
    result['days_since_last_run'] = gap
    if gap > LONG_BREAK_DAYS:
        result.update(stage='first_up', label='久休復出', prior_spell_days=gap,
                      completed_prep_runs=0, prep_start_date=target.isoformat(),
                      summary=f'久休 {gap} 日後首仗；本輪尚未有正式賽表現可驗證狀態')
        return result
    for i, (newer, older) in enumerate(zip(dates, dates[1:])):
        spell = (newer - older).days
        if spell <= LONG_BREAK_DAYS:
            continue
        completed = i + 1
        stage = {1:'second_up', 2:'third_up'}.get(completed, 'established_prep')
        label = {1:'休後第二仗', 2:'休後第三仗'}.get(completed, f'本輪第 {completed+1} 仗')
        returned = valid[newer]
        placing = str(returned.get('placing') or '')
        match = re.match(r'^\s*(\d+)(?:/|\s|$)', placing)
        finish = returned.get('finish_pos')
        if finish is None and match:
            finish = int(match[1])
        margin = returned.get('margin')
        if margin is None:
            match = re.search(r'\(([+-]?\d+(?:\.\d+)?)L\)', placing)
            margin = abs(float(match[1])) if match else None
        result.update(stage=stage, label=label, prior_spell_days=spell,
                      completed_prep_runs=completed, prep_start_date=newer.isoformat(),
                      return_run_date=newer.isoformat(), return_finish=finish, return_margin=margin,
                      summary=f'{label}；本輪首仗前休 {spell} 日，距上仗 {gap} 日，'
                              f'本輪已跑 {completed} 仗；休前往績需與復出後表現分開睇')
        break
    return result
