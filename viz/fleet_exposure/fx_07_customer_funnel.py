#!/usr/bin/env python3
"""Fleet chart 7: funnel plot of customers, standardised ticket ratio (STR) against expected tickets.

Why: a customer with few machines can show a high STR by chance alone, and customers differ from one another by more
than Poisson chance allows (sites, users and reporting differ). The funnel plot shows both at once. Each customer is
one dot: x = expected tickets at fleet rates for its models and ages (log scale, because expected tickets span four
orders of magnitude), y = STR = observed / expected. Three pairs of limits are drawn:
  solid gray: the 95% and 99.8% overdispersion-adjusted funnel (fleet.funnel_limits), which allows for the normal
              spread between customers (tau^2 from fx_summary.json);
  dashed:     the plain Poisson 99.8% limits (fleet.poisson_limits, tau^2 = 0), which allow for chance only.
Dots: light gray = neither flag; orange = flagged by the Poisson rule (not consistent); blue = consistent outliers.
The title contrasts the customers flagged by the Poisson rule with those outside the 99.8% funnel, so the reader sees
why plain Poisson limits flag too many. Labelled: consistent outliers with at least LABEL_MIN_EXPECTED expected
tickets, and every customer beyond the 99.8% funnel; labels are placed by a small branch-and-bound search
(place_labels()) over spots around each dot, clear of other labels, coloured dots, the legend and the line labels.
A label without a leader must be clearly nearer its own dot than any other coloured dot (MISREAD_RATIO), so in the
crowded band of orange and blue dots most labels get a short leader line. One customer with an STR far above the
rest is drawn at the top edge (noted).

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and the gitignored name table exists. It is written to deliverables/
  (gitignored) and must never be committed; its privacy warning is the first line of the subtitle.

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here except for the checks):
  verification/outputs/fleet/fx_customer_rates.csv  customer, tickets, expected, STR, z_d, p_poisson,
                                                    poisson_flagged, beyond_funnel_998, variants_flagged,
                                                    O_h1, E_h1, O_h2, E_h2, consistent_outlier (one row per customer)
  verification/outputs/fleet/fx_summary.json        customers.tau2 (funnel), definitions (z95, z998, flag and
                                                    consistency thresholds, period), customers.* counts for checks
  data/private/fx_private_customer_names.csv        customer -> real_account_name (real-name version only; gitignored)
Outputs:
  viz/figures/fx_07_customer_funnel.png
  deliverables/fx_07_customer_funnel_REALNAMES.png   (private=True only)

Run:  cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_07_customer_funnel.py
"""
import math
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullLocator  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_07_customer_funnel.png'
REAL_PNG = 'fx_07_customer_funnel_REALNAMES.png'
LABEL_MIN_EXPECTED = 10   # consistent outliers with at least this many expected tickets are labelled
PLOT_H = 6.4              # inches between the title band and the footer (axes, tick labels, axis label)
PLOT_H_NAMES = 7.4        # the same for the real-name version: its wrapped names need more room
TITLE_IN_PER_CHAR = 0.124  # approximate width of one title character (15 pt bold), for the figure width
LABEL_PT = 8.5            # point-label font size
LABEL_IN_PER_CHAR = 0.066  # approximate width of one character at LABEL_PT (DejaVu Sans), for label boxes
NAME_WRAP = 20            # real names longer than this many characters wrap onto more lines
DOT_GRAY, DOT_COLOUR = 14, 30  # marker areas (pt^2)
X_RIGHT = 2.4             # x axis ends at this multiple of the largest expected count (room for the line labels)
AX_W_LESS, AX_H_LESS = 1.04, 0.56  # figure width / plot height less the axes size (tick and axis labels), inches
PRIVACY_WARNING = ('Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                   '(gitignored); never commit.')


# ---------------------------------------------------------------------------------------------------------------
# Independent recomputations for the checks (Poisson tail, Benjamini-Hochberg, funnel z), written here from the
# definitions in verification/fleet_exposure.py, so the flags in the CSV are tested, not copied.
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


def bh(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def checks(S, cr):
    """Consistency checks; returns the customers with expected tickets (the plotted population) plus the counts
    the chart states."""
    d, C = S['definitions'], S['customers']
    style.check('fx_07 customer tickets sum to the fleet', S['fleet']['tickets'], int(cr.tickets.sum()))
    style.check('fx_07 customers without expected tickets have no tickets', 0,
                int(cr.tickets[cr.expected <= 0].sum()))
    c = cr[cr.expected > 0].reset_index(drop=True)
    style.check('fx_07 customers with expected tickets = summary', C['customers_with_E'], len(c))
    style.check('fx_07 STR = tickets / expected', 0, float((c.tickets / c.expected - c.STR).abs().max()), 1e-9)

    # Poisson rule recomputed: upper tail, BH over customers with expected > 0, at least min_flag_tickets.
    p = np.array([poisson_upper(o, e) for o, e in zip(c.tickets, c.expected)])
    style.check('fx_07 Poisson p recomputed', 0, float(np.abs(p - c.p_poisson.to_numpy()).max()), 1e-9)
    flag = (c.tickets.to_numpy() >= d['min_flag_tickets']) & (bh(p) < d['q_cut'])
    style.check('fx_07 flagged customers recomputed = poisson_flagged', 0,
                int((flag != c.poisson_flagged.to_numpy()).sum()))
    style.check('fx_07 flagged customers = summary', C['poisson_flagged'], int(flag.sum()))

    # Consistent rule recomputed: flagged in >= min_variants variants and Poisson p < 0.05 in each half.
    p1 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(c.O_h1, c.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(c.O_h2, c.E_h2)])
    cons = (c.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < 0.05) & (p2 < 0.05)
    style.check('fx_07 consistent outliers recomputed = consistent_outlier', 0,
                int((cons != c.consistent_outlier.to_numpy()).sum()))
    style.check('fx_07 consistent outliers = summary', C['consistent_outliers'], int(cons.sum()))

    # tau^2 (drawn in the note) recomputed: additive random-effects moment estimator on the Poisson z of every
    # customer with expected > 0, winsorised at its 10th and 90th percentiles (verification/fleet_exposure.py, F5).
    e_, o_ = c.expected.to_numpy(), c.tickets.to_numpy(float)
    z0 = (np.sqrt(o_ / e_) - 1) * 2 * np.sqrt(e_)
    zw = np.clip(z0, *np.percentile(z0, [10, 90]))
    w = 4 * e_  # 1 / s^2
    tau2 = max(0.0, (len(zw) * np.mean(zw ** 2) - (len(zw) - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    style.check('fx_07 tau^2 recomputed = summary', C['tau2'], tau2, 1e-9)

    # Funnel z recomputed on the square-root scale with the summary's tau^2; beyond the 99.8% funnel.
    s2 = 1 / (4 * c.expected.to_numpy())
    z = (np.sqrt(c.tickets.to_numpy() / c.expected.to_numpy()) - 1) / np.sqrt(s2 + C['tau2'])
    style.check('fx_07 funnel z recomputed = z_d', 0, float(np.abs(z - c.z_d.to_numpy()).max()), 1e-9)
    beyond = z > d['z998']
    style.check('fx_07 beyond the 99.8% funnel recomputed = beyond_funnel_998', 0,
                int((beyond != c.beyond_funnel_998.to_numpy()).sum()))
    style.check('fx_07 beyond the 99.8% funnel = summary', C['flagged_998'], int(beyond.sum()))
    # The drawn lines (fleet.funnel_limits / fleet.poisson_limits) put the same customers outside.
    hi998 = fleet.funnel_limits(c.expected, d['z998'], S)[1]
    style.check('fx_07 dots above the drawn 99.8% funnel = beyond the funnel', int(beyond.sum()),
                int((c.STR.to_numpy() > hi998).sum()))
    in95 = cons & (z < d['z95'])
    style.check('fx_07 consistent outliers inside the 95% funnel = summary', C['consistent_outliers_inside_funnel_95'],
                int(in95.sum()))
    hi95 = fleet.funnel_limits(c.expected, d['z95'], S)[1]
    style.check('fx_07 consistent outliers below the drawn 95% funnel', int(in95.sum()),
                int((cons & (c.STR.to_numpy() < hi95)).sum()))
    # Above the plain Poisson 99.8% limit, recomputed: sqrt(O/E) > 1 + z / (2 sqrt(E)).
    above_pois = np.sqrt(c.STR.to_numpy()) > 1 + d['z998'] / (2 * np.sqrt(c.expected.to_numpy()))
    style.check('fx_07 above the drawn Poisson 99.8% limit',
                int(above_pois.sum()), int((c.STR.to_numpy() > fleet.poisson_limits(c.expected, d['z998'])[1]).sum()))
    # The note says the flagged customers below the dashed line sit "just below it": every customer above it is
    # flagged, and those below it are within 20% of it.
    hi_pois = fleet.poisson_limits(c.expected, d['z998'])[1]
    style.check('fx_07 every customer above the dashed limit is flagged', 0, int((above_pois & ~flag).sum()))
    style.check('fx_07 flagged customers below the dashed limit are within 20% of it', 1,
                int(((c.STR.to_numpy() / hi_pois)[flag & ~above_pois] > 0.8).all()))
    # Colours are nested: every consistent outlier is also flagged in the main variant (blue drawn over orange).
    style.check('fx_07 consistent outliers are flagged', 0, int((cons & ~flag).sum()))
    # Customers with no tickets (drawn on the baseline), counted from the two halves.
    style.check('fx_07 tickets = first half + second half', 0, int((c.O_h1 + c.O_h2 != c.tickets).sum()))
    n_zero = int(((c.O_h1 + c.O_h2) == 0).sum())
    style.check('fx_07 customers with no tickets', n_zero, int((c.tickets == 0).sum()))
    return c, {'flagged': int(flag.sum()), 'consistent': int(cons.sum()), 'beyond': int(beyond.sum()),
               'in95': int(in95.sum()), 'above_pois': int(above_pois.sum()),
               'flag_below_pois': int((flag & ~above_pois).sum()), 'n_zero': n_zero}


# ---------------------------------------------------------------------------------------------------------------
# Layout helpers: page bands (the same arithmetic as style.frame) and greedy label placement in inches
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


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def inside(box, pts, pad=0.0):
    """Boolean mask: which of the (n, 2) points lie in box grown by pad."""
    return ((pts[:, 0] > box[0] - pad) & (pts[:, 0] < box[2] + pad) &
            (pts[:, 1] > box[1] - pad) & (pts[:, 1] < box[3] + pad))


def box_distance(box, p):
    """Distance from point p to the box (0 inside)."""
    dx = max(box[0] - p[0], 0.0, p[0] - box[2])
    dy = max(box[1] - p[1], 0.0, p[1] - box[3])
    return math.hypot(dx, dy)


def segment(p, q, n=30):
    t = np.linspace(0, 1, n)[:, None]
    return np.asarray(p) + t * (np.asarray(q) - np.asarray(p))


def segments_cross(a, b, c, d):
    """Whether segment a-b properly crosses segment c-d."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (orient(a, b, c) * orient(a, b, d) < 0) and (orient(c, d, a) * orient(c, d, b) < 0)


RADII = [0.1, 0.2, 0.32, 0.46, 0.62, 0.8, 1.0, 1.25, 1.55, 1.9]  # label distance from its dot (inches)
ANGLES = np.deg2rad(np.arange(0, 360, 15))
R_DOT = 0.055      # coloured dot radius plus a margin (inches)
R_LEADER = 0.08    # how far a leader stays from other coloured dots (inches) ...
LEADER_GAP_PT = 3  # ... beyond the gap the leader leaves at its own dot (arrowprops shrinkB, points); a dot that
                   # touches its neighbour can still have a leader that leaves on the far side
TOP_K = 64         # cheapest spots per label searched jointly (128 finds no better layout for either version)
MAX_NODES = 400_000
MISREAD_RATIO = 2.5  # a label without a leader must be this many times nearer its own dot than any other coloured
                     # dot, or it could be read as that dot's label (such a spot is not allowed)
LEADER_CLEAR = 0.12  # a label with a leader should keep this far from other coloured dots (inches) ...
LEADER_NEAR_COST = 0.3  # ... or pay this
GRAY_COST = 0.02   # cost per gray dot a label covers (its background hides them)
LONG_LEADER, LONG_COST = 1.0, 1.5  # extra cost per inch of leader beyond LONG_LEADER inches
CROSS_COST = {'funnel': 1.5, 'poisson': 1.5, 'fleet': 1.5}  # cost of a label across a line, by line (a label on
                                                            # a line reads worse than a longer leader)


def candidates(i, items, keep_out, dots, gray, curves, ax_w, ax_h):
    """Every allowed spot for label i, cheapest first, with its own cost: distance (more beyond LONG_LEADER), gray
    dots covered, limit lines crossed, and another coloured dot at a label that has a leader. A spot may not leave
    the axes, touch a keep-out box or cover a coloured dot; its leader may not pass over another coloured dot; and
    a label without a leader must be clearly nearer its own dot than any other coloured dot (MISREAD_RATIO)."""
    x, y, w, h = items[i]
    other_dots = dots[np.hypot(dots[:, 0] - x, dots[:, 1] - y) > 1e-9]  # every other coloured dot, labelled or not
    out = []
    for r in RADII:
        for a in ANGLES:
            cx, cy = math.cos(a), math.sin(a)
            ha = 'left' if cx > 0.4 else 'right' if cx < -0.4 else 'center'
            va = 'bottom' if cy > 0.4 else 'top' if cy < -0.4 else 'center'
            tx, ty = x + r * cx, y + r * cy
            box = text_box(tx, ty, w, h, ha, va)
            if box[0] < 0.04 or box[1] < 0.1 or box[2] > ax_w - 0.04 or box[3] > ax_h - 0.04:
                continue
            grown = (box[0] - 0.03, box[1] - 0.03, box[2] + 0.03, box[3] + 0.03)
            if any(overlaps(grown, b) for b in keep_out) or inside(grown, dots, R_DOT).any():
                continue
            leader = r > 0.14
            end = (min(max(x, box[0]), box[2]), min(max(y, box[1]), box[3]))  # where the leader meets the box
            if leader:
                seg = segment((x, y), end)
                if any(inside(b, seg).any() for b in keep_out):
                    continue
                seg = seg[np.hypot(seg[:, 0] - x, seg[:, 1] - y) > LEADER_GAP_PT / 72]  # the drawn part
                if len(other_dots) and len(seg) and np.min(np.hypot(seg[:, None, 0] - other_dots[None, :, 0],
                                                       seg[:, None, 1] - other_dots[None, :, 1])) < R_LEADER:
                    continue
            cost = r + 0.5 * r * r + LONG_COST * max(0.0, r - LONG_LEADER)
            cost += GRAY_COST * int(inside(box, gray).sum())
            cost += sum(wt for cv, wt in curves if inside(box, cv).any())
            near = min((box_distance(box, p) for p in other_dots), default=math.inf)
            if not leader and near < MISREAD_RATIO * box_distance(box, (x, y)):
                continue
            if leader and near < LEADER_CLEAR:
                cost += LEADER_NEAR_COST
            cost += 0.03 * (ha == 'center')
            # Where the drawn leader leaves the label, as a fraction of the label box (arrowprops relpos).
            relpos = ((end[0] - box[0]) / w, (end[1] - box[1]) / h) if leader else None
            out.append((cost, box, (x, y), end if leader else None, (tx - x, ty - y, ha, va, relpos)))
    return sorted(out, key=lambda c: c[0])


def compatible(a, b):
    """Whether two chosen spots (of different labels) can both be drawn: boxes apart, no leader through the other
    box, leaders not crossing."""
    _, box, dot, end, _ = a
    _, obox, odot, oend, _ = b
    grown = (box[0] - 0.03, box[1] - 0.03, box[2] + 0.03, box[3] + 0.03)
    if overlaps(grown, obox):
        return False
    if end is not None and inside(obox, segment(dot, end)).any():
        return False
    if oend is not None and inside(box, segment(odot, oend)).any():
        return False
    return not (end is not None and oend is not None and segments_cross(dot, end, odot, oend))


def envelope(cand, pad=0.04):
    """Bounding box of a spot's label and leader, grown by pad: spots whose envelopes are apart cannot clash."""
    _, box, dot, end, _ = cand
    x0, y0, x1, y1 = box
    if end is not None:
        x0, y0, x1, y1 = min(x0, dot[0]), min(y0, dot[1]), max(x1, dot[0]), max(y1, dot[1])
    return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)


def place_labels(items, keep_out, dots, gray, curves, ax_w, ax_h):
    """Label placement in inches within the axes: the combination of spots (each label's TOP_K cheapest) with the
    lowest total cost. Depth-first branch and bound with forward checking: pairwise compatibility is precomputed,
    the most constrained label is placed next, and the bound adds each other label's cheapest spot still allowed.

    items: (x, y, w, h) per label (dot position, label size). keep_out: boxes no label may touch (legend, line
    labels). dots: (n, 2) coloured dot centres, which no label may cover. gray: (m, 2) gray dot centres (small cost
    each). curves: list of ((k, 2) samples of a limit line, cost of a label across it).
    Returns (dx, dy, ha, va, relpos) per item; relpos is None when the label needs no leader."""
    n = len(items)
    cands = [candidates(i, items, keep_out, dots, gray, curves, ax_w, ax_h)[:TOP_K] for i in range(n)]
    if any(not c for c in cands):
        raise RuntimeError('fx_07: no free spot for a label')
    cost = [np.array([c[0] for c in cs]) for cs in cands]
    env = [[envelope(c) for c in cs] for cs in cands]
    compat = {}
    for i in range(n):
        for j in range(i + 1, n):
            m = np.ones((len(cands[i]), len(cands[j])), bool)
            for a, ca in enumerate(cands[i]):
                for b, cb in enumerate(cands[j]):
                    if overlaps(env[i][a], env[j][b]):
                        m[a, b] = compatible(ca, cb)
            compat[i, j], compat[j, i] = m, m.T

    best, nodes = [math.inf, None], [0]

    def search(assigned, allowed, total):
        nodes[0] += 1
        free = [i for i in range(n) if i not in assigned]
        if not free:
            if total < best[0]:
                best[0], best[1] = total, dict(assigned)
            return
        if total + sum(cost[i][allowed[i]].min() for i in free) >= best[0] or nodes[0] > MAX_NODES:
            return
        i = min(free, key=lambda k: (int(allowed[k].sum()), k))
        for a in np.flatnonzero(allowed[i]):  # candidates are sorted by cost, so cheapest first
            narrowed = {}
            for j in free:
                if j != i:
                    narrowed[j] = allowed[j] & compat[i, j][a]
                    if not narrowed[j].any():
                        break
            else:
                assigned[i] = a
                search(assigned, {**allowed, **narrowed}, total + cost[i][a])
                del assigned[i]

    search({}, {i: np.ones(len(cands[i]), bool) for i in range(n)}, 0.0)
    if best[1] is None:
        raise RuntimeError('fx_07: labels do not fit without overlaps')
    if nodes[0] > MAX_NODES:
        print(f'  [WARN] fx_07: label search stopped at {MAX_NODES:,} nodes; layout may not be the best')
    return [cands[i][best[1][i]][4] for i in range(n)]


def wrap_name(name, width=NAME_WRAP):
    return '\n'.join(textwrap.wrap(name, width)) if len(name) > width else name


def lie(k):
    """'only 1 lies' / 'only 3 lie' / 'none lies'."""
    return 'none lies' if k == 0 else f'only {k} lies' if k == 1 else f'only {k} lie'


# ---------------------------------------------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------------------------------------------
def draw(S, c, counts, path, names=None):
    d, C = S['definitions'], S['customers']
    z95, z998, tau2 = d['z95'], d['z998'], C['tau2']
    name = (lambda x: x) if names is None else (lambda x: names.get(x, x))

    # Axis ranges: x from just below the smallest expected count to room at the right for the line labels; y up to
    # just above the highest coloured dot. Dots above the top are drawn on the top edge and noted.
    xlo, xhi = c.expected.min() / 1.4, c.expected.max() * X_RIGHT
    ytop = math.ceil(c[c.poisson_flagged | c.consistent_outlier].STR.max() + 0.6)
    over = c[c.STR > ytop].sort_values('STR', ascending=False)
    n_zero = counts['n_zero']

    title = (f'{counts["flagged"]} customers are flagged, but {lie(counts["beyond"])} outside the normal spread '
             f'between customers')
    subtitle = [f'Standardised ticket ratio (STR) against expected tickets for the {len(c):,} customers with machines '
                f'on IPA\'s installed-base list in place during {fleet.period_text(S)}, one dot each. The plain '
                f'Poisson 99.8% limits (dashed) allow for chance only: {counts["above_pois"]} customers lie above '
                f'them. The funnel limits (solid gray) also allow for the normal spread between customers: '
                f'{counts["beyond"]} lies above the 99.8% limit. Blue: the {counts["consistent"]} consistent '
                f'outliers, {counts["in95"]} of them inside even the 95% funnel; orange: '
                f'{counts["flagged"] - counts["consistent"]} more flagged customers.']
    if counts['beyond'] != 1:
        subtitle[0] = subtitle[0].replace(f'{counts["beyond"]} lies above', f'{counts["beyond"]} lie above')
    if names is not None:
        subtitle.insert(0, PRIVACY_WARNING)  # first line, so the warning is read before the chart
    if len(over) == 1:
        o = over.iloc[0]
        over_txt = (f'; one (STR {o.STR:.1f}: {int(o.tickets)} tickets against {o.expected:.2f} expected) is drawn '
                    f'on the top edge')
    elif len(over):
        o = over.iloc[0]
        over_txt = (f'; {len(over)} with an STR above {ytop} (highest {o.STR:.1f}: {int(o.tickets)} tickets against '
                    f'{o.expected:.2f} expected) are drawn on the top edge')
    else:
        over_txt = ''
    notes = [f'Limits on the square-root scale: STR = (1 ± z√(1/(4E) + τ²))², E = expected tickets, z = {z95:.2f} '
             f'(95%) or {z998:.2f} (99.8%), τ² = {tau2:.3f} (spread between customers, estimated from their STRs); '
             f'dashed: τ² = 0. The flag\'s false-discovery cut is a little looser than the dashed line, so '
             f'{counts["flag_below_pois"]} flagged customers sit just below it.',
             f'Expected tickets allow for model and machine age only, not coverage, use or reporting. {n_zero} '
             f'customers with no tickets lie on the baseline{over_txt}.',
             fleet.source('customer_rates')[:-1] + '; τ² from fx_summary.json'
             + ('; names from data/private/fx_private_customer_names.csv (gitignored).' if names is not None
                else '.')]
    definitions = [fleet.expected_definition(S), fleet.STR_DEFINITION, fleet.flagged_customer_definition(S),
                   fleet.consistent_definition(S), fleet.funnel_definition(S)]

    width = max(11.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    top_band, bottom_band = bands(width, subtitle, definitions, notes)
    plot_h = PLOT_H if names is None else PLOT_H_NAMES
    fig, ax = style.figure(width, top_band + plot_h + bottom_band)
    ax_w, ax_h = width - AX_W_LESS, plot_h - AX_H_LESS  # axes size in inches, for the label placement
    ax.set_xscale('log')
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(0, ytop)
    lx0, lx1 = math.log10(xlo), math.log10(xhi)

    def to_in(x, y):
        """Data -> inches from the axes' lower-left corner, as an (n, 2) array."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        return np.column_stack([(np.log10(x) - lx0) / (lx1 - lx0) * ax_w, np.minimum(y, ytop) / ytop * ax_h])

    def from_in_x(xi):
        return 10 ** (lx0 + xi / ax_w * (lx1 - lx0))

    line_h = LABEL_PT / 72 * 1.3
    keep_out = []

    # Limits: the fleet rate, the 95% and 99.8% funnel (solid) and the plain Poisson 99.8% limits (dashed).
    xs = np.logspace(lx0, lx1, 1500)
    lo95, hi95 = fleet.funnel_limits(xs, z95, S)
    lo998, hi998 = fleet.funnel_limits(xs, z998, S)
    plo, phi = fleet.poisson_limits(xs, z998)
    ax.axhline(1, color=style.INK2, lw=0.8, zorder=1)
    # Samples of each line in inches, with the cost of a label across it (solid funnel lines cost most: a label on
    # one reads as if the line were its leader).
    curves = [(to_in(xs, np.ones_like(xs)), CROSS_COST['fleet'])]
    for lo, hi, lw, ls, kind in ((lo95, hi95, 0.9, '-', 'funnel'), (lo998, hi998, 1.5, '-', 'funnel'),
                                 (plo, phi, 1.0, (0, (4, 3)), 'poisson')):
        for yv in (hi, lo):
            ax.plot(xs, yv, color=style.GRAY, lw=lw, ls=ls, zorder=2)
            curves.append((to_in(xs, yv)[yv < ytop], CROSS_COST[kind]))

    # Line labels at the right end: the funnel's above its upper limit, the Poisson pair's below its lower limit
    # (the space above the dashed upper limit is where the largest customers' labels go), clear of the line over
    # the label's width.
    for lab, line, above in (('99.8% funnel', hi998, True), ('95% funnel', hi95, True),
                             ('99.8% Poisson only', plo, False)):
        w = len(lab) * LABEL_IN_PER_CHAR
        span = line[xs >= from_in_x(ax_w - 3 / 72 - w)]
        yv = float(span.max() if above else span.min())
        dy = 3 if above else -3
        va = 'bottom' if above else 'top'
        ax.annotate(lab, xy=(xhi, yv), xytext=(-3, dy), textcoords='offset points', ha='right', va=va,
                    fontsize=LABEL_PT, color=style.INK2)
        bx, by = to_in(xhi, yv)[0]
        keep_out.append(text_box(bx - 3 / 72, by + dy / 72, w, line_h, 'right', va))
    ax.annotate('1 = fleet rate', xy=(xlo, 1), xytext=(3, 3), textcoords='offset points', ha='left', va='bottom',
                fontsize=LABEL_PT, color=style.INK2)
    bx, by = to_in(xlo, 1)[0]
    keep_out.append(text_box(bx + 3 / 72, by + 3 / 72, 14 * LABEL_IN_PER_CHAR, line_h, 'left', 'bottom'))

    # Dots: gray, then orange, then blue on top; dots above the top edge as triangles on it.
    cls = np.where(c.consistent_outlier, 'consistent', np.where(c.poisson_flagged, 'flagged', 'neither'))
    y_draw = np.minimum(c.STR, ytop)
    high = (c.STR > ytop).to_numpy()
    n_cls = {k: int((cls == k).sum()) for k in ('neither', 'flagged', 'consistent')}
    style.check('fx_07 legend: not flagged', len(c) - counts['flagged'], n_cls['neither'])
    style.check('fx_07 legend: flagged, not consistent', counts['flagged'] - counts['consistent'], n_cls['flagged'])
    style.check('fx_07 legend: consistent outliers', counts['consistent'], n_cls['consistent'])
    for z, (key, colour, size, label) in enumerate((('neither', style.GRAY_LIGHT, DOT_GRAY, 'Not flagged'),
                                                    ('flagged', style.ORANGE, DOT_COLOUR, 'Flagged, not consistent'),
                                                    ('consistent', style.BLUE, DOT_COLOUR, 'Consistent outlier'))):
        for m, sel in (('o', (cls == key) & ~high), ('^', (cls == key) & high)):
            if sel.any() or m == 'o':
                ax.scatter(c.expected[sel], y_draw[sel], s=size * (2 if m == '^' else 1), marker=m, color=colour,
                           edgecolor=style.SURFACE, linewidth=0.4, zorder=3 + z, clip_on=False,
                           label=f'{label} ({n_cls[key]})' if m == 'o' else None)
    for o in over.itertuples():
        ax.annotate(f'STR {o.STR:.1f}', xy=(o.expected, ytop), xytext=(6, -1), textcoords='offset points',
                    ha='left', va='top', fontsize=LABEL_PT, color=style.INK2)
        bx, by = to_in(o.expected, ytop)[0]
        keep_out.append(text_box(bx + 6 / 72, by - 1 / 72, 9 * LABEL_IN_PER_CHAR, line_h, 'left', 'top'))

    leg = ax.legend(loc='upper right', frameon=True, facecolor=style.SURFACE, edgecolor='none', framealpha=1,
                    handletextpad=0.3, borderaxespad=0.3, fontsize=9)
    leg_w = 0.6 + 0.075 * max(len(t.get_text()) for t in leg.get_texts())
    keep_out.append((ax_w - leg_w, ax_h - 0.95, ax_w, ax_h))

    # Labels: consistent outliers with expected >= LABEL_MIN_EXPECTED, and every customer beyond the 99.8% funnel
    # (placed first, with what it shows).
    lab = c[(c.consistent_outlier & (c.expected >= LABEL_MIN_EXPECTED)) | c.beyond_funnel_998]
    lab = lab.assign(rest=~lab.beyond_funnel_998).sort_values(['rest', 'expected'], ascending=[True, False],
                                                              kind='mergesort')
    beyond_txt = 'outside the 99.8% funnel'  # second line of the beyond-funnel label; its name wraps to this width
    texts = [wrap_name(name(r.customer), max(NAME_WRAP, len(beyond_txt))) + '\n' + beyond_txt if r.beyond_funnel_998
             else wrap_name(name(r.customer)) for r in lab.itertuples()]
    items = []
    for (px, py), t in zip(to_in(lab.expected, lab.STR), texts):
        lines = t.split('\n')
        items.append((px, py, max(map(len, lines)) * LABEL_IN_PER_CHAR + 0.06, len(lines) * LABEL_PT / 72 * 1.2 + 0.05))
    dots = to_in(c.expected[cls != 'neither'], c.STR[cls != 'neither'])
    gray = to_in(c.expected[cls == 'neither'], c.STR[cls == 'neither'])
    spots = place_labels(items, keep_out, dots, gray, curves, ax_w, ax_h)
    for r, t, (dx, dy, ha, va, relpos) in zip(lab.itertuples(), texts, spots):
        ax.annotate(t, xy=(r.expected, r.STR), xytext=(dx * 72, dy * 72), textcoords='offset points', ha=ha, va=va,
                    fontsize=LABEL_PT, color=style.INK if r.beyond_funnel_998 else style.INK2,
                    weight='bold' if r.beyond_funnel_998 else 'normal', linespacing=1.1, zorder=7,
                    bbox=dict(boxstyle='square,pad=0.1', fc=style.SURFACE, ec='none', alpha=0.85),
                    arrowprops=dict(arrowstyle='-', color=style.GRAY, lw=0.6, shrinkA=0, shrinkB=LEADER_GAP_PT,
                                    relpos=relpos) if relpos else None)

    ax.set_xticks([t for t in (0.03, 0.1, 0.3, 1, 3, 10, 30, 100, 300) if xlo <= t <= xhi])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.xaxis.set_minor_locator(NullLocator())  # no tick marks (style sheet), not even the log axis's minor ones
    ax.set_yticks(range(0, ytop + 1))
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Expected tickets at fleet rates for the customer\'s models and ages (log scale)')
    ax.set_ylabel('STR (observed ÷ expected tickets)')

    style.frame(fig, title, subtitle, notes=notes, definitions=definitions)
    return style.save(fig, path)


def plot(out_dir=fleet.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into
    fleet.DELIVERABLES.

    The real-name PNG always goes to fleet.DELIVERABLES, whatever out_dir is, so a test run into a scratch out_dir
    with private=True overwrites the deliverable; pass private=False for test runs."""
    out_dir = Path(out_dir)
    S = fleet.summary()
    c, counts = checks(S, fleet.load('customer_rates'))
    written = [draw(S, c, counts, out_dir / PNG)]
    if private:
        names = fleet.real_customer_names()
        if names is None:
            print('  real-name variant skipped: data/private/fx_private_customer_names.csv not found')
        else:
            labelled = c[(c.consistent_outlier & (c.expected >= LABEL_MIN_EXPECTED)) | c.beyond_funnel_998]
            style.check('fx_07 real names for every labelled customer', len(labelled),
                        int(labelled.customer.isin(set(names)).sum()))
            written.append(draw(S, c, counts, fleet.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
