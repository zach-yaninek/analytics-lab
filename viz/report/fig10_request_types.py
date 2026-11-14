#!/usr/bin/env python3
"""Report figure 10 (Results, Request types by age): young machines run 8.0 unplanned tickets per 100 machine-months
vs. 4.8 for older ones (1.66 times), with higher rates in nearly every request group; within model, Electronics'
share is 1.31 times as large on young machines (mostly Touchscreen) and Mechanical's 0.70 times; 80% of the 1,447
extra tickets come from young machines running above older ones of the same model; and Touchscreen tickets cluster
on 2022-23 installs (1.54 per 100, 3.9 times the 2024-26 rate).

(a) Unplanned tickets per 100 installed machine-months on young and older machines, all tickets and each of the ten
    request groups, all models together. The axis is logarithmic, so the gap between a row's two marks is its rate
    ratio and reads the same at every rate. Every group runs higher on young machines, but the rate ratio's 95%
    bootstrap interval includes 1 for two of them (Network and Software), which is why the report says "nearly every":
    those two come last, apart, with grey young-machine marks and a direct label; the rest run in order of young
    machines' rate.
(b) Each request group's within-model share ratio, pooled over the 15 comparison models, with its 95% bootstrap
    interval over accounts, in the rows of (a). Not categorized has none (the share ratio's base leaves it out), so
    its row says 'excluded'. The two groups that pass the planned test, Electronics and Mechanical, are cobalt and
    labelled.
(c) The 1,447 extra tickets on young machines in one bar, with the 1,156 of them (80%) from young machines running
    above older ones of the same model (the within-model part) in cobalt.
(d) Touchscreen tickets per 100 installed machine-months on the comparison models' machines, by install cohort, with
    95% bootstrap intervals over accounts. The connector gives the 2022-23 rate as a multiple of the 2024-26 rate. The
    axis label is fig12's, word for word.
Labels that cross a grid line have a white backing, so the grid stops behind them.

Inputs: verification/outputs/followups/ag_band_rates.csv, ag_type_rates.csv, ag_type_adjusted.csv, ag_support.csv,
ag_by_model.csv, ag_decomposition.csv, ag_install_year.csv, ag_install_pooled.csv, rp_pairs.csv (read without its
customer column), followups_summary.json; fleet/fx_machine_flags.csv (read without its customer column). The
intervals' level is read from the protocol (docs/09 §6). Notebook 07 checks the same numbers: part_a() follows its
recomputation step by step, and fig12_electronics.py reuses part_a().
"""
import itertools
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig10_request_types'
LABEL = 'fig:request-types'
SHORT = 'Request types by age'

FU = S.OUT / 'followups'
PROTOCOL = S.ROOT / 'docs' / '09_followups_protocol.md'
AGES = ['Under 4', '4+']      # young (under 4 years) and older machines, as the tables label the age groups
ALL = 'All unplanned tickets'
FOCUS = 'Touchscreen'
MACHINE_COLS = ['serial_id', 'model', 'age_band', 'tickets', 'install_year']           # not the customer column
PAIR_COLS = ['case_id', 'next_case_id', 'machine_id', 'index_group', 'index_category', 'next_group', 'next_category']
SHOWN = {ALL: 'All tickets', 'Not categorised': 'Not categorized'}                     # names as the report prints them
CASING = [pe.Stroke(linewidth=2.4, foreground=S.WHITE), pe.Normal()]   # so an interval reads on a cobalt bar


# ----------------------------------------------------------------------------------------------------------------
# Notebook 07's recomputation from the committed outputs (also used by fig12_electronics.py)
# ----------------------------------------------------------------------------------------------------------------
def dashed(label):
    """'2022-23' -> '2022–23', as the report prints a span of years."""
    return label.replace('-', '–')


def cohort_years(label):
    """'2022-23' -> (2022, 2023)."""
    first, last = label.split('-')
    return int(first), int(first[:2] + last)


def mh_share(a, b, n1, n0):
    """Mantel-Haenszel share ratio over the models: the sum of a·n0/N ÷ the sum of b·n1/N, where N = n1 + n0."""
    N = n1 + n0
    return (a * n0 / N).sum() / (b * n1 / N).sum()


def mh_excess(a, b, n1, n0):
    """Young machines' tickets minus those expected at the same within-model mix: the sum of a − n1·(a + b)/N."""
    return (a - n1 * (a + b) / (n1 + n0)).sum()


def how_many(higher, clear, total):
    """The report's words for how many groups run higher on young machines (notebook 07): 'every' when every
    interval excludes 1, 'nearly every' when every estimate is higher and all but at most two intervals exclude 1."""
    if clear == total:
        return 'every'
    if higher == total and total - clear <= 2:
        return 'nearly every'
    return f'{clear} of {total}'


def part_a(tag):
    """Notebook 07's numbers for Part A of the follow-ups, recomputed from the committed outputs, with every
    cross-check against the script's own tables as an S.check named with `tag`."""
    summary = json.loads((FU / 'followups_summary.json').read_text())
    defs = summary['definitions']
    groups = defs['groups']

    def age_group(bands):
        return np.where(pd.Series(bands).isin(defs['young_bands']), AGES[0], AGES[1])

    # All tickets: each fleet machine's tickets and the machine-months by model and age group
    machines = pd.read_csv(S.OUT / 'fleet' / 'fx_machine_flags.csv', usecols=MACHINE_COLS)
    machines['age_group'] = age_group(machines.age_band)
    support = pd.read_csv(FU / 'ag_support.csv')
    months = support.groupby('age_group').months.sum().reindex(AGES)
    tickets = machines.groupby('age_group').tickets.sum().reindex(AGES)
    rate = 100 * tickets / months
    listed = support.set_index(['model', 'age_group']).tickets
    per_model = machines.groupby(['model', 'age_group']).tickets.sum()
    S.check(f'{tag} per-machine tickets = ag_support.csv by model and age group', 0,
            int((per_model.reindex(listed.index, fill_value=0) != listed).sum() + (per_model.sum() != listed.sum())))

    # Each request group, all models together: the sums over the age bands
    bands = pd.read_csv(FU / 'ag_band_rates.csv')
    bands['age_group'] = age_group(bands.age_band)
    sums = bands.groupby(['type', 'age_group'])[['tickets', 'months']].sum()
    young, older = sums.xs(AGES[0], level='age_group'), sums.xs(AGES[1], level='age_group')
    crude = pd.DataFrame({'young_tickets': young.tickets, 'older_tickets': older.tickets,
                          'young_rate': 100 * young.tickets / young.months,
                          'older_rate': 100 * older.tickets / older.months}).reindex(groups + [ALL])
    crude['ratio'] = crude.young_rate / crude.older_rate
    rates = pd.read_csv(FU / 'ag_type_rates.csv')
    boot = rates[rates.level.isin(['group', 'all'])].set_index('type').loc[crude.index]
    crude['lo'], crude['hi'] = boot.rate_ratio_lo.to_numpy(), boot.rate_ratio_hi.to_numpy()
    S.check(f'{tag} all tickets: the age bands give the same ratio', rate.iloc[0] / rate.iloc[1],
            crude.at[ALL, 'ratio'], 1e-9)
    S.check(f'{tag} group rates = ag_type_rates.csv (young)', 0,
            float((crude.young_rate - boot.under4_rate_per_100).abs().max()), 1e-9)
    S.check(f'{tag} group rates = ag_type_rates.csv (older)', 0,
            float((crude.older_rate - boot.plus4_rate_per_100).abs().max()), 1e-9)
    S.check(f'{tag} the ten groups add up to all tickets', 0,
            int(abs(crude.loc[groups, 'young_tickets'].sum() - tickets.iloc[0])
                + abs(crude.loc[groups, 'older_tickets'].sum() - tickets.iloc[1])))
    S.check(f'{tag} every interval holds its rate ratio', 1,
            int(((crude.lo <= crude.ratio) & (crude.ratio <= crude.hi)).all()))
    lower = crude.lo.loc[groups]
    groups_word = how_many(int((crude.ratio.loc[groups] > 1).sum()), int((lower > 1).sum()), len(groups))

    # Within model: the 15 comparison models and the share ratio's base, the nine groups other than Not categorized
    adjusted = pd.read_csv(FU / 'ag_type_adjusted.csv')
    primary = adjusted[adjusted.variant == 'primary'].copy()
    for flag in ('estimable', 'significant', 'tested'):
        S.check(f'{tag} primary rows: {flag} is a flag', 1, int(primary[flag].map(type).eq(bool).all()))
        primary[flag] = primary[flag].eq(True)
    adj_groups = primary[primary.level == 'group'].set_index('type')
    adj_cats = primary[primary.level == 'category'].set_index('type')
    months_by = support.pivot(index='model', columns='age_group', values='months').reindex(columns=AGES).fillna(0)
    comparison = sorted(months_by.index[(months_by >= defs['min_support_months']).all(axis=1)])
    S.check(f'{tag} comparison models = ag_support.csv and the summary', 1,
            int(comparison == sorted(support.model[support.in_support].unique())
                == sorted(summary['facts']['support']['support_models'])))
    M1, M0 = months_by.loc[comparison, AGES[0]], months_by.loc[comparison, AGES[1]]

    def base(column):
        table = support[support.model.isin(comparison)].pivot(index='model', columns='age_group', values=column)
        return table[AGES[0]], table[AGES[1]]

    n1, n0 = base('family_tickets')
    left_out = [g for g in groups if g not in defs['primary_family']]
    S.check(f'{tag} the share ratio\'s base leaves out Not categorized only', 1,
            int(left_out == ['Not categorised'] and len(defs['primary_family']) == len(groups) - 1))
    S.check(f'{tag} the script\'s shares divide by the nine-group base', 1,
            int(np.allclose(adj_groups.under4_share, adj_groups.under4_tickets / n1.sum(), rtol=1e-8, atol=0)
                and np.allclose(adj_groups.plus4_share, adj_groups.plus4_tickets / n0.sum(), rtol=1e-8, atol=0)))

    def mh_rate(a, b):
        M = M1 + M0
        return (a * M0 / M).sum() / (b * M1 / M).sum()

    # Each comparison model's tickets in a group: the six models of ag_by_model.csv, the tickets that rp_pairs.csv
    # shows on the other nine, and the one placement of the rest that gives the script's within-model rate ratio
    six = pd.read_csv(FU / 'ag_by_model.csv')
    pairs = pd.read_csv(FU / 'rp_pairs.csv', usecols=PAIR_COLS)
    cols = ['case_id', 'machine_id', 'group', 'category']
    seen = pd.concat([pairs[['case_id', 'machine_id', 'index_group', 'index_category']].set_axis(cols, axis=1),
                      pairs.loc[pairs.next_case_id.notna(), ['next_case_id', 'machine_id', 'next_group',
                                                             'next_category']].set_axis(cols, axis=1)])
    seen = seen.drop_duplicates('case_id').merge(machines[['serial_id', 'model', 'age_group', 'install_year']],
                                                 left_on='machine_id', right_on='serial_id')
    S.check(f'{tag} ag_by_model.csv models are comparison models', 1, int(set(six.model) <= set(comparison)))
    S.check(f'{tag} rp_pairs.csv never shows more tickets than a machine has', 1,
            int((seen.groupby('machine_id').size().reindex(machines.serial_id, fill_value=0).to_numpy()
                 <= machines.tickets.to_numpy()).all()))
    others = [m for m in comparison if m not in set(six.model)]
    cells = pd.MultiIndex.from_product([others, AGES], names=['model', 'age_group'])
    seen_other = seen[seen.model.isin(others)]
    missing = listed.reindex(cells, fill_value=0) - seen_other.groupby(['model', 'age_group']).size().reindex(
        cells, fill_value=0)
    S.check(f'{tag} rp_pairs.csv misses no negative number of tickets', 1, int((missing >= 0).all()))
    room_young = missing.xs(AGES[0], level='age_group')[lambda s: s > 0]
    room_old = missing.xs(AGES[1], level='age_group')[lambda s: s > 0]

    def placements(total, room):
        return [p for p in itertools.product(*(range(int(r) + 1) for r in room)) if sum(p) == total]

    def group_counts(group):
        yng, old = pd.Series(0, index=comparison), pd.Series(0, index=comparison)
        by_six = six.pivot(index='model', columns='age_group', values=f'tickets_{group}')
        yng.loc[by_six.index], old.loc[by_six.index] = by_six[AGES[0]].to_numpy(), by_six[AGES[1]].to_numpy()
        shown = seen_other[seen_other.group == group].groupby(['model', 'age_group']).size()
        for m in others:
            yng[m], old[m] = shown.get((m, AGES[0]), 0), shown.get((m, AGES[1]), 0)
        script = adj_groups.loc[group]
        left_young, left_old = int(script.under4_tickets - yng.sum()), int(script.plus4_tickets - old.sum())
        tried = [(yng.add(pd.Series(py, index=room_young.index), fill_value=0),
                  old.add(pd.Series(po, index=room_old.index), fill_value=0))
                 for py in placements(left_young, room_young) for po in placements(left_old, room_old)]
        fits = [(a, b) for a, b in tried if np.isclose(mh_rate(a, b), script.rate_ratio_mh, rtol=1e-8, atol=0)]
        S.check(f'{tag} {group}: one placement gives the script\'s within-model rate ratio', 1, len(fits))
        return fits[0]

    share_ratio, excess = {}, {}
    for group in ('Electronics', 'Mechanical'):
        a, b = group_counts(group)
        share_ratio[group], excess[group] = mh_share(a, b, n1, n0), mh_excess(a, b, n1, n0)
        S.check(f'{tag} {group}: share ratio = the script\'s', adj_groups.at[group, 'share_ratio_mh'],
                share_ratio[group], 1e-8 * share_ratio[group])
        S.check(f'{tag} {group}: excess = the script\'s', adj_groups.at[group, 'excess_under4_tickets'],
                excess[group], 1e-6)
    S.check(f'{tag} every interval holds its share ratio', 1,
            int(((adj_groups.share_ratio_lo <= adj_groups.share_ratio_mh)
                 & (adj_groups.share_ratio_mh <= adj_groups.share_ratio_hi)).all()))
    el_excess = adj_cats[(adj_cats.group == 'Electronics') & adj_cats.estimable].excess_under4_tickets
    mostly = el_excess.idxmax() if el_excess.max() / excess['Electronics'] > 0.5 else 'no single Category'

    # Extra tickets on young machines and their split
    tickets_by = support.pivot(index='model', columns='age_group', values='tickets').reindex(columns=AGES).fillna(0)
    S.check(f'{tag} the two pivots list the models alike', 1, int(tickets_by.index.equals(months_by.index)))
    inside = tickets_by.index.isin(comparison)
    old_rate = tickets_by[AGES[1]].sum() / months_by[AGES[1]].sum()
    own_rate = tickets_by.loc[inside, AGES[1]] / months_by.loc[inside, AGES[1]]
    expected_same_model = (months_by.loc[inside, AGES[0]] * own_rate).sum()
    extra = tickets_by[AGES[0]].sum() - months_by[AGES[0]].sum() * old_rate
    within = tickets_by.loc[inside, AGES[0]].sum() - expected_same_model
    mix = expected_same_model - months_by.loc[inside, AGES[0]].sum() * old_rate
    outside = tickets_by.loc[~inside, AGES[0]].sum() - months_by.loc[~inside, AGES[0]].sum() * old_rate
    dec = pd.read_csv(FU / 'ag_decomposition.csv')
    dec = dec[dec.level == 'all'].iloc[0]
    facts = summary['facts']['part_a']
    ours = [extra, within, mix, outside]
    S.check(f'{tag} the parts add up to the extra tickets', extra, within + mix + outside, 1e-9)
    S.check(f'{tag} the parts = ag_decomposition.csv', 0, float(np.abs(np.array(ours) - dec[
        ['extra_tickets', 'within_model_age_tickets', 'model_mix_tickets', 'outside_support_tickets']].astype(
        float).to_numpy()).max()), 1e-6)
    S.check(f'{tag} the parts = followups_summary.json', 0, float(np.abs(np.array(ours) - np.array(
        [facts[k] for k in ('extra_tickets', 'extra_within_model_age', 'extra_model_mix',
                            'extra_outside_support')])).max()), 1e-5)

    # Touchscreen by install cohort on the comparison models, at any age
    years = pd.read_csv(FU / 'ag_install_year.csv')
    ts_years = years[years.category == FOCUS]
    pooled = pd.read_csv(FU / 'ag_install_pooled.csv', dtype={'install': str})
    pooled_ts = pooled[(pooled.category == FOCUS) & (pooled.unit == 'cohort')].set_index('install')
    names = list(pooled_ts.index)
    cohorts = pd.DataFrame([ts_years[ts_years.install_year.between(*cohort_years(c))][
        ['machines', 'under4_machines', 'months', 'tickets']].sum().rename(c) for c in names])
    cohorts['rate'] = 100 * cohorts.tickets / cohorts.months
    newest = names[-1]
    cohorts['vs_newest'] = cohorts.rate / cohorts.at[newest, 'rate']
    cohorts['lo'], cohorts['hi'] = pooled_ts.rate_lo, pooled_ts.rate_hi
    cluster = cohorts.rate.idxmax()
    S.check(f'{tag} {FOCUS} cohorts = ag_install_pooled.csv', 1, int(
        np.allclose(cohorts[['machines', 'months', 'tickets', 'rate']].to_numpy(float),
                    pooled_ts[['machines', 'months', 'tickets', 'rate_per_100']].to_numpy(float))
        and np.allclose(cohorts.vs_newest, pooled_ts.ratio_to_newest_cohort)))
    S.check(f'{tag} {FOCUS} cohorts: every interval holds its rate', 1,
            int(((cohorts.lo <= cohorts.rate) & (cohorts.rate <= cohorts.hi)).all()))
    S.check(f'{tag} {FOCUS} cohorts are the protocol\'s four', 1,
            int([dashed(c) for c in names] == ['2016–18', '2019–21', '2022–23', '2024–26']))

    # The intervals' level: the protocol's statistical conventions (docs/09 §6)
    level = re.search(r'\*\*Intervals:\*\* (\d+)% percentile intervals from ([\d,]+) bootstrap draws over accounts',
                      PROTOCOL.read_text())
    S.check(f'{tag} intervals: the protocol\'s draws = the summary\'s', summary['n_boot'],
            int(level.group(2).replace(',', '')))

    return SimpleNamespace(
        summary=summary, defs=defs, groups=groups, machines=machines, support=support, months=months,
        tickets=tickets, rate_young=rate.iloc[0], rate_old=rate.iloc[1], ratio_all=rate.iloc[0] / rate.iloc[1],
        bands=bands, crude=crude, rates=rates, groups_word=groups_word, adj_groups=adj_groups, adj_cats=adj_cats,
        comparison=comparison, n1=n1, n0=n0, seen=seen, share_ratio=share_ratio, excess=excess, mostly=mostly,
        extra=extra, within=within, mix=mix, outside=outside, ts_years=ts_years, cohorts=cohorts, cluster=cluster,
        newest=newest, interval_level=int(level.group(1)))


def centre_under_panel(fig, ax):
    """Centre the x-axis label under the whole panel, tick labels included, so a one-line label wider than the
    axis takes no room beside it (two passes, as the layout settles)."""
    for _ in range(2):
        fig.draw_without_rendering()
        renderer = fig.canvas.get_renderer()
        box = ax.get_window_extent(renderer)
        left = min(t.get_window_extent(renderer).x0 for t in ax.get_yticklabels() if t.get_text())
        ax.xaxis.label.set_x(((left + box.x1) / 2 - box.x0) / box.width)


# ----------------------------------------------------------------------------------------------------------------
# The figure
# ----------------------------------------------------------------------------------------------------------------
def plot(out_dir=S.FIG_DIR):
    p = part_a('fig10')
    crude, adj = p.crude, p.adj_groups
    sr_el, sr_mech = p.share_ratio['Electronics'], p.share_ratio['Mechanical']
    share_within = p.within / p.extra
    rate_cluster = p.cohorts.at[p.cluster, 'rate']
    ratio_cluster = p.cohorts.at[p.cluster, 'vs_newest']
    passing = sorted(adj.index[adj.significant])

    S.report_check('fig10 young machines per 100 machine-months', '8.0', S.num(p.rate_young, 1))
    S.report_check('fig10 older machines per 100 machine-months', '4.8', S.num(p.rate_old, 1))
    S.report_check('fig10 young vs. older, all tickets', '1.66', S.num(p.ratio_all, 2))
    S.report_check('fig10 request groups with a higher rate on young machines', 'nearly every', p.groups_word)
    S.report_check('fig10 within model: Electronics\' share ratio', '1.31', S.num(sr_el, 2))
    S.report_check('fig10 Category behind most of Electronics\' larger share', 'mostly Touchscreen',
                   f'mostly {p.mostly}')
    S.report_check('fig10 within model: Mechanical\'s share ratio', '0.70', S.num(sr_mech, 2))
    S.report_check('fig10 share of the extra tickets from young machines above older ones of the same model', '80%',
                   S.pct(share_within))
    S.report_check('fig10 extra tickets on young machines', '1,447', S.num(p.extra))
    S.report_check('fig10 install cohort where Touchscreen tickets cluster', '2022–23', dashed(p.cluster))
    S.report_check('fig10 Touchscreen per 100 machine-months on those installs', '1.54', S.num(rate_cluster, 2))
    S.report_check('fig10 that rate vs. the newest cohort\'s', '3.9', S.num(ratio_cluster, 1))
    S.report_check('fig10 the newest cohort', '2024–26', dashed(p.newest))
    S.report_check('fig10 within-model extra tickets (Definitions, Extra tickets and the 80%)', '1,156',
                   S.num(p.within))
    S.report_check('fig10 comparison models (Definitions, Within model)', '15', S.num(len(p.comparison)))
    S.check('fig10 (b) the cobalt groups = the groups that pass the test', 1, int(passing == ['Electronics',
                                                                                             'Mechanical']))
    S.check('fig10 intervals: 95% (docs/09 §6)', 95, p.interval_level)

    fig, ax0 = S.figure(2.2)
    ax0.remove()
    axes = fig.subplot_mosaic([['a', 'b', 'c'], ['a', 'b', 'd']], width_ratios=[1.3, 0.95, 1.75],
                              height_ratios=[0.26, 0.74])
    ax, bx, cx, dx = (axes[k] for k in 'abcd')
    backing = dict(facecolor=S.WHITE, edgecolor='none', pad=0.8)   # the light grid stops behind the labels

    # (a) rates by request group, young vs. older: all tickets on top, then the groups by young machines' rate, and
    # last, apart, the groups whose rate ratio's interval includes 1 (the 'nearly' of 'nearly every'), young in grey
    clear = crude.lo.loc[p.groups] > 1
    by_rate = crude.loc[p.groups].sort_values('young_rate', ascending=False, kind='mergesort').index.tolist()
    order = [g for g in by_rate if clear[g]] + [g for g in by_rate if not clear[g]]
    unclear = order[int(clear.sum()):]
    ys = {ALL: 0.0} | {g: 1.25 + i + (0.4 if g in unclear else 0) for i, g in enumerate(order)}
    for g, y in ys.items():
        r = crude.loc[g]
        ax.plot([r.older_rate, r.young_rate], [y, y], color=S.GREY, lw=1.0, zorder=2)
        ax.plot(r.older_rate, y, 'o', mfc=S.WHITE, mec=S.GREY_DARK, mew=1.0, ms=4, zorder=3)
        ax.plot(r.young_rate, y, 'o', color=S.GREY if g in unclear else S.COBALT, ms=4, zorder=4)
    S.check('fig10 (a) every group runs higher on young machines', 1, int((crude.ratio > 1).all()))
    S.check('fig10 (a) the grey groups\' rate-ratio intervals include 1, and only theirs', 1,
            int(all(crude.lo[g] <= 1 <= crude.hi[g] for g in unclear) and (crude.lo.drop(unclear) > 1).all()))
    S.check('fig10 (a) groups whose interval includes 1: the "nearly" of "nearly every" (at most two)', 1,
            int(0 < len(unclear) <= 2 and p.groups_word == 'nearly every'))
    a = crude.loc[ALL]
    # the two rates either side of the row, and the ratio above it; the rates' backings over the ratio's, so the grid
    # line at 3 stops cleanly between them
    for value, x, ha in ((a.older_rate, a.older_rate / 1.3, 'right'), (a.young_rate, a.young_rate * 1.25, 'left')):
        text = S.num(value, 1)
        S.check(f'fig10 (a) label {text}', round(value, 1), float(text))
        S.label(ax, x, 0, text, ha=ha, bbox=backing, zorder=2.6)
    text = f'{S.num(p.ratio_all, 2)}×'
    S.check(f'fig10 (a) label {text}', round(p.ratio_all, 2), float(text.rstrip('×')))
    S.label(ax, np.sqrt(a.older_rate * a.young_rate), -1.15, text, ha='center', size=S.FONT, weight='bold',
            color=S.GREEN, bbox=backing, zorder=2.5)
    top = crude.loc[order[0]]                 # the first group's marks carry the direct labels
    S.label(ax, top.older_rate / 1.3, ys[order[0]], 'Older', ha='right', bbox=backing, zorder=2.5)
    S.label(ax, top.young_rate * 1.3, ys[order[0]], 'Young', ha='left', bbox=backing, zorder=2.5)
    S.label(ax, crude.young_rate[unclear].max() * 1.8, np.mean([ys[g] for g in unclear]),
            'Ratio’s interval\nincludes 1', ha='left', linespacing=1.0, bbox=backing, zorder=2.5)
    ax.set_xscale('log')
    ax.set_xlim(0.04, 22)
    ax.set_xticks([0.1, 0.3, 1, 3, 10], ['0.1', '0.3', '1', '3', '10'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_yticks(list(ys.values()), [SHOWN.get(g, g) for g in ys])
    ax.set_ylim(max(ys.values()) + 0.55, -1.75)
    ax.set_xlabel('Per 100 machine-months (log scale)')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'Ticket rates')

    # (b) within-model share ratio of each group, in the rows of (a); the two that pass the test in cobalt
    for g in order:
        if g not in adj.index:      # outside the share ratio's base: say so rather than leave the row empty
            S.check(f'fig10 (b) the row without a share ratio is Not categorized ({g})', 'Not categorised', g)
            S.label(bx, 1, ys[g], 'excluded', ha='center', bbox=backing, zorder=2.5)
            continue
        r, y = adj.loc[g], ys[g]
        focal = g in passing
        colour = S.COBALT if focal else S.GREY
        bx.plot([r.share_ratio_lo, r.share_ratio_hi], [y, y], color=colour, lw=1.0, solid_capstyle='butt', zorder=3)
        bx.plot(r.share_ratio_mh, y, 'o', color=colour, ms=4 if focal else 3.3, zorder=4)
        if focal:
            text = S.num(p.share_ratio[g], 2)
            S.check(f'fig10 (b) label {g} {text}', round(r.share_ratio_mh, 2), float(text))
            if r.share_ratio_mh > 1:
                S.label(bx, r.share_ratio_hi * 1.08, y, text, ha='left', bbox=backing, zorder=2.5)
            else:
                S.label(bx, r.share_ratio_lo / 1.08, y, text, ha='right', bbox=backing, zorder=2.5)
    bx.axvline(1, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)
    bx.sharey(ax)
    bx.tick_params(axis='y', labelleft=False, length=0)
    bx.set_xscale('log')
    bx.set_xlim(0.25, 4.6)
    bx.set_xticks([0.5, 1, 2, 4], ['0.5', '1', '2', '4'])
    bx.xaxis.set_minor_locator(NullLocator())
    bx.set_xlabel('Share ratio (log scale)')
    S.clean(bx, grid='x', left=False)
    S.panel(bx, 'b', 'Within model')

    # (c) the extra tickets on young machines in one bar, the within-model part in cobalt
    S.check('fig10 (c) the within-model part lies inside the extra tickets', 1, int(0 < p.within < p.extra))
    cx.barh(0, p.within, height=0.6, color=S.COBALT, zorder=3)
    cx.barh(0, p.extra - p.within, left=p.within, height=0.6, color=S.GREY_FILL, zorder=3)
    for text, value in ((S.num(p.extra), p.extra), (f'{S.num(p.within)} ({S.pct(share_within)})', p.within)):
        S.check(f'fig10 (c) label {text}', round(value), float(text.split(' ')[0].replace(',', '')))
    S.check(f'fig10 (c) label ({S.pct(share_within)})', round(100 * share_within),
            float(S.pct(share_within).rstrip('%')))
    S.label(cx, p.extra + 25, 0, S.num(p.extra), bbox=backing, zorder=2.5)
    # just clear of the grid line at 0, so the backing leaves that line whole
    S.label(cx, 20, -0.42, f'Within model {S.num(p.within)} ({S.pct(share_within)})', va='bottom', bbox=backing,
            zorder=2.5)
    cx.set_ylim(0.45, -1.3)
    cx.set_yticks([])
    cx.set_xlim(0, 1850)
    cx.set_xticks([0, 500, 1000, 1500])
    S.thousands_axis(cx.xaxis)
    S.clean(cx, grid='x', left=False)
    S.panel(cx, 'c', 'Extra tickets')

    # (d) Touchscreen tickets by install cohort; the connector gives 2022-23 as a multiple of 2024-26
    names = list(p.cohorts.index)
    for i, c in enumerate(names):
        r = p.cohorts.loc[c]
        dx.bar(i, r.rate, width=0.62, color=S.COBALT if c == p.cluster else S.GREY_FILL, zorder=3)
        line, = dx.plot([i, i], [r.lo, r.hi], color=S.GREY_DARK, lw=1.0, solid_capstyle='butt', zorder=4)
        line.set_path_effects(CASING)
    i_c, i_n = names.index(p.cluster), names.index(p.newest)
    r_c, r_n = p.cohorts.loc[p.cluster], p.cohorts.loc[p.newest]
    text = S.num(r_c.rate, 2)
    S.check(f'fig10 (d) label {text}', round(r_c.rate, 2), float(text))
    S.label(dx, i_c, r_c.hi + 0.06, text, ha='center', va='bottom', bbox=backing, zorder=2.5)
    xc = (i_c + i_n) / 2                      # the connector, between the two bars
    dx.plot([i_c + 0.31, xc, xc, i_n - 0.31], [r_c.rate, r_c.rate, r_n.rate, r_n.rate], color=S.GREY_DARK, lw=0.6,
            zorder=2)
    text = f'{S.num(ratio_cluster, 1)}×'
    S.check(f'fig10 (d) label {text}', round(ratio_cluster, 1), float(text.rstrip('×')))
    S.label(dx, xc + 0.08, (r_c.rate + max(r_n.hi, r_n.rate)) / 2, text, ha='left', bbox=backing, zorder=2.5)
    dx.set_xticks(range(len(names)), [dashed(c) for c in names])
    dx.tick_params(axis='x', length=0)
    dx.set_xlim(-0.55, len(names) - 0.45)
    dx.set_ylim(0, 2.3)
    dx.set_yticks([0, 1.0, 2.0], ['0', '1.0', '2.0'])
    dx.set_xlabel('Install years')
    dx.set_ylabel(f'{FOCUS}\ntickets per 100\nmachine-months')   # fig12's wording, on three lines to fit
    S.clean(dx, grid='y', left=False)
    S.panel(dx, 'd', f'{FOCUS} by install cohort')

    # Nothing drawn is clipped: every mark, interval, and bar inside its panel's limits
    S.check('fig10 (a) marks inside the axis', 1, int(ax.get_xlim()[0] < crude.older_rate.min()
                                                      and crude.young_rate.max() * 1.6 < ax.get_xlim()[1]))
    S.check('fig10 (b) intervals inside the axis', 1, int(bx.get_xlim()[0] < adj.share_ratio_lo.min()
                                                          and adj.share_ratio_hi.max() < bx.get_xlim()[1]))
    S.check('fig10 (c) bars inside the axis', 1, int(p.extra < cx.get_xlim()[1]))
    S.check('fig10 (d) intervals inside the axis', 1, int(p.cohorts.hi.max() + 0.3 < dx.get_ylim()[1]))

    centre_under_panel(fig, ax)
    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share).replace('%', chr(92) + '%')  # noqa: E731
    return (f'Young machines run {S.num(p.rate_young, 1)} tickets per 100 machine-months vs. {S.num(p.rate_old, 1)} '
            f'for older ones ({S.num(p.ratio_all, 2)} times), with higher rates in {p.groups_word} request group. '
            f'(a)~By request group; (b)~share ratios; (c)~{S.num(p.extra)} extra tickets, {pc(share_within)} within '
            f'model; (d)~{FOCUS} by cohort; {p.interval_level}\\% intervals.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
