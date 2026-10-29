#!/usr/bin/env python3
"""Slide chart 6: the 15 customers with the most unplanned tickets, observed against expected from their fleets.

Slide version of viz/fleet_exposure/fx_06_busiest_customers.py. A customer with many tickets is not necessarily a
problem customer: it may simply have many machines, or models and ages that generate tickets at a high fleet rate.
One row per customer, busiest on top: a gray ring at expected tickets (what its machines would generate at fleet
rates for their model and age, the model + age fit), a filled dot at observed unplanned tickets on listed machines,
both counts at the outer ends. Dot colour, as in fx_06: blue = consistent outlier, light blue = flagged (Poisson rule)
but not consistent, gray = not flagged. The busiest, Customer 029 (114 against 102 expected), is in line with its
fleet; Customer 171, one ticket behind, has 113 against 59 expected.

Left out against the page chart: the machine counts in the row labels and the STR column (STR = observed / expected,
the ratio of the two numbers drawn on each row).

Two versions are drawn from the same data, both on the half card:
  pseudonymous (Customer NNN), always: plot(out_dir);
  named: each row labelled with its customer's name, at NAME_PT on one line or two (wrap_names()), the rest as in the
  pseudonymous chart. plot(out_dir, private=True) draws it with the real names, when the gitignored name table
  exists, to deliverables/slides/ (gitignored; the _REALNAMES file name marks it, nothing on the image does);
  plot_named(names_map, path) draws it with any names, e.g. names.twin() placeholders to check the layout without
  looking at real names. Its checks (named_checks()): each row label is its name, inside the image and clear of the
  other row labels and the x tick labels; the plot keeps at least MIN_PLOT_IN; the legend is clear of the counts,
  dots and lines; every text is inside the image.

Input:  verification/outputs/fleet/fx_customer_rates.csv  (one row per customer: tickets, expected, STR, flags)
        verification/outputs/fleet/fx_machine_flags.csv   (every machine with a ticket: independent check of tickets)
        verification/outputs/fleet/fx_summary.json        (flag thresholds, fleet totals, customer flag counts)
        data/private/fx_private_customer_names.csv        (customer -> real name; private=True only, via
                                                           viz/deliverables/names.py; gitignored)
Output: viz/figures/slides/sl_06_busiest_customers.png (half card)
        deliverables/slides/sl_06_busiest_customers_REALNAMES.png (private=True only; gitignored, never commit)

Run:  cd /home/user/analytics-lab && python3 -I viz/slides/sl_06_busiest_customers.py   (both versions)
"""
import json
import math
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'deliverables')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.text import Text  # noqa: E402

import deck_style as S  # noqa: E402
import names  # noqa: E402

PNG = 'sl_06_busiest_customers.png'
REAL_PNG = 'sl_06_busiest_customers_REALNAMES.png'
FLEET = S.OUT / 'fleet'
TOP_N = 15                # customers shown: the most unplanned tickets, as in fx_06
NAME_PT = 12              # named variant: row-label size (pseudonyms: TICK = 15 pt), so 15 rows of names fit the card
NAME_SPACING = 1.05       # ... line spacing of a two-line name (>= 1, so the measured boxes hold the ink, as checked)
LABEL_GAP = 2             # ... clear space (points) the checks require between a row label and its neighbours
MIN_PLOT_IN = 4.8         # ... the plot keeps at least this width (pseudonymous 6.9 in, twin names 5.4 in)
CLASSES = [  # (key, dot colour, legend label): fx_06's classes in the deck palette
    ('consistent', S.BLUE, 'Consistent outlier'),
    ('flagged', S.LIGHT, 'Flagged, not consistent'),
    ('not_flagged', S.GRAY, 'Not flagged'),
]
COLOUR = {key: colour for key, colour, _ in CLASSES}
# Numbers the card header and the speaker notes quote: customer -> (observed, expected as drawn).
QUOTED = {'Customer 029': (114, 102), 'Customer 171': (113, 59)}


def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), from log-space terms (fx_06's recomputation)."""
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


def class_of(row):
    if row.consistent_outlier:
        return 'consistent'
    return 'flagged' if row.poisson_flagged else 'not_flagged'


def checks(summ, cr, mf):
    """fx_06's consistency checks on the customer table; returns the TOP_N rows in drawing order."""
    d, F, C = summ['definitions'], summ['fleet'], summ['customers']
    S.check('sl_06 customers = population accounts', F['accounts'], len(cr))
    S.check('sl_06 customer tickets sum to the fleet', F['tickets'], int(cr.tickets.sum()))
    S.check('sl_06 expected sums to observed (fit property)', F['tickets'], float(cr.expected.sum()), 1e-6)
    by_cust = mf.groupby('customer').tickets.sum().reindex(cr.customer).fillna(0).to_numpy()
    S.check('sl_06 customer tickets = sum of its machines\' tickets', 0,
            int(np.abs(by_cust - cr.tickets.to_numpy()).max()))
    pos = cr.expected > 0
    S.check('sl_06 STR = tickets / expected', 0, float((cr.tickets[pos] / cr.expected[pos] - cr.STR[pos]).abs().max()),
            1e-9)

    # Flags recomputed: Poisson upper tail, BH over customers with expected > 0, >= min tickets.
    p = np.array([poisson_upper(o, e) for o, e in zip(cr.tickets[pos], cr.expected[pos])])
    S.check('sl_06 Poisson p recomputed', 0, float(np.abs(p - cr.p_poisson[pos].to_numpy()).max()), 1e-9)
    flag = np.zeros(len(cr), bool)
    flag[pos.to_numpy()] = (cr.tickets[pos].to_numpy() >= d['min_flag_tickets']) & (bh(p) < d['q_cut'])
    S.check('sl_06 flagged customers recomputed = poisson_flagged', 0, int((flag != cr.poisson_flagged.to_numpy()).sum()))
    S.check('sl_06 flagged customers = summary', C['poisson_flagged'], int(flag.sum()))
    # Consistent rule recomputed from the variant count and each half's Poisson p.
    p1 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h1, cr.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h2, cr.E_h2)])
    cons = (cr.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < 0.05) & (p2 < 0.05)
    S.check('sl_06 consistent outliers recomputed = consistent_outlier', 0,
            int((cons != cr.consistent_outlier.to_numpy()).sum()))
    S.check('sl_06 consistent outliers = summary', C['consistent_outliers'], int(cons.sum()))

    # The TOP_N: most tickets (ties broken by customer); no tie at the boundary.
    top = cr.sort_values(['tickets', 'customer'], ascending=[False, True], kind='mergesort').head(TOP_N)
    S.check('sl_06 top rows = CSV order', 1, int(top.customer.tolist() == cr.customer.head(TOP_N).tolist()))
    S.check('sl_06 no tie at the top-N boundary', 1,
            int(cr.tickets.nlargest(TOP_N).min() > cr.tickets.nlargest(TOP_N + 1).min()))
    S.check('sl_06 every row has expected > 0', 1, int((top.expected > 0).all()))
    S.check('sl_06 consistent outliers shown are flagged', 0, int((top.consistent_outlier & ~top.poisson_flagged).sum()))
    rows = top.index.to_numpy()
    S.check('sl_06 flagged among the top 15 (10) = recomputed', 10, int(flag[rows].sum()))
    S.check('sl_06 flagged among the top 15 = CSV', int(top.poisson_flagged.sum()), int(flag[rows].sum()))
    S.check('sl_06 consistent among the top 15 (6) = recomputed', 6, int(cons[rows].sum()))
    S.check('sl_06 consistent among the top 15 = CSV', int(top.consistent_outlier.sum()), int(cons[rows].sum()))
    # Each row against the machine table: tickets equal; expected at least the expected on machines with a ticket.
    mt = mf.groupby('customer').agg(o=('tickets', 'sum'), e=('expected', 'sum')).reindex(top.customer).fillna(0)
    S.check('sl_06 each drawn observed count = machine-table sum', 0,
            int(np.abs(mt.o.to_numpy() - top.tickets.to_numpy()).max()))
    S.check('sl_06 each expected >= expected on machines with a ticket', 0,
            int((top.expected.to_numpy() < mt.e.to_numpy() - 1e-9).sum()))
    # Each drawn expected count (no decimals) = tickets / STR, from another column.
    S.check('sl_06 each drawn expected count = tickets / STR (rounded)', 0,
            float(np.abs(np.round(top.expected) - np.round(top.tickets / top.STR)).max()))
    # The busiest is in line with its fleet: not flagged, and the 95% interval of its STR includes 1.
    b = top.iloc[0]
    S.check('sl_06 busiest is unique', 1, int(top.tickets.iloc[0] > top.tickets.iloc[1]))
    S.check('sl_06 busiest not flagged and its STR interval includes 1', 1,
            int((not b.poisson_flagged) and b.STR_lo <= 1 <= b.STR_hi))
    return top


def load():
    """The fleet summary and the TOP_N rows in drawing order, after fx_06's checks."""
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    cr = pd.read_csv(FLEET / 'fx_customer_rates.csv')
    mf = pd.read_csv(FLEET / 'fx_machine_flags.csv')
    return summ, checks(summ, cr, mf)


# ---------------------------------------------------------------------------------------------------------------
# Named variant: row labels and their layout checks
# ---------------------------------------------------------------------------------------------------------------
def two_lines(name):
    """name on at most two lines of about equal length: textwrap at the narrowest width that gives two (fx_10)."""
    for width in range(math.ceil(len(name) / 2), len(name) + 1):
        lines = textwrap.wrap(name, width, break_long_words=False, break_on_hyphens=False)
        if len(lines) <= 2:
            return lines
    return [name]


def wrap_names(full):
    """Row labels of the named variant, top row first: each name on one line when it has at most W characters, else
    on two (two_lines). W is the narrowest width (so the narrowest label column) that leaves no two neighbouring rows
    both on two lines and no line longer than W: at NAME_PT a two-line label fits between one-line neighbours, but
    two two-line labels do not fit in one row pitch."""
    for w in range(1, max(map(len, full)) + 1):
        lines = [[s] if len(s) <= w else two_lines(s) for s in full]
        two = [len(x) > 1 for x in lines]
        if not any(a and b for a, b in zip(two, two[1:])) and max(len(s) for x in lines for s in x) <= w:
            return ['\n'.join(x) for x in lines]
    return list(full)


def inside_image(box, fig):
    return box.x0 >= 0 and box.y0 >= 0 and box.x1 <= fig.bbox.width and box.y1 <= fig.bbox.height


def named_checks(fig, ax, top, full):
    """The named variant's layout, measured at the saved resolution; check names carry pseudonyms only. Each row
    label is its customer's name (lines joined by a space), inside the image and LABEL_GAP clear of the other row
    labels; no row label touches an x tick label; the label column leaves the plot at least MIN_PLOT_IN wide; the
    legend is clear of the counts, dots and lines it sits over; every text is inside the image."""
    fig.set_dpi(S.DPI)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    px = S.DPI / 72  # pixels per point
    S.check(f'sl_06 named: plot at least {MIN_PLOT_IN} in wide', 1, int(ax.bbox.width / S.DPI >= MIN_PLOT_IN))
    labels = ax.get_yticklabels()  # in set_yticklabels order: top row first
    boxes = [t.get_window_extent(r) for t in labels]
    S.check('sl_06 named: one row label per row', len(top), len(labels))
    for c, name, t, b in zip(top.customer, full, labels, boxes):
        same = t.get_text().replace('\n', ' ').split() == name.split()
        S.check(f'sl_06 named: {c} row label = its name', 1, int(same))
        S.check(f'sl_06 named: {c} row label inside the image', 1, int(inside_image(b, fig)))
    grown = [b.padded(LABEL_GAP * px / 2) for b in boxes]
    S.check('sl_06 named: row labels overlapping another row label', 0,
            sum(grown[i].overlaps(grown[j]) for i in range(len(grown)) for j in range(i + 1, len(grown))))
    xticks = [t.get_window_extent(r) for t in ax.get_xticklabels() if t.get_visible() and t.get_text()]
    S.check('sl_06 named: row labels touching an x tick label', 0, sum(b.overlaps(x) for b in boxes for x in xticks))

    # The legend sits over the empty lower right: no count, dot (centre within its radius) or dumbbell line under it.
    leg = ax.get_legend().get_window_extent(r)

    def under(x, y, pad=0.0):
        return leg.x0 - pad < x < leg.x1 + pad and leg.y0 - pad < y < leg.y1 + pad
    hits = sum(leg.overlaps(t.get_window_extent(r)) for t in ax.texts)
    for coll in ax.collections:
        xy = ax.transData.transform(coll.get_offsets())
        rad = (np.sqrt(coll.get_sizes()) / 2 + max(coll.get_linewidths(), default=0) / 2) * px
        hits += sum(under(x, y, pad) for (x, y), pad in zip(xy, np.broadcast_to(rad, len(xy))))
    for line in ax.lines:
        ends = ax.transData.transform(np.column_stack(line.get_data()))
        hits += int(any(under(x, y) for x, y in ends[0] + np.linspace(0, 1, 50)[:, None] * (ends[-1] - ends[0])))
    S.check('sl_06 named: counts, dots and lines under the legend', 0, hits)
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    S.check('sl_06 named: texts outside the image', 0,
            sum(not inside_image(t.get_window_extent(r), fig) for t in texts))


# ---------------------------------------------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------------------------------------------
def draw(summ, top, path, names_map=None):
    """Draw one version into path: row labels Customer NNN when names_map is None, else each customer's name from
    names_map (wrap_names(), at NAME_PT) followed by named_checks(). Returns path."""
    n = len(top)
    cls = [class_of(r) for r in top.itertuples()]

    # The numbers drawn, as text, against the CSV.
    obs_txt = [f'{o}' for o in top.tickets]
    exp_txt = [f'{e:.0f}' for e in top.expected]
    for c, o, e, ot, et in zip(top.customer, top.tickets, top.expected, obs_txt, exp_txt):
        S.check(f'sl_06 {c} observed as drawn', float(ot), o)
        S.check(f'sl_06 {c} expected as drawn', float(et), e, 0.5)
    drawn = dict(zip(top.customer, zip(obs_txt, exp_txt)))
    for c, (o, e) in QUOTED.items():
        S.check(f'sl_06 {c} observed (card header)', o, float(drawn[c][0]))
        S.check(f'sl_06 {c} expected (card header)', e, float(drawn[c][1]))

    fig, ax = S.figure(S.HALF)
    y = np.arange(n)[::-1]  # busiest on top
    for yi, o, e, k, ot, et in zip(y, top.tickets, top.expected, cls, obs_txt, exp_txt):
        ax.plot([e, o], [yi, yi], color=S.GRAY_LIGHT, lw=2.2, solid_capstyle='butt', zorder=1)
        ax.scatter([e], [yi], s=95, facecolor=S.WHITE, edgecolor=S.GRAY, linewidth=2, zorder=2)
        ax.scatter([o], [yi], s=110, color=COLOUR[k], linewidth=0, zorder=3)
        right = o >= e
        ax.annotate(ot, xy=(o, yi), xytext=(8 if right else -8, 0), textcoords='offset points', va='center',
                    ha='left' if right else 'right', fontsize=S.SMALL, color=S.INK,
                    weight='bold' if k == 'consistent' else 'normal')
        ax.annotate(et, xy=(e, yi), xytext=(-8 if right else 8, 0), textcoords='offset points', va='center',
                    ha='right' if right else 'left', fontsize=S.SMALL, color=S.INK2)

    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0, 130)
    ax.set_xticks([0, 25, 50, 75, 100, 125])
    ax.set_yticks(y)
    if names_map is None:
        ax.set_yticklabels(top.customer, color=S.INK, fontsize=S.TICK)
    else:
        full = [names.substitute(c, names_map)[0] for c in top.customer]  # KeyError names only the pseudonym
        # Centred on the row (va='center'): the default centre-baseline would hang a second line below the row.
        ax.set_yticklabels(wrap_names(full), color=S.INK, fontsize=NAME_PT, linespacing=NAME_SPACING, va='center')
    S.style_axes(ax, grid='x', baseline='left')
    period = ' to '.join(pd.Timestamp(x).strftime('%b %Y') for x in summ['definitions']['period'])
    S.check('sl_06 period drawn = Aug 2025 to Aug 2026', 1, int(period == 'Aug 2025 to Aug 2026'))
    ax.set_xlabel(f'Unplanned tickets, {period}')
    present = set(cls)
    handles = [Line2D([], [], marker='o', ls='', markersize=10, markerfacecolor=col, markeredgewidth=0, label=lab)
               for key, col, lab in CLASSES if key in present]
    handles.append(Line2D([], [], marker='o', ls='', markersize=9, markerfacecolor=S.WHITE, markeredgecolor=S.GRAY,
                          markeredgewidth=2, label='Expected from its fleet'))
    # The bottom rows have the fewest tickets, so the lower right of the plot is empty.
    ax.legend(handles=handles, loc='lower right', handlelength=1.0, handletextpad=0.5, borderaxespad=0.2, labelspacing=0.35,
              frameon=True, facecolor=S.WHITE, edgecolor='none', framealpha=1)
    if names_map is not None:
        named_checks(fig, ax, top, full)
    return S.save(fig, Path(path))


def plot(out_dir=S.FIG_DIR, private=False):
    """Draw the pseudonymous chart into out_dir and, when private and the gitignored name table exists, the real-name
    variant into deliverables/slides/ (gitignored), whatever out_dir is. Returns every path written."""
    summ, top = load()
    written = [draw(summ, top, Path(out_dir) / PNG)]
    if private:
        real = names.real_names()
        if real is None:
            print('  real-name variant skipped: data/private/fx_private_customer_names.csv not found')
        else:
            written.append(plot_named(real, names.DELIVERABLES / 'slides' / REAL_PNG))
    return written


def plot_named(names_map, path):
    """Draw the named variant into path with names_map ({'Customer NNN': name}: the real names, or names.twin()
    placeholders for a layout check), with the same number checks as the pseudonymous chart. Returns path."""
    summ, top = load()
    return draw(summ, top, Path(path), names_map)


if __name__ == '__main__':
    plot(private=True)
