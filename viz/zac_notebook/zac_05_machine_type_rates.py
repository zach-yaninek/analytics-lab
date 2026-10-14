#!/usr/bin/env python3
"""Zac's figure 5: unplanned ticket rate by telemetry machine type, per 100 active machine-months.

Recreates 05_machine_type_rates.png from Zac's notebook (cell 27, query machine_type_rates over his view
comparison_month). Same population (machine-months with at least one transaction, Aug 2025 to Jul 2026, devices on
known non-shared hosts), same selection (his chart screen: at least 100 active machine-months, at least 20 tickets,
type not Unknown; then the 10 highest rates) and the same metric (100 x tickets / active machine-months, a ratio of
totals) as his chart, with the same one-decimal values. Added: the type the title names in blue, the number of
machines per type on the axis, and a labelled line at the rate over all types (his printed "overall comparison
rate"; zac_06 uses the same name). The footer says which tickets the rates count and how they compare with
high_ticket chart 10, which also counts quiet months and the tickets opened in them (the direction and size of the
difference are computed and stated in words).

Inputs:  zac_data.load_db('machine_type_rates')        one row per machine type (Zac's SQL, cell 27, re-run on the DB)
         zac_data.load_db('comparison_cohort')         cohort totals (cell 27), for the totals checks
         zac_data.load_db('ticket_cohort_exclusions')  tickets left out of the cohort, by reason (cell 27)
         zac_data.load_db('monthly_comparison')        months of the comparison window (cell 29), for the period
         zac_data.load_db('machine_type_rates_vs_expected')   Zac's notebook table next to the re-run, for a check
         zac_data.load('case_monthly')                 unplanned tickets per month in the case export (cell 29)
         verification/outputs/htm_type_rates.csv   high_ticket chart 10's rates by type, for the note
Output:  viz/figures/zac_05_machine_type_rates.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_05_machine_type_rates.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10                  # Zac's selection: eligible_rates.head(10) (notebook cell 27)
MIN_MONTHS = 100            # Zac's chart screen: active_machine_months >= 100 (cell 27)
MIN_TICKETS = 20            # Zac's chart screen: tickets >= 20 (cell 27)
UNKNOWN = 'Unknown'         # Zac's chart screen: machine_type != 'Unknown' (cell 27)
MALFORMED = 'package name: alexsd-49'   # a malformed machine_type value, its own row in Zac's table (cell 27)
COHORT = 'Known nonshared hosts'        # Zac's comparison cohort (comparison_cohort, cell 27)
# Zac's ticket_cohort_exclusions reasons (cell 27): every unplanned ticket in the window has exactly one.
INCLUDED = 'Included in comparison'
NO_MATCH = 'No device match'
QUIET = 'No transactions in ticket month'
HOST = ['Missing host', 'Shared/internal host']


def window_text(months):
    """'Aug 2025 to Jul 2026' from the months of Zac's comparison window (zac_data.period_text() is the case export's
    longer period, Aug 2025 to Aug 2026)."""
    start, end = (pd.Period(m, 'M').strftime('%b %Y') for m in (months.min(), months.max()))
    return f'{start} to {end}'


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    r = zac_data.load_db('machine_type_rates').rename(columns={'tickets_per_100_active_months': 'rate'})
    cohort = zac_data.load_db('comparison_cohort').set_index('cohort').loc[COHORT]
    excl = zac_data.load_db('ticket_cohort_exclusions').set_index('reason').tickets
    months = zac_data.load_db('monthly_comparison').month
    unplanned = int(zac_data.load('case_monthly').set_index('month').loc[months, 'unplanned_tickets'].sum())
    htm_rates = pd.read_csv(zac_data.OUTPUTS / 'htm_type_rates.csv').set_index('machine_type')
    period = window_text(months)

    # Checks: the types add up to Zac's cohort and the rates are ratios of totals.
    tickets, active = int(r.tickets.sum()), int(r.active_machine_months.sum())
    style.check('zac_05 tickets = comparison cohort tickets', int(cohort.tickets), tickets)
    style.check('zac_05 tickets = tickets included in the comparison', int(excl[INCLUDED]), tickets)
    style.check('zac_05 active machine-months = comparison cohort', int(cohort.active_machine_months), active)
    style.check('zac_05 rates = 100 x tickets / active machine-months', 0,
                float((100 * r.tickets / r.active_machine_months - r.rate).abs().max()), 1e-9)
    style.check('zac_05 period = active machine-month definition', 1, int(period in zac_data.ACTIVE_MONTH_DEFINITION))
    # Every unplanned ticket of the window is either counted or has one exclusion reason.
    style.check('zac_05 exclusion reasons as named here', 1,
                int(set(excl.index) == {INCLUDED, NO_MATCH, QUIET, *HOST}))
    style.check('zac_05 unplanned tickets in the window = counted + excluded', unplanned, int(excl.sum()))
    all_rate = 100 * tickets / active  # Zac's printed "overall comparison rate" (cell 27)

    # Zac's chart screen and top-10 rule (cell 27).
    eligible = r[(r.active_machine_months >= MIN_MONTHS) & (r.tickets >= MIN_TICKETS) & (r.machine_type != UNKNOWN)]
    ranked = eligible.sort_values(['rate', 'machine_type'], ascending=[False, True], kind='mergesort')
    style.check('zac_05 no tie at the top-10 boundary', 1, int(ranked.rate.iloc[TOP_N - 1] > ranked.rate.iloc[TOP_N]))
    shown, rest = ranked.head(TOP_N), ranked.iloc[TOP_N:]
    screened = r.drop(eligible.index)
    style.check('zac_05 Unknown and the malformed value fail a screen', 1,
                int({UNKNOWN, MALFORMED} <= set(screened.machine_type)))
    lead, runner, others = shown.iloc[0], shown.iloc[1], shown.rate.iloc[1:]
    above_lead = screened[screened.rate > lead.rate]  # screened-out types with a higher (unstable) rate
    # Zac's own table (his notebook output, 2 decimals; db_machine_type_rates_vs_expected.csv) has the same rates.
    zac = zac_data.load_db('machine_type_rates_vs_expected').set_index('machine_type')
    style.check('zac_05 shown rates = Zac\'s notebook table (2 decimals)', 0,
                float(np.abs(zac.loc[shown.machine_type, 'tickets_per_100_active_months_expected'].to_numpy() -
                             shown.rate.to_numpy()).max()), 0.005)

    # High_ticket chart 10 counts machine-months from first to last transaction and every ticket in the period.
    htm_fleet = 100 * htm_rates.tickets_used_for_rate.sum() / htm_rates.exposure_months.sum()  # as chart 10
    htm_shown = htm_rates.loc[shown.machine_type]
    style.check('zac_05 Zac rates in htm_type_rates = DB re-run', 0,
                float(np.abs(htm_shown.zac_rate_per_100_active_months.to_numpy() - shown.rate.to_numpy()).max()), 1e-9)
    style.check('zac_05 chart-10 tickets = Zac tickets + tickets in months with no transaction',
                int(htm_rates.tickets_used_for_rate.sum()), tickets + int(excl[QUIET]))
    rel = htm_shown.rate_per_100_months.to_numpy() / shown.rate.to_numpy() - 1  # chart 10 rate vs this one
    # What chart 10 adds: tickets in months with no transaction, and quiet machine-months.
    more_tickets = int(htm_rates.tickets_used_for_rate.sum()) / tickets - 1
    more_months = int(htm_rates.exposure_months.sum()) / active - 1
    style.check('zac_05 chart-10 machine-months >= active machine-months', 1, int(more_months >= 0))
    style.check('zac_05 chart-10 fleet rate = Zac rate x (1 + more tickets) / (1 + more months)', htm_fleet,
                all_rate * (1 + more_tickets) / (1 + more_months), 1e-9)
    if (rel > 0).all():
        rel_text = f'are {rel.min():.0%} to {rel.max():.0%} higher'
    elif (rel < 0).all():
        rel_text = f'are {-rel.max():.0%} to {-rel.min():.0%} lower'
    else:
        rel_text = f'differ by {rel.min():+.0%} to {rel.max():+.0%}'
    weigh = 'outweigh' if more_tickets > more_months else 'weigh less than'

    d = shown.iloc[::-1]  # highest rate on top, as in Zac's chart
    colors = [style.BLUE if t == lead.machine_type else style.GRAY_LIGHT for t in d.machine_type]
    fig, ax = style.figure(10, 8.6)
    y = np.arange(len(d))
    xmax = d.rate.max() * 1.12
    pad, label_w = xmax * 0.01, xmax * 0.045  # value-label offset and approximate width (3 characters), data units
    ax.axvline(all_rate, color=style.INK2, lw=1, zorder=1)  # under the bars, as the fleet line in chart 10
    ax.barh(y, d.rate, height=0.5, color=colors, linewidth=0, zorder=2)
    ax.text(all_rate + pad, len(d) - 0.45, f'Overall: {all_rate:.1f}', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    for yi, row in zip(y, d.itertuples()):
        is_lead = row.machine_type == lead.machine_type
        # Right of the bar end, unless that lands on the overall line: then inside the bar end (same rule in zac_07).
        on_line = row.rate < all_rate < row.rate + 2 * pad + label_w
        x, ha = (row.rate - pad, 'right') if on_line else (row.rate + pad, 'left')
        color = style.SURFACE if on_line and is_lead else style.INK if is_lead else style.INK2
        ax.text(x, yi, f'{row.rate:.1f}', va='center', ha=ha, fontsize=9.5, color=color,
                weight='bold' if is_lead else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([f'{t}  ·  {n:,} machines' for t, n in zip(d.machine_type, d.machines)], color=style.INK2)
    ax.set_ylim(-0.6, len(d) + 0.1)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Unplanned tickets per 100 active machine-months')

    host = int(excl[HOST].sum())
    # A screened-out value with a higher rate than the lead, named so the title's "top" is not misread.
    higher = ''.join(f' ({t.machine_type}\'s {t.rate:.1f} rests on {t.tickets} tickets)'
                     for t in above_lead.itertuples())
    style.frame(
        fig,
        f'{lead.machine_type} has the top ticket rate: {lead.rate / runner.rate:.1f}× the next type, '
        f'{lead.rate / all_rate:.1f}× the overall rate',
        f'Unplanned tickets per 100 active machine-months by telemetry machine type, {period}: the {TOP_N} highest '
        f'rates among the {len(eligible)} types that pass Zac\'s screens. {lead.machine_type}: {int(lead.tickets)} '
        f'tickets in {int(lead.active_machine_months):,} active machine-months on {int(lead.machines)} machines. The '
        f'other {TOP_N - 1} lie between {others.min():.1f} and {others.max():.1f}; the line marks the overall rate '
        f'({tickets:,} tickets over {active:,} active machine-months, all types).',
        notes=[f'Tickets counted: unplanned tickets opened in an active month of a machine on a known, non-shared '
               f'host, {tickets:,} of the {unplanned:,} opened in these months. The rest have no device match '
               f'({int(excl[NO_MATCH]):,}), no transaction in the ticket\'s month ({int(excl[QUIET])}), or a shared '
               f'or missing host ({host}).',
               f'Zac\'s screens: at least {MIN_MONTHS} active machine-months and {MIN_TICKETS} tickets, type known '
               f'(descriptive stability screens, not significance tests). Ratios of totals, not adjusted for machine '
               f'age, customer mix or reporting.',
               f'Not shown: {len(rest)} more eligible types with lower rates ({rest.rate.min():.1f} to '
               f'{rest.rate.max():.1f}) and {len(screened)} values that fail a screen '
               f'({int(screened.active_machine_months.sum()):,} active machine-months, {int(screened.tickets.sum())} '
               f'tickets in all): {UNKNOWN}, a malformed type value and {len(screened) - 2} types with too few tickets '
               f'or months{higher}.',
               f'High-ticket chart 10 also counts quiet months (first to last transaction) and the {int(excl[QUIET])} '
               f'tickets opened in a month with no transaction. The extra tickets ({more_tickets:+.1%}) {weigh} the '
               f'extra machine-months ({more_months:+.1%}), so its rates {rel_text} for the {TOP_N} types shown '
               f'(fleet: {htm_fleet:.1f} against {all_rate:.1f}).',
               'Source: verification/outputs/db/db_machine_type_rates.csv (Zac\'s SQL, notebook cell 27, re-run on the '
               'full database); tickets counted from verification/outputs/repro_sql_case_monthly.csv and '
               'verification/outputs/db/db_ticket_cohort_exclusions.csv; chart 10 from '
               'verification/outputs/htm_type_rates.csv.'],
        definitions=[zac_data.UNPLANNED_DEFINITION, zac_data.ACTIVE_MONTH_DEFINITION])
    return [style.save(fig, out_dir / 'zac_05_machine_type_rates.png')]


if __name__ == '__main__':
    plot()
