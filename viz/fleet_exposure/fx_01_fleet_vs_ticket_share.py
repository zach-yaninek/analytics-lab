#!/usr/bin/env python3
"""Fleet chart 1: each model's share of the installed base against its share of unplanned tickets.

Replaces the retired raw-count chart high_ticket/htm_09 (tickets by model, with a disclaimer that the counts ignore
fleet size). IPA's installed-base list now gives the denominator, so the same question can be answered directly: do
the models with the most tickets get them mostly because so many of them are installed?

Paired horizontal bars, one pair per model: gray = the model's share of installed machine-months, blue = its share of
unplanned tickets, each with its value at the bar end. A model with the fleet's ticket rate has two bars of equal
length; a longer blue bar means a higher rate. Rows: the TOP_N models with the most installed machine-months, then
one row for all other models. The three models with the most tickets have bold labels. The title compares their
combined share of tickets with their combined share of installed machine-months; its verb is computed from the two
numbers (verdict() below): "mostly reflects" when at least two thirds of their ticket share is matched by their share
of installed machine-months (their combined rate is at most 1.5 times the fleet's), "only partly reflects" down to
one half (at most twice the fleet's rate), "far exceeds" below that, "is below" when the ticket share is the smaller.
The subtitle gives their combined rate against the fleet's; a footer note says which of the three are above the fleet
rate on their own 95% interval (as in chart fx_02), so "mostly" is not read as "only".

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here):
  verification/outputs/fleet/fx_model_rates.csv      model, machines, months, tickets, share_of_months,
                                                     share_of_tickets, rate_per_100, ratio_lo, vs_fleet (one row
                                                     per model); share_of_machines, ci_lo and unlisted_tickets for
                                                     the consistency checks
  verification/outputs/fleet/fx_unlisted_by_model.csv  unlisted_tickets per model (tickets on serials not on the list)
  verification/outputs/fleet/fx_summary.json         period, third-party exclusion, fleet rate and the unplanned
                                                     tickets in the period (drawn); fleet totals, unlisted and match
                                                     counts for the consistency checks
Output:  viz/figures/fx_01_fleet_vs_ticket_share.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_01_fleet_vs_ticket_share.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_01_fleet_vs_ticket_share.png'
TOP_N = 10        # models shown by installed machine-months; the rest are one row
N_BUSY = 3        # the models with the most tickets, compared in the title
ROW_IN = 0.46     # inches per model row
BAR_H = 0.30      # bar thickness in rows (about 22 px at 150 dpi with ROW_IN)
OFFSET = 0.165    # bar centre above / below the row centre (a small gap between the two bars of a pair)
OTHER_GAP = 0.35  # extra space above the "other models" row
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
MOSTLY, PARTLY = 2 / 3, 1 / 2  # share of months / share of tickets at or above which the title says mostly / partly
WORDS = {2: 'two', 3: 'three', 4: 'four', 5: 'five'}
NOT_ABOVE = {'not different': 'is not different from it', 'below': 'is below it',
             'not estimable (one account)': 'is not estimable (one account)'}


def verdict(ticket_share, month_share):
    """How the busiest models' ticket share compares with their share of installed machine-months."""
    if ticket_share < month_share:
        return 'is below'
    ratio = month_share / ticket_share  # = fleet rate / their combined rate
    return 'mostly reflects' if ratio >= MOSTLY else 'only partly reflects' if ratio >= PARTLY else 'far exceeds'


def names(models):
    """'A', 'A and B', 'A, B and C'."""
    models = list(models)
    return models[0] if len(models) == 1 else ', '.join(models[:-1]) + ' and ' + models[-1]


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    F = S['fleet']
    m = fleet.load('model_rates')
    unl = fleet.load('unlisted_by_model').set_index('model')

    # Totals: the model table covers the whole population (exposed machines) and every ticket.
    tickets, months = float(m.tickets.sum()), float(m.months.sum())
    style.check('fx_01 model tickets = fleet tickets', F['tickets'], tickets)
    style.check('fx_01 model months = fleet installed machine-months', F['months'], months, 1e-6)
    style.check('fx_01 model machines = exposed machines', F['machines_exposed'], int(m.machines.sum()))
    style.check('fx_01 machines per model = share_of_machines x exposed machines', 0,
                float((m.machines - m.share_of_machines * F['machines_exposed']).abs().max()), 1e-6)
    style.check('fx_01 every model has installed machine-months', 0, int((m.months <= 0).sum()))
    # The drawn shares (CSV columns) against shares recomputed from the counts and the summary totals.
    style.check('fx_01 share_of_months = months / fleet months', 0,
                float((m.share_of_months - m.months / F['months']).abs().max()), 1e-12)
    style.check('fx_01 share_of_tickets = tickets / fleet tickets', 0,
                float((m.share_of_tickets - m.tickets / F['tickets']).abs().max()), 1e-12)

    # Rows: most installed machine-months first; the rest grouped.
    by_months = m.sort_values(['months', 'model'], ascending=[False, True], kind='mergesort')
    style.check('fx_01 no tie at the top-N boundary', 1,
                int(by_months.months.iloc[TOP_N - 1] > by_months.months.iloc[TOP_N]))
    shown, rest = by_months.head(TOP_N), by_months.iloc[TOP_N:]
    other_months = 1 - shown.share_of_months.sum()
    other_tickets = 1 - shown.share_of_tickets.sum()
    style.check('fx_01 other models: share of months', float(rest.months.sum() / F['months']), other_months, 1e-12)
    style.check('fx_01 other models: share of tickets', float(rest.tickets.sum() / F['tickets']), other_tickets,
                1e-12)
    other_machines = F['machines_exposed'] - int(shown.machines.sum())
    style.check('fx_01 other models: machines', int(rest.machines.sum()), other_machines)

    # The busiest models (most tickets) and their combined shares.
    by_tickets = m.sort_values(['tickets', 'model'], ascending=[False, True], kind='mergesort')
    style.check('fx_01 no tie at the busiest-models boundary', 1,
                int(by_tickets.tickets.iloc[N_BUSY - 1] > by_tickets.tickets.iloc[N_BUSY]))
    busy = by_tickets.head(N_BUSY)
    busy_names = busy.model.tolist()
    style.check('fx_01 the busiest models are among the rows shown', 1, int(set(busy_names) <= set(shown.model)))
    t_share, m_share = float(busy.share_of_tickets.sum()), float(busy.share_of_months.sum())
    style.check('fx_01 busiest: share of tickets', float(busy.tickets.sum()) / F['tickets'], t_share, 1e-12)
    style.check('fx_01 busiest: share of months', float(busy.months.sum()) / F['months'], m_share, 1e-12)
    also_most_installed = set(busy_names) == set(by_months.model.head(N_BUSY))
    busy_rate = 100 * busy.tickets.sum() / busy.months.sum()
    fleet_rate = fleet.fleet_rate(S)
    style.check('fx_01 fleet rate = tickets / months', fleet_rate, 100 * tickets / months, 1e-9)
    style.check('fx_01 busiest: combined rate = months-weighted rate_per_100', busy_rate,
                float((busy.rate_per_100 * busy.months).sum() / busy.months.sum()), 1e-9)
    style.check('fx_01 rate ratio = share of tickets / share of months', busy_rate / fleet_rate, t_share / m_share,
                1e-9)
    verb = verdict(t_share, m_share)
    rate_ratio = float(busy_rate / fleet_rate)  # from the counts; = share of tickets / share of months
    expect_verb = ('is below' if rate_ratio < 1 else 'mostly reflects' if rate_ratio <= 1 / MOSTLY else
                   'only partly reflects' if rate_ratio <= 1 / PARTLY else 'far exceeds')
    style.check('fx_01 title verb = the rule applied to the combined rate ratio', 1, int(verb == expect_verb))

    # Which of the busiest models are above the fleet rate on their own 95% interval (chart fx_02's classes).
    style.check('fx_01 busiest: "above" = ratio-to-fleet interval wholly above 1', 0,
                int(((busy.ratio_lo > 1) != (busy.vs_fleet == 'above')).sum()))
    style.check('fx_01 busiest: every class not "above" is worded', 1,
                int(set(busy.vs_fleet) - {'above'} <= set(NOT_ABOVE)))
    above, not_above = busy[busy.vs_fleet == 'above'], busy[busy.vs_fleet != 'above']
    boot_only = bool((busy.ci_method == 'cluster bootstrap').all())

    # Tickets left out: unplanned tickets on serials that are not on the list (removed or replaced machines).
    n_unl = int(unl.unlisted_tickets.sum())
    style.check('fx_01 unlisted tickets = summary', S['unlisted']['tickets'], n_unl)
    style.check('fx_01 unlisted tickets = model table column', float(m.unlisted_tickets.sum()), n_unl)
    style.check('fx_01 unlisted tickets = match table', S['match']['unplanned tickets on unlisted serials'], n_unl)
    in_period = S['match']['unplanned tickets in period']
    style.check('fx_01 tickets in period = listed + unlisted', in_period,
                S['match']['unplanned tickets on listed machines'] + n_unl)
    busy_unl = int(unl.unlisted_tickets.reindex(busy_names).fillna(0).sum())
    style.check('fx_01 busiest: unlisted tickets (model table)', float(busy.unlisted_tickets.sum()), busy_unl)
    most_unl = unl.unlisted_tickets.sort_values(ascending=False, kind='mergesort')
    most_unl_model, most_unl_n = most_unl.index[0], int(most_unl.iloc[0])
    style.check('fx_01 most unlisted tickets (model table)',
                float(m.set_index('model').unlisted_tickets.max()), most_unl_n)
    style.check('fx_01 no tie for the most unlisted tickets', 1, int(most_unl.iloc[0] > most_unl.iloc[1]))

    # ---------------------------------------------------------------------------------------------- Text
    n_word = WORDS.get(N_BUSY, str(N_BUSY))
    title = (f'The {n_word} busiest models\' {style.pct(t_share, 0)} of tickets {verb} their '
             f'{style.pct(m_share, 0)} of installed machine-months')
    installed = (f'are also the {n_word} with the most installed machine-months' if also_most_installed else
                 'rank ' + ', '.join(str(int(np.flatnonzero(by_months.model.to_numpy() == n)[0]) + 1)
                                     for n in busy_names) + ' by installed machine-months')
    subtitle = [f'Share of installed machine-months (gray) and of unplanned tickets (blue) by model, '
                f'{fleet.period_text(S)}: the {TOP_N} models with the most installed machine-months and the other '
                f'{len(rest)} combined. Two bars of equal length = the fleet\'s ticket rate.',
                f'The {n_word} models with the most tickets (bold) {installed}; their combined rate is '
                f'{rate_ratio:.2f}× the fleet\'s ({busy_rate:.1f} against {fleet_rate:.1f} unplanned '
                f'tickets per 100 installed machine-months).']
    if not_above.empty:
        each = f'all {n_word} run above the fleet rate'
    else:
        each = (f'{names(above.model)} {"runs" if len(above) == 1 else "run"} above the fleet rate and '
                if len(above) else f'none of the {n_word} runs above the fleet rate: ')
        each += names(f'{r.model} {NOT_ABOVE[r.vs_fleet]}' for r in not_above.itertuples())
    interval = ('cluster bootstrap over accounts' if boot_only else
                'cluster bootstrap over accounts, or the wider of that and Byar\'s Poisson interval')
    notes = [f'Shares and rates are crude, not adjusted for machine age. On their own 95% intervals ({interval}; '
             f'chart fx_02), {each}.',
             f'Not counted: {n_unl:,} unplanned tickets ({style.pct(n_unl / in_period, 1)} of the {in_period:,} in '
             f'the period) on serials that are not on the list (removed or replaced machines, exposure unknown); '
             f'{busy_unl} of them on these {n_word} models, the most ({most_unl_n}) on {most_unl_model}.',
             fleet.source('model_rates', 'unlisted_by_model')]

    # ---------------------------------------------------------------------------------------------- Drawing
    labels = [f'{r.model}  ·  {r.machines:,} machines' for r in shown.itertuples()]
    labels.append(f'Other {len(rest)} models  ·  {other_machines:,} machines')
    gray = 100 * np.append(shown.share_of_months.to_numpy(), other_months)
    blue = 100 * np.append(shown.share_of_tickets.to_numpy(), other_tickets)
    y = -np.arange(len(labels), dtype=float)
    y[-1] -= OTHER_GAP

    width = max(11.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    fig, ax = style.figure(width, 4.6 + ROW_IN * (len(labels) + OTHER_GAP))
    ax.barh(y + OFFSET, gray, height=BAR_H, color=style.GRAY_LIGHT, linewidth=0)
    ax.barh(y - OFFSET, blue, height=BAR_H, color=style.BLUE, linewidth=0)
    xmax = max(gray.max(), blue.max()) * 1.42
    pad = xmax * 0.008
    for i, (yi, g, b) in enumerate(zip(y, gray, blue)):
        # The first row names the two series, in place of a legend.
        g_txt = f'{g:.1f}%' + ('  of installed machine-months' if i == 0 else '')
        b_txt = f'{b:.1f}%' + ('  of unplanned tickets' if i == 0 else '')
        ax.text(g + pad, yi + OFFSET, g_txt, va='center', ha='left', fontsize=9, color=style.INK2)
        ax.text(b + pad, yi - OFFSET, b_txt, va='center', ha='left', fontsize=9, color=style.BLUE)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    for tick, name in zip(ax.get_yticklabels(), shown.model.tolist() + [None]):
        if name in busy_names:
            tick.set_fontweight('bold')
            tick.set_color(style.INK)
    ax.set_ylim(y[-1] - 0.6, 0.6)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of all installed machine-months (gray) or of all unplanned tickets (blue)')

    style.frame(fig, title, subtitle, notes=notes,
                definitions=[fleet.installed_month_definition(S), fleet.unplanned_definition()])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
