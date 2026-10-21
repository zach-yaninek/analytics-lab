#!/usr/bin/env python3
"""Fleet chart 4: unplanned tickets per 100 installed machine-months by service status, with 95% intervals.

IPA's installed-base list gives each machine a service status (Service Contract, Under Warranty, No Coverage, Not
Serviceable). Dividing each status's unplanned tickets by its installed machine-months shows whether machines under
different service arrangements generate tickets at different rates. One bar per status, sorted by rate (highest on
top), with its 95% interval (cluster bootstrap over accounts; the wider of the bootstrap and Byar's Poisson
interval for a status in fewer than 10 accounts) and its rate at the end of the interval. The axis label under
each status gives its machines and installed machine-months. Blue = interval wholly above the fleet rate, orange =
wholly below, gray = the interval includes it (the same classes as charts fx_02 and fx_03; the colour key is in the
subtitle, so no legend crosses the fleet line). The vertical line is the fleet rate. The title names the highest-
and lowest-rate statuses and their multiples of the fleet rate.

The rates are crude and the status is the list's 19 Oct 2026 snapshot, applied to the whole period, so the first
footer note says how far that matters for the two extremes: Under Warranty machines are mostly new installs (a
lower bound on the share installed during the period is computed from their mean installed months), and machines
in their first year run above the fleet rate (fx_age_rates.csv); what Not Serviceable means is open with IPA (the
note gives the youngest age band among its machines with a ticket). The second note gives the interval method and
the machines left out of every rate (those on a third-party service plan, from fx_service_plan_rates.csv rows with
in_population == False): their count, account count, tickets, installed machine-months and rate, all computed.

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here):
  verification/outputs/fleet/fx_coverage_rates.csv      one row per service status: machines, machines_with_ticket,
                                                        accounts, months, tickets, rate_per_100, byar_lo/hi,
                                                        boot_lo/hi, ci_lo/ci_hi (ci_method), ratio_to_fleet,
                                                        vs_fleet, fleet_rate_per_100
  verification/outputs/fleet/fx_service_plan_rates.csv  one row per service plan, in_population (the third-party
                                                        plan's count and rate for the note)
  verification/outputs/fleet/fx_summary.json            period, list date, fleet totals, third-party totals
  verification/outputs/fleet/fx_age_rates.csv           fleet rate in the first age band (note)
  verification/outputs/fleet/fx_machine_flags.csv       per-machine status, age band, months and tickets of every
                                                        machine with a ticket (checks; Not Serviceable age band)
  verification/outputs/fleet/fx_customer_rates.csv      months and months share per status for every customer
                                                        (independent check of months and accounts per status)
Output:  viz/figures/fx_04_rate_by_coverage.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_04_rate_by_coverage.py
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_04_rate_by_coverage.png'
ROW_IN = 0.62             # inches per status row
BAR_H = 0.24              # bar thickness in rows (about 22 px at 150 dpi with ROW_IN)
FIG_H = 4.55              # figure height besides the rows: title band, footer, x axis (inches)
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
BOOT = 'cluster bootstrap'
WIDER = 'wider of bootstrap and Byar'
CLASSES = [  # vs_fleet value, bar colour, colour key in the subtitle (in place of a legend)
    ('above', style.BLUE, 'blue = interval wholly above the fleet rate'),
    ('below', style.ORANGE, 'orange = interval wholly below it'),
    ('not different', style.GRAY_LIGHT, 'gray = interval includes it'),
    ('not estimable (one account)', style.GRAY_LIGHT, 'gray = one account, not estimable'),
]
WARRANTY = 'Under Warranty'           # status of the early-life caveat (checked against the data)
NOT_SERVICEABLE = 'Not Serviceable'   # status whose meaning is to be confirmed by IPA (checked against the data)
FIRST_BAND = '<1'                     # first age band of the analysis (fx_summary definitions.age_bands)


def ratio_text(r):
    """1.7036 -> '1.7', 0.2410 -> '0.24' (two significant digits)."""
    return f'{r:.2g}' if r < 10 else f'{r:.0f}'


def band_floor(band):
    """Lower edge in years of an age band label: '<1' -> 0, '8-10' -> 8, '10+' -> 10."""
    return 0 if band.startswith('<') else int(band.rstrip('+').split('-')[0])


def names(items):
    """'A', 'A and B', 'A, B and C'."""
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    F, D, T = S['fleet'], S['definitions'], S['third_party']
    f = fleet.fleet_rate(S)
    c = fleet.load('coverage_rates')
    plans = fleet.load('service_plan_rates')
    ages = fleet.load('age_rates').set_index('age_band')
    mf = fleet.load('machine_flags')
    cr = fleet.load('customer_rates')

    # ---------------------------------------------------------------------------------------------- Checks
    # Fleet totals: the fleet rate is a ratio of totals, and the status rows add up to the fleet.
    style.check('fx_04 fleet rate = 100 x tickets / months (summary)', f, 100 * F['tickets'] / F['months'], 1e-9)
    style.check('fx_04 fleet rate = 100 x tickets / months (all status rows)', f,
                100 * c.tickets.sum() / c.months.sum(), 1e-9)
    style.check('fx_04 fleet rate column = summary', 0, float((c.fleet_rate_per_100 - f).abs().max()), 1e-9)
    style.check('fx_04 status tickets = fleet tickets', F['tickets'], c.tickets.sum(), 1e-6)
    style.check('fx_04 status months = fleet months', F['months'], c.months.sum(), 1e-6)
    style.check('fx_04 status machines = machines with installed months', F['machines_exposed'], int(c.machines.sum()))
    style.check('fx_04 status machines with a ticket = fleet', F['machines_with_ticket'],
                int(c.machines_with_ticket.sum()))
    style.check('fx_04 one row per status', len(c), c.service_status.nunique())
    style.check('fx_04 statuses named in the notes are in the data', 1,
                int({WARRANTY, NOT_SERVICEABLE} <= set(c.service_status)))
    style.check('fx_04 rates = 100 x tickets / months', 0,
                float((100 * c.tickets / c.months - c.rate_per_100).abs().max()), 1e-9)

    # Per-status counts recomputed from other tables: tickets and machines with a ticket from the per-machine
    # table (every machine with a ticket), months and accounts from the per-customer months shares.
    by = c.set_index('service_status')
    per_machine = mf.groupby('service_status').agg(tickets=('tickets', 'sum'), with_ticket=('serial_id', 'size'))
    per_machine = per_machine.reindex(by.index).fillna(0)
    style.check('fx_04 tickets per status = per-machine table', 0,
                float((per_machine.tickets - by.tickets).abs().max()), 1e-9)
    style.check('fx_04 machines with a ticket per status = per-machine table', 0,
                float((per_machine.with_ticket - by.machines_with_ticket).abs().max()))
    share_col = {s: 'months_share_' + s.lower().replace(' ', '_') for s in by.index}
    style.check('fx_04 every status has a months-share column (customer table)', 1,
                int(set(share_col.values()) <= set(cr.columns)))
    months_cust = pd.Series({s: float((cr.months * cr[col]).sum()) for s, col in share_col.items()})
    style.check('fx_04 months per status = customer months x status share', 0,
                float((months_cust - by.months).abs().max()), 1e-6)
    accounts_cust = pd.Series({s: int((cr[col] > 0).sum()) for s, col in share_col.items()})
    style.check('fx_04 accounts per status = customers with months in the status', 0,
                int((accounts_cust - by.accounts).abs().max()))

    # Intervals as drawn: Byar recomputed from the counts, and the interval rule (F8).
    z = D['z95']
    style.check('fx_04 interval level 95% (z95 of the analysis)', 1.96, z, 0.001)
    k = c.tickets.to_numpy(float)
    k1 = np.maximum(k, 1)
    b_lo = np.where(k > 0, k * (1 - 1 / (9 * k1) - z / (3 * np.sqrt(k1))) ** 3, 0.0)
    b_hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    style.check('fx_04 Byar intervals recomputed from tickets', 0,
                float(max(np.abs(100 * b_lo / c.months - c.byar_lo).max(),
                          np.abs(100 * b_hi / c.months - c.byar_hi).max())), 1e-9)
    weak = (c.accounts < D['min_clusters']) | (c.tickets == 0)
    style.check('fx_04 interval method = rule (accounts < min_clusters or no tickets)', 0,
                int((c.ci_method != np.where(weak, WIDER, BOOT)).sum()))
    lo = np.where(weak, np.fmin(c.boot_lo, c.byar_lo), c.boot_lo)
    hi = np.where(weak, np.fmax(c.boot_hi, c.byar_hi), c.boot_hi)
    style.check('fx_04 drawn intervals = bootstrap / wider-of rule', 0,
                float(max(np.abs(lo - c.ci_lo).max(), np.abs(hi - c.ci_hi).max())), 1e-9)
    style.check('fx_04 every rate lies in its interval', 1,
                int(((c.ci_lo <= c.rate_per_100) & (c.rate_per_100 <= c.ci_hi)).all()))
    # The colour comes from vs_fleet (bootstrap interval of the ratio to the fleet); it must agree with where the
    # drawn rate interval sits against the fleet line.
    drawn = np.select([c.ci_lo > f, c.ci_hi < f], ['above', 'below'], 'not different')
    single = c.vs_fleet.str.startswith('not estimable')
    style.check('fx_04 colour class = drawn interval against the fleet line', 0,
                int(((drawn != c.vs_fleet) & ~single).sum()))
    style.check('fx_04 every class has a colour', 1, int(set(c.vs_fleet) <= {cl[0] for cl in CLASSES}))
    style.check('fx_04 ratio_to_fleet = rate / fleet rate', 0,
                float((c.rate_per_100 / f - c.ratio_to_fleet).abs().max()), 1e-9)

    # Title: the highest- and lowest-rate statuses against the fleet.
    d = c.sort_values(['rate_per_100', 'service_status'], ascending=[True, False], kind='mergesort')  # top = high
    n = len(d)
    top, low = d.iloc[-1], d.iloc[0]
    style.check('fx_04 title: highest rate', float(c.rate_per_100.max()), top.rate_per_100)
    style.check('fx_04 title: lowest rate', float(c.rate_per_100.min()), low.rate_per_100)
    style.check('fx_04 title: highest ratio to fleet', top.ratio_to_fleet, 100 * top.tickets / top.months / f, 1e-9)
    style.check('fx_04 title: lowest ratio to fleet', low.ratio_to_fleet, 100 * low.tickets / low.months / f, 1e-9)
    style.check('fx_04 title: highest status is above the fleet', 1, int(top.vs_fleet == 'above'))
    style.check('fx_04 title: lowest status is below the fleet', 1, int(low.vs_fleet == 'below'))
    title = (f'{top.service_status} machines have {ratio_text(top.ratio_to_fleet)}× the fleet\'s ticket rate, '
             f'{low.service_status} {ratio_text(low.ratio_to_fleet)}×')

    # Subtitle: list date and period.
    list_date = pd.Timestamp(D['equipment_list_date'])
    list_text = f'{list_date.day} {list_date:%b %Y}'
    style.check('fx_04 list date = the date in the source line', 1, int(f'({list_text})' in fleet.source()))

    # Note 1, Under Warranty: every listed machine is installed to the end of the period, so a machine installed
    # before the period has the full period's months and the others fewer; months / full months bounds the share
    # installed before the period from above.
    start, end = (pd.Timestamp(x) for x in D['period'])
    full = (end + pd.Timedelta(days=1) - start).days / D['month_days']
    style.check('fx_04 full-period months = longest exposure of any machine (per-machine table)', full,
                float(mf.months.max()), 1e-9)
    style.check('fx_04 no machine has more than the full period', 1, int((mf.months <= full + 1e-9).all()))
    w = by.loc[WARRANTY]
    w_mean = w.months / w.machines
    w_new = 1 - w_mean / full  # lower bound on the share of these machines installed during the period
    w_new_pct = math.floor(100 * w_new)
    style.check('fx_04 warranty: "mostly new installs" (lower bound > half)', 1, int(w_new > 0.5))
    style.check('fx_04 warranty: mean installed months', w.months / w.machines,
                float(months_cust[WARRANTY]) / int(w.machines), 1e-9)
    w_mf = mf[mf.service_status == WARRANTY]
    style.check('fx_04 warranty: machines with a ticket are all in the first age band', 1,
                int((w_mf.age_band == FIRST_BAND).all()))
    style.check('fx_04 first age band = analysis age bands[0]', 1, int(D['age_bands'][0] == FIRST_BAND))
    first = ages.loc[FIRST_BAND]
    first_rate = 100 * first.tickets / first.months
    style.check('fx_04 first-band rate = 100 x tickets / months', first.rate_per_100, first_rate, 1e-9)
    style.check('fx_04 first-band rate is above the fleet', 1, int(first.vs_fleet == 'above' and first_rate > f))
    first_years = int(FIRST_BAND.lstrip('<'))
    # Not Serviceable: the youngest age band among its machines with a ticket.
    ns_mf = mf[mf.service_status == NOT_SERVICEABLE]
    style.check('fx_04 Not Serviceable machines with a ticket (per-machine table)',
                int(by.loc[NOT_SERVICEABLE, 'machines_with_ticket']), len(ns_mf))
    ns_floor = min(band_floor(b) for b in ns_mf.age_band)
    style.check('fx_04 Not Serviceable: age bands are analysis age bands', 1,
                int(set(ns_mf.age_band) <= set(D['age_bands'])))
    ns_age = (f'; its {len(ns_mf)} machines with a ticket are all {ns_floor}+ years old'
              if ns_floor > 0 and len(ns_mf) else '')
    below = d[d.vs_fleet == 'below'].sort_values('rate_per_100', ascending=False).service_status

    # Note 2, third-party plan: rows of the plan table outside the population.
    tp = plans[~plans.in_population.astype(bool)]
    inp = plans[plans.in_population.astype(bool)]
    style.check('fx_04 third-party plans = summary', 1, int(set(tp.service_plan) == set(D['third_party_plans'])))
    tp_machines, tp_tickets, tp_months = int(tp.machines.sum()), int(tp.tickets.sum()), float(tp.months.sum())
    tp_accounts = int(tp.accounts.sum())
    tp_rate = 100 * tp_tickets / tp_months
    style.check('fx_04 third-party machines = summary', T['machines'], tp_machines)
    style.check('fx_04 third-party machines = definition text', 1,
                int(f'the {tp_machines} machines' in fleet.installed_month_definition(S)))
    style.check('fx_04 third-party tickets = summary', T['tickets'], tp_tickets)
    style.check('fx_04 third-party months = summary', T['months'], tp_months, 1e-6)
    style.check('fx_04 third-party accounts = summary', T['accounts'], tp_accounts)
    style.check('fx_04 third-party rate = rate column (months-weighted)', tp_rate,
                float((tp.rate_per_100 * tp.months).sum() / tp_months), 1e-9)
    style.check('fx_04 plans in the population = fleet tickets', F['tickets'], inp.tickets.sum(), 1e-6)
    style.check('fx_04 plans in the population = fleet months', F['months'], inp.months.sum(), 1e-6)
    style.check('fx_04 plans in the population = fleet machines', F['machines_exposed'], int(inp.machines.sum()))
    W3 = S['with_third_party_sensitivity']
    style.check('fx_04 all plans = fleet with third party (tickets)', W3['tickets'], plans.tickets.sum(), 1e-6)
    style.check('fx_04 all plans = fleet with third party (months)', W3['months'], plans.months.sum(), 1e-6)
    tp_plan = names(sorted(tp.service_plan))

    wider = d[d.ci_method == WIDER]
    wider_txt = (f'; for {names(wider.service_status.tolist())} (fewer than {D["min_clusters"]} accounts), the wider '
                 f'of that and Byar\'s Poisson interval' if len(wider) else '')

    # ---------------------------------------------------------------------------------------------- Drawing
    fig, ax = style.figure(max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN), FIG_H + ROW_IN * n)
    y = np.arange(n, dtype=float)
    colour = {cl[0]: cl[1] for cl in CLASSES}
    xmax = d.ci_hi.max() * 1.14
    pad = xmax * 0.012
    ax.axvline(f, color=style.INK2, lw=1, zorder=1)
    ax.barh(y, d.rate_per_100, height=BAR_H, color=[colour[v] for v in d.vs_fleet], linewidth=0, zorder=2)
    ax.errorbar(d.rate_per_100, y, xerr=[d.rate_per_100 - d.ci_lo, d.ci_hi - d.rate_per_100], fmt='none',
                ecolor=style.INK2, elinewidth=1.1, capsize=3.5, capthick=1.1, zorder=3)
    for yi, row in zip(y, d.itertuples()):
        named = row.service_status in (top.service_status, low.service_status)
        ax.text(row.ci_hi + pad, yi, f'{row.rate_per_100:.1f}', va='center', ha='left', fontsize=9.5,
                color=style.INK if named else style.INK2, weight='bold' if named else 'normal')
    ax.text(f + pad, n - 0.5, f'Fleet: {f:.1f}', va='bottom', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f'{r.service_status}\n{r.machines:,} machines · {r.months:,.0f} machine-months'
                        for r in d.itertuples()], color=style.INK2, linespacing=1.5)
    for tick, status in zip(ax.get_yticklabels(), d.service_status):
        if status in (top.service_status, low.service_status):
            tick.set_color(style.INK)
    ax.set_ylim(-0.55, n - 0.05)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Unplanned tickets per 100 installed machine-months')

    # ---------------------------------------------------------------------------------------------- Text
    key = ', '.join(text for cls, _, text in CLASSES if cls in set(d.vs_fleet))
    subtitle = (f'Unplanned tickets per 100 installed machine-months by service status on IPA\'s installed-base list '
                f'of {list_text}, {fleet.period_text(S)}: {F["machines_exposed"]:,} machines. Bars with 95% '
                f'intervals: {key}. Fleet rate (line) {f:.1f} = {int(F["tickets"]):,} tickets over '
                f'{F["months"]:,.0f} installed machine-months.')
    snapshot_note = (f'Status is the {list_text} snapshot, applied to the whole period. {WARRANTY} machines are mostly '
                     f'new installs (they average {w_mean:.1f} of a possible {full:.1f} installed months, so at least '
                     f'{w_new_pct}% were installed during the period), and machines under {first_years} year old run '
                     f'at {first_rate:.1f} fleet-wide (chart fx_03): part of their rate is early-life. What '
                     f'{NOT_SERVICEABLE} means is to be confirmed by IPA{ns_age}. The low {names(below)} rates '
                     f'probably mean fewer calls reach IPA, not more reliable machines.')
    method_note = (f'95% intervals: cluster bootstrap over accounts, since tickets cluster within accounts{wider_txt}. '
                   f'Left out of every rate: the {tp_machines} machines on the {tp_plan} third-party service plan '
                   f'({tp_accounts} account{"" if tp_accounts == 1 else "s"}), with {tp_tickets} unplanned '
                   f'tickets in {tp_months:,.0f} installed machine-months ({tp_rate:.2f} per 100).')
    source_note = (fleet.source('coverage_rates', 'service_plan_rates', 'age_rates', 'machine_flags').rstrip('.')
                   + '; fleet rate from fx_summary.json.')
    style.frame(fig, title, subtitle,
                definitions=[fleet.unplanned_definition(), fleet.installed_month_definition(S)],
                notes=[snapshot_note, method_note, source_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
