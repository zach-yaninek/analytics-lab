#!/usr/bin/env python3
"""Fleet chart 12: what drives each consistent-outlier customer's excess tickets.

A customer can be a consistent outlier because one or two of its machines generate many more tickets than their
model and age predict, because its whole fleet runs a little high, or simply because it has so few machines that a
couple of bad ones decide its ratio. Which of these it is decides the follow-up (fix a machine, or talk to the site).
This chart splits each consistent outlier's excess unplanned tickets (observed - expected, the model + age fit of
verification/fleet_exposure.py) into the excess on its two machines with the most excess (blue) and the excess on the
rest of its machines (gray). One row per consistent outlier, largest excess on top, labelled
'Customer NNN (n machines)', with the net excess and the top-2 share at the bar end and, in two columns at the right,
the pattern assigned by the analysis (small fleet / a few machines / spread across fleet) and the customer's most
frequent recorded category with its share of the customer's unplanned tickets. When the rest of a customer's machines
are together below expected, the top-2 excess is larger than the customer's net excess: the blue bar then shows the
top-2 excess and an ink tick marks the net. The title counts the small fleets among the consistent outliers and,
among the larger ones, those whose excess is spread across their own fleet (the analysis' rule: the top 2 machines
hold under half of it). The figure height is set from the rows plus the title and footer bands as frame() reserves
them, so the bars are about 22 px thick whatever the footer holds.

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and data/private/fx_private_customer_names.csv exists. It is written to
  deliverables/ (gitignored) and must never be committed; its privacy warning is the first line of the subtitle.

Inputs (computed by verification/fleet_exposure.py; nothing is refitted here):
  verification/outputs/fleet/fx_outlier_drivers.csv  one row per consistent-outlier or beyond-funnel customer:
                                                     machines, tickets, expected, excess, top2_machines_excess,
                                                     top2_share_of_excess, pattern, top_category,
                                                     top_category_share (the plotted series)
  verification/outputs/fleet/fx_customer_rates.csv   one row per customer: tickets, expected, machines,
                                                     consistent_outlier (independent check of the rows)
  verification/outputs/fleet/fx_machine_flags.csv    every machine with a ticket: tickets, expected (independent
                                                     recomputation of the top-2 excess and of the patterns)
  verification/outputs/fleet/fx_summary.json         period, consistent-outlier count, definitions
  data/private/fx_private_customer_names.csv         customer -> real_account_name (real-name version only;
                                                     gitignored; via fleet.real_customer_names())
Outputs:
  viz/figures/fx_12_outlier_drivers.png
  deliverables/fx_12_outlier_drivers_REALNAMES.png   (private=True only)

Run:  cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_12_outlier_drivers.py
"""
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_12_outlier_drivers.png'
REAL_PNG = 'fx_12_outlier_drivers_REALNAMES.png'
# The analysis' pattern labels (verification/fleet_exposure.py, 'Drivers of outlier customers').
SMALL, FEW, SPREAD = 'small fleet', 'a few machines', 'spread across fleet'
FEW_SHARE = 0.5           # the analysis' rule: 'a few machines' = top-2 machines hold at least this share of the
                          # excess (checked below: the rule reproduces every pattern in the CSV)
ROW_IN = 0.34             # inches per customer row
AXIS_IN = 0.75            # plot band besides the rows: x tick labels, x label, column heads, layout pads (inches)
Y_LO, Y_HI = -0.6, -0.4   # y limits = (Y_LO, n + Y_HI): the plot spans n + Y_HI - Y_LO rows
BAR_H = 0.43              # bar thickness as a share of the row pitch (0.43 x 0.34 in = about 22 px at 150 dpi)
TITLE_IN_PER_CHAR = 0.118  # approximate width of one title character (15 pt bold), for the figure width
LABEL_IN_PER_CHAR = 0.075  # approximate width of one tick-label character (10 pt), for the real-name width
COL_PT_PER_CHAR = 5.6     # approximate width of one column character (9.5 pt), for the column offsets
COL_GAP_PT = 16           # gap between the plot area and the first column, and between the columns
FONT = 9.5
XPAD = 1.3                # x range = largest bar x this, leaving room for the bar-end labels
PRIVACY_WARNING = ('Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                   '(gitignored); never commit.')


def small_threshold(patterns):
    """The machine count in the analysis' small-fleet label, e.g. 'small fleet (<10 machines)' -> 10."""
    labels = {p for p in patterns if p.startswith(SMALL)}
    if len(labels) != 1:
        raise ValueError(f'expected one small-fleet label, got {sorted(labels)}')
    return int(re.search(r'<\s*(\d+)', labels.pop()).group(1))


def pattern_rule(machines, share, small_n):
    """The analysis' pattern rule, written here from its definition so the CSV labels are tested, not copied."""
    if machines < small_n:
        return 'small'
    return 'few' if share >= FEW_SHARE else 'spread'


def pattern_key(label):
    return 'small' if label.startswith(SMALL) else {FEW: 'few', SPREAD: 'spread'}[label]


def bands(width, subtitle, definitions, notes):
    """(top band, bottom band) in inches, as style.frame() reserves them (same wrapping and line heights), so the
    figure height can be set from the rows (as in fx_10)."""
    usable = width - 2 * style.MARGIN

    def n_lines(items, per_in):
        items = [items] if isinstance(items, str) else list(items)
        return sum(len(textwrap.wrap(t, int(usable * per_in), break_on_hyphens=False)) for t in items)

    top = (0.25 + style.TITLE_PT / 72 * 1.25 + 0.08
           + n_lines(subtitle, style.SUB_CHARS_PER_IN) * style.SUB_PT / 72 * 1.35 + 0.2)
    note_lh = style.NOTE_PT / 72 * 1.4
    bottom = 0.16 + (n_lines(notes, style.NOTE_CHARS_PER_IN) * note_lh + 0.06 if notes else 0)
    bottom += sum(n_lines(t, style.NOTE_CHARS_PER_IN) * note_lh + 0.04 for t in definitions) + 0.16
    return top, bottom


def checks(S, dr, cr, mf):
    """Consistency checks against the customer and machine tables; returns the rows in drawing order and the
    independent recomputations used to check the drawn numbers."""
    n_cons = S['customers']['consistent_outliers']
    c = dr[dr.consistent_outlier].copy()
    style.check('fx_12 consistent outliers in drivers = summary', n_cons, len(c))
    style.check('fx_12 consistent outliers in customer table = summary', n_cons, int(cr.consistent_outlier.sum()))
    style.check('fx_12 subtitle: customers on the list = customer table rows', S['fleet']['accounts'], len(cr))
    style.check('fx_12 drivers rows = consistent outliers of the customer table', 1,
                int(set(c.customer) == set(cr.customer[cr.consistent_outlier])))

    # Customer totals from the customer table.
    ci = cr.set_index('customer').loc[c.customer]
    style.check('fx_12 tickets = customer table', 0, int(np.abs(ci.tickets.to_numpy() - c.tickets.to_numpy()).max()))
    style.check('fx_12 expected = customer table', 0,
                float(np.abs(ci.expected.to_numpy() - c.expected.to_numpy()).max()), 1e-6)
    style.check('fx_12 machines = customer table', 0, int(np.abs(ci.machines.to_numpy() - c.machines.to_numpy()).max()))
    excess = ci.tickets.to_numpy() - ci.expected.to_numpy()
    style.check('fx_12 excess = tickets - expected (customer table)', 0,
                float(np.abs(excess - c.excess.to_numpy()).max()), 1e-6)

    # Machine table: tickets per customer, and the two machines with the most excess.
    mf = mf.assign(excess=mf.tickets - mf.expected)
    by_cust = mf.groupby('customer').tickets.sum().reindex(c.customer).fillna(0).to_numpy()
    style.check('fx_12 tickets = sum of the machines\' tickets', 0, int(np.abs(by_cust - c.tickets.to_numpy()).max()))
    top2, second = [], []
    for cust in c.customer:
        ex = np.sort(mf.excess[mf.customer == cust].to_numpy())[::-1]
        top2.append(float(ex[:2].sum()))
        second.append(float(ex[1]) if len(ex) > 1 else -np.inf)
    top2 = np.array(top2)
    # Machines without a ticket (not in the machine table) have negative excess, so the top 2 of the machines with
    # a ticket are the customer's top 2 whenever both have positive excess.
    style.check('fx_12 the top-2 machines all have positive excess', 1, int((np.array(second) > 0).all()))
    style.check('fx_12 top-2 excess recomputed from the machine table', 0,
                float(np.abs(top2 - c.top2_machines_excess.to_numpy()).max()), 1e-6)
    share = top2 / excess
    style.check('fx_12 top-2 share = top-2 excess / excess', 0,
                float(np.abs(share - c.top2_share_of_excess.to_numpy()).max()), 1e-9)
    style.check('fx_12 every excess is positive', 1, int((excess > 0).all()))

    # Patterns: the analysis' rule, recomputed from the customer and machine tables, gives every label in the CSV.
    small_n = small_threshold(dr.pattern)
    rule = [pattern_rule(m, s, small_n) for m, s in zip(ci.machines, share)]
    style.check('fx_12 pattern rule reproduces every CSV pattern', 0,
                sum(r != pattern_key(p) for r, p in zip(rule, c.pattern)))

    # Top category: its share of the customer's tickets is a whole number of tickets.
    count = c.top_category_share.to_numpy() * c.tickets.to_numpy()
    style.check('fx_12 top-category share x tickets is a ticket count', 0,
                float(np.abs(count - np.round(count)).max()), 1e-6)
    style.check('fx_12 every row has a top category', 1, int(c.top_category.notna().all()))

    c['excess_chk'] = excess
    c['top2_chk'] = top2
    c['share_chk'] = share
    c['rule'] = rule
    c['cat_count'] = np.round(count).astype(int)
    c = c.sort_values(['excess', 'customer'], ascending=[False, True], kind='mergesort')
    return c, small_n


def draw(S, c, small_n, path, names=None):
    """Draw one version of the chart (pseudonymous when names is None)."""
    F = S['fleet']
    n = len(c)
    name = (lambda x: x) if names is None else (lambda x: names.get(x, x))
    keys = [pattern_key(p) for p in c.pattern]
    n_small = keys.count('small')
    n_large = n - n_small
    n_spread = keys.count('spread')
    # Title counts recomputed from the customer and machine tables (the 'rule' column).
    style.check('fx_12 title: small fleets (recomputed)', sum(r == 'small' for r in c.rule), n_small)
    style.check('fx_12 title: larger fleets (recomputed)', sum(r != 'small' for r in c.rule), n_large)
    style.check('fx_12 title: spread across fleet (recomputed)', sum(r == 'spread' for r in c.rule), n_spread)
    style.check('fx_12 title: consistent outliers', S['customers']['consistent_outliers'], n)
    title = (f'{n_small} of {n} consistent outliers have under {small_n} machines; '
             f'{n_spread} of the other {n_large} have their excess spread across their fleets')

    # Subtitle totals, recomputed from the customer and machine tables.
    tot_t, tot_e = int(c.tickets.sum()), float(c.expected.sum())
    tot_x, tot_2 = float(c.excess.sum()), float(c.top2_machines_excess.sum())
    style.check('fx_12 subtitle: tickets (customer table)', tot_t, int(sum(int(t) for t in c.tickets)))
    style.check('fx_12 subtitle: excess (customer table)', round(float(c.excess_chk.sum()), 1), round(tot_x, 1))
    style.check('fx_12 subtitle: expected = tickets - excess', round(tot_t - float(c.excess_chk.sum()), 1),
                round(tot_e, 1))
    style.check('fx_12 subtitle: top-2 share of the excess (machine table)',
                round(100 * float(c.top2_chk.sum()) / float(c.excess_chk.sum()), 1), round(100 * tot_2 / tot_x, 1))
    subtitle = [f'Excess unplanned tickets (observed − expected) of each of the {n} consistent-outlier customers '
                f'among the {F["accounts"]:,} with machines on IPA\'s installed-base list, {fleet.period_text(S)}, '
                f'largest first: blue on the customer\'s two machines with the most excess, gray on the rest of its '
                f'machines. At the right: the analysis\' pattern and the customer\'s top category.',
                f'Together: {tot_t:,} unplanned tickets against {tot_e:.1f} expected; {style.pct(tot_2 / tot_x)} of '
                f'the {tot_x:.1f} excess tickets are on their top-2 machines.']
    if names is not None:
        subtitle.insert(0, PRIVACY_WARNING)  # first line, so the warning is read before the chart
    notes = [f'Excess per machine = its tickets − its expected tickets, so a customer\'s machines add up to its '
             f'excess; where the rest of its machines are together below expected, the top 2 hold more than 100% of '
             f'it. Pattern (the analysis\' rule): small fleet = under {small_n} machines in place during the period; '
             f'otherwise a few machines = the top 2 hold at least {FEW_SHARE:.0%} of the excess, else spread across '
             f'fleet.',
             'Top category = most frequent recorded category among the customer\'s unplanned tickets. Expected '
             'tickets allow for model and age only, not coverage, use or reporting.',
             fleet.source('outlier_drivers', 'customer_rates', 'machine_flags')[:-1]
             + ('; names from data/private/fx_private_customer_names.csv (gitignored).' if names is not None
                else '.')]
    definitions = [fleet.unplanned_definition(), fleet.expected_definition(S), fleet.consistent_definition(S)]

    labels = [f'{name(x)} ({m:,} machines)' for x, m in zip(c.customer, c.machines)]
    pseudo_w = LABEL_IN_PER_CHAR * max(len(f'{x} ({m:,} machines)') for x, m in zip(c.customer, c.machines))
    label_w = LABEL_IN_PER_CHAR * max(len(s) for s in labels)
    width = max(12.5, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN) + max(0.0, label_w - pseudo_w)
    top_band, bottom_band = bands(width, subtitle, definitions, notes)
    fig, ax = style.figure(width, top_band + bottom_band + AXIS_IN + ROW_IN * (n + Y_HI - Y_LO))

    y = np.arange(n)[::-1]  # largest excess on top
    exc = c.excess.to_numpy()
    top2 = c.top2_machines_excess.to_numpy()
    rest = exc - top2
    ends = np.maximum(exc, top2)
    ax.barh(y, top2, height=BAR_H, color=style.BLUE, linewidth=0, zorder=2)
    pos = rest > 0
    ax.barh(y[pos], rest[pos], left=top2[pos], height=BAR_H, color=style.GRAY_LIGHT, linewidth=0, zorder=2)
    neg = ~pos
    for yi, e in zip(y[neg], exc[neg]):  # net excess inside the blue bar when the rest is below expected
        ax.plot([e, e], [yi - BAR_H * 0.8, yi + BAR_H * 0.8], color=style.INK, lw=1.6, solid_capstyle='butt',
                zorder=3)

    # Bar-end labels: net excess and the top-2 share (and the rest, when it is below expected).
    for yi, end, e, s, r in zip(y, ends, exc, c.top2_share_of_excess, rest):
        text = f'{e:.1f}   top 2: {s:.0%}' + (f', rest {r:.1f}'.replace('-', '−') if r < 0 else '')
        ax.annotate(text, xy=(end, yi), xytext=(6, 0), textcoords='offset points', va='center', ha='left',
                    fontsize=FONT, color=style.INK2)
    style.check('fx_12 drawn excess (1 decimal) = customer tickets - expected', 0,
                float(np.abs(np.round(exc, 1) - np.round(c.excess_chk.to_numpy(), 1)).max()))
    style.check('fx_12 drawn top-2 share (whole %) = recomputed', 0,
                float(np.abs(np.round(100 * c.top2_share_of_excess.to_numpy()) -
                             np.round(100 * c.share_chk.to_numpy())).max()))
    rest_chk = c.excess_chk.to_numpy() - c.top2_chk.to_numpy()
    style.check('fx_12 drawn negative rests (1 decimal) = recomputed', 0,
                float(np.abs(np.round(rest[neg], 1) - np.round(rest_chk[neg], 1)).max()) if neg.any() else 0.0)
    style.check('fx_12 rows with a negative rest (recomputed)', int((rest_chk < 0).sum()), int(neg.sum()))

    # Two text columns at the right of the plot area (axes x, data y): pattern, and top category with its share.
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    pat_text = [p[0].upper() + p[1:] for p in c.pattern]
    # A top category tied with others is the alphabetically first of them (fleet_exposure.py); say so.
    cat_text = [f'{t} ({s:.0%}{f", tied with {k - 1} more" if k > 1 else ""})'
                for t, s, k in zip(c.top_category, c.top_category_share, c.top_category_ties)]
    style.check('fx_12 drawn top-category shares (whole %) = count / tickets', 0,
                float(np.abs(np.round(100 * c.top_category_share.to_numpy()) -
                             np.round(100 * c.cat_count.to_numpy() / c.tickets.to_numpy())).max()))
    heads = ('Pattern', 'Top category (share of tickets)')
    col1 = COL_GAP_PT
    col2 = col1 + COL_PT_PER_CHAR * max(len(s) for s in [*pat_text, heads[0]]) + COL_GAP_PT
    for x_pt, head in zip((col1, col2), heads):
        ax.annotate(head, xy=(1, n - 0.45), xycoords=tr, xytext=(x_pt, 0), textcoords='offset points',
                    ha='left', va='bottom', fontsize=FONT, color=style.INK2, weight='bold')
    for yi, p, t in zip(y, pat_text, cat_text):
        for x_pt, text in zip((col1, col2), (p, t)):
            ax.annotate(text, xy=(1, yi), xycoords=tr, xytext=(x_pt, 0), textcoords='offset points',
                        ha='left', va='center', fontsize=FONT, color=style.INK2)

    ax.set_ylim(Y_LO, n + Y_HI)
    ax.set_xlim(0, float(ends.max()) * XPAD)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.tick_params(axis='y', length=0)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel(f'Excess unplanned tickets (observed − expected), {fleet.period_text(S)}')
    handles = [Patch(color=style.BLUE, linewidth=0, label='Excess on its 2 machines with the most excess'),
               Patch(color=style.GRAY_LIGHT, linewidth=0, label='Excess on the rest of its machines')]
    if neg.any():
        handles.append(Line2D([], [], color=style.INK, lw=1.6, marker='|', markersize=9, markeredgewidth=1.6,
                              ls='', label='Net excess, where the rest is below expected'))
    # The bottom rows have the least excess, so the lower right of the plot is empty.
    ax.legend(handles=handles, loc='lower right', frameon=True, facecolor=style.SURFACE, edgecolor='none',
              framealpha=1, handlelength=1.4)

    style.frame(fig, title, subtitle, notes=notes, definitions=definitions)
    return style.save(fig, path)


def plot(out_dir=fleet.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into
    fleet.DELIVERABLES.

    The real-name PNG always goes to fleet.DELIVERABLES, whatever out_dir is, so a test run into a scratch out_dir
    with private=True overwrites the deliverable; pass private=False for test runs."""
    out_dir = Path(out_dir)
    S = fleet.summary()
    dr = fleet.load('outlier_drivers')
    cr = fleet.load('customer_rates')
    mf = fleet.load('machine_flags')
    c, small_n = checks(S, dr, cr, mf)
    written = [draw(S, c, small_n, out_dir / PNG)]
    if private:
        names = fleet.real_customer_names()
        if names is None:
            print('  real-name variant skipped: data/private/fx_private_customer_names.csv not found')
        else:
            style.check('fx_12 real names for every row', len(c), int(c.customer.isin(set(names)).sum()))
            written.append(draw(S, c, small_n, fleet.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
