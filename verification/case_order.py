#!/usr/bin/env python3
"""The creation-order test of the case clock (docs/04 §2.1): one shared clock, or each hospital's own?

Salesforce assigns case numbers in creation order. Sorted by case number, opening times on one shared clock can tie
(they are minute-precise) but never step backwards. Had each ticket shown its hospital's local time, a Pacific ticket
opened minutes after an Eastern one would show about 3 hours earlier. This counts the backward steps between
consecutive case numbers:
  - on the export clock, as recorded;
  - on hospital-local clocks: each recorded time (US Eastern, as IPA confirmed) as its hospital's zone would show it;
  - the other way round: each recorded time read as its hospital's local time and moved to US Eastern.
It uses two maps from hospital location to time zone: timestamp_semantics.py's (the state, with 3-digit ZIP rules for
the states that span two zones; verification/zones.py) and the state alone.

docs/04 §2.1 reports 1,205-1,312 backward steps on hospital-local clocks. The first map gives 1,312. The 1,205 came
from a second-wave reviewer's own zone map, which is recorded only in data/derived/workflowB_result.json (not in the
repository). The maps here give 1,210-1,312.

Checks: 7,471 tickets with unique, all-digit case numbers; every hospital located on both maps; tickets by state and
zone = ts_zone_mapping.csv (timestamp_semantics.py's); the case pseudonyms T##### run in case-number order.

Privacy: case numbers and hospital locations are read in memory only. The output holds labels and counts.

Run:  cd /home/user/analytics-lab && python3 -I verification/case_order.py
Writes verification/outputs/case_order_steps.csv
"""
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script directory off sys.path

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import OUTPUTS, build_cases, build_maps, clean, load_raw  # noqa: E402
from zones import STATE_TZ, locate  # noqa: E402

EASTERN = ZoneInfo('America/New_York')
TICKETS = 7471                     # rows of IPA's case export
MAPS = {'state + ZIP3': 'the state, with 3-digit ZIP rules for split states (timestamp_semantics.py)',
        'state only': 'the state alone'}
CLOCKS = {'shown locally': "each recorded time as its hospital's zone would show it",
          'read as local': "each recorded time read as its hospital's local time, moved to US Eastern"}


def steps(times, order):
    """Steps between consecutive case numbers, and how many go backwards or tie (minute precision)."""
    t = np.asarray(pd.to_datetime(pd.Series(times)).to_numpy(), dtype='datetime64[m]')[order]
    gaps = np.diff(t).astype(np.int64)
    return {'steps': len(gaps), 'backward': int((gaps < 0).sum()), 'ties': int((gaps == 0).sum())}


def convert(opened, zones, clock):
    """The opening times on hospital-local clocks ('shown locally') or read as hospital-local ('read as local')."""
    out = []
    for t, zone in zip(opened, zones):
        t, zone = t.to_pydatetime(), ZoneInfo(zone)
        moved = t.replace(tzinfo=EASTERN).astimezone(zone) if clock == 'shown locally' else \
            t.replace(tzinfo=zone).astimezone(EASTERN)
        out.append(moved.replace(tzinfo=None))
    return out


def main():
    checks = []

    def check(name, ok, detail):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        checks.append(bool(ok))

    raw0 = load_raw()
    raw = raw0.astype(object).where(raw0.notna(), None)
    cases = build_cases(raw, build_maps(raw))
    number = raw['Case Number'].map(clean)
    check('tickets, case numbers unique and all digits', len(cases) == TICKETS and number.is_unique
          and bool(number.str.fullmatch(r'\d+').all()), f'{len(cases):,} tickets ({TICKETS:,} expected)')
    order = np.argsort(number.astype(np.int64).to_numpy(), kind='stable')
    check('case pseudonyms run in case-number order', bool((cases.case_id.to_numpy()[order]
                                                           == np.sort(cases.case_id.to_numpy())).all()),
          'T##### sorted = case numbers sorted')
    opened = pd.to_datetime(cases.opened_at)

    geo = pd.DataFrame([locate(a, b) for a, b in
                        raw[['Hospital City, State, Zip', 'Shipping Country']].itertuples(index=False)])
    zones = {'state + ZIP3': geo.iana, 'state only': geo.state.map(STATE_TZ)}
    check('every hospital located on both maps', all(z.notna().all() for z in zones.values()),
          ', '.join(f'{k}: {int(z.isna().sum())} without a zone' for k, z in zones.items()))
    committed = pd.read_csv(OUTPUTS / 'ts_zone_mapping.csv').groupby(['state', 'iana']).tickets.sum()
    mine = geo.groupby(['state', 'iana']).size()
    check('tickets by state and zone = ts_zone_mapping.csv', mine.sort_index().equals(committed.sort_index()),
          f'{len(mine)} state-zone pairs, {int(mine.sum()):,} tickets')

    rows = [{'clock': 'export clock, as recorded', 'zone_map': '', **steps(opened, order)}]
    for clock in CLOCKS:
        for key in MAPS:
            rows.append({'clock': f'{clock}: {CLOCKS[clock]}', 'zone_map': f'{key}: {MAPS[key]}',
                         **steps(convert(opened, zones[key], clock), order)})
    table = pd.DataFrame(rows)
    on_export, local = table.iloc[0], table.iloc[1:]
    check('export clock: no backward step', on_export.backward == 0,
          f'{on_export.backward} of {on_export.steps:,} steps backward, {on_export.ties} ties')
    check('hospital-local clocks: more than 1,200 backward steps on every map', bool((local.backward > 1200).all()),
          f'{local.backward.min():,}-{local.backward.max():,} of {local.steps.iloc[0]:,} steps')

    path = OUTPUTS / 'case_order_steps.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    print(f'  wrote {path.name} ({len(table)} rows)')
    print(f'{sum(checks)}/{len(checks)} checks pass')
    return 0 if all(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
