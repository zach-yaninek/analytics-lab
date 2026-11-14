#!/usr/bin/env python3
"""Report figure 12 (Results, Electronics cases): per machine-month, Electronics runs 1.71 times as often on young
machines, near the 1.66 for all tickets; Touchscreen stands out at 4.2 times, and of its 411 tickets on young
machines, 344 are connector reseats or replacements, 402 are on the four 2.0 models, and 315 are on 2022-23 installs;
and its rate steps from 0.36 to 1.61 per 100 between Jan-Apr and May-Aug 2022 installs.

(a) The young vs. older rate ratio per installed machine-month, all models together, of all tickets, of Electronics,
    and of the Electronics Categories with 30 or more tickets in each age group (the script's threshold for showing a
    unit), with 95% bootstrap intervals over accounts. Touchscreen, the highest, is cobalt.
(b) Touchscreen's 411 tickets on young machines and the three subsets the report names, each drawn against the 411.
(c) Touchscreen tickets per 100 installed machine-months on the comparison models' machines installed January to
    April and May to August 2022 (counted by the case-list builder from IPA's installed-base list; the outputs give
    no interval for these two windows, so none is drawn).

Inputs: the tables of fig10_request_types.part_a() (notebook 07's recomputation of Part A), and
verification/outputs/electronics/ec_counts.csv, ec_subsets.csv, ec_edge.csv (the case-list builder's aggregate
tables); followups/ag_by_status.csv, ag_install_pooled.csv; fleet/fx_model_rates.csv. Notebook 07 checks the same
numbers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import fig10_request_types as F10  # noqa: E402  (notebook 07's recomputation, shared with figure 10)
import report_style as S  # noqa: E402

NAME = 'fig12_electronics'
LABEL = 'fig:electronics'
SHORT = 'Electronics cases'

EC = S.OUT / 'electronics'
AGES, ALL, FOCUS = F10.AGES, F10.ALL, F10.FOCUS
WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine'}


def and_join(names):
    """['a', 'b', 'c'] -> 'a, b, and c'."""
    return ' and '.join(names) if len(names) < 3 else ', '.join(names[:-1]) + f', and {names[-1]}'


def short(label):
    """'January to April 2022' -> ('Jan–Apr', '2022') (notebook 07)."""
    first, last = label.split(' to ')
    return f'{first[:3]}–{last[:3]}', last.split()[-1]


def young_touchscreen(p, subsets):
    """Touchscreen's young-machine tickets on each comparison model, split by install cohort, as notebook 07 rebuilds
    them from the install-year counts and rp_pairs.csv; returns the counts on the 2.0 models and on the 2022-23
    installs, the 2.0 models (most tickets first), and the young-machine total."""
    ts = p.ts_years
    mixed = ts.install_year[(ts.under4_machines > 0) & (ts.under4_machines < ts.machines)].unique()
    S.check('fig12 one install year mixes ages', 1, len(mixed))
    year = int(mixed[0])
    before, after = ts.install_year < year, ts.install_year > year
    S.check('fig12 earlier install years are all older, later all young', 1,
            int((ts.under4_machines[before] == 0).all() and (ts.under4_machines[after] == ts.machines[after]).all()))
    seen = p.seen[(p.seen.category == FOCUS) & p.seen.model.isin(p.comparison)]
    old_mixed = seen[(seen.install_year == year) & (seen.age_group == AGES[1])].groupby('model').size()
    S.check(f'fig12 rp_pairs.csv has every older-machine {FOCUS} ticket on {year} installs',
            p.adj_cats.at[FOCUS, 'plus4_tickets'] - ts.tickets[before].sum(), int(old_mixed.sum()))
    S.check('fig12 the install-year table covers the comparison models', 1,
            int(sorted(ts.model.unique()) == p.comparison))
    old_mixed = old_mixed.reindex(p.comparison, fill_value=0)

    def per_model(rows):
        return ts[rows].groupby('model').tickets.sum().reindex(p.comparison, fill_value=0)

    first, last = F10.cohort_years(p.cluster)
    S.check('fig12 the mixed year sits in the cluster cohort, just before the newest', 1,
            int(first <= year <= last and last + 1 == F10.cohort_years(p.newest)[0]
                and F10.cohort_years(p.newest)[1] >= ts.install_year.max()))
    by_model = pd.DataFrame({
        'older': per_model(before) + old_mixed,
        'young_cluster': per_model(ts.install_year.between(first, last)) - old_mixed,
        'young_newest': per_model(ts.install_year.between(*F10.cohort_years(p.newest))),
        'young': per_model(ts.install_year >= year) - old_mixed})
    S.check('fig12 young = the two young cohorts', 1,
            int((by_model.young == by_model.young_cluster + by_model.young_newest).all()))
    models = pd.read_csv(S.OUT / 'fleet' / 'fx_model_rates.csv', usecols=['model', 'family'])
    v2 = sorted(models.model[(models.family == 'scrubEx') & models.model.str.endswith('2.0')])
    v2_order = by_model.loc[v2, 'young'].sort_values(ascending=False, kind='mergesort').index.tolist()
    n_v2, n_cluster = int(by_model.loc[v2, 'young'].sum()), int(by_model.young_cluster.sum())
    a, b = by_model.young, by_model.older
    script = p.adj_cats.loc[FOCUS]
    S.check(f'fig12 {FOCUS}: per-model counts give the script\'s share ratio', script.share_ratio_mh,
            F10.mh_share(a, b, p.n1, p.n0), 1e-9)
    S.check(f'fig12 {FOCUS}: per-model counts give the script\'s excess', script.excess_under4_tickets,
            F10.mh_excess(a, b, p.n1, p.n0), 1e-6)
    builder = pd.read_csv(EC / 'ec_counts.csv').set_index('key').value
    S.check('fig12 the case-list builder counts the same tickets on the 2.0 models',
            int(builder['focus_under4_core_models']), n_v2)
    S.check('fig12 the case-list builder counts the same tickets on 2022-23 installs',
            int(subsets.at['u4_coh', 'tickets']), n_cluster)
    return n_v2, n_cluster, v2_order, int(by_model.young.sum()), builder


def plot(out_dir=S.FIG_DIR):
    p = F10.part_a('fig12')
    crude = p.crude
    months_young, months_old = p.months

    # (a) Electronics and its Categories, young vs. older, all models together
    rows = p.rates[(p.rates.level == 'category') & (p.rates.group == 'Electronics')].set_index('type')
    cats = pd.DataFrame({'young': rows.under4_tickets, 'older': rows.plus4_tickets,
                         'young_rate': 100 * rows.under4_tickets / months_young,
                         'older_rate': 100 * rows.plus4_tickets / months_old,
                         'lo': rows.rate_ratio_lo, 'hi': rows.rate_ratio_hi})
    cats['ratio'] = cats.young_rate / cats.older_rate
    S.check('fig12 Category ratios = ag_type_rates.csv (relative)', 0,
            float((cats.ratio / rows.rate_ratio - 1).abs().max()), 1e-7)   # the CSV keeps about 10 digits
    S.check('fig12 Category months = the age groups\' months', 0,
            float(np.abs(rows[['under4_months', 'plus4_months']].to_numpy() - [months_young, months_old]).max()), 1e-3)
    min_tickets = p.defs['min_shown_tickets']
    shown = cats[(cats.young >= min_tickets) & (cats.older >= min_tickets)].sort_values('ratio', ascending=False)
    stands_out = shown.ratio.idxmax()
    S.check('fig12 every drawn interval holds its ratio', 1,
            int(((shown.lo <= shown.ratio) & (shown.ratio <= shown.hi)).all()))
    ratio_el, ratio_ts = crude.at['Electronics', 'ratio'], cats.at[FOCUS, 'ratio']
    ts_young = int(cats.at[FOCUS, 'young'])

    # (b) Touchscreen's young-machine tickets and the subsets the report names
    subsets = pd.read_csv(EC / 'ec_subsets.csv').set_index('key')
    S.check('fig12 the builder\'s young-machine Touchscreen tickets = ag_type_rates.csv', ts_young,
            int(subsets.at['u4_focus', 'tickets']))
    n_conn = int(subsets.at['u4_conn', 'tickets'])
    S.check('fig12 the connector subset is Connector Reseat/Replace', 1,
            int(subsets.at['u4_conn', 'label'] == 'of which Connector Reseat/Replace'))
    n_v2, n_cluster, v2_order, n_young_ts, builder = young_touchscreen(p, subsets)
    S.check('fig12 every young-machine Touchscreen ticket is on a comparison model', ts_young, n_young_ts)

    # (c) the two 2022 install windows
    edge = pd.read_csv(EC / 'ec_edge.csv')
    edge['rate'] = 100 * edge.tickets / edge.months
    S.check('fig12 window rates = ec_edge.csv', 0, float((edge.rate - edge.rate_per_100).abs().max()), 1e-12)
    year22 = pd.read_csv(F10.FU / 'ag_install_pooled.csv', dtype={'install': str}).query(
        f"category == '{FOCUS}' and unit == 'year' and install == '2022'").iloc[0]
    S.check('fig12 the two windows fit inside the 2022 install year', 1,
            int(edge.machines.sum() <= year22.machines and edge.months.sum() <= year22.months
                and edge.tickets.sum() <= year22.tickets))
    (early, y0), (late, y1) = map(short, edge.label)
    rate_early, rate_late = edge.rate

    # The case list: every unplanned Electronics ticket on the fleet machines
    el_bands = p.bands[p.bands.type == 'Electronics']
    n_el = int(el_bands.tickets.sum())
    status = pd.read_csv(F10.FU / 'ag_by_status.csv')
    S.check('fig12 Electronics tickets = ag_by_status.csv', int(status.tickets[status.type == 'Electronics'].sum()),
            n_el)
    S.check('fig12 Electronics tickets = the case-list builder\'s', int(builder['tickets']), n_el)

    S.report_check('fig12 Electronics: young vs. older rate per machine-month', '1.71', S.num(ratio_el, 2))
    S.report_check('fig12 all tickets: young vs. older rate', '1.66', S.num(p.ratio_all, 2))
    S.report_check('fig12 the Electronics Category that stands out', FOCUS, stands_out)
    S.report_check('fig12 Touchscreen: young vs. older rate per machine-month', '4.2', S.num(ratio_ts, 1))
    S.report_check('fig12 Touchscreen tickets on young machines', '411', S.num(ts_young))
    S.report_check('fig12 young-machine Touchscreen tickets that are connector reseats or replacements', '344',
                   S.num(n_conn))
    S.report_check('fig12 young-machine Touchscreen tickets on the 2.0 models', '402', S.num(n_v2))
    S.report_check('fig12 number of 2.0 models', 'four', WORDS[len(v2_order)])
    S.report_check('fig12 the 2.0 models, most young-machine Touchscreen tickets first',
                   'LVD-Remote-2.0, MV-2.0, LVRR-WP-2.0, and SV-48-2.0', and_join(v2_order))
    S.report_check('fig12 young-machine Touchscreen tickets on 2022-23 installs', '315', S.num(n_cluster))
    S.report_check('fig12 the install cohort of the 315', '2022–23', F10.dashed(p.cluster))
    S.report_check('fig12 the earlier install window', 'Jan–Apr', early)
    S.report_check('fig12 the later install window', 'May–Aug', late)
    S.report_check('fig12 the windows\' install year', '2022', y0 if y0 == y1 else f'{y0}/{y1}')
    S.report_check('fig12 Touchscreen per 100 machine-months, Jan-Apr 2022 installs', '0.36', S.num(rate_early, 2))
    S.report_check('fig12 Touchscreen per 100 machine-months, May-Aug 2022 installs', '1.61', S.num(rate_late, 2))
    S.check('fig12 (a) tickets a Category needs in each age group to be drawn (notebook 07)', 30, min_tickets)
    for label, r in zip((early, late), edge.itertuples()):  # the caption's ticket counts give the drawn rates
        S.check(f'fig12 caption: {label} tickets give its rate', round(r.rate, 2), round(100 * r.tickets / r.months, 2))
    S.check('fig12 intervals: 95% (docs/09 §6)', 95, p.interval_level)

    fig, (ax, bx, cx) = S.figure(2.1, ncols=3, width_ratios=[0.98, 1.1, 0.78])

    # (a) rate ratios: all tickets and Electronics on top, then the Categories, highest first
    ref = [(ALL, p.ratio_all, crude.at[ALL, 'lo'], crude.at[ALL, 'hi']),
           ('Electronics', ratio_el, crude.at['Electronics', 'lo'], crude.at['Electronics', 'hi'])]
    cat_rows = [(c, r.ratio, r.lo, r.hi) for c, r in shown.iterrows()]
    ys = [0.0, 1.0] + [2.6 + i for i in range(len(cat_rows))]
    for (name, ratio, lo, hi), y in zip(ref + cat_rows, ys):
        focal = name == stands_out
        colour = S.COBALT if focal else S.GREY_DARK if name in (ALL, 'Electronics') else S.GREY
        ax.plot([lo, hi], [y, y], color=colour, lw=1.0, solid_capstyle='butt', zorder=3)
        ax.plot(ratio, y, 'o', color=colour, ms=4 if focal or name in (ALL, 'Electronics') else 3.3, zorder=4)
        if focal:
            text = S.num(ratio, 1)
            S.check(f'fig12 (a) label {name} {text}', round(ratio, 1), float(text))
            S.label(ax, lo / 1.1, y, text, ha='right', size=S.FONT, weight='bold', color=S.GREEN)
        elif name in (ALL, 'Electronics'):
            text = S.num(ratio, 2)
            S.check(f'fig12 (a) label {name} {text}', round(ratio, 2), float(text))
            S.label(ax, hi * 1.08, y, text, ha='left')
    ax.axvline(1, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)
    ax.set_xscale('log')
    ax.set_xlim(0.55, 8)
    ax.set_xticks([1, 2, 4], ['1', '2', '4'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_yticks(ys, [F10.SHOWN.get(r[0], r[0]) for r in ref + cat_rows])
    ax.set_ylim(ys[-1] + 0.7, -0.7)
    ax.set_xlabel('Rate ratio, young vs. older (log scale)')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'Electronics by Category')

    # (b) Touchscreen's young-machine tickets and three subsets, each against the 411
    rows_b = [('All', ts_young), ('Connector reseats or replacements', n_conn),
              (f'On the {WORDS[len(v2_order)]} 2.0 models', n_v2), (f'On {F10.dashed(p.cluster)} installs', n_cluster)]
    for i, (name, value) in enumerate(rows_b):
        y = 1.15 * i
        bx.barh(y, value, height=0.36, color=S.COBALT, zorder=3)
        if value < ts_young:
            bx.barh(y, ts_young - value, left=value, height=0.36, color=S.GREY_FILL, zorder=3)
        S.label(bx, 2, y - 0.25, name, va='bottom')
        text = S.num(value)
        S.check(f'fig12 (b) label {name} {text}', value, float(text.replace(',', '')))
        S.label(bx, ts_young + 8, y, text)
    bx.set_ylim(1.15 * (len(rows_b) - 1) + 0.5, -0.8)
    bx.set_yticks([])
    bx.set_xlim(0, 470)
    bx.set_xticks([0, 100, 200, 300, 400])
    bx.set_xlabel('Tickets')
    S.clean(bx, grid='x', left=False)
    S.panel(bx, 'b', f'{FOCUS}, young machines')

    # (c) the step between the two 2022 install windows
    for i, (label, rate) in enumerate(((early, rate_early), (late, rate_late))):
        cx.bar(i, rate, width=0.56, color=S.COBALT if rate == max(rate_early, rate_late) else S.GREY_FILL, zorder=3)
        text = S.num(rate, 2)
        S.check(f'fig12 (c) label {label} {text}', round(rate, 2), float(text))
        S.label(cx, i, rate + 0.04, text, ha='center', va='bottom')
    cx.set_xticks([0, 1], [early, late])
    cx.tick_params(axis='x', length=0)
    cx.set_xlim(-0.55, 1.55)
    cx.set_ylim(0, 1.9)
    cx.set_yticks([0, 0.5, 1.0, 1.5], ['0', '0.5', '1.0', '1.5'])
    cx.set_xlabel('Install months')
    cx.set_ylabel(f'{FOCUS} tickets\nper 100 machine-months')
    S.clean(cx, grid='y', left=False)
    S.panel(cx, 'c', f'{y0} installs')

    # Nothing drawn is clipped: every interval, bar, and label inside its panel's limits
    lo_all = min(r[2] for r in ref + cat_rows)
    hi_all = max(r[3] for r in ref + cat_rows)
    S.check('fig12 (a) intervals inside the axis', 1, int(ax.get_xlim()[0] < lo_all and hi_all < ax.get_xlim()[1]))
    S.check('fig12 (b) bars inside the axis', 1, int(ts_young < bx.get_xlim()[1]))
    S.check('fig12 (c) bars inside the axis', 1, int(max(rate_early, rate_late) + 0.2 < cx.get_ylim()[1]))

    F10.centre_under_panel(fig, ax)
    S.export(fig, NAME, out_dir)
    pc = chr(92) + '%'  # LaTeX: an escaped percent sign
    return (f'Per machine-month, Electronics runs {S.num(ratio_el, 2)} times as often on young machines, near the '
            f'{S.num(p.ratio_all, 2)} for all tickets, and {FOCUS} stands out at {S.num(ratio_ts, 1)} times. '
            f'(a)~Categories with {S.num(min_tickets)} or more tickets in each age group, {p.interval_level}{pc} '
            f'intervals; (b)~its {S.num(ts_young)} young-machine tickets; (c)~from {S.num(edge.tickets.iloc[0])} and '
            f'{S.num(edge.tickets.iloc[1])} tickets.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
