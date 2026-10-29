#!/usr/bin/env python3
"""Slide chart 24 (follow-up to slide 5): what type is the next ticket in a 7-day follow-up?

Pairing matrix at group level (docs/09 §5 B1): rows = the index ticket's request type, columns = the type of its next
ticket, for the 631 index tickets whose next unplanned ticket opens within 7 days. Software, Operator error and Other
are pooled as Other (followup_terms.MATRIX_MAP). Cell = share of the row's 7-day follow-ups (each row sums to 100%),
shaded white to blue, the diagonal (same group) outlined in navy. Row label: the row's follow-ups and the share of
that group's eligible index tickets that have one.

Also holds the cell helpers the other heat tables share (sl_22, sl_25, sl_30): the white-to-blue ramp, the text
colour by contrast, and the whole-percent cell label.

Input:  verification/outputs/followups/rp_pairs.csv (one row per eligible index ticket), rp_matrix.csv,
        rp_index_type.csv, followups_summary.json
Output: viz/figures/slides/sl_24_repeat_pairings_7d.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_24_repeat_pairings_7d.png'
TERMS = ['repeat7', 'pairing7', 'other_groups']

RAMP_TOP = 0.6          # a share of 60% or more is full BLUE; 0 is WHITE
GAP = 2.0               # white gap between cells, points


# ---- cell helpers shared by the heat tables (sl_22, sl_24, sl_25, sl_30) ----

def cell_color(share):
    """WHITE at 0, BLUE at RAMP_TOP or more, straight between (one hue, light to dark)."""
    t = float(np.clip(share / RAMP_TOP, 0.0, 1.0)) if np.isfinite(share) else 0.0
    return tuple((1 - t) * np.array(to_rgb(S.WHITE)) + t * np.array(to_rgb(S.BLUE)))


def _luminance(color):
    c = np.array(to_rgb(color))
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(c @ np.array([0.2126, 0.7152, 0.0722]))


def contrast(a, b):
    """WCAG contrast ratio of two colours."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_color(bg):
    """INK on light cells, WHITE on dark ones: whichever has more contrast with the cell."""
    return S.WHITE if contrast(S.WHITE, bg) > contrast(S.INK, bg) else S.INK


def pct_text(share, n=None):
    """A share as a whole percent ('23%'), '<1%' when it is above 0 but rounds to 0, '' when the cell is empty."""
    if n == 0 or not np.isfinite(share):
        return ''
    v = int(np.floor(100 * share + 0.5))
    return '<1%' if v == 0 and share > 0 else f'{v}%'


def pct_drawn(text):
    """The percent a pct_text label shows, for S.check with tolerance 0.5: '<1%' reads as 0.5 (0 to 1)."""
    return 0.5 if text == '<1%' else float(text.rstrip('%'))


def text_width_pt(fig, text, size, weight='normal'):
    """Width of a string in points, measured with the figure's renderer."""
    r = fig.canvas.get_renderer()
    w = r.get_text_width_height_descent(text, FontProperties(family='sans-serif', size=size, weight=weight),
                                        ismath=False)[0]
    return w * 72 / fig.dpi


def draw_cells(ax, shares, counts, size=S.SMALL, ink_small=None):
    """Row-normalised shares as white-to-blue cells with whole-percent text (blank for no pairs) and the diagonal
    outlined in NAVY; cell (i, j) spans [j, j+1] x [i, i+1]. ink_small: cells with fewer pairs get lighter text,
    in italic so the cue holds on every cell: INK2 where it stays legible (contrast 3:1 or more), else the cell's
    usual INK or WHITE. Returns {(i, j): text drawn}."""
    drawn = {}
    n_rows, n_cols = shares.shape
    for i in range(n_rows):
        for j in range(n_cols):
            share, n = shares[i, j], counts[i, j]
            bg = cell_color(share)
            ax.add_patch(Rectangle((j, i), 1, 1, facecolor=bg, edgecolor=S.WHITE, linewidth=GAP, zorder=1))
            txt = pct_text(share, n)
            drawn[(i, j)] = txt
            if not txt:
                continue
            color, style = text_color(bg), 'normal'
            if ink_small is not None and n < ink_small:
                style = 'italic'
                if contrast(S.INK2, bg) >= 3.0:
                    color = S.INK2
            ax.text(j + 0.5, i + 0.5, txt, ha='center', va='center_baseline', fontsize=size, color=color,
                    style=style, zorder=3)
    for k in range(min(n_rows, n_cols)):
        ax.add_patch(Rectangle((k, k), 1, 1, fill=False, edgecolor=S.NAVY, linewidth=2.0, zorder=2))
    ax.set_xlim(0, n_cols)
    ax.set_ylim(n_rows, 0)
    return drawn


# ---- the group-level pairing matrix (sl_24: 7 days, sl_25: 30 days) ----

def to_slide_group(g):
    return T.MATRIX_MAP.get(g, g)


def pairing_counts(days):
    """Index group x next group counts of the repeats within `days` (rp_pairs.csv), and each index group's eligible
    tickets, on the slide's eight groups."""
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    p['i'] = p.index_group.map(to_slide_group)
    rep = p[p[f'repeat_{days}']].copy()
    rep['n'] = rep.next_group.map(to_slide_group)
    g = T.MATRIX_GROUPS
    counts = pd.crosstab(rep.i, rep.n).reindex(index=g, columns=g, fill_value=0)
    eligible = p.groupby('i').size().reindex(g, fill_value=0)
    return p, rep, counts, eligible


def pairing_figure(days, tag):
    """The pairing matrix for repeats within `days` (7 or 30), with every number checked. Returns the figure; the
    caller prints the definitions and saves it."""
    g = T.MATRIX_GROUPS
    b = T.summary()['facts']['part_b']
    p, rep, counts, eligible = pairing_counts(days)
    total = int(counts.to_numpy().sum())
    unmapped = (set(p.index_group.map(to_slide_group)) | set(rep.n)) - set(g)
    S.check(f'{tag} every index and next group is one of the eight on the slide', 0, len(unmapped))
    S.check(f'{tag} eligible index tickets = summary (6,665)', b['eligible'], len(p))
    S.check(f'{tag} eligible tickets by index group add up', b['eligible'], int(eligible.sum()))
    S.check(f'{tag} matrix total = summary repeats within {days} days', b[f'repeats_{days}'], total)
    S.check(f'{tag} matrix total = {"631" if days == 7 else "1,574"} (docs/09 pins)', 631 if days == 7 else 1574, total)
    S.check(f'{tag} every repeat has a next ticket {days} days or less later', 0,
            int((rep.gap_days.isna() | (rep.gap_days < 0) | (rep.gap_days > days)).sum()))
    S.check(f'{tag} every index ticket opened before 2 Aug 2026', 0, int((p.opened_date >= '2026-08-02').sum()))

    # The same matrix from the committed group-level matrix (all ten groups), pooled the same way.
    m = pd.read_csv(T.FU / 'rp_matrix.csv')
    m = m[(m.window == f'{days} days') & (m.level == 'group')]
    mc = (m.assign(i=m.index_type.map(to_slide_group), n=m.next_type.map(to_slide_group))
          .pivot_table(index='i', columns='n', values='pairs', aggfunc='sum')
          .reindex(index=g, columns=g).fillna(0))
    S.check(f'{tag} matrix = rp_matrix.csv ({days} days, group level), every cell', 0,
            float(np.abs(mc.to_numpy() - counts.to_numpy()).max()))
    # Row labels: repeats and repeat % by index group, against rp_index_type.csv (Other = three groups pooled).
    it = pd.read_csv(T.FU / 'rp_index_type.csv')
    it = it.assign(i=it.index_group.map(to_slide_group)).groupby('i')[['eligible', f'repeats_{days}']].sum().reindex(g)

    shares = counts.to_numpy() / counts.to_numpy().sum(axis=1, keepdims=True)
    fig, ax = S.figure(S.HALF_TALL)
    drawn = draw_cells(ax, shares, counts.to_numpy())
    for i, gi in enumerate(g):
        S.check(f'{tag} {gi} row sums to 100%', 1, float(shares[i].sum()), 1e-9)
        for j, gj in enumerate(g):
            txt = drawn[(i, j)]
            if txt:
                S.check(f'{tag} {gi} -> {gj} share of the row', 100 * shares[i, j], pct_drawn(txt), 0.5)
            else:
                S.check(f'{tag} {gi} -> {gj} blank = no pairs', 0, int(counts.iloc[i, j]))

    # Row labels: the group (tick label), then its repeats and the share of its eligible tickets that repeat, in
    # two right-aligned columns between the names and the matrix.
    reps = counts.sum(axis=1)
    pcts = [int(np.floor(100 * reps[gi] / eligible[gi] + 0.5)) for gi in g]
    rep_txt = [f'{int(reps[gi]):,}' for gi in g]
    pct_txt = [f'({v}%)' for v in pcts]
    for gi, rt, pt in zip(g, rep_txt, pct_txt):
        S.check(f'{tag} {gi} row label: repeats = rp_index_type.csv', it.loc[gi, f'repeats_{days}'],
                int(rt.replace(',', '')))
        S.check(f'{tag} {gi} row label: eligible = rp_index_type.csv', it.loc[gi, 'eligible'], eligible[gi])
        S.check(f'{tag} {gi} row label: % of its eligible tickets that repeat', 100 * reps[gi] / eligible[gi],
                float(pt.strip('(%)')), 0.5)
    w_pct = max(text_width_pt(fig, t, S.SMALL) for t in pct_txt)
    w_rep = max(text_width_pt(fig, t, S.SMALL) for t in rep_txt)
    w_name = max(text_width_pt(fig, t, S.TICK) for t in g)
    gap0, gap1, gap2 = 7, 5, 11           # points: matrix to %, % to repeats, repeats to name
    for i in range(len(g)):
        for txt, x in ((pct_txt[i], -gap0), (rep_txt[i], -(gap0 + w_pct + gap1))):
            ax.annotate(txt, xy=(0, i + 0.5), xycoords=('axes fraction', 'data'), xytext=(x, 0),
                        textcoords='offset points', ha='right', va='center_baseline', fontsize=S.SMALL, color=S.INK2)
    pad = gap0 + w_pct + gap1 + w_rep + gap2
    ax.set_yticks(np.arange(len(g)) + 0.5)
    ax.set_yticklabels(g)
    ax.tick_params(axis='y', pad=pad)
    for t in ax.get_yticklabels():
        t.set_verticalalignment('center_baseline')
    ax.set_xticks(np.arange(len(g)) + 0.5)
    ax.set_xticklabels([T.MATRIX_SHORT[x] for x in g], fontsize=S.SMALL)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position('top')
    ax.tick_params(axis='x', pad=4)
    S.style_axes(ax, grid=None, baseline=None)
    ax.set_xlabel('Next ticket', labelpad=8)
    # 'Index ticket' heads the row labels, level with the column labels (the y axis label, set horizontally).
    ax.annotate('Index ticket', xy=(0, 1), xycoords='axes fraction', xytext=(-(pad + w_name), 4),
                textcoords='offset points', ha='left', va='bottom', fontsize=S.FONT, color=S.INK2)

    # The definitions' numbers.
    t = T.terms()
    if days == 7:
        mm = re.search(r'within (\d+) days .* before (\d+) Aug 2026 \(([\d,]+) of ([\d,]+)\)', t['repeat7'][1])
        S.check(f'{tag} definition: within 7 days', days, int(mm.group(1)))
        S.check(f'{tag} definition: 631 follow-ups', total, int(mm.group(3).replace(',', '')))
        S.check(f'{tag} definition: 6,665 eligible', len(p), int(mm.group(4).replace(',', '')))
    if days == 30:
        mm = re.search(r'within (\d+) days \(7-day: within (\d+)\) .* before (\d+) Aug 2026 \(([\d,]+)\)',
                       t['repeat'][1])
        S.check(f'{tag} definition: within 30 days', days, int(mm.group(1)))
        S.check(f'{tag} definition: 6,665 eligible', len(p), int(mm.group(4).replace(',', '')))
    S.check(f'{tag} definition: Other = Software, Operator error and Other', 1,
            int(sorted(k for k, v in T.MATRIX_MAP.items() if v == 'Other') == ['Operator error', 'Other', 'Software']))
    return fig


def plot(out_dir=S.FIG_DIR):
    fig = pairing_figure(7, 'sl_24')
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
