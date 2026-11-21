#!/usr/bin/env python3
"""Report figure 3 (Results, Repeat tickets): of 6,665 eligible tickets, 23.6% repeat within 30 days and 9.5% within 7
days, 1.53 and 2.30 times random timing's shares, and without monitoring tickets the 30-day share is 22.0%.

(a) The shares that repeat within 7 and 30 days, observed (cobalt) and under random timing (grey), and the 30-day
    share without monitoring tickets (a lighter cobalt, as a variant of the observed share; hatching is kept for
    fig13's record-only values).
(b) The share of eligible tickets that repeat within d days, for each whole number of days d from 0 to 30, observed
    and under random timing, with the two ratios at 7 and 30 days. Whole days match the report's 7- and 30-day
    windows and the caption's wording. Between whole days the exact observed curve has a daily ripple, because
    follow-ups tend to open at the same time of day as the ticket before them; whole days leave it out.

Random timing gives an eligible ticket a next ticket within d days with chance 1 - (1 - d/L)^(n - 1), for its machine's
n unplanned tickets and L days in the period. followups.py stores these chances at 7 and 30 days (rp_pairs.csv); as
notebook 03 does, we rebuild n and L for each machine, check that the formula gives the stored chances, and then draw
it at every d. The formula is exact for d up to 30 days, since every eligible ticket has 30 days of the export after
it.

Inputs: verification/outputs/followups/rp_pairs.csv (one row per eligible ticket, with its machine's next ticket; read
without its customer column), rp_null.csv and followups_summary.json; repro_sql_repeat_summary.csv and
audit_case_repeat_gap_bins.csv (the same counts from the case export); fleet/fx_machine_flags.csv and
htm_machine_counts.csv (each machine's tickets and days, to rebuild random timing). Notebook 03 checks the same numbers.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig03_repeats'
LABEL = 'fig:repeats'
SHORT = 'Repeat tickets vs. random timing'

WINDOW, WEEK = 30, 7          # days, as the report's Definitions state
CUTOFF = '2026-08-02'         # eligible tickets open before Aug 2nd, 2026
# The 30-day share without monitoring tickets is a variant of the observed share: cobalt mixed half with white, a
# lighter tint as GREY_FILL is of the data grey (hatching is kept for fig13's records)
COBALT_TINT = tuple(0.5 * c + 0.5 for c in to_rgb(S.COBALT))
PAIR_COLS = ['case_id', 'next_case_id', 'machine_id', 'opened_date', 'gap_days', 'repeat_30', 'repeat_7',
             'index_monitoring', 'next_monitoring', 'null_p30', 'null_p7']


def closed_form(n, L, d):
    """Random timing's chance that an eligible ticket's next ticket falls within d days (followups.py, notebook 03)."""
    n, L = np.asarray(n, float), np.asarray(L, float)
    return np.where((n > 1) & (L > WINDOW), 1 - (1 - d / L) ** (n - 1), 0.0)


def script_window(pairs, flag):
    """The window behind one of the script's flags, in whole days (notebook 03)."""
    days = math.ceil(pairs.gap_days[flag].max())
    left_out = pairs.gap_days[pairs.next_case_id.notna() & ~flag]
    return days if left_out.min() > days else math.nan


def machine_days(pairs, summary):
    """Each machine's unplanned tickets n and days L in the period, rebuilt as notebook 03 does: fleet machines from
    fleet_exposure.py's table, the others from high_ticket_machines.py's counts over the whole period."""
    flags = pd.read_csv(S.OUT / 'fleet' / 'fx_machine_flags.csv', usecols=['serial_id', 'tickets', 'months'])
    chances = pairs.groupby('machine_id')[['null_p30', 'null_p7']].first()
    fleet = chances.join(flags.set_index('serial_id')[['tickets', 'months']], how='inner')
    tickets = pd.read_csv(S.OUT / 'htm_machine_counts.csv', usecols=['machine_id', 'unplanned_tickets'])
    tickets = tickets.set_index('machine_id').unplanned_tickets
    S.check('fig03 the two tables count the fleet machines alike', 0,
            int((tickets.loc[flags.serial_id].to_numpy() != flags.tickets.to_numpy()).sum()))
    first_day, last_day = pd.to_datetime(summary['definitions']['period'])
    whole = (last_day - first_day).days + 1
    other = chances.drop(fleet.index)
    nl = pd.concat([pd.DataFrame({'n': fleet.tickets, 'L': fleet.months * 365.25 / 12}),
                    pd.DataFrame({'n': tickets.loc[other.index], 'L': float(whole)})])
    both = chances.join(nl)
    for d, col in ((WINDOW, 'null_p30'), (WEEK, 'null_p7')):
        S.check(f'fig03 the formula gives the stored {d}-day chances', 0,
                float(np.abs(closed_form(both.n, both.L, d) - both[col]).max()), 1e-9)
    return pairs[['machine_id']].join(nl, on='machine_id')


def without_monitoring(pairs):
    """Repeats within 30 days once monitoring tickets leave each machine's sequence (notebook 03)."""
    by_case = pairs.set_index('case_id')
    chain = pairs.loc[~pairs.index_monitoring, ['next_case_id', 'gap_days', 'next_monitoring']].copy()
    while chain.next_monitoring.any():   # step past each monitoring follow-up to the ticket after it
        hop = chain.next_monitoring
        assert chain.next_case_id[hop].isin(by_case.index).all(), 'a monitoring follow-up has no row of its own'
        step = by_case.loc[chain.next_case_id[hop].to_numpy()]
        chain.loc[hop, 'gap_days'] = chain.gap_days[hop].to_numpy() + step.gap_days.to_numpy()
        chain.loc[hop, 'next_case_id'] = step.next_case_id.to_numpy()
        chain.loc[hop, 'next_monitoring'] = step.next_monitoring.to_numpy()
    return chain.gap_days.between(0, WINDOW)


def plot(out_dir=S.FIG_DIR):
    pairs = pd.read_csv(S.OUT / 'followups' / 'rp_pairs.csv', usecols=PAIR_COLS)
    summary = json.loads((S.OUT / 'followups' / 'followups_summary.json').read_text())
    assert pairs.case_id.is_unique and (pairs.opened_date < CUTOFF).all()
    n_eligible, n_machines = len(pairs), pairs.machine_id.nunique()
    within_30, within_7 = pairs.gap_days.between(0, WINDOW), pairs.gap_days.between(0, WEEK)
    S.check('fig03 30-day flags = the script\'s', 0, int((within_30 != pairs.repeat_30).sum()))
    S.check('fig03 7-day flags = the script\'s', 0, int((within_7 != pairs.repeat_7).sum()))
    share_30, share_7 = within_30.mean(), within_7.mean()

    # The same counts from the case export (reproduce_sql.py and audit_case_logic.py)
    sql = pd.read_csv(S.OUT / 'repro_sql_repeat_summary.csv').iloc[0]
    S.check('fig03 eligible tickets = reproduce_sql.py', int(sql.eligible_tickets), n_eligible)
    S.check('fig03 machines = reproduce_sql.py', int(sql.machines), n_machines)
    S.check('fig03 30-day repeats = reproduce_sql.py', int(sql.repeat_tickets), int(within_30.sum()))
    cum = pd.read_csv(S.OUT / 'audit_case_repeat_gap_bins.csv').set_index('gap_bin').cum_repeats
    for d, flag in ((WEEK, within_7), (WINDOW, within_30)):
        S.check(f'fig03 {d}-day repeats = audit_case_logic.py', int(cum[cum.index.str.endswith(f',{d}d]')].item()),
                int(flag.sum()))

    # Random timing: the stored chances, their shares and the ratios
    chance_30, chance_7 = pairs.null_p30.mean(), pairs.null_p7.mean()
    ratio_30, ratio_7 = share_30 / chance_30, share_7 / chance_7
    null = pd.read_csv(S.OUT / 'followups' / 'rp_null.csv').set_index(['variant', 'window'])
    for d, chance in ((WINDOW, chance_30), (WEEK, chance_7)):
        S.check(f'fig03 random timing\'s {d}-day share = rp_null.csv', null.loc[('own window, uniform', f'{d} days'),
                                                                               'null_pct'], 100 * chance, 1e-6)
    part_b = summary['facts']['part_b']
    S.check('fig03 30-day ratio = followups_summary.json', part_b['fleet_observed_over_expected_30'], ratio_30, 1e-6)
    S.check('fig03 7-day ratio = followups_summary.json', part_b['fleet_observed_over_expected_7'], ratio_7, 1e-6)

    # Without monitoring tickets
    repeat_nm = without_monitoring(pairs)
    share_nm = repeat_nm.mean()
    pin = next(c for c in summary['checks']['list'] if c['check'].startswith('pin slide 5'))
    S.check('fig03 without monitoring = followups.py\'s count from the case export (repeats)', pin['actual'][0],
            int(repeat_nm.sum()))
    S.check('fig03 without monitoring = followups.py\'s count from the case export (eligible)', pin['actual'][1],
            len(repeat_nm))

    # The curves: the shares that repeat within d days, observed and under random timing, for d = 0, 1, ..., 30
    per_ticket = machine_days(pairs, summary)
    days = np.arange(WINDOW + 1)
    obs = np.array([pairs.gap_days.between(0, d).mean() for d in days])
    rnd = np.array([closed_form(per_ticket.n, per_ticket.L, d).mean() for d in days])
    for d, o, r in ((WEEK, share_7, chance_7), (WINDOW, share_30, chance_30)):
        S.check(f'fig03 observed curve at {d} days = the {d}-day share', o, obs[d], 1e-12)
        S.check(f'fig03 random curve at {d} days = the stored share', r, rnd[d], 1e-9)
    S.check('fig03 both curves start at 0 (no simultaneous follow-up)', 0, obs[0] + rnd[0])
    S.check('fig03 observed curve never falls', 1, int((np.diff(obs) >= 0).all()))

    S.report_check('fig03 eligible tickets', '6,665', S.num(n_eligible))
    S.report_check('fig03 repeat window (days)', '30', S.num(script_window(pairs, pairs.repeat_30)))
    S.report_check('fig03 short window (days)', '7', S.num(script_window(pairs, pairs.repeat_7)))
    S.report_check('fig03 30-day share', '23.6%', S.pct(share_30, 1))
    S.report_check('fig03 7-day share', '9.5%', S.pct(share_7, 1))
    S.report_check('fig03 30-day ratio to random timing', '1.53', S.num(ratio_30, 2))
    S.report_check('fig03 7-day ratio to random timing', '2.30', S.num(ratio_7, 2))
    S.report_check('fig03 30-day share without monitoring tickets', '22.0%', S.pct(share_nm, 1))

    fig, (ax, bx) = S.figure(2.1, ncols=2, width_ratios=[1, 1.12])
    blank = dict(fc=S.WHITE, ec='none', pad=0.8)   # keeps the light grid out of a label

    # (a) bars: observed (cobalt) and random timing (grey), 7 and 30 days, and the 30-day share without monitoring
    # tickets (a lighter cobalt: the observed share once monitoring tickets leave each machine's sequence)
    rows = [(f'Within {WEEK} days', share_7, 'obs', 0.0), ('Random timing', chance_7, 'null', 1.0),
            (f'Within {WINDOW} days', share_30, 'obs', 2.45), ('Random timing', chance_30, 'null', 3.45),
            (f'Within {WINDOW} days, without\nmonitoring tickets', share_nm, 'nm', 5.0)]
    colour = {'obs': S.COBALT, 'null': S.GREY_FILL, 'nm': COBALT_TINT}
    for name, value, kind, y in rows:
        ax.barh(y, value, height=0.62, color=colour[kind], zorder=3)
        key = name == f'Within {WINDOW} days'      # the one green readout: the 30-day share
        text = S.pct(value, 1)
        S.check(f'fig03 (a) label {name} {text}', round(100 * value, 1), float(text.rstrip('%')))
        S.label(ax, value + 0.006, y, text, size=S.FONT if key else S.TICK, weight='bold' if key else 'normal',
                color=S.GREEN if key else S.TEXT, bbox=blank)
    ax.set_yticks([r[3] for r in rows], [r[0] for r in rows], linespacing=1.0)
    ax.set_ylim(5.6, -0.6)
    ax.set_xlim(0, 0.32)
    ax.set_xticks([0, 0.1, 0.2, 0.3])
    S.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of eligible tickets')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'Observed vs. random timing')

    # (b) the curves, with the two ratios at 7 and 30 days
    bx.plot(days, rnd, color=S.GREY_DARK, lw=1.2, ls=(0, (4, 2.5)), zorder=3)
    bx.plot(days, obs, color=S.COBALT, lw=1.5, zorder=4)
    for d, o, r, ratio in ((WEEK, share_7, chance_7, ratio_7), (WINDOW, share_30, chance_30, ratio_30)):
        bx.plot([d, d], [r, o], color=S.GREY_DARK, lw=0.6, zorder=2)
        bx.plot(d, o, 'o', color=S.COBALT, ms=4, zorder=5)
        bx.plot(d, r, 'o', mfc=S.WHITE, mec=S.GREY_DARK, mew=1.0, ms=4, zorder=5)
        text = f'{S.num(ratio, 2)}×'
        S.check(f'fig03 (b) ratio label at {d} days', round(ratio, 2), float(text.rstrip('×')))
        # Beside its connector, in the band between the two curves: right of the 7-day one, where the curves part,
        # centred between the observed curve's lowest and the random curve's highest point over the next five days
        # (the label spans about three); left of the 30-day one, at the connector's middle.
        if d == WEEK:
            span = (days >= d) & (days <= d + 5)
            y = (obs[span].min() + rnd[span].max()) / 2
            S.label(bx, d + 0.8, y, text, ha='left', bbox=blank)
        else:
            S.label(bx, d - 0.6, (o + r) / 2, text, ha='right', bbox=blank)
    S.label(bx, 12.4, obs[12] + 0.022, 'Observed', ha='right', bbox=blank)        # just above the curve
    S.label(bx, 18, rnd[18] - 0.016, 'Random timing', ha='left')      # just below the dashed line
    bx.set_xlim(0, WINDOW + 0.5)
    bx.set_xticks([0, 7, 14, 21, 30])
    bx.set_ylim(0, 0.26)
    bx.set_yticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
    S.pct_axis(bx.yaxis)
    bx.set_xlabel('Days to the next ticket')
    bx.set_ylabel('Share of eligible tickets')
    S.clean(bx, grid='y')
    S.panel(bx, 'b', 'Repeats within each number of days')

    # Nothing drawn is clipped: every bar and both curves inside their panel's limits
    S.check('fig03 (a) bars inside the axis', 1, int(max(r[1] for r in rows) < ax.get_xlim()[1]))
    S.check('fig03 (b) curves inside the axis', 1, int(max(obs.max(), rnd.max()) < bx.get_ylim()[1]))

    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share, 1).replace('%', chr(92) + '%')  # noqa: E731
    return (f'Of {S.num(n_eligible)} eligible tickets, {pc(share_30)} repeat within {WINDOW} days and {pc(share_7)} '
            f'within {WEEK} days, {S.num(ratio_30, 2)} and {S.num(ratio_7, 2)} times random timing\'s shares, and '
            f'without monitoring tickets the {WINDOW}-day share is {pc(share_nm)}. '
            f'(a)~Shares at {WEEK} and {WINDOW} days; (b)~shares within each number of days up to {WINDOW}.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
