#!/usr/bin/env python3
"""Report figure 1 (Results, Customer fleet ownership): ticket serials reach 42% of the telemetry devices, and
accounts are individual facilities, so fleets come from the installed-base list.

(a) The 7,183 devices in the telemetry device table, split by whether a ticket serial reaches them (3,041, 42%).
(b) Accounts against sites: 845 accounts at 837 distinct address strings and 725 distinct City, State, and ZIP5
    combinations, the two counts of sites.

Inputs: verification/outputs/fu/fu_devices.csv (one row per device; ticket_customer is set when a ticket serial
reaches it), fleet_account_granularity.csv, fleet_customer_naive_rates.csv (one row per account). Notebook 01 checks
the same numbers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig01_ownership'
LABEL = 'fig:ownership'
SHORT = 'Ticket serials and accounts'


def plot(out_dir=S.FIG_DIR):
    devices = pd.read_csv(S.OUT / 'fu' / 'fu_devices.csv', usecols=['machine_id', 'ticket_customer'])
    assert devices.machine_id.is_unique
    n_devices = len(devices)
    n_reached = int(devices.ticket_customer.notna().sum())
    gran = pd.read_csv(S.OUT / 'fleet_account_granularity.csv').set_index('rule')['count']
    accounts = len(pd.read_csv(S.OUT / 'fleet_customer_naive_rates.csv', usecols=[0]))
    strings = int(gran[[r for r in gran.index if r.startswith('distinct address string')][0]])
    zip5 = int(gran['distinct City+State+ZIP5 (any organisation)'])
    S.check('fig01 accounts = granularity table', int(gran['distinct cleaned Account Name']), accounts)

    S.report_check('fig01 devices reached', '3,041', S.num(n_reached))
    S.report_check('fig01 devices', '7,183', S.num(n_devices))
    S.report_check('fig01 share reached', '42%', S.pct(n_reached / n_devices))
    S.report_check('fig01 accounts', '845', S.num(accounts))
    S.report_check('fig01 sites', '725–837', S.span(zip5, strings))

    fig, (ax, bx) = S.figure(1.55, ncols=2, width_ratios=[1.25, 1])

    # (a) one bar: devices reached by a ticket serial (cobalt) and the rest (grey)
    ax.barh(0, n_reached, height=0.42, color=S.COBALT, zorder=3)
    ax.barh(0, n_devices - n_reached, left=n_reached, height=0.42, color=S.GREY_FILL, zorder=3)
    S.label(ax, n_reached / 2, 0.42, f'{S.num(n_reached)} reached ({S.pct(n_reached / n_devices)})', ha='center',
            va='bottom', size=S.FONT, weight='bold', color=S.GREEN)
    S.label(ax, n_reached + (n_devices - n_reached) / 2, 0.42, f'{S.num(n_devices - n_reached)} not on any ticket',
            ha='center', va='bottom', size=S.FONT)
    ax.set_xlim(0, n_devices)
    ax.set_ylim(-0.45, 1.05)
    ax.set_yticks([])
    ax.set_xticks([0, 2000, 4000, 6000, n_devices])
    S.thousands_axis(ax.xaxis)
    ax.set_xlabel('Telemetry devices')
    S.clean(ax, left=False)
    S.panel(ax, 'a', 'Devices that ticket serials reach')

    # (b) accounts against the two counts of sites
    rows = [('Accounts', accounts, S.COBALT), ('Address strings', strings, S.GREY_FILL),
            ('City, State, ZIP5', zip5, S.GREY_FILL)]
    for i, (name, value, colour) in enumerate(rows):
        bx.barh(-i, value, height=0.55, color=colour, zorder=3)
        S.label(bx, value + 12, -i, S.num(value), bbox=dict(fc=S.WHITE, ec='none', pad=0.8))  # grid kept out
    bx.set_yticks([-i for i in range(len(rows))], [r[0] for r in rows])
    bx.set_xlim(0, 980)
    bx.set_xticks([0, 250, 500, 750])
    bx.set_xlabel('Count')
    S.clean(bx, grid='x', left=False)
    S.panel(bx, 'b', 'Accounts and sites')

    S.export(fig, NAME, out_dir)
    return (f'Ticket serials reach {S.num(n_reached)} of {S.num(n_devices)} devices '
            f'({S.pct(n_reached / n_devices).replace("%", chr(92) + "%")}), and accounts are individual facilities '
            f'({S.num(accounts)} accounts at {S.span(zip5, strings).replace("–", "--")} sites), so fleets come from '
            f'the installed-base list. (a)~Devices in the telemetry device table; (b)~sites counted as distinct '
            f'address strings or as City, State, and ZIP5.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
