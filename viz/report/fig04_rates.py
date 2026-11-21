#!/usr/bin/env python3
"""Report figure 4 (Results, Rates by model and age): the fleet runs at 6.2 unplanned tickets per 100 installed
machine-months; the three busiest models (LVD-Remote-2.0, LVRR-WP-2.0, and MV-2.0) hold 42% of machine-months and 51%
of tickets, partly because they are younger; scrubBank 480 runs 2.6 times the fleet age for age; and machines under
4 years run about 8 per 100 vs. 2.5 at 10 years or more, where 83 of the 164 machines with a ticket are Not
Serviceable.

(a) The three busiest models together: their share of installed machine-months, their share of the tickets their
    machines would have at the fleet's age-band rates (the age-for-age denominator), and their share of unplanned
    tickets. The middle bar is what "partly because they are younger" rests on: the fleet's age-band rates alone lift
    their share from 42% to 47%, and they hold 51%.
(b) Each of the 27 models with at least 100 installed machine-months (the models with a rate of their own): its
    ratio to the fleet age for age with its 95% interval (a cluster bootstrap over accounts that re-fits the joint
    model and age fit in every resample; for the 2 models at fewer than 10 accounts, the wider of that and Byar's
    Poisson interval), sorted by ratio. Points are anonymous; scrubBank 480 is cobalt and named, as in the report.
    The dashed line is the fleet (a ratio of 1), named at its left end as in (c).
(c) Unplanned tickets per 100 installed machine-months by age band (years from install to the midpoint of the
    machine's installed time in the period), with 95% cluster-bootstrap intervals over accounts and the fleet's rate
    as a dashed line. Each bar is labelled with its band (0–1, 1–2, 2–4, 4–6, 6–8, 8–10, and 10+ years): the bands
    are 1, 1, 2, 2, 2, and 2 years wide and the last is open, so the bars are categories, not a linear age axis.
    The three bands under 4 years and the 10+ band are cobalt; the bracket gives the rate of the bands under 4 years
    together, and the note gives the paragraph's caveat: the 10+ rate overstates the drop, since 83 of the band's 164
    machines with a ticket are Not Serviceable.

Inputs: verification/outputs/fleet/fx_customer_rates.csv (one row per customer, read without its customer column:
the fleet's tickets and installed months), fx_machine_flags.csv (one row per fleet machine with a ticket, read without
its customer column), fx_model_rates.csv (one row per model: installed months, the age-for-age denominator, ratios
and intervals), fx_age_rates.csv (one row per age band: installed months and intervals), and fx_summary.json (totals
and definitions). Notebook 04 checks the same numbers, and this script reuses its logic.
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig04_rates'
LABEL = 'fig:rates'
SHORT = 'Rates by model and age'

FLEET = S.OUT / 'fleet'
DOC = S.ROOT / 'docs' / '06_fleet_exposure.md'   # the analysis' description: the intervals' level and rule
N_BUSY = 3                    # the report's three busiest models
SB = 'scrubBank 480'          # the model the report names
YOUNG, OLD = 4, 10            # years: the report's cuts, under 4 years and 10 years or more
NOT_SERVICEABLE = 'Not Serviceable'
CASING = [pe.Stroke(linewidth=2.4, foreground=S.WHITE), pe.Normal()]   # so an interval reads on a cobalt bar
MACHINE_COLS = ['serial_id', 'model', 'rate_group', 'service_status', 'age_band', 'months', 'tickets', 'expected',
                'expected_with_coverage']


def band_years(label):
    """A band's years from its label (notebook 04): '<1' -> (0, 1), '2-4' -> (2, 4), '10+' -> (10, inf)."""
    if label.startswith('<'):
        return 0.0, float(label[1:])
    if label.endswith('+'):
        return float(label[:-1]), math.inf
    lo, hi = label.split('-')
    return float(lo), float(hi)


def band_name(label):
    """A band's tick label from its years: '<1' -> '0–1', '2-4' -> '2–4', '10+' -> '10+'."""
    lo, hi = band_years(label)
    return f'{lo:g}+' if math.isinf(hi) else f'{lo:g}–{hi:g}'


def data_box(fig, artist, ax):
    """An artist's box in ax's data coordinates, in the final layout (as fig13 places its note)."""
    fig.canvas.draw()
    return artist.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted())


def band_factors(machines, bands, column, factors):
    """Age-band factors of one of the script's fits, relative to the youngest band, recovered from the machines with a
    ticket (notebook 04): the log of a machine's expected tickets per installed month is a sum of one term per level."""
    X = pd.get_dummies(machines[factors].astype(str), dtype=float)
    y = np.log(machines[column] / machines.months).to_numpy()
    beta, _, rank, _ = np.linalg.lstsq(X.to_numpy(), y, rcond=None)
    S.check(f'fig04 {column}: only the split of the scale between factors is free', X.shape[1] - (len(factors) - 1),
            rank)
    S.check(f'fig04 {column}: the terms reproduce every machine\'s expected tickets', 0,
            float(np.abs(X.to_numpy() @ beta - y).max()), 1e-9)
    term = pd.Series(beta, X.columns)[[f'age_band_{band}' for band in bands]].to_numpy()
    return pd.Series(np.exp(term - term[0]), bands)


def plot(out_dir=S.FIG_DIR):
    summary = json.loads((FLEET / 'fx_summary.json').read_text())
    defs = summary['definitions']
    customers = pd.read_csv(FLEET / 'fx_customer_rates.csv', usecols=['tickets', 'months', 'machines'])
    machines = pd.read_csv(FLEET / 'fx_machine_flags.csv', usecols=MACHINE_COLS)
    models = pd.read_csv(FLEET / 'fx_model_rates.csv').set_index('model')
    ages = pd.read_csv(FLEET / 'fx_age_rates.csv').set_index('age_band')
    S.check('fig04 one row per machine with a ticket', 1, int(machines.serial_id.is_unique and
                                                              (machines.tickets > 0).all()))
    S.check('fig04 one row per customer in the population', summary['fleet']['accounts'], len(customers))

    # The fleet rate (notebook 04): the per-customer table holds every fleet machine, with a ticket or not
    fleet_tickets = int(customers.tickets.sum())
    fleet_months = customers.months.sum()
    fleet_rate = 100 * fleet_tickets / fleet_months
    S.check('fig04 machine tickets = fleet tickets', fleet_tickets, int(machines.tickets.sum()))
    S.check('fig04 fleet tickets = fx_summary.json', summary['fleet']['tickets'], fleet_tickets)
    S.check('fig04 fleet machines = fx_summary.json', summary['fleet']['machines_exposed'],
            int(customers.machines.sum()))
    S.check('fig04 fleet months = fx_summary.json', summary['fleet']['months'], fleet_months, 1e-6)
    S.check('fig04 fleet rate = fx_summary.json', summary['fleet']['rate_per_100'], fleet_rate, 1e-9)

    # (a) The three busiest models: shares of machine-months, of tickets at the fleet's age-band rates, and of tickets
    model_tickets = machines.groupby('model').tickets.sum().reindex(models.index, fill_value=0)
    S.check('fig04 model tickets = fx_model_rates.csv', 0, float((model_tickets - models.tickets).abs().max()))
    S.check('fig04 model months = fleet months', fleet_months, models.months.sum(), 1e-6)
    S.check('fig04 age-for-age denominators add up to the fleet\'s tickets', fleet_tickets,
            models.expected_age_only.sum(), 1e-6)
    ranked = model_tickets.sort_index().sort_values(ascending=False, kind='mergesort')
    top3 = list(ranked.index[:N_BUSY])
    S.check('fig04 no tie at the busiest-models boundary', 1, int(ranked.iloc[N_BUSY - 1] > ranked.iloc[N_BUSY]))
    t3, m3, e3 = model_tickets[top3].sum(), models.months[top3].sum(), models.expected_age_only[top3].sum()
    share_months, share_age, share_tickets = m3 / fleet_months, e3 / fleet_tickets, t3 / fleet_tickets
    raw_ratio, age_ratio = (t3 / m3) / (fleet_tickets / fleet_months), t3 / e3
    S.check('fig04 the busiest models\' shares = fx_model_rates.csv (months)', models.share_of_months[top3].sum(),
            share_months, 1e-9)
    S.check('fig04 the busiest models\' shares = fx_model_rates.csv (tickets)', models.share_of_tickets[top3].sum(),
            share_tickets, 1e-9)
    S.check('fig04 each busiest model\'s age-for-age ratio = fx_model_rates.csv', 0,
            float((model_tickets[top3] / models.expected_age_only[top3] - models.age_std_ratio[top3]).abs().max()),
            1e-9)
    S.check('fig04 raw ratio = share of tickets / share of months', share_tickets / share_months, raw_ratio, 1e-9)
    S.check('fig04 age-for-age ratio = share of tickets / share at the fleet\'s age-band rates',
            share_tickets / share_age, age_ratio, 1e-9)
    if age_ratio <= 1:
        youth = 'entirely because they are younger'
    elif age_ratio < raw_ratio:
        youth = 'partly because they are younger'
    else:
        youth = 'not because they are younger'

    # (b) Each model with its own rate, age for age
    sb_ratio = model_tickets[SB] / models.expected_age_only[SB]
    S.check('fig04 scrubBank 480 ratio = fx_model_rates.csv', models.age_std_ratio[SB], sb_ratio, 1e-9)
    S.check('fig04 own rate = at least min_type_months installed months', 0,
            int((models.own_rate != (models.months >= defs['min_type_months'])).sum()))
    own = models[models.own_rate].assign(ratio=lambda d: model_tickets[d.index] / d.expected_age_only)
    S.check('fig04 (b) ratios = tickets / age-for-age denominator', 0,
            float((own.ratio - own.age_std_ratio).abs().max()), 1e-9)
    S.check('fig04 (b) every interval holds its ratio', 1,
            int(((own.age_std_lo <= own.ratio) & (own.ratio <= own.age_std_hi)).all()))
    S.check('fig04 (b) scrubBank 480 has its own rate', 1, int(bool(own.own_rate.get(SB, False))))
    weak = own[(own.accounts < defs['min_clusters']) | (own.tickets == 0)]
    S.check('fig04 (b) 2 models at fewer than 10 accounts (wider-of intervals)', 2, len(weak))
    k = weak.tickets.to_numpy(float)          # Byar's interval for the count (fleet_exposure.py), for those models
    z = defs['z95']
    byar_lo = np.where(k > 0, k * (1 - 1 / (9 * np.maximum(k, 1)) - z / (3 * np.sqrt(np.maximum(k, 1)))) ** 3, 0)
    byar_hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    S.check('fig04 (b) their intervals hold the Poisson interval', 1,
            int(((weak.age_std_lo <= byar_lo / weak.expected_age_only + 1e-12)
                 & (weak.age_std_hi >= byar_hi / weak.expected_age_only - 1e-12)).all()))
    own = own.sort_values(['ratio', 'months'], kind='mergesort')
    S.check('fig04 (b) scrubBank 480 runs highest of the models with their own rate', 1, int(own.index[-1] == SB))
    S.check('fig04 (b) models drawn = models with 100 or more installed months', int((models.months >= 100).sum()),
            len(own))
    S.check('fig04 (b) 100 installed months for a rate of its own (fx_summary.json)', 100, defs['min_type_months'])
    S.check('fig04 (b) 10 accounts for a bootstrap interval alone (fx_summary.json)', 10, defs['min_clusters'])
    level = re.search(r'\*\*Intervals:\*\* (\d+)%, from a cluster bootstrap that resamples accounts', DOC.read_text())
    S.check('fig04 caption: 95% intervals (docs/06)', 95, int(level.group(1)))
    S.check('fig04 (b) weak groups get the wider of the bootstrap and the exact Poisson interval (docs/06)', 1,
            int('fewer than 10 accounts' in DOC.read_text()
                and 'the wider of the bootstrap and the exact Poisson (Byar) interval' in DOC.read_text()))

    # (c) Age bands, the report's cuts, and the 10+ band's machines with a ticket by service status
    band_tickets = machines.groupby('age_band').tickets.sum().reindex(ages.index, fill_value=0)
    S.check('fig04 age bands = the analysis\' bands, in order', 1, int(list(ages.index) == defs['age_bands']))
    S.check('fig04 band tickets = fx_age_rates.csv', 0, float((band_tickets - ages.tickets).abs().max()))
    S.check('fig04 band months = fleet months', fleet_months, ages.months.sum(), 1e-6)
    band_rate = 100 * band_tickets / ages.months
    S.check('fig04 band rates = fx_age_rates.csv', 0, float((band_rate - ages.rate_per_100).abs().max()), 1e-9)
    S.check('fig04 every band: cluster-bootstrap interval', 1, int((ages.ci_method == 'cluster bootstrap').all()))
    S.check('fig04 every band interval holds its rate', 1,
            int(((ages.ci_lo <= band_rate) & (band_rate <= ages.ci_hi)).all()))
    years = {band: band_years(band) for band in ages.index}
    S.check('fig04 no band spans a cut', 1,
            int(all(hi <= cut or lo >= cut for lo, hi in years.values() for cut in (YOUNG, OLD))))
    edges = [lo for lo, _ in years.values()]
    S.check('fig04 the bands are contiguous from 0, the last open', 1,
            int(edges[0] == 0 and all(years[b][1] == years[n][0] for b, n in zip(ages.index, ages.index[1:]))
                and math.isinf(years[ages.index[-1]][1])))
    young_bands = [band for band, (lo, hi) in years.items() if hi <= YOUNG]
    old_bands = [band for band, (lo, hi) in years.items() if lo >= OLD]
    rate_young = 100 * band_tickets[young_bands].sum() / ages.months[young_bands].sum()
    rate_old = 100 * band_tickets[old_bands].sum() / ages.months[old_bands].sum()
    in_old = machines[machines.age_band.isin(old_bands)]
    n_old, n_old_ns = len(in_old), int((in_old.service_status == NOT_SERVICEABLE).sum())
    S.check('fig04 10+ machines with a ticket = fx_age_rates.csv', int(ages.machines_with_ticket[old_bands].sum()),
            n_old)
    S.check('fig04 every young band runs above the fleet, and the 10+ band below it (intervals)', 1,
            int((ages.ci_lo[young_bands] > fleet_rate).all() and (ages.ci_hi[old_bands] < fleet_rate).all()))
    # The reading that the 10+ rate overstates the drop with age (notebook 04): with service status in the fit, the
    # 10+ band's factor relative to each band under 4 years rises
    fits = pd.DataFrame({
        'main': band_factors(machines, list(ages.index), 'expected', ['rate_group', 'age_band']),
        'with status': band_factors(machines, list(ages.index), 'expected_with_coverage',
                                    ['rate_group', 'age_band', 'service_status'])}).T
    (oldest,) = old_bands
    vs_young = fits[[oldest]].to_numpy() / fits[young_bands].to_numpy()
    rises = bool((vs_young[1] > vs_young[0] * (1 + 1e-6)).all())
    reading = 'overstates the drop with age' if rises else 'does not overstate the drop with age'

    S.report_check('fig04 fleet rate per 100 installed machine-months', '6.2', S.num(fleet_rate, 1))
    S.report_check('fig04 the three busiest models', 'LVD-Remote-2.0, LVRR-WP-2.0, and MV-2.0',
                   ', '.join(top3[:-1]) + ', and ' + top3[-1])
    S.report_check('fig04 their share of machine-months', '42%', S.pct(share_months))
    S.report_check('fig04 their share of tickets', '51%', S.pct(share_tickets))
    S.report_check('fig04 their excess: raw vs. age-for-age ratio', 'partly because they are younger', youth)
    S.report_check('fig04 scrubBank 480 vs. the fleet, age for age (times)', '2.6', S.num(sb_ratio, 1))
    S.report_check('fig04 the cut for young machines (years)', '4', S.num(YOUNG))
    S.report_check('fig04 rate per 100, under 4 years', '8', S.num(rate_young))
    S.report_check('fig04 the cut for old machines (years)', '10', S.num(OLD))
    S.report_check('fig04 rate per 100, 10 years or more', '2.5', S.num(rate_old, 1))
    S.report_check('fig04 the 10+ rate vs. the drop with age', 'overstates the drop with age', reading)
    S.report_check('fig04 10+ machines with a ticket that are Not Serviceable', '83', S.num(n_old_ns))
    S.report_check('fig04 10+ machines with a ticket', '164', S.num(n_old))

    fig, (ax, bx, cx) = S.figure(2.2, ncols=3, width_ratios=[0.92, 0.88, 1.2])
    blank = dict(fc=S.WHITE, ec='none', pad=0.8)   # keeps the light grid out of a label

    # (a) the three busiest models' shares, each labelled above its bar; the one green readout is their ticket share
    rows = [('Installed machine-months', share_months, S.GREY_FILL, 0.0),
            ('Tickets at the fleet’s\nage-band rates', share_age, S.GREY_FILL, 1.45),
            ('Unplanned tickets', share_tickets, S.COBALT, 2.7)]
    for name, value, colour, y in rows:
        ax.barh(y, value, height=0.36, color=colour, zorder=3)
        S.label(ax, 0.004, y - 0.26, name, va='bottom', linespacing=1.0, bbox=blank)
        text = S.pct(value)
        S.check(f'fig04 (a) label {name!r} {text}', round(100 * value), float(text.rstrip('%')))
        key = colour == S.COBALT
        S.label(ax, value + 0.012, y, text, size=S.FONT if key else S.TICK, weight='bold' if key else 'normal',
                color=S.GREEN if key else S.TEXT, bbox=blank)   # '51%' crosses the 60% gridline
    ax.set_ylim(3.05, -0.75)
    ax.set_yticks([])
    ax.set_xlim(0, 0.66)
    ax.set_xticks([0, 0.2, 0.4, 0.6])
    S.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of the fleet')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'Three busiest models')

    # (b) each model with its own rate: ratio to the fleet age for age, sorted, with its interval (anonymous points)
    xs = np.arange(len(own))
    focal = (own.index == SB)
    bx.axhline(1, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)   # the fleet
    bx.vlines(xs[~focal], own.age_std_lo[~focal], own.age_std_hi[~focal], color=S.GREY, lw=0.9, zorder=3)
    bx.plot(xs[~focal], own.ratio[~focal], 'o', color=S.GREY, ms=3.0, zorder=4)
    bx.vlines(xs[focal], own.age_std_lo[focal], own.age_std_hi[focal], color=S.COBALT, lw=1.2, zorder=5)
    bx.plot(xs[focal], own.ratio[focal], 'o', color=S.COBALT, ms=4.0, zorder=6)
    sb = own.loc[SB]
    text = f'{S.num(sb.ratio, 1)}×'
    S.check(f'fig04 (b) label {text}', round(sb.ratio, 1), float(text.rstrip('×')))
    # beside the upper half of its interval, clear of the next models' intervals, between two gridlines
    y_sb = math.floor((sb.ratio + sb.age_std_hi) / 2) + 0.5
    S.check('fig04 (b) the scrubBank 480 label sits beside the upper half of its interval', 1,
            int(sb.ratio < y_sb < sb.age_std_hi))
    S.label(bx, xs[focal][0] - 0.9, y_sb, f'{SB}\n{text}', ha='right', va='center', linespacing=1.15)
    # the fleet's line, named at its left end as in (c), just above the line and the lowest models' intervals
    fleet_label = S.label(bx, -0.6, 1.1, 'Fleet', ha='left', va='bottom')
    bx.set_xlim(-1, len(own))
    bx.set_xticks([])
    bx.set_ylim(0, 4.1)
    bx.set_yticks([0, 1, 2, 3, 4])
    bx.set_ylabel('Ratio to the fleet,\nage for age')
    bx.set_xlabel(f'{S.num(len(own))} models, sorted by ratio')
    S.clean(bx, grid='y', bottom=False)
    S.panel(bx, 'b', 'Models vs. the fleet')

    # (c) rates by age band with intervals, the fleet's rate, the young bands together, and the 10+ band's note
    n = len(ages)
    x = np.arange(n)
    hot = [b in young_bands or b in old_bands for b in ages.index]
    cx.axhline(fleet_rate, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)
    for xi, band, h in zip(x, ages.index, hot):
        cx.bar(xi, band_rate[band], width=0.64, color=S.COBALT if h else S.GREY_FILL, zorder=3)
        line, = cx.plot([xi, xi], [ages.ci_lo[band], ages.ci_hi[band]], color=S.GREY_DARK, lw=1.0,
                        solid_capstyle='butt', zorder=4)
        line.set_path_effects(CASING)
    # the bands under 4 years together: a bracket over their intervals, clear above the gridline over them (a bracket
    # just under a gridline reads as a doubled line)
    grid_over = S.ceil_to(float(ages.ci_hi[young_bands].max()), 2.5)
    top = grid_over + 0.6
    i0, i1 = x[0] - 0.32, x[len(young_bands) - 1] + 0.32
    cx.plot([i0, i0, i1, i1], [top - 0.25, top, top, top - 0.25], color=S.TEXT, lw=0.6, zorder=5)
    S.check('fig04 (c) the bracket clears the gridline over the young bands\' intervals', 1,
            int(float(ages.ci_hi[young_bands].max()) < grid_over < top - 0.25))
    text_young = S.num(rate_young, 1)
    S.check(f'fig04 (c) label under {YOUNG} years {text_young}', round(rate_young, 1), float(text_young))
    S.label(cx, (i0 + i1) / 2, top + 0.12, text_young, ha='center', va='bottom')
    # the 10+ band's rate and note
    xo = x[-1]
    text_old = S.num(rate_old, 1)
    S.check(f'fig04 (c) label 10+ {text_old}', round(rate_old, 1), float(text_old))
    S.label(cx, xo, float(ages.ci_hi[oldest]) + 0.2, text_old, ha='center', va='bottom')
    # the note, naming its band, in the empty space above the older bands (a leader would read as an interval), flush
    # with the panel's right edge so its white box takes the gridline through to the end
    S.label(cx, n - 0.5, 11.95, f'The {oldest} rate overstates\nthe drop: {S.num(n_old_ns)} of its {S.num(n_old)}\n'
            f'machines with a ticket\nare {NOT_SERVICEABLE}', ha='right', va='top', linespacing=1.0, bbox=blank)
    text_fleet = f'Fleet {S.num(fleet_rate, 1)}'
    S.label(cx, 3.17, fleet_rate + 0.2, text_fleet, ha='center', va='bottom')   # between the 2-4 bar and 6-8 interval
    # each bar named by its band: the bands differ in width, so evenly spaced edge ticks would read as a linear axis
    names = [band_name(band) for band in ages.index]
    S.check('fig04 (c) band labels name each band\'s years', 1,
            int(all([float(v) for v in re.findall(r'\d+', name)] == [y for y in years[band] if math.isfinite(y)]
                    for name, band in zip(names, ages.index))))
    S.check('fig04 (c) docstring: the bands are 1, 1, 2, 2, 2, and 2 years wide, the last open', 1,
            int([hi - lo for lo, hi in years.values()][:-1] == [1, 1, 2, 2, 2, 2]
                and math.isinf(years[ages.index[-1]][1])))
    cx.set_xticks(x, names)
    cx.tick_params(axis='x', length=0)
    cx.set_xlim(-0.5, n - 0.5)
    cx.set_ylim(0, 12)
    cx.set_yticks([0, 2.5, 5, 7.5, 10], ['0', '2.5', '5', '7.5', '10'])
    cx.set_xlabel('Machine age (years)')
    cx.set_ylabel('Tickets per 100\nmachine-months')
    S.clean(cx, grid='y', left=False)
    S.panel(cx, 'c', 'Rates by machine age')

    # Nothing drawn is clipped
    S.check('fig04 (a) bars inside the axis', 1, int(max(r[1] for r in rows) < ax.get_xlim()[1]))
    S.check('fig04 (b) intervals inside the axis', 1, int(own.age_std_hi.max() < bx.get_ylim()[1]))
    S.check('fig04 (c) intervals inside the axis', 1, int(ages.ci_hi.max() < cx.get_ylim()[1]))
    box = data_box(fig, fleet_label, bx)
    under = (xs + 0.5 > box.x0) & (xs - 0.5 < box.x1)
    S.check('fig04 (b) the Fleet label sits above the line and every interval under it', 1,
            int(box.y0 > 1 and bool((own.age_std_hi[under] < box.y0).all())))

    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share).replace('%', chr(92) + '%')  # noqa: E731
    return (f'The three busiest models hold {pc(share_months)} of machine-months and {pc(share_tickets)} of tickets, '
            f'{youth}; {SB} runs {S.num(sb_ratio, 1)} times the fleet age for age; machines under {YOUNG} years '
            f'run about {S.num(rate_young)} per 100 vs. {S.num(rate_old, 1)} at {OLD} years or more. '
            f'(a)~Shares; (b)~by model; (c)~by age; {S.num(int(level.group(1)))}\\% intervals.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
