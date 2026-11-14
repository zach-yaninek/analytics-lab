#!/usr/bin/env python3
"""Report figure 11 (Results, Repeat-contact pairings): of the 1,574 repeats, 31% are the same Category, 10% the same
request group with another Category, 32% a different group, and 28% involve monitoring, No Trouble Found, or a blank
Category; 46% of pairs of a machine's tickets a day or less apart share a Category vs. 27% over six months apart; and
no model or telemetry type with 100 or more eligible tickets clearly stands out from the fleet.

(a) The 1,574 repeats by class (the first class that applies; the three process classes together, as the report
    gives them).
(b) All pairs of a machine's tickets with a recorded Category, neither a monitoring ticket: the share of pairs that
    share a Category, by days between the two tickets, with 95% bootstrap intervals over accounts. The two bins the
    report compares are cobalt. The ticks sit between the bars at the bins' edges (0, 1, 7, 30, 90, and 180 days;
    the last bin is open), which keeps six range labels from crowding at this width.
(c) The repeat ratio to the fleet (observed / random-timing repeats, divided by the fleet's) of the 12 models and 11
    telemetry types with 100 or more eligible tickets, with 95% bootstrap intervals over accounts. Points are
    anonymous: models are circles, telemetry types squares, each group in rising order.

Inputs: verification/outputs/followups/rp_pairs.csv (one row per eligible ticket, with its machine's next ticket; read
without its customer column), rp_classes.csv, rp_same_by_gap.csv (counts of all pairs by gap, with intervals),
rp_by_model.csv and rp_by_type.csv (the bootstrap intervals and p-values), followups_summary.json. The outputs do not
record the intervals' level, so it is read from the protocol (docs/09 §6), and the count of pairs is cross-checked
against docs/10. Notebook 03 checks the same numbers.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig11_pairings'
LABEL = 'fig:pairings'
SHORT = 'Repeat-contact pairings'

WINDOW = 30                   # days, as the report's Definitions state
PAIR_COLS = ['case_id', 'machine_id', 'model', 'telemetry_type', 'gap_days', 'repeat_30', 'index_monitoring',
             'next_monitoring', 'index_category', 'next_category', 'index_group', 'next_group', 'pair_class',
             'null_p30']
CLASSES = ['Monitoring involved', 'No Trouble Found involved', 'Category blank', 'Same Category',
           'Same group, other Category', 'Different group']
NOT_TYPES = ['No device match', 'Unknown']   # rows of their own in rp_by_type.csv, never tested
PROTOCOL = S.ROOT / 'docs' / '09_followups_protocol.md'
RESULTS = S.ROOT / 'docs' / '10_followups_results.md'
EDGES = [0, 1, 7, 30, 90, 180]   # days: the gap bins' lower edges, then 180, where the open last bin starts
CASING = [pe.Stroke(linewidth=2.4, foreground=S.WHITE), pe.Normal()]   # so an interval reads on a cobalt bar


def in_words(days):
    """A gap as the report words it (notebook 03): 1 day is 'a day', a whole number of 30-day months in words."""
    if days == 1:
        return 'a day'
    words = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
    return f'{words[days // 30]} months' if days % 30 == 0 and days // 30 < len(words) else f'{days} days'


def bh(p):
    """Benjamini-Hochberg q-values, computed as in followups.py (notebook 03)."""
    p = np.asarray(p, float)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def tested(pairs, within_30, fleet_ratio, key, name, min_eligible, alpha):
    """The units the script tests, recomputed from rp_pairs.csv, with the script's bootstrap interval and p-value
    (notebook 03)."""
    script = pd.read_csv(S.OUT / 'followups' / name).set_index(key)
    units = (pairs.assign(repeat=within_30).groupby(key)
             .agg(eligible=('case_id', 'size'), repeats=('repeat', 'sum'), expected=('null_p30', 'sum')))
    units = units[(units.eligible >= min_eligible) & ~units.index.isin(NOT_TYPES)].copy()
    units['ratio'] = units.repeats / units.expected / fleet_ratio
    rows = script.loc[units.index]
    units[['lo', 'hi', 'p']] = rows[['srr_lo', 'srr_hi', 'srr_p']].to_numpy()
    units['q'] = bh(units.p)
    units['stands_out'] = ((units.lo > 1) | (units.hi < 1)) & (units.q < alpha)
    tag = f'fig11 {name}'
    S.check(f'{tag}: the same units as the script tests', 1,
            int(set(units.index) == set(script.index[~script.pooled.astype(bool) & ~script.index.isin(NOT_TYPES)])))
    S.check(f'{tag}: eligible tickets', 0, int((units.eligible != rows.eligible).sum()))
    S.check(f'{tag}: repeats', 0, int((units.repeats != rows.repeats_30).sum()))
    S.check(f'{tag}: ratios', 0, float((units.ratio - rows.srr).abs().max()), 1e-9)
    S.check(f'{tag}: q-values', 0, float((units.q - rows.srr_q).abs().max()), 1e-9)
    S.check(f'{tag}: every interval holds its ratio', 1,
            int(((units.lo <= units.ratio) & (units.ratio <= units.hi)).all()))
    return units.sort_values('ratio')


def plot(out_dir=S.FIG_DIR):
    pairs = pd.read_csv(S.OUT / 'followups' / 'rp_pairs.csv', usecols=PAIR_COLS)
    summary = json.loads((S.OUT / 'followups' / 'followups_summary.json').read_text())
    defs = summary['definitions']
    within_30 = pairs.gap_days.between(0, WINDOW)
    S.check('fig11 30-day flags = the script\'s', 0, int((within_30 != pairs.repeat_30).sum()))

    # (a) the repeats by class: the first class that applies
    rep = pairs[within_30]
    n_repeats = len(rep)
    pair_class = pd.Series(np.select(
        [rep.index_monitoring | rep.next_monitoring,
         rep.index_category.eq('No Trouble Found') | rep.next_category.eq('No Trouble Found'),
         rep.index_category.eq('Not categorised') | rep.next_category.eq('Not categorised'),
         rep.index_category.eq(rep.next_category),
         rep.index_group.eq(rep.next_group)], CLASSES[:5], CLASSES[5]), index=rep.index)
    S.check('fig11 our classes = the script\'s pair_class', 0, int((pair_class != rep.pair_class).sum()))
    S.check('fig11 the classes = the summary\'s', 1, int(defs['classes'] == CLASSES))
    counts = pair_class.value_counts().reindex(CLASSES, fill_value=0)
    share = counts / n_repeats
    share_process = share[CLASSES[:3]].sum()     # monitoring, No Trouble Found, or a blank Category
    by_class = pd.read_csv(S.OUT / 'followups' / 'rp_classes.csv')
    by_class = by_class[by_class.gap_bin == 'all repeats'].set_index('pair_class')
    S.check('fig11 class counts = rp_classes.csv', 0, int((by_class.pairs.reindex(CLASSES) - counts).abs().max()))
    S.check('fig11 repeats = followups_summary.json', summary['facts']['part_b']['repeats_30'], n_repeats)

    # (b) all pairs of a machine's tickets: the share that share a Category, by gap
    by_gap = pd.read_csv(S.OUT / 'followups' / 'rp_same_by_gap.csv')
    by_gap['share'] = by_gap.same_category_pairs / by_gap.pairs
    S.check('fig11 gap bins in the protocol\'s order', 1, int(by_gap.gap_bin.tolist() == defs['gap_bins']))
    S.check('fig11 shares = rp_same_by_gap.csv', 0, float((by_gap.share - by_gap.share_pairs).abs().max()), 1e-6)
    S.check('fig11 every interval holds its share', 1,
            int(((by_gap.share_lo <= by_gap.share) & (by_gap.share <= by_gap.share_hi)).all()))
    nearest, farthest = by_gap.iloc[0], by_gap.iloc[-1]
    nearest_days = int(re.search(r'\d+', nearest.gap_bin).group())    # '1 day or less' -> 1
    farthest_days = int(re.search(r'\d+', farthest.gap_bin).group())  # 'over 180 days' -> 180
    n_pairs = int(by_gap.pairs.sum())
    # The edge ticks: bin i runs from EDGES[i] to EDGES[i + 1] days ('1 day or less' from 0; 'over 180 days' open)
    bounds = [([0] if 'or less' in b else []) + [int(v) for v in re.findall(r'\d+', b)] for b in by_gap.gap_bin]
    S.check('fig11 (b) edge ticks = the bins\' edges', 1,
            int(bounds == [[lo, hi] for lo, hi in zip(EDGES, EDGES[1:])] + [[EDGES[-1]]]))
    level = re.search(r'\*\*Intervals:\*\* (\d+)% percentile intervals from ([\d,]+) bootstrap draws over accounts',
                      PROTOCOL.read_text())
    S.check('fig11 intervals: 95% (docs/09 §6)', 95, int(level.group(1)))
    S.check('fig11 intervals: the protocol\'s draws = the summary\'s', summary['n_boot'],
            int(level.group(2).replace(',', '')))
    recorded = re.search(r'\(([\d,]+) pairs;', RESULTS.read_text())
    S.check('fig11 caption: pairs = docs/10 (Same Category by gap)', int(recorded.group(1).replace(',', '')), n_pairs)

    # (c) models and telemetry types with 100 or more eligible tickets, relative to the fleet
    min_eligible, alpha = defs['min_eligible'], defs['alpha']
    fleet_ratio = within_30.sum() / pairs.null_p30.sum()
    S.check('fig11 fleet ratio = followups_summary.json', summary['facts']['part_b']['fleet_observed_over_expected_30'],
            fleet_ratio, 1e-6)
    models = tested(pairs, within_30, fleet_ratio, 'model', 'rp_by_model.csv', min_eligible, alpha)
    types = tested(pairs, within_30, fleet_ratio, 'telemetry_type', 'rp_by_type.csv', min_eligible, alpha)
    n_stand_out = int(models.stands_out.sum() + types.stands_out.sum())
    units = pd.concat([models, types])
    q_min = float(units.q.min())
    S.check('fig11 no unit above or below the fleet (followups_summary.json)', 0,
            sum(len(summary['facts']['part_b'][k]) for k in ('models_above', 'models_below', 'types_above',
                                                              'types_below')))
    script_q = pd.concat([pd.read_csv(S.OUT / 'followups' / f).srr_q for f in ('rp_by_model.csv', 'rp_by_type.csv')])
    S.check('fig11 caption: smallest q = the script\'s', round(float(script_q.min()), 2), float(S.num(q_min, 2)))
    S.check('fig11 caption: smallest q is not under alpha', 1, int(q_min >= alpha))

    S.report_check('fig11 repeats', '1,574', S.num(n_repeats))
    S.report_check('fig11 same Category', '31%', S.pct(share['Same Category']))
    S.report_check('fig11 same request group, another Category', '10%', S.pct(share['Same group, other Category']))
    S.report_check('fig11 different group', '32%', S.pct(share['Different group']))
    S.report_check('fig11 monitoring, No Trouble Found, or a blank Category', '28%', S.pct(share_process))
    S.report_check('fig11 shortest gap bin', 'a day or less', f'{in_words(nearest_days)} or less')
    S.report_check('fig11 pairs a day or less apart that share a Category', '46%', S.pct(nearest.share))
    S.report_check('fig11 longest gap bin', 'over six months', f'over {in_words(farthest_days)}')
    S.report_check('fig11 pairs over six months apart that share a Category', '27%', S.pct(farthest.share))
    S.report_check('fig11 eligible tickets a unit needs to be tested', '100', S.num(min_eligible))
    S.report_check('fig11 models or telemetry types that clearly stand out', 'No',
                   'No' if n_stand_out == 0 else S.num(n_stand_out))
    S.report_check('fig11 models tested (Definitions, Clearly stands out)', '12', S.num(len(models)))
    S.report_check('fig11 telemetry types tested (Definitions, Clearly stands out)', '11', S.num(len(types)))

    fig, (ax, bx, cx) = S.figure(2.7, ncols=3, width_ratios=[0.8, 1.12, 1.08])

    # (a) the repeats by class, each labelled above its bar (the process classes last, after a wider gap)
    rows = [('Same Category', share['Same Category'], S.COBALT, 0.0),
            ('Same request group,\nother Category', share['Same group, other Category'], S.GREY_FILL, 1.25),
            ('Different request group', share['Different group'], S.GREY_FILL, 2.35),
            ('Monitoring, No Trouble Found,\nor blank Category', share_process, S.GREY_FILL, 3.75)]
    for name, value, colour, y in rows:
        ax.barh(y, value, height=0.34, color=colour, zorder=3)
        S.label(ax, 0.003, y - 0.24, name, va='bottom', linespacing=1.0)
        text = S.pct(value)
        S.check(f'fig11 (a) label {name!r} {text}', round(100 * value), float(text.rstrip('%')))
        key = colour == S.COBALT                  # the one green readout: the same-Category share
        S.label(ax, value + 0.008, y, text, size=S.FONT if key else S.TICK, weight='bold' if key else 'normal',
                color=S.GREEN if key else S.TEXT)
    ax.set_ylim(4.05, -0.75)
    ax.set_yticks([])
    ax.set_xlim(0, 0.37)
    ax.set_xticks([0, 0.1, 0.2, 0.3])
    S.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of repeats')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'What the repeats are')

    # (b) same-Category share by days apart; the two compared bins in cobalt, each labelled above its interval
    focal = {0, len(by_gap) - 1}
    for i, r in by_gap.iterrows():
        bx.bar(i, r.share, width=0.64, color=S.COBALT if i in focal else S.GREY_FILL, zorder=3)
        line, = bx.plot([i, i], [r.share_lo, r.share_hi], color=S.GREY_DARK, lw=1.0, solid_capstyle='butt', zorder=4)
        line.set_path_effects(CASING)
        if i in focal:
            text = S.pct(r.share)
            S.check(f'fig11 (b) label {r.gap_bin} {text}', round(100 * r.share), float(text.rstrip('%')))
            S.label(bx, i, r.share_hi + 0.012, text, ha='center', va='bottom')
    bx.set_xticks(np.arange(len(EDGES)) - 0.5, [S.num(e) for e in EDGES])   # between the bars: the bins' edges
    bx.set_xlim(-0.5, len(by_gap) - 0.5)
    bx.set_ylim(0, 0.68)
    bx.set_yticks([0, 0.2, 0.4, 0.6])
    S.pct_axis(bx.yaxis)
    bx.set_xlabel('Days between the two tickets')
    bx.set_ylabel('Pairs that share a Category')
    S.clean(bx, grid='y', left=False)
    S.panel(bx, 'b', 'Same Category by days apart')

    # (c) each model and telemetry type: ratio to the fleet with its interval (anonymous points)
    gap = 1.6
    groups = [(models, 'o', 0.0, f'{S.num(len(models))} models'),
              (types, 's', len(models) - 1 + gap, f'{S.num(len(types))} telemetry\ntypes')]
    centres, names = [], []
    for units_, marker, start, name in groups:
        xs = start + np.arange(len(units_))
        cx.vlines(xs, units_.lo, units_.hi, color=S.COBALT, lw=0.9, zorder=3)
        cx.plot(xs, units_.ratio, marker, color=S.COBALT, ms=3.3 if marker == 'o' else 3.0, zorder=4)
        centres.append(xs.mean())
        names.append(name)
    x_end = len(models) - 1 + gap + len(types) - 1
    cx.axhline(1, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)   # the fleet
    cx.set_xlim(-0.8, x_end + 0.8)
    cx.set_xticks(centres, names, linespacing=1.0)
    cx.tick_params(axis='x', length=0)
    cx.set_ylim(0.4, 1.7)
    cx.set_yticks([0.5, 1.0, 1.5], ['0.5', '1.0', '1.5'])
    cx.set_ylabel('Repeat ratio to the fleet')
    S.clean(cx, grid='y', bottom=False)
    S.panel(cx, 'c', 'Models and types')

    # Nothing drawn is clipped: every bar, interval, and point inside its panel's limits
    S.check('fig11 (a) bars inside the axis', 1, int(max(r[1] for r in rows) < ax.get_xlim()[1]))
    S.check('fig11 (b) intervals inside the axis', 1, int(by_gap.share_hi.max() < bx.get_ylim()[1]))
    S.check('fig11 (c) intervals inside the axis', 1,
            int(cx.get_ylim()[0] < units.lo.min() and units.hi.max() < cx.get_ylim()[1]))

    S.export(fig, NAME, out_dir)
    pc = lambda s: S.pct(s).replace('%', chr(92) + '%')  # noqa: E731
    return (f'Of the {S.num(n_repeats)} repeats, {pc(share["Same Category"])} are the same Category, and '
            f'{pc(nearest.share)} of pairs of a machine\'s tickets {in_words(nearest_days)} or less apart share a '
            f'Category vs. {pc(farthest.share)} over {in_words(farthest_days)} apart. '
            f'(a)~Bars show repeats by class. '
            f'(b)~Bars show {S.num(n_pairs)} pairs by gap. '
            f'(c)~No model or telemetry type with {S.num(min_eligible)} or more eligible tickets clearly stands out '
            f'(smallest q, {S.num(q_min, 2)}). '
            f'Lines show {S.num(int(level.group(1)))}\\% bootstrap intervals over accounts.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
