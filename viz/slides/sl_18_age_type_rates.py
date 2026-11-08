#!/usr/bin/env python3
"""Slide chart 18 (follow-up to slide 4): unplanned-ticket rates by request type, machines under 4 vs 4+ years.

The crude rate ratio by request group (docs/09 §4 A1): a group's unplanned tickets per 100 installed machine-months
on under-4 machines ÷ the same rate on 4+ machines, all models pooled (descriptive, not adjusted for model), with its
95% account-bootstrap interval. Drawn in the layout of the other comparison charts (sl_19, sl_20): one dot and bar per
row on a log scale, a dashed line at 1 (no difference) and the numbers on the right. All unplanned tickets sit on
top, set apart by a gap, then the ten groups by ratio, highest first. Blue = the interval excludes 1, gray = it
includes 1; the All row in navy. The right-hand columns give the two rates (Per 100, under 4 / 4+) and the ratio,
bold where the interval excludes 1.

Input:  verification/outputs/followups/ag_type_rates.csv, followups_summary.json
Output: viz/figures/slides/sl_18_age_type_rates.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.transforms import offset_copy  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_18_age_type_rates.png'
TERMS = ['rate_ratio_crude', 'interval', 'crude', 'rate', 'under4', 'request_group']
ALL = 'All unplanned tickets'
GAP = 0.5                  # extra space between the All row and the groups (rows)
X_LO, X_HI = 0.42, 15      # x limits (log scale); the value columns sit right of every bar
RATES_AT = -48             # right edge of the Per 100 column, in points from the axes' right edge (Ratio: the edge)
TICKS = [0.5, 1, 2, 4]
PIN_U4 = 'A1: under-4 rate per 100 (slide 4: 3,629 / 45,103.38)'
PIN_P4 = 'A1: 4+ rate per 100 (slide 4: 3,121 / 64,517.91)'


def excludes_one(lo, hi):
    return lo > 1 or hi < 1


def plot(out_dir=S.FIG_DIR):
    t = pd.read_csv(T.FU / 'ag_type_rates.csv')
    # Highest ratio at the top (y = row index, so the highest comes last); ties broken by name, A at the top.
    d = t[t.level == 'group'].sort_values(['rate_ratio', 'type'], ascending=[True, False]).reset_index(drop=True)
    a = t[t.level == 'all'].iloc[0]
    s = T.summary()
    pins = {c['check']: c['actual'] for c in s['checks']['list']}
    S.check('sl_18 ten request groups', 10, len(d))
    S.check('sl_18 the groups are the summary\'s ten', 1, int(sorted(d.type) == sorted(s['definitions']['groups'])))
    S.check('sl_18 one all row', 1, int((t.level == 'all').sum() == 1 and a.type == ALL))
    S.check('sl_18 groups sum to the all row, under 4', a.under4_tickets, d.under4_tickets.sum())
    S.check('sl_18 groups sum to the all row, 4+', a.plus4_tickets, d.plus4_tickets.sum())
    S.check('sl_18 every row on the same months, under 4', 0, float(np.ptp(t.under4_months)), 1e-6)
    S.check('sl_18 every row on the same months, 4+', 0, float(np.ptp(t.plus4_months)), 1e-6)

    # The definitions' numbers: 6,750 tickets on 8,946 listed machines; the bands and the period; 2,000 draws.
    terms = T.terms()
    m = re.search(r'([\d,]+) tickets on ([\d,]+) listed machines', terms['rate'][1])
    S.check('sl_18 definition: 6,750 tickets = the all row', a.under4_tickets + a.plus4_tickets,
            int(m.group(1).replace(',', '')))
    S.check('sl_18 definition: 6,750 tickets = the pinned fx_summary', pins['pin fx_summary tickets'],
            int(m.group(1).replace(',', '')))
    S.check('sl_18 definition: 8,946 listed machines = the pinned fx_summary', pins['pin fx_summary machines_exposed'],
            int(m.group(2).replace(',', '')))
    S.check('sl_18 definition: under 4 = the young bands <1, 1-2, 2-4', 1,
            int(s['definitions']['young_bands'] == ['<1', '1-2', '2-4']
                and '(<1, 1-2 and 2-4 years)' in terms['under4'][1]))
    S.check('sl_18 definition: Aug 2025 to Aug 2026 = the period', 1,
            int(s['definitions']['period'] == ['2025-08-01', '2026-08-31']
                and '(Aug 2025 to Aug 2026)' in terms['under4'][1]))
    S.check('sl_18 definition: 2,000 bootstrap draws', s['n_boot'],
            int(re.search(r'\(([\d,]+) draws\)', terms['interval'][1]).group(1).replace(',', '')))
    S.check('sl_18 definition: the colour rule as drawn (blue = the interval excludes 1)', 1,
            int('blue = the interval excludes 1' in terms['rate_ratio_crude'][1]))

    fig, ax = S.figure(S.HALF_TALL)
    fig.set_dpi(S.DPI)                           # the layout checks measure in output pixels
    n = len(d)
    y_all = n + GAP
    rows = [(i, r, False) for i, r in d.iterrows()] + [(y_all, a, True)]
    yax = ax.get_yaxis_transform()               # x in axes fractions, y in data: the Ratio column at x = 1
    rax = offset_copy(yax, fig=fig, x=RATES_AT, units='points')   # the Per 100 column
    values = []                                  # (row type, [its value texts])
    for y, r, is_all in rows:
        u = 100 * r.under4_tickets / r.under4_months
        p = 100 * r.plus4_tickets / r.plus4_months
        ratio = u / p
        S.check(f'sl_18 {r.type} under-4 rate = 100 x tickets / months', u, r.under4_rate_per_100, 1e-9)
        S.check(f'sl_18 {r.type} 4+ rate = 100 x tickets / months', p, r.plus4_rate_per_100, 1e-9)
        S.check(f'sl_18 {r.type} rate ratio = the CSV', ratio, r.rate_ratio, 1e-9)
        S.check(f'sl_18 {r.type} interval contains the estimate', 1, int(r.rate_ratio_lo <= ratio <= r.rate_ratio_hi))
        S.check(f'sl_18 {r.type} interval inside the axes ({X_LO} to {X_HI})', 1,
                int(X_LO < r.rate_ratio_lo and r.rate_ratio_hi < X_HI))
        sig = excludes_one(r.rate_ratio_lo, r.rate_ratio_hi)
        colour = S.NAVY if is_all else S.BLUE if sig else S.GRAY
        ax.plot([r.rate_ratio_lo, r.rate_ratio_hi], [y, y], color=colour, lw=2.5, solid_capstyle='round', zorder=2,
                gid=r.type)
        ax.scatter(ratio, y, s=90, color=colour, zorder=3, edgecolor=S.WHITE, linewidth=1.5, gid=r.type)
        label = f'{ratio:.2f}'
        rates = f'{u:.2f} / {p:.2f}'
        S.check(f'sl_18 {r.type} label {label}', ratio, float(label), 0.005)
        S.check(f'sl_18 {r.type} label {rates}: under 4', u, float(rates.split(' / ')[0]), 0.005)
        S.check(f'sl_18 {r.type} label {rates}: 4+', p, float(rates.split(' / ')[1]), 0.005)
        values.append((r.type, [
            ax.text(1, y, label, transform=yax, va='center', ha='right', fontsize=S.SMALL,
                    color=S.INK if sig else S.INK2, weight='bold' if sig else 'normal'),
            ax.text(1, y, rates, transform=rax, va='center', ha='right', fontsize=S.SMALL, color=S.INK2)]))

    # The All row: the CSV's own numbers, and slide 4's (pinned in followups.py).
    S.check('sl_18 all row: 6,750 tickets', 6750, a.under4_tickets + a.plus4_tickets)
    S.check('sl_18 all row: under-4 rate = slide 4 (8.05)', pins[PIN_U4], a.under4_rate_per_100, 1e-5)
    S.check('sl_18 all row: 4+ rate = slide 4 (4.84)', pins[PIN_P4], a.plus4_rate_per_100, 1e-5)
    S.check('sl_18 all row: rate ratio = slide 4 (1.66)', pins[PIN_U4] / pins[PIN_P4], a.rate_ratio, 1e-5)
    # Sort order: highest ratio at the top, the All row above every group.
    S.check('sl_18 rows sorted by the rate ratio, highest at the top', 1, int(d.rate_ratio.is_monotonic_increasing))
    S.check('sl_18 the All row above the groups', 1, int(y_all > n - 1))
    # What was drawn, read back: each bar spans its CSV interval and each dot sits at its CSV ratio, in its row.
    csv = {r.type: (y, r) for y, r, _ in rows}
    bars = {ln.get_gid(): ln for ln in ax.lines if ln.get_gid()}
    dots = {c.get_gid(): c for c in ax.collections if c.get_gid()}
    S.check('sl_18 drawn: one bar and one dot per row', 1, int(sorted(bars) == sorted(dots) == sorted(csv)))
    S.check('sl_18 drawn: bars = the CSV intervals, in their rows', 1,
            int(all(np.allclose(bars[k].get_xdata(), [r.rate_ratio_lo, r.rate_ratio_hi], rtol=0, atol=1e-12)
                    and np.allclose(bars[k].get_ydata(), [y, y]) for k, (y, r) in csv.items())))
    S.check('sl_18 drawn: dots = the CSV ratios, in their rows', 1,
            int(all(np.allclose(dots[k].get_offsets(), [[r.rate_ratio, y]], rtol=0, atol=1e-9)
                    for k, (y, r) in csv.items())))
    # Colour rule, read back from the drawn bars and dots: blue = the interval excludes 1, gray = it includes 1, the
    # All row navy.
    rule = {r.type: S.BLUE if excludes_one(r.rate_ratio_lo, r.rate_ratio_hi) else S.GRAY for _, r in d.iterrows()}
    rule[ALL] = S.NAVY
    S.check('sl_18 colour rule: every bar coloured by its interval', 1,
            int({k: ln.get_color() for k, ln in bars.items()} == rule))
    S.check('sl_18 colour rule: every dot coloured like its bar', 1,
            int(all(np.allclose(dots[k].get_facecolor()[0], to_rgba(v)) for k, v in rule.items())))
    S.check('sl_18 colour rule: Network and Software include 1', 1,
            int(sorted(k for k, v in rule.items() if v == S.GRAY) == ['Network', 'Software']))
    S.check('sl_18 colour rule: bold values = blue rows and the All row', 1,
            int(all((texts[0].get_fontweight() == 'bold') == (rule[k] != S.GRAY) for k, texts in values)))

    ax.axvline(1, color=S.INK2, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.set_xscale('log')
    ax.set_xticks(TICKS)
    ax.set_xticklabels([f'{v:g}×' for v in TICKS])
    ax.set_xlim(X_LO, X_HI)
    mask = {'boxstyle': 'square,pad=0.1', 'facecolor': S.WHITE, 'edgecolor': 'none'}  # hides the grid behind the text
    head = [ax.text(1, y_all + 0.55, 'Per 100, under 4 / 4+', transform=rax, ha='right', va='bottom',
                    fontsize=S.SMALL, color=S.INK2, bbox=mask),
            ax.text(1, y_all + 0.55, 'Ratio', transform=yax, ha='right', va='bottom', fontsize=S.SMALL,
                    color=S.INK2)]
    ax.set_yticks(list(range(n)) + [y_all])
    ax.set_yticklabels(list(d.type) + [ALL])
    lab_all = ax.get_yticklabels()[-1]
    lab_all.set_fontweight('bold')
    lab_all.set_color(S.INK)
    ax.set_ylim(-1.3, y_all + 1.35)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Rate ratio, under 4 vs 4+ years (log scale)')
    notes = [ax.text(0.95, -1.05, '← higher on 4+', ha='right', va='center', fontsize=S.SMALL, color=S.INK2,
                     bbox=mask),
             ax.text(1.05, -1.05, 'higher under 4 →', ha='left', va='center', fontsize=S.SMALL, color=S.INK2,
                     bbox=mask)]
    S.definitions(fig, T.items(TERMS))
    layout_checks(fig, ax, bars, dots, values, head, notes)
    return [S.save(fig, Path(out_dir) / PNG)]


def layout_checks(fig, ax, bars, dots, values, head, notes):
    """Nothing overlaps or leaves the image: each row's numbers right of every bar and dot, no bar or dot under the
    header or the direction note, no two texts touching, every text inside the image (output pixels)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    px = S.DPI / 72                              # pixels per point
    marks = []                                   # each bar and dot as a pixel box (round caps and white edges included)
    for k, ln in bars.items():
        (x0, y0), (x1, _) = ax.transData.transform(np.column_stack(ln.get_data()))
        cap = ln.get_linewidth() / 2 * px
        marks.append((x0 - cap, y0 - cap, x1 + cap, y0 + cap))
        (cx, cy), = ax.transData.transform(dots[k].get_offsets())
        rad = (np.sqrt(dots[k].get_sizes()[0]) / 2 + dots[k].get_linewidths()[0] / 2) * px
        marks.append((cx - rad, cy - rad, cx + rad, cy + rad))
    right = max(mk[2] for mk in marks)
    left_values = min(Text.get_window_extent(x, r).x0 for _, texts in values for x in texts)
    S.check('sl_18 layout: every number right of every bar and dot', 1, int(right + 4 * px < left_values))

    def hit(box):
        return any(box.x0 < mk[2] and mk[0] < box.x1 and box.y0 < mk[3] and mk[1] < box.y1 for mk in marks)
    S.check('sl_18 layout: bars or dots under the header or the direction note', 0,
            sum(hit(Text.get_window_extent(x, r)) for x in head + notes))
    texts = [x for _, ts in values for x in ts] + head + notes + [
        lab for lab in ax.get_yticklabels() + ax.get_xticklabels() + [ax.xaxis.label] if lab.get_text()]
    boxes = [Text.get_window_extent(x, r) for x in texts]
    S.check('sl_18 layout: texts touching', 0,
            sum(boxes[i].overlaps(boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))))
    every = [x for x in fig.findobj(Text) if x.get_visible() and x.get_text()]
    S.check('sl_18 layout: texts outside the image', 0,
            sum(not (b.x0 >= 0 and b.y0 >= 0 and b.x1 <= fig.bbox.x1 and b.y1 <= fig.bbox.y1)
                for b in (Text.get_window_extent(x, r) for x in every)))


if __name__ == '__main__':
    plot()
