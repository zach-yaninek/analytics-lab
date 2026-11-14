#!/usr/bin/env python3
"""Report figure 7 (Results, Ticket clock and fields): opening times never step backwards in case-number order (0 of
7,470 steps) but would 1,295–1,312 times on hospital-local clocks, and Trouble Code and Category are filled on 1 of 64
open tickets and on nearly all of the 461 August 2026 tickets of any kind with status Trouble Closed.

(a) The 7,470 steps between consecutive tickets in case-number order (all 7,471 tickets, of any kind), with the steps
    that go backwards, on the export clock and on hospital-local clocks: each recorded time as its hospital's zone
    would show it, under the two maps from hospital location to zone (the state with 3-digit ZIP rules for the states
    that span two zones, and the state alone). The report's range is these two counts.
(b) The 64 open tickets (status Dispatch, all opened in August 2026) and the 461 tickets opened in August 2026 with
    status Trouble Closed: the share with a Trouble Code and the share with a Category. The report gives no count for
    "nearly all"; as notebook 05 does, we read it as at least 95%, but fewer than all, of the 461 having both fields.

IPA's answers (one U.S. Eastern clock; Category set near close; the export holds only final values) are records of a
meeting, so nothing here checks them.

Inputs: verification/outputs/case_order_steps.csv (steps and backward steps by clock and zone map), ts_facts.csv,
ts_field_fill_rates.csv (fill shares by status and by age at export), ts_text_markers_by_month.csv (tickets by
opening month), fu/fu_ticket_last10.csv (one row per device-matched ticket and window: the fields of the one August
Trouble Closed ticket opened 30 days or more before the export), and, for cross-checks, audit_case_status_by_month.csv,
audit_case_service_group_by_status.csv and audit_case_missing_category_composition.csv. Notebook 05 checks the same
numbers.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig07_clock'
LABEL = 'fig:clock'
SHORT = 'Ticket clock and issue fields'

OPEN = 'open (Status=Dispatch)'
CLOSED = 'closed (all other statuses)'
FIELDS = {'Trouble Code': 'Trouble Code', 'Category': 'Trouble Code Category'}   # name: column of the fill table
RECENT = ['age <7d Trouble Closed only', 'age 7-30d Trouble Closed only']      # Trouble Closed, under 30 days old
NOT_UNPLANNED = ['Planned work', 'Cancelled request', 'Duplicate case']        # the kinds the Definitions leave out
NEARLY_ALL = 0.95             # notebook 05's reading of "nearly all": at least 95%, but fewer than all


def filled(fill, group, column):
    """Tickets in a group of ts_field_fill_rates.csv that carry a field: the group's share times its tickets (the
    shares have four decimals, which pins down the count in any group under 5,000 tickets; notebook 05)."""
    count = fill.loc[group, column] * fill.loc[group, 'tickets']
    assert abs(count - round(count)) < 0.25, (group, column, count)
    return int(round(count))


def how_many(count, total):
    """The report's words for how many of a group have both fields (notebook 05)."""
    if count == total:
        return 'all'
    return 'nearly all' if count >= NEARLY_ALL * total else f'{count} of {total}'


def clocks(n_steps):
    """Backward steps in case-number order on the export clock and, shown locally, under the two zone maps."""
    order = pd.read_csv(S.OUT / 'case_order_steps.csv')
    export, local = order.iloc[0], order.iloc[1:]
    assert export.clock == 'export clock, as recorded'
    S.check('fig07 every clock counts the same steps', 1,
            int(export.steps == n_steps and (local.steps == n_steps).all()))
    shown = local[local.clock.str.startswith('shown locally')]        # as each hospital's zone would show the time
    read_local = local[local.clock.str.startswith('read as local')]   # another simulation, which the report leaves out
    S.check('fig07 two zone maps, each shown locally and read as local', 1,
            int(len(shown) == len(read_local) == 2 and len(shown) + len(read_local) == len(local)))
    zip3 = shown[shown.zone_map.str.startswith('state + ZIP3')].iloc[0]
    state = shown[shown.zone_map.str.startswith('state only')].iloc[0]
    S.check('fig07 more than 1,200 backward steps on every local clock (docs/04 §2.1)', 1,
            int((local.backward > 1200).all()))
    return export, zip3, state


def august_closed(fact, fill, tickets_by_month, month):
    """The tickets opened in the month with status Trouble Closed, and how many carry each field (notebook 05)."""
    status_counts = ast.literal_eval(fact['B', 'status_counts'])
    other = {'Dispatch': ast.literal_eval(fact['C', 'open_tickets_by_month']),
             **ast.literal_eval(fact['C', 'other_closed_statuses_by_month'])}
    assert set(other) | {'Trouble Closed'} == set(status_counts)
    assert all(sum(per_month.values()) == status_counts[s] for s, per_month in other.items())
    in_month = {s: per_month.get(month, 0) for s, per_month in other.items()}
    n_closed = int(tickets_by_month[month]) - sum(in_month.values())
    audit = pd.read_csv(S.OUT / 'audit_case_status_by_month.csv').set_index('month').loc[month]
    S.check('fig07 August Trouble Closed = audit_case_logic.py', int(audit['Trouble Closed']), n_closed)
    S.check('fig07 August statuses = audit_case_logic.py', 0,
            sum(abs(int(audit[s]) - n) for s, n in in_month.items()))

    # Under 30 days old at export: the fill table's two Trouble Closed age groups, all opened in the month
    export_ref = pd.Timestamp(fact['load', 'latest_timestamp_any_column (export ran at/after)'])
    cut_7, cut_30 = export_ref - pd.Timedelta(days=7), export_ref - pd.Timedelta(days=30)
    S.check('fig07 every ticket under 30 days old was opened in the month', 1,
            int(cut_30.strftime('%Y-%m') == month == pd.Timestamp(fact['load', 'last_opened']).strftime('%Y-%m')))
    recent = pd.DataFrame([[int(fill.loc[g, 'tickets'])] + [filled(fill, g, c) for c in FIELDS.values()]
                           for g in RECENT], columns=['tickets', *FIELDS])

    # The rest were opened earlier in the month, 30 days or more before the export: read from the per-ticket table
    last10 = pd.read_csv(S.OUT / 'fu' / 'fu_ticket_last10.csv',
                         usecols=['case_id', 'opened_at_eastern', 'status', 'trouble_code', 'category'])
    last10 = last10.drop_duplicates('case_id')     # one row per ticket and window
    opened = pd.to_datetime(last10.opened_at_eastern)
    in_comparison = (last10.status == 'Trouble Closed') & (opened.dt.strftime('%Y-%m') == month)
    older = last10[in_comparison & (opened <= cut_30)]
    S.check('fig07 the per-ticket table holds the older August Trouble Closed tickets',
            int(n_closed - recent.tickets.sum()), len(older))
    matched = [last10[in_comparison & (opened > cut_7)], last10[in_comparison & (opened > cut_30) & (opened <= cut_7)]]
    S.check('fig07 the device-matched tickets of each age group are among the group', 1,
            int(all(len(m) <= r.tickets and m.trouble_code.notna().sum() <= r['Trouble Code']
                    and m.category.notna().sum() <= r.Category for m, (_, r) in zip(matched, recent.iterrows()))))
    with_field = {'Trouble Code': int(recent['Trouble Code'].sum() + older.trouble_code.notna().sum()),
                  'Category': int(recent.Category.sum() + older.category.notna().sum())}
    return n_closed, with_field


def plot(out_dir=S.FIG_DIR):
    facts = pd.read_csv(S.OUT / 'ts_facts.csv')
    fact = {(section, item): value
            for section, item, value in facts[['section', 'item', 'value']].itertuples(index=False)}
    fill = pd.read_csv(S.OUT / 'ts_field_fill_rates.csv').set_index('group')
    tickets_by_month = pd.read_csv(S.OUT / 'ts_text_markers_by_month.csv').set_index('month')['tickets']
    groups = pd.read_csv(S.OUT / 'audit_case_service_group_by_status.csv').set_index('service_group')

    # (a) the steps in case-number order: one fewer than the tickets
    n_tickets = int(tickets_by_month.sum())
    S.check('fig07 tickets = the rows timestamp_semantics.py loads', int(fact['load', 'rows']), n_tickets)
    S.check('fig07 tickets = open + closed in the fill table',
            int(fill.loc[OPEN, 'tickets'] + fill.loc[CLOSED, 'tickets']), n_tickets)
    S.check('fig07 tickets = audit_case_logic.py\'s service groups', int(groups.loc['All', 'All']), n_tickets)
    n_steps = n_tickets - 1
    export, zip3, state = clocks(n_steps)

    # (b) open tickets: all opened in one month, which sets the comparison month
    n_open = int(fill.loc[OPEN, 'tickets'])
    open_field = {name: filled(fill, OPEN, column) for name, column in FIELDS.items()}
    S.check('fig07 open tickets with a Trouble Code = timestamp_semantics.py\'s count',
            int(fact['C', 'open_tickets_with_trouble_code']), open_field['Trouble Code'])
    dispatch = groups['Dispatch']
    S.check('fig07 open tickets = audit_case_logic.py\'s', int(dispatch['All']), n_open)
    S.check('fig07 all open tickets unplanned (two unplanned service groups)', n_open,
            int(dispatch['Missing trouble code'] + dispatch['Other recorded issue']))
    S.check('fig07 open tickets in the planned, canceled, or duplicate groups', 0, int(dispatch[NOT_UNPLANNED].sum()))
    no_category = pd.read_csv(S.OUT / 'audit_case_missing_category_composition.csv').query("status == 'Dispatch'")
    S.check('fig07 open tickets without a Category also lack a Trouble Code', 1,
            int(set(no_category.trouble_code) == {'[Missing]'}))
    S.check('fig07 open tickets with a Category = audit_case_logic.py\'s', int(n_open - no_category.cases.sum()),
            open_field['Category'])
    open_by_month = ast.literal_eval(fact['C', 'open_tickets_by_month'])
    (month,) = open_by_month
    S.check('fig07 all open tickets opened in one month', n_open, open_by_month[month])
    month_label = pd.Period(month, freq='M').strftime('%B %Y')

    n_closed, closed_field = august_closed(fact, fill, tickets_by_month, month)
    # Every one of the 461 has a Trouble Code, so those with a Category have both fields
    both_closed = closed_field['Trouble Code'] + closed_field['Category'] - n_closed
    S.check('fig07 every August Trouble Closed ticket has a Trouble Code', n_closed, closed_field['Trouble Code'])
    both_open = open_field['Category']     # the open tickets with a Category are the ones with a Trouble Code

    S.report_check('fig07 steps in case-number order', '7,470', S.num(n_steps))
    S.report_check('fig07 backward steps on the export clock', '0', S.num(export.backward))
    lo, hi = sorted((int(zip3.backward), int(state.backward)))
    S.report_check('fig07 backward steps on hospital-local clocks (two zone maps)', '1,295–1,312', S.span(lo, hi))
    S.report_check('fig07 open tickets', '64', S.num(n_open))
    S.report_check('fig07 open tickets with a Trouble Code', '1', S.num(open_field['Trouble Code']))
    S.report_check('fig07 open tickets with a Category', '1', S.num(open_field['Category']))
    S.report_check('fig07 month compared', 'August 2026', month_label)
    S.report_check('fig07 August 2026 tickets with status Trouble Closed', '461', S.num(n_closed))
    S.report_check('fig07 of the 461, with both fields', 'nearly all', how_many(both_closed, n_closed))

    fig, (ax, bx) = S.figure(1.8, ncols=2, width_ratios=[1.05, 1])

    # (a) each clock's steps: cobalt those that go backwards, grey the rest; each count just right of its segment,
    # except the export clock's: it has no segment, and the one green readout needs white (4.6:1, not 3.0:1 on the
    # grey fill), so it sits just above the bar's start
    rows = [('Export clock', export.backward), ('Hospital-local,\nstate and ZIP3', zip3.backward),
            ('Hospital-local,\nstate only', state.backward)]
    for y, (name, back) in enumerate(rows):
        ax.barh(y, back, height=0.5, color=S.COBALT, zorder=3)
        ax.barh(y, n_steps - back, left=back, height=0.5, color=S.GREY_FILL, zorder=3)
        key = y == 0                         # the one green readout: no backward step on the export clock
        text = f'{S.num(back)} backward'
        S.check(f'fig07 (a) label {name!r}', back, int(text.split()[0].replace(',', '')))
        if key:
            S.label(ax, 0, y - 0.3, text, va='bottom', size=S.FONT, weight='bold', color=S.GREEN, zorder=4)
        else:
            S.label(ax, back + 90, y, text, zorder=4)
    S.check('fig07 (a) the green readout labels a clock with no backward step (no segment to sit beside)', 0,
            int(rows[0][1]))
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], linespacing=1.0)
    ax.set_ylim(len(rows) - 0.45, -0.72)
    ax.set_xlim(0, n_steps)
    ax.set_xticks([0, 2500, 5000, n_steps])       # even steps that leave the total's tick clear
    S.thousands_axis(ax.xaxis)
    ax.set_xlabel('Steps between consecutive tickets')
    S.clean(ax, left=False)
    S.panel(ax, 'a', 'Backward steps in case-number order')

    # (b) each group's share with each field: cobalt filled, grey blank; the count after the filled part
    groups_b = [(f'{S.num(n_open)} open tickets', n_open, open_field, 0.0),
                (f'{S.num(n_closed)} Trouble Closed tickets', n_closed, closed_field, 2.75)]
    ticks, names = [], []
    for heading, n, field, y0 in groups_b:
        S.label(bx, 0, y0 - 0.68, heading, va='center')
        for j, name in enumerate(FIELDS):
            y, share = y0 + j, field[name] / n
            bx.barh(y, share, height=0.56, color=S.COBALT, zorder=3)
            bx.barh(y, 1 - share, left=share, height=0.56, color=S.GREY_FILL, zorder=3)
            text = f'{S.num(field[name])} of {S.num(n)}'
            S.check(f'fig07 (b) label {heading} {name}', field[name], int(text.split()[0].replace(',', '')))
            x = share + 0.025 if share < 0.9 else 1.025
            S.label(bx, x, y, text, zorder=4)
            ticks.append(y)
            names.append(name)
    bx.set_yticks(ticks, names)
    bx.set_ylim(ticks[-1] + 0.55, -1.0)
    bx.set_xlim(0, 1.3)
    bx.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    bx.spines['bottom'].set_bounds(0, 1)      # the scale ends at 100%; the counts sit beyond it
    S.pct_axis(bx.xaxis)
    bx.set_xlabel('Share of tickets')
    S.clean(bx, left=False)
    S.panel(bx, 'b', f'Fields filled on {month_label} tickets')

    S.export(fig, NAME, out_dir)
    # 'of any kind', as the report says: the 461 are not limited to unplanned tickets, the report's default
    # The fields' result goes in (b)'s entry, so each panel has one and the caption keeps to three lines
    return (f'Opening times never step backwards in case-number order ({S.num(export.backward)} of {S.num(n_steps)} '
            f'steps) but would {S.num(lo)}--{S.num(hi)} times on hospital-local clocks. (a)~Two zone maps; '
            f'(b)~Trouble Code and Category are filled on {S.num(both_open)} of {S.num(n_open)} open tickets '
            f'vs. {how_many(both_closed, n_closed)} of {S.num(n_closed)} {month_label} Trouble Closed tickets of any '
            f'kind.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
