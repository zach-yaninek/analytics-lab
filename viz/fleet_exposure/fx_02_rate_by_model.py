#!/usr/bin/env python3
"""Fleet chart 2: unplanned tickets per 100 installed machine-months by model, with 95% intervals.

Raw ticket counts by model mostly measure how many machines of each model IPA has installed. Dividing each model's
unplanned tickets by its installed machine-months (from IPA's installed-base list) gives a rate that can be compared
across models, and the interval shows whether a model's rate is really different from the fleet's or within the
noise. One dot per model with its own rate (at least 100 installed machine-months; smaller models are pooled in the
analysis and not shown), sorted by rate, with the model's machine count on the axis label. The line through each
dot is the 95% interval (cluster bootstrap over accounts; the wider of the bootstrap and Byar's Poisson interval for
models in fewer than 10 accounts). Blue = interval wholly above the fleet rate, orange = wholly below, gray = the
interval includes it. The vertical line is the fleet rate. The title names the highest-rate model and its multiple
of the fleet and counts the models above the fleet. The rates are crude (not adjusted for age), so one footer note
says which of the above-fleet models stay above on the age-standardised ratio from the same analysis, and how far
their age mix alone lifts them (machines under 4 years old run above the fleet rate, chart 3, and the newer models'
machines are mostly that young). The note does not call every above-fleet model younger: an age mix can run above
the fleet rate just because a model has few machines in the oldest, lowest-rate band.

Inputs:  verification/outputs/fleet/fx_model_rates.csv   one row per model: machines, accounts, months, tickets,
                                                         rate_per_100, ci_lo/ci_hi (ci_method), vs_fleet,
                                                         ratio_to_fleet, expected_age_only, age_std_ratio,
                                                         age_std_lo/hi, age_std_vs_fleet, own_rate
         verification/outputs/fleet/fx_summary.json      fleet rate and totals, period, min_type_months,
                                                         min_clusters
         verification/outputs/fleet/fx_age_rates.csv     fleet rate by age band (checks the note's age claim)
         verification/outputs/fleet/fx_machine_flags.csv expected tickets per machine (recovers the fitted age
                                                         factors for the same check; nothing from it is drawn)
Output:  viz/figures/fx_02_rate_by_model.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_02_rate_by_model.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_02_rate_by_model.png'
ROW_IN = 0.29             # inches per model row
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
BOOT = 'cluster bootstrap'
WIDER = 'wider of bootstrap and Byar'
CLASSES = [  # vs_fleet value, colour of the dot, colour of the interval, legend text
    ('above', style.BLUE, style.BLUE, 'Above the fleet: 95% interval wholly above the fleet rate'),
    ('below', style.ORANGE, style.ORANGE, 'Below the fleet: interval wholly below'),
    ('not different', style.GRAY, style.GRAY_LIGHT, 'Not different: interval includes the fleet rate'),
    ('not estimable (one account)', style.GRAY, style.GRAY_LIGHT, 'Not estimable: one account'),
]
YOUNG = ['<1', '1-2', '2-4']  # the youngest age bands (fx_summary definitions.age_bands), under YOUNG_YEARS
YOUNG_YEARS = int(YOUNG[-1].split('-')[1])


def names(models):
    """'A', 'A and B', 'A, B and C'."""
    models = list(models)
    return models[0] if len(models) == 1 else ', '.join(models[:-1]) + ' and ' + models[-1]


def age_factors():
    """Fitted age factor per age band, relative to the fleet's months-weighted mean, recovered from the per-machine
    expected tickets of the main model + age fit (expected / months = model factor x age factor, so within one
    model group the ratio between age bands is the ratio of age factors). Used only for a check."""
    mf = fleet.load('machine_flags')
    mf = mf[mf.months > 0].assign(per_month=lambda x: x.expected / x.months)
    cells = mf.groupby(['rate_group', 'age_band']).per_month.agg(['min', 'max', 'first'])
    style.check('fx_02 one expected rate per model group x age band (machine flags)', 0,
                float((cells['max'] - cells['min']).max()), 1e-9)
    piv = cells['first'].unstack()
    ref = piv.notna().sum().idxmax()  # the age band held by the most model groups
    rel = piv.div(piv[ref], axis=0)
    spread = float((rel.max() - rel.min()).max())  # the same age factor in every model group (main effects)
    style.check('fx_02 age factors identical across model groups', 0, spread, 1e-9)
    return rel.mean()


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    F, D = S['fleet'], S['definitions']
    f = fleet.fleet_rate(S)
    m = fleet.load('model_rates')

    # Fleet totals: the fleet rate is a ratio of totals, and the model rows add up to the fleet.
    style.check('fx_02 fleet rate = 100 x tickets / months (summary)', f, 100 * F['tickets'] / F['months'], 1e-9)
    style.check('fx_02 fleet rate = 100 x tickets / months (all model rows)', f,
                100 * m.tickets.sum() / m.months.sum(), 1e-9)
    style.check('fx_02 fleet rate column = summary', 0, float((m.fleet_rate_per_100 - f).abs().max()), 1e-9)
    style.check('fx_02 model tickets = fleet tickets', F['tickets'], m.tickets.sum(), 1e-6)
    style.check('fx_02 model machines = fleet machines with exposure', F['machines_exposed'], int(m.machines.sum()))
    style.check('fx_02 own rate = at least min_type_months installed months', 0,
                int((m.own_rate != (m.months >= D['min_type_months'])).sum()))

    d = m[m.own_rate].copy()
    rest = m[~m.own_rate]
    # Rates, intervals and classes as drawn, recomputed from the counts and the interval rule (F8).
    style.check('fx_02 rates = 100 x tickets / months', 0,
                float((100 * d.tickets / d.months - d.rate_per_100).abs().max()), 1e-9)
    weak = (d.accounts < D['min_clusters']) | (d.tickets == 0)
    style.check('fx_02 interval method = rule (accounts < min_clusters or no tickets)', 0,
                int((d.ci_method != np.where(weak, WIDER, BOOT)).sum()))
    lo = np.where(weak, np.fmin(d.boot_lo, d.byar_lo), d.boot_lo)
    hi = np.where(weak, np.fmax(d.boot_hi, d.byar_hi), d.boot_hi)
    style.check('fx_02 drawn intervals = bootstrap / wider-of rule', 0,
                float(max(np.abs(lo - d.ci_lo).max(), np.abs(hi - d.ci_hi).max())), 1e-9)
    # The colour comes from vs_fleet (the bootstrap interval of the ratio to the fleet); it must agree with where
    # the drawn rate interval sits against the fleet line.
    drawn = np.select([d.ci_lo > f, d.ci_hi < f], ['above', 'below'], 'not different')
    single = d.vs_fleet.str.startswith('not estimable')
    style.check('fx_02 colour class = drawn interval against the fleet line', 0,
                int(((drawn != d.vs_fleet) & ~single).sum()))
    style.check('fx_02 every class has a colour', 1, int(set(d.vs_fleet) <= {c[0] for c in CLASSES}))
    age_cls = np.select([d.age_std_lo > 1, d.age_std_hi < 1], ['above', 'below'], 'not different')
    style.check('fx_02 age-standardised class = its interval against 1', 0,
                int(((age_cls != d.age_std_vs_fleet) & ~d.age_std_vs_fleet.str.startswith('not estimable')).sum()))
    style.check('fx_02 age-standardised ratio = tickets / age-only expected', 0,
                float((d.tickets / d.expected_age_only - d.age_std_ratio).abs().max()), 1e-9)

    d = d.sort_values(['rate_per_100', 'model'], ascending=[True, False], kind='mergesort')  # highest on top
    n = len(d)
    top = d.iloc[-1]
    top_ratio = top.rate_per_100 / f
    style.check('fx_02 top ratio = ratio_to_fleet', top.ratio_to_fleet, top_ratio, 1e-9)
    style.check('fx_02 top model has the highest rate shown', 1, int(top.rate_per_100 == d.rate_per_100.max()))
    counts = d.vs_fleet.value_counts()
    n_above, n_below = int(counts.get('above', 0)), int(counts.get('below', 0))
    style.check('fx_02 models above (drawn intervals)', n_above, int((d.ci_lo > f).sum()))
    style.check('fx_02 models below (drawn intervals)', n_below, int((d.ci_hi < f).sum()))
    style.check('fx_02 models shown + pooled = all models', len(m), n + len(rest))
    months_share = d.months.sum() / F['months']
    style.check('fx_02 share of months shown = 1 - pooled share', 1 - rest.months.sum() / m.months.sum(),
                months_share, 1e-9)
    style.check('fx_02 fleet months = model months', F['months'], m.months.sum(), 1e-6)

    # Age note: which above-fleet models stay above once age is allowed for, and why their ratios fall.
    above = d[d.vs_fleet == 'above'].sort_values(['rate_per_100', 'model'], ascending=[False, True])
    stay = above[above.age_std_vs_fleet == 'above']
    drop = above[above.age_std_vs_fleet != 'above']
    join = d[(d.vs_fleet != 'above') & (d.age_std_vs_fleet == 'above')]
    # Age mix alone: the fleet's rate for each machine's age applied to the model's months, over the crude fleet
    # rate (= crude ratio over the age-standardised ratio). Above 1 = the months sit in higher-rate age bands (mostly
    # the bands under 4 years, but also an absence of the oldest, lowest-rate band).
    age_mix = above.expected_age_only / (above.months * f / 100)
    style.check('fx_02 age mix = crude ratio / age-standardised ratio', 0,
                float((age_mix - above.ratio_to_fleet / above.age_std_ratio).abs().max()), 1e-9)
    style.check('fx_02 every above-fleet model has a higher-rate age mix (age lowers each ratio)', 1,
                int((age_mix > 1).all()))
    lift_lo, lift_hi = above.loc[age_mix.idxmin()], above.loc[age_mix.idxmax()]
    b = age_factors()
    style.check('fx_02 age bands named here = analysis age bands', 1, int(set(b.index) == set(D['age_bands'])))
    style.check(f'fx_02 every band under {YOUNG_YEARS} years has a higher age factor than every older band', 1,
                int(b[YOUNG].min() > b.drop(YOUNG).max()))
    style.check('fx_02 interval level 95% (z95 of the analysis)', 1.96, D['z95'], 0.001)
    ages = fleet.load('age_rates').set_index('age_band')
    style.check(f'fx_02 crude rate above the fleet in every band under {YOUNG_YEARS} years (chart 3)', 1,
                int((ages.loc[YOUNG, 'vs_fleet'] == 'above').all()))

    title = (f'{n_above} of {n} models are above the fleet rate; {top.model} is highest at {top_ratio:.1f}× '
             f'the fleet')

    # ---- draw ----
    # Wide enough for the one-line title (the model name in it comes from the data).
    fig, ax = style.figure(max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN), 4.6 + ROW_IN * n)
    y = np.arange(n)
    xmax = d.ci_hi.max() * 1.1
    pad, label_w = xmax * 0.012, xmax * 0.045  # value-label offset and approximate width (4 characters)
    ax.axvline(f, color=style.INK2, lw=1, zorder=1)
    handles = []
    for cls, dot, line, text in CLASSES:
        sel = (d.vs_fleet == cls).to_numpy()
        if not sel.any():
            continue
        ax.hlines(y[sel], d.ci_lo[sel], d.ci_hi[sel], color=line, lw=2, zorder=2)
        ax.scatter(d.rate_per_100[sel], y[sel], s=55, color=dot, edgecolors=style.SURFACE, linewidths=1.2,
                   zorder=3)
        handles.append(Line2D([], [], color=line, lw=2, marker='o', ms=7.5, mfc=dot, mec=style.SURFACE,
                              label=f'{text} ({int(sel.sum())})'))
    for yi, row in zip(y, d.itertuples()):
        # Right of the interval, unless that lands on the fleet line: then left of the interval.
        on_line = row.ci_hi + pad < f < row.ci_hi + pad + label_w
        x, ha = (row.ci_lo - pad, 'right') if on_line else (row.ci_hi + pad, 'left')
        hot = row.vs_fleet == 'above'
        ax.text(x, yi, f'{row.rate_per_100:.1f}', va='center', ha=ha, fontsize=9.5,
                color=style.INK if hot else style.INK2, weight='bold' if row.model == top.model else 'normal')
    ax.text(f + pad, n - 0.45, f'Fleet: {f:.1f}', va='bottom', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f'{t}  ·  {k:,} machines' for t, k in zip(d.model, d.machines)], color=style.INK2)
    ax.set_ylim(-0.7, n + 0.25)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Unplanned tickets per 100 installed machine-months')
    ax.legend(handles=handles, loc='lower right', handlelength=2.2, frameon=True, facecolor=style.SURFACE,
              edgecolor='none', framealpha=1)

    # ---- text ----
    ratio = lambda r: f'{r:.2f}×'  # noqa: E731
    stay_txt = names([f'{r.model} ({ratio(r.age_std_ratio)})' for r in stay.itertuples()])
    if len(drop):
        drop_txt = (f'; {names([f"{r.model} ({ratio(r.age_std_ratio)})" for r in drop.itertuples()])} '
                    f'{"is" if len(drop) == 1 else "are"} not different from the fleet once machine age is allowed for')
    else:
        drop_txt = ''
    join_txt = ''.join(f' {r.model} goes the other way: {r.vs_fleet} on the crude rate shown, above the fleet once '
                       f'age is allowed for ({ratio(r.age_std_ratio)}).' for r in join.itertuples())
    age_note = (f'Age-standardised, {len(stay)} of the {len(above)} models above the fleet stay above: {stay_txt}'
                f'{drop_txt}. Part of each gap is machine age: machines under {YOUNG_YEARS} years old run above the '
                f'fleet rate, and at the fleet\'s rate for their age alone these {len(above)} models would run at '
                f'{age_mix.min():.2f}× ({lift_lo.model}) to {age_mix.max():.2f}× ({lift_hi.model}) the fleet rate.'
                f'{join_txt}')
    wider = d[d.ci_method == WIDER]
    wider_txt = (f'; for {names(wider.model.tolist())} (fewer than {D["min_clusters"]} accounts), the wider of that '
                 f'and Byar\'s Poisson interval' if len(wider) else '')
    ci_note = (f'95% intervals: cluster bootstrap over accounts, since tickets cluster within accounts{wider_txt}. '
               f'Not shown: {len(rest)} models with fewer than {D["min_type_months"]} installed machine-months '
               f'({int(rest.machines.sum())} machines, {int(rest.tickets.sum())} tickets in all), pooled in the '
               f'analysis.')
    source_note = fleet.source('model_rates').rstrip('.') + '; fleet rate from fx_summary.json.'
    style.frame(
        fig,
        title,
        f'Unplanned tickets per 100 installed machine-months by model, {fleet.period_text(S)}: the {n} models with '
        f'at least {D["min_type_months"]} installed machine-months ({months_share:.1%} of the fleet\'s months), '
        f'sorted by rate, with 95% intervals. Fleet rate '
        f'{f:.1f} = {int(F["tickets"]):,} tickets over {F["months"]:,.0f} installed machine-months on '
        f'{F["machines_exposed"]:,} machines.',
        definitions=[fleet.unplanned_definition(), fleet.installed_month_definition(S), fleet.AGE_STD_DEFINITION],
        notes=[age_note, ci_note, source_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
