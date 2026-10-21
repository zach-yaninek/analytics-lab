#!/usr/bin/env python3
"""Fleet chart 6: the customers with the most unplanned tickets, observed against expected tickets.

A customer with many tickets is not necessarily a problem customer: it may simply have many machines, or models and
ages that generate tickets at a high fleet rate. This chart puts each of the TOP_N busiest customers' unplanned
tickets next to the tickets its machines would generate at fleet rates for their model and age (expected tickets,
the model + age fit of verification/fleet_exposure.py). One row per customer, busiest on top, labelled
'Customer NNN (n machines)': a gray ring at expected tickets, a filled dot at observed tickets, joined by a thin
line, with both counts at the outer ends and the standardised ticket ratio (STR = observed / expected) in a column
at the right, bold when the customer is flagged. Dot colour, as in fx_07: blue = consistent outlier, orange =
flagged (Poisson rule) but not consistent, gray = not flagged. The title counts the flagged and consistent customers
among the TOP_N and says whether the busiest one is in line with its fleet (not flagged, and the 95% interval of its
STR includes 1); the subtitle gives that customer's numbers (and its lead over the next customer) and the share of
the fleet's tickets and machines the TOP_N hold. The footer gives the definitions, then a caveat (what expected
tickets allow for; which machines are counted; how many flagged and consistent customers are not shown), how the
STR interval is computed, and the source.

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and data/private/fx_private_customer_names.csv exists. It is written to
  deliverables/ (gitignored) and must never be committed; its privacy warning is the first line of the subtitle.

Inputs (computed by verification/fleet_exposure.py; nothing is refitted here):
  verification/outputs/fleet/fx_customer_rates.csv   one row per customer: tickets, expected, machines, STR,
                                                     STR_lo/STR_hi (Byar), p_poisson, q_poisson, poisson_flagged,
                                                     variants_flagged, O_h1/E_h1/p_h1, O_h2/E_h2/p_h2,
                                                     consistent_outlier
  verification/outputs/fleet/fx_machine_flags.csv    every machine with a ticket (customer, tickets, expected):
                                                     independent check of each customer's tickets, machines with a
                                                     ticket and (as a lower bound) expected tickets
  verification/outputs/fleet/fx_match.csv            listed and population accounts and machines, for the checks
  verification/outputs/fleet/fx_summary.json         period, flag thresholds, fleet totals, customer flag counts
  data/private/fx_private_customer_names.csv         customer -> real_account_name (real-name version only;
                                                     gitignored; via fleet.real_customer_names())
Outputs:
  viz/figures/fx_06_busiest_customers.png
  deliverables/fx_06_busiest_customers_REALNAMES.png   (private=True only)

Run:  cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_06_busiest_customers.py
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_06_busiest_customers.png'
REAL_PNG = 'fx_06_busiest_customers_REALNAMES.png'
TOP_N = 15                # customers shown: the most unplanned tickets
ROW_IN = 0.36             # inches per customer row
FIG_H = 5.3               # figure height besides the rows: title band, footer, x axis (inches)
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
LABEL_IN_PER_CHAR = 0.075  # approximate width of one tick-label character (10 pt), for the real-name width
DOT = 62                  # marker area (pt^2): about 8 pt across
PRIVACY_WARNING = ('Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                   '(gitignored); never commit.')
CLASSES = [  # (key, dot colour, legend label): fx_07's classes; mid gray, as light gray would vanish on the line
    ('consistent', style.BLUE, 'Observed: consistent outlier'),
    ('flagged', style.ORANGE, 'Observed: flagged, not consistent'),
    ('not_flagged', style.GRAY, 'Observed: not flagged'),
]
COLOUR = {key: colour for key, colour, _ in CLASSES}


# ---------------------------------------------------------------------------------------------------------------
# Independent recomputations for the checks (Poisson tail, Benjamini-Hochberg, Byar), written here from the
# definitions so the flags and intervals in the CSV are tested, not copied.
# ---------------------------------------------------------------------------------------------------------------
def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), from log-space terms."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    log_term = lambda j: -mu + j * math.log(mu) - math.lgamma(j + 1)  # noqa: E731
    if k <= mu:
        return max(0.0, 1.0 - sum(math.exp(log_term(j)) for j in range(k)))
    total, j = 0.0, k
    while True:
        t = math.exp(log_term(j))
        total += t
        if t < total * 1e-16 or j > k + 20_000:
            return total
        j += 1


def bh(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def byar_interval(k, z):
    """Byar's approximation to the exact Poisson interval for a count k > 0."""
    lo = k * (1 - 1 / (9 * k) - z / (3 * math.sqrt(k))) ** 3
    hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * math.sqrt(k + 1))) ** 3
    return lo, hi


def class_of(row):
    if row.consistent_outlier:
        return 'consistent'
    return 'flagged' if row.poisson_flagged else 'not_flagged'


def checks(S, cr, mf, match):
    """Consistency checks on the whole customer table; returns the TOP_N rows in drawing order."""
    d, F, C = S['definitions'], S['fleet'], S['customers']
    style.check('fx_06 customers = population accounts', F['accounts'], len(cr))
    # Subtitle: the customers are the listed accounts less the one(s) with only third-party-plan machines.
    style.check('fx_06 customers = listed accounts - third-party-only accounts',
                match['listed accounts'] - match['accounts with only third-party machines (excluded)'], len(cr))
    style.check('fx_06 third-party machines (note) = match table', S['third_party']['machines'],
                match['listed machines on a third-party service plan (excluded)'])
    # Note: machines installed after the period are not counted in the machines column.
    style.check('fx_06 machines installed after the period = population - counted machines',
                match['population machines installed after the period (0 months)'],
                F['machines'] - int(cr.machines.sum()))
    style.check('fx_06 customer tickets sum to the fleet', F['tickets'], int(cr.tickets.sum()))
    style.check('fx_06 expected sums to observed (fit property)', F['tickets'], float(cr.expected.sum()), 1e-6)
    style.check('fx_06 machines sum to exposed machines', F['machines_exposed'], int(cr.machines.sum()))
    # Tickets per customer from the machine table (every machine with a ticket).
    by_cust = mf.groupby('customer').tickets.sum().reindex(cr.customer).fillna(0).to_numpy()
    style.check('fx_06 customer tickets = sum of its machines\' tickets', 0,
                int(np.abs(by_cust - cr.tickets.to_numpy()).max()))
    style.check('fx_06 machine tickets sum to the fleet', F['tickets'], int(mf.tickets.sum()))
    # STR = observed / expected.
    pos = cr.expected > 0
    style.check('fx_06 STR = tickets / expected', 0,
                float((cr.tickets[pos] / cr.expected[pos] - cr.STR[pos]).abs().max()), 1e-9)

    # Flags recomputed: Poisson upper tail, BH over customers with expected > 0, >= min tickets.
    p = np.array([poisson_upper(o, e) for o, e in zip(cr.tickets[pos], cr.expected[pos])])
    style.check('fx_06 Poisson p recomputed', 0, float(np.abs(p - cr.p_poisson[pos].to_numpy()).max()), 1e-9)
    flag = np.zeros(len(cr), bool)
    flag[pos.to_numpy()] = (cr.tickets[pos].to_numpy() >= d['min_flag_tickets']) & (bh(p) < d['q_cut'])
    style.check('fx_06 flagged customers recomputed = poisson_flagged', 0,
                int((flag != cr.poisson_flagged.to_numpy()).sum()))
    style.check('fx_06 flagged customers = summary', C['poisson_flagged'], int(flag.sum()))
    # Consistent rule recomputed from the variant count and each half's Poisson p.
    p1 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h1, cr.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h2, cr.E_h2)])
    cons = (cr.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < 0.05) & (p2 < 0.05)
    style.check('fx_06 consistent outliers recomputed = consistent_outlier', 0,
                int((cons != cr.consistent_outlier.to_numpy()).sum()))
    style.check('fx_06 consistent outliers = summary', C['consistent_outliers'], int(cons.sum()))

    # The TOP_N: most tickets (ties broken by customer, as the CSV is sorted); no tie at the boundary.
    top = cr.sort_values(['tickets', 'customer'], ascending=[False, True], kind='mergesort').head(TOP_N)
    style.check('fx_06 top rows = CSV order', 1, int(top.customer.tolist() == cr.customer.head(TOP_N).tolist()))
    style.check('fx_06 no tie at the top-N boundary', 1,
                int(cr.tickets.nlargest(TOP_N).min() > cr.tickets.nlargest(TOP_N + 1).min()))
    style.check('fx_06 the busiest customer is unique', 1, int(top.tickets.iloc[0] > top.tickets.iloc[1]))
    style.check('fx_06 consistent outliers shown are flagged', 0,
                int((top.consistent_outlier & ~top.poisson_flagged).sum()))
    style.check('fx_06 every row has expected > 0', 1, int((top.expected > 0).all()))
    # Title counts from the recomputed flags (top.index holds cr's row positions).
    rows = top.index.to_numpy()
    style.check('fx_06 flagged among the top N (title) = recomputed', int(top.poisson_flagged.sum()),
                int(flag[rows].sum()))
    style.check('fx_06 consistent among the top N (title) = recomputed', int(top.consistent_outlier.sum()),
                int(cons[rows].sum()))
    # Each row against the machine table (machines with a ticket only): tickets equal; machines with a ticket
    # equal and no more than the machines drawn; expected at least the expected on those machines.
    mt = mf.groupby('customer').agg(n=('tickets', 'size'), o=('tickets', 'sum'), e=('expected', 'sum')) \
        .reindex(top.customer).fillna(0)
    style.check('fx_06 top-N tickets = machine-table sum', int(top.tickets.sum()), int(mt.o.sum()))
    style.check('fx_06 top-N machines with a ticket = machine table', 0,
                int((mt.n.to_numpy() != top.machines_with_ticket.to_numpy()).sum()))
    style.check('fx_06 top-N machines >= machines with a ticket', 0,
                int((top.machines.to_numpy() < mt.n.to_numpy()).sum()))
    style.check('fx_06 top-N expected >= expected on machines with a ticket', 0,
                int((top.expected.to_numpy() < mt.e.to_numpy() - 1e-9).sum()))
    # Byar interval of the busiest customer's STR.
    b = top.iloc[0]
    lo, hi = byar_interval(int(b.tickets), d['z95'])
    style.check('fx_06 busiest STR_lo = Byar / expected', lo / b.expected, b.STR_lo, 1e-9)
    style.check('fx_06 busiest STR_hi = Byar / expected', hi / b.expected, b.STR_hi, 1e-9)
    return top


def draw(S, cr, top, path, names=None):
    """Draw one version of the chart (pseudonymous when names is None)."""
    F = S['fleet']
    n = len(top)
    name = (lambda c: c) if names is None else (lambda c: names.get(c, c))
    cls = [class_of(r) for r in top.itertuples()]
    n_flag = int(top.poisson_flagged.sum())
    n_cons = int(top.consistent_outlier.sum())
    rest = cr[~cr.customer.isin(set(top.customer))]
    rest_flag, rest_cons = int(rest.poisson_flagged.sum()), int(rest.consistent_outlier.sum())
    style.check('fx_06 flagged shown + not shown = summary', S['customers']['poisson_flagged'], n_flag + rest_flag)
    style.check('fx_06 consistent shown + not shown = summary', S['customers']['consistent_outliers'],
                n_cons + rest_cons)
    # The note counts the consistent outliers not shown among the flagged customers not shown.
    style.check('fx_06 consistent outliers not shown are flagged', 0,
                int((rest.consistent_outlier & ~rest.poisson_flagged).sum()))
    tickets, machines = int(top.tickets.sum()), int(top.machines.sum())
    zero_months = F['machines'] - F['machines_exposed']

    b = top.iloc[0]
    lead = int(top.tickets.iloc[0] - top.tickets.iloc[1])
    style.check('fx_06 busiest lead over the next (independent)', lead,
                int(cr.tickets.max() - cr.tickets.drop(cr.tickets.idxmax()).max()))
    b_in_line = (not b.poisson_flagged) and b.STR_lo <= 1 <= b.STR_hi
    if b_in_line:
        busiest = 'the busiest is in line with its fleet'
    elif b.poisson_flagged:
        busiest = 'including the busiest'
    else:
        busiest = 'the busiest is not flagged'
    title = (f'{n_flag} of the {n} busiest customers are flagged, {n_cons} consistently'
             + ('; ' if b_in_line or not b.poisson_flagged else ', ') + busiest)

    labels = [f'{name(c)} ({m:,} machines)' for c, m in zip(top.customer, top.machines)]
    pseudo_w = LABEL_IN_PER_CHAR * max(len(f'{c} ({m:,} machines)') for c, m in zip(top.customer, top.machines))
    label_w = LABEL_IN_PER_CHAR * max(len(s) for s in labels)
    width = max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN) + max(0.0, label_w - pseudo_w)
    fig, ax = style.figure(width, FIG_H + ROW_IN * n)

    y = np.arange(n)[::-1]  # busiest on top
    xmax = float(max(top.tickets.max(), top.expected.max())) * 1.1
    for yi, o, e, k in zip(y, top.tickets, top.expected, cls):
        ax.plot([e, o], [yi, yi], color=style.GRAY_LIGHT, lw=1.6, solid_capstyle='butt', zorder=1)
        ax.scatter([e], [yi], s=DOT, facecolor=style.SURFACE, edgecolor=style.GRAY, linewidth=1.5, zorder=2)
        ax.scatter([o], [yi], s=DOT, color=COLOUR[k], linewidth=0, zorder=3)
        # Counts at the outer ends: observed beyond its dot, expected beyond its ring.
        right = o >= e
        ax.annotate(f'{o}', xy=(o, yi), xytext=(7 if right else -7, 0), textcoords='offset points', va='center',
                    ha='left' if right else 'right', fontsize=9, color=style.INK2)
        ax.annotate(f'{e:.0f}', xy=(e, yi), xytext=(-7 if right else 7, 0), textcoords='offset points',
                    va='center', ha='right' if right else 'left', fontsize=9, color=style.MUTED)
    # STR column at the right of the plot area (axes x, data y).
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    ax.text(1.02, n - 0.45, 'STR', transform=tr, ha='left', va='bottom', fontsize=9.5, color=style.INK2,
            weight='bold')
    for yi, r, k in zip(y, top.itertuples(), cls):
        flagged = k != 'not_flagged'
        ax.text(1.02, yi, f'{r.STR:.2f}', transform=tr, ha='left', va='center', fontsize=9.5,
                color=style.INK if flagged else style.INK2, weight='bold' if flagged else 'normal')
    style.check('fx_06 drawn STR (2 decimals) = tickets / expected', 0,
                float(np.abs(np.round(top.STR, 2) - np.round(top.tickets / top.expected, 2)).max()))

    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0, xmax)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.tick_params(axis='y', length=0)
    style.thousands_axis(ax.xaxis)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel(f'Unplanned tickets, {fleet.period_text(S)}')
    present = set(cls)
    handles = [Line2D([], [], marker='o', ls='', markersize=8, markerfacecolor=col, markeredgewidth=0, label=lab)
               for c, col, lab in CLASSES if c in present]
    handles.append(Line2D([], [], marker='o', ls='', markersize=8, markerfacecolor=style.SURFACE,
                          markeredgecolor=style.GRAY, markeredgewidth=1.5,
                          label='Expected: their machines\' models and ages at fleet rates'))
    # The bottom rows have the fewest tickets, so the lower right of the plot is empty.
    ax.legend(handles=handles, loc='lower right', frameon=True, facecolor=style.SURFACE, edgecolor='none',
              framealpha=1, handletextpad=0.4)

    share_t, share_m = tickets / F['tickets'], machines / F['machines_exposed']
    if b_in_line:
        b_verdict = 'includes 1; not flagged'
    elif b.poisson_flagged:
        b_verdict = 'flagged'
    else:
        b_verdict = 'excludes 1, but not flagged'
    subtitle = [f'Unplanned tickets (filled dot) against expected tickets (gray ring) for the {n} customers with the '
                f'most unplanned tickets of the {len(cr):,} with machines on IPA\'s installed-base list (third-party '
                f'service plan excluded), {fleet.period_text(S)}; standardised ticket ratio (STR) at the right, bold '
                f'when flagged. Together they have {tickets:,} of the fleet\'s {F["tickets"]:,} unplanned tickets '
                f'({style.pct(share_t)}) on {machines:,} of its {F["machines_exposed"]:,} machines '
                f'({style.pct(share_m)}).',
                f'The busiest, {name(b.customer)} (by {lead} ticket{"" if lead == 1 else "s"}): '
                f'{b.tickets} tickets against {b.expected:.1f} expected, STR {b.STR:.2f} (95% interval '
                f'{b.STR_lo:.2f} to {b.STR_hi:.2f}; {b_verdict}).']
    if names is not None:
        subtitle.insert(0, PRIVACY_WARNING)  # first line, so the warning is read before the chart
    notes = [f'Expected tickets allow for models and machine ages only, not coverage, use or reporting; tickets '
             f'cluster within a customer\'s machines, so a flag calls for follow-up, not proof. Machines = listed '
             f'machines installed before the end of the period ({zero_months} installed later and '
             f'{S["third_party"]["machines"]} on a third-party service plan left out). Not shown: {rest_flag} more '
             f'flagged customers ({rest_cons} of them consistent outliers), all with fewer tickets.',
             'STR interval: Byar\'s approximation to the exact Poisson interval for the observed count, divided by '
             'expected tickets; it does not allow for tickets clustering within a customer, so it is if anything '
             'too narrow.',
             fleet.source('customer_rates')[:-1]
             + ('; names from data/private/fx_private_customer_names.csv (gitignored).' if names is not None
                else '.')]
    style.frame(fig, title, subtitle, notes=notes,
                definitions=[fleet.unplanned_definition(), fleet.expected_definition(S), fleet.STR_DEFINITION,
                             fleet.flagged_customer_definition(S), fleet.consistent_definition(S)])
    return style.save(fig, path)


def plot(out_dir=fleet.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into
    fleet.DELIVERABLES.

    The real-name PNG always goes to fleet.DELIVERABLES, whatever out_dir is, so a test run into a scratch out_dir
    with private=True overwrites the deliverable; pass private=False for test runs."""
    out_dir = Path(out_dir)
    S = fleet.summary()
    cr = fleet.load('customer_rates')
    mf = fleet.load('machine_flags')
    match = fleet.load('match').set_index('measure').value
    top = checks(S, cr, mf, match)
    written = [draw(S, cr, top, out_dir / PNG)]
    if private:
        names = fleet.real_customer_names()
        if names is None:
            print('  real-name variant skipped: data/private/fx_private_customer_names.csv not found')
        else:
            style.check('fx_06 real names for every row', len(top), int(top.customer.isin(set(names)).sum()))
            written.append(draw(S, cr, top, fleet.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
