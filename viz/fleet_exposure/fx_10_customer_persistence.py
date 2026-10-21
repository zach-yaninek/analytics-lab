#!/usr/bin/env python3
"""Fleet chart 10: do customers that run high stay high? Each customer's STR in the first half against the second.

Why: a customer that generates more tickets than its fleet explains in one half of the period could be unlucky, or
it could be a lasting problem (site, users, reporting). If the excess is real it should carry over: customers high
in the first half should tend to be high again in the second. This chart plots, for every customer with at least
MIN_E_HALF expected tickets in each half (the population of the analysis' persistence statistics, F7 of
verification/fleet_exposure.py), its standardised ticket ratio (STR = observed / expected) in the first half (x)
against the second half (y). Both axes are logarithmic, because these are ratios (0.5 and 2 sit the same distance
from 1), with the same range on each; the lines at 1 mark "in line with the fleet" in each half and split the plot
into four quadrants, each labelled with its customer count. A customer with no tickets in a half has STR 0, which a
log axis cannot show: those are drawn at a floor value in a shaded strip at the left (first half) or bottom (second
half), the tick there reads 0, and the customers with none in either half, which all sit on one point, are
counted in a label.

Dots: light gray = other customers; dark gray = above their expected tickets beyond chance (one-sided Poisson
p < 0.05) in both halves but not consistent outliers; blue = consistent outliers, each labelled. Labels are placed
by a small search (place_labels()) around each dot, clear of the other labels, the coloured dots, the legend and the
quadrant labels, with a leader line when a label sits away from its dot. The search's hard rules make every label
read as its own dot's: a label without a leader is clearly nearer its own dot than any other coloured dot, each
labelled dot's nearest label is its own, and leaders neither cross nor pass over another dot or label. Checks
confirm that no dot is hidden under the legend or the quadrant labels.

The title states the split-half rank correlation (Spearman) against the median of the analysis' permutation null
(second-half results shuffled among customers in the same tenth of second-half expected tickets, so differences
between customers are kept but persistence is not); the subtitle adds the null's 97.5th percentile and how many of
the customers above 1 in the first half are above 1 again. A footer note compares the customers above their
expected tickets beyond chance in both halves with the permutation-null median.

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and data/private/fx_private_customer_names.csv exists. It is written to
  deliverables/ (gitignored) and must never be committed; its privacy warning is the first line of the subtitle.

Inputs (computed by verification/fleet_exposure.py; nothing is refitted here, the numbers are only re-derived for
the checks):
  verification/outputs/fleet/fx_outlier_customers.csv    one row per customer with expected tickets >= 1 (plus the
                                                         flagged and low ones): customer, machines, O_h1, E_h1,
                                                         STR_h1, p_h1, O_h2, E_h2, STR_h2, p_h2, variants_flagged,
                                                         consistent_outlier
  verification/outputs/fleet/fx_outlier_persistence.csv  persistence statistics against their nulls: rows
                                                         spearman_STR_h1_h2 and significant_in_both_halves (units,
                                                         observed, perm_null_median, perm_null_p2_5,
                                                         perm_null_p97_5)
  verification/outputs/fleet/fx_summary.json             period, split, n_null, min_variants, consistent-outlier
                                                         count and the same persistence statistics (for checks)
  data/private/fx_private_customer_names.csv             customer -> real_account_name (real-name version only;
                                                         gitignored; via fleet.real_customer_names())
Outputs:
  viz/figures/fx_10_customer_persistence.png
  deliverables/fx_10_customer_persistence_REALNAMES.png   (private=True only)

Run:  cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_10_customer_persistence.py
"""
import math
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_10_customer_persistence.png'
REAL_PNG = 'fx_10_customer_persistence_REALNAMES.png'
NAMES_FILE = 'data/private/fx_private_customer_names.csv'
MIN_E_HALF = 3            # customers with at least this many expected tickets in each half (as the analysis, F7)
SPEARMAN, SIG_BOTH = 'spearman_STR_h1_h2', 'significant_in_both_halves'   # fx_outlier_persistence.csv rows
P_CUT = 0.05              # "above expected beyond chance" in a half: one-sided Poisson p below this (F7)
ZERO_GAP = 2.4            # zero-ticket customers are drawn at the smallest positive STR divided by this
EDGE = 1.35               # axis ends: this factor beyond the floor value and beyond the largest STR ...
HEADROOM = 1.6            # ... and this factor above the largest STR (room for the quadrant labels)
TICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10]
PLOT_H = 8.6              # inches between the title band and the footer (axes, tick labels, axis label)
TITLE_IN_PER_CHAR = 0.124  # approximate width of one title character (15 pt bold), for the figure width
AX_W_LESS, AX_H_LESS = 1.22, 0.56  # figure width / plot height less the axes size (margins, tick and axis labels)
LABEL_PT = 8.5            # point-label font size
LABEL_IN_PER_CHAR = 0.066  # approximate width of one character at LABEL_PT (DejaVu Sans), for label boxes
NAME_WRAP = 24            # real names longer than this wrap onto two lines
DOT_GRAY, DOT_COLOUR = 16, 34  # marker areas (pt^2)
PRIVACY_WARNING = ('Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                   '(gitignored); never commit.')


# ---------------------------------------------------------------------------------------------------------------
# Independent recomputations for the checks: Poisson tail and Spearman, written here from the definitions in
# verification/fleet_exposure.py, so the columns of the CSVs are tested, not copied.
# ---------------------------------------------------------------------------------------------------------------
def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed in log space."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    term = lambda j: math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1))  # noqa: E731
    if k <= mu:
        return max(0.0, 1.0 - sum(term(j) for j in range(k)))
    total, j = 0.0, k
    while True:
        t = term(j)
        total += t
        if t < total * 1e-17 or j > k + 20_000:
            return total
        j += 1


def rank_correlation(a, b):
    """Spearman: Pearson correlation of the ranks, ties given their average rank."""
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    ra, rb = ra - ra.mean(), rb - rb.mean()
    return float((ra * rb).sum() / math.sqrt((ra * ra).sum() * (rb * rb).sum()))


def checks(S, oc, pe):
    """Consistency checks; returns the plotted customers (with recomputed STRs and classes) and the numbers drawn."""
    d, P = S['definitions'], S['persistence']
    style.check('fx_10 consistent outliers in the table = summary', S['customers']['consistent_outliers'],
                int(oc.consistent_outlier.sum()))
    # Consistent rule recomputed over the whole table: flagged in >= min_variants variants, p < 0.05 in each half.
    p1 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(oc.O_h1, oc.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(oc.O_h2, oc.E_h2)])
    cons = (oc.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < P_CUT) & (p2 < P_CUT)
    style.check('fx_10 consistent outliers recomputed = consistent_outlier', 0,
                int((cons != oc.consistent_outlier.to_numpy()).sum()))

    keep = ((oc.E_h1 >= MIN_E_HALF) & (oc.E_h2 >= MIN_E_HALF)).to_numpy()
    c = oc[keep].copy()
    c['p1'], c['p2'], c['cons'] = p1[keep], p2[keep], cons[keep]
    rows = pe[pe.level == 'customer'].set_index('statistic')
    sp, sb = rows.loc[SPEARMAN], rows.loc[SIG_BOTH]
    style.check('fx_10 customers plotted = units of the persistence statistics', int(sp.units), len(c))
    style.check('fx_10 customers plotted = summary units', P[SPEARMAN]['units'], len(c))
    style.check('fx_10 p first half recomputed = p_h1', 0, float(np.abs(c.p1 - c.p_h1).max()), 1e-9)
    style.check('fx_10 p second half recomputed = p_h2', 0, float(np.abs(c.p2 - c.p_h2).max()), 1e-9)

    # STR per half recomputed from tickets and expected tickets; these are what is plotted.
    c['x'], c['y'] = c.O_h1 / c.E_h1, c.O_h2 / c.E_h2
    style.check('fx_10 STR first half = O_h1 / E_h1', 0, float((c.x - c.STR_h1).abs().max()), 1e-9)
    style.check('fx_10 STR second half = O_h2 / E_h2', 0, float((c.y - c.STR_h2).abs().max()), 1e-9)
    rho = rank_correlation(c.x, c.y)
    style.check('fx_10 rank correlation recomputed = persistence CSV', float(sp.observed), rho, 1e-9)
    style.check('fx_10 rank correlation = summary', P[SPEARMAN]['observed'], rho, 5e-5)
    for col in ('perm_null_median', 'perm_null_p97_5'):
        style.check(f'fx_10 rank correlation {col}: CSV = summary', P[SPEARMAN][col], float(sp[col]), 5e-5)
    sig = (c.p1 < P_CUT) & (c.p2 < P_CUT)
    style.check('fx_10 above expected beyond chance in both halves recomputed = persistence CSV', float(sb.observed),
                int(sig.sum()))
    style.check('fx_10 above expected beyond chance in both halves = summary', P[SIG_BOTH]['observed'], int(sig.sum()))
    for col in ('perm_null_median', 'perm_null_p2_5', 'perm_null_p97_5'):
        style.check(f'fx_10 both-halves {col}: CSV = summary', P[SIG_BOTH][col], float(sb[col]), 5e-5)
    style.check('fx_10 consistent outliers plotted are above expected beyond chance in both halves', 0,
                int((c.cons & ~sig).sum()))

    # Quadrants (lines at 1) and the zero-ticket strips.
    style.check('fx_10 no STR exactly 1 (quadrants are strict)', 0, int(((c.x == 1) | (c.y == 1)).sum()))
    a1, a2 = c.x > 1, c.y > 1
    q = {'both': int((a1 & a2).sum()), 'first': int((a1 & ~a2).sum()), 'second': int((~a1 & a2).sum()),
         'neither': int((~a1 & ~a2).sum())}
    style.check('fx_10 quadrants add up to the customers plotted', len(c), sum(q.values()))
    style.check('fx_10 above 1 in the first half (tickets > expected)', int(a1.sum()), int((c.O_h1 > c.E_h1).sum()))
    style.check('fx_10 above 1 in the second half (tickets > expected)', int(a2.sum()), int((c.O_h2 > c.E_h2).sum()))
    z1, z2 = c.O_h1 == 0, c.O_h2 == 0
    style.check('fx_10 STR 0 in the first half = no tickets', int(z1.sum()), int((c.STR_h1 == 0).sum()))
    style.check('fx_10 STR 0 in the second half = no tickets', int(z2.sum()), int((c.STR_h2 == 0).sum()))
    c['cls'] = np.where(c.cons, 'consistent', np.where(sig, 'both', 'other'))
    # The same counts straight from the CSV's own columns (STR, p, consistent_outlier), for the drawn quadrant and
    # legend counts, which use the recomputed values above.
    raw = oc[keep]
    r1, r2 = raw.STR_h1 > 1, raw.STR_h2 > 1
    for key, sel in (('both', r1 & r2), ('first', r1 & ~r2), ('second', ~r1 & r2), ('neither', ~r1 & ~r2)):
        style.check(f'fx_10 quadrant {key} from the CSV STR columns', q[key], int(sel.sum()))
    raw_sig = (raw.p_h1 < P_CUT) & (raw.p_h2 < P_CUT)
    legend = {'consistent': int(raw.consistent_outlier.sum()),
              'both': int((raw_sig & ~raw.consistent_outlier).sum()),
              'other': int((~raw_sig & ~raw.consistent_outlier).sum())}
    style.check('fx_10 legend classes cover every customer plotted', len(c), sum(legend.values()))
    return c, {'legend': legend, 'rho': rho, 'null_med': float(sp.perm_null_median),
               'null_hi': float(sp.perm_null_p97_5), 'sig': int(sig.sum()), 'sig_med': float(sb.perm_null_median),
               'sig_lo': float(sb.perm_null_p2_5), 'sig_hi': float(sb.perm_null_p97_5), 'q': q,
               'above1': int(a1.sum()), 'above2': int(a2.sum()), 'zero1': int(z1.sum()), 'zero2': int(z2.sum()),
               'zero_both': int((z1 & z2).sum()), 'cons_all': int(cons.sum()), 'cons_shown': int(c.cons.sum())}


# ---------------------------------------------------------------------------------------------------------------
# Layout helpers: page bands (the same arithmetic as style.frame) and label placement in inches
# ---------------------------------------------------------------------------------------------------------------
def bands(width, subtitle, definitions, notes):
    """(top band, bottom band) in inches, as style.frame() reserves them, so the figure height can be set from the
    plot height."""
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


def text_box(x, y, w, h, ha, va):
    """(x0, y0, x1, y1) of a w x h text box anchored at (x, y) with the given alignment."""
    x0 = {'left': x, 'center': x - w / 2, 'right': x - w}[ha]
    y0 = {'bottom': y, 'center': y - h / 2, 'top': y - h}[va]
    return (x0, y0, x0 + w, y0 + h)


def overlaps(a, b, pad=0.0):
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3]


def inside(box, pts, pad=0.0):
    """Boolean mask: which of the (n, 2) points lie in box grown by pad."""
    return ((pts[:, 0] > box[0] - pad) & (pts[:, 0] < box[2] + pad) &
            (pts[:, 1] > box[1] - pad) & (pts[:, 1] < box[3] + pad))


def box_distance(box, p):
    """Distance from point p to the box (0 inside)."""
    return math.hypot(max(box[0] - p[0], 0.0, p[0] - box[2]), max(box[1] - p[1], 0.0, p[1] - box[3]))


def segment(p, q, n=30):
    t = np.linspace(0, 1, n)[:, None]
    return np.asarray(p) + t * (np.asarray(q) - np.asarray(p))


def segments_cross(a, b, c, d):
    """Whether segment a-b properly crosses segment c-d."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (orient(a, b, c) * orient(a, b, d) < 0) and (orient(c, d, a) * orient(c, d, b) < 0)


RADII = [0.08, 0.18, 0.3, 0.44, 0.6, 0.78, 0.98, 1.2]  # label distance from its dot (inches)
ANGLES = np.deg2rad(np.arange(0, 360, 15))
R_DOT = 0.06        # coloured dot radius plus a margin (inches)
TOP_K = 32          # cheapest spots per label searched jointly
MAX_NODES = 400_000
LEADER_MIN = 0.12   # a label further than this from its dot gets a leader line (inches)
MISREAD_GAP = 0.12  # a label without a leader must be this much nearer its own dot than any other coloured dot
LEADER_CLEAR = 0.16  # a label with a leader must keep this far from every other coloured dot (inches)
LEADER_DOT = 0.09    # a leader may not pass nearer than this to another coloured dot (inches) ...
LEADER_BOX = 0.05    # ... or than this to another label
END_CLEAR = 0.18     # a leader's end (at its label) keeps this far from every other label (inches)
PAIR_GAP, PAIR_CLEAR = 0.08, 0.35  # each labelled dot's own label must be the nearest label to it by PAIR_GAP; when
                                   # its label is far (leader), other labels keep at least PAIR_CLEAR from it
LINE_COST = 0.5     # cost of a label across a reference line at 1
GRAY_COST = 0.06    # cost of each gray dot a label covers
LENGTH_COST = 0.5   # cost of a spot r inches from its dot: r + LENGTH_COST * r^2 (long leaders cost more)
RELPOS = {'left': 0.0, 'center': 0.5, 'right': 1.0, 'bottom': 0.0, 'top': 1.0}  # leader end on the label box


def candidates(i, items, keep_out, dots, gray, lines, ax_w, ax_h):
    """Every allowed spot for label i, cheapest first: (cost, box, dot, leader end, (dx, dy, ha, va, leader)).

    Hard rules, so every label reads as belonging to its own dot: a spot may not leave the axes, touch a keep-out
    box or cover a coloured dot. A label next to its dot (no leader) must be at least MISREAD_GAP nearer its own dot
    than any other coloured dot (blue or dark gray). A label further away gets a leader line, drawn from the dot to
    the label's anchor corner (the text's alignment point, see RELPOS), which may not pass over another coloured dot
    or a keep-out box, and the label must keep LEADER_CLEAR from every other coloured dot.
    Cost: distance, gray dots covered, reference lines crossed."""
    x, y, w, h = items[i]
    other_dots = dots[np.hypot(dots[:, 0] - x, dots[:, 1] - y) > 1e-9]
    out = []
    for r in RADII:
        for a in ANGLES:
            cx, cy = math.cos(a), math.sin(a)
            ha = 'left' if cx > 0.4 else 'right' if cx < -0.4 else 'center'
            va = 'bottom' if cy > 0.4 else 'top' if cy < -0.4 else 'center'
            anchor = (x + r * cx, y + r * cy)  # the text's alignment point
            box = text_box(*anchor, w, h, ha, va)
            if box[0] < 0.04 or box[1] < 0.04 or box[2] > ax_w - 0.04 or box[3] > ax_h - 0.04:
                continue
            if any(overlaps(box, b, 0.03) for b in keep_out) or inside(box, dots, R_DOT).any():
                continue
            nearest_other = min((box_distance(box, p) for p in other_dots), default=math.inf)
            leader = r > LEADER_MIN
            if leader:
                if nearest_other < LEADER_CLEAR:
                    continue
                seg = segment((x, y), anchor)
                if any(inside(b, seg).any() for b in keep_out):
                    continue
                if len(other_dots) and np.min(np.hypot(seg[:, None, 0] - other_dots[None, :, 0],
                                                       seg[:, None, 1] - other_dots[None, :, 1])) < LEADER_DOT:
                    continue
            elif nearest_other < box_distance(box, (x, y)) + MISREAD_GAP:
                continue
            cost = r + LENGTH_COST * r * r + GRAY_COST * int(inside(box, gray, 0.02).sum())
            cost += LINE_COST * sum(box[k] < v < box[k + 2] for k, v in lines)
            cost += 0.03 * (ha == 'center')
            out.append((cost, box, (x, y), anchor if leader else None, (r * cx, r * cy, ha, va, leader)))
    return sorted(out, key=lambda c: c[0])


def read_as(box, other_box, other_dot):
    """Whether a label box could be read as the label of other_dot: it is not clearly further from that dot than
    the dot's own label (other_box) is, or, when that label is far off on a leader, it comes within PAIR_CLEAR."""
    return box_distance(box, other_dot) < min(box_distance(other_box, other_dot) + PAIR_GAP, PAIR_CLEAR)


def compatible(a, b):
    """Whether two chosen spots (of different labels) can both be drawn: boxes apart, neither label read as the
    other dot's, no leader through the other box, leaders not crossing."""
    _, box, dot, end, _ = a
    _, obox, odot, oend, _ = b
    if overlaps(box, obox, 0.03) or read_as(box, obox, odot) or read_as(obox, box, dot):
        return False
    # A leader keeps clear of the other label along its length, and its end, where the eye lands, clearly so.
    if end is not None and (inside(obox, segment(dot, end), LEADER_BOX).any() or box_distance(obox, end) < END_CLEAR):
        return False
    if oend is not None and (inside(box, segment(odot, oend), LEADER_BOX).any() or box_distance(box, oend) < END_CLEAR):
        return False
    return not (end is not None and oend is not None and segments_cross(dot, end, odot, oend))


def place_labels(items, keep_out, dots, gray, lines, ax_w, ax_h):
    """Label placement in inches within the axes: the combination of spots (each label's TOP_K cheapest) with the
    lowest total cost, by branch and bound with forward checking. Each choice removes the spots it rules out from
    the labels still to place (backtracking at once when one has none left); the label with the fewest spots left
    goes next; the bound is the cost so far plus each remaining label's cheapest spot left.

    items: (x, y, w, h) per label (dot position, label size). keep_out: boxes no label may touch. dots: (n, 2)
    coloured dot centres, which no label may cover. gray: (m, 2) gray dot centres (small cost each). lines:
    (axis, position) of the reference lines, axis 0 = vertical line at x, 1 = horizontal line at y.
    Returns (dx, dy, ha, va, leader) per item."""
    every = [candidates(i, items, keep_out, dots, gray, lines, ax_w, ax_h) for i in range(len(items))]
    if any(not c for c in every):
        raise RuntimeError('fx_10: no free spot for a label')
    # The cheapest spots first; if they admit no layout, widen the search (the spots near a dot can crowd out the
    # only ones that fit).
    for top_k in (TOP_K, 2 * TOP_K, 4 * TOP_K, None):
        spots = _search([c[:top_k] for c in every])
        if spots is not None:
            return spots
    raise RuntimeError('fx_10: labels do not fit without overlaps')


def _search(cands):
    """Branch and bound over the given spots per label; (dx, dy, ha, va, leader) per label, or None."""
    n = len(cands)
    ok = {}

    def fits(i, a, j, b):
        key = (i, a, j, b) if i < j else (j, b, i, a)
        if key not in ok:
            ok[key] = compatible(cands[i][a], cands[j][b])
        return ok[key]

    best, nodes = [math.inf, None], [0]

    def search(domains, chosen, cost):
        """domains: label -> its spots (indices, cheapest first) still compatible with every choice made."""
        nodes[0] += 1
        if nodes[0] > MAX_NODES or cost + sum(cands[j][d[0]][0] for j, d in domains.items()) >= best[0]:
            return
        if not domains:
            best[0], best[1] = cost, dict(chosen)
            return
        i = min(domains, key=lambda j: (len(domains[j]), j))
        rest = [(j, d) for j, d in domains.items() if j != i]
        for a in domains[i]:
            pruned = {}
            for j, d in rest:
                pruned[j] = [b for b in d if fits(i, a, j, b)]
                if not pruned[j]:
                    break
            else:
                chosen[i] = a
                search(pruned, chosen, cost + cands[i][a][0])
                del chosen[i]

    search({i: list(range(len(cands[i]))) for i in range(n)}, {}, 0.0)
    return None if best[1] is None else [cands[i][best[1][i]][4] for i in range(n)]


def wrap_name(name):
    """Names longer than NAME_WRAP on two lines of about equal length (no single dangling word)."""
    if len(name) <= NAME_WRAP:
        return name
    for width in range(math.ceil(len(name) / 2), len(name) + 1):
        lines = textwrap.wrap(name, width, break_on_hyphens=False)
        if len(lines) <= 2:
            return '\n'.join(lines)
    return name


def num(x):
    """Rank correlations to 2 decimals."""
    return f'{x:.2f}'


def count(x):
    """A null-distribution count: whole numbers without decimals."""
    return f'{x:.0f}' if float(x).is_integer() else f'{x:.1f}'


# ---------------------------------------------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------------------------------------------
def draw(S, c, k, path, names=None):
    h1_text, h2_text = fleet.half_texts(S)
    name = (lambda x: x) if names is None else (lambda x: names.get(x, x))
    n = len(c)

    # Axis range, the same on both axes: zero-ticket customers at a floor below the smallest positive STR, in a
    # shaded strip; the upper end leaves room above the largest STR for the quadrant labels.
    pos = np.concatenate([c.x[c.x > 0], c.y[c.y > 0]])
    zero_at = pos.min() / ZERO_GAP
    sep = math.sqrt(zero_at * pos.min())  # edge of the zero strip, halfway (log scale) to the smallest STR
    lo, hi = zero_at / EDGE, pos.max() * HEADROOM
    style.check('fx_10 floor below every positive STR', 1, int(zero_at < pos.min() and sep < pos.min()))
    style.check('fx_10 every STR inside the axes', 1, int(pos.max() < hi))
    xs, ys = np.where(c.x > 0, c.x, zero_at), np.where(c.y > 0, c.y, zero_at)

    # ---- text ----
    persists = k['rho'] > k['null_hi']
    title = (f'Customers that run high tend to stay high: rank correlation {num(k["rho"])} between halves, '
             f'{num(k["null_med"])} by chance' if persists else
             f'Customers do not clearly stay high: rank correlation {num(k["rho"])} between halves, '
             f'{num(k["null_med"])} by chance')
    share_again = k['q']['both'] / k['above1']
    subtitle = [f'Standardised ticket ratio (STR) of each customer in the first half against the second half of '
                f'{fleet.period_text(S)}: the {n} customers with at least {MIN_E_HALF} expected tickets in each half, '
                f'one dot each. Of the {k["above1"]} above 1 in the first half, {k["q"]["both"]} '
                f'({share_again:.0%}) are above 1 again in the second, against {k["above2"]} of all {n} '
                f'({k["above2"] / n:.0%}). Chance: in {S["n_null"]:,} shuffles of the second halves, 97.5% give a '
                f'rank correlation below {num(k["null_hi"])}.']
    if names is not None:
        subtitle.insert(0, PRIVACY_WARNING)  # first line, so the warning is read before the chart
    not_shown = k['cons_all'] - k['cons_shown']
    notes = [f'Log axes, because these are ratios (0.5 and 2 sit the same distance from 1). Customers with no tickets '
             f'in a half (STR 0, which a log axis cannot show) are drawn in the shaded strips at 0: {k["zero1"]} in '
             f'the first half, {k["zero2"]} in the second. Consistent outliers lie above 1 in both halves by '
             f'definition; the rank correlation over all {n} customers is the test of persistence. '
             f'{not_shown} more consistent outliers have under {MIN_E_HALF} expected tickets in a half and are not '
             f'drawn.',
             f'Chance = second-half results shuffled {S["n_null"]:,} times among customers in the same tenth of '
             f'second-half expected tickets: differences between customers kept, persistence removed. {k["sig"]} '
             f'customers are above their expected tickets beyond chance (Poisson p < {P_CUT:g}) in both halves, '
             f'against a median of {count(k["sig_med"])} in the shuffles (95%: {count(k["sig_lo"])} to '
             f'{count(k["sig_hi"])}).',
             fleet.source('outlier_customers', 'outlier_persistence')[:-1] + '; half dates and shuffles from '
             'fx_summary.json' + (f'; names from {NAMES_FILE} (gitignored).' if names is not None else '.')]
    definitions = [fleet.expected_definition(S), fleet.STR_DEFINITION, fleet.consistent_definition(S)]

    width = max(10.5, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    top_band, bottom_band = bands(width, subtitle, definitions, notes)
    fig, ax = style.figure(width, top_band + PLOT_H + bottom_band)
    ax_w, ax_h = width - AX_W_LESS, PLOT_H - AX_H_LESS  # axes size in inches, for the label placement
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    l0, l1 = math.log10(lo), math.log10(hi)

    def to_in(x, y):
        """Data -> inches from the axes' lower-left corner, as an (n, 2) array."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        return np.column_stack([(np.log10(x) - l0) / (l1 - l0) * ax_w, (np.log10(y) - l0) / (l1 - l0) * ax_h])

    # Zero strips and the reference lines at 1.
    ax.axvspan(lo, sep, color=style.ZERO_CELL, lw=0, zorder=0)
    ax.axhspan(lo, sep, color=style.ZERO_CELL, lw=0, zorder=0)
    ax.axvline(1, color=style.INK2, lw=0.8, zorder=1)
    ax.axhline(1, color=style.INK2, lw=0.8, zorder=1)
    one = to_in(1, 1)[0]
    lines = [(0, one[0]), (1, one[1])]

    # Quadrant labels with their counts, in the four corners of the positive region.
    line_h = LABEL_PT / 72 * 1.25
    keep_out = []
    quads =[(f'Above 1 in both halves: {k["q"]["both"]}', hi, hi, 'right', 'top', -4, -4),
             (f'Above 1 in the second half only: {k["q"]["second"]}', sep, hi, 'left', 'top', 4, -4),
             (f'Above 1 in the first half only: {k["q"]["first"]}', hi, sep, 'right', 'bottom', -4, 4),
             (f'Below 1 in both halves: {k["q"]["neither"]}', sep, sep, 'left', 'bottom', 4, 4)]
    for text, qx, qy, ha, va, dx, dy in quads:
        ax.annotate(text, xy=(qx, qy), xytext=(dx, dy), textcoords='offset points', ha=ha, va=va,
                    fontsize=LABEL_PT + 0.5, color=style.INK2, zorder=6)
        bx, by = to_in(qx, qy)[0]
        keep_out.append(text_box(bx + dx / 72, by + dy / 72, len(text) * (LABEL_IN_PER_CHAR + 0.004), line_h, ha, va))

    # Dots: gray, then dark gray, then blue on top.
    styles = (('other', style.GRAY_LIGHT, DOT_GRAY, 'Other customers'),
              ('both', style.GRAY, DOT_COLOUR,
               f'Above expected beyond chance in both halves (Poisson p < {P_CUT:g}), not consistent'),
              ('consistent', style.BLUE, DOT_COLOUR, 'Consistent outlier'))
    for z, (key, colour, size, label) in enumerate(styles):
        sel = (c.cls == key).to_numpy()
        ax.scatter(xs[sel], ys[sel], s=size, color=colour, edgecolor=style.SURFACE, linewidth=0.4, zorder=3 + z,
                   clip_on=False, label=f'{label} ({int(sel.sum())})')
    # The customers with no tickets in either half all sit on one point: say how many.
    if k['zero_both']:
        txt = f'{k["zero_both"]} with no tickets in either half'
        ax.annotate(txt, xy=(zero_at, zero_at), xytext=(7, 0), textcoords='offset points', ha='left',
                    va='center', fontsize=LABEL_PT, color=style.INK2, zorder=6)
        bx, by = to_in(zero_at, zero_at)[0]
        keep_out.append(text_box(bx + 7 / 72, by, len(txt) * LABEL_IN_PER_CHAR, line_h, 'left', 'center'))

    leg = ax.legend(loc='upper left', bbox_to_anchor=(0, 0.955), frameon=True, facecolor=style.SURFACE,
                    edgecolor='none', framealpha=1, handletextpad=0.3, borderaxespad=0.3, fontsize=9)
    leg_w = 0.5 + 0.068 * max(len(t.get_text()) for t in leg.get_texts())
    keep_out.append((0, ax_h * 0.955 - 0.78, leg_w, ax_h * 0.955))
    # The legend is opaque and the quadrant and zero labels are drawn over the plot: none may sit on a dot.
    every_dot = to_in(xs, ys)
    style.check('fx_10 no dot under the legend, quadrant or zero labels', 0,
                int(sum(inside(b, every_dot, 0.03).sum() for b in keep_out)))
    for key, _, _, label in styles:
        style.check(f'fx_10 legend count: {label}', k['legend'][key], int((c.cls == key).sum()))

    # Labels: every consistent outlier drawn, largest expected tickets first.
    lab = c[c.cls == 'consistent'].assign(E=c.E_h1 + c.E_h2).sort_values(['E', 'customer'], ascending=[False, True])
    texts = [wrap_name(name(x)) for x in lab.customer]
    items = []
    for (px, py), t in zip(to_in(lab.x, lab.y), texts):
        parts = t.split('\n')
        items.append((px, py, max(map(len, parts)) * LABEL_IN_PER_CHAR + 0.06, len(parts) * LABEL_PT / 72 * 1.2 + 0.05))
    coloured = (c.cls != 'other').to_numpy()
    dots = to_in(xs[coloured], ys[coloured])
    gray = to_in(xs[~coloured], ys[~coloured])
    spots = place_labels(items, keep_out, dots, gray, lines, ax_w, ax_h)
    for r, t, (dx, dy, ha, va, leader) in zip(lab.itertuples(), texts, spots):
        ax.annotate(t, xy=(r.x, r.y), xytext=(dx * 72, dy * 72), textcoords='offset points', ha=ha, va=va,
                    fontsize=LABEL_PT, color=style.INK, linespacing=1.1, zorder=7,
                    bbox=dict(boxstyle='square,pad=0.1', fc=style.SURFACE, ec='none', alpha=0.85),
                    arrowprops=dict(arrowstyle='-', color=style.GRAY, lw=0.6, shrinkA=0, shrinkB=3,
                                    relpos=(RELPOS[ha], RELPOS[va])) if leader else None)

    ticks = [zero_at] + [t for t in TICKS if sep < t < hi]
    fmt = FuncFormatter(lambda v, _: '0' if v == zero_at else f'{v:g}')
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(FixedLocator(ticks))
        axis.set_minor_locator(NullLocator())
        axis.set_major_formatter(fmt)
    style.style_axes(ax, grid='both', baseline=None)
    ax.set_xlabel(f'STR, first half ({h1_text}), log scale')
    ax.set_ylabel(f'STR, second half ({h2_text}), log scale')

    style.frame(fig, title, subtitle, notes=notes, definitions=definitions)
    return style.save(fig, path)


def plot(out_dir=fleet.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into
    fleet.DELIVERABLES.

    The real-name PNG always goes to fleet.DELIVERABLES, whatever out_dir is, so a test run into a scratch out_dir
    with private=True overwrites the deliverable; pass private=False for test runs."""
    out_dir = Path(out_dir)
    S = fleet.summary()
    c, k = checks(S, fleet.load('outlier_customers'), fleet.load('outlier_persistence'))
    # Half dates drawn on the axis labels, recomputed from the period and the split.
    start, end, split = (pd.Timestamp(x) for x in (*S['definitions']['period'], S['definitions']['split']))
    h1_text, h2_text = fleet.half_texts(S)
    last1 = split - pd.Timedelta(days=1)
    style.check('fx_10 first-half dates = period start to the day before the split', 1,
                int(h1_text == f'{start.day} {start:%b %Y} to {last1.day} {last1:%b %Y}'))
    style.check('fx_10 second-half dates = split to period end', 1,
                int(h2_text == f'{split.day} {split:%b} to {end.day} {end:%b %Y}'))
    written = [draw(S, c, k, out_dir / PNG)]
    if private:
        names = fleet.real_customer_names()
        if names is None:
            print(f'  real-name variant skipped: {NAMES_FILE} not found')
        else:
            labelled = c[c.cls == 'consistent']
            style.check('fx_10 real names for every labelled customer', len(labelled),
                        int(labelled.customer.isin(set(names)).sum()))
            written.append(draw(S, c, k, fleet.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
